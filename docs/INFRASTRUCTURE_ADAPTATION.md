# Client-infrastructure adaptation

AVENTRA should adapt its configuration and plans to the client's systems. The client retains its CRM, ERP and operational databases. AVENTRA maintains control metadata: source scopes, observed schemas, reviewed mappings, feedback, configuration revisions and audit events.

The new infrastructure-profile path reads current client records directly. It does not require copying business records into the workbench's imported-dataset storage. CSV/JSON imports remain a separate optional evaluation path.

## Implemented increment

The local `/workbench` page now contains **Adapt to client infrastructure**, backed by `/api/adaptation`:

1. An authenticated administrator registers a SQLite source under `AVENTRA_DATA_ROOT`, an explicit table allowlist, and the client's own business concepts with datatype constraints. No customer names or table structures are predefined.
2. Discovery introspects scoped table columns, nullability, primary keys and foreign keys. It does not sample business values or activate permissions. The source is opened read-only.
3. A versioned proposal records the observed schema hash, changed tables, semantic mapping suggestions, and previously approved mapping feedback. The semantic mapper is initialized with the concepts supplied for that profile rather than the fixed global vocabulary.
4. The administrator inspects/corrects explicit mappings and approves or rejects the current revision. Authenticated identity is recorded. Stale schemas, stale revisions, duplicate canonical targets within a table, and incompatible field types prevent activation.
5. Reads use the approved revision and fetch current values directly from the client source. Only explicitly mapped fields and scoped tables are returned. Results identify the configuration revision and source schema hash.
6. A changed schema blocks reads until rediscovery and another review. Rediscovery reuses mappings supported by approved corrections when the original field and datatype still match. New and changed fields are proposed for review.

Schema drift is checked during explicit discovery and before every mapped read. There is no background watcher yet. A rejected revision remains rejected; registering a corrected profile or discovering a changed schema creates a new review path.

## What learning means here

Learning currently means persistent, source-scoped memory of approved field mappings. It survives API process restarts because it is stored in the application database. The next proposal explains whether a mapping came from semantic scoring or `APPROVED_FEEDBACK`.

It does **not** mean autonomous model-weight updates, permission expansion, source-code rewriting, or unsupported API invention. AVENTRA's business-operation contracts remain explicit. Model training from feedback requires a versioned dataset, held-out evaluation and model-release approval; that training pipeline is not implemented in this increment.

## API sequence

All calls require the existing bearer token.

- `POST /api/adaptation/profiles`: `{name, relative_path, allowed_tables, concepts}`. Each concept contains `name`, `description`, `compatible_types`.
- `POST /api/adaptation/profiles/{id}/discover`: observe current schema and propose a revision. Repeated discovery of an unchanged schema is idempotent.
- `POST /api/adaptation/profiles/{id}/decide`: `{revision, decision: "APPROVE" | "REJECT", mappings, comments}`. Mapping keys are `table.column` and values are client-defined concept names. Approval requires explicit reviewed mappings.
- `POST /api/adaptation/profiles/{id}/read`: `{table, limit}`. Limit is 1–1000. The active approved mapping must still match the current schema.
- `GET /api/adaptation/profiles`: profiles owned by the authenticated user, including proposal history and active configuration.

Scopes are currently per authenticated user, not per organization. Database credentials, remote database adapters, CRM/ERP OpenAPI discovery, continuous synchronization and multi-tenant isolation remain future work. Only SQLite source reads have been implemented and tested here. The existing generic CRM/ERP simulator adapters are not part of this verified path.

## Verification

Run with `DATABASE_URL` pointing to a fresh isolated test database:

```powershell
python -m pytest backend/tests/test_infrastructure_adaptation.py backend/tests/test_real_data_workbench.py -q
```

The combined suite covers 14 tests: direct reads reflecting client-side updates, schema drift blocking, correction reuse, stale approvals, source scopes, datatype enforcement, rejection, authentication/ownership, actual local dataset inference, actual SQLite reads and the earlier financial/audit safeguards. TypeScript checking also passes.

The next architectural step is an orchestrator that resolves business requests through these approved profiles and capabilities, followed by actual CRM/ERP read adapters. It must refuse unsupported actions and propose reviewed changes when the client's infrastructure evolves. No production accuracy, arbitrary-infrastructure compatibility, autonomous task completion or tenant-isolation claim is made by this increment.
