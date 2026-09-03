"""A MESA TEM QUATRO CONTRATOS — E TRÊS COISAS AINDA FALAVAM DE UM SÓ.

31/08. Ele abriu quatro janelas da Tradovate (MESU6, MNQU6, MGCV6, MBTU6) e
mandou o robô operar todas. O motor passou a analisar as quatro. Três peças
por baixo continuaram raciocinando como se houvesse uma:

  1. O CANCELAMENTO. Ele escreveu: "tive uma impressão de que era para
     cancelar uma e cancelou outra, verifica se foi isso mesmo por favor".
     Estava certo, e era pior. Às 17:15 o log dizia

         ✅ ORDENS CANCELADAS NA PLATAFORMA: BUY MGCV6 19 ctr @ 4453.75
            ... ordens canceladas na plataforma (3 → 0)
         17:20 ℹ️ NADA A CANCELAR NA PLATAFORMA: BUY MESU6 13 ctr @ 7683.75

     Duas causas somadas. A varredura de DOM que roda logo depois do clique
     fazia `querySelectorAll('a, button, span, div')` na PÁGINA e clicava em
     tudo que dissesse "cancelar" — e o painel de ordens da Tradovate lista
     os quatro contratos juntos. E a conferência contava as ordens da CONTA
     INTEIRA: "3 → 0" não afirma nada sobre o MGCV6. Cancelar o ouro
     derrubava o índice, a Nasdaq e o bitcoin, e cinco minutos depois o MESU6
     aparecia como "nada a cancelar" porque já tinha morrido ali atrás.

  2. O RISCO. `drawdown_restante_hoje` descontava só o que já tinha DOÍDO.
     Quatro cenários no mesmo minuto usavam o mesmo restante do dia para se
     dimensionar; com a fatia padrão de um terço por operação, quatro
     entradas comprometem 132% do que restava — e nenhuma via a outra.

  3. O RUÍDO DO TRAILING. Um `_ultimo_atr` global, sem dono e sem hora,
     dividido pelo tick do ativo DA ORDEM. Está no test_atr_pela_fita.

Este arquivo tranca 1 e 2. Nenhum destes testes conhece Chrome, disco ou
corretora: são regras, e regra se confere na mesa da cozinha.
"""

import os
import unittest

from harness import RAIZ, carregar, fonte_do_arquivo, funcao_inteira


def _ns():
    return carregar(
        ["risco_comprometido_nas_posicoes", "texto_do_risco_comprometido",
         "drawdown_restante_hoje", "valor_por_ponto_do_ativo",
         "VALOR_POR_PONTO", "VALOR_POR_PONTO_PADRAO"],
        stubs={"plano_da_conta_ativa": lambda: {},
               "operacoes_fechadas_hoje": lambda **_: [],
               "carregar_posicoes": lambda: [],
               "_e_da_conta_ativa": lambda p: True})


def _pos(**kw):
    base = {"status": "PENDENTE", "direcao": "BUY", "ativo": "MESU6",
            "contratos": 1, "entry": 7600.0, "stop": 7592.0}
    base.update(kw)
    return base


