"""A IA LOCAL LENDO GRÁFICO — testada contra um Ollama de mentira, por HTTP.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
13/08. Ele escreveu: "Continua com o mesmo erro agora nas análises / Não está
analisando nem com gemini / Nem com local / Precisa corrigir isso".

E o log dele provava um defeito MEU:

    ✅ A IA local JÁ está no ar. Modelos: qwen2.5:3b. Nada a fazer.

O `_instalar_ia_worker` saía na primeira linha quando havia QUALQUER modelo
instalado — antes do passo que baixa o modelo de VISÃO que eu tinha acabado
de acrescentar. Resultado: o botão criado para instalar a visão nunca
conseguia instalá-la; o `qwen2.5:3b` é texto puro e não enxerga imagem
nenhuma; e quando os dez modelos da Gemini caíram, não havia reserva.

Os testes anteriores não pegaram isso porque olhavam o CÓDIGO. Este aqui
sobe um servidor HTTP de verdade em 127.0.0.1, na 11434, respondendo como o
Ollama responde, e faz o caminho inteiro passar por ele: `/api/tags` para
descobrir os modelos, `/api/generate` com a imagem em base64, o JSON de
volta. É o único jeito de provar que o caminho que falhou na mesa dele
funciona — sem baixar 5 GB de modelo.
"""

import base64
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

from harness import carregar, fonte_do_arquivo, requests_ou_pular

PORTA = 11434


class _ImagemFalsa:
    """Uma imagem que grava bytes reconhecíveis, sem depender do Pillow.

    O que este arquivo prova é o CAMINHO (base64, HTTP, JSON, escolha do
    modelo, validação). Amarrar isso à presença do Pillow faria o teste
    sumir calado justamente na máquina onde ele mais importa."""

    def __init__(self, marca=b"\xff\xd8\xffGRAFICO-DE-TESTE"):
        self.marca = marca

    def convert(self, _modo):
        return self

    def save(self, saida, **_kw):
        saida.write(self.marca)


def _imagem_de_teste():
    """Pillow de verdade quando existe; a falsa quando não existe."""
    try:
        from PIL import Image
        img = Image.new("RGB", (64, 48), (12, 18, 30))
        return img, True
    except Exception:
        return _ImagemFalsa(), False


class _Ollama(BaseHTTPRequestHandler):
    """O Ollama de mentira. Guarda o que recebeu, para o teste conferir."""

    modelos = ["qwen2.5vl:7b"]
    resposta = '{"asset_symbol": "MESU6"}'
    status_generate = 200
    recebido = {}

    def log_message(self, *_a):          # silêncio: o teste já fala bastante
        pass

    def _json(self, codigo, corpo):
        dados = json.dumps(corpo).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        if self.path.startswith("/api/tags"):
            self._json(200, {"models": [{"name": m} for m in _Ollama.modelos]})
        else:
            self._json(404, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(n) or b"{}")
        if self.path.startswith("/api/generate"):
            _Ollama.recebido = corpo
            if _Ollama.status_generate != 200:
                self._json(_Ollama.status_generate, {"error": "boom"})
                return
            self._json(200, {"response": _Ollama.resposta, "done": True})
        else:
            self._json(404, {})


class _ServidorCalado(HTTPServer):
    """O cliente fecha a conexão assim que lê a resposta e o handler estoura
    um BrokenPipe no stderr. É esperado e não é defeito — mas polui a saída
    da suíte, e log poluído é log que ninguém lê."""

    def handle_error(self, *_a):
        pass


