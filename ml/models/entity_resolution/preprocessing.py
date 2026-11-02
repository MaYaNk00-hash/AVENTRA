from typing import Dict, Any, List
from pydantic import BaseModel, Field
from ml.models.entity_resolution.features import clean, get_tokens, get_nums


class BusinessRecord(BaseModel):
    entity_id: str
    business_name: str
    business_address: str = ""
    country: str = "GLOBAL"
    source_system: str = "CRM"


class PreprocessedRecord(BaseModel):
    raw: BusinessRecord
    clean_name: str
    clean_address: str
    name_tokens: List[str]
    addr_tokens: List[str]
    addr_nums: List[str]


def preprocess_record(record_dict: Dict[str, Any]) -> PreprocessedRecord:
    rec = BusinessRecord(**record_dict)
    c_name = clean(rec.business_name)
    c_addr = clean(rec.business_address)
    return PreprocessedRecord(
        raw=rec,
        clean_name=c_name,
        clean_address=c_addr,
        name_tokens=list(get_tokens(c_name)),
        addr_tokens=list(get_tokens(c_addr)),
        addr_nums=list(get_nums(c_addr))
    )

