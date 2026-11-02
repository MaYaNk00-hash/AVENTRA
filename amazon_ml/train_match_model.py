import polars as pl
import numpy as np
import rapidfuzz
from rapidfuzz import fuzz, distance
import lightgbm as lgb
from sklearn.metrics import precision_recall_fscore_support
import time
import sys
import re
from collections import defaultdict
import metric
import test_high_recall_blocking as thb

sys.stdout.reconfigure(encoding='utf-8')

# 1. Load benchmark datasets
print("Loading benchmark data...")
s1 = pl.read_parquet("s1_eval_sample.parquet")
s2 = pl.read_parquet("s2_eval_sample.parquet")
s3 = pl.read_parquet("s3_eval_sample.parquet")
gt = pl.read_parquet("gt_eval_sample.parquet")

gt_map = {row['source1_entity_id']: set(row['matched_entity_ids'].split(',')) for row in gt.iter_rows(named=True)}

# Load target records map
targets = {}
for df in [s2, s3]:
    for r in df.iter_rows(named=True):
        targets[r['entity_id']] = r

s1_records = {r['entity_id']: r for r in s1.iter_rows(named=True)}

# Build blocking index
print("Building blocking index...")
t0 = time.time()
index = defaultdict(list)
for eid, r in targets.items():
    for k in thb.get_keys(r['business_name'], r['business_address']):
        index[(r['country'], k)].append(eid)
print(f"Index built in {time.time()-t0:.2f}s")

# Generate candidate pairs
print("Generating candidate pairs...")
s1_list = list(s1_records.values())

SPLIT_RE = re.compile(r'[^a-z0-9]+')
NUM_RE = re.compile(r'\b\d{1,6}\b')

def clean(s):
    return " ".join(SPLIT_RE.split(s.lower())).strip() if s else ""

def get_tokens(s):
    return set(SPLIT_RE.split(s.lower())) - {""} if s else set()

def get_nums(s):
    return set(NUM_RE.findall(s.lower())) if s else set()

# Precompute clean strings & tokens
print("Precomputing text representations...")
for r in list(s1_records.values()) + list(targets.values()):
    r['c_name'] = clean(r['business_name'])
    r['c_addr'] = clean(r['business_address'])
    r['t_name'] = get_tokens(r['business_name'])
    r['t_addr'] = get_tokens(r['business_address'])
    r['n_addr'] = get_nums(r['business_address'])

def extract_features(s1_r, cand_r):
    # Name features
    s1_cn, c_cn = s1_r['c_name'], cand_r['c_name']
    s1_ca, c_ca = s1_r['c_addr'], cand_r['c_addr']
    
    name_ratio = fuzz.ratio(s1_cn, c_cn) / 100.0
    name_tsort = fuzz.token_sort_ratio(s1_cn, c_cn) / 100.0
    name_tset = fuzz.token_set_ratio(s1_cn, c_cn) / 100.0
    name_jw = distance.JaroWinkler.similarity(s1_cn, c_cn)
    
    t_name_s1 = s1_r['t_name']
    t_name_c = cand_r['t_name']
    name_jaccard = len(t_name_s1 & t_name_c) / max(1, len(t_name_s1 | t_name_c))
    name_len_diff = abs(len(s1_cn) - len(c_cn)) / max(1, max(len(s1_cn), len(c_cn)))
    
    # Address features
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
        
        t_addr_s1 = s1_r['t_addr']
        t_addr_c = cand_r['t_addr']
        addr_jaccard = len(t_addr_s1 & t_addr_c) / max(1, len(t_addr_s1 | t_addr_c))
        
        # Number matching in address
        n_s1 = s1_r['n_addr']
        n_c = cand_r['n_addr']
        if n_s1 and n_c:
            num_match = len(n_s1 & n_c) / max(1, len(n_s1 | n_c))
        elif not n_s1 and not n_c:
            num_match = 0.5
        else:
            num_match = 0.0
            
    # Source indicator (1 for S2, 0 for S3)
    is_s2 = 1.0 if cand_r['entity_id'].startswith("S2-") else 0.0
    
    # Total combined jaccard
    total_tokens_s1 = t_name_s1 | s1_r['t_addr']
    total_tokens_c = t_name_c | cand_r['t_addr']
    total_jaccard = len(total_tokens_s1 & total_tokens_c) / max(1, len(total_tokens_s1 | total_tokens_c))
    
    return [
        name_ratio, name_tsort, name_tset, name_jw, name_jaccard, name_len_diff,
        addr_null, addr_tsort, addr_tset, addr_jw, addr_jaccard, num_match,
        is_s2, total_jaccard,
        name_tset * addr_tset,
        name_jw * addr_jw
    ]

