"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from "@xyflow/react";
import {
  Play,
  CheckCircle2,
  Clock,
  ShieldAlert,
  GitFork,
  RefreshCw,
  Terminal,
  Layers,
  ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api";

const INITIAL_NODES = [
  {
    id: "n1",
    position: { x: 50, y: 150 },
    data: { label: "1. CRM Submission Trigger", type: "trigger", tool: "crm_connector.fetch_record", status: "READY" },
    style: { background: "#0D1117", color: "#E6EDF3", border: "1px solid #00D2FF", borderRadius: "8px", padding: "12px", width: 200, fontSize: "12px", fontWeight: 600 },
  },
  {
    id: "n2",
    position: { x: 300, y: 150 },
    data: { label: "2. ERP Candidate Retrieval", type: "action", tool: "erp_connector.search_records", status: "READY" },
    style: { background: "#0D1117", color: "#E6EDF3", border: "1px solid #388BFD", borderRadius: "8px", padding: "12px", width: 200, fontSize: "12px", fontWeight: 600 },
  },
  {
    id: "n3",
    position: { x: 550, y: 150 },
    data: { label: "3. LightGBM Entity Resolution", type: "ml_node", tool: "entity_resolution.score_pair", status: "READY" },
    style: { background: "#0D1117", color: "#E6EDF3", border: "1px solid #A371F7", borderRadius: "8px", padding: "12px", width: 200, fontSize: "12px", fontWeight: 600 },
  },
  {
    id: "n4",
    position: { x: 800, y: 150 },
    data: { label: "4. Governance Approval Gate", type: "approval_gate", tool: "approval_gate.request_authorization", status: "READY" },
    style: { background: "#0D1117", color: "#E6EDF3", border: "1px solid #D29922", borderRadius: "8px", padding: "12px", width: 200, fontSize: "12px", fontWeight: 600 },
  },
  {
    id: "n5",
    position: { x: 1050, y: 150 },
    data: { label: "5. Enterprise Record Commit", type: "action", tool: "enterprise_action.commit_record", status: "READY" },
    style: { background: "#0D1117", color: "#E6EDF3", border: "1px solid #2EA043", borderRadius: "8px", padding: "12px", width: 200, fontSize: "12px", fontWeight: 600 },
  },
  {
    id: "n6",
    position: { x: 1300, y: 150 },
    data: { label: "6. Tamper-Evident Ledger", type: "audit", tool: "audit_ledger.append_entry", status: "READY" },
    style: { background: "#0D1117", color: "#E6EDF3", border: "1px solid #3FB950", borderRadius: "8px", padding: "12px", width: 200, fontSize: "12px", fontWeight: 600 },
  },
];

const INITIAL_EDGES = [
  { id: "e1-2", source: "n1", target: "n2", animated: true, style: { stroke: "#388BFD", strokeWidth: 2 } },
  { id: "e2-3", source: "n2", target: "n3", animated: true, style: { stroke: "#A371F7", strokeWidth: 2 } },
  { id: "e3-4", source: "n3", target: "n4", animated: true, style: { stroke: "#D29922", strokeWidth: 2 } },
  { id: "e4-5", source: "n4", target: "n5", animated: true, style: { stroke: "#2EA043", strokeWidth: 2 } },
  { id: "e5-6", source: "n5", target: "n6", animated: true, style: { stroke: "#3FB950", strokeWidth: 2 } },
];

export default function WorkflowStudioView() {
  const [nodes, setNodes, onNodesChange] = useNodesState(INITIAL_NODES);
  const [edges, setEdges, onEdgesChange] = useEdgesState(INITIAL_EDGES);
  const [selectedNode, setSelectedNode] = useState<any>(INITIAL_NODES[2]);
  const [isRunning, setIsRunning] = useState(false);
  const [executionStatus, setExecutionStatus] = useState("IDLE");
  const [activeWorkflowId, setActiveWorkflowId] = useState("wf-customer-onboarding");
  const [executionEvents, setExecutionEvents] = useState<any[]>([]);

  const onNodeClick = useCallback((event: any, node: any) => {
    setSelectedNode(node);
  }, []);

  const handleRunWorkflow = async () => {
    if (isRunning) return;
    setIsRunning(true);
    setExecutionStatus("RUNNING");
    setExecutionEvents([]);

    // Reset node styles
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        style: { ...n.style, opacity: 0.6 },
      }))
    );

    try {
      const res = await api.executeWorkflow(activeWorkflowId, {
        record: {
          business_name: "Apex Global Logistics LLC",
          business_address: "742 Evergreen Terrace, Springfield, IL 62704",
          country: "US",
          federal_tax_id: "US-EIN-8829104",
          contact_email: "billing@apexlogistic.com",
        },
      });

      // Stream live execution events
      const es = new EventSource(`http://localhost:8000${res.stream_url}`);

      es.onmessage = (event) => {
        const evt = JSON.parse(event.data);
        setExecutionEvents((prev) => [...prev, evt]);

        // Highlight matching node in React Flow
        setNodes((nds) =>
          nds.map((n) => {
            if (n.id === evt.step_id) {
              return {
                ...n,
                style: {
                  ...n.style,
                  opacity: 1,
                  boxShadow:
                    evt.event_type === "COMPLETED"
                      ? "0 0 12px rgba(63, 185, 80, 0.4)"
                      : evt.event_type === "APPROVAL_REQUESTED"
                      ? "0 0 12px rgba(210, 153, 34, 0.5)"
                      : "0 0 12px rgba(0, 210, 255, 0.4)",
                },
              };
            }
            return n;
          })
        );

        if (evt.event_type === "APPROVAL_REQUESTED") {
          setExecutionStatus("AWAITING_APPROVAL");
          setIsRunning(false);
        } else if (evt.component === "ExecutionEngine" && evt.event_type === "COMPLETED") {
          setExecutionStatus("COMPLETED");
          setIsRunning(false);
          es.close();
        } else if (evt.event_type === "FAILED") {
          setExecutionStatus("FAILED");
          setIsRunning(false);
          es.close();
        }
      };

      es.onerror = () => {
        es.close();
        setIsRunning(false);
      };
    } catch (e: any) {
      alert(`Error running workflow: ${e.message}`);
      setIsRunning(false);
      setExecutionStatus("FAILED");
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-80px)] space-y-4">
      {/* Studio Header */}
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <GitFork className="h-5 w-5 text-[#58A6FF]" />
            <h1 className="text-xl font-bold tracking-tight text-white">
              Workflow Studio & Execution Graph
            </h1>
          </div>
          <p className="text-xs text-[#8B949E]">
            Interactive Directed Acyclic Graph (DAG) with real node execution, conditional branching, and approval states.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={activeWorkflowId}
            onChange={(e) => setActiveWorkflowId(e.target.value)}
            className="rounded-md border border-[#30363D] bg-[#161B22] px-3 py-1.5 text-xs font-medium text-white focus:outline-none"
          >
            <option value="wf-customer-onboarding">
              Customer Onboarding & Duplicate Resolution
            </option>
            <option value="wf-invoice-reconciliation">
              3-Way Invoice Reconciliation & Payment Gate
            </option>
          </select>

          <button
            onClick={handleRunWorkflow}
            disabled={isRunning}
            className="flex items-center gap-1.5 rounded-md bg-[#238636] px-4 py-1.5 text-xs font-semibold text-white shadow hover:bg-[#2EA043] disabled:opacity-50"
          >
            {isRunning ? (
              <>
                <Clock className="h-3.5 w-3.5 animate-spin" />
                Executing...
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 fill-white" />
                Run Workflow
              </>
            )}
          </button>
        </div>
      </div>

      {/* Main Canvas & Inspector Split */}
      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-4 overflow-hidden rounded-xl border border-[#21262D] bg-[#0E1117]">
        {/* React Flow Graph Editor (3 Columns) */}
        <div className="lg:col-span-3 h-full relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            fitView
          >
            <Background color="#161B22" gap={16} />
            <Controls />
            <MiniMap
              nodeColor={() => "#21262D"}
              maskColor="#090B10"
              style={{ background: "#0E1117", border: "1px solid #21262D" }}
            />
          </ReactFlow>

          {/* Graph Status Pill */}
          <div className="absolute top-3 left-3 flex items-center gap-2 rounded-md border border-[#30363D] bg-[#0D1117]/80 px-2.5 py-1 backdrop-blur text-[11px] font-mono text-white">
            <span className={`h-2 w-2 rounded-full ${isRunning ? "bg-[#00D2FF] animate-ping" : "bg-[#2EA043]"}`}></span>
            Status: {executionStatus}
          </div>
        </div>

        {/* Node Properties & Telemetry Panel (1 Column) */}
        <div className="border-t lg:border-t-0 lg:border-l border-[#21262D] bg-[#0A0D14] p-4 flex flex-col justify-between overflow-y-auto">
          <div>
            <div className="flex items-center gap-2 border-b border-[#21262D] pb-2">
              <Layers className="h-4 w-4 text-[#58A6FF]" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                Node Inspector
              </h3>
            </div>

            {selectedNode ? (
              <div className="mt-3 space-y-3 text-xs">
                <div>
                  <span className="text-[#8B949E] text-[10px] uppercase">Node Label</span>
                  <p className="font-semibold text-white mt-0.5">{selectedNode.data?.label}</p>
                </div>

                <div>
                  <span className="text-[#8B949E] text-[10px] uppercase">Target Tool Contract</span>
                  <p className="font-mono text-[11px] text-[#58A6FF] bg-[#161B22] p-1.5 rounded border border-[#21262D] mt-0.5">
                    {selectedNode.data?.tool || "N/A"}
                  </p>
                </div>

                <div>
                  <span className="text-[#8B949E] text-[10px] uppercase">Node Type</span>
                  <p className="capitalize text-[#C9D1D9] mt-0.5">{selectedNode.data?.type}</p>
                </div>

                <div>
                  <span className="text-[#8B949E] text-[10px] uppercase">Policy Gate</span>
                  <p className="text-[#3FB950] font-medium mt-0.5">
                    {selectedNode.data?.type === "approval_gate"
                      ? "Human Authorization Required"
                      : "Allowlisted Automated Execution"}
                  </p>
                </div>
              </div>
            ) : (
              <p className="text-xs text-[#8B949E] mt-4">Select a node on the graph to view properties.</p>
            )}
          </div>

          {/* Micro Telemetry Stream */}
          <div className="mt-4 border-t border-[#21262D] pt-3">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#8B949E]">
              Execution Telemetry
            </span>
            <div className="mt-2 h-44 overflow-y-auto font-mono text-[10px] space-y-1 bg-[#0E1117] p-2 rounded border border-[#21262D]">
              {executionEvents.length === 0 ? (
                <span className="text-[#8B949E]">No active events. Run workflow to stream live telemetry.</span>
              ) : (
                executionEvents.map((evt, idx) => (
                  <div key={idx} className="text-[#C9D1D9]">
                    <span className="text-[#58A6FF]">[{evt.component}]</span> {evt.message}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

