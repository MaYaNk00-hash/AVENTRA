"""
Company B ERP Simulator Connector.
Simulates an Enterprise Resource Planning system managing vendors, purchase orders, goods receipts, and general ledger postings.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.database.models import EnterpriseRecord


class CompanyBERPConnector:
    def __init__(self, db: Session):
        self.db = db
        self.system_id = "COMPANY_B_ERP"

    def list_vendors(self) -> List[Dict[str, Any]]:
        records = self.db.query(EnterpriseRecord).filter(
            EnterpriseRecord.system_origin == self.system_id
        ).all()
        return [
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

    def get_purchase_order(self, po_number: str) -> Optional[Dict[str, Any]]:
        # Realistic fixtures for ERP PO lookup
        po_fixtures = {
            "PO-4401": {
                "po_number": "PO-4401",
                "vendor_id": "ERP-B-502",
                "vendor_name": "Supreme Industrial Supply Co",
                "total_amount": 1080.0,
                "status": "APPROVED",
                "line_items": [
                    {"sku": "SKU-500", "description": "Carbon Steel Valves", "quantity": 10, "unit_price": 100.0, "total": 1000.0}
                ]
            },
            "PO-8819": {
                "po_number": "PO-8819",
                "vendor_id": "ERP-B-501",
                "vendor_name": "Apex Global Logistics Inc",
                "total_amount": 1080.0,
                "status": "APPROVED",
                "line_items": [
                    {"sku": "SKU-A", "description": "Heavy Industrial Supplies", "quantity": 10, "unit_price": 100.0, "total": 1000.0}
                ]
            }
        }
        return po_fixtures.get(po_number)

    def get_goods_receipt(self, po_number: str) -> Optional[Dict[str, Any]]:
        gr_fixtures = {
            "PO-4401": {
                "receipt_id": "GR-909",
                "po_number": "PO-4401",
                "received_items": {"SKU-500": 10.0}
            },
            "PO-8819": {
                "receipt_id": "GR-552",
                "po_number": "PO-8819",
                "received_items": {"SKU-A": 10.0}
            }
        }
        return gr_fixtures.get(po_number)

