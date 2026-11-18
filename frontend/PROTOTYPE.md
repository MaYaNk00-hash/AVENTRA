# Aventra conversational prototype

Run `npm run dev` from `frontend`, then open http://localhost:3000. The existing enterprise console remains available at `/console`.

Private published preview: https://aventra-enterprise-copilot.glazedecho2.chatgpt.site (ChatGPT sign-in required). The hosted demo uses sample data; connect live functionality through a reachable backend configured at build time.

## Walkthrough

1. Choose **Onboard a customer**, then send the suggested request.
2. Watch the simulated model steps complete and select **Review action**.
3. Inspect the sample evidence, add a review note, and approve or decline.
4. Open **Audit trail** and select **Verify chain**. Demo decisions use Web Crypto SHA-256 hashes linked to previous blocks.
5. Try invoice reconciliation, schema drift, or financial anomaly investigation through the workspace or **Workflows**.
6. Open **Model library** to inspect all eight repository models and test an editable JSON example against the backend.

Demo runs, conversation history, and local audit blocks persist in this browser's local storage. They are sample data and do not update enterprise systems. The browser-local ledger demonstrates chaining; it is not a durable production audit service. Model cards show metrics reported in the repository configurations, not newly measured evaluations.

## Live backend

Start the existing backend from the repository root:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Choose **Live backend** in the composer or workspace settings. Requests use `NEXT_PUBLIC_API_URL`, defaulting to `http://localhost:8000`. Configure this public variable before building if deploying against another backend. Never put backend credentials in public environment variables.

The backend's current agent implementation routes all tasks through `run_customer_onboarding`. The new workspace therefore supports customer onboarding through the live agent and directs other tasks to model-level inference or the full console. It reads stored execution events and polls running executions, so synchronous backend events are not missed. Live approvals use actual ticket IDs and evidence; no sample evidence is substituted.

**Connections** and **Audit trail** read backend records in live mode. The approvals page lists workflows started in this workspace; the enterprise console exposes the complete backend approval queue. The displayed reviewer is the repository's prototype persona, not a new authentication layer.

## Verification and static export

```powershell
npx tsc --noEmit
npm run build
```

For a static demonstration build:

```powershell
$env:NEXT_OUTPUT_EXPORT = "true"
npm run build
Remove-Item Env:NEXT_OUTPUT_EXPORT
```

The static output is in `frontend/out`. Demo mode works without a backend. Hosted live mode requires a reachable backend with appropriate browser networking and CORS configuration.

Keyboard shortcuts: **Ctrl/Cmd K** searches pages, models, and conversations; **Alt N** starts a conversation; **Enter** sends; **Shift Enter** inserts a newline. Text attachments support TXT, CSV, JSON, and Markdown up to 50 KB, with a 12,000-character message limit. Demo evidence remains the labeled scenario fixture; uploaded text is not analyzed by the simulator.
