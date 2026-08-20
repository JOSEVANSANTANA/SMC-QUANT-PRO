#!/usr/bin/env python3
"""
Testes unitários para o módulo order_flow.py.
"""

import unittest
from order_flow import OrderFlowEngine


class TestOrderFlowEngine(unittest.TestCase):
    def setUp(self):
        self.engine = OrderFlowEngine(max_ticks=100)

    def test_calculo_cvd_acumulado(self):
        self.engine.registrar_tick(preco=100.0, volume=5.0, agressao_compra=True)
        self.engine.registrar_tick(preco=100.25, volume=2.0, agressao_compra=False)
        self.engine.registrar_tick(preco=100.50, volume=3.0, agressao_compra=True)

        # 5 - 2 + 3 = 6
        self.assertEqual(self.engine.obter_cvd(), 6.0)
        self.assertEqual(self.engine.volume_total, 10.0)

    def test_detectar_absorcao_compradora(self):
        # Simula 20 ticks de venda agressiva em 100.0 sem o preço cair
        for _ in range(20):
            self.engine.registrar_tick(preco=100.0, volume=2.0, agressao_compra=False)

        res = self.engine.detectar_absorcao(nivel_preco=100.0, tolerancia=0.25)
        self.assertTrue(res["absorcao"])
        self.assertEqual(res["tipo"], "ABSORCAO_COMPRADORA")

    def test_detectar_sweep_de_liquidez_bullish(self):
        # Rompe mínima de 100.0 caindo para 99.50 e volta para 100.50 com agressão compradora
        self.engine.registrar_tick(preco=100.0, volume=5.0, agressao_compra=False)
        self.engine.registrar_tick(preco=99.50, volume=10.0, agressao_compra=False)
        for _ in range(5):
            self.engine.registrar_tick(preco=100.50, volume=4.0, agressao_compra=True)

        sweep = self.engine.detectar_sweep_de_liquidez(
            maxima_recente=105.0, minima_recente=100.0, preco_atual=100.50, direcao="BUY"
        )
        self.assertTrue(sweep["sweep"])
        self.assertEqual(sweep["tipo"], "BULLISH_SWEEP")

    def test_volume_profile_poc(self):
        self.engine.registrar_tick(preco=100.0, volume=5.0)
        self.engine.registrar_tick(preco=101.0, volume=20.0)  # Maior volume
        self.engine.registrar_tick(preco=102.0, volume=10.0)

        profile = self.engine.calcular_volume_profile(agrupamento_ticks=1.0)
        self.assertEqual(profile["poc"], 101.0)
        self.assertEqual(profile["volume_poc"], 20.0)


if __name__ == "__main__":
    unittest.main()
