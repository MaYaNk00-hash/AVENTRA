import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.workflow_planner.inference import WorkflowPlannerModel


def evaluate():
    m = WorkflowPlannerModel()
    m.load()
    print("Workflow Planner Evaluation Metrics:")
    print(m.evaluate())


if __name__ == "__main__":
    evaluate()

