import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Si está en Railway u otro entorno en la nube, DATABASE_URL existirá.
# Si es local, utiliza SQLite en el archivo prolago.db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./prolago.db")

# Si Railway proporciona postgres:// lo convertimos a postgresql:// para SQLAlchemy 2.0+
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
