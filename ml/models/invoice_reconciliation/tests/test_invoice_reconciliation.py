import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))
from ml.models.invoice_reconciliation.inference import InvoiceReconciliationModel
from ml.shared.schemas.base import ModelExecutionStatus


def test_invoice_reconciliation_exact():
    model = InvoiceReconciliationModel()
    model.load()

    data = {
        "invoice": {
            "invoice_number": "INV-2026-001",
            "po_number": "PO-8819",
            "vendor_id": "VEND-ACME",
            "invoice_date": "2026-10-25",
            "subtotal": 1000.0,
            "tax_amount": 80.0,
            "total_amount": 1080.0,
            "line_items": [
                {"sku": "SKU-A", "description": "Steel Rods", "quantity": 10, "unit_price": 100.0, "total": 1000.0}
            ]
        },
        "purchase_order": {
            "po_number": "PO-8819",
            "vendor_id": "VEND-ACME",
            "total_amount": 1080.0,
            "line_items": [
                {"sku": "SKU-A", "description": "Steel Rods", "quantity": 10, "unit_price": 100.0, "total": 1000.0}
            ]
        },
        "goods_receipt": {
            "receipt_id": "GR-552",
            "po_number": "PO-8819",
            "received_items": {"SKU-A": 10.0}
        }
    }

    out = model.predict(data)
    assert out.execution_status == ModelExecutionStatus.SUCCESS
    assert out.prediction["reconciliation_status"] == "RECONCILED_EXACT"
    assert out.prediction["requires_human_approval"] is False


def test_invoice_reconciliation_overbill_discrepancy():
    model = InvoiceReconciliationModel()
    model.load()

    data = {
        "invoice": {
            "invoice_number": "INV-2026-002",
            "po_number": "PO-8819",
            "vendor_id": "VEND-ACME",
            "invoice_date": "2026-10-25",
            "subtotal": 1500.0,
            "tax_amount": 120.0,
            "total_amount": 1620.0,
            "line_items": [
                {"sku": "SKU-A", "description": "Steel Rods", "quantity": 10, "unit_price": 150.0, "total": 1500.0}
            ]
        },
        "purchase_order": {
            "po_number": "PO-8819",
            "vendor_id": "VEND-ACME",
            "total_amount": 1080.0,
            "line_items": [
                {"sku": "SKU-A", "description": "Steel Rods", "quantity": 10, "unit_price": 100.0, "total": 1000.0}
            ]
        }
    }

    out = model.predict(data)
    assert out.prediction["reconciliation_status"] == "DISCREPANCY_APPROVAL_REQUIRED"
    assert out.prediction["requires_human_approval"] is True
    assert out.prediction["total_variance_currency"] == 500.0

