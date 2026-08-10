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
exec "${PY}" main_app.py
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

# ---- 5. tirar a quarentena e registrar ----
echo "4/4 — Registrando no macOS…"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
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
echo "  Sem isso a lista de janelas vem sem os títulos e a"
echo "  captura do gráfico sai preta — sem nenhuma mensagem de erro."
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
