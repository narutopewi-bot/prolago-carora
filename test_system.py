import urllib.request
import urllib.parse
import json
import http.cookiejar

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

BASE = "http://127.0.0.1:8000"

def test_flow():
    print("1. Probando Login con admin/admin123...")
    login_data = json.dumps({"username": "admin", "password": "admin123"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
    res = opener.open(req)
    data = json.loads(res.read().decode())
    print("  -> Login exitoso:", data)
    assert data["status"] == "ok"

    print("\n2. Probando /api/configuracion...")
    res = opener.open(f"{BASE}/api/configuracion")
    cfg = json.loads(res.read().decode())
    print("  -> Configuración:", cfg)
    assert float(cfg["tasa_bcv"]) == 473.92

    print("\n3. Probando /api/articulos...")
    res = opener.open(f"{BASE}/api/articulos?limit=5")
    arts = json.loads(res.read().decode())
    print(f"  -> Total de artículos en base de datos: {arts['total']}")
    assert arts["total"] >= 900

    print("\n4. Consultando stock del artículo #499...")
    res = opener.open(f"{BASE}/api/articulos/499")
    art499 = json.loads(res.read().decode())
    stock_inicial = art499["stock"]
    precio499 = art499["precio"]
    print(f"  -> Artículo: {art499['nombre']}, Stock inicial: {stock_inicial}, Precio: ${precio499}")

    print("\n5. Creando Factura de prueba...")
    fact_payload = {
        "cliente_nombre": "CLIENTE DE PRUEBA CARORA",
        "efectivo": 12.40,
        "zelle": 20.00,
        "pagomovil": 0.0,
        "punto": 0.0,
        "credito": 0.0,
        "items": [
            {
                "codigo_articulo": 499,
                "cantidad": 2,
                "precio_unitario": precio499,
                "descuento_pct": 0
            }
        ]
    }
    req = urllib.request.Request(f"{BASE}/api/facturas", data=json.dumps(fact_payload).encode(), headers={"Content-Type": "application/json"})
    res = opener.open(req)
    fact_res = json.loads(res.read().decode())
    print("  -> Factura creada:", fact_res)
    assert fact_res["status"] == "ok"

    print("\n6. Verificando descuento de stock...")
    res = opener.open(f"{BASE}/api/articulos/499")
    art499_post = json.loads(res.read().decode())
    print(f"  -> Stock anterior: {stock_inicial}, Nuevo stock: {art499_post['stock']}")
    assert round(art499_post["stock"], 2) == round(stock_inicial - 2, 2)

    print("\n7. Consultando resumen de caja...")
    res = opener.open(f"{BASE}/api/reportes/resumen")
    rep = json.loads(res.read().decode())
    print("  -> Ventas hoy:", rep["ventas_hoy"])
    assert rep["ventas_hoy"]["cantidad_facturas"] >= 1
    assert rep["ventas_hoy"]["zelle"] >= 20.0

    print("\n¡TODAS LAS PRUEBAS AUTOMATIZADAS PASARON EXITOSAMENTE!")

if __name__ == "__main__":
    test_flow()
