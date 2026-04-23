@echo off
cd /d "%~dp0"
title Limpar Build - Acampamento Defense

echo ============================================================
echo Limpeza de Arquivos de Build
echo ============================================================
echo.
echo Este script ira remover:
echo   - Pasta build/ (arquivos temporarios)
echo   - Pasta __pycache__/ (cache do Python)
echo   - Arquivo AcampamentoDefense.spec (config PyInstaller)
echo.
echo NOTA: O executavel em dist/ sera mantido!
echo.
echo Deseja continuar? (S/N)
set /p resposta=Resposta:

if /i not "%resposta%"=="S" (
    echo.
    echo Operacao cancelada.
    pause
    exit /b 0
)

echo.
echo [INFO] Limpando arquivos...
echo.

REM Remover pasta build
if exist "build" (
    echo [INFO] Removendo pasta build/
    rmdir /s /q "build"
)

REM Remover pasta __pycache__
if exist "__pycache__" (
    echo [INFO] Removendo pasta __pycache__/
    rmdir /s /q "__pycache__"
)

REM Remover arquivo .spec
if exist "AcampamentoDefense.spec" (
    echo [INFO] Removendo AcampamentoDefense.spec
    del /q "AcampamentoDefense.spec"
)

echo.
echo [OK] Limpeza concluida!
echo.
echo O executavel em dist/ foi mantido.
echo.
pause
