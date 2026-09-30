"""O que separa uma leitura de mercado de uma alucinação.

Do log de 11/08, o trecho que explica "nenhuma entrada de hoje foi válida":

    18:01  Preço 7753.25  ⚠️ não muda há 3 ciclos
    ...
    18:05  Leitura IA: BUY  · Preço 7753.25  (não muda há 7 ciclos)
    18:06  Leitura IA: SELL · Preço 7753.25  (não muda há 8 ciclos)
    18:07  Leitura IA: SELL · Preço 7753.25  (não muda há 9 ciclos)
    18:10  Leitura IA: BUY  · Preço 7753.25  (não muda há 12 ciclos)
    18:11  Leitura IA: BUY  · Preço 7753.25  (não muda há 13 ciclos)

A tela estava PARADA e o motor virou de lado quatro vezes em cima da mesma
imagem. O aviso existia desde sempre — e não impedia nada. Avisar sem agir é o
mesmo que não avisar.

E o segundo caso, das 15:30:
    Preço 7741.75 · sugestão SELL com entrada em 7785.00
Quarenta e três pontos acima do mercado, 8,6 vezes o risco. A ordem ficou
pendente e morreu sem nunca ser tocada.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _ns():
    return carregar(["_num", "MAX_DISTANCIA_ENTRADA_R",
                     "CICLOS_PARA_PRECO_CONGELADO",
                     "avaliar_distancia_da_entrada"])


class TestPrecoCongelado(unittest.TestCase):
    def test_o_limite_e_de_tres_leituras(self):
        """Duas leituras iguais podem ser mercado parado; três significam tela
        que não atualiza."""
        self.assertEqual(_ns()["CICLOS_PARA_PRECO_CONGELADO"], 3)

    def test_a_trava_bloqueia_de_verdade_a_sugestao(self):
        """O ponto do defeito: o aviso existia e não agia. Agora a leitura
        congelada entra na mesma porta dos outros filtros (`repetido`)."""
        fonte = fonte_do_arquivo()
        self.assertIn("leitura_congelada = (", fonte)
        i = fonte.index("if leitura_congelada and acao in (\"BUY\", \"SELL\"):\n"
                        "                            repetido = True")
        self.assertGreater(i, 0, "a trava não está ligada ao gate de sugestão")

    def test_o_aviso_nao_se_repete_a_cada_ciclo(self):
        """Treze linhas iguais no log é o que fez o trader parar de ler os
        avisos. O aviso sai uma vez e volta a sair quando o preço se mexer."""
        fonte = fonte_do_arquivo()
        self.assertIn("_avisou_congelado", fonte)
        self.assertIn("self._avisou_congelado = False", fonte,
                      "sem o reset, ela cala para sempre depois do 1º aviso")


class TestDistanciaDaEntrada(unittest.TestCase):
    def test_o_caso_real_das_1530(self):
        """Preço 7741,75 · SELL com entrada 7785,00 · stop 7790,00.
        Risco 5 pontos, distância 43,25 = 8,65 R. Fora."""
        ns = _ns()
        ok, dist = ns["avaliar_distancia_da_entrada"](7785.0, 7790.0, 7741.75)
        self.assertFalse(ok)
        self.assertAlmostEqual(dist, 8.65, places=2)

    def test_entrada_perto_do_preco_passa(self):
        """Preço 7756,5 · SELL entrada 7762,0 · stop 7765,5 = 1,57 R. Passa —
        é uma ordem limitada normal esperando o preço voltar."""
        ns = _ns()
        ok, dist = ns["avaliar_distancia_da_entrada"](7762.0, 7765.5, 7756.5)
        self.assertTrue(ok)
        self.assertAlmostEqual(dist, 1.57, places=2)

    def test_entrada_no_proprio_preco(self):
        ns = _ns()
        ok, dist = ns["avaliar_distancia_da_entrada"](7750.0, 7745.0, 7750.0)
        self.assertTrue(ok)
        self.assertEqual(dist, 0.0)

    def test_o_limite_e_exatamente_3R(self):
        ns = _ns()
        # 3,0 R passa; 3,1 R não. O limite é "menor ou igual".
        self.assertTrue(ns["avaliar_distancia_da_entrada"](100.0, 90.0, 130.0)[0])
        self.assertFalse(ns["avaliar_distancia_da_entrada"](100.0, 90.0, 131.0)[0])

    def test_sem_como_medir_nao_barra_nada(self):
        """Ausência de medida NUNCA vira reprovação — é a mesma regra do piso
        de ticks: não sei medir, não barro."""
        ns = _ns()
        for args in ((None, 90.0, 100.0), (100.0, None, 100.0),
                     (100.0, 90.0, None), (100.0, 100.0, 100.0),
                     (100.0, 90.0, 0)):
            ok, dist = ns["avaliar_distancia_da_entrada"](*args)
            self.assertTrue(ok, args)
            self.assertIsNone(dist, args)

    def test_limite_zero_desliga_a_trava(self):
        ns = _ns()
        ok, dist = ns["avaliar_distancia_da_entrada"](7785.0, 7790.0, 7741.75,
                                                      max_r=0)
        self.assertTrue(ok)
        self.assertIsNotNone(dist, "mesmo desligada, a medida continua sendo dita")

    def test_vale_para_os_dois_lados(self):
        ns = _ns()
        # BUY com entrada muito ABAIXO do preço: mesma distância, mesmo veredito.
        self.assertFalse(
            ns["avaliar_distancia_da_entrada"](7700.0, 7695.0, 7743.25)[0])


class TestTemaEscuroFixado(unittest.TestCase):
    def test_o_modo_de_aparencia_e_declarado(self):
        """22 dos 101 rótulos usam a cor padrão do tema. Com o CustomTkinter em
        modo 'System' num sistema em MODO CLARO, essa cor é `gray10` — quase
        preto sobre o fundo #0a0e14 do próprio app. Metade da aba some."""
        fonte = fonte_do_arquivo()
        self.assertIn('ctk.set_appearance_mode("dark")', fonte)

    def test_e_declarado_antes_de_qualquer_janela(self):
        fonte = fonte_do_arquivo()
        self.assertLess(fonte.index('ctk.set_appearance_mode("dark")'),
                        fonte.index("class SmcQuantApp"),
                        "o modo precisa ser fixado ANTES de a janela nascer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
