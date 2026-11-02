import polars as pl
import numpy as np
import pickle
import time
import sys
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import distance, fuzz

sys.path.insert(0, os.path.abspath("code/business_entity_resolution/src"))
import blocking
import features
import metric

sys.stdout.reconfigure(encoding='utf-8')

def test_threading():
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
        
    print(f"Testing ThreadPoolExecutor on {len(s1_records):,} records with 8 threads...")
    t0 = time.time()
    
    def process_s1_single(s1_rec):
        sid = s1_rec['entity_id']
        name = s1_rec['business_name']
        addr = s1_rec['business_address']
        
        keys = blocking.get_keys(name, addr)
        candidates = set()
        for k in keys:
            bucket = index.get(k)
            if bucket and len(bucket) <= 2500:
                candidates.update(bucket)
                
        cand_list = sorted(list(candidates))
        if not cand_list:
            return (sid, "", "")
            
        cand_str = ",".join(cand_list)
        
        s1_cn = s1_rec['c_name']
        s1_ta = s1_rec['t_addr']
        s1_tn = s1_rec['t_name']
        
        filtered_cands = []
        for cid in cand_list:
            cand_r = targets[cid]
            jw = distance.JaroWinkler.similarity(s1_cn, cand_r['c_name'])
            if jw >= 0.45 or len(s1_ta & cand_r['t_addr']) > 0 or len(s1_tn & cand_r['t_name']) > 0:
                filtered_cands.append(cid)
                
        if not filtered_cands:
            return (sid, "", cand_str)
            
        pair_feats = [features.extract_features(s1_rec, targets[cid]) for cid in filtered_cands]
        probs = model.predict_proba(np.array(pair_feats, dtype=np.float32))[:, 1]
        
        matched_ids = [cid for cid, p in zip(filtered_cands, probs) if p >= 0.85]
        return (sid, ",".join(matched_ids) if matched_ids else "", cand_str)
        
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(process_s1_single, s1_records))
        
    all_matches = {}
    for sid, mids, cands in results:
        all_matches[sid] = set(mids.split(",")) if mids else set()
        
    elapsed = time.time() - t0
    f05 = metric.compute_macro_f05(gt_map, all_matches)
    print(f"Completed 5,000 queries in {elapsed:.2f}s (Rate: {len(s1_records)/elapsed:.1f} queries/sec)")
    print(f"Validation Macro F_0.5 Score: {f05:.4f}")

if __name__ == "__main__":
    test_threading()
