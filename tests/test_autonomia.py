"""A ferramenta errada para o trabalho — e a certa.

Durante três versões eu tratei a VWAP inventada como problema de PROMPT, depois
como problema de GUARDA. Era problema de ARQUITETURA, e o diagnóstico cabe numa
frase: **um LLM não lê pixel, ele prevê o texto mais provável.**

Por isso ele nunca diz "não sei" — ele completa. Com a legenda mostrando

    VWAP 7769.56

ele escreveu "a VWAP está exatamente em 7752.34, conforme indicado na legenda".
A palavra "exatamente" e a citação da fonte estavam lá. O número, não.

"VWAP 7769.56" é TEXTO IMPRESSO: pixels nítidos, fonte digital, alto contraste.
Isso é trabalho de OCR, que lê com precisão perto de 100% e não completa o que
não viu. E OCR não precisa de chave, de internet nem de cota — os dois sistemas
já trazem um motor embutido (Vision no macOS, Windows.Media.Ocr no Windows).

Este arquivo testa o PARSER: dado o texto que o OCR devolve, o número certo sai.
É a parte que carrega o risco de erro — o motor de OCR em si é do sistema
operacional e não é nosso para testar aqui.

A legenda abaixo é a do print real da Tradovate de 12/08/2026 15:45, candle das
13:25, transcrita rótulo por rótulo.
"""

import unittest

from harness import carregar, fonte_do_arquivo, pular_se_faltar

LEGENDA_REAL = """12/08/2026 13:25
PSAR 7764.20
SMA 7767.58
SMA 7766.04
RSI 55
MIDDLE 50
OVERBOU 70
OVERSOL 30
VWAP 7769.56
OPEN 7770.25
HIGH 7771.25
LOW 7768.50
CLOSE 7769.00
VOLUME 3943"""


def _ns():
    return carregar(
        ["_sem_acento", "_ROTULOS_LEGENDA", "_ROTULOS_IGNORADOS",
         "_numero_da_legenda", "ler_indicadores_da_legenda",
         "_APELIDOS_INDICADOR", "chave_do_indicador",
         "resposta_do_indicador_lido"],
        stubs={"unicodedata": __import__("unicodedata")})


