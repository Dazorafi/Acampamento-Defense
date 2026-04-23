@echo off
cd /d "%~dp0"
title Build - Acampamento Defense

echo ============================================================
echo Build do Executavel - Acampamento Defense
echo ============================================================
echo.

REM Verificar se Python esta instalado
set "PYTHON=python"
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if errorlevel 1 (
        echo [ERRO] Python nao encontrado!
        echo Por favor, instale o Python 3.10 ou superior.
        echo.
        pause
        exit /b 1
    ) else (
        set "PYTHON=py"
    )
)

echo [INFO] Python encontrado: %PYTHON%
echo.

REM Verificar se o arquivo principal existe
if not exist "acampamento_defense_pygamev8.py" (
    echo [ERRO] Arquivo acampamento_defense_pygamev8.py nao encontrado!
    echo Execute este script na pasta do projeto.
    echo.
    pause
    exit /b 1
)

echo [INFO] Arquivo do jogo encontrado
echo.

REM Executar o script de build
echo [INFO] Iniciando build...
echo.
"%PYTHON%" "%~dp0build_executable.py"

if errorlevel 1 (
    echo.
    echo [ERRO] Build falhou!
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Build concluido com sucesso!
echo ============================================================
echo.
echo O executavel esta em: dist\AcampamentoDefense.exe
echo.
echo Deseja executar o jogo agora? (S/N)
set /p resposta=Resposta:

if /i "%resposta%"=="S" (
    echo.
    echo [INFO] Iniciando o jogo...
    start "" "dist\AcampamentoDefense.exe"
)

echo.
pause
