import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.session import get_db, SessionLocal
from backend.database.models import WorkflowDefinition, WorkflowExecution, User
from backend.workflows.engine import WorkflowExecutionEngine, subscribe_execution_events
from backend.security.auth import get_current_user

router = APIRouter(prefix="/api/workflows", tags=["Workflows"])


class ExecuteWorkflowRequest(BaseModel):
    workflow_id: str
    input_data: Dict[str, Any] = {}


@router.get("")
def list_workflows(db: Session = Depends(get_db)):
    wfs = db.query(WorkflowDefinition).all()
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "trigger_type": w.trigger_type,
            "nodes": w.nodes,
            "edges": w.edges,
            "status": w.status,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None
        }
        for w in wfs
    ]


@router.get("/executions")
def list_executions(limit: int = 50, db: Session = Depends(get_db)):
    execs = db.query(WorkflowExecution).order_by(WorkflowExecution.started_at.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "workflow_id": e.workflow_id,
            "triggered_by": e.triggered_by,
            "status": e.status,
            "current_step": e.current_step,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            "duration_ms": e.duration_ms,
            "events_count": len(e.execution_events or [])
        }
        for e in execs
    ]


@router.get("/executions/{execution_id}")
def get_execution_details(execution_id: str, db: Session = Depends(get_db)):
    e = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")

    return {
        "id": e.id,
        "workflow_id": e.workflow_id,
        "triggered_by": e.triggered_by,
        "status": e.status,
        "current_step": e.current_step,
        "input_data": e.input_data,
        "output_data": e.output_data,
        "execution_events": e.execution_events or [],
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "duration_ms": e.duration_ms,
        "error_details": e.error_details
    }


def _background_run(execution_id: str):
    db = SessionLocal()
    try:
        engine = WorkflowExecutionEngine(db)
        engine.run_customer_onboarding(execution_id)
    finally:
        db.close()


@router.post("/execute")
def execute_workflow(
    req: ExecuteWorkflowRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    engine = WorkflowExecutionEngine(db)
    execution = engine.create_execution(
        workflow_id=req.workflow_id,
        triggered_by="operator",
        input_data=req.input_data
    )

    # Launch execution in background task so UI immediately opens SSE stream
    background_tasks.add_task(_background_run, execution.id)

    return {
        "execution_id": execution.id,
        "workflow_id": execution.workflow_id,
        "status": "RUNNING",
        "stream_url": f"/api/workflows/{execution.id}/stream"
    }


@router.get("/{execution_id}/stream")
async def stream_execution_events(execution_id: str):
    """
    Real-time Server-Sent Events (SSE) telemetry feed.
    Emits live step timings, model outputs, and terminal messages.
    """
    async def event_generator():
        async for evt in subscribe_execution_events(execution_id):
            yield f"data: {json.dumps(evt)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

