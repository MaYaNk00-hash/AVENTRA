import polars as pl
import re
import sys
import time
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

LEGAL_SUFFIXES = {
    'inc', 'incorporated', 'corp', 'corporation', 'llc', 'ltd', 'limited',
    'pvt', 'private', 'co', 'company', 'services', 'enterprises', 'associates',
    'group', 'center', 'centre', 'solutions', 'technologies', 'holdings', 'trust',
    'sarl', 'sas', 'sa', 'eurl', 'gmbh', 'llp', 'pllc'
}

COMMON_WORDS = {
    'and', 'the', 'of', 'in', 'at', 'on', 'for', 'to', 'a', 'an', 'by',
    'no', 'near', 'opp', 'opposite', 'behind', 'fl', 'floor', 'block', 'unit',
    'plot', 'road', 'rd', 'street', 'st', 'avenue', 'ave', 'lane', 'ln', 'dr', 'drive'
}

SPLIT_RE = re.compile(r'[^a-z0-9]+')
NUM_RE = re.compile(r'\b\d{2,6}\b')

def get_keys(name_str, addr_str):
    name_clean = name_str.lower() if name_str else ""
    raw_tokens = [t for t in SPLIT_RE.split(name_clean) if t]
    clean_tokens = [t for t in raw_tokens if len(t) > 1 and t not in LEGAL_SUFFIXES and t not in COMMON_WORDS]
    
    keys = []
    # 1. Full name compact
    compact = "".join(raw_tokens)
    if len(compact) >= 5:
        keys.append(f"full:{compact[:20]}")
        
    # 2. First 2 tokens sorted
    if len(clean_tokens) >= 2:
        t0, t1 = clean_tokens[0], clean_tokens[1]
        s0, s1 = min(t0, t1), max(t0, t1)
        keys.append(f"t2:{s0}_{s1}")
        keys.append(f"pfx2:{s0[:3]}_{s1[:3]}")
    elif len(clean_tokens) == 1:
        keys.append(f"t1:{clean_tokens[0]}")
        
    # 3. Any pair of tokens from the first 3 tokens
    if len(clean_tokens) >= 3:
        for i in range(len(clean_tokens[:3])):
            for j in range(i+1, len(clean_tokens[:3])):
                ta, tb = clean_tokens[i], clean_tokens[j]
                keys.append(f"pair:{min(ta, tb)}_{max(ta, tb)}")
                
    # 4. First significant token + first number in address
    if addr_str and clean_tokens:
        nums = NUM_RE.findall(addr_str)
        if nums:
            keys.append(f"tok_num:{clean_tokens[0]}_{nums[0]}")
            if len(nums) > 1:
                keys.append(f"tok_num:{clean_tokens[0]}_{nums[-1]}")
                
    # 5. First 6 chars of clean name
    if len(compact) >= 6:
        keys.append(f"c6:{compact[:6]}")
        
    return list(set(keys))

# Load evaluation data
s1 = pl.read_parquet("s1_eval_sample.parquet")
s2 = pl.read_parquet("s2_eval_sample.parquet")
s3 = pl.read_parquet("s3_eval_sample.parquet")
gt = pl.read_parquet("gt_eval_sample.parquet")

gt_map = {row['source1_entity_id']: set(row['matched_entity_ids'].split(',')) for row in gt.iter_rows(named=True)}

# Build index on S2 & S3
t0 = time.time()
index = defaultdict(list)
for df in [s2, s3]:
    c_list = df["country"].to_list()
    id_list = df["entity_id"].to_list()
    name_list = df["business_name"].to_list()
    addr_list = df["business_address"].to_list()
    for c, eid, name, addr in zip(c_list, id_list, name_list, addr_list):
        for k in get_keys(name, addr):
            index[(c, k)].append(eid)

print(f"Index built in {time.time()-t0:.2f}s with {len(index):,} buckets")

# Evaluate recall
s1_ids = s1["entity_id"].to_list()
s1_countries = s1["country"].to_list()
s1_names = s1["business_name"].to_list()
s1_addrs = s1["business_address"].to_list()

total_true = sum(len(v) for v in gt_map.values())
total_recalled = 0
cand_sizes = []
missed_examples = []

t1 = time.time()
for sid, c, name, addr in zip(s1_ids, s1_countries, s1_names, s1_addrs):
    true_targets = gt_map[sid]
    candidates = set()
    for k in get_keys(name, addr):
        b = index.get((c, k))
        if b and len(b) <= 2000:
            candidates.update(b)
            
    hit = true_targets.intersection(candidates)
    total_recalled += len(hit)
    cand_sizes.append(len(candidates))
    
    missed = true_targets - candidates
    if missed and len(missed_examples) < 10:
        missed_examples.append((sid, name, addr, missed))

print(f"Evaluated 5,000 S1 queries in {time.time()-t1:.2f}s")
print(f"Recall: {total_recalled}/{total_true} = {total_recalled/total_true*100:.2f}%")
print(f"Average candidates: {sum(cand_sizes)/len(cand_sizes):.1f}, Median: {sorted(cand_sizes)[len(cand_sizes)//2]}")
print(f"Max candidates: {max(cand_sizes)}")

