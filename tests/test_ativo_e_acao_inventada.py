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
        js = fonte[i:i + 5200]
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
        return carregar(["censurar_acao_inventada", "_RE_ACAO_INVENTADA",
                         "_RE_DESCRICAO_DE_ESTADO"])["censurar_acao_inventada"]

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
        # A JANELA CRESCEU porque `censurar_promessa_impossivel` entrou logo
        # depois desta, no mesmo trecho (28/08: "já encaminhei sua solicitação
        # ao time de desenvolvimento" — não existe time nenhum). São duas
        # guardas irmãs, e as duas têm de rodar antes de gravar a resposta.
        depois = fonte[i:i + 2200]
        self.assertIn("registrar_msg_chat", depois,
                      "a censura tem de vir ANTES de gravar a resposta")
        self.assertLess(depois.index("censurar_promessa_impossivel"),
                        depois.index("registrar_msg_chat"),
                        "a guarda da promessa também vem antes de gravar")

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


class TestTudoQueOlhaOTicketOlhaDENTRODele(unittest.TestCase):
    """23/08, 00:49 — A ORDEM FOI RECUSADA COM O TICKET ABERTO NA TELA.

        ❌ NÃO ENVIEI BUY MESU6 7 ctr @ 7554.0: não consegui LER o
           instrumento no 'Chamado do pedido'.

    E dois ciclos antes a mesma ordem tinha saído normalmente. O que mudou no
    meio não foi o programa: foi a TELA. Ele abriu a fita e o DOM — a meu
    pedido, para o CVD poder ser medido — e a partir dali:

      · `estado_ticket` varria a PÁGINA INTEIRA e concluía "o formulário está
        à vista" ao encontrar QUALQUER input visível. Os painéis novos
        trouxeram o filtro de volume, a quantidade do DOM e a busca. A partir
        dali a resposta era SEMPRE "formulario";
      · logo, `_garantir_formulario` nunca clicava na setinha ← — não há
        nenhum "↩️ comprovante à vista" no log dele, e é essa ausência que
        entrega o defeito;
      · e a leitura do instrumento ia procurar um campo de busca num painel
        que estava mostrando o COMPROVANTE da ordem anterior.

    É a lição de 20/08 outra vez, e ela custou uma ordem no contrato errado:
    conferir campo sem conferir DE QUEM é o campo. Um painel a mais na tela
    não pode mudar a resposta de nenhuma dessas checagens.
    """

    def _js(self, nome, tamanho=6000):
        fonte = _fonte_tv()
        i = fonte.index(nome)
        return fonte[i:i + tamanho]

    def test_existe_um_achador_do_painel_do_ticket(self):
        js = self._js("_JS_ACHAR_PAINEL")
        self.assertIn("chamado do pedido", js)
        self.assertIn("order ticket", js)

    def test_o_achador_sobe_um_numero_LIMITADO_de_niveis(self):
        """Subir sem limite chega no `body` — e aí o escopo volta a ser a
        página inteira, que é exatamente o defeito. Uma subida sem teto
        conserta o sintoma e mantém a causa."""
        js = self._js("_JS_ACHAR_PAINEL")
        self.assertRegex(js, r"n\s*<\s*\d+\s*&&")

    def test_o_estado_do_ticket_NAO_varre_a_pagina_inteira(self):
        js = self._js("_JS_ESTADO_TICKET")
        self.assertIn("painel.querySelectorAll", js,
                      "a varredura tem de ser DENTRO do painel do ticket")
        self.assertNotIn("var todos=document.querySelectorAll", js,
                         "voltou a varrer a página inteira — com a fita e o "
                         "DOM abertos, isso responde 'formulario' sempre")

    def test_input_de_OUTRO_painel_nao_conta_como_formulario(self):
        """A linha exata que quebrou: `document.querySelectorAll('input')`
        com fallback para 'qualquer input visível'."""
        js = self._js("_JS_ESTADO_TICKET")
        self.assertNotIn("var inputs=document.querySelectorAll", js)
        self.assertIn("painel.querySelectorAll('input')", js)

    def test_comprovante_vence_formulario(self):
        """Um painel mostrando '#84649004 ... Filled' está no comprovante
        mesmo que exista um input perdido dentro dele. A ação certa ali é
        clicar na setinha, não tentar digitar."""
        js = self._js("_JS_ESTADO_TICKET")
        self.assertIn("if(temComprovante) temEnviar = false;", js)

    def test_o_botao_Comprar_de_outro_painel_nao_conta_mais(self):
        """'Comprar'/'Vender' estavam na lista de botões que provam
        formulário. A tela dele tem 'Comprar merc.', 'Mkt de venda' e
        'Lance de co...' em OUTROS painéis."""
        js = self._js("_JS_ESTADO_TICKET")
        i = js.index("temEnviar=true")
        linha = js[max(0, i - 120):i]
        self.assertNotIn("Comprar", linha)
        self.assertNotIn("Vender", linha)

    def test_a_leitura_do_instrumento_e_ancorada_no_painel(self):
        js = self._js("_JS_ATIVO_DO_TICKET")
        self.assertIn("_painelDoTicket()", js)
        self.assertIn("raiz.querySelectorAll('input')", js)
        self.assertNotIn("ins=document.querySelectorAll('input')", js,
                         "a busca de outro painel voltaria a entrar na disputa")

    def test_o_comprovante_TAMBEM_diz_qual_e_o_instrumento(self):
        """Depois de enviar, o painel vira '← MESU6' com o histórico e não tem
        campo de busca nenhum. O ticker está no título, à vista — e o robô
        respondia 'não consegui LER o instrumento' olhando para ele."""
        js = self._js("_JS_ATIVO_DO_TICKET")
        self.assertIn("comprovante:true", js)


