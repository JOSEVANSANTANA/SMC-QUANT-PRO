@echo off
setlocal EnableDelayedExpansion
title SMC Quant Pro - Instalacao no Windows

REM =====================================================================
REM  SMC Quant Pro - instalacao no Windows.  DE DOIS CLIQUES NESTE ARQUIVO.
REM
REM  ELE INSTALA O QUE FALTAR: Python, Node.js e as bibliotecas. O cliente
REM  nao precisa saber o que e nada disso.
REM
REM  ASCII PURO E QUEBRA CRLF, e isso nao e estilo. O cmd.exe EXIGE CRLF:
REM  com quebra de linha do Unix ele executa cada COMENTARIO como se fosse
REM  comando, e a tela do cliente encheu de "'PASSO' nao e reconhecido como
REM  um comando interno". Acento depende da pagina de codigo do console,
REM  que varia de maquina, e e outra forma de virar lixo na tela.
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
REM ANTES DE TUDO: ELE DESCOMPACTOU O ZIP?
REM
REM O Windows deixa dar DOIS CLIQUES NUM ARQUIVO DENTRO DO ZIP. Ele extrai
REM para uma pasta temporaria, roda, e depois APAGA. A instalacao inteira
REM iria para o lixo sem ninguem entender por que o programa "sumiu".
REM
REM E o sintoma seguinte seria pior: o ABRIR nao acharia o main_app.py e o
REM cliente concluiria que o pacote veio quebrado.
REM ---------------------------------------------------------------------
echo %CD% | find /i "\Temp\" >nul && goto DENTRO_DO_ZIP
echo %CD% | find /i "\AppData\Local\Temp" >nul && goto DENTRO_DO_ZIP
if not exist "main_app.py" goto DENTRO_DO_ZIP
goto PASTA_OK

:DENTRO_DO_ZIP
echo  [X] PARE: parece que voce esta rodando de DENTRO do arquivo ZIP.
echo.
echo      O Windows deixa clicar em arquivos dentro do zip, mas eles rodam
echo      numa pasta temporaria que ele APAGA depois. A instalacao iria
echo      toda para o lixo.
echo.
echo      FACA ASSIM:
echo        1. Clique com o botao DIREITO no arquivo .zip
echo        2. Escolha "Extrair Tudo..."  (ou "Extract All...")
echo        3. Escolha uma pasta simples, por exemplo:  C:\SMC_QUANT_PRO
echo        4. ENTRE na pasta extraida e de dois cliques neste arquivo
echo.
echo      Pasta atual: %CD%
echo.
pause
exit /b 1

:PASTA_OK

REM ---------------------------------------------------------------------
REM ONEDRIVE: o mesmo problema que o iCloud causa no Mac.
REM
REM O OneDrive tira do disco os arquivos que voce nao usa ha um tempo e
REM deixa so um marcador. Quando o programa for ler um deles, ele nao vai
REM estar la -- e a falha aparece no meio do pregao, sem explicacao, num
REM arquivo que funcionava ontem. NAO PARA a instalacao: e um aviso, e a
REM decisao e dele.
REM ---------------------------------------------------------------------
echo %CD% | find /i "OneDrive" >nul
if not errorlevel 1 (
  echo  [!] AVISO: esta pasta esta dentro do OneDrive.
  echo      O OneDrive tira arquivos do disco para poupar espaco e deixa so
  echo      um marcador. Quando o programa for ler um deles no meio do
  echo      pregao, ele pode nao estar la.
  echo      O ideal e mover a pasta para algo como  C:\SMC_QUANT_PRO
  echo.
)

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
REM administrador, que e onde metade das instalacoes para. PrependPath=1 e
REM a caixa "Add python.exe to PATH" que todo mundo esquece de marcar.
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

REM O PYTHON PODE SER VELHO DEMAIS. Uma maquina com 3.7 instalado passa em
REM "achei o Python" e depois falha pacote por pacote, sem dizer a causa.
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [X] Este Python e ANTIGO DEMAIS para o programa ^(precisa ser 3.9+^).
  echo      Instale o 3.12 em https://www.python.org/downloads/ e marque
  echo      "Add python.exe to PATH" na primeira tela.
  echo.
  pause
  exit /b 1
)

