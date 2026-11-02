from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ml.shared.model_registry.registry import ModelRegistry
from ml.shared.model_registry.bootstrap import bootstrap_registry

router = APIRouter(prefix="/api/ml", tags=["ML Intelligence"])

# Ensure registry is initialized
bootstrap_registry()


class InferenceRequest(BaseModel):
    data: Dict[str, Any]


@router.get("/models")
def list_models():
    return ModelRegistry.list_models()


@router.get("/models/{model_id}")
def get_model(model_id: str):
    models = {m["model_identifier"]: m for m in ModelRegistry.list_models()}
    if model_id not in models:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found in registry.")
    return models[model_id]


@router.post("/models/{model_id}/predict")
def run_model_inference(model_id: str, req: InferenceRequest):
    try:
        model = ModelRegistry.get_model(model_id)
        out = model.predict(req.data)
        return out.model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/{model_id}/evaluate")
def run_model_evaluation(model_id: str):
    try:
        model = ModelRegistry.get_model(model_id)
        metrics = model.evaluate()
        ModelRegistry.update_metrics(model_id, metrics)
        return {"model_id": model_id, "metrics": metrics, "status": "EVALUATION_SUCCESS"}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")


@router.get("/dependency-graph")
def get_model_dependency_graph():
    """
    Returns visual dependency graph structure between models, data stores, and workflow gates.
    """
    nodes = [
        {"id": "m3", "label": "M3: Intent Parser", "type": "model", "category": "NLP", "position": {"x": 50, "y": 180}},
        {"id": "m4", "label": "M4: Workflow Planner", "type": "model", "category": "ORCHESTRATION", "position": {"x": 300, "y": 180}},
        {"id": "m7", "label": "M7: Document Intelligence", "type": "model", "category": "VISION_DOC", "position": {"x": 580, "y": 60}},
        {"id": "m1", "label": "M1: Entity Resolution", "type": "model", "category": "MATCHING", "position": {"x": 580, "y": 180}},
        {"id": "m2", "label": "M2: Schema Mapper", "type": "model", "category": "SCHEMA", "position": {"x": 580, "y": 300}},
        {"id": "m5", "label": "M5: Invoice Reconciliation", "type": "model", "category": "FINANCE", "position": {"x": 860, "y": 60}},
        {"id": "m8", "label": "M8: Anomaly Detector", "type": "model", "category": "RISK", "position": {"x": 860, "y": 180}},
        {"id": "m6", "label": "M6: Adaptation Recommender", "type": "model", "category": "GOVERNANCE", "position": {"x": 860, "y": 300}},
        {"id": "gate", "label": "Trust & Approval Gate", "type": "gate", "category": "SECURITY", "position": {"x": 1140, "y": 180}},
        {"id": "ledger", "label": "Tamper-Evident Ledger", "type": "audit", "category": "AUDIT", "position": {"x": 1380, "y": 180}}
    ]

    edges = [
        {"id": "e_m3_m4", "source": "m3", "target": "m4", "label": "Typed Intent JSON"},
        {"id": "e_m4_m7", "source": "m4", "target": "m7", "label": "Doc Task"},
        {"id": "e_m4_m1", "source": "m4", "target": "m1", "label": "Entity Link Task"},
        {"id": "e_m4_m2", "source": "m4", "target": "m2", "label": "Schema Task"},
        {"id": "e_m7_m5", "source": "m7", "target": "m5", "label": "Extracted Invoices"},
        {"id": "e_m1_gate", "source": "m1", "target": "gate", "label": "Match Evidence (p >= 0.85)"},
        {"id": "e_m5_m8", "source": "m5", "target": "m8", "label": "Reconciled PO & Variance"},
        {"id": "e_m2_m6", "source": "m2", "target": "m6", "label": "Candidate Mappings"},
        {"id": "e_m8_gate", "source": "m8", "target": "gate", "label": "Risk Tier Evaluation"},
        {"id": "e_m6_gate", "source": "m6", "target": "gate", "label": "Migration Diff"},
        {"id": "e_gate_ledger", "source": "gate", "target": "ledger", "label": "Authorized & Signed Action"}
    ]

    return {"nodes": nodes, "edges": edges}

