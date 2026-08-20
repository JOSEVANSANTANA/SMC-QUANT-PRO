#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tiger_hud.py — Interface Gráfica Holográfica Estilo Jarvis / TIGER HUD

Oferece:
  1. TigerHUDEmbeddedFrame: Frame embutido na aba TIGER do SMC Quant Pro com Orbe animado ao vivo e telemetria.
  2. TigerHolographicHUD: Janela flutuante desacoplada (Interface Solta / Always on Top) arrastável sobre o gráfico.
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


class HUDCanvasRenderer:
    """Motor de renderização vetorial holográfico compartilhado entre o frame embutido e a janela solta."""

    def __init__(self, canvas: Canvas, largura: int = 700, altura: int = 240, modo_compacto: bool = False):
        self.canvas = canvas
        self.largura = largura
        self.altura = altura
        self.modo_compacto = modo_compacto

        self.estado = "STANDBY"  # STANDBY, OUVINDO, PENSANDO, FALANDO
        self.angulo_rotacao = 0.0
        self.fase_pulso = 0.0
        self.texto_usuario = "Aguardando comando..."
        self.texto_resposta = "TIGER 2.0 // Jarvis Engine online via OpenRouter."
        self.ativo_smc = "MNQ / NQ Futures"
        self.score_confluencia = "Score: 92/100"
        self.modelo_ativo = "OpenRouter: Claude 3.5 Sonnet"

    def atualizar_estado(self, estado: str, texto_usuario: str = "", texto_resposta: str = ""):
        self.estado = estado
        if texto_usuario:
            self.texto_usuario = texto_usuario
        if texto_resposta:
            self.texto_resposta = texto_resposta

    def desenhar(self):
        self.canvas.delete("all")
        w, h = self.largura, self.altura

        # 1. Moldura Futurista HUD
        self.canvas.create_rectangle(6, 6, w - 6, h - 6, outline=COR_NEON_AZUL, width=1)
        self.canvas.create_line(12, 32, w - 12, 32, fill=COR_NEON_AZUL, width=1)

        # Cantos HUD
        c = 12
        self.canvas.create_line(6, 6, 6 + c, 6, fill=COR_NEON_CYAN, width=2)
        self.canvas.create_line(6, 6, 6, 6 + c, fill=COR_NEON_CYAN, width=2)
        self.canvas.create_line(w - 6, 6, w - 6 - c, 6, fill=COR_NEON_CYAN, width=2)
        self.canvas.create_line(w - 6, 6, w - 6, 6 + c, fill=COR_NEON_CYAN, width=2)

        # Cabeçalho
        self.canvas.create_text(18, 18, text="⚡ TIGER 2.0 // JARVIS HUD", anchor="w", font=("Courier", 10, "bold"), fill=COR_NEON_CYAN)
        cor_status = COR_NEON_VERDE if self.estado in ("OUVINDO", "FALANDO") else (COR_NEON_DOURADO if self.estado == "PENSANDO" else COR_NEON_CYAN)
        self.canvas.create_text(w // 2, 18, text=f"STATUS: {self.estado}", font=("Courier", 10, "bold"), fill=cor_status)
        self.canvas.create_text(w - 40, 18, text="100% CLOUD", font=("Courier", 8), fill=COR_TEXTO_MUTED)

        # 2. Orbe Holográfico Central
        cx = w // 2
        cy = (h // 2) - (15 if not self.modo_compacto else 0)
        raio_base = (42 if self.modo_compacto else 50) + math.sin(self.fase_pulso) * (8 if self.estado in ("OUVINDO", "FALANDO") else 2.5)

        # Glow exterior
        for r, opac in [(raio_base + 18, "#031d2e"), (raio_base + 10, "#07324f"), (raio_base + 5, "#0d4d7a")]:
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=opac, width=2)

        # Anel Exterior com marcas angulares
        self.canvas.create_oval(cx - raio_base, cy - raio_base, cx + raio_base, cy + raio_base, outline=COR_NEON_CYAN, width=2)
        for i in range(12):
            ang = self.angulo_rotacao + (i * (math.pi / 6))
            x1 = cx + (raio_base - 5) * math.cos(ang)
            y1 = cy + (raio_base - 5) * math.sin(ang)
            x2 = cx + (raio_base + 5) * math.cos(ang)
            y2 = cy + (raio_base + 5) * math.sin(ang)
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

        # Núcleo / Rosto do Orbe
        raio_core = raio_base * 0.35
        cor_core = COR_NEON_DOURADO if self.estado == "PENSANDO" else (COR_NEON_VERDE if self.estado == "OUVINDO" else COR_NEON_CYAN)
        self.canvas.create_oval(cx - raio_core, cy - raio_core, cx + raio_core, cy + raio_core, fill=COR_CARD_BG, outline=cor_core, width=2)

        if self.estado == "FALANDO":
            pontos = []
            for px in range(int(cx - raio_core + 4), int(cx + raio_core - 4), 3):
                py = cy + math.sin(self.fase_pulso * 3 + px * 0.25) * 6
                pontos.extend([px, py])
            if len(pontos) >= 4:
                self.canvas.create_line(pontos, fill=COR_NEON_CYAN, width=2, smooth=True)
        else:
            self.canvas.create_rectangle(cx - 8, cy - 3, cx - 3, cy + 1, fill=cor_core, outline="")
            self.canvas.create_rectangle(cx + 3, cy - 3, cx + 8, cy + 1, fill=cor_core, outline="")
            self.canvas.create_arc(cx - 8, cy + 1, cx + 8, cy + 9, start=200, extent=140, style="arc", outline=cor_core, width=2)

        # 3. Cartões Laterais de Telemetria
        card_w = 175
        # Esquerdo (SMC)
        self.canvas.create_rectangle(15, 45, 15 + card_w, h - 15 if not self.modo_compacto else h - 45, fill=COR_CARD_BG, outline=COR_NEON_AZUL, width=1)
        self.canvas.create_text(25, 58, text="📊 TELEMETRIA SMC", anchor="w", font=("Courier", 8, "bold"), fill=COR_NEON_CYAN)
        self.canvas.create_text(25, 82, text=f"ATIVO: {self.ativo_smc[:16]}", anchor="w", font=("Arial", 8), fill=COR_TEXTO)
        self.canvas.create_text(25, 102, text="REGIME: Expansão", anchor="w", font=("Arial", 8), fill=COR_TEXTO)
        self.canvas.create_text(25, 122, text=self.score_confluencia, anchor="w", font=("Arial", 8, "bold"), fill=COR_NEON_VERDE)
        if not self.modo_compacto and h > 200:
            self.canvas.create_text(25, 145, text="ORDER FLOW (CVD):", anchor="w", font=("Arial", 7), fill=COR_TEXTO_MUTED)
            self.canvas.create_text(25, 162, text="Delta +1,420 (Alta)", anchor="w", font=("Arial", 8, "bold"), fill=COR_NEON_CYAN)

        # Direito (OpenRouter Cloud)
        self.canvas.create_rectangle(w - 15 - card_w, 45, w - 15, h - 15 if not self.modo_compacto else h - 45, fill=COR_CARD_BG, outline=COR_NEON_AZUL, width=1)
        self.canvas.create_text(w - card_w - 5, 58, text="🤖 MOTOR IA CLOUD", anchor="w", font=("Courier", 8, "bold"), fill=COR_NEON_CYAN)
        self.canvas.create_text(w - card_w - 5, 82, text="PROVEDOR: OpenRouter", anchor="w", font=("Arial", 8), fill=COR_TEXTO)
        self.canvas.create_text(w - card_w - 5, 102, text="MODELO: Claude 3.5", anchor="w", font=("Arial", 8), fill=COR_TEXTO)
        self.canvas.create_text(w - card_w - 5, 122, text="IA LOCAL: Desativada", anchor="w", font=("Arial", 8), fill=COR_TEXTO_MUTED)
        if not self.modo_compacto and h > 200:
            self.canvas.create_text(w - card_w - 5, 145, text="LATÊNCIA: 240ms", anchor="w", font=("Arial", 7), fill=COR_NEON_VERDE)
            self.canvas.create_text(w - card_w - 5, 162, text="VOZ: STT/TTS Ativo", anchor="w", font=("Arial", 8, "bold"), fill=COR_NEON_CYAN)

        # 4. Transcrição / Live Prompt (no rodapé do HUD)
        if h > 220:
            self.canvas.create_line(15, h - 50, w - 15, h - 50, fill=COR_NEON_AZUL, width=1)
            self.canvas.create_text(25, h - 35, text=f"🎤 {self.texto_usuario[:65]}", anchor="w", font=("Arial", 9, "italic"), fill="#90caf9")
            self.canvas.create_text(25, h - 16, text=f"🐯 {self.texto_resposta[:75]}", anchor="w", font=("Arial", 9, "bold"), fill=COR_TEXTO)


class TigerHUDEmbeddedFrame(tk.Frame):
    """Componente visual holográfico embutido diretamente na aba TIGER do SMC Quant Pro."""

    def __init__(self, master, largura: int = 720, altura: int = 210, **kwargs):
        super().__init__(master, bg=COR_FUNDO, **kwargs)
        self.largura = largura
        self.altura = altura

        self.canvas = Canvas(
            self,
            width=self.largura,
            height=self.altura,
            bg=COR_FUNDO,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.renderer = HUDCanvasRenderer(self.canvas, self.largura, self.altura, modo_compacto=True)
        self._animando = True
        self._loop_animacao()

    def atualizar_estado(self, estado: str, texto_usuario: str = "", texto_resposta: str = ""):
        self.renderer.atualizar_estado(estado, texto_usuario, texto_resposta)

    def _loop_animacao(self):
        if not self._animando:
            return
        self.renderer.angulo_rotacao += 0.05
        self.renderer.fase_pulso += 0.1
        self.renderer.desenhar()
        self.after(35, self._loop_animacao)

    def destruir(self):
        self._animando = False
        self.destroy()


class TigerHolographicHUD:
    """Janela flutuante desacoplada (Interface Solta / Always on Top) estilo Jarvis."""

    def __init__(self, root: Optional[tk.Tk] = None, on_close=None):
        self._proprio_root = False
        if root is None:
            self.root = tk.Tk()
            self._proprio_root = True
        else:
            self.root = tk.Toplevel(root)

        self.on_close = on_close
        self.root.title("TIGER 2.0 // HOLOGRAPHIC HUD")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        try:
            self.root.attributes("-alpha", 0.94)
        except Exception:
            pass

        self.largura = 740
        self.altura = 380
        largura_tela = self.root.winfo_screenwidth()
        pos_x = (largura_tela - self.largura) // 2
        pos_y = 60
        self.root.geometry(f"{self.largura}x{self.altura}+{pos_x}+{pos_y}")
        self.root.configure(bg=COR_FUNDO)

        # Arraste com mouse
        self.root.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.root.bind("<B1-Motion>", self._arrastar)

        self.canvas = Canvas(
            self.root,
            width=self.largura,
            height=self.altura,
            bg=COR_FUNDO,
            highlightthickness=1,
            highlightbackground=COR_NEON_AZUL
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.btn_fechar = tk.Label(
            self.root,
            text="✕",
            font=("Arial", 12, "bold"),
            fg=COR_NEON_CYAN,
            bg=COR_FUNDO,
            cursor="hand2"
        )
        self.btn_fechar.place(x=self.largura - 28, y=8)
        self.btn_fechar.bind("<Button-1>", lambda e: self.fechar())

        self.renderer = HUDCanvasRenderer(self.canvas, self.largura, self.altura, modo_compacto=False)
        self._animando = True
        self._loop_animacao()

    def _iniciar_arraste(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def _arrastar(self, event):
        x = self.root.winfo_x() + (event.x - self._offset_x)
        y = self.root.winfo_y() + (event.y - self._offset_y)
        self.root.geometry(f"+{x}+{y}")

    def atualizar_estado(self, estado: str, texto_usuario: str = "", texto_resposta: str = ""):
        self.renderer.atualizar_estado(estado, texto_usuario, texto_resposta)

    def _loop_animacao(self):
        if not self._animando:
            return
        self.renderer.angulo_rotacao += 0.05
        self.renderer.fase_pulso += 0.1
        self.renderer.desenhar()
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
    hud.root.mainloop()


if __name__ == "__main__":
    main()
