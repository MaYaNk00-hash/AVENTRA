import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.adaptation_recommender.inference import AdaptationRecommenderModel


def evaluate():
    m = AdaptationRecommenderModel()
    m.load()
    print("Adaptation Recommender Evaluation Metrics:")
    print(m.evaluate())


if __name__ == "__main__":
    evaluate()

