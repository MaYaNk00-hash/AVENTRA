"""
Evaluation and training script for Semantic Schema Mapper.
"""

import os
import sys
from typing import Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.semantic_schema_mapper.inference import SemanticSchemaMapperModel


def run_evaluation() -> Dict[str, float]:
    print("Evaluating Semantic Schema Mapper...")
    model = SemanticSchemaMapperModel()
    model.load()
    metrics = model.evaluate()
    print("Schema Mapper Evaluation Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    return metrics


if __name__ == "__main__":
    run_evaluation()

