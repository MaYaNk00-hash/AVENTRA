import polars as pl
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

gt = pl.read_csv("dataset/train/train_ground_truth.tsv", separator="\t", infer_schema_length=0)
total_s1 = len(gt)
empty_s1 = len(gt.filter(pl.col("matched_entity_ids").is_null() | (pl.col("matched_entity_ids") == "")))
matched_s1 = total_s1 - empty_s1

print(f"Total S1 entities: {total_s1:,}")
print(f"Singletons (0 matches): {empty_s1:,} ({empty_s1/total_s1*100:.2f}%)")
print(f"Entities with >=1 match: {matched_s1:,} ({matched_s1/total_s1*100:.2f}%)")

# Let's check distribution of match counts per entity
exploded = gt.filter(pl.col("matched_entity_ids").is_not_null() & (pl.col("matched_entity_ids") != "")).select(
    pl.col("source1_entity_id"),
    pl.col("matched_entity_ids").str.split(",")
).explode("matched_entity_ids")

total_pairs = len(exploded)
print(f"Total true pairs: {total_pairs:,}")
print(f"Average true matches per non-singleton entity: {total_pairs/matched_s1:.2f}")

# Count how many matches come from S2 vs S3
s2_matches = exploded.filter(pl.col("matched_entity_ids").str.starts_with("S2-"))
s3_matches = exploded.filter(pl.col("matched_entity_ids").str.starts_with("S3-"))
print(f"Matches from S2: {len(s2_matches):,} ({len(s2_matches)/total_pairs*100:.2f}%)")
print(f"Matches from S3: {len(s3_matches):,} ({len(s3_matches)/total_pairs*100:.2f}%)")

