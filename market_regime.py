#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_regime.py — Classificador de Regime de Mercado Institucional, Filtro Anti-Contra-Tendência e Matriz de Confluência.

Funcionalidades:
  1. Classificação de Regime de Mercado (Math-Based + Efficiency Ratio de Kaufman):
     - EXPANSAO (Trend): Tendência direcional ativa — identifica ALTA / BAIXA e força da tendência.
     - COMPRESSAO (Range / Chop Zone): Mercado lateralizado — bloqueia entradas no miolo e exige Sweep nos extremos.
     - RISCO_NOTICIA (Event Risk): Notícias macro de alto impacto — bloqueio preventivo.
  2. Escudo Institucional Anti-Contra-Tendência:
     - Impede apostas contra tendências fortes (ex.: comprar faca caindo ou vender foguete subindo)
       a menos que exista confirmação estrutural completa de reversão (CHoCH/MSS + Liquidity Sweep + OB/FVG + Prob >= 85%).
  3. Matriz de Confluência Multi-Fator:
     - Pontuação de 0 a 100 combinando SMC + Order Flow + Regime de Mercado + R:R.
"""

from typing import Any, Dict, List, Optional, Sequence


REGIME_EXPANSAO = "EXPANSAO"
REGIME_COMPRESSAO = "COMPRESSAO"
REGIME_RISCO_NOTICIA = "RISCO_NOTICIA"

# Aliases de compatibilidade
EXPANSAO = REGIME_EXPANSAO
COMPRESSAO = REGIME_COMPRESSAO
RISCO_NOTICIA = REGIME_RISCO_NOTICIA


def _extrair_fechamento(item: Any) -> Optional[float]:
    if isinstance(item, (int, float)):
        return float(item)
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        try:
            return float(item[1])
        except (TypeError, ValueError):
            return None
    if isinstance(item, dict):
        for chave in ("close", "fechamento", "preco", "price"):
            if item.get(chave) is not None:
                try:
                    return float(item[chave])
                except (TypeError, ValueError):
                    return None
    return None


class MarketRegimeClassifier:
    """Classifica o regime de mercado em tempo real para proteção de drawdown e alinhamento direcional."""

    def __init__(self, periodo_analise: int = 15):
        self.periodo_analise = max(5, int(periodo_analise))

    @staticmethod
    def classificar(candles: Optional[List[Dict[str, float]]] = None,
                    atr_atual: Optional[float] = None,
                    atr_medio: Optional[float] = None,
                    minutos_para_noticia: Optional[int] = None) -> Dict[str, Any]:
        """
        Classifica o regime atual com base em volatilidade, estrutura e Ratio de Eficiência de Kaufman (ER).
        Funciona tanto via chamada estática quanto via instância.
        """
        if minutos_para_noticia is not None and 0 <= minutos_para_noticia <= 15:
            return {
                "regime": REGIME_RISCO_NOTICIA,
                "direcao": "NEUTRO",
                "motivo": f"Notícia de alto impacto em {minutos_para_noticia} minutos. Operações bloqueadas.",
                "permissao_operar": False,
                "score_penalidade": -50,
                "tendencia_forte": False,
                "efficiency_ratio": 0.0,
            }

        if not candles or len(candles) < 3:
            return {
                "regime": REGIME_EXPANSAO,
                "direcao": "NEUTRO",
                "motivo": "Amostra inicial de candles — operando em modo padrão.",
                "permissao_operar": True,
                "score_penalidade": 0,
                "tendencia_forte": False,
                "efficiency_ratio": 0.5,
            }

        janela = min(len(candles), 15)
        ultimos = candles[-janela:]
        fechamentos = []
        aberturas = []
        maximas = []
        minimas = []

        for idx, c in enumerate(ultimos):
            if not isinstance(c, dict):
                val = _extrair_fechamento(c)
                if val is not None:
                    fechamentos.append(val)
                    aberturas.append(fechamentos[-2] if len(fechamentos) > 1 else val)
                    maximas.append(val)
                    minimas.append(val)
                continue
            cl = float(c.get("close", c.get("fechamento", c.get("preco", 0))) or 0)
            op = float(c.get("open", c.get("abertura", cl)) or cl)
            hi = float(c.get("high", c.get("maxima", max(op, cl))) or max(op, cl))
            lo = float(c.get("low", c.get("minima", min(op, cl))) or min(op, cl))
            fechamentos.append(cl)
            aberturas.append(op)
            maximas.append(hi)
            minimas.append(lo)

        if len(fechamentos) < 3:
            return {
                "regime": REGIME_EXPANSAO,
                "direcao": "NEUTRO",
                "motivo": "Amostra insuficiente — operando em modo padrão.",
                "permissao_operar": True,
                "score_penalidade": 0,
                "tendencia_forte": False,
                "efficiency_ratio": 0.5,
            }

        amplitude_total = max(maximas) - min(minimas)
        corpos_medios = sum(abs(fechamentos[i] - aberturas[i]) for i in range(len(fechamentos))) / len(fechamentos)
        razao_atr = (float(atr_atual) / float(atr_medio)) if (atr_atual and atr_medio and float(atr_medio) > 0) else 1.0

        inicio = aberturas[0] if aberturas[0] > 0 else fechamentos[0]
        fim = fechamentos[-1]
        deslocamento = fim - inicio
        deslocamento_abs = abs(deslocamento)

        caminho_bruto = sum(abs(fechamentos[i] - fechamentos[i - 1]) for i in range(1, len(fechamentos)))
        efficiency_ratio = (deslocamento_abs / caminho_bruto) if caminho_bruto > 0 else 0.0

        passos_a_favor = 0
        passos_validos = 0
        for i in range(1, len(fechamentos)):
            diff = fechamentos[i] - fechamentos[i - 1]
            if abs(diff) > 1e-9:
                passos_validos += 1
                if (deslocamento > 0 and diff > 0) or (deslocamento < 0 and diff < 0):
                    passos_a_favor += 1
        consistencia_passos = (passos_a_favor / passos_validos) if passos_validos > 0 else 0.0

        direcao = "ALTA" if deslocamento > 0 else ("BAIXA" if deslocamento < 0 else "LATERAL")
        tendencia_forte = bool(
            len(fechamentos) >= 4
            and efficiency_ratio >= 0.55
            and consistencia_passos >= 0.65
            and (amplitude_total <= 0 or deslocamento_abs >= amplitude_total * 0.55)
        )

        if razao_atr > 1.2 or (amplitude_total > 0 and deslocamento_abs > amplitude_total * 0.6 and corpos_medios > 0) or tendencia_forte:
            return {
                "regime": REGIME_EXPANSAO,
                "direcao": direcao,
                "motivo": f"Mercado em expansão direcional ({direcao}) com eficiência {efficiency_ratio:.0%}.",
                "permissao_operar": True,
                "alvo_rr_recomendado": 3.0 if tendencia_forte else 2.5,
                "score_penalidade": 0,
                "tendencia_forte": tendencia_forte,
                "efficiency_ratio": round(efficiency_ratio, 3),
                "consistencia": round(consistencia_passos, 3),
            }

        tamanho_sombras = sum(max(0.0, (maximas[i] - minimas[i]) - abs(fechamentos[i] - aberturas[i])) for i in range(len(fechamentos)))
        tamanho_corpos = sum(abs(fechamentos[i] - aberturas[i]) for i in range(len(fechamentos)))
        muita_sombra = tamanho_sombras > (tamanho_corpos * 1.2) if tamanho_corpos > 0 else True

        if razao_atr < 0.7 or (amplitude_total > 0 and deslocamento_abs < amplitude_total * 0.25) or (efficiency_ratio < 0.30 and muita_sombra):
            return {
                "regime": REGIME_COMPRESSAO,
                "direcao": "LATERAL",
                "motivo": f"Mercado em compressão lateral (ER {efficiency_ratio:.0%}). Risco de violina elevado no miolo.",
                "permissao_operar": False,
                "alvo_rr_recomendado": 1.5,
                "score_penalidade": 30,
                "tendencia_forte": False,
                "efficiency_ratio": round(efficiency_ratio, 3),
                "consistencia": round(consistencia_passos, 3),
            }

        return {
            "regime": REGIME_EXPANSAO,
            "direcao": direcao,
            "motivo": "Estrutura direcional moderada.",
            "permissao_operar": True,
            "alvo_rr_recomendado": 2.0,
            "score_penalidade": 0,
            "tendencia_forte": tendencia_forte,
            "efficiency_ratio": round(efficiency_ratio, 3),
            "consistencia": round(consistencia_passos, 3),
        }


class _ResultadoContraTendencia(dict):
    """Dicionário que também permite desempacotamento `(permitido, motivo)`."""
    def __iter__(self):
        yield bool(self.get("permitido", True))
        yield str(self.get("motivo") or "")


def avaliar_contra_tendencia_forte(
    acao: str,
    precos_recentes: Optional[Any] = None,
    candles: Optional[ Any ] = None,
    confluencias: Optional[Sequence[str]] = None,
    market_analysis: str = "",
    probabilidade: float = 0.0,
    order_flow_pressao: Optional[str] = None,
) -> _ResultadoContraTendencia:
    """
    Trava Institucional Anti-Contra-Tendência:
    Quando o mercado está em tendência fortíssima (ex: derretendo ou explodindo em linha reta),
    NUNCA permite apostar contra a tendência no palpite.
    Só autoriza uma operação de reversão contra tendência forte se houver:
      1. Confirmação explícita de quebra de estrutura de reversão (CHoCH / MSS), E
      2. Varredura de liquidez institucional (Liquidity Sweep / Spring / Upthrust), E
      3. Zona institucional clara (Order Block / FVG / Absorção), E
      4. Order Flow não oposto à reversão (se medido), E
      5. Probabilidade de alta convicção (>= 85%).
    """
    direcao_sinal = str(acao or "").strip().upper()
    if direcao_sinal not in ("BUY", "SELL"):
        return _ResultadoContraTendencia({"permitido": True, "contra_tendencia": False, "direcao_tendencia": "NEUTRO", "motivo": None})

    # Compatibilidade posicional: avaliar_contra_tendencia_forte(acao, info_regime_dict, confluencias, probabilidade)
    info: Optional[Dict[str, Any]] = None
    if isinstance(precos_recentes, dict) and ("regime" in precos_recentes or "tendencia_forte" in precos_recentes or "direcao" in precos_recentes):
        info = dict(precos_recentes)
        if candles is not None and confluencias is None and isinstance(candles, (list, tuple)):
            confluencias = candles
        if isinstance(confluencias, (int, float)) and probabilidade == 0.0:
            probabilidade = float(confluencias)
            confluencias = candles if isinstance(candles, (list, tuple)) else []
    else:
        amostra_candles: List[Dict[str, float]] = []
        if candles and isinstance(candles, (list, tuple)) and len(candles) >= 4:
            amostra_candles = list(candles[-12:])
        elif precos_recentes and isinstance(precos_recentes, (list, tuple)):
            valores = [v for v in (_extrair_fechamento(x) for x in precos_recentes) if v is not None and v > 0]
            filtrados: List[float] = []
            for v in valores:
                if not filtrados or abs(v - filtrados[-1]) > 1e-9:
                    filtrados.append(v)
            if len(filtrados) >= 4:
                for i, p in enumerate(filtrados[-10:]):
                    ant = filtrados[max(0, len(filtrados) - 10 + i - 1)]
                    amostra_candles.append({
                        "open": ant,
                        "high": max(ant, p),
                        "low": min(ant, p),
                        "close": p,
                    })

        if len(amostra_candles) < 4:
            return _ResultadoContraTendencia({"permitido": True, "contra_tendencia": False, "direcao_tendencia": "NEUTRO", "motivo": None})

        info = MarketRegimeClassifier.classificar(amostra_candles)

    tendencia_forte = bool(info.get("tendencia_forte"))
    raw_dir = str(info.get("direcao") or "NEUTRO").upper()
    if raw_dir in ("BEARISH", "SELL", "DOWN", "BAIXA"):
        direcao_tendencia = "BAIXA"
    elif raw_dir in ("BULLISH", "BUY", "UP", "ALTA"):
        direcao_tendencia = "ALTA"
    else:
        direcao_tendencia = raw_dir

    contra = (
        tendencia_forte
        and ((direcao_sinal == "BUY" and direcao_tendencia == "BAIXA")
             or (direcao_sinal == "SELL" and direcao_tendencia == "ALTA"))
    )
    if not contra:
        return _ResultadoContraTendencia({
            "permitido": True,
            "contra_tendencia": False,
            "direcao_tendencia": direcao_tendencia,
            "efficiency_ratio": info.get("efficiency_ratio", 0.0),
            "motivo": None,
        })

    # Está contra uma tendência forte! Verifica se existe confirmação institucional completa de reversão.
    texto_confl = " | ".join(str(c).lower() for c in (confluencias or []))
    texto_total = f"{texto_confl} | {str(market_analysis or '').lower()}"

    tem_choch_mss = any(k in texto_total for k in ("choch", "mss", "change of character", "mudança de caráter", "mudanca de carater"))
    tem_sweep = any(k in texto_total for k in ("sweep", "varredura de liquidez", "captura de liquidez", "stop hunt", "manipulação", "manipulacao"))
    tem_zona = any(k in texto_total for k in ("order block", "ob", "fvg", "fair value gap", "ineficiência", "ineficiencia", "absorção", "absorcao"))
    prob_ok = float(probabilidade or 0.0) >= 85.0

    fluxo_contra = False
    if order_flow_pressao:
        p_norm = str(order_flow_pressao).upper()
        if (direcao_sinal == "BUY" and "VENDEDOR" in p_norm) or (direcao_sinal == "SELL" and "COMPRADOR" in p_norm):
            fluxo_contra = True

    if tem_choch_mss and tem_sweep and tem_zona and prob_ok and not fluxo_contra:
        return _ResultadoContraTendencia({
            "permitido": True,
            "contra_tendencia": True,
            "direcao_tendencia": direcao_tendencia,
            "efficiency_ratio": info.get("efficiency_ratio", 0.0),
            "motivo": "",
        })

    faltam = []
    if not tem_choch_mss:
        faltam.append("CHoCH/MSS de reversão confirmada")
    if not tem_sweep:
        faltam.append("Liquidity Sweep de exaustão")
    if not tem_zona:
        faltam.append("Order Block/FVG institucional")
    if not prob_ok:
        faltam.append(f"probabilidade >= 85% (atual: {float(probabilidade or 0):.0f}%)")
    if fluxo_contra:
        faltam.append(f"Order Flow ainda {order_flow_pressao}")

    return _ResultadoContraTendencia({
        "permitido": False,
        "contra_tendencia": True,
        "direcao_tendencia": direcao_tendencia,
        "efficiency_ratio": info.get("efficiency_ratio", 0.0),
        "motivo": (
            f"mercado em tendência forte de {direcao_tendencia} "
            f"(eficiência {info.get('efficiency_ratio', 0):.0%}) e o sinal {direcao_sinal} "
            f"aposta contra o fluxo dominante sem confirmação completa de reversão "
            f"(faltou: {', '.join(faltam)})"
        ),
    })


class ConfluenceMatrix:
    """Matriz de pontuação multi-fator institucional."""

    def __init__(self):
        pass

    @staticmethod
    def pontuar_setup(setup_smc: Dict[str, Any],
                      order_flow: Optional[Dict[str, Any]] = None,
                      regime: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Pontua o setup de 0 a 100. Retorna aprovação apenas para Score >= 80.
        Funciona tanto via chamada estática quanto via instância.
        """
        score = 0
        confluencias = []
        alertas = []

        direcao = str(setup_smc.get("direcao") or setup_smc.get("action") or "").upper()
        fatores_smc = setup_smc.get("confluencias") or setup_smc.get("confluences") or []
        texto_smc = " ".join(str(f).upper() for f in fatores_smc) + " " + str(setup_smc.get("market_analysis", "")).upper()

        # 1. Componente SMC (até 40 pontos)
        if any(k in texto_smc for k in ("ORDER_BLOCK", "ORDER BLOCK", "OB")):
            score += 15
            confluencias.append("Order Block Institucional")
        if any(k in texto_smc for k in ("FVG", "FAIR VALUE GAP", "IMBALANCE", "INEFICIÊNCIA", "INEFICIENCIA")):
            score += 15
            confluencias.append("Fair Value Gap (FVG)")
        if any(k in texto_smc for k in ("CHOCH", "BOS", "MSS", "QUEBRA DE ESTRUTURA")):
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
        else:
            # Se order_flow não foi passado separadamente, verifica se há sweep/liquidez e indicadores na leitura
            if any(k in texto_smc for k in ("SWEEP", "VARREDURA DE LIQUIDEZ", "LIQUIDITY SWEEP")):
                score += 20
                confluencias.append("Liquidity Sweep Institucional")
            if any(k in texto_smc for k in ("VWAP", "RSI", "MACD", "DISCOUNT", "PREMIUM", "OTE")):
                score += 10
                confluencias.append("Confluência Técnica / Zona OTE")

        # 3. Componente Regime de Mercado (até 20 pontos)
        if regime:
            tipo_regime = regime.get("regime", REGIME_EXPANSAO)
            if tipo_regime == REGIME_RISCO_NOTICIA:
                score = 0
                alertas.append("BLOQUEIO: Risco de notícia macroeconômica.")
            elif tipo_regime == REGIME_EXPANSAO:
                dir_regime = str(regime.get("direcao", "")).upper()
                if (direcao in ("BUY", "COMPRA") and dir_regime == "ALTA") or \
                   (direcao in ("SELL", "VENDA") and dir_regime == "BAIXA"):
                    score += 20
                    confluencias.append("Tendência em Expansão Alinhada")
                elif regime.get("tendencia_forte") and (
                    (direcao in ("BUY", "COMPRA") and dir_regime == "BAIXA") or
                    (direcao in ("SELL", "VENDA") and dir_regime == "ALTA")
                ):
                    score -= 30
                    alertas.append(f"BLOQUEIO: Sinal {direcao} contra tendência forte de {dir_regime}.")
                else:
                    score += 10
                    confluencias.append("Expansão Moderada")
            elif tipo_regime == REGIME_COMPRESSAO:
                if any(k in texto_smc for k in ("SWEEP", "VARREDURA DE LIQUIDEZ", "LIQUIDITY SWEEP")):
                    score += 15
                    confluencias.append("Range Sweep nas Extremidades")
                else:
                    score -= 20
                    alertas.append("ALERTA: Mercado em compressão/range sem captura de liquidez nas extremidades.")

        # 4. Relação Risco:Retorno (até 10 pontos)
        rr = float(setup_smc.get("rr") or setup_smc.get("risk_reward_ratio") or 0.0)
        if rr >= 2.0:
            score += 10
            confluencias.append(f"Relação R:R Atraente ({rr:.1f}R)")
        elif rr >= 1.5:
            score += 5

        score_final = max(0, min(100, score))
        aprovado = score_final >= 80 and not any(a.startswith("BLOQUEIO") or a.startswith("ALERTA") for a in alertas)

        return {
            "score": score_final,
            "aprovado": aprovado,
            "confluencias": confluencias,
            "alertas": alertas,
            "veredito": "APROVADO INSTITUCIONAL" if aprovado else "RECUSADO POR CONFLUÊNCIA INSUFICIENTE",
        }
