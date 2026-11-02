"""
AVENTRA Enterprise Workflow Execution Engine.
Executes React-Flow compatible DAGs, manages approval gates, idempotency,
and real-time Server-Sent Events (SSE) telemetry.
"""

import time
import uuid
import secrets
import asyncio
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.database.models import WorkflowDefinition, WorkflowExecution, ApprovalRequest
from backend.database.session import SessionLocal
from backend.connectors.company_a_crm import CompanyACRMConnector
from backend.connectors.company_b_erp import CompanyBERPConnector
from backend.security.audit import append_audit_entry
from ml.shared.model_registry.registry import ModelRegistry
from ml.shared.model_registry.bootstrap import bootstrap_registry

# Global in-memory broadcast bus for real-time SSE streaming: execution_id -> list of asyncio.Queue
EXECUTION_SUBSCRIBERS: Dict[str, List[asyncio.Queue]] = {}
EXECUTION_EVENT_LOGS: Dict[str, List[Dict[str, Any]]] = {}


def broadcast_event(execution_id: str, event: Dict[str, Any]):
    if execution_id not in EXECUTION_EVENT_LOGS:
        EXECUTION_EVENT_LOGS[execution_id] = []
    EXECUTION_EVENT_LOGS[execution_id].append(event)

    queues = EXECUTION_SUBSCRIBERS.get(execution_id, [])
    for q in queues:
        try:
            q.put_nowait(event)
        except Exception:
            pass


async def subscribe_execution_events(execution_id: str):
    q = asyncio.Queue()
    if execution_id not in EXECUTION_SUBSCRIBERS:
        EXECUTION_SUBSCRIBERS[execution_id] = []
    EXECUTION_SUBSCRIBERS[execution_id].append(q)

    # Immediately replay existing events
    for existing_evt in EXECUTION_EVENT_LOGS.get(execution_id, []):
        await q.put(existing_evt)

    try:
        while True:
            evt = await q.get()
            yield evt
            if evt.get("status") in ["COMPLETED", "FAILED", "AWAITING_APPROVAL"]:
                # Keep connection alive briefly, then finish
                if evt.get("status") in ["COMPLETED", "FAILED"]:
                    break
    finally:
        if execution_id in EXECUTION_SUBSCRIBERS and q in EXECUTION_SUBSCRIBERS[execution_id]:
            EXECUTION_SUBSCRIBERS[execution_id].remove(q)


