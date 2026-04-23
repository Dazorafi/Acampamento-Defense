@echo off
cd /d "%~dp0"
cls

:menu
title Acampamento Defense - Menu Principal
cls
echo.
echo  ============================================================
echo.
echo           ACAMPAMENTO DEFENSE - MENU PRINCIPAL
echo.
echo  ============================================================
echo.
echo   1. Jogar (executar o jogo compilado)
echo   2. Build (compilar novo executavel)
echo   3. Limpar arquivos temporarios
echo   4. Executar codigo-fonte Python
echo   5. Sair
echo.
echo  ============================================================
echo.
set /p opcao=  Escolha uma opcao (1-5):
echo.

if "%opcao%"=="1" goto jogar
if "%opcao%"=="2" goto build
if "%opcao%"=="3" goto limpar
if "%opcao%"=="4" goto python
if "%opcao%"=="5" goto sair

echo  [ERRO] Opcao invalida!
timeout /t 2 >nul
goto menu

:jogar
cls
echo.
echo  [INFO] Iniciando jogo...
echo.
if not exist "%~dp0dist\AcampamentoDefense.exe" (
    echo  [ERRO] Executavel nao encontrado!
    echo  Execute a opcao 2 para compilar o jogo primeiro.
    echo.
    pause
    goto menu
)
start "" "%~dp0dist\AcampamentoDefense.exe"
echo  [OK] Jogo executando!
echo.
timeout /t 2 >nul
goto menu

:build
cls
call "%~dp0build.bat"
pause
goto menu

:limpar
cls
call limpar.bat
goto menu

:python
cls
echo.
echo  [INFO] Executando codigo-fonte Python...
echo.
if not exist "%~dp0acampamento_defense_pygamev8.py" (
    echo  [ERRO] Arquivo acampamento_defense_pygamev8.py nao encontrado!
    echo.
    pause
    goto menu
)
set "PYTHON=python"
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if errorlevel 1 (
        echo  [ERRO] Python nao encontrado!
        echo  Instale o Python 3.10 ou superior.
        echo.
        pause
        goto menu
    ) else (
        set "PYTHON=py"
    )
)
echo  [INFO] Verificando dependencias...
"%PYTHON%" -m pip show pygame >nul 2>&1
if errorlevel 1 (
    echo  [AVISO] Pygame nao encontrado. Instalando...
    "%PYTHON%" -m pip install pygame
)
echo.
echo  [INFO] Iniciando jogo...
"%PYTHON%" "%~dp0acampamento_defense_pygamev8.py"
goto menu

:sair
cls
echo.
echo  Ate logo!
echo.
timeout /t 1 >nul
exit /b 0
