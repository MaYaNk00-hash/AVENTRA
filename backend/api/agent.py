from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.agents.agent import EnterpriseAIAgent

router = APIRouter(prefix="/api/agent", tags=["AI Agent Workspace"])


class AgentTaskRequest(BaseModel):
    prompt: str = Field(..., min_length=2)
    user_name: Optional[str] = "Marcus Thorne (Operator)"


@router.post("/execute")
def submit_agent_task(req: AgentTaskRequest, db: Session = Depends(get_db)):
    agent = EnterpriseAIAgent(db)
    result = agent.process_task(req.prompt, user_name=req.user_name)
    return result

