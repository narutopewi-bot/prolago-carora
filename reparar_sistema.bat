@echo off
title PROLAGO CARORA 2026 - HERRAMIENTA DE REPARACION
color 0E

:: Solicitar permisos de Administrador si no los tiene
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Solicitando permisos de Administrador...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:MENU
cls
echo ========================================================
echo    HERRAMIENTA DE MANTENIMIENTO Y REPARACION RAPIDA
echo                  PROLAGO CARORA 2026
echo ========================================================
echo.
echo  [1] Reparacion Automatica Completa (1 Clic)
echo      (Cierra procesos colgados, repara firewall y reinicia)
echo.
echo  [2] Liberar Puerto 8000 (Cierra procesos colgados)
echo  [3] Reparar Firewall de Windows (Permite celulares en Wi-Fi)
echo  [4] Crear Copia de Respaldo de Emergencia en el Escritorio
echo  [5] Ver IP de esta computadora para conectar celulares
echo  [6] Salir
echo.
echo ========================================================
set /p opc=" Seleccione una opcion [1-6]: "

if "%opc%"=="1" goto REPARAR_TODO
if "%opc%"=="2" goto LIBERAR_PUERTO
if "%opc%"=="3" goto FIREWALL
if "%opc%"=="4" goto BACKUP
if "%opc%"=="5" goto VER_IP
if "%opc%"=="6" exit /b
goto MENU

:REPARAR_TODO
cls
echo ========================================================
echo         REPARACION AUTOMATICA RAPIDA (1 CLIC)
echo ========================================================
echo.
echo 1. Cerrando posibles procesos colgados en el puerto 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
echo    [OK] Puerto 8000 liberado.

echo.
echo 2. Reparando regla del Firewall de Windows...
netsh advfirewall firewall delete rule name="Prolago Carora 2026" >nul 2>&1
netsh advfirewall firewall add rule name="Prolago Carora 2026" dir=in action=allow protocol=TCP localport=8000 profile=any >nul 2>&1
echo    [OK] Regla de Firewall reconfigurada exitosamente.

echo.
echo 3. Iniciando el sistema Prolago Carora...
if exist "C:\ProlagoCarora\ProlagoCarora.exe" (
    start "" "C:\ProlagoCarora\ProlagoCarora.exe"
    echo    [OK] Sistema reiniciado correctamente.
) else if exist "ProlagoCarora.exe" (
    start "" "ProlagoCarora.exe"
    echo    [OK] Sistema reiniciado correctamente.
) else (
    echo    [AVISO] No se encontro el ejecutable directo.
)

echo.
echo ========================================================
echo  REPARACION COMPLETADA CON EXITO
echo ========================================================
pause
goto MENU

:LIBERAR_PUERTO
cls
echo Liberando puerto 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Cerrando proceso con PID %%a...
    taskkill /f /pid %%a >nul 2>&1
)
echo [OK] Puerto 8000 limpio.
pause
goto MENU

:FIREWALL
cls
echo Configurando regla de Firewall...
netsh advfirewall firewall delete rule name="Prolago Carora 2026" >nul 2>&1
netsh advfirewall firewall add rule name="Prolago Carora 2026" dir=in action=allow protocol=TCP localport=8000 profile=any >nul 2>&1
echo [OK] Firewall configurado correctamente.
pause
goto MENU

:BACKUP
cls
echo Generando respaldo de seguridad...
set FECHA=%date:~6,4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%
set FECHA=%FECHA: =0%
if exist "C:\ProlagoCarora\prolago.db" (
    copy "C:\ProlagoCarora\prolago.db" "%USERPROFILE%\Desktop\RESPALDO_PROLAGO_%FECHA%.db"
    echo [OK] Respaldo creado en tu Escritorio: RESPALDO_PROLAGO_%FECHA%.db
) else if exist "prolago.db" (
    copy "prolago.db" "%USERPROFILE%\Desktop\RESPALDO_PROLAGO_%FECHA%.db"
    echo [OK] Respaldo creado en tu Escritorio: RESPALDO_PROLAGO_%FECHA%.db
) else (
    echo [!] No se encontro el archivo prolago.db
)
pause
goto MENU

:VER_IP
cls
for /f "tokens=4" %%a in ('route print ^| find " 0.0.0.0 "') do set IP_LOCAL=%%a
echo ========================================================
echo  DIRECCION IP DE ESTA COMPUTADORA: %IP_LOCAL%
echo  PUERTO: 8000
echo.
echo  En los celulares conectados al mismo Wi-Fi, abre:
echo  http://%IP_LOCAL%:8000
echo ========================================================
pause
goto MENU
