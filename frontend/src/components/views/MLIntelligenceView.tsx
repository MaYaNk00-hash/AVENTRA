"use client";

import React, { useState, useEffect } from "react";
import {
  Cpu,
  Play,
  RefreshCw,
  GitMerge,
  Layers,
  CheckCircle2,
  Sliders,
  FileCode,
  Gauge,
  Sparkles,
  ArrowRight,
} from "lucide-react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
} from "@xyflow/react";
import { api } from "@/lib/api";

export default function MLIntelligenceView() {
  const [activeSubTab, setActiveSubTab] = useState<"catalog" | "dependency_graph" | "evaluation">("catalog");
  const [models, setModels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedModel, setSelectedModel] = useState<any>(null);
  const [inferenceInput, setInferenceInput] = useState<string>("{}");
  const [inferenceOutput, setInferenceOutput] = useState<any>(null);
  const [isInferenceRunning, setIsInferenceRunning] = useState(false);
  const [evaluatingModelId, setEvaluatingModelId] = useState<string | null>(null);

  // Dependency graph state
  const [depGraph, setDepGraph] = useState<any>(null);

  const loadModels = async () => {
    setLoading(true);
    try {
      const data = await api.listModels();
      setModels(data);
      if (data.length > 0 && !selectedModel) {
        selectModelForTest(data[0]);
      }
      const graph = await api.getModelDependencyGraph();
      setDepGraph(graph);
    } catch (e) {
      console.error("Failed to load models", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadModels();
  }, []);

  const selectModelForTest = (m: any) => {
    setSelectedModel(m);
    setInferenceOutput(null);

    // Prefill realistic JSON based on model type
    if (m.model_identifier === "entity_resolution") {
      setInferenceInput(
        JSON.stringify(
          {
            query: {
              entity_id: "NEW-001",
              business_name: "Acme Industrial Supplies LLC",
              business_address: "450 Market Street Suite 200, San Francisco, CA",
              country: "US",
              source_system: "COMPANY_A_CRM",
            },
            candidates: [
              {
                entity_id: "ERP-991",
                business_name: "Acme Industrial Supplies Corp",
                business_address: "450 Market St Ste 200, San Francisco, CA",
                country: "US",
                source_system: "COMPANY_B_ERP",
              },
            ],
          },
          null,
          2
        )
      );
    } else if (m.model_identifier === "semantic_schema_mapper") {
      setInferenceInput(
        JSON.stringify(
          {
            fields: [
              {
                field_name: "client_legal_entity",
                datatype: "varchar(255)",
                description: "Company registered title",
                sample_values: ["Microsoft Corp"],
              },
              {
                field_name: "invoice_gross_sum",
                datatype: "decimal(12,2)",
                description: "Total invoice balance due",
                sample_values: [14200.5],
              },
            ],
          },
          null,
          2
        )
      );
    } else if (m.model_identifier === "intent_parser") {
      setInferenceInput(
        JSON.stringify(
          {
            prompt: "Onboard new enterprise customer Acme Technologies and resolve potential duplicate records.",
          },
          null,
          2
        )
      );
    } else if (m.model_identifier === "anomaly_detection") {
      setInferenceInput(
        JSON.stringify(
          {
            transaction_id: "TX-9901",
            vendor_id: "VEND-NEW-01",
            amount: 75000.0,
            historical_avg_amount: 1500.0,
            historical_std_amount: 300.0,
            vendor_age_days: 2,
            transactions_last_24h: 7,
            is_weekend: true,
          },
          null,
          2
        )
      );
    } else if (m.model_identifier === "document_intelligence") {
      setInferenceInput(
        JSON.stringify(
          {
            document_text: "INVOICE # INV-2026-9041\nPURCHASE ORDER: PO-7712\nDATE: 2026-10-20\nSubtotal: $1250.00\nTax: $100.00\nTotal Amount: $1350.00",
            filename: "invoice_sample.txt",
          },
          null,
          2
        )
      );
    } else {
      setInferenceInput(JSON.stringify({ test_key: "value" }, null, 2));
    }
  };

  const handleRunInference = async () => {
    if (!selectedModel || isInferenceRunning) return;
    setIsInferenceRunning(true);
    setInferenceOutput(null);

    try {
      const parsedData = JSON.parse(inferenceInput);
      const res = await api.predictModel(selectedModel.model_identifier, parsedData);
      setInferenceOutput(res);
    } catch (e: any) {
      setInferenceOutput({ error: e.message || "Invalid JSON or execution error" });
    } finally {
      setIsInferenceRunning(false);
    }
  };

  const handleEvaluate = async (modelId: string) => {
    setEvaluatingModelId(modelId);
    try {
      const res = await api.evaluateModel(modelId);
      // Refresh list to show updated metrics
      await loadModels();
    } catch (e: any) {
      alert(`Evaluation error: ${e.message}`);
    } finally {
      setEvaluatingModelId(null);
    }
  };

  // Prepare dependency graph nodes & edges for React Flow
  const depNodes = (depGraph?.nodes || []).map((n: any) => ({
    id: n.id,
    position: n.position,
    data: { label: n.label, category: n.category },
    style: {
      background: n.type === "gate" ? "#211E0B" : n.type === "audit" ? "#0F2815" : "#161B22",
      color: "#E6EDF3",
      border:
        n.type === "gate"
          ? "1px solid #D29922"
          : n.type === "audit"
          ? "1px solid #3FB950"
          : "1px solid #58A6FF",
      borderRadius: "8px",
      padding: "10px",
      fontSize: "11px",
      fontWeight: 600,
      width: 190,
    },
  }));

  const depEdges = (depGraph?.edges || []).map((e: any) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label,
    animated: true,
    style: { stroke: "#58A6FF", strokeWidth: 1.5 },
    labelStyle: { fill: "#8B949E", fontSize: 10, fontFamily: "monospace" },
  }));

  return (
    <div className="space-y-6">
      {/* Title & Navigation */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <Cpu className="h-5 w-5 text-[#A371F7]" />
            <h1 className="text-xl font-bold tracking-tight text-white">
              ML Intelligence Hub & Registry
            </h1>
          </div>
          <p className="text-xs text-[#8B949E]">
            8 independent modular models with isolated preprocessing, feature engineering, and reproducible artifacts.
          </p>
        </div>

        {/* Sub-tab Pills */}
        <div className="flex rounded-lg border border-[#30363D] bg-[#161B22] p-1 text-xs">
          <button
            onClick={() => setActiveSubTab("catalog")}
            className={`rounded-md px-3 py-1 font-medium transition-colors ${
              activeSubTab === "catalog" ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
            }`}
          >
            Model Catalog & Sandbox
          </button>
          <button
            onClick={() => setActiveSubTab("dependency_graph")}
            className={`rounded-md px-3 py-1 font-medium transition-colors ${
              activeSubTab === "dependency_graph"
                ? "bg-[#1F6FEB] text-white"
                : "text-[#8B949E] hover:text-white"
            }`}
          >
            Model Dependency Graph
          </button>
        </div>
      </div>

      {activeSubTab === "catalog" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Models List (1 Column) */}
          <div className="space-y-3">
            <span className="text-xs font-bold uppercase tracking-wider text-[#8B949E]">
              Registered Enterprise Models ({models.length})
            </span>
            <div className="space-y-2 overflow-y-auto max-h-[600px] pr-1">
              {models.map((m) => {
                const isSelected = selectedModel?.model_identifier === m.model_identifier;
                return (
                  <div
                    key={m.model_identifier}
                    onClick={() => selectModelForTest(m)}
                    className={`cursor-pointer rounded-lg border p-3 transition-all ${
                      isSelected
                        ? "border-[#58A6FF] bg-[#161B22] shadow-sm"
                        : "border-[#21262D] bg-[#0E1117] hover:border-[#30363D]"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="text-xs font-bold text-white">{m.display_name}</h4>
                        <span className="font-mono text-[10px] text-[#58A6FF]">
                          {m.model_identifier} • v{m.model_version}
                        </span>
                      </div>
                      <span className="flex items-center gap-1 rounded bg-[#238636]/20 px-1.5 py-0.5 text-[9px] font-bold text-[#3FB950]">
                        ACTIVE
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-[#8B949E] line-clamp-2">
                      {m.description}
                    </p>
                    <div className="mt-2.5 flex items-center justify-between border-t border-[#21262D] pt-2">
                      <span className="text-[10px] font-mono text-[#8B949E]">
                        Task: {m.task_type}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEvaluate(m.model_identifier);
                        }}
                        disabled={evaluatingModelId === m.model_identifier}
                        className="text-[10px] text-[#58A6FF] hover:underline"
                      >
                        {evaluatingModelId === m.model_identifier ? "Evaluating..." : "Evaluate →"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Interactive Sandbox & Inspection (2 Columns) */}
          <div className="space-y-4 lg:col-span-2">
            {selectedModel && (
              <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-5 shadow-sm space-y-4">
                <div className="flex items-start justify-between border-b border-[#21262D] pb-3">
                  <div>
                    <h2 className="text-sm font-bold text-white">
                      {selectedModel.display_name}
                    </h2>
                    <p className="font-mono text-xs text-[#58A6FF]">
                      ml/models/{selectedModel.model_identifier}
                    </p>
                  </div>
                  <button
                    onClick={handleRunInference}
                    disabled={isInferenceRunning}
                    className="flex items-center gap-1.5 rounded-md bg-[#238636] px-4 py-1.5 text-xs font-semibold text-white shadow hover:bg-[#2EA043] disabled:opacity-50"
                  >
                    {isInferenceRunning ? (
                      <>
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        Running...
                      </>
                    ) : (
                      <>
                        <Play className="h-3.5 w-3.5 fill-white" />
                        Run Inference
                      </>
                    )}
                  </button>
                </div>

                {/* Metrics Breakdown */}
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[#8B949E]">
                    Trained Model Evaluation Metrics
                  </span>
                  <div className="mt-1.5 flex flex-wrap gap-2">
                    {Object.entries(selectedModel.metrics || {}).map(([k, v]: any) => (
                      <div
                        key={k}
                        className="rounded-md border border-[#30363D] bg-[#161B22] px-2.5 py-1 text-xs"
                      >
                        <span className="text-[#8B949E] text-[10px] uppercase">{k}:</span>{" "}
                        <span className="font-mono font-bold text-white">
                          {typeof v === "number" ? v.toFixed(3) : v}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Input Payload Editor */}
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[#8B949E]">
                    Input Contract Payload (JSON)
                  </span>
                  <textarea
                    rows={7}
                    value={inferenceInput}
                    onChange={(e) => setInferenceInput(e.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-[#30363D] bg-[#0A0D14] p-3 font-mono text-xs text-[#E6EDF3] focus:border-[#58A6FF] focus:outline-none"
                  />
                </div>

                {/* Inference Result Terminal */}
                {inferenceOutput && (
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#8B949E]">
                      Live Prediction Output
                    </span>
                    <pre className="mt-1.5 max-h-60 overflow-y-auto rounded-lg border border-[#21262D] bg-[#0A0D14] p-3 font-mono text-xs text-[#3FB950]">
                      {JSON.stringify(inferenceOutput, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Model Dependency View Tab */}
      {activeSubTab === "dependency_graph" && (
        <div className="h-[550px] overflow-hidden rounded-xl border border-[#21262D] bg-[#0E1117]">
          <ReactFlow nodes={depNodes} edges={depEdges} fitView>
            <Background color="#161B22" gap={16} />
            <Controls />
            <MiniMap style={{ background: "#0D1117" }} />
          </ReactFlow>
        </div>
      )}
    </div>
  );
}