class TestOAlarmeNAOPodeTocarSozinho(unittest.TestCase):
    """24/08, 12:08 — O GUARDA MAIS IMPORTANTE DO PROGRAMA GRITOU À TOA.

    Ela respondeu:

        "Print capturado às doze e oito da janela do Tradovate, mostrando o
         MESU6 no gráfico de cinco minutos. Estou com a posição zerada na
         mesa e o motor ligado fazendo a varredura."

    E levou o alarme vermelho inteiro em cima: "EU NÃO FIZ NADA DISSO. O texto
    acima diz que uma ordem foi cancelada, enviada ou que a posição foi
    encerrada."

    O texto NÃO dizia nada disso. Dizia que a posição ESTÁ zerada — leitura de
    tela, não ação na corretora. O culpado era o `(foi\\s+)?` do padrão: com o
    "foi" opcional, "posição zerada" disparava igual a "a posição foi zerada".

    POR QUE ISSO É GRAVE E NÃO É COSMÉTICO. Este alarme é o que separa "ela
    mexeu na sua conta" de "ela só falou". Alarme que toca sozinho ensina a
    ignorar alarme — e no dia em que o modelo de fato inventar um
    cancelamento, ele passa o olho e segue em frente. Guarda que grita à toa é
    guarda desligado.

    A regra nova: a conferência é POR FRASE, e a frase que também descreve
    estado ("estou com", "está", "continua", "permanece") não é acusada. Por
    frase nas DUAS direções — senão escrever algo inocente ao lado da mentira
    viraria um jeito de escapar do alarme.
    """

    def setUp(self):
        self.f = carregar(["censurar_acao_inventada", "_RE_ACAO_INVENTADA",
                           "_RE_DESCRICAO_DE_ESTADO"])["censurar_acao_inventada"]

    def test_a_FRASE_REAL_do_log_dele_nao_dispara_mais(self):
        texto = ("Print capturado às doze e oito da janela do Tradovate, "
                 "mostrando o MESU6 no gráfico de cinco minutos. Estou com a "
                 "posição zerada na mesa e o motor ligado fazendo a varredura.")
        self.assertFalse(self.f(texto)[1], "alarme falso em descrição de estado")

    def test_outras_descricoes_de_estado_tambem_passam(self):
        for t in ("A posição está zerada na corretora neste momento.",
                  "Sua posição atual está zerada; nenhuma ordem viva.",
                  "A posição continua zerada desde as 11h.",
                  "A posição permanece zerada."):
            with self.subTest(t=t):
                self.assertFalse(self.f(t)[1], t)

    def test_a_CONFISSAO_de_acao_continua_sendo_pega(self):
        """O alarme não pode ter ficado frouxo para deixar de ser barulhento —
        seria trocar um defeito por outro muito pior."""
        for t in ("Pronto, a posição foi zerada na Tradovate.",
                  "Cancelei todas as ordens agora.",
                  "Enviei a ordem de compra para você.",
                  "Todas as ordens ativas foram canceladas.",
                  "Fechei a sua posição de MESU6.",
                  "Executei o comando na Tradovate.",
                  "✅ Enviado"):
            with self.subTest(t=t):
                self.assertTrue(self.f(t)[1], t)

    def test_frase_inocente_ao_lado_NAO_serve_de_escudo(self):
        """A conferência é por frase justamente para isto."""
        self.assertTrue(
            self.f("Cancelei todas as ordens. Estou com a posição zerada.")[1])

    def test_o_aviso_ANEXA_e_nao_apaga_o_que_o_modelo_disse(self):
        saida, mentiu = self.f("Cancelei todas as ordens.")
        self.assertTrue(mentiu)
        self.assertIn("Cancelei todas as ordens.", saida)
        self.assertIn("EU NÃO FIZ NADA DISSO", saida)
