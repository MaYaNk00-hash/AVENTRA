import json
import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from showcase import app as server
from showcase.core import ROOT, NAMES, LocalModel, dataset

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('EXTERNAL_AI_ENABLED','false')
    monkeypatch.setenv('LOCAL_ML_ENABLED','true')
    monkeypatch.setattr(server,'DB',str(tmp_path/'audit.sqlite'))
    with TestClient(server.app) as c:
        c.get('/')
        yield c

def test_registry_and_offline_guard(client,monkeypatch):
    import requests
    def forbidden(*a,**k): raise AssertionError('Network forbidden')
    monkeypatch.setattr(requests.Session,'request',forbidden)
    registry=client.get('/api/models').json()
    assert len(registry['models'])==5
    assert all(m['status']=='loaded' for m in registry['models'])
    assert client.post('/api/external',json={'request':'Explain a workflow'}).status_code==403
    for name in NAMES:
        _,test=dataset(name,seed=781)
        response=client.post('/api/predict',json={'model':name,'record':test[0]})
        assert response.status_code==200,response.text
        assert response.json()['component']=='local_ml'
    assert len(client.get('/api/logs').json())==4

def test_end_to_end_real_matching_review_and_persistence(client):
    response=client.post('/api/workflows',json={'request':'Register a new customer account for Helix Instruments'})
    assert response.status_code==200,response.text
    run=response.json();assert run['state']=='AWAITING_APPROVAL'
    assert {r['model'] for r in run['results']}=={'workflow_intent','entity_resolution'}
    with server.database() as db: assert db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]==0
    decision={'approve':True,'reviewer':'Independent judge','reason':'Reviewed actual inference and simulated operation'}
    response=client.post('/api/workflows/'+run['id']+'/decision',json=decision)
    assert response.status_code==200,response.text
    assert response.json()['state']=='COMPLETED'
    assert client.post('/api/workflows/'+run['id']+'/decision',json=decision).status_code==409
    with server.database() as db: assert db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]==1
    assert client.get('/api/logs').json()[0]['kind']=='workflow_decision'

def test_invalid_input_and_origin(client):
    assert client.post('/api/predict',json={'model':'invoice_discrepancy','record':{}}).status_code==422
    assert client.post('/api/predict',headers={'Origin':'https://untrusted.example'},json={'model':'workflow_intent','record':{'text':'test'}}).status_code==403

@pytest.mark.parametrize('text,model', [('Process the supplier invoice','invoice_discrepancy'),('Approve the pending payment','transaction_anomaly')])
def test_analysis_routes_use_real_models(client,text,model):
    _,rows=dataset(model,seed=819)
    response=client.post('/api/workflows',json={'request':text,'analysis':rows[0]})
    assert response.status_code==200,response.text
    assert model in {item['model'] for item in response.json()['results']}

def test_held_out_template_separation():
    for name in ['workflow_intent','email_classification']:
        train,test=dataset(name)
        assert not {x['template_group'] for x in train}&{x['template_group'] for x in test}

def test_original_snapshot_unchanged():
    root=ROOT.parent
    for name,expected in json.loads((ROOT/'original_manifest.json').read_text()).items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
