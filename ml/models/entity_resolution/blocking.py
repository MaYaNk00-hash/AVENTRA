from collections import defaultdict
from typing import List, Dict, Any, Set
import re
from ml.models.entity_resolution.features import clean, get_tokens, get_nums

SPLIT_RE = re.compile(r'[^a-z0-9]+')
ADDR_STOPWORDS = {
    'and', 'the', 'of', 'in', 'at', 'on', 'for', 'to', 'a', 'an', 'by',
    'road', 'rd', 'street', 'st', 'avenue', 'ave', 'lane', 'ln', 'dr', 'drive',
    'bldg', 'building', 'apt', 'apartment', 'suite', 'ste', 'room', 'rm', 'box', 'po'
}


class MultiKeyBlocker:
    """
    Candidate generation engine using token-prefix and distinctive address blocking.
    """
    def __init__(self, max_bucket_size: int = 150):
        self.max_bucket_size = max_bucket_size
        self.index: Dict[str, Set[str]] = defaultdict(set)
        self.records: Dict[str, Dict[str, Any]] = {}

    def build_index(self, records: List[Dict[str, Any]]):
        self.index.clear()
        self.records.clear()
        
        for r in records:
            rid = str(r["entity_id"])
            self.records[rid] = r
            name_clean = clean(r.get("business_name", ""))
            addr_clean = clean(r.get("business_address", ""))
            
            # Blocking Key 1: First 3 letters of first name token
            tokens = get_tokens(name_clean)
            for t in tokens:
                if len(t) >= 3:
                    self.index[f"n3_{t[:3]}"].add(rid)
            
            # Blocking Key 2: Address numbers
            nums = get_nums(addr_clean)
            for n in nums:
                self.index[f"num_{n}"].add(rid)
                
            # Blocking Key 3: Distinctive address tokens
            for at in get_tokens(addr_clean):
                if len(at) >= 4 and at not in ADDR_STOPWORDS:
                    self.index[f"addr_{at}"].add(rid)

    def retrieve_candidates(self, query_record: Dict[str, Any], top_k: int = 25) -> List[str]:
        q_name = clean(query_record.get("business_name", ""))
        q_addr = clean(query_record.get("business_address", ""))
        
        candidate_counts = defaultdict(int)
        
        # Check name tokens
        for t in get_tokens(q_name):
            if len(t) >= 3:
                key = f"n3_{t[:3]}"
                bucket = self.index.get(key, set())
                if len(bucket) <= self.max_bucket_size:
                    for cid in bucket:
                        candidate_counts[cid] += 2
                        
        # Check nums
        for n in get_nums(q_addr):
            key = f"num_{n}"
            bucket = self.index.get(key, set())
            if len(bucket) <= self.max_bucket_size:
                for cid in bucket:
                    candidate_counts[cid] += 3

        # Check addr tokens
        for at in get_tokens(q_addr):
            if len(at) >= 4 and at not in ADDR_STOPWORDS:
                key = f"addr_{at}"
                bucket = self.index.get(key, set())
                if len(bucket) <= self.max_bucket_size:
                    for cid in bucket:
                        candidate_counts[cid] += 1
                        
        sorted_cands = sorted(candidate_counts.items(), key=lambda x: x[1], reverse=True)
        return [cid for cid, _ in sorted_cands[:top_k]]

