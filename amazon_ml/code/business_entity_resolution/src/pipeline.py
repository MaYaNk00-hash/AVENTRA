import os
import sys
import time
import pickle
import argparse
import subprocess
import polars as pl
import numpy as np
from collections import defaultdict
from rapidfuzz import distance, fuzz
import re

sys.path.insert(0, os.path.dirname(__file__))
import blocking
import features

sys.stdout.reconfigure(encoding='utf-8')

SPLIT_RE = re.compile(r'[^a-z0-9]+')
NUM_RE = re.compile(r'\b\d{1,6}\b')

ADDR_STOPWORDS = {
    'and', 'the', 'of', 'in', 'at', 'on', 'for', 'to', 'a', 'an', 'by',
    'no', 'near', 'opp', 'opposite', 'behind', 'fl', 'floor', 'block', 'unit',
    'plot', 'road', 'rd', 'street', 'st', 'avenue', 'ave', 'lane', 'ln', 'dr', 'drive',
    'hwy', 'highway', 'pkwy', 'parkway', 'blvd', 'boulevard', 'bldg', 'building',
    'apt', 'apartment', 'suite', 'ste', 'room', 'rm', 'box', 'po', 'null', 'none',
    'c/o', 'beside', 'ground', 'first', 'second', 'third', '1st', '2nd', '3rd', 'floor',
    'city', 'state', 'district', 'dist', 'taluk', 'taluka', 'vill', 'village', 'nagar',
    'main', 'cross', 'west', 'east', 'north', 'south', 'new', 'old'
}

def clean(s):
    return " ".join(SPLIT_RE.split(s.lower())).strip() if s else ""

def get_tokens(s):
    return set(SPLIT_RE.split(s.lower())) - {""} if s else set()

def get_distinctive_addr_tokens(s):
    if not s:
        return set()
    return {t for t in SPLIT_RE.split(s.lower()) if len(t) >= 4 and t not in ADDR_STOPWORDS and not t.isdigit()}

def get_nums(s):
    if not s:
        return set()
    raw = NUM_RE.findall(s.lower())
    return {n.lstrip('0') or '0' for n in raw}

def score_candidate(s1_cn, s1_ca, s1_tn, s1_ta, s1_da, s1_na,
                    c_cn, c_ca, c_tn, c_ta, c_da, c_na, target_has_non_ascii):
    jw_name = distance.JaroWinkler.similarity(s1_cn, c_cn)
    name_jaccard = len(s1_tn & c_tn) / max(1, len(s1_tn | c_tn)) if (s1_tn or c_tn) else 0.0
    
    if s1_ca and c_ca:
        jw_addr = distance.JaroWinkler.similarity(s1_ca, c_ca)
        addr_jaccard = len(s1_ta & c_ta) / max(1, len(s1_ta | c_ta)) if (s1_ta or c_ta) else 0.0
        num_overlap = 1.0 if (s1_na and c_na and not s1_na.isdisjoint(c_na)) else 0.0
        d_addr_overlap = 1.0 if (s1_da and c_da and not s1_da.isdisjoint(c_da)) else 0.0
    else:
        jw_addr = 0.0
        addr_jaccard = 0.0
        num_overlap = 0.0
        d_addr_overlap = 0.0
        
    base_score = max(
        jw_name,
        0.7 * jw_name + 0.3 * name_jaccard,
        0.5 * jw_name + 0.3 * jw_addr + 0.2 * num_overlap,
        0.4 * jw_name + 0.4 * addr_jaccard + 0.2 * d_addr_overlap
    )
    
    # FIX 2: Non-Latin script guarded address boost
    if target_has_non_ascii and s1_ca and c_ca and jw_addr >= 0.90 and addr_jaccard >= 0.85:
        base_score = max(base_score, 0.5 * jw_addr + 0.5 * addr_jaccard)
        
    return base_score

