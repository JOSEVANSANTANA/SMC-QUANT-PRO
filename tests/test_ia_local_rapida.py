"""A IA local era lenta por minha causa, não por ser local.

19/08, ele: "esta muito lento para pensar... é muito burra... estou seriamente
considerando desinstalar local e deixar somente via api".

Fui medir onde o tempo ia. O modelo não era o problema principal — a porta era.
Eu falava com o Ollama pelo endereço que IMITA a OpenAI
(/v1/chat/completions), e por ali só passam os campos que a OpenAI entende.
Faltavam exatamente os dois que mandam no relógio:

  • `keep_alive`: sem ele o Ollama tira o modelo da memória logo depois de
    responder. A pergunta seguinte relê 3 a 5 GB do disco ANTES de começar a
    pensar. Toda resposta era, na prática, uma primeira resposta.
  • `num_predict`: o teto de 1200 tokens veio junto com o código da nuvem. Lá
    isso sai em segundos. Aqui, a uns 8 tokens por segundo, são dois minutos e
    meio para uma frase que ele lê em dez segundos.

E havia um terceiro, na leitura de gráfico: o `keep_alive` da visão estava
fixo em "12m" contra um ciclo do motor que sai de fábrica em 15 minutos. O
modelo era descarregado TRÊS MINUTOS antes de ser chamado de novo — um
keep_alive menor que o ciclo é o mesmo que nenhum.
"""

import unittest

from harness import carregar, fonte_do_arquivo


class _RespostaFalsa:
    def __init__(self, dados, status=200):
        self._dados = dados
        self.status_code = status
        self.text = str(dados)

    def json(self):
        return self._dados


class _RequestsFalso:
    """Guarda o que foi enviado, em vez de ir à rede."""

    def __init__(self, dados=None, status=200):
        self.chamadas = []
        self._dados = dados if dados is not None else {
            "message": {"content": "resposta do modelo local"}}
        self._status = status

    def post(self, url, json=None, timeout=None, **kw):
        self.chamadas.append({"url": url, "corpo": json or {},
                              "timeout": timeout})
        return _RespostaFalsa(self._dados, self._status)


class TestAPortaNativaDoOllama(unittest.TestCase):

    def _ns(self, fake):
        return carregar(["KEEP_ALIVE_LOCAL", "TETO_SAIDA_LOCAL",
                         "_pedir_ollama"], stubs={"requests": fake})

    def test_manda_KEEP_ALIVE(self):
        """Sem isto o modelo sai da memória entre uma pergunta e a seguinte, e
        cada resposta paga de novo a leitura de vários GB do disco."""
        fake = _RequestsFalso()
        ns = self._ns(fake)
        ns["_pedir_ollama"]("http://localhost:11434/api/chat", "local",
                            "qwen2.5:7b", [{"role": "user", "content": "oi"}])
        corpo = fake.chamadas[0]["corpo"]
        self.assertEqual(corpo.get("keep_alive"), ns["KEEP_ALIVE_LOCAL"])

    def test_manda_TETO_DE_SAIDA_menor_que_o_da_nuvem(self):
        """1200 tokens saem em segundos na nuvem e em minutos aqui."""
        fake = _RequestsFalso()
        ns = self._ns(fake)
        ns["_pedir_ollama"]("http://localhost:11434/api/chat", "local",
                            "qwen2.5:7b", [{"role": "user", "content": "oi"}])
        corpo = fake.chamadas[0]["corpo"]
        self.assertEqual(corpo["options"]["num_predict"], ns["TETO_SAIDA_LOCAL"])
        self.assertLess(ns["TETO_SAIDA_LOCAL"], 1200)

    def test_temperatura_continua_baixa(self):
        """Numa mesa, criatividade é o defeito: é ela que faz um modelo
        pequeno completar um número que não sabe."""
        fake = _RequestsFalso()
        ns = self._ns(fake)
        ns["_pedir_ollama"]("http://x", "local", "m", [])
        self.assertLessEqual(fake.chamadas[0]["corpo"]["options"]["temperature"],
                             0.3)

    def test_le_a_resposta_no_formato_do_ollama(self):
        fake = _RequestsFalso({"message": {"content": "  olá  "}})
        ns = self._ns(fake)
        self.assertEqual(ns["_pedir_ollama"]("http://x", "local", "m", []),
                         "olá")

    def test_resposta_estranha_nao_quebra(self):
        for dados in ({}, {"message": {}}, {"message": {"content": None}}):
            fake = _RequestsFalso(dados)
            ns = self._ns(fake)
            self.assertEqual(ns["_pedir_ollama"]("http://x", "local", "m", []), "")

    def test_erro_HTTP_levanta_para_quem_chamou_tratar(self):
        fake = _RequestsFalso({"error": "model not found"}, status=404)
        ns = self._ns(fake)
        with self.assertRaises(RuntimeError):
            ns["_pedir_ollama"]("http://x", "local", "m", [])

    def test_o_provedor_local_aponta_para_a_porta_NATIVA(self):
        ns = carregar(["PROVEDORES_IA"])
        local = ns["PROVEDORES_IA"]["local"]
        self.assertEqual(local["formato"], "ollama")
        self.assertIn("/api/chat", local["url"])
        self.assertNotIn("/v1/", local["url"])


