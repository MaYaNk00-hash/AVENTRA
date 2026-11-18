"use client";

import React, { useState, useEffect } from "react";
import {
  LayoutDashboard,
  Bot,
  GitFork,
  Cpu,
  TerminalSquare,
  ShieldCheck,
  Database,
  ScrollText,
  ChevronLeft,
  ChevronRight,
  Shield,
  UserCheck,
  Lock,
  Sparkles,
  ExternalLink,
} from "lucide-react";

export type NavTab =
  | "dashboard"
  | "ai_workspace"
  | "workflow_studio"
  | "ml_intelligence"
  | "execution_monitor"
  | "approvals"
  | "data_hub"
  | "audit_ledger";

interface SidebarProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  pendingApprovalsCount: number;
  currentRole: string;
  onRoleChange: (role: string) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const ROLES = [
  { id: "COMPLIANCE_OFFICER", name: "Elena Rostova", title: "Compliance Officer", icon: ShieldCheck },
  { id: "OPERATIONS_APPROVER", name: "Marcus Thorne", title: "Ops Approver", icon: UserCheck },
  { id: "ADMIN", name: "Alexander Vance", title: "Chief AI Officer", icon: Lock },
  { id: "AUDITOR", name: "Dr. Sarah Lin", title: "Lead Auditor", icon: ScrollText },
];

