import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.document_intelligence.inference import DocumentIntelligenceModel


def evaluate():
    m = DocumentIntelligenceModel()
    m.load()
    print("Document Intelligence Evaluation Metrics:")
    print(m.evaluate())


if __name__ == "__main__":
    evaluate()

