import polars as pl
import numpy as np
import rapidfuzz
from rapidfuzz import fuzz, distance
import lightgbm as lgb
import time
import sys
import os
import re
import pickle
from collections import defaultdict
import metric
import test_high_recall_blocking as thb

sys.stdout.reconfigure(encoding='utf-8')

os.makedirs("models", exist_ok=True)
os.makedirs("output", exist_ok=True)

print("--- Step 1: Loading Training Sample for Model Training ---")
# Sample 30,000 S1 entities from train
s1_train = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", n_rows=60000, infer_schema_length=0)
gt_train = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", n_rows=60000, infer_schema_length=0)

s1_needed = set(s1_train["entity_id"].to_list())
gt_map = {}
targets_needed = set()

for row in gt_train.iter_rows():
    sid, m = row[0], row[1]
    if sid in s1_needed:
        mids = set(m.split(",")) if m else set()
        gt_map[sid] = mids
        targets_needed.update(mids)

print(f"Loaded {len(s1_needed):,} S1 train entities with {len(targets_needed):,} true targets.")

# Load matching targets from S2 and S3 plus random negative targets
s2_train = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", n_rows=500000, infer_schema_length=0)
s3_train = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", n_rows=500000, infer_schema_length=0)

# Make sure all true targets are loaded
s2_needed = [t for t in targets_needed if t.startswith("S2-")]
s3_needed = [t for t in targets_needed if t.startswith("S3-")]

s2_all = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", infer_schema_length=0)
s3_all = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", infer_schema_length=0)

s2_targets = s2_all.filter(pl.col("entity_id").is_in(s2_needed))
s3_targets = s3_all.filter(pl.col("entity_id").is_in(s3_needed))

s2_combined = pl.concat([s2_targets, s2_train.head(150000)]).unique(subset=["entity_id"])
s3_combined = pl.concat([s3_targets, s3_train.head(150000)]).unique(subset=["entity_id"])

target_records = {}
for df in [s2_combined, s3_combined]:
    for r in df.iter_rows(named=True):
        target_records[r['entity_id']] = r

s1_records = {r['entity_id']: r for r in s1_train.iter_rows(named=True)}

print(f"Total target training records: {len(target_records):,}")

# Precompute representations
SPLIT_RE = re.compile(r'[^a-z0-9]+')
NUM_RE = re.compile(r'\b\d{1,6}\b')

def clean(s):
    return " ".join(SPLIT_RE.split(s.lower())).strip() if s else ""

def get_tokens(s):
    return set(SPLIT_RE.split(s.lower())) - {""} if s else set()

def get_nums(s):
    return set(NUM_RE.findall(s.lower())) if s else set()

print("Precomputing text representations...")
for r in list(s1_records.values()) + list(target_records.values()):
    r['c_name'] = clean(r['business_name'])
    r['c_addr'] = clean(r['business_address'])
    r['t_name'] = get_tokens(r['business_name'])
    r['t_addr'] = get_tokens(r['business_address'])
    r['n_addr'] = get_nums(r['business_address'])

# Build blocking index
print("Building blocking index...")
t0 = time.time()
index = defaultdict(list)
for eid, r in target_records.items():
    for k in thb.get_keys(r['business_name'], r['business_address']):
        index[(r['country'], k)].append(eid)
print(f"Index built in {time.time()-t0:.2f}s")

def extract_features(s1_r, cand_r):
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
        
        n_s1 = s1_r['n_addr']
        n_c = cand_r['n_addr']
        if n_s1 and n_c:
            num_match = len(n_s1 & n_c) / max(1, len(n_s1 | n_c))
        elif not n_s1 and not n_c:
            num_match = 0.5
        else:
            num_match = 0.0
            
    is_s2 = 1.0 if cand_r['entity_id'].startswith("S2-") else 0.0
    
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

# Generate training pairs (sample negatives if too many candidates per query)
print("Extracting feature dataset...")
np.random.seed(42)
all_s1_keys = list(s1_records.keys())
np.random.shuffle(all_s1_keys)

train_keys = all_s1_keys[:45000]
val_keys = all_s1_keys[45000:60000]

X_train, y_train = [], []
for sid in train_keys:
    s1_r = s1_records[sid]
    c = s1_r['country']
    true_targets = gt_map.get(sid, set())
    
    candidates = set()
    for k in thb.get_keys(s1_r['business_name'], s1_r['business_address']):
        b = index.get((c, k))
        if b and len(b) <= 2500:
            candidates.update(b)
            
    pos_cands = [cid for cid in candidates if cid in true_targets]
    neg_cands = [cid for cid in candidates if cid not in true_targets]
    
    # Subsample negative candidates to maintain fast training without losing hard negatives
    if len(neg_cands) > 15:
        neg_cands = list(np.random.choice(neg_cands, 15, replace=False))
        
    for cid in pos_cands + neg_cands:
        cand_r = target_records[cid]
        feat = extract_features(s1_r, cand_r)
        X_train.append(feat)
        y_train.append(1 if cid in true_targets else 0)

print(f"X_train size: {len(X_train):,} pairs (Positives: {sum(y_train):,}, Negatives: {len(y_train)-sum(y_train):,})")

X_train = np.array(X_train, dtype=np.float32)
y_train = np.array(y_train, dtype=np.int32)

print("Training production LightGBM...")
model = lgb.LGBMClassifier(
    n_estimators=250,
    learning_rate=0.06,
    max_depth=7,
    num_leaves=63,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1
)
model.fit(X_train, y_train)

with open("models/matching_lgb_model.pkl", "wb") as f:
    pickle.dump(model, f)
print("Saved model to models/matching_lgb_model.pkl")

# Evaluate validation set
print("Running validation evaluation on 15,000 held-out S1 queries...")
val_gt = {sid: gt_map.get(sid, set()) for sid in val_keys}
val_data = []

t0 = time.time()
for sid in val_keys:
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
        
    # Quick filter: calculate fast JW name score; only run full model on candidates with jw > 0.35 or addr overlap
    filtered_cands = []
    for cid in cands_list:
        cand_r = target_records[cid]
        jw = distance.JaroWinkler.similarity(s1_r['c_name'], cand_r['c_name'])
        if jw >= 0.35 or len(s1_r['t_addr'] & cand_r['t_addr']) > 0 or len(s1_r['t_name'] & cand_r['t_name']) > 0:
            filtered_cands.append(cid)
            
    if not filtered_cands:
        val_data.append((sid, [], []))
        continue
        
    feats = [extract_features(s1_r, target_records[cid]) for cid in filtered_cands]
    probs = model.predict_proba(np.array(feats, dtype=np.float32))[:, 1]
    val_data.append((sid, filtered_cands, probs))

print(f"Validation inference took {time.time()-t0:.2f}s")

best_score = 0
best_thresh = 0.5
for thresh in np.arange(0.40, 0.90, 0.05):
    preds = {}
    for sid, cands, probs in val_data:
        matched = {cid for cid, p in zip(cands, probs) if p >= thresh}
        preds[sid] = matched
    score = metric.compute_macro_f05(val_gt, preds)
    print(f"Threshold: {thresh:.2f} --> Validation Macro F_0.5: {score:.4f}")
    if score > best_score:
        best_score = score
        best_thresh = thresh

print(f"\n=======================================================")
print(f"FINAL BEST VALIDATION MACRO F_0.5: {best_score:.4f} at Threshold {best_thresh:.2f}")
print(f"=======================================================")
