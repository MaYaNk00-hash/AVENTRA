"""
Dynamic Enterprise Connector Factory & Discovery Engine.
Instantiates, configures, tests, and discovers schemas for all supported enterprise systems
(CRMs, ERPs, Relational Databases, Email gateways) without editing source code.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.connectors.base import (
    BaseEnterpriseConnector,
    ConnectorType,
    ConnectorHealth,
    ConnectorStatus
)
from backend.connectors.company_a_crm import CompanyACRMConnector
from backend.connectors.company_b_erp import CompanyBERPConnector
from backend.connectors.generic_connectors import (
    GenericCRMConnector,
    GenericERPConnector,
    GenericDatabaseConnector,
    GenericEmailConnector
)
from backend.database.models import EnterpriseConnection
from backend.security.vault import decrypt_secrets, mask_connection_dict


SUPPORTED_CATALOG: List[Dict[str, Any]] = [
    # CRM Systems
    {
        "provider": "salesforce",
        "display_name": "Salesforce CRM",
        "connector_type": "CRM",
        "category": "Customer Relationship Management",
        "icon": "Users",
        "description": "Enterprise customer accounts, contacts, leads, and opportunity pipeline synchronization.",
        "default_endpoint": "https://enterprise-instance.my.salesforce.com/services/data/v58.0",
        "auth_methods": ["OAUTH2", "API_KEY"],
        "config_schema": [
            {"key": "endpoint", "label": "Instance URL", "type": "url", "required": True, "placeholder": "https://your-company.my.salesforce.com"},
            {"key": "api_version", "label": "REST API Version", "type": "text", "required": False, "placeholder": "v58.0"}
        ],
        "secret_schema": [
            {"key": "client_secret", "label": "Client Secret / Consumer Key", "type": "password", "required": True},
            {"key": "api_key", "label": "Security Token / API Key", "type": "password", "required": False}
        ],
        "default_entities": ["accounts", "contacts", "opportunities", "leads"],
        "supported_operations": ["READ", "SEARCH", "CREATE_RECORD", "UPDATE_RECORD", "DELETE"]
    },
    {
        "provider": "hubspot",
        "display_name": "HubSpot CRM",
        "connector_type": "CRM",
        "category": "Customer Relationship Management",
        "icon": "Users",
        "description": "HubSpot private app integration for inbound contact, company, and deal management.",
        "default_endpoint": "https://api.hubapi.com/crm/v3",
        "auth_methods": ["PRIVATE_APP_TOKEN", "OAUTH2"],
        "config_schema": [
            {"key": "endpoint", "label": "Base URL", "type": "url", "required": True, "placeholder": "https://api.hubapi.com/crm/v3"}
        ],
        "secret_schema": [
            {"key": "api_key", "label": "HubSpot Private App Access Token", "type": "password", "required": True}
        ],
        "default_entities": ["contacts", "companies", "deals", "tickets"],
        "supported_operations": ["READ", "SEARCH", "CREATE_RECORD", "UPDATE_RECORD"]
    },
    {
        "provider": "custom_crm",
        "display_name": "Custom REST CRM",
        "connector_type": "CRM",
        "category": "Customer Relationship Management",
        "icon": "Users",
        "description": "Generic RESTful connector for in-house enterprise CRM or legacy proprietary databases.",
        "default_endpoint": "https://crm.internal.corp/api/v1",
        "auth_methods": ["BEARER_TOKEN", "API_KEY", "BASIC"],
        "config_schema": [
            {"key": "endpoint", "label": "REST API Endpoint", "type": "url", "required": True, "placeholder": "https://api.crm-alpha.internal"}
        ],
        "secret_schema": [
            {"key": "api_key", "label": "Bearer API Key", "type": "password", "required": True}
        ],
        "default_entities": ["accounts", "contacts", "leads"],
        "supported_operations": ["READ", "SEARCH", "CREATE_RECORD", "UPDATE_RECORD"]
    },

    # ERP Systems
    {
        "provider": "sap",
        "display_name": "SAP S/4HANA & ECC",
        "connector_type": "ERP",
        "category": "Enterprise Resource Planning",
        "icon": "Building2",
        "description": "SAP OData / BAPI gateway for purchase orders, vendors, invoices, and material documents.",
        "default_endpoint": "https://sap-gateway.enterprise.corp:8443/sap/opu/odata/sap",
        "auth_methods": ["OAUTH2_SAML", "BASIC_AUTH", "X509_CERT"],
        "config_schema": [
            {"key": "endpoint", "label": "SAP OData Service URL", "type": "url", "required": True, "placeholder": "https://sap-gateway.internal:8443/odata"},
            {"key": "client_number", "label": "SAP Client (Mandt)", "type": "text", "required": False, "placeholder": "100"}
        ],
        "secret_schema": [
            {"key": "client_secret", "label": "Gateway Client Secret", "type": "password", "required": True},
            {"key": "api_key", "label": "Technical User Token", "type": "password", "required": False}
        ],
        "default_entities": ["vendors", "purchase_orders", "invoices", "general_ledger"],
        "supported_operations": ["READ", "SEARCH", "CREATE_RECORD", "UPDATE_RECORD"]
    },
    {
        "provider": "netsuite",
        "display_name": "Oracle NetSuite ERP",
        "connector_type": "ERP",
        "category": "Enterprise Resource Planning",
        "icon": "Building2",
        "description": "SuiteTalk REST Web Services for vendor bills, purchase orders, and multi-subsidiary ledgers.",
        "default_endpoint": "https://account-id.suitetalk.api.netsuite.com/services/rest/record/v1",
        "auth_methods": ["TBA_TOKEN", "OAUTH2"],
        "config_schema": [
            {"key": "endpoint", "label": "SuiteTalk REST Endpoint", "type": "url", "required": True, "placeholder": "https://123456.suitetalk.api.netsuite.com"},
            {"key": "realm", "label": "NetSuite Account ID", "type": "text", "required": True, "placeholder": "123456_SB1"}
        ],
        "secret_schema": [
            {"key": "client_secret", "label": "Consumer Secret / Token Secret", "type": "password", "required": True},
            {"key": "api_key", "label": "Token ID", "type": "password", "required": True}
        ],
        "default_entities": ["vendors", "purchase_orders", "vendor_bills"],
        "supported_operations": ["READ", "SEARCH", "CREATE_RECORD", "UPDATE_RECORD"]
    },

    # Relational & Analytical Databases
    {
        "provider": "postgresql",
        "display_name": "PostgreSQL Enterprise",
        "connector_type": "DATABASE",
        "category": "Databases & Warehouses",
        "icon": "Database",
        "description": "Secure SQL introspection, allowlisted read execution, and schema discovery for PostgreSQL.",
        "default_endpoint": "localhost:5432",
        "auth_methods": ["PASSWORD", "IAM_TOKEN", "CERTIFICATE"],
        "config_schema": [
            {"key": "host", "label": "Host Address", "type": "text", "required": True, "placeholder": "db.production.internal"},
            {"key": "port", "label": "Port", "type": "number", "required": True, "placeholder": "5432"},
            {"key": "database_name", "label": "Database Name", "type": "text", "required": True, "placeholder": "enterprise_dw"}
        ],
        "secret_schema": [
            {"key": "username", "label": "Database User", "type": "text", "required": True, "placeholder": "aventra_ro"},
            {"key": "password", "label": "Database Password", "type": "password", "required": True}
        ],
        "default_entities": ["audit_logs", "financial_ledger", "reconciliation_batches"],
        "supported_operations": ["READ", "QUERY", "SEARCH"]
    },
    {
        "provider": "mysql",
        "display_name": "MySQL / MariaDB",
        "connector_type": "DATABASE",
        "category": "Databases & Warehouses",
        "icon": "Database",
        "description": "Standard MySQL connection driver with parameterized query enforcement.",
        "default_endpoint": "localhost:3306",
        "auth_methods": ["PASSWORD", "SSL_KEY"],
        "config_schema": [
            {"key": "host", "label": "Host Address", "type": "text", "required": True, "placeholder": "mysql.internal"},
            {"key": "port", "label": "Port", "type": "number", "required": True, "placeholder": "3306"},
            {"key": "database_name", "label": "Database Name", "type": "text", "required": True, "placeholder": "corp_data"}
        ],
        "secret_schema": [
            {"key": "username", "label": "Database User", "type": "text", "required": True, "placeholder": "app_user"},
            {"key": "password", "label": "Database Password", "type": "password", "required": True}
        ],
        "default_entities": ["records", "transactions"],
        "supported_operations": ["READ", "QUERY", "SEARCH"]
    },
    {
        "provider": "sqlite",
        "display_name": "SQLite Local / Edge Database",
        "connector_type": "DATABASE",
        "category": "Databases & Warehouses",
        "icon": "Database",
        "description": "Local file or embedded SQLite database connector for edge partitions.",
        "default_endpoint": "sqlite:///data/local.db",
        "auth_methods": ["NONE", "ENCRYPTION_KEY"],
        "config_schema": [
            {"key": "database_name", "label": "Database Path / URI", "type": "text", "required": True, "placeholder": "backend/aventra.db"}
        ],
        "secret_schema": [],
        "default_entities": ["users", "records", "audit_ledger"],
        "supported_operations": ["READ", "QUERY", "SEARCH"]
    },

    # Email & Messaging Gateways
    {
        "provider": "gmail",
        "display_name": "Google Workspace Gmail",
        "connector_type": "EMAIL",
        "category": "Communication Gateways",
        "icon": "Mail",
        "description": "Google Gmail REST API for secure mailbox monitoring, invoice ingestion, and draft synthesis.",
        "default_endpoint": "https://gmail.googleapis.com/gmail/v1",
        "auth_methods": ["OAUTH2_SERVICE_ACCOUNT", "USER_CONSENT_OAUTH"],
        "config_schema": [
            {"key": "domain", "label": "Google Workspace Domain", "type": "text", "required": True, "placeholder": "acme-corp.com"},
            {"key": "service_account", "label": "Delegated Service Account", "type": "text", "required": False, "placeholder": "ops-bot@acme-corp.iam.gserviceaccount.com"}
        ],
        "secret_schema": [
            {"key": "oauth_client_secret", "label": "OAuth Client Secret / Key", "type": "password", "required": True},
            {"key": "refresh_token", "label": "Refresh Token", "type": "password", "required": True}
        ],
        "default_entities": ["messages", "threads", "drafts", "labels"],
        "supported_operations": ["READ", "SEARCH", "CREATE_DRAFT"]
    },
    {
        "provider": "ms_365",
        "display_name": "Microsoft 365 Exchange",
        "connector_type": "EMAIL",
        "category": "Communication Gateways",
        "icon": "Mail",
        "description": "Microsoft Graph Mail API for Exchange Online email inspection and drafts.",
        "default_endpoint": "https://graph.microsoft.com/v1.0",
        "auth_methods": ["AZURE_AD_CLIENT_CREDENTIALS", "DELEGATED_OAUTH"],
        "config_schema": [
            {"key": "tenant_id", "label": "Azure AD Tenant ID", "type": "text", "required": True, "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"},
            {"key": "client_id", "label": "Azure App Client ID", "type": "text", "required": True, "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"}
        ],
        "secret_schema": [
            {"key": "client_secret", "label": "Azure AD Client Secret", "type": "password", "required": True}
        ],
        "default_entities": ["messages", "folders", "drafts"],
        "supported_operations": ["READ", "SEARCH", "CREATE_DRAFT"]
    }
]


class ConnectorFactory:
    """
    Factory for producing and managing dynamic connector instances.
    """

    @classmethod
    def get_supported_catalog(cls) -> List[Dict[str, Any]]:
        """Returns discovery catalog of supported providers and configuration requirements."""
        return SUPPORTED_CATALOG

    @classmethod
    def build_connector(
        cls,
        connector_type: str,
        provider: str,
        connection_id: str,
        config: Dict[str, Any],
        secrets: Dict[str, Any],
        db: Optional[Session] = None
    ) -> BaseEnterpriseConnector:
        """
        Dynamically constructs an enterprise connector driver.
        """
        ctype = str(connector_type).upper()
        prov = str(provider).lower()

        # Connect to existing simulator instances if requested
        if connection_id == "COMPANY_A_CRM" and db is not None:
            return CompanyACRMConnector(db=db, config=config)
        if connection_id == "COMPANY_B_ERP" and db is not None:
            return CompanyBERPConnector(db=db, config=config)

        if ctype == "CRM":
            return GenericCRMConnector(connection_id, prov, config, secrets)
        elif ctype == "ERP":
            return GenericERPConnector(connection_id, prov, config, secrets)
        elif ctype == "DATABASE":
            return GenericDatabaseConnector(connection_id, prov, config, secrets)
        elif ctype == "EMAIL":
            return GenericEmailConnector(connection_id, prov, config, secrets)
        else:
            raise ValueError(f"Unsupported connector type: {connector_type}")

    @classmethod
    def get_connector_for_connection(
        cls,
        connection_model: EnterpriseConnection,
        db: Optional[Session] = None
    ) -> BaseEnterpriseConnector:
        """
        Instantiates connector for an existing EnterpriseConnection DB record,
        decrypting credentials in memory only.
        """
        secrets = decrypt_secrets(connection_model.encrypted_secrets) if connection_model.encrypted_secrets else {}
        config = connection_model.config or {}
        return cls.build_connector(
            connector_type=connection_model.connector_type,
            provider=connection_model.provider,
            connection_id=connection_model.id,
            config=config,
            secrets=secrets,
            db=db
        )

    @classmethod
    def test_connection_model(
        cls,
        connection_model: EnterpriseConnection,
        db: Optional[Session] = None
    ) -> ConnectorHealth:
        """
        Executes health check against a registered connection and updates its database health status.
        """
        connector = cls.get_connector_for_connection(connection_model, db=db)
        health = connector.test_connection()

        # Persist health update
        connection_model.status = health.status.value
        connection_model.last_health_check = {
            "status": health.status.value,
            "latency_ms": health.latency_ms,
            "last_checked_at": health.last_checked_at,
            "message": health.message,
            "error_code": health.error_code
        }
        if db is not None:
            db.commit()
            db.refresh(connection_model)

        return health

    @classmethod
    def test_raw_credentials(
        cls,
        connector_type: str,
        provider: str,
        config: Dict[str, Any],
        secrets: Dict[str, Any],
        db: Optional[Session] = None
    ) -> ConnectorHealth:
        """
        Pre-flight test for wizard Step 5 before committing connection to storage.
        """
        connector = cls.build_connector(
            connector_type=connector_type,
            provider=provider,
            connection_id=f"test-preflight-{provider}",
            config=config,
            secrets=secrets,
            db=db
        )
        return connector.test_connection()

    @classmethod
    def discover_schema(
        cls,
        connection_model: EnterpriseConnection,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Discovers remote metadata, tables, columns, or entity structures.
        """
        connector = cls.get_connector_for_connection(connection_model, db=db)
        return connector.discover_schema()

