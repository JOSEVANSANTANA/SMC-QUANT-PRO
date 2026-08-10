#!/bin/bash
# =====================================================================
#  SMC Quant Pro — abrir o programa (Mac)
#  Dois cliques neste arquivo.
# =====================================================================
set -u
cd "$(dirname "$0")" || exit 1

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
