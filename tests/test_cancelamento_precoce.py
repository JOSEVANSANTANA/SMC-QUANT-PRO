"""23/08: MANDA E CANCELA, MANDA E CANCELA. QUASE NENHUMA EXECUÇÃO NO MEIO.

O log de um pregão inteiro é uma sequência de ORDEM ENVIADA seguida de ORDENS
CANCELADAS poucos minutos depois. Duas causas independentes, ambas com número.

CAUSA 1 — O PRAZO ESTAVA EM CICLOS, E O NOME MENTIA
----------------------------------------------------
A regra era `sinal_ativo["candles"] >= MAX_CANDLES` com MAX_CANDLES = 6. Só
que `candles` sobe uma vez por CICLO DE ANÁLISE — não por candle do gráfico.
O intervalo do ciclo é configurável, então a paciência de toda ordem pendente
andava junto, em silêncio:

    ciclo de 15 min -> 90 minutos
    ciclo de  3 min -> 18 minutos
    ciclo de  1 min ->  6 MINUTOS

Às 15:42 ele baixou o intervalo para 1 min. Às 15:52 saiu SELL 8 ctr @ 7553,5.
Às 15:58 veio "preço não voltou à zona de entrada". Seis minutos. Uma ordem
limitada de MES em 5m não tem o que provar em seis minutos — o cenário não
morreu, o cronômetro é que era o do ciclo.

CAUSA 2 — A PORTA DE DESTRUIR ERA MAIS LARGA QUE A DE CONSTRUIR
----------------------------------------------------------------
16:01, o mesmo ciclo, duas linhas:

    🔄 CENÁRIO MUDOU: a sugestão SELL MESU6 @ 7555.5 foi INVALIDADA
       (surgiu um setup de BUY com qualidade). 13 ordem(ns) cancelada(s).
    ↔️ BUY MESU6: o cenário inverteu de lado nos últimos 30 min e a
       probabilidade (72%) não chega aos 80% que eu exijo para virar a mão.

O MESMO BUY de 72% foi bom o bastante para derrubar treze contratos e ruim
demais para entrar. O robô ficou sem os dois: pagou o preço da virada sem
fazer a virada.

Quem derrubava usava o piso de qualidade (70%). Quem entrava, na virada de
lado, exige piso + margem anti-chicote (80%). Duas réguas para a mesma
decisão, e a destrutiva era a frouxa.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _ns():
    return carregar(["janela_de_mitigacao_min", "pode_derrubar_cenario_por_virada",
                     "_mitigacao_vencida", "PISO_MITIGACAO_MIN",
                     "CICLOS_DE_MITIGACAO"])


class TestOPrazoDaOrdemNaoEncolheComOCiclo(unittest.TestCase):
    """`janela_de_mitigacao_min`: o intervalo de análise e a paciência da
    ordem são coisas sem relação. Amarrar uma na outra foi o defeito."""

    def setUp(self):
        self.f = _ns()["janela_de_mitigacao_min"]

    def test_o_caso_REAL_das_1552_nao_se_repete(self):
        """Ciclo de 1 min dava 6 minutos de vida à ordem. Agora dá 30."""
        self.assertEqual(self.f(1, 60), 30)

    def test_ciclo_de_3_minutos_tambem_sobe_para_o_piso(self):
        self.assertEqual(self.f(3, 60), 30)

    def test_o_prazo_do_PLANO_e_o_teto(self):
        """Nada do robô sobrevive ao 'Prazo p/ acatar' que ele configurou:
        6 ciclos de 15 min dariam 90, mas o plano dele diz 60."""
        self.assertEqual(self.f(15, 60), 60)

    def test_e_o_teto_vale_mesmo_abaixo_do_piso(self):
        """Se ele configurou 10 min de prazo, 10 é o que vale — o piso não
        pode passar por cima de uma escolha explícita dele."""
        self.assertEqual(self.f(15, 10), 10)

    def test_sem_prazo_configurado_nao_inventa_teto(self):
        self.assertEqual(self.f(15, None), 90)
        self.assertEqual(self.f(15, 0), 90)

    def test_intervalo_bobo_nao_derruba_a_conta(self):
        for ruim in (None, "", "abc", -5):
            self.assertEqual(self.f(ruim, 60), 30, repr(ruim))

    def test_o_piso_e_o_numero_de_ciclos_estao_declarados(self):
        ns = _ns()
        self.assertEqual(ns["PISO_MITIGACAO_MIN"], 30)
        self.assertEqual(ns["CICLOS_DE_MITIGACAO"], 6)


class TestOPrazoEMedidoNoRELOGIO(unittest.TestCase):
    """Contar ciclos era o erro. `_mitigacao_vencida` conta minutos."""

    def setUp(self):
        self.f = _ns()["_mitigacao_vencida"]

    def test_vencido_quando_o_tempo_passou(self):
        self.assertTrue(self.f({"ts_criacao": 1000.0}, 30, agora=1000.0 + 30 * 60))

    def test_nao_vencido_um_minuto_antes(self):
        self.assertFalse(self.f({"ts_criacao": 1000.0}, 30, agora=1000.0 + 29 * 60))

    def test_usa_o_ts_criacao_que_o_sinal_JA_tinha(self):
        """Nenhum campo novo foi inventado para isto."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _mitigacao_vencida")
        self.assertIn('get("ts_criacao")', fonte[i:i + 900])
        j = fonte.index('"ts_criacao": time.time()')
        self.assertGreater(j, 0)

    def test_sinal_sem_carimbo_NAO_e_expirado(self):
        """Sinal de uma versão anterior não tem data. Expirar o que não dá
        para datar seria cancelar no escuro."""
        self.assertFalse(self.f({}, 30))
        self.assertFalse(self.f({"ts_criacao": None}, 30))
        self.assertFalse(self.f(None, 30))

    def test_a_contagem_de_ciclos_saiu_do_caminho_do_cancelamento(self):
        fonte = fonte_do_arquivo()
        self.assertNotIn('sinal_ativo["candles"] >= MAX_CANDLES', fonte)
        self.assertIn("_mitigacao_vencida(sinal_ativo, MINUTOS_MITIGACAO)", fonte)

    def test_a_janela_e_calculada_a_partir_do_plano_no_ciclo(self):
        """Função que existe e não é chamada é o `self.order_flow` de novo."""
        fonte = fonte_do_arquivo()
        i = fonte.index("MINUTOS_MITIGACAO = janela_de_mitigacao_min(")
        trecho = fonte[i:i + 200]
        self.assertIn("INTERVALO_MINUTOS", trecho)
        self.assertIn("_timeout_min", trecho)


