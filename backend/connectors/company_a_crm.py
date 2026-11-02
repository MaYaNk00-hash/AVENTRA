"""
Company A CRM Simulator Connector.
Simulates a live CRM system managing corporate clients, accounts, and contacts.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.database.models import EnterpriseRecord


class CompanyACRMConnector:
    def __init__(self, db: Session):
        self.db = db
        self.system_id = "COMPANY_A_CRM"

    def list_accounts(self) -> List[Dict[str, Any]]:
        records = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id
        ).all()
        return [
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

