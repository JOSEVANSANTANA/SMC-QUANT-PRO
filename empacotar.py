#!/usr/bin/env python3
"""Gera os DOIS pacotes de entrega — Windows e Mac — a partir do repositório.

    python3 empacotar.py            # os dois zips
    python3 empacotar.py windows    # só o do Windows
    python3 empacotar.py mac        # só o do Mac
    python3 empacotar.py --sem-painel   # sem o painel de licenças (ver abaixo)

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
    "motor/index.js",
    "motor/package.json",
    "package.json",
    "server.js",
    "versao.json",
    "icone.ico",
    "tests/LEIA-ME.md",
    "tests/harness.py",
    "tests/run.py",
    "tests/test_conversa.py",
    "tests/test_dimensionamento.py",
    "tests/test_interface.py",
    "tests/test_mac.py",
    "tests/test_motor.py",
    "tests/test_piso_qualidade.py",
]

# A CASCA de cada sistema.
SO_WINDOWS = [
    "requirements.txt",
    "SMC_Quant_Pro.spec",
    "COMPILAR.md",
    "LEIA-ME_WINDOWS.txt",
    "instalador/LEIA-ME.md",
    "instalador/SMC_Quant_Pro.iss",
]
SO_MAC = [
    "requirements-mac.txt",
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
    arquivos = COMUM + especificos + ([PAINEL] if com_painel else [])
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
            else:
                z.write(origem, destino)

    tam = os.path.getsize(nome_zip) / 1024
    print(f"✅ {os.path.basename(nome_zip)}  ({len(arquivos)} arquivos, {tam:.0f} KB)")
    return nome_zip


def main(argv):
    com_painel = "--sem-painel" not in argv
    alvos = [a.lower() for a in argv if not a.startswith("--")] or ["windows", "mac"]
    desconhecidos = [a for a in alvos if a not in ("windows", "mac")]
    if desconhecidos:
        raise SystemExit(f"Sistema desconhecido: {desconhecidos}. "
                         "Use 'windows', 'mac', ou nenhum para os dois.")
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
