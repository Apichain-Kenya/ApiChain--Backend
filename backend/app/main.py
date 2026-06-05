import os
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv  # type: ignore

# CRITICAL: load_dotenv() MUST run before any app.routers imports.
# Blockchain services read env vars (RPC URL, keys, addresses) at import time.
load_dotenv()

from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app import database
from app.routers import auth, farmers, user, batch, environmental, apiary, geo_ai
from app.services.environment_scheduler import start_scheduler, stop_scheduler
# aggregator router + table fully removed in Sprint 8 (2026-05-18). The
# 2026-04-12 pivot to admin-enrollment retired the aggregator concept; the
# migration is reversible should iteration 2 reintroduce it.
# lab_results router removed in Sprint 3 (2026-05-16) — the canonical
# oracle-signed path is POST /batches/{id}/lab-verify, which also persists
# the lab_results row. See routers/batch.py.


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sprint 6 hotfix: the reconciler + 6-hour environmental snapshot jobs
    # live in app.services.environment_scheduler. They MUST be started on
    # boot or HTTP 202 pending batches stay pending forever.
    try:
        start_scheduler()
        logging.getLogger(__name__).info("scheduler started")
    except Exception:
        logging.getLogger(__name__).exception("scheduler failed to start")
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(lifespan=lifespan)

security = HTTPBearer()

_origins_env = os.getenv("FRONTEND_ORIGINS", "")
_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
if _origins:
    _allow_credentials = True
else:
    _origins = ["*"]
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Backend is running"}

app.include_router(auth.router)
app.include_router(farmers.router)
app.include_router(user.router)
app.include_router(batch.router)
app.include_router(environmental.router)
app.include_router(apiary.router)
app.include_router(geo_ai.router)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="ApiChain API",
        version="1.0.0",
        description="API with JWT auth",
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            openapi_schema["paths"][path][method]["security"] = [
                {"BearerAuth": []}
            ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi