Current UI: provider-independent Operations Console plus optional Gemini assistance. All 110 backend tests now pass; prior failure counts below are historical. See PROTOTYPE_OPERATIONS.md.

The AVENTRA home page and `/agent` provide five connected views:

- Overview: owner-scoped database totals, recent runs, and configuration readiness.
- Task workspace: API-assisted requests, source records, comparison scores, numeric summaries, input/output metadata, JSON evidence export, and exact approval diffs.
- Connections: discovered capabilities, approved grants, explicit schema reachability checks, and access review.
- Approvals: every pending proposal owned by the signed-in user, including proposals older than the recent history window.
- Activity: search and status filters over the latest 30 saved runs. Opening a run refreshes its state from the backend.

Start all three local services from the project root:

```powershell
powershell -File infrastructure/scripts/start_local_workspace.ps1
```

The launcher preserves existing listeners and checks HTTP readiness. Background
service logs are under `validation/runtime-logs`. Stop only the processes you
started when finished. Use the normal backend `.env.local` for server credentials;
the UI has no provider selector or credential input. Trained artifacts are not
retrained by the launcher.

An approved connection is an access grant. The Connections check reports actual
schema reachability and whether the approved schema still matches. Data reads,
write permissions, and concurrency checks run during task execution. Provider key
configuration does not prove external API connectivity.

For a review demonstration, open a result's evidence table, select a permitted
field with **Propose update**, enter a JSON scalar, and prepare the proposal.
Open **Approvals**, inspect the exact diff, enter a rationale, then approve or
reject it. Approval performs backend permission and stale-data checks before a
conditional write and verifies the resulting client record.

Validation for this change: production frontend build and standalone TypeScript
check passed; 43 targeted integration/regression tests passed. The complete
backend suite reported 81 passed and six failures in older agent, CRM fixture,
and ERP reconciliation expectations. Live authenticated overview, approval queue,
and all three configured connection checks returned HTTP 200. External Gemini
access has now been verified using gemini-3.5-flash-lite; see GEMINI_DEFAULT.md. Visual browser verification stopped because the
computer-use tool could not confidently determine the browser URL.
