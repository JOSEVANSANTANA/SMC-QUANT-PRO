import base64
import json
import os
import re
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

from harness import RAIZ, carregar, requests_ou_pular

import sys
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
import tiger_predictive  # noqa: E402


NOMES = ["erro_e_cota", "erro_e_modelo_inexistente", "segundos_ate_cota_voltar", "classificar_erro_modelo"]
COTA_DIA = ("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Quota exceeded ... "
            "GenerateRequestsPerDayPerProjectPerModel-FreeTier ... Please retry in 21h6m53.7s.', "
            "'details': [{'retryDelay': '76404s'}]}}")


class TestCota(unittest.TestCase):
    def test_cota_com_404_no_numero_nao_mata_o_modelo(self):
        ns = carregar(NOMES)
        self.assertFalse(ns["erro_e_modelo_inexistente"](COTA_DIA))
        self.assertEqual(ns["classificar_erro_modelo"](COTA_DIA), "cota")

    def test_404_de_verdade_continua_sendo_invalido(self):
        ns = carregar(NOMES)
        self.assertTrue(ns["erro_e_modelo_inexistente"]("404 NOT_FOUND. models/x is not found"))
        self.assertTrue(ns["erro_e_modelo_inexistente"]("models/x is no longer available"))

    def test_cota_diaria_espera_horas_e_cota_por_minuto_nao(self):
        ns = carregar(NOMES)
        self.assertGreater(ns["segundos_ate_cota_voltar"](COTA_DIA), 3600)
        self.assertEqual(ns["segundos_ate_cota_voltar"]("429 RESOURCE_EXHAUSTED per minute", 900), 900)


class TestTigerPredictiveImportEOte(unittest.TestCase):
    def test_calibrar_rejeita_ote_quando_nova_entrada_fica_acima_de_1_5R_do_preco(self):
        res = tiger_predictive.calibrar_setup_para_orcamento_e_execucao_real(
            direcao="SELL",
            entry=26274.0,
            stop=26374.0,
            tp1=26074.0,
            tp2=25950.0,
            preco_atual=26253.0,
            tick=0.25,
            valor_por_ponto=2.0,
            faixa_ticks=(16, 80),
            orcamento_max_usd=660.0,
            rr_minimo=1.5,
        )
        # novo_ep = 26374 - 20 = 26354; dist = |26354 - 26253| = 101 > 1.5 * 20 = 30 -> não ajusta
        self.assertFalse(res["ajustado"])
        self.assertEqual(res["entry"], 26274.0)


