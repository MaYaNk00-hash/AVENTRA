"""Actual artifact inference; only the provider transport/tool selection is mocked."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from backend.agents import local_intelligence
from ml.shared.model_registry.bootstrap import bootstrap_registry

CASES = {
    "intent_parser": {"prompt": "Review unusual supplier transactions for anomalies"},
    "workflow_planner": {"intent_type": "DETECT_ANOMALIES"},
    "semantic_schema_mapper": {"fields": [{"field_name": "billing_total", "description": "Total invoice amount", "datatype": "number"}]},
    "invoice_reconciliation": {"po_total": 1200, "inv_total": 1260, "price_variance": 60, "qty_variance": 0, "tax_diff": 0, "has_exceptions": 1},
    "adaptation_recommender": {"semantic_similarity": .82, "has_type_shift": 1},
    "document_intelligence": {"document_text": "Invoice Number: HYBRID-001\nSubtotal: $1200.00\nTax: $96.00\nTotal Amount: $1296.00", "filename": "synthetic-example.txt"},
    "anomaly_detection": {"transaction_id": "HYBRID-T1", "vendor_id": "DEMO-V1", "amount": 19000, "historical_avg_amount": 1200, "historical_std_amount": 250, "vendor_age_days": 4, "transactions_last_24h": 9, "is_weekend": True, "payment_terms_days": 30},
    "entity_resolution": {"query": {"entity_id": "DEMO-A", "business_name": "Synthetic Cedar Components", "business_address": "12 Fictional Road Pune", "country": "IN", "source_system": "CRM"}, "candidates": [{"entity_id": "DEMO-B", "business_name": "Synthetic Cedar Components Ltd", "business_address": "12 Fictional Road Pune", "country": "IN", "source_system": "ERP"}]},
}


@pytest.mark.parametrize("name", CASES)
def test_existing_artifact_inference_preserves_bytes(name):
    bootstrap_registry()
    _, path, before = local_intelligence.load_artifact(name)
    result = local_intelligence.predict(name, CASES[name])
    assert result["artifact_sha256"] == before == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["output"] and result["duration_ms"] >= 0
    assert result["evaluation_metrics"] is None
    if name == "anomaly_detection":
        assert isinstance(result["output"]["raw_anomaly_score"], float)
        assert result["output"]["score"] is None
        assert "not fraud probabilities" in result["output"]["score_type"]
    if name == "workflow_planner":
        assert result["component"] == "local_template"
        assert result["output"]["tools_executed"] is False
        assert result["output"]["score"] is None


def test_text_probabilities_match_loaded_estimator():
    bundle,_,_=local_intelligence.load_artifact("intent_parser")
    expected=bundle["classifier"].predict_proba(bundle["vectorizer"].transform([CASES["intent_parser"]["prompt"]]))[0]
    result=local_intelligence.predict("intent_parser",CASES["intent_parser"])["output"]
    assert sum(result["class_probabilities"].values())==pytest.approx(1)
    assert list(result["class_probabilities"].values())==pytest.approx(expected.tolist())


def test_missing_artifact_fails_without_baseline_training(tmp_path,monkeypatch):
    monkeypatch.setattr(local_intelligence,"ROOT",tmp_path)
    with pytest.raises(HTTPException) as error:
        local_intelligence.predict("anomaly_detection",CASES["anomaly_detection"])
    assert error.value.status_code==503
    assert not list(tmp_path.rglob("*.pkl"))


def test_invalid_features_are_rejected():
    with pytest.raises(HTTPException) as error:
        local_intelligence.predict("invoice_reconciliation",{"po_total":float("nan")})
    assert error.value.status_code==422
