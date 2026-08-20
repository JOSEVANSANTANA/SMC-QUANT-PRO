"""O TRAIL QUE PROTEGE LUCRO ABERTO — a regra da mesa, em código.

20/08, ele descreveu o problema melhor do que qualquer manual:

    "na mesa não posso tomar drawdown, se não, quebro a regra e posso perder a
     conta do mesmo jeito. (no caso, LUCROS NÃO REALIZADOS se por acaso voltar
     eu tomo drawdown)"

Numa conta de mesa o drawdown costuma ser medido contra o TOPO da conta,
incluindo lucro aberto. Um trade que sobe US$1.500 e volta ao zero não é
"trade neutro": são US$1.500 de drawdown consumidos, e podem quebrar a regra
num dia que fechou no positivo. Stop fixo não protege disso, porque ele nunca
sobe.

O TRAIL ANTIGO era um número só, igual para todo cenário: arma em 1R, segue a
1R. Ele erra dos dois lados — num alvo curto arma tarde demais (deixa devolver
quase tudo) e num alvo largo aperta cedo demais (sai no ruído antes do
movimento que ele veio pegar).

O novo responde três perguntas, e a terceira manda nas outras duas:
  1. QUANDO armar   -> do R:R do cenário
  2. A QUE distância -> do R:R, ajustado pela probabilidade
  3. O TETO DA MESA  -> quanto pode ser devolvido sem virar drawdown
"""

import os
import sys
import unittest

from harness import RAIZ, fonte_do_arquivo

sys.path.insert(0, RAIZ)
import tradovate_auto as tv  # noqa: E402


# MESU6: tick 0,25 e US$5 por ponto -> US$1,25 por tick.
VT = 1.25


class TestQuandoArmarEAQueDistancia(unittest.TestCase):

    def test_alvo_CURTO_protege_ja_em_1R(self):
        """R:R 2 não tem muito a ganhar esperando: deixar voltar de 1R para
        zero desperdiça a maior parte do que o trade ia pagar."""
        p = tv.plano_trailing_inteligente(32, rr=2.0, contratos=1,
                                          valor_do_tick=VT,
                                          drawdown_restante=10000)
        self.assertEqual(p["acionar"], 32)
        self.assertEqual(p["stop"], 32)
        self.assertIn("curto", p["motivo"])

    def test_alvo_LARGO_deixa_respirar_ate_1_5R(self):
        """Arrastar cedo um trade de 3R é a forma clássica de ser stopado no
        ruído antes do movimento que ele veio pegar."""
        p = tv.plano_trailing_inteligente(32, rr=3.5, probabilidade=80,
                                          contratos=1, valor_do_tick=VT,
                                          drawdown_restante=10000)
        self.assertEqual(p["acionar"], 48)      # 1,5 x 32
        self.assertEqual(p["stop"], 40)         # 1,25 x 32
        self.assertIn("largo", p["motivo"])

    def test_probabilidade_baixa_so_APERTA_nunca_afrouxa(self):
        """Afrouxar por causa da probabilidade seria deixar o otimismo do
        modelo mexer no risco. Ela só encurta a corda."""
        largo = tv.plano_trailing_inteligente(32, rr=3.5, probabilidade=80,
                                              contratos=1, valor_do_tick=VT,
                                              drawdown_restante=10000)
        fraco = tv.plano_trailing_inteligente(32, rr=3.5, probabilidade=55,
                                              contratos=1, valor_do_tick=VT,
                                              drawdown_restante=10000)
        self.assertLess(fraco["stop"], largo["stop"])
        self.assertIn("65", fraco["motivo"])

    def test_desligado_continua_desligado(self):
        self.assertIsNone(tv.plano_trailing_inteligente(32, ligado=False))

    def test_sem_ticks_de_stop_nao_inventa(self):
        self.assertIsNone(tv.plano_trailing_inteligente(0))
        self.assertIsNone(tv.plano_trailing_inteligente(None))


