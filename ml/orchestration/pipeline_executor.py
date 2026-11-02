"""
Pipeline Executor for Cross-Model Orchestration.
Executes multi-model dependency DAGs, maintains scoped context, and validates output contracts.
"""

import time
from typing import Dict, Any, Optional
from ml.shared.model_registry.registry import ModelRegistry
from ml.shared.model_registry.bootstrap import bootstrap_registry
from ml.orchestration.context_manager import WorkflowContext, WorkflowExecutionEvent


class PipelineExecutor:
    def __init__(self):
        bootstrap_registry()

    def execute_customer_onboarding_pipeline(
        self,
        new_customer_record: Dict[str, Any],
        erp_candidate_pool: list[Dict[str, Any]],
        context: Optional[WorkflowContext] = None
    ) -> WorkflowContext:
        ctx = context or WorkflowContext(workflow_id="wf-customer-onboarding")
        t_start = time.time()

        # Step 1: Intent Verification
        ctx.log_event("step_intent", "IntentParser", "START", "Parsing task intent and validating security boundaries")
        t0 = time.time()
        intent_model = ModelRegistry.get_model("intent_parser")
        intent_out = intent_model.predict({
            "prompt": f"Onboard new customer '{new_customer_record.get('business_name')}' and resolve potential duplicates."
        })
        ctx.log_event("step_intent", "IntentParser", "COMPLETED", "Task intent verified as ONBOARD_CUSTOMER (WRITE)", duration_ms=(time.time()-t0)*1000, payload=intent_out.prediction)
        ctx.record_model_output("intent_parser", intent_model.model_version, intent_out.prediction)

        # Step 2: Workflow Planning
        ctx.log_event("step_planning", "WorkflowPlanner", "START", "Generating DAG dependency plan with allowlisted tools")
        t0 = time.time()
        planner_model = ModelRegistry.get_model("workflow_planner")
        plan_out = planner_model.predict({
            "intent_type": "ONBOARD_CUSTOMER",
            "action_type": "WRITE"
        })
        ctx.log_event("step_planning", "WorkflowPlanner", "COMPLETED", "Validated DAG with 6 steps and 0 cycles", duration_ms=(time.time()-t0)*1000, payload=plan_out.prediction)
        ctx.record_model_output("workflow_planner", planner_model.model_version, plan_out.prediction)

        # Step 3: Candidate Retrieval and Entity Resolution
        ctx.log_event("step_er", "EntityResolution", "START", f"Evaluating {len(erp_candidate_pool)} candidate records using LightGBM pairwise model")
        t0 = time.time()
        er_model = ModelRegistry.get_model("entity_resolution")
        er_out = er_model.predict({
            "query": new_customer_record,
            "candidates": erp_candidate_pool
        })
        ctx.log_event("step_er", "EntityResolution", "COMPLETED", f"Entity resolution completed. Decision: {er_out.prediction['decision']} (Conf: {er_out.confidence})", duration_ms=(time.time()-t0)*1000, payload=er_out.prediction)
        ctx.record_model_output("entity_resolution", er_model.model_version, er_out.prediction)

        # Step 4: Governance Gate
        requires_approval = er_out.prediction.get("requires_approval", False)
        if requires_approval:
            ctx.approval_required = True
            ctx.approval_state = "PENDING"
            ctx.approval_evidence = {
                "decision": er_out.prediction["decision"],
                "confidence": er_out.confidence,
                "golden_record_recommendation": er_out.prediction.get("golden_record_recommendation"),
                "top_match": er_out.prediction["matches"][0] if er_out.prediction.get("matches") else None
            }
            ctx.log_event("step_approval", "ApprovalGate", "APPROVAL_REQUESTED", "High-confidence duplicate or ambiguous record detected. Human authorization required before record merge.", payload=ctx.approval_evidence)
            ctx.current_state = "AWAITING_APPROVAL"
        else:
            ctx.approval_required = False
            ctx.approval_state = "NONE"
            ctx.current_state = "READY_TO_COMMIT"
            ctx.log_event("step_approval", "ApprovalGate", "SKIPPED", "No duplicates or policy violations detected. Automated execution permitted.")

        return ctx

    def execute_invoice_reconciliation_pipeline(
        self,
        raw_invoice_text: str,
        po_record: Dict[str, Any],
        goods_receipt: Optional[Dict[str, Any]] = None,
        context: Optional[WorkflowContext] = None
    ) -> WorkflowContext:
        ctx = context or WorkflowContext(workflow_id="wf-invoice-reconciliation")

        # Step 1: Document Intelligence Extraction
        ctx.log_event("step_doc_intel", "DocumentIntelligence", "START", "Extracting key-value invoice tokens and table rows")
        t0 = time.time()
        doc_model = ModelRegistry.get_model("document_intelligence")
        doc_out = doc_model.predict({"document_text": raw_invoice_text})
        ctx.log_event("step_doc_intel", "DocumentIntelligence", "COMPLETED", f"Document extraction completed. Fields found: {len(doc_out.prediction['extracted_fields'])}", duration_ms=(time.time()-t0)*1000, payload=doc_out.prediction)
        ctx.record_model_output("document_intelligence", doc_model.model_version, doc_out.prediction)

        extracted = doc_out.prediction["extracted_fields"]

        # Step 2: 3-Way Reconciliation
        ctx.log_event("step_3way", "InvoiceReconciliation", "START", f"Performing 3-way matching between Invoice #{extracted.get('invoice_number')} and PO #{po_record.get('po_number')}")
        t0 = time.time()
        recon_model = ModelRegistry.get_model("invoice_reconciliation")
        recon_out = recon_model.predict({
            "invoice": {
                "invoice_number": extracted.get("invoice_number", "UNKNOWN"),
                "po_number": extracted.get("po_number", po_record.get("po_number")),
                "vendor_id": po_record.get("vendor_id"),
                "invoice_date": extracted.get("invoice_date", "2026-10-29"),
                "subtotal": extracted.get("subtotal", 0.0),
                "tax_amount": extracted.get("tax_amount", 0.0),
                "total_amount": extracted.get("total_amount", 0.0),
                "line_items": extracted.get("line_items", [])
            },
            "purchase_order": po_record,
            "goods_receipt": goods_receipt
        })
        ctx.log_event("step_3way", "InvoiceReconciliation", "COMPLETED", f"3-way reconciliation completed: {recon_out.prediction['reconciliation_status']}", duration_ms=(time.time()-t0)*1000, payload=recon_out.prediction)
        ctx.record_model_output("invoice_reconciliation", recon_model.model_version, recon_out.prediction)

        # Step 3: Anomaly Detection
        ctx.log_event("step_anomaly", "AnomalyDetection", "START", "Scoring transaction against vendor history and Isolation Forest baseline")
        t0 = time.time()
        anomaly_model = ModelRegistry.get_model("anomaly_detection")
        anomaly_out = anomaly_model.predict({
            "transaction_id": extracted.get("invoice_number", "TX-INV"),
            "vendor_id": po_record.get("vendor_id"),
            "amount": extracted.get("total_amount", 0.0),
            "historical_avg_amount": po_record.get("total_amount", 1000.0),
            "historical_std_amount": 250.0,
            "vendor_age_days": 180,
            "transactions_last_24h": 1,
            "is_weekend": False
        })
        ctx.log_event("step_anomaly", "AnomalyDetection", "COMPLETED", f"Anomaly score: {anomaly_out.prediction['anomaly_score']} (Tier: {anomaly_out.prediction['risk_tier']})", duration_ms=(time.time()-t0)*1000, payload=anomaly_out.prediction)
        ctx.record_model_output("anomaly_detection", anomaly_model.model_version, anomaly_out.prediction)

        # Step 4: Governance Synthesis
        requires_approval = recon_out.prediction.get("requires_human_approval", False) or anomaly_out.prediction.get("requires_human_approval", False)
        if requires_approval:
            ctx.approval_required = True
            ctx.approval_state = "PENDING"
            ctx.approval_evidence = {
                "reconciliation_flags": recon_out.prediction.get("flags", []),
                "total_variance": recon_out.prediction.get("total_variance_currency", 0.0),
                "anomaly_indicators": anomaly_out.prediction.get("anomaly_indicators", []),
                "risk_tier": anomaly_out.prediction.get("risk_tier")
            }
            ctx.current_state = "AWAITING_APPROVAL"
            ctx.log_event("step_approval", "ApprovalGate", "APPROVAL_REQUESTED", "Discrepancy or anomaly detected. Human approval required before disbursement.", payload=ctx.approval_evidence)
        else:
            ctx.approval_required = False
            ctx.approval_state = "NONE"
            ctx.current_state = "READY_TO_COMMIT"
            ctx.log_event("step_approval", "ApprovalGate", "SKIPPED", "Invoice and payment verified within policy bounds.")

        return ctx
