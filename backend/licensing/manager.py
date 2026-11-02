"""
Local Enterprise License Manager & Entitlement Policy Engine.
Operates 100% locally on customer infrastructure with zero outbound phone-home requirements.
"""

import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

from backend.licensing.contracts import (
    LicenseEntitlements,
    OfflineLicenseVerifier,
    LicenseTier
)
from backend.licensing.identity import generate_installation_identity
from backend.licensing.generator import decode_license_token, generate_license_token, DEFAULT_VENDOR_SECRET


LICENSE_STORAGE_FILE = os.path.join(os.path.dirname(__file__), "active_license.json")
REVOCATION_STORAGE_FILE = os.path.join(os.path.dirname(__file__), "revocations.json")


class LicenseManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LicenseManager, cls).__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.verifier = OfflineLicenseVerifier(DEFAULT_VENDOR_SECRET)
        self.active_entitlements: Optional[LicenseEntitlements] = None
        self.revoked_license_ids: set = set()
        self.fingerprint = generate_installation_identity()
        
        self._load_revocations()
        self._load_persisted_license()

    def _load_revocations(self):
        if os.path.exists(REVOCATION_STORAGE_FILE):
            try:
                with open(REVOCATION_STORAGE_FILE, "r") as f:
                    data = json.load(f)
                    self.revoked_license_ids = set(data.get("revoked_ids", []))
            except Exception:
                self.revoked_license_ids = set()

    def _save_revocations(self):
        try:
            with open(REVOCATION_STORAGE_FILE, "w") as f:
                json.dump({"revoked_ids": list(self.revoked_license_ids), "updated_at": datetime.utcnow().isoformat()}, f, indent=2)
        except Exception:
            pass

    def _load_persisted_license(self):
        # 1. Check environment variable token first
        env_token = os.getenv("AVENTRA_LICENSE_TOKEN")
        if env_token:
            try:
                ent = decode_license_token(env_token)
                res = self.verify_and_install_license(ent, persist=False)
                if res["valid"]:
                    return
            except Exception:
                pass

        # 2. Check local file storage
        if os.path.exists(LICENSE_STORAGE_FILE):
            try:
                with open(LICENSE_STORAGE_FILE, "r") as f:
                    data = json.load(f)
                    ent = LicenseEntitlements(**data)
                    self.verify_and_install_license(ent, persist=False)
            except Exception:
                self.active_entitlements = None

        # 3. If no license present, seed a default valid Developer/Enterprise trial license
        if not self.active_entitlements:
            self._seed_trial_license()

    def _seed_trial_license(self):
        token = generate_license_token(
            organization_id="ORG-TRIAL-ENTERPRISE",
            organization_name="Enterprise Proof of Concept",
            installation_id=self.fingerprint.installation_id,
            tier=LicenseTier.STANDARD_ENTERPRISE,
            duration_days=365
        )
        ent = decode_license_token(token)
        self.verify_and_install_license(ent, persist=True)

    def verify_and_install_license(self, entitlements: LicenseEntitlements, persist: bool = True) -> Dict[str, Any]:
        """
        Validates the incoming license token against all security policies:
        1. Signature verification
        2. Revocation list verification
        3. Installation ID matching (supports exact match or cluster wildcard '*')
        4. Expiration date check
        """
        # 1. Check revocation list
        if entitlements.license_id in self.revoked_license_ids:
            return {
                "valid": False,
                "status": "REVOKED",
                "reason": f"License '{entitlements.license_id}' has been formally revoked."
            }

        # 2. Cryptographic signature check
        verification = self.verifier.verify_license(entitlements)
        if not verification["valid"]:
            return verification

        # 3. Machine / Cluster fingerprint binding check
        allowed_inst = entitlements.installation_id
        current_inst = self.fingerprint.installation_id
        if allowed_inst != "*" and allowed_inst != current_inst:
            return {
                "valid": False,
                "status": "HARDWARE_MISMATCH",
                "reason": f"License bound to installation ID '{allowed_inst}', but host has '{current_inst}'."
            }

        # Successfully validated
        self.active_entitlements = entitlements

        if persist:
            try:
                with open(LICENSE_STORAGE_FILE, "w") as f:
                    f.write(entitlements.model_dump_json(indent=2))
            except Exception:
                pass

        return {
            "valid": True,
            "status": "ACTIVE_ENTITLED",
            "license_id": entitlements.license_id,
            "organization": entitlements.organization_name,
            "tier": entitlements.tier.value,
            "expires_in_days": (entitlements.expires_at - datetime.utcnow()).days,
            "allowed_models": entitlements.models_licensed,
            "allowed_connectors": entitlements.allowed_connectors
        }

    def activate_from_token(self, token_str: str) -> Dict[str, Any]:
        """Activates system using raw base64 license token string."""
        try:
            ent = decode_license_token(token_str)
            return self.verify_and_install_license(ent, persist=True)
        except Exception as e:
            return {
                "valid": False,
                "status": "INVALID_TOKEN",
                "reason": f"Corrupt or malformed license token: {str(e)}"
            }

    def revoke_license(self, license_id: str, reason: str = "Administrative revocation") -> Dict[str, Any]:
        """Adds a license ID to local revocation list and revokes entitlement."""
        self.revoked_license_ids.add(license_id)
        self._save_revocations()

        if self.active_entitlements and self.active_entitlements.license_id == license_id:
            self.active_entitlements = None
            if os.path.exists(LICENSE_STORAGE_FILE):
                try:
                    os.remove(LICENSE_STORAGE_FILE)
                except Exception:
                    pass

        return {
            "revoked": True,
            "license_id": license_id,
            "reason": reason,
            "active_now": False
        }

    def get_status(self) -> Dict[str, Any]:
        """Returns non-sensitive licensing status for UI dashboard and audit logs."""
        if not self.active_entitlements:
            return {
                "is_active": False,
                "status": "UNLICENSED",
                "installation_id": self.fingerprint.installation_id,
                "organization": None,
                "tier": "UNLICENSED",
                "days_remaining": 0,
                "allowed_models": [],
                "allowed_connectors": []
            }

        # Real-time expiration check
        if self.active_entitlements.is_expired():
            return {
                "is_active": False,
                "status": "EXPIRED",
                "installation_id": self.fingerprint.installation_id,
                "organization": self.active_entitlements.organization_name,
                "tier": self.active_entitlements.tier.value,
                "days_remaining": 0,
                "expires_at": self.active_entitlements.expires_at.isoformat(),
                "allowed_models": [],
                "allowed_connectors": []
            }

        days_rem = max(0, (self.active_entitlements.expires_at - datetime.utcnow()).days)
        return {
            "is_active": True,
            "status": "ACTIVE_ENTITLED",
            "license_id": self.active_entitlements.license_id,
            "installation_id": self.fingerprint.installation_id,
            "organization": self.active_entitlements.organization_name,
            "tier": self.active_entitlements.tier.value,
            "days_remaining": days_rem,
            "expires_at": self.active_entitlements.expires_at.isoformat(),
            "max_connectors": self.active_entitlements.max_active_connectors,
            "max_concurrent_workflows": self.active_entitlements.max_concurrent_workflows,
            "allowed_models": self.active_entitlements.models_licensed,
            "allowed_connectors": self.active_entitlements.allowed_connectors,
            "data_boundary_policy": self.active_entitlements.data_boundary_policy.value
        }

    def is_model_entitled(self, model_id: str) -> bool:
        status = self.get_status()
        if not status["is_active"]:
            return False
        # Match "M1" or "entity_resolution"
        models = [m.upper() for m in self.active_entitlements.models_licensed]
        return (model_id.upper() in models) or ("*" in models)

    def is_connector_entitled(self, connector_type: str) -> bool:
        status = self.get_status()
        if not status["is_active"]:
            return False
        conn_types = [c.upper() for c in self.active_entitlements.allowed_connectors]
        return (connector_type.upper() in conn_types) or ("*" in conn_types)
