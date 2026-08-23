#!/usr/bin/env python3
"""Gera os DOIS pacotes de entrega — Windows e Mac — a partir do repositório.

    python3 empacotar.py            # os dois zips
    python3 empacotar.py windows    # só o do Windows
    python3 empacotar.py mac        # só o do Mac
    python3 empacotar.py --sem-painel   # sem o painel de licenças (ver abaixo)
    python3 empacotar.py --entrega      # UM zip com os dois: SEU/ e CLIENTE/

POR QUE ISTO EXISTE
-------------------
O SMC Quant Pro tem UM código só. `main_app.py`, `plataforma.py`,
`tradovate_auto.py` e o `motor/` são os MESMOS arquivos nos dois sistemas —
quem decide "PrintWindow ou screencapture", "DPAPI ou Chaveiro", "win32gui ou
Quartz" é o `plataforma.py`, em tempo de execução. Ou seja: toda correção já
nasce valendo para os dois.

O que muda entre um sistema e outro é só a CASCA: a lista de dependências, o
.spec do empacotador, os instaladores e o passo a passo. Montar isso na mão a
cada entrega é onde o erro entra — foi assim que o `.spec` do Windows ficou
fora do repositório enquanto o do Mac estava dentro. Aqui a divisão é
declarada uma vez, em COMUM/WINDOWS/MAC, e o script confere que todo arquivo
listado existe antes de empacotar.

O script NÃO compila nada. Ele monta as pastas que você descompacta na
máquina certa; o build (PyInstaller) roda lá, com o .spec de cada sistema.
"""

import os
import sys
import zipfile

RAIZ = os.path.dirname(os.path.abspath(__file__))

# O CÓDIGO. Idêntico nos dois sistemas — esta lista é a prova disso.
COMUM = [
    "main_app.py",
    "plataforma.py",
    "tradovate_auto.py",
    "tradovate_stream.py",
    "order_flow.py",
    "market_regime.py",
    "tiger_voice.py",
    "tiger_hud.py",
    "jarvis.py",
    "motor/index.js",
    "motor/package.json",
    "package.json",
    "server.js",
    "versao.json",
    "icone.ico",
    "tests/LEIA-ME.md",
    "tests/harness.py",
    "tests/run.py",
    "tests/fumaca_gui.py",
    "tests/test_autonomia.py",
    "tests/test_burrice.py",
    "tests/test_conversa.py",
    "tests/test_duplicidade.py",
    "tests/test_dias_do_ciclo.py",
    "tests/test_dimensionamento.py",
    "tests/test_honestidade.py",
    "tests/test_instalacao_assistida.py",
    "tests/test_interface.py",
    "tests/test_inteligencia.py",
    "tests/test_mac.py",
    "tests/test_motor.py",
    "tests/test_nomes_indefinidos.py",
    "tests/test_macro_no_motor.py",
    "tests/test_ia_local_rapida.py",
    "tests/test_aprendizado_visivel.py",
    "tests/test_ordem_atm.py",
    "tests/test_modo_autonomo.py",
    "tests/test_perseguir_a_meta.py",
    "tests/test_acerto_do_motor.py",
    "tests/test_cancelamento_na_corretora.py",
    "tests/test_cofre_por_provedor.py",
    "tests/test_catalogo_openrouter.py",
    "tests/test_desfecho_honesto.py",
    "tests/test_duplicidade_e_aumento.py",
    "tests/test_trail_inteligente.py",
    "tests/test_ativo_e_acao_inventada.py",
    "tests/test_risco_por_operacao.py",
    "tests/test_raciocinio_vazado.py",
    "tests/test_freio_nao_esquece.py",
    "tests/test_replay_negado.py",
    "tests/test_replay_nao_engole_sugestao.py",
    "tests/test_conta_orfa.py",
    "tests/test_telemetria_honesta.py",
    "tests/test_fluxo_real.py",
    "tests/test_ambiente_replay.py",
    "tests/test_notificacao.py",
    "tests/test_piso_qualidade.py",
    "tests/test_pregao.py",
    "tests/test_qualidade_leitura.py",
    "tests/test_meta.py",
    "tests/test_visao_local.py",
    "tests/test_voz.py",
    "tests/test_tradovate_stream.py",
    "tests/test_order_flow.py",
    "tests/test_market_regime.py",
    "tests/test_tiger_voice.py",
    "ENTREGA_AO_CLIENTE.md",
]

