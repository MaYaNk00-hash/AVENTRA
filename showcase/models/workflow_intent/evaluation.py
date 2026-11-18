import json
from showcase.core import LocalModel, evaluate, folder
if __name__ == "__main__":
    model=LocalModel("workflow_intent")
    data=json.loads((folder("workflow_intent")/"dataset.json").read_text())
    print(json.dumps(evaluate("workflow_intent",model.model,data["test"]),indent=2))
