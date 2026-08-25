@echo off
setlocal EnableDelayedExpansion
title SMC Quant Pro - Gerar o instalador do cliente

REM =====================================================================
REM  GERA O setup.exe QUE O CLIENTE RECEBE.  DOIS CLIQUES AQUI.
REM
REM  ESTE ARQUIVO E SEU, NAO DO CLIENTE. Ele roda na SUA maquina Windows e
REM  produz um unico arquivo para enviar:
REM
REM      SMC_Quant_Pro_Setup_<versao>.exe
REM
REM  O cliente da dois cliques nesse setup e acabou: sem Python, sem
REM  prompt de comando, sem pip, sem .bat. Foi o pedido dele, e estava
REM  certo -- "o cliente nao tem que abrir prompt de comando, precisa ser
REM  o pacote, com o executavel exe, simples".
REM
REM  O QUE ELE FAZ, EM ORDEM:
REM    1. confere o Python (e instala, se faltar)
REM    2. confere o PyInstaller (e instala, se faltar)
REM    3. compila:  dist\SMC_Quant_Pro\SMC_Quant_Pro.exe
REM    4. acha o Inno Setup e compila o instalador
REM    5. diz onde ficou o setup.exe pronto para enviar
REM
REM  Cada passo PARA na primeira falha, dizendo qual foi. Seguir depois de
REM  um passo falho produziria um instalador incompleto -- que e pior que
REM  instalador nenhum, porque so falha na maquina do cliente.
REM =====================================================================

cd /d "%~dp0"

echo.
echo ======================================================================
echo   GERAR O INSTALADOR DO CLIENTE (Windows)
echo   Pasta: %CD%
echo ======================================================================
echo.

if not exist "main_app.py" (
  echo  [X] Nao achei o main_app.py. Este arquivo tem de ficar na pasta
  echo      do projeto, ao lado do main_app.py.
  echo.
  pause
  exit /b 1
)

call :ACHAR_PYTHON
if not defined PY (
  echo  [X] Python nao encontrado. Rode o INSTALAR_WINDOWS.bat primeiro:
  echo      ele baixa e instala o Python sozinho.
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do set "VPY=%%v"
echo  [ok] Python: !VPY!

REM ---------------------------------------------------------------------
REM PASSO 1 - PYINSTALLER
REM ---------------------------------------------------------------------
%PY% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo  [..] Instalando o PyInstaller...
  %PY% -m pip install --upgrade pyinstaller
  %PY% -c "import PyInstaller" >nul 2>&1
  if errorlevel 1 (
    echo  [X] Nao consegui instalar o PyInstaller. Sem ele nao ha .exe.
    echo.
    pause
    exit /b 1
  )
)
echo  [ok] PyInstaller pronto.

REM AS BIBLIOTECAS DO PROGRAMA TAMBEM PRECISAM ESTAR AQUI. O PyInstaller
REM empacota o que ele CONSEGUE IMPORTAR: uma biblioteca faltando na sua
REM maquina vira uma biblioteca faltando no .exe do cliente, e o defeito so
REM aparece la.
%PY% -c "import customtkinter, PIL, requests" >nul 2>&1
if errorlevel 1 (
  echo  [..] Faltam bibliotecas do programa. Instalando...
  %PY% -m pip install -r requirements.txt
)

REM ---------------------------------------------------------------------
REM PASSO 2 - COMPILAR O .EXE
REM
REM Limpar build\ e dist\ antes NAO e zelo: o PyInstaller reaproveita o que
REM achar la, e um resto de compilacao anterior entra no pacote novo sem
REM avisar. Ja e o bastante para o cliente receber codigo velho dentro de
REM um instalador com numero novo.
REM ---------------------------------------------------------------------
echo.
echo  [..] Limpando compilacoes anteriores...
if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"

echo  [..] Compilando o programa. Isso leva alguns minutos.
echo.
%PY% -m PyInstaller --noconfirm SMC_Quant_Pro.spec
if errorlevel 1 goto FALHOU_COMPILAR

if not exist "dist\SMC_Quant_Pro\SMC_Quant_Pro.exe" goto FALHOU_COMPILAR
echo.
echo  [ok] Executavel pronto: dist\SMC_Quant_Pro\SMC_Quant_Pro.exe

REM ---------------------------------------------------------------------
REM PASSO 3 - O INNO SETUP
REM
REM Procurado nos lugares padrao dos dois formatos (64 e 32 bits) porque o
REM Inno Setup nao poe o ISCC.exe no PATH por conta propria.
REM ---------------------------------------------------------------------
set "ISCC="
where iscc >nul 2>&1 && set "ISCC=iscc"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"

if not defined ISCC (
  echo.
  echo  [!] O Inno Setup nao esta instalado nesta maquina.
  echo.
  echo      O EXECUTAVEL JA ESTA PRONTO -- o que falta e so embrulhar num
  echo      instalador. Baixe o Inno Setup 6 (gratuito) em
  echo          https://jrsoftware.org/isdl.php
  echo      instale, e de dois cliques NESTE arquivo de novo.
  echo.
  echo      Enquanto isso da para entregar a pasta dist\SMC_Quant_Pro
  echo      compactada -- funciona, mas o cliente tem de descompactar e
  echo      achar o .exe, que e justamente o que queremos evitar.
  echo.
  pause
  exit /b 1
)
echo  [ok] Inno Setup: %ISCC%

echo.
echo  [..] Montando o instalador...
"%ISCC%" "instalador\SMC_Quant_Pro.iss"
if errorlevel 1 (
  echo.
  echo  [X] O INNO SETUP FALHOU. A mensagem dele esta acima, com o numero
  echo      da linha do .iss. Tire uma foto desta tela.
  echo.
  pause
  exit /b 1
)

echo.
echo ======================================================================
echo   PRONTO. O INSTALADOR DO CLIENTE ESTA EM:
echo.
dir /b "instalador\Output\*.exe" 2>nul
dir /b "Output\*.exe" 2>nul
echo.
echo   E ESSE UNICO ARQUIVO que voce envia. O cliente da dois cliques nele
echo   e acabou -- ele nao precisa de Python, nem de prompt, nem de nada.
echo ======================================================================
echo.
pause
exit /b 0

:FALHOU_COMPILAR
echo.
echo  [X] A COMPILACAO FALHOU.
echo.
echo      As ultimas linhas acima dizem o motivo. As causas comuns sao:
echo        - uma biblioteca do requirements.txt que nao instalou aqui;
echo        - antivirus segurando a escrita na pasta dist\;
echo        - a pasta dist\ aberta no Explorer (feche e tente de novo).
echo.
pause
exit /b 1

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
