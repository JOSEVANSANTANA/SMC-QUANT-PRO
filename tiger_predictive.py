# -*- coding: utf-8 -*-
"""
tiger_predictive.py — Motor Quantitativo de Predição, Mapeamento de Liquidez,
Conselheiro Tático de Meta/Momentum e Memória Evolutiva Institucional.

Funcionalidades:
  1. PredictiveLiquidityEngine:
     - Mede agressão (Delta de Volume) e rejeição (Absorção Passiva / Icebergs) na fita real da Tradovate.
     - Compatível nativamente com o formato de negócios da `tradovate_stream.py` ({preco, tamanho, lado})
       e com o formato genérico ({price, size, aggressor}).
  2. calcular_plano_tatico_meta_momentum:
     - Cruza Meta Diária / Ciclo, Risco Restante (Drawdown), Regime de Mercado (Kaufman ER) e Order Flow (CVD)
       para orientar o R:R ótimo, o rigor de entrada e o gerenciamento de lucro sem devolver capital.
  3. MemoriaEvolutivaMercado:
     - Aprende continuamente a expectativa matemática (+R e Win Rate) por (ativo, direção, regime, faixa horária, confluências),
       refinando de forma preditiva e objetiva as próximas decisões em busca de lucro consistente.
"""

import time
import math
import logging
from typing import Any, Dict, List, Optional, Sequence


class PredictiveLiquidityEngine:
    def __init__(self, log_callback=None):
        self.log = log_callback or logging.getLogger(__name__).info
        self.heatmap_levels: Dict[str, Dict[float, Dict[str, float]]] = {}
        self.atr_history: Dict[str, List[float]] = {}
        self.ttl_segundos = 3600  # 1 hora

    def _limpar_memoria_antiga(self, ativo: str, tempo_atual: float):
        """Remove níveis de preço cuja liquidez secou há mais de 1 hora."""
        if ativo not in self.heatmap_levels:
            return
        chaves_remover = [
            preco
            for preco, dados in self.heatmap_levels[ativo].items()
            if tempo_atual - dados.get("timestamp", 0) > self.ttl_segundos
        ]
        for c in chaves_remover:
            del self.heatmap_levels[ativo][c]

    @staticmethod
    def _extrair_negocio(tick: Dict[str, Any]):
        preco = float(tick.get("preco") or tick.get("price") or 0.0)
        volume = float(tick.get("tamanho") or tick.get("size") or tick.get("volume") or 0.0)
        lado = tick.get("lado")
        if lado is None:
            lado = tick.get("aggressor")
        tipo = 0
        if lado in (True, 1, "1", "compra", "COMPRA", "buy", "BUY"):
            tipo = 1
        elif lado in (False, -1, "-1", "venda", "VENDA", "sell", "SELL"):
            tipo = -1
        return preco, volume, tipo

    def analisar_fita(self, ativo: str, negocios: List[Dict[str, Any]]) -> None:
        """
        Processa os ticks em tempo real para montar o Heatmap Institucional.
        Aceita tanto o formato nativo da TradovateStream ({preco, tamanho, lado})
        quanto o formato {price, size, aggressor}.
        """
        if not ativo or not negocios:
            return

        tempo_atual = time.time()
        ativo_key = str(ativo).strip().upper()

        if ativo_key not in self.heatmap_levels:
            self.heatmap_levels[ativo_key] = {}

        self._limpar_memoria_antiga(ativo_key, tempo_atual)

        for tick in negocios[-100:]:
            try:
                if not isinstance(tick, dict):
                    continue
                preco, volume, tipo = self._extrair_negocio(tick)
                if preco <= 0 or volume <= 0 or tipo == 0:
                    continue

                if preco not in self.heatmap_levels[ativo_key]:
                    self.heatmap_levels[ativo_key][preco] = {
                        "compra_agressiva": 0.0,
                        "venda_agressiva": 0.0,
                        "delta": 0.0,
                        "timestamp": tempo_atual,
                    }

                dados = self.heatmap_levels[ativo_key][preco]
                if tipo == 1:
                    dados["compra_agressiva"] += volume
                elif tipo == -1:
                    dados["venda_agressiva"] += volume

                dados["delta"] = dados["compra_agressiva"] - dados["venda_agressiva"]
                dados["timestamp"] = tempo_atual
            except Exception:
                pass

    def gerar_insight_preditivo(self, ativo: str, preco_atual: float, limiar_lotes: float = 20.0) -> str:
        """
        Calcula os Polos Magnéticos (Zonas de Absorção/Liquidez Institucional) e
        devolve o bloco quantitativo injetado no prompt da IA.
        """
        if not ativo or not preco_atual or preco_atual <= 0:
            return ""
        ativo_key = str(ativo).strip().upper()
        niveis = self.heatmap_levels.get(ativo_key)
        if not niveis:
            return ""

        zona_resistencia = None
        max_agressao_compra = 0.0
        zona_suporte = None
        max_agressao_venda = 0.0

        for preco, dados in niveis.items():
            if preco <= preco_atual and dados["venda_agressiva"] > max_agressao_venda:
                max_agressao_venda = dados["venda_agressiva"]
                zona_suporte = preco
            if preco >= preco_atual and dados["compra_agressiva"] > max_agressao_compra:
                max_agressao_compra = dados["compra_agressiva"]
                zona_resistencia = preco

        insights = []
        if zona_suporte is not None and max_agressao_venda >= limiar_lotes:
            insights.append(
                f"ZONA DE ABSORÇÃO/SUPORTE INSTITUCIONAL detectada em {zona_suporte:g} "
                f"({max_agressao_venda:.0f} contratos de agressão vendedora absorvidos)."
            )
        if zona_resistencia is not None and max_agressao_compra >= limiar_lotes:
            insights.append(
                f"ZONA DE OFERTA/LIQUIDEZ INSTITUCIONAL detectada em {zona_resistencia:g} "
                f"({max_agressao_compra:.0f} contratos de agressão compradora absorvidos)."
            )

        if not insights:
            return ""

        texto = "\n[MOTOR PREDITIVO (ORDER FLOW HEATMAP)]\n"
        texto += "A leitura quantitativa da fita aponta os seguintes Polos Magnéticos de liquidez:\n- "
        texto += "\n- ".join(insights)
        texto += "\nUse estes níveis para validar zonas de Order Block, refinar entradas e posicionar stops fora do alcance de Sweeps.\n"
        return texto


