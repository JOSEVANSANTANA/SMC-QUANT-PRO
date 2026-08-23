#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orbe_temas.py — Os temas visuais do Orbe da TIGER, como DADO e não como código.

POR QUE ISTO EXISTE COMO ARQUIVO SEPARADO
------------------------------------------
O pedido dele foi explícito: "o código deve ser estruturado de forma que trocar
o tema só atualize os assets visuais e as animações, sem exigir mudança no
código da mesa de IA".

Antes, a paleta e o rosto do Orbe estavam escritos DENTRO do laço de desenho do
`tiger_hud.py`, misturados com o radar, os painéis de telemetria e o
equalizador. Trocar de estilo exigia editar o mesmo arquivo que desenha a
telemetria — ou seja, mexer no que mostra número de conta para mudar cor de
enfeite. Isso é a receita para quebrar o que importa por causa do que não
importa.

Aqui um tema é um DICIONÁRIO: paleta + parâmetros de geometria + a função que
desenha o rosto. Acrescentar um tema novo é acrescentar uma entrada em
`TEMAS_DO_ORBE`. Nada no motor, na leitura de posição ou no envio de ordem
sabe que temas existem.

O QUE UM TEMA PODE E O QUE NÃO PODE
------------------------------------
PODE: cor, espessura, geometria do rosto, número de anéis, estilo do
equalizador, e trocar a função de desenho do rosto inteira.

