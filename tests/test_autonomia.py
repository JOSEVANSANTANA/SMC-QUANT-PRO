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

from harness import carregar, fonte_do_arquivo

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
             "provedores_configurados", "carregar_chave_provedor"],
            stubs={"carregar_config": lambda: {},
                   "carregar_api_key": lambda: "",
                   "dpapi_decrypt": lambda x: x,
                   "requests": __import__("requests")})

    def test_a_ia_local_existe_e_nao_pede_chave(self):
        ns = self._ns()
        self.assertIn("local", ns["PROVEDORES_IA"])
        self.assertTrue(ns["PROVEDORES_IA"]["local"]["sem_chave"])
        self.assertIn("localhost", ns["PROVEDORES_IA"]["local"]["url"])

    def test_ela_fala_o_protocolo_que_ja_existe(self):
        """O Ollama expõe o formato da OpenAI. Por isso a IA local entrou sem
        uma linha de código novo de rede — e é por isso que ela é barata de
        manter, não uma segunda implementação para dar manutenção."""
        ns = self._ns()
        self.assertEqual(ns["PROVEDORES_IA"]["local"]["formato"], "openai")

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
        fonte = fonte_do_arquivo()
        i = fonte.index("def responder_por_provedor_alternativo")
        bloco = fonte[i:i + 2200]
        self.assertIn("instalados = ia_local_no_ar()", bloco)
        self.assertIn("or instalados[:2]", bloco)


if __name__ == "__main__":
    unittest.main(verbosity=2)