class TestUmaPortaSoParaTodosOsProvedores(unittest.TestCase):
    """O mesmo `if formato == 'anthropic' ... else openai` estava escrito em
    TRÊS lugares. Quando a IA local ganhou porta própria, dois deles
    continuariam mandando o formato da OpenAI para o endereço nativo do Ollama
    — e o teste de instalação passaria a falhar sem motivo aparente."""

    def _ns(self):
        marcas = {}

        def _falso(nome):
            def fn(url, chave, modelo, mensagens, timeout=None):
                marcas["quem"] = nome
                marcas["timeout"] = timeout
                return nome
            return fn

        ns = carregar(["pedir_ao_provedor"],
                      stubs={"_pedir_anthropic": _falso("anthropic"),
                             "_pedir_ollama": _falso("ollama"),
                             "_pedir_openai": _falso("openai")})
        return ns, marcas

    def test_cada_formato_vai_para_a_sua_porta(self):
        ns, marcas = self._ns()
        for formato, esperado in (("anthropic", "anthropic"),
                                  ("ollama", "ollama"),
                                  ("openai", "openai"),
                                  (None, "openai")):
            ns["pedir_ao_provedor"]({"formato": formato, "url": "u"},
                                    "k", "m", [])
            self.assertEqual(marcas["quem"], esperado, repr(formato))

    def test_o_timeout_pedido_chega_ao_provedor(self):
        ns, marcas = self._ns()
        ns["pedir_ao_provedor"]({"formato": "ollama", "url": "u"},
                                "k", "m", [], 25)
        self.assertEqual(marcas["timeout"], 25)

    def test_nenhum_outro_lugar_despacha_provedor_na_mao(self):
        """Se voltar a existir um `if formato == 'anthropic'` solto por aí, a
        próxima porta nova vai ser esquecida nele."""
        fonte = fonte_do_arquivo()
        self.assertEqual(fonte.count('== "anthropic"'), 1,
                         "voltou a haver despacho de provedor fora de "
                         "pedir_ao_provedor()")
        i = fonte.index("def pedir_ao_provedor(")
        self.assertIn('== "anthropic"', fonte[i:i + 1500],
                      "o único despacho tem de ser o de dentro da porta única")


