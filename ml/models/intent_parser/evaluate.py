import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.intent_parser.inference import IntentParserModel


def evaluate():
    m = IntentParserModel()
    m.load()
    print("Intent Parser Evaluation Metrics:")
    print(m.evaluate())


if __name__ == "__main__":
    evaluate()

