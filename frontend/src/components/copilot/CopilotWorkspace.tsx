"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowDownToLine, ArrowRight, ArrowUp, AudioLines, Bell, BookOpen, Boxes, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Database, FileCheck2, FileText, GitBranch, Layers3, Link2, Loader2, LockKeyhole, Menu, MessageSquare, MoreHorizontal, Network, Plus, Search, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, Workflow, X, Zap } from "lucide-react";
import { AuditBlock, Model, MODELS, Run, SCENARIOS, ScenarioId, classifyPrompt, downloadJson, hashBlock, request } from "./data";

type Tab = "workspace" | "workflows" | "models" | "connections" | "approvals" | "audit";
type Mode = "demo" | "live";
type LiveConnection = { id: string; name?: string; display_name?: string; provider?: string; connector_type?: string; enabled?: boolean; status?: string };
const NAV = [
  { id: "workspace", label: "AI workspace", icon: Sparkles },
  { id: "workflows", label: "Workflows", icon: Workflow },
  { id: "models", label: "Model library", icon: Boxes },
  { id: "connections", label: "Connections", icon: Link2 },
  { id: "approvals", label: "Approvals", icon: ShieldCheck },
  { id: "audit", label: "Audit trail", icon: FileCheck2 },
] as const;
const SCENARIO_ICONS = { customer: Network, invoice: FileText, schema: Layers3, anomaly: ShieldCheck };
const DEMO_CONNECTIONS = [
  { id: "crm", name: "Company A CRM", provider: "Customer relationships", icon: "C", color: "blue" },
  { id: "erp", name: "Company B ERP", provider: "Vendors, invoices & orders", icon: "E", color: "purple" },
  { id: "database", name: "Enterprise database", provider: "Canonical records & schemas", icon: "D", color: "green" },
];
const STORAGE_KEY = "aventra-copilot-v1";
const LABELS: Record<Run["status"], string> = { RUNNING: "In progress", AWAITING_APPROVAL: "Needs review", COMPLETED: "Completed", REJECTED: "Declined", FAILED: "Stopped" };

function Brand({ small = false }: { small?: boolean }) {
  return <span className={`aventra-mark ${small ? "small" : ""}`} aria-hidden="true"><span /><span /><span /><span /></span>;
}

function Status({ status }: { status: Run["status"] }) {
  return <span className={`status status-${status.toLowerCase()}`}><i />{LABELS[status]}</span>;
}

