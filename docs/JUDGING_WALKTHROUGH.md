# AVENTRA: live agent prototype for judging

This version replaces the root page with a working, evidence-based tool runtime. The suggestions on the welcome screen fill a request; they do not supply an answer. Requests read the current client sources, invoke the matching model when requested, persist the run, and display actual tool evidence. Update proposals wait for review, execute once, then re-read the source to verify the saved values.

## Start the local presentation

Install the repository's existing Python/frontend dependencies if needed. Use three terminals:

```powershell
# Terminal 1 — repository root: independent editable client application
python -m uvicorn prototype_client.app:app --host 127.0.0.1 --port 8100

# Terminal 2 — repository root: Aventra control plane and agent runtime
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Terminal 3 — frontend directory
npm run build
npm run start -- --hostname 127.0.0.1
```

Prepare the local sample connections from the repository root:

```powershell
python infrastructure/scripts/prepare_judging.py --approve-local-sandbox
```

This explicit setup action approves only the repository's **local sample sandbox**. It creates three connections: a CRM HTTP collection, an ERP HTTP collection, and a direct SQLite operations table. It does not grant permissions to a remote enterprise. You can review the saved scopes through the connection buttons in the agent sidebar.

The setup script uses `AVENTRA_DEMO_USERNAME` and `AVENTRA_DEMO_PASSWORD`, falling back to the seeded local development account `admin` / `Password123!`. Replace development credentials before any deployment. Secrets are never printed by the setup script. Set these environment variables locally if you changed the account.

Open:

- Agent: http://127.0.0.1:3000/agent (also the default `/` page).
- Separate client website: http://127.0.0.1:8100.
- Infrastructure workbench: http://127.0.0.1:3000/workbench.

## Five-minute proof that the output is not prewritten

1. Sign in to the agent using your local backend account. The three sample sources should be checked in the sidebar.
2. Open the **client website** in a second tab. Ask a judge to choose a record and change its `registered_title`, `postal_location`, or `review_state` using the site's edit form. These changes are written into the separate client SQLite database.
3. Ask Aventra to **Show all records across the connected systems**. Expand each evidence collection. Confirm that the judge's changed value appears in the CRM response. The operations data is read directly from a database; the CRM and ERP data come from HTTP calls.
4. Ask **Compare connected resources and find duplicate businesses**. The LightGBM entity-resolution model scores the actual retrieved names/addresses. Candidate results can change if the judge edits the records; a high score is a model score, not a proof of legal identity or a calibrated accuracy guarantee.
5. From a retrieved row, select **Propose update**. Choose an explicitly writable field and enter a JSON scalar, for example `"reviewed-by-finance"`. Aventra reads the record again and displays the exact before/after proposal. Nothing has changed yet.
6. Enter review remarks and select **Approve & verify update**. Aventra submits the permitted change, reads the source again and displays the verified client record. Refresh the independent client website to confirm the same value there.
7. For a negative test, create a proposal, edit that same record directly in the client website, then approve the old proposal. Aventra must fail the stale preview rather than overwrite the newer client state.
8. Ask **Summarize the connected systems**. Counts and numeric field summaries are computed from current records. Numeric totals retain source units; currency compatibility is not inferred.

The sample business records are initial editable fixtures. Neither agent responses nor model scores are fixtures. The client application never stores canned agent answers.

## Connecting an existing client website with minimal changes

### Existing OpenAPI 3 API

If the client website already exposes a compatible API, no client frontend code change is required:

1. Add its exact origin to the server's comma-separated `AVENTRA_ALLOWED_ORIGINS`, then restart the backend. The prototype defaults to allowing only `http://127.0.0.1:8100`.
2. Put its bearer credential in a server environment variable beginning with `AVENTRA_CONNECTOR_`. Do not enter the secret into the UI. The connection stores only the variable's reference.
3. Select **Connect system**, enter the API base URL, OpenAPI document path, system role and optional credential reference.
4. Aventra discovers supported collection resources and fields from the document. It proposes entity-role bindings using schema metadata and remembers previously approved bindings. Select actual record keys, correct the bindings, and approve only the resources and writable fields the client permits.
5. Run tasks against the approved resources. A changed schema blocks execution until rediscovery and approval.

**Current API compatibility:** OpenAPI 3, internal schema references, flat JSON row collections, either top-level arrays or an object containing one array. Item PATCH operations must declare native `If-Match` support and have an item GET returning an ETag, or implement the documented hash-precondition bridge contract. An item path must be the collection path followed by one path parameter. OAuth login flows, arbitrary response transformations, nested entity models, pagination and multipart files are not implemented. Collections are capped at 500 rows / 2 MB, and matching at 25,000 candidate pairs per resource pair; the runtime refuses an oversized response rather than silently claiming complete results.

Normal HTML does not reveal a website's database schema or grant permission to manipulate records. AVENTRA cannot safely connect to **every website** from a URL alone. Sites without a compatible API need a permitted adapter, database bridge, or a future authorized browser connector. No CAPTCHA bypass or unrestricted browser automation is included.

### Configuration-only client-side database bridge

When the client owns its database but has no suitable API, deploy the included small sidecar next to its infrastructure. The existing website can remain unchanged. Configure an approved database account, table allowlist, bearer token and optional writable fields; the bridge introspects actual table columns. It does not create or alter the client's table schemas.

