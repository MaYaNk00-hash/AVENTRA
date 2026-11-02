"use client";

import React, { useState, useEffect } from "react";
import {
  Database,
  Plus,
  RefreshCw,
  GitMerge,
  Sliders,
  AlertTriangle,
  CheckCircle2,
  Layers,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";

export default function DataHubView() {
  const [activeTab, setActiveTab] = useState<"crm" | "erp" | "golden" | "schema">("crm");
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [driftReport, setDriftReport] = useState<any>(null);
  const [isDriftLoading, setIsDriftLoading] = useState(false);
  const [showNewRecordModal, setShowNewRecordModal] = useState(false);
  const [newRecordName, setNewRecordName] = useState("");
  const [newRecordAddress, setNewRecordAddress] = useState("");
  const [newRecordTaxId, setNewRecordTaxId] = useState("");

  const loadRecords = async (origin?: string) => {
    setLoading(true);
    try {
      const data = await api.listRecords(origin);
      setRecords(data);
    } catch (e) {
      console.error("Failed to load records", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "crm") loadRecords("COMPANY_A_CRM");
    else if (activeTab === "erp") loadRecords("COMPANY_B_ERP");
    else if (activeTab === "golden") loadRecords("GOLDEN_MASTER");
  }, [activeTab]);

  const handleCreateRecord = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRecordName) return;

    try {
      await api.createRecord({
        business_name: newRecordName,
        business_address: newRecordAddress,
        tax_identifier: newRecordTaxId,
        country: "US",
        system_origin: "COMPANY_A_CRM",
      });
      setShowNewRecordModal(false);
      setNewRecordName("");
      setNewRecordAddress("");
      setNewRecordTaxId("");
      await loadRecords("COMPANY_A_CRM");
    } catch (e: any) {
      alert(`Error creating record: ${e.message}`);
    }
  };

  const handleSimulateDrift = async () => {
    setIsDriftLoading(true);
    try {
      const res = await api.simulateDrift();
      setDriftReport(res.prediction);
    } catch (e: any) {
      alert(`Drift simulation error: ${e.message}`);
    } finally {
      setIsDriftLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-[#388BFD]" />
            <h1 className="text-xl font-bold tracking-tight text-white">
              Enterprise Data Hub & System Connectors
            </h1>
          </div>
          <p className="text-xs text-[#8B949E]">
            Inspect CRM/ERP source data, golden master linkages, and monitor schema drift with controlled adaptation proposals.
          </p>
        </div>

        {/* Sub-tab navigation */}
        <div className="flex rounded-lg border border-[#30363D] bg-[#161B22] p-1 text-xs">
          <button
            onClick={() => setActiveTab("crm")}
            className={`rounded-md px-3 py-1 font-medium transition-colors ${
              activeTab === "crm" ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
            }`}
          >
            Company A CRM
          </button>
          <button
            onClick={() => setActiveTab("erp")}
            className={`rounded-md px-3 py-1 font-medium transition-colors ${
              activeTab === "erp" ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
            }`}
          >
            Company B ERP
          </button>
          <button
            onClick={() => setActiveTab("golden")}
            className={`rounded-md px-3 py-1 font-medium transition-colors ${
              activeTab === "golden" ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
            }`}
          >
            Golden Master Entities
          </button>
          <button
            onClick={() => setActiveTab("schema")}
            className={`rounded-md px-3 py-1 font-medium transition-colors ${
              activeTab === "schema" ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
            }`}
          >
            Schema Drift & Migration
          </button>
        </div>
      </div>

      {/* Main Tab Content */}
      {activeTab !== "schema" ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#8B949E]">
              {activeTab === "crm"
                ? "Company A CRM Accounts"
                : activeTab === "erp"
                ? "Company B ERP Vendors"
                : "Consolidated Golden Records"} ({records.length})
            </span>

            {activeTab === "crm" && (
              <button
                onClick={() => setShowNewRecordModal(true)}
                className="flex items-center gap-1.5 rounded-md bg-[#238636] px-3 py-1.5 text-xs font-semibold text-white shadow hover:bg-[#2EA043]"
              >
                <Plus className="h-3.5 w-3.5" />
                New Customer Prospect
              </button>
            )}
          </div>

          {/* Records Table */}
          <div className="overflow-hidden rounded-xl border border-[#21262D] bg-[#0E1117] shadow-sm">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[#21262D] bg-[#161B22] font-semibold text-[#8B949E]">
                <tr>
                  <th className="px-4 py-3">Record ID</th>
                  <th className="px-4 py-3">Business Entity Name</th>
                  <th className="px-4 py-3">Address</th>
                  <th className="px-4 py-3">Tax / EIN</th>
                  <th className="px-4 py-3">Canonical ID</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#21262D] font-mono text-[#E6EDF3]">
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-[#8B949E]">
                      Loading records...
                    </td>
                  </tr>
                ) : records.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-[#8B949E]">
                      No records in this partition.
                    </td>
                  </tr>
                ) : (
                  records.map((r) => (
                    <tr key={r.id} className="hover:bg-[#161B22]/50">
                      <td className="px-4 py-3 text-[#58A6FF]">{r.id}</td>
                      <td className="px-4 py-3 font-sans font-medium text-white">{r.name}</td>
                      <td className="px-4 py-3 font-sans text-[#8B949E] truncate max-w-xs">{r.address}</td>
                      <td className="px-4 py-3">{r.tax_identifier || "N/A"}</td>
                      <td className="px-4 py-3 text-[#3FB950] font-semibold">
                        {r.canonical_id || "UNLINKED"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-[#238636]/20 px-1.5 py-0.5 text-[10px] font-bold text-[#3FB950]">
                          {r.status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* Schema Drift & Controlled Adaptation View */
        <div className="space-y-6">
          <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-5 shadow-sm space-y-4">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center border-b border-[#21262D] pb-3">
              <div>
                <h3 className="text-sm font-bold text-white">
                  Model M6: Controlled Schema Adaptation Recommender
                </h3>
                <p className="text-xs text-[#8B949E]">
                  Detects schema mutations across Company A CRM and synthesizes safe versioned migration diffs. AI never self-authorizes.
                </p>
              </div>
              <button
                onClick={handleSimulateDrift}
                disabled={isDriftLoading}
                className="flex items-center gap-1.5 rounded-md bg-[#1F6FEB] px-4 py-2 text-xs font-semibold text-white shadow hover:bg-[#388BFD] disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isDriftLoading ? "animate-spin" : ""}`} />
                Simulate Schema Drift & Run Model M6
              </button>
            </div>

            {driftReport && (
              <div className="space-y-4 animate-in fade-in duration-300">
                <div className="flex items-center justify-between rounded-lg border border-[#D29922]/30 bg-[#D29922]/10 p-3">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-[#D29922]" />
                    <span className="text-xs font-bold text-white">
                      Proposal #{driftReport.proposal_id}: Schema Drift Detected ({driftReport.from_version} → {driftReport.to_version})
                    </span>
                  </div>
                  <span className="rounded bg-[#D29922] px-2 py-0.5 text-[10px] font-bold text-black uppercase">
                    Status: {driftReport.status}
                  </span>
                </div>

                {/* Diff breakdown */}
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="rounded-lg border border-[#21262D] bg-[#161B22] p-3 text-xs space-y-2">
                    <span className="font-bold text-[#8B949E] text-[10px] uppercase">
                      Renamed / Modified Fields
                    </span>
                    {driftReport.drift_report?.renamed_fields?.map((r: any, idx: number) => (
                      <div key={idx} className="flex items-center justify-between font-mono text-[11px] bg-[#0E1117] p-2 rounded border border-[#21262D]">
                        <span className="text-[#F85149] line-through">{r.old_field}</span>
                        <ArrowRight className="h-3 w-3 text-[#8B949E]" />
                        <span className="text-[#3FB950] font-semibold">{r.new_field}</span>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-lg border border-[#21262D] bg-[#161B22] p-3 text-xs space-y-2">
                    <span className="font-bold text-[#8B949E] text-[10px] uppercase">
                      Impacted Production Workflows
                    </span>
                    {driftReport.drift_report?.impacted_workflows?.map((wf: any, idx: number) => (
                      <div key={idx} className="bg-[#0E1117] p-2 rounded border border-[#21262D]">
                        <div className="flex items-center justify-between font-bold text-white">
                          <span>{wf.workflow_name}</span>
                          <span className="text-[10px] text-[#F85149]">Risk: {wf.risk_tier}</span>
                        </div>
                        <p className="mt-1 font-mono text-[10px] text-[#8B949E]">
                          Affected attributes: {wf.affected_fields?.join(", ")}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* New Customer Prospect Modal */}
      {showNewRecordModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <form
            onSubmit={handleCreateRecord}
            className="w-full max-w-md rounded-xl border border-[#30363D] bg-[#0E1117] p-6 shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between border-b border-[#21262D] pb-3">
              <h3 className="text-sm font-bold text-white">New Company A CRM Account</h3>
              <button
                type="button"
                onClick={() => setShowNewRecordModal(false)}
                className="text-[#8B949E] hover:text-white"
              >
                ✕
              </button>
            </div>

            <div>
              <label className="text-xs font-semibold text-[#8B949E]">Legal Entity Name</label>
              <input
                type="text"
                required
                value={newRecordName}
                onChange={(e) => setNewRecordName(e.target.value)}
                placeholder="e.g. Apex Global Logistics LLC"
                className="mt-1 w-full rounded-md border border-[#30363D] bg-[#161B22] px-3 py-2 text-xs text-white focus:outline-none focus:border-[#58A6FF]"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-[#8B949E]">Street Address</label>
              <input
                type="text"
                value={newRecordAddress}
                onChange={(e) => setNewRecordAddress(e.target.value)}
                placeholder="e.g. 742 Evergreen Terrace, Springfield, IL"
                className="mt-1 w-full rounded-md border border-[#30363D] bg-[#161B22] px-3 py-2 text-xs text-white focus:outline-none focus:border-[#58A6FF]"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-[#8B949E]">Tax Identifier / EIN</label>
              <input
                type="text"
                value={newRecordTaxId}
                onChange={(e) => setNewRecordTaxId(e.target.value)}
                placeholder="e.g. US-EIN-8829104"
                className="mt-1 w-full rounded-md border border-[#30363D] bg-[#161B22] px-3 py-2 text-xs text-white focus:outline-none focus:border-[#58A6FF]"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-[#21262D]">
              <button
                type="button"
                onClick={() => setShowNewRecordModal(false)}
                className="rounded-md border border-[#30363D] bg-[#161B22] px-4 py-2 text-xs font-semibold text-[#C9D1D9]"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="rounded-md bg-[#238636] px-4 py-2 text-xs font-semibold text-white shadow hover:bg-[#2EA043]"
              >
                Save Account
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

