Current UI: the Operations Console and explicit local inference work without an external API. Gemini is an optional helper. See PROTOTYPE_OPERATIONS.md for the latest behavior and complete passing-suite validation.

AVENTRA's main UI (`/` and `/agent`) and `/api/runtime/runs` now default to
Gemini language-to-tool planning. The backend still validates plans, retrieves
connected records, and requires human approval before writes. Explicit form
updates remain deterministic backend operations. Entity comparisons retain the
existing entity-resolution model. All ML code, datasets, artifacts, and the
separate local ML showcase remain available without retraining.

Set `GEMINI_API_KEY` in the root `.env.local` (ignored by Git), then restart the
backend. Keep `GEMINI_MODEL` set to a model available to your Google account.
Never put the key in frontend environment variables. A configured key alone does
not verify provider access; a successful live provider call is required.

The UI has no planner selector. Free-text tasks use the configured Gemini model;
explicit preview, summary, and form-update controls use deterministic backend
tools. API clients can explicitly request `"planner": "local"`. Provider failures
never silently fall back to local inference or another model.

Live verification now succeeds with `GEMINI_MODEL=gemini-3.5-flash-lite` and the
existing backend key. Previous 3.8 Flash structured-planning requests timed out.
The planner uses low thinking effort, a JSON MIME type plus JSON Schema, and bounded provider retries.

Actual backend runs returned 10 of 5,000 synthetic company records in 2119.57 ms
and summarized the dataset in 2010.59 ms. These are observed run durations, not
performance guarantees. Actual requests, results, and execution events are in
`validation/results/gemini-live-verification-1793642405.json`.

Overview's **Verify API connection** calls authenticated POST
`/api/runtime/planner/verify`. It checks a real structured provider response using
generic test metadata, executes no enterprise tools, sends no client rows, and
records the result in the audit ledger. GET `/api/runtime/planner` reports the
latest real check in this backend process; status resets on restart or when the
configured model/key changes. Provider failures remain visible.

Validation (provider responses are mocked; client retrieval uses real local HTTP
and SQLite):

```powershell
$env:DATABASE_URL='sqlite:///./validation/results/gemini-default-tests.db'
python -m pytest backend/tests/test_gemini_planner.py backend/tests/test_adaptive_runtime.py -q
```
