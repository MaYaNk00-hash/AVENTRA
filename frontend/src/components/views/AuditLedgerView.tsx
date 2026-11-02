"use client";

import React, { useState, useEffect } from "react";
import {
  ScrollText,
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
  Hash,
  Lock,
  Layers,
  FileCheck,
  Eye,
} from "lucide-react";
import { api } from "@/lib/api";

export default function AuditLedgerView() {
  const [entries, setEntries] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState<any>(null);
  const [inspectBlock, setInspectBlock] = useState<any>(null);

  const loadLedger = async () => {
    setLoading(true);
    try {
      const res = await api.getAuditLedger();
      setEntries(res.entries);
      setTotal(res.total);
    } catch (e) {
      console.error("Failed to load audit ledger", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLedger();
  }, []);

  const handleVerifyChain = async () => {
    setIsVerifying(true);
    try {
      const res = await api.verifyAuditChain();
      setVerificationResult(res);
    } catch (e: any) {
      alert(`Verification error: ${e.message}`);
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <ScrollText className="h-5 w-5 text-[#3FB950]" />
            <h1 className="text-xl font-bold tracking-tight text-white">
              Cryptographic Tamper-Evident Audit Ledger
            </h1>
          </div>
          <p className="text-xs text-[#8B949E]">
            Immutable, SHA-256 chained sequence guaranteeing non-repudiation of all agent actions, model inferences, and governance approvals.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleVerifyChain}
            disabled={isVerifying}
            className="flex items-center gap-1.5 rounded-md bg-gradient-to-r from-[#1F6FEB] to-[#238636] px-4 py-1.5 text-xs font-semibold text-white shadow hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
          >
            {isVerifying ? (
              <>
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                Verifying Chain...
              </>
            ) : (
              <>
                <ShieldCheck className="h-3.5 w-3.5" />
                Verify SHA-256 Hash Chain
              </>
            )}
          </button>
        </div>
      </div>

      {/* Verification Result Banner */}
      {verificationResult && (
        <div
          className={`rounded-xl border p-4 animate-in fade-in duration-300 ${
            verificationResult.is_valid
              ? "border-[#238636]/40 bg-[#238636]/10"
              : "border-[#F85149]/40 bg-[#F85149]/10"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              {verificationResult.is_valid ? (
                <ShieldCheck className="h-5 w-5 text-[#3FB950]" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-[#F85149]" />
              )}
              <div>
                <h4 className="text-xs font-bold text-white">
                  {verificationResult.is_valid
                    ? "Cryptographic Verification Passed: Zero Tampering Detected"
                    : "Cryptographic Verification Failed: Broken Hash Link"}
                </h4>
                <p className="text-[11px] text-[#8B949E]">
                  Validated {verificationResult.total_entries} blocks from root to tip. Latest block hash:{" "}
                  <span className="font-mono text-white">
                    {verificationResult.latest_block_hash?.slice(0, 16)}...
                  </span>
                </p>
              </div>
            </div>
            <span className="font-mono text-xs font-bold text-[#3FB950]">
              {verificationResult.status}
            </span>
          </div>
        </div>
      )}

      {/* Audit Blocks Table */}
      <div className="overflow-hidden rounded-xl border border-[#21262D] bg-[#0E1117] shadow-sm">
        <div className="border-b border-[#21262D] bg-[#161B22] px-4 py-2.5 flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-[#8B949E]">
            Chained Blocks ({total})
          </span>
          <span className="text-[10px] font-mono text-[#8B949E]">
            Algorithm: SHA-256 Chained Hash
          </span>
        </div>

        <table className="w-full text-left text-xs">
          <thead className="border-b border-[#21262D] bg-[#0D1117] font-semibold text-[#8B949E]">
            <tr>
              <th className="px-4 py-3">Block #</th>
              <th className="px-4 py-3">Timestamp (UTC)</th>
              <th className="px-4 py-3">Action Type</th>
              <th className="px-4 py-3">Actor & Role</th>
              <th className="px-4 py-3">Previous Hash</th>
              <th className="px-4 py-3">Current Hash</th>
              <th className="px-4 py-3 text-right">Payload</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#21262D] font-mono text-[#E6EDF3]">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-[#8B949E]">
                  Loading audit blocks...
                </td>
              </tr>
            ) : entries.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-[#8B949E]">
                  No audit entries recorded.
                </td>
              </tr>
            ) : (
              entries.map((entry) => (
                <tr key={entry.id} className="hover:bg-[#161B22]/50">
                  <td className="px-4 py-3 font-bold text-white">#{entry.id}</td>
                  <td className="px-4 py-3 text-[#8B949E] text-[11px]">
                    {entry.timestamp ? entry.timestamp.replace("T", " ").slice(0, 19) : "--"}
                  </td>
                  <td className="px-4 py-3 font-sans font-semibold text-[#58A6FF]">
                    {entry.action_type}
                  </td>
                  <td className="px-4 py-3 text-[11px]">
                    <span className="text-white">{entry.actor_id}</span>{" "}
                    <span className="text-[#8B949E]">({entry.actor_role})</span>
                  </td>
                  <td className="px-4 py-3 text-[10px] text-[#8B949E]" title={entry.prev_hash}>
                    {entry.prev_hash.slice(0, 8)}...
                  </td>
                  <td className="px-4 py-3 text-[10px] text-[#3FB950] font-bold" title={entry.current_hash}>
                    {entry.current_hash.slice(0, 8)}...
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setInspectBlock(entry)}
                      className="inline-flex items-center gap-1 rounded border border-[#30363D] bg-[#161B22] px-2 py-1 text-[10px] text-[#C9D1D9] hover:text-white"
                    >
                      <Eye className="h-3 w-3" />
                      Inspect
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Inspect Block Payload Modal */}
      {inspectBlock && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-xl rounded-xl border border-[#30363D] bg-[#0E1117] p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-[#21262D] pb-3">
              <h3 className="text-sm font-bold text-white">
                Sealed Audit Block #{inspectBlock.id}: {inspectBlock.action_type}
              </h3>
              <button
                onClick={() => setInspectBlock(null)}
                className="text-[#8B949E] hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="space-y-2 text-xs font-mono">
              <div>
                <span className="text-[#8B949E] text-[10px] uppercase">Current Block Hash</span>
                <p className="text-[#3FB950] break-all bg-[#0A0D14] p-2 rounded border border-[#21262D]">
                  {inspectBlock.current_hash}
                </p>
              </div>

              <div>
                <span className="text-[#8B949E] text-[10px] uppercase">Chained Previous Hash</span>
                <p className="text-[#8B949E] break-all bg-[#0A0D14] p-2 rounded border border-[#21262D]">
                  {inspectBlock.prev_hash}
                </p>
              </div>

              <div>
                <span className="text-[#8B949E] text-[10px] uppercase">Payload SHA-256 Digest</span>
                <p className="text-[#58A6FF] break-all bg-[#0A0D14] p-2 rounded border border-[#21262D]">
                  {inspectBlock.payload_hash}
                </p>
              </div>

              <div>
                <span className="text-[#8B949E] text-[10px] uppercase">Recorded Transaction Payload</span>
                <pre className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-[#21262D] bg-[#0A0D14] p-3 text-[11px] text-[#E6EDF3]">
                  {JSON.stringify(inspectBlock.details, null, 2)}
                </pre>
              </div>
            </div>

            <div className="flex justify-end pt-2 border-t border-[#21262D]">
              <button
                onClick={() => setInspectBlock(null)}
                className="rounded-md bg-[#161B22] px-4 py-2 text-xs font-semibold text-white hover:bg-[#21262D]"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

