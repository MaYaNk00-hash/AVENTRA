import polars as pl
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("Loading train datasets...")
s1 = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", infer_schema_length=0)
gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", infer_schema_length=0)

s1_countries = dict(zip(s1["entity_id"], s1["country"]))

# Sample s2 and s3 to check country match
print("Loading s2...")
s2 = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", infer_schema_length=0)
s2_countries = dict(zip(s2["entity_id"], s2["country"]))

print("Loading s3...")
s3 = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", infer_schema_length=0)
s3_countries = dict(zip(s3["entity_id"], s3["country"]))

print("Verifying if cross-country matches exist...")
diff_country_count = 0
total_checked = 0
same_country_count = 0

for row in gt.iter_rows(named=True):
    s1_id = row["source1_entity_id"]
    matched = row["matched_entity_ids"]
    if not matched:
        continue
    c1 = s1_countries.get(s1_id)
    for mid in matched.split(","):
        c2 = s2_countries.get(mid) if mid.startswith("S2-") else s3_countries.get(mid)
        if c2 is not None:
            total_checked += 1
            if c1 != c2:
                diff_country_count += 1
            else:
                same_country_count += 1

print(f"Total pairs checked: {total_checked:,}")
print(f"Same country pairs: {same_country_count:,} ({same_country_count/total_checked*100:.4f}%)")
print(f"Diff country pairs: {diff_country_count:,} ({diff_country_count/total_checked*100:.4f}%)")
