"""Provider contract tests use a mocked Google transport, not a live Gemini call."""
import json

import pytest
import requests
from fastapi import HTTPException
from backend.agents import gemini_planner as planner


def output(**overrides):
    return {"action": "retrieve", "query": "Narmada", "source_id": "", "resource": "",
            "record_key": "", "changes": [], "explanation": "Search current records", **overrides}


def transport(monkeypatch, payload=None, status=200, finish="STOP"):
    captured = {}
    class Response:
        status_code = status
        def json(self):
            return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": json.dumps(payload or output())}]}}]}
    def post(self, url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(requests.Session, "post", post)
    return captured


def test_structured_plan_and_metadata_only_transport(monkeypatch):
    captured = transport(monkeypatch)
    result = planner.plan("Locate Narmada", [{"source_id": "s", "fields": {"client_label": "string"}}])
    assert result.query == "Narmada"
    payload = captured["json"]
    context = json.loads(payload["contents"][0]["parts"][0]["text"])
    assert set(context) == {"request", "approved_capabilities"}
    assert "rows" not in json.dumps(context)
    assert "test-only-not-a-real-key" not in json.dumps(payload)
    assert captured["allow_redirects"] is False
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["responseJsonSchema"]["additionalProperties"] is False


@pytest.mark.parametrize("payload,code,finish", [(output(action="execute_sql"),200,"STOP"), (output(extra="malicious"),200,"STOP"), (output(),200,"MAX_TOKENS"), (output(),429,"STOP"), (output(action="unsupported"),200,"STOP")])
def test_rejects_invalid_incomplete_and_provider_failures(monkeypatch,payload,code,finish):
    transport(monkeypatch,payload,code,finish)
    with pytest.raises(HTTPException) as error:
        planner.plan("request", [])
    assert error.value.status_code in (422,502)
    assert "test-only-not-a-real-key" not in str(error.value.detail)


def test_not_configured_and_model_path_rejected(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert planner.status()["configured"] is False
    with pytest.raises(HTTPException) as error:
        planner.plan("request", [])
    assert error.value.status_code == 503
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    monkeypatch.setenv("GEMINI_MODEL", "../arbitrary-endpoint")
    with pytest.raises(HTTPException):
        planner.plan("request", [])


def test_timeout_has_no_fallback(monkeypatch):
    transport(monkeypatch)
    def timeout(*args, **kwargs):
        raise requests.Timeout("sensitive-provider-detail")
    monkeypatch.setattr(requests.Session,"post",timeout)
    with pytest.raises(HTTPException) as error:
        planner.plan("request", [])
    assert "no fallback" in error.value.detail
    assert "sensitive-provider-detail" not in error.value.detail


def test_verification_tracks_transport_and_invalidates_when_credentials_change(monkeypatch):
    transport(monkeypatch)
    planner.plan("List records", [])
    verified=planner.status()
    assert verified["live_connection_verified"] is True
    assert verified["verification_status"]=="verified"
    assert verified["duration_ms"]>=0 and verified["checked_at"]
    assert "test-only-not-a-real-key" not in json.dumps(verified)
    monkeypatch.setenv("GEMINI_API_KEY","changed-test-key")
    assert planner.status()["live_connection_verified"] is False
    assert planner.status()["verification_status"]=="not_checked"


def test_rejected_credential_cannot_claim_a_verified_connection(monkeypatch):
    transport(monkeypatch,status=403)
    with pytest.raises(HTTPException) as error:
        planner.plan("List records", [])
    assert "permissions" in error.value.detail
    assert planner.status()["live_connection_verified"] is False
    assert planner.status()["verification_reason"]=="provider_http_403"


def test_transient_provider_error_is_retried_and_counted(monkeypatch):
    transport(monkeypatch)
    successful=requests.Session.post
    calls=[];delays=[]
    def temporary(self,*args,**kwargs):
        calls.append(1)
        if len(calls)<3:
            return type("TransientResponse",(),{"status_code":503,"headers":{}})()
        return successful(self,*args,**kwargs)
    monkeypatch.setattr(requests.Session,"post",temporary)
    monkeypatch.setattr(planner.time,"sleep",delays.append)
    result=planner.plan("List records",[])
    assert len(calls)==3 and delays==[.5,1.0]
    assert result._provider_metadata["attempts"]==3
    assert planner.status()["attempts"]==3


def test_authentication_errors_are_not_retried(monkeypatch):
    transport(monkeypatch,status=401)
    def no_sleep(delay):raise AssertionError("Authentication errors must not be retried")
    monkeypatch.setattr(planner.time,"sleep",no_sleep)
    with pytest.raises(HTTPException):planner.plan("List records",[])
    assert planner.status()["attempts"]==1
