"""A ordem inteira numa submissão só — e o campo certo, conferido.

19/08, print dele do 'Chamado do pedido' com o painel de ATMs aberto:

    PREÇO         29542.00      <- o MESU6 estava em 7732.50
    OBTER LUCRO   80 ticks  ->  29562.00
    STOP LOSS     40 ticks  ->  29532.00

Os três números são coerentes ENTRE SI (80 e 40 ticks de 0,25 a partir de
29542), e nenhum deles tem relação com o gráfico. Ou seja: o ticket estava
sendo preenchido, e no lugar errado.

DOIS DEFEITOS, E O SEGUNDO É O QUE ASSUSTA
------------------------------------------
1) `definir_campo_ticket` mirava por POSIÇÃO: "o primeiro input do painel da
   esquerda, sem placeholder, cujo valor pareça número". Isso funciona com o
   ticket sozinho na tela. Com o painel de ATMs ABERTO — que é como ele opera
   — a mesma coluna passa a ter OBTER LUCRO, STOP LOSS, ACIONAR LUCROS e
   FREQUÊNCIA, todos numéricos e todos sem placeholder.

2) A função devolvia 'OK' por ter ENCONTRADO um input, nunca por ter CONFERIDO
   que o número entrou onde devia. Escrever no campo errado e reportar sucesso
   é a pior combinação possível quando o passo seguinte é clicar em Enviar.

E O CAMINHO NOVO, QUE É IDEIA DELE
----------------------------------
"ela tem opcao de colocar a entrada com ordem ATMs marcados em tiks, assim, a
ordem ja entra com stop e gains e quando acionada a saida tanto de stop quanto
de gain, ela cancela as pendentes".

Está certo, e é melhor que o que estava lá. O caminho antigo mandava TRÊS
ordens separadas, e entre uma e outra o painel vira comprovante e precisa
voltar ao formulário. Toda vez que essa volta falha existe uma janela em que a
ENTRADA está no mercado e a PROTEÇÃO não — o pior estado que este programa
pode produzir. Com a ATM é uma submissão só, e o OCO é da corretora.
"""

import unittest

from harness import RAIZ, carregar, fonte_do_arquivo  # noqa: F401
import os
import sys

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import tradovate_auto as tv


class TestLerNumeroDoCampo(unittest.TestCase):
    """A Tradovate reescreve o número no campo com a formatação da localidade,
    e o campo é lido de volta como TEXTO. Comparar '7732.5' com '7,732.50' como
    string diria que o valor não entrou — e o robô abortaria uma ordem certa."""

    def test_o_mesmo_numero_em_tres_formatos(self):
        for texto in ("29542", "29542.00", "29,542.00", "29.542,00"):
            self.assertEqual(tv._como_numero(texto), 29542.0, texto)

    def test_decimal_com_virgula_continua_decimal(self):
        self.assertEqual(tv._como_numero("7732,50"), 7732.5)
        self.assertEqual(tv._como_numero("1,5"), 1.5)

    def test_milhar_com_virgula_e_tres_casas(self):
        self.assertEqual(tv._como_numero("1,500"), 1500.0)

    def test_texto_que_nao_e_numero_devolve_None(self):
        for t in ("", None, "Selecionar", "abc", "--"):
            self.assertIsNone(tv._como_numero(t), repr(t))

    def test_valores_batem_compara_como_NUMERO(self):
        self.assertTrue(tv.valores_batem(7732.5, "7,732.50"))
        self.assertTrue(tv.valores_batem(40, "40"))
        self.assertFalse(tv.valores_batem(40, "41"))

    def test_tolerancia_existe_para_arredondamento_de_tick(self):
        """A plataforma arredonda para o tick dela. Recusar a ordem por causa
        disso seria recusar por estar certa."""
        self.assertTrue(tv.valores_batem(7732.60, "7732.50", tolerancia=0.125))
        self.assertFalse(tv.valores_batem(7735.00, "7732.50", tolerancia=0.125))

    def test_sem_tolerancia_a_igualdade_e_exata(self):
        self.assertFalse(tv.valores_batem(7732.60, "7732.50"))