class TestLerALegenda(unittest.TestCase):

    def test_a_vwap_do_print_real_sai_certa(self):
        """O número que o modelo errou. Este teste é a razão de tudo isto."""
        ns = _ns()
        v = ns["ler_indicadores_da_legenda"](LEGENDA_REAL)
        self.assertEqual(v["VWAP"], 7769.56)
        self.assertNotEqual(v["VWAP"], 7752.34)     # o que ele respondeu

    def test_as_duas_medias_viram_lista_e_nenhuma_e_escolhida_escondido(self):
        """Há DUAS SMAs naquele gráfico. Dizer 'a média é 7767.58' seria
        escolher uma às escondidas — e foi inventando uma terceira (7751.28)
        que ele errou."""
        ns = _ns()
        v = ns["ler_indicadores_da_legenda"](LEGENDA_REAL)
        self.assertEqual(v["SMA"], [7767.58, 7766.04])

    def test_o_candle_inteiro_e_lido(self):
        ns = _ns()
        v = ns["ler_indicadores_da_legenda"](LEGENDA_REAL)
        self.assertEqual(v["ABERTURA"], 7770.25)
        self.assertEqual(v["MAXIMA"], 7771.25)
        self.assertEqual(v["MINIMA"], 7768.50)
        self.assertEqual(v["FECHAMENTO"], 7769.00)
        self.assertEqual(v["VOLUME"], 3943)
        self.assertEqual(v["RSI"], 55)
        self.assertEqual(v["PSAR"], 7764.20)

    def test_parametro_de_indicador_nao_vira_preco(self):
        """MIDDLE 50, OVERBOU 70 e OVERSOL 30 são a CONFIGURAÇÃO do RSI, não
        níveis de preço. Ler 70 como se fosse um nível passaria despercebido e
        contaminaria a análise inteira."""
        ns = _ns()
        v = ns["ler_indicadores_da_legenda"](LEGENDA_REAL)
        for proibido in ("MIDDLE", "OVERBOU", "OVERSOL"):
            self.assertNotIn(proibido, v)
        self.assertNotIn(70, v.values())
        self.assertNotIn(30, v.values())

    def test_texto_vazio_devolve_vazio_e_nao_zero(self):
        """'Não li' e 'não tem' são coisas diferentes. Confundir as duas é
        exatamente a regra anti-invenção sendo quebrada."""
        ns = _ns()
        for t in ("", None, "   ", "nenhum texto reconhecido aqui"):
            self.assertEqual(ns["ler_indicadores_da_legenda"](t), {})

    def test_le_os_dois_formatos_de_numero(self):
        ns = _ns()
        self.assertEqual(ns["_numero_da_legenda"]("7769.56"), 7769.56)
        self.assertEqual(ns["_numero_da_legenda"]("7.769,56"), 7769.56)
        self.assertEqual(ns["_numero_da_legenda"]("7,769.56"), 7769.56)
        self.assertEqual(ns["_numero_da_legenda"]("3943"), 3943.0)
        self.assertEqual(ns["_numero_da_legenda"]("-12,5"), -12.5)

    def test_o_que_nao_e_numero_nao_vira_numero(self):
        ns = _ns()
        for t in ("", "VWAP", "--", ".", None, "abc"):
            self.assertIsNone(ns["_numero_da_legenda"](t), repr(t))

    def test_aceita_dois_pontos_e_igual_entre_rotulo_e_valor(self):
        """Nem toda plataforma escreve 'VWAP 7769.56'."""
        ns = _ns()
        for linha in ("VWAP: 7769.56", "VWAP = 7769.56", "VWAP   7769.56"):
            self.assertEqual(
                ns["ler_indicadores_da_legenda"](linha).get("VWAP"), 7769.56,
                linha)

    def test_data_e_hora_nao_viram_indicador(self):
        """A primeira linha da legenda é '12/08/2026 13:25'."""
        ns = _ns()
        v = ns["ler_indicadores_da_legenda"]("12/08/2026 13:25")
        self.assertEqual(v, {})


class TestOApelidoQueOTraderUsa(unittest.TestCase):
    """Ele não digita 'SMA'. Ele digita 'a média móvel de 50'."""

    def test_reconhece_como_ele_fala(self):
        ns = _ns()
        for falado, esperado in (("VWAP", "VWAP"), ("vwap", "VWAP"),
                                 ("a média móvel de 50", "SMA"),
                                 ("média móvel", "SMA"), ("mm", "SMA"),
                                 ("o RSI", "RSI"), ("volume", "VOLUME"),
                                 ("o PSAR", "PSAR")):
            self.assertEqual(ns["chave_do_indicador"](falado), esperado, falado)

    def test_o_que_nao_e_indicador_devolve_nada(self):
        ns = _ns()
        for t in ("MACD", "ichimoku", "", None, "compro ou vendo"):
            self.assertIsNone(ns["chave_do_indicador"](t), repr(t))


class TestARespostaSemModelo(unittest.TestCase):

    def test_responde_o_numero_lido(self):
        ns = _ns()
        v = ns["ler_indicadores_da_legenda"](LEGENDA_REAL)
        r = ns["resposta_do_indicador_lido"]("VWAP", v)
        self.assertIn("7769.56", r)
        self.assertNotIn("7752.34", r)

    def test_diz_que_o_numero_nao_passou_por_modelo(self):
        """Ele precisa saber POR QUE pode confiar neste número e não no de
        antes. Sem essa frase, é só mais um número na tela."""
        ns = _ns()
        v = ns["ler_indicadores_da_legenda"](LEGENDA_REAL)
        r = ns["resposta_do_indicador_lido"]("VWAP", v)
        self.assertIn("não passou por modelo", r)
        self.assertIn("sem API", r)

    def test_com_duas_medias_ela_mostra_as_duas_e_pergunta(self):
        ns = _ns()
        v = ns["ler_indicadores_da_legenda"](LEGENDA_REAL)
        r = ns["resposta_do_indicador_lido"]("a média móvel", v)
        self.assertIn("7767.58", r)
        self.assertIn("7766.04", r)
        self.assertIn("período", r)

    def test_indicador_ausente_devolve_None_e_nao_uma_desculpa(self):
        """None faz o caminho normal (modelo + guardas) continuar. Uma resposta
        de desculpa aqui MATARIA esse caminho — a camada de OCR só pode
        adicionar certeza, nunca tirar resposta."""
        ns = _ns()
        v = ns["ler_indicadores_da_legenda"](LEGENDA_REAL)
        self.assertIsNone(ns["resposta_do_indicador_lido"]("MACD", v))
        self.assertIsNone(ns["resposta_do_indicador_lido"]("VWAP", {}))


