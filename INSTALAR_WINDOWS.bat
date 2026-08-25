@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title SMC Quant Pro - Instalacao no Windows

REM =====================================================================
REM  SMC Quant Pro — instalacao no Windows
REM
REM  COMO USAR: de DOIS CLIQUES neste arquivo.
REM
REM  POR QUE ESTE ARQUIVO EXISTE
REM  ---------------------------
REM  O pacote do Mac sempre teve seis arquivos de dois cliques
REM  (INSTALAR_MAC.command, ABRIR_SMC_QUANT_PRO.command, e outros). O do
REM  Windows tinha ZERO. Quem recebia o zip no Windows abria a pasta, nao
REM  encontrava nada para clicar, e ia procurar.
REM
REM  Foi exatamente o que aconteceu com o primeiro cliente: ele vasculhou as
REM  pastas, achou "instalador\SMC_Quant_Pro.iss" e abriu — que e o script
REM  do Inno Setup, a ferramenta de COMPILACAO. Ele ficou olhando para uma
REM  tela de programador sem ter o que fazer ali. A culpa nao foi dele; a
REM  pasta nao devia estar no pacote, e este arquivo nao existia.
REM
REM  Ele NAO instala nada escondido e NAO mexe em nada fora desta pasta,
REM  exceto as bibliotecas Python que o programa precisa. Cada passo e
REM  anunciado antes de rodar, e qualquer falha PARA aqui em vez de seguir
REM  fingindo que deu certo.
REM =====================================================================

cd /d "%~dp0"

echo.
echo ======================================================================
echo   SMC QUANT PRO - INSTALACAO NO WINDOWS
echo   Pasta: %CD%
echo ======================================================================
echo.

REM ---------------------------------------------------------------------
REM PASSO 1 - PYTHON
REM
REM `py -3` (o Python Launcher) e tentado ANTES de `python`, porque no
REM Windows o comando `python` pode cair na loja da Microsoft e abrir uma
REM pagina em vez de rodar — um beco sem saida que ja fez gente achar que
REM o Python nao estava instalado quando estava.
REM ---------------------------------------------------------------------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [X] NAO ENCONTREI O PYTHON.
  echo.
  echo     Baixe o Python 3.11 ou 3.12 em https://www.python.org/downloads/
  echo     Na PRIMEIRA tela do instalador, MARQUE a caixa:
  echo         "Add python.exe to PATH"
  echo.
  echo     Essa caixa e a parte que todo mundo esquece. Sem ela o Windows
  echo     nao acha o Python, mesmo com ele instalado.
  echo.
  echo     Depois de instalar, de dois cliques NESTE arquivo de novo.
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do set "VPY=%%v"
echo [ok] Python encontrado: !VPY!

REM ---------------------------------------------------------------------
REM PASSO 2 - NODE.JS (o motor do WhatsApp)
REM
REM NAO PARA A INSTALACAO. O programa abre e opera sem o Node; o que fica
REM de fora e o envio de relatorio pelo WhatsApp. Parar tudo aqui custaria
REM ao cliente o programa inteiro por causa de um recurso.
REM ---------------------------------------------------------------------
node -v >nul 2>&1
if errorlevel 1 (
  echo [!] Node.js NAO encontrado.
  echo     O programa vai abrir e operar normalmente, mas o envio de
  echo     relatorio pelo WhatsApp fica de fora ate voce instalar.
  echo     Baixe a versao LTS em https://nodejs.org
) else (
  for /f "delims=" %%n in ('node -v 2^>^&1') do set "VNODE=%%n"
  echo [ok] Node.js encontrado: !VNODE!
)

REM ---------------------------------------------------------------------
REM PASSO 3 - BIBLIOTECAS
REM ---------------------------------------------------------------------
echo.
echo  Instalando as bibliotecas do programa. Isso leva alguns minutos na
echo  primeira vez -- e normal a tela ficar parada durante o download.
echo.
%PY% -m pip install --upgrade pip
if errorlevel 1 (
  echo.
  echo [X] Nao consegui atualizar o pip. Confira sua conexao e tente de novo.
  pause
  exit /b 1
)
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [X] A INSTALACAO DAS BIBLIOTECAS FALHOU.
  echo.
  echo     Leia a ultima linha vermelha acima: ela costuma dizer qual
  echo     biblioteca falhou e por que. O item que NAO pode faltar e o
  echo     pywin32 -- sem ele o programa nao lista as janelas abertas e
  echo     nao consegue capturar o grafico.
  echo.
  pause
  exit /b 1
)

REM ---------------------------------------------------------------------
REM CONFERENCIA: o pywin32 entrou mesmo?
REM
REM `pip install` pode terminar sem erro e ainda assim deixar o pywin32
REM sem registrar as extensoes. Conferir importando e a unica prova real —
REM a mesma regra que o programa aplica aos campos da corretora: nao basta
REM escrever, tem de ler de volta.
REM ---------------------------------------------------------------------
%PY% -c "import win32gui" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [!] O pywin32 instalou mas nao esta importando.
  echo     Rode este comando no Prompt e tente de novo:
  echo         %PY% -m pip install --force-reinstall pywin32
  echo.
) else (
  echo [ok] pywin32 conferido - o programa consegue ver as janelas.
)

echo.
echo ======================================================================
echo   PRONTO. INSTALACAO CONCLUIDA.
echo.
echo   Para usar o programa, de DOIS CLIQUES em:
echo       ABRIR_SMC_QUANT_PRO.bat
echo.
echo   O passo a passo completo esta no LEIA-ME_WINDOWS.txt
echo ======================================================================
echo.
pause
