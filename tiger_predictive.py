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


import json
import os
from datetime import datetime


class MemoriaEvolutivaMercado:
    """
    Motor de Auto-Aprendizado Real Institucional com Travas Anti-Alucinação:
      1. Aprendizado Bayesiano Multi-Dimensional com Decaimento Exponencial (EWMA):
         Aprende por (ativo, direção, regime, sessão horária, confluências).
      2. Aprendizado Contrafactual (Shadow Book):
         Monitora os cenários descartados pelos filtros contra o preço real para medir
         se o filtro salvou dinheiro (teria dado STOP) ou perdeu ganho (teria dado ALVO).
      3. Feedback Loop Autocorretivo Ciclo-a-Ciclo:
         Injeta no prompt do ciclo seguinte os erros técnicos cometidos pela IA no ciclo
         anterior (ex: stop de 100 ticks acima do teto de 80 ticks do NQ), impedindo repetição.
      4. Travas Anti-Alucinação:
         - Validação geométrica estrita antes de gravar qualquer amostra.
         - Encolhimento Bayesiano (Shrinkage k=8) contra superajuste em amostras pequenas.
         - Trava Anti-Câmara-de-Eco: se os 2 últimos cenários daquele ativo+lado deram STOP,
           proíbe inflar probabilidade mesmo que o histórico antigo seja positivo.
         - Teto rígido de ajuste em [-15.0, +12.0] pontos percentuais.
    """

    PRIOR_WINRATE = 0.60
    SHRINKAGE_K = 8.0
    MAX_BONUS_PTS = 12.0
    MAX_PENALTY_PTS = -15.0
    EWMA_ALPHA = 0.25

    def __init__(self, caminho_arquivo: Optional[str] = None):
        if not caminho_arquivo:
            pasta = os.path.expanduser("~/Library/Application Support/SMC_Quant_Pro")
            os.makedirs(pasta, exist_ok=True)
            caminho_arquivo = os.path.join(pasta, "memoria_evolutiva_real.json")
        self.caminho_arquivo = caminho_arquivo
        self.dados: Dict[str, Any] = {
            "versao": "2.86.1",
            "buckets": {},
            "sombra_ativa": [],
            "estatisticas_filtros": {},
            "feedback_ciclo_por_ativo": {},
            "ultimos_resultados_por_ativo": {},
        }
        self._carregar()

    def _carregar(self) -> None:
        if os.path.isfile(self.caminho_arquivo):
            try:
                with open(self.caminho_arquivo, "r", encoding="utf-8") as f:
                    lido = json.load(f)
                if isinstance(lido, dict):
                    for k, v in lido.items():
                        self.dados[k] = v
            except Exception:
                pass

    def _salvar(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.caminho_arquivo), exist_ok=True)
            tmp = self.caminho_arquivo + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.dados, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.caminho_arquivo)
        except Exception:
            pass

    @staticmethod
    def _raiz_ativo(ativo: str) -> str:
        s = str(ativo or "").strip().upper()
        for prefixo in ("MES", "MNQ", "MYM", "M2K", "MGC", "MCL", "MBT", "ES", "NQ", "YM", "RTY", "GC", "CL", "WIN", "WDO"):
            if s.startswith(prefixo):
                return prefixo
        return s or "GERAL"

    @staticmethod
    def _sessao_horaria(ts: Optional[float] = None) -> str:
        dt_now = datetime.fromtimestamp(ts or time.time())
        h = dt_now.hour + dt_now.minute / 60.0
        if 9.5 <= h < 12.0:
            return "MANHA_NY"
        if 12.0 <= h < 14.5:
            return "MEIO_DIA"
        if 14.5 <= h <= 17.5:
            return "TARDE_NY"
        return "EXTENDIDO"

    @staticmethod
    def validar_geometria_anti_alucinacao(
        direcao: str, entry: float, stop: float, tp1: float
    ) -> Tuple[bool, str]:
        """Trava Anti-Alucinação #1: impede gravar ou aprender em cima de números impossíveis."""
        try:
            ep, sl, tp = float(entry or 0), float(stop or 0), float(tp1 or 0)
        except (TypeError, ValueError):
            return False, "preços não numéricos"
        if ep <= 0 or sl <= 0 or tp <= 0:
            return False, "preços zerados ou negativos"
        d = str(direcao or "").strip().upper()
        if d == "BUY" and not (sl < ep < tp):
            return False, f"geometria BUY inválida (stop={sl}, entry={ep}, tp1={tp})"
        if d == "SELL" and not (sl > ep > tp):
            return False, f"geometria SELL inválida (stop={sl}, entry={ep}, tp1={tp})"
        if d not in ("BUY", "SELL"):
            return False, f"direção inválida ({d})"
        return True, ""

    def registrar_resultado_verificado(
        self,
        ativo: str,
        direcao: str,
        resultado: str,
        rr_obtido: float = 0.0,
        regime: str = "EXPANSAO",
        confluencias: Optional[Sequence[str]] = None,
        entry: float = 0.0,
        stop: float = 0.0,
        tp1: float = 0.0,
        ts: Optional[float] = None,
    ) -> bool:
        """
        Registra um cenário real verificado pelo preço (ALVO ou STOP).
        Aplica trava anti-alucinação para rejeitar dados corrompidos.
        """
        res_up = str(resultado or "").strip().upper()
        if res_up not in ("ALVO", "WIN", "GAIN", "TP1", "TP2", "STOP", "LOSS"):
            return False
        if entry > 0 and stop > 0 and tp1 > 0:
            ok_geo, _ = self.validar_geometria_anti_alucinacao(direcao, entry, stop, tp1)
            if not ok_geo:
                return False

        ganhou = res_up in ("ALVO", "WIN", "GAIN", "TP1", "TP2")
        raiz = self._raiz_ativo(ativo)
        dir_up = str(direcao or "").strip().upper()
        reg_up = str(regime or "EXPANSAO").strip().upper()
        sessao = self._sessao_horaria(ts)

        chaves_contexto = [
            f"{raiz}|{dir_up}",
            f"{raiz}|{dir_up}|{reg_up}",
            f"{raiz}|{dir_up}|{sessao}",
        ]
        buckets = self.dados.setdefault("buckets", {})
        for chave in chaves_contexto:
            b = buckets.setdefault(
                chave,
                {
                    "wins": 0,
                    "losses": 0,
                    "total": 0,
                    "soma_r": 0.0,
                    "ewma_wr": self.PRIOR_WINRATE,
                    "ultimo_ts": 0.0,
                },
            )
            b["total"] = int(b.get("total", 0)) + 1
            if ganhou:
                b["wins"] = int(b.get("wins", 0)) + 1
                r_val = float(rr_obtido) if rr_obtido > 0 else 2.0
            else:
                b["losses"] = int(b.get("losses", 0)) + 1
                r_val = -1.0
            b["soma_r"] = round(float(b.get("soma_r", 0.0)) + r_val, 3)
            ewma_ant = float(b.get("ewma_wr", self.PRIOR_WINRATE))
            b["ewma_wr"] = round(
                (1.0 - self.EWMA_ALPHA) * ewma_ant + self.EWMA_ALPHA * (1.0 if ganhou else 0.0),
                4,
            )
            b["ultimo_ts"] = float(ts or time.time())

        # Atualiza sequência recente (Anti-Câmara-de-Eco)
        seq_map = self.dados.setdefault("ultimos_resultados_por_ativo", {})
        chave_seq = f"{raiz}|{dir_up}"
        historico_seq = list(seq_map.get(chave_seq) or [])
        historico_seq.append("WIN" if ganhou else "LOSS")
        seq_map[chave_seq] = historico_seq[-10:]

        # Se acertou, limpa feedback de erro anterior desse ativo
        if ganhou:
            self.dados.get("feedback_ciclo_por_ativo", {}).pop(raiz, None)

        self._salvar()
        return True

    def calibrar_probabilidade_real(
        self,
        probabilidade_base: float,
        ativo: str,
        direcao: str,
        regime: str = "EXPANSAO",
        confluencias: Optional[Sequence[str]] = None,
        ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calcula o ajuste Bayesiano + EWMA com Travas Anti-Alucinação:
          - Se os últimos 2 trades de (ativo, direção) tomaram STOP, bloqueia qualquer bônus
            positivo e aplica penalidade de cautela (-4.0 pts).
          - Usa Shrinkage Bayesiano (k=8) para não alucinar com 1 ou 2 trades.
        """
        prob_in = float(probabilidade_base or 0.0)
        raiz = self._raiz_ativo(ativo)
        dir_up = str(direcao or "").strip().upper()
        reg_up = str(regime or "EXPANSAO").strip().upper()
        sessao = self._sessao_horaria(ts)

        buckets = self.dados.get("buckets", {})
        b_base = buckets.get(f"{raiz}|{dir_up}")
        b_reg = buckets.get(f"{raiz}|{dir_up}|{reg_up}")
        b_ses = buckets.get(f"{raiz}|{dir_up}|{sessao}")

        seq = list((self.dados.get("ultimos_resultados_por_ativo") or {}).get(f"{raiz}|{dir_up}") or [])
        dois_stops_seguidos = len(seq) >= 2 and seq[-1] == "LOSS" and seq[-2] == "LOSS"

        if not b_base or int(b_base.get("total", 0)) == 0:
            return {
                "probabilidade_ajustada": prob_in,
                "delta": 0.0,
                "amostras": 0,
                "motivo": "sem histórico específico neste contexto",
                "trava_anti_eco_acionada": False,
            }

        n = int(b_base.get("total", 0))
        wr_empirico = float(b_base.get("wins", 0)) / max(1, n)
        ewma_wr = float(b_base.get("ewma_wr", wr_empirico))
        wr_combinado = 0.5 * wr_empirico + 0.5 * ewma_wr

        if b_reg and int(b_reg.get("total", 0)) >= 2:
            wr_reg = float(b_reg.get("ewma_wr", wr_combinado))
            wr_combinado = 0.65 * wr_combinado + 0.35 * wr_reg

        if b_ses and int(b_ses.get("total", 0)) >= 2:
            wr_ses = float(b_ses.get("ewma_wr", wr_combinado))
            wr_combinado = 0.75 * wr_combinado + 0.25 * wr_ses

        peso_bayes = n / (n + self.SHRINKAGE_K)
        wr_shrunk = self.PRIOR_WINRATE + peso_bayes * (wr_combinado - self.PRIOR_WINRATE)
        delta_bruto = (wr_shrunk - self.PRIOR_WINRATE) * 45.0

        # Trava Anti-Câmara-de-Eco: nunca infla probabilidade após 2 stops seguidos no mesmo ativo+lado
        if dois_stops_seguidos:
            delta_final = min(-4.0, delta_bruto)
            motivo = (
                f"Trava Anti-Eco ativa: últimos 2 cenários de {dir_up} {raiz} bateram no stop "
                f"({delta_final:+.1f} pts de cautela)"
            )
        else:
            delta_final = max(self.MAX_PENALTY_PTS, min(self.MAX_BONUS_PTS, delta_bruto))
            motivo = (
                f"Memória Evolutiva {raiz} {dir_up} ({n} amostras, WR ponderado {wr_combinado*100:.0f}%): "
                f"{delta_final:+.1f} pts"
            )

        prob_final = round(max(0.0, min(98.0, prob_in + delta_final)), 1)
        return {
            "probabilidade_ajustada": prob_final,
            "delta": round(delta_final, 1),
            "amostras": n,
            "motivo": motivo,
            "trava_anti_eco_acionada": dois_stops_seguidos,
        }

    def registrar_cenario_sombra(
        self,
        ativo: str,
        direcao: str,
        entry: float,
        stop: float,
        tp1: float,
        motivo_descarte: str,
        confluencias: Optional[Sequence[str]] = None,
        regime: str = "EXPANSAO",
    ) -> bool:
        """
        Guarda cenários descartados pelos filtros para Aprendizado Contrafactual (Shadow Book).
        Quando o preço real andar, o agente verifica se o filtro salvou capital (teria dado STOP)
        ou se descartou uma operação vencedora (teria dado ALVO).
        """
        ok_geo, _ = self.validar_geometria_anti_alucinacao(direcao, entry, stop, tp1)
        if not ok_geo:
            return False

        sombra = self.dados.setdefault("sombra_ativa", [])
        # Limita tamanho da fila sombra para não crescer indefinidamente
        agora = time.time()
        sombra[:] = [s for s in sombra if agora - float(s.get("ts", 0)) < 14400][-50:]

        raiz = self._raiz_ativo(ativo)
        sombra.append({
            "ativo": raiz,
            "direcao": str(direcao).strip().upper(),
            "entry": float(entry),
            "stop": float(stop),
            "tp1": float(tp1),
            "motivo_descarte": str(motivo_descarte or "filtro"),
            "confluencias": list(confluencias or []),
            "regime": str(regime or "EXPANSAO"),
            "ativou_entrada": False,
            "ts": agora,
        })
        self._salvar()
        return True

    def atualizar_precos_sombra(self, ativo: str, preco_atual: float) -> List[Dict[str, Any]]:
        """
        Compara o preço ao vivo contra os cenários descartados no Shadow Book.
        Retorna a lista de cenários sombra resolvidos neste tick.
        """
        try:
            p = float(preco_atual or 0.0)
        except (TypeError, ValueError):
            return []
        if p <= 0:
            return []

        raiz = self._raiz_ativo(ativo)
        sombra = self.dados.get("sombra_ativa") or []
        if not sombra:
            return []

        resolvidos: List[Dict[str, Any]] = []
        restantes: List[Dict[str, Any]] = []
        stats_filtros = self.dados.setdefault("estatisticas_filtros", {})

        for item in sombra:
            if item.get("ativo") != raiz:
                restantes.append(item)
                continue
            ep = float(item["entry"])
            sl = float(item["stop"])
            tp = float(item["tp1"])
            d = item["direcao"]

            if not item.get("ativou_entrada"):
                # Verifica se o preço chegou na entrada ou já passou direto pro alvo sem tocar
                if (d == "BUY" and p <= ep) or (d == "SELL" and p >= ep):
                    item["ativou_entrada"] = True
                elif (d == "BUY" and p >= tp) or (d == "SELL" and p <= tp):
                    # Foi embora pro alvo sem tocar na entrada limite
                    continue
                else:
                    restantes.append(item)
                    continue

            # Já ativou a entrada sombra: verifica se bateu no STOP ou no ALVO
            bateu_stop = (d == "BUY" and p <= sl) or (d == "SELL" and p >= sl)
            bateu_alvo = (d == "BUY" and p >= tp) or (d == "SELL" and p <= tp)

            if bateu_stop or bateu_alvo:
                motivo_f = str(item.get("motivo_descarte") or "filtro")
                st = stats_filtros.setdefault(
                    motivo_f, {"stops_evitados": 0, "alvos_perdidos": 0}
                )
                if bateu_stop:
                    st["stops_evitados"] = int(st.get("stops_evitados", 0)) + 1
                    item["desfecho_sombra"] = "STOP_EVITADO"
                else:
                    st["alvos_perdidos"] = int(st.get("alvos_perdidos", 0)) + 1
                    item["desfecho_sombra"] = "ALVO_PERDIDO"
                resolvidos.append(item)
            else:
                restantes.append(item)

        if resolvidos or len(restantes) != len(sombra):
            self.dados["sombra_ativa"] = restantes
            self._salvar()
        return resolvidos

    def registrar_feedback_ciclo(
        self, ativo: str, motivo_falha: str, detalhe_correcao: str
    ) -> None:
        """
        Registra uma falha técnica da IA no ciclo atual (ex: stop fora da faixa máxima de ticks,
        contradição textual, entrada longe demais) para que no PRÓXIMO ciclo o prompt já inclua
        uma instrução corretiva explícita.
        """
        raiz = self._raiz_ativo(ativo)
        fb = self.dados.setdefault("feedback_ciclo_por_ativo", {})
        atual = fb.get(raiz) or {"contagem": 0, "historico": []}
        atual["contagem"] = int(atual.get("contagem", 0)) + 1
        atual["ultimo_motivo"] = str(motivo_falha)
        atual["instrucao_corretiva"] = str(detalhe_correcao)
        atual["ts"] = time.time()
        hist = list(atual.get("historico") or [])
        hist.append({"ts": time.time(), "motivo": str(motivo_falha)})
        atual["historico"] = hist[-5:]
        fb[raiz] = atual
        self._salvar()

    def gerar_prompt_autocorrecao_ciclo(self, ativo: str) -> str:
        """
        Devolve o bloco de autocorreção ciclo-a-ciclo a ser injetado no PROMPT_FINAL
        para impedir que a IA repita o mesmo erro técnico nos ciclos seguintes.
        """
        if not ativo:
            return ""
        raiz = self._raiz_ativo(ativo)
        fb = (self.dados.get("feedback_ciclo_por_ativo") or {}).get(raiz)
        if not fb:
            return ""
        # Expira após 45 minutos
        if time.time() - float(fb.get("ts", 0)) > 2700:
            return ""
        instrucao = str(fb.get("instrucao_corretiva") or "").strip()
        motivo = str(fb.get("ultimo_motivo") or "").strip()
        vezes = int(fb.get("contagem", 1))
        if not instrucao:
            return ""
        return (
            f"\n[⚠️ AUTOCORREÇÃO OBRIGATÓRIA DO AGENTE ({raiz} — {vezes}x recente)]\n"
            f"No ciclo anterior, sua leitura para {raiz} foi BARRADA pelo seguinte erro técnico:\n"
            f"  • Falha detectada: {motivo}\n"
            f"  • Correção obrigatória agora: {instrucao}\n"
            "NÃO repita o mesmo erro neste ciclo.\n"
        )

