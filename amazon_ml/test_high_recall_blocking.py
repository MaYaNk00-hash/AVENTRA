import polars as pl
import re
import sys
import time
from collections import defaultdict
import itertools

sys.stdout.reconfigure(encoding='utf-8')

LEGAL_SUFFIXES = {
    'inc', 'incorporated', 'corp', 'corporation', 'llc', 'ltd', 'limited',
    'pvt', 'private', 'co', 'company', 'services', 'enterprises', 'associates',
    'group', 'center', 'centre', 'solutions', 'technologies', 'holdings', 'trust',
    'sarl', 'sas', 'sa', 'eurl', 'gmbh', 'llp', 'pllc', 'dba', 'fka',
    'formerly', 'c/o', 'care', 'smt', 'shri', 'sri', 'dr', 'mr', 'mrs',
    'trading', 'as', 'com', 'org', 'net', 'in', 'us', 'fr', 'web', 'online', 'intl', 'international'
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
    
    # 1. Full name compact
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
            
    # 5. Address-based blocking
    # (a) Address number + significant address token
    if addr_nums and clean_addr_tokens:
        for atok in clean_addr_tokens[:3]:
            for num in addr_nums[:2]:
                keys.append(f"an:{atok}_{num}")
                
    # (b) Address token pairs (any 2 distinctive address tokens of length >= 4)
    dist_addr = [t for t in clean_addr_tokens if len(t) >= 4]
    if len(dist_addr) >= 2:
        for a0, a1 in itertools.combinations(dist_addr[:4], 2):
            keys.append(f"a2:{min(a0, a1)}_{max(a0, a1)}")
            
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

t1 = time.time()
for sid, c, name, addr in zip(s1_ids, s1_countries, s1_names, s1_addrs):
    true_targets = gt_map[sid]
    candidates = set()
    for k in get_keys(name, addr):
        b = index.get((c, k))
        if b:
            # Skip excessively large common buckets (e.g. > 2500)
            if len(b) <= 2500:
                candidates.update(b)
            
    hit = true_targets.intersection(candidates)
    total_recalled += len(hit)
    cand_sizes.append(len(candidates))

print(f"Evaluated 5,000 S1 queries in {time.time()-t1:.2f}s")
print(f"Recall: {total_recalled}/{total_true} = {total_recalled/total_true*100:.2f}%")
print(f"Average candidates: {sum(cand_sizes)/len(cand_sizes):.1f}, Median: {sorted(cand_counts)[len(cand_counts)//2] if 'cand_counts' in locals() else sorted(cand_sizes)[len(cand_sizes)//2]}")
print(f"Max candidates: {max(cand_sizes)}")
