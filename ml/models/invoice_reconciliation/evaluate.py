import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ml.models.invoice_reconciliation.inference import InvoiceReconciliationModel


def evaluate():
    m = InvoiceReconciliationModel()
    m.load()
    print("Invoice Reconciliation Evaluation Metrics:")
    print(m.evaluate())


if __name__ == "__main__":
    evaluate()

