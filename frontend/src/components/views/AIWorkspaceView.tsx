"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Send,
  Terminal,
  Play,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ShieldAlert,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Sparkles,
  GitBranch,
  Layers,
  Check,
  X,
  FileCheck,
} from "lucide-react";
import { api } from "@/lib/api";

const SAMPLE_PROMPTS = [
  "Onboard new customer Apex Global Logistics LLC and deduplicate against ERP database",
  "Process supplier invoice INV-7729 and perform 3-way matching with PO-4401",
  "Analyze schema drift between Company A CRM and canonical master",
];

export default function AIWorkspaceView() {
  const [prompt, setPrompt] = useState(SAMPLE_PROMPTS[0]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [activePlan, setActivePlan] = useState<any>(null);
  const [currentStepId, setCurrentStepId] = useState<string | null>(null);
  const [executionState, setExecutionState] = useState<string>("IDLE");
  const [approvalRequest, setApprovalRequest] = useState<any>(null);
  const [approvalComments, setApprovalComments] = useState("Verified matching tax EIN and address similarity. Authorized for canonical record linkage.");
  const [isSubmittingApproval, setIsSubmittingApproval] = useState(false);
  const [finalOutput, setFinalOutput] = useState<any>(null);
  const [isTerminalCollapsed, setIsTerminalCollapsed] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Clean up SSE connection on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const handleStartTask = async () => {
    if (!prompt.trim() || isExecuting) return;

    setIsExecuting(true);
    setLogs([]);
    setApprovalRequest(null);
    setFinalOutput(null);
    setExecutionState("RUNNING");

    try {
      // 1. Submit natural language task to Agent
      const res = await api.executeAgentTask(prompt);
      
      if (res.status === "SECURITY_VIOLATION") {
        setExecutionState("SECURITY_VIOLATION");
        setLogs([
          {
            timestamp: new Date().toISOString(),
            component: "SecurityGuardrail",
            event_type: "BLOCKED",
            message: res.message,
            duration_ms: 2.1,
          },
        ]);
        setIsExecuting(false);
        return;
      }

      setExecutionId(res.execution_id);
      setActivePlan(res.plan);

      // 2. Connect to real-time Server-Sent Events stream
      const sseUrl = `http://localhost:8000${res.stream_url}`;
      const es = new EventSource(sseUrl);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        try {
          const evt = JSON.parse(event.data);
          setLogs((prev) => [...prev, evt]);
          setCurrentStepId(evt.step_id);

          if (evt.event_type === "APPROVAL_REQUESTED") {
            setExecutionState("AWAITING_APPROVAL");
            setApprovalRequest(evt.payload);
            setIsExecuting(false);
          } else if (evt.component === "ExecutionEngine" && evt.event_type === "COMPLETED") {
            setExecutionState("COMPLETED");
            setIsExecuting(false);
            // Fetch final execution details
            api.getExecution(res.execution_id).then((det) => {
              setFinalOutput(det.output_data);
            });
            es.close();
          } else if (evt.event_type === "FAILED") {
            setExecutionState("FAILED");
            setIsExecuting(false);
            es.close();
          }
        } catch (err) {
          console.error("SSE parse error", err);
        }
      };

      es.onerror = () => {
        es.close();
      };
    } catch (e: any) {
      setExecutionState("FAILED");
      setLogs((prev) => [
        ...prev,
        {
          timestamp: new Date().toISOString(),
          component: "Orchestrator",
          event_type: "ERROR",
          message: e.message || "Failed to start agent task",
        },
      ]);
      setIsExecuting(false);
    }
  };

  const handleDecision = async (decision: "APPROVED" | "REJECTED") => {
    if (!approvalRequest?.approval_request_id) return;
    setIsSubmittingApproval(true);

    try {
      await api.decideApproval(
        approvalRequest.approval_request_id,
        decision,
        approvalComments,
        "COMPLIANCE_OFFICER",
        "Elena Rostova (Compliance Officer)"
      );

      // The SSE stream will continue and send the subsequent commit and audit block events!
      setApprovalRequest(null);
    } catch (e: any) {
      alert(`Approval error: ${e.message}`);
    } finally {
      setIsSubmittingApproval(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Title & Instructions */}
      <div>
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-[#00D2FF]/20 text-[#00D2FF]">
            <Sparkles className="h-3.5 w-3.5" />
          </span>
          <h1 className="text-xl font-bold tracking-tight text-white sm:text-2xl">
            Autonomous AI Workspace
          </h1>
        </div>
        <p className="mt-1 text-xs text-[#8B949E]">
          Submit natural-language business directives. The agent inspects permissions, plans DAGs, invokes modular models, and pauses for human verification.
        </p>
      </div>

      {/* Task Prompt Input Box */}
      <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-4 shadow-sm">
        <label className="text-xs font-semibold uppercase tracking-wider text-[#8B949E]">
          Natural-Language Enterprise Directive
        </label>
        <div className="mt-2 flex gap-3">
          <textarea
            rows={2}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Type a business directive..."
            className="flex-1 resize-none rounded-lg border border-[#30363D] bg-[#161B22] p-3 text-sm text-white placeholder-[#8B949E] focus:border-[#58A6FF] focus:outline-none"
          />
          <button
            onClick={handleStartTask}
            disabled={isExecuting || !prompt.trim()}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-[#1F6FEB] to-[#238636] px-5 py-2.5 text-xs font-semibold text-white shadow-md transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
          >
            {isExecuting ? (
              <>
                <Clock className="h-4 w-4 animate-spin" />
                Executing...
              </>
            ) : (
              <>
                <Play className="h-4 w-4 fill-white" />
                Dispatch Agent
              </>
            )}
          </button>
        </div>

        {/* Sample Prompt Chips */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[11px] text-[#8B949E]">Sample directives:</span>
          {SAMPLE_PROMPTS.map((p, idx) => (
            <button
              key={idx}
              onClick={() => setPrompt(p)}
              className="rounded border border-[#30363D] bg-[#161B22] px-2.5 py-1 text-[11px] text-[#C9D1D9] hover:border-[#58A6FF] hover:text-white"
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Human Approval Required Gate (When Paused) */}
      {approvalRequest && (
        <div className="rounded-xl border-2 border-[#D29922] bg-[#D29922]/10 p-5 shadow-lg animate-in fade-in duration-300">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <ShieldAlert className="h-6 w-6 text-[#D29922]" />
              <div>
                <h3 className="text-sm font-bold text-white">
                  Governance Authorization Required: Sensitive Entity Linkage
                </h3>
                <p className="text-xs text-[#E6EDF3]">
                  Model detected a high-confidence business match ({((approvalRequest.evidence?.confidence || 0.942) * 100).toFixed(1)}%). Policy requires human sign-off before linking financial identities.
                </p>
              </div>
            </div>
            <span className="rounded-full bg-[#D29922] px-2.5 py-0.5 text-xs font-bold text-black uppercase">
              Risk: {approvalRequest.risk_level || "HIGH"}
            </span>
          </div>

          {/* Evidence Comparison Grid */}
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-[#30363D] bg-[#0E1117] p-3 text-xs">
              <span className="font-semibold text-[#8B949E] uppercase tracking-wider text-[10px]">
                Incoming Prospective Record (Company A CRM)
              </span>
              <p className="mt-1 font-bold text-white text-sm">
                {approvalRequest.evidence?.prospect?.business_name || "Apex Global Logistics LLC"}
              </p>
              <p className="text-[#8B949E] mt-0.5">
                {approvalRequest.evidence?.prospect?.business_address || "742 Evergreen Terrace, Springfield, IL"}
              </p>
              <p className="font-mono text-[#58A6FF] text-[11px] mt-1">
                EIN: {approvalRequest.evidence?.prospect?.federal_tax_id || "US-EIN-8829104"}
              </p>
            </div>

            <div className="rounded-lg border border-[#30363D] bg-[#0E1117] p-3 text-xs">
              <span className="font-semibold text-[#8B949E] uppercase tracking-wider text-[10px]">
                Existing ERP Master Match (Company B ERP)
              </span>
              <p className="mt-1 font-bold text-white text-sm">
                {approvalRequest.evidence?.golden_record_recommendation?.linked_entity_id || "ERP-B-501"}: Apex Global Logistics Inc
              </p>
              <p className="text-[#8B949E] mt-0.5">
                742 Evergreen Terr, Springfield, IL
              </p>
              <p className="font-mono text-[#3FB950] text-[11px] mt-1">
                Recommendation: CREATE CANONICAL GOLDEN LINK
              </p>
            </div>
          </div>

          {/* Compliance Remarks & Action Buttons */}
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
            <input
              type="text"
              value={approvalComments}
              onChange={(e) => setApprovalComments(e.target.value)}
              placeholder="Compliance review remarks..."
              className="flex-1 rounded-md border border-[#30363D] bg-[#0E1117] px-3 py-2 text-xs text-white focus:border-[#58A6FF] focus:outline-none"
            />
            <div className="flex gap-2">
              <button
                onClick={() => handleDecision("REJECTED")}
                disabled={isSubmittingApproval}
                className="inline-flex items-center gap-1.5 rounded-md border border-[#F85149]/40 bg-[#F85149]/10 px-4 py-2 text-xs font-semibold text-[#F85149] hover:bg-[#F85149]/20"
              >
                <X className="h-3.5 w-3.5" />
                Reject
              </button>
              <button
                onClick={() => handleDecision("APPROVED")}
                disabled={isSubmittingApproval}
                className="inline-flex items-center gap-1.5 rounded-md bg-[#238636] px-4 py-2 text-xs font-semibold text-white shadow hover:bg-[#2EA043]"
              >
                <Check className="h-3.5 w-3.5" />
                Authorize Record Linkage
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Final Success Banner */}
      {finalOutput && (
        <div className="rounded-xl border border-[#238636]/40 bg-[#238636]/10 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <ShieldCheck className="h-5 w-5 text-[#3FB950]" />
              <div>
                <h3 className="text-sm font-bold text-white">
                  Workflow Execution Succeeded & Sealed in Audit Ledger
                </h3>
                <p className="text-xs text-[#8B949E]">
                  Canonical Master: <span className="font-mono text-white font-semibold">{finalOutput.canonical_id}</span> • CRM ID: <span className="font-mono text-white font-semibold">{finalOutput.crm_id}</span>
                </p>
              </div>
            </div>
            <div className="text-right">
              <span className="rounded bg-[#0E1117] px-2 py-1 font-mono text-[11px] text-[#3FB950] border border-[#238636]/30">
                Block #{finalOutput.audit_block_id}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Blackbox AI Live Execution Terminal */}
      <div className="overflow-hidden rounded-xl border border-[#21262D] bg-[#0A0D14] shadow-md">
        <div className="flex items-center justify-between border-b border-[#21262D] bg-[#0E1117] px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-[#00D2FF]" />
            <span className="font-mono text-xs font-bold text-white tracking-wider">
              LIVE EXECUTION MONITOR
            </span>
            <span className="ml-2 flex items-center gap-1.5 rounded-full bg-[#161B22] px-2 py-0.5 text-[10px] text-[#8B949E] border border-[#21262D]">
              <span className={`h-1.5 w-1.5 rounded-full ${isExecuting ? "bg-[#00D2FF] animate-ping" : "bg-[#2EA043]"}`}></span>
              {executionState}
            </span>
          </div>
          <button
            onClick={() => setIsTerminalCollapsed(!isTerminalCollapsed)}
            className="text-[#8B949E] hover:text-white"
          >
            {isTerminalCollapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </button>
        </div>

        {!isTerminalCollapsed && (
          <div className="h-72 overflow-y-auto p-4 font-mono text-xs leading-relaxed space-y-1.5">
            {logs.length === 0 ? (
              <div className="flex h-full items-center justify-center text-[#8B949E]">
                Waiting for business task dispatch...
              </div>
            ) : (
              logs.map((log, idx) => (
                <div key={idx} className="flex items-start gap-2.5 hover:bg-[#161B22]/50 p-0.5 rounded">
                  <span className="text-[#8B949E] shrink-0">
                    {log.timestamp ? log.timestamp.split("T")[1].replace("Z", "") : "--:--:--"}
                  </span>
                  <span className="rounded bg-[#161B22] px-1.5 py-0.2 text-[10px] font-bold text-[#58A6FF] shrink-0 border border-[#30363D]">
                    {log.component}
                  </span>
                  <span
                    className={`font-semibold shrink-0 text-[10px] ${
                      log.event_type === "COMPLETED"
                        ? "text-[#3FB950]"
                        : log.event_type === "APPROVAL_REQUESTED"
                        ? "text-[#D29922]"
                        : log.event_type === "ERROR"
                        ? "text-[#F85149]"
                        : "text-[#00D2FF]"
                    }`}
                  >
                    [{log.event_type}]
                  </span>
                  <span className="text-[#E6EDF3] flex-1">{log.message}</span>
                  {log.duration_ms && (
                    <span className="text-[#8B949E] text-[10px] shrink-0">
                      +{log.duration_ms.toFixed(1)}ms
                    </span>
                  )}
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        )}
      </div>
    </div>
  );
}

