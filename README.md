ApiChain Backend

Backend service for the Geo-AI and Blockchain-enabled Honey Traceability System.

This backend powers the core functionality for ApiChain, including farmer and aggregator onboarding, secure authentication, geo-spatial farm data management, document verification, and the honey traceability pipeline leveraging Geo-AI and blockchain technologies.

The Geo-AI module predicts expected honey physicochemical properties based on apiary
location, harvest season, and local flowering species, then validates those predictions
against actual lab results to produce an authenticity score.


Tech Stack
Backend Framework: FastAPI
Database: PostgreSQL + PostGIS
ORM & Migrations: SQLAlchemy + Alembic
Geospatial: GeoAlchemy2
Authentication: JWT-based authentication
Containerization: Docker


Setup Instructions
1. Clone the repository
git clone https://github.com/Apichain-Kenya/ApiChain--Backend.git
cd ApiChain--Backend
2. Create a virtual environment
python -m venv .venv

Activate the virtual environment:

Windows (PowerShell):
.venv\Scripts\Activate
Linux/Mac:
source .venv/bin/activate
3. Install dependencies
pip install -r backend/requirements.txt
4. Set up environment variables

Create a .env file inside backend/

5. Set up the database

Make sure PostgreSQL is running and has the PostGIS extension installed. 

6. Set up Geo-AI models 

The machine learning models are **not stored in this repository** (binary files, ~50MB).
You must download and extract them before the Geo-AI endpoints will work.

**Step 1 — Download the model zip**

Download `ml_models.zip` from the shared team drive:


**Step 2 — Create the models folder**

```bash
mkdir backend/app/ml_models
```

**Step 3 — Extract the zip into that folder**

The folder must contain exactly these files:
backend/app/ml_models/
scaler.pkl
le_region.pkl
le_season.pkl
le_veg.pkl
feature_cols.json
flowering_calendar.pkl
ensemble_moisture_content.pkl
ensemble_sucrose_level.pkl
ensemble_hmf_level.pkl



7. Start the server

cd backend 
python -u -m uvicorn app.main:app --reload --port 8000

The server will be accessible at:

http://127.0.0.1:8000

You can view interactive API docs at:

http://127.0.0.1:8000/docs
