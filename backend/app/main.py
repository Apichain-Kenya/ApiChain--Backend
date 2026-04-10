import os
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer
from dotenv import load_dotenv # type: ignore
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app import database
from app.routers import auth, farmers, aggregator, user

load_dotenv()
app = FastAPI()

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
app.include_router(aggregator.router)
app.include_router(user.router)


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