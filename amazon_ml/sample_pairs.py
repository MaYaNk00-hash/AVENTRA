import polars as pl
import sys

sys.stdout.reconfigure(encoding='utf-8')

s1 = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", infer_schema_length=0)
gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", infer_schema_length=0)
s2 = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", n_rows=1000000, infer_schema_length=0)
s3 = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", n_rows=1000000, infer_schema_length=0)

s1_map = {r['entity_id']: r for r in s1.head(100000).to_dicts()}
s2_map = {r['entity_id']: r for r in s2.to_dicts()}
s3_map = {r['entity_id']: r for r in s3.to_dicts()}

print("--- 20 Sample True Pairs ---")
seen = 0
for row in gt.iter_rows(named=True):
    s1_id = row['source1_entity_id']
    if s1_id not in s1_map:
        continue
    matched = row['matched_entity_ids']
    if not matched:
        continue
    for mid in matched.split(','):
        target = s2_map.get(mid) or s3_map.get(mid)
        if target:
            seen += 1
            s1_rec = s1_map[s1_id]
            print(f"[{seen}] Country: {s1_rec['country']}")
            print(f"  S1:     NAME: {s1_rec['business_name']} | ADDR: {s1_rec['business_address']}")
            print(f"  TARGET: NAME: {target['business_name']} | ADDR: {target['business_address']}")
            print("-" * 70)
            if seen >= 20:
                break
    if seen >= 20:
        break
