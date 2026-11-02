import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure AVENTRA root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database.session import seed_database
from ml.shared.model_registry.bootstrap import bootstrap_registry

from backend.api.auth import router as auth_router
from backend.api.workflows import router as workflows_router
from backend.api.approvals import router as approvals_router
from backend.api.ml_models import router as ml_router
from backend.api.data import router as data_router
from backend.api.audit import router as audit_router
from backend.api.analytics import router as analytics_router
from backend.api.agent import router as agent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and seed fixtures
    print("[AVENTRA] Initializing database and cryptographic ledger...")
    seed_database()
    print("[AVENTRA] Bootstrapping modular ML Model Registry...")
    bootstrap_registry()
    print("[AVENTRA] System ready. All trust & execution services active.")
    yield
    print("[AVENTRA] Graceful shutdown completed.")


app = FastAPI(
    title="AVENTRA: Enterprise AI Trust & Orchestration Platform",
    description="High-assurance enterprise agentic platform with human-in-the-loop governance, cryptographic auditability, and modular ML models.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(workflows_router)
app.include_router(approvals_router)
app.include_router(ml_router)
app.include_router(data_router)
app.include_router(audit_router)
app.include_router(analytics_router)
app.include_router(agent_router)


@app.get("/")
def root():
    return {
        "platform": "AVENTRA Enterprise AI Trust & Orchestration",
        "status": "OPERATIONAL",
        "version": "1.0.0",
        "docs_url": "/docs"
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "HEALTHY",
        "trust_layer": "ENFORCED",
        "audit_ledger": "ACTIVE",
        "models_count": 8
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

