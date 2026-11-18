"""
AVENTRA Enterprise ERP Integration & Reconciliation API.
Provides REST endpoints for:
- Vendor, Purchase Order, Invoice, and Goods Receipt read/create/update operations
- 3-Way Reconciliation connecting Model M5, M7, and M8
- Exception handling for missing documents, duplicates, and financial variances
- Governance approval policies and single-use cryptographic nonces for high-privilege writes
- Multi-schema support (SAP ERP / Company B ERP vs Oracle NetSuite ERP)
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.connectors.base import ConnectorQuery
from backend.connectors.erp_adapters import (
    SAPERPAdapter,
    NetSuiteERPAdapter,
    SUPPORTED_CURRENCIES,
    validate_currency
)
from backend.connectors.erp_reconciliation import ERPReconciliationEngine
from backend.connectors.resilience import PermissionDeniedError
from backend.security.audit import append_audit_entry

router = APIRouter(prefix="/api/erp", tags=["Enterprise ERP Integration"])


# ==========================================
# SCHEMAS
# ==========================================

class CreateVendorRequest(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=200)
    business_address: Optional[str] = ""
    country: str = "US"
    tax_number: Optional[str] = None
    contact_email: Optional[str] = None
    payment_terms: str = "Net30"
    currency: str = "USD"
    adapter: str = "COMPANY_B_ERP"


class CreatePurchaseOrderRequest(BaseModel):
    po_number: str = Field(..., min_length=2)
    vendor_id: str = Field(..., min_length=2)
    vendor_name: Optional[str] = None
    order_date: Optional[str] = None
    total_amount: float = Field(..., gt=0)
    tax_amount: float = Field(default=0.0, ge=0)
    currency: str = "USD"
    payment_terms: str = "Net30"
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    adapter: str = "COMPANY_B_ERP"


class CreateInvoiceRequest(BaseModel):
    invoice_number: str = Field(..., min_length=2)
    po_number: str = Field(..., min_length=2)
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    subtotal: float = Field(..., gt=0)
    tax_amount: float = Field(default=0.0, ge=0)
    total_amount: float = Field(..., gt=0)
    currency: str = "USD"
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    adapter: str = "COMPANY_B_ERP"


class CreateGoodsReceiptRequest(BaseModel):
    gr_number: str = Field(..., min_length=2)
    po_number: str = Field(..., min_length=2)
    vendor_id: Optional[str] = None
    received_date: Optional[str] = None
    carrier_tracking: Optional[str] = None
    received_items: List[Dict[str, Any]] = Field(default_factory=list)
    adapter: str = "COMPANY_B_ERP"


class RunReconciliationPayload(BaseModel):
    invoice_data: Dict[str, Any]
    tolerance_pct: float = 2.0
    max_currency_tolerance: float = 50.0
    adapter: str = "COMPANY_B_ERP"


class ExtractAndReconcilePayload(BaseModel):
    document_text: str
    filename: Optional[str] = "invoice.pdf"
    tolerance_pct: float = 2.0


class RequestReconciliationApprovalPayload(BaseModel):
    execution_id: str
    invoice_number: str
    po_number: str
    reconciliation_result: Dict[str, Any]


class ExecuteAuthorizedPaymentPayload(BaseModel):
    approval_id: str
    reviewer_name: str
    reviewer_role: str
    adapter: str = "COMPANY_B_ERP"


def _get_erp_adapter(adapter_name: str, db: Session):
    norm = adapter_name.upper()
    if "NETSUITE" in norm:
        return NetSuiteERPAdapter(db)
    return SAPERPAdapter(db)


# ==========================================
# ENDPOINTS
# ==========================================

@router.get("/schemas")
def get_supported_erp_schemas(record_type: str = Query("vendor"), adapter: str = Query("COMPANY_B_ERP"), db: Session = Depends(get_db)):
    erp = _get_erp_adapter(adapter, db)
    return erp.discover_schema(record_type)


@router.get("/vendors")
def list_vendors(
    adapter: str = Query("COMPANY_B_ERP"),
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    incremental_since: Optional[str] = None,
    db: Session = Depends(get_db)
):
    erp = _get_erp_adapter(adapter, db)
    res = erp.read_records(ConnectorQuery(
        record_type="vendor",
        filters={"search": search, "status": status_filter} if (search or status_filter) else {},
        limit=limit,
        cursor=cursor,
        incremental_since=incremental_since
    ))
    return res.model_dump()


@router.post("/vendors", status_code=status.HTTP_201_CREATED)
def create_vendor(req: CreateVendorRequest, db: Session = Depends(get_db)):
    erp = _get_erp_adapter(req.adapter, db)
    try:
        res = erp.create_record("vendor", req.model_dump())
        return res.model_dump()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.get("/purchase-orders")
def list_purchase_orders(
    adapter: str = Query("COMPANY_B_ERP"),
    search: Optional[str] = None,
    vendor_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    incremental_since: Optional[str] = None,
    db: Session = Depends(get_db)
):
    erp = _get_erp_adapter(adapter, db)
    filters = {}
    if search:
        filters["search"] = search
    if vendor_id:
        filters["vendor_id"] = vendor_id
    res = erp.read_records(ConnectorQuery(
        record_type="purchase_order",
        filters=filters,
        limit=limit,
        cursor=cursor,
        incremental_since=incremental_since
    ))
    return res.model_dump()


@router.get("/purchase-orders/{po_number}")
def get_purchase_order(po_number: str, adapter: str = Query("COMPANY_B_ERP"), db: Session = Depends(get_db)):
    erp = _get_erp_adapter(adapter, db)
    rec = erp.get_record_by_id("purchase_order", po_number)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Purchase order '{po_number}' not found.")
    return rec


@router.post("/purchase-orders", status_code=status.HTTP_201_CREATED)
def create_purchase_order(req: CreatePurchaseOrderRequest, db: Session = Depends(get_db)):
    erp = _get_erp_adapter(req.adapter, db)
    try:
        res = erp.create_record("purchase_order", req.model_dump())
        return res.model_dump()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.get("/invoices")
def list_invoices(
    adapter: str = Query("COMPANY_B_ERP"),
    search: Optional[str] = None,
    po_number: Optional[str] = None,
    vendor_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    incremental_since: Optional[str] = None,
    db: Session = Depends(get_db)
):
    erp = _get_erp_adapter(adapter, db)
    filters = {}
    if search:
        filters["search"] = search
    if po_number:
        filters["po_number"] = po_number
    if vendor_id:
        filters["vendor_id"] = vendor_id
    if status_filter:
        filters["status"] = status_filter

    res = erp.read_records(ConnectorQuery(
        record_type="invoice",
        filters=filters,
        limit=limit,
        cursor=cursor,
        incremental_since=incremental_since
    ))
    return res.model_dump()


@router.get("/invoices/{invoice_number}")
def get_invoice(invoice_number: str, adapter: str = Query("COMPANY_B_ERP"), db: Session = Depends(get_db)):
    erp = _get_erp_adapter(adapter, db)
    rec = erp.get_record_by_id("invoice", invoice_number)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_number}' not found.")
    return rec


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
def create_invoice(req: CreateInvoiceRequest, db: Session = Depends(get_db)):
    erp = _get_erp_adapter(req.adapter, db)
    try:
        res = erp.create_record("invoice", req.model_dump())
        return res.model_dump()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.get("/goods-receipts")
def list_goods_receipts(
    adapter: str = Query("COMPANY_B_ERP"),
    search: Optional[str] = None,
    po_number: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    incremental_since: Optional[str] = None,
    db: Session = Depends(get_db)
):
    erp = _get_erp_adapter(adapter, db)
    filters = {}
    if search:
        filters["search"] = search
    if po_number:
        filters["po_number"] = po_number

    res = erp.read_records(ConnectorQuery(
        record_type="goods_receipt",
        filters=filters,
        limit=limit,
        cursor=cursor,
        incremental_since=incremental_since
    ))
    return res.model_dump()


@router.get("/goods-receipts/{gr_number}")
def get_goods_receipt(gr_number: str, adapter: str = Query("COMPANY_B_ERP"), db: Session = Depends(get_db)):
    erp = _get_erp_adapter(adapter, db)
    rec = erp.get_record_by_id("goods_receipt", gr_number)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Goods receipt '{gr_number}' not found.")
    return rec


@router.post("/goods-receipts", status_code=status.HTTP_201_CREATED)
def create_goods_receipt(req: CreateGoodsReceiptRequest, db: Session = Depends(get_db)):
    erp = _get_erp_adapter(req.adapter, db)
    try:
        res = erp.create_record("goods_receipt", req.model_dump())
        return res.model_dump()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


# ==========================================
# RECONCILIATION & ML ENDPOINTS
# ==========================================

@router.post("/reconciliation/run")
def run_reconciliation(req: RunReconciliationPayload, db: Session = Depends(get_db)):
    """
    Executes 3-way matching across live PO, Invoice, and Goods Receipt using Model M5 & M8.
    """
    engine = ERPReconciliationEngine(db)
    res = engine.run_three_way_reconciliation(
        invoice_data=req.invoice_data,
        tolerance_pct=req.tolerance_pct,
        max_currency_tolerance=req.max_currency_tolerance,
        adapter_type=req.adapter
    )
    return res


@router.post("/reconciliation/extract-and-reconcile")
def extract_and_reconcile(req: ExtractAndReconcilePayload, db: Session = Depends(get_db)):
    """
    Extracts invoice tokens via Model M7 (Document Intelligence OCR) and feeds them into
    Model M5 3-Way Reconciliation and Model M8 Anomaly Detection.
    """
    engine = ERPReconciliationEngine(db)
    res = engine.extract_and_reconcile_document(
        document_text=req.document_text,
        filename=req.filename or "invoice.txt",
        tolerance_pct=req.tolerance_pct
    )
    return res


@router.post("/reconciliation/request-approval")
def request_reconciliation_approval(req: RequestReconciliationApprovalPayload, db: Session = Depends(get_db)):
    """
    Submits a discrepant or anomalous invoice to the Governance Approval Gate, generating
    a single-use 64-character cryptographic nonce.
    """
    engine = ERPReconciliationEngine(db)
    appr = engine.submit_reconciliation_approval_request(
        execution_id=req.execution_id,
        invoice_number=req.invoice_number,
        po_number=req.po_number,
        reconciliation_result=req.reconciliation_result
    )
    return {
        "status": "APPROVAL_REQUIRED",
        "approval_id": appr.id,
        "nonce_token": appr.nonce_token,
        "risk_level": appr.risk_level
    }


@router.post("/reconciliation/execute-authorized-payment")
def execute_authorized_payment(req: ExecuteAuthorizedPaymentPayload, db: Session = Depends(get_db)):
    """
    Executes authorized ERP payment write and records the block into the tamper-evident
    cryptographic audit ledger.
    """
    engine = ERPReconciliationEngine(db)
    try:
        res = engine.execute_authorized_payment(
            approval_id=req.approval_id,
            reviewer_name=req.reviewer_name,
            reviewer_role=req.reviewer_role,
            adapter_type=req.adapter
        )
        return res
    except PermissionDeniedError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

