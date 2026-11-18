# Real-data implementation: step 1

The supplied AVENTRA brief describes the long-term platform. This increment establishes a smaller, testable foundation for CRM/ERP/database analysis. It does not implement multi-tenant SaaS, external vendor write execution, natural-language agent planning, or vendor API authentication.

## Implemented workflow

Open `/workbench` on the local frontend. Sign in using an existing backend account, import CSV/JSON exports or an approved SQLite table, select an analysis, map columns, and inspect the actual model output and dataset hashes. Imported records persist in the backend database and are scoped to the authenticated **user**. User scoping is not organization/tenant isolation.

Four components are available:

1. Entity resolution: existing LightGBM artifact, actual imported query/target records, bounded candidate retrieval and country matching. Explicit mappings are required for ID, name, address, country. Up to 500 queries / 10,000 candidates per run. Sensitive links are recommendations, never automatically applied.
2. Semantic schema mapping: existing TF-IDF/reranking model using imported columns and samples. Datatype overrides are accepted by the API through `options.datatypes`. CSV values are strings unless types are supplied. This model's canonical concept vocabulary is still configured in YAML; adaptability does not mean that vocabularies or validation rules are removed.
3. Invoice reconciliation: deterministic financial validation over structured invoice, purchase-order and goods-receipt data. Each JSON array element must contain `invoice`, `purchase_order`, and `goods_receipt` objects following the existing Pydantic contracts. This is a rules component, not a trained predictor. Missing evidence, reference mismatch, quantity overbilling and arithmetic errors require review.
4. Historical anomaly analysis: an Isolation Forest fitted to the separately imported reference history, with no generated baseline. Requires 30 historical records and 5 distinct amounts. Fits log(amount), uses a 5% contamination assumption, and returns decision scores, not calibrated probabilities. A single common currency must be declared. This amount-only detector requires representative history and validation before operational use; it does not detect all forms of fraud.

This path never substitutes Apex, Zenith or another fixture for submitted data. API imports and analyses append provenance events to the backend ledger. Analysis results are currently returned directly; durable result-history storage is a later increment. Imports are snapshots of exports/tables, not continuously synchronized live systems.

## Start locally

```powershell
# Repository root
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Another terminal, frontend directory
npm run dev
```

Use an account already configured in the backend. The existing local seeder creates the development account `admin` with password `Password123!`; this is for local development only and must be replaced before a deployment. Browser access tokens stay in page memory and are not stored in local storage.

For SQLite imports, set `AVENTRA_DATA_ROOT` to a dedicated directory, then place permitted `.db`, `.sqlite` or `.sqlite3` files inside it. The default root is `data` relative to the backend working directory. Supply a relative path and table name. Only administrators can import database tables. Files open read-only; paths outside the configured root are rejected. Do not point the root at an unrestricted filesystem directory.

Import limits: 2 MB / 10,000 nonempty record objects, with valid JSON or a CSV with unique headers and consistent row lengths. Dataset metadata includes row count, columns, source domain, and SHA-256 digest.

## API contracts

- `POST /api/workbench/datasets`: `{name, domain: "CRM"|"ERP"|"DATABASE", format: "csv"|"json", content}`.
- `GET /api/workbench/datasets`: datasets owned by the authenticated user.
- `POST /api/workbench/database-import`: `{name, relative_path, table, domain}`; admin only.
- `POST /api/workbench/analyze`: `{task: "entities"|"schema"|"invoice"|"anomaly", dataset_id, candidate_dataset_id?, mapping?, candidate_mapping?, options?}`. Mapping dictionaries map canonical names to actual source columns. Anomaly analysis requires `options.currency`; reference history maps `amount` to its source column.

All workbench calls require the existing bearer authentication mechanism. Credentials are obtained from `POST /api/auth/login` using URL-encoded username/password.

## Safety changes in this increment

- Legacy `/api/agent/execute` and `/api/workflows/execute` now require authentication and return HTTP 409. Their simulator-based write execution is intentionally unavailable rather than silently substituting records. The conversational demo still runs locally; its former live execution path will report the restriction.
- Approval decisions require an authenticated permitted reviewer, a valid nonce, and the authenticated reviewer identity rather than a self-declared role.
- Backend audit verification now verifies the genesis payload/header as well as subsequent blocks.
- Financial tolerance applies only to price-variance flags. Missing PO/receipt, mismatched references, invalid line math and overbilling cannot fall through to tolerated reconciliation.

Other pre-existing legacy routes and connectors are not certified or comprehensively hardened by this increment. The old console still contains simulator adapters. Use the new workbench for this read-only real-data path. No production-readiness or tenant-isolation claim is made.

## Verification

Run new tests against a fresh isolated database:

```powershell
$env:DATABASE_URL = 'sqlite:///C:/absolute/path/to/workbench-test.db'
python -m pytest backend/tests/test_real_data_workbench.py -q
```

The tests check real local challenge-record matching, supplied-history anomaly scoring, authenticated owner isolation, rejected malformed CSV, real SQLite table reads, blocked path traversal, disabled legacy execution, unauthorized approvals, financial review gates and genesis tampering detection. They test correctness of the vertical slice, not representative business accuracy. Existing legacy agent tests will need replacement because the unsafe execution contract has been disabled.

## Next increments

2. Add organization isolation, durable analysis histories, import mapping versions, and a reviewed write-proposal contract.
3. Implement one actual CRM API and one actual ERP API using administrator-supplied credentials, explicit permissions, pagination, retries, idempotency and sandbox verification. No credentials have been supplied in this session.
4. Add a stateful orchestrator over registered tools with structured inputs, authenticated approvals and resumable execution. Do not reactivate the legacy canned agent.
5. Evaluate on held-out representative enterprise data, document provenance, and measure errors and latency. The earlier 500-query challenge sample is a limited benchmark, not production certification.

The hosted static prototype is not a hosted data-processing backend. This increment runs locally and has not been deployed as an authenticated cloud service.
