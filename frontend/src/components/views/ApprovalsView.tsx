"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Clock,
  Check,
  X,
  FileText,
  AlertTriangle,
  RefreshCw,
  GitMerge,
  Key,
} from "lucide-react";
import { api } from "@/lib/api";

interface ApprovalsViewProps {
  currentRole: string;
}

export default function ApprovalsView({ currentRole }: ApprovalsViewProps) {
  const [approvals, setApprovals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("ALL");
  const [selectedTicket, setSelectedTicket] = useState<any>(null);
  const [comments, setComments] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadApprovals = async () => {
    setLoading(true);
    try {
      const data = await api.listApprovals(filter === "ALL" ? undefined : filter);
      setApprovals(data);
    } catch (e) {
      console.error("Failed to load approvals", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadApprovals();
  }, [filter]);

  const handleDecision = async (decision: "APPROVED" | "REJECTED") => {
    if (!selectedTicket || isSubmitting) return;
    if (!comments.trim()) {
      alert("Please enter compliance reviewer remarks before deciding.");
      return;
    }

    setIsSubmitting(true);
    try {
      await api.decideApproval(
        selectedTicket.id,
        decision,
        comments,
        currentRole,
        "Elena Rostova (Compliance Officer)"
      );
      setSelectedTicket(null);
      setComments("");
      await loadApprovals();
    } catch (e: any) {
      alert(`Error submitting decision: ${e.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-[#D29922]" />
            <h1 className="text-xl font-bold tracking-tight text-white">
              Human-in-the-Loop Governance & Authorization
            </h1>
          </div>
          <p className="text-xs text-[#8B949E]">
            Review sensitive mutations, high-confidence entity linkages, and invoice variances before execution.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex rounded-lg border border-[#30363D] bg-[#161B22] p-1 text-xs">
          {["ALL", "PENDING", "APPROVED", "REJECTED"].map((st) => (
            <button
              key={st}
              onClick={() => setFilter(st)}
              className={`rounded-md px-3 py-1 font-medium transition-colors ${
                filter === st ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* Approvals Table / Grid */}
      <div className="space-y-3">
        {loading ? (
          <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-8 text-center text-xs text-[#8B949E]">
            Loading governance tickets...
          </div>
        ) : approvals.length === 0 ? (
          <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-8 text-center text-xs text-[#8B949E]">
            No {filter !== "ALL" ? filter.toLowerCase() : ""} approval requests in queue.
          </div>
        ) : (
          approvals.map((ticket) => (
            <div
              key={ticket.id}
              className="rounded-xl border border-[#21262D] bg-[#0E1117] p-4 transition-all hover:border-[#30363D]"
            >
              <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-white">
                      {ticket.action_type}
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                        ticket.risk_level === "CRITICAL"
                          ? "bg-[#F85149]/20 text-[#F85149]"
                          : ticket.risk_level === "HIGH"
                          ? "bg-[#D29922]/20 text-[#D29922]"
                          : "bg-[#238636]/20 text-[#3FB950]"
                      }`}
                    >
                      RISK: {ticket.risk_level}
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                        ticket.status === "PENDING"
                          ? "bg-[#D29922]/20 text-[#D29922] animate-pulse"
                          : ticket.status === "APPROVED"
                          ? "bg-[#238636]/20 text-[#3FB950]"
                          : "bg-[#F85149]/20 text-[#F85149]"
                      }`}
                    >
                      {ticket.status}
                    </span>
                  </div>

                  <p className="text-xs text-[#E6EDF3]">
                    {ticket.evidence?.decision === "DUPLICATE_IDENTIFIED"
                      ? `LightGBM identified duplicate entity '${ticket.evidence?.golden_record_recommendation?.suggested_canonical_name || "Apex Global Logistics"}' across CRM/ERP records.`
                      : ticket.evidence?.variance_summary || "Operational verification requested."}
                  </p>

                  <div className="flex flex-wrap items-center gap-4 text-[10px] text-[#8B949E] font-mono">
                    <span>Model Confidence: {ticket.confidence_score ? `${(ticket.confidence_score * 100).toFixed(1)}%` : "N/A"}</span>
                    <span>Execution: {ticket.execution_id.slice(0, 8)}...</span>
                    <span>Nonce: {ticket.nonce_token?.slice(0, 12)}...</span>
                  </div>
                </div>

                {ticket.status === "PENDING" ? (
                  <button
                    onClick={() => {
                      setSelectedTicket(ticket);
                      setComments("Verified matching entity credentials and address similarity. Approved.");
                    }}
                    className="self-start sm:self-auto rounded-md bg-[#1F6FEB] px-4 py-2 text-xs font-semibold text-white shadow hover:bg-[#388BFD]"
                  >
                    Review Evidence & Sign-off →
                  </button>
                ) : (
                  <div className="text-right text-[11px] text-[#8B949E]">
                    <span className="block font-medium text-white">
                      Decided by: {ticket.reviewed_by || "System"}
                    </span>
                    <span className="italic">&ldquo;{ticket.reviewer_comments}&rdquo;</span>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Review & Authorize Modal */}
      {selectedTicket && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-2xl rounded-xl border border-[#30363D] bg-[#0E1117] p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-[#21262D] pb-3">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-[#D29922]" />
                <h3 className="text-sm font-bold text-white">
                  Evidence Review & Cryptographic Sign-off
                </h3>
              </div>
              <button
                onClick={() => setSelectedTicket(null)}
                className="text-[#8B949E] hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Side by side comparison */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-[#21262D] bg-[#161B22] p-3 text-xs">
                <span className="text-[10px] uppercase font-bold text-[#8B949E]">
                  Prospective CRM Account
                </span>
                <p className="font-bold text-white text-sm mt-1">
                  {selectedTicket.evidence?.prospect?.business_name || "Apex Global Logistics LLC"}
                </p>
                <p className="text-[#8B949E] mt-0.5">
                  {selectedTicket.evidence?.prospect?.business_address || "742 Evergreen Terrace, Springfield, IL"}
                </p>
                <p className="font-mono text-[#58A6FF] text-[11px] mt-1">
                  Tax ID: {selectedTicket.evidence?.prospect?.federal_tax_id || "US-EIN-8829104"}
                </p>
              </div>

              <div className="rounded-lg border border-[#21262D] bg-[#161B22] p-3 text-xs">
                <span className="text-[10px] uppercase font-bold text-[#8B949E]">
                  Matched ERP Vendor
                </span>
                <p className="font-bold text-white text-sm mt-1">
                  {selectedTicket.evidence?.golden_record_recommendation?.linked_entity_id || "ERP-B-501"}: Apex Global Logistics Inc
                </p>
                <p className="text-[#8B949E] mt-0.5">
                  742 Evergreen Terr, Springfield, IL
                </p>
                <p className="font-mono text-[#3FB950] text-[11px] mt-1">
                  Confidence: {selectedTicket.confidence_score ? `${(selectedTicket.confidence_score * 100).toFixed(1)}%` : "94.2%"}
                </p>
              </div>
            </div>

            {/* Nonce & Policy Protection Notice */}
            <div className="rounded-lg border border-[#30363D] bg-[#0A0D14] p-3 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2 text-[#8B949E]">
                <Key className="h-4 w-4 text-[#D29922]" />
                <span>Single-Use Cryptographic Nonce:</span>
              </div>
              <span className="font-mono text-[10px] text-white">
                {selectedTicket.nonce_token}
              </span>
            </div>

            {/* Review Remarks */}
            <div>
              <label className="text-xs font-semibold text-[#8B949E]">
                Compliance Auditor Remarks (Recorded in Tamper-Evident Ledger)
              </label>
              <textarea
                rows={2}
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="Enter regulatory or internal reason for decision..."
                className="mt-1 w-full rounded-md border border-[#30363D] bg-[#161B22] p-2.5 text-xs text-white focus:border-[#58A6FF] focus:outline-none"
              />
            </div>

            {/* Modal Actions */}
            <div className="flex justify-end gap-3 border-t border-[#21262D] pt-3">
              <button
                onClick={() => setSelectedTicket(null)}
                className="rounded-md border border-[#30363D] bg-[#161B22] px-4 py-2 text-xs font-semibold text-[#C9D1D9] hover:bg-[#21262D]"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDecision("REJECTED")}
                disabled={isSubmitting}
                className="rounded-md border border-[#F85149]/40 bg-[#F85149]/10 px-4 py-2 text-xs font-semibold text-[#F85149] hover:bg-[#F85149]/20"
              >
                Reject Mutation
              </button>
              <button
                onClick={() => handleDecision("APPROVED")}
                disabled={isSubmitting}
                className="rounded-md bg-[#238636] px-5 py-2 text-xs font-semibold text-white shadow hover:bg-[#2EA043]"
              >
                {isSubmitting ? "Signing & Committing..." : "Authorize Record Linkage"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

