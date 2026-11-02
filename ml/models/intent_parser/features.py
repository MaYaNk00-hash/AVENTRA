import re
from typing import Dict, Any, List

INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"ignore all rules",
    r"bypass approval",
    r"disable auth",
    r"drop table",
    r"force write without approval",
    r"grant admin",
    r"sudo\b",
    r"rm -rf"
]


def detect_prompt_injection(prompt: str) -> bool:
    lower_prompt = prompt.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lower_prompt):
            return True
    return False


def extract_keywords_and_entities(prompt: str) -> Dict[str, Any]:
    lower = prompt.lower()
    
    # Check for onboarding / duplicate keywords
    onboard_score = sum(1 for w in ["onboard", "create customer", "new vendor", "add supplier", "register business"] if w in lower)
    duplicate_score = sum(1 for w in ["duplicate", "resolve", "merge", "match", "entity resolution", "deduplicate"] if w in lower)
    invoice_score = sum(1 for w in ["invoice", "reconcile", "po", "purchase order", "3-way match", "payment"] if w in lower)
    schema_score = sum(1 for w in ["schema", "mapping", "drift", "field", "column", "datatype"] if w in lower)
    anomaly_score = sum(1 for w in ["anomaly", "fraud", "unusual", "suspicious", "outlier"] if w in lower)
    audit_score = sum(1 for w in ["audit", "ledger", "tamper", "hash chain", "compliance", "history"] if w in lower)
    
    scores = {
        "ONBOARD_CUSTOMER": onboard_score * 2 + (1 if "customer" in lower else 0),
        "RESOLVE_DUPLICATES": duplicate_score * 2,
        "RECONCILE_INVOICE": invoice_score * 2,
        "MAP_SCHEMA": schema_score * 2,
        "DETECT_ANOMALIES": anomaly_score * 2,
        "AUDIT_INSPECTION": audit_score * 2
    }
    
    # Action type detection (Read vs Write)
    write_indicators = ["create", "add", "insert", "update", "merge", "modify", "delete", "sync", "link", "approve", "execute", "onboard"]
    is_write = any(w in lower for w in write_indicators)

    return {
        "intent_scores": scores,
        "is_write": is_write,
        "has_injection": detect_prompt_injection(prompt)
    }

