"""
AVENTRA Enterprise Connection Management API.
Full REST API supporting:
- Connection setup wizard provider discovery catalog
- Secure creation, testing, updating, toggling, and deletion
- Least-privilege permission validation and read-only enforcement
- Cryptographic vault secret isolation (zero secret exposure to client)
- Dynamic schema introspection
- Chained cryptographic audit ledger logging for all lifecycle transitions
"""

import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.database.models import EnterpriseConnection
from backend.connectors.factory import ConnectorFactory
from backend.connectors.base import ConnectorQuery
from backend.connectors.resilience import (
    execute_with_resilience,
    ConnectionDisabledError,
    PermissionDeniedError,
    RateLimitExceededError,
    ConnectionTimeoutError
)
from backend.security.vault import (
    encrypt_secrets,
    decrypt_secrets,
    mask_connection_dict,
    mask_secret_value
)
from backend.security.audit import append_audit_entry

router = APIRouter(prefix="/api/connections", tags=["Enterprise Connection Management"])


# ==========================================
# REQUEST / RESPONSE SCHEMAS
# ==========================================

class ConnectionCreateRequest(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=2, max_length=100)
    connector_type: str = Field(..., description="CRM, ERP, DATABASE, or EMAIL")
    provider: str = Field(..., description="salesforce, hubspot, sap, postgresql, gmail, etc.")
    description: Optional[str] = ""
    environment: str = Field(default="PRODUCTION")
    tenant_id: str = Field(default="default-enterprise")
    read_only: bool = Field(default=False, description="Least privilege default")
    allowed_operations: List[str] = Field(default_factory=list)
    allowed_entities: List[str] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)
    secrets: Dict[str, Any] = Field(default_factory=dict, description="Encrypted immediately on ingest")


class ConnectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None
    read_only: Optional[bool] = None
    allowed_operations: Optional[List[str]] = None
    allowed_entities: Optional[List[str]] = None
    config: Optional[Dict[str, Any]] = None
    secrets: Optional[Dict[str, Any]] = None


class PreflightTestRequest(BaseModel):
    connector_type: str
    provider: str
    config: Dict[str, Any] = Field(default_factory=dict)
    secrets: Dict[str, Any] = Field(default_factory=dict)


class ExecuteOperationRequest(BaseModel):
    operation: str = Field(..., description="READ, SEARCH, CREATE_RECORD, UPDATE_RECORD, QUERY")
    entity_type: Optional[str] = None
    query: Optional[Dict[str, Any]] = None
    record_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


def _format_connection_response(conn: EnterpriseConnection) -> Dict[str, Any]:
    """Serializes connection model while ensuring secrets are masked and stripped."""
    data = {
        "id": conn.id,
        "name": conn.name,
        "connector_type": conn.connector_type,
        "provider": conn.provider,
        "description": conn.description,
        "environment": conn.environment,
        "tenant_id": conn.tenant_id,
        "status": conn.status,
        "is_enabled": conn.is_enabled,
        "read_only": conn.read_only,
        "allowed_operations": conn.allowed_operations or [],
        "allowed_entities": conn.allowed_entities or [],
        "config": conn.config or {},
        "last_health_check": conn.last_health_check or {},
        "metrics": conn.metrics or {},
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
        "updated_at": conn.updated_at.isoformat() if conn.updated_at else None,
    }
    # Unpack secret keys so frontend knows what fields are configured, without leaking values
    if conn.encrypted_secrets:
        try:
            raw_sec = decrypt_secrets(conn.encrypted_secrets)
            data["configured_secret_keys"] = list(raw_sec.keys())
            data["masked_secrets"] = {k: mask_secret_value(v) for k, v in raw_sec.items()}
        except Exception:
            data["configured_secret_keys"] = []
            data["masked_secrets"] = {}
    else:
        data["configured_secret_keys"] = []
        data["masked_secrets"] = {}

    return mask_connection_dict(data)


