@echo off
setlocal EnableDelayedExpansion
title SMC Quant Pro

REM =====================================================================
REM  SMC Quant Pro - abrir o programa (Windows). DOIS CLIQUES NESTE ARQUIVO.
REM
REM  A JANELA PRETA FICA ABERTA DE PROPOSITO: e nela que sai o log do motor
REM  -- ordem enviada, posicao encerrada, ciclo de analise. Fechar esta
REM  janela FECHA o programa.
REM
REM  ASCII e CRLF, pelo mesmo motivo do INSTALAR_WINDOWS.bat: o cmd.exe
REM  exige CRLF, e com quebra do Unix ele executa os comentarios como se
REM  fossem comandos.
REM =====================================================================

cd /d "%~dp0"

if not exist "main_app.py" (
  echo.
  echo  [X] Nao achei o main_app.py nesta pasta.
  echo.
  echo      Se voce clicou neste arquivo DE DENTRO do zip, o Windows o
  echo      copiou para uma pasta temporaria sozinho. Extraia o zip
  echo      primeiro ^(botao direito - "Extrair Tudo"^) e rode de la.
  echo.
  echo      Pasta atual: %CD%
  echo.
  pause
  exit /b 1
)

call :ACHAR_PYTHON
if not defined PY (
  echo.
  echo  [X] NAO ENCONTREI O PYTHON.
  echo      De dois cliques em INSTALAR_WINDOWS.bat primeiro - ele baixa e
  echo      instala o Python sozinho, se voce deixar.
  echo.
  pause
  exit /b 1
)

REM AS BIBLIOTECAS ENTRARAM? Perguntar aqui evita o pior desfecho: o
REM programa abrir, estourar um ModuleNotFoundError no meio, e o cliente
REM concluir que o produto esta quebrado.
%PY% -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [X] As bibliotecas do programa nao estao instaladas.
  echo      De dois cliques em INSTALAR_WINDOWS.bat primeiro.
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
REM mensagem junto -- o cliente ve um piscar e nao tem o que relatar.
if not "%SAIDA%"=="0" (
  echo.
  echo ======================================================================
  echo   O PROGRAMA FECHOU COM ERRO ^(codigo %SAIDA%^).
  echo.
  echo   As ultimas linhas ACIMA dizem o motivo. Tire uma foto delas antes
  echo   de fechar esta janela -- e com elas que da para consertar.
  echo.
  echo   Se aparecer "ModuleNotFoundError", faltou biblioteca: de dois
  echo   cliques em INSTALAR_WINDOWS.bat e rode de novo.
  echo ======================================================================
  echo.
  pause
)
exit /b 0

:ACHAR_PYTHON
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3" && goto :eof
python --version >nul 2>&1 && set "PY=python" && goto :eof
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if exist "%%d\python.exe" set "PY="%%d\python.exe""
)
if defined PY goto :eof
if exist "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" -3"
goto :eof
