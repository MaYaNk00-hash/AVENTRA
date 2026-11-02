import polars as pl
import numpy as np
import time
import sys
import os
from collections import defaultdict
from rapidfuzz import distance, fuzz
import re
import itertools

sys.stdout.reconfigure(encoding='utf-8')

LEGAL_SUFFIXES = {
    'inc', 'incorporated', 'corp', 'corporation', 'llc', 'ltd', 'limited',
    'pvt', 'private', 'co', 'company', 'services', 'enterprises', 'associates',
    'group', 'center', 'centre', 'solutions', 'technologies', 'holdings', 'trust',
    'sarl', 'sas', 'sa', 'eurl', 'gmbh', 'llp', 'pllc', 'dba', 'fka',
    'formerly', 'c/o', 'care', 'smt', 'shri', 'sri', 'dr', 'mr', 'mrs',
    'trading', 'as', 'com', 'org', 'net', 'in', 'us', 'fr', 'web', 'online',
    'intl', 'international'
}

ADDR_STOPWORDS = {
    'and', 'the', 'of', 'in', 'at', 'on', 'for', 'to', 'a', 'an', 'by',
    'no', 'near', 'opp', 'opposite', 'behind', 'fl', 'floor', 'block', 'unit',
    'plot', 'road', 'rd', 'street', 'st', 'avenue', 'ave', 'lane', 'ln', 'dr', 'drive',
    'hwy', 'highway', 'pkwy', 'parkway', 'blvd', 'boulevard', 'bldg', 'building',
    'apt', 'apartment', 'suite', 'ste', 'room', 'rm', 'box', 'po', 'null', 'none',
    'c/o', 'beside', 'ground', 'first', 'second', 'third', '1st', '2nd', '3rd', 'floor',
    'city', 'state', 'district', 'dist', 'taluk', 'taluka', 'vill', 'village', 'nagar'
}

SPLIT_RE = re.compile(r'[^a-z0-9]+')
NUM_RE = re.compile(r'\b\d{1,6}\b')

def get_keys(name_str, addr_str):
    name_clean = name_str.lower() if name_str else ""
    raw_name_tokens = [t for t in SPLIT_RE.split(name_clean) if t]
    clean_name_tokens = [t for t in raw_name_tokens if len(t) > 1 and t not in LEGAL_SUFFIXES]
    
    addr_clean = addr_str.lower() if addr_str else ""
    raw_addr_tokens = [t for t in SPLIT_RE.split(addr_clean) if t]
    clean_addr_tokens = [t for t in raw_addr_tokens if len(t) > 2 and t not in ADDR_STOPWORDS and not t.isdigit()]
    addr_nums = NUM_RE.findall(addr_clean)
    
    keys = []
    
    # 1. Full name compact representation
    compact = "".join(raw_name_tokens)
    if len(compact) >= 5:
        keys.append(f"fn:{compact[:20]}")
        
    # 2. Significant name token pairs (combinations of up to 5 tokens)
    if len(clean_name_tokens) >= 2:
        for t0, t1 in itertools.combinations(clean_name_tokens[:5], 2):
            s0, s1 = min(t0, t1), max(t0, t1)
            keys.append(f"n2:{s0}_{s1}")
            keys.append(f"p2:{s0[:3]}_{s1[:3]}")
    elif len(clean_name_tokens) == 1:
        keys.append(f"n1:{clean_name_tokens[0]}")
        
    # 3. First 6 chars of compact name
    if len(compact) >= 6:
        keys.append(f"c6:{compact[:6]}")
        
    # 4. First name token + address number
    if clean_name_tokens and addr_nums:
        keys.append(f"tn:{clean_name_tokens[0]}_{addr_nums[0]}")
        if len(addr_nums) > 1:
            keys.append(f"tn:{clean_name_tokens[0]}_{addr_nums[-1]}")
            
    # 5. Address-based blocking keys (for transliterated/DBA records)
    if addr_nums and clean_addr_tokens:
        for atok in clean_addr_tokens[:3]:
            for num in addr_nums[:2]:
                keys.append(f"an:{atok}_{num}")
                
    # 6. Address token pairs
    dist_addr = [t for t in clean_addr_tokens if len(t) >= 4]
    if len(dist_addr) >= 2:
        for a0, a1 in itertools.combinations(dist_addr[:4], 2):
            keys.append(f"a2:{min(a0, a1)}_{max(a0, a1)}")
            
    return list(set(keys))

def clean(s):
    return " ".join(SPLIT_RE.split(s.lower())).strip() if s else ""

def get_tokens(s):
    return set(SPLIT_RE.split(s.lower())) - {""} if s else set()

def get_distinctive_addr_tokens(s):
    if not s:
        return set()
    return {t for t in SPLIT_RE.split(s.lower()) if len(t) >= 4 and t not in ADDR_STOPWORDS and not t.isdigit()}

