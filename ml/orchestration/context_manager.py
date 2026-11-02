"""
Workflow Scoped Context Manager for AVENTRA.
Manages secure cross-model data transfer, provenance tracking, and state isolation.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import time
import uuid


class WorkflowExecutionEvent(BaseModel):
    timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    step_id: str
    component: str
    event_type: str  # "START", "COMPLETED", "APPROVAL_REQUESTED", "ERROR"
    message: str
    duration_ms: Optional[float] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class WorkflowContext(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    organization_id: str = "DEFAULT-CORP"
    authorized_user: str = "system_operator"
    user_role: str = "OPERATIONS_APPROVER"
    current_state: str = "INITIALIZED"
    
    # Scoped dataset and record references
    input_datasets: Dict[str, Any] = Field(default_factory=dict)
    model_outputs: Dict[str, Any] = Field(default_factory=dict)
    model_versions: Dict[str, str] = Field(default_factory=dict)
    validation_results: Dict[str, Any] = Field(default_factory=dict)
    
    # Governance & Approval
    approval_required: bool = False
    approval_state: str = "NONE"  # "NONE", "PENDING", "APPROVED", "REJECTED"
    approval_evidence: Dict[str, Any] = Field(default_factory=dict)
    approval_token_nonce: Optional[str] = None
    
    # Audit log
    execution_history: List[WorkflowExecutionEvent] = Field(default_factory=list)

    def log_event(self, step_id: str, component: str, event_type: str, message: str, duration_ms: Optional[float] = None, payload: Optional[Dict[str, Any]] = None):
        event = WorkflowExecutionEvent(
            step_id=step_id,
            component=component,
            event_type=event_type,
            message=message,
            duration_ms=duration_ms,
            payload=payload or {}
        )
        self.execution_history.append(event)
        return event

    def record_model_output(self, model_identifier: str, version: str, output: Any):
        self.model_outputs[model_identifier] = output
        self.model_versions[model_identifier] = version

