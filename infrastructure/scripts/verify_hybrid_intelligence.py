"""Repeat real Gemini selection + existing-artifact inference using synthetic inputs.

python infrastructure/scripts/verify_hybrid_intelligence.py
Requires the backend on localhost:8000 and its configured Gemini key.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

import requests

ROOT=Path(__file__).resolve().parents[2]
GOALS={
    "intent_parser":"Classify the supplied prompt using the local intent_parser artifact",
    "workflow_planner":"Inspect the saved workflow_planner template for the supplied intent_type; do not execute its tools",
    "semantic_schema_mapper":"Map the supplied field definitions using the local semantic_schema_mapper classifier",
    "invoice_reconciliation":"Classify the supplied invoice comparison features using the local invoice_reconciliation classifier",
    "adaptation_recommender":"Classify the supplied breaking-change features using the local adaptation_recommender",
    "document_intelligence":"Extract the supplied invoice text and compute the document_intelligence regression score",
    "anomaly_detection":"Analyze the supplied transaction with the local anomaly_detection Isolation Forest",
    "entity_resolution":"Match the supplied business query and candidates using the local entity_resolution artifact",
}


def main():
    cases=json.loads((ROOT/'validation/hybrid_examples.json').read_text(encoding='utf-8'))['examples']
    artifact_paths=list((ROOT/'ml/models').glob('*/artifacts/*.pkl'))
    import hashlib
    before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifact_paths}
    report={'started_at':datetime.now(timezone.utc).isoformat(),'input_provenance':'Synthetic inference examples; not training or evaluation results','checks':[],'artifact_sha256_before':before}
    with requests.Session() as session:
        session.trust_env=False
        base='http://127.0.0.1:8000'
        login=session.post(base+'/api/auth/login',data={'username':os.getenv('AVENTRA_DEMO_USERNAME','admin'),'password':os.getenv('AVENTRA_DEMO_PASSWORD','Password123!')},timeout=10)
        login.raise_for_status();session.headers['Authorization']='Bearer '+login.json()['access_token']
        inventory=session.get(base+'/api/runtime/intelligence/models',timeout=10);inventory.raise_for_status()
        report['inventory']=inventory.json()
        for name,payload in cases.items():
            response=session.post(base+'/api/runtime/runs',json={'goal':GOALS[name],'source_ids':[],'analysis':payload,'planner':'gemini'},timeout=110)
            response.raise_for_status();run=response.json()
            matched=run['status']=='COMPLETED' and run['result'].get('analysis',{}).get('model')==name
            report['checks'].append({'expected_model':name,'passed':matched,'run':run})
            print(json.dumps({'expected_model':name,'passed':matched,'status':run['status'],'local_model':run['result'].get('analysis',{}).get('model'),'duration_ms':run['result'].get('execution',{}).get('duration_ms'),'error':run['result'].get('error')}),flush=True)
    after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifact_paths}
    report['artifacts_unchanged']=before==after
    report['all_checks_passed']=all(check['passed'] for check in report['checks']) and report['artifacts_unchanged']
    destination=ROOT/'validation/results'/('hybrid-live-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.json')
    with destination.open('x',encoding='utf-8') as file:json.dump(report,file,indent=2)
    print('Actual verification report:',destination,flush=True)
    if not report['all_checks_passed']:raise SystemExit('One or more hybrid checks failed; inspect the actual report.')


if __name__=='__main__':main()
