"""
Architectural Service Interfaces for AVENTRA Enterprise Platform.
Establishes formal decoupling between Workflow Engine, Model Registry,
Enterprise Memory, Approval Governance, and Audit Ledger services.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


# ==========================================
# 1. MODEL REGISTRY SERVICE INTERFACE
# ==========================================

class IModelRegistryService(ABC):
    @abstractmethod
    def get_model(self, model_identifier: str) -> Any:
        """Retrieves and initializes a model by identifier."""
        pass

    @abstractmethod
    def list_registered_models(self) -> List[Dict[str, Any]]:
        """Lists metadata, task capabilities, and metrics for all registered models."""
        pass

    @abstractmethod
    def health_check_all(self) -> Dict[str, Any]:
        """Runs validation checks across all registered ML artifacts."""
        pass


# ==========================================
# 2. ENTERPRISE MEMORY SERVICE INTERFACE
# ==========================================

class IEnterpriseMemoryService(ABC):
    @abstractmethod
    def store_schema_mapping(self, source_system: str, field_name: str, canonical_concept: str, confidence: float, approved_by: Optional[str] = None) -> bool:
        """Persists an aligned schema mapping as versioned enterprise knowledge."""
        pass

    @abstractmethod
    def lookup_canonical_mapping(self, source_system: str, field_name: str) -> Optional[str]:
        """Retrieves verified canonical mapping for a source system field."""
        pass

    @abstractmethod
    def record_human_correction(self, task_type: str, original_prediction: Dict[str, Any], corrected_value: Dict[str, Any], reviewer_id: str) -> str:
        """Stores human review feedback to drive continuous learning without model drift."""
        pass

    @abstractmethod
    def get_audit_trail(self, entity_id: str) -> List[Dict[str, Any]]:
        """Retrieves all memory operations and human corrections associated with an entity."""
        pass


# ==========================================
# 3. WORKFLOW ENGINE SERVICE INTERFACE
# ==========================================

class IWorkflowEngineService(ABC):
    @abstractmethod
    def create_execution(self, workflow_id: str, triggered_by: str, input_data: Dict[str, Any]) -> str:
        """Instantiates a new workflow execution with status INITIALIZED."""
        pass

    @abstractmethod
    def execute_dag_step(self, execution_id: str, step_id: str, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes an individual tool or ML step within an authorized DAG."""
        pass

    @abstractmethod
    def pause_at_gate(self, execution_id: str, step_id: str, approval_id: str) -> None:
        """Transitions execution to AWAITING_APPROVAL and creates cryptographic review ticket."""
        pass

    @abstractmethod
    def resume_after_approval(self, approval_id: str, approved_by: str, user_role: str, decision: str, comments: str) -> Dict[str, Any]:
        """Resumes paused workflow upon cryptographic signature authorization."""
        pass


# ==========================================
# 4. APPROVAL GOVERNANCE SERVICE INTERFACE
# ==========================================

class IApprovalGovernanceService(ABC):
    @abstractmethod
    def request_approval(self, execution_id: str, step_id: str, action_type: str, risk_level: str, confidence_score: float, evidence: Dict[str, Any]) -> str:
        """Issues a new approval ticket with unique cryptographic nonce."""
        pass

    @abstractmethod
    def review_ticket(self, approval_id: str, decision: str, reviewer_name: str, reviewer_role: str, comments: str, nonce: Optional[str] = None) -> Dict[str, Any]:
        """Records reviewer authorization and validates RBAC entitlement."""
        pass


# ==========================================
# 5. AUDIT LEDGER SERVICE INTERFACE
# ==========================================

class IAuditLedgerService(ABC):
    @abstractmethod
    def record_event(self, event_type: str, actor: str, payload: Dict[str, Any], execution_id: Optional[str] = None) -> str:
        """Appends a new SHA-256 chained block to the tamper-evident ledger."""
        pass

    @abstractmethod
    def verify_ledger_integrity(self) -> Dict[str, Any]:
        """Cryptographically validates full ledger chain from genesis block to tip."""
        pass

