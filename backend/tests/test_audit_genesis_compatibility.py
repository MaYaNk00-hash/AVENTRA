"""Legacy root blocks remain verifiable without accepting tampered data."""
import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.database.models import Base, AuditLedgerEntry
from backend.security.audit import compute_payload_hash, verify_ledger_chain, append_audit_entry


@pytest.mark.parametrize("tamper", [None, "payload", "header"])
def test_legacy_root_and_successor(tamper):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        details = {"genesis": "AVENTRA_TRUST_LEDGER_ROOT", "initialized_at": "2026-10-24T00:00:00Z"}
        payload_hash = compute_payload_hash(details)
        previous = "0" * 64
        root = AuditLedgerEntry(
            actor_id="SYSTEM", actor_role="SYSTEM_CORE",
            action_type="GENESIS_LEDGER_INITIALIZATION", entity_type="SYSTEM",
            entity_id="ROOT_BLOCK", details=details, payload_hash=payload_hash,
            prev_hash=previous,
            current_hash=hashlib.sha256(f"{previous}{payload_hash}GENESIS_SYSTEM_INIT".encode()).hexdigest(),
        )
        db.add(root)
        db.commit()
        append_audit_entry(db, "reviewer", "ADMIN", "REVIEW", "TEST", "1", {"approved": True})
        if tamper == "payload":
            root.details = {"altered": True}
        elif tamper == "header":
            root.actor_id = "IMPOSTOR"
        db.commit()
        assert verify_ledger_chain(db)["is_valid"] is (tamper is None)
    engine.dispose()
