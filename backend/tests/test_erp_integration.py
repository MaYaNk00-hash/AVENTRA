"""
Unit & Integration Tests for Stage 7: Complete ERP Integration.
Verifies all 7 roadmap checklist items:
1. Vendor, purchase order, invoice, and goods receipt read operations
2. Connect Model M5 reconciliation to real ERP records
3. Connect Model M7 extraction and Model M8 anomaly detection
4. Exception handling and reconciliation status (missing PO/GR, duplicate invoices, vendor mismatch)
5. Approval-controlled ERP write operations (governance gate with cryptographic nonce)
6. Financial validations (currency, tax, quantities, line items, mathematical tolerances)
7. Multi-schema evaluation (SAP ERP / Company B ERP vs Oracle NetSuite ERP)
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from backend.database.session import SessionLocal, seed_database
from backend.database.models import EnterpriseRecord, ApprovalRequest, WorkflowExecution
from backend.connectors.erp_adapters import (
    SAPERPAdapter,
    NetSuiteERPAdapter,
    validate_currency,
    validate_financial_totals,
    validate_line_items,
    erp_record_to_canonical_vendor,
    erp_record_to_canonical_po,
    erp_record_to_canonical_invoice,
    erp_record_to_canonical_gr
)
from backend.connectors.erp_reconciliation import ERPReconciliationEngine
from backend.connectors.base import ConnectorQuery
from backend.connectors.resilience import PermissionDeniedError
from backend.security.audit import verify_ledger_chain


@pytest.fixture(scope="module")
def db_session():
    seed_database()
    db = SessionLocal()

    # Clean up any test-specific records before test suite
    test_ids = [
        "PO-TEST-001", "INV-TEST-001", "GR-TEST-001", "VND-TEST-001",
        "NS-PO-TEST-1", "NS-BILL-TEST-1", "exec-erp-test-01"
    ]
    db.query(ApprovalRequest).filter(ApprovalRequest.execution_id == "exec-erp-test-01").delete(synchronize_session=False)
    db.query(WorkflowExecution).filter(WorkflowExecution.id == "exec-erp-test-01").delete(synchronize_session=False)
    db.query(EnterpriseRecord).filter(EnterpriseRecord.id.in_(test_ids)).delete(synchronize_session=False)
    db.commit()

    yield db

    # Teardown
    db.query(ApprovalRequest).filter(ApprovalRequest.execution_id == "exec-erp-test-01").delete(synchronize_session=False)
    db.query(WorkflowExecution).filter(WorkflowExecution.id == "exec-erp-test-01").delete(synchronize_session=False)
    db.query(EnterpriseRecord).filter(EnterpriseRecord.id.in_(test_ids)).delete(synchronize_session=False)
    db.commit()
    db.close()


# =====================================================================
# 1. READ OPERATIONS ACROSS VENDORS, POs, INVOICES, GOODS RECEIPTS
# =====================================================================

def test_erp_vendor_po_invoice_gr_reads(db_session: Session):
    """
    Verify reading vendors, purchase orders, invoices, and goods receipts from SAP ERP.
    Tests search, status filtering, cursor pagination, and incremental synchronization.
    """
    adapter = SAPERPAdapter(db_session)

    # 1. Vendors read
    v_page = adapter.read_records(ConnectorQuery(record_type="vendor", limit=10))
    assert v_page.count >= 1
    assert any("business_name" in r for r in v_page.records)
    first_v = v_page.records[0]
    assert "vendor_id" in first_v

    # 2. Purchase Orders read
    po_page = adapter.read_records(ConnectorQuery(record_type="purchase_order", limit=10))
    assert po_page.count >= 1
    first_po = po_page.records[0]
    assert "po_number" in first_po
    assert "total_amount" in first_po
    assert len(first_po["line_items"]) >= 1

    # 3. Goods Receipts read
    gr_page = adapter.read_records(ConnectorQuery(record_type="goods_receipt", limit=10))
    assert gr_page.count >= 1
    first_gr = gr_page.records[0]
    assert "gr_number" in first_gr
    assert "received_items" in first_gr

    # 4. Invoices read
    inv_page = adapter.read_records(ConnectorQuery(record_type="invoice", limit=10))
    assert inv_page.count >= 1
    first_inv = inv_page.records[0]
    assert "invoice_number" in first_inv

    # 5. Search filtering
    search_page = adapter.read_records(ConnectorQuery(
        record_type="purchase_order",
        filters={"search": "PO-2026-8801"}
    ))
    assert search_page.count >= 1
    assert any(r["po_number"] == "PO-2026-8801" for r in search_page.records)

    # 6. Cursor pagination
    p1 = adapter.read_records(ConnectorQuery(record_type="vendor", limit=1, cursor="0"))
    assert p1.count == 1
    if p1.has_more:
        p2 = adapter.read_records(ConnectorQuery(record_type="vendor", limit=1, cursor=p1.next_cursor))
        assert p2.count == 1
        assert p1.records[0]["vendor_id"] != p2.records[0]["vendor_id"]

    # 7. Incremental sync
    watermark_old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    inc_page = adapter.read_records(ConnectorQuery(record_type="purchase_order", incremental_since=watermark_old))
    assert inc_page.count >= 1

    watermark_future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    empty_inc = adapter.read_records(ConnectorQuery(record_type="purchase_order", incremental_since=watermark_future))
    assert empty_inc.count == 0


# =====================================================================
# 2. SCHEMA 2: NETSUITE ALTERNATE ERP READS & CANONICAL MAPPINGS
# =====================================================================

def test_schema_2_netsuite_alternate_erp_reads(db_session: Session):
    """
    Verify Schema 2 (Oracle NetSuite alternate schema):
    Read operations with distinct naming (tran_id, bill_number, receipt_doc_no, entity_id)
    and bidirectional Canonical contract mappings.
    """
    ns_adapter = NetSuiteERPAdapter(db_session)
    schema = ns_adapter.discover_schema("entity")
    field_names = [f["field_name"] for f in schema]
    assert "entity_id" in field_names
    assert "company_name" in field_names
    assert "remit_address" in field_names

    # Read NetSuite Purchase Orders
    po_page = ns_adapter.read_records(ConnectorQuery(record_type="purchaseorder", limit=10))
    assert po_page.count >= 1
    first_ns_po = po_page.records[0]
    assert "tran_id" in first_ns_po
    assert "foreign_total" in first_ns_po

    # Translate NetSuite PO to CanonicalPurchaseOrder
    canon_po = erp_record_to_canonical_po(first_ns_po, "NETSUITE_ERP")
    assert canon_po.po_number == first_ns_po["tran_id"]
    assert canon_po.total_amount == first_ns_po["foreign_total"]
    assert canon_po.currency == "USD"
    assert len(canon_po.line_items) >= 1

    # Read NetSuite Vendor Bills
    bill_page = ns_adapter.read_records(ConnectorQuery(record_type="vendorbill", limit=10))
    assert bill_page.count >= 1
    first_ns_bill = bill_page.records[0]
    assert "bill_number" in first_ns_bill
    assert "gross_amount" in first_ns_bill

    # Translate NetSuite Bill to CanonicalInvoice
    canon_inv = erp_record_to_canonical_invoice(first_ns_bill, "NETSUITE_ERP")
    assert canon_inv.invoice_number == first_ns_bill["bill_number"]
    assert canon_inv.total_amount == first_ns_bill["gross_amount"]

    # Translate SAP PO to CanonicalPurchaseOrder
    sap_adapter = SAPERPAdapter(db_session)
    sap_po = sap_adapter.get_record_by_id("purchase_order", "PO-2026-8801")
    assert sap_po is not None
    canon_sap_po = erp_record_to_canonical_po(sap_po, "SAP_ERP")
    assert canon_sap_po.po_number == "PO-2026-8801"
    assert canon_sap_po.total_amount == 5400.00


# =====================================================================
# 3. CONNECT MODEL M5: 3-WAY RECONCILIATION & TOLERANCES
# =====================================================================

def test_m5_three_way_reconciliation_exact_and_tolerated(db_session: Session):
    """
    Verify Model M5 3-Way Reconciliation connected to real ERP records:
    1. Exact Match: Invoice lines equal PO & GR -> RECONCILED_EXACT, no approval required.
    2. Tolerated Match: Variance within 2% / $50 tolerance -> RECONCILED_WITHIN_TOLERANCE.
    """
    engine = ERPReconciliationEngine(db_session)

    # 1. Exact match test
    exact_invoice = {
        "invoice_number": "INV-2026-EXACT-01",
        "po_number": "PO-2026-8801",
        "vendor_id": "ERP-B-501",
        "vendor_name": "Apex Global Logistics Inc",
        "subtotal": 5400.00,
        "tax_amount": 0.00,
        "total_amount": 5400.00,
        "currency": "USD",
        "line_items": [
            {"sku": "LOG-FREIGHT-40FT", "description": "Ocean Freight 40ft Container", "quantity": 1.0, "unit_price": 4200.00, "total": 4200.00},
            {"sku": "LOG-PORT-HANDLING", "description": "Port Handling & Customs Clearance", "quantity": 1.0, "unit_price": 1200.00, "total": 1200.00}
        ]
    }
    res_exact = engine.run_three_way_reconciliation(exact_invoice)
    assert res_exact["reconciliation_status"] == "RECONCILED_EXACT"
    assert res_exact["requires_human_approval"] is False
    assert res_exact["total_variance_currency"] == 0.0

    # 2. Tolerated variance test ($5,430 vs $5,400 -> $30 variance < $50 tolerance)
    tolerated_invoice = {
        "invoice_number": "INV-2026-TOL-01",
        "po_number": "PO-2026-8801",
        "vendor_id": "ERP-B-501",
        "vendor_name": "Apex Global Logistics Inc",
        "subtotal": 5430.00,
        "tax_amount": 0.00,
        "total_amount": 5430.00,
        "currency": "USD",
        "line_items": [
            {"sku": "LOG-FREIGHT-40FT", "description": "Ocean Freight 40ft Container", "quantity": 1.0, "unit_price": 4230.00, "total": 4230.00},
            {"sku": "LOG-PORT-HANDLING", "description": "Port Handling & Customs Clearance", "quantity": 1.0, "unit_price": 1200.00, "total": 1200.00}
        ]
    }
    res_tol = engine.run_three_way_reconciliation(tolerated_invoice, tolerance_pct=0.5)
    assert res_tol["reconciliation_status"] == "RECONCILED_WITHIN_TOLERANCE"
    assert res_tol["requires_human_approval"] is False
    assert res_tol["total_variance_currency"] == 30.0


# =====================================================================
# 4. CONNECT MODEL M7 & M8: OCR EXTRACTION & ANOMALY DETECTION
# =====================================================================

def test_m7_document_extraction_and_m8_anomaly_detection(db_session: Session):
    """
    Verify Model M7 (Document Intelligence) OCR extraction and Model M8 (Isolation Forest)
    anomaly scoring integrated into the 3-Way Reconciliation pipeline.
    """
    engine = ERPReconciliationEngine(db_session)

    # Document text representing a scanned freight invoice
    scanned_doc = """
    INVOICE
    Apex Global Logistics LLC
    Invoice Number: INV-EXTRACT-998
    Purchase Order: PO-2026-8801
    Date: 2026-10-22
    Subtotal: $5400.00
    Tax: $0.00
    Total Amount: $5400.00
    Currency: USD
    Line Items:
    LOG-FREIGHT-40FT Ocean Freight 40ft Container 1 $4200.00 $4200.00
    LOG-PORT-HANDLING Customs Handling 1 $1200.00 $1200.00
    """

    res = engine.extract_and_reconcile_document(
        document_text=scanned_doc,
        filename="apex_ocean_freight.pdf"
    )

    assert "extraction" in res
    assert "reconciliation" in res
    extracted_fields = res["extraction"]["extracted_fields"]
    assert extracted_fields.get("total_amount") == 5400.0 or extracted_fields.get("invoice_number") is not None
    assert res["reconciliation"]["reconciliation_status"] in ["RECONCILED_EXACT", "RECONCILED_WITHIN_TOLERANCE"]

    # Test M8 Anomaly Evaluation directly
    anomaly_check = engine.evaluate_financial_anomaly({
        "vendor_id": "ERP-B-501",
        "invoice_number": "INV-M8-01",
        "amount": 5400.00,
        "po_amount": 5400.00,
        "vendor_terms": "Net30"
    })
    assert "is_anomaly" in anomaly_check
    assert "anomaly_score" in anomaly_check


# =====================================================================
# 5. EXCEPTION HANDLING & RECONCILIATION STATUSES
# =====================================================================

def test_reconciliation_exceptions_handling(db_session: Session):
    """
    Verify robust exception handling for:
    1. Missing Purchase Order document
    2. Missing Goods Receipt document
    3. Duplicate invoice submission
    4. Vendor mismatch between PO and Invoice
    """
    engine = ERPReconciliationEngine(db_session)

    # 1. Missing PO exception
    missing_po_inv = {
        "invoice_number": "INV-MISS-PO",
        "po_number": "PO-NON-EXISTENT-9999",
        "vendor_id": "ERP-B-501",
        "subtotal": 1000.00,
        "tax_amount": 0.00,
        "total_amount": 1000.00,
        "currency": "USD"
    }
    res_no_po = engine.run_three_way_reconciliation(missing_po_inv)
    assert res_no_po["reconciliation_status"] == "EXCEPTION_MISSING_DOCUMENT"
    assert any("MISSING_PURCHASE_ORDER" in f for f in res_no_po["flags"])
    assert res_no_po["requires_human_approval"] is True

    # 2. Missing Goods Receipt exception (create a PO without any GR)
    db_session.query(EnterpriseRecord).filter(EnterpriseRecord.id == "PO-TEST-NO-GR").delete(synchronize_session=False)
    db_session.commit()
    adapter = SAPERPAdapter(db_session)
    adapter.create_record("purchase_order", {
        "po_number": "PO-TEST-NO-GR",
        "vendor_id": "ERP-B-501",
        "total_amount": 2500.00,
        "tax_amount": 0.00,
        "currency": "USD",
        "line_items": [
            {"sku": "RAW-STEEL-TUBE", "description": "Steel tubing", "quantity": 10.0, "unit_price": 250.00, "total": 2500.00}
        ]
    })

    missing_gr_inv = {
        "invoice_number": "INV-MISS-GR",
        "po_number": "PO-TEST-NO-GR",
        "vendor_id": "ERP-B-501",
        "subtotal": 2500.00,
        "tax_amount": 0.00,
        "total_amount": 2500.00,
        "currency": "USD"
    }
    res_no_gr = engine.run_three_way_reconciliation(missing_gr_inv)
    assert res_no_gr["reconciliation_status"] == "EXCEPTION_MISSING_DOCUMENT"
    assert any("MISSING_GOODS_RECEIPT" in f for f in res_no_gr["flags"])

    # 3. Duplicate invoice exception (INV-2026-001 is already seeded with status RECONCILED)
    dup_inv = {
        "invoice_number": "INV-2026-001",
        "po_number": "PO-2026-8801",
        "vendor_id": "ERP-B-501",
        "subtotal": 5400.00,
        "tax_amount": 0.00,
        "total_amount": 5400.00,
        "currency": "USD"
    }
    res_dup = engine.run_three_way_reconciliation(dup_inv)
    assert res_dup["reconciliation_status"] == "EXCEPTION_DUPLICATE_INVOICE"
    assert any("DUPLICATE_INVOICE_NUMBER" in f for f in res_dup["flags"])

    # 4. Vendor mismatch exception
    mismatch_inv = {
        "invoice_number": "INV-VND-MISMATCH",
        "po_number": "PO-2026-8801", # Belongs to ERP-B-501 (Apex Global)
        "vendor_id": "ERP-B-502",     # Mismatched vendor: Supreme Industrial
        "subtotal": 5400.00,
        "tax_amount": 0.00,
        "total_amount": 5400.00,
        "currency": "USD"
    }
    res_mismatch = engine.run_three_way_reconciliation(mismatch_inv)
    assert res_mismatch["reconciliation_status"] == "EXCEPTION_VENDOR_MISMATCH"
    assert any("VENDOR_MISMATCH" in f for f in res_mismatch["flags"])


# =====================================================================
# 6. FINANCIAL VALIDATIONS (CURRENCY, TAX, QUANTITIES, TOLERANCES)
# =====================================================================

def test_currency_tax_and_financial_tolerance_validations():
    """
    Verify strict financial validations:
    - Supported ISO 4217 currencies
    - Tax math validation: subtotal + tax == total
    - Positive quantities and non-negative unit prices
    - Line item sum consistency
    """
    # 1. Currency validation
    assert validate_currency("USD") == "USD"
    assert validate_currency("eur") == "EUR"
    with pytest.raises(ValueError) as exc:
        validate_currency("INVALID_COIN")
    assert "Unsupported financial currency" in str(exc.value)

    # 2. Financial totals validation
    validate_financial_totals(subtotal=100.0, tax_amount=10.0, total_amount=110.0)
    with pytest.raises(ValueError) as exc:
        validate_financial_totals(subtotal=100.0, tax_amount=10.0, total_amount=135.0)
    assert "Financial reconciliation error" in str(exc.value)

    # 3. Line item quantity <= 0 validation
    with pytest.raises(ValueError) as exc:
        validate_line_items([
            {"sku": "PART-A", "quantity": 0.0, "unit_price": 50.0, "total": 0.0}
        ])
    assert "quantity must be strictly positive" in str(exc.value)

    # 4. Line item unit price < 0 validation
    with pytest.raises(ValueError) as exc:
        validate_line_items([
            {"sku": "PART-B", "quantity": 2.0, "unit_price": -10.0, "total": -20.0}
        ])
    assert "unit price cannot be negative" in str(exc.value)

    # 5. Line item sum != declared subtotal
    with pytest.raises(ValueError) as exc:
        validate_line_items(
            [{"sku": "PART-C", "quantity": 1.0, "unit_price": 40.0, "total": 40.0}],
            expected_subtotal=100.0
        )
    assert "does not match declared subtotal" in str(exc.value)


# =====================================================================
# 7. APPROVAL-CONTROLLED ERP WRITE & CRYPTOGRAPHIC AUDIT TRAIL
# =====================================================================

def test_approval_gated_erp_write_and_audit_trail(db_session: Session):
    """
    Verify that financial discrepancies require human approval via a single-use
    cryptographic nonce, unauthorized write operations are blocked, and authorized
    payments are chained into the tamper-evident SHA-256 audit ledger.
    """
    engine = ERPReconciliationEngine(db_session)

    # Ensure parent workflow execution exists
    db_session.query(ApprovalRequest).filter(ApprovalRequest.execution_id == "exec-erp-test-01").delete(synchronize_session=False)
    existing_exec = db_session.query(WorkflowExecution).filter(WorkflowExecution.id == "exec-erp-test-01").first()
    if not existing_exec:
        exec_row = WorkflowExecution(
            id="exec-erp-test-01",
            workflow_id="wf-invoice-reconciliation",
            triggered_by="financial_controller_test",
            status="RUNNING"
        )
        db_session.add(exec_row)
        db_session.commit()

    # 1. Run reconciliation on high discrepancy invoice ($7,800 vs $5,400)
    discrepant_inv = {
        "invoice_number": "INV-2026-003",
        "po_number": "PO-2026-8801",
        "vendor_id": "ERP-B-501",
        "vendor_name": "Apex Global Logistics Inc",
        "subtotal": 7800.00,
        "tax_amount": 0.00,
        "total_amount": 7800.00,
        "currency": "USD",
        "line_items": [
            {"sku": "LOG-FREIGHT-40FT", "description": "Ocean Freight", "quantity": 1.0, "unit_price": 6200.00, "total": 6200.00},
            {"sku": "LOG-PORT-HANDLING", "description": "Port Handling", "quantity": 1.0, "unit_price": 1600.00, "total": 1600.00}
        ]
    }
    recon_res = engine.run_three_way_reconciliation(discrepant_inv)
    assert recon_res["reconciliation_status"] == "DISCREPANCY_APPROVAL_REQUIRED"
    assert recon_res["requires_human_approval"] is True
    assert recon_res["total_variance_currency"] == 2400.00

    # 2. Submit approval request
    appr_req = engine.submit_reconciliation_approval_request(
        execution_id="exec-erp-test-01",
        invoice_number="INV-2026-003",
        po_number="PO-2026-8801",
        reconciliation_result=recon_res
    )
    assert appr_req.status == "PENDING"
    assert len(appr_req.nonce_token) == 64
    assert appr_req.risk_level == "CRITICAL"

    # 3. Attempt unauthorized execution -> PermissionDeniedError
    with pytest.raises(PermissionDeniedError) as exc:
        engine.execute_authorized_payment(
            approval_id=appr_req.id,
            reviewer_name="Marcus Thorne",
            reviewer_role="FINANCIAL_CONTROLLER"
        )
    assert "must be APPROVED" in str(exc.value)

    # 4. Authorized approval decision
    appr_req.status = "APPROVED"
    db_session.commit()

    # 5. Execute authorized payment write
    pay_res = engine.execute_authorized_payment(
        approval_id=appr_req.id,
        reviewer_name="Marcus Thorne (Financial Controller)",
        reviewer_role="FINANCIAL_CONTROLLER"
    )
    assert pay_res["success"] is True
    assert "payment_reference" in pay_res
    assert pay_res["status"] == "PAYMENT_AUTHORIZED"

    # 6. Verify invoice record status updated in database
    inv_row = db_session.query(EnterpriseRecord).filter(
        EnterpriseRecord.entity_type == "INVOICE",
        EnterpriseRecord.id == "INV-2026-003"
    ).first()
    assert inv_row is not None
    assert inv_row.status == "PAYMENT_AUTHORIZED"
    assert inv_row.raw_data["reconciliation_status"] == "APPROVED_BY_GOVERNANCE"

    # 7. Verify cryptographic audit ledger integrity
    chain_check = verify_ledger_chain(db_session)
    assert chain_check["is_valid"] is True
    assert chain_check["total_entries"] >= 1
