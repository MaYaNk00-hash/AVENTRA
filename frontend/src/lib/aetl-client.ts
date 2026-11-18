/**
 * AETL Enterprise API Client
 * ===========================
 * Drop this file into any other project (React, Next.js, Vue, Vanilla JS).
 * It lets you call CRM, ERP, Transactions, and Database APIs
 * from the AETL server running on localhost:8000.
 *
 * USAGE (copy this file to your project):
 *   import { AETLClient } from './aetl-client'
 *   const client = new AETLClient()
 *   const customers = await client.crm.getCustomers({ page: 1, limit: 20 })
 */

// ─────────────────────────────────────────────────────────────────────────────
// CONFIGURATION — Edit these to match your setup
// ─────────────────────────────────────────────────────────────────────────────
const AETL_CONFIG = {
  baseUrl: 'http://localhost:8000',
  apiKey: 'aetl_live_AoCvYTEi4WuUdmWtoFMu0_uH8XGNSMZYzIJIDOPqD6E',
  timeout: 10000,
}

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export interface AETLResponse<T = any> {
  success: boolean
  data: T
  pagination: {
    page: number
    limit: number
    total: number
    has_next: boolean
  } | null
  request_id: string
  error: { code: string; message: string } | null
}

export interface PaginationParams {
  page?: number
  limit?: number
  search?: string
}

export interface Customer {
  customer_id: string
  first_name: string
  last_name: string
  email: string
  phone?: string
  company_name?: string
  account_status: string
  lifecycle_stage: string
  data_origin: string
}

export interface Lead {
  lead_id: string
  first_name: string
  last_name: string
  email: string
  company_name?: string
  lead_source: string
  lead_status: string
  score: number
}

export interface Organization {
  org_id: string
  name: string
  domain: string
  industry: string
  annual_revenue: number
  employees_count: number
  country: string
  city: string
}

export interface Product {
  product_id: string
  sku: string
  name: string
  unit_price: number
  stock_quantity: number
  data_origin: string
}

export interface Vendor {
  vendor_id: string
  name: string
  tax_id: string
  payment_terms: string
  currency: string
  rating: number
  status: string
}

export interface PurchaseOrder {
  po_id: string
  vendor_id: string
  status: string
  total_amount: number
  currency: string
  created_at: number
}

export interface Order {
  order_id: string
  customer_id: string
  status: string
  total_amount: number
  created_at: number
}

export interface Payment {
  payment_id: string
  customer_id: string
  order_id: string
  amount: number
  currency: string
  status: string
  payment_method: string
}

export interface RecordCount {
  total_records: number
  is_exact_5000: boolean
  by_module: Record<string, number>
  by_enterprise: Record<string, number>
  by_data_origin: Record<string, number>
}

// ─────────────────────────────────────────────────────────────────────────────
// CORE HTTP LAYER
// ─────────────────────────────────────────────────────────────────────────────

class AETLHttp {
  private baseUrl: string
  private apiKey: string

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.apiKey = apiKey
  }

  private buildUrl(path: string, params?: Record<string, any>): string {
    const url = new URL(`${this.baseUrl}${path}`)
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null) url.searchParams.set(k, String(v))
      })
    }
    return url.toString()
  }

  async get<T = any>(path: string, params?: Record<string, any>): Promise<AETLResponse<T>> {
    const url = this.buildUrl(path, params)
    const res = await fetch(url, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
    })

    if (!res.ok && res.status === 429) {
      const retryAfter = res.headers.get('X-RateLimit-Reset') || '60'
      throw new Error(`Rate limit exceeded. Retry after ${retryAfter}s`)
    }

    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || `AETL API error: ${res.status}`)
    }
    return data
  }

  async post<T = any>(path: string, body?: any): Promise<AETLResponse<T>> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || `AETL API error: ${res.status}`)
    return data
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// CRM MODULE
// ─────────────────────────────────────────────────────────────────────────────

class CRMModule {
  constructor(private http: AETLHttp) {}

  /** Get paginated list of customers */
  getCustomers(params?: PaginationParams) {
    return this.http.get<Customer[]>('/api/v1/public/crm/customers', params)
  }

  /** Get paginated list of leads */
  getLeads(params?: PaginationParams) {
    return this.http.get<Lead[]>('/api/v1/public/crm/leads', params)
  }

  /** Get paginated list of contacts */
  getContacts(params?: PaginationParams) {
    return this.http.get<any[]>('/api/v1/public/crm/contacts', params)
  }

  /** Get paginated list of organizations */
  getOrganizations(params?: PaginationParams) {
    return this.http.get<Organization[]>('/api/v1/public/crm/organizations', params)
  }

