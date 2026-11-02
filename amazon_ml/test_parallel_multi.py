import polars as pl
import numpy as np
import pickle
import time
import sys
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from rapidfuzz import distance, fuzz
import re

sys.path.insert(0, os.path.abspath("code/business_entity_resolution/src"))
import blocking
import features
import metric

sys.stdout.reconfigure(encoding='utf-8')

SPLIT_RE = re.compile(r'[^a-z0-9]+')
NUM_RE = re.compile(r'\b\d{1,6}\b')

def clean(s):
    return " ".join(SPLIT_RE.split(s.lower())).strip() if s else ""

def get_tokens(s):
    return set(SPLIT_RE.split(s.lower())) - {""} if s else set()

def get_nums(s):
    return set(NUM_RE.findall(s.lower())) if s else set()

# Worker global variables
W_TARGET_IDS = None
W_TARGET_C_NAMES = None
W_TARGET_C_ADDRS = None
W_TARGET_T_NAMES = None
W_TARGET_T_ADDRS = None
W_TARGET_N_ADDRS = None
W_TARGET_IS_S2 = None
W_INDEX = None
W_MODEL = None

def init_worker_state(target_ids, c_names, c_addrs, t_names, t_addrs, n_addrs, is_s2, index_dict, model_path):
    global W_TARGET_IDS, W_TARGET_C_NAMES, W_TARGET_C_ADDRS, W_TARGET_T_NAMES, W_TARGET_T_ADDRS, W_TARGET_N_ADDRS, W_TARGET_IS_S2, W_INDEX, W_MODEL
    W_TARGET_IDS = target_ids
    W_TARGET_C_NAMES = c_names
    W_TARGET_C_ADDRS = c_addrs
    W_TARGET_T_NAMES = t_names
    W_TARGET_T_ADDRS = t_addrs
    W_TARGET_N_ADDRS = n_addrs
    W_TARGET_IS_S2 = is_s2
    W_INDEX = index_dict
    with open(model_path, "rb") as f:
        W_MODEL = pickle.load(f)

def process_s1_chunk(s1_tuples):
    """
    Process a chunk of (sid, name, addr) tuples.
    """
    cand_lines = []
    match_lines = []
    
    pair_s1_indices = []
    pair_cand_indices = []
    pair_features = []
    
    for local_idx, (sid, name, addr) in enumerate(s1_tuples):
        s1_cn = clean(name)
        s1_ca = clean(addr)
        s1_tn = get_tokens(name)
        s1_ta = get_tokens(addr)
        s1_na = get_nums(addr)
        
        keys = blocking.get_keys(name, addr)
        candidates = set()
        for k in keys:
            bucket = W_INDEX.get(k)
            if bucket and len(bucket) <= 2500:
                candidates.update(bucket)
                
        cand_indices = sorted(list(candidates))
        if not cand_indices:
            cand_lines.append(f"{sid}\t\n")
            match_lines.append(f"{sid}\t\n")
            continue
            
        cand_ids = [W_TARGET_IDS[cidx] for cidx in cand_indices]
        cand_lines.append(f"{sid}\t{','.join(cand_ids)}\n")
        
        for cidx in cand_indices:
            c_cn = W_TARGET_C_NAMES[cidx]
            c_ta = W_TARGET_T_ADDRS[cidx]
            c_tn = W_TARGET_T_NAMES[cidx]
            
            jw = distance.JaroWinkler.similarity(s1_cn, c_cn)
            addr_match = bool(s1_ta and any(len(t) >= 4 and t in c_ta for t in s1_ta))
            name_match = jw >= 0.60 or (s1_tn and len(s1_tn & c_tn) >= 2)
            
            if name_match or addr_match:
                pair_s1_indices.append(local_idx)
                pair_cand_indices.append(cidx)
                
                # Compute features
                name_ratio = fuzz.ratio(s1_cn, c_cn) / 100.0
                name_tsort = fuzz.token_sort_ratio(s1_cn, c_cn) / 100.0
                name_tset = fuzz.token_set_ratio(s1_cn, c_cn) / 100.0
                name_jaccard = len(s1_tn & c_tn) / max(1, len(s1_tn | c_tn))
                name_len_diff = abs(len(s1_cn) - len(c_cn)) / max(1, max(len(s1_cn), len(c_cn)))
                
                c_ca = W_TARGET_C_ADDRS[cidx]
                if not c_ca or not s1_ca:
                    addr_null, addr_tsort, addr_tset, addr_jw, addr_jaccard, num_match = 1.0, 0.5, 0.5, 0.5, 0.5, 0.5
                else:
                    addr_null = 0.0
                    addr_tsort = fuzz.token_sort_ratio(s1_ca, c_ca) / 100.0
                    addr_tset = fuzz.token_set_ratio(s1_ca, c_ca) / 100.0
                    addr_jw = distance.JaroWinkler.similarity(s1_ca, c_ca)
                    addr_jaccard = len(s1_ta & c_ta) / max(1, len(s1_ta | c_ta))
                    c_na = W_TARGET_N_ADDRS[cidx]
                    num_match = len(s1_na & c_na) / max(1, len(s1_na | c_na)) if s1_na and c_na else (0.5 if not s1_na and not c_na else 0.0)
                    
                tot_s1 = s1_tn | s1_ta
                tot_c = c_tn | c_ta
                total_jaccard = len(tot_s1 & tot_c) / max(1, len(tot_s1 | tot_c))
                
                pair_features.append([
                    name_ratio, name_tsort, name_tset, jw, name_jaccard, name_len_diff,
                    addr_null, addr_tsort, addr_tset, addr_jw, addr_jaccard, num_match,
                    1.0 if W_TARGET_IS_S2[cidx] else 0.0, total_jaccard,
                    name_tset * addr_tset,
                    jw * addr_jw
                ])
                
    if pair_features:
        np_feats = np.array(pair_features, dtype=np.float32)
        probs = W_MODEL.predict_proba(np_feats)[:, 1]
    else:
        probs = []
        
    s1_matches = [[] for _ in range(len(s1_tuples))]
    for s1_idx, cidx, p in zip(pair_s1_indices, pair_cand_indices, probs):
        if p >= 0.65:
            s1_matches[s1_idx].append(W_TARGET_IDS[cidx])
            
    for local_idx, (sid, _, _) in enumerate(s1_tuples):
        if len(cand_lines) <= local_idx or not cand_lines[local_idx].strip():
            continue
        m_list = s1_matches[local_idx]
        if m_list:
            match_lines.append(f"{sid}\t{','.join(m_list)}\n")
        else:
            match_lines.append(f"{sid}\t\n")
            
    return match_lines, cand_lines

