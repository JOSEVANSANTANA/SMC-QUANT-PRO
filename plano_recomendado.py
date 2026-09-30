# -*- coding: utf-8 -*-
"""COMO CONFIGURAR O PLANO PARA CHEGAR NA META — a conta, não o palpite.

POR QUE ESTE ARQUIVO EXISTE
----------------------------
28/08, 09:12. Ele: "ACABEI DE CONSEGUIR LIBERACAO MAIOR DE DROWDROW, ME AJUDA
A CONFIGURAR O PLANO DE TRADING PARA CONSEGUIR CHEGAR NA META POR FAVOR".

A resposta que ele recebeu foi um pedido de mais informação e, logo depois,
seiscentos caracteres de lixo. Mas o problema não era a resposta: era que a
pergunta ia para um MODELO DE LINGUAGEM quando ela é ARITMÉTICA. A meta está
no plano. O drawdown está no plano. O resultado do dia está no diário. O
ganho médio, a perda média e a taxa de acerto estão nas operações fechadas. O
ATR está na fita. O CVD está no motor de fluxo. Tudo o que a pergunta pede já
está medido dentro do programa — e nada disso chega ao modelo como conta
fechada, então ele opina.

É o mesmo defeito que `chance_de_bater_a_meta` já tinha consertado uma vez:
"lição vira texto no prompt, não vira acesso ao diário".

O QUE ESTE MÓDULO RECUSA A FAZER
---------------------------------
Ele NÃO responde "aumente o risco e você bate a meta". No dia deste log a
ferramenta aceitou risco de 30% sobre margem de US$2.000 com drawdown de
US$600 — e disse a verdade em uma linha que passou batida:

    ⚠️ PLANO: cada operação arrisca US$600.00. O seu drawdown máximo é
    US$600.00 — ou seja, 1.0 stop(s) encerram o seu dia.

UM stop e o dia acabou. Isso não é um plano agressivo, é um plano de uma
tentativa só. A meta não pode mandar no risco; quem manda no risco é o
drawdown, e a meta é CONSEQUÊNCIA. Quando a meta não cabe, este módulo diz
que não cabe e diz qual meta cabe — porque a alternativa é ele configurar
para o número que quer e descobrir o preço depois.

O ACHADO QUE IMPORTA MAIS QUE QUALQUER AJUSTE
----------------------------------------------
Do mesmo dia: acerto 50%, ganho médio US$80,62, perda média US$157,50.

O plano exigia R:R 1:2. A conta entregou 1:0,51. As entradas saíam com alvo
ao dobro do risco e o resultado real foi perda média DUAS VEZES maior que o
ganho médio — ou seja, o filtro de entrada estava fazendo o trabalho dele e a
SAÍDA não. Ganhador cortado cedo, perdedor indo até o stop inteiro.

Com esses números a esperança por operação é NEGATIVA (−US$38,44). Nenhum
ajuste de risco conserta esperança negativa: risco maior só acelera a perda.
Por isso a esperança é a PRIMEIRA coisa que este módulo calcula, e quando ela
é negativa a recomendação inteira muda de assunto — deixa de ser "como
configurar para ganhar mais" e passa a ser "por que cada operação perde".

TUDO AQUI É FUNÇÃO PURA. Entra número medido, sai número e a conta que o
gerou. Sem disco, sem rede, sem relógio, sem interface — para o teste poder
prender cada regra separada e para o texto que ele lê poder mostrar a conta.
"""

# Fatia do drawdown que UM stop pode consumir para o dia ainda ter jogo.
# 1/3 significa: três stops seguidos cabem antes de o dia acabar. Abaixo de
# dois, o plano vira uma tentativa só.
FRACAO_DO_DRAWDOWN_POR_STOP = 1.0 / 3.0

# Quantos stops seguidos um dia precisa tolerar para ser um plano, e não uma
# aposta. Dois é o mínimo defensável; três é o alvo.
STOPS_MINIMOS_NO_DIA = 2
STOPS_ALVO_NO_DIA = 3

# Margem de segurança sobre o R:R de empate. Empatar não é objetivo.
FOLGA_SOBRE_O_EMPATE = 1.35

# Abaixo disto a amostra não sustenta conclusão sobre taxa de acerto.
AMOSTRA_MINIMA = 20


def _n(valor, padrao=None):
    """Número, ou o padrão. Nunca levanta — entrada ruim aqui viraria
    exceção no meio do pregão."""
    try:
        if valor is None:
            return padrao
        return float(valor)
    except (TypeError, ValueError):
        return padrao


