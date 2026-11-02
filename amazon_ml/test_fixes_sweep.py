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

def get_normalized_nums(addr_clean):
    if not addr_clean:
        return []
    raw_nums = NUM_RE.findall(addr_clean)
    # Strip leading zeros so "020" -> "20", "004" -> "4"
    norm_nums = [n.lstrip('0') or '0' for n in raw_nums]
    return list(dict.fromkeys(norm_nums))

def get_keys_v2(name_str, addr_str):
    """
    Enhanced blocking key generator:
    - Normalizes numeric tokens (strips leading zeros)
    - Prioritizes head AND tail (city/locality) address tokens
    """
    name_clean = name_str.lower() if name_str else ""
    raw_name_tokens = [t for t in SPLIT_RE.split(name_clean) if t]
    clean_name_tokens = [t for t in raw_name_tokens if len(t) > 1 and t not in LEGAL_SUFFIXES]
    
    addr_clean = addr_str.lower() if addr_str else ""
    raw_addr_tokens = [t for t in SPLIT_RE.split(addr_clean) if t]
    clean_addr_tokens = [t for t in raw_addr_tokens if len(t) > 2 and t not in ADDR_STOPWORDS and not t.isdigit()]
    
    # FIX 1: Normalized numbers (strip leading zeros)
    addr_nums = get_normalized_nums(addr_clean)
    
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
        
    # 4. First name token + normalized address number
    if clean_name_tokens and addr_nums:
        keys.append(f"tn:{clean_name_tokens[0]}_{addr_nums[0]}")
        if len(addr_nums) > 1:
            keys.append(f"tn:{clean_name_tokens[0]}_{addr_nums[-1]}")
            
    # FIX 1: Prioritize Head tokens + Tail tokens (city/state) for address combinations
    dist_addr = [t for t in clean_addr_tokens if len(t) >= 4]
    if dist_addr:
        head_tokens = dist_addr[:3]
        tail_tokens = dist_addr[-2:]
        selected_addr_tokens = list(dict.fromkeys(head_tokens + tail_tokens))
    else:
        selected_addr_tokens = []
        
    # 5. Address-based blocking keys with normalized numbers
    if addr_nums and selected_addr_tokens:
        for atok in selected_addr_tokens[:4]:
            for num in addr_nums[:2]:
                keys.append(f"an:{atok}_{num}")
                
    # 6. Address token pairs (cross head & tail tokens)
    if len(selected_addr_tokens) >= 2:
        for a0, a1 in itertools.combinations(selected_addr_tokens[:5], 2):
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
    if not s:
        return set()
    raw = NUM_RE.findall(s.lower())
    return {n.lstrip('0') or '0' for n in raw}

def score_candidate_v2(s1_cn, s1_ca, s1_tn, s1_ta, s1_d_addr, s1_na,
                       c_cn, c_ca, c_tn, c_ta, c_d_addr, c_na,
                       use_address_boost=True):
    """
    Composite candidate scorer with FIX 2 (Conditional Address Boost).
    """
    jw_name = distance.JaroWinkler.similarity(s1_cn, c_cn)
    name_jaccard = len(s1_tn & c_tn) / max(1, len(s1_tn | c_tn)) if (s1_tn or c_tn) else 0.0
    
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
        
    base_score = max(
        jw_name,
        0.7 * jw_name + 0.3 * name_jaccard,
        0.5 * jw_name + 0.3 * jw_addr + 0.2 * num_overlap,
        0.4 * jw_name + 0.4 * addr_jaccard + 0.2 * d_addr_overlap
    )
    
    # FIX 2: Conditional Address-Boosted Scoring (Strict Precision Guard)
    if use_address_boost and s1_ca and c_ca:
        if jw_addr >= 0.90 and addr_jaccard >= 0.85:
            boosted_score = 0.5 * jw_addr + 0.5 * addr_jaccard
            base_score = max(base_score, boosted_score)
            
    return base_score

