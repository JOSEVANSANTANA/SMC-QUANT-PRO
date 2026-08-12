"""O que a TIGER entende quando o trader fala.

Cada teste aqui nasceu de uma frase REAL do chat que voltou errada. As frases
estão nos comentários, com o que ela respondeu antes.
"""

import unittest

from harness import carregar


def _ns_historico(sinais):
    return carregar(
        ["_sem_acento", "_norm_busca", "_num", "responder_historico_sugestoes",
         "pergunta_sobre_historico_sugestoes", "_RE_HISTORICO_SUG",
         "_RE_HISTORICO_PEDE"],
        stubs={"carregar_sinais_log": lambda: list(sinais),
               "_e_da_conta_ativa": lambda r: True,
               "unicodedata": __import__("unicodedata")})


def _ns_intencao():
    """interpretar_intencao puxa meio arquivo junto. Os pedaços que ela chama
    mas que não são o objeto deste teste entram como stub honesto (devolvendo
    'não é comigo'), para o teste medir só o roteamento."""
    return carregar(
        ["_sem_acento", "_norm_busca", "_RE_QUAL_LADO", "pergunta_qual_lado",
         "_RE_DEFINIR_NIVEL", "interpretar_niveis_da_posicao",
         "_RE_NIVEL", "_RE_NIVEL_TEORIA", "pergunta_pede_nivel",
         "_MOTOR_SUBSTANTIVOS", "_MOTOR_ARTIGO", "_MOTOR_NEGADO",
         "_MOTOR_DESLIGAR", "_MOTOR_PARA", "_MOTOR_LIGAR",
         "_PRINT_SOZINHO", "_PRINT_COM_AGORA",
         "_RE_ESQUECER", "pedido_de_esquecer",
         "_COMANDOS_CONHECIDOS", "_distancia_edicao", "corrigir_digitacao",
         "interpretar_intencao", "processar_turno_chat"],
        stubs={"extrair_licao": lambda t: None,
               "interpretar_configuracao": lambda t: None,
               "pergunta_sobre_configuracao": lambda t: False,
               "simbolo_do_texto": lambda t: None,
               "unicodedata": __import__("unicodedata")})


SINAIS = [
    {"id": 1, "data_hora": "10/08/2026 13:02:41", "direcao": "BUY",
     "ativo": "MESU6", "entry": 7773.25, "stop": 7768.25, "tp1": 7783.25,
     "tp2": 7790.0, "decisao": None},
    {"id": 2, "data_hora": "10/08/2026 13:40:10", "direcao": "SELL",
     "ativo": "MGCV6", "entry": 3100.0, "stop": 3105.0, "tp1": 3090.0,
     "tp2": 3080.0, "decisao": "NAO_OPEROU"},
]


class TestHistoricoDeSugestoes(unittest.TestCase):
    def test_qual_nao_e_um_ativo(self):
        """A frase: 'qual a utima sugestao ?'
        A resposta antiga: 'Procurei no histórico e NÃO há sugestão de QUAL
        registrada.' — porque o padrão `[A-Z]{3,6}\\d{0,2}` casava a palavra
        QUAL no texto passado para maiúsculas. Qualquer palavra virava ticker."""
        ns = _ns_historico(SINAIS)
        r = ns["responder_historico_sugestoes"]("qual a utima sugestao ?")
        self.assertNotIn("QUAL", r)
        # Sem ativo citado, a resposta é a última sugestão do arquivo — a de
        # MGCV6, que é a mais recente. O defeito antigo trocava isso por uma
        # negativa sobre um ativo que não existe.
        self.assertIn("MGCV6", r)

    def test_outras_palavras_comuns_tambem_nao_sao_ativos(self):
        ns = _ns_historico(SINAIS)
        for frase in ("qual foi a ULTIMA sugestao",
                      "me diz QUAIS foram as sugestoes",
                      "TEVE alguma sugestao hoje?"):
            r = ns["responder_historico_sugestoes"](frase)
            self.assertIsNotNone(r, frase)
            for palavra in ("QUAL", "QUAIS", "ULTIMA", "TEVE", "ALGUMA"):
                self.assertNotIn(f"sugestão de {palavra}", r, frase)

    def test_ativo_de_verdade_ausente_e_dito_como_ausente(self):
        """Isto NÃO pode regredir: quando ele cita um ativo que não está no
        histórico, a resposta certa é 'procurei e não achei' — nunca devolver
        a sugestão de OUTRO ativo."""
        ns = _ns_historico(SINAIS)
        r = ns["responder_historico_sugestoes"]("teve sugestão de PETR4 hoje?")
        self.assertIn("PETR4", r)
        self.assertIn("NÃO há sugestão", r)

    def test_ativo_presente_devolve_os_numeros_do_disco(self):
        ns = _ns_historico(SINAIS)
        r = ns["responder_historico_sugestoes"]("qual foi a última sugestão de MGCV6?")
        self.assertIn("MGCV6", r)
        self.assertIn("3100", r)
        self.assertIn("3105", r)

    def test_historico_vazio_diz_que_esta_vazio(self):
        ns = _ns_historico([])
        r = ns["responder_historico_sugestoes"]("qual a ultima sugestao?")
        self.assertIn("vazio", r)
        # E não pode virar "não sei" nem "estou sem acesso".
        self.assertNotIn("não tenho acesso", r)


