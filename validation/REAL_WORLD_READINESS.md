# Real-world readiness verification

Assessment date: 2 November 2026.

**Verdict: a working interactive prototype with some functional model inference, but not ready for arbitrary business data or production operations.** Passing the original eight example requests established that the APIs could execute those inputs. It did not establish business correctness, authorization enforcement, or accuracy on representative customer data.

## What was executed

- Existing ML/backend suite in a separate SQLite database: **54 passed, 5 failed** across 59 tests. The same CRM and ERP failures reproduced when each module ran separately with a fresh database.
- New reproducible behavioral checks: **20 passed, 20 failed** across 40 checks. These are deliberately selected correctness and safety cases, not an accuracy estimate.
- The existing LightGBM artifact was evaluated on **500 labeled source queries**, using the local challenge dataset, with **1,754 known match links** and **11,748 candidate records**.
- Mutating workflow and approval checks ran in a temporary database. No live external CRM/ERP account was used, no dataset was uploaded, and the application's main database was not used for these tests.
- Source review traced UI demo behavior, backend routing, model input handling, approval handling, and audit verification. No production business document collection or real connector account was supplied or tested.

## Labeled entity-matching result

The evaluation selected 500 source1 rows starting at offset 100,000. The candidate pool included all known true targets for these queries and 10,000 distractors from source2/source3. The existing `MultiKeyBlocker` retrieved up to 25 candidates per query, followed by the actual entity-resolution inference model and its top-10 output. Links with a score of at least 0.85 counted as predicted matches.

| Measurement | Observed result |
| --- | ---: |
| Correct predicted links | 1,594 |
| Incorrect predicted links | 0 |
| Missed true links | 160 |
| Link recall in this test | 90.9% |
| Observed link precision in this test | 100.0% |
| Blocking recall at 25 candidates | 96.8% |
| Positive-pair recall when the true candidate is supplied directly | 92.6% |

**Limits:** this is a bounded candidate-pool check against the repository's existing labeled challenge files, not a full-corpus production evaluation. Dataset provenance and absence of training overlap cannot be independently established from the artifact metadata. All true targets were intentionally available in the pool, and deployment prevalence, multilingual coverage, calibration, and false-positive rates at production scale remain unverified. Do not present the 100% observed precision as a production guarantee.

Artifact SHA-256: `1c7303332f8821191d3a536fc2f7b0e7c0635f557cbf562a5e5589f49b1afda0`.

## Confirmed blockers

| Area | Reproduction and observed behavior | Source |
| --- | --- | --- |
| Arbitrary customer input | Requesting Narmada Precision Tools Pvt Ltd in Gwalior created an execution containing **Zenith Dynamics Corp**, a San Francisco address, and predefined US identifiers. The requested customer details were not preserved. | `backend/agents/agent.py:59-77` |
| READ/WRITE boundary | `Inspect the audit ledger` was classified as `AUDIT_INSPECTION / READ`, but ran the onboarding engine and increased enterprise record count from **13 to 14** in the isolated database. | `backend/agents/agent.py:57-85` |
| Workflow routing | An invoice reconciliation request executed CRM ingestion and LightGBM entity resolution rather than the invoice pipeline. The frontend avoids this path for non-customer live tasks, but the backend route remains incorrect. | `backend/agents/agent.py:85` |
| Quantity overbilling | Billing 20 units against 10 received units produced `QUANTITY_OVERBILL`, but the final status was **RECONCILED_WITHIN_TOLERANCE** with **requires_human_approval=false**, because the unit-price variance was zero. | `ml/models/invoice_reconciliation/inference.py:51`; `features.py:44-57` |
| Incomplete invoice evidence | Missing PO, missing receipt, mismatched PO identifiers, and an inconsistent line product were accepted as reconciled in the checks. An unknown SKU and a stated-total mismatch could be treated as tolerated without approval. | `ml/models/invoice_reconciliation/features.py`; `inference.py` |
| Common invoice formats | A standard USD decimal-total example worked. `INR 11,800.00`, `₹11,800.00`, `EUR 1.234,56`, and an integer total failed to extract the expected amount. The INR invoice header also produced **OICE** as the invoice identifier. | `ml/models/document_intelligence/features.py:4-11` |
| Approval authorization | An HTTP request with **no authentication**, an **AUDITOR** role, and **no nonce** approved a pending action and completed the workflow in the temporary database. Reviewer identity and role are accepted from the request body rather than enforced through authentication on this route. | `backend/api/approvals.py:74-86`; `backend/workflows/engine.py:223-282` |
| Audit verification | Changing the genesis block's payload was still reported as valid. Changing the second block's payload was correctly detected. Genesis verification skips payload/header validation. | `backend/security/audit.py:66-69` |
| Planner coverage | Schema mapping and anomaly requests produced a generic CRM/audit graph without the corresponding schema/anomaly model tool. Customer and invoice graph checks passed. | `ml/models/workflow_planner/inference.py` |
| Guardrail coverage | A known `bypass approval` phrase was blocked. A paraphrase requesting the human authorization step be skipped was labeled `PASSED_GUARDRAILS`. The parser still marked authorization as required, so this alone does not prove engine-level gate bypass. | `ml/models/intent_parser/features.py` |

