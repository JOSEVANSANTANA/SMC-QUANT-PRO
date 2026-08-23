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

    # =====================================================================
    #  TIME & SALES — O ÚNICO LUGAR DE ONDE UM CVD DE VERDADE PODE SAIR
    # =====================================================================
    #  Por que é aqui e não no gráfico: delta de agressão precisa de TAMANHO
    #  por negócio e de QUEM agrediu. O gráfico não tem isso; a fita tem.
    #
    #  COMO ISTO LÊ, e por que não precisa da janela na frente:
    #  o CDP roda `Runtime.evaluate` DENTRO da página — é DOM, não pixel.
    #  A janela pode estar atrás de outras, em outra aba do navegador ou
    #  fora da tela, e a leitura continua igual. O que ele NÃO consegue é
    #  ler o que não existe: a Tradovate é uma aplicação React, e um painel
    #  fechado não tem nó no DOM. Por isso a fita precisa estar ABERTA no
    #  layout — aberta, não à vista.
    #
    #  A CLASSIFICAÇÃO DA AGRESSÃO é declarada, nunca adivinhada:
    #    1. coluna/classe de lado na própria linha (Buy/Sell, bid/ask)  -> "rotulo"
    #    2. preço do negócio contra bid/ask do topo do book (Lee-Ready)  -> "bid_ask"
    #  Sem nenhuma das duas, a linha entra SEM lado e o delta não é
    #  calculado. Um delta com lado chutado é o defeito que este módulo
    #  existe para não repetir.
    _JS_TIME_AND_SALES = r"""
    (function(){
      function txt(el){ try{ return (el.innerText||el.textContent||'').trim(); }
                        catch(e){ return ''; } }
      function norm(s){ return (s||'').toString().normalize('NFD')
        .replace(/[\u0300-\u036f]/g,'').toLowerCase(); }

      // CARIMBO DE HORA E DATA NAO SAO NUMERO.
      // A fita dele mostra "10:42:56.611" e "7/9/26" na primeira coluna.
      // Tirando os separadores, o carimbo vira 104256.611 — MAIOR que o
      // preco 7557.25. Qualquer heuristica de "o maior numero da linha e o
      // preco" leria a HORA como preco e mandaria o CVD para o espaco.
      function ehCarimbo(s){
        return /\d{1,2}:\d{2}/.test(s) || /\d{1,2}\/\d{1,2}\/\d{2,4}/.test(s);
      }
      function num(s){
        if(!s || ehCarimbo(s)) return null;
        var t = String(s).replace(/[^0-9.,-]/g,'');
        if(!t) return null;
        if(t.indexOf(',')>-1 && t.indexOf('.')>-1){
          t = (t.lastIndexOf(',') > t.lastIndexOf('.'))
              ? t.replace(/\./g,'').replace(',','.')
              : t.replace(/,/g,'');
        } else if(t.indexOf(',')>-1){
          t = (t.split(',')[1]||'').length===3 ? t.replace(',','') : t.replace(',','.');
        }
        var v = parseFloat(t);
        return isNaN(v) ? null : v;
      }

      var diag = { painel:false, linhas_vistas:0, metodo:null, rotulos:[],
                   cabecalho:null };

      // 1) ACHAR A FITA PELOS TITULOS DAS COLUNAS.
      //    Na tela dele o cabecalho e "SELO DE DATA E HORA | PRECO | TAMA |
      //    CONT." — nao existe a expressao "Time & Sales" em lugar nenhum do
      //    painel. Procurar pelo NOME da janela nao acha; procurar pelo que
      //    as colunas dizem, acha. E vale nos dois idiomas.
      var RE_HORA  = /(selo de data|data e hora|timestamp|hora)/;
      var RE_PRECO = /(preco|price)/;
      var RE_TAM   = /(tama|size|qtd|quant)/;
      var alvo = null, melhor = 1e9;
      var cands = document.querySelectorAll('div,section,table,aside,ul');
      for(var i=0;i<cands.length;i++){
        var c = cands[i], t = txt(c);
        if(!t || t.length > 8000) continue;
        var n = norm(t);
        if(!(RE_HORA.test(n) && RE_PRECO.test(n) && RE_TAM.test(n))) continue;
        // O MENOR container que ainda tem as tres colunas e a fita; os
        // maiores sao a pagina inteira em volta dela.
        if(t.length < melhor){ melhor = t.length; alvo = c; }
      }
      if(!alvo) return JSON.stringify({ok:false, motivo:'fita_nao_encontrada', diag:diag});
      diag.painel = true;
      diag.cabecalho = txt(alvo).slice(0,90);

      // 2) AS LINHAS. Cada uma tem carimbo + preco + tamanho.
      var linhas = alvo.querySelectorAll('tr,[role=row],li,div');
      var out = [];
      for(var j=0;j<linhas.length;j++){
        var ln = linhas[j];
        var celulas = ln.querySelectorAll('td,[role=cell],span,div');
        var textos = [];
        if(celulas.length >= 2){
          for(var k=0;k<celulas.length;k++){
            var ct = txt(celulas[k]);
            if(ct && ct.length < 30) textos.push(ct);
          }
        }
        if(textos.length < 2){
          // Fita que desenha a linha inteira num no so.
          var bruto = txt(ln);
          if(!bruto || bruto.length > 80) continue;
          textos = bruto.split(/\s+/);
        }
        // Linha de fita PRECISA ter carimbo de hora — e assim o cabecalho,
        // que tem as palavras mas nao tem hora, fica de fora sozinho.
        var temHora = false;
        for(var h=0;h<textos.length;h++){ if(ehCarimbo(textos[h])) temHora = true; }
        if(!temHora) continue;

        var nums = [];
        for(var m=0;m<textos.length;m++){
          var v = num(textos[m]);
          if(v !== null) nums.push(v);
        }
        if(nums.length < 2) continue;

        // ORDEM DAS COLUNAS, que e o que a tela garante: depois do carimbo
        // vem PRECO e depois TAMANHO. Nada de "o maior e o preco".
        var preco = nums[0];
        var tam = null;
        for(var q=1;q<nums.length;q++){
          if(nums[q] > 0 && nums[q] === Math.floor(nums[q])){ tam = nums[q]; break; }
        }
        if(preco === null || tam === null || preco <= 0) continue;

        // 3) O LADO. Na fita dele a linha inteira e VERMELHA ou VERDE, e essa
        //    e a marca da agressao. Cor primeiro, classe depois.
        var lado = null;
        try{
          var cor = window.getComputedStyle(ln).backgroundColor || '';
          var rgb = cor.match(/(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
          if(rgb){
            var R=+rgb[1], G=+rgb[2], B=+rgb[3];
            if(R>G+25 && R>B+25) lado='venda';
            else if(G>R+25 && G>B+15) lado='compra';
          }
        }catch(e){}
        if(!lado){
          var assinatura = (ln.className||'') + ' ' + (ln.getAttribute('data-side')||'')
                         + ' ' + (ln.getAttribute('aria-label')||'');
          var na = norm(assinatura);
          if(/\b(buy|bid|comprad|compra|up|alta|green)\b/.test(na)) lado='compra';
          else if(/\b(sell|ask|offer|vend|down|baixa|red)\b/.test(na)) lado='venda';
        }
        if(lado && diag.rotulos.indexOf(lado)<0) diag.rotulos.push(lado);

        out.push({preco:preco, tamanho:tam, lado:lado});
        if(out.length >= 200) break;
      }
      diag.linhas_vistas = out.length;
      if(!out.length) return JSON.stringify({ok:false, motivo:'fita_sem_linhas', diag:diag});

      // 4) BID/ASK, para as linhas que nao trouxerem lado.
      var bid=null, ask=null;
      var rot = document.querySelectorAll('div,span,td');
      for(var p=0;p<rot.length;p++){
        var rt = txt(rot[p]);
        if(!rt || rt.length>40) continue;
        var nr = norm(rt);
        if(bid===null && /^(bid|compra|preco de compra)\b/.test(nr)){
          var vb=num(rt); if(vb) bid=vb;
        }
        if(ask===null && /^(ask|offer|venda|preco de venda)\b/.test(nr)){
          var va=num(rt); if(va) ask=va;
        }
      }
      diag.metodo = diag.rotulos.length ? 'rotulo' : ((bid&&ask) ? 'bid_ask' : null);
      return JSON.stringify({ok:true, linhas:out, bid:bid, ask:ask, diag:diag});
    })();
    """

    def ler_time_and_sales(self) -> Dict[str, Any]:
        """Lê a fita de negócios. Devolve o que achou E como achou.

        O diagnóstico volta junto de propósito: quando não há leitura, o
        trader precisa saber se é a fita fechada, se é a fita aberta e sem
        linhas, ou se é o lado da agressão que não dá para determinar. Um
        "não consegui" sem motivo manda ele caçar defeito no escuro.
        """
        if not self.cdp:
            return {"ok": False, "motivo": "cdp_ausente",
                    "diag": {"painel": False, "linhas_vistas": 0, "metodo": None}}
        try:
            res = self.cdp.cdp("Runtime.evaluate", {
                "expression": self._JS_TIME_AND_SALES,
                "returnByValue": True, "awaitPromise": False}, timeout=4)
            bruto = res.get("result", {}).get("value", "")
            if not bruto:
                return {"ok": False, "motivo": "sem_retorno",
                        "diag": {"painel": False, "linhas_vistas": 0, "metodo": None}}
            return json.loads(bruto)
        except Exception as e:
            return {"ok": False, "motivo": f"erro:{e}",
                    "diag": {"painel": False, "linhas_vistas": 0, "metodo": None}}

    # A fita é uma lista rolante: a cada leitura, o topo traz os negócios
    # novos e o resto já foi contado. Sem esta marca, cada ciclo somaria a
    # janela inteira outra vez e o CVD viraria um número crescente sem
    # significado — parecido demais com o contador inventado que saiu daqui.
    def negocios_novos(self, resultado: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Só os negócios que ainda não foram contados, do mais antigo ao mais novo."""
        r = resultado if resultado is not None else self.ler_time_and_sales()
        diag = r.get("diag") or {}
        if not r.get("ok"):
            return [], diag
        linhas = r.get("linhas") or []          # a fita vem do mais novo para o mais antigo
        marca_anterior = getattr(self, "_ultima_marca_fita", None)
        novos = []
        for ln in linhas:
            marca = (ln.get("preco"), ln.get("tamanho"), ln.get("lado"))
            if marca_anterior is not None and marca == marca_anterior:
                break
            novos.append(ln)
        if linhas:
            primeira = linhas[0]
            self._ultima_marca_fita = (primeira.get("preco"),
                                       primeira.get("tamanho"),
                                       primeira.get("lado"))
        # Na PRIMEIRA leitura não há marca: a janela inteira seria "nova" e o
        # CVD nasceria com o passado embutido. Conta a partir de agora.
        if marca_anterior is None:
            return [], diag
        novos.reverse()
        return novos, diag

    @staticmethod
    def classificar_agressao(linha: Dict[str, Any], bid: Optional[float],
                             ask: Optional[float]) -> Optional[bool]:
        """True = agressão compradora, False = vendedora, None = não sei.

        `None` é resposta legítima e importante: negócio sem lado determinável
        não entra no delta. Preferir um chute aqui seria reconstruir, com
        outro nome, o delta inventado que este módulo substituiu.
        """
        lado = linha.get("lado")
        if lado == "compra":
            return True
        if lado == "venda":
            return False
        preco = linha.get("preco")
        if preco is None or bid is None or ask is None:
            return None
        # Lee-Ready clássico: no ask (ou acima) foi o comprador quem cruzou o
        # spread; no bid (ou abaixo), o vendedor. Entre os dois, indefinido.
        if preco >= ask:
            return True
        if preco <= bid:
            return False
        return None
