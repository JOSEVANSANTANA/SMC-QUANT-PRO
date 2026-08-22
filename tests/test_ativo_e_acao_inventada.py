"""AS DUAS FALHAS DE 20/08 QUE CUSTARAM DINHEIRO E CONFIANÇA.

=====================================================================
1. A ORDEM ERA DE MNQU6 E EXECUTOU EM MESU6
=====================================================================
12:17. O cenário era MNQU6 (Micro Nasdaq, negociando a ~29.700). O programa
preencheu preço 29630, stop 29580, alvo 29780, quantidade 2, conferiu tudo e
mandou. A Tradovate registrou:

    #372662132 Comprar 2 MESU6 LMT em 29630.00 - Filled - 2/2

MESU6, não MNQU6. O ticket estava com o OUTRO instrumento selecionado, e o
robô nunca olhou para esse campo. Uma compra limitada de MES a 29.630 num
mercado que está em 7.770 é uma ordem a mercado disfarçada: preencheu na hora.

E repare no que TODAS as conferências disseram naquele ciclo: "preço
conferido", "quantidade conferida", "ATM conferida". Todas verdadeiras. Todas
sobre o formulário errado. Conferir os campos sem conferir DE QUEM são os
campos é o tipo de checagem que dá falsa segurança — a pior espécie.

=====================================================================
2. A TIGER DISSE QUE CANCELOU AS ORDENS. NÃO CANCELOU NADA.
=====================================================================
13:08, no chat:
    ❯ encerre todas operacoes agora
    ✳ "✅ ENVIADO: TODAS as ordens foram canceladas via API Tradovate.
       Posição atual: 0 contratos MESU6."

A posição continuou aberta. Ele só descobriu porque foi olhar. Seis minutos
depois o MESMO modelo dizia "não tenho acesso para executar comandos na
Tradovate" — as duas frases na mesma conversa.

A regra JÁ ESTAVA no prompt ("nunca diga que fez algo"). O modelo passou por
cima. Num sistema que mexe com dinheiro, instrução ao modelo é pedido, não
garantia: o que garante é conferir a saída — como já se fazia com os números
da conta desde 12/08.
"""

import os
import re
import sys
import unittest

from harness import RAIZ, carregar, fonte_do_arquivo

sys.path.insert(0, RAIZ)
import tradovate_auto as tv  # noqa: E402


