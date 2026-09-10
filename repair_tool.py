import os
import sys
import subprocess
import socket
import sqlite3
import shutil
import time
from datetime import datetime

INSTALL_DIR = r"C:\ProlagoCarora"
DB_PATH = os.path.join(INSTALL_DIR, "prolago.db")
APP_EXE = os.path.join(INSTALL_DIR, "ProlagoCarora.exe")

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

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

def liberar_puerto():
    print("\n [1/4] Buscando y cerrando procesos en el puerto 8000...")
    try:
        # Buscar PIDs en el puerto 8000
        cmd = 'netstat -ano | findstr :8000 | findstr LISTENING'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        lines = res.stdout.strip().split("\n")
        pids = set()
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 5:
                pids.add(parts[-1])
        
        if pids:
            for pid in pids:
                print(f"       -> Cerrando proceso fantasma (PID: {pid})...")
                subprocess.run(f'taskkill /F /PID {pid}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("       [OK] Puerto 8000 liberado correctamente.")
        else:
            print("       [OK] El puerto 8000 ya estaba libre.")
    except Exception as e:
        print(f"       [!] Error liberando puerto: {e}")

def reparar_firewall():
    print("\n [2/4] Reparando regla del Firewall de Windows (Puerto 8000)...")
    try:
        subprocess.run('netsh advfirewall firewall delete rule name="Prolago Carora 2026"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run('netsh advfirewall firewall add rule name="Prolago Carora 2026" dir=in action=allow protocol=TCP localport=8000 profile=any', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("       [OK] Regla de Firewall reconfigurada (Acceso permitido en red local/Wi-Fi).")
    except Exception as e:
        print(f"       [!] Error en firewall: {e}")

def verificar_y_reparar_db():
    print("\n [3/4] Verificando e indexando la base de datos prolago.db...")
    if not os.path.exists(DB_PATH):
        print(f"       [!] No se encontro base de datos en {DB_PATH}")
        return

    # Crear respaldo de seguridad antes de cualquier operacion
    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(INSTALL_DIR, f"prolago_backup_{fecha_str}.db")
    try:
        shutil.copy2(DB_PATH, backup_path)
        print(f"       -> Respaldo de seguridad creado: prolago_backup_{fecha_str}.db")
    except Exception as e:
        print(f"       [!] No se pudo crear respaldo preventivo: {e}")

    # Verificar integridad SQLite
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        res = cursor.fetchall()
        if res and res[0][0] == "ok":
            print("       [OK] Integridad de la base de datos: CORRECTA (Sin corrupcion).")
        else:
            print(f"       [!] Resultado integridad: {res}")

        # Compactar y optimizar
        cursor.execute("VACUUM;")
        cursor.execute("PRAGMA optimize;")
        conn.commit()
        conn.close()
        print("       [OK] Base de datos compactada y optimizada.")
    except Exception as e:
        print(f"       [!] Error reparando base de datos: {e}")

def reiniciar_sistema():
    print("\n [4/4] Reiniciando Prolago Carora 2026...")
    if os.path.exists(APP_EXE):
        subprocess.Popen([APP_EXE], cwd=INSTALL_DIR)
        print("       [OK] Sistema iniciado exitosamente.")
    else:
        print(f"       [!] No se encontro el ejecutable en {APP_EXE}")

def reparacion_automatica_completa():
    clear_screen()
    print("=" * 65)
    print("      PROLAGO CARORA 2026 - REPARACION AUTOMATICA TOTAL")
    print("=" * 65)
    liberar_puerto()
    reparar_firewall()
    verificar_y_reparar_db()
    reiniciar_sistema()
    print("\n" + "=" * 65)
    print("   [LISTO] REPARACION COMPLETADA CON EXITO")
    print("=" * 65)
    input("\n Presione ENTER para volver al menu principal...")

def hacer_backup_manual():
    clear_screen()
    print("=" * 65)
    print("            CREAR RESPALDO DE BASE DE DATOS")
    print("=" * 65)
    if not os.path.exists(DB_PATH):
        print("\n [!] No se encontro el archivo prolago.db")
        input("\n Presione ENTER...")
        return
    
    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Copiar al escritorio
    desktop = os.path.join(os.environ.get("USERPROFILE", "C:\\"), "Desktop")
    destino_desktop = os.path.join(desktop, f"COPIA_PROLAGO_{fecha_str}.db")
    destino_local = os.path.join(INSTALL_DIR, f"prolago_backup_{fecha_str}.db")

    try:
        shutil.copy2(DB_PATH, destino_local)
        shutil.copy2(DB_PATH, destino_desktop)
        print(f"\n [OK] Respaldo guardado con exito en:")
        print(f"      1. Tu Escritorio: COPIA_PROLAGO_{fecha_str}.db")
        print(f"      2. En instalacion: prolago_backup_{fecha_str}.db")
        print("\n Puedes guardar el archivo de tu Escritorio en un pendrive.")
    except Exception as e:
        print(f"\n [!] Error creando respaldo: {e}")

    input("\n Presione ENTER para continuar...")

def diagnostico_red():
    clear_screen()
    print("=" * 65)
    print("             DIAGNOSTICO DE RED LOCAL Y WI-FI")
    print("=" * 65)
    ip = obtener_ip_local()
    print(f"\n  -> Direccion IP de esta computadora: {ip}")
    print(f"  -> Puerto del sistema: 8000")
    print(f"\n  Direccion para abrir en CELULARES conectados al mismo Wi-Fi:")
    print(f"  =========================================")
    print(f"   http://{ip}:8000")
    print(f"  =========================================\n")

    # Probar si el puerto 8000 responde
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", 8000))
        print(" [OK] El sistema esta respondiendo activamente en el puerto 8000.")
        s.close()
    except Exception:
        print(" [AVISO] El sistema no parece estar corriendo actualmente en el puerto 8000.")

    input("\n Presione ENTER para volver al menu...")

def menu():
    while True:
        clear_screen()
        print("=" * 65)
        print("   HERRAMIENTA DE MANTENIMIENTO Y RESCATE - PROLAGO CARORA 2026")
        print("=" * 65)
        print(" 1. [RECOMENDADO] Reparacion Automatica Completa (1 Clic)")
        print("    (Cierra procesos colgados, repara firewall, optimiza BD y arranca)")
        print()
        print(" 2. Liberar Puerto 8000 (Cerrar procesos bloqueados)")
        print(" 3. Reparar Regla de Firewall de Windows (Permitir celulares)")
        print(" 4. Verificar y Optimizar Base de Datos (Sin borrar datos)")
        print(" 5. Crear Respaldo de Emergencia (Copia en el Escritorio)")
        print(" 6. Diagnostico de Red y Direccion IP para Celulares")
        print(" 7. Salir")
        print("=" * 65)
        opc = input(" Seleccione una opcion [1-7]: ").strip()

        if opc == "1":
            reparacion_automatica_completa()
        elif opc == "2":
            clear_screen()
            liberar_puerto()
            input("\n Presione ENTER...")
        elif opc == "3":
            clear_screen()
            reparar_firewall()
            input("\n Presione ENTER...")
        elif opc == "4":
            clear_screen()
            verificar_y_reparar_db()
            input("\n Presione ENTER...")
        elif opc == "5":
            hacer_backup_manual()
        elif opc == "6":
            diagnostico_red()
        elif opc == "7":
            break

if __name__ == "__main__":
    menu()
