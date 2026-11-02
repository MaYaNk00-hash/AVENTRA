import os
import pandas as pd

def inspect_file(path, n=5):
    print(f"\n--- Inspecting {path} ---")
    df = pd.read_csv(path, sep="\t", nrows=n)
    print(df.info())
    print(df.head(n))

print("Checking dataset lines/shape...")
for split in ["train", "test"]:
    for f in os.listdir(f"dataset/{split}"):
        p = f"dataset/{split}/{f}"
        if p.endswith(".tsv"):
            inspect_file(p, 5)
