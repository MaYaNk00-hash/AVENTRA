import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))
from ml.models.document_intelligence.inference import DocumentIntelligenceModel
from ml.shared.schemas.base import ModelExecutionStatus


def test_document_extraction():
    model = DocumentIntelligenceModel()
    model.load()

    raw_invoice_text = """
    GLOBAL INDUSTRIAL SUPPLIERS INC.
    100 Industrial Parkway, Chicago, IL

    INVOICE # INV-2026-9041
    PURCHASE ORDER: PO-7712
    DATE: 2026-10-20

    Line Items:
    SKU-100 Heavy Duty Bearings 50 $20.00 $1000.00
    SKU-200 Stainless Steel Bolts 100 $2.50 $250.00

    Subtotal: $1250.00
    Tax: $100.00
    Total Amount: $1350.00
    """

    out = model.predict({"document_text": raw_invoice_text, "filename": "sample_invoice.txt"})
    assert out.execution_status == ModelExecutionStatus.SUCCESS
    pred = out.prediction
    fields = pred["extracted_fields"]
    assert fields["invoice_number"] == "INV-2026-9041"
    assert fields["po_number"] == "PO-7712"
    assert fields["total_amount"] == 1350.00
    assert fields["tax_amount"] == 100.00
    assert len(fields["line_items"]) == 2