# ======================================================================
#  O RISCO QUE JÁ ESTÁ NA MESA
# ======================================================================
class TestRiscoComprometido(unittest.TestCase):

    def test_pendente_reserva_a_distancia_inteira_ate_o_stop(self):
        ns = _ns()
        # MES: 8 pontos × US$5 × 3 contratos = US$120.
        self.assertEqual(
            ns["risco_comprometido_nas_posicoes"]([_pos(contratos=3)]), 120.0)

    def test_soma_ATIVOS_DIFERENTES(self):
        """O ponto todo. Antes, cada cenário era dimensionado como se fosse o
        único do dia."""
        ns = _ns()
        total = ns["risco_comprometido_nas_posicoes"]([
            _pos(ativo="MESU6", contratos=2),                    # 8pt×5×2 = 80
            _pos(ativo="MNQU6", entry=19400.0, stop=19380.0,     # 20pt×2×1 = 40
                 contratos=1),
            _pos(ativo="MGCV6", entry=4450.0, stop=4445.0,       # 5pt×10×1 = 50
                 contratos=1),
        ])
        self.assertEqual(total, 170.0)

    def test_aberta_PERDENDO_reserva_so_o_que_FALTA_ate_o_stop(self):
        """O caminho já andado está em `pnl_atual`, que quem chama soma à
        parte. Reservar a distância cheia da entrada aqui contaria o prejuízo
        duas vezes e apertaria a conta além do que o plano manda."""
        ns = _ns()
        p = _pos(status="ABERTA", contratos=1, entry=7600.0, stop=7592.0,
                 preco_atual=7596.0)
        # Faltam 4 pontos até o stop × US$5 = US$20 (e não os 40 da entrada).
        self.assertEqual(ns["risco_comprometido_nas_posicoes"]([p]), 20.0)

    def test_aberta_GANHANDO_nao_reserva_mais_que_o_risco_planejado(self):
        """Um vencedor que correu 10 pontos não passa a arriscar 18. O teto é
        o risco que o plano autorizou quando dimensionou: entrada → stop."""
        ns = _ns()
        p = _pos(status="ABERTA", contratos=1, entry=7600.0, stop=7592.0,
                 preco_atual=7610.0)
        self.assertEqual(ns["risco_comprometido_nas_posicoes"]([p]), 40.0)

    def test_stop_JA_NO_LUCRO_nao_reserva_nada(self):
        """Num BUY com o stop ACIMA da entrada, bater o stop dá lucro: essa
        posição não consome mais nada do drawdown do dia. Em módulo, ela
        reservaria justamente o lucro protegido — o contrário do que se
        quer."""
        ns = _ns()
        p = _pos(status="ABERTA", direcao="BUY", entry=7600.0, stop=7615.0,
                 preco_atual=7620.0)
        self.assertEqual(ns["risco_comprometido_nas_posicoes"]([p]), 0.0)
        v = _pos(status="ABERTA", direcao="SELL", entry=7600.0, stop=7585.0,
                 preco_atual=7580.0)
        self.assertEqual(ns["risco_comprometido_nas_posicoes"]([v]), 0.0)

    def test_sell_conta_para_o_lado_certo(self):
        ns = _ns()
        p = _pos(direcao="SELL", entry=7600.0, stop=7608.0, contratos=2)
        self.assertEqual(ns["risco_comprometido_nas_posicoes"]([p]), 80.0)

    def test_fechada_cancelada_e_excluida_NAO_reservam(self):
        ns = _ns()
        for st in ("FECHADA", "CANCELADA", "EXCLUIDA", "SUBSTITUIDA", ""):
            self.assertEqual(
                ns["risco_comprometido_nas_posicoes"]([_pos(status=st)]), 0.0)

    def test_registro_torto_nao_derruba_a_conta(self):
        """Diário de meses tem linha antiga, campo faltando e texto onde
        devia haver número. Uma exceção aqui apagaria a trava inteira, porque
        quem chama devolve o drawdown CHEIO no `except`."""
        ns = _ns()
        tortos = [
            _pos(stop=None), _pos(entry=None), _pos(contratos=0),
            _pos(contratos="três"), _pos(stop="x"), _pos(direcao=""),
            {}, {"status": "PENDENTE"},
        ]
        self.assertEqual(ns["risco_comprometido_nas_posicoes"](tortos), 0.0)
        self.assertEqual(ns["risco_comprometido_nas_posicoes"](None), 0.0)


