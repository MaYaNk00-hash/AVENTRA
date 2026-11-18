"""Grounded tool runtime: discovered client resources, persisted runs, reviewed writes."""
import datetime as dt
import hashlib
import json
import os
import re
import random
import time
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, quote

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, JSON, create_engine, inspect, MetaData, Table, select, update, and_, func
from sqlalchemy.orm import Session, load_only
from rapidfuzz import fuzz, process

from backend.database.models import Base, User
from backend.database.session import get_db
from backend.security.auth import get_current_user
from backend.security.audit import append_audit_entry
from backend.api.adaptation import connect as sqlite_connect
from ml.shared.model_registry.registry import ModelRegistry
from ml.models.semantic_schema_mapper.inference import SemanticSchemaMapperModel
from backend.agents import gemini_planner
from backend.agents import local_intelligence

router = APIRouter(prefix="/api/runtime", tags=["Adaptive agent runtime"])


class ClientSource(Base):
    __tablename__ = "agent_client_sources"
    id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    domain = Column(String, nullable=False)
    config = Column(JSON, nullable=False)
    discovered = Column(JSON, nullable=False)
    approved = Column(JSON, nullable=False, default=dict)
    status = Column(String, nullable=False, default="NEEDS_REVIEW")


class AgentRun(Base):
    __tablename__ = "adaptive_agent_runs"
    id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    goal = Column(String, nullable=False)
    status = Column(String, nullable=False)
    events = Column(JSON, nullable=False, default=list)
    evidence = Column(JSON, nullable=False, default=dict)
    proposal = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=False, default=dict)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def require_admin(user):
    if user.role != "ADMIN":
        raise HTTPException(403, "Client connection configuration requires an administrator")


def owned(db, model, identifier, user):
    row = db.query(model).filter_by(id=identifier, owner_id=user.id).first()
    if row is None:
        raise HTTPException(404, "Owned resource not found")
    return row


def allowed_url(base, path):
    parsed = urlsplit(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    allowed = {item.strip().rstrip("/") for item in os.getenv("AVENTRA_ALLOWED_ORIGINS", "http://127.0.0.1:8100").split(",")}
    if origin not in allowed or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(422, "Client origin must be explicitly allowed in AVENTRA_ALLOWED_ORIGINS")
    if not path.startswith("/") or path.startswith("//") or ".." in path or "?" in path or "#" in path:
        raise HTTPException(422, "Only scoped relative API paths are supported")
    return base.rstrip("/") + path


def dispatch_local_prototype_client(method: str, path: str, body=None, extra_headers=None, metadata=False):
    """
    Direct in-process fallback for prototype client sandbox when port 8100 is not externally listening.
    Interacts with the same judging-client.sqlite database without network dependency.
    """
    import prototype_client.app as pc
    pc.seed()
    clean_path = path.split("?")[0].rstrip("/")
    if clean_path in ("/openapi.json", ""):
        val = pc.spec()
        return {"body": val, "etag": None} if metadata else val

    parts = [p for p in clean_path.split("/") if p]
    if len(parts) == 2 and parts[0] == "api":
        table = parts[1]
        val = pc.list_rows(table)
        return {"body": val, "etag": None} if metadata else val
    elif len(parts) == 3 and parts[0] == "api":
        table = parts[1]
        record_key = parts[2]
        if method.upper() == "GET":
            primary = pc.key_field(table)
            with pc.database() as db:
                row = db.execute(f"SELECT * FROM {pc.quote(table)} WHERE {pc.quote(primary)}=?", (record_key,)).fetchone()
            if not row:
                raise HTTPException(404, "Record not found")
            rec = dict(row)
            etag = f'"{pc.digest(rec)}"'
            return {"body": rec, "etag": etag} if metadata else rec
        elif method.upper() == "PATCH":
            fields = {col["name"] for col in pc.columns(table)}
            primary = pc.key_field(table)
            changes = body or {}
            if not isinstance(changes, dict) or not changes or set(changes) - fields or primary in changes:
                raise HTTPException(422, "Only known non-key fields may be updated")
            if any(value is not None and not isinstance(value, (str, int, float, bool)) for value in changes.values()):
                raise HTTPException(422, "Flat scalar field values required")
            body_hash = pc.digest({"table": table, "record_key": record_key, "changes": changes})
            with pc.database() as db:
                db.execute("BEGIN IMMEDIATE")
                request_key = (extra_headers or {}).get("Idempotency-Key")
                if request_key:
                    existing = db.execute("SELECT * FROM aventra.agent_idempotency WHERE request_key=?", (request_key,)).fetchone()
                    if existing:
                        if existing["payload_hash"] != body_hash:
                            raise HTTPException(409, "Idempotency key was already used for another mutation")
                        return json.loads(existing["response"])
                before = db.execute(f"SELECT * FROM {pc.quote(table)} WHERE {pc.quote(primary)}=?", (record_key,)).fetchone()
                if not before:
                    raise HTTPException(404, "Record not found")
                if_match = (extra_headers or {}).get("If-Match")
                if if_match and if_match != f'"{pc.digest(dict(before))}"':
                    raise HTTPException(412, "Record changed since the preview; refresh it")
                assignments = ','.join(pc.quote(key) + '=?' for key in changes)
                db.execute(f"UPDATE {pc.quote(table)} SET {assignments} WHERE {pc.quote(primary)}=?", (*changes.values(), record_key))
                after = dict(db.execute(f"SELECT * FROM {pc.quote(table)} WHERE {pc.quote(primary)}=?", (record_key,)).fetchone())
                if request_key:
                    db.execute("INSERT INTO aventra.agent_idempotency VALUES (?,?,?)", (request_key, body_hash, json.dumps(after)))
            etag = f'"{pc.digest(after)}"'
            return {"body": after, "etag": etag} if metadata else after

    raise HTTPException(404, f"Unsupported prototype client path: {path}")



def http(config, method, path, body=None, extra_headers=None, metadata=False):
    headers = {"Accept": "application/json", **(extra_headers or {})}
    reference = config.get("credential_env", "")
    if reference:
        if not reference.startswith("AVENTRA_CONNECTOR_"):
            raise HTTPException(422, "Connector secrets must use an AVENTRA_CONNECTOR_ environment reference")
        secret = os.getenv(reference)
        if not secret:
            raise HTTPException(422, "Referenced connector credential is not configured")
        headers["Authorization"] = "Bearer " + secret
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.request(method, allowed_url(config["base_url"], path), json=body, headers=headers, timeout=(5, 20), allow_redirects=False, stream=True) as response:
                if response.status_code >= 300:
                    raise HTTPException(502, f"Client returned HTTP {response.status_code}; no result assumed")
                payload = b""
                for chunk in response.iter_content(65536):
                    payload += chunk
                    if len(payload) > 2_000_000:
                        raise HTTPException(422, "Client response exceeds the 2 MB prototype limit")
                value = json.loads(payload) if payload else {}
                return {"body": value, "etag": response.headers.get("ETag")} if metadata else value
    except (requests.ConnectionError, requests.Timeout) as error:
        base_url = config.get("base_url", "")
        if "8100" in base_url or "localhost:8100" in base_url or "127.0.0.1:8100" in base_url:
            try:
                return dispatch_local_prototype_client(method, path, body, extra_headers, metadata)
            except HTTPException:
                raise
            except Exception:
                pass
        if isinstance(error, requests.Timeout):
            raise HTTPException(504, "Client service timed out; no result assumed") from error
        raise HTTPException(502, f"Client service is unreachable at {config['base_url']}. Start that service and retry; no data was retrieved.") from error
    except (requests.RequestException, ValueError) as error:
        raise HTTPException(502, "Client request failed or returned invalid JSON; check the connected API") from error


def resolve(spec, schema):
    for _ in range(12):
        if "$ref" not in schema:
            return schema
        reference = schema["$ref"]
        if not reference.startswith("#/"):
            raise HTTPException(422, "External schema references are unsupported")
        value = spec
        for part in reference[2:].split("/"):
            value = value[part.replace("~1", "/").replace("~0", "~")]
        schema = value
    raise HTTPException(422, "Recursive schema reference cannot be resolved")


def openapi_catalog(config):
    spec = http(config, "GET", config["spec_path"])
    if not str(spec.get("openapi", "")).startswith("3."):
        raise HTTPException(422, "An OpenAPI 3 document is required")
    resources = {}
    for path, operations in sorted(spec.get("paths", {}).items()):
        if "{" in path or "get" not in operations:
            continue
        response = operations["get"].get("responses", {}).get("200", {})
        schema = resolve(spec, response.get("content", {}).get("application/json", {}).get("schema", {}))
        list_field = ""
        if schema.get("type") == "object":
            arrays = [(key, resolve(spec, value)) for key, value in schema.get("properties", {}).items() if resolve(spec, value).get("type") == "array"]
            if len(arrays) != 1:
                continue
            list_field, schema = arrays[0]
        if schema.get("type") != "array":
            continue
        row = resolve(spec, schema.get("items", {}))
        fields = {key: {"type": value.get("type", "string"), "description": value.get("description", "")} for key, value in row.get("properties", {}).items()}
        if not fields:
            continue
        resource = {"name": operations["get"].get("summary") or path, "read_path": path, "list_field": list_field, "fields": fields, "writable": {}, "update_path": None}
        for item_path, item_ops in spec["paths"].items():
            if re.fullmatch(re.escape(path.rstrip("/")) + r"/\{[^/{}]+\}", item_path) and "patch" in item_ops:
                body = resolve(spec, item_ops["patch"].get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}))
                parameters = item_ops["patch"].get("parameters", []) + item_ops.get("parameters", [])
                precondition = "etag" if "get" in item_ops and any(parameter.get("in") == "header" and parameter.get("name", "").lower() == "if-match" for parameter in parameters) else "sha256" if item_ops["patch"].get("x-aventra-precondition") == "sha256" else None
                resource.update(update_path=item_path, write_precondition=precondition, writable={key: value for key, value in body.get("properties", {}).items() if key in fields and not value.get("readOnly")})
                break
        resources[path] = resource
    if not resources:
        raise HTTPException(422, "No supported flat JSON collection GET operations were discovered")
    return resources


