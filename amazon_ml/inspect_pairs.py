import polars as pl
import re

print("Loading train datasets...")
s1 = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", infer_schema_length=0)
gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", infer_schema_length=0)

s1_dict = {row["entity_id"]: row for row in s1.to_dicts()}

# load small chunks or index of s2 and s3 to check pairs
print("Loading subset of s2 and s3...")
s2 = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", n_rows=500000, infer_schema_length=0)
s3 = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", n_rows=500000, infer_schema_length=0)

s2_dict = {row["entity_id"]: row for row in s2.to_dicts()}
s3_dict = {row["entity_id"]: row for row in s3.to_dicts()}

# Check 20 matched pairs
print("\n================== SAMPLE MATCHED PAIRS ==================")
count = 0
for row in gt.to_dicts():
    s1_id = row["source1_entity_id"]
    matched = row["matched_entity_ids"]
    if not matched:
        continue
    matched_ids = matched.split(",")
    # check if any matched_id is in s2_dict or s3_dict
    s1_rec = s1_dict.get(s1_id)
    if not s1_rec:
        continue
    
    found_any = False
    for mid in matched_ids:
        target_rec = s2_dict.get(mid) or s3_dict.get(mid)
        if target_rec:
            found_any = True
            print(f"\n[MATCH] S1 ID: {s1_id} <---> Target ID: {mid}")
            print(f"  S1 Name:    {s1_rec['business_name']}")
            print(f"  Target Name:{target_rec['business_name']}")
            print(f"  S1 Addr:    {s1_rec['business_address']}")
            print(f"  Target Addr:{target_rec['business_address']}")
            print(f"  S1 Country: {s1_rec['country']} | Target Country: {target_rec['country']}")
            count += 1
            if count >= 15:
                break
    if count >= 15:
        break

