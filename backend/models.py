from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    nombre = Column(String(100), nullable=False)
    rol = Column(String(20), default="cajero")  # 'admin' o 'cajero'
    activo = Column(Boolean, default=True)
    permisos = Column(Text, default="*")  # JSON lista de permisos o '*'
    creado_en = Column(DateTime, default=datetime.utcnow)

    @property
    def lista_permisos(self):
        if self.rol == "admin":
            return ["pos", "inventario", "compras", "despachos", "creditos", "historial", "clientes", "reportes", "mantenimiento", "usuarios", "modificar_facturas", "*"]
        if not self.permisos or self.permisos == "*":
            if self.rol == "admin":
                return ["pos", "inventario", "compras", "despachos", "creditos", "historial", "clientes", "reportes", "mantenimiento", "usuarios", "modificar_facturas", "*"]
            return ["pos", "historial", "clientes"]
        try:
            import json
            p = json.loads(self.permisos)
            if isinstance(p, list):
                return p
        except Exception:
            return [x.strip() for x in self.permisos.split(",") if x.strip()]
        return []

    def tiene_permiso(self, perm: str) -> bool:
        if self.rol == "admin":
            return True
        perms = self.lista_permisos
        return "*" in perms or perm in perms

class Articulo(Base):
    __tablename__ = "articulos"

    codigo = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(255), index=True, nullable=False)
    categoria = Column(String(100), default="GENERAL")
    marca = Column(String(100), default="")
    proveedor = Column(String(100), default="")
    
    # Costos y Precios
    costo = Column(Float, default=0.0)
    flete = Column(Float, default=0.0)
    costo_final = Column(Float, default=0.0)
    mas = Column(Float, default=0.0)
    rentabilidad = Column(Float, default=20.0)  # porcentaje, ej: 20
    sugerido = Column(Float, default=0.0)
    precio = Column(Float, default=0.0)
    
    # Inventario
    stock = Column(Float, default=0.0)
    stock_alerta = Column(Float, default=5.0)
    activo = Column(Boolean, default=True)

class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    cedula_rif = Column(String(50), index=True, default="")
    nombre = Column(String(150), index=True, nullable=False)
    direccion = Column(String(255), default="")
    telefono = Column(String(50), default="")
    tipo = Column(String(20), default="general")  # 'general' o 'despacho'

class Compra(Base):
    __tablename__ = "compras"

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    codigo_articulo = Column(Integer, index=True, nullable=False)
    nombre_articulo = Column(String(255), default="")
    cantidad = Column(Float, default=0.0)
    costo = Column(Float, default=0.0)
    flete = Column(Float, default=0.0)
    mas = Column(Float, default=0.0)
    rentabilidad = Column(Float, default=0.0)
    precio = Column(Float, default=0.0)

class Factura(Base):
    __tablename__ = "facturas"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String(50), unique=True, index=True, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    cliente_nombre = Column(String(150), default="CLIENTE DE CONTADO")
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    
    total = Column(Float, default=0.0)
    tasa_bcv = Column(Float, default=1.0)
    condicion = Column(String(20), default="contado") # 'contado' o 'credito'
    
    # Desglose de formas de pago en USD
    credito = Column(Float, default=0.0)
    saldo_pendiente = Column(Float, default=0.0)
    estado_credito = Column(String(20), default="saldado") # 'pendiente', 'parcial', 'saldado'
    fecha_vencimiento = Column(DateTime, nullable=True)
    
    efectivo = Column(Float, default=0.0)
    zelle = Column(Float, default=0.0)
    pagomovil = Column(Float, default=0.0)
    punto = Column(Float, default=0.0)
    
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    items = relationship("DetalleFactura", back_populates="factura", cascade="all, delete-orphan")
    abonos = relationship("AbonoCredito", back_populates="factura", cascade="all, delete-orphan")

class AbonoCredito(Base):
    __tablename__ = "abonos_credito"

    id = Column(Integer, primary_key=True, index=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    monto_usd = Column(Float, default=0.0)
    monto_bs = Column(Float, default=0.0)
    tasa_bcv = Column(Float, default=1.0)
    metodo_pago = Column(String(50), default="efectivo") # 'efectivo', 'pagomovil', 'zelle', 'punto'
    nota = Column(String(255), default="")

    factura = relationship("Factura", back_populates="abonos")

class DetalleFactura(Base):
    __tablename__ = "detalles_factura"

    id = Column(Integer, primary_key=True, index=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=False)
    codigo_articulo = Column(Integer, nullable=False)
    nombre_articulo = Column(String(255), nullable=False)
    cantidad = Column(Float, default=1.0)
    precio_unitario = Column(Float, default=0.0)
    descuento_pct = Column(Float, default=0.0)
    subtotal = Column(Float, default=0.0)
    costo_unitario = Column(Float, default=0.0)

    factura = relationship("Factura", back_populates="items")

class Despacho(Base):
    __tablename__ = "despachos"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String(50), unique=True, index=True, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    destino_cliente = Column(String(150), nullable=False)
    direccion = Column(String(255), default="")
    total = Column(Float, default=0.0)

    items = relationship("DetalleDespacho", back_populates="despacho", cascade="all, delete-orphan")

class DetalleDespacho(Base):
    __tablename__ = "detalles_despacho"

    id = Column(Integer, primary_key=True, index=True)
    despacho_id = Column(Integer, ForeignKey("despachos.id"), nullable=False)
    codigo_articulo = Column(Integer, nullable=False)
    nombre_articulo = Column(String(255), nullable=False)
    cantidad = Column(Float, default=1.0)
    costo_unitario = Column(Float, default=0.0)
    subtotal = Column(Float, default=0.0)

    despacho = relationship("Despacho", back_populates="items")

class Configuracion(Base):
    __tablename__ = "configuracion"

    clave = Column(String(50), primary_key=True)
    valor = Column(String(255), nullable=False)
