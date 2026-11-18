"""Read-only adapters for the existing ml/ artifacts. Never trains or saves them."""
import copy
import hashlib
import json
import math
import pickle
from pathlib import Path
import time

import numpy as np
from fastapi import HTTPException
from ml.shared.model_registry.registry import ModelRegistry

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = {
    "entity_resolution": ("matching_lgb_model.pkl", "LightGBM classifier"),
    "semantic_schema_mapper": ("schema_mapper.pkl", "TF-IDF + Logistic Regression"),
    "intent_parser": ("intent_model.pkl", "TF-IDF + Logistic Regression"),
    "workflow_planner": ("workflow_planner.pkl", "Deterministic saved templates; not a learned estimator"),
    "invoice_reconciliation": ("reconciliation_calibrator.pkl", "Decision Tree feature classifier"),
    "adaptation_recommender": ("adaptation_recommender.pkl", "Decision Tree breaking-change classifier"),
    "document_intelligence": ("document_extractor.pkl", "Ridge extraction-score regressor + deterministic parsing"),
    "anomaly_detection": ("isolation_forest.pkl", "Isolation Forest"),
}
_cache = {}


def load_artifact(name):
    if name not in ARTIFACTS:
        raise HTTPException(422, "Unsupported local model")
    path = ROOT / "ml" / "models" / name / "artifacts" / ARTIFACTS[name][0]
    try:
        content = path.read_bytes()
        fingerprint = hashlib.sha256(content).hexdigest()
        if name not in _cache or _cache[name][0] != fingerprint:
            bundle = pickle.loads(content)  # Only the fixed repository-owned artifact paths.
            if name in ("intent_parser", "semantic_schema_mapper"):
                if not hasattr(bundle["classifier"], "classes_") or not hasattr(bundle["vectorizer"], "vocabulary_"):
                    raise ValueError("Unfitted text artifact")
            elif name == "workflow_planner":
                if not isinstance(bundle.get("templates"), dict): raise ValueError("Missing templates")
            else:
                estimator = bundle.get("calibrator", bundle.get("model")) if isinstance(bundle, dict) else bundle
                if not hasattr(estimator, "n_features_in_"): raise ValueError("Unfitted estimator")
            _cache[name] = (fingerprint, bundle)
        return _cache[name][1], path, fingerprint
    except (OSError, ValueError, KeyError, TypeError, pickle.UnpicklingError, EOFError, ImportError, AttributeError) as error:
        raise HTTPException(503, f"Local artifact {name} is unavailable ({type(error).__name__}); no fallback prediction") from error


def inventory():
    metadata = {row["model_identifier"]: row for row in ModelRegistry.list_models()}
    result = []
    for name, (filename, kind) in ARTIFACTS.items():
        row = {"id": name, "version": metadata.get(name, {}).get("model_version"), "implementation": kind,
               "artifact_path": f"ml/models/{name}/artifacts/{filename}",
               "evaluation_metrics": None, "evaluation_note": "No held-out evaluation report verified by this adapter; configured constants are not measured metrics.",
               "training_provenance": "Existing artifact. Repository training scripts use generated scenarios for several models; no retraining performed."}
        try:
            bundle, _, fingerprint = load_artifact(name)
            row.update(status="loaded", artifact_sha256=fingerprint)
            if isinstance(bundle, dict): row["declared_training_samples"] = bundle.get("sample_count", bundle.get("dataset_sample_size"))
        except HTTPException as error:
            row.update(status="unavailable", error=error.detail)
        result.append(row)
    return result


def numeric_features(payload, names):
    values = []
    for name in names:
        value = payload.get(name)
        if isinstance(value, bool): value = int(value)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Provide finite numeric feature {name}")
        values.append(float(value))
    return np.array([values])


def classify(estimator, features):
    probabilities = estimator.predict_proba(features)[0]
    classes = [str(label) for label in estimator.classes_]
    best = int(np.argmax(probabilities))
    return {"prediction": classes[best], "score": float(probabilities[best]),
            "class_probabilities": dict(zip(classes, map(float, probabilities))),
            "score_type": "estimator class probability; calibration not independently verified"}