def get_nums(s):
    return set(NUM_RE.findall(s.lower())) if s else set()

def score_candidate(s1_cn, s1_ca, s1_tn, s1_ta, s1_d_addr, s1_na,
                    c_cn, c_ca, c_tn, c_ta, c_d_addr, c_na):
    # Name similarities
    jw_name = distance.JaroWinkler.similarity(s1_cn, c_cn)
    
    # Token jaccard on name
    name_jaccard = len(s1_tn & c_tn) / max(1, len(s1_tn | c_tn)) if (s1_tn or c_tn) else 0.0
    
    # Address similarities
    if s1_ca and c_ca:
        jw_addr = distance.JaroWinkler.similarity(s1_ca, c_ca)
        addr_jaccard = len(s1_ta & c_ta) / max(1, len(s1_ta | c_ta)) if (s1_ta or c_ta) else 0.0
        num_overlap = 1.0 if (s1_na and c_na and not s1_na.isdisjoint(c_na)) else 0.0
        d_addr_overlap = 1.0 if (s1_d_addr and c_d_addr and not s1_d_addr.isdisjoint(c_d_addr)) else 0.0
    else:
        jw_addr = 0.0
        addr_jaccard = 0.0
        num_overlap = 0.0
        d_addr_overlap = 0.0
        
    # High composite score
    score = max(
        jw_name,
        0.7 * jw_name + 0.3 * name_jaccard,
        0.5 * jw_name + 0.3 * jw_addr + 0.2 * num_overlap,
        0.4 * jw_name + 0.4 * addr_jaccard + 0.2 * d_addr_overlap
    )
    return score

def create_or_load_heldout_split():
    if os.path.exists("heldout_s1.parquet") and os.path.exists("heldout_gt.parquet"):
        print("Using existing heldout validation split parquet files...")
        return
    
    print("Creating genuinely heldout validation split from train data (rows 1,500,000 - 1,510,000)...")
    gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", infer_schema_length=0)
    gt_val = gt.slice(1500000, 10000)
    
    s1_needed = set(gt_val["source1_entity_id"].to_list())
    targets_needed = set()
    for row in gt_val.iter_rows():
        if row[1]:
            targets_needed.update(row[1].split(","))
            
    print(f"Heldout split: {len(s1_needed)} S1 entities, {len(targets_needed)} true ground-truth targets.")
    
    s1_full = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", infer_schema_length=0)
    s1_val = s1_full.filter(pl.col("entity_id").is_in(list(s1_needed)))
    
    s2_full = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", infer_schema_length=0)
    s3_full = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", infer_schema_length=0)
    
    s2_targets = s2_full.filter(pl.col("entity_id").is_in(list(targets_needed)))
    s3_targets = s3_full.filter(pl.col("entity_id").is_in(list(targets_needed)))
    
    s2_noise = s2_full.slice(1500000, 200000)
    s3_noise = s3_full.slice(1500000, 200000)
    
    s2_val = pl.concat([s2_targets, s2_noise]).unique(subset=["entity_id"])
    s3_val = pl.concat([s3_targets, s3_noise]).unique(subset=["entity_id"])
    
    print(f"Target pool: {len(s2_val):,} S2 + {len(s3_val):,} S3 = {len(s2_val)+len(s3_val):,} total targets.")
    
    s1_val.write_parquet("heldout_s1.parquet")
    s2_val.write_parquet("heldout_s2.parquet")
    s3_val.write_parquet("heldout_s3.parquet")
    gt_val.write_parquet("heldout_gt.parquet")
    print("Heldout split created and saved successfully.")

