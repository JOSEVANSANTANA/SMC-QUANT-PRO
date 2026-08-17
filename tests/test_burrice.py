#!/usr/bin/env python3
"""OS QUATRO DEFEITOS DO LOG DE 13 e 14/08 — "ela está cada vez mais burra".

Ele não escreveu uma impressão: colou a conversa inteira. Cada teste aqui é
uma linha daquele log, com o texto EXATO que ele digitou e a resposta EXATA
que recebeu.

O que os quatro têm em comum, e por que ficam no mesmo arquivo: em três deles
a ferramenta pegou um PEDAÇO da frase, respondeu esse pedaço e jogou o resto
fora. É isso que se sente como burrice — não é o modelo raciocinando mal, é o
roteador da casa entregando a pergunta errada para ele. O quarto é o outro
lado da mesma moeda: ela tinha o número certo na mão e imprimiu o errado.
"""

import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from harness import carregar, fonte_do_arquivo


class TestOTEQueSequestrouOBoaNoite(unittest.TestCase):
    """14/08, 23:34.

        ❯ boa note
        ✳ OTE é a faixa mais eficiente do recuo, entre 61,8 e 79 por cento da
          correção, com o coração em 70,5. [...]
        ❯ eu disse, boa noite

    Ele precisou repetir para ser entendido. A causa: o TÍTULO do verbete era
    comparado com um `in` cru, sem fronteira de palavra. O título de OTE,
    cortado no parêntese, é a string "ote" — e "ote" está dentro de "n-OTE".

    E não era uma resposta a mais: desde a 2.30.0 a base é consultada ANTES do
    modelo, então o falso positivo SEQUESTRAVA a pergunta.
    """

    def _buscar(self):
        ns = carregar(["_sem_acento", "_norm_busca", "_parecido",
                       "_nota_base_smc", "_todos_os_topicos",
                       "buscar_base_smc", "BASE_SMC", "BASE_MACRO"])
        return ns["buscar_base_smc"], ns["_todos_os_topicos"]

    def test_boa_note_nao_vira_aula_de_OTE(self):
        buscar, _ = self._buscar()
        self.assertIsNone(buscar("boa note"),
                          "'boa note' voltou a cair no verbete de OTE")

    def test_as_outras_palavras_com_ote_dentro(self):
        """O mesmo caminho engolia qualquer palavra com 'ote' no meio. Estas
        são de mesa, não inventadas: ele escreve 'anote isso' o tempo todo."""
        buscar, _ = self._buscar()
        for frase in ("anote isso", "note que o preço caiu", "me manda uma nota",
                      "acesso remoto", "bote pra rodar"):
            self.assertIsNone(buscar(frase),
                              f"{frase!r} caiu num verbete por casamento parcial")

    def test_quem_PERGUNTA_de_OTE_continua_sendo_respondido(self):
        """Consertar o falso positivo não pode matar o verdadeiro — senão a
        base perde a razão de existir."""
        buscar, _ = self._buscar()
        for frase in ("o que é ote", "me explica o OTE",
                      "qual é a entrada ótima", "o que é um choch"):
            self.assertIsNotNone(buscar(frase),
                                 f"{frase!r} deixou de achar resposta na base")
        self.assertEqual(buscar("o que é ote")["t"], "OTE (entrada ótima)")

    def test_todo_titulo_curto_estava_exposto(self):
        """OTE foi o que apareceu no log, mas SETE verbetes têm título curto
        (OTE, BOS, MSS, FVG, iFVG, BPR, CHoCH) e todos corriam o mesmo risco.
        Este teste falha se alguém voltar a usar `in` cru no título."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _nota_base_smc")
        bloco = fonte[i:i + 2600]
        self.assertNotIn('.split(" (")[0] in p', bloco,
                         "o título voltou a casar por substring")
        self.assertIn(r"\b{re.escape(titulo)}\b", bloco)


class TestOPedidoQueFoiEngolidoPeloComando(unittest.TestCase):
    """14/08, 23:37. A mensagem inteira, como ele digitou:

        ❯ por favor, antes de ligar o motor, ajuste o plano de trading para o
          segundo dia de operacao, pois, foi final de semana, e voce esta
          contato o final de semana? fica ciente que o mercado comeca as 19h
          de domingo e encerra as 17:59 de sexta feira,
        ✳ Ligando o motor agora [...]

    Ele pediu TRÊS coisas e a ferramenta respondeu a nenhuma: ligou o motor e
    descartou a frase. "antes de ligar" não é ordem de ligar — é a marcação de
    tempo de outra ordem. Como o roteador devolve UM comando só, casar ali era
    perder o pedido de verdade.
    """

    def _intencao(self):
        from test_conversa import _ns_intencao
        return _ns_intencao()["interpretar_intencao"]

    def test_a_frase_dele_nao_vira_um_clique_no_botao(self):
        f = self._intencao()
        frase = ("por favor, antes de ligar o motor , ajuste o plano de "
                 "trading para o segundo dia de operacao, pois, foi final de "
                 "semana, e voce esta contato o final de semana? fica ciente "
                 "que o mercado comeca as 19h de domingo e encerra as 17:59 "
                 "de sexta feira,")
        self.assertNotEqual(f(frase), "LIGAR_MOTOR",
                            "a mensagem inteira virou 'ligar motor' de novo e "
                            "o pedido do plano foi jogado fora")

    def test_oracao_subordinada_nao_e_ordem(self):
        f = self._intencao()
        for frase in ("antes de ligar o motor, me diga como está o plano",
                      "antes de desligar o motor me mostra o resultado",
                      "quando ligar o motor me avisa",
                      "assim que ligar o motor, confere a conta",
                      "em vez de ligar o motor, só me explica o cenário"):
            self.assertNotIn(f(frase), ("LIGAR_MOTOR", "DESLIGAR_MOTOR"),
                             f"{frase!r} foi tratada como comando do motor")

    def test_a_ORDEM_DE_VERDADE_continua_ligando(self):
        """O conserto não pode deixar o motor sem interruptor. Estas são as
        formas que ele usa todo dia."""
        f = self._intencao()
        for frase in ("liga o motor", "ligar motor", "pode ligar o motor",
                      "tiger, liga o motor", "sobe o robô",
                      "liga o motor antes que o pregão abra"):
            self.assertEqual(f(frase), "LIGAR_MOTOR", frase)
        for frase in ("desliga o motor", "para o motor", "pausa as análises"):
            self.assertEqual(f(frase), "DESLIGAR_MOTOR", frase)

    def test_a_negacao_que_ja_existia_nao_regrediu(self):
        """'não precisa acionar a cota da API para algumas ANÁLISES' desligou o
        motor no meio do pregão uma vez. Não pode voltar."""
        f = self._intencao()
        self.assertNotEqual(
            f("nao precisa acionar a cota da API para algumas analises"),
            "DESLIGAR_MOTOR")

    def test_uma_ocorrencia_legitima_basta(self):
        """A checagem roda em TODAS as ocorrências, não só na primeira — senão
        a subordinada do começo mataria o comando real do fim."""
        f = self._intencao()
        self.assertEqual(f("antes de ligar o motor, liga o motor"),
                         "LIGAR_MOTOR")


class TestALicaoQueEraUmRecursoInexistente(unittest.TestCase):
    """14/08, 10:57 e 10:58 — ele mandou a MESMA coisa duas vezes seguidas,
    que é o que a gente faz quando desconfia que não pegou:

        ❯ toda vez que eu enviar STATUS pelo whatsapp, por favor, envie o
          status para mim!-Aprenda isso
        ✳ Anotado e aprendido. Está gravado na minha memória e passa a valer
          em TODAS as análises e conversas daqui pra frente.

    Falso duas vezes. Lição vira TEXTO no pedido ao modelo, nunca vira código.
    E o WhatsApp desta ferramenta SÓ ENVIA — não há nada escutando o que
    chega. Ele não estava pedindo uma regra: estava pedindo um recurso que não
    existe, e saiu acreditando que passaria a funcionar.
    """

    def _ns(self):
        return carregar(["_sem_acento", "_LICAO_ACAO_WHATSAPP_RECEBE",
                         "licao_pede_acao"])

    def test_a_frase_dele_e_RECUSADA_com_explicacao(self):
        f = self._ns()["licao_pede_acao"]
        for frase in (
                "toda vez que eu enviar STATUS pelo whatsapp, por favor, "
                "envie o status para mim!",
                "acompanhe o motor,  toda vez que eu enviar STATUS pelo "
                "whatsapp, por favor, envie o status para mim!",
                "sempre que eu mandar status no zap voce responde"):
            recusa, motivo = f(frase)
            self.assertTrue(recusa, f"{frase!r} ainda seria gravada como lição")
            self.assertIn("SÓ ENVIA", motivo,
                          "a recusa precisa DIZER por que não dá")

    def test_a_recusa_diz_o_que_FUNCIONA(self):
        """Recusar sem oferecer a saída é deixar o trader na mão. A resposta
        tem de terminar com o que ele pode fazer AGORA."""
        _, motivo = self._ns()["licao_pede_acao"](
            "toda vez que eu enviar STATUS pelo whatsapp, envie o status")
        self.assertIn("status", motivo.lower())
        self.assertIn("manda no whatsapp", motivo)

    def test_as_licoes_BOAS_dele_continuam_passando(self):
        """A primeira versão desta trava recusava qualquer lição que citasse
        uma ação, e teria apagado DUAS lições boas da lista real dele. Uma
        lição que instrui o raciocínio ('não opine sem olhar o preço') não é
        pedido de recurso — é exatamente o que lição serve para fazer."""
        f = self._ns()["licao_pede_acao"]
        for frase in (
                "tira um print e olha o preco atual, nunca forneca "
                "recomendacoes sem olhar o preco atual",
                "toda vez que pedir alguma analise ou detalhe sobre algum "
                "indicador, tire um print novo e analise para me responder",
                "toda vez que te perguntar um preco de um determinado ativo, "
                "voce acessa yahoo finance e extrai a ultima atualizacao",
                "nunca invente numeros, nunca alucine",
                "so opere em zona de desconto quando a estrutura confirmar"):
            recusa, _ = f(frase)
            self.assertFalse(recusa, f"levou lição boa junto: {frase!r}")

    def test_a_faxina_de_abertura_tambem_usa_a_trava(self):
        """As duas do WhatsApp já estão GRAVADAS na máquina dele desde 14/08,
        entrando em toda análise. Recusar as novas não tira as velhas."""
        ns = carregar(["_sem_acento", "_e_pergunta", "_RE_FATO_EFEMERO",
                       "_e_fato_efemero", "_LICAO_IMPOSSIVEL",
                       "licao_pede_invencao", "_LICAO_ACAO_WHATSAPP_RECEBE",
                       "licao_pede_acao", "licoes_que_nao_ensinam"])
        boas, ruins = ns["licoes_que_nao_ensinam"]([
            "nunca invente numeros, nunca alucine",
            "toda vez que eu enviar STATUS pelo whatsapp, por favor, envie o "
            "status para mim!",
            "tira um print e olha o preco atual, nunca forneca recomendacoes "
            "sem olhar o preco atual",
        ])
        self.assertEqual(len(boas), 2, f"levou lição boa junto — sobrou {boas}")
        self.assertEqual(len(ruins), 1)
        self.assertIn("whatsapp", ruins[0][0].lower())


class TestORecordeAbaixoDoPrecoDeAgora(unittest.TestCase):
    """13/08, 16:31:

        ✳ A máxima histórica do S&P 500 é de aproximadamente 2.924 pontos,
          atingido em abril de 2000 durante a crise da bolsa americana.

    Três erros numa frase, impressos como fato. E no MESMO chat, no MESMO dia,
    o motor dela estava lendo o MES em 7.812 — ela afirmou um teto histórico
    MENOR que o preço que ela própria acabara de ler.

    Não é preciso saber nada de mercado para pegar isso: é aritmética. O
    modelo vai errar de novo; o que dá para impedir é a ferramenta ENTREGAR o
    erro sem conferir o número que ela tem na mão.
    """

    def _conferir(self):
        ns = carregar(["_RE_MAXIMA_HISTORICA", "_RE_NOME_DE_INDICE",
                       "_RE_CONTEXTO_DE_DATA", "_numeros_de_preco",
                       "conferir_maxima_historica"])
        return ns["conferir_maxima_historica"]

    def test_a_frase_REAL_do_log_e_pega(self):
        f = self._conferir()
        texto, valor = f(
            "A máxima histórica do S&P 500 é de aproximadamente 2.924 pontos, "
            "atingido em abril de 2000 durante a crise da bolsa americana.",
            7812.0, "S&P 500")
        self.assertEqual(valor, 2924.0)
        self.assertIn("impossível", texto)
        self.assertIn("7,812.00", texto,
                      "a correção precisa trazer o preço REAL que ela tem")

    def test_o_500_de_SP_500_nao_e_um_preco(self):
        """A primeira versão desta trava acusou 'máxima histórica de 500' na
        frase que fala do S&P 500. Alarme falso ensina o trader a ignorar o
        aviso — que é pior que não ter aviso."""
        ns = carregar(["_RE_MAXIMA_HISTORICA", "_RE_NOME_DE_INDICE",
                       "_RE_CONTEXTO_DE_DATA", "_numeros_de_preco"])
        numeros = ns["_numeros_de_preco"]("máxima histórica do S&P 500 é 2.924")
        self.assertNotIn(500.0, numeros)
        self.assertIn(2924.0, numeros)

    def test_ano_nao_e_preco_mas_nivel_depois_de_em_e(self):
        """'em abril de 2000' é data. 'ficou EM 6.147 pontos' é nível. A
        primeira versão descartava os dois e engolia o caso que importa."""
        f = self._conferir()
        self.assertIsNone(
            f("A máxima histórica do S&P 500 foi registrada em 2025.",
              7812.0)[1])
        self.assertEqual(
            f("O topo histórico ficou em 6.147 pontos em fevereiro de 2025.",
              7812.0)[1], 6147.0)

    def test_sem_preco_real_nao_se_confere_nada(self):
        """Conferir contra um preço chutado seria repetir o defeito que a
        trava existe para pegar."""
        f = self._conferir()
        self.assertIsNone(f("A máxima histórica é de 2.924 pontos.", None)[1])
        self.assertIsNone(f("A máxima histórica é de 2.924 pontos.", 0)[1])

    def test_resposta_correta_passa_intacta(self):
        f = self._conferir()
        for texto in ("A máxima histórica do S&P 500 é cerca de 7.900 pontos.",
                      "Recorde absoluto: 7.850 pontos, batido hoje.",
                      "A máxima histórica caiu 30% desde então.",
                      "O preço está em 7.812 e a máxima do dia foi 7.830.",
                      "Sem relação com recordes, o stop fica em 7.800."):
            saida, valor = f(texto, 7812.0)
            self.assertIsNone(valor, f"alarme falso em {texto!r}")
            self.assertEqual(saida, texto, "o texto bom foi alterado")

    def test_o_preco_vem_do_ativo_DA_PERGUNTA(self):
        """Se o preço de referência viesse do último ativo que o motor leu,
        uma pergunta sobre ouro seria conferida contra o preço do índice."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _preco_de_referencia")
        bloco = fonte[i:i + 1400]
        self.assertIn("simbolo_do_texto(pergunta)", bloco)
        self.assertIn("lido[0] == simbolo", bloco,
                      "a leitura do motor entrou sem conferir se é o mesmo ativo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
