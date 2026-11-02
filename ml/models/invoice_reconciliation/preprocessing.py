from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    sku: str
    description: str = ""
    quantity: float
    unit_price: float
    total: float


class PurchaseOrder(BaseModel):
    po_number: str
    vendor_id: str
    total_amount: float
    line_items: List[LineItem] = Field(default_factory=list)


class GoodsReceipt(BaseModel):
    receipt_id: str
    po_number: str
    received_items: Dict[str, float] = Field(default_factory=dict)  # sku -> received_qty


class Invoice(BaseModel):
    invoice_number: str
    po_number: str
    vendor_id: str
    invoice_date: str
    subtotal: float
    tax_amount: float = 0.0
    total_amount: float
    line_items: List[LineItem] = Field(default_factory=list)


class ReconciliationInput(BaseModel):
    invoice: Invoice
    purchase_order: Optional[PurchaseOrder] = None
    goods_receipt: Optional[GoodsReceipt] = None
    existing_invoice_numbers: List[str] = Field(default_factory=list)