class TestOTetoDaMesa(unittest.TestCase):
    """A regra dele, e a que MANDA nas outras duas."""

    def test_com_drawdown_apertado_o_trail_ENCURTA(self):
        """O caso real: 25 contratos e US$1.000 de drawdown restante. Com o
        trail largo (40 ticks) a devolução possível seria US$1.250 — mais do
        que TODO o drawdown que sobrou."""
        p = tv.plano_trailing_inteligente(32, rr=3.5, probabilidade=80,
                                          contratos=25, valor_do_tick=VT,
                                          drawdown_restante=1000)
        devolucao = p["stop"] * VT * 25
        teto = 1000 * tv.TRAIL_FRACAO_DO_DRAWDOWN
        self.assertLessEqual(devolucao, teto,
                             "a devolução possível não pode passar do teto")
        self.assertIn("REGRA DA MESA", p["motivo"])

    def test_o_teto_SO_encurta_nunca_alarga(self):
        """Com drawdown de sobra, a regra da mesa não pode AUMENTAR a corda —
        senão ela viraria uma licença para devolver mais."""
        folgado = tv.plano_trailing_inteligente(32, rr=2.0, contratos=1,
                                                valor_do_tick=VT,
                                                drawdown_restante=1_000_000)
        self.assertEqual(folgado["stop"], 32)

    def test_posicao_grande_demais_e_DITA_em_voz_alta(self):
        """Quando proteger exigiria um trail colado no preço, o certo é dizer
        que a posição está grande para o drawdown que sobrou — não apertar até
        o absurdo e fingir que protegeu."""
        p = tv.plano_trailing_inteligente(32, rr=3.0, contratos=50,
                                          valor_do_tick=VT,
                                          drawdown_restante=300)
        self.assertTrue(p["aperto_pela_mesa"])
        self.assertEqual(p["stop"], tv.TRAIL_TICKS_MINIMO)
        self.assertIn("grande para o que sobrou", p["motivo"])

    def test_nunca_desce_abaixo_do_minimo(self):
        """Abaixo do mínimo o trail vira ruído: qualquer respiração normal do
        mercado tira o trade."""
        for ctr in (10, 50, 200):
            p = tv.plano_trailing_inteligente(32, rr=3.0, contratos=ctr,
                                              valor_do_tick=VT,
                                              drawdown_restante=50)
            self.assertGreaterEqual(p["stop"], tv.TRAIL_TICKS_MINIMO)

    def test_sem_drawdown_conhecido_a_regra_nao_chuta(self):
        """`None` é 'não sei', e não 'está zerado'. Sem o número, o trail fica
        no que o cenário mandou."""
        p = tv.plano_trailing_inteligente(32, rr=2.0, contratos=25,
                                          valor_do_tick=VT,
                                          drawdown_restante=None)
        self.assertEqual(p["stop"], 32)
        self.assertNotIn("REGRA DA MESA", p["motivo"])


class TestOPorqueSAINOREGISTRO(unittest.TestCase):
    """Um stop que se move sozinho sem explicação é a receita para ele
    desconfiar da ferramenta no meio do pregão."""

    def test_todo_plano_traz_o_motivo_em_portugues(self):
        p = tv.plano_trailing_inteligente(32, rr=2.0, contratos=1,
                                          valor_do_tick=VT,
                                          drawdown_restante=5000)
        self.assertTrue(p["motivo"])
        self.assertNotIn("None", p["motivo"])

    def test_o_app_registra_o_trail_escolhido(self):
        fonte = fonte_do_arquivo()
        self.assertIn("plano_trailing_inteligente(", fonte)
        i = fonte.index("plano_trailing_inteligente(")
        trecho = fonte[i:i + 1500]
        self.assertIn("🪜 TRAIL:", trecho)
        self.assertIn("trailing['motivo']", trecho)

    def test_o_app_passa_o_drawdown_e_o_valor_do_tick(self):
        """Sem esses dois a regra da mesa não tem como agir — ela viraria
        enfeite."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_enviar_bracket")
        corpo = fonte[i:i + 4000]
        self.assertIn("drawdown_restante_hoje()", corpo)
        self.assertIn("valor_por_ponto_do_ativo(", corpo)


class TestDesligarAIALocal(unittest.TestCase):
    """"ela pensa muito às vezes, tendo em vista que estou com API OpenRouter".

    Vira caixinha em vez de instrução no manual porque o motivo dele pode
    mudar: se a internet cair no meio do pregão, a local é a única que não
    depende de conta em lugar nenhum, e religar tem de custar um clique."""

    def test_desligada_sai_da_FILA_e_nao_so_falha(self):
        """A diferença aparece no relógio dele: cada tentativa gasta o tempo
        de subir um modelo que não vai responder, a cada ciclo."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def modelos_do_provedor")
        corpo = fonte[i:i + 1200]
        self.assertIn("if not ia_local_ligada():", corpo)
        self.assertIn("return []", corpo)

    def test_ela_some_tambem_da_lista_de_configurados(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def provedores_configurados")
        self.assertIn("ia_local_ligada() and ia_local_no_ar()",
                      fonte[i:i + 900])

    def test_ligada_por_padrao(self):
        """Quem nunca mexeu na caixinha não pode perder um degrau da escada."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def ia_local_ligada")
        self.assertIn('cfg.get("ia_local_ativa", True)', fonte[i:i + 1200])

    def test_a_caixinha_existe_e_grava_relendo_do_disco(self):
        fonte = fonte_do_arquivo()
        self.assertIn("self.ia_local_var", fonte)
        i = fonte.index("def _salvar_pref_ia_local")
        corpo = fonte[i:i + 1500]
        self.assertIn('salvar_config({"ia_local_ativa"', corpo)
        self.assertIn("gravado = ia_local_ligada()", corpo)

    def test_ao_desligar_ele_e_avisado_do_que_PERDE(self):
        """Desligar sem dizer o custo é deixar o trader descobrir no dia em
        que a rede cair."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _salvar_pref_ia_local")
        self.assertIn("sem internet", fonte[i:i + 1500])


if __name__ == "__main__":
    unittest.main()
