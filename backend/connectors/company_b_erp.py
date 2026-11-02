"""
Company B ERP Simulator Connector.
Conforms to BaseEnterpriseConnector standard interface.
Simulates an Enterprise Resource Planning system managing vendors, purchase orders, goods receipts, and general ledger postings.
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


class CompanyBERPConnector(BaseEnterpriseConnector):
    def __init__(self, db: Session, config: Optional[Dict[str, Any]] = None):
        cfg = config or {"endpoint": "https://erp.enterprise-internal.net/api/v2", "client_secret": "erp_b_secret_9981"}
        super().__init__(
            connector_id="COMPANY_B_ERP",
            connector_type=ConnectorType.ERP,
            config=cfg
        )
        self.db = db
        self.system_id = "COMPANY_B_ERP"
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
            message=f"ERP Connected. {count} vendors/POs discoverable."
        )

    def discover_schema(self) -> List[Dict[str, Any]]:
        return [
            {"field_name": "vendor_id", "data_type": "string", "is_primary_key": True, "nullable": False},
            {"field_name": "business_name", "data_type": "string", "is_primary_key": False, "nullable": False},
            {"field_name": "business_address", "data_type": "string", "is_primary_key": False, "nullable": True},
            {"field_name": "country", "data_type": "string", "is_primary_key": False, "nullable": False},
            {"field_name": "tax_number", "data_type": "string", "is_primary_key": False, "nullable": True},
            {"field_name": "canonical_id", "data_type": "string", "is_primary_key": False, "nullable": True},
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
                "vendor_id": r.id,
                "business_name": r.name,
                "business_address": r.address,
                "country": r.country,
                "tax_number": r.tax_identifier,
                "email": r.contact_email,
                "canonical_id": r.canonical_id,
                "status": r.status,
                "erp_metadata": r.raw_data
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
        return self.get_vendor(record_id)

    def create_record(self, record_type: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        res = self.create_vendor(data)
        return ConnectorOperationResult(
            success=True,
            record_id=res["vendor_id"],
            action="CREATE_VENDOR",
            details=res
        )

    def update_record(self, record_type: str, record_id: str, data: Dict[str, Any]) -> ConnectorOperationResult:
        if "canonical_id" in data:
            success = self.link_canonical_id(record_id, data["canonical_id"])
            return ConnectorOperationResult(
                success=success,
                record_id=record_id,
                action="LINK_CANONICAL_ID"
            )
        return ConnectorOperationResult(
            success=True,
            record_id=record_id,
            action="UPDATE_VENDOR"
        )

    # Backward-compatible convenience methods
    def list_vendors(self) -> List[Dict[str, Any]]:
        res = self.read_records(ConnectorQuery(record_type="vendor", limit=500))
        return res.records

    def get_vendor(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        r = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id,
            EnterpriseRecord.id == vendor_id
        ).first()
        if not r:
            return None
        return {
            "vendor_id": r.id,
            "business_name": r.name,
            "business_address": r.address,
            "country": r.country,
            "tax_number": r.tax_identifier,
            "canonical_id": r.canonical_id,
            "status": r.status
        }

    def link_canonical_id(self, vendor_id: str, canonical_id: str) -> bool:
        r = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id,
            EnterpriseRecord.id == vendor_id
        ).first()
        if not r:
            return False
        r.canonical_id = canonical_id
        self.db.commit()
        return True

    def link_golden_record(self, canonical_id: str, vendor_id: str, crm_account_id: str) -> Dict[str, Any]:
        """
        Executes verified enterprise record linkage.
        Updates both Company B ERP and Company A CRM records with the unified canonical identifier.
        """
        v_rec = self.db.query(EnterpriseRecord).filter(EnterpriseRecord.id == vendor_id).first()
        c_rec = self.db.query(EnterpriseRecord).filter(EnterpriseRecord.id == crm_account_id).first()

        if v_rec:
            v_rec.canonical_id = canonical_id
        if c_rec:
            c_rec.canonical_id = canonical_id

        # Also insert or update Golden Master record
        golden = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.id == canonical_id,
            EnterpriseRecord.system_origin == "GOLDEN_MASTER"
        ).first()

        if not golden:
            golden = EnterpriseRecord(
                id=canonical_id,
                system_origin="GOLDEN_MASTER",
                entity_type="CANONICAL_BUSINESS",
                canonical_id=canonical_id,
                name=c_rec.name if c_rec else (v_rec.name if v_rec else "Unified Entity"),
                address=c_rec.address if c_rec else (v_rec.address if v_rec else ""),
                country=c_rec.country if c_rec else "US",
                tax_identifier=c_rec.tax_identifier if c_rec else (v_rec.tax_identifier if v_rec else None),
                status="LINKED_VERIFIED",
                raw_data={
                    "linked_crm_id": crm_account_id,
                    "linked_erp_id": vendor_id,
                    "resolution_method": "LIGHTGBM_PAIRWISE_MATCH"
                }
            )
            self.db.add(golden)

        self.db.commit()
        return {
            "status": "LINKED_SUCCESS",
            "canonical_id": canonical_id,
            "crm_id": crm_account_id,
            "erp_id": vendor_id
        }

    def create_vendor(self, data: Dict[str, Any]) -> Dict[str, Any]:
        v_id = data.get("vendor_id") or f"ERP-V-{self.db.query(EnterpriseRecord).count() + 201}"
        record = EnterpriseRecord(
            id=v_id,
            system_origin=self.system_id,
            entity_type="VENDOR",
            name=data["business_name"],
            address=data.get("business_address", ""),
            country=data.get("country", "US"),
            tax_identifier=data.get("tax_number"),
            contact_email=data.get("email"),
            canonical_id=data.get("canonical_id"),
            status="ACTIVE",
            raw_data=data.get("erp_metadata", {})
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return {
            "vendor_id": record.id,
            "status": "CREATED",
            "system": self.system_id
        }

    def get_purchase_order(self, po_number: str) -> Optional[Dict[str, Any]]:
        po_store = {
            "PO-2026-8801": {
                "po_number": "PO-2026-8801",
                "vendor_id": "ERP-VND-001",
                "vendor_name": "Apex Global Logistics LLC",
                "total_amount": 5400.00,
                "currency": "USD",
                "status": "APPROVED",
                "line_items": [
                    {"item_code": "LOG-FREIGHT-40FT", "description": "Ocean Freight 40ft Container", "qty": 1, "unit_price": 4200.00, "total": 4200.00},
                    {"item_code": "LOG-PORT-HANDLING", "description": "Port Handling & Customs Clearance", "qty": 1, "unit_price": 1200.00, "total": 1200.00}
                ]
            }
        }
        return po_store.get(po_number)

    def get_goods_receipt(self, gr_number: str) -> Optional[Dict[str, Any]]:
        gr_store = {
            "GR-2026-4401": {
                "gr_number": "GR-2026-4401",
                "po_number": "PO-2026-8801",
                "received_date": "2026-10-18T14:30:00Z",
                "status": "VERIFIED_RECEIVED",
                "received_items": [
                    {"item_code": "LOG-FREIGHT-40FT", "qty_received": 1, "condition": "ACCEPTABLE"},
                    {"item_code": "LOG-PORT-HANDLING", "qty_received": 1, "condition": "ACCEPTABLE"}
                ]
            }
        }
        return gr_store.get(gr_number)
