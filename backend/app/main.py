from dotenv import load_dotenv
from fastapi import FastAPI
# FIX: Added CORS middleware so the frontend can make cross-origin API calls.
# Without this, browsers block requests from a different origin (e.g. localhost:3000).
from fastapi.middleware.cors import CORSMiddleware
from app import database
from app.routers import auth, farmers, aggregator

load_dotenv()
app = FastAPI()

# FIX: CORS — allow all origins during development.
# TODO: Restrict 'allow_origins' to specific frontend URLs before production deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Backend is running"}

app.include_router(auth.router)
app.include_router(farmers.router)
app.include_router(aggregator.router)