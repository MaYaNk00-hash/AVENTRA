from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class IntentInput(BaseModel):
    prompt: str = Field(..., min_length=2)
    user_id: Optional[str] = "user_default"
    user_roles: list[str] = Field(default_factory=lambda: ["OPERATOR"])
    session_id: Optional[str] = None


class PreprocessedIntentInput(BaseModel):
    raw_prompt: str
    cleaned_prompt: str
    user_roles: list[str]


def preprocess_intent_input(data: Dict[str, Any]) -> PreprocessedIntentInput:
    req = IntentInput(**data)
    cleaned = req.prompt.strip()
    return PreprocessedIntentInput(
        raw_prompt=req.prompt,
        cleaned_prompt=cleaned,
        user_roles=req.user_roles
    )