class TestDoCenarioSMCParaOsTicksDaATM(unittest.TestCase):
    """A ATM não recebe preço de stop: recebe DISTÂNCIA em ticks a partir do
    preenchimento. Esta conta é a que decide onde fica a proteção de uma ordem
    que vai ser enviada sem ninguém olhando."""

    def test_a_conta_do_print_dele(self):
        """MES, tick 0,25: 40 ticks de stop e 80 de alvo — exatamente os
        números que apareciam na tela."""
        t_stop, t_alvo, erro = tv.plano_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25)
        self.assertIsNone(erro)
        self.assertEqual((t_stop, t_alvo), (40, 80))

    def test_venda_mede_a_distancia_do_mesmo_jeito(self):
        t_stop, t_alvo, erro = tv.plano_atm("SELL", 7732.50, 7742.50, 7712.50, 0.25)
        self.assertIsNone(erro)
        self.assertEqual((t_stop, t_alvo), (40, 80))

    def test_COMPRA_com_stop_ACIMA_da_entrada_e_recusada(self):
        """A ATM é cega: ela mede distância e não sabe de que lado o stop
        está. Um BUY com stop acima da entrada viraria, na Tradovate, um stop
        de N ticks ABAIXO — ela inverteria em silêncio a proteção que o
        cenário pedia."""
        t_stop, t_alvo, erro = tv.plano_atm("BUY", 7732.50, 7742.50, 7752.50, 0.25)
        self.assertIsNone(t_stop)
        self.assertIn("incoerente", erro)

    def test_VENDA_com_alvo_ACIMA_da_entrada_e_recusada(self):
        _, _, erro = tv.plano_atm("SELL", 7732.50, 7742.50, 7752.50, 0.25)
        self.assertIn("incoerente", erro)

    def test_distancia_zero_nao_vira_ordem(self):
        """ATM com zero tick é ordem sem proteção nenhuma. 'None' aqui
        significa NÃO ENVIE, nunca 'use zero'."""
        _, _, erro = tv.plano_atm("BUY", 7732.50, 7732.50, 7752.50, 0.25)
        self.assertIsNotNone(erro)

    def test_tick_invalido_nao_vira_ordem(self):
        for tick in (0, None, -1, "abc"):
            _, _, erro = tv.plano_atm("BUY", 7732.5, 7722.5, 7752.5, tick)
            self.assertIsNotNone(erro, repr(tick))

    def test_preco_nao_numerico_nao_vira_ordem(self):
        _, _, erro = tv.plano_atm("BUY", None, 7722.5, 7752.5, 0.25)
        self.assertIn("números", erro)

    def test_ticks_entre_arredonda_para_o_inteiro_mais_proximo(self):
        self.assertEqual(tv.ticks_entre(100.0, 99.0, 0.25), 4)
        self.assertEqual(tv.ticks_entre(100.0, 100.30, 0.25), 1)
        self.assertIsNone(tv.ticks_entre(100.0, 100.0, 0.25))

    def test_o_tick_de_cada_ativo_vem_da_tabela_do_app(self):
        """A conta em ticks só existe se eu souber o tick do contrato. Chutar
        um tick seria inventar a distância do stop."""
        ns = carregar(["tick_do_ativo", "TICK_MINIMO"])
        self.assertEqual(ns["tick_do_ativo"]("MESU6"), 0.25)
        self.assertEqual(ns["tick_do_ativo"]("MYMZ5"), 1.0)
        self.assertIsNone(ns["tick_do_ativo"]("PAPELDESCONHECIDO"))


class _BotFalso(tv.TradovateAuto):
    """Um TradovateAuto que nunca fala com Chrome nenhum.

    Guarda o JS pedido e devolve o que o teste mandar — é assim que dá para
    conferir a lógica de decisão sem plataforma aberta."""

    def __init__(self, respostas=None):
        self.log_linhas = []
        self.log = self.log_linhas.append
        self.js = []
        self.cliques = []
        self.respostas = respostas or {}
        self.campos = {}

    def avaliar_js(self, expressao):
        self.js.append(expressao)
        for chave, valor in self.respostas.items():
            if chave in expressao:
                return valor
        return "{}"

    def clicar_pagina(self, x, y, dry_run=False):
        self.cliques.append((x, y))

    def _garantir_formulario(self, tentativas=3):
        return self.respostas.get("_formulario", True)

    def localizar(self, palavra):
        if palavra in self.respostas.get("_sem_botao", ()):
            return None
        return {"x": 10, "y": 20}

    def _achar_por_texto(self, palavras):
        return {p: {"x": 1, "y": 2} for p in palavras}

    def _selecionar_tipo(self, tipo, pausa=0.45, dry_run=False):
        return True

    # o que os testes observam
    def _campo_por_rotulo(self, rotulo, valor=None, ocorrencia=0, tolerancia=18):
        falhos = self.respostas.get("_campos_que_falham", ())
        if rotulo in falhos:
            return {"estado": "CAMPO_NAO_ACHADO"}
        errados = self.respostas.get("_campos_que_mentem", ())
        if valor is not None:
            self.campos[rotulo] = valor
        lido = self.campos.get(rotulo, "")
        if rotulo in errados:
            lido = "999999"
        if rotulo == "EXIBIR EM":
            lido = self.respostas.get("_exibir_em", "Ticks")
        return {"estado": "OK", "valor": str(lido), "x": 5, "y": 6}


