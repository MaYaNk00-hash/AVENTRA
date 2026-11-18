"""Provision only the local editable sandbox. Never targets a remote client account.

Run after starting ports 8000 and 8100:
    python infrastructure/scripts/prepare_judging.py --approve-local-sandbox
Uses AVENTRA_DEMO_USERNAME/PASSWORD, falling back to the repository's local dev account.
"""
import argparse
import json
import os
import requests

parser=argparse.ArgumentParser()
parser.add_argument("--approve-local-sandbox",action="store_true",required=True)
args=parser.parse_args()
base="http://127.0.0.1:8000"
client="http://127.0.0.1:8100"
session=requests.Session()
session.trust_env=False
login=session.post(base+"/api/auth/login",data={"username":os.getenv("AVENTRA_DEMO_USERNAME","admin"),"password":os.getenv("AVENTRA_DEMO_PASSWORD","Password123!")},timeout=20)
login.raise_for_status()
session.headers["Authorization"]="Bearer "+login.json()["access_token"]


def api(path,body=None):
    response=session.request("GET" if body is None else "POST",base+"/api/runtime"+path,json=body,timeout=60)
    if not response.ok:
        raise RuntimeError(f"{path}: {response.status_code}: {response.text}")
    return response.json()


configurations=[
    ("Local sandbox · CRM","CRM","openapi","/api/customer_accounts","account_ref",{"name":"registered_title","address":"postal_location","country":"nation"},["review_state"]),
    ("Local sandbox · ERP","ERP","openapi","/api/supplier_directory","supplier_number",{"name":"trading_label","address":"office_location","country":"country_code"},["lifecycle"]),
    ("Local sandbox · Operations DB","DATABASE","sqlite","warehouse_orders","order_ticket",{},["fulfillment_state"]),
]
existing=api("/sources")
for name,domain,kind,resource,key,bindings,writable in configurations:
    found=next((source for source in existing if source["name"]==name and source["kind"]==kind),None)
    if found:
        source=api(f"/sources/{found['id']}/rediscover",{})
    else:
        source=api("/sources",{"name":name,"domain":domain,"kind":kind,"base_url":client if kind=="openapi" else "","relative_path":"judging-client.sqlite" if kind=="sqlite" else "","allowed_tables":["warehouse_orders"] if kind=="sqlite" else []})
    # Approval is explicit and limited to this repository's own sample sandbox.
    source=api(f"/sources/{source['id']}/approve",{"schema_sha256":source["schema_sha256"],"resources":{resource:{"key_field":key,"bindings":bindings,"writable_fields":writable}}})
    print(json.dumps({"name":name,"source_id":source["id"],"status":source["status"],"resource":resource}))
print("Ready: http://127.0.0.1:3000/agent | editable client: http://127.0.0.1:8100")