function Dialog({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    return () => previous?.focus();
  }, []);
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={panel} tabIndex={-1} className={`dialog ${wide ? "dialog-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title} onKeyDown={event => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") {
        const focusable = panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input, textarea, select, a[href]');
        if (!focusable?.length) return;
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) { event.preventDefault(); first.focus(); }
      }
    }}>
      <div className="dialog-heading"><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={19} /></button></div>
      {children}
    </div>
  </div>;
}

function ModelDetail({ model, onClose }: { model: Model; onClose: () => void }) {
  const [input, setInput] = useState(JSON.stringify(model.sample, null, 2));
  const [output, setOutput] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function predict() {
    setError(""); setOutput(null); setBusy(true);
    try {
      const payload = JSON.parse(input);
      const result = await request<{ execution_status: string; error_details?: string }>(`/api/ml/models/${model.id}/predict`, { data: payload });
      if (result.execution_status === "FAILED") throw new Error(result.error_details || "Model inference failed");
      setOutput(JSON.stringify(result, null, 2));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Inference unavailable"); }
    finally { setBusy(false); }
  }
  return <Dialog title={model.name} onClose={onClose} wide>
    <div className="model-detail-intro"><span className="model-code">{model.code}</span><span>{model.algorithm}<br /><small>v{model.version} · {model.category}</small></span><strong>{model.score}<small>{model.metric}</small></strong></div>
    <p className="muted">{model.description}</p>
    <div className="notice"><Database size={16} />Live inference sends this input to your configured FastAPI backend. The metric above is reported in the repository.</div>
    <label className="field-label" htmlFor="model-input">Model input · JSON</label>
    <textarea id="model-input" className="json-editor" value={input} onChange={event => setInput(event.target.value)} spellCheck={false} />
    {error && <p className="inline-error" role="alert">{error}. Check that the backend is running and the input matches the model contract.</p>}
    {output && <><div className="section-caption">LIVE MODEL OUTPUT</div><pre className="json-output">{output}</pre></>}
    <div className="dialog-actions"><button className="secondary-button" onClick={() => setInput(JSON.stringify(model.sample, null, 2))}>Reset example</button><button className="primary-button" disabled={busy} onClick={predict}>{busy ? <Loader2 size={16} className="spin" /> : <Zap size={16} />}Run live inference</button></div>
  </Dialog>;
}

export default function CopilotWorkspace() {
  const [tab, setTab] = useState<Tab>("workspace");
  const [mode, setMode] = useState<Mode>("demo");
  const [runs, setRuns] = useState<Run[]>([]);
  const [blocks, setBlocks] = useState<AuditBlock[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [ready, setReady] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [dialog, setDialog] = useState<"search" | "guide" | "settings" | "review" | null>(null);
  const [search, setSearch] = useState("");
  const [model, setModel] = useState<Model | null>(null);
  const [notice, setNotice] = useState("");
  const [notes, setNotes] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [enabled, setEnabled] = useState(["crm", "erp", "database"]);
  const [liveConnections, setLiveConnections] = useState<LiveConnection[]>([]);
  const [liveLedger, setLiveLedger] = useState<unknown[]>([]);
  const [resourceError, setResourceError] = useState("");
  const [loadingResource, setLoadingResource] = useState(false);
  const [verification, setVerification] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [backendState, setBackendState] = useState<"unknown" | "online" | "offline">("unknown");
  const [workflow, setWorkflow] = useState<ScenarioId>("customer");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const submitLock = useRef(false);
  const decisionLock = useRef(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const selected = runs.find(run => run.id === selectedId);
  const visibleRuns = runs.filter(run => run.source === mode);
  const pending = visibleRuns.filter(run => run.status === "AWAITING_APPROVAL");
  const running = runs.some(run => run.status === "RUNNING") || submitting;

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      if (saved && Array.isArray(saved.runs) && Array.isArray(saved.blocks)) {
        setRuns(saved.runs.filter((run: Run) => SCENARIOS[run.scenario] && typeof run.id === "string" && typeof run.prompt === "string").map((run: Run) => run.status === "RUNNING" && run.source === "demo" ? { ...run, status: "FAILED", summary: "This demo was interrupted by a page reload. Start a new run to replay it." } : run));
        setBlocks(saved.blocks);
      }
    } catch { /* A fresh workspace is usable when browser storage is unavailable. */ }
    setReady(true);
  }, []);
  useEffect(() => {
    if (ready) try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ runs: runs.slice(0, 60), blocks })); } catch { /* In-memory sessions remain usable. */ }
  }, [runs, blocks, ready]);
  useEffect(() => {
    const timer = setInterval(() => setRuns(previous => previous.some(run => run.source === "demo" && run.status === "RUNNING") ? previous.map(run => run.source === "demo" && run.status === "RUNNING" ? { ...run, step: Math.min(run.step + 1, 4), ...(run.step >= 3 ? { status: "AWAITING_APPROVAL" as const, summary: SCENARIOS[run.scenario].summary } : {}) } : run) : previous), 950);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "k") { event.preventDefault(); setSearch(""); setDialog("search"); }
      if (event.altKey && event.key.toLowerCase() === "n") { event.preventDefault(); setTab("workspace"); setSelectedId(null); setPrompt(""); inputRef.current?.focus(); }
    };
    window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(() => { if (selectedId) endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [selectedId, selected?.status]);

  const refreshLiveRun = useCallback(async (id: string) => {
    const result = await request<{ status: string; execution_events: Run["events"]; output_data: unknown; error_details?: string }>(`/api/workflows/executions/${id}`);
    const approvals = result.status === "AWAITING_APPROVAL" ? await request<{ id: string; execution_id: string; evidence: unknown }[]>("/api/approvals?status_filter=PENDING") : [];
    const approval = approvals.find(item => item.execution_id === id);
    const statuses = ["RUNNING", "AWAITING_APPROVAL", "COMPLETED", "REJECTED", "FAILED"];
    setRuns(previous => previous.map(run => run.id !== id ? run : { ...run, status: statuses.includes(result.status) ? result.status as Run["status"] : "FAILED", step: result.status === "RUNNING" ? 1 : 4, events: result.execution_events, approvalId: approval?.id, evidence: approval?.evidence ?? result.output_data, summary: result.error_details || (result.status === "AWAITING_APPROVAL" ? "The backend paused this workflow for human review. Inspect the live evidence below before deciding." : result.status === "COMPLETED" ? "The backend reports this workflow as completed. Its output is available below." : `Backend status: ${result.status}`) }));
  }, []);
  const liveRunningIds = runs.filter(run => run.source === "live" && run.status === "RUNNING").map(run => run.id).join(",");
  useEffect(() => {
    if (!liveRunningIds) return;
    let polling = false;
    const timer = setInterval(async () => {
      if (polling) return; polling = true;
      try { for (const id of liveRunningIds.split(",")) await refreshLiveRun(id); }
      catch { setNotice("Live updates are unavailable. Check the backend connection, then refresh the page to reconnect."); }
      finally { polling = false; }
    }, 1800);
    return () => clearInterval(timer);
  }, [liveRunningIds, refreshLiveRun]);

  useEffect(() => {
    if (mode !== "live") return;
    let disposed = false;
    request("/api/health").then(() => { if (!disposed) setBackendState("online"); }).catch(() => { if (!disposed) setBackendState("offline"); });
    return () => { disposed = true; };
  }, [mode]);
  useEffect(() => {
    setResourceError(""); setVerification("");
    if (mode !== "live" || !["connections", "audit"].includes(tab)) return;
    let disposed = false; setLoadingResource(true);
    const load = tab === "connections" ? request<LiveConnection[]>("/api/connections").then(setLiveConnections) : request<{ entries: unknown[] }>("/api/audit/ledger").then(result => setLiveLedger(result.entries));
    load.catch(error => { if (!disposed) setResourceError(error.message || "Backend unavailable"); }).finally(() => { if (!disposed) setLoadingResource(false); });
    return () => { disposed = true; };
  }, [mode, tab]);

  function navigate(next: Tab) { setTab(next); setMobileNav(false); setNotice(""); }
  function newChat() { navigate("workspace"); setSelectedId(null); setPrompt(""); setTimeout(() => inputRef.current?.focus(), 40); }
  function openRun(run: Run) { setMode(run.source); setSelectedId(run.id); navigate("workspace"); setDialog(null); }
  function changeMode(next: Mode) { setMode(next); setSelectedId(null); setNotice(""); }

  async function startTask(text = prompt, forcedScenario?: ScenarioId) {
    if (!text.trim() || submitLock.current || running) return;
    const scenario = forcedScenario || classifyPrompt(text);
    if (!scenario) { setNotice("Try a customer onboarding, invoice, schema drift, or transaction risk request. This prototype supports those four business workflows."); return; }
    if (mode === "live" && scenario !== "customer") { setNotice("The current backend agent executes customer onboarding only. Use the model library to run this model directly, or switch to demo mode for the complete workflow walkthrough."); return; }
    if (mode === "demo" && enabled.length < 3) { setNotice("Reconnect all three sample sources in Connections before running a demo workflow."); return; }
    submitLock.current = true; setSubmitting(true); setNotice("");
    try {
      let id: string = crypto.randomUUID();
      if (mode === "live") {
        const response = await request<{ execution_id: string; status: string; message?: string }>("/api/agent/execute", { prompt: text, user_name: "Elena Rostova (Compliance Officer)" });
        if (response.status === "SECURITY_VIOLATION") throw new Error(response.message || "Request blocked by backend guardrails");
        if (!response.execution_id) throw new Error("The backend did not return an execution ID");
        id = response.execution_id; setBackendState("online");
      }
      const run: Run = { id, scenario, source: mode, prompt: text.trim(), step: 0, status: "RUNNING", createdAt: new Date().toISOString() };
      setRuns(previous => [run, ...previous]); setSelectedId(id); setPrompt(""); navigate("workspace");
      if (mode === "live") await refreshLiveRun(id);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not start the workflow"); }
    finally { submitLock.current = false; setSubmitting(false); }
  }

  async function decide(approved: boolean) {
    if (!selected || decisionLock.current || notes.trim().length < 3) return;
    decisionLock.current = true; setDeciding(true);
    try {
      if (selected.source === "live") {
        if (!selected.approvalId) throw new Error("No live approval ticket is available. Refresh the execution before deciding.");
        await request(`/api/approvals/${selected.approvalId}/decide`, { decision: approved ? "APPROVED" : "REJECTED", comments: notes.trim(), reviewer_name: "Elena Rostova", reviewer_role: "COMPLIANCE_OFFICER" });
        await refreshLiveRun(selected.id);
      } else {
        const block = { id: crypto.randomUUID(), timestamp: new Date().toISOString(), action: approved ? "REVIEW_APPROVED" : "REVIEW_REJECTED", runId: selected.id, actor: "Elena Rostova · demo reviewer", notes: notes.trim(), previousHash: blocks.at(-1)?.hash || "0".repeat(64) };
        const hash = await hashBlock(block);
        setBlocks(previous => [...previous, { ...block, hash }]);
        setRuns(previous => previous.map(run => run.id !== selected.id ? run : { ...run, status: approved ? "COMPLETED" : "REJECTED", notes: notes.trim(), summary: approved ? "Review approved. The demo workflow is complete and your decision is recorded in the local SHA-256 audit chain. Enterprise systems were not changed." : "Review declined. The proposed action was stopped and your decision is recorded in the local audit chain." }));
      }
      setDialog(null); setNotes(""); setVerification("");
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not save the review"); }
    finally { decisionLock.current = false; setDeciding(false); }
  }

  async function verify() {
    setVerifying(true); setVerification("");
    try {
      if (mode === "live") {
        const result = await request<{ is_valid: boolean; message?: string }>("/api/audit/verify-chain");
        setVerification(result.is_valid ? "Backend chain verification passed." : "Backend verification failed. Inspect the audit ledger.");
      } else {
        if (!blocks.length) { setVerification("No decisions to verify yet. Complete a demo review to create the first audit block."); return; }
        let previous = "0".repeat(64);
        for (const { hash, ...block } of blocks) {
          if (block.previousHash !== previous || await hashBlock(block) !== hash) throw new Error("Verification failed: a local audit block has changed.");
          previous = hash;
        }
        setVerification(`Verified ${blocks.length} local ${blocks.length === 1 ? "block" : "blocks"}. All SHA-256 hashes and previous-block links match.`);
      }
    } catch (error) { setVerification(error instanceof Error ? error.message : "Verification unavailable"); }
    finally { setVerifying(false); }
  }

  const pageTitle = NAV.find(item => item.id === tab)?.label;
  return <div className="copilot-app">
    {mobileNav && <button aria-label="Close navigation" className="nav-scrim" onClick={() => setMobileNav(false)} />}
    <aside className={`copilot-sidebar ${mobileNav ? "is-open" : ""}`}>
      <a className="brand" href="/" aria-label="Aventra home"><Brand small /><span>aventra<span className="brand-period">.</span></span><span className="brand-enterprise">ENTERPRISE</span></a>
      <button className="new-chat" onClick={newChat}><Plus size={18} />New conversation<span>Alt N</span></button>
      <button className="search-trigger" onClick={() => { setSearch(""); setDialog("search"); }}><Search size={16} />Search anything<kbd>Ctrl K</kbd></button>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="Main navigation">{NAV.map((item, index) => <div key={item.id}>{index === 4 && <div className="nav-caption governance-caption">TRUST & GOVERNANCE</div>}<button className={`nav-item ${tab === item.id ? "active" : ""}`} onClick={() => navigate(item.id)}><item.icon size={18} /><span>{item.label}</span>{item.id === "models" && <span className="nav-counter">8</span>}{item.id === "approvals" && pending.length > 0 && <span className="nav-counter amber">{pending.length}</span>}{tab === item.id && <span className="active-dot" />}</button></div>)}</nav>
      <div className="recent-heading"><span>RECENT CONVERSATIONS</span><button className="icon-button" onClick={() => setDialog("search")} aria-label="Search conversations"><MoreHorizontal size={16} /></button></div>
      <div className="recent-list">{visibleRuns.length ? visibleRuns.slice(0, 5).map(run => <button key={run.id} onClick={() => openRun(run)} className={selectedId === run.id ? "selected" : ""}><MessageSquare size={14} /><span>{run.prompt}</span>{run.status === "AWAITING_APPROVAL" && <i />}</button>) : <p>Your next great idea<br />starts with a conversation.</p>}</div>
      <div className="sidebar-bottom"><div className="trust-note"><span className="trust-note-icon"><ShieldCheck size={18} /></span><div>Built on trust.<br /><small>{mode === "demo" ? "Sample data. Human oversight." : "Your infrastructure. Your data."}</small></div><LockKeyhole size={13} /></div><button className="profile" onClick={() => setDialog("settings")}><span className="avatar">ER</span><span>Elena Rostova<small>Compliance officer</small></span><Settings2 size={17} /></button></div>
    </aside>

    <div className="copilot-main">
      <header className="topbar"><div className="topbar-location"><button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={20} /></button><span className="workspace-symbol"><Layers3 size={16} /></span><span>Acme workspace</span><ChevronRight size={13} /><strong>{pageTitle}</strong></div><div className="topbar-actions"><a href="/workbench" className="secondary-button">Real data workbench</a><span className={`environment-pill ${mode}`}><i />{mode === "demo" ? "Interactive demo" : `Live · ${backendState === "online" ? "connected" : backendState === "offline" ? "offline" : "checking"}`}</span><button className="icon-button help-button" aria-label="Open demo guide" onClick={() => setDialog("guide")}><CircleHelp size={19} /></button><button className="notification-button icon-button" aria-label={`${pending.length} approvals need review`} onClick={() => navigate("approvals")}><Bell size={19} />{pending.length > 0 && <i />}</button><span className="avatar small-avatar">ER</span></div></header>
      <main className={`main-viewport ${tab === "workspace" ? "workspace-viewport" : ""}`}>
        {notice && <div className="global-notice" role="alert"><CircleHelp size={17} /><span>{notice}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice("")}><X size={16} /></button></div>}

        {tab === "workspace" && <div className={`workspace-layout ${contextOpen ? "with-context" : ""}`}><div className="conversation-column"><div className="conversation-toolbar"><button className="workspace-mode" onClick={() => setDialog("settings")}><Brand small />Aventra Copilot<ChevronDown size={14} /></button><button className={`context-toggle ${contextOpen ? "selected" : ""}`} aria-label="Toggle workspace context" onClick={() => setContextOpen(!contextOpen)}><SlidersHorizontal size={15} /><span>Workspace context</span></button></div>
          <div className="conversation-scroll">
            {!selected ? <div className="welcome-screen"><div className="hero-brand"><Brand /><span className="orbit orbit-one" /><span className="orbit orbit-two" /><span className="orbit-dot" /></div><div className="eyebrow"><span />YOUR ENTERPRISE, WORKING TOGETHER</div><h1>Less busywork.<br /><span>More possibility.</span></h1><p className="hero-description">Connect your data. Orchestrate your workflows.<br />Move forward with intelligence you can trust.</p>
              <div className="suggestion-grid">{(Object.entries(SCENARIOS) as [ScenarioId, typeof SCENARIOS[ScenarioId]][]).map(([id, scenario]) => { const Icon = SCENARIO_ICONS[id]; return <button key={id} className={`suggestion-card suggestion-${id}`} onClick={() => { setPrompt(scenario.prompt); inputRef.current?.focus(); }}><span className="suggestion-icon"><Icon size={20} /></span><span className="suggestion-title">{scenario.title}</span><span className="suggestion-subtitle">{scenario.subtitle}</span><span className="suggestion-footer">{scenario.tag}<ArrowRight size={15} /></span></button>; })}</div>
              <div className="workspace-pulse"><div><span className="pulse-icon"><AudioLines size={17} /></span><strong>A little context. A lot of potential.</strong></div><span>{mode === "demo" ? `${enabled.length} sample sources` : "Live backend"}<i />8 specialized models</span></div>
            </div> : <div className="conversation-content"><div className="conversation-meta"><span>{selected.source === "demo" ? "SAMPLE WORKFLOW" : "LIVE EXECUTION"}</span><button className="text-button" onClick={() => downloadJson(`aventra-${selected.id}.json`, selected)}><ArrowDownToLine size={14} />Export</button></div><div className="user-message"><span className="avatar small-avatar">ER</span><p>{selected.prompt}</p></div><div className="assistant-message"><Brand small /><div className="assistant-content"><div className="assistant-heading"><strong>Aventra</strong><Status status={selected.status} /></div><p>{selected.status === "RUNNING" ? "I’m bringing the right tools and context together. Here’s the plan." : selected.summary}</p><div className="execution-plan"><div className="plan-heading"><Workflow size={16} /><strong>{SCENARIOS[selected.scenario].title}</strong><span>{selected.source === "demo" ? "Simulated execution" : "Backend execution"}</span></div>{SCENARIOS[selected.scenario].steps.map((step, index) => <div className={`execution-step ${index < selected.step ? "done" : index === selected.step && selected.status === "RUNNING" ? "current" : ""}`} key={step}><span>{index < selected.step ? <Check size={12} /> : index === selected.step && selected.status === "RUNNING" ? <Loader2 size={13} className="spin" /> : index + 1}</span><p>{step}</p>{index < selected.step && <small>Complete</small>}</div>)}</div>
                  {selected.status !== "RUNNING" && selected.source === "demo" && <div className="evidence-card"><div className="section-caption">SAMPLE EVIDENCE · {SCENARIOS[selected.scenario].tag}</div><div className="evidence-table">{SCENARIOS[selected.scenario].evidence.map(([label, left, right]) => <div key={label}><span>{label}</span><strong>{left}</strong><span>{right}</span></div>)}</div></div>}
                  {selected.source === "live" && selected.evidence != null && <details className="live-details"><summary>Inspect live backend evidence</summary><pre className="json-output">{JSON.stringify(selected.evidence, null, 2)}</pre></details>}
                  {selected.events && selected.events.length > 0 && <details className="live-details"><summary>Execution telemetry · {selected.events.length} events</summary><div className="telemetry">{selected.events.map((event, index) => <p key={index}><strong>{event.component}</strong><span>{event.message}</span></p>)}</div></details>}
                  {selected.status === "AWAITING_APPROVAL" && <div className="review-prompt"><span className="review-shield"><ShieldCheck size={22} /></span><div><strong>Your judgment makes the difference.</strong><p>Review the evidence before authorizing the next step.</p></div><button className="primary-button" onClick={() => { setNotes(""); setDialog("review"); }}>Review action<ArrowRight size={14} /></button></div>}
                  {selected.notes && <div className="review-notes"><CheckCheck size={17} /><span><strong>Reviewer’s note</strong>{selected.notes}</span></div>}
                  <div className="model-chips">{SCENARIOS[selected.scenario].models.map(code => <button key={code} onClick={() => setModel(MODELS.find(item => item.code === code)!)}><Boxes size={12} />{MODELS.find(item => item.code === code)?.name}</button>)}</div>
                </div></div><div ref={endRef} /></div>}
          </div>
          <div className="composer-region"><form className={`composer ${running ? "is-running" : ""}`} onSubmit={event => { event.preventDefault(); void startTask(); }}><textarea ref={inputRef} aria-label="Message Aventra" placeholder={selected ? "What would you like to do next?" : "Ask Aventra to make work flow…"} value={prompt} rows={2} maxLength={12000} disabled={submitting} onChange={event => setPrompt(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void startTask(); } }} /><div className="composer-bottom"><div><button className="icon-button attach-button" type="button" aria-label="Attach a text document" onClick={() => fileRef.current?.click()}><Plus size={20} /></button><span className="composer-source"><Database size={13} />{mode === "demo" ? "Sample enterprise data" : "Enterprise backend"}</span></div><div><select aria-label="Execution mode" value={mode} onChange={event => changeMode(event.target.value as Mode)} disabled={running}><option value="demo">Demo mode</option><option value="live">Live backend</option></select><button className="send-button" aria-label="Send message" disabled={!prompt.trim() || running || !ready} type="submit">{running ? <Loader2 size={17} className="spin" /> : <ArrowUp size={19} />}</button></div></div></form><div className="composer-footnote"><LockKeyhole size={11} />{mode === "demo" ? "Demo uses sample data. Review every action. You’re always in control." : "Connected to your backend. Sensitive actions pause for human review."}<button onClick={() => setDialog("guide")} aria-label="Learn about the prototype"><CircleHelp size={12} /></button></div></div>
        </div>{contextOpen && <aside className="context-panel"><div className="context-heading"><strong>Workspace context</strong><button className="icon-button" onClick={() => setContextOpen(false)} aria-label="Close context panel"><X size={17} /></button></div><p>The right information, connected to every conversation.</p><div className="section-caption">DATA SOURCES</div>{DEMO_CONNECTIONS.map(connection => <div className="context-source" key={connection.id}><span className={`connector-logo ${connection.color}`}>{connection.icon}</span><div><strong>{connection.name}</strong><small>{mode === "demo" ? enabled.includes(connection.id) ? "Sample source enabled" : "Sample source paused" : "Inspect in Connections"}</small></div></div>)}<button className="text-button" onClick={() => navigate("connections")}>Manage connections<ArrowRight size={13} /></button><div className="context-policy"><ShieldCheck size={24} /><h3>Intelligence with boundaries.</h3><p>Approval gates for sensitive actions. A traceable decision history. Human oversight at every important step.</p><span>{mode === "demo" ? "Prototype policy walkthrough" : "Backend policies apply"}</span></div><button className="text-button" onClick={() => navigate("models")}><Boxes size={15} />Explore all 8 models</button></aside>}</div>}

        {tab === "workflows" && <div className="content-page"><PageHeading eyebrow="CONNECTED INTELLIGENCE" title="Good work starts with a plan." description="From a business request to a governed, traceable workflow." /><div className="workflow-tabs">{(Object.keys(SCENARIOS) as ScenarioId[]).map(id => <button key={id} className={workflow === id ? "selected" : ""} onClick={() => setWorkflow(id)}>{SCENARIOS[id].title}</button>)}</div><div className="workflow-canvas"><div className="canvas-label"><i />WORKFLOW BLUEPRINT<span>Directed acyclic graph</span></div><div className="workflow-nodes">{SCENARIOS[workflow].models.map((code, index) => { const item = MODELS.find(entry => entry.code === code)!; return <div className="node-with-arrow" key={code}><button className="workflow-node" onClick={() => setModel(item)}><span className="model-code">{code}</span><strong>{item.name}</strong><small>{item.category}</small></button><ArrowRight className="node-arrow" size={22} /></div>; })}<div className="node-with-arrow"><div className="workflow-node gate-node"><ShieldCheck size={24} /><strong>Human review</strong><small>Approval gate</small></div><ArrowRight className="node-arrow" size={22} /></div><div className="workflow-node ledger-node"><FileCheck2 size={24} /><strong>Audit trail</strong><small>Record the decision</small></div></div><div className="canvas-footer"><LockKeyhole size={14} />Allowlisted tools · Explicit dependencies · Human authorization</div></div><div className="workflow-bottom"><div><span className="section-caption">TRY THIS WORKFLOW</span><p>{SCENARIOS[workflow].prompt}</p></div><button className="primary-button" disabled={running} onClick={() => void startTask(SCENARIOS[workflow].prompt, workflow)}><Zap size={16} />Run {mode === "demo" ? "demo" : "workflow"}</button></div><div className="policy-grid"><div><ShieldCheck size={22} /><h3>Human at the helm</h3><p>Sensitive record links, invoice exceptions, and migrations pause for explicit review.</p></div><div><Network size={22} /><h3>A model for every step</h3><p>Specialized models pass typed outputs through the orchestrator’s scoped context.</p></div><div><LockKeyhole size={22} /><h3>A decision you can trace</h3><p>Follow the evidence from source data to reviewer decision and audit record.</p></div></div></div>}

        {tab === "models" && <div className="content-page"><PageHeading eyebrow="THE INTELLIGENCE LAYER" title="Eight minds. One workspace." description="Explore the specialized models behind every governed workflow." /><div className="library-toolbar"><span><i className="green-dot" />8 modular components</span><span>Metrics reported in repository configs · Select a model for live inference</span></div><div className="model-grid">{MODELS.map(item => <button className="model-card" key={item.id} onClick={() => setModel(item)}><div className="model-card-top"><span className="model-code">{item.code}</span><span>v{item.version}</span><ArrowRight size={16} /></div><span className="model-category">{item.category}</span><h3>{item.name}</h3><p>{item.description}</p><div className="model-card-bottom"><strong>{item.score}</strong><span>{item.metric}</span></div></button>)}</div></div>}

        {tab === "connections" && <div className="content-page"><PageHeading eyebrow="YOUR CONNECTED ENTERPRISE" title="Bring your world together." description={mode === "demo" ? "Explore the sample sources that give your copilot context." : "Inspect the enterprise connections configured in your backend."} /><div className="notice"><LockKeyhole size={17} />{mode === "demo" ? "These are sample connectors for the walkthrough. Toggles change demo availability in this browser." : "Live credentials and connector configuration are managed in the enterprise console."}</div>{resourceError && <p className="inline-error" role="alert">{resourceError}</p>}{loadingResource ? <Loading /> : mode === "demo" ? <div className="connections-grid">{DEMO_CONNECTIONS.map(connection => <div className="connection-card" key={connection.id}><div className="connection-card-top"><span className={`connector-logo ${connection.color}`}>{connection.icon}</span><button className={`toggle-switch ${enabled.includes(connection.id) ? "on" : ""}`} role="switch" aria-checked={enabled.includes(connection.id)} aria-label={`Enable ${connection.name}`} onClick={() => setEnabled(previous => previous.includes(connection.id) ? previous.filter(id => id !== connection.id) : [...previous, connection.id])}><span /></button></div><h3>{connection.name}</h3><p>{connection.provider}</p><div className="connection-state"><i className={enabled.includes(connection.id) ? "green-dot" : "gray-dot"} />{enabled.includes(connection.id) ? "Sample source enabled" : "Paused"}<span>DEMO</span></div></div>)}</div> : <div className="live-connections">{liveConnections.length ? liveConnections.map(connection => <div className="list-row" key={connection.id}><Database size={23} /><div><strong>{connection.display_name || connection.name || connection.id}</strong><p>{connection.provider} · {connection.connector_type}</p></div><span>{connection.status || (connection.enabled ? "Enabled" : "Disabled")}</span></div>) : !resourceError && <Empty icon={<Database />} title="No connections yet" description="Add an enterprise connector in the console to see it here." />}</div>}<a className="console-link" href="/console">Open enterprise console<ArrowRight size={15} /></a><div className="connection-explainer"><GitBranch size={30} /><div><h3>One canonical picture.</h3><p>CRM accounts, ERP vendors, and enterprise schemas meet in a shared intelligence layer. Your copilot connects the dots, while you control the decisions.</p></div></div></div>}

        {tab === "approvals" && <div className="content-page"><PageHeading eyebrow="HUMAN OVERSIGHT" title="Your judgment. At the right moment." description="Review evidence, record your reasoning, and decide what happens next." /><div className="approval-stats"><div><strong>{pending.length}</strong><span>Awaiting your review</span></div><div><strong>{visibleRuns.filter(run => run.status === "COMPLETED").length}</strong><span>Approved workflows</span></div><div><strong>{visibleRuns.filter(run => run.status === "REJECTED").length}</strong><span>Declined workflows</span></div></div>{visibleRuns.filter(run => run.status !== "RUNNING").length ? <div className="approval-list">{visibleRuns.filter(run => run.status !== "RUNNING").map(run => <button className="approval-row" key={run.id} onClick={() => openRun(run)}><span className="approval-icon"><ShieldCheck size={22} /></span><div><strong>{SCENARIOS[run.scenario].title}</strong><p>{run.prompt}</p><small>{run.source === "demo" ? "Sample workflow" : "Live workflow"} · {new Date(run.createdAt).toLocaleString()}</small></div><Status status={run.status} /><ChevronRight size={17} /></button>)}</div> : <Empty icon={<ShieldCheck />} title="A clear desk. A fresh start." description="Run a workflow to see how sensitive actions pause here for your review." action={<button className="primary-button" onClick={newChat}>Start a conversation<ArrowRight size={15} /></button>} />}{mode === "live" && <a className="console-link" href="/console">View all backend approval tickets in the enterprise console<ArrowRight size={15} /></a>}</div>}

        {tab === "audit" && <div className="content-page"><PageHeading eyebrow="TRUST, WITH A PAPER TRAIL" title="Every decision tells a story." description={mode === "demo" ? "Your demo review decisions, linked by a real local SHA-256 hash chain." : "Inspect the tamper-evident audit ledger maintained by your backend."} action={<button className="primary-button" onClick={() => void verify()} disabled={verifying}>{verifying ? <Loader2 size={16} className="spin" /> : <ShieldCheck size={16} />}Verify chain</button>} />{verification && <div className="notice" role="status"><ShieldCheck size={17} />{verification}</div>}{resourceError && <p className="inline-error">{resourceError}</p>}{loadingResource ? <Loading /> : mode === "live" ? liveLedger.length ? <pre className="json-output ledger-output">{JSON.stringify(liveLedger, null, 2)}</pre> : !resourceError && <Empty icon={<FileCheck2 />} title="The ledger is ready" description="Backend audit records will appear here as workflows execute." /> : blocks.length ? <div className="audit-list">{[...blocks].reverse().map((block, index) => <div className="audit-block" key={block.id}><span className="block-number">{String(blocks.length - index).padStart(2, "0")}</span><div><div className="audit-block-heading"><strong>{block.action === "REVIEW_APPROVED" ? "Workflow review approved" : "Workflow review declined"}</strong><time>{new Date(block.timestamp).toLocaleString()}</time></div><p>{block.notes}</p><small>{block.actor}</small><code>SHA-256 {block.hash}</code></div><CheckCheck size={19} /></div>)}</div> : <Empty icon={<FileCheck2 />} title="Trust starts with the first decision." description="Complete a demo approval to create your first verifiable audit block." action={<button className="secondary-button" onClick={newChat}>Explore a workflow<ArrowRight size={15} /></button>} />}<div className="audit-footer"><LockKeyhole size={15} /><span>{mode === "demo" ? "Browser-local prototype ledger. Export it to keep a copy of your demo." : "Verification is performed by the backend audit service."}</span><button className="text-button" onClick={() => downloadJson("aventra-audit.json", mode === "demo" ? blocks : liveLedger)}><ArrowDownToLine size={15} />Export JSON</button></div></div>}
      </main>
    </div>

    <input className="sr-only" ref={fileRef} type="file" accept=".txt,.csv,.json,.md" onChange={async event => {
      const file = event.target.files?.[0]; if (!file) return;
      if (file.size > 50000) { setNotice("Choose a text document smaller than 50 KB for this prototype."); event.target.value = ""; return; }
      try { const text = await file.text(); setPrompt(previous => `${previous}${previous ? "\n\n" : ""}[${file.name}]\n${text}`.slice(0, 12000)); inputRef.current?.focus(); setNotice("Document text added to your message. Demo workflows still use the labeled sample records; the model library supports live document extraction."); }
      catch { setNotice("This document could not be read. Try a plain text file."); }
      event.target.value = "";
    }} />
    {model && <ModelDetail key={model.id} model={model} onClose={() => setModel(null)} />}
    {dialog === "search" && <Dialog title="Find your next step" onClose={() => setDialog(null)}><div className="search-input"><Search size={19} /><input autoFocus aria-label="Search conversations and pages" placeholder="Search conversations, models, or pages…" value={search} onChange={event => setSearch(event.target.value)} /></div><div className="search-results">{NAV.filter(item => item.label.toLowerCase().includes(search.toLowerCase())).map(item => <button key={item.id} onClick={() => { navigate(item.id); setDialog(null); }}><item.icon size={18} /><span>{item.label}</span><ArrowRight size={14} /></button>)}{runs.filter(run => run.prompt.toLowerCase().includes(search.toLowerCase())).slice(0, 8).map(run => <button key={run.id} onClick={() => openRun(run)}><MessageSquare size={17} /><span>{run.prompt}<small>{run.source} conversation</small></span><ChevronRight size={14} /></button>)}{MODELS.filter(item => search.length > 1 && item.name.toLowerCase().includes(search.toLowerCase())).map(item => <button key={item.id} onClick={() => { setDialog(null); setModel(item); }}><Boxes size={18} /><span>{item.name}</span><span>{item.code}</span></button>)}{search && !NAV.some(item => item.label.toLowerCase().includes(search.toLowerCase())) && !runs.some(run => run.prompt.toLowerCase().includes(search.toLowerCase())) && !MODELS.some(item => search.length > 1 && item.name.toLowerCase().includes(search.toLowerCase())) && <p className="muted">No matches. Try “workflow”, “invoice”, or “schema”.</p>}</div></Dialog>}
    {dialog === "settings" && <Dialog title="Make this workspace yours" onClose={() => setDialog(null)}><p className="muted">Choose how you want to explore Aventra.</p><div className="mode-options"><button className={mode === "demo" ? "selected" : ""} disabled={running} onClick={() => changeMode("demo")}><Sparkles size={22} /><strong>Interactive demo</strong><p>Four sample workflows, simulated progress, human review, and a local audit trail. No backend required.</p>{mode === "demo" && <Check size={17} />}</button><button className={mode === "live" ? "selected" : ""} disabled={running} onClick={() => changeMode("live")}><Database size={22} /><strong>Live backend</strong><p>Run customer onboarding, inspect connections and the audit ledger, and test all eight models directly.</p>{mode === "live" && <Check size={17} />}</button></div><div className="settings-profile"><span className="avatar">ER</span><div><strong>Elena Rostova</strong><p>Compliance officer · Prototype reviewer</p></div></div><a href="/console" className="console-link">Open the full enterprise console<ArrowRight size={15} /></a></Dialog>}
    {dialog === "guide" && <Dialog title="A little guide to what’s possible" onClose={() => setDialog(null)}><p className="muted">Aventra brings your enterprise models and governance into one conversational workspace.</p><ol className="guide-steps"><li><span>01</span><div><strong>Start with a business request</strong><p>Pick a suggestion or ask about customers, invoices, schema drift, or transaction risks.</p></div></li><li><span>02</span><div><strong>Watch the plan take shape</strong><p>Follow the model sequence, inspect sample evidence, and explore the eight-model library.</p></div></li><li><span>03</span><div><strong>Make the important decision</strong><p>Approve or decline with a review note. Then verify the local audit chain and export your results.</p></div></li></ol><div className="notice"><BookOpen size={18} />Demo mode simulates sample workflows. Model metrics come from repository configs. Live inference requires the FastAPI backend.</div><button className="primary-button full-width" onClick={() => { setDialog(null); newChat(); }}>Let’s make work flow<ArrowRight size={16} /></button></Dialog>}
    {dialog === "review" && selected && <Dialog title="A moment for your judgment" onClose={() => { if (!deciding) setDialog(null); }} wide><div className="review-modal-intro"><ShieldCheck size={27} /><div><strong>{SCENARIOS[selected.scenario].title}</strong><p>{selected.source === "demo" ? "Sample decision · updates this prototype only" : "Live decision · submits to the backend approval service"}</p></div><Status status={selected.status} /></div>{selected.source === "demo" ? <div className="evidence-table review-evidence">{SCENARIOS[selected.scenario].evidence.map(([label, left, right]) => <div key={label}><span>{label}</span><strong>{left}</strong><span>{right}</span></div>)}</div> : <pre className="json-output">{JSON.stringify(selected.evidence, null, 2)}</pre>}<label className="field-label" htmlFor="review-note">Your review note <span>Required</span></label><textarea id="review-note" className="review-textarea" placeholder="Explain what you reviewed and why you’re making this decision…" value={notes} onChange={event => setNotes(event.target.value)} maxLength={2000} /><p className="field-help">Your decision and reasoning will be included in the audit record.</p>{notice && <p className="inline-error" role="alert">{notice}</p>}<div className="dialog-actions"><button className="secondary-button decline-button" disabled={deciding || notes.trim().length < 3} onClick={() => void decide(false)}><X size={16} />Decline</button><button className="primary-button" disabled={deciding || notes.trim().length < 3} onClick={() => void decide(true)}>{deciding ? <Loader2 className="spin" size={16} /> : <Check size={16} />}{SCENARIOS[selected.scenario].decision}</button></div></Dialog>}
  </div>;
}

function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}
function Empty({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-icon">{icon}</span><h2>{title}</h2><p>{description}</p>{action}</div>;
}
function Loading() { return <div className="loading-state"><Loader2 className="spin" size={20} />Loading from your backend…</div>; }
