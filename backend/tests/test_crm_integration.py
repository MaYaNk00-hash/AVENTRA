"""
Unit & Integration Tests for Stage 6: Complete CRM Integration:
1. Account, Contact, Lead, and Organization read operations
2. Supported record creation and updates with persistent storage
3. Search, filtering, cursor pagination, and incremental synchronization
4. Model M1 Entity Resolution connected to live CRM records
5. Duplicate matches, conflict detection, and field-level validation
6. Governance approval policies and audit trail on writes
7. Verification across two distinct CRM schemas / adapters (Salesforce & HubSpot)
"""

import pytest
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from backend.database.session import SessionLocal, seed_database
from backend.database.models import EnterpriseRecord, ApprovalRequest, AuditLedgerEntry, WorkflowExecution
from backend.connectors.crm_adapters import (
    SalesforceCRMAdapter,
    HubSpotCRMAdapter,
    crm_record_to_canonical_account
)
from backend.connectors.crm_duplicates import CRMDuplicateResolver
from backend.connectors.base import ConnectorQuery
from backend.api.crm import (
    list_accounts,
    get_account,
    create_account,
    update_account,
    list_contacts,
    create_contact,
    list_leads,
    create_lead,
    scan_crm_duplicates,
    request_crm_merge,
    execute_crm_merge,
    CreateAccountRequest,
    UpdateAccountRequest,
    CreateContactRequest,
    CreateLeadRequest,
    DuplicateScanRequest,
    RequestMergePayload,
    ExecuteMergePayload
)
from backend.security.audit import verify_ledger_chain


@pytest.fixture(scope="module")
def db_session():
    seed_database()
    db = SessionLocal()
    # Explicit test-only records required by the adapter contract. Production
    # seeding deliberately does not fabricate missing contacts or HubSpot rows.
    created_fixture_ids = []
    primary = db.query(EnterpriseRecord).filter_by(id="CRM-A-101").one()
    fixtures = [
        EnterpriseRecord(id="CRM-CNT-FIXTURE-01",system_origin="COMPANY_A_CRM",entity_type="CONTACT",name="Synthetic Contact",contact_email="contact@example.test",raw_data={"account_id":"CRM-A-101","first_name":"Synthetic"}),
        EnterpriseRecord(id="CRM-LEAD-FIXTURE-01",system_origin="COMPANY_A_CRM",entity_type="LEAD",name="Synthetic Prospect",contact_email="lead@example.test",raw_data={"contact_name":"Synthetic Lead","lead_score":50}),
        EnterpriseRecord(id="HS-COMP-901",system_origin="HUBSPOT_CRM",entity_type="COMPANY",name=primary.name,address=primary.address,country=primary.country,tax_identifier=primary.tax_identifier,contact_email="company@example.test",raw_data={"domain_name":"example.test","annual_revenue_usd":0}),
    ]
    for fixture in fixtures:
        if not db.query(EnterpriseRecord).filter_by(id=fixture.id).first():
            created_fixture_ids.append(fixture.id);db.add(fixture)
    db.commit()

    test_record_ids = ["CRM-A-TEST-99", "CRM-A-TEST-100", "HS-COMP-TEST-01", "NEW-PROSPECT-01"]
    db.query(ApprovalRequest).filter(ApprovalRequest.execution_id == "exec-crm-test-01").delete(synchronize_session=False)
    db.query(WorkflowExecution).filter(WorkflowExecution.id == "exec-crm-test-01").delete(synchronize_session=False)
    db.query(EnterpriseRecord).filter(EnterpriseRecord.id.in_(test_record_ids)).delete(synchronize_session=False)
    for rec_id in ["CRM-A-101", "HS-COMP-901"]:
        rec = db.query(EnterpriseRecord).filter(EnterpriseRecord.id == rec_id).first()
        if rec:
            rec.canonical_id = None
    db.commit()

    yield db

    db.query(ApprovalRequest).filter(ApprovalRequest.execution_id == "exec-crm-test-01").delete(synchronize_session=False)
    db.query(WorkflowExecution).filter(WorkflowExecution.id == "exec-crm-test-01").delete(synchronize_session=False)
    db.query(EnterpriseRecord).filter(EnterpriseRecord.id.in_(test_record_ids)).delete(synchronize_session=False)
    for rec_id in ["CRM-A-101", "HS-COMP-901"]:
        rec = db.query(EnterpriseRecord).filter(EnterpriseRecord.id == rec_id).first()
        if rec:
            rec.canonical_id = None
    db.commit()
    db.close()
    with SessionLocal() as cleanup:
        cleanup.query(EnterpriseRecord).filter(EnterpriseRecord.id.in_(created_fixture_ids)).delete(synchronize_session=False)
        cleanup.commit()


