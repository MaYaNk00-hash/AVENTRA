# Model M5: Invoice Verification & 3-Way Reconciliation

## Overview
Deterministic 3-way matching engine comparing Vendor Invoices against ERP Purchase Orders and Warehouse Goods Receipts.

## Rule Matrix
1. **PO & Vendor Validation**: Validates cross-system identifiers.
2. **Duplicate Detection**: Flags reused invoice reference codes.
3. **Price Variance**: Tolerates up to configured percentage variance (default 2%), flagging higher discrepancies.
4. **Quantity Reconciliation**: Verifies billed quantities against physically received warehouse logs.
5. **Math Check**: Audits line item additions against subtotal and tax amounts.

## Tests
```bash
pytest ml/models/invoice_reconciliation/tests/test_invoice_reconciliation.py
```

