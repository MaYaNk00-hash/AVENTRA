export type ScenarioId = "customer" | "invoice" | "schema" | "anomaly";
export type RunStatus = "RUNNING" | "AWAITING_APPROVAL" | "COMPLETED" | "REJECTED" | "FAILED";
export type Run = {
  id: string; prompt: string; scenario: ScenarioId; source: "demo" | "live";
  status: RunStatus; step: number; createdAt: string; summary?: string;
  approvalId?: string; evidence?: unknown; notes?: string;
  events?: { component: string; message: string; event_type: string }[];
};
export type AuditBlock = { id: string; timestamp: string; action: string; runId: string; actor: string; notes: string; previousHash: string; hash: string };
export type Model = { id: string; code: string; name: string; category: string; algorithm: string; description: string; metric: string; score: string; version: string; sample: Record<string, unknown> };

// Reported repository metrics, not live evaluations. Presets follow model input contracts.
export const MODELS: Model[] = [
  { id: "entity_resolution", code: "M1", name: "Entity resolution", category: "Matching", algorithm: "LightGBM · 16 pairwise features", description: "Find duplicate businesses across CRM and ERP records using lexical and address features. Sensitive matches require human review.", metric: "Held-out precision", score: "91.5%", version: "1.2.0", sample: { query: { entity_id: "CRM-A-101", business_name: "Apex Global Logistics LLC", business_address: "742 Evergreen Terrace, Springfield, IL", country: "US" }, candidates: [{ entity_id: "ERP-B-501", business_name: "Apex Global Logistics Inc", business_address: "742 Evergreen Terr, Springfield, IL", country: "US" }] } },
  { id: "semantic_schema_mapper", code: "M2", name: "Semantic schema mapper", category: "Data intelligence", algorithm: "Character n-gram TF-IDF + reranker", description: "Align source fields with canonical concepts, enforce datatype compatibility, and flag uncertain mappings for review.", metric: "Reported top-1 accuracy", score: "94.1%", version: "1.1.0", sample: { fields: [{ field_name: "billing_address", datatype: "string", description: "Customer billing street address", sample_values: ["742 Evergreen Terrace"] }] } },
  { id: "intent_parser", code: "M3", name: "Typed intent parser", category: "Understanding", algorithm: "Guarded keyword and intent extraction", description: "Turn natural language into typed READ or WRITE intents and detect prompt injection patterns before planning.", metric: "Reported intent accuracy", score: "96.5%", version: "1.0.0", sample: { prompt: "Onboard new customer Apex Global Logistics LLC and resolve duplicates" } },
  { id: "workflow_planner", code: "M4", name: "Workflow planner", category: "Orchestration", algorithm: "NetworkX DAG + tool allowlist", description: "Build a cycle-free execution plan with approved tools, explicit dependencies, and mandatory approval gates.", metric: "Reported valid plan rate", score: "99.2%", version: "1.0.0", sample: { intent_type: "ONBOARD_CUSTOMER", action_type: "WRITE", target_systems: ["CRM", "ERP"] } },
  { id: "invoice_reconciliation", code: "M5", name: "Invoice reconciliation", category: "Finance", algorithm: "Deterministic three-way matching", description: "Compare invoice, purchase order, and goods receipt. Enforce price, quantity, tax, and financial variance tolerances.", metric: "Reported reconciliation accuracy", score: "99.7%", version: "1.0.0", sample: { invoice: { invoice_number: "INV-7729", po_number: "PO-4401", vendor_id: "V-1", invoice_date: "2026-11-02", subtotal: 1000, tax_amount: 0, total_amount: 1000, line_items: [] }, purchase_order: { po_number: "PO-4401", vendor_id: "V-1", total_amount: 1000, line_items: [] } } },
  { id: "adaptation_recommender", code: "M6", name: "Adaptation recommender", category: "Governance", algorithm: "Schema diff + dependency impact analysis", description: "Detect schema drift and propose a versioned migration. Recommendations never authorize production changes.", metric: "Reported drift recall", score: "98.5%", version: "1.0.0", sample: { old_schema: { system_name: "CRM", version: "1.0", fields: [{ name: "customer_name", datatype: "string" }] }, new_schema: { system_name: "CRM", version: "1.1", fields: [{ name: "legal_name", datatype: "string" }] }, active_workflows: [] } },
  { id: "document_intelligence", code: "M7", name: "Document intelligence", category: "Extraction", algorithm: "Regex and token extraction + normalization", description: "Extract invoice identifiers, dates, totals, taxes, and line items from raw document text into a structured schema.", metric: "Reported field-level F1", score: "94.2%", version: "1.0.0", sample: { document_text: "Invoice No: INV-7729\nPO No: PO-4401\nDate: 2026-11-02\nSubtotal: $1,000.00\nTax: $0.00\nTotal: $1,000.00" } },
  { id: "anomaly_detection", code: "M8", name: "Anomaly detection", category: "Risk", algorithm: "Isolation Forest + business rules", description: "Score financial transactions against behavioral baselines and enterprise rules. Escalate high-risk outliers.", metric: "Reported precision", score: "93.4%", version: "1.0.0", sample: { transaction_id: "TX-1024", vendor_id: "V-1", amount: 15000, historical_avg_amount: 1000, historical_std_amount: 200, vendor_age_days: 5, transactions_last_24h: 12, is_weekend: false } },
];