# ==========================================
# ENDPOINTS
# ==========================================

@router.get("/templates")
def get_connection_templates():
    """
    Returns discovery catalog of supported connectors, providers, schemas,
    and capability flags for the setup wizard.
    """
    return {
        "templates": ConnectorFactory.get_supported_catalog(),
        "total_supported": len(ConnectorFactory.get_supported_catalog())
    }


@router.get("")
def list_connections(
    connector_type: Optional[str] = None,
    provider: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Lists all enterprise connections with safe masked secrets.
    """
    query = db.query(EnterpriseConnection)
    if connector_type:
        query = query.filter(EnterpriseConnection.connector_type == connector_type.upper())
    if provider:
        query = query.filter(EnterpriseConnection.provider == provider.lower())
    if status_filter:
        query = query.filter(EnterpriseConnection.status == status_filter.upper())

    conns = query.order_by(EnterpriseConnection.created_at.desc()).all()
    return [_format_connection_response(c) for c in conns]


@router.get("/{connection_id}")
def get_connection(connection_id: str, db: Session = Depends(get_db)):
    """
    Retrieves a single enterprise connection with secrets strictly redacted.
    """
    conn = db.query(EnterpriseConnection).filter(EnterpriseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found.")
    return _format_connection_response(conn)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_connection(
    req: ConnectionCreateRequest,
    actor_id: str = "admin",
    actor_role: str = "ADMIN",
    db: Session = Depends(get_db)
):
    """
    Creates a new enterprise connection.
    Validates configuration, encrypts sensitive credentials into the AES-256 vault,
    tests initial health, and commits an entry to the cryptographic audit ledger.
    """
    # Generate unique ID if omitted
    conn_id = req.id.strip() if req.id else f"conn-{req.provider.lower()}-{uuid.uuid4().hex[:6]}"
    
    # Check duplicate ID
    existing = db.query(EnterpriseConnection).filter(EnterpriseConnection.id == conn_id).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Connection with ID '{conn_id}' already exists."
        )

    # Encrypt raw secrets immediately
    encrypted_payload = encrypt_secrets(req.secrets)

    conn = EnterpriseConnection(
        id=conn_id,
        name=req.name,
        connector_type=req.connector_type.upper(),
        provider=req.provider.lower(),
        description=req.description or "",
        environment=req.environment,
        tenant_id=req.tenant_id,
        status="CONNECTED",
        is_enabled=True,
        read_only=req.read_only,
        allowed_operations=req.allowed_operations or ["READ", "SEARCH"],
        allowed_entities=req.allowed_entities or [],
        encrypted_secrets=encrypted_payload,
        config=req.config,
        last_health_check={},
        metrics={
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "consecutive_failures": 0,
            "rate_limited_count": 0
        }
    )

    db.add(conn)
    db.commit()
    db.refresh(conn)

    # Run initial health test
    try:
        health = ConnectorFactory.test_connection_model(conn, db=db)
    except Exception as e:
        conn.status = "DISCONNECTED"
        conn.last_health_check = {"status": "DISCONNECTED", "message": str(e), "latency_ms": 0.0}
        db.commit()

    # Record tamper-evident cryptographic audit entry
    append_audit_entry(
        db=db,
        actor_id=actor_id,
        actor_role=actor_role,
        action_type="CONNECTION_CREATED",
        entity_type="ENTERPRISE_CONNECTION",
        entity_id=conn.id,
        details={
            "connection_id": conn.id,
            "name": conn.name,
            "connector_type": conn.connector_type,
            "provider": conn.provider,
            "read_only": conn.read_only,
            "allowed_operations": conn.allowed_operations,
            "environment": conn.environment
        }
    )

    return _format_connection_response(conn)


@router.put("/{connection_id}")
def update_connection(
    connection_id: str,
    req: ConnectionUpdateRequest,
    actor_id: str = "admin",
    actor_role: str = "ADMIN",
    db: Session = Depends(get_db)
):
    """
    Updates an existing enterprise connection.
    If new secrets are provided, re-encrypts into vault; preserves existing credentials otherwise.
    """
    conn = db.query(EnterpriseConnection).filter(EnterpriseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found.")

    if req.name is not None:
        conn.name = req.name
    if req.description is not None:
        conn.description = req.description
    if req.environment is not None:
        conn.environment = req.environment
    if req.read_only is not None:
        conn.read_only = req.read_only
    if req.allowed_operations is not None:
        conn.allowed_operations = req.allowed_operations
    if req.allowed_entities is not None:
        conn.allowed_entities = req.allowed_entities
    if req.config is not None:
        merged_cfg = dict(conn.config or {})
        merged_cfg.update(req.config)
        conn.config = merged_cfg

    # Update secrets only if real non-masked values supplied
    if req.secrets is not None and len(req.secrets) > 0:
        existing_secrets = decrypt_secrets(conn.encrypted_secrets) if conn.encrypted_secrets else {}
        for k, v in req.secrets.items():
            if v and not str(v).startswith("***"):
                existing_secrets[k] = v
        conn.encrypted_secrets = encrypt_secrets(existing_secrets)

    db.commit()
    db.refresh(conn)

    # Cryptographic audit ledger entry
    append_audit_entry(
        db=db,
        actor_id=actor_id,
        actor_role=actor_role,
        action_type="CONNECTION_UPDATED",
        entity_type="ENTERPRISE_CONNECTION",
        entity_id=conn.id,
        details={
            "connection_id": conn.id,
            "read_only": conn.read_only,
            "allowed_operations": conn.allowed_operations,
            "environment": conn.environment
        }
    )

    return _format_connection_response(conn)


@router.delete("/{connection_id}")
def delete_connection(
    connection_id: str,
    actor_id: str = "admin",
    actor_role: str = "ADMIN",
    db: Session = Depends(get_db)
):
    """
    Safely removes an enterprise connection configuration and logs audit event.
    """
    conn = db.query(EnterpriseConnection).filter(EnterpriseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found.")

    conn_name = conn.name
    conn_type = conn.connector_type
    db.delete(conn)
    db.commit()

    append_audit_entry(
        db=db,
        actor_id=actor_id,
        actor_role=actor_role,
        action_type="CONNECTION_DELETED",
        entity_type="ENTERPRISE_CONNECTION",
        entity_id=connection_id,
        details={"name": conn_name, "connector_type": conn_type}
    )

    return {"deleted": True, "connection_id": connection_id, "name": conn_name}


@router.post("/{connection_id}/test")
def run_connection_test(
    connection_id: str,
    actor_id: str = "admin",
    actor_role: str = "ADMIN",
    db: Session = Depends(get_db)
):
    """
    Performs on-demand live health verification and latency measurement.
    """
    conn = db.query(EnterpriseConnection).filter(EnterpriseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found.")

    health = ConnectorFactory.test_connection_model(conn, db=db)

    append_audit_entry(
        db=db,
        actor_id=actor_id,
        actor_role=actor_role,
        action_type="CONNECTION_TESTED",
        entity_type="ENTERPRISE_CONNECTION",
        entity_id=conn.id,
        details={"status": health.status.value, "latency_ms": health.latency_ms}
    )

    return health.model_dump()


@router.post("/test-preflight")
def run_preflight_test(req: PreflightTestRequest, db: Session = Depends(get_db)):
    """
    Tests credentials and endpoint in flight without writing to storage (Wizard Step 5).
    """
    try:
        health = ConnectorFactory.test_raw_credentials(
            connector_type=req.connector_type,
            provider=req.provider,
            config=req.config,
            secrets=req.secrets,
            db=db
        )
        return health.model_dump()
    except Exception as e:
        return {
            "connector_id": f"test-{req.provider}",
            "connector_type": req.connector_type,
            "status": "AUTHENTICATION_FAILED",
            "latency_ms": 0.0,
            "last_checked_at": "",
            "message": f"Pre-flight test failed: {str(e)}",
            "error_code": "PREFLIGHT_ERROR"
        }


@router.post("/{connection_id}/toggle")
def toggle_connection_status(
    connection_id: str,
    enabled: bool = Query(..., description="Target enabled state"),
    actor_id: str = "admin",
    actor_role: str = "ADMIN",
    db: Session = Depends(get_db)
):
    """
    Enables or disables an enterprise connection.
    """
    conn = db.query(EnterpriseConnection).filter(EnterpriseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found.")

    conn.is_enabled = enabled
    if not enabled:
        conn.status = "DISABLED"
    else:
        # Re-test when enabling
        try:
            health = ConnectorFactory.test_connection_model(conn, db=db)
            conn.status = health.status.value
        except Exception:
            conn.status = "CONNECTED"

    db.commit()
    db.refresh(conn)

    append_audit_entry(
        db=db,
        actor_id=actor_id,
        actor_role=actor_role,
        action_type="CONNECTION_STATUS_CHANGED",
        entity_type="ENTERPRISE_CONNECTION",
        entity_id=conn.id,
        details={"is_enabled": enabled, "new_status": conn.status}
    )

    return _format_connection_response(conn)


@router.get("/{connection_id}/discover")
def discover_connection_schema(connection_id: str, db: Session = Depends(get_db)):
    """
    Performs dynamic introspection of remote tables, objects, fields, and data types.
    """
    conn = db.query(EnterpriseConnection).filter(EnterpriseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found.")

    if not conn.is_enabled:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot introspect disabled connection '{connection_id}'. Enable it first."
        )

    try:
        schema = ConnectorFactory.discover_schema(conn, db=db)
        return {
            "connection_id": conn.id,
            "provider": conn.provider,
            "connector_type": conn.connector_type,
            "discovered_schema": schema
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schema discovery failed: {str(e)}")


@router.post("/{connection_id}/execute")
def execute_connection_operation(
    connection_id: str,
    req: ExecuteOperationRequest,
    db: Session = Depends(get_db)
):
    """
    Executes a high-assurance operation against an enterprise connector with:
    - Least-privilege validation (blocks writes on read-only, restricts disallowed ops)
    - Sliding-window rate limiting
    - Configurable timeout and exponential backoff retry resilience
    """
    conn = db.query(EnterpriseConnection).filter(EnterpriseConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found.")

    connector = ConnectorFactory.get_connector_for_connection(conn, db=db)

    def run_op():
        op = req.operation.upper()
        if op in ["READ", "QUERY", "SEARCH"]:
            cq = ConnectorQuery(
                record_type=req.entity_type or "default",
                filters=req.query.get("filters", {}) if req.query else {},
                limit=req.query.get("limit", 50) if req.query else 50
            )
            return connector.read_records(cq).model_dump()
        elif op == "GET_BY_ID":
            return connector.get_record_by_id(req.entity_type or "default", req.record_id or "")
        elif op in ["CREATE", "CREATE_RECORD", "INSERT"]:
            return connector.create_record(req.entity_type or "default", req.data or {}).model_dump()
        elif op in ["UPDATE", "UPDATE_RECORD"]:
            return connector.update_record(req.entity_type or "default", req.record_id or "", req.data or {}).model_dump()
        else:
            raise ValueError(f"Unsupported operation: {req.operation}")

    try:
        result = execute_with_resilience(
            connection=conn,
            operation=req.operation,
            func=run_op,
            entity=req.entity_type
        )
        db.commit()
        return {"success": True, "result": result}
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=429,
            detail=str(e),
            headers={"Retry-After": str(int(e.retry_after))}
        )
    except ConnectionDisabledError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Operation execution error: {str(e)}")