class TestOInstrumentoDoTicket(unittest.TestCase):

    def test_MES_e_MNQ_NAO_sao_o_mesmo_contrato(self):
        """O erro que custou a ordem. Se esta linha voltar a dar True, o
        prejuízo volta junto."""
        self.assertFalse(tv.TradovateAuto.mesmo_instrumento("MESU6", "MNQU6"))
        self.assertFalse(tv.TradovateAuto.mesmo_instrumento("MNQU6", "MESU6"))

    def test_o_mesmo_contrato_com_e_sem_vencimento_casa(self):
        """MESU6 e MES são o mesmo instrumento — recusar aqui travaria toda
        ordem legítima."""
        for a, b in (("MESU6", "MES"), ("MES", "MESU6"),
                     ("MNQU6", "MNQ"), ("MNQ", "MNQU6"),
                     ("MESZ5", "MESU6"), ("NQ", "NQZ5")):
            self.assertTrue(tv.TradovateAuto.mesmo_instrumento(a, b), f"{a}/{b}")

    def test_MNQ_sozinho_nao_vira_MN(self):
        """'Q' e 'N' também são códigos de mês. Sem tratar isso, a raiz de
        'MNQ' saía como 'MN' e deixava de casar com 'MNQU6' — trocando um bug
        por outro."""
        self.assertTrue(tv.TradovateAuto.mesmo_instrumento("MNQ", "MNQU6"))

    def test_vazio_ou_None_nunca_casa(self):
        """Ausência de leitura não pode virar 'está certo'."""
        for a in ("", None, "   "):
            self.assertFalse(tv.TradovateAuto.mesmo_instrumento(a, "MESU6"))
            self.assertFalse(tv.TradovateAuto.mesmo_instrumento("MESU6", a))

    def test_o_ativo_e_conferido_ANTES_de_preco_e_quantidade(self):
        """Ordem importa: conferir preço num formulário do instrumento errado
        é exatamente o que produziu 'preço conferido' e ordem errada."""
        fonte = _fonte_tv()
        i = fonte.index("def _preencher_ordem_atm")
        corpo = fonte[i:i + 3000]
        i_ativo = corpo.index("garantir_ativo_no_ticket(")
        i_preco = corpo.index("PREÇO")
        self.assertLess(i_ativo, i_preco)

    def test_nao_conseguir_ler_o_instrumento_BLOQUEIA_o_envio(self):
        """'Não sei em que contrato isto cairia' tem de parar a ordem. Ordem
        no instrumento errado não tem desfazer."""
        fonte = _fonte_tv()
        i = fonte.index("def garantir_ativo_no_ticket")
        corpo = fonte[i:i + 2500]
        self.assertIn("if atual is None:", corpo)
        self.assertIn("return False", corpo)

    def test_a_troca_e_CONFERIDA_depois_de_feita(self):
        """Escrever no campo não prova que a plataforma aceitou: sem o Enter e
        sem reler, o ticket pode continuar no contrato anterior."""
        fonte = _fonte_tv()
        i = fonte.index("def garantir_ativo_no_ticket")
        corpo = fonte[i:i + 2500]
        self.assertIn("depois = self.ler_ativo_do_ticket()", corpo)
        self.assertIn("Enter", corpo)

    def test_recusa_de_ativo_NAO_cai_para_o_caminho_antigo(self):
        """Mandar pelas três ordens separadas não conserta o instrumento
        errado — só espalha o erro por três ordens em vez de uma."""
        fonte = _fonte_tv()
        i = fonte.index("def _preencher_ordem_atm")
        corpo = fonte[i:i + 3000]
        i_ativo = corpo.index("ok_ativo, motivo_ativo")
        trecho = corpo[i_ativo:i_ativo + 700]
        self.assertIn("return False, motivo_ativo, False", trecho,
                      "sem_painel tem de ser False = RECUSA, não falta de recurso")

    def test_o_app_passa_o_ativo_no_envio(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("enviar_ordem_com_atm(")
        self.assertIn("ativo=", fonte[i:i + 700])


class TestOCampoVazioDepoisDeEnviar(unittest.TestCase):
    """22/08, 16:57 — 'NÃO ENVIEI BUY MESU6 4 ctr: não consegui LER o
    instrumento no Chamado do pedido'.

    A recusa estava CERTA (sem saber o contrato, não se manda ordem) e mesmo
    assim era um defeito: o instrumento estava lá, na tela, à vista. Quem não
    enxergava era a leitura.

    O padrão que ele viu e descreveu — 'após envio de ordens' — é a prova:

      · ticket JÁ CARREGADO  -> o campo tem value='MESU6' -> achado pelo VALOR
      · ticket recém-limpo   -> o campo tem value='' e placeholder='Pesquisar'

    e a lista de placeholders aceitos era (symbol|símbolo|instrumento|buscar|
    search). 'Pesquisar' — a palavra que a Tradovate em português de fato
    escreve — não está em nenhuma delas. O campo era PULADO, ninguém achava o
    instrumento, e a ordem seguinte morria na trava.

    Por isso era intermitente, e por isso parecia 'ter voltado': dependia só
    de o ticket estar carregado ou limpo no instante da leitura.
    """

    def _regex_do_placeholder(self):
        """A lista de rótulos aceitos, lida do JS que roda na plataforma."""
        fonte = _fonte_tv()
        i = fonte.index("_JS_ATIVO_DO_TICKET")
        js = fonte[i:i + 3000]
        m = re.search(r"var busca=/\((.*?)\)/\.test\(ph\)", js)
        self.assertIsNotNone(m, "não achei a regex do placeholder do instrumento")
        return m.group(1).split("|")

    def test_pesquisar_esta_na_lista_de_rotulos(self):
        """A palavra que a plataforma REALMENTE usa em português."""
        self.assertIn("pesquisar", self._regex_do_placeholder(),
                      "sem 'pesquisar', o campo vazio do ticket limpo é "
                      "invisível para o robô — e toda ordem depois de um "
                      "envio é recusada por 'não consegui LER o instrumento'")

    def test_os_rotulos_antigos_continuam_valendo(self):
        """A correção ACRESCENTA; ela não pode trocar um idioma pelo outro —
        o mesmo programa roda com a Tradovate em inglês."""
        aceitos = self._regex_do_placeholder()
        for rotulo in ("search", "symbol", "instrumento", "buscar"):
            self.assertIn(rotulo, aceitos)

    def test_um_campo_COM_ticker_ganha_de_um_campo_so_com_placeholder(self):
        """A trava que impede a cura de virar doença.

        Alargar o placeholder para 'pesquisar' faz outras caixas de busca da
        página entrarem na disputa — inclusive a busca geral da plataforma,
        que fica MAIS ALTA na tela e venceria no critério antigo (o de menor
        `top`). Ler o instrumento errado é pior que não ler nenhum: não ler
        recusa a ordem, ler errado MANDA a ordem — no contrato errado, que foi
        o prejuízo de 20/08 registrado no topo deste arquivo.

        Um campo que já mostra um ticker é PROVA; um placeholder é indício.
        """
        fonte = _fonte_tv()
        i = fonte.index("_JS_ATIVO_DO_TICKET")
        js = fonte[i:i + 3000]
        self.assertIn("comValor || soBusca", js,
                      "a fila do VALOR tem de vencer a do placeholder")

    def test_ticket_vazio_nao_e_anunciado_como_ticket_em_nada(self):
        """Campo achado e vazio é o estado NORMAL depois de uma ordem — a
        Tradovate limpa o ticket. A frase tem de dizer isso, e não 'o ticket
        está em ' seguido de espaço em branco."""
        fonte = _fonte_tv()
        i = fonte.index("def garantir_ativo_no_ticket")
        corpo = fonte[i:i + 2500]
        self.assertIn("SEM instrumento", corpo)


class TestAAcaoQueElaNAOFEZ(unittest.TestCase):

    def _f(self):
        return carregar(["censurar_acao_inventada",
                         "_RE_ACAO_INVENTADA"])["censurar_acao_inventada"]

    def test_a_frase_REAL_de_20_08_e_pega(self):
        texto, mentiu = self._f()(
            "✅ ENVIADO: TODAS as ordens foram canceladas via API Tradovate. "
            "Posição atual: 0 contratos MESU6. Nenhuma ordem ativa na plataforma.")
        self.assertTrue(mentiu)
        self.assertIn("EU NÃO FIZ NADA DISSO", texto)

    def test_a_SEGUNDA_frase_real_tambem(self):
        """"Todas as ordens ATIVAS foram canceladas" — o adjetivo no meio fazia
        a regex colada demais deixar passar justamente a variação que
        aconteceu."""
        _, mentiu = self._f()(
            "✅ **ORDEM CANCELADA:** Todas as ordens ativas foram canceladas "
            "via Tradovate. Posição atual: 0 contratos MESU6.")
        self.assertTrue(mentiu)

    def test_pega_as_outras_formas_de_dizer_a_mesma_coisa(self):
        for frase in ("Encerrei a sua posição de 3 contratos.",
                      "Já cancelei todas as ordens pendentes.",
                      "A posição foi zerada com sucesso.",
                      "Fechei todas as posições agora.",
                      "Executei o comando na Tradovate."):
            self.assertTrue(self._f()(frase)[1], frase)

    def test_NAO_pega_a_resposta_HONESTA(self):
        """Ensinar o comando certo é o comportamento desejado — barrar isso
        deixaria a TIGER muda justamente quando ela está certa."""
        for frase in (
                "Para sair de todas as operações, use o comando 'Sair em Mkt & Cxl'.",
                "Não tenho acesso para executar comandos na Tradovate.",
                "O comando que cancela as ordens é 'Sair em Mkt & Cxl'.",
                "Sua posição está aberta: 3 contratos MESU6 @ 7770.33.",
                "Se a ordem for cancelada, o cenário morre junto."):
            self.assertFalse(self._f()(frase)[1], frase)

    def test_o_aviso_e_ANEXADO_e_nao_substitui(self):
        """Ele tem de ler o que o modelo disse E saber que não aconteceu.
        Apagar a frase esconderia o defeito."""
        original = "Já cancelei todas as ordens pendentes."
        texto, _ = self._f()(original)
        self.assertIn(original, texto)

    def test_texto_vazio_nao_dispara_nada(self):
        for v in ("", None, "   "):
            self.assertFalse(self._f()(v)[1])

    def test_a_guarda_roda_no_fluxo_do_chat(self):
        """De nada adianta a função existir se ninguém a chama."""
        fonte = fonte_do_arquivo()
        self.assertIn("resposta, inventou_acao = censurar_acao_inventada(", fonte)
        i = fonte.index("resposta, inventou_acao = censurar_acao_inventada(")
        depois = fonte[i:i + 900]
        self.assertIn("registrar_msg_chat", depois,
                      "a censura tem de vir ANTES de gravar a resposta")

    def test_a_guarda_e_de_CODIGO_e_nao_so_de_prompt(self):
        """A regra já existia no prompt e o modelo passou por cima. Instrução
        ao modelo é pedido; conferir a saída é o que garante."""
        fonte = fonte_do_arquivo()
        self.assertIn("diga que fez algo", fonte,
                      "a regra do prompt continua")
        self.assertIn("def censurar_acao_inventada", fonte,
                      "e agora existe também a guarda em código")


def _fonte_tv():
    return fonte_do_arquivo(os.path.join(RAIZ, "tradovate_auto.py"))


if __name__ == "__main__":
    unittest.main()
