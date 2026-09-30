#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tiger_voice.py / jarvis.py — Assistente Virtual de Voz Institucional (IA TIGER / Jarvis)

Módulo autônomo e modular de interação por voz em tempo real:
  - PADRÃO CASCATA (Fallback): 1º Gemini -> 2º OpenRouter/Groq -> 3º Ollama (Local).
  - JSON Mode Nativo: Previne alucinações na alteração do núcleo de trading.
  - STT (Speech-to-Text): Reconhecimento de voz contínuo via SpeechRecognition.
  - TTS (Text-to-Speech): Síntese de voz com baixa latência (say nativo no macOS).
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

# Importa a Autonomia da TIGER
try:
    from tiger_autonomia import TigerAutonomia
except ImportError:
    TigerAutonomia = None

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

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TIGER_VOICE")

WAKE_WORDS = ["tiger", "olá tiger", "ola tiger", "jarvis", "olá jarvis", "ola jarvis"]


class TigerVoiceAssistant:
    """Assistente de Voz inteligente integrado com Cascata de LLMs."""

    def __init__(self):
        self.sistema = platform.system().lower()
        self.executando = False
        self.historico: List[Dict[str, str]] = []
        self._lock_fala = threading.Lock()
        
        # Carrega todas as chaves disponíveis no sistema
        self.chaves = self._carregar_todas_as_chaves()
        
        # Módulo de Autonomia e Sandboxing
        self.autonomia = TigerAutonomia(assistente_voz=self) if TigerAutonomia else None
        
        # Variável para simular a leitura do disco (substitua pelas chamadas reais ao seu config)
        self.estado_atual_do_plano = {
            "risco_pct": 5.0,
            "rr_minimo": 2.0,
            "probabilidade_minima": 65,
            "max_stops_seguidos": 3
        }

        # Inicializa STT
        if SR_DISPONIVEL:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
        else:
            self.recognizer = None

        # Inicializa TTS offline (pyttsx3)
        self.engine_tts = None
        if self.sistema != "darwin" and PYTTSX3_DISPONIVEL:
            try:
                self.engine_tts = pyttsx3.init()
                self.engine_tts.setProperty("rate", 190)
            except Exception:
                pass

    def _carregar_todas_as_chaves(self) -> Dict[str, str]:
        """Varre o config.json do usuário e carrega as chaves de todos os provedores."""
        chaves = {"gemini": os.getenv("GEMINI_API_KEY", ""), 
                  "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
                  "groq": os.getenv("GROQ_API_KEY", "")}
        
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
                        k_prov = dados.get("chaves_provedores", {})
                        if k_prov.get("gemini"): chaves["gemini"] = k_prov["gemini"]
                        if k_prov.get("openrouter"): chaves["openrouter"] = k_prov["openrouter"]
                        if k_prov.get("groq"): chaves["groq"] = k_prov["groq"]
                        # Algumas vezes a chave da Gemini fica solta no JSON principal
                        if dados.get("chave_gemini"): chaves["gemini"] = dados["chave_gemini"]
                except Exception:
                    pass
        return chaves
    
    def _salvar_estado_do_plano(self):
        """Simula salvar o estado modificado. Implemente para escrever no config.json real"""
        logger.info(f"💾 Salvando novo estado do plano no disco: {self.estado_atual_do_plano}")

    # =========================================================================
    #  Módulo 1: TTS e STT (Ouvir e Falar)
    # =========================================================================
    def falar_texto(self, texto: str):
        if not texto or not texto.strip(): return
        limpo = texto.replace("*", "").replace("#", "").replace("`", "").strip()
        logger.info(f"🗣️ [TIGER]: {limpo}")

        with self._lock_fala:
            if self.sistema == "darwin":
                try:
                    subprocess.run(["say", "-v", "Luciana", "-r", "195", limpo], check=False)
                    return
                except Exception: pass

            if self.engine_tts:
                try:
                    self.engine_tts.say(limpo)
                    self.engine_tts.runAndWait()
                    return
                except Exception: pass
            print(f"\n[TIGER FALA]: {limpo}\n")

    def ouvir_microfone(self, timeout: int = 5, frase_limite: int = 8) -> Optional[str]:
        if not self.recognizer: return None
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

    # =========================================================================
    #  Módulo 2: O Cérebro em Cascata (Gemini -> OpenRouter -> Local)
    # =========================================================================
    def consultar_ia_com_fallback(self, mensagem_usuario: str, json_mode: bool = False, prompt_customizado: str = None) -> str:
        """
        Roteador mestre de Inteligência. Garante 100% de disponibilidade.
        Tenta Gemini primeiro. Se falhar, vai para OpenRouter/Groq. Se falhar, usa Local.
        """
        system_prompt = prompt_customizado or (
            "Você é a TIGER: a inteligência artificial mentora de trading institucional e assistente "
            "do trader Josevan no SMC Quant Pro. Responda em português de forma direta e profissional, "
            "sem markdown, pois sua resposta será lida em voz alta."
        )

        # 1. TENTA GEMINI (Prioridade 1)
        if self.chaves.get("gemini"):
            try:
                resposta = self._requisicao_gemini(mensagem_usuario, system_prompt, json_mode)
                if resposta:
                    self._atualizar_historico(mensagem_usuario, resposta, json_mode)
                    return resposta
            except Exception as e:
                logger.warning(f"⚠️ Gemini falhou ({e}). Iniciando Rota de Backup (OpenRouter)...")

        # 2. TENTA OPENROUTER (Prioridade 2)
        if self.chaves.get("openrouter") or self.chaves.get("groq"):
            try:
                resposta = self._requisicao_openrouter(mensagem_usuario, system_prompt, json_mode)
                if resposta:
                    self._atualizar_historico(mensagem_usuario, resposta, json_mode)
                    return resposta
            except Exception as e:
                logger.warning(f"⚠️ Nuvem Backup falhou ({e}). Acordando IA Local...")

        # 3. TENTA OLLAMA LOCAL (Último Recurso)
        try:
            resposta = self._requisicao_ollama(mensagem_usuario, system_prompt, json_mode)
            if resposta:
                self._atualizar_historico(mensagem_usuario, resposta, json_mode)
                return resposta
        except Exception as e:
            logger.error(f"❌ Falha Crítica: IA Local também não respondeu ({e}).")

        # Fallback Final de Erro
        if json_mode:
            return '{"sucesso": false, "resposta_vocal": "Perda total de comunicação com os motores de inferência. Ação abortada para proteger o capital."}'
        return "Sinto muito, Josevan. Todos os meus sistemas na nuvem e locais perderam a conexão. Não consigo processar a resposta agora."

    def _atualizar_historico(self, user_msg, asst_msg, json_mode):
        if not json_mode: # Não poluimos o histórico com JSONs sistêmicos
            self.historico.append({"role": "user", "content": user_msg})
            self.historico.append({"role": "assistant", "content": asst_msg})

    def _requisicao_gemini(self, msg: str, sys_prompt: str, json_mode: bool) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.chaves['gemini']}"
        contents = []
        # Converte histórico para o formato do Gemini
        for h in self.historico[-6:] + [{"role": "user", "content": msg}]:
            role = "model" if h["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": h["content"]}]})
            
        payload = {
            "system_instruction": {"parts": [{"text": sys_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.0 if json_mode else 0.3}
        }
        if json_mode:
            payload["generationConfig"]["response_mime_type"] = "application/json"

        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as response:
            dados = json.loads(response.read().decode())
            return dados["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _requisicao_openrouter(self, msg: str, sys_prompt: str, json_mode: bool) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.chaves.get('openrouter')}", "Content-Type": "application/json"}
        payload = {
            "model": "anthropic/claude-3.5-sonnet",
            "messages": [{"role": "system", "content": sys_prompt}] + self.historico[-6:] + [{"role": "user", "content": msg}],
            "temperature": 0.0 if json_mode else 0.3
        }
        if json_mode: payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            dados = json.loads(response.read().decode())
            return dados["choices"][0]["message"]["content"].strip()

    def _requisicao_ollama(self, msg: str, sys_prompt: str, json_mode: bool) -> str:
        # Acha o modelo instalado para não chutar
        try:
            req_tags = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req_tags, timeout=3) as response:
                model_data = json.loads(response.read().decode())
                if not model_data.get("models"):
                    raise Exception("Nenhum modelo Ollama instalado.")
                model = model_data["models"][0]["name"]
        except Exception:
            raise Exception("Ollama não está rodando na porta 11434.")

        url = "http://localhost:11434/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": sys_prompt}] + self.historico[-6:] + [{"role": "user", "content": msg}],
            "stream": False,
            "options": {"temperature": 0.0 if json_mode else 0.3}
        }
        if json_mode: payload["format"] = "json"

        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as response:
            dados = json.loads(response.read().decode())
            return dados["message"]["content"].strip()

    # =========================================================================
    #  Módulo 3: Automação Rápida e Autonomia
    # =========================================================================
    def executar_comando(self, comando: str) -> Tuple[bool, str]:
        c = comando.lower()
        
        # MÓDULO DE AUTONOMIA (Barreira Anti-Alucinação)
        keywords_sistema = ["altere", "mude", "configure", "ajuste", "aumente o risco", "reduza", "probabilidade mínima"]
        eh_comando_sistema = any(k in c for k in keywords_sistema)
        
        if eh_comando_sistema and self.autonomia:
             logger.info("⚡ Invocando Módulo de Autonomia Estrita (JSON Mode)...")
             resultado = self.autonomia.processar_comando_sistema(
                 texto_falado=comando,
                 estado_do_plano=self.estado_atual_do_plano
             )
             if resultado["ok"]:
                 self.estado_atual_do_plano = resultado["novo_estado"]
                 self._salvar_estado_do_plano()
                 return True, resultado["msg_vocal"]
             else:
                 return True, resultado["msg_vocal"]

        # Comandos Nativos do SO
        if "abrir tradovate" in c:
            subprocess.Popen(["open", "https://trader.tradovate.com"]) if self.sistema == "darwin" else os.system("start https://trader.tradovate.com")
            return True, "Abrindo a plataforma Tradovate."
        if "encerrar assistente" in c or "desligar tiger" in c:
            self.executando = False
            return True, "Desligando os motores principais. Tenha um excelente pregão, Josevan."

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
            except Exception: pass

        def _rotina_voz():
            self.falar_texto("Olá Josevan! Sistemas conectados com múltiplas contingências. Pronto para operar.")
            if hud: hud.atualizar_estado("STANDBY", "Aguardando...", "Pronto para operar.")

            while self.executando:
                try:
                    if hud: hud.atualizar_estado("OUVINDO", "Escutando...", "Microfone aberto.")
                    fala = self.ouvir_microfone(timeout=4, frase_limite=8)
                    if not fala:
                        if hud: hud.atualizar_estado("STANDBY", "Aguardando...", "Diga 'Olá Tiger'.")
                        continue

                    comando_util = fala
                    for w in WAKE_WORDS: comando_util = comando_util.replace(w, "").strip()

                    if not comando_util and any(w in fala for w in WAKE_WORDS):
                        self.falar_texto("Sim, estou ouvindo.")
                        fala_seguinte = self.ouvir_microfone(timeout=6, frase_limite=10)
                        if fala_seguinte: comando_util = fala_seguinte
                        else: continue

                    if not comando_util: continue

                    if hud: hud.atualizar_estado("PENSANDO", comando_util, "Processando na nuvem...")
                    
                    # Tenta comandos locais e Autonomia Estrita Primeiro
                    executou, msg_auto = self.executar_comando(comando_util)
                    if executou:
                        if hud: hud.atualizar_estado("FALANDO", comando_util, msg_auto)
                        self.falar_texto(msg_auto)
                        continue

                    # Bate-papo de mercado: Vai pro Cascade de LLMs
                    logger.info("🤖 Enviando para Cascade Engine...")
                    resposta_ia = self.consultar_ia_com_fallback(comando_util, json_mode=False)
                    
                    if hud: hud.atualizar_estado("FALANDO", comando_util, resposta_ia)
                    self.falar_texto(resposta_ia)
                    if hud: hud.atualizar_estado("STANDBY", comando_util, resposta_ia)

                except Exception as e:
                    logger.error(f"Erro no loop de voz: {e}")
                    time.sleep(1)

        t_voz = threading.Thread(target=_rotina_voz, daemon=True)
        t_voz.start()

        if hud:
            try: hud.root.mainloop()
            except KeyboardInterrupt: pass
            finally: self.executando = False
        else:
            try:
                while self.executando: time.sleep(0.5)
            except KeyboardInterrupt: self.executando = False


def main():
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║        🐯 TIGER VOICE ASSISTANT — CASCADE ENGINE v3.0          ║
    ║        (Gemini -> OpenRouter -> Groq -> Local Ollama)          ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    assistente = TigerVoiceAssistant()
    assistente.loop_principal(com_hud=("--sem-hud" not in sys.argv))

if __name__ == "__main__":
    main()