def run_worker_shard(test_dir, output_dir, model_path, country, shard_id, num_shards, max_bucket_size, cand_threshold, top_k, match_threshold, batch_size=2000):
    t0 = time.time()
    with open(model_path, "rb") as f:
        model = pickle.load(f)
        
    s1_path = os.path.join(test_dir, "test_source1.tsv")
    s2_path = os.path.join(test_dir, "test_source2.tsv")
    s3_path = os.path.join(test_dir, "test_source3.tsv")
    
    s2_c = pl.read_csv(s2_path, separator="\t", infer_schema_length=0).filter(pl.col("country") == country)
    s3_c = pl.read_csv(s3_path, separator="\t", infer_schema_length=0).filter(pl.col("country") == country)
    target_df = pl.concat([s2_c, s3_c])
    
    target_ids = target_df["entity_id"].to_list()
    raw_names = target_df["business_name"].to_list()
    raw_addrs = target_df["business_address"].to_list()
    
    target_c_names = [clean(n) for n in raw_names]
    target_c_addrs = [clean(a) for a in raw_addrs]
    target_t_names = [get_tokens(n) for n in raw_names]
    target_t_addrs = [get_tokens(a) for a in raw_addrs]
    target_d_addrs = [get_distinctive_addr_tokens(a) for a in raw_addrs]
    target_n_addrs = [get_nums(a) for a in raw_addrs]
    target_has_non_ascii = [any(ord(c) > 127 for c in (n or '')) for n in raw_names]
    target_is_s2 = [eid.startswith("S2-") for eid in target_ids]
    
    index = defaultdict(list)
    for idx, (n, a) in enumerate(zip(raw_names, raw_addrs)):
        for k in blocking.get_keys(n, a):
            index[k].append(idx)
            
    s1_c = pl.read_csv(s1_path, separator="\t", infer_schema_length=0).filter(pl.col("country") == country)
    s1_ids = s1_c["entity_id"].to_list()
    s1_names = s1_c["business_name"].to_list()
    s1_addrs = s1_c["business_address"].to_list()
    
    s1_tuples = list(zip(s1_ids, s1_names, s1_addrs))
    s1_shard = [s1_tuples[i] for i in range(shard_id, len(s1_tuples), num_shards)]
    
    tmp_m_path = os.path.join(output_dir, f"tmp_match_{country}_{shard_id}.tsv")
    tmp_c_path = os.path.join(output_dir, f"tmp_cand_{country}_{shard_id}.tsv")
    
    done = 0
    with open(tmp_m_path, "w", encoding="utf-8") as f_match, \
         open(tmp_c_path, "w", encoding="utf-8") as f_cand:
        
        for b_start in range(0, len(s1_shard), batch_size):
            b_tuples = s1_shard[b_start:b_start + batch_size]
            
            pair_s1_indices = []
            pair_cand_indices = []
            pair_features = []
            
            cand_lines = []
            match_lines = []
            
            for local_idx, (sid, name, addr) in enumerate(b_tuples):
                s1_cn = clean(name)
                s1_ca = clean(addr)
                s1_tn = get_tokens(name)
                s1_ta = get_tokens(addr)
                s1_da = get_distinctive_addr_tokens(addr)
                s1_na = get_nums(addr)
                
                keys = blocking.get_keys(name, addr)
                bucket_cand_indices = set()
                for k in keys:
                    bucket = index.get(k)
                    if bucket and len(bucket) <= max_bucket_size:
                        bucket_cand_indices.update(bucket)
                        
                if not bucket_cand_indices:
                    cand_lines.append(f"{sid}\t\n")
                    continue
                    
                scored = []
                for cidx in bucket_cand_indices:
                    sc = score_candidate(
                        s1_cn, s1_ca, s1_tn, s1_ta, s1_da, s1_na,
                        target_c_names[cidx], target_c_addrs[cidx],
                        target_t_names[cidx], target_t_addrs[cidx],
                        target_d_addrs[cidx], target_n_addrs[cidx],
                        target_has_non_ascii[cidx]
                    )
                    scored.append((sc, cidx))
                    
                scored.sort(key=lambda x: x[0], reverse=True)
                
                # Filter candidates by cand_threshold (0.65) and take top K (20)
                filtered_top_k = [cidx for (sc, cidx) in scored if sc >= cand_threshold][:top_k]
                
                if not filtered_top_k:
                    cand_lines.append(f"{sid}\t\n")
                    continue
                    
                cand_ids = [target_ids[cidx] for cidx in filtered_top_k]
                cand_lines.append(f"{sid}\t{','.join(cand_ids)}\n")
                
                for cidx in filtered_top_k:
                    pair_s1_indices.append(local_idx)
                    pair_cand_indices.append(cidx)
                    
                    feats = features.extract_features(
                        s1_cn, s1_ca, s1_tn, s1_ta, s1_na,
                        target_c_names[cidx], target_c_addrs[cidx],
                        target_t_names[cidx], target_t_addrs[cidx],
                        target_n_addrs[cidx], target_is_s2[cidx]
                    )
                    pair_features.append(feats)
                    
            if pair_features:
                np_feats = np.array(pair_features, dtype=np.float32)
                probs = model.predict_proba(np_feats)[:, 1]
            else:
                probs = []
                
            s1_matches = [[] for _ in range(len(b_tuples))]
            for s1_idx, cidx, p in zip(pair_s1_indices, pair_cand_indices, probs):
                if p >= match_threshold:
                    s1_matches[s1_idx].append(target_ids[cidx])
                    
            for local_idx, (sid, _, _) in enumerate(b_tuples):
                m_list = s1_matches[local_idx]
                if m_list:
                    match_lines.append(f"{sid}\t{','.join(m_list)}\n")
                else:
                    match_lines.append(f"{sid}\t\n")
                    
            f_match.writelines(match_lines)
            f_cand.writelines(cand_lines)
            f_match.flush()
            f_cand.flush()
            
            done += len(b_tuples)
            if done % 10000 == 0 or done == len(s1_shard):
                elapsed = time.time() - t0
                print(f"  [{country} Worker {shard_id+1}/{num_shards}] Processed {done:,}/{len(s1_shard):,} entities ({done/len(s1_shard)*100:.1f}%) - {done/max(0.1, elapsed):.1f} ent/s", flush=True)

