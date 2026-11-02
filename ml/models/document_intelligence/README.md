# Model M7: Document Intelligence & Extraction

## Overview
Parses unstructured business documents (scanned receipts, PDF invoices, billing records) into standardized structured schema objects matching ERP entity definitions.

## Key Extractions
- Invoice Reference Number
- Purchase Order Number
- Transaction & Issue Dates
- Line items with SKU, Description, Quantity, Unit Price, and Item Subtotals
- Tax and Final Payable Amounts

## Verification
```bash
pytest ml/models/document_intelligence/tests/test_document_intelligence.py
```

