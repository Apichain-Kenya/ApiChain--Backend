from sqlalchemy import create_engine, text

# 🔴 PUT YOUR ACTUAL DB URL HERE
DATABASE_URL = "postgresql://apichain:apichain@localhost:5432/apichain"

engine = create_engine(DATABASE_URL)



with engine.connect() as conn:
    result = conn.execute(text("SHOW search_path"))
    print(result.fetchone())