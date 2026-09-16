import os
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Request, Response, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, desc, text
import json

from .database import get_db, engine, Base
from .models import Articulo, Cliente, Factura, DetalleFactura, Despacho, DetalleDespacho, Compra, Usuario, Configuracion, AbonoCredito, Caja
from .schemas import (
    LoginRequest, TasaBCVUpdate, ArticuloCreate, ArticuloOut,
    ClienteCreate, ClienteOut, FacturaCreate, DespachoCreate, CompraCreate, AbonoCreate,
    UsuarioCreate, UsuarioUpdate, UsuarioOut, VerificarAdminRequest, ItemFacturaUpdate, FacturaUpdate,
    CajaApertura, CajaCierre
)
from .auth import (
    hash_password, verify_password, create_session, check_admin_password,
    ACTIVE_SESSIONS, get_current_user, require_user, require_admin
)

# Inicializar tablas
Base.metadata.create_all(bind=engine)

# Auto-migración segura de columnas nuevas
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE articulos ADD COLUMN stock_alerta FLOAT DEFAULT 5.0"))
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN permisos TEXT DEFAULT '*'"))
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE facturas ADD COLUMN caja_id INTEGER"))
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE abonos_credito ADD COLUMN caja_id INTEGER"))
        conn.commit()
    except Exception:
        pass

app = FastAPI(title="Prolago Carora Web", version="1.0.0")

# Directorios de frontend
import sys
if getattr(sys, "frozen", False):
    ROOT_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATIC_DIR = os.path.join(ROOT_DIR, "frontend", "static")
TEMPLATES_DIR = os.path.join(ROOT_DIR, "frontend", "templates")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Helper para configuración
def get_config_val(db: Session, clave: str, default: str = "") -> str:
    cfg = db.query(Configuracion).filter_by(clave=clave).first()
    return cfg.valor if cfg else default

# ==========================================
# RUTAS DE AUTENTICACIÓN
# ==========================================
@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.username == payload.username.strip(), Usuario.activo == True).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Usuario o contraseña incorrectos")
    
    token = create_session(user.id)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=86400 * 7,
        samesite="lax"
    )
    return {
        "status": "ok",
        "user": {
            "id": user.id,
            "username": user.username,
            "nombre": user.nombre,
            "rol": user.rol,
            "permisos": user.lista_permisos
        }
    }

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]
    response.delete_cookie("session_token")
    return {"status": "ok"}

@app.get("/api/auth/me")
def me(user: Usuario = Depends(require_user)):
    return {
        "id": user.id,
        "username": user.username,
        "nombre": user.nombre,
        "rol": user.rol,
        "permisos": user.lista_permisos
    }

@app.post("/api/auth/verificar_admin")
def verificar_admin(payload: VerificarAdminRequest, db: Session = Depends(get_db)):
    admin = check_admin_password(db, payload.password)
    if not admin:
        raise HTTPException(status_code=401, detail="Contraseña de administrador incorrecta")
    return {"status": "ok", "admin_nombre": admin.nombre}