# Split 5,000 S1 queries into 3,500 train and 1,500 validation
np.random.seed(42)
all_s1_ids = list(s1_records.keys())
np.random.shuffle(all_s1_ids)

train_s1_ids = set(all_s1_ids[:3500])
val_s1_ids = set(all_s1_ids[3500:])

print(f"Generating training pairs from {len(train_s1_ids)} S1 entities...")
X_train, y_train = [], []
t0 = time.time()

for sid in train_s1_ids:
    s1_r = s1_records[sid]
    c = s1_r['country']
    true_targets = gt_map[sid]
    
    candidates = set()
    for k in thb.get_keys(s1_r['business_name'], s1_r['business_address']):
        b = index.get((c, k))
        if b and len(b) <= 2500:
            candidates.update(b)
            
    for cand_id in candidates:
        cand_r = targets[cand_id]
        feat = extract_features(s1_r, cand_r)
        label = 1 if cand_id in true_targets else 0
        X_train.append(feat)
        y_train.append(label)

print(f"Generated {len(X_train):,} training pairs in {time.time()-t0:.2f}s (Positives: {sum(y_train):,})")

X_train = np.array(X_train, dtype=np.float32)
y_train = np.array(y_train, dtype=np.int32)

print("Training LightGBM model...")
lgb_model = lgb.LGBMClassifier(
    n_estimators=150,
    learning_rate=0.08,
    max_depth=6,
    num_leaves=31,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1
)
lgb_model.fit(X_train, y_train)

# Feature importance
feature_names = [
    'name_ratio', 'name_tsort', 'name_tset', 'name_jw', 'name_jaccard', 'name_len_diff',
    'addr_null', 'addr_tsort', 'addr_tset', 'addr_jw', 'addr_jaccard', 'num_match',
    'is_s2', 'total_jaccard', 'name_x_addr_tset', 'name_x_addr_jw'
]
print("\nFeature Importances:")
for name, imp in sorted(zip(feature_names, lgb_model.feature_importances_), key=lambda x: x[1], reverse=True):
    print(f"  {name:20s}: {imp}")

# Evaluate on Validation Set with threshold tuning for Macro F0.5
print("\nEvaluating on Validation set of 1,500 entities...")
val_data = []
t0 = time.time()
for sid in val_s1_ids:
    s1_r = s1_records[sid]
    c = s1_r['country']
    candidates = set()
    for k in thb.get_keys(s1_r['business_name'], s1_r['business_address']):
        b = index.get((c, k))
        if b and len(b) <= 2500:
            candidates.update(b)
            
    cands_list = list(candidates)
    if not cands_list:
        val_data.append((sid, [], []))
        continue
        
    feats = [extract_features(s1_r, targets[cid]) for cid in cands_list]
    probs = lgb_model.predict_proba(np.array(feats, dtype=np.float32))[:, 1]
    val_data.append((sid, cands_list, probs))

print(f"Validation inference completed in {time.time()-t0:.2f}s")

# Test various probability thresholds
val_gt = {sid: gt_map[sid] for sid in val_s1_ids}
best_thresh = 0.5
best_f05 = 0.0

for thresh in np.arange(0.30, 0.95, 0.05):
    preds = {}
    for sid, cands, probs in val_data:
        matched = {cid for cid, p in zip(cands, probs) if p >= thresh}
        preds[sid] = matched
    score = metric.compute_macro_f05(val_gt, preds)
    print(f"Threshold: {thresh:.2f} --> Validation Macro F_0.5: {score:.4f}")
    if score > best_f05:
        best_f05 = score
        best_thresh = thresh

print(f"\n>>> BEST THRESHOLD: {best_thresh:.2f} with Macro F_0.5 = {best_f05:.4f} <<<")
