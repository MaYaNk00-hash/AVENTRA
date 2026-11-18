"""Client-side, configuration-only database bridge. Does not modify table schemas.

Set AVENTRA_BRIDGE_DATABASE_URL, AVENTRA_BRIDGE_TABLES, AVENTRA_BRIDGE_TOKEN.
Optional AVENTRA_BRIDGE_WRITES is a JSON mapping of table names to writable columns.
Run: python -m uvicorn infrastructure.bridge.app:app --host 127.0.0.1 --port 8200
"""
import datetime
import decimal
import hashlib
import json
import os
import secrets

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, inspect, Table, MetaData, select, update, and_

URL = os.getenv("AVENTRA_BRIDGE_DATABASE_URL")
TOKEN = os.getenv("AVENTRA_BRIDGE_TOKEN")
TABLES = [name.strip() for name in os.getenv("AVENTRA_BRIDGE_TABLES", "").split(",") if name.strip()]
WRITES = json.loads(os.getenv("AVENTRA_BRIDGE_WRITES", "{}"))
if not URL or not TOKEN or not TABLES:
    raise RuntimeError("Configure database URL, table allowlist and bridge bearer token before starting")
engine = create_engine(URL, pool_pre_ping=True)
app = FastAPI(title="AVENTRA client-side database bridge", openapi_url=None)
bearer = HTTPBearer()


def authorize(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not secrets.compare_digest(credentials.credentials, TOKEN):
        raise HTTPException(403, "Bridge credential invalid")


def portable(row):
    return {key: value.isoformat() if isinstance(value, (datetime.date, datetime.datetime)) else float(value) if isinstance(value, decimal.Decimal) else value for key, value in dict(row).items()}


def digest(row):
    return hashlib.sha256(json.dumps(portable(row), sort_keys=True, default=str).encode()).hexdigest()


def table_for(name):
    if name not in TABLES:
        raise HTTPException(404, "Table is outside the bridge allowlist")
    return Table(name, MetaData(), autoload_with=engine)


def key_for(table):
    keys = list(table.primary_key.columns)
    if len(keys) != 1:
        raise HTTPException(422, "This bridge requires a single-column primary key")
    return keys[0]


def kind(column):
    try:
        python_type = column.type.python_type
    except (NotImplementedError, AttributeError):
        return "unsupported"
    return "boolean" if python_type is bool else "integer" if python_type is int else "number" if python_type in (float, decimal.Decimal) else "string" if python_type is str else "unsupported"


@app.get("/openapi.json", dependencies=[Depends(authorize)])
def discovery():
    paths = {}
    for name in TABLES:
        table = table_for(name)
        key = key_for(table)
        fields = {column.name: {"type": kind(column) if kind(column) != "unsupported" else "string", "description": column.comment or column.name.replace("_", " ")} for column in table.columns}
        response = {"description": "Live client data", "content": {"application/json": {"schema": {"type": "object", "properties": fields}}}}
        paths[f"/data/{name}"] = {"get": {"summary": name, "responses": {"200": {"description": "Live collection", "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object", "properties": fields}}}}}}}}
        item = {"get": {"responses": {"200": response}}}
        writable = {column.name: fields[column.name] for column in table.columns if column.name in WRITES.get(name, []) and column.name != key.name and kind(column) != "unsupported"}
        if writable:
            item["patch"] = {"parameters": [{"name": "If-Match", "in": "header", "required": True, "schema": {"type": "string"}}], "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": writable, "additionalProperties": False}}}}, "responses": {"200": response}}
        paths[f"/data/{name}/{{record_key}}"] = item
    return {"openapi": "3.0.3", "info": {"title": "Client configured infrastructure bridge", "version": "1.0"}, "paths": paths}


@app.get("/data/{name}", dependencies=[Depends(authorize)])
def collection(name: str):
    table = table_for(name)
    with engine.connect() as connection:
        return [portable(row) for row in connection.execute(select(table).limit(501)).mappings()]


@app.get("/data/{name}/{record_key}", dependencies=[Depends(authorize)])
def record(name: str, record_key: str):
    table = table_for(name)
    key = key_for(table)
    with engine.connect() as connection:
        row = connection.execute(select(table).where(key == record_key)).mappings().first()
    if row is None:
        raise HTTPException(404, "Client record not found")
    return JSONResponse(portable(row), headers={"ETag": '"' + digest(row) + '"'})


@app.patch("/data/{name}/{record_key}", dependencies=[Depends(authorize)])
async def patch(name: str, record_key: str, request: Request):
    table = table_for(name)
    key = key_for(table)
    changes = await request.json()
    allowed = {column.name for column in table.columns if column.name in WRITES.get(name, []) and column.name != key.name and kind(column) != "unsupported"}
    if not isinstance(changes, dict) or not changes or set(changes) - allowed:
        raise HTTPException(403, "Mutation exceeds the client-configured write scope")
    for field, value in changes.items():
        expected = kind(table.c[field])
        valid = isinstance(value, str) if expected == "string" else isinstance(value, bool) if expected == "boolean" else isinstance(value, int) and not isinstance(value, bool) if expected == "integer" else isinstance(value, (int, float)) and not isinstance(value, bool)
        if not valid:
            raise HTTPException(422, "Value type does not match the client column")
        if isinstance(value, (int, float)):
            import math
            if not math.isfinite(value):
                raise HTTPException(422, "Nonfinite values are unsupported")
    with engine.begin() as connection:
        before = connection.execute(select(table).where(key == record_key)).mappings().first()
        if before is None:
            raise HTTPException(404, "Client record not found")
        if request.headers.get("If-Match") != '"' + digest(before) + '"':
            raise HTTPException(412, "Stale client representation; refresh before proposing another change")
        # The database enforces the precondition atomically, not just in Python.
        conditions = [table.c[field].is_(None) if value is None else table.c[field] == value for field, value in before.items()]
        changed = connection.execute(update(table).where(and_(*conditions)).values(**changes))
        if changed.rowcount != 1:
            raise HTTPException(409, "Concurrent client update detected")
        after = connection.execute(select(table).where(key == record_key)).mappings().one()
        return portable(after)
