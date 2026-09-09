import urllib.request
import urllib.parse
import json
import http.cookiejar

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
BASE = "http://127.0.0.1:8000"

def run_test():
    print("1. Login como admin...")
    login_data = json.dumps({"username": "admin", "password": "admin123"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
    res = opener.open(req)
    assert res.status == 200

    print("2. Creando venta a crédito de prueba...")
    fact_payload = {
        "cliente_nombre": "JUAN PEREZ",
        "efectivo": 0.0,
        "zelle": 0.0,
        "pagomovil": 0.0,
        "punto": 0.0,
        "credito": 32.40,
        "dias_credito": 15,
        "items": [
            {
                "codigo_articulo": 499,
                "cantidad": 2,
                "precio_unitario": 16.20,
                "descuento_pct": 0
            }
        ]
    }
    req = urllib.request.Request(f"{BASE}/api/facturas", data=json.dumps(fact_payload).encode(), headers={"Content-Type": "application/json"})
    res = opener.open(req)
    f_data = json.loads(res.read().decode())
    print("  -> Factura a crédito creada:", f_data)
    fact_id = f_data["factura_id"]

    print("3. Consultando /api/creditos...")
    res = opener.open(f"{BASE}/api/creditos?solo_pendientes=true")
    creditos = json.loads(res.read().decode())
    print(f"  -> Total deudor: ${creditos['resumen']['total_por_cobrar_usd']}")
    encontrado = next((c for c in creditos["items"] if c["factura_id"] == fact_id), None)
    assert encontrado is not None
    assert encontrado["saldo_pendiente"] == 32.40
    print(f"  -> Factura #{encontrado['numero']} para {encontrado['cliente_nombre']} saldo: ${encontrado['saldo_pendiente']}")

    print("4. Registrando abono parcial de $12.40...")
    abono_payload = {
        "monto_usd": 12.40,
        "metodo_pago": "pagomovil",
        "nota": "Abono inicial Pago Movil"
    }
    req = urllib.request.Request(f"{BASE}/api/creditos/{fact_id}/abonos", data=json.dumps(abono_payload).encode(), headers={"Content-Type": "application/json"})
    res = opener.open(req)
    ab_res = json.loads(res.read().decode())
    print("  -> Abono registrado:", ab_res)
    assert ab_res["nuevo_saldo_pendiente"] == 20.00
    assert ab_res["estado_credito"] == "parcial"

    print("5. Registrando abono final de $20.00...")
    abono_payload2 = {
        "monto_usd": 20.00,
        "metodo_pago": "efectivo",
        "nota": "Pago total saldo"
    }
    req = urllib.request.Request(f"{BASE}/api/creditos/{fact_id}/abonos", data=json.dumps(abono_payload2).encode(), headers={"Content-Type": "application/json"})
    res = opener.open(req)
    ab_res2 = json.loads(res.read().decode())
    print("  -> Abono final registrado:", ab_res2)
    assert ab_res2["nuevo_saldo_pendiente"] == 0.00
    assert ab_res2["estado_credito"] == "saldado"

    print("6. Consultando historial de abonos...")
    res = opener.open(f"{BASE}/api/creditos/{fact_id}/abonos")
    abonos_hist = json.loads(res.read().decode())
    print(f"  -> Cantidad de abonos registrados: {len(abonos_hist)}")
    assert len(abonos_hist) == 2

    print("\n¡PRUEBAS DE CRÉDITO Y COBRANZAS COMPLETADAS CON ÉXITO!")

if __name__ == "__main__":
    run_test()
