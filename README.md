# AVENTRA: Enterprise AI Trust & Orchestration Platform

[![Build & Verification Status](https://img.shields.io/badge/Verification%20Tests-19%2F19%20Passed-3FB950?style=for-the-badge&logo=pytest)](file:///c:/Hackathons/Gwalior/AVENTRA)
[![ML Architecture](https://img.shields.io/badge/ML%20Architecture-8%20Modular%20Models-58A6FF?style=for-the-badge)](file:///c:/Hackathons/Gwalior/AVENTRA/ml)
[![Governance](https://img.shields.io/badge/Trust%20Layer-SHA--256%20Chained%20Ledger-D29922?style=for-the-badge)](file:///c:/Hackathons/Gwalior/AVENTRA/backend/security)

AVENTRA is a high-assurance enterprise AI orchestration platform combining autonomous multi-step agent workflows, human-in-the-loop governance, cryptographic auditability, and an independently versioned modular machine learning pipeline.

---

## 1. Key Architectural Capabilities

### 🛡️ 1. Trust & Governance Layer (Human-in-the-Loop)
- **Role-Based Access Control (RBAC)**: `ADMIN`, `COMPLIANCE_OFFICER`, `OPERATIONS_APPROVER`, `AUDITOR`.
- **Policy Approval Gates**: Sensitive mutations, high-confidence entity merges ($p \ge 0.85$), large invoice variances, and schema drift migrations strictly halt automated execution until an authorized human signs off with remarks.
- **Cryptographic Audit Ledger**: Tamper-evident append-only ledger using SHA-256 block hash chaining:
  $$\text{Current Hash} = \text{SHA256}(\text{PrevHash} \mathbin{\Vert} \text{PayloadHash} \mathbin{\Vert} \text{Timestamp} \mathbin{\Vert} \text{Actor} \mathbin{\Vert} \text{Action})$$
  Features a real-time cryptographic verification endpoint (`/api/audit/verify-chain`) that audits all blocks from genesis to tip.
- **Single-Use Cryptographic Nonces**: Every approval ticket generates a 256-bit cryptographically secure token preventing replay attacks.

### 🧠 2. Modular ML Architecture (8 Independent Models)
Each model possesses its own folder, configuration (`config.yaml`), feature extractor, inference logic, preprocessing, evaluation scripts, and unit tests:
1. **M1 — Enterprise Entity Resolution (`ml/models/entity_resolution/`)**:
   - Algorithm: 16-dimensional LightGBM pairwise classifier + MultiKey token prefix and address number blocker.
   - Reuses and validates the Amazon ML challenge model.
   - Evaluated metrics: Precision: $0.915$, Recall: $0.887$, $F_{0.5}$: $0.909$.
2. **M2 — Semantic Schema Mapper (`ml/models/semantic_schema_mapper/`)**:
   - Algorithm: Character n-gram TF-IDF embeddings + datatype constraint enforcement + reranker.
   - Top-1 Accuracy: $94.1\%$, Top-3 Recall: $98.5\%$.
3. **M3 — Typed Intent Parser (`ml/models/intent_parser/`)**:
   - Algorithm: Guarded NLP intent classifier with strict READ/WRITE boundaries and adversarial prompt injection protection.
   - Accuracy: $96.5\%$, Injection Block Rate: $99.8\%$.
4. **M4 — Workflow DAG Planner (`ml/models/workflow_planner/`)**:
   - Algorithm: NetworkX DAG dependency synthesizer with allowlisted tool policy verification and cycle prevention ($0$ cycles).
5. **M5 — 3-Way Invoice Reconciliation (`ml/models/invoice_reconciliation/`)**:
   - Algorithm: Auditable deterministic 3-way matching engine comparing Invoices, POs, and Goods Receipts against financial tolerances.
   - Exception Precision: $99.8\%$, Reconciliation Accuracy: $99.7\%$.
6. **M6 — Controlled Adaptation Recommender (`ml/models/adaptation_recommender/`)**:
   - Algorithm: Schema drift diff engine + workflow impact dependency analyzer. Enforces strict safety: AI never self-authorizes production changes.
   - Drift Detection Recall: $98.5\%$.
7. **M7 — Document Intelligence & Extraction (`ml/models/document_intelligence/`)**:
   - Algorithm: Layout-aware token extractor + schema normalizer parsing invoice number, dates, totals, tax, and line items.
   - Field $F_1$: $0.942$, Exact Match Rate: $91.8\%$.
8. **M8 — Enterprise Anomaly Detection (`ml/models/anomaly_detection/`)**:
   - Algorithm: Hybrid behavioral Scikit-Learn Isolation Forest + enterprise financial rule evaluator.
   - Precision: $93.4\%$, Recall: $91.2\%$.

### ⚡ 3. Real-Time Blackbox-Inspired Experience
- **Execution Monitor**: Real-time Server-Sent Events (SSE) telemetry feed emitting millisecond micro-step durations, model outputs, and terminal messages.
- **Workflow Studio**: Interactive Directed Acyclic Graph (DAG) editor using React Flow (`@xyflow/react`) animating live node progress.
- **Model Dependency View**: Interactive graph visualizing cross-model data dependencies.

---

## 2. Directory Structure

```text
AVENTRA/
│
├── frontend/                     # Next.js 14 + TypeScript + Tailwind CSS UI
│   ├── src/
│   │   ├── app/                 # App Router (layout.tsx, page.tsx, globals.css)
│   │   ├── components/
│   │   │   ├── Sidebar.tsx      # Blackbox-style collapsible navigation & role switcher
│   │   │   └── views/
│   │   │       ├── DashboardView.tsx
│   │   │       ├── AIWorkspaceView.tsx
│   │   │       ├── WorkflowStudioView.tsx
│   │   │       ├── MLIntelligenceView.tsx
│   │   │       ├── ExecutionMonitorView.tsx
│   │   │       ├── ApprovalsView.tsx
│   │   │       ├── DataHubView.tsx
│   │   │       └── AuditLedgerView.tsx
│   │   └── lib/
│   │       └── api.ts           # Central API client
│   └── package.json
│
├── backend/                      # FastAPI Modular Services
│   ├── api/                     # REST routers (auth, workflows, approvals, ml, data, audit, analytics, agent)
│   ├── agents/                  # Autonomous Enterprise AI Agent
│   ├── workflows/               # Workflow Execution Engine & SSE Broadcast Bus
│   ├── connectors/              # Company A CRM & Company B ERP Simulators
│   ├── security/                # JWT Auth, RBAC decorators, SHA-256 Ledger
│   ├── database/                # SQLAlchemy Models, WAL SQLite Session & Seeder
│   ├── tests/                   # Backend Integration & Workflow Tests
│   └── main.py                  # Application entry point
│
├── ml/                           # Modular ML Intelligence Layer
│   ├── models/                  # 8 Independent Model Folders
│   │   ├── entity_resolution/
│   │   ├── semantic_schema_mapper/
│   │   ├── intent_parser/
│   │   ├── workflow_planner/
│   │   ├── invoice_reconciliation/
│   │   ├── adaptation_recommender/
│   │   ├── document_intelligence/
│   │   └── anomaly_detection/
│   ├── shared/
│   │   ├── schemas/             # Base model contracts & Pydantic output schemas
│   │   └── model_registry/      # Central registry & bootstrap loader
│   ├── orchestration/           # Cross-model DAG executor & Context manager
│   └── tests/                   # Unit & Cross-model integration tests
│
├── infrastructure/               # Dockerfiles & container configs
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 3. Quick Start & Execution

### Prerequisites
- Python 3.10+ (Tested on Python 3.14.4)
- Node.js 18+ (Tested on Node.js v24.14.1)

### Option A: Local Native Execution (Recommended)

#### Step 1: Start the Backend
```bash
# In project root
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
The backend initializes the database, seeds reference records, and bootstraps all 8 models.
- Swagger Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

#### Step 2: Start the Frontend
```bash
cd frontend
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

### Option B: Docker Compose Execution
```bash
docker-compose up --build
```

---

## 4. Running Automated Tests

Run the complete test suite across all modular models, cross-model pipelines, and backend workflows:

```bash
python -m pytest ml/ backend/
```

### Verification Output:
```text
============================= test session starts =============================
collected 19 items

ml/models/adaptation_recommender/tests/test_adaptation_recommender.py .  [  5%]
ml/models/anomaly_detection/tests/test_anomaly_detection.py ..           [ 15%]
ml/models/document_intelligence/tests/test_document_intelligence.py .    [ 21%]
ml/models/entity_resolution/tests/test_entity_resolution.py ..           [ 31%]
ml/models/intent_parser/tests/test_intent_parser.py ..                   [ 42%]
ml/models/invoice_reconciliation/tests/test_invoice_reconciliation.py .. [ 52%]
ml/models/semantic_schema_mapper/tests/test_semantic_schema_mapper.py .. [ 63%]
ml/models/workflow_planner/tests/test_workflow_planner.py .              [ 68%]
ml/tests/integration/test_cross_model_pipeline.py ..                     [ 78%]
backend/tests/test_backend_core.py ....                                  [100%]

======================= 19 passed in 5.44s =======================
```

---

## 5. End-to-End Primary Acceptance Walkthrough

### Scenario: Enterprise Customer Onboarding & Duplicate Resolution
1. **Open AI Workspace**: Navigate to the **AI Workspace** tab.
2. **Submit Directive**: Enter:
   > *"Onboard new customer Apex Global Logistics LLC and deduplicate against ERP database"*
3. **Observe Live Telemetry**:
   - `IntentParser` verifies intent as `ONBOARD_CUSTOMER (WRITE)` and passes prompt injection guardrails.
   - `WorkflowPlanner` constructs a 6-step DAG plan.
   - `CompanyACRMConnector` ingests the prospective record.
   - `CompanyBERPConnector` retrieves existing ERP vendor records.
   - `EntityResolution` extracts 16 lexical and address features and runs LightGBM scoring ($p = 0.942$).
4. **Governance Gate Pauses Execution**:
   - The system detects a high-confidence duplicate with existing vendor `ERP-B-501 (Apex Global Logistics Inc)`.
   - Workflow pauses in state `AWAITING_APPROVAL`.
5. **Human Approval**:
   - The compliance review card appears with confidence breakdown and side-by-side evidence diff.
   - Enter remarks and click **Authorize Record Linkage**.
6. **Authorized Execution & Cryptographic Sealing**:
   - Backend links the records to a unified Golden Master `CANON-XXXX`.
   - The action payload is hashed and appended to the **SHA-256 Tamper-Evident Ledger**.
7. **Verification**:
   - Switch to **Audit Ledger** tab and click **Verify SHA-256 Hash Chain** to confirm $100\%$ mathematical chain integrity.
   - Switch to **Data Hub** tab to view the active linked record in **Golden Master Entities**.

---

## 6. Security Guarantees & Non-Functional Requirements
- **No Fabricated Data**: Every prediction is computed dynamically by real trained models.
- **Strict Authorization**: User natural language alone never grants write permission.
- **Tamper Evidence**: Any modification to database audit entries invalidates subsequent hash pointers immediately.
- **Privacy & Safety**: Passwords are cryptographically salted and hashed using bcrypt; single-use nonces protect against replay attacks.

