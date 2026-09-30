"""Aprendizado que ninguém vê é indistinguível de aprendizado que não existe.

19/08, ele: "nao aprende com a web, nao aprende com as operacoes... estou
seriamente considerando desinstalar".

Fui conferir esperando encontrar o mecanismo desligado. Ele estava ligado, e
funcionando: `aprendizado_por_padrao` lê o histórico real e `ajuste_por_
aprendizado` corrige a probabilidade com o que a conta DELE já viveu. O
problema era outro, e mais burro que o defeito: os dois DESCARTAM em silêncio
todo padrão com menos de 3 ou 4 amostras. Do lado de fora, "ainda não tenho
dados suficientes" e "isto não funciona" são a mesma tela — nenhuma.

E havia o agravante que fecha a conta: quem alimenta esse histórico é o motor,
quando um cenário dele resolve. Com o motor morrendo em TODO ciclo (o
`name 'analise' is not defined` da v2.43.0), nenhum cenário chegava ao fim e
nada era gravado. O aprendizado ficou congelado exatamente no período em que
ele o achou burro. A queixa dele estava certa; a causa é que era outra.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _op(resultado, *confluencias):
    return {"resultado": resultado, "hora": "10",
            "confluencias": list(confluencias)}


class TestOProgressoDoAprendizado(unittest.TestCase):

    def _ns(self, db):
        return carregar(["progresso_do_aprendizado", "resumo_do_aprendizado",
                         "_normalizar_padrao"],
                        stubs={"carregar_performance": lambda: list(db)})

    def test_padrao_com_amostra_suficiente_JA_conta(self):
        ns = self._ns([_op("WIN", "Order Block"), _op("WIN", "Order Block"),
                       _op("LOSS", "Order Block")])
        prontos, faltando, total = ns["progresso_do_aprendizado"](minimo=3)
        self.assertEqual(total, 3)
        self.assertEqual(len(prontos), 1)
        rot, v, n, pct = prontos[0]
        self.assertEqual((v, n), (2, 3))
        self.assertAlmostEqual(pct, 66.7, places=0)
        self.assertEqual(faltando, [])

    def test_padrao_com_pouca_amostra_APARECE_com_o_que_falta(self):
        """Era este o silêncio: o padrão existia, estava sendo contado, e não
        aparecia em lugar nenhum até cruzar o limiar."""
        ns = self._ns([_op("WIN", "FVG"), _op("LOSS", "FVG")])
        prontos, faltando, _ = ns["progresso_do_aprendizado"](minimo=3)
        self.assertEqual(prontos, [])
        self.assertEqual(len(faltando), 1)
        rot, n, faltam = faltando[0]
        self.assertEqual((n, faltam), (2, 1))

    def test_o_que_esta_MAIS_PERTO_de_virar_regra_vem_primeiro(self):
        ns = self._ns([_op("WIN", "Order Block"), _op("WIN", "FVG"),
                       _op("LOSS", "FVG")])
        _, faltando, _ = ns["progresso_do_aprendizado"](minimo=4)
        self.assertEqual([f[0] for f in faltando][0],
                         ns["_normalizar_padrao"]("FVG"),
                         "o que tem mais amostra é o que falta menos")

    def test_a_mesma_confluencia_repetida_na_operacao_conta_UMA_vez(self):
        """Senão uma leitura tagarela, que escreve 'order block' três vezes na
        mesma análise, viraria sozinha um padrão 'aprendido'."""
        ns = self._ns([_op("WIN", "Order Block", "order block", "ORDER BLOCK")])
        _, faltando, _ = ns["progresso_do_aprendizado"](minimo=3)
        self.assertEqual(faltando[0][1], 1)

    def test_historico_vazio_nao_quebra(self):
        ns = self._ns([])
        self.assertEqual(ns["progresso_do_aprendizado"](), ([], [], 0))


class TestOResumoNUNCAFicaMudo(unittest.TestCase):
    """Silêncio ele lê como defeito — e leu. 'Ainda não aprendi nada' é uma
    resposta ruim de ouvir e infinitamente melhor que nenhuma."""

    def _ns(self, db):
        return carregar(["progresso_do_aprendizado", "resumo_do_aprendizado",
                         "_normalizar_padrao"],
                        stubs={"carregar_performance": lambda: list(db)})

    def test_sem_historico_ele_DIZ_que_nao_aprendeu_e_por_que(self):
        texto = self._ns([])["resumo_do_aprendizado"]()
        self.assertTrue(texto.strip())
        self.assertIn("Ainda não aprendi nada", texto)
        self.assertIn("amostra", texto.lower())

    def test_com_historico_ele_mostra_NUMERO(self):
        ns = self._ns([_op("WIN", "Order Block"), _op("WIN", "Order Block"),
                       _op("LOSS", "Order Block"), _op("WIN", "FVG")])
        texto = ns["resumo_do_aprendizado"]()
        self.assertIn("4 cenário(s) fechado(s)", texto)
        self.assertIn("JÁ PESA NA MINHA DECISÃO", texto)
        self.assertIn("AINDA JUNTANDO AMOSTRA", texto)

    def test_nunca_devolve_vazio(self):
        for db in ([], [_op("WIN", "X")], [_op("LOSS")], [_op("WIN", "A")] * 9):
            self.assertTrue(self._ns(db)["resumo_do_aprendizado"]().strip(),
                            repr(db[:1]))


class TestElaRESPONDEAPerguntaSemInventar(unittest.TestCase):
    """'O que você aprendeu comigo?' ia para o modelo, que não tem como saber
    e responde bonito. Numa ferramenta que promete aprender com as operações
    dele, aprendizado inventado é a pior mentira possível."""

    def _ns(self):
        return carregar(["pergunta_sobre_aprendizado", "_RE_APRENDIZADO",
                         "_norm_busca", "_sem_acento"])

    def test_as_formas_em_que_ele_pergunta(self):
        ns = self._ns()
        for t in ("o que voce aprendeu comigo?",
                  "o que você já aprendeu com as minhas operações",
                  "você aprendeu alguma coisa com os meus trades?",
                  "o que voce aprendeu?",
                  "qual é o seu aprendizado ate agora",
                  "voce melhorou com o meu historico?",
                  "quanto voce aprendeu comigo"):
            self.assertTrue(ns["pergunta_sobre_aprendizado"](t), t)

    def test_a_frase_EXATA_que_ele_escreveu_em_19_08(self):
        ns = self._ns()
        self.assertTrue(ns["pergunta_sobre_aprendizado"](
            "nao aprende com a web, nao aprende com as operacoes"))

    def test_pedir_para_APRENDER_metodologia_nao_e_a_mesma_coisa(self):
        """'Quero aprender a operar' é pergunta de metodologia e tem de
        continuar caindo na base de conhecimento."""
        ns = self._ns()
        for t in ("me ensina a aprender smc", "quero aprender a operar",
                  "o que é aprendizado de maquina",
                  "como faço para aprender order block",
                  "me ajuda a melhorar minha entrada",
                  "boa tarde", "o que é ote", "liga o motor",
                  "o que voce pode fazer"):
            self.assertFalse(ns["pergunta_sobre_aprendizado"](t), t)

    def test_texto_vazio_ou_None_nao_quebra(self):
        ns = self._ns()
        for t in ("", None, "   "):
            self.assertFalse(ns["pergunta_sobre_aprendizado"](t), repr(t))


class TestOndeIssoAPARECE(unittest.TestCase):
    """Função escrita e nunca chamada é exatamente o defeito que eu vim
    consertar. Não adianta trocá-lo por outro do mesmo formato."""

    def _fonte(self):
        return fonte_do_arquivo()

    def test_o_motor_diz_na_PRIMEIRA_linha_o_que_aprendeu(self):
        """'Módulo de aprendizado ativado' é propaganda; o que informa é o
        número. Sem ele, aprendizado zerado tem a mesma cara de aprendizado
        funcionando."""
        fonte = self._fonte()
        i = fonte.index("ROBÔ SMC INICIADO COM MÓDULO DE APRENDIZADO")
        self.assertIn("resumo_do_aprendizado()", fonte[i:i + 700])

    def test_entra_no_STATUS_da_conversa(self):
        fonte = self._fonte()
        i = fonte.index("def _chat_status_texto(")
        self.assertIn("resumo_do_aprendizado()", fonte[i:i + 3000])

    def test_o_prompt_recebe_o_que_AINDA_NAO_e_regra(self):
        """Sem isso o modelo não tem como responder 'o que você aprendeu
        comigo' sem inventar."""
        fonte = self._fonte()
        i = fonte.index("def compilar_memoria_prompt(")
        bloco = fonte[i:fonte.index("def ", i + 10)]
        self.assertIn("progresso_do_aprendizado()", bloco)
        self.assertIn("NÃO deve tratá-los como aprendidos", bloco)

    def test_a_pergunta_direta_e_respondida_SEM_MODELO(self):
        """Sem cota, sem internet e sem modelo: é dado do disco dela."""
        fonte = self._fonte()
        i = fonte.index("def responder_offline(")
        bloco = fonte[i:i + 2500]
        self.assertIn("pergunta_sobre_aprendizado(pergunta)", bloco)
        self.assertIn("resumo_do_aprendizado()", bloco)


if __name__ == "__main__":
    unittest.main()
