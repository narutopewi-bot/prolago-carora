@echo off
title PROLAGO CARORA 2026 - Servidor Local
color 0A

echo ========================================================
echo       PROLAGO CARORA 2026 - SISTEMA ADMINISTRATIVO
echo                 INICIANDO SERVIDOR LOCAL
echo ========================================================
echo.

:: Detectar IP local
for /f "tokens=4" %%a in ('route print ^| find " 0.0.0.0 "') do (
    set LOCAL_IP=%%a
)

echo [OK] Servidor activo para la red local.
echo.
echo ========================================================
echo  ACCESO DESDE ESTA COMPUTADORA:
echo    http://localhost:8000
echo.
echo  ACCESO DESDE CELULARES O OTRAS COMPUTADORAS (WI-FI):
echo    http://%LOCAL_IP%:8000
echo ========================================================
echo.
echo NOTA: No cierres esta ventana mientras el sistema este en uso.
echo Para detener el sistema, presiona Ctrl + C.
echo.

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
