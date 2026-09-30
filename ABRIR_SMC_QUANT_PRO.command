#!/bin/bash
# =====================================================================
#  SMC Quant Pro — abrir o programa (Mac)
#  Dois cliques neste arquivo.
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


# O PATH do Finder é mais pobre que o do Terminal: sem estas duas pastas,
# o Node instalado pelo Homebrew "some" e o motor não sobe.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

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
    echo "❌ Não achei um Python com Tk. Rode primeiro o INSTALAR_MAC.command."
    read -r -p "Pressione ENTER para fechar."
    exit 1
fi

echo "Abrindo o SMC Quant Pro…"
echo "(Pode fechar esta janela preta DEPOIS que o programa abrir — mas se"
echo " fechar antes, o programa fecha junto.)"
echo ""
exec "$PY" main_app.py
