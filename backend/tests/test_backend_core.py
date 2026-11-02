import pytest
import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from backend.main import app
from backend.database.session import SessionLocal, seed_database
from backend.database.models import User, WorkflowExecution, ApprovalRequest, AuditLedgerEntry
from backend.security.audit import verify_ledger_chain, append_audit_entry
from backend.workflows.engine import WorkflowExecutionEngine

client = TestClient(app)


def setup_module():
    seed_database()


def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "HEALTHY"


def test_audit_ledger_integrity():
    db = SessionLocal()
    try:
        verification = verify_ledger_chain(db)
        assert verification["is_valid"] is True
        assert verification["total_entries"] >= 1
    finally:
        db.close()


def test_primary_customer_onboarding_and_approval_flow():
    """
    Validates Stage 5 & 11 Primary Acceptance Criteria:
    1. Triggers customer onboarding workflow.
    2. Model identifies duplicate with Apex Global Logistics.
    3. Workflow pauses at Governance Approval Gate with status AWAITING_APPROVAL.
    4. Compliance Officer inspects evidence and authorizes linkage.
    5. Action executes and generates canonical ID.
    6. Cryptographic audit entry is chained and verified.
    """
    db = SessionLocal()
    try:
        engine = WorkflowExecutionEngine(db)
        execution = engine.create_execution(
            workflow_id="wf-customer-onboarding",
            triggered_by="operator_test",
            input_data={
                "record": {
                    "business_name": "Apex Global Logistics LLC",
                    "business_address": "742 Evergreen Terrace, Springfield, IL 62704",
                    "country": "US",
                    "federal_tax_id": "US-EIN-8829104",
                    "contact_email": "billing@apexlogistic.com"
                }
            }
        )

        # 1. Run workflow -> should pause at approval gate
        run_res = engine.run_customer_onboarding(execution.id)
        assert run_res["status"] == "AWAITING_APPROVAL"
        appr_id = run_res["approval_id"]

        # Check DB state
        appr_req = db.query(ApprovalRequest).filter(ApprovalRequest.id == appr_id).first()
        assert appr_req.status == "PENDING"
        assert appr_req.risk_level in ["HIGH", "MEDIUM"]
        assert appr_req.confidence_score > 0.70

        # 2. Approve via engine
        resume_res = engine.resume_after_approval(
            approval_id=appr_id,
            approved_by="Elena Rostova (Compliance Officer)",
            user_role="COMPLIANCE_OFFICER",
            decision="APPROVED",
            comments="Verified identical EIN and matching address. Linkage approved."
        )

        assert resume_res["status"] == "COMPLETED"
        assert "canonical_id" in resume_res["output"]

        # 3. Verify audit chain remains unbroken
        verify_after = verify_ledger_chain(db)
        assert verify_after["is_valid"] is True

    finally:
        db.close()


def test_agent_task_execution():
    res = client.post("/api/agent/execute", json={
        "prompt": "Onboard new vendor Zenith Dynamics Corp into Company A CRM."
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["AWAITING_APPROVAL", "COMPLETED", "RUNNING"]
    assert "execution_id" in data