# A CASCA de cada sistema.
SO_WINDOWS = [
    "requirements.txt",
    "SMC_Quant_Pro.spec",
    "COMPILAR.md",
    "LEIA-ME_WINDOWS.txt",
    "instalador/LEIA-ME.md",
    "instalador/SMC_Quant_Pro.iss",
    # O abridor do painel EXISTIA só no Mac. No Windows o painel ia junto no
    # pacote e não tinha como abrir com dois cliques — ficava um HTML solto no
    # meio dos arquivos. Sai automaticamente com --sem-painel, porque o filtro
    # olha "PAINEL_LICENCAS" no nome.
    "ABRIR_PAINEL_LICENCAS.bat",
]
SO_MAC = [
    "requirements-mac.txt",
    # O PRIMEIRO ARQUIVO QUE ELE PRECISA NUM MAC, e o único que o Gatekeeper
    # nunca bloqueia — é texto puro. 18/08: dois cliques no CRIAR_APP.command
    # e o Mac respondeu "a Apple não pôde verificar...", com um botão "Mover
    # para o Lixo" ao lado. Sem este arquivo, a instalação para ali.
    "DESBLOQUEAR_MAC.txt",
    # A SAÍDA QUE NÃO DEPENDE DE NADA DAR CERTO. `bash script.sh` no Terminal
    # nunca passa pelo Gatekeeper — ele só bloqueia o que o Finder LANÇA.
    # E, descompactando pelo Terminal, a marca de quarentena nem chega a
    # existir: quem marca é o Finder, não o `unzip`.
    "INSTALAR_SEM_BLOQUEIO_MAC.sh",
    "SMC_Quant_Pro_MAC.spec",
    "INSTALAR_NO_MAC.md",
    "LEIA-ME_MAC.txt",
    "INSTALAR_MAC.command",
    "ABRIR_SMC_QUANT_PRO.command",
    "CRIAR_APP.command",
    "ABRIR_PAINEL_LICENCAS.command",
]

# O painel de licenças carrega o SEU token de administrador. Ele é seu, e por
# isso vai nos pacotes — mas nunca pode ser repassado a um cliente. O script
# avisa em toda execução, e `--sem-painel` gera os zips sem ele.
PAINEL = "painel_licencas.html"

# O GUIA DE REVENDA TAMBÉM É SEU, E ESTAVA INDO JUNTO.
# Tirar o painel do zip do cliente não adianta nada se o pacote leva, ao lado,
# o passo a passo que diz "abra o painel_licencas.html na sua máquina e gere
# uma licença para ele" e "o painel carrega o seu token de administrador". O
# arquivo não vaza a senha, mas entrega ao cliente o desenho inteiro do
# negócio — inclusive que existe um painel, que é justamente o que ele não
# deveria saber. Sai junto com o painel, pelo mesmo motivo.
SO_SEU = ["ENTREGA_AO_CLIENTE.md"]

# E dentro dos LEIA-ME há trechos que também são só seus (a seção do painel, o
# item do changelog que explica a revenda). Ali não dá para tirar o arquivo
# inteiro — o LEIA-ME é do cliente. Então os trechos vêm delimitados no
# próprio texto, e o empacotador os remove ao montar o pacote do cliente.
# As MARCAS somem dos dois pacotes: elas são instrução para o empacotador, não
# para quem lê.
MARCA_INICIO = "[[SO SEU — nao vai no pacote do cliente]]"
MARCA_FIM = "[[FIM SO SEU]]"


def texto_do_pacote(conteudo, com_painel=True):
    """Tira os trechos marcados como só-seus (quando for pacote de cliente) e,
    sempre, as próprias marcas.

    Função PURA, de propósito: é o tipo de coisa que precisa ser conferível
    sem gerar zip nenhum."""
    saida, pulando = [], False
    for linha in conteudo.splitlines(keepends=True):
        nua = linha.strip()
        if nua == MARCA_INICIO:
            pulando = not com_painel
            continue
        if nua == MARCA_FIM:
            pulando = False
            continue
        if not pulando:
            saida.append(linha)
    return "".join(saida)


def versao():
    """A versão vem do versao.json — nunca de um número digitado aqui, que
    envelheceria em silêncio e batizaria o zip errado."""
    import json
    with open(os.path.join(RAIZ, "versao.json"), encoding="utf-8") as f:
        return json.load(f)["versao"]


def conferir(arquivos):
    """Todo arquivo listado tem de existir. Um pacote entregue com um arquivo
    faltando só é descoberto na máquina do trader, no meio do pregão."""
    faltando = [a for a in arquivos
                if not os.path.exists(os.path.join(RAIZ, a))]
    if faltando:
        raise SystemExit(
            "❌ Não vou gerar um pacote incompleto. Faltam no repositório:\n  "
            + "\n  ".join(faltando))


