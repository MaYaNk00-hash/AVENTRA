import polars as pl
import numpy as np
import pickle
import time
import sys
import os
from collections import defaultdict
from rapidfuzz import distance

sys.path.insert(0, os.path.abspath("code/business_entity_resolution/src"))
import blocking
import features
import metric

sys.stdout.reconfigure(encoding='utf-8')

def test_batch():
    s1 = pl.read_parquet("s1_eval_sample.parquet")
    s2 = pl.read_parquet("s2_eval_sample.parquet")
    s3 = pl.read_parquet("s3_eval_sample.parquet")
    gt = pl.read_parquet("gt_eval_sample.parquet")
    
    gt_map = {row['source1_entity_id']: set(row['matched_entity_ids'].split(',')) for row in gt.iter_rows(named=True)}
    
    with open("models/matching_lgb_model.pkl", "rb") as f:
        model = pickle.load(f)
        
    targets = {}
    index = defaultdict(list)
    for df in [s2, s3]:
        for r in df.iter_rows(named=True):
            rec = {
                'entity_id': r['entity_id'],
                'business_name': r['business_name'],
                'business_address': r['business_address'],
                'country': r['country']
            }
            features.prepare_record(rec)
            targets[r['entity_id']] = rec
            for k in blocking.get_keys(r['business_name'], r['business_address']):
                index[k].append(r['entity_id'])
                
    s1_records = []
    for r in s1.iter_rows(named=True):
        rec = {
            'entity_id': r['entity_id'],
            'business_name': r['business_name'],
            'business_address': r['business_address'],
            'country': r['country']
        }
        features.prepare_record(rec)
        s1_records.append(rec)
        
    print(f"Testing vectorized batch inference on {len(s1_records):,} records...")
    t0 = time.time()
    
    cand_strings = []
    pair_s1_indices = []
    pair_cand_ids = []
    pair_features = []
    
    for s1_idx, s1_rec in enumerate(s1_records):
        name = s1_rec['business_name']
        addr = s1_rec['business_address']
        
        keys = blocking.get_keys(name, addr)
        candidates = set()
        for k in keys:
            bucket = index.get(k)
            if bucket and len(bucket) <= 2500:
                candidates.update(bucket)
                
        cand_list = sorted(list(candidates))
        cand_strings.append(",".join(cand_list))
        
        if not cand_list:
            continue
            
        s1_cn = s1_rec['c_name']
        s1_ta = s1_rec['t_addr']
        s1_tn = s1_rec['t_name']
        
        for cid in cand_list:
            cand_r = targets[cid]
            jw = distance.JaroWinkler.similarity(s1_cn, cand_r['c_name'])
            if jw >= 0.45 or (s1_ta and not s1_ta.isdisjoint(cand_r['t_addr'])) or (s1_tn and not s1_tn.isdisjoint(cand_r['t_name'])):
                pair_s1_indices.append(s1_idx)
                pair_cand_ids.append(cid)
                pair_features.append(features.extract_features(s1_rec, cand_r))
                
    print(f"Feature extraction for {len(pair_features):,} pairs took {time.time()-t0:.2f}s")
    
    if pair_features:
        np_feats = np.array(pair_features, dtype=np.float32)
        probs = model.predict_proba(np_feats)[:, 1]
    else:
        probs = np.array([], dtype=np.float32)
        
    s1_matches = [[] for _ in range(len(s1_records))]
    for s1_idx, cid, p in zip(pair_s1_indices, pair_cand_ids, probs):
        if p >= 0.65:
            s1_matches[s1_idx].append(cid)
            
    all_matches = {s1_records[i]['entity_id']: set(s1_matches[i]) for i in range(len(s1_records))}
    
    elapsed = time.time() - t0
    f05 = metric.compute_macro_f05(gt_map, all_matches)
    print(f"\nCompleted 5,000 queries in {elapsed:.2f}s (Rate: {len(s1_records)/elapsed:.1f} queries/sec)")
    print(f"Validation Macro F_0.5 Score: {f05:.4f}")

if __name__ == "__main__":
    test_batch()
