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

  // Audit Ledger
  getAuditLedger: (limit = 50, offset = 0) =>
    fetchJson(`/api/audit/ledger?limit=${limit}&offset=${offset}`),
  verifyAuditChain: () => fetchJson("/api/audit/verify-chain"),
};

