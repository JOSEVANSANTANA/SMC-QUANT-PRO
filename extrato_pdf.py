#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LEITURA DO EXTRATO DE ORDENS DA CORRETORA (PDF) PARA O DIÁRIO.

O PEDIDO
--------
"Inclua uma opção de enviar o PDF do extrato de ordens gerado pela Tradovate
ou qualquer outra corretora para preenchimento dos envios de ordens manuais, e
o motor preencher automaticamente com base no relatório."

Hoje as operações feitas fora da sugestão do robô entram uma a uma, na mão:
direção, ativo, entrada, stop, alvo, quantidade, preço de saída. Num dia de
111 ordens isso não acontece — e o que não acontece vira diário incompleto,
que é pior que diário nenhum, porque a taxa de acerto passa a ser calculada
sobre uma amostra que ninguém sabe que está torta.

O QUE ESTE MÓDULO FAZ, E O QUE ELE SE RECUSA A FAZER
-----------------------------------------------------
Ele lê o relatório de Orders, separa o que é EXECUÇÃO do que é intenção, e
monta as operações fechadas por FIFO. Ele não estima, não completa lacuna e
não deduz o que o documento não disse.

Três recusas explícitas, e o motivo de cada uma:

  1. SÓ ORDEM `Filled` VIRA OPERAÇÃO. Canceled, Rejected e Working são
     intenção, não dinheiro. Um bracket cancelado é o par de proteção que
     morreu junto com a saída — contá-lo como trade multiplicaria por três a
     contagem do dia. Elas voltam no relatório do que foi ignorado, com o
     motivo, para ele conferir que a conta bate.

  2. POSIÇÃO QUE FICOU ABERTA NÃO VIRA RESULTADO. Se sobrou quantidade sem
     par ao fim do arquivo, ela é devolvida como sobra e é dita em voz alta.
     Inventar um preço de saída para "fechar" o número seria exatamente o
     tipo de mentira que este projeto passa o dia inteiro caçando.

  3. LINHA QUE NÃO CONFERE NÃO ENTRA. Ver `conferir_pela_nocional` abaixo.

A CONFERÊNCIA PELA COLUNA NOCIONAL — POR QUE ELA MUDA TUDO
-----------------------------------------------------------
Extrair texto de PDF é frágil por natureza: a tabela vira uma fita de
palavras, as colunas vazias somem, o cabeçalho se repete no meio dos dados e
um carimbo de hora se parte em duas linhas na quebra de página. Um leitor
descuidado erra silenciosamente de coluna e entrega um preço no lugar de
outro — e nesse ponto o diário fica errado sem ninguém perceber.

Só que o próprio relatório traz a resposta: a coluna "Notional Value" é
`quantidade x preço x multiplicador`. Conferindo cada linha executada contra
ela, um deslocamento de coluna deixa de ser silencioso — a conta não fecha, e
a linha é reportada como ilegível em vez de importada errada.

No extrato real usado para desenhar isto (MESU6, 111 ordens):
    7691.50 x 8 x 5  = 307,660.00 ✔
    7688.75 x 20 x 5 = 768,875.00 ✔
    7678.75 x 5 x 5  = 191,968.75 ✔

O multiplicador sai do PRÓPRIO documento, e não de uma tabela cravada aqui —
assim o leitor funciona para o contrato que ele operar amanhã sem ninguém
precisar vir aqui cadastrar. Quando ele bate com o `valor_por_ponto_do_ativo`
que o resto do programa usa, a importação confirma o que já se sabia; quando
diverge, o programa fala, porque divergência aí significa P&L errado.

