import re
from typing import List, Set
from rapidfuzz import fuzz, distance

SPLIT_RE = re.compile(r'[^a-z0-9]+')
NUM_RE = re.compile(r'\b\d{1,6}\b')


def clean(s: str) -> str:
    return " ".join(SPLIT_RE.split(s.lower())).strip() if s else ""


def get_tokens(s: str) -> Set[str]:
    return set(SPLIT_RE.split(s.lower())) - {""} if s else set()


def get_nums(s: str) -> Set[str]:
    if not s:
        return set()
    raw = NUM_RE.findall(s.lower())
    return {n.lstrip('0') or '0' for n in raw}


def extract_features(s1_cn: str, s1_ca: str, s1_tn: Set[str], s1_ta: Set[str], s1_na: Set[str],
                     c_cn: str, c_ca: str, c_tn: Set[str], c_ta: Set[str], c_na: Set[str], is_s2: bool = True) -> List[float]:
    """
    Extract exact 16-dimensional feature vector matching the trained LightGBM ER model.
    """
    name_ratio = fuzz.ratio(s1_cn, c_cn) / 100.0
    name_tsort = fuzz.token_sort_ratio(s1_cn, c_cn) / 100.0
    name_tset = fuzz.token_set_ratio(s1_cn, c_cn) / 100.0
    name_jw = distance.JaroWinkler.similarity(s1_cn, c_cn)
    
    name_jaccard = len(s1_tn & c_tn) / max(1, len(s1_tn | c_tn)) if (s1_tn or c_tn) else 0.0
    name_len_diff = abs(len(s1_cn) - len(c_cn)) / max(1, max(len(s1_cn), len(c_cn)))
    
    addr_null = 1.0 if not c_ca or not s1_ca else 0.0
    if addr_null:
        addr_tsort = 0.5
        addr_tset = 0.5
        addr_jw = 0.5
        addr_jaccard = 0.5
        num_match = 0.5
    else:
        addr_tsort = fuzz.token_sort_ratio(s1_ca, c_ca) / 100.0
        addr_tset = fuzz.token_set_ratio(s1_ca, c_ca) / 100.0
        addr_jw = distance.JaroWinkler.similarity(s1_ca, c_ca)
        addr_jaccard = len(s1_ta & c_ta) / max(1, len(s1_ta | c_ta)) if (s1_ta or c_ta) else 0.0
        
        if s1_na and c_na:
            num_match = len(s1_na & c_na) / max(1, len(s1_na | c_na))
        elif not s1_na and not c_na:
            num_match = 0.5
        else:
            num_match = 0.0
            
    tot_s1 = s1_tn | s1_ta
    tot_c = c_tn | c_ta
    total_jaccard = len(tot_s1 & tot_c) / max(1, len(tot_s1 | tot_c)) if (tot_s1 or tot_c) else 0.0
    
    return [
        name_ratio, name_tsort, name_tset, name_jw, name_jaccard, name_len_diff,
        addr_null, addr_tsort, addr_tset, addr_jw, addr_jaccard, num_match,
        1.0 if is_s2 else 0.0, total_jaccard,
        name_tset * addr_tset,
        name_jw * addr_jw
    ]

