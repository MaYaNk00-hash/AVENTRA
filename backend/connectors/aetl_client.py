"""
AETL Enterprise API Client — Python SDK
=========================================
Drop this file into any Python project (Flask, FastAPI, Django, scripts).
Lets you call CRM, ERP, Transactions, and Database APIs from AETL on localhost:8000.

Requirements:
    pip install requests   (standard — almost always already installed)

Quick start:
    from aetl_client import AETLClient
    client = AETLClient()
    customers = client.crm.get_customers(limit=20)
    print(customers['data'])
"""

import requests
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — edit these to match your setup
# ─────────────────────────────────────────────────────────────────────────────
AETL_BASE_URL = "http://localhost:8000"
AETL_API_KEY  = "aetl_live_AoCvYTEi4WuUdmWtoFMu0_uH8XGNSMZYzIJIDOPqD6E"


class AETLError(Exception):
    """Raised when the AETL API returns an error response."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"AETL API {status_code}: {detail}")


class AETLHttp:
    def __init__(self, base_url: str, api_key: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        self.timeout = timeout

    def get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        r = self.session.get(url, params={k: v for k, v in (params or {}).items() if v is not None}, timeout=self.timeout)
        if not r.ok:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            raise AETLError(r.status_code, detail)
        return r.json()

    def post(self, path: str, body: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        r = self.session.post(url, json=body, timeout=self.timeout)
        if not r.ok:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            raise AETLError(r.status_code, detail)
        return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# CRM MODULE
# ─────────────────────────────────────────────────────────────────────────────

class CRMModule:
    def __init__(self, http: AETLHttp):
        self._http = http

    def get_customers(self, page: int = 1, limit: int = 20, search: Optional[str] = None) -> Dict:
        """Get paginated customers. Returns {success, data, pagination, request_id}"""
        return self._http.get("/api/v1/public/crm/customers", {"page": page, "limit": limit, "search": search})

    def get_leads(self, page: int = 1, limit: int = 20) -> Dict:
        """Get paginated CRM leads."""
        return self._http.get("/api/v1/public/crm/leads", {"page": page, "limit": limit})

    def get_contacts(self, page: int = 1, limit: int = 20) -> Dict:
        """Get paginated contacts."""
        return self._http.get("/api/v1/public/crm/contacts", {"page": page, "limit": limit})

    def get_organizations(self, page: int = 1, limit: int = 20) -> Dict:
        """Get paginated organizations."""
        return self._http.get("/api/v1/public/crm/organizations", {"page": page, "limit": limit})

    def get_analytics(self) -> Dict:
        """Get CRM analytics summary (customer count, leads, organizations)."""
        return self._http.get("/api/v1/public/analytics/crm")


# ─────────────────────────────────────────────────────────────────────────────
# ERP MODULE
# ─────────────────────────────────────────────────────────────────────────────

class ERPModule:
    def __init__(self, http: AETLHttp):
        self._http = http

    def get_products(self, page: int = 1, limit: int = 20, search: Optional[str] = None) -> Dict:
        """Get paginated product catalog."""
        return self._http.get("/api/v1/public/erp/products", {"page": page, "limit": limit, "search": search})

    def get_vendors(self, page: int = 1, limit: int = 20) -> Dict:
        """Get paginated vendor list."""
        return self._http.get("/api/v1/public/erp/vendors", {"page": page, "limit": limit})

    def get_purchase_orders(self, page: int = 1, limit: int = 20) -> Dict:
        """Get paginated purchase orders."""
        return self._http.get("/api/v1/public/erp/purchase-orders", {"page": page, "limit": limit})

    def get_inventory(self, page: int = 1, limit: int = 20) -> Dict:
        """Get paginated inventory records."""
        return self._http.get("/api/v1/public/erp/inventory", {"page": page, "limit": limit})

    def get_analytics(self) -> Dict:
        """Get ERP analytics summary."""
        return self._http.get("/api/v1/public/analytics/erp")


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTIONS MODULE
# ─────────────────────────────────────────────────────────────────────────────

class TransactionsModule:
    def __init__(self, http: AETLHttp):
        self._http = http

    def get_orders(self, page: int = 1, limit: int = 20) -> Dict:
        return self._http.get("/api/v1/public/transactions/orders", {"page": page, "limit": limit})

    def get_payments(self, page: int = 1, limit: int = 20) -> Dict:
        return self._http.get("/api/v1/public/transactions/payments", {"page": page, "limit": limit})

    def get_refunds(self, page: int = 1, limit: int = 20) -> Dict:
        return self._http.get("/api/v1/public/transactions/refunds", {"page": page, "limit": limit})

    def get_invoices(self, page: int = 1, limit: int = 20) -> Dict:
        return self._http.get("/api/v1/public/transactions/invoices", {"page": page, "limit": limit})

    def get_analytics(self) -> Dict:
        return self._http.get("/api/v1/public/analytics/transactions")


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE MODULE
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_TABLES = [
    "customers", "contacts", "crm_leads", "crm_organizations",
    "products", "vendors", "purchase_orders", "inventory_records",
    "customer_orders", "invoices", "departments", "approval_workflows",
    "client_records", "legacy_leads", "raw_materials", "legacy_vendors",
    "po_master", "dispatch_orders", "supplier_bills", "plant_departments",
    "plant_approvals", "subscriptions", "service_leads", "service_orders",
    "service_invoices", "cloud_departments", "service_approvals",
    "payment_transactions", "refund_records",
]

class DatabaseModule:
    def __init__(self, http: AETLHttp):
        self._http = http

    def get_metadata(self) -> Dict:
        """Get database architecture overview."""
        return self._http.get("/api/v1/public/database/metadata")

    def list_tables(self) -> List[str]:
        """List all publicly accessible table names."""
        return self._http.get("/api/v1/public/database/tables")["data"]

    def get_schema(self, table_name: str) -> Dict:
        """Get column schema for a table."""
        if table_name not in ALLOWED_TABLES:
            raise ValueError(f"Table '{table_name}' is not in the allowed list. Use list_tables() to see options.")
        return self._http.get(f"/api/v1/public/database/tables/{table_name}/schema")

    def query(self, table_name: str, page: int = 1, limit: int = 25) -> Dict:
        """Query rows from a table with pagination."""
        if table_name not in ALLOWED_TABLES:
            raise ValueError(f"Table '{table_name}' not allowed.")
        return self._http.get(f"/api/v1/public/database/tables/{table_name}/records",
                              {"page": page, "limit": limit})


# ─────────────────────────────────────────────────────────────────────────────
# DATA MANAGEMENT MODULE
# ─────────────────────────────────────────────────────────────────────────────

class DataManagementModule:
    def __init__(self, http: AETLHttp):
        self._http = http

    def get_count(self) -> Dict:
        """Get total record count and module/enterprise breakdown — no auth needed."""
        return self._http.get("/api/v1/data-management/count")

    def get_provenance(self) -> Dict:
        """Get provenance breakdown by data origin — no auth needed."""
        return self._http.get("/api/v1/data-management/provenance")

    def get_records(self, page: int = 1, limit: int = 25,
                    module: Optional[str] = None,
                    enterprise_id: Optional[str] = None) -> Dict:
        """Search the central record registry."""
        return self._http.get("/api/v1/data-management/records",
                              {"page": page, "limit": limit, "module": module, "enterprise_id": enterprise_id})


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class AETLClient:
    """
    Main entry point for the AETL Enterprise API.

    Example:
        client = AETLClient()
        customers = client.crm.get_customers(limit=10)
        for c in customers['data']:
            print(c['email'])
    """

    def __init__(self,
                 base_url: str = AETL_BASE_URL,
                 api_key: str = AETL_API_KEY,
                 timeout: int = 10):
        self._http = AETLHttp(base_url, api_key, timeout)
        self.crm = CRMModule(self._http)
        self.erp = ERPModule(self._http)
        self.transactions = TransactionsModule(self._http)
        self.database = DatabaseModule(self._http)
        self.data = DataManagementModule(self._http)

    def health(self) -> Dict:
        """Check if the AETL server is running. No auth required."""
        r = requests.get(f"{AETL_BASE_URL}/health", timeout=5)
        return r.json()

    def overview(self) -> Dict:
        """Get enterprise-wide analytics overview."""
        return self._http.get("/api/v1/public/analytics/overview")


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST — run this file directly to verify connectivity
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing AETL cross-project API connectivity...\n")

    client = AETLClient()

    # Health
    h = client.health()
    print(f"✅ Health: {h.get('status')}")

    # Record count (no auth)
    count = client.data.get_count()
    print(f"✅ Total records: {count['data']['total_records']}")

    # CRM
    c = client.crm.get_customers(limit=3)
    print(f"✅ CRM customers: {c['pagination']['total']} total, first: {c['data'][0]['email']}")

    # ERP
    p = client.erp.get_products(limit=3)
    print(f"✅ ERP products:  {p['pagination']['total']} total, first: {p['data'][0]['name']}")

    # Transactions
    pay = client.transactions.get_payments(limit=3)
    print(f"✅ Payments:      {pay['pagination']['total']} total, first status: {pay['data'][0]['status']}")

    # Database query
    rows = client.database.query("vendors", limit=3)
    print(f"✅ DB vendors:    {rows['pagination']['total']} total, first: {rows['data'][0]['name']}")

    print("\n🎉 All checks passed! Your cross-project integration is working.")