class TestOCRLigadoNoCaminhoCerto(unittest.TestCase):

    def test_o_ocr_e_tentado_ANTES_do_modelo(self):
        """Se rodasse depois, teria virado mais uma conferência — e o número
        errado continuaria sendo o primeiro a aparecer na tela."""
        fonte = fonte_do_arquivo()
        i_ocr = fonte.index("self._ler_nivel_por_ocr(caminho, texto)")
        i_modelo = fonte.index("threading.Thread(target=self._chat_worker,\n"
                               "                                 args=(pedido, caminho)")
        self.assertLess(i_ocr, i_modelo)

    def test_a_fronteira_de_sistema_e_respeitada(self):
        """Vision e Windows.Media.Ocr são específicos de cada sistema — e a
        regra da casa é que essa diferença mora só no plataforma.py."""
        import os
        from harness import RAIZ
        with open(os.path.join(RAIZ, "plataforma.py"), encoding="utf-8") as f:
            plat = f.read()
        self.assertIn("def ler_texto_da_imagem", plat)
        self.assertIn("def motor_de_ocr", plat)
        self.assertIn("VNRecognizeTextRequest", plat)
        self.assertIn("winrt.windows.media.ocr", plat)
        fonte = fonte_do_arquivo()
        self.assertNotIn("VNRecognizeTextRequest", fonte)

    def test_sem_motor_de_ocr_o_app_avisa_uma_vez(self):
        """Recurso que falha calado é pior que recurso ausente."""
        fonte = fonte_do_arquivo()
        self.assertIn("_avisou_sem_ocr", fonte)
        self.assertIn("motor_de_ocr()", fonte)

    def test_falha_do_ocr_nao_derruba_a_resposta(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _ler_nivel_por_ocr")
        bloco = fonte[i:i + 1600]
        self.assertIn("except Exception", bloco)
        self.assertIn("return None", bloco)


class TestIALocalSemChave(unittest.TestCase):
    """O 12/08 mostrou o buraco: 'You have no credits remaining'. Um cérebro
    que depende de saldo some justamente no dia em que o saldo acaba."""

    def _ns(self):
        return carregar(
            ["PROVEDORES_IA", "ORDEM_PROVEDORES", "ia_local_no_ar",
             "provedores_configurados", "carregar_chave_provedor", "ia_local_ligada"],
            stubs={"carregar_config": lambda: {},
                   "carregar_api_key": lambda: "",
                   "dpapi_decrypt": lambda x: x,
                   "requests": __import__("requests")})

    def test_a_ia_local_existe_e_nao_pede_chave(self):
        ns = self._ns()
        self.assertIn("local", ns["PROVEDORES_IA"])
        self.assertTrue(ns["PROVEDORES_IA"]["local"]["sem_chave"])
        self.assertIn("localhost", ns["PROVEDORES_IA"]["local"]["url"])

    def test_ela_fala_a_porta_NATIVA_do_ollama(self):
        """Entrou pelo formato da OpenAI, que o Ollama imita — e foi isso que
        a deixou barata de adicionar. Só que a porta de compatibilidade não
        aceita `keep_alive` nem `num_predict`: o modelo era descarregado da
        memória depois de CADA resposta (3 a 5 GB relidos do disco na pergunta
        seguinte) e escrevia até 1200 tokens a ~8 por segundo.

        19/08: "esta muito lento para pensar". Era isto, e era meu. A porta
        nativa custa uma função a mais de manutenção e devolve os dois campos
        que mandam no relógio."""
        ns = self._ns()
        self.assertEqual(ns["PROVEDORES_IA"]["local"]["formato"], "ollama")
        self.assertIn("/api/chat", ns["PROVEDORES_IA"]["local"]["url"])

    def test_ela_e_a_ultima_da_fila(self):
        """Quando há um modelo grande de pé, ele responde melhor. A local é o
        CHÃO da escada — a que nunca falta —, não o teto."""
        ns = self._ns()
        self.assertEqual(ns["ORDEM_PROVEDORES"][-1], "local")

    def test_ollama_fora_do_ar_devolve_lista_vazia_sem_explodir(self):
        """Nesta máquina de teste não há Ollama. Tem de devolver [] e seguir —
        se levantasse, derrubaria o chat toda vez que a Gemini caísse."""
        ns = self._ns()
        self.assertEqual(ns["ia_local_no_ar"](timeout=0.2), [])

    def test_sem_ollama_ela_nao_entra_na_fila(self):
        """Entrar na fila sem estar de pé faria o chat esperar um timeout
        justamente no momento em que ele já está lento."""
        ns = self._ns()
        self.assertNotIn("local", ns["provedores_configurados"]())

    def test_os_modelos_tentados_sao_os_que_estao_baixados(self):
        """Tentar 'qwen2.5:7b' numa máquina que só tem 'llama3.1:8b' falharia
        quatro vezes antes de acertar por acaso."""
        # O filtro mudou de CASA, não de comportamento: saiu de dentro de
        # `responder_por_provedor_alternativo` para `modelos_do_provedor`,
        # que agora responde a pergunta "o que eu tento?" para a fila E para
        # o botão de testar. Eram duas respostas diferentes, e a do botão
        # estava errada — quatro 404 num Mac com o Ollama de pé.
        fonte = fonte_do_arquivo()
        i = fonte.index("def modelos_do_provedor")
        bloco = fonte[i:i + 1400]
        self.assertIn("instalados = ia_local_no_ar()", bloco)
        self.assertIn("or instalados[:2]", bloco)
        i2 = fonte.index("def responder_por_provedor_alternativo")
        self.assertIn("modelos_do_provedor(pid, info)", fonte[i2:i2 + 2200])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOModeloPequenoNaoPodeSequestrarABase(unittest.TestCase):
    """O teste real de 12/08, 21:18 — com a IA local instalada:

        ❯ O QUE É SMC?
        ✳ "SMC, no contexto do mercado financeiro in which we're discussing
           futures trading e altamente volátil como o forex (minúcias como
           E-mini), é a sigla para Smart Money Concepts..."

    Inglês no meio da frase, "minúcias" no lugar de "micro", e E-mini de ÍNDICE
    chamado de forex. A base própria responde essa pergunta com precisão, sem
    cota e sem internet — e não foi consultada.

    A causa foi arquitetural e minha: `responder_offline` só era tentado depois
    que TODOS os modelos falhavam. Enquanto o último da fila era a Gemini, isso
    funcionava. Com a IA local, o último da fila nunca falha — e a base deixou
    de existir na prática.
    """

    def test_a_base_responde_o_que_e_smc(self):
        """Se este teste falhar, a pergunta volta a cair no modelo pequeno."""
        ns = carregar(
            ["_sem_acento", "_norm_busca", "_parecido", "BASE_SMC", "BASE_MACRO",
             "_todos_os_topicos", "_nota_base_smc", "buscar_base_smc"],
            stubs={"unicodedata": __import__("unicodedata")})
        for pergunta in ("o que é smc?", "o que é vwap?", "o que é order block?",
                         "o que é choch?", "o que é liquidez?"):
            self.assertIsNotNone(ns["buscar_base_smc"](pergunta), pergunta)

    def test_o_prompt_do_provedor_diz_o_que_o_MES_e(self):
        """O modelo pequeno chamou o Micro E-mini de forex e inventou o valor
        por ponto. Isso não se conserta com guarda depois — se conserta
        dizendo, no prompt, o que o contrato é."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _mensagens_para_provedor")
        corpo = fonte[i:i + 4000]
        self.assertIn("NÃO é forex", corpo)
        self.assertIn("US$ 5 por ponto", corpo)
        self.assertIn("PORTUGUÊS DO BRASIL", corpo)

    def test_a_temperatura_dos_provedores_e_baixa(self):
        """Criatividade numa mesa é defeito: é o que faz um modelo pequeno
        completar um multiplicador que não sabe."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _pedir_openai")
        self.assertIn('"temperature": 0.2', fonte[i:i + 900])