Example environment setup (substitute the client's actual values locally; never commit secrets):

```powershell
$env:AVENTRA_BRIDGE_DATABASE_URL = '<SQLAlchemy database connection URL>'
$env:AVENTRA_BRIDGE_TABLES = '<permitted-table>,<another-permitted-table>'
$env:AVENTRA_BRIDGE_TOKEN = '<client-scoped bearer token>'
$env:AVENTRA_BRIDGE_WRITES = '<JSON object mapping permitted tables to writable-column arrays>'
python -m uvicorn infrastructure.bridge.app:app --host 127.0.0.1 --port 8200
```

The bridge is read-only unless `AVENTRA_BRIDGE_WRITES` grants fields. Store the same token on the Aventra server under an `AVENTRA_CONNECTOR_...` variable, allow the bridge's exact origin, then connect its `/openapi.json` through the UI. The bearer credential is required for discovery and every data operation. Do not expose the bridge publicly without the client's transport security/network controls.

The bridge uses SQLAlchemy so compatible database drivers can be configured without rewriting the client's website. **SQLite execution is tested here. PostgreSQL/MySQL deployment has not been verified against a live server in this session**, and still requires the appropriate driver, account privileges, networking, supported types and integration tests. Only single-column primary keys and flat scalar updates are supported. Database constraints remain authoritative.

## How the agent works today

- Planner: choose local constrained tools or the optional Gemini language-to-tool planner. Gemini proposes one supported action using the user's request and the approved source/field metadata; retrieved rows and connector credentials are excluded from its context. Server validation remains authoritative. This is bounded planning, not an unrestricted agent loop.
- Retrieval: actual client HTTP calls or parameterized database reads, with source IDs, schema hashes and response hashes recorded in persistent run events.
- Matching: the existing LightGBM artifact receives records translated through approved semantic role bindings. Physical client table/column names are not hardcoded into the runtime. Stable model roles such as name/address are tool contracts, not a required client database layout.
- Automation: a selected actual record and exact field values define a write proposal. Arbitrary destructive operations, payments, emails, unsupported tools and unspecified mutations are refused. Writes never happen from a model's recommendation alone.
- Approvals: authenticated, role-checked, owner-scoped, single-claim run decisions. A record/schema snapshot is rechecked before execution.
- Verification: conditional client PATCH or a database compare-and-swap update, followed by a fresh read. A network/verification failure after a possible mutation is marked `RECONCILIATION_REQUIRED`; no automatic retry is attempted.
- Learning: approved source bindings are retained and proposed on rediscovery, alongside the previously implemented infrastructure-profile feedback memory. Autonomous model retraining is not implemented.

Runs and source configuration persist in the existing backend control database. Business data stays in client systems, but **evidence snapshots are stored with runs** for verification/history; this is a deliberate data-retention boundary that needs a client retention policy before production.

## Verification performed

The focused suite consists of 37 tests:

```powershell
# Use a fresh isolated DATABASE_URL, as described in REAL_DATA_IMPLEMENTATION.md.
python -m pytest backend/tests/test_gemini_planner.py backend/tests/test_adaptive_runtime.py backend/tests/test_client_bridge.py backend/tests/test_real_data_workbench.py backend/tests/test_infrastructure_adaptation.py -q
```

Twelve runtime tests use a separate actual HTTP service and SQLite tables with different field names from the presentation data. Gemini transport/plans are mocked in tests; the underlying HTTP/DB reads and existing model execution are real. Eight provider contract cases verify schema output, failure handling, configuration and metadata-only context. Three bridge tests verify actual writes and safeguards; the other 14 cover earlier data/adaptation safeguards. Earlier browser testing verified retrieval, actual model matching, approval, PATCH execution and source re-read verification. Live Gemini quality and account access require an actual configured key and are not verified by mocked tests.

This is a local prototype, not a production multi-tenant agent. Cross-user approval delegation, organization isolation, multi-worker job recovery, unrestricted multi-step planning, automatic retraining, pagination, comprehensive compliance hardening and live vendor-account certification remain outside this verified scope. Existing legacy simulator routes are not certified by these tests.

The older hosted static Site is not this live backend. Present the local agent and independent client together; do not describe the old hosted landing prototype as a deployed production agent.

Authentication no longer uses the repository's fixed JWT signing key. Set AVENTRA_JWT_SECRET to a strong secret of at least 32 characters for stable sessions across restarts/workers. Without it, the local process generates an ephemeral signing key and users must sign in again after a backend restart.

The request box also supports grounded update commands: `Set ACTUAL_FIELD = "value" for ACTUAL_RECORD_KEY`. The runtime searches its retrieved evidence for exactly one matching record and approved field; ambiguous or unsupported commands fail without a write. This is a constrained command grammar, not general LLM language understanding.

## Optional Gemini language planning

Save `GEMINI_API_KEY=your-key` in the root `.env.local` (ignored by Git), then start/restart the backend. It automatically loads this file; existing process environment variables take precedence. Never put a live key in `.env.example`, frontend variables, source control or chat. The example file is never loaded as runtime configuration.

```powershell
# Supply GEMINI_API_KEY securely in this terminal before starting the backend.
$env:GEMINI_MODEL = 'gemini-3.8-flash'
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Sign in again after restarting, then select **Gemini** in the request box. Without `GEMINI_API_KEY`, the choice is disabled. Configured status means the environment contains a key, not that Google has accepted it. The first real run validates account/model availability; errors persist as failed runs with no silent fallback.

Supported examples: “Can you locate Narmada for me?”, “Give me a numerical overview of these systems”, or “Please change review_state to reviewed for C-101”. Updates require an exact record key in the request, a uniquely identifiable approved resource and permitted fields. They prepare a proposal and require human approval. Complex filters, arbitrary answers about records, multi-step workflows and identifying a write target by business name alone are not implemented.

Choosing Gemini sends the request text and approved schema metadata to Google; don't include secrets in the request. Full retrieved client rows remain in the backend. Gemini translates language; actual totals, returned records and matching scores still come from existing backend tools. See [Google's structured output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) for the REST contract used here. Model access depends on the configured Google account.
