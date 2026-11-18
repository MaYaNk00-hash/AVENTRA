"""Verify configuration-only bridge behavior against a real SQLite client database."""
import importlib
import sqlite3
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def bridge(tmp_path,monkeypatch):
    path=tmp_path/"client-owned.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE bespoke_parties (opaque_key TEXT PRIMARY KEY, firm_caption TEXT, status_flag TEXT, rating INTEGER)")
        db.execute("INSERT INTO bespoke_parties VALUES ('K-998','Client supplied company','pending',3)")
        db.execute("CREATE TABLE restricted_table (private_value TEXT)")
    monkeypatch.setenv("AVENTRA_BRIDGE_DATABASE_URL","sqlite:///"+path.as_posix())
    monkeypatch.setenv("AVENTRA_BRIDGE_TABLES","bespoke_parties")
    monkeypatch.setenv("AVENTRA_BRIDGE_TOKEN","test-only-bridge-credential")
    monkeypatch.setenv("AVENTRA_BRIDGE_WRITES",'{"bespoke_parties":["status_flag","rating"]}')
    module=importlib.import_module("infrastructure.bridge.app")
    module=importlib.reload(module)
    with TestClient(module.app) as client:
        yield client,path
    module.engine.dispose()


def auth():
    return {"Authorization":"Bearer test-only-bridge-credential"}


def test_bridge_discovers_actual_schema_without_changing_it(bridge):
    client,path=bridge
    assert client.get("/openapi.json").status_code in (401,403)
    spec=client.get("/openapi.json",headers=auth()).json()
    assert set(spec["paths"])=={"/data/bespoke_parties","/data/bespoke_parties/{record_key}"}
    fields=spec["paths"]["/data/bespoke_parties"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["properties"]
    assert set(fields)=={"opaque_key","firm_caption","status_flag","rating"}
    assert fields["rating"]["type"]=="integer"
    assert client.get("/data/restricted_table",headers=auth()).status_code==404
    with sqlite3.connect(path) as db:
        tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables=={"bespoke_parties","restricted_table"}


def test_bridge_writes_actual_data_with_atomic_preconditions(bridge):
    client,path=bridge
    before=client.get("/data/bespoke_parties/K-998",headers=auth())
    assert before.json()["status_flag"]=="pending"
    headers={**auth(),"If-Match":before.headers["ETag"]}
    response=client.patch("/data/bespoke_parties/K-998",headers=headers,json={"status_flag":"approved","rating":7})
    assert response.status_code==200,response.text
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status_flag,rating FROM bespoke_parties").fetchone()==("approved",7)
    assert client.patch("/data/bespoke_parties/K-998",headers=headers,json={"status_flag":"stale-overwrite"}).status_code==412


def test_bridge_rejects_ungranted_fields_and_wrong_types(bridge):
    client,_=bridge
    before=client.get("/data/bespoke_parties/K-998",headers=auth())
    headers={**auth(),"If-Match":before.headers["ETag"]}
    assert client.patch("/data/bespoke_parties/K-998",headers=headers,json={"firm_caption":"unauthorized"}).status_code==403
    assert client.patch("/data/bespoke_parties/K-998",headers=headers,json={"rating":"seven"}).status_code==422
