import re
import itertools

LEGAL_SUFFIXES = {
    'inc', 'incorporated', 'corp', 'corporation', 'llc', 'ltd', 'limited',
    'pvt', 'private', 'co', 'company', 'services', 'enterprises', 'associates',
    'group', 'center', 'centre', 'solutions', 'technologies', 'holdings', 'trust',
    'sarl', 'sas', 'sa', 'eurl', 'gmbh', 'llp', 'pllc', 'dba', 'fka',
    'formerly', 'c/o', 'care', 'smt', 'shri', 'sri', 'dr', 'mr', 'mrs',
    'trading', 'as', 'com', 'org', 'net', 'in', 'us', 'fr', 'web', 'online',
    'intl', 'international'
}

ADDR_STOPWORDS = {
    'and', 'the', 'of', 'in', 'at', 'on', 'for', 'to', 'a', 'an', 'by',
    'no', 'near', 'opp', 'opposite', 'behind', 'fl', 'floor', 'block', 'unit',
    'plot', 'road', 'rd', 'street', 'st', 'avenue', 'ave', 'lane', 'ln', 'dr', 'drive',
    'hwy', 'highway', 'pkwy', 'parkway', 'blvd', 'boulevard', 'bldg', 'building',
    'apt', 'apartment', 'suite', 'ste', 'room', 'rm', 'box', 'po', 'null', 'none',
    'c/o', 'beside', 'ground', 'first', 'second', 'third', '1st', '2nd', '3rd', 'floor',
    'city', 'state', 'district', 'dist', 'taluk', 'taluka', 'vill', 'village', 'nagar'
}

SPLIT_RE = re.compile(r'[^a-z0-9]+')
NUM_RE = re.compile(r'\b\d{1,6}\b')

def get_normalized_nums(addr_clean):
    if not addr_clean:
        return []
    raw_nums = NUM_RE.findall(addr_clean)
    norm_nums = [n.lstrip('0') or '0' for n in raw_nums]
    return list(dict.fromkeys(norm_nums))

def get_keys(name_str, addr_str):
    """
    Extract multi-aspect blocking keys from business name and address:
    - Normalizes numeric tokens (strips leading zeros)
    - Prioritizes head AND tail (city/locality) address tokens
    """
    name_clean = name_str.lower() if name_str else ""
    raw_name_tokens = [t for t in SPLIT_RE.split(name_clean) if t]
    clean_name_tokens = [t for t in raw_name_tokens if len(t) > 1 and t not in LEGAL_SUFFIXES]
    
    addr_clean = addr_str.lower() if addr_str else ""
    raw_addr_tokens = [t for t in SPLIT_RE.split(addr_clean) if t]
    clean_addr_tokens = [t for t in raw_addr_tokens if len(t) > 2 and t not in ADDR_STOPWORDS and not t.isdigit()]
    
    addr_nums = get_normalized_nums(addr_clean)
    
    keys = []
    
    # 1. Full name compact representation
    compact = "".join(raw_name_tokens)
    if len(compact) >= 5:
        keys.append(f"fn:{compact[:20]}")
        
    # 2. Significant name token pairs (combinations of up to 5 tokens)
    if len(clean_name_tokens) >= 2:
        for t0, t1 in itertools.combinations(clean_name_tokens[:5], 2):
            s0, s1 = min(t0, t1), max(t0, t1)
            keys.append(f"n2:{s0}_{s1}")
            keys.append(f"p2:{s0[:3]}_{s1[:3]}")
    elif len(clean_name_tokens) == 1:
        keys.append(f"n1:{clean_name_tokens[0]}")
        
    # 3. First 6 chars of compact name
    if len(compact) >= 6:
        keys.append(f"c6:{compact[:6]}")
        
    # 4. First name token + normalized address number
    if clean_name_tokens and addr_nums:
        keys.append(f"tn:{clean_name_tokens[0]}_{addr_nums[0]}")
        if len(addr_nums) > 1:
            keys.append(f"tn:{clean_name_tokens[0]}_{addr_nums[-1]}")
            
    # 5. Prioritize Head tokens + Tail tokens (city/state) for address combinations
    dist_addr = [t for t in clean_addr_tokens if len(t) >= 4]
    if dist_addr:
        head_tokens = dist_addr[:3]
        tail_tokens = dist_addr[-2:]
        selected_addr_tokens = list(dict.fromkeys(head_tokens + tail_tokens))
    else:
        selected_addr_tokens = []
        
    # 6. Address-based blocking keys with normalized numbers
    if addr_nums and selected_addr_tokens:
        for atok in selected_addr_tokens[:4]:
            for num in addr_nums[:2]:
                keys.append(f"an:{atok}_{num}")
                
    # 7. Address token pairs (cross head & tail tokens)
    if len(selected_addr_tokens) >= 2:
        for a0, a1 in itertools.combinations(selected_addr_tokens[:5], 2):
            keys.append(f"a2:{min(a0, a1)}_{max(a0, a1)}")
            
    return list(set(keys))