class TestQualLado(unittest.TestCase):
    def test_compro_ou_vendo_vira_leitura_do_grafico(self):
        """A frase: 'compro ou vendo ?'
        A resposta antiga: o despejo genérico de 'não tenho como responder'.
        É a pergunta mais direta da mesa e não dá para respondê-la sem olhar
        o gráfico — então ela olha."""
        ns = _ns_intencao()
        for frase in ("compro ou vendo ?", "compro ou vendo",
                      "é compra ou venda agora?", "qual o lado?",
                      "qual a direção?", "devo comprar?",
                      "vale a pena vender aqui?", "long ou short?"):
            self.assertEqual(ns["interpretar_intencao"](frase), "VER_GRAFICO",
                             frase)

    def test_pergunta_sobre_a_propria_posicao_nao_e_pergunta_de_lado(self):
        """'estou comprado ou vendido?' é pergunta de POSIÇÃO — quem responde
        é o diário, não uma leitura nova do gráfico."""
        ns = _ns_intencao()
        self.assertFalse(ns["pergunta_qual_lado"]("estou comprado ou vendido?"))
        self.assertFalse(ns["pergunta_qual_lado"]("minha posição é de compra?"))


class TestDefinirNiveis(unittest.TestCase):
    def test_le_stop_e_alvo_da_frase(self):
        """Posição vinda da plataforma entra com 'stop None · alvo None'.
        Agora o trader informa, e é código que grava."""
        ns = _ns_intencao()
        d = ns["interpretar_niveis_da_posicao"](
            "o stop do MESU6 é 7760 e o alvo é 7800", ["MESU6"])
        self.assertEqual(d, {"ativo": "MESU6", "stop": 7760.0, "tp1": 7800.0})

    def test_so_o_stop(self):
        ns = _ns_intencao()
        d = ns["interpretar_niveis_da_posicao"]("o stop é 7760", ["MESU6"])
        self.assertEqual(d["stop"], 7760.0)
        self.assertIsNone(d["tp1"])
        self.assertIsNone(d["ativo"])

    def test_decimal_com_virgula(self):
        ns = _ns_intencao()
        d = ns["interpretar_niveis_da_posicao"]("stop em 7760,25", ["MESU6"])
        self.assertEqual(d["stop"], 7760.25)

    def test_sem_numero_nao_grava_nada(self):
        ns = _ns_intencao()
        # Sem número não há o que gravar — e chutar um nível é chutar risco.
        self.assertIsNone(
            ns["interpretar_niveis_da_posicao"]("o stop está apertado", ["MESU6"]))

    def test_pergunta_nunca_vira_definicao(self):
        """'onde ponho o stop?' pede um número; não traz um. Se isto regredir,
        uma PERGUNTA passa a sobrescrever o stop de uma posição aberta."""
        ns = _ns_intencao()
        for frase in ("onde ponho o stop?", "qual o stop de MESU6?",
                      "quanto deve ser o alvo?", "como fica o stop?"):
            self.assertNotEqual(
                _tipo(ns["interpretar_intencao"](frase)), "DEFINIR_NIVEIS", frase)

    def test_frase_afirmativa_vira_definicao(self):
        ns = _ns_intencao()
        self.assertEqual(
            _tipo(ns["interpretar_intencao"]("o stop do MESU6 é 7760")),
            "DEFINIR_NIVEIS")

    def test_ativo_so_e_reconhecido_se_estiver_na_lista(self):
        """A lista vem do diário. Assim a frase não inventa um ticker."""
        ns = _ns_intencao()
        d = ns["interpretar_niveis_da_posicao"](
            "o stop do MESU6 é 7760", ["MNQZ5"])
        self.assertIsNone(d["ativo"])