POR QUE NÃO IMPORTA TAMBÉM O STOP E O ALVO
-------------------------------------------
Dá para vê-los: as `multibracket` canceladas ao lado de uma entrada são a
proteção que morreu junto com ela. Mas amarrar bracket a entrada exige supor
qual pertence a qual — o relatório não traz o vínculo. Como stop e alvo não
entram na conta do resultado (só entrada, saída e quantidade entram), supor
isso custaria risco de erro sem comprar nada. Ficam vazios, e vazio aqui quer
dizer "o documento não disse", que é a verdade.
"""

import re

# Ordens que representam dinheiro que trocou de mãos. O resto é intenção.
_EXECUTADA = "Filled"

# Vocabulário do relatório da Tradovate. Ficam aqui, num só lugar, porque
# outra corretora que use os mesmos rótulos passa a funcionar sem código novo,
# e uma que use rótulos diferentes é uma linha a acrescentar e não um leitor
# novo para escrever.
_TIPOS = {
    "Stop Limit": "STOP_LIMITE",
    "Limit": "LIMITE",
    "Market": "MERCADO",
    "Stop": "STOP",
}
_ESTADOS = {
    "Filled": "EXECUTADA",
    "Canceled": "CANCELADA",
    "Cancelled": "CANCELADA",
    "Rejected": "REJEITADA",
    "Working": "ABERTA",
    "Expired": "EXPIRADA",
    "Pending": "PENDENTE",
}
_LADOS = {"Buy": "BUY", "Sell": "SELL"}

_CABECALHO = ("Order ID B/S Quantity Contract Type Limit Price Stop Price "
              "Status Text Filled Qty Fill Time Avg Fill Price Timestamp "
              "Account Venue Notional Value")

_RE_ORDEM = re.compile(r"\b\d{9,}\s+(?:Buy|Sell)\b")
_RE_NUMERO = re.compile(r"^-?[\d,]+\.?\d*$")


# ---------------------------------------------------------------------------
# 1. O TEXTO SAI DO PDF
# ---------------------------------------------------------------------------
class SemLeitorDePdf(Exception):
    """Nenhuma biblioteca de PDF disponível — com o nome do que instalar.

    Exceção própria, e não `Exception` genérica, porque a interface precisa
    distinguir "não consigo abrir PDF nenhum nesta máquina" (que se resolve
    instalando um pacote) de "este PDF não é um extrato de ordens" (que se
    resolve escolhendo outro arquivo). Mensagem única para as duas faria o
    usuário tentar a correção errada."""


def texto_do_pdf(caminho):
    """Texto cru do PDF, por qualquer leitor que esta máquina tenha.

    Quatro tentativas em vez de uma dependência cravada: o programa roda em
    Mac e Windows, congelado por PyInstaller e rodando do fonte, e exigir um
    pacote específico transformaria "importar extrato" num recurso que só
    funciona em metade das instalações."""
    erros = []
    for tentativa in (_texto_pypdf, _texto_pdfplumber, _texto_fitz, _texto_pdftotext):
        try:
            txt = tentativa(caminho)
            if txt and txt.strip():
                return txt
        except ImportError:
            continue
        except Exception as e:                      # leitor existe mas falhou
            erros.append(f"{tentativa.__name__}: {e}")
    if erros:
        raise SemLeitorDePdf(
            "achei um leitor de PDF mas ele não conseguiu abrir este arquivo "
            "(" + " | ".join(erros) + ")")
    raise SemLeitorDePdf(
        "não há leitor de PDF nesta instalação. Instale um destes: "
        "'pip install pypdf' (o mais leve), pdfplumber ou pymupdf.")


def _texto_pypdf(caminho):
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader        # nome antigo do mesmo projeto
    r = PdfReader(caminho)
    return "\n".join((p.extract_text() or "") for p in r.pages)


def _texto_pdfplumber(caminho):
    import pdfplumber
    with pdfplumber.open(caminho) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _texto_fitz(caminho):
    import fitz
    with fitz.open(caminho) as doc:
        return "\n".join(pg.get_text() for pg in doc)


def _texto_pdftotext(caminho):
    """O binário do poppler, quando existe. Última tentativa de propósito:
    depende de programa externo, que é a suposição mais frágil das quatro."""
    import subprocess
    saida = subprocess.run(["pdftotext", "-layout", caminho, "-"],
                           capture_output=True, text=True, timeout=60)
    if saida.returncode != 0:
        raise RuntimeError(saida.stderr.strip()[:200] or "pdftotext falhou")
    return saida.stdout


# ---------------------------------------------------------------------------
# 2. O TEXTO VIRA ORDENS
# ---------------------------------------------------------------------------
def _achatar(texto):
    """Desmancha a tabela em uma fita de palavras e remenda o que a quebra de
    página partiu.

    Os três remendos saíram do extrato real, não de suposição:
      · '08/23/2026 22:' + '58:25'  — o carimbo parte no fim da coluna;
      · 'APEX221749000' + '00137'   — a conta parte no meio do número;
      · o cabeçalho da tabela se repete no topo de cada página, dentro dos
        dados."""
    u = re.sub(r"\s+", " ", texto or "")
    u = u.replace(_CABECALHO, " ")
    u = re.sub(r"(\d{2}):\s+(\d{2}:\d{2})", r"\1:\2", u)
    u = re.sub(r"\b(APEX\d+)\s+(\d+)\b", r"\1\2", u)
    # OS TÍTULOS DE SEÇÃO SAEM, e esta linha custou uma leitura errada.
    #
    # O relatório abre cada dia com '8/24/26: 108 order(s)' e fecha com
    # 'TOTAL: 111 order(s)'. Achatado, esse título gruda no FIM da última
    # ordem do dia anterior — e o '108' virou o valor nocional daquela linha,
    # que é justamente a coluna que confere a leitura. A conferência passou a
    # aprovar a linha errada, ou seja: o defeito estragou o próprio detector
    # de defeito. Fora antes de qualquer leitura.
    u = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}:\s*\d+\s*order\(s\)", " ", u)
    u = re.sub(r"TOTAL:\s*(?:order\(s\))?\s*\d*\s*(?:order\(s\))?", " ", u)
    return u


def _numero(txt):
    if not _RE_NUMERO.match(txt or ""):
        return None
    try:
        return float(txt.replace(",", ""))
    except ValueError:
        return None


def _ler_uma_ordem(pedaco):
    """Uma linha da tabela vira dicionário, lendo da esquerda para a direita.

    A COLUNA DO PREÇO SAI DO TIPO DA ORDEM, e não da posição na fita. As
    colunas 'Limit Price' e 'Stop Price' são duas, mas só uma vem preenchida
    por linha, e a coluna vazia simplesmente não existe no texto extraído —
    contar posições daria o preço de stop como se fosse limite na metade das
    linhas. O tipo diz qual é qual, sem ambiguidade."""
    t = pedaco.split()
    if len(t) < 6:
        return None
    ordem = {"id": t[0], "lado": _LADOS.get(t[1]), "qtd": None, "ativo": None,
             "tipo": None, "preco_limite": None, "preco_stop": None,
             "estado": None, "rotulo": "", "executados": 0,
             "preco_medio": None, "hora_execucao": "", "carimbo": "",
             "conta": "", "nocional": None, "bruto": pedaco}
    if not ordem["lado"]:
        return None
    i = 2
    ordem["qtd"] = int(_numero(t[i]) or 0) if _numero(t[i]) is not None else None
    if not ordem["qtd"]:
        return None
    i += 1
    ordem["ativo"] = t[i].upper()
    i += 1

    # Tipo: "Stop Limit" tem duas palavras e precisa ser testado antes de "Stop".
    if i + 1 < len(t) and f"{t[i]} {t[i + 1]}" in _TIPOS:
        ordem["tipo"] = _TIPOS[f"{t[i]} {t[i + 1]}"]
        i += 2
    elif t[i] in _TIPOS:
        ordem["tipo"] = _TIPOS[t[i]]
        i += 1
    else:
        return None

    precos = []
    while i < len(t) and _numero(t[i]) is not None:
        precos.append(_numero(t[i]))
        i += 1
    if ordem["tipo"] == "LIMITE" and precos:
        ordem["preco_limite"] = precos[0]
    elif ordem["tipo"] == "STOP" and precos:
        ordem["preco_stop"] = precos[0]
    elif ordem["tipo"] == "STOP_LIMITE" and len(precos) >= 2:
        ordem["preco_limite"], ordem["preco_stop"] = precos[0], precos[1]
    # MERCADO não tem preço de entrada: as duas colunas vêm vazias.

    if i >= len(t) or t[i] not in _ESTADOS:
        return None
    ordem["estado"] = _ESTADOS[t[i]]
    i += 1

    # Rótulo livre ('Chart', 'DOM', 'multibracket'): tudo que não for número
    # nem data até a próxima coluna numérica.
    rotulo = []
    while i < len(t) and _numero(t[i]) is None and not re.match(r"^\d{2}/\d{2}/\d{4}", t[i]):
        rotulo.append(t[i])
        i += 1
    ordem["rotulo"] = " ".join(rotulo)

    if ordem["estado"] == "EXECUTADA":
        if i < len(t) and _numero(t[i]) is not None:
            ordem["executados"] = int(_numero(t[i]))
            i += 1
        i, ordem["hora_execucao"] = _consumir_data(t, i)
        if i < len(t) and _numero(t[i]) is not None:
            ordem["preco_medio"] = _numero(t[i])
            i += 1

    i, ordem["carimbo"] = _consumir_data(t, i)
    resto = t[i:]
    for palavra in resto:
        if re.match(r"^[A-Z]{2,}\d{4,}$", palavra):
            ordem["conta"] = palavra
            break
    # O NOCIONAL VEM DEPOIS DA PRAÇA (a coluna 'Venue', que neste relatório é
    # a moeda). Antes eu pegava o último número da linha, e bastava um resto
    # de título de seção grudado no fim para o número errado virar a
    # conferência. Ancorar na coluna anterior é o que torna a leitura desta
    # coluna independente do que houver depois dela.
    for n, palavra in enumerate(resto):
        if re.match(r"^[A-Z]{3}$", palavra):
            for adiante in resto[n + 1:]:
                v = _numero_de_dinheiro(adiante)
                if v is not None and v > 0:
                    ordem["nocional"] = v
                    break
            break
    return ordem


def _numero_de_dinheiro(txt):
    """Número que pode ser um VALOR, recusando pedaço de identificador.

    `000137` é metade de um número de conta que a quebra de página jogou para
    o fim da linha, e `float()` o aceita alegremente como 137. Foi o que a
    primeira versão leu como valor nocional de uma ordem de US$ 38 mil — e
    reprovou a linha por um motivo que não era o verdadeiro, o que é quase tão
    ruim quanto aprovar: manda procurar o defeito no lugar errado.

    Valor não começa com zero à esquerda; identificador começa. A regra é do
    formato, não do tamanho — chutar por magnitude ('número grande deve ser o
    nocional') acertaria neste extrato e erraria no primeiro contrato barato."""
    if not txt or re.match(r"^0\d", txt.replace(",", "")):
        return None
    return _numero(txt)


def _consumir_data(t, i):
    """Lê 'DD/MM/AAAA HH:MM:SS' a partir de `i` e devolve (novo_i, texto).

    A HORA É OPCIONAL, E ISSO NÃO É FROUXIDÃO — É A QUEBRA DE PÁGINA.
    Quando o cabeçalho da tabela se repete no meio de uma linha, ele empurra
    os pedaços da direita para depois, e sobra a data sozinha ou uma hora
    partida ('14:'). A primeira versão exigia data E hora coladas, não achava,
    e não avançava — o preço médio de execução ficava vazio e a ordem inteira
    era recusada. Era uma execução real de verdade indo para o lixo por causa
    de um espaço em branco.

    Aceitar a data sem a hora não afrouxa nada, porque quem valida o preço é a
    coluna nocional, e não o carimbo: uma linha remontada errado continua
    reprovando na conta de quantidade x preço x multiplicador."""
    if i >= len(t) or not re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", t[i]):
        return i, ""
    data = t[i]
    i += 1
    if i < len(t) and re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", t[i]):
        return i + 1, f"{data} {t[i]}"
    if i < len(t) and re.match(r"^\d{1,2}:$", t[i]):
        return i + 1, data          # hora partida na quebra de página
    return i, data


def ler_ordens(texto):
    """Todas as ordens do relatório, na ordem em que aparecem."""
    fita = _achatar(texto)
    cortes = [m.start() for m in _RE_ORDEM.finditer(fita)]
    ordens = []
    for n, ini in enumerate(cortes):
        fim = cortes[n + 1] if n + 1 < len(cortes) else len(fita)
        o = _ler_uma_ordem(fita[ini:fim].strip())
        if o:
            ordens.append(o)
    return ordens


def total_declarado(texto):
    """O 'TOTAL: N order(s)' que o próprio relatório imprime, ou None.

    Serve para o programa comparar o que LEU com o que o documento DIZ ter, e
    avisar quando faltou linha. Sem isso, um leitor que perdesse metade das
    ordens numa quebra de página entregaria meio diário com cara de diário
    inteiro."""
    # LÊ DO TEXTO CRU, e não de `_achatar`: é `_achatar` que apaga os títulos
    # de seção e o TOTAL, justamente para eles não virarem número de coluna.
    # Ler daqui o que lá foi apagado seria pedir o dado à função que existe
    # para removê-lo.
    plano = re.sub(r"\s+", " ", texto or "")
    m = re.search(r"TOTAL:\s*(?:order\(s\))?\s*(\d+)", plano)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*order\(s\)\s*$", plano.strip())
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# 3. A LEITURA SE CONFERE
# ---------------------------------------------------------------------------
def multiplicador_implicito(ordem, tolerancia=0.01):
    """Quantos dólares vale UM PONTO do contrato, segundo o próprio documento.

    `nocional = quantidade x preço x multiplicador`, então o multiplicador sai
    por divisão. Devolve None quando a linha não tem os três números — e None
    aqui quer dizer "não deu para conferir", que é diferente de "confere"."""
    q = ordem.get("executados") or ordem.get("qtd")
    p = ordem.get("preco_medio") or ordem.get("preco_limite") or ordem.get("preco_stop")
    n = ordem.get("nocional")
    if not q or not p or not n:
        return None
    bruto = n / (q * p)
    perto = round(bruto)
    # Multiplicador é número redondo E MAIOR OU IGUAL A 1 em todo contrato
    # listado (MES=5, MNQ=2, ES=50). Um valor quebrado é sinal de coluna
    # trocada, não de contrato exótico — então ele volta como está e a
    # conferência reprova.
    #
    # O `perto >= 1` foi acrescentado depois de a conferência APROVAR uma
    # linha em que o nocional lido era 108 (resto de título de seção): 108
    # dividido por 8 x 7691,50 dá 0,00175, que arredonda para ZERO, e zero
    # passava no teste de "é redondo". Um detector que aprova o absurdo por
    # arredondamento é pior que não ter detector, porque dá confiança falsa.
    if perto >= 1 and abs(bruto - perto) <= tolerancia:
        return float(perto)
    return bruto


def conferir_pela_nocional(ordem, tolerancia=0.01):
    """(ok, motivo) para UMA ordem executada.

    É esta função que impede uma troca silenciosa de coluna de virar diário
    errado. `ok=True` com motivo vazio significa que a conta fechou; `ok=True`
    com motivo significa que não deu para conferir (linha sem nocional), e a
    diferença importa: a segunda passa, mas passa avisada."""
    if ordem.get("estado") != "EXECUTADA":
        return True, ""
    if not ordem.get("preco_medio"):
        return False, "ordem executada sem preço médio de execução"
    if not ordem.get("executados"):
        return False, "ordem executada sem quantidade executada"
    if not ordem.get("nocional"):
        return True, "sem coluna de valor nocional para conferir"
    m = multiplicador_implicito(ordem, tolerancia)
    if m is None:
        return True, "sem números suficientes para conferir"
    if m < 1 or abs(m - round(m)) > tolerancia:
        return False, (f"o valor nocional não fecha com quantidade x preço "
                       f"(daria multiplicador {m:.4f}, que não é de contrato "
                       f"nenhum) — provável troca de coluna na leitura")
    return True, ""


# ---------------------------------------------------------------------------
# 4. AS EXECUÇÕES VIRAM OPERAÇÕES FECHADAS
# ---------------------------------------------------------------------------
def _chave_de_tempo(ordem):
    """Ordena pelo instante da execução. Carimbo ilegível vai para o fim em
    vez de para o começo: uma linha partida na quebra de página não pode
    reordenar o dia inteiro à frente das que estão íntegras."""
    txt = ordem.get("hora_execucao") or ordem.get("carimbo") or ""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2}):(\d{2})", txt)
    if not m:
        return (9999, 99, 99, 99, 99, 99)
    mes, dia, ano, hh, mm, ss = (int(g) for g in m.groups())
    return (ano, mes, dia, hh, mm, ss)


