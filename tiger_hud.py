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

# OS TEMAS DO ORBE VIVEM FORA DAQUI, de proposito. Ver orbe_temas.py: trocar
# o estilo do Orbe nao pode exigir editar o arquivo que desenha a telemetria
# da conta. Se o modulo faltar na instalacao, o HUD degrada para o rosto
# classico em vez de nao abrir — painel que nao abre esconde posicao aberta.
try:
    import orbe_temas
except Exception:
    orbe_temas = None

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
    """Motor Gráfico Holográfico Sci-Fi de Alta Fidelidade (TIGER Neural Cockpit)."""

    def __init__(self, canvas: Canvas, largura: int = 900, altura: int = 320, modo_compacto: bool = False):
        self.canvas = canvas
        self.largura = largura
        self.altura = altura
        self.modo_compacto = modo_compacto

        self.estado = "STANDBY"  # STANDBY, OUVINDO, PENSANDO, FALANDO, ACAO
        # Tema visual do Orbe (ver orbe_temas.py). Trocavel em tempo de
        # execucao por `definir_tema` — sem tocar em nada do motor.
        self.tema_orbe = getattr(orbe_temas, "TEMA_PADRAO", "quantum_predator") \
            if orbe_temas else "quantum_predator"
        # Amplitude da fala AGORA (0.0 a 1.0), quando a camada de voz mede.
        # None = nao medi — e a boca cai numa oscilacao plausivel em vez de
        # fingir uma medida que nao existe.
        self.envelope_voz = None
        # CAMADA 0: a captura do grafico como fundo do cluster, e o
        # interruptor que a desliga. CAMADA 1: o PNG que pode substituir o
        # rosto vetorial. As referencias ficam AQUI porque o Tkinter nao
        # segura imagem sozinho — sem isso o coletor leva e some sem erro.
        self.imagem_fundo = None
        self.contexto_de_fundo = True
        self.imagem_rosto = None
        self.angulo_rotacao = 0.0
        self.angulo_radar = 0.0
        self.fase_onda = 0.0
        self.texto_usuario = "Aguardando chamado por voz ('Olá Tiger' ou 'Jarvis')..."
        self.texto_resposta = "TIGER 2.0 // Jarvis Neural Engine online e monitorando o mercado."
        # OS VALORES INICIAIS DESTE PAINEL ERAM UMA MESA INTEIRA DE MENTIRA.
        #
        # Enquanto nenhuma análise tivesse rodado, o HUD abria afirmando
        # MESU6 a 7698,75, regime de alta, score 82% aprovado, três
        # confluências, CVD +1.420 comprador forte e CDP ao vivo — tudo isso
        # sem uma única leitura de tela ter acontecido. E o +1.420 é
        # exatamente o número que apareceu no pregão de 22/08 e que a TIGER
        # citou de volta ao trader como se fosse fluxo medido.
        #
        # Painel de instrumento não enfeita: ou mostra medição, ou mostra
        # travessão. Um mostrador parado no valor bonito é pior que um
        # mostrador vazio, porque o vazio ninguém confunde com leitura.
        self.ativo_smc = "— (aguardando primeira leitura)"
        self.regime_smc = "— (sem leitura)"
        self.score_confluencia = "Score: — (sem leitura)"
        self.confluencias_txt = "— (nenhuma confluência lida ainda)"
        self.orderflow_txt = "Order Flow: — (sem fluxo ao vivo)"
        self.cvd_valor = 0.0
        self.cdp_status_txt = "⚪ CDP Tradovate: não verificado"
        self.posicao_txt = "— (posição não verificada)"
        self.provedor_ia = "— (não configurado)"
        self.modelo_ia = "— (não configurado)"
        self.latencia_ia = "— (sem medição)"
        self.trailing_txt = "Auto Trail: — (nenhuma ordem enviada)"
        self.wake_word = "'Olá Tiger' / 'Jarvis'"
        self.maos_livres_ativa = False
        self.on_falar_click = None
        self.on_toggle_maos_livres = None
        self._cx = 450
        self._cy = 160
        self._raio_base = 90
        self._btn_falar_bounds = None
        self._badge_ml_bounds = None
        # AQUI HAVIA TRÊS LINHAS DE LOG FALSAS, e uma delas era a pior frase
        # que este programa poderia exibir sem ser verdade:
        #
        #     ("09:35", "ORDEM", "BUY MESU6 6 ctr @ 7690.0 enviada")
        #
        # O painel abria afirmando que uma ordem de seis contratos tinha ido
        # para a corretora. Nenhuma tinha. As outras duas diziam que o stop
        # móvel estava armado e que o delta confirmava fluxo comprador — o
        # mesmo +1.420 de sempre.
        #
        # Log é registro do que aconteceu. Um log de exemplo é um registro do
        # que NÃO aconteceu, e num programa que manda ordem sozinho isso não
        # é enfeite de interface: é a diferença entre o trader achar que está
        # posicionado e estar.
        self.logs_recentes = []

    def tratar_clique(self, x: int, y: int):
        """Processa clique do mouse nas áreas interativas do HUD (Orbe, Botão de Voz e Mãos Livres)."""
        # 1. Clique no Badge Mãos Livres
        if self._badge_ml_bounds:
            bx1, by1, bx2, by2 = self._badge_ml_bounds
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                if callable(self.on_toggle_maos_livres):
                    self.on_toggle_maos_livres()
                return

        # 2. Clique no Botão Central ou no Orbe
        no_botao = False
        if self._btn_falar_bounds:
            bx1, by1, bx2, by2 = self._btn_falar_bounds
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                no_botao = True

        dist_centro_sq = (x - self._cx) ** 2 + (y - self._cy) ** 2
        no_orbe = dist_centro_sq <= (self._raio_base * 1.15) ** 2

        if no_botao or no_orbe:
            if callable(self.on_falar_click):
                self.on_falar_click()

    def atualizar_dimensoes(self, w: int, h: int):
        self.largura = max(400, w)
        self.altura = max(200, h)

    def atualizar_telemetria(self, ativo: str = "", regime: str = "", score: str = "",
                             confluencias: str = "", orderflow: str = "",
                             provedor: str = "", modelo: str = "", latencia: str = "",
                             cdp_status: str = "", posicao: str = "", trailing: str = "",
                             logs: list = None):
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
        if cdp_status:
            self.cdp_status_txt = str(cdp_status)
        if posicao:
            self.posicao_txt = str(posicao)
        if trailing:
            self.trailing_txt = str(trailing)
        if logs is not None:
            self.logs_recentes = list(logs)

    # -----------------------------------------------------------------
    #  PONTE COM O MÓDULO DE TEMAS
    # -----------------------------------------------------------------
    #  Os três métodos abaixo são a ÚNICA porta entre o laço de desenho e
    #  `orbe_temas.py`. Sem o módulo, o HUD continua abrindo — degradado, mas
    #  abrindo. Painel que não abre esconde posição aberta, e esconder posição
    #  é pior que mostrar um rosto feio.

    def _tema(self):
        """O tema escolhido, ou None se o módulo de temas não veio."""
        if orbe_temas is None:
            return None
        return orbe_temas.tema(getattr(self, "tema_orbe", None))

    def _cores_estado(self):
        """A paleta do estado atual (parado / ouvindo / calculando / falando /
        ação confirmada). Sem o módulo, devolve o cyan de sempre."""
        if orbe_temas is None:
            return {"principal": COR_CYAN_GLOW, "brilho": COR_TEXT_BRIGHT,
                    "pulso": 1.0, "rotulo": str(self.estado)}
        return orbe_temas.cores_do_estado(self.estado)

    def _abertura_boca(self):
        """Quanto a boca está aberta agora — 0.0 a 1.0.

        `envelope_voz` é a amplitude da fala, quando a camada de voz consegue
        medir; None significa "não medi" e a boca cai numa oscilação de fala
        plausível — que SÓ roda com o estado FALANDO. Boca calada não se mexe."""
        if orbe_temas is None:
            return 0.0
        return orbe_temas.abertura_da_boca(
            self.estado, getattr(self, "envelope_voz", None), self.fase_onda)

    def _barras_voz(self, n=24):
        """As alturas das barras do equalizador."""
        if orbe_temas is None:
            return [0.06] * n
        return orbe_temas.barras_do_equalizador(
            self.estado, getattr(self, "envelope_voz", None), self.fase_onda, n=n)

    def _desenhar_fundo_de_contexto(self, cx, cy, largura_centro, h):
        """CAMADA 0 — a ultima captura do grafico, como FUNDO do cluster.

        Nao e um feed ao vivo paralelo: e a MESMA imagem que o motor analisou
        no ultimo ciclo. Fica atras de tudo de proposito — contexto e o que
        fica atras, informacao e o que fica na frente.

        DESLIGAVEL. `contexto_de_fundo` False deixa o cluster escuro, so com o
        rosto e a telemetria. Num pregao lateral, fundo demais atrapalha ler o
        numero — e quem decide isso e ele, nao eu.
        """
        if not getattr(self, "contexto_de_fundo", True):
            return
        img = getattr(self, "imagem_fundo", None)
        if img is None:
            return
        try:
            self.canvas.create_image(cx, cy, image=img, anchor="center")
        except Exception:
            return
        # VEU ESCURO POR CIMA. Sem ele, o grafico compete com o rosto e com o
        # equalizador em brilho, e o cockpit vira sopa visual. O Canvas do
        # Tkinter nao tem transparencia real por pixel, entao o veu e feito
        # com um retangulo do stipple — que e o jeito que existe aqui.
        try:
            meia_l = int(largura_centro * 0.5)
            self.canvas.create_rectangle(
                cx - meia_l, cy - h // 2, cx + meia_l, cy + h // 2,
                fill=COR_FUNDO_DEEP, outline="", stipple="gray50")
        except Exception:
            pass

    def definir_fundo_de_contexto(self, imagem_tk, ligado=True):
        """Recebe a captura ja convertida para Tk e diz se ela deve aparecer.

        A referencia fica GUARDADA aqui: o Tkinter nao segura imagem sozinho,
        e sem alguem guardando o coletor de lixo leva e o fundo some sem erro
        nenhum — o tipo de defeito que parece 'o recurso nao funciona'."""
        self.imagem_fundo = imagem_tk
        self.contexto_de_fundo = bool(ligado)

    def definir_rosto_de_imagem(self, imagem_tk):
        """O PNG que substitui o rosto vetorial, quando o tema pede.

        `None` volta ao rosto desenhado. Nao ha erro nesse caminho: se a
        imagem nao carregou, o Orbe continua com o rosto de linha, que e feio
        perto do fotorrealista mas infinitamente melhor que painel vazio."""
        self.imagem_rosto = imagem_tk

    def definir_tema(self, nome):
        """Troca o tema do Orbe e redesenha. É tudo o que a interface precisa
        chamar — nenhum outro arquivo sabe que temas existem."""
        self.tema_orbe = str(nome or "")
        try:
            self.desenhar()
        except Exception:
            pass

    def atualizar_estado(self, estado: str, texto_usuario: str = "", texto_resposta: str = ""):
        self.estado = estado
        if texto_usuario:
            self.texto_usuario = texto_usuario
        if texto_resposta:
            self.texto_resposta = texto_resposta

    def _desenhar_card(self, x1, y1, x2, y2, titulo, icone="⚡", badge="🟢 ATIVO", cor_neon=COR_CYAN_GLOW):
        """Desenha um card Sci-Fi translúcido com chanfros neon nos cantos e tipografia nítida."""
        # Fundo
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=COR_CARD_BG, outline=COR_CARD_BORDER, width=1)
        # Cantos neon chanfrados
        cl = 12
        self.canvas.create_line(x1, y1, x1 + cl, y1, fill=cor_neon, width=2)
        self.canvas.create_line(x1, y1, x1, y1 + cl, fill=cor_neon, width=2)
        self.canvas.create_line(x2, y1, x2 - cl, y1, fill=cor_neon, width=2)
        self.canvas.create_line(x2, y1, x2, y1 + cl, fill=cor_neon, width=2)
        self.canvas.create_line(x1, y2, x1 + cl, y2, fill=cor_neon, width=2)
        self.canvas.create_line(x1, y2, x1, y2 - cl, fill=cor_neon, width=2)
        self.canvas.create_line(x2, y2, x2 - cl, y2, fill=cor_neon, width=2)
        self.canvas.create_line(x2, y2, x2, y2 - cl, fill=cor_neon, width=2)

        # Cabeçalho com fonte grande e nítida
        self.canvas.create_text(x1 + 14, y1 + 17, text=f"{icone} {titulo}", anchor="w",
                                font=("Arial", 11, "bold"), fill=cor_neon)
        if badge:
            bw = len(badge) * 7 + 16
            bx2 = x2 - 12
            bx1 = bx2 - bw
            self.canvas.create_rectangle(bx1, y1 + 6, bx2, y1 + 27, fill="#041a2f",
                                         outline=cor_neon, width=1)
            self.canvas.create_text((bx1 + bx2) // 2, y1 + 16, text=badge,
                                    font=("Arial", 9, "bold"), fill=cor_neon)
        self.canvas.create_line(x1 + 10, y1 + 32, x2 - 10, y1 + 32, fill=COR_CARD_BORDER, width=1)

    def _desenhar_mini_item(self, x1, y, x2, tag, valor, cor_val=COR_TEXT_BRIGHT, h_item=28):
        """Mini-card estilizado de alta legibilidade para cada indicador / telemetria."""
        self.canvas.create_rectangle(x1 + 8, y, x2 - 8, y + h_item, fill="#030c18",
                                     outline="#0a223c", width=1)
        self.canvas.create_text(x1 + 14, y + h_item // 2, text=f"[{tag}]", anchor="w",
                                font=("Arial", 9, "bold"), fill=COR_CYAN_DIM)
        txt_v = str(valor)
        # Mais caracteres visíveis com espaçamento confortável
        largura_disp = (x2 - 8) - (x1 + 14 + len(tag) * 8 + 14)
        max_c = max(18, int(largura_disp / 7.5))
        self.canvas.create_text(x1 + 14 + len(tag) * 8 + 10, y + h_item // 2,
                                text=txt_v[:max_c], anchor="w",
                                font=("Arial", 11, "bold"), fill=cor_val)

    def desenhar(self):
        self.canvas.delete("all")
        w, h = self.largura, self.altura
        cx, cy = w // 2, h // 2 - 8

        # -------------------------------------------------------------
        # 1. Background Grid & Grade Cibernética
        # -------------------------------------------------------------
        grid_step = 35
        for x in range(0, w, grid_step):
            self.canvas.create_line(x, 0, x, h, fill="#040a14", width=1)
        for y in range(0, h, grid_step):
            self.canvas.create_line(0, y, w, y, fill="#040a14", width=1)

        # Moldura Superior / Externa do Cockpit
        b = 6
        self.canvas.create_polygon(
            b + 18, b, w - b - 18, b, w - b, b + 18,
            w - b, h - b - 18, w - b - 18, h - b,
            b + 18, h - b, b, h - b - 18, b, b + 18,
            fill="", outline=COR_CARD_BORDER, width=1
        )

        # Acentos Neon nos Cantos
        c_len = 24
        self.canvas.create_line(b, b + 18, b + 18, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(b + 18, b, b + 18 + c_len, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(w - b, b + 18, w - b - 18, b, fill=COR_CYAN_GLOW, width=2)
        self.canvas.create_line(w - b - 18, b, w - b - 18 - c_len, b, fill=COR_CYAN_GLOW, width=2)

        # Barra Superior de Status HUD (Cockpit Header)
        self.canvas.create_text(24, 20, text="◈ NÚCLEO NEURAL TIGER • HUD COCKPIT", anchor="w",
                                font=("Courier", 11, "bold"), fill=COR_CYAN_GLOW)
        cor_st = COR_GREEN_CYBER if self.estado == "OUVINDO" else (
            COR_GOLD_CYBER if self.estado == "PENSANDO" else (
                COR_CYAN_GLOW if self.estado == "FALANDO" else COR_BLUE_ELECTRIC))

        # Badge Central de Status
        self.canvas.create_text(w // 2, 20, text=f"SYSTEM STATUS: ⟪ {self.estado} ⟫",
                                font=("Courier", 11, "bold"), fill=cor_st)

        # Badge Mãos Livres no Cabeçalho (Clicável para ativar/desativar microfone aberto)
        ml_txt = "🎙️ MÃOS LIVRES: ATIVADA" if self.maos_livres_ativa else "🎙️ MÃOS LIVRES: DESATIVADA"
        ml_col = COR_GREEN_CYBER if self.maos_livres_ativa else COR_TEXT_MUTED
        ml_w = len(ml_txt) * 6 + 18
        ml_x2 = w - 24
        ml_x1 = ml_x2 - ml_w
        self.canvas.create_rectangle(ml_x1, 9, ml_x2, 29, fill="#041a2f", outline=ml_col, width=1)
        self.canvas.create_text((ml_x1 + ml_x2) // 2, 19, text=ml_txt,
                                font=("Courier", 8, "bold"), fill=ml_col)
        self._badge_ml_bounds = (ml_x1, 9, ml_x2, 29)

        # -------------------------------------------------------------
        # 2. Dimensões dos Painéis e Dimensionamento Imponente do Orbe
        # -------------------------------------------------------------
        pw = max(290, min(420, int(w * 0.30))) if w > 600 else 0
        largura_centro = w - 2 * pw if pw > 0 else w
        raio_base = min(max(h * 0.34, 75), int(largura_centro * 0.42), 170) + math.sin(self.fase_onda) * 2.0

        # -------------------------------------------------------------
        # CAMADA 0 — O GRAFICO COMO FUNDO DO CLUSTER
        # -------------------------------------------------------------
        # Antes isto era um quadro FLUTUANTE no canto inferior-direito, e
        # ficou exatamente como ele descreveu: solto, desalinhado, brigando
        # com o equalizador por atencao. Um retangulo de 210px no meio de um
        # cockpit nao le como "contexto", le como erro de alinhamento.
        #
        # Agora o grafico e o FUNDO: ocupa o espaco central inteiro, atras do
        # Orbe e atras de tudo. Contexto e o que fica atras; informacao e o
        # que fica na frente. As camadas 1 (rosto) e 2 (telemetria, logs,
        # equalizador) sao desenhadas DEPOIS, entao ficam por cima — no
        # Canvas do Tkinter a ordem de desenho E a ordem das camadas.
        self._desenhar_fundo_de_contexto(cx, cy, largura_centro, h)

        pitch = 0.38  # ~22 graus de inclinação tridimensional

        # -------------------------------------------------------------
        # 3. Radar de Monitoramento (Sobreposição de Escaneamento Rotativo)
        # -------------------------------------------------------------
        r_radar = raio_base * 1.65
        # Anéis concêntricos de radar
        for mult_r in [0.5, 0.85, 1.25, 1.65]:
            self.canvas.create_oval(cx - raio_base * mult_r, cy - raio_base * mult_r,
                                    cx + raio_base * mult_r, cy + raio_base * mult_r,
                                    outline="#06223b", width=1)

        # Feixe de Escaneamento do Radar (Cone Rotativo)
        ang_rad_deg = math.degrees(self.angulo_radar)
        self.canvas.create_arc(cx - r_radar, cy - r_radar, cx + r_radar, cy + r_radar,
                               start=ang_rad_deg, extent=42, fill="#032a3d",
                               outline=COR_CYAN_GLOW, width=1.5)
        # Linha de ponta do radar
        rad_ponta_x = cx + r_radar * math.cos(self.angulo_radar + math.radians(42))
        rad_ponta_y = cy - r_radar * math.sin(self.angulo_radar + math.radians(42))
        self.canvas.create_line(cx, cy, rad_ponta_x, rad_ponta_y, fill=COR_CYAN_GLOW, width=2)

        # Marcadores de Alvo Flickering no Radar
        for i_blip, (dist_b, ang_off) in enumerate([(0.7, 1.2), (1.1, 3.4), (1.4, 4.8)]):
            blip_ang = ang_off
            bx = cx + raio_base * dist_b * math.cos(blip_ang)
            by = cy + raio_base * dist_b * math.sin(blip_ang)
            if abs((self.angulo_radar % (2 * math.pi)) - (blip_ang % (2 * math.pi))) < 0.8:
                self.canvas.create_oval(bx - 3, by - 3, bx + 3, by + 3, fill=COR_GREEN_CYBER, outline="")
                self.canvas.create_oval(bx - 7, by - 7, bx + 7, by + 7, outline=COR_GREEN_CYBER, width=1)

        # -------------------------------------------------------------
        # 4. Conexões Arteriais Luminosas (Data Feeds Laterais para o Orbe)
        # -------------------------------------------------------------
        item_y_esq = 48 + 42
        item_h_esq = max(24, min(32, (h - 20 - item_y_esq - 20) // 5))
        item_y_dir = 48 + 38
        item_h_dir = max(20, min(24, (max(110, (h - 68) // 3) - item_y_dir - 10) // 3))

        if pw > 0 and w > 640:
            # Conexões da Esquerda (SMC Telemetry -> Orbe)
            px2 = 20 + pw
            for idx in range(5):
                start_y = item_y_esq + idx * (item_h_esq + 5) + item_h_esq // 2
                target_y = cy + (idx - 2) * (raio_base * 0.28)
                target_x = cx - raio_base * 0.92
                ctrl_x = (px2 + target_x) // 2
                
                # Linha arterial curva suave
                self.canvas.create_line(px2, start_y, ctrl_x, start_y, ctrl_x, target_y, target_x, target_y,
                                        smooth=True, fill="#073a57", width=1.5)
                # Nó de conexão arterial brilhante
                self.canvas.create_oval(px2 - 2, start_y - 2, px2 + 2, start_y + 2, fill=COR_CYAN_GLOW, outline="")
                self.canvas.create_oval(target_x - 3, target_y - 3, target_x + 3, target_y + 3, fill=COR_CYAN_GLOW, outline="")

                # Pacote de Dados Animado viajando na linha
                prog = ((self.angulo_rotacao * 1.5 + idx * 0.4) % 1.0)
                pulse_x = px2 + (target_x - px2) * prog
                pulse_y = start_y + (target_y - start_y) * prog
                self.canvas.create_oval(pulse_x - 2, pulse_y - 2, pulse_x + 2, pulse_y + 2,
                                        fill=COR_CYAN_GLOW, outline="")

            # Conexões da Direita (IA & Logs -> Orbe)
            rx1 = w - 20 - pw
            for idx in range(5):
                start_y = item_y_dir + idx * 30 + 12
                target_y = cy + (idx - 2) * (raio_base * 0.28)
                target_x = cx + raio_base * 0.92
                ctrl_x = (rx1 + target_x) // 2

                self.canvas.create_line(rx1, start_y, ctrl_x, start_y, ctrl_x, target_y, target_x, target_y,
                                        smooth=True, fill="#073a57", width=1.5)
                self.canvas.create_oval(rx1 - 2, start_y - 2, rx1 + 2, start_y + 2, fill=COR_GOLD_CYBER, outline="")
                self.canvas.create_oval(target_x - 3, target_y - 3, target_x + 3, target_y + 3, fill=COR_GOLD_CYBER, outline="")

                prog = ((self.angulo_rotacao * 1.5 + idx * 0.45) % 1.0)
                pulse_x = rx1 + (target_x - rx1) * prog
                pulse_y = start_y + (target_y - start_y) * prog
                self.canvas.create_oval(pulse_x - 2, pulse_y - 2, pulse_x + 2, pulse_y + 2,
                                        fill=COR_GOLD_CYBER, outline="")

        # -------------------------------------------------------------
        # 5. Orbe Central Reator Holográfico — Globo Geodésico 3D & Cyber Tiger Face
        # -------------------------------------------------------------
        # Halo Glow Radiante Externo
        for glow_r, glow_col in [
            (raio_base + 45, "#020c18"),
            (raio_base + 30, "#03172c"),
            (raio_base + 16, "#062747"),
            (raio_base + 6, "#0a3a69")
        ]:
            self.canvas.create_oval(cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r,
                                    outline=glow_col, width=1)

        # Projeção Tridimensional da Esfera Geodésica (Wireframe Globe)
        latitudes = [-60, -35, 0, 35, 60]
        longitudes = [k * 30 for k in range(12)]
        rot = self.angulo_rotacao

        # Desenho das Linhas de Latitude 3D
        for lat_deg in latitudes:
            lat_rad = math.radians(lat_deg)
            r_lat = raio_base * math.cos(lat_rad)
            z_lat = raio_base * math.sin(lat_rad)
            pontos_frente = []
            pontos_tras = []

            for st_deg in range(0, 365, 10):
                th_rad = math.radians(st_deg) + rot
                x_3d = r_lat * math.sin(th_rad)
                y_3d = r_lat * math.cos(th_rad)
                y_proj = y_3d * math.cos(pitch) - z_lat * math.sin(pitch)
                z_proj = y_3d * math.sin(pitch) + z_lat * math.cos(pitch)
                px = cx + x_3d
                py = cy - y_proj

                if z_proj >= 0:
                    pontos_frente.append((px, py))
                else:
                    pontos_tras.append((px, py))

            if len(pontos_frente) >= 2:
                for idx in range(len(pontos_frente) - 1):
                    self.canvas.create_line(pontos_frente[idx][0], pontos_frente[idx][1],
                                            pontos_frente[idx + 1][0], pontos_frente[idx + 1][1],
                                            fill=COR_CYAN_GLOW if lat_deg == 0 else COR_CYAN_DIM,
                                            width=1.5 if lat_deg == 0 else 1)
            if len(pontos_tras) >= 2:
                for idx in range(len(pontos_tras) - 1):
                    self.canvas.create_line(pontos_tras[idx][0], pontos_tras[idx][1],
                                            pontos_tras[idx + 1][0], pontos_tras[idx + 1][1],
                                            fill="#043242", width=1)

        # Desenho dos Meridianos 3D com Vértices Quânticos
        for lon_deg in longitudes:
            th_rad = math.radians(lon_deg) + rot
            pontos_merid = []
            for lat_step in range(-80, 85, 15):
                lat_rad = math.radians(lat_step)
                r_lat = raio_base * math.cos(lat_rad)
                z_lat = raio_base * math.sin(lat_rad)
                x_3d = r_lat * math.sin(th_rad)
                y_3d = r_lat * math.cos(th_rad)
                y_proj = y_3d * math.cos(pitch) - z_lat * math.sin(pitch)
                z_proj = y_3d * math.sin(pitch) + z_lat * math.cos(pitch)
                px = cx + x_3d
                py = cy - y_proj
                pontos_merid.append((px, py, z_proj))

            for idx in range(len(pontos_merid) - 1):
                p1 = pontos_merid[idx]
                p2 = pontos_merid[idx + 1]
                cor_l = COR_CYAN_GLOW if (p1[2] + p2[2]) / 2 >= 0 else "#032938"
                self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=cor_l, width=1)
                if p1[2] > 20 and idx % 2 == 0:
                    self.canvas.create_oval(p1[0] - 2, p1[1] - 2, p1[0] + 2, p1[1] + 2,
                                            fill=COR_CYAN_GLOW, outline="")

        # -------------------------------------------------------------
        # O ROSTO VEM DO TEMA — ver orbe_temas.py
        # -------------------------------------------------------------
        # Antes, os ~100 comandos de desenho do rosto estavam escritos aqui,
        # no meio do laco que tambem desenha radar, telemetria e logs. Trocar
        # de estilo exigia editar o arquivo que mostra numero de conta.
        # Agora o tema entrega a funcao do rosto, e este laco so a chama.
        tf_scale = max(28.0, raio_base * 0.46)
        _cor_est = self._cores_estado()
        _abertura = self._abertura_boca()
        _t = self._tema()
        # CAMADA 1 — o rosto. A IMAGEM tem preferencia quando existe; o rosto
        # vetorial e a queda segura. Uma imagem que nao carregou nao pode
        # deixar o Orbe sem cara nenhuma.
        _usou_imagem = False
        _img_rosto = getattr(self, "imagem_rosto", None)
        if _img_rosto is not None and orbe_temas is not None:
            try:
                _usou_imagem = orbe_temas.desenhar_rosto_de_imagem(
                    self.canvas, cx, cy, tf_scale, _img_rosto)
            except Exception:
                _usou_imagem = False
        if not _usou_imagem and _t is not None:
            try:
                _t["rosto"](self.canvas, cx, cy, tf_scale, _cor_est,
                            self.fase_onda, _abertura)
            except Exception:
                # Um tema quebrado nao pode derrubar o painel inteiro.
                pass

        # Anel Orbital Maior com Coordenadas Sci-Fi
        r_orb_x = raio_base * 1.54
        r_orb_y = raio_base * 0.64
        self.canvas.create_oval(cx - r_orb_x, cy - r_orb_y, cx + r_orb_x, cy + r_orb_y,
                                outline=COR_CYAN_DIM, width=1)

        # Ticks e Marcadores Angulares no Anel Orbital
        for i in range(24):
            ang_t = i * (math.pi / 12) + (rot * 0.5)
            tx = cx + r_orb_x * math.cos(ang_t)
            ty = cy + r_orb_y * math.sin(ang_t)
            is_card = (i % 6 == 0)
            len_t = 6 if is_card else 3
            self.canvas.create_line(tx, ty - len_t, tx, ty + len_t,
                                    fill=COR_CYAN_GLOW if is_card else COR_CYAN_DIM, width=1)

        # Rótulos de Coordenadas Orbitais
        self.canvas.create_text(cx, cy - r_orb_y - 12, text="000° // SYS.CORE",
                                font=("Courier", 8, "bold"), fill=COR_CYAN_DIM)
        self.canvas.create_text(cx + r_orb_x + 18, cy, text="090°",
                                font=("Courier", 8, "bold"), fill=COR_CYAN_DIM)
        self.canvas.create_text(cx, cy + r_orb_y + 12, text="180° // QUANTUM.LOCK",
                                font=("Courier", 8, "bold"), fill=COR_CYAN_DIM)
        self.canvas.create_text(cx - r_orb_x - 18, cy, text="270°",
                                font=("Courier", 8, "bold"), fill=COR_CYAN_DIM)

        # Partículas Quânticas em Órbita
        for p_idx in range(4):
            p_ang = rot * 1.6 + (p_idx * (math.pi / 2))
            px_dot = cx + r_orb_x * math.cos(p_ang)
            py_dot = cy + r_orb_y * math.sin(p_ang)
            self.canvas.create_oval(px_dot - 3, py_dot - 3, px_dot + 3, py_dot + 3,
                                    fill=COR_CYAN_GLOW, outline="")

        # -------------------------------------------------------------
        # 6. Equalizador de Voz em Onda Fluida & Controles Inferiores
        # -------------------------------------------------------------
        if h > 240:
            # EQUALIZADOR DE VOZ — barras, e nao mais uma senoide unica.
            # A senoide antiga oscilava igual em silencio e em fala; so mudava
            # de amplitude. Barras leem como VOZ para o olho, e a linha de
            # repouso baixa (nunca zero) diz "quieta", nao "desligada".
            largura_onda = min(260, int(raio_base * 1.7))
            onda_y = cy + r_orb_y + 26
            _barras = self._barras_voz(n=24)
            _cor_v = self._cores_estado()
            n_b = max(1, len(_barras))
            passo_b = max(3, largura_onda // n_b)
            x0_b = cx - (passo_b * n_b) // 2
            for i_b, alt_rel in enumerate(_barras):
                bx = x0_b + i_b * passo_b
                alt = 3 + alt_rel * 22
                self.canvas.create_rectangle(
                    bx, onda_y - alt, bx + max(2, passo_b - 2), onda_y + alt,
                    fill=_cor_v["principal"] if alt_rel > 0.35 else _cor_v["brilho"],
                    outline="")
            self.canvas.create_line(x0_b, onda_y, x0_b + passo_b * n_b, onda_y,
                                    fill=COR_CARD_BORDER, width=1)

            # Botão de Ação Central
            btn_w, btn_h = 190, 28
            btn_y = onda_y + 16
            self.canvas.create_rectangle(cx - btn_w // 2, btn_y, cx + btn_w // 2, btn_y + btn_h,
                                         fill="#041a2f", outline=COR_CYAN_GLOW, width=1.5)
            btn_txt = "🎙️ FALAR COM A TIGER" if self.estado == "STANDBY" else (
                "🎤 ESCUTANDO..." if self.estado == "OUVINDO" else (
                    "⚙️ CALCULANDO..." if self.estado == "PENSANDO" else (
                        "🟠 ORDEM CONFIRMADA" if str(self.estado).upper() == "ACAO"
                        else "🔊 TIGER FALANDO")))
            self.canvas.create_text(cx, btn_y + btn_h // 2, text=btn_txt,
                                    font=("Arial", 10, "bold"),
                                    fill=self._cores_estado()["principal"])

            # Registra coordenadas interativas do Orbe e do Botão de Voz
            self._cx = cx
            self._cy = cy
            self._raio_base = raio_base
            self._btn_falar_bounds = (cx - btn_w // 2, btn_y, cx + btn_w // 2, btn_y + btn_h)

            # Legenda de Wake-Words
            self.canvas.create_text(cx, btn_y + btn_h + 14,
                                    text='💡 WAKE-WORDS: "Olá Tiger", "Jarvis", "Tiger..."',
                                    font=("Arial", 9), fill=COR_TEXT_MUTED)

        # -------------------------------------------------------------
        # 7. Painéis Laterais Sci-Fi Glassmorphism (Telemetria & IA)
        # -------------------------------------------------------------
        # Painel Esquerdo: TELEMETRIA SMC & ORDER FLOW
        if w > 600:
            px1, py1, px2, py2 = 20, 48, 20 + pw, h - 16
            self._desenhar_card(px1, py1, px2, py2, "TELEMETRIA SMC & ORDER FLOW",
                                icone="⚡", badge="🟢 ATIVO", cor_neon=COR_CYAN_GLOW)

            item_y = py1 + 42
            item_h = max(26, min(34, (py2 - item_y - 20) // 5))

            self._desenhar_mini_item(px1, item_y, px2, "ATIVO", self.ativo_smc,
                                     "#ffffff", item_h)
            self._desenhar_mini_item(px1, item_y + item_h + 5, px2, "REGIME",
                                     f"{self.regime_smc}", COR_GREEN_CYBER, item_h)
            self._desenhar_mini_item(px1, item_y + (item_h + 5) * 2, px2, "ORDER FLOW",
                                     self.orderflow_txt, COR_CYAN_GLOW, item_h)
            self._desenhar_mini_item(px1, item_y + (item_h + 5) * 3, px2, "CONFLUÊNCIAS",
                                     self.confluencias_txt, "#ffffff", item_h)
            self._desenhar_mini_item(px1, item_y + (item_h + 5) * 4, px2, "POSIÇÃO",
                                     self.posicao_txt, COR_GOLD_CYBER, item_h)

        # Painel Direito: MOTOR IA CLOUD & LOGS EM TEMPO REAL
        if w > 600:
            rx1, ry1, rx2, ry2 = w - 20 - pw, 48, w - 20, h - 16

            # Card Superior (Motor IA & CDP) - Compacto (94px)
            h_sup = 94
            ry_mid1 = ry1 + h_sup
            ry_mid2 = ry1 + h_sup + 8

            self._desenhar_card(rx1, ry1, rx2, ry_mid1, "MOTOR IA CLOUD & CDP",
                                icone="🤖", badge="🟢 ONLINE", cor_neon=COR_GREEN_CYBER)

            item_y = ry1 + 36
            item_h = max(18, (ry_mid1 - item_y - 8) // 3)
            self._desenhar_mini_item(rx1, item_y, rx2, "PROVEDOR",
                                     f"{self.provedor_ia} ({self.modelo_ia})",
                                     "#ffffff", item_h)
            self._desenhar_mini_item(rx1, item_y + item_h + 3, rx2, "CDP LINK",
                                     self.cdp_status_txt, COR_GREEN_CYBER, item_h)
            self._desenhar_mini_item(rx1, item_y + (item_h + 3) * 2, rx2, "TRAILING",
                                     self.trailing_txt, COR_CYAN_GLOW, item_h)

            # Card Inferior (Conversas & Logs em Tempo Real) - Ocupando toda a extensão
            self._desenhar_card(rx1, ry_mid2, rx2, ry2, "CONVERSAS & LOGS",
                                icone="⚡", badge="TEMPO REAL", cor_neon=COR_GOLD_CYBER)

            # Renderização Rica de Mensagens com Quebra de Linha Automática e Fonte 11pt Legível
            largura_texto = rx2 - rx1 - 24
            log_y = ry_mid2 + 38

            # Pega as mensagens mais recentes e renderiza com texto completo e fonte nítida
            for hora, tag_l, txt_l in self.logs_recentes[-6:]:
                if log_y >= ry2 - 20:
                    break

                # Cores e Ícones de acordo com o autor
                if tag_l in ("VOCÊ", "voce", "USER"):
                    cor_header = COR_CYAN_GLOW
                    icone_msg = "👤"
                    cor_corpo = "#ffffff"
                elif tag_l in ("TIGER", "ia", "IA", "JARVIS"):
                    cor_header = COR_GOLD_CYBER
                    icone_msg = "🐯"
                    cor_corpo = "#e0f2fe"
                else:
                    cor_header = COR_GREEN_CYBER
                    icone_msg = "⚡"
                    cor_corpo = "#d1fae5"

                # 1. Cabeçalho da mensagem (Hora + Autor)
                self.canvas.create_text(rx1 + 12, log_y, text=f"{icone_msg} {hora} [{tag_l}]", anchor="nw",
                                        font=("Arial", 9, "bold"), fill=cor_header)
                log_y += 15

                # 2. Corpo da mensagem (quebra de linha automática nativa com fonte 11pt)
                txt_formatado = txt_l.strip().replace("\r\n", " ").replace("\n", " ")
                if len(txt_formatado) > 200:
                    txt_formatado = txt_formatado[:197] + "..."

                item_txt = self.canvas.create_text(rx1 + 12, log_y, text=txt_formatado, width=largura_texto, anchor="nw",
                                                   font=("Arial", 11), fill=cor_corpo)
                bbox = self.canvas.bbox(item_txt)
                h_msg = (bbox[3] - bbox[1]) if bbox else 16
                log_y += h_msg + 8

                # Linha sutil separadora entre interações
                if log_y < ry2 - 22:
                    self.canvas.create_line(rx1 + 12, log_y - 3, rx2 - 12, log_y - 3, fill="#072338", width=1)


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
            cursor="hand2",
            bd=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        self.renderer = CyberHUDCanvasRenderer(self.canvas, self.largura, self.altura, modo_compacto=False)
        self._animando = True
        self.canvas.bind("<Button-1>", self._ao_clicar_canvas)
        self.bind("<Configure>", self._ao_redimensionar)
        self._loop_animacao()

    def _ao_clicar_canvas(self, event):
        self.renderer.tratar_clique(event.x, event.y)

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
        self.renderer.angulo_radar += 0.035
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
        self.renderer.angulo_radar += 0.035
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
