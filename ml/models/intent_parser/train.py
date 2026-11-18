"""
Training pipeline for AVENTRA Intent Parser model.
Generates an open-source style enterprise prompt intent dataset of at most 6,000 instructions across
all 7 enterprise intents, trains a TF-IDF + Logistic Regression classification model, and saves the artifact.
"""

import os
import sys
import pickle
import random
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

INTENT_TEMPLATES = {
    "ONBOARD_CUSTOMER": [
        "Onboard new enterprise customer {org} and initialize CRM profile.",
        "Add new corporate client {org} into sales accounts and create billing record.",
        "Register {org} as a new enterprise partner in our client portal.",
        "Create customer account for {org} with default payment terms.",
        "New account creation request for {org} across regional subsidiaries.",
        "Onboard supplier {org} with vendor master data and banking details.",
        "Provision new customer entity {org} into customer database.",
        "Ingest newly signed contract customer {org} into our enterprise ledger.",
        "Initiate onboarding workflow for corporate account {org}."
    ],
    "RESOLVE_DUPLICATES": [
        "Resolve duplicate accounts between CRM and ERP for {org}.",
        "Deduplicate customer records and match entity profiles for {org}.",
        "Identify and merge conflicting customer entities for {org} in the database.",
        "Scan enterprise database for potential duplicate records of {org}.",
        "Run LightGBM entity resolution to identify duplicates for {org}.",
        "Find duplicate vendor registrations matching {org} in SAP database.",
        "Resolve entity conflicts and establish golden record for {org}.",
        "Deduplicate ERP supplier list against Salesforce customer catalog."
    ],
    "RECONCILE_INVOICE": [
        "Reconcile invoice {inv} against purchase order {po} and goods receipt.",
        "Execute 3-way matching for vendor invoice {inv} with PO {po}.",
        "Perform line item invoice reconciliation on bill {inv} for {org}.",
        "Check variance between received goods and billed line items on invoice {inv}.",
        "Reconcile payment voucher {inv} against ERP procurement contract {po}.",
        "Verify price tolerances and tax calculation for invoice {inv}.",
        "Match incoming supplier invoice {inv} with PO {po} quantities.",
        "Audit invoice {inv} totals against warehouse delivery receipt."
    ],
    "MAP_SCHEMA": [
        "Map source CRM schema fields to canonical enterprise concepts.",
        "Align incoming Salesforce table definitions with standard data model.",
        "Detect schema drift and map modified ERP columns to canonical schema.",
        "Reconcile schema mappings for customer table after v2.0 API migration.",
        "Map NetSuite custom fields into canonical enterprise data dictionary.",
        "Generate semantic schema alignment recommendations for billing table.",
        "Update schema mapping definitions to resolve unrecognized column names."
    ],
    "DETECT_ANOMALIES": [
        "Scan payment transactions for unusual amounts or fraud anomalies.",
        "Detect transaction anomalies in recent vendor disbursement disbursements.",
        "Evaluate anomaly risk score for high-value transaction {tx}.",
        "Analyze vendor payment behavior for statistical outliers and spikes.",
        "Flag suspicious disbursements to newly registered accounts.",
        "Run Isolation Forest behavioral anomaly detection on last 24h transactions.",
        "Detect outlier purchase orders exceeding historical vendor average."
    ],
    "AUDIT_INSPECTION": [
        "Inspect tamper-evident audit ledger and verify cryptographic hashes.",
        "Audit recent administrative operations and user approval history.",
        "Verify blockchain audit trail integrity for compliance inspection.",
        "Retrieve audit log entries for customer onboarding transactions.",
        "Run compliance audit check on authorized database commits.",
        "Inspect event log history and verify digital signature chain.",
        "Generate regulatory audit report for enterprise data changes."
    ],
    "SYSTEM_HEALTH_CHECK": [
        "Check system health status and connector latency.",
        "Ping external CRM and ERP endpoints to verify live connectivity.",
        "Run diagnostic health check on all enterprise database adapters.",
        "Verify operational status of ML inference services and API bridges.",
        "Test connection pools and database query response times.",
        "Inspect system uptime, memory usage, and background worker queues."
    ]
}

SAMPLE_ORGS = ["Acme Industrial", "Globex Corp", "Initech LLC", "Umbrella Global", "Soylent Corp", "Hooli Tech", "Wayne Enterprises", "Stark Industries", "Cyberdyne Systems", "Massive Dynamic", "Pied Piper"]
SAMPLE_INVS = ["INV-2026-101", "INV-8820", "BILL-9011", "VOUCH-331", "INV-4402", "INVOICE-773"]
SAMPLE_POS = ["PO-7712", "PO-9912", "PO-3341", "PO-1029", "PO-5540"]
SAMPLE_TXS = ["TX-9901", "TX-1044", "TX-8821", "TX-3021"]

ACTION_MAP = {
    "ONBOARD_CUSTOMER": "WRITE",
    "RESOLVE_DUPLICATES": "WRITE",
    "RECONCILE_INVOICE": "WRITE",
    "MAP_SCHEMA": "WRITE",
    "DETECT_ANOMALIES": "READ",
    "AUDIT_INSPECTION": "READ",
    "SYSTEM_HEALTH_CHECK": "READ"
}


def generate_intent_dataset(output_parquet: str = "ml/models/intent_parser/data/intents_6k.parquet",
                            output_json: str = "ml/models/intent_parser/data/intents_6k.json",
                            max_samples: int = 6000) -> pl.DataFrame:
    random.seed(42)
    records = []
    intents = list(INTENT_TEMPLATES.keys())

    for i in range(max_samples):
        intent = intents[i % len(intents)]
        template = random.choice(INTENT_TEMPLATES[intent])
        
        prompt = template.format(
            org=random.choice(SAMPLE_ORGS),
            inv=random.choice(SAMPLE_INVS),
            po=random.choice(SAMPLE_POS),
            tx=random.choice(SAMPLE_TXS)
        )

        # Add variations (casing, prefix, polite words)
        prefixes = ["", "Please ", "Kindly ", "Could you ", "System request: ", "Execute: ", "Run "]
        prompt = f"{random.choice(prefixes)}{prompt}"

        records.append({
            "id": f"REQ-{i:05d}",
            "prompt": prompt,
            "intent_type": intent,
            "action_type": ACTION_MAP[intent],
            "requires_authorization": ACTION_MAP[intent] == "WRITE"
        })

    df = pl.DataFrame(records)
    os.makedirs(os.path.dirname(output_parquet), exist_ok=True)
    df.write_parquet(output_parquet)
    
    import json
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"Generated intent dataset: {len(df)} records saved to {output_parquet} & {output_json}")
    return df


def train_model(data_path: str = "ml/models/intent_parser/data/intents_6k.parquet",
                output_path: str = "ml/models/intent_parser/artifacts/intent_model.pkl"):
    print("Training Intent Parser TF-IDF + Logistic Regression model on 6k prompts...")
    if not os.path.exists(data_path):
        df = generate_intent_dataset(data_path)
    else:
        df = pl.read_parquet(data_path)

    X_texts = df["prompt"].to_list()
    y_intents = df["intent_type"].to_list()

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=3000, lowercase=True)
    X_vec = vectorizer.fit_transform(X_texts)

    classifier = LogisticRegression(C=2.0, max_iter=200, random_state=42)
    classifier.fit(X_vec, y_intents)

    bundle = {
        "vectorizer": vectorizer,
        "classifier": classifier,
        "classes": list(classifier.classes_)
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(bundle, f)
    print(f"Artifact saved to {output_path} (trained on {len(df)} samples)")
    return bundle


if __name__ == "__main__":
    train_model()