def predict(name, payload):
    started = time.perf_counter()
    bundle, path, fingerprint = load_artifact(name)
    features = payload
    try:
        if len(json.dumps(payload)) > 200000: raise ValueError("Analysis payload exceeds 200 KB")
        if name == "intent_parser":
            from ml.models.intent_parser.preprocessing import preprocess_intent_input
            from ml.models.intent_parser.features import detect_prompt_injection
            text = preprocess_intent_input(payload).cleaned_prompt
            output = classify(bundle["classifier"], bundle["vectorizer"].transform([text]))
            output["security_blocked"] = detect_prompt_injection(text)
            output["security_note"] = "Injection pattern check is deterministic; the classifier never authorizes writes."
            features = {"prompt": text}
        elif name == "semantic_schema_mapper":
            from ml.models.semantic_schema_mapper.features import normalize_field_name
            fields = payload.get("fields")
            if not isinstance(fields, list) or not 1 <= len(fields) <= 100: raise ValueError("Provide 1 to 100 fields")
            texts = [f"{normalize_field_name(field['field_name'])} {field.get('description', '')}" for field in fields]
            matrix = bundle["vectorizer"].transform(texts)
            output = {"mappings": [{"field_name": field["field_name"], **classify(bundle["classifier"], matrix[index])} for index, field in enumerate(fields)]}
            features = {"field_texts": texts}
        elif name == "workflow_planner":
            from ml.models.workflow_planner.features import validate_dag_structure
            intent = payload.get("intent_type")
            if intent not in bundle["templates"]: raise ValueError("Provide a supported intent_type: " + ", ".join(bundle["supported_intents"]))
            output = copy.deepcopy(bundle["templates"][intent])
            output.update(intent_type=intent, validation=validate_dag_structure(output["nodes"], output["edges"]),
                          score=None, score_type="No probability: deterministic template lookup", tools_executed=False)
        elif name in ("invoice_reconciliation", "adaptation_recommender"):
            if name == "adaptation_recommender" and (not isinstance(payload.get("semantic_similarity"), (int, float)) or not 0 <= payload["semantic_similarity"] <= 1 or payload.get("has_type_shift") not in (0, 1, False, True)):
                raise ValueError("semantic_similarity must be 0..1 and has_type_shift must be 0 or 1")
            names = bundle["features"]
            vector = numeric_features(payload, names)
            estimator = bundle["calibrator"] if name == "invoice_reconciliation" else bundle["model"]
            output = classify(estimator, vector)
            if name == "invoice_reconciliation":
                output["label_definition"] = {"0": "No exceptions under the training rules", "1": "Training-rule exceptions with price variance <= 50", "2": "Training-rule exceptions with price variance > 50"}.get(output["prediction"])
                output["limitation"] = "Feature classifier trained on generated rule labels; not proof of an invoice's validity or payment authorization."
            else:
                output["label_definition"] = "Breaking change" if output["prediction"] == "1" else "Non-breaking under training labels"
            output["recommendation"] = "Advisory classification only; human approval is required for any enterprise write."
            features = dict(zip(names, vector[0].tolist()))
        elif name == "anomaly_detection":
            from ml.models.anomaly_detection.preprocessing import preprocess_transaction
            transaction = preprocess_transaction(payload)
            vector = np.array([transaction.features])
            if not np.isfinite(vector).all(): raise ValueError("Transaction features must be finite")
            flag = int(bundle.predict(vector)[0]) == -1
            output = {"is_anomaly": flag, "raw_anomaly_score": float(bundle.score_samples(vector)[0]),
                      "decision_function": float(bundle.decision_function(vector)[0]),
                      "review_recommendation": "Human review recommended" if flag else "No statistical anomaly flagged",
                      "score": None, "score_type": "Uncalibrated Isolation Forest scores; not fraud probabilities"}
            features = dict(zip(["amount", "amount_ratio", "z_score", "new_vendor_flag", "velocity", "weekend_flag", "terms_difference"], transaction.features))
        elif name == "document_intelligence":
            from ml.models.document_intelligence.preprocessing import preprocess_document
            from ml.models.document_intelligence.features import parse_document_fields
            document = preprocess_document(payload)
            if not document.extracted_text: raise ValueError("Provide document_text or a text-bearing PDF")
            fields = parse_document_fields(document.extracted_text)["extracted_fields"]
            features = {"total_amount": float(fields.get("total_amount") or 0), "subtotal": float(fields.get("subtotal") or 0),
                        "tax_amount": float(fields.get("tax_amount") or 0), "extracted_fields_count": sum(value is not None for value in fields.values())}
            score = float(bundle["calibrator"].predict(numeric_features(features, list(features)))[0])
            output = {"extracted_fields": fields, "regression_score": score, "score_type": "Ridge score for extraction features; not calibrated correctness probability",
                      "extraction_method": "Deterministic field parsing; Ridge artifact supplies the separate regression score"}
        else:
            from ml.models.entity_resolution.inference import EntityResolutionModel
            if not isinstance(payload.get("candidates"), list) or len(payload["candidates"]) > 100: raise ValueError("Provide up to 100 candidates")
            model = EntityResolutionModel()
            # Use the verified loaded artifact directly; do not invoke any fallback loader.
            model.model = bundle
            model.is_loaded = True
            response = model.predict(payload)
            if response.execution_status == "FAILED": raise ValueError(response.error_details)
            output = response.prediction
        json.dumps(output, allow_nan=False)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise HTTPException(422, f"Invalid {name} input: {error}") from error
    version = next((row["model_version"] for row in ModelRegistry.list_models() if row["model_identifier"] == name), None)
    return {"component": "local_ml" if name != "workflow_planner" else "local_template",
            "model": name, "version": version, "implementation": ARTIFACTS[name][1],
            "artifact_path": str(path.relative_to(ROOT)), "artifact_sha256": fingerprint,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3), "input": payload,
            "input_features": features, "output": output, "evaluation_metrics": None}
