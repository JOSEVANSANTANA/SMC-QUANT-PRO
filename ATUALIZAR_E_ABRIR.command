#!/bin/bash
# =====================================================================
#  ATUALIZAR E ABRIR — dois cliques.
#
#  Traz a versão nova do GitHub, CONFERE AS TRAVAS DE DINHEIRO e só então
#  reabre o SMC Quant Pro.
#
#  POR QUE ELE EXISTE
#  ------------------
#  O Claude trabalha num servidor na nuvem: ele consegue publicar no
#  GitHub, mas não alcança este Mac. Sem este arquivo, cada atualização
#  virava uma sequência de comandos no Terminal — e foi ali que se perdeu
#  tempo. Aqui é um clique duplo.
#
#  POR QUE ELE RODA TESTE ANTES DE ABRIR
#  -------------------------------------
#  Este programa manda ordem de verdade na Tradovate. Em 21 e 22/08 ele
#  perdeu US$3.033 e US$2.262 com drawdown configurado de US$2.000, porque
#  o dimensionamento deixava UMA operação arriscar o dia inteiro e porque
#  reiniciar o ciclo apagava prejuízo do freio de perda.
#
#  Os dois arquivos de teste abaixo reproduzem esses dois dias com os
#  números reais do diário. Se um deles falhar, alguma coisa desfez a
#  correção — e aí este script NÃO abre o aplicativo. Recusar-se a abrir é
#  chato; abrir com a trava quebrada custa a conta.
#
#  NÃO recompila nada: o .app criado pelo CRIAR_APP.command roda os .py
#  desta pasta. Trocar os arquivos já é atualizar o app.
# =====================================================================
set -u

cd "$(dirname "$0")" || { echo "❌ não consegui entrar na pasta do script"; exit 1; }
PASTA="$(pwd)"

echo ""
echo "======================================================"
echo "  SMC QUANT PRO — atualizar e abrir"
echo "  Pasta: $PASTA"
echo "======================================================"
echo ""

pausa_e_sai() {
    echo ""
    echo "Pressione ENTER para fechar esta janela."
    read -r _
    exit "${1:-1}"
}

# ---------------------------------------------------------------------
# 1) É um repositório git mesmo?
# ---------------------------------------------------------------------
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "❌ Esta pasta não é um repositório git."
    echo "   Este script tem de ficar na pasta oficial do projeto"
    echo "   (~/SMC-QUANT-PRO), não numa cópia solta."
    pausa_e_sai 1
fi

# ---------------------------------------------------------------------
# 2) TRABALHO NÃO SALVO — parar é melhor que sobrescrever.
#    Um merge por cima de alteração local pode apagar trabalho de alguém.
# ---------------------------------------------------------------------
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  Há alterações não salvas nesta pasta:"
    echo ""
    git status --short
    echo ""
    echo "   NÃO vou atualizar por cima disso — poderia apagar trabalho."
    echo "   Peça ao Claude para resolver, ou salve num commit antes."
    pausa_e_sai 1
fi

# ---------------------------------------------------------------------
# 3) QUAL BRANCH SEGUIR
#    O arquivo BRANCH_ATUAL.txt manda, se existir. Assim, quando o Claude
#    mudar de branch, ele muda o arquivo e este script acompanha sozinho.
# ---------------------------------------------------------------------
BRANCH="claude/risco-por-operacao"
if [ -f "BRANCH_ATUAL.txt" ]; then
    LIDA="$(tr -d ' \t\r\n' < BRANCH_ATUAL.txt)"
    [ -n "$LIDA" ] && BRANCH="$LIDA"
fi
echo "📡 Buscando novidades em: $BRANCH"

if ! git fetch origin --prune 2>&1 | sed 's/^/   /'; then
    echo "❌ Não consegui falar com o GitHub. Sem internet, ou credencial expirada."
    pausa_e_sai 1
fi

