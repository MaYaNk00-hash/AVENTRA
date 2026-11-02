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
        
    score = max(
        jw_name,
        0.7 * jw_name + 0.3 * name_jaccard,
        0.5 * jw_name + 0.3 * jw_addr + 0.2 * num_overlap,
        0.4 * jw_name + 0.4 * addr_jaccard + 0.2 * d_addr_overlap
    )
    return score

def run_diagnostic():
    s1 = pl.read_parquet("heldout_s1.parquet")
    s2 = pl.read_parquet("heldout_s2.parquet")
    s3 = pl.read_parquet("heldout_s3.parquet")
    gt = pl.read_parquet("heldout_gt.parquet")
    
    target_df = pl.concat([s2, s3])
    
    # Create lookup map for targets
    target_records = {}
    for row in target_df.iter_rows(named=True):
        target_records[row['entity_id']] = {
            'business_name': row.get('business_name', '') or '',
            'business_address': row.get('business_address', '') or '',
            'country': row.get('country', '') or ''
        }
        
    s1_records = {}
    for row in s1.iter_rows(named=True):
        s1_records[row['entity_id']] = {
            'business_name': row.get('business_name', '') or '',
            'business_address': row.get('business_address', '') or '',
            'country': row.get('country', '') or ''
        }
        
    gt_pairs = []
    for row in gt.iter_rows(named=True):
        sid = row['source1_entity_id']
        m = row['matched_entity_ids']
        if m:
            for tid in m.split(','):
                gt_pairs.append((sid, tid))
                
    total_true_pairs = len(gt_pairs)
    print(f"Total true ground-truth pairs in validation: {total_true_pairs:,}")
    
    # Build inverted index (max_bucket_size = 150)
    target_ids = target_df["entity_id"].to_list()
    raw_names = target_df["business_name"].to_list()
    raw_addrs = target_df["business_address"].to_list()
    
    target_c_names = [clean(n) for n in raw_names]
    target_c_addrs = [clean(a) for a in raw_addrs]
    target_t_names = [get_tokens(n) for n in raw_names]
    target_t_addrs = [get_tokens(a) for a in raw_addrs]
    target_d_addrs = [get_distinctive_addr_tokens(a) for a in raw_addrs]
    target_n_addrs = [get_nums(a) for a in raw_addrs]
    
    index = defaultdict(list)
    for idx, (n, a) in enumerate(zip(raw_names, raw_addrs)):
        for k in get_keys(n, a):
            index[k].append(idx)
            
    # Also keep full index for key overlap check
    full_target_keys = {}
    for tid, rec in target_records.items():
        full_target_keys[tid] = set(get_keys(rec['business_name'], rec['business_address']))
        
    # Perform candidate generation at K=30, theta=0.55, max_bucket_size=150
    s1_ids = s1["entity_id"].to_list()
    s1_names = s1["business_name"].to_list()
    s1_addrs = s1["business_address"].to_list()
    
    s1_c_names = [clean(n) for n in s1_names]
    s1_c_addrs = [clean(a) for a in s1_addrs]
    s1_t_names = [get_tokens(n) for n in s1_names]
    s1_t_addrs = [get_tokens(a) for a in s1_addrs]
    s1_d_addrs = [get_distinctive_addr_tokens(a) for a in s1_addrs]
    s1_n_addrs = [get_nums(a) for a in s1_addrs]
    
    s1_id_to_idx = {sid: idx for idx, sid in enumerate(s1_ids)}
    
    recovered_pairs = set()
    s1_candidates_map = {}
    
    for i in range(len(s1_ids)):
        sid = s1_ids[i]
        keys = get_keys(s1_names[i], s1_addrs[i])
        bucket_cand_indices = set()
        for k in keys:
            bucket = index.get(k)
            if bucket and len(bucket) <= 150:
                bucket_cand_indices.update(bucket)
                
        scored = []
        for cidx in bucket_cand_indices:
            score = score_candidate(
                s1_c_names[i], s1_c_addrs[i], s1_t_names[i], s1_t_addrs[i], s1_d_addrs[i], s1_n_addrs[i],
                target_c_names[cidx], target_c_addrs[cidx],
                target_t_names[cidx], target_t_addrs[cidx],
                target_d_addrs[cidx], target_n_addrs[cidx]
            )
            tid = target_ids[cidx]
            scored.append((score, tid))
            
        scored.sort(key=lambda x: x[0], reverse=True)
        s1_candidates_map[sid] = scored
        
        top30 = [tid for (score, tid) in scored if score >= 0.55][:30]
        for tid in top30:
            recovered_pairs.add((sid, tid))
            
    missed_pairs = [p for p in gt_pairs if p not in recovered_pairs]
    print(f"Total missed pairs: {len(missed_pairs):,} / {total_true_pairs:,} ({len(missed_pairs)/total_true_pairs*100:.2f}%)")
    
    # Categorize misses
    zero_key_overlap = []
    bucket_overflow_only = []
    in_bucket_but_low_score = []
    in_bucket_but_pruned_rank = []
    
    for sid, tid in missed_pairs:
        s1_rec = s1_records.get(sid, {})
        t_rec = target_records.get(tid, {})
        
        s1_keys = set(get_keys(s1_rec.get('business_name', ''), s1_rec.get('business_address', '')))
        t_keys = full_target_keys.get(tid, set())
        
        shared_keys = s1_keys & t_keys
        
        if not shared_keys:
            zero_key_overlap.append((sid, tid, s1_rec, t_rec, s1_keys, t_keys))
        else:
            # Check if any shared key was indexed with <= 150 bucket size
            accessible_keys = [k for k in shared_keys if k in index and len(index[k]) <= 150]
            if not accessible_keys:
                bucket_overflow_only.append((sid, tid, s1_rec, t_rec, shared_keys, [len(index[k]) for k in shared_keys]))
            else:
                # Target WAS in the raw candidate pool for this S1! Find its score and rank
                scored_list = s1_candidates_map.get(sid, [])
                # Find where tid is in scored_list
                tid_score = None
                tid_rank = None
                for rank, (score, cand_id) in enumerate(scored_list, start=1):
                    if cand_id == tid:
                        tid_score = score
                        tid_rank = rank
                        break
                        
                if tid_score is not None:
                    if tid_score < 0.55:
                        in_bucket_but_low_score.append((sid, tid, s1_rec, t_rec, tid_score, tid_rank, len(scored_list)))
                    else:
                        in_bucket_but_pruned_rank.append((sid, tid, s1_rec, t_rec, tid_score, tid_rank, len(scored_list)))
                        
    print("\n=======================================================")
    print("MISSED MATCHES ROOT-CAUSE BREAKDOWN")
    print("=======================================================")
    print(f"Total Ground-Truth Match Pairs:    {total_true_pairs:,}")
    print(f"Recovered at K=30, θ=0.55:         {len(recovered_pairs):,} ({len(recovered_pairs)/total_true_pairs*100:.2f}%)")
    print(f"Total Missed Pairs:                {len(missed_pairs):,} ({len(missed_pairs)/total_true_pairs*100:.2f}%)\n")
    
    print(f"1. Zero Blocking Key Overlap:       {len(zero_key_overlap):,} ({len(zero_key_overlap)/len(missed_pairs)*100:.2f}% of misses, {len(zero_key_overlap)/total_true_pairs*100:.2f}% of total GT)")
    print(f"2. Shared Keys in Overflow Buckets: {len(bucket_overflow_only):,} ({len(bucket_overflow_only)/len(missed_pairs)*100:.2f}% of misses, {len(bucket_overflow_only)/total_true_pairs*100:.2f}% of total GT)")
    print(f"3. In Candidate Pool, Score < 0.55: {len(in_bucket_but_low_score):,} ({len(in_bucket_but_low_score)/len(missed_pairs)*100:.2f}% of misses, {len(in_bucket_but_low_score)/total_true_pairs*100:.2f}% of total GT)")
    print(f"4. In Candidate Pool, Rank > 30:    {len(in_bucket_but_pruned_rank):,} ({len(in_bucket_but_pruned_rank)/len(missed_pairs)*100:.2f}% of misses, {len(in_bucket_but_pruned_rank)/total_true_pairs*100:.2f}% of total GT)")
    
    # Print examples for Zero Key Overlap
    print("\n=======================================================")
    print("EXAMPLES: ZERO KEY OVERLAP (Structurally Invisible to Blocking)")
    print("=======================================================")
    for idx, (sid, tid, s1_rec, t_rec, s1_k, t_k) in enumerate(zero_key_overlap[:15], 1):
        print(f"\nExample {idx}:")
        print(f"  [S1: {sid} ({s1_rec.get('country')})]")
        print(f"    Name:    '{s1_rec.get('business_name')}'")
        print(f"    Address: '{s1_rec.get('business_address')}'")
        print(f"    S1 Keys: {sorted(list(s1_k))[:4]}")
        print(f"  [Target: {tid} ({t_rec.get('country')})]")
        print(f"    Name:    '{t_rec.get('business_name')}'")
        print(f"    Address: '{t_rec.get('business_address')}'")
        print(f"    T Keys:  {sorted(list(t_k))[:4]}")
        
    # Print examples for Key Overlap Exists but Not Recovered
    print("\n=======================================================")
    print("EXAMPLES: KEY OVERLAP EXISTS BUT NOT RECOVERED")
    print("=======================================================")
    all_in_pool = in_bucket_but_low_score + in_bucket_but_pruned_rank
    for idx, (sid, tid, s1_rec, t_rec, score, rank, total_cand) in enumerate(all_in_pool[:12], 1):
        status = "Score < 0.55" if score < 0.55 else f"Rank #{rank} > 30"
        print(f"\nExample {idx} [{status} | Score: {score:.3f} | Rank: {rank}/{total_cand}]:")
        print(f"  [S1: {sid} ({s1_rec.get('country')})]")
        print(f"    Name:    '{s1_rec.get('business_name')}'")
        print(f"    Address: '{s1_rec.get('business_address')}'")
        print(f"  [Target: {tid} ({t_rec.get('country')})]")
        print(f"    Name:    '{t_rec.get('business_name')}'")
        print(f"    Address: '{t_rec.get('business_address')}'")

if __name__ == "__main__":
    run_diagnostic()