def test_schema_1_salesforce_read_operations(db_session: Session):
    """
    Verify Schema 1 (Company A / Salesforce):
    Read operations for Accounts, Contacts, Leads, and Organizations.
    """
    adapter = SalesforceCRMAdapter(db_session)
    
    # 1. Accounts read
    page_acc = adapter.read_records(ConnectorQuery(record_type="account", limit=10))
    assert page_acc.count >= 1
    assert any("account_name" in r for r in page_acc.records)
    first_acc = page_acc.records[0]
    assert "account_id" in first_acc

    # 2. Contacts read
    page_cnt = adapter.read_records(ConnectorQuery(record_type="contact", limit=10))
    assert page_cnt.count >= 1
    assert any("contact_id" in r for r in page_cnt.records)

    # 3. Leads read
    page_led = adapter.read_records(ConnectorQuery(record_type="lead", limit=10))
    assert page_led.count >= 1
    assert any("lead_id" in r for r in page_led.records)

    # 4. Get by ID
    single = adapter.get_record_by_id("account", first_acc["account_id"])
    assert single is not None
    assert single["account_name"] == first_acc["account_name"]


def test_schema_2_hubspot_read_operations(db_session: Session):
    """
    Verify Schema 2 (HubSpot CRM alternate schema):
    Read operations for Companies and distinct field nomenclature.
    """
    adapter = HubSpotCRMAdapter(db_session)
    schema = adapter.discover_schema()
    field_names = [f["field_name"] for f in schema]

    assert "company_id" in field_names
    assert "legal_organization_name" in field_names
    assert "tax_ein" in field_names
    assert "domain_email" in field_names
    assert "lifecycle_stage" in field_names

    # Read records
    page_comp = adapter.read_records(ConnectorQuery(record_type="company", limit=10))
    assert page_comp.count >= 1
    first_comp = page_comp.records[0]
    assert "legal_organization_name" in first_comp
    assert "tax_ein" in first_comp


def test_record_creation_updates_and_field_validation(db_session: Session):
    """
    Verify record creation and updates with persistent storage and field validation.
    """
    adapter = SalesforceCRMAdapter(db_session)

    # 1. Invalid email validation
    with pytest.raises(ValueError) as exc:
        adapter.create_record("account", {
            "account_name": "Test Company",
            "primary_email": "invalid-email-address-no-at"
        })
    assert "Invalid primary_email format" in str(exc.value)

    # 2. Missing mandatory account_name validation
    with pytest.raises(ValueError) as exc:
        adapter.create_record("account", {"account_name": ""})
    assert "account_name" in str(exc.value)

    # 3. Valid creation
    db_session.query(EnterpriseRecord).filter(EnterpriseRecord.id == "CRM-A-TEST-99").delete(synchronize_session=False)
    db_session.commit()
    created = adapter.create_record("account", {
        "account_id": "CRM-A-TEST-99",
        "account_name": "Atlas Heavy Industries Ltd",
        "street_address": "88 Harbor Blvd, Seattle, WA 98101",
        "country": "US",
        "federal_tax_id": "US-EIN-7729104",
        "primary_email": "procurement@atlasheavy.com",
        "annual_revenue": 45000000.0
    })
    assert created.success is True
    assert created.record_id == "CRM-A-TEST-99"

    # Verify persisted in database
    persisted = db_session.query(EnterpriseRecord).filter(
        EnterpriseRecord.id == "CRM-A-TEST-99"
    ).first()
    assert persisted is not None
    assert persisted.name == "Atlas Heavy Industries Ltd"

    # 4. Valid update
    updated = adapter.update_record("account", "CRM-A-TEST-99", {
        "account_name": "Atlas Heavy Industries Corporation",
        "annual_revenue": 52000000.0
    })
    assert updated.success is True

    db_session.refresh(persisted)
    assert persisted.name == "Atlas Heavy Industries Corporation"
    assert persisted.raw_data["annual_revenue"] == 52000000.0


