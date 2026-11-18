"use client";
import { useState, type FormEvent } from "react";
import { Database, ArrowLeft, Upload, ShieldCheck, Loader2, Sparkles, LayoutDashboard } from "lucide-react";
import InfrastructurePanel from "@/components/InfrastructurePanel";

type Dataset = { id: string; name: string; domain: string; columns: string[]; row_count: number; sha256: string };
type Task = "entities" | "schema" | "invoice" | "anomaly";
const TASKS: Record<Task, string> = { entities: "Cross-system entity matching", schema: "Semantic field mapping", invoice: "Invoice / PO / receipt validation", anomaly: "Historical transaction anomalies" };
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Workbench() {
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [task, setTask] = useState<Task>("entities");
  const [source, setSource] = useState("");
  const [candidate, setCandidate] = useState("");
  const [mapping, setMapping] = useState<Record<string,string>>({});
  const [candidateMapping, setCandidateMapping] = useState<Record<string,string>>({});
  const [currency, setCurrency] = useState("");
  const [domain, setDomain] = useState("CRM");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [output, setOutput] = useState<unknown>(null);
  const [dbPath, setDbPath] = useState("");
  const [table, setTable] = useState("");
  async function api(path: string, body?: unknown, bearer = token) {
    const response = await fetch(BASE + path, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${bearer}` }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(60000) });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    return data;
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); } catch (failure) { setError(failure instanceof Error ? failure.message : "Request failed"); } finally { setBusy(false); }
  }
  async function login(event: FormEvent) {
    event.preventDefault();
    await perform(async () => {
      const response = await fetch(BASE + "/api/auth/login", { method: "POST", body: new URLSearchParams({ username, password }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Login failed");
      const records = await api("/api/workbench/datasets", undefined, result.access_token);
      setToken(result.access_token); setPassword(""); setDatasets(records);
    });
  }
  const current = datasets.find(item => item.id === source);
  const other = datasets.find(item => item.id === candidate);
  const fields = task === "entities" ? ["entity_id", "business_name", "business_address", "country"] : task === "anomaly" ? ["amount"] : [];
  function columns(dataset: Dataset | undefined, values: Record<string,string>, setValues: (value: Record<string,string>) => void) {
    return fields.map(field => <label key={field} className="field-label">{field}<select required value={values[field] || ""} onChange={event => setValues({...values,[field]:event.target.value})}><option value="">Choose source column</option>{dataset?.columns.map(column => <option key={column}>{column}</option>)}</select></label>);
  }
  return <div className="copilot-app" style={{overflowY:"auto",display:"block"}}><main className="content-page" style={{maxWidth:1100}}>
    <div style={{display:"flex",gap:"14px",alignItems:"center",marginBottom:"16px",flexWrap:"wrap"}}>
      <a className="console-link" href="/agent"><ArrowLeft size={16}/> Back to Task Workspace (/agent)</a>
      <a className="console-link" href="/console" style={{color:"#58A6FF"}}><LayoutDashboard size={16}/> Enterprise Operations Console (/console)</a>
    </div>
    <div className="page-heading"><div><div className="eyebrow" style={{marginTop:28}}>ACTUAL DATA · FOUR COMPONENTS</div><h1>Your records. Verifiable results.</h1><p>Connect existing client infrastructure, review adaptive mappings, and read current records. Dataset imports remain available for evaluation.</p></div><Database size={35}/></div>
    <div className="notice"><ShieldCheck size={19}/>Read-only analysis. No simulated sources, generated transaction history, or enterprise writes. Existing prototype conversations remain separate.</div>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {!token ? <form onSubmit={login} className="composer"><h2>Sign in to your backend</h2><label className="field-label">Username<input required autoComplete="username" value={username} onChange={event=>setUsername(event.target.value)}/></label><label className="field-label">Password<input required type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)}/></label><button disabled={busy} className="primary-button">{busy ? "Connecting…" : "Sign in"}</button><p className="muted">Use an existing backend account. Your token stays in memory and is cleared when this page reloads.</p></form> : <>
      <InfrastructurePanel token={token}/><section className="composer" style={{marginBottom:24}}><h2>1. Import actual data</h2><p className="muted">CSV with headers or a JSON array of objects · maximum 2 MB / 10,000 records. Invoice JSON rows must contain invoice, purchase_order, and goods_receipt objects.</p><label className="field-label">Source system<select value={domain} onChange={event=>setDomain(event.target.value)}><option>CRM</option><option>ERP</option><option>DATABASE</option></select></label><label className="secondary-button"><Upload size={15}/>Choose dataset<input disabled={busy} type="file" accept=".csv,.json" onChange={event=>{const file=event.target.files?.[0]; if(!file)return; void perform(async()=>{if(file.size>2000000)throw new Error("Maximum file size is 2 MB"); await api("/api/workbench/datasets",{name:file.name,domain,format:file.name.toLowerCase().endsWith(".csv")?"csv":"json",content:await file.text()});setDatasets(await api("/api/workbench/datasets"));setOutput(null);});event.target.value="";}}/></label>
      <details style={{marginTop:20}}><summary>Import a SQLite table (administrator)</summary><p className="muted">Place your database under the server’s configured AVENTRA_DATA_ROOT. Only read-only SELECT operations are used.</p><label className="field-label">Relative database path<input value={dbPath} onChange={event=>setDbPath(event.target.value)} placeholder="company.sqlite"/></label><label className="field-label">Table name<input value={table} onChange={event=>setTable(event.target.value)}/></label><button className="secondary-button" disabled={busy||!dbPath||!table} onClick={()=>void perform(async()=>{await api("/api/workbench/database-import",{name:table,domain,relative_path:dbPath,table});setDatasets(await api("/api/workbench/datasets"));})}>Read table</button></details>
      <div style={{marginTop:20}}>{datasets.map(dataset=><p className="muted" key={dataset.id}><strong>{dataset.name}</strong> · {dataset.domain} · {dataset.row_count} rows · SHA-256 {dataset.sha256.slice(0,12)}</p>)}</div></section>
      <form className="composer" onSubmit={event=>{event.preventDefault();setOutput(null);void perform(async()=>setOutput(await api("/api/workbench/analyze",{task,dataset_id:source,candidate_dataset_id:candidate||null,mapping,candidate_mapping:candidateMapping,options:{currency}})));}}><h2>2. Select analysis and map fields</h2><div className="workflow-tabs" style={{marginTop:20}}>{(Object.keys(TASKS) as Task[]).map(key=><button type="button" key={key} className={task===key?"selected":""} onClick={()=>{setTask(key);setOutput(null);setMapping({});setCandidateMapping({});}}>{TASKS[key]}</button>)}</div><label className="field-label">Input dataset<select required value={source} onChange={event=>{setSource(event.target.value);setMapping({});setOutput(null);}}><option value="">Select imported data</option>{datasets.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{columns(current,mapping,setMapping)}
      {(task==="entities"||task==="anomaly")&&<><label className="field-label">{task==="anomaly"?"Historical reference dataset":"Target CRM / ERP dataset"}<select required value={candidate} onChange={event=>{setCandidate(event.target.value);setCandidateMapping({});}}><option value="">Select reference data</option>{datasets.filter(item=>item.id!==source).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{columns(other,candidateMapping,setCandidateMapping)}</>}
      {task==="anomaly"&&<label className="field-label">Currency shared by both datasets<input required value={currency} onChange={event=>setCurrency(event.target.value)} placeholder="INR"/></label>}
      {task==="schema"&&<p className="muted">Field suggestions use actual column names, types, and sample values. Review uncertain suggestions; mappings are never applied automatically.</p>}
      <button className="primary-button" disabled={busy||!source}>{busy&&<Loader2 size={15} className="spin"/>}Analyze actual records</button></form>
      {output!==null&&<section style={{marginTop:28}}><h2>3. Inspect evidence and provenance</h2><pre className="json-output" style={{maxHeight:650}}>{JSON.stringify(output,null,2)}</pre></section>}
    </>}
  </main></div>;
}
