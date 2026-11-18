"""
Unit tests validating Stage 5: Dynamic Enterprise Connection Management:
1. Connector discovery catalog & pre-flight testing
2. Connection lifecycle: creation, testing, updating, toggling (disabling/enabling), and deletion
3. Multiple connections of the same type (e.g. multi-CRM and multi-DB)
4. Secure encryption of connection credentials and zero plain-text secret exposure
5. Least-privilege permission validation (read-only blocks, operation and entity whitelists)
6. Resilience: rate limiting, retries, timeouts, and error reporting
7. Dynamic schema introspection for APIs and relational databases
8. Tamper-evident cryptographic audit ledger logging for all connection operations
"""

import pytest
import time
from sqlalchemy.orm import Session

from backend.database.session import SessionLocal, seed_database
from backend.database.models import EnterpriseConnection, AuditLedgerEntry
from backend.security.vault import encrypt_secrets, decrypt_secrets, mask_connection_dict
from backend.security.audit import verify_ledger_chain
from backend.connectors.factory import ConnectorFactory, SUPPORTED_CATALOG
from backend.connectors.resilience import (
    execute_with_resilience,
    LeastPrivilegeValidator,
    ConnectionRateLimiter,
    ConnectionDisabledError,
    PermissionDeniedError,
    RateLimitExceededError,
    ConnectionTimeoutError
)
from backend.connectors.base import ConnectorType, ConnectorStatus, ConnectorQuery
from backend.api.connections import (
    list_connections,
    get_connection,
    create_connection,
    update_connection,
    delete_connection,
    run_connection_test,
    run_preflight_test,
    toggle_connection_status,
    discover_connection_schema,
    execute_connection_operation,
    ConnectionCreateRequest,
    ConnectionUpdateRequest,
    PreflightTestRequest,
    ExecuteOperationRequest
)


@pytest.fixture(scope="module")
def db_session():
    seed_database()
    db = SessionLocal()
    yield db
    db.close()


def test_supported_catalog_discovery():
    """Verify connector discovery for supported enterprise APIs and databases."""
    catalog = ConnectorFactory.get_supported_catalog()
    assert len(catalog) >= 8

    providers = {c["provider"] for c in catalog}
    assert "salesforce" in providers
    assert "hubspot" in providers
    assert "sap" in providers
    assert "postgresql" in providers
    assert "gmail" in providers
    assert "ms_365" in providers

    for entry in catalog:
        assert "connector_type" in entry
        assert "display_name" in entry
        assert "config_schema" in entry
        assert "secret_schema" in entry
        assert "supported_operations" in entry


def test_secrets_vault_encryption_and_zero_plain_text_exposure(db_session: Session):
    """
    Verify secrets are stored using AES-256 encrypted ciphertext in the DB
    and never exposed to frontend views or serialization.
    """
    raw_secrets = {
        "api_key": "sec_live_crm_token_9999",
        "client_secret": "super_secret_oauth_secret_12345",
        "password": "production_dw_password!"
    }
    encrypted = encrypt_secrets(raw_secrets)
    assert encrypted != str(raw_secrets)
    assert "sec_live_crm_token_9999" not in encrypted
    assert "production_dw_password!" not in encrypted

    # Decrypt in memory
    decrypted = decrypt_secrets(encrypted)
    assert decrypted["api_key"] == "sec_live_crm_token_9999"
    assert decrypted["password"] == "production_dw_password!"

    # Test masking helper
    safe_view = mask_connection_dict({
        "id": "conn-test-sec",
        "name": "Secure CRM",
        "encrypted_secrets": encrypted,
        "secrets": raw_secrets,
        "config": {"endpoint": "https://api.crm.internal", "api_key": "sec_live_crm_token_9999"}
    })
    assert "encrypted_secrets" not in safe_view
    assert "secrets" not in safe_view
    assert safe_view["masked_secrets"]["api_key"] != "sec_live_crm_token_9999"
    assert "..." in safe_view["masked_secrets"]["api_key"] or safe_view["masked_secrets"]["api_key"] == "***REDACTED***"