REM ---------------------------------------------------------------------
REM PASSO 2 - NODE.JS (o motor do WhatsApp)
REM
REM NAO PARA A INSTALACAO se o cliente recusar: o programa abre e opera sem
REM o Node, e o que fica de fora e o envio de relatorio pelo WhatsApp.
REM Parar tudo aqui custaria o programa inteiro por causa de um recurso.
REM ---------------------------------------------------------------------
call :ACHAR_NODE
if defined NODE goto NODE_OK

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
REM ---------------------------------------------------------------------
REM O /qn PRECISA DE ADMINISTRADOR, E FALHA EM SILENCIO SEM ELE.
REM
REM 25/08, cliente: autorizou o download do Node, a instalacao "rodou", e o
REM programa continuou dizendo "Node.js nao encontrado". O msiexec com /qn
REM (quieto, sem interface) instala PARA A MAQUINA INTEIRA -- e isso exige
REM elevacao. Sem UAC para pedir, ele desiste sem mostrar nada, e o cliente
REM fica achando que autorizou algo que aconteceu.
REM
REM Duas saidas, nesta ordem: primeiro tenta quieto (funciona se a janela ja
REM estiver elevada); se nao der, ABRE O INSTALADOR NORMAL, com as telas --
REM ai o Windows pede a senha e o cliente ve o que esta acontecendo. Uma
REM instalacao com dois cliques a mais e muito melhor que uma que falha
REM calada.
REM ---------------------------------------------------------------------
msiexec /i "%TEMP%\smc_node_setup.msi" /qn /norestart
call :ACHAR_NODE
if defined NODE goto NODE_INSTALADO

echo      A instalacao silenciosa nao passou (o Windows costuma exigir
echo      senha de administrador para o Node). Vou abrir o instalador
echo      normal: siga as telas, e ACEITE se ele pedir permissao.
echo.
start /wait "" msiexec /i "%TEMP%\smc_node_setup.msi" /norestart
call :ACHAR_NODE

:NODE_INSTALADO
del /q "%TEMP%\smc_node_setup.msi" >nul 2>&1
if defined NODE (
  echo  [ok] Node.js instalado: !NODE!
) else (
  echo  [!] O Node.js ainda nao aparece. O programa VAI ABRIR e operar
  echo      normalmente -- o que fica de fora e so o envio de relatorio
  echo      pelo WhatsApp. Da para instalar depois por https://nodejs.org
)
goto NODE_FIM

:NODE_OK
echo  [ok] Node.js: !NODE!
:NODE_FIM

REM ---------------------------------------------------------------------
REM PASSO 3 - BIBLIOTECAS
REM
REM UM PACOTE RUIM NAO PODE DERRUBAR A INSTALACAO INTEIRA, e essa era a
REM armadilha: `pip install -r requirements.txt` e tudo-ou-nada. A lista
REM tem itens que so existem em certas versoes do Windows e do Python --
REM os `winrt-*`, que servem SO para leitura de texto na tela. Se um deles
REM nao tivesse pacote pronto para a maquina do cliente, o pip devolvia
REM erro, o instalador parava, e o cliente ficava sem o programa por causa
REM de um recurso que ele talvez nem use.
REM
REM Agora: tenta a lista inteira; se falhar, instala um por um; e no fim
REM CONFERE O QUE IMPORTA DE VERDADE. O que faltar e dito pelo nome, com o
REM que se perde -- em vez de um "erro" generico.
REM ---------------------------------------------------------------------
echo.
echo  Instalando as bibliotecas. Na primeira vez leva alguns minutos --
echo  e normal a tela ficar parada durante o download.
echo.
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if not errorlevel 1 goto CONFERIR

echo.
echo  [!] A lista inteira nao passou de uma vez. Vou instalar um por um,
echo      para que um pacote problematico nao leve os outros junto.
echo.
for /f "usebackq tokens=* delims=" %%p in ("requirements.txt") do (
  set "LINHA=%%p"
  set "LINHA=!LINHA: =!"
  if not "!LINHA!"=="" (
    if not "!LINHA:~0,1!"=="#" (
      echo      - !LINHA!
      %PY% -m pip install "!LINHA!" >nul 2>&1 || echo        ^(falhou: !LINHA!^)
    )
  )
)