class TestODrawdownRestanteDescontaOsOutrosAtivos(unittest.TestCase):

    def test_o_que_esta_na_mesa_sai_do_orcamento(self):
        ns = _ns()
        ns2 = carregar(
            ["drawdown_restante_hoje", "risco_comprometido_nas_posicoes",
             "valor_por_ponto_do_ativo", "VALOR_POR_PONTO",
             "VALOR_POR_PONTO_PADRAO"],
            stubs={"plano_da_conta_ativa": lambda: {},
                   "operacoes_fechadas_hoje": lambda **_: [],
                   "_e_da_conta_ativa": lambda p: True,
                   "carregar_posicoes": lambda: [
                       _pos(ativo="MESU6", contratos=3)]})    # US$120
        self.assertEqual(
            ns2["drawdown_restante_hoje"]({"drawdown_maximo": 1000}), 880.0)
        del ns

    def test_LUCRO_NAO_ENGOLE_o_risco_comprometido(self):
        """A armadilha que este teste existe para prender.

        A primeira versão escreveu `min(0.0, realizado + aberto - pendente)`.
        O grampo `min(0.0, ...)` existe para que LUCRO não aumente o limite —
        e, com o risco somado ali dentro, num dia positivo o grampo engolia a
        trava inteira. Ou seja: a proteção contra empilhar ordem sumia
        justamente no dia em que ele empilha mais ordem.

        Lucro não sobe o teto; risco em aberto desce o que sobrou. São duas
        regras, e elas moram em linhas diferentes."""
        ns2 = carregar(
            ["drawdown_restante_hoje", "risco_comprometido_nas_posicoes",
             "valor_por_ponto_do_ativo", "VALOR_POR_PONTO",
             "VALOR_POR_PONTO_PADRAO"],
            stubs={"plano_da_conta_ativa": lambda: {},
                   "operacoes_fechadas_hoje": lambda **_: [
                       {"pnl_final": 5000.0}],                # dia MUITO bom
                   "_e_da_conta_ativa": lambda p: True,
                   "carregar_posicoes": lambda: [
                       _pos(ativo="MESU6", contratos=3)]})    # US$120 na mesa
        self.assertEqual(
            ns2["drawdown_restante_hoje"]({"drawdown_maximo": 1000}), 880.0,
            "com lucro no dia, o risco comprometido continua descontando")

    def test_nunca_devolve_negativo(self):
        ns2 = carregar(
            ["drawdown_restante_hoje", "risco_comprometido_nas_posicoes",
             "valor_por_ponto_do_ativo", "VALOR_POR_PONTO",
             "VALOR_POR_PONTO_PADRAO"],
            stubs={"plano_da_conta_ativa": lambda: {},
                   "operacoes_fechadas_hoje": lambda **_: [],
                   "_e_da_conta_ativa": lambda p: True,
                   "carregar_posicoes": lambda: [
                       _pos(ativo="MESU6", contratos=99)]})
        self.assertEqual(
            ns2["drawdown_restante_hoje"]({"drawdown_maximo": 1000}), 0.0)

    def test_o_disco_e_lido_UMA_vez(self):
        """Esta função roda em TODO dimensionamento. Duas leituras do diário
        por chamada é o tipo de custo que ninguém vê e todo mundo paga."""
        corpo = funcao_inteira(fonte_do_arquivo(), "drawdown_restante_hoje")
        self.assertEqual(corpo.count("carregar_posicoes()"), 1)


class TestOTraderDESCOBREQuemSeguraOOrcamento(unittest.TestCase):
    """Número sem dono é o silêncio que faz ele desconfiar da ferramenta."""

    def test_a_frase_nomeia_ativo_direcao_e_valor(self):
        ns = _ns()
        txt = ns["texto_do_risco_comprometido"]([
            _pos(ativo="MNQU6", direcao="SELL", entry=19400.0, stop=19420.0,
                 contratos=2)])
        for pedaco in ("MNQU6", "SELL", "2 ctr", "80"):
            self.assertIn(pedaco, txt)

    def test_sem_nada_na_mesa_a_frase_e_vazia(self):
        ns = _ns()
        self.assertEqual(ns["texto_do_risco_comprometido"]([]), "")
        self.assertEqual(
            ns["texto_do_risco_comprometido"]([_pos(status="FECHADA")]), "")

    def test_o_motor_diz_isso_quando_recusa_por_tamanho(self):
        """Sem esta linha ele lê 'não abri MNQU6' e vai procurar o defeito no
        MNQU6, quando quem gastou o orçamento foi o MGCV6."""
        fonte = fonte_do_arquivo()
        i = fonte.index('self.log(f"🚫 NÃO ABRI a posição: {motivo}")')
        self.assertIn("texto_do_risco_comprometido", fonte[i - 900:i])


