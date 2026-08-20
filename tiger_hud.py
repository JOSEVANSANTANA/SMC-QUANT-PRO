#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tiger_hud.py — Interface Gráfica Holográfica Estilo Jarvis / TIGER HUD

Janela flutuante (HUD Overlay / Glassmorphism) com:
  - Orbe holográfico central animado (pulsação neon cyan/azul/dourado ao escutar e falar).
  - Anéis concêntricos de energia e ondas sonoras em tempo real.
  - Cartões laterais com telemetria (Status da IA, OpenRouter Cloud, Contexto SMC e Transcrição).
  - Janela sem bordas (Frameless), translúcida e 'Always on Top'.
"""

import math
import time
import tkinter as tk
from tkinter import Canvas
import threading
from typing import Optional

COR_FUNDO = "#0a0e17"
COR_NEON_CYAN = "#00f0ff"
COR_NEON_AZUL = "#0066ff"
COR_NEON_VERDE = "#00ff88"
COR_NEON_DOURADO = "#ffb700"
COR_TEXTO = "#e0f7fa"
COR_TEXTO_MUTED = "#5c7c8a"
COR_CARD_BG = "#0f1726"


class TigerHolographicHUD:
    """HUD Holográfico flutuante estilo Jarvis / TIGER."""

    def __init__(self, root: Optional[tk.Tk] = None, on_close=None):
        self._proprio_root = False
        if root is None:
            self.root = tk.Tk()
            self._proprio_root = True
        else:
            self.root = tk.Toplevel(root)

        self.on_close = on_close
        self.root.title("TIGER 2.0 // HOLOGRAPHIC HUD")
        self.root.overrideredirect(True)  # Sem bordas da janela padrão
        self.root.attributes("-topmost", True)  # Sempre no topo

        # Transparência / Opacidade no macOS e Windows
        try:
            self.root.attributes("-alpha", 0.94)
        except Exception:
            pass

        # Dimensões e posicionamento no centro-superior da tela
        self.largura = 740
        self.altura = 460
        largura_tela = self.root.winfo_screenwidth()
        pos_x = (largura_tela - self.largura) // 2
        pos_y = 60
        self.root.geometry(f"{self.largura}x{self.altura}+{pos_x}+{pos_y}")
        self.root.configure(bg=COR_FUNDO)

        # Estados de Animação
        self.estado = "STANDBY"  # STANDBY, OUVINDO, PENSANDO, FALANDO
        self.angulo_rotacao = 0.0
        self.fase_pulso = 0.0
        self.texto_usuario = "Aguardando comando de voz..."
        self.texto_resposta = "TIGER 2.0 online. Diga 'Olá Tiger' ou 'Jarvis'."
        self.ativo_smc = "MNQ / NQ Futures"
        self.score_confluencia = "Score: 92/100 (Aprovado)"
        self.modelo_ativo = "OpenRouter: Claude 3.5 Sonnet"

        # Permitir arrastar a janela HUD
        self.root.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.root.bind("<B1-Motion>", self._arrastar)

        self._criar_elementos()
        self._animando = True
        self._loop_animacao()

    def _iniciar_arraste(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def _arrastar(self, event):
        x = self.root.winfo_x() + (event.x - self._offset_x)
        y = self.root.winfo_y() + (event.y - self._offset_y)
        self.root.geometry(f"+{x}+{y}")

    def _criar_elementos(self):
        # Canvas Principal para o Orbe Holográfico e HUD
        self.canvas = Canvas(
            self.root,
            width=self.largura,
            height=self.altura,
            bg=COR_FUNDO,
            highlightthickness=1,
            highlightbackground=COR_NEON_AZUL
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Botão Fechar discreto no canto superior direito
        self.btn_fechar = tk.Label(
            self.root,
            text="✕",
            font=("Arial", 12, "bold"),
            fg=COR_NEON_CYAN,
            bg=COR_FUNDO,
            cursor="hand2"
        )
        self.btn_fechar.place(x=self.largura - 30, y=10)
        self.btn_fechar.bind("<Button-1>", lambda e: self.fechar())

    def atualizar_estado(self, estado: str, texto_usuario: str = "", texto_resposta: str = ""):
        """Atualiza a telemetria e o estado do orbe."""
        self.estado = estado
        if texto_usuario:
            self.texto_usuario = texto_usuario
        if texto_resposta:
            self.texto_resposta = texto_resposta

    def _desenhar_hud(self):
        self.canvas.delete("all")

        # 1. Moldura Futurista HUD e Linhas de Grid
        self.canvas.create_rectangle(8, 8, self.largura - 8, self.altura - 8, outline=COR_NEON_AZUL, width=1)
        self.canvas.create_line(15, 40, self.largura - 15, 40, fill=COR_NEON_AZUL, width=1)
        self.canvas.create_line(15, self.altura - 40, self.largura - 15, self.altura - 40, fill=COR_NEON_AZUL, width=1)

        # Cantos com reforço HUD
        c = 15
        self.canvas.create_line(8, 8, 8 + c, 8, fill=COR_NEON_CYAN, width=3)
        self.canvas.create_line(8, 8, 8, 8 + c, fill=COR_NEON_CYAN, width=3)
        self.canvas.create_line(self.largura - 8, 8, self.largura - 8 - c, 8, fill=COR_NEON_CYAN, width=3)
        self.canvas.create_line(self.largura - 8, 8, self.largura - 8, 8 + c, fill=COR_NEON_CYAN, width=3)

        # Cabeçalho
        self.canvas.create_text(25, 25, text="⚡ TIGER 2.0 // JARVIS SYSTEM", anchor="w", font=("Courier", 11, "bold"), fill=COR_NEON_CYAN)
        cor_status = COR_NEON_VERDE if self.estado in ("OUVINDO", "FALANDO") else (COR_NEON_DOURADO if self.estado == "PENSANDO" else COR_NEON_CYAN)
        self.canvas.create_text(self.largura // 2, 25, text=f"STATUS: {self.estado}", font=("Courier", 11, "bold"), fill=cor_status)
        self.canvas.create_text(self.largura - 60, 25, text="100% CLOUD", font=("Courier", 9), fill=COR_TEXTO_MUTED)

        # 2. Orbe Holográfico Central
        cx, cy = self.largura // 2, 160
        raio_base = 55 + math.sin(self.fase_pulso) * (10 if self.estado in ("OUVINDO", "FALANDO") else 3)

        # Glow exterior
        for r, opac in [(raio_base + 25, "#031d2e"), (raio_base + 15, "#07324f"), (raio_base + 8, "#0d4d7a")]:
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=opac, width=2)

        # Anel Exterior com marcas angulares rotativas
        self.canvas.create_oval(cx - raio_base, cy - raio_base, cx + raio_base, cy + raio_base, outline=COR_NEON_CYAN, width=2)
        for i in range(12):
            ang = self.angulo_rotacao + (i * (math.pi / 6))
            x1 = cx + (raio_base - 6) * math.cos(ang)
            y1 = cy + (raio_base - 6) * math.sin(ang)
            x2 = cx + (raio_base + 6) * math.cos(ang)
            y2 = cy + (raio_base + 6) * math.sin(ang)
            self.canvas.create_line(x1, y1, x2, y2, fill=COR_NEON_CYAN, width=1)

        # Anel Interno em contra-rotação
        raio_int = raio_base * 0.65
        self.canvas.create_oval(cx - raio_int, cy - raio_int, cx + raio_int, cy + raio_int, outline=COR_NEON_AZUL, width=2)
        for i in range(8):
            ang = -self.angulo_rotacao * 1.5 + (i * (math.pi / 4))
            x1 = cx + (raio_int - 4) * math.cos(ang)
            y1 = cy + (raio_int - 4) * math.sin(ang)
            x2 = cx + (raio_int + 4) * math.cos(ang)
            y2 = cy + (raio_int + 4) * math.sin(ang)
            self.canvas.create_line(x1, y1, x2, y2, fill=COR_NEON_VERDE if self.estado == "OUVINDO" else COR_NEON_AZUL, width=2)

        # Rosto / Núcleo do Orbe
        raio_core = raio_base * 0.35
        cor_core = COR_NEON_DOURADO if self.estado == "PENSANDO" else (COR_NEON_VERDE if self.estado == "OUVINDO" else COR_NEON_CYAN)
        self.canvas.create_oval(cx - raio_core, cy - raio_core, cx + raio_core, cy + raio_core, fill=COR_CARD_BG, outline=cor_core, width=2)

        # Olhos / Ondas de Voz no Centro
        if self.estado == "FALANDO":
            # Onda de voz senoidal
            pontos = []
            for px in range(int(cx - raio_core + 5), int(cx + raio_core - 5), 3):
                py = cy + math.sin(self.fase_pulso * 3 + px * 0.2) * 8
                pontos.extend([px, py])
            if len(pontos) >= 4:
                self.canvas.create_line(pontos, fill=COR_NEON_CYAN, width=2, smooth=True)
        else:
            # Olhos robóticos HUD
            self.canvas.create_rectangle(cx - 10, cy - 4, cx - 4, cy + 2, fill=cor_core, outline="")
            self.canvas.create_rectangle(cx + 4, cy - 4, cx + 10, cy + 2, fill=cor_core, outline="")
            self.canvas.create_arc(cx - 10, cy + 2, cx + 10, cy + 12, start=200, extent=140, style="arc", outline=cor_core, width=2)

        # 3. Cartões Laterais HUD
        # Cartão Esquerdo: SMC Context
        self.canvas.create_rectangle(25, 60, 210, 240, fill=COR_CARD_BG, outline=COR_NEON_AZUL, width=1)
        self.canvas.create_text(35, 75, text="📊 TELEMETRIA SMC", anchor="w", font=("Courier", 9, "bold"), fill=COR_NEON_CYAN)
        self.canvas.create_text(35, 105, text=f"ATIVO: {self.ativo_smc}", anchor="w", font=("Arial", 8), fill=COR_TEXTO)
        self.canvas.create_text(35, 130, text="REGIME: Expansão (Trend)", anchor="w", font=("Arial", 8), fill=COR_TEXTO)
        self.canvas.create_text(35, 155, text=self.score_confluencia, anchor="w", font=("Arial", 8), fill=COR_NEON_VERDE)
        self.canvas.create_text(35, 185, text="ORDER FLOW (CVD):", anchor="w", font=("Arial", 8), fill=COR_TEXTO_MUTED)
        self.canvas.create_text(35, 205, text="Delta +1,420 (Comprador)", anchor="w", font=("Arial", 8, "bold"), fill=COR_NEON_CYAN)

        # Cartão Direito: LLM Cloud Status
        self.canvas.create_rectangle(self.largura - 210, 60, self.largura - 25, 240, fill=COR_CARD_BG, outline=COR_NEON_AZUL, width=1)
        self.canvas.create_text(self.largura - 200, 75, text="🤖 MOTOR DE IA", anchor="w", font=("Courier", 9, "bold"), fill=COR_NEON_CYAN)
        self.canvas.create_text(self.largura - 200, 105, text="PROVEDOR: OpenRouter", anchor="w", font=("Arial", 8), fill=COR_TEXTO)
        self.canvas.create_text(self.largura - 200, 130, text="MODELO: Claude 3.5 Sonnet", anchor="w", font=("Arial", 8), fill=COR_TEXTO)
        self.canvas.create_text(self.largura - 200, 155, text="LATÊNCIA: 280ms", anchor="w", font=("Arial", 8), fill=COR_NEON_VERDE)
        self.canvas.create_text(self.largura - 200, 185, text="IA LOCAL: Desativada", anchor="w", font=("Arial", 8), fill=COR_TEXTO_MUTED)
        self.canvas.create_text(self.largura - 200, 205, text="MODO VOZ: STT/TTS Ativo", anchor="w", font=("Arial", 8, "bold"), fill=COR_NEON_CYAN)

        # 4. Painel Inferior: Transcrição e Resposta da TIGER
        self.canvas.create_rectangle(25, 260, self.largura - 25, 410, fill=COR_CARD_BG, outline=COR_NEON_CYAN, width=1)
        self.canvas.create_text(40, 280, text=f"🎤 VOCÊ:  \"{self.texto_usuario}\"", anchor="w", font=("Arial", 10, "italic"), fill="#90caf9")
        self.canvas.create_text(40, 320, text=f"🐯 TIGER: {self.texto_resposta}", anchor="w", font=("Arial", 10, "bold"), fill=COR_TEXTO, width=self.largura - 80)

        # Rodapé
        self.canvas.create_text(self.largura // 2, self.altura - 20, text="Pressione ESC ou clique no X para fechar o HUD", font=("Courier", 8), fill=COR_TEXTO_MUTED)

    def _loop_animacao(self):
        if not self._animando:
            return
        self.angulo_rotacao += 0.05
        self.fase_pulso += 0.1
        self._desenhar_hud()
        self.root.after(35, self._loop_animacao)

    def fechar(self):
        self._animando = False
        if self.on_close:
            self.on_close()
        self.root.destroy()

    def exibir(self):
        self.root.deiconify()
        self.root.lift()

    def ocultar(self):
        self.root.withdraw()


def main():
    hud = TigerHolographicHUD()
    # Simula troca de estados
    def simular():
        estados = [
            ("OUVINDO", "Olá Tiger, qual a tendência do NQ agora?", "..."),
            ("PENSANDO", "Olá Tiger, qual a tendência do NQ agora?", "Processando via OpenRouter Claude 3.5..."),
            ("FALANDO", "Olá Tiger, qual a tendência do NQ agora?", "O NQ rompeu o Order Block de 15 minutos em 20.450 com fluxo comprador expressivo. O alvo projetado é 20.520."),
            ("STANDBY", "Comando concluído.", "TIGER 2.0 aguardando próximo chamado.")
        ]
        while True:
            for est, u, r in estados:
                time.sleep(3)
                hud.atualizar_estado(est, u, r)

    threading.Thread(target=simular, daemon=True).start()
    hud.root.mainloop()


if __name__ == "__main__":
    main()
