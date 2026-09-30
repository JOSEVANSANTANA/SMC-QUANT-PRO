#!/bin/bash
# =====================================================================
#  INSTALA O SMC QUANT PRO SEM O BLOQUEIO DO MAC — um comando só.
#
#  Este script existe porque a saída anterior (o `xattr` na pasta já
#  extraída) FALHOU na máquina dele, e falhou por dois motivos que eu não
#  tinha previsto:
#
#   1. A pasta estava no iCLOUD DRIVE. O Terminal não tem permissão para
#      reescrever atributo de arquivo lá dentro sem Acesso Total ao Disco,
#      então o `xattr` imprimia "Operation not permitted" — e eu tinha
#      escrito, com todas as letras, que "silêncio é sinal de que deu
#      certo". Instrui a ignorar exatamente a linha que explicava a falha.
#
#   2. A marca de quarentena é aplicada por QUEM EXTRAI. O Finder (Utilitário
#      de Arquivos) marca tudo o que descompacta. O `unzip` do Terminal NÃO
#      marca nada. Ou seja: descompactando aqui, não há o que desbloquear —
#      o problema deixa de existir em vez de ser remediado.
#
#  O que ele faz, nesta ordem:
#    • acha o zip mais recente (Downloads, Mesa, Documentos, iCloud);
#    • descompacta em ~/Applications/SMC_QUANT_PRO (fora do iCloud);
#    • tira a quarentena de qualquer sobra, e DIZ se não conseguiu;
#    • devolve a permissão de execução aos .command;
#    • CONFERE no fim e abre a pasta.
#
#  Cada passo é anunciado. Falha nenhuma passa calada.
# =====================================================================
set -u

DESTINO="$HOME/Applications/SMC_QUANT_PRO"

echo ""
echo "======================================================================"
echo "  SMC QUANT PRO — instalação sem o bloqueio do Mac"
echo "======================================================================"
echo ""

# ---- 1. ACHAR O ZIP -------------------------------------------------
# Procura nos lugares onde o download costuma cair, inclusive o iCloud.
echo "1) Procurando o pacote..."
ZIP=""
for pasta in "$HOME/Downloads" "$HOME/Desktop" "$HOME/Documents" \
             "$HOME/Library/Mobile Documents/com~apple~CloudDocs" \
             "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Documentos" \
             "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Documents"; do
    [ -d "$pasta" ] || continue
    # O MAIS RECENTE, COMPARANDO UM A UM. Duas armadilhas já caíram aqui:
    #
    #  • `stat -f` dá a data do arquivo no Mac e o estado do SISTEMA DE
    #    ARQUIVOS no Linux — o script chegou a "achar" um zip chamado
    #    "Total: 16777216 Free: 16603400".
    #  • `find ... | xargs ls -t` parece resolver, mas com a busca VAZIA o
    #    xargs roda `ls -t` assim mesmo, sem argumento nenhum — e `ls -t` sem
    #    argumento lista a PASTA ATUAL. Sem nenhum zip na máquina, o script
    #    escolhia o primeiro arquivo do diretório de onde foi chamado e tentava
    #    descompactá-lo. (Foi assim que ele tentou abrir a si próprio.)
    #
    # `-nt` compara duas datas sem depender de `stat`, e o laço simplesmente
    # não roda quando não há nada. O -print0 é por causa das pastas com espaço
    # no nome, como "Mobile Documents".
    achado=""
    while IFS= read -r -d "" f; do
        if [ -z "$achado" ] || [ "$f" -nt "$achado" ]; then achado="$f"; fi
    done < <(find "$pasta" -maxdepth 3 -name "SMC_QUANT_PRO*.zip" -type f -print0 2>/dev/null)
    if [ -n "$achado" ] && [ -f "$achado" ]; then ZIP="$achado"; break; fi
done

if [ -z "$ZIP" ]; then
    echo ""
    echo "   ❌ Não achei nenhum SMC_QUANT_PRO*.zip."
    echo ""
    echo "   Coloque o zip que eu te mandei na pasta Downloads e rode de novo."
    echo "   (Se ele já estiver lá com outro nome, renomeie para começar com"
    echo "    SMC_QUANT_PRO.)"
    exit 1
fi
echo "   Achei: $ZIP"

# ---- 2. DESCOMPACTAR ------------------------------------------------
# Trabalha numa pasta temporária: se algo der errado no meio, a instalação
# que já existe não fica pela metade.
TEMP=$(mktemp -d)
trap 'rm -rf "$TEMP"' EXIT

echo ""
echo "2) Descompactando (pelo Terminal — é isto que evita a quarentena)..."
if ! unzip -q -o "$ZIP" -d "$TEMP"; then
    echo "   ❌ O zip não abriu. Ele pode ter vindo incompleto do download."
    exit 1
fi

