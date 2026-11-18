# AVENTRA × INDUX (AETL) End-to-End Integration Guide
## Complete Step-by-Step Walkthrough: From Launch to Schema Introspection, Matching & Verification

This document provides the definitive, step-by-step operational guide to launch both platforms, generate API keys, establish enterprise client connections, introspect live schemas, run modular ML matching, and verify results in the cryptographic audit ledger.

---

### Architecture & Port Allocation

| Component | Technology | Default Port | URL / Interface |
| :--- | :--- | :--- | :--- |
| **Indux Web Part (AETL)** | FastAPI + SQLite (WAL) | `8002` | `http://127.0.0.1:8002` (Docs: `/docs`, Edu: `/edu`) |
| **AVENTRA Backend** | FastAPI + SQLAlchemy | `8000` | `http://127.0.0.1:8000` (Docs: `/docs`) |
| **AVENTRA Frontend** | Next.js 14 + React + Tailwind | `3000` | `http://localhost:3000` (`/agent`, `/console`) |

---

## Step 1: Start Indux Web Part (AETL Enterprise Simulator)

1. Open PowerShell and navigate to the Indux directory:
   ```powershell
   cd "c:\Hackathons\Gwalior\Indux part web"
   ```
2. Verify the `.env` configuration:
   ```dotenv
   HOST=127.0.0.1
   PORT=8002
   ```
3. Start the Indux server:
   ```powershell
   python main.py
   ```
4. **Verification**: Open `http://127.0.0.1:8002/health` in your browser. You should see:
   ```json
   {
     "status": "HEALTHY",
     "service": "AETL Enterprise Simulation Ecosystem",
     "version": "2.0.0"
   }
   ```
   Interactive Swagger docs are live at `http://127.0.0.1:8002/docs`.

---

## Step 2: Generate & Retrieve Indux API Keys

Indux authenticates external connectors like AVENTRA using standard enterprise API keys (`aetl_live_...`).

### Method A: Generate via Terminal / cURL
Run this command in PowerShell to mint a new live API key:
```powershell
curl -X POST "http://127.0.0.1:8002/api/v1/api-management/keys" `
  -H "Content-Type: application/json" `
  -d '{\"name\": \"AVENTRA Production Connector\", \"rate_limit_per_minute\": 120, \"expires_in_days\": 90}'
```
**Response Output:**
```json
{
  "success": true,
  "data": {
    "key_id": "key_a94f8102b3",
    "name": "AVENTRA Production Connector",
    "api_key": "aetl_live_pjUgAde4Oa9CIc4qJsJxd6ToRxz5285UPMdSCWiq3Tg",
    "rate_limit_per_minute": 120,
    "permissions": ["*"]
  }
}
```

### Method B: Pre-configured Key
The pre-configured testing key already seeded in your environment is:
```text
aetl_live_pjUgAde4Oa9CIc4qJsJxd6ToRxz5285UPMdSCWiq3Tg
```

---

## Step 3: Start AVENTRA Platform

### 3.1 Start AVENTRA FastAPI Backend
1. Open a new PowerShell terminal:
   ```powershell
   cd "c:\Hackathons\Gwalior\AVENTRA"
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```
2. **Verification**: Open `http://127.0.0.1:8000/docs` to see the AVENTRA Swagger API.

### 3.2 Start AVENTRA Next.js Frontend
1. Open another PowerShell terminal:
   ```powershell
   cd "c:\Hackathons\Gwalior\AVENTRA\frontend"
   npm run dev
   ```
2. **Verification**: Open `http://localhost:3000` in your browser.

---

## Step 4: Connect Indux to AVENTRA

You can connect Indux to AVENTRA in either workspace:

### Workspace 1: Operations Console (`/console?tab=data_hub`)
1. Go to `http://localhost:3000/console?tab=data_hub`.
2. Scroll to **Enterprise Connections** and click **`+ New Connection`**.
3. Fill in the connection wizard:
   * **Connection Name**: `Custom REST CRM Instance`
   * **Connector Type**: `CRM`
   * **Provider**: `custom_crm` (or `rest_custom`)
   * **Base URL**: `![alt text](image.png)`
   * **Authentication**: `API Key`
   * **API Key Value**: `aetl_live_pjUgAde4Oa9CIc4qJsJxd6ToRxz5285UPMdSCWiq3Tg`
4. Click **Run Pre-flight Test** — The status will turn green (`CONNECTED`, latency ~12ms).
5. Click **Save Connection**.

### Workspace 2: Task Workspace (`/agent`)
1. Go to `http://localhost:3000/agent`.
2. Sign in with `admin` / `Password123!`.
3. In the left sidebar, click the **`+`** icon next to **`CLIENT CONNECTIONS`**.
4. Enter:
   * **Connection Name**: `Indux Enterprise AETL`
   * **System Role**: `CRM`
   * **Connection Method**: `Website / OpenAPI API`
   * **Client API Base URL**: `http://127.0.0.1:8002`
   * **OpenAPI Document Path**: `/openapi.json`
   * **Server Credential Reference**: `AVENTRA_CONNECTOR_INDUX_KEY`
5. Click **Discover client capabilities**.

---

## Step 5: Dynamic Schema Introspection & Discovery

Once the connection is active, you can introspect its live schema:

1. In `http://localhost:3000/console?tab=data_hub`, locate **Custom REST CRM Instance**.
2. Click the **Discover Schema** (or eye icon) button.
3. The **Dynamic Schema Introspection** modal pops up showing the introspected structure:

| Field / Table | Data Type | Primary Key | Description |
| :--- | :--- | :--- | :--- |
| **`account_id`** | `string` | <span style="color:#3FB950;font-weight:bold;">PRIMARY KEY</span> | Unique CRM account identifier |
| **`account_name`** | `string` | `-` | Legal business entity name |
| **`industry`** | `string` | `-` | Market classification |
| **`country`** | `string` | `-` | Country code / jurisdiction |
| **`annual_revenue`** | `decimal` | `-` | Reported annual revenue |
| **`contact_email`** | `string` | `-` | Primary account contact email |

### Verifying Programmatically via Terminal
You can verify this exact introspection response via cURL:
```powershell
curl http://127.0.0.1:8000/api/connections/Indux_crm/discover
```

---

## Step 6: Schema Matching & Entity Resolution

AVENTRA applies its modular machine learning models to map schemas and resolve duplicates:

### 6.1 M2: Semantic Schema Mapping
The **M2 Semantic Schema Mapper** maps client field names to AVENTRA canonical models without requiring the client to change their database:
* `account_name` $\rightarrow$ Canonical `business_name`
* `country` $\rightarrow$ Canonical `jurisdiction_iso`
* `annual_revenue` $\rightarrow$ Canonical `reported_revenue_usd`
* `contact_email` $\rightarrow$ Canonical `primary_email`

Test the mapping via Python:
```powershell
python -c "from ml.models.semantic_schema_mapper.inference import SemanticSchemaMapper; mapper = SemanticSchemaMapper(); print(mapper.predict(['account_name', 'annual_revenue', 'contact_email']))"
```

### 6.2 M1: Cross-System Entity Resolution & Deduplication
The **M1 Entity Resolution Model** compares records across different systems (e.g., Company A CRM vs Company B ERP) using LightGBM + Jaro-Winkler string distance:
1. In `http://localhost:3000/console?tab=data_hub`, click **Scan Duplicates** on any record.
2. The model evaluates candidate pairs and returns matching probabilities (e.g. `98.4% match`).
3. Click **Review Candidate** $\rightarrow$ **Merge Records** to generate a golden entity.

Run an automated duplicate scan in the terminal:
```powershell
python -c "from backend.connectors.crm_duplicates import scan_crm_duplicates; dups = scan_crm_duplicates(); print(f'Detected {len(dups)} duplicate clusters across systems.')"
```

---

## Step 7: Verifying via the Cryptographic SHA-256 Audit Ledger

Every single action in AVENTRA is cryptographically hashed and chained to prevent tampering:

1. Open `http://localhost:3000/console?tab=audit_ledger`.
2. Inspect the live block ledger:
   * **`CONNECTION_REGISTERED`**: Logs connection registration with encrypted credentials.
   * **`CONNECTION_TESTED`**: Logs pre-flight health check with latency metrics.
   * **`SCHEMA_DISCOVERED`**: Logs the SHA-256 digest of the introspected schema.
   * **`DUPLICATE_SCANNED`**: Logs M1 model confidence scores.
3. Every block includes:
   * Block Number (e.g., `#372`)
   * Current Hash: `SHA-256(prev_hash + timestamp + actor + payload)`
   * Previous Block Hash (cryptographic chain link)

### Terminal Ledger Verification
Run this command to cryptographically verify the integrity of the audit chain:
```powershell
python -c "from backend.database.session import SessionLocal; from backend.security.audit import verify_audit_ledger_integrity; db = SessionLocal(); valid = verify_audit_ledger_integrity(db); print('Ledger Integrity Valid:', valid)"
```
**Expected Output:**
```text
Ledger Integrity Valid: True
```

---

## Step 8: One-Command Full E2E Verification Script

To test the entire pipeline end-to-end (Health check $\rightarrow$ Key generation $\rightarrow$ Connection test $\rightarrow$ Schema introspection $\rightarrow$ M1 duplicate matching $\rightarrow$ Audit ledger verification), run:

```powershell
python "c:\Hackathons\Gwalior\verify_integration.py"
```

### Expected Output Summary:
```text
[1/6] Testing Indux Web Part (AETL) health on port 8002...
      [OK] Indux is HEALTHY (200 OK)
[2/6] Querying Indux API Key Management & Public CRM/ERP APIs...
      [OK] Created live API key: aetl_live_pjUgAde4Oa9CIc4qJsJxd6ToRxz5285UPMdSCWiq3Tg
      [OK] Retrieved 1 public CRM customers
      [OK] Retrieved 1 public ERP products
[3/6] Testing AVENTRA Backend health on port 8000...
      [OK] AVENTRA preflight to Indux status: CONNECTED (latency: 12.0ms)
[4/6] Registering Indux as an Enterprise Connection in AVENTRA...
      [OK] Registered connection ID: Indux_crm
[5/6] Introspecting live schema via AVENTRA /discover endpoint...
      [OK] Discovered 6 schema fields:
           - account_id (string, PRIMARY KEY)
           - account_name (string)
           - industry (string)
           - country (string)
           - annual_revenue (decimal)
           - contact_email (string)
[6/6] Verifying M1 Entity Resolution duplicate scan & Audit Ledger...
      [OK] M1 scan completed. Found duplicates.
      [OK] SHA-256 Tamper-evident Audit Ledger verified across 372 blocks.

==================================================
ALL END-TO-END INTEGRATION CHECKS PASSED!
==================================================
```
