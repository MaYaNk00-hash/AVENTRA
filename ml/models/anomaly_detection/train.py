"""
Training pipeline for AVENTRA Anomaly Detection model.
Generates an open-source enterprise procurement & disbursement transaction dataset of at most 6,000 records,
extracts 7 behavioral anomaly features, trains an Isolation Forest detector, and saves the artifact.
"""

import os
import sys
import pickle
import random
import numpy as np
import polars as pl
from sklearn.ensemble import IsolationForest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.anomaly_detection.preprocessing import preprocess_transaction


def generate_transactions_dataset(output_parquet: str = "ml/models/anomaly_detection/data/transactions_6k.parquet",
                                 output_csv: str = "ml/models/anomaly_detection/data/transactions_6k.csv",
                                 total_samples: int = 6000) -> pl.DataFrame:
    random.seed(42)
    np.random.seed(42)

    anomaly_count = int(total_samples * 0.05)
    normal_count = total_samples - anomaly_count

    records = []

    # 1. Normal transactions
    for i in range(normal_count):
        hist_avg = float(np.random.uniform(500.0, 5000.0))
        hist_std = float(hist_avg * np.random.uniform(0.10, 0.25))
        amount = float(max(10.0, np.random.normal(hist_avg, hist_std)))
        vendor_age = int(np.random.randint(60, 1800))
        tx_24h = int(np.random.poisson(1.5))
        is_wknd = bool(random.random() < 0.10)
        terms = 30 if random.random() < 0.85 else 45

        tx_data = {
            "transaction_id": f"TX-NORM-{i:05d}",
            "vendor_id": f"VEND-{random.randint(100, 999)}",
            "amount": round(amount, 2),
            "currency": "USD",
            "historical_avg_amount": round(hist_avg, 2),
            "historical_std_amount": round(hist_std, 2),
            "vendor_age_days": vendor_age,
            "transactions_last_24h": tx_24h,
            "is_weekend": is_wknd,
            "payment_terms_days": terms
        }
        pt = preprocess_transaction(tx_data)
        row = dict(tx_data)
        for idx, feat_val in enumerate(pt.features):
            row[f"f_{idx}"] = feat_val
        row["is_anomaly_ground_truth"] = 0
        records.append(row)

    # 2. Anomalous transactions (spikes, new vendor bursts, weekend oddities)
    for i in range(anomaly_count):
        hist_avg = float(np.random.uniform(500.0, 3000.0))
        hist_std = float(hist_avg * 0.15)
        
        anomaly_type = random.choice(["spike", "new_vendor", "high_velocity", "weekend_surge"])
        if anomaly_type == "spike":
            amount = float(hist_avg * np.random.uniform(5.0, 15.0))
            vendor_age = random.randint(30, 365)
            tx_24h = 1
            is_wknd = False
            terms = 30
        elif anomaly_type == "new_vendor":
            amount = float(np.random.uniform(25000.0, 80000.0))
            vendor_age = random.randint(1, 5)
            tx_24h = random.randint(3, 8)
            is_wknd = random.random() < 0.5
            terms = 0  # Immediate payment demand
        elif anomaly_type == "high_velocity":
            amount = float(hist_avg * 2.0)
            vendor_age = random.randint(15, 100)
            tx_24h = random.randint(12, 35)
            is_wknd = False
            terms = 30
        else:
            amount = float(hist_avg * 4.0)
            vendor_age = random.randint(5, 50)
            tx_24h = random.randint(4, 10)
            is_wknd = True
            terms = 60

        tx_data = {
            "transaction_id": f"TX-ANOM-{i:05d}",
            "vendor_id": f"VEND-SUSP-{random.randint(10, 99)}",
            "amount": round(amount, 2),
            "currency": "USD",
            "historical_avg_amount": round(hist_avg, 2),
            "historical_std_amount": round(hist_std, 2),
            "vendor_age_days": vendor_age,
            "transactions_last_24h": tx_24h,
            "is_weekend": is_wknd,
            "payment_terms_days": terms
        }
        pt = preprocess_transaction(tx_data)
        row = dict(tx_data)
        for idx, feat_val in enumerate(pt.features):
            row[f"f_{idx}"] = feat_val
        row["is_anomaly_ground_truth"] = 1
        records.append(row)

    random.shuffle(records)
    df = pl.DataFrame(records)

    os.makedirs(os.path.dirname(output_parquet), exist_ok=True)
    df.write_parquet(output_parquet)
    df.write_csv(output_csv)
    print(f"Generated transactions dataset: {len(df)} records saved to {output_parquet} & {output_csv}")
    return df


def train_model(data_path: str = "ml/models/anomaly_detection/data/transactions_6k.parquet",
                output_path: str = "ml/models/anomaly_detection/artifacts/isolation_forest.pkl"):
    print("Training Isolation Forest anomaly detection model on 6k transaction records...")
    if not os.path.exists(data_path):
        df = generate_transactions_dataset(data_path)
    else:
        df = pl.read_parquet(data_path)

    feature_cols = [f"f_{i}" for i in range(7)]
    X = df.select(feature_cols).to_numpy()

    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42
    )
    model.fit(X)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(model, f)
    print(f"Artifact saved to {output_path} (trained on {len(df)} samples)")
    return model


if __name__ == "__main__":
    train_model()

