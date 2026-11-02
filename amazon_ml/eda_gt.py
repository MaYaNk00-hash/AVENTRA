import polars as pl

print("--- Ground Truth Analysis ---")
gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", infer_schema_length=0)
print(f"Total S1 entities in GT: {len(gt):,}")

# check empty matches (singletons)
s1_null = gt.filter(pl.col("matched_entity_ids").is_null() | (pl.col("matched_entity_ids") == ""))
print(f"Singletons (no match): {len(s1_null):,} ({len(s1_null)/len(gt)*100:.2f}%)")

non_null = gt.filter(pl.col("matched_entity_ids").is_not_null() & (pl.col("matched_entity_ids") != ""))
print(f"Entities with matches: {len(non_null):,} ({len(non_null)/len(gt)*100:.2f}%)")

# check match count distribution
match_counts = non_null.select(
    pl.col("matched_entity_ids").str.split(",").list.len().alias("n_matches")
)
print("Match counts summary:")
print(match_counts.describe())

# Check sample matches
s1 = pl.read_csv("dataset/train/train_source1.tsv", separator="\t", n_rows=100000, infer_schema_length=0)
s2 = pl.read_csv("dataset/train/train_source2.tsv", separator="\t", n_rows=100000, infer_schema_length=0)
s3 = pl.read_csv("dataset/train/train_source3.tsv", separator="\t", n_rows=100000, infer_schema_length=0)

# Check country consistency in a sample of pairs
sample_gt = non_null.head(1000)
print("Checking country consistency across 1000 sample ground truth rows...")
