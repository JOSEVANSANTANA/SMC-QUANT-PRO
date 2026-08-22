"""EU ESCREVI QUATRO NOMES DE MODELO DE CABEÇA. OS QUATRO ESTAVAM ERRADOS.

20/08, log dele, com a chave JÁ autenticando (o 401 tinha acabado):

    ⚠️ .../deepseek/deepseek-chat-v3.1:free      : não existe para esta conta (404)
    ⚠️ .../meta-llama/llama-3.3-70b-instruct:free: não existe para esta conta (404)
    ⚠️ .../google/gemini-2.0-flash-exp:free      : não existe para esta conta (404)
    ⚠️ .../qwen/qwen-2.5-72b-instruct:free       : não existe para esta conta (404)
    ⚠️ .../openai/gpt-4o-mini: HTTP 402 "Insufficient credits. This account
                                          never purchased credits."
    ❌ NÃO respondeu — o modelo pedido não existe para esta conta (404).

Conferido contra o catálogo real: nenhum dos quatro nomes existe. O catálogo
tem 414 modelos e muda sozinho — qualquer lista que eu digite aqui começa a
apodrecer no mesmo dia em que eu escrevo.

E repare no resumo: ele copiou o ÚLTIMO erro (404, problema MEU, que ele não
tem como resolver) e enterrou o 402, que era a única linha da rodada dizendo
algo acionável sobre a CONTA dele.

Duas correções, então: perguntar o catálogo em vez de inventá-lo, e resumir
pelo erro que mais diz, não pelo que chegou por último.
"""

import unittest

from harness import carregar, fonte_do_arquivo, modulo_requests


def _ns():
    return carregar(
        ["modelos_gratuitos_openrouter", "modelos_do_provedor", "PROVEDORES_IA",
         "erro_mais_informativo", "diagnostico_de_provedor", "ia_local_no_ar",
         "_CACHE_MODELOS_OPENROUTER", "VALIDADE_CATALOGO_SEG"],
        stubs={"requests": modulo_requests()})


class _RespostaFalsa:
    def __init__(self, dados, status=200):
        self.status_code, self._d = status, dados

    def json(self):
        return self._d


class TestOCatalogoVemDaPropriaOpenRouter(unittest.TestCase):

    def _com_catalogo(self, dados, status=200):
        ns = _ns()
        chamadas = []

        class Req:
            @staticmethod
            def get(url, timeout=None):
                chamadas.append(url)
                return _RespostaFalsa(dados, status)
        ns["requests"] = Req
        ns["_CACHE_MODELOS_OPENROUTER"]["lista"] = []
        ns["_CACHE_MODELOS_OPENROUTER"]["quando"] = 0.0
        return ns, chamadas

    def _catalogo(self):
        z = {"prompt": "0", "completion": "0"}
        pago = {"prompt": "0.0000015", "completion": "0.000006"}
        return {"data": [
            {"id": "openrouter/free", "pricing": z},
            {"id": "google/gemma-4-31b-it:free", "pricing": z},
            {"id": "openai/gpt-4o-mini", "pricing": pago},
            {"id": "anthropic/claude-3.5-sonnet", "pricing": pago},
        ]}

    def test_devolve_SO_os_gratuitos(self):
        """A conta dele nunca comprou crédito — o 402 diz isso com todas as
        letras. Gastar dinheiro dele sem ele pedir não é papel do programa."""
        ns, _ = self._com_catalogo(self._catalogo())
        lista = ns["modelos_gratuitos_openrouter"]()
        self.assertIn("openrouter/free", lista)
        self.assertIn("google/gemma-4-31b-it:free", lista)
        self.assertNotIn("openai/gpt-4o-mini", lista)
        self.assertNotIn("anthropic/claude-3.5-sonnet", lista)

    def test_o_roteador_automatico_vem_PRIMEIRO(self):
        """'openrouter/free' não é um modelo: é a própria OpenRouter escolhendo
        entre os gratuitos que estiverem de pé. É a resiliência que fez este
        provedor ser o primeiro da fila, e ela não serve de nada se eu insistir
        num nome fixo."""
        ns, _ = self._com_catalogo(self._catalogo())
        self.assertEqual(ns["modelos_gratuitos_openrouter"]()[0], "openrouter/free")

    def test_consulta_o_catalogo_SEM_CHAVE(self):
        """O catálogo é público. Consultar sem chave tem duas vantagens: sei os
        nomes certos antes da primeira pergunta, e uma falha aqui nunca é
        confundida com 'a chave dele não presta'."""
        ns, chamadas = self._com_catalogo(self._catalogo())
        ns["modelos_gratuitos_openrouter"]()
        self.assertEqual(chamadas, ["https://openrouter.ai/api/v1/models"])

    def test_catalogo_fora_do_ar_devolve_VAZIO_e_nao_um_palpite(self):
        """[] quer dizer 'não sei', não 'não existe nenhum'. Quem chama cai na
        reserva — que é o comportamento certo, e não inventar nome."""
        ns, _ = self._com_catalogo({}, status=500)
        self.assertEqual(ns["modelos_gratuitos_openrouter"](), [])

    def test_sem_catalogo_o_provedor_cai_na_RESERVA(self):
        ns, _ = self._com_catalogo({}, status=500)
        lista = ns["modelos_do_provedor"]("openrouter")
        self.assertTrue(lista, "sem catálogo tem de sobrar a lista de reserva")
        self.assertIn("openrouter/free", lista)

    def test_o_catalogo_e_guardado_por_algumas_horas(self):
        """Uma consulta por pergunta seria desperdício; uma por dia deixaria a
        lista envelhecer dentro do pregão."""
        ns, chamadas = self._com_catalogo(self._catalogo())
        ns["modelos_gratuitos_openrouter"]()
        ns["modelos_gratuitos_openrouter"]()
        self.assertEqual(len(chamadas), 1, "a segunda vez tem de vir do cache")


