from dotenv import load_dotenv
from fastapi import FastAPI
from app import database
from app.routers import auth, farmers, aggregator

load_dotenv()
app = FastAPI()

@app.get("/")
def root():
    return {"message": "Backend is running 🚀"}

app.include_router(auth.router)
app.include_router(farmers.router)  
app.include_router(aggregator.router)