import json
from showcase.core import LocalModel, evaluate, folder
if __name__ == "__main__":
    model=LocalModel("invoice_discrepancy")
    data=json.loads((folder("invoice_discrepancy")/"dataset.json").read_text())
    print(json.dumps(evaluate("invoice_discrepancy",model.model,data["test"]),indent=2))
