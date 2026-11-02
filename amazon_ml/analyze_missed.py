import polars as pl
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# Let's inspect the missed pairs in detail
import eval_blocking_fast as eb

s1 = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", n_rows=20000, infer_schema_length=0)
gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", n_rows=20000, infer_schema_length=0)
s2 = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", n_rows=600000, infer_schema_length=0)
s3 = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", n_rows=600000, infer_schema_length=0)

s1_dict = {r['entity_id']: r for r in s1.to_dicts()}
s2_dict = {r['entity_id']: r for r in s2.to_dicts()}
s3_dict = {r['entity_id']: r for r in s3.to_dicts()}

gt_map = {}
for r in gt.to_dicts():
    sid = r['source1_entity_id']
    m = r['matched_entity_ids']
    if m:
        gt_map[sid] = set(m.split(','))

target_all = {}
target_all.update(s2_dict)
target_all.update(s3_dict)

index = defaultdict(list)
for df in [s2, s3]:
    c_list = df["country"].to_list()
    id_list = df["entity_id"].to_list()
    name_list = df["business_name"].to_list()
    addr_list = df["business_address"].to_list()
    
    for c, eid, name, addr in zip(c_list, id_list, name_list, addr_list):
        keys = eb.get_keys_for_record(name, addr)
        for k in keys:
            index[(c, k)].append(eid)

print("--- ANALYZING MISSED PAIRS ---")
missed_count = 0
for sid, s1_rec in s1_dict.items():
    true_set = gt_map.get(sid, set())
    in_scope = true_set.intersection(set(target_all.keys()))
    if not in_scope:
        continue
    
    c = s1_rec['country']
    s1_keys = set(eb.get_keys_for_record(s1_rec['business_name'], s1_rec['business_address']))
    
    candidates = set()
    for k in s1_keys:
        bucket = index.get((c, k))
        if bucket and len(bucket) <= 1000:
            candidates.update(bucket)
            
    missed = in_scope - candidates
    for m in missed:
        t_rec = target_all[m]
        t_keys = set(eb.get_keys_for_record(t_rec['business_name'], t_rec['business_address']))
        missed_count += 1
        print(f"\n[MISSED {missed_count}] S1: {sid} <---> Target: {m}")
        print(f"  S1:     NAME: '{s1_rec['business_name']}' | ADDR: '{s1_rec['business_address']}'")
        print(f"  TARGET: NAME: '{t_rec['business_name']}' | ADDR: '{t_rec['business_address']}'")
        print(f"  S1 Keys:     {s1_keys}")
        print(f"  Target Keys: {t_keys}")
        print(f"  Intersection: {s1_keys.intersection(t_keys)}")
        if missed_count >= 15:
            break
    if missed_count >= 15:
        break

