import polars as pl
import numpy as np
import pickle
import time
import sys
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from rapidfuzz import distance, fuzz

sys.path.insert(0, os.path.abspath("code/business_entity_resolution/src"))
import blocking
import features
import metric

sys.stdout.reconfigure(encoding='utf-8')

# Global variables for worker processes
G_TARGETS = None
G_INDEX = None
G_MODEL = None
G_THRESHOLD = 0.85

def init_worker(targets, index, model_path, threshold):
    global G_TARGETS, G_INDEX, G_MODEL, G_THRESHOLD
    G_TARGETS = targets
    G_INDEX = index
    with open(model_path, "rb") as f:
        G_MODEL = pickle.load(f)
    G_THRESHOLD = threshold

def process_s1_batch(batch_s1):
    results_match = []
    results_cand = []
    
    for s1_rec in batch_s1:
        sid = s1_rec['entity_id']
        name = s1_rec['business_name']
        addr = s1_rec['business_address']
        
        keys = blocking.get_keys(name, addr)
        candidates = set()
        for k in keys:
            bucket = G_INDEX.get(k)
            if bucket and len(bucket) <= 2500:
                candidates.update(bucket)
                
        cand_list = sorted(list(candidates))
        if not cand_list:
            results_cand.append((sid, ""))
            results_match.append((sid, ""))
            continue
            
        results_cand.append((sid, ",".join(cand_list)))
        
        # Fast filter
        s1_cn = s1_rec['c_name']
        s1_ta = s1_rec['t_addr']
        s1_tn = s1_rec['t_name']
        
        filtered_cands = []
        for cid in cand_list:
            cand_r = G_TARGETS[cid]
            jw = distance.JaroWinkler.similarity(s1_cn, cand_r['c_name'])
            if jw >= 0.45 or len(s1_ta & cand_r['t_addr']) > 0 or len(s1_tn & cand_r['t_name']) > 0:
                filtered_cands.append(cid)
                
        if not filtered_cands:
            results_match.append((sid, ""))
            continue
            
        # Extract features and predict
        pair_feats = [features.extract_features(s1_rec, G_TARGETS[cid]) for cid in filtered_cands]
        probs = G_MODEL.predict_proba(np.array(pair_feats, dtype=np.float32))[:, 1]
        
        matched_ids = [cid for cid, p in zip(filtered_cands, probs) if p >= G_THRESHOLD]
        results_match.append((sid, ",".join(matched_ids) if matched_ids else ""))
        
    return results_match, results_cand

def test_parallel():
    s1 = pl.read_parquet("s1_eval_sample.parquet")
    s2 = pl.read_parquet("s2_eval_sample.parquet")
    s3 = pl.read_parquet("s3_eval_sample.parquet")
    gt = pl.read_parquet("gt_eval_sample.parquet")
    
    gt_map = {row['source1_entity_id']: set(row['matched_entity_ids'].split(',')) for row in gt.iter_rows(named=True)}
    
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
        
    print(f"Testing parallel execution on {len(s1_records):,} records with 8 workers...")
    t0 = time.time()
    
    # Split into batches of 500
    chunk_size = 500
    batches = [s1_records[i:i+chunk_size] for i in range(0, len(s1_records), chunk_size)]
    
    with ProcessPoolExecutor(max_workers=8, initializer=init_worker, initargs=(targets, dict(index), "models/matching_lgb_model.pkl", 0.85)) as executor:
        results = list(executor.map(process_s1_batch, batches))
        
    all_matches = {}
    for batch_match, batch_cand in results:
        for sid, mids in batch_match:
            all_matches[sid] = set(mids.split(",")) if mids else set()
            
    elapsed = time.time() - t0
    f05 = metric.compute_macro_f05(gt_map, all_matches)
    print(f"Completed 5,000 queries in {elapsed:.2f}s (Rate: {len(s1_records)/elapsed:.1f} queries/sec)")
    print(f"Validation Macro F_0.5 Score: {f05:.4f}")

if __name__ == "__main__":
    test_parallel()