class TestAOrdemSoSAIComTudoConferido(unittest.TestCase):
    """A regra de ouro: nada é enviado antes de todos os campos terem sido
    escritos E conferidos por leitura de volta. Com qualquer um falhando, o
    pior resultado passa a ser 'não operou' — que é um resultado com o qual dá
    para viver."""

    def _bot(self, **respostas):
        return _BotFalso(respostas)

    def test_o_caminho_feliz_envia_uma_vez_e_leva_stop_e_alvo(self):
        bot = self._bot()
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["enviadas"], ["ENTRADA", "STOP", "ALVO"])
        self.assertEqual((r["ticks_stop"], r["ticks_alvo"]), (40, 80))
        self.assertFalse(r["exposto"])
        self.assertEqual(bot.campos["PREÇO"], 7732.50)
        self.assertEqual(bot.campos["QTD"], 2)
        self.assertEqual(bot.campos["OBTER LUCRO"], 80)
        self.assertEqual(bot.campos["STOP LOSS"], 40)

    def test_campo_de_preco_que_MENTE_aborta_antes_do_enviar(self):
        """Era isto que faltava: o campo dizia OK e o número estava noutro
        lugar."""
        bot = self._bot(_campos_que_mentem=("PREÇO",))
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertIn("PREÇO", r["erro"])
        self.assertFalse(r["exposto"], "nada foi enviado, então nada ficou exposto")

    def test_ATM_que_nao_grava_o_stop_NAO_manda_a_entrada(self):
        """Entrada sem proteção anexada é exatamente o que este caminho veio
        eliminar. Melhor não operar."""
        bot = self._bot(_campos_que_falham=("STOP LOSS",))
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertFalse(r["exposto"])
        self.assertEqual(sorted(r["faltando"]), ["ALVO", "ENTRADA", "STOP"])

    def test_cenario_incoerente_nem_chega_a_tocar_no_formulario(self):
        bot = self._bot()
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7742.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertIn("incoerente", r["erro"])
        self.assertEqual(bot.campos, {}, "não podia ter escrito nada")

    def test_sem_quantidade_nao_envia(self):
        bot = self._bot()
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=None, enviar=True)
        self.assertFalse(r["ok"])
        self.assertIn("quantidade", r["erro"])

    def test_modo_teste_preenche_e_NAO_clica_em_enviar(self):
        bot = self._bot()
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["enviadas"], ["PRE-VISUALIZACAO"])
        self.assertEqual(bot.campos["OBTER LUCRO"], 80)
        self.assertTrue(any("NÃO enviei" in l for l in bot.log_linhas))

    def test_formulario_ausente_nao_vira_ordem(self):
        bot = self._bot(_formulario=False)
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertIn("formulário", r["erro"])

    def test_sem_o_botao_ENVIAR_nada_e_dado_como_enviado(self):
        bot = self._bot(_sem_botao=("Enviar",))
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertFalse(r["exposto"])

    def test_EXIBIR_EM_fora_de_ticks_e_AVISADO(self):
        """Em 'Preço', o mesmo número 40 deixa de ser 40 ticks e vira o preço
        40. Não é detalhe de tela: é a diferença entre um stop de dez pontos e
        uma ordem sem sentido nenhum."""
        bot = self._bot(_exibir_em="Preço")
        bot._achar_por_texto = lambda p: {}          # nem o combo aparece
        bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                 qtd=2, enviar=True)
        self.assertTrue(any("EXIBIR EM" in l for l in bot.log_linhas))


class TestOAppUSAOCaminhoNovo(unittest.TestCase):
    """Método escrito e nunca chamado é o defeito de sempre."""

    def test_o_envio_do_app_tenta_a_ATM_primeiro(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_enviar_bracket(")
        bloco = fonte[i:i + 3500]
        self.assertIn("enviar_ordem_com_atm(", bloco)
        j = bloco.index("enviar_ordem_com_atm(")
        k = bloco.index("enviar_bracket_ticket(")
        self.assertLess(j, k, "o caminho das três ordens tem de ser a reserva")

    def test_a_reserva_so_entra_quando_NADA_foi_enviado(self):
        """Cair para o caminho antigo depois de a entrada já ter ido seria
        duplicar posição."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_enviar_bracket(")
        bloco = fonte[i:i + 3500]
        self.assertIn('not res.get("exposto")', bloco)

    def test_o_ativo_e_repassado_para_achar_o_tick(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_enviar_bracket(")
        self.assertIn("tick_do_ativo(", fonte[i:i + 1200])
        j = fonte.index("self._tv_enviar_bracket(")
        self.assertIn("ativo=", fonte[j:j + 400])


if __name__ == "__main__":
    unittest.main()
