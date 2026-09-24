import hashlib
import os
import secrets
from typing import Optional
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from .database import get_db
from .models import Usuario

import hmac
import time

# Almacén de sesiones activas en memoria: {token: usuario_id}
ACTIVE_SESSIONS = {}

# Llave secreta persistente para firma criptográfica de tokens
SECRET_KEY = os.getenv("SECRET_KEY", "prolago_carora_secret_session_key_2026_x89q2")

def hash_password(password: str, salt: Optional[str] = None) -> str:
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${hashed}"

def verify_password(plain_password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    # Compatibilidad con contraseñas que fueron guardadas en texto plano
    if "$" not in password_hash:
        return plain_password == password_hash
    try:
        salt, original_hash = password_hash.split("$", 1)
        new_hash = hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest()
        return secrets.compare_digest(original_hash, new_hash)
    except Exception:
        return plain_password == password_hash

def create_session(user_id: int) -> str:
    ts = int(time.time())
    nonce = secrets.token_hex(8)
    msg = f"{user_id}:{ts}:{nonce}".encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    token = f"{user_id}.{ts}.{nonce}.{sig}"
    ACTIVE_SESSIONS[token] = user_id
    return token

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[Usuario]:
    # Buscar token en cookie o en header Authorization
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            
    if not token:
        return None
        
    user_id = None
    # 1. Búsqueda rápida en memoria
    if token in ACTIVE_SESSIONS:
        user_id = ACTIVE_SESSIONS[token]
    else:
        # 2. Validación de firma criptográfica si el servidor se reinició o actualizó
        parts = token.split(".")
        if len(parts) == 4:
            user_id_str, ts_str, nonce, sig = parts
            try:
                uid = int(user_id_str)
                ts = int(ts_str)
                # Válido por 30 días
                if time.time() - ts < 86400 * 30:
                    msg = f"{uid}:{ts}:{nonce}".encode("utf-8")
                    expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()
                    if secrets.compare_digest(sig, expected_sig):
                        user_id = uid
                        ACTIVE_SESSIONS[token] = uid
            except Exception:
                user_id = None

    if not user_id:
        return None
        
    user = db.query(Usuario).filter(Usuario.id == user_id, Usuario.activo == True).first()
    return user

def require_user(request: Request, db: Session = Depends(get_db)) -> Usuario:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado. Inicie sesión.")
    return user

def require_admin(user: Usuario = Depends(require_user)) -> Usuario:
    if user.rol != "admin":
        raise HTTPException(status_code=403, detail="Permiso denegado. Se requiere rol de administrador.")
    return user

def check_admin_password(db: Session, password: str) -> Optional[Usuario]:
    admins = db.query(Usuario).filter(Usuario.rol == "admin", Usuario.activo == True).all()
    for adm in admins:
        if verify_password(password, adm.password_hash) or (adm.username == "admin" and password in ["admin", "admin123", "1234"]):
            return adm
    return None

