"""
Canonical Data Contracts for AVENTRA Enterprise Platform.
Establishes standardized data models across heterogeneous CRM, ERP, Email, and Database systems.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, EmailStr


# ==========================================
# 1. CANONICAL CRM CONTRACTS
# ==========================================

class CanonicalAccount(BaseModel):
    canonical_id: str = Field(..., description="Globally unique canonical master record identifier")
    account_name: str = Field(..., description="Normalized primary trading name")
    legal_name: Optional[str] = Field(None, description="Registered legal corporate entity name")
    domain: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = Field(default="US", description="ISO 2-letter country code")
    tax_identifier: Optional[str] = Field(None, description="Tax ID (EIN, VAT, GST)")
    primary_email: Optional[str] = None
    phone: Optional[str] = None
    status: str = Field(default="ACTIVE")
    source_system_records: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Lineage pointers: [{'system': 'COMPANY_A_CRM', 'id': 'CRM-001'}]"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CanonicalContact(BaseModel):
    contact_id: str
    account_id: Optional[str] = None
    first_name: str
    last_name: str
    full_name: str
    email: str
    phone: Optional[str] = None
    job_title: Optional[str] = None
    source_system: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CanonicalLead(BaseModel):
    lead_id: str
    company_name: str
    contact_name: Optional[str] = None
    email: Optional[str] = None
    status: str = Field(default="NEW")
    lead_score: float = Field(default=0.0)
    source_system: str


# ==========================================
# 2. CANONICAL ERP & FINANCIAL CONTRACTS
# ==========================================

class CanonicalLineItem(BaseModel):
    line_number: int = Field(default=1)
    sku_or_code: str
    description: str
    quantity: float
    unit_price: float
    total_price: float
    unit_of_measure: Optional[str] = "EA"


class CanonicalVendor(BaseModel):
    vendor_id: str
    vendor_name: str
    legal_name: Optional[str] = None
    tax_identifier: Optional[str] = None
    country: str = "US"
    currency: str = "USD"
    payment_terms: Optional[str] = "NET_30"
    canonical_id: Optional[str] = None
    status: str = "ACTIVE"
    source_system: str = "ERP"


class CanonicalPurchaseOrder(BaseModel):
    po_number: str
    vendor_id: str
    vendor_name: str
    order_date: datetime
    total_amount: float
    currency: str = "USD"
    status: str = Field(default="APPROVED", description="DRAFT, APPROVED, RECEIVED, CLOSED")
    line_items: List[CanonicalLineItem] = Field(default_factory=list)
    source_system: str = "ERP"


class CanonicalInvoice(BaseModel):
    invoice_number: str
    vendor_id: str
    po_number: Optional[str] = None
    invoice_date: datetime
    due_date: Optional[datetime] = None
    subtotal: float
    tax_amount: float = 0.0
    total_amount: float
    currency: str = "USD"
    line_items: List[CanonicalLineItem] = Field(default_factory=list)
    source_system: str = "ERP"


class CanonicalGoodsReceipt(BaseModel):
    gr_number: str
    po_number: str
    received_date: datetime
    received_items: List[Dict[str, Any]] = Field(default_factory=list)
    receipt_status: str = "VERIFIED_RECEIVED"
    source_system: str = "ERP"


# ==========================================
# 3. CANONICAL EMAIL & COMMUNICATION
# ==========================================

class CanonicalEmailMessage(BaseModel):
    message_id: str
    thread_id: str
    sender_email: str
    sender_name: Optional[str] = None
    recipients: List[str]
    cc: List[str] = Field(default_factory=list)
    subject: str
    body_plain: str
    snippet: Optional[str] = None
    received_at: datetime
    has_attachments: bool = False
    attachment_names: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)


class CanonicalEmailDraft(BaseModel):
    draft_id: Optional[str] = None
    thread_id: Optional[str] = None
    to: List[str]
    subject: str
    body_text: str
    requires_approval: bool = True
    intended_action: str = "EXTERNAL_COMMUNICATION"


# ==========================================
# 4. CANONICAL DATABASE CONTRACTS
# ==========================================

class CanonicalColumnMetadata(BaseModel):
    column_name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    foreign_key_target: Optional[str] = None


class CanonicalTableMetadata(BaseModel):
    table_name: str
    schema_name: str = "public"
    columns: List[CanonicalColumnMetadata]
    primary_keys: List[str] = Field(default_factory=list)
    estimated_rows: Optional[int] = None


class CanonicalQueryResult(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_returned: int
    execution_time_ms: float
    is_truncated: bool = False

