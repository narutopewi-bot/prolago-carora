import json
import urllib.request
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from sqlalchemy import text, inspect, Boolean, DateTime as SqlDateTime, Date as SqlDate, Integer, Float
from sqlalchemy.orm import Session
from .database import engine, Base, get_db, DATABASE_URL
from . import models

router = APIRouter(prefix="/api/migration", tags=["migration"])

MIGRATION_SECRET = "prolago_master_migration_secret_key_2026_carora"

def serialize_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="ignore")
    return val

def deserialize_value(val: Any, col_type: Any) -> Any:
    if val is None:
        return None
    if isinstance(col_type, Boolean):
        return bool(val)
    if isinstance(col_type, SqlDateTime):
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val)
            except Exception:
                pass
    if isinstance(col_type, SqlDate):
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val).date()
            except Exception:
                pass
    if isinstance(col_type, Float):
        try:
            return float(val)
        except Exception:
            return 0.0
    if isinstance(col_type, Integer):
        try:
            return int(val)
        except Exception:
            return 0
    return val

@router.get("/export-full-data")
def export_full_data(secret: str = Query(...)):
    if secret != MIGRATION_SECRET:
        raise HTTPException(status_code=403, detail="Acceso denegado: Token de migración inválido")

    export_result = {
        "version": 1,
        "exported_at": datetime.utcnow().isoformat(),
        "database_url_type": "postgresql" if DATABASE_URL.startswith("postgresql") else "sqlite",
        "tables": {}
    }

    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            t_name = table.name
            try:
                # Verificar si la tabla existe físicamente
                result = conn.execute(text(f'SELECT * FROM "{t_name}"'))
                rows = result.fetchall()
                cols = result.keys()
                
                table_records = []
                for row in rows:
                    rec = {}
                    for col_name, col_val in zip(cols, row):
                        rec[col_name] = serialize_value(col_val)
                    table_records.append(rec)

                export_result["tables"][t_name] = table_records
            except Exception as e:
                export_result["tables"][t_name] = {"error": str(e)}

    return export_result

@router.post("/import-full-data")
def import_full_data(payload: Dict[str, Any] = Body(...), secret: str = Query(...)):
    if secret != MIGRATION_SECRET:
        raise HTTPException(status_code=403, detail="Acceso denegado: Token de migración inválido")

    tables_data = payload.get("tables", {})
    if not tables_data:
        raise HTTPException(status_code=400, detail="No se proporcionaron datos de tablas en el payload")

    imported_summary = {}

    with engine.begin() as conn:
        # Desactivar temporalmente restricciones de clave foránea si es PostgreSQL
        is_pg = DATABASE_URL.startswith("postgresql")

        # 1. Limpiar tablas existentes en orden inverso de dependencias
        for table in reversed(Base.metadata.sorted_tables):
            t_name = table.name
            if t_name in tables_data and isinstance(tables_data[t_name], list):
                try:
                    conn.execute(text(f'DELETE FROM "{t_name}"'))
                except Exception as ex_del:
                    print(f"[IMPORT] Aviso al vaciar tabla {t_name}: {ex_del}")

        # 2. Insertar registros en orden directo de dependencias
        for table in Base.metadata.sorted_tables:
            t_name = table.name
            records = tables_data.get(t_name)
            if not records or not isinstance(records, list):
                continue

            col_map = {col.name: col.type for col in table.columns}
            valid_col_names = set(col_map.keys())

            cleaned_records = []
            for raw_rec in records:
                rec = {}
                for k, v in raw_rec.items():
                    if k in valid_col_names:
                        rec[k] = deserialize_value(v, col_map[k])
                cleaned_records.append(rec)

            if cleaned_records:
                try:
                    conn.execute(table.insert(), cleaned_records)
                    imported_summary[t_name] = len(cleaned_records)
                    print(f"[IMPORT] Tabla {t_name}: {len(cleaned_records)} registros insertados con éxito.")

                    # En PostgreSQL, sincronizar el contador de secuencia para el campo 'id'
                    if is_pg and "id" in valid_col_names:
                        try:
                            conn.execute(text(
                                f"SELECT setval(pg_get_serial_sequence('\"{t_name}\"', 'id'), COALESCE(MAX(id), 1)) FROM \"{t_name}\""
                            ))
                        except Exception as seq_err:
                            print(f"[IMPORT] Aviso de secuencia en {t_name}: {seq_err}")
                except Exception as ex_ins:
                    imported_summary[t_name] = f"Error: {ex_ins}"
                    print(f"[IMPORT] Error insertando en {t_name}: {ex_ins}")

    return {
        "status": "ok",
        "imported_summary": imported_summary,
        "timestamp": datetime.utcnow().isoformat()
    }

@router.post("/sync-from-render")
def sync_from_render(secret: str = Query(...)):
    if secret != MIGRATION_SECRET:
        raise HTTPException(status_code=403, detail="Acceso denegado: Token de migración inválido")

    render_url = f"https://prolago-carora.onrender.com/api/migration/export-full-data?secret={MIGRATION_SECRET}"
    print(f"[SYNC] Obteniendo dump completo desde Render: {render_url}...")

    req = urllib.request.Request(render_url, headers={"User-Agent": "ProlagoMigrator/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error conectando con Render para exportar datos: {str(e)}")

    print(f"[SYNC] Datos recibidos de Render. Iniciando importación directa a la base de datos actual...")
    return import_full_data(payload=data, secret=MIGRATION_SECRET)

@router.get("/health-check")
def health_check(secret: str = Query(...)):
    if secret != MIGRATION_SECRET:
        raise HTTPException(status_code=403, detail="Acceso denegado: Token de migración inválido")

    is_pg = DATABASE_URL.startswith("postgresql")
    sequences_status = {}

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            t_name = table.name
            cols = [c.name for c in table.columns]
            if "id" in cols:
                max_id = conn.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{t_name}"')).scalar()
                if is_pg:
                    try:
                        seq_name = conn.execute(text(f"SELECT pg_get_serial_sequence('{t_name}', 'id')")).scalar()
                        if seq_name:
                            conn.execute(text(f"SELECT setval('{seq_name}', {max_id + 1}, false)"))
                            sequences_status[t_name] = {"max_id": max_id, "sequence": seq_name, "next_id": max_id + 1, "calibrated": True}
                        else:
                            sequences_status[t_name] = {"max_id": max_id, "sequence": None, "calibrated": False}
                    except Exception as e:
                        sequences_status[t_name] = {"max_id": max_id, "error": str(e)}
                else:
                    sequences_status[t_name] = {"max_id": max_id, "status": "sqlite"}

    return {
        "status": "healthy",
        "database_type": "postgresql" if is_pg else "sqlite",
        "sequences": sequences_status
    }
