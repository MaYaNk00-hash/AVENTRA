import os
import hashlib
import json
import bcrypt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from backend.database.models import (
    Base, User, AuditLedgerEntry, WorkflowDefinition, EnterpriseRecord, SchemaMapping, EnterpriseConnection
)
from backend.security.vault import encrypt_secrets

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "aventra.db"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# Handle both PostgreSQL enterprise deployments and local SQLite
if DATABASE_URL.startswith("sqlite"):
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
else:
    # Enterprise PostgreSQL with connection pooling and health pre-ping
    engine = create_engine(
        DATABASE_URL,
        pool_size=int(os.getenv("DB_POOL_SIZE", "15")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_pre_ping=True,
        pool_recycle=3600
    )

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

        # Seed Live ERP Records (POs, Goods Receipts, Invoices across SAP and NetSuite schemas)
        if not db.query(EnterpriseRecord).filter(EnterpriseRecord.entity_type == "PURCHASE_ORDER").first():
            erp_seed_records = [
                # 1. SAP ERP: Standard Purchase Order
                EnterpriseRecord(
                    id="PO-2026-8801",
                    system_origin="COMPANY_B_ERP",
                    entity_type="PURCHASE_ORDER",
                    name="Apex Global Logistics Inc",
                    status="APPROVED",
                    raw_data={
                        "po_number": "PO-2026-8801",
                        "vendor_id": "ERP-B-501",
                        "vendor_name": "Apex Global Logistics Inc",
                        "order_date": "2026-10-15T09:00:00Z",
                        "total_amount": 5400.00,
                        "tax_amount": 0.00,
                        "subtotal": 5400.00,
                        "currency": "USD",
                        "payment_terms": "Net30",
                        "line_items": [
                            {"line_number": 1, "sku": "LOG-FREIGHT-40FT", "description": "Ocean Freight 40ft Container", "quantity": 1.0, "unit_price": 4200.00, "total": 4200.00},
                            {"line_number": 2, "sku": "LOG-PORT-HANDLING", "description": "Port Handling & Customs Clearance", "quantity": 1.0, "unit_price": 1200.00, "total": 1200.00}
                        ]
                    }
                ),
                # 2. SAP ERP: Goods Receipt for PO-2026-8801
                EnterpriseRecord(
                    id="GR-2026-4401",
                    system_origin="COMPANY_B_ERP",
                    entity_type="GOODS_RECEIPT",
                    name="GR for PO-2026-8801",
                    status="VERIFIED_RECEIVED",
                    raw_data={
                        "gr_number": "GR-2026-4401",
                        "po_number": "PO-2026-8801",
                        "vendor_id": "ERP-B-501",
                        "received_date": "2026-10-18T14:30:00Z",
                        "carrier_tracking": "TRK-MAERSK-9921",
                        "received_items": [
                            {"sku": "LOG-FREIGHT-40FT", "quantity_received": 1.0, "condition": "ACCEPTABLE"},
                            {"sku": "LOG-PORT-HANDLING", "quantity_received": 1.0, "condition": "ACCEPTABLE"}
                        ]
                    }
                ),
                # 3. SAP ERP: Exact Match Invoice
                EnterpriseRecord(
                    id="INV-2026-001",
                    system_origin="COMPANY_B_ERP",
                    entity_type="INVOICE",
                    name="Apex Global Logistics Inc",
                    status="RECONCILED",
                    raw_data={
                        "invoice_number": "INV-2026-001",
                        "po_number": "PO-2026-8801",
                        "vendor_id": "ERP-B-501",
                        "vendor_name": "Apex Global Logistics Inc",
                        "invoice_date": "2026-10-19T10:00:00Z",
                        "due_date": "2026-11-19T10:00:00Z",
                        "subtotal": 5400.00,
                        "tax_amount": 0.00,
                        "total_amount": 5400.00,
                        "currency": "USD",
                        "reconciliation_status": "RECONCILED_EXACT",
                        "line_items": [
                            {"line_number": 1, "sku": "LOG-FREIGHT-40FT", "description": "Ocean Freight 40ft Container", "quantity": 1.0, "unit_price": 4200.00, "total": 4200.00},
                            {"line_number": 2, "sku": "LOG-PORT-HANDLING", "description": "Port Handling & Customs Clearance", "quantity": 1.0, "unit_price": 1200.00, "total": 1200.00}
                        ]
                    }
                ),
                # 4. SAP ERP: Discrepant Invoice (Triggers Approval Gate)
                EnterpriseRecord(
                    id="INV-2026-003",
                    system_origin="COMPANY_B_ERP",
                    entity_type="INVOICE",
                    name="Apex Global Logistics Inc",
                    status="DISCREPANCY_APPROVAL_REQUIRED",
                    raw_data={
                        "invoice_number": "INV-2026-003",
                        "po_number": "PO-2026-8801",
                        "vendor_id": "ERP-B-501",
                        "vendor_name": "Apex Global Logistics Inc",
                        "invoice_date": "2026-10-21T11:00:00Z",
                        "due_date": "2026-11-21T11:00:00Z",
                        "subtotal": 7800.00,
                        "tax_amount": 0.00,
                        "total_amount": 7800.00,
                        "currency": "USD",
                        "reconciliation_status": "DISCREPANCY_APPROVAL_REQUIRED",
                        "line_items": [
                            {"line_number": 1, "sku": "LOG-FREIGHT-40FT", "description": "Ocean Freight 40ft Container", "quantity": 1.0, "unit_price": 6200.00, "total": 6200.00},
                            {"line_number": 2, "sku": "LOG-PORT-HANDLING", "description": "Port Handling & Customs Clearance", "quantity": 1.0, "unit_price": 1600.00, "total": 1600.00}
                        ]
                    }
                ),
                # 5. NetSuite ERP: Vendor
                EnterpriseRecord(
                    id="NS-VND-701",
                    system_origin="NETSUITE_ERP",
                    entity_type="VENDOR",
                    name="Meridian Cloud Software Inc",
                    address="200 Tech Blvd, Austin, TX 78701",
                    tax_identifier="US-EIN-4491029",
                    status="ACTIVE",
                    raw_data={
                        "currency_code": "USD",
                        "terms": "Net 30",
                        "subsidiary": "Americas"
                    }
                ),
                # 6. NetSuite ERP: Purchase Order
                EnterpriseRecord(
                    id="NS-PO-301",
                    system_origin="NETSUITE_ERP",
                    entity_type="PURCHASE_ORDER",
                    name="Meridian Cloud Software Inc",
                    status="APPROVED",
                    raw_data={
                        "tran_id": "NS-PO-301",
                        "entity_ref": "NS-VND-701",
                        "vendor_title": "Meridian Cloud Software Inc",
                        "tran_date": "2026-10-10T08:00:00Z",
                        "foreign_total": 8200.00,
                        "tax_total": 0.00,
                        "currency_code": "USD",
                        "items": [
                            {"line_id": 1, "item_ref": "SW-SUB-ENT", "memo": "Annual Enterprise Cloud License", "qty": 1.0, "rate": 8200.00, "amount": 8200.00}
                        ]
                    }
                ),
                # 7. NetSuite ERP: Item Receipt
                EnterpriseRecord(
                    id="NS-GR-301",
                    system_origin="NETSUITE_ERP",
                    entity_type="GOODS_RECEIPT",
                    name="Item Receipt for NS-PO-301",
                    status="RECEIVED",
                    raw_data={
                        "receipt_doc_no": "NS-GR-301",
                        "po_ref": "NS-PO-301",
                        "date_received": "2026-10-12T12:00:00Z",
                        "items_received": [
                            {"item_ref": "SW-SUB-ENT", "quantity": 1.0}
                        ]
                    }
                ),
                # 8. NetSuite ERP: Vendor Bill
                EnterpriseRecord(
                    id="NS-BILL-301",
                    system_origin="NETSUITE_ERP",
                    entity_type="INVOICE",
                    name="Meridian Cloud Software Inc",
                    status="OPEN",
                    raw_data={
                        "bill_number": "NS-BILL-301",
                        "po_ref": "NS-PO-301",
                        "entity_ref": "NS-VND-701",
                        "vendor_title": "Meridian Cloud Software Inc",
                        "bill_date": "2026-10-13T10:00:00Z",
                        "net_amount": 8200.00,
                        "tax_amount": 0.00,
                        "gross_amount": 8200.00,
                        "currency_code": "USD",
                        "bill_items": [
                            {"line_id": 1, "item_ref": "SW-SUB-ENT", "memo": "Annual Enterprise Cloud License", "qty": 1.0, "rate": 8200.00, "amount": 8200.00}
                        ]
                    }
                )
            ]
            db.add_all(erp_seed_records)
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

        # 6. Seed Enterprise Connections
        if not db.query(EnterpriseConnection).first():
            connections = [
                EnterpriseConnection(
                    id="conn-crm-01",
                    name="Company A CRM (Alpha Production)",
                    connector_type="CRM",
                    provider="salesforce",
                    description="Primary corporate customer accounts, contacts, and opportunities management.",
                    environment="PRODUCTION",
                    tenant_id="default-enterprise",
                    status="CONNECTED",
                    is_enabled=True,
                    read_only=False,
                    allowed_operations=["READ", "SEARCH", "CREATE_RECORD", "UPDATE_RECORD"],
                    allowed_entities=["accounts", "contacts", "opportunities"],
                    encrypted_secrets=encrypt_secrets({
                        "api_key": "sec_crm_alpha_token_live",
                        "client_secret": "sf_live_oauth2_sec991"
                    }),
                    config={
                        "endpoint": "https://api.crm-alpha.internal",
                        "timeout_seconds": 10,
                        "max_retries": 3,
                        "rate_limit_per_minute": 120
                    },
                    last_health_check={
                        "status": "CONNECTED",
                        "latency_ms": 14.2,
                        "message": "Connected. 3 accounts discoverable.",
                        "last_checked_at": "2026-11-02T12:00:00Z"
                    },
                    metrics={
                        "total_requests": 28,
                        "successful_requests": 28,
                        "failed_requests": 0,
                        "consecutive_failures": 0,
                        "rate_limited_count": 0
                    }
                ),
                EnterpriseConnection(
                    id="conn-erp-01",
                    name="Company B ERP (Vendor Ledger)",
                    connector_type="ERP",
                    provider="sap",
                    description="Core enterprise resource planning, vendor master, and purchase orders.",
                    environment="PRODUCTION",
                    tenant_id="default-enterprise",
                    status="CONNECTED",
                    is_enabled=True,
                    read_only=False,
                    allowed_operations=["READ", "SEARCH", "CREATE_RECORD", "UPDATE_RECORD"],
                    allowed_entities=["vendors", "purchase_orders", "invoices"],
                    encrypted_secrets=encrypt_secrets({
                        "client_secret": "erp_b_secret_9981",
                        "api_key": "sap_gateway_token_prod"
                    }),
                    config={
                        "endpoint": "https://erp.enterprise-internal.net/api/v2",
                        "timeout_seconds": 15,
                        "max_retries": 3,
                        "rate_limit_per_minute": 100
                    },
                    last_health_check={
                        "status": "CONNECTED",
                        "latency_ms": 22.8,
                        "message": "ERP Connected. 3 vendors discoverable.",
                        "last_checked_at": "2026-11-02T12:00:00Z"
                    },
                    metrics={
                        "total_requests": 42,
                        "successful_requests": 42,
                        "failed_requests": 0,
                        "consecutive_failures": 0,
                        "rate_limited_count": 0
                    }
                ),
                EnterpriseConnection(
                    id="conn-db-01",
                    name="Enterprise Analytics Data Warehouse",
                    connector_type="DATABASE",
                    provider="postgresql",
                    description="Read-only enterprise financial audit repository and historical transaction warehouse.",
                    environment="PRODUCTION",
                    tenant_id="default-enterprise",
                    status="CONNECTED",
                    is_enabled=True,
                    read_only=True,
                    allowed_operations=["READ", "SEARCH", "QUERY"],
                    allowed_entities=["audit_logs", "general_ledger", "reconciliation_batches"],
                    encrypted_secrets=encrypt_secrets({
                        "password": "dw_prod_pg_password_90!",
                        "username": "avent_ro"
                    }),
                    config={
                        "host": "dw.analytics.enterprise.local",
                        "port": 5432,
                        "database_name": "dw_enterprise",
                        "timeout_seconds": 10,
                        "max_retries": 2,
                        "rate_limit_per_minute": 200
                    },
                    last_health_check={
                        "status": "CONNECTED",
                        "latency_ms": 8.4,
                        "message": "PostgreSQL database ready. 12 tables discoverable.",
                        "last_checked_at": "2026-11-02T12:00:00Z"
                    },
                    metrics={
                        "total_requests": 15,
                        "successful_requests": 15,
                        "failed_requests": 0,
                        "consecutive_failures": 0,
                        "rate_limited_count": 0
                    }
                ),
                EnterpriseConnection(
                    id="conn-email-01",
                    name="Corporate Operations Mailbox",
                    connector_type="EMAIL",
                    provider="gmail",
                    description="Google Workspace operational inbox for invoice submission and vendor alerts.",
                    environment="PRODUCTION",
                    tenant_id="default-enterprise",
                    status="CONNECTED",
                    is_enabled=True,
                    read_only=False,
                    allowed_operations=["READ", "SEARCH", "CREATE_DRAFT"],
                    allowed_entities=["messages", "threads", "drafts"],
                    encrypted_secrets=encrypt_secrets({
                        "oauth_client_secret": "GOCSPX-live-prod-secret-9921",
                        "refresh_token": "1//04live_refresh_token"
                    }),
                    config={
                        "domain": "enterprise.com",
                        "service_account": "ops-bot@enterprise.com",
                        "timeout_seconds": 10,
                        "max_retries": 3,
                        "rate_limit_per_minute": 60
                    },
                    last_health_check={
                        "status": "CONNECTED",
                        "latency_ms": 31.0,
                        "message": "Google Workspace API operational. Mailbox authorized.",
                        "last_checked_at": "2026-11-02T12:00:00Z"
                    },
                    metrics={
                        "total_requests": 19,
                        "successful_requests": 19,
                        "failed_requests": 0,
                        "consecutive_failures": 0,
                        "rate_limited_count": 0
                    }
                )
            ]
            db.add_all(connections)
            db.commit()

    finally:
        db.close()