  /** Get CRM analytics summary */
  getAnalytics() {
    return this.http.get('/api/v1/public/analytics/crm')
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ERP MODULE
// ─────────────────────────────────────────────────────────────────────────────

class ERPModule {
  constructor(private http: AETLHttp) {}

  /** Get paginated product catalog */
  getProducts(params?: PaginationParams) {
    return this.http.get<Product[]>('/api/v1/public/erp/products', params)
  }

  /** Get paginated vendor list */
  getVendors(params?: PaginationParams) {
    return this.http.get<Vendor[]>('/api/v1/public/erp/vendors', params)
  }

  /** Get paginated purchase orders */
  getPurchaseOrders(params?: PaginationParams) {
    return this.http.get<PurchaseOrder[]>('/api/v1/public/erp/purchase-orders', params)
  }

  /** Get inventory records */
  getInventory(params?: PaginationParams) {
    return this.http.get<any[]>('/api/v1/public/erp/inventory', params)
  }

  /** Get ERP analytics summary */
  getAnalytics() {
    return this.http.get('/api/v1/public/analytics/erp')
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// TRANSACTIONS MODULE
// ─────────────────────────────────────────────────────────────────────────────

class TransactionsModule {
  constructor(private http: AETLHttp) {}

  getOrders(params?: PaginationParams) {
    return this.http.get<Order[]>('/api/v1/public/transactions/orders', params)
  }

  getPayments(params?: PaginationParams) {
    return this.http.get<Payment[]>('/api/v1/public/transactions/payments', params)
  }

  getRefunds(params?: PaginationParams) {
    return this.http.get<any[]>('/api/v1/public/transactions/refunds', params)
  }

  getInvoices(params?: PaginationParams) {
    return this.http.get<any[]>('/api/v1/public/transactions/invoices', params)
  }

  getAnalytics() {
    return this.http.get('/api/v1/public/analytics/transactions')
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// DATABASE MODULE
// ─────────────────────────────────────────────────────────────────────────────

const ALLOWED_TABLES = [
  'customers', 'contacts', 'crm_leads', 'crm_organizations',
  'products', 'vendors', 'purchase_orders', 'inventory_records',
  'customer_orders', 'invoices', 'departments', 'approval_workflows',
  'client_records', 'legacy_leads', 'raw_materials', 'legacy_vendors',
  'po_master', 'dispatch_orders', 'supplier_bills', 'plant_departments',
  'plant_approvals', 'subscriptions', 'service_leads', 'service_orders',
  'service_invoices', 'cloud_departments', 'service_approvals',
  'payment_transactions', 'refund_records',
] as const

export type AllowedTable = typeof ALLOWED_TABLES[number]

class DatabaseModule {
  constructor(private http: AETLHttp) {}

  /** Get database architecture metadata */
  getMetadata() {
    return this.http.get('/api/v1/public/database/metadata')
  }

  /** List all accessible table names */
  listTables() {
    return this.http.get<string[]>('/api/v1/public/database/tables')
  }

  /** Get schema (column definitions) for a table */
  getTableSchema(tableName: AllowedTable) {
    return this.http.get(`/api/v1/public/database/tables/${tableName}/schema`)
  }

  /** Query records from a table with pagination */
  queryTable(tableName: AllowedTable, params?: PaginationParams) {
    return this.http.get(`/api/v1/public/database/tables/${tableName}/records`, params)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// DATA MANAGEMENT MODULE
// ─────────────────────────────────────────────────────────────────────────────

class DataManagementModule {
  constructor(private http: AETLHttp) {}

  /** Get total record count (5,000 breakdown) — no auth required */
  getCount() {
    return this.http.get<RecordCount>('/api/v1/data-management/count')
  }

  /** Get provenance breakdown — no auth required */
  getProvenance() {
    return this.http.get('/api/v1/data-management/provenance')
  }

  /** Search central record registry — auth required */
  getRecords(params?: { page?: number; limit?: number; module?: string; enterprise_id?: string }) {
    return this.http.get('/api/v1/data-management/records', params)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN CLIENT (entry point)
// ─────────────────────────────────────────────────────────────────────────────

export class AETLClient {
  public crm: CRMModule
  public erp: ERPModule
  public transactions: TransactionsModule
  public database: DatabaseModule
  public data: DataManagementModule

  private http: AETLHttp

  constructor(config?: Partial<typeof AETL_CONFIG>) {
    const merged = { ...AETL_CONFIG, ...config }
    this.http = new AETLHttp(merged.baseUrl, merged.apiKey)
    this.crm = new CRMModule(this.http)
    this.erp = new ERPModule(this.http)
    this.transactions = new TransactionsModule(this.http)
    this.database = new DatabaseModule(this.http)
    this.data = new DataManagementModule(this.http)
  }

  /** Health check — no auth required */
  health() {
    return fetch(`${AETL_CONFIG.baseUrl}/health`).then((r) => r.json())
  }

  /** Enterprise-wide analytics overview */
  getOverview() {
    return this.http.get('/api/v1/public/analytics/overview')
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// DEFAULT EXPORT — use directly if you don't need custom config
// ─────────────────────────────────────────────────────────────────────────────
export const aetl = new AETLClient()
export default aetl

