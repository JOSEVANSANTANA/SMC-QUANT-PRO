"""O piso de qualidade — quem decide se uma leitura vira sugestão.

O CASO REAL (pregão de 10/08): sete descartes seguidos de BUY MESU6, com
R:R 1:0,55 · 1:0,66 · 1:1,00 · 1:1,19 · 1:1,74 · 1:1,91 · 1:1,94, todos contra
o piso de 1:2. Do lado do trader isso lê como "a ferramenta não acerta uma".
Do lado do código, parte daqueles cenários tinha um 2º alvo que pagava o piso
com folga — e era descartado por causa do PRIMEIRO alvo, o da parcial.
"""

import unittest

from harness import carregar


def _ns():
    return carregar(["avaliar_piso_de_qualidade"])


class TestRRPeloPrimeiroAlvo(unittest.TestCase):
    def test_primeiro_alvo_paga_o_piso(self):
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"](
            "BUY", entry=7770, stop=7765, tp1=7782, tp2=7790,
            rr_minimo=2.0, probabilidade=70, probabilidade_minima=55)
        self.assertTrue(r["ok"])
        self.assertEqual(r["alvo_do_piso"], 1)
        self.assertAlmostEqual(r["rr"], 2.4)

    def test_probabilidade_abaixo_do_piso_reprova_mesmo_com_rr_bom(self):
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"](
            "BUY", 7770, 7765, 7790, 7800, 2.0, 40, 55)
        self.assertFalse(r["ok"])
        self.assertGreater(r["rr"], 2.0)   # o R:R passou; a convicção não


class TestSegundoAlvoSalvaOCenario(unittest.TestCase):
    def test_o_caso_do_1_para_1_19(self):
        """1º alvo paga 1:1,19 (descartado antes); 2º paga 1:2,60."""
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"](
            "BUY", entry=7770, stop=7765, tp1=7775.95, tp2=7783,
            rr_minimo=2.0, probabilidade=75, probabilidade_minima=55)
        self.assertTrue(r["ok"])
        self.assertEqual(r["alvo_do_piso"], 2)
        self.assertAlmostEqual(r["rr_tp1"], 1.19)
        self.assertAlmostEqual(r["rr"], 2.6)

    def test_vale_para_venda_tambem(self):
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"](
            "SELL", entry=7770, stop=7775, tp1=7764.05, tp2=7757,
            rr_minimo=2.0, probabilidade=75, probabilidade_minima=55)
        self.assertTrue(r["ok"])
        self.assertEqual(r["alvo_do_piso"], 2)

    def test_segundo_alvo_do_lado_errado_nao_salva_nada(self):
        """Alvo ABAIXO da entrada numa COMPRA não é alvo. Se isto regredir, um
        erro de leitura da IA vira sugestão aprovada com R:R inventado."""
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"](
            "BUY", entry=7770, stop=7765, tp1=7775.95, tp2=7757,
            rr_minimo=2.0, probabilidade=75, probabilidade_minima=55)
        self.assertFalse(r["ok"])
        self.assertEqual(r["alvo_do_piso"], 1)

    def test_segundo_alvo_tambem_curto_continua_reprovando(self):
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"](
            "BUY", entry=7770, stop=7765, tp1=7772, tp2=7776,
            rr_minimo=2.0, probabilidade=85, probabilidade_minima=55)
        self.assertFalse(r["ok"])
        self.assertLess(r["rr_tp2"], 2.0)

    def test_o_piso_nao_foi_afrouxado(self):
        """A regra continua sendo 1:2. O que mudou foi CONTRA QUAL ALVO se
        mede — nunca o valor do piso."""
        ns = _ns()
        for rr_min in (1.5, 2.0, 3.0):
            r = ns["avaliar_piso_de_qualidade"](
                "BUY", 7770, 7765, 7775, 7780, rr_min, 90, 55)
            # tp1 = 1:1 · tp2 = 1:2
            self.assertEqual(r["ok"], rr_min <= 2.0, rr_min)


class TestBordas(unittest.TestCase):
    def test_sem_alvo_nenhum(self):
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"]("BUY", 7770, 7765, 0, 0, 2.0, 90, 55)
        self.assertFalse(r["ok"])
        self.assertEqual(r["alvo_do_piso"], 0)
        self.assertEqual(r["rr"], 0.0)

    def test_entrada_igual_ao_stop_nao_divide_por_zero(self):
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"]("BUY", 7770, 7770, 7790, 7800,
                                            2.0, 90, 55)
        self.assertFalse(r["ok"])
        self.assertEqual(r["rr"], 0.0)

    def test_none_no_lugar_dos_precos(self):
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"]("BUY", None, None, None, None,
                                            2.0, 90, 55)
        self.assertFalse(r["ok"])

    def test_hold_nao_ganha_o_atalho_do_segundo_alvo(self):
        """O atalho do 2º alvo só existe para BUY/SELL. Um 'HOLD' com alvos
        preenchidos não pode ser promovido a cenário aprovado."""
        ns = _ns()
        r = ns["avaliar_piso_de_qualidade"](
            "HOLD", 7770, 7765, 7775.95, 7783, 2.0, 90, 55)
        self.assertEqual(r["alvo_do_piso"], 1)
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
