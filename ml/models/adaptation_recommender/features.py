from typing import Dict, Any, List
import re
from rapidfuzz import fuzz
from ml.models.adaptation_recommender.preprocessing import DriftInput, SchemaField

SYNONYM_GROUPS = [
    {"company", "organization", "org", "business", "firm", "corp", "vendor", "client", "customer"},
    {"name", "legal_name", "title"},
    {"address", "addr", "location", "loc", "street"},
    {"id", "identifier", "code", "num", "number", "key"},
    {"tax", "vat", "gst", "ein", "tin"},
    {"total", "amount", "sum", "val", "value"},
    {"date", "timestamp", "time"}
]


def compute_semantic_drift_similarity(name1: str, name2: str) -> float:
    tsort = fuzz.token_sort_ratio(name1, name2) / 100.0
    tset = fuzz.token_set_ratio(name1, name2) / 100.0
    base_sim = max(tsort, tset)

    toks1 = set(re.findall(r'[a-zA-Z0-9]+', name1.lower()))
    toks2 = set(re.findall(r'[a-zA-Z0-9]+', name2.lower()))
    
    direct_overlap = len(toks1 & toks2)
    synonym_overlap = 0
    for g in SYNONYM_GROUPS:
        if bool(toks1 & g) and bool(toks2 & g):
            synonym_overlap += 1

    semantic_score = base_sim
    if direct_overlap > 0 or synonym_overlap > 0:
        boost = 0.25 * direct_overlap + 0.35 * synonym_overlap
        semantic_score = min(1.0, base_sim + boost)

    return semantic_score


def analyze_schema_drift(drift_in: DriftInput, similarity_threshold: float = 0.50) -> Dict[str, Any]:
    old_fields = {f.name: f for f in drift_in.old_schema.fields}
    new_fields = {f.name: f for f in drift_in.new_schema.fields}

    added = []
    removed = []
    modified = []
    renamed = []

    # Check for removed or modified
    for name, old_f in old_fields.items():
        if name in new_fields:
            new_f = new_fields[name]
            if old_f.datatype.lower() != new_f.datatype.lower() or old_f.nullable != new_f.nullable:
                modified.append({
                    "field_name": name,
                    "old_datatype": old_f.datatype,
                    "new_datatype": new_f.datatype,
                    "change_type": "TYPE_OR_CONSTRAINT_MODIFIED"
                })
        else:
            removed.append(old_f)

    # Check for added or potential renames
    for name, new_f in new_fields.items():
        if name not in old_fields:
            best_match = None
            best_sim = 0.0
            for rem_f in list(removed):
                sim = compute_semantic_drift_similarity(rem_f.name, new_f.name)
                if sim > best_sim:
                    best_sim = sim
                    best_match = rem_f

            if best_match and best_sim >= similarity_threshold:
                renamed.append({
                    "old_field": best_match.name,
                    "new_field": new_f.name,
                    "similarity": round(best_sim, 3),
                    "confidence": round(best_sim, 3)
                })
                removed.remove(best_match)
            else:
                added.append(new_f)

    # Impact assessment on active workflows
    impacted_workflows = []
    all_changed_field_names = {r["old_field"] for r in renamed} | {r.name for r in removed} | {m["field_name"] for m in modified}
    for wf in drift_in.active_workflows:
        wf_name = wf.get("name", "Unknown Workflow")
        used_fields = set(wf.get("required_fields", []))
        affected = used_fields & all_changed_field_names
        if affected:
            impacted_workflows.append({
                "workflow_name": wf_name,
                "workflow_id": wf.get("id"),
                "affected_fields": list(affected),
                "risk_tier": "HIGH" if len(affected) > 1 else "MEDIUM"
            })

    return {
        "added_fields": [f.model_dump() for f in added],
        "removed_fields": [f.model_dump() for f in removed],
        "modified_fields": modified,
        "renamed_fields": renamed,
        "impacted_workflows": impacted_workflows,
        "has_breaking_changes": bool(removed or modified or impacted_workflows)
    }
