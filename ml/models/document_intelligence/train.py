"""
Training pipeline for AVENTRA Document Intelligence model.
Generates an open-source invoice text benchmark dataset of at most 6,000 document representations,
calibrates field token extractions and confidence scorers, and saves the artifact.
"""

import os
import sys
import pickle
import random
import json
import numpy as np
import polars as pl
from sklearn.linear_model import Ridge

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.document_intelligence.preprocessing import preprocess_document
from ml.models.document_intelligence.features import parse_document_fields

VENDORS = [
    "GLOBAL INDUSTRIAL SUPPLIERS INC.\n100 Industrial Parkway, Chicago, IL",
    "APEX TECHNOLOGY SOLUTIONS LLC\n500 Silicon Way, San Jose, CA",
    "PRECISION PARTS MANUFACTURING\n12 Foundry Road, Cleveland, OH",
    "METRO LOGISTICS & FREIGHT SERVICES\n88 Harbor Blvd, Newark, NJ",
    "VORTEX ENTERPRISE SYSTEMS\n770 Tech Center Drive, Austin, TX"
]

SKUS = [
    ("SKU-100", "Heavy Duty Bearings"),
    ("SKU-200", "Stainless Steel Bolts"),
    ("SKU-300", "Hydraulic Seals"),
    ("SKU-400", "Pneumatic Valves"),
    ("SKU-500", "Aluminum Flanges")
]


def generate_document_dataset(output_parquet: str = "ml/models/document_intelligence/data/documents_6k.parquet",
                              output_json: str = "ml/models/document_intelligence/data/documents_6k.json",
                              max_samples: int = 6000) -> pl.DataFrame:
    random.seed(42)
    np.random.seed(42)
    records = []

    for i in range(max_samples):
        vendor_hdr = random.choice(VENDORS)
        inv_num = f"INV-2026-{1000 + (i % 9000)}"
        po_num = f"PO-{7000 + (i % 3000)}"
        date_str = f"2026-10-{(i % 28) + 1:02d}"

        # Generate 1 to 3 line items
        num_items = random.randint(1, 3)
        items = []
        subtotal = 0.0
        line_item_str = ""

        for j in range(num_items):
            sku, desc = SKUS[(i + j) % len(SKUS)]
            qty = random.randint(5, 50)
            price = round(float(random.uniform(5.0, 100.0)), 2)
            tot = round(qty * price, 2)
            subtotal += tot
            line_item_str += f"    {sku} {desc} {qty} ${price:.2f} ${tot:.2f}\n"

        subtotal = round(subtotal, 2)
        tax = round(subtotal * 0.08, 2)
        total = round(subtotal + tax, 2)

        doc_text = f"""
{vendor_hdr}

INVOICE # {inv_num}
PURCHASE ORDER: {po_num}
DATE: {date_str}

Line Items:
{line_item_str}
Subtotal: ${subtotal:.2f}
Tax: ${tax:.2f}
Total Amount: ${total:.2f}
"""

        parsed = parse_document_fields(doc_text)
        confidences = parsed["confidences"]
        avg_conf = float(np.mean(list(confidences.values()))) if confidences else 0.0

        records.append({
            "doc_id": f"DOC-{i:05d}",
            "filename": f"invoice_{i:05d}.txt",
            "invoice_number": inv_num,
            "po_number": po_num,
            "total_amount": total,
            "tax_amount": tax,
            "subtotal": subtotal,
            "extracted_fields_count": len(parsed["extracted_fields"]),
            "average_confidence": round(avg_conf, 4),
            "raw_text": doc_text
        })

    df = pl.DataFrame(records)
    os.makedirs(os.path.dirname(output_parquet), exist_ok=True)
    df.write_parquet(output_parquet)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(records[:100], f, indent=2)

    print(f"Generated document intelligence dataset: {len(df)} records saved to {output_parquet} & {output_json}")
    return df


def train_model(data_path: str = "ml/models/document_intelligence/data/documents_6k.parquet",
                output_path: str = "ml/models/document_intelligence/artifacts/document_extractor.pkl"):
    print("Calibrating Document Intelligence token confidence model on 6k invoices...")
    if not os.path.exists(data_path):
        df = generate_document_dataset(data_path)
    else:
        df = pl.read_parquet(data_path)

    # Train a confidence calibration regressor on extracted feature indicators
    X = np.column_stack([
        df["total_amount"].to_numpy(),
        df["subtotal"].to_numpy(),
        df["tax_amount"].to_numpy(),
        df["extracted_fields_count"].to_numpy()
    ])
    y = df["average_confidence"].to_numpy()

    calibrator = Ridge(alpha=1.0)
    calibrator.fit(X, y)

    bundle = {
        "calibrator": calibrator,
        "sample_count": len(df),
        "mean_confidence": float(np.mean(y))
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"Artifact saved to {output_path} (calibrated on {len(df)} samples)")
    return bundle


if __name__ == "__main__":
    train_model()

