import polars as pl
import os

print("--- Counting rows in files ---")
for split in ["train", "test"]:
    for f in os.listdir(f"dataset/{split}"):
        if f.endswith(".tsv"):
            path = f"dataset/{split}/{f}"
            df = pl.read_csv(path, separator="\t", infer_schema_length=0)
            print(f"{path}: {len(df):,} rows")
            if "country" in df.columns:
                print("  Countries:", df["country"].value_counts().to_dicts())