class TestMentiraNaVozPassiva(unittest.TestCase):
    """12/08, 21:35 — o modelo local respondeu a 'DEIXE ISSO SALVO' com:

        "Claro, ficou salvo:
         PENÚLTIMA LEITURA DO MOTOR (21:30): BUY MESU6 @ 7769.25..."

    Nada foi salvo, e o conteúdo listado como salvo tinha acabado de ser
    inventado. A guarda anti-mentira olhava só a primeira pessoa ('gravei',
    'salvei') e a forma passiva passava inteira.
    """

    def _ns(self):
        return carregar(["_ALEGACOES_FALSAS", "_RE_ALEGACOES",
                         "_AVISO_ALEGACAO", "censurar_alegacao_falsa"])

    def test_a_frase_real_e_censurada(self):
        ns = self._ns()
        _t, censurou = ns["censurar_alegacao_falsa"](
            "Claro, ficou salvo:\n\nPENÚLTIMA LEITURA DO MOTOR (21:30): "
            "BUY MESU6 @ 7769.25, probabilidade 72.0%")
        self.assertTrue(censurou)

    def test_outras_formas_passivas_tambem(self):
        ns = self._ns()
        for t in ("Está gravado na minha memória.",
                  "Foi registrado com sucesso.",
                  "Pronto, já salvei na memória."):
            self.assertTrue(ns["censurar_alegacao_falsa"](t)[1], t)

    def test_ensinar_o_comando_nao_e_mentira(self):
        """Explicar COMO salvar é o comportamento correto — censurar isso
        deixaria a ferramenta sem como orientar."""
        ns = self._ns()
        for t in ("Para salvar isso, diga 'aprenda isso' no fim da frase.",
                  "Se quiser que fique gravado, termine com 'aprenda isso'."):
            self.assertFalse(ns["censurar_alegacao_falsa"](t)[1], t)

    def test_conversa_normal_passa(self):
        ns = self._ns()
        for t in ("A VWAP está em 7769.56.",
                  "O viés é comprador e a estrutura de alta segue intacta."):
            self.assertFalse(ns["censurar_alegacao_falsa"](t)[1], t)


