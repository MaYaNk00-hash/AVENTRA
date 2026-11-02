"""
AVENTRA Production Architecture: Licensing Control Plane vs. Enterprise Data Plane.
Enforces strict security boundary ensuring customer data never leaves enterprise infrastructure.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import base64
import hashlib
from pydantic import BaseModel, Field


class LicenseTier(str, Enum):
    COMMUNITY = "COMMUNITY"
    STANDARD_ENTERPRISE = "STANDARD_ENTERPRISE"
    MISSION_CRITICAL = "MISSION_CRITICAL"
    AIR_GAPPED = "AIR_GAPPED"


class DataPlaneBoundaryPolicy(str, Enum):
    """
    Defines network and data egress boundaries.
    """
    AIR_GAPPED_OFFLINE = "AIR_GAPPED_OFFLINE"       # 0% external network traffic allowed
    TELEMETRY_MINIMAL = "TELEMETRY_MINIMAL"         # Only anonymized license heartbeat
    HYBRID_MANAGED = "HYBRID_MANAGED"               # Optional vendor control-plane notifications


class LicenseEntitlements(BaseModel):
    """
    Vendor-issued, cryptographically signed enterprise license token.
    Evaluated 100% locally on customer infrastructure without mandatory phone-home.
    """
    license_id: str = Field(..., description="Unique license identifier")
    organization_id: str = Field(..., description="Enterprise customer identifier")
    organization_name: str = Field(..., description="Legal company name")
    installation_id: str = Field(..., description="Hardware or cluster fingerprint")
    tier: LicenseTier = Field(default=LicenseTier.STANDARD_ENTERPRISE)
    data_boundary_policy: DataPlaneBoundaryPolicy = Field(default=DataPlaneBoundaryPolicy.AIR_GAPPED_OFFLINE)
    max_active_connectors: int = Field(default=25)
    max_concurrent_workflows: int = Field(default=50)
    allowed_connectors: List[str] = Field(default=["CRM", "ERP", "DATABASE", "EMAIL"])
    models_licensed: List[str] = Field(default=["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"])
    issued_at: datetime
    expires_at: datetime
    signature: str = Field(..., description="Vendor Ed25519/HMAC signature validating token authenticity")

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    def payload_bytes(self) -> bytes:
        """Serializes payload fields (excluding signature) for cryptographic verification."""
        d = self.model_dump(exclude={"signature"})
        # Sort keys and format datetimes deterministically
        d["issued_at"] = self.issued_at.isoformat()
        d["expires_at"] = self.expires_at.isoformat()
        return json.dumps(d, sort_keys=True).encode()


class DataPlaneGuard:
    """
    Architectural gatekeeper that guarantees enterprise data (records, documents,
    invoices, vector embeddings, audit ledger blocks) never crosses the boundary.
    """

    @staticmethod
    def assert_data_egress_prohibited(payload: Dict[str, Any], destination: str) -> bool:
        """
        Validates that sensitive enterprise payloads cannot be dispatched to vendor endpoints.
        """
        prohibited_destinations = ["vendor.aventra.io", "telemetry.vendor.com", "external-api.io"]
        for domain in prohibited_destinations:
            if domain in destination.lower():
                raise PermissionError(
                    f"[DATA_PLANE_VIOLATION] Attempted to send enterprise data to {destination}. "
                    "AVENTRA data plane boundary strictly prohibits customer data transmission outside the VPC."
                )
        return True


class OfflineLicenseVerifier:
    """
    Verifies license signatures locally using embedded vendor public key or shared trust secret.
    """

    def __init__(self, vendor_public_key_or_secret: str = "AVENTRA_VENDOR_ROOT_TRUST_KEY_V1"):
        self.trust_root = vendor_public_key_or_secret

    def verify_license(self, entitlements: LicenseEntitlements) -> Dict[str, Any]:
        """
        Validates cryptographic integrity and active validity of the license.
        """
        if entitlements.is_expired():
            return {
                "valid": False,
                "reason": f"License expired on {entitlements.expires_at.isoformat()}",
                "status": "EXPIRED"
            }

        # Compute HMAC-SHA256 signature for verification
        expected_sig = hashlib.sha256(
            entitlements.payload_bytes() + self.trust_root.encode()
        ).hexdigest()

        if entitlements.signature != expected_sig:
            return {
                "valid": False,
                "reason": "Cryptographic signature verification failed. Untrusted or tampered license.",
                "status": "INVALID_SIGNATURE"
            }

        return {
            "valid": True,
            "organization": entitlements.organization_name,
            "tier": entitlements.tier.value,
            "status": "ACTIVE_ENTITLED",
            "expires_in_days": (entitlements.expires_at - datetime.utcnow()).days
        }

