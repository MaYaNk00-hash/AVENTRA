import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))
from ml.models.entity_resolution.inference import EntityResolutionModel
from ml.shared.schemas.base import ModelExecutionStatus


def test_entity_resolution_load():
    model = EntityResolutionModel()
    model.load()
    assert model.is_loaded is True
    health = model.health_check()
    assert health["status"] == "HEALTHY"


def test_entity_resolution_exact_match():
    model = EntityResolutionModel()
    model.load()

    query = {
        "entity_id": "NEW-001",
        "business_name": "Acme Industrial Supplies LLC",
        "business_address": "450 Market Street Suite 200 San Francisco CA",
        "country": "US",
        "source_system": "COMPANY_A_CRM"
    }

    candidates = [
        {
            "entity_id": "ERP-991",
            "business_name": "Acme Industrial Supplies Corp",
            "business_address": "450 Market St Ste 200 San Francisco CA",
            "country": "US",
            "source_system": "COMPANY_B_ERP"
        },
        {
            "entity_id": "ERP-102",
            "business_name": "Zenith Global Logistics",
            "business_address": "1200 Broadway New York NY",
            "country": "US",
            "source_system": "COMPANY_B_ERP"
        }
    ]

    out = model.predict({"query": query, "candidates": candidates})
    assert out.execution_status == ModelExecutionStatus.SUCCESS
    assert out.confidence is not None
    assert out.confidence > 0.70
    assert out.prediction["decision"] in ["DUPLICATE_IDENTIFIED", "UNCERTAIN_MATCH_REVIEW_REQUIRED"]
    assert out.prediction["golden_record_recommendation"] is not None

