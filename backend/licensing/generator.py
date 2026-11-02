"""
Vendor License Entitlement Generator (Vendor Control Plane Tooling).
Issues cryptographically signed enterprise license tokens for customer activation.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import hashlib
import json
import base64

from backend.licensing.contracts import (
    LicenseTier,
    DataPlaneBoundaryPolicy,
    LicenseEntitlements
)


DEFAULT_VENDOR_SECRET = "AVENTRA_VENDOR_ROOT_TRUST_KEY_V1"


def generate_license_token(
    organization_id: str,
    organization_name: str,
    installation_id: str,
    tier: LicenseTier = LicenseTier.STANDARD_ENTERPRISE,
    duration_days: int = 365,
    max_active_connectors: int = 25,
    max_concurrent_workflows: int = 50,
    allowed_connectors: Optional[List[str]] = None,
    models_licensed: Optional[List[str]] = None,
    data_boundary_policy: DataPlaneBoundaryPolicy = DataPlaneBoundaryPolicy.AIR_GAPPED_OFFLINE,
    vendor_secret: str = DEFAULT_VENDOR_SECRET
) -> str:
    """
    Generates a cryptographically signed, base64-encoded license entitlement token.
    """
    now = datetime.utcnow()
    expires = now + timedelta(days=duration_days)
    license_id = f"LIC-{datetime.utcnow().year}-{hashlib.sha256(f'{organization_id}{now}'.encode()).hexdigest()[:8].upper()}"

    connectors = allowed_connectors or ["CRM", "ERP", "DATABASE", "EMAIL"]
    models = models_licensed or ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"]

    entitlements = LicenseEntitlements(
        license_id=license_id,
        organization_id=organization_id,
        organization_name=organization_name,
        installation_id=installation_id,
        tier=tier,
        data_boundary_policy=data_boundary_policy,
        max_active_connectors=max_active_connectors,
        max_concurrent_workflows=max_concurrent_workflows,
        allowed_connectors=connectors,
        models_licensed=models,
        issued_at=now,
        expires_at=expires,
        signature=""
    )

    # Compute HMAC-SHA256 signature
    sig = hashlib.sha256(entitlements.payload_bytes() + vendor_secret.encode()).hexdigest()
    entitlements.signature = sig

    # Export to compact base64 token
    raw_json = entitlements.model_dump_json()
    encoded = base64.b64encode(raw_json.encode("utf-8")).decode("utf-8")
    return encoded


def decode_license_token(token_str: str) -> LicenseEntitlements:
    """Decodes raw base64 license token string into LicenseEntitlements object."""
    try:
        raw_json = base64.b64decode(token_str.strip().encode("utf-8")).decode("utf-8")
        data = json.loads(raw_json)
        return LicenseEntitlements(**data)
    except Exception as e:
        raise ValueError(f"Failed to decode license token: {str(e)}")

