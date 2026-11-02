from typing import Dict, Any, List
from ml.models.invoice_reconciliation.preprocessing import ReconciliationInput


def calculate_variances(rec_in: ReconciliationInput, price_tolerance_pct: float = 2.0) -> Dict[str, Any]:
    inv = rec_in.invoice
    po = rec_in.purchase_order
    gr = rec_in.goods_receipt

    line_results = []
    total_price_variance = 0.0
    total_qty_variance = 0.0
    flags = []

    # Check duplicate invoice
    if inv.invoice_number in rec_in.existing_invoice_numbers:
        flags.append("DUPLICATE_INVOICE_NUMBER_DETECTED")

    # Check vendor match
    if po and po.vendor_id != inv.vendor_id:
        flags.append(f"VENDOR_MISMATCH: Invoice vendor ({inv.vendor_id}) != PO vendor ({po.vendor_id})")

    # Check math: sum(line.total) + tax ~ total_amount
    computed_subtotal = sum(l.total for l in inv.line_items)
    computed_total = computed_subtotal + inv.tax_amount
    if abs(computed_total - inv.total_amount) > 0.05:
        flags.append(f"MATH_DISCREPANCY: Stated total {inv.total_amount} != computed {round(computed_total, 2)}")

    if po:
        po_items_by_sku = {l.sku: l for l in po.line_items}
        gr_items = gr.received_items if gr else {}

        for l in inv.line_items:
            po_item = po_items_by_sku.get(l.sku)
            if not po_item:
                flags.append(f"UNKNOWN_ITEM_SKU: {l.sku} not present on PO {po.po_number}")
                continue

            # Price check
            unit_price_diff = l.unit_price - po_item.unit_price
            price_pct_diff = (unit_price_diff / max(0.01, po_item.unit_price)) * 100.0
            
            # Qty check
            received_qty = gr_items.get(l.sku, po_item.quantity)
            qty_diff = l.quantity - received_qty

            line_status = "MATCH"
            if abs(price_pct_diff) > price_tolerance_pct:
                line_status = "PRICE_VARIANCE"
                flags.append(f"PRICE_VARIANCE on {l.sku}: Stated ${l.unit_price} vs PO ${po_item.unit_price} ({price_pct_diff:+.1f}%)")
            
            if qty_diff > 0:
                line_status = "QUANTITY_OVERBILL"
                flags.append(f"OVERBILL on {l.sku}: Billed {l.quantity} vs Received {received_qty}")

            total_price_variance += abs(unit_price_diff * l.quantity)
            total_qty_variance += max(0.0, qty_diff)

            line_results.append({
                "sku": l.sku,
                "description": l.description or po_item.description,
                "billed_qty": l.quantity,
                "received_qty": received_qty,
                "billed_price": l.unit_price,
                "po_price": po_item.unit_price,
                "variance_amount": round(unit_price_diff * l.quantity, 2),
                "status": line_status
            })

    return {
        "flags": flags,
        "line_item_details": line_results,
        "total_price_variance": round(total_price_variance, 2),
        "total_qty_variance": round(total_qty_variance, 2),
        "has_exceptions": len(flags) > 0
    }

