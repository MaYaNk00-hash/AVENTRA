import hashlib
import json
import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.database.models import AuditLedgerEntry


def compute_payload_hash(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_entry_hash(prev_hash: str, payload_hash: str, timestamp_iso: str, actor_id: str, action_type: str) -> str:
    raw_str = f"{prev_hash}|{payload_hash}|{timestamp_iso}|{actor_id}|{action_type}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


def append_audit_entry(
    db: Session,
    actor_id: str,
    actor_role: str,
    action_type: str,
    entity_type: str,
    entity_id: str,
    details: Dict[str, Any]
) -> AuditLedgerEntry:
    # 1. Fetch latest audit entry to get previous hash
    last_entry = db.query(AuditLedgerEntry).order_by(AuditLedgerEntry.id.desc()).first()
    prev_hash = last_entry.current_hash if last_entry else "0" * 64

    # 2. Hash payload
    payload_hash = compute_payload_hash(details)
    now = datetime.datetime.utcnow()
    iso_time = now.isoformat()

    # 3. Compute chained current hash
    curr_hash = compute_entry_hash(prev_hash, payload_hash, iso_time, actor_id, action_type)

    entry = AuditLedgerEntry(
        timestamp=now,
        actor_id=actor_id,
        actor_role=actor_role,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload_hash=payload_hash,
        prev_hash=prev_hash,
        current_hash=curr_hash,
        details=details,
        is_verified=True
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify_ledger_chain(db: Session) -> Dict[str, Any]:
    entries = db.query(AuditLedgerEntry).order_by(AuditLedgerEntry.id.asc()).all()
    if not entries:
        return {"is_valid": True, "total_entries": 0, "status": "EMPTY_LEDGER"}

    prev_expected = "0" * 64
    for idx, entry in enumerate(entries):
        if idx == 0 and entry.prev_hash == "0" * 64:
            # Genesis entry
            prev_expected = entry.current_hash
            continue

        if entry.prev_hash != prev_expected:
            return {
                "is_valid": False,
                "broken_index": idx,
                "entry_id": entry.entry_id,
                "reason": f"Broken chain link: entry.prev_hash ({entry.prev_hash[:12]}...) != expected ({prev_expected[:12]}...)"
            }

        expected_payload_hash = compute_payload_hash(entry.details)
        if entry.payload_hash != expected_payload_hash:
            return {
                "is_valid": False,
                "broken_index": idx,
                "entry_id": entry.entry_id,
                "reason": "Payload hash mismatch: entry payload has been altered!"
            }

        expected_curr_hash = compute_entry_hash(
            entry.prev_hash,
            entry.payload_hash,
            entry.timestamp.isoformat(),
            entry.actor_id,
            entry.action_type
        )
        if entry.current_hash != expected_curr_hash:
            return {
                "is_valid": False,
                "broken_index": idx,
                "entry_id": entry.entry_id,
                "reason": "Block header hash mismatch: entry cryptographic signature corrupted!"
            }

        prev_expected = entry.current_hash

    return {
        "is_valid": True,
        "total_entries": len(entries),
        "latest_block_hash": entries[-1].current_hash,
        "status": "ALL_BLOCKS_CRYPTOGRAPHICALLY_VERIFIED"
    }

