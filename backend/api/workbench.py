"""Authenticated analysis of supplied enterprise datasets. No simulator fallback."""
import csv
import hashlib
import io
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, JSON, select, create_engine, MetaData, Table
from sqlalchemy.orm import Session
from sklearn.ensemble import IsolationForest

from backend.database.models import Base, User
from backend.database.session import get_db
from backend.security.auth import get_current_user
from backend.security.audit import append_audit_entry
from ml.shared.model_registry.registry import ModelRegistry

router = APIRouter(prefix="/api/workbench", tags=["Real data workbench"])


class Dataset(Base):
    __tablename__ = "workbench_datasets"
    id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    domain = Column(String, nullable=False)
    digest = Column(String, nullable=False)
    records = Column(JSON, nullable=False)


class ImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    domain: Literal["CRM", "ERP", "DATABASE"]
    format: Literal["csv", "json"]
    content: str = Field(min_length=1, max_length=2_000_000)


class DatabaseImport(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relative_path: str
    table: str
    domain: Literal["CRM", "ERP", "DATABASE"] = "DATABASE"


def metadata(dataset):
    return {"id": dataset.id, "name": dataset.name, "domain": dataset.domain, "sha256": dataset.digest, "row_count": len(dataset.records), "columns": list(dict.fromkeys(key for row in dataset.records for key in row))}


def save_rows(rows, name, domain, db, user):
    if not rows or len(rows) > 10000 or any(not isinstance(row, dict) or not row for row in rows):
        raise HTTPException(422, "Supply 1–10000 nonempty record objects")
    if len(json.dumps(rows, allow_nan=False, default=str).encode()) > 2_000_000:
        raise HTTPException(413, "Dataset exceeds 2 MB")
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
    dataset = Dataset(id=str(uuid.uuid4()), owner_id=user.id, name=name, domain=domain, digest=digest, records=rows)
    db.add(dataset)
    db.commit()
    append_audit_entry(db, user.id, user.role, "DATASET_IMPORTED", "DATASET", dataset.id, metadata(dataset))
    return metadata(dataset)


@router.post("/datasets")
def import_dataset(req: ImportRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        if req.format == "json":
            rows = json.loads(req.content, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite number")))
            if not isinstance(rows, list):
                raise ValueError("JSON must be an array of objects")
        else:
            reader = csv.DictReader(io.StringIO(req.content.lstrip("\ufeff")))
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("CSV requires unique column headers")
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError("CSV row lengths must match the headers")
        return save_rows(rows, req.name, req.domain, db, user)
    except (ValueError, TypeError, csv.Error) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/database-import")
def import_database(req: DatabaseImport, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "ADMIN":
        raise HTTPException(403, "Database imports require an administrator")
    root = Path(os.getenv("AVENTRA_DATA_ROOT", "data")).resolve()
    path = (root / req.relative_path).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
        raise HTTPException(422, "Choose an existing SQLite file inside AVENTRA_DATA_ROOT")
    source = create_engine(f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true")
    try:
        table = Table(req.table, MetaData(), autoload_with=source)
        with source.connect() as connection:
            rows = [dict(row) for row in connection.execute(select(table).limit(10001)).mappings()]
        # Normalize dates and decimals into portable JSON values.
        rows = json.loads(json.dumps(rows, default=str, allow_nan=False))
        return save_rows(rows, req.name, req.domain, db, user)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(422, "Unable to read the selected table") from error
    finally:
        source.dispose()


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [metadata(item) for item in db.query(Dataset).filter_by(owner_id=user.id).all()]


class AnalysisRequest(BaseModel):
    task: Literal["entities", "schema", "invoice", "anomaly"]
    dataset_id: str
    candidate_dataset_id: str | None = None
    mapping: dict[str, str] = Field(default_factory=dict)
    candidate_mapping: dict[str, str] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)


def owned_dataset(db, identifier, user):
    dataset = db.query(Dataset).filter_by(id=identifier, owner_id=user.id).first()
    if dataset is None:
        raise HTTPException(404, "Dataset not found")
    return dataset


def mapped_records(dataset, mapping, required):
    columns = metadata(dataset)["columns"]
    if any(field not in mapping or mapping[field] not in columns for field in required):
        raise ValueError("Explicit column mappings are required for: " + ", ".join(required))
    if any(column not in columns for column in mapping.values()):
        raise ValueError("Mapping references an unknown source column")
    return [{canonical: row.get(column) for canonical, column in mapping.items()} for row in dataset.records]


@router.post("/analyze")
def analyze(req: AnalysisRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dataset = owned_dataset(db, req.dataset_id, user)
    candidate = owned_dataset(db, req.candidate_dataset_id, user) if req.candidate_dataset_id else None
    try:
        if candidate is not None and candidate.id == dataset.id:
            raise ValueError("Reference data must be a separate dataset")
        model_id = {"entities": "entity_resolution", "schema": "semantic_schema_mapper", "invoice": "invoice_reconciliation", "anomaly": "history_isolation_forest"}[req.task]
        if req.task == "entities":
            if not candidate:
                raise ValueError("Choose a separate candidate dataset")
            fields = ["entity_id", "business_name", "business_address", "country"]
            queries = mapped_records(dataset, req.mapping, fields)
            candidates = mapped_records(candidate, req.candidate_mapping, fields)
            if len(queries) > 500 or len(candidates) > 10000:
                raise ValueError("Entity analysis supports at most 500 queries and 10000 candidates")
            for records in [queries, candidates]:
                identifiers = [str(row["entity_id"]) for row in records]
                if len(set(identifiers)) != len(identifiers) or any(not row["business_name"] or not row["entity_id"] or not row["country"] for row in records):
                    raise ValueError("Entity IDs must be unique; IDs, names and countries must be nonempty")
            from ml.models.entity_resolution.blocking import MultiKeyBlocker
            blocker = MultiKeyBlocker()
            blocker.build_index(candidates)
            indexed = {str(row["entity_id"]): row for row in candidates}
            output = []
            for query in queries:
                retrieved = [indexed[key] for key in blocker.retrieve_candidates(query, top_k=50) if str(indexed[key]["country"]).casefold() == str(query["country"]).casefold()]
                result = ModelRegistry.get_model(model_id).predict({"query": query, "candidates": retrieved}).model_dump()
                output.append({"source_entity_id": query["entity_id"], "retrieved_candidates": len(retrieved), "result": result})
        elif req.task == "schema":
            fields = []
            for column in metadata(dataset)["columns"]:
                values = [row[column] for row in dataset.records if row.get(column) is not None][:20]
                datatype = req.options.get("datatypes", {}).get(column)
                if not datatype:
                    datatype = "float" if values and all(isinstance(value, (float, int)) and not isinstance(value, bool) for value in values) else "string"
                fields.append({"field_name": column, "datatype": datatype, "sample_values": values[:3]})
            output = ModelRegistry.get_model(model_id).predict({"fields": fields}).model_dump()
        elif req.task == "invoice":
            # Each JSON row follows the validated reconciliation contract, including its actual PO and receipt.
            output = [ModelRegistry.get_model(model_id).predict(row).model_dump() for row in dataset.records]
        else:
            if not candidate:
                raise ValueError("Provide a separate historical transaction dataset")
            history = mapped_records(candidate, req.candidate_mapping, ["amount"])
            transactions = mapped_records(dataset, req.mapping, ["amount"])
            def amounts(rows):
                values = np.array([float(row["amount"]) for row in rows])
                if not np.isfinite(values).all() or (values < 0).any():
                    raise ValueError("Amounts must be finite nonnegative numbers")
                return values
            historical, current = amounts(history), amounts(transactions)
            if len(historical) < 30 or len(np.unique(historical)) < 5:
                raise ValueError("Supply at least 30 historical transactions with 5 distinct amounts")
            if not req.options.get("currency"):
                raise ValueError("Declare the single currency used by both transaction datasets")
            forest = IsolationForest(n_estimators=150, contamination=.05, random_state=42, n_jobs=1)
            forest.fit(np.log1p(historical).reshape(-1, 1))
            scores = -forest.decision_function(np.log1p(current).reshape(-1, 1))
            output = {"training_rows": len(history), "currency": req.options["currency"], "method": "IsolationForest on log(amount); positive decision score means outlier, not fraud probability", "transactions": [{"row_index": index, "amount": float(amount), "outlier_score": float(score), "requires_review": bool(score > 0)} for index, (amount, score) in enumerate(zip(current, scores))]}
        outputs = output if isinstance(output, list) else [output]
        for entry in outputs:
            prediction = entry.get("result", entry)
            if prediction.get("execution_status") == "FAILED":
                raise ValueError(prediction.get("error_details") or "Model input validation failed")
        result = {"analysis_id": str(uuid.uuid4()), "task": req.task, "model": model_id, "datasets": [metadata(item) for item in [dataset, candidate] if item], "output": output, "mutations_performed": False, "status": "ANALYZED", "limitations": "Read-only analysis; no enterprise writes. Scores are recommendations and require review. No production accuracy guarantee."}
        append_audit_entry(db, user.id, user.role, "DATASET_ANALYZED", "ANALYSIS", result["analysis_id"], {"task": req.task, "model": model_id, "dataset_hashes": [item["sha256"] for item in result["datasets"]]})
        return result
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(422, str(error)) from error
