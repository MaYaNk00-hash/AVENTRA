"""
Unit and Integration Tests for Stage 3: Enterprise Licensing & Activation.
Validates offline activation, hardware fingerprint binding, signature integrity,
expiration policies, and strict separation of licensing traffic from customer operational data.
"""

import pytest
from datetime import datetime, timedelta
import json
import base64

from backend.licensing.identity import generate_installation_identity, detect_container_environment
from backend.licensing.contracts import LicenseTier, DataPlaneBoundaryPolicy, LicenseEntitlements
from backend.licensing.generator import generate_license_token, decode_license_token, DEFAULT_VENDOR_SECRET
from backend.licensing.manager import LicenseManager


def test_unique_installation_identity_generation():
    fp1 = generate_installation_identity()
    assert fp1.installation_id.startswith("AVN-INST-")
    assert len(fp1.installation_id.split("-")) == 6
    assert fp1.hostname is not None
    assert fp1.os_system in ["Windows", "Linux", "Darwin"]
    
    # Determinism check
    fp2 = generate_installation_identity()
    assert fp1.installation_id == fp2.installation_id


def test_offline_license_generation_and_decoding():
    fp = generate_installation_identity()
    token = generate_license_token(
        organization_id="ORG-TEST-99",
        organization_name="Test Enterprise Corp",
        installation_id=fp.installation_id,
        tier=LicenseTier.MISSION_CRITICAL,
        duration_days=180
    )
    assert isinstance(token, str)
    assert len(token) > 50

    ent = decode_license_token(token)
    assert ent.organization_id == "ORG-TEST-99"
    assert ent.tier == LicenseTier.MISSION_CRITICAL
    assert ent.installation_id == fp.installation_id
    assert ent.is_expired() is False
    assert len(ent.signature) == 64


def test_license_activation_flow():
    mgr = LicenseManager()
    fp = mgr.fingerprint

    token = generate_license_token(
        organization_id="ORG-ACTIVE-01",
        organization_name="Apex Global Holdings",
        installation_id=fp.installation_id,
        tier=LicenseTier.STANDARD_ENTERPRISE,
        duration_days=300
    )

    result = mgr.activate_from_token(token)
    assert result["valid"] is True
    assert result["status"] == "ACTIVE_ENTITLED"
    assert result["organization"] == "Apex Global Holdings"
    assert result["tier"] == "STANDARD_ENTERPRISE"
    assert result["expires_in_days"] >= 298

    # Query status
    status = mgr.get_status()
    assert status["is_active"] is True
    assert status["organization"] == "Apex Global Holdings"
    assert status["days_remaining"] >= 298
    assert mgr.is_model_entitled("M1") is True
    assert mgr.is_connector_entitled("CRM") is True


def test_tampered_signature_rejection():
    mgr = LicenseManager()
    fp = mgr.fingerprint

    token = generate_license_token(
        organization_id="ORG-HACKED",
        organization_name="Untrusted Org",
        installation_id=fp.installation_id,
        vendor_secret="WRONG_SECRET_KEY"
    )

    result = mgr.activate_from_token(token)
    assert result["valid"] is False
    assert result["status"] == "INVALID_SIGNATURE"


def test_hardware_mismatch_rejection():
    mgr = LicenseManager()
    wrong_hardware_id = "AVN-INST-0000-1111-2222-3333"

    token = generate_license_token(
        organization_id="ORG-WRONG-HW",
        organization_name="Wrong Hardware Org",
        installation_id=wrong_hardware_id,
        duration_days=100
    )

    result = mgr.activate_from_token(token)
    assert result["valid"] is False
    assert result["status"] == "HARDWARE_MISMATCH"
    assert "License bound to installation ID" in result["reason"]


def test_expired_license_handling():
    mgr = LicenseManager()
    fp = mgr.fingerprint

    token = generate_license_token(
        organization_id="ORG-EXPIRED",
        organization_name="Expired Enterprise",
        installation_id=fp.installation_id,
        duration_days=-5  # expired 5 days ago
    )

    result = mgr.activate_from_token(token)
    assert result["valid"] is False
    assert result["status"] == "EXPIRED"


def test_revocation_policy_enforcement():
    mgr = LicenseManager()
    fp = mgr.fingerprint

    token = generate_license_token(
        organization_id="ORG-TO-REVOKE",
        organization_name="Revoked Enterprise",
        installation_id=fp.installation_id,
        duration_days=90
    )
    act_res = mgr.activate_from_token(token)
    assert act_res["valid"] is True
    lic_id = act_res["license_id"]

    # Revoke license
    rev_res = mgr.revoke_license(lic_id, reason="Security audit key rotation")
    assert rev_res["revoked"] is True
    assert rev_res["license_id"] == lic_id

    # Attempting to re-activate revoked license must fail
    react_res = mgr.activate_from_token(token)
    assert react_res["valid"] is False
    assert react_res["status"] == "REVOKED"


def test_licensing_traffic_separation_from_customer_data():
    """
    Validates that licensing tokens, fingerprints, and statuses contain
    ZERO enterprise database records, customer PII, or operational metrics.
    """
    fp = generate_installation_identity()
    fp_dict = fp.model_dump()
    
    # Assert fingerprint only contains infrastructure metadata
    allowed_fp_keys = {"installation_id", "hostname", "os_system", "machine_arch", "mac_node_hash", "is_containerized"}
    assert set(fp_dict.keys()) == allowed_fp_keys
    
    # Check token serialization contains zero customer data
    token = generate_license_token("ORG-1", "Test Corp", fp.installation_id)
    ent = decode_license_token(token)
    ent_json = ent.model_dump_json()
    
    disallowed_keywords = ["customer", "invoice", "vendor", "account", "transaction", "balance", "email_body", "ssn"]
    for kw in disallowed_keywords:
        assert kw not in ent_json.lower()
