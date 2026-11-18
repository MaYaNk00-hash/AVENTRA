from showcase.core import prepare
def preprocess(records):
    return prepare("transaction_anomaly", records)