# ==========================================
# ARTÍCULOS E INVENTARIO
# ==========================================
@app.get("/api/articulos")
def list_articulos(
    search: Optional[str] = None,
    categoria: Optional[str] = None,
    solo_stock: Optional[bool] = False,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    query = db.query(Articulo).filter(Articulo.activo == True)
    if search:
        s = f"%{search.strip()}%"
        # Permitir buscar por código o nombre
        try:
            codigo_num = int(search.strip())
            query = query.filter(or_(Articulo.codigo == codigo_num, Articulo.nombre.ilike(s)))
        except ValueError:
            query = query.filter(Articulo.nombre.ilike(s))
            
    if categoria and categoria != "TODAS":
        query = query.filter(Articulo.categoria == categoria)
        
    if solo_stock:
        query = query.filter(Articulo.stock > 0)
        
    total = query.count()
    items = query.order_by(Articulo.nombre.asc()).offset(offset).limit(limit).all()
    return {"total": total, "items": items}

@app.get("/api/articulos/{codigo}")
def get_articulo(codigo: int, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    item = db.query(Articulo).filter(Articulo.codigo == codigo).first()
    if not item:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    return item

@app.post("/api/articulos")
def create_articulo(payload: ArticuloCreate, db: Session = Depends(get_db), user: Usuario = Depends(require_admin)):
    exists = db.query(Articulo).filter(Articulo.codigo == payload.codigo).first()
    if exists:
        raise HTTPException(status_code=400, detail=f"Ya existe un artículo con el código {payload.codigo}")
    
    # Calcular costo final y precio sugerido
    costo_final = round((payload.costo or 0.0) + (payload.flete or 0.0), 2)
    rent = payload.rentabilidad or 20.0
    sugerido = round(costo_final + (costo_final * rent / 100.0) + (payload.mas or 0.0), 2)
    precio = payload.precio or sugerido

    stock_alerta = payload.stock_alerta if payload.stock_alerta is not None else 5.0

    item = Articulo(
        codigo=payload.codigo,
        nombre=payload.nombre.strip().upper(),
        categoria=(payload.categoria or "GENERAL").strip().upper(),
        marca=(payload.marca or "").strip().upper(),
        proveedor=(payload.proveedor or "").strip().upper(),
        costo=payload.costo or 0.0,
        flete=payload.flete or 0.0,
        costo_final=costo_final,
        mas=payload.mas or 0.0,
        rentabilidad=rent,
        sugerido=sugerido,
        precio=precio,
        stock=payload.stock or 0.0,
        stock_alerta=stock_alerta,
        activo=True
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@app.put("/api/articulos/{codigo}")
def update_articulo(codigo: int, payload: ArticuloCreate, db: Session = Depends(get_db), user: Usuario = Depends(require_admin)):
    item = db.query(Articulo).filter(Articulo.codigo == codigo).first()
    if not item:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
        
    costo_final = round((payload.costo or 0.0) + (payload.flete or 0.0), 2)
    rent = payload.rentabilidad or 20.0
    sugerido = round(costo_final + (costo_final * rent / 100.0) + (payload.mas or 0.0), 2)

    item.nombre = payload.nombre.strip().upper()
    item.categoria = (payload.categoria or "GENERAL").strip().upper()
    item.marca = (payload.marca or "").strip().upper()
    item.proveedor = (payload.proveedor or "").strip().upper()
    item.costo = payload.costo or 0.0
    item.flete = payload.flete or 0.0
    item.costo_final = costo_final
    item.mas = payload.mas or 0.0
    item.rentabilidad = rent
    item.sugerido = sugerido
    item.precio = payload.precio or sugerido
    item.stock = payload.stock
    if payload.stock_alerta is not None:
        item.stock_alerta = payload.stock_alerta
    
    db.commit()
    db.refresh(item)
    return item

# ==========================================
# CLIENTES
# ==========================================
@app.get("/api/clientes")
def list_clientes(
    tipo: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    query = db.query(Cliente)
    if tipo:
        query = query.filter(Cliente.tipo == tipo)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(Cliente.nombre.ilike(s), Cliente.cedula_rif.ilike(s)))
    return query.order_by(Cliente.nombre.asc()).limit(150).all()

@app.post("/api/clientes")
def create_cliente(payload: ClienteCreate, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    cliente = Cliente(
        cedula_rif=payload.cedula_rif.strip().upper(),
        nombre=payload.nombre.strip().upper(),
        direccion=payload.direccion.strip(),
        telefono=payload.telefono.strip(),
        tipo=payload.tipo or "general"
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente

# ==========================================
# FACTURACIÓN / POS
# ==========================================
@app.get("/api/facturas/siguiente_numero")
def get_next_factura_num(db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    # Buscar el último número numérico de factura
    last_fact = db.query(Factura).order_by(Factura.id.desc()).first()
    if not last_fact:
        return {"siguiente": "1"}
    try:
        next_num = str(int(last_fact.numero) + 1)
    except:
        next_num = str(last_fact.id + 1)
    return {"siguiente": next_num}

@app.post("/api/facturas")
def create_factura(payload: FacturaCreate, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="La factura no tiene ningún producto")

    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))

    # Siguiente número
    last_fact = db.query(Factura).order_by(Factura.id.desc()).first()
    try:
        next_num = str(int(last_fact.numero) + 1) if last_fact else "1"
    except:
        next_num = str((last_fact.id if last_fact else 0) + 1)

    total_factura = 0.0
    detalles = []

    # Validar productos y calcular
    for it in payload.items:
        articulo = db.query(Articulo).filter(Articulo.codigo == it.codigo_articulo).first()
        if not articulo:
            raise HTTPException(status_code=404, detail=f"Artículo {it.codigo_articulo} no encontrado")
        
        # Descuento en %
        dcto = max(0.0, min(100.0, it.descuento_pct or 0.0))
        precio_con_dcto = it.precio_unitario * (1.0 - dcto / 100.0)
        subtotal = round(it.cantidad * precio_con_dcto, 2)
        total_factura += subtotal

        # Disminuir stock
        articulo.stock = round(articulo.stock - it.cantidad, 2)

        detalles.append(DetalleFactura(
            codigo_articulo=articulo.codigo,
            nombre_articulo=articulo.nombre,
            cantidad=it.cantidad,
            precio_unitario=it.precio_unitario,
            descuento_pct=dcto,
            subtotal=subtotal,
            costo_unitario=articulo.costo_final
        ))

    total_factura = round(total_factura, 2)

    # Validar formas de pago
    total_pagado = round((payload.efectivo or 0.0) + (payload.zelle or 0.0) +
                         (payload.pagomovil or 0.0) + (payload.punto or 0.0) +
                         (payload.credito or 0.0), 2)
    
    # Si no se desglosó el pago, asignar automáticamente al método principal
    efectivo = payload.efectivo or 0.0
    zelle = payload.zelle or 0.0
    pagomovil = payload.pagomovil or 0.0
    punto = payload.punto or 0.0
    credito = payload.credito or 0.0

    if total_pagado == 0.0:
        efectivo = total_factura

    condicion = payload.condicion or ("credito" if credito > 0 else "contado")

    # Gestión de crédito
    saldo_pendiente = credito if (credito > 0 or condicion == "credito") else 0.0
    estado_credito = "pendiente" if saldo_pendiente > 0 else "saldado"
    fecha_venc = (datetime.now() + timedelta(days=payload.dias_credito or 15)) if saldo_pendiente > 0 else None
    caja_activa = db.query(Caja).filter(Caja.estado == "abierta").order_by(Caja.id.desc()).first()
    caja_id = caja_activa.id if caja_activa else None

    factura = Factura(
        numero=next_num,
        fecha=datetime.now(),
        cliente_nombre=(payload.cliente_nombre or "CLIENTE DE CONTADO").strip().upper(),
        cliente_id=payload.cliente_id,
        total=total_factura,
        tasa_bcv=tasa_bcv,
        condicion=condicion,
        efectivo=efectivo,
        zelle=zelle,
        pagomovil=pagomovil,
        punto=punto,
        credito=credito,
        saldo_pendiente=saldo_pendiente,
        estado_credito=estado_credito,
        fecha_vencimiento=fecha_venc,
        usuario_id=user.id,
        caja_id=caja_id,
        items=detalles
    )
    db.add(factura)
    db.commit()
    db.refresh(factura)

    cli = None
    if payload.cliente_id:
        cli = db.query(Cliente).filter(Cliente.id == payload.cliente_id).first()
    if not cli and payload.cliente_nombre:
        cli = db.query(Cliente).filter(Cliente.nombre == payload.cliente_nombre.strip().upper()).first()

    return {
        "status": "ok",
        "factura_id": factura.id,
        "numero": factura.numero,
        "condicion": factura.condicion,
        "total_usd": factura.total,
        "total_bs": round(factura.total * tasa_bcv, 2),
        "tasa_bcv": tasa_bcv,
        "efectivo": factura.efectivo or 0.0,
        "zelle": factura.zelle or 0.0,
        "pagomovil": factura.pagomovil or 0.0,
        "punto": factura.punto or 0.0,
        "credito": factura.credito or 0.0,
        "saldo_pendiente": factura.saldo_pendiente,
        "fecha_vencimiento": factura.fecha_vencimiento.strftime("%d/%m/%Y") if factura.fecha_vencimiento else "",
        "dias_credito": payload.dias_credito or 15,
        "cliente_nombre": factura.cliente_nombre,
        "cliente_cedula": cli.cedula_rif if cli else "",
        "cliente_telefono": cli.telefono if cli else "",
        "cliente_direccion": cli.direccion if cli else "",
        "fecha": factura.fecha.strftime("%d/%m/%Y %I:%M %p") if factura.fecha else ""
    }

@app.get("/api/facturas")
def list_facturas(
    limit: int = 150,
    offset: int = 0,
    search: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    condicion: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    query = db.query(Factura)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(Factura.numero.ilike(s), Factura.cliente_nombre.ilike(s)))
    if fecha_inicio and fecha_inicio.strip():
        try:
            dt_inicio = datetime.strptime(fecha_inicio.strip(), "%Y-%m-%d")
            query = query.filter(Factura.fecha >= dt_inicio)
        except Exception:
            pass
    if fecha_fin and fecha_fin.strip():
        try:
            dt_fin = datetime.strptime(fecha_fin.strip(), "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Factura.fecha < dt_fin)
        except Exception:
            pass
    if condicion and condicion.strip():
        c = condicion.strip().lower()
        if c in ["contado", "credito"]:
            query = query.filter(Factura.condicion == c)

    total = query.count()
    facturas = query.order_by(Factura.fecha.desc()).offset(offset).limit(limit).all()
    
    items = []
    for f in facturas:
        cred = f.credito or 0.0
        saldo = f.saldo_pendiente if f.saldo_pendiente is not None else cred
        abonado = round(max(0.0, cred - saldo), 2)
        items.append({
            "id": f.id,
            "numero": f.numero,
            "fecha": f.fecha.isoformat() if f.fecha else "",
            "fecha_formateada": f.fecha.strftime("%d/%m/%Y %I:%M %p") if f.fecha else "",
            "cliente_nombre": f.cliente_nombre or "CLIENTE DE CONTADO",
            "condicion": f.condicion or "contado",
            "total": f.total or 0.0,
            "tasa_bcv": f.tasa_bcv or 1.0,
            "efectivo": f.efectivo or 0.0,
            "zelle": f.zelle or 0.0,
            "pagomovil": f.pagomovil or 0.0,
            "punto": f.punto or 0.0,
            "credito": cred,
            "saldo_pendiente": saldo,
            "total_abonado": abonado,
            "estado_credito": f.estado_credito or ("saldado" if saldo <= 0.009 else "pendiente"),
            "fecha_vencimiento": f.fecha_vencimiento.strftime("%d/%m/%Y") if f.fecha_vencimiento else ""
        })
    return {"total": total, "items": items}

@app.get("/api/facturas/{id}")
def get_factura(id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    factura = db.query(Factura).filter(Factura.id == id).first()
    if not factura:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    cred = factura.credito or 0.0
    saldo = factura.saldo_pendiente if factura.saldo_pendiente is not None else cred
    abonado = round(max(0.0, cred - saldo), 2)

    cli = db.query(Cliente).filter(Cliente.id == factura.cliente_id).first() if factura.cliente_id else None
    if not cli and factura.cliente_nombre:
        cli = db.query(Cliente).filter(Cliente.nombre == factura.cliente_nombre).first()
    
    abonos_list = [
        {
            "id": ab.id,
            "fecha": ab.fecha.strftime("%Y-%m-%d %H:%M") if ab.fecha else "",
            "monto_usd": ab.monto_usd,
            "monto_bs": ab.monto_bs,
            "metodo_pago": ab.metodo_pago
        }
        for ab in (factura.abonos or [])
    ]

    return {
        "id": factura.id,
        "numero": factura.numero,
        "condicion": factura.condicion or "contado",
        "credito_inicial": cred,
        "saldo_pendiente": saldo,
        "total_abonado": abonado,
        "estado_credito": factura.estado_credito or ("saldado" if saldo <= 0.009 else "pendiente"),
        "fecha": factura.fecha.strftime("%d/%m/%Y %I:%M %p") if factura.fecha else "",
        "fecha_vencimiento": factura.fecha_vencimiento.strftime("%d/%m/%Y") if factura.fecha_vencimiento else "",
        "cliente_nombre": factura.cliente_nombre,
        "cliente_cedula": cli.cedula_rif if cli else "",
        "cliente_telefono": cli.telefono if cli else "",
        "cliente_direccion": cli.direccion if cli else "",
        "total_usd": factura.total,
        "total_bs": round(factura.total * factura.tasa_bcv, 2),
        "tasa_bcv": factura.tasa_bcv,
        "pagos": {
            "efectivo": factura.efectivo,
            "zelle": factura.zelle,
            "pagomovil": factura.pagomovil,
            "punto": factura.punto,
            "credito": cred
        },
        "abonos": abonos_list,
        "items": [
            {
                "codigo": it.codigo_articulo,
                "nombre": it.nombre_articulo,
                "cantidad": it.cantidad,
                "precio": it.precio_unitario,
                "descuento": it.descuento_pct,
                "subtotal": it.subtotal
            }
            for it in factura.items
        ]
    }

@app.put("/api/facturas/{id}")
def update_factura(id: int, payload: FacturaUpdate, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    autorizado = user.tiene_permiso("modificar_facturas") or user.rol == "admin"
    if not autorizado:
        if payload.admin_password:
            admin = check_admin_password(db, payload.admin_password)
            if admin:
                autorizado = True
    
    if not autorizado:
        raise HTTPException(status_code=403, detail="Se requiere autorización de administrador para modificar facturas")
    
    factura = db.query(Factura).filter(Factura.id == id).first()
    if not factura:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    tasa_bcv = factura.tasa_bcv or float(get_config_val(db, "tasa_bcv", "473.92"))

    # Si se actualizan los ítems
    if payload.items is not None:
        if len(payload.items) == 0:
            raise HTTPException(status_code=400, detail="La factura debe tener al menos un producto")
        
        # 1. Revertir stock de los ítems existentes
        for item_antiguo in factura.items:
            art = db.query(Articulo).filter(Articulo.codigo == item_antiguo.codigo_articulo).first()
            if art:
                art.stock += item_antiguo.cantidad
        
        # 2. Eliminar detalles anteriores
        for item_antiguo in list(factura.items):
            db.delete(item_antiguo)
        db.flush()

        # 3. Aplicar nuevos ítems y descontar nuevo stock
        total_nuevo = 0.0
        nuevos_detalles = []
        for it in payload.items:
            art = db.query(Articulo).filter(Articulo.codigo == it.codigo_articulo).first()
            if not art:
                raise HTTPException(status_code=400, detail=f"Artículo con código {it.codigo_articulo} no encontrado")
            
            art.stock -= it.cantidad
            dcto = it.descuento_pct or 0.0
            subt = round(it.cantidad * it.precio_unitario * (1 - dcto / 100), 2)
            total_nuevo += subt
            nuevos_detalles.append(DetalleFactura(
                codigo_articulo=art.codigo,
                nombre_articulo=art.nombre,
                cantidad=it.cantidad,
                precio_unitario=it.precio_unitario,
                descuento_pct=dcto,
                subtotal=subt,
                costo_unitario=art.costo_final
            ))
        
        factura.items = nuevos_detalles
        factura.total = round(total_nuevo, 2)

    # Actualizar cliente si corresponde
    if payload.cliente_nombre is not None and payload.cliente_nombre.strip():
        factura.cliente_nombre = payload.cliente_nombre.strip().upper()
    if payload.cliente_id is not None:
        factura.cliente_id = payload.cliente_id

    # Actualizar condición
    if payload.condicion:
        factura.condicion = payload.condicion.strip().lower()

    # Actualizar desglose de formas de pago
    if payload.efectivo is not None: factura.efectivo = payload.efectivo
    if payload.zelle is not None: factura.zelle = payload.zelle
    if payload.pagomovil is not None: factura.pagomovil = payload.pagomovil
    if payload.punto is not None: factura.punto = payload.punto
    if payload.credito is not None: factura.credito = payload.credito

    suma_pagos = round((factura.efectivo or 0.0) + (factura.zelle or 0.0) + (factura.pagomovil or 0.0) + (factura.punto or 0.0), 2)
    
    if factura.condicion == "contado":
        factura.credito = 0.0
        factura.saldo_pendiente = 0.0
        factura.estado_credito = "saldado"
        if suma_pagos == 0.0:
            factura.efectivo = factura.total
    else:  # Crédito
        if payload.credito is None and (factura.credito is None or factura.credito == 0.0):
            factura.credito = max(0.0, round(factura.total - suma_pagos, 2))
        
        # Considerar abonos ya realizados
        total_abonos = sum(ab.monto_usd for ab in (factura.abonos or []))
        credito_inicial = factura.credito or 0.0
        factura.saldo_pendiente = max(0.0, round(credito_inicial - total_abonos, 2))
        factura.estado_credito = "saldado" if factura.saldo_pendiente <= 0.009 else "pendiente"
        if payload.dias_credito and payload.dias_credito > 0:
            factura.fecha_vencimiento = factura.fecha + timedelta(days=payload.dias_credito)

    db.commit()
    db.refresh(factura)

    return {
        "status": "ok",
        "mensaje": f"Factura #{factura.numero} modificada exitosamente",
        "factura_id": factura.id,
        "numero": factura.numero,
        "total": factura.total,
        "condicion": factura.condicion,
        "saldo_pendiente": factura.saldo_pendiente
    }

# ==========================================
# GESTIÓN DE CRÉDITOS Y COBRANZAS
# ==========================================
@app.get("/api/creditos")
def list_creditos(
    search: Optional[str] = None,
    solo_pendientes: bool = True,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    query = db.query(Factura).filter(Factura.credito > 0)
    if solo_pendientes:
        query = query.filter(Factura.saldo_pendiente > 0.009)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(Factura.numero.ilike(s), Factura.cliente_nombre.ilike(s)))

    facturas_credito = query.order_by(Factura.fecha.desc()).all()
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))

    total_por_cobrar_usd = sum(f.saldo_pendiente for f in facturas_credito if f.saldo_pendiente > 0)
    total_por_cobrar_bs = round(total_por_cobrar_usd * tasa_bcv, 2)
    clientes_unicos = len(set(f.cliente_nombre for f in facturas_credito if f.saldo_pendiente > 0))

    items = []
    for f in facturas_credito:
        # Buscar teléfono del cliente si está registrado
        telefono = ""
        direccion = ""
        cli = None
        if f.cliente_id:
            cli = db.query(Cliente).filter(Cliente.id == f.cliente_id).first()
        if not cli and f.cliente_nombre:
            cli = db.query(Cliente).filter(Cliente.nombre == f.cliente_nombre).first()
        if cli:
            telefono = cli.telefono
            direccion = cli.direccion

        items.append({
            "factura_id": f.id,
            "numero": f.numero,
            "fecha": f.fecha.strftime("%Y-%m-%d %H:%M"),
            "fecha_vencimiento": f.fecha_vencimiento.strftime("%Y-%m-%d") if f.fecha_vencimiento else "",
            "cliente_nombre": f.cliente_nombre,
            "telefono": telefono,
            "direccion": direccion,
            "total_factura": f.total,
            "monto_credito": f.credito,
            "saldo_pendiente": round(f.saldo_pendiente, 2),
            "saldo_pendiente_bs": round(f.saldo_pendiente * tasa_bcv, 2),
            "estado": f.estado_credito,
            "tasa_bcv": tasa_bcv
        })

    return {
        "resumen": {
            "total_por_cobrar_usd": round(total_por_cobrar_usd, 2),
            "total_por_cobrar_bs": total_por_cobrar_bs,
            "total_deudores": clientes_unicos,
            "facturas_activas": len([f for f in facturas_credito if f.saldo_pendiente > 0])
        },
        "items": items
    }

@app.post("/api/creditos/{factura_id}/abonos")
def registrar_abono(
    factura_id: int,
    payload: AbonoCreate,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    factura = db.query(Factura).filter(Factura.id == factura_id).first()
    if not factura:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    if factura.saldo_pendiente <= 0:
        raise HTTPException(status_code=400, detail="Esta factura ya está completamente saldada")

    monto_abono = min(payload.monto_usd, factura.saldo_pendiente)
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    monto_bs = payload.monto_bs if payload.monto_bs and payload.monto_bs > 0 else round(monto_abono * tasa_bcv, 2)

    caja_activa = db.query(Caja).filter(Caja.estado == "abierta").order_by(Caja.id.desc()).first()
    caja_id = caja_activa.id if caja_activa else None

    abono = AbonoCredito(
        factura_id=factura.id,
        fecha=datetime.now(),
        monto_usd=round(monto_abono, 2),
        monto_bs=round(monto_bs, 2),
        tasa_bcv=tasa_bcv,
        metodo_pago=payload.metodo_pago or "efectivo",
        nota=payload.nota or "",
        caja_id=caja_id
    )
    db.add(abono)

    factura.saldo_pendiente = round(max(0.0, factura.saldo_pendiente - monto_abono), 2)
    if factura.saldo_pendiente <= 0.009:
        factura.estado_credito = "saldado"
    else:
        factura.estado_credito = "parcial"

    db.commit()
    db.refresh(abono)

    return {
        "status": "ok",
        "abono_id": abono.id,
        "monto_abonado": abono.monto_usd,
        "nuevo_saldo_pendiente": factura.saldo_pendiente,
        "estado_credito": factura.estado_credito
    }

@app.get("/api/creditos/{factura_id}/abonos")
def listar_abonos(factura_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    abonos = db.query(AbonoCredito).filter(AbonoCredito.factura_id == factura_id).order_by(AbonoCredito.fecha.desc()).all()
    return [
        {
            "id": a.id,
            "fecha": a.fecha.strftime("%Y-%m-%d %H:%M"),
            "monto_usd": a.monto_usd,
            "monto_bs": a.monto_bs,
            "metodo_pago": a.metodo_pago,
            "nota": a.nota
        }
        for a in abonos
    ]

# ==========================================
# DESPACHOS (NOTAS DE ENTREGA)
# ==========================================
@app.get("/api/despachos/siguiente_numero")
def get_next_despacho_num(db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    last = db.query(Despacho).order_by(Despacho.id.desc()).first()
    try:
        next_num = str(int(last.numero) + 1) if last else "1"
    except:
        next_num = str((last.id if last else 0) + 1)
    return {"siguiente": next_num}

@app.post("/api/despachos")
def create_despacho(payload: DespachoCreate, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if not user.tiene_permiso("despachos"):
        raise HTTPException(status_code=403, detail="No tienes permiso para emitir notas de entrega")

    if not payload.items:
        raise HTTPException(status_code=400, detail="El despacho no contiene artículos")

    last = db.query(Despacho).order_by(Despacho.id.desc()).first()
    try:
        next_num = str(int(last.numero) + 1) if last else "1"
    except:
        next_num = str((last.id if last else 0) + 1)

    total_despacho = 0.0
    detalles = []

    for it in payload.items:
        articulo = db.query(Articulo).filter(Articulo.codigo == it.codigo_articulo).first()
        if not articulo:
            raise HTTPException(status_code=404, detail=f"Artículo {it.codigo_articulo} no encontrado")
        
        costo = it.costo_unitario or articulo.costo_final
        subtotal = round(it.cantidad * costo, 2)
        total_despacho += subtotal

        # Disminuir stock
        articulo.stock = round(articulo.stock - it.cantidad, 2)

        detalles.append(DetalleDespacho(
            codigo_articulo=articulo.codigo,
            nombre_articulo=articulo.nombre,
            cantidad=it.cantidad,
            costo_unitario=costo,
            subtotal=subtotal
        ))

    despacho = Despacho(
        numero=next_num,
        fecha=datetime.now(),
        destino_cliente=payload.destino_cliente.strip().upper(),
        direccion=(payload.direccion or "").strip(),
        total=round(total_despacho, 2),
        items=detalles
    )
    db.add(despacho)
    db.commit()
    db.refresh(despacho)

    return {"status": "ok", "despacho_id": despacho.id, "numero": despacho.numero, "total": despacho.total}

@app.get("/api/despachos")
def list_despachos(limit: int = 50, offset: int = 0, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if not user.tiene_permiso("despachos"):
        raise HTTPException(status_code=403, detail="No tienes permiso para consultar notas de entrega")
    return db.query(Despacho).order_by(Despacho.fecha.desc()).offset(offset).limit(limit).all()

# ==========================================
# COMPRAS / ENTRADA DE MERCANCÍA
# ==========================================
@app.post("/api/compras")
def create_compra(payload: CompraCreate, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    articulo = db.query(Articulo).filter(Articulo.codigo == payload.codigo_articulo).first()
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no registrado")

    costo_final = round(payload.costo + (payload.flete or 0.0), 2)
    rent = payload.rentabilidad or 20.0
    sugerido = round(costo_final + (costo_final * rent / 100.0) + (payload.mas or 0.0), 2)
    precio_final = payload.precio or sugerido

    # Actualizar artículo
    articulo.costo = payload.costo
    articulo.flete = payload.flete or 0.0
    articulo.costo_final = costo_final
    articulo.mas = payload.mas or 0.0
    articulo.rentabilidad = rent
    articulo.sugerido = sugerido
    articulo.precio = precio_final
    articulo.stock = round(articulo.stock + payload.cantidad, 2)

    # Registrar en compras
    compra = Compra(
        fecha=datetime.now(),
        codigo_articulo=articulo.codigo,
        nombre_articulo=articulo.nombre,
        cantidad=payload.cantidad,
        costo=payload.costo,
        flete=payload.flete or 0.0,
        mas=payload.mas or 0.0,
        rentabilidad=rent,
        precio=precio_final
    )
    db.add(compra)
    db.commit()
    db.refresh(compra)

    return {
        "status": "ok",
        "compra_id": compra.id,
        "articulo": articulo.nombre,
        "nuevo_stock": articulo.stock,
        "nuevo_precio": articulo.precio
    }

# ==========================================
# CONFIGURACIÓN Y TASA BCV
# ==========================================
@app.get("/api/configuracion")
def get_config(db: Session = Depends(get_db)):
    configs = db.query(Configuracion).all()
    return {c.clave: c.valor for c in configs}

@app.post("/api/configuracion/tasa_bcv")
def update_tasa_bcv(payload: TasaBCVUpdate, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if payload.tasa <= 0:
        raise HTTPException(status_code=400, detail="La tasa debe ser mayor a 0")
    
    cfg = db.query(Configuracion).filter_by(clave="tasa_bcv").first()
    if not cfg:
        cfg = Configuracion(clave="tasa_bcv", valor=str(round(payload.tasa, 2)))
        db.add(cfg)
    else:
        cfg.valor = str(round(payload.tasa, 2))
    db.commit()
    return {"status": "ok", "tasa_bcv": cfg.valor}

# ==========================================
# CONTROL DE CAJAS Y TURNOS
# ==========================================
def calcular_metricas_caja(caja: Caja, db: Session) -> Caja:
    facturas = db.query(Factura).filter(Factura.caja_id == caja.id).all()
    abonos = db.query(AbonoCredito).filter(AbonoCredito.caja_id == caja.id).all()
    
    ventas_efectivo = sum(f.efectivo or 0.0 for f in facturas)
    ventas_zelle = sum(f.zelle or 0.0 for f in facturas)
    ventas_pagomovil = sum(f.pagomovil or 0.0 for f in facturas)
    ventas_punto = sum(f.punto or 0.0 for f in facturas)
    ventas_credito = sum(f.credito or 0.0 for f in facturas)
    total_ventas = sum(f.total or 0.0 for f in facturas)
    
    abonos_efectivo = sum(a.monto_usd for a in abonos if (a.metodo_pago or "").lower() == 'efectivo')
    abonos_zelle = sum(a.monto_usd for a in abonos if (a.metodo_pago or "").lower() == 'zelle')
    abonos_pagomovil = sum(a.monto_usd for a in abonos if (a.metodo_pago or "").lower() == 'pagomovil')
    abonos_punto = sum(a.monto_usd for a in abonos if (a.metodo_pago or "").lower() == 'punto')
    total_abonos = sum(a.monto_usd for a in abonos)
    
    caja.ventas_efectivo = round(ventas_efectivo, 2)
    caja.ventas_zelle = round(ventas_zelle, 2)
    caja.ventas_pagomovil = round(ventas_pagomovil, 2)
    caja.ventas_punto = round(ventas_punto, 2)
    caja.ventas_credito = round(ventas_credito, 2)
    caja.total_ventas = round(total_ventas, 2)
    
    caja.abonos_efectivo = round(abonos_efectivo, 2)
    caja.abonos_zelle = round(abonos_zelle, 2)
    caja.abonos_pagomovil = round(abonos_pagomovil, 2)
    caja.abonos_punto = round(abonos_punto, 2)
    caja.total_abonos = round(total_abonos, 2)
    
    caja.total_esperado_efectivo = round((caja.monto_apertura_usd or 0.0) + caja.ventas_efectivo + caja.abonos_efectivo, 2)
    caja.total_esperado_general = round((caja.monto_apertura_usd or 0.0) + (caja.total_ventas - caja.ventas_credito) + caja.total_abonos, 2)
    return caja

def serializar_caja(caja: Caja, db: Session, detalle: bool = False):
    caja = calcular_metricas_caja(caja, db)
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    
    res = {
        "id": caja.id,
        "numero": caja.numero,
        "estado": caja.estado,
        "fecha_apertura": caja.fecha_apertura.strftime("%d/%m/%Y %I:%M %p") if caja.fecha_apertura else "",
        "fecha_cierre": caja.fecha_cierre.strftime("%d/%m/%Y %I:%M %p") if caja.fecha_cierre else "",
        "usuario_apertura_id": caja.usuario_apertura_id,
        "usuario_apertura_nombre": caja.usuario_apertura_nombre or "Administrador",
        "usuario_cierre_id": caja.usuario_cierre_id,
        "usuario_cierre_nombre": caja.usuario_cierre_nombre or "",
        "monto_apertura_usd": caja.monto_apertura_usd or 0.0,
        "monto_apertura_bs": caja.monto_apertura_bs or 0.0,
        "tasa_bcv_apertura": caja.tasa_bcv_apertura or 1.0,
        "tasa_bcv_cierre": caja.tasa_bcv_cierre or tasa_bcv,
        
        "ventas_efectivo": caja.ventas_efectivo or 0.0,
        "ventas_zelle": caja.ventas_zelle or 0.0,
        "ventas_pagomovil": caja.ventas_pagomovil or 0.0,
        "ventas_punto": caja.ventas_punto or 0.0,
        "ventas_credito": caja.ventas_credito or 0.0,
        "total_ventas": caja.total_ventas or 0.0,
        
        "abonos_efectivo": caja.abonos_efectivo or 0.0,
        "abonos_zelle": caja.abonos_zelle or 0.0,
        "abonos_pagomovil": caja.abonos_pagomovil or 0.0,
        "abonos_punto": caja.abonos_punto or 0.0,
        "total_abonos": caja.total_abonos or 0.0,
        
        "total_esperado_efectivo": caja.total_esperado_efectivo or 0.0,
        "total_esperado_general": caja.total_esperado_general or 0.0,
        
        "declarado_efectivo": caja.declarado_efectivo or 0.0,
        "declarado_zelle": caja.declarado_zelle or 0.0,
        "declarado_pagomovil": caja.declarado_pagomovil or 0.0,
        "declarado_punto": caja.declarado_punto or 0.0,
        "total_declarado": caja.total_declarado or 0.0,
        
        "diferencia_efectivo": caja.diferencia_efectivo or 0.0,
        "diferencia_general": caja.diferencia_general or 0.0,
        
        "observaciones_apertura": caja.observaciones_apertura or "",
        "observaciones_cierre": caja.observaciones_cierre or ""
    }
    
    if detalle:
        facturas = db.query(Factura).filter(Factura.caja_id == caja.id).order_by(Factura.fecha.desc()).all()
        abonos = db.query(AbonoCredito).filter(AbonoCredito.caja_id == caja.id).order_by(AbonoCredito.fecha.desc()).all()
        res["facturas"] = [
            {
                "id": f.id,
                "numero": f.numero,
                "cliente": f.cliente_nombre,
                "total": f.total,
                "condicion": f.condicion,
                "hora": f.fecha.strftime("%I:%M %p") if f.fecha else ""
            } for f in facturas
        ]
        res["abonos_lista"] = [
            {
                "id": a.id,
                "factura_id": a.factura_id,
                "monto_usd": a.monto_usd,
                "metodo_pago": a.metodo_pago,
                "hora": a.fecha.strftime("%I:%M %p") if a.fecha else ""
            } for a in abonos
        ]
    return res

@app.get("/api/cajas/estado")
def get_caja_estado(db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    caja = db.query(Caja).filter(Caja.estado == "abierta").order_by(Caja.id.desc()).first()
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    if not caja:
        return {"activa": False, "caja": None, "tasa_bcv": tasa_bcv}
    return {"activa": True, "caja": serializar_caja(caja, db, detalle=True), "tasa_bcv": tasa_bcv}

@app.post("/api/cajas/abrir")
def abrir_caja(payload: CajaApertura, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if not user.tiene_permiso("cajas") and not user.tiene_permiso("pos"):
        raise HTTPException(status_code=403, detail="No tienes permiso para abrir caja")

    caja_activa = db.query(Caja).filter(Caja.estado == "abierta").first()
    if caja_activa:
        raise HTTPException(status_code=400, detail=f"Ya existe una caja abierta (#{caja_activa.numero}). Debe cerrarla antes de abrir una nueva.")
    
    last_caja = db.query(Caja).order_by(Caja.id.desc()).first()
    nuevo_num = (last_caja.numero + 1) if (last_caja and last_caja.numero) else 1
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    
    monto_usd = round(payload.monto_apertura_usd or 0.0, 2)
    monto_bs = payload.monto_apertura_bs if (payload.monto_apertura_bs and payload.monto_apertura_bs > 0) else round(monto_usd * tasa_bcv, 2)
    
    nueva_caja = Caja(
        numero=nuevo_num,
        estado="abierta",
        fecha_apertura=datetime.now(),
        usuario_apertura_id=user.id,
        usuario_apertura_nombre=user.nombre,
        monto_apertura_usd=monto_usd,
        monto_apertura_bs=monto_bs,
        tasa_bcv_apertura=tasa_bcv,
        observaciones_apertura=(payload.observaciones or "").strip(),
        total_esperado_efectivo=monto_usd,
        total_esperado_general=monto_usd
    )
    db.add(nueva_caja)
    db.commit()
    db.refresh(nueva_caja)
    return {"status": "ok", "caja": serializar_caja(nueva_caja, db)}

@app.post("/api/cajas/cerrar")
def cerrar_caja(payload: CajaCierre, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if not user.tiene_permiso("cajas") and not user.tiene_permiso("pos"):
        raise HTTPException(status_code=403, detail="No tienes permiso para cerrar caja")

    caja = db.query(Caja).filter(Caja.estado == "abierta").order_by(Caja.id.desc()).first()
    if not caja:
        raise HTTPException(status_code=400, detail="No hay ninguna caja abierta actualmente para cerrar")
    
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    caja = calcular_metricas_caja(caja, db)
    
    dec_ef = round(payload.declarado_efectivo or 0.0, 2)
    dec_zelle = round(payload.declarado_zelle or 0.0, 2)
    dec_pm = round(payload.declarado_pagomovil or 0.0, 2)
    dec_punto = round(payload.declarado_punto or 0.0, 2)
    total_dec = round(dec_ef + dec_zelle + dec_pm + dec_punto, 2)
    
    dif_efectivo = round(dec_ef - (caja.total_esperado_efectivo or 0.0), 2)
    dif_general = round(total_dec - (caja.total_esperado_general or 0.0), 2)
    
    caja.estado = "cerrada"
    caja.fecha_cierre = datetime.now()
    caja.usuario_cierre_id = user.id
    caja.usuario_cierre_nombre = user.nombre
    caja.tasa_bcv_cierre = tasa_bcv
    caja.declarado_efectivo = dec_ef
    caja.declarado_zelle = dec_zelle
    caja.declarado_pagomovil = dec_pm
    caja.declarado_punto = dec_punto
    caja.total_declarado = total_dec
    caja.diferencia_efectivo = dif_efectivo
    caja.diferencia_general = dif_general
    caja.observaciones_cierre = (payload.observaciones or "").strip()
    
    db.commit()
    db.refresh(caja)
    return {"status": "ok", "caja": serializar_caja(caja, db, detalle=True)}

@app.get("/api/cajas")
def listar_cajas(limit: int = 50, offset: int = 0, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    cajas = db.query(Caja).order_by(Caja.id.desc()).offset(offset).limit(limit).all()
    return [serializar_caja(c, db) for c in cajas]

@app.get("/api/cajas/{caja_id}")
def obtener_caja_detalle(caja_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    caja = db.query(Caja).filter(Caja.id == caja_id).first()
    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada")
    return serializar_caja(caja, db, detalle=True)

# ==========================================
# REPORTES Y ESTADÍSTICAS GERENCIALES
# ==========================================
def parse_date_range(desde: Optional[str], hasta: Optional[str]):
    try:
        dt_inicio = datetime.strptime(desde, "%Y-%m-%d") if desde else datetime.combine(date.today() - timedelta(days=30), datetime.min.time())
    except:
        dt_inicio = datetime.combine(date.today() - timedelta(days=30), datetime.min.time())
        
    try:
        dt_fin = datetime.strptime(hasta, "%Y-%m-%d") + timedelta(days=1, microseconds=-1) if hasta else datetime.combine(date.today(), datetime.max.time())
    except:
        dt_fin = datetime.combine(date.today(), datetime.max.time())
    return dt_inicio, dt_fin

# 1. Reporte de Ventas
@app.get("/api/reportes/ventas")
def get_reporte_ventas(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    condicion: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    if not user.tiene_permiso("reportes"):
        raise HTTPException(status_code=403, detail="No tiene permisos para ver reportes")
    dt_inicio, dt_fin = parse_date_range(desde, hasta)
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    
    q = db.query(Factura).filter(Factura.fecha >= dt_inicio, Factura.fecha <= dt_fin)
    if condicion and condicion in ["contado", "credito"]:
        q = q.filter(Factura.condicion == condicion)
    facturas = q.order_by(Factura.fecha.desc()).all()
    
    total_usd = sum(f.total for f in facturas)
    total_contado = sum(f.total for f in facturas if f.condicion == "contado")
    total_credito = sum(f.total for f in facturas if f.condicion == "credito")
    
    efectivo = sum(f.efectivo or 0.0 for f in facturas)
    zelle = sum(f.zelle or 0.0 for f in facturas)
    pagomovil = sum(f.pagomovil or 0.0 for f in facturas)
    punto = sum(f.punto or 0.0 for f in facturas)
    credito = sum(f.credito or 0.0 for f in facturas)
    
    cant = len(facturas)
    ticket_promedio = round(total_usd / cant, 2) if cant > 0 else 0.0
    
    factura_ids = [f.id for f in facturas]
    top_prods = []
    if factura_ids:
        rows = (
            db.query(
                DetalleFactura.codigo_articulo,
                DetalleFactura.nombre_articulo,
                func.sum(DetalleFactura.cantidad).label("total_cant"),
                func.sum(DetalleFactura.subtotal).label("total_subt")
            )
            .filter(DetalleFactura.factura_id.in_(factura_ids))
            .group_by(DetalleFactura.codigo_articulo, DetalleFactura.nombre_articulo)
            .order_by(desc("total_cant"))
            .limit(10)
            .all()
        )
        top_prods = [
            {
                "codigo": r[0],
                "nombre": r[1],
                "cantidad": round(r[2], 2),
                "total_usd": round(r[3], 2)
            }
            for r in rows
        ]
    
    usuarios_map = {u.id: u.nombre for u in db.query(Usuario).all()}
    cajero_ventas = {}
    for f in facturas:
        uid = f.usuario_id or 0
        unom = usuarios_map.get(uid, "Desconocido")
        if unom not in cajero_ventas:
            cajero_ventas[unom] = {"nombre": unom, "facturas": 0, "total_usd": 0.0}
        cajero_ventas[unom]["facturas"] += 1
        cajero_ventas[unom]["total_usd"] = round(cajero_ventas[unom]["total_usd"] + f.total, 2)
    
    return {
        "periodo": {
            "desde": dt_inicio.strftime("%d/%m/%Y"),
            "hasta": dt_fin.strftime("%d/%m/%Y")
        },
        "totales": {
            "total_usd": round(total_usd, 2),
            "total_bs": round(total_usd * tasa_bcv, 2),
            "total_contado_usd": round(total_contado, 2),
            "total_credito_usd": round(total_credito, 2),
            "cantidad_facturas": cant,
            "ticket_promedio_usd": ticket_promedio
        },
        "desglose_pagos": {
            "efectivo": round(efectivo, 2),
            "zelle": round(zelle, 2),
            "pagomovil": round(pagomovil, 2),
            "punto": round(punto, 2),
            "credito": round(credito, 2)
        },
        "top_productos": top_prods,
        "ventas_por_cajero": list(cajero_ventas.values()),
        "facturas_recientes": [
            {
                "numero": f.numero,
                "fecha": f.fecha.strftime("%d/%m/%Y %I:%M %p") if f.fecha else "",
                "cliente": f.cliente_nombre,
                "condicion": f.condicion,
                "total": f.total
            }
            for f in facturas[:50]
        ]
    }

# 2. Reporte de Compras
@app.get("/api/reportes/compras")
def get_reporte_compras(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    if not user.tiene_permiso("reportes"):
        raise HTTPException(status_code=403, detail="No tiene permisos para ver reportes")
    dt_inicio, dt_fin = parse_date_range(desde, hasta)
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    
    compras = db.query(Compra).filter(Compra.fecha >= dt_inicio, Compra.fecha <= dt_fin).order_by(Compra.fecha.desc()).all()
    total_invertido = sum((c.cantidad * c.costo) for c in compras)
    total_unidades = sum(c.cantidad for c in compras)
    
    return {
        "periodo": {
            "desde": dt_inicio.strftime("%d/%m/%Y"),
            "hasta": dt_fin.strftime("%d/%m/%Y")
        },
        "totales": {
            "total_invertido_usd": round(total_invertido, 2),
            "total_invertido_bs": round(total_invertido * tasa_bcv, 2),
            "cantidad_compras": len(compras),
            "total_unidades": round(total_unidades, 2)
        },
        "compras": [
            {
                "id": c.id,
                "fecha": c.fecha.strftime("%d/%m/%Y %I:%M %p") if c.fecha else "",
                "codigo": c.codigo_articulo,
                "nombre": c.nombre_articulo,
                "cantidad": c.cantidad,
                "costo": c.costo,
                "subtotal": round(c.cantidad * c.costo, 2)
            }
            for c in compras
        ]
    }

# 3. Reporte de Inventario
@app.get("/api/reportes/inventario")
def get_reporte_inventario(
    filtro: Optional[str] = "todos",
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    if not user.tiene_permiso("reportes"):
        raise HTTPException(status_code=403, detail="No tiene permisos para ver reportes")
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    articulos = db.query(Articulo).filter(Articulo.activo == True).order_by(Articulo.nombre.asc()).all()
    
    total_costo = sum(a.stock * a.costo_final for a in articulos if a.stock > 0)
    total_pvp = sum(a.stock * a.precio for a in articulos if a.stock > 0)
    ganancia_potencial = total_pvp - total_costo
    margen_pct = round((ganancia_potencial / total_costo * 100), 2) if total_costo > 0 else 0.0
    
    criticos = [a for a in articulos if a.stock <= (a.stock_alerta if a.stock_alerta is not None else 5.0) and a.stock > 0]
    agotados = [a for a in articulos if a.stock <= 0]
    
    items_filtrados = articulos
    if filtro == "alerta":
        items_filtrados = criticos
    elif filtro == "agotados":
        items_filtrados = agotados
    elif filtro == "con_stock":
        items_filtrados = [a for a in articulos if a.stock > 0]
    
    return {
        "totales": {
            "patrimonio_costo_usd": round(total_costo, 2),
            "patrimonio_costo_bs": round(total_costo * tasa_bcv, 2),
            "patrimonio_pvp_usd": round(total_pvp, 2),
            "patrimonio_pvp_bs": round(total_pvp * tasa_bcv, 2),
            "ganancia_proyectada_usd": round(ganancia_potencial, 2),
            "margen_proyectado_pct": margen_pct,
            "total_productos": len(articulos),
            "productos_alerta": len(criticos),
            "productos_agotados": len(agotados)
        },
        "articulos": [
            {
                "codigo": a.codigo,
                "nombre": a.nombre,
                "categoria": a.categoria,
                "stock": a.stock,
                "stock_alerta": a.stock_alerta,
                "costo_final": a.costo_final,
                "precio": a.precio,
                "valoracion_costo": round(a.stock * a.costo_final, 2) if a.stock > 0 else 0.0
            }
            for a in items_filtrados
        ]
    }

# 3.1. Reporte de Stock por Acabarse (Alerta de Stock personalizada)
@app.get("/api/reportes/stock-alerta")
def get_reporte_stock_alerta(
    filtro: Optional[str] = "todos",
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    if not user.tiene_permiso("reportes") and not user.tiene_permiso("inventario"):
        raise HTTPException(status_code=403, detail="No tiene permisos para ver reportes de inventario")
    
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    articulos = db.query(Articulo).filter(Articulo.activo == True).order_by(Articulo.nombre.asc()).all()
    
    items_alerta = []
    total_agotados = 0
    total_por_acabarse = 0
    inversion_reposicion_usd = 0.0

    for a in articulos:
        limite_alerta = a.stock_alerta if a.stock_alerta is not None else 5.0
        if a.stock <= limite_alerta:
            es_agotado = (a.stock <= 0)
            if es_agotado:
                total_agotados += 1
            else:
                total_por_acabarse += 1
                
            deficit = max(0.0, limite_alerta - a.stock)
            costo_unit = a.costo_final or a.costo or 0.0
            costo_rep_usd = round(deficit * costo_unit, 2)
            inversion_reposicion_usd += costo_rep_usd
            
            estado_texto = "Agotado" if es_agotado else "Por acabarse"
            
            items_alerta.append({
                "codigo": a.codigo,
                "nombre": a.nombre,
                "categoria": a.categoria or "GENERAL",
                "marca": a.marca or "",
                "proveedor": a.proveedor or "",
                "stock": round(a.stock, 2) if a.stock is not None else 0.0,
                "stock_alerta": round(limite_alerta, 2),
                "deficit": round(deficit, 2),
                "costo_final": costo_unit,
                "precio": a.precio or 0.0,
                "costo_reposicion_usd": costo_rep_usd,
                "costo_reposicion_bs": round(costo_rep_usd * tasa_bcv, 2),
                "estado": estado_texto,
                "es_agotado": es_agotado
            })

    if filtro == "agotados":
        filtrados = [i for i in items_alerta if i["es_agotado"]]
    elif filtro == "por_acabarse":
        filtrados = [i for i in items_alerta if not i["es_agotado"]]
    else:
        filtrados = items_alerta

    # Ordenar: agotados primero, luego por menor stock
    filtrados.sort(key=lambda x: (0 if x["es_agotado"] else 1, x["stock"]))

    return {
        "totales": {
            "total_articulos_alerta": len(items_alerta),
            "total_agotados": total_agotados,
            "total_por_acabarse": total_por_acabarse,
            "inversion_reposicion_usd": round(inversion_reposicion_usd, 2),
            "inversion_reposicion_bs": round(inversion_reposicion_usd * tasa_bcv, 2)
        },
        "articulos": filtrados
    }

# 4. Reporte de Cajas
@app.get("/api/reportes/cajas")
def get_reporte_cajas_consolidado(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    if not user.tiene_permiso("reportes"):
        raise HTTPException(status_code=403, detail="No tiene permisos para ver reportes")
    dt_inicio, dt_fin = parse_date_range(desde, hasta)
    cajas = db.query(Caja).filter(Caja.fecha_apertura >= dt_inicio, Caja.fecha_apertura <= dt_fin).order_by(Caja.id.desc()).all()
    
    cajas_serializadas = [serializar_caja(c, db) for c in cajas]
    total_ingresos = sum(c["total_ventas"] for c in cajas_serializadas)
    total_abonos = sum(c["total_abonos"] for c in cajas_serializadas)
    total_efectivo = sum(c["ventas_efectivo"] + c["abonos_efectivo"] for c in cajas_serializadas)
    total_diferencias = sum(c["diferencia_efectivo"] for c in cajas_serializadas if c["estado"] == "cerrada")
    
    return {
        "periodo": {
            "desde": dt_inicio.strftime("%d/%m/%Y"),
            "hasta": dt_fin.strftime("%d/%m/%Y")
        },
        "totales": {
            "cantidad_cajas": len(cajas),
            "total_ventas_usd": round(total_ingresos, 2),
            "total_abonos_usd": round(total_abonos, 2),
            "total_efectivo_usd": round(total_efectivo, 2),
            "total_diferencias_usd": round(total_diferencias, 2)
        },
        "cajas": cajas_serializadas
    }

# 5. Reporte de Cobranza (Cuentas por Cobrar)
@app.get("/api/reportes/cobranza")
def get_reporte_cobranza(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    if not user.tiene_permiso("reportes"):
        raise HTTPException(status_code=403, detail="No tiene permisos para ver reportes")
    dt_inicio, dt_fin = parse_date_range(desde, hasta)
    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))
    now = datetime.now()
    
    facturas_pendientes = db.query(Factura).filter(Factura.condicion == "credito", Factura.saldo_pendiente > 0).all()
    cartera_total = sum(f.saldo_pendiente for f in facturas_pendientes)
    cartera_vencida = sum(f.saldo_pendiente for f in facturas_pendientes if f.fecha_vencimiento and f.fecha_vencimiento < now)
    cartera_vigente = cartera_total - cartera_vencida
    
    deudores_dict = {}
    for f in facturas_pendientes:
        nom = f.cliente_nombre or "CLIENTE"
        if nom not in deudores_dict:
            deudores_dict[nom] = {
                "cliente": nom,
                "saldo_total": 0.0,
                "facturas_count": 0,
                "vencidas_count": 0
            }
        deudores_dict[nom]["saldo_total"] = round(deudores_dict[nom]["saldo_total"] + f.saldo_pendiente, 2)
        deudores_dict[nom]["facturas_count"] += 1
        if f.fecha_vencimiento and f.fecha_vencimiento < now:
            deudores_dict[nom]["vencidas_count"] += 1
            
    abonos = db.query(AbonoCredito).filter(AbonoCredito.fecha >= dt_inicio, AbonoCredito.fecha <= dt_fin).order_by(AbonoCredito.fecha.desc()).all()
    total_abonos_periodo = sum(a.monto_usd for a in abonos)
    
    facturas_dict = {f.id: f for f in db.query(Factura).filter(Factura.id.in_([a.factura_id for a in abonos])).all()} if abonos else {}
    
    return {
        "periodo": {
            "desde": dt_inicio.strftime("%d/%m/%Y"),
            "hasta": dt_fin.strftime("%d/%m/%Y")
        },
        "totales": {
            "cartera_total_usd": round(cartera_total, 2),
            "cartera_total_bs": round(cartera_total * tasa_bcv, 2),
            "cartera_vencida_usd": round(cartera_vencida, 2),
            "cartera_vigente_usd": round(cartera_vigente, 2),
            "total_abonos_periodo_usd": round(total_abonos_periodo, 2),
            "clientes_deudores_count": len(deudores_dict)
        },
        "clientes_deudores": sorted(list(deudores_dict.values()), key=lambda x: x["saldo_total"], reverse=True),
        "abonos_periodo": [
            {
                "id": a.id,
                "fecha": a.fecha.strftime("%d/%m/%Y %I:%M %p") if a.fecha else "",
                "factura_num": facturas_dict[a.factura_id].numero if a.factura_id in facturas_dict else str(a.factura_id),
                "cliente": facturas_dict[a.factura_id].cliente_nombre if a.factura_id in facturas_dict else "",
                "monto_usd": a.monto_usd,
                "monto_bs": a.monto_bs,
                "metodo_pago": a.metodo_pago,
                "nota": a.nota
            }
            for a in abonos
        ]
    }

# Compatibilidad para widgets existentes
@app.get("/api/reportes/resumen")
def get_reporte_resumen(db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    today_start = datetime.combine(date.today(), datetime.min.time())
    
    facturas_hoy = db.query(Factura).filter(Factura.fecha >= today_start).all()
    total_hoy = sum(f.total for f in facturas_hoy)
    efectivo_hoy = sum(f.efectivo for f in facturas_hoy)
    zelle_hoy = sum(f.zelle for f in facturas_hoy)
    pagomovil_hoy = sum(f.pagomovil for f in facturas_hoy)
    punto_hoy = sum(f.punto for f in facturas_hoy)
    credito_hoy = sum(f.credito for f in facturas_hoy)

    articulos = db.query(Articulo).filter(Articulo.activo == True).all()
    total_articulos = len(articulos)
    bajo_stock = sum(1 for a in articulos if a.stock <= (a.stock_alerta if a.stock_alerta is not None else 5.0))
    patrimonio_total = sum(a.stock * a.costo_final for a in articulos if a.stock > 0)

    tasa_bcv = float(get_config_val(db, "tasa_bcv", "473.92"))

    return {
        "ventas_hoy": {
            "cantidad_facturas": len(facturas_hoy),
            "total_usd": round(total_hoy, 2),
            "total_bs": round(total_hoy * tasa_bcv, 2),
            "efectivo": round(efectivo_hoy, 2),
            "zelle": round(zelle_hoy, 2),
            "pagomovil": round(pagomovil_hoy, 2),
            "punto": round(punto_hoy, 2),
            "credito": round(credito_hoy, 2)
        },
        "inventario": {
            "total_productos": total_articulos,
            "bajo_stock": bajo_stock,
            "patrimonio_usd": round(patrimonio_total, 2),
            "patrimonio_bs": round(patrimonio_total * tasa_bcv, 2)
        },
        "tasa_bcv": tasa_bcv
    }


# ==========================================
# GESTIÓN DE USUARIOS Y PERMISOS
# ==========================================
@app.get("/api/usuarios")
def list_usuarios(db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if not user.tiene_permiso("usuarios"):
        raise HTTPException(status_code=403, detail="No tiene permisos para administrar usuarios")
    usuarios = db.query(Usuario).order_by(Usuario.id.asc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "nombre": u.nombre,
            "rol": u.rol,
            "activo": u.activo,
            "permisos": u.lista_permisos,
            "creado_en": u.creado_en.strftime("%d/%m/%Y %H:%M") if u.creado_en else ""
        }
        for u in usuarios
    ]

@app.post("/api/usuarios")
def create_usuario(payload: UsuarioCreate, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if not user.tiene_permiso("usuarios"):
        raise HTTPException(status_code=403, detail="No tiene permisos para administrar usuarios")
    
    clean_username = payload.username.strip().lower()
    if len(clean_username) < 3:
        raise HTTPException(status_code=400, detail="El nombre de usuario debe tener al menos 3 caracteres")
    if len(payload.password) < 4:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 4 caracteres")
    
    existe = db.query(Usuario).filter(Usuario.username == clean_username).first()
    if existe:
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está registrado")
    
    permisos_str = "*"
    if payload.permisos is not None and payload.rol != "admin":
        permisos_str = json.dumps(payload.permisos)

    nuevo = Usuario(
        username=clean_username,
        nombre=payload.nombre.strip(),
        password_hash=hash_password(payload.password),
        rol=payload.rol or "cajero",
        activo=payload.activo if payload.activo is not None else True,
        permisos=permisos_str
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {"status": "ok", "id": nuevo.id, "mensaje": "Usuario creado exitosamente"}

@app.put("/api/usuarios/{id}")
def update_usuario(id: int, payload: UsuarioUpdate, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if not user.tiene_permiso("usuarios"):
        raise HTTPException(status_code=403, detail="No tiene permisos para administrar usuarios")
    
    u = db.query(Usuario).filter(Usuario.id == id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.id == u.id and payload.activo is False:
        raise HTTPException(status_code=400, detail="No puede desactivar su propio usuario")
    
    if u.rol == "admin" and (payload.rol == "cajero" or payload.activo is False):
        total_admins = db.query(Usuario).filter(Usuario.rol == "admin", Usuario.activo == True).count()
        if total_admins <= 1:
            raise HTTPException(status_code=400, detail="Debe existir al menos un administrador activo en el sistema")

    if payload.nombre is not None and payload.nombre.strip():
        u.nombre = payload.nombre.strip()
    if payload.rol is not None:
        u.rol = payload.rol
    if payload.activo is not None:
        u.activo = payload.activo
    if payload.password and len(payload.password.strip()) >= 4:
        u.password_hash = hash_password(payload.password.strip())
    
    if payload.permisos is not None:
        u.permisos = "*" if u.rol == "admin" else json.dumps(payload.permisos)

    db.commit()
    return {"status": "ok", "mensaje": "Usuario actualizado exitosamente"}

@app.delete("/api/usuarios/{id}")
def delete_usuario(id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    if not user.tiene_permiso("usuarios"):
        raise HTTPException(status_code=403, detail="No tiene permisos para administrar usuarios")
    
    u = db.query(Usuario).filter(Usuario.id == id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.id == u.id:
        raise HTTPException(status_code=400, detail="No puede eliminar su propia cuenta")
    if u.rol == "admin":
        total_admins = db.query(Usuario).filter(Usuario.rol == "admin", Usuario.activo == True).count()
        if total_admins <= 1:
            raise HTTPException(status_code=400, detail="No se puede eliminar el único administrador activo")
    
    db.delete(u)
    db.commit()
    return {"status": "ok", "mensaje": "Usuario eliminado exitosamente"}

# ==========================================
# RUTAS DE PÁGINAS HTML (INTERFAZ WEB)
# ==========================================
def get_user_first_allowed_url(user: Usuario) -> str:
    modulo_urls = [
        ("pos", "/"),
        ("cajas", "/cajas"),
        ("inventario", "/inventario"),
        ("compras", "/compras"),
        ("despachos", "/despachos"),
        ("creditos", "/creditos"),
        ("historial", "/historial"),
        ("clientes", "/clientes"),
        ("reportes", "/reportes"),
        ("mantenimiento", "/mantenimiento"),
        ("usuarios", "/usuarios"),
    ]
    for mod, url in modulo_urls:
        if user.tiene_permiso(mod):
            return url
    return "/"

@app.get("/login", response_class=HTMLResponse)
def page_login(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/propuesta", response_class=HTMLResponse)
@app.get("/presentacion", response_class=HTMLResponse)
def page_propuesta_comercial(request: Request, user: Optional[Usuario] = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="propuesta.html", context={"user": user})

@app.get("/descargar-informe-pdf")
@app.get("/informe-actualizaciones.pdf")
def descargar_informe_actualizaciones_pdf():
    pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Informe_Actualizaciones_Prolago_2026.pdf")
    if not os.path.exists(pdf_path):
        try:
            from generar_pdf_reporte import generar_pdf
            generar_pdf(pdf_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"No se pudo generar el PDF: {e}")
    return FileResponse(
        path=pdf_path,
        filename="Informe_Actualizaciones_Prolago_2026.pdf",
        media_type="application/pdf"
    )

@app.get("/", response_class=HTMLResponse)
def page_pos(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("pos"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="pos.html", context={"user": user})

@app.get("/cajas", response_class=HTMLResponse)
def page_cajas(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("cajas"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="cajas.html", context={"user": user})

@app.get("/inventario", response_class=HTMLResponse)
def page_inventario(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("inventario"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="articulos.html", context={"user": user})

@app.get("/compras", response_class=HTMLResponse)
def page_compras(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("compras"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="compras.html", context={"user": user})

@app.get("/despachos", response_class=HTMLResponse)
def page_despachos(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("despachos"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="despachos.html", context={"user": user})

@app.get("/historial", response_class=HTMLResponse)
def page_historial(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("historial"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="historial.html", context={"user": user})

@app.get("/clientes", response_class=HTMLResponse)
def page_clientes(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("clientes"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="clientes.html", context={"user": user})

@app.get("/reportes", response_class=HTMLResponse)
def page_reportes(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("reportes"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="reportes.html", context={"user": user})

@app.get("/creditos", response_class=HTMLResponse)
def page_creditos(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("creditos"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="creditos.html", context={"user": user})

@app.get("/usuarios", response_class=HTMLResponse)
def page_usuarios(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("usuarios"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="usuarios.html", context={"user": user})

# ==========================================
# MANTENIMIENTO, DIAGNÓSTICO Y RESPALDOS
# ==========================================
import socket
import sqlite3
import shutil

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def crear_autobackup_diario():
    try:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else "."
        db_file = os.path.join(base_dir, "prolago.db")
        if not os.path.exists(db_file):
            return
        backup_dir = os.path.join(base_dir, "respaldos")
        os.makedirs(backup_dir, exist_ok=True)
        hoy_str = datetime.now().strftime("%Y-%m-%d")
        dest = os.path.join(backup_dir, f"prolago_autobackup_{hoy_str}.db")
        if not os.path.exists(dest):
            shutil.copy2(db_file, dest)
    except Exception:
        pass

crear_autobackup_diario()

@app.get("/mantenimiento", response_class=HTMLResponse)
def page_mantenimiento(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.tiene_permiso("mantenimiento"):
        return RedirectResponse(url=get_user_first_allowed_url(user))
    return templates.TemplateResponse(request=request, name="mantenimiento.html", context={"user": user})

@app.get("/api/mantenimiento/diagnostico")
def get_diagnostico(db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else "."
    db_file = os.path.join(base_dir, "prolago.db")
    backup_dir = os.path.join(base_dir, "respaldos")

    integrity = "OK"
    db_size_kb = 0
    if os.path.exists(db_file):
        db_size_kb = round(os.path.getsize(db_file) / 1024, 2)
        try:
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            res = cur.fetchall()
            integrity = res[0][0] if res else "UNKNOWN"
            conn.close()
        except Exception as e:
            integrity = f"ERROR: {str(e)}"

    total_arts = db.query(Articulo).count()
    total_facts = db.query(Factura).count()
    total_clis = db.query(Cliente).count()
    tasa = get_config_val(db, "tasa_bcv", "473.92")

    # Contar respaldos automáticos existentes
    cant_respaldos = 0
    if os.path.exists(backup_dir):
        cant_respaldos = len([f for f in os.listdir(backup_dir) if f.endswith(".db")])

    return {
        "estado_sistema": "OPERATIVO",
        "integridad_db": integrity,
        "tamano_db_kb": db_size_kb,
        "articulos_activos": total_arts,
        "facturas_emitidas": total_facts,
        "clientes_registrados": total_clis,
        "tasa_bcv": tasa,
        "respaldos_guardados": cant_respaldos,
        "ip_local": get_lan_ip(),
        "puerto": 8000,
        "fecha_servidor": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.post("/api/mantenimiento/optimizar")
def optimizar_sistema(db: Session = Depends(get_db), user: Usuario = Depends(require_admin)):
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else "."
    db_file = os.path.join(base_dir, "prolago.db")

    Base.metadata.create_all(bind=engine)

    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("VACUUM;")
            cur.execute("PRAGMA optimize;")
            conn.commit()
            conn.close()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al optimizar: {str(e)}")

    return {"status": "ok", "mensaje": "Base de datos optimizada, compactada y verificada exitosamente"}

@app.get("/api/mantenimiento/descargar_backup")
def descargar_backup(user: Usuario = Depends(require_admin)):
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else "."
    db_file = os.path.join(base_dir, "prolago.db")
    if not os.path.exists(db_file):
        raise HTTPException(status_code=404, detail="Archivo de base de datos no encontrado")

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(base_dir, "respaldos")
    os.makedirs(backup_dir, exist_ok=True)
    
    # Guardar copia local en la carpeta 'respaldos'
    try:
        shutil.copy2(db_file, os.path.join(backup_dir, f"prolago_respaldo_{fecha}.db"))
    except Exception:
        pass

    filename = f"COPIA_SEGURIDAD_PROLAGO_{fecha}.db"
    return FileResponse(path=db_file, filename=filename, media_type="application/octet-stream")

@app.post("/api/mantenimiento/restaurar_backup")
async def restaurar_backup(archivo: UploadFile = File(...), user: Usuario = Depends(require_admin)):
    if not archivo.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="El archivo debe tener extensión .db")

    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else "."
    db_file = os.path.join(base_dir, "prolago.db")
    backup_dir = os.path.join(base_dir, "respaldos")
    os.makedirs(backup_dir, exist_ok=True)

    # 1. Guardar archivo subido en temporal para verificar integridad antes de tocar la BD real
    temp_path = os.path.join(backup_dir, "temp_restore.db")
    with open(temp_path, "wb") as f:
        content = await archivo.read()
        f.write(content)

    # 2. Validar que sea un archivo SQLite íntegro
    cant_arts = 0
    cant_facts = 0
    try:
        test_conn = sqlite3.connect(temp_path)
        cur = test_conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        check_res = cur.fetchall()
        
        cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='articulos';")
        if cur.fetchone()[0]:
            cur.execute("SELECT count(*) FROM articulos;")
            cant_arts = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='facturas';")
        if cur.fetchone()[0]:
            cur.execute("SELECT count(*) FROM facturas;")
            cant_facts = cur.fetchone()[0]

        test_conn.close()

        if not check_res or check_res[0][0].lower() != "ok":
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(status_code=400, detail="El archivo está dañado o no es una base de datos válida.")
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=400, detail=f"Error al validar archivo de respaldo: {str(e)}")

    # 3. Liberar conexiones de SQLAlchemy en Windows para evitar bloqueos
    engine.dispose()

    # 4. Guardar copia de seguridad preventiva de la BD que se va a reemplazar
    if os.path.exists(db_file):
        fecha_seg = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            shutil.copy2(db_file, os.path.join(backup_dir, f"prolago_reemplazada_{fecha_seg}.db"))
        except Exception:
            pass

    # 5. Sobreescribir prolago.db con el respaldo validado
    shutil.move(temp_path, db_file)

    # 6. Asegurar esquemas e índices
    Base.metadata.create_all(bind=engine)

    return {
        "status": "ok",
        "mensaje": f"¡Base de datos restaurada con éxito! Se recuperaron {cant_arts} artículos y {cant_facts} facturas.",
        "articulos_restaurados": cant_arts,
        "facturas_restauradas": cant_facts
    }