# O pacote de ENTREGA tem zips dentro (SEU/ e CLIENTE/). O SEU é o que
# instala — é o único que traz o painel de licenças.
INTERNO=$(find "$TEMP" -path "*/SEU/*_MAC_*.zip" -type f 2>/dev/null | head -1)
if [ -z "$INTERNO" ]; then
    INTERNO=$(find "$TEMP" -name "*_MAC_*.zip" -type f 2>/dev/null | head -1)
fi
if [ -n "$INTERNO" ]; then
    echo "   Era o pacote de entrega. Abrindo o de dentro:"
    echo "   $(basename "$INTERNO")"
    unzip -q -o "$INTERNO" -d "$TEMP/extraido" || exit 1
    ORIGEM=$(find "$TEMP/extraido" -maxdepth 2 -name "main_app.py" -exec dirname {} \; | head -1)
else
    ORIGEM=$(find "$TEMP" -maxdepth 3 -name "main_app.py" -exec dirname {} \; | head -1)
fi

if [ -z "$ORIGEM" ]; then
    echo "   ❌ Não achei o main_app.py dentro do zip. Pacote incompleto."
    exit 1
fi

# ---- 3. INSTALAR FORA DO iCLOUD -------------------------------------
echo ""
echo "3) Instalando em: $DESTINO"
echo "   (fora do iCloud — lá os arquivos somem do disco para poupar espaço)"
mkdir -p "$HOME/Applications"
if [ -d "$DESTINO" ]; then
    # Guarda os dados do trader: diário, plano, configuração. Eles NÃO ficam
    # nesta pasta (ficam em Application Support), mas se alguém tiver posto
    # algo aqui, um backup datado evita a perda.
    BACKUP="$DESTINO.anterior.$(date +%Y%m%d-%H%M%S)"
    echo "   Já existia uma instalação. Guardando a antiga em:"
    echo "   $(basename "$BACKUP")"
    mv "$DESTINO" "$BACKUP"
fi
mkdir -p "$DESTINO"
cp -R "$ORIGEM"/. "$DESTINO"/

# ---- 4. QUARENTENA E PERMISSÃO --------------------------------------
echo ""
echo "4) Conferindo bloqueio e permissões..."
# Não deve haver quarentena (o unzip não marca), mas o zip de origem podia
# estar dentro de uma pasta marcada. Aqui é barato garantir.
if xattr -dr com.apple.quarantine "$DESTINO" 2>/dev/null; then
    echo "   Marca de quarentena: limpa."
else
    echo "   ⚠️  Não consegui limpar a marca de quarentena (sem permissão?)."
    echo "      Siga com os passos abaixo mesmo assim e veja o item 5."
fi
chmod +x "$DESTINO"/*.command 2>/dev/null
chmod +x "$DESTINO"/*.sh 2>/dev/null

# ---- 5. CONFERIR DE VERDADE -----------------------------------------
echo ""
echo "5) Conferindo o resultado (é o que faltava da última vez):"
FALTOU=0
for arq in main_app.py plataforma.py INSTALAR_MAC.command CRIAR_APP.command; do
    if [ -f "$DESTINO/$arq" ]; then
        echo "   ✅ $arq"
    else
        echo "   ❌ FALTANDO: $arq"
        FALTOU=1
    fi
done

MARCADOS=$(xattr -r -p com.apple.quarantine "$DESTINO" 2>/dev/null | wc -l | tr -d ' ')
if [ "$MARCADOS" = "0" ]; then
    echo "   ✅ nenhum arquivo bloqueado pelo Gatekeeper"
else
    echo "   ⚠️  ainda há $MARCADOS arquivo(s) com a marca de quarentena."
    echo "      Rode, colando esta linha inteira:"
    echo "      sudo xattr -dr com.apple.quarantine \"$DESTINO\""
    echo "      (vai pedir a senha do seu Mac; ela não aparece enquanto digita)"
fi

echo ""
if [ "$FALTOU" = "1" ]; then
    echo "======================================================================"
    echo "  ❌ A instalação ficou INCOMPLETA. Não siga adiante."
    echo "     Me mande esta tela inteira."
    echo "======================================================================"
    exit 1
fi

echo "======================================================================"
echo "  ✅ PRONTO. O programa está em:"
echo "     $DESTINO"
echo ""
echo "  AGORA, no Finder que vai abrir:"
echo "    1) dois cliques em INSTALAR_MAC.command"
echo "    2) depois, dois cliques em CRIAR_APP.command"
echo "    3) abra SEMPRE pelo ÍCONE do aplicativo, nunca pelo .command"
echo ""
echo "  NÃO mova esta pasta depois disso: o ícone do aplicativo aponta"
echo "  para o caminho onde ela estava quando você rodou o CRIAR_APP."
echo "======================================================================"
echo ""
open "$DESTINO" 2>/dev/null
