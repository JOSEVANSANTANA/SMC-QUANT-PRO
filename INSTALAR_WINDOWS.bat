@echo off
setlocal EnableDelayedExpansion
title SMC Quant Pro - Instalacao no Windows

REM =====================================================================
REM  SMC Quant Pro - instalacao no Windows.  DE DOIS CLIQUES NESTE ARQUIVO.
REM
REM  ELE INSTALA O QUE FALTAR. Pedido dele: "era para ta tudo incluso no
REM  pacote, certifique-se de incluir ja na opcao do cmd o download do
REM  python se o cliente nao tiver".
REM
REM  Antes este arquivo so DIZIA "baixe o Python em python.org" e parava.
REM  Mandar o cliente para uma pagina de download no meio da instalacao e
REM  onde a instalacao morre: ele nao sabe qual versao, nao sabe que tem de
REM  marcar "Add python.exe to PATH", e some.
REM
REM  DUAS COISAS SOBRE ESTE ARQUIVO SEREM ASCII E TEREM QUEBRA CRLF:
REM  o cmd.exe do Windows EXIGE CRLF. Com quebra de linha do Unix ele le o
REM  arquivo errado e passa a executar cada linha de comentario como se
REM  fosse comando -- foi exatamente o que apareceu na tela do cliente:
REM  "'PASSO' nao e reconhecido como um comando interno". E acento depende
REM  da pagina de codigo do console, que varia de maquina. Os dois juntos
REM  transformam o instalador em lixo na tela.
REM =====================================================================

cd /d "%~dp0"

REM OS ENDERECOS SAO OFICIAIS E FICAM A VISTA, nao escondidos no meio do
REM script: o cliente le o que vai ser baixado ANTES de autorizar.
set "PY_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
set "NODE_URL=https://nodejs.org/dist/v20.17.0/node-v20.17.0-x64.msi"

echo.
echo ======================================================================
echo   SMC QUANT PRO - INSTALACAO NO WINDOWS
echo   Pasta: %CD%
echo ======================================================================
echo.

REM ---------------------------------------------------------------------
REM COMO BAIXAR. O curl.exe vem no Windows 10 (1803+) e no 11. Onde nao
REM houver, o PowerShell resolve. Duas tentativas porque uma so falharia
REM em maquina antiga sem dizer por que.
REM ---------------------------------------------------------------------
set "BAIXAR="
where curl >nul 2>&1 && set "BAIXAR=curl"
if not defined BAIXAR (
  where powershell >nul 2>&1 && set "BAIXAR=powershell"
)

REM ---------------------------------------------------------------------
REM PASSO 1 - PYTHON
REM
REM `py -3` (o Python Launcher) e tentado ANTES de `python`, porque no
REM Windows o comando `python` pode cair na loja da Microsoft e abrir uma
REM pagina em vez de rodar -- beco sem saida que ja fez gente achar que o
REM Python nao estava instalado quando estava.
REM ---------------------------------------------------------------------
call :ACHAR_PYTHON
if defined PY goto PYTHON_OK

echo  [!] O Python nao esta instalado nesta maquina.
echo.
echo      Eu posso baixar e instalar agora, sozinho. Sao cerca de 25 MB,
echo      direto do site oficial python.org, e a instalacao e SO PARA O
echo      SEU USUARIO -- nao pede senha de administrador e nao mexe em
echo      mais nada do computador.
echo.
echo      Endereco exato: %PY_URL%
echo.
set /p "RESP=     Posso baixar e instalar? (S/N): "
if /i not "!RESP!"=="S" (
  echo.
  echo      Tudo bem. Entao instale o Python 3.12 na mao, em
  echo      https://www.python.org/downloads/
  echo      Na PRIMEIRA tela, MARQUE "Add python.exe to PATH".
  echo      Depois de dois cliques NESTE arquivo de novo.
  echo.
  pause
  exit /b 1
)

if not defined BAIXAR (
  echo.
  echo  [X] Nao achei nem o curl nem o PowerShell para baixar o arquivo.
  echo      Instale o Python na mao em https://www.python.org/downloads/
  echo      e marque "Add python.exe to PATH" na primeira tela.
  echo.
  pause
  exit /b 1
)

echo.
echo      Baixando o Python... (25 MB - pode levar um minuto)
if "%BAIXAR%"=="curl" (
  curl -L -o "%TEMP%\smc_python_setup.exe" "%PY_URL%"
) else (
  powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%TEMP%\smc_python_setup.exe'"
)
if not exist "%TEMP%\smc_python_setup.exe" (
  echo.
  echo  [X] O DOWNLOAD FALHOU. Confira a conexao com a internet.
  echo      Se estiver numa rede de empresa, o firewall pode estar
  echo      bloqueando o python.org.
  echo.
  pause
  exit /b 1
)

echo      Instalando o Python. NAO feche esta janela.
REM InstallAllUsers=0 instala SO para este usuario: nao pede senha de
REM administrador. PrependPath=1 e a caixa "Add python.exe to PATH" que
REM todo mundo esquece de marcar -- aqui ela vem marcada por padrao.
"%TEMP%\smc_python_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
del /q "%TEMP%\smc_python_setup.exe" >nul 2>&1