class TestTurnoDoChat(unittest.TestCase):
    def test_definir_niveis_nao_pede_confirmacao(self):
        # Ele está me DANDO um dado, não mandando operar.
        ns = _ns_intencao()
        tipo, dado = ns["processar_turno_chat"]("o stop do MESU6 é 7760")
        self.assertEqual(tipo, "DEFINIR_NIVEIS")
        self.assertIn("7760", dado)

    def test_acatar_continua_pedindo_confirmacao(self):
        # Isto NÃO pode afrouxar: ACATAR pode disparar ordem real.
        ns = _ns_intencao()
        self.assertEqual(ns["processar_turno_chat"]("acatar"),
                         ("PEDIR_CONFIRMACAO", "ACATAR"))


def _tipo(intencao):
    return intencao[0] if isinstance(intencao, tuple) else intencao


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestAprenderTudoIsso(unittest.TestCase):
    """10/08 18:09 e 18:10 — ele pediu duas vezes e as duas caíram no despejo
    genérico ("não tenho como responder isso com segurança agora"), enquanto
    "liste o que você aprendeu" respondia "ainda não gravei nenhuma lição"."""

    def _f(self):
        return carregar(["_LICAO_VERBO", "_LICAO_OBJETO", "_LICAO_SOBRA",
                         "extrair_licao"])["extrair_licao"]

    def test_as_duas_frases_do_log(self):
        f = self._f()
        # "" = a lição é o turno anterior dele. O que não pode é devolver None,
        # que é o que mandava a frase para o modelo e virava despejo.
        self.assertEqual(f("aprenda tudo isso"), "")
        self.assertEqual(f("aprenda isso tudo que pedi acima"), "")

    def test_variantes_da_mesma_intencao(self):
        f = self._f()
        for frase in ("aprenda isso", "aprenda tudo", "memorize tudo isso",
                      "guarde isso tudo", "anota tudo isso por favor",
                      "aprenda isso que eu falei", "memorize isso aí"):
            self.assertEqual(f(frase), "", frase)

    def test_o_que_pedi_acima_nao_vira_a_licao(self):
        """Bug encontrado ao escrever este teste: a forma PREFIXO tratava o
        'que' de 'que pedi acima' como separador e gravava a lição
        'pedi acima' — uma frase sem sentido, na memória permanente."""
        f = self._f()
        self.assertNotEqual(f("aprenda isso tudo que pedi acima"), "pedi acima")

    def test_licao_de_verdade_continua_sendo_extraida(self):
        f = self._f()
        self.assertEqual(
            f("nunca opere contra o H4 depois das 15h, aprenda isso"),
            "nunca opere contra o H4 depois das 15h")
        self.assertEqual(f("aprenda: nunca opere em premium"),
                         "nunca opere em premium")
        self.assertEqual(f("aprenda que o dia começa as 19h"),
                         "o dia começa as 19h")
        self.assertEqual(
            f("É SÓ VOCÊ OLHAR NOS HISTÓRICOS DE SUGESTÕES-APRENDA ISSO"),
            "É SÓ VOCÊ OLHAR NOS HISTÓRICOS DE SUGESTÕES")

    def test_frase_que_nao_e_licao_continua_nao_sendo(self):
        f = self._f()
        for frase in ("eu quero aprender isso melhor", "tira um print",
                      "qual a ultima sugestao?", "liga o motor"):
            self.assertIsNone(f(frase), frase)


