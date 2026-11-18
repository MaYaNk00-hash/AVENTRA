"""Fetch a new immutable source snapshot and prepare an isolated editable demo.

python infrastructure/scripts/import_open_company_demo.py --connect
Network is used only for fetching the public source, never for fabricated results.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import uuid

import requests

ROOT = Path(__file__).resolve().parents[2]
PUBLISHER = "https://github.com/datasets/s-and-p-500-companies"
CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
PACKAGE_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/datapackage.json"


def build_snapshot(payload, package, destination, limit=200):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    required = {"Symbol", "Security", "GICS Sector", "Headquarters Location"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("Publisher schema changed; import stopped")
    if not 1 <= limit <= 500:
        raise ValueError("Sample size must be 1 to 500")
    if not any(license.get("name") == "ODC-PDDL-1.0" for license in package.get("licenses", [])):
        raise ValueError("Publisher license metadata changed; review before importing")
    all_rows = list(reader)
    # Preserve source ordering and text. One row is a listed security, not
    # necessarily one unique legal company (multiple share classes can occur).
    rows = all_rows[:limit]
    symbols = [row["Symbol"] for row in rows]
    if not rows or len(set(symbols)) != len(symbols) or any(not value for value in symbols):
        raise ValueError("Empty data or non-unique security key")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "source.csv").write_bytes(payload)
    (destination / "datapackage.json").write_text(json.dumps(package, indent=2), encoding="utf-8")
    database = destination / "companies.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE companies (symbol TEXT PRIMARY KEY, company_name TEXT NOT NULL, sector TEXT, headquarters TEXT, sub_industry TEXT, review_state TEXT NOT NULL)")
        db.executemany("INSERT INTO companies VALUES (?,?,?,?,?,?)", [(r["Symbol"], r["Security"], r["GICS Sector"], r["Headquarters Location"], r.get("GICS Sub-Industry", ""), "unreviewed") for r in rows])
        db.execute("CREATE TABLE sector_counts (sector TEXT PRIMARY KEY, security_count INTEGER NOT NULL)")
        db.executemany("INSERT INTO sector_counts VALUES (?,?)", sorted(Counter(r["GICS Sector"] for r in rows).items()))
    manifest = {
        "title": "Open company directory — public-data prototype",
        "publisher_url": PUBLISHER, "download_url": CSV_URL,
        "upstream": "Wikipedia company directory, distributed by datasets/DataHub",
        "license": "ODC-PDDL-1.0 (publisher declaration)",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "source_rows": len(all_rows), "imported_rows": len(rows),
        "sampling": f"First {len(rows)} source rows in publisher order; not a representative sample",
        "unit": "listed security; companies may have multiple share classes",
        "synthetic_fields": "review_state is local demo workflow state, initialized to unreviewed; not publisher data",
        "derived_tables": "sector_counts is calculated from the imported sample",
        "database_relative_path": database.relative_to(ROOT / "data").as_posix() if database.is_relative_to(ROOT / "data") else str(database),
        "training": "No model training or evaluation is performed by this importer",
    }
    (destination / "provenance.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def connect_snapshot(manifest, session, backend):
    def api(path, body=None):
        response = session.request("GET" if body is None else "POST", backend + "/api/runtime" + path, json=body, timeout=45)
        if not response.ok:
            raise RuntimeError(f"Backend registration failed: HTTP {response.status_code} at {path}")
        return response.json()
    name = ("Synthetic company demo " if manifest.get("dataset_kind") == "synthetic" else "Open company demo ") + manifest["sha256"][:8] + " " + Path(manifest["database_relative_path"]).parent.name[-8:]
    source = api("/sources", {"name": name, "domain": "CRM", "kind": "sqlite", "relative_path": manifest["database_relative_path"], "allowed_tables": ["companies", "sector_counts"], "provenance": manifest})
    grants = {
        "companies": {"key_field": "symbol", "bindings": {"name": "company_name", "address": "headquarters"}, "writable_fields": ["review_state"]},
        "sector_counts": {"key_field": "sector", "bindings": {}, "writable_fields": []},
    }
    return api(f"/sources/{source['id']}/approve", {"schema_sha256": source["schema_sha256"], "resources": grants})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--connect", action="store_true", help="Register this new local-only demo source; only review_state is writable")
    parser.add_argument("--backend", choices=["http://127.0.0.1:8000", "http://localhost:8000"], default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(CSV_URL, timeout=(10, 30)); response.raise_for_status()
        metadata = session.get(PACKAGE_URL, timeout=(10, 30)); metadata.raise_for_status()
        snapshot = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        destination = ROOT / "data" / "open_company_demo" / snapshot
        manifest = build_snapshot(response.content, metadata.json(), destination, args.limit)
        print(json.dumps({"snapshot": str(destination), **manifest}, indent=2, ensure_ascii=False))
        if args.connect:
            # Use only the local development account or explicitly supplied demo credentials.
            login = session.post(args.backend + "/api/auth/login", data={"username": os.getenv("AVENTRA_DEMO_USERNAME", "admin"), "password": os.getenv("AVENTRA_DEMO_PASSWORD", "Password123!")}, timeout=10)
            if not login.ok:
                raise RuntimeError("Local login failed; set AVENTRA_DEMO_USERNAME/PASSWORD. Snapshot remains available.")
            session.headers["Authorization"] = "Bearer " + login.json()["access_token"]
            source = connect_snapshot(manifest, session, args.backend)
            (destination / "connection.json").write_text(json.dumps({"source_id": source["id"], "name": source["name"]}, indent=2), encoding="utf-8")
            print(json.dumps({"connected_source": source["id"], "status": source["status"]}))


if __name__ == "__main__":
    main()
