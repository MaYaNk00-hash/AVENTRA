"""
Standard Connector Interface for AVENTRA Enterprise Integrations.
Defines standard lifecycle, pagination, error recovery, and security boundary for all external systems.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any, Optional
import time
from pydantic import BaseModel, Field


class ConnectorType(str, Enum):
    CRM = "CRM"
    ERP = "ERP"
    DATABASE = "DATABASE"
    EMAIL = "EMAIL"


class ConnectorStatus(str, Enum):
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"


class ConnectorHealth(BaseModel):
    connector_id: str
    connector_type: ConnectorType
    status: ConnectorStatus
    latency_ms: float
    last_checked_at: str
    message: Optional[str] = None
    error_code: Optional[str] = None


class ConnectorQuery(BaseModel):
    record_type: str = Field(..., description="Target entity type, e.g. 'account', 'invoice', 'customer'")
    filters: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=50, ge=1, le=1000)
    cursor: Optional[str] = None
    incremental_since: Optional[str] = None


class ConnectorPage(BaseModel):
    records: List[Dict[str, Any]]
    count: int
    has_more: bool
    next_cursor: Optional[str] = None
    total_count: Optional[int] = None


class ConnectorOperationResult(BaseModel):
    success: bool
    record_id: Optional[str] = None
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    error_code: Optional[str] = None


class BaseEnterpriseConnector(ABC):
    """
    Abstract Base Class for all external enterprise connectors.
    Provides standard lifecycle, least-privilege permission validation,
    credential masking, and resilience patterns.
    """

    def __init__(
        self,
        connector_id: str,
        connector_type: ConnectorType,
        config: Dict[str, Any]
    ):
        self.connector_id = connector_id
        self.connector_type = connector_type
        self.config = config
        self.is_connected: bool = False
        self.last_sync_time: Optional[float] = None

    @abstractmethod
    def connect(self) -> bool:
        """Establishes session or authenticates with remote enterprise API."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Closes active connections, clears temporary session keys."""
        pass

    @abstractmethod
    def test_connection(self) -> ConnectorHealth:
        """Validates connection health, latency, and credential validity."""
        pass

    @abstractmethod
    def discover_schema(self) -> List[Dict[str, Any]]:
        """Introspects remote system schema, tables, objects, and types."""
        pass

    @abstractmethod
    def read_records(self, query: ConnectorQuery) -> ConnectorPage:
        """Reads records with pagination, filtering, and timeout controls."""
        pass

    @abstractmethod
    def get_record_by_id(self, record_type: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single record by primary key."""
        pass

    @abstractmethod
    def create_record(self, record_type: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        """Creates a record in the remote system (Requires governance approval)."""
        pass

    @abstractmethod
    def update_record(self, record_type: str, record_id: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        """Updates an existing record in the remote system (Requires governance approval)."""
        pass

    def mask_credentials(self) -> Dict[str, Any]:
        """Returns safe configuration suitable for frontend/logging with secrets redacted."""
        safe = dict(self.config)
        sensitive_keys = ["password", "secret", "token", "api_key", "private_key", "authorization"]
        for k in list(safe.keys()):
            if any(s in k.lower() for s in sensitive_keys):
                val = str(safe[k])
                safe[k] = val[:3] + "..." + val[-3:] if len(val) > 8 else "***REDACTED***"
        return safe
