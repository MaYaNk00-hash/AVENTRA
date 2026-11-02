from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class PlanRequestInput(BaseModel):
    intent_type: str
    action_type: str = "READ"
    target_systems: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    user_role: str = "OPERATOR"


class PreprocessedPlanRequest(BaseModel):
    raw: PlanRequestInput
    sanitized_intent: str
    is_write: bool


def preprocess_plan_request(data: Dict[str, Any]) -> PreprocessedPlanRequest:
    req = PlanRequestInput(**data)
    return PreprocessedPlanRequest(
        raw=req,
        sanitized_intent=req.intent_type.upper().strip(),
        is_write=req.action_type.upper() == "WRITE"
    )

