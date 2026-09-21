import os
import sqlite3
from datetime import datetime
from sqlalchemy import text, Boolean, DateTime, Date
from .database import engine, Base, TARGET_DB, DATABASE_URL

def migrate_sqlite_to_pg_if_needed():
    """
    Si la aplicación está conectada a PostgreSQL y la base de datos está vacía,
    migra automáticamente todos los datos del archivo local SQLite (prolago.db).
    """
    if not DATABASE_URL.startswith("postgresql"):
        return

    # Verificar si PostgreSQL ya tiene datos en la tabla articulos
    with engine.connect() as conn:
        try:
            art_count = conn.execute(text("SELECT COUNT(*) FROM articulos")).scalar()
            if art_count and art_count > 0:
                print(f"[PG MIGRATOR] PostgreSQL ya contiene {art_count} artículos. Omitiendo migración.")
                return
        except Exception as e:
            print(f"[PG MIGRATOR] Comprobación inicial de artículos: {e}")

    if not os.path.exists(TARGET_DB):
        print(f"[PG MIGRATOR] Archivo SQLite {TARGET_DB} no encontrado. No se puede migrar.")
        return

    print(f"[PG MIGRATOR] Migrando datos desde SQLite ({TARGET_DB}) a PostgreSQL en la nube...")

    try:
        sqlite_conn = sqlite3.connect(TARGET_DB)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cur = sqlite_conn.cursor()

        # Importar modelos para que Base.metadata esté poblado
        from . import models

        with engine.begin() as pg_conn:
            for table in Base.metadata.sorted_tables:
                t_name = table.name
                try:
                    # Verificar si la tabla existe en SQLite
                    exists = sqlite_cur.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t_name,)
                    ).fetchone()
                    if not exists:
                        continue

                    rows = sqlite_cur.execute(f"SELECT * FROM {t_name}").fetchall()
                    if not rows:
                        continue

                    records = []
                    for row in rows:
                        rec = dict(row)
                        # Adaptación de tipos entre SQLite y PostgreSQL
                        for col in table.columns:
                            c_name = col.name
                            if c_name in rec and rec[c_name] is not None:
                                val = rec[c_name]
                                if isinstance(col.type, Boolean):
                                    rec[c_name] = bool(val)
                                elif isinstance(col.type, DateTime) and isinstance(val, str):
                                    try:
                                        rec[c_name] = datetime.fromisoformat(val)
                                    except Exception:
                                        pass
                                elif isinstance(col.type, Date) and isinstance(val, str):
                                    try:
                                        rec[c_name] = datetime.fromisoformat(val).date()
                                    except Exception:
                                        pass
                        records.append(rec)

                    if records:
                        # Insertar por lotes
                        pg_conn.execute(table.insert(), records)
                        print(f"[PG MIGRATOR] Migrada tabla '{t_name}': {len(records)} filas insertadas.")

                        # Ajustar secuencia del serial primary key en Postgres
                        if "id" in [c.name for c in table.columns]:
                            try:
                                pg_conn.execute(text(
                                    f"SELECT setval(pg_get_serial_sequence('{t_name}', 'id'), COALESCE(MAX(id), 1)) FROM \"{t_name}\""
                                ))
                            except Exception:
                                pass

                except Exception as ex_table:
                    print(f"[PG MIGRATOR] Advertencia en tabla '{t_name}': {ex_table}")

        sqlite_conn.close()
        print("[PG MIGRATOR] ¡Migración de SQLite a PostgreSQL finalizada con total éxito!")
    except Exception as e:
        print(f"[PG MIGRATOR] Error general durante la migración: {e}")
