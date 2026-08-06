# ============================================================================
#  SMC QUANT PRO — Automação de ordens na Tradovate (clique em 2º plano)
#  Marca: TIGER INVEST VIP
# ----------------------------------------------------------------------------
#  OBJETIVO
#    Clicar na altura (preço) do gráfico da Tradovate para posicionar
#    entrada / stop / alvo — SEM roubar o foco da janela e SEM mover o mouse
#    físico. Funciona mesmo com o Chrome atrás de outras janelas ou minimizado.
#
#  COMO ISSO É POSSÍVEL SEM ROUBAR O FOCO
#    A Tradovate (trader.tradovate.com) é um app WEB rodando no Chrome. O jeito
#    correto de injetar um clique num app web em segundo plano é pelo
#    Chrome DevTools Protocol (CDP): mandamos o evento de mouse direto pro
#    renderizador da aba, no PIXEL exato da página. É o mesmo princípio do
#    PrintWindow que o app já usa pra LER a janela sem trazê-la pra frente —
#    só que aqui a gente ESCREVE (clica) em vez de ler.
#
#    → pyautogui NÃO serve: ele move o cursor real e exige a janela na frente,
#      ou seja, rouba o foco. Por isso não é usado aqui.
#
#  PRÉ-REQUISITO (uma vez)
#    O Chrome precisa estar aberto com a "porta de depuração" ligada. Este
#    módulo abre um Chrome dedicado assim (perfil separado, não mexe no seu
#    Chrome normal):
#        chrome.exe --remote-debugging-port=9222
#                   --user-data-dir=<pasta_perfil> https://trader.tradovate.com
#    Use abrir_chrome_debug() para isso. Logue na Tradovate nessa janela uma vez.
#
#  DEPENDÊNCIAS
#    ZERO libs externas. Só a biblioteca padrão do Python (socket, json, etc).
#    Isso mantém o empacotamento (PyInstaller) leve e sem surpresas.
#
#  TESTE ISOLADO (a "estrutura para testar" antes de mexer no app):
#        python tradovate_auto.py
#    O assistente abre o Chrome, calibra 2 preços e deixa você mandar cliques.
# ============================================================================

import os
import json
import time
import socket
import base64
import struct
import hashlib
import subprocess
from urllib.request import urlopen

PORTA_DEBUG_PADRAO = 9222


# ============================================================================
#  Cliente WebSocket mínimo (localhost) — o suficiente pra falar CDP.
#  Escrito à mão de propósito: evita a dependência 'websocket-client' no
#  executável. CDP em localhost manda frames de texto pequenos; este cliente
#  cobre exatamente esse caso (mascara os frames do cliente, lê os do servidor,
#  responde ping, remonta frames fragmentados).
# ============================================================================
class ConexaoPerdida(Exception):
    """A ligação CDP com o Chrome caiu (aba fechada, Chrome reaberto, socket
    abortado). Quem receber isto deve reconectar antes de tentar de novo."""


