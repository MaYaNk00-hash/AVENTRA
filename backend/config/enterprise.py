"""
Per-Enterprise Configuration, Security Policies, and Secrets Isolation Boundaries.
Enforces multi-tenant configuration isolation and strict least-privilege security policies.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import os
from enum import Enum
from pydantic import BaseModel, Field


class DeploymentEnvironment(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"
    AIR_GAPPED_GOV = "AIR_GAPPED_GOV"


class SecurityPolicyConfig(BaseModel):
    """
    Enterprise-governed autonomy constraints.
    These policies dictate when human approval is mandatory and what operations are disallowed.
    """
    approval_confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Predictions with matching or drift probability >= threshold require human approval"
    )
    financial_variance_tolerance: float = Field(
        default=0.02,
        ge=0.0,
        le=0.10,
        description="Invoice reconciliation variances above 2% mandate human sign-off"
    )
    prohibit_autonomous_external_email: bool = Field(
        default=True,
        description="External outgoing email messages cannot be sent without human-in-the-loop review"
    )
    allow_schema_adaptation_write: bool = Field(
        default=False,
        description="Prohibits autonomous model M6 schema alteration in production databases"
    )
    disallowed_sql_keywords: List[str] = Field(
        default=["DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE", "EXEC", "XP_"]
    )
    allowed_tool_ids: List[str] = Field(
        default=[
            "tool_crm_read",
            "tool_crm_update_canonical",
            "tool_erp_read_po",
            "tool_erp_read_invoice",
            "tool_database_query_readonly",
            "tool_email_read",
            "tool_email_create_draft"
        ]
    )


class EnterpriseTenantConfig(BaseModel):
    """
    Per-enterprise tenant configuration and isolation boundaries.
    """
    tenant_id: str = Field(..., description="Unique enterprise organization ID")
    organization_name: str
    environment: DeploymentEnvironment = DeploymentEnvironment.PRODUCTION
    data_residency_region: str = Field(default="US_EAST", description="Geographic residency boundary")
    primary_database_dsn: Optional[str] = None
    security_policy: SecurityPolicyConfig = Field(default_factory=SecurityPolicyConfig)
    active_connectors: List[str] = Field(default_factory=list)
    audit_chain_algorithm: str = "SHA-256"


# ==========================================
# SECRETS MANAGEMENT ABSTRACTION
# ==========================================

class ISecretsManager(ABC):
    @abstractmethod
    def get_secret(self, key: str, default: Optional[str] = None) -> str:
        """Retrieves an encrypted secret or credential."""
        pass

    @abstractmethod
    def set_secret(self, key: str, value: str) -> None:
        """Stores a secret securely."""
        pass


class EnvironmentSecretsManager(ISecretsManager):
    """
    Default Secrets Manager injecting credentials securely via OS environment variables.
    Never persists plain-text tokens in source code or client-side bundles.
    """
    def __init__(self, prefix: str = "AVENTRA_SECRET_"):
        self.prefix = prefix

    def get_secret(self, key: str, default: Optional[str] = None) -> str:
        env_key = f"{self.prefix}{key.upper()}"
        val = os.getenv(env_key) or os.getenv(key.upper())
        if val is not None:
            return val
        if default is not None:
            return default
        raise KeyError(f"Secret '{key}' not found in environment variables.")

    def set_secret(self, key: str, value: str) -> None:
        env_key = f"{self.prefix}{key.upper()}"
        os.environ[env_key] = value
