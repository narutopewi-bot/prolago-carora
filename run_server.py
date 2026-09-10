import os
import sys
import socket
import webbrowser
import threading
import time
import uvicorn

# Configurar rutas para PyInstaller
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    EXE_DIR = os.path.dirname(sys.executable)
    # Asegurar que el directorio de trabajo sea donde reside el ejecutable
    os.chdir(EXE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BASE_DIR

def obtener_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def abrir_navegador():
    time.sleep(1.8)
    try:
        webbrowser.open("http://localhost:8000")
    except Exception as e:
        print(f"No se pudo abrir el navegador automaticamente: {e}")

def main():
    ip_local = obtener_ip_local()
    
    print("=" * 65)
    print("      PROLAGO CARORA 2026 - SISTEMA ADMINISTRATIVO Y POS")
    print("               SERVIDOR LOCAL PARA RED Y NEGOCIO")
    print("=" * 65)
    print(f" [OK] Base de datos activa.")
    print(f" [OK] Servidor escuchando en toda la red local.")
    print("-" * 65)
    print(f"  --> ACCESO DESDE ESTA COMPUTADORA:")
    print(f"      http://localhost:8000")
    print()
    print(f"  --> ACCESO DESDE CELULARES Y TABLETS (MISMO WI-FI):")
    print(f"      http://{ip_local}:8000")
    print("=" * 65)
    print(" NOTA: Mantenga esta ventana abierta durante la jornada laboral.")
    print(" Para cerrar el sistema de forma segura, presione Ctrl + C.")
    print("=" * 65 + "\n")

    threading.Thread(target=abrir_navegador, daemon=True).start()

    from backend.main import app
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

if __name__ == "__main__":
    main()
