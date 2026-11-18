"""Versioned, approval-governed adaptation to an explicitly scoped client database."""
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Integer, JSON, create_engine, inspect, Table, MetaData, select
from sqlalchemy.orm import Session

from backend.database.models import Base, User
from backend.database.session import get_db
from backend.security.auth import get_current_user
from backend.security.audit import append_audit_entry
from ml.models.semantic_schema_mapper.inference import SemanticSchemaMapperModel
from ml.models.semantic_schema_mapper.features import check_type_compatibility

router = APIRouter(prefix="/api/adaptation", tags=["Infrastructure adaptation"])


class InfrastructureProfile(Base):
    __tablename__ = "infrastructure_profiles"
    id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    config = Column(JSON, nullable=False)
    revision = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="UNDISCOVERED")
    observed = Column(JSON, nullable=False, default=dict)
    active = Column(JSON, nullable=False, default=dict)
    proposals = Column(JSON, nullable=False, default=list)
    feedback = Column(JSON, nullable=False, default=dict)


class Concept(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    compatible_types: list[str] = Field(min_length=1, max_length=20)


class RegisterProfile(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relative_path: str
    allowed_tables: list[str] = Field(min_length=1, max_length=100)
    concepts: list[Concept] = Field(min_length=1, max_length=100)


class Decision(BaseModel):
    revision: int
    decision: Literal["APPROVE", "REJECT"]
    mappings: dict[str, str] = Field(default_factory=dict)
    comments: str = Field(min_length=3, max_length=2000)


class ReadRequest(BaseModel):
    table: str
    limit: int = Field(default=100, ge=1, le=1000)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def administrator(user):
    if user.role != "ADMIN":
        raise HTTPException(403, "Infrastructure configuration requires an administrator")


def owned(db, identifier, user):
    profile = db.query(InfrastructureProfile).filter_by(id=identifier, owner_id=user.id).first()
    if profile is None:
        raise HTTPException(404, "Infrastructure profile not found")
    return profile


def connect(config):
    root = Path(os.getenv("AVENTRA_DATA_ROOT", "data")).resolve()
    path = (root / config["relative_path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
        raise HTTPException(422, "Source must be an existing SQLite database inside AVENTRA_DATA_ROOT")
    # Prevent URI query parameters in a filename from changing SQLite connection mode.
    from urllib.parse import quote
    return create_engine(f"sqlite:///file:{quote(path.as_posix(), safe='/:')}?mode=ro&uri=true")


def schema_of(connection, config):
    inspector = inspect(connection)
    available = set(inspector.get_table_names())
    schema = {}
    for name in sorted(set(config["allowed_tables"])):
        if name not in available:
            schema[name] = {"missing": True, "columns": []}
            continue
        schema[name] = {"missing": False, "columns": [{"name": column["name"], "datatype": str(column["type"]).lower(), "nullable": column["nullable"], "primary_key": column.get("primary_key", False)} for column in inspector.get_columns(name)], "foreign_keys": inspector.get_foreign_keys(name)}
    return schema


def describe(profile):
    return {"id": profile.id, "name": profile.name, "source": {"provider": "sqlite", "relative_path": profile.config["relative_path"]}, "status": profile.status, "revision": profile.revision, "capabilities": ["READ"], "allowed_tables": profile.config["allowed_tables"], "concepts": profile.config["concepts"], "observed": profile.observed, "active": profile.active, "proposals": profile.proposals, "learned_mapping_count": len(profile.feedback)}


@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [describe(profile) for profile in db.query(InfrastructureProfile).filter_by(owner_id=user.id).all()]


@router.post("/profiles")
def register(req: RegisterProfile, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    administrator(user)
    names = [concept.name for concept in req.concepts]
    if len(names) != len(set(names)) or len(req.allowed_tables) != len(set(req.allowed_tables)):
        raise HTTPException(422, "Concept names and allowed table names must be unique")
    config = req.model_dump(exclude={"name"})
    source = connect(config)
    try:
        with source.connect() as connection:
            schema = schema_of(connection, config)
        if any(table["missing"] for table in schema.values()):
            raise HTTPException(422, "Every scoped table must exist when registering")
    finally:
        source.dispose()
    profile = InfrastructureProfile(id=str(uuid.uuid4()), owner_id=user.id, name=req.name, config=config, revision=0, status="UNDISCOVERED", observed={}, active={}, proposals=[], feedback={})
    db.add(profile)
    db.commit()
    append_audit_entry(db, user.id, user.role, "INFRASTRUCTURE_REGISTERED", "PROFILE", profile.id, {"tables": req.allowed_tables, "capabilities": ["READ"]})
    return describe(profile)


@router.post("/profiles/{identifier}/discover")
def discover(identifier: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    administrator(user)
    profile = owned(db, identifier, user)
    source = connect(profile.config)
    try:
        with source.connect() as connection:
            schema = schema_of(connection, profile.config)
    finally:
        source.dispose()
    digest = fingerprint(schema)
    if profile.observed.get("sha256") == digest:
        return describe(profile)
    previous = profile.observed.get("schema", {})
    model = SemanticSchemaMapperModel()
    model.canonical_concepts = [{"concept": item["name"], "description": item["description"], "compatible_types": item["compatible_types"]} for item in profile.config["concepts"]]
    model.load()
    suggestions = []
    for table, metadata in schema.items():
        for column in metadata["columns"]:
            key = table + "." + column["name"]
            memory = profile.feedback.get(key)
            if memory and memory["datatype"] == column["datatype"]:
                suggestions.append({"source": key, "target": memory["target"], "basis": "APPROVED_FEEDBACK", "approved_observations": memory["count"]})
            else:
                result = model.predict({"fields": [{"field_name": column["name"], "datatype": column["datatype"]}]}).prediction["mappings"][0]
                suggestions.append({"source": key, "target": result["target_canonical_concept"], "score": result["match_confidence"], "basis": "SEMANTIC_SUGGESTION"})
    revision = profile.revision + 1
    proposal = {"revision": revision, "schema_sha256": digest, "schema": schema, "changed_tables": [table for table in schema if schema[table] != previous.get(table)], "suggestions": suggestions, "status": "PENDING_REVIEW"}
    updated = db.query(InfrastructureProfile).filter_by(id=profile.id, revision=profile.revision).update({"revision": revision, "observed": {"sha256": digest, "schema": schema}, "proposals": [*profile.proposals, proposal], "status": "NEEDS_REVIEW"}, synchronize_session=False)
    if not updated:
        db.rollback()
        raise HTTPException(409, "Profile changed; refresh before discovering again")
    db.commit()
    db.refresh(profile)
    append_audit_entry(db, user.id, user.role, "ADAPTATION_PROPOSED", "PROFILE", profile.id, {"revision": revision, "schema_sha256": digest})
    return describe(profile)


@router.post("/profiles/{identifier}/decide")
def decide(identifier: str, req: Decision, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    administrator(user)
    profile = owned(db, identifier, user)
    if req.revision != profile.revision or profile.status != "NEEDS_REVIEW":
        raise HTTPException(409, "Only the current pending revision may be reviewed")
    source = connect(profile.config)
    try:
        with source.connect() as connection:
            digest = fingerprint(schema_of(connection, profile.config))
    finally:
        source.dispose()
    if digest != profile.observed["sha256"]:
        raise HTTPException(409, "Client schema changed during review; discover again")
    proposals = [dict(proposal) for proposal in profile.proposals]
    proposal = proposals[-1]
    feedback = dict(profile.feedback)
    active = profile.active
    if req.decision == "APPROVE":
        concepts = {concept["name"]: concept for concept in profile.config["concepts"]}
        fields = {table + "." + column["name"]: column for table, definition in profile.observed["schema"].items() for column in definition["columns"]}
        used = set()
        for field, target in req.mappings.items():
            if field not in fields or target not in concepts:
                raise HTTPException(422, "Mappings must reference discovered fields and configured client concepts")
            if not check_type_compatibility(fields[field]["datatype"], concepts[target]["compatible_types"]):
                raise HTTPException(422, "A mapping violates its declared datatype constraints")
            pair = (field.rsplit(".", 1)[0], target)
            if pair in used:
                raise HTTPException(422, "A table cannot map two columns to the same concept")
            used.add(pair)
            feedback[field] = {"target": target, "datatype": fields[field]["datatype"], "count": feedback.get(field, {}).get("count", 0) + 1, "approved_by": user.id}
        if not req.mappings or any(table["missing"] for table in profile.observed["schema"].values()):
            raise HTTPException(422, "Activation requires explicit mappings and no missing scoped tables")
        active = {"revision": req.revision, "schema_sha256": digest, "mappings": req.mappings}
    proposal.update(status="APPROVED" if req.decision == "APPROVE" else "REJECTED", reviewed_by=user.id, comments=req.comments, mappings=req.mappings)
    updated = db.query(InfrastructureProfile).filter_by(id=profile.id, revision=req.revision, status="NEEDS_REVIEW").update({"proposals": proposals, "feedback": feedback, "active": active, "status": "ACTIVE" if req.decision == "APPROVE" else "REJECTED"}, synchronize_session=False)
    if not updated:
        db.rollback()
        raise HTTPException(409, "This revision was already reviewed")
    db.commit()
    db.refresh(profile)
    append_audit_entry(db, user.id, user.role, "ADAPTATION_" + req.decision, "PROFILE", profile.id, {"revision": req.revision, "schema_sha256": digest, "comments": req.comments, "mappings": req.mappings})
    return describe(profile)


@router.post("/profiles/{identifier}/read")
def read_client(identifier: str, req: ReadRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = owned(db, identifier, user)
    if profile.status != "ACTIVE" or req.table not in profile.config["allowed_tables"]:
        raise HTTPException(409, "An active approved configuration and scoped table are required")
    source = connect(profile.config)
    try:
        with source.connect() as connection:
            schema = schema_of(connection, profile.config)
            if fingerprint(schema) != profile.active["schema_sha256"]:
                raise HTTPException(409, "Client schema drift detected; rediscover and approve before reading")
            mappings = {field[len(req.table)+1:]: target for field, target in profile.active["mappings"].items() if field.startswith(req.table + ".")}
            if not mappings:
                raise HTTPException(409, "No approved fields for this table")
            table = Table(req.table, MetaData(), autoload_with=connection)
            rows = connection.execute(select(*(table.c[field] for field in mappings)).limit(req.limit)).mappings()
            records = [{target: row[field] for field, target in mappings.items()} for row in rows]
    finally:
        source.dispose()
    append_audit_entry(db, user.id, user.role, "CLIENT_DATA_READ", "PROFILE", profile.id, {"table": req.table, "revision": profile.active["revision"], "row_count": len(records)})
    return {"profile_id": profile.id, "configuration_revision": profile.active["revision"], "schema_sha256": profile.active["schema_sha256"], "records": records, "source": "CLIENT_DATABASE", "client_mutations_performed": False}
