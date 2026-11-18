import requests

login = requests.post('http://127.0.0.1:8000/api/auth/login', data={'username': 'admin', 'password': 'Password123!'}).json()
token = login['access_token']
headers = {'Authorization': f'Bearer {token}'}

# 1. Verify Gemini Planner
v_resp = requests.post('http://127.0.0.1:8000/api/runtime/planner/verify', headers=headers)
v_data = v_resp.json()
print(f"1. Planner Verify Status: {v_resp.status_code}")
print(f"   Live Verified: {v_data.get('live_connection_verified')}, Reason: {v_data.get('verification_reason')}, Duration: {v_data.get('duration_ms')}ms")

# 2. Get active sources
sources = requests.get('http://127.0.0.1:8000/api/runtime/sources', headers=headers).json()
active_ids = [s['id'] for s in sources if s['status'] == 'ACTIVE']

# 3. Test Gemini Task 'Show first 10 records from companies'
run1 = requests.post('http://127.0.0.1:8000/api/runtime/runs', headers=headers, json={
    'goal': 'Show first 10 records from companies',
    'source_ids': active_ids,
    'planner': 'gemini'
}).json()
print('\n2. Run (Show first 10 records from companies):')
print(f"   Status: {run1.get('status')}")
print(f"   Result Type: {run1.get('result', {}).get('type')}")
print(f"   Records Returned: {run1.get('result', {}).get('returned_count')}")
print(f"   Events: {[e['tool'] for e in run1.get('events', [])]}")

# 4. Test Gemini Task 'Show all records across the connected systems'
run2 = requests.post('http://127.0.0.1:8000/api/runtime/runs', headers=headers, json={
    'goal': 'Show all records across the connected systems',
    'source_ids': active_ids,
    'planner': 'gemini'
}).json()
print('\n3. Run (Show all records across connected systems):')
print(f"   Status: {run2.get('status')}")
print(f"   Result Type: {run2.get('result', {}).get('type')}")
print(f"   Records Returned: {run2.get('result', {}).get('returned_count')}")
print(f"   Events: {[e['tool'] for e in run2.get('events', [])]}")

# 5. Test Enterprise Console agent task
agent_res = requests.post('http://127.0.0.1:8000/api/agent/execute', headers=headers, json={
    'prompt': 'Onboard new customer Apex Global Logistics LLC and deduplicate against ERP database'
}).json()
print('\n4. Enterprise Console /api/agent/execute:')
print(f"   Status: {agent_res.get('status')}")
print(f"   Execution ID: {agent_res.get('execution_id')}")
print(f"   Workflow: {agent_res.get('workflow_id')}")

