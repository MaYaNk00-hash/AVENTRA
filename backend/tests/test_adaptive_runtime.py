"""Real HTTP + SQLite integration tests. No mocked client responses or model scores."""
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

import pytest
import requests
from fastapi.testclient import TestClient
from backend.main import app
from backend.security.auth import create_access_token


def auth(name="admin"):
    return {"Authorization":"Bearer "+create_access_token({"sub":name})}


@pytest.fixture(scope="module")
def live_client(tmp_path_factory):
    root=tmp_path_factory.mktemp("live-client")
    path=root/"existing-client.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE crm_live (customer_guid TEXT PRIMARY KEY, display_text TEXT, postal_site TEXT, nation TEXT, workflow_flag TEXT)")
        db.execute("CREATE TABLE erp_weird (vendor_pk TEXT PRIMARY KEY, trading_label TEXT, office_site TEXT, country_code TEXT, lifecycle TEXT)")
        db.execute("CREATE TABLE operational_jobs (job_ref TEXT PRIMARY KEY, booked_value REAL)")
        db.execute("INSERT INTO crm_live VALUES (?,?,?,?,?)",("RANDOM-CUSTOMER-41","Narmada Precision Tools Private Limited","12 Industrial Estate Gwalior","IN","new"))
        db.execute("INSERT INTO erp_weird VALUES (?,?,?,?,?)",("DIFFERENT-SUPPLIER-92","Narmada Precision Tools Pvt Ltd","12 Industrial Estate Gwalior","IN","active"))
        db.execute("INSERT INTO operational_jobs VALUES (?,?)",("JOB-ONLY-009",3872.50))
    with socket.socket() as socket_handle:
        socket_handle.bind(("127.0.0.1",0))
        port=socket_handle.getsockname()[1]
    url=f"http://127.0.0.1:{port}"
    env={**os.environ,"CLIENT_DB":str(path),"CLIENT_TABLES":"crm_live,erp_weird"}
    process=subprocess.Popen([sys.executable,"-m","uvicorn","prototype_client.app:app","--host","127.0.0.1","--port",str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    previous={key:os.environ.get(key) for key in ["AVENTRA_ALLOWED_ORIGINS","AVENTRA_DATA_ROOT"]}
    os.environ["AVENTRA_ALLOWED_ORIGINS"]=url
    os.environ["AVENTRA_DATA_ROOT"]=str(root)
    try:
        for _ in range(100):
            try:
                if requests.get(url+"/openapi.json",timeout=.5).ok:
                    break
            except requests.RequestException:
                time.sleep(.1)
        else:
            pytest.fail("Independent client HTTP service did not start")
        with TestClient(app) as client:
            yield client,url,path
    finally:
        process.terminate()
        process.wait(timeout=10)
        for key,value in previous.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


def source(client,url,domain,resource,key,bindings,writable=None):
    response=client.post("/api/runtime/sources",headers=auth(),json={"name":"Client "+domain,"domain":domain,"kind":"openapi","base_url":url})
    assert response.status_code==200,response.text
    discovered=response.json()
    assert resource in discovered["resources"]
    response=client.post(f"/api/runtime/sources/{discovered['id']}/approve",headers=auth(),json={"schema_sha256":discovered["schema_sha256"],"resources":{resource:{"key_field":key,"bindings":bindings,"writable_fields":writable or []}}})
    assert response.status_code==200,response.text
    return response.json()["id"]


@pytest.fixture(scope="module")
def connected(live_client):
    client,url,path=live_client
    crm=source(client,url,"CRM","/api/crm_live","customer_guid",{"name":"display_text","address":"postal_site","country":"nation"},["workflow_flag"])
    erp=source(client,url,"ERP","/api/erp_weird","vendor_pk",{"name":"trading_label","address":"office_site","country":"country_code"})
    response=client.post("/api/runtime/sources",headers=auth(),json={"name":"Existing client operations DB","domain":"DATABASE","kind":"sqlite","relative_path":path.name,"allowed_tables":["operational_jobs"]})
    assert response.status_code==200,response.text
    dbsource=response.json()
    response=client.post(f"/api/runtime/sources/{dbsource['id']}/approve",headers=auth(),json={"schema_sha256":dbsource["schema_sha256"],"resources":{"operational_jobs":{"key_field":"job_ref","bindings":{},"writable_fields":[]}}})
    assert response.status_code==200,response.text
    return crm,erp,dbsource["id"]


def start(client,ids,goal="Show all records",**extra):
    response=client.post("/api/runtime/runs",headers=auth(),json={"goal":goal,"source_ids":ids,"planner":"local",**extra})
    assert response.status_code==200,response.text
    return response.json()


def test_retrieves_real_http_and_db_records(live_client,connected):
    client,url,path=live_client
    result=start(client,list(connected))
    assert result["status"]=="COMPLETED",result
    assert {item["domain"] for item in result["evidence"]["resources"]}=={"CRM","ERP","DATABASE"}
    jobs=next(item for item in result["evidence"]["resources"] if item["domain"]=="DATABASE")
    assert jobs["rows"]==[{"job_ref":"JOB-ONLY-009","booked_value":3872.5}]
    assert len([event for event in result["events"] if event["tool"]=="client.read"])==3
    assert client.get(f"/api/runtime/runs/{result['id']}",headers=auth()).json()["evidence"]==result["evidence"]


def test_random_sample_is_bounded_and_grounded(live_client,connected):
    client,_,_=live_client
    result=start(client,list(connected),"retriev random 10 clients data")
    assert result["status"]=="COMPLETED",result
    output=result["result"]
    assert output["requested_limit"]==10
    assert output["returned_count"]==3  # Three real fixture rows; never invent ten.
    assert output["selection"]=="random sample of retrieved matches"
    assert output["execution"]["duration_ms"]>0
    assert output["execution"]["score"] is None
    assert len({row["record_key"] for row in output["records"]})==3


def test_workspace_overview_and_live_connection_health(live_client,connected):
    client,_,_=live_client
    overview=client.get("/api/runtime/overview",headers=auth())
    assert overview.status_code==200
    data=overview.json()
    assert data["sources"]["approved"]>=3
    assert data["sources"]["resources"]>=3
    assert data["runs"]["total"]>=data["runs"]["completed"]
    assert "key" not in data["planner"]
    health=client.get(f"/api/runtime/sources/{connected[0]}/health",headers=auth()).json()
    assert health["status"]=="reachable"
    assert health["duration_ms"]>0 and health["checked_at"]
    assert client.get(f"/api/runtime/sources/{connected[0]}/health").status_code==401
    assert client.get("/api/runtime/sources/not-owned/health",headers=auth()).status_code==404


def test_gemini_selects_actual_local_artifact_without_sending_input_values(live_client,monkeypatch):
    from backend.agents import gemini_planner
    from backend.tests.test_hybrid_intelligence import CASES
    client,_,_=live_client
    def route(goal,capabilities):
        context=str(capabilities)
        assert "amount" in context and "19000" not in context and "HYBRID-T1" not in context
        return gemini_planner.ToolPlan(action="analyze",query="",source_id="",resource="",record_key="",changes=[],explanation="Use the local transaction artifact",analysis_model="anomaly_detection")
    monkeypatch.setattr(gemini_planner,"plan",route)
    response=client.post("/api/runtime/runs",headers=auth(),json={"goal":"Analyze this transaction for outliers","source_ids":[],"analysis":CASES["anomaly_detection"],"planner":"gemini"})
    assert response.status_code==200,response.text
    run=response.json()
    assert run["status"]=="COMPLETED",run
    assert run["result"]["type"]=="ml_analysis"
    analysis=run["result"]["analysis"]
    assert analysis["model"]=="anomaly_detection" and len(analysis["artifact_sha256"])==64
    assert analysis["output"]["score"] is None
    assert run["evidence"]["model_input"]==CASES["anomaly_detection"]
    assert any(event["tool"]=="planner.gemini.validated" for event in run["events"])
    assert any(event["tool"]=="model.anomaly_detection" for event in run["events"])
    assert not any(event["tool"]=="client.read" for event in run["events"])
    assert client.get("/api/runtime/intelligence/models").status_code==401


def test_approval_queue_includes_pending_older_than_recent_history(live_client):
    from backend.api.runtime import AgentRun
    from backend.database.session import SessionLocal
    from backend.database.models import User
    import uuid
    client,_,_=live_client
    identifiers=[]
    with SessionLocal() as db:
        owner=db.query(User).filter_by(username="admin").one()
        for index in range(33):
            identifier=str(uuid.uuid4());identifiers.append(identifier)
            db.add(AgentRun(id=identifier,owner_id=owner.id,goal="Queue pagination regression",status="AWAITING_APPROVAL" if index==0 else "COMPLETED",events=[{"timestamp":f"2020-01-{index//24+1:02d}T{index%24:02d}:00:00Z"}],evidence={},proposal={},result={}))
        foreign_id=str(uuid.uuid4());identifiers.append(foreign_id)
        db.add(AgentRun(id=foreign_id,owner_id="another-owner",goal="Private proposal",status="AWAITING_APPROVAL",events=[],evidence={},proposal={},result={}))
        db.commit()
        try:
            recent=client.get("/api/runtime/runs",headers=auth()).json()
            pending=client.get("/api/runtime/runs?status=AWAITING_APPROVAL",headers=auth()).json()
            assert len(recent)==30
            assert identifiers[0] not in {run["id"] for run in recent}
            assert identifiers[0] in {run["id"] for run in pending}
            assert foreign_id not in {run["id"] for run in pending}
            assert all(run["status"]=="AWAITING_APPROVAL" for run in pending)
        finally:
            db.query(AgentRun).filter(AgentRun.id.in_(identifiers)).delete(synchronize_session=False)
            db.commit()


def test_gemini_plan_executes_actual_retrieval_with_no_rows_in_context(live_client,connected,monkeypatch):
    from backend.agents import gemini_planner
    captured = []
    def planned(goal, capabilities):
        captured.extend(capabilities)
        return gemini_planner.ToolPlan(action="retrieve", query="Narmada", source_id="", resource="", record_key="", changes=[], explanation="Search current business records")
    monkeypatch.setattr(gemini_planner,"plan",planned)
    client,_,_=live_client
    # Omit planner to verify that the public API defaults to Gemini.
    response=client.post("/api/runtime/runs",headers=auth(),json={"goal":"Can you locate the Narmada business for me?","source_ids":list(connected)})
    assert response.status_code==200,response.text
    result=response.json()
    assert result["status"]=="COMPLETED",result
    assert result["result"]["search"]=="Narmada"
    assert any(hit["record_key"]=="RANDOM-CUSTOMER-41" for hit in result["result"]["records"])
    assert all("rows" not in item and "credential_env" not in item for item in captured)
    assert any(event["tool"]=="planner.gemini.validated" for event in result["events"])


def test_gemini_updates_remain_reviewed_and_scope_checked(live_client,connected,monkeypatch):
    from backend.agents import gemini_planner
    client,url,_=live_client
    plan=gemini_planner.ToolPlan(action="update",query="",source_id=connected[0],resource="/api/crm_live",record_key="RANDOM-CUSTOMER-41",changes=[{"field":"workflow_flag","value_json":'"gemini-proposal"'}],explanation="Prepare the requested change")
    monkeypatch.setattr(gemini_planner,"plan",lambda *args: plan)
    before=requests.get(url+"/api/crm_live/RANDOM-CUSTOMER-41").json()
    run=start(client,list(connected),'Please change RANDOM-CUSTOMER-41 workflow_flag to gemini-proposal',planner="gemini")
    assert run["status"]=="AWAITING_APPROVAL",run
    assert run["proposal"]["changes"]=={"workflow_flag":"gemini-proposal"}
    assert requests.get(url+"/api/crm_live/RANDOM-CUSTOMER-41").json()==before
    plan.changes=[gemini_planner.Change(field="display_text",value_json='"unapproved"')]
    blocked=start(client,list(connected),'Change RANDOM-CUSTOMER-41 display_text',planner="gemini")
    assert blocked["status"]=="FAILED" and blocked["result"]["http_status"]==403
    plan.changes=[gemini_planner.Change(field="workflow_flag",value_json='"reviewed"')]
    missing_key=start(client,list(connected),'Change the customer status',planner="gemini")
    assert missing_key["status"]=="FAILED" and missing_key["result"]["http_status"]==422


def test_gemini_unconfigured_does_not_claim_completion(live_client,connected,monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY",raising=False)
    client,_,_=live_client
    assert client.get("/api/runtime/planner").status_code==401
    config=client.get("/api/runtime/planner",headers=auth()).json()
    assert config["configured"] is False and "key" not in config
    run=start(client,list(connected),"Show all records",planner="gemini")
    assert run["status"]=="FAILED" and run["result"]["http_status"]==503
    assert not any(event["tool"]=="client.read" for event in run["events"])


def test_actual_model_compares_different_client_schemas(live_client,connected):
    client,_,_=live_client
    result=start(client,list(connected),"Find duplicate businesses across these systems")
    assert result["status"]=="COMPLETED",result
    assert result["result"]["type"]=="entity_comparison"
    matches=result["result"]["matches"]
    assert any(row["record_key"]=="RANDOM-CUSTOMER-41" and row["target_entity_id"]=="DIFFERENT-SUPPLIER-92" and row["match_probability"]>=.4 for row in matches)


def test_agent_summary_computes_actual_values(live_client,connected):
    client,_,_=live_client
    result=start(client,list(connected),"Summarize the connected systems")
    assert result["status"]=="COMPLETED"
    job=next(item for item in result["result"]["resources"] if item["resource"]=="operational_jobs")
    assert job["numeric_fields"]["booked_value"]["sum"]==3872.5


def proposal(client,connected,value="reviewed"):
    return start(client,list(connected),"Update the selected customer review field",mutation={"source_id":connected[0],"resource":"/api/crm_live","record_key":"RANDOM-CUSTOMER-41","changes":{"workflow_flag":value}})


def test_agent_grounds_a_typed_update_request_from_live_schema(live_client,connected):
    client,url,_=live_client
    run=start(client,list(connected),'Set workflow_flag = "requested-in-chat" for RANDOM-CUSTOMER-41')
    assert run["status"]=="AWAITING_APPROVAL",run
    assert run["proposal"]["source_id"]==connected[0]
    assert run["proposal"]["changes"]=={"workflow_flag":"requested-in-chat"}
    assert run["proposal"]["record_key"]=="RANDOM-CUSTOMER-41"
    assert requests.get(url+"/api/crm_live/RANDOM-CUSTOMER-41").json()["workflow_flag"]=="new"
    ambiguous=start(client,list(connected),'Set workflow_flag = "reviewed"')
    assert ambiguous["status"]=="FAILED"
    assert ambiguous["result"]["http_status"]==422


def test_approved_patch_is_real_verified_and_not_replayed(live_client,connected):
    client,url,_=live_client
    run=proposal(client,connected)
    assert run["status"]=="AWAITING_APPROVAL",run
    assert requests.get(url+"/api/crm_live/RANDOM-CUSTOMER-41").json()["workflow_flag"]=="new"
    decision={"decision":"APPROVE","comments":"Reviewed exact field change against live evidence"}
    assert client.post(f"/api/runtime/runs/{run['id']}/decide",json=decision).status_code==401
    response=client.post(f"/api/runtime/runs/{run['id']}/decide",headers=auth(),json=decision)
    assert response.status_code==200,response.text
    result=response.json()
    assert result["status"]=="COMPLETED",result
    assert result["result"]["verified"] is True
    assert requests.get(url+"/api/crm_live/RANDOM-CUSTOMER-41").json()["workflow_flag"]=="reviewed"
    assert client.post(f"/api/runtime/runs/{run['id']}/decide",headers=auth(),json=decision).status_code==409


def test_reject_and_write_scope_do_not_change_client(live_client,connected):
    client,url,_=live_client
    run=proposal(client,connected,"rejected-value")
    result=client.post(f"/api/runtime/runs/{run['id']}/decide",headers=auth(),json={"decision":"REJECT","comments":"No change authorized"}).json()
    assert result["status"]=="REJECTED"
    assert requests.get(url+"/api/crm_live/RANDOM-CUSTOMER-41").json()["workflow_flag"]=="reviewed"
    invalid=start(client,list(connected),"Change a forbidden field",mutation={"source_id":connected[0],"resource":"/api/crm_live","record_key":"RANDOM-CUSTOMER-41","changes":{"display_text":"Forbidden rename"}})
    assert invalid["status"]=="FAILED"
    assert invalid["result"]["http_status"]==403


def test_stale_preview_blocks_write_and_rereads_are_live(live_client,connected):
    client,url,_=live_client
    run=proposal(client,connected,"agent-value")
    endpoint=url+"/api/crm_live/RANDOM-CUSTOMER-41"
    before=requests.get(endpoint)
    assert requests.patch(endpoint,json={"workflow_flag":"changed-by-client"},headers={"If-Match":before.headers["ETag"]}).ok
    result=client.post(f"/api/runtime/runs/{run['id']}/decide",headers=auth(),json={"decision":"APPROVE","comments":"Stale review test"}).json()
    assert result["status"]=="FAILED",result
    assert requests.get(endpoint).json()["workflow_flag"]=="changed-by-client"
    fresh=start(client,list(connected))
    rows=next(item for item in fresh["evidence"]["resources"] if item["domain"]=="CRM")["rows"]
    assert rows[0]["workflow_flag"]=="changed-by-client"


def test_scope_auth_and_unsupported_actions(live_client,connected):
    client,url,_=live_client
    assert client.get("/api/runtime/sources").status_code==401
    assert client.get("/api/runtime/sources",headers=auth("compliance")).json()==[]
    assert client.post("/api/runtime/sources",headers=auth(),json={"name":"Unapproved origin","domain":"CRM","kind":"openapi","base_url":"http://169.254.169.254"}).status_code==422
    result=start(client,list(connected),"Delete all customer records")
    assert result["status"]=="FAILED"
    assert result["result"]["http_status"]==422


def test_explicit_operations_and_local_inference_work_without_gemini(live_client,connected,monkeypatch):
    from backend.agents import gemini_planner
    from backend.tests.test_hybrid_intelligence import CASES
    client,_,_=live_client
    monkeypatch.delenv("GEMINI_API_KEY",raising=False)
    def forbidden(*args,**kwargs):raise AssertionError("Explicit backend tools must not call Gemini")
    monkeypatch.setattr(gemini_planner,"plan",forbidden)
    for operation,ids in [("browse",list(connected)),("summary",list(connected)),("compare",list(connected[:2]))]:
        response=client.post("/api/runtime/runs",headers=auth(),json={"goal":"User selected a structured operation","source_ids":ids,"operation":operation,"search":"Narmada","limit":1})
        assert response.status_code==200,response.text
        run=response.json();assert run["status"]=="COMPLETED",run
        assert run["result"]["execution"]["planner"]=="backend tools"
        assert run["result"]["execution"]["provider"] is None
        assert not any(event["tool"].startswith("planner.gemini") for event in run["events"])
        if operation=="browse":assert run["result"]["returned_count"]==1
    compact=client.get("/api/runtime/runs?compact=true",headers=auth()).json()
    assert compact and all(row["evidence"]=={} and row["proposal"]=={} for row in compact)
    fresh=client.get(f"/api/runtime/runs/{run['id']}",headers=auth()).json()
    assert fresh["evidence"]["resources"]
    direct=client.post("/api/runtime/intelligence/predict",headers=auth(),json={"model":"anomaly_detection","analysis":CASES["anomaly_detection"]}).json()
    assert direct["status"]=="COMPLETED",direct
    assert direct["result"]["execution"]["provider"] is None
    assert direct["result"]["analysis"]["output"]["score"] is None


def test_comparison_batches_more_than_100_actual_candidates(live_client,connected):
    client,_,path=live_client
    identifiers=[f"BATCH-CANDIDATE-{i}" for i in range(120)]
    with sqlite3.connect(path) as db:
        db.executemany("INSERT INTO erp_weird VALUES (?,?,?,?,?)",[(key,"Synthetic Unrelated Parts "+key,"Fictional site","IN","active") for key in identifiers])
    try:
        result=client.post("/api/runtime/runs",headers=auth(),json={"goal":"Compare selected businesses","source_ids":list(connected[:2]),"operation":"compare"}).json()
        assert result["status"]=="COMPLETED",result
        assert result["result"]["candidate_generation"]["scored_pairs"]==121
        assert result["result"]["candidate_generation"]["lexical_shortlisting_used"] is False
    finally:
        with sqlite3.connect(path) as db:db.executemany("DELETE FROM erp_weird WHERE vendor_pk=?",[(key,) for key in identifiers])


def test_schema_drift_blocks_existing_grants(live_client,connected):
    client,_,path=live_client
    with sqlite3.connect(path) as db:
        db.execute("ALTER TABLE crm_live ADD COLUMN client_new_column TEXT")
    result=start(client,list(connected))
    assert result["status"]=="FAILED"
    assert "schema" in result["result"]["error"]
    discovery=client.post(f"/api/runtime/sources/{connected[0]}/rediscover",headers=auth()).json()
    assert discovery["status"]=="NEEDS_REVIEW"
    assert "client_new_column" in discovery["resources"]["/api/crm_live"]["fields"]
