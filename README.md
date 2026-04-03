ApiChain Backend

Backend service for the Geo-AI and Blockchain-enabled Honey Traceability System.

This backend powers the core functionality for ApiChain, including farmer and aggregator onboarding, secure authentication, geo-spatial farm data management, document verification, and the honey traceability pipeline leveraging Geo-AI and blockchain technologies.



The ApiChain backend enables:

Farmer & Aggregator onboarding
OTP-based authentication
Geo-spatial farm data management (PostGIS)
Document verification
Honey traceability pipeline (Geo-AI + Blockchain integration)

It exposes a RESTful API to facilitate frontend integration and ensures traceability and authenticity in the honey supply chain.

Features
Secure JWT-based authentication
OTP verification for farmers and aggregators
CRUD operations for farm and honey data
Geo-spatial data handling with PostGIS
Blockchain integration for traceability
FastAPI-based endpoints with interactive documentation

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

Create a .env file inside backend/:

DATABASE_URL=postgresql://username:password@localhost:5432/apichain
SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30



5. Set up the database

Make sure PostgreSQL is running and has the PostGIS extension installed. 

6. Start the server

cd backend 
python -u -m uvicorn app.main:app --reload --port 8000

The server will be accessible at:

http://127.0.0.1:8000

You can view interactive API docs at:

http://127.0.0.1:8000/docs