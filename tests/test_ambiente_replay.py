"""Testes de identificação determinística de Conta e Modo Replay (RPL).

PORTADO PARA O HARNESS EM 22/08. A versão original fazia `import main_app`,
que arrasta customtkinter e tkinter para dentro do processo de teste. No Mac
do trader isso passa; em qualquer máquina sem a pilha gráfica — e o servidor
onde a suíte é auditada é uma delas — o módulo inteiro morre no import e os
três testes viram ERROR sem nunca terem rodado.

É o motivo de `carregar()` existir: o teste isola as funções que quer e não
depende de haver tela. Aqui bastavam duas.
"""
import unittest
from unittest.mock import MagicMock

from harness import carregar

ns = carregar(["texto_do_ambiente_atual"],
              stubs={"unicodedata": __import__("unicodedata")})


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
        txt = ns["texto_do_ambiente_atual"](bot)
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
        txt_demo = ns["texto_do_ambiente_atual"](bot_demo)
        self.assertIn("DEMO", txt_demo)

        bot_real = MagicMock()
        bot_real.ler_ambiente.return_value = {
            "conta": "12345678",
            "modo": "REAL",
            "eh_replay": False,
        }
        txt_real = ns["texto_do_ambiente_atual"](bot_real)
        self.assertIn("MERCADO REAL", txt_real)

    # O teste de ROTEAMENTO ("é replay?" vira AMBIENTE_MERCADO) mudou-se para
    # test_conversa.py. Não foi para escondê-lo: `interpretar_intencao` puxa
    # meia dúzia de funções junto, e a lista dessas dependências já é mantida
    # lá, no helper `_ns_intencao()`. Uma segunda cópia da lista aqui ficaria
    # desatualizada na primeira refatoração — e um teste de intenção que não
    # roda é pior do que nenhum. Cada teste no arquivo de quem já tem a
    # ferramenta certa.


if __name__ == "__main__":
    unittest.main()