if __name__ == "__main__":
    print("Testing multi-core parallel execution on benchmark...")
    s1 = pl.read_parquet("s1_eval_sample.parquet")
    s2 = pl.read_parquet("s2_eval_sample.parquet")
    s3 = pl.read_parquet("s3_eval_sample.parquet")
    
    target_df = pl.concat([s2, s3])
    target_ids = target_df["entity_id"].to_list()
    raw_names = target_df["business_name"].to_list()
    raw_addrs = target_df["business_address"].to_list()
    
    target_c_names = [clean(n) for n in raw_names]
    target_c_addrs = [clean(a) for a in raw_addrs]
    target_t_names = [get_tokens(n) for n in raw_names]
    target_t_addrs = [get_tokens(a) for a in raw_addrs]
    target_n_addrs = [get_nums(a) for a in raw_addrs]
    target_is_s2 = [eid.startswith("S2-") for eid in target_ids]
    
    index = defaultdict(list)
    for idx, (n, a) in enumerate(zip(raw_names, raw_addrs)):
        for k in blocking.get_keys(n, a):
            index[k].append(idx)
            
    s1_tuples = list(zip(s1["entity_id"].to_list(), s1["business_name"].to_list(), s1["business_address"].to_list()))
    
    # Split into chunks of 1,000 queries
    chunk_size = 1000
    chunks = [s1_tuples[i:i+chunk_size] for i in range(0, len(s1_tuples), chunk_size)]
    
    t0 = time.time()
    with ProcessPoolExecutor(
        max_workers=6,
        initializer=init_worker_state,
        initargs=(target_ids, target_c_names, target_c_addrs, target_t_names, target_t_addrs, target_n_addrs, target_is_s2, dict(index), "models/matching_lgb_model.pkl")
    ) as executor:
        results = list(executor.map(process_s1_chunk, chunks))
        
    elapsed = time.time() - t0
    print(f"Processed 5,000 queries across 6 workers in {elapsed:.2f}s ({len(s1_tuples)/elapsed:.1f} queries/sec)!")
