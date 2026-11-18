"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
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
import { Bell, Shield, ExternalLink, Sparkles, Database, Layers } from "lucide-react";

const VALID_TABS: NavTab[] = [
  "dashboard",
  "ai_workspace",
  "workflow_studio",
  "ml_intelligence",
  "execution_monitor",
  "approvals",
  "data_hub",
  "audit_ledger",
];

function ConsoleContent() {
  const [currentTab, setCurrentTab] = useState<NavTab>("dashboard");
  const [currentRole, setCurrentRole] = useState("COMPLIANCE_OFFICER");
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState(0);

  // Read tab and role from URL on initial load and keep on refresh
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab") as NavTab;
      if (tabParam && VALID_TABS.includes(tabParam)) {
        setCurrentTab(tabParam);
      }
      const roleParam = params.get("role");
      if (roleParam) {
        setCurrentRole(roleParam);
      }
    }
  }, []);

  // Listen to browser Back/Forward (popstate) navigation
  useEffect(() => {
    const handlePopState = () => {
      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);
        const tabParam = params.get("tab") as NavTab;
        if (tabParam && VALID_TABS.includes(tabParam)) {
          setCurrentTab(tabParam);
        } else {
          setCurrentTab("dashboard");
        }
        const roleParam = params.get("role");
        if (roleParam) {
          setCurrentRole(roleParam);
        }
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // Persist tab selection to browser URL without full reload
  const handleSelectTab = useCallback((tab: NavTab) => {
    setCurrentTab(tab);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", tab);
      window.history.pushState({ tab }, "", url.toString());
    }
  }, []);

  const handleRoleChange = useCallback((role: string) => {
    setCurrentRole(role);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("role", role);
      window.history.pushState({ role }, "", url.toString());
    }
  }, []);

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
      {/* Sidebar with Navigation and Cross-Workspace Links */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={handleSelectTab}
        pendingApprovalsCount={pendingApprovalsCount}
        currentRole={currentRole}
        onRoleChange={handleRoleChange}
        isCollapsed={isCollapsed}
        onToggleCollapse={() => setIsCollapsed(!isCollapsed)}
      />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Header Bar */}
        <header className="flex h-16 items-center justify-between border-b border-[#21262D] bg-[#0A0D14] px-6">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm font-bold text-[#8B949E] uppercase tracking-wider">
              AVENTRA / {currentTab.replace("_", " ").toUpperCase()}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Direct workspace switcher pills */}
            <a
              href="/agent"
              className="hidden md:inline-flex items-center gap-1.5 rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-1.5 text-xs font-semibold text-[#58A6FF] hover:bg-[#21262D] hover:border-[#58A6FF] transition"
            >
              <Sparkles className="h-3.5 w-3.5 text-[#58A6FF]" />
              <span>Task Workspace (/agent)</span>
            </a>

            <a
              href="/workbench"
              className="hidden lg:inline-flex items-center gap-1.5 rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-1.5 text-xs font-semibold text-[#8B949E] hover:text-white hover:bg-[#21262D] transition"
            >
              <Database className="h-3.5 w-3.5" />
              <span>Data Workbench</span>
            </a>

            {/* Quick status pill */}
            <div className="flex items-center gap-2 rounded-full border border-[#21262D] bg-[#161B22] px-3 py-1 text-xs">
              <span className="h-2 w-2 rounded-full bg-[#3FB950]"></span>
              <span className="font-mono text-xs text-[#C9D1D9]">BACKEND: ONLINE</span>
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
          {currentTab === "dashboard" && <DashboardView onNavigateTab={handleSelectTab} />}
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

export default function Home() {
  return (
    <Suspense fallback={<div className="flex h-screen w-screen items-center justify-center bg-[#090B10] text-white">Loading AVENTRA Console...</div>}>
      <ConsoleContent />
    </Suspense>
  );
}
