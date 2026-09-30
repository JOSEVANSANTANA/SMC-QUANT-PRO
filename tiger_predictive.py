# -*- coding: utf-8 -*-
"""
tiger_predictive.py — Motor Quantitativo de Predição e Mapeamento de Liquidez

Este módulo atua de forma autônoma para medir a agressão (Delta de Volume) 
e a rejeição (Absorção) da fita. Ele fornece um "Heatmap Sintético" das zonas
institucionais ocultas, guiando a inteligência artificial para áreas de 
alta probabilidade antes mesmo da quebra de estrutura (BOS) gráfica.
"""

import time
import math
import logging
from typing import List, Dict, Tuple, Optional

class PredictiveLiquidityEngine:
    def __init__(self, log_callback=None):
        self.log = log_callback or logging.getLogger(__name__).info
        # Histórico de acumulação por nível de preço
        self.heatmap_levels: Dict[str, Dict[float, Dict[str, float]]] = {}
        # Histórico de variação de ATR preditivo
        self.atr_history: Dict[str, List[float]] = {}
        # Frequência de limpeza da memória para manter relevância intradiária
        self.ttl_segundos = 3600  # 1 hora

    def _limpar_memoria_antiga(self, ativo: str, tempo_atual: float):
        """Remove níveis de preço cuja liquidez secou há mais de 1 hora."""
        if ativo not in self.heatmap_levels:
            return
        chaves_remover = []
        for preco, dados in self.heatmap_levels[ativo].items():
            if tempo_atual - dados.get('timestamp', 0) > self.ttl_segundos:
                chaves_remover.append(preco)
        for c in chaves_remover:
            del self.heatmap_levels[ativo][c]

    def analisar_fita(self, ativo: str, negocios: List[Dict]) -> None:
        """
        Processa os ticks em tempo real para montar o Heatmap.
        Busca Absorção: Agressão direcional pesada que não desloca o preço, 
        indicando ordens limitadas absorvendo a liquidez (Icebergs).
        """
        if not negocios or len(negocios) < 10:
            return

        tempo_atual = time.time()
        ativo_key = ativo.upper()
        
        if ativo_key not in self.heatmap_levels:
            self.heatmap_levels[ativo_key] = {}
            
        self._limpar_memoria_antiga(ativo_key, tempo_atual)

        # Mapeia as agressões dos últimos N negócios
        for tick in negocios[-50:]:  # Foco nos eventos mais recentes
            try:
                preco = float(tick.get("price", 0))
                volume = float(tick.get("size", 0))
                # 1 para Agressão de Compra, -1 para Venda, 0 neutro
                tipo = int(tick.get("aggressor", 0)) 
                
                if preco <= 0 or volume <= 0 or tipo == 0:
                    continue
                
                if preco not in self.heatmap_levels[ativo_key]:
                    self.heatmap_levels[ativo_key][preco] = {
                        'compra_agressiva': 0.0,
                        'venda_agressiva': 0.0,
                        'delta': 0.0,
                        'timestamp': tempo_atual
                    }
                
                dados = self.heatmap_levels[ativo_key][preco]
                if tipo == 1:
                    dados['compra_agressiva'] += volume
                elif tipo == -1:
                    dados['venda_agressiva'] += volume
                    
                # Delta positivo indica pressão de compra, negativo pressão de venda
                dados['delta'] = dados['compra_agressiva'] - dados['venda_agressiva']
                dados['timestamp'] = tempo_atual

            except Exception:
                pass

    def gerar_insight_preditivo(self, ativo: str, preco_atual: float) -> str:
        """
        Calcula os 'Polos Magnéticos' (Zonas de Rejeição/Liquidez) e 
        devolve o texto que será injetado no prompt da IA.
        """
        ativo_key = ativo.upper()
        if ativo_key not in self.heatmap_levels or not self.heatmap_levels[ativo_key]:
            return ""

        niveis = self.heatmap_levels[ativo_key]
        
        # Procura as zonas de maior Absorção (Alto Delta, pouca progressão de preço)
        # Simplificação: procuraremos os picos absolutos de agressão (Compra/Venda)
        zona_resistencia = None
        max_agressao_compra = 0.0
        
        zona_suporte = None
        max_agressao_venda = 0.0
        
        for preco, dados in niveis.items():
            # Agressão vendedora no fundo indica Absorção de Compradores Passivos (Suporte)
            if preco < preco_atual and dados['venda_agressiva'] > max_agressao_venda:
                max_agressao_venda = dados['venda_agressiva']
                zona_suporte = preco
                
            # Agressão compradora no topo indica Absorção de Vendedores Passivos (Resistência)
            elif preco > preco_atual and dados['compra_agressiva'] > max_agressao_compra:
                max_agressao_compra = dados['compra_agressiva']
                zona_resistencia = preco

        insights = []
        if zona_suporte and max_agressao_venda > 50: # Limiar genérico de lotes no Micro
            insights.append(f"ZONA DE ABSORÇÃO/SUPORTE INSTITUCIONAL detectada em {zona_suporte} (forte agressão vendedora rejeitada).")
        
        if zona_resistencia and max_agressao_compra > 50:
            insights.append(f"ZONA DE OFERTA/LIQUIDEZ detectada em {zona_resistencia} (vendedores limitados absorvendo pressão compradora).")

        if not insights:
            return ""

        texto = "\n[MOTOR PREDITIVO (ORDER FLOW HEATMAP)]\n"
        texto += "A leitura quantitativa da fita aponta os seguintes 'Polos Magnéticos' de liquidez:\n- "
        texto += "\n- ".join(insights)
        texto += "\nUse estes dados para validar zonas de Order Block e prever o limite dos Sweeps.\n"
        
        return texto
