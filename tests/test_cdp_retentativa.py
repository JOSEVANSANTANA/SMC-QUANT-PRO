import unittest

from tradovate_auto import TradovateAuto


class TestAvisoDeCDPAusente(unittest.TestCase):

    def test_avisa_uma_vez_e_volta_a_avisar_apos_recuperacao(self):
        mensagens = []
        bot = TradovateAuto(log=mensagens.append)
        bot.chrome_ligado = lambda: False

        self.assertFalse(bot.conectar())
        self.assertFalse(bot.conectar())
        avisos_cdp = [m for m in mensagens if "não encontrado na porta" in m]
        self.assertEqual(len(avisos_cdp), 1)

        bot.chrome_ligado = lambda: True
        bot.descobrir_aba_tradovate = lambda _id=None: None
        self.assertFalse(bot.conectar())

        bot.chrome_ligado = lambda: False
        self.assertFalse(bot.conectar())
        avisos_cdp = [m for m in mensagens if "não encontrado na porta" in m]
        self.assertEqual(len(avisos_cdp), 2)


if __name__ == "__main__":
    unittest.main()