def test_search_filtering_pagination_and_incremental_sync(db_session: Session):
    """
    Verify search, filtering, cursor pagination, and incremental synchronization.
    """
    adapter = SalesforceCRMAdapter(db_session)

    # 1. Substring search
    search_page = adapter.read_records(ConnectorQuery(
        record_type="account",
        filters={"search": "Apex Global"}
    ))
    assert search_page.count >= 1
    assert any("Apex" in r["account_name"] for r in search_page.records)

    # 2. Status filtering
    status_page = adapter.read_records(ConnectorQuery(
        record_type="account",
        filters={"status": "ACTIVE"}
    ))
    assert all(r["status"] == "ACTIVE" for r in status_page.records)

    # 3. Cursor pagination
    p1 = adapter.read_records(ConnectorQuery(record_type="account", limit=1, cursor="0"))
    assert p1.count == 1
    if p1.has_more:
        assert p1.next_cursor is not None
        p2 = adapter.read_records(ConnectorQuery(record_type="account", limit=1, cursor=p1.next_cursor))
        assert p2.count == 1
        assert p1.records[0]["account_id"] != p2.records[0]["account_id"]

    # 4. Incremental synchronization
    old_watermark = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    incremental_res = adapter.read_records(ConnectorQuery(
        record_type="account",
        incremental_since=old_watermark
    ))
    assert incremental_res.count >= 1

    future_watermark = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    empty_sync = adapter.read_records(ConnectorQuery(
        record_type="account",
        incremental_since=future_watermark
    ))
    assert empty_sync.count == 0


def test_m1_entity_resolution_and_conflict_detection(db_session: Session):
    """
    Verify Model M1 Entity Resolution duplicate detection and field-level conflict extraction.
    """
    resolver = CRMDuplicateResolver(db_session)

    # Query record with slight lexical variation against existing "Apex Global Logistics LLC"
    query = {
        "account_id": "NEW-PROSPECT-01",
        "account_name": "Apex Global Logistics Inc",  # "Inc" vs "LLC"
        "street_address": "742 Evergreen Terr",        # "Terr" vs "Terrace"
        "country": "US",
        "federal_tax_id": "US-EIN-8829104",
        "system_origin": "COMPANY_A_CRM"
    }

    result = resolver.find_duplicates(query_record=query, threshold=0.75)

    assert result["has_duplicates"] is True
    assert len(result["matches"]) >= 1

    top_match = result["matches"][0]
    assert top_match["match_probability"] >= 0.75

    # Check field conflicts detected
    conflicts = top_match.get("field_conflicts", [])
    assert len(conflicts) >= 1
    conflict_fields = {c["field"] for c in conflicts}
    assert "business_name" in conflict_fields or "address" in conflict_fields


