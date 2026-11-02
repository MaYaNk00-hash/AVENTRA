"""
Unit tests validating Stage 2 Production Architecture implementations:
1. Licensing control plane and offline signature verification
2. Data plane egress prevention guard
3. Standard BaseEnterpriseConnector contract and lifecycle
4. Canonical CRM, ERP, Email, and Database schemas
5. Per-enterprise configuration, security policy, and secrets manager
"""

import pytest
from datetime import datetime, timedelta
import hashlib
import json

from backend.licensing.contracts import (
    LicenseTier,
    DataPlaneBoundaryPolicy,
    LicenseEntitlements,
    OfflineLicenseVerifier,
    DataPlaneGuard
)
from backend.connectors.base import (
    BaseEnterpriseConnector,
    ConnectorType,
    ConnectorStatus,
    ConnectorQuery
)
from backend.connectors.company_a_crm import CompanyACRMConnector
from backend.connectors.company_b_erp import CompanyBERPConnector
from backend.contracts.canonical import (
    CanonicalAccount,
    CanonicalPurchaseOrder,
    CanonicalInvoice,
    CanonicalLineItem,
    CanonicalEmailDraft,
    CanonicalTableMetadata,
    CanonicalColumnMetadata
)
from backend.config.enterprise import (
    EnterpriseTenantConfig,
    SecurityPolicyConfig,
    EnvironmentSecretsManager
)
from backend.database.session import SessionLocal, seed_database


def setup_module():
    seed_database()


def test_offline_license_verification_valid():
    trust_root = "AVENTRA_VENDOR_ROOT_TRUST_KEY_V1"
    now = datetime.utcnow()
    
    entitlements = LicenseEntitlements(
        license_id="LIC-2026-ENT-9910",
        organization_id="ORG-ACME-ENTERPRISE",
        organization_name="Acme Global Corporation",
        installation_id="HW-CLUSTER-FP-00912",
        tier=LicenseTier.STANDARD_ENTERPRISE,
        data_boundary_policy=DataPlaneBoundaryPolicy.AIR_GAPPED_OFFLINE,
        max_active_connectors=10,
        max_concurrent_workflows=25,
        allowed_connectors=["CRM", "ERP", "DATABASE", "EMAIL"],
        models_licensed=["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"],
        issued_at=now - timedelta(days=5),
        expires_at=now + timedelta(days=360),
        signature=""
    )
    
    # Sign token
    sig = hashlib.sha256(entitlements.payload_bytes() + trust_root.encode()).hexdigest()
    entitlements.signature = sig

    verifier = OfflineLicenseVerifier(trust_root)
    res = verifier.verify_license(entitlements)
    assert res["valid"] is True
    assert res["status"] == "ACTIVE_ENTITLED"
    assert res["organization"] == "Acme Global Corporation"


def test_offline_license_verification_tampered_signature():
    trust_root = "AVENTRA_VENDOR_ROOT_TRUST_KEY_V1"
    now = datetime.utcnow()
    
    entitlements = LicenseEntitlements(
        license_id="LIC-TAMPERED-001",
        organization_id="ORG-EVIL-CORP",
        organization_name="Untrusted Enterprise",
        installation_id="HW-CLUSTER-FP-00912",
        tier=LicenseTier.MISSION_CRITICAL,
        data_boundary_policy=DataPlaneBoundaryPolicy.AIR_GAPPED_OFFLINE,
        max_active_connectors=100,
        max_concurrent_workflows=100,
        issued_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=30),
        signature="FAKE_TAMPERED_SIGNATURE_HEX_12345"
    )

    verifier = OfflineLicenseVerifier(trust_root)
    res = verifier.verify_license(entitlements)
    assert res["valid"] is False
    assert res["status"] == "INVALID_SIGNATURE"


def test_offline_license_verification_expired():
    trust_root = "AVENTRA_VENDOR_ROOT_TRUST_KEY_V1"
    now = datetime.utcnow()
    
    entitlements = LicenseEntitlements(
        license_id="LIC-EXPIRED-001",
        organization_id="ORG-ACME-ENTERPRISE",
        organization_name="Acme Global Corporation",
        installation_id="HW-CLUSTER-FP-00912",
        tier=LicenseTier.STANDARD_ENTERPRISE,
        data_boundary_policy=DataPlaneBoundaryPolicy.AIR_GAPPED_OFFLINE,
        issued_at=now - timedelta(days=400),
        expires_at=now - timedelta(days=10),
        signature=""
    )
    sig = hashlib.sha256(entitlements.payload_bytes() + trust_root.encode()).hexdigest()
    entitlements.signature = sig

    verifier = OfflineLicenseVerifier(trust_root)
    res = verifier.verify_license(entitlements)
    assert res["valid"] is False
    assert res["status"] == "EXPIRED"


