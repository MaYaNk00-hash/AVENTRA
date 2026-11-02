"""
Company A CRM Simulator Connector.
Conforms to BaseEnterpriseConnector standard interface.
Simulates a live CRM system managing corporate clients, accounts, and contacts.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database.models import EnterpriseRecord
from backend.connectors.base import (
    BaseEnterpriseConnector,
    ConnectorType,
    ConnectorStatus,
    ConnectorHealth,
    ConnectorQuery,
    ConnectorPage,
    ConnectorOperationResult
)


class CompanyACRMConnector(BaseEnterpriseConnector):
    def __init__(self, db: Session, config: Optional[Dict[str, Any]] = None):
        cfg = config or {"endpoint": "https://api.crm-alpha.internal", "api_key": "sec_crm_alpha_token_live"}
        super().__init__(
            connector_id="COMPANY_A_CRM",
            connector_type=ConnectorType.CRM,
            config=cfg
        )
        self.db = db
        self.system_id = "COMPANY_A_CRM"
        self.is_connected = True

    def connect(self) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        self.is_connected = False

    def test_connection(self) -> ConnectorHealth:
        start_time = datetime.utcnow()
        count = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id
        ).count()
        latency = (datetime.utcnow() - start_time).total_seconds() * 1000.0
        return ConnectorHealth(
            connector_id=self.connector_id,
            connector_type=self.connector_type,
            status=ConnectorStatus.CONNECTED if self.is_connected else ConnectorStatus.DISCONNECTED,
            latency_ms=round(latency, 2),
            last_checked_at=datetime.utcnow().isoformat(),
            message=f"Connected. {count} active CRM accounts discoverable."
        )

    def discover_schema(self) -> List[Dict[str, Any]]:
        return [
            {"field_name": "account_id", "data_type": "string", "is_primary_key": True, "nullable": False},
            {"field_name": "account_name", "data_type": "string", "is_primary_key": False, "nullable": False},
            {"field_name": "street_address", "data_type": "string", "is_primary_key": False, "nullable": True},
            {"field_name": "country", "data_type": "string", "is_primary_key": False, "nullable": False},
            {"field_name": "federal_tax_id", "data_type": "string", "is_primary_key": False, "nullable": True},
            {"field_name": "primary_email", "data_type": "string", "is_primary_key": False, "nullable": True},
            {"field_name": "status", "data_type": "string", "is_primary_key": False, "nullable": False}
        ]

    def read_records(self, query: ConnectorQuery) -> ConnectorPage:
        q = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id
        )
        total = q.count()
        records = q.limit(query.limit).all()
        formatted = [
            {
                "account_id": r.id,
                "account_name": r.name,
                "street_address": r.address,
                "country": r.country,
                "federal_tax_id": r.tax_identifier,
                "primary_email": r.contact_email,
                "status": r.status,
                "metadata": r.raw_data
            }
            for r in records
        ]
        return ConnectorPage(
            records=formatted,
            count=len(formatted),
            has_more=total > len(formatted),
            total_count=total
        )

    def get_record_by_id(self, record_type: str, record_id: str) -> Optional[Dict[str, Any]]:
        return self.get_account(record_id)

    def create_record(self, record_type: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        res = self.create_account(data)
        return ConnectorOperationResult(
            success=True,
            record_id=res["account_id"],
            action="CREATE_ACCOUNT",
            details=res
        )

    def update_record(self, record_type: str, record_id: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        r = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id,
            EnterpriseRecord.id == record_id
        ).first()
        if not r:
            return ConnectorOperationResult(
                success=False,
                record_id=record_id,
                action="UPDATE_ACCOUNT",
                error_message=f"Record {record_id} not found"
            )
        if "account_name" in data:
            r.name = data["account_name"]
        if "street_address" in data:
            r.address = data["street_address"]
        if "primary_email" in data:
            r.contact_email = data["primary_email"]
        self.db.commit()
        return ConnectorOperationResult(
            success=True,
            record_id=record_id,
            action="UPDATE_ACCOUNT"
        )

    # Backward-compatible convenience methods
    def list_accounts(self) -> List[Dict[str, Any]]:
        res = self.read_records(ConnectorQuery(record_type="account", limit=500))
        return res.records

    def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        r = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id,
            EnterpriseRecord.id == account_id
        ).first()
        if not r:
            return None
        return {
            "account_id": r.id,
            "account_name": r.name,
            "street_address": r.address,
            "country": r.country,
            "federal_tax_id": r.tax_identifier,
            "primary_email": r.contact_email,
            "status": r.status,
            "metadata": r.raw_data
        }

    def create_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        acc_id = data.get("account_id") or f"CRM-A-{self.db.query(EnterpriseRecord).count() + 101}"
        record = EnterpriseRecord(
            id=acc_id,
            system_origin=self.system_id,
            entity_type="CUSTOMER",
            name=data["account_name"],
            address=data.get("street_address", ""),
            country=data.get("country", "US"),
            tax_identifier=data.get("federal_tax_id"),
            contact_email=data.get("primary_email"),
            status="ACTIVE",
            raw_data=data.get("metadata", {})
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return {
            "account_id": record.id,
            "status": "CREATED",
            "system": self.system_id
        }
