#!/usr/bin/env python3
"""
Testes unitários para o módulo market_regime.py.
"""

import unittest
from market_regime import ConfluenceMatrix, MarketRegimeClassifier, REGIME_EXPANSAO, REGIME_COMPRESSAO, REGIME_RISCO_NOTICIA


class TestMarketRegime(unittest.TestCase):
    def test_classificacao_expansao_alta(self):
        candles = [
            {"open": 100.0, "high": 102.0, "low": 99.5, "close": 101.5},
            {"open": 101.5, "high": 104.0, "low": 101.0, "close": 103.5},
            {"open": 103.5, "high": 106.0, "low": 103.0, "close": 105.5},
            {"open": 105.5, "high": 108.0, "low": 105.0, "close": 107.5},
            {"open": 107.5, "high": 110.0, "low": 107.0, "close": 109.5},
        ]
        res = MarketRegimeClassifier.classificar(candles=candles, atr_atual=3.0, atr_medio=2.0)
        self.assertEqual(res["regime"], REGIME_EXPANSAO)
        self.assertEqual(res["direcao"], "ALTA")
        self.assertTrue(res["permissao_operar"])

    def test_classificacao_risco_noticia(self):
        res = MarketRegimeClassifier.classificar(minutos_para_noticia=5)
        self.assertEqual(res["regime"], REGIME_RISCO_NOTICIA)
        self.assertFalse(res["permissao_operar"])

    def test_matriz_confluencia_aprovada(self):
        setup = {
            "direcao": "BUY",
            "confluencias": ["ORDER_BLOCK", "FVG", "CHOCH"],
            "rr": 2.5
        }
        order_flow = {
            "pressao": "COMPRADORA",
            "absorcao": True
        }
        regime = {
            "regime": REGIME_EXPANSAO,
            "direcao": "ALTA"
        }

        res = ConfluenceMatrix.pontuar_setup(setup, order_flow, regime)
        self.assertGreaterEqual(res["score"], 80)
        self.assertTrue(res["aprovado"])
        self.assertEqual(res["veredito"], "APROVADO INSTITUCIONAL")

    def test_matriz_confluencia_rejeita_risco_noticia(self):
        setup = {
            "direcao": "BUY",
            "confluencias": ["ORDER_BLOCK", "FVG"],
            "rr": 2.0
        }
        regime = {
            "regime": REGIME_RISCO_NOTICIA
        }

        res = ConfluenceMatrix.pontuar_setup(setup, regime=regime)
        self.assertFalse(res["aprovado"])
        self.assertIn("BLOQUEIO", res["alertas"][0])


if __name__ == "__main__":
    unittest.main()