# ======================================================================
#  O CANCELAMENTO QUE ACERTAVA O VIZINHO
# ======================================================================
class TestAVarreduraNaoLimpaODeskInteiro(unittest.TestCase):

    def _fonte(self):
        return fonte_do_arquivo(os.path.join(RAIZ, "tradovate_auto.py"))

    def test_a_varredura_procura_o_TICKER_antes_de_clicar(self):
        fonte = self._fonte()
        i = fonte.index("_JS_VARREDURA_CANCELAR = r")
        js = fonte[i:fonte.index("def _js_varredura_cancelar", i)]
        self.assertIn("daOrdemAlvo", js)
        self.assertIn("parentElement", js,
                      "achar a LINHA da ordem é subir pelos ancestrais")
        # O clique só acontece dentro do teste do alvo.
        for gatilho in ("clicar(el); clicados++",
                        "clicar(xBtns[j]); clicados++"):
            j = js.index(gatilho)
            self.assertIn("daOrdemAlvo", js[j - 120:j])

    def test_SEM_alvo_a_varredura_nao_clica_em_nada(self):
        """Varrer o desk inteiro é uma decisão grande demais para ser o
        comportamento padrão de um valor ausente."""
        fonte = self._fonte()
        i = fonte.index("_JS_VARREDURA_CANCELAR = r")
        js = fonte[i:fonte.index("def _js_varredura_cancelar", i)]
        self.assertIn("if(!ALVO) return false;", js)

    def test_limpar_a_conta_inteira_continua_possivel_mas_PEDIDA(self):
        fonte = self._fonte()
        self.assertIn("if(ALVO === '*') return true;", fonte)
        self.assertIn("varrer_todos_os_ativos", fonte)

    def test_sem_ativo_e_sem_pedido_explicito_ele_RECUSA_o_clique(self):
        corpo = funcao_inteira(self._fonte(), "sair_em_mercado_e_cancelar")
        i = corpo.index("elif not varrer_todos_os_ativos:")
        trecho = corpo[i:i + 700]
        self.assertIn('r["recusa"] = True', trecho)
        self.assertIn("TODOS os", trecho)


class TestAConferenciaEDoCONTRATOEnaoDaConta(unittest.TestCase):

    def _fonte(self):
        return fonte_do_arquivo(os.path.join(RAIZ, "tradovate_auto.py"))

    def test_a_leitura_de_ordens_traz_o_ticker_de_cada_linha(self):
        fonte = self._fonte()
        i = fonte.index("_JS_ORDENS_VIVAS = r")
        js = fonte[i:i + 3500]
        self.assertIn("reTicker", js)
        self.assertIn("por_ativo:porAtivo", js)

    def test_existe_a_contagem_POR_ATIVO(self):
        corpo = funcao_inteira(self._fonte(), "_vivas_do_ativo")
        self.assertIn("por_ativo", corpo)
        # "Não sei" continua sendo diferente de "zero" — a lição de sempre.
        self.assertIn("return None", corpo)

    def test_quem_declara_sucesso_e_o_contrato_alvo(self):
        corpo = funcao_inteira(self._fonte(), "sair_em_mercado_e_cancelar")
        self.assertIn('restam = r["alvo_depois"]', corpo)
        self.assertIn('havia = r["alvo_antes"]', corpo)

    def test_o_estrago_nos_OUTROS_ativos_e_medido_e_dito(self):
        """Ele não pode descobrir pelo extrato da corretora que o robô
        derrubou uma ordem que ele não mandou derrubar."""
        corpo = funcao_inteira(self._fonte(), "sair_em_mercado_e_cancelar")
        self.assertIn('r["colateral"]', corpo)
        self.assertIn("de OUTROS", corpo)
        self.assertIn("CONFIRA", corpo)

    def test_o_titulo_NADA_A_CANCELAR_sai_de_bandeira_e_nao_de_substring(self):
        """O motivo agora traz o ticker no meio ('não havia ordem de MGCV6
        viva'), e a busca por 'não havia ordem viva' deixaria de casar. Um
        título de mensagem não pode depender de substring de prosa."""
        self.assertIn('r["nada_a_cancelar"] = True', self._fonte())
        self.assertIn('res.get("nada_a_cancelar")', fonte_do_arquivo())

    def test_estado_ilegivel_nao_vira_NameError(self):
        """`estado` era atribuído dentro do try e lido fora dele. Com
        `exigir_zerado=True`, uma exceção qualquer na leitura estourava um
        NameError cru no caminho que decide se aperta o botão que LIQUIDA A
        MERCADO."""
        corpo = funcao_inteira(self._fonte(), "sair_em_mercado_e_cancelar")
        i_init = corpo.index("estado = {}")
        i_try = corpo.index("estado = self.ler_estado()")
        self.assertLess(i_init, i_try)