export default function Sidebar({
  currentTab,
  onSelectTab,
  pendingApprovalsCount,
  currentRole,
  onRoleChange,
  isCollapsed,
  onToggleCollapse,
}: SidebarProps) {
  const [sidebarWidth, setSidebarWidth] = useState<number>(230);
  const [isResizing, setIsResizing] = useState(false);

  // Restore saved adjustable width from localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("aventra_sidebar_width");
      if (saved) {
        const parsed = parseInt(saved, 10);
        if (!isNaN(parsed) && parsed >= 180 && parsed <= 400) {
          setSidebarWidth(parsed);
        }
      }
    }
  }, []);

  // Drag-to-resize handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      const newWidth = Math.max(180, Math.min(380, e.clientX));
      setSidebarWidth(newWidth);
      if (typeof window !== "undefined") {
        localStorage.setItem("aventra_sidebar_width", newWidth.toString());
      }
    };

    const handleMouseUp = () => {
      if (isResizing) setIsResizing(false);
    };

    if (isResizing) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  const navItems = [
    { id: "dashboard" as NavTab, label: "Dashboard", icon: LayoutDashboard },
    { id: "ai_workspace" as NavTab, label: "AI Workspace", icon: Bot },
    { id: "workflow_studio" as NavTab, label: "Workflow Studio", icon: GitFork },
    { id: "ml_intelligence" as NavTab, label: "ML Intelligence", icon: Cpu },
    { id: "execution_monitor" as NavTab, label: "Execution Monitor", icon: TerminalSquare },
    {
      id: "approvals" as NavTab,
      label: "Approvals",
      icon: ShieldCheck,
      badge: pendingApprovalsCount > 0 ? pendingApprovalsCount : undefined,
    },
    { id: "data_hub" as NavTab, label: "Data Hub", icon: Database },
    { id: "audit_ledger" as NavTab, label: "Audit Ledger", icon: ScrollText },
  ];

  const activeRoleObj = ROLES.find((r) => r.id === currentRole) || ROLES[0];

  return (
    <aside
      style={{ width: isCollapsed ? 64 : sidebarWidth }}
      className={`relative flex flex-col border-r border-[#21262D] bg-[#0A0D14] transition-[width] ${
        isResizing ? "transition-none select-none" : "duration-200"
      }`}
    >
      {/* Brand Header */}
      <div className="flex h-16 items-center justify-between border-b border-[#21262D] px-3.5">
        {!isCollapsed && (
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[#00D2FF] to-[#0066FF] shadow-md shadow-[#0066FF]/20">
              <Shield className="h-4 w-4 text-white" />
            </div>
            <div className="truncate">
              <span className="font-mono text-sm font-bold tracking-wider text-white">
                AVENTRA
              </span>
              <span className="block text-[10px] font-medium tracking-tight text-[#8B949E]">
                ENTERPRISE TRUST AI
              </span>
            </div>
          </div>
        )}
        {isCollapsed && (
          <div className="mx-auto flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[#00D2FF] to-[#0066FF]">
            <Shield className="h-4 w-4 text-white" />
          </div>
        )}
        <button
          onClick={onToggleCollapse}
          className="rounded p-1 text-[#8B949E] hover:bg-[#161B22] hover:text-white"
          title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      {/* Role Switcher */}
      <div className="border-b border-[#21262D] p-3">
        {!isCollapsed ? (
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-[#8B949E]">
              Active Governance Role
            </label>
            <select
              value={currentRole}
              onChange={(e) => onRoleChange(e.target.value)}
              className="mt-1 w-full truncate rounded-md border border-[#30363D] bg-[#161B22] px-2 py-1 text-xs font-medium text-white shadow-sm focus:border-[#58A6FF] focus:outline-none"
            >
              {ROLES.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title} — {r.name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="flex justify-center" title={`${activeRoleObj.title} (${activeRoleObj.name})`}>
            <activeRoleObj.icon className="h-4.5 w-4.5 text-[#58A6FF]" />
          </div>
        )}
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`group flex w-full items-center rounded-md px-2.5 py-1.5 text-xs font-medium transition-all ${
                isActive
                  ? "bg-[#1F6FEB]/15 text-[#58A6FF] border border-[#1F6FEB]/30"
                  : "text-[#8B949E] hover:bg-[#161B22] hover:text-[#E6EDF3]"
              }`}
              title={isCollapsed ? item.label : undefined}
            >
              <Icon
                className={`h-4 w-4 shrink-0 transition-colors ${
                  isActive ? "text-[#58A6FF]" : "text-[#8B949E] group-hover:text-white"
                }`}
              />
              {!isCollapsed && <span className="ml-2.5 truncate">{item.label}</span>}
              {!isCollapsed && item.badge !== undefined && (
                <span className="ml-auto flex h-4 min-w-4 items-center justify-center rounded-full bg-[#D29922] px-1 text-[10px] font-bold text-black animate-pulse">
                  {item.badge}
                </span>
              )}
              {isCollapsed && item.badge !== undefined && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[#D29922]" />
              )}
            </button>
          );
        })}

        {/* Workspaces switcher links */}
        {!isCollapsed && (
          <div className="pt-2 mt-2 border-t border-[#21262D] space-y-0.5">
            <div className="px-2 text-[10px] font-semibold uppercase tracking-wider text-[#6E7681]">
              Workspaces
            </div>
            <a
              href="/agent"
              className="flex items-center rounded-md px-2.5 py-1.5 text-xs text-[#8B949E] hover:bg-[#161B22] hover:text-[#58A6FF] transition"
            >
              <Sparkles className="h-3.5 w-3.5 mr-2 text-[#58A6FF]" />
              <span className="truncate">Task Workspace</span>
              <ExternalLink className="ml-auto h-3 w-3 opacity-50" />
            </a>
            <a
              href="/workbench"
              className="flex items-center rounded-md px-2.5 py-1.5 text-xs text-[#8B949E] hover:bg-[#161B22] hover:text-white transition"
            >
              <Database className="h-3.5 w-3.5 mr-2 text-[#8B949E]" />
              <span className="truncate">Data Workbench</span>
              <ExternalLink className="ml-auto h-3 w-3 opacity-50" />
            </a>
          </div>
        )}
      </nav>

      {/* Trust & Cryptographic Status */}
      <div className="border-t border-[#21262D] p-2.5">
        {!isCollapsed ? (
          <div className="rounded border border-[#238636]/30 bg-[#238636]/10 p-2">
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#3FB950] opacity-75"></span>
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#2EA043]"></span>
              </span>
              <span className="text-[10px] font-bold text-[#3FB950]">
                TRUST LAYER ACTIVE
              </span>
            </div>
            <p className="mt-0.5 text-[9px] text-[#8B949E]">
              SHA-256 Chained • 0 Violations
            </p>
          </div>
        ) : (
          <div className="flex justify-center" title="Trust Layer Active (SHA-256 Verified)">
            <span className="flex h-2 w-2 rounded-full bg-[#2EA043]"></span>
          </div>
        )}
      </div>

      {/* Drag-to-Resize Handle */}
      {!isCollapsed && (
        <div
          onMouseDown={handleMouseDown}
          className={`absolute -right-1 top-0 bottom-0 w-2 cursor-col-resize z-50 transition-colors hover:bg-[#58A6FF]/40 ${
            isResizing ? "bg-[#58A6FF]" : "bg-transparent"
          }`}
          title="Drag to resize sidebar width"
        />
      )}
    </aside>
  );
}
