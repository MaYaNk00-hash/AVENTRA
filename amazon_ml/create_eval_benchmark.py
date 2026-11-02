import polars as pl
import re
import sys
import time
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# 1. Load ground truth sample of 5,000 entities with matches
gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", infer_schema_length=0)
gt_sample = gt.filter(pl.col("matched_entity_ids").is_not_null() & (pl.col("matched_entity_ids") != "")).head(5000)

s1_needed = set(gt_sample["source1_entity_id"].to_list())
targets_needed = set()
gt_map = {}

for row in gt_sample.iter_rows():
    sid, m = row[0], row[1]
    mids = set(m.split(","))
    gt_map[sid] = mids
    targets_needed.update(mids)

print(f"Sampling {len(s1_needed)} S1 entities and {len(targets_needed)} true target entities.")

# 2. Extract these S1 entities from train_source1
s1_full = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", infer_schema_length=0)
s1_df = s1_full.filter(pl.col("entity_id").is_in(list(s1_needed)))

# 3. Extract these target entities from train_source2 and train_source3 PLUS random noise records (e.g. 200,000 noise records)
print("Extracting targets and noise from source2 and source3...")
s2_full = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", n_rows=300000, infer_schema_length=0)
s3_full = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", n_rows=300000, infer_schema_length=0)

# Also explicitly fetch any targets that weren't in the first 300k rows
s2_needed = [t for t in targets_needed if t.startswith("S2-")]
s3_needed = [t for t in targets_needed if t.startswith("S3-")]

s2_all = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", infer_schema_length=0)
s3_all = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", infer_schema_length=0)

s2_targets = s2_all.filter(pl.col("entity_id").is_in(s2_needed))
s3_targets = s3_all.filter(pl.col("entity_id").is_in(s3_needed))

# Combine targets + 100k noise records from each
s2_eval = pl.concat([s2_targets, s2_full.head(100000)]).unique(subset=["entity_id"])
s3_eval = pl.concat([s3_targets, s3_full.head(100000)]).unique(subset=["entity_id"])

print(f"Evaluation target pool: {len(s2_eval) + len(s3_eval):,} records")

# Save these evaluation slices as parquet for lightning fast testing
s1_df.write_parquet("s1_eval_sample.parquet")
s2_eval.write_parquet("s2_eval_sample.parquet")
s3_eval.write_parquet("s3_eval_sample.parquet")
gt_sample.write_parquet("gt_eval_sample.parquet")
print("Saved evaluation parquet files successfully.")