class TestBuscaQueNaoViraDespejo(unittest.TestCase):
    """12/08, 21:38. Ele escreveu uma frase SOBRE ela:

        "VOCE CONSEGUE SIM, VOCE TEM CAPACIDADE PARA ISSO... É SÓ VOCE
         PESQUISAR E APRENDER"

    A palavra 'pesquisar' bastou para virar consulta. A busca não achou nada, e
    ela despejou o resultado da Lotofácil e o balanço da Copasa.
    """

    def test_frase_dirigida_a_ela_nao_vira_consulta(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _chat_web_pesquisa")
        bloco = fonte[i:i + 2600]
        self.assertIn("Isso soou como uma frase para mim", bloco)
        self.assertIn("len(consulta.split()) > 12", bloco)

    def test_manchete_sem_relacao_nao_entra(self):
        """Manchete que não casa com a pergunta não é resposta parcial: é
        ruído com cara de resposta."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _chat_web_pesquisa")
        bloco = fonte[i:i + 3200]
        self.assertIn("termos & set(", bloco)


class TestIALocalComVisao(unittest.TestCase):
    """13/08: TODOS os dez modelos da Gemini devolveram 503/429 no mesmo ciclo,
    duas passadas seguidas, e a análise morreu — com a IA local instalada, no
    ar, e INÚTIL. Ele perguntou, com razão: "por que não tenta a IA local?"

    A resposta era constrangedora: o modelo baixado (qwen2.5:3b) é de TEXTO
    puro. Ele não enxerga imagem nenhuma. A IA local nunca poderia ter lido um
    gráfico — e nada no app dizia isso."""

    def _ns(self):
        return carregar(["MODELO_VISAO_LOCAL", "MODELO_VISAO_LOCAL_LEVE",
                         "_RAM_NAO_INFORMADA", "_num_gb_de_ram",
                         "modelo_visao_recomendado"])

    def test_existe_um_modelo_de_visao(self):
        ns = self._ns()
        self.assertIn("vl", ns["MODELO_VISAO_LOCAL"].lower())
        self.assertIn("vl", ns["MODELO_VISAO_LOCAL_LEVE"].lower())

    def test_o_modelo_de_visao_tambem_respeita_a_memoria(self):
        """Modelo de visão é maior que o de texto. Máquina apertada leva o
        leve — um modelo que não cabe trava a máquina no pregão."""
        ns = self._ns()
        self.assertEqual(ns["modelo_visao_recomendado"](8),
                         ns["MODELO_VISAO_LOCAL_LEVE"])
        self.assertEqual(ns["modelo_visao_recomendado"](16),
                         ns["MODELO_VISAO_LOCAL"])

    def test_a_leitura_local_e_a_ULTIMA_reserva(self):
        """Ela entra depois que TODOS os modelos da Gemini falharam — não no
        lugar deles. Lê pior; entra porque nenhuma leitura é pior ainda."""
        fonte = fonte_do_arquivo()
        i = fonte.index("bruto, porque = analisar_grafico_local(")
        antes = fonte[i - 2500:i]
        self.assertIn("if resposta is None:", antes)

    def test_a_leitura_local_e_DECLARADA_como_reserva(self):
        """Não pode parecer leitura da Gemini. Quem lê o log precisa saber de
        onde veio o número."""
        fonte = fonte_do_arquivo()
        i = fonte.index("bruto, porque = analisar_grafico_local(")
        bloco = fonte[i:i + 1200]
        self.assertIn("IA LOCAL", bloco)
        self.assertIn("reserva", bloco)

    def test_resposta_fora_do_formato_e_descartada(self):
        """JSON quebrado do modelo pequeno não pode virar cenário."""
        fonte = fonte_do_arquivo()
        i = fonte.index("bruto, porque = analisar_grafico_local(")
        bloco = fonte[i:i + 1200]
        # NÃO é mais só `json.loads`: JSON válido com as chaves erradas
        # ("trend", "price") passava no loads e matava o ciclo logo depois,
        # lendo `current_price` que não existia. Ver test_visao_local.py.
        self.assertIn("analise_local_valida(bruto)", bloco)
        self.assertIn("descartado", bloco)

    def test_a_reserva_nunca_derruba_o_ciclo(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def analisar_grafico_local")
        bloco = fonte[i:i + 4200]
        self.assertIn("except Exception", bloco)
        # Devolve (texto, motivo): None sozinho não dizia POR QUE falhou, e
        # foi isso que deixou o log dele com "não devolveu resposta neste
        # ciclo" — uma frase sobre a qual não dá para fazer nada.
        self.assertIn("return None, f\"{type(e).__name__}", bloco)

    def test_sem_modelo_de_visao_baixado_ela_nao_finge(self):
        """Ter o Ollama no ar com um modelo de TEXTO não é ter visão. Foi
        exatamente essa confusão que produziu o defeito."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def analisar_grafico_local")
        bloco = fonte[i:i + 4200]
        self.assertIn("nenhum modelo de visão baixado", bloco)

    def test_a_instalacao_assistida_traz_o_modelo_de_visao(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _instalar_ia_worker")
        bloco = fonte[i:i + 8000]
        self.assertIn("modelo_visao_recomendado()", bloco)
        self.assertIn("modelo de VISÃO", bloco)

    def test_a_honestidade_sobre_a_qualidade_esta_escrita(self):
        """Um modelo local de 3 a 7 bilhões lê gráfico PIOR que a Gemini. Isso
        precisa estar no código, não só na minha cabeça."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def analisar_grafico_local")
        self.assertIn("lê gráfico PIOR", fonte[i:i + 2600])


class TestVozConfiguravel(unittest.TestCase):
    """Pedido dele: "configurar a velocidade da fala e uma biblioteca de opções
    de voz para não ser apenas essa chata"."""

    def _plat(self):
        import os
        from harness import RAIZ
        with open(os.path.join(RAIZ, "plataforma.py"), encoding="utf-8") as f:
            return f.read()

    def test_a_lista_de_vozes_vem_do_SISTEMA(self):
        """Presumir que 'Luciana' está instalada seria o mesmo chute que esta
        ferramenta inteira existe para evitar."""
        plat = self._plat()
        self.assertIn("def vozes_disponiveis", plat)
        self.assertIn('"say", "-v", "?"', plat)

    def test_da_para_OUVIR_antes_de_escolher(self):
        """Escolher voz por NOME, sem ouvir, é escolher no escuro — e
        descobrir no meio do pregão."""
        plat = self._plat()
        self.assertIn("def experimentar_voz", plat)
        fonte = fonte_do_arquivo()
        self.assertIn("🔈 ouvir", fonte)

    def test_voz_desinstalada_nao_deixa_a_ferramenta_muda(self):
        """Voz configurada que sumiu da máquina cai para a melhor e segue."""
        plat = self._plat()
        i = plat.index("def voz_escolhida_ou_melhor")
        self.assertIn("voz_portugues_macos()", plat[i:i + 800])

    def test_a_escolha_e_gravada_e_RELIDA(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def salvar_voz_escolhida")
        self.assertIn("return voz_escolhida()", fonte[i:i + 500])

    def test_existe_controle_de_velocidade_na_interface(self):
        fonte = fonte_do_arquivo()
        self.assertIn("Velocidade da fala:", fonte)
        self.assertIn("VOZ DA TIGER", fonte)
        self.assertIn("palavras/min", fonte)

    def test_a_velocidade_continua_limitada(self):
        """Fala rápida demais é ininteligível — e no meio do pregão isso é
        pior que não falar."""
        plat = self._plat()
        i = plat.index("def falar_nativo")
        self.assertIn("max(90, min(", plat[i:i + 600])


class TestMicrofoneDentroDoBundle(unittest.TestCase):
    """CINCO relatos do mesmo defeito. A causa, finalmente:

    O lançador do .app fazia `exec /Library/Frameworks/.../python3 main_app.py`.
    O processo que passa a existir é o PYTHON — um binário que mora FORA do
    .app. E o macOS não atribui permissão a "quem abriu": ele atribui ao
    binário que pede, e ao bundle que CONTÉM esse binário.

    Por isso o Info.plist declarava NSMicrophoneUsageDescription certinho e
    não servia para nada; por isso o estado ficava eternamente em "nunca
    pedido"; e por isso autorizar "SMC Quant Pro" e "Terminal" na lista não
    mudava nada — nenhum dos dois era o requerente."""

    def setUp(self):
        # No pacote do outro sistema este arquivo não existe — e não
        # existir ali é o certo. Falhar por isso assustaria o cliente
        # com um vermelho que não é defeito nenhum.
        pular_se_faltar("CRIAR_APP.command")

    def _criar_app(self):
        import os
        from harness import RAIZ
        with open(os.path.join(RAIZ, "CRIAR_APP.command"), encoding="utf-8") as f:
            return f.read()

    def test_o_python_e_copiado_para_dentro_do_bundle(self):
        s = self._criar_app()
        self.assertIn('cp "$PY" "$APP/Contents/MacOS/python-smc"', s)

    def test_o_lancador_executa_o_python_de_dentro(self):
        s = self._criar_app()
        self.assertIn("python-smc", s)
        self.assertNotIn('exec "${PY}" main_app.py', s)

    def test_a_causa_esta_escrita_no_codigo(self):
        """Cinco rodadas de correção às cegas custaram caro. O próximo que ler
        isto precisa saber POR QUE, senão 'simplifica' de volta."""
        s = self._criar_app()
        self.assertIn("FORA", s)
        self.assertIn("nunca pedido", s)

    def test_o_plist_continua_declarando_o_microfone(self):
        s = self._criar_app()
        self.assertIn("NSMicrophoneUsageDescription", s)
