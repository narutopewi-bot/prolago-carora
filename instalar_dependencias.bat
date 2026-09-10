@echo off
title Instalador de Dependencias - PROLAGO CARORA
color 0B

echo ========================================================
echo       PROLAGO CARORA 2026 - INSTALADOR LOCAL
echo ========================================================
echo.
echo Instalando dependencias de Python...
pip install -r requirements.txt
echo.
echo ========================================================
echo  [OK] Dependencias instaladas con exito.
echo  Ya puedes iniciar el sistema con 'iniciar_servidor_local.bat'
echo ========================================================
pause
