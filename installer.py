import os
import sys
import zipfile
import subprocess
import ctypes
import shutil

INSTALL_DIR = r"C:\ProlagoCarora"
APP_EXE = os.path.join(INSTALL_DIR, "ProlagoCarora.exe")
APP_ICO = os.path.join(INSTALL_DIR, "app.ico")

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def show_message(title, text, style=0x40):
    # 0x40 = MB_ICONINFORMATION | MB_OK
    ctypes.windll.user32.MessageBoxW(0, text, title, style)

def ask_yes_no(title, text):
    # 0x24 = MB_ICONQUESTION | MB_YESNO
    res = ctypes.windll.user32.MessageBoxW(0, text, title, 0x24)
    return res == 6 # IDYES

def configure_firewall():
    print(" [1/4] Configurando Firewall de Windows para red local...")
    try:
        subprocess.run(
            'netsh advfirewall firewall delete rule name="Prolago Carora 2026"',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        subprocess.run(
            'netsh advfirewall firewall add rule name="Prolago Carora 2026" dir=in action=allow protocol=TCP localport=8000 profile=any',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print("       -> Regla de Firewall agregada exitosamente (Puerto 8000).")
    except Exception as e:
        print(f"       -> Advertencia al configurar firewall: {e}")

def create_shortcut(target_path, shortcut_path, icon_path, description="Prolago Carora 2026"):
    try:
        ps_cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{shortcut_path}"); '
            f'$s.TargetPath = "{target_path}"; '
            f'$s.WorkingDirectory = "{os.path.dirname(target_path)}"; '
            f'$s.IconLocation = "{icon_path},0"; '
            f'$s.Description = "{description}"; '
            f'$s.Save()'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"       -> Error creando acceso directo: {e}")

def main():
    print("=" * 65)
    print("      PROLAGO CARORA 2026 - INSTALADOR OFICIAL DE WINDOWS")
    print("=" * 65)
    print()

    # 1. Obtener ruta del bundle embebido
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        bundle_dir = os.path.dirname(os.path.abspath(__file__))

    zip_path = os.path.join(bundle_dir, "app_bundle.zip")
    icon_source = os.path.join(bundle_dir, "app.ico")

    if not os.path.exists(zip_path):
        print(f"Error critico: No se encontro el paquete de instalacion en {zip_path}")
        input("Presione ENTER para salir...")
        return

    # 2. Crear carpeta de instalación
    print(f" [2/4] Instalando archivos en {INSTALL_DIR}...")
    os.makedirs(INSTALL_DIR, exist_ok=True)

    # Si ya existía una base de datos prolago.db en la máquina destino, protegerla para no borrar datos
    existing_db = os.path.join(INSTALL_DIR, "prolago.db")
    db_backup = None
    if os.path.exists(existing_db):
        db_backup = os.path.join(INSTALL_DIR, "prolago_backup_install.db")
        try:
            shutil.copy2(existing_db, db_backup)
            print("       -> Se detecto base de datos existente. Tus datos estan protegidos.")
        except Exception:
            pass

    # Extraer zip
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(INSTALL_DIR)

    # Restaurar base de datos previa si existía
    if db_backup and os.path.exists(db_backup):
        try:
            shutil.copy2(db_backup, existing_db)
            os.remove(db_backup)
        except Exception:
            pass

    # Copiar icono
    if os.path.exists(icon_source):
        try:
            shutil.copy2(icon_source, APP_ICO)
        except Exception:
            pass

    print("       -> Archivos instalados con exito.")

    # 3. Configurar Firewall
    configure_firewall()

    # 4. Crear accesos directos
    print(" [3/4] Creando accesos directos en Escritorio y Menu Inicio...")
    
    # Escritorio del usuario actual y público
    user_desktop = os.path.join(os.environ.get("USERPROFILE", "C:\\"), "Desktop", "Prolago Carora 2026.lnk")
    public_desktop = r"C:\Users\Public\Desktop\Prolago Carora 2026.lnk"
    start_menu = r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Prolago Carora 2026.lnk"

    create_shortcut(APP_EXE, user_desktop, APP_ICO)
    create_shortcut(APP_EXE, public_desktop, APP_ICO)
    create_shortcut(APP_EXE, start_menu, APP_ICO)
    print("       -> Acceso directo 'Prolago Carora 2026' listo.")

    print()
    print("=" * 65)
    print("   [LISTO] PROLAGO CARORA 2026 HA SIDO INSTALADO CORRECTAMENTE")
    print("=" * 65)
    print(" - Ubicacion: C:\\ProlagoCarora")
    print(" - Acceso directo en el Escritorio creado.")
    print(" - Puerto de red 8000 habilitado para celulares y tablets en Wi-Fi.")
    print("=" * 65)
    print()

    iniciar = ask_yes_no(
        "Instalación Completada - Prolago Carora",
        "¡Prolago Carora 2026 se ha instalado exitosamente!\n\n"
        "Ubicación: C:\\ProlagoCarora\n"
        "Se ha creado el acceso directo en tu Escritorio.\n\n"
        "¿Deseas iniciar el sistema ahora?"
    )

    if iniciar:
        print(" Iniciando Prolago Carora 2026...")
        subprocess.Popen([APP_EXE], cwd=INSTALL_DIR)
    
if __name__ == "__main__":
    main()