def montar(sistema, com_painel=True):
    especificos = SO_WINDOWS if sistema == "windows" else SO_MAC
    if not com_painel:
        # O ATALHO SAI JUNTO COM O PAINEL. Deixar o
        # ABRIR_PAINEL_LICENCAS.command num pacote sem o painel entrega ao
        # cliente um botão que não faz nada — e, pior, avisa que existe um
        # painel de licenças que ele não deveria nem saber que existe.
        especificos = [a for a in especificos if "PAINEL_LICENCAS" not in a]
    arquivos = COMUM + especificos + ([PAINEL] if com_painel else [])
    if not com_painel:
        arquivos = [a for a in arquivos if a not in SO_SEU]
    conferir(arquivos)

    v = versao()
    rotulo = "WINDOWS" if sistema == "windows" else "MAC"
    nome_zip = os.path.join(RAIZ, f"SMC_QUANT_PRO_{rotulo}_v{v}.zip")
    if os.path.exists(nome_zip):
        os.remove(nome_zip)

    with zipfile.ZipFile(nome_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in arquivos:
            origem = os.path.join(RAIZ, rel)
            destino = f"SMC_QUANT_PRO/{rel}"
            if rel.endswith(".command"):
                # O zip do Python NÃO leva a permissão de execução por padrão.
                # Sem ela, o duplo-clique no .command não faz nada no Mac e o
                # trader precisa descobrir sozinho o `chmod +x`. A permissão vai
                # gravada no cabeçalho Unix da entrada (0o755).
                info = zipfile.ZipInfo.from_file(origem, destino)
                info.external_attr = (0o755 << 16)
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(origem, "rb") as f:
                    z.writestr(info, f.read())
            elif rel.endswith((".txt", ".md")):
                # Passa pelo filtro dos trechos só-seus. Vale para TODOS os
                # textos: um trecho marcado num arquivo que eu esqueça de
                # listar aqui continuaria vazando, e a regra que depende de eu
                # lembrar não é regra.
                with open(origem, encoding="utf-8") as f:
                    z.writestr(destino, texto_do_pacote(f.read(), com_painel))
            else:
                z.write(origem, destino)

    tam = os.path.getsize(nome_zip) / 1024
    print(f"✅ {os.path.basename(nome_zip)}  ({len(arquivos)} arquivos, {tam:.0f} KB)")
    return nome_zip


LEIA_PRIMEIRO = """PACOTE DE ENTREGA — SMC QUANT PRO v{v}
=======================================================================

Dentro deste zip há DUAS pastas. Elas contêm arquivos com o MESMO NOME e
conteúdo DIFERENTE. Por isso vieram separadas, e por isso este aviso é a
primeira coisa que você lê.


SEU/                    <-- é o SEU. Instale a partir daqui.
  Traz o painel_licencas.html e o atalho ABRIR_PAINEL_LICENCAS
  (.command no Mac, .bat no Windows). Dois cliques no atalho abrem o
  painel no Google Chrome.

  O painel NÃO guarda a sua senha: ela é digitada nele e fica no
  navegador daquela máquina. O que ele dá é PODER — com a senha, cria e
  revoga licença. Por isso ele fica aqui, e só aqui.


CLIENTE/                <-- é o que você ENVIA. Nunca envie o de cima.
  Idêntico ao SEU, menos o painel e os atalhos. O atalho sozinho já
  anunciaria ao cliente que existe um painel de licenças.


NO MAC, ANTES DE TUDO: O GATEKEEPER
-----------------------------------
Ao dar dois cliques num .command o Mac vai dizer "A Apple não pôde
verificar se o item está livre de algum malware", com um botão "Mover
para o Lixo" ao lado. Clique em OK — NUNCA em "Mover para o Lixo" — e
abra o DESBLOQUEAR_MAC.txt que está dentro do pacote. São três passos e
um minuto: uma linha colada no Terminal libera a pasta inteira.

Isso acontece com TODO arquivo vindo de zip baixado, e não é sinal de
problema: a mensagem diz que o Mac NÃO PÔDE VERIFICAR, não que achou
alguma coisa. Só some de vez com uma assinatura paga da Apple.

Avise o seu cliente disso ANTES de ele receber o zip. É o momento em que
mais gente desiste, e é o mais fácil de resolver.


QUAL ARQUIVO MANDAR PARA CADA CLIENTE
-------------------------------------
  MacBook / iMac (Apple Silicon) ....  SMC_QUANT_PRO_MAC_v{v}.zip
  Windows 10 ou 11 ..................  SMC_QUANT_PRO_WINDOWS_v{v}.zip

Não existe pacote que sirva para os dois. Cada um traz o instalador, o
LEIA-ME e os scripts do seu próprio sistema.


CONFERÊNCIA DE CINCO SEGUNDOS, ANTES DE ENVIAR
----------------------------------------------
  unzip -l CLIENTE/SMC_QUANT_PRO_MAC_v{v}.zip | grep -i painel

Se isso imprimir qualquer coisa, PARE e não envie. Essa linha tem de sair
vazia.

O passo a passo completo está no ENTREGA_AO_CLIENTE.md, dentro de SEU/.
"""


def montar_entrega_unica(alvos):
    """UM zip com tudo: o pacote dele e o do cliente, separados por pasta.

    Pedido de 17/08: "nas próximas atualizações me entregue tudo junto em um
    zip". Antes saíam dois (ou quatro) arquivos soltos, e ele tinha de saber
    de cabeça qual era qual.

    O risco que isto remove é real e não é de conforto: o pacote DELE e o do
    CLIENTE têm exatamente o MESMO NOME DE ARQUIVO. Dois zips com o mesmo nome
    em pastas diferentes do computador é a receita para enviar o errado uma
    vez — e enviar o painel de licenças a um cliente não tem volta.

    Aqui eles nascem dentro do mesmo zip, em SEU/ e CLIENTE/, com um
    LEIA-PRIMEIRO que diz qual é qual antes de qualquer outra coisa."""
    v = versao()
    # OS BYTES SÃO LIDOS NA HORA, e isso não é detalhe de estilo.
    # `montar()` grava sempre no MESMO nome de arquivo — é a mesma versão, o
    # mesmo sistema. Guardar os caminhos e só depois montar o zip final fazia
    # o pacote do CLIENTE sobrescrever o SEU antes de qualquer um ser lido: os
    # dois apontavam para o mesmo arquivo, e a pasta SEU/ saía com o conteúdo
    # do cliente. Silenciosamente, e com o nome certo por cima.
    conteudo = {"SEU": [], "CLIENTE": []}
    for sistema in alvos:
        for pasta, com_painel in (("SEU", True), ("CLIENTE", False)):
            caminho = montar(sistema, com_painel=com_painel)
            with open(caminho, "rb") as f:
                conteudo[pasta].append((os.path.basename(caminho), f.read()))
            os.remove(caminho)

    nome = os.path.join(RAIZ, f"SMC_QUANT_PRO_ENTREGA_v{v}.zip")
    if os.path.exists(nome):
        os.remove(nome)
    with zipfile.ZipFile(nome, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("LEIA-PRIMEIRO.txt", LEIA_PRIMEIRO.format(v=v))
        for pasta in ("SEU", "CLIENTE"):
            for base, dados in conteudo[pasta]:
                # Os zips internos já estão comprimidos: comprimir de novo
                # gasta tempo e não muda o tamanho.
                z.writestr(f"{pasta}/{base}", dados,
                           compress_type=zipfile.ZIP_STORED)

    tam = os.path.getsize(nome) / 1024
    print(f"\n📦 {os.path.basename(nome)}  ({tam:.0f} KB)")
    print("   SEU/      → com painel de licenças e atalho (é o seu)")
    print("   CLIENTE/  → sem painel e sem atalho (é o que você envia)")
    return nome


def main(argv):
    com_painel = "--sem-painel" not in argv
    entrega = "--entrega" in argv
    alvos = [a.lower() for a in argv if not a.startswith("--")] or ["windows", "mac"]
    desconhecidos = [a for a in alvos if a not in ("windows", "mac")]
    if desconhecidos:
        raise SystemExit(f"Sistema desconhecido: {desconhecidos}. "
                         "Use 'windows', 'mac', ou nenhum para os dois.")
    if entrega:
        if "--sem-painel" in argv:
            raise SystemExit(
                "--entrega e --sem-painel não combinam: o pacote de entrega "
                "já traz as DUAS versões, em SEU/ e CLIENTE/.")
        montar_entrega_unica(alvos)
        return 0
    for sistema in alvos:
        montar(sistema, com_painel)
    if com_painel:
        print(f"\n⚠️  Os dois pacotes incluem o {PAINEL}, que carrega o SEU "
              "token de administrador.\n    Ele é para a sua máquina. NUNCA "
              "repasse este zip a um cliente.\n    Para gerar sem ele: "
              "python3 empacotar.py --sem-painel")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
