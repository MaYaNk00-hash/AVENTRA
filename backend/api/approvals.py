from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.database.models import ApprovalRequest, User
from backend.workflows.engine import WorkflowExecutionEngine
from backend.security.auth import get_current_user
from backend.security.rbac import require_roles

router = APIRouter(prefix="/api/approvals", tags=["Human Approvals"])


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    comments: str = Field(..., min_length=3)
    nonce_token: Optional[str] = None
    reviewer_name: Optional[str] = "Elena Rostova (Compliance Officer)"
    reviewer_role: Optional[str] = "COMPLIANCE_OFFICER"


@router.get("")
def list_approvals(status_filter: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(ApprovalRequest)
    if status_filter:
        query = query.filter(ApprovalRequest.status == status_filter.upper())
    requests = query.order_by(ApprovalRequest.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "execution_id": r.execution_id,
            "step_id": r.step_id,
            "action_type": r.action_type,
            "risk_level": r.risk_level,
            "confidence_score": r.confidence_score,
            "evidence": r.evidence,
            "status": r.status,
            "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "reviewer_comments": r.reviewer_comments,
            "nonce_token": r.nonce_token,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in requests
    ]


@router.get("/{approval_id}")
def get_approval_detail(approval_id: str, db: Session = Depends(get_db)):
    r = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Approval request not found")

    return {
        "id": r.id,
        "execution_id": r.execution_id,
        "step_id": r.step_id,
        "action_type": r.action_type,
        "risk_level": r.risk_level,
        "confidence_score": r.confidence_score,
        "evidence": r.evidence,
        "status": r.status,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "reviewer_comments": r.reviewer_comments,
        "nonce_token": r.nonce_token,
        "created_at": r.created_at.isoformat() if r.created_at else None
    }


@router.post("/{approval_id}/decide")
def decide_approval(
    approval_id: str,
    req: ApprovalDecisionRequest,
    db: Session = Depends(get_db)
):
    engine = WorkflowExecutionEngine(db)
    try:
        res = engine.resume_after_approval(
            approval_id=approval_id,
            approved_by=req.reviewer_name or "Elena Rostova",
            user_role=req.reviewer_role or "COMPLIANCE_OFFICER",
            decision=req.decision,
            comments=req.comments
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