class TestExtrairJsonEOpenRouterVisao(unittest.TestCase):
    def test_extrair_json_analise_limpa_think_e_markdown(self):
        ns = carregar(["CHAVES_DA_ANALISE", "analise_local_valida", "extrair_json_analise"])
        payload = {
            "asset_symbol": "MNQZ6",
            "current_price": 26253.0,
            "market_analysis": "Estrutura de baixa em 5m",
            "confluence_factors": ["Order Block bearish"],
            "confidence_score": 80,
            "probabilidade": 78,
            "action": "SELL",
            "entry_price": 26265.0,
            "stop_loss": 26280.0,
            "take_profit_1": 26230.0,
            "take_profit_2": 26200.0,
            "ledger_update": "sem posição",
        }
        bruto = f"<think>analisando...</think>\n```json\n{json.dumps(payload)}\n```"
        extraido = ns["extrair_json_analise"](bruto)
        self.assertIsNotNone(extraido)
        self.assertEqual(json.loads(extraido)["asset_symbol"], "MNQZ6")

        incompleto = json.dumps({"asset_symbol": "MNQZ6"})
        self.assertIsNone(ns["extrair_json_analise"](incompleto))

    def test_modelos_visao_gratuitos_openrouter_filtra_pagos_e_audio(self):
        catalogo = {
            "data": [
                {
                    "id": "openai/gpt-4o",
                    "pricing": {"prompt": "0.000005", "completion": "0.000015"},
                    "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
                },
                {
                    "id": "google/lyria-3-pro-preview",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text", "audio"]},
                },
                {
                    "id": "meta-llama/llama-texto:free",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                },
                {
                    "id": "openrouter/free",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
                },
                {
                    "id": "nvidia/nemotron-3.5-super-vl:free",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "architecture": {"input_modalities": ["text", "image", "video"], "output_modalities": ["text"]},
                },
                {
                    "id": "google/gemma-4-31b-it:free",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "architecture": {"input_modalities": ["image", "text", "video"], "output_modalities": ["text"]},
                },
            ]
        }

        class Resp:
            status_code = 200
            def json(self):
                return catalogo

        class Req:
            @staticmethod
            def get(_url, timeout=None):
                return Resp()

        ns = carregar(
            ["_CACHE_MODELOS_VISAO_OPENROUTER", "_FALLBACK_VISAO_OPENROUTER",
             "VALIDADE_CATALOGO_SEG", "modelos_visao_gratuitos_openrouter"],
            stubs={"requests": Req},
        )
        ns["_CACHE_MODELOS_VISAO_OPENROUTER"]["lista"] = []
        ns["_CACHE_MODELOS_VISAO_OPENROUTER"]["quando"] = 0.0
        modelos = ns["modelos_visao_gratuitos_openrouter"]()
        self.assertEqual(
            modelos,
            ["google/gemma-4-31b-it:free", "nvidia/nemotron-3.5-super-vl:free", "openrouter/free"],
        )

    def test_analisar_grafico_openrouter_http_fallback_e_402(self):
        requests = requests_ou_pular()
        from PIL import Image

        reqs = []
        estado = {"modo": "fallback"}
        valido = json.dumps({
            "asset_symbol": "MNQZ6",
            "current_price": 26253.0,
            "market_analysis": "rejeição no topo",
            "confluence_factors": ["Order Block bearish"],
            "confidence_score": 82,
            "probabilidade": 78,
            "action": "SELL",
            "entry_price": 26265.0,
            "stop_loss": 26280.0,
            "take_profit_1": 26230.0,
            "take_profit_2": 26200.0,
            "ledger_update": "sem posição",
        })

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                corpo = json.loads(self.rfile.read(n) or b"{}")
                reqs.append(corpo)
                if estado["modo"] == "402":
                    body = json.dumps({"error": {"message": "Insufficient credits"}}).encode()
                    self.send_response(402)
                elif len(reqs) == 1:
                    body = json.dumps({"error": "rate limit"}).encode()
                    self.send_response(429)
                else:
                    body = json.dumps({"choices": [{"message": {"content": f"```json\n{valido}\n```"}}]}).encode()
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = HTTPServer(("127.0.0.1", 0), Handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
            ns = carregar(
                ["LADO_MAX_VISAO_NUVEM", "_b64_da_imagem", "CHAVES_DA_ANALISE",
                 "_CONTRATO_JSON_LOCAL", "prompt_para_visao_local",
                 "analise_local_valida", "extrair_json_analise",
                 "diagnostico_de_provedor", "analisar_grafico_openrouter"],
                stubs={
                    "requests": requests,
                    "base64": base64,
                    "BytesIO": BytesIO,
                    "Image": Image,
                    "carregar_chave_provedor": lambda _p: "sk-or-v1-test",
                    "modelos_visao_gratuitos_openrouter": lambda: ["m1:free", "m2:free"],
                },
            )
            img = Image.new("RGB", (64, 48), (15, 20, 30))
            txt, mod, mot = ns["analisar_grafico_openrouter"](
                img, "analise", modelos=["m1:free", "m2:free"], timeout=10, url=url
            )
            self.assertIsNotNone(txt, mot)
            self.assertEqual(mod, "m2:free")
            self.assertEqual(mot, "")
            self.assertEqual(len(reqs), 2)
            parts = reqs[1]["messages"][1]["content"]
            img_part = [p for p in parts if p.get("type") == "image_url"][0]
            self.assertTrue(img_part["image_url"]["url"].startswith("data:image/jpeg;base64,"))

            # HTTP 402 deve parar imediatamente no primeiro modelo
            reqs.clear()
            estado["modo"] = "402"
            txt2, mod2, mot2 = ns["analisar_grafico_openrouter"](
                img, "analise", modelos=["m1:free", "m2:free"], timeout=10, url=url
            )
            self.assertIsNone(txt2)
            self.assertIsNone(mod2)
            self.assertIn("SEM CRÉDITO", mot2.upper())
            self.assertEqual(len(reqs), 1)
        finally:
            srv.shutdown()
            srv.server_close()


class TestCensuraAcaoEPrintAtomico(unittest.TestCase):
    def test_narrativa_seta_posicao_zerada_nao_dispara_alarme_falso(self):
        ns = carregar(["censurar_acao_inventada", "_RE_ACAO_INVENTADA", "_RE_DESCRICAO_DE_ESTADO"])
        f = ns["censurar_acao_inventada"]
        narrativa = "3. BUY limit 27.030 → *não foi preenchido / expirou* → posição zerada."
        self.assertFalse(f(narrativa)[1], narrativa)

        # Ainda deve pegar confissão explícita mesmo se seguida de seta
        self.assertTrue(f("Encerrei sua posição → posição zerada.")[1])
        self.assertTrue(f("Pronto, a posição foi zerada.")[1])

    def test_salvar_ultimo_print_usa_escrita_atomica(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            destino = os.path.join(td, "ultimo_print.png")
            chamadas = []
            real_replace = os.replace

            def spy_replace(src, dst):
                chamadas.append((src, dst))
                return real_replace(src, dst)

            ns = carregar(
                ["salvar_ultimo_print"],
                stubs={
                    "pasta_dados_usuario": lambda: td,
                    "ULTIMO_PRINT_FILE": destino,
                    "os": type("OS", (), {"replace": staticmethod(spy_replace), "path": os.path, "remove": os.remove}),
                    "time": time,
                },
            )
            img = Image.new("RGB", (32, 24), (20, 30, 40))
            info = ns["salvar_ultimo_print"](img, janela="Tradovate")
            self.assertIsNotNone(info)
            self.assertEqual(info["caminho"], destino)
            self.assertEqual(chamadas, [(destino + ".tmp", destino)])
            self.assertTrue(os.path.exists(destino))
            self.assertFalse(os.path.exists(destino + ".tmp"))


if __name__ == "__main__":
    unittest.main()
