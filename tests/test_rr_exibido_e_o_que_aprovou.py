"""23/08, 20:11: A TELA MOSTROU UM R:R QUE O PRÓPRIO PISO TERIA RECUSADO.

Com 13 contratos vendidos já abertos, a sugestão saiu assim no chat:

    📘 Nova sugestão: SELL MESU6 — entrada 7687.5, stop 7692.5,
       alvo 7682.5, R:R 1.0, probabilidade 82%

O piso de qualidade configurado era 1:2. Um R:R 1.0 não passa em 1:2 — e
mesmo assim virou sugestão. À primeira vista, piso furado.

NÃO ERA. O piso funcionou; quem mentiu foi a tela.

`avaliar_piso_de_qualidade` testa o TP1 e, se ele não paga o piso, CAI PARA O
TP2 e aprova por ele (devolvendo `alvo_do_piso = 2`). Com os números reais
daquele dia:

    entrada 7687,5 · stop 7692,5 · tp1 7682,5 · tp2 7677,5
      rr_tp1 = 1.0   <- este era o exibido
      rr_tp2 = 2.0   <- este era o que aprovou

O texto da sugestão pegava `sinal_ativo["tp1"]` toda vez que `tp1` existisse,
sem olhar qual alvo tinha de fato passado. E o comentário do próprio código,
logo acima da linha, prometia o contrário do que ela fazia:

    "Usa o mesmo alvo do piso de qualidade (tp1, ou tp2 se não houver tp1),
     então o número exibido nunca fica abaixo do RR_MINIMO que aprovou."

POR QUE ISTO IMPORTA, SE NÃO MUDA NENHUM TRADE
-----------------------------------------------
Não muda mesmo: a operação enviada é a mesma, com os mesmos alvos. O que muda
é a capacidade do trader de CONFERIR a operação. Ele configurou 1:2, leu 1.0
na tela e não teve como saber se o robô furou a régua ou se a tela estava
errada — teve de perguntar. Um painel que mostra um número e decide por outro
apaga a auditoria, que é justamente o que sustenta deixar isto rodando
sozinho.

É a mesma família do bracket que chegou na corretora diferente do decidido:
o dinheiro não muda de lugar, a confiança muda.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _ns():
    return carregar(["avaliar_piso_de_qualidade"])


class TestOPisoAprovaPeloTP2QuandoOTP1NaoPaga(unittest.TestCase):
    """Primeiro, provar que o piso NÃO estava furado — o mecanismo é legítimo."""

    def setUp(self):
        self.f = _ns()["avaliar_piso_de_qualidade"]

    def test_o_caso_REAL_das_2011(self):
        r = self.f("SELL", 7687.5, 7692.5, 7682.5, 7677.5, 2.0, 82, 70)
        self.assertTrue(r["ok"])
        self.assertEqual(r["alvo_do_piso"], 2)
        self.assertEqual(r["rr_tp1"], 1.0)
        self.assertEqual(r["rr_tp2"], 2.0)

    def test_quando_o_TP1_ja_paga_o_piso_e_ele_que_vale(self):
        r = self.f("SELL", 7690.0, 7695.0, 7680.0, 7670.0, 2.0, 80, 70)
        self.assertTrue(r["ok"])
        self.assertEqual(r["alvo_do_piso"], 1)

    def test_se_NENHUM_dos_dois_paga_o_cenario_e_recusado(self):
        """O piso continua sendo piso — o TP2 é uma segunda chance, não um
        atalho para aprovar qualquer coisa."""
        r = self.f("SELL", 7690.0, 7695.0, 7688.0, 7686.0, 2.0, 90, 70)
        self.assertFalse(r["ok"])

    def test_o_TP2_do_LADO_ERRADO_nao_salva_o_cenario(self):
        """Num SELL, um 'alvo' acima da entrada não é alvo — é prejuízo com
        outro nome. Aceitá-lo aprovaria o cenário pelo valor absoluto."""
        r = self.f("SELL", 7690.0, 7695.0, 7688.0, 7712.0, 2.0, 90, 70)
        self.assertFalse(r["ok"])

    def test_probabilidade_abaixo_do_minimo_reprova_mesmo_com_RR_bom(self):
        """Os dois pisos valem juntos, não em alternativa."""
        r = self.f("SELL", 7687.5, 7692.5, 7682.5, 7677.5, 2.0, 50, 70)
        self.assertFalse(r["ok"])


class TestATelaMostraOALVOQueAprovou(unittest.TestCase):
    """A correção: o R:R exibido é o do alvo que passou no piso."""

    def _bloco(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("_alvo_rr_disp =")
        return fonte[max(0, i - 1800):i + 400]

    def test_o_alvo_exibido_sai_de_alvo_do_piso(self):
        bloco = self._bloco()
        self.assertIn("alvo_do_piso == 2", bloco)
        self.assertIn('sinal_ativo["tp2"]', bloco)

    def test_NAO_pega_mais_o_tp1_so_por_ele_existir(self):
        """Era `sinal_ativo["tp1"] or sinal_ativo["tp2"]` — o `or` escolhia o
        TP1 sempre que ele existisse, mesmo tendo sido o TP2 a aprovar."""
        fonte = fonte_do_arquivo()
        self.assertNotIn('_alvo_rr_disp = sinal_ativo["tp1"] or sinal_ativo["tp2"]',
                         fonte)

    def test_sem_tp2_nao_quebra(self):
        """Cenário com um alvo só continua funcionando."""
        bloco = self._bloco()
        i = bloco.index("_alvo_rr_disp =")
        self.assertIn('or sinal_ativo["tp2"]', bloco[i:i + 220])

    def test_o_caso_de_2011_esta_REGISTRADO_no_codigo(self):
        """Comentário que promete o que o código não faz foi o que segurou
        este defeito por tanto tempo. Agora o número real está escrito ali."""
        bloco = self._bloco()
        self.assertIn("7682.5", bloco)
        self.assertIn("R:R 1.0", bloco)

    def test_o_comentario_MENTIROSO_saiu(self):
        """A frase antiga prometia exatamente o comportamento certo, e por
        isso ninguém foi conferir a linha embaixo dela."""
        fonte = fonte_do_arquivo()
        self.assertNotIn("Usa o mesmo alvo do piso de qualidade\n", fonte)

    def test_o_R_R_continua_saindo_dos_PRECOS_e_nunca_do_texto_da_IA(self):
        bloco = self._bloco()
        self.assertIn("nunca", bloco.lower())
        self.assertIn('sinal_ativo["entry"]', bloco)


class TestAConferenciaEmNumerosDoDiaReal(unittest.TestCase):
    """A régua medida em Python, com os preços que estavam na tela dele."""

    def test_o_que_ele_LERIA_antes_e_o_que_le_agora(self):
        entrada, stop = 7687.5, 7692.5
        tp1, tp2 = 7682.5, 7677.5
        risco = abs(entrada - stop)
        antes = round(abs(tp1 - entrada) / risco, 2)     # o que a tela mostrava
        agora = round(abs(tp2 - entrada) / risco, 2)     # o que aprovou
        self.assertEqual(antes, 1.0)
        self.assertEqual(agora, 2.0)
        # E o ponto: o número exibido agora nunca fica abaixo do piso.
        self.assertGreaterEqual(agora, 2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
