"use client";

import React, { useState, useEffect } from "react";
import Sidebar, { NavTab } from "@/components/Sidebar";
import DashboardView from "@/components/views/DashboardView";
import AIWorkspaceView from "@/components/views/AIWorkspaceView";
import WorkflowStudioView from "@/components/views/WorkflowStudioView";
import MLIntelligenceView from "@/components/views/MLIntelligenceView";
import ExecutionMonitorView from "@/components/views/ExecutionMonitorView";
import ApprovalsView from "@/components/views/ApprovalsView";
import DataHubView from "@/components/views/DataHubView";
import AuditLedgerView from "@/components/views/AuditLedgerView";
import { api } from "@/lib/api";
import { Bell, Shield, ExternalLink } from "lucide-react";

export default function Home() {
  const [currentTab, setCurrentTab] = useState<NavTab>("dashboard");
  const [currentRole, setCurrentRole] = useState("COMPLIANCE_OFFICER");
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState(0);

  const fetchPendingCount = async () => {
    try {
      const approvals = await api.listApprovals("PENDING");
      setPendingApprovalsCount(approvals.length);
    } catch {}
  };

  useEffect(() => {
    fetchPendingCount();
    const interval = setInterval(fetchPendingCount, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#090B10] text-[#E6EDF3]">
      {/* Blackbox-inspired Sidebar */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        pendingApprovalsCount={pendingApprovalsCount}
        currentRole={currentRole}
        onRoleChange={setCurrentRole}
        isCollapsed={isCollapsed}
        onToggleCollapse={() => setIsCollapsed(!isCollapsed)}
      />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Header Bar */}
        <header className="flex h-16 items-center justify-between border-b border-[#21262D] bg-[#0A0D14] px-6">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs font-bold text-[#8B949E] uppercase tracking-wider">
              AVENTRA / {currentTab.replace("_", " ").toUpperCase()}
            </span>
          </div>

          <div className="flex items-center gap-4">
            {/* Quick status pill */}
            <div className="flex items-center gap-2 rounded-full border border-[#21262D] bg-[#161B22] px-3 py-1 text-xs">
              <span className="h-2 w-2 rounded-full bg-[#3FB950]"></span>
              <span className="font-mono text-[11px] text-[#C9D1D9]">FASTAPI BACKEND: ONLINE</span>
            </div>

            {/* API Docs Link */}
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="hidden sm:flex items-center gap-1 text-xs text-[#8B949E] hover:text-[#58A6FF]"
            >
              Swagger Docs <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </header>

        {/* Dynamic Viewport */}
        <main className="flex-1 overflow-y-auto p-6">
          {currentTab === "dashboard" && <DashboardView onNavigateTab={setCurrentTab} />}
          {currentTab === "ai_workspace" && <AIWorkspaceView />}
          {currentTab === "workflow_studio" && <WorkflowStudioView />}
          {currentTab === "ml_intelligence" && <MLIntelligenceView />}
          {currentTab === "execution_monitor" && <ExecutionMonitorView />}
          {currentTab === "approvals" && <ApprovalsView currentRole={currentRole} />}
          {currentTab === "data_hub" && <DataHubView />}
          {currentTab === "audit_ledger" && <AuditLedgerView />}
        </main>
      </div>
    </div>
  );
}
