"""
Base Model Interface and Schema Contracts for AVENTRA Modular ML Platform.
All ML models must implement this standard contract to ensure composability,
deterministic execution, and audit-ready outputs.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel as PydanticBaseModel, Field
import time


class ModelExecutionStatus:
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class BaseModelOutput(PydanticBaseModel):
    """
    Standard output contract for all AVENTRA ML models.
    """
    model_identifier: str = Field(..., description="Unique model identifier, e.g. 'entity_resolution'")
    model_version: str = Field(..., description="Semantic version of the model, e.g. '1.0.0'")
    prediction: Any = Field(..., description="Primary prediction payload or structured output")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Calibrated confidence score if applicable")
    supporting_evidence: Dict[str, Any] = Field(default_factory=dict, description="Explainability, feature contributions or matched tokens")
    execution_status: str = Field(default=ModelExecutionStatus.SUCCESS, description="Execution outcome status")
    error_details: Optional[str] = Field(None, description="Detailed error description if execution failed")
    processing_metadata: Dict[str, Any] = Field(default_factory=dict, description="Latency, hardware, timestamp metadata")

    model_config = {"arbitrary_types_allowed": True}


class BaseModel(ABC):
    """
    Abstract Base Model interface that every independent AVENTRA model must implement.
    """
    model_identifier: str = "base_model"
    model_version: str = "1.0.0"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.is_loaded = False

    @abstractmethod
    def load(self) -> None:
        """Load model weights, scalers, and artifacts from disk."""
        raise NotImplementedError

    @abstractmethod
    def preprocess(self, data: Any) -> Any:
        """Validate input types, normalize strings/features, and apply tokenization."""
        raise NotImplementedError

    @abstractmethod
    def predict(self, data: Any) -> BaseModelOutput:
        """Run inference and return a structured BaseModelOutput object."""
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, data: Any) -> Dict[str, float]:
        """Compute evaluation metrics (precision, recall, F1, accuracy, etc.) on test/holdout data."""
        raise NotImplementedError

    def health_check(self) -> Dict[str, Any]:
        """Perform a quick diagnostic verification of the model."""
        return {
            "model_identifier": self.model_identifier,
            "model_version": self.model_version,
            "is_loaded": self.is_loaded,
            "status": "HEALTHY" if self.is_loaded else "NOT_LOADED"
        }
