The synthetic prototype contains exactly 5,000 fictional company records with
the same six-column schema as the public-data demo:

`symbol, company_name, sector, headquarters, sub_industry, review_state`

Dataset location:
`data/synthetic_company_demo/20261102T173024Z-8c4b3486/`

Files include `companies.csv`, `companies.sqlite`, `provenance.json`, and
`connection.json`. The company table contains 5,000 unique `SYN` identifiers.
The additional `sector_counts` table contains 11 derived aggregates summing to
5,000. These 11 aggregate rows are not additional company records.

Every company name starts with `Synthetic`. Headquarters include fictional
districts; real city and sector names are vocabulary only. No real company facts,
transactions, financial amounts, predictions, or metrics are claimed. Review
states are generated local demonstration values.

The generator uses seed 42 and version 1.0.0. Repeating the seed and count produces
the same CSV content/hash. Each invocation creates a new snapshot directory and
refuses to overwrite an existing destination:

```powershell
python -m infrastructure.scripts.generate_synthetic_company_demo --count 5000 --seed 42 --connect
```

Open Overview in AVENTRA and find **Synthetic company directory**. Its preview and
summary use deterministic backend tools; **Ask about this data** uses the
configured external API. Only the local `review_state` field is writable through
the approved source. Provenance and run metadata identify this dataset as synthetic.

Scoped SQLite retrieval now supports at most 10,000 rows per resource, enabling
the full 5k sample to be searched and summarized. External API collections retain
their existing 500-row and 2 MB response limits. UI results remain bounded and
evidence tables display a preview. Large pairwise comparisons now use disclosed lexical candidate shortlisting
and a 50,000-scored-pair ceiling; this does not provide exhaustive 5k-by-5k matching. See PROTOTYPE_OPERATIONS.md. No ML artifacts are retrained or replaced.

Live verification processed all 5,000 company rows: the preview returned 10 rows
in 260.12 ms and the summary completed in 188.93 ms for that execution. Actual
results are saved in the snapshot's `verification.json`; these are observed
durations, not performance guarantees. All 26 targeted backend tests and the
standalone TypeScript check passed.