class TestAquecerAReservaNaHoraCERTA(unittest.TestCase):
    """A primeira resposta local é sempre a pior: o modelo tem de sair do
    disco. Deixá-lo residente o tempo todo resolveria — e seria uma troca ruim,
    porque um 7B ocupa vários GB da RAM dele durante o pregão inteiro, para o
    caso de talvez precisar.

    O gatilho certo é o estouro da cota: ali a reserva ESTÁ prestes a ser
    chamada."""

    def _ns(self):
        return carregar(["INTERVALO_AQUECIMENTO_LOCAL", "_aquecimento_local",
                         "deve_aquecer_ia_local"])

    def test_a_primeira_vez_aquece(self):
        ns = self._ns()
        self.assertTrue(ns["deve_aquecer_ia_local"](agora=1000.0))

    def test_uma_rajada_de_erros_NAO_dispara_dez_carregamentos(self):
        """Dez 429 seguidos são um evento só, não dez."""
        ns = self._ns()
        self.assertTrue(ns["deve_aquecer_ia_local"](agora=1000.0))
        for t in (1001.0, 1100.0, 1200.0):
            self.assertFalse(ns["deve_aquecer_ia_local"](agora=t), t)

    def test_depois_do_intervalo_volta_a_aquecer(self):
        ns = self._ns()
        ns["deve_aquecer_ia_local"](agora=1000.0)
        depois = 1000.0 + ns["INTERVALO_AQUECIMENTO_LOCAL"] + 1
        self.assertTrue(ns["deve_aquecer_ia_local"](agora=depois))

    def test_o_estouro_de_cota_e_que_dispara(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def registrar_falha_modelo(")
        bloco = fonte[i:i + 1400]
        self.assertIn("_aquecer_reserva_em_segundo_plano()", bloco)
        self.assertIn('tipo in ("cota", "transitorio")', bloco)

    def test_aquecer_nunca_derruba_o_programa(self):
        """Aquecer é um luxo, e luxo que derruba o programa não é luxo."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def aquecer_ia_local(")
        self.assertIn("except Exception", fonte[i:i + 900])
        j = fonte.index("def _aquecer_reserva_em_segundo_plano(")
        self.assertIn("daemon=True", fonte[j:j + 500])


class TestOKeepAliveDaVisaoAcompanhaOCiclo(unittest.TestCase):
    """Estava fixo em '12m' contra um ciclo que sai de fábrica em 15 minutos:
    o modelo era descarregado três minutos ANTES de ser chamado de novo, e
    cada leitura recomeçava do disco. Um keep_alive menor que o ciclo é o
    mesmo que nenhum."""

    def _ns(self):
        return carregar(["_keep_alive_do_ciclo"],
                        stubs={"carregar_config": lambda: {}})

    def _minutos(self, texto):
        return int(str(texto).rstrip("m"))

    def test_e_sempre_MAIOR_que_o_intervalo_do_motor(self):
        ns = self._ns()
        for intervalo in (1, 5, 10, 15, 20, 30):
            valor = self._minutos(ns["_keep_alive_do_ciclo"](intervalo))
            self.assertGreater(valor, intervalo, f"intervalo {intervalo}")

    def test_o_caso_QUE_ESTAVA_ERRADO(self):
        """15 minutos de ciclo com 12 de residência."""
        ns = self._ns()
        self.assertGreater(self._minutos(ns["_keep_alive_do_ciclo"](15)), 15)

    def test_tem_TETO_para_nao_travar_a_maquina_dele(self):
        """Manter um modelo de visão residente por horas é RAM parada o dia
        inteiro. Com ciclo muito longo, vale mais recarregar."""
        ns = self._ns()
        self.assertLessEqual(self._minutos(ns["_keep_alive_do_ciclo"](600)), 45)

    def test_configuracao_estragada_nao_quebra_a_leitura(self):
        ns = self._ns()
        for ruim in (None, "", "abc", -3, 0):
            self.assertRegex(str(ns["_keep_alive_do_ciclo"](ruim)), r"^\d+m$",
                             repr(ruim))

    def test_a_leitura_de_grafico_usa_esse_calculo(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def analisar_grafico_local(")
        bloco = fonte[i:i + 3000]
        self.assertIn("keep_alive or _keep_alive_do_ciclo()", bloco)
        self.assertNotIn('"keep_alive": "12m"', bloco)


if __name__ == "__main__":
    unittest.main()
