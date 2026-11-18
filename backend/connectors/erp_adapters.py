"""
Enterprise ERP Integration Adapters.
Provides multi-schema connectors and validation engines for ERP systems:
1. SAP ERP Adapter (Standard Enterprise Schema: Vendors, POs, Invoices, Goods Receipts)
2. NetSuite ERP Adapter (Alternate Enterprise Schema: Entities, Transactions, Bills, Item Receipts)
3. Bidirectional Canonical Contract Translation (CanonicalVendor, CanonicalPurchaseOrder, CanonicalInvoice, CanonicalGoodsReceipt)
4. Financial validations: Currency codes (ISO 4217), tax calculations, unit price/quantity bounds, and tolerance checking.
"""

import re
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from backend.database.models import EnterpriseRecord
from backend.connectors.base import (
    BaseEnterpriseConnector,
    ConnectorType,
    ConnectorStatus,
    ConnectorHealth,
    ConnectorQuery,
    ConnectorPage,
    ConnectorOperationResult
)
from backend.contracts.canonical import (
    CanonicalVendor,
    CanonicalPurchaseOrder,
    CanonicalInvoice,
    CanonicalGoodsReceipt,
    CanonicalLineItem
)

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "JPY", "INR", "AUD", "CHF", "SGD"}


def validate_currency(currency: str) -> str:
    curr = (currency or "USD").upper().strip()
    if curr not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported financial currency '{curr}'. Supported: {', '.join(sorted(SUPPORTED_CURRENCIES))}")
    return curr


def validate_financial_totals(subtotal: float, tax_amount: float, total_amount: float, tolerance: float = 0.05) -> None:
    expected_total = subtotal + tax_amount
    if abs(expected_total - total_amount) > tolerance:
        raise ValueError(
            f"Financial reconciliation error: Subtotal ({subtotal:.2f}) + Tax ({tax_amount:.2f}) = {expected_total:.2f}, "
            f"which does not match Total Amount ({total_amount:.2f}) within tolerance ${tolerance}."
        )


def validate_line_items(line_items: List[Dict[str, Any]], expected_subtotal: Optional[float] = None, tolerance: float = 0.05) -> None:
    if not line_items:
        raise ValueError("Line items list cannot be empty.")

    computed_subtotal = 0.0
    for idx, item in enumerate(line_items):
        sku = item.get("sku") or item.get("item_code") or item.get("sku_or_code") or item.get("item_ref")
        if not sku:
            raise ValueError(f"Line item #{idx+1} is missing mandatory SKU or item identifier.")

        qty = float(item.get("quantity") or item.get("qty") or 0.0)
        if qty <= 0:
            raise ValueError(f"Line item #{idx+1} ('{sku}') quantity must be strictly positive (got {qty}).")

        unit_price = float(item.get("unit_price") or item.get("rate") or 0.0)
        if unit_price < 0:
            raise ValueError(f"Line item #{idx+1} ('{sku}') unit price cannot be negative (got {unit_price}).")

        item_total = float(item.get("total") or item.get("total_price") or item.get("amount") or (qty * unit_price))
        if abs((qty * unit_price) - item_total) > tolerance:
            raise ValueError(f"Line item #{idx+1} ('{sku}') math mismatch: {qty} * ${unit_price:.2f} != ${item_total:.2f}")

        computed_subtotal += item_total

    if expected_subtotal is not None and abs(computed_subtotal - expected_subtotal) > tolerance:
        raise ValueError(
            f"Line items sum (${computed_subtotal:.2f}) does not match declared subtotal (${expected_subtotal:.2f})."
        )


# =====================================================================
# 1. SAP ERP ADAPTER (Standard Enterprise Schema)
# =====================================================================

