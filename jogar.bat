@echo off
cd /d "%~dp0"
title Acampamento Defense

REM Verificar se o executavel existe
if not exist "%~dp0dist\AcampamentoDefense.exe" (
    echo [ERRO] Executavel nao encontrado!
    echo.
    echo Execute o build.bat primeiro para criar o executavel.
    echo.
    pause
    exit /b 1
)

echo [INFO] Iniciando Acampamento Defense...
echo.
start "" "%~dp0dist\AcampamentoDefense.exe"