class _WebSocketMinimo:
    def __init__(self, host, porta, caminho, timeout=10):
        self.sock = socket.create_connection((host, porta), timeout=timeout)
        self.sock.settimeout(timeout)
        self._handshake(host, porta, caminho)
        self._buffer = b""

    def _handshake(self, host, porta, caminho):
        chave = base64.b64encode(os.urandom(16)).decode()
        pedido = (
            f"GET {caminho} HTTP/1.1\r\n"
            f"Host: {host}:{porta}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {chave}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(pedido.encode())
        # Lê os cabeçalhos da resposta até a linha em branco.
        dados = b""
        while b"\r\n\r\n" not in dados:
            pedaco = self.sock.recv(4096)
            if not pedaco:
                raise ConnectionError("Handshake WebSocket falhou (conexão fechada).")
            dados += pedaco
        if b"101" not in dados.split(b"\r\n", 1)[0]:
            raise ConnectionError("Servidor não aceitou o upgrade WebSocket.")
        # Qualquer byte após \r\n\r\n já é frame — guarda no buffer.
        self._buffer = dados.split(b"\r\n\r\n", 1)[1]

    def _recv_exato(self, n):
        while len(self._buffer) < n:
            pedaco = self.sock.recv(65536)
            if not pedaco:
                raise ConnectionError("Conexão WebSocket fechada pelo servidor.")
            self._buffer += pedaco
        out, self._buffer = self._buffer[:n], self._buffer[n:]
        return out

    def enviar(self, texto):
        payload = texto.encode("utf-8")
        n = len(payload)
        cabecalho = bytes([0x81])  # FIN + opcode texto
        if n < 126:
            cabecalho += bytes([0x80 | n])
        elif n < 65536:
            cabecalho += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            cabecalho += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mascara = os.urandom(4)
        mascarado = bytes(payload[i] ^ mascara[i % 4] for i in range(n))
        self.sock.sendall(cabecalho + mascara + mascarado)

    def _ler_frame(self):
        b0, b1 = self._recv_exato(2)
        fin = b0 & 0x80
        opcode = b0 & 0x0F
        mascarado = b1 & 0x80
        tam = b1 & 0x7F
        if tam == 126:
            tam = struct.unpack(">H", self._recv_exato(2))[0]
        elif tam == 127:
            tam = struct.unpack(">Q", self._recv_exato(8))[0]
        chave = self._recv_exato(4) if mascarado else None
        payload = self._recv_exato(tam) if tam else b""
        if chave:
            payload = bytes(payload[i] ^ chave[i % 4] for i in range(len(payload)))
        return fin, opcode, payload

    def receber(self):
        """Devolve a próxima mensagem de TEXTO completa (remonta fragmentos e
        trata frames de controle como ping/close)."""
        partes = b""
        while True:
            fin, opcode, payload = self._ler_frame()
            if opcode == 0x8:        # close
                raise ConnectionError("Servidor pediu fechamento do WebSocket.")
            if opcode == 0x9:        # ping -> responde pong
                self._enviar_controle(0xA, payload)
                continue
            if opcode == 0xA:        # pong -> ignora
                continue
            partes += payload
            if fin:
                return partes.decode("utf-8", "replace")

    def _enviar_controle(self, opcode, payload=b""):
        n = len(payload)
        mascara = os.urandom(4)
        mascarado = bytes(payload[i] ^ mascara[i % 4] for i in range(n))
        self.sock.sendall(bytes([0x80 | opcode, 0x80 | n]) + mascara + mascarado)

    def fechar(self):
        try:
            self._enviar_controle(0x8)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ============================================================================
#  Automação da Tradovate via CDP.
# ============================================================================
class TradovateAuto:
    def __init__(self, porta=PORTA_DEBUG_PADRAO, log=print, arquivo_calib=None):
        self.porta = porta
        self.log = log
        self.ws = None
        self._proximo_id = 1
        # calib = mapeamento linear preço -> Y da página + X da coluna de clique.
        #   { "p1":preco1, "y1":Y1, "p2":preco2, "y2":Y2, "x_click":X }
        self.calib = None
        self.arquivo_calib = arquivo_calib
        if arquivo_calib:
            self.carregar_calibracao(arquivo_calib)

    # ----------------------- Descoberta / conexão -----------------------
    def _http_json(self, caminho):
        url = f"http://127.0.0.1:{self.porta}{caminho}"
        with urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))

    def chrome_ligado(self):
        """True se há um Chrome escutando na porta de depuração."""
        try:
            self._http_json("/json/version")
            return True
        except Exception:
            return False

    def descobrir_aba_tradovate(self):
        """Acha a aba cujo URL contém 'tradovate' e devolve o webSocketDebuggerUrl."""
        for aba in self._http_json("/json"):
            if aba.get("type") == "page" and "tradovate" in (aba.get("url") or "").lower():
                return aba.get("webSocketDebuggerUrl")
        return None

    def conectar(self):
        """Abre o WebSocket CDP na aba da Tradovate. Retorna True/False."""
        if not self.chrome_ligado():
            self.log("❌ Chrome de depuração não encontrado na porta "
                     f"{self.porta}. Abra com abrir_chrome_debug() e logue na Tradovate.")
            return False
        ws_url = self.descobrir_aba_tradovate()
        if not ws_url:
            self.log("❌ Nenhuma aba da Tradovate encontrada. Abra trader.tradovate.com "
                     "na janela de depuração e tente de novo.")
            return False
        # ws://127.0.0.1:9222/devtools/page/XXXX
        resto = ws_url.split("://", 1)[1]
        hostporta, caminho = resto.split("/", 1)
        host, porta = hostporta.split(":")
        self.ws = _WebSocketMinimo(host, int(porta), "/" + caminho)
        self.cdp("Runtime.enable")
        self.cdp("Page.enable")
        self.log("✅ Conectado à aba da Tradovate via CDP.")
        return True

    def desconectar(self):
        if self.ws:
            self.ws.fechar()
            self.ws = None

    # ----------------------------- CDP ----------------------------------
    def cdp(self, metodo, params=None, timeout=10):
        """Envia um comando CDP e espera a resposta com o mesmo id.

        Se o socket cair (Chrome fechado, aba trocada, nova janela de depuração
        aberta por cima da antiga — o famoso WinError 10053), a conexão é
        MARCADA COMO MORTA aqui. Sem isso, `self.ws` continuava preenchido e
        ninguém reconectava: todas as leituras seguintes falhavam para sempre.
        """
        if not self.ws:
            raise ConexaoPerdida("CDP não conectado (chame conectar() antes).")
        meu_id = self._proximo_id
        self._proximo_id += 1
        try:
            self.ws.enviar(json.dumps({"id": meu_id, "method": metodo,
                                        "params": params or {}}))
            limite = time.time() + timeout
            while time.time() < limite:
                msg = json.loads(self.ws.receber())
                if msg.get("id") == meu_id:      # resposta do nosso comando
                    if "error" in msg:
                        raise RuntimeError(f"CDP {metodo}: {msg['error']}")
                    return msg.get("result", {})
                # senão é um evento assíncrono — ignoramos.
        except (OSError, EOFError, ValueError) as e:
            # OSError cobre ConnectionAbortedError/ConnectionResetError (10053/
            # 10054); ValueError cobre frame/JSON corrompido de socket meio morto.
            self._marcar_morta()
            raise ConexaoPerdida(f"conexão com o Chrome caiu durante {metodo}: {e}")
        self._marcar_morta()
        raise ConexaoPerdida(f"sem resposta do CDP para {metodo} (conexão travada).")

    def _marcar_morta(self):
        """Derruba o socket e zera o estado para que a PRÓXIMA chamada reconecte."""
        try:
            if self.ws:
                self.ws.fechar()
        except Exception:
            pass
        self.ws = None

    def conexao_viva(self):
        """Ping baratíssimo para saber se ainda dá para falar com a aba."""
        if not self.ws:
            return False
        try:
            self.cdp("Runtime.evaluate",
                     {"expression": "1", "returnByValue": True}, timeout=4)
            return True
        except Exception:
            self._marcar_morta()
            return False

    def avaliar_js(self, expressao):
        """Runtime.evaluate: roda JS na página e devolve o valor."""
        r = self.cdp("Runtime.evaluate", {
            "expression": expressao, "returnByValue": True, "awaitPromise": True
        })
        return r.get("result", {}).get("value")

    # ------------------------ Clique em 2º plano ------------------------
    def clicar_pagina(self, x, y, dry_run=False):
        """Injeta um clique esquerdo no ponto (x, y) da PÁGINA (coordenadas CSS,
        relativas ao topo-esquerdo da área do site). Não move o mouse real nem
        traz a janela pra frente."""
        x, y = int(round(x)), int(round(y))
        if dry_run:
            self.log(f"   [dry-run] clicaria em (x={x}, y={y})")
            return
        base = {"x": x, "y": y, "button": "left", "clickCount": 1}
        self.cdp("Input.dispatchMouseEvent", dict(base, type="mouseMoved"))
        self.cdp("Input.dispatchMouseEvent", dict(base, type="mousePressed"))
        self.cdp("Input.dispatchMouseEvent", dict(base, type="mouseReleased"))
        self.log(f"   🖱️ clique injetado em (x={x}, y={y})")

    def duplo_clique_pagina(self, x, y, dry_run=False):
        """Duplo-clique no ponto (x, y) da página (alguns gestos da Tradovate
        respondem a duplo-clique)."""
        x, y = int(round(x)), int(round(y))
        if dry_run:
            self.log(f"   [dry-run] duplo-clique em (x={x}, y={y})")
            return
        base = {"x": x, "y": y, "button": "left"}
        self.cdp("Input.dispatchMouseEvent", dict(base, type="mouseMoved", clickCount=0))
        for c in (1, 2):
            self.cdp("Input.dispatchMouseEvent", dict(base, type="mousePressed", clickCount=c))
            self.cdp("Input.dispatchMouseEvent", dict(base, type="mouseReleased", clickCount=c))
        self.log(f"   🖱️🖱️ duplo-clique injetado em (x={x}, y={y})")

    # ---------------------- Inspetor do "Chamado do pedido" --------------
    #  Lê a estrutura do formulário de ordem (inputs, botões, rótulos) e devolve
    #  um resumo. É assim que eu "enxergo" o DOM da SUA Tradovate à distância pra
    #  travar os seletores certos da Opção B (digitar preço + Comprar/Vender +
    #  Enviar), sem chutar.
    def inspecionar_ticket(self):
        js = r"""
        (function(){
          function vis(el){var r=el.getBoundingClientRect();
            return r.width>0&&r.height>0&&r.bottom>0&&r.right>0;}
          function txt(el){return (el.innerText||el.textContent||'').trim().slice(0,40);}
          var out={inputs:[],botoes:[],selects:[]};
          document.querySelectorAll('input,textarea').forEach(function(el){
            if(!vis(el))return;
            var r=el.getBoundingClientRect();
            out.inputs.push({tipo:el.type||'', ph:el.placeholder||'',
              nome:el.name||'', aria:el.getAttribute('aria-label')||'',
              valor:(el.value||'').slice(0,20),
              x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)});
          });
          document.querySelectorAll('button,[role=button]').forEach(function(el){
            if(!vis(el))return; var t=txt(el); if(!t)return;
            var r=el.getBoundingClientRect();
            out.botoes.push({texto:t, x:Math.round(r.x+r.width/2),
              y:Math.round(r.y+r.height/2)});
          });
          document.querySelectorAll('select,[role=combobox],[role=listbox]').forEach(function(el){
            if(!vis(el))return; var r=el.getBoundingClientRect();
            out.selects.push({texto:txt(el), x:Math.round(r.x+r.width/2),
              y:Math.round(r.y+r.height/2)});
          });
          return JSON.stringify(out);
        })()
        """
        try:
            return json.loads(self.avaliar_js(js) or "{}")
        except Exception as e:
            self.log(f"⚠️ Falha ao inspecionar o ticket: {e}")
            return {}

    # ---------------------- Digitação em 2º plano -----------------------
    def digitar_texto(self, texto):
        """Digita texto na página via CDP (vai pro elemento com foco).
        Use depois de clicar/focar um campo."""
        self.cdp("Input.insertText", {"text": str(texto)})

    def apagar_campo(self, vezes=12):
        """Seleciona-tudo + apaga (Ctrl+A, Delete) no campo com foco."""
        # Ctrl+A
        self.cdp("Input.dispatchKeyEvent", {"type": "keyDown", "modifiers": 2,
                                            "key": "a", "code": "KeyA",
                                            "windowsVirtualKeyCode": 65})
        self.cdp("Input.dispatchKeyEvent", {"type": "keyUp", "modifiers": 2,
                                            "key": "a", "code": "KeyA",
                                            "windowsVirtualKeyCode": 65})
        # Delete
        self.cdp("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Delete",
                                            "code": "Delete", "windowsVirtualKeyCode": 46})
        self.cdp("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Delete",
                                            "code": "Delete", "windowsVirtualKeyCode": 46})

    def teclar_escape(self):
        """Manda ESC para a página. É uma das saídas do comprovante da ordem
        quando a setinha ← não é encontrada no DOM."""
        for tipo in ("keyDown", "keyUp"):
            self.cdp("Input.dispatchKeyEvent", {"type": tipo, "key": "Escape",
                                                "code": "Escape",
                                                "windowsVirtualKeyCode": 27})

    # ============================================================
    #  OPÇÃO B — Ordem pelo "Chamado do pedido" (preço EXATO digitado)
    # ============================================================
    #  Localiza controles por TEXTO em tempo de execução (Comprar/Vender/
    #  LIMITE/STOP/Enviar são <div> React, não têm id estável), e preenche
    #  os inputs com o "setter nativo" pra o React reconhecer a mudança.
    def _achar_por_texto(self, palavras):
        """Devolve {palavra: {x, y}} do MENOR elemento visível cujo texto é
        exatamente a palavra (centro em coordenadas de página)."""
        js = """
        (function(alvos){
          function vis(el){var r=el.getBoundingClientRect();return r.width>0&&r.height>0;}
          var res={};
          var els=document.querySelectorAll('button,div,span,a,li,td,label,p');
          for(var i=0;i<els.length;i++){var el=els[i];
            if(!vis(el))continue;
            var t=(el.textContent||'').trim();
            for(var j=0;j<alvos.length;j++){var a=alvos[j];
              if(t===a){var r=el.getBoundingClientRect();var area=r.width*r.height;
                if(!res[a]||area<res[a].area){
                  res[a]={area:area,x:Math.round(r.x+r.width/2),
                          y:Math.round(r.y+r.height/2)};}}}}
          return JSON.stringify(res);
        })(%s)
        """ % json.dumps(palavras)
        try:
            return json.loads(self.avaliar_js(js) or "{}")
        except Exception:
            return {}

    def localizar(self, palavra):
        return self._achar_por_texto([palavra]).get(palavra)

    def definir_campo_ticket(self, papel, valor):
        """Preenche o campo do ticket: papel='preco' ou 'qtd'. Usa o setter
        nativo do input + eventos input/change pra o React captar."""
        js = """
        (function(papel,val){
          function setInput(el,v){
            var setter=Object.getOwnPropertyDescriptor(
              window.HTMLInputElement.prototype,'value').set;
            setter.call(el,String(v));
            el.dispatchEvent(new Event('input',{bubbles:true}));
            el.dispatchEvent(new Event('change',{bubbles:true}));
          }
          var ins=[].slice.call(document.querySelectorAll('input')).filter(function(el){
            var r=el.getBoundingClientRect();
            return r.width>0&&r.height>0&&r.x<300;});   // painel do ticket (esquerda)
          var alvo=null;
          if(papel==='preco'){
            alvo=ins.filter(function(el){
              return (el.placeholder||'')===''
                && /^[0-9][0-9.,]*$/.test((el.value||'').trim());})[0];
          } else {
            alvo=ins.filter(function(el){
              return (el.placeholder||'').toLowerCase().indexOf('selecionar')>=0;})[0];
          }
          if(!alvo) return 'NAO_ACHOU';
          alvo.focus(); setInput(alvo,val);
          return 'OK';
        })(%s,%s)
        """ % (json.dumps(papel), json.dumps(str(valor)))
        return self.avaliar_js(js)

    def _selecionar_tipo(self, tipo, pausa=0.45, dry_run=False):
        """Ajusta TIPO DE PEDIDO clicando no seletor e na opção. Best-effort.
        ATENÇÃO: no Tradovate em PT-BR, STOP = 'PARAR' e STOP LIMITE = 'PARAR
        LIMITE' (confirmado na tela do usuário)."""
        mapa = {"LIMITE": ["LIMITE", "LIMIT"],
                "STOP": ["PARAR", "STOP", "STP"],
                "MERCADO": ["MERCADO", "MKT", "MARKET"],
                "STOP LIMITE": ["PARAR LIMITE", "STOP LIMITE", "STOP LIMIT"]}
        desejados = mapa.get(tipo.upper(), [tipo.upper()])
        todos = sum(mapa.values(), [])
        # Com o dropdown FECHADO, só o tipo ATUAL fica visível -> descobre qual é.
        achou = self._achar_por_texto(todos)
        atual = next((w for lst in mapa.values() for w in lst if w in achou), None)
        if not atual:
            self.log("   ⚠️ seletor de TIPO não encontrado — mantendo o atual.")
            return
        if atual in desejados:
            self.log(f"   tipo já é {tipo.upper()} — mantendo.")
            return
        if dry_run:
            self.log(f"   [dry] mudaria TIPO {atual} → {tipo.upper()}")
            return
        self.clicar_pagina(achou[atual]["x"], achou[atual]["y"]); time.sleep(pausa)  # abre
        opc = self._achar_por_texto(desejados)
        alvo = next((opc[w] for w in desejados if w in opc), None)
        if alvo:
            self.clicar_pagina(alvo["x"], alvo["y"]); time.sleep(pausa)
            self.log(f"   tipo → {tipo.upper()}")
        else:
            self.log(f"   ⚠️ opção '{tipo}' não apareceu no dropdown — mantendo o atual.")

    # Marcadores de que o painel está mostrando o COMPROVANTE da última ordem
    # (e não o formulário). Em PT e EN, porque a Tradovate troca de idioma.
    _RE_COMPROVANTE = r"(MODIFICAR|CANCELAR|Funcionando|Preenchido|Trabalhando|" \
                      r"MODIFY|CANCEL|Working|Filled|Pending)"

    _JS_ESTADO_TICKET = r"""
    (function(){
      function vis(el){
        try{ var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
        catch(e){ return false; }
      }
      function txt(el){
        try{ return (el.innerText||el.textContent||''); }catch(e){ return ''; }
      }
      var temEnviar=false, temComprovante=false;
      var todos=document.querySelectorAll('button,[role=button],div,span,a,p');
      for(var i=0;i<todos.length;i++){
        var el=todos[i];
        if(!vis(el)) continue;
        var t=txt(el).trim();
        if(!t||t.length>60) continue;
        if(/^(Enviar|Submit|Redefinir|Reset)$/i.test(t)) temEnviar=true;
        if(/^(MODIFICAR|CANCELAR|MODIFY|CANCEL)$/i.test(t)) temComprovante=true;
      }
      if(!temComprovante){
        var corpo=(document.body?txt(document.body):'');
        if(/PLACEHOLDER_COMPROVANTE/.test(corpo)) temComprovante=true;
      }
      return JSON.stringify({formulario:temEnviar, comprovante:temComprovante});
    })()
    """

    def estado_ticket(self):
        """Em que estado o 'Chamado do pedido' está:
        'formulario'  -> pronto para digitar a próxima ordem
        'comprovante' -> mostrando o recibo da última ordem (precisa do ←)
        'ausente'     -> o painel não está aberto na tela (só você abre)
        """
        js = self._JS_ESTADO_TICKET.replace("PLACEHOLDER_COMPROVANTE",
                                             self._RE_COMPROVANTE)
        try:
            d = json.loads(self.avaliar_js(js) or "{}")
        except ConexaoPerdida:
            raise
        except Exception:
            return "ausente"
        if d.get("formulario"):
            return "formulario"
        if d.get("comprovante"):
            return "comprovante"
        return "ausente"

    def voltar_ticket(self, dry_run=False):
        """Volta do comprovante da ordem para o FORMULÁRIO clicando na setinha ←.
        É o passo que permite enviar STOP e ALVO depois da ENTRADA.

        A versão anterior procurava o ícone numa FAIXA FIXA DE PIXELS
        (cy entre 165 e 290). Bastava a Tradovate desenhar o painel um pouco
        mais acima — como acontece com o ticket no topo — para a seta ficar fora
        da faixa e o robô concluir que ela "não existe": entrada enviada, stop e
        alvo não. Agora a busca é ANCORADA NO PRÓPRIO COMPROVANTE, sem depender
        de onde ele está na tela.
        """
        js = r"""
        (function(){
          function vis(el){
            try{ var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
            catch(e){ return false; }
          }
          function txt(el){
            try{ return (el.innerText||el.textContent||''); }catch(e){ return ''; }
          }
          function temSvg(el){
            try{
              return (el.tagName && el.tagName.toLowerCase()==='svg') ||
                     (el.querySelector && !!el.querySelector('svg'));
            }catch(e){ return false; }
          }

          // 1) Acha o MENOR container que contém o texto do comprovante.
          var marcador=/PLACEHOLDER_COMPROVANTE/;
          var painel=null, menorArea=Infinity;
          var conts=document.querySelectorAll('div,section,form,aside,main');
          for(var i=0;i<conts.length;i++){
            var el=conts[i];
            if(!vis(el)) continue;
            var t=txt(el);
            if(!marcador.test(t)) continue;
            var r=el.getBoundingClientRect();
            if(r.width<150||r.height<80) continue;   // pequeno demais p/ ser painel
            var a=r.width*r.height;
            if(a<menorArea){ menorArea=a; painel=el; }
          }

          // 2) Escopo da busca: o painel do comprovante (ou a página toda).
          var escopo = painel || document;
          var cx0=0, cy0=0, larg=window.innerWidth, altura=window.innerHeight;
          if(painel){
            var rp=painel.getBoundingClientRect();
            cx0=rp.x; cy0=rp.y; larg=rp.width; altura=rp.height;
          }

          // 3) Dentro dele, o menor ícone clicável no ALTO À ESQUERDA.
          var cands=escopo.querySelectorAll('button,[role=button],a,svg,i,span,div');
          var best=null;
          for(var k=0;k<cands.length;k++){
            var e2=cands[k];
            if(!vis(e2)) continue;
            var r2=e2.getBoundingClientRect();
            if(r2.width>60||r2.height>60) continue;      // ícone, não bloco
            if(r2.width<8||r2.height<8) continue;
            var relX=(r2.x+r2.width/2)-cx0, relY=(r2.y+r2.height/2)-cy0;
            if(relX > larg*0.45) continue;               // metade esquerda
            if(relY > Math.max(altura*0.30, 90)) continue; // topo do painel
            var t2=txt(e2).trim();
            var setaTexto = /^(←|<|‹|⟵|Voltar|Back)$/i.test(t2);
            var svg = temSvg(e2);
            if(!svg && !setaTexto) continue;
            var score = (r2.width*r2.height) - (svg?1e6:0) - (setaTexto?2e6:0);
            if(!best || score<best.score)
              best={score:score, x:Math.round(r2.x+r2.width/2),
                    y:Math.round(r2.y+r2.height/2), el:e2,
                    svg:svg, texto:setaTexto};
          }
          if(!best) return JSON.stringify({achou:false, tinha_painel:!!painel});
          try{
            var alvo=(best.el.closest &&
                      best.el.closest('button,[role=button],a,div')) || best.el;
            alvo.click();
          }catch(e){}
          return JSON.stringify({achou:true, x:best.x, y:best.y,
                                 svg:best.svg, texto:best.texto,
                                 tinha_painel:!!painel});
        })()
        """.replace("PLACEHOLDER_COMPROVANTE", self._RE_COMPROVANTE)

        v = self.avaliar_js(js)
        try:
            d = json.loads(v or "{}")
        except Exception:
            d = {}
        if d.get("achou"):
            if dry_run:
                self.log(f"   [dry] voltaria (←) em ({d['x']},{d['y']})")
                return True
            self.log(f"   ↩️ voltar (←) clicado em ({d['x']},{d['y']}) "
                     f"[svg={d.get('svg')} texto={d.get('texto')}].")
            time.sleep(0.5)
            return True

        onde = ("dentro do comprovante" if d.get("tinha_painel")
                else "na tela (comprovante não localizado)")
        self.log(f"   ⚠️ não achei o botão de voltar (←) {onde} — tentando as "
                 "outras saídas do comprovante.")
        if dry_run:
            return False
        # ROTAS ALTERNATIVAS. Depender de UMA única forma de voltar foi o que
        # deixou posição sem stop no pregão: a setinha não era encontrada e o
        # robô simplesmente desistia, com a entrada já no mercado. Agora há três
        # saídas independentes, e cada uma é verificada de verdade — só declaro
        # que voltei quando o formulário reaparece.
        for rotulo, acao in (
            ("atributo (aria-label/title de voltar)", self._voltar_por_atributo),
            ("tecla ESC", self._voltar_por_escape),
            ("cabeçalho do 'Chamado do pedido'", self._voltar_por_cabecalho),
        ):
            try:
                acao()
            except ConexaoPerdida:
                raise
            except Exception:
                continue
            time.sleep(0.6)
            if self._formulario_visivel():
                self.log(f"   ↩️ voltei ao formulário pela {rotulo}.")
                return True
        return False

    def _voltar_por_atributo(self):
        """Clica em quem se declara botão de voltar/fechar por aria-label/title.
        Independe de geometria — funciona mesmo se a Tradovate mover o painel."""
        self.avaliar_js(r"""
        (function(){
          var sel='[aria-label],[title],[data-testid]';
          var els=document.querySelectorAll(sel);
          var re=/(voltar|back|fechar|close|retornar|previous|anterior)/i;
          for(var i=0;i<els.length;i++){
            var e=els[i];
            var r=e.getBoundingClientRect();
            if(r.width<=0||r.height<=0) continue;
            if(r.width>80||r.height>80) continue;
            var a=(e.getAttribute('aria-label')||'')+' '+
                  (e.getAttribute('title')||'')+' '+
                  (e.getAttribute('data-testid')||'');
            if(!re.test(a)) continue;
            try{ e.click(); return 'ok'; }catch(err){}
          }
          return 'nada';
        })()
        """)

    def _voltar_por_escape(self):
        self.teclar_escape()

    def _voltar_por_cabecalho(self):
        """Clica no título do painel 'Chamado do pedido'. Na Tradovate isso
        recolhe/reabre o ticket, que volta no estado de formulário."""
        for palavra in ("Chamado do pedido", "Order Ticket", "Chamado do Pedido"):
            alvo = self.localizar(palavra)
            if alvo:
                self.clicar_pagina(alvo["x"], alvo["y"])
                return

    # ------------------- LEITURA DAS POSIÇÕES ABERTAS -------------------
    #  Descobre se VOCÊ está posicionado, lendo a própria tela da corretora —
    #  inclusive numa operação aberta na mão, fora da sugestão do robô.
    #
    #  Por que há DUAS estratégias: a Tradovate é um app React feito de <div>,
    #  não de <table>. Em muitos layouts NÃO existe uma grade de posições na
    #  tela; o que existe é o campo "POSIÇÃO" no painel do instrumento (e o
    #  "ABRIR P/L" no topo). Então:
    #    A) grade de posições, quando o painel estiver aberto (tabela/ARIA grid);
    #    B) rótulo "POSIÇÃO"/"POSITION" + valor ao lado, associado ao símbolo do
    #       painel — funciona no layout padrão, sem precisar abrir nada.
    #
    #  REGRA DE OURO (anti-invenção): nada é deduzido. Só devolvemos número que
    #  foi lido de um rótulo reconhecido. Se não reconhecer, devolve vazio e diz
    #  o motivo. Uma leitura "POSIÇÃO 0" é informação legítima (você está zerado)
    #  e é justamente o que permite corrigir uma execução que não aconteceu.
    # Uma única passada no DOM devolve POSIÇÕES e PREÇO ao vivo. É chamada com
    # frequência (poller de segundos), então varre o documento uma vez só.
    #
    # Percorre também IFRAMES de mesma origem e SHADOW DOM: apps React como a
    # Tradovate escondem painéis aí dentro, e um querySelectorAll comum não
    # enxerga — foi por isso que o campo "POSIÇÃO", visível na tela, aparecia
    # como "0 rótulos" no diagnóstico.
    _JS_ESTADO = r"""
    (function(){
      function norm(s){
        return (s||'').toString().normalize('NFD').replace(/[̀-ͯ]/g,'')
               .toLowerCase().replace(/[^a-z0-9\/&% .-]/g,' ').replace(/\s+/g,' ').trim();
      }
      function num(s){
        if(s===null||s===undefined) return null;
        var t=s.toString().trim();
        if(t===''||t==='-'||t==='--'||t==='-.-'||t==='—') return null;
        if(!/[0-9]/.test(t)) return null;
        var neg=/^\(.*\)$/.test(t)||/^\s*-/.test(t);
        t=t.replace(/[()]/g,'').replace(/[^0-9.,-]/g,'');
        var ult=Math.max(t.lastIndexOf('.'), t.lastIndexOf(','));
        if(ult>-1){ t=t.slice(0,ult).replace(/[.,]/g,'')+'.'+t.slice(ult+1); }
        t=t.replace(/-/g,'');
        var v=parseFloat(t);
        if(isNaN(v)) return null;
        return neg?-v:v;
      }
      function txt(el){
        try{ return (el.innerText||el.textContent||'').trim(); }catch(e){ return ''; }
      }
      function vis(el){
        try{ var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
        catch(e){ return false; }
      }
      function folha(el){ try{ return el.children.length===0; }catch(e){ return false; } }

      // ---- Coleta TODOS os elementos, inclusive iframes e shadow DOM ----
      var TODOS=null;
      function todos(){
        if(TODOS) return TODOS;
        var res=[], raizes=[document];
        var ifr=[];
        try{ ifr=document.querySelectorAll('iframe,frame'); }catch(e){}
        for(var i=0;i<ifr.length;i++){
          try{ if(ifr[i].contentDocument) raizes.push(ifr[i].contentDocument); }catch(e){}
        }
        for(var r=0;r<raizes.length;r++){
          var pilha=[raizes[r]];
          var guarda=0;
          while(pilha.length && guarda++ < 400){
            var no=pilha.pop(), els=null;
            try{ els=no.querySelectorAll('*'); }catch(e){ continue; }
            for(var k=0;k<els.length;k++){
              res.push(els[k]);
              try{ if(els[k].shadowRoot) pilha.push(els[k].shadowRoot); }catch(e){}
            }
          }
        }
        TODOS=res;
        return res;
      }

      function ehSimbolo(t){
        if(!t) return false;
        t=t.toUpperCase().trim();
        if(t.length<3||t.length>8) return false;
        if(/^(WIN|WDO|IND|DOL)(FUT|[FGHJKMNQUVXZ][0-9]{1,2})$/.test(t)) return true;
        if(/^[A-Z0-9]{1,4}[FGHJKMNQUVXZ][0-9]{1,2}$/.test(t)) return true;
        if(/^[A-Z]{2,5}[0-9]{1,2}$/.test(t)) return true;
        return false;
      }
      function simboloEm(t){
        if(!t) return null;
        var toks=t.toUpperCase().split(/[\s |,;:()\/]+/);
        for(var i=0;i<toks.length;i++) if(ehSimbolo(toks[i])) return toks[i];
        return null;
      }

      // Rótulos VIZINHOS que têm número próprio e não podem ser confundidos com
      // o valor que procuramos. Sem isto, o robô lia "QUANTIDADE 1" (o tamanho
      // da ordem no ticket) achando que era "POSIÇÃO 1" — reportando posição
      // aberta com você zerado.
      var ROT_VIZINHOS=['quantidade','qty','quantity','qtd','tamanho','size',
                        'capital','conta','saldo','balance','equity','margem',
                        'margem diaria','margem inicial','preco de venda','compra',
                        'bid','ask','ultimo','last','volume'];
      function ehVizinhoProibido(t){ return ROT_VIZINHOS.indexOf(t)>-1; }

      // Acha o valor numérico associado a um rótulo (no próprio texto ou perto).
      // Procura do MAIS PERTO para o mais longe e nunca atravessa outro rótulo.
      function valorPerto(el, textoBruto, ehRotulo){
        var resto=textoBruto.replace(/^[^0-9+-]*/,'');
        if(resto && resto!==textoBruto){
          var v0=num(resto);
          if(v0!==null) return {valor:v0, el:el};
        }
        // 1) irmão imediatamente seguinte — o caso normal (<div>RÓTULO</div><div>0</div>)
        var irmao=el.nextElementSibling;
        for(var s=0; s<3 && irmao; s++){
          if(folha(irmao)){
            var it=txt(irmao);
            if(it && it.length<=24 && /^[-+(]?[0-9]/.test(it.trim())){
              var vi=num(it);
              if(vi!==null) return {valor:vi, el:irmao};
            }
            // Encontrou OUTRO rótulo antes do número: o valor não está por aqui.
            if(it && ehVizinhoProibido(norm(it))) break;
          }
          irmao=irmao.nextElementSibling;
        }
        // 2) sobe pelos containers, mas parando ao esbarrar em rótulo vizinho
        var cont=el.parentElement;
        for(var up=0; up<3 && cont; up++){
          var fl=null;
          try{ fl=cont.querySelectorAll('div,span,label,p,strong,b,td'); }catch(e){ break; }
          var bloqueado=false;
          for(var f=0; f<fl.length; f++){
            var fe=fl[f];
            if(!folha(fe)||fe===el) continue;
            var ft=txt(fe);
            if(!ft||ft.length>24) continue;
            var nf=norm(ft);
            if(ehRotulo(nf)) continue;
            // Bloco contaminado por outro campo numérico: não dá para saber de
            // quem é o número. Melhor subir do que chutar.
            if(ehVizinhoProibido(nf)){ bloqueado=true; break; }
            if(!/^[-+(]?[0-9]/.test(ft.trim())) continue;
            var v=num(ft);
            if(v!==null) return {valor:v, el:fe};
          }
          if(bloqueado) return null;
          cont=cont.parentElement;
        }
        return null;
      }

      var res={ok:false, motivo:'', estrategia:'', linhas:[], preco:null,
               diag:{amostras:[], textos_posi:[]}};

      // ================= PREÇO AO VIVO =================
      // Lê COMPRA/VENDA (bid/ask) do painel. É o preço EXATO da plataforma —
      // muito melhor que o preço lido da imagem pela IA.
      var ROT_BID=['compra','bid','melhor compra'];
      var ROT_ASK=['preco de venda','venda','ask','melhor venda'];
      function ehRotPreco(t){
        for(var i=0;i<ROT_BID.length;i++) if(t===ROT_BID[i]) return true;
        for(var j=0;j<ROT_ASK.length;j++) if(t===ROT_ASK[j]) return true;
        return false;
      }
      var bid=null, ask=null;
      var lista=todos();
      for(var n=0;n<lista.length;n++){
        var el=lista[n];
        if(!folha(el)) continue;
        var b=txt(el);
        if(!b||b.length>26) continue;
        var t=norm(b);
        var eBid=ROT_BID.indexOf(t)>-1, eAsk=ROT_ASK.indexOf(t)>-1;
        if(!eBid&&!eAsk) continue;
        if(!vis(el)) continue;
        var achado=valorPerto(el, b, ehRotPreco);
        if(!achado) continue;
        if(eBid && bid===null) bid=achado.valor;
        if(eAsk && ask===null) ask=achado.valor;
        if(bid!==null && ask!==null) break;
      }
      if(bid!==null && ask!==null && bid>0 && ask>0){
        res.preco=Math.round(((bid+ask)/2)*100)/100;
        res.diag.bid=bid; res.diag.ask=ask;
      } else if(bid!==null && bid>0){ res.preco=bid; res.diag.bid=bid; }
      else if(ask!==null && ask>0){ res.preco=ask; res.diag.ask=ask; }

      // ================= POSIÇÕES: grade =================
      var SIN={
        ativo:['symbol','contract','instrument','simbolo','ativo','produto'],
        qtd:['netpos','net pos','net position','position','pos','posicao',
             'qty','quantity','quantidade','contratos'],
        preco:['avg price','avgprice','avg px','avg. px','average price','avg',
               'preco medio','preco med','preco de entrada'],
        pnl:['p l','p/l','pl','p&l','pnl','open p l','open pl','abrir p/l',
             'abrir p l','p l aberto','profit','lucro','resultado']
      };
      function achaCol(cabs, chaves){
        for(var i=0;i<cabs.length;i++)
          for(var k=0;k<chaves.length;k++) if(cabs[i]===chaves[k]) return i;
        for(var i2=0;i2<cabs.length;i2++)
          for(var k2=0;k2<chaves.length;k2++)
            if(cabs[i2].indexOf(chaves[k2])>-1) return i2;
        return -1;
      }
      var grades=[];
      for(var g0=0; g0<lista.length; g0++){
        var tag=(lista[g0].tagName||'').toLowerCase();
        var papel='';
        try{ papel=lista[g0].getAttribute('role')||''; }catch(e){}
        if(tag==='table'||papel==='grid'||papel==='table') grades.push(lista[g0]);
      }
      res.diag.grades_encontradas=grades.length;
      for(var g=0; g<grades.length; g++){
        var grade=grades[g];
        if(!vis(grade)) continue;
        var cabEls=[];
        try{ cabEls=[].slice.call(grade.querySelectorAll('thead th,[role=columnheader],th')); }
        catch(e){ continue; }
        if(!cabEls.length) continue;
        var cabs=cabEls.map(function(e){return norm(txt(e));})
                       .filter(function(t){return t!=='';});
        if(cabs.length<2) continue;
        var iA=achaCol(cabs,SIN.ativo), iQ=achaCol(cabs,SIN.qtd);
        if(iA<0||iQ<0) continue;
        var iP=achaCol(cabs,SIN.preco), iL=achaCol(cabs,SIN.pnl);
        var out=[];
        var lg=[].slice.call(grade.querySelectorAll('tbody tr,[role=row]'));
        for(var i=0;i<lg.length;i++){
          var cels=[].slice.call(lg[i].querySelectorAll('td,[role=gridcell],[role=cell]'));
          if(cels.length<2) continue;
          var tt=cels.map(txt);
          var ativo=(tt[iA]||'').split('\n')[0].trim();
          var q=num(tt[iQ]);
          if(!ativo||q===null||!/[A-Za-z]/.test(ativo)) continue;
          out.push({ativo:ativo.slice(0,20), qtd_liquida:q,
                    preco_medio:iP>-1?num(tt[iP]):null,
                    pnl:iL>-1?num(tt[iL]):null, fonte:'grade'});
        }
        res.ok=true; res.estrategia='grade'; res.linhas=out;
        res.diag.cabecalhos=cabs;
        if(!out.length) res.motivo='grade de posicoes vazia (voce esta zerado)';
        return JSON.stringify(res);
      }

      // ================= POSIÇÕES: rótulo "POSIÇÃO" =================
      var ROT_POS=['posicao','position','net pos','netpos','posicao liquida'];
      function ehRotuloPos(t){
        if(!t) return false;
        for(var i=0;i<ROT_POS.length;i++){
          if(t===ROT_POS[i]) return true;
          if(t.indexOf(ROT_POS[i])===0 && t.length<=ROT_POS[i].length+12) return true;
        }
        return false;
      }

      // ---- LEITURA DO BLOCO INTEIRO DA POSIÇÃO ----------------------------
      // A Tradovate não desenha "POSIÇÃO" e o número em caixinhas separadas e
      // previsíveis: ela escreve tudo junto, no formato
      //     POSICAO 50@7730.00 62.50 USD          (comprado 50, médio 7730, +62.50)
      //     POSICAO 8@7756.00 (140.00) USD        (parênteses = PREJUÍZO)
      //     POSICAO 0 -.-- USD                    (zerado, sem P&L)
      // Procurar "o número ao lado do rótulo" quebrava nisso de duas formas:
      //   1) "50@7730.00" virava o número 507730 (o @ era descartado), que a
      //      trava de sanidade rejeitava — daí o "achei o rotulo POSICAO mas nao
      //      consegui ler o numero ao lado" que aparecia o pregão inteiro;
      //   2) o preço médio nunca era lido (ficava null fixo) e o P&L só era
      //      procurado no pai imediato da quantidade, que quase nunca o contém.
      // Sem preço médio E sem P&L, a posição era descartada como "leitura
      // duvidosa" — e o app concluía que você estava zerado, devolvendo para
      // PENDENTE uma ordem que já tinha executado.
      // Ler o bloco inteiro com regex resolve os três formatos de uma vez.
      function blocoDoRotulo(el){
        var c=el, melhor=null;
        for(var i=0;i<6 && c;i++){
          var t=txt(c);
          if(t && t.length<=90 && /[0-9]/.test(t) && /posi|position|net ?pos/i.test(t)){
            melhor=t;   // o MENOR ancestral que já tem rótulo + número
            break;
          }
          c=c.parentElement;
        }
        return melhor;
      }
      // Devolve {qtd, preco, pnl} — cada campo só vem preenchido quando foi
      // realmente lido. Nada é deduzido: o que não der para ler volta null.
      // Um número "de dinheiro": no máximo 2 casas decimais, com separador de
      // milhar opcional. O limite de 2 casas é o que impede o parser de engolir
      // dois números colados — a tela às vezes vem sem espaço entre eles
      // ("7756.0070.00" é preço 7756.00 seguido de P&L 70.00, não 77.560.070).
      var NUMP='(?:[0-9]{1,3}(?:,[0-9]{3})+(?:\\.[0-9]{1,2})?|[0-9]+(?:[.,][0-9]{1,2})?)';
      function parseBlocoPos(t){
        if(!t) return null;
        var r={qtd:null, preco:null, pnl:null};
        var limpo=t.replace(/\s+/g,' ');
        // a) "50@7730.00" -> quantidade E preço médio de uma vez.
        var mq=limpo.match(new RegExp('(-?[0-9]{1,4})\\s*@\\s*('+NUMP+')'));
        if(mq){
          r.qtd=parseFloat(mq[1]);
          var p=num(mq[2]);
          if(p!==null && p>0) r.preco=p;
          // Tira do texto o trecho já consumido, para o P&L não reaproveitar
          // esses mesmos dígitos quando vierem grudados.
          limpo=limpo.replace(mq[0],' ');
        } else {
          // b) sem @: o primeiro número depois do rótulo é a quantidade.
          var ms=limpo.match(/(?:posi[cç][aã]o|position|net ?pos)\s*:?\s*(-?[0-9]{1,4})(?![0-9.,])/i);
          if(ms) r.qtd=parseFloat(ms[1]);
        }
        // c) P&L: número colado em USD/$ — parênteses significam PREJUÍZO.
        //    "-.--" é a plataforma dizendo "não há", e não o número zero.
        var mp=limpo.match(new RegExp('(\\(?\\s*-?'+NUMP+'\\s*\\)?)\\s*(?:USD|\\$|R\\$)','i'));
        if(mp){
          var bruto2=mp[1].trim();
          var negativo=/^\(/.test(bruto2);
          var v=num(bruto2.replace(/[()]/g,''));
          if(v!==null) r.pnl=negativo?-Math.abs(v):v;
        }
        if(r.qtd!==null && (Math.abs(r.qtd)>1000 ||
            Math.abs(r.qtd-Math.round(r.qtd))>1e-9)) r.qtd=null;
        return r;
      }

      var achados=[], vistos=0;
      for(var m=0;m<lista.length;m++){
        var e2=lista[m];
        if(!folha(e2)) continue;
        var bruto=txt(e2);
        if(!bruto||bruto.length>40) continue;
        var t2=norm(bruto);
        // Diagnóstico: guarda QUALQUER texto que fale de posição, mesmo que o
        // formato não bata — é assim que se descobre o rótulo real da tela.
        if(t2.indexOf('posi')>-1 && res.diag.textos_posi.length<15)
          res.diag.textos_posi.push(bruto.slice(0,40));
        if(!ehRotuloPos(t2)) continue;
        if(!vis(e2)) continue;
        vistos++;
        if(res.diag.amostras.length<12){
          var pai=e2.parentElement;
          res.diag.amostras.push({rotulo:bruto.slice(0,40),
            pai:(pai?txt(pai):'').replace(/\s+/g,' ').slice(0,120)});
        }
        // Lê o bloco inteiro ANTES de tentar o vizinho: é ele que traz o preço
        // médio e o P&L, que a busca por vizinho nunca alcançava.
        var pb=parseBlocoPos(blocoDoRotulo(e2));
        var ach=valorPerto(e2, bruto, ehRotuloPos);
        // SANIDADE: posição é contagem de CONTRATOS — inteiro e pequeno.
        // Sem isto o robô lia o PREÇO vizinho (ex.: 7614.75) como se fosse a
        // quantidade da posição. Preço nunca é posição.
        var q=ach?ach.valor:null;
        if(q!==null && (Math.abs(q)>1000 || Math.abs(q-Math.round(q))>1e-9)) q=null;
        // O bloco manda quando o vizinho não deu um número aproveitável — é o
        // caso de "50@7730.00", em que o vizinho vira 507730 e é descartado.
        if(q===null && pb && pb.qtd!==null) q=pb.qtd;
        if(q===null) continue;
        var simbolo=null, c2=e2.parentElement;
        for(var u2=0; u2<8 && c2 && !simbolo; u2++){
          var cand=[];
          try{ cand=c2.querySelectorAll('div,span,label,p,h1,h2,h3,strong,b,a'); }catch(e){}
          for(var q2=0; q2<cand.length; q2++){
            var ce=cand[q2];
            if(!folha(ce)) continue;
            var s=simboloEm(txt(ce).split('\n')[0]);
            if(s){ simbolo=s; break; }
          }
          c2=c2.parentElement;
        }
        if(!simbolo) simbolo=simboloEm(document.title);
        // P&L da POSIÇÃO: só vale se estiver no MESMO bloco do campo POSIÇÃO.
        // Subir mais níveis fazia o robô pegar o CAPITAL DA CONTA (ex.: "106,040.57
        // USD" da barra do topo) e reportar como resultado da operação — número
        // completamente errado. Fica restrito ao container imediato.
        var ROT_CONTA=['capital','conta','saldo','balance','equity','margem',
                       'margem diaria','margem inicial'];
        var pnl=null, c3=(ach&&ach.el)?ach.el.parentElement:e2.parentElement;
        if(c3){
          var fl3=[];
          try{ fl3=c3.querySelectorAll('div,span,label,p,strong,b,td'); }catch(e){}
          // Se o bloco fala de capital/conta, não é P&L de posição: ignora.
          var blocoDeConta=false;
          for(var w3=0; w3<fl3.length; w3++){
            if(ROT_CONTA.indexOf(norm(txt(fl3[w3])))>-1){ blocoDeConta=true; break; }
          }
          if(!blocoDeConta){
            for(var y=0; y<fl3.length; y++){
              var ye=fl3[y];
              if(!folha(ye)||(ach&&ye===ach.el)||ye===e2) continue;
              var yt=txt(ye);
              if(!yt||yt.length>24) continue;
              if(/usd|\$|r\$/i.test(yt)){
                // "-.--" é ausência de valor, não zero.
                if(!/[0-9]/.test(yt)) continue;
                var negY=/^\(/.test(yt.trim());
                var pv=num(yt.replace(/[()]/g,''));
                if(pv!==null){ pnl=negY?-Math.abs(pv):pv; break; }
              }
            }
          }
        }
        // O bloco completa o que faltou. Preço médio SÓ vem daqui (a busca por
        // vizinho nunca o enxergava) e o P&L do bloco entra quando o vizinho não
        // achou nada. Nenhum dos dois é estimado: ou foi lido, ou fica null.
        var precoMed=(pb && pb.preco!==null)?pb.preco:null;
        if(pnl===null && pb && pb.pnl!==null) pnl=pb.pnl;
        achados.push({ativo:simbolo, qtd_liquida:q, preco_medio:precoMed,
                      pnl:pnl, fonte:'rotulo'});
      }
      res.diag.rotulos_posicao=vistos;
      res.diag.total_elementos=lista.length;

      if(achados.length){
        var mapa={}, semSimbolo=[];
        for(var a=0;a<achados.length;a++){
          var it=achados[a];
          if(!it.ativo){ semSimbolo.push(it); continue; }
          var ant=mapa[it.ativo];
          if(!ant){ mapa[it.ativo]=it; continue; }
          // Mesmo ativo aparecendo em dois cantos da tela (o painel desenha o
          // rótulo duas vezes): junta o melhor de cada leitura em vez de
          // descartar a que veio incompleta. Antes, a segunda leitura sem P&L
          // apagava o P&L que a primeira tinha lido.
          if(ant.qtd_liquida===0 && it.qtd_liquida!==0) ant.qtd_liquida=it.qtd_liquida;
          if(ant.pnl===null && it.pnl!==null) ant.pnl=it.pnl;
          if(ant.preco_medio===null && it.preco_medio!==null) ant.preco_medio=it.preco_medio;
        }
        res.linhas=Object.keys(mapa).map(function(k){return mapa[k];});
        if(!res.linhas.length && semSimbolo.length){
          var melhor=semSimbolo[0];
          for(var z=1;z<semSimbolo.length;z++)
            if(semSimbolo[z].qtd_liquida!==0) melhor=semSimbolo[z];
          res.linhas=[melhor];
        }
        res.ok=true; res.estrategia='rotulo';
        var abertas=res.linhas.filter(function(l){return l.qtd_liquida!==0;});
        if(!abertas.length) res.motivo='li o campo POSICAO: voce esta zerado';
        return JSON.stringify(res);
      }

      res.motivo = vistos
        ? 'achei o rotulo POSICAO ('+vistos+'x) mas nao consegui ler o numero ao lado'
        : 'nao achei grade de posicoes nem o campo POSICAO na tela';
      return JSON.stringify(res);
    })()
    """

    def ler_estado(self):
        """UMA passada no DOM devolvendo preço ao vivo + posições abertas."""
        try:
            bruto = self.avaliar_js(self._JS_ESTADO)
            return json.loads(bruto or "{}")
        except ConexaoPerdida as e:
            return {"ok": False, "motivo": str(e), "linhas": [], "preco": None,
                    "conexao_perdida": True}
        except Exception as e:
            return {"ok": False, "motivo": str(e), "linhas": [], "preco": None}

    def ler_preco(self):
        """Preço ao vivo (média bid/ask) direto do painel. None se não der.
        É o preço EXATO da plataforma — não passa por leitura de imagem."""
        d = self.ler_estado() or {}
        if d.get("conexao_perdida"):
            raise ConexaoPerdida(d.get("motivo", "conexão caiu"))
        preco = d.get("preco")
        try:
            preco = float(preco)
        except (TypeError, ValueError):
            return None
        return preco if preco > 0 else None

    def ler_posicoes(self):
        """Posições abertas. ok=False = não consegui ler com segurança."""
        d = self.ler_estado() or {}
        if not d.get("ok") and not d.get("conexao_perdida"):
            self.log(f"ℹ️ Posições: {d.get('motivo', 'leitura falhou')}.")
        return d

    def diagnosticar_posicoes(self):
        """Dump do que a leitura enxerga. Se a detecção não pegar na SUA tela,
        rode isto e me mande o resultado — com ele eu acerto sem chutar."""
        dados = self.ler_estado() or {}
        diag = dados.get("diag") or {}
        self.log("──── DIAGNÓSTICO DA LEITURA (posições + preço) ────")
        self.log(f"  leitura ok .........: {dados.get('ok')}")
        self.log(f"  estratégia .........: {dados.get('estrategia') or '(nenhuma)'}")
        self.log(f"  motivo .............: {dados.get('motivo') or '(sem observação)'}")
        self.log(f"  elementos varridos .: {diag.get('total_elementos', '?')} "
                 "(inclui iframes e shadow DOM)")
        self.log(f"  grades na tela .....: {diag.get('grades_encontradas', '?')}")
        self.log(f"  rótulos 'POSIÇÃO' ..: {diag.get('rotulos_posicao', 0)}")
        self.log(f"  PREÇO ao vivo ......: {dados.get('preco')} "
                 f"(compra {diag.get('bid')} / venda {diag.get('ask')})")
        if diag.get("cabecalhos"):
            self.log(f"  colunas ............: {diag['cabecalhos']}")
        textos = diag.get("textos_posi") or []
        if textos:
            self.log("  textos com 'posi' na tela (é aqui que se descobre o rótulo real):")
            for t in textos:
                self.log(f"    · {t!r}")
        for am in (diag.get("amostras") or []):
            self.log(f"  ↳ rótulo: {am.get('rotulo')!r} | contexto: {am.get('pai')!r}")
        linhas = dados.get("linhas") or []
        if not linhas:
            self.log("  linhas .............: nenhuma")
        for ln in linhas:
            self.log(f"  • {ln.get('ativo') or '(ativo não identificado)'}: "
                     f"qtd={ln.get('qtd_liquida')} preço_médio={ln.get('preco_medio')} "
                     f"pnl={ln.get('pnl')} (via {ln.get('fonte')})")
        self.log("────────────────────────────────────────────")
        return dados


    def _formulario_visivel(self):
        """True se o FORMULÁRIO de ordem está à vista. Indicador confiável: o
        botão 'Enviar' só existe no formulário — no comprovante da ordem ele
        some. (Comprar/Vender não servem: o comprovante de uma venda deixa um
        texto 'Vender' na tela e dava falso-positivo.)"""
        return bool(self.localizar("Enviar"))

    def _garantir_formulario(self, tentativas=5):
        """Garante que o FORMULÁRIO do 'Chamado do pedido' está à vista.

        Há DOIS motivos possíveis para ele não estar, e eles pedem ações
        diferentes — antes o robô dizia sempre "comprovante à vista", o que
        confundia quando o ticket simplesmente não estava aberto:
          a) está no COMPROVANTE da última ordem  -> basta clicar na setinha ←;
          b) o ticket NÃO ESTÁ ABERTO na tela     -> só VOCÊ pode abrir.
        """
        for i in range(tentativas):
            estado = self.estado_ticket()
            if estado == "formulario":
                if i > 0:
                    self.log("   ✅ formulário de ordem de volta à vista.")
                return True
            if estado == "ausente":
                # Depois de ENVIAR, a Tradovate leva um instante para desenhar o
                # comprovante. Nas primeiras voltas damos esse tempo em vez de
                # concluir logo que o ticket "não está aberto".
                if i < 2:
                    time.sleep(0.7)
                    continue
                self.log("   ❌ o painel 'Chamado do pedido' NÃO está aberto na "
                         "Tradovate (não é comprovante — o ticket não está na "
                         "tela). Abra o ticket na plataforma e deixe-o visível; "
                         "sem ele o robô não tem onde digitar a ordem.")
                return False
            self.log(f"   ↩️ comprovante à vista — voltando ao formulário "
                     f"(tentativa {i + 1}/{tentativas})...")
            self.voltar_ticket()
            time.sleep(0.7)
        ok = self.estado_ticket() == "formulario"
        if not ok:
            self.log("   ❌ não consegui voltar ao formulário do ticket. Clique na "
                     "setinha ← do 'Chamado do pedido' e tente de novo.")
        return ok

    def enviar_ordem_ticket(self, preco, direcao, tipo="LIMITE", qtd=None,
                            enviar=False, pausa=0.45):
        """Preenche UMA ordem no 'Chamado do pedido'. Se enviar=False (padrão),
        só preenche pra você conferir na tela — NÃO clica em Enviar."""
        long_ = str(direcao).upper() in ("BUY", "COMPRA", "COMPRAR", "C", "LONG")
        palavra_dir = "Comprar" if long_ else "Vender"
        modo = "ENVIAR" if enviar else "SÓ PREENCHER (confira na tela)"
        self.log(f"🧾 Ordem [{modo}]: {palavra_dir} {tipo} @ {preco}"
                 + (f"  x{qtd}" if qtd else ""))
        if enviar and (qtd is None):
            self.log("   ⚠️ QTD é obrigatória pra ENVIAR (o Tradovate recusa sem "
                     "quantidade). Informe a quantidade.")
            return False
        # 0) garante que o formulário está à vista (após uma ordem, o painel vira
        #    comprovante e precisa do ← para voltar).
        if not self._garantir_formulario():
            self.log("   ❌ formulário do 'Chamado do pedido' não está visível. "
                     "Abra o ticket na Tradovate.")
            return False
        # 1) direção
        d = self.localizar(palavra_dir)
        if not d:
            # Diagnóstico: mostra o que ESTÁ detectável, pra facilitar ajuste.
            achou = self._achar_por_texto(["Comprar", "Vender", "Enviar",
                                           "LIMITE", "PARAR", "MERCADO"])
            self.log(f"   ❌ não achei o botão '{palavra_dir}'. Detectáveis agora: "
                     f"{list(achou.keys())}")
            return False
        # Clicar Comprar/Vender e preencher campos é seguro (não envia a ordem);
        # só o botão "Enviar" no fim é que dispara. Por isso preenchemos de
        # verdade mesmo em dry-run, pra você VER o formulário preenchido.
        self.clicar_pagina(d["x"], d["y"])
        time.sleep(pausa)
        # 2) tipo (best-effort)
        if tipo:
            self._selecionar_tipo(tipo, pausa)
        # 3) preço (sempre preenche — é seguro, só escreve no campo)
        r = self.definir_campo_ticket("preco", preco)
        if r != "OK":
            self.log(f"   ❌ campo de preço não encontrado ({r}).")
            return False
        self.log(f"   ✏️ preço {preco} preenchido.")
        time.sleep(pausa)
        # 4) qtd
        if qtd is not None:
            self.definir_campo_ticket("qtd", int(qtd))
            self.log(f"   ✏️ qtd {int(qtd)} preenchida.")
            time.sleep(pausa)
        # 5) enviar (só no modo real)
        if enviar:
            e = self.localizar("Enviar")
            if not e:
                self.log("   ❌ botão 'Enviar' não encontrado.")
                return False
            self.clicar_pagina(e["x"], e["y"])
            self.log("   ✅ Enviar clicado.")
        else:
            self.log("   👀 Preenchido (não enviei). Confira e mande '!' pra enviar.")
        return True

    def enviar_bracket_ticket(self, direcao, entrada, stop, alvo, qtd=None,
                              enviar=False, pausa=0.7):
        """Coloca a estrutura completa com PREÇOS EXATOS do SMC via ticket:
          LONG : entrada Comprar/LIMITE · stop Vender/STOP · alvo Vender/LIMITE
          SHORT: entrada Vender/LIMITE  · stop Comprar/STOP · alvo Comprar/LIMITE
        """
        long_ = str(direcao).upper() in ("BUY", "COMPRA", "COMPRAR", "C", "LONG")
        dir_entrada = "Comprar" if long_ else "Vender"
        dir_prot = "Vender" if long_ else "Comprar"
        plano = [("ENTRADA", entrada, dir_entrada, "LIMITE"),
                 ("STOP",    stop,    dir_prot,    "STOP"),
                 ("ALVO",    alvo,    dir_prot,    "LIMITE")]
        self.log(f"📦 Bracket {'LONG' if long_ else 'SHORT'} via ticket "
                 f"[{'ENVIAR' if enviar else 'dry'}]  qtd={qtd}")
        resultado = {"ok": True, "enviadas": [], "faltando": [], "erro": None,
                     "exposto": False}
        if enviar and (qtd is None):
            self.log("   ⚠️ QTD é obrigatória pra ENVIAR o bracket. Informe a quantidade.")
            resultado["ok"] = False
            resultado["erro"] = "quantidade não informada"
            resultado["faltando"] = [n for n, p, _, _ in plano if p is not None]
            return resultado

        for nome, preco, dirr, tipo in plano:
            if preco is None:
                continue
            self.log(f" • {nome}")
            # A PROTEÇÃO NÃO PODE DESISTIR NA PRIMEIRA TENTATIVA. No pregão, a
            # ENTRADA saiu e o STOP não, três vezes seguidas, porque o robô
            # tentava voltar ao formulário uma única vez e desistia — com a
            # ordem já no mercado. Stop e alvo agora têm três rodadas completas
            # (cada uma com todas as rotas de volta ao formulário), com pausa
            # crescente para dar tempo de a Tradovate redesenhar o painel.
            tentativas = 3 if (enviar and nome in ("STOP", "ALVO")) else 1
            perna_ok = False
            for t in range(tentativas):
                if t:
                    espera = 1.5 * t
                    self.log(f"   🔁 {nome}: nova tentativa ({t + 1}/{tentativas}) "
                             f"em {espera:.1f}s — a proteção não pode ficar de fora.")
                    time.sleep(espera)
                try:
                    perna_ok = self.enviar_ordem_ticket(preco, dirr, tipo, qtd, enviar)
                except ConexaoPerdida as e:
                    perna_ok = False
                    resultado["erro"] = str(e)
                    self.log(f"   ❌ {nome}: a conexão com o Chrome caiu ({e}).")
                    break        # sem Chrome, repetir não adianta
                except Exception as e:
                    perna_ok = False
                    resultado["erro"] = str(e)
                    self.log(f"   ❌ {nome}: falhou ({e}).")
                if perna_ok:
                    break

            if perna_ok:
                resultado["enviadas"].append(nome)
            else:
                resultado["ok"] = False
                resultado["faltando"].append(nome)
                if nome == "ENTRADA":
                    # Sem entrada não existe posição — mandar stop/alvo agora
                    # criaria ordens soltas na plataforma. Aborta o resto.
                    resultado["faltando"] += [n for n, p, _, _ in plano
                                               if p is not None and n != "ENTRADA"]
                    self.log("   ⛔ ENTRADA não foi enviada — abortei stop e alvo "
                             "para não deixar ordens soltas na plataforma.")
                    break
            time.sleep(pausa)

        # RISCO REAL: a entrada foi para o mercado mas a proteção não. Isso é
        # posição a descoberto — precisa gritar, não passar em silêncio.
        if enviar and "ENTRADA" in resultado["enviadas"] and resultado["faltando"]:
            resultado["exposto"] = True
            resultado["sem_stop"] = "STOP" in resultado["faltando"]
            self.log("🚨 ATENÇÃO: a ENTRADA foi enviada, mas "
                     f"{' e '.join(resultado['faltando'])} NÃO. Se essa ordem for "
                     "executada, a posição fica SEM PROTEÇÃO. Coloque "
                     "stop/alvo na mão na plataforma AGORA.")
            if resultado["sem_stop"]:
                # Sem stop é o cenário que quebra conta. A ordem de entrada é
                # LIMITADA e ainda não foi preenchida: cancelá-la na plataforma
                # elimina o risco por completo. Não faço isso por conta própria
                # porque cancelar mexe nas ordens da corretora — inclusive as que
                # você lançou na mão. Fica no seu comando.
                self.log("   ⛑️ SAÍDA SEGURA: enquanto a entrada não for "
                         "preenchida, o risco é zero. Cancele a ordem de entrada "
                         f"em {plano[0][1]} na Tradovate, ou coloque o stop em "
                         f"{stop} na mão — o que for mais rápido.")
        else:
            self.log("📦 Bracket concluído." if resultado["ok"]
                     else "📦 Bracket NÃO foi enviado por completo.")
        return resultado

    # --------------------------- Calibração -----------------------------
    #  Precisamos saber a que altura (Y da página) fica cada preço. Em vez de
    #  adivinhar pixels, deixamos VOCÊ clicar em 2 preços conhecidos: a própria
    #  página do Chrome captura o clientX/clientY do seu clique (mesmo sistema de
    #  coordenadas que o CDP usa pra clicar). Assim o mapa fica exato e sem
    #  bagunça de DPI/posição de janela.
    def armar_captura_clique(self):
        """Instala um listener que guarda o PRÓXIMO clique seu na página."""
        self.avaliar_js(
            "window.__smc_calib=null;"
            "document.addEventListener('click',function h(e){"
            "window.__smc_calib={x:e.clientX,y:e.clientY};"
            "document.removeEventListener('click',h,true);},true);"
            "true"
        )

    def ler_captura_clique(self, timeout=60):
        """Espera você clicar; devolve (x, y) do clique na página."""
        limite = time.time() + timeout
        while time.time() < limite:
            v = self.avaliar_js("window.__smc_calib && JSON.stringify(window.__smc_calib)")
            if v:
                d = json.loads(v)
                return d["x"], d["y"]
            time.sleep(0.3)
        return None

    def definir_calibracao(self, preco1, y1, preco2, y2, x_click):
        self.calib = {"p1": float(preco1), "y1": float(y1),
                      "p2": float(preco2), "y2": float(y2), "x_click": float(x_click)}
        if self.arquivo_calib:
            self.salvar_calibracao(self.arquivo_calib)

    def preco_para_y(self, preco):
        """Interpolação linear preço -> Y da página."""
        if not self.calib:
            raise RuntimeError("Sem calibração. Calibre 2 preços primeiro.")
        c = self.calib
        if c["p2"] == c["p1"]:
            raise RuntimeError("Calibração inválida: os 2 preços são iguais.")
        m = (c["y2"] - c["y1"]) / (c["p2"] - c["p1"])
        return c["y1"] + m * (float(preco) - c["p1"])

    def clicar_preco(self, preco, dry_run=False):
        """Clica na altura de um preço, na coluna X calibrada."""
        y = self.preco_para_y(preco)
        self.log(f"→ preço {preco} = y {y:.0f}")
        self.clicar_pagina(self.calib["x_click"], y, dry_run=dry_run)

    # --------------------------- Bracket --------------------------------
    def enviar_bracket(self, direcao, entrada, stop, alvo, dry_run=True, pausa=0.6):
        """Posiciona a estrutura entrada + stop + alvo clicando em cada altura.

        ⚠️ A SEQUÊNCIA EXATA de cliques que a Tradovate exige (onde clicar pra
        virar LIMIT/STOP, se a estratégia ATM já anexa stop/alvo, etc.) você
        ajusta AQUI depois de testar o clique cru no gráfico. O motor de clique
        (clicar_preco) já está pronto e é a parte difícil; esta função é só o
        roteiro, propositalmente simples pra você afinar.
        """
        if not self.calib:
            self.log("❌ Calibre antes de enviar ordem.")
            return False
        modo = "SIMULAÇÃO (dry-run)" if dry_run else "REAL (clicando)"
        self.log(f"📦 Bracket {direcao} — {modo}")
        self.log(f"   entrada={entrada}  stop={stop}  alvo={alvo}")
        etapas = [("ENTRADA", entrada), ("STOP", stop), ("ALVO", alvo)]
        for nome, preco in etapas:
            if preco is None:
                continue
            self.log(f" • {nome} @ {preco}")
            self.clicar_preco(preco, dry_run=dry_run)
            time.sleep(pausa)
        self.log("📦 Bracket concluído." if not dry_run else "📦 Bracket (dry-run) concluído.")
        return True

    # ------------------------- Persistência -----------------------------
    def salvar_calibracao(self, caminho):
        try:
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(self.calib, f, indent=2)
        except Exception as e:
            self.log(f"⚠️ Falha ao salvar calibração: {e}")

    def carregar_calibracao(self, caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                self.calib = json.load(f)
        except Exception:
            self.calib = None
        return self.calib


# ============================================================================
#  Abre um Chrome dedicado com a porta de depuração ligada, já na Tradovate.
#  Usa um perfil SEPARADO pra não interferir no seu Chrome do dia a dia.
# ============================================================================
def abrir_chrome_debug(porta=PORTA_DEBUG_PADRAO, url="https://trader.tradovate.com",
                       perfil_dir=None, chrome_path=None, log=print):
    if perfil_dir is None:
        perfil_dir = os.path.join(os.path.expanduser("~"), ".smc_tradovate_chrome")
    candidatos = [chrome_path] if chrome_path else [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     r"Google\Chrome\Application\chrome.exe"),
    ]
    exe = next((c for c in candidatos if c and os.path.exists(c)), None)
    if not exe:
        log("❌ chrome.exe não encontrado. Informe o caminho em chrome_path=.")
        return None
    # FLAGS ANTI-CONGELAMENTO (essenciais para a captura em 2º plano):
    #   Por padrão o Chrome PARA de renderizar uma janela que está atrás de
    #   outras (occlusion detection) ou em segundo plano — e aí o PrintWindow
    #   devolve um quadro CONGELADO, o que fazia o robô dizer "não consigo ver
    #   o gráfico" mesmo com a janela aberta. Estas flags mantêm o Chrome
    #   renderizando sempre, então dá pra capturar a janela mesmo coberta por
    #   outras, sem precisar trazê-la pra frente (logo, sem roubar o foco).
    flags_anti_congelamento = [
        "--disable-features=CalculateNativeWinOcclusion",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
    ]
    args = [exe, f"--remote-debugging-port={porta}",
            f"--user-data-dir={perfil_dir}", *flags_anti_congelamento,
            "--new-window", url]
    log(f"🌐 Abrindo Chrome de depuração (porta {porta}) — modo sempre-renderizando...")
    return subprocess.Popen(args)