export const SCENARIOS: Record<ScenarioId, { title: string; subtitle: string; prompt: string; tag: string; models: string[]; steps: string[]; summary: string; evidence: [string, string, string][]; decision: string }> = {
  customer: { title: "Onboard a customer", subtitle: "Find the match. Keep the trust.", prompt: "Onboard Apex Global Logistics LLC and check for duplicates in the ERP", tag: "CRM + ERP", models: ["M3", "M4", "M1"], steps: ["Understand the request", "Build a governed workflow", "Compare CRM and ERP records", "Review the matching evidence"], summary: "I found a potential duplicate for Apex Global Logistics. Review the matching records before creating a canonical link.", evidence: [["Business name", "Apex Global Logistics LLC", "Apex Global Logistics Inc"], ["Address", "742 Evergreen Terrace, Springfield", "742 Evergreen Terr, Springfield"], ["Tax identifier", "US-EIN-8829104", "US-EIN-8829104"]], decision: "Authorize record linkage" },
  invoice: { title: "Reconcile an invoice", subtitle: "Three sources. One clear answer.", prompt: "Reconcile invoice INV-7729 against PO-4401 and its goods receipt", tag: "FINANCE", models: ["M3", "M4", "M7", "M5", "M8"], steps: ["Understand the finance request", "Extract invoice fields", "Match invoice, PO, and receipt", "Check variance and financial risk"], summary: "The sample invoice has a $240 variance against its purchase order. This exceeds the configured tolerance and needs a reviewer before proceeding.", evidence: [["Reference", "INV-7729", "PO-4401 / GR-4401"], ["Total amount", "$12,240.00", "$12,000.00"], ["Received quantity", "102 units billed", "100 units received"]], decision: "Approve variance exception" },
  schema: { title: "Understand schema drift", subtitle: "Change happens. Stay a step ahead.", prompt: "Analyze schema drift between the CRM and our canonical data model", tag: "DATA QUALITY", models: ["M3", "M4", "M2", "M6"], steps: ["Inspect the source schema", "Align canonical field mappings", "Analyze downstream impact", "Prepare a migration proposal"], summary: "The sample CRM schema contains a renamed field and a datatype change. I prepared a migration proposal for review; no production schema is changed.", evidence: [["Customer field", "customer_name · string", "legal_name · string"], ["Amount field", "total_amount · float", "total_amount · decimal"], ["Impacted workflow", "Customer onboarding", "Mapping review required"]], decision: "Approve migration proposal" },
  anomaly: { title: "Investigate anomalies", subtitle: "Turn unusual activity into insight.", prompt: "Investigate unusual supplier transactions and highlight financial risks", tag: "RISK & TRUST", models: ["M3", "M4", "M8"], steps: ["Understand the risk request", "Retrieve sample transaction history", "Score behavioral outliers", "Prepare the risk review"], summary: "The sample transaction is 15× its vendor’s historical average and the vendor is only 5 days old. The high-risk activity is held for investigation.", evidence: [["Transaction amount", "$15,000.00", "$1,000.00 historical average"], ["Vendor age", "5 days", "New-vendor risk"], ["Transaction velocity", "12 in the last 24 hours", "Elevated activity"]], decision: "Acknowledge risk review" },
};

export function classifyPrompt(prompt: string): ScenarioId | null {
  if (/schema|drift|mapping|canonical.*field/i.test(prompt)) return "schema";
  if (/anomal|unusual|outlier|risk.*transaction/i.test(prompt)) return "anomaly";
  if (/invoice|reconcil|purchase order|receipt/i.test(prompt)) return "invoice";
  if (/customer|onboard|duplicate|deduplicat|record.*link|apex/i.test(prompt)) return "customer";
  return null;
}

export async function request<T = unknown>(endpoint: string, body?: unknown): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const response = await fetch(`${base}${endpoint}`, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(20000) });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail === "string" ? error.detail : `Request failed (${response.status})`);
  }
  return response.json();
}

export async function hashBlock(block: Omit<AuditBlock, "hash">): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(block)));
  return Array.from(new Uint8Array(digest)).map(value => value.toString(16).padStart(2, "0")).join("");
}

export function downloadJson(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url);
}
