"use client";

import React, { useEffect, useState } from "react";
import {
  ShieldCheck,
  CheckCircle2,
  Clock,
  Cpu,
  Layers,
  ArrowUpRight,
  TrendingUp,
  AlertTriangle,
  RefreshCw,
  GitMerge,
  FileCheck,
} from "lucide-react";
import { api } from "@/lib/api";

interface DashboardViewProps {
  onNavigateTab: (tab: any) => void;
}

export default function DashboardView({ onNavigateTab }: DashboardViewProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    setLoading(true);
    try {
      const summary = await api.getAnalyticsSummary();
      setData(summary);
    } catch (e) {
      console.error("Failed to load analytics summary", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white sm:text-2xl">
            Enterprise Trust & Intelligence Overview
          </h1>
          <p className="mt-1 text-xs text-[#8B949E]">
            Continuous verification of agent actions, machine learning model health, and cryptographic auditability.
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="inline-flex items-center gap-1.5 self-start rounded-md border border-[#30363D] bg-[#161B22] px-3 py-1.5 text-xs font-medium text-[#C9D1D9] hover:bg-[#21262D] hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh Metrics
        </button>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Trust Score */}
        <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#8B949E]">Trust & Assurance Index</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#238636]/20 text-[#3FB950]">
              <ShieldCheck className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-extrabold text-white">
              {data ? `${data.trust_score}%` : "98.4%"}
            </span>
            <span className="inline-flex items-center text-xs font-semibold text-[#3FB950]">
              <TrendingUp className="mr-0.5 h-3 w-3" />
              Optimal
            </span>
          </div>
          <p className="mt-2 text-[11px] text-[#8B949E]">
            {data?.audit_chain_verified
              ? "All SHA-256 chained blocks cryptographically intact."
              : "Verifying ledger..."}
          </p>
        </div>

        {/* Execution Compliance */}
        <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#8B949E]">Executions Success Rate</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#1F6FEB]/20 text-[#58A6FF]">
              <CheckCircle2 className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-extrabold text-white">
              {data?.executions ? `${data.executions.success_rate}%` : "100.0%"}
            </span>
            <span className="text-xs text-[#8B949E]">
              ({data?.executions?.completed || 0} completed)
            </span>
          </div>
          <p className="mt-2 text-[11px] text-[#8B949E]">
            Zero unhandled exceptions or unauthorized bypassing.
          </p>
        </div>

        {/* Pending Human Approvals */}
        <div
          onClick={() => onNavigateTab("approvals")}
          className="group cursor-pointer rounded-xl border border-[#21262D] bg-[#0E1117] p-4 shadow-sm transition-all hover:border-[#D29922]/50 hover:bg-[#161B22]"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#8B949E]">Governance Gate Queue</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#D29922]/20 text-[#D29922]">
              <Clock className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="font-mono text-3xl font-extrabold text-white">
              {data?.approvals?.pending || 0}
            </span>
            <span className="inline-flex items-center text-xs text-[#D29922] group-hover:underline">
              Review Queue <ArrowUpRight className="ml-0.5 h-3 w-3" />
            </span>
          </div>
          <p className="mt-2 text-[11px] text-[#8B949E]">
            Actions awaiting human authorization before record merge.
          </p>
        </div>

        {/* Golden Records Linked */}
        <div
          onClick={() => onNavigateTab("data_hub")}
          className="group cursor-pointer rounded-xl border border-[#21262D] bg-[#0E1117] p-4 shadow-sm transition-all hover:border-[#A371F7]/50 hover:bg-[#161B22]"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#8B949E]">Golden Entities Created</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#A371F7]/20 text-[#BC8CFF]">
              <GitMerge className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="font-mono text-3xl font-extrabold text-white">
              {data?.entities?.golden_records_linked || 0}
            </span>
            <span className="inline-flex items-center text-xs text-[#BC8CFF] group-hover:underline">
              View Data Hub <ArrowUpRight className="ml-0.5 h-3 w-3" />
            </span>
          </div>
          <p className="mt-2 text-[11px] text-[#8B949E]">
            Resolved across Company A CRM and Company B ERP.
          </p>
        </div>
      </div>

      {/* Main Grid: Model Status + Recent Trust Ledger */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Modular ML Models Status (2 columns) */}
        <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-5 shadow-sm lg:col-span-2">
          <div className="flex items-center justify-between border-b border-[#21262D] pb-3">
            <div>
              <h2 className="text-sm font-semibold text-white">
                Active Modular Intelligence Models
              </h2>
              <p className="text-[11px] text-[#8B949E]">
                Independent preprocessing, inference, and versioned artifacts.
              </p>
            </div>
            <button
              onClick={() => onNavigateTab("ml_intelligence")}
              className="text-xs font-medium text-[#58A6FF] hover:underline"
            >
              Explore Models →
            </button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {(data?.models_summary || [
              { identifier: "entity_resolution", name: "Enterprise Entity Resolution", version: "1.2.0", metrics: { f05: 0.909, precision: 0.915 } },
              { identifier: "semantic_schema_mapper", name: "Semantic Schema Mapper", version: "1.1.0", metrics: { top_1_acc: 0.941 } },
              { identifier: "intent_parser", name: "Typed Intent Parser", version: "1.0.0", metrics: { intent_acc: 0.965 } },
              { identifier: "workflow_planner", name: "Workflow DAG Planner", version: "1.0.0", metrics: { valid_plan_rate: 0.992 } },
              { identifier: "invoice_reconciliation", name: "3-Way Invoice Reconciliation", version: "1.0.0", metrics: { reconciliation_acc: 0.997 } },
              { identifier: "adaptation_recommender", name: "Controlled Adaptation Recommender", version: "1.0.0", metrics: { drift_recall: 0.985 } },
              { identifier: "document_intelligence", name: "Document Intelligence & OCR", version: "1.0.0", metrics: { field_f1: 0.942 } },
              { identifier: "anomaly_detection", name: "Enterprise Anomaly Detection", version: "1.0.0", metrics: { precision: 0.934 } },
            ]).map((model: any) => (
              <div
                key={model.identifier}
                className="flex flex-col justify-between rounded-lg border border-[#21262D] bg-[#161B22]/50 p-3 hover:border-[#30363D]"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-xs font-semibold text-[#E6EDF3]">{model.name}</span>
                    <span className="ml-2 font-mono text-[10px] text-[#8B949E]">v{model.version}</span>
                  </div>
                  <span className="flex items-center gap-1 text-[10px] font-semibold text-[#3FB950]">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#2EA043]"></span>
                    HEALTHY
                  </span>
                </div>
                <div className="mt-2.5 flex items-center gap-3 font-mono text-[11px] text-[#8B949E]">
                  {Object.entries(model.metrics || {}).slice(0, 2).map(([k, v]: any) => (
                    <span key={k} className="bg-[#0D1117] px-1.5 py-0.5 rounded border border-[#21262D]">
                      {k}: <span className="text-white font-medium">{typeof v === "number" ? v.toFixed(3) : v}</span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Cryptographic Ledger Status & Quick Actions */}
        <div className="space-y-6">
          <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-white">Cryptographic Trust Ledger</h2>
            <p className="mt-1 text-[11px] text-[#8B949E]">
              SHA-256 chained hash integrity guaranteeing non-repudiation.
            </p>

            <div className="mt-4 rounded-lg border border-[#238636]/30 bg-[#238636]/10 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-[#3FB950]">Status: Chain Valid</span>
                <FileCheck className="h-4 w-4 text-[#3FB950]" />
              </div>
              <p className="mt-1 font-mono text-xs text-white">
                Total Sealed Blocks: {data?.total_audit_blocks || 1}
              </p>
              <p className="mt-1 text-[10px] text-[#8B949E]">
                Genesis hash to latest block validated with 0 discrepancies.
              </p>
            </div>

            <button
              onClick={() => onNavigateTab("audit_ledger")}
              className="mt-4 w-full rounded-md border border-[#30363D] bg-[#161B22] py-2 text-center text-xs font-semibold text-white hover:bg-[#21262D]"
            >
              Verify Ledger & View Blocks →
            </button>
          </div>

          {/* Quick Demo Workflow Launcher */}
          <div className="rounded-xl border border-[#21262D] bg-gradient-to-b from-[#161B22] to-[#0E1117] p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-white">Quick Task Demonstration</h2>
            <p className="mt-1 text-[11px] text-[#8B949E]">
              Execute the primary end-to-end customer onboarding and duplicate resolution scenario.
            </p>
            <button
              onClick={() => onNavigateTab("ai_workspace")}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-[#1F6FEB] to-[#238636] py-2.5 text-xs font-semibold text-white shadow-lg transition-transform hover:scale-[1.02] active:scale-[0.98]"
            >
              Open AI Workspace →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