def sqlite_catalog(config):
    source = sqlite_connect(config)
    try:
        with source.connect() as connection:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            resources = {}
            for name in config["allowed_tables"]:
                if name not in tables:
                    raise HTTPException(409, "A scoped client table no longer exists")
                columns = inspector.get_columns(name)
                keys = inspector.get_pk_constraint(name).get("constrained_columns", [])
                fields = {column["name"]: {"type": "number" if any(token in str(column["type"]).lower() for token in ["int", "float", "real", "numeric", "decimal"]) else "string", "description": str(column["type"])} for column in columns}
                resources[name] = {"name": name, "fields": fields, "key_hint": keys[0] if len(keys) == 1 else "", "writable": {key: value for key, value in fields.items() if key not in keys}}
            return resources
    finally:
        source.dispose()


def catalog(source):
    return openapi_catalog(source.config) if source.kind == "openapi" else sqlite_catalog(source.config)


def describe_source(source):
    model = SemanticSchemaMapperModel()
    model.canonical_concepts = [
        {"concept": "name", "description": "Business organization company registered legal trading display title label name", "compatible_types": ["string", "text", "varchar"]},
        {"concept": "address", "description": "Business office postal mailing street location site address", "compatible_types": ["string", "text", "varchar"]},
        {"concept": "country", "description": "Country nation territory code", "compatible_types": ["string", "text", "varchar"]},
        {"concept": "record_key", "description": "Unique record identifier customer account vendor supplier reference number key ID GUID", "compatible_types": ["string", "text", "varchar", "number", "integer"]},
    ]
    model.load()
    suggestions = {}
    for name, resource in source.discovered.items():
        remembered = source.approved.get("resources", {}).get(name)
        if remembered:
            suggestions[name] = remembered
            continue
        mapped = model.predict({"fields": [{"field_name": field, "datatype": metadata["type"], "description": metadata.get("description", "")} for field, metadata in resource["fields"].items()]}).prediction["mappings"]
        grant = {"key_field": resource.get("key_hint", ""), "bindings": {}, "writable_fields": []}
        best = {}
        for field in mapped:
            target = field["target_canonical_concept"]
            if target and field["match_confidence"] > best.get(target, 0):
                best[target] = field["match_confidence"]
                if target == "record_key" and not resource.get("key_hint"):
                    grant["key_field"] = field["source_field"]
                elif target != "record_key":
                    grant["bindings"][target] = field["source_field"]
        suggestions[name] = grant
    return {"id": source.id, "name": source.name, "kind": source.kind, "domain": source.domain, "status": source.status, "schema_sha256": digest(source.discovered), "resources": source.discovered, "suggestions": suggestions, "approved": source.approved, "provenance": source.config.get("provenance"), "connection": {key: value for key, value in source.config.items() if key != "credential_env"}}


class ConnectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    domain: Literal["CRM", "ERP", "DATABASE"]
    kind: Literal["openapi", "sqlite"]
    base_url: str = ""
    spec_path: str = "/openapi.json"
    credential_env: str = ""
    relative_path: str = ""
    allowed_tables: list[str] = Field(default_factory=list, max_length=30)
    provenance: dict = Field(default_factory=dict)


