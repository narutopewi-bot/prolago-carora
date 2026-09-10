import os
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, desc

from .database import get_db, engine, Base
from .models import Articulo, Cliente, Factura, DetalleFactura, Despacho, DetalleDespacho, Compra, Usuario, Configuracion, AbonoCredito
from .schemas import (
    LoginRequest, TasaBCVUpdate, ArticuloCreate, ArticuloOut,
    ClienteCreate, ClienteOut, FacturaCreate, DespachoCreate, CompraCreate, AbonoCreate
)
from .auth import (
    hash_password, verify_password, create_session,
    ACTIVE_SESSIONS, get_current_user, require_user, require_admin
)

# Inicializar tablas
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Prolago Carora Web", version="1.0.0")

# Directorios de frontend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "frontend", "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "frontend", "templates")

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
    return {"status": "ok", "user": {"id": user.id, "username": user.username, "nombre": user.nombre, "rol": user.rol}}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]
    response.delete_cookie("session_token")
    return {"status": "ok"}

@app.get("/api/auth/me")
def me(user: Usuario = Depends(require_user)):
    return {"id": user.id, "username": user.username, "nombre": user.nombre, "rol": user.rol}

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
        items=detalles
    )
    db.add(factura)
    db.commit()
    db.refresh(factura)

    return {
        "status": "ok",
        "factura_id": factura.id,
        "numero": factura.numero,
        "condicion": factura.condicion,
        "total_usd": factura.total,
        "total_bs": round(factura.total * tasa_bcv, 2),
        "tasa_bcv": tasa_bcv,
        "saldo_pendiente": factura.saldo_pendiente,
        "fecha_vencimiento": factura.fecha_vencimiento.strftime("%Y-%m-%d") if factura.fecha_vencimiento else ""
    }

@app.get("/api/facturas")
def list_facturas(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_user)
):
    query = db.query(Factura)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(Factura.numero.ilike(s), Factura.cliente_nombre.ilike(s)))
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
            "estado_credito": f.estado_credito or ("saldado" if saldo <= 0.009 else "pendiente")
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
        "fecha": factura.fecha.strftime("%Y-%m-%d %H:%M:%S") if factura.fecha else "",
        "cliente_nombre": factura.cliente_nombre,
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

    abono = AbonoCredito(
        factura_id=factura.id,
        fecha=datetime.now(),
        monto_usd=round(monto_abono, 2),
        monto_bs=round(monto_bs, 2),
        tasa_bcv=tasa_bcv,
        metodo_pago=payload.metodo_pago or "efectivo",
        nota=payload.nota or ""
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
# REPORTES Y ESTADÍSTICAS
# ==========================================
@app.get("/api/reportes/resumen")
def get_reporte_resumen(db: Session = Depends(get_db), user: Usuario = Depends(require_user)):
    today_start = datetime.combine(date.today(), datetime.min.time())
    
    # Facturas de hoy
    facturas_hoy = db.query(Factura).filter(Factura.fecha >= today_start).all()
    total_hoy = sum(f.total for f in facturas_hoy)
    efectivo_hoy = sum(f.efectivo for f in facturas_hoy)
    zelle_hoy = sum(f.zelle for f in facturas_hoy)
    pagomovil_hoy = sum(f.pagomovil for f in facturas_hoy)
    punto_hoy = sum(f.punto for f in facturas_hoy)
    credito_hoy = sum(f.credito for f in facturas_hoy)

    # Métricas globales de inventario
    articulos = db.query(Articulo).filter(Articulo.activo == True).all()
    total_articulos = len(articulos)
    bajo_stock = sum(1 for a in articulos if a.stock <= 5)
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
# RUTAS DE PÁGINAS HTML (INTERFAZ WEB)
# ==========================================
@app.get("/login", response_class=HTMLResponse)
def page_login(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/", response_class=HTMLResponse)
def page_pos(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="pos.html", context={"user": user})

@app.get("/inventario", response_class=HTMLResponse)
def page_inventario(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="articulos.html", context={"user": user})

@app.get("/compras", response_class=HTMLResponse)
def page_compras(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="compras.html", context={"user": user})

@app.get("/despachos", response_class=HTMLResponse)
def page_despachos(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="despachos.html", context={"user": user})

@app.get("/historial", response_class=HTMLResponse)
def page_historial(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="historial.html", context={"user": user})

@app.get("/clientes", response_class=HTMLResponse)
def page_clientes(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="clientes.html", context={"user": user})

@app.get("/reportes", response_class=HTMLResponse)
def page_reportes(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="reportes.html", context={"user": user})

@app.get("/creditos", response_class=HTMLResponse)
def page_creditos(request: Request, user: Usuario = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="creditos.html", context={"user": user})

