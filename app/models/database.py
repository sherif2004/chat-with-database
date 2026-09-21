from sqlalchemy import create_engine

from app.config import DATABASE_URL

# Railway PostgreSQL
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)
