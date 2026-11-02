import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))
from ml.models.semantic_schema_mapper.inference import SemanticSchemaMapperModel
from ml.shared.schemas.base import ModelExecutionStatus


def test_schema_mapper_load():
    model = SemanticSchemaMapperModel()
    model.load()
    assert model.is_loaded is True
    assert model.health_check()["status"] == "HEALTHY"


def test_schema_mapper_inference():
    model = SemanticSchemaMapperModel()
    model.load()

    input_data = {
        "fields": [
            {
                "field_name": "cust_legal_name",
                "datatype": "varchar(255)",
                "description": "Registered company name of client",
                "sample_values": ["Microsoft Corp", "Alphabet Inc"]
            },
            {
                "field_name": "inv_total_val",
                "datatype": "decimal(12,2)",
                "description": "Total payable invoice balance",
                "sample_values": [14200.50, 850.00]
            },
            {
                "field_name": "billing_street_loc",
                "datatype": "text",
                "description": "Invoicing physical address",
                "sample_values": ["100 Main St, Austin TX"]
            }
        ]
    }

    out = model.predict(input_data)
    assert out.execution_status == ModelExecutionStatus.SUCCESS
    mappings = out.prediction["mappings"]
    assert len(mappings) == 3

    # Check top matches
    m_name = next(m for m in mappings if m["source_field"] == "cust_legal_name")
    assert m_name["target_canonical_concept"] == "customer_name"
    assert m_name["match_confidence"] > 0.70

    m_total = next(m for m in mappings if m["source_field"] == "inv_total_val")
    assert m_total["target_canonical_concept"] == "total_amount"

    m_addr = next(m for m in mappings if m["source_field"] == "billing_street_loc")
    assert m_addr["target_canonical_concept"] == "billing_address"

