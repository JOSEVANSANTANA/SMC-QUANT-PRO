#!/bin/bash
# =====================================================================
#  Cria o "SMC Quant Pro.app" e instala em /Applications.
#  Dois cliques neste arquivo.
#
#  POR QUE NÃO USA O PyInstaller: o .app aqui é um "atalho de verdade" do
#  macOS — uma pasta .app com Info.plist e um lançador que roda os .py
#  desta pasta. Sai em SEGUNDOS, não engorda nada, e continua usando os
#  arquivos que você já tem. Quando eu te mandar uma versão nova, você
#  troca os .py e o app continua valendo, sem recompilar.
#
#  O Info.plist declara as permissões (Gravação de Tela, Microfone). Sem
#  essa declaração o macOS nega em SILÊNCIO: nenhuma caixa aparece, a
#  captura sai preta e ninguém descobre o motivo.
# =====================================================================
set -u
cd "$(dirname "$0")" || exit 1

# ---------------------------------------------------------------------
# AUTO-CURA DA QUARENTENA E AVISO DO iCLOUD
#
# 18/08: dois cliques no CRIAR_APP.command e o Mac respondeu "A Apple nao
# pode verificar se o item esta livre de algum malware", com um botao
# "Mover para o Lixo" ao lado. Todo arquivo vindo de um zip baixado leva a
# marca de quarentena, e script sem assinatura da Apple e bloqueado.
#
# Se ESTE script conseguiu rodar (pelo Terminal, ou pelo botao direito >
# Abrir), a marca ja foi vencida aqui. Entao ele limpa a PASTA INTEIRA de
# uma vez: os outros .command passam a abrir com dois cliques, e o trader
# nao repete o mesmo susto quatro vezes.
xattr -dr com.apple.quarantine "$(pwd)" 2>/dev/null || true

# O iCLOUD TIRA ARQUIVO DO DISCO PARA POUPAR ESPACO e deixa so um marcador.
# Quando o programa vai ler o que foi retirado, ele nao esta la — e a falha
# aparece no meio do pregao, sem explicacao, num arquivo que funcionava
# ontem. No print de 18/08 a pasta estava no iCloud Drive e o proprio
# Finder mostrava "Nao foi possivel concluir a sincronizacao do iCloud".
case "$(pwd)" in
  *"/Library/Mobile Documents/"*|*"/com~apple~CloudDocs/"*)
    echo ""
    echo "======================================================================"
    echo "  AVISO: esta pasta esta dentro do iCLOUD DRIVE."
    echo ""
    echo "  O iCloud retira do disco os arquivos que voce nao usa ha um tempo"
    echo "  e deixa so um marcador. Quando o programa for ler um deles, ele"
    echo "  nao vai estar la — e a falha aparece no meio do pregao."
    echo ""
    echo "  Mova a pasta para um lugar que NAO sincroniza, por exemplo:"
    echo "      $HOME/Applications/SMC_QUANT_PRO"
    echo ""
    echo "  Depois rode os passos do DESBLOQUEAR_MAC.txt de novo."
    echo "======================================================================"
    echo ""
    ;;
esac

PASTA="$(pwd)"
NOME="SMC Quant Pro"
APP="/Applications/${NOME}.app"

echo ""
echo "======================================================"
echo "  CRIANDO O APLICATIVO"
echo "  Programa em: $PASTA"
echo "  Aplicativo:  $APP"
echo "======================================================"
echo ""

falhou() {
    echo ""
    echo "❌ $1"
    echo ""
    read -r -p "Pressione ENTER para fechar."
    exit 1
}

# ---- 1. os arquivos precisam estar aqui ----
for f in main_app.py plataforma.py tradovate_auto.py; do
    [ -f "$f" ] || falhou "Faltou o $f nesta pasta. Descompacte o zip inteiro e rode de dentro da pasta."
done

# ---- 2. achar o Python com Tk ----
PY=""
for cand in \
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
    /opt/homebrew/bin/python3 \
    "$(command -v python3 2>/dev/null)"
do
    [ -x "$cand" ] || continue
    "$cand" -c "import tkinter" >/dev/null 2>&1 && { PY="$cand"; break; }
done
[ -n "$PY" ] || falhou "Não achei um Python com Tk. Rode antes o INSTALAR_MAC.command."
echo "1/4 — Python: $PY"