# ---------------------------------------------------------------------------
# 1) A ESPERANÇA. A primeira pergunta, e a que mais decide.
# ---------------------------------------------------------------------------
def esperanca_por_operacao(acerto, ganho_medio, perda_media):
    """Quanto UMA operação vale, em média, com os números dele.

    esperanca = acerto × ganho_médio − (1 − acerto) × perda_média

    `acerto` entra de 0 a 1. Devolve US$ por operação, ou None quando falta
    número — e None aqui é resposta legítima: sem operação fechada não existe
    esperança medida, e inventar uma seria inventar tudo o que vem depois.
    """
    p = _n(acerto)
    g = _n(ganho_medio)
    perda = _n(perda_media)
    if p is None or g is None or perda is None:
        return None
    if not (0.0 <= p <= 1.0):
        return None
    return p * g - (1.0 - p) * abs(perda)


def rr_realizado(ganho_medio, perda_media):
    """O R:R que a CONTA entregou — ganho médio ÷ perda média.

    É o número que denuncia a saída. O plano pede 1:2 na entrada; se aqui sai
    1:0,5, o alvo não está sendo alcançado e o stop está. Nenhum filtro de
    entrada conserta isso, porque o filtro já fez a parte dele."""
    g = _n(ganho_medio)
    perda = _n(perda_media)
    if g is None or perda is None or abs(perda) <= 0:
        return None
    return g / abs(perda)


def rr_para_ficar_no_azul(acerto, folga=FOLGA_SOBRE_O_EMPATE):
    """O R:R que a taxa de acerto DELE exige para a esperança ser positiva.

    No empate: acerto × R = (1 − acerto)  →  R = (1 − acerto) / acerto.
    Com 50% de acerto, empata em 1:1 — e é por isso que um plano de 1:2 com
    50% de acerto deveria estar ganhando. Devolve já com folga, porque
    configurar para empatar é configurar para pagar corretagem."""
    p = _n(acerto)
    if p is None or p <= 0 or p > 1:
        return None
    return ((1.0 - p) / p) * _n(folga, 1.0)


def acerto_para_o_rr(rr, folga=FOLGA_SOBRE_O_EMPATE):
    """O caminho inverso: com R:R de R, que taxa de acerto empata.

    acerto = 1 / (1 + R). Serve para transformar o R:R do plano em um piso de
    probabilidade honesto, em vez de um número redondo escolhido a dedo."""
    r = _n(rr)
    if r is None or r <= 0:
        return None
    empate = 1.0 / (1.0 + r)
    return min(0.95, empate * _n(folga, 1.0))


# ---------------------------------------------------------------------------
# 2) O TETO. Quem manda no risco é o drawdown, nunca a meta.
# ---------------------------------------------------------------------------
def risco_que_o_drawdown_permite(drawdown, stops_ate_parar=STOPS_ALVO_NO_DIA):
    """Quanto UMA operação pode arriscar para caberem N stops no dia.

    É a trava que faltou em 28/08: risco de US$600 com drawdown de US$600 dá
    exatamente UM stop. Com três, cada stop custa um terço — e o dia continua
    existindo depois do segundo erro."""
    dd = _n(drawdown)
    n = _n(stops_ate_parar, STOPS_ALVO_NO_DIA)
    if dd is None or dd <= 0 or n is None or n < 1:
        return None
    return dd / float(int(n))


def stops_que_cabem(drawdown, risco_por_operacao):
    """Quantos stops seguidos o dia aguenta com este risco. O número que
    transforma '30% de risco' em 'uma tentativa só'."""
    dd = _n(drawdown)
    r = _n(risco_por_operacao)
    if dd is None or r is None or r <= 0:
        return None
    return dd / r