# ============================================================================
#  Entradas de terminal à prova de erro (não quebram com ENTER vazio, aceitam
#  vírgula como separador decimal e tratam Ctrl+Z/EOF sem estourar traceback).
# ============================================================================
def _ler_texto(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return None

def _ler_float(prompt):
    """Repergunta até vir um número válido. ENTER vazio -> repergunta.
    Aceita vírgula (7588,5) além de ponto. EOF -> devolve None (aborta)."""
    while True:
        txt = _ler_texto(prompt)
        if txt is None:
            return None
        if not txt:
            print("  (vazio) digite um número, ex: 7590")
            continue
        try:
            return float(txt.replace(",", "."))
        except ValueError:
            print(f"  '{txt}' não é um número válido. Ex: 7590 ou 7588.5")

def _ler_sim_nao(prompt, padrao=False):
    txt = _ler_texto(prompt)
    if not txt:
        return padrao
    return txt.lower() in ("s", "sim", "y", "yes")


# ============================================================================
#  ASSISTENTE DE TESTE ISOLADO  —  python tradovate_auto.py
# ============================================================================
def _assistente():
    print("=" * 68)
    print(" SMC QUANT PRO — teste de automação Tradovate (clique em 2º plano)")
    print("=" * 68)
    calib_path = os.path.join(os.path.expanduser("~"), ".smc_tradovate_calib.json")
    bot = TradovateAuto(arquivo_calib=calib_path)

    if not bot.chrome_ligado():
        print("\nChrome de depuração não está aberto.")
        if _ler_sim_nao("Abrir agora (Chrome dedicado na Tradovate)? [s/N] "):
            abrir_chrome_debug()
            print("→ Faça login na Tradovate nessa janela e deixe o gráfico visível.")
            _ler_texto("Quando estiver pronto, aperte ENTER... ")

    if not bot.conectar():
        return

    if bot.calib:
        print(f"\nCalibração existente encontrada: {bot.calib}")
        if _ler_sim_nao("Recalibrar? [s/N] "):
            bot.calib = None

    if not bot.calib:
        print("\n--- CALIBRAÇÃO (2 preços conhecidos no gráfico) ---")
        pontos = []
        for i in (1, 2):
            preco = _ler_float(f"[{i}/2] Digite um preço visível no gráfico e ENTER: ")
            if preco is None:
                print("      Abortado.")
                return
            print(f"      Agora CLIQUE exatamente na linha/altura do preço {preco} no gráfico...")
            bot.armar_captura_clique()
            xy = bot.ler_captura_clique()
            if not xy:
                print("      ⏱️ Não capturei o clique. Abortando.")
                return
            print(f"      capturado: x={xy[0]} y={xy[1]}")
            pontos.append((preco, xy))
        if pontos[0][0] == pontos[1][0]:
            print("      ❌ Os 2 preços são iguais — impossível calibrar. Rode de novo.")
            return
        x_click = round((pontos[0][1][0] + pontos[1][1][0]) / 2)
        bot.definir_calibracao(pontos[0][0], pontos[0][1][1],
                               pontos[1][0], pontos[1][1][1], x_click)
        print(f"✅ Calibrado e salvo em {calib_path}")

    print("\n--- TESTE ---  (abra o 'Chamado do pedido' na Tradovate)")
    print("Comandos:")
    print("  inspect                                   -> dump do formulário (me envie)")
    print("  ordem <preço> <buy|sell> [limit|stop] [qtd] -> PREENCHE o ticket (não envia)")
    print("  !ordem <preço> <buy|sell> [limit|stop] <qtd> -> preenche e clica ENVIAR")
    print("  bracket <buy|sell> <ent> <stop> <alvo> [qtd] -> preenche as 3 ordens")
    print("  !bracket <buy|sell> <ent> <stop> <alvo> <qtd> -> envia as 3 ordens")
    print("  <preço> / !<preço>                        -> clique cru na altura (Opção A)")
    print("  sair    (dica: STOP no seu Tradovate = 'PARAR')")
    while True:
        entrada = _ler_texto("cmd> ")
        if entrada is None or entrada.lower() in ("sair", "q", "exit"):
            break
        if not entrada:
            continue

        real = entrada.startswith("!")
        corpo = entrada[1:].strip() if real else entrada
        partes = corpo.split()
        cmd = partes[0].lower() if partes else ""

        if cmd in ("inspect", "inspecionar", "ticket"):
            print("\n----- ESTRUTURA DO 'CHAMADO DO PEDIDO' (copie e me envie) -----")
            print(json.dumps(bot.inspecionar_ticket(), ensure_ascii=False, indent=2))
            print("----- fim -----\n")
            continue

        if cmd == "ordem":
            try:
                preco = float(partes[1].replace(",", "."))
                direcao = partes[2]
                tipo = "LIMITE"
                qtd = None
                # partes[3] e partes[4] podem ser tipo e/ou qtd, em qualquer ordem
                for p in partes[3:5]:
                    if p.isdigit():
                        qtd = int(p)
                    else:
                        tipo = p.upper()
            except (IndexError, ValueError):
                print("  uso: ordem <preço> <buy|sell> [limit|stop] [qtd]")
                continue
            bot.enviar_ordem_ticket(preco, direcao, tipo, qtd=qtd, enviar=real)
            continue

        if cmd == "bracket":
            try:
                direcao = partes[1]
                ent = float(partes[2].replace(",", "."))
                stop = float(partes[3].replace(",", "."))
                alvo = float(partes[4].replace(",", "."))
                qtd = int(partes[5]) if len(partes) > 5 else None
            except (IndexError, ValueError):
                print("  uso: bracket <buy|sell> <entrada> <stop> <alvo> [qtd]")
                continue
            bot.enviar_bracket_ticket(direcao, ent, stop, alvo, qtd=qtd, enviar=real)
            continue

        # senão: clique cru na altura de um preço (Opção A)
        try:
            preco = float(corpo.replace(",", "."))
        except ValueError:
            print("  comando inválido. Veja a lista acima.")
            continue
        bot.clicar_preco(preco, dry_run=not real)

    bot.desconectar()
    print("Encerrado.")


if __name__ == "__main__":
    _assistente()