# ---- 3. montar o bundle ----
echo "2/4 — Montando o aplicativo…"
rm -rf "$APP" 2>/dev/null
if ! mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" 2>/dev/null; then
    falhou "Não consegui escrever em /Applications. Arraste este instalador para uma pasta sua e rode de novo, ou autorize no Finder."
fi

VERSAO="$("$PY" -c "import json;print(json.load(open('versao.json'))['versao'])" 2>/dev/null || echo "2.16.0")"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>${NOME}</string>
  <key>CFBundleDisplayName</key><string>${NOME}</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIdentifier</key><string>com.tigerinvest.smcquantpro</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSAO}</string>
  <key>CFBundleVersion</key><string>${VERSAO}</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSScreenCaptureUsageDescription</key>
  <string>O SMC Quant Pro captura a janela do seu gráfico para que a análise seja feita sobre o que está REALMENTE na tela, sem inventar dados.</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>Usado apenas quando você liga o comando de voz "Olá Tiger".</string>
  <key>NSSpeechRecognitionUsageDescription</key>
  <string>Usado apenas para entender os comandos de voz que você fala.</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>Usado para abrir o Google Chrome na página da corretora.</string>
</dict>
</plist>
PLIST

# ---- O PYTHON PRECISA MORAR DENTRO DO BUNDLE ----
# ESTE É O DEFEITO DO MICROFONE, e ele durou cinco relatos.
#
# O lançador antigo fazia `exec /Library/Frameworks/.../python3 main_app.py`.
# O processo que passa a existir é o PYTHON — um binário que mora FORA do
# .app. E o macOS não atribui permissão a "quem abriu": ele atribui ao
# binário que está pedindo, e ao bundle que CONTÉM esse binário.
#
# Resultado: o Info.plist aqui do lado declarava NSMicrophoneUsageDescription
# certinho, e não servia para nada — porque quem pedia microfone era o
# python3 do /Library/Frameworks, que não tem bundle nenhum. Por isso o
# estado ficava eternamente em "nunca pedido", por isso nada aparecia na
# lista, e por isso autorizar "SMC Quant Pro" e "Terminal" não mudava nada:
# nenhum dos dois era o requerente.
#
# A correção é copiar o executável do Python PARA DENTRO do bundle. Ele
# continua carregando a biblioteca do framework por caminho absoluto, então
# uma cópia simples funciona — e agora o processo em execução está dentro do
# .app, com a identidade e o Info.plist do .app.
cp "$PY" "$APP/Contents/MacOS/python-smc" || falhou "Não consegui copiar o Python para dentro do aplicativo."
chmod +x "$APP/Contents/MacOS/python-smc"

cat > "$APP/Contents/MacOS/launcher" <<LAUNCHER
#!/bin/bash
# Lançador do SMC Quant Pro. Gerado por CRIAR_APP.command.
# O Finder entrega um PATH mínimo (sem /opt/homebrew/bin), e é por isso
# que o Node "some" quando o programa é aberto pelo ícone. Corrigido aqui.
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
cd "${PASTA}" || {
    osascript -e 'display alert "SMC Quant Pro" message "A pasta do programa foi movida ou apagada:\n\n${PASTA}\n\nColoque a pasta de volta, ou rode o CRIAR_APP.command de novo a partir do novo lugar." as critical'
    exit 1
}
# O python DE DENTRO do bundle — é isso que faz o macOS reconhecer o pedido
# de microfone como sendo do "SMC Quant Pro". Ver o comentário no
# CRIAR_APP.command.
exec "\$(dirname "\$0")/python-smc" main_app.py
LAUNCHER
chmod +x "$APP/Contents/MacOS/launcher"

# ---- 4. ícone (opcional) ----
echo "3/4 — Ícone…"
if [ -f "icone.icns" ]; then
    cp "icone.icns" "$APP/Contents/Resources/icone.icns"
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string icone" \
        "$APP/Contents/Info.plist" >/dev/null 2>&1
    echo "      ✅ ícone aplicado"
else
    echo "      ℹ️  sem icone.icns na pasta — o app usa o ícone genérico do macOS."
    echo "         (não atrapalha em nada)"
fi

# ---- 5. tirar a quarentena, ASSINAR e registrar ----
echo "4/4 — Registrando no macOS…"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null

