import json
from showcase.core import LocalModel, evaluate, folder
if __name__ == "__main__":
    model=LocalModel("transaction_anomaly")
    data=json.loads((folder("transaction_anomaly")/"dataset.json").read_text())
    print(json.dumps(evaluate("transaction_anomaly",model.model,data["test"]),indent=2))
