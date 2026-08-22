"""UMA OPERAÇÃO NÃO PODE GASTAR O DIA INTEIRO.

Este arquivo inteiro nasceu de um pregão só, 22/08/2026, e do log que o
trader colou:

    11:41  ORDEM ENVIADA: BUY MESU6 10 ctr @ 7540,0 · stop 7532,0
    11:44  Operação encerrada no STOP: resultado US$ -400,00
    11:56  ORDEM ENVIADA: BUY MESU6 60 ctr @ 7542,5 · stop 7536,0
    11:57  ... SELL MESU6 33 ctr @ 7540,0 · stop 7552,0
    12:03  ORDEM ENVIADA: BUY MESU6 50 ctr @ 7550,0 · stop 7542,0
    12:07  Operação encerrada no STOP: resultado US$ -2.000,00
    12:08  o prejuízo de hoje bateu o drawdown máximo do plano (US$2.000,00)

A aritmética fecha exata e é isso que dói: stop de 8 pontos × US$5/ponto =
US$40 por contrato. Com US$2.000 de drawdown restante, 2000 ÷ 40 = 50
contratos. O dimensionamento fez a conta certa da regra errada — montou uma
posição cujo pior caso valia CEM POR CENTO do que restava do dia. O stop fez
o que stop faz, e às 12:07 o dia tinha acabado.

O defeito não era de execução nem de leitura de tela. Era de conceito: o
drawdown restante é orçamento do DIA e estava servindo de orçamento de UMA
ENTRADA. A trava sabia reduzir o risco até o limite; não sabia dizer que uma
aposta sozinha não pode valer o limite todo.
"""

import unittest

from harness import carregar


def _ns():
    return carregar(
        ["FRACAO_MAX_DO_RESTANTE_PADRAO", "calcular_contratos"],
        stubs={"valor_por_ponto_do_ativo": lambda a: 5.0,
               "tick_do_ativo": lambda a: 0.25})


class TestOPregaoDe22De08(unittest.TestCase):

    def test_o_trade_que_zerou_o_dia_nao_passa_mais(self):
        """O caso exato das 12:03: 50 contratos, stop de US$2.000."""
        ns = _ns()
        r = ns["calcular_contratos"](
            entry=7550.0, stop=7542.0, asset_symbol="MESU6",
            margem=50000, risco_pct=4.0, drawdown_maximo=2000,
            restante_dia=2000.0)
        # US$40 de risco por contrato; 33% de US$2.000 = US$660 -> 16 contratos.
        self.assertEqual(r["contratos"], 16)
        self.assertLessEqual(r["risco_real_usd"], 2000.0 * 0.33)
        self.assertIn("uma operação sozinha não pode gastar o dia inteiro",
                      r["motivo_limite"])

    def test_o_pior_caso_deixa_o_trader_vivo_para_o_proximo_trade(self):
        """O ponto não é o número 16 — é sobreviver ao stop.

        Com o teto antigo, um stop consumia o dia e não havia segundo trade.
        Dois perdedores seguidos acontecem toda semana; se o primeiro já
        reprova a conta, a estratégia nunca chega a ser testada.
        """
        ns = _ns()
        restante = 2000.0
        for _ in range(3):
            r = ns["calcular_contratos"](
                entry=7550.0, stop=7542.0, asset_symbol="MESU6",
                margem=50000, risco_pct=4.0, drawdown_maximo=2000,
                restante_dia=restante)
            self.assertGreater(r["contratos"], 0,
                               "três stops seguidos têm de caber no dia")
            restante -= r["risco_real_usd"]
        self.assertGreater(restante, 0)

    def test_com_lote_de_60_contratos_tambem_encolhe(self):
        """As 11:56: 60 contratos com stop de 6,5 pontos (US$32,50/ctr)."""
        ns = _ns()
        r = ns["calcular_contratos"](
            entry=7542.5, stop=7536.0, asset_symbol="MESU6",
            margem=50000, risco_pct=4.0, drawdown_maximo=2000,
            restante_dia=2000.0)
        self.assertLess(r["contratos"], 60)
        self.assertLessEqual(r["risco_real_usd"], 660.0)