def contratos_que_cabem(risco_usd, ticks_de_stop, valor_do_tick):
    """Tamanho da posição que o orçamento de risco paga. Sempre para baixo:
    arredondar para cima aqui é estourar o risco por decisão de arredondamento."""
    r = _n(risco_usd)
    t = _n(ticks_de_stop)
    vt = _n(valor_do_tick)
    if None in (r, t, vt) or t <= 0 or vt <= 0 or r <= 0:
        return None
    return int(r // (t * vt))


# ---------------------------------------------------------------------------
# 3) A META. O que ela exige, e se isso cabe no teto de cima.
# ---------------------------------------------------------------------------
def risco_que_a_meta_exige(falta, oportunidades, rr):
    """Risco por operação para a meta sair no prazo, supondo que TODAS
    acertem. É um piso otimista de propósito: se nem essa conta couber no
    drawdown, a meta não cabe de jeito nenhum."""
    f = _n(falta)
    n = _n(oportunidades)
    r = _n(rr)
    if None in (f, n, r) or n < 1 or r <= 0 or f <= 0:
        return None
    return (f / float(int(n))) / r


def meta_que_cabe(risco_permitido, oportunidades, rr, esperanca=None):
    """A meta que o drawdown COMPORTA — o número que substitui o que ele
    queria pelo que a conta aguenta.

    Com esperança medida, usa a esperança (realista). Sem ela, usa o caso de
    todas acertarem (otimista) e quem chama diz que é teto, não previsão."""
    r = _n(risco_permitido)
    n = _n(oportunidades)
    rr_ = _n(rr)
    if None in (r, n, rr_) or n < 1 or rr_ <= 0 or r <= 0:
        return None
    e = _n(esperanca)
    if e is not None:
        return e * int(n)
    return r * rr_ * int(n)


# ---------------------------------------------------------------------------
# 4) O MOMENTO DO MERCADO — o que a fita e o ATR permitem AGORA.
# ---------------------------------------------------------------------------
def leitura_do_momento(atr_ticks=None, cvd=None, negocios_na_fita=0,
                       ticks_de_stop=None):
    """O que o mercado de agora tem a dizer sobre o tamanho do stop e do alvo.

    Devolve um dicionário de ACHADOS, nunca uma ordem. Cada chave só aparece
    quando o dado existe: sem fita não há delta, e delta ausente é ausência,
    não zero — foi por isso que ele perguntou "qual o delta?" às 08:51 e
    recebeu 'não calculo delta no chute'. A resposta estava certa; o que
    faltava era ela chegar aqui quando existe.
    """
    achados = {}
    atr = _n(atr_ticks)
    stop = _n(ticks_de_stop)

    if atr is not None and atr > 0:
        achados["atr_ticks"] = atr
        # Stop abaixo de um ATR é varrido pela respiração normal do mercado.
        achados["stop_minimo_pelo_atr"] = int(round(atr))
        achados["stop_confortavel_pelo_atr"] = int(round(atr * 1.5))
        if stop is not None and stop > 0:
            achados["stop_atual_em_atr"] = stop / atr
            if stop < atr:
                achados["stop_curto_para_a_volatilidade"] = True

    n = _n(negocios_na_fita, 0) or 0
    d = _n(cvd)
    if n <= 0 or d is None:
        # A fita não está entregando. Dizer isso é o dado.
        achados["fita"] = "sem leitura"
    else:
        achados["fita"] = "lendo"
        achados["cvd"] = d
        achados["negocios"] = int(n)
        achados["lado_da_agressao"] = (
            "comprador" if d > 0 else "vendedor" if d < 0 else "equilibrado")
    return achados


# ---------------------------------------------------------------------------
# 5) O AGREGADOR. Junta tudo e devolve AJUSTES CONCRETOS.
# ---------------------------------------------------------------------------
def recomendar_plano(*, margem=None, drawdown=None, drawdown_restante=None,
                     meta=None, falta=None, oportunidades=None,
                     risco_pct=None, rr_minimo=None, probabilidade_minima=None,
                     max_stops_seguidos=None,
                     acerto=None, ganho_medio=None, perda_media=None,
                     amostra=0, ticks_de_stop=None, valor_do_tick=None,
                     atr_ticks=None, cvd=None, negocios_na_fita=0):
    """A recomendação inteira: achados, ajustes de campo e um veredito.

    Devolve {"achados": [...], "ajustes": [...], "veredito": str, "contas": {}}.

    `ajustes` é uma lista de {campo, de, para, porque} — campos REAIS do plano,
    para o painel poder aplicar com um clique e para o teste poder conferir
    cada um. Lista vazia significa que não há nada a mudar, e isso também é
    uma resposta.
    """
    achados, ajustes, contas = [], [], {}

    margem = _n(margem)
    dd = _n(drawdown)
    dd_resta = _n(drawdown_restante)
    risco_pct = _n(risco_pct)
    rr_atual = _n(rr_minimo)
    prob_atual = _n(probabilidade_minima)
    n_amostra = int(_n(amostra, 0) or 0)

    risco_atual = None
    if margem is not None and risco_pct is not None and margem > 0:
        risco_atual = margem * (risco_pct / 100.0)
        contas["risco_atual_usd"] = risco_atual

    # ---- (a) A ESPERANÇA MANDA NA CONVERSA -------------------------------
    esperanca = esperanca_por_operacao(acerto, ganho_medio, perda_media)
    realizado = rr_realizado(ganho_medio, perda_media)
    if esperanca is not None:
        contas["esperanca_usd"] = esperanca
    if realizado is not None:
        contas["rr_realizado"] = realizado

    esperanca_confiavel = esperanca is not None and n_amostra >= AMOSTRA_MINIMA
    if esperanca is not None and not esperanca_confiavel:
        achados.append(
            f"AMOSTRA PEQUENA: {n_amostra} operação(ões) fechada(s), e eu só "
            f"trato taxa de acerto como medida a partir de {AMOSTRA_MINIMA}. "
            "Os números abaixo saem do que existe — leia-os como indício, não "
            "como estatística.")

    if esperanca is not None and esperanca < 0:
        achados.append(
            f"CADA OPERAÇÃO ESTÁ VALENDO US$ {esperanca:,.2f} EM MÉDIA — "
            "negativo. Enquanto isso for verdade, mexer no risco só muda a "
            "velocidade da perda: risco maior perde mais rápido, risco menor "
            "perde mais devagar. Não existe configuração de tamanho que torne "
            "positiva uma esperança negativa.")

    # O achado mais útil do dia dele: plano pedindo 1:2, conta entregando 1:0,5.
    if realizado is not None and rr_atual is not None and rr_atual > 0:
        contas["rr_planejado"] = rr_atual
        if realizado < rr_atual * 0.6:
            achados.append(
                f"O PLANO PEDE 1:{rr_atual:g} E A CONTA ESTÁ ENTREGANDO "
                f"1:{realizado:.2f}. Ganho médio US$ {_n(ganho_medio, 0):,.2f} "
                f"contra perda média US$ {abs(_n(perda_media, 0)):,.2f}. "
                "O filtro de ENTRADA está fazendo o trabalho dele — quem não "
                "está entregando é a SAÍDA: o ganhador sai antes do alvo e o "
                "perdedor vai até o stop inteiro. Apertar R:R mínimo ou "
                "probabilidade mínima NÃO conserta isso, porque o problema "
                "não está na escolha do cenário. Está no trailing e no alvo.")

    # ---- (b) O TETO DE RISCO PELO DRAWDOWN -------------------------------
    base_dd = dd_resta if (dd_resta is not None and dd_resta > 0) else dd
    if base_dd is not None and base_dd > 0:
        contas["drawdown_considerado"] = base_dd
        permitido = risco_que_o_drawdown_permite(base_dd, STOPS_ALVO_NO_DIA)
        contas["risco_permitido_usd"] = permitido
        if risco_atual is not None and risco_atual > 0:
            cabem = stops_que_cabem(base_dd, risco_atual)
            contas["stops_que_cabem"] = cabem
            if cabem is not None and cabem < STOPS_MINIMOS_NO_DIA:
                achados.append(
                    f"COM O RISCO DE HOJE, {cabem:.1f} STOP(S) ENCERRAM O SEU "
                    f"DIA. Cada operação arrisca US$ {risco_atual:,.2f} contra "
                    f"um drawdown de US$ {base_dd:,.2f}. Isso não é um plano "
                    "agressivo, é um plano de uma tentativa: o primeiro erro "
                    "fecha o pregão, mesmo que o segundo cenário fosse o bom.")
                if margem and permitido:
                    novo_pct = (permitido / margem) * 100.0
                    ajustes.append({
                        "campo": "risco_pct",
                        "de": risco_pct, "para": round(novo_pct, 2),
                        "porque": (
                            f"US$ {permitido:,.2f} por operação faz caberem "
                            f"{STOPS_ALVO_NO_DIA} stops seguidos dentro do "
                            f"drawdown de US$ {base_dd:,.2f}. Com "
                            f"{risco_pct:g}% cabe {cabem:.1f}.")})

    # ---- (c) O QUE A META EXIGE, CONFRONTADO COM O TETO ------------------
    exigido = risco_que_a_meta_exige(falta, oportunidades,
                                     rr_atual if rr_atual else 2.0)
    if exigido is not None:
        contas["risco_exigido_pela_meta_usd"] = exigido
        permitido = contas.get("risco_permitido_usd")
        if permitido and exigido > permitido:
            # O TETO É O CASO DE ACERTAR TODAS. Ele é dito como teto, com
            # essas palavras — e quando existe esperança medida, a projeção
            # REALISTA sai junto. Sem isso, o número otimista apareceria logo
            # depois de "cada operação está perdendo dinheiro" e leria como
            # incentivo, que é o oposto do que esta função existe para fazer.
            teto = meta_que_cabe(permitido, oportunidades,
                                 rr_atual if rr_atual else 2.0)
            contas["meta_que_cabe_usd"] = teto
            projetada = meta_que_cabe(permitido, oportunidades,
                                      rr_atual if rr_atual else 2.0,
                                      esperanca) if esperanca is not None else None
            if projetada is not None:
                contas["meta_projetada_usd"] = projetada
            texto = (
                f"A META NÃO CABE NESTE DRAWDOWN. Faltam US$ "
                f"{_n(falta, 0):,.2f} em {int(_n(oportunidades, 0))} "
                f"operação(ões); mesmo ACERTANDO TODAS isso pediria US$ "
                f"{exigido:,.2f} de risco por operação, e o drawdown só "
                f"comporta US$ {permitido:,.2f}. Não é pessimismo, é divisão.")
            if teto is not None:
                texto += (f" O TETO no prazo — acertando todas, com o risco "
                          f"que cabe — é US$ {teto:,.2f}.")
            if projetada is not None and projetada < 0:
                texto += (f" E esse é o teto, não a expectativa: com o seu "
                          f"desempenho medido, a projeção destas "
                          f"{int(_n(oportunidades, 0))} operações é "
                          f"US$ {projetada:,.2f}.")
            elif projetada is not None:
                texto += (f" Com o seu desempenho medido, a projeção é "
                          f"US$ {projetada:,.2f}.")
            if teto is None:
                texto += (" Alongue o prazo da meta ou reduza o valor dela — "
                          "são as duas saídas que não passam por arriscar o "
                          "que você não tem.")
            achados.append(texto)

    # ---- (d) O PISO DE QUALIDADE, TIRADO DO ACERTO DELE ------------------
    if acerto is not None:
        rr_azul = rr_para_ficar_no_azul(acerto)
        if rr_azul is not None:
            contas["rr_para_ficar_no_azul"] = rr_azul
            if rr_atual is not None and rr_atual < rr_azul:
                ajustes.append({
                    "campo": "rr_minimo",
                    "de": rr_atual, "para": round(rr_azul, 2),
                    "porque": (
                        f"com {_n(acerto, 0) * 100:.0f}% de acerto, o R:R de "
                        f"empate é 1:{(1 - _n(acerto, 0)) / _n(acerto, 1):.2f}. "
                        f"1:{rr_azul:.2f} é esse empate com folga.")})
        if rr_atual is not None and rr_atual > 0:
            piso = acerto_para_o_rr(rr_atual)
            if piso is not None:
                contas["probabilidade_de_empate"] = piso * 100.0
                if prob_atual is not None and prob_atual < piso * 100.0:
                    ajustes.append({
                        "campo": "probabilidade_minima",
                        "de": prob_atual, "para": round(piso * 100.0),
                        "porque": (
                            f"num R:R 1:{rr_atual:g}, abaixo de "
                            f"{piso * 100:.0f}% de acerto a soma fica "
                            "negativa no longo prazo.")})

    # ---- (e) STOPS SEGUIDOS ----------------------------------------------
    #
    # OS AJUSTES TÊM DE SER COERENTES ENTRE SI. Encontrado ao ler a primeira
    # saída de verdade: com risco de 30% a lista dizia, na mesma tela,
    # "baixe o risco para 10%" E "baixe o freio de 2 stops para 1". O segundo
    # só valia se o primeiro fosse ignorado — a 10% cabem três stops e o freio
    # de 2 está certo. Uma recomendação que se contradiz na própria lista é
    # uma recomendação que ninguém segue.
    stops_cfg = _n(max_stops_seguidos)
    risco_depois = risco_atual
    for a in ajustes:
        if a["campo"] == "risco_pct" and margem:
            risco_depois = margem * (float(a["para"]) / 100.0)
    cabem_depois = stops_que_cabem(base_dd, risco_depois) \
        if (base_dd and risco_depois) else contas.get("stops_que_cabem")
    if stops_cfg is not None and cabem_depois is not None \
            and stops_cfg > cabem_depois:
        ajustes.append({
            "campo": "max_stops_seguidos",
            "de": stops_cfg, "para": max(1, int(cabem_depois)),
            "porque": (
                f"o freio está armado para {stops_cfg:g} stops seguidos, mas o "
                f"drawdown só paga {cabem_depois:.1f}. O freio nunca chegaria "
                "a disparar — o limite de perda chega antes dele.")})

    # ---- (f) O MOMENTO DO MERCADO ----------------------------------------
    momento = leitura_do_momento(atr_ticks=atr_ticks, cvd=cvd,
                                 negocios_na_fita=negocios_na_fita,
                                 ticks_de_stop=ticks_de_stop)
    contas["momento"] = momento
    if momento.get("stop_curto_para_a_volatilidade"):
        achados.append(
            f"O STOP DE {int(_n(ticks_de_stop, 0))} TICKS ESTÁ ABAIXO DO ATR "
            f"({momento['atr_ticks']:.0f} ticks). Um stop menor que a "
            "respiração normal do mercado é varrido sem o cenário ter sido "
            "invalidado — é assim que se toma stop numa leitura que estava "
            f"certa. Confortável aqui seria {momento['stop_confortavel_pelo_atr']} "
            "ticks.")
    if momento.get("fita") == "sem leitura":
        achados.append(
            "A FITA NÃO ESTÁ SENDO LIDA, então não há CVD para confirmar o "
            "lado. Sem ela, a recomendação acima é só plano e volatilidade — "
            "abra o Time & Sales no layout da Tradovate para o delta entrar "
            "na conta.")

    # ---- (g) TAMANHO DE POSIÇÃO QUE ISSO VIRA ----------------------------
    alvo_risco = contas.get("risco_permitido_usd") or risco_atual
    ctr = contratos_que_cabem(alvo_risco, ticks_de_stop, valor_do_tick)
    if ctr is not None:
        contas["contratos_recomendados"] = ctr
        if ctr < 1:
            achados.append(
                f"COM US$ {alvo_risco:,.2f} DE RISCO E STOP DE "
                f"{int(_n(ticks_de_stop, 0))} TICKS NÃO CABE NEM UM CONTRATO. "
                "Ou o stop encurta (e aí precisa caber na volatilidade), ou o "
                "drawdown precisa ser maior, ou este ativo não é para esta "
                "conta agora.")

    # ---- (h) O VEREDITO ---------------------------------------------------
    if esperanca is not None and esperanca < 0:
        veredito = ("Antes de configurar qualquer coisa: cada operação está "
                    "perdendo dinheiro em média. Conserte a saída — é ela que "
                    "está entregando um R:R pior do que o que a entrada "
                    "prometeu — e só depois mexa no tamanho.")
    elif "meta_que_cabe_usd" in contas:
        veredito = ("A meta de hoje não sai hoje sem estourar o drawdown. Os "
                    "ajustes abaixo são para o dia continuar existindo amanhã.")
    elif ajustes:
        veredito = ("O plano cabe, com estes ajustes. Cada um tem a conta que "
                    "o gerou ao lado.")
    else:
        veredito = ("Não há nada a ajustar no plano com os números de agora — "
                    "o que está configurado é coerente com o drawdown, com a "
                    "meta e com o seu desempenho medido.")

    return {"achados": achados, "ajustes": ajustes,
            "veredito": veredito, "contas": contas}


def texto_da_recomendacao(rec):
    """A recomendação em texto de mesa, para o chat e para o WhatsApp.

    Separado do cálculo de propósito: o número é testável sem a redação, e a
    redação muda sem risco de mexer na conta."""
    if not rec:
        return "Não consegui montar a recomendação: faltam números do plano."
    linhas = ["⚙️ COMO CONFIGURAR O PLANO — a conta, não o palpite", ""]
    for a in rec.get("achados") or []:
        linhas.append(f"• {a}")
    if rec.get("achados"):
        linhas.append("")
    ajustes = rec.get("ajustes") or []
    if ajustes:
        linhas.append("AJUSTES SUGERIDOS:")
        for a in ajustes:
            de = a.get("de")
            de_txt = f"{de:g}" if isinstance(de, (int, float)) else "—"
            linhas.append(f"  · {a['campo']}: {de_txt} → {a['para']:g}")
            linhas.append(f"    {a['porque']}")
        linhas.append("")
    linhas.append(f"➡️ {rec.get('veredito', '')}")
    return "\n".join(linhas).strip()
