from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.database.session import get_db
from backend.database.models import AuditLedgerEntry
from backend.security.audit import verify_ledger_chain

router = APIRouter(prefix="/api/audit", tags=["Cryptographic Audit Ledger"])


@router.get("/ledger")
def get_audit_ledger(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    total = db.query(AuditLedgerEntry).count()
    entries = db.query(AuditLedgerEntry).order_by(AuditLedgerEntry.id.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "entries": [
            {
                "id": e.id,
                "entry_id": e.entry_id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "actor_id": e.actor_id,
                "actor_role": e.actor_role,
                "action_type": e.action_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "payload_hash": e.payload_hash,
                "prev_hash": e.prev_hash,
                "current_hash": e.current_hash,
                "details": e.details,
                "is_verified": e.is_verified
            }
            for e in entries
        ]
    }


@router.get("/verify-chain")
def run_ledger_verification(db: Session = Depends(get_db)):
    """
    Performs full SHA-256 chained hash validation across all audit records.
    Detects if any payload, previous pointer, or block signature has been altered.
    """
    res = verify_ledger_chain(db)
    return res

