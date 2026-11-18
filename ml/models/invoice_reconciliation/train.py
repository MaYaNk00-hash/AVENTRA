"""
Training pipeline for AVENTRA Invoice Reconciliation model.
Generates an open-source enterprise procurement 3-way matching dataset of at most 6,000 cases
(Invoice, PO, Goods Receipt), fits a decision tree variance calibrator model, and saves the artifact.
"""

import os
import sys
import pickle
import random
import json
import numpy as np
import polars as pl
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.invoice_reconciliation.preprocessing import ReconciliationInput
from ml.models.invoice_reconciliation.features import calculate_variances


def generate_reconciliation_dataset(output_parquet: str = "ml/models/invoice_reconciliation/data/reconciliation_6k.parquet",
                                   output_json: str = "ml/models/invoice_reconciliation/data/reconciliation_6k.json",
                                   max_samples: int = 6000) -> pl.DataFrame:
    random.seed(42)
    np.random.seed(42)

    records = []
    cases = ["EXACT", "TOLERATED", "PRICE_DISCREPANCY", "QTY_DISCREPANCY", "TAX_DISCREPANCY"]
    weights = [0.40, 0.25, 0.20, 0.10, 0.05]

    for i in range(max_samples):
        case = random.choices(cases, weights=weights, k=1)[0]
        base_unit_price = round(float(np.random.uniform(20.0, 500.0)), 2)
        base_qty = int(np.random.randint(5, 100))
        po_total = round(base_unit_price * base_qty, 2)
        po_tax = round(po_total * 0.08, 2)

        inv_unit_price = base_unit_price
        inv_qty = base_qty
        inv_tax = po_tax
        rcv_qty = base_qty

        if case == "EXACT":
            pass
        elif case == "TOLERATED":
            # 0.5% to 1.5% variance, below $40
            pct = np.random.uniform(0.005, 0.015)
            inv_unit_price = round(base_unit_price * (1.0 + pct), 2)
        elif case == "PRICE_DISCREPANCY":
            # 5% to 25% price hike, over $50
            pct = np.random.uniform(0.05, 0.25)
            inv_unit_price = round(base_unit_price * (1.0 + pct), 2)
        elif case == "QTY_DISCREPANCY":
            # Invoice billed more than goods received
            inv_qty = int(base_qty * np.random.uniform(1.2, 1.5))
        elif case == "TAX_DISCREPANCY":
            inv_tax = round(po_tax + np.random.uniform(15.0, 80.0), 2)

        inv_subtotal = round(inv_unit_price * inv_qty, 2)
        inv_total = round(inv_subtotal + inv_tax, 2)

        scenario = {
            "invoice": {
                "invoice_number": f"INV-{i:05d}",
                "po_number": f"PO-{i:05d}",
                "vendor_id": f"VEND-{random.randint(100, 999)}",
                "invoice_date": "2026-10-25",
                "subtotal": inv_subtotal,
                "tax_amount": inv_tax,
                "total_amount": inv_total,
                "line_items": [
                    {"sku": f"SKU-{i:04d}", "description": "Component", "quantity": inv_qty, "unit_price": inv_unit_price, "total": inv_subtotal}
                ]
            },
            "purchase_order": {
                "po_number": f"PO-{i:05d}",
                "vendor_id": f"VEND-{random.randint(100, 999)}",
                "total_amount": round(po_total + po_tax, 2),
                "line_items": [
                    {"sku": f"SKU-{i:04d}", "description": "Component", "quantity": base_qty, "unit_price": base_unit_price, "total": po_total}
                ]
            },
            "goods_receipt": {
                "receipt_id": f"GR-{i:05d}",
                "po_number": f"PO-{i:05d}",
                "received_items": {f"SKU-{i:04d}": float(rcv_qty)}
            }
        }

        # Calculate variance features
        rec_in = ReconciliationInput(**scenario)
        analysis = calculate_variances(rec_in, price_tolerance_pct=2.0)

        price_var = analysis["total_price_variance"]
        qty_var = analysis["total_qty_variance"]
        has_exc = 1 if analysis["has_exceptions"] else 0
        status_label = 0 if not analysis["has_exceptions"] else (1 if price_var <= 50.0 and analysis["has_exceptions"] else 2)

        records.append({
            "case_id": f"REC-{i:05d}",
            "po_total": po_total,
            "inv_total": inv_total,
            "price_variance": price_var,
            "qty_variance": qty_var,
            "tax_diff": abs(inv_tax - po_tax),
            "has_exceptions": has_exc,
            "scenario_type": case,
            "reconciliation_status_class": status_label
        })

    df = pl.DataFrame(records)
    os.makedirs(os.path.dirname(output_parquet), exist_ok=True)
    df.write_parquet(output_parquet)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(records[:100], f, indent=2)

    print(f"Generated reconciliation dataset: {len(df)} records saved to {output_parquet} & {output_json}")
    return df


def train_model(data_path: str = "ml/models/invoice_reconciliation/data/reconciliation_6k.parquet",
                output_path: str = "ml/models/invoice_reconciliation/artifacts/reconciliation_calibrator.pkl"):
    print("Training Decision Tree variance calibrator on 6k procurement triples...")
    if not os.path.exists(data_path):
        df = generate_reconciliation_dataset(data_path)
    else:
        df = pl.read_parquet(data_path)

    features = ["po_total", "inv_total", "price_variance", "qty_variance", "tax_diff", "has_exceptions"]
    X = df.select(features).to_numpy()
    y = df["reconciliation_status_class"].to_numpy()

    dt = DecisionTreeClassifier(max_depth=5, random_state=42)
    dt.fit(X, y)

    bundle = {
        "calibrator": dt,
        "features": features,
        "sample_count": len(df)
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"Artifact saved to {output_path} (trained on {len(df)} samples)")
    return bundle


if __name__ == "__main__":
    train_model()

