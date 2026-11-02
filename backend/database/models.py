import datetime
import uuid
import json
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(30), nullable=False, default="OPERATIONS_APPROVER")  # ADMIN, COMPLIANCE_OFFICER, OPERATIONS_APPROVER, AUDITOR
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AuditLedgerEntry(Base):
    """
    Cryptographically chained append-only audit ledger.
    Every entry includes SHA-256(prev_hash + payload_hash + metadata) guaranteeing tamper evidence.
    """
    __tablename__ = "audit_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    actor_id = Column(String(50), nullable=False)
    actor_role = Column(String(30), nullable=False)
    action_type = Column(String(50), nullable=False, index=True)  # RECORD_MERGE, APPROVAL_GRANTED, SCHEMA_MIGRATED, etc.
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=False)
    current_hash = Column(String(64), nullable=False, index=True)
    details = Column(JSON, default=dict)
    is_verified = Column(Boolean, default=True)


class WorkflowDefinition(Base):
    __tablename__ = "workflows"

    id = Column(String(50), primary_key=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, default="")
    trigger_type = Column(String(50), default="MANUAL")  # MANUAL, WEBHOOK, SCHEDULED
    nodes = Column(JSON, nullable=False, default=list)
    edges = Column(JSON, nullable=False, default=list)
    status = Column(String(30), default="ACTIVE")
    created_by = Column(String(50), default="system")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(50), ForeignKey("workflows.id"), nullable=False, index=True)
    triggered_by = Column(String(50), nullable=False)
    status = Column(String(30), default="PENDING", index=True)  # PENDING, RUNNING, AWAITING_APPROVAL, COMPLETED, FAILED
    current_step = Column(String(50), default="INIT")
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    context_data = Column(JSON, default=dict)
    execution_events = Column(JSON, default=list)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, default=0.0)
    error_details = Column(Text, nullable=True)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_id = Column(String(36), ForeignKey("workflow_executions.id"), nullable=False, index=True)
    step_id = Column(String(50), nullable=False)
    action_type = Column(String(50), nullable=False)
    risk_level = Column(String(20), nullable=False, default="MEDIUM")  # LOW, MEDIUM, HIGH, CRITICAL
    confidence_score = Column(Float, nullable=True)
    evidence = Column(JSON, default=dict)
    status = Column(String(30), default="PENDING", index=True)  # PENDING, APPROVED, REJECTED, EXPIRED
    reviewed_by = Column(String(50), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewer_comments = Column(Text, nullable=True)
    nonce_token = Column(String(64), nullable=False)  # Cryptographic single-use nonce
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class EnterpriseRecord(Base):
    __tablename__ = "enterprise_records"

    id = Column(String(50), primary_key=True)
    system_origin = Column(String(50), nullable=False, index=True)  # COMPANY_A_CRM, COMPANY_B_ERP, GOLDEN_MASTER
    entity_type = Column(String(50), nullable=False, default="BUSINESS_ENTITY")
    canonical_id = Column(String(50), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    address = Column(Text, default="")
    country = Column(String(10), default="US")
    tax_identifier = Column(String(50), nullable=True)
    contact_email = Column(String(100), nullable=True)
    status = Column(String(30), default="ACTIVE")
    raw_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class SchemaMapping(Base):
    __tablename__ = "schema_mappings"

    id = Column(String(50), primary_key=True)
    source_system = Column(String(50), nullable=False)
    target_system = Column(String(50), nullable=False)
    version = Column(String(20), default="v1.0")
    mappings = Column(JSON, nullable=False, default=list)
    status = Column(String(30), default="ACTIVE")
    approved_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

