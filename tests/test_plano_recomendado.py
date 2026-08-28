""""ME AJUDA A CONFIGURAR O PLANO DE TRADING PARA CHEGAR NA META"

O PEDIDO, E O QUE ELE RECEBEU
------------------------------
28/08, 09:12. Ele acabara de conseguir liberação maior de drawdown e pediu
ajuda para configurar o plano. A resposta foi um pedido de mais informação
seguido de seiscentos caracteres de lixo em outro idioma.

Mas o defeito não era a resposta. Era a pergunta ter ido para um MODELO DE
LINGUAGEM quando ela é ARITMÉTICA — e toda ela já estava medida dentro do
programa: meta e drawdown no plano, resultado no diário, ganho e perda médios
nas operações fechadas, ATR na fita, CVD no motor de fluxo.

É o mesmo defeito que `chance_de_bater_a_meta` consertou uma vez: lição vira
texto no prompt, não vira acesso ao diário.

OS NÚMEROS DESTE ARQUIVO SÃO OS DELE
-------------------------------------
Conta '50K BARBOSA', 28/08: margem US$2.000 · drawdown US$600 · meta US$3.000
em 1 dia · risco 30% · R:R mínimo 1:2 · acerto 50% · ganho médio US$80,62 ·
perda média US$157,50.

Três coisas saem dessa linha, e as três estão testadas aqui:

  1. Risco de 30% sobre US$2.000 são US$600 por operação, contra um drawdown
     de US$600. UM stop encerra o dia. O programa avisou e aceitou.

  2. O plano pedia 1:2 e a conta entregou 1:0,51. A ENTRADA fez o trabalho
     dela; quem não entregou foi a SAÍDA.

  3. Com 50% de acerto e perda média o dobro do ganho médio, a esperança por
     operação é −US$38,44. Nenhum ajuste de tamanho conserta isso.
"""

import os
import sys
import unittest

from harness import RAIZ

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import plano_recomendado as P          # noqa: E402


