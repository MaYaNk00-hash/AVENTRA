from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from ml.models.semantic_schema_mapper.features import normalize_field_name, build_text_repr


class SourceFieldInput(BaseModel):
    field_name: str
    datatype: str = "string"
    description: str = ""
    sample_values: List[Any] = Field(default_factory=list)
    is_primary_key: bool = False
    is_foreign_key: bool = False


class PreprocessedField(BaseModel):
    raw: SourceFieldInput
    normalized_name: str
    combined_text: str


def preprocess_source_field(data: Dict[str, Any]) -> PreprocessedField:
    field = SourceFieldInput(**data)
    norm_name = normalize_field_name(field.field_name)
    combined = build_text_repr(field.field_name, field.description, field.sample_values)
    return PreprocessedField(raw=field, normalized_name=norm_name, combined_text=combined)

