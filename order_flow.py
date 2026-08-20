#!/usr/bin/env python3
"""
order_flow.py — Motor Quantitativo de Order Flow, Volume Delta (CVD) e Absorção Institucional.

Calcula em tempo real:
  1. CVD (Cumulative Volume Delta) — Saldo acumulado de agressões de compra vs venda.
  2. Detector de Absorção Passiva — Alto volume em nível de suporte/resistência sem deslocamento.
  3. Detector de Liquidity Sweep (Stop Hunt) — Rompimento de máxima/mínima seguido de rejeição imediata.
  4. Volume Profile & POC (Point of Control) — Níveis de maior concentração de contratos.
"""

from collections import deque
import time
from typing import Any, Dict, List, Optional, Tuple


class OrderFlowEngine:
    """Motor de análise de fluxo de ordens institucional."""

    def __init__(self, max_ticks: int = 5000):
        self.max_ticks = max_ticks
        self.ticks = deque(maxlen=max_ticks)
        self.cvd = 0.0
        self.volume_total = 0.0
        self.compras_agressivas = 0.0
        self.vendas_agressivas = 0.0

    def registrar_tick(self, preco: float, volume: float = 1.0, agressao_compra: bool = True, ts: Optional[float] = None):
        """Registra um novo tick de negociação no motor de fluxo."""
        if preco is None or preco <= 0:
            return
        t = ts or time.time()
        vol = max(1.0, float(volume))
        delta = vol if agressao_compra else -vol

        self.cvd += delta
        self.volume_total += vol
        if agressao_compra:
            self.compras_agressivas += vol
        else:
            self.vendas_agressivas += vol

        self.ticks.append({
            "ts": t,
            "preco": float(preco),
            "volume": vol,
            "agressao_compra": agressao_compra,
            "delta": delta,
            "cvd": self.cvd
        })

    def obter_cvd(self) -> float:
        """Devolve o Cumulative Volume Delta acumulado."""
        return self.cvd

    def detectar_absorcao(self, nivel_preco: float, tolerancia: float = 1.0, janela_ticks: int = 50) -> Dict[str, Any]:
        """
        Detecta se há absorção institucional passiva próxima a um nível chave.
        Absorção ocorre quando há alto volume de agressão mas o preço não consegue romper o nível.
        """
        if not self.ticks or nivel_preco is None:
            return {"absorcao": False, "motivo": "Sem dados de ticks suficientes"}

        amostra = list(self.ticks)[-janela_ticks:]
        ticks_no_nivel = [t for t in amostra if abs(t["preco"] - nivel_preco) <= tolerancia]

        if len(ticks_no_nivel) < 5:
            return {"absorcao": False, "motivo": "Baixa atividade no nível"}

        vol_no_nivel = sum(t["volume"] for t in ticks_no_nivel)
        delta_no_nivel = sum(t["delta"] for t in ticks_no_nivel)

        # Se há forte agressão vendedora (delta muito negativo) mas o preço se manteve acima do nível -> Absorção Compradora
        if delta_no_nivel < -10 and all(t["preco"] >= nivel_preco - tolerancia for t in ticks_no_nivel):
            return {
                "absorcao": True,
                "tipo": "ABSORCAO_COMPRADORA",
                "volume": vol_no_nivel,
                "delta": delta_no_nivel,
                "nivel": nivel_preco,
                "confianca": 85
            }

        # Se há forte agressão compradora (delta muito positivo) mas o preço se manteve abaixo do nível -> Absorção Vendedora
        if delta_no_nivel > 10 and all(t["preco"] <= nivel_preco + tolerancia for t in ticks_no_nivel):
            return {
                "absorcao": True,
                "tipo": "ABSORCAO_VENDEDORA",
                "volume": vol_no_nivel,
                "delta": delta_no_nivel,
                "nivel": nivel_preco,
                "confianca": 85
            }

        return {"absorcao": False, "volume": vol_no_nivel, "delta": delta_no_nivel}

    def detectar_sweep_de_liquidez(self, maxima_recente: float, minima_recente: float,
                                   preco_atual: float, direcao: str) -> Dict[str, Any]:
        """
        Detecta se houve captura de liquidez (Sweep / Stop Hunt) em topos ou fundos.
        """
        if not self.ticks or preco_atual is None:
            return {"sweep": False}

        amostra = list(self.ticks)[-30:]
        if not amostra:
            return {"sweep": False}

        if direcao.upper() in ("BUY", "COMPRA") and minima_recente:
            # Preço perfurou a mínima recente e voltou acima com delta positivo (rejeição)
            violou_fundo = any(t["preco"] < minima_recente for t in amostra)
            rejeitou = preco_atual > minima_recente
            delta_recente = sum(t["delta"] for t in amostra[-10:])
            if violou_fundo and rejeitou and delta_recente > 0:
                return {
                    "sweep": True,
                    "tipo": "BULLISH_SWEEP",
                    "nivel_violado": minima_recente,
                    "delta_reversao": delta_recente,
                    "motivo": f"Liquidez de venda capturada abaixo de {minima_recente} com rejeição compradora."
                }

        if direcao.upper() in ("SELL", "VENDA") and maxima_recente:
            # Preço perfurou a máxima recente e voltou abaixo com delta negativo (rejeição)
            violou_topo = any(t["preco"] > maxima_recente for t in amostra)
            rejeitou = preco_atual < maxima_recente
            delta_recente = sum(t["delta"] for t in amostra[-10:])
            if violou_topo and rejeitou and delta_recente < 0:
                return {
                    "sweep": True,
                    "tipo": "BEARISH_SWEEP",
                    "nivel_violado": maxima_recente,
                    "delta_reversao": delta_recente,
                    "motivo": f"Liquidez de compra capturada acima de {maxima_recente} com rejeição vendedora."
                }

        return {"sweep": False}

    def calcular_volume_profile(self, agrupamento_ticks: float = 0.25) -> Dict[str, Any]:
        """Calcula o Volume Profile e localiza o Point of Control (POC)."""
        if not self.ticks:
            return {"poc": None, "volume_total": 0}

        distribuicao: Dict[float, float] = {}
        for t in self.ticks:
            p = round(t["preco"] / agrupamento_ticks) * agrupamento_ticks
            distribuicao[p] = distribuicao.get(p, 0.0) + t["volume"]

        poc_preco = max(distribuicao.items(), key=lambda x: x[1])[0] if distribuicao else None
        return {
            "poc": poc_preco,
            "volume_poc": distribuicao.get(poc_preco, 0.0) if poc_preco else 0.0,
            "niveis": distribuicao,
            "volume_total": self.volume_total
        }

    def resumo_para_ia(self) -> Dict[str, Any]:
        """Gera um resumo quantitativo conciso para alimentar a tomada de decisão da IA."""
        return {
            "cvd": round(self.cvd, 2),
            "volume_total": round(self.volume_total, 2),
            "pressao": "COMPRADORA" if self.cvd > 0 else "VENDEDORA" if self.cvd < 0 else "NEUTRA",
            "proporcao_compra_pct": round((self.compras_agressivas / max(1.0, self.volume_total)) * 100, 1),
            "total_ticks": len(self.ticks)
        }
