"""Separate loopback showcase server. All mutations are isolated simulations."""
import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from showcase.core import ROOT, NAMES, LocalModel
from showcase.provider import configuration, get_provider

app=FastAPI(title='AVENTRA isolated ML showcase')
MODELS={}; ERRORS={}
for name in NAMES:
    try: MODELS[name]=LocalModel(name)
    except Exception as error: ERRORS[name]=type(error).__name__
try:
    from ml.models.entity_resolution.inference import EntityResolutionModel
    entity=EntityResolutionModel(); entity.load(); MODELS['entity_resolution']=entity
except Exception as error: ERRORS['entity_resolution']=type(error).__name__

DB=os.getenv('SHOWCASE_DATABASE',str(ROOT/'runtime.sqlite'))
SESSION=secrets.token_urlsafe(32)

@contextmanager
def database():
    with sqlite3.connect(DB,timeout=20) as db:
        db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp REAL, kind TEXT, payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, state TEXT, payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS operations (workflow_id TEXT PRIMARY KEY, operation TEXT, details TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS records (domain TEXT, record_key TEXT PRIMARY KEY, payload TEXT)')
        for domain,key,record in [('CRM','C1',{'entity_id':'C1','business_name':'Narmada Precision Tools','business_address':'12 Industrial Estate Gwalior','country':'IN','source_system':'CRM'}),('ERP','V1',{'entity_id':'V1','business_name':'Narmada Precision Tools Pvt Ltd','business_address':'12 Industrial Estate Gwalior','country':'IN','source_system':'ERP'})]:
            db.execute('INSERT OR IGNORE INTO records VALUES (?,?,?)',(domain,key,json.dumps(record)))
        db.commit()
        yield db

def log(db,kind,payload):
    db.execute('INSERT INTO events(timestamp,kind,payload) VALUES (?,?,?)',(time.time(),kind,json.dumps(payload,allow_nan=False)))

@app.middleware('http')
async def local_boundary(request:Request,call_next):
    if not configuration()['showcase_mode']:
        return JSONResponse({'detail':'Showcase mode disabled'},403)
    if request.method=='POST':
        if request.cookies.get('showcase_session')!=SESSION:
            return JSONResponse({'detail':'Open the showcase UI first to establish a local session'},403)
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'Cross-origin writes refused'},403)
    return await call_next(request)

@app.get('/')
def index():
    response=FileResponse(ROOT/'index.html');response.set_cookie('showcase_session',SESSION,httponly=True,samesite='strict');return response

@app.get('/api/models')
def models():
    rows=[]
    for name in NAMES+['entity_resolution']:
        model=MODELS.get(name)
        if name=='entity_resolution':
            report={'version':getattr(model,'model_version',None),'provenance':'Existing original artifact loaded read-only. No retraining. Evaluation not recomputed in showcase.','metrics':None,'artifact_path':str(getattr(model,'artifact_path',''))}
        else:
            report=model.report if model else {}
        rows.append({'name':name,'status':'loaded' if model else 'unavailable','error':ERRORS.get(name),**report})
    return {'configuration':configuration(),'models':rows}

class Predict(BaseModel):
    model: str
    record: dict

def predict(name,record):
    if not configuration()['local_ml_enabled']: raise HTTPException(403,'Local ML disabled')
    if name not in MODELS: raise HTTPException(503,'Model unavailable')
    try:
        if name=='entity_resolution':
            if not isinstance(record.get('query'),dict) or not isinstance(record.get('candidates'),list) or len(record['candidates'])>100:
                raise ValueError('Provide query and up to 100 candidates')
            start=time.perf_counter(); result=MODELS[name].predict(record).model_dump(mode='json')
            if result.get('execution_status')=='FAILED': raise ValueError('Existing model inference failed')
            return {'component':'local_ml','model':name,'version':MODELS[name].model_version,'artifact_sha256':hashlib.sha256(__import__('pathlib').Path(MODELS[name].artifact_path).read_bytes()).hexdigest(),'duration_ms':(time.perf_counter()-start)*1000,'input_features':record,'output':result}
        return MODELS[name].predict(record)
    except (ValueError,KeyError,TypeError) as error:
        raise HTTPException(422,'Invalid input: '+str(error))

@app.post('/api/predict')
def inference(req:Predict):
    result=predict(req.model,req.record)
    with database() as db: log(db,'inference',result)
    return result

@app.get('/api/logs')
def logs():
    with database() as db:
        return [dict(row) | {'payload':json.loads(row['payload'])} for row in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]

@app.get('/api/records')
def records():
    with database() as db: return [dict(row)|{'payload':json.loads(row['payload'])} for row in db.execute('SELECT * FROM records')]

class Workflow(BaseModel):
    request: str=Field(min_length=3,max_length=3000)
    analysis: dict=Field(default_factory=dict)

@app.post('/api/workflows')
def workflow(req:Workflow):
    intent=predict('workflow_intent',{'text':req.request})
    route=intent['output']['prediction']
    results=[intent]; identifier=str(uuid.uuid4())
    with database() as db:
        rows=[json.loads(row['payload']) for row in db.execute('SELECT payload FROM records')]
        if 'entity_resolution' in MODELS:
            results.append(predict('entity_resolution',{'query':rows[0],'candidates':rows[1:]}))
        else:
            raise HTTPException(503,'Existing entity-resolution model unavailable; workflow cannot claim matching')
        analysis_model={'invoice_processing':'invoice_discrepancy','payment_approval':'transaction_anomaly','customer_support':'email_classification'}.get(route)
        if analysis_model:
            results.append(predict(analysis_model,req.analysis or ({'text':req.request} if analysis_model=='email_classification' else {})))
        payload={'id':identifier,'state':'AWAITING_APPROVAL','routing':'deterministic mapping of local classifier output; human review required','route':route,'request':req.request,'retrieved_records':rows,'results':results,'operation':'Create isolated simulated enterprise review task; no real payment, email or production update'}
        db.execute('INSERT INTO workflows VALUES (?,?,?)',(identifier,'AWAITING_APPROVAL',json.dumps(payload)))
        log(db,'workflow_prepared',payload)
        return payload

class Decision(BaseModel):
    approve: bool
    reviewer: str=Field(min_length=2,max_length=100)
    reason: str=Field(min_length=3,max_length=1000)

@app.post('/api/workflows/{identifier}/decision')
def decide(identifier:str,req:Decision):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM workflows WHERE id=?',(identifier,)).fetchone()
        if not row: raise HTTPException(404,'Workflow not found')
        if row['state']!='AWAITING_APPROVAL': raise HTTPException(409,'Workflow already decided')
        payload=json.loads(row['payload']); state='COMPLETED' if req.approve else 'REJECTED'
        if req.approve:
            db.execute('INSERT INTO operations VALUES (?,?,?)',(identifier,payload['route'],json.dumps({'simulation':True,'reviewer':req.reviewer,'reason':req.reason})))
        payload.update(state=state,decision=req.model_dump(),simulation=True)
        db.execute('UPDATE workflows SET state=?,payload=? WHERE id=?',(state,json.dumps(payload),identifier));log(db,'workflow_decision',payload)
        return payload

@app.post('/api/external')
def external(req:Workflow):
    result=get_provider().plan(req.request,[])
    with database() as db: log(db,'external_ai',result)
    return result
