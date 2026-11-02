"""
Central Model Registry for AVENTRA Modular Machine Learning Architecture.
Manages versioning, metadata, schemas, and lifecycle of all independent models.
"""

from typing import Dict, Any, Type, Optional, List
import time
from pydantic import BaseModel as PydanticBaseModel
from ml.shared.schemas.base import BaseModel, BaseModelOutput


class ModelMetadata(PydanticBaseModel):
    model_identifier: str
    model_version: str
    display_name: str
    description: str
    task_type: str
    supported_tasks: List[str]
    input_schema: str
    output_schema: str
    artifact_path: str
    metrics: Dict[str, float] = {}
    is_active: bool = True
    last_validated: Optional[str] = None


class ModelRegistry:
    _instance = None
    _models: Dict[str, Type[BaseModel]] = {}
    _loaded_instances: Dict[str, BaseModel] = {}
    _metadata: Dict[str, ModelMetadata] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelRegistry, cls).__new__(cls)
            cls._models = {}
            cls._loaded_instances = {}
            cls._metadata = {}
        return cls._instance

    @classmethod
    def register(cls, model_identifier: str, model_cls: Type[BaseModel], metadata: ModelMetadata):
        cls._models[model_identifier] = model_cls
        cls._metadata[model_identifier] = metadata

    @classmethod
    def get_model(cls, model_identifier: str, auto_load: bool = True) -> BaseModel:
        if model_identifier not in cls._models:
            raise KeyError(f"Model '{model_identifier}' is not registered in Model Registry.")
        
        if model_identifier not in cls._loaded_instances:
            instance = cls._models[model_identifier]()
            if auto_load:
                instance.load()
            cls._loaded_instances[model_identifier] = instance
            
        return cls._loaded_instances[model_identifier]

    @classmethod
    def list_models(cls) -> List[Dict[str, Any]]:
        result = []
        for mid, meta in cls._metadata.items():
            loaded = mid in cls._loaded_instances and cls._loaded_instances[mid].is_loaded
            result.append({
                "model_identifier": meta.model_identifier,
                "model_version": meta.model_version,
                "display_name": meta.display_name,
                "description": meta.description,
                "task_type": meta.task_type,
                "supported_tasks": meta.supported_tasks,
                "metrics": meta.metrics,
                "is_active": meta.is_active,
                "is_loaded": loaded,
                "last_validated": meta.last_validated
            })
        return result

    @classmethod
    def update_metrics(cls, model_identifier: str, metrics: Dict[str, float]):
        if model_identifier in cls._metadata:
            cls._metadata[model_identifier].metrics.update(metrics)
            cls._metadata[model_identifier].last_validated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

