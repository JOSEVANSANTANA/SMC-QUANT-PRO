"""QUATRO ABAS DA TRADOVATE ABERTAS. TODAS VIRAM ORDEM? E ONDE A ORDEM É DIGITADA?

A PERGUNTA
----------
31/08, 15:22. Ele montou a mesa com quatro janelas: 'smcquant ouro',
'SMC QUANT PRO', 'microouro' e 'bitcoins' — MESU6, MGCV6 e MBTU6 na mesma
conta. "quero que acompanhe todos, e caso surjam sugestões em algum deles,
sejam enviadas ordens, isso já está sendo feito?"

A RESPOSTA HONESTA ERA "SIM, MENOS UM" — E DUAS COISAS PRECISAVAM MUDAR.

1. O BITCOIN NÃO GERAVA NADA. 'MBT' não estava na tabela de contratos, e o
   motor recusa gráfico de contrato que ele não conhece — a mesma recusa que
   ele já tinha visto com o WINFUT:

       🚫 'WINFUT' não está na tabela de contratos, então eu não sei quanto
          vale um ponto dele — e sem isso qualquer dimensionamento meu seria
          chute.

   A recusa está certa: sem valor por ponto, o dimensionamento vira chute
   sobre dinheiro. O que estava errado era a tabela estar incompleta. O Micro
   Bitcoin é 0,1 BTC — US$ 0,10 por ponto, degrau de US$ 5.

2. A ABA QUE RECEBIA A ORDEM ERA SORTEADA. `descobrir_aba_tradovate` devolvia
   a PRIMEIRA aba cujo URL contém 'tradovate'. Com quatro abas, todas em
   trader.tradovate.com, qual vem primeiro é ordem de criação do Chrome —
   muda quando ele fecha e reabre uma, e não tem relação nenhuma com a lista
   de gráficos monitorados.

   O efeito estava na foto que ele mandou: o ticket da aba 'bitcoins' com
   MESU6 escrito dentro, preço 7685.00, enquanto o gráfico daquela aba é o
   MBTU6 a 79300. Não era defeito de envio — o ticket da Tradovate opera
   qualquer instrumento e `garantir_ativo_no_ticket` troca o símbolo antes de
   mandar. Era o programa escrevendo numa aba sorteada.

E O TEXTO DA TELA MENTIA
-------------------------
"A PRIMEIRA da lista é a principal: é nela que o envio de ordem e a leitura de
posições trabalham." Lido de fora, isso quer dizer "só o primeiro ativo é
operado" — e não é. Todos são. O que a primeira faz é ser a aba onde a ordem é
DIGITADA. Texto de tela que descreve errado o que o robô faz com dinheiro é
defeito, não estilo: ele ia reorganizar a lista esperando mudar o que é
operado.
"""

import os
import sys
import unittest

from harness import RAIZ, carregar, funcao_inteira

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def _fonte(nome="main_app.py"):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


NS = carregar([
    "valor_por_ponto_do_ativo",
    "tick_do_ativo",
    "faixa_de_stop_do_ativo",
    "_e_contrato_conhecido",
    "VALOR_POR_PONTO",
    "VALOR_POR_PONTO_PADRAO",
])

vpp = NS["valor_por_ponto_do_ativo"]
tick = NS["tick_do_ativo"]
faixa = NS["faixa_de_stop_do_ativo"]
conhecido = NS["_e_contrato_conhecido"]


class OBitcoinDaMesaDELE(unittest.TestCase):

    def test_MBTU6_deixa_de_ser_recusado(self):
        """A janela 'bitcoins' dele. Antes, o ciclo inteiro dela era jogado
        fora com 'não está na tabela de contratos'."""
        self.assertTrue(conhecido("MBTU6"))
        self.assertTrue(conhecido("MBT"))

    def test_o_valor_por_ponto_do_micro_bitcoin(self):
        """0,1 BTC: cada US$ 1 no preço do bitcoin move US$ 0,10 no contrato.
        Este número decide QUANTOS CONTRATOS ele vai carregar — errar aqui é
        errar o tamanho da posição, que é o erro mais caro que existe."""
        self.assertEqual(vpp("MBTU6"), 0.10)
        self.assertEqual(vpp("MBT"), 0.10)

    def test_o_bitcoin_cheio_vale_cinquenta_vezes_o_micro(self):
        """5 BTC contra 0,1 BTC."""
        self.assertEqual(vpp("BTCU6"), 5.00)
        self.assertAlmostEqual(vpp("BTCU6") / vpp("MBTU6"), 50.0)

    def test_o_degrau_de_preco_e_de_cinco_dolares(self):
        self.assertEqual(tick("MBTU6"), 5.0)
        self.assertEqual(tick("BTCU6"), 5.0)

    def test_a_faixa_de_stop_acompanha_o_tamanho_do_movimento(self):
        """Faixa estreita demais recusaria todo cenário do contrato — o
        bitcoin percorre milhares de pontos num dia."""
        self.assertEqual(faixa("MBTU6"), (40, 400))

    def test_MBT_nao_atropela_nenhum_contrato_que_ja_existia(self):
        """Raiz nova casando por prefixo com raiz antiga trocaria o valor por
        ponto de um contrato que já funcionava — em silêncio."""
        for antigo, esperado in (("MESU6", 5.0), ("MNQU6", 2.0),
                                 ("MGCV6", 10.0), ("MYMU6", 0.5),
                                 ("M2KU6", 0.5), ("MCLU6", 100.0),
                                 ("WINV26", 0.20), ("WDOV26", 10.00)):
            self.assertEqual(vpp(antigo), esperado, antigo)

    def test_palavra_qualquer_continua_recusada(self):
        """A trava original: 'CLAUDE' começa com 'CL' (petróleo)."""
        for lixo in ("CLAUDE", "BTCOINS", "MBTX", "CHAT"):
            self.assertFalse(conhecido(lixo), lixo)


