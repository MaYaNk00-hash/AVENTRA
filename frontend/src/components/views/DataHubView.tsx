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
  Server,
  Activity,
  Power,
  Trash2,
  Key,
  Lock,
  Eye,
  EyeOff,
  Check,
  X,
  ExternalLink,
  Users,
  Building2,
  Mail,
  Search,
  Sparkles,
  Info,
  ShieldAlert,
  UserCheck,
  HelpCircle,
  FileText
} from "lucide-react";
import { api } from "@/lib/api";

export default function DataHubView() {
  const [activeTab, setActiveTab] = useState<"connections" | "crm" | "erp" | "golden" | "schema">("connections");

  // Data Records State
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [driftReport, setDriftReport] = useState<any>(null);
  const [isDriftLoading, setIsDriftLoading] = useState(false);
  const [showNewRecordModal, setShowNewRecordModal] = useState(false);
  const [newRecordName, setNewRecordName] = useState("");
  const [newRecordAddress, setNewRecordAddress] = useState("");
  const [newRecordTaxId, setNewRecordTaxId] = useState("");
  const [newRecordEmail, setNewRecordEmail] = useState("");

  // CRM Entity Sub-Tab & Adapter State
  const [crmEntity, setCrmEntity] = useState<"accounts" | "contacts" | "leads">("accounts");
  const [crmAdapter, setCrmAdapter] = useState<"COMPANY_A_CRM" | "HUBSPOT_CRM">("COMPANY_A_CRM");
  const [crmSearchQuery, setCrmSearchQuery] = useState("");
  const [crmSelectedRecord, setCrmSelectedRecord] = useState<any>(null);

  // M1 Duplicate Intelligence State
  const [m1Result, setM1Result] = useState<any>(null);
  const [isM1Scanning, setIsM1Scanning] = useState(false);
  const [showM1Modal, setShowM1Modal] = useState(false);

  // Connections State
  const [connections, setConnections] = useState<any[]>([]);
  const [loadingConnections, setLoadingConnections] = useState(true);
  const [templates, setTemplates] = useState<any[]>([]);
  const [filterType, setFilterType] = useState<string>("ALL");
  const [searchConnQuery, setSearchConnQuery] = useState("");
  const [testingStatus, setTestingStatus] = useState<Record<string, "testing" | "success" | "error">>({});
  const [togglingStatus, setTogglingStatus] = useState<Record<string, boolean>>({});

  // Schema Discovery Drawer State
  const [inspectingConn, setInspectingConn] = useState<any>(null);
  const [discoveredSchemaData, setDiscoveredSchemaData] = useState<any>(null);
  const [isLoadingSchema, setIsLoadingSchema] = useState(false);

  // Connection Setup Wizard State
  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null);
  const [showPasswordMap, setShowPasswordMap] = useState<Record<string, boolean>>({});
  const [preflightResult, setPreflightResult] = useState<any>(null);
  const [isPreflightRunning, setIsPreflightRunning] = useState(false);
  const [isCreatingConnection, setIsCreatingConnection] = useState(false);

  const [wizardForm, setWizardForm] = useState({
    id: "",
    name: "",
    connector_type: "CRM",
    provider: "salesforce",
    description: "",
    environment: "PRODUCTION",
    tenant_id: "default-enterprise",
    read_only: false,
    allowed_operations: ["READ", "SEARCH"],
    allowed_entities: "accounts, contacts",
    rate_limit_per_minute: 60,
    timeout_seconds: 10,
    max_retries: 3,
    config: {} as Record<string, any>,
    secrets: {} as Record<string, any>
  });

  // Load connections & templates
  const loadConnections = async () => {
    setLoadingConnections(true);
    try {
      const data = await api.listConnections();
      setConnections(data || []);
    } catch (e) {
      console.error("Failed to load enterprise connections", e);
    } finally {
      setLoadingConnections(false);
    }
  };

  const loadTemplates = async () => {
    try {
      const res = await api.getConnectionTemplates();
      setTemplates(res?.templates || []);
    } catch (e) {
      console.error("Failed to load connection templates", e);
    }
  };

  const loadRecords = async (origin?: string) => {
    setLoading(true);
    try {
      const data = await api.listRecords(origin);
      setRecords(data || []);
    } catch (e) {
      console.error("Failed to load records", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConnections();
    loadTemplates();
  }, []);

  useEffect(() => {
    if (activeTab === "crm") loadRecords(crmAdapter);
    else if (activeTab === "erp") loadRecords("COMPANY_B_ERP");
    else if (activeTab === "golden") loadRecords("GOLDEN_MASTER");
    else if (activeTab === "connections") loadConnections();
  }, [activeTab, crmAdapter]);

  // Connection Actions
  const handleTestConnection = async (id: string) => {
    setTestingStatus(prev => ({ ...prev, [id]: "testing" }));
    try {
      await api.testConnection(id);
      setTestingStatus(prev => ({ ...prev, [id]: "success" }));
      await loadConnections();
      setTimeout(() => {
        setTestingStatus(prev => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
      }, 3000);
    } catch (e: any) {
      setTestingStatus(prev => ({ ...prev, [id]: "error" }));
      alert(`Connection test failed: ${e.message}`);
    }
  };

  const handleToggleConnection = async (id: string, currentEnabled: boolean) => {
    setTogglingStatus(prev => ({ ...prev, [id]: true }));
    try {
      await api.toggleConnection(id, !currentEnabled);
      await loadConnections();
    } catch (e: any) {
      alert(`Toggle status failed: ${e.message}`);
    } finally {
      setTogglingStatus(prev => ({ ...prev, [id]: false }));
    }
  };

  const handleDeleteConnection = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to delete enterprise connection "${name}"? This action is cryptographically recorded in the audit ledger.`)) {
      return;
    }
    try {
      await api.deleteConnection(id);
      await loadConnections();
    } catch (e: any) {
      alert(`Failed to delete connection: ${e.message}`);
    }
  };

  const handleInspectSchema = async (conn: any) => {
    setInspectingConn(conn);
    setIsLoadingSchema(true);
    setDiscoveredSchemaData(null);
    try {
      const res = await api.discoverConnectionSchema(conn.id);
      setDiscoveredSchemaData(res?.discovered_schema || []);
    } catch (e: any) {
      alert(`Schema introspection error: ${e.message}`);
    } finally {
      setIsLoadingSchema(false);
    }
  };

  // M1 Duplicate Intelligence Scan
  const handleScanDuplicates = async (record: any) => {
    setCrmSelectedRecord(record);
    setIsM1Scanning(true);
    setShowM1Modal(true);
    setM1Result(null);

    try {
      const res = await api.predictModel("entity_resolution", {
        query: {
          entity_id: record.id,
          business_name: record.name,
          business_address: record.address || "",
          country: record.country || "US",
          source_system: record.system_origin || "CRM"
        },
        candidates: records
          .filter(r => r.id !== record.id)
          .map(r => ({
            entity_id: r.id,
            business_name: r.name,
            business_address: r.address || "",
            country: r.country || "US",
            source_system: r.system_origin || "CRM"
          }))
      });
      setM1Result(res.prediction || res);
    } catch (e: any) {
      alert(`Model M1 Duplicate Resolution Error: ${e.message}`);
      setShowM1Modal(false);
    } finally {
      setIsM1Scanning(false);
    }
  };

  // Wizard Lifecycle
  const openWizard = (template?: any) => {
    const t = template || (templates.length > 0 ? templates[0] : null);
    setSelectedTemplate(t);
    setWizardStep(1);
    setPreflightResult(null);

    const initConfig: Record<string, any> = {};
    if (t?.config_schema) {
      t.config_schema.forEach((f: any) => {
        initConfig[f.key] = f.placeholder || "";
      });
    }

    const initSecrets: Record<string, any> = {};
    if (t?.secret_schema) {
      t.secret_schema.forEach((s: any) => {
        initSecrets[s.key] = "";
      });
    }

    setWizardForm({
      id: "",
      name: t ? `${t.display_name} Instance` : "",
      connector_type: t ? t.connector_type : "CRM",
      provider: t ? t.provider : "salesforce",
      description: t ? t.description : "",
      environment: "PRODUCTION",
      tenant_id: "default-enterprise",
      read_only: false,
      allowed_operations: t?.supported_operations || ["READ", "SEARCH"],
      allowed_entities: t?.default_entities?.join(", ") || "",
      rate_limit_per_minute: 60,
      timeout_seconds: 10,
      max_retries: 3,
      config: initConfig,
      secrets: initSecrets
    });
    setShowWizard(true);
  };

  const selectWizardTemplate = (t: any) => {
    setSelectedTemplate(t);
    const initConfig: Record<string, any> = {};
    t.config_schema?.forEach((f: any) => {
      initConfig[f.key] = f.placeholder || "";
    });

    const initSecrets: Record<string, any> = {};
    t.secret_schema?.forEach((s: any) => {
      initSecrets[s.key] = "";
    });

    setWizardForm(prev => ({
      ...prev,
      name: `${t.display_name} Instance`,
      connector_type: t.connector_type,
      provider: t.provider,
      description: t.description,
      allowed_operations: t.supported_operations || ["READ", "SEARCH"],
      allowed_entities: t.default_entities?.join(", ") || "",
      config: initConfig,
      secrets: initSecrets
    }));
  };

  const handleRunPreflight = async () => {
    setIsPreflightRunning(true);
    setPreflightResult(null);
    try {
      const res = await api.testPreflightConnection({
        connector_type: wizardForm.connector_type,
        provider: wizardForm.provider,
        config: wizardForm.config,
        secrets: wizardForm.secrets
      });
      setPreflightResult(res);
    } catch (e: any) {
      setPreflightResult({
        status: "AUTHENTICATION_FAILED",
        message: e.message || "Failed pre-flight network probe.",
        latency_ms: 0.0
      });
    } finally {
      setIsPreflightRunning(false);
    }
  };

  const handleSaveConnection = async () => {
    setIsCreatingConnection(true);
    try {
      const entitiesList = wizardForm.allowed_entities
        ? wizardForm.allowed_entities.split(",").map(s => s.trim()).filter(Boolean)
        : [];

      await api.createConnection({
        id: wizardForm.id.trim() || undefined,
        name: wizardForm.name,
        connector_type: wizardForm.connector_type,
        provider: wizardForm.provider,
        description: wizardForm.description,
        environment: wizardForm.environment,
        tenant_id: wizardForm.tenant_id,
        read_only: wizardForm.read_only,
        allowed_operations: wizardForm.allowed_operations,
        allowed_entities: entitiesList,
        config: {
          ...wizardForm.config,
          rate_limit_per_minute: Number(wizardForm.rate_limit_per_minute),
          timeout_seconds: Number(wizardForm.timeout_seconds),
          max_retries: Number(wizardForm.max_retries)
        },
        secrets: wizardForm.secrets
      });

      setShowWizard(false);
      await loadConnections();
    } catch (e: any) {
      alert(`Error saving connection: ${e.message}`);
    } finally {
      setIsCreatingConnection(false);
    }
  };

  // Original records handler
  const handleCreateRecord = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRecordName) return;

    try {
      await api.createRecord({
        business_name: newRecordName,
        business_address: newRecordAddress,
        tax_identifier: newRecordTaxId,
        contact_email: newRecordEmail || undefined,
        country: "US",
        system_origin: crmAdapter,
      });
      setShowNewRecordModal(false);
      setNewRecordName("");
      setNewRecordAddress("");
      setNewRecordTaxId("");
      setNewRecordEmail("");
      await loadRecords(crmAdapter);
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

  // Filtered connections list
  const filteredConnections = connections.filter(c => {
    if (filterType !== "ALL" && c.connector_type !== filterType) return false;
    if (searchConnQuery) {
      const q = searchConnQuery.toLowerCase();
      return (
        c.name.toLowerCase().includes(q) ||
        c.provider.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q) ||
        (c.description && c.description.toLowerCase().includes(q))
      );
    }
    return true;
  });

  // Filtered CRM records
  const filteredRecords = records.filter(r => {
    if (!crmSearchQuery) return true;
    const q = crmSearchQuery.toLowerCase();
    return (
      (r.name && r.name.toLowerCase().includes(q)) ||
      (r.id && r.id.toLowerCase().includes(q)) ||
      (r.tax_identifier && r.tax_identifier.toLowerCase().includes(q)) ||
      (r.contact_email && r.contact_email.toLowerCase().includes(q)) ||
      (r.address && r.address.toLowerCase().includes(q))
    );
  });

  const getProviderIcon = (type: string) => {
    switch (type?.toUpperCase()) {
      case "CRM":
        return <Users className="h-4 w-4 text-[#00E5FF]" />;
      case "ERP":
        return <Building2 className="h-4 w-4 text-[#A855F7]" />;
      case "DATABASE":
        return <Database className="h-4 w-4 text-[#388BFD]" />;
      case "EMAIL":
        return <Mail className="h-4 w-4 text-[#F59E0B]" />;
      default:
        return <Server className="h-4 w-4 text-[#10B981]" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-[#00E5FF]" />
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              Enterprise Data Hub & Connection Engine
              <span className="rounded bg-[#00E5FF]/10 px-2 py-0.5 font-mono text-[10px] font-bold text-[#00E5FF] border border-[#00E5FF]/30">
                ACTIVE
              </span>
            </h1>
          </div>
          <p className="text-xs text-[#8B949E] mt-0.5">
            Configure dynamic enterprise integrations with zero source-code modification, AES-256 encrypted credential isolation, and least-privilege policies.
          </p>
        </div>

        {/* Sub-tab Navigation */}
        <div className="flex flex-wrap rounded-lg border border-[#30363D] bg-[#161B22] p-1 text-xs">
          <button
            onClick={() => setActiveTab("connections")}
            className={`rounded-md px-3 py-1 font-semibold transition-colors flex items-center gap-1.5 ${
              activeTab === "connections" ? "bg-[#00E5FF] text-black shadow-sm" : "text-[#8B949E] hover:text-white"
            }`}
          >
            <Server className="h-3.5 w-3.5" />
            Enterprise Connections ({connections.length})
          </button>
          <button
            onClick={() => setActiveTab("crm")}
            className={`rounded-md px-3 py-1 font-semibold transition-colors flex items-center gap-1.5 ${
              activeTab === "crm" ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
            }`}
          >
            <Users className="h-3.5 w-3.5" />
            CRM Hub (Live Sync)
          </button>
          <button
            onClick={() => setActiveTab("erp")}
            className={`rounded-md px-3 py-1 font-medium transition-colors ${
              activeTab === "erp" ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
            }`}
          >
            ERP Vendors
          </button>
          <button
            onClick={() => setActiveTab("golden")}
            className={`rounded-md px-3 py-1 font-medium transition-colors ${
              activeTab === "golden" ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
            }`}
          >
            Golden Records
          </button>
          <button
            onClick={() => setActiveTab("schema")}
            className={`rounded-md px-3 py-1 font-medium transition-colors ${
              activeTab === "schema" ? "bg-[#1F6FEB] text-white" : "text-[#8B949E] hover:text-white"
            }`}
          >
            Schema Drift (M6)
          </button>
        </div>
      </div>

      {/* ============================================================== */}
      {/* ENTERPRISE CONNECTIONS TAB                                     */}
      {/* ============================================================== */}
      {activeTab === "connections" && (
        <div className="space-y-5 animate-in fade-in duration-200">
          {/* Action HUD Bar */}
          <div className="flex flex-col gap-3 rounded-xl border border-[#21262D] bg-[#0E1117] p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            {/* Filters */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-[#8B949E]" />
                <input
                  type="text"
                  placeholder="Filter connections..."
                  value={searchConnQuery}
                  onChange={(e) => setSearchConnQuery(e.target.value)}
                  className="rounded-lg border border-[#30363D] bg-[#161B22] pl-8 pr-3 py-1.5 text-xs text-white placeholder-[#8B949E] focus:border-[#00E5FF] focus:outline-none w-48"
                />
              </div>

              {["ALL", "CRM", "ERP", "DATABASE", "EMAIL"].map((t) => (
                <button
                  key={t}
                  onClick={() => setFilterType(t)}
                  className={`rounded-lg px-2.5 py-1.5 font-mono text-[11px] font-semibold transition-colors ${
                    filterType === t
                      ? "bg-[#21262D] text-[#00E5FF] border border-[#00E5FF]/40"
                      : "text-[#8B949E] hover:bg-[#161B22] hover:text-white"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            {/* Launch Wizard Button */}
            <div className="flex items-center gap-2">
              <button
                onClick={loadConnections}
                title="Refresh Connections"
                className="flex items-center gap-1 rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-1.5 text-xs font-semibold text-[#8B949E] hover:text-white transition-colors"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loadingConnections ? "animate-spin" : ""}`} />
                Sync
              </button>
              <button
                onClick={() => openWizard()}
                className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-[#00E5FF] to-[#0070F3] px-3.5 py-1.5 text-xs font-bold text-black shadow-md shadow-[#00E5FF]/20 hover:opacity-95 transition-all"
              >
                <Plus className="h-4 w-4" />
                Connect Enterprise System
              </button>
            </div>
          </div>

          {/* Connection Cards Grid */}
          {loadingConnections ? (
            <div className="flex h-48 items-center justify-center rounded-xl border border-[#21262D] bg-[#0E1117]">
              <div className="flex items-center gap-2 text-xs text-[#8B949E]">
                <RefreshCw className="h-4 w-4 animate-spin text-[#00E5FF]" />
                Querying encrypted enterprise connection registry...
              </div>
            </div>
          ) : filteredConnections.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-[#21262D] bg-[#0E1117] py-12 text-center">
              <Server className="h-10 w-10 text-[#484F58] mb-3" />
              <h3 className="text-sm font-bold text-white">No Connections Found</h3>
              <p className="text-xs text-[#8B949E] mt-1 max-w-sm">
                No enterprise connectors match your query. Use the connection wizard to dynamically configure new CRM, ERP, database, or email integrations.
              </p>
              <button
                onClick={() => openWizard()}
                className="mt-4 flex items-center gap-1.5 rounded-lg bg-[#00E5FF] px-3 py-1.5 text-xs font-bold text-black shadow"
              >
                <Plus className="h-3.5 w-3.5" />
                Launch Setup Wizard
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {filteredConnections.map((conn) => {
                const isConnTesting = testingStatus[conn.id] === "testing";
                const isConnSuccess = testingStatus[conn.id] === "success";
                const isConnToggling = togglingStatus[conn.id];

                return (
                  <div
                    key={conn.id}
                    className="flex flex-col justify-between rounded-xl border border-[#21262D] bg-[#0E1117] p-5 shadow-sm hover:border-[#30363D] transition-all"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-2.5">
                          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#30363D] bg-[#161B22]">
                            {getProviderIcon(conn.connector_type)}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="text-sm font-bold text-white">{conn.name}</h3>
                              <span className="font-mono text-[10px] text-[#8B949E]">({conn.id})</span>
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="rounded bg-[#21262D] px-1.5 py-0.5 font-mono text-[9px] font-bold text-[#00E5FF] uppercase">
                                {conn.connector_type}
                              </span>
                              <span className="font-mono text-[10px] text-[#8B949E] uppercase">
                                Provider: {conn.provider}
                              </span>
                              <span className="rounded bg-[#161B22] border border-[#30363D] px-1.5 py-0.2 font-mono text-[9px] text-[#8B949E]">
                                {conn.environment}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Status Pill */}
                        <div className="flex items-center gap-1.5">
                          {conn.is_enabled ? (
                            <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                              conn.status === "CONNECTED"
                                ? "bg-[#238636]/20 text-[#3FB950] border border-[#238636]/40"
                                : conn.status === "DEGRADED"
                                ? "bg-[#D29922]/20 text-[#D29922] border border-[#D29922]/40"
                                : "bg-[#DA3633]/20 text-[#F85149] border border-[#DA3633]/40"
                            }`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${
                                conn.status === "CONNECTED" ? "bg-[#3FB950] animate-pulse" : "bg-[#F85149]"
                              }`} />
                              {conn.status}
                            </span>
                          ) : (
                            <span className="flex items-center gap-1.5 rounded-full bg-[#30363D]/40 px-2.5 py-0.5 text-[10px] font-bold text-[#8B949E] border border-[#30363D]">
                              <span className="h-1.5 w-1.5 rounded-full bg-[#8B949E]" />
                              DISABLED
                            </span>
                          )}
                        </div>
                      </div>

                      {conn.description && (
                        <p className="mt-3 text-xs text-[#8B949E] line-clamp-2">
                          {conn.description}
                        </p>
                      )}

                      {/* Security Metadata Badges */}
                      <div className="mt-4 grid grid-cols-2 gap-2 text-[11px] font-mono">
                        <div className="rounded-lg border border-[#21262D] bg-[#161B22] p-2">
                          <div className="flex items-center gap-1.5 text-[#8B949E] text-[10px] uppercase font-bold">
                            <Lock className="h-3 w-3 text-[#3FB950]" />
                            Least-Privilege Policy
                          </div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {conn.read_only ? (
                              <span className="rounded bg-[#F85149]/20 px-1.5 py-0.2 text-[9px] font-bold text-[#F85149]">
                                READ-ONLY
                              </span>
                            ) : (
                              <span className="rounded bg-[#3FB950]/20 px-1.5 py-0.2 text-[9px] font-bold text-[#3FB950]">
                                READ / WRITE
                              </span>
                            )}
                            {conn.allowed_operations?.slice(0, 2).map((op: string) => (
                              <span key={op} className="rounded bg-[#21262D] px-1 py-0.2 text-[9px] text-[#C9D1D9]">
                                {op}
                              </span>
                            ))}
                            {conn.allowed_operations?.length > 2 && (
                              <span className="text-[9px] text-[#8B949E]">
                                +{conn.allowed_operations.length - 2}
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="rounded-lg border border-[#21262D] bg-[#161B22] p-2">
                          <div className="flex items-center gap-1.5 text-[#8B949E] text-[10px] uppercase font-bold">
                            <Key className="h-3 w-3 text-[#00E5FF]" />
                            AES-256 Vault Secrets
                          </div>
                          <div className="mt-1 text-[10px] text-[#00E5FF] font-semibold truncate">
                            {conn.configured_secret_keys?.length > 0
                              ? `${conn.configured_secret_keys.length} Credential(s) Isolated`
                              : "No Vault Credentials"}
                          </div>
                        </div>
                      </div>

                      {/* Health Check Details */}
                      <div className="mt-2.5 flex items-center justify-between rounded-lg bg-[#161B22]/50 px-3 py-1.5 text-[10px] text-[#8B949E] font-mono">
                        <div className="flex items-center gap-1.5">
                          <Activity className="h-3 w-3 text-[#00E5FF]" />
                          <span>
                            Latency: <strong className="text-white">{conn.last_health_check?.latency_ms || 0} ms</strong>
                          </span>
                        </div>
                        <div className="truncate max-w-[200px]">
                          {conn.last_health_check?.message || "Operational"}
                        </div>
                      </div>
                    </div>

                    {/* Card Actions Bottom */}
                    <div className="mt-4 flex items-center justify-between border-t border-[#21262D] pt-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleTestConnection(conn.id)}
                          disabled={isConnTesting || !conn.is_enabled}
                          className="flex items-center gap-1 rounded-md border border-[#30363D] bg-[#161B22] px-2.5 py-1 text-xs font-semibold text-[#C9D1D9] hover:border-[#00E5FF] hover:text-white disabled:opacity-50 transition-colors"
                        >
                          <RefreshCw className={`h-3 w-3 ${isConnTesting ? "animate-spin text-[#00E5FF]" : ""}`} />
                          {isConnTesting ? "Pinging..." : isConnSuccess ? "Healthy!" : "Test Link"}
                        </button>

                        <button
                          onClick={() => handleInspectSchema(conn)}
                          disabled={!conn.is_enabled}
                          className="flex items-center gap-1 rounded-md border border-[#30363D] bg-[#161B22] px-2.5 py-1 text-xs font-semibold text-[#00E5FF] hover:bg-[#00E5FF]/10 disabled:opacity-50 transition-colors"
                        >
                          <Database className="h-3 w-3" />
                          Discover Schema
                        </button>
                      </div>

                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleToggleConnection(conn.id, conn.is_enabled)}
                          disabled={isConnToggling}
                          title={conn.is_enabled ? "Disable connection" : "Enable connection"}
                          className={`p-1.5 rounded-md border transition-colors ${
                            conn.is_enabled
                              ? "border-[#238636]/40 text-[#3FB950] hover:bg-[#238636]/20"
                              : "border-[#30363D] text-[#8B949E] hover:text-white"
                          }`}
                        >
                          <Power className="h-3.5 w-3.5" />
                        </button>

                        <button
                          onClick={() => handleDeleteConnection(conn.id, conn.name)}
                          title="Delete Connection"
                          className="p-1.5 rounded-md text-[#8B949E] hover:text-[#F85149] hover:bg-[#F85149]/10 transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ============================================================== */}
      {/* CRM INTEGRATION TAB (STAGE 6 ROADMAP REQUIREMENT)              */}
      {/* ============================================================== */}
      {activeTab === "crm" && (
        <div className="space-y-4 animate-in fade-in duration-200">
          {/* CRM Control HUD */}
          <div className="flex flex-col gap-3 rounded-xl border border-[#21262D] bg-[#0E1117] p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            {/* Adapter Selector & Search */}
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex rounded-lg border border-[#30363D] bg-[#161B22] p-1 text-xs font-mono">
                <button
                  onClick={() => setCrmAdapter("COMPANY_A_CRM")}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-bold transition-colors ${
                    crmAdapter === "COMPANY_A_CRM"
                      ? "bg-[#1F6FEB] text-white"
                      : "text-[#8B949E] hover:text-white"
                  }`}
                >
                  Adapter 1: Salesforce / Company A
                </button>
                <button
                  onClick={() => setCrmAdapter("HUBSPOT_CRM")}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-bold transition-colors ${
                    crmAdapter === "HUBSPOT_CRM"
                      ? "bg-[#1F6FEB] text-white"
                      : "text-[#8B949E] hover:text-white"
                  }`}
                >
                  Adapter 2: HubSpot CRM
                </button>
              </div>

              {/* Search Field */}
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-[#8B949E]" />
                <input
                  type="text"
                  placeholder="Search accounts, tax IDs, emails..."
                  value={crmSearchQuery}
                  onChange={(e) => setCrmSearchQuery(e.target.value)}
                  className="rounded-lg border border-[#30363D] bg-[#161B22] pl-8 pr-3 py-1.5 text-xs text-white placeholder-[#8B949E] focus:border-[#58A6FF] focus:outline-none w-56"
                />
              </div>
            </div>

            {/* Create Record Button */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => loadRecords(crmAdapter)}
                className="flex items-center gap-1 rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-1.5 text-xs font-semibold text-[#8B949E] hover:text-white"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                Sync
              </button>
              <button
                onClick={() => setShowNewRecordModal(true)}
                className="flex items-center gap-1.5 rounded-lg bg-[#238636] px-3.5 py-1.5 text-xs font-bold text-white shadow hover:bg-[#2EA043]"
              >
                <Plus className="h-4 w-4" />
                New Customer Account
              </button>
            </div>
          </div>

          {/* CRM Records Table */}
          <div className="overflow-hidden rounded-xl border border-[#21262D] bg-[#0E1117] shadow-sm">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[#21262D] bg-[#161B22] font-semibold text-[#8B949E]">
                <tr>
                  <th className="px-4 py-3">Record ID</th>
                  <th className="px-4 py-3">Account / Legal Name</th>
                  <th className="px-4 py-3">Billing Address</th>
                  <th className="px-4 py-3">Tax / EIN</th>
                  <th className="px-4 py-3">Contact Email</th>
                  <th className="px-4 py-3">Canonical ID</th>
                  <th className="px-4 py-3 text-right">M1 Intelligence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#21262D] font-mono text-[#E6EDF3]">
                {loading ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-[#8B949E]">
                      Loading CRM records...
                    </td>
                  </tr>
                ) : filteredRecords.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-[#8B949E]">
                      No CRM records found for this adapter partition.
                    </td>
                  </tr>
                ) : (
                  filteredRecords.map((r) => (
                    <tr key={r.id} className="hover:bg-[#161B22]/50">
                      <td className="px-4 py-3 text-[#58A6FF]">{r.id}</td>
                      <td className="px-4 py-3 font-sans font-medium text-white">{r.name}</td>
                      <td className="px-4 py-3 font-sans text-[#8B949E] truncate max-w-xs">{r.address || "N/A"}</td>
                      <td className="px-4 py-3">{r.tax_identifier || "N/A"}</td>
                      <td className="px-4 py-3 text-[#8B949E]">{r.contact_email || "N/A"}</td>
                      <td className="px-4 py-3 text-[#3FB950] font-semibold">
                        {r.canonical_id || "UNLINKED"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleScanDuplicates(r)}
                          className="flex items-center gap-1 rounded bg-[#1F6FEB]/20 px-2 py-1 text-[11px] font-bold text-[#58A6FF] hover:bg-[#1F6FEB]/30 ml-auto"
                        >
                          <Sparkles className="h-3 w-3 text-[#58A6FF]" />
                          Scan M1
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* ERP VENDORS TAB                                                */}
      {/* ============================================================== */}
      {activeTab === "erp" && (
        <div className="space-y-4 animate-in fade-in duration-200">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#8B949E]">
              Company B ERP Vendors ({records.length})
            </span>
          </div>

          <div className="overflow-hidden rounded-xl border border-[#21262D] bg-[#0E1117] shadow-sm">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[#21262D] bg-[#161B22] font-semibold text-[#8B949E]">
                <tr>
                  <th className="px-4 py-3">Vendor ID</th>
                  <th className="px-4 py-3">Business Entity Name</th>
                  <th className="px-4 py-3">Address</th>
                  <th className="px-4 py-3">Tax Identifier</th>
                  <th className="px-4 py-3">Canonical ID</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#21262D] font-mono text-[#E6EDF3]">
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-[#8B949E]">
                      Loading ERP vendor master...
                    </td>
                  </tr>
                ) : records.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-[#8B949E]">
                      No ERP records in this partition.
                    </td>
                  </tr>
                ) : (
                  records.map((r) => (
                    <tr key={r.id} className="hover:bg-[#161B22]/50">
                      <td className="px-4 py-3 text-[#A855F7]">{r.id}</td>
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
      )}

      {/* ============================================================== */}
      {/* GOLDEN RECORDS TAB                                             */}
      {/* ============================================================== */}
      {activeTab === "golden" && (
        <div className="space-y-4 animate-in fade-in duration-200">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#8B949E]">
              Consolidated Golden Master Entities ({records.length})
            </span>
          </div>

          <div className="overflow-hidden rounded-xl border border-[#21262D] bg-[#0E1117] shadow-sm">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[#21262D] bg-[#161B22] font-semibold text-[#8B949E]">
                <tr>
                  <th className="px-4 py-3">Golden ID</th>
                  <th className="px-4 py-3">Entity Name</th>
                  <th className="px-4 py-3">Normalized Address</th>
                  <th className="px-4 py-3">Tax / EIN</th>
                  <th className="px-4 py-3">Lineage Pointers</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#21262D] font-mono text-[#E6EDF3]">
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-[#8B949E]">
                      Loading golden master entities...
                    </td>
                  </tr>
                ) : records.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-[#8B949E]">
                      No golden records created yet. Run customer onboarding or duplicate resolution to merge entities.
                    </td>
                  </tr>
                ) : (
                  records.map((r) => (
                    <tr key={r.id} className="hover:bg-[#161B22]/50">
                      <td className="px-4 py-3 text-[#3FB950] font-bold">{r.id}</td>
                      <td className="px-4 py-3 font-sans font-medium text-white">{r.name}</td>
                      <td className="px-4 py-3 font-sans text-[#8B949E] truncate max-w-xs">{r.address}</td>
                      <td className="px-4 py-3">{r.tax_identifier || "N/A"}</td>
                      <td className="px-4 py-3 text-[#58A6FF]">
                        {r.canonical_id || "MULTI-ORIGIN"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-[#238636]/20 px-1.5 py-0.5 text-[10px] font-bold text-[#3FB950]">
                          MASTER ACTIVE
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* SCHEMA DRIFT VIEW (MODEL M6)                                   */}
      {/* ============================================================== */}
      {activeTab === "schema" && (
        <div className="space-y-6 animate-in fade-in duration-200">
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

      {/* ============================================================== */}
      {/* MODEL M1 DUPLICATE RESOLUTION SCAN MODAL                       */}
      {/* ============================================================== */}
      {showM1Modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
          <div className="w-full max-w-2xl rounded-2xl border border-[#30363D] bg-[#0E1117] shadow-2xl flex flex-col max-h-[85vh] overflow-hidden">
            <div className="flex items-center justify-between border-b border-[#21262D] px-6 py-4">
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-[#58A6FF]" />
                <div>
                  <h3 className="text-sm font-bold text-white">
                    Model M1 Entity Resolution & Duplicate Detection
                  </h3>
                  <span className="font-mono text-[10px] text-[#8B949E]">
                    Query: {crmSelectedRecord?.name} ({crmSelectedRecord?.id})
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowM1Modal(false)}
                className="rounded-lg p-1 text-[#8B949E] hover:bg-[#21262D] hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {isM1Scanning ? (
                <div className="flex h-40 items-center justify-center text-xs text-[#8B949E] gap-2">
                  <RefreshCw className="h-4 w-4 animate-spin text-[#58A6FF]" />
                  Evaluating pairwise lexical and address features via LightGBM...
                </div>
              ) : !m1Result ? (
                <div className="text-center py-8 text-xs text-[#8B949E]">
                  No matching analysis generated.
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Top Verdict Banner */}
                  <div className="flex items-center justify-between rounded-xl border border-[#58A6FF]/30 bg-[#58A6FF]/10 p-4">
                    <div>
                      <span className="text-xs font-bold text-white uppercase font-mono">
                        M1 Verdict: {m1Result.decision || "MATCH_ANALYSIS_COMPLETE"}
                      </span>
                      <p className="text-[11px] text-[#8B949E] mt-0.5">
                        Matches found: {m1Result.matches?.length || 0} candidate(s) evaluated against live enterprise database.
                      </p>
                    </div>
                    {m1Result.matches && m1Result.matches.length > 0 && (
                      <span className="rounded bg-[#58A6FF] px-2.5 py-1 text-xs font-bold text-black font-mono">
                        {Math.round(m1Result.matches[0].match_probability * 100)}% Match
                      </span>
                    )}
                  </div>

                  {/* Candidate Match List */}
                  {m1Result.matches?.map((m: any, idx: number) => (
                    <div key={idx} className="rounded-xl border border-[#21262D] bg-[#161B22] p-4 text-xs font-mono space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-white text-sm">
                          {m.target_business_name}
                        </span>
                        <span className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                          m.match_probability >= 0.85
                            ? "bg-[#238636]/20 text-[#3FB950] border border-[#238636]/40"
                            : "bg-[#D29922]/20 text-[#D29922] border border-[#D29922]/40"
                        }`}>
                          {m.status} (Prob: {m.match_probability})
                        </span>
                      </div>
                      <p className="text-[#8B949E] text-[11px]">
                        Target ID: <strong className="text-[#58A6FF]">{m.target_entity_id}</strong> • System: {m.source_system}
                      </p>
                      {m.target_business_address && (
                        <p className="text-[#8B949E] text-[11px]">
                          Address: {m.target_business_address}
                        </p>
                      )}
                      {m.evidence && (
                        <div className="mt-2 rounded bg-[#0E1117] p-2 text-[10px] text-[#8B949E] border border-[#21262D]">
                          <span>Token Overlap: {m.evidence.token_overlap?.join(", ") || "None"}</span> •{" "}
                          <span>Jaccard: {m.evidence.jaccard_similarity}</span> •{" "}
                          <span>Address Num Match: {m.evidence.address_number_match ? "YES" : "NO"}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex justify-end border-t border-[#21262D] px-6 py-3 bg-[#161B22]/50">
              <button
                type="button"
                onClick={() => setShowM1Modal(false)}
                className="rounded-lg bg-[#21262D] px-4 py-1.5 text-xs font-bold text-white hover:bg-[#30363D]"
              >
                Close Analysis
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* ADMINISTRATOR CONNECTION SETUP WIZARD                          */}
      {/* ============================================================== */}
      {showWizard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
          <div className="w-full max-w-2xl rounded-2xl border border-[#30363D] bg-[#0E1117] shadow-2xl flex flex-col max-h-[90vh] overflow-hidden">
            {/* Wizard Header */}
            <div className="flex items-center justify-between border-b border-[#21262D] px-6 py-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="rounded bg-[#00E5FF]/20 px-2 py-0.5 font-mono text-[10px] font-bold text-[#00E5FF]">
                    STEP {wizardStep} OF 4
                  </span>
                  <h3 className="text-base font-bold text-white">
                    {wizardStep === 1 && "Select Enterprise Provider & Category"}
                    {wizardStep === 2 && "Configure Connection Identity & Perimeter"}
                    {wizardStep === 3 && "Vault Credentials & Security Policies"}
                    {wizardStep === 4 && "Pre-Flight Health Verification & Activation"}
                  </h3>
                </div>
                <p className="text-xs text-[#8B949E] mt-0.5">
                  Connect supported CRM, ERP, relational database, or email system without editing source code.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowWizard(false)}
                className="rounded-lg p-1 text-[#8B949E] hover:bg-[#21262D] hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Wizard Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {/* STEP 1: Provider Discovery Catalog */}
              {wizardStep === 1 && (
                <div className="space-y-4">
                  <span className="text-xs font-bold text-[#8B949E] uppercase tracking-wider block">
                    Supported Systems Catalog ({templates.length})
                  </span>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {templates.map((tpl) => {
                      const isSelected = selectedTemplate?.provider === tpl.provider;
                      return (
                        <div
                          key={tpl.provider}
                          onClick={() => selectWizardTemplate(tpl)}
                          className={`cursor-pointer rounded-xl border p-4 transition-all flex flex-col justify-between ${
                            isSelected
                              ? "border-[#00E5FF] bg-[#00E5FF]/5 shadow-sm shadow-[#00E5FF]/20"
                              : "border-[#21262D] bg-[#161B22] hover:border-[#30363D]"
                          }`}
                        >
                          <div>
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <div className="p-1.5 rounded-lg bg-[#21262D]">
                                  {getProviderIcon(tpl.connector_type)}
                                </div>
                                <span className="font-bold text-sm text-white">{tpl.display_name}</span>
                              </div>
                              <span className="font-mono text-[9px] font-bold uppercase rounded bg-[#21262D] px-1.5 py-0.5 text-[#00E5FF]">
                                {tpl.connector_type}
                              </span>
                            </div>
                            <p className="mt-2 text-xs text-[#8B949E] line-clamp-2">
                              {tpl.description}
                            </p>
                          </div>
                          <div className="mt-3 flex items-center justify-between border-t border-[#21262D]/60 pt-2 text-[10px] font-mono text-[#8B949E]">
                            <span>Auth: {tpl.auth_methods?.join(", ") || "Standard"}</span>
                            {isSelected && <Check className="h-3.5 w-3.5 text-[#00E5FF]" />}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* STEP 2: Identity & Basics */}
              {wizardStep === 2 && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-[#8B949E]">
                      Connection Display Name <span className="text-[#F85149]">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={wizardForm.name}
                      onChange={(e) => setWizardForm({ ...wizardForm, name: e.target.value })}
                      placeholder="e.g. Salesforce North America Production"
                      className="mt-1 w-full rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-2 text-xs text-white focus:border-[#00E5FF] focus:outline-none"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-[#8B949E]">
                        Unique Connection ID (Slug)
                      </label>
                      <input
                        type="text"
                        value={wizardForm.id}
                        onChange={(e) => setWizardForm({ ...wizardForm, id: e.target.value })}
                        placeholder="Auto-generated if empty"
                        className="mt-1 w-full rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-2 text-xs font-mono text-white focus:border-[#00E5FF] focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-[#8B949E]">
                        Target Environment
                      </label>
                      <select
                        value={wizardForm.environment}
                        onChange={(e) => setWizardForm({ ...wizardForm, environment: e.target.value })}
                        className="mt-1 w-full rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-2 text-xs text-white focus:border-[#00E5FF] focus:outline-none"
                      >
                        <option value="PRODUCTION">PRODUCTION</option>
                        <option value="STAGING">STAGING</option>
                        <option value="DEVELOPMENT">DEVELOPMENT</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#8B949E]">
                      Description & Business Purpose
                    </label>
                    <textarea
                      rows={2}
                      value={wizardForm.description}
                      onChange={(e) => setWizardForm({ ...wizardForm, description: e.target.value })}
                      placeholder="e.g. Core CRM synchronization for sales opportunities and client identity."
                      className="mt-1 w-full rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-2 text-xs text-white focus:border-[#00E5FF] focus:outline-none"
                    />
                  </div>

                  {selectedTemplate?.config_schema && selectedTemplate.config_schema.length > 0 && (
                    <div className="border-t border-[#21262D] pt-3 space-y-3">
                      <span className="text-xs font-bold text-white uppercase tracking-wider block">
                        Network Endpoint Configuration
                      </span>
                      {selectedTemplate.config_schema.map((f: any) => (
                        <div key={f.key}>
                          <label className="block text-xs font-semibold text-[#8B949E]">
                            {f.label} {f.required && <span className="text-[#F85149]">*</span>}
                          </label>
                          <input
                            type={f.type === "number" ? "number" : "text"}
                            required={f.required}
                            value={wizardForm.config[f.key] || ""}
                            onChange={(e) =>
                              setWizardForm({
                                ...wizardForm,
                                config: { ...wizardForm.config, [f.key]: e.target.value }
                              })
                            }
                            placeholder={f.placeholder}
                            className="mt-1 w-full rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-2 text-xs font-mono text-white focus:border-[#00E5FF] focus:outline-none"
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* STEP 3: Vault Credentials & Least Privilege */}
              {wizardStep === 3 && (
                <div className="space-y-5">
                  <div className="flex items-start gap-2.5 rounded-xl border border-[#00E5FF]/30 bg-[#00E5FF]/10 p-3 text-xs">
                    <ShieldCheck className="h-4 w-4 text-[#00E5FF] mt-0.5 shrink-0" />
                    <div>
                      <span className="font-bold text-white">Cryptographic Vault Isolation Enforced:</span>
                      <p className="text-[#8B949E] mt-0.5">
                        Credentials entered below are encrypted immediately via AES-256 PBKDF2 vault on the server. They are never rendered or transmitted to browser bundles.
                      </p>
                    </div>
                  </div>

                  {selectedTemplate?.secret_schema && selectedTemplate.secret_schema.length > 0 ? (
                    <div className="space-y-3">
                      <span className="text-xs font-bold text-white uppercase tracking-wider block">
                        Authentication Secrets
                      </span>
                      {selectedTemplate.secret_schema.map((s: any) => {
                        const isVisible = showPasswordMap[s.key];
                        return (
                          <div key={s.key}>
                            <label className="block text-xs font-semibold text-[#8B949E]">
                              {s.label} {s.required && <span className="text-[#F85149]">*</span>}
                            </label>
                            <div className="relative mt-1">
                              <input
                                type={isVisible ? "text" : "password"}
                                required={s.required}
                                value={wizardForm.secrets[s.key] || ""}
                                onChange={(e) =>
                                  setWizardForm({
                                    ...wizardForm,
                                    secrets: { ...wizardForm.secrets, [s.key]: e.target.value }
                                  })
                                }
                                placeholder="Enter secure token or key"
                                className="w-full rounded-lg border border-[#30363D] bg-[#161B22] px-3 py-2 pr-10 text-xs font-mono text-white focus:border-[#00E5FF] focus:outline-none"
                              />
                              <button
                                type="button"
                                onClick={() =>
                                  setShowPasswordMap({ ...showPasswordMap, [s.key]: !isVisible })
                                }
                                className="absolute right-2.5 top-2.5 text-[#8B949E] hover:text-white"
                              >
                                {isVisible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="rounded-lg border border-[#21262D] bg-[#161B22] p-3 text-xs text-[#8B949E]">
                      This connector provider does not require explicit secret credentials.
                    </div>
                  )}

                  <div className="border-t border-[#21262D] pt-4 space-y-4">
                    <span className="text-xs font-bold text-white uppercase tracking-wider block">
                      Least-Privilege & Resilience Constraints
                    </span>

                    <div className="flex items-center justify-between rounded-xl border border-[#21262D] bg-[#161B22] p-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <Lock className="h-3.5 w-3.5 text-[#3FB950]" />
                          <span className="text-xs font-bold text-white">Strict Read-Only Mode</span>
                        </div>
                        <p className="text-[11px] text-[#8B949E] mt-0.5">
                          Enforces read-only bounds. Autonomous AI agents and workflows cannot mutate or write records.
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={wizardForm.read_only}
                        onChange={(e) => setWizardForm({ ...wizardForm, read_only: e.target.checked })}
                        className="h-4 w-4 rounded accent-[#00E5FF]"
                      />
                    </div>

                    <div className="grid grid-cols-3 gap-3 font-mono text-xs">
                      <div>
                        <label className="text-[11px] text-[#8B949E] block mb-1">Max Req/Min</label>
                        <input
                          type="number"
                          value={wizardForm.rate_limit_per_minute}
                          onChange={(e) => setWizardForm({ ...wizardForm, rate_limit_per_minute: Number(e.target.value) })}
                          className="w-full rounded-lg border border-[#30363D] bg-[#161B22] px-2.5 py-1.5 text-xs text-white"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-[#8B949E] block mb-1">Timeout (Sec)</label>
                        <input
                          type="number"
                          value={wizardForm.timeout_seconds}
                          onChange={(e) => setWizardForm({ ...wizardForm, timeout_seconds: Number(e.target.value) })}
                          className="w-full rounded-lg border border-[#30363D] bg-[#161B22] px-2.5 py-1.5 text-xs text-white"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-[#8B949E] block mb-1">Max Retries</label>
                        <input
                          type="number"
                          value={wizardForm.max_retries}
                          onChange={(e) => setWizardForm({ ...wizardForm, max_retries: Number(e.target.value) })}
                          className="w-full rounded-lg border border-[#30363D] bg-[#161B22] px-2.5 py-1.5 text-xs text-white"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 4: Pre-Flight Verification & Summary */}
              {wizardStep === 4 && (
                <div className="space-y-4">
                  <div className="rounded-xl border border-[#21262D] bg-[#161B22] p-4 text-xs space-y-3 font-mono">
                    <span className="text-[10px] uppercase font-bold text-[#8B949E] block">
                      Target Connection Manifest
                    </span>
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div>
                        <span className="text-[#8B949E]">System: </span>
                        <span className="text-white font-bold">{wizardForm.name}</span>
                      </div>
                      <div>
                        <span className="text-[#8B949E]">Provider: </span>
                        <span className="text-[#00E5FF] font-bold uppercase">{wizardForm.provider}</span>
                      </div>
                      <div>
                        <span className="text-[#8B949E]">Privilege: </span>
                        <span className={wizardForm.read_only ? "text-[#F85149] font-bold" : "text-[#3FB950] font-bold"}>
                          {wizardForm.read_only ? "READ-ONLY" : "READ/WRITE"}
                        </span>
                      </div>
                      <div>
                        <span className="text-[#8B949E]">Rate Limit: </span>
                        <span className="text-white">{wizardForm.rate_limit_per_minute} req/min</span>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-[#21262D] bg-[#0E1117] p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="text-xs font-bold text-white">Live Pre-Flight Connectivity Probe</h4>
                        <p className="text-[11px] text-[#8B949E]">
                          Test round-trip latency and authentication without writing to the database.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={handleRunPreflight}
                        disabled={isPreflightRunning}
                        className="flex items-center gap-1.5 rounded-lg bg-[#21262D] px-3 py-1.5 text-xs font-bold text-[#00E5FF] hover:bg-[#30363D] disabled:opacity-50"
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${isPreflightRunning ? "animate-spin" : ""}`} />
                        {isPreflightRunning ? "Probing..." : "Test Now"}
                      </button>
                    </div>

                    {preflightResult && (
                      <div className={`rounded-lg border p-3 text-xs font-mono animate-in fade-in ${
                        preflightResult.status === "CONNECTED"
                          ? "border-[#238636]/40 bg-[#238636]/10 text-[#3FB950]"
                          : "border-[#DA3633]/40 bg-[#DA3633]/10 text-[#F85149]"
                      }`}>
                        <div className="flex items-center justify-between font-bold">
                          <span>Verdict: {preflightResult.status}</span>
                          {preflightResult.latency_ms > 0 && (
                            <span>Latency: {preflightResult.latency_ms} ms</span>
                          )}
                        </div>
                        <p className="mt-1 text-[11px] text-[#C9D1D9]">
                          {preflightResult.message}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Wizard Navigation Footer */}
            <div className="flex items-center justify-between border-t border-[#21262D] px-6 py-4 bg-[#161B22]/50">
              <button
                type="button"
                onClick={() => setWizardStep(prev => Math.max(1, prev - 1))}
                disabled={wizardStep === 1}
                className="rounded-lg border border-[#30363D] bg-[#161B22] px-3.5 py-1.5 text-xs font-semibold text-[#8B949E] hover:text-white disabled:opacity-30"
              >
                Back
              </button>

              <div className="flex items-center gap-2">
                {wizardStep < 4 ? (
                  <button
                    type="button"
                    onClick={() => {
                      if (wizardStep === 2 && !wizardForm.name.trim()) {
                        alert("Connection Name is required.");
                        return;
                      }
                      setWizardStep(prev => prev + 1);
                    }}
                    className="flex items-center gap-1 rounded-lg bg-[#00E5FF] px-4 py-1.5 text-xs font-bold text-black shadow hover:opacity-95"
                  >
                    Continue
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleSaveConnection}
                    disabled={isCreatingConnection}
                    className="flex items-center gap-1.5 rounded-lg bg-[#238636] px-5 py-2 text-xs font-bold text-white shadow-lg shadow-[#238636]/30 hover:bg-[#2EA043] disabled:opacity-50"
                  >
                    <Check className="h-4 w-4" />
                    {isCreatingConnection ? "Committing..." : "Commit & Activate Connection"}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* DYNAMIC SCHEMA DISCOVERY INSPECTOR MODAL                       */}
      {/* ============================================================== */}
      {inspectingConn && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
          <div className="w-full max-w-2xl rounded-2xl border border-[#30363D] bg-[#0E1117] shadow-2xl flex flex-col max-h-[85vh] overflow-hidden">
            <div className="flex items-center justify-between border-b border-[#21262D] px-6 py-4">
              <div className="flex items-center gap-2">
                <Database className="h-5 w-5 text-[#00E5FF]" />
                <div>
                  <h3 className="text-sm font-bold text-white">
                    Dynamic Schema Introspection: {inspectingConn.name}
                  </h3>
                  <span className="font-mono text-[10px] text-[#8B949E]">
                    {inspectingConn.connector_type} • Provider: {inspectingConn.provider}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setInspectingConn(null)}
                className="rounded-lg p-1 text-[#8B949E] hover:bg-[#21262D] hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {isLoadingSchema ? (
                <div className="flex h-40 items-center justify-center text-xs text-[#8B949E] gap-2">
                  <RefreshCw className="h-4 w-4 animate-spin text-[#00E5FF]" />
                  Introspecting remote system entities and column types...
                </div>
              ) : !discoveredSchemaData || discoveredSchemaData.length === 0 ? (
                <div className="text-center py-8 text-xs text-[#8B949E]">
                  No schema definitions could be introspected from this connector.
                </div>
              ) : (
                <div className="space-y-4">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-[#8B949E]">
                    Introspected Structure ({discoveredSchemaData.length} entities/attributes)
                  </span>

                  <div className="rounded-xl border border-[#21262D] bg-[#161B22] overflow-hidden">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="border-b border-[#21262D] bg-[#0E1117] text-[#8B949E]">
                        <tr>
                          <th className="px-4 py-2.5">Field / Table</th>
                          <th className="px-4 py-2.5">Data Type</th>
                          <th className="px-4 py-2.5">Primary Key</th>
                          <th className="px-4 py-2.5">Description</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#21262D] text-[#C9D1D9]">
                        {discoveredSchemaData.map((item: any, idx: number) => {
                          const isTable = !!item.table_name;
                          return (
                            <tr key={idx} className="hover:bg-[#21262D]/40">
                              <td className="px-4 py-2 font-bold text-white">
                                {item.field_name || item.table_name}
                              </td>
                              <td className="px-4 py-2 text-[#00E5FF]">
                                {item.data_type || (isTable ? `Table (${item.columns?.length || 0} cols)` : "string")}
                              </td>
                              <td className="px-4 py-2">
                                {item.is_primary_key ? (
                                  <span className="rounded bg-[#238636]/20 px-1.5 py-0.5 text-[9px] font-bold text-[#3FB950]">
                                    PRIMARY KEY
                                  </span>
                                ) : (
                                  <span className="text-[#8B949E]">-</span>
                                )}
                              </td>
                              <td className="px-4 py-2 text-[#8B949E] text-[11px]">
                                {item.description || "Discovered via connector reflection"}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end border-t border-[#21262D] px-6 py-3 bg-[#161B22]/50">
              <button
                type="button"
                onClick={() => setInspectingConn(null)}
                className="rounded-lg bg-[#21262D] px-4 py-1.5 text-xs font-bold text-white hover:bg-[#30363D]"
              >
                Close Inspector
              </button>
            </div>
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
              <h3 className="text-sm font-bold text-white">New CRM Customer Account</h3>
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

            <div className="grid grid-cols-2 gap-2">
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
              <div>
                <label className="text-xs font-semibold text-[#8B949E]">Contact Email</label>
                <input
                  type="email"
                  value={newRecordEmail}
                  onChange={(e) => setNewRecordEmail(e.target.value)}
                  placeholder="billing@apex.com"
                  className="mt-1 w-full rounded-md border border-[#30363D] bg-[#161B22] px-3 py-2 text-xs text-white focus:outline-none focus:border-[#58A6FF]"
                />
              </div>
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
