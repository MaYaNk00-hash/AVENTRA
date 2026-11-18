"""Generate an isolated, reproducible 5k company demo; never replaces data.

python -m infrastructure.scripts.generate_synthetic_company_demo --connect
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
import random
import sqlite3
import uuid

import requests
from infrastructure.scripts.import_open_company_demo import ROOT, connect_snapshot

FIELDS = ["symbol", "company_name", "sector", "headquarters", "sub_industry", "review_state"]
SECTORS = {
    "Information Technology": ["Software", "IT Services", "Semiconductors"],
    "Industrials": ["Machinery", "Logistics", "Building Products"],
    "Financials": ["Insurance", "Banking", "Financial Services"],
    "Health Care": ["Medical Devices", "Health Services", "Biotechnology"],
    "Consumer Discretionary": ["Retail", "Leisure Products", "Automotive"],
    "Consumer Staples": ["Food Products", "Household Products", "Food Distribution"],
    "Energy": ["Energy Equipment", "Renewable Fuels", "Oil Services"],
    "Materials": ["Chemicals", "Packaging", "Construction Materials"],
    "Real Estate": ["Property Management", "Industrial Property", "Commercial Property"],
    "Utilities": ["Electric Utilities", "Water Utilities", "Gas Utilities"],
    "Communication Services": ["Telecommunications", "Media", "Interactive Services"],
}


def generate_snapshot(destination, count=5000, seed=42):
    if not 1 <= count <= 10000:
        raise ValueError("Record count must be between 1 and 10000")
    rng = random.Random(seed)
    adjectives = ["Amber", "Cedar", "Silver", "Summit", "Cobalt", "River", "Maple", "Evergreen", "Orchid", "Horizon"]
    nouns = ["Bridge", "Point", "Works", "Systems", "Partners", "Dynamics", "Solutions", "Group", "Ventures", "Labs"]
    cities = ["Gwalior", "Pune", "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Chennai", "Ahmedabad", "Jaipur", "Indore"]
    records = []
    for index in range(1, count + 1):
        sector = rng.choice(list(SECTORS))
        records.append({
            "symbol": f"SYN{index:06d}",
            "company_name": f"Synthetic {rng.choice(adjectives)} {rng.choice(nouns)} {index:05d}",
            "sector": sector,
            "headquarters": f"Fictional District {rng.randint(1, 90)}, {rng.choice(cities)}, India",
            "sub_industry": rng.choice(SECTORS[sector]),
            "review_state": rng.choices(["unreviewed", "queued", "reviewed"], weights=[75, 20, 5])[0],
        })
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader(); writer.writerows(records)
    payload = buffer.getvalue().encode("utf-8")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "companies.csv").write_bytes(payload)
    database = destination / "companies.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE companies (symbol TEXT PRIMARY KEY, company_name TEXT NOT NULL, sector TEXT, headquarters TEXT, sub_industry TEXT, review_state TEXT NOT NULL)")
        db.executemany("INSERT INTO companies VALUES (?,?,?,?,?,?)", [tuple(record[field] for field in FIELDS) for record in records])
        db.execute("CREATE TABLE sector_counts (sector TEXT PRIMARY KEY, security_count INTEGER NOT NULL)")
        db.executemany("INSERT INTO sector_counts VALUES (?,?)", sorted(Counter(record["sector"] for record in records).items()))
    manifest = {
        "title": f"Synthetic company directory — {count:,} fictional records",
        "dataset_kind": "synthetic", "generator_version": "1.0.0", "seed": seed,
        "publisher_url": "", "license": "Locally generated synthetic demonstration data",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "source_rows": count, "imported_rows": count,
        "sampling": "Seeded pseudorandom generation; no sampling of real companies",
        "unit": "fictional company; SYN identifiers are not real stock tickers",
        "synthetic_fields": "All fields are synthetic. City and sector labels are vocabulary only; no real company, address, or review decision is represented.",
        "derived_tables": "sector_counts is calculated from the generated company rows; security_count retains the existing demo schema",
        "database_relative_path": database.relative_to(ROOT / "data").as_posix() if database.is_relative_to(ROOT / "data") else str(database),
        "training": "No model training, predictions, or evaluation results are generated",
    }
    (destination / "provenance.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--connect", action="store_true")
    args = parser.parse_args()
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    destination = ROOT / "data" / "synthetic_company_demo" / name
    manifest = generate_snapshot(destination, args.count, args.seed)
    print(json.dumps({"snapshot": str(destination), **manifest}, indent=2, ensure_ascii=False))
    if args.connect:
        with requests.Session() as session:
            session.trust_env = False
            backend = "http://127.0.0.1:8000"
            login = session.post(backend + "/api/auth/login", data={"username": os.getenv("AVENTRA_DEMO_USERNAME", "admin"), "password": os.getenv("AVENTRA_DEMO_PASSWORD", "Password123!")}, timeout=10)
            if not login.ok:
                raise RuntimeError("Local login failed; set AVENTRA_DEMO_USERNAME/PASSWORD. Generated data is preserved.")
            session.headers["Authorization"] = "Bearer " + login.json()["access_token"]
            source = connect_snapshot(manifest, session, backend)
            (destination / "connection.json").write_text(json.dumps({"source_id": source["id"], "name": source["name"]}, indent=2), encoding="utf-8")
            print(json.dumps({"source_id": source["id"], "status": source["status"]}))


if __name__ == "__main__":
    main()
