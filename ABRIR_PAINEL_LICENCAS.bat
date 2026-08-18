@echo off
REM =====================================================================
REM  Abre o Painel de Licencas NO GOOGLE CHROME (Windows).
REM  Dois cliques neste arquivo.
REM
REM  POR QUE CHROME, E NAO O NAVEGADOR PADRAO
REM  ----------------------------------------
REM  O painel guarda o endereco do servidor e a senha de administrador no
REM  localStorage DO NAVEGADOR QUE ABRIU. Cada navegador tem o seu proprio
REM  localStorage: abrir hoje no Edge e amanha no Chrome significa digitar
REM  a senha de novo, com a sensacao de que "o painel esqueceu tudo".
REM  Fixando o Chrome, a memoria e sempre a mesma.
REM
REM  Sem Chrome instalado ele NAO falha calado: avisa e abre no navegador
REM  padrao, dizendo que a memoria vai ser outra.
REM =====================================================================
cd /d "%~dp0"

if not exist "painel_licencas.html" (
    echo [ERRO] Nao achei o painel_licencas.html nesta pasta.
    echo        Descompacte o zip inteiro e rode de dentro da pasta criada.
    echo.
    echo        Se voce recebeu um pacote SEM o painel, ele foi gerado com
    echo        --sem-painel: e o pacote que vai para CLIENTE, e o painel
    echo        nunca vai junto de proposito.
    pause
    exit /b 1
)

set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if defined CHROME (
    echo Abrindo o Painel de Licencas no Google Chrome...
    start "" "%CHROME%" "%CD%\painel_licencas.html"
) else (
    echo [AVISO] Google Chrome nao encontrado nesta maquina.
    echo         Vou abrir no navegador padrao.
    echo         Atencao: o endereco do servidor e a senha ficam guardados
    echo         por NAVEGADOR. Se voce costuma usar o Chrome, vai precisar
    echo         digitar os dois de novo aqui.
    start "" "%CD%\painel_licencas.html"
)