class TestMostrarPrint(unittest.TestCase):
    """10/08 18:09 — 'me mostre o print' caiu no despejo genérico, com o PNG
    salvo no disco ali do lado. Abrir arquivo local não depende de cota."""

    def test_pedidos_de_ver_a_imagem(self):
        ns = _ns_intencao()
        for frase in ("me mostre o print", "mostra o print",
                      "cadê o print?", "abre a imagem",
                      "onde está o screenshot?"):
            self.assertEqual(ns["interpretar_intencao"](frase),
                             "MOSTRAR_PRINT", frase)

    def test_pedir_ANALISE_nao_e_pedir_para_ver(self):
        """'analisa o print' continua sendo leitura do gráfico, não abrir um
        arquivo — se isto regredir, ele perde a análise."""
        ns = _ns_intencao()
        for frase in ("analisa o print", "lê o gráfico do print",
                      "me diz o que tem na imagem"):
            self.assertNotEqual(ns["interpretar_intencao"](frase),
                                "MOSTRAR_PRINT", frase)

    def test_e_uma_acao_local_sem_confirmacao(self):
        ns = _ns_intencao()
        self.assertEqual(ns["processar_turno_chat"]("me mostre o print"),
                         ("EXECUTAR", "MOSTRAR_PRINT"))


class TestConfirmacaoDoAcatar(unittest.TestCase):
    """11/08, 19:21 — ele digitou ACATAR e relatou que "nada aconteceu".

        ❯ ACATAR
        ✳ "Confirmando: ACATAR o BUY MESU6 ... Responda 'sim'"

    Do lado do código estava tudo certo: ela perguntou e ficou esperando. Do
    lado dele, ele deu a ordem e o programa devolveu uma pergunta — e o
    indicador de estado voltava para "pronta" logo depois, sem nenhum sinal de
    que havia decisão pendente.
    """

    def test_repetir_o_comando_confirma(self):
        """ACATAR duas vezes é a mesma ordem, dita pela mesma pessoa. Não é
        ambíguo."""
        ns = _ns_intencao()
        self.assertEqual(
            ns["processar_turno_chat"]("acatar", confirmacao_pendente="ACATAR"),
            ("EXECUTAR", "ACATAR"))

    def test_o_primeiro_comando_continua_nao_executando(self):
        """A trava de responsabilidade não pode afrouxar: dinheiro nunca sai de
        um comando só."""
        ns = _ns_intencao()
        self.assertEqual(ns["processar_turno_chat"]("acatar"),
                         ("PEDIR_CONFIRMACAO", "ACATAR"))

    def test_sim_continua_confirmando(self):
        ns = _ns_intencao()
        self.assertEqual(
            ns["processar_turno_chat"]("sim", confirmacao_pendente="ACATAR"),
            ("EXECUTAR", "ACATAR"))

    def test_dispensar_cancela_um_acatar_pendente(self):
        ns = _ns_intencao()
        self.assertEqual(
            ns["processar_turno_chat"]("dispensar", confirmacao_pendente="ACATAR"),
            ("CONF_CANCELADA", None))

    def test_comando_DIFERENTE_nao_confirma_por_acidente(self):
        """Repetir ZERAR não pode confirmar um ACATAR pendente — são ordens
        diferentes, e uma delas mexe em dinheiro."""
        ns = _ns_intencao()
        tipo, _ = ns["processar_turno_chat"]("zera o ciclo",
                                             confirmacao_pendente="ACATAR")
        self.assertNotEqual(tipo, "EXECUTAR")

    def test_trocar_de_assunto_derruba_a_confirmacao(self):
        ns = _ns_intencao()
        tipo, _ = ns["processar_turno_chat"]("status", confirmacao_pendente="ACATAR")
        self.assertEqual(tipo, "EXECUTAR")   # executa o STATUS, não o ACATAR
