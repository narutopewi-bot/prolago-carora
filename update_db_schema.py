from sqlalchemy import text
from backend.database import engine, Base
import backend.models

print("Actualizando tablas y esquema...")
Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    # Comprobar columnas en facturas
    try:
        conn.execute(text("ALTER TABLE facturas ADD COLUMN saldo_pendiente FLOAT DEFAULT 0.0"))
        print("Columna saldo_pendiente agregada")
    except Exception as e:
        print("Columna saldo_pendiente ya existe o error:", e)

    try:
        conn.execute(text("ALTER TABLE facturas ADD COLUMN estado_credito VARCHAR(20) DEFAULT 'saldado'"))
        print("Columna estado_credito agregada")
    except Exception as e:
        print("Columna estado_credito ya existe o error:", e)

    try:
        conn.execute(text("ALTER TABLE facturas ADD COLUMN fecha_vencimiento DATETIME"))
        print("Columna fecha_vencimiento agregada")
    except Exception as e:
        print("Columna fecha_vencimiento ya existe o error:", e)

    conn.commit()

print("Esquema verificado exitosamente.")
