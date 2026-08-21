#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tiger_hud.py — Interface Gráfica Holográfica Futurista Estilo Jarvis / TIGER HUD

Design Sci-Fi / Cyberpunk de Alta Fidelidade com suporte a:
  - Redimensionamento dinâmico e Modo Maximizado / Tela Cheia.
  - Orbe Reator Holográfico Imponente com anéis concêntricos de alta rotação.
  - Grade de radar, anéis de graus, partículas orbitais e equalizador de voz em tempo real.
  - Painéis laterais de telemetria SMC e OpenRouter Cloud Engine.
  - Integração nativa na aba TIGER ou Janela Flutuante Desacoplada (Always-on-Top).
"""

import math
import time
import tkinter as tk
from tkinter import Canvas
import threading
from typing import Optional

# Paleta Sci-Fi / Cyberpunk Futurista
COR_FUNDO_DEEP = "#030712"
COR_CARD_BG = "#060e1d"
COR_CARD_BORDER = "#0f2c4f"
COR_CYAN_GLOW = "#00f5ff"
COR_CYAN_DIM = "#04808c"
COR_BLUE_ELECTRIC = "#0066ff"
COR_GREEN_CYBER = "#00ff88"
COR_GOLD_CYBER = "#ffb700"
COR_PURPLE_CYBER = "#b026ff"
COR_TEXT_BRIGHT = "#e6f9ff"
COR_TEXT_MUTED = "#4d738f"


class CyberHUDCanvasRenderer:
    """Motor Gráfico Vetorial de Alta Estética Holográfica / Jarvis com dimensionamento adaptativo."""

    def __init__(self, canvas: Canvas, largura: int = 900, altura: int = 320, modo_compacto: bool = False):
        self.canvas = canvas
        self.largura = largura
        self.altura = altura
        self.modo_compacto = modo_compacto

        self.estado = "STANDBY"  # STANDBY, OUVINDO, PENSANDO, FALANDO
        self.angulo_rotacao = 0.0
        self.fase_onda = 0.0
        self.texto_usuario = "Aguardando chamado por voz ('Olá Tiger' ou 'Jarvis')..."
        self.texto_resposta = "TIGER 2.0 // Jarvis Neural Engine online e monitorando o mercado."
        self.ativo_smc = "MESU6"
        self.regime_smc = "Aguardando Leitura"
        self.score_confluencia = "Score: —"
        self.confluencias_txt = "Mapeando zonas SMC"
        self.orderflow_txt = "Delta: Mapeando Fluxo"
        self.provedor_ia = "OpenRouter"
        self.modelo_ia = "Claude 3.5 Sonnet"
        self.latencia_ia = "210ms (Rápida)"
        self.wake_word = "'Olá Tiger' / 'Jarvis'"

    def atualizar_dimensoes(self, w: int, h: int):
        self.largura = max(400, w)
        self.altura = max(200, h)

    def atualizar_telemetria(self, ativo: str = "", regime: str = "", score: str = "",
                             confluencias: str = "", orderflow: str = "",
                             provedor: str = "", modelo: str = "", latencia: str = ""):
        if ativo:
            self.ativo_smc = str(ativo)
        if regime:
            self.regime_smc = str(regime)
        if score:
            self.score_confluencia = str(score)
        if confluencias:
            self.confluencias_txt = str(confluencias)
        if orderflow:
            self.orderflow_txt = str(orderflow)
        if provedor:
            self.provedor_ia = str(provedor)
        if modelo:
            self.modelo_ia = str(modelo)
        if latencia:
            self.latencia_ia = str(latencia)

    def atualizar_estado(self, estado: str, texto_usuario: str = "", texto_resposta: str = ""):
        self.estado = estado
        if texto_usuario:
            self.texto_usuario = texto_usuario
        if texto_resposta:
            self.texto_resposta = texto_resposta

    def desenhar(self):
        self.canvas.delete("all")
        w, h = self.largura, self.altura
        cx, cy = w // 2, h // 2 - (15 if h > 260 and not self.modo_compacto else 0)

        # -------------------------------------------------------------
        # 1. Background Grid & Efeitos de Profundidade
        # -------------------------------------------------------------
        # Grade quadriculada sutil
        grid_step = 35
        for x in range(0, w, grid_step):
            self.canvas.create_line(x, 0, x, h, fill="#050d1a", width=1)
        for y in range(0, h, grid_step):
            self.canvas.create_line(0, y, w, y, fill="#050d1a", width=1)

        # Moldura Externa com Cantos Chanfrados Futuristas
        b = 6
        self.canvas.create_polygon(
            b + 18, b,
            w - b - 18, b,
            w - b, b + 18,
            w - b, h - b - 18,
            w - b - 18, h - b,
            b + 18, h - b,
            b, h - b - 18,
            b, b + 18,
            fill="", outline=COR_CARD_BORDER, width=1
        )

        # Detalhes e Acentos Neon nos Cantos
        c_len = 28
        # Canto Sup. Esq.
        self.canvas.create_line(b, b + 18, b + 18, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(b + 18, b, b + 18 + c_len, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(b, b + 18, b, b + 18 + c_len, fill=COR_CYAN_GLOW, width=2)
        # Canto Sup. Dir.
        self.canvas.create_line(w - b, b + 18, w - b - 18, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(w - b - 18, b, w - b - 18 - c_len, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(w - b, b + 18, w - b, b + 18 + c_len, fill=COR_CYAN_GLOW, width=2)

        # Barra Superior de Status HUD
        self.canvas.create_text(24, 20, text="◈ TIGER 2.0 // JARVIS HOLOGRAPHIC COCKPIT", anchor="w", font=("Courier", 11, "bold"), fill=COR_CYAN_GLOW)
        cor_st = COR_GREEN_CYBER if self.estado == "OUVINDO" else (COR_GOLD_CYBER if self.estado == "PENSANDO" else (COR_CYAN_GLOW if self.estado == "FALANDO" else COR_BLUE_ELECTRIC))
        self.canvas.create_text(w // 2, 20, text=f"SYSTEM STATUS: ⟪ {self.estado} ⟫", font=("Courier", 12, "bold"), fill=cor_st)
        self.canvas.create_text(w - 24, 20, text="100% OPENROUTER CLOUD", anchor="e", font=("Courier", 9, "bold"), fill=COR_TEXT_MUTED)

        # -------------------------------------------------------------
        # 2. Orbe Central Reator Holográfico Imponente (Jarvis Reactor)
        # -------------------------------------------------------------
        # Dimensionamento adaptativo: cresce proporcionalmente com o tamanho do canvas!
        raio_base = min(max(h * 0.28, 55), 115) + math.sin(self.fase_onda) * (10 if self.estado in ("OUVINDO", "FALANDO") else 3.5)

        # Halo Glow Radiante Externo
        for glow_r, glow_col in [
            (raio_base + 45, "#020c18"),
            (raio_base + 32, "#03172c"),
            (raio_base + 20, "#062747"),
            (raio_base + 10, "#0a3a69")
        ]:
            self.canvas.create_oval(cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r, outline=glow_col, width=2)

        # Anel 1: Anel de Radar Externo com 36 marcas angulares
        self.canvas.create_oval(cx - raio_base, cy - raio_base, cx + raio_base, cy + raio_base, outline=COR_CYAN_DIM, width=1)
        for i in range(36):
            ang = self.angulo_rotacao + (i * (math.pi / 18))
            is_cardinal = (i % 9 == 0)
            is_sub = (i % 3 == 0)
            len_tick = 10 if is_cardinal else (6 if is_sub else 3)
            x1 = cx + (raio_base - len_tick) * math.cos(ang)
            y1 = cy + (raio_base - len_tick) * math.sin(ang)
            x2 = cx + (raio_base + len_tick) * math.cos(ang)
            y2 = cy + (raio_base + len_tick) * math.sin(ang)
            self.canvas.create_line(x1, y1, x2, y2, fill=COR_CYAN_GLOW if is_cardinal else (COR_CYAN_DIM if is_sub else "#0b425e"), width=2 if is_cardinal else 1)

        # Anel 2: Triade de Arcos Segurados Giratórios (Efeito Sci-Fi Iron Man)
        r_arco = raio_base * 0.84
        ang_deg = math.degrees(self.angulo_rotacao * 1.2)
        self.canvas.create_arc(cx - r_arco, cy - r_arco, cx + r_arco, cy + r_arco, start=ang_deg, extent=75, style="arc", outline=COR_CYAN_GLOW, width=3)
        self.canvas.create_arc(cx - r_arco, cy - r_arco, cx + r_arco, cy + r_arco, start=ang_deg + 120, extent=75, style="arc", outline=COR_CYAN_GLOW, width=3)
        self.canvas.create_arc(cx - r_arco, cy - r_arco, cx + r_arco, cy + r_arco, start=ang_deg + 240, extent=75, style="arc", outline=COR_CYAN_GLOW, width=3)

        # Anel 3: Contra-rotação Interna em Alta Velocidade
        r_int = raio_base * 0.65
        ang_contra = math.degrees(-self.angulo_rotacao * 1.8)
        self.canvas.create_arc(cx - r_int, cy - r_int, cx + r_int, cy + r_int, start=ang_contra, extent=85, style="arc", outline=cor_st, width=2)
        self.canvas.create_arc(cx - r_int, cy - r_int, cx + r_int, cy + r_int, start=ang_contra + 180, extent=85, style="arc", outline=cor_st, width=2)

        # Anel 4: Partículas Orbitais em Translação
        for p_idx in range(4):
            p_ang = self.angulo_rotacao * 2.2 + (p_idx * (math.pi / 2))
            px_dot = cx + (raio_base * 0.74) * math.cos(p_ang)
            py_dot = cy + (raio_base * 0.74) * math.sin(p_ang)
            self.canvas.create_oval(px_dot - 3, py_dot - 3, px_dot + 3, py_dot + 3, fill=COR_CYAN_GLOW, outline="")

        # Núcleo Reator / Cyber Face
        r_core = raio_base * 0.42
        self.canvas.create_oval(cx - r_core, cy - r_core, cx + r_core, cy + r_core, fill=COR_CARD_BG, outline=cor_st, width=2)

        # Animação Central: Equalizador de Voz ou Olhos Cibernéticos
        if self.estado in ("FALANDO", "OUVINDO"):
            # Equalizador de ondas senoidais múltiplas
            largura_onda = r_core * 1.6
            for onda_offset, col_onda, alpha_amp in [(0, COR_CYAN_GLOW, 1.0), (1.5, COR_BLUE_ELECTRIC, 0.6)]:
                pontos = []
                for px in range(int(cx - largura_onda // 2), int(cx + largura_onda // 2), 3):
                    dist = abs(px - cx) / (largura_onda / 2)
                    amp = (1.0 - dist) * (14 if self.estado == "FALANDO" else 8) * alpha_amp
                    py = cy + math.sin(self.fase_onda * 4.0 + px * 0.25 + onda_offset) * amp
                    pontos.extend([px, py])
                if len(pontos) >= 4:
                    self.canvas.create_line(pontos, fill=col_onda, width=2, smooth=True)
        else:
            # Olhos Cibernéticos Holográficos
            eye_offset = max(6, int(r_core * 0.35))
            eye_r = max(3, int(r_core * 0.18))
            self.canvas.create_oval(cx - eye_offset - eye_r, cy - eye_r - 2, cx - eye_offset + eye_r, cy + eye_r - 2, fill=cor_st, outline="")
            self.canvas.create_oval(cx + eye_offset - eye_r, cy - eye_r - 2, cx + eye_offset + eye_r, cy + eye_r - 2, fill=cor_st, outline="")
            arc_w = eye_offset * 1.5
            self.canvas.create_arc(cx - arc_w, cy + 2, cx + arc_w, cy + max(10, int(r_core * 0.6)), start=200, extent=140, style="arc", outline=cor_st, width=2)

        # -------------------------------------------------------------
        # 3. Painéis Laterais Glassmorphism (SMC Telemetry & IA Engine)
        # -------------------------------------------------------------
        pw = max(180, min(240, int(w * 0.24)))
        
        # Painel Esquerdo (SMC)
        if w > 580:
            px1, py1, px2, py2 = 20, 48, 20 + pw, h - 20 if (h <= 260 or self.modo_compacto) else h - 70
            self.canvas.create_rectangle(px1, py1, px2, py2, fill=COR_CARD_BG, outline=COR_CARD_BORDER, width=1)
            self.canvas.create_text(px1 + 14, py1 + 16, text="⚡ TELEMETRIA SMC", anchor="w", font=("Courier", 10, "bold"), fill=COR_CYAN_GLOW)
            self.canvas.create_line(px1 + 10, py1 + 28, px2 - 10, py1 + 28, fill=COR_CARD_BORDER, width=1)
            self.canvas.create_text(px1 + 14, py1 + 46, text=f"• ATIVO: {self.ativo_smc[:18]}", anchor="w", font=("Arial", 9, "bold"), fill=COR_TEXT_BRIGHT)
            self.canvas.create_text(px1 + 14, py1 + 68, text=f"• REGIME: {self.regime_smc[:20]}", anchor="w", font=("Arial", 9), fill=COR_TEXT_BRIGHT)
            self.canvas.create_text(px1 + 14, py1 + 90, text=f"• {self.score_confluencia[:22]}", anchor="w", font=("Arial", 9, "bold"), fill=COR_GREEN_CYBER)
            if py2 - py1 > 140:
                self.canvas.create_text(px1 + 14, py1 + 114, text="• CONFLUÊNCIAS:", anchor="w", font=("Arial", 8), fill=COR_TEXT_MUTED)
                self.canvas.create_text(px1 + 14, py1 + 132, text=f"  {self.confluencias_txt[:24]}", anchor="w", font=("Arial", 9, "bold"), fill=COR_CYAN_GLOW)

        # Painel Direito (OpenRouter Cloud)
        if w > 580:
            rx1, ry1, rx2, ry2 = w - 20 - pw, 48, w - 20, h - 20 if (h <= 260 or self.modo_compacto) else h - 70
            self.canvas.create_rectangle(rx1, ry1, rx2, ry2, fill=COR_CARD_BG, outline=COR_CARD_BORDER, width=1)
            self.canvas.create_text(rx1 + 14, ry1 + 16, text="🤖 MOTOR IA CLOUD", anchor="w", font=("Courier", 10, "bold"), fill=COR_CYAN_GLOW)
            self.canvas.create_line(rx1 + 10, ry1 + 28, rx2 - 10, ry1 + 28, fill=COR_CARD_BORDER, width=1)
            self.canvas.create_text(rx1 + 14, ry1 + 46, text=f"• PROVEDOR: {self.provedor_ia[:18]}", anchor="w", font=("Arial", 9, "bold"), fill=COR_TEXT_BRIGHT)
            self.canvas.create_text(rx1 + 14, ry1 + 68, text=f"• MODELO: {self.modelo_ia[:18]}", anchor="w", font=("Arial", 9), fill=COR_TEXT_BRIGHT)
            self.canvas.create_text(rx1 + 14, py1 + 90, text=f"• LATÊNCIA: {self.latencia_ia[:18]}", anchor="w", font=("Arial", 9, "bold"), fill=COR_GREEN_CYBER)
            if ry2 - ry1 > 140:
                self.canvas.create_text(rx1 + 14, ry1 + 114, text=f"• {self.orderflow_txt[:24]}", anchor="w", font=("Arial", 8), fill=COR_TEXT_MUTED)
                self.canvas.create_text(rx1 + 14, ry1 + 132, text=f"• WAKE-WORD: {self.wake_word[:22]}", anchor="w", font=("Arial", 9, "bold"), fill=COR_GOLD_CYBER)

        # -------------------------------------------------------------
        # 4. Painel Inferior de Transcrição e Diálogo Flutuante
        # -------------------------------------------------------------
        if h > 260 and not self.modo_compacto:
            ty1, ty2 = h - 64, h - 14
            self.canvas.create_rectangle(20, ty1, w - 20, ty2, fill=COR_CARD_BG, outline=COR_CYAN_DIM, width=1)
            self.canvas.create_text(32, ty1 + 18, text=f"🎤 VOCÊ: {self.texto_usuario[:85]}", anchor="w", font=("Arial", 10, "italic"), fill="#90caf9")
            self.canvas.create_text(32, ty1 + 38, text=f"🐯 TIGER: {self.texto_resposta[:100]}", anchor="w", font=("Arial", 10, "bold"), fill=COR_TEXT_BRIGHT)


class TigerHUDEmbeddedFrame(tk.Frame):
    """Componente visual holográfico embutido diretamente na aba TIGER do SMC Quant Pro."""

    def __init__(self, master, largura: int = 900, altura: int = 300, **kwargs):
        super().__init__(master, bg=COR_FUNDO_DEEP, **kwargs)
        self.largura = largura
        self.altura = altura

        self.canvas = Canvas(
            self,
            width=self.largura,
            height=self.altura,
            bg=COR_FUNDO_DEEP,
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        self.renderer = CyberHUDCanvasRenderer(self.canvas, self.largura, self.altura, modo_compacto=False)
        self._animando = True
        self.bind("<Configure>", self._ao_redimensionar)
        self._loop_animacao()

    def _ao_redimensionar(self, event):
        if event.width > 50 and event.height > 50:
            self.largura = event.width
            self.altura = event.height
            self.renderer.atualizar_dimensoes(event.width, event.height)

    def redimensionar(self, nova_altura: int):
        self.altura = nova_altura
        self.canvas.configure(height=nova_altura)
        self.renderer.atualizar_dimensoes(self.largura, nova_altura)

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

        self.largura = 840
        self.altura = 440
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
            highlightbackground=COR_CYAN_DIM,
            bd=0
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