class TestOsNomesQueEuInventei(unittest.TestCase):

    def test_a_lista_fixa_NAO_e_mais_a_fonte(self):
        """O campo 'descobrir' é o que separa a lista escrita à mão (reserva)
        da lista de verdade (catálogo)."""
        ns = _ns()
        self.assertEqual(
            ns["PROVEDORES_IA"]["openrouter"].get("descobrir"), "openrouter")

    def test_os_quatro_nomes_errados_sairam_da_LISTA(self):
        """Eles não existem no catálogo da OpenRouter. Deixá-los na reserva
        seria garantir 404 justamente quando o catálogo não responder.

        A verificação é sobre a LISTA, não sobre o arquivo: o comentário que
        conta este erro fica — é ele que impede alguém de digitar nomes de
        cabeça outra vez."""
        modelos = _ns()["PROVEDORES_IA"]["openrouter"]["modelos"]
        for inventado in ("deepseek/deepseek-chat-v3.1:free",
                          "meta-llama/llama-3.3-70b-instruct:free",
                          "google/gemini-2.0-flash-exp:free",
                          "qwen/qwen-2.5-72b-instruct:free"):
            self.assertNotIn(inventado, modelos, inventado)

    def test_a_reserva_NAO_tem_modelo_pago(self):
        """Cair na reserva não pode virar cobrança inesperada na conta dele."""
        ns = _ns()
        for m in ns["PROVEDORES_IA"]["openrouter"]["modelos"]:
            self.assertTrue(
                m == "openrouter/free" or m.endswith(":free"), m)

    def test_a_fila_E_o_botao_pedem_a_MESMA_funcao(self):
        """A duplicação já custou caro uma vez: a fila filtrava os modelos da
        IA local pelos instalados e o botão de testar tentava a lista fixa,
        dando quatro 404 num Mac com o Ollama de pé."""
        fonte = fonte_do_arquivo()
        self.assertGreaterEqual(fonte.count("modelos_do_provedor("), 3)


class TestOResumoPegaOErroQueMaisDiz(unittest.TestCase):

    def test_402_ganha_de_404(self):
        """Saldo é fato sobre a conta dele, acionável. Nome de modelo errado é
        problema meu, e ele não tem como resolver."""
        e = _ns()["erro_mais_informativo"]
        escolhido = e([Exception("HTTP 404: a"),
                       Exception('HTTP 402: Insufficient credits'),
                       Exception("HTTP 404: b")])
        self.assertIn("402", str(escolhido))

    def test_401_ganha_de_404(self):
        e = _ns()["erro_mais_informativo"]
        self.assertIn("401", str(e([Exception("HTTP 404: x"),
                                    Exception("HTTP 401: unauthorized")])))

    def test_sem_erro_nenhum_devolve_None(self):
        self.assertIsNone(_ns()["erro_mais_informativo"]([]))

    def test_o_402_da_openrouter_vira_frase_em_portugues(self):
        """A resposta dela é 'Insufficient credits. This account never
        purchased credits' — e nenhum dos padrões antigos casava com isso, então
        o texto cru vazava para o log em inglês."""
        d = _ns()["diagnostico_de_provedor"]
        frase = d(Exception('HTTP 402: {"error":{"message":"Insufficient '
                            'credits. This account never purchased credits."}}'))
        self.assertIn("SEM CRÉDITO", frase.upper())
        self.assertIn("gratuitos", frase)


if __name__ == "__main__":
    unittest.main()