class TestSoDerrubaUmCenarioPorOutroQueEuTOMARIA(unittest.TestCase):
    """`pode_derrubar_cenario_por_virada` — a régua única."""

    def setUp(self):
        self.f = _ns()["pode_derrubar_cenario_por_virada"]

    def test_o_BUY_de_72_das_1601_NAO_derruba_os_13_contratos(self):
        """O caso exato. 72% passa no piso (70) e não passa na virada (80)."""
        self.assertFalse(self.f(72, 70, 10))

    def test_com_conviccao_de_virada_ele_derruba(self):
        self.assertTrue(self.f(80, 70, 10))
        self.assertTrue(self.f(85, 70, 10))

    def test_a_regua_e_EXATAMENTE_a_da_trava_de_chicote(self):
        """Se as duas divergirem de novo, volta o buraco: derruba e não entra.
        Aqui a soma é a mesma expressão dos dois lados."""
        fonte = fonte_do_arquivo()
        i = fonte.index("if chicote and probabilidade <")
        trava = fonte[i:i + 160]
        self.assertIn("PROBABILIDADE_MINIMA + MARGEM_ANTI_CHICOTE", trava)
        j = fonte.index("pode_derrubar_cenario_por_virada(\n")
        derruba = fonte[j:j + 200]
        self.assertIn("PROBABILIDADE_MINIMA", derruba)
        self.assertIn("MARGEM_ANTI_CHICOTE", derruba)

    def test_numero_bobo_nao_derruba_nada(self):
        """Na dúvida, não destrói o que está de pé."""
        for ruim in (None, "", "abc"):
            self.assertFalse(self.f(ruim, 70, 10), repr(ruim))

    def test_esta_LIGADA_na_invalidacao_por_mudanca_de_cenario(self):
        fonte = fonte_do_arquivo()
        i = fonte.index('acao != sinal_ativo.get("direcao")')
        trecho = fonte[i:i + 400]
        self.assertIn("pode_derrubar_cenario_por_virada(", trecho)


