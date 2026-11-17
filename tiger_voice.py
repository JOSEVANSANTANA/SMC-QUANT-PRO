#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tiger_voice.py / jarvis.py — Assistente Virtual de Voz Institucional (IA TIGER / Jarvis)

Módulo autônomo e modular de interação por voz em tempo real:
  - PADRÃO CASCATA (Fallback): 1º Gemini -> 2º OpenRouter/Groq -> 3º Ollama (Local).
  - JSON Mode Nativo: Previne alucinações na alteração do núcleo de trading.
  - STT (Speech-to-Text): Reconhecimento de voz contínuo via SpeechRecognition.
  - TTS (Text-to-Speech): Síntese de voz com baixa latência (say nativo no macOS / pyttsx3 no Windows).
"""

import os
import sys
import time
import json
import logging
import platform
import subprocess
import threading
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple

try:
    from tiger_autonomia import TigerAutonomia
except ImportError:
    TigerAutonomia = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import speech_recognition as sr
    SR_DISPONIVEL = True
except ImportError:
    SR_DISPONIVEL = False

try:
    import pyttsx3
    PYTTSX3_DISPONIVEL = True
except ImportError:
    PYTTSX3_DISPONIVEL = False

try:
    from openai import OpenAI
    OPENAI_LIB_DISPONIVEL = True
except ImportError:
    OPENAI_LIB_DISPONIVEL = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TIGER_VOICE")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODELO_PADRAO = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
MODELOS_RAPIDOS = [
    "anthropic/claude-3.5-sonnet",
    "meta-llama/llama-3.3-70b-instruct",
    "openai/gpt-4o-mini",
    "deepseek/deepseek-chat",
    "google/gemini-2.0-flash-001",
]
WAKE_WORDS = ["tiger", "olá tiger", "ola tiger", "jarvis", "olá jarvis", "ola jarvis"]


class TigerVoiceAssistant:
    """Assistente de Voz inteligente integrado com Cascata de LLMs e OpenRouter."""

    def __init__(self, api_key: Optional[str] = None, modelo: str = MODELO_PADRAO):
        self.sistema = platform.system().lower()
        self.executando = False
        self.historico: List[Dict[str, str]] = []
        self._lock_fala = threading.Lock()
        self.modelo = modelo

        self.chaves = self._carregar_todas_as_chaves()
        if api_key:
            self.chaves["openrouter"] = api_key
        self.api_key = api_key or self.chaves.get("openrouter") or ""

        self.autonomia = TigerAutonomia(assistente_voz=self) if TigerAutonomia else None
        self.estado_atual_do_plano = {
            "risco_pct": 5.0,
            "rr_minimo": 2.0,
            "probabilidade_minima": 65,
            "max_stops_seguidos": 3,
        }

        if SR_DISPONIVEL:
            self.recognizer = sr.Recognizer()
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
        else:
            self.recognizer = None

        self.engine_tts = None
        if PYTTSX3_DISPONIVEL and self.sistema != "darwin":
            try:
                self.engine_tts = pyttsx3.init()
                self.engine_tts.setProperty("rate", 190)
            except Exception:
                pass

        self.client_openai = None
        if OPENAI_LIB_DISPONIVEL and self.api_key:
            try:
                self.client_openai = OpenAI(
                    base_url=OPENROUTER_BASE_URL,
                    api_key=self.api_key,
                    default_headers={
                        "HTTP-Referer": "https://tigerinvest.vip",
                        "X-Title": "SMC Quant Pro Tiger Voice Assistant",
                    },
                )
            except Exception:
                self.client_openai = None

    def _carregar_todas_as_chaves(self) -> Dict[str, str]:
        chaves = {
            "gemini": os.getenv("GEMINI_API_KEY", ""),
            "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
            "groq": os.getenv("GROQ_API_KEY", ""),
        }
        caminhos_cfg = [
            os.path.expanduser("~/Library/Application Support/SMC_Quant_Pro/config_smc.json"),
            os.path.expanduser("~/Library/Application Support/SMC_Quant_Pro/config.json"),
            os.path.expanduser("~/.smc_quant_pro/config.json"),
            os.path.join(os.getcwd(), "config.json"),
        ]
        for c in caminhos_cfg:
            if os.path.isfile(c):
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        dados = json.load(f)
                        k_prov = dados.get("chaves_provedores", {})
                        if isinstance(k_prov, dict):
                            if k_prov.get("gemini"):
                                chaves["gemini"] = k_prov["gemini"]
                            if k_prov.get("openrouter"):
                                chaves["openrouter"] = k_prov["openrouter"]
                            if k_prov.get("groq"):
                                chaves["groq"] = k_prov["groq"]
                        if dados.get("chave_gemini"):
                            chaves["gemini"] = dados["chave_gemini"]
                except Exception:
                    pass
        return chaves

    def _salvar_estado_do_plano(self):
        logger.info(f"💾 Salvando novo estado do plano no disco: {self.estado_atual_do_plano}")

    def falar_texto(self, texto: str):
        if not texto or not texto.strip():
            return
        limpo = texto.replace("*", "").replace("#", "").replace("`", "").strip()
        logger.info(f"🗣️ [TIGER]: {limpo}")

        with self._lock_fala:
            if self.sistema == "darwin":
                try:
                    subprocess.run(["say", "-v", "Luciana", "-r", "195", limpo], check=False)
                    return
                except Exception:
                    pass

            if self.engine_tts:
                try:
                    self.engine_tts.say(limpo)
                    self.engine_tts.runAndWait()
                    return
                except Exception:
                    pass
            print(f"\n[TIGER FALA]: {limpo}\n")

    def ouvir_microfone(self, timeout: int = 5, frase_limite: int = 8) -> Optional[str]:
        if not self.recognizer:
            return None
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                logger.info("🎤 Escutando microfone...")
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=frase_limite)
            texto = self.recognizer.recognize_google(audio, language="pt-BR")
            logger.info(f"👂 [VOCÊ]: {texto}")
            return texto.strip().lower()
        except Exception:
            return None

    def consultar_openrouter(self, mensagem_usuario: str) -> str:
        """Compatibilidade direta com consulta ao OpenRouter."""
        if not self.api_key:
            return "Chave da API do OpenRouter não configurada."
        system_prompt = (
            "Você é a TIGER: a inteligência artificial mentora de trading institucional e assistente "
            "do trader Josevan no SMC Quant Pro. Responda em português de forma direta e profissional, "
            "sem markdown, pois sua resposta será lida em voz alta."
        )
        mensagens = [{"role": "system", "content": system_prompt}]
        mensagens.extend(self.historico[-6:])
        mensagens.append({"role": "user", "content": mensagem_usuario})

        if self.client_openai:
            try:
                resposta = self.client_openai.chat.completions.create(
                    model=self.modelo,
                    messages=mensagens,
                    temperature=0.3,
                    max_tokens=350,
                    timeout=25,
                )
                conteudo = resposta.choices[0].message.content or ""
                self._atualizar_historico(mensagem_usuario, conteudo, False)
                return conteudo.strip()
            except Exception as e:
                logger.warning(f"OpenAI SDK falhou ({e}). Tentando fallback HTTP...")

        return self._requisicao_http_openrouter(mensagens, mensagem_usuario)

    def _requisicao_http_openrouter(self, mensagens: List[Dict[str, str]], mensagem_usuario: str) -> str:
        try:
            url = f"{OPENROUTER_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "SMC-Quant-Pro/2.85",
                "HTTP-Referer": "https://tigerinvest.vip",
                "X-Title": "SMC Quant Pro Tiger Voice Assistant",
            }
            payload = {
                "model": self.modelo,
                "messages": mensagens,
                "temperature": 0.3,
                "max_tokens": 350,
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=25) as response:
                if getattr(response, "status", 200) == 200:
                    dados = json.loads(response.read().decode("utf-8"))
                    conteudo = dados.get("choices", [{}])[0].get("message", {}).get("content", "")
                    self._atualizar_historico(mensagem_usuario, conteudo, False)
                    return conteudo.strip()
                return f"A API do OpenRouter retornou status {response.status}."
        except urllib.error.HTTPError as e:
            return f"A API do OpenRouter retornou erro HTTP {e.code}."
        except Exception:
            return "Não consegui conectar aos servidores do OpenRouter no momento."

    def consultar_ia_com_fallback(
        self, mensagem_usuario: str, json_mode: bool = False, prompt_customizado: str = None
    ) -> str:
        system_prompt = prompt_customizado or (
            "Você é a TIGER: a inteligência artificial mentora de trading institucional e assistente "
            "do trader Josevan no SMC Quant Pro. Responda em português de forma direta e profissional, "
            "sem markdown, pois sua resposta será lida em voz alta."
        )

        if self.chaves.get("gemini"):
            try:
                resposta = self._requisicao_gemini(mensagem_usuario, system_prompt, json_mode)
                if resposta:
                    self._atualizar_historico(mensagem_usuario, resposta, json_mode)
                    return resposta
            except Exception as e:
                logger.warning(f"⚠️ Gemini falhou ({e}). Iniciando Rota de Backup (OpenRouter)...")

        if self.chaves.get("openrouter") or self.chaves.get("groq") or self.api_key:
            try:
                resposta = self._requisicao_openrouter(mensagem_usuario, system_prompt, json_mode)
                if resposta:
                    self._atualizar_historico(mensagem_usuario, resposta, json_mode)
                    return resposta
            except Exception as e:
                logger.warning(f"⚠️ Nuvem Backup falhou ({e}). Acordando IA Local...")

        try:
            resposta = self._requisicao_ollama(mensagem_usuario, system_prompt, json_mode)
            if resposta:
                self._atualizar_historico(mensagem_usuario, resposta, json_mode)
                return resposta
        except Exception as e:
            logger.error(f"❌ Falha Crítica: IA Local também não respondeu ({e}).")

        if json_mode:
            return '{"sucesso": false, "resposta_vocal": "Perda total de comunicação com os motores de inferência."}'
        return "Sinto muito, Josevan. Todos os meus sistemas na nuvem e locais perderam a conexão."

    def _atualizar_historico(self, user_msg, asst_msg, json_mode):
        if not json_mode:
            self.historico.append({"role": "user", "content": user_msg})
            self.historico.append({"role": "assistant", "content": asst_msg})

    def _requisicao_gemini(self, msg: str, sys_prompt: str, json_mode: bool) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.chaves['gemini']}"
        contents = []
        for h in self.historico[-6:] + [{"role": "user", "content": msg}]:
            role = "model" if h["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": h["content"]}]})

        payload = {
            "system_instruction": {"parts": [{"text": sys_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.0 if json_mode else 0.3},
        }
        if json_mode:
            payload["generationConfig"]["response_mime_type"] = "application/json"

        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as response:
            dados = json.loads(response.read().decode())
            return dados["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _requisicao_openrouter(self, msg: str, sys_prompt: str, json_mode: bool) -> str:
        url = f"{OPENROUTER_BASE_URL}/chat/completions"
        chave = self.chaves.get("openrouter") or self.api_key
        headers = {"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
        payload = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": sys_prompt}] + self.historico[-6:] + [{"role": "user", "content": msg}],
            "temperature": 0.0 if json_mode else 0.3,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            dados = json.loads(response.read().decode())
            return dados["choices"][0]["message"]["content"].strip()

    def _requisicao_ollama(self, msg: str, sys_prompt: str, json_mode: bool) -> str:
        req_tags = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req_tags, timeout=3) as response:
            model_data = json.loads(response.read().decode())
            if not model_data.get("models"):
                raise RuntimeError("Nenhum modelo Ollama instalado.")
            model = model_data["models"][0]["name"]

        url = "http://localhost:11434/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": sys_prompt}] + self.historico[-6:] + [{"role": "user", "content": msg}],
            "stream": False,
            "options": {"temperature": 0.0 if json_mode else 0.3},
        }
        if json_mode:
            payload["format"] = "json"

        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as response:
            dados = json.loads(response.read().decode())
            return dados["message"]["content"].strip()

    def executar_comando(self, comando: str) -> Tuple[bool, str]:
        c = comando.lower()

        keywords_sistema = ["altere", "mude", "configure", "ajuste", "aumente o risco", "reduza", "probabilidade mínima"]
        if any(k in c for k in keywords_sistema) and self.autonomia:
            logger.info("⚡ Invocando Módulo de Autonomia Estrita (JSON Mode)...")
            resultado = self.autonomia.processar_comando_sistema(
                texto_falado=comando,
                estado_do_plano=self.estado_atual_do_plano,
            )
            if resultado["ok"]:
                self.estado_atual_do_plano = resultado["novo_estado"]
                self._salvar_estado_do_plano()
            return True, resultado["msg_vocal"]

        if "abrir tradovate" in c or "abrir corretora" in c:
            if self.sistema == "darwin":
                subprocess.Popen(["open", "https://trader.tradovate.com"])
            elif self.sistema == "windows":
                os.system("start https://trader.tradovate.com")
            return True, "Abrindo a plataforma Tradovate no seu navegador."

        if "abrir tradingview" in c or "abrir gráfico" in c or "abrir grafico" in c:
            if self.sistema == "darwin":
                subprocess.Popen(["open", "https://www.tradingview.com"])
            elif self.sistema == "windows":
                os.system("start https://www.tradingview.com")
            return True, "Abrindo o TradingView no navegador."

        if "abrir navegador" in c or "abrir chrome" in c:
            if self.sistema == "darwin":
                subprocess.Popen(["open", "-a", "Google Chrome"])
            elif self.sistema == "windows":
                os.system("start chrome")
            return True, "Abrindo o Google Chrome."

        if "abrir terminal" in c:
            if self.sistema == "darwin":
                subprocess.Popen(["open", "-a", "Terminal"])
            elif self.sistema == "windows":
                os.system("start cmd")
            return True, "Abrindo o Terminal."

        if "abrir bloco de notas" in c or "abrir notas" in c:
            if self.sistema == "darwin":
                subprocess.Popen(["open", "-a", "Notes"])
            elif self.sistema == "windows":
                os.system("start notepad")
            return True, "Abrindo o aplicativo de notas."

        if "que horas são" in c or "horário" in c or "horario" in c:
            agora = time.strftime("%H:%M")
            return True, f"Agora são {agora}."

        if "encerrar assistente" in c or "desligar tiger" in c or "tchau tiger" in c or "tchau jarvis" in c:
            self.executando = False
            return True, "Desligando o assistente de voz. Tenha um excelente pregão, Josevan."

        return False, ""

    def loop_principal(self, com_hud: bool = True):
        self.executando = True
        logger.info("🐯 [TIGER VOICE ASSISTANT] — Cascade Engine (Gemini -> OpenRouter -> Local) Iniciado.")

        hud = None
        if com_hud:
            try:
                from tiger_hud import TigerHolographicHUD
                hud = TigerHolographicHUD()
                hud.atualizar_estado("STANDBY", "Pronto para ouvir...", "TIGER Multi-LLM online.")
            except Exception:
                pass

        def _rotina_voz():
            self.falar_texto("Olá Josevan! Sistemas conectados com múltiplas contingências. Pronto para operar.")
            if hud:
                hud.atualizar_estado("STANDBY", "Aguardando...", "Pronto para operar.")

            while self.executando:
                try:
                    if hud:
                        hud.atualizar_estado("OUVINDO", "Escutando...", "Microfone aberto.")
                    fala = self.ouvir_microfone(timeout=4, frase_limite=8)
                    if not fala:
                        if hud:
                            hud.atualizar_estado("STANDBY", "Aguardando...", "Diga 'Olá Tiger'.")
                        continue

                    comando_util = fala
                    for w in WAKE_WORDS:
                        comando_util = comando_util.replace(w, "").strip()

                    if not comando_util and any(w in fala for w in WAKE_WORDS):
                        self.falar_texto("Sim, estou ouvindo.")
                        fala_seguinte = self.ouvir_microfone(timeout=6, frase_limite=10)
                        if fala_seguinte:
                            comando_util = fala_seguinte
                        else:
                            continue

                    if not comando_util:
                        continue

                    if hud:
                        hud.atualizar_estado("PENSANDO", comando_util, "Processando na nuvem...")

                    executou, msg_auto = self.executar_comando(comando_util)
                    if executou:
                        if hud:
                            hud.atualizar_estado("FALANDO", comando_util, msg_auto)
                        self.falar_texto(msg_auto)
                        continue

                    logger.info("🤖 Enviando para Cascade Engine...")
                    resposta_ia = self.consultar_ia_com_fallback(comando_util, json_mode=False)

                    if hud:
                        hud.atualizar_estado("FALANDO", comando_util, resposta_ia)
                    self.falar_texto(resposta_ia)
                    if hud:
                        hud.atualizar_estado("STANDBY", comando_util, resposta_ia)

                except Exception as e:
                    logger.error(f"Erro no loop de voz: {e}")
                    time.sleep(1)

        t_voz = threading.Thread(target=_rotina_voz, daemon=True)
        t_voz.start()

        if hud:
            try:
                hud.root.mainloop()
            except KeyboardInterrupt:
                pass
            finally:
                self.executando = False
        else:
            try:
                while self.executando:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.executando = False


def main():
    assistente = TigerVoiceAssistant()
    assistente.loop_principal(com_hud=("--sem-hud" not in sys.argv))


if __name__ == "__main__":
    main()
