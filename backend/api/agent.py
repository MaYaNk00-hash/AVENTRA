from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.agents.agent import EnterpriseAIAgent
from backend.security.auth import get_current_user
from backend.database.models import User

router = APIRouter(prefix="/api/agent", tags=["AI Agent Workspace"])


class AgentTaskRequest(BaseModel):
    prompt: str = Field(..., min_length=2)
    user_name: Optional[str] = "Marcus Thorne (Operator)"


@router.post("/execute")
def submit_agent_task(req: AgentTaskRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = EnterpriseAIAgent(db)
    result = agent.process_task(req.prompt, user_name=user.full_name or req.user_name)
    return result

