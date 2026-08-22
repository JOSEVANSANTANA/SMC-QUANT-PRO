#!/bin/bash
# =====================================================================
#  AJUSTAR O PLANO DE TRADING — dois cliques.
#
#  Cinco campos do Plano estavam autorizando o que nenhuma trava de código
#  consegue impedir. Este script arruma os cinco, com backup, e mostra o
#  antes e o depois.
#
#  POR QUE ISTO É UM SCRIPT E NÃO "vá na aba Plano e mude"
#  ------------------------------------------------------
#  São cinco campos, numa conta específica, dentro de um JSON com duas
#  contas. Errar um dígito aqui custa dinheiro, e caçar campo em tela é
#  onde o erro entra. O script edita só os cinco, valida o JSON no fim e
#  guarda uma cópia do arquivo antigo.
#
#  ELE NÃO INVENTA NADA: se um campo já estiver no valor certo, ele diz
#  que já estava e segue. Se a conta não for encontrada, ele para.
# =====================================================================
set -u

# ENTRAR NA PASTA DO SCRIPT ANTES DE QUALQUER COISA. Num duplo clique, o
# Terminal começa na pasta pessoal — e o `xattr -dr` logo abaixo sairia
# varrendo o HOME inteiro em vez da pasta do projeto.
cd "$(dirname "$0")" || { echo "❌ não consegui entrar na pasta do script"; exit 1; }

# ---------------------------------------------------------------------
# AUTO-CURA DA QUARENTENA E AVISO DO iCLOUD
#
# Todo arquivo vindo de um zip baixado leva a marca de quarentena, e script
# sem assinatura da Apple e bloqueado com "A Apple nao pode verificar se o
# item esta livre de algum malware" — e um botao "Mover para o Lixo" ao lado.
# Se ESTE script conseguiu rodar, a marca ja foi vencida aqui: entao ele
# limpa a PASTA INTEIRA, e os outros .command passam a abrir com dois
# cliques. Sem isto, o mesmo susto se repete uma vez por arquivo.
xattr -dr com.apple.quarantine "$(pwd)" 2>/dev/null || true

# O iCLOUD TIRA ARQUIVO DO DISCO PARA POUPAR ESPACO e deixa so um marcador.
# Quando o programa vai ler o que foi retirado, ele nao esta la — e a falha
# aparece no meio do pregao, num arquivo que funcionava ontem. No print de
# 18/08 a pasta estava no iCloud Drive e o Finder ja mostrava "Nao foi
# possivel concluir a sincronizacao do iCloud".
case "$(pwd)" in
  *"/Library/Mobile Documents/"*|*"/com~apple~CloudDocs/"*)
    echo ""
    echo "======================================================================"
    echo "  AVISO: esta pasta esta dentro do iCLOUD DRIVE."
    echo ""
    echo "  Mova o projeto para um lugar que NAO sincroniza, por exemplo:"
    echo "      $HOME/SMC-QUANT-PRO"
    echo "======================================================================"
    echo ""
    ;;
esac

CONFIG="$HOME/Library/Application Support/SMC_Quant_Pro/config_smc.json"

echo ""
echo "======================================================"
echo "  SMC QUANT PRO — ajustar o Plano de Trading"
echo "======================================================"
echo ""

pausa_e_sai() {
    echo ""
    echo "Pressione ENTER para fechar esta janela."
    read -r _
    exit "${1:-1}"
}

if [ ! -f "$CONFIG" ]; then
    echo "❌ Não achei o arquivo de configuração em:"
    echo "   $CONFIG"
    pausa_e_sai 1
fi

# ---------------------------------------------------------------------
# O APLICATIVO TEM DE ESTAR FECHADO.
# Ele guarda a configuração em memória e regrava ao sair — editar com ele
# aberto significa ver a mudança sumir sem explicação nenhuma.
# ---------------------------------------------------------------------
if pgrep -f "main_app.py" >/dev/null 2>&1; then
    echo "🔄 O SMC Quant Pro está aberto. Fechando antes de editar,"
    echo "   senão ele regrava por cima e a mudança se perde."
    osascript -e 'quit app "SMC Quant Pro"' >/dev/null 2>&1
    sleep 2
    pkill -f "main_app.py" >/dev/null 2>&1
    sleep 1
