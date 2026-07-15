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
        """Envia um comando CDP e espera a resposta com o mesmo id."""
        if not self.ws:
            raise RuntimeError("CDP não conectado (chame conectar() antes).")
        meu_id = self._proximo_id
        self._proximo_id += 1
        self.ws.enviar(json.dumps({"id": meu_id, "method": metodo, "params": params or {}}))
        limite = time.time() + timeout
        while time.time() < limite:
            msg = json.loads(self.ws.receber())
            if msg.get("id") == meu_id:      # resposta do nosso comando
                if "error" in msg:
                    raise RuntimeError(f"CDP {metodo}: {msg['error']}")
                return msg.get("result", {})
            # senão é um evento assíncrono — ignoramos.
        raise TimeoutError(f"Sem resposta do CDP para {metodo}.")

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

    def voltar_ticket(self, dry_run=False):
        """Clica na setinha ← do topo do 'Chamado do pedido' para voltar do
        comprovante da ordem de volta ao FORMULÁRIO. Necessário entre as ordens
        do bracket (depois de enviar, o painel vira comprovante)."""
        js = """
        (function(){
          var cands=[].slice.call(
            document.querySelectorAll('svg,button,[role=button],i,a,span,div'));
          var best=null;
          for(var k=0;k<cands.length;k++){var el=cands[k];
            var r=el.getBoundingClientRect();
            if(r.width<=0||r.height<=0) continue;
            var cx=r.x+r.width/2, cy=r.y+r.height/2;
            // ícone pequeno, no topo-esquerdo do painel do ticket
            if(cx<60 && cy>185 && cy<255 && r.width<=44 && r.height<=44){
              var a=r.width*r.height;
              if(!best||a<best.a){best={a:a,x:Math.round(cx),y:Math.round(cy)};}
            }
          }
          return best?JSON.stringify(best):'';
        })()
        """
        v = self.avaliar_js(js)
        if not v:
            self.log("   ⚠️ setinha ← não encontrada.")
            return False
        d = json.loads(v)
        if dry_run:
            self.log(f"   [dry] voltaria (←) em ({d['x']},{d['y']})")
            return True
        self.clicar_pagina(d["x"], d["y"])
        self.log("   ↩️ voltei ao formulário (←).")
        time.sleep(0.4)
        return True

    def _garantir_formulario(self, tentativas=2):
        """Garante que o formulário (Comprar/Vender) está à vista; se estiver no
        comprovante da última ordem, clica ← para voltar."""
        for _ in range(tentativas):
            if self.localizar("Comprar") or self.localizar("Vender"):
                return True
            if not self.voltar_ticket():
                break
            time.sleep(0.4)
        return bool(self.localizar("Comprar") or self.localizar("Vender"))

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
            self.log(f"   ❌ não achei o botão '{palavra_dir}'. Abra o 'Chamado do pedido'.")
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
        if enviar and (qtd is None):
            self.log("   ⚠️ QTD é obrigatória pra ENVIAR o bracket. Informe a quantidade.")
            return False
        ok = True
        for nome, preco, dirr, tipo in plano:
            if preco is None:
                continue
            self.log(f" • {nome}")
            ok = self.enviar_ordem_ticket(preco, dirr, tipo, qtd, enviar) and ok
            time.sleep(pausa)
        self.log("📦 Bracket concluído.")
        return ok

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
    args = [exe, f"--remote-debugging-port={porta}",
            f"--user-data-dir={perfil_dir}", "--new-window", url]
    log(f"🌐 Abrindo Chrome de depuração (porta {porta})...")
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