class TestOrfasDeAtivosDiferentesVaoUMAAUMA(unittest.TestCase):

    def test_o_resolvedor_agrupa_por_contrato(self):
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_resolver_ordens_orfas_na_corretora")
        self.assertIn("por_ativo", corpo)
        self.assertIn("for ativo_alvo, lista in por_ativo.items():", corpo)
        self.assertIn("ativo=ativo_alvo or None", corpo)

    def test_a_leitura_de_posicao_olha_TODOS_os_contratos_envolvidos(self):
        """Perguntar só pelo primeiro da lista fazia a decisão de apertar um
        botão que liquida a mercado sair de uma leitura que não olhou os
        outros três."""
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_resolver_ordens_orfas_na_corretora")
        self.assertNotIn("posicao_aberta_no_ativo(orfas[0]", corpo)
        self.assertIn("any(bool(posicao_aberta_no_ativo(a))", corpo)

    def test_o_ativo_chega_ate_a_corretora(self):
        fonte = fonte_do_arquivo()
        corpo = funcao_inteira(fonte, "_tv_cancelar_na_plataforma")
        assinatura = corpo[:corpo.index('"""')]
        self.assertIn("ativo=None", assinatura)
        self.assertIn("varrer_todos_os_ativos=False", assinatura)
        self.assertIn("ativo=ativo", corpo)

    def test_limpar_o_desk_inteiro_so_nos_comandos_que_pedem_isso(self):
        """'Sair a mercado e cancelar TUDO' é botão de pânico e continua
        existindo. O que não pode é o pânico ser o padrão de quem esqueceu de
        dizer o ativo."""
        fonte = fonte_do_arquivo()
        for comando in ('"TODAS AS ORDENS PENDENTES"',
                        '"TODAS AS ORDENS E POSIÇÕES"'):
            i = fonte.index(comando)
            self.assertIn("varrer_todos_os_ativos=True", fonte[i:i + 300],
                          f"{comando} tem de pedir a limpeza geral por escrito")
        # Só as CHAMADAS (a docstring também cita a bandeira, e citar não é
        # apertar): chat (2) e WhatsApp (1), e mais ninguém.
        self.assertEqual(fonte.count("varrer_todos_os_ativos=True)"), 3)