def run_evaluation():
    print("Loading heldout validation split (10,000 S1 queries, 433k targets)...")
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
            
    target_df = pl.concat([s2, s3])
    target_ids = target_df["entity_id"].to_list()
    raw_names = target_df["business_name"].to_list()
    raw_addrs = target_df["business_address"].to_list()
    
    target_c_names = [clean(n) for n in raw_names]
    target_c_addrs = [clean(a) for a in raw_addrs]
    target_t_names = [get_tokens(n) for n in raw_names]
    target_t_addrs = [get_tokens(a) for a in raw_addrs]
    target_d_addrs = [get_distinctive_addr_tokens(a) for a in raw_addrs]
    target_n_addrs = [get_nums(a) for a in raw_addrs]
    
    s1_ids = s1["entity_id"].to_list()
    s1_names = s1["business_name"].to_list()
    s1_addrs = s1["business_address"].to_list()
    
    s1_c_names = [clean(n) for n in s1_names]
    s1_c_addrs = [clean(a) for a in s1_addrs]
    s1_t_names = [get_tokens(n) for n in s1_names]
    s1_t_addrs = [get_tokens(a) for a in s1_addrs]
    s1_d_addrs = [get_distinctive_addr_tokens(a) for a in s1_addrs]
    s1_n_addrs = [get_nums(a) for a in s1_addrs]
    
    print("Building updated inverted index (with Fix 1 address tail keys & norm numbers)...")
    index = defaultdict(list)
    for idx, (n, a) in enumerate(zip(raw_names, raw_addrs)):
        for k in get_keys_v2(n, a):
            index[k].append(idx)
            
    print("Scoring candidates for 10,000 S1 queries (with Fix 2 conditional address boost)...")
    t0 = time.time()
    query_candidates = []
    
    for i in range(len(s1_ids)):
        keys = get_keys_v2(s1_names[i], s1_addrs[i])
        bucket_cand_indices = set()
        for k in keys:
            bucket = index.get(k)
            if bucket and len(bucket) <= 150:
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
            score = score_candidate_v2(
                s1_cn, s1_ca, s1_tn, s1_ta, s1_da, s1_na,
                target_c_names[cidx], target_c_addrs[cidx],
                target_t_names[cidx], target_t_addrs[cidx],
                target_d_addrs[cidx], target_n_addrs[cidx],
                use_address_boost=True
            )
            tid = target_ids[cidx]
            scored_candidates.append((score, tid))
            
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        query_candidates.append(scored_candidates)
        
    elapsed = time.time() - t0
    print(f"Scored in {elapsed:.2f}s ({len(s1_ids)/elapsed:.1f} S1/s)")
    
    print("\n=======================================================")
    print("UPDATED SWEEP RESULTS TABLE (AFTER FIX 1 & FIX 2, max_bucket_size = 150)")
    print("=======================================================")
    print(f"{'K':<5} | {'θ (Theta)':<10} | {'Recall@K':<12} | {'Avg Cand/Ent':<14} | {'Max Cand':<10} | {'Est. File Size (1.73M S1)'}")
    print("-" * 80)
    
    sweep_data = {}
    for K in [15, 20, 30]:
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
            
            sweep_data[(K, theta)] = (recall, avg_cand, max_cand, est_full_size_mb)
            print(f"{K:<5} | {theta:<10.2f} | {recall*100:<10.2f}% | {avg_cand:<14.2f} | {max_cand:<10} | ~{est_full_size_mb:.1f} MB")
            
    # --- PRECISION SPOT CHECK ---
    print("\n=======================================================")
    print("PRECISION SPOT-CHECK: SHARED-ADDRESS DIFFERENT S1 ENTITIES")
    print("=======================================================")
    
    # Find S1 entities that share near-identical addresses (e.g. jw_addr >= 0.90) but have different true matches or different names
    s1_addr_clusters = defaultdict(list)
    for i, a in enumerate(s1_c_addrs):
        if len(a) >= 15:
            # Hash first 20 chars of clean address
            key = a[:20]
            s1_addr_clusters[key].append(i)
            
    spot_check_cases = []
    for key, indices in s1_addr_clusters.items():
        if len(indices) >= 2:
            for idx1, idx2 in itertools.combinations(indices[:4], 2):
                ca1, ca2 = s1_c_addrs[idx1], s1_c_addrs[idx2]
                cn1, cn2 = s1_c_names[idx1], s1_c_names[idx2]
                
                # Different entities (low name similarity) but sharing same building/address
                if distance.JaroWinkler.similarity(cn1, cn2) < 0.60:
                    jw_a = distance.JaroWinkler.similarity(ca1, ca2)
                    if jw_a >= 0.90:
                        sid1, sid2 = s1_ids[idx1], s1_ids[idx2]
                        m1 = gt_map.get(sid1, set())
                        m2 = gt_map.get(sid2, set())
                        if m1 != m2: # distinct true targets
                            spot_check_cases.append((idx1, idx2, sid1, sid2, cn1, cn2, ca1, ca2, m1, m2))
                            
    print(f"Identified {len(spot_check_cases)} shared-address multi-business entity pairs in validation slice.")
    
    # Check if address-boost caused false crossover candidates with high score
    crossovers_found = 0
    crossover_examples = []
    
    for idx1, idx2, sid1, sid2, cn1, cn2, ca1, ca2, m1, m2 in spot_check_cases:
        # Check candidates for S1_1
        cands1 = query_candidates[idx1]
        for score, tid in cands1:
            # If tid belongs to m2 (the other business), check its score
            if m2 and tid in m2:
                crossovers_found += 1
                crossover_examples.append((sid1, sid2, tid, cn1, cn2, score))
                
    print(f"Cross-business false candidate crossovers with score >= 0.55: {crossovers_found}")
    if crossover_examples:
        for ex in crossover_examples[:5]:
            print(f"  Warning: S1 '{ex[3]}' pulled target {ex[2]} of S1 '{ex[4]}' with score {ex[5]:.3f}")
    else:
        print("  ✓ PASS: Zero false cross-business candidate promotions detected under strict guard (JW>=0.90 & Jaccard>=0.85).")

if __name__ == "__main__":
    run_evaluation()
