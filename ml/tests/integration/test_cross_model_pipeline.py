import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.orchestration.pipeline_executor import PipelineExecutor


def test_cross_model_onboarding_pipeline():
    executor = PipelineExecutor()

    new_customer = {
        "entity_id": "NEW-CUST-881",
        "business_name": "Apex Global Logistics LLC",
        "business_address": "742 Evergreen Terrace Springfield IL",
        "country": "US",
        "source_system": "COMPANY_A_CRM"
    }

    candidates = [
        {
            "entity_id": "ERP-VEND-104",
            "business_name": "Apex Global Logistics Inc",
            "business_address": "742 Evergreen Terr Springfield IL",
            "country": "US",
            "source_system": "COMPANY_B_ERP"
        },
        {
            "entity_id": "ERP-VEND-992",
            "business_name": "Pinnacle Dynamics Corp",
            "business_address": "100 Market St San Francisco CA",
            "country": "US",
            "source_system": "COMPANY_B_ERP"
        }
    ]

    ctx = executor.execute_customer_onboarding_pipeline(new_customer, candidates)
    assert ctx.current_state == "AWAITING_APPROVAL"
    assert ctx.approval_required is True
    assert "entity_resolution" in ctx.model_outputs
    assert "workflow_planner" in ctx.model_outputs
    assert "intent_parser" in ctx.model_outputs
    assert len(ctx.execution_history) >= 4


def test_cross_model_invoice_reconciliation_pipeline():
    executor = PipelineExecutor()

    invoice_raw = """
    SUPREME INDUSTRIAL SUPPLY CO.
    INVOICE #: INV-7729
    PURCHASE ORDER: PO-4401
    DATE: 2026-10-25

    SKU-500 Carbon Steel Valves 10 $100.00 $1000.00

    Subtotal: $1000.00
    Tax: $80.00
    Total Amount: $1080.00
    """

    po_data = {
        "po_number": "PO-4401",
        "vendor_id": "VEND-SUPREME",
        "total_amount": 1080.0,
        "line_items": [
            {"sku": "SKU-500", "description": "Carbon Steel Valves", "quantity": 10, "unit_price": 100.0, "total": 1000.0}
        ]
    }

    goods_receipt = {
        "receipt_id": "GR-909",
        "po_number": "PO-4401",
        "received_items": {"SKU-500": 10.0}
    }

    ctx = executor.execute_invoice_reconciliation_pipeline(invoice_raw, po_data, goods_receipt)
    assert ctx.current_state == "READY_TO_COMMIT"
    assert ctx.approval_required is False
    assert "document_intelligence" in ctx.model_outputs
    assert "invoice_reconciliation" in ctx.model_outputs
    assert "anomaly_detection" in ctx.model_outputs