fi

BACKUP="${CONFIG}.bak-$(date +%Y%m%d-%H%M%S)"
cp "$CONFIG" "$BACKUP" || { echo "❌ não consegui fazer backup"; pausa_e_sai 1; }
echo "💾 Backup: $(basename "$BACKUP")"
echo ""

python3 - "$CONFIG" <<'PYEOF'
import json, sys

caminho = sys.argv[1]

# Os cinco campos, com o motivo de cada um. O motivo vai para a tela porque
# um número trocado sem explicação é um número que volta ao antigo na
# próxima vez que alguém mexer na aba.
ALVOS = {
    "risco_pct":            (5.0,  "40% da conta por operação (US$800 de US$2.000). Com 5% são US$100"),
    "max_contratos":        (5,    "60 MES = US$300 por ponto; 7 pontos levam a conta"),
    "max_stops_seguidos":   (2,    "com 20, o freio de stops seguidos está DESLIGADO. O padrão do código é 2"),
    "max_operacoes_dia":    (5,    "vinte trades num dia de conta de avaliação"),
    "probabilidade_minima": (70.0, "55% é quase cara-ou-coroa, e o modo autônomo aceita tudo que passa no piso"),
}

with open(caminho, encoding="utf-8") as f:
    cfg = json.load(f)

ativa = cfg.get("conta_ativa")
conta = next((c for c in cfg.get("contas", []) if c.get("id") == ativa), None)
if conta is None:
    print("❌ Não achei a conta ativa (%s) dentro do arquivo." % ativa)
    sys.exit(1)

plano = conta.setdefault("plano_trading", {})
print("Conta: %s  (%s)" % (conta.get("nome", "?"), ativa))
print("")
print("  %-22s %10s   %10s" % ("CAMPO", "ANTES", "DEPOIS"))
print("  " + "-" * 48)

mudou = False
for campo, (novo, porque) in ALVOS.items():
    antes = plano.get(campo, "—")
    if antes == novo:
        print("  %-22s %10s   %10s   (já estava)" % (campo, antes, novo))
        continue
    plano[campo] = novo
    mudou = True
    print("  %-22s %10s → %10s" % (campo, antes, novo))
    print("      %s" % porque)

if not mudou:
    print("")
    print("✅ Os cinco campos já estavam corretos. Nada a fazer.")
    sys.exit(0)

# Grava e RELÊ do disco. Escrever e confiar é como dizer "cancelei" sem
# recontar as ordens — é a mesma família de erro que este projeto persegue.
with open(caminho, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)

with open(caminho, encoding="utf-8") as f:
    conferido = json.load(f)
c2 = next(c for c in conferido["contas"] if c["id"] == ativa)
for campo, (novo, _) in ALVOS.items():
    if c2["plano_trading"].get(campo) != novo:
        print("")
        print("❌ %s não ficou gravado. Restaure o backup." % campo)
        sys.exit(1)

print("")
print("✅ Gravado e conferido relendo o arquivo do disco.")
PYEOF

CODIGO=$?
echo ""
if [ $CODIGO -ne 0 ]; then
    echo "❌ Algo deu errado. O arquivo antigo está em:"
    echo "   $BACKUP"
    echo "   Para voltar atrás:  cp \"$BACKUP\" \"$CONFIG\""
    pausa_e_sai 1
fi

echo "======================================================"
echo "  ✅ Plano ajustado. Pode abrir o SMC Quant Pro."
echo "======================================================"
echo ""
echo "  O que NÃO foi tocado, de propósito: drawdown_maximo,"
echo "  hora_inicio, hora_fim, ciclo_inicio e as chaves de API."
echo ""
echo "  E o modo autônomo continua sendo decisão sua."
echo ""
pausa_e_sai 0
