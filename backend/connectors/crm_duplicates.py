"""
CRM Duplicate Resolution & Conflict Management Engine.
Connects Model M1 LightGBM Entity Resolution to live CRM records:
- Generates 16-feature pairwise lexical/address similarity vectors.
- Detects duplicate matches across CRM and ERP candidate pools.
- Identifies field-level conflicts (name discrepancies, address variants, tax ID conflicts).
- Generates structured merge proposals with confidence metrics.
- Enforces user permissions and governance approval policies on high-confidence writes.
"""

import time
import secrets
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.database.models import EnterpriseRecord, ApprovalRequest
from datetime import datetime
from backend.security.audit import append_audit_entry
from backend.connectors.resilience import PermissionDeniedError
from ml.shared.model_registry.registry import ModelRegistry
from ml.shared.model_registry.bootstrap import bootstrap_registry


class CRMDuplicateResolver:
    """
    Intelligent duplicate detection, field-level conflict extraction,
    and governance gating for live CRM records.
    """
    def __init__(self, db: Session):
        self.db = db
        bootstrap_registry()

    def find_duplicates(
        self,
        query_record: Dict[str, Any],
        candidate_pool: Optional[List[Dict[str, Any]]] = None,
        threshold: float = 0.85
    ) -> Dict[str, Any]:
        """
        Runs Model M1 Entity Resolution against live records.
        """
        q_name = (query_record.get("account_name") or
                  query_record.get("legal_organization_name") or
                  query_record.get("business_name") or
                  query_record.get("name") or "")
        q_addr = (query_record.get("street_address") or
                  query_record.get("billing_address") or
                  query_record.get("business_address") or
                  query_record.get("address") or "")
        q_tax = query_record.get("federal_tax_id") or query_record.get("tax_ein") or query_record.get("tax_identifier")
        q_id = query_record.get("account_id") or query_record.get("company_id") or query_record.get("id") or "QUERY-REC"
        q_system = query_record.get("system_origin") or "CRM"

        # Gather candidates if not provided
        if candidate_pool is None:
            db_candidates = self.db.query(EnterpriseRecord).filter(
                EnterpriseRecord.id != q_id
            ).limit(100).all()

            candidate_pool = [
                {
                    "entity_id": r.id,
                    "business_name": r.name,
                    "business_address": r.address or "",
                    "country": r.country or "US",
                    "tax_identifier": r.tax_identifier,
                    "contact_email": r.contact_email,
                    "source_system": r.system_origin
                }
                for r in db_candidates
            ]

        if not candidate_pool:
            return {
                "decision": "NO_CANDIDATES",
                "matches": [],
                "has_duplicates": False,
                "confidence": 0.0
            }

        # Format for Model M1
        m1_query = {
            "entity_id": q_id,
            "business_name": q_name,
            "business_address": q_addr,
            "country": query_record.get("country", "US"),
            "source_system": q_system
        }

        m1_candidates = [
            {
                "entity_id": c["entity_id"],
                "business_name": c["business_name"],
                "business_address": c.get("business_address", ""),
                "country": c.get("country", "US"),
                "source_system": c.get("source_system", "CRM")
            }
            for c in candidate_pool
        ]

        # Model M1 Inference
        er_model = ModelRegistry.get_model("entity_resolution")
        er_out = er_model.predict({
            "query": m1_query,
            "candidates": m1_candidates
        })

        pred = er_out.prediction
        scored_matches = pred.get("matches", [])
        
        # Extract field-level conflicts for top matches
        enriched_matches = []
        for m in scored_matches:
            target_id = m.get("target_entity_id")
            cand_raw = next((c for c in candidate_pool if c["entity_id"] == target_id), {})
            
            conflicts = self._extract_field_conflicts(query_record, cand_raw)
            m["field_conflicts"] = conflicts
            m["has_conflicts"] = len(conflicts) > 0
            enriched_matches.append(m)

        high_conf = [m for m in enriched_matches if m["match_probability"] >= threshold]

        return {
            "decision": pred.get("decision", "EVALUATED"),
            "confidence": er_out.confidence,
            "has_duplicates": len(high_conf) > 0,
            "high_confidence_matches": high_conf,
            "matches": enriched_matches,
            "recommendation": pred.get("golden_record_recommendation")
        }

    def _extract_field_conflicts(
        self,
        query: Dict[str, Any],
        candidate: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Analyzes field differences between query record and existing matching candidate.
        """
        conflicts = []

        q_name = query.get("account_name") or query.get("name") or query.get("legal_organization_name") or ""
        c_name = candidate.get("business_name") or candidate.get("name") or ""
        if q_name.strip().lower() != c_name.strip().lower():
            conflicts.append({
                "field": "business_name",
                "source_value": q_name,
                "existing_value": c_name,
                "severity": "LOW" if any(w in c_name.lower() for w in q_name.lower().split()) else "MEDIUM"
            })

        q_addr = query.get("street_address") or query.get("address") or query.get("billing_address") or ""
        c_addr = candidate.get("business_address") or candidate.get("address") or ""
        if q_addr and c_addr and q_addr.strip().lower() != c_addr.strip().lower():
            conflicts.append({
                "field": "address",
                "source_value": q_addr,
                "existing_value": c_addr,
                "severity": "MEDIUM"
            })

        q_tax = query.get("federal_tax_id") or query.get("tax_ein") or query.get("tax_identifier")
        c_tax = candidate.get("tax_identifier")
        if q_tax and c_tax and q_tax.strip() != c_tax.strip():
            conflicts.append({
                "field": "tax_identifier",
                "source_value": q_tax,
                "existing_value": c_tax,
                "severity": "CRITICAL"
            })

        return conflicts

    def submit_governed_merge_request(
        self,
        execution_id: str,
        source_record_id: str,
        target_record_id: str,
        match_probability: float,
        proposed_canonical_name: str,
        actor_id: str = "operator"
    ) -> ApprovalRequest:
        """
        Routes duplicate merge through governance approval gate with single-use cryptographic nonce.
        """
        nonce = secrets.token_hex(32)
        appr_req = ApprovalRequest(
            execution_id=execution_id,
            step_id="crm_duplicate_gate",
            action_type="MERGE_ENTERPRISE_IDENTITY",
            risk_level="HIGH" if match_probability > 0.85 else "MEDIUM",
            confidence_score=match_probability,
            evidence={
                "source_record_id": source_record_id,
                "target_record_id": target_record_id,
                "match_probability": match_probability,
                "proposed_canonical_name": proposed_canonical_name
            },
            status="PENDING",
            nonce_token=nonce
        )
        self.db.add(appr_req)
        self.db.commit()
        self.db.refresh(appr_req)

        append_audit_entry(
            db=self.db,
            actor_id=actor_id,
            actor_role="OPERATOR",
            action_type="DUPLICATE_MERGE_APPROVAL_REQUESTED",
            entity_type="CRM_RECORD",
            entity_id=source_record_id,
            details={
                "approval_id": appr_req.id,
                "target_record_id": target_record_id,
                "match_probability": match_probability
            }
        )

        return appr_req

    def execute_authorized_merge(
        self,
        approval_id: str,
        reviewer_name: str,
        reviewer_role: str,
        canonical_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes merge after verification of human authorization gate.
        """
        appr = self.db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not appr:
            raise ValueError(f"Approval request '{approval_id}' not found.")
        if appr.status != "APPROVED":
            raise PermissionDeniedError(f"Merge cannot proceed: Approval status is '{appr.status}'.")
        if reviewer_role not in ("ADMIN", "COMPLIANCE_OFFICER", "OPERATIONS_APPROVER"):
            raise PermissionDeniedError("Your role cannot execute an approved merge.")

        evidence = appr.evidence or {}
        src_id = evidence.get("source_record_id")
        tgt_id = evidence.get("target_record_id")
        if not src_id or not tgt_id or src_id == tgt_id:
            raise ValueError("Merge requires two distinct existing records.")
        records = self.db.query(EnterpriseRecord).filter(EnterpriseRecord.id.in_([src_id, tgt_id])).all()
        if len(records) != 2:
            raise ValueError("Merge source or target no longer exists; no records changed.")

        canon_key = canonical_id or f"CAN-{secrets.token_hex(4).upper()}"

        # Update source and target records to point to the unified canonical ID
        claimed = self.db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id, ApprovalRequest.status == "APPROVED", ApprovalRequest.nonce_token == appr.nonce_token).update({"status": "EXECUTED"}, synchronize_session="fetch")
        if claimed != 1:
            self.db.rollback()
            raise PermissionDeniedError("Merge approval was already consumed or changed.")
        for rec in records:
            rec.canonical_id = canon_key
            rec.updated_at = datetime.utcnow()

        # Audit ledger chaining
        append_audit_entry(
            db=self.db,
            actor_id=reviewer_name,
            actor_role=reviewer_role,
            action_type="ENTERPRISE_IDENTITY_MERGED",
            entity_type="CANONICAL_ACCOUNT",
            entity_id=canon_key,
            details={
                "approval_id": approval_id,
                "source_record_id": src_id,
                "target_record_id": tgt_id,
                "canonical_id": canon_key
            }
        )

        return {
            "success": True,
            "canonical_id": canon_key,
            "merged_records": [src_id, tgt_id],
            "approved_by": reviewer_name
        }
