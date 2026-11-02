"""
Training and vocabulary fitting for Semantic Schema Mapper.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.semantic_schema_mapper.inference import SemanticSchemaMapperModel


def train():
    print("Fitting canonical vocabulary and TF-IDF representations...")
    model = SemanticSchemaMapperModel()
    model.load()
    print("Schema mapper initialized and ready.")


if __name__ == "__main__":
    train()

