#!/bin/bash
# =====================================================================
#  SMC Quant Pro — instalação no Mac (Apple Silicon M1/M2/M3)
#
#  COMO USAR: dê DOIS CLIQUES neste arquivo no Finder.
#  (Se o Mac disser que não pode abrir, veja o LEIA-ME_MAC.txt.)
#
#  Ele NÃO instala nada escondido e NÃO mexe em nada fora desta pasta,
#  exceto instalar as bibliotecas Python que o programa precisa.
#  Cada passo é anunciado antes de rodar, e qualquer falha PARA aqui em
#  vez de seguir fingindo que deu certo.
# =====================================================================
set -u

cd "$(dirname "$0")" || exit 1
PASTA="$(pwd)"

echo ""
echo "======================================================"
echo "  SMC QUANT PRO — INSTALAÇÃO NO MAC"
echo "  Pasta: $PASTA"
echo "======================================================"
echo ""

falhou() {
    echo ""
    echo "❌ $1"
    echo ""
    echo "Nada foi instalado pela metade sem você saber. Resolva o ponto"
    echo "acima e rode este instalador de novo."
    echo ""
    read -r -p "Pressione ENTER para fechar."
    exit 1
}

# ---------------------------------------------------------------
# 1. PYTHON COM TK
# ---------------------------------------------------------------
echo "1/5 — Procurando um Python que sirva…"
echo "      (o Python que vem no Mac NÃO serve: ele não traz o Tk, que é"
echo "       a biblioteca da interface do programa)"

PY=""
for cand in \
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
    /opt/homebrew/bin/python3 \
    "$(command -v python3 2>/dev/null)"
do
    [ -x "$cand" ] || continue
    if "$cand" -c "import tkinter" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done

if [ -z "$PY" ]; then
    echo ""
    echo "❌ Não achei nenhum Python COM Tk nesta máquina."
    echo ""
    echo "   O que fazer (5 minutos):"
    echo "   1. Abra https://www.python.org/downloads/macos/"
    echo "   2. Baixe o 'macOS 64-bit universal2 installer' do Python 3.12"
    echo "   3. Instale e rode este instalador de novo."
    echo ""
    echo "   Atenção: o Python que já vem no Mac não resolve — é justamente"
    echo "   ele que não tem o Tk."
    falhou "Python com Tk ausente."
fi

echo "      ✅ usando: $PY"
"$PY" --version

# ---------------------------------------------------------------
# 2. NODE
# ---------------------------------------------------------------
echo ""
echo "2/5 — Procurando o Node.js (é ele que roda o motor)…"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
NODE="$(command -v node 2>/dev/null || true)"
if [ -z "$NODE" ]; then
    echo ""
    echo "⚠️  Node.js não encontrado."
    echo "    O programa ABRE sem ele, mas o MOTOR não sobe."
    echo ""
    echo "    Para instalar depois, no Terminal:  brew install node"
    echo "    Ou baixe o .pkg ARM64 em https://nodejs.org"
    echo ""
    read -r -p "    Continuar mesmo assim? [s/N] " resp
    case "$resp" in
        s|S|y|Y) echo "    Seguindo sem o Node." ;;
        *) falhou "Instalação interrompida por você." ;;
    esac
else
    echo "      ✅ $NODE ($(node -v 2>/dev/null))"
fi

# ---------------------------------------------------------------
# 3. ARQUIVOS OBRIGATÓRIOS
# ---------------------------------------------------------------
echo ""
echo "3/5 — Conferindo se a pasta está completa…"
FALTA=""
for f in main_app.py plataforma.py tradovate_auto.py requirements-mac.txt \
         versao.json motor/index.js motor/package.json; do
    if [ ! -f "$f" ]; then
        FALTA="$FALTA $f"
    fi
done
if [ -n "$FALTA" ]; then
    echo ""
    echo "❌ Faltam arquivos nesta pasta:$FALTA"
    falhou "Descompacte o zip inteiro e rode de dentro da pasta criada."
fi
echo "      ✅ todos os arquivos estão aqui"

# ---------------------------------------------------------------
# 4. BIBLIOTECAS PYTHON
# ---------------------------------------------------------------
echo ""
echo "4/5 — Instalando as bibliotecas Python (2 a 5 minutos)…"
echo "      A mais importante é a pyobjc-framework-Quartz: sem ela o"
echo "      programa não enxerga as janelas abertas do Mac."
echo ""
"$PY" -m pip install --upgrade pip >/dev/null 2>&1
if ! "$PY" -m pip install -r requirements-mac.txt; then
    falhou "A instalação das bibliotecas falhou (veja o erro acima). Costuma ser internet."
fi

echo ""
echo "      Conferindo o que REALMENTE ficou instalado:"
"$PY" - <<'VERIFICA'
import importlib, sys
itens = [("tkinter", "interface"), ("PIL", "imagem/captura"),
         ("customtkinter", "interface"), ("requests", "internet"),
         ("google.genai", "IA (Gemini)"), ("Quartz", "janelas do macOS")]
faltou = []
for mod, papel in itens:
    try:
        importlib.import_module(mod)
        print(f"      ✅ {mod:<16} ({papel})")
    except Exception as e:
        print(f"      ❌ {mod:<16} ({papel}) — {type(e).__name__}")
        faltou.append(mod)
sys.exit(1 if faltou else 0)
VERIFICA
if [ $? -ne 0 ]; then
    falhou "Alguma biblioteca não subiu (marcada com ❌ acima)."
fi

# ---------------------------------------------------------------
# 5. DIAGNÓSTICO DA PLATAFORMA
# ---------------------------------------------------------------
echo ""
echo "5/5 — Diagnóstico do seu Mac:"
echo ""
"$PY" plataforma.py 2>/dev/null | sed 's/^/      /'

echo ""
echo "======================================================"
echo "  ✅ INSTALADO."
echo "======================================================"
echo ""
echo "  FALTA UM PASSO, E ELE É OBRIGATÓRIO:"
echo ""
echo "  Ajustes do Sistema → Privacidade e Segurança →"
echo "  Gravação de Tela → botão '+' → adicione o TERMINAL"
echo "  → feche e abra o programa de novo."
echo ""
echo "  Sem isso o macOS NÃO dá erro: ele só entrega as janelas"
echo "  sem título e a captura do gráfico sai preta."
echo "  (Se a linha 'Gravação de Tela' acima já diz 'concedida',"
echo "   está feito.)"
echo ""
echo "  PARA ABRIR O PROGRAMA, dê dois cliques em:"
echo "      ABRIR_SMC_QUANT_PRO.command"
echo ""
read -r -p "Pressione ENTER para fechar."
