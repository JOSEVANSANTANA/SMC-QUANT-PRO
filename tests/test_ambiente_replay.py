"""Testes de identificação determinística de Conta e Modo Replay (RPL)."""
import unittest
import sys
from unittest.mock import MagicMock

from harness import RAIZ
sys.path.insert(0, RAIZ)
import main_app  # noqa: E402
import tradovate_auto as tv  # noqa: E402


class TestDeteccaoAmbienteReplay(unittest.TestCase):

    def test_reconhece_conta_replay_pelo_prefixo_rpl(self):
        bot = MagicMock()
        bot.ler_ambiente.return_value = {
            "conta": "RPL2893430-5",
            "modo": "REPLAY",
            "eh_replay": True,
            "velocidade": "400%",
            "horario_mercado": "09:07:16 CDT"
        }
        txt = main_app.texto_do_ambiente_atual(bot)
        self.assertIn("MARKET REPLAY", txt)
        self.assertIn("RPL2893430-5", txt)
        self.assertIn("400%", txt)

    def test_reconhece_conta_real_e_demo(self):
        bot_demo = MagicMock()
        bot_demo.ler_ambiente.return_value = {
            "conta": "DEMO998811",
            "modo": "DEMO",
            "eh_replay": False,
        }
        txt_demo = main_app.texto_do_ambiente_atual(bot_demo)
        self.assertIn("DEMO", txt_demo)

        bot_real = MagicMock()
        bot_real.ler_ambiente.return_value = {
            "conta": "12345678",
            "modo": "REAL",
            "eh_replay": False,
        }
        txt_real = main_app.texto_do_ambiente_atual(bot_real)
        self.assertIn("MERCADO REAL", txt_real)

    def test_intencao_pergunta_sobre_replay_ou_mercado_real(self):
        perguntas = [
            "é replay?",
            "estou no replay?",
            "é mercado real ou replay?",
            "estamos no replay?",
            "qual ambiente?",
            "modo replay",
        ]
        for p in perguntas:
            intencao = main_app.interpretar_intencao(p)
            self.assertEqual(intencao, "AMBIENTE_MERCADO", f"Falhou para: {p}")


if __name__ == "__main__":
    unittest.main()
