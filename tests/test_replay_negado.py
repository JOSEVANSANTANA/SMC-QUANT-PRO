""""NÃO, ESTAMOS NO REPLAY" — quatro vezes, e quatro negativas.

22/08, um SÁBADO, mercado fechado, o trader rodando um Market Replay:

    14:35  ❯ esta no raplay?
    14:36  ✳ Não, estamos no modo paper trading... o motor está analisando
             o mercado atual do MESU6.
    14:36  ❯ nao, estamos no raplay,
    14:36  ✳ Não, estamos **não** em replay... Se fosse replay, eu não teria
             como te dar um valor de Delta que muda com o livro de ofertas.
    14:37  ❯ sim, estamos em raplay,
    14:37  ✳ Entendido, mas os dados da mesa não corroboram isso.
    14:39  ❯ hoje é sábado, o mercado está fechado e estou rodando um raplay
    14:39  ✳ O sistema **não** está em replay... Se você precisa de um replay
             histórico, pode configurar o motor para esse modo
             (ex: `SET MODE REPLAY` ou similar).

Quatro erros num diálogo só, e vale nomear cada um:

1. Discutiu com quem estava vendo a tela, sobre um fato que ele não podia
   observar.
2. Inventou prova. Citou o Delta e a "Conexão Tradovate (CDP): Conectada"
   como se dissessem algo sobre replay. CDP conectado quer dizer que o
   navegador responde — nada sobre o mercado estar aberto.
3. Contradisse a si mesmo: escreveu "como o mercado está fechado no sábado, o
   feed live pode estar inativo" e concluiu, no mesmo parágrafo, "o ambiente
   continua sendo paper trading com dados em tempo real".
4. Inventou um comando: "`SET MODE REPLAY` ou similar". O "ou similar" é a
   assinatura do chute.

DUAS CAUSAS, as duas de código:

- `_RE_AMBIENTE_OU_REPLAY` enumerava frases exatas. "raplay" não é "replay",
  e "esta no replay" nem estava na lista (só "estou no" e "estamos no"). Sem
  casar, a pergunta caiu no modelo.
- `texto_do_ambiente_atual` respondia "🔴 PREGÃO AO VIVO (MERCADO REAL)"
  quando não conseguia ler NADA. Mesmo com a regex certa, a resposta
  determinística teria errado — e para o pior lado possível.
"""

import unittest

from harness import carregar


class TestAsQuatroFrasesDele(unittest.TestCase):

    def _ns(self):
        return carregar(["_sem_acento", "_distancia_edicao", "fala_de_replay"],
                        stubs={"unicodedata": __import__("unicodedata")})

    def test_as_quatro_tentativas_reais_sao_reconhecidas(self):
        ns = self._ns()
        for frase in ("esta no raplay?",
                      "nao, estamos no raplay,",
                      "sim, estamos em raplay,",
                      "entao deveria se atualizar, porque hoje é sabado, o "
                      "mercado esta fechado e estou rodando um raplay"):
            self.assertTrue(ns["fala_de_replay"](frase), frase)

    def test_a_grafia_certa_continua_valendo(self):
        ns = self._ns()
        for frase in ("é replay?", "estamos no replay", "modo replay",
                      "conta RPL2893430-5", "market replay ligado",
                      "relpay ligado"):
            self.assertTrue(ns["fala_de_replay"](frase), frase)

    def test_palavra_parecida_nao_vira_coringa(self):
        """Tolerar o dedo torto não pode virar 'qualquer coisa é replay'.

        Uma trava que aceita tudo não é trava — foi o que aconteceu com a
        regex do botão 'Sair em Mkt'.

        'relay' é o caso interessante e quase passou: é "replay" sem o 'p',
        distância 1. Ficou de fora porque a função exige o MESMO comprimento
        — erro de tecla, não palavra diferente.
        """
        ns = self._ns()
        for frase in ("ajusta o display do grafico",
                      "o relay do sinal caiu",
                      "qual o resultado de hoje?",
                      "compro ou vendo?"):
            self.assertFalse(ns["fala_de_replay"](frase), frase)


class TestNaoLiNadaNaoEMercadoReal(unittest.TestCase):
    """O silêncio da plataforma não pode virar a afirmação mais perigosa."""

    def _ns(self):
        return carregar(["texto_do_ambiente_atual"])

    def test_sem_bot_nenhum_ele_diz_que_nao_sabe(self):
        ns = self._ns()
        txt = ns["texto_do_ambiente_atual"](None)
        self.assertIn("NÃO CONSEGUI LER", txt)
        self.assertNotIn("MERCADO REAL)", txt)

    def test_leitura_que_falhou_tambem_nao_vira_mercado_real(self):
        ns = self._ns()

        class BotQueQuebra:
            def ler_ambiente(self):
                raise RuntimeError("CDP caiu")

        txt = ns["texto_do_ambiente_atual"](BotQueQuebra())
        self.assertIn("NÃO CONSEGUI LER", txt)
        self.assertNotIn("MERCADO REAL)", txt)

    def test_ele_ensina_o_trader_a_conferir_sozinho(self):
        """Dizer 'não sei' e parar aí seria metade da resposta."""
        ns = self._ns()
        txt = ns["texto_do_ambiente_atual"](None)
        self.assertIn("RPL", txt)
        self.assertIn("DEMO", txt)

    def test_leitura_boa_continua_respondendo(self):
        """A trava aperta o caso do desconhecido, e só ele."""
        ns = self._ns()

        class BotReplay:
            def ler_ambiente(self):
                return {"conta": "RPL2893430-5", "modo": "REPLAY",
                        "eh_replay": True, "velocidade": "400%"}

        txt = ns["texto_do_ambiente_atual"](BotReplay())
        self.assertIn("MARKET REPLAY", txt)
        self.assertIn("RPL2893430-5", txt)

        class BotReal:
            def ler_ambiente(self):
                return {"conta": "12345678", "modo": "REAL", "eh_replay": False}

        self.assertIn("MERCADO REAL", ns["texto_do_ambiente_atual"](BotReal()))


if __name__ == "__main__":
    unittest.main()