:CONFERIR
REM CONFERIR IMPORTANDO E A UNICA PROVA REAL. `pip install` pode terminar
REM sem erro e ainda deixar o pywin32 sem registrar as extensoes -- a mesma
REM regra que o programa aplica aos campos da corretora: nao basta
REM escrever, tem de ler de volta.
echo.
echo  Conferindo o que entrou de verdade...
set "FALTOU="
call :CONFERIR_UM customtkinter "a janela do programa"
call :CONFERIR_UM PIL           "a leitura das imagens do grafico"
call :CONFERIR_UM requests      "a conversa com a internet"
call :CONFERIR_UM win32gui      "listar janelas e capturar o grafico"

if defined FALTOU (
  echo.
  echo  [X] FALTA COISA ESSENCIAL: !FALTOU!
  echo      Sem isso o programa nao abre. Tente rodar este arquivo de novo;
  echo      se insistir, tire uma foto desta tela.
  echo.
  pause
  exit /b 1
)

REM O pywin32 as vezes instala e nao registra. Vale uma tentativa antes de
REM desistir -- e barato, e evita uma ida e volta com o suporte.
%PY% -c "import win32gui" >nul 2>&1
if errorlevel 1 (
  %PY% -m pip install --force-reinstall pywin32 >nul 2>&1
)

echo.
echo  Conferindo os opcionais ^(o programa abre sem eles^)...
call :OPCIONAL "winrt.windows.media.ocr" "ler texto da tela por OCR"
call :OPCIONAL "sounddevice"             "falar com a TIGER pelo microfone"
call :OPCIONAL "pypdf"                   "ler PDF de outras corretoras (ja existe leitor proprio)"

echo.
echo ======================================================================
echo   PRONTO. INSTALACAO CONCLUIDA.
echo.
echo   Para usar o programa, de DOIS CLIQUES em:
echo       ABRIR_SMC_QUANT_PRO.bat
echo.
echo   Na primeira vez ele vai pedir a CHAVE DE LICENCA - e a que voce
echo   recebeu ao adquirir o produto.
echo ======================================================================
echo.
pause
exit /b 0

REM ---------------------------------------------------------------------
:CONFERIR_UM
%PY% -c "import %~1" >nul 2>&1
if errorlevel 1 (
  set "FALTOU=!FALTOU! %~1"
  echo  [X] %~1 - sem ele nao ha %~2
) else (
  echo  [ok] %~1 - %~2
)
goto :eof

:OPCIONAL
%PY% -c "import %~1" >nul 2>&1
if errorlevel 1 (
  echo  [--] %~1 nao entrou. O que fica de fora: %~2.
  echo       O programa abre e opera normalmente.
) else (
  echo  [ok] %~1 - %~2
)
goto :eof

REM ---------------------------------------------------------------------
REM ACHAR O PYTHON, inclusive o que acabou de ser instalado.
REM
REM `py -3` (o Python Launcher) vem ANTES de `python` porque no Windows o
REM comando `python` pode cair na loja da Microsoft e abrir uma pagina em
REM vez de rodar -- beco sem saida que ja fez gente achar que o Python nao
REM estava instalado quando estava.
REM
REM Os dois ultimos caminhos existem porque a mudanca de PATH nao vale na
REM janela que ja esta aberta. Sem procurar neles, o instalador acabaria de
REM instalar o Python e diria em seguida que nao achou Python nenhum.
REM ---------------------------------------------------------------------
:ACHAR_NODE
REM PROCURA NO PATH **E** NOS LUGARES CONHECIDOS. O PATH e lido quando o
REM processo nasce: logo depois de instalar o Node, esta janela ainda nao o
REM enxerga. Foi assim que um cliente autorizou a instalacao, ela funcionou,
REM e o programa continuou dizendo que nao havia Node.
set "NODE="
where node >nul 2>&1 && set "NODE=node" && goto :eof
if exist "%ProgramFiles%\nodejs\node.exe" set "NODE=%ProgramFiles%\nodejs\node.exe" && goto :eof
if exist "%ProgramFiles(x86)%\nodejs\node.exe" set "NODE=%ProgramFiles(x86)%\nodejs\node.exe" && goto :eof
if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" set "NODE=%LOCALAPPDATA%\Programs\nodejs\node.exe" && goto :eof
goto :eof

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
