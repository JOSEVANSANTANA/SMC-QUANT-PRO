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
import re
import json
import time
import socket
import base64
import struct
import hashlib
import threading
import subprocess
import unicodedata
from urllib.request import urlopen

try:
    from tradovate_stream import TradovateStream
except ImportError:
    TradovateStream = None

PORTA_DEBUG_PADRAO = 9222


# ============================================================================
#  CONTAS QUE PRECISAM FECHAR ANTES DE QUALQUER CLIQUE
#  ---------------------------------------------------------------------------
#  Funções PURAS, de propósito: elas decidem quantos ticks vão no stop e no
#  alvo de uma ordem que vai ser ENVIADA. Isso tem de poder ser conferido sem
#  Chrome, sem Tradovate e sem mercado aberto — e é o que os testes fazem.
# ============================================================================
def _como_numero(valor):
    """'29.542,00', '29,542.00', '7732.50' -> float. None quando não é número.

    A Tradovate escreve o número no campo do jeito da localidade do navegador,
    e o campo é lido de volta como TEXTO. Comparar '7732.5' com '7,732.50' como
    string diria que o valor não entrou — e o robô abortaria uma ordem correta."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(" ", "")
    if not texto:
        return None
    # Fica só o último separador decimal; os outros são de milhar.
    if "," in texto and "." in texto:
        decimal = "," if texto.rfind(",") > texto.rfind(".") else "."
        milhar = "." if decimal == "," else ","
        texto = texto.replace(milhar, "").replace(decimal, ".")
    elif "," in texto:
        # "1,5" é decimal; "1,500" pode ser milhar. Três casas depois da
        # vírgula, sem outro separador, é milhar em pt-BR.
        inteiro, _, resto = texto.rpartition(",")
        texto = (inteiro + resto) if len(resto) == 3 else texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def valores_batem(escrito, lido, tolerancia=None):
    """O que eu escrevi é o que está no campo?

    Compara como NÚMERO quando os dois são números (a plataforma reformata
    '7732.5' como '7,732.50', e isso continua sendo o mesmo preço), e como
    texto quando não são. A tolerância existe para arredondamento de tick, não
    para 'chegou perto' — o padrão é igualdade exata."""
    a, b = _como_numero(escrito), _como_numero(lido)
    if a is not None and b is not None:
        return abs(a - b) <= (tolerancia if tolerancia is not None else 1e-9)
    return str(escrito).strip() == str(lido).strip()


def ticks_entre(preco_a, preco_b, tick):
    """Distância entre dois preços, EM TICKS, sempre positiva e inteira.

    É o que a estratégia ATM da Tradovate espera: ela não recebe preço de stop,
    recebe DISTÂNCIA em ticks a partir do preenchimento. Devolve None quando
    não dá para calcular — e None aqui significa "não envie a ordem", nunca
    "use zero": ATM com zero tick é ordem sem proteção nenhuma."""
    try:
        a, b, t = float(preco_a), float(preco_b), float(tick)
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    n = int(round(abs(a - b) / t))
    return n if n > 0 else None


def plano_trailing(ticks_stop, ligado=False, frequencia=1):
    """O AUTO TRAIL do ticket, quando ele estiver ligado. None = não mexer.

    19/08, ele: "ali na janela do chamado do pedido voce tem todas as opcoes...
    e ainda trailing SE FOR O CASO". O "se for o caso" é o que decide o
    desenho: o trailing entra como opção, desligada por padrão, porque ele
    MUDA a gestão do trade — deixar de ser "stop fixo até o alvo" e passar a
    "stop que persegue" não é detalhe de preenchimento, é outra estratégia.

    Os números não são escolhidos no chute:
      • distância do trail = a MESMA do stop do cenário. Qualquer outra
        distância mudaria em silêncio o risco que o Plano dimensionou.
      • aciona a 1R (o mesmo número de ticks do stop): antes disso o trade
        ainda não pagou o próprio risco, e arrastar o stop ali só antecipa
        saída no ruído.
      • frequência 1 tick: o stop acompanha, não pula degraus.
    """
    if not ligado:
        return None
    try:
        n = int(ticks_stop)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return {"stop": n, "acionar": n, "frequencia": max(1, int(frequencia))}


# ======================================================================
#  TRAILING INTELIGENTE — o stop que decide QUANDO armar, e a que distância
# ======================================================================
#  Ele descreveu o problema melhor do que qualquer manual, em 20/08:
#
#     "na mesa não posso tomar drawdown, se não, quebro a regra e posso
#      perder a conta do mesmo jeito. (no caso, LUCROS NÃO REALIZADOS se por
#      acaso voltar eu tomo drawdown)"
#
#  Numa conta de mesa o drawdown costuma ser medido contra o TOPO da conta,
#  incluindo lucro aberto. Ou seja: um trade que sobe US$1.500 e volta ao zero
#  não é "trade neutro" — é US$1.500 de drawdown consumidos, e pode quebrar a
#  regra num dia que fechou no positivo. O stop fixo não protege disso, porque
#  ele nunca sobe.
#
#  O QUE MUDA EM RELAÇÃO AO TRAIL ANTIGO. O de cima é um número só, igual para
#  todo cenário: arma em 1R, segue a 1R. Ele erra dos dois lados — num alvo
#  curto arma tarde demais (deixa devolver quase tudo) e num alvo largo aperta
#  cedo demais (sai no ruído antes do movimento que ele veio pegar).
#
#  As três perguntas que este aqui responde, e de onde vem cada resposta:
#
#    1. QUANDO ARMAR. Do R:R do cenário. Alvo curto (R:R ≤ 2) tem pouco a
#       ganhar esperando: arma em 1R. Alvo largo (R:R ≥ 3) precisa de espaço
#       para respirar: arma em 1,5R. Arrastar cedo um trade de 3R é a forma
#       clássica de ser stopado no ruído antes do movimento.
#
#    2. A QUE DISTÂNCIA SEGUIR. Também do R:R, pelo mesmo motivo — e a
#       probabilidade ajusta: cenário fraco não merece corda comprida.
#
#    3. O TETO DA MESA, que é a regra dele e MANDA NAS OUTRAS DUAS. A
#       devolução máxima possível a partir do topo é
#       `ticks_trail × valor_do_tick × contratos`. Se isso passa da fatia do
#       drawdown que ainda resta, o trail APERTA até caber. Este passo só
#       encurta, nunca alarga: errar para o lado de proteger demais custa uma
#       saída antecipada; errar para o outro custa a conta.
#
#  Função PURA, como todo o resto que decide dinheiro aqui: dá para conferir
#  sem Chrome, sem corretora e sem mercado.

# o que sobrou, que é exatamente o que se quer evitar.
TRAIL_FRACAO_DO_DRAWDOWN = 0.30
# Abaixo disto o trail vira ruído: qualquer respiração normal do mercado tira
# o trade. Se o teto da mesa exigir menos que isto, o certo é dizer que não dá
# para proteger nessa quantidade de contratos — não apertar até o absurdo.
TRAIL_TICKS_MINIMO = 4


def plano_trailing_inteligente(ticks_stop, rr=None, probabilidade=None,
                               contratos=1, valor_do_tick=0.0,
                               drawdown_restante=None, ligado=True,
                               frequencia=1, modo_r="auto",
                               ruido_ticks=None, ativo=None):
    """Decide QUANDO armar o trail e a que DISTÂNCIA seguir. None = não mexer.

    Devolve {stop, acionar, frequencia, motivo} — `motivo` em português, para
    aparecer no registro: um stop que se move sozinho sem explicação é a
    receita para ele desconfiar da ferramenta no meio do pregão.
    """
    if not ligado:
        return None
    try:
        base = int(ticks_stop)
    except (TypeError, ValueError):
        return None
    if base <= 0:
        return None

    def _f(v, padrao=None):
        try:
            return float(v)
        except (TypeError, ValueError):
            return padrao

    rr = _f(rr)
    prob = _f(probabilidade)
    ruido = _f(ruido_ticks)
    razoes = []

    # Multiplicador customizado se o trader escolheu via chat (ex: "1.5 R" -> 1.5)
    mult_custom = None
    if modo_r and str(modo_r).lower() not in ("auto", "ia", "adaptativa", "🤖 ia adaptativa (smart smc)"):
        import re
        m_match = re.search(r"(\d+(?:[.,]\d+)?)", str(modo_r))
        if m_match:
            try:
                mult_custom = float(m_match.group(1).replace(",", "."))
            except Exception:
                mult_custom = None

    # ---- 1) QUANDO ARMAR, e 2) A QUE DISTÂNCIA ----
    if mult_custom is not None and mult_custom > 0:
        acionar = max(1, int(round(base * mult_custom)))
        distancia = max(TRAIL_TICKS_MINIMO, base)
        razoes.append(f"Gatilho customizado em {mult_custom:.1f}R ({acionar} ticks) com folga de {distancia} ticks")
    else:
        if rr is not None and rr >= 3.0:
            acionar = int(round(base * 1.5))
            distancia = int(round(base * 1.25))
            razoes.append(f"R:R {rr:.1f} é largo — deixo respirar até 1,5R e sigo "
                          "com folga, para não sair no ruído antes do movimento")
        elif rr is not None and rr <= 2.0:
            acionar = base
            distancia = base
            razoes.append(f"R:R {rr:.1f} é curto — protejo já em 1R, porque não há "
                          "muito a ganhar esperando")
        else:
            acionar = base
            distancia = base
            razoes.append("R:R intermediário — armo em 1R com a distância do stop")

        # A probabilidade só APERTA. Cenário fraco não merece corda comprida, e
        # afrouxar por causa dela seria deixar o otimismo do modelo mexer no risco.
        if prob is not None and prob < 65 and distancia > base:
            distancia = base
            razoes.append(f"probabilidade {prob:.0f}% abaixo de 65 — encurtei a "
                          "corda de volta para a distância do stop")

        if ruido is not None and ruido > 0:
            distancia = max(distancia, int(round(ruido * 1.5)))
            razoes.append(f"calibrado pelo ruído do mercado ({ruido:g} ticks)")

    # ---- 3) O TETO DA MESA. Manda nos dois de cima. ----
    dd = _f(drawdown_restante)
    vt = _f(valor_do_tick, 0.0) or 0.0
    try:
        ctr = max(1, int(contratos or 1))
    except (TypeError, ValueError):
        ctr = 1
    aviso_mesa = None
    if dd is not None and dd > 0 and vt > 0:
        teto_usd = dd * TRAIL_FRACAO_DO_DRAWDOWN
        ticks_que_cabem = int(teto_usd // (vt * ctr))
        if ticks_que_cabem < distancia:
            if ticks_que_cabem >= TRAIL_TICKS_MINIMO:
                distancia = ticks_que_cabem
                razoes.append(
                    f"REGRA DA MESA: com {ctr} contrato(s), devolver "
                    f"{distancia} ticks já custaria US$ "
                    f"{distancia * vt * ctr:,.2f} — o teto era "
                    f"US$ {teto_usd:,.2f} ({TRAIL_FRACAO_DO_DRAWDOWN:.0%} do "
                    f"drawdown que ainda resta, US$ {dd:,.2f}). Apertei o "
                    "trail para o lucro aberto não virar drawdown ao voltar")
            else:
                # Não dá para proteger nesta quantidade de contratos sem
                # colar o stop no preço. Dizer isso é mais útil do que armar
                # um trail que vai tirar o trade na primeira respiração.
                aviso_mesa = (
                    f"com {ctr} contrato(s), proteger o lucro dentro do "
                    f"drawdown que resta (US$ {dd:,.2f}) exigiria um trail de "
                    f"{ticks_que_cabem} ticks — perto demais do preço para "
                    f"não ser ruído (mínimo {TRAIL_TICKS_MINIMO}). O trail vai "
                    "no mínimo, mas a posição está grande para o que sobrou "
                    "de drawdown")
                distancia = TRAIL_TICKS_MINIMO
                razoes.append(aviso_mesa)
        # Armar depois do que se pode devolver não protege nada: o acionamento
        # nunca pode ficar acima da devolução que a mesa tolera.
        if acionar > distancia * 3:
            acionar = distancia * 3

    distancia = max(TRAIL_TICKS_MINIMO, int(distancia))
    acionar = max(1, int(acionar))
    return {"stop": distancia, "acionar": acionar,
            "frequencia": max(1, int(frequencia)),
            "motivo": " · ".join(razoes),
            "aperto_pela_mesa": bool(aviso_mesa)}


def plano_atm(direcao, entrada, stop, alvo, tick):
    """Traduz o cenário SMC para o que o formulário ATM entende.

    Devolve (ticks_stop, ticks_alvo, erro). Com `erro` preenchido, NADA deve
    ser enviado: sem os dois números não existe bracket, e uma entrada sem
    bracket é justamente o estado que este caminho veio eliminar.

    A conferência de LADO não é preciosismo. A ATM é cega: ela mede distância
    e não sabe se o seu stop está do lado certo da entrada. Um BUY com stop
    ACIMA da entrada vira, na Tradovate, um stop de N ticks ABAIXO — ou seja,
    ela inverteria silenciosamente a proteção que o cenário pedia."""
    try:
        ent = float(entrada)
        stp = float(stop)
        alv = float(alvo)
    except (TypeError, ValueError):
        return None, None, "entrada, stop e alvo precisam ser números"
    comprado = str(direcao).upper() in ("BUY", "COMPRA", "COMPRAR", "C", "LONG")
    if comprado and not (stp < ent < alv):
        return None, None, (f"cenário incoerente para COMPRA: stop {stp}, "
                            f"entrada {ent}, alvo {alv} — o stop tem de ficar "
                            "ABAIXO da entrada e o alvo ACIMA")
    if not comprado and not (alv < ent < stp):
        return None, None, (f"cenário incoerente para VENDA: alvo {alv}, "
                            f"entrada {ent}, stop {stp} — o stop tem de ficar "
                            "ACIMA da entrada e o alvo ABAIXO")
    t_stop = ticks_entre(ent, stp, tick)
    t_alvo = ticks_entre(ent, alv, tick)
    if not t_stop or not t_alvo:
        return None, None, (f"não consegui converter para ticks (tick={tick}): "
                            f"stop={t_stop}, alvo={t_alvo}")
    return t_stop, t_alvo, None


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
        self.stream = TradovateStream(self, log=self.log) if TradovateStream else None
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
        # NÃO LIGAMOS Runtime.enable NEM Page.enable — E ISSO É O CONSERTO.
        #
        # 19/08, 20:12, no meio de uma ordem que já tinha o preço e a
        # quantidade conferidos na tela:
        #     ⚠️ falha ao enviar ordem: sem resposta do CDP para
        #        Runtime.evaluate (conexão travada).
        #
        # O socket não caiu: ele AFOGOU. `Runtime.enable` faz o Chrome
        # empurrar todo console.log, toda criação de contexto de execução e
        # todo erro da página; `Page.enable` empurra o ciclo de vida de cada
        # frame. A Tradovate é um app ao vivo, com iframes e cotação entrando
        # o tempo todo — e o laço que espera a resposta do NOSSO comando
        # passava os 10 segundos inteiros lendo evento dos outros. A resposta
        # existia; ela estava atrás de uma fila que não parava de crescer.
        #
        # E o pior: nada disso era usado. Nenhum evento de Runtime ou de Page
        # é consumido em lugar nenhum deste arquivo — `Runtime.evaluate`,
        # `Input.dispatchMouseEvent` e `Input.dispatchKeyEvent` funcionam sem
        # habilitar domínio nenhum. Eram duas linhas que só produziam ruído,
        # e o ruído derrubou a ordem.
        self.log("✅ Conectado à aba da Tradovate via CDP.")
        if self.stream:
            self.stream.definir_cliente_cdp(self)
        return True

    def desconectar(self):
        if self.ws:
            self.ws.fechar()
            self.ws = None

    # ----------------------------- CDP ----------------------------------
    # COMANDOS QUE PODEM SER REENVIADOS SEM RISCO: todos apenas LEEM.
    # Qualquer coisa fora desta lista (Input.*, digitação, navegação) muda o
    # estado da plataforma e NUNCA é repetida depois de uma queda de conexão.
    _CDP_REPETIVEIS = frozenset({
        "Runtime.evaluate",          # leitura de DOM e de campos
        "Target.getTargets",
        "Browser.getVersion",
        "Page.getLayoutMetrics",
        "DOM.getDocument",
    })

    def cdp(self, metodo, params=None, timeout=12):
        """Envia um comando CDP com proteção thread-safe (RLock) e auto-reconexão.

        Se o socket cair, a conexão é restabelecida automaticamente.
        """
        if not hasattr(self, "_cdp_lock"):
            self._cdp_lock = threading.RLock()

        with self._cdp_lock:
            if not self.ws:
                try:
                    self.conectar()
                except Exception:
                    pass
            if not self.ws:
                raise ConexaoPerdida("CDP não conectado (chame conectar() antes).")

            meu_id = self._proximo_id
            self._proximo_id += 1
            try:
                self.ws.enviar(json.dumps({"id": meu_id, "method": metodo,
                                            "params": params or {}}))
                limite = time.time() + timeout
                ignoradas = 0
                while time.time() < limite:
                    msg = json.loads(self.ws.receber())
                    if msg.get("id") == meu_id:      # resposta do nosso comando
                        if "error" in msg:
                            raise RuntimeError(f"CDP {metodo}: {msg['error']}")
                        return msg.get("result", {})
                    ignoradas += 1
            except (OSError, EOFError, ValueError, ConnectionError) as e:
                self._marcar_morta()
                # RECONECTAR, SIM. REENVIAR, DEPENDE DO COMANDO.
                #
                # A reconexão automática é uma boa ideia e fica. O reenvio
                # cego é que não pode ficar: `cdp()` também transporta o
                # CLIQUE (Input.dispatchMouseEvent). Se a ligação cair DEPOIS
                # de o clique chegar ao Chrome e ANTES de a resposta voltar, o
                # reenvio clica de novo — e no botão Enviar isso é uma SEGUNDA
                # ORDEM no mercado.
                #
                # É a regra que este arquivo já tinha, escrita em outro lugar:
                # PREENCHER PODE SER REPETIDO; ENVIAR, NÃO. Ler o DOM, medir,
                # consultar — repetir isso é inofensivo e vale a pena. Clicar
                # e digitar mudam o estado da corretora, e "não sei se chegou"
                # tem de virar erro, não uma segunda tentativa.
                if metodo in self._CDP_REPETIVEIS:
                    try:
                        if self.conectar():
                            self.ws.enviar(json.dumps(
                                {"id": meu_id, "method": metodo,
                                 "params": params or {}}))
                            limite = time.time() + timeout
                            while time.time() < limite:
                                msg = json.loads(self.ws.receber())
                                if msg.get("id") == meu_id:
                                    if "error" in msg:
                                        raise RuntimeError(
                                            f"CDP {metodo}: {msg['error']}")
                                    return msg.get("result", {})
                    except Exception:
                        pass
                self._marcar_morta()
                if metodo not in self._CDP_REPETIVEIS:
                    raise ConexaoPerdida(
                        f"a ligação caiu durante {metodo} ({e}) e este comando "
                        "MUDA O ESTADO da plataforma — NÃO repito para não "
                        "arriscar uma segunda ordem. NÃO SEI se ele chegou: "
                        "confira a Tradovate.")
                raise ConexaoPerdida(f"conexão com o Chrome caiu durante {metodo}: {e}")

            self._marcar_morta()
            raise ConexaoPerdida(
                f"sem resposta do CDP para {metodo} em {timeout}s"
                + (f" — {ignoradas} evento(s) da página chegaram na frente" if ignoradas else
                   " (conexão travada)") + ".")

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

    # ==================================================================
    #  MIRAR O CAMPO PELO RÓTULO — e conferir que o valor entrou nele
    # ==================================================================
    #  O QUE ESTAVA ERRADO, e por que era invisível.
    #
    #  `definir_campo_ticket` pegava "o primeiro input do painel da esquerda,
    #  sem placeholder, cujo valor pareça número". Isso funciona enquanto o
    #  ticket está sozinho na tela. Com o painel de ATMs ABERTO — que é
    #  exatamente como ele opera — a mesma coluna passa a ter os campos de
    #  OBTER LUCRO, STOP LOSS, ACIONAR LUCROS e FREQUÊNCIA, todos numéricos e
    #  todos sem placeholder. O primeiro "input numérico da esquerda" deixa de
    #  ser o PREÇO da ordem.
    #
    #  E o pior nem era errar o campo: era não perceber. A função devolvia 'OK'
    #  por ter ENCONTRADO um input, nunca por ter CONFERIDO que o número entrou
    #  onde devia. Escrever no campo errado e reportar sucesso é a pior
    #  combinação possível quando o próximo passo é clicar em Enviar.
    #
    #  A âncora certa é o RÓTULO, que é o que um humano usa para achar o campo:
    #  "PREÇO" tem um input à direita, na mesma linha. É layout de formulário,
    #  não heurística de posição.
    #  E TUDO NUMA IDA SÓ AO CHROME. Cada `Runtime.evaluate` é uma viagem de
    #  ida e volta pelo WebSocket, e foi numa dessas viagens que a ordem de
    #  19/08 morreu ("sem resposta do CDP"). Preencher o ATM custava seis
    #  viagens; agora custa uma. Menos viagens não é otimização de vaidade:
    #  é menos superfície para travar no meio de uma ordem.
    _JS_CAMPOS_POR_ROTULO = r"""
    (function(pedidos, tolerancia){
      function vis(el){var r=el.getBoundingClientRect();
        return r.width>0 && r.height>0 && r.bottom>0 && r.right>0;}
      function norm(s){return (s||'').replace(/\s+/g,' ').trim().toUpperCase();}
      // UMA varredura do DOM para todos os rótulos pedidos. Varrer uma vez por
      // campo era o que fazia o custo crescer junto com o formulário.
      var candidatos = {};
      pedidos.forEach(function(p){ candidatos[norm(p.rotulo)] = []; });
      var els = document.querySelectorAll('div,span,label,p,td,th');
      for (var i=0;i<els.length;i++){
        var el = els[i];
        var t = norm(el.textContent);
        if (!(t in candidatos)) continue;
        if (!vis(el)) continue;
        var r = el.getBoundingClientRect();
        candidatos[t].push({el:el, r:r, area:r.width*r.height});
      }
      // Os inputs visíveis (exceto checkboxes), também uma vez só.
      var ins = [];
      var todos = document.querySelectorAll('input');
      for (var k=0;k<todos.length;k++){
        var inp = todos[k];
        if (!vis(inp) || inp.disabled || inp.readOnly || inp.type === 'checkbox') continue;
        ins.push({el:inp, r:inp.getBoundingClientRect()});
      }
      var setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value').set;

      function resolver(p){
        var rotNorm = norm(p.rotulo);
        
        // 0) Rota de Alta Precisão: data-testid nativos da Tradovate (no próprio input ou no container pai)
        var directEl = null;
        if (rotNorm.indexOf("OBTER LUCRO") !== -1 || rotNorm.indexOf("TAKE PROFIT") !== -1) {
          directEl = document.querySelector('[data-testid="simple-tpsl-bracket-0-take-profit-input"] input, [data-testid*="take-profit-input"] input, input[data-testid*="take-profit-input"]');
        } else if (rotNorm.indexOf("STOP LOSS") !== -1) {
          if (p.ocorrencia === 1) {
            directEl = document.querySelector('[data-testid="simple-tpsl-bracket-0-auto-trail-stop-loss-input"] input, [data-testid*="auto-trail-stop-loss-input"] input, input[data-testid*="auto-trail-stop-loss-input"]');
          } else {
            directEl = document.querySelector('[data-testid="simple-tpsl-bracket-0-stop-loss-input"] input, [data-testid*="stop-loss-input"] input, input[data-testid*="stop-loss-input"]');
          }
        } else if (rotNorm.indexOf("ACIONAR LUCROS") !== -1 || rotNorm.indexOf("TRIGGER") !== -1) {
          directEl = document.querySelector('[data-testid="simple-tpsl-bracket-0-auto-trail-trigger-input"] input, [data-testid*="auto-trail-trigger-input"] input, input[data-testid*="auto-trail-trigger-input"]');
        } else if (rotNorm.indexOf("FREQUÊNCIA") !== -1 || rotNorm.indexOf("FREQUENCY") !== -1) {
          directEl = document.querySelector('[data-testid="simple-tpsl-bracket-0-auto-trail-frequency-input"] input, [data-testid*="auto-trail-frequency-input"] input, input[data-testid*="auto-trail-frequency-input"]');
        } else if (rotNorm.indexOf("PREÇO") !== -1 || rotNorm.indexOf("PRICE") !== -1) {
          directEl = document.querySelector('[data-testid="order-ticket-price-input"] input, [data-testid*="price-input"] input, input[data-testid*="price"]');
        } else if (rotNorm.indexOf("QTD") !== -1 || rotNorm.indexOf("QUANTIDADE") !== -1 || rotNorm.indexOf("QTY") !== -1) {
          directEl = document.querySelector('[data-testid="order-ticket-quantity"] input, [data-testid*="quantity"] input, input[data-testid*="qty"]');
        }

        if (directEl && vis(directEl)) {
          var rDirect = directEl.getBoundingClientRect();
          if (p.valor !== null && p.valor !== undefined){
            directEl.focus();
            setter.call(directEl, '');
            directEl.dispatchEvent(new Event('input', {bubbles:true}));
            setter.call(directEl, String(p.valor));
            directEl.dispatchEvent(new Event('input', {bubbles:true}));
            directEl.dispatchEvent(new Event('change', {bubbles:true}));
            directEl.blur();
          }
          return {estado:'OK', valor:String(directEl.value||''),
                  x:Math.round(rDirect.x + rDirect.width/2),
                  y:Math.round(rDirect.y + rDirect.height/2),
                  via:'data-testid'};
        }

        var lista = candidatos[rotNorm] || [];
        if (!lista.length) return {estado:'ROTULO_NAO_ACHADO'};
        // Um rótulo pode repetir (STOP LOSS aparece no bracket E no auto
        // trail). Desempata por posição na tela, de cima para baixo:
        // `ocorrencia` diz qual delas. Ordem visual é estável; a do DOM não é.
        lista.sort(function(a,b){
          return (a.r.top - b.r.top) || (a.area - b.area); });
        // entre rótulos na MESMA linha fica o menor (o texto, não o contêiner
        // que engloba meia tela e cujo "centro" não diz nada)
        var linhas = [];
        for (var i=0;i<lista.length;i++){
          var c = lista[i], achou = -1;
          for (var j=0;j<linhas.length;j++){
            if (Math.abs(linhas[j].r.top - c.r.top) <= tolerancia){ achou = j; break; }
          }
          if (achou < 0) linhas.push(c);
          else if (c.area < linhas[achou].area) linhas[achou] = c;
        }
        if (p.ocorrencia >= linhas.length)
          return {estado:'OCORRENCIA_INEXISTENTE', quantas:linhas.length};
        var lr = linhas[p.ocorrencia].r;
        var meio = lr.top + lr.height/2;
        // Busca de inputs: suporta layout horizontal (mesma linha) E vertical (logo abaixo do rótulo)
        var melhor = null;
        for (var m=0;m<ins.length;m++){
          var ir = ins[m].r;
          if (ins[m].el.type === "checkbox") continue;
          
          var distHorizontal = (ir.left >= lr.left - 10) ? (ir.left - lr.left) : 9999;
          var distVertical = (ir.top >= lr.top - 5) ? (ir.top - lr.top) : 9999;
          
          // Caso 1: Na mesma linha (horizontal)
          if (Math.abs(ir.top + ir.height/2 - meio) <= tolerancia && ir.left >= lr.left - 10){
            var distH = ir.left - lr.right;
            if (!melhor || distH < melhor.dist)
              melhor = {el:ins[m].el, dist:distH, r:ir};
          }
          // Caso 2: Logo abaixo do rótulo (vertical)
          else if (ir.top >= lr.top && ir.top <= lr.bottom + 55 && ir.left >= lr.left - 50 && ir.left <= lr.right + 150){
            var distV = (ir.top - lr.bottom) * 2 + Math.abs(ir.left - lr.left);
            if (!melhor || distV < melhor.dist)
              melhor = {el:ins[m].el, dist:distV, r:ir};
          }
        }
        if (!melhor){
          // NEM TODO CAMPO DO TICKET É UM <input>. 'EXIBIR EM' e 'TIPO DE
          // STOP LOSS' são seletores, e a unidade escolhida ali (Ticks ou
          // Preço) muda o SIGNIFICADO do número que eu escrevo logo abaixo.
          // Para LEITURA, então, vale o texto do controle vizinho (ao lado ou abaixo).
          if (p.valor === null || p.valor === undefined){
            var textoMelhor = null;
            for (var q=0;q<els.length;q++){
              var e2 = els[q];
              var t2 = (e2.textContent||'').replace(/\s+/g,' ').trim();
              var n2 = norm(t2);
              if (!t2 || t2.length > 24 || n2 === norm(p.rotulo) || n2.indexOf(norm(p.rotulo)) !== -1) continue;
              if (!vis(e2)) continue;
              var r2 = e2.getBoundingClientRect();
              var d2 = 9999;
              if (Math.abs(r2.top + r2.height/2 - meio) <= tolerancia && r2.left >= lr.right){
                d2 = r2.left - lr.right;
              } else if (r2.top >= lr.top && r2.top <= lr.bottom + 45 && r2.left >= lr.left - 30 && r2.left <= lr.right + 100){
                d2 = (r2.top - lr.bottom) + Math.abs(r2.left - lr.left);
              } else {
                continue;
              }
              var a2 = r2.width * r2.height;
              if (!textoMelhor || d2 < textoMelhor.dist - 4 || (Math.abs(d2 - textoMelhor.dist) <= 4 && a2 < textoMelhor.area))
                textoMelhor = {texto:t2, dist:d2, area:a2};
            }
            if (textoMelhor)
              return {estado:'OK', valor:textoMelhor.texto, tipo:'texto'};
          }
          return {estado:'CAMPO_NAO_ACHADO'};
        }
        var el = melhor.el;
        if (p.valor !== null && p.valor !== undefined){
          el.focus();
          setter.call(el, '');
          el.dispatchEvent(new Event('input', {bubbles:true}));
          setter.call(el, String(p.valor));
          el.dispatchEvent(new Event('input', {bubbles:true}));
          el.dispatchEvent(new Event('change', {bubbles:true}));
          el.blur();
        }
        return {estado:'OK', valor:String(el.value||''),
                x:Math.round(melhor.r.x + melhor.r.width/2),
                y:Math.round(melhor.r.y + melhor.r.height/2)};
      }

      var saida = [];
      for (var n=0;n<pedidos.length;n++){
        try { saida.push(resolver(pedidos[n])); }
        catch (e) { saida.push({estado:'ERRO_JS', detalhe:String(e).slice(0,120)}); }
      }
      return JSON.stringify(saida);
    })(%s, %s)
    """

    def campos_por_rotulo(self, pedidos, tolerancia=18):
        """Lê/escreve VÁRIOS campos numa ida só ao Chrome.

        `pedidos` é uma lista de (rotulo, ocorrencia, valor) — valor None só
        lê. Devolve a lista de resultados, na mesma ordem."""
        corpo = [{"rotulo": str(r), "ocorrencia": int(o),
                  "valor": None if v is None else str(v)}
                 for r, o, v in pedidos]
        js = self._JS_CAMPOS_POR_ROTULO % (json.dumps(corpo),
                                           json.dumps(int(tolerancia)))
        try:
            saida = json.loads(self.avaliar_js(js) or "[]") or []
        except ConexaoPerdida:
            raise
        except Exception as e:
            saida = []
        if len(saida) != len(corpo):
            saida = [{"estado": "SEM_RESPOSTA"} for _ in corpo]
        return saida

    def _campo_por_rotulo(self, rotulo, valor=None, ocorrencia=0, tolerancia=18):
        try:
            return self.campos_por_rotulo(
                [(rotulo, ocorrencia, valor)], tolerancia)[0]
        except ConexaoPerdida:
            raise
        except Exception as e:
            return {"estado": "ERRO", "detalhe": str(e)[:120]}

    def ler_campo_por_rotulo(self, rotulo, ocorrencia=0):
        """O que está ESCRITO no campo daquele rótulo agora, ou None."""
        r = self._campo_por_rotulo(rotulo, None, ocorrencia)
        return r.get("valor") if r.get("estado") == "OK" else None

    def definir_campo_por_rotulo(self, rotulo, valor, ocorrencia=0,
                                 tolerancia_num=None):
        """Escreve no campo do rótulo e CONFERE lendo de volta.

        Devolve (ok, detalhe). A conferência é o ponto: sem ela, escrever no
        campo errado e reportar sucesso é a pior combinação possível quando o
        passo seguinte é clicar em Enviar."""
        r = self._campo_por_rotulo(rotulo, valor, ocorrencia, tolerancia=18)
        estado = r.get("estado")
        if estado != "OK":
            return False, estado or "SEM_RESPOSTA"
        lido = r.get("valor", "")
        if valores_batem(valor, lido, tolerancia_num):
            return True, lido
        return False, f"escrevi {valor!r} e o campo ficou {lido!r}"

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

    def ler_ativo_ticket(self):
        """Lê o ativo/símbolo atualmente selecionado no 'Chamado do pedido'."""
        js = r"""
        (function(){
          function vis(el){try{var r=el.getBoundingClientRect(); return r.width>0&&r.height>0;}catch(e){return false;}}
          function txt(el){try{return (el.innerText||el.textContent||'').trim();}catch(e){return '';}}
          function norm(s){return (s||'').toString().replace(/\s+/g,' ').trim().toUpperCase();}
          
          var ins = [].slice.call(document.querySelectorAll('input, [contenteditable=true]')).filter(function(el){
            if(!vis(el)) return false;
            var r = el.getBoundingClientRect();
            return r.x < 350 && r.y < 350;
          });
          for (var i=0; i<ins.length; i++){
            var el = ins[i];
            var val = norm(el.value || '');
            if (/^[A-Z0-9]{2,8}$/.test(val) && el.getBoundingClientRect().top < 150){
              return val;
            }
          }
          var textos = document.querySelectorAll('div, span, h1, h2, h3, button');
          for (var j=0; j<textos.length; j++){
            var r = textos[j].getBoundingClientRect();
            if (r.x < 350 && r.y < 120 && vis(textos[j])){
              var t = norm(txt(textos[j]));
              if (/^[A-Z0-9]{2,8}$/.test(t)) return t;
            }
          }
          return '';
        })()
        """
        try:
            return (self.avaliar_js(js) or "").strip().strip('"').upper()
        except Exception:
            return ""

    def selecionar_ativo_ticket(self, ativo, pausa=0.45):
        """Seleciona e confere o ativo (ex: 'MNQU6', 'MESU6') no 'Chamado do pedido'.
        
        Se o ticket já estiver com o ativo desejado, não faz nada e confirma.
        Se estiver com outro ativo (ex: 'MESU6' quando a ordem é 'MNQU6'), digita o ativo
        no campo de busca de símbolo, envia Enter e confirma a troca.
        """
        if not ativo or str(ativo).strip().upper() in ("DESCONHECIDO", "", "NONE"):
            return True, "nenhum ativo específico informado"
        alvo = str(ativo).strip().upper()
        
        js = r"""
        (function(alvo){
          function vis(el){try{var r=el.getBoundingClientRect(); return r.width>0&&r.height>0;}catch(e){return false;}}
          function txt(el){try{return (el.innerText||el.textContent||'').trim();}catch(e){return '';}}
          function norm(s){return (s||'').toString().replace(/\s+/g,' ').trim().toUpperCase();}
          
          var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          
          var ins = [].slice.call(document.querySelectorAll('input, [contenteditable=true]')).filter(function(el){
            if(!vis(el)) return false;
            var r = el.getBoundingClientRect();
            return r.x < 350 && r.y < 350;
          });
          
          var inputSimbolo = null;
          for (var i=0; i<ins.length; i++){
            var el = ins[i];
            var ph = (el.placeholder || '').toLowerCase();
            var val = norm(el.value || '');
            if (ph.indexOf('search') >= 0 || ph.indexOf('pesquis') >= 0 || ph.indexOf('símbolo') >= 0 || ph.indexOf('symbol') >= 0 || ph.indexOf('contract') >= 0){
              inputSimbolo = el;
              break;
            }
            if (/^[A-Z0-9]{2,8}$/.test(val) && el.getBoundingClientRect().top < 150){
              inputSimbolo = el;
              break;
            }
          }
          if (!inputSimbolo && ins.length > 0){
            ins.sort(function(a,b){ return a.getBoundingClientRect().top - b.getBoundingClientRect().top; });
            if (ins[0].getBoundingClientRect().top < 150){
              inputSimbolo = ins[0];
            }
          }
          
          var atual = inputSimbolo ? norm(inputSimbolo.value) : '';
          if (atual === alvo || (atual && alvo.startsWith(atual)) || (atual && atual.startsWith(alvo))){
            return JSON.stringify({ok:true, mudou:false, ativo_atual:atual});
          }
          
          if (!inputSimbolo){
            var abas = document.querySelectorAll('div, span, button, a');
            for(var a=0; a<abas.length; a++){
              var ab = abas[a];
              if(!vis(ab)) continue;
              var tabTxt = norm(txt(ab));
              if(tabTxt.indexOf(alvo) >= 0 && ab.getBoundingClientRect().top < 150){
                ab.click();
                return JSON.stringify({ok:true, mudou:true, via:'aba_grafico', ativo_novo:alvo});
              }
            }
            return JSON.stringify({ok:false, motivo:'campo de símbolo não encontrado no ticket', ativo_atual:atual});
          }
          
          inputSimbolo.focus();
          setter.call(inputSimbolo, '');
          inputSimbolo.dispatchEvent(new Event('input', {bubbles:true}));
          setter.call(inputSimbolo, alvo);
          inputSimbolo.dispatchEvent(new Event('input', {bubbles:true}));
          inputSimbolo.dispatchEvent(new Event('change', {bubbles:true}));
          
          return JSON.stringify({ok:true, mudou:true, ativo_anterior:atual, ativo_novo:alvo});
        })(%s)
        """ % json.dumps(alvo)
        
        try:
            res = json.loads(self.avaliar_js(js) or "{}")
        except ConexaoPerdida:
            raise
        except Exception as e:
            return False, f"erro ao selecionar ativo no ticket ({e})"
        
        if not res.get("ok"):
            self.log(f"   ⚠️ Não consegui preencher o ativo '{alvo}' no ticket: {res.get('motivo')}")
            return False, res.get("motivo")
            
        if res.get("mudou"):
            self.cdp("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
            self.cdp("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
            time.sleep(pausa)
            
            js_dropdown = r"""
            (function(alvo){
              function vis(el){try{var r=el.getBoundingClientRect(); return r.width>0&&r.height>0;}catch(e){return false;}}
              function txt(el){try{return (el.innerText||el.textContent||'').trim();}catch(e){return '';}}
              function norm(s){return (s||'').toString().replace(/\s+/g,' ').trim().toUpperCase();}
              var itens = document.querySelectorAll('li, tr, [role=option], [role=row], div');
              for (var i=0; i<itens.length; i++){
                var it = itens[i];
                if(!vis(it)) continue;
                var t = norm(txt(it));
                var r = it.getBoundingClientRect();
                if (r.x < 450 && r.y < 350 && (t === alvo || t.startsWith(alvo + ' ') || t.startsWith(alvo + '\n'))){
                  it.click();
                  return true;
                }
              }
              return false;
            })(%s)
            """ % json.dumps(alvo)
            try:
                self.avaliar_js(js_dropdown)
            except Exception:
                pass
            time.sleep(pausa)
            self.log(f"   ✏️ Ativo alterado no ticket: {res.get('ativo_anterior', '')} → {alvo}")
        else:
            self.log(f"   ✏️ Ativo conferido no ticket: {alvo}")
            
        return True, "ativo conferido"

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
        if(/^(Enviar|Submit|Redefinir|Reset|Comprar|Vender|Buy|Sell)$/i.test(t)) temEnviar=true;
        if(/^(MODIFICAR|CANCELAR|MODIFY|CANCEL)$/i.test(t)) temComprovante=true;
      }
      if(!temEnviar){
        var inputs=document.querySelectorAll('input, [data-testid*="price"], [data-testid*="qty"], [data-testid*="trading-ticket"], .trading-ticket, .ticket-form');
        for(var j=0; j<inputs.length; j++){
          if(vis(inputs[j])){ temEnviar=true; break; }
        }
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

          // 0) Atalho direto: na Tradovate moderna, a seta ← tem a classe .icon-back
          var direto = document.querySelector('.trading-ticket-header .icon-back, .trading-ticket-header [data-testid="icon-button-container"], .icon.icon-back');
          if (direto && vis(direto)) {
            var rDirect = direto.getBoundingClientRect();
            if (rDirect.width > 0 && rDirect.height > 0) {
              // O CLIQUE FALTAVA AQUI. Este atalho devolvia as coordenadas e
              // saía pelo `return` ANTES do trecho que clica, lá embaixo — e
              // o Python, vendo achou:true, registrava "voltar (←) clicado"
              // sem nada ter sido clicado. O formulário não voltava e a
              // mensagem dizia que sim.
              try {
                var b = (direto.closest && direto.closest('button,[role=button],a')) || direto;
                b.click();
              } catch(e){}
              return JSON.stringify({achou: true, x: Math.round(rDirect.x + rDirect.width/2), y: Math.round(rDirect.y + rDirect.height/2), via: 'icon-back'});
            }
          }

          // 1) Acha o MENOR container que contém o texto do comprovante.
          var marcador=/PLACEHOLDER_COMPROVANTE/;
          var nucleo=null, menorArea=Infinity;
          var conts=document.querySelectorAll('div,section,form,aside,main');
          for(var i=0;i<conts.length;i++){
            var el=conts[i];
            if(!vis(el)) continue;
            var t=txt(el);
            if(!marcador.test(t)) continue;
            var r=el.getBoundingClientRect();
            if(r.width<150||r.height<80) continue;   // pequeno demais p/ ser painel
            var a=r.width*r.height;
            if(a<menorArea){ menorArea=a; nucleo=el; }
          }

          // 2) A ÂNCORA É GEOMÉTRICA, NÃO DE PARENTESCO — e esta troca é a
          //    correção de 20/08, 00:15. O robô não conseguiu voltar, a ordem
          //    de BUY MESU6 @ 7771 não saiu, e a seta ← estava na tela o
          //    tempo todo.
          //
          //    O QUE ESTAVA ERRADO: a busca era feita dentro do subárvore de
          //    um ancestral do comprovante, alcançado SUBINDO cinco níveis a
          //    partir do menor bloco que contivesse "Funcionando/Filled/...".
          //    Naquele comprovante os BRACKETS traziam os próprios estados
          //    ("Vender 17 LMT 7772.00 - Filled", "STP 7766.25 - Cancelado"),
          //    então o menor bloco marcado passou a ser uma linha de bracket —
          //    vários níveis mais FUNDO do que a tabela de eventos de antes. A
          //    subida de cinco níveis não chegava mais ao painel, o escopo
          //    ficou preso lá embaixo, e `querySelectorAll` só enxerga
          //    DESCENDENTES: a seta, que fica ACIMA, na linha do título, não
          //    era descendente de nada disso. Ela não existia para a busca.
          //
          //    Contar níveis de aninhamento de um app React é apostar numa
          //    coisa que muda sozinha — foi a segunda vez que essa aposta
          //    custou uma ordem. A posição na TELA, não. A seta do ticket fica
          //    na COLUNA do comprovante e um pouco ACIMA dele; é isso que se
          //    procura agora, varrendo o documento inteiro. Profundidade de
          //    DOM deixou de importar.
          var faixa=null;
          if(nucleo){
            var rn=nucleo.getBoundingClientRect();
            faixa={ x1: rn.x - 40, x2: rn.x + rn.width + 40,
                    // A linha do título fica logo acima do corpo do
                    // comprovante. A folga para baixo cobre o layout em que a
                    // seta divide a linha com o primeiro item do recibo.
                    y1: rn.y - 220, y2: rn.y + 70 };
          }
          var escopo = document;

          // 3b) NADA QUE FECHE MÓDULO PODE SER CLICADO. Foi um clique no título
          //     do painel que abriu "Fechar este módulo o removerá do seu espaço
          //     de trabalho" e travou a plataforma no meio do pregão.
          var PROIBIDO=/(close|fechar|remove|remover|excluir|delete|minimi|maximi|popout|pop-out|settings|config)/i;
          function seguro(el){
            try{
              var a=(el.getAttribute('aria-label')||'')+' '+
                    (el.getAttribute('title')||'')+' '+
                    (el.getAttribute('data-testid')||'')+' '+
                    (el.className&&el.className.baseVal!==undefined
                       ? el.className.baseVal : (el.className||''));
              if(PROIBIDO.test(String(a))) return false;
              var tt=txt(el).trim();
              if(/^(×|✕|✖|x|X)$/.test(tt)) return false;          // botão de fechar
              if(/chamado do pedido|order ticket/i.test(tt)) return false; // título/aba
              return true;
            }catch(e){ return false; }
          }

          // 4) O menor ícone clicável na COLUNA do comprovante, na altura da
          //    linha do título. Sem comprovante localizado, cai para o alto à
          //    esquerda da tela, que é onde o ticket vive no layout padrão.
          var cands=escopo.querySelectorAll('button,[role=button],a,svg,i,span,div');
          var best=null, vistos=0;
          for(var k=0;k<cands.length;k++){
            var e2=cands[k];
            if(!vis(e2)) continue;
            if(!seguro(e2)) continue;
            var r2=e2.getBoundingClientRect();
            if(r2.width>60||r2.height>60) continue;      // ícone, não bloco
            if(r2.width<8||r2.height<8) continue;
            var mx=r2.x+r2.width/2, my=r2.y+r2.height/2;
            if(faixa){
              if(mx < faixa.x1 || mx > faixa.x2) continue;
              if(my < faixa.y1 || my > faixa.y2) continue;
            }else{
              if(mx > window.innerWidth*0.45) continue;
              if(my > Math.max(window.innerHeight*0.30, 90)) continue;
            }
            var t2=txt(e2).trim();
            var setaTexto = /^(←|<|‹|⟵|Voltar|Back)$/i.test(t2);
            var svg = temSvg(e2);
            if(!svg && !setaTexto) continue;
            // O ancestral clicável também precisa ser seguro: de nada adianta o
            // ícone ser inofensivo se o botão em volta dele fecha o módulo.
            var alvo2=null;
            try{ alvo2=e2.closest && e2.closest('button,[role=button],a'); }catch(e){}
            if(alvo2 && !seguro(alvo2)) continue;
            vistos++;
            // À ESQUERDA GANHA. Dentro da faixa pode haver mais de um ícone na
            // linha do título (destacar painel, expandir); a seta de voltar é
            // a primeira da linha, encostada na margem. Sem este critério o
            // desempate ficava só no tamanho, que é quase igual entre eles.
            var score = (r2.width*r2.height) + mx*4
                        - (svg?1e6:0) - (setaTexto?2e6:0);
            if(!best || score<best.score)
              best={score:score, x:Math.round(mx), y:Math.round(my), el:e2,
                    svg:svg, texto:setaTexto};
          }
          if(!best) return JSON.stringify({achou:false, tinha_painel:!!nucleo,
                                           candidatos:vistos});
          try{
            var alvo=(best.el.closest &&
                      best.el.closest('button,[role=button],a')) || best.el;
            if(!seguro(alvo)) alvo=best.el;
            alvo.click();
          }catch(e){}
          return JSON.stringify({achou:true, x:best.x, y:best.y,
                                 svg:best.svg, texto:best.texto,
                                 tinha_painel:!!nucleo, candidatos:vistos});
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

        # O QUE EU VI, E NÃO SÓ QUE FALHEI. Em 20/08 a mensagem foi só "não
        # achei o botão de voltar", e com ela não dava para saber se o
        # comprovante tinha sido localizado, se havia ícone nenhum na faixa ou
        # se todos tinham sido barrados por segurança. Sem esses três números
        # a investigação vira adivinhação.
        onde = ("na coluna do comprovante" if d.get("tinha_painel")
                else "no alto à esquerda da tela (comprovante não localizado)")
        self.log(f"   ⚠️ não achei o botão de voltar (←) {onde} — "
                 f"{d.get('candidatos', 0)} ícone(s) chegaram a ser avaliados. "
                 "Tentando as outras saídas do comprovante.")
        if dry_run:
            return False
        # ROTAS ALTERNATIVAS — todas NÃO DESTRUTIVAS.
        #
        # LIÇÃO CARA (pregão de 06/08, 15:45): houve aqui uma terceira rota que
        # clicava no TÍTULO do painel "Chamado do pedido". Na Tradovate, clicar
        # no título/aba de um módulo é o gesto de FECHAR o módulo: subiu o
        # diálogo "Fechar este módulo o removerá do seu espaço de trabalho", que
        # é modal, travou a plataforma inteira e desmontou a área de trabalho
        # dele — com a ordem de entrada já enviada. A rota foi removida.
        #
        # REGRA QUE FICA: uma rota de recuperação só pode tocar em ícone de
        # NAVEGAÇÃO dentro do painel. Nunca em título, aba, "×" ou qualquer
        # coisa capaz de fechar um módulo. Prejuízo por não conseguir voltar é
        # ruim; destruir a mesa do trader no meio do pregão é pior.
        for rotulo, acao in (
            ("atributo (aria-label/title de voltar)", self._voltar_por_atributo),
            ("tecla ESC", self._voltar_por_escape),
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
        """Clica em quem se declara botão de VOLTAR por aria-label/title.

        'fechar' e 'close' foram DELIBERADAMENTE tirados da busca: na Tradovate
        o botão de fechar remove o MÓDULO do espaço de trabalho. Voltar e fechar
        não são sinônimos aqui — confundir os dois desmontou a mesa dele no meio
        do pregão."""
        self.avaliar_js(r"""
        (function(){
          // '[class]' entrou junto: sem ele, o ícone que se declara só pela
          // classe nunca chegava a ser examinado, por mais que a regra abaixo
          // soubesse reconhecê-lo.
          var els=document.querySelectorAll(
            '[aria-label],[title],[data-testid],[class]');
          var quero=/(voltar|back|retornar|previous|anterior|arrow.?left|chevron.?left)/i;
          // Barreira de segurança: nada que cheire a fechar/remover é clicado,
          // mesmo que também diga "voltar" em algum outro atributo.
          var proibidoRe=new RegExp('close|fechar|remove|remover|excluir|delete|'+
                                    'minimi|maximi|expand|popout|pop-out|'+
                                    'settings|config', 'i');
          for(var i=0;i<els.length;i++){
            var e=els[i];
            var r=e.getBoundingClientRect();
            if(r.width<=0||r.height<=0) continue;
            if(r.width>80||r.height>80) continue;
            // A CLASSE TAMBÉM CONTA. Ícone de app React costuma se declarar
            // pelo nome da classe ('icon-arrow-left', 'chevronLeft') e não ter
            // aria-label nenhum — era uma rota inteira de recuperação ficando
            // de fora por não olhar o atributo mais óbvio. `baseVal` porque em
            // <svg> o className é objeto, não string.
            var cls=(e.className&&e.className.baseVal!==undefined
                     ? e.className.baseVal : (e.className||''));
            var a=(e.getAttribute('aria-label')||'')+' '+
                  (e.getAttribute('title')||'')+' '+
                  (e.getAttribute('data-testid')||'')+' '+String(cls);
            if(!quero.test(a)) continue;
            if(proibidoRe.test(a)) continue;
            try{ e.click(); return 'ok'; }catch(err){}
          }
          return 'nada';
        })()
        """)

    def _voltar_por_escape(self):
        self.teclar_escape()

    def dispensar_dialogo_perigoso(self):
        """Se a Tradovate subir um diálogo de CONFIRMAÇÃO DESTRUTIVA (fechar
        módulo, remover painel, sair de posições), clica em CANCELAR.

        Existe por causa do pregão de 06/08: um clique errado do robô abriu
        "Fechar este módulo o removerá do seu espaço de trabalho". O diálogo é
        MODAL — enquanto ele está na tela, nada mais funciona, e o robô ficou
        martelando a plataforma com a ordem de entrada já enviada. Agora ele
        reconhece a situação e sai dela pelo lado seguro.

        NUNCA clica em OK/Confirmar: a resposta certa para uma confirmação que o
        robô não pediu é sempre "não".
        Devolve True se dispensou algum diálogo."""
        js = r"""
        (function(){
          function vis(el){
            try{ var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
            catch(e){ return false; }
          }
          function txt(el){
            try{ return (el.innerText||el.textContent||'').trim(); }catch(e){ return ''; }
          }
          var perigoRe=new RegExp('remover[áa]? do seu espa[çc]o|'+
                                  'remove it from your workspace|'+
                                  'fechar este m[óo]dulo|close this module', 'i');
          // Procura o aviso em um elemento VISÍVEL de texto — não no
          // textContent do body inteiro, que arrasta junto o conteúdo de
          // <script>/<style> e daria alarme falso.
          var achouAviso=false;
          var avisos=document.querySelectorAll('div,p,span,h1,h2,h3,label,td');
          for(var a=0;a<avisos.length;a++){
            var ea=avisos[a];
            if(!vis(ea)) continue;
            var ta=txt(ea);
            if(!ta||ta.length>300) continue;
            if(perigoRe.test(ta)){ achouAviso=true; break; }
          }
          if(!achouAviso) return JSON.stringify({achou:false});
          // Acha o botão CANCELAR (nunca o OK) e clica nele.
          var els=document.querySelectorAll('button,[role=button],a,div,span');
          for(var i=0;i<els.length;i++){
            var e=els[i];
            if(!vis(e)) continue;
            var t=txt(e);
            if(!/^(cancelar|cancel|n[ãa]o|no)$/i.test(t)) continue;
            var r=e.getBoundingClientRect();
            if(r.width>200||r.height>80) continue;
            try{ e.click(); return JSON.stringify({achou:true, via:'cancelar'}); }catch(err){}
          }
          return JSON.stringify({achou:true, via:'nenhum botao'});
        })()
        """
        try:
            d = json.loads(self.avaliar_js(js) or "{}")
        except ConexaoPerdida:
            raise
        except Exception:
            return False
        if not d.get("achou"):
            return False
        if d.get("via") == "cancelar":
            self.log("   🛡️ a Tradovate pediu confirmação para FECHAR UM MÓDULO. "
                     "Cliquei em CANCELAR — o robô nunca confirma isso.")
            time.sleep(0.4)
            return True
        # Diálogo na tela e sem botão de cancelar reconhecido: ESC e alerta.
        self.teclar_escape()
        self.log("   🛡️ há um diálogo de confirmação aberto na Tradovate "
                 "bloqueando a tela. Tentei fechá-lo com ESC. Se continuar, "
                 "clique em CANCELAR (nunca em OK) para não perder o painel.")
        return True

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
               conta:null, modo:"REAL", eh_replay:false, velocidade:null, horario_mercado:null,
               diag:{amostras:[], textos_posi:[]}};

      // ================= IDENTIFICAÇÃO DETERMINÍSTICA: CONTA & MODO REPLAY =================
      var corpoTexto = (document.body ? (document.body.innerText || document.body.textContent || '') : '');
      var elsConta = document.querySelectorAll('.account-dropdown, [data-testid*="account"], .account-selector, div, span, select, p, label');
      for(var ic=0; ic<elsConta.length; ic++){
        var tc = txt(elsConta[ic]);
        if(!tc || tc.length > 60) continue;
        var mRpl = tc.match(/\b(RPL[0-9A-Z-]+)\b/i);
        if(mRpl){ res.conta = mRpl[1]; res.eh_replay = true; res.modo = "REPLAY"; break; }
        var mDemo = tc.match(/\b(DEMO[0-9A-Z-]+)\b/i);
        if(mDemo){ res.conta = mDemo[1]; res.modo = "DEMO"; break; }
        var mNum = tc.match(/\b([0-9]{6,10}(?:-[0-9]+)?)\b/);
        if(mNum && !res.conta){ res.conta = mNum[1]; }
      }
      if(!res.eh_replay){
        if(/\bRPL[0-9A-Z-]*\b/i.test(corpoTexto) || /VELOCIDADE\s*:\s*\d+%/i.test(corpoTexto) || /\(R\)\s*\d{2}:\d{2}/i.test(corpoTexto)){
          res.eh_replay = true;
          res.modo = "REPLAY";
        }
      }
      var mVel = corpoTexto.match(/VELOCIDADE\s*:\s*(\d+%)/i);
      if(mVel) res.velocidade = mVel[1];
      var mH = corpoTexto.match(/(\d{2}:\d{2}:\d{2}\s*(?:CDT|EST|EDT|CST|UTC|BRT)?)/i);
      if(mH) res.horario_mercado = mH[1];

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
        if self.stream:
            try:
                p_stream = self.stream.ler_preco_imediato()
                if p_stream and p_stream > 0:
                    return p_stream
            except Exception:
                pass
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

    def ler_ambiente(self):
        """Identifica a Conta ativa, Modo (REAL / DEMO / REPLAY), Velocidade e Horário do Mercado."""
        d = self.ler_estado() or {}
        return {
            "conta": d.get("conta"),
            "modo": d.get("modo", "REAL"),
            "eh_replay": bool(d.get("eh_replay")),
            "velocidade": d.get("velocidade"),
            "horario_mercado": d.get("horario_mercado"),
        }

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

    # ==================================================================
    #  ORDENS VIVAS NA PLATAFORMA — contar ANTES e DEPOIS de cancelar
    # ==================================================================
    #  Sem isto, "cancelei" seria mais uma frase que eu não posso provar. O
    #  painel "Chamado do pedido" mostra cada ordem numa linha com o número
    #  dela e o estado: "#344367004 Comprar 16 MESU6 LMT em 7712.50 -
    #  Funcionando - 0/16", e os brackets logo abaixo como "Suspenso".
    #
    #  A âncora é o NÚMERO DA ORDEM (#seguido de dígitos), e ele resolve dois
    #  problemas de uma vez: separa a linha da ordem do contêiner que engloba
    #  todas (o contêiner traz vários números, a linha traz um só), e não
    #  confunde com a tabela de eventos embaixo, cujo ID vem sem o '#'.
    #
    #  E a diferença que mais importa: NÃO ACHAR NADA não é "zero ordens". Se
    #  o painel não estiver aberto, a tela fica igual à de uma conta limpa.
    #  Por isso 'ok' só é True quando eu vi o painel; senão devolvo o motivo e
    #  quem chamou que decida — nunca "está tudo cancelado" por não ter visto.
    _JS_ORDENS_VIVAS = r"""
    (function(){
      function vis(el){try{var r=el.getBoundingClientRect();
        return r.width>0&&r.height>0;}catch(e){return false;}}
      function txt(el){try{return (el.innerText||el.textContent||'')
        .replace(/\s+/g,' ').trim();}catch(e){return '';}}
      function norm(s){return (s||'').toString().normalize('NFD')
        .replace(/[̀-ͯ]/g,'').toLowerCase();}
      // Estados em que a ordem AINDA OCUPA LUGAR na corretora. 'Suspenso' é o
      // bracket esperando a entrada preencher: ele some sozinho se a entrada
      // for cancelada, mas enquanto está lá, está lá.
      var reVivo=/(funcionando|working|suspenso|suspended|aceito|accepted|pendente|pending|em execucao|na execucao)/;
      var reMorto=/(cancelad|cancell?ed|preenchid|filled|executad|rejeitad|rejected|expirad|expired|recusad)/;
      var vivas={}, mortas={}, amostras=[], viuPainel=false;
      var els=document.querySelectorAll('div,span,li,td,tr,p');
      for(var i=0;i<els.length;i++){
        var el=els[i];
        if(!vis(el)) continue;
        var t=txt(el);
        if(!t||t.length>240) continue;
        var ids=t.match(/#\d{4,}/g);
        if(!ids||ids.length!==1) continue;   // linha de UMA ordem só
        viuPainel=true;
        var n=norm(t);
        if(reMorto.test(n)){ mortas[ids[0]]=1; continue; }
        if(!reVivo.test(n)) continue;
        if(!vivas[ids[0]]){
          vivas[ids[0]]=1;
          if(amostras.length<8) amostras.push(t.slice(0,140));
        }
      }
      if(!viuPainel){
        // Nem uma linha de ordem na tela. Pode ser conta limpa COM o painel
        // aberto, ou painel fechado — e as duas leituras são idênticas daqui.
        var titulo=false, cab=document.querySelectorAll('div,span,h1,h2,h3,label');
        for(var c=0;c<cab.length;c++){
          if(!vis(cab[c])) continue;
          var tc=norm(txt(cab[c]));
          if(tc.length<40 && /(chamado do pedido|order ticket|orders|pedidos)/.test(tc)){
            titulo=true; break;
          }
        }
        if(!titulo) return JSON.stringify({ok:false, vivas:null,
          motivo:'nao achei o painel de ordens na tela — nao da para dizer se ha ordem viva'});
      }
      return JSON.stringify({ok:true, vivas:Object.keys(vivas).length,
                             ids:Object.keys(vivas), amostras:amostras,
                             mortas:Object.keys(mortas).length});
    })()
    """

    def contar_ordens_vivas(self):
        """Quantas ordens minhas/suas ainda estão de pé na Tradovate.

        Devolve {ok, vivas, ids, amostras, motivo}. `ok=False` significa NÃO SEI
        — e não zero. Quem chama tem de tratar as duas coisas de forma
        diferente: "zero ordens" libera; "não sei" só permite avisar."""
        try:
            d = json.loads(self.avaliar_js(self._JS_ORDENS_VIVAS) or "{}")
        except ConexaoPerdida as e:
            return {"ok": False, "vivas": None, "conexao_perdida": True,
                    "motivo": f"a ligação com o Chrome caiu: {e}"}
        except Exception as e:
            return {"ok": False, "vivas": None, "motivo": str(e)}
        return d or {"ok": False, "vivas": None, "motivo": "sem resposta da página"}

    # ==================================================================
    #  "SAIR EM MKT &" — O BOTÃO QUE ZERA A POSIÇÃO E CANCELA AS ORDENS
    # ==================================================================
    #  Ele pediu isto por escrito: "se estou deixando automação ligada é porque
    #  precisa ter total autonomia... ali no topo tem a opção Sair em MKT &,
    #  essa opção zera a posição atual e cancela todas as ordens".
    #
    #  E é PRECISAMENTE por zerar a posição que este botão não pode ser tratado
    #  como um "cancelar ordens". São duas ações num clique só, e uma delas é
    #  irreversível: se houver posição executada, ela é liquidada a mercado. Uma
    #  ordem cancelada por engano custa uma oportunidade; uma posição liquidada
    #  por engano custa dinheiro na hora.
    #
    #  Daí a trava: eu só encosto neste botão depois de LER na tela que a
    #  posição está ZERADA. Não "supor que está" — ler. Se a leitura falhar, eu
    #  não clico: com posição desconhecida, este botão é uma aposta, e o
    #  caminho honesto é avisar você para cancelar na mão.
    #
    #  Isso também casa com a regra que já existia no diário: posição JÁ
    #  EXECUTADA é gerida por stop e alvo, nunca cancelada por mudança de
    #  leitura. Quando a ordem não pegou (posição 0), este botão faz só o que se
    #  quer dele — varrer as ordens que sobraram.
    _JS_BOTAO_SAIR = r"""
    (function(){
      function vis(el){try{var r=el.getBoundingClientRect();
        return r.width>0&&r.height>0;}catch(e){return false;}}
      function txt(el){try{return (el.innerText||el.textContent||'')
        .replace(/[\s\u2009]+/g,' ').trim();}catch(e){return '';}}
      function norm(s){return (s||'').toString().normalize('NFD')
        .replace(/[̀-ͯ]/g,'').toLowerCase();}
      var re=/(sair em (mkt|mercado))|(exit at m(k|ar)?[kt])|(flatten)|(cancelar tod[oa]s)|(cancel all)/i;
      var achados=[];
      var els=document.querySelectorAll('button,[role=button],div,span,a,li');
      for(var i=0;i<els.length;i++){
        var el=els[i];
        if(!vis(el)) continue;
        var t=txt(el);
        if(!t||t.length>70) continue;
        if(!re.test(norm(t))) continue;
        var r=el.getBoundingClientRect();
        var isBtn=(el.tagName==='BUTTON'||el.getAttribute('role')==='button');
        var bonus=isBtn?0:10000;
        achados.push({el:el, t:t, r:r, area:r.width*r.height + bonus, isBtn:isBtn,
                      titulo:(el.getAttribute('title')||''),
                      aria:(el.getAttribute('aria-label')||''),
                      cortado:(el.scrollWidth > el.clientWidth + 2)});
      }
      if(!achados.length) return JSON.stringify({achou:false});
      achados.sort(function(a,b){return a.area-b.area;});
      var m=achados[0];
      var rotulo=(m.titulo||m.aria||m.t);
      var alvo=(m.el.closest && m.el.closest('button,[role=button],a')) || m.el;
      // ESTA FUNÇÃO SÓ OLHA. O CLIQUE É DE QUEM DECIDE.
      //
      // Havia aqui um dispatchEvent + click() e ele custava caro: quem chama
      // isto é `localizar_sair_em_mercado()`, que roda ANTES da checagem de
      // modo teste e ANTES da recusa por "Reverso e Cxl". Com o clique aqui
      // dentro, o modo teste zerava a posição de verdade — e logo abaixo o
      // programa escrevia "MODO TESTE: achei o botão e NÃO cliquei".
      //
      // Localizar e agir são passos diferentes de propósito: é a separação
      // que permite LER o rótulo, decidir se aquele botão serve, e só então
      // clicar. Juntar os dois transforma toda leitura numa ação.
      var rAlvo=alvo.getBoundingClientRect();
      return JSON.stringify({achou:true, rotulo:rotulo, texto_na_tela:m.t,
        cortado:!!m.cortado, quantos:achados.length,
        x:Math.round(rAlvo.x+rAlvo.width/2), y:Math.round(rAlvo.y+rAlvo.height/2)});
    })()
    """

    # A LEGENDA DIZ O QUE O BOTÃO VAI FAZER — e por isso ela precisa
    # DISCRIMINAR. Com 'sair', 'mkt', '&' e 'all' na lista, a expressão casava
    # com "Sair em Mkt" puro, que zera a posição e DEIXA as ordens vivas: o
    # oposto do que se quer aqui. Uma trava que aceita tudo não é trava.
    #
    # O que continua coberto, e era o motivo do alargamento: 'Cxl' abreviado
    # ('Sair em Mkt & Cxl'), 'Cancelar todas' e as reticências do texto
    # cortado pelo CSS.
    _RE_SAIR_CANCELA = re.compile(
        r"cancel|\bcxl\b|\bcxl\.|&\s*cxl|&\s*\.{1,3}|&\s*…",
        re.IGNORECASE)

    _JS_VARREDURA_CANCELAR = r"""
    (function(){
      try {
        // 1. Clica em links de cancelamento ou botões X de ordens vivas
        var els = document.querySelectorAll('a, button, span, div');
        for(var i=0; i<els.length; i++){
          var el = els[i];
          var t = (el.innerText || el.textContent || '').trim().toLowerCase();
          if(t === 'cancelar' || t === '[cancelar]' || t === 'cancel' || t === '[cancel]' || t === 'cxl'){
            el.dispatchEvent(new MouseEvent("mousedown", {bubbles: true, cancelable: true, view: window, buttons: 1}));
            el.dispatchEvent(new MouseEvent("mouseup", {bubbles: true, cancelable: true, view: window, buttons: 1}));
            el.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true, view: window, buttons: 1}));
            try { el.click(); } catch(e){}
          }
        }
        var xBtns = document.querySelectorAll('[title*="cancel" i], [title*="cancelar" i], .cancel-order, .order-cancel');
        for(var j=0; j<xBtns.length; j++){
          var xb = xBtns[j];
          xb.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true, view: window, buttons: 1}));
          try { xb.click(); } catch(e){}
        }
        // 2. Garante que o painel de ATMs/OCO no chamado do pedido permaneça aberto e ativo
        var btnA = document.querySelector('[data-testid="switch-falsy-btn"], .context-toolbar .falsy-value');
        if(btnA){
          btnA.dispatchEvent(new MouseEvent("mousedown", {bubbles: true, cancelable: true, view: window, buttons: 1}));
          btnA.dispatchEvent(new MouseEvent("mouseup", {bubbles: true, cancelable: true, view: window, buttons: 1}));
          btnA.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true, view: window, buttons: 1}));
          try { btnA.click(); } catch(e){}
        }
      } catch(e){}
    })()
    """

    # E ESTE EU NÃO CLICO NUNCA, mesmo falando em cancelar.
    # 'Reverso e Cxl' cancela as ordens E INVERTE A POSIÇÃO — sai do BUY e
    # entra VENDIDO, a mercado, no mesmo clique. Passou a casar com a regex
    # nova (tem 'Cxl'), e sem esta exceção o robô poderia abrir uma posição
    # contrária tentando limpar a tela. Abrir posição que ninguém pediu é pior
    # do que qualquer coisa que este botão vem resolver.
    _RE_SAIR_PROIBIDO = re.compile(r"revers", re.IGNORECASE)

    def localizar_sair_em_mercado(self):
        """Acha o botão 'Sair em Mkt &' e devolve o que ele diz que faz."""
        try:
            d = json.loads(self.avaliar_js(self._JS_BOTAO_SAIR) or "{}")
        except ConexaoPerdida:
            raise
        except Exception:
            return {"achou": False}
        if not d.get("achou"):
            return {"achou": False}
        rotulo = unicodedata.normalize("NFD", str(d.get("rotulo") or ""))
        d["inverte_posicao"] = bool(self._RE_SAIR_PROIBIDO.search(rotulo))
        d["cancela_ordens"] = bool(self._RE_SAIR_CANCELA.search(rotulo)
                                   and not d["inverte_posicao"])
        return d

    def sair_em_mercado_e_cancelar(self, enviar=False, exigir_zerado=True):
        """Clica em 'Sair em Mkt & Cancelar': zera a posição e limpa as ordens.

        Devolve {ok, clicou, motivo, vivas_antes, vivas_depois, recusa}."""
        r = {"ok": False, "clicou": False, "motivo": None, "recusa": False,
             "vivas_antes": None, "vivas_depois": None, "rotulo": None}

        # 1) A POSIÇÃO ESTÁ ZERADA? Leitura na tela.
        quais_abertas = ""
        try:
            estado = self.ler_estado() or {}
            abertas = [l for l in (estado.get("linhas") or [])
                       if l.get("qtd_liquida")]
            if abertas:
                quais_abertas = ", ".join(
                    f"{l.get('ativo') or '?'} {l.get('qtd_liquida')}"
                    for l in abertas)
        except ConexaoPerdida as e:
            if exigir_zerado:
                r["motivo"] = f"a ligação com o Chrome caiu antes de eu ler a posição: {e}"
                r["recusa"] = True
                return r
        except Exception:
            pass

        if exigir_zerado:
            if not estado.get("ok"):
                r["motivo"] = ("não consegui LER a posição na tela ("
                               + str(estado.get("motivo") or "motivo não informado")
                               + "). Este botão liquida a mercado: sem saber se "
                                 "você está posicionado, clicar nele é aposta.")
                r["recusa"] = True
                self.log(f"   ⛔ não clico em 'Sair em Mkt': {r['motivo']}")
                return r
            if quais_abertas:
                r["motivo"] = (f"você ESTÁ posicionado ({quais_abertas}). Este botão "
                               "zeraria a posição a mercado, e posição executada "
                               "se administra por stop e alvo — não por mudança "
                               "de leitura minha.")
                r["recusa"] = True
                self.log(f"   ⛔ não clico em 'Sair em Mkt': {r['motivo']}")
                return r

        # 2) QUANTAS ORDENS HÁ AGORA — é o "antes" que dá sentido ao "depois".
        antes = self.contar_ordens_vivas()
        r["vivas_antes"] = antes.get("vivas")

        # 3) O BOTÃO, E O QUE A LEGENDA DELE DIZ QUE ELE FAZ.
        try:
            btn = self.localizar_sair_em_mercado()
        except ConexaoPerdida as e:
            r["motivo"] = f"a ligação com o Chrome caiu: {e}"
            return r
        if not btn.get("achou"):
            r["motivo"] = ("não achei o botão 'Sair em Mkt &' na tela da "
                           "Tradovate. Ele fica no topo do painel do "
                           "instrumento — deixe-o visível.")
            self.log(f"   ⚠️ {r['motivo']}")
            return r
        r["rotulo"] = btn.get("rotulo")
        if btn.get("inverte_posicao"):
            r["motivo"] = (f"o botão está em '{btn.get('rotulo')}', que além de "
                           "cancelar INVERTE A POSIÇÃO — sairia do seu lado e "
                           "entraria no contrário, a mercado. Não encosto nele. "
                           "Escolha 'Sair em Mkt & Cxl' na setinha ao lado.")
            r["recusa"] = True
            self.log(f"   ⛔ {r['motivo']}")
            return r
        if not btn.get("cancela_ordens"):
            r["motivo"] = (f"o botão está em '{btn.get('rotulo')}', que não "
                           "cancela ordem nenhuma. Na setinha ao lado dele, "
                           "escolha 'Sair em Mkt & Cxl' — aí eu uso.")
            r["recusa"] = True
            self.log(f"   ⛔ {r['motivo']}")
            return r

        if not enviar:
            r["ok"] = True
            r["motivo"] = (f"MODO TESTE: achei o botão '{btn.get('rotulo')}' e "
                           f"NÃO cliquei. Havia {r['vivas_antes']} ordem(ns) "
                           "viva(s) — continuam todas lá.")
            self.log(f"   🧪 {r['motivo']}")
            return r

        # 4) O CLIQUE.
        if quais_abertas:
            self.log(f"   🧹 Clicando em '{btn.get('rotulo')}' "
                     f"({r['vivas_antes']} ordem(ns) viva(s), posição aberta: {quais_abertas} — liquidando a pedido do trader).")
        else:
            self.log(f"   🧹 Clicando em '{btn.get('rotulo')}' "
                     f"({r['vivas_antes']} ordem(ns) viva(s), posição zerada).")
        try:
            self.clicar_pagina(btn["x"], btn["y"])
        except ConexaoPerdida as e:
            r["motivo"] = (f"a ligação caiu no clique ({e}) — NÃO SEI se o "
                           "cancelamento saiu. CONFIRA A PLATAFORMA.")
            r["incerto"] = True
            self.log(f"   ⚠️ {r['motivo']}")
            return r
        r["clicou"] = True

        # Varredura complementar no DOM: clica em links [CANCELAR] da lista de ordens, botões X e Redefinir
        try:
            self.avaliar_js(self._JS_VARREDURA_CANCELAR)
        except Exception:
            pass

        time.sleep(0.6)
        try:
            self._confirmar_dialogo_de_cancelamento()
        except ConexaoPerdida:
            pass
        time.sleep(0.9)

        # 5) A CONFERÊNCIA.
        depois = self.contar_ordens_vivas()
        r["vivas_depois"] = depois.get("vivas")
        if not depois.get("ok"):
            r["motivo"] = ("cliquei, mas não consegui reler as ordens ("
                           + str(depois.get("motivo") or "motivo não informado")
                           + "). NÃO SEI dizer se elas saíram. CONFIRA A "
                             "PLATAFORMA.")
            r["incerto"] = True
            self.log(f"   ⚠️ {r['motivo']}")
            return r
        if depois.get("vivas"):
            # Segunda rota: tenta 'Cancelar todas' antes de desistir
            self.log(f"   ↩️ ainda há {depois['vivas']} ordem(ns) viva(s) — "
                     "tentando o botão 'Cancelar todas' antes de desistir.")
            try:
                ok2, det2 = self.cancelar_todas_as_ordens()
            except ConexaoPerdida as e:
                ok2, det2 = False, str(e)
            if ok2:
                terceira = self.contar_ordens_vivas()
                r["vivas_depois"] = terceira.get("vivas")
                if terceira.get("ok") and not terceira.get("vivas"):
                    r["ok"] = True
                    r["motivo"] = (f"ordens canceladas na plataforma "
                                   f"({r['vivas_antes']} → 0) pelo botão "
                                   f"'{det2}', depois de o "
                                   f"'{btn.get('rotulo')}' não ter bastado.")
                    self.log(f"   ✅ {r['motivo']}")
                    return r
            r["motivo"] = (f"cliquei em '{btn.get('rotulo')}'"
                           + (f" e também em '{det2}'" if ok2 else "")
                           + f" e AINDA HÁ {r['vivas_depois']} ordem(ns) "
                             "viva(s) na plataforma. NÃO cancelei. "
                             "Cancele na mão.")
            self.log(f"   ❌ {r['motivo']}")
            return r
        r["ok"] = True
        # "CANCELADAS (0 → 0)" NÃO É CANCELAMENTO — É UMA TELA JÁ LIMPA.
        #
        # 22/08, às 10:53 e às 11:56, saiu para ele: "✅ ORDENS CANCELADAS NA
        # PLATAFORMA: BUY MESU6 @ 7545,0 ... (0 → 0), com a posição zerada".
        # Zero antes e zero depois quer dizer que não havia o que cancelar. O
        # resultado final está certo (a tela está limpa, que era o objetivo),
        # mas a frase credita ao programa uma ação que ele não fez.
        #
        # Parece implicância e não é: é a mesma família do lucro que não
        # existiu. No dia em que a leitura falhar e devolver zero por engano,
        # essa frase vai dizer "cancelei" com três ordens vivas na tela.
        if not r.get("vivas_antes"):
            r["motivo"] = ("não havia ordem viva na plataforma para cancelar"
                           + (f"; posições fechadas ({quais_abertas})"
                              if quais_abertas else "; a posição já estava zerada")
                           + ".")
        else:
            r["motivo"] = (f"ordens canceladas na plataforma "
                           f"({r['vivas_antes']} → 0)"
                           + (f", posições fechadas ({quais_abertas})" if quais_abertas else ", com a posição zerada")
                           + ".")
        self.log(f"   ✅ {r['motivo']}")
        return r

    # ==================================================================
    #  A SEGUNDA ROTA: "Sair de todas as posições / Cancelar todas"
    # ==================================================================
    #  20/08, 12:26: eu cliquei em 'Sair em Mkt & Cxl' e as TRÊS ordens
    #  continuaram vivas. Relatei isso corretamente ("NÃO cancelei, cancele na
    #  mão") — mas parar ali era desistir cedo demais, porque o próprio
    #  diagnóstico de leitura que eu imprimo a cada ciclo trazia, na lista de
    #  textos com "posi" na tela:
    #
    #      · 'Sair de todas as posições Cancelar todas'
    #
    #  Ou seja: existia um segundo botão, explícito, visível, no DOM dele, e eu
    #  nunca tentei. Estava escrito no meu próprio log.
    #
    #  Por que o primeiro clique falha às vezes: o 'Sair em Mkt & Cxl' fica num
    #  seletor combinado, e o alvo do clique pode cair na parte do menu em vez
    #  da parte do botão. Este aqui é um botão inteiro, sem seletor.
    _JS_CANCELAR_TODAS = r"""
    (function(){
      function vis(el){try{var r=el.getBoundingClientRect();
        return r.width>0&&r.height>0;}catch(e){return false;}}
      function txt(el){try{return (el.innerText||el.textContent||'')
        .replace(/\s+/g,' ').trim();}catch(e){return '';}}
      function norm(s){return (s||'').toString().normalize('NFD')
        .replace(/[̀-ͯ]/g,'').toLowerCase();}
      // "Cancelar todas", "Cancelar todos", "Cancel All", e o botão duplo
      // "Sair de todas as posicoes Cancelar todas".
      var re=/(cancelar tod[oa]s|cancel all)/;
      // REVERTER/INVERTER continua proibido pelo mesmo motivo de sempre:
      // abrir posicao contraria e pior do que nao cancelar.
      var proibido=/(revers|inverter)/;
      var melhor=null;
      var els=document.querySelectorAll('button,[role=button],a,div,span');
      for(var i=0;i<els.length;i++){
        var el=els[i];
        if(!vis(el)) continue;
        var t=txt(el);
        if(!t || t.length>60) continue;
        var n=norm(t);
        if(!re.test(n) || proibido.test(n)) continue;
        var r=el.getBoundingClientRect();
        // O MENOR elemento que contem o texto e o proprio botao; os maiores
        // sao os paineis em volta, e clicar no centro de um painel erra o alvo
        // — foi o que aconteceu com o clique em (1400, 79).
        var a=r.width*r.height;
        if(a < 40) continue;                 // pequeno demais para ser botao
        if(!melhor || a < melhor.area)
          melhor={el:el, area:a, texto:t,
                  x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)};
      }
      if(!melhor) return JSON.stringify({achou:false});
      try{
        var alvo=(melhor.el.closest && melhor.el.closest('button,[role=button],a'))
                 || melhor.el;
        alvo.click();
      }catch(e){}
      return JSON.stringify({achou:true, texto:melhor.texto,
                             x:melhor.x, y:melhor.y});
    })()
    """

    def cancelar_todas_as_ordens(self):
        """Clica no botão 'Cancelar todas' da Tradovate. Devolve (ok, detalhe).

        É a SEGUNDA rota, e ela não zera posição: cancela ordem. Por isso é
        mais segura que o 'Sair em Mkt & Cxl' — mas continua vindo depois
        dele, porque o que ele pediu foi o primeiro."""
        try:
            d = json.loads(self.avaliar_js(self._JS_CANCELAR_TODAS) or "{}")
        except ConexaoPerdida:
            raise
        except Exception as e:
            return False, str(e)
        if not d.get("achou"):
            return False, "não achei o botão 'Cancelar todas' na tela"
        self.log(f"   🧹 cliquei também em '{d.get('texto')}' "
                 f"({d.get('x')},{d.get('y')}).")
        time.sleep(0.6)
        try:
            self._confirmar_dialogo_de_cancelamento()
        except ConexaoPerdida:
            pass
        time.sleep(0.9)
        return True, d.get("texto")

    def _confirmar_dialogo_de_cancelamento(self):
        """Confirma a caixa de 'tem certeza?' do cancelamento — e SÓ ela."""
        js = r"""
        (function(){
          function vis(el){try{var r=el.getBoundingClientRect();
            return r.width>0&&r.height>0;}catch(e){return false;}}
          function txt(el){try{return (el.innerText||el.textContent||'')
            .replace(/\s+/g,' ').trim();}catch(e){return '';}}
          function norm(s){return (s||'').toString().normalize('NFD')
            .replace(/[̀-ͯ]/g,'').toLowerCase();}
          var reAssunto=new RegExp('cancelar|cancel|sair|exit|liquidar|liquidate|'+
            'zerar|flatten|deseja|realmente|confirmar|fechar|close|posic|ordens|orders', 'i');
          var achou=false;
          var els=document.querySelectorAll('div,p,span,h1,h2,h3,label,td,[role=dialog]');
          for(var i=0;i<els.length;i++){
            var e=els[i];
            if(!vis(e)) continue;
            var t=txt(e);
            if(!t||t.length>300) continue;
            if(reAssunto.test(norm(t))){ achou=true; break; }
          }
          if(!achou) return JSON.stringify({achou:false});
          var bts=document.querySelectorAll('button,[role=button],a,div,span');
          for(var k=0;k<bts.length;k++){
            var b=bts[k];
            if(!vis(b)) continue;
            var tb=norm(txt(b));
            if(!/^(ok|sim|yes|confirmar|confirm|continuar|continue|sair.*cancelar|cancelar.*todas|sair.*todas|fechar.*todas|sim.*cancelar|sim.*sair)$/i.test(tb)) continue;
            var rb=b.getBoundingClientRect();
            if(rb.width>300||rb.height>120) continue;
            try{ b.click(); return JSON.stringify({achou:true, via:'confirmou'}); }catch(err){}
          }
          return JSON.stringify({achou:true, via:'sem botao'});
        })()
        """
        try:
            d = json.loads(self.avaliar_js(js) or "{}")
        except ConexaoPerdida:
            raise
        except Exception:
            return False
        if d.get("via") == "confirmou":
            self.log("   ☑️ confirmei a caixa de cancelamento que EU acabei de "
                     "abrir (é a única que respondo com sim).")
            return True
        return False

    def _formulario_visivel(self):
        """True se o FORMULÁRIO de ordem está à vista. Indicador confiável: o
        botão 'Enviar' só existe no formulário — no comprovante da ordem ele
        some. (Comprar/Vender não servem: o comprovante de uma venda deixa um
        texto 'Vender' na tela e dava falso-positivo.)"""
        return bool(self.localizar("Enviar"))

    def _garantir_formulario(self, tentativas=3):
        """Garante que o FORMULÁRIO do 'Chamado do pedido' está à vista.

        Há DOIS motivos possíveis para ele não estar, e eles pedem ações
        diferentes — antes o robô dizia sempre "comprovante à vista", o que
        confundia quando o ticket simplesmente não estava aberto:
          a) está no COMPROVANTE da última ordem  -> basta clicar na setinha ←;
          b) o ticket NÃO ESTÁ ABERTO na tela     -> só VOCÊ pode abrir.
        """
        # ANTES DE QUALQUER COISA: se houver um diálogo modal de confirmação na
        # tela, a plataforma está bloqueada e insistir só piora. Sai dele pelo
        # CANCELAR e segue.
        try:
            self.dispensar_dialogo_perigoso()
        except ConexaoPerdida:
            raise
        except Exception:
            pass
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
                     "setinha ← do 'Chamado do pedido' e tente de novo. "
                     "(Não vou insistir clicando na plataforma: martelar a tela "
                     "no meio do pregão é pior do que parar e te avisar.)")
        return ok

    def enviar_ordem_ticket(self, preco, direcao, tipo="LIMITE", qtd=None,
                            enviar=False, pausa=0.45, ativo=None):
        """Preenche UMA ordem no 'Chamado do pedido'. Se enviar=False (padrão),
        só preenche pra você conferir na tela — NÃO clica em Enviar."""
        long_ = str(direcao).upper() in ("BUY", "COMPRA", "COMPRAR", "C", "LONG")
        palavra_dir = "Comprar" if long_ else "Vender"
        modo = "ENVIAR" if enviar else "SÓ PREENCHER (confira na tela)"
        rotulo_ativo = f" [{ativo}]" if ativo else ""
        self.log(f"🧾 Ordem [{modo}]{rotulo_ativo}: {palavra_dir} {tipo} @ {preco}"
                 + (f"  x{qtd}" if qtd else ""))
        if enviar and (qtd is None):
            self.log("   ⚠️ QTD é obrigatória pra ENVIAR (o Tradovate recusa sem "
                     "quantidade). Informe a quantidade.")
            return False
        # 0) garante que o formulário está à vista e seleciona o ativo correto
        if not self._garantir_formulario():
            self.log("   ❌ formulário do 'Chamado do pedido' não está visível. "
                     "Abra o ticket na Tradovate.")
            return False
        if ativo:
            self.selecionar_ativo_ticket(ativo, pausa)
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

    # ==================================================================
    #  BRACKET DE UMA VEZ SÓ — pela estratégia ATM, em ticks
    # ==================================================================
    #  A ideia é dele, e é melhor que a minha. O caminho antigo mandava TRÊS
    #  ordens separadas (entrada, stop, alvo), e entre uma e outra o painel da
    #  Tradovate vira comprovante e precisa voltar ao formulário. Toda vez que
    #  essa volta falha, existe uma janela em que a ENTRADA já está no mercado
    #  e a PROTEÇÃO não — o pior estado que este programa pode produzir.
    #
    #  A plataforma já resolve isso sozinha: o painel ATM recebe o alvo e o
    #  stop EM TICKS e anexa os dois à ordem no momento do preenchimento, com
    #  OCO nativo (executou um, o outro é cancelado pela corretora, não por
    #  mim). Uma submissão, sem volta ao formulário, sem janela de exposição.
    #
    #  A regra de ouro deste método: NADA é enviado antes de todos os campos
    #  terem sido escritos E conferidos por leitura de volta. Se qualquer um
    #  falhar, ele devolve o motivo e não clica em Enviar — o pior resultado
    #  possível passa a ser "não operou", que é um resultado com o qual dá
    #  para viver.
    ROTULO_PRECO = "PREÇO"
    ROTULO_QTD = "QTD"
    ROTULO_ALVO_ATM = "OBTER LUCRO"
    ROTULO_STOP_ATM = "STOP LOSS"

    ROTULO_UNIDADE_ATM = "EXIBIR EM"
    ROTULO_TRAIL_ACIONAR = "ACIONAR LUCROS"
    ROTULO_TRAIL_FREQ = "FREQUÊNCIA"

    def painel_atm_visivel(self):
        """Os campos de bracket do ATM estão na tela? (uma ida ao Chrome)"""
        r = self.campos_por_rotulo([(self.ROTULO_ALVO_ATM, 0, None),
                                    (self.ROTULO_STOP_ATM, 0, None)])
        return all(x.get("estado") == "OK" for x in r)

    def abrir_painel_atm(self, pausa=0.5):
        """Abre e expande o painel de Take Profit / Stop Loss (ATMs / Bracket)."""
        if self.painel_atm_visivel():
            return True
        js = r"""
        (function(){
            function vis(el){try{var r=el.getBoundingClientRect(); return r.width>0&&r.height>0;}catch(e){return false;}}
            function txt(el){try{return (el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();}catch(e){return '';}}
            
            // 1. Botão 'Ativar ordens bracket' / 'Enable bracket orders' / 'Add take profit / stop loss'
            var btns = document.querySelectorAll('button, [role=button], div.btn');
            for(var i=0; i<btns.length; i++){
                var t = txt(btns[i]).toLowerCase();
                if(t.includes('ativar ordens bracket') || t.includes('enable bracket') || t.includes('add take profit') || t.includes('adicionar take profit')){
                    if(vis(btns[i])){
                        var r = btns[i].getBoundingClientRect();
                        btns[i].click();
                        return JSON.stringify({achou: true, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), texto: t});
                    }
                }
            }
            // 2. Switch S / A no topo do ticket (se o A estiver inativo)
            var switches = document.querySelectorAll('[data-testid="switch-falsy-btn"], [data-testid="table-view-mode-switch"] .falsy-value, .icon-switch .falsy-value');
            for(var j=0; j<switches.length; j++){
                if(vis(switches[j])){
                    var rs = switches[j].getBoundingClientRect();
                    switches[j].click();
                    return JSON.stringify({achou: true, x: Math.round(rs.x + rs.width/2), y: Math.round(rs.y + rs.height/2), texto: 'switch A'});
                }
            }
            // 3. Abas de texto ATMs / ATM / Bracket
            for(var k=0; k<btns.length; k++){
                var t2 = txt(btns[k]).toLowerCase();
                if(t2 === 'atms' || t2 === 'atm' || t2 === 'bracket'){
                    if(vis(btns[k])){
                        var r2 = btns[k].getBoundingClientRect();
                        btns[k].click();
                        return JSON.stringify({achou: true, x: Math.round(r2.x + r2.width/2), y: Math.round(r2.y + r2.height/2), texto: t2});
                    }
                }
            }
            return JSON.stringify({achou: false});
        })()
        """
        try:
            d = json.loads(self.avaliar_js(js) or "{}")
            if d.get("achou"):
                self.log(f"   🔧 acionei o painel de ATMs via '{d.get('texto')}'…")
                time.sleep(pausa)
                if self.painel_atm_visivel():
                    return True
        except Exception:
            pass

        for palavra in ("ATMs", "ATM", "Ativar ordens bracket"):
            alvo = self.localizar(palavra)
            if alvo:
                self.log(f"   🔧 clicando em {palavra}…")
                self.clicar_pagina(alvo["x"], alvo["y"])
                time.sleep(pausa)
                if self.painel_atm_visivel():
                    return True
        return self.painel_atm_visivel()

    def configurar_atm(self, ticks_stop, ticks_alvo, trailing=None, pausa=0.4):
        """Escreve o bracket (e o trailing, se pedido) NUMA IDA SÓ ao Chrome.

        `trailing` é None (não mexe no AUTO TRAIL) ou um dict com
        {stop, acionar, frequencia} em ticks.

        Devolve (ok, detalhe, sem_painel). A conferência é por leitura de
        volta, campo a campo: é ela que separa 'escrevi' de 'entrou'.

        `sem_painel` separa DUAS coisas que não podem ser confundidas:
          • "não tem painel de ATMs aqui"  -> não dá para usar este caminho;
            quem chama pode tentar outro.
          • "tem, e eu me RECUSO a enviar" -> unidade errada, campo que não
            confere, cenário incoerente. Aqui NÃO existe 'tentar outro
            caminho': o outro caminho manda a entrada primeiro e a proteção
            depois, que é exatamente o risco de que a recusa está fugindo."""
        def _lote():
            pedidos = [
                # A UNIDADE VEM PRIMEIRO, E É LIDA, NÃO ESCRITA.
                # Se 'EXIBIR EM' estiver em Preço, o número 40 deixa de ser 40
                # ticks e vira o preço 40 — a diferença entre um stop de dez
                # pontos e uma ordem sem sentido nenhum.
                (self.ROTULO_UNIDADE_ATM, 0, None),
                (self.ROTULO_ALVO_ATM, 0, int(ticks_alvo)),
                # ocorrência 0 = o STOP LOSS do bracket. O de baixo, na
                # ocorrência 1, é o do AUTO TRAIL — outro campo, outra função.
                (self.ROTULO_STOP_ATM, 0, int(ticks_stop)),
            ]
            if trailing:
                pedidos += [
                    (self.ROTULO_STOP_ATM, 1, int(trailing["stop"])),
                    (self.ROTULO_TRAIL_ACIONAR, 0, int(trailing["acionar"])),
                    (self.ROTULO_TRAIL_FREQ, 0, int(trailing["frequencia"])),
                ]
            else:
                # DESLIGADO TEM DE APAGAR, NÃO SÓ DEIXAR DE ESCREVER.
                #
                # 20/08, ele: "a opção trail stop, às vezes mesmo desativada ela
                # está funcionando na plataforma". Estava mesmo, e a causa é
                # esta: o ramo de cima escrevia os campos do AUTO TRAIL; este
                # aqui simplesmente NÃO OS TOCAVA. O ticket da Tradovate guarda
                # o que foi digitado antes — então bastava UMA ordem com trail
                # ligado para todas as seguintes herdarem aquele trail, com a
                # caixinha aqui desmarcada e ele sem entender de onde vinha.
                #
                # "Não mexer" parecia o comportamento conservador. Não é: num
                # formulário com memória, não mexer é aceitar a configuração de
                # outra pessoa — no caso, a de um cenário que já morreu. Zerar é
                # o único jeito de a caixinha desmarcada significar o que diz.
                pedidos += [
                    (self.ROTULO_STOP_ATM, 1, 0),
                    (self.ROTULO_TRAIL_ACIONAR, 0, 0),
                    (self.ROTULO_TRAIL_FREQ, 0, 0),
                ]
            return pedidos, self.campos_por_rotulo(pedidos)

        def _garantir_checkboxes():
            js_cb = r"""
            (function(){
                var marcados = 0;
                var targets = ['take-profit', 'stop-loss'];
                for(var i=0; i<targets.length; i++){
                    var nome = targets[i];
                    var cb = document.querySelector('[data-testid="simple-tpsl-bracket-0-' + nome + '-checkbox"], [data-testid*="' + nome + '-checkbox"]');
                    var lbl = document.querySelector('[data-testid="simple-tpsl-bracket-0-' + nome + '-checkbox-label"], [data-testid*="' + nome + '-checkbox-label"]');
                    // SÓ MARCA O QUE ESTÁ DESMARCADO — nunca alterna.
                    //
                    // A condição anterior tinha um OU a mais: com o checkbox
                    // JÁ MARCADO (cb.checked === true) mas a classe do label
                    // diferente de 'checkbox-active', ela clicava — e clicar
                    // num checkbox marcado DESMARCA. O efeito seria mandar a
                    // entrada sem stop e sem alvo anexados, que é o estado que
                    // a ordem ATM inteira existe para impedir.
                    //
                    // Quando o checkbox existe, ele é a fonte da verdade: a
                    // classe do label é aparência e pode mudar de nome numa
                    // atualização da Tradovate sem nada estar errado.
                    var precisa = cb ? !cb.checked
                                     : (lbl.className || '').indexOf('checkbox-active') === -1;
                    if(lbl && precisa){
                        var r = lbl.getBoundingClientRect();
                        var opts = {bubbles: true, cancelable: true, view: window, clientX: r.x + r.width/2, clientY: r.y + r.height/2};
                        lbl.dispatchEvent(new MouseEvent('mousedown', opts));
                        lbl.dispatchEvent(new MouseEvent('mouseup', opts));
                        lbl.dispatchEvent(new MouseEvent('click', opts));
                        try { lbl.click(); } catch(e){}
                        marcados++;
                    }
                }
                return marcados;
            })()
            """
            try:
                self.avaliar_js(js_cb)
            except Exception:
                pass

        _garantir_checkboxes()
        time.sleep(0.25)
        pedidos, res = _lote()
        # Painel fechado? Abre e refaz — sem isso, o robô desistia da ordem
        # inteira por causa de uma aba que um clique resolve.
        if res[1].get("estado") != "OK" or res[2].get("estado") != "OK":
            if self.abrir_painel_atm():
                _garantir_checkboxes()
                time.sleep(0.25)
                pedidos, res = _lote()
            else:
                return False, ("o painel de ATMs não está à vista no 'Chamado "
                               "do pedido'"), True

        unidade = res[0].get("valor") if res[0].get("estado") == "OK" else None
        if unidade and "TICK" not in str(unidade).upper():
            return False, (f"'EXIBIR EM' está em {unidade!r}, não em Ticks — "
                           "nessa unidade o número que eu escrevo vira PREÇO, "
                           "não distância. Não envio assim"), False
        if not unidade:
            self.log("   ⚠️ não consegui LER o seletor 'EXIBIR EM'. Confirme "
                     "que ele está em Ticks na Tradovate.")

        # OS TRÊS PRIMEIROS SÃO OBRIGATÓRIOS: unidade, alvo e stop do bracket.
        # Falhar num deles é motivo para não enviar — é o risco da operação.
        #
        # A LIMPEZA DO AUTO TRAIL É BEST-EFFORT, e a distinção importa. Quando
        # o trail está DESLIGADO eu escrevo 0 nos campos dele para apagar o que
        # sobrou da ordem anterior; se esses campos não existirem neste layout
        # (seção recolhida, versão diferente do ticket), exigir que eles
        # confiram RECUSARIA A ORDEM INTEIRA por causa de uma limpeza — e
        # bloquear a operação para zerar um campo opcional seria trocar um
        # problema pequeno por um grande.
        n_obrigatorios = 3      # unidade + alvo + stop (índices 0,1,2)
        limpando_trail = not trailing
        for i, ((rotulo, ocorrencia, valor), r) in enumerate(
                zip(pedidos[1:], res[1:]), start=1):
            onde = f"{rotulo}" + (" (auto trail)" if ocorrencia else "")
            opcional = limpando_trail and i >= n_obrigatorios
            if r.get("estado") != "OK":
                if opcional:
                    self.log(f"   ℹ️ não achei o campo {onde} para zerar o AUTO "
                             "TRAIL. Se a plataforma tiver um trail guardado de "
                             "uma ordem anterior, ele pode continuar valendo — "
                             "confira no ticket.")
                    continue
                return False, f"campo {onde}: {r.get('estado', 'SEM_RESPOSTA')}", False
            if not valores_batem(valor, r.get("valor", "")):
                if opcional:
                    self.log(f"   ℹ️ campo {onde}: tentei zerar e ficou "
                             f"{r.get('valor')!r}. Confira o AUTO TRAIL no ticket.")
                    continue
                return False, (f"campo {onde}: escrevi {valor!r} e o campo "
                               f"ficou {r.get('valor')!r}"), False
        self.log(f"   🛡️ ATM conferida na tela: alvo {int(ticks_alvo)} ticks · "
                 f"stop {int(ticks_stop)} ticks"
                 + (f" · auto trail {trailing['stop']} ticks a partir de "
                    f"{trailing['acionar']}" if trailing
                    else " · AUTO TRAIL zerado (desligado nas configurações)"))
        return True, "todos os campos conferidos", False

    # ==================================================================
    #  O INSTRUMENTO DO TICKET — a conferência que faltava, e custou caro
    # ==================================================================
    #  20/08, 12:17. O cenário era MNQU6 (Micro Nasdaq, que negocia a ~29.700).
    #  Eu preenchi preço 29630, stop 29580, alvo 29780, quantidade 2, conferi
    #  tudo, e mandei. A Tradovate registrou:
    #
    #     #372662132 Comprar 2 MESU6 LMT em 29630.00 - Filled - 2/2
    #
    #  MESU6, não MNQU6. O ticket estava com o OUTRO instrumento selecionado, e
    #  eu nunca olhei para esse campo — preenchi preço e quantidade num
    #  formulário cujo ativo eu não tinha conferido. Uma compra limitada de MES
    #  a 29.630 num mercado que está em 7.770 é uma ordem a mercado disfarçada:
    #  preencheu na hora, e o resultado apareceu como (20.00) e depois (30.00)
    #  no P/L da conta.
    #
    #  E repare no que TODAS as minhas conferências disseram: "preço conferido",
    #  "quantidade conferida", "ATM conferida". Todas verdadeiras. Todas sobre o
    #  formulário errado. Conferir os campos sem conferir DE QUEM são os campos
    #  é o tipo de checagem que dá falsa segurança — a pior espécie.
    #
    #  Agora o ativo é o PRIMEIRO campo conferido, e a regra é dura: se eu não
    #  consigo ler o instrumento do ticket, ou não consigo colocar o certo lá,
    #  eu NÃO ENVIO. Ordem no instrumento errado não tem desfazer.
    _JS_ATIVO_DO_TICKET = r"""
    (function(alvo){
      function vis(el){try{var r=el.getBoundingClientRect();
        return r.width>0&&r.height>0;}catch(e){return false;}}
      function ehSimbolo(t){
        if(!t) return false;
        t=t.toUpperCase().trim();
        return /^[A-Z0-9]{1,5}[FGHJKMNQUVXZ][0-9]{1,2}$/.test(t)
            || /^[A-Z]{2,5}[0-9]{1,2}$/.test(t);
      }
      // O campo do instrumento é o input de BUSCA no topo do 'Chamado do
      // pedido': tem lupa ao lado e o valor é um ticker, nunca um número.
      //
      // 'PESQUISAR' É O ROTULO QUE A TRADOVATE EM PORTUGUES USA — e ele
      // faltava nesta lista. O efeito só aparecia DEPOIS DE ENVIAR uma ordem:
      // com o ticket já carregado, o campo tem valor ('MESU6') e era achado
      // pelo valor; quando a plataforma limpa o ticket, sobra o campo VAZIO
      // com o placeholder 'Pesquisar', que não casava com 'buscar' nem com
      // 'search' — o campo era PULADO, ninguém achava o instrumento, e a
      // ordem seguinte era recusada por segurança ("não consegui LER o
      // instrumento"). A trava estava certa; a leitura é que estava cega.
      var comValor=null, soBusca=null, ins=document.querySelectorAll('input');
      for(var i=0;i<ins.length;i++){
        var el=ins[i];
        if(!vis(el)) continue;
        var v=(el.value||'').trim();
        var ph=(el.getAttribute('placeholder')||'').toLowerCase();
        var busca=/(symbol|s[ií]mbolo|instrumento|buscar|pesquisar|pesquisa|search)/.test(ph);
        if(!ehSimbolo(v) && !busca) continue;
        var r=el.getBoundingClientRect();
        var cand={el:el, top:r.top, valor:v,
                  x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)};
        // DUAS FILAS, e a do VALOR sempre ganha. Alargar o placeholder para
        // 'pesquisar' faz outras caixas de busca da página entrarem na
        // disputa; um campo que JÁ MOSTRA um ticker é prova, um placeholder é
        // só indício. Sem esta separação, a correção de cegueira viraria uma
        // troca de instrumento — que é o erro mais caro dos dois.
        if(ehSimbolo(v)){
          if(!comValor || cand.top < comValor.top) comValor=cand;
        } else {
          if(!soBusca || cand.top < soBusca.top) soBusca=cand;
        }
      }
      var achado = comValor || soBusca;
      if(!achado) return JSON.stringify({achou:false});
      var res={achou:true, atual:achado.valor,
               x:achado.x, y:achado.y};
      if(alvo){
        // Escreve com o setter nativo, como nos outros campos, para o React
        // enxergar a mudança. O Enter é o que confirma a busca na Tradovate.
        var setter=Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,'value').set;
        var el=achado.el;
        el.focus();
        setter.call(el,'');
        el.dispatchEvent(new Event('input',{bubbles:true}));
        setter.call(el,String(alvo));
        el.dispatchEvent(new Event('input',{bubbles:true}));
        el.dispatchEvent(new Event('change',{bubbles:true}));
        res.escrito=String(el.value||'');
      }
      return JSON.stringify(res);
    })(%s)
    """

    def ler_ativo_do_ticket(self):
        """Qual instrumento está selecionado no 'Chamado do pedido'."""
        try:
            d = json.loads(self.avaliar_js(
                self._JS_ATIVO_DO_TICKET % "null") or "{}")
        except ConexaoPerdida:
            raise
        except Exception:
            return None
        return (d.get("atual") or "").strip().upper() if d.get("achou") else None

    @staticmethod
    def mesmo_instrumento(a, b):
        """MESU6 e MES são o mesmo; MESU6 e MNQU6 NÃO são.

        A comparação é pela RAIZ (as letras antes do mês/ano), e não pelos três
        primeiros caracteres: 'MES'[:3] e 'MNQ'[:3] são diferentes, mas
        'MESU6'[:3]='MES' e 'MNQU6'[:3]='MNQ' também — o que salvou aqui foi
        não comparar por prefixo curto em nenhum dos dois lados."""
        def raiz(s):
            s = str(s or "").strip().upper()
            # SEM DÍGITO, NÃO HÁ VENCIMENTO A REMOVER — e esta linha existe
            # porque 'Q' e 'N' também são códigos de mês: sem ela, 'MNQ'
            # (a raiz do Micro Nasdaq) era lida como 'MN', e deixava de casar
            # com 'MNQU6'. Só tiro mês e ano de quem tem ano.
            if not re.search(r"\d", s):
                return s
            m = re.match(r"^([A-Z]{1,5}?)[FGHJKMNQUVXZ]\d{1,2}$", s)
            return m.group(1) if m else s
        ra, rb = raiz(a), raiz(b)
        return bool(ra) and bool(rb) and ra == rb

    def garantir_ativo_no_ticket(self, ativo, pausa=0.8):
        """O ticket está no instrumento CERTO? Se não, coloca — e confere.

        Devolve (ok, motivo). `ok=False` significa NÃO ENVIE: ou eu não sei em
        que instrumento o ticket está, ou não consegui trocá-lo."""
        if not ativo:
            # Sem saber qual deveria ser, não há o que conferir — e também não
            # há como afirmar que está certo. Quem chama decide; aqui eu digo.
            return False, "não sei para qual ativo é esta ordem"
        atual = self.ler_ativo_do_ticket()
        if atual is None:
            return False, ("não consegui LER o instrumento no 'Chamado do "
                           "pedido'. Sem isso eu não sei em qual contrato a "
                           "ordem cairia — e ordem no instrumento errado não "
                           "tem desfazer")
        if self.mesmo_instrumento(atual, ativo):
            self.log(f"   ✅ instrumento do ticket: {atual} (é o do cenário).")
            return True, atual
        # Campo ACHADO e VAZIO é o estado normal logo depois de uma ordem: a
        # Tradovate limpa o ticket. Não é erro, e a frase não pode dizer que o
        # ticket "está em  " — o que ele está é sem instrumento nenhum.
        self.log(f"   🔁 o ticket está {('SEM instrumento' if not atual else 'em ' + atual)}"
                 f" e esta ordem é de {ativo.upper()} — preenchendo o "
                 f"instrumento antes de tudo.")
        try:
            self.avaliar_js(self._JS_ATIVO_DO_TICKET % json.dumps(str(ativo)))
            time.sleep(pausa)
            # ENTER confirma a busca; sem ele a Tradovate mantém o anterior.
            self.cdp("Input.dispatchKeyEvent",
                     {"type": "keyDown", "key": "Enter",
                      "code": "Enter", "windowsVirtualKeyCode": 13})
            self.cdp("Input.dispatchKeyEvent",
                     {"type": "keyUp", "key": "Enter",
                      "code": "Enter", "windowsVirtualKeyCode": 13})
            time.sleep(pausa)
        except ConexaoPerdida:
            raise
        except Exception as e:
            return False, f"não consegui escrever o instrumento no ticket: {e}"
        depois = self.ler_ativo_do_ticket()
        if depois and self.mesmo_instrumento(depois, ativo):
            self.log(f"   ✅ instrumento trocado e conferido: {depois}.")
            return True, depois
        return False, (f"tentei trocar o ticket para {ativo.upper()} e ele "
                       f"continua em {depois or 'ilegível'}. NÃO envio: os "
                       "preços deste cenário não fazem sentido no outro "
                       "contrato")

    def _preencher_ordem_atm(self, palavra_dir, entrada, qtd, tipo, tick,
                             t_stop, t_alvo, trailing, pausa, ativo=None):
        """Deixa o ticket PRONTO e conferido. Não envia nada.

        Devolve (ok, erro, sem_painel). Separado do envio de propósito: enquanto só se
        preenche, repetir é seguro — nenhuma ordem foi para o mercado. É essa
        separação que permite tentar de novo quando o Chrome engasga."""
        if not self._garantir_formulario():
            return False, "formulário do ticket não está à vista", False

        # O ATIVO VEM ANTES DE TUDO. Preencher preço e quantidade num
        # formulário cujo instrumento eu não conferi é o erro de 20/08: todas
        # as conferências passaram, e a ordem foi para o contrato errado.
        if ativo:
            ok_ativo, motivo_ativo = self.garantir_ativo_no_ticket(ativo)
            if not ok_ativo:
                self.log(f"   ⛔ {motivo_ativo}")
                # RECUSA, não indisponibilidade: mandar pelo caminho antigo
                # não conserta o instrumento errado — só espalha o erro por
                # três ordens em vez de uma.
                return False, motivo_ativo, False

        d = self.localizar(palavra_dir)
        if not d:
            return False, f"botão '{palavra_dir}' não encontrado", False
        self.clicar_pagina(d["x"], d["y"])
        time.sleep(pausa)

        if tipo:
            self._selecionar_tipo(tipo, pausa)

        # PREÇO E QUANTIDADE NA MESMA IDA. O preço tem tolerância de meio
        # tick: a plataforma arredonda para o tick dela, e recusar a ordem por
        # causa disso seria recusar por estar certa.
        pedidos = [(self.ROTULO_PRECO, 0, entrada)]
        if qtd is not None:
            pedidos.append((self.ROTULO_QTD, 0, int(qtd)))
        res = self.campos_por_rotulo(pedidos)
        if res[0].get("estado") != "OK":
            return False, f"campo PREÇO: {res[0].get('estado', 'SEM_RESPOSTA')}", False
        if not valores_batem(entrada, res[0].get("valor", ""), float(tick) / 2):
            return False, (f"campo PREÇO: escrevi {entrada!r} e o campo ficou "
                           f"{res[0].get('valor')!r}"), False
        self.log(f"   ✏️ preço {entrada} conferido no campo "
                 f"({res[0].get('valor')}).")
        if qtd is not None:
            if res[1].get("estado") != "OK":
                return False, f"campo QTD: {res[1].get('estado', 'SEM_RESPOSTA')}", False
            if not valores_batem(int(qtd), res[1].get("valor", "")):
                return False, (f"campo QTD: escrevi {int(qtd)} e o campo ficou "
                               f"{res[1].get('valor')!r}"), False
            self.log(f"   ✏️ quantidade {int(qtd)} conferida no campo.")
        time.sleep(pausa)

        return self.configurar_atm(t_stop, t_alvo, trailing, pausa)

    def enviar_ordem_com_atm(self, direcao, entrada, stop, alvo, tick,
                             qtd=None, enviar=False, tipo="LIMITE", pausa=0.5,
                             trailing=None, tentativas=2, ativo=None):
        """A ordem INTEIRA numa submissão só: entrada + stop + alvo + OCO.

        Devolve o mesmo formato do bracket antigo, para quem chama não precisar
        saber por qual caminho foi:
          {ok, enviadas, faltando, erro, exposto, ticks_stop, ticks_alvo}
        """
        resultado = {"ok": False, "enviadas": [], "faltando": [], "erro": None,
                     "exposto": False, "ticks_stop": None, "ticks_alvo": None,
                     "via": "ATM"}
        t_stop, t_alvo, erro = plano_atm(direcao, entrada, stop, alvo, tick)
        if erro:
            resultado["erro"] = erro
            resultado["faltando"] = ["ENTRADA", "STOP", "ALVO"]
            # Cenário incoerente é RECUSA, não falta de recurso: mandar o
            # mesmo cenário por outro caminho não o torna coerente.
            resultado["recusa_de_seguranca"] = True
            self.log(f"   ⛔ não envio: {erro}")
            return resultado
        resultado["ticks_stop"], resultado["ticks_alvo"] = t_stop, t_alvo

        long_ = str(direcao).upper() in ("BUY", "COMPRA", "COMPRAR", "C", "LONG")
        palavra_dir = "Comprar" if long_ else "Vender"
        rotulo_ativo = f" [{ativo}]" if ativo else ""
        self.log(f"📦 Ordem ÚNICA com ATM [{'ENVIAR' if enviar else 'dry'}]: "
                 f"{palavra_dir} {tipo} @ {entrada}{rotulo_ativo} · stop {t_stop} ticks "
                 f"({stop}) · alvo {t_alvo} ticks ({alvo}) · qtd={qtd}"
                 + (" · com AUTO TRAIL" if trailing else ""))

        if enviar and not qtd:
            resultado["erro"] = "quantidade não informada"
            resultado["faltando"] = ["ENTRADA", "STOP", "ALVO"]
            self.log("   ⚠️ QTD é obrigatória para enviar.")
            return resultado

        # PREENCHER PODE SER REPETIDO; ENVIAR, NÃO.
        # 19/08, 20:12: preço e quantidade já estavam conferidos na tela e o
        # ciclo morreu em "sem resposta do CDP" no passo seguinte. A ordem se
        # perdeu por um engasgo de socket, com o ticket praticamente pronto.
        # Enquanto NADA foi enviado, tentar de novo (reconectando) não tem
        # risco nenhum — e é a diferença entre operar e não operar.
        ok, det, sem_painel = False, "não tentei", False
        for tentativa in range(max(1, int(tentativas))):
            try:
                ok, det, sem_painel = self._preencher_ordem_atm(
                    palavra_dir, entrada, qtd, tipo, tick, t_stop, t_alvo,
                    trailing, pausa, ativo=ativo)
            except ConexaoPerdida as e:
                ok, det, sem_painel = (
                    False, f"a ligação com o Chrome engasgou: {e}", False)
            if ok:
                break
            if tentativa + 1 < max(1, int(tentativas)):
                self.log(f"   🔁 {det} — refazendo o preenchimento "
                         f"({tentativa + 2}ª tentativa). Nada foi enviado "
                         "ainda, então repetir é seguro.")
                try:
                    self.conectar()
                except Exception:
                    pass
                time.sleep(1.0)
        if not ok:
            resultado["erro"] = det
            resultado["faltando"] = ["ENTRADA", "STOP", "ALVO"]
            resultado["sem_atm"] = bool(sem_painel)
            # RECUSA NÃO É INDISPONIBILIDADE, e confundir as duas quase custou
            # caro em 19/08: a ATM se recusou a enviar (por um motivo que era
            # meu, mas ainda assim uma recusa) e o programa CAIU PARA O CAMINHO
            # ANTIGO, que manda a entrada primeiro e a proteção depois. Ou
            # seja: a trava disse "não mando assim" e a reserva tentou mandar
            # assim mesmo. Só há reserva quando o painel de ATMs não existe.
            resultado["recusa_de_seguranca"] = not sem_painel
            self.log(f"   ⛔ {det}. NÃO enviei a entrada: entrada sem proteção "
                     "anexada é exatamente o que este caminho veio eliminar.")
            return resultado

        if not enviar:
            resultado["ok"] = True
            resultado["enviadas"] = ["PRE-VISUALIZACAO"]
            self.log("   👀 Formulário preenchido e conferido. NÃO enviei "
                     "(modo teste) — confira na tela.")
            return resultado

        try:
            e = self.localizar("Enviar")
            if not e:
                resultado["erro"] = "botão 'Enviar' não encontrado"
                resultado["faltando"] = ["ENTRADA", "STOP", "ALVO"]
                self.log("   ❌ botão 'Enviar' não encontrado — nada foi enviado.")
                return resultado
            self.clicar_pagina(e["x"], e["y"])
        except ConexaoPerdida as ex:
            # AQUI a incerteza é real: o clique pode ter saído ou não. Dizer
            # "não enviei" seria um palpite, e o palpite errado deixa uma ordem
            # viva sem ninguém sabendo. Manda conferir.
            resultado["erro"] = (f"a ligação caiu no momento do envio ({ex}) — "
                                 "NÃO SEI dizer se a ordem saiu")
            resultado["incerto"] = True
            self.log("   ⚠️ A conexão caiu exatamente no clique de Enviar. "
                     "NÃO tenho como afirmar se a ordem foi ou não. CONFIRA A "
                     "PLATAFORMA antes de qualquer coisa.")
            return resultado
        resultado["ok"] = True
        resultado["enviadas"] = ["ENTRADA", "STOP", "ALVO"]
        self.log("   ✅ Enviada. Stop e alvo foram junto, anexados pela "
                 "própria Tradovate — o OCO é dela, não meu.")
        # Retorna automaticamente ao formulário do ticket clicando na setinha de volta
        try:
            time.sleep(0.6)
            self._garantir_formulario(tentativas=2)
        except Exception:
            pass
        return resultado

    def enviar_bracket_ticket(self, direcao, entrada, stop, alvo, qtd=None,
                              enviar=False, pausa=0.7, ativo=None):
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
        rotulo_ativo = f" [{ativo}]" if ativo else ""
        self.log(f"📦 Bracket {'LONG' if long_ else 'SHORT'}{rotulo_ativo} via ticket "
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
            tentativas = 2 if (enviar and nome in ("STOP", "ALVO")) else 1
            perna_ok = False
            for t in range(tentativas):
                if t:
                    espera = 1.5 * t
                    self.log(f"   🔁 {nome}: nova tentativa ({t + 1}/{tentativas}) "
                             f"em {espera:.1f}s — a proteção não pode ficar de fora.")
                    time.sleep(espera)
                try:
                    perna_ok = self.enviar_ordem_ticket(preco, dirr, tipo, qtd, enviar, pausa=pausa, ativo=ativo)
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
    # ONDE PROCURAR O CHROME: a lista vem da camada de plataforma, porque o
    # caminho muda de sistema (C:\Program Files... no Windows,
    # /Applications/Google Chrome.app no macOS). Chromium e Edge entram como
    # reserva: falam o mesmo protocolo CDP.
    if chrome_path:
        candidatos = [chrome_path]
    else:
        try:
            import plataforma
            candidatos = plataforma.caminhos_chrome()
        except Exception:
            candidatos = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
    exe = next((c for c in candidatos if c and os.path.exists(c)), None)
    if not exe:
        log("❌ Google Chrome não encontrado. Informe o caminho em chrome_path=.")
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
