import pandas as pd

df = pd.read_csv("output/candidate_pairs.tsv", sep="\t", dtype=str, keep_default_na=False)

counts = df["candidate_entity_ids"].apply(lambda x: len(x.split(",")) if x else 0)

print("rows:", len(df))
print("rows with candidates:", (counts > 0).sum())
print("avg candidates/entity (over rows with candidates):", counts[counts > 0].mean())
print("max candidates for one entity:", counts.max())
print("total candidate ID entries:", counts.sum())