def test_governance_approval_policies_and_audit_on_writes(db_session: Session):
    """
    Verify that duplicate merges require approval, single-use cryptographic nonces,
    and are logged in the append-only cryptographic audit ledger.
    """
    resolver = CRMDuplicateResolver(db_session)

    # Ensure parent workflow execution exists for foreign key constraint
    db_session.query(ApprovalRequest).filter(ApprovalRequest.execution_id == "exec-crm-test-01").delete(synchronize_session=False)
    for rec_id in ["CRM-A-101", "HS-COMP-901"]:
        r_clean = db_session.query(EnterpriseRecord).filter(EnterpriseRecord.id == rec_id).first()
        if r_clean:
            r_clean.canonical_id = None
    db_session.commit()

    existing_exec = db_session.query(WorkflowExecution).filter(
        WorkflowExecution.id == "exec-crm-test-01"
    ).first()
    if not existing_exec:
        exec_row = WorkflowExecution(
            id="exec-crm-test-01",
            workflow_id="wf-customer-onboarding",
            triggered_by="operator_test",
            status="RUNNING"
        )
        db_session.add(exec_row)
        db_session.commit()

    # 1. Submit merge request
    appr_req = resolver.submit_governed_merge_request(
        execution_id="exec-crm-test-01",
        source_record_id="CRM-A-101",
        target_record_id="HS-COMP-901",
        match_probability=0.942,
        proposed_canonical_name="Apex Global Logistics (Master)",
        actor_id="operator_test"
    )

    assert appr_req.status == "PENDING"
    assert len(appr_req.nonce_token) == 64
    assert appr_req.risk_level == "HIGH"

    # 2. Attempt unauthorized execution -> should fail
    with pytest.raises(Exception):
        resolver.execute_authorized_merge(
            approval_id=appr_req.id,
            reviewer_name="Elena Rostova",
            reviewer_role="COMPLIANCE_OFFICER"
        )

    # 3. Simulate authorized approval decision
    appr_req.status = "APPROVED"
    db_session.commit()
    with pytest.raises(Exception,match="role"):
        resolver.execute_authorized_merge(appr_req.id,"Test auditor","AUDITOR")
    original_evidence=dict(appr_req.evidence)
    appr_req.evidence={**original_evidence,"target_record_id":"NONEXISTENT-RECORD"}
    db_session.commit()
    with pytest.raises(ValueError,match="no longer exists"):
        resolver.execute_authorized_merge(appr_req.id,"Test reviewer","COMPLIANCE_OFFICER")
    assert db_session.query(EnterpriseRecord).filter_by(id="CRM-A-101").one().canonical_id is None
    appr_req.evidence=original_evidence
    db_session.commit()

    # 4. Authorized execution
    merge_res = resolver.execute_authorized_merge(
        approval_id=appr_req.id,
        reviewer_name="Elena Rostova (Compliance Officer)",
        reviewer_role="COMPLIANCE_OFFICER"
    )
    assert merge_res["success"] is True
    assert "canonical_id" in merge_res
    with pytest.raises(Exception,match="Approval status"):
        resolver.execute_authorized_merge(appr_req.id,"Test reviewer","COMPLIANCE_OFFICER")

    # 5. Verify records updated with canonical ID
    rec1 = db_session.query(EnterpriseRecord).filter(EnterpriseRecord.id == "CRM-A-101").first()
    rec2 = db_session.query(EnterpriseRecord).filter(EnterpriseRecord.id == "HS-COMP-901").first()
    assert rec1.canonical_id == merge_res["canonical_id"]
    assert rec2.canonical_id == merge_res["canonical_id"]

    # 6. Verify audit ledger chain
    chain_check = verify_ledger_chain(db_session)
    assert chain_check["is_valid"] is True


def test_cross_schema_canonical_mapping():
    """
    Verify both CRM schemas translate cleanly to CanonicalAccount.
    """
    # Salesforce
    sf_raw = {
        "account_id": "CRM-A-101",
        "account_name": "Zenith Dynamics",
        "street_address": "100 Market St",
        "country": "US",
        "federal_tax_id": "US-EIN-1948201",
        "primary_email": "ops@zenithdyn.com"
    }
    canon_sf = crm_record_to_canonical_account(sf_raw, "COMPANY_A_CRM")
    assert canon_sf.account_name == "Zenith Dynamics"
    assert canon_sf.tax_identifier == "US-EIN-1948201"

    # HubSpot
    hs_raw = {
        "company_id": "HS-COMP-902",
        "legal_organization_name": "Meridian Cloud Software",
        "billing_address": "200 Tech Blvd",
        "country_code": "US",
        "tax_ein": "US-EIN-4491029",
        "domain_email": "billing@meridiancloud.io"
    }
    canon_hs = crm_record_to_canonical_account(hs_raw, "HUBSPOT_CRM")
    assert canon_hs.account_name == "Meridian Cloud Software"
    assert canon_hs.tax_identifier == "US-EIN-4491029"
    assert canon_hs.primary_email == "billing@meridiancloud.io"