class SAPERPAdapter(BaseEnterpriseConnector):
    """
    Standard Enterprise ERP Connector conforming to SAP ERP nomenclature:
    - Vendors (Suppliers)
    - Purchase Orders (POs)
    - Invoices (Vendor Invoices)
    - Goods Receipts (GRs)
    """
    def __init__(self, db: Session, config: Optional[Dict[str, Any]] = None):
        cfg = config or {
            "endpoint": "https://sap.enterprise-internal.net/api/v2",
            "client_secret": "erp_sap_secret_key_88",
            "timeout_seconds": 15
        }
        super().__init__(
            connector_id="COMPANY_B_ERP",
            connector_type=ConnectorType.ERP,
            config=cfg
        )
        self.db = db
        self.system_id = "COMPANY_B_ERP"
        self.is_connected = True

    def connect(self) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        self.is_connected = False

    def test_connection(self) -> ConnectorHealth:
        start_time = datetime.now(timezone.utc)
        count = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id
        ).count()
        latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000.0
        return ConnectorHealth(
            connector_id=self.connector_id,
            connector_type=self.connector_type,
            status=ConnectorStatus.CONNECTED if self.is_connected else ConnectorStatus.DISCONNECTED,
            latency_ms=round(latency, 2),
            last_checked_at=datetime.now(timezone.utc).isoformat(),
            message=f"SAP ERP Connector live. {count} enterprise records discoverable."
        )

    def discover_schema(self, record_type: str = "vendor") -> List[Dict[str, Any]]:
        norm = record_type.lower()
        if norm in ["vendor", "vendors"]:
            return [
                {"field_name": "vendor_id", "data_type": "string", "is_primary_key": True, "nullable": False},
                {"field_name": "business_name", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "business_address", "data_type": "string", "is_primary_key": False, "nullable": True},
                {"field_name": "country", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "tax_number", "data_type": "string", "is_primary_key": False, "nullable": True},
                {"field_name": "contact_email", "data_type": "string", "is_primary_key": False, "nullable": True},
                {"field_name": "payment_terms", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "currency", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "status", "data_type": "string", "is_primary_key": False, "nullable": False}
            ]
        elif norm in ["purchase_order", "po", "purchase_orders"]:
            return [
                {"field_name": "po_number", "data_type": "string", "is_primary_key": True, "nullable": False},
                {"field_name": "vendor_id", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "vendor_name", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "order_date", "data_type": "datetime", "is_primary_key": False, "nullable": False},
                {"field_name": "currency", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "total_amount", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "tax_amount", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "status", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "line_items", "data_type": "array[object]", "is_primary_key": False, "nullable": False}
            ]
        elif norm in ["invoice", "invoices"]:
            return [
                {"field_name": "invoice_number", "data_type": "string", "is_primary_key": True, "nullable": False},
                {"field_name": "po_number", "data_type": "string", "is_primary_key": False, "nullable": True},
                {"field_name": "vendor_id", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "invoice_date", "data_type": "datetime", "is_primary_key": False, "nullable": False},
                {"field_name": "subtotal", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "tax_amount", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "total_amount", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "currency", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "status", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "line_items", "data_type": "array[object]", "is_primary_key": False, "nullable": False}
            ]
        else: # goods receipt
            return [
                {"field_name": "gr_number", "data_type": "string", "is_primary_key": True, "nullable": False},
                {"field_name": "po_number", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "received_date", "data_type": "datetime", "is_primary_key": False, "nullable": False},
                {"field_name": "status", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "received_items", "data_type": "array[object]", "is_primary_key": False, "nullable": False}
            ]

    def read_records(self, query: ConnectorQuery) -> ConnectorPage:
        rec_type = query.record_type.upper()
        entity_type_map = {
            "VENDOR": "VENDOR",
            "VENDORS": "VENDOR",
            "PURCHASE_ORDER": "PURCHASE_ORDER",
            "PURCHASE_ORDERS": "PURCHASE_ORDER",
            "PO": "PURCHASE_ORDER",
            "INVOICE": "INVOICE",
            "INVOICES": "INVOICE",
            "GOODS_RECEIPT": "GOODS_RECEIPT",
            "GOODS_RECEIPTS": "GOODS_RECEIPT",
            "GR": "GOODS_RECEIPT"
        }
        target_entity_type = entity_type_map.get(rec_type, "VENDOR")

        q = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id,
            EnterpriseRecord.entity_type == target_entity_type
        )

        filters = query.filters or {}
        search = filters.get("search")
        if search:
            q = q.filter(
                or_(
                    EnterpriseRecord.name.ilike(f"%{search}%"),
                    EnterpriseRecord.id.ilike(f"%{search}%"),
                    EnterpriseRecord.tax_identifier.ilike(f"%{search}%")
                )
            )

        status_filter = filters.get("status")
        if status_filter:
            q = q.filter(EnterpriseRecord.status == status_filter)

        vendor_id = filters.get("vendor_id")
        if vendor_id and target_entity_type in ["PURCHASE_ORDER", "INVOICE"]:
            q = q.filter(
                or_(
                    EnterpriseRecord.canonical_id == vendor_id,
                    EnterpriseRecord.raw_data["vendor_id"].as_string() == vendor_id
                )
            )

        po_number = filters.get("po_number")
        if po_number and target_entity_type in ["INVOICE", "GOODS_RECEIPT"]:
            q = q.filter(EnterpriseRecord.raw_data["po_number"].as_string() == po_number)

        # Incremental watermark
        if query.incremental_since:
            try:
                watermark_dt = datetime.fromisoformat(query.incremental_since.replace("Z", "+00:00"))
                if watermark_dt.tzinfo is not None:
                    watermark_dt = watermark_dt.replace(tzinfo=None)
                q = q.filter(EnterpriseRecord.updated_at >= watermark_dt)
            except Exception:
                pass

        # Cursor pagination
        offset = 0
        if query.cursor:
            try:
                offset = int(query.cursor)
            except ValueError:
                offset = 0

        total_count = q.count()
        records_raw = q.order_by(EnterpriseRecord.created_at.desc()).offset(offset).limit(query.limit).all()

        formatted = []
        for r in records_raw:
            raw = r.raw_data or {}
            if target_entity_type == "VENDOR":
                formatted.append({
                    "vendor_id": r.id,
                    "business_name": r.name,
                    "business_address": r.address,
                    "country": r.country,
                    "tax_number": r.tax_identifier,
                    "contact_email": r.contact_email,
                    "payment_terms": raw.get("payment_terms", "Net30"),
                    "currency": raw.get("currency", "USD"),
                    "canonical_id": r.canonical_id,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None
                })
            elif target_entity_type == "PURCHASE_ORDER":
                formatted.append({
                    "po_number": r.id,
                    "vendor_id": raw.get("vendor_id"),
                    "vendor_name": r.name,
                    "order_date": raw.get("order_date") or (r.created_at.isoformat() if r.created_at else None),
                    "total_amount": raw.get("total_amount", 0.0),
                    "tax_amount": raw.get("tax_amount", 0.0),
                    "currency": raw.get("currency", "USD"),
                    "payment_terms": raw.get("payment_terms", "Net30"),
                    "status": r.status,
                    "line_items": raw.get("line_items", []),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None
                })
            elif target_entity_type == "INVOICE":
                formatted.append({
                    "invoice_number": r.id,
                    "po_number": raw.get("po_number"),
                    "vendor_id": raw.get("vendor_id"),
                    "vendor_name": r.name,
                    "invoice_date": raw.get("invoice_date") or (r.created_at.isoformat() if r.created_at else None),
                    "due_date": raw.get("due_date"),
                    "subtotal": raw.get("subtotal", 0.0),
                    "tax_amount": raw.get("tax_amount", 0.0),
                    "total_amount": raw.get("total_amount", 0.0),
                    "currency": raw.get("currency", "USD"),
                    "status": r.status,
                    "line_items": raw.get("line_items", []),
                    "reconciliation_notes": raw.get("reconciliation_notes"),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None
                })
            elif target_entity_type == "GOODS_RECEIPT":
                formatted.append({
                    "gr_number": r.id,
                    "po_number": raw.get("po_number"),
                    "vendor_id": raw.get("vendor_id"),
                    "received_date": raw.get("received_date") or (r.created_at.isoformat() if r.created_at else None),
                    "status": r.status,
                    "received_items": raw.get("received_items", []),
                    "carrier_tracking": raw.get("carrier_tracking"),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None
                })

        next_cursor = str(offset + len(formatted)) if (offset + len(formatted)) < total_count else None
        return ConnectorPage(
            records=formatted,
            count=len(formatted),
            has_more=next_cursor is not None,
            next_cursor=next_cursor,
            total_count=total_count
        )

    def get_record_by_id(self, record_type: str, record_id: str) -> Optional[Dict[str, Any]]:
        page = self.read_records(ConnectorQuery(record_type=record_type, filters={"search": record_id}, limit=10))
        for r in page.records:
            cur_id = r.get("vendor_id") or r.get("po_number") or r.get("invoice_number") or r.get("gr_number")
            if cur_id == record_id:
                return r
        # Direct fallback by ID
        rec = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id,
            EnterpriseRecord.id == record_id
        ).first()
        if not rec:
            return None
        return rec.raw_data

    def create_record(self, record_type: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        norm = record_type.lower()
        if norm in ["vendor", "vendors"]:
            return self._create_vendor(data)
        elif norm in ["purchase_order", "po", "purchase_orders"]:
            return self._create_purchase_order(data)
        elif norm in ["invoice", "invoices"]:
            return self._create_invoice(data)
        elif norm in ["goods_receipt", "gr", "goods_receipts"]:
            return self._create_goods_receipt(data)
        else:
            raise ValueError(f"Unknown ERP record type '{record_type}'.")

    def _create_vendor(self, data: Dict[str, Any]) -> ConnectorOperationResult:
        name = (data.get("business_name") or data.get("vendor_name") or "").strip()
        if not name:
            raise ValueError("Vendor creation requires a valid 'business_name'.")

        curr = validate_currency(data.get("currency", "USD"))
        v_id = data.get("vendor_id") or f"ERP-VND-{self.db.query(EnterpriseRecord).count() + 101}"

        existing = self.db.query(EnterpriseRecord).filter(EnterpriseRecord.id == v_id).first()
        if existing:
            raise ValueError(f"Vendor '{v_id}' already exists.")

        rec = EnterpriseRecord(
            id=v_id,
            system_origin=self.system_id,
            entity_type="VENDOR",
            name=name,
            address=data.get("business_address", ""),
            country=data.get("country", "US"),
            tax_identifier=data.get("tax_number"),
            contact_email=data.get("contact_email"),
            status=data.get("status", "ACTIVE"),
            raw_data={
                "payment_terms": data.get("payment_terms", "Net30"),
                "currency": curr,
                "notes": data.get("notes", "")
            }
        )
        self.db.add(rec)
        self.db.commit()
        return ConnectorOperationResult(success=True, record_id=v_id, action="CREATE_VENDOR", details=data)

    def _create_purchase_order(self, data: Dict[str, Any]) -> ConnectorOperationResult:
        po_number = (data.get("po_number") or "").strip()
        if not po_number:
            raise ValueError("Purchase order creation requires 'po_number'.")

        vendor_id = (data.get("vendor_id") or "").strip()
        if not vendor_id:
            raise ValueError("Purchase order creation requires 'vendor_id'.")

        curr = validate_currency(data.get("currency", "USD"))
        total_amount = float(data.get("total_amount", 0.0))
        tax_amount = float(data.get("tax_amount", 0.0))
        subtotal = total_amount - tax_amount

        line_items = data.get("line_items", [])
        validate_line_items(line_items, expected_subtotal=subtotal if line_items else None)
        validate_financial_totals(subtotal, tax_amount, total_amount)

        existing = self.db.query(EnterpriseRecord).filter(EnterpriseRecord.id == po_number).first()
        if existing:
            raise ValueError(f"Purchase order '{po_number}' already exists.")

        vendor_name = data.get("vendor_name")
        if not vendor_name:
            v = self.db.query(EnterpriseRecord).filter(EnterpriseRecord.id == vendor_id).first()
            vendor_name = v.name if v else "Unknown Vendor"

        rec = EnterpriseRecord(
            id=po_number,
            system_origin=self.system_id,
            entity_type="PURCHASE_ORDER",
            name=vendor_name,
            status=data.get("status", "APPROVED"),
            raw_data={
                "po_number": po_number,
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "order_date": data.get("order_date") or datetime.now(timezone.utc).isoformat(),
                "total_amount": total_amount,
                "tax_amount": tax_amount,
                "subtotal": subtotal,
                "currency": curr,
                "payment_terms": data.get("payment_terms", "Net30"),
                "line_items": line_items
            }
        )
        self.db.add(rec)
        self.db.commit()
        return ConnectorOperationResult(success=True, record_id=po_number, action="CREATE_PURCHASE_ORDER", details=data)

    def _create_invoice(self, data: Dict[str, Any]) -> ConnectorOperationResult:
        inv_number = (data.get("invoice_number") or "").strip()
        if not inv_number:
            raise ValueError("Invoice creation requires 'invoice_number'.")

        po_number = (data.get("po_number") or "").strip()
        vendor_id = (data.get("vendor_id") or "").strip()

        curr = validate_currency(data.get("currency", "USD"))
        subtotal = float(data.get("subtotal", 0.0))
        tax_amount = float(data.get("tax_amount", 0.0))
        total_amount = float(data.get("total_amount", 0.0))

        line_items = data.get("line_items", [])
        if line_items:
            validate_line_items(line_items, expected_subtotal=subtotal)
        validate_financial_totals(subtotal, tax_amount, total_amount)

        existing = self.db.query(EnterpriseRecord).filter(EnterpriseRecord.id == inv_number).first()
        if existing:
            raise ValueError(f"Invoice '{inv_number}' already exists in ERP.")

        vendor_name = data.get("vendor_name")
        if not vendor_name and vendor_id:
            v = self.db.query(EnterpriseRecord).filter(EnterpriseRecord.id == vendor_id).first()
            vendor_name = v.name if v else "Unknown Vendor"

        rec = EnterpriseRecord(
            id=inv_number,
            system_origin=self.system_id,
            entity_type="INVOICE",
            name=vendor_name or "Vendor Invoice",
            status=data.get("status", "RECEIVED"),
            raw_data={
                "invoice_number": inv_number,
                "po_number": po_number,
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "invoice_date": data.get("invoice_date") or datetime.now(timezone.utc).isoformat(),
                "due_date": data.get("due_date"),
                "subtotal": subtotal,
                "tax_amount": tax_amount,
                "total_amount": total_amount,
                "currency": curr,
                "line_items": line_items,
                "reconciliation_status": data.get("reconciliation_status", "PENDING")
            }
        )
        self.db.add(rec)
        self.db.commit()
        return ConnectorOperationResult(success=True, record_id=inv_number, action="CREATE_INVOICE", details=data)

    def _create_goods_receipt(self, data: Dict[str, Any]) -> ConnectorOperationResult:
        gr_number = (data.get("gr_number") or "").strip()
        if not gr_number:
            raise ValueError("Goods receipt creation requires 'gr_number'.")

        po_number = (data.get("po_number") or "").strip()
        if not po_number:
            raise ValueError("Goods receipt creation requires 'po_number'.")

        received_items = data.get("received_items", [])
        if not received_items:
            raise ValueError("Goods receipt requires at least one received item.")

        existing = self.db.query(EnterpriseRecord).filter(EnterpriseRecord.id == gr_number).first()
        if existing:
            raise ValueError(f"Goods receipt '{gr_number}' already exists.")

        rec = EnterpriseRecord(
            id=gr_number,
            system_origin=self.system_id,
            entity_type="GOODS_RECEIPT",
            name=f"GR for {po_number}",
            status=data.get("status", "VERIFIED_RECEIVED"),
            raw_data={
                "gr_number": gr_number,
                "po_number": po_number,
                "vendor_id": data.get("vendor_id"),
                "received_date": data.get("received_date") or datetime.now(timezone.utc).isoformat(),
                "carrier_tracking": data.get("carrier_tracking"),
                "received_items": received_items
            }
        )
        self.db.add(rec)
        self.db.commit()
        return ConnectorOperationResult(success=True, record_id=gr_number, action="CREATE_GOODS_RECEIPT", details=data)

    def update_record(self, record_type: str, record_id: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        rec = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id,
            EnterpriseRecord.id == record_id
        ).first()
        if not rec:
            raise ValueError(f"ERP record '{record_id}' not found.")

        raw = dict(rec.raw_data or {})
        for k, v in data.items():
            if k == "status":
                rec.status = v
            elif k in ["name", "business_name", "vendor_name"]:
                rec.name = v
            raw[k] = v

        rec.raw_data = raw
        rec.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return ConnectorOperationResult(success=True, record_id=record_id, action="UPDATE_RECORD", details=data)


# =====================================================================
# 2. NETSUITE ERP ADAPTER (Alternate Enterprise Schema)
# =====================================================================

class NetSuiteERPAdapter(BaseEnterpriseConnector):
    """
    Alternate Enterprise ERP Connector conforming to Oracle NetSuite nomenclature:
    - Entities (Vendors / Suppliers)
    - Purchase Orders (Transaction Type: PurchaseOrder)
    - Vendor Bills (Transaction Type: VendorBill / Invoice)
    - Item Receipts (Transaction Type: ItemReceipt / Goods Receipt)
    """
    def __init__(self, db: Session, config: Optional[Dict[str, Any]] = None):
        cfg = config or {
            "endpoint": "https://123456.suitetalk.api.netsuite.com/services/rest/record/v1",
            "account_id": "NETSUITE_123456_PROD",
            "token_id": "ns_token_id_9921"
        }
        super().__init__(
            connector_id="NETSUITE_ERP",
            connector_type=ConnectorType.ERP,
            config=cfg
        )
        self.db = db
        self.system_id = "NETSUITE_ERP"
        self.is_connected = True

    def connect(self) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        self.is_connected = False

    def test_connection(self) -> ConnectorHealth:
        start_time = datetime.now(timezone.utc)
        count = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id
        ).count()
        latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000.0
        return ConnectorHealth(
            connector_id=self.connector_id,
            connector_type=self.connector_type,
            status=ConnectorStatus.CONNECTED if self.is_connected else ConnectorStatus.DISCONNECTED,
            latency_ms=round(latency, 2),
            last_checked_at=datetime.now(timezone.utc).isoformat(),
            message=f"NetSuite ERP SuiteTalk live. {count} records discoverable."
        )

    def discover_schema(self, record_type: str = "entity") -> List[Dict[str, Any]]:
        norm = record_type.lower()
        if norm in ["entity", "vendor", "supplier"]:
            return [
                {"field_name": "entity_id", "data_type": "string", "is_primary_key": True, "nullable": False},
                {"field_name": "company_name", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "remit_address", "data_type": "string", "is_primary_key": False, "nullable": True},
                {"field_name": "vat_registration_no", "data_type": "string", "is_primary_key": False, "nullable": True},
                {"field_name": "currency_code", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "terms", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "entity_status", "data_type": "string", "is_primary_key": False, "nullable": False}
            ]
        elif norm in ["purchaseorder", "po", "tran"]:
            return [
                {"field_name": "tran_id", "data_type": "string", "is_primary_key": True, "nullable": False},
                {"field_name": "entity_ref", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "tran_date", "data_type": "datetime", "is_primary_key": False, "nullable": False},
                {"field_name": "foreign_total", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "tax_total", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "currency_code", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "items", "data_type": "array[object]", "is_primary_key": False, "nullable": False}
            ]
        elif norm in ["vendorbill", "bill", "invoice"]:
            return [
                {"field_name": "bill_number", "data_type": "string", "is_primary_key": True, "nullable": False},
                {"field_name": "po_ref", "data_type": "string", "is_primary_key": False, "nullable": True},
                {"field_name": "entity_ref", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "bill_date", "data_type": "datetime", "is_primary_key": False, "nullable": False},
                {"field_name": "net_amount", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "tax_amount", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "gross_amount", "data_type": "float", "is_primary_key": False, "nullable": False},
                {"field_name": "bill_items", "data_type": "array[object]", "is_primary_key": False, "nullable": False}
            ]
        else:
            return [
                {"field_name": "receipt_doc_no", "data_type": "string", "is_primary_key": True, "nullable": False},
                {"field_name": "po_ref", "data_type": "string", "is_primary_key": False, "nullable": False},
                {"field_name": "date_received", "data_type": "datetime", "is_primary_key": False, "nullable": False},
                {"field_name": "items_received", "data_type": "array[object]", "is_primary_key": False, "nullable": False}
            ]

    def read_records(self, query: ConnectorQuery) -> ConnectorPage:
        rec_type = query.record_type.lower()
        if rec_type in ["vendor", "entity", "vendors"]:
            target_entity = "VENDOR"
        elif rec_type in ["purchase_order", "po", "purchaseorder"]:
            target_entity = "PURCHASE_ORDER"
        elif rec_type in ["invoice", "vendorbill", "bill"]:
            target_entity = "INVOICE"
        else:
            target_entity = "GOODS_RECEIPT"

        q = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id,
            EnterpriseRecord.entity_type == target_entity
        )

        filters = query.filters or {}
        search = filters.get("search")
        if search:
            q = q.filter(
                or_(
                    EnterpriseRecord.name.ilike(f"%{search}%"),
                    EnterpriseRecord.id.ilike(f"%{search}%")
                )
            )

        if query.incremental_since:
            try:
                watermark_dt = datetime.fromisoformat(query.incremental_since.replace("Z", "+00:00"))
                q = q.filter(EnterpriseRecord.updated_at >= watermark_dt)
            except Exception:
                pass

        offset = int(query.cursor) if query.cursor and query.cursor.isdigit() else 0
        total_count = q.count()
        records_raw = q.order_by(EnterpriseRecord.created_at.desc()).offset(offset).limit(query.limit).all()

        formatted = []
        for r in records_raw:
            raw = r.raw_data or {}
            if target_entity == "VENDOR":
                formatted.append({
                    "entity_id": r.id,
                    "company_name": r.name,
                    "remit_address": r.address,
                    "vat_registration_no": r.tax_identifier,
                    "currency_code": raw.get("currency_code", "USD"),
                    "terms": raw.get("terms", "Net 30"),
                    "entity_status": r.status
                })
            elif target_entity == "PURCHASE_ORDER":
                formatted.append({
                    "tran_id": r.id,
                    "entity_ref": raw.get("entity_ref") or raw.get("entity_id") or "UNKNOWN_VENDOR",
                    "vendor_title": r.name,
                    "tran_date": raw.get("tran_date") or (r.created_at.isoformat() if r.created_at else None),
                    "foreign_total": raw.get("foreign_total") or raw.get("total_amount", 0.0),
                    "tax_total": raw.get("tax_total", 0.0),
                    "currency_code": raw.get("currency_code") or raw.get("currency_iso", "USD"),
                    "status": r.status,
                    "items": raw.get("items") or raw.get("line_items", [])
                })
            elif target_entity == "INVOICE":
                formatted.append({
                    "bill_number": r.id,
                    "po_ref": raw.get("po_ref") or raw.get("po_number"),
                    "entity_ref": raw.get("entity_ref") or raw.get("entity_id") or "UNKNOWN_VENDOR",
                    "vendor_title": r.name,
                    "bill_date": raw.get("bill_date") or raw.get("invoice_date") or (r.created_at.isoformat() if r.created_at else None),
                    "net_amount": raw.get("net_amount") or raw.get("subtotal", 0.0),
                    "tax_amount": raw.get("tax_amount", 0.0),
                    "gross_amount": raw.get("gross_amount") or raw.get("total_amount", 0.0),
                    "currency_code": raw.get("currency_code") or raw.get("currency_iso", "USD"),
                    "status": r.status,
                    "bill_items": raw.get("bill_items") or raw.get("line_items", [])
                })
            elif target_entity == "GOODS_RECEIPT":
                formatted.append({
                    "receipt_doc_no": r.id,
                    "po_ref": raw.get("po_ref"),
                    "date_received": raw.get("date_received") or (r.created_at.isoformat() if r.created_at else None),
                    "doc_status": r.status,
                    "items_received": raw.get("items_received", [])
                })

        next_cursor = str(offset + len(formatted)) if (offset + len(formatted)) < total_count else None
        return ConnectorPage(
            records=formatted,
            count=len(formatted),
            has_more=next_cursor is not None,
            next_cursor=next_cursor,
            total_count=total_count
        )

    def get_record_by_id(self, record_type: str, record_id: str) -> Optional[Dict[str, Any]]:
        page = self.read_records(ConnectorQuery(record_type=record_type, filters={"search": record_id}, limit=10))
        for r in page.records:
            cur_id = r.get("entity_id") or r.get("tran_id") or r.get("bill_number") or r.get("receipt_doc_no")
            if cur_id == record_id:
                return r
        return None

    def create_record(self, record_type: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        norm = record_type.lower()
        if norm in ["vendor", "entity"]:
            entity_id = data.get("entity_id") or f"NS-VND-{self.db.query(EnterpriseRecord).count() + 1}"
            company_name = data.get("company_name", "").strip()
            if not company_name:
                raise ValueError("NetSuite vendor requires 'company_name'.")

            rec = EnterpriseRecord(
                id=entity_id,
                system_origin=self.system_id,
                entity_type="VENDOR",
                name=company_name,
                address=data.get("remit_address", ""),
                tax_identifier=data.get("vat_registration_no"),
                status=data.get("entity_status", "ACTIVE"),
                raw_data={
                    "currency_code": validate_currency(data.get("currency_code", "USD")),
                    "terms": data.get("terms", "Net 30")
                }
            )
            self.db.add(rec)
            self.db.commit()
            return ConnectorOperationResult(success=True, record_id=entity_id, action="CREATE_NETSUITE_ENTITY", details=data)

        elif norm in ["purchaseorder", "po"]:
            tran_id = data.get("tran_id") or f"NS-PO-{self.db.query(EnterpriseRecord).count() + 1}"
            curr = validate_currency(data.get("currency_code", "USD"))
            total = float(data.get("foreign_total", 0.0))
            tax = float(data.get("tax_total", 0.0))
            validate_financial_totals(total - tax, tax, total)

            rec = EnterpriseRecord(
                id=tran_id,
                system_origin=self.system_id,
                entity_type="PURCHASE_ORDER",
                name=data.get("vendor_title", "NetSuite PO"),
                status="APPROVED",
                raw_data={
                    "tran_id": tran_id,
                    "entity_ref": data.get("entity_ref"),
                    "tran_date": data.get("tran_date") or datetime.now(timezone.utc).isoformat(),
                    "foreign_total": total,
                    "tax_total": tax,
                    "currency_code": curr,
                    "items": data.get("items", [])
                }
            )
            self.db.add(rec)
            self.db.commit()
            return ConnectorOperationResult(success=True, record_id=tran_id, action="CREATE_NETSUITE_PO", details=data)

        elif norm in ["vendorbill", "bill", "invoice"]:
            bill_num = data.get("bill_number") or f"NS-BILL-{self.db.query(EnterpriseRecord).count() + 1}"
            curr = validate_currency(data.get("currency_code", "USD"))
            gross = float(data.get("gross_amount", 0.0))
            tax = float(data.get("tax_amount", 0.0))
            net = float(data.get("net_amount", gross - tax))
            validate_financial_totals(net, tax, gross)

            rec = EnterpriseRecord(
                id=bill_num,
                system_origin=self.system_id,
                entity_type="INVOICE",
                name=data.get("vendor_title", "Vendor Bill"),
                status=data.get("status", "OPEN"),
                raw_data={
                    "bill_number": bill_num,
                    "po_ref": data.get("po_ref"),
                    "entity_ref": data.get("entity_ref"),
                    "bill_date": data.get("bill_date") or datetime.now(timezone.utc).isoformat(),
                    "net_amount": net,
                    "tax_amount": tax,
                    "gross_amount": gross,
                    "currency_code": curr,
                    "bill_items": data.get("bill_items", [])
                }
            )
            self.db.add(rec)
            self.db.commit()
            return ConnectorOperationResult(success=True, record_id=bill_num, action="CREATE_NETSUITE_BILL", details=data)

        else:
            receipt_id = data.get("receipt_doc_no") or f"NS-GR-{self.db.query(EnterpriseRecord).count() + 1}"
            rec = EnterpriseRecord(
                id=receipt_id,
                system_origin=self.system_id,
                entity_type="GOODS_RECEIPT",
                name=f"Item Receipt {receipt_id}",
                status="RECEIVED",
                raw_data={
                    "receipt_doc_no": receipt_id,
                    "po_ref": data.get("po_ref"),
                    "date_received": data.get("date_received") or datetime.now(timezone.utc).isoformat(),
                    "items_received": data.get("items_received", [])
                }
            )
            self.db.add(rec)
            self.db.commit()
            return ConnectorOperationResult(success=True, record_id=receipt_id, action="CREATE_NETSUITE_ITEM_RECEIPT", details=data)

    def update_record(self, record_type: str, record_id: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        rec = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id,
            EnterpriseRecord.id == record_id
        ).first()
        if not rec:
            raise ValueError(f"NetSuite record '{record_id}' not found.")

        raw = dict(rec.raw_data or {})
        for k, v in data.items():
            if k == "status":
                rec.status = v
            raw[k] = v

        rec.raw_data = raw
        rec.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return ConnectorOperationResult(success=True, record_id=record_id, action="UPDATE_RECORD", details=data)


# =====================================================================
# 3. CANONICAL ENTERPRISE ERP MAPPINGS
# =====================================================================

def erp_record_to_canonical_vendor(record: Dict[str, Any], adapter_type: str = "SAP_ERP") -> CanonicalVendor:
    norm = adapter_type.upper()
    if "NETSUITE" in norm:
        return CanonicalVendor(
            vendor_id=record.get("entity_id", ""),
            vendor_name=record.get("company_name", ""),
            legal_name=record.get("company_name"),
            tax_identifier=record.get("vat_registration_no"),
            currency=record.get("currency_code", "USD"),
            payment_terms=record.get("terms", "NET_30"),
            status=record.get("entity_status", "ACTIVE"),
            source_system="NETSUITE_ERP"
        )
    return CanonicalVendor(
        vendor_id=record.get("vendor_id", ""),
        vendor_name=record.get("business_name", ""),
        legal_name=record.get("business_name"),
        tax_identifier=record.get("tax_number"),
        country=record.get("country", "US"),
        currency=record.get("currency", "USD"),
        payment_terms=record.get("payment_terms", "NET_30"),
        status=record.get("status", "ACTIVE"),
        canonical_id=record.get("canonical_id"),
        source_system="COMPANY_B_ERP"
    )


def erp_record_to_canonical_po(record: Dict[str, Any], adapter_type: str = "SAP_ERP") -> CanonicalPurchaseOrder:
    norm = adapter_type.upper()
    if "NETSUITE" in norm:
        line_items = []
        for idx, item in enumerate(record.get("items", [])):
            qty = float(item.get("qty", 1.0))
            rate = float(item.get("rate", 0.0))
            line_items.append(CanonicalLineItem(
                line_number=idx + 1,
                sku_or_code=item.get("item_ref", f"ITEM-{idx+1}"),
                description=item.get("memo", ""),
                quantity=qty,
                unit_price=rate,
                total_price=item.get("amount", qty * rate)
            ))
        dt_str = record.get("tran_date") or datetime.now(timezone.utc).isoformat()
        try:
            order_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            order_dt = datetime.now(timezone.utc)

        vendor_id = record.get("entity_ref") or record.get("entity_id") or record.get("vendor_id") or "UNKNOWN_VENDOR"
        return CanonicalPurchaseOrder(
            po_number=record.get("tran_id") or record.get("po_number", ""),
            vendor_id=vendor_id,
            vendor_name=record.get("vendor_title") or record.get("vendor_name", "Vendor"),
            order_date=order_dt,
            total_amount=float(record.get("foreign_total") or record.get("total_amount", 0.0)),
            currency=record.get("currency_code") or record.get("currency_iso", "USD"),
            status=record.get("status", "APPROVED"),
            line_items=line_items,
            source_system="NETSUITE_ERP"
        )

    line_items = []
    for idx, item in enumerate(record.get("line_items", [])):
        qty = float(item.get("quantity", item.get("qty", 1.0)))
        price = float(item.get("unit_price", 0.0))
        line_items.append(CanonicalLineItem(
            line_number=item.get("line_number", idx + 1),
            sku_or_code=item.get("sku", item.get("item_code", f"SKU-{idx+1}")),
            description=item.get("description", ""),
            quantity=qty,
            unit_price=price,
            total_price=float(item.get("total", qty * price))
        ))

    dt_str = record.get("order_date") or datetime.now(timezone.utc).isoformat()
    try:
        order_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        order_dt = datetime.now(timezone.utc)

    return CanonicalPurchaseOrder(
        po_number=record.get("po_number", ""),
        vendor_id=record.get("vendor_id", ""),
        vendor_name=record.get("vendor_name", "Vendor"),
        order_date=order_dt,
        total_amount=float(record.get("total_amount", 0.0)),
        currency=record.get("currency", "USD"),
        status=record.get("status", "APPROVED"),
        line_items=line_items,
        source_system="COMPANY_B_ERP"
    )


def erp_record_to_canonical_invoice(record: Dict[str, Any], adapter_type: str = "SAP_ERP") -> CanonicalInvoice:
    norm = adapter_type.upper()
    if "NETSUITE" in norm:
        line_items = []
        for idx, item in enumerate(record.get("bill_items", [])):
            qty = float(item.get("qty", 1.0))
            rate = float(item.get("rate", 0.0))
            line_items.append(CanonicalLineItem(
                line_number=idx + 1,
                sku_or_code=item.get("item_ref", f"ITEM-{idx+1}"),
                description=item.get("memo", ""),
                quantity=qty,
                unit_price=rate,
                total_price=float(item.get("amount", qty * rate))
            ))
        dt_str = record.get("bill_date") or datetime.now(timezone.utc).isoformat()
        try:
            inv_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            inv_dt = datetime.now(timezone.utc)

        vendor_id = record.get("entity_ref") or record.get("entity_id") or record.get("vendor_id") or "UNKNOWN_VENDOR"
        return CanonicalInvoice(
            invoice_number=record.get("bill_number") or record.get("invoice_number", ""),
            vendor_id=vendor_id,
            po_number=record.get("po_ref") or record.get("po_number"),
            invoice_date=inv_dt,
            subtotal=float(record.get("net_amount") or record.get("subtotal", 0.0)),
            tax_amount=float(record.get("tax_amount", 0.0)),
            total_amount=float(record.get("gross_amount") or record.get("total_amount", 0.0)),
            currency=record.get("currency_code") or record.get("currency_iso", "USD"),
            line_items=line_items,
            source_system="NETSUITE_ERP"
        )

    line_items = []
    for idx, item in enumerate(record.get("line_items", [])):
        qty = float(item.get("quantity", item.get("qty", 1.0)))
        price = float(item.get("unit_price", 0.0))
        line_items.append(CanonicalLineItem(
            line_number=item.get("line_number", idx + 1),
            sku_or_code=item.get("sku", item.get("item_code", f"SKU-{idx+1}")),
            description=item.get("description", ""),
            quantity=qty,
            unit_price=price,
            total_price=float(item.get("total", qty * price))
        ))
    dt_str = record.get("invoice_date") or datetime.now(timezone.utc).isoformat()
    try:
        inv_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        inv_dt = datetime.now(timezone.utc)

    return CanonicalInvoice(
        invoice_number=record.get("invoice_number", ""),
        vendor_id=record.get("vendor_id", ""),
        po_number=record.get("po_number"),
        invoice_date=inv_dt,
        subtotal=float(record.get("subtotal", 0.0)),
        tax_amount=float(record.get("tax_amount", 0.0)),
        total_amount=float(record.get("total_amount", 0.0)),
        currency=record.get("currency", "USD"),
        line_items=line_items,
        source_system="COMPANY_B_ERP"
    )


def erp_record_to_canonical_gr(record: Dict[str, Any], adapter_type: str = "SAP_ERP") -> CanonicalGoodsReceipt:
    norm = adapter_type.upper()
    if "NETSUITE" in norm:
        dt_str = record.get("date_received") or datetime.now(timezone.utc).isoformat()
        try:
            rcv_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            rcv_dt = datetime.now(timezone.utc)
        return CanonicalGoodsReceipt(
            gr_number=record.get("receipt_doc_no", ""),
            po_number=record.get("po_ref", ""),
            received_date=rcv_dt,
            received_items=record.get("items_received", []),
            receipt_status=record.get("doc_status", "VERIFIED_RECEIVED"),
            source_system="NETSUITE_ERP"
        )

    dt_str = record.get("received_date") or datetime.now(timezone.utc).isoformat()
    try:
        rcv_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        rcv_dt = datetime.now(timezone.utc)
    return CanonicalGoodsReceipt(
        gr_number=record.get("gr_number", ""),
        po_number=record.get("po_number", ""),
        received_date=rcv_dt,
        received_items=record.get("received_items", []),
        receipt_status=record.get("status", "VERIFIED_RECEIVED"),
        source_system="COMPANY_B_ERP"
    )
