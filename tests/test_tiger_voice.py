#!/usr/bin/env python3
"""
Testes unitários para o módulo tiger_voice.py (Jarvis / TIGER Voice Assistant).
"""

import unittest
from unittest.mock import MagicMock, patch
from tiger_voice import TigerVoiceAssistant


class TestTigerVoiceAssistant(unittest.TestCase):
    def setUp(self):
        self.assistente = TigerVoiceAssistant(api_key="sk-or-v1-teste123456789")

    def test_executar_comando_abrir_tradovate(self):
        executou, msg = self.assistente.executar_comando("abrir tradovate")
        self.assertTrue(executou)
        self.assertIn("Tradovate", msg)

    def test_executar_comando_abrir_tradingview(self):
        executou, msg = self.assistente.executar_comando("abrir tradingview")
        self.assertTrue(executou)
        self.assertIn("TradingView", msg)

    def test_executar_comando_abrir_chrome(self):
        executou, msg = self.assistente.executar_comando("abrir chrome")
        self.assertTrue(executou)
        self.assertIn("Google Chrome", msg)

    def test_executar_comando_horario(self):
        executou, msg = self.assistente.executar_comando("que horas são?")
        self.assertTrue(executou)
        self.assertIn("Agora são", msg)

    def test_executar_comando_desligar(self):
        self.assistente.executando = True
        executou, msg = self.assistente.executar_comando("desligar tiger")
        self.assertTrue(executou)
        self.assertFalse(self.assistente.executando)
        self.assertIn("Desligando", msg)

    def test_comando_desconhecido_retorna_false(self):
        executou, msg = self.assistente.executar_comando("como está a taxa de juros do Fed?")
        self.assertFalse(executou)
        self.assertEqual(msg, "")

    @patch("urllib.request.urlopen")
    def test_consultar_openrouter_fallback_http(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"choices": [{"message": {"content": "O mercado esta em tendencia de alta."}}]}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        self.assistente.client_openai = None  # força fallback HTTP nativo
        resp = self.assistente.consultar_openrouter("qual a tendência do NQ?")
        self.assertEqual(resp, "O mercado esta em tendencia de alta.")


if __name__ == "__main__":
    unittest.main()
