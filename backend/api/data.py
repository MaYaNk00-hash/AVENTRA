from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.database.models import EnterpriseRecord, SchemaMapping
from backend.connectors.company_a_crm import CompanyACRMConnector
from backend.connectors.company_b_erp import CompanyBERPConnector
from ml.shared.model_registry.registry import ModelRegistry

router = APIRouter(prefix="/api/data", tags=["Data Hub & Connectors"])


class CreateRecordRequest(BaseModel):
    system_origin: str = "COMPANY_A_CRM"
    business_name: str
    business_address: str = ""
    country: str = "US"
    tax_identifier: Optional[str] = None
    contact_email: Optional[str] = None


class AlignSchemaRequest(BaseModel):
    fields: List[Dict[str, Any]]


@router.get("/records")
def list_records(system_origin: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(EnterpriseRecord)
    if system_origin:
        query = query.filter(EnterpriseRecord.system_origin == system_origin)
    recs = query.order_by(EnterpriseRecord.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "system_origin": r.system_origin,
            "entity_type": r.entity_type,
            "name": r.name,
            "address": r.address,
            "country": r.country,
            "tax_identifier": r.tax_identifier,
            "contact_email": r.contact_email,
            "canonical_id": r.canonical_id,
            "status": r.status,
            "raw_data": r.raw_data,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in recs
    ]


@router.post("/records")
def create_customer_record(req: CreateRecordRequest, db: Session = Depends(get_db)):
    crm = CompanyACRMConnector(db)
    res = crm.create_account({
        "account_name": req.business_name,
        "street_address": req.business_address,
        "country": req.country,
        "federal_tax_id": req.tax_identifier,
        "primary_email": req.contact_email
    })
    return res


@router.get("/schemas")
def get_system_schemas():
    return {
        "COMPANY_A_CRM": {
            "version": "v1.0",
            "table": "crm_accounts",
            "fields": [
                {"name": "account_name", "datatype": "varchar(255)", "description": "Customer business entity name"},
                {"name": "street_address", "datatype": "text", "description": "Billing location address"},
                {"name": "country", "datatype": "varchar(10)", "description": "Country designation"},
                {"name": "federal_tax_id", "datatype": "varchar(50)", "description": "Federal tax ID / EIN"},
                {"name": "primary_email", "datatype": "varchar(100)", "description": "Primary accounts contact"}
            ]
        },
        "COMPANY_B_ERP": {
            "version": "v1.0",
            "table": "erp_vendors",
            "fields": [
                {"name": "business_name", "datatype": "varchar(255)", "description": "Vendor legal enterprise name"},
                {"name": "business_address", "datatype": "text", "description": "Physical headquarters address"},
                {"name": "country", "datatype": "varchar(10)", "description": "Country code"},
                {"name": "tax_number", "datatype": "varchar(50)", "description": "Tax identification number"},
                {"name": "canonical_id", "datatype": "varchar(50)", "description": "Golden record universal key"}
            ]
        }
    }


@router.post("/drift/simulate")
def simulate_schema_drift():
    """
    Simulates schema drift on Company A CRM:
    - Renames 'account_name' to 'organization_legal_name'
    - Modifies 'street_address' to varchar(500)
    - Adds 'credit_risk_rating'
    Invokes Model M6 Adaptation Recommender to synthesize diff and impact analysis.
    """
    model = ModelRegistry.get_model("adaptation_recommender")
    payload = {
        "old_schema": {
            "system_name": "COMPANY_A_CRM",
            "version": "v1.0",
            "fields": [
                {"name": "account_name", "datatype": "varchar(255)"},
                {"name": "street_address", "datatype": "text"},
                {"name": "federal_tax_id", "datatype": "varchar(50)"}
            ]
        },
        "new_schema": {
            "system_name": "COMPANY_A_CRM",
            "version": "v2.0",
            "fields": [
                {"name": "organization_legal_name", "datatype": "varchar(255)"},
                {"name": "street_address", "datatype": "varchar(500)"},
                {"name": "federal_tax_id", "datatype": "varchar(50)"},
                {"name": "credit_risk_rating", "datatype": "integer"}
            ]
        },
        "active_workflows": [
            {
                "id": "wf-customer-onboarding",
                "name": "Customer Onboarding & Duplicate Resolution",
                "required_fields": ["account_name", "federal_tax_id"]
            }
        ]
    }
    out = model.predict(payload)
    return out.model_dump()


@router.post("/mappings/align")
def align_custom_schema(req: AlignSchemaRequest):
    """
    Uses Model M2 Semantic Schema Mapper to align source fields to canonical definitions.
    """
    model = ModelRegistry.get_model("semantic_schema_mapper")
    out = model.predict({"fields": req.fields})
    return out.model_dump()

