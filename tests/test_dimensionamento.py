"""Dimensionamento de posição — o teste que existe por causa de US$ 1.177,50.

O CASO REAL (pregão de 10/08, conta do Josevan):
    Margem US$1.400 · Risco/operação 20% · Drawdown máximo US$1.400 · MESU6.
    US$1.400 × 20% = US$280 de risco permitido por operação.

    Com um stop de 4 pontos (US$20/contrato) a sugestão saiu com 14 contratos —
    é o número que está no log. Com um stop de 1,87 ponto, que o motor também
    produziu naquela sessão, a MESMA conta seria dimensionada em 29 contratos:
    US$280 ÷ (1,87 × US$5) = 29,9. Vinte e nove contratos numa conta de mil e
    quatrocentos dólares.

    A aritmética está certa; o resultado é insano. A causa é o divisor: quanto
    mais curto o stop, maior a posição. Um stop de 7 ticks no MES é ruído de
    mercado, não invalidação de estrutura.

    (Os 30 contratos que aparecem no log vieram da EXECUÇÃO na plataforma, não
    deste cálculo — essa divergência é assunto do test_execucao.py.)
"""

import unittest

from harness import carregar


def _ns(**stubs):
    # `carregar_posicoes` + `_e_da_conta_ativa` entraram em 22/08: quem calcula
    # RISCO parou de ler por `posicoes_do_ciclo`, porque reiniciar o ciclo
    # apagava prejuízo realizado do teto. Ver operacoes_fechadas_hoje.
    base = {"plano_da_conta_ativa": lambda: {},
            "operacoes_fechadas_hoje": lambda **_: [],
            "posicoes_do_ciclo": lambda: [],
            "carregar_posicoes": lambda: [],
            "_e_da_conta_ativa": lambda p: True}
    base.update(stubs)
    return carregar(
        ["VALOR_POR_PONTO", "VALOR_POR_PONTO_PADRAO", "TICK_MINIMO",
         "MIN_TICKS_STOP_PADRAO", "valor_por_ponto_do_ativo", "tick_do_ativo",
         "calcular_contratos", "dimensionar_pelo_plano",
         "drawdown_restante_hoje"],
        stubs=base)


class TestValorPorPonto(unittest.TestCase):
    def test_prefixo_mais_longo_ganha(self):
        ns = _ns()
        # MESU6 é Micro (US$5), não ES (US$50). Se o prefixo curto ganhasse,
        # todo dimensionamento de micro contrato sairia 10x menor.
        self.assertEqual(ns["valor_por_ponto_do_ativo"]("MESU6"), 5.0)
        self.assertEqual(ns["valor_por_ponto_do_ativo"]("ESU6"), 50.0)
        self.assertEqual(ns["valor_por_ponto_do_ativo"]("MNQZ5"), 2.0)
        self.assertEqual(ns["valor_por_ponto_do_ativo"]("NQZ5"), 20.0)

    def test_tick_desconhecido_devolve_none(self):
        ns = _ns()
        # None é resposta legítima: sem tick conhecido, o piso NÃO é aplicado.
        # Inventar um tick seria pior do que não ter piso.
        self.assertEqual(ns["tick_do_ativo"]("MESU6"), 0.25)
        self.assertIsNone(ns["tick_do_ativo"]("XYZW9"))
        self.assertIsNone(ns["tick_do_ativo"](""))


class TestPisoDeStop(unittest.TestCase):
    def test_stop_de_ruido_vira_posicao_gigante_sem_o_piso(self):
        """Sem piso, 1,87 ponto de stop = 29 contratos. Com piso: recusado."""
        ns = _ns()
        entry, stop = 7772.43, 7770.56          # 1,87 ponto = 7,48 ticks

        sem_piso = ns["calcular_contratos"](entry, stop, "MESU6", 1400, 20, 1400)
        self.assertEqual(sem_piso["contratos"], 29,
                         "o comportamento antigo tem de continuar reproduzível")

        com_piso = ns["calcular_contratos"](entry, stop, "MESU6", 1400, 20, 1400,
                                            min_ticks_stop=8)
        self.assertEqual(com_piso["contratos"], 0)
        self.assertIn("curto demais", com_piso["motivo_limite"])
        self.assertIn("tick", com_piso["motivo_limite"])

    def test_stop_no_limite_do_piso_passa(self):
        ns = _ns()
        # Exatamente 8 ticks (2,00 pontos no MES) tem de PASSAR: o piso é
        # "menor que", não "menor ou igual". Um piso que rejeita o próprio
        # valor configurado confundiria qualquer um.
        r = ns["calcular_contratos"](7772.00, 7770.00, "MESU6", 1400, 20, 1400,
                                     min_ticks_stop=8)
        self.assertEqual(r["ticks_risco"], 8.0)
        self.assertGreater(r["contratos"], 0)

    def test_piso_zero_desliga_a_trava(self):
        ns = _ns()
        r = ns["calcular_contratos"](7772.43, 7770.56, "MESU6", 1400, 20, 1400,
                                     min_ticks_stop=0)
        self.assertEqual(r["contratos"], 29)

    def test_ativo_sem_tick_conhecido_nao_e_barrado(self):
        ns = _ns()
        # Não sei o tick do ativo => não sei medir o piso => não barro.
        r = ns["calcular_contratos"](100.0, 99.9, "XYZW9", 1400, 20, 1400,
                                     min_ticks_stop=8)
        self.assertIsNone(r["ticks_risco"])
        self.assertGreater(r["contratos"], 0)


class TestTetoDeContratos(unittest.TestCase):
    def test_teto_corta_e_diz_que_cortou(self):
        ns = _ns()
        r = ns["calcular_contratos"](7772.43, 7770.56, "MESU6", 1400, 20, 1400,
                                     max_contratos=3, min_ticks_stop=0)
        self.assertEqual(r["contratos"], 3)
        self.assertIn("teto de 3", r["motivo_limite"])

    def test_teto_zero_significa_sem_teto(self):
        ns = _ns()
        r = ns["calcular_contratos"](7772.43, 7770.56, "MESU6", 1400, 20, 1400,
                                     max_contratos=0, min_ticks_stop=0)
        self.assertEqual(r["contratos"], 29)

    def test_teto_acima_do_calculado_nao_interfere(self):
        ns = _ns()
        r = ns["calcular_contratos"](7772.43, 7770.56, "MESU6", 1400, 20, 1400,
                                     max_contratos=100, min_ticks_stop=0)
        self.assertEqual(r["contratos"], 29)
        self.assertIsNone(r["motivo_limite"])


class TestDrawdownRestante(unittest.TestCase):
    def test_teto_passa_a_ser_UMA_FATIA_do_que_sobrou_do_dia(self):
        """ATUALIZADO EM 22/08, e o motivo da mudança está no log do pregão.

        A versão anterior deste teste afirmava: "sobram US$222,50 — e é ISSO
        que a próxima operação pode arriscar". Era o raciocínio de quem
        escreveu a trava, e estava errado pela metade. O que sobrou é
        orçamento do DIA; usá-lo inteiro numa entrada significa que o primeiro
        stop encerra o dia.

        Em 22/08 isso saiu do campo teórico: com US$2.000 restantes e um stop
        de US$40 por contrato, o programa dimensionou 50 contratos e a
        operação seguinte perdeu exatamente US$2.000 às 12:07.

        O teto do dia continua valendo — o que mudou é que uma operação só
        pega uma fatia dele.
        """
        ns = _ns()
        # O dia já perdeu US$1.177,50 de um drawdown de US$1.400. Sobram
        # US$222,50, e 33% disso (US$73,42) é o que UMA entrada pode arriscar.
        r = ns["calcular_contratos"](7772.00, 7767.00, "MESU6", 1400, 20, 1400,
                                     restante_dia=222.50)
        self.assertEqual(r["risco_usd"], 73.42)
        self.assertIn("drawdown que ainda resta", r["motivo_limite"])
        # 5 pontos × US$5 = US$25/contrato → 73,42 ÷ 25 = 2 contratos.
        # Com os 8 de antes, um único stop levava US$200 dos US$222,50 que
        # restavam. Agora restam três tentativas em vez de uma.
        self.assertEqual(r["contratos"], 2)

    def test_sem_restante_usa_o_drawdown_cheio(self):
        ns = _ns()
        r = ns["calcular_contratos"](7772.00, 7767.00, "MESU6", 1400, 20, 1400)
        self.assertEqual(r["risco_usd"], 280.0)   # 20% de 1400, abaixo do dd
        self.assertEqual(r["contratos"], 11)

    def test_restante_zerado_nao_dimensiona_nada(self):
        ns = _ns()
        r = ns["calcular_contratos"](7772.00, 7767.00, "MESU6", 1400, 20, 1400,
                                     restante_dia=0)
        self.assertEqual(r["contratos"], 0)
        self.assertIsNotNone(r["motivo_limite"])