## Model and connector limitations

- Demo mode progresses on a client timer and displays scenario fixtures. Uploading a file into a demo conversation does not make the simulator analyze that file. This is labeled in the UI.
- Live inference does call the actual model implementations. That proves execution, not correctness for an arbitrary input distribution.
- Model `evaluate()` methods return configured metrics rather than recomputing them against the supplied data. UI metric cards are reported configuration values, not new measured evaluations.
- The anomaly model fits its Isolation Forest to randomly generated baseline samples in `load()`. It is not learning this enterprise's actual transaction history. Normal/extreme synthetic checks passed, but the reported anomaly precision/recall was not independently validated.
- The workflow engine directly instantiates the local Company A CRM and Company B ERP simulator connectors. Other generic CRM/ERP connectors use mock record lists. These checks do not demonstrate a live Salesforce, HubSpot, SAP, or NetSuite integration.
- The document parser is text/regex extraction with text-based PDF support. Scanned-image OCR, multilingual invoices, reliable currency parsing, and representative document-level accuracy are unverified.

## Existing-suite failures

The full suite failed the following tests; each failure also reproduced in its module-only run:

1. Salesforce read operations: expected seeded contact records were absent.
2. HubSpot read operations: expected company records were absent.
3. CRM governance/merge: the expected target record was absent after the operation.
4. ERP tolerated reconciliation: returned `RECONCILED_EXACT` instead of `RECONCILED_WITHIN_TOLERANCE`.
5. ERP extraction/reconciliation integration: returned `DISCREPANCY_APPROVAL_REQUIRED` for its nominal example.

These failures include fixture/integration issues and should not all be interpreted as independently measured model accuracy failures.

## Reproduce and inspect

From the repository root:

```powershell
python validation/check_real_world_readiness.py
```

The script creates an isolated temporary database, runs the targeted checks, reads the existing local labeled data, and writes `validation/results/real-world-readiness.json`. Exit code 1 is expected while any check fails. Running this assessment does not retrain or change model artifacts.

Artifacts:

- `validation/check_real_world_readiness.py`: executable checks and evaluation method.
- `validation/results/real-world-readiness.json`: per-case inputs/results, measured counts, and benchmark limits.
- `validation/results/baseline-tests.txt`: existing-suite output.
- `validation/results/crm-isolated-tests.txt` and `erp-isolated-tests.txt`: module-only reproduction output.

## Required before real business use

Prioritize authenticated, server-enforced approval permissions and READ/WRITE separation; then preserve structured user input and route each intent to the correct executor. Fix financial exception gating and audit genesis validation. Replace simulator connectors with verified integrations, add representative Indian/international invoice coverage, and evaluate on a held-out customer dataset with documented training provenance. Keep demo mode explicitly labeled until those checks pass.

This assessment added verification scripts and reports. It did not change application/model behavior or publish another UI version.
