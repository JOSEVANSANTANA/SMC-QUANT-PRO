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
