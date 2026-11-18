"""
Training pipeline for AVENTRA Adaptation Recommender model.
Generates an open-source style enterprise database schema drift and evolution dataset of at most 6,000 scenarios,
fits a schema mutation classifier and breaking-change impact predictor model, and saves the artifact.
"""

import os
import sys
import pickle
import random
import json
import polars as pl
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.adaptation_recommender.preprocessing import DriftInput
from ml.models.adaptation_recommender.features import analyze_schema_drift, compute_semantic_drift_similarity

COMMON_FIELD_EVOLUTIONS = [
    ("company_name", "organization_legal_name", "varchar(255)", "varchar(255)", True),
    ("billing_address", "invoicing_street_address", "text", "text", True),
    ("tax_id", "tax_identifier_code", "varchar(50)", "varchar(50)", True),
    ("customer_id", "client_uuid", "integer", "varchar(64)", True),
    ("phone", "contact_phone_number", "varchar(20)", "varchar(40)", False),
    ("email", "primary_contact_email", "varchar(100)", "varchar(150)", False),
    ("created_at", "record_creation_timestamp", "timestamp", "timestamp", False),
    ("status", "account_lifecycle_state", "varchar(20)", "varchar(50)", False),
    ("credit_limit", "authorized_credit_ceiling", "decimal(12,2)", "decimal(14,2)", True),
    ("shipping_loc", "fulfillment_delivery_address", "text", "text", False)
]


def generate_drift_dataset(output_parquet: str = "ml/models/adaptation_recommender/data/schema_drift_6k.parquet",
                           output_json: str = "ml/models/adaptation_recommender/data/schema_drift_6k.json",
                           max_samples: int = 6000) -> pl.DataFrame:
    random.seed(42)
    records = []

    for i in range(max_samples):
        old_f, new_f, old_t, new_t, is_breaking = random.choice(COMMON_FIELD_EVOLUTIONS)
        
        # Suffix variation for realism
        tag = f"_{i % 50}" if random.random() < 0.3 else ""
        f1 = f"{old_f}{tag}"
        f2 = f"{new_f}{tag}"

        sim = compute_semantic_drift_similarity(f1, f2)
        has_type_shift = 1 if old_t != new_t else 0
        is_breaking_val = 1 if (is_breaking or has_type_shift) else 0

        drift_payload = {
            "old_schema": {
                "system_name": f"SYSTEM_{i % 10}",
                "version": "v1.0",
                "fields": [{"name": f1, "datatype": old_t}]
            },
            "new_schema": {
                "system_name": f"SYSTEM_{i % 10}",
                "version": "v2.0",
                "fields": [{"name": f2, "datatype": new_t}]
            },
            "active_workflows": [
                {"id": f"wf-{i % 5}", "name": "Enterprise Workflow", "required_fields": [f1]}
            ]
        }

        records.append({
            "scenario_id": f"DRIFT-{i:05d}",
            "old_field": f1,
            "new_field": f2,
            "semantic_similarity": sim,
            "has_type_shift": has_type_shift,
            "is_breaking": is_breaking_val,
            "is_renamed": 1 if sim >= 0.60 else 0
        })

    df = pl.DataFrame(records)
    os.makedirs(os.path.dirname(output_parquet), exist_ok=True)
    df.write_parquet(output_parquet)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(records[:100], f, indent=2)

    print(f"Generated schema drift dataset: {len(df)} records saved to {output_parquet} & {output_json}")
    return df


def train_model(data_path: str = "ml/models/adaptation_recommender/data/schema_drift_6k.parquet",
                output_path: str = "ml/models/adaptation_recommender/artifacts/adaptation_recommender.pkl"):
    print("Training Adaptation Recommender decision tree on 6k schema drift events...")
    if not os.path.exists(data_path):
        df = generate_drift_dataset(data_path)
    else:
        df = pl.read_parquet(data_path)

    features = ["semantic_similarity", "has_type_shift"]
    X = df.select(features).to_numpy()
    y = df["is_breaking"].to_numpy()

    dt = DecisionTreeClassifier(max_depth=4, random_state=42)
    dt.fit(X, y)

    bundle = {
        "model": dt,
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

