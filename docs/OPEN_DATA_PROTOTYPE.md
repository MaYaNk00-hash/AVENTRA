The working public-data prototype imports the datasets/DataHub company directory:
https://github.com/datasets/s-and-p-500-companies

The publisher declares ODC-PDDL-1.0 for the data and identifies Wikipedia as its
upstream source. Each source row is a listed security, so multiple share classes
can represent the same company. This is a reference-data snapshot, not a live CRM.

The first import fetched 503 rows and imported the first 200 into a new database:
`data/open_company_demo/20261102T172201Z-a56e246e/companies.sqlite`.
The original CSV, publisher metadata, source SHA-256, sampling method, and fetch
time are preserved alongside it in `provenance.json`. No existing dataset or
trained artifact was replaced. `sector_counts` contains 11 counts derived from
the imported sample. `review_state` is an explicitly local workflow field,
initialized to `unreviewed`; it is not a fact supplied by the publisher.

Open http://localhost:3000, sign in, and select **Overview**. The open-data card
offers **Preview 10 records**, **Summarize source data**, and **Ask about this
data**. Preview and summary are explicit deterministic backend tools, require
authentication, and do not call Gemini or a trained model. The free-text action
uses the configured Gemini planner and requires working provider access.
Connections → Dataset provenance displays the source attribution and checksum.

The initial live verification completed the preview with 10 real company rows
and summarized 211 rows (200 securities plus 11 sector-aggregate rows, not 211
companies). Actual run results, metadata, and execution events are saved in:
`data/open_company_demo/20261102T172201Z-a56e246e/verification.json`.

To show a controlled write, open a preview row in the evidence table, choose
**Propose update**, select `review_state`, enter the JSON string `"reviewed"`,
and prepare the proposal. In Approvals, inspect the diff, enter a rationale, and
approve or reject. Only this local workflow field is writable; source company
names and the original downloaded CSV remain unchanged.

To fetch a fresh isolated snapshot and register it with the local backend:

```powershell
python infrastructure/scripts/import_open_company_demo.py --connect
```

Each run creates a new folder and refuses to reuse a destination. For non-default
local accounts, set `AVENTRA_DEMO_USERNAME` and `AVENTRA_DEMO_PASSWORD` in the shell.
The importer fetches only the documented public repository; it does not train a
model, synthesize business records, or claim successful Gemini access.

Local sessions use `AVENTRA_JWT_SECRET` from the ignored backend `.env.local`.
Keep it stable across reloads and never commit or share its value. Changing the
key invalidates existing tokens: sign in once after a key change. HTTP 401 now
returns the main UI to sign-in instead of mislabeling a failed status request as
a missing external API key.
