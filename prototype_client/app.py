"""Separate editable client website/API for live judging, backed by actual SQLite.

Run: python -m uvicorn prototype_client.app:app --host 127.0.0.1 --port 8100
Change CLIENT_DB and CLIENT_TABLES to expose another permitted SQLite schema.
"""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="Independent client sandbox", openapi_url=None)
PATH = Path(os.getenv("CLIENT_DB", "data/judging-client.sqlite")).resolve()
TABLES = os.getenv("CLIENT_TABLES", "customer_accounts,supplier_directory,warehouse_orders").split(",")
METADATA = PATH.with_name(PATH.stem + ".aventra-sidecar.sqlite")
METADATA.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(METADATA) as metadata_db:
    metadata_db.execute("CREATE TABLE IF NOT EXISTS agent_idempotency (request_key TEXT PRIMARY KEY, payload_hash TEXT, response TEXT)")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def database():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(PATH)
    db.row_factory = sqlite3.Row
    db.execute("ATTACH DATABASE ? AS aventra", (str(METADATA),))
    return db


def seed():
    # Creates editable sample business data once, never canned agent responses.
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS customer_accounts (account_ref TEXT PRIMARY KEY, registered_title TEXT NOT NULL, postal_location TEXT, nation TEXT, review_state TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS supplier_directory (supplier_number TEXT PRIMARY KEY, trading_label TEXT NOT NULL, office_location TEXT, country_code TEXT, lifecycle TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS warehouse_orders (order_ticket TEXT PRIMARY KEY, organisation_label TEXT, committed_total REAL, fulfillment_state TEXT)")
        if not db.execute("SELECT 1 FROM customer_accounts").fetchone():
            db.executemany("INSERT INTO customer_accounts VALUES (?,?,?,?,?)",[("C-101","Narmada Precision Tools Private Limited","12 Industrial Estate, Gwalior","IN","unreviewed"),("C-102","Riverstone Components","15 Sector Road, Pune","IN","unreviewed")])
        if not db.execute("SELECT 1 FROM supplier_directory").fetchone():
            db.executemany("INSERT INTO supplier_directory VALUES (?,?,?,?,?)",[("S-201","Narmada Precision Tools Pvt Ltd","12 Industrial Est, Gwalior","IN","active"),("S-202","Coastal Freight Services","73 Harbour Road, Kochi","IN","active")])
        if not db.execute("SELECT 1 FROM warehouse_orders").fetchone():
            db.executemany("INSERT INTO warehouse_orders VALUES (?,?,?,?)",[("ORDER-301","Narmada Precision Tools",12800.0,"received"),("ORDER-302","Coastal Freight Services",7400.0,"pending")])


if not os.getenv("CLIENT_DB") or os.getenv("CLIENT_INITIALIZE_SAMPLE") == "1":
    seed()


def columns(table):
    if table not in TABLES:
        raise HTTPException(404, "Table is not exposed by this client")
    with database() as db:
        values = db.execute('PRAGMA table_info("' + table.replace('"','""') + '")').fetchall()
    if not values:
        raise HTTPException(404, "Client table not found")
    return values


def key_field(table):
    primary = [column["name"] for column in columns(table) if column["pk"]]
    if len(primary) != 1:
        raise HTTPException(422, "Sandbox table must have a single primary key")
    return primary[0]


def quote(name):
    return '"' + name.replace('"','""') + '"'


@app.get("/openapi.json")
def spec():
    paths = {}
    for table in TABLES:
        properties = {column["name"]: {"type":"number" if any(word in column["type"].lower() for word in ["int","real","numeric"]) else "string", "description":column["name"].replace("_"," ")} for column in columns(table)}
        primary = key_field(table)
        row = {"type":"object","properties":properties}
        paths[f"/api/{table}"] = {"get":{"summary":table,"responses":{"200":{"description":"Current client records","content":{"application/json":{"schema":{"type":"array","items":row}}}}}}}
        paths[f"/api/{table}/{{record_key}}"] = {"get":{"responses":{"200":{"description":"Current record","content":{"application/json":{"schema":row}}}}},"patch":{"parameters":[{"name":"If-Match","in":"header","required":True,"schema":{"type":"string"}}],"requestBody":{"content":{"application/json":{"schema":{"type":"object","properties":{key:value for key,value in properties.items() if key != primary},"additionalProperties":False}}}},"responses":{"200":{"description":"Updated record"}}}}
    return {"openapi":"3.0.3","info":{"title":"Client-owned dynamic API","version":"1.0"},"paths":paths}


@app.get("/api/{table}")
def list_rows(table: str):
    columns(table)
    with database() as db:
        return [dict(row) for row in db.execute(f"SELECT * FROM {quote(table)} LIMIT 501")]


@app.get("/api/{table}/{record_key}")
def get_row(table: str, record_key: str):
    primary = key_field(table)
    with database() as db:
        row = db.execute(f"SELECT * FROM {quote(table)} WHERE {quote(primary)}=?", (record_key,)).fetchone()
    if not row:
        raise HTTPException(404,"Record not found")
    record = dict(row)
    return JSONResponse(record, headers={"ETag": '"'+digest(record)+'"'})


@app.patch("/api/{table}/{record_key}")
async def patch_row(table: str, record_key: str, request: Request):
    fields = {column["name"] for column in columns(table)}
    primary = key_field(table)
    changes = await request.json()
    if not isinstance(changes,dict) or not changes or set(changes)-fields or primary in changes:
        raise HTTPException(422,"Only known non-key fields may be updated")
    if any(value is not None and not isinstance(value,(str,int,float,bool)) for value in changes.values()):
        raise HTTPException(422,"Flat scalar field values required")
    body_hash = digest({"table":table,"record_key":record_key,"changes":changes})
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        request_key = request.headers.get("Idempotency-Key")
        if request_key:
            existing = db.execute("SELECT * FROM aventra.agent_idempotency WHERE request_key=?",(request_key,)).fetchone()
            if existing:
                if existing["payload_hash"]!=body_hash:
                    raise HTTPException(409,"Idempotency key was already used for another mutation")
                return json.loads(existing["response"])
        before = db.execute(f"SELECT * FROM {quote(table)} WHERE {quote(primary)}=?",(record_key,)).fetchone()
        if not before:
            raise HTTPException(404,"Record not found")
        if request.headers.get("If-Match") != '"'+digest(dict(before))+'"':
            raise HTTPException(412,"Record changed since the preview; refresh it")
        assignments = ','.join(quote(key)+'=?' for key in changes)
        db.execute(f"UPDATE {quote(table)} SET {assignments} WHERE {quote(primary)}=?",(*changes.values(),record_key))
        after = dict(db.execute(f"SELECT * FROM {quote(table)} WHERE {quote(primary)}=?",(record_key,)).fetchone())
        if request_key:
            db.execute("INSERT INTO aventra.agent_idempotency VALUES (?,?,?)",(request_key,body_hash,json.dumps(after)))
        return after


@app.get("/",response_class=HTMLResponse)
def home():
    return '''<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Client operations · independent sandbox</title><style>body{font:15px system-ui;background:#f1f4f8;color:#203047;margin:0}main{max-width:1100px;margin:40px auto;padding:25px}h1{font-size:34px}p{color:#62758c;line-height:1.7}section{background:white;padding:25px;margin-top:25px;border:1px solid #dce3eb;border-radius:12px}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:12px;border-bottom:1px solid #e6eaf0}button{cursor:pointer;background:#235c91;color:white;border:0;border-radius:6px;padding:10px 16px}input,select,textarea{padding:10px;border:1px solid #becbd9;border-radius:5px;margin:8px}pre{white-space:pre-wrap}#notice{color:#a43c28}</style></head><body><main><small>CLIENT-OWNED APPLICATION · LIVE SQLITE DATA</small><h1>Operations desk</h1><p>This is a separate editable client website on port 8100. Change its data before running Aventra. Every table and record below comes from this application's database; agent responses are not stored here.</p><button onclick="load()">Refresh client records</button><a href="/openapi.json"> API discovery document</a><div id="notice" role="alert"></div><div id="tables"></div><section><h2>Edit a record directly</h2><p>Change a client record here, then retrieve it through Aventra to demonstrate live access.</p><label>Table<select id="table"></select></label><label>Record key<input id="key"></label><label>Field<input id="field"></label><label>New string value<input id="value"></label><button onclick="edit()">Save in client system</button></section></main><script>
async function load(){const spec=await(await fetch('/openapi.json')).json();const root=document.querySelector('#tables');root.replaceChildren();const select=document.querySelector('#table');select.replaceChildren();for(const path of Object.keys(spec.paths).filter(p=>!p.includes('{'))){const name=path.split('/').pop();const option=document.createElement('option');option.value=name;option.textContent=name;select.append(option);const section=document.createElement('section');const title=document.createElement('h2');title.textContent=name;section.append(title);const rows=await(await fetch(path)).json();const table=document.createElement('table');const fields=Object.keys(spec.paths[path].get.responses['200'].content['application/json'].schema.items.properties);const head=document.createElement('tr');for(const field of fields){const th=document.createElement('th');th.textContent=field;head.append(th)}table.append(head);for(const row of rows){const tr=document.createElement('tr');for(const field of fields){const td=document.createElement('td');td.textContent=String(row[field]??'');tr.append(td)}table.append(tr)}section.append(table);root.append(section)}}
async function edit(){try{const path='/api/'+encodeURIComponent(document.querySelector('#table').value)+'/'+encodeURIComponent(document.querySelector('#key').value);const before=await fetch(path);if(!before.ok)throw Error('Record not found');const response=await fetch(path,{method:'PATCH',headers:{'Content-Type':'application/json','If-Match':before.headers.get('ETag')},body:JSON.stringify({[document.querySelector('#field').value]:document.querySelector('#value').value})});if(!response.ok)throw Error(await response.text());document.querySelector('#notice').textContent='Saved in client database. Run Aventra again to retrieve the new value.';await load()}catch(error){document.querySelector('#notice').textContent=error.message}}load();</script></body></html>'''