def main():
    parser = argparse.ArgumentParser(description="Business Entity Resolution Pipeline")
    parser.add_argument("--test-dir", type=str, default="dataset/test", help="Path to test directory")
    parser.add_argument("--output-dir", type=str, default="output", help="Path to output directory")
    parser.add_argument("--model-path", type=str, default="models/matching_lgb_model.pkl", help="Path to model file")
    parser.add_argument("--max-bucket-size", type=int, default=150, help="Max candidates per key bucket")
    parser.add_argument("--cand-threshold", type=float, default=0.65, help="Candidate similarity threshold θ")
    parser.add_argument("--top-k", type=int, default=20, help="Top-K candidate cap")
    parser.add_argument("--match-threshold", type=float, default=0.65, help="Classification probability threshold")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel worker processes")
    
    parser.add_argument("--worker-mode", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--country", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--shard-id", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--num-shards", type=int, default=1, help=argparse.SUPPRESS)
    
    args = parser.parse_args()
    
    if args.worker_mode:
        run_worker_shard(
            test_dir=args.test_dir,
            output_dir=args.output_dir,
            model_path=args.model_path,
            country=args.country,
            shard_id=args.shard_id,
            num_shards=args.num_shards,
            max_bucket_size=args.max_bucket_size,
            cand_threshold=args.cand_threshold,
            top_k=args.top_k,
            match_threshold=args.match_threshold
        )
        return
        
    start_time = time.time()
    os.makedirs(args.output_dir, exist_ok=True)
    
    print("==================================================", flush=True)
    print("BUSINESS ENTITY RESOLUTION PIPELINE", flush=True)
    print("==================================================", flush=True)
    print(f"Test Directory:      {args.test_dir}", flush=True)
    print(f"Output Directory:    {args.output_dir}", flush=True)
    print(f"Model Path:          {args.model_path}", flush=True)
    print(f"Top-K Cap:           {args.top_k}", flush=True)
    print(f"Candidate Threshold: {args.cand_threshold}", flush=True)
    print(f"Match Threshold:     {args.match_threshold}", flush=True)
    print(f"Max Bucket Size:     {args.max_bucket_size}", flush=True)
    print(f"Worker Processes:    {args.workers}", flush=True)
    
    s1_path = os.path.join(args.test_dir, "test_source1.tsv")
    s1_full = pl.read_csv(s1_path, separator="\t", infer_schema_length=0)
    countries = sorted(list(set(s1_full["country"].to_list())))
    print(f"\nCountries to process: {countries}", flush=True)
    print(f"Total Source 1 test entities: {len(s1_full):,}", flush=True)
    
    matching_file = os.path.join(args.output_dir, "matching_results.tsv")
    candidate_file = os.path.join(args.output_dir, "candidate_pairs.tsv")
    
    with open(matching_file, "w", encoding="utf-8") as f_match, \
         open(candidate_file, "w", encoding="utf-8") as f_cand:
        f_match.write("source1_entity_id\tmatched_entity_ids\n")
        f_cand.write("source1_entity_id\tcandidate_entity_ids\n")
        
    total_processed_s1 = 0
    
    for country in countries:
        c_t0 = time.time()
        print(f"\n==========================================", flush=True)
        print(f"PROCESSING COUNTRY: {country}", flush=True)
        print(f"==========================================", flush=True)
        
        s1_c_count = len(s1_full.filter(pl.col("country") == country))
        print(f"Spawning {args.workers} worker processes for {s1_c_count:,} {country} entities...", flush=True)
        
        procs = []
        for shard_id in range(args.workers):
            cmd = [
                sys.executable,
                os.path.abspath(__file__),
                "--worker-mode",
                "--test-dir", args.test_dir,
                "--output-dir", args.output_dir,
                "--model-path", args.model_path,
                "--country", country,
                "--shard-id", str(shard_id),
                "--num-shards", str(args.workers),
                "--max-bucket-size", str(args.max_bucket_size),
                "--cand-threshold", str(args.cand_threshold),
                "--top-k", str(args.top_k),
                "--match-threshold", str(args.match_threshold)
            ]
            p = subprocess.Popen(cmd)
            procs.append(p)
            
        for p in procs:
            p.wait()
            if p.returncode != 0:
                raise RuntimeError(f"Worker process failed with return code {p.returncode}")
                
        print(f"All workers finished for {country}. Merging shard files...", flush=True)
        
        with open(matching_file, "a", encoding="utf-8") as f_match, \
             open(candidate_file, "a", encoding="utf-8") as f_cand:
            
            for shard_id in range(args.workers):
                tmp_m = os.path.join(args.output_dir, f"tmp_match_{country}_{shard_id}.tsv")
                tmp_c = os.path.join(args.output_dir, f"tmp_cand_{country}_{shard_id}.tsv")
                
                with open(tmp_m, "r", encoding="utf-8") as f_in:
                    for line in f_in:
                        f_match.write(line)
                        total_processed_s1 += 1
                with open(tmp_c, "r", encoding="utf-8") as f_in:
                    for line in f_in:
                        f_cand.write(line)
                        
                os.remove(tmp_m)
                os.remove(tmp_c)
                
        print(f"Completed {country} in {time.time()-c_t0:.2f}s ({(time.time()-c_t0)/60:.2f}m).", flush=True)
        
    print("\n==================================================", flush=True)
    print("PIPELINE EXECUTION COMPLETED", flush=True)
    print("==================================================", flush=True)
    print(f"Total S1 entities processed: {total_processed_s1:,}", flush=True)
    print(f"Output files saved:")
    print(f"  - {matching_file}")
    print(f"  - {candidate_file}")
    print(f"Total Pipeline Runtime: {time.time()-start_time:.2f}s ({(time.time()-start_time)/60:.2f} minutes)", flush=True)

if __name__ == "__main__":
    main()