def test_data_plane_guard_prevents_vendor_egress():
    # Valid internal destination
    assert DataPlaneGuard.assert_data_egress_prohibited({"test": 1}, "https://internal-api.acme.local") is True
    
    # Prohibited vendor telemetry egress
    with pytest.raises(PermissionError) as excinfo:
        DataPlaneGuard.assert_data_egress_prohibited({"customer_ssn": "000"}, "https://telemetry.vendor.com/ingest")
    assert "DATA_PLANE_VIOLATION" in str(excinfo.value)


def test_standard_connector_interface_crm():
    db = SessionLocal()
    try:
        crm = CompanyACRMConnector(db)
        assert isinstance(crm, BaseEnterpriseConnector)
        assert crm.connector_type == ConnectorType.CRM
        
        # Test lifecycle
        health = crm.test_connection()
        assert health.status == ConnectorStatus.CONNECTED
        assert health.latency_ms >= 0.0
        
        # Test schema discovery
        schema = crm.discover_schema()
        assert len(schema) >= 5
        field_names = [f["field_name"] for f in schema]
        assert "account_id" in field_names
        assert "account_name" in field_names
        
        # Test standardized query
        page = crm.read_records(ConnectorQuery(record_type="account", limit=10))
        assert page.count > 0
        assert len(page.records) > 0
        
        # Test credential masking
        masked = crm.mask_credentials()
        assert masked["api_key"] != "sec_crm_alpha_token_live"
        assert "***" in masked["api_key"] or "..." in masked["api_key"]
    finally:
        db.close()


def test_standard_connector_interface_erp():
    db = SessionLocal()
    try:
        erp = CompanyBERPConnector(db)
        assert isinstance(erp, BaseEnterpriseConnector)
        assert erp.connector_type == ConnectorType.ERP
        
        health = erp.test_connection()
        assert health.status == ConnectorStatus.CONNECTED
        
        schema = erp.discover_schema()
        assert any(f["field_name"] == "vendor_id" for f in schema)
        
        page = erp.read_records(ConnectorQuery(record_type="vendor", limit=10))
        assert page.count > 0
    finally:
        db.close()


def test_canonical_contracts_validation():
    account = CanonicalAccount(
        canonical_id="CAN-ACC-00192",
        account_name="Apex Global Logistics LLC",
        country="US",
        tax_identifier="US-EIN-992182"
    )
    assert account.canonical_id == "CAN-ACC-00192"
    assert account.country == "US"

    po = CanonicalPurchaseOrder(
        po_number="PO-9910",
        vendor_id="VND-001",
        vendor_name="Apex Global Logistics",
        order_date=datetime.utcnow(),
        total_amount=5400.00,
        line_items=[
            CanonicalLineItem(
                sku_or_code="FREIGHT-40",
                description="40ft Freight",
                quantity=1,
                unit_price=5400.00,
                total_price=5400.00
            )
        ]
    )
    assert po.line_items[0].quantity == 1

    draft = CanonicalEmailDraft(
        to=["operations@partner.com"],
        subject="Re: Purchase Order PO-9910 Confirmation",
        body_text="Your order has been verified and received."
    )
    assert draft.requires_approval is True

    table = CanonicalTableMetadata(
        table_name="enterprise_vendors",
        columns=[
            CanonicalColumnMetadata(column_name="id", data_type="VARCHAR(64)", is_primary_key=True),
            CanonicalColumnMetadata(column_name="name", data_type="VARCHAR(255)")
        ]
    )
    assert table.columns[0].is_primary_key is True


def test_enterprise_config_and_secrets():
    policy = SecurityPolicyConfig(
        approval_confidence_threshold=0.85,
        financial_variance_tolerance=0.02,
        prohibit_autonomous_external_email=True
    )
    assert policy.approval_confidence_threshold == 0.85
    assert "DROP" in policy.disallowed_sql_keywords

    tenant = EnterpriseTenantConfig(
        tenant_id="TENANT-GLOBAL-101",
        organization_name="Global Enterprise Inc",
        security_policy=policy
    )
    assert tenant.tenant_id == "TENANT-GLOBAL-101"

    # Secrets manager
    sec = EnvironmentSecretsManager(prefix="TEST_SEC_")
    sec.set_secret("DATABASE_PASSWORD", "SuperSecureP@ssword99")
    val = sec.get_secret("DATABASE_PASSWORD")
    assert val == "SuperSecureP@ssword99"

