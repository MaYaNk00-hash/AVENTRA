import polars as pl
import re
import sys
import time
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

LEGAL_SUFFIXES = {
    'inc', 'incorporated', 'corp', 'corporation', 'llc', 'l.l.c.', 'ltd', 'limited',
    'pvt', 'private', 'co', 'company', 'services', 'enterprises', 'associates',
    'group', 'center', 'centre', 'solutions', 'technologies', 'holdings', 'trust',
    'sarl', 'sas', 'sa', 'eurl', 'gmbh'
}

COMMON_STOPWORDS = {
    'and', '&', 'the', 'of', 'in', 'at', 'on', 'for', 'to', 'a', 'an', 'by',
    'no', 'near', 'opp', 'opposite', 'behind', 'fl', 'floor', 'block', 'unit',
    'plot', 'road', 'rd', 'street', 'st', 'avenue', 'ave', 'lane', 'ln', 'dr', 'drive'
}

def clean_text(text):
    if not text or text == 'None' or text == '<NULL>':
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_name_tokens(text):
    cleaned = clean_text(text)
    tokens = [t for t in cleaned.split() if t not in LEGAL_SUFFIXES and t not in COMMON_STOPWORDS and len(t) > 1]
    return tokens

def get_blocking_keys(name, addr):
    keys = set()
    cleaned_name = clean_text(name)
    tokens = extract_name_tokens(name)
    
    # 1. Exact cleaned alphanumeric name (without spaces)
    name_no_space = "".join(cleaned_name.split())
    if len(name_no_space) >= 4:
        keys.add(f"n_full:{name_no_space[:20]}")
    
    # 2. Significant name tokens (first 2 tokens sorted)
    if len(tokens) >= 2:
        sorted_2 = tuple(sorted(tokens[:2]))
        keys.add(f"n2:{sorted_2[0]}_{sorted_2[1]}")
    elif len(tokens) == 1:
        keys.add(f"n1:{tokens[0]}")
        
    # 3. First 3 tokens sorted if >= 3
    if len(tokens) >= 3:
        sorted_3 = tuple(sorted(tokens[:3]))
        keys.add(f"n3:{sorted_3[0]}_{sorted_3[1]}_{sorted_3[2]}")

    # 4. First token + address numbers
    addr_cleaned = clean_text(addr)
    addr_nums = re.findall(r'\b\d{2,6}\b', addr_cleaned)
    if tokens and addr_nums:
        keys.add(f"tok_num:{tokens[0]}_{addr_nums[0]}")
        if len(addr_nums) > 1:
            keys.add(f"tok_num:{tokens[0]}_{addr_nums[-1]}")
            
    # 5. Core name (first 2 tokens concatenated)
    if len(tokens) >= 2:
        keys.add(f"n_prefix:{tokens[0][:4]}_{tokens[1][:4]}")
        
    return keys

print("Loading test slice of 20,000 S1 records and ground truth...")
s1 = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", n_rows=20000, infer_schema_length=0)
gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", n_rows=20000, infer_schema_length=0)

s1_ids = set(s1["entity_id"])
gt_map = {}
all_matched_targets = set()
for row in gt.iter_rows(named=True):
    s1_id = row['source1_entity_id']
    if s1_id in s1_ids:
        m = row['matched_entity_ids']
        if m:
            mids = set(m.split(','))
            gt_map[s1_id] = mids
            all_matched_targets.update(mids)
        else:
            gt_map[s1_id] = set()

# Load S2 and S3 sample
s2 = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", n_rows=600000, infer_schema_length=0)
s3 = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", n_rows=600000, infer_schema_length=0)

loaded_target_ids = set(s2["entity_id"]).union(set(s3["entity_id"]))

# Build inverted index for targets by country
start = time.time()
print("Building index on S2/S3...")
index = defaultdict(list)

for df in [s2, s3]:
    for row in df.iter_rows(named=True):
        country = row['country']
        eid = row['entity_id']
        name = row['business_name']
        addr = row['business_address']
        keys = get_blocking_keys(name, addr)
        for k in keys:
            index[(country, k)].append(eid)

print(f"Index built in {time.time()-start:.2f}s with {len(index)} distinct country+key buckets.")

# Query S1 records
print("Evaluating blocking recall and candidate size on S1...")
total_true_in_scope = 0
total_recalled = 0
cand_counts = []

for row in s1.iter_rows(named=True):
    s1_id = row['entity_id']
    country = row['country']
    true_set = gt_map.get(s1_id, set())
    # Filter true_set to targets that were actually loaded in S2/S3 sample
    loaded_true = true_set.intersection(loaded_target_ids)
    if not loaded_true:
        continue
    
    keys = get_blocking_keys(row['business_name'], row['business_address'])
    candidates = set()
    for k in keys:
        matches = index.get((country, k))
        if matches:
            if len(matches) <= 2000: # cap huge buckets to avoid explosion
                candidates.update(matches)
                
    total_true_in_scope += len(loaded_true)
    total_recalled += len(loaded_true.intersection(candidates))
    cand_counts.append(len(candidates))

print(f"Recall: {total_recalled}/{total_true_in_scope} = {total_recalled/total_true_in_scope*100:.2f}%")
print(f"Average candidates per S1: {sum(cand_counts)/len(cand_counts):.1f}, Median: {sorted(cand_counts)[len(cand_counts)//2]}")
