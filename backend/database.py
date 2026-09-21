import os
import sys
import shutil
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Si está en entorno empaquetado (PyInstaller .exe), la BD debe guardarse junto al ejecutable
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
    TARGET_DB = os.path.join(BASE_DIR, "prolago.db")
    # Copiar base de datos inicial con 982 artículos si es la primera ejecución
    if not os.path.exists(TARGET_DB):
        BUNDLED_DB = os.path.join(BUNDLE_DIR, "prolago.db")
        if os.path.exists(BUNDLED_DB):
            try:
                shutil.copy2(BUNDLED_DB, TARGET_DB)
            except Exception:
                pass
    DEFAULT_DB = TARGET_DB.replace("\\", "/")
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    TARGET_DB = os.path.join(BASE_DIR, "prolago.db")
    DEFAULT_DB = TARGET_DB.replace("\\", "/")

# Si está en la nube (Render/Railway), DATABASE_URL existirá. Si es local, utiliza SQLite
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB}")

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
