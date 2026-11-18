# AVENTRA isolated ML showcase

Run from the original repository root. No original application files are changed. The separate FastAPI app loads the original entity-resolution artifact read-only, plus four new local artifacts. Original Gemini orchestration is preserved unchanged in the original application. This showcase adds a separate optional provider adapter, never a replacement for a local prediction.

## Start and verify

```powershell
$env:SHOWCASE_MODE='true'
$env:LOCAL_ML_ENABLED='true'
$env:EXTERNAL_AI_ENABLED='false'
python -m uvicorn showcase.app:app --host 127.0.0.1 --port 8300
```

Open http://127.0.0.1:8300/ . No API keys are needed. The root page establishes an HTTP-only local session cookie used by POST endpoints. Keep this demonstration bound to loopback; it has no production authentication or tenant isolation. Reviewer identity is self-declared for simulated operations, not enterprise authorization.

```powershell
python -m showcase.core
python -m pytest showcase -q -p no:cacheprovider --disable-warnings
# Independent training/evaluation examples:
python -m showcase.models.invoice_discrepancy.train
python -m showcase.models.invoice_discrepancy.evaluation
```

Restart the showcase after retraining to load the new artifacts. Retraining overwrites only the new showcase artifacts and datasets. Each model has training, preprocessing, inference, evaluation, configuration, artifacts, tests and README files. Shared code lives in `core.py`; the models have independent estimators, version metadata and artifact directories. Changes to shared code should trigger evaluation for every affected model. Use only trusted local joblib artifacts.

## Artifact paths and evaluation

|Model|Artifact|Held-out results|
|---|---|---|
|Workflow intent|`models/workflow_intent/artifacts/model.joblib`|Accuracy 0.60; macro F1 0.58; 240 training / 60 test rows|
|Invoice discrepancy|`models/invoice_discrepancy/artifacts/model.joblib`|Accuracy 0.96; macro F1 0.9463; 1200 training / 400 test rows|
|Transaction anomaly|`models/transaction_anomaly/artifacts/model.joblib`|AUROC 1.0 on deliberate synthetic injections; normal false-positive rate 0.04286; 1050 normal training / 550 test rows|
|Email classification|`models/email_classification/artifacts/model.joblib`|Accuracy 0.90; macro F1 0.8933; 240 training / 60 test rows|
|Existing entity resolution|Original `ml/models/entity_resolution/artifacts/matching_lgb_model.pkl`|Loaded read-only; no new accuracy claim or retraining|

All NEW training data is explicitly **synthetic**, generated and persisted in each model's `dataset.json`. There are only 50 authored linguistic templates per text task, with six company/reference variants per template. Entire templates are held out; variants are correlated, so test rows are not 60 independent linguistic examples. Hyperparameters were fixed before the reported evaluation. Workflow payment approval has zero recall on this small held-out test: do not present the classifier as production-ready. New enterprise phrasing, real invoices and realistic anomaly prevalence need independent evaluation and better datasets. No existing datasets were reused or altered.

Invoice labels simulate adjudication with label noise; the high score reflects recovery of those synthetic patterns. Anomaly injections are deliberately easy, not real fraud labels. Raw Isolation Forest score_samples values are lower for more unusual observations; they are never fraud probabilities. Classifier probabilities are uncalibrated. Reports contain per-class metrics, confusion matrices, provenance, split details, and artifact/dataset hashes. TF-IDF, one-hot encoding and scaling fit on training only and are saved inside each pipeline.

## Judge demonstration

1. Confirm **External AI DISABLED** and all five actual load statuses at the top.
2. Select each model, replace the input with an unseen example, and run inference. Inspect actual input features, model ID/version/hash, latency and score. Inspect evaluation details and logs. The UI never supplies canned predictions.
3. Prepare a workflow: `Register a new customer account for Helix Instruments`. It uses local intent inference, a deterministic route mapping, actual SQLite retrieval of the isolated synthetic CRM/ERP records, and the original matching artifact.
4. Inspect the proposed route and all actual model outputs. Enter reviewer name and rationale; approve the simulated task. The backend atomically persists an operation and decision log. Repeated approval returns 409. Rejecting creates no operation.
5. For invoice/payment routes, provide the corresponding inference JSON in analysis inputs. The actual predicted category determines the analysis model; classification mistakes remain visible and must be rejected, not hidden. These workflows create review tasks only, never payments or messages.

Runtime storage: `showcase/runtime.sqlite` (records, workflows, simulated operations, persistent logs). `/api/records` exposes isolated synthetic client rows. It does not connect to live CRM/ERP accounts or alter the existing production workflow engine. This is a separate demonstration of the same sequence. SQLite records are retrieved through backend queries; no real vendor certification is claimed.

Endpoints: GET `/api/models`, `/api/records`, `/api/logs`; POST `/api/predict`, `/api/workflows`, `/api/workflows/{id}/decision`. Actual successful inference logs include model/version/hash, features, output and latency; workflow logs include route and per-model results. Failed requests return validation errors rather than fabricated predictions. Logs retain demonstration input data, so do not enter sensitive customer data.

## Optional provider

External calls require both `EXTERNAL_AI_ENABLED=true` and an explicit POST `/api/external`. Configure `AI_PROVIDER=google`, `AI_PROVIDER_API_KEY`, `AI_MODEL` in the backend environment. If the provider key is omitted, the adapter reads the existing `GEMINI_API_KEY` environment value without exposing it. `.env.example` is documentation, not automatically loaded. Other provider IDs fail explicitly until an adapter is implemented. This optional endpoint provides external explanation only; it does not execute workflows or replace local classifications. Every response identifies provider/model/component. Live provider access has not been verified here; local-only tests forbid network calls.

## Preservation and verification limits

`original_manifest.json` snapshots 232 preexisting project/artifact files before implementation. Tests compare their SHA-256 hashes. Generated caches, Git metadata, frontend build/dependency directories, virtual environments and the large raw `amazon_ml` dataset directory were excluded from this snapshot. No commands write to those original dataset paths. All implementation, training outputs and verification files are under `showcase/`.

Browser automation was unavailable because local browser use is disabled in Work settings. Backend tests and HTTP delivery checks are performed, but interactive visual QA must be completed manually before claiming full UI verification.