class TestNadaACancelarNaoSeChamaCancelado(unittest.TestCase):
    """'✅ ORDENS CANCELADAS NA PLATAFORMA … não havia ordem viva na
    plataforma para cancelar'. O corpo dizia a verdade; o TÍTULO dizia o
    contrário — e é o título que vai para o WhatsApp."""

    def _bloco(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("NADA A CANCELAR NA PLATAFORMA")
        return fonte[i - 900:i + 400]

    def test_o_titulo_muda_quando_nao_havia_o_que_cancelar(self):
        bloco = self._bloco()
        self.assertIn("não havia ordem viva", bloco)
        self.assertIn("NADA A CANCELAR NA PLATAFORMA", bloco)

    def test_e_continua_dizendo_CANCELADAS_quando_cancelou_mesmo(self):
        self.assertIn("ORDENS CANCELADAS NA PLATAFORMA", self._bloco())

    def test_aguenta_texto_sem_acento(self):
        """O motivo vem da automação e nem sempre passa acentuado."""
        bloco = self._bloco()
        self.assertIn("nao havia ordem viva", bloco)


class TestOBotaoAtualizarDoCiclo(unittest.TestCase):
    """Pedido dele: 'considere incluir um botão atualizar ali no ciclo'."""

    def _corpo(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _atualizar_ciclo_agora")
        return fonte[i:i + 2000]

    def test_o_botao_existe_e_chama_a_funcao(self):
        # Ancorado no texto EXATO: já existe um "🔄 Atualizar lista de
        # janelas abertas" noutra aba, e casar com ele testaria o botão errado.
        fonte = fonte_do_arquivo()
        alvo = 'text="🔄 Atualizar", width='
        self.assertIn(alvo, fonte)
        i = fonte.index(alvo)
        self.assertIn("_atualizar_ciclo_agora", fonte[i:i + 300])

    def test_ele_rele_o_EXTRATO_e_nao_so_redesenha(self):
        """Redesenhar o mesmo número não é atualizar — é repintar."""
        self.assertIn("_reconciliar_pelo_extrato()", self._corpo())

    def test_sem_CDP_ele_diz_que_NAO_releu(self):
        """Chamar de 'atualizado' um painel que não falou com a corretora é
        o conforto falso que faz confiar numa tela velha."""
        corpo = self._corpo()
        self.assertIn("sem conexão com a Tradovate", corpo)
        self.assertIn("NÃO reli o extrato", corpo)

    def test_invalida_as_assinaturas_senao_o_redesenho_e_descartado(self):
        corpo = self._corpo()
        self.assertIn("_assin_posicoes = None", corpo)
        self.assertIn("_assin_dashboard = None", corpo)
        self.assertIn("forcar=True", corpo)

    def test_diz_o_que_encontrou_nos_dois_casos(self):
        corpo = self._corpo()
        self.assertIn("não havia nada", corpo)
        self.assertIn("registro(s)", corpo)


class TestOFiltroDeTendenciaNAOEstaLigado(unittest.TestCase):
    """A pergunta dele: 'o algoritmo usa a regressão para identificar viés
    macro antes de procurar Order Blocks nos tempos menores?'

    A resposta honesta é NÃO, e este teste existe para que ela continue
    verdadeira até alguém ligar de fato — e falhe no dia em que ligarem sem
    alimentar, que é o defeito do `self.order_flow` de novo.

    `MarketRegimeClassifier` é atribuído a `self.regime_classifier` e nunca
    é chamado em lugar nenhum. O 'Regime de Mercado: Expansão de Tendência
    (Bullish)' que aparece na telemetria não vem dele: vem de reescrever a
    palavra BUY/SELL da última leitura da IA."""

    def test_o_classificador_de_regime_continua_sem_ser_chamado(self):
        fonte = fonte_do_arquivo()
        self.assertIn("self.regime_classifier = MarketRegimeClassifier", fonte)
        self.assertEqual(fonte.count("regime_classifier.classificar("), 0,
                         "alguém ligou o classificador: troque este teste por "
                         "um que prove que ele recebe CANDLES de verdade, e "
                         "não uma lista vazia")

    def test_o_regime_do_painel_vem_da_acao_da_IA_e_isso_esta_explicito(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("regime_txt = \"Expansão Bullish (Alta)\"")
        trecho = fonte[max(0, i - 300):i + 100]
        self.assertIn("acao", trecho)


if __name__ == "__main__":
    unittest.main(verbosity=2)
