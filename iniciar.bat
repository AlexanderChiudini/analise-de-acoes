@echo off
cd /d "%~dp0"
title Equity Lab
echo.
echo Equity Lab - mantenha esta janela aberta durante o uso.
echo Acesse http://127.0.0.1:8765 no navegador (ou a porta definida em PORT).
echo Para encerrar, pressione Ctrl+C.
echo.
if exist "%~dp0.runtime\python.exe" (
    "%~dp0.runtime\python.exe" -I "%~dp0server.py"
) else (
    python "%~dp0server.py"
)
if errorlevel 1 (
    echo.
    echo Nao foi possivel iniciar. Confira a mensagem acima.
    echo Se o Python nao foi encontrado, instale Python 3.11 ou superior.
    echo Se a porta estiver em uso, feche a outra janela do Equity Lab.
    pause
    exit /b 1
)
