""""SÓ ESTÁ LENDO A TRADOVATE."

A RECLAMAÇÃO
------------
    ⚠️ Erro de Visualização
    Janela 'MGC1! 4.704,5 ▲ +0.21% Sem nome - Google Chrome' não encontrada.
    Verifique se a corretora está aberta. Ciclo pulado.

Essa era uma janela do TRADINGVIEW, aberta, na tela, com o gráfico rodando. E
o programa dizia que não existia — enquanto lia a Tradovate no mesmo ciclo,
sem falhar uma vez.

O MOTIVO, INTEIRO, ESTÁ NO PRÓPRIO TEXTO DO ERRO
-------------------------------------------------
O título tem O PREÇO DENTRO: "4.704,5 ▲ +0.21%". O TradingView escreve a
cotação na aba, então o título muda A CADA TIQUE. O que ficou gravado na lista
de janelas monitoradas foi a fotografia de um instante — um título que nunca
mais existiu. A busca era por igualdade (e, falhando, por "o salvo está dentro
do aberto"): as duas perguntam por um texto que já morreu.

E é por isso que SÓ a Tradovate funcionava. O título dela é
"Tradovate - SMC QUANT PRO" o pregão inteiro. Não havia preferência por
corretora nenhuma no código — era o único título parado.

O CONSERTO, E O QUE ELE NÃO PODE FAZER
---------------------------------------
Compara o que NÃO muda: sem números, sem setas, sem porcentagem. Sobra
"mgc1 sem nome google chrome", e isso casa amanhã também.

A trava é tão importante quanto o conserto: o pedaço que identifica o ATIVO
(MGC1, MNQ1, MESU6 — palavra com dígito) é OBRIGATÓRIO. Se a janela do ouro
não estiver aberta, o programa NÃO pode "quase casar" com a do índice e
analisar o gráfico errado achando que é o certo. Aí ele recusa — e diz que
recusou, listando o que estava aberto.
"""

import os
import sys
import unittest

from harness import RAIZ, funcao_inteira

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import plataforma as P          # noqa: E402


