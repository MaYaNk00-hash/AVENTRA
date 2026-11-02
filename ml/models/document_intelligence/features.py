import re
from typing import Dict, Any, List, Optional

INV_RE = re.compile(r'(?:invoice\s*(?:#|no\.?|num(?:ber)?)|inv#?)\s*[:\-]?\s*([A-Za-z0-9\-_]+)', re.IGNORECASE)
PO_RE = re.compile(r'(?:purchase\s*order|po\s*(?:#|no\.?|num(?:ber)?)|p\.o\.)\s*[:\-]?\s*([A-Za-z0-9\-_]+)', re.IGNORECASE)
DATE_RE = re.compile(r'(?:date|dated|invoice\s*date)\s*[:\-]?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}|[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})', re.IGNORECASE)
SUBTOTAL_RE = re.compile(r'\bsubtotal\s*[:\-]?\s*\$?\s*([0-9,]+\.[0-9]{2})', re.IGNORECASE)
TOTAL_RE = re.compile(r'(?<!sub)\btotal(?:\s*(?:amount|due|balance|pay(?:able)?))?\s*[:\-]?\s*\$?\s*([0-9,]+\.[0-9]{2})', re.IGNORECASE)
TAX_RE = re.compile(r'\b(?:tax|vat|gst|sales\s*tax)\s*[:\-]?\s*\$?\s*([0-9,]+\.[0-9]{2})', re.IGNORECASE)
LINE_ITEM_RE = re.compile(r'^\s*([A-Za-z0-9\-_]+)\s+(.+?)\s+([0-9]+(?:\.[0-9]+)?)\s+\$?([0-9,]+\.[0-9]{2})\s+\$?([0-9,]+\.[0-9]{2})\s*$', re.MULTILINE)


def parse_document_fields(text: str) -> Dict[str, Any]:
    extracted = {}
    confidences = {}

    # Invoice Number
    inv_m = INV_RE.search(text)
    if inv_m:
        extracted["invoice_number"] = inv_m.group(1).strip()
        confidences["invoice_number"] = 0.98
    else:
        extracted["invoice_number"] = None
        confidences["invoice_number"] = 0.0

    # PO Number
    po_m = PO_RE.search(text)
    if po_m:
        extracted["po_number"] = po_m.group(1).strip()
        confidences["po_number"] = 0.95
    else:
        extracted["po_number"] = None
        confidences["po_number"] = 0.0

    # Date
    date_m = DATE_RE.search(text)
    if date_m:
        extracted["invoice_date"] = date_m.group(1).strip()
        confidences["invoice_date"] = 0.92
    else:
        extracted["invoice_date"] = None
        confidences["invoice_date"] = 0.0

    # Subtotal
    subtotal_m = SUBTOTAL_RE.search(text)
    if subtotal_m:
        extracted["subtotal"] = float(subtotal_m.group(1).replace(",", ""))
        confidences["subtotal"] = 0.95
    else:
        extracted["subtotal"] = 0.0
        confidences["subtotal"] = 0.50

    # Total Amount
    total_m = TOTAL_RE.search(text)
    if total_m:
        raw_val = total_m.group(1).replace(",", "")
        extracted["total_amount"] = float(raw_val)
        confidences["total_amount"] = 0.96
    else:
        extracted["total_amount"] = None
        confidences["total_amount"] = 0.0

    # Tax Amount
    tax_m = TAX_RE.search(text)
    if tax_m:
        raw_tax = tax_m.group(1).replace(",", "")
        extracted["tax_amount"] = float(raw_tax)
        confidences["tax_amount"] = 0.90
    else:
        extracted["tax_amount"] = 0.0
        confidences["tax_amount"] = 0.50

    # Line items
    line_items = []
    for m in LINE_ITEM_RE.finditer(text):
        sku = m.group(1).strip()
        desc = m.group(2).strip()
        qty = float(m.group(3))
        unit_p = float(m.group(4).replace(",", ""))
        tot = float(m.group(5).replace(",", ""))
        line_items.append({
            "sku": sku,
            "description": desc,
            "quantity": qty,
            "unit_price": unit_p,
            "total": tot
        })

    extracted["line_items"] = line_items
    confidences["line_items"] = 0.90 if line_items else 0.40

    if not extracted["subtotal"] and line_items:
        extracted["subtotal"] = round(sum(l["total"] for l in line_items), 2)

    return {
        "extracted_fields": extracted,
        "confidences": confidences
    }
