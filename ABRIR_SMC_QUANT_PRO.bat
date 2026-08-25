@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title SMC Quant Pro

REM =====================================================================
REM  SMC Quant Pro — abrir o programa (Windows)
REM  De DOIS CLIQUES neste arquivo.
REM
REM  A JANELA PRETA FICA ABERTA DE PROPOSITO: e nela que sai o log do
REM  motor — ordem enviada, posicao encerrada, ciclo de analise. Fechar
REM  esta janela FECHA o programa.
REM =====================================================================

cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo [X] NAO ENCONTREI O PYTHON.
  echo     De dois cliques em INSTALAR_WINDOWS.bat primeiro.
  echo.
  pause
  exit /b 1
)

if not exist "main_app.py" (
  echo.
  echo [X] Nao achei o main_app.py nesta pasta.
  echo     Este arquivo precisa ficar DENTRO da pasta SMC_QUANT_PRO,
  echo     junto com o resto do programa.
  echo     Pasta atual: %CD%
  echo.
  pause
  exit /b 1
)

echo.
echo  Abrindo o SMC Quant Pro...
echo  (NAO feche esta janela: e aqui que sai o log do motor.)
echo.

%PY% main_app.py
set "SAIDA=%errorlevel%"

REM SAIDA DIFERENTE DE ZERO E DEFEITO, E TEM DE FICAR NA TELA.
REM Sem este bloco a janela fecha sozinha no instante do erro e leva a
REM mensagem junto — o cliente ve um piscar e nao tem o que relatar.
if not "%SAIDA%"=="0" (
  echo.
  echo ======================================================================
  echo   O PROGRAMA FECHOU COM ERRO (codigo %SAIDA%^).
  echo.
  echo   As ultimas linhas ACIMA dizem o motivo. Tire uma foto delas
  echo   antes de fechar esta janela -- e com elas que da para consertar.
  echo.
  echo   Se aparecer "ModuleNotFoundError", faltou biblioteca: de dois
  echo   cliques em INSTALAR_WINDOWS.bat e rode de novo.
  echo ======================================================================
  echo.
  pause
)
