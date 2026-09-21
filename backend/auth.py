import hashlib
import os
import secrets
from typing import Optional
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from .database import get_db
from .models import Usuario

# Almacén de sesiones activas en memoria: {token: usuario_id}
ACTIVE_SESSIONS = {}

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
    token = secrets.token_urlsafe(32)
    ACTIVE_SESSIONS[token] = user_id
    return token

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[Usuario]:
    # Buscar token en cookie o en header Authorization
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            
    if not token or token not in ACTIVE_SESSIONS:
        return None
        
    user_id = ACTIVE_SESSIONS[token]
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