if ! git rev-parse --verify "origin/$BRANCH" >/dev/null 2>&1; then
    echo "❌ A branch 'origin/$BRANCH' não existe."
    echo "   Confira o nome em BRANCH_ATUAL.txt (ou peça ao Claude)."
    pausa_e_sai 1
fi

ANTES="$(git rev-parse HEAD)"
DEPOIS="$(git rev-parse "origin/$BRANCH")"

if [ "$ANTES" = "$DEPOIS" ]; then
    echo "✅ Já está na versão mais nova. Nada para trazer."
else
    echo ""
    echo "📥 Novidades:"
    git --no-pager log --oneline "HEAD..origin/$BRANCH" | sed 's/^/   /'
    echo ""
    if ! git merge --ff-only "origin/$BRANCH" >/dev/null 2>&1; then
        echo "⚠️  O merge não é direto (esta cópia tem commits próprios)."
        echo "   Não vou forçar. Peça ao Claude para resolver — ele sabe"
        echo "   o que é de quem, e forçar aqui apagaria alguma coisa."
        pausa_e_sai 1
    fi
    echo "✅ Atualizado."
fi

# ---------------------------------------------------------------------
# 4) AS TRAVAS DE DINHEIRO
#    Não é a suíte inteira (leva minutos). São os dois arquivos que
#    reproduzem 21 e 22/08. Se falharem, o app NÃO abre.
# ---------------------------------------------------------------------
echo ""
echo "🔒 Conferindo as travas de risco antes de abrir..."

PY="python3"
command -v python3 >/dev/null 2>&1 || PY="python"

# O `if` pega o código de saída direto, sem passar por `$?`: com `set -u` e
# uma atribuição no meio, `$?` já mordeu gente demais.
if SAIDA_TESTE="$(cd tests && "$PY" -m unittest test_risco_por_operacao test_freio_nao_esquece 2>&1)"; then
    echo "   ✅ dimensionamento e freio de perda: de pé."
else
    echo ""
    echo "$SAIDA_TESTE" | tail -30
    echo ""
    echo "❌ UMA TRAVA DE RISCO FALHOU — NÃO VOU ABRIR O APLICATIVO."
    echo ""
    echo "   Estes testes reproduzem os pregões de 21 e 22/08, quando o robô"
    echo "   perdeu US\$3.033 e US\$2.262 com teto de US\$2.000. Se eles não"
    echo "   passam, a proteção que impede isso não está de pé."
    echo ""
    echo "   Mande esta tela para o Claude."
    pausa_e_sai 1
fi

# ---------------------------------------------------------------------
# 5) FECHAR E REABRIR
#    Reabrir sem fechar deixaria a versão velha rodando e mostrando
#    números velhos — que é o tipo de divergência que este projeto inteiro
#    existe para não ter.
# ---------------------------------------------------------------------
echo ""
if pgrep -f "SMC Quant Pro" >/dev/null 2>&1 || pgrep -f "main_app.py" >/dev/null 2>&1; then
    echo "🔄 Fechando a versão que está aberta..."
    osascript -e 'quit app "SMC Quant Pro"' >/dev/null 2>&1
    sleep 2
    pkill -f "main_app.py" >/dev/null 2>&1
    sleep 1
fi

APP="/Applications/SMC Quant Pro.app"
if [ ! -d "$APP" ]; then
    echo "ℹ️  O aplicativo ainda não existe em /Applications."
    echo "   Rodando o CRIAR_APP.command uma vez..."
    if [ -x "./CRIAR_APP.command" ]; then
        ./CRIAR_APP.command
    else
        bash ./CRIAR_APP.command
    fi
fi

echo "🚀 Abrindo o SMC Quant Pro..."
open "$APP" 2>/dev/null || "$PY" main_app.py &

echo ""
echo "======================================================"
echo "  ✅ Pronto. Versão: $(git --no-pager log -1 --format='%h %s' | cut -c1-60)"
echo "======================================================"
echo ""
echo "  Lembrete: o modo autônomo NÃO é ligado por este script."
echo "  Quem decide isso é você, na aba Motor."
echo ""
pausa_e_sai 0
