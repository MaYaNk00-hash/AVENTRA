import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))
from ml.models.anomaly_detection.inference import AnomalyDetectionModel
from ml.shared.schemas.base import ModelExecutionStatus


def test_anomaly_detection_normal():
    model = AnomalyDetectionModel()
    model.load()

    normal_tx = {
        "transaction_id": "TX-1001",
        "vendor_id": "VEND-REGULAR",
        "amount": 1050.0,
        "historical_avg_amount": 1000.0,
        "historical_std_amount": 200.0,
        "vendor_age_days": 365,
        "transactions_last_24h": 1,
        "is_weekend": False
    }

    out = model.predict(normal_tx)
    assert out.execution_status == ModelExecutionStatus.SUCCESS
    pred = out.prediction
    assert pred["risk_tier"] == "LOW"
    assert pred["requires_human_approval"] is False


def test_anomaly_detection_spike_and_new_vendor():
    model = AnomalyDetectionModel()
    model.load()

    suspicious_tx = {
        "transaction_id": "TX-9999",
        "vendor_id": "VEND-SUSPICIOUS-NEW",
        "amount": 75000.0,
        "historical_avg_amount": 1200.0,
        "historical_std_amount": 300.0,
        "vendor_age_days": 2,
        "transactions_last_24h": 8,
        "is_weekend": True
    }

    out = model.predict(suspicious_tx)
    assert out.execution_status == ModelExecutionStatus.SUCCESS
    pred = out.prediction
    assert pred["risk_tier"] in ["HIGH", "CRITICAL"]
    assert pred["requires_human_approval"] is True
    assert len(pred["anomaly_indicators"]) >= 2

