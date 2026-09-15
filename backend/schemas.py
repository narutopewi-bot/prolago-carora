from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

class LoginRequest(BaseModel):
    username: str
    password: str

class TasaBCVUpdate(BaseModel):
    tasa: float

class ArticuloBase(BaseModel):
    codigo: int
    nombre: str
    categoria: Optional[str] = "GENERAL"
    marca: Optional[str] = ""
    proveedor: Optional[str] = ""
    costo: Optional[float] = 0.0
    flete: Optional[float] = 0.0
    costo_final: Optional[float] = 0.0
    mas: Optional[float] = 0.0
    rentabilidad: Optional[float] = 20.0
    sugerido: Optional[float] = 0.0
    precio: Optional[float] = 0.0
    stock: Optional[float] = 0.0
    stock_alerta: Optional[float] = 5.0
    activo: Optional[bool] = True

class ArticuloCreate(ArticuloBase):
    pass

class ArticuloOut(ArticuloBase):
    class Config:
        from_attributes = True

class ClienteBase(BaseModel):
    cedula_rif: Optional[str] = ""
    nombre: str
    direccion: Optional[str] = ""
    telefono: Optional[str] = ""
    tipo: Optional[str] = "general"

class ClienteCreate(ClienteBase):
    pass

class ClienteOut(ClienteBase):
    id: int
    class Config:
        from_attributes = True

class ItemFacturaCreate(BaseModel):
    codigo_articulo: int
    cantidad: float
    precio_unitario: float
    descuento_pct: Optional[float] = 0.0

class FacturaCreate(BaseModel):
    cliente_nombre: Optional[str] = "CLIENTE DE CONTADO"
    cliente_id: Optional[int] = None
    condicion: Optional[str] = "contado" # 'contado' o 'credito'
    efectivo: Optional[float] = 0.0
    zelle: Optional[float] = 0.0
    pagomovil: Optional[float] = 0.0
    punto: Optional[float] = 0.0
    credito: Optional[float] = 0.0
    dias_credito: Optional[int] = 15
    items: List[ItemFacturaCreate]

class AbonoCreate(BaseModel):
    monto_usd: float
    monto_bs: Optional[float] = 0.0
    metodo_pago: Optional[str] = "efectivo"
    nota: Optional[str] = ""

class ItemDespachoCreate(BaseModel):
    codigo_articulo: int
    cantidad: float
    costo_unitario: float

class DespachoCreate(BaseModel):
    destino_cliente: str
    direccion: Optional[str] = ""
    items: List[ItemDespachoCreate]

class CompraCreate(BaseModel):
    codigo_articulo: int
    cantidad: float
    costo: float
    flete: Optional[float] = 0.0
    mas: Optional[float] = 0.0
    rentabilidad: Optional[float] = 20.0
    precio: float
