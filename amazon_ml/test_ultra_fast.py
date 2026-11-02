import polars as pl
import numpy as np
import pickle
import time
import sys
import os
from collections import defaultdict
from rapidfuzz import distance, fuzz
import re

sys.path.insert(0, os.path.abspath("code/business_entity_resolution/src"))
import blocking
import metric

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
    return set(NUM_RE.findall(s.lower())) if s else set()

def extract_pair_features(s1_cn, s1_ca, s1_tn, s1_ta, s1_na,
                          c_cn, c_ca, c_tn, c_ta, c_na, is_s2):
    name_ratio = fuzz.ratio(s1_cn, c_cn) / 100.0
    name_tsort = fuzz.token_sort_ratio(s1_cn, c_cn) / 100.0
    name_tset = fuzz.token_set_ratio(s1_cn, c_cn) / 100.0
    name_jw = distance.JaroWinkler.similarity(s1_cn, c_cn)
    
    name_jaccard = len(s1_tn & c_tn) / max(1, len(s1_tn | c_tn))
    name_len_diff = abs(len(s1_cn) - len(c_cn)) / max(1, max(len(s1_cn), len(c_cn)))
    
    addr_null = 1.0 if not c_ca or not s1_ca else 0.0
    if addr_null:
        addr_tsort = 0.5
        addr_tset = 0.5
        addr_jw = 0.5
        addr_jaccard = 0.5
        num_match = 0.5
    else:
        addr_tsort = fuzz.token_sort_ratio(s1_ca, c_ca) / 100.0
        addr_tset = fuzz.token_set_ratio(s1_ca, c_ca) / 100.0
        addr_jw = distance.JaroWinkler.similarity(s1_ca, c_ca)
        addr_jaccard = len(s1_ta & c_ta) / max(1, len(s1_ta | c_ta))
        
        if s1_na and c_na:
            num_match = len(s1_na & c_na) / max(1, len(s1_na | c_na))
        elif not s1_na and not c_na:
            num_match = 0.5
        else:
            num_match = 0.0
            
    tot_s1 = s1_tn | s1_ta
    tot_c = c_tn | c_ta
    total_jaccard = len(tot_s1 & tot_c) / max(1, len(tot_s1 | tot_c))
    
    return [
        name_ratio, name_tsort, name_tset, name_jw, name_jaccard, name_len_diff,
        addr_null, addr_tsort, addr_tset, addr_jw, addr_jaccard, num_match,
        1.0 if is_s2 else 0.0, total_jaccard,
        name_tset * addr_tset,
        name_jw * addr_jw
    ]

def test_ultra_fast():
    s1 = pl.read_parquet("s1_eval_sample.parquet")
    s2 = pl.read_parquet("s2_eval_sample.parquet")
    s3 = pl.read_parquet("s3_eval_sample.parquet")
    gt = pl.read_parquet("gt_eval_sample.parquet")
    
    gt_map = {row['source1_entity_id']: set(row['matched_entity_ids'].split(',')) for row in gt.iter_rows(named=True)}
    
    with open("models/matching_lgb_model.pkl", "rb") as f:
        model = pickle.load(f)
        
    target_df = pl.concat([s2, s3])
    target_ids = target_df["entity_id"].to_list()
    raw_names = target_df["business_name"].to_list()
    raw_addrs = target_df["business_address"].to_list()
    
    target_c_names = [clean(n) for n in raw_names]
    target_c_addrs = [clean(a) for a in raw_addrs]
    target_t_names = [get_tokens(n) for n in raw_names]
    target_t_addrs = [get_tokens(a) for a in raw_addrs]
    target_dist_addrs = [get_distinctive_addr_tokens(a) for a in raw_addrs]
    target_n_addrs = [get_nums(a) for a in raw_addrs]
    target_is_s2 = [eid.startswith("S2-") for eid in target_ids]
    
    index = defaultdict(list)
    for idx, (n, a) in enumerate(zip(raw_names, raw_addrs)):
        for k in blocking.get_keys(n, a):
            index[k].append(idx)
            
    s1_ids = s1["entity_id"].to_list()
    s1_names = s1["business_name"].to_list()
    s1_addrs = s1["business_address"].to_list()
    
    print(f"Benchmarking Ultra-Fast pipeline on {len(s1_ids):,} entities...")
    t0 = time.time()
    
    pair_s1_indices = []
    pair_cand_indices = []
    pair_features = []
    cand_strings = []
    
    for s1_idx, (sid, name, addr) in enumerate(zip(s1_ids, s1_names, s1_addrs)):
        s1_cn = clean(name)
        s1_ca = clean(addr)
        s1_tn = get_tokens(name)
        s1_ta = get_tokens(addr)
        s1_d_addr = get_distinctive_addr_tokens(addr)
        s1_na = get_nums(addr)
        
        keys = blocking.get_keys(name, addr)
        candidates = set()
        for k in keys:
            bucket = index.get(k)
            if bucket and len(bucket) <= 2500:
                candidates.update(bucket)
                
        cand_indices = sorted(list(candidates))
        if not cand_indices:
            cand_strings.append("")
            continue
            
        cand_strings.append(",".join(target_ids[cidx] for cidx in cand_indices))
        
        for cidx in cand_indices:
            c_cn = target_c_names[cidx]
            jw = distance.JaroWinkler.similarity(s1_cn, c_cn)
            
            # Fast filter: High JW OR high token overlap OR shared distinctive address token
            name_match = (jw >= 0.55) or (s1_tn and len(s1_tn & target_t_names[cidx]) >= 2)
            addr_match = bool(s1_d_addr and not s1_d_addr.isdisjoint(target_dist_addrs[cidx]))
            
            if name_match or addr_match:
                pair_s1_indices.append(s1_idx)
                pair_cand_indices.append(cidx)
                pair_features.append(extract_pair_features(
                    s1_cn, s1_ca, s1_tn, s1_ta, s1_na,
                    c_cn, target_c_addrs[cidx], target_t_names[cidx], target_t_addrs[cidx], target_n_addrs[cidx], target_is_s2[cidx]
                ))
                
    t_feat = time.time() - t0
    print(f"Total Candidate Pairs Filtered: {len(pair_features):,} in {t_feat:.2f}s!")
    
    if pair_features:
        np_feats = np.array(pair_features, dtype=np.float32)
        probs = model.predict_proba(np_feats)[:, 1]
    else:
        probs = []
        
    s1_matches = [[] for _ in range(len(s1_ids))]
    for s1_idx, cidx, p in zip(pair_s1_indices, pair_cand_indices, probs):
        if p >= 0.65:
            s1_matches[s1_idx].append(target_ids[cidx])
            
    all_matches = {s1_ids[i]: set(s1_matches[i]) for i in range(len(s1_ids))}
    f05 = metric.compute_macro_f05(gt_map, all_matches)
    
    total_elapsed = time.time() - t0
    print(f"Total time for 5,000 queries: {total_elapsed:.2f}s ({len(s1_ids)/total_elapsed:.1f} queries/sec)!")
    print(f"Validation Macro F_0.5 Score: {f05:.4f}")

if __name__ == "__main__":
    test_ultra_fast()
