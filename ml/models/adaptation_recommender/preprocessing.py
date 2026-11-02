from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class SchemaField(BaseModel):
    name: str
    datatype: str
    description: str = ""
    nullable: bool = True


class SchemaDefinition(BaseModel):
    system_name: str
    version: str
    fields: List[SchemaField]


class DriftInput(BaseModel):
    old_schema: SchemaDefinition
    new_schema: SchemaDefinition
    active_workflows: List[Dict[str, Any]] = Field(default_factory=list)

