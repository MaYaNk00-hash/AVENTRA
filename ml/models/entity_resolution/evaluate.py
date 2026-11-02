"""
Evaluation script for AVENTRA Entity Resolution model.
Validates performance against held-out validation pairs and generates confusion metrics.
"""

import os
import sys
import time
import pickle
import polars as pl
from typing import Dict

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.entity_resolution.inference import EntityResolutionModel


def run_evaluation() -> Dict[str, float]:
    print("Evaluating Entity Resolution model...")
    model = EntityResolutionModel()
    model.load()
    metrics = model.evaluate()
    print("Evaluation Results:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    return metrics


if __name__ == "__main__":
    run_evaluation()

