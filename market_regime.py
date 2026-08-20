#!/usr/bin/env python3
"""
market_regime.py — Classificador de Regime de Mercado e Matriz de Confluência Institucional.

Funcionalidades:
  1. Classificação de Regime de Mercado:
     - EXPANSAO (Trend): Tendência forte, volatilidade favorável — alvos longos (R:R 3:1+).
     - COMPRESSAO (Range): Mercado lateralizado/travado — trades curtos ou ficar de fora.
     - RISCO_NOTICIA (Event Risk): Notícias de alto impacto (FOMC, CPI, NFP) — bloqueio total.
  2. Matriz de Confluência Multi-Fator:
     - Pontuação de 0 a 100 combinando SMC + Order Flow + Regime de Mercado + Horário Institucional.
     - Apenas trades com Score >= 80 são autorizados para execução.
"""

from typing import Any, Dict, List, Optional


REGIME_EXPANSAO = "EXPANSAO"
REGIME_COMPRESSAO = "COMPRESSAO"
REGIME_RISCO_NOTICIA = "RISCO_NOTICIA"


class MarketRegimeClassifier:
    """Classifica o regime de mercado em tempo real para proteção de drawdown."""

    @staticmethod
    def classificar(candles: Optional[List[Dict[str, float]]] = None,
                    atr_atual: Optional[float] = None,
                    atr_medio: Optional[float] = None,
                    minutos_para_noticia: Optional[int] = None) -> Dict[str, Any]:
        """
        Classifica o regime atual com base em volatilidade e estrutura.
        """
        # 1. Filtro de Evento Macro / Notícia
        if minutos_para_noticia is not None and 0 <= minutos_para_noticia <= 15:
            return {
                "regime": REGIME_RISCO_NOTICIA,
                "motivo": f"Notícia de alto impacto em {minutos_para_noticia} minutos. Operações bloqueadas.",
                "permissao_operar": False,
                "score_penalidade": -50
            }

        if not candles or len(candles) < 5:
            return {
                "regime": REGIME_EXPANSAO,
                "motivo": "Amostra inicial de candles — operando em modo padrão.",
                "permissao_operar": True,
                "direcao": "NEUTRO"
            }

        # 2. Análise de Deslocamento e Volatilidade
        ultimos = candles[-10:] if len(candles) >= 10 else candles
        maximas = [c.get("high", c.get("maxima", 0)) for c in ultimos]
        minimas = [c.get("low", c.get("minima", 0)) for c in ultimos]
        fechamentos = [c.get("close", c.get("fechamento", 0)) for c in ultimos]

        amplitude_total = max(maximas) - min(minimas)
        corpos_medios = sum(abs(c.get("close", 0) - c.get("open", 0)) for c in ultimos) / len(ultimos)

        # Relação ATR atual vs médio
        razao_atr = (atr_atual / atr_medio) if (atr_atual and atr_medio and atr_medio > 0) else 1.0

        # Tendência direcional
        inicio = fechamentos[0]
        fim = fechamentos[-1]
        deslocamento = fim - inicio

        if razao_atr > 1.2 or (abs(deslocamento) > amplitude_total * 0.6 and corpos_medios > 0):
            direcao = "ALTA" if deslocamento > 0 else "BAIXA"
            return {
                "regime": REGIME_EXPANSAO,
                "direcao": direcao,
                "motivo": f"Mercado em expansão direcional ({direcao}) com volatilidade ativa.",
                "permissao_operar": True,
                "alvo_rr_recomendado": 3.0
            }

        if razao_atr < 0.7 or abs(deslocamento) < amplitude_total * 0.25:
            return {
                "regime": REGIME_COMPRESSAO,
                "direcao": "LATERAL",
                "motivo": "Mercado em compressão lateral (range estreito). Risco de violina elevado.",
                "permissao_operar": False,
                "alvo_rr_recomendado": 1.5
            }

        return {
            "regime": REGIME_EXPANSAO,
            "direcao": "ALTA" if deslocamento > 0 else "BAIXA",
            "motivo": "Estrutura direcional moderada.",
            "permissao_operar": True,
            "alvo_rr_recomendado": 2.0
        }


class ConfluenceMatrix:
    """Matriz de pontuação multi-fator institucional."""

    @staticmethod
    def pontuar_setup(setup_smc: Dict[str, Any],
                      order_flow: Optional[Dict[str, Any]] = None,
                      regime: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Pontua o setup de 0 a 100. Retorna aprovação apenas para Score >= 80.
        """
        score = 0
        confluencias = []
        alertas = []

        direcao = str(setup_smc.get("direcao", "")).upper()

        # 1. Componente SMC (até 40 pontos)
        fatores_smc = setup_smc.get("confluencias", []) or []
        if any("ORDER_BLOCK" in str(f).upper() or "OB" in str(f).upper() for f in fatores_smc):
            score += 15
            confluencias.append("Order Block Institucional")
        if any("FVG" in str(f).upper() or "IMBALANCE" in str(f).upper() for f in fatores_smc):
            score += 15
            confluencias.append("Fair Value Gap (FVG)")
        if any("CHOCH" in str(f).upper() or "BOS" in str(f).upper() or "MSS" in str(f).upper() for f in fatores_smc):
            score += 10
            confluencias.append("Quebra de Estrutura (BOS/ChoCH)")

        # 2. Componente Order Flow (até 30 pontos)
        if order_flow:
            pressao = str(order_flow.get("pressao", "")).upper()
            if (direcao in ("BUY", "COMPRA") and pressao == "COMPRADORA") or \
               (direcao in ("SELL", "VENDA") and pressao == "VENDEDORA"):
                score += 15
                confluencias.append(f"CVD Alinhado ({pressao})")

            if order_flow.get("absorcao"):
                score += 15
                confluencias.append("Absorção Passiva Confirmada")
            elif order_flow.get("sweep"):
                score += 15
                confluencias.append("Liquidity Sweep Confirmado")

        # 3. Componente Regime de Mercado (até 20 pontos)
        if regime:
            tipo_regime = regime.get("regime", REGIME_EXPANSAO)
            if tipo_regime == REGIME_RISCO_NOTICIA:
                score = 0
                alertas.append("BLOQUEIO: Risco de notícia macroeconômica.")
            elif tipo_regime == REGIME_EXPANSAO:
                dir_regime = regime.get("direcao", "")
                if (direcao in ("BUY", "COMPRA") and dir_regime == "ALTA") or \
                   (direcao in ("SELL", "VENDA") and dir_regime == "BAIXA"):
                    score += 20
                    confluencias.append("Tendência em Expansão Alinhada")
                else:
                    score += 10
                    confluencias.append("Expansão Neutra")
            elif tipo_regime == REGIME_COMPRESSAO:
                score -= 20
                alertas.append("ALERTA: Mercado em compressão/range.")

        # 4. Relação Risco:Retorno (até 10 pontos)
        rr = float(setup_smc.get("rr", 0.0) or 0.0)
        if rr >= 2.0:
            score += 10
            confluencias.append(f"Relação R:R Atraente ({rr:.1f}R)")
        elif rr >= 1.5:
            score += 5

        score_final = max(0, min(100, score))
        aprovado = score_final >= 80 and not alertas

        return {
            "score": score_final,
            "aprovado": aprovado,
            "confluencias": confluencias,
            "alertas": alertas,
            "veredito": "APROVADO INSTITUCIONAL" if aprovado else "RECUSADO POR CONFLUÊNCIA INSUFICIENTE"
        }
