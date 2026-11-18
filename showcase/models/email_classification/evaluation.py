import json
from showcase.core import LocalModel, evaluate, folder
if __name__ == "__main__":
    model=LocalModel("email_classification")
    data=json.loads((folder("email_classification")/"dataset.json").read_text())
    print(json.dumps(evaluate("email_classification",model.model,data["test"]),indent=2))