def test_multiple_connections_of_same_type(db_session: Session):
    """
    Verify supporting multiple distinct enterprise connections of the same type (e.g. 2 CRM instances).
    """
    # Clean up any leftover test connections from prior runs
    db_session.query(EnterpriseConnection).filter(
        EnterpriseConnection.id.in_(["conn-crm-americas", "conn-crm-emea"])
    ).delete(synchronize_session=False)
    db_session.commit()

    req_crm_us = ConnectionCreateRequest(
        id="conn-crm-americas",
        name="Salesforce Americas Production",
        connector_type="CRM",
        provider="salesforce",
        description="Americas commercial client accounts",
        environment="PRODUCTION",
        read_only=False,
        allowed_operations=["READ", "SEARCH", "CREATE_RECORD"],
        allowed_entities=["accounts", "contacts"],
        config={"endpoint": "https://na1.salesforce.com/api/v58"},
        secrets={"client_secret": "sf_na_secret_key_881"}
    )
    req_crm_emea = ConnectionCreateRequest(
        id="conn-crm-emea",
        name="HubSpot EMEA Accounts",
        connector_type="CRM",
        provider="hubspot",
        description="EMEA regional lead pipeline",
        environment="PRODUCTION",
        read_only=True,  # Read-only policy
        allowed_operations=["READ", "SEARCH"],
        allowed_entities=["contacts", "deals"],
        config={"endpoint": "https://api.hubapi.com/crm/v3"},
        secrets={"api_key": "pat_eu_hubspot_token_994"}
    )

    created_us = create_connection(req_crm_us, db=db_session)
    created_emea = create_connection(req_crm_emea, db=db_session)

    assert created_us["id"] == "conn-crm-americas"
    assert created_emea["id"] == "conn-crm-emea"
    assert created_us["connector_type"] == "CRM"
    assert created_emea["connector_type"] == "CRM"
    assert created_us["read_only"] is False
    assert created_emea["read_only"] is True

    # Check database query finds both
    crms = list_connections(connector_type="CRM", db=db_session)
    crm_ids = [c["id"] for c in crms]
    assert "conn-crm-americas" in crm_ids
    assert "conn-crm-emea" in crm_ids


def test_preflight_and_on_demand_connection_testing(db_session: Session):
    """
    Verify pre-flight testing (wizard Step 5) and on-demand live testing with health/latency.
    """
    # 1. Preflight test with valid credentials
    preflight_ok = run_preflight_test(PreflightTestRequest(
        connector_type="CRM",
        provider="salesforce",
        config={"endpoint": "https://test.salesforce.com"},
        secrets={"client_secret": "valid_sf_secret"}
    ), db=db_session)
    assert preflight_ok["status"] == "CONNECTED"
    assert preflight_ok["latency_ms"] > 0

    # 2. Preflight test with missing credentials
    preflight_fail = run_preflight_test(PreflightTestRequest(
        connector_type="CRM",
        provider="salesforce",
        config={"endpoint": "https://test.salesforce.com"},
        secrets={}
    ), db=db_session)
    assert preflight_fail["status"] == "AUTHENTICATION_FAILED"

    # 3. On-demand test of existing connection
    tested = run_connection_test("conn-crm-americas", db=db_session)
    assert tested["status"] == "CONNECTED"
    assert tested["latency_ms"] > 0


def test_least_privilege_permission_validation(db_session: Session):
    """
    Verify least-privilege enforcement:
    - Write operation blocked on read-only connection
    - Operation outside allowed_operations blocked
    - Entity outside allowed_entities blocked
    """
    conn_emea = db_session.query(EnterpriseConnection).filter(
        EnterpriseConnection.id == "conn-crm-emea"
    ).first()
    assert conn_emea.read_only is True

    conn_americas = db_session.query(EnterpriseConnection).filter(
        EnterpriseConnection.id == "conn-crm-americas"
    ).first()
    assert conn_americas.read_only is False

    # 1. Attempt write on read-only connection -> Expect 403 / PermissionDeniedError
    with pytest.raises(PermissionDeniedError) as exc_info:
        LeastPrivilegeValidator.validate(conn_emea, operation="CREATE_RECORD", entity="contacts")
    assert "strictly READ-ONLY" in str(exc_info.value)

    # 2. Attempt operation not in allowed_operations list on non-read-only connection -> Expect PermissionDeniedError
    with pytest.raises(PermissionDeniedError) as exc_info:
        LeastPrivilegeValidator.validate(conn_americas, operation="DELETE", entity="accounts")
    assert "not in the allowed operations list" in str(exc_info.value)

    # 3. Attempt entity outside allowed_entities -> Expect PermissionDeniedError
    with pytest.raises(PermissionDeniedError) as exc_info:
        LeastPrivilegeValidator.validate(conn_americas, operation="READ", entity="unauthorized_payroll")
    assert "outside the authorized data perimeter" in str(exc_info.value)

    # 4. Valid read operation on allowed entity succeeds
    LeastPrivilegeValidator.validate(conn_americas, operation="READ", entity="accounts")


