#!/bin/bash
# =====================================================================
#  Abre o Painel de Licenças no navegador padrão do Mac.
#  Dois cliques neste arquivo.
# =====================================================================
cd "$(dirname "$0")" || exit 1

if [ ! -f "painel_licencas.html" ]; then
    echo "❌ Não achei o painel_licencas.html nesta pasta."
    echo "   Descompacte o zip inteiro e rode de dentro da pasta criada."
    read -r -p "Pressione ENTER para fechar."
    exit 1
fi

echo "Abrindo o Painel de Licenças…"
open "painel_licencas.html"
sleep 1