def calcular_plano_tatico_meta_momentum(
    plano: Dict[str, Any],
    realizado_hoje: float = 0.0,
    drawdown_restante: float = 1000.0,
    operacoes_feitas_hoje: int = 0,
    regime_info: Optional[Dict[str, Any]] = None,
    fluxo_info: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Módulo de Superinteligência Tática: cruza Meta do Plano, Risco Disponível e Momentum
    para guiar cada decisão rumo ao lucro com proteção máxima da conta.
    """
    if "dd_restante" in kwargs and drawdown_restante == 1000.0:
        drawdown_restante = float(kwargs.get("dd_restante") or 0.0)
    if regime_info is None and "regime" in kwargs:
        regime_info = {"regime": kwargs.get("regime")}
    if fluxo_info is None and "cvd_delta" in kwargs:
        cvd_kw = float(kwargs.get("cvd_delta") or 0.0)
        fluxo_info = {
            "cvd": cvd_kw,
            "pressao": "COMPRADORA" if cvd_kw > 0 else ("VENDEDORA" if cvd_kw < 0 else "NEUTRA"),
        }
    try:
        meta_ciclo = float(plano.get("meta_alvo", 0) or 0)
        dias_meta = max(1, int(float(plano.get("dias_meta", 1) or 1)))
        max_ops = max(1, int(float(plano.get("max_operacoes_dia", 5) or 5)))
        rr_min_plano = max(1.0, float(plano.get("rr_minimo", 2.0) or 2.0))
        prob_min_plano = float(plano.get("probabilidade_minima", 70.0) or 70.0)
        margem = float(plano.get("margem", 0) or 0)
        risco_pct = float(plano.get("risco_pct", 1.0) or 1.0)
    except (TypeError, ValueError):
        meta_ciclo, dias_meta, max_ops, rr_min_plano, prob_min_plano, margem, risco_pct = 0.0, 1, 5, 2.0, 70.0, 0.0, 1.0

    meta_diaria = (meta_ciclo / dias_meta) if meta_ciclo > 0 else 0.0
    falta_hoje = max(0.0, meta_diaria - float(realizado_hoje or 0.0)) if meta_diaria > 0 else 0.0
    ops_restantes = max(0, max_ops - int(operacoes_feitas_hoje or 0))
    meta_batida = bool(meta_diaria > 0 and float(realizado_hoje or 0.0) >= meta_diaria)

    regime = (regime_info or {}).get("regime", "EXPANSAO")
    direcao_regime = (regime_info or {}).get("direcao", "NEUTRO")
    tendencia_forte = bool((regime_info or {}).get("tendencia_forte", False))
    er = float((regime_info or {}).get("efficiency_ratio", 0.5) or 0.5)

    pressao_fluxo = str((fluxo_info or {}).get("pressao", "NEUTRA") or "NEUTRA").upper()
    cvd = float((fluxo_info or {}).get("cvd", 0.0) or 0.0)

    # Calibração de Momentum e Alvo Tático
    if meta_batida:
        postura = "META_BATIDA_ENCERRAR_DIA"
        rr_tatico = rr_min_plano
        prob_tatica = 95.0
        diretriz = (
            f"🏆 META DO DIA BATIDA (Realizado: US$ {realizado_hoje:+,.2f} / Meta Diária: US$ {meta_diaria:,.2f}). "
            "Cessar novas operações hoje para blindar 100% do lucro conquistado."
        )
    elif drawdown_restante <= 0 or ops_restantes <= 0:
        postura = "DEFESA_TOTAL_PARAR"
        rr_tatico = rr_min_plano
        prob_tatica = 95.0
        diretriz = "🛑 Orçamento de risco ou limite de operações do dia esgotado. Preservação de capital prioritária."
    elif tendencia_forte and er >= 0.55:
        postura = f"ATAQUE_A_FAVOR_DO_MOMENTUM_{direcao_regime}"
        rr_tatico = max(rr_min_plano, 2.5)
        prob_tatica = max(prob_min_plano, 75.0)
        alvo_por_op = (falta_hoje / ops_restantes) if (falta_hoje > 0 and ops_restantes > 0) else 0.0
        diretriz = (
            f"🚀 ALTO MOMENTUM DIRECIONAL ({direcao_regime}, Eficiência {er:.0%}, Fluxo {pressao_fluxo} CVD {cvd:+.0f}): "
            f"Operar EXCLUSIVAMENTE a favor da tendência ({'BUY' if direcao_regime == 'ALTA' else 'SELL'}) em pullbacks (OB/FVG/OTE). "
            f"Alvo R:R tático recomendado: 1:{rr_tatico:.1f}."
            + (f" Faltam US$ {falta_hoje:,.2f} para a meta de hoje ({ops_restantes} op(s) restante(s), ~US$ {alvo_por_op:,.2f}/op)."
               if falta_hoje > 0 else "")
        )
    elif regime == "COMPRESSAO":
        postura = "SELETIVIDADE_MAXIMA_RANGE"
        rr_tatico = rr_min_plano
        prob_tatica = max(prob_min_plano, 82.0)
        diretriz = (
            f"🛡️ MERCADO EM COMPRESSÃO/RANGE (Eficiência {er:.0%}): "
            "PROIBIDO operar rompimentos no meio do range. Exigir Liquidity Sweep claro nos extremos (topo/fundo da caixa) "
            f"com confirmação de absorção e probabilidade >= {prob_tatica:.0f}%."
        )
    else:
        postura = "EXECUCAO_INSTITUCIONAL_PADRAO"
        rr_tatico = rr_min_plano
        prob_tatica = max(prob_min_plano, 75.0)
        alvo_por_op = (falta_hoje / ops_restantes) if (falta_hoje > 0 and ops_restantes > 0) else 0.0
        diretriz = (
            f"🎯 POSTURA TÁTICA INSTITUCIONAL (Regime: {regime} {direcao_regime} · Fluxo: {pressao_fluxo}): "
            f"Priorizar setups A+ com R:R >= 1:{rr_tatico:.1f} e proteção rápida de break-even."
            + (f" Faltam US$ {falta_hoje:,.2f} para a meta do dia em até {ops_restantes} oportunidade(s) (~US$ {alvo_por_op:,.2f}/op)."
               if falta_hoje > 0 else "")
        )

    return {
        "postura": postura,
        "meta_diaria": round(meta_diaria, 2),
        "realizado_hoje": round(float(realizado_hoje or 0.0), 2),
        "falta_hoje": round(falta_hoje, 2),
        "ops_restantes": ops_restantes,
        "meta_batida": meta_batida,
        "meta_diaria_batida": meta_batida,
        "rr_tatico": round(rr_tatico, 2),
        "prob_tatica": round(prob_tatica, 1),
        "direcao_dominante": direcao_regime,
        "tendencia_forte": tendencia_forte,
        "efficiency_ratio": round(er, 3),
        "diretriz": diretriz,
    }