# ======================================================================
#  14 CONTRATOS ENTRANDO EM CIMA DE 6
# ======================================================================
class TestACorretoraTemAUltimaPalavraAntesDeEnviar(unittest.TestCase):
    """31/08, MBTU6. Na tela dele havia ao mesmo tempo uma compra de 6 em
    78.800 e uma posição de 14 em 79.150. Ele: "as ordens estão encavalando,
    precisa estar muito atento a isso... isso é delicado".

    A trava contra empilhar existia e ESTAVA FUNCIONANDO — o log daquela tarde
    tem "⛔ Segurei o BUY MBTU6" várias vezes. O buraco é que ela pergunta ao
    DIÁRIO, e o que o diário não sabe, para ela, não existe: ordem mandada na
    mão, ordem de antes de o app abrir, reconciliação que não fechou.
    """

    def _ns(self):
        return carregar(["decidir_envio_contra_a_plataforma",
                         "exposicao_do_diario_no_ativo", "_mesmo_contrato"])

    def test_tela_limpa_libera(self):
        ns = self._ns()
        pode, _ = ns["decidir_envio_contra_a_plataforma"](
            "MBTU6", True, 0, 0, (0, 0))
        self.assertTrue(pode)

    def test_posicao_que_o_diario_NAO_conhece_barra(self):
        ns = self._ns()
        pode, motivo = ns["decidir_envio_contra_a_plataforma"](
            "MBTU6", True, 6, 0, (0, 0))
        self.assertFalse(pode)
        self.assertIn("MBTU6", motivo)
        self.assertIn("6 contrato", motivo)
        self.assertIn("NÃO estão no meu diário", motivo)

    def test_ordem_viva_que_o_diario_NAO_conhece_barra(self):
        ns = self._ns()
        pode, motivo = ns["decidir_envio_contra_a_plataforma"](
            "MBTU6", True, 0, 2, (0, 0))
        self.assertFalse(pode)
        self.assertIn("2 ordem", motivo)

    def test_posicao_vendida_conta_pelo_MODULO(self):
        """-14 é tanta exposição quanto +14."""
        ns = self._ns()
        pode, motivo = ns["decidir_envio_contra_a_plataforma"](
            "MBTU6", True, -14, 0, (0, 0))
        self.assertFalse(pode)
        self.assertIn("14 contrato", motivo)

    def test_o_que_o_DIARIO_JA_SABE_nao_e_revisto_aqui(self):
        """Quem decide o que fazer com exposição conhecida é a política de
        posição aberta, que roda antes: ou barra (ORDEM_VIVA), ou marca como
        AUMENTO, que ele acata na mão. Rever aquela decisão aqui tornaria o
        aumento manual impossível, e ele não pediu isso."""
        ns = self._ns()
        for exposicao in ((6, 0), (0, 1), (6, 1)):
            pode, _ = ns["decidir_envio_contra_a_plataforma"](
                "MBTU6", True, 6, 1, exposicao)
            self.assertTrue(pode, f"diário com {exposicao} tem de liberar")

    def test_NAO_CONSEGUI_LER_nao_e_permissao(self):
        """A mesma regra que `contar_ordens_vivas` escreve na própria
        docstring: 'zero ordens libera; não sei só permite avisar'. Do outro
        lado desta função sai uma ordem de verdade — então aqui avisar é
        recusar."""
        ns = self._ns()
        pode, motivo = ns["decidir_envio_contra_a_plataforma"](
            "MBTU6", False, 0, 0, (0, 0))
        self.assertFalse(pode)
        self.assertIn("não consegui LER", motivo)
        self.assertIn("painel de ordens", motivo,
                      "recusar sem dizer o que fazer vira ferramenta parada")

    def test_numero_torto_na_leitura_nao_derruba(self):
        ns = self._ns()
        for p, o in ((None, None), ("x", "y"), ("", ""), (0.0, 0.0)):
            pode, _ = ns["decidir_envio_contra_a_plataforma"](
                "MBTU6", True, p, o, (0, 0))
            self.assertTrue(pode)


