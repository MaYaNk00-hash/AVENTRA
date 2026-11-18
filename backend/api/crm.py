"""
AVENTRA Enterprise CRM Integration API.
Provides REST endpoints for:
- Accounts, Contacts, Leads, and Organization read/create/update operations
- Search, filtering, cursor pagination, and incremental synchronization
- Model M1 LightGBM entity resolution & duplicate detection
- Field-level conflict analysis & merge proposals
- Permission and governance approval enforcement on writes
- Multi-schema support (Salesforce / Company A CRM vs HubSpot CRM)
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.connectors.base import ConnectorQuery
from backend.connectors.crm_adapters import (
    SalesforceCRMAdapter,
    HubSpotCRMAdapter,
    crm_record_to_canonical_account
)
from backend.connectors.crm_duplicates import CRMDuplicateResolver
from backend.security.audit import append_audit_entry

router = APIRouter(prefix="/api/crm", tags=["Enterprise CRM Integration"])


# ==========================================
# SCHEMAS
# ==========================================

class CreateAccountRequest(BaseModel):
    account_name: str = Field(..., min_length=2, max_length=200)
    street_address: Optional[str] = ""
    country: str = "US"
    federal_tax_id: Optional[str] = None
    primary_email: Optional[str] = None
    annual_revenue: float = 0.0
    adapter: str = "COMPANY_A_CRM"


class UpdateAccountRequest(BaseModel):
    account_name: Optional[str] = None
    street_address: Optional[str] = None
    country: Optional[str] = None
    federal_tax_id: Optional[str] = None
    primary_email: Optional[str] = None
    annual_revenue: Optional[float] = None
    status: Optional[str] = None


class CreateContactRequest(BaseModel):
    account_id: Optional[str] = None
    first_name: Optional[str] = ""
    last_name: str = Field(..., min_length=1)
    email: str = Field(..., description="Valid business email")
    phone: Optional[str] = None
    job_title: Optional[str] = None
    adapter: str = "COMPANY_A_CRM"


class CreateLeadRequest(BaseModel):
    company_name: str = Field(..., min_length=2)
    contact_name: Optional[str] = None
    email: Optional[str] = None
    lead_status: str = "NEW"
    lead_score: float = 50.0
    adapter: str = "COMPANY_A_CRM"


class DuplicateScanRequest(BaseModel):
    record: Dict[str, Any]
    threshold: float = 0.85


class RequestMergePayload(BaseModel):
    execution_id: str
    source_record_id: str
    target_record_id: str
    match_probability: float
    proposed_canonical_name: str


class ExecuteMergePayload(BaseModel):
    approval_id: str
    reviewer_name: str
    reviewer_role: str
    canonical_id: Optional[str] = None


def _get_adapter(adapter_name: str, db: Session):
    norm = adapter_name.upper()
    if norm in ["HUBSPOT", "HUBSPOT_CRM"]:
        return HubSpotCRMAdapter(db)
    return SalesforceCRMAdapter(db)


# ==========================================
# ENDPOINTS
# ==========================================

@router.get("/accounts")
def list_accounts(
    adapter: str = Query("COMPANY_A_CRM", description="COMPANY_A_CRM or HUBSPOT_CRM"),
    search: Optional[str] = None,
    country: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    incremental_since: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Reads CRM accounts/companies with search, filtering, cursor pagination, and incremental sync.
    """
    crm = _get_adapter(adapter, db)
    filters = {}
    if search:
        filters["search"] = search
    if country:
        filters["country"] = country
        filters["country_code"] = country
    if status_filter:
        filters["status"] = status_filter
        filters["lifecycle_stage"] = status_filter

    query = ConnectorQuery(
        record_type="account" if "COMPANY_A" in adapter.upper() else "company",
        filters=filters,
        limit=limit,
        cursor=cursor,
        incremental_since=incremental_since
    )
    res = crm.read_records(query)
    return res.model_dump()