@router.post("/sources")
def connect_source(req: ConnectRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_admin(user)
    if req.kind == "sqlite" and not req.allowed_tables:
        raise HTTPException(422, "Select the client tables that may be inspected")
    config = req.model_dump(exclude={"name", "domain", "kind"})
    source = ClientSource(id=str(uuid.uuid4()), owner_id=user.id, name=req.name, kind=req.kind, domain=req.domain, config=config, approved={}, status="NEEDS_REVIEW")
    source.discovered = catalog(source)
    db.add(source)
    db.commit()
    append_audit_entry(db, user.id, user.role, "CLIENT_SOURCE_DISCOVERED", "SOURCE", source.id, {"kind": req.kind, "schema_sha256": digest(source.discovered)})
    return describe_source(source)


@router.get("/sources")
def sources(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [describe_source(source) for source in db.query(ClientSource).filter_by(owner_id=user.id).all()]


@router.get("/overview")
def workspace_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    counts = dict(db.query(AgentRun.status, func.count(AgentRun.id)).filter_by(owner_id=user.id).group_by(AgentRun.status).all())
    owned_sources = db.query(ClientSource).filter_by(owner_id=user.id).all()
    return {
        "runs": {"total": sum(counts.values()), "completed": counts.get("COMPLETED", 0),
                 "failed": counts.get("FAILED", 0), "awaiting_approval": counts.get("AWAITING_APPROVAL", 0)},
        "sources": {"total": len(owned_sources), "approved": sum(s.status == "ACTIVE" for s in owned_sources),
                    "resources": sum(len(s.approved.get("resources", {})) for s in owned_sources)},
        "planner": gemini_planner.status(),
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


@router.get("/sources/{identifier}/health")
def source_health(identifier: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    source = owned(db, ClientSource, identifier, user)
    started = time.perf_counter()
    try:
        current = catalog(source)
        matches = digest(current) == source.approved.get("schema_sha256")
        result = {"status": "reachable" if matches else "review_required",
                  "message": "Service reachable; approved schema matches." if matches else "Service reachable; review and approve its current schema.",
                  "resource_count": len(current)}
    except HTTPException as error:
        result = {"status": "unavailable", "message": str(error.detail)}
    except Exception:
        result = {"status": "unavailable", "message": "Connection check failed. Check service configuration and permissions."}
    return {"source_id": source.id, **result, "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "check": "schema reachability; record retrieval is checked when a task runs"}


class ResourceGrant(BaseModel):
    key_field: str
    bindings: dict[str, str] = Field(default_factory=dict)
    writable_fields: list[str] = Field(default_factory=list)


class SourceApproval(BaseModel):
    schema_sha256: str
    resources: dict[str, ResourceGrant]


@router.post("/sources/{identifier}/approve")
def approve_source(identifier: str, req: SourceApproval, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_admin(user)
    source = owned(db, ClientSource, identifier, user)
    current = catalog(source)
    if digest(current) != req.schema_sha256:
        raise HTTPException(409, "Schema changed; rediscover before approving")
    if not req.resources:
        raise HTTPException(422, "Explicitly select at least one resource")
    for name, grant in req.resources.items():
        resource = current.get(name)
        if not resource or grant.key_field not in resource["fields"] or any(field not in resource["fields"] for field in grant.bindings.values()) or any(field not in resource["writable"] or field == grant.key_field for field in grant.writable_fields):
            raise HTTPException(422, "Grant references an undiscovered resource, key, binding or writable field")
        if set(grant.bindings) - {"name", "address", "country"}:
            raise HTTPException(422, "Entity bindings support name, address and country")
        if grant.writable_fields and source.kind == "openapi" and not resource.get("update_path"):
            raise HTTPException(422, "The source does not declare an item PATCH operation")
        if grant.writable_fields and source.kind == "openapi" and not resource.get("write_precondition"):
            raise HTTPException(422, "Writes require declared native If-Match support or the conditional bridge contract. Read access needs no bridge changes")
    source.discovered = current
    source.approved = {"schema_sha256": digest(current), "resources": {name: grant.model_dump() for name, grant in req.resources.items()}}
    source.status = "ACTIVE"
    db.commit()
    append_audit_entry(db, user.id, user.role, "CLIENT_CAPABILITIES_APPROVED", "SOURCE", source.id, source.approved)
    return describe_source(source)


@router.post("/sources/{identifier}/rediscover")
def rediscover(identifier: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_admin(user)
    source = owned(db, ClientSource, identifier, user)
    current = catalog(source)
    source.discovered = current
    if digest(current) != source.approved.get("schema_sha256"):
        source.status = "NEEDS_REVIEW"
    db.commit()
    return describe_source(source)


def check_schema(source):
    if source.status != "ACTIVE" or digest(catalog(source)) != source.approved.get("schema_sha256"):
        raise HTTPException(409, f"{source.name}: capabilities or schema require review")


def read_rows(source, resource_name):
    resource = source.discovered[resource_name]
    if source.kind == "openapi":
        result = http(source.config, "GET", resource["read_path"])
        rows = result.get(resource["list_field"]) if resource["list_field"] and isinstance(result, dict) else result
    else:
        database = sqlite_connect(source.config)
        try:
            with database.connect() as connection:
                table = Table(resource_name, MetaData(), autoload_with=connection)
                rows = [dict(row) for row in connection.execute(select(table).limit(10001)).mappings()]
        finally:
            database.dispose()
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise HTTPException(422, "Collection response does not match the discovered JSON contract")
    row_limit = 10000 if source.kind == "sqlite" else 500
    if len(rows) > row_limit:
        raise HTTPException(422, f"This prototype supports {row_limit} rows per {source.kind} resource. Narrow the source view; pagination is not yet implemented")
    fields = resource["fields"]
    rows = [{key: value for key, value in row.items() if key in fields} for row in rows]
    key = source.approved["resources"][resource_name]["key_field"]
    ids = [str(row.get(key)) for row in rows]
    if any(row.get(key) is None for row in rows) or len(set(ids)) != len(ids):
        raise HTTPException(422, "Client key field is missing or not unique")
    return json.loads(json.dumps(rows, default=str))


def emit(db, run, tool, message, details=None):
    run.events = [*run.events, {"timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "tool": tool, "message": message, "details": details or {}}]
    db.commit()


def run_view(run):
    return {key: getattr(run, key) for key in ["id", "goal", "status", "events", "evidence", "proposal", "result"]}


class Mutation(BaseModel):
    source_id: str
    resource: str
    record_key: str
    changes: dict[str, Any] = Field(min_length=1, max_length=10)


class RunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=2000)
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    task: Literal["auto", "retrieve", "compare"] = "auto"
    mutation: Mutation | None = None
    planner: Literal["local", "gemini"] = "gemini"
    analysis: dict = Field(default_factory=dict)
    operation: Literal["browse", "summary", "compare"] | None = None
    search: str = Field(default="", max_length=1000)
    limit: int = Field(default=20, ge=1, le=100)
    random_sample: bool = False


@router.get("/intelligence/models")
def local_models(user: User = Depends(get_current_user)):
    return {"models": local_intelligence.inventory(), "policy": "Gemini selects tools; local artifacts compute predictions; backend permissions and human approval control writes."}


class LocalInferenceRequest(BaseModel):
    model: str
    analysis: dict


@router.post("/intelligence/predict")
def explicit_local_inference(req: LocalInferenceRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    started = time.perf_counter()
    run = AgentRun(id=str(uuid.uuid4()), owner_id=user.id, goal="Explicit local analysis: " + req.model, status="RUNNING", events=[], evidence={"model_input": req.analysis}, proposal={}, result={})
    db.add(run);db.commit()
    try:
        analysis = local_intelligence.predict(req.model, req.analysis)
        run.status = "COMPLETED"
        run.result = {"type": "ml_analysis", "analysis": analysis, "summary": "Completed the explicitly selected local artifact operation. No external AI call or enterprise write was performed."}
        emit(db, run, "model." + req.model, "Executed the existing artifact using the user-selected local analysis control", analysis)
    except HTTPException as error:
        run.status = "FAILED"
        run.result = {"error": error.detail, "http_status": error.status_code}
        emit(db, run, "failure", str(error.detail))
    run.result = {**run.result, "execution": {"input": {"request": run.goal, "source_ids": []}, "planner": "backend tools", "provider": None, "model": None, "local_model": req.model, "duration_ms": round((time.perf_counter()-started)*1000, 2)}}
    append_audit_entry(db, user.id, user.role, "LOCAL_ML_INFERENCE", "AGENT_RUN", run.id, {"model": req.model, "status": run.status, "result_sha256": digest(run.result), "artifact_sha256": run.result.get("analysis", {}).get("artifact_sha256")})
    db.commit()
    return run_view(run)


@router.get("/planner")
def planner_status(user: User = Depends(get_current_user)):
    return gemini_planner.status()


@router.post("/planner/verify")
def verify_planner(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Verify a real structured provider response using only generic test metadata.
    capabilities = [{"source_id": "connection-check", "source_name": "Connection verification",
                     "domain": "CRM", "resource": "records", "key_field": "id",
                     "fields": {"id": "string", "name": "string"}, "writable_fields": []}]
    try:
        result = gemini_planner.plan("List all records", capabilities)
    except HTTPException:
        append_audit_entry(db, user.id, user.role, "AI_PROVIDER_VERIFICATION_FAILED", "AI_PROVIDER", "google", gemini_planner.status())
        raise
    verified = gemini_planner.status()
    append_audit_entry(db, user.id, user.role, "AI_PROVIDER_VERIFIED", "AI_PROVIDER", "google", verified)
    return {**verified, "test_action": result.action, "enterprise_data_sent": False, "tools_executed": False}


@router.post("/runs")
def start_run(req: RunRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    started = time.perf_counter()
    if req.operation:
        if req.analysis or req.mutation:
            raise HTTPException(422, "Structured read operations cannot include analysis input or a mutation")
        req.planner = "local"  # Explicit user-selected tool operation; never a provider fallback.
    uses_gemini = req.planner == "gemini" and req.mutation is None
    if req.mutation and user.role not in ("ADMIN", "OPERATIONS_APPROVER", "COMPLIANCE_OFFICER"):
        raise HTTPException(403, "Your role cannot propose client writes")
    selected = [owned(db, ClientSource, identifier, user) for identifier in dict.fromkeys(req.source_ids)]
    run = AgentRun(id=str(uuid.uuid4()), owner_id=user.id, goal=req.goal, status="RUNNING", events=[], evidence={}, proposal={}, result={})
    db.add(run)
    db.commit()
    local_intent = None
    try:
        language_plan = gemini_planner.ToolPlan(action={"browse": "retrieve", "summary": "summary", "compare": "compare"}[req.operation], query=req.search if req.operation == "browse" else "", source_id="", resource="", record_key="", changes=[], explanation="Explicit operation selected by the user") if req.operation else None
        from ml.models.intent_parser.features import detect_prompt_injection
        if detect_prompt_injection(req.goal):
            raise HTTPException(403, "Request blocked by deterministic injection-pattern guard; no provider call or enterprise operation performed")
        try:
            local_intent = local_intelligence.predict("intent_parser", {"prompt": req.goal})
            emit(db, run, "model.intent_parser", "Computed task classification using the trained local artifact; this prediction does not grant permissions", local_intent)
        except HTTPException as error:
            if error.status_code != 503: raise
            emit(db, run, "model.intent_parser.unavailable", "Intent artifact unavailable; backend permissions and deterministic guards remain enforced", {"error": error.detail})
        if req.operation:
            emit(db, run, "tool.operation", "Executing the operation explicitly selected by the user; no external AI request", {"operation": req.operation, "search": req.search, "limit": req.limit, "random_sample": req.random_sample})
        if req.planner == "gemini" and not req.mutation:
            capabilities = []
            for source in selected:
                check_schema(source)
                for name, grant in source.approved["resources"].items():
                    capabilities.append({"source_id": source.id, "source_name": source.name, "domain": source.domain,
                                         "resource": name, "key_field": grant["key_field"],
                                         "fields": {field: value["type"] for field, value in source.discovered[name]["fields"].items()},
                                         "writable_fields": grant["writable_fields"]})
            if req.analysis:
                capabilities.append({"kind": "local_ml", "input_available": True, "models": list(local_intelligence.ARTIFACTS),
                                     "input_field_names": sorted(req.analysis), "source_id": "", "resource": ""})
            emit(db, run, "planner.gemini.request", "Requesting a language-to-tool plan using approved schema metadata; client rows are excluded", {"model": gemini_planner.status()["model"]})
            language_plan = gemini_planner.plan(req.goal, capabilities)
            if language_plan.action == "analyze":
                if not req.analysis or not language_plan.analysis_model:
                    raise HTTPException(422, "Provide structured analysis input for the requested local model")
                if any([language_plan.query, language_plan.source_id, language_plan.resource, language_plan.record_key, language_plan.changes]):
                    raise HTTPException(422, "Local analysis cannot include retrieval scope or proposed mutations")
                emit(db, run, "planner.gemini.validated", "Validated Gemini's selection of an allowlisted local model; input values remain in the backend", {"model": gemini_planner.status()["model"], "plan": language_plan.model_dump(), "provider_attempts": language_plan._provider_metadata.get("attempts")})
                analysis = local_intelligence.predict(language_plan.analysis_model, req.analysis)
                emit(db, run, "model." + language_plan.analysis_model, "Executed the existing artifact locally without retraining; no enterprise tools or writes executed", analysis)
                run.status = "COMPLETED"
                run.evidence = {"model_input": req.analysis}
                run.result = {"type": "ml_analysis", "summary": f"Completed local {language_plan.analysis_model.replace('_', ' ')} inference. Result is advisory; no enterprise write performed.",
                              "analysis": analysis, "local_intent": local_intent,
                              "execution": {"input": {"request": req.goal, "source_ids": req.source_ids}, "planner": "gemini", "provider": "google", "model": gemini_planner.status()["model"], "duration_ms": round((time.perf_counter()-started)*1000, 2), "local_model": analysis["model"], "local_version": analysis["version"], "artifact_sha256": analysis["artifact_sha256"], "provider_attempts": language_plan._provider_metadata.get("attempts")}}
                emit(db, run, "complete", "Hybrid Gemini selection and local artifact inference completed")
                append_audit_entry(db, user.id, user.role, "HYBRID_ML_INFERENCE", "AGENT_RUN", run.id, {"gemini_model": gemini_planner.status()["model"], "local_model": analysis["model"], "local_version": analysis["version"], "artifact_sha256": analysis["artifact_sha256"], "input_sha256": digest(req.analysis), "result_sha256": digest(run.result)})
                db.commit()
                return run_view(run)
            if language_plan.analysis_model:
                raise HTTPException(422, "Unexpected local model selection in a non-analysis plan")
            scope = None
            if language_plan.source_id and language_plan.resource:
                scope = next((item for item in capabilities if item.get("kind") != "local_ml" and item["source_id"] == language_plan.source_id and item["resource"] == language_plan.resource), None)
                if scope is None:
                    alt = next((item for item in capabilities if item.get("kind") != "local_ml" and item["resource"] == language_plan.resource), None)
                    if alt:
                        scope = alt
                        language_plan.source_id = alt["source_id"]
                    else:
                        raise HTTPException(422, "Gemini proposed an unknown or unapproved resource")
            elif language_plan.resource and not language_plan.source_id:
                matching = [item for item in capabilities if item.get("kind") != "local_ml" and item["resource"] == language_plan.resource]
                if not matching:
                    raise HTTPException(422, "Gemini proposed an unknown or unapproved resource")
                scope = matching[0]
                language_plan.source_id = scope["source_id"]
            elif language_plan.source_id and not language_plan.resource:
                matching = [item for item in capabilities if item.get("kind") != "local_ml" and item["source_id"] == language_plan.source_id]
                if not matching:
                    raise HTTPException(422, "Gemini proposed an unknown or unapproved source")
                scope = matching[0]
            if (language_plan.source_id or language_plan.resource) and scope is None:
                raise HTTPException(422, "Gemini proposed an unknown or unapproved resource")
            if language_plan.action == "compare" and scope:
                raise HTTPException(422, "Comparison needs at least two resources; select the sources to compare")
            if language_plan.action == "update":
                if not scope or not language_plan.record_key or not re.search(r'(?<![\w-])' + re.escape(language_plan.record_key) + r'(?![\w-])', req.goal):
                    raise HTTPException(422, "An update requires an exact record key in your request and one approved resource")
                if not language_plan.changes or len({change.field for change in language_plan.changes}) != len(language_plan.changes):
                    raise HTTPException(422, "Invalid or duplicate proposed field changes")
                try:
                    changes = {change.field: json.loads(change.value_json) for change in language_plan.changes}
                except ValueError:
                    raise HTTPException(422, "Gemini proposed an invalid field value")
                if set(changes) - set(scope["writable_fields"]):
                    raise HTTPException(403, "Gemini proposed a change outside the approved write scope")
                if user.role not in ("ADMIN", "OPERATIONS_APPROVER", "COMPLIANCE_OFFICER"):
                    raise HTTPException(403, "Your role cannot propose client writes")
                req.mutation = Mutation(source_id=scope["source_id"], resource=scope["resource"], record_key=language_plan.record_key, changes=changes)
            elif language_plan.changes or language_plan.record_key:
                raise HTTPException(422, "Unexpected mutation data in a read plan")
            emit(db, run, "planner.gemini.validated", "Validated the Gemini plan against approved capabilities; execution remains controlled by the backend", {"model": gemini_planner.status()["model"], "plan": language_plan.model_dump(), "provider_attempts": language_plan._provider_metadata.get("attempts")})
        compare = req.task == "compare" or (req.task == "auto" and bool(re.search(r"\b(duplicate|duplicates|deduplicate|compare|match|matching)\b", req.goal, re.I)))
        if not selected:
            raise HTTPException(422, "Select approved sources for data workflows, or provide structured input for a supported local analysis")
        summarize = bool(re.search(r"\b(summarize|summarise|summary|overview|count|totals)\b", req.goal, re.I)) and not req.mutation
        requested_update = bool(re.match(r"\s*(?:please\s+)?(?:set|update|mark)\b", req.goal, re.I))
        if language_plan:
            compare = language_plan.action == "compare"
            summarize = language_plan.action == "summary"
            requested_update = False
        if not language_plan and req.task == "auto" and not req.mutation and re.search(r"\b(delete|remove|pay|send|create|merge)\b", req.goal, re.I):
            raise HTTPException(422, "Destructive actions, payments, messaging and record creation are unsupported")
        if not language_plan:
            emit(db, run, "planner", "Grounded local planner selected tools from approved client capabilities", {"strategy": "compare_entities" if compare else "retrieve_records", "sources": [source.name for source in selected], "planner": "local constrained tool planner"})
        evidence = []
        for source in selected:
            check_schema(source)
            emit(db, run, "schema_guard", "Verified the current client schema against the approved fingerprint", {"source_id": source.id, "schema_sha256": source.approved["schema_sha256"]})
            for resource_name, grant in source.approved["resources"].items():
                if language_plan and language_plan.source_id and (source.id != language_plan.source_id or resource_name != language_plan.resource):
                    continue
                if language_plan and not language_plan.source_id and language_plan.resource and resource_name != language_plan.resource:
                    continue
                rows = read_rows(source, resource_name)
                emit(db, run, "client.read", f"Retrieved {len(rows)} current records from {source.name} · {resource_name}", {"source_id": source.id, "resource": resource_name, "domain": source.domain, "response_sha256": digest(rows)})
                evidence.append({"source_id": source.id, "source_name": source.name, "domain": source.domain, "resource": resource_name, "key_field": grant["key_field"], "bindings": grant["bindings"], "writable_fields": grant["writable_fields"], "schema_sha256": source.approved["schema_sha256"], "rows": rows})
        run.evidence = {"resources": evidence}
        db.commit()
        if requested_update and not req.mutation:
            proposed = []
            for item in evidence:
                changes = {}
                for field in item["writable_fields"]:
                    assignment = re.search(r'(?<!\w)' + re.escape(field) + r'\s*=\s*("(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?|true|false)', req.goal)
                    if assignment:
                        changes[field] = json.loads(assignment.group(1))
                if changes:
                    for row in item["rows"]:
                        key = str(row[item["key_field"]])
                        if re.search(r'(?<![\w-])' + re.escape(key) + r'(?![\w-])', req.goal):
                            proposed.append(Mutation(source_id=item["source_id"], resource=item["resource"], record_key=key, changes=changes))
            if len(proposed) != 1:
                raise HTTPException(422, 'Specify one unambiguous key and an approved field assignment: Set FIELD = "value" for RECORD_KEY. You can also select a retrieved row to propose an update')
            if user.role not in ("ADMIN", "COMPLIANCE_OFFICER", "OPERATIONS_APPROVER"):
                raise HTTPException(403, "Your role cannot propose a client update")
            req.mutation = proposed[0]
            emit(db, run, "planner.ground_update", "Bound the requested field assignment to one actual retrieved record and its approved write capability", {"source_id": req.mutation.source_id, "resource": req.mutation.resource, "record_key": req.mutation.record_key, "changes": req.mutation.changes})
        if req.mutation:
            run.result = {"type": "mutation_preparation", "summary": "Retrieved current client records to prepare an exact field-change proposal. Review the before/after evidence below."}
        elif compare:
            groups = [item for item in evidence if item["bindings"].get("name")]
            if len(groups) < 2:
                raise HTTPException(422, "Entity comparison requires name bindings on at least two approved resources")
            matches = []
            scored_pairs = 0
            blocking_used = False
            possible_pairs = sum(len(left["rows"]) * len(right["rows"]) for index, left in enumerate(groups) for right in groups[index+1:])
            for index, left in enumerate(groups):
                for right in groups[index + 1:]:
                    shortlist = len(left["rows"]) * len(right["rows"]) > 25000
                    blocking_used = blocking_used or shortlist
                    choices = {i: str(target.get(right["bindings"]["name"]) or "") for i, target in enumerate(right["rows"])}
                    def entity(item, row):
                        bindings = item["bindings"]
                        return {"entity_id": str(row[item["key_field"]]), "business_name": str(row.get(bindings["name"]) or ""), "business_address": str(row.get(bindings.get("address", "")) or ""), "country": str(row.get(bindings.get("country", "")) or "GLOBAL"), "source_system": item["domain"]}
                    for row in left["rows"]:
                        query = entity(left, row)
                        indices = [item[2] for item in process.extract(query["business_name"], choices, scorer=fuzz.WRatio, limit=10, score_cutoff=60)] if shortlist else range(len(right["rows"]))
                        candidates = [entity(right, right["rows"][i]) for i in indices]
                        if left["bindings"].get("country") and right["bindings"].get("country"):
                            candidates = [candidate for candidate in candidates if candidate["country"].casefold() == query["country"].casefold()]
                        if not query["business_name"].strip():
                            continue
                        scored_matches = []
                        for offset in range(0, len(candidates), 100):
                            batch = candidates[offset:offset+100]
                            if scored_pairs + len(batch) > 50000:
                                raise HTTPException(422, "Comparison reached 50000 scored candidate pairs. Select fewer sources to complete this run.")
                            prediction = local_intelligence.predict("entity_resolution", {"query": query, "candidates": batch})
                            scored_pairs += len(batch)
                            scored_matches.extend(prediction["output"].get("matches", []))
                        scored_matches.sort(key=lambda match: match["match_probability"], reverse=True)
                        for match in scored_matches[:10]:
                            if match["match_probability"] >= .4:
                                matches.append({"source_id": left["source_id"], "resource": left["resource"], "record_key": query["entity_id"], "source_name": query["business_name"], "target_source_id": right["source_id"], "target_resource": right["resource"], **match})
            run.result = {"type": "entity_comparison", "matches": matches, "summary": f"Scored {scored_pairs} candidate pairs across {len(groups)} resources; {len(matches)} candidate links need review. {'Large comparisons used a bounded lexical shortlist; results are not exhaustive.' if blocking_used else 'Candidate scoring used country filtering where available.'} No records were merged.", "model": "entity_resolution", "model_version": "1.2.0", "candidate_generation": {"possible_pairs": possible_pairs, "scored_pairs": scored_pairs, "lexical_shortlisting_used": blocking_used, "shortlist_limit": 10 if blocking_used else None, "shortlist_cutoff": 60 if blocking_used else None, "note": "Lexical selection is deterministic candidate generation, not a learned prediction. Only the artifact produces match scores."}}
            _, artifact_path, artifact_hash = local_intelligence.load_artifact("entity_resolution")
            run.result["artifact_sha256"] = artifact_hash
            emit(db, run, "model.entity_resolution", "Computed pairwise LightGBM evidence from retrieved client records", {"candidate_links": len(matches), "artifact_sha256": artifact_hash, "artifact_path": str(artifact_path.relative_to(local_intelligence.ROOT))})
        elif summarize:
            summaries = []
            for item in evidence:
                numeric = {}
                for field in selected[[source.id for source in selected].index(item["source_id"])].discovered[item["resource"]]["fields"]:
                    values = [row.get(field) for row in item["rows"]]
                    values = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
                    if values:
                        numeric[field] = {"count": len(values), "sum": sum(values), "minimum": min(values), "maximum": max(values)}
                summaries.append({"source": item["source_name"], "resource": item["resource"], "row_count": len(item["rows"]), "numeric_fields": numeric})
            run.result = {"type": "summary", "resources": summaries, "summary": f"Summarized {sum(item['row_count'] for item in summaries)} live records from {len(summaries)} resources. Numeric sums use source units; currencies are not inferred."}
            emit(db, run, "evidence.aggregate", "Computed counts and numeric summaries from client responses")
        else:
            quoted = re.findall(r'["“]([^"”]+)["”]', req.goal)
            found = []
            sample_request = re.search(r"\b(?:random|first|top)\s+(\d+)\b|\b(?:retrieve|retriev|show|list)\s+(\d+)\b", req.goal, re.I)
            limit = req.limit if req.operation else (min(100, max(1, int(next(value for value in sample_request.groups() if value)))) if sample_request else 100)
            terms = [word for word in re.findall(r"[\w-]+", req.goal.casefold()) if word not in {"show", "find", "search", "records", "record", "all", "the", "from", "in", "and", "across", "crm", "erp", "database", "db", "retrieve", "retriev", "please", "list", "me", "information", "about", "random", "first", "top", "clients", "client", "data"} and not (sample_request and word.isdigit())]
            query = " ".join(quoted) if quoted else " ".join(terms)
            if language_plan:
                query = language_plan.query
            for item in evidence:
                for row in item["rows"]:
                    text = " ".join(str(value) for value in row.values())
                    score = fuzz.partial_token_set_ratio(query, text) if query else 100
                    if not query or score >= 65:
                        found.append({"source_id": item["source_id"], "resource": item["resource"], "record_key": str(row[item["key_field"]]), "relevance": round(score / 100, 3), "record": row})
            found.sort(key=lambda row: row["relevance"], reverse=True)
            random_selection = req.random_sample if req.operation else bool(re.search(r"\brandom\b", req.goal, re.I))
            selected_records = random.SystemRandom().sample(found, min(limit, len(found))) if random_selection else found[:limit]
            run.result = {"type": "retrieval", "records": selected_records, "total_matches": len(found), "returned_count": len(selected_records), "requested_limit": limit, "selection": "random sample of retrieved matches" if random_selection else "ranked matches", "summary": f"Returned {len(selected_records)} of {len(found)} matching records from {len(evidence)} connected resources.", "search": query, "ranking": "lexical fuzzy relevance; relevance scores are not model probabilities"}
            emit(db, run, "evidence.rank", "Ranked actual retrieved rows against the request", {"matches": len(found)})
        if req.mutation:
            mutation = req.mutation
            item = next((item for item in evidence if item["source_id"] == mutation.source_id and item["resource"] == mutation.resource), None)
            if item is None or set(mutation.changes) - set(item["writable_fields"]):
                raise HTTPException(403, "Proposed change exceeds the approved write scope")
            before = next((row for row in item["rows"] if str(row[item["key_field"]]) == mutation.record_key), None)
            if before is None:
                raise HTTPException(404, "The selected client record no longer exists")
            fields = next(source for source in selected if source.id == mutation.source_id).discovered[mutation.resource]["fields"]
            for key, value in list(mutation.changes.items()):
                target_type = fields.get(key, {}).get("type", "string")
                if target_type == "string" and not isinstance(value, str):
                    mutation.changes[key] = str(value)
                elif target_type in ("integer", "number") and isinstance(value, str):
                    try:
                        mutation.changes[key] = int(value) if target_type == "integer" else float(value)
                    except ValueError:
                        pass
                elif target_type == "boolean" and isinstance(value, str):
                    if value.lower() in ("true", "1", "yes"):
                        mutation.changes[key] = True
                    elif value.lower() in ("false", "0", "no"):
                        mutation.changes[key] = False
                if not valid_value(target_type, mutation.changes[key]):
                    raise HTTPException(422, f"Field {key} has an incompatible value type")
            run.proposal = {**mutation.model_dump(), "before": before, "before_sha256": digest(before), "schema_sha256": item["schema_sha256"], "key_field": item["key_field"]}
            run.status = "AWAITING_APPROVAL"
            emit(db, run, "approval_gate", "Prepared exact before/after field changes; waiting for authenticated approval", {"changes": mutation.changes, "client_write_performed": False})
        else:
            run.status = "COMPLETED"
            emit(db, run, "complete", "Completed evidence-based read workflow; no client mutation performed")
        db.commit()
    except HTTPException as error:
        run.status = "FAILED"
        run.result = {"error": error.detail, "http_status": error.status_code}
        emit(db, run, "failure", str(error.detail))
    except Exception:
        run.status = "FAILED"
        run.result = {"error": "Execution failed; no successful outcome is assumed"}
        emit(db, run, "failure", "Tool execution failed. Inspect the source contract and permissions")
    run.result = {**run.result, "execution": {
        "input": {"request": req.goal, "source_ids": req.source_ids, "search": req.search, "limit": req.limit, "random_sample": req.random_sample},
        "local_intent": local_intent,
        "datasets": [{"source_id": source.id, "kind": source.config["provenance"].get("dataset_kind", "public_snapshot"),
                      "title": source.config["provenance"].get("title"), "sha256": source.config["provenance"].get("sha256")}
                     for source in selected if source.config.get("provenance")],
        "planner": "gemini" if uses_gemini else "backend tools",
        "operation": req.operation,
        "provider_attempts": language_plan._provider_metadata.get("attempts") if uses_gemini and language_plan else None,
        "provider": "google" if uses_gemini else None,
        "model": gemini_planner.status()["model"] if uses_gemini else None,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "score": None,
        "score_note": "Retrieval returns source records; no trained classifier probability is produced.",
    }}
    append_audit_entry(db, user.id, user.role, "AGENT_RUN_PREPARED", "AGENT_RUN", run.id, {"status": run.status, "evidence_sha256": digest(run.evidence), "result_sha256": digest(run.result)})
    db.commit()
    return run_view(run)


def valid_value(kind, value):
    if kind == "string":
        return isinstance(value, (str, int, float, bool))
    if kind in ("number", "integer"):
        import math
        if isinstance(value, str):
            try:
                val = float(value)
                return math.isfinite(val) and (kind != "integer" or val.is_integer())
            except ValueError:
                return False
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and (kind != "integer" or isinstance(value, int))
    if kind == "boolean":
        if isinstance(value, str):
            return value.lower() in ("true", "false", "1", "0", "yes", "no")
        return isinstance(value, bool)
    return False


class DemoPreview(BaseModel):
    operation: Literal["preview", "summary"] = "preview"


@router.post("/sources/{identifier}/demo-preview")
def preview_open_data(identifier: str, req: DemoPreview, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    source = owned(db, ClientSource, identifier, user)
    if source.kind != "sqlite" or not source.config.get("provenance", {}).get("imported_rows"):
        raise HTTPException(422, "Direct demo actions require a registered local dataset snapshot")
    # Explicit tool action, not a language model prediction or provider fallback.
    return start_run(RunRequest(goal="Show first 10 records" if req.operation == "preview" else "Summarize connected records", source_ids=[identifier], task="retrieve", planner="local"), db, user)


@router.get("/runs")
def runs(status: Literal["AWAITING_APPROVAL", "COMPLETED", "FAILED"] | None = None, compact: bool = False,
         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(AgentRun).filter_by(owner_id=user.id)
    if status:
        query = query.filter_by(status=status)
    if compact:
        query = query.options(load_only(AgentRun.id, AgentRun.goal, AgentRun.status, AgentRun.events, AgentRun.result))
        history = [{"id": run.id, "goal": run.goal, "status": run.status,
                    "events": run.events[:1] + (run.events[-1:] if len(run.events)>1 else []),
                    "evidence": {}, "proposal": {}, "result": {key: value for key, value in run.result.items() if key in ("type", "summary", "error")}}
                   for run in query.all()]
    else:
        history = [run_view(run) for run in query.all()]
    ordered = sorted(history, key=lambda item: item["events"][0]["timestamp"] if item["events"] else "", reverse=True)
    return ordered if status == "AWAITING_APPROVAL" else ordered[:30]


@router.get("/runs/{identifier}")
def get_run(identifier: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return run_view(owned(db, AgentRun, identifier, user))


class RunDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    comments: str = Field(min_length=3, max_length=2000)


@router.post("/runs/{identifier}/decide")
def decide_run(identifier: str, req: RunDecision, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in ("ADMIN", "COMPLIANCE_OFFICER", "OPERATIONS_APPROVER"):
        raise HTTPException(403, "Your authenticated role cannot approve writes")
    run = owned(db, AgentRun, identifier, user)
    if run.status != "AWAITING_APPROVAL":
        raise HTTPException(409, "Only a pending proposal can be decided")
    claimed = db.query(AgentRun).filter_by(id=run.id, status="AWAITING_APPROVAL").update({"status": "EXECUTING" if req.decision == "APPROVE" else "REJECTED"}, synchronize_session=False)
    if not claimed:
        db.rollback()
        raise HTTPException(409, "This proposal was already claimed")
    db.commit()
    db.refresh(run)
    if req.decision == "REJECT":
        emit(db, run, "approval_gate", "Reviewer rejected the proposed mutation", {"reviewer": user.id, "comments": req.comments})
        append_audit_entry(db, user.id, user.role, "CLIENT_UPDATE_REJECTED", "AGENT_RUN", run.id, {"comments": req.comments})
        return run_view(run)
    mutation_sent = False
    try:
        proposal = run.proposal
        source = owned(db, ClientSource, proposal["source_id"], user)
        check_schema(source)
        if source.approved["schema_sha256"] != proposal["schema_sha256"]:
            raise HTTPException(409, "The approved source schema changed")
        grant = source.approved["resources"].get(proposal["resource"], {})
        if set(proposal["changes"]) - set(grant.get("writable_fields", [])):
            raise HTTPException(403, "The write grant has been revoked")
        rows = read_rows(source, proposal["resource"])
        before = next((row for row in rows if str(row[proposal["key_field"]]) == proposal["record_key"]), None)
        if before is None or digest(before) != proposal["before_sha256"]:
            raise HTTPException(409, "Client record changed since the preview; create a new proposal")
        emit(db, run, "approval_gate", "Authenticated reviewer approved the exact proposed changes", {"reviewer": user.id, "comments": req.comments})
        if source.kind == "openapi":
            resource = source.discovered[proposal["resource"]]
            path = re.sub(r"\{[^{}]+\}", quote(proposal["record_key"], safe=""), resource["update_path"])
            conditional = {"X-Aventra-Expected-Hash": proposal["before_sha256"]}
            if resource.get("write_precondition") == "etag":
                snapshot = http(source.config, "GET", path, metadata=True)
                item = snapshot["body"]
                if not isinstance(item, dict) or not snapshot["etag"] or digest({key: value for key, value in item.items() if key in resource["fields"]}) != proposal["before_sha256"]:
                    raise HTTPException(409, "Item ETag or current representation is unavailable; no write performed")
                conditional = {"If-Match": snapshot["etag"]}
            elif resource.get("write_precondition") != "sha256":
                raise HTTPException(409, "The client has no approved atomic write precondition")
            mutation_sent = True
            http(source.config, "PATCH", path, proposal["changes"], {"Idempotency-Key": run.id, **conditional})
        else:
            readonly = sqlite_connect(source.config)
            readonly.dispose()
            root = Path(os.getenv("AVENTRA_DATA_ROOT", "data")).resolve()
            path = (root / source.config["relative_path"]).resolve()
            database = create_engine(f"sqlite:///file:{quote(path.as_posix(), safe='/:')}?mode=rw&uri=true")
            try:
                with database.begin() as connection:
                    table = Table(proposal["resource"], MetaData(), autoload_with=connection)
                    # Full-row compare-and-swap prevents overwriting concurrent client changes.
                    conditions = [table.c[key].is_(None) if value is None else table.c[key] == value for key, value in before.items()]
                    changed = connection.execute(update(table).where(and_(*conditions)).values(**proposal["changes"]))
                    if changed.rowcount != 1:
                        raise HTTPException(409, "Client record changed before the update")
                mutation_sent = True
            finally:
                database.dispose()
        emit(db, run, "client.patch", "Client mutation submitted once; reading the source to verify", {"idempotency_key": run.id})
        actual = next((row for row in read_rows(source, proposal["resource"]) if str(row[proposal["key_field"]]) == proposal["record_key"]), None)
        if actual is None or any(actual.get(key) != value for key, value in proposal["changes"].items()):
            raise HTTPException(409, "Client result does not match the approved changes; manual reconciliation required")
        run.status = "COMPLETED"
        run.result = {"execution": run.result.get("execution"), "type": "verified_update", "before": before, "after": actual, "verified": True, "summary": "Approved changes were applied and verified by reading the client system again."}
        emit(db, run, "client.verify", "Re-read verified all approved field changes", {"response_sha256": digest(actual)})
        append_audit_entry(db, user.id, user.role, "CLIENT_UPDATE_VERIFIED", "AGENT_RUN", run.id, {"source_id": source.id, "before_sha256": digest(before), "after_sha256": digest(actual), "comments": req.comments})
        db.commit()
    except Exception as error:
        run.status = "RECONCILIATION_REQUIRED" if mutation_sent else "FAILED"
        run.result = {"execution": run.result.get("execution"), "error": error.detail if isinstance(error, HTTPException) else "Client execution failed", "mutation_may_have_occurred": mutation_sent, "automatic_retry": False}
        emit(db, run, "failure", "No completion claimed; review the client state before any new attempt", run.result)
    return run_view(run)
