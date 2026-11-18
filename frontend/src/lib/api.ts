/**
 * AVENTRA API Client
 * Connects the frontend to the FastAPI backend services.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchJson(endpoint: string, options: RequestInit = {}) {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const errorText = await res.text();
    let errorDetail = errorText;
    try {
      const parsed = JSON.parse(errorText);
      errorDetail = parsed.detail || errorText;
    } catch {}
    throw new Error(errorDetail || `HTTP error ${res.status}`);
  }

  return res.json();
}

export const api = {
  // Analytics
  getAnalyticsSummary: () => fetchJson("/api/analytics/summary"),

  // Agent
  executeAgentTask: (prompt: string, user_name?: string) =>
    fetchJson("/api/agent/execute", {
      method: "POST",
      body: JSON.stringify({ prompt, user_name: user_name || "Elena Rostova (Compliance Officer)" }),
    }),

  // Workflows
  listWorkflows: () => fetchJson("/api/workflows"),
  listExecutions: () => fetchJson("/api/workflows/executions"),
  getExecution: (id: string) => fetchJson(`/api/workflows/executions/${id}`),
  executeWorkflow: (workflow_id: string, input_data: any) =>
    fetchJson("/api/workflows/execute", {
      method: "POST",
      body: JSON.stringify({ workflow_id, input_data }),
    }),

  // Approvals
  listApprovals: (status?: string) =>
    fetchJson(`/api/approvals${status ? `?status_filter=${status}` : ""}`),
  getApproval: (id: string) => fetchJson(`/api/approvals/${id}`),
  decideApproval: (id: string, decision: "APPROVED" | "REJECTED", comments: string, reviewer_role?: string, reviewer_name?: string) =>
    fetchJson(`/api/approvals/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        comments,
        reviewer_name: reviewer_name || "Elena Rostova",
        reviewer_role: reviewer_role || "COMPLIANCE_OFFICER",
      }),
    }),

  // ML Intelligence
  listModels: () => fetchJson("/api/ml/models"),
  getModel: (id: string) => fetchJson(`/api/ml/models/${id}`),
  predictModel: (id: string, data: any) =>
    fetchJson(`/api/ml/models/${id}/predict`, {
      method: "POST",
      body: JSON.stringify({ data }),
    }),
  evaluateModel: (id: string) =>
    fetchJson(`/api/ml/models/${id}/evaluate`, {
      method: "POST",
    }),
  getModelDependencyGraph: () => fetchJson("/api/ml/dependency-graph"),

  // Data Hub
  listRecords: (system_origin?: string) =>
    fetchJson(`/api/data/records${system_origin ? `?system_origin=${system_origin}` : ""}`),
  createRecord: (record: any) =>
    fetchJson("/api/data/records", {
      method: "POST",
      body: JSON.stringify(record),
    }),
  getSchemas: () => fetchJson("/api/data/schemas"),
  simulateDrift: () => fetchJson("/api/data/drift/simulate", { method: "POST" }),
  alignSchema: (fields: any[]) =>
    fetchJson("/api/data/mappings/align", {
      method: "POST",
      body: JSON.stringify({ fields }),
    }),

  // Enterprise Dynamic Connections
  getConnectionTemplates: () => fetchJson("/api/connections/templates"),
  listConnections: (connector_type?: string, provider?: string) => {
    const params = new URLSearchParams();
    if (connector_type) params.append("connector_type", connector_type);
    if (provider) params.append("provider", provider);
    const qs = params.toString();
    return fetchJson(`/api/connections${qs ? `?${qs}` : ""}`);
  },
  getConnection: (id: string) => fetchJson(`/api/connections/${id}`),
  createConnection: (data: any) =>
    fetchJson("/api/connections", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateConnection: (id: string, data: any) =>
    fetchJson(`/api/connections/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteConnection: (id: string) =>
    fetchJson(`/api/connections/${id}`, {
      method: "DELETE",
    }),
  testConnection: (id: string) =>
    fetchJson(`/api/connections/${id}/test`, {
      method: "POST",
    }),
  testPreflightConnection: (data: any) =>
    fetchJson("/api/connections/test-preflight", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  toggleConnection: (id: string, enabled: boolean) =>
    fetchJson(`/api/connections/${id}/toggle?enabled=${enabled}`, {
      method: "POST",
    }),
  discoverConnectionSchema: (id: string) => fetchJson(`/api/connections/${id}/discover`),

  // Enterprise CRM Integration (Stage 6)
  listCrmAccounts: (adapter = "COMPANY_A_CRM", search?: string, limit = 50, cursor?: string, incremental_since?: string) => {
    const params = new URLSearchParams({ adapter, limit: limit.toString() });
    if (search) params.append("search", search);
    if (cursor) params.append("cursor", cursor);
    if (incremental_since) params.append("incremental_since", incremental_since);
    return fetchJson(`/api/crm/accounts?${params.toString()}`);
  },
  getCrmAccount: (id: string, adapter = "COMPANY_A_CRM") =>
    fetchJson(`/api/crm/accounts/${id}?adapter=${adapter}`),
  createCrmAccount: (data: any) =>
    fetchJson("/api/crm/accounts", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateCrmAccount: (id: string, data: any, adapter = "COMPANY_A_CRM") =>
    fetchJson(`/api/crm/accounts/${id}?adapter=${adapter}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  listCrmContacts: (adapter = "COMPANY_A_CRM", search?: string, limit = 50) => {
    const params = new URLSearchParams({ adapter, limit: limit.toString() });
    if (search) params.append("search", search);
    return fetchJson(`/api/crm/contacts?${params.toString()}`);
  },
  createCrmContact: (data: any) =>
    fetchJson("/api/crm/contacts", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listCrmLeads: (adapter = "COMPANY_A_CRM", search?: string, limit = 50) => {
    const params = new URLSearchParams({ adapter, limit: limit.toString() });
    if (search) params.append("search", search);
    return fetchJson(`/api/crm/leads?${params.toString()}`);
  },
  createCrmLead: (data: any) =>
    fetchJson("/api/crm/leads", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  scanCrmDuplicates: (record: any, threshold = 0.85) =>
    fetchJson("/api/crm/duplicates/scan", {
      method: "POST",
      body: JSON.stringify({ record, threshold }),
    }),
  requestCrmMerge: (data: { execution_id: string; source_record_id: string; target_record_id: string; match_probability: number; proposed_canonical_name: string }) =>
    fetchJson("/api/crm/duplicates/request-merge", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  executeCrmMerge: (data: { approval_id: string; reviewer_name: string; reviewer_role: string; canonical_id?: string }) =>
    fetchJson("/api/crm/duplicates/execute-merge", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  incrementalCrmSync: (watermark: string, adapter = "COMPANY_A_CRM") =>
    fetchJson(`/api/crm/sync/incremental?watermark=${encodeURIComponent(watermark)}&adapter=${adapter}`),

  // Audit Ledger
  getAuditLedger: (limit = 50, offset = 0) =>
    fetchJson(`/api/audit/ledger?limit=${limit}&offset=${offset}`),
  verifyAuditChain: () => fetchJson("/api/audit/verify-chain"),
};

