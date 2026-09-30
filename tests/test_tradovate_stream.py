#!/usr/bin/env python3
"""
Testes unitários para o módulo tradovate_stream.py.
"""

import json
import unittest
from tradovate_stream import TradovateStream


class _MockCDP:
    def __init__(self, retorno_js=None):
        self.retorno_js = retorno_js or {}
        self.chamadas = []

    def cdp(self, metodo, params=None, timeout=10):
        self.chamadas.append((metodo, params))
        return {
            "result": {
                "value": json.dumps(self.retorno_js)
            }
        }


class TestTradovateStream(unittest.TestCase):
    def test_leitura_estado_sucesso(self):
        mock_dados = {
            "ok": True,
            "ts": 123456789,
            "ativo": "MNQU6",
            "preco": 29650.25,
            "posicao": 2,
            "pnl_flutuante": 150.0
        }
        cdp = _MockCDP(mock_dados)
        stream = TradovateStream(cdp)

        estado = stream.ler_estado_ao_vivo()
        self.assertTrue(estado["ok"])
        self.assertEqual(estado["ativo"], "MNQU6")
        self.assertEqual(estado["preco"], 29650.25)
        self.assertEqual(estado["posicao"], 2)
        self.assertEqual(estado["pnl_flutuante"], 150.0)

    def test_ler_preco_imediato(self):
        mock_dados = {"ok": True, "preco": 7780.50, "ativo": "MESU6"}
        cdp = _MockCDP(mock_dados)
        stream = TradovateStream(cdp)

        preco = stream.ler_preco_imediato()
        self.assertEqual(preco, 7780.50)

    def test_ler_posicao_e_pnl(self):
        mock_dados = {"ok": True, "posicao": -1, "pnl_flutuante": -50.0}
        cdp = _MockCDP(mock_dados)
        stream = TradovateStream(cdp)

        pos, pnl = stream.ler_posicao_e_pnl()
        self.assertEqual(pos, -1)
        self.assertEqual(pnl, -50.0)

    def test_sem_cdp_retorna_erro_seguro(self):
        stream = TradovateStream(None)
        estado = stream.ler_estado_ao_vivo()
        self.assertFalse(estado["ok"])
        self.assertIn("não configurado", estado["erro"])


if __name__ == "__main__":
    unittest.main()