```eof

### 2. Injetando a Predição no Cérebro do `main_app.py`

Agora que o motor matemático existe, ele precisa receber os dados da Tradovate e sussurrar os resultados no ouvido da Gemini/Claude antes da análise.

Faremos isso com o **Monkey Patch** cirúrgico, igual fizemos para estabilizar o sistema.

Vá para a **última linha** do arquivo `main_app.py`, crie uma linha em branco e cole o seguinte bloco:

```python
# ==============================================================================
# PATCH PREDITIVO: INJEÇÃO DO ORÁCULO DE LIQUIDEZ (FASE 1)
# ==============================================================================
import main_app

# Tenta carregar o motor recém-criado
try:
    from tiger_predictive import PredictiveLiquidityEngine
    _motor_preditivo = PredictiveLiquidityEngine()
except Exception as e:
    _motor_preditivo = None
    print(f"⚠️ Motor Preditivo não carregado: {e}")

# Interceptador 1: Alimenta o Motor com os Ticks da Tradovate
_old_processar_ticks = SmcQuantApp._processar_negocios_recebidos

def _patch_processar_negocios_recebidos(self, negocios_lista):
    _old_processar_ticks(self, negocios_lista)
    if _motor_preditivo and negocios_lista:
        try:
            # O primeiro elemento geralmente tem o symbol
            ativo = negocios_lista[0].get("contract", {}).get("name", "")
            if ativo:
                _motor_preditivo.analisar_fita(ativo, negocios_lista)
        except Exception:
            pass

SmcQuantApp._processar_negocios_recebidos = _patch_processar_negocios_recebidos


# Interceptador 2: Injeta a Predição no Prompt da Inteligência Artificial
_old_mensagens_para_provedor = SmcQuantApp._mensagens_para_provedor

def _patch_mensagens_para_provedor(self, pergunta):
    # Roda a função original que monta o prompt (com regras, diário, imagem, etc)
    mensagens = _old_mensagens_para_provedor(self, pergunta)
    
    if _motor_preditivo:
        ativo_alvo = None
        # Tenta descobrir de qual ativo o prompt está falando (geralmente na pergunta ou estado)
        # O self._ativo_em_foco seria o ideal, mas vamos deduzir do estado geral
        for t, d in getattr(self, "_hist_indicadores", {}).items():
            if d: ativo_alvo = t; break # Pega o primeiro ativo ativo
            
        if ativo_alvo:
            preco_atual = 0.0
            _hist = getattr(self, "_hist_indicadores", {}).get(ativo_alvo, [])
            if _hist and _hist[-1][1]: preco_atual = _hist[-1][1]
            
            insight = _motor_preditivo.gerar_insight_preditivo(ativo_alvo, preco_atual)
            if insight:
                # Injeta o insight no final do texto da pergunta que vai pra IA
                for msg in mensagens:
                    if msg.get("role") == "user":
                        # Se for um prompt multi-modal (lista de partes)
                        if isinstance(msg.get("content"), list):
                            for part in msg["content"]:
                                if part.get("type") == "text":
                                    part["text"] += insight
                                    break
                        # Se for texto simples (Claude/Groq)
                        elif isinstance(msg.get("content"), str):
                            msg["content"] += insight
                            
                self.log(f"🧠 [PREDIÇÃO ATIVA]: Insight injetado para {ativo_alvo}.")

    return mensagens

SmcQuantApp._mensagens_para_provedor = _patch_mensagens_para_provedor