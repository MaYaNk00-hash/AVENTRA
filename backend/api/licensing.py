"""
Licensing & Activation REST API Router.
Enables offline activation, status inspection, and entitlement enforcement without vendor data access.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

from backend.licensing.manager import LicenseManager
from backend.licensing.identity import generate_installation_identity
from backend.security.auth import get_current_user
from backend.security.rbac import require_roles
from backend.database.models import User


router = APIRouter(prefix="/api/licensing", tags=["Enterprise Licensing & Activation"])


class ActivationRequest(BaseModel):
    license_token: str = Field(..., min_length=10, description="Base64 encoded signed license token")


class RevocationRequest(BaseModel):
    license_id: str
    reason: Optional[str] = "Security compromise or migration"


@router.get("/status")
def get_license_status():
    """
    Returns non-sensitive licensing health, tier, and days remaining.
    Open to authenticated dashboard and health checks.
    """
    mgr = LicenseManager()
    return mgr.get_status()


@router.get("/fingerprint")
def get_installation_fingerprint():
    """
    Returns installation hardware fingerprint for customer to request a signed license token.
    Contains zero customer PII or operational data.
    """
    fp = generate_installation_identity()
    return {
        "installation_id": fp.installation_id,
        "hostname": fp.hostname,
        "os_system": fp.os_system,
        "machine_arch": fp.machine_arch,
        "is_containerized": fp.is_containerized,
        "instructions": "Provide installation_id to vendor authority to generate a signed offline license."
    }


@router.post("/activate")
def activate_license(
    req: ActivationRequest,
    current_user: User = Depends(require_roles(["ADMIN", "COMPLIANCE_OFFICER"]))
):
    """
    Activates AVENTRA using an offline signed license token.
    Requires ADMIN or COMPLIANCE_OFFICER role.
    """
    mgr = LicenseManager()
    res = mgr.activate_from_token(req.license_token)
    if not res.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res
        )
    return {
        "success": True,
        "message": f"Successfully activated AVENTRA {res.get('tier')} for {res.get('organization')}.",
        "license_details": res
    }


@router.post("/revoke")
def revoke_license(
    req: RevocationRequest,
    current_user: User = Depends(require_roles(["ADMIN", "COMPLIANCE_OFFICER"]))
):
    """
    Revokes a compromised or decommissioned license key.
    """
    mgr = LicenseManager()
    res = mgr.revoke_license(req.license_id, reason=req.reason)
    return res