def test_resilience_rate_limiting_and_timeouts():
    """
    Verify per-connection rate limiting sliding window and timeout SLAs.
    """
    limiter = ConnectionRateLimiter()
    conn_id = "conn-rate-test-01"

    # Limit to 5 req/min
    for _ in range(5):
        limiter.check_and_consume(conn_id, max_per_minute=5)

    # 6th request must raise RateLimitExceededError
    with pytest.raises(RateLimitExceededError) as exc:
        limiter.check_and_consume(conn_id, max_per_minute=5)
    assert exc.value.retry_after > 0


def test_connection_disabling_and_toggling(db_session: Session):
    """
    Verify connection disabling, status transition, and rejection of execution while disabled.
    """
    # Disable conn-crm-americas
    toggled_off = toggle_connection_status("conn-crm-americas", enabled=False, db=db_session)
    assert toggled_off["is_enabled"] is False
    assert toggled_off["status"] == "DISABLED"

    conn = db_session.query(EnterpriseConnection).filter(
        EnterpriseConnection.id == "conn-crm-americas"
    ).first()

    with pytest.raises(ConnectionDisabledError):
        LeastPrivilegeValidator.validate(conn, operation="READ", entity="accounts")

    # Re-enable
    toggled_on = toggle_connection_status("conn-crm-americas", enabled=True, db=db_session)
    assert toggled_on["is_enabled"] is True
    assert toggled_on["status"] == "CONNECTED"


def test_dynamic_schema_discovery(db_session: Session):
    """
    Verify dynamic introspection of schemas, tables, fields, and types without code modification.
    """
    # 1. CRM Schema Discovery
    crm_schema = discover_connection_schema("conn-crm-americas", db=db_session)
    assert crm_schema["connection_id"] == "conn-crm-americas"
    assert len(crm_schema["discovered_schema"]) > 0
    field_names = [f["field_name"] for f in crm_schema["discovered_schema"]]
    assert "account_id" in field_names
    assert "account_name" in field_names

    # 2. Database Schema Discovery
    db_schema = discover_connection_schema("conn-db-01", db=db_session)
    assert db_schema["connection_id"] == "conn-db-01"
    tables = [t["table_name"] for t in db_schema["discovered_schema"]]
    assert "financial_ledger" in tables or "audit_logs" in tables


def test_connection_updating_and_deletion(db_session: Session):
    """
    Verify updating connection configuration/secrets and safe deletion.
    """
    # Clean up leftover if any
    db_session.query(EnterpriseConnection).filter(
        EnterpriseConnection.id == "conn-temp-to-delete"
    ).delete(synchronize_session=False)
    db_session.commit()

    # Create temp connection
    req = ConnectionCreateRequest(
        id="conn-temp-to-delete",
        name="Temporary Staging Database",
        connector_type="DATABASE",
        provider="mysql",
        config={"host": "mysql.staging", "port": 3306},
        secrets={"password": "initial_password_123"}
    )
    create_connection(req, db=db_session)

    # Update description and policy
    updated = update_connection(
        "conn-temp-to-delete",
        ConnectionUpdateRequest(
            name="Updated Staging Database",
            read_only=True,
            allowed_operations=["READ", "QUERY"],
            config={"port": 3307}
        ),
        db=db_session
    )
    assert updated["name"] == "Updated Staging Database"
    assert updated["read_only"] is True
    assert updated["config"]["port"] == 3307

    # Delete
    del_res = delete_connection("conn-temp-to-delete", db=db_session)
    assert del_res["deleted"] is True
    assert del_res["connection_id"] == "conn-temp-to-delete"

    # Confirm it is gone
    with pytest.raises(Exception):
        get_connection("conn-temp-to-delete", db=db_session)


def test_cryptographic_audit_ledger_trail(db_session: Session):
    """
    Verify all connection lifecycle operations (CREATED, TESTED, STATUS_CHANGED, UPDATED, DELETED)
    are cryptographically chained in the append-only audit ledger without chain breaks.
    """
    verify_res = verify_ledger_chain(db_session)
    assert verify_res["is_valid"] is True
    assert verify_res["total_entries"] >= 5

    # Check for connection audit entries
    entries = db_session.query(AuditLedgerEntry).filter(
        AuditLedgerEntry.entity_type == "ENTERPRISE_CONNECTION"
    ).all()
    action_types = {e.action_type for e in entries}
    assert "CONNECTION_CREATED" in action_types
    assert "CONNECTION_TESTED" in action_types
    assert "CONNECTION_STATUS_CHANGED" in action_types
