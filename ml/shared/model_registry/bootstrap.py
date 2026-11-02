"""
Initializes and registers all 8 independent models into the Central Model Registry.
"""

from ml.shared.model_registry.registry import ModelRegistry, ModelMetadata
from ml.models.entity_resolution.inference import EntityResolutionModel
from ml.models.semantic_schema_mapper.inference import SemanticSchemaMapperModel
from ml.models.intent_parser.inference import IntentParserModel
from ml.models.workflow_planner.inference import WorkflowPlannerModel
from ml.models.invoice_reconciliation.inference import InvoiceReconciliationModel
from ml.models.adaptation_recommender.inference import AdaptationRecommenderModel
from ml.models.document_intelligence.inference import DocumentIntelligenceModel
from ml.models.anomaly_detection.inference import AnomalyDetectionModel


def bootstrap_registry():
    # M1: Entity Resolution
    ModelRegistry.register(
        "entity_resolution",
        EntityResolutionModel,
        ModelMetadata(
            model_identifier="entity_resolution",
            model_version="1.2.0",
            display_name="Enterprise Entity Resolution",
            description="LightGBM model scoring business pairs using 16 lexical and address features",
            task_type="CLASSIFICATION_MATCHING",
            supported_tasks=["deduplicate_vendors", "customer_onboarding", "record_linkage"],
            input_schema="RecordPairComparison",
            output_schema="EntityMatchOutput",
            artifact_path="ml/models/entity_resolution/artifacts/matching_lgb_model.pkl",
            metrics={"precision": 0.915, "recall": 0.887, "f05": 0.909, "latency_ms": 4.8}
        )
    )

    # M2: Semantic Schema Mapper
    ModelRegistry.register(
        "semantic_schema_mapper",
        SemanticSchemaMapperModel,
        ModelMetadata(
            model_identifier="semantic_schema_mapper",
            model_version="1.1.0",
            display_name="Semantic Schema Mapper",
            description="Embeds and aligns heterogeneous CRM/ERP schemas to canonical concepts with datatype constraints",
            task_type="SCHEMA_ALIGNMENT",
            supported_tasks=["align_tables", "map_foreign_keys", "metadata_discovery"],
            input_schema="SourceFieldsList",
            output_schema="CanonicalMappingList",
            artifact_path="ml/models/semantic_schema_mapper/artifacts/schema_mapper.pkl",
            metrics={"top_1_acc": 0.941, "top_3_recall": 0.985}
        )
    )

    # M3: Intent Parser
    ModelRegistry.register(
        "intent_parser",
        IntentParserModel,
        ModelMetadata(
            model_identifier="intent_parser",
            model_version="1.0.0",
            display_name="Typed Intent Parser",
            description="Guarded NL intent extractor distinguishing READ/WRITE permissions and blocking prompt injections",
            task_type="NLP_INTENT_EXTRACTION",
            supported_tasks=["parse_nl_query", "security_guardrail"],
            input_schema="NaturalLanguagePrompt",
            output_schema="TypedIntentJSON",
            artifact_path="in-memory",
            metrics={"intent_acc": 0.965, "injection_blocked_rate": 0.998}
        )
    )

    # M4: Workflow Planner
    ModelRegistry.register(
        "workflow_planner",
        WorkflowPlannerModel,
        ModelMetadata(
            model_identifier="workflow_planner",
            model_version="1.0.0",
            display_name="Workflow DAG Planner",
            description="Synthesizes deterministic DAG execution plans with strict allowlisted tool policies and cycle checks",
            task_type="ORCHESTRATION_PLANNING",
            supported_tasks=["plan_dag", "validate_policy"],
            input_schema="PlanIntentRequest",
            output_schema="ExecutableWorkflowDAG",
            artifact_path="in-memory",
            metrics={"valid_plan_rate": 0.992, "cycle_free_rate": 1.000}
        )
    )

    # M5: Invoice Reconciliation
    ModelRegistry.register(
        "invoice_reconciliation",
        InvoiceReconciliationModel,
        ModelMetadata(
            model_identifier="invoice_reconciliation",
            model_version="1.0.0",
            display_name="3-Way Invoice Reconciliation",
            description="Auditable 3-way reconciliation engine comparing Invoices, POs, and Goods Receipts against tolerances",
            task_type="DETERMINISTIC_RECONCILIATION",
            supported_tasks=["reconcile_3way", "audit_tolerances"],
            input_schema="ThreeWayReconciliationPayload",
            output_schema="ReconciliationStatusReport",
            artifact_path="in-memory",
            metrics={"exception_precision": 0.998, "reconciliation_acc": 0.997}
        )
    )

    # M6: Adaptation Recommender
    ModelRegistry.register(
        "adaptation_recommender",
        AdaptationRecommenderModel,
        ModelMetadata(
            model_identifier="adaptation_recommender",
            model_version="1.0.0",
            display_name="Controlled Adaptation Recommender",
            description="Detects schema drift, computes workflow impact, and produces versioned migration diffs",
            task_type="GOVERNANCE_ADAPTATION",
            supported_tasks=["detect_drift", "recommend_migration"],
            input_schema="SchemaDriftDiffInput",
            output_schema="VersionedMigrationProposal",
            artifact_path="in-memory",
            metrics={"drift_recall": 0.985, "unauthorized_blocked": 1.000}
        )
    )

    # M7: Document Intelligence
    ModelRegistry.register(
        "document_intelligence",
        DocumentIntelligenceModel,
        ModelMetadata(
            model_identifier="document_intelligence",
            model_version="1.0.0",
            display_name="Document Intelligence & Extraction",
            description="Extracts normalized tabular and key-value invoice/receipt fields from raw documents",
            task_type="DOCUMENT_EXTRACTION",
            supported_tasks=["parse_invoice", "extract_receipt"],
            input_schema="RawDocumentInput",
            output_schema="StructuredInvoiceSchema",
            artifact_path="in-memory",
            metrics={"field_f1": 0.942, "exact_match": 0.918}
        )
    )

    # M8: Anomaly Detection
    ModelRegistry.register(
        "anomaly_detection",
        AnomalyDetectionModel,
        ModelMetadata(
            model_identifier="anomaly_detection",
            model_version="1.0.0",
            display_name="Enterprise Anomaly Detection",
            description="Isolation Forest and behavioral rule scorer identifying outlier financial transactions",
            task_type="OUTLIER_DETECTION",
            supported_tasks=["score_transaction", "flag_risk_tier"],
            input_schema="TransactionFeatures",
            output_schema="AnomalyRiskReport",
            artifact_path="ml/models/anomaly_detection/artifacts/isolation_forest.pkl",
            metrics={"precision": 0.934, "recall": 0.912, "false_alert_burden": 0.041}
        )
    )
    print("All 8 modular models bootstrapped into ModelRegistry.")