class ATODOSOsAtivosPodemVIRAROrdem(unittest.TestCase):

    def test_o_envio_NAO_esta_preso_a_janela_principal(self):
        """O laço do motor não pode acatar só na primeira janela. Se acatasse,
        a mesa dele operaria um ativo de quatro."""
        fonte = _fonte()
        i = fonte.index("self._acatar_sozinha(")
        # Do começo do bloco de decisão até a chamada, não pode haver um
        # `if janela_principal` que a envolva.
        trecho = fonte[fonte.index("---- A FERRAMENTA ACATA SOZINHA ----"):i]
        self.assertNotIn("janela_principal", trecho)

    def test_a_posicao_e_a_ordem_viva_sao_decididas_POR_ATIVO(self):
        """Se a trava de posição fosse global, uma ordem viva no MESU6
        bloquearia o cenário do ouro — a mesa inteira viraria um ativo só."""
        fonte = _fonte()
        self.assertIn("def posicao_aberta_no_ativo(ativo)", fonte)
        self.assertIn("def ordem_enviada_e_viva_no_ativo(ativo)", fonte)

    def test_o_texto_da_tela_diz_que_TODOS_viram_ordem(self):
        """Ele dizia 'é na primeira que o envio de ordem trabalha', que lido de
        fora quer dizer 'só o primeiro é operado'."""
        fonte = _fonte()
        i = fonte.index("Cada janela é um ativo, com cenário e histórico")
        trecho = fonte[i:i + 1400]
        self.assertIn("TODOS são analisados e TODOS podem", trecho)
        self.assertIn("ABA DE EXECUÇÃO", trecho)


class AAbaQueRecebeAOrdemDeixaDeSerSorteada(unittest.TestCase):

    def _fonte_tv(self):
        with open(os.path.join(RAIZ, "tradovate_auto.py"), encoding="utf-8") as f:
            return f.read()

    def test_a_aba_preferida_MANDA(self):
        corpo = funcao_inteira(self._fonte_tv(), "descobrir_aba_tradovate")
        self.assertIn("id_preferida", corpo)
        i_pref = corpo.index("id_preferida")
        i_fallback = corpo.rindex("abas[0]")
        self.assertLess(i_pref, i_fallback,
                        "a preferência tem de ser consultada ANTES de cair na "
                        "primeira aba que o Chrome listar")

    def test_quando_a_aba_preferida_sumiu_ele_DIZ_e_segue(self):
        """Parar de operar porque uma aba foi fechada seria pior que a doença.
        Mas seguir em silêncio é como o ticket da aba 'bitcoins' apareceu com
        MESU6 dentro sem ninguém entender."""
        corpo = funcao_inteira(self._fonte_tv(), "descobrir_aba_tradovate")
        self.assertIn("não está mais", corpo)
        self.assertIn("conferido no ticket", corpo)

    def test_conectar_aceita_e_repassa_a_aba(self):
        corpo = funcao_inteira(self._fonte_tv(), "conectar")
        self.assertIn("id_aba", corpo)
        self.assertIn("descobrir_aba_tradovate(id_aba)", corpo)

    def test_a_aba_de_execucao_vem_da_PRIMEIRA_janela_monitorada(self):
        corpo = funcao_inteira(_fonte(), "_aba_de_execucao")
        self.assertIn("janelas_monitoradas()", corpo)
        self.assertIn("[0]", corpo)
        self.assertIn("_PREFIXO_CDP", corpo)

    def test_janela_que_nao_e_aba_do_Chrome_devolve_None(self):
        """Janela de aplicativo (Profit, MetaTrader) não tem aba de CDP —
        devolver um handle de janela como id de aba faria a busca casar com
        nada e o log acusar aba sumida a cada ciclo."""
        corpo = funcao_inteira(_fonte(), "_aba_de_execucao")
        self.assertIn("startswith(plataforma._PREFIXO_CDP)", corpo)
        self.assertIn("return None", corpo)

    def test_o_motor_passa_a_aba_ao_conectar(self):
        corpo = funcao_inteira(_fonte(), "_tv_conectar")
        self.assertIn("bot.conectar(self._aba_de_execucao())", corpo)

    def test_o_instrumento_continua_conferido_no_ticket_antes_de_enviar(self):
        """A escolha da aba NÃO substitui esta trava. É ela que impede a ordem
        de cair no contrato errado — e ordem no instrumento errado não tem
        desfazer."""
        corpo = funcao_inteira(self._fonte_tv(), "garantir_ativo_no_ticket")
        self.assertIn("return False", corpo)
        self.assertIn("mesmo_instrumento", corpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