class TestATravaSoAperta(unittest.TestCase):
    """Ela nunca pode AUMENTAR posição — só cortar."""

    def test_plano_conservador_passa_intacto(self):
        """Quem já arrisca pouco não é afetado pela fatia.

        Risco do plano = US$200; 33% de US$2.000 = US$660. O menor manda, e o
        menor é o do plano. Se esta trava aumentasse a posição de alguém, ela
        seria o próprio problema que veio resolver.
        """
        ns = _ns()
        r = ns["calcular_contratos"](
            entry=7550.0, stop=7542.0, asset_symbol="MESU6",
            margem=20000, risco_pct=1.0, drawdown_maximo=2000,
            restante_dia=2000.0)
        self.assertEqual(r["contratos"], 5)          # US$200 / US$40
        self.assertEqual(r["risco_usd"], 200.0)

    def test_sem_drawdown_restante_informado_nada_muda(self):
        """Os recálculos de histórico passam restante_dia=None de propósito:
        uma regra de hoje não pode reescrever o P&L de ontem."""
        ns = _ns()
        r = ns["calcular_contratos"](
            entry=7550.0, stop=7542.0, asset_symbol="MESU6",
            margem=20000, risco_pct=1.0, drawdown_maximo=0,
            restante_dia=None)
        self.assertEqual(r["contratos"], 5)


class TestQuandoNaoDaParaOperar(unittest.TestCase):

    def test_dia_quase_esgotado_devolve_zero_e_explica(self):
        """Zero contratos é resposta, não é falha.

        Restando US$50 do dia, a fatia dá US$16,50 e nem um contrato cabe. A
        resposta certa é não operar — e o motivo tem de dizer isso, senão ele
        vê '0' e acha que o programa quebrou.
        """
        ns = _ns()
        r = ns["calcular_contratos"](
            entry=7550.0, stop=7542.0, asset_symbol="MESU6",
            margem=50000, risco_pct=4.0, drawdown_maximo=2000,
            restante_dia=50.0)
        self.assertEqual(r["contratos"], 0)
        self.assertIn("US$40.00", r["motivo_limite"])
        self.assertIn("uma operação sozinha não pode gastar o dia inteiro",
                      r["motivo_limite"])

    def test_fatia_invalida_cai_no_padrao_em_vez_de_liberar_tudo(self):
        """Configuração estragada não pode virar 'sem limite'.

        Um `0`, um `None` ou um `1,8` vindos de um plano editado à mão não
        podem abrir a porteira: o padrão assume, e o padrão é apertado.
        """
        ns = _ns()
        for ruim in (0, None, -0.5, 1.8, "abc"):
            r = ns["calcular_contratos"](
                entry=7550.0, stop=7542.0, asset_symbol="MESU6",
                margem=50000, risco_pct=4.0, drawdown_maximo=2000,
                restante_dia=2000.0, fracao_max_do_restante=ruim)
            self.assertEqual(r["contratos"], 16, f"fração {ruim!r}")

    def test_o_trader_pode_escolher_outra_fatia(self):
        """A trava é dele, não minha: 50% é decisão legítima de quem assume."""
        ns = _ns()
        r = ns["calcular_contratos"](
            entry=7550.0, stop=7542.0, asset_symbol="MESU6",
            margem=50000, risco_pct=4.0, drawdown_maximo=2000,
            restante_dia=2000.0, fracao_max_do_restante=0.5)
        self.assertEqual(r["contratos"], 25)         # US$1.000 / US$40

    def test_o_padrao_sobrevive_a_tres_stops(self):
        ns = _ns()
        self.assertLessEqual(ns["FRACAO_MAX_DO_RESTANTE_PADRAO"], 1 / 3 + 0.01)
        self.assertGreater(ns["FRACAO_MAX_DO_RESTANTE_PADRAO"], 0)


if __name__ == "__main__":
    unittest.main()