def operacoes_fechadas(ordens):
    """Casa entradas com saídas por FIFO e devolve (fechadas, sobras, recusadas).

    FIFO — o primeiro contrato a entrar é o primeiro a sair — porque é a regra
    que a própria corretora usa para apurar resultado, e porque qualquer outra
    escolha aqui seria minha, não dele.

    `fechadas` são operações com entrada, saída e quantidade, prontas para o
    diário. `sobras` é quantidade que ficou aberta ao fim do arquivo: ela NÃO
    vira resultado, porque não há preço de saída que exista. `recusadas` são
    as linhas que não passaram na conferência.

    Uma reversão direta (vendido 5, compra 12) fecha os 5 e abre 7 do outro
    lado — o laço trata isso naturalmente, sem caso especial, porque consome
    a fila até acabar e o que sobrar vira lote novo."""
    boas, recusadas = [], []
    for o in ordens:
        if o.get("estado") != "EXECUTADA":
            continue
        ok, motivo = conferir_pela_nocional(o)
        if ok:
            if motivo:
                o = dict(o, ressalva=motivo)
            boas.append(o)
        else:
            recusadas.append(dict(o, motivo=motivo))

    boas.sort(key=_chave_de_tempo)
    filas = {}          # ativo -> lista de lotes abertos [{lado, qtd, preco, ordem}]
    fechadas = []
    for o in boas:
        ativo = o["ativo"]
        fila = filas.setdefault(ativo, [])
        restante = int(o["executados"] or 0)
        preco = o["preco_medio"]
        lado = o["lado"]
        while restante > 0 and fila and fila[0]["lado"] != lado:
            lote = fila[0]
            casa = min(lote["qtd"], restante)
            fechadas.append({
                "ativo": ativo,
                "direcao": lote["lado"],
                "contratos": casa,
                "entrada": lote["preco"],
                "saida": preco,
                "pontos": ((preco - lote["preco"]) if lote["lado"] == "BUY"
                           else (lote["preco"] - preco)),
                "id_entrada": lote["ordem"]["id"],
                "id_saida": o["id"],
                "abertura": lote["ordem"].get("hora_execucao", ""),
                "fechamento": o.get("hora_execucao", ""),
                "multiplicador": (multiplicador_implicito(lote["ordem"])
                                  or multiplicador_implicito(o)),
                "rotulo": lote["ordem"].get("rotulo", ""),
            })
            lote["qtd"] -= casa
            restante -= casa
            if lote["qtd"] <= 0:
                fila.pop(0)
        if restante > 0:
            fila.append({"lado": lado, "qtd": restante, "preco": preco, "ordem": o})

    sobras = []
    for ativo, fila in filas.items():
        for lote in fila:
            if lote["qtd"] > 0:
                sobras.append({
                    "ativo": ativo, "direcao": lote["lado"], "contratos": lote["qtd"],
                    "entrada": lote["preco"], "id_entrada": lote["ordem"]["id"],
                    "abertura": lote["ordem"].get("hora_execucao", ""),
                })
    return fechadas, sobras, recusadas