class TestOQueODiarioTemNesseContrato(unittest.TestCase):

    def test_soma_aberta_e_conta_ordem_enviada(self):
        ns = carregar(["exposicao_do_diario_no_ativo", "_mesmo_contrato"])
        lista = [
            _pos(ativo="MBTU6", status="ABERTA", contratos=6),
            _pos(ativo="MBTU6", status="PENDENTE", enviada_plataforma=True),
            _pos(ativo="MESU6", status="ABERTA", contratos=99),   # outro ativo
        ]
        self.assertEqual(
            ns["exposicao_do_diario_no_ativo"](lista, "MBTU6"), (6, 1))

    def test_pendente_NAO_enviada_nao_ocupa_lugar_na_corretora(self):
        ns = carregar(["exposicao_do_diario_no_ativo", "_mesmo_contrato"])
        lista = [_pos(ativo="MBTU6", status="PENDENTE")]
        self.assertEqual(
            ns["exposicao_do_diario_no_ativo"](lista, "MBTU6"), (0, 0))

    def test_a_PROPRIA_ordem_que_esta_saindo_e_ignorada(self):
        """A armadilha que faria a trava inteira virar enfeite.

        `_marcar_ordem_na_corretora` carimba ANTES do envio, na thread da
        interface — e por um bom motivo (ver a docstring dela). Quando a
        conferência roda, a ordem que estamos mandando JÁ está no diário. Sem
        excluí-la, o diário "conhece" qualquer coisa que apareça na tela, a
        recusa nunca acontece, e um teste desatento passaria."""
        ns = carregar(["exposicao_do_diario_no_ativo", "_mesmo_contrato"])
        lista = [_pos(ativo="MBTU6", status="PENDENTE",
                      enviada_plataforma=True, sinal_id="s-agora")]
        self.assertEqual(
            ns["exposicao_do_diario_no_ativo"](lista, "MBTU6"), (0, 1))
        self.assertEqual(
            ns["exposicao_do_diario_no_ativo"](lista, "MBTU6",
                                               ignorar_sinal_id="s-agora"),
            (0, 0))

    def test_contrato_diferente_nao_se_mistura(self):
        ns = carregar(["exposicao_do_diario_no_ativo", "_mesmo_contrato"])
        lista = [_pos(ativo="MNQU6", status="ABERTA", contratos=5)]
        self.assertEqual(
            ns["exposicao_do_diario_no_ativo"](lista, "MESU6"), (0, 0))
        # MES e MESU6 são o mesmo instrumento.
        lista = [_pos(ativo="MES", status="ABERTA", contratos=5)]
        self.assertEqual(
            ns["exposicao_do_diario_no_ativo"](lista, "MESU6"), (5, 0))


class TestAConferenciaESTAlLIGADANoCaminhoDoEnvio(unittest.TestCase):
    """Função que existe e não é chamada não trava nada."""

    def test_ela_roda_ANTES_do_envio_do_bracket(self):
        corpo = funcao_inteira(fonte_do_arquivo(), "_tv_enviar_bracket")
        i_conf = corpo.index("_conferir_plataforma_antes_de_enviar(")
        i_envio = corpo.index("bot.enviar_ordem_com_atm(")
        self.assertLess(i_conf, i_envio)

    def test_recusar_DESFAZ_o_carimbo_da_ordem(self):
        """O carimbo é posto antes do envio. Se a ordem não sai, ele tem de
        cair — senão o diário passa a acreditar numa ordem que nunca existiu e
        a próxima sugestão do ativo é barrada por um fantasma."""
        corpo = funcao_inteira(fonte_do_arquivo(), "_tv_enviar_bracket")
        i = corpo.index("_conferir_plataforma_antes_de_enviar(")
        trecho = corpo[i:i + 900]
        self.assertIn("NÃO MANDEI A ORDEM", trecho)
        self.assertIn("_desmarcar_ordem_na_corretora", trecho)

    def test_em_modo_TESTE_nao_gasta_leitura(self):
        """Em dry-run nada sai, então não há o que conferir — e conferir
        gastaria dois CDP a cada ciclo à toa."""
        corpo = funcao_inteira(fonte_do_arquivo(), "_tv_enviar_bracket")
        i = corpo.index("_conferir_plataforma_antes_de_enviar(")
        self.assertIn("if not dry:", corpo[i - 500:i])

    def test_falha_de_leitura_vira_RECUSA_e_nunca_zero(self):
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_conferir_plataforma_antes_de_enviar")
        self.assertEqual(corpo.count("leitura_ok = False"), 4)
        self.assertIn("if do_ativo is None:", corpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