def _fonte(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


# A conta dele, 28/08, como estava configurada quando ele pediu ajuda.
DIA_28 = dict(
    margem=2000.0, drawdown=600.0, meta=3000.0,
    falta=3307.50, oportunidades=4,
    risco_pct=30.0, rr_minimo=2.0, probabilidade_minima=60.0,
    max_stops_seguidos=2,
    acerto=0.50, ganho_medio=80.62, perda_media=157.50, amostra=4,
    ticks_de_stop=16, valor_do_tick=1.25,
)


class TestAEsperancaMandaNaConversa(unittest.TestCase):

    def test_a_conta_dele_perde_dinheiro_por_operacao(self):
        """0,5 × 80,62 − 0,5 × 157,50 = −38,44. Este número é o assunto."""
        e = P.esperanca_por_operacao(0.50, 80.62, 157.50)
        self.assertAlmostEqual(e, -38.44, places=2)

    def test_esperanca_positiva_quando_o_ganho_paga_a_perda(self):
        e = P.esperanca_por_operacao(0.50, 200.0, 100.0)
        self.assertAlmostEqual(e, 50.0, places=6)

    def test_sem_numero_devolve_None_e_nao_zero(self):
        """Zero afirmaria que empata. None diz que não se sabe — e é a
        diferença entre não ter medida e ter medido empate."""
        self.assertIsNone(P.esperanca_por_operacao(None, 100, 50))
        self.assertIsNone(P.esperanca_por_operacao(0.5, None, 50))

    def test_acerto_fora_de_0_a_1_e_recusado(self):
        """50 em vez de 0,50 é o erro de digitação que viraria uma esperança
        cinquenta vezes maior."""
        self.assertIsNone(P.esperanca_por_operacao(50, 100, 50))


class TestOPlanoPedeUmRREAContaEntregaOutro(unittest.TestCase):

    def test_o_rr_realizado_da_conta_dele(self):
        """80,62 ÷ 157,50 = 0,51. O plano pedia 2,0."""
        self.assertAlmostEqual(P.rr_realizado(80.62, 157.50), 0.512, places=3)

    def test_o_achado_acusa_a_SAIDA_e_nao_o_filtro_de_entrada(self):
        """É a diferença entre consertar o problema e apertar o parafuso
        errado: com R:R realizado muito abaixo do planejado, subir o R:R
        mínimo só recusa mais cenários bons."""
        rec = P.recomendar_plano(**DIA_28)
        texto = " ".join(rec["achados"])
        self.assertIn("SAÍDA", texto)
        self.assertIn("1:0.51", texto.replace(",", "."))

    def test_o_achado_diz_explicitamente_que_apertar_o_filtro_nao_resolve(self):
        rec = P.recomendar_plano(**DIA_28)
        texto = " ".join(rec["achados"]).lower()
        self.assertIn("não conserta", texto)

    def test_rr_realizado_igual_ao_planejado_nao_gera_achado(self):
        bom = dict(DIA_28, ganho_medio=200.0, perda_media=100.0)
        rec = P.recomendar_plano(**bom)
        self.assertNotIn("SAÍDA", " ".join(rec["achados"]))


class TestQuemMandaNoRiscoEODrawdown(unittest.TestCase):

    def test_o_caso_dele_UM_stop_encerra_o_dia(self):
        self.assertAlmostEqual(P.stops_que_cabem(600.0, 600.0), 1.0)

    def test_o_achado_chama_isso_de_plano_de_uma_tentativa(self):
        rec = P.recomendar_plano(**DIA_28)
        texto = " ".join(rec["achados"]).lower()
        self.assertIn("uma tentativa", texto)

    def test_o_ajuste_devolve_o_risco_que_faz_caberem_tres_stops(self):
        """US$600 ÷ 3 = US$200 por operação = 10% de uma margem de US$2.000."""
        rec = P.recomendar_plano(**DIA_28)
        risco = [a for a in rec["ajustes"] if a["campo"] == "risco_pct"]
        self.assertEqual(len(risco), 1)
        self.assertAlmostEqual(risco[0]["para"], 10.0, places=2)
        self.assertEqual(risco[0]["de"], 30.0)

    def test_o_ajuste_traz_a_conta_que_o_gerou(self):
        """Número sem a conta ao lado é ordem, e ordem ele não tem por que
        obedecer."""
        rec = P.recomendar_plano(**DIA_28)
        risco = [a for a in rec["ajustes"] if a["campo"] == "risco_pct"][0]
        self.assertIn("600", risco["porque"])
        self.assertIn("stops", risco["porque"].lower())

    def test_risco_saudavel_NAO_vira_ajuste(self):
        """A ferramenta não pode ficar sugerindo mudança onde não há defeito —
        é assim que se ensina alguém a ignorar sugestão."""
        ok = dict(DIA_28, risco_pct=10.0)
        rec = P.recomendar_plano(**ok)
        self.assertEqual(
            [a for a in rec["ajustes"] if a["campo"] == "risco_pct"], [])

    def test_o_drawdown_QUE_RESTA_manda_sobre_o_drawdown_cheio(self):
        """Depois de perder metade do dia, o teto não pode continuar sendo o
        número do começo da manhã."""
        rec = P.recomendar_plano(**dict(DIA_28, drawdown_restante=150.0))
        self.assertEqual(rec["contas"]["drawdown_considerado"], 150.0)
        self.assertAlmostEqual(rec["contas"]["risco_permitido_usd"], 50.0)


class TestAMetaEConsequenciaDoRiscoENaoOContrario(unittest.TestCase):

    def test_a_meta_dele_nao_cabe_e_o_programa_DIZ_isso(self):
        """US$3.307,50 em 4 operações a R:R 1:2 pediriam US$413,44 de risco
        por operação, acertando TODAS. O drawdown paga US$200."""
        rec = P.recomendar_plano(**DIA_28)
        self.assertAlmostEqual(
            rec["contas"]["risco_exigido_pela_meta_usd"], 413.4375, places=3)
        self.assertIn("NÃO CABE NESTE DRAWDOWN", " ".join(rec["achados"]))

    def test_ele_diz_QUAL_meta_cabe_em_vez_de_so_recusar(self):
        """Recusar sem oferecer o número que serve deixa a pessoa no mesmo
        lugar em que ela estava."""
        rec = P.recomendar_plano(**DIA_28)
        self.assertIn("meta_que_cabe_usd", rec["contas"])

    def test_meta_que_cabe_usa_a_ESPERANCA_quando_a_amostra_permite(self):
        """Com amostra suficiente, o número realista é esperança × operações —
        não o sonho de acertar todas."""
        cabe = P.meta_que_cabe(200.0, 4, 2.0, esperanca=-38.44)
        self.assertAlmostEqual(cabe, -153.76, places=2)

    def test_sem_esperanca_medida_usa_o_teto_otimista(self):
        cabe = P.meta_que_cabe(200.0, 4, 2.0, esperanca=None)
        self.assertAlmostEqual(cabe, 1600.0)

    def test_meta_que_cabe_no_drawdown_nao_vira_achado(self):
        modesta = dict(DIA_28, falta=300.0, risco_pct=10.0)
        rec = P.recomendar_plano(**modesta)
        self.assertNotIn("NÃO CABE", " ".join(rec["achados"]))


class TestOPisoDeQualidadeSaiDoAcertoDELE(unittest.TestCase):

    def test_com_50_por_cento_o_empate_e_1_para_1(self):
        self.assertAlmostEqual(P.rr_para_ficar_no_azul(0.50, folga=1.0), 1.0)

    def test_com_40_por_cento_o_empate_sobe_para_1_para_1_5(self):
        self.assertAlmostEqual(P.rr_para_ficar_no_azul(0.40, folga=1.0), 1.5)

    def test_o_caminho_inverso_fecha(self):
        """Se R:R 1:2 empata em 33,3% de acerto, então 33,3% de acerto pede
        R:R 1:2. Uma conta que não fecha nos dois sentidos está errada em um
        deles."""
        self.assertAlmostEqual(P.acerto_para_o_rr(2.0, folga=1.0), 1 / 3.0,
                               places=6)
        self.assertAlmostEqual(
            P.rr_para_ficar_no_azul(1 / 3.0, folga=1.0), 2.0, places=6)

    def test_acerto_zero_nao_divide_por_zero(self):
        self.assertIsNone(P.rr_para_ficar_no_azul(0.0))

    def test_probabilidade_minima_sobe_quando_esta_abaixo_do_empate(self):
        frouxo = dict(DIA_28, rr_minimo=1.0, probabilidade_minima=40.0)
        rec = P.recomendar_plano(**frouxo)
        prob = [a for a in rec["ajustes"]
                if a["campo"] == "probabilidade_minima"]
        self.assertEqual(len(prob), 1)
        self.assertGreater(prob[0]["para"], 40)


class TestOsAjustesNaoPodemSeContradizer(unittest.TestCase):
    """DEFEITO ENCONTRADO AO LER A PRIMEIRA SAÍDA DE VERDADE.

    Com o risco em 30%, a lista dizia na MESMA tela: 'baixe o risco para 10%'
    E 'baixe o freio de 2 stops seguidos para 1'. O segundo só fazia sentido
    se o primeiro fosse ignorado — a 10% cabem três stops e o freio de 2 está
    certo do jeito que está. Uma recomendação que se contradiz na própria
    lista é uma recomendação que ninguém segue."""

    def test_o_freio_e_medido_DEPOIS_do_ajuste_de_risco(self):
        rec = P.recomendar_plano(**DIA_28)
        campos = [a["campo"] for a in rec["ajustes"]]
        self.assertIn("risco_pct", campos)
        self.assertNotIn("max_stops_seguidos", campos)

    def test_quando_nem_o_risco_ajustado_paga_o_freio_ele_aparece(self):
        """Drawdown minúsculo: mesmo com o risco no que cabe, o freio de 4
        stops continua sendo teatro."""
        apertado = dict(DIA_28, drawdown=60.0, max_stops_seguidos=4)
        rec = P.recomendar_plano(**apertado)
        freio = [a for a in rec["ajustes"]
                 if a["campo"] == "max_stops_seguidos"]
        self.assertEqual(len(freio), 1)
        self.assertIn("nunca chegaria a disparar", freio[0]["porque"])

    def test_freio_coerente_com_o_drawdown_fica_quieto(self):
        ok = dict(DIA_28, risco_pct=10.0)
        rec = P.recomendar_plano(**ok)
        self.assertEqual(
            [a for a in rec["ajustes"] if a["campo"] == "max_stops_seguidos"],
            [])


class TestOTetoNaoPodeSerLidoComoIncentivo(unittest.TestCase):
    """SEGUNDO DEFEITO DA MESMA LEITURA. Logo depois de 'cada operação está
    perdendo dinheiro', a recomendação dizia 'o que cabe no prazo é
    US$ 1.600,00' — o caso de acertar TODAS, sem dizer que era isso. Lido em
    sequência, virava incentivo."""

    def test_o_teto_e_chamado_de_teto_com_essas_palavras(self):
        rec = P.recomendar_plano(**DIA_28)
        texto = " ".join(rec["achados"])
        self.assertIn("O TETO no prazo", texto)
        self.assertIn("acertando todas", texto)

    def test_a_projecao_REALISTA_sai_junto_e_e_negativa(self):
        rec = P.recomendar_plano(**DIA_28)
        self.assertAlmostEqual(rec["contas"]["meta_projetada_usd"],
                               -153.76, places=2)
        self.assertIn("não a expectativa", " ".join(rec["achados"]))

    def test_com_esperanca_positiva_a_projecao_sai_sem_o_contraste(self):
        bom = dict(DIA_28, ganho_medio=250.0, perda_media=100.0, amostra=30)
        rec = P.recomendar_plano(**bom)
        texto = " ".join(rec["achados"])
        self.assertIn("Com o seu desempenho medido", texto)
        self.assertNotIn("não a expectativa", texto)


class TestOMomentoDoMercadoEntraNaConta(unittest.TestCase):

    def test_stop_menor_que_o_ATR_e_acusado(self):
        """'stop de 10 tick(s) é curto demais' já aparecia no log dele, mas
        contra uma faixa FIXA por contrato. Aqui é contra a volatilidade
        medida na fita de agora."""
        m = P.leitura_do_momento(atr_ticks=24.0, ticks_de_stop=12)
        self.assertTrue(m["stop_curto_para_a_volatilidade"])
        self.assertEqual(m["stop_confortavel_pelo_atr"], 36)

    def test_stop_folgado_nao_e_acusado(self):
        m = P.leitura_do_momento(atr_ticks=12.0, ticks_de_stop=20)
        self.assertNotIn("stop_curto_para_a_volatilidade", m)

    def test_fita_sem_leitura_e_DITA_e_nao_virada_em_zero(self):
        """'qual o delta?' às 08:51 — a resposta certa é que não há leitura,
        nunca um delta de conveniência."""
        m = P.leitura_do_momento(cvd=None, negocios_na_fita=0)
        self.assertEqual(m["fita"], "sem leitura")
        self.assertNotIn("cvd", m)

    def test_cvd_lido_traz_o_lado_da_agressao(self):
        m = P.leitura_do_momento(cvd=15475, negocios_na_fita=420)
        self.assertEqual(m["lado_da_agressao"], "comprador")
        self.assertEqual(m["negocios"], 420)

    def test_cvd_negativo_e_vendedor(self):
        self.assertEqual(
            P.leitura_do_momento(cvd=-900, negocios_na_fita=50)["lado_da_agressao"],
            "vendedor")

    def test_a_recomendacao_avisa_quando_a_fita_esta_muda(self):
        rec = P.recomendar_plano(**DIA_28)
        self.assertIn("FITA NÃO ESTÁ SENDO LIDA", " ".join(rec["achados"]))

    def test_com_fita_lendo_o_aviso_some(self):
        rec = P.recomendar_plano(**dict(DIA_28, cvd=15475,
                                        negocios_na_fita=420))
        self.assertNotIn("FITA NÃO ESTÁ SENDO LIDA", " ".join(rec["achados"]))


class TestTamanhoDePosicao(unittest.TestCase):

    def test_contratos_arredondam_para_BAIXO(self):
        """US$200 ÷ (16 ticks × US$1,25) = 10,0. Com US$210, dá 10,5 — e 10 é
        o único número que não estoura o risco."""
        self.assertEqual(P.contratos_que_cabem(200.0, 16, 1.25), 10)
        self.assertEqual(P.contratos_que_cabem(210.0, 16, 1.25), 10)

    def test_quando_nao_cabe_nem_um_contrato_o_programa_DIZ(self):
        aperto = dict(DIA_28, drawdown_restante=20.0, ticks_de_stop=40)
        rec = P.recomendar_plano(**aperto)
        self.assertEqual(rec["contas"]["contratos_recomendados"], 0)
        self.assertIn("NÃO CABE NEM UM CONTRATO", " ".join(rec["achados"]))

    def test_stop_zero_nao_divide_por_zero(self):
        self.assertIsNone(P.contratos_que_cabem(200.0, 0, 1.25))


class TestOVeredito(unittest.TestCase):

    def test_com_esperanca_negativa_o_veredito_MUDA_DE_ASSUNTO(self):
        """Ele pediu como configurar para ganhar mais. Com cada operação
        valendo menos que zero, responder sobre tamanho seria responder a
        pergunta errada com precisão."""
        rec = P.recomendar_plano(**DIA_28)
        self.assertIn("saída", rec["veredito"].lower())
        self.assertIn("antes de configurar", rec["veredito"].lower())

    def test_plano_saudavel_recebe_um_veredito_de_nada_a_fazer(self):
        bom = dict(DIA_28, risco_pct=10.0, falta=300.0, ganho_medio=200.0,
                   perda_media=100.0, amostra=30, cvd=500,
                   negocios_na_fita=90, atr_ticks=12.0, ticks_de_stop=20)
        rec = P.recomendar_plano(**bom)
        self.assertEqual(rec["ajustes"], [])
        self.assertIn("nada a ajustar", rec["veredito"].lower())

    def test_amostra_pequena_e_declarada_antes_de_tudo(self):
        """Quatro operações não são uma taxa de acerto. Dizer isso é o que
        separa indício de estatística."""
        rec = P.recomendar_plano(**DIA_28)
        self.assertIn("AMOSTRA PEQUENA", rec["achados"][0])


class TestNadaAquiLevantaComEntradaRuim(unittest.TestCase):
    """Esta função roda no meio do pregão, chamada pelo chat. Uma exceção
    aqui é a mesa sem resposta."""

    def test_plano_vazio_nao_levanta(self):
        rec = P.recomendar_plano()
        self.assertIsInstance(rec["achados"], list)
        self.assertIsInstance(rec["ajustes"], list)
        self.assertTrue(rec["veredito"])

    def test_texto_de_None_nao_levanta(self):
        self.assertIn("faltam números", P.texto_da_recomendacao(None))

    def test_strings_no_lugar_de_numeros_nao_levantam(self):
        rec = P.recomendar_plano(margem="dois mil", drawdown="", meta=None,
                                 risco_pct="trinta")
        self.assertTrue(rec["veredito"])

    def test_o_texto_sai_legivel_com_a_conta_dele(self):
        txt = P.texto_da_recomendacao(P.recomendar_plano(**DIA_28))
        self.assertIn("risco_pct", txt)
        self.assertIn("30 → 10", txt)


class TestOModuloEPuro(unittest.TestCase):
    """Sem disco, sem rede, sem relógio — para o teste prender a regra e não
    o ambiente, e para a mesma conta dar o mesmo número amanhã."""

    def test_nao_importa_nada_de_fora_da_biblioteca_padrao(self):
        fonte = _fonte("plano_recomendado.py")
        for proibido in ("import requests", "import os", "open(",
                         "datetime", "import main_app", "import time"):
            self.assertNotIn(proibido, fonte, proibido)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestAPerguntaCHEGAAoCodigoQueSabeResponder(unittest.TestCase):
    """13/08 a conta da meta existia e a pergunta não chegava nela. 28/08 foi
    a mesma coisa com a configuração do plano — e o roteamento é a metade do
    conserto que não aparece no cálculo."""

    def setUp(self):
        from test_conversa import _ns_intencao
        from harness import carregar
        self.ns = _ns_intencao()
        # A função pura entra à parte: o roteador usa a CONSTANTE
        # (`_RE_CONFIGURAR_PLANO`), que o harness traz sozinho, e esta é a
        # mesma regra exposta para quem quiser perguntar direto.
        self.ns["pergunta_como_configurar"] = carregar(
            ["_sem_acento", "_RE_CONFIGURAR_PLANO",
             "pergunta_como_configurar"])["pergunta_como_configurar"]

    def _intencao(self, txt):
        return self.ns["interpretar_intencao"](txt)

    def test_a_frase_EXATA_de_28_08_vira_CONFIGURAR_PLANO(self):
        self.assertEqual(
            self._intencao("ACABEI DE CONSEGUIR LIBERACAO MAIOR DE DROWDROW, "
                           "ME AJUDA A CONFIGURAR O PLANO DE TRADING PARA "
                           "CONSEGUIR CHEGAR NA META POR FAVOR"),
            "CONFIGURAR_PLANO")

    def test_o_que_recomenda_colocar_como_risco_NAO_cai_mais_na_meta(self):
        """Tem a palavra 'meta' e 'bater' — cairia na conta da meta, que
        responde SE dá, não COMO configurar."""
        self.assertEqual(
            self._intencao("O QUE RECOMENDA COLOCAR COMO RISCO PARA BATER A "
                           "META HOJE?"),
            "CONFIGURAR_PLANO")

    def test_o_erro_de_digitacao_dele_tambem_casa(self):
        """'RECOMANDA' — quem está no meio do pregão digita torto."""
        self.assertEqual(
            self._intencao("O QUE RECOMANDA PARA CHEGAR NA META HOJE?"),
            "CONFIGURAR_PLANO")

    def test_a_pergunta_de_PROBABILIDADE_continua_indo_para_a_meta(self):
        """Consertar uma pergunta não pode roubar a outra."""
        self.assertEqual(
            self._intencao("como estamos de probabilidade de bater a meta de "
                           "hoje até as 17:59?"),
            "META")

    def test_pergunta_de_opiniao_sobre_o_plano_segue_para_a_IA(self):
        """'você acha que tenho chance de perder a conta?' é conversa, não
        configuração — e a IA recebe estes mesmos números no contexto."""
        self.assertIsNone(
            self._intencao("DA UMA OLHADA NO MEU PLANO DE TRADING, VOCE ACHA "
                           "QUE TENHO CHANCE DE PERDER A CONTA?"))

    def test_a_funcao_pura_concorda_com_o_roteador(self):
        f = self.ns["pergunta_como_configurar"]
        self.assertTrue(f("como configuro o plano de trading"))
        self.assertTrue(f("qual a melhor forma de ajustar o drawdown"))
        self.assertFalse(f("qual o delta?"))
        self.assertFalse(f(""))
        self.assertFalse(f(None))
