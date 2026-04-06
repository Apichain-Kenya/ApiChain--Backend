import os
from dotenv import load_dotenv
from fastapi import FastAPI
# FIX: Added CORS middleware so the frontend can make cross-origin API calls.
# Without this, browsers block requests from a different origin (e.g. localhost:3000).
from fastapi.middleware.cors import CORSMiddleware
from app import database
from app.routers import auth, farmers, aggregator

load_dotenv()
app = FastAPI()

# CORS configuration:
# Set FRONTEND_ORIGINS in .env as a comma-separated list of allowed origins.
# e.g. FRONTEND_ORIGINS=http://localhost:3000,http://localhost:5173
# When explicit origins are set, allow_credentials=True is safe (cookies/auth headers work).
# When no origins are set, fall back to allow_origins=["*"] with allow_credentials=False
# (wildcard + credentials is unsafe and rejected by browsers).
_origins_env = os.getenv("FRONTEND_ORIGINS", "")
if _origins_env:
    _origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
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