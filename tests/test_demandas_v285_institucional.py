# -*- coding: utf-8 -*-
"""Testes unitários das melhorias institucionais v2.85+ (18 demandas)."""

import unittest

from harness import carregar
import market_regime
import tiger_predictive
import tradovate_auto


def _ns():
    return carregar([
        "validar_coerencia_sinal_ia",
        "freio_de_sugestoes",
        "data_do_pregao",
    ])


class TestCoerenciaSinalIA(unittest.TestCase):
    """Item 1: Bloqueia contradição entre action (BUY/SELL) e geometria/texto."""

    def test_buy_com_texto_e_confluencia_bearish_e_bloqueado(self):
        ns = _ns()
        sinal = {
            "action": "BUY",
            "entry_price": 29815.0,
            "stop_loss": 29795.0,
            "take_profit_1": 29860.0,
            "confluence_factors": [
                "Order Block bearish",
                "Liquidity sweep",
                "FVG / ineficiência",
            ],
            "market_analysis": (
                "O mercado testou uma zona de resistência importante marcada por um "
                "bloco de ordens vendedoras (Order Block bearish) no topo. "
                "A entrada curta posicionada no miolo do order block aproveita a "
                "assimetria para capturar o movimento de retração. O stop loss fica "
                "protegido acima do pavio máximo da manipulação."
            ),
        }
        ok, acao_corr, motivo = ns["validar_coerencia_sinal_ia"](sinal)
        self.assertFalse(ok)
        self.assertEqual(acao_corr, "HOLD")
        self.assertIn("contradição textual", motivo)

    def test_buy_com_geometria_invertida_e_bloqueado(self):
        ns = _ns()
        sinal = {
            "action": "BUY",
            "entry_price": 7700.0,
            "stop_loss": 7710.0,      # stop ACIMA da entrada num BUY!
            "take_profit_1": 7680.0,  # alvo ABAIXO da entrada num BUY!
            "confluence_factors": ["Order Block bullish"],
            "market_analysis": "Compra no desconto.",
        }
        ok, acao_corr, motivo = ns["validar_coerencia_sinal_ia"](sinal)
        self.assertFalse(ok)
        self.assertEqual(acao_corr, "HOLD")
        self.assertIn("geometria", motivo)

    def test_buy_coerente_passa_normalmente(self):
        ns = _ns()
        sinal = {
            "action": "BUY",
            "entry_price": 7700.0,
            "stop_loss": 7690.0,
            "take_profit_1": 7725.0,
            "confluence_factors": ["Bullish Order Block", "Liquidity Sweep", "Discount Zone"],
            "market_analysis": (
                "Varreu liquidez no fundo e reagiu no Order Block comprador em desconto, "
                "com stop protegido abaixo da mínima e alvo na liquidez compradora do topo."
            ),
        }
        ok, acao_corr, motivo = ns["validar_coerencia_sinal_ia"](sinal)
        self.assertTrue(ok)
        self.assertEqual(acao_corr, "BUY")
        self.assertEqual(motivo, "")


class TestContraTendenciaForte(unittest.TestCase):
    """Item 13: Bloqueia operações contra tendência direcional forte sem reversão estrutural."""

    def test_bloqueia_compra_contra_tendencia_forte_de_baixa(self):
        info_regime = {
            "regime": market_regime.REGIME_EXPANSAO,
            "efficiency_ratio": 0.78,
            "tendencia_forte": True,
            "direcao": "BEARISH",
        }
        ok, motivo = market_regime.avaliar_contra_tendencia_forte(
            "BUY", info_regime, ["Order Block", "Discount Zone"], probabilidade=72.0
        )
        self.assertFalse(ok)
        self.assertIn("tendência forte de BAIXA", motivo)

    def test_permite_reversao_estrutural_completa_com_alta_probabilidade(self):
        info_regime = {
            "regime": market_regime.REGIME_EXPANSAO,
            "efficiency_ratio": 0.75,
            "tendencia_forte": True,
            "direcao": "BEARISH",
        }
        ok, motivo = market_regime.avaliar_contra_tendencia_forte(
            "BUY",
            info_regime,
            ["CHoCH", "Liquidity Sweep", "Bullish Order Block", "FVG"],
            probabilidade=88.0,
        )
        self.assertTrue(ok)
        self.assertEqual(motivo, "")


class TestMetaDiariaAtingidaFreio(unittest.TestCase):
    """Item 18: Para sugestões e operações ao atingir a meta diária da conta."""

    def test_freio_para_ao_atingir_meta_diaria(self):
        ns = _ns()
        plano = {
            "meta_alvo": 2500.0,
            "dias_meta": 5,  # meta diária = US$ 500.00
            "parar_na_meta_diaria": True,
            "drawdown_maximo": 1000.0,
            "max_stops_seguidos": 2,
            "max_operacoes_dia": 6,
        }
        pos_ganho = [
            {
                "id": 1,
                "conta_id": "conta_teste",
                "status": "FECHADA",
                "pnl_final": 520.0,
                "data_fechamento": f"{ns['data_do_pregao']()} 11:30",
            }
        ]
        ns["carregar_posicoes"] = lambda: pos_ganho
        pode, motivo = ns["freio_de_sugestoes"](plano, conta_id="conta_teste")
        self.assertFalse(pode)
        self.assertIn("META DO DIA ATINGIDA", motivo)
        self.assertIn("próximo pregão", motivo)


class TestBlindagemZeroDevolucao(unittest.TestCase):
    """Item 10: Modo Blindagem Zero-Devolução (0.5R) no trailing inteligente."""

    def test_modo_blindagem_arma_em_meio_r(self):
        res = tradovate_auto.plano_trailing_inteligente(
            ticks_stop=20,
            rr=2.5,
            probabilidade=75,
            contratos=2,
            valor_do_tick=1.25,
            drawdown_restante=1000.0,
            ligado=True,
            modo_r="🛡️ Blindagem Zero-Devolução (0.5R)",
            ativo="MESU6",
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["acionar"], 10)  # 0.5 * 20 ticks = 10 ticks
        self.assertLessEqual(res["stop"], 10)
        self.assertIn("zero-devolução", res["motivo"].lower())


class TestPlanoTaticoMetaMomentum(unittest.TestCase):
    """Item 8: Consultor tático de Meta & Momentum."""

    def test_meta_batida_retorna_modo_blindado(self):
        plano = {"meta_alvo": 2000.0, "dias_meta": 4, "margem": 50000.0, "risco_pct": 1.0}
        res = tiger_predictive.calcular_plano_tatico_meta_momentum(
            plano, realizado_hoje=550.0, realizado_ciclo=1200.0, dd_restante=1000.0
        )
        self.assertTrue(res["meta_diaria_batida"])
        self.assertEqual(res["postura"], "META_BATIDA_ENCERRAR_DIA")


if __name__ == "__main__":
    unittest.main()
