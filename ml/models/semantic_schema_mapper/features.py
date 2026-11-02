import re
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from rapidfuzz import fuzz

NORMALIZE_RE = re.compile(r'[^a-zA-Z0-9]+')


def normalize_field_name(name: str) -> str:
    parts = re.findall(r'[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z0-9]|\b)', name)
    if not parts:
        parts = NORMALIZE_RE.split(name.lower())
    return " ".join([p.lower() for p in parts if p]).strip()


def check_type_compatibility(source_type: str, allowed_types: List[str]) -> bool:
    src = source_type.lower().strip()
    for t in allowed_types:
        if t in src or src in t:
            return True
    return False


def build_text_repr(field_name: str, description: str, sample_values: List[Any]) -> str:
    norm_name = normalize_field_name(field_name)
    samples_str = " ".join([str(s) for s in sample_values[:3]])
    return f"{norm_name} {description} {samples_str}".strip()

