import os
import hashlib
import json
import bcrypt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from backend.database.models import (
    Base, User, AuditLedgerEntry, WorkflowDefinition, EnterpriseRecord, SchemaMapping
)

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "aventra.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Enable WAL mode and foreign keys in SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def hash_pw(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 1. Seed Users if empty
        if not db.query(User).first():
            users = [
                User(
                    id="usr-admin-1",
                    username="admin",
                    email="admin@aventra.enterprise.io",
                    hashed_password=hash_pw("Password123!"),
                    full_name="Alexander Vance (Chief AI Officer)",
                    role="ADMIN"
                ),
                User(
                    id="usr-compliance-1",
                    username="compliance",
                    email="compliance@aventra.enterprise.io",
                    hashed_password=hash_pw("Password123!"),
                    full_name="Elena Rostova (Compliance & Trust Officer)",
                    role="COMPLIANCE_OFFICER"
                ),
                User(
                    id="usr-approver-1",
                    username="approver",
                    email="ops.approver@aventra.enterprise.io",
                    hashed_password=hash_pw("Password123!"),
                    full_name="Marcus Thorne (Operations Approver)",
                    role="OPERATIONS_APPROVER"
                ),
                User(
                    id="usr-auditor-1",
                    username="auditor",
                    email="audit@aventra.enterprise.io",
                    hashed_password=hash_pw("Password123!"),
                    full_name="Dr. Sarah Lin (Lead Internal Auditor)",
                    role="AUDITOR"
                )
            ]
            db.add_all(users)
            db.commit()

        # 2. Seed Genesis Audit Block if empty
        if not db.query(AuditLedgerEntry).first():
            genesis_payload = {"genesis": "AVENTRA_TRUST_LEDGER_ROOT", "initialized_at": "2026-10-24T00:00:00Z"}
            p_hash = hashlib.sha256(json.dumps(genesis_payload, sort_keys=True).encode()).hexdigest()
            prev_hash = "0" * 64
            curr_hash = hashlib.sha256(f"{prev_hash}{p_hash}GENESIS_SYSTEM_INIT".encode()).hexdigest()
            genesis_entry = AuditLedgerEntry(
                actor_id="SYSTEM",
                actor_role="SYSTEM_CORE",
                action_type="GENESIS_LEDGER_INITIALIZATION",
                entity_type="SYSTEM",
                entity_id="ROOT_BLOCK",
                payload_hash=p_hash,
                prev_hash=prev_hash,
                current_hash=curr_hash,
                details=genesis_payload
            )
            db.add(genesis_entry)
            db.commit()

        # 3. Seed Default Workflows
        if not db.query(WorkflowDefinition).first():
            wf_onboarding = WorkflowDefinition(
                id="wf-customer-onboarding",
                name="Customer Onboarding & Duplicate Resolution",
                description="End-to-end multi-source entity verification, LightGBM duplicate detection, and human approval gating before CRM/ERP record linkage.",
                trigger_type="MANUAL",
                nodes=[
                    {"id": "n1", "label": "CRM Submission Trigger", "type": "trigger", "tool": "crm_connector.fetch_record", "position": {"x": 50, "y": 150}},
                    {"id": "n2", "label": "ERP Candidate Retrieval", "type": "action", "tool": "erp_connector.search_records", "position": {"x": 280, "y": 150}},
                    {"id": "n3", "label": "LightGBM Entity Resolution", "type": "ml_node", "tool": "entity_resolution.score_pair", "position": {"x": 510, "y": 150}},
                    {"id": "n4", "label": "Governance Approval Gate", "type": "approval_gate", "tool": "approval_gate.request_authorization", "position": {"x": 740, "y": 150}},
                    {"id": "n5", "label": "Enterprise Record Commit", "type": "action", "tool": "enterprise_action.commit_record", "position": {"x": 970, "y": 150}},
                    {"id": "n6", "label": "Tamper-Evident Ledger", "type": "audit", "tool": "audit_ledger.append_entry", "position": {"x": 1200, "y": 150}}
                ],
                edges=[
                    {"id": "e1-2", "source": "n1", "target": "n2"},
                    {"id": "e2-3", "source": "n2", "target": "n3"},
                    {"id": "e3-4", "source": "n3", "target": "n4"},
                    {"id": "e4-5", "source": "n4", "target": "n5"},
                    {"id": "e5-6", "source": "n5", "target": "n6"}
                ],
                status="ACTIVE"
            )

            wf_invoice = WorkflowDefinition(
                id="wf-invoice-reconciliation",
                name="3-Way Invoice Reconciliation & Payment Gate",
                description="Extracts invoice tokens, reconciles against ERP purchase orders and warehouse receipts, identifies anomalies, and requests human authorization.",
                trigger_type="MANUAL",
                nodes=[
                    {"id": "n1", "label": "Invoice Ingestion", "type": "trigger", "tool": "document_intelligence.extract", "position": {"x": 50, "y": 150}},
                    {"id": "n2", "label": "ERP PO Lookup", "type": "action", "tool": "erp_connector.search_records", "position": {"x": 280, "y": 150}},
                    {"id": "n3", "label": "3-Way Matching Rules", "type": "ml_node", "tool": "invoice_reconciliation.match_3way", "position": {"x": 510, "y": 150}},
                    {"id": "n4", "label": "Anomaly Check", "type": "ml_node", "tool": "anomaly_detector.evaluate", "position": {"x": 740, "y": 150}},
                    {"id": "n5", "label": "Financial Approval Gate", "type": "approval_gate", "tool": "approval_gate.request_authorization", "position": {"x": 970, "y": 150}},
                    {"id": "n6", "label": "Payment Authorization", "type": "action", "tool": "enterprise_action.commit_record", "position": {"x": 1200, "y": 150}},
                    {"id": "n7", "label": "Cryptographic Audit", "type": "audit", "tool": "audit_ledger.append_entry", "position": {"x": 1430, "y": 150}}
                ],
                edges=[
                    {"id": "e1-2", "source": "n1", "target": "n2"},
                    {"id": "e2-3", "source": "n2", "target": "n3"},
                    {"id": "e3-4", "source": "n3", "target": "n4"},
                    {"id": "e4-5", "source": "n4", "target": "n5"},
                    {"id": "e5-6", "source": "n5", "target": "n6"},
                    {"id": "e6-7", "source": "n6", "target": "n7"}
                ],
                status="ACTIVE"
            )

            db.add_all([wf_onboarding, wf_invoice])
            db.commit()

        # 4. Seed Enterprise Simulator Records (Company A CRM & Company B ERP)
        if not db.query(EnterpriseRecord).first():
            records = [
                EnterpriseRecord(
                    id="CRM-A-101",
                    system_origin="COMPANY_A_CRM",
                    entity_type="CUSTOMER",
                    name="Apex Global Logistics LLC",
                    address="742 Evergreen Terrace, Springfield, IL 62704",
                    country="US",
                    tax_identifier="US-EIN-8829104",
                    contact_email="billing@apexlogistic.com",
                    status="ACTIVE",
                    raw_data={"account_tier": "ENTERPRISE", "sales_rep": "David Chen"}
                ),
                EnterpriseRecord(
                    id="CRM-A-102",
                    system_origin="COMPANY_A_CRM",
                    entity_type="CUSTOMER",
                    name="Zenith Dynamics Corp",
                    address="100 Market Street Suite 400, San Francisco, CA 94105",
                    country="US",
                    tax_identifier="US-EIN-1948201",
                    contact_email="procurement@zenithdyn.com",
                    status="ACTIVE",
                    raw_data={"account_tier": "STRATEGIC", "sales_rep": "Sarah Connor"}
                ),
                EnterpriseRecord(
                    id="ERP-B-501",
                    system_origin="COMPANY_B_ERP",
                    entity_type="VENDOR",
                    name="Apex Global Logistics Inc",
                    address="742 Evergreen Terr, Springfield, IL",
                    country="US",
                    tax_identifier="US-EIN-8829104",
                    contact_email="accounts@apexlogistic.com",
                    status="ACTIVE",
                    raw_data={"vendor_rating": "PREFERRED", "payment_terms": "Net30"}
                ),
                EnterpriseRecord(
                    id="ERP-B-502",
                    system_origin="COMPANY_B_ERP",
                    entity_type="VENDOR",
                    name="Supreme Industrial Supply Co",
                    address="1400 Industrial Way, Cleveland, OH 44114",
                    country="US",
                    tax_identifier="US-EIN-9938210",
                    contact_email="orders@supremeindustrial.com",
                    status="ACTIVE",
                    raw_data={"vendor_rating": "STANDARD", "payment_terms": "Net45"}
                ),
                EnterpriseRecord(
                    id="ERP-B-503",
                    system_origin="COMPANY_B_ERP",
                    entity_type="VENDOR",
                    name="Global Micro Technologies Ltd",
                    address="Plot 42 Cyber City, Gurgaon, Haryana",
                    country="India",
                    tax_identifier="GSTIN-06AAAAA0000A1Z5",
                    contact_email="sales@globalmicro.in",
                    status="ACTIVE",
                    raw_data={"vendor_rating": "PREFERRED", "payment_terms": "Net60"}
                )
            ]
            db.add_all(records)
            db.commit()

        # 5. Seed Schema Mappings
        if not db.query(SchemaMapping).first():
            sm = SchemaMapping(
                id="sm-crm-to-canonical",
                source_system="COMPANY_A_CRM",
                target_system="CANONICAL_ENTERPRISE",
                version="v1.0",
                mappings=[
                    {"source_field": "account_name", "target_field": "customer_name", "confidence": 0.98},
                    {"source_field": "street_address", "target_field": "billing_address", "confidence": 0.95},
                    {"source_field": "federal_tax_id", "target_field": "tax_identifier", "confidence": 0.99},
                    {"source_field": "primary_email", "target_field": "contact_email", "confidence": 0.96}
                ],
                status="ACTIVE",
                approved_by="compliance"
            )
            db.add(sm)
            db.commit()

    finally:
        db.close()
