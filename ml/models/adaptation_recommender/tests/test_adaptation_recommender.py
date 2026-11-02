import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))
from ml.models.adaptation_recommender.inference import AdaptationRecommenderModel
from ml.shared.schemas.base import ModelExecutionStatus


def test_schema_drift_detection():
    model = AdaptationRecommenderModel()
    model.load()

    data = {
        "old_schema": {
            "system_name": "COMPANY_A_CRM",
            "version": "v1.0",
            "fields": [
                {"name": "company_name", "datatype": "varchar(255)"},
                {"name": "billing_address", "datatype": "text"},
                {"name": "tax_id", "datatype": "varchar(50)"}
            ]
        },
        "new_schema": {
            "system_name": "COMPANY_A_CRM",
            "version": "v2.0",
            "fields": [
                {"name": "organization_legal_name", "datatype": "varchar(255)"}, # renamed
                {"name": "billing_address", "datatype": "varchar(500)"},          # type modified
                {"name": "tax_id", "datatype": "varchar(50)"},
                {"name": "credit_score", "datatype": "integer"}                  # added
            ]
        },
        "active_workflows": [
            {
                "id": "wf-onboarding",
                "name": "Customer Onboarding Workflow",
                "required_fields": ["company_name", "tax_id"]
            }
        ]
    }

    out = model.predict(data)
    assert out.execution_status == ModelExecutionStatus.SUCCESS
    pred = out.prediction
    assert pred["requires_authenticated_approval"] is True
    report = pred["drift_report"]
    assert len(report["added_fields"]) == 1
    assert len(report["renamed_fields"]) == 1
    assert report["renamed_fields"][0]["old_field"] == "company_name"
    assert report["renamed_fields"][0]["new_field"] == "organization_legal_name"
    assert len(report["impacted_workflows"]) == 1

