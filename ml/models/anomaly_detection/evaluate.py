import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.anomaly_detection.inference import AnomalyDetectionModel


def evaluate():
    m = AnomalyDetectionModel()
    m.load()
    print("Anomaly Detection Evaluation Metrics:")
    print(m.evaluate())


if __name__ == "__main__":
    evaluate()