def formato_de_data(texto):
    """'MDY', 'DMY' ou None — QUEM DECIDE É O DOCUMENTO.

    O extrato da Tradovate escreve 08/24/2026; o diário deste programa
    escreve 24/08/2026. Trocar os dois lança a operação no dia errado, e no
    dia errado ela cai no pregão errado, e o pregão errado muda a taxa de
    acerto que ele usa para decidir dinheiro. É um erro que não aparece: a
    data continua sendo uma data válida.

    A saída não é chutar 'corretora americana, deve ser MDY'. Basta UMA data
    do arquivo com um componente maior que 12 para o próprio documento
    responder — 08/24 só pode ser mês 08, dia 24. Num extrato com dezenas de
    ordens espalhadas pelo mês, essa data existe quase sempre.

    None quer dizer 'o arquivo não me disse', e quem chamou tem de tratar isso
    como pergunta em aberto, não como MDY silencioso."""
    for a, b in re.findall(r"\b(\d{1,2})/(\d{1,2})/\d{2,4}\b", texto or ""):
        if int(a) > 12:
            return "DMY"
        if int(b) > 12:
            return "MDY"
    return None


def data_br(txt, formato="MDY"):
    """'08/24/2026 00:07:24' -> '24/08/2026 00:07', no formato do diário.

    Devolve '' quando não há data: string vazia obriga quem chamou a decidir o
    que fazer, enquanto devolver a data de HOJE colocaria uma operação antiga
    no pregão de agora sem ninguém perceber."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\s+(\d{1,2}):(\d{2}))?", txt or "")
    if not m:
        return ""
    p1, p2, ano, hh, mm = m.groups()
    dia, mes = (p2, p1) if formato == "MDY" else (p1, p2)
    if len(ano) == 2:
        ano = f"20{ano}"
    hora = f" {int(hh):02d}:{mm}" if hh else ""
    return f"{int(dia):02d}/{int(mes):02d}/{ano}{hora}"


def resumo_da_leitura(ordens, fechadas, sobras, recusadas, total=None):
    """O que o programa vai DIZER antes de gravar qualquer coisa.

    Ele existe porque importação silenciosa é a pior forma de importação: o
    diário é a base do cálculo de acerto, e uma linha a mais ou a menos ali
    muda um número que ele usa para decidir dinheiro. Antes de gravar, ele lê
    o que vai entrar, o que ficou de fora, e por quê."""
    por_estado = {}
    for o in ordens:
        por_estado[o.get("estado") or "?"] = por_estado.get(o.get("estado") or "?", 0) + 1
    linhas = [f"Li {len(ordens)} ordem(ns) no arquivo."]
    if total is not None and total != len(ordens):
        linhas.append(
            f"⚠️ O relatório diz ter {total} ordem(ns) e eu li {len(ordens)}. "
            "A diferença costuma ser linha partida na quebra de página — "
            "confira antes de gravar.")
    if por_estado:
        linhas.append("Por situação: " + " · ".join(
            f"{k.lower()} {v}" for k, v in sorted(por_estado.items())))
    linhas.append(f"Viram operação fechada: {len(fechadas)}.")
    if sobras:
        linhas.append(
            "Ficou posição ABERTA no fim do arquivo (não vira resultado, "
            "porque não há preço de saída): " + " · ".join(
                f"{s['direcao']} {s['contratos']} {s['ativo']} @ {s['entrada']}"
                for s in sobras))
    if recusadas:
        linhas.append(f"NÃO importei {len(recusadas)} linha(s) que não passaram "
                      "na conferência:")
        for r in recusadas[:5]:
            linhas.append(f"   · ordem {r['id']}: {r['motivo']}")
        if len(recusadas) > 5:
            linhas.append(f"   · (e mais {len(recusadas) - 5})")
    return "\n".join(linhas)
