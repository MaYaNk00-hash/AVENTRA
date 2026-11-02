import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))
from ml.models.workflow_planner.inference import WorkflowPlannerModel
from ml.shared.schemas.base import ModelExecutionStatus


def test_workflow_planner_onboarding():
    model = WorkflowPlannerModel()
    model.load()

    out = model.predict({
        "intent_type": "ONBOARD_CUSTOMER",
        "action_type": "WRITE"
    })
    assert out.execution_status == ModelExecutionStatus.SUCCESS
    pred = out.prediction
    assert pred["is_executable"] is True
    assert len(pred["nodes"]) == 6
    assert pred["validation"]["is_valid_dag"] is True
    assert pred["validation"]["has_cycle"] is False