class TestDrawdownRestanteHoje(unittest.TestCase):
    def test_desconta_realizado_e_aberto(self):
        # A posição ABERTA agora vem de `carregar_posicoes`, não do ciclo: o
        # prejuízo em aberto de hoje conta contra o teto mesmo que o trader
        # tenha reiniciado a contagem de meta no meio do pregão.
        ns = _ns(operacoes_fechadas_hoje=lambda **_: [{"pnl_final": -900.0}],
                 carregar_posicoes=lambda: [
                     {"status": "ABERTA", "pnl_atual": -277.50}])
        self.assertAlmostEqual(
            ns["drawdown_restante_hoje"]({"drawdown_maximo": 1400}), 222.50)

    def test_lucro_nao_aumenta_o_limite(self):
        ns = _ns(operacoes_fechadas_hoje=lambda **_: [{"pnl_final": 5000.0}])
        # Ganhar não compra permissão para arriscar mais que o plano manda.
        self.assertEqual(
            ns["drawdown_restante_hoje"]({"drawdown_maximo": 1400}), 1400)

    def test_sem_drawdown_configurado_devolve_none(self):
        ns = _ns()
        # None não é zero: "não há teto configurado" ≠ "o teto acabou".
        self.assertIsNone(ns["drawdown_restante_hoje"]({"drawdown_maximo": 0}))

    def test_nunca_devolve_negativo(self):
        ns = _ns(operacoes_fechadas_hoje=lambda **_: [{"pnl_final": -9000.0}])
        self.assertEqual(
            ns["drawdown_restante_hoje"]({"drawdown_maximo": 1400}), 0.0)


class TestEntradasInvalidas(unittest.TestCase):
    def test_sem_margem_explica(self):
        ns = _ns()
        r = ns["calcular_contratos"](7772, 7767, "MESU6", 0, 20, 1400)
        self.assertEqual(r["contratos"], 0)
        self.assertIn("Margem", r["motivo_limite"])

    def test_entry_igual_stop(self):
        ns = _ns()
        r = ns["calcular_contratos"](7772, 7772, "MESU6", 1400, 20, 1400)
        self.assertEqual(r["contratos"], 0)

    def test_none_nao_explode(self):
        ns = _ns()
        for e, s in ((None, 7767), (7772, None), (None, None)):
            self.assertEqual(
                ns["calcular_contratos"](e, s, "MESU6", 1400, 20, 1400)["contratos"], 0)

    def test_risco_de_um_contrato_maior_que_o_permitido(self):
        ns = _ns()
        # ES cheio (US$50/pt), stop de 20 pontos = US$1.000/contrato, com
        # apenas US$280 permitidos. Zero contratos, e dizendo por quê.
        r = ns["calcular_contratos"](6000, 5980, "ESU6", 1400, 20, 1400)
        self.assertEqual(r["contratos"], 0)
        self.assertIn("já passa", r["motivo_limite"])


