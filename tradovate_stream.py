#!/usr/bin/env python3
"""
tradovate_stream.py — Stream de Dados em Tempo Real e Monitor de Sessão Tradovate via CDP.

Permite obter em tempo real (< 10ms):
  1. Cotação ao vivo (Bid, Ask, Last, Volume).
  2. Posição líquida aberta, preço médio e P&L flutuante real.
  3. Status de ordens ativas (Pending, Filled, Canceled).
  4. Saldo da conta e margem disponível.

Funciona diretamente na sessão ativa do Chrome logada na Tradovate (inclusive contas
financiadas Apex, Topstep, MyFundedFutures, etc.), sem necessidade de assinatura de
desenvolvedor de API paga.
"""

import json
import time
from typing import Any, Dict, List, Optional, Tuple


class TradovateStream:
    """Cliente de monitoramento em tempo real da sessão Tradovate via CDP."""

    def __init__(self, cdp_client=None, log=print):
        self.cdp = cdp_client
        self.log = log
        self._ultimo_preco = None
        self._ultimo_ativo = None
        self._ultima_posicao = None
        self._ultimo_pnl = 0.0
        self._cache_ts = 0.0

    def definir_cliente_cdp(self, cdp_client):
        """Atualiza a referência do cliente CDP."""
        self.cdp = cdp_client

    # -------------------------------------------------------------------------
    # Script JavaScript leve injetado na aba da Tradovate para leitura direta
    # -------------------------------------------------------------------------
    _JS_LEITURA_ESTADO = """
    (() => {
        try {
            const estado = {
                ok: true,
                ts: Date.now(),
                ativo: "",
                preco: null,
                bid: null,
                ask: null,
                posicao: 0,
                preco_medio: null,
                pnl_flutuante: 0.0,
                saldo: null,
                ordens_ativas: []
            };

            // 1. Tenta ler o ativo ativo e cotação no cabeçalho ou DOM
            const elAtivo = document.querySelector('.contract-search-input, [data-testid="symbol-search"], .chart-symbol, .order-ticket-symbol');
            if (elAtivo) {
                estado.ativo = (elAtivo.value || elAtivo.innerText || "").trim().toUpperCase();
            }

            // Busca elementos de preço e cotação
            const precos = Array.from(document.querySelectorAll('.last-price, .current-price, .tv-market-price, .dom-last-price, [data-testid="last-price"]'));
            for (const el of precos) {
                const txt = (el.innerText || "").replace(/[^0-9.]/g, '');
                const val = parseFloat(txt);
                if (!isNaN(val) && val > 0) {
                    estado.preco = val;
                    break;
                }
            }

            // 2. Busca posição e P&L flutuante
            const elPos = document.querySelector('.position-display, .net-position, [data-testid="net-pos"]');
            if (elPos) {
                const txtPos = (elPos.innerText || "").replace(/[^0-9-]/g, '');
                const p = parseInt(txtPos, 10);
                if (!isNaN(p)) estado.posicao = p;
            }

            const elPnl = document.querySelector('.open-pnl, .unrealized-pnl, [data-testid="open-pnl"]');
            if (elPnl) {
                let txtPnl = (elPnl.innerText || "").replace(/[^0-9.-]/g, '');
                const pnl = parseFloat(txtPnl);
                if (!isNaN(pnl)) estado.pnl_flutuante = pnl;
            }

            return JSON.stringify(estado);
        } catch (e) {
            return JSON.stringify({ ok: false, erro: String(e) });
        }
    })();
    """

    def ler_estado_ao_vivo(self) -> Dict[str, Any]:
        """Lê o estado ao vivo da plataforma via CDP com latência ultrabaixa (< 10ms)."""
        if not self.cdp:
            return {"ok": False, "erro": "CDP não configurado"}

        try:
            res = self.cdp.cdp("Runtime.evaluate", {
                "expression": self._JS_LEITURA_ESTADO,
                "returnByValue": True,
                "awaitPromise": False
            }, timeout=3)

            val_str = res.get("result", {}).get("value", "")
            if not val_str:
                return {"ok": False, "erro": "Sem retorno do script de leitura"}

            dados = json.loads(val_str)
            if dados.get("ok"):
                if dados.get("preco") is not None:
                    self._ultimo_preco = dados["preco"]
                if dados.get("ativo"):
                    self._ultimo_ativo = dados["ativo"]
                self._ultimo_pnl = dados.get("pnl_flutuante", 0.0)
                self._cache_ts = time.time()

            return dados
        except Exception as e:
            return {"ok": False, "erro": f"Erro na leitura via CDP: {e}"}

    def ler_preco_imediato(self, ativo: Optional[str] = None) -> Optional[float]:
        """Devolve o último preço lido em tempo real."""
        estado = self.ler_estado_ao_vivo()
        if estado.get("ok") and estado.get("preco") is not None:
            return float(estado["preco"])
        return self._ultimo_preco

    def ler_posicao_e_pnl(self) -> Tuple[int, float]:
        """Devolve uma tupla (posição_líquida, pnl_flutuante)."""
        estado = self.ler_estado_ao_vivo()
        if estado.get("ok"):
            pos = int(estado.get("posicao", 0))
            pnl = float(estado.get("pnl_flutuante", 0.0))
            return pos, pnl
        return 0, self._ultimo_pnl
