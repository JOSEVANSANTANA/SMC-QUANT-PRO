#!/bin/bash
# =====================================================================
#  Abre o Painel de Licenças NO GOOGLE CHROME.
#  Dois cliques neste arquivo.
#
#  POR QUE CHROME, E NÃO O NAVEGADOR PADRÃO
#  ----------------------------------------
#  O painel guarda o endereço do servidor e a senha de administrador no
#  localStorage DO NAVEGADOR QUE ABRIU. Cada navegador tem o seu próprio
#  localStorage: abrir hoje no Safari e amanhã no Chrome significa digitar
#  a senha de novo, com a sensação de que "o painel esqueceu tudo".
#  Fixando o Chrome, a memória é sempre a mesma.
#
#  Se o Chrome não estiver instalado, ele NÃO falha calado: avisa e abre no
#  navegador padrão, dizendo que a memória vai ser outra.
# =====================================================================
cd "$(dirname "$0")" || exit 1

if [ ! -f "painel_licencas.html" ]; then
    echo "❌ Não achei o painel_licencas.html nesta pasta."
    echo "   Descompacte o zip inteiro e rode de dentro da pasta criada."
    echo ""
    echo "   Se você recebeu um pacote SEM o painel, ele foi gerado com"
    echo "   --sem-painel — é o pacote que vai para CLIENTE, e o painel"
    echo "   nunca vai junto de propósito."
    read -r -p "Pressione ENTER para fechar."
    exit 1
fi

CAMINHO="$(pwd)/painel_licencas.html"

if [ -d "/Applications/Google Chrome.app" ] \
   || [ -d "$HOME/Applications/Google Chrome.app" ]; then
    echo "Abrindo o Painel de Licenças no Google Chrome…"
    open -a "Google Chrome" "$CAMINHO"
else
    echo "⚠️  Google Chrome não encontrado nesta máquina."
    echo "   Vou abrir no navegador padrão."
    echo "   Atenção: o endereço do servidor e a senha ficam guardados por"
    echo "   NAVEGADOR. Se você costuma usar o Chrome, vai precisar digitar"
    echo "   os dois de novo aqui."
    open "$CAMINHO"
fi
sleep 1
