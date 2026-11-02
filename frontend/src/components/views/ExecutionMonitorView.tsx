"use client";

import React, { useState, useEffect } from "react";
import {
  TerminalSquare,
  Search,
  Filter,
  RefreshCw,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Play,
  FileCode,
} from "lucide-react";
import { api } from "@/lib/api";

export default function ExecutionMonitorView() {
  const [executions, setExecutions] = useState<any[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterText, setFilterText] = useState("");

  const loadExecutions = async () => {
    setLoading(true);
    try {
      const list = await api.listExecutions();
      setExecutions(list);
      if (list.length > 0 && !selectedExecution) {
        selectExecution(list[0].id);
      }
    } catch (e) {
      console.error("Failed to load executions", e);
    } finally {
      setLoading(false);
    }
  };

  const selectExecution = async (id: string) => {
    try {
      const det = await api.getExecution(id);
      setSelectedExecution(det);
      setEvents(det.execution_events || []);
    } catch (e) {
      console.error("Failed to fetch execution details", e);
    }
  };

  useEffect(() => {
    loadExecutions();
  }, []);

  const filteredEvents = events.filter(
    (e) =>
      e.message?.toLowerCase().includes(filterText.toLowerCase()) ||
      e.component?.toLowerCase().includes(filterText.toLowerCase()) ||
      e.event_type?.toLowerCase().includes(filterText.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <TerminalSquare className="h-5 w-5 text-[#00D2FF]" />
            <h1 className="text-xl font-bold tracking-tight text-white">
              Live Execution Monitor & Terminal Logs
            </h1>
          </div>
          <p className="text-xs text-[#8B949E]">
            Microsecond execution telemetry, real backend component operations, and error traces.
          </p>
        </div>
        <button
          onClick={loadExecutions}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md border border-[#30363D] bg-[#161B22] px-3 py-1.5 text-xs font-medium text-[#C9D1D9] hover:bg-[#21262D] hover:text-white"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh Executions
        </button>
      </div>

      {/* Main Split: Execution Sessions List + Terminal */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        {/* Execution Sessions (1 Column) */}
        <div className="space-y-3">
          <span className="text-xs font-bold uppercase tracking-wider text-[#8B949E]">
            Execution Runs ({executions.length})
          </span>
          <div className="space-y-2 overflow-y-auto max-h-[580px] pr-1">
            {executions.map((ex) => {
              const isSelected = selectedExecution?.id === ex.id;
              return (
                <div
                  key={ex.id}
                  onClick={() => selectExecution(ex.id)}
                  className={`cursor-pointer rounded-lg border p-3 transition-all ${
                    isSelected
                      ? "border-[#58A6FF] bg-[#161B22]"
                      : "border-[#21262D] bg-[#0E1117] hover:border-[#30363D]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold text-white">
                      {ex.workflow_id}
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                        ex.status === "COMPLETED"
                          ? "bg-[#238636]/20 text-[#3FB950]"
                          : ex.status === "AWAITING_APPROVAL"
                          ? "bg-[#D29922]/20 text-[#D29922]"
                          : "bg-[#1F6FEB]/20 text-[#58A6FF]"
                      }`}
                    >
                      {ex.status}
                    </span>
                  </div>
                  <p className="mt-1 font-mono text-[10px] text-[#8B949E] truncate">
                    ID: {ex.id}
                  </p>
                  <div className="mt-2 flex items-center justify-between text-[10px] text-[#8B949E]">
                    <span>Events: {ex.events_count}</span>
                    <span>{ex.duration_ms ? `${ex.duration_ms.toFixed(1)}ms` : "--"}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Blackbox Live Terminal (3 Columns) */}
        <div className="lg:col-span-3 space-y-4">
          <div className="overflow-hidden rounded-xl border border-[#21262D] bg-[#0A0D14] shadow-md flex flex-col h-[580px]">
            {/* Terminal Header */}
            <div className="flex items-center justify-between border-b border-[#21262D] bg-[#0E1117] px-4 py-2.5">
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs font-bold text-white">
                  SESSION: {selectedExecution?.id || "N/A"}
                </span>
                <span className="text-[10px] font-mono text-[#8B949E]">
                  Status: {selectedExecution?.status} • Duration: {selectedExecution?.duration_ms?.toFixed(1) || "--"}ms
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1.5 h-3 w-3 text-[#8B949E]" />
                  <input
                    type="text"
                    placeholder="Filter logs..."
                    value={filterText}
                    onChange={(e) => setFilterText(e.target.value)}
                    className="w-44 rounded-md border border-[#30363D] bg-[#161B22] pl-7 pr-2 py-1 font-mono text-[10px] text-white focus:outline-none focus:border-[#58A6FF]"
                  />
                </div>
              </div>
            </div>

            {/* Terminal Output Stream */}
            <div className="flex-1 overflow-y-auto p-4 font-mono text-xs space-y-1.5">
              {filteredEvents.length === 0 ? (
                <div className="flex h-full items-center justify-center text-[#8B949E]">
                  No log telemetry records found for this execution session.
                </div>
              ) : (
                filteredEvents.map((evt, idx) => (
                  <div key={idx} className="flex items-start gap-3 hover:bg-[#161B22]/60 p-1 rounded transition-colors">
                    <span className="text-[#8B949E] text-[10px] shrink-0">
                      {evt.timestamp ? evt.timestamp.split("T")[1].replace("Z", "") : "--:--:--"}
                    </span>
                    <span className="rounded bg-[#161B22] px-1.5 py-0.2 text-[9px] font-bold text-[#58A6FF] shrink-0 border border-[#30363D]">
                      {evt.component}
                    </span>
                    <span
                      className={`text-[10px] font-bold shrink-0 ${
                        evt.event_type === "COMPLETED"
                          ? "text-[#3FB950]"
                          : evt.event_type === "APPROVAL_REQUESTED"
                          ? "text-[#D29922]"
                          : evt.event_type === "ERROR"
                          ? "text-[#F85149]"
                          : "text-[#00D2FF]"
                      }`}
                    >
                      [{evt.event_type}]
                    </span>
                    <span className="text-[#E6EDF3] flex-1">{evt.message}</span>
                    {evt.duration_ms && (
                      <span className="text-[#8B949E] text-[10px] shrink-0">
                        +{evt.duration_ms.toFixed(1)}ms
                      </span>
                    )}
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

