The main task view is now an **Operations Console**, with explicit Browse,
Summarize, and Compare controls. These invoke authenticated backend tools and do
not require Gemini. Search terms, result limits, sampling, selected sources, and
the execution route are saved with each run. Propose Update remains available
on retrieved evidence rows and still requires human review before a write.

The free-text Gemini composer is inside **Optional: describe a request with
Gemini**. Provider errors remain visible; an AI request is never silently
replaced with a model prediction, another provider, or a hardcoded answer.
ML Intelligence similarly offers **Run local inference** as the primary explicit
control and **Ask Gemini to select a tool** as an optional action.

Gemini generation retries at most three times for temporary connection errors,
timeouts, and HTTP 429/500/502/503/504. Backoff is bounded; long Retry-After values
return an error. Credential/permission errors are not retried. Only plan
generation is retried: enterprise writes are never automatically repeated by
this retry helper. Provider attempt counts are recorded in execution metadata.
An external provider's uptime, quota, or accuracy cannot be guaranteed.

For this local prototype, `.env.local` enables
`AVENTRA_LOCAL_SANDBOX_ENABLED=true`. The backend supervises the repository's
client service on localhost:8100, using the existing judging-client database.
It restarts its own failed child and can start it when no listener is present.
It never terminates an existing unrelated listener, replaces the dataset, or
starts a remote client. Supervision stops with the backend. Production defaults
remain off. Actual child-process logs use unique names under
`validation/runtime-logs/`.

Comparisons batch existing artifact inference in groups of 100 candidates.
Resource combinations larger than 25,000 possible pairs use a deterministic
lexical shortlist of up to ten candidates per query, with cutoff 60. The actual
matching score still comes from the saved LightGBM artifact. Results disclose
possible/scored pair counts and shortlisting; they are not exhaustive identity
resolution. A run is bounded to 50,000 scored pairs.

The run-history UI uses `GET /api/runtime/runs?compact=true`, which omits large
evidence payloads. Opening a run fetches its complete saved evidence and approval
diff before enabling interaction. The original full-detail API remains
available. Four older failing tests were corrected through explicit test-only
CRM fixtures and checks for the intentionally disabled legacy agent endpoint;
authentication was not weakened. The legacy merge implementation was also
hardened against missing records, unauthorized roles, and approval replay.

Validation:

- Complete backend suite: **110 passed**. Isolated database used; no production
  fixtures were fabricated or replaced.
- Standalone TypeScript check and production frontend build passed.
- Live explicit Browse and Summary processed 5,228 source/aggregate rows across
  seven resources, without an external AI call.
- Live comparison scored 20,984 candidate pairs and returned 15 candidate links
  for review, with shortlisting disclosed.
- Eight explicit local artifact checks passed.
- Eight genuine Gemini-to-local-artifact checks passed again.
- No trained artifact was retrained or written by these changes.

Actual observed execution reports:

- `validation/results/operations-console-live-1793646087.json`
- `validation/results/local-only-all-models-1793646390.json`
- `validation/results/hybrid-live-20261102T190320Z-6334e385.json`

These checks establish the tested behavior, not correctness for arbitrary
enterprise requests or every possible input. Unsupported operations such as
real payments, messaging, deletion, and unrestricted record creation remain
explicitly unsupported. Browser visual verification was previously blocked by
the computer-use tool's URL-confidence check; build and API checks do not replace
that visual verification.