REM A MUDANCA DE PATH NAO VALE NESTA JANELA, e este e o detalhe que faria
REM tudo parecer ter falhado logo depois de dar certo: o PATH e lido quando
REM o processo nasce, e este cmd nasceu antes da instalacao. Por isso
REM procuramos o python.exe no lugar onde ele acabou de ser posto.
call :ACHAR_PYTHON
if not defined PY (
  echo.
  echo  [!] O Python foi instalado, mas esta janela ainda nao o enxerga.
  echo      Isso e normal: o Windows so atualiza o PATH em janelas NOVAS.
  echo      FECHE esta janela e de dois cliques neste arquivo de novo.
  echo.
  pause
  exit /b 0
)

:PYTHON_OK
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do set "VPY=%%v"
echo  [ok] Python: !VPY!

REM ---------------------------------------------------------------------
REM PASSO 2 - NODE.JS (o motor do WhatsApp)
REM
REM NAO PARA A INSTALACAO se o cliente recusar: o programa abre e opera sem
REM o Node, e o que fica de fora e o envio de relatorio pelo WhatsApp.
REM Parar tudo aqui custaria o programa inteiro por causa de um recurso.
REM ---------------------------------------------------------------------
node -v >nul 2>&1
if not errorlevel 1 goto NODE_OK

echo.
echo  [!] O Node.js nao esta instalado. Ele serve para UMA coisa: mandar o
echo      relatorio pelo WhatsApp. Sem ele o programa abre e opera igual.
echo.
echo      Endereco exato: %NODE_URL%
echo.
set /p "RESPN=     Posso baixar e instalar o Node.js tambem? (S/N): "
if /i not "!RESPN!"=="S" (
  echo      Ok, seguindo sem o Node. Da para instalar depois por
  echo      https://nodejs.org e o WhatsApp passa a funcionar.
  goto NODE_FIM
)
if not defined BAIXAR goto NODE_FIM

echo      Baixando o Node.js...
if "%BAIXAR%"=="curl" (
  curl -L -o "%TEMP%\smc_node_setup.msi" "%NODE_URL%"
) else (
  powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%NODE_URL%' -OutFile '%TEMP%\smc_node_setup.msi'"
)
if not exist "%TEMP%\smc_node_setup.msi" (
  echo      [!] O download do Node falhou. Seguindo sem ele.
  goto NODE_FIM
)
echo      Instalando o Node.js...
msiexec /i "%TEMP%\smc_node_setup.msi" /qn /norestart
del /q "%TEMP%\smc_node_setup.msi" >nul 2>&1
goto NODE_FIM

:NODE_OK
for /f "delims=" %%n in ('node -v 2^>^&1') do set "VNODE=%%n"
echo  [ok] Node.js: !VNODE!
:NODE_FIM

REM ---------------------------------------------------------------------
REM PASSO 3 - BIBLIOTECAS
REM ---------------------------------------------------------------------
echo.
echo  Instalando as bibliotecas do programa. Na primeira vez leva alguns
echo  minutos -- e normal a tela ficar parada durante o download.
echo.
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo  [X] A INSTALACAO DAS BIBLIOTECAS FALHOU.
  echo      Leia a ultima linha vermelha acima: ela costuma dizer qual
  echo      biblioteca falhou e por que. O item que NAO pode faltar e o
  echo      pywin32 -- sem ele o programa nao lista as janelas abertas e
  echo      nao consegue capturar o grafico.
  echo.
  pause
  exit /b 1
)

REM CONFERENCIA: o pywin32 entrou MESMO?
REM `pip install` pode terminar sem erro e ainda assim deixar o pywin32 sem
REM registrar as extensoes. Conferir importando e a unica prova real -- a
REM mesma regra que o programa aplica aos campos da corretora: nao basta
REM escrever, tem de ler de volta.
%PY% -c "import win32gui" >nul 2>&1
if errorlevel 1 (
  echo  [!] O pywin32 instalou mas nao esta importando. Tentando consertar...
  %PY% -m pip install --force-reinstall pywin32 >nul 2>&1
  %PY% -c "import win32gui" >nul 2>&1
  if errorlevel 1 (
    echo  [!] Ainda nao importa. O programa vai abrir, mas nao vai
    echo      conseguir listar as janelas nem capturar o grafico.
  ) else (
    echo  [ok] pywin32 consertado.
  )
) else (
  echo  [ok] pywin32 conferido - o programa consegue ver as janelas.
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
exit /b 0

REM ---------------------------------------------------------------------
REM ACHAR O PYTHON, inclusive o que acabou de ser instalado.
REM
REM Os dois ultimos caminhos existem porque a mudanca de PATH nao vale na
REM janela que ja esta aberta. Sem procurar neles, o instalador acabaria de
REM instalar o Python e diria em seguida que nao achou Python nenhum.
REM ---------------------------------------------------------------------
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
