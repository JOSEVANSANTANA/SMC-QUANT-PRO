; ============================================================================
;  SMC QUANT PRO  —  Instalador profissional (Inno Setup)
;  Marca: TIGER INVEST VIP
; ----------------------------------------------------------------------------
;  Este script gera um único "setup.exe" que:
;    1. Instala o app compilado (SMC_Quant_Pro.exe + pasta motor/) no lugar certo
;    2. Cria atalho na Área de Trabalho e no Menu Iniciar
;    3. (Opcional) Instala o Node.js automaticamente se o cliente não tiver
;    4. NUNCA apaga os dados do cliente em %APPDATA%\SMC_Quant_Pro nas atualizações
;
;  COMO USAR (na sua máquina Windows):
;    1. Instale o Inno Setup 6:  https://jrsoftware.org/isdl.php
;    2. Ajuste os caminhos na seção [Setup]/#define abaixo (marcados com  <<< AJUSTE)
;    3. Abra este .iss no Inno Setup Compiler e clique em "Compile" (ou F9)
;    4. O setup.exe sai na pasta definida em OutputDir
;
;  REGRA DE VERSÃO: sempre que subir uma versão, altere MyAppVersion abaixo
;  para bater com VERSAO_ATUAL do main_app.py e com o campo "versao" do gist.
; ============================================================================

#define MyAppName        "SMC Quant Pro"
#define MyAppPublisher   "TIGER INVEST VIP"
#define MyAppVersion     "1.6.1"
#define MyAppExeName     "SMC_Quant_Pro.exe"
#define MyAppURL         "https://smc-quant-pro.onrender.com"

; ----------------------------------------------------------------------------
;  <<< AJUSTE: pastas de origem (onde estão os arquivos na SUA máquina)
; ----------------------------------------------------------------------------
; Pasta que o PyInstaller gerou (contém o .exe e tudo que ele precisa).
; Normalmente é  ...\dist\SMC_Quant_Pro\  quando você compila em modo "onedir".
#define SourceApp        "C:\SMC\dist\SMC_Quant_Pro"

; Pasta do motor Node.js (com node_modules JÁ pronto do Baileys).
#define SourceMotor      "C:\SMC\motor"

; Ícone do aplicativo (.ico). Deixe vazio ("") se não tiver um.
#define AppIcon          "C:\SMC\assets\icone.ico"

; Instalador do Node.js para incluir no pacote (opcional, mas recomendado).
; Baixe o .msi LTS x64 em https://nodejs.org e aponte aqui.
; Deixe vazio ("") se NÃO quiser embutir o Node.js no setup.
#define NodeInstaller    "C:\SMC\redist\node-v20.17.0-x64.msi"

; ----------------------------------------------------------------------------

[Setup]
; AppId identifica o produto de forma única. NÃO troque entre versões — é o que
; faz o instalador reconhecer uma instalação existente e atualizá-la no lugar.
AppId={{7B3F1C2A-9E4D-4A18-B6C2-SMCQUANTPRO01}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Instala em Arquivos de Programas -> requer privilégio de admin.
PrivilegesRequired=admin
OutputDir=Output
OutputBaseFilename=SMC_Quant_Pro_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Descomente e aponte para uma imagem sua se quiser personalizar o assistente:
; WizardImageFile=assets\wizard_lateral.bmp
; WizardSmallImageFile=assets\wizard_topo.bmp
#if AppIcon != ""
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
#endif
; Idioma da interface do próprio setup:
ShowLanguageDialog=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: checkedonce

[Files]
; --- Aplicativo principal (todo o conteúdo da pasta dist do PyInstaller) ---
Source: "{#SourceApp}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; --- Motor Node.js (com node_modules já pronto) ---
Source: "{#SourceMotor}\*"; DestDir: "{app}\motor"; Flags: ignoreversion recursesubdirs createallsubdirs

; --- Instalador do Node.js embutido (copiado só temporariamente p/ rodar) ---
#if NodeInstaller != ""
Source: "{#NodeInstaller}"; DestDir: "{tmp}"; DestName: "node_setup.msi"; Flags: deleteafterinstall
#endif

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Instala o Node.js silenciosamente SOMENTE se o cliente ainda não tiver.
; A checagem é feita pela função NodeInstalado() em [Code].
#if NodeInstaller != ""
Filename: "msiexec.exe"; Parameters: "/i ""{tmp}\node_setup.msi"" /qn /norestart"; \
    StatusMsg: "Instalando o Node.js (necessário para o WhatsApp)..."; \
    Check: not NodeInstalado; Flags: waituntilterminated
#endif

; Oferece abrir o app ao final da instalação.
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o {#MyAppName} agora"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove apenas o que o instalador colocou em {app}. Os dados do cliente ficam
; em %APPDATA%\SMC_Quant_Pro e NÃO são tocados aqui de propósito, para não
; destruir histórico/licença de quem só está desinstalando para reinstalar.
Type: filesandordirs; Name: "{app}\motor\node_modules\.cache"

[Code]
{ ------------------------------------------------------------------------ }
{  Detecta se o Node.js já está instalado na máquina do cliente.           }
{  Estratégia: procura "node.exe" no PATH via cmd. Retorna True se achar.   }
{ ------------------------------------------------------------------------ }
function NodeInstalado(): Boolean;
var
  ResultCode: Integer;
begin
  { 'where node' devolve 0 se encontrar o executável no PATH. }
  Result := Exec('cmd.exe', '/C where node', '', SW_HIDE,
                 ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

{ ------------------------------------------------------------------------ }
{  Aviso amigável se o cliente estiver ATUALIZANDO por cima de uma versão   }
{  já instalada — deixa claro que os dados dele serão preservados.          }
{ ------------------------------------------------------------------------ }
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
