"""O RASCUNHO DO MODELO NÃO É RESPOSTA PARA QUEM ESTÁ POSICIONADO.

22/08, 12:43. Pergunta dele: "É replay?". O que apareceu no chat da mesa:

    1.  **Analyze the user's question:** The user asks "É replay?" (Is it replay?).
    2.  **Consult the system instructions and context:**
        *   The system prompt defines me as JARVIS/TIGER 2.0...
        *   Let's re-read the "DIRETRIZES DE COMPORTAMENTO".
    3.  **Determine the answer:** ...

O filtro que existia procurava o CABEÇALHO ("Here's a thinking process:") e
este vazamento não tem cabeçalho nenhum — começa direto no passo 1. Ele
procurava a etiqueta, não a coisa.

E havia um defeito de projeto por baixo: o filtro tentava RESGATAR a resposta
de dentro do raciocínio, procurando a linha onde ela começaria por palavras
como "ordem" e "mesa" — que aparecem no meio da deliberação também. Isso é
palpite, e palpite no painel é o que este programa inteiro existe para não
fazer. Se o que sobrou é o rascunho, o certo é dizer que o modelo não
respondeu.
"""

import unittest

from harness import carregar


def _ns():
    return carregar(["_MARCAS_DE_RACIOCINIO", "_parece_raciocinio_interno",
                     "limpar_raciocinio_ia"])


VAZAMENTO_REAL = """1.  **Analyze the user's question:** The user asks "É replay?" (Is it replay?).
2.  **Consult the system instructions and context:**
    *   The system prompt defines me as JARVIS/TIGER 2.0, an AI assistant.
    *   It specifies the primary asset: MES / MESU6.
    *   It provides real-time table data: CVD Delta: +1,420 (Buyer Strong).
3.  **Determine the answer:**
    *   Is it replay? The system prompt says: "CONTA 'TESTES SMC QUANT'".
    *   Let's re-read the "DIRETRIZES DE COMPORTAMENTO".
    *   I need to be honest. The data shows "0 operations closed in the cycle".
"""

VAZAMENTO_COM_CABECALHO = """Here's a thinking process:

1. **Analyze User Input:**
   - User says: "NAO FOI EXECULTADA"
   - Context: Earlier I sent a buy order for MESU6 60 ctr @ 7542.5.
2. **Check Rules/Constraints:**
   - Rule 8: "NUNCA invente número."
   - Let me be careful not to over-claim.
3. **Draft Response:**
   - "Compreendido. A ordem ficou pendente."
"""


class TestOQueVazouNoPregao(unittest.TestCase):

    def test_o_vazamento_sem_cabecalho_nao_chega_ao_trader(self):
        """O caso das 12:43, que passava inteiro pelo filtro antigo."""
        ns = _ns()
        saida = ns["limpar_raciocinio_ia"](VAZAMENTO_REAL)
        self.assertNotIn("Analyze the user's question", saida)
        self.assertNotIn("Let's re-read", saida)
        self.assertIn("rascunho do raciocínio", saida)

    def test_o_vazamento_com_cabecalho_tambem_nao(self):
        """O das 11:57 e 11:58, quando ele digitou 'NAO FOI EXECULTADA'."""
        ns = _ns()
        saida = ns["limpar_raciocinio_ia"](VAZAMENTO_COM_CABECALHO)
        self.assertNotIn("Check Rules", saida)
        self.assertNotIn("Draft Response", saida)

    def test_o_aviso_diz_o_que_fazer(self):
        """Erro sem saída é erro que ele lê e ignora."""
        ns = _ns()
        saida = ns["limpar_raciocinio_ia"](VAZAMENTO_REAL)
        self.assertIn("Pergunte de novo", saida)


class TestRespostaBoaContinuaPassando(unittest.TestCase):
    """O custo dos dois erros é diferente, mas nenhum é zero.

    Engolir resposta boa gera um 'pergunte de novo' chato. Se acontecer com
    frequência, ele desliga o filtro — e aí volta o problema inteiro.
    """

    def test_analise_de_mesa_em_portugues_passa_intacta(self):
        ns = _ns()
        boa = ("Delta comprador em +1.420 no MESU6. O preço caiu e o delta "
               "continua comprador: isso é absorção passiva no Order Block "
               "de 7542, não agressão vendedora. Enquanto 7536 segurar, a "
               "leitura é de continuação para 7566. Se perder, o cenário "
               "vira e o alvo passa a ser a liquidez de 7515.")
        self.assertEqual(ns["limpar_raciocinio_ia"](boa), boa)

    def test_resposta_curta_nunca_e_confundida_com_rascunho(self):
        ns = _ns()
        for curta in ("Sim, é replay: conta RPL2893430-5, velocidade 400%.",
                      "Não tenho esse dado na mesa.",
                      "Order Block é a última vela contrária antes do "
                      "deslocamento que rompeu a estrutura."):
            self.assertEqual(ns["limpar_raciocinio_ia"](curta), curta)

    def test_uma_marca_sozinha_nao_condena_o_texto(self):
        """'Let me check' citado dentro de uma explicação legítima.

        A função exige DUAS marcas independentes justamente para isto: uma
        frase em inglês no meio de uma resposta boa não é deliberação.
        """
        ns = _ns()
        texto = ("O modelo respondeu 'Let me check the order flow' antes de "
                 "concluir, e é por isso que a resposta veio truncada. "
                 "Isso acontece quando o provedor corta o texto no limite de "
                 "tokens. A leitura da mesa continua válida: delta comprador "
                 "em +1.420, preço testando o Order Block de 7542, e o alvo "
                 "segue em 7566 enquanto 7536 segurar o teste.")
        self.assertEqual(ns["limpar_raciocinio_ia"](texto), texto)

    def test_texto_vazio_nao_quebra(self):
        ns = _ns()
        self.assertEqual(ns["limpar_raciocinio_ia"](""), "")
        self.assertEqual(ns["limpar_raciocinio_ia"](None), "")


if __name__ == "__main__":
    unittest.main()
