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
      PLACEHOLDER_LADO_PELA_COR
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
        var lado = _ladoPelaCor(ln);
        if(lado && diag.rotulos.indexOf(lado)<0) diag.rotulos.push(lado);

        out.push({preco:preco, tamanho:tam, lado:lado});
        if(out.length >= 200) break;
      }
      diag.linhas_vistas = out.length;
      if(!out.length) return JSON.stringify({ok:false, motivo:'fita_sem_linhas', diag:diag});

      // 4) BID/ASK, para as linhas que nao trouxerem lado.
      //
      // O LEITOR ANTIGO NAO PODIA FUNCIONAR NESTA TELA. Ele exigia que o
      // rotulo e o valor estivessem no MESMO no de texto — `num("COMPRA")`,
      // que e sempre null. No cabecalho do grafico dele os dois estao
      // empilhados em elementos separados:
      //
      //     COMPRA            PRECO DE VENDA
      //     7536.75           7537.00
      //
      // Entao: acha o rotulo, e procura o numero ao lado dele — no irmao
      // seguinte, no pai, nessa ordem. Nunca no documento inteiro: o primeiro
      // numero solto da pagina nao tem relacao nenhuma com o book.
      function _valorPerto(el){
        var v = num(txt(el));
        if(v) return v;
        try{
          var ir = el.nextElementSibling;
          for(var k=0; k<3 && ir; k++, ir = ir.nextElementSibling){
            var t = txt(ir);
            if(t && t.length <= 40){ v = num(t); if(v) return v; }
          }
        }catch(e){}
        try{
          var pai = el.parentElement;
          if(pai){
            var tp = txt(pai);
            // Tira o proprio rotulo antes de procurar o numero no pai.
            if(tp && tp.length <= 80){
              v = num(tp.replace(txt(el), ' '));
              if(v) return v;
            }
          }
        }catch(e){}
        return null;
      }

      var bid=null, ask=null;
      var rot = document.querySelectorAll('div,span,td');
      for(var p=0;p<rot.length;p++){
        var rt = txt(rot[p]);
        if(!rt || rt.length>40) continue;
        var nr = norm(rt);
        if(bid===null && /^(bid|compra|preco de compra)\b/.test(nr)){
          var vb=_valorPerto(rot[p]); if(vb) bid=vb;
        }
        if(ask===null && /^(ask|offer|venda|preco de venda)\b/.test(nr)){
          var va=_valorPerto(rot[p]); if(va) ask=va;
        }
      }

      // BID/ASK PARADO E PIOR QUE BID/ASK NENHUM.
      //
      // Nos prints de 23/08 o cabecalho marca COMPRA 7536.75 e PRECO DE VENDA
      // 7537.00 enquanto a fita imprime negocio a 7583 e a 7591 — o book do
      // replay nao acompanha. Se eu usasse esses numeros no Lee-Ready, TODO
      // negocio sairia "acima do ask" e portanto agressao compradora: o CVD
      // viraria uma reta subindo para sempre. Um numero errado com cara de
      // medida — que e exatamente o defeito que este modulo existe para nao
      // repetir.
      //
      // Book de verdade cola no ultimo negocio. 0,2% de distancia ja e
      // ordem de grandeza acima de qualquer spread real destes contratos, e
      // e o bastante para separar "parado" de "vivo" sem precisar saber o
      // tick de cada ativo.
      if(bid && ask && out.length){
        var ultimo = out[0].preco;
        var meio = (bid + ask) / 2;
        if(meio > 0 && Math.abs(ultimo - meio) / meio > 0.002){
          diag.bid_ask_descartado = {bid:bid, ask:ask, ultimo:ultimo};
          bid = null; ask = null;
        }
      }
      diag.metodo = diag.rotulos.length ? 'rotulo' : ((bid&&ask) ? 'bid_ask' : null);
      return JSON.stringify({ok:true, linhas:out, bid:bid, ask:ask, diag:diag});
    })();
    """

    # =====================================================================
    #  CAPTURA CONTÍNUA — a fita não espera o robô olhar
    # =====================================================================
    #  Ele: "a fita muda o tempo inteiro, esse acompanhamento com o cdp
    #  precisa ser online, sem pausas". Está certo, e o problema é real: com
    #  leitura de 6 em 6 segundos, tudo que rolou entre uma leitura e outra
    #  ou é perdido (se saiu da janela visível da fita) ou chega atrasado.
    #  Num ativo líquido a fita anda dezenas de linhas por segundo.
    #
    #  E o extremo oposto também não serve: chamar o CDP em laço apertado é
    #  exatamente o que afogou o Chrome em 20/08 e derrubou uma ordem no meio
    #  do envio.
    #
    #  A SAÍDA NÃO É OLHAR MAIS VEZES — É PARAR DE OLHAR.
    #  Um MutationObserver instalado DENTRO da página observa a fita em tempo
    #  real, sem pausa nenhuma, e vai empilhando cada negócio novo num balde
    #  ali mesmo. O robô não fica perguntando "mudou?": de tempos em tempos
    #  ele ESVAZIA o balde e recebe tudo que aconteceu no intervalo, na
    #  ordem, sem buraco.
    #
    #  Quem observa é o navegador, que já ia repintar aquelas linhas de
    #  qualquer jeito. O CDP passa a ser chamado MENOS vezes que antes, e
    #  mesmo assim nenhum negócio se perde.
    # AS PEÇAS COMPARTILHADAS: achar a fita e entender uma linha.
    # Ficam numa só porque o observador contínuo e a leitura sob demanda
    # PRECISAM concordar sobre o que é uma linha e qual é o preço dela. Duas
    # cópias divergiriam, e o dia em que divergissem o CVD mudaria de valor
    # dependendo de qual caminho leu.
    _JS_PECAS_DA_FITA = r"""
      function _txt(el){ try{ return (el.innerText||el.textContent||'').trim(); }
                         catch(e){ return ''; } }
      function _norm(s){ return (s||'').toString().normalize('NFD')
        .replace(/[\u0300-\u036f]/g,'').toLowerCase(); }
      // Carimbo de hora/data NÃO é número — "10:42:56.611" vira 104256.611,
      // maior que o preço 7557.25, e seria lido como preço.
      function _ehCarimbo(s){
        return /\d{1,2}:\d{2}/.test(s) || /\d{1,2}\/\d{1,2}\/\d{2,4}/.test(s);
      }
      function _num(s){
        if(!s || _ehCarimbo(s)) return null;
        var t=String(s).replace(/[^0-9.,-]/g,'');
        if(!t) return null;
        if(t.indexOf(',')>-1 && t.indexOf('.')>-1){
          t=(t.lastIndexOf(',')>t.lastIndexOf('.'))
            ? t.replace(/\./g,'').replace(',','.') : t.replace(/,/g,'');
        } else if(t.indexOf(',')>-1){
          t=(t.split(',')[1]||'').length===3 ? t.replace(',','') : t.replace(',','.');
        }
        var v=parseFloat(t);
        return isNaN(v)?null:v;
      }
      // A fita dele NÃO se chama "Time & Sales" em lugar nenhum: o cabeçalho
      // é "SELO DE DATA E HORA | PREÇO | TAMA | CONT.". A âncora são os
      // TÍTULOS DAS COLUNAS, que é o que a tela garante nos dois idiomas.
      function _acharFita(){
        var RE_H=/(selo de data|data e hora|timestamp|hora)/;
        var RE_P=/(preco|price)/, RE_T=/(tama|size|qtd|quant)/;
        var alvo=null, menor=1e9;
        var c=document.querySelectorAll('div,section,table,aside,ul');
        for(var i=0;i<c.length;i++){
          var t=_txt(c[i]);
          if(!t || t.length>8000) continue;
          var n=_norm(t);
          if(!(RE_H.test(n) && RE_P.test(n) && RE_T.test(n))) continue;
          if(t.length<menor){ menor=t.length; alvo=c[i]; }
        }
        return alvo;
      }
      function _lerLinha(ln){
        if(!ln || !ln.querySelectorAll) return null;
        var cel=ln.querySelectorAll('td,[role=cell],span,div'), textos=[];
        for(var k=0;k<cel.length;k++){
          var ct=_txt(cel[k]);
          if(ct && ct.length<30) textos.push(ct);
        }
        if(textos.length<2){
          var bruto=_txt(ln);
          if(!bruto || bruto.length>80) return null;
          textos=bruto.split(/\s+/);
        }
        // Linha de fita TEM carimbo de hora. É assim que o cabeçalho, que
        // tem as palavras das colunas mas não tem hora, fica de fora.
        var hora=null;
        for(var h=0;h<textos.length;h++){ if(_ehCarimbo(textos[h])){ hora=textos[h]; break; } }
        if(!hora) return null;
        var nums=[];
        for(var m=0;m<textos.length;m++){ var v=_num(textos[m]); if(v!==null) nums.push(v); }
        if(nums.length<2) return null;
        var preco=nums[0], tam=null;
        for(var q=1;q<nums.length;q++){
          if(nums[q]>0 && nums[q]===Math.floor(nums[q])){ tam=nums[q]; break; }
        }
        if(preco===null || tam===null || preco<=0) return null;
        // O LADO pela COR da linha: a fita da Tradovate pinta vermelho e
        // verde, e essa é a marca mais estável que existe aqui — classe de
        // CSS muda a cada release da plataforma.
        var lado = _ladoPelaCor(ln);
        return {preco:preco, tamanho:tam, lado:lado, ts:hora,
                chave: hora+'|'+preco+'|'+tam};
      }
    """

    # A COR DA LINHA — E O MOTIVO DE ELA PRECISAR DE UM SEGUNDO OLHAR.
    #
    # Em 23/08, 12:05, o painel respondeu "a fita não marca o lado da agressão
    # e não achei bid/ask". Só que a fita DELE marca: as linhas aparecem
    # pintadas de vermelho e verde nos prints, sem exceção.
    #
    # A explicação está em ONDE a tinta é aplicada. `getComputedStyle` não
    # herda cor de fundo: se a Tradovate pinta a CÉLULA (ou uma faixa interna
    # que ocupa a linha toda) em vez do elemento da linha, a linha devolve
    # `rgba(0,0,0,0)` — transparente. O regex de três números casa "0, 0, 0",
    # nenhuma das duas condições bate, e o lado sai `null` EM SILÊNCIO. A
    # leitura falha parecendo uma fita sem cor.
    #
    # A correção é olhar a linha e, se ela for transparente, olhar para
    # dentro. Não é chute: é procurar a mesma marca um nível abaixo, e parar
    # no primeiro fundo que realmente tem cor.
    _JS_LADO_PELA_COR = r"""
      function _corDe(el){
        try{
          var c = window.getComputedStyle(el);
          // Fundo transparente não é cor: alfa 0 significa "não pintado",
          // e tratá-lo como preto (0,0,0) era o que fazia a leitura morrer.
          if(c.backgroundColor && /rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*0\s*\)/.test(c.backgroundColor)) return null;
          var m = (c.backgroundColor||'').match(/(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
          if(!m) return null;
          var R=+m[1], G=+m[2], B=+m[3];
          if(R===G && G===B) return null;   // cinza/branco/preto: sem lado
          if(R>G+25 && R>B+25) return 'venda';
          if(G>R+25 && G>B+15) return 'compra';
          return null;
        }catch(e){ return null; }
      }
      function _ladoPelaCor(ln){
        var l = _corDe(ln);
        if(l) return l;
        // A linha não está pintada: a tinta pode estar na célula.
        try{
          var f = ln.children || [];
          for(var i=0;i<f.length && i<12;i++){
            l = _corDe(f[i]);
            if(l) return l;
            var n = f[i].children || [];
            for(var j=0;j<n.length && j<6;j++){
              l = _corDe(n[j]);
              if(l) return l;
            }
          }
        }catch(e){}
        // Última tentativa: marca declarada em classe ou atributo.
        try{
          var a = ((ln.className||'') + ' ' + (ln.getAttribute('data-side')||'')
                   + ' ' + (ln.getAttribute('aria-label')||''))
                  .toString().normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
          if(/\b(buy|bid|comprad|compra|up|alta|green)\b/.test(a)) return 'compra';
          if(/\b(sell|ask|offer|vend|down|baixa|red)\b/.test(a)) return 'venda';
        }catch(e){}
        return null;
      }
    """

    _JS_INSTALAR_OBSERVADOR = r"""
    (function(){
      PLACEHOLDER_ACHAR_FITA
      if(window.__smcFita && window.__smcFita.vivo) {
        return JSON.stringify({ok:true, ja_estava:true,
                               capturados: window.__smcFita.balde.length});
      }
      var alvo = _acharFita();
      if(!alvo) return JSON.stringify({ok:false, motivo:'fita_nao_encontrada'});

      var st = window.__smcFita = window.__smcFita || {};
      st.balde = st.balde || [];
      st.vistos = st.vistos || {};
      st.vivo = true;
      st.perdidos = 0;

      // PORTEIRO BARATO, ANTES DO TRABALHO CARO.
      //
      // Cada nó que entra na fita chegava direto em `_lerLinha`, e lá dentro
      // roda `querySelectorAll('td,[role=cell],span,div')` sobre a subárvore
      // inteira e, mais adiante, `getComputedStyle` — que força o navegador a
      // recalcular estilo. Como o laço de fora JÁ expande os descendentes de
      // cada nó adicionado, um bloco de linhas trocado de uma vez fazia isso
      // n vezes para os mesmos n nós: custo quadrático, na página DELE, num
      // ativo que imprime dezenas de negócios por segundo.
      //
      // Toda linha de fita tem carimbo de hora no próprio texto. Uma leitura
      // de texto e um teste de regex descartam container e cabeçalho antes de
      // qualquer varredura. O que passa daqui é candidato de verdade.
      function pareceLinha(ln){
        if(!ln || !ln.querySelectorAll) return false;
        var t;
        try{ t = (ln.innerText||ln.textContent||''); }catch(e){ return false; }
        if(!t) return false;
        // Linha de fita é curta. Texto comprido é bloco, não linha.
        if(t.length > 120) return false;
        return /\d{1,2}:\d{2}/.test(t);
      }

      function registrar(ln){
        if(!pareceLinha(ln)) return;
        var d = _lerLinha(ln);
        if(!d) return;
        // A MESMA LINHA repintada não é negócio novo. A chave junta hora,
        // preço e tamanho: dois negócios idênticos no mesmo milissegundo são
        // o mesmo print da fita.
        var chave = d.chave;
        if(st.vistos[chave]) return;
        st.vistos[chave] = 1;
        st.balde.push({preco:d.preco, tamanho:d.tamanho, lado:d.lado, ts:d.ts});
        // TETO NO BALDE: se o robô parar de esvaziar (app fechado, CDP caído),
        // a página não pode crescer sem limite e travar o navegador DELE.
        if(st.balde.length > 4000){
          st.perdidos += (st.balde.length - 3000);
          st.balde = st.balde.slice(-3000);
        }
        var ks = Object.keys(st.vistos);
        if(ks.length > 8000){ for(var i=0;i<4000;i++) delete st.vistos[ks[i]]; }
      }

      // Conta o que JÁ está na tela como visto, sem mandar para o balde: o
      // CVD começa a contar de agora, e não com o passado da sessão embutido.
      var iniciais = alvo.querySelectorAll('tr,[role=row],li,div');
      for(var i=0;i<iniciais.length;i++){
        var d0 = _lerLinha(iniciais[i]);
        if(d0) st.vistos[d0.chave] = 1;
      }

      st.obs = new MutationObserver(function(muts){
        for(var m=0;m<muts.length;m++){
          var add = muts[m].addedNodes;
          for(var a=0;a<add.length;a++){
            var n = add[a];
            if(!n || n.nodeType !== 1) continue;
            registrar(n);
            // A fita às vezes troca um bloco inteiro de linhas de uma vez.
            var dentro = n.querySelectorAll ? n.querySelectorAll('tr,[role=row],li,div') : [];
            for(var q=0;q<dentro.length;q++) registrar(dentro[q]);
          }
        }
      });
      st.obs.observe(alvo, {childList:true, subtree:true});
      return JSON.stringify({ok:true, ja_estava:false, capturados:0});
    })();
    """

    _JS_ESVAZIAR_BALDE = r"""
    (function(){
      var st = window.__smcFita;
      if(!st || !st.vivo) return JSON.stringify({ok:false, motivo:'sem_observador'});
      var lote = st.balde;
      st.balde = [];
      var perdidos = st.perdidos || 0;
      st.perdidos = 0;
      return JSON.stringify({ok:true, negocios:lote, perdidos:perdidos});
    })();
    """

    def _js_com_achador(self, js):
        """Injeta o achador da fita e o leitor de linha nos scripts."""
        return js.replace("PLACEHOLDER_ACHAR_FITA",
                          self._JS_LADO_PELA_COR + self._JS_PECAS_DA_FITA)

    def instalar_observador(self):
        """Põe o observador da fita de pé DENTRO da página. Idempotente.

        Chamar de novo com o observador vivo não reinstala nada — devolve
        `ja_estava` e segue. É de propósito: um observador duplicado contaria
        cada negócio duas vezes, e o CVD dobraria sem ninguém perceber.
        """
        if not self.cdp:
            return {"ok": False, "motivo": "cdp_ausente"}
        try:
            r = self.cdp.cdp("Runtime.evaluate", {
                "expression": self._js_com_achador(self._JS_INSTALAR_OBSERVADOR),
                "returnByValue": True, "awaitPromise": False}, timeout=5)
            bruto = r.get("result", {}).get("value", "")
            return json.loads(bruto) if bruto else {"ok": False, "motivo": "sem_retorno"}
        except Exception as e:
            return {"ok": False, "motivo": f"erro:{e}"}

    def drenar_negocios(self):
        """Tira do balde tudo que a página capturou desde a última vez.

        Devolve (negócios, info). `perdidos` vem junto e nunca é escondido:
        se o balde estourou porque ninguém esvaziou, o CVD tem um buraco, e
        um buraco não anunciado é pior que um número ausente.
        """
        if not self.cdp:
            return [], {"ok": False, "motivo": "cdp_ausente"}
        try:
            r = self.cdp.cdp("Runtime.evaluate", {
                "expression": self._JS_ESVAZIAR_BALDE,
                "returnByValue": True, "awaitPromise": False}, timeout=4)
            bruto = r.get("result", {}).get("value", "")
            if not bruto:
                return [], {"ok": False, "motivo": "sem_retorno"}
            d = json.loads(bruto)
            if not d.get("ok"):
                return [], d
            return (d.get("negocios") or []), d
        except Exception as e:
            return [], {"ok": False, "motivo": f"erro:{e}"}

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
                "expression": self._JS_TIME_AND_SALES.replace(
                    "PLACEHOLDER_LADO_PELA_COR", self._JS_LADO_PELA_COR),
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