@router.get("/accounts/{account_id}")
def get_account(
    account_id: str,
    adapter: str = Query("COMPANY_A_CRM"),
    db: Session = Depends(get_db)
):
    crm = _get_adapter(adapter, db)
    rec = crm.get_record_by_id("account", account_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found.")
    return rec


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(
    req: CreateAccountRequest,
    actor_id: str = "operator",
    actor_role: str = "OPERATIONS_APPROVER",
    db: Session = Depends(get_db)
):
    """
    Creates a new account in the designated CRM with field-level validation and audit logging.
    """
    crm = _get_adapter(req.adapter, db)
    try:
        if "HUBSPOT" in req.adapter.upper():
            data = {
                "legal_organization_name": req.account_name,
                "billing_address": req.street_address,
                "country_code": req.country,
                "tax_ein": req.federal_tax_id,
                "domain_email": req.primary_email,
                "annual_revenue_usd": req.annual_revenue
            }
        else:
            data = {
                "account_name": req.account_name,
                "street_address": req.street_address,
                "country": req.country,
                "federal_tax_id": req.federal_tax_id,
                "primary_email": req.primary_email,
                "annual_revenue": req.annual_revenue
            }
        
        result = crm.create_record("account", data)

        append_audit_entry(
            db=db,
            actor_id=actor_id,
            actor_role=actor_role,
            action_type="CRM_ACCOUNT_CREATED",
            entity_type="CRM_ACCOUNT",
            entity_id=result.record_id or "NEW",
            details={"name": req.account_name, "adapter": req.adapter}
        )

        return result.model_dump()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.put("/accounts/{account_id}")
def update_account(
    account_id: str,
    req: UpdateAccountRequest,
    adapter: str = Query("COMPANY_A_CRM"),
    actor_id: str = "operator",
    actor_role: str = "OPERATIONS_APPROVER",
    db: Session = Depends(get_db)
):
    """
    Updates an existing CRM account with field-level validation and audit logging.
    """
    crm = _get_adapter(adapter, db)
    try:
        update_data = {k: v for k, v in req.model_dump().items() if v is not None}
        result = crm.update_record("account", account_id, update_data)
        if not result.success:
            raise HTTPException(status_code=404, detail=result.error_message)

        append_audit_entry(
            db=db,
            actor_id=actor_id,
            actor_role=actor_role,
            action_type="CRM_ACCOUNT_UPDATED",
            entity_type="CRM_ACCOUNT",
            entity_id=account_id,
            details={"updated_fields": list(update_data.keys()), "adapter": adapter}
        )

        return result.model_dump()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.get("/contacts")
def list_contacts(
    adapter: str = Query("COMPANY_A_CRM"),
    search: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    db: Session = Depends(get_db)
):
    crm = _get_adapter(adapter, db)
    res = crm.read_records(ConnectorQuery(
        record_type="contact",
        filters={"search": search} if search else {},
        limit=limit,
        cursor=cursor
    ))
    return res.model_dump()


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
def create_contact(req: CreateContactRequest, db: Session = Depends(get_db)):
    crm = _get_adapter(req.adapter, db)
    try:
        res = crm.create_record("contact", req.model_dump())
        return res.model_dump()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.get("/leads")
def list_leads(
    adapter: str = Query("COMPANY_A_CRM"),
    search: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    db: Session = Depends(get_db)
):
    crm = _get_adapter(adapter, db)
    res = crm.read_records(ConnectorQuery(
        record_type="lead",
        filters={"search": search} if search else {},
        limit=limit,
        cursor=cursor
    ))
    return res.model_dump()


@router.post("/leads", status_code=status.HTTP_201_CREATED)
def create_lead(req: CreateLeadRequest, db: Session = Depends(get_db)):
    crm = _get_adapter(req.adapter, db)
    try:
        res = crm.create_record("lead", req.model_dump())
        return res.model_dump()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/duplicates/scan")
def scan_crm_duplicates(req: DuplicateScanRequest, db: Session = Depends(get_db)):
    """
    Connects Model M1 LightGBM Entity Resolution to evaluate live CRM duplicate candidates
    and detect field-level conflicts.
    """
    resolver = CRMDuplicateResolver(db)
    result = resolver.find_duplicates(
        query_record=req.record,
        threshold=req.threshold
    )
    return result


@router.post("/duplicates/request-merge")
def request_crm_merge(req: RequestMergePayload, db: Session = Depends(get_db)):
    """
    Submits a high-confidence merge to the Governance Approval Gate.
    """
    resolver = CRMDuplicateResolver(db)
    appr_req = resolver.submit_governed_merge_request(
        execution_id=req.execution_id,
        source_record_id=req.source_record_id,
        target_record_id=req.target_record_id,
        match_probability=req.match_probability,
        proposed_canonical_name=req.proposed_canonical_name
    )
    return {
        "status": "APPROVAL_REQUIRED",
        "approval_id": appr_req.id,
        "nonce_token": appr_req.nonce_token,
        "risk_level": appr_req.risk_level
    }


@router.post("/duplicates/execute-merge")
def execute_crm_merge(req: ExecuteMergePayload, db: Session = Depends(get_db)):
    """
    Executes authorized identity merge and updates canonical master linkage.
    """
    resolver = CRMDuplicateResolver(db)
    res = resolver.execute_authorized_merge(
        approval_id=req.approval_id,
        reviewer_name=req.reviewer_name,
        reviewer_role=req.reviewer_role,
        canonical_id=req.canonical_id
    )
    return res


@router.get("/sync/incremental")
def incremental_sync_stream(
    watermark: str = Query(..., description="ISO 8601 timestamp watermark"),
    adapter: str = Query("COMPANY_A_CRM"),
    db: Session = Depends(get_db)
):
    """
    Returns only records mutated since the provided timestamp watermark.
    """
    crm = _get_adapter(adapter, db)
    res = crm.read_records(ConnectorQuery(
        record_type="account",
        incremental_since=watermark,
        limit=500
    ))
    return {
        "adapter": adapter,
        "watermark_queried": watermark,
        "new_records_count": res.count,
        "records": res.records
    }
