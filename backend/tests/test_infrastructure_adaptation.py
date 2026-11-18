import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.security.auth import create_access_token


def auth(name="admin"):
    return {"Authorization":"Bearer " + create_access_token({"sub":name})}


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv("AVENTRA_DATA_ROOT",str(tmp_path))
    path=tmp_path/"client.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE partners (local_key INTEGER PRIMARY KEY, trading_label TEXT)")
        db.execute("INSERT INTO partners VALUES (1, 'Client supplied name')")
        db.execute("CREATE TABLE payroll_private (secret TEXT)")
    return path


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def register(client):
    response=client.post("/api/adaptation/profiles",headers=auth(),json={"name":"Client chosen infrastructure","relative_path":"client.sqlite","allowed_tables":["partners"],"concepts":[{"name":"party_label","description":"Trading label of the business partner","compatible_types":["text","varchar"]},{"name":"party_number","description":"Partner key","compatible_types":["integer"]}]})
    assert response.status_code==200,response.text
    return response.json()["id"]


def discover(client,identifier):
    response=client.post(f"/api/adaptation/profiles/{identifier}/discover",headers=auth())
    assert response.status_code==200,response.text
    return response.json()


def approve(client,identifier,revision=1):
    return client.post(f"/api/adaptation/profiles/{identifier}/decide",headers=auth(),json={"revision":revision,"decision":"APPROVE","mappings":{"partners.trading_label":"party_label","partners.local_key":"party_number"},"comments":"Reviewed against the client schema"})


def test_discovery_approval_live_read_and_feedback(client,source):
    identifier=register(client)
    first=discover(client,identifier)
    assert set(first["observed"]["schema"])=={"partners"}
    assert first["status"]=="NEEDS_REVIEW"
    assert first["active"]=={}
    assert client.post(f"/api/adaptation/profiles/{identifier}/read",headers=auth(),json={"table":"partners"}).status_code==409
    assert approve(client,identifier).status_code==200
    assert approve(client,identifier).status_code==409
    result=client.post(f"/api/adaptation/profiles/{identifier}/read",headers=auth(),json={"table":"partners"}).json()
    assert result["records"]==[{"party_label":"Client supplied name","party_number":1}]
    with sqlite3.connect(source) as db:
        db.execute("UPDATE partners SET trading_label='Changed in client system' WHERE local_key=1")
    result=client.post(f"/api/adaptation/profiles/{identifier}/read",headers=auth(),json={"table":"partners"}).json()
    assert result["records"][0]["party_label"]=="Changed in client system"
    with sqlite3.connect(source) as db:
        db.execute("ALTER TABLE partners ADD COLUMN region TEXT")
    assert client.post(f"/api/adaptation/profiles/{identifier}/read",headers=auth(),json={"table":"partners"}).status_code==409
    second=discover(client,identifier)
    assert second["revision"]==2
    assert second["status"]=="NEEDS_REVIEW"
    memory={item["source"]:item for item in second["proposals"][-1]["suggestions"]}
    assert memory["partners.trading_label"]["basis"]=="APPROVED_FEEDBACK"
    assert memory["partners.trading_label"]["target"]=="party_label"
    assert approve(client,identifier,revision=1).status_code==409
    assert approve(client,identifier,revision=2).status_code==200
    assert client.post(f"/api/adaptation/profiles/{identifier}/read",headers=auth(),json={"table":"payroll_private"}).status_code==409


def test_schema_change_during_review_blocks_activation(client,source):
    identifier=register(client)
    discover(client,identifier)
    with sqlite3.connect(source) as db:
        db.execute("ALTER TABLE partners ADD COLUMN updated_at TEXT")
    assert approve(client,identifier).status_code==409


def test_permissions_and_type_constraints(client,source):
    identifier=register(client)
    discover(client,identifier)
    payload={"revision":1,"decision":"APPROVE","mappings":{"partners.local_key":"party_label"},"comments":"Wrong datatype test"}
    assert client.post(f"/api/adaptation/profiles/{identifier}/decide",headers=auth(),json=payload).status_code==422
    assert client.post(f"/api/adaptation/profiles/{identifier}/discover",headers=auth("compliance")).status_code==403
    assert client.post(f"/api/adaptation/profiles/{identifier}/read",headers=auth("compliance"),json={"table":"partners"}).status_code==404
    assert client.get("/api/adaptation/profiles").status_code==401
    assert client.get("/api/adaptation/profiles",headers=auth("compliance")).json()==[]


def test_rejection_never_activates_configuration(client,source):
    identifier=register(client)
    discover(client,identifier)
    response=client.post(f"/api/adaptation/profiles/{identifier}/decide",headers=auth(),json={"revision":1,"decision":"REJECT","comments":"Mapping evidence insufficient"})
    assert response.status_code==200
    assert response.json()["status"]=="REJECTED"
    assert response.json()["learned_mapping_count"]==0
    assert client.post(f"/api/adaptation/profiles/{identifier}/read",headers=auth(),json={"table":"partners"}).status_code==409