class BaseComOllamaFalso(unittest.TestCase):
    """Sobe o servidor uma vez para a classe inteira."""

    @classmethod
    def setUpClass(cls):
        cls.servidor = _ServidorCalado(("127.0.0.1", PORTA), _Ollama)
        cls.thread = threading.Thread(target=cls.servidor.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        _Ollama.modelos = ["qwen2.5vl:7b"]
        _Ollama.resposta = json.dumps({
            "asset_symbol": "MESU6", "current_price": 7784.0,
            "market_analysis": "estrutura de alta", "confluence_factors": ["FVG"],
            "confidence_score": 70, "probabilidade": 60, "action": "BUY",
            "entry_price": 7784.0, "stop_loss": 7770.0,
            "take_profit_1": 7800.0, "take_profit_2": 7810.0,
            "ledger_update": "sem posição"})
        _Ollama.status_generate = 200
        _Ollama.recebido = {}

    def _ns(self):
        # Este arquivo TROCA `requests.post` por um servidor de mentira e
        # confere o que foi enviado — ou seja, exercita o caminho HTTP de
        # verdade. Sem a biblioteca, ele PULA dizendo por quê, em vez de
        # falhar como se o programa estivesse quebrado.
        requests = requests_ou_pular()
        return carregar(
            ["_RAM_NAO_INFORMADA", "MODELO_VISAO_LOCAL", "MODELO_VISAO_LOCAL_LEVE",
             "modelo_visao_recomendado", "LADO_MAX_VISAO_LOCAL",
             "_b64_da_imagem", "_MARCAS_DE_VISAO",
             "tem_modelo_de_visao", "modelo_de_visao_instalado",
             "CHAVES_DA_ANALISE", "_CONTRATO_JSON_LOCAL",
             "prompt_para_visao_local", "analise_local_valida",
             "analisar_grafico_local", "_num_gb_de_ram", "ia_local_no_ar",
             "_keep_alive_do_ciclo"],
            stubs={"requests": requests, "base64": base64, "BytesIO": BytesIO,
                   "Image": _Image(), "carregar_config": lambda: {}})


def _Image():
    """O Pillow de verdade quando existe; senão um objeto que só precisa ter
    o atributo LANCZOS (a redução vive dentro de um try)."""
    try:
        from PIL import Image
        return Image
    except Exception:
        return type("Image", (), {"LANCZOS": 1})


class TestOCaminhoInteiroPorHTTP(BaseComOllamaFalso):
    """O caminho que falhou na mesa dele, do começo ao fim."""

    def test_le_o_grafico_e_devolve_o_json(self):
        ns = self._ns()
        img, _real = _imagem_de_teste()
        bruto, porque = ns["analisar_grafico_local"](img, "leia este gráfico",
                                                     timeout=10)
        self.assertIsNotNone(bruto, f"a IA local não devolveu nada: {porque}")
        self.assertEqual(json.loads(bruto)["asset_symbol"], "MESU6")
        self.assertEqual(porque, "", "deu certo e ainda assim veio motivo")

    def test_a_imagem_chega_do_outro_lado_em_base64(self):
        """Se o base64 estivesse errado, o modelo receberia lixo e responderia
        sobre um gráfico que nunca viu — que é pior que não responder."""
        ns = self._ns()
        img, real = _imagem_de_teste()
        ns["analisar_grafico_local"](img, "leia", timeout=10)
        imagens = _Ollama.recebido.get("images") or []
        self.assertEqual(len(imagens), 1)
        bytes_recebidos = base64.b64decode(imagens[0])
        self.assertTrue(bytes_recebidos.startswith(b"\xff\xd8\xff"),
                        "não chegou um JPEG do outro lado")
        if real:
            from PIL import Image
            aberta = Image.open(BytesIO(bytes_recebidos))
            self.assertEqual(aberta.size, (64, 48))

    def test_manda_o_contrato_de_chaves_junto(self):
        """O Ollama não tem `response_schema`: `format=json` garante que sai
        JSON e mais nada. Sem as chaves por extenso o modelo inventa as dele,
        o json.loads passa, e o ciclo morre lendo current_price inexistente."""
        ns = self._ns()
        img, _ = _imagem_de_teste()
        ns["analisar_grafico_local"](img, "leia este gráfico", timeout=10)
        enviado = _Ollama.recebido.get("prompt") or ""
        self.assertIn("leia este gráfico", enviado)
        for chave in ns["CHAVES_DA_ANALISE"]:
            self.assertIn(chave, enviado, chave)
        self.assertEqual(_Ollama.recebido.get("format"), "json")

    def test_escolhe_o_modelo_de_visao_que_ESTA_instalado(self):
        """Pedir o qwen2.5vl:7b numa máquina que baixou o :3b devolveria erro
        de modelo inexistente — e o trader ficaria sem análise por causa de
        uma etiqueta."""
        _Ollama.modelos = ["qwen2.5:3b", "qwen2.5vl:3b"]
        ns = self._ns()
        img, _ = _imagem_de_teste()
        ns["analisar_grafico_local"](img, "leia", modelo="qwen2.5vl:7b",
                                     timeout=10)
        self.assertEqual(_Ollama.recebido.get("model"), "qwen2.5vl:3b")

    def test_temperatura_baixa_para_ler_numero(self):
        """Criatividade em leitura de preço é invenção."""
        ns = self._ns()
        img, _ = _imagem_de_teste()
        ns["analisar_grafico_local"](img, "leia", timeout=10)
        self.assertLessEqual(
            (_Ollama.recebido.get("options") or {}).get("temperature", 1), 0.2)


class TestQuandoDaErrado(BaseComOllamaFalso):
    """A reserva não pode derrubar o ciclo que ela existe para salvar."""

    def test_so_modelo_de_texto_instalado_devolve_None(self):
        """Este é EXATAMENTE o estado da máquina dele: qwen2.5:3b e nada mais.
        Nesse estado a função tem que dizer 'não sei ler', não tentar."""
        _Ollama.modelos = ["qwen2.5:3b"]
        ns = self._ns()
        img, _ = _imagem_de_teste()
        texto, porque = ns["analisar_grafico_local"](img, "leia", timeout=10)
        self.assertIsNone(texto)
        self.assertIn("texto puro", porque)
        self.assertEqual(_Ollama.recebido, {},
                         "não pode nem ter chamado o /api/generate")

    def test_erro_HTTP_devolve_None_COM_o_motivo(self):
        _Ollama.status_generate = 500
        ns = self._ns()
        img, _ = _imagem_de_teste()
        texto, porque = ns["analisar_grafico_local"](img, "leia", timeout=10)
        self.assertIsNone(texto)
        self.assertIn("500", porque)

    def test_resposta_vazia_devolve_None_COM_o_motivo(self):
        _Ollama.resposta = "   "
        ns = self._ns()
        img, _ = _imagem_de_teste()
        texto, porque = ns["analisar_grafico_local"](img, "leia", timeout=10)
        self.assertIsNone(texto)
        self.assertIn("vazio", porque)

    def test_servidor_fora_do_ar_devolve_None(self):
        """Sem Ollama nenhum, a função sai calada — não levanta no meio do
        ciclo do motor."""
        self.servidor.shutdown()
        try:
            ns = self._ns()
            img, _ = _imagem_de_teste()
            texto, porque = ns["analisar_grafico_local"](img, "leia", timeout=3)
            self.assertIsNone(texto)
            self.assertIn("fora do ar", porque)
        finally:
            self.__class__.thread = threading.Thread(
                target=self.servidor.serve_forever, daemon=True)
            self.thread.start()


class TestJSONValidoNaoEAnaliseValida(unittest.TestCase):
    """`{"trend": "alta"}` passa no json.loads e não serve para nada."""

    def _ns(self):
        return carregar(["CHAVES_DA_ANALISE", "analise_local_valida"])

    def test_json_com_as_chaves_certas_passa(self):
        ns = self._ns()
        bom = json.dumps({k: 1 for k in ns["CHAVES_DA_ANALISE"]})
        self.assertIsNotNone(ns["analise_local_valida"](bom))

    def test_json_valido_com_chaves_inventadas_e_recusado(self):
        ns = self._ns()
        self.assertIsNone(ns["analise_local_valida"](
            '{"trend": "alta", "price": 7784}'))

    def test_falta_UMA_chave_obrigatoria_ja_recusa(self):
        """Faltar `current_price` significa que o preço vira None e o cenário
        inteiro sai em cima de nada."""
        ns = self._ns()
        d = {k: 1 for k in ns["CHAVES_DA_ANALISE"]}
        d.pop("current_price")
        self.assertIsNone(ns["analise_local_valida"](json.dumps(d)))

    def test_texto_solto_e_recusado(self):
        ns = self._ns()
        self.assertIsNone(ns["analise_local_valida"]("Claro! Aqui está:"))
        self.assertIsNone(ns["analise_local_valida"](None))

    def test_lista_no_lugar_de_objeto_e_recusada(self):
        ns = self._ns()
        self.assertIsNone(ns["analise_local_valida"]("[1, 2, 3]"))


class TestReconhecerQuemEnxerga(unittest.TestCase):
    """A confusão entre 'tem modelo' e 'tem modelo que ENXERGA' foi a causa
    raiz do defeito. Ela agora tem nome e teste."""

    def _ns(self):
        return carregar(["_MARCAS_DE_VISAO", "tem_modelo_de_visao",
                         "modelo_de_visao_instalado"])

    def test_o_modelo_da_maquina_dele_NAO_enxerga(self):
        ns = self._ns()
        self.assertFalse(ns["tem_modelo_de_visao"](["qwen2.5:3b"]))
        self.assertIsNone(ns["modelo_de_visao_instalado"](["qwen2.5:3b"]))

    def test_reconhece_os_modelos_de_visao_conhecidos(self):
        ns = self._ns()
        for nome in ("qwen2.5vl:7b", "llava:13b", "moondream", "llama3.2-vision",
                     "minicpm-v", "gemma3:4b", "bakllava"):
            self.assertTrue(ns["tem_modelo_de_visao"]([nome]), nome)

    def test_devolve_o_nome_de_quem_enxerga_no_meio_dos_outros(self):
        ns = self._ns()
        self.assertEqual(
            ns["modelo_de_visao_instalado"](["qwen2.5:7b", "qwen2.5vl:3b",
                                             "nomic-embed-text"]),
            "qwen2.5vl:3b")

    def test_lista_vazia_ou_None_nao_levanta(self):
        ns = self._ns()
        for entrada in ([], None, [""], [None]):
            self.assertFalse(ns["tem_modelo_de_visao"](entrada), repr(entrada))


class TestOModeloDeVisaoQueCabe(unittest.TestCase):

    def _ns(self):
        return carregar(["_RAM_NAO_INFORMADA", "MODELO_VISAO_LOCAL",
                         "MODELO_VISAO_LOCAL_LEVE", "_num_gb_de_ram",
                         "modelo_visao_recomendado"])

    def test_maquina_apertada_recebe_o_leve(self):
        ns = self._ns()
        self.assertEqual(ns["modelo_visao_recomendado"](8),
                         ns["MODELO_VISAO_LOCAL_LEVE"])

    def test_maquina_folgada_recebe_o_padrao(self):
        ns = self._ns()
        self.assertEqual(ns["modelo_visao_recomendado"](16),
                         ns["MODELO_VISAO_LOCAL"])

    def test_o_de_visao_pede_MAIS_memoria_que_o_de_texto(self):
        """Modelo de visão carrega o codificador de imagem junto: o limite não
        pode ser o mesmo do texto (9 GB), senão trava a máquina no pregão."""
        ns = self._ns()
        self.assertEqual(ns["modelo_visao_recomendado"](11),
                         ns["MODELO_VISAO_LOCAL_LEVE"])
        self.assertEqual(ns["modelo_visao_recomendado"](12),
                         ns["MODELO_VISAO_LOCAL"])

    def test_sem_medir_a_memoria_nao_levanta(self):
        ns = self._ns()
        self.assertIn(ns["modelo_visao_recomendado"](None),
                      (ns["MODELO_VISAO_LOCAL"], ns["MODELO_VISAO_LOCAL_LEVE"]))


class TestAInstalacaoNaoSaiAntesDaVisao(unittest.TestCase):
    """O defeito, no lugar exato onde ele estava."""

    def _bloco(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _instalar_ia_worker")
        return fonte[i:i + 9000]

    def test_pronto_significa_TEXTO_E_VISAO(self):
        """A saída antecipada agora exige as duas coisas. Era ela que fazia o
        log dele dizer 'Nada a fazer' com um modelo cego instalado."""
        bloco = self._bloco()
        # Âncora na LINHA DE LOG, não no comentário que a descreve.
        cabeca = bloco[:bloco.index("JÁ está completa")]
        self.assertIn("tem_modelo_de_visao(instalados)", cabeca)

    def test_com_so_texto_instalado_ele_AVISA_e_segue(self):
        bloco = self._bloco()
        self.assertIn("mas SEM modelo de visão", bloco)

    def test_o_passo_da_visao_vem_DEPOIS_da_saida_antecipada(self):
        """Se o passo 3b morasse antes, nada disso importaria; se a saída
        antecipada não olhasse a visão, o 3b seria inalcançável — que foi o
        que aconteceu."""
        bloco = self._bloco()
        self.assertLess(bloco.index("JÁ está completa"),
                        bloco.index("PASSO 3b"))
        self.assertIn("baixar_modelo_ia_local(exe, visao", bloco)

    def test_falhar_a_visao_nao_aborta_a_instalacao(self):
        """Sem visão ela ainda conversa por texto. Abortar tudo tiraria também
        o que já tinha funcionado."""
        bloco = self._bloco()
        i = bloco.index("Não consegui trazer o modelo de visão")
        self.assertNotIn("return", bloco[i:i + 400])


class TestOMotorExplicaPorQueNaoTeveAnalise(unittest.TestCase):
    """'Não está analisando nem com gemini / Nem com local' — ele só descobriu
    o motivo porque me mandou o log. O motor tem que dizer sozinho."""

    def _bloco(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("if resposta is None:\n                            instalados_local")
        return fonte[i:i + 2600]

    def test_diz_quando_a_ia_local_nem_esta_no_ar(self):
        self.assertIn("não está no ar", self._bloco())

    def test_diz_quando_os_modelos_instalados_sao_CEGOS(self):
        bloco = self._bloco()
        self.assertIn("NENHUM desses modelos enxerga imagem", bloco)
        self.assertIn("Instalar a IA LOCAL", bloco)

    def test_a_leitura_local_passa_pela_validacao_de_chaves(self):
        self.assertIn("analise_local_valida(bruto)", self._bloco())

    def test_a_leitura_local_e_DECLARADA_como_reserva(self):
        """Leitura de reserva apresentada como leitura da Gemini seria mentira
        sobre a origem do número que ele vai operar."""
        bloco = self._bloco()
        self.assertIn("IA LOCAL", bloco)
        self.assertIn("reserva", bloco)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestACOLADEMODELOS(unittest.TestCase):
    """O DEFEITO QUE MATOU AS ANÁLISES DO DIA 13, E O RELATÓRIO DO WHATSAPP.

    Log das 14:45: onze modelos na lista, e o motor escreveu "Todos os
    modelos disponíveis falharam. Último erro: 404 ... gemini-2.5-flash-lite"
    — que era o SEGUNDO da fila. Os outros nove nem apareceram no registro.

    Motivo: o cooldown era um FILTRO. Nove modelos tinham entrado em cooldown
    de cota dois minutos antes, postos lá pela conversa do chat. Sobraram
    exatamente os dois que estavam mortos com 404. O motor tentou esses dois,
    desistiu, e a frase "todos falharam" estava certa sobre os dois e calada
    sobre os nove.
    """

    def _ns(self):
        return carregar(["fila_por_cooldown"])

    def test_ninguem_fica_de_fora(self):
        ns = self._ns()
        modelos = [f"m{i}" for i in range(11)]
        # os 9 últimos estacionados; livres são só os dois primeiros
        cool = {m: 9_999 for m in modelos[2:]}
        fila, parados = ns["fila_por_cooldown"](modelos, cool, agora=0)
        self.assertEqual(sorted(fila), sorted(modelos),
                         "algum modelo foi cortado da fila")
        self.assertEqual(parados, 9)

    def test_o_estacionado_vai_para_o_FIM_e_nao_para_fora(self):
        ns = self._ns()
        fila, _ = ns["fila_por_cooldown"](["a", "b", "c"], {"a": 100}, agora=0)
        self.assertEqual(fila, ["b", "c", "a"])

    def test_o_cenario_exato_do_log_das_14h45(self):
        """Dois livres e mortos, nove estacionados e vivos. Antes o motor via
        dois candidatos; agora vê onze, com os nove no fim."""
        ns = self._ns()
        mortos = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
        vivos = ["gemini-3-flash-preview", "gemini-flash-latest",
                 "gemini-flash-lite-latest", "gemini-3.5-flash",
                 "gemini-3.1-flash-lite-preview", "gemini-3.1-flash-lite",
                 "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.7-flash"]
        cool = {m: 9_999 for m in vivos}
        fila, parados = ns["fila_por_cooldown"](mortos + vivos, cool, agora=0)
        self.assertEqual(len(fila), 11)
        self.assertEqual(parados, 9)
        self.assertEqual(fila[:2], mortos)
        for m in vivos:
            self.assertIn(m, fila, f"{m} continuaria fora da fila")

    def test_cooldown_vencido_conta_como_livre(self):
        ns = self._ns()
        fila, parados = ns["fila_por_cooldown"](["a", "b"], {"a": 50}, agora=100)
        self.assertEqual(parados, 0)
        self.assertEqual(fila, ["a", "b"])

    def test_o_preferido_lidera_mesmo_estacionado(self):
        """Quem respondeu por último é o mais provável de responder agora."""
        ns = self._ns()
        fila, _ = ns["fila_por_cooldown"](["a", "b", "c"], {"c": 100}, agora=0,
                                          preferido="c")
        self.assertEqual(fila[0], "c")

    def test_sem_cooldown_nenhum_a_ordem_e_preservada(self):
        ns = self._ns()
        fila, parados = ns["fila_por_cooldown"](["a", "b", "c"], {}, agora=0)
        self.assertEqual(fila, ["a", "b", "c"])
        self.assertEqual(parados, 0)

    def test_o_motor_usa_a_MESMA_funcao_do_chat(self):
        """Duas cópias da mesma regra foi o que deixou uma delas errada por
        semanas: o chat ordenava, o motor cortava."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _analisar_ciclo") if "def _analisar_ciclo" in fonte else 0
        self.assertIn("candidatos, n_parados = fila_por_cooldown(", fonte)
        self.assertIn("return fila_por_cooldown(base, cooldown, agora, preferido)[0]",
                      fonte)

    def test_a_mensagem_de_falha_diz_QUANTOS_foram_tentados(self):
        """'Todos os modelos falharam' sobre 2 de 11 foi o que escondeu este
        defeito por um dia inteiro."""
        fonte = fonte_do_arquivo()
        self.assertIn("Falharam os {len(candidatos)} modelo(s) tentados", fonte)


class TestAImagemQueVaiParaAIALocal(unittest.TestCase):
    """'o computador inteiro ficou lento' — 13/08.

    Um modelo de visão pica a imagem em quadradinhos antes de pensar. A tela
    cheia de um MacBook vira milhares de pedaços, e é isso que come a máquina
    e estoura o prazo. A Gemini roda no servidor do Google e não liga; a IA
    local roda na mesa dele."""

    def _ns(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest("Pillow não instalado nesta máquina de teste")
        return carregar(["LADO_MAX_VISAO_LOCAL", "_b64_da_imagem"],
                        stubs={"base64": base64, "BytesIO": BytesIO,
                               "Image": Image})

    def test_tela_cheia_de_macbook_e_reduzida(self):
        ns = self._ns()
        from PIL import Image
        grande = Image.new("RGB", (3024, 1964), (10, 10, 10))
        bruto = base64.b64decode(ns["_b64_da_imagem"](grande))
        saiu = Image.open(BytesIO(bruto))
        self.assertEqual(max(saiu.size), ns["LADO_MAX_VISAO_LOCAL"])
        self.assertAlmostEqual(saiu.size[0] / saiu.size[1], 3024 / 1964,
                               places=2, msg="a proporção foi distorcida")

    def test_imagem_pequena_NAO_e_esticada(self):
        """Aumentar não cria pixel nenhum: só inventa borrão em cima do preço."""
        ns = self._ns()
        from PIL import Image
        pequena = Image.new("RGB", (800, 600), (10, 10, 10))
        saiu = Image.open(BytesIO(base64.b64decode(ns["_b64_da_imagem"](pequena))))
        self.assertEqual(saiu.size, (800, 600))

    def test_o_limite_ainda_deixa_o_preco_legivel(self):
        """Abaixo de ~1000px os números de 12px do gráfico viram borrão, e a
        reserva passaria a inventar em vez de ler."""
        ns = self._ns()
        self.assertGreaterEqual(ns["LADO_MAX_VISAO_LOCAL"], 1200)