class TestDimensionarPeloPlano(unittest.TestCase):
    def test_junta_plano_travas_e_drawdown(self):
        plano = {"margem": 1400, "risco_pct": 20, "drawdown_maximo": 1400,
                 "max_contratos": 0, "min_ticks_stop": 8}
        ns = _ns(plano_da_conta_ativa=lambda: plano,
                 operacoes_fechadas_hoje=lambda **_: [{"pnl_final": -1177.50}],
                 posicoes_do_ciclo=lambda: [])
        # Stop de 1,87 ponto: barrado pelo piso, mesmo com drawdown sobrando.
        r = ns["dimensionar_pelo_plano"](7772.43, 7770.56, "MESU6")
        self.assertEqual(r["contratos"], 0)
        self.assertIn("curto demais", r["motivo_limite"])
        # Stop de 5 pontos: passa no piso, mas o drawdown restante aperta —
        # e agora aperta pela FATIA, não pelo restante inteiro. O atalho tem
        # de levar a fatia junto: se `dimensionar_pelo_plano` esquecer de
        # passá-la, todo o resto do programa volta a dimensionar pelo dia
        # cheio sem que nada acuse.
        r2 = ns["dimensionar_pelo_plano"](7772.00, 7767.00, "MESU6")
        self.assertEqual(r2["risco_usd"], 73.42)
        self.assertEqual(r2["contratos"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestAvisosDoPlano(unittest.TestCase):
    """Aritmética sobre os números que o trader digitou — nunca opinião."""

    def _avisos(self, plano):
        # As duas tabelas vêm junto porque o aviso do teto de contratos
        # precisa de um ativo de referência (o MES) para dizer onde o teto
        # real está. Sem elas o teste morria de NameError no dia em que um
        # plano com 'max_contratos' chegasse aqui.
        return carregar(["avisos_do_plano", "TICK_MINIMO",
                         "VALOR_POR_PONTO"])["avisos_do_plano"](plano)

    def test_o_plano_real_da_conta_1(self):
        # Margem 1400 · Drawdown 1400 · Risco 20% · Teto 6 operações.
        # 20% de 1400 = 280 por trade → 1400 ÷ 280 = 5 stops encerram o dia,
        # ANTES do teto de 6 operações. Ninguém tinha dito isso ao trader.
        avisos = self._avisos({"margem": 1400, "drawdown_maximo": 1400,
                               "risco_pct": 20, "max_operacoes_dia": 6,
                               "max_stops_seguidos": 5, "min_ticks_stop": 8})
        texto = " ".join(avisos)
        self.assertIn("5.0 stop(s) encerram o seu dia", texto)
        self.assertIn("ANTES do limite de operações", texto)
        self.assertIn("igual ou maior que a margem", texto)

    def test_plano_conservador_nao_gera_alarme_falso(self):
        # 1% de risco, drawdown de 5% da margem: 5 stops também, mas o
        # drawdown NÃO é a conta inteira. Só o aviso de sequência aparece.
        avisos = self._avisos({"margem": 10000, "drawdown_maximo": 500,
                               "risco_pct": 1, "max_operacoes_dia": 6,
                               "max_stops_seguidos": 2, "min_ticks_stop": 8})
        texto = " ".join(avisos)
        self.assertNotIn("igual ou maior que a margem", texto)

    def test_piso_de_ticks_desligado_e_avisado(self):
        avisos = self._avisos({"margem": 10000, "drawdown_maximo": 500,
                               "risco_pct": 1, "min_ticks_stop": 0})
        self.assertTrue(any("desligado" in a for a in avisos))

    def test_plano_vazio_nao_explode_nem_inventa(self):
        self.assertEqual(
            [a for a in self._avisos({}) if "stop(s) encerram" in a], [])


class TestAMetaQueNaoCabeNoPlano(unittest.TestCase):
    """22/08: 'ele está configurado para bater a meta em um dia, ele tem
    margem, ele tem drawdown disponível, risco de 5% — o que explica tamanha
    cautela?'

    Não era cautela. Era a conta:

        Margem US$2.000 × 5%      = US$100 de risco por operação
        entrada 7540,0 · stop 7528,0 = 12 pontos = US$60 por contrato no MES
        US$100 ÷ US$60               = 1 contrato

    O dimensionamento era a única parte do sistema que estava obedecendo ao
    plano à risca. O que faltava era alguém dizer que o RESTO do plano não
    fechava: com 5 operações por dia e R:R 1:2, o melhor dia possível deste
    plano são US$1.000 — um TERÇO da Meta de US$3.000 que estava salva na
    mesma tela, e isso acertando 5 de 5.

    Ele passou a tarde procurando defeito no dimensionamento. O defeito era o
    silêncio sobre a meta.
    """

    def _avisos(self, plano):
        return carregar(["avisos_do_plano", "TICK_MINIMO",
                         "VALOR_POR_PONTO"])["avisos_do_plano"](plano)

    SEU_PLANO = {"margem": 2000.0, "risco_pct": 5.0, "drawdown_maximo": 1000.0,
                 "meta_alvo": 3000.0, "dias_meta": 1, "rr_minimo": 2.0,
                 "max_operacoes_dia": 5, "max_stops_seguidos": 3,
                 "max_contratos": 60, "min_ticks_stop": 8}

    def test_a_meta_impossivel_e_dita_em_voz_alta(self):
        texto = " ".join(self._avisos(self.SEU_PLANO))
        self.assertIn("NÃO CABE", texto)
        self.assertIn("US$1,000.00", texto)   # o melhor dia possível
        self.assertIn("3.0x", texto)          # o tamanho do buraco

    def test_o_aviso_mostra_a_saida_sem_escolher_por_ele(self):
        """Quatro caminhos, e a decisão continua sendo dele. Um programa que
        mexe com dinheiro informa; quem arrisca decide."""
        texto = " ".join(self._avisos(self.SEU_PLANO))
        for saida in ("risco/operação", "margem", "dias p/ bater a meta",
                      "máx. operações/dia"):
            self.assertIn(saida, texto)

    def test_o_programa_promete_NAO_crescer_sozinho_atras_da_meta(self):
        """A trava que dá sentido ao aviso.

        A saída preguiçosa seria o motor aumentar a posição sozinho até a
        Meta caber — e aí o 'Risco/operação 5%' na tela viraria enfeite,
        exatamente como o 'Máx. contratos 60'. O tamanho sai do risco que ele
        definiu, não do que falta para o alvo."""
        texto = " ".join(self._avisos(self.SEU_PLANO))
        self.assertIn("não vou aumentar posição por conta própria", texto)

    def test_meta_que_cabe_nao_gera_aviso(self):
        """US$1.000 em 1 dia CABE nos mesmos números — e aí o programa cala a
        boca. Aviso que aparece sempre é aviso que ninguém lê."""
        plano = dict(self.SEU_PLANO, meta_alvo=1000.0)
        self.assertEqual(
            [a for a in self._avisos(plano) if "NÃO CABE" in a], [])

    def test_o_teto_de_contratos_decorativo_e_denunciado(self):
        """'Máx. contratos 60' com US$100 de risco e piso de 8 ticks: o
        dimensionamento nunca passa de 10 no MES. Um número na tela que não
        pode acontecer é o que faz o trader procurar defeito onde não há."""
        texto = " ".join(self._avisos(self.SEU_PLANO))
        self.assertIn("nunca vai ser alcançado", texto)
        self.assertIn("10 contrato(s)", texto)

    def test_teto_de_contratos_alcancavel_fica_quieto(self):
        plano = dict(self.SEU_PLANO, max_contratos=4)
        self.assertEqual(
            [a for a in self._avisos(plano) if "nunca vai ser" in a], [])

    def test_sem_meta_configurada_nao_inventa_cobranca(self):
        plano = dict(self.SEU_PLANO, meta_alvo=0)
        self.assertEqual(
            [a for a in self._avisos(plano) if "NÃO CABE" in a], [])
