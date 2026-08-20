#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tiger_hud.py — Interface Gráfica Holográfica Futurista Estilo Jarvis / TIGER HUD

Design Sci-Fi / Cyberpunk de Alta Fidelidade:
  - Orbe Reator Holográfico Central com anéis concêntricos girando em direções opostas.
  - Discadores angulares, marcações de graus, radar HUD e espectro sonoro animado (Equalizer Bars).
  - Telemetria de Trading SMC em tempo real (Ativo, Regime de Mercado, Confluência, CVD Delta).
  - Status do Motor de IA Cloud (OpenRouter, Claude 3.5 / GPT-4o Mini, Latência).
  - Transcrição de voz flutuante com brilho neon.
  - Modos: Embutido nativo na aba TIGER ou Janela Flutuante Desacoplada (Always-on-Top).
"""

import math
import time
import tkinter as tk
from tkinter import Canvas
import threading
from typing import Optional

# Paleta Sci-Fi / Cyberpunk Futurista
COR_FUNDO_DEEP = "#040711"
COR_CARD_BG = "#081021"
COR_CARD_BORDER = "#102a4a"
COR_CYAN_GLOW = "#00f5ff"
COR_CYAN_DIM = "#058b99"
COR_BLUE_ELECTRIC = "#0066ff"
COR_GREEN_CYBER = "#00ff88"
COR_GOLD_CYBER = "#ffb700"
COR_PURPLE_CYBER = "#b026ff"
COR_TEXT_BRIGHT = "#e6f9ff"
COR_TEXT_MUTED = "#4d738f"


class CyberHUDCanvasRenderer:
    """Motor Gráfico Vetorial de Alta Estética Holográfica / Jarvis."""

    def __init__(self, canvas: Canvas, largura: int = 800, altura: int = 260, modo_compacto: bool = False):
        self.canvas = canvas
        self.largura = largura
        self.altura = altura
        self.modo_compacto = modo_compacto

        self.estado = "STANDBY"  # STANDBY, OUVINDO, PENSANDO, FALANDO
        self.angulo_rotacao = 0.0
        self.fase_onda = 0.0
        self.texto_usuario = "Aguardando chamado por voz ('Olá Tiger' ou 'Jarvis')..."
        self.texto_resposta = "TIGER 2.0 // Jarvis Neural Engine online via OpenRouter."
        self.ativo_smc = "MNQ / NQ Futures"
        self.score_confluencia = "Score: 92/100 (Aprovado)"
        self.modelo_ativo = "OpenRouter: Claude 3.5 Sonnet"

        # Espectro de áudio simulado para animação
        self.barras_audio = [0.2] * 16

    def atualizar_estado(self, estado: str, texto_usuario: str = "", texto_resposta: str = ""):
        self.estado = estado
        if texto_usuario:
            self.texto_usuario = texto_usuario
        if texto_resposta:
            self.texto_resposta = texto_resposta

    def desenhar(self):
        self.canvas.delete("all")
        w, h = self.largura, self.altura
        cx, cy = w // 2, h // 2 - (10 if not self.modo_compacto else 0)

        # -------------------------------------------------------------
        # 1. Fundo Tecnológico e Grid Hexagonal / Linhas de Radar
        # -------------------------------------------------------------
        # Grade de linhas discretas de background
        for x in range(0, w, 40):
            self.canvas.create_line(x, 0, x, h, fill="#070e1c", width=1)
        for y in range(0, h, 40):
            self.canvas.create_line(0, y, w, y, fill="#070e1c", width=1)

        # Moldura Externa com Cantos Chanfrados Futuristas
        b = 8
        self.canvas.create_polygon(
            b + 15, b,
            w - b - 15, b,
            w - b, b + 15,
            w - b, h - b - 15,
            w - b - 15, h - b,
            b + 15, h - b,
            b, h - b - 15,
            b, b + 15,
            fill="", outline=COR_CARD_BORDER, width=1
        )

        # Detalhes Neon nos 4 cantos
        c_len = 22
        # Canto Superior Esquerdo
        self.canvas.create_line(b, b + 15, b + 15, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(b + 15, b, b + 15 + c_len, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(b, b + 15, b, b + 15 + c_len, fill=COR_CYAN_GLOW, width=2)
        # Canto Superior Direito
        self.canvas.create_line(w - b, b + 15, w - b - 15, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(w - b - 15, b, w - b - 15 - c_len, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(w - b, b + 15, w - b, b + 15 + c_len, fill=COR_CYAN_GLOW, width=2)

        # Barra Superior de Status
        self.canvas.create_text(24, 20, text="◈ TIGER 2.0 // JARVIS HOLOGRAPHIC HUD", anchor="w", font=("Courier", 10, "bold"), fill=COR_CYAN_GLOW)
        cor_st = COR_GREEN_CYBER if self.estado == "OUVINDO" else (COR_GOLD_CYBER if self.estado == "PENSANDO" else (COR_CYAN_GLOW if self.estado == "FALANDO" else COR_BLUE_ELECTRIC))
        self.canvas.create_text(w // 2, 20, text=f"SYSTEM: {self.estado}", font=("Courier", 11, "bold"), fill=cor_st)
        self.canvas.create_text(w - 24, 20, text="100% OPENROUTER CLOUD", anchor="e", font=("Courier", 8, "bold"), fill=COR_TEXT_MUTED)

        # -------------------------------------------------------------
        # 2. Orbe Central Reator Holográfico (Jarvis Cyber Core)
        # -------------------------------------------------------------
        raio_base = (46 if self.modo_compacto else 56) + math.sin(self.fase_onda) * (8 if self.estado in ("OUVINDO", "FALANDO") else 2.5)

        # Halo Glow Externo
        for glow_r, glow_col in [(raio_base + 32, "#031424"), (raio_base + 22, "#062238"), (raio_base + 12, "#0b3759")]:
            self.canvas.create_oval(cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r, outline=glow_col, width=2)

        # Anel 1: Anel de Radar Externo com marcas angulares
        self.canvas.create_oval(cx - raio_base, cy - raio_base, cx + raio_base, cy + raio_base, outline=COR_CYAN_DIM, width=1)
        for i in range(24):
            ang = self.angulo_rotacao + (i * (math.pi / 12))
            is_cardinal = (i % 6 == 0)
            len_tick = 8 if is_cardinal else 4
            x1 = cx + (raio_base - len_tick) * math.cos(ang)
            y1 = cy + (raio_base - len_tick) * math.sin(ang)
            x2 = cx + (raio_base + len_tick) * math.cos(ang)
            y2 = cy + (raio_base + len_tick) * math.sin(ang)
            self.canvas.create_line(x1, y1, x2, y2, fill=COR_CYAN_GLOW if is_cardinal else COR_CYAN_DIM, width=2 if is_cardinal else 1)

        # Anel 2: Arcos Segurados Giratórios (Efeito Sci-Fi Iron Man / Jarvis)
        r_arco = raio_base * 0.82
        ang_deg = math.degrees(self.angulo_rotacao)
        self.canvas.create_arc(cx - r_arco, cy - r_arco, cx + r_arco, cy + r_arco, start=ang_deg, extent=70, style="arc", outline=COR_CYAN_GLOW, width=3)
        self.canvas.create_arc(cx - r_arco, cy - r_arco, cx + r_arco, cy + r_arco, start=ang_deg + 120, extent=70, style="arc", outline=COR_CYAN_GLOW, width=3)
        self.canvas.create_arc(cx - r_arco, cy - r_arco, cx + r_arco, cy + r_arco, start=ang_deg + 240, extent=70, style="arc", outline=COR_CYAN_GLOW, width=3)

        # Anel 3: Contra-rotação interna
        r_int = raio_base * 0.62
        ang_contra = math.degrees(-self.angulo_rotacao * 1.6)
        self.canvas.create_arc(cx - r_int, cy - r_int, cx + r_int, cy + r_int, start=ang_contra, extent=90, style="arc", outline=cor_st, width=2)
        self.canvas.create_arc(cx - r_int, cy - r_int, cx + r_int, cy + r_int, start=ang_contra + 180, extent=90, style="arc", outline=cor_st, width=2)

        # Núcleo Reator / Cyber Face
        r_core = raio_base * 0.38
        self.canvas.create_oval(cx - r_core, cy - r_core, cx + r_core, cy + r_core, fill=COR_CARD_BG, outline=cor_st, width=2)

        # Animação Central: Equalizador ou Olhos Cibernéticos HUD
        if self.estado in ("FALANDO", "OUVINDO"):
            # Onda de voz senoidal e espectro pulsante
            pontos = []
            largura_onda = r_core * 1.5
            passo = 3
            for px in range(int(cx - largura_onda // 2), int(cx + largura_onda // 2), passo):
                dist = abs(px - cx) / (largura_onda / 2)
                amp = (1.0 - dist) * (10 if self.estado == "FALANDO" else 6)
                py = cy + math.sin(self.fase_onda * 3.5 + px * 0.3) * amp
                pontos.extend([px, py])
            if len(pontos) >= 4:
                self.canvas.create_line(pontos, fill=COR_CYAN_GLOW, width=2, smooth=True)
        else:
            # Olhos cibernéticos elegantes
            self.canvas.create_oval(cx - 9, cy - 4, cx - 3, cy + 2, fill=cor_st, outline="")
            self.canvas.create_oval(cx + 3, cy - 4, cx + 9, cy + 2, fill=cor_st, outline="")
            self.canvas.create_arc(cx - 10, cy + 2, cx + 10, cy + 12, start=200, extent=140, style="arc", outline=cor_st, width=2)

        # -------------------------------------------------------------
        # 3. Painéis Laterais Glassmorphism (SMC & IA Cloud)
        # -------------------------------------------------------------
        pw = 190
        # Painel Esquerdo: Telemetria SMC
        px1, py1, px2, py2 = 20, 42, 20 + pw, h - 20 if not self.modo_compacto else h - 55
        self.canvas.create_rectangle(px1, py1, px2, py2, fill=COR_CARD_BG, outline=COR_CARD_BORDER, width=1)
        self.canvas.create_text(px1 + 12, py1 + 15, text="⚡ TELEMETRIA SMC", anchor="w", font=("Courier", 9, "bold"), fill=COR_CYAN_GLOW)
        self.canvas.create_line(px1 + 10, py1 + 25, px2 - 10, py1 + 25, fill=COR_CARD_BORDER, width=1)
        self.canvas.create_text(px1 + 12, py1 + 42, text=f"• ATIVO: {self.ativo_smc[:14]}", anchor="w", font=("Arial", 8, "bold"), fill=COR_TEXT_BRIGHT)
        self.canvas.create_text(px1 + 12, py1 + 62, text="• REGIME: Expansão (Trend)", anchor="w", font=("Arial", 8), fill=COR_TEXT_BRIGHT)
        self.canvas.create_text(px1 + 12, py1 + 82, text=f"• {self.score_confluencia}", anchor="w", font=("Arial", 8, "bold"), fill=COR_GREEN_CYBER)
        if not self.modo_compacto and h > 200:
            self.canvas.create_text(px1 + 12, py1 + 105, text="• ORDER FLOW (CVD):", anchor="w", font=("Arial", 8), fill=COR_TEXT_MUTED)
            self.canvas.create_text(px1 + 12, py1 + 123, text="  Delta +1,420 (Comprador)", anchor="w", font=("Arial", 8, "bold"), fill=COR_CYAN_GLOW)

        # Painel Direito: Motor de IA Cloud
        rx1, ry1, rx2, ry2 = w - 20 - pw, 42, w - 20, h - 20 if not self.modo_compacto else h - 55
        self.canvas.create_rectangle(rx1, ry1, rx2, ry2, fill=COR_CARD_BG, outline=COR_CARD_BORDER, width=1)
        self.canvas.create_text(rx1 + 12, ry1 + 15, text="🤖 MOTOR IA CLOUD", anchor="w", font=("Courier", 9, "bold"), fill=COR_CYAN_GLOW)
        self.canvas.create_line(rx1 + 10, ry1 + 25, rx2 - 10, ry1 + 25, fill=COR_CARD_BORDER, width=1)
        self.canvas.create_text(rx1 + 12, ry1 + 42, text="• PROVEDOR: OpenRouter", anchor="w", font=("Arial", 8, "bold"), fill=COR_TEXT_BRIGHT)
        self.canvas.create_text(rx1 + 12, ry1 + 62, text="• MODELO: Claude 3.5 Sonnet", anchor="w", font=("Arial", 8), fill=COR_TEXT_BRIGHT)
        self.canvas.create_text(rx1 + 12, ry1 + 82, text="• LATÊNCIA: 240ms (Rápida)", anchor="w", font=("Arial", 8, "bold"), fill=COR_GREEN_CYBER)
        if not self.modo_compacto and h > 200:
            self.canvas.create_text(rx1 + 12, ry1 + 105, text="• IA LOCAL: Desativada (OFF)", anchor="w", font=("Arial", 8), fill=COR_TEXT_MUTED)
            self.canvas.create_text(rx1 + 12, ry1 + 123, text="• WAKE-WORD: 'Olá Tiger'/'Jarvis'", anchor="w", font=("Arial", 8, "bold"), fill=COR_GOLD_CYBER)

        # -------------------------------------------------------------
        # 4. Painel Inferior de Transcrição e Diálogo
        # -------------------------------------------------------------
        if h > 210:
            ty1, ty2 = h - 60, h - 14
            self.canvas.create_rectangle(20, ty1, w - 20, ty2, fill=COR_CARD_BG, outline=COR_CYAN_DIM, width=1)
            self.canvas.create_text(30, ty1 + 16, text=f"🎤 VOCÊ: {self.texto_usuario[:70]}", anchor="w", font=("Arial", 9, "italic"), fill="#90caf9")
            self.canvas.create_text(30, ty1 + 35, text=f"🐯 TIGER: {self.texto_resposta[:85]}", anchor="w", font=("Arial", 9, "bold"), fill=COR_TEXT_BRIGHT)


class TigerHUDEmbeddedFrame(tk.Frame):
    """Componente visual holográfico embutido diretamente na aba TIGER do SMC Quant Pro."""

    def __init__(self, master, largura: int = 800, altura: int = 210, **kwargs):
        super().__init__(master, bg=COR_FUNDO_DEEP, **kwargs)
        self.largura = largura
        self.altura = altura

        self.canvas = Canvas(
            self,
            width=self.largura,
            height=self.altura,
            bg=COR_FUNDO_DEEP,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self.renderer = CyberHUDCanvasRenderer(self.canvas, self.largura, self.altura, modo_compacto=True)
        self._animando = True
        self._loop_animacao()

    def atualizar_estado(self, estado: str, texto_usuario: str = "", texto_resposta: str = ""):
        self.renderer.atualizar_estado(estado, texto_usuario, texto_resposta)

    def _loop_animacao(self):
        if not self._animando:
            return
        self.renderer.angulo_rotacao += 0.04
        self.renderer.fase_onda += 0.08
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
            self.root.attributes("-alpha", 0.95)
        except Exception:
            pass

        self.largura = 780
        self.altura = 390
        largura_tela = self.root.winfo_screenwidth()
        pos_x = (largura_tela - self.largura) // 2
        pos_y = 50
        self.root.geometry(f"{self.largura}x{self.altura}+{pos_x}+{pos_y}")
        self.root.configure(bg=COR_FUNDO_DEEP)

        # Arraste com o mouse
        self.root.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.root.bind("<B1-Motion>", self._arrastar)

        self.canvas = Canvas(
            self.root,
            width=self.largura,
            height=self.altura,
            bg=COR_FUNDO_DEEP,
            highlightthickness=1,
            highlightbackground=COR_CYAN_DIM
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.btn_fechar = tk.Label(
            self.root,
            text="✕",
            font=("Arial", 12, "bold"),
            fg=COR_CYAN_GLOW,
            bg=COR_FUNDO_DEEP,
            cursor="hand2"
        )
        self.btn_fechar.place(x=self.largura - 28, y=8)
        self.btn_fechar.bind("<Button-1>", lambda e: self.fechar())

        self.renderer = CyberHUDCanvasRenderer(self.canvas, self.largura, self.altura, modo_compacto=False)
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
        self.renderer.angulo_rotacao += 0.04
        self.renderer.fase_onda += 0.08
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