def run_sweep():
    create_or_load_heldout_split()
    
    s1 = pl.read_parquet("heldout_s1.parquet")
    s2 = pl.read_parquet("heldout_s2.parquet")
    s3 = pl.read_parquet("heldout_s3.parquet")
    gt = pl.read_parquet("heldout_gt.parquet")
    
    gt_map = {}
    total_true_links = 0
    for row in gt.iter_rows(named=True):
        sid = row['source1_entity_id']
        m = row['matched_entity_ids']
        if m:
            mids = set(m.split(','))
            gt_map[sid] = mids
            total_true_links += len(mids)
        else:
            gt_map[sid] = set()
            
    print(f"Total S1 entities in validation: {len(s1):,}")
    print(f"Total S1 with >=1 true matches: {sum(1 for v in gt_map.values() if v):,}")
    print(f"Total ground truth link pairs: {total_true_links:,}")
    
    target_df = pl.concat([s2, s3])
    target_ids = target_df["entity_id"].to_list()
    raw_names = target_df["business_name"].to_list()
    raw_addrs = target_df["business_address"].to_list()
    
    print("Pre-processing target records...")
    target_c_names = [clean(n) for n in raw_names]
    target_c_addrs = [clean(a) for a in raw_addrs]
    target_t_names = [get_tokens(n) for n in raw_names]
    target_t_addrs = [get_tokens(a) for a in raw_addrs]
    target_d_addrs = [get_distinctive_addr_tokens(a) for a in raw_addrs]
    target_n_addrs = [get_nums(a) for a in raw_addrs]
    
    s1_ids = s1["entity_id"].to_list()
    s1_names = s1["business_name"].to_list()
    s1_addrs = s1["business_address"].to_list()
    
    print("Pre-processing S1 records...")
    s1_c_names = [clean(n) for n in s1_names]
    s1_c_addrs = [clean(a) for a in s1_addrs]
    s1_t_names = [get_tokens(n) for n in s1_names]
    s1_t_addrs = [get_tokens(a) for a in s1_addrs]
    s1_d_addrs = [get_distinctive_addr_tokens(a) for a in s1_addrs]
    s1_n_addrs = [get_nums(a) for a in s1_addrs]
    
    # Check max_bucket_size options
    for max_b in [150, 300, 500]:
        print(f"\n=======================================================")
        print(f"EVALUATION FOR max_bucket_size = {max_b}")
        print(f"=======================================================")
        index = defaultdict(list)
        for idx, (n, a) in enumerate(zip(raw_names, raw_addrs)):
            for k in get_keys(n, a):
                index[k].append(idx)
                
        print(f"Scoring candidates for {len(s1_ids):,} S1 queries...")
        t0 = time.time()
        
        query_candidates = []
        for i in range(len(s1_ids)):
            sid = s1_ids[i]
            keys = get_keys(s1_names[i], s1_addrs[i])
            bucket_cand_indices = set()
            for k in keys:
                bucket = index.get(k)
                if bucket and len(bucket) <= max_b:
                    bucket_cand_indices.update(bucket)
                    
            if not bucket_cand_indices:
                query_candidates.append([])
                continue
                
            scored_candidates = []
            s1_cn = s1_c_names[i]
            s1_ca = s1_c_addrs[i]
            s1_tn = s1_t_names[i]
            s1_ta = s1_t_addrs[i]
            s1_da = s1_d_addrs[i]
            s1_na = s1_n_addrs[i]
            
            for cidx in bucket_cand_indices:
                score = score_candidate(
                    s1_cn, s1_ca, s1_tn, s1_ta, s1_da, s1_na,
                    target_c_names[cidx], target_c_addrs[cidx],
                    target_t_names[cidx], target_t_addrs[cidx],
                    target_d_addrs[cidx], target_n_addrs[cidx]
                )
                tid = target_ids[cidx]
                scored_candidates.append((score, tid))
                
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            query_candidates.append(scored_candidates)
            
        elapsed = time.time() - t0
        print(f"Completed scoring in {elapsed:.2f}s ({len(s1_ids)/elapsed:.1f} S1/s)")
        
        print(f"\n--- SWEEP RESULTS TABLE (max_bucket_size = {max_b}) ---")
        print(f"{'K':<5} | {'θ (Theta)':<10} | {'Recall@K':<12} | {'Avg Cand/Ent':<14} | {'Max Cand':<10} | {'Est. File Size (1.73M S1)'}")
        print("-" * 80)
        
        for K in [10, 15, 20, 30]:
            for theta in [0.55, 0.65]:
                recalled_links = 0
                cand_counts = []
                sample_tsv_bytes = 0
                
                for i, scored in enumerate(query_candidates):
                    sid = s1_ids[i]
                    filtered_cand_ids = [tid for (score, tid) in scored if score >= theta][:K]
                    cand_counts.append(len(filtered_cand_ids))
                    
                    true_m = gt_map.get(sid, set())
                    if true_m:
                        hits = len(true_m.intersection(set(filtered_cand_ids)))
                        recalled_links += hits
                        
                    line = f"{sid}\t{','.join(filtered_cand_ids)}\n"
                    sample_tsv_bytes += len(line.encode('utf-8'))
                    
                recall = recalled_links / total_true_links if total_true_links > 0 else 0.0
                avg_cand = np.mean(cand_counts)
                max_cand = max(cand_counts) if cand_counts else 0
                
                est_full_size_bytes = (sample_tsv_bytes / len(s1_ids)) * 1732544
                est_full_size_mb = est_full_size_bytes / (1024 * 1024)
                
                print(f"{K:<5} | {theta:<10.2f} | {recall*100:<10.2f}% | {avg_cand:<14.2f} | {max_cand:<10} | ~{est_full_size_mb:.1f} MB")

if __name__ == "__main__":
    run_sweep()
