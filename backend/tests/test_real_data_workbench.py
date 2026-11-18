"""Run with DATABASE_URL set to an isolated SQLite database."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.security.auth import create_access_token


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as client:
        yield client


def headers(username="admin"):
    return {"Authorization": "Bearer " + create_access_token({"sub": username})}


def upload(client, rows, name="records", username="admin"):
    response = client.post("/api/workbench/datasets", headers=headers(username), json={"name": name, "domain": "CRM", "format": "json", "content": json.dumps(rows)})
    assert response.status_code == 200, response.text
    return response.json()


def test_import_requires_auth_and_valid_rows(client):
    assert client.get("/api/workbench/datasets").status_code == 401
    response = client.post("/api/workbench/datasets", headers=headers(), json={"name": "bad", "domain": "ERP", "format": "csv", "content": "id,name\n1,A,extra"})
    assert response.status_code == 422
    first = upload(client, [{"id": "unseen", "name": "Narmada Precision"}])
    second = upload(client, [{"id": "unseen", "name": "Different company"}])
    assert first["sha256"] != second["sha256"]
    assert first["row_count"] == 1
    assert first["columns"] == ["id", "name"]


def test_owner_isolation(client):
    dataset = upload(client, [{"name": "private-owner-record"}])
    visible = client.get("/api/workbench/datasets", headers=headers("compliance")).json()
    assert dataset["id"] not in [item["id"] for item in visible]
    response = client.post("/api/workbench/analyze", headers=headers("compliance"), json={"task": "schema", "dataset_id": dataset["id"]})
    assert response.status_code == 404


def test_entity_mapping_uses_actual_dataset_record(client):
    import polars as pl
    record = pl.read_csv("amazon_ml/dataset/train/train_source1.tsv", separator="\t", skip_rows_after_header=100000, n_rows=1, infer_schema_length=0).to_dicts()[0]
    mapping = {field:field for field in ["entity_id", "business_name", "business_address", "country"]}
    record = {key:value or "" for key,value in record.items()}
    source = upload(client, [record])
    target = upload(client, [{**record,"entity_id":"actual-target-record"}])
    response = client.post("/api/workbench/analyze", headers=headers(), json={"task":"entities","dataset_id":source["id"],"candidate_dataset_id":target["id"],"mapping":mapping,"candidate_mapping":mapping})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mutations_performed"] is False
    match = result["output"][0]["result"]["prediction"]["matches"][0]
    assert match["target_entity_id"] == "actual-target-record"
    assert match["target_business_name"] == record["business_name"]
    assert result["datasets"][0]["sha256"] == source["sha256"]
    invalid = client.post("/api/workbench/analyze", headers=headers(), json={"task":"entities","dataset_id":source["id"],"candidate_dataset_id":target["id"]})
    assert invalid.status_code == 422


def test_schema_uses_imported_columns(client):
    dataset = upload(client, [{"billing_address":"Gwalior","contact_email":"testing@example.invalid"}])
    response = client.post("/api/workbench/analyze",headers=headers(),json={"task":"schema","dataset_id":dataset["id"]})
    assert response.status_code == 200
    fields = response.json()["output"]["prediction"]["mappings"]
    assert {row["source_field"] for row in fields} == {"billing_address","contact_email"}


def test_anomaly_requires_history_and_changes_with_data(client):
    history = upload(client, [{"paid":950 + (index % 17) * 8} for index in range(100)])
    current = upload(client, [{"sum":1000},{"sum":150000}])
    payload = {"task":"anomaly","dataset_id":current["id"],"candidate_dataset_id":history["id"],"mapping":{"amount":"sum"},"candidate_mapping":{"amount":"paid"},"options":{"currency":"INR"}}
    response = client.post("/api/workbench/analyze",headers=headers(),json=payload)
    assert response.status_code == 200, response.text
    output = response.json()["output"]
    assert output["training_rows"] == 100
    assert output["transactions"][1]["requires_review"] is True
    assert output["transactions"][1]["outlier_score"] > output["transactions"][0]["outlier_score"]
    small = upload(client,[{"paid":1}])
    payload["candidate_dataset_id"] = small["id"]
    assert client.post("/api/workbench/analyze",headers=headers(),json=payload).status_code == 422


def test_reads_actual_sqlite_table_and_blocks_path_escape(client,tmp_path,monkeypatch):
    monkeypatch.setenv("AVENTRA_DATA_ROOT", str(tmp_path))
    with sqlite3.connect(tmp_path / "company.sqlite") as db:
        db.execute("CREATE TABLE customers (id TEXT, legal_name TEXT)")
        db.execute("INSERT INTO customers VALUES (?, ?)",("unique-db-id","Actual table company"))
    payload = {"name":"company table","relative_path":"company.sqlite","table":"customers"}
    response = client.post("/api/workbench/database-import",headers=headers(),json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["row_count"] == 1
    assert response.json()["columns"] == ["id","legal_name"]
    assert client.post("/api/workbench/database-import",headers=headers("compliance"),json=payload).status_code == 403
    payload["relative_path"] = "../outside.sqlite"
    assert client.post("/api/workbench/database-import",headers=headers(),json=payload).status_code == 422


def test_legacy_agent_cannot_mutate_simulators(client):
    assert client.post("/api/agent/execute",json={"prompt":"Inspect audit ledger"}).status_code == 401
    assert client.post("/api/agent/execute",headers=headers(),json={"prompt":"Onboard arbitrary customer"}).status_code == 409


def test_approval_rejects_unauthenticated_calls(client):
    assert client.post("/api/approvals/unknown/decide",json={"decision":"APPROVED","comments":"test approval"}).status_code == 401


def test_financial_exceptions_are_not_tolerated(client):
    from ml.models.invoice_reconciliation.inference import InvoiceReconciliationModel
    invoice = {"invoice_number":"I-REAL","po_number":"P-REAL","vendor_id":"V-REAL","invoice_date":"2026-11-02","subtotal":2000,"total_amount":2000,"line_items":[{"sku":"A","quantity":20,"unit_price":100,"total":2000}]}
    po = {"po_number":"P-REAL","vendor_id":"V-REAL","total_amount":1000,"line_items":[{"sku":"A","quantity":10,"unit_price":100,"total":1000}]}
    receipt = {"receipt_id":"R-REAL","po_number":"P-REAL","received_items":{"A":10}}
    for payload in [{"invoice":invoice,"purchase_order":po,"goods_receipt":receipt},{"invoice":invoice},{"invoice":invoice,"purchase_order":po}]:
        output = InvoiceReconciliationModel().predict(payload)
        assert output.prediction["requires_human_approval"] is True


def test_genesis_payload_tampering_is_detected():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.database.models import Base
    from backend.security.audit import append_audit_entry, verify_ledger_chain
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        entry = append_audit_entry(db,"test","AUDITOR","TEST","CHECK","one",{"value":1})
        entry.details = {"value":2}
        db.commit()
        assert verify_ledger_chain(db)["is_valid"] is False
    engine.dispose()