NÃO PODE: mudar o que a telemetria diz. Um tema é pele. Se um dia um tema
precisar esconder um dado para "ficar mais limpo", a resposta é não — o painel
existe para mostrar o número, e esconder número por estética é a mesma família
de erro que inventar número por estética.
"""

import math


# =====================================================================
#  AS CORES DE ESTADO — o que o Orbe está fazendo, dito por cor
# =====================================================================
#  Ele pediu: parado = azul frio pulsando; falando = verde-azulado vibrante;
#  pensando = azul profundo; ação confirmada = âmbar firme.
#
#  ISTO NÃO É SÓ ENFEITE. O trader olha o Orbe de longe, no meio do pregão,
#  sem ler texto. A cor é a única informação que atravessa a periferia da
#  visão — e por isso ela tem de ser inequívoca e SEMPRE derivada do estado
#  real, nunca de um timer decorativo.
CORES_DE_ESTADO = {
    "STANDBY":  {"principal": "#2f6f9f", "brilho": "#4da3d9", "pulso": 0.9,
                 "rotulo": "OBSERVANDO"},
    "OUVINDO":  {"principal": "#00d9ff", "brilho": "#7df1ff", "pulso": 2.2,
                 "rotulo": "OUVINDO"},
    "PENSANDO": {"principal": "#1f5fd0", "brilho": "#5b8ff5", "pulso": 1.6,
                 "rotulo": "CALCULANDO"},
    "FALANDO":  {"principal": "#00ff9d", "brilho": "#8affd4", "pulso": 3.0,
                 "rotulo": "FALANDO"},
    "ACAO":     {"principal": "#ffb400", "brilho": "#ffd980", "pulso": 1.2,
                 "rotulo": "ORDEM CONFIRMADA"},
}


def cores_do_estado(estado):
    """A paleta do estado atual. Estado desconhecido cai em STANDBY.

    Cair no padrão em vez de levantar é deliberado: um estado novo que alguém
    acrescente no futuro não pode apagar o Orbe no meio do pregão."""
    return CORES_DE_ESTADO.get(str(estado or "").upper(), CORES_DE_ESTADO["STANDBY"])


def abertura_da_boca(estado, envelope, fase):
    """Quanto a boca do tigre está aberta agora — de 0.0 (fechada) a 1.0.

    HONESTIDADE SOBRE O QUE ISTO É E O QUE NÃO É
    ---------------------------------------------
    Ele pediu "lip-sync profissional". Lip-sync de verdade — a boca formando
    a FORMA de cada fonema — exige análise fonética do áudio, quadro a quadro.
    O que existe aqui é outra coisa, e o nome certo importa: a boca é dirigida
    pela ENERGIA da fala, não pelo fonema.

    Na prática, para quem olha, o efeito é convincente: a boca abre nas
    sílabas fortes e fecha nas pausas. Mas chamar isso de lip-sync seria
    vender o que não foi feito, e este projeto não faz isso nem com número de
    conta nem com enfeite de tela.

    `envelope` é a amplitude da fala no instante (0.0 a 1.0), quando a camada
    de voz consegue medir. Sem medida (`None`), cai numa oscilação de fala
    plausível — e ela SÓ roda quando o estado é FALANDO, ou seja, quando a
    TIGER está de fato falando. A boca nunca se mexe com a boca calada.
    """
    if str(estado or "").upper() != "FALANDO":
        return 0.0
    if envelope is None:
        # Duas senoides de períodos diferentes: evita o "boneco de ventríloquo"
        # de uma abertura perfeitamente periódica.
        bruto = (math.sin(fase * 7.0) * 0.5 + math.sin(fase * 11.3) * 0.3 + 0.6)
        return max(0.05, min(1.0, bruto))
    try:
        return max(0.0, min(1.0, float(envelope)))
    except (TypeError, ValueError):
        return 0.0


def barras_do_equalizador(estado, envelope, fase, n=24):
    """As alturas (0.0 a 1.0) das barras do equalizador de voz.

    Substitui a senoide única por um equalizador de N barras, que é o que
    lê como "voz" para o olho. Em silêncio as barras repousam numa linha
    baixa — não em zero absoluto, senão o painel parece desligado quando na
    verdade está só quieto.
    """
    ativo = str(estado or "").upper() in ("FALANDO", "OUVINDO")
    if not ativo:
        return [0.06] * n
    try:
        ganho = 1.0 if envelope is None else max(0.15, min(1.0, float(envelope)))
    except (TypeError, ValueError):
        ganho = 1.0
    barras = []
    for i in range(n):
        # A janela central é mais alta: voz tem mais energia no meio do
        # espectro, e visualmente isso dá o formato de "sino" que se espera.
        centro = 1.0 - abs((i / max(1, n - 1)) - 0.5) * 1.6
        centro = max(0.15, centro)
        osc = (math.sin(fase * 6.0 + i * 0.7) * 0.35
               + math.sin(fase * 9.1 + i * 1.3) * 0.25 + 0.55)
        barras.append(max(0.06, min(1.0, centro * osc * ganho)))
    return barras


# =====================================================================
#  OS ROSTOS — cada tema desenha o seu
# =====================================================================
#  Assinatura de todo desenhista de rosto:
#      desenhar(canvas, cx, cy, escala, cor, fase, abertura) -> None
#
#  `cor` é o dicionário devolvido por `cores_do_estado`, para o rosto
#  acompanhar o estado sem cada tema reimplementar essa regra.

def _rosto_classico(canvas, cx, cy, s, cor, fase, abertura):
    """O rosto que já existia: felino cibernético de traço fino."""
    c, brilho = cor["principal"], cor["brilho"]
    canvas.create_oval(cx - s * 1.15, cy - s * 1.15, cx + s * 1.15, cy + s * 1.15,
                       fill="#030c18", outline="#07324d", width=1.5)
    for lado in (-1, 1):
        canvas.create_polygon(
            cx + lado * s * 0.62, cy - s * 0.22, cx + lado * s * 0.22, cy - s * 0.14,
            cx + lado * s * 0.38, cy - s * 0.02, cx + lado * s * 0.60, cy - s * 0.12,
            fill="#041a2f", outline=c, width=1.5)
        canvas.create_oval(cx + lado * s * 0.30 if lado > 0 else cx - s * 0.48,
                           cy - s * 0.19,
                           cx + s * 0.48 if lado > 0 else cx - s * 0.30,
                           cy - s * 0.05, fill="#ffb700", outline="")
        canvas.create_line(cx + lado * s * 0.70, cy - s * 0.34,
                           cx + lado * s * 0.18, cy - s * 0.20, fill=c, width=2)
    _boca_e_focinho(canvas, cx, cy, s, c, brilho, abertura)


def _rosto_predador_quantico(canvas, cx, cy, s, cor, fase, abertura):
    """QUANTUM PREDATOR — o rosto em camadas, denso, com malha de energia.

    A referência que ele mandou é uma imagem gerada por IA: um tigre de
    energia, fotorrealista. Isso não se desenha com linha e polígono num
    Canvas de Tkinter, e fingir que sim entregaria um resultado pior que o
    atual. O que dá para fazer — e é o que está aqui — é um rosto VETORIAL
    muito mais denso: malha poligonal, camadas concêntricas, listras que
    respiram com a fase e olhos com núcleo brilhante.

    (Se um dia quiser o tigre fotorrealista de verdade, o caminho é outro:
    carregar um PNG como asset do tema. A estrutura de temas já comporta —
    ver `TEMAS_DO_ORBE`, campo `imagem`.)
    """
    c, brilho = cor["principal"], cor["brilho"]
    pulso = 1.0 + math.sin(fase * cor["pulso"]) * 0.06

    # Camadas concêntricas do reator facial — profundidade por sobreposição.
    for i, (mult, larg) in enumerate(((1.30, 1), (1.15, 2), (0.98, 1))):
        canvas.create_oval(cx - s * mult * pulso, cy - s * mult * pulso,
                           cx + s * mult * pulso, cy + s * mult * pulso,
                           fill="#020a14" if i == 0 else "",
                           outline=brilho if i == 1 else "#07324d",
                           width=larg)

    # Malha de energia: raios do centro para a borda, densidade de "quantum".
    for k in range(18):
        ang = (k / 18.0) * math.tau + fase * 0.15
        r1, r2 = s * 0.98, s * 1.30
        canvas.create_line(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1,
                           cx + math.cos(ang) * r2, cy + math.sin(ang) * r2,
                           fill=c if k % 3 == 0 else "#07324d", width=1)

    # Olhos predadores com núcleo — polígono externo + íris + fenda vertical.
    for lado in (-1, 1):
        canvas.create_polygon(
            cx + lado * s * 0.70, cy - s * 0.26, cx + lado * s * 0.20, cy - s * 0.16,
            cx + lado * s * 0.36, cy + s * 0.02, cx + lado * s * 0.68, cy - s * 0.10,
            fill="#04121f", outline=brilho, width=2)
        ix1 = cx + (lado * s * 0.28 if lado > 0 else -s * 0.52)
        ix2 = cx + (s * 0.52 if lado > 0 else -s * 0.28)
        canvas.create_oval(ix1, cy - s * 0.21, ix2, cy - s * 0.03,
                           fill="#ffb400", outline=brilho, width=1)
        canvas.create_line(cx + lado * s * 0.40, cy - s * 0.23,
                           cx + lado * s * 0.40, cy - s * 0.01,
                           fill="#000000", width=3)
        # Sobrancelha angulada dupla — o "bravo focado".
        for off in (0.0, 0.10):
            canvas.create_line(cx + lado * s * (0.78 - off), cy - s * (0.38 + off),
                               cx + lado * s * (0.16 + off), cy - s * (0.22 + off),
                               fill=c, width=2)

    # Listras de testa que respiram com a fase.
    for j, base in enumerate((0.70, 0.54, 0.40)):
        respiro = math.sin(fase * 2.0 + j) * 0.03
        canvas.create_line(cx - s * (0.26 - j * 0.05), cy - s * (base + respiro),
                           cx + s * (0.26 - j * 0.05), cy - s * (base + respiro),
                           fill=brilho if j == 0 else c, width=2)

    _boca_e_focinho(canvas, cx, cy, s, c, brilho, abertura, denso=True)


def _rosto_espectral(canvas, cx, cy, s, cor, fase, abertura):
    """SPECTRAL TIGER — traço mínimo, quase fantasma. Para quem quer o painel
    limpo e a atenção nos números, não no bicho."""
    c, brilho = cor["principal"], cor["brilho"]
    canvas.create_oval(cx - s * 1.05, cy - s * 1.05, cx + s * 1.05, cy + s * 1.05,
                       fill="", outline=c, width=1)
    for lado in (-1, 1):
        canvas.create_line(cx + lado * s * 0.58, cy - s * 0.20,
                           cx + lado * s * 0.24, cy - s * 0.12,
                           fill=brilho, width=3)
    _boca_e_focinho(canvas, cx, cy, s, c, brilho, abertura, minimalista=True)


def _rosto_retro(canvas, cx, cy, s, cor, fase, abertura):
    """RETRO TERM — terminal verde de fósforo. Sem curva, só caractere e bloco."""
    c = "#33ff66"
    canvas.create_rectangle(cx - s, cy - s, cx + s, cy + s, fill="#001200",
                            outline=c, width=1)
    for lado in (-1, 1):
        canvas.create_rectangle(cx + lado * s * 0.55 - s * 0.12, cy - s * 0.22,
                                cx + lado * s * 0.55 + s * 0.12, cy - s * 0.02,
                                fill=c, outline="")
    alt = s * 0.06 + abertura * s * 0.26
    canvas.create_rectangle(cx - s * 0.30, cy + s * 0.28,
                            cx + s * 0.30, cy + s * 0.28 + alt,
                            fill=c, outline="")


def _boca_e_focinho(canvas, cx, cy, s, c, brilho, abertura, denso=False,
                    minimalista=False):
    """Focinho e boca — a boca ABRE conforme `abertura` (ver `abertura_da_boca`).

    Era uma linha fixa. Agora a mandíbula desce, e é o que dá a leitura
    imediata de "ela está falando" sem precisar ler o texto de status."""
    ny = cy + s * 0.16
    # Focinho.
    canvas.create_polygon(cx - s * 0.14, ny, cx + s * 0.14, ny, cx, ny + s * 0.14,
                          fill=brilho if denso else c, outline="")
    # Cavidade da boca — a altura é o que anima.
    queda = s * (0.10 + abertura * 0.34)
    canvas.create_arc(cx - s * 0.34, ny + s * 0.06,
                      cx + s * 0.34, ny + s * 0.06 + queda * 2,
                      start=200, extent=140, style="arc", outline=c,
                      width=3 if denso else 2)
    if abertura > 0.25 and not minimalista:
        # Interior da boca aparece só quando abre de verdade.
        canvas.create_oval(cx - s * 0.20, ny + s * 0.12,
                           cx + s * 0.20, ny + s * 0.12 + queda,
                           fill="#0a0000", outline=c, width=1)
    if not minimalista:
        for lado in (-1, 1):
            for w_off in (0.0, 0.08, 0.16):
                canvas.create_line(cx + lado * s * 0.24, ny + s * (0.24 + w_off),
                                   cx + lado * s * 0.86, ny + s * (0.10 + w_off * 1.6),
                                   fill=c, width=1)


# =====================================================================
#  O REGISTRO DE TEMAS — acrescentar um tema é acrescentar uma entrada
# =====================================================================
TEMAS_DO_ORBE = {
    "quantum_predator": {
        "rotulo": "Quantum Predator",
        "descricao": "Rosto em camadas com malha de energia. O mais denso.",
        "rosto": _rosto_predador_quantico,
        "aneis": 5,
        "particulas": 26,
        "equalizador": "barras",
        "imagem": None,      # reservado: PNG como rosto, se um dia quiser
    },
    "classic_matrix": {
        "rotulo": "Classic Matrix",
        "descricao": "O felino cibernético original, traço fino.",
        "rosto": _rosto_classico,
        "aneis": 4,
        "particulas": 18,
        "equalizador": "barras",
        "imagem": None,
    },
    "spectral_tiger": {
        "rotulo": "Spectral Tiger",
        "descricao": "Traço mínimo. Para quando a atenção é dos números.",
        "rosto": _rosto_espectral,
        "aneis": 2,
        "particulas": 8,
        "equalizador": "onda",
        "imagem": None,
    },
    "retro_term": {
        "rotulo": "Retro Term",
        "descricao": "Terminal de fósforo verde. Sem curva, só bloco.",
        "rosto": _rosto_retro,
        "aneis": 1,
        "particulas": 0,
        "equalizador": "barras",
        "imagem": None,
    },
}

TEMA_PADRAO = "quantum_predator"


def tema(nome=None):
    """O tema pedido, ou o padrão. Nome desconhecido NÃO quebra o Orbe.

    Um `KeyError` aqui apagaria o painel inteiro por causa de uma string de
    configuração errada — e o painel mostra posição aberta e P&L."""
    return TEMAS_DO_ORBE.get(str(nome or "").strip().lower(),
                             TEMAS_DO_ORBE[TEMA_PADRAO])


def nomes_dos_temas():
    """(chave, rótulo) de cada tema, para montar o seletor da interface."""
    return [(k, v["rotulo"]) for k, v in TEMAS_DO_ORBE.items()]