class WorkflowExecutionEngine:
    def __init__(self, db: Session):
        self.db = db
        bootstrap_registry()

    def create_execution(self, workflow_id: str, triggered_by: str, input_data: Dict[str, Any]) -> WorkflowExecution:
        wf = self.db.query(WorkflowDefinition).filter(WorkflowDefinition.id == workflow_id).first()
        if not wf:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        execution = WorkflowExecution(
            workflow_id=workflow_id,
            triggered_by=triggered_by,
            status="PENDING",
            current_step="INITIALIZING",
            input_data=input_data,
            output_data={},
            context_data={},
            execution_events=[]
        )
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        return execution

    def log_and_broadcast(
        self,
        execution: WorkflowExecution,
        step_id: str,
        component: str,
        event_type: str,
        message: str,
        duration_ms: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        evt = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime()) + f"{int(time.time()*1000)%1000:03d}Z",
            "step_id": step_id,
            "component": component,
            "event_type": event_type,
            "message": message,
            "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
            "payload": payload or {}
        }
        events = list(execution.execution_events or [])
        events.append(evt)
        execution.execution_events = events
        self.db.commit()

        broadcast_event(execution.id, evt)
        return evt

    def run_customer_onboarding(self, execution_id: str) -> Dict[str, Any]:
        execution = self.db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        execution.status = "RUNNING"
        self.db.commit()
        t0_total = time.time()

        crm = CompanyACRMConnector(self.db)
        erp = CompanyBERPConnector(self.db)

        try:
            # 1. CRM Input Ingestion
            t0 = time.time()
            self.log_and_broadcast(execution, "n1", "CRM Submission Trigger", "STARTED", "Received enterprise customer registration payload")
            input_rec = execution.input_data.get("record", {
                "business_name": "Apex Global Logistics LLC",
                "business_address": "742 Evergreen Terrace, Springfield, IL 62704",
                "country": "US",
                "federal_tax_id": "US-EIN-8829104",
                "contact_email": "operations@apexlogistic.com"
            })
            time.sleep(0.1) # Realistic IO latency
            self.log_and_broadcast(execution, "n1", "CRM Submission Trigger", "COMPLETED", f"Ingested prospective record for '{input_rec['business_name']}'", (time.time()-t0)*1000)

            # 2. ERP Candidate Retrieval
            t0 = time.time()
            self.log_and_broadcast(execution, "n2", "ERP Candidate Retrieval", "STARTED", "Querying Company B ERP vendor pool for candidate blocking")
            erp_vendors = erp.list_vendors()
            time.sleep(0.12)
            self.log_and_broadcast(execution, "n2", "ERP Candidate Retrieval", "COMPLETED", f"Retrieved {len(erp_vendors)} existing enterprise vendor records across active systems", (time.time()-t0)*1000)

            # 3. LightGBM Entity Resolution
            t0 = time.time()
            self.log_and_broadcast(execution, "n3", "LightGBM Entity Resolution", "STARTED", "Evaluating 16-feature pairwise lexical/address interaction vectors")
            er_model = ModelRegistry.get_model("entity_resolution")
            er_out = er_model.predict({
                "query": {
                    "entity_id": "NEW-PROSPECT",
                    "business_name": input_rec["business_name"],
                    "business_address": input_rec.get("business_address", ""),
                    "country": input_rec.get("country", "US"),
                    "source_system": "COMPANY_A_CRM"
                },
                "candidates": [
                    {
                        "entity_id": v["vendor_id"],
                        "business_name": v["business_name"],
                        "business_address": v.get("business_address", ""),
                        "country": v.get("country", "US"),
                        "source_system": "COMPANY_B_ERP"
                    }
                    for v in erp_vendors
                ]
            })
            pred = er_out.prediction
            top_prob = er_out.confidence
            self.log_and_broadcast(
                execution, "n3", "LightGBM Entity Resolution", "COMPLETED",
                f"Model score: {top_prob:.3f} | Decision: {pred['decision']}",
                (time.time()-t0)*1000,
                {"matches": pred["matches"][:3], "recommendation": pred.get("golden_record_recommendation")}
            )

            # 4. Governance Approval Gate
            requires_approval = pred.get("requires_approval", False)
            if requires_approval:
                nonce = secrets.token_hex(32)
                appr_req = ApprovalRequest(
                    execution_id=execution.id,
                    step_id="n4",
                    action_type="MERGE_ENTERPRISE_IDENTITY",
                    risk_level="HIGH" if top_prob > 0.80 else "MEDIUM",
                    confidence_score=top_prob,
                    evidence={
                        "decision": pred["decision"],
                        "confidence": top_prob,
                        "prospect": input_rec,
                        "golden_record_recommendation": pred.get("golden_record_recommendation"),
                        "candidate_evidence": pred["matches"][0] if pred.get("matches") else None
                    },
                    status="PENDING",
                    nonce_token=nonce
                )
                self.db.add(appr_req)
                execution.status = "AWAITING_APPROVAL"
                execution.current_step = "n4"
                self.db.commit()

                self.log_and_broadcast(
                    execution, "n4", "Governance Approval Gate", "APPROVAL_REQUESTED",
                    f"Duplicate identified (Score: {top_prob:.1%}). Pausing automated execution. Awaiting Human-in-the-Loop review.",
                    payload={"approval_request_id": appr_req.id, "risk_level": appr_req.risk_level, "evidence": appr_req.evidence}
                )
                return {"status": "AWAITING_APPROVAL", "execution_id": execution.id, "approval_id": appr_req.id}

            # If no duplicate, proceed to commit directly
            return self._complete_onboarding(execution, input_rec, None, t0_total)

        except Exception as e:
            execution.status = "FAILED"
            execution.error_details = str(e)
            self.db.commit()
            self.log_and_broadcast(execution, "error", "ExecutionEngine", "FAILED", f"Error during workflow: {str(e)}")
            return {"status": "FAILED", "error": str(e)}

    def resume_after_approval(
        self,
        approval_id: str,
        approved_by: str,
        user_role: str,
        decision: str,  # "APPROVED" or "REJECTED"
        comments: str
    ) -> Dict[str, Any]:
        appr_req = self.db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not appr_req:
            raise ValueError(f"Approval request '{approval_id}' not found.")

        if appr_req.status != "PENDING":
            raise ValueError(f"Approval request already resolved with status: {appr_req.status}")

        execution = self.db.query(WorkflowExecution).filter(WorkflowExecution.id == appr_req.execution_id).first()
        if not execution:
            raise ValueError("Associated execution not found")

        # Update approval request
        appr_req.status = decision
        appr_req.reviewed_by = approved_by
        appr_req.reviewer_comments = comments
        appr_req.reviewed_at = datetime.datetime.utcnow()
        self.db.commit()

        if decision == "REJECTED":
            execution.status = "REJECTED"
            execution.completed_at = datetime.datetime.utcnow()
            self.db.commit()
            self.log_and_broadcast(
                execution, "n4", "Governance Approval Gate", "REJECTED",
                f"Action rejected by {user_role} ({approved_by}): {comments}",
                payload={"reviewer": approved_by, "comments": comments}
            )
            # Record rejection in audit ledger
            append_audit_entry(
                self.db,
                actor_id=approved_by,
                actor_role=user_role,
                action_type="APPROVAL_REJECTED",
                entity_type="WORKFLOW_EXECUTION",
                entity_id=execution.id,
                details={"comments": comments, "evidence": appr_req.evidence}
            )
            return {"status": "REJECTED", "execution_id": execution.id}

        # Decision is APPROVED -> Resume execution
        self.log_and_broadcast(
            execution, "n4", "Governance Approval Gate", "APPROVED",
            f"Authorized by {user_role} ({approved_by}). Remarks: '{comments}'. Resuming execution.",
            payload={"reviewer": approved_by, "comments": comments}
        )

        input_rec = execution.input_data.get("record", {})
        golden_info = appr_req.evidence.get("golden_record_recommendation")
        return self._complete_onboarding(execution, input_rec, golden_info, time.time() - (execution.duration_ms / 1000))

    def _complete_onboarding(
        self,
        execution: WorkflowExecution,
        input_rec: Dict[str, Any],
        golden_info: Optional[Dict[str, Any]],
        t0_total: float
    ) -> Dict[str, Any]:
        crm = CompanyACRMConnector(self.db)
        erp = CompanyBERPConnector(self.db)

        # 5. Enterprise Record Commit
        t0 = time.time()
        self.log_and_broadcast(execution, "n5", "Enterprise Record Commit", "STARTED", "Writing verified records to Company A CRM and linking with ERP master")
        time.sleep(0.1)

        crm_res = crm.create_account({
            "account_name": input_rec["business_name"],
            "street_address": input_rec.get("business_address", ""),
            "country": input_rec.get("country", "US"),
            "federal_tax_id": input_rec.get("federal_tax_id"),
            "primary_email": input_rec.get("contact_email")
        })

        canonical_id = f"CANON-{uuid.uuid4().hex[:6].upper()}"
        if golden_info and golden_info.get("linked_entity_id"):
            erp_id = golden_info["linked_entity_id"]
            erp.link_golden_record(canonical_id, erp_id, crm_res["account_id"])
            action_desc = f"Created CRM record {crm_res['account_id']} and linked to ERP vendor {erp_id} as Golden Entity '{canonical_id}'"
        else:
            action_desc = f"Created standalone CRM record {crm_res['account_id']}"

        self.log_and_broadcast(execution, "n5", "Enterprise Record Commit", "COMPLETED", action_desc, (time.time()-t0)*1000, {"crm_id": crm_res["account_id"], "canonical_id": canonical_id})

        # 6. Cryptographic Audit Ledger Entry
        t0 = time.time()
        self.log_and_broadcast(execution, "n6", "Tamper-Evident Ledger", "STARTED", "Hashing execution payload and appending to SHA-256 chained ledger")
        audit_entry = append_audit_entry(
            self.db,
            actor_id=execution.triggered_by,
            actor_role="OPERATIONS",
            action_type="ENTERPRISE_CUSTOMER_ONBOARDED",
            entity_type="ENTERPRISE_RECORD",
            entity_id=canonical_id,
            details={
                "execution_id": execution.id,
                "workflow_id": execution.workflow_id,
                "crm_account_id": crm_res["account_id"],
                "canonical_id": canonical_id,
                "business_name": input_rec["business_name"],
                "golden_linkage": golden_info
            }
        )
        self.log_and_broadcast(
            execution, "n6", "Tamper-Evident Ledger", "COMPLETED",
            f"Audit Block #{audit_entry.id} sealed. Hash: {audit_entry.current_hash[:16]}...",
            (time.time()-t0)*1000,
            {"block_id": audit_entry.id, "hash": audit_entry.current_hash, "prev_hash": audit_entry.prev_hash}
        )

        total_ms = (time.time() - t0_total) * 1000
        execution.status = "COMPLETED"
        execution.completed_at = datetime.datetime.utcnow()
        execution.duration_ms = total_ms
        execution.output_data = {
            "canonical_id": canonical_id,
            "crm_id": crm_res["account_id"],
            "audit_block_id": audit_entry.id,
            "audit_hash": audit_entry.current_hash
        }
        self.db.commit()

        self.log_and_broadcast(execution, "completed", "ExecutionEngine", "COMPLETED", f"Workflow successfully completed in {total_ms:.1f}ms", total_ms)
        return {"status": "COMPLETED", "execution_id": execution.id, "output": execution.output_data}
