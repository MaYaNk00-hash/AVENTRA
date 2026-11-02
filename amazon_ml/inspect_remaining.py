import polars as pl
import re
import sys
from collections import defaultdict
import test_high_recall_blocking as thb

sys.stdout.reconfigure(encoding='utf-8')

s1 = pl.read_parquet("s1_eval_sample.parquet")
s2 = pl.read_parquet("s2_eval_sample.parquet")
s3 = pl.read_parquet("s3_eval_sample.parquet")
gt = pl.read_parquet("gt_eval_sample.parquet")

gt_map = {row['source1_entity_id']: set(row['matched_entity_ids'].split(',')) for row in gt.iter_rows(named=True)}

# Load target dict
targets = {}
for df in [s2, s3]:
    for r in df.iter_rows(named=True):
        targets[r['entity_id']] = r

index = defaultdict(list)
for eid, r in targets.items():
    for k in thb.get_keys(r['business_name'], r['business_address']):
        index[(r['country'], k)].append(eid)

print("--- 10 REMAINING MISSED PAIRS ---")
missed_count = 0
for r in s1.iter_rows(named=True):
    sid = r['entity_id']
    c = r['country']
    true_targets = gt_map[sid]
    candidates = set()
    for k in thb.get_keys(r['business_name'], r['business_address']):
        b = index.get((c, k))
        if b and len(b) <= 3000:
            candidates.update(b)
            
    missed = true_targets - candidates
    for m in missed:
        t_rec = targets.get(m)
        if not t_rec:
            continue
        missed_count += 1
        print(f"\n[REMAINING MISSED {missed_count}] Country: {c}")
        print(f"  S1:     NAME: '{r['business_name']}' | ADDR: '{r['business_address']}'")
        print(f"  TARGET: NAME: '{t_rec['business_name']}' | ADDR: '{t_rec['business_address']}'")
        s1_keys = set(thb.get_keys(r['business_name'], r['business_address']))
        t_keys = set(thb.get_keys(t_rec['business_name'], t_rec['business_address']))
        print(f"  S1 keys: {sorted(s1_keys)[:6]}")
        print(f"  T  keys: {sorted(t_keys)[:6]}")
        if missed_count >= 10:
            break
    if missed_count >= 10:
        break
