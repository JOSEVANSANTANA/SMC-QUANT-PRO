#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tiger_voice.py / jarvis.py — Assistente Virtual de Voz Institucional (IA TIGER / Jarvis)

Módulo autônomo e modular de interação por voz em tempo real:
  - Processamento LLM: EXCLUSIVAMENTE via API OpenRouter (sem IA local/Llama pesada).
  - STT (Speech-to-Text): Reconhecimento de voz contínuo via SpeechRecognition.
  - TTS (Text-to-Speech): Síntese de voz com baixa latência (say nativo no macOS / pyttsx3 no Windows).
  - Automações de SO e Plataforma: Controle de navegador, janelas, Tradovate e comandos do sistema.
  - Segurança: Chaves carregadas via .env (python-dotenv) ou Chaveiro/Config do SMC Quant Pro.
"""

import os
import sys
import time
import json
import logging
import platform
import subprocess
import threading
from typing import Dict, List, Optional, Tuple

# Carregamento de variáveis de ambiente
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Reconhecimento de Fala (STT)
try:
    import speech_recognition as sr
    SR_DISPONIVEL = True
except ImportError:
    SR_DISPONIVEL = False

# Síntese de Voz (TTS)
try:
    import pyttsx3
    PYTTSX3_DISPONIVEL = True
except ImportError:
    PYTTSX3_DISPONIVEL = False

# Cliente OpenAI para compatibilidade com OpenRouter
try:
    from openai import OpenAI
    OPENAI_LIB_DISPONIVEL = True
except ImportError:
    OPENAI_LIB_DISPONIVEL = False

try:
    import requests
    REQUESTS_DISPONIVEL = True
except ImportError:
    REQUESTS_DISPONIVEL = False

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TIGER_VOICE")

# Configurações Padrão
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODELO_PADRAO = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
MODELOS_RAPIDOS = [
    "anthropic/claude-3.5-sonnet",
    "meta-llama/llama-3.3-70b-instruct",
    "openai/gpt-4o-mini",
    "deepseek/deepseek-chat",
    "google/gemini-2.0-flash-001"
]
WAKE_WORDS = ["tiger", "olá tiger", "ola tiger", "jarvis", "olá jarvis", "ola jarvis"]


class TigerVoiceAssistant:
    """Assistente de Voz inteligente integrado com OpenRouter e automação de sistema."""

    def __init__(self, api_key: Optional[str] = None, modelo: str = MODELO_PADRAO):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or self._obter_chave_smc()
        self.modelo = modelo
        self.sistema = platform.system().lower()
        self.executando = False
        self.historico: List[Dict[str, str]] = []
        self._lock_fala = threading.Lock()

        # Inicializa STT
        if SR_DISPONIVEL:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
        else:
            self.recognizer = None
            logger.warning("SpeechRecognition não instalado. Entrada por voz desativada.")

        # Inicializa TTS offline (pyttsx3)
        self.engine_tts = None
        if self.sistema != "darwin" and PYTTSX3_DISPONIVEL:
            try:
                self.engine_tts = pyttsx3.init()
                self.engine_tts.setProperty("rate", 190)
            except Exception as e:
                logger.warning(f"Falha ao iniciar pyttsx3: {e}")

        # Inicializa Cliente OpenRouter
        self.client_openai = None
        if OPENAI_LIB_DISPONIVEL and self.api_key:
            self.client_openai = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=self.api_key,
                default_headers={
                    "HTTP-Referer": "https://tigerinvest.vip",
                    "X-Title": "SMC Quant Pro Tiger Voice Assistant"
                }
            )

    def _obter_chave_smc(self) -> str:
        """Tenta recuperar a chave do OpenRouter salva no ecossistema SMC Quant Pro."""
        # 1. Tenta ler do arquivo de configuração local
        caminhos_cfg = [
            os.path.expanduser("~/Library/Application Support/SMC_Quant_Pro/config.json"),
            os.path.expanduser("~/.smc_quant_pro/config.json"),
            os.path.join(os.getcwd(), "config.json")
        ]
        for c in caminhos_cfg:
            if os.path.isfile(c):
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        dados = json.load(f)
                        k = dados.get("chaves_provedores", {}).get("openrouter")
                        if k and len(k) > 10:
                            return k
                except Exception:
                    pass
        return ""

    # =========================================================================
    #  Módulo 1: TTS (Text-to-Speech / Falar)
    # =========================================================================
    def falar_texto(self, texto: str):
        """Converte texto em fala e reproduz no alto-falante sem travar a interface."""
        if not texto or not texto.strip():
            return

        limpo = texto.replace("*", "").replace("#", "").replace("`", "").strip()
        logger.info(f"🗣️ [TIGER]: {limpo}")

        with self._lock_fala:
            if self.sistema == "darwin":
                # No macOS, o comando nativo 'say' possui a menor latência e voz limpa
                try:
                    subprocess.run(["say", "-r", "195", limpo], check=False)
                    return
                except Exception as e:
                    logger.warning(f"Falha no comando say do macOS: {e}")

            if self.engine_tts:
                try:
                    self.engine_tts.say(limpo)
                    self.engine_tts.runAndWait()
                    return
                except Exception as e:
                    logger.warning(f"Falha no pyttsx3: {e}")

            # Fallback para print se nenhum TTS estiver disponível
            print(f"\n[TIGER FALA]: {limpo}\n")

    # =========================================================================
    #  Módulo 2: STT (Speech-to-Text / Ouvir Microfone)
    # =========================================================================
    def ouvir_microfone(self, timeout: int = 5, frase_limite: int = 8) -> Optional[str]:
        """Escuta o microfone local e converte áudio para texto em português."""
        if not self.recognizer:
            logger.error("Reconhecedor de fala não disponível.")
            return None

        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                logger.info("🎤 Escutando microfone...")
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=frase_limite)

            texto = self.recognizer.recognize_google(audio, language="pt-BR")
            logger.info(f"👂 [VOCÊ]: {texto}")
            return texto.strip().lower()

        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            logger.error(f"Erro no serviço de reconhecimento de voz: {e}")
            return None
        except Exception as e:
            logger.warning(f"Erro ao capturar áudio: {e}")
            return None

    # =========================================================================
    #  Módulo 3: LLM (OpenRouter API)
    # =========================================================================
    def consultar_openrouter(self, mensagem_usuario: str) -> str:
        """Envia mensagem para a API do OpenRouter e retorna a resposta formatada."""
        if not self.api_key:
            return "Chave da API do OpenRouter não configurada. Por favor, defina a OPENROUTER_API_KEY no arquivo .env."

        # Prompt de Persona Institucional
        system_prompt = (
            "Você é a TIGER: a inteligência artificial mentora de trading institucional e assistente "
            "de automação do trader Josevan no SMC Quant Pro. Responda em português de forma concisa, "
            "direta, profissional e em texto corrido (sem markdown, sem asteriscos e sem listas com bullet), "
            "pois sua resposta será lida em voz alta por síntese de voz."
        )

        mensagens = [{"role": "system", "content": system_prompt}]
        mensagens.extend(self.historico[-6:])
        mensagens.append({"role": "user", "content": mensagem_usuario})

        # 1. Tentativa via OpenAI SDK com base_url do OpenRouter
        if self.client_openai:
            try:
                resposta = self.client_openai.chat.completions.create(
                    model=self.modelo,
                    messages=mensagens,
                    temperature=0.3,
                    max_tokens=350,
                    timeout=25
                )
                conteudo = resposta.choices[0].message.content or ""
                self.historico.append({"role": "user", "content": mensagem_usuario})
                self.historico.append({"role": "assistant", "content": conteudo})
                return conteudo.strip()
            except Exception as e:
                logger.warning(f"OpenAI SDK falhou no OpenRouter ({e}). Tentando fallback HTTP...")

        # 2. Requisição HTTP direta via urllib (biblioteca padrão, sem dependência externa)
        return self._requisicao_http_openrouter(mensagens, mensagem_usuario)

    def _requisicao_http_openrouter(self, mensagens: List[Dict[str, str]], mensagem_usuario: str) -> str:
        """Executa requisição HTTP direta ao OpenRouter via urllib.request nativo."""
        import urllib.request
        import urllib.error

        try:
            url = f"{OPENROUTER_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "SMC-Quant-Pro/2.53",
                "HTTP-Referer": "https://tigerinvest.vip",
                "X-Title": "SMC Quant Pro Tiger Voice Assistant"
            }
            payload = {
                "model": self.modelo,
                "messages": mensagens,
                "temperature": 0.3,
                "max_tokens": 350
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=25) as response:
                if response.status == 200:
                    dados = json.loads(response.read().decode("utf-8"))
                    conteudo = dados.get("choices", [{}])[0].get("message", {}).get("content", "")
                    self.historico.append({"role": "user", "content": mensagem_usuario})
                    self.historico.append({"role": "assistant", "content": conteudo})
                    return conteudo.strip()
                else:
                    return f"A API do OpenRouter retornou status {response.status}."
        except urllib.error.HTTPError as e:
            corpo = e.read().decode("utf-8", "replace")[:200]
            logger.error(f"Erro HTTP OpenRouter {e.code}: {corpo}")
            return f"A API do OpenRouter retornou erro HTTP {e.code}."
        except Exception as e:
            logger.error(f"Falha na requisição HTTP OpenRouter: {e}")
            return "Não consegui conectar aos servidores do OpenRouter no momento. Verifique sua conexão com a internet."

    # =========================================================================
    #  Módulo 4: Automação do Sistema Operacional & Comandos Rápidos
    # =========================================================================
    def executar_comando(self, comando: str) -> Tuple[bool, str]:
        """
        Analisa e executa comandos de automação local no sistema operacional.
        Retorna (executou_automacao: bool, mensagem_resposta: str).
        """
        c = comando.lower()

        # 1. Abrir Navegador / Tradovate / TradingView
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

        # 2. Comandos do Sistema
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

        # 3. Informações Rápidas de Horário
        if "que horas são" in c or "horário" in c or "horario" in c:
            agora = time.strftime("%H:%M")
            return True, f"Agora são {agora}."

        # 4. Encerramento do Assistente
        if "encerrar assistente" in c or "desligar tiger" in c or "tchau tiger" in c or "tchau jarvis" in c:
            self.executando = False
            return True, "Desligando o assistente de voz. Tenha um excelente pregão, Josevan."

        return False, ""

    # =========================================================================
    #  Módulo 5: Loop de Execução Contínuo (Jarvis / Tiger Loop)
    # =========================================================================
    def loop_principal(self):
        """Inicia o loop infinito de escuta e processamento da IA TIGER."""
        self.executando = True
        logger.info("🐯 [TIGER VOICE ASSISTANT INICIADO] — 100% OpenRouter Cloud Engine")
        self.falar_texto("Olá Josevan! Assistente Tiger online e conectado ao OpenRouter. Como posso ajudar você agora?")

        while self.executando:
            try:
                # 1. Escuta por comando ou wake word
                fala = self.ouvir_microfone(timeout=4, frase_limite=8)
                if not fala:
                    continue

                # 2. Verifica se contém wake word ou se é comando direto
                eh_chamado = any(w in fala for w in WAKE_WORDS)
                comando_util = fala
                for w in WAKE_WORDS:
                    comando_util = comando_util.replace(w, "").strip()

                # Se a frase contiver apenas o wake word, saúda e escuta a instrução
                if eh_chamado and not comando_util:
                    self.falar_texto("Sim, estou ouvindo.")
                    fala_seguinte = self.ouvir_microfone(timeout=6, frase_limite=10)
                    if fala_seguinte:
                        comando_util = fala_seguinte
                    else:
                        continue

                if not comando_util:
                    continue

                # 3. Tenta automação local primeiro
                executou, msg_auto = self.executar_comando(comando_util)
                if executou:
                    self.falar_texto(msg_auto)
                    continue

                # 4. Processa com OpenRouter LLM
                logger.info(f"🤖 Enviando para OpenRouter ({self.modelo})...")
                resposta_ia = self.consultar_openrouter(comando_util)
                self.falar_texto(resposta_ia)

            except KeyboardInterrupt:
                logger.info("Encerrando por interrupção de teclado.")
                self.executando = False
                break
            except Exception as e:
                logger.error(f"Erro inesperado no loop de voz: {e}")
                time.sleep(1)


# =============================================================================
#  Ponto de Entrada (Execução Standalone)
# =============================================================================
def main():
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║       🐯 TIGER VOICE ASSISTANT — 100% OPENROUTER CLOUD         ║
    ║   Controle de Voz Inteligente para Mesas Proprietárias (SMC)   ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    assistente = TigerVoiceAssistant()
    if not assistente.api_key:
        print("⚠️ AVISO: Nenhuma chave do OpenRouter encontrada.")
        print("Defina a variável de ambiente OPENROUTER_API_KEY ou configure no painel do SMC Quant Pro.")
    assistente.loop_principal()


if __name__ == "__main__":
    main()
