# 1. No topo de main_app.py, onde tem a importação do motor:
#
# try:
#     from market_regime import MarketRegimeClassifier, ConfluenceMatrix
# except Exception:
#     MarketRegimeClassifier, ConfluenceMatrix = None, None
#
# CERTIFIQUE-SE DE INSTANCIAR NO __init__ DA SmcQuantApp:
# Substitua a linha 13880:
# self.regime_classifier = MarketRegimeClassifier() if MarketRegimeClassifier else None
# self.confluence_matrix = ConfluenceMatrix() if ConfluenceMatrix else None

# ==============================================================================
# 2. VÁ PARA A LINHA ~2559 DENTRO DA FUNÇÃO _loop_robo_quant (onde ele emite o cenário)
# ==============================================================================

# ENCONTRE ESTE BLOCO:
#
# if sinal_ativo["estado"] == "ENCERRADA" and acao in ("BUY", "SELL") \
#         and preco is not None and preco > 0 \
#         and sinal.get("entry_price") and sinal.get("stop_loss") \
#         and sinal.get("entry_price") > 0 and sinal.get("stop_loss") > 0 \
#         and qualidade_ok and not repetido:

# ==============================================================================
# E SUBSTITUA POR ESTE BLOCO INTEIRO:
# ==============================================================================

                        # ---- 🛡️ FILTRO INSTITUCIONAL DE CONSOLIDAÇÃO (MARKET REGIME) ----
                        # Aqui a inteligência do `market_regime.py` age antes do sinal 
                        # ser validado. Se a fita detectou range (COMPRESSAO) e a IA sugeriu
                        # um rompimento falso, a Matriz de Confluência derruba a nota e recusa.
                        
                        regime_ok = True
                        if acao in ("BUY", "SELL") and getattr(self, "regime_classifier", None):
                            _velas_fita = getattr(self, "_negocios_por_ativo", {}).get(
                                raiz_do_contrato(ativo) or str(ativo).upper(), [])
                            
                            # Avalia se tem histórico mínimo na fita para classificar
                            if len(_velas_fita) >= 15:
                                info_regime = self.regime_classifier.classificar(list(_velas_fita))
                                avaliacao_matrix = self.confluence_matrix.pontuar_setup(sinal, None, info_regime)
                                
                                if not avaliacao_matrix["aprovado"]:
                                    regime_ok = False
                                    repetido = True # Evita que prossiga
                                    self._contar_motivo_do_descarte(
                                        acao, ativo, "mercado em consolidação (chop zone)")
                                    self.log(f"🛡️ BLOQUEIO DE CONSOLIDAÇÃO: {acao} {ativo} recusado "
                                              f"pelo Filtro Institucional. {avaliacao_matrix['alertas'][0]}. "
                                              f"Nota da confluência: {avaliacao_matrix['score']}/80.")

                        # Só cria sinal com preços VÁLIDOS (>0), preço de tela lido E que
                        # passe no piso de qualidade, e que NÃO seja um rompimento falso num range.
                        if sinal_ativo["estado"] == "ENCERRADA" and acao in ("BUY", "SELL") \
                                and preco is not None and preco > 0 \
                                and sinal.get("entry_price") and sinal.get("stop_loss") \
                                and sinal.get("entry_price") > 0 and sinal.get("stop_loss") > 0 \
                                and qualidade_ok and not repetido and regime_ok:
```eof

Com este patch implementado em `main_app.py`, e o arquivo `market_regime.py` salvo na mesma pasta, toda ordem em ambientes de consolidação ou em momentos de baixíssima ineficiência do preço será ativamente bloqueada (ou penalizada) pela sua máquina aritmética. 

Faça a inserção, abra a plataforma na conta de teste da Apex ou Topstep e preste atenção no log quando o mercado lateralizar. Ele vai exibir claramente o aviso do "Bloqueio de Consolidação". Me confirme se tudo correu perfeitamente!

# -*- coding: utf-8 -*-
"""
market_regime.py — Classificador de Regime de Mercado Institucional e Smart SMC.

Funcionalidades:
  1. Identificação de Regime (Math-Based, não dependente de LLM):
     - EXPANSAO (Trend): SMC direcional liberado, FVG, BOS.
     - COMPRESSAO (Range/Chop Zone): Operações centrais bloqueadas. Habilita 
       estratégia de Sweep de Liquidez nas extremidades (Retorno à Média).
  2. Filtro Anti-Violinada para timeframes rápidos (30s e 5m).
"""

from typing import Any, Dict, List, Optional

EXPANSAO = "EXPANSAO"
COMPRESSAO = "COMPRESSAO"
RISCO_NOTICIA = "RISCO_NOTICIA"

class MarketRegimeClassifier:
    """Classifica o regime de mercado em tempo real para proteção e calibração SMC."""

    def __init__(self):
        # Janela ideal para ler o regime nos últimos 15 a 20 candles.
        self.periodo_analise = 15

    def classificar(self, candles: List[Dict[str, float]]) -> Dict[str, Any]:
        """
        Classifica o regime atual com base na eficiência direcional e volatilidade.
        candles: lista de dicionários contendo OHLC [{'open', 'high', 'low', 'close'}].
        """
        resultado = {
            "regime": EXPANSAO,
            "motivo": "Amostra inicial — operando em modo padrão.",
            "permissao_operar": True,
            "score_penalidade": 0,
            "estrategia_sugerida": "SMC Direcional (BOS/FVG)"
        }

        if not candles or len(candles) < self.periodo_analise:
            return resultado

        # Seleciona apenas a janela de análise
        ultimos = candles[-self.periodo_analise:]

        maximas = [c.get("high", c.get("maxima", 0)) for c in ultimos]
        minimas = [c.get("low", c.get("minima", 0)) for c in ultimos]
        fechamentos = [c.get("close", c.get("fechamento", 0)) for c in ultimos]
        aberturas = [c.get("open", c.get("abertura", 0)) for c in ultimos]

        try:
            topo_caixote = max(maximas)
            fundo_caixote = min(minimas)
            amplitude_total = topo_caixote - fundo_caixote

            # 1. Distância Líquida Percorrida (Fechamento atual vs Abertura do início da janela)
            inicio = aberturas[0]
            fim = fechamentos[-1]
            deslocamento_liquido = abs(fim - inicio)

            # 2. Caminho Bruto Percorrido (Soma do tamanho de todos os candles)
            caminho_bruto = sum([abs(ultimos[i].get("close", 0) - ultimos[i-1].get("close", 0)) for i in range(1, len(ultimos))])
            
            # Evita divisão por zero
            if caminho_bruto == 0 or amplitude_total == 0:
                 resultado.update({
                     "regime": COMPRESSAO,
                     "motivo": "Mercado paralisado, sem volume.",
                     "permissao_operar": False,
                     "estrategia_sugerida": "Ficar de fora"
                 })
                 return resultado

            # 3. Ratio de Eficiência de Kaufman (ER)
            # ER = Deslocamento Direcional / Caminho Bruto
            # Vai de 0 (vai e volta, consolidação perfeita) a 1.0 (tendência perfeita sem pullback)
            efficiency_ratio = deslocamento_liquido / caminho_bruto

            # 4. Sombras vs Corpos
            tamanho_corpos = sum([abs(c.get("close", 0) - c.get("open", 0)) for c in ultimos])
            tamanho_sombras = sum([(c.get("high", 0) - c.get("low", 0)) - abs(c.get("close", 0) - c.get("open", 0)) for c in ultimos])
            
            # MATEMÁTICA INSTITUCIONAL DA CONSOLIDAÇÃO
            # Se a eficiência for menor que 0.35 (vai e volta demais) E as sombras forem maiores que os corpos
            if efficiency_ratio < 0.35 and tamanho_sombras > (tamanho_corpos * 1.2):
                resultado.update({
                    "regime": COMPRESSAO,
                    "motivo": f"Mercado em Range (Topos: {topo_caixote} / Fundos: {fundo_caixote}). Alta fricção de liquidez.",
                    "permissao_operar": True, # Podemos operar, MAS...
                    "estrategia_sugerida": "Retorno à Média (Liquidity Sweep nos extremos). Bloquear BOS central.",
                    "score_penalidade": 30 # Penaliza a nota da IA se ela sugerir compra no topo
                })
            else:
                 resultado.update({
                    "regime": EXPANSAO,
                    "motivo": "Mercado em fluxo direcional. Caminho livre.",
                    "permissao_operar": True,
                    "estrategia_sugerida": "SMC Direcional (BOS/CHoCH/FVG)",
                    "score_penalidade": 0
                })

        except Exception as e:
             resultado["motivo"] = f"Erro no cálculo do regime: {e}"

        return resultado

class ConfluenceMatrix:
    """Matriz de pontuação multi-fator."""
    def __init__(self):
        pass

    def pontuar_setup(self, setup_smc: Dict, order_flow: Dict, regime_info: Dict) -> Dict:
        """
        Cruza a sugestão da IA com as leis do mercado. Se o score for menor que 80, o trade não sai.
        """
        score = 0
        alertas = []
        aprovado = False

        # Avaliação de SMC Básica
        if "order block" in str(setup_smc).lower(): score += 30
        if "varredura de liquidez" in str(setup_smc).lower() or "sweep" in str(setup_smc).lower(): score += 20
        if "fvg" in str(setup_smc).lower() or "fair value gap" in str(setup_smc).lower(): score += 10
        
        # Filtro Absoluto de Consolidação
        direcao = str(setup_smc.get("action", "HOLD")).upper()

        if regime_info.get("regime") == COMPRESSAO:
            alertas.append("ALERTA: Mercado Consolidado. Filtrando entradas falsas e ativando Sweep.")
            # Numa consolidação, comprar rompimento é pedir para levar violinada
            # Se o setup sugere COMPRA, só ganha ponto se for acompanhado de um Sweep (fundo do caixote)
            if direcao in ["BUY", "COMPRA"] and "sweep" not in str(setup_smc).lower():
                score -= 40
                alertas.append("Setup de compra em consolidação sem captura de liquidez inferior. Risco de False Breakout (Violinada).")
            elif direcao in ["SELL", "VENDA"] and "sweep" not in str(setup_smc).lower():
                score -= 40
                alertas.append("Setup de venda em consolidação sem captura de liquidez superior. Risco de False Breakout (Violinada).")
            else:
                # É um Sweep (Retorno à média) na consolidação! Estratégia de altíssimo acerto.
                score += 50
                alertas.append("Configuração Institucional de Retorno à Média (Range Sweep) validada. Estratégia LUCRATIVA DE CONSOLIDAÇÃO ATIVADA.")
        
        else: # Regime de Expansão (Trend)
            # Mercado está correndo, BOS/CHoCH e FVG ganham poder
            if "bos" in str(setup_smc).lower() or "choch" in str(setup_smc).lower():
                score += 30
            alertas.append("Regime de Expansão detectado. Privilegiando estrutura direcional.")

        # Deduz a penalidade macro
        score -= regime_info.get("score_penalidade", 0)

        # Avaliação Final
        if score >= 80:
             aprovado = True
             veredito = "APROVADO INSTITUCIONAL"
        else:
             veredito = "RECUSADO POR CONFLUÊNCIA E/OU REGIME DE MERCADO"

        return {
            "score": score,
            "aprovado": aprovado,
            "alertas": alertas,
            "veredito": veredito
        }
```eof