# ASSINATURA AD-HOC — É O QUE FAZ A PERMISSÃO SOBREVIVER À PRÓXIMA VERSÃO.
#
# 28/08. Ele mandou a foto dos Ajustes com "SMC Quant Pro" LIGADO em Gravação
# de Tela, e o macOS reexibiu a caixa pedindo a permissão. As duas coisas
# eram verdade ao mesmo tempo, e a explicação é do sistema:
#
# Um aplicativo SEM ASSINATURA é identificado pelo CONTEÚDO do binário. A
# cada versão nova o conteúdo muda, então para o macOS a versão nova é OUTRO
# programa — que nunca foi autorizado. Só que a linha antiga CONTINUA NA
# LISTA, com o mesmo nome e ainda marcada. A tela mostra concedida; o núcleo
# nega. Ele ficou num laço: marcar de novo não resolve, porque a linha
# marcada é a do programa velho.
#
# A assinatura ad-hoc (--sign -) dá ao pacote uma identidade estável baseada
# no bundle identifier, e não no conteúdo. Não substitui uma Developer ID da
# Apple (que custa e exige conta paga), mas encerra o pior sintoma: a
# permissão deixa de ser revogada em silêncio a cada atualização.
#
# Se o codesign falhar, o app continua funcionando — só volta a perder a
# permissão nas atualizações. Por isso é aviso, não erro fatal.
if command -v codesign >/dev/null 2>&1; then
    if codesign --force --deep --sign - "$APP" >/dev/null 2>&1; then
        echo "      ✅ assinado (ad-hoc) — a permissão de Gravação de Tela"
        echo "         passa a sobreviver às próximas atualizações."
    else
        echo "      ⚠️  não consegui assinar o aplicativo. Ele funciona igual,"
        echo "         mas a cada atualização o macOS vai pedir a permissão de"
        echo "         Gravação de Tela de novo — e aí é preciso REMOVER a"
        echo "         linha antiga na lista (botão −) antes de reautorizar."
    fi
fi

touch "$APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$APP" >/dev/null 2>&1

if [ ! -x "$APP/Contents/MacOS/launcher" ]; then
    falhou "O aplicativo não ficou executável. Algo bloqueou a escrita em /Applications."
fi

echo ""
echo "======================================================"
echo "  ✅ APLICATIVO CRIADO"
echo "======================================================"
echo ""
echo "  Ele está em Aplicativos, com o nome:  ${NOME}"
echo "  Abra pelo Launchpad, pelo Spotlight ou pelo Finder."
echo "  Para deixar no Dock: abra uma vez, botão direito no"
echo "  ícone do Dock → Opções → Manter no Dock."
echo ""
echo "  ⚠️ ATENÇÃO — A PERMISSÃO É POR APLICATIVO:"
echo ""
echo "  Você tinha liberado a Gravação de Tela para o TERMINAL."
echo "  O aplicativo é OUTRO programa aos olhos do macOS, então"
echo "  precisa da própria permissão:"
echo ""
echo "     Ajustes do Sistema → Privacidade e Segurança →"
echo "     Gravação de Tela → botão '+' → Aplicativos →"
echo "     '${NOME}' → e ABRA o app de novo"
echo ""
echo "  SE '${NOME}' JÁ APARECE MARCADO E MESMO ASSIM O"
echo "  PROGRAMA RECLAMA: a autorização é da versão ANTERIOR."
echo "  Clique na linha, no botão '−' para REMOVÊ-LA, e abra o"
echo "  app de novo para o macOS perguntar outra vez. Marcar de"
echo "  novo não adianta — a linha marcada é a do app velho."
echo ""
echo "  Sem isso a lista de janelas vem sem os títulos e a"
echo "  captura do gráfico sai preta — sem nenhuma mensagem de erro."
echo "  (As abas do Chrome NÃO dependem desta permissão.)"
echo ""
echo "  ⚠️ NÃO MOVA a pasta ${PASTA}"
echo "     O aplicativo aponta para ela. Se precisar mover, rode"
echo "     este CRIAR_APP.command de novo no lugar novo."
echo ""
read -r -p "Abrir o aplicativo agora? [S/n] " r
case "$r" in
    n|N) echo "Ok. Abra pelo Launchpad quando quiser." ;;
    *) open -a "$APP" ;;
esac
