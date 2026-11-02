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
    'sarl', 'sas', 'sa', 'eurl', 'gmbh'
}

COMMON_STOPWORDS = {
    'and', 'the', 'of', 'in', 'at', 'on', 'for', 'to', 'a', 'an', 'by',
    'no', 'near', 'opp', 'opposite', 'behind', 'fl', 'floor', 'block', 'unit',
    'plot', 'road', 'rd', 'street', 'st', 'avenue', 'ave', 'lane', 'ln', 'dr', 'drive'
}

SPLIT_RE = re.compile(r'[^a-z0-9]+')
NUM_RE = re.compile(r'\b\d{2,6}\b')

def get_keys_for_record(name_str, addr_str):
    name_clean = name_str.lower() if name_str else ""
    raw_tokens = SPLIT_RE.split(name_clean)
    tokens = [t for t in raw_tokens if len(t) > 1 and t not in LEGAL_SUFFIXES and t not in COMMON_STOPWORDS]
    
    keys = []
    # 1. Exact alphanumeric name
    compact_name = "".join(t for t in raw_tokens if t)
    if len(compact_name) >= 5:
        keys.append(f"n_full:{compact_name[:20]}")
        
    # 2. First 2 tokens sorted
    if len(tokens) >= 2:
        t0, t1 = tokens[0], tokens[1]
        keys.append(f"n2:{min(t0, t1)}_{max(t0, t1)}")
        keys.append(f"pfx:{t0[:4]}_{t1[:4]}")
    elif len(tokens) == 1:
        keys.append(f"n1:{tokens[0]}")
        
    # 3. First 3 tokens sorted
    if len(tokens) >= 3:
        t_sorted = sorted(tokens[:3])
        keys.append(f"n3:{t_sorted[0]}_{t_sorted[1]}_{t_sorted[2]}")
        
    # 4. Token + address numbers
    if addr_str and tokens:
        nums = NUM_RE.findall(addr_str)
        if nums:
            keys.append(f"num:{tokens[0]}_{nums[0]}")
            if len(nums) > 1:
                keys.append(f"num:{tokens[0]}_{nums[-1]}")
                
    return keys

print("Loading test slice...")
s1 = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", n_rows=20000, infer_schema_length=0)
gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", n_rows=20000, infer_schema_length=0)

s1_ids = s1["entity_id"].to_list()
s1_names = s1["business_name"].to_list()
s1_addrs = s1["business_address"].to_list()
s1_countries = s1["country"].to_list()

gt_s1_ids = gt["source1_entity_id"].to_list()
gt_matches = gt["matched_entity_ids"].to_list()

s1_id_set = set(s1_ids)
gt_map = {}
for sid, m in zip(gt_s1_ids, gt_matches):
    if sid in s1_id_set:
        gt_map[sid] = set(m.split(',')) if m else set()

s2 = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", n_rows=600000, infer_schema_length=0)
s3 = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", n_rows=600000, infer_schema_length=0)

target_ids_set = set(s2["entity_id"].to_list()).union(set(s3["entity_id"].to_list()))

t0 = time.time()
print("Building index on S2 & S3...")
index = defaultdict(list)

for df in [s2, s3]:
    c_list = df["country"].to_list()
    id_list = df["entity_id"].to_list()
    name_list = df["business_name"].to_list()
    addr_list = df["business_address"].to_list()
    
    for c, eid, name, addr in zip(c_list, id_list, name_list, addr_list):
        keys = get_keys_for_record(name, addr)
        for k in keys:
            index[(c, k)].append(eid)

print(f"Built index in {time.time()-t0:.2f}s with {len(index):,} buckets")

print("Evaluating recall...")
t1 = time.time()
total_true_in_scope = 0
total_recalled = 0
cand_counts = []

for sid, c, name, addr in zip(s1_ids, s1_countries, s1_names, s1_addrs):
    true_set = gt_map.get(sid, set())
    in_scope = true_set.intersection(target_ids_set)
    if not in_scope:
        continue
        
    keys = get_keys_for_record(name, addr)
    candidates = set()
    for k in keys:
        bucket = index.get((c, k))
        if bucket and len(bucket) <= 1000:
            candidates.update(bucket)
            
    total_true_in_scope += len(in_scope)
    total_recalled += len(in_scope.intersection(candidates))
    cand_counts.append(len(candidates))

print(f"Evaluated in {time.time()-t1:.2f}s")
print(f"Recall: {total_recalled}/{total_true_in_scope} = {total_recalled/total_true_in_scope*100:.2f}%")
print(f"Average candidates: {sum(cand_counts)/len(cand_counts):.1f}, Median: {sorted(cand_counts)[len(cand_counts)//2]}")
