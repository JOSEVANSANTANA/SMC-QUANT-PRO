import unittest
from harness import carregar

NOMES = ["erro_e_cota", "erro_e_modelo_inexistente", "segundos_ate_cota_voltar", "classificar_erro_modelo"]
COTA_DIA = ("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Quota exceeded ... "
            "GenerateRequestsPerDayPerProjectPerModel-FreeTier ... Please retry in 21h6m53.7s.', "
            "'details': [{'retryDelay': '76404s'}]}}")


class TestCota(unittest.TestCase):
    def test_cota_com_404_no_numero_nao_mata_o_modelo(self):
        ns = carregar(NOMES)
        self.assertFalse(ns["erro_e_modelo_inexistente"](COTA_DIA))
        self.assertEqual(ns["classificar_erro_modelo"](COTA_DIA), "cota")

    def test_404_de_verdade_continua_sendo_invalido(self):
        ns = carregar(NOMES)
        self.assertTrue(ns["erro_e_modelo_inexistente"]("404 NOT_FOUND. models/x is not found"))
        self.assertTrue(ns["erro_e_modelo_inexistente"]("models/x is no longer available"))

    def test_cota_diaria_espera_horas_e_cota_por_minuto_nao(self):
        ns = carregar(NOMES)
        self.assertGreater(ns["segundos_ate_cota_voltar"](COTA_DIA), 3600)
        self.assertEqual(ns["segundos_ate_cota_voltar"]("429 RESOURCE_EXHAUSTED per minute", 900), 900)


if __name__ == "__main__":
    unittest.main()
