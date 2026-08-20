"""A média de acertos do motor — e a honestidade de dizer quando ela não vale.

19/08, ele: "futuramente eu preciso ter em registro a media de acertos do
motor, portanto, preciso que comece a registrar de forma bem criteriosa todas
as sugestoes que me enviar, confrontando posteriormente em conferencia com o
preco se de fato a sugestao foi uma sugestao valida (GAINS)".

O REGISTRO JÁ EXISTIA, e é a parte boa da história: toda sugestão que sai vira
linha no diário de sinais, e o motor acompanha cada cenário contra o preço da
tela até ele resolver — no alvo ou no stop — gravando entrada, saída,
R-múltiplo, P&L e as confluências daquela leitura. Vale inclusive para o que
ele NÃO acatou, porque a pergunta é sobre o desempenho do MOTOR, não do trader.

O que faltava era a conta. E a conta tem duas armadilhas, as duas cobertas
aqui:

  1. TAXA CALCULADA SÓ SOBRE O QUE FECHOU é a estatística mais fácil de
     enganar que existe. Se metade das sugestões continua em acompanhamento,
     "70% de acerto" não quer dizer nada.
  2. TAXA DE ACERTO SOZINHA MENTE. 90% de acerto com 1:0,1 perde dinheiro. Por
     isso a expectativa em R sai junto, sempre.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _op(resultado, r, usd=0.0, direcao="BUY"):
    return {"resultado": resultado, "r_multiplo": r, "pnl_usd": usd,
            "direcao": direcao, "hora": "10", "confluencias": []}


class TestAContaDoAcerto(unittest.TestCase):

    def _ns(self):
        return carregar(["relatorio_de_acerto", "texto_do_relatorio_de_acerto",
                         "AMOSTRA_MINIMA_ACERTO"],
                        stubs={"carregar_performance": lambda: [],
                               "carregar_sinais_log": lambda: []})

    def test_conta_acertos_erros_e_taxa(self):
        ns = self._ns()
        rel = ns["relatorio_de_acerto"](
            [_op("WIN", 2.0), _op("WIN", 2.0), _op("LOSS", -1.0)])
        self.assertEqual((rel["acertos"], rel["erros"], rel["resolvidas"]),
                         (2, 1, 3))
        self.assertAlmostEqual(rel["taxa"], 66.7, places=0)

    def test_a_EXPECTATIVA_em_R_sai_junto(self):
        """Taxa de acerto sozinha mente: 90% de acerto com 1:0,1 perde
        dinheiro. O número que diz se a coisa paga é o R médio."""
        ns = self._ns()
        rel = ns["relatorio_de_acerto"](
            [_op("WIN", 0.1)] * 9 + [_op("LOSS", -1.0)])
        self.assertAlmostEqual(rel["taxa"], 90.0)
        self.assertLess(rel["r_medio"], 0, "90% de acerto e ainda assim negativo")

    def test_separa_por_LADO(self):
        ns = self._ns()
        rel = ns["relatorio_de_acerto"](
            [_op("WIN", 1, direcao="BUY"), _op("LOSS", -1, direcao="BUY"),
             _op("WIN", 1, direcao="SELL")])
        self.assertEqual(rel["por_direcao"]["BUY"][:2], (1, 2))
        self.assertEqual(rel["por_direcao"]["SELL"][:2], (1, 1))

    def test_as_que_ainda_NAO_resolveram_sao_contadas_a_parte(self):
        """Sem isto, 'X% de acerto' esconde quantas sugestões continuam em
        aberto — e uma taxa sobre metade da amostra não é uma taxa."""
        ns = self._ns()
        rel = ns["relatorio_de_acerto"]([_op("WIN", 1.0)], total_sugestoes=10)
        self.assertEqual(rel["pendentes"], 9)

    def test_o_que_nao_e_WIN_nem_LOSS_nao_entra(self):
        ns = self._ns()
        rel = ns["relatorio_de_acerto"](
            [_op("WIN", 1.0), {"resultado": "CANCELADO"}, {"resultado": None}])
        self.assertEqual(rel["resolvidas"], 1)

    def test_historico_vazio_devolve_zeros_e_nao_palpite(self):
        ns = self._ns()
        rel = ns["relatorio_de_acerto"]([])
        self.assertEqual((rel["resolvidas"], rel["taxa"], rel["r_medio"]),
                         (0, 0.0, 0.0))

    def test_numero_estragado_no_disco_nao_derruba_a_conta(self):
        ns = self._ns()
        rel = ns["relatorio_de_acerto"](
            [{"resultado": "WIN", "r_multiplo": "abc", "pnl_usd": None,
              "direcao": "BUY"}])
        self.assertEqual(rel["resolvidas"], 1)
        self.assertEqual(rel["r_total"], 0.0)


class TestOTextoNaoCravaOQueNaoSustenta(unittest.TestCase):

    def _ns(self, db, sinais=0):
        return carregar(["relatorio_de_acerto", "texto_do_relatorio_de_acerto",
                         "AMOSTRA_MINIMA_ACERTO"],
                        stubs={"carregar_performance": lambda: list(db),
                               "carregar_sinais_log": lambda: [{}] * sinais})

    def test_sem_desfecho_ele_DIZ_que_nao_tem_taxa(self):
        ns = self._ns([])
        texto = ns["texto_do_relatorio_de_acerto"]()
        self.assertIn("Ainda não tenho taxa de acerto", texto)

    def test_amostra_pequena_vem_com_o_aviso_em_cima(self):
        """Abaixo do mínimo a taxa balança dezenas de pontos por sorte. Cravar
        o número ali é convidar a decidir dinheiro em cima de acaso."""
        ns = self._ns([_op("WIN", 1.0)] * 3)
        texto = ns["texto_do_relatorio_de_acerto"]()
        self.assertIn("AMOSTRA PEQUENA", texto)
        self.assertIn(str(ns["AMOSTRA_MINIMA_ACERTO"]), texto)

    def test_amostra_suficiente_nao_leva_o_aviso(self):
        ns = self._ns([_op("WIN", 1.0)] * 25)
        self.assertNotIn("AMOSTRA PEQUENA",
                         ns["texto_do_relatorio_de_acerto"]())

    def test_o_texto_mostra_a_expectativa_e_o_acumulado(self):
        ns = self._ns([_op("WIN", 2.0, 100.0), _op("LOSS", -1.0, -50.0)])
        texto = ns["texto_do_relatorio_de_acerto"]()
        self.assertIn("expectativa", texto)
        self.assertIn("R", texto)
        self.assertIn("US$", texto)

    def test_diz_quantas_ainda_estao_em_acompanhamento(self):
        ns = self._ns([_op("WIN", 1.0)], sinais=5)
        self.assertIn("em acompanhamento", ns["texto_do_relatorio_de_acerto"]())

    def test_nunca_devolve_vazio(self):
        for db, s in (([], 0), ([_op("WIN", 1.0)], 1), ([_op("LOSS", -1.0)], 9)):
            self.assertTrue(self._ns(db, s)["texto_do_relatorio_de_acerto"]().strip())


class TestElePERGUNTAEElaRESPONDEDoDisco(unittest.TestCase):
    """Mandar essa pergunta para o modelo seria pedir a ele que estimasse o
    próprio desempenho — e ele estimaria, com um número redondo e simpático."""

    def _ns(self):
        return carregar(["pergunta_sobre_acerto", "_RE_ACERTO", "_norm_busca",
                         "_sem_acento"])

    def test_as_formas_de_perguntar(self):
        ns = self._ns()
        for t in ("qual a sua taxa de acerto?", "quantas voce acertou?",
                  "qual o win rate do motor", "qual a media de acertos",
                  "qual o percentual de acerto das suas sugestoes",
                  "as suas sugestoes acertam?",
                  "como esta o desempenho do motor",
                  "quantos acertos voce teve"):
            self.assertTrue(ns["pergunta_sobre_acerto"](t), t)

    def test_perguntar_de_UM_trade_nao_e_pedir_estatistica(self):
        ns = self._ns()
        for t in ("acertou o alvo?", "o preco acertou o stop",
                  "voce errou o ticker", "o que voce aprendeu comigo",
                  "qual a media do meu resultado diario",
                  "boa tarde", "liga o motor", "o que é ote"):
            self.assertFalse(ns["pergunta_sobre_acerto"](t), t)

    def test_texto_vazio_nao_quebra(self):
        ns = self._ns()
        for t in ("", None, "   "):
            self.assertFalse(ns["pergunta_sobre_acerto"](t), repr(t))

    def test_a_resposta_sai_SEM_MODELO_e_antes_do_aprendizado(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def responder_offline(")
        bloco = fonte[i:i + 2500]
        self.assertIn("pergunta_sobre_acerto(pergunta)", bloco)
        self.assertLess(bloco.index("pergunta_sobre_acerto(pergunta)"),
                        bloco.index("pergunta_sobre_aprendizado(pergunta)"),
                        "'taxa de acerto' é mais específica que 'o que você "
                        "aprendeu' e tem de ser testada primeiro")

    def test_entra_no_contexto_da_conversa_e_no_registro_do_motor(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _chat_status_texto(")
        self.assertIn("texto_do_relatorio_de_acerto()", fonte[i:i + 3500])
        j = fonte.index("ROBÔ SMC INICIADO COM MÓDULO DE APRENDIZADO")
        self.assertIn("texto_do_relatorio_de_acerto()", fonte[j:j + 1400])


if __name__ == "__main__":
    unittest.main()