def _fonte(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


# O título do print, letra por letra.
SALVO_MGC = "MGC1! 4.704,5 ▲ +0.21% Sem nome - Google Chrome"
# A mesma janela, dois tiques depois.
AGORA_MGC = "MGC1! 4.702,0 ▼ -0.05% Sem nome - Google Chrome"
AGORA_MNQ = "MNQ1! 24.310,25 ▲ +0.44% Sem nome - Google Chrome"
TRADOVATE = "Tradovate - SMC QUANT PRO"


class TestOTituloQueMudaSozinho(unittest.TestCase):

    def test_o_esqueleto_joga_fora_preco_seta_e_porcentagem(self):
        self.assertEqual(P.esqueleto_do_titulo(SALVO_MGC),
                         "mgc1 sem nome google chrome")

    def test_dois_tiques_diferentes_dao_o_MESMO_esqueleto(self):
        """É esta igualdade que faz o casamento durar mais que um segundo."""
        self.assertEqual(P.esqueleto_do_titulo(SALVO_MGC),
                         P.esqueleto_do_titulo(AGORA_MGC))

    def test_o_codigo_do_ativo_SOBREVIVE(self):
        """Tirar todo dígito mataria MGC1 e MNQ1 junto com o preço — e aí as
        duas janelas ficariam idênticas."""
        self.assertIn("mgc1", P.esqueleto_do_titulo(SALVO_MGC))
        self.assertIn("mnq1", P.esqueleto_do_titulo(AGORA_MNQ))

    def test_contador_de_mensagens_nao_conta(self):
        self.assertEqual(P.esqueleto_do_titulo("(78) WhatsApp"), "whatsapp")

    def test_a_numeracao_que_o_PROPRIO_programa_poe_nao_conta(self):
        """'Google Chrome — janela 2 (1512x982)' é enfeite nosso, não nome de
        janela. Se virasse parte do título exigido, o rótulo salvo hoje não
        casaria depois de o trader redimensionar a janela."""
        self.assertEqual(
            P.esqueleto_do_titulo("Google Chrome — janela 2 (1512x982)"),
            "google chrome")

    def test_titulo_vazio_nao_levanta(self):
        self.assertEqual(P.esqueleto_do_titulo(None), "")
        self.assertEqual(P.esqueleto_do_titulo(""), "")


class TestOCasoDoPrint(unittest.TestCase):
    """A reclamação inteira, em testes."""

    def test_a_janela_do_TradingView_e_encontrada_com_o_preco_mudado(self):
        i = P.melhor_janela_por_titulo(SALVO_MGC,
                                       [TRADOVATE, AGORA_MGC, AGORA_MNQ])
        self.assertEqual(i, 1)

    def test_a_Tradovate_continua_achando_do_mesmo_jeito(self):
        """Consertar as outras não pode quebrar a única que funcionava."""
        i = P.melhor_janela_por_titulo(TRADOVATE,
                                       [AGORA_MNQ, TRADOVATE, AGORA_MGC])
        self.assertEqual(i, 1)

    def test_TRES_janelas_escolhidas_TRES_janelas_achadas(self):
        """'Preciso certificar de que ocorra leitura em TODAS as janelas que eu
        selecionar.' Três títulos salvos com preço velho, três achados."""
        abertas = [TRADOVATE, AGORA_MGC, AGORA_MNQ]
        salvos = [TRADOVATE, SALVO_MGC,
                  "MNQ1! 24.180,00 ▼ -0.12% Sem nome - Google Chrome"]
        achados = [P.melhor_janela_por_titulo(s, abertas) for s in salvos]
        self.assertEqual(achados, [0, 1, 2])


class TestNuncaAnalisarOGraficoErrado(unittest.TestCase):
    """Errar a janela é pior do que perder o ciclo: seria ler o gráfico do
    ouro e mandar ordem pensando no índice."""

    def test_sem_a_janela_do_ativo_ele_RECUSA(self):
        """Só MNQ e Tradovate abertas, o salvo é do MGC: o parecido não serve.
        'mgc1' não está em lugar nenhum, então a resposta é não achei."""
        self.assertIsNone(
            P.melhor_janela_por_titulo(SALVO_MGC, [TRADOVATE, AGORA_MNQ]))

    def test_o_codigo_do_ativo_e_OBRIGATORIO_mesmo_com_o_resto_todo_igual(self):
        """'Sem nome - Google Chrome' é igual nas duas. Quatro das cinco
        palavras batem — e ainda assim não é a janela."""
        self.assertIsNone(P.melhor_janela_por_titulo(SALVO_MGC, [AGORA_MNQ]))

    def test_duas_janelas_igualmente_boas_nao_viram_chute(self):
        i = P.melhor_janela_por_titulo(
            "Profit — Book",
            ["Profit — Book de Ofertas", "Profit — Book Lateral"])
        self.assertIsNone(i)

    def test_coincidencia_solta_de_uma_palavra_nao_basta(self):
        self.assertIsNone(
            P.melhor_janela_por_titulo("Tradovate - SMC QUANT PRO",
                                       ["Documento sem nome - Word"]))

    def test_lista_vazia_e_alvo_vazio(self):
        self.assertIsNone(P.melhor_janela_por_titulo(SALVO_MGC, []))
        self.assertIsNone(P.melhor_janela_por_titulo("", [TRADOVATE]))
        self.assertIsNone(P.melhor_janela_por_titulo(None, [TRADOVATE]))


class TestOutrasPlataformas(unittest.TestCase):
    """'não analise tradeview, profit, nada' — ele estava DESCREVENDO o
    defeito. O motor tem de ler qualquer plataforma que ele escolher."""

    def test_Profit_com_cotacao_no_titulo(self):
        i = P.melhor_janela_por_titulo(
            "Profit Chart — WDOV25 5.512,50",
            [TRADOVATE, "Profit Chart — WDOV25 5.498,00"])
        self.assertEqual(i, 1)

    def test_MetaTrader_com_conta_e_saldo_no_titulo(self):
        i = P.melhor_janela_por_titulo(
            "MetaTrader 5 - Conta 512345: 10 250,00 USD",
            ["MetaTrader 5 - Conta 512345: 10 190,50 USD"])
        self.assertEqual(i, 0)

    def test_aba_do_Chrome_com_preco_no_titulo(self):
        """As abas do CDP passam pelo mesmo casamento: o rótulo guardado tem o
        preço do momento em que ele escolheu."""
        i = P.melhor_janela_por_titulo(
            "MGC1! 4.704,5 Sem nome",
            ["Tradovate", "MGC1! 4.688,0 Sem nome"])
        self.assertEqual(i, 1)


class TestResolverDevolveOTituloDeVerdade(unittest.TestCase):

    def test_alvo_vazio_devolve_par_vazio(self):
        self.assertEqual(P.resolver_janela(""), (None, ""))
        self.assertEqual(P.resolver_janela(None), (None, ""))

    def test_encontrar_janela_continua_devolvendo_so_o_handle(self):
        """Todo o resto do programa chama esta; a assinatura não muda."""
        self.assertIsNone(P.encontrar_janela(""))

    def test_resolver_devolve_DOIS_valores(self):
        r = P.resolver_janela("janela que não existe em lugar nenhum 999")
        self.assertEqual(len(r), 2)

    def test_a_lista_salva_NAO_e_reescrita_a_cada_tique(self):
        """Tentador e errado: regravar o título novo faria o histórico de cada
        janela (cenário, imagem anterior, preço anterior) ser jogado fora toda
        volta do ciclo, porque ele é guardado sob o nome salvo."""
        fonte = _fonte("main_app.py")
        i = fonte.index("def _resolver_hwnd_corretora")
        self.assertNotIn("salvar_janelas_monitoradas", fonte[i:i + 2600])

    def test_no_Mac_o_TAMANHO_da_janela_e_conferido_ANTES_do_texto(self):
        """Sem a permissão de Gravação de Tela, TODAS as janelas do Chrome vêm
        sem nome e viram 'Google Chrome — janela 2 (1512x982)'. Pelo texto as
        três são idênticas; a medida é a única coisa que as separa. Se a
        comparação por texto rodasse primeiro, ela devolveria a primeira da
        lista — um chute com cara de acerto."""
        fonte = _fonte("plataforma.py")
        i = fonte.index("def resolver_janela")
        corpo = fonte[i:i + 3200]
        j = corpo.index("if E_MACOS:")
        por_tamanho = corpo.index("janela\\s+\\d+\\s+\\((\\d+)x(\\d+)\\)", j)
        por_texto = corpo.index("melhor_janela_por_titulo(alvo,", j)
        self.assertLess(por_tamanho, por_texto)


class TestOPainelAvisaQueOTituloVaiMudar(unittest.TestCase):

    def test_titulo_com_cotacao_e_reconhecido_como_volatil(self):
        self.assertTrue(P.titulo_muda_sozinho(SALVO_MGC))
        self.assertTrue(P.titulo_muda_sozinho("(78) WhatsApp"))

    def test_titulo_parado_NAO_dispara_o_aviso(self):
        """Se avisasse em toda janela, o aviso não valeria nada."""
        self.assertFalse(P.titulo_muda_sozinho(TRADOVATE))
        self.assertFalse(P.titulo_muda_sozinho("Google Chrome"))

    def test_a_numeracao_do_proprio_programa_nao_conta_como_cotacao(self):
        self.assertFalse(
            P.titulo_muda_sozinho("Google Chrome — janela 2 (1512x982)"))

    def test_vazio_nao_levanta(self):
        self.assertFalse(P.titulo_muda_sozinho(None))

    def test_incluir_a_MESMA_janela_duas_vezes_e_barrado(self):
        """Incluir o TradingView hoje e amanhã guardaria dois títulos que
        parecem diferentes e são a mesma janela — o motor analisaria o mesmo
        gráfico duas vezes por ciclo, gastando cota em dobro."""
        codigo = _fonte("main_app.py")
        i = codigo.index("def _incluir_janela_monitorada")
        corpo = codigo[i:i + 2400]
        self.assertIn("esqueleto_do_titulo", corpo)
        self.assertIn("MESMA janela", corpo)

    def test_o_painel_avisa_que_o_titulo_tem_preco_dentro(self):
        # A FUNÇÃO INTEIRA, NÃO UMA JANELA DE N BYTES. Este teste já foi
        # remendado uma vez com "a janela cresceu: agora são 4200" — e voltou a
        # quebrar na correção seguinte, pelo mesmo motivo. Recorte por tamanho
        # mede a POSIÇÃO da regra, não a regra.
        corpo = funcao_inteira(_fonte("main_app.py"),
                               "_incluir_janela_monitorada")
        self.assertIn("titulo_muda_sozinho", corpo)


class TestOMotorTrataCadaJanelaComoUma(unittest.TestCase):

    def setUp(self):
        self.codigo = _fonte("main_app.py")

    def test_o_cache_de_handle_e_POR_JANELA(self):
        """Era um só. Com duas janelas monitoradas, a segunda volta do laço
        apagava o handle da primeira e o cache nunca acertava — busca completa
        por janela, por ciclo, e a linha de 'janela fixada' repetindo sempre."""
        self.assertIn("_hwnd_por_janela", self.codigo)
        self.assertNotIn("self._hwnd_cache_nome", self.codigo)

    def test_o_cache_guarda_e_le_pelo_nome_da_janela(self):
        i = self.codigo.index("def _resolver_hwnd_corretora")
        corpo = self.codigo[i:i + 2600]
        self.assertIn("_hwnd_por_janela.get(nome_janela)", corpo)
        self.assertIn("_hwnd_por_janela[nome_janela] = hwnd", corpo)

    def test_o_cache_do_Mac_deixa_de_depender_do_pywin32(self):
        """A conferência 'a janela ainda existe?' estava trancada atrás de
        PYWIN32_DISPONIVEL, que é False no Mac — lá o cache nunca valia."""
        i = self.codigo.index("def _resolver_hwnd_corretora")
        corpo = self.codigo[i:i + 2600]
        self.assertNotIn("PYWIN32_DISPONIVEL", corpo)

    def test_o_motor_usa_o_casamento_novo_e_guarda_o_titulo_real(self):
        i = self.codigo.index("def _resolver_hwnd_corretora")
        corpo = self.codigo[i:i + 2600]
        self.assertIn("resolver_janela(nome_janela)", corpo)


class TestOAvisoDizAVerdadeEParaDeGritar(unittest.TestCase):

    def setUp(self):
        self.codigo = _fonte("main_app.py")
        self.i = self.codigo.index("ERRO DE VISUALIZAÇÃO: não encontrei a janela")
        self.trecho = self.codigo[self.i:self.i + 2200]

    def test_nao_diz_mais_CICLO_PULADO_quando_ha_outras_janelas(self):
        """Era ESTA janela que foi pulada, não o ciclo. As outras seguem
        sendo analisadas no mesmo laço, logo abaixo — dizer 'ciclo pulado'
        fazia parecer que o robô tinha parado de trabalhar."""
        self.assertIn("Sigo com as outras", self.trecho)

    def test_a_mensagem_LISTA_o_que_esta_aberto(self):
        """'Não encontrei' sem dizer o que existe não deixa ninguém consertar
        nada. Com a lista, dá para ver que o título mudou."""
        self.assertIn("_janelas_abertas_para_log", self.trecho)

    def test_existe_a_funcao_que_lista_as_janelas_abertas(self):
        i = self.codigo.index("def _janelas_abertas_para_log")
        self.assertIn("listar_janelas", self.codigo[i:i + 900])

    def test_o_WhatsApp_nao_repete_a_mesma_queixa_todo_ciclo(self):
        """Aviso que chega a cada volta ensina a ignorar aviso — foi o mesmo
        defeito do alarme de permissão de tela."""
        self.assertIn("_falhas_por_janela", self.trecho)
        self.assertIn("% 20 == 0", self.trecho)

    def test_o_contador_zera_quando_a_janela_volta(self):
        self.assertIn("self._falhas_por_janela[nome_janela] = 0", self.trecho)

    def test_a_mensagem_diz_ONDE_reescolher_a_janela(self):
        self.assertIn("Janelas monitoradas", self.trecho)


if __name__ == "__main__":
    unittest.main(verbosity=2)
