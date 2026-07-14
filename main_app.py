import time, json, threading, customtkinter as ctk, tkinter as tk, os, subprocess, sys, webbrowser
import base64
import datetime
import ctypes
import requests
from io import BytesIO
from PIL import ImageGrab, Image
import pyttsx3
from google import genai
from google.genai import types

# --------------------------------------------------------------------
# DEPENDÊNCIA WINDOWS (foco de janela + criptografia DPAPI)
# --------------------------------------------------------------------
try:
    import win32gui
    import win32con
    import win32crypt
    PYWIN32_DISPONIVEL = True
except ImportError:
    PYWIN32_DISPONIVEL = False

# --------------------------------------------------------------------
# CONFIGURAÇÕES E PERSISTÊNCIA DE DADOS
# --------------------------------------------------------------------
# --------------------------------------------------------------------
# MODO DESENVOLVEDOR (oculto no app final)
# --------------------------------------------------------------------
# Ativa recursos internos (backup/restauração dos dados do usuário) apenas
# quando a variável de ambiente SMC_DEV_MODE=1 está definida. No executável
# entregue ao cliente, nada disso aparece na interface.
#
# Para ativar durante o desenvolvimento, no cmd:
#     set SMC_DEV_MODE=1
#     python main_app.py
MODO_DEV = os.environ.get("SMC_DEV_MODE") == "1"

def criar_backup_dados():
    """Compacta toda a pasta de dados do usuário (config, diário, sessão do
    WhatsApp) num .zip com timestamp — útil antes de atualizar o app."""
    import zipfile
    origem = pasta_dados_usuario()
    carimbo = time.strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(os.path.expanduser("~"), f"SMC_backup_{carimbo}.zip")
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for raiz, _, arquivos in os.walk(origem):
            for arq in arquivos:
                caminho = os.path.join(raiz, arq)
                # node_modules é pesado e reinstalável — não vai no backup
                if "node_modules" in caminho:
                    continue
                z.write(caminho, os.path.relpath(caminho, origem))
    return destino

def restaurar_backup_dados(caminho_zip):
    import zipfile
    destino = pasta_dados_usuario()
    with zipfile.ZipFile(caminho_zip, "r") as z:
        z.extractall(destino)
    return destino

# --------------------------------------------------------------------
# VERIFICAÇÃO DE ATUALIZAÇÃO
# --------------------------------------------------------------------
# ====================================================================
# CHECKLIST DE RELEASE — fazer os 3 passos, sempre nesta ordem:
#   1. Incrementar VERSAO_ATUAL abaixo (ex: 1.0.0 -> 1.1.0)
#   2. Compilar o .exe e subir o .zip na pasta do Google Drive
#   3. Editar o gist e trocar o campo "versao" para o MESMO número:
#      https://gist.github.com/JOSEVANSANTANA/186b63b2de425d236abef4afcf9d1b33
#
# Se o gist ficar com número MAIOR que o VERSAO_ATUAL de um cliente,
# ele vê o banner verde de atualização. Se ficarem iguais, não vê nada.
# ====================================================================
VERSAO_ATUAL = "1.6.5"

# ====================================================================
# >>> COLE AQUI A URL DO SEU ARQUIVO versao.json <<<
# ====================================================================
# Deixe "" (vazio) para desativar a checagem de atualização.
#
# ATENÇÃO: essa URL precisa devolver o CONTEÚDO PURO do JSON.
# O Google Drive NÃO funciona aqui (devolve página HTML de confirmação).
# Use um GitHub Gist: crie o gist, clique em "Raw", copie a URL da barra
# de endereços. Ela se parece com:
#   https://gist.githubusercontent.com/SEU_USUARIO/ID/raw/versao.json
#
# O arquivo .zip do PROGRAMA pode continuar normalmente no Google Drive —
# o link dele vai DENTRO do JSON, no campo "url_download".
# Sem o hash de commit no caminho: assim o gist sempre devolve a versão MAIS
# RECENTE do JSON. Se a URL tivesse o hash (.../raw/8a9b0c.../versao.json),
# ela ficaria congelada no conteúdo daquele momento e os clientes nunca
# veriam as atualizações futuras.
URL_VERSAO = "https://gist.githubusercontent.com/JOSEVANSANTANA/186b63b2de425d236abef4afcf9d1b33/raw/versao.json"

def _comparar_versoes(v1: str, v2: str) -> int:
    """Retorna 1 se v1 > v2, -1 se v1 < v2, 0 se iguais. Compara 1.10.0 > 1.9.0
    corretamente (comparação numérica, não alfabética)."""
    def partes(v):
        try:
            return [int(x) for x in v.strip().split(".")]
        except ValueError:
            return [0]
    a, b = partes(v1), partes(v2)
    tamanho = max(len(a), len(b))
    a += [0] * (tamanho - len(a))
    b += [0] * (tamanho - len(b))
    for x, y in zip(a, b):
        if x > y:
            return 1
        if x < y:
            return -1
    return 0

def verificar_nova_versao():
    """Consulta o JSON remoto. Retorna dict com info da nova versão, ou None."""
    if not URL_VERSAO:
        return None
    try:
        resposta = requests.get(URL_VERSAO, timeout=8)
        dados = resposta.json()
        versao_remota = str(dados.get("versao", "")).strip()
        if versao_remota and _comparar_versoes(versao_remota, VERSAO_ATUAL) > 0:
            return {
                "versao": versao_remota,
                "url_download": dados.get("url_download", ""),
                "notas": dados.get("notas", ""),
            }
    except Exception:
        pass  # sem internet ou JSON inválido: silencioso, não atrapalha o uso
    return None

def diretorio_da_aplicacao():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def pasta_dados_usuario():
    base = os.environ.get('APPDATA') or os.path.expanduser("~")
    pasta = os.path.join(base, "SMC_Quant_Pro")
    os.makedirs(pasta, exist_ok=True)
    return pasta

DIR_ORIGEM_MOTOR = os.path.join(diretorio_da_aplicacao(), "motor")
DIR_DADOS_MOTOR = os.path.join(pasta_dados_usuario(), "motor")
CONFIG_FILE = os.path.join(pasta_dados_usuario(), "config_smc.json")
PERFORMANCE_FILE = os.path.join(pasta_dados_usuario(), "performance_db.json")
SIGNALS_LOG_FILE = os.path.join(pasta_dados_usuario(), "signals_log.json")
POSITIONS_FILE = os.path.join(pasta_dados_usuario(), "positions_db.json")
LICENCA_FILE = os.path.join(pasta_dados_usuario(), "licenca.json")

# ====================================================================
# SISTEMA DE LICENÇA
# ====================================================================
# >>> COLE AQUI A URL DO SEU SERVIDOR DE LICENÇAS (Render) <<<
# Ex.: "https://smc-licenca.onrender.com"
URL_SERVIDOR_LICENCA = "https://smc-quant-pro.onrender.com"

# Dias que o app funciona offline após a última validação bem-sucedida,
# antes de exigir internet novamente (tolerância combinada: 7 dias).
DIAS_TOLERANCIA_OFFLINE = 7


def gerar_id_maquina():
    """ID estável e único desta máquina, derivado do hardware do Windows.
    Não muda entre execuções, então a licença "casa" com o computador."""
    import hashlib
    partes = []
    try:
        # UUID do fabricante da placa — estável e único por máquina
        saida = subprocess.check_output(
            "wmic csproduct get uuid", shell=True, stderr=subprocess.DEVNULL
        ).decode(errors="ignore")
        linhas = [l.strip() for l in saida.splitlines() if l.strip() and "UUID" not in l]
        if linhas:
            partes.append(linhas[0])
    except Exception:
        pass
    try:
        partes.append(os.environ.get("COMPUTERNAME", ""))
        partes.append(str(os.environ.get("PROCESSOR_IDENTIFIER", "")))
    except Exception:
        pass
    base = "|".join(p for p in partes if p) or "fallback-sem-hardware"
    return hashlib.sha256(base.encode()).hexdigest()[:32]


def nome_desta_maquina():
    return os.environ.get("COMPUTERNAME", "PC-desconhecido")


def carregar_licenca_local():
    try:
        with open(LICENCA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def salvar_licenca_local(chave):
    dados = {
        "chave": chave,
        "maquina_id": gerar_id_maquina(),
        "validada_em": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(LICENCA_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def ativar_licenca_online(chave):
    """Chama o servidor para ativar. Retorna (sucesso: bool, mensagem: str)."""
    if not URL_SERVIDOR_LICENCA:
        # Sem servidor configurado, o app opera livre (modo desenvolvimento).
        return True, "Servidor de licença não configurado (modo livre)."
    try:
        resp = requests.post(
            f"{URL_SERVIDOR_LICENCA.rstrip('/')}/ativar",
            json={
                "chave": chave.strip(),
                "maquina_id": gerar_id_maquina(),
                "nome_maquina": nome_desta_maquina(),
            },
            timeout=15,
        )
        dados = resp.json()
        if dados.get("ok"):
            salvar_licenca_local(chave.strip())
            return True, dados.get("mensagem", "Licença ativada.")
        return False, dados.get("erro", "Não foi possível ativar a licença.")
    except Exception as e:
        return False, f"Não consegui contatar o servidor de licença: {e}"


def verificar_licenca_valida():
    """Chamado ao abrir o app. Retorna (liberado: bool, motivo: str).

    Lógica de tolerância offline:
      • Se nunca ativou -> precisa ativar (bloqueado).
      • Se já ativou -> tenta revalidar online; se conseguir, renova o prazo.
      • Se estiver offline mas dentro dos DIAS_TOLERANCIA -> libera.
      • Se passou da tolerância sem revalidar -> pede internet.
    """
    if not URL_SERVIDOR_LICENCA:
        return True, "modo livre"

    local = carregar_licenca_local()
    if not local or not local.get("chave"):
        return False, "sem_licenca"

    # Máquina diferente da que ativou? (arquivo copiado para outro PC)
    if local.get("maquina_id") != gerar_id_maquina():
        return False, "maquina_diferente"

    # Tenta revalidar online (renova a janela offline)
    try:
        resp = requests.post(
            f"{URL_SERVIDOR_LICENCA.rstrip('/')}/validar",
            json={"chave": local["chave"], "maquina_id": gerar_id_maquina()},
            timeout=10,
        )
        if resp.json().get("ok"):
            salvar_licenca_local(local["chave"])  # renova validada_em
            return True, "online"
        return False, "revogada"
    except Exception:
        # Sem internet: aplica a tolerância offline
        try:
            validada = datetime.datetime.fromisoformat(local["validada_em"])
            dias = (datetime.datetime.now() - validada).days
            if dias <= DIAS_TOLERANCIA_OFFLINE:
                return True, f"offline_ok ({DIAS_TOLERANCIA_OFFLINE - dias} dias restantes)"
            return False, "offline_expirado"
        except Exception:
            return False, "erro_local"

BAILEYS_URL = "http://localhost:3939"
BAILEYS_API_URL = f"{BAILEYS_URL}/enviar-relatorio"


def carregar_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def salvar_config(dados: dict):
    atual = carregar_config()
    atual.update(dados)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False, indent=2)

# --------------------------------------------------------------------
# CRIPTOGRAFIA DA API KEY VIA WINDOWS DPAPI
# --------------------------------------------------------------------
# DPAPI amarra a criptografia à conta do Windows do usuário — sem precisar
# gerar/guardar uma chave separada (que seria mais um segredo pra vazar).
# Só o mesmo usuário, na mesma máquina, consegue descriptografar de volta.
def dpapi_encrypt(texto: str) -> str:
    if not PYWIN32_DISPONIVEL or not texto:
        return texto
    dados = texto.encode('utf-8')
    blob = win32crypt.CryptProtectData(dados, "SMC_Quant_Pro_APIKey", None, None, None, 0)
    return base64.b64encode(blob).decode('utf-8')

def dpapi_decrypt(texto_cifrado: str) -> str:
    if not PYWIN32_DISPONIVEL or not texto_cifrado:
        return texto_cifrado
    try:
        blob = base64.b64decode(texto_cifrado)
        _, dados = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
        return dados.decode('utf-8')
    except Exception:
        return ""

def carregar_api_key() -> str:
    cfg = carregar_config()
    cifrado = cfg.get("gemini_api_key_enc")
    if cifrado:
        return dpapi_decrypt(cifrado)
    return ""

def salvar_api_key(api_key_texto: str):
    salvar_config({"gemini_api_key_enc": dpapi_encrypt(api_key_texto)})

# --------------------------------------------------------------------
# MÓDULO DE APRENDIZADO (FEEDBACK LOOP) — agora com R-múltiplo
# --------------------------------------------------------------------
def carregar_performance():
    if os.path.exists(PERFORMANCE_FILE):
        try:
            with open(PERFORMANCE_FILE, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, list):
                # Filtra qualquer entrada malformada (ex: de uma versão antiga
                # do arquivo, ou escrita parcial) — nunca confia cegamente em
                # dado persistido em disco.
                return [op for op in dados if isinstance(op, dict) and "resultado" in op]
        except Exception:
            pass
    return []

# --------------------------------------------------------------------
# VALOR POR PONTO DOS ATIVOS (futuros) — usado no cálculo de contratos
# --------------------------------------------------------------------
# Cada tick/ponto de um contrato futuro vale um valor diferente em US$.
# Sem isso, o dimensionamento de posição seria genérico e errado.
# A identificação do ativo vem do próprio gráfico (campo asset_symbol).
# --------------------------------------------------------------------
# PALETA INSTITUCIONAL DO DASHBOARD
# --------------------------------------------------------------------
# Fundo profundo, cards levemente elevados, verde neon como acento de
# resultado positivo e vermelho para negativo. Alto contraste para leitura
# rápida sob pressão, sem cansar a vista em sessões longas.
COR = {
    "fundo":     "#0a0e14",   # fundo da aba
    "card":      "#12161f",   # superfície dos painéis
    "borda":     "#2a2f3a",   # bordas sutis
    "input":     "#1a1f2b",   # campos de entrada
    "texto":     "#e6edf3",   # texto principal
    "dim":       "#8a92a5",   # rótulos e texto secundário
    "verde":     "#00E676",   # positivo / acento da marca
    "verde_esc": "#1f6b3a",   # botões e bordas de destaque
    "vermelho":  "#FF1744",   # negativo
    "amarelo":   "#ffcc66",   # pendente / atenção
}

VALOR_POR_PONTO = {
    "MES": 5.0,    # Micro E-mini S&P 500
    "ES": 50.0,    # E-mini S&P 500
    "MNQ": 2.0,    # Micro E-mini Nasdaq-100
    "NQ": 20.0,    # E-mini Nasdaq-100
    "MYM": 0.5,    # Micro E-mini Dow
    "YM": 5.0,     # E-mini Dow
    "M2K": 0.5,    # Micro E-mini Russell 2000
    "RTY": 50.0,   # E-mini Russell 2000
}
VALOR_POR_PONTO_PADRAO = 5.0  # fallback se o ativo não for reconhecido

def valor_por_ponto_do_ativo(asset_symbol: str) -> float:
    """Resolve o valor por ponto a partir do ticker lido no gráfico.
    Ex: 'MESU6' -> procura o prefixo 'MES' na tabela."""
    if not asset_symbol:
        return VALOR_POR_PONTO_PADRAO
    simbolo = asset_symbol.upper().strip()
    # Tenta casar o prefixo mais longo primeiro (ex: MES antes de ES)
    for prefixo in sorted(VALOR_POR_PONTO.keys(), key=len, reverse=True):
        if simbolo.startswith(prefixo):
            return VALOR_POR_PONTO[prefixo]
    return VALOR_POR_PONTO_PADRAO

def calcular_contratos(entry, stop, asset_symbol, margem, risco_pct, drawdown_maximo):
    """
    Dimensiona a posição com base no plano da mesa:
    - risco em US$ por trade = margem × risco_pct%
    - risco por contrato = distância até o stop (pontos) × valor por ponto do ativo
    - contratos = risco permitido ÷ risco por contrato
    Nunca deixa o risco de um único trade ultrapassar o drawdown máximo.
    Retorna dict com os detalhes para exibir na mensagem.
    """
    vpp = valor_por_ponto_do_ativo(asset_symbol)
    if entry is None or stop is None or entry == stop or not margem:
        return {"contratos": 0, "risco_usd": 0, "risco_por_contrato": 0,
                "valor_por_ponto": vpp, "pontos_risco": 0}

    risco_usd_permitido = margem * (risco_pct / 100.0)

    # Trava de segurança: o risco por trade nunca deve exceder o drawdown
    # máximo configurado para a conta da mesa.
    if drawdown_maximo and risco_usd_permitido > drawdown_maximo:
        risco_usd_permitido = drawdown_maximo

    pontos_risco = abs(entry - stop)
    risco_por_contrato = pontos_risco * vpp
    contratos = int(risco_usd_permitido // risco_por_contrato) if risco_por_contrato > 0 else 0
    contratos = max(contratos, 0)

    # Risco REAL da posição = o que os contratos dimensionados de fato arriscam
    # (nunca ultrapassa o teto permitido pelo plano, pois os contratos são
    # arredondados para baixo). É este o número honesto para mostrar ao trader.
    risco_real_usd = round(contratos * risco_por_contrato, 2)

    return {
        "contratos": contratos,
        "risco_usd": round(risco_usd_permitido, 2),   # teto permitido pelo plano
        "risco_real_usd": risco_real_usd,             # risco efetivo dos contratos
        "risco_por_contrato": round(risco_por_contrato, 2),
        "valor_por_ponto": vpp,
        "pontos_risco": round(pontos_risco, 2),
    }

def calcular_r_multiplo(direcao, entry, stop, preco_saida):
    risco_pontos = abs(entry - stop)
    if risco_pontos == 0:
        return 0.0
    if direcao == "BUY":
        ganho_pontos = preco_saida - entry
    else:
        ganho_pontos = entry - preco_saida
    return round(ganho_pontos / risco_pontos, 2)

def salvar_resultado_performance(direcao, entry, stop, tp, preco_saida, resultado, ativo="DESCONHECIDO"):
    """Registra o desfecho HIPOTÉTICO de um cenário do robô (independente de o
    trader ter acatado). Guarda o P&L em US$ que teria sido obtido usando o
    sizing do plano — é a base do comparativo 'e se eu tivesse acatado tudo'."""
    r_multiplo = calcular_r_multiplo(direcao, entry, stop, preco_saida)

    plano = carregar_config().get("plano_trading", {})
    sizing = calcular_contratos(entry, stop, ativo, plano.get("margem", 0),
                                 plano.get("risco_pct", 1.0), plano.get("drawdown_maximo", 0))
    contratos = max(sizing["contratos"], 1)
    vpp = valor_por_ponto_do_ativo(ativo)
    pontos = (preco_saida - entry) if direcao == "BUY" else (entry - preco_saida)
    pnl_usd = round(pontos * vpp * contratos, 2)

    db = carregar_performance()
    db.append({
        "data_hora": time.strftime('%d/%m/%Y %H:%M:%S'),
        "direcao": direcao,
        "ativo": ativo,
        "entry": entry,
        "stop": stop,
        "alvo": tp,
        "preco_saida": preco_saida,
        "resultado": resultado,
        "r_multiplo": r_multiplo,
        "contratos": contratos,
        "pnl_usd": pnl_usd,
    })
    db = db[-200:]
    with open(PERFORMANCE_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def calcular_max_drawdown_r(valores_r_acumulados):
    if not valores_r_acumulados:
        return 0.0
    pico = float("-inf")
    max_dd = 0.0
    for v in valores_r_acumulados:
        pico = max(pico, v)
        max_dd = max(max_dd, pico - v)
    return round(max_dd, 2)

# --------------------------------------------------------------------
# DIÁRIO DE TRADER — posições reais (acatadas do robô ou manuais)
# --------------------------------------------------------------------
# Cada posição acatada/manual vira um registro "ABERTA" que recebe P&L ao
# vivo a cada atualização de preço do ciclo, e ao fechar (stop/alvo/manual)
# realiza o resultado no dia. É isso que alimenta o dashboard de verdade.
def _parse_dt(texto):
    """Converte 'dd/mm/aaaa HH:MM' para datetime. Retorna None se falhar."""
    if not texto:
        return None
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'):
        try:
            return datetime.datetime.strptime(texto, fmt)
        except ValueError:
            continue
    return None

def inicio_do_ciclo():
    """Momento em que o ciclo de 5 dias foi (re)iniciado. Tudo anterior a isso
    é histórico arquivado e NÃO aparece no dashboard."""
    plano = carregar_config().get("plano_trading", {})
    marca = plano.get("ciclo_inicio")
    if marca:
        try:
            return datetime.datetime.fromisoformat(marca)
        except ValueError:
            pass
    return None

def _dentro_do_ciclo(registro, campo_data="data_criacao"):
    inicio = inicio_do_ciclo()
    if inicio is None:
        return True  # sem ciclo definido: mostra tudo
    dt = _parse_dt(registro.get(campo_data) or registro.get("data_hora"))
    # Registro SEM data válida = dado legado (gravado por versões antigas, antes
    # deste campo existir). Ele NÃO pertence ao ciclo atual — se o tratássemos
    # como "dentro", ele voltaria a somar no dashboard mesmo depois de o trader
    # clicar em "Reiniciar ciclo". Por isso, com um ciclo já definido, um
    # registro sem data é considerado FORA do ciclo.
    if dt is None:
        return False
    return dt >= inicio

def posicoes_do_ciclo():
    """Posições criadas a partir do início do ciclo atual."""
    return [p for p in carregar_posicoes() if _dentro_do_ciclo(p, "data_criacao")]

def pnl_usd_do_registro(op):
    """P&L em US$ de um registro de performance (cenário hipotético do robô).

    Registros gravados antes da v1.2 não possuem o campo 'pnl_usd'. Em vez de
    tratá-los como zero (o que zerava o comparativo), recalculamos a partir de
    entrada, saída, ativo e contratos.
    """
    if op.get("pnl_usd") is not None:
        return op["pnl_usd"]
    entry = op.get("entry")
    saida = op.get("preco_saida")
    if entry is None or saida is None:
        return 0.0
    direcao = op.get("direcao", "BUY")
    ativo = op.get("ativo", "DESCONHECIDO")
    contratos = op.get("contratos")
    if not contratos:
        plano = carregar_config().get("plano_trading", {})
        sizing = calcular_contratos(entry, op.get("stop", entry), ativo,
                                     plano.get("margem", 0), plano.get("risco_pct", 1.0),
                                     plano.get("drawdown_maximo", 0))
        contratos = max(sizing["contratos"], 1)
    pontos = (saida - entry) if direcao == "BUY" else (entry - saida)
    return round(pontos * valor_por_ponto_do_ativo(ativo) * contratos, 2)

def performance_do_ciclo():
    """Resultados hipotéticos do robô dentro do ciclo atual (todas as sugestões,
    acatadas ou não) — usado no comparativo."""
    return [op for op in carregar_performance() if _dentro_do_ciclo(op, "data_hora")]

def carregar_posicoes():
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, list):
                return [p for p in dados if isinstance(p, dict) and "id" in p]
        except Exception:
            pass
    return []

def salvar_posicoes(lista):
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(lista[-500:], f, ensure_ascii=False, indent=2)

def abrir_posicao(origem, direcao, ativo, entry, stop, tp1, tp2, contratos, status_inicial="ABERTA"):
    """
    status_inicial:
      - "PENDENTE": aguardando o preço tocar a região de entrada (sinais acatados).
        Só vira ABERTA (e passa a contar P&L) quando o preço de fato chega lá.
      - "ABERTA": posição já executada (entrada manual, trader já está posicionado).
    """
    lista = carregar_posicoes()
    pos = {
        "id": int(time.time() * 1000),
        "origem": origem,  # "ROBO" (acatou sugestão) ou "MANUAL" (diário)
        "direcao": direcao,
        "ativo": ativo or "DESCONHECIDO",
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "contratos": max(int(contratos or 1), 1),
        "vpp": valor_por_ponto_do_ativo(ativo),
        "status": status_inicial,
        "preco_atual": entry,
        "pnl_atual": 0.0,
        "data_criacao": time.strftime('%d/%m/%Y %H:%M'),
        "data_abertura": time.strftime('%d/%m/%Y %H:%M') if status_inicial == "ABERTA" else None,
        "data_fechamento": None,
        "pnl_final": None,
    }
    lista.append(pos)
    salvar_posicoes(lista)
    return pos

def calcular_pnl_posicao(pos, preco):
    pontos = (preco - pos["entry"]) if pos["direcao"] == "BUY" else (pos["entry"] - preco)
    return round(pontos * pos["vpp"] * pos["contratos"], 2)

def atualizar_posicoes_com_preco(preco, ativo=None):
    """
    Governa o ciclo de vida das posições do diário, comparando com o preço real:
      PENDENTE -> ABERTA    (o preço tocou a região de entrada: execução confirmada)
      PENDENTE -> CANCELADA (o preço rompeu o stop ANTES de tocar a entrada)
      ABERTA   -> FECHADA   (bateu stop ou alvo final)
    Só posições ABERTAS acumulam P&L — uma sugestão acatada que o preço nunca
    alcançou não pode contar como operação em andamento.
    Retorna lista de eventos para notificação.
    """
    if preco is None:
        return []
    lista = carregar_posicoes()
    eventos = []
    for pos in lista:
        status = pos.get("status")
        if status not in ("PENDENTE", "ABERTA"):
            continue
        # Não marca P&L de MES com preço de MNQ.
        if ativo and pos.get("ativo") not in (None, "", "DESCONHECIDO"):
            if not pos["ativo"].upper().startswith(ativo.upper()[:3]):
                continue

        direcao = pos["direcao"]
        bateu_stop = (direcao == "BUY" and preco <= pos["stop"]) or \
                     (direcao == "SELL" and preco >= pos["stop"])

        # ---------- PENDENTE: aguardando execução ----------
        if status == "PENDENTE":
            tocou_entrada = (direcao == "BUY" and preco <= pos["entry"]) or \
                             (direcao == "SELL" and preco >= pos["entry"])
            if bateu_stop:
                # Stop rompido antes da entrada: o setup nunca foi executado.
                pos["status"] = "CANCELADA"
                pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
                pos["pnl_final"] = 0.0
                eventos.append(("CANCELADA", dict(pos)))
            elif tocou_entrada:
                pos["status"] = "ABERTA"
                pos["data_abertura"] = time.strftime('%d/%m/%Y %H:%M')
                pos["preco_atual"] = preco
                pos["pnl_atual"] = calcular_pnl_posicao(pos, preco)
                eventos.append(("EXECUTADA", dict(pos)))
            continue

        # ---------- ABERTA: acumula P&L e pode fechar ----------
        pos["preco_atual"] = preco
        pos["pnl_atual"] = calcular_pnl_posicao(pos, preco)

        bateu_tp2 = pos.get("tp2") is not None and (
            (direcao == "BUY" and preco >= pos["tp2"]) or
            (direcao == "SELL" and preco <= pos["tp2"])
        )
        if bateu_stop or bateu_tp2:
            pos["status"] = "FECHADA"
            pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
            pos["pnl_final"] = pos["pnl_atual"]
            eventos.append(("STOP" if bateu_stop else "ALVO", dict(pos)))
    salvar_posicoes(lista)
    return eventos

def fechar_posicao_manual(pos_id, preco_saida=None):
    lista = carregar_posicoes()
    for pos in lista:
        if pos["id"] == pos_id and pos["status"] == "ABERTA":
            preco = preco_saida if preco_saida is not None else pos.get("preco_atual", pos["entry"])
            pos["status"] = "FECHADA"
            pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
            pos["pnl_final"] = calcular_pnl_posicao(pos, preco)
            pos["preco_atual"] = preco
            pos["pnl_atual"] = pos["pnl_final"]
            salvar_posicoes(lista)
            return pos
    return None

def resultados_por_dia():
    """Agrega o P&L realizado por dia (posições fechadas) + P&L aberto de hoje.
    Retorna lista de (data_str, resultado_do_dia) em ordem cronológica."""
    lista = posicoes_do_ciclo()
    por_dia = {}
    for pos in lista:
        if pos.get("status") == "FECHADA" and pos.get("pnl_final") is not None:
            dia = (pos.get("data_fechamento") or "")[:10]
            if dia:
                por_dia[dia] = por_dia.get(dia, 0.0) + pos["pnl_final"]
    hoje = time.strftime('%d/%m/%Y')
    # Só posições ABERTAS (executadas de verdade) têm P&L flutuante.
    aberto_hoje = sum(p.get("pnl_atual", 0) for p in lista if p.get("status") == "ABERTA")
    if aberto_hoje:
        por_dia[hoje] = por_dia.get(hoje, 0.0) + aberto_hoje

    def chave(d):
        try:
            return datetime.datetime.strptime(d, '%d/%m/%Y')
        except ValueError:
            return datetime.datetime.min
    return sorted(por_dia.items(), key=lambda kv: chave(kv[0]))

def compilar_memoria_prompt():
    contexto = "\n--- FEEDBACK LOOP DE APRENDIZADO ---\n"

    # 1) Plano do trader (o "projeto" dele) — a IA calibra rigor pela meta/drawdown.
    plano = carregar_config().get("plano_trading", {})
    if plano.get("margem"):
        contexto += (f"PLANO DO TRADER: margem US${plano.get('margem')}, "
                      f"meta US${plano.get('meta_alvo')}, drawdown máximo US${plano.get('drawdown_maximo')}, "
                      f"risco por operação {plano.get('risco_pct', 1.0)}%.\n")

    # 2) Diário de trader — operações REAIS (acatadas e manuais), que valem
    # mais como aprendizado do que os fechamentos hipotéticos do robô.
    posicoes = carregar_posicoes()
    fechadas = [p for p in posicoes if p.get("status") == "FECHADA" and p.get("pnl_final") is not None]
    abertas = [p for p in posicoes if p.get("status") == "ABERTA"]
    if fechadas:
        pnl_total = sum(p["pnl_final"] for p in fechadas)
        wins_reais = sum(1 for p in fechadas if p["pnl_final"] > 0)
        contexto += (f"DIÁRIO REAL DO TRADER: {len(fechadas)} operações fechadas, "
                      f"{wins_reais} positivas, resultado acumulado US${pnl_total:.2f}.\n")
        contexto += "Últimas operações reais:\n"
        for p in fechadas[-4:]:
            contexto += (f"- [{p['origem']}] {p['direcao']} {p['ativo']} entrada {p['entry']} -> "
                          f"US${p['pnl_final']:.2f}\n")
    if abertas:
        contexto += f"POSIÇÕES ABERTAS AGORA: {len(abertas)} — não sugira sinais em conflito direto com elas.\n"

    # 3) Performance hipotética do robô (sinais acompanhados internamente).
    db = carregar_performance()
    if db:
        total = len(db)
        wins = sum(1 for op in db if op["resultado"] == "WIN")
        winrate = (wins / total) * 100
        contexto += f"Taxa de acerto dos cenários do robô ({total}): {winrate:.1f}%\n"
    else:
        winrate = 100.0

    # 4) Instrução de calibragem.
    perdeu_recente = (fechadas and fechadas[-1]["pnl_final"] < 0) or \
                     (db and db[-1]["resultado"] == "LOSS")
    contexto += "\nINSTRUÇÃO CRÍTICA DO SISTEMA:\n"
    if winrate < 50.0 or perdeu_recente:
        contexto += ("⚠️ ALERTA: perdas recentes ou mercado incerto. SEJA EXTREMAMENTE RIGOROSO. "
                      "Exija confluência perfeita entre Order Block não mitigado, FVG e captura de "
                      "liquidez. Em caso de ruído no gráfico, obrigatoriamente sugira ACTION: HOLD.\n")
    else:
        contexto += "✅ Sistema calibrado. Mantenha os parâmetros estruturais atuais.\n"

    return contexto

# --------------------------------------------------------------------
# REGISTRO DE SINAIS + DECISÃO DO TRADER (acatou ou não a sugestão)
# --------------------------------------------------------------------
def carregar_sinais_log():
    if os.path.exists(SIGNALS_LOG_FILE):
        try:
            with open(SIGNALS_LOG_FILE, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if isinstance(dados, list):
                return [s for s in dados if isinstance(s, dict) and "id" in s]
        except Exception:
            pass
    return []

def salvar_sinais_log(lista):
    lista = lista[-100:]
    with open(SIGNALS_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)

def registrar_novo_sinal_log(direcao, entry, stop, tp1, tp2, ativo="DESCONHECIDO"):
    lista = carregar_sinais_log()
    novo_id = int(time.time() * 1000)
    lista.append({
        "id": novo_id,
        "data_hora": time.strftime('%d/%m/%Y %H:%M:%S'),
        "direcao": direcao,
        "ativo": ativo,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "decisao": None,
    })
    salvar_sinais_log(lista)
    return novo_id

def atualizar_decisao_sinal(sinal_id, decisao):
    lista = carregar_sinais_log()
    for s in lista:
        if s["id"] == sinal_id:
            s["decisao"] = decisao
            break
    salvar_sinais_log(lista)

# --------------------------------------------------------------------
# CAPTURA DA JANELA DA CORRETORA EM SEGUNDO PLANO (sem roubar foco)
# --------------------------------------------------------------------
# Por que isso existe: usar SetForegroundWindow() força a troca de janela
# ativa de verdade — se o usuário estiver trabalhando em outro programa,
# a tela "pula" para a corretora a cada candle. Isso é inaceitável.
#
# A solução correta é capturar o CONTEÚDO da janela diretamente via
# PrintWindow, sem precisar trazê-la para frente. Usamos a flag
# PW_RENDERFULLCONTENT, necessária para capturar corretamente conteúdo
# renderizado por GPU — como uma aba do Chrome (o Tradovate roda em Chrome).
def encontrar_janela_por_titulo(nome_parcial: str):
    """Retorna o hwnd da primeira janela visível cujo título contenha
    `nome_parcial`, ou None se não encontrar."""
    if not nome_parcial or not PYWIN32_DISPONIVEL:
        return None

    resultado = {"hwnd": None}

    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            titulo = win32gui.GetWindowText(hwnd)
            if nome_parcial.lower() in titulo.lower():
                resultado["hwnd"] = hwnd
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        pass
    return resultado["hwnd"]

def garantir_janela_renderizando(hwnd, restaurar_se_minimizada=True):
    """
    Prepara QUALQUER janela para ser capturada com conteúdo ATUAL, sem roubar
    o foco do usuário. Funciona para Chrome, NinjaTrader, MT5, TradingView
    desktop — não depende de flags específicas de nenhum aplicativo.

    IMPORTANTE SOBRE FOCO:
      - Se a janela JÁ ESTIVER VISÍVEL (mesmo parcialmente coberta, mesmo em
        outro monitor), NADA aqui muda foco, posição ou z-order. O usuário
        segue trabalhando sem qualquer interrupção.
      - Se estiver MINIMIZADA, e `restaurar_se_minimizada` for True, usamos
        SW_SHOWNOACTIVATE: a janela reaparece na tela, mas NÃO recebe o foco
        do teclado nem do mouse — você continua digitando no programa em que
        estava. Isso é necessário porque uma janela minimizada não é
        renderizada pelo Windows: não existe pixel atual para capturar.
      - Se `restaurar_se_minimizada` for False, não tocamos na janela e o
        ciclo será pulado com aviso.
    Retorna True se a janela está apta a ser capturada.
    """
    if not PYWIN32_DISPONIVEL:
        return True
    try:
        if win32gui.IsIconic(hwnd):  # minimizada
            if not restaurar_se_minimizada:
                return False
            # SW_SHOWNOACTIVATE = 4 -> mostra sem ativar/roubar foco
            win32gui.ShowWindow(hwnd, 4)
            time.sleep(0.4)  # dá tempo do app redesenhar
            # Empurra a janela restaurada para o FUNDO da pilha, sem ativá-la.
            # Assim ela volta a ser renderizável (dá pra capturar), mas NÃO fica
            # por cima do que você está fazendo — nada de "pular na sua frente".
            # HWND_BOTTOM=1 ; SWP_NOSIZE=0x1|NOMOVE=0x2|NOACTIVATE=0x10 = 0x13
            try:
                ctypes.windll.user32.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x13)
            except Exception:
                pass
    except Exception:
        pass
    try:
        # RDW_INVALIDATE(0x1) | RDW_UPDATENOW(0x100) | RDW_ALLCHILDREN(0x80)
        # Apenas pede repintura ao app. Não altera foco, posição ou z-order.
        ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x1 | 0x100 | 0x80)
        time.sleep(0.15)
    except Exception:
        pass
    return True

def capturar_via_recorte_de_tela(hwnd):
    """
    Plano C: recorta a região da TELA onde a janela está.
    Captura o que está fisicamente visível naquelas coordenadas — sempre
    conteúdo atual, nunca congelado. A limitação é real e conhecida: se outra
    janela estiver POR CIMA, o recorte pega a janela de cima. Por isso é o
    último recurso, e só é usado quando o PrintWindow retorna quadro velho.
    Retorna (imagem, houve_sobreposicao).
    """
    if not PYWIN32_DISPONIVEL:
        return None, False
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right - left <= 0 or bottom - top <= 0:
            return None, False
        # A janela do topo naquele ponto central é a nossa? Se não, há sobreposição.
        centro = ((left + right) // 2, (top + bottom) // 2)
        hwnd_no_ponto = win32gui.WindowFromPoint(centro)
        sobreposto = True
        try:
            raiz = ctypes.windll.user32.GetAncestor(hwnd_no_ponto, 2)  # GA_ROOT
            sobreposto = (raiz != hwnd)
        except Exception:
            pass
        imagem = ImageGrab.grab(bbox=(left, top, right, bottom))
        return imagem, sobreposto
    except Exception:
        return None, False

def capturar_janela_em_segundo_plano(hwnd):
    """
    Captura o conteúdo de uma janela específica pelo handle, SEM trazê-la
    para o primeiro plano e sem tirar o usuário do que ele estiver fazendo.
    Retorna uma imagem PIL, ou None se a captura falhar.
    """
    if not PYWIN32_DISPONIVEL:
        return None
    import win32ui

    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        largura, altura = right - left, bottom - top
        if largura <= 0 or altura <= 0:
            return None

        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()

        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, largura, altura)
        saveDC.SelectObject(saveBitMap)

        PW_RENDERFULLCONTENT = 0x00000002
        resultado = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), PW_RENDERFULLCONTENT)

        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        imagem = Image.frombuffer(
            'RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1
        )

        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

        return imagem if resultado == 1 else None
    except Exception:
        return None

def imagem_esta_em_branco(imagem_pil):
    """Heurística: se a imagem capturada for essencialmente uma cor sólida,
    a captura em segundo plano provavelmente falhou silenciosamente."""
    try:
        extremos = imagem_pil.convert("L").getextrema()
        return (extremos[1] - extremos[0]) < 5
    except Exception:
        return False

def hash_imagem(imagem_pil):
    """Impressão digital da imagem capturada.

    POR QUE ISSO EXISTE (bug crítico de trading):
    O Chrome PARA DE RENDERIZAR quando sua janela está minimizada ou
    totalmente coberta por outra janela (otimização chamada "occlusion
    detection" / "renderer backgrounding"). Nesse estado, PrintWindow devolve
    o ÚLTIMO QUADRO desenhado — uma foto congelada, possivelmente de vários
    minutos atrás.

    O resultado é desastroso: a IA analisa um gráfico velho e reporta o preço
    antigo como se fosse o atual. Comparando o hash de capturas consecutivas
    detectamos isso e nos recusamos a analisar, em vez de emitir um relatório
    baseado em dado defasado.
    """
    import hashlib
    try:
        # Reduz e converte para cinza: ignora ruído de compressão/antialiasing,
        # mas qualquer mudança real de candle/preço altera o hash.
        pequena = imagem_pil.convert("L").resize((160, 90))
        return hashlib.md5(pequena.tobytes()).hexdigest()
    except Exception:
        return None

def listar_janelas_abertas():
    """Retorna os títulos de todas as janelas visíveis abertas no Windows,
    para popular o dropdown de seleção (em vez do usuário digitar na mão)."""
    if not PYWIN32_DISPONIVEL:
        return []
    titulos = []

    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            titulo = win32gui.GetWindowText(hwnd)
            if titulo.strip():
                titulos.append(titulo)
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        pass
    return sorted(set(titulos))

# --------------------------------------------------------------------
# NÚCLEO DE SUPORTE
# --------------------------------------------------------------------
def falar(texto: str):
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 165)
        for v in engine.getProperty('voices'):
            if 'brazil' in v.name.lower() or 'portugu' in v.name.lower():
                engine.setProperty('voice', v.id)
                break
        engine.say(texto)
        engine.runAndWait()
        engine.stop()
    except Exception:
        pass

def enviar_relatorio_whatsapp(mensagem: str, imagem_print, log_callback):
    log_callback("📲 Disparando relatório para o WhatsApp...")
    try:
        payload = {"jid": "", "texto": mensagem}
        if imagem_print is not None:
            output = BytesIO()
            imagem_print.convert("RGB").save(output, format="JPEG", quality=80)
            payload["imagemBase64"] = base64.b64encode(output.getvalue()).decode('utf-8')
            output.close()

        response = requests.post(BAILEYS_API_URL, json=payload, timeout=15)
        if response.status_code == 200:
            log_callback("✅ Relatório enviado com sucesso!")
        else:
            log_callback(f"⚠️ Erro na API do WhatsApp: {response.text}")
    except Exception as e:
        log_callback(f"⚠️ Falha no disparo do relatório: {e}")

# --------------------------------------------------------------------
# INTERFACE GRÁFICA (GUI) E GERENCIADOR DE PROCESSOS
# --------------------------------------------------------------------
class SmcQuantApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SMC Quant Pro - Trader Institucional AI")
        self.geometry("680x900")
        self.minsize(680, 800)
        self.protocol("WM_DELETE_WINDOW", self.ao_fechar)

        self.processo_motor = None
        self.motor_rodando = False
        self.robo_ativo = False
        self.parar_solicitado = False
        # IDs de sinais que o trader marcou como "Não operei". O robô usa isto
        # para PARAR de mandar acompanhamento de pendente de um cenário que o
        # trader dispensou (senão o WhatsApp seguia tratando como entrada ativa).
        self.sinais_dispensados = set()
        # IDs de sinais que o trader ACATOU (dashboard ou WhatsApp). O robô só
        # manda acompanhamento (entrada acionada, alvo, stop) de cenários que
        # foram acatados — cenário não acatado é só a sugestão inicial, sem
        # follow-up no WhatsApp.
        self.sinais_acatados = set()

        # Poller dos comandos recebidos por WhatsApp (ACATAR/DISPENSAR). Roda
        # em segundo plano por toda a vida do app; se o motor estiver fora do
        # ar, a chamada falha em silêncio e ele tenta de novo depois.
        threading.Thread(target=self._poller_comandos_whatsapp, daemon=True).start()

        config_atual = carregar_config()
        self.plano = config_atual.get("plano_trading", {
            "margem": 0, "meta_alvo": 0, "drawdown_maximo": 0,
            "risco_pct": 1.0, "data_inicio": None,
        })

        self.tabview = ctk.CTkTabview(self, width=660, height=720)
        self.tabview.pack(padx=10, pady=10, fill="both", expand=True)
        self.tabview.add("⚙️ Motor & WhatsApp")
        self.tabview.add("📊 Plano de Trading")
        tab_motor = self.tabview.tab("⚙️ Motor & WhatsApp")
        tab_plano = self.tabview.tab("📊 Plano de Trading")

        self._montar_tab_motor(tab_motor, config_atual)
        self._montar_tab_plano(tab_plano)

        self.verificar_node()
        self.after(3000, self._loop_atualizar_dashboard)

    # ------------------------------------------------------------------
    # ABA 1: MOTOR / WHATSAPP / SETUP
    # ------------------------------------------------------------------
    def _montar_tab_motor(self, master, config_atual):
        scroll_motor = ctk.CTkScrollableFrame(master)
        scroll_motor.pack(fill="both", expand=True)
        master = scroll_motor  # todos os widgets vão para o frame rolável

        self.lbl_status = ctk.CTkLabel(master, text="Verificando dependências...", text_color="yellow")
        self.lbl_status.pack(pady=8)

        # Banner de atualização (fica oculto até detectar nova versão)
        self.frame_update = ctk.CTkFrame(master, fg_color="#1b2a1b", border_color="#00E676", border_width=1)
        self.lbl_update = ctk.CTkLabel(self.frame_update, text="", justify="left",
                                        font=ctk.CTkFont(weight="bold", size=12))
        self.lbl_update.pack(side="left", padx=12, pady=8)
        self.btn_update = ctk.CTkButton(self.frame_update, text="⬇️ Baixar atualização",
                                         fg_color="#1f8b4c", width=160, command=self._baixar_atualizacao)
        self.btn_update.pack(side="right", padx=12, pady=8)
        self._url_download_update = ""
        # Checa em segundo plano para não travar a abertura do app
        threading.Thread(target=self._checar_atualizacao, daemon=True).start()

        self.btn_instalar = ctk.CTkButton(master, text="1. Baixar Node.js (Obrigatório)", fg_color="blue", command=self.abrir_download)
        self.btn_instalar.pack(pady=4)

        self.btn_verificar = ctk.CTkButton(master, text="2. Verificar Instalação", fg_color="gray", command=self.verificar_node)
        self.btn_verificar.pack(pady=4)

        self.api_entry = ctk.CTkEntry(master, placeholder_text="Cole sua Chave da API Gemini", width=420, show="*")
        self.api_entry.pack(pady=8)

        api_key_salva = carregar_api_key()
        if api_key_salva:
            self.api_entry.insert(0, api_key_salva)

        ctk.CTkLabel(master, text="Janela da corretora a monitorar:").pack(pady=(6, 0))
        nome_janela_salvo = config_atual.get("nome_janela_corretora", "")
        self.janela_var = tk.StringVar(value=nome_janela_salvo or "(clique em Atualizar lista)")
        self.janela_dropdown = ctk.CTkOptionMenu(master, variable=self.janela_var, values=[self.janela_var.get()], width=420)
        self.janela_dropdown.pack(pady=4)
        ctk.CTkButton(master, text="🔄 Atualizar lista de janelas abertas", fg_color="#555555",
                      command=self._atualizar_lista_janelas).pack(pady=(0, 4))

        self.restaurar_minimizada_var = tk.BooleanVar(
            value=config_atual.get("restaurar_janela_minimizada", True)
        )
        ctk.CTkCheckBox(
            master,
            text="Restaurar a janela se ela estiver minimizada (não rouba o foco)",
            variable=self.restaurar_minimizada_var,
            command=self._salvar_pref_restaurar
        ).pack(pady=(2, 0))
        ctk.CTkLabel(
            master,
            text="Se desmarcado e a janela estiver minimizada, o ciclo é pulado com aviso.\n"
                 "Uma janela minimizada não é desenhada pelo Windows — não há como capturá-la.",
            text_color="gray", font=ctk.CTkFont(size=10), justify="left"
        ).pack(pady=(0, 4))
        self._atualizar_lista_janelas(manter_selecao=nome_janela_salvo)

        if not PYWIN32_DISPONIVEL:
            ctk.CTkLabel(master, text="⚠️ pywin32 não encontrado — foco automático de janela desativado.",
                         text_color="orange").pack(pady=2)

        frame_horario = ctk.CTkFrame(master, fg_color="transparent")
        frame_horario.pack(pady=6)

        ctk.CTkLabel(frame_horario, text="Pregão de:").grid(row=0, column=0, padx=(4, 4), sticky="w")
        self.entry_hora_inicio = ctk.CTkEntry(frame_horario, width=60)
        self.entry_hora_inicio.grid(row=0, column=1, padx=4)
        self.entry_hora_inicio.insert(0, config_atual.get("hora_inicio", "09:00"))

        ctk.CTkLabel(frame_horario, text="até:").grid(row=0, column=2, padx=4, sticky="w")
        self.entry_hora_fim = ctk.CTkEntry(frame_horario, width=60)
        self.entry_hora_fim.grid(row=0, column=3, padx=4)
        self.entry_hora_fim.insert(0, config_atual.get("hora_fim", "17:00"))

        ctk.CTkLabel(
            master,
            text="Dica: no plano gratuito da API Gemini (20 análises/dia por modelo), 15 min\n"
                 "dentro do horário de pregão cabe folgado na cota. A cada 5 min estoura rápido.",
            text_color="gray", font=ctk.CTkFont(size=11), justify="left"
        ).pack(pady=(0, 4))

        self.btn_ligar = ctk.CTkButton(master, text="▶️ LIGAR MOTOR", fg_color="gray",
                                        state="disabled", command=self.alternar_motor)
        self.btn_ligar.pack(pady=8)

        # Dropdown de intervalo alterável AO VIVO (mesmo com o motor ligado).
        # O loop de análise relê esse valor a cada ciclo, então mudar aqui
        # ajusta a frequência sem precisar reiniciar o motor.
        frame_intervalo_vivo = ctk.CTkFrame(master, fg_color="transparent")
        frame_intervalo_vivo.pack(pady=2)
        ctk.CTkLabel(frame_intervalo_vivo, text="⏱️ Intervalo de análise (ao vivo):").pack(side="left", padx=6)
        self.intervalo_vivo_var = tk.StringVar(value=str(config_atual.get("intervalo_minutos", 15)))
        ctk.CTkOptionMenu(
            frame_intervalo_vivo,
            variable=self.intervalo_vivo_var,
            values=["1", "3", "5", "10", "15", "30", "60"],
            width=90,
            command=self._alterar_intervalo_ao_vivo
        ).pack(side="left", padx=6)

        self.lbl_qr_titulo = ctk.CTkLabel(master, text="", text_color="white",
                                           font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_qr_titulo.pack(pady=(12, 4))
        self.lbl_qr_imagem = ctk.CTkLabel(master, text="")
        # Imagem vazia permanente, mantida como referência forte — usada
        # para "limpar" o QR sem nunca passar image=None (isso quebra o
        # CustomTkinter quando a imagem anterior já foi coletada pelo GC,
        # gerando TclError "image ... doesn't exist" em loop).
        self._imagem_qr_vazia = ctk.CTkImage(
            light_image=Image.new("RGBA", (1, 1), (0, 0, 0, 0)),
            dark_image=Image.new("RGBA", (1, 1), (0, 0, 0, 0)),
            size=(1, 1)
        )
        self.lbl_qr_imagem.pack(pady=(0, 16))

        ctk.CTkLabel(master, text="📋 Registro de atividade",
                     font=ctk.CTkFont(weight="bold", size=13)).pack(padx=10, pady=(6, 2), anchor="w")
        self.console = tk.Text(master, height=22, bg="#0d0d0d", fg="#00ff00",
                                font=("Consolas", 10), relief="flat", borderwidth=0,
                                insertbackground="#00ff00")
        self.console.pack(pady=(0, 8), padx=10, fill="both", expand=True)

        # ---------- SEÇÃO DESENVOLVEDOR (oculta no app do cliente) ----------
        if MODO_DEV:
            frame_dev = ctk.CTkFrame(master, fg_color="#2b1b1b", border_color="#8b4513", border_width=1)
            frame_dev.pack(padx=10, pady=8, fill="x")
            ctk.CTkLabel(frame_dev, text="🛠️ MODO DESENVOLVEDOR",
                         font=ctk.CTkFont(weight="bold", size=12), text_color="#ff9955").pack(pady=(6, 2))
            frame_dev_btns = ctk.CTkFrame(frame_dev, fg_color="transparent")
            frame_dev_btns.pack(pady=(0, 8))
            ctk.CTkButton(frame_dev_btns, text="💾 Criar backup dos dados", fg_color="#8b4513",
                          command=self._criar_backup).pack(side="left", padx=6)
            ctk.CTkButton(frame_dev_btns, text="♻️ Restaurar backup", fg_color="#5a3010",
                          command=self._restaurar_backup).pack(side="left", padx=6)
            ctk.CTkButton(frame_dev_btns, text="📂 Abrir pasta de dados", fg_color="#444444",
                          command=lambda: os.startfile(pasta_dados_usuario())).pack(side="left", padx=6)

    def _checar_atualizacao(self):
        info = verificar_nova_versao()
        if not info:
            return
        self._url_download_update = info.get("url_download", "")

        def _mostrar():
            notas = info.get("notas", "")
            texto = f"🆕 Nova versão disponível: {info['versao']} (você tem a {VERSAO_ATUAL})"
            if notas:
                texto += f"\n{notas[:90]}"
            self.lbl_update.configure(text=texto)
            self.frame_update.pack(padx=10, pady=(2, 6), fill="x", before=self.btn_instalar)
            self.log(f"🆕 Atualização disponível: versão {info['versao']}")
        self.after(0, _mostrar)

    def _baixar_atualizacao(self):
        if self._url_download_update:
            webbrowser.open_new(self._url_download_update)
            self.log("🌐 Página de download da atualização aberta no navegador.")
        else:
            self.log("⚠️ Link de download indisponível. Contate o suporte.")

    def _criar_backup(self):
        try:
            caminho = criar_backup_dados()
            self.log(f"💾 Backup criado: {caminho}")
        except Exception as e:
            self.log(f"⚠️ Falha ao criar backup: {e}")

    def _restaurar_backup(self):
        from tkinter import filedialog
        caminho = filedialog.askopenfilename(
            title="Selecione o backup (.zip)",
            filetypes=[("Arquivo ZIP", "*.zip")]
        )
        if not caminho:
            return
        try:
            destino = restaurar_backup_dados(caminho)
            self.log(f"♻️ Backup restaurado em: {destino}")
            self.log("⚠️ Reinicie o programa para carregar os dados restaurados.")
        except Exception as e:
            self.log(f"⚠️ Falha ao restaurar backup: {e}")

    # ------------------------------------------------------------------
    # ABA 2: PLANO DE TRADING (mesa proprietária)
    # ------------------------------------------------------------------
    def _imprimir_dashboard(self):
        """Gera um relatório HTML do dashboard e abre no navegador.
        O usuário usa Ctrl+P para imprimir ou salvar como PDF — sem depender
        de bibliotecas extras de PDF, que inflariam o executável."""
        try:
            stats = self._computar_stats_plano()
            posicoes = posicoes_do_ciclo()
            fechadas = [p for p in posicoes if p.get("status") == "FECHADA" and p.get("pnl_final") is not None]
            abertas = [p for p in posicoes if p.get("status") in ("ABERTA", "PENDENTE")]
            dias = resultados_por_dia()

            def cor(v):
                return "#0a7d3a" if v >= 0 else "#c62828"

            # Linhas da tabela de operações fechadas
            linhas_fechadas = "".join(
                f"<tr><td>{p.get('data_fechamento','—')}</td><td>{p['origem']}</td>"
                f"<td>{p['direcao']}</td><td>{p['ativo']}</td><td>{p['entry']}</td>"
                f"<td>{p['stop']}</td><td>{p.get('tp1','—')}</td><td>{p['contratos']}</td>"
                f"<td style='color:{cor(p['pnl_final'])};font-weight:bold'>US$ {p['pnl_final']:+,.2f}</td></tr>"
                for p in fechadas
            ) or "<tr><td colspan='9' style='text-align:center;color:#888'>Nenhuma operação fechada no ciclo.</td></tr>"

            linhas_abertas = "".join(
                f"<tr><td>{p['status']}</td><td>{p['origem']}</td><td>{p['direcao']}</td>"
                f"<td>{p['ativo']}</td><td>{p['entry']}</td><td>{p['stop']}</td>"
                f"<td>{p['contratos']}</td>"
                f"<td style='color:{cor(p.get('pnl_atual',0))}'>US$ {p.get('pnl_atual',0):+,.2f}</td></tr>"
                for p in abertas
            ) or "<tr><td colspan='8' style='text-align:center;color:#888'>Nenhuma posição em aberto.</td></tr>"

            linhas_dias = "".join(
                f"<tr><td>Dia {i}</td><td>{d}</td>"
                f"<td style='color:{cor(v)};font-weight:bold'>US$ {v:+,.2f}</td></tr>"
                for i, (d, v) in enumerate(dias, start=1)
            ) or "<tr><td colspan='3' style='text-align:center;color:#888'>Sem dias operados.</td></tr>"

            margem = self.plano.get("margem") or 0
            capital_atual = margem + stats["lucro_usd"]
            retorno = (stats["lucro_usd"] / margem * 100) if margem else 0
            gerado_em = time.strftime('%d/%m/%Y às %H:%M:%S')
            ciclo_ini = inicio_do_ciclo()
            ciclo_txt = ciclo_ini.strftime('%d/%m/%Y %H:%M') if ciclo_ini else "início do histórico"

            html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>SMC Quant Pro — Relatório do Dashboard</title>
<style>
  @media print {{ .noprint {{ display:none }} body {{ margin:0 }} }}
  body {{ font-family:'Segoe UI',Arial,sans-serif; margin:28px; color:#1a1a1a; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  h2 {{ font-size:14px; margin:22px 0 8px; padding-bottom:4px;
        border-bottom:2px solid #00994d; color:#00663a; }}
  .sub {{ color:#666; font-size:12px; margin-bottom:18px; }}
  .kpis {{ display:flex; gap:10px; margin-bottom:8px; }}
  .kpi {{ flex:1; border:1px solid #ddd; border-radius:6px; padding:10px; text-align:center; }}
  .kpi .r {{ font-size:9px; color:#777; letter-spacing:.5px; text-transform:uppercase; }}
  .kpi .v {{ font-size:17px; font-weight:bold; margin-top:4px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th {{ background:#f2f4f6; text-align:left; padding:7px; border-bottom:2px solid #ddd; font-size:10px;
        text-transform:uppercase; letter-spacing:.4px; color:#555; }}
  td {{ padding:7px; border-bottom:1px solid #eee; }}
  .box {{ border:1px solid #ddd; border-radius:6px; padding:12px; font-size:13px; line-height:1.7; }}
  .aviso {{ margin-top:26px; font-size:10px; color:#777; border-top:1px solid #ddd; padding-top:10px; }}
  button {{ padding:9px 18px; font-size:14px; cursor:pointer; border-radius:5px;
            border:none; background:#00994d; color:#fff; }}
</style></head><body>

<div class="noprint" style="margin-bottom:18px">
  <button onclick="window.print()">🖨️ Imprimir / Salvar como PDF</button>
</div>

<h1>SMC Quant Pro — Relatório do Dashboard</h1>
<div class="sub">Gerado em {gerado_em} &nbsp;·&nbsp; Ciclo iniciado em {ciclo_txt}</div>

<div class="kpis">
  <div class="kpi"><div class="r">Resultado do dia</div>
    <div class="v" style="color:{cor(stats['resultado_hoje'])}">US$ {stats['resultado_hoje']:+,.2f}</div></div>
  <div class="kpi"><div class="r">Total do ciclo</div>
    <div class="v" style="color:{cor(stats['lucro_usd'])}">US$ {stats['lucro_usd']:+,.2f}</div></div>
  <div class="kpi"><div class="r">Drawdown</div>
    <div class="v">US$ {stats['max_dd_usd']:,.2f}</div></div>
  <div class="kpi"><div class="r">Win rate</div>
    <div class="v">{stats['winrate']:.0f}% ({stats['total_ops']} ops)</div></div>
  <div class="kpi"><div class="r">Meta atingida</div>
    <div class="v">{(stats['lucro_usd']/stats['meta']*100) if stats['meta'] else 0:.0f}%</div></div>
</div>

<h2>Evolução Patrimonial</h2>
<div class="box">
  Capital inicial (margem): <b>US$ {margem:,.2f}</b><br>
  Resultado realizado: <b style="color:{cor(stats['realizado'])}">US$ {stats['realizado']:+,.2f}</b><br>
  Resultado em aberto: <b style="color:{cor(stats['flutuante'])}">US$ {stats['flutuante']:+,.2f}</b><br>
  <b>Capital atual: US$ {capital_atual:,.2f}</b> &nbsp;·&nbsp;
  Retorno sobre a margem: <b style="color:{cor(retorno)}">{retorno:+.2f}%</b><br>
  Dias operados: {len(dias)} &nbsp;·&nbsp; Meta: US$ {stats['meta']:,.2f} &nbsp;·&nbsp;
  Falta: US$ {stats['falta']:,.2f}
</div>

<h2>Resultado por Dia Operado</h2>
<table><thead><tr><th>Sequência</th><th>Data</th><th>Resultado</th></tr></thead>
<tbody>{linhas_dias}</tbody></table>

<h2>Operações Fechadas no Ciclo</h2>
<table><thead><tr><th>Fechamento</th><th>Origem</th><th>Direção</th><th>Ativo</th>
<th>Entrada</th><th>Stop</th><th>Alvo</th><th>Ctr</th><th>Resultado</th></tr></thead>
<tbody>{linhas_fechadas}</tbody></table>

<h2>Posições em Aberto / Pendentes</h2>
<table><thead><tr><th>Status</th><th>Origem</th><th>Direção</th><th>Ativo</th>
<th>Entrada</th><th>Stop</th><th>Ctr</th><th>P&amp;L atual</th></tr></thead>
<tbody>{linhas_abertas}</tbody></table>

<div class="aviso">
  <b>Aviso:</b> Este relatório tem caráter estritamente educacional e de registro pessoal
  (diário de trader). Não constitui recomendação de investimento nem garantia de resultado.
  Os valores de P&amp;L são marcados a cada ciclo de análise e podem divergir dos valores
  oficiais da corretora — sempre confira na plataforma antes de qualquer decisão.
  <br>SMC Quant Pro v{VERSAO_ATUAL} — TIGER INVEST
</div>
</body></html>"""

            caminho = os.path.join(pasta_dados_usuario(),
                                    f"relatorio_dashboard_{time.strftime('%Y%m%d_%H%M%S')}.html")
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(html)
            webbrowser.open_new_tab(f"file:///{caminho.replace(os.sep, '/')}")
            self.log(f"🖨️ Relatório gerado e aberto no navegador. Use Ctrl+P para imprimir ou salvar em PDF.")
            self.log(f"   Arquivo: {caminho}")
        except Exception as e:
            import traceback
            self.log(f"⚠️ Falha ao gerar relatório: {e}")
            self.log(traceback.format_exc())

    def _card_kpi(self, master, titulo, coluna):
        """Card compacto de indicador — leitura em 1 segundo."""
        card = ctk.CTkFrame(master, fg_color=COR["card"], corner_radius=8,
                             border_width=1, border_color=COR["borda"])
        card.grid(row=0, column=coluna, sticky="nsew", padx=4, pady=2)
        ctk.CTkLabel(card, text=titulo.upper(), font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=COR["dim"]).pack(pady=(8, 0))
        valor = ctk.CTkLabel(card, text="—", font=ctk.CTkFont(size=17, weight="bold"),
                              text_color=COR["texto"])
        valor.pack(pady=(0, 8))
        return valor

    def _montar_tab_plano(self, master):
        scroll = ctk.CTkScrollableFrame(master, fg_color=COR["fundo"])
        scroll.pack(fill="both", expand=True)

        # ================= FAIXA DE KPIs (leitura instantânea) =================
        frame_kpis = ctk.CTkFrame(scroll, fg_color="transparent")
        frame_kpis.pack(padx=8, pady=(8, 4), fill="x")
        for i in range(5):
            frame_kpis.grid_columnconfigure(i, weight=1)
        self.kpi_dia = self._card_kpi(frame_kpis, "Resultado do dia", 0)
        self.kpi_total = self._card_kpi(frame_kpis, "Total do ciclo", 1)
        self.kpi_dd = self._card_kpi(frame_kpis, "Drawdown", 2)
        self.kpi_winrate = self._card_kpi(frame_kpis, "Win rate", 3)
        self.kpi_meta = self._card_kpi(frame_kpis, "Meta atingida", 4)

        # ================= CONFIGURAÇÃO DA CONTA =================
        frame_config = ctk.CTkFrame(scroll, fg_color=COR["card"], corner_radius=8,
                                     border_width=1, border_color=COR["borda"])
        frame_config.pack(padx=8, pady=6, fill="x")

        ctk.CTkLabel(frame_config, text="CONFIGURAÇÃO DA CONTA (MESA PROPRIETÁRIA)",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=COR["dim"]
                     ).grid(row=0, column=0, columnspan=4, pady=(10, 8))

        campos = [
            ("Margem (US$):", "entry_margem", "margem", 1, 0),
            ("Meta Alvo (US$):", "entry_meta", "meta_alvo", 1, 2),
            ("Drawdown Máx. (US$):", "entry_dd", "drawdown_maximo", 2, 0),
            ("Risco/operação (%):", "entry_risco", "risco_pct", 2, 2),
        ]
        for rotulo, attr, chave, linha, col in campos:
            ctk.CTkLabel(frame_config, text=rotulo, text_color=COR["dim"],
                         font=ctk.CTkFont(size=11)).grid(row=linha, column=col, sticky="e", padx=(12, 4), pady=4)
            entrada = ctk.CTkEntry(frame_config, width=110, fg_color=COR["input"],
                                    border_color=COR["borda"], text_color=COR["texto"])
            entrada.grid(row=linha, column=col + 1, padx=(0, 12), pady=4)
            padrao = 1.0 if chave == "risco_pct" else 0
            entrada.insert(0, str(self.plano.get(chave, padrao)))
            setattr(self, attr, entrada)

        frame_botoes_plano = ctk.CTkFrame(frame_config, fg_color="transparent")
        frame_botoes_plano.grid(row=3, column=0, columnspan=4, pady=(6, 10))
        ctk.CTkButton(frame_botoes_plano, text="💾 Salvar Plano", width=140,
                      fg_color=COR["verde_esc"], hover_color=COR["verde"],
                      command=self.salvar_plano_trading).pack(side="left", padx=6)
        ctk.CTkButton(frame_botoes_plano, text="🔄 Reiniciar ciclo (zera o painel)", width=210,
                      fg_color="#5a3a1a", hover_color="#8b4513",
                      command=self.reiniciar_plano_trading).pack(side="left", padx=6)
        ctk.CTkButton(frame_botoes_plano, text="🖨️ Imprimir / PDF", width=150,
                      fg_color="#2a3f5f", hover_color="#3a5580",
                      command=self._imprimir_dashboard).pack(side="left", padx=6)

        # ================= GRÁFICOS LADO A LADO =================
        frame_graficos = ctk.CTkFrame(scroll, fg_color="transparent")
        frame_graficos.pack(padx=8, pady=6, fill="x")
        frame_graficos.grid_columnconfigure(0, weight=1)
        frame_graficos.grid_columnconfigure(1, weight=1)

        for coluna, (titulo, attr) in enumerate([
            ("📈 EQUITY — RESULTADO ACUMULADO (US$)", "canvas_equity"),
            ("📅 RESULTADO POR DIA OPERADO (US$)", "canvas_operacoes"),
        ]):
            col = ctk.CTkFrame(frame_graficos, fg_color=COR["card"], corner_radius=8,
                                border_width=1, border_color=COR["borda"])
            col.grid(row=0, column=coluna, sticky="nsew", padx=(0, 6) if coluna == 0 else (6, 0))
            ctk.CTkLabel(col, text=titulo, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=COR["dim"]).pack(anchor="w", padx=10, pady=(8, 2))
            canvas = tk.Canvas(col, bg=COR["card"], height=175, highlightthickness=0)
            canvas.pack(fill="x", padx=6, pady=(0, 8))
            setattr(self, attr, canvas)
            self._ativar_zoom_pan(canvas)

        self.lbl_legenda_dias = ctk.CTkLabel(scroll, text="", justify="left", anchor="w",
                                              text_color=COR["dim"], font=ctk.CTkFont(size=9))
        self.lbl_legenda_dias.pack(padx=12, pady=(0, 2), fill="x")

        # ================= COMPARATIVO: ACATADAS vs TODAS AS SUGESTÕES =================
        frame_comp = ctk.CTkFrame(scroll, fg_color=COR["card"], corner_radius=8,
                                   border_width=1, border_color="#3a3a5a")
        frame_comp.pack(padx=8, pady=6, fill="x")
        ctk.CTkLabel(frame_comp, text="⚖️ COMPARATIVO DO CICLO — O QUE VOCÊ FEZ vs. TODAS AS SUGESTÕES",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=COR["dim"]).pack(pady=(10, 6))
        self.lbl_comparativo = ctk.CTkLabel(frame_comp, text="Sem dados ainda.", justify="left",
                                             anchor="w", font=("Consolas", 11))
        self.lbl_comparativo.pack(padx=14, pady=(0, 10), fill="x")

        # ================= EVOLUÇÃO PATRIMONIAL =================
        frame_patrimonio = ctk.CTkFrame(scroll, fg_color=COR["card"], corner_radius=8,
                                         border_width=1, border_color=COR["verde_esc"])
        frame_patrimonio.pack(padx=8, pady=6, fill="x")
        ctk.CTkLabel(frame_patrimonio, text="💰 EVOLUÇÃO PATRIMONIAL",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=COR["dim"]).pack(pady=(10, 6))
        self.lbl_patrimonio = ctk.CTkLabel(frame_patrimonio, text="Sem dados ainda.",
                                            justify="left", anchor="w", font=("Consolas", 11))
        self.lbl_patrimonio.pack(padx=14, pady=(0, 10), fill="x")

        # ================= POSIÇÕES =================
        ctk.CTkLabel(scroll, text="🔥 ORDENS PENDENTES E OPERAÇÕES EM ANDAMENTO",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=COR["dim"]
                     ).pack(padx=12, pady=(10, 2), anchor="w")
        self.frame_posicoes = ctk.CTkFrame(scroll, fg_color=COR["card"], corner_radius=8)
        self.frame_posicoes.pack(padx=8, pady=4, fill="x")

        # ================= INCLUSÃO MANUAL NO DIÁRIO =================
        frame_manual = ctk.CTkFrame(scroll, fg_color=COR["card"], corner_radius=8,
                                     border_width=1, border_color=COR["borda"])
        frame_manual.pack(padx=8, pady=8, fill="x")
        ctk.CTkLabel(frame_manual, text="✍️ INCLUIR OPERAÇÃO NO DIÁRIO (FORA DA SUGESTÃO)",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=COR["dim"]
                     ).grid(row=0, column=0, columnspan=8, pady=(10, 6), padx=10, sticky="w")

        # Situação da operação: já concluída, ou ainda rodando.
        self.manual_situacao = tk.StringVar(value="Em andamento")
        ctk.CTkLabel(frame_manual, text="Situação:", text_color=COR["dim"],
                     font=ctk.CTkFont(size=11)).grid(row=1, column=0, padx=(10, 2), sticky="e")
        ctk.CTkOptionMenu(frame_manual, variable=self.manual_situacao,
                          values=["Em andamento", "Já concluída"], width=140,
                          fg_color=COR["input"], command=self._alternar_campos_manual
                          ).grid(row=1, column=1, columnspan=2, padx=4, pady=(0, 6), sticky="w")

        ctk.CTkLabel(frame_manual, text="Aguardar entrada (pendente):", text_color=COR["dim"],
                     font=ctk.CTkFont(size=10)).grid(row=1, column=3, columnspan=2, padx=(12, 2), sticky="e")
        self.manual_pendente = tk.BooleanVar(value=False)
        self.chk_pendente = ctk.CTkCheckBox(frame_manual, text="", variable=self.manual_pendente, width=20)
        self.chk_pendente.grid(row=1, column=5, sticky="w", pady=(0, 6))

        self.manual_direcao = tk.StringVar(value="BUY")
        ctk.CTkOptionMenu(frame_manual, variable=self.manual_direcao, values=["BUY", "SELL"],
                          width=80, fg_color=COR["input"]).grid(row=2, column=0, padx=(10, 4), pady=(0, 4))
        campos_manual = [
            ("manual_ativo", "Ativo (MESU6)", 105),
            ("manual_entry", "Entrada", 85),
            ("manual_stop", "Stop", 85),
            ("manual_tp1", "Alvo 1", 85),
            ("manual_tp2", "Alvo 2 (opc.)", 95),
            ("manual_contratos", "Qtde", 55),
        ]
        for col, (attr, ph, w) in enumerate(campos_manual, start=1):
            e = ctk.CTkEntry(frame_manual, placeholder_text=ph, width=w,
                              fg_color=COR["input"], border_color=COR["borda"],
                              text_color=COR["texto"], placeholder_text_color=COR["dim"])
            e.grid(row=2, column=col, padx=3, pady=(0, 4))
            setattr(self, attr, e)

        # Só aparece quando a operação já foi concluída.
        self.manual_saida = ctk.CTkEntry(frame_manual, placeholder_text="Preço de saída", width=120,
                                          fg_color=COR["input"], border_color=COR["borda"],
                                          text_color=COR["texto"], placeholder_text_color=COR["dim"])
        ctk.CTkButton(frame_manual, text="➕ Incluir no diário", fg_color=COR["verde_esc"],
                      hover_color=COR["verde"], command=self._adicionar_operacao_manual
                      ).grid(row=3, column=6, columnspan=2, padx=10, pady=(2, 10), sticky="e")
        self.lbl_dica_manual = ctk.CTkLabel(
            frame_manual, text="Em andamento: o P&L é acompanhado até bater stop ou alvo.",
            text_color=COR["dim"], font=ctk.CTkFont(size=10))
        self.lbl_dica_manual.grid(row=3, column=0, columnspan=6, padx=10, pady=(2, 10), sticky="w")

        # ================= SINAIS =================
        ctk.CTkLabel(scroll, text="📋 ÚLTIMOS SINAIS — MARQUE SE VOCÊ ACATOU",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=COR["dim"]
                     ).pack(padx=12, pady=(10, 2), anchor="w")
        self.frame_sinais = ctk.CTkFrame(scroll, fg_color=COR["card"], corner_radius=8)
        self.frame_sinais.pack(padx=8, pady=(4, 12), fill="both", expand=True)

        self._atualizar_dashboard()

    def _alternar_campos_manual(self, _valor=None):
        """Mostra o campo 'Preço de saída' só quando a operação já foi concluída."""
        if self.manual_situacao.get() == "Já concluída":
            self.manual_saida.grid(row=3, column=1, columnspan=2, padx=4, pady=(2, 10), sticky="w")
            self.chk_pendente.configure(state="disabled")
            self.manual_pendente.set(False)
            self.lbl_dica_manual.configure(
                text="Concluída: informe o preço de saída — o resultado entra direto no dashboard.")
            self.lbl_dica_manual.grid(row=3, column=3, columnspan=3, sticky="w")
        else:
            self.manual_saida.grid_forget()
            self.chk_pendente.configure(state="normal")
            self.lbl_dica_manual.configure(
                text="Em andamento: o P&L é acompanhado até bater stop ou alvo.")
            self.lbl_dica_manual.grid(row=3, column=0, columnspan=6, sticky="w")

    def _adicionar_operacao_manual(self):
        from tkinter import messagebox

        def aviso(msg):
            # Popup visível + log, para o trader SABER por que nada foi incluído
            # (antes só ia pro log e passava despercebido).
            self.log(f"⚠️ {msg}")
            messagebox.showwarning("Incluir operação no diário", msg)

        def num(campo, obrigatorio=True):
            txt = campo.get().strip().replace(",", ".")
            if not txt:
                if obrigatorio:
                    raise ValueError("campo obrigatório vazio")
                return None
            return float(txt)

        try:
            entry = num(self.manual_entry)
            stop = num(self.manual_stop)
            tp1 = num(self.manual_tp1, obrigatorio=False)
            tp2 = num(self.manual_tp2, obrigatorio=False)
            contratos = int(self.manual_contratos.get().strip() or 1)
        except ValueError:
            aviso("Preencha Entrada, Stop e Qtde com números válidos.")
            return

        if entry == stop:
            aviso("Entrada e Stop não podem ser iguais.")
            return

        ativo = self.manual_ativo.get().strip().upper() or "DESCONHECIDO"
        direcao = self.manual_direcao.get()
        concluida = self.manual_situacao.get() == "Já concluída"

        # Preço de saída é obrigatório para operação concluída.
        preco_saida = None
        if concluida:
            try:
                preco_saida = num(self.manual_saida)
            except ValueError:
                aviso("Operação 'Já concluída': informe o Preço de saída para o "
                      "resultado entrar no dashboard.")
                return

        if concluida:
            status = "FECHADA"
        elif self.manual_pendente.get():
            status = "PENDENTE"   # aguarda o preço tocar a entrada
        else:
            status = "ABERTA"     # já posicionado, acompanha o P&L

        pos = abrir_posicao("MANUAL", direcao, ativo, entry, stop, tp1, tp2,
                             contratos, status_inicial=status if status != "FECHADA" else "ABERTA")

        if concluida:
            # Fecha imediatamente no preço informado, realizando o resultado.
            fechada = fechar_posicao_manual(pos["id"], preco_saida)
            self.log(f"📕 Operação CONCLUÍDA incluída no diário: {direcao} {ativo} "
                      f"{entry} → {preco_saida}  |  Resultado: US$ {fechada['pnl_final']:+,.2f}")
        elif status == "PENDENTE":
            self.log(f"⏳ Ordem PENDENTE incluída: {direcao} {ativo} @ {entry} "
                      f"— só conta P&L quando o preço tocar a entrada.")
        else:
            self.log(f"🔥 Operação EM ANDAMENTO incluída: {direcao} {ativo} @ {entry} "
                      f"({contratos} ctr) — P&L será acompanhado a cada ciclo.")

        # Limpa os campos para o próximo lançamento.
        for campo in (self.manual_ativo, self.manual_entry, self.manual_stop,
                       self.manual_tp1, self.manual_tp2, self.manual_contratos, self.manual_saida):
            campo.delete(0, "end")
        self._atualizar_dashboard()

    def _renderizar_posicoes(self):
        for widget in self.frame_posicoes.winfo_children():
            widget.destroy()

        todas = posicoes_do_ciclo()
        pendentes = [p for p in todas if p.get("status") == "PENDENTE"]
        abertas = [p for p in todas if p.get("status") == "ABERTA"]

        if not pendentes and not abertas:
            ctk.CTkLabel(self.frame_posicoes, text="Nenhuma ordem pendente ou operação em andamento.",
                         text_color=COR["dim"]).pack(pady=6)
            return

        # PENDENTES: acatadas, mas o preço ainda não tocou a entrada.
        for pos in pendentes:
            linha = ctk.CTkFrame(self.frame_posicoes, fg_color="#241f14")
            linha.pack(fill="x", pady=3, padx=4)
            texto = (f"⏳ PENDENTE [{pos['origem']}] {pos['direcao']} {pos['ativo']} | "
                     f"Aguardando preço tocar {pos['entry']} | Stop {pos['stop']} | "
                     f"{pos['contratos']} ctr | Preço atual: {pos.get('preco_atual', '—')}")
            ctk.CTkLabel(linha, text=texto, anchor="w", text_color=COR["amarelo"]).pack(side="left", padx=8, pady=6)
            ctk.CTkButton(linha, text="Cancelar", width=90, fg_color="#555555",
                          command=lambda i=pos["id"]: self._cancelar_posicao_click(i)).pack(side="right", padx=8)

        # ABERTAS: executadas, com P&L ao vivo.
        for pos in abertas:
            linha = ctk.CTkFrame(self.frame_posicoes)
            linha.pack(fill="x", pady=3, padx=4)
            pnl = pos.get("pnl_atual", 0.0)
            cor = COR["verde"] if pnl >= 0 else COR["vermelho"]
            texto = (f"🔥 ABERTA [{pos['origem']}] {pos['direcao']} {pos['ativo']} | "
                     f"Entrada {pos['entry']} | Stop {pos['stop']} | "
                     f"{pos['contratos']} ctr | Preço atual: {pos.get('preco_atual', '—')}")
            ctk.CTkLabel(linha, text=texto, anchor="w").pack(side="left", padx=8, pady=6)
            ctk.CTkLabel(linha, text=f"US${pnl:+.2f}", text_color=cor,
                         font=ctk.CTkFont(weight="bold", size=14)).pack(side="left", padx=10)
            ctk.CTkButton(linha, text="Fechar agora", width=100, fg_color="#8b4513",
                          command=lambda i=pos["id"]: self._fechar_posicao_click(i)).pack(side="right", padx=8)

    def _cancelar_posicao_click(self, pos_id):
        lista = carregar_posicoes()
        for pos in lista:
            if pos["id"] == pos_id and pos["status"] == "PENDENTE":
                pos["status"] = "CANCELADA"
                pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
                pos["pnl_final"] = 0.0
                self.log(f"🚫 Ordem pendente cancelada: {pos['direcao']} {pos['ativo']} @ {pos['entry']}")
                break
        salvar_posicoes(lista)
        self._atualizar_dashboard()

    def _fechar_posicao_click(self, pos_id):
        pos = fechar_posicao_manual(pos_id)
        if pos:
            self.log(f"📕 Posição FECHADA no diário: {pos['direcao']} {pos['ativo']} → "
                      f"US${pos['pnl_final']:+.2f}")
        self._atualizar_dashboard()

    # ------------------------------------------------------------------
    def _salvar_pref_restaurar(self):
        valor = self.restaurar_minimizada_var.get()
        salvar_config({"restaurar_janela_minimizada": valor})
        if valor:
            self.log("⚙️ Janela minimizada será restaurada automaticamente (sem roubar foco).")
        else:
            self.log("⚙️ Janela minimizada NÃO será restaurada — ciclos serão pulados nesse caso.")

    def _atualizar_lista_janelas(self, manter_selecao=None):
        titulos = listar_janelas_abertas()
        if not titulos:
            titulos = ["Nenhuma janela encontrada"]
        self.janela_dropdown.configure(values=titulos)
        selecionar = manter_selecao if manter_selecao in titulos else titulos[0]
        self.janela_var.set(selecionar)

    def _alterar_intervalo_ao_vivo(self, novo_valor):
        try:
            minutos = max(int(novo_valor), 1)
            salvar_config({"intervalo_minutos": minutos})
            self.log(f"⏱️ Intervalo de análise alterado para {minutos} min (efeito no próximo ciclo).")
        except ValueError:
            pass

    def abrir_download(self):
        webbrowser.open_new("https://nodejs.org/en/download/")

    def verificar_node(self):
        try:
            subprocess.run(["node", "-v"], check=True, capture_output=True)
            self.lbl_status.configure(text="STATUS: Ambiente pronto!", text_color="lime")
            self.btn_ligar.configure(state="normal", text="▶️ LIGAR MOTOR", fg_color="green")
            self.log("Node.js detectado.")
        except Exception:
            self.lbl_status.configure(text="STATUS: Node.js não encontrado.", text_color="red")
            self.btn_ligar.configure(state="disabled", fg_color="gray")

    def log(self, msg):
        def _escrever():
            self.console.insert(tk.END, f"{msg}\n")
            self.console.see(tk.END)
        self.after(0, _escrever)

    # ------------------------------------------------------------------
    # PLANO DE TRADING — salvar / reiniciar
    # ------------------------------------------------------------------
    def salvar_plano_trading(self):
        try:
            self.plano["margem"] = float(self.entry_margem.get().replace(",", "."))
            self.plano["meta_alvo"] = float(self.entry_meta.get().replace(",", "."))
            self.plano["drawdown_maximo"] = float(self.entry_dd.get().replace(",", "."))
            self.plano["risco_pct"] = float(self.entry_risco.get().replace(",", "."))
        except ValueError:
            self.log("⚠️ Valores do plano de trading inválidos — use apenas números.")
            return

        if not self.plano.get("data_inicio"):
            self.plano["data_inicio"] = datetime.date.today().isoformat()

        salvar_config({"plano_trading": self.plano})
        self.log("💾 Plano de trading salvo.")
        self._atualizar_dashboard()

    def reiniciar_plano_trading(self):
        from tkinter import messagebox
        abertas = [p for p in posicoes_do_ciclo() if p.get("status") in ("ABERTA", "PENDENTE")]
        aviso = ""
        if abertas:
            aviso = (f"\n\nATENÇÃO: você tem {len(abertas)} posição(ões) aberta(s)/pendente(s). "
                      "Elas sairão do dashboard, mas continuarão sendo acompanhadas internamente.")

        confirmado = messagebox.askyesno(
            "Reiniciar contagem de 5 dias",
            "Isso vai ZERAR todos os indicadores do dashboard (resultado, gráficos, "
            "operações e comparativo) e iniciar um novo ciclo a partir de agora.\n\n"
            "Seu histórico NÃO será apagado — ele fica arquivado nos arquivos de dados."
            + aviso + "\n\nDeseja continuar?"
        )
        if not confirmado:
            self.log("↩️ Reinício de ciclo cancelado.")
            return

        agora = datetime.datetime.now()
        self.plano["data_inicio"] = agora.date().isoformat()
        self.plano["ciclo_inicio"] = agora.isoformat(timespec="seconds")
        salvar_config({"plano_trading": self.plano})
        self.log(f"🔄 Novo ciclo de 5 dias iniciado em {agora.strftime('%d/%m/%Y %H:%M:%S')}. "
                  "Dashboard zerado (histórico preservado nos arquivos).")
        self._atualizar_dashboard()

    # ------------------------------------------------------------------
    # DASHBOARD — equity curve, drawdown, plano de 5 dias, sinais
    # ------------------------------------------------------------------
    def _loop_atualizar_dashboard(self):
        try:
            self._atualizar_dashboard()
        except Exception as e:
            self.log(f"⚠️ Erro ao atualizar dashboard (não crítico): {e}")
        self.after(5000, self._loop_atualizar_dashboard)

    def _computar_stats_plano(self):
        # Estatísticas agora vêm do DIÁRIO REAL (posições acatadas + manuais),
        # não mais dos fechamentos hipotéticos do robô — é isso que o trader
        # de fato executou.
        posicoes = posicoes_do_ciclo()
        fechadas = [p for p in posicoes if p.get("status") == "FECHADA" and p.get("pnl_final") is not None]
        abertas = [p for p in posicoes if p.get("status") == "ABERTA"]

        curva = []
        acumulado = 0.0
        for p in fechadas:
            acumulado += p["pnl_final"]
            curva.append(acumulado)

        realizado = acumulado
        flutuante = sum(p.get("pnl_atual", 0) for p in abertas)
        lucro_usd = realizado + flutuante

        total = len(fechadas)
        wins = sum(1 for p in fechadas if p["pnl_final"] > 0)
        winrate = (wins / total * 100) if total else 0.0

        # Drawdown máximo REAL em US$ (pico a vale da curva de resultado)
        max_dd_usd = 0.0
        pico = 0.0
        for v in curva:
            pico = max(pico, v)
            max_dd_usd = max(max_dd_usd, pico - v)
        max_dd_usd = round(max_dd_usd, 2)

        margem = self.plano.get("margem") or 0
        risco_pct = self.plano.get("risco_pct") or 1.0
        risco_usd = margem * (risco_pct / 100) if margem else 0

        meta = self.plano.get("meta_alvo") or 0
        data_inicio_str = self.plano.get("data_inicio")
        dias_passados = 0
        dias_restantes = 5
        if data_inicio_str:
            try:
                data_inicio = datetime.date.fromisoformat(data_inicio_str)
                dias_passados = (datetime.date.today() - data_inicio).days
                dias_restantes = max(5 - dias_passados, 0)
            except ValueError:
                pass

        falta = meta - lucro_usd
        meta_diaria = (falta / dias_restantes) if dias_restantes > 0 else None
        hoje = time.strftime('%d/%m/%Y')
        resultado_hoje = dict(resultados_por_dia()).get(hoje, 0.0)

        return {
            "curva": curva, "winrate": winrate, "max_dd_usd": max_dd_usd,
            "lucro_usd": lucro_usd, "realizado": realizado, "flutuante": flutuante,
            "risco_usd": risco_usd, "dias_passados": dias_passados,
            "dias_restantes": dias_restantes, "falta": falta, "abertas": len(abertas),
            "meta_diaria": meta_diaria, "total_ops": total, "meta": meta,
            "resultado_hoje": resultado_hoje,
        }

    def _atualizar_dashboard(self):
        try:
            stats = self._computar_stats_plano()
            dd_max_config = self.plano.get("drawdown_maximo") or 0

            def cor_valor(v):
                return COR["verde"] if v >= 0 else COR["vermelho"]

            # ---------- FAIXA DE KPIs ----------
            self.kpi_dia.configure(text=f"US$ {stats['resultado_hoje']:+,.2f}",
                                    text_color=cor_valor(stats["resultado_hoje"]))
            self.kpi_total.configure(text=f"US$ {stats['lucro_usd']:+,.2f}",
                                      text_color=cor_valor(stats["lucro_usd"]))

            dd = stats["max_dd_usd"]
            estourou = dd_max_config and dd > dd_max_config
            perto = dd_max_config and dd >= dd_max_config * 0.8
            self.kpi_dd.configure(
                text=f"US$ {dd:,.2f}" + (" ⚠️" if estourou else ""),
                text_color=COR["vermelho"] if estourou else (COR["amarelo"] if perto else COR["texto"])
            )

            self.kpi_winrate.configure(
                text=f"{stats['winrate']:.0f}%" + (f"  ({stats['total_ops']} ops)" if stats["total_ops"] else ""),
                text_color=COR["verde"] if stats["winrate"] >= 50 else COR["texto"]
            )

            meta = stats["meta"]
            pct_meta = (stats["lucro_usd"] / meta * 100) if meta else 0
            self.kpi_meta.configure(
                text=f"{pct_meta:.0f}%" if meta else "—",
                text_color=COR["verde"] if pct_meta >= 100 else COR["texto"]
            )

            self._desenhar_equity_curve()
            self._desenhar_grafico_dias()
            self._renderizar_comparativo(stats)
            self._renderizar_patrimonio(stats)
            self._renderizar_posicoes()
            self._renderizar_lista_sinais()
        except Exception as e:
            import traceback
            self.log(f"❌ ERRO ao atualizar dashboard: {e}")
            self.log(traceback.format_exc())

    def _renderizar_comparativo(self, stats):
        """Compara, DENTRO DO CICLO ATUAL:
          (A) o que você realmente executou (posições acatadas + manuais)
          (B) o que teria acontecido se tivesse acatado TODAS as sugestões
        A base de (B) é o desfecho hipotético que o robô acompanha para cada
        cenário que gerou, independentemente de você ter operado ou não.
        """
        # (A) Real executado no ciclo
        posicoes = posicoes_do_ciclo()
        fechadas = [p for p in posicoes if p.get("status") == "FECHADA" and p.get("pnl_final") is not None]
        abertas = [p for p in posicoes if p.get("status") == "ABERTA"]
        real_total = sum(p["pnl_final"] for p in fechadas) + sum(p.get("pnl_atual", 0) for p in abertas)
        real_ops = len(fechadas)
        real_wins = sum(1 for p in fechadas if p["pnl_final"] > 0)

        # (B) Hipotético: todas as sugestões do robô no ciclo
        perf = performance_do_ciclo()
        # Cada sinal pode gerar 2 registros (TP1 parcial + TP2/stop). Agrupa por
        # entrada para não contar a mesma operação duas vezes.
        vistos = {}
        for op in perf:
            chave = (op.get("direcao"), op.get("entry"), op.get("stop"))
            # mantém o desfecho final (último registrado para aquela entrada)
            vistos[chave] = op
        sugestoes = list(vistos.values())
        hip_total = sum(pnl_usd_do_registro(op) for op in sugestoes)
        hip_ops = len(sugestoes)
        hip_wins = sum(1 for op in sugestoes if pnl_usd_do_registro(op) > 0)

        if hip_ops == 0 and real_ops == 0 and not abertas:
            self.lbl_comparativo.configure(
                text="Nenhuma operação ou sugestão fechada neste ciclo ainda.",
                text_color=COR["dim"]
            )
            return

        diferenca = real_total - hip_total
        nao_acatadas = max(hip_ops - real_ops, 0)
        wr_real = (real_wins / real_ops * 100) if real_ops else 0
        wr_hip = (hip_wins / hip_ops * 100) if hip_ops else 0

        if diferenca > 0:
            veredito = f"✅ Sua seletividade ADICIONOU US$ {diferenca:+,.2f} em relação a acatar tudo."
            cor = COR["verde"]
        elif diferenca < 0:
            veredito = f"⚠️ Acatar todas teria rendido US$ {abs(diferenca):,.2f} a mais que suas escolhas."
            cor = COR["vermelho"]
        else:
            veredito = "➖ Resultado idêntico a acatar todas as sugestões."
            cor = COR["dim"]

        texto = (
            f"{'':<28}{'OPERAÇÕES':>11}{'WIN RATE':>11}{'RESULTADO':>16}\n"
            f"{'─' * 66}\n"
            f"{'Você executou':<28}{real_ops:>11}{wr_real:>10.0f}%{real_total:>+15,.2f}\n"
            f"{'Se acatasse TODAS':<28}{hip_ops:>11}{wr_hip:>10.0f}%{hip_total:>+15,.2f}\n"
            f"{'─' * 66}\n"
            f"{'Diferença':<28}{'':>11}{'':>11}{diferenca:>+15,.2f}\n"
            f"\nSugestões não acatadas no ciclo: {nao_acatadas}\n"
            f"{veredito}"
        )
        self.lbl_comparativo.configure(text=texto, text_color=cor)

    def _renderizar_patrimonio(self, stats):
        """Relatório de evolução patrimonial: capital inicial (margem), variação
        realizada, flutuante, capital atual, retorno % e projeção da meta."""
        margem = self.plano.get("margem") or 0
        realizado = stats["realizado"]
        flutuante = stats["flutuante"]
        total = stats["lucro_usd"]
        capital_atual = margem + total
        retorno_pct = (total / margem * 100) if margem else 0

        dias = resultados_por_dia()
        dias_operados = len(dias)
        media_dia = (realizado / dias_operados) if dias_operados else 0

        meta = stats["meta"]
        falta = stats["falta"]
        if media_dia > 0 and falta > 0:
            projecao = f"{falta / media_dia:.1f} dia(s) no ritmo atual"
        elif falta <= 0 and meta:
            projecao = "✅ META ATINGIDA"
        else:
            projecao = "—"

        dd_max = self.plano.get("drawdown_maximo") or 0
        margem_dd = dd_max - stats["max_dd_usd"] if dd_max else 0
        alerta = ""
        if dd_max and stats["max_dd_usd"] >= dd_max * 0.8:
            alerta = "  ⚠️ PRÓXIMO DO LIMITE"

        # Trilha de 5 dias com a meta acumulada esperada em cada um
        trilha = []
        for dia in range(1, 6):
            meta_dia = meta * (dia / 5) if meta else 0
            if stats["dias_passados"] >= dia:
                marca = "✅" if stats["lucro_usd"] >= meta_dia else "❌"
            else:
                marca = "⬜"
            trilha.append(f"D{dia} {marca}")

        meta_diaria_txt = (f"US$ {stats['meta_diaria']:,.2f}/dia"
                            if stats["meta_diaria"] is not None else "PRAZO ESGOTADO")

        cor = COR["verde"] if total >= 0 else COR["vermelho"]
        texto = (
            f"Capital inicial (margem):   US$ {margem:>12,.2f}\n"
            f"Resultado realizado:        US$ {realizado:>+12,.2f}\n"
            f"Resultado em aberto:        US$ {flutuante:>+12,.2f}\n"
            f"{'─' * 46}\n"
            f"CAPITAL ATUAL:              US$ {capital_atual:>12,.2f}\n"
            f"Retorno sobre a margem:         {retorno_pct:>+8.2f} %\n"
            f"{'─' * 46}\n"
            f"Dias operados: {dias_operados}   |   Média/dia: US$ {media_dia:+,.2f}\n"
            f"Drawdown: US$ {stats['max_dd_usd']:,.2f}"
            f"{f'  (folga: US$ {margem_dd:,.2f})' if dd_max else ''}{alerta}\n"
            f"Falta p/ meta: US$ {stats['falta']:,.2f}   |   Ritmo: {meta_diaria_txt}\n"
            f"Projeção: {projecao}\n"
            f"{'─' * 46}\n"
            f"Trilha de 5 dias:  {'   '.join(trilha)}   "
            f"({stats['dias_passados']}/5 · restam {stats['dias_restantes']})"
        )
        self.lbl_patrimonio.configure(text=texto, text_color=cor)

    def _ativar_zoom_pan(self, canvas):
        """Torna um gráfico MANIPULÁVEL: roda do mouse dá zoom, arraste move
        (pan) e duplo-clique reseta. O estado (_zoom/_panx) vive no canvas."""
        canvas._zoom = 1.0
        canvas._panx = 0.0
        canvas._arraste_x = None

        def redesenhar():
            # Redesenha os dois gráficos (barato e mantém tudo consistente).
            try:
                self._desenhar_equity_curve()
                self._desenhar_grafico_dias()
            except Exception:
                pass

        def on_wheel(event):
            # event.delta > 0 = rolar pra cima = ampliar. Zoom entre 1x e 8x.
            fator = 1.15 if getattr(event, "delta", 0) > 0 else (1 / 1.15)
            novo = min(max(canvas._zoom * fator, 1.0), 8.0)
            canvas._zoom = novo
            if novo <= 1.0:       # ao voltar ao mínimo, recentraliza
                canvas._panx = 0.0
            redesenhar()
            return "break"

        def on_wheel_linux(delta):
            return lambda e: on_wheel(type("E", (), {"delta": delta})())

        def on_press(event):
            canvas._arraste_x = event.x

        def on_drag(event):
            if canvas._arraste_x is not None:
                canvas._panx += event.x - canvas._arraste_x
                canvas._arraste_x = event.x
                redesenhar()

        def on_release(_event):
            canvas._arraste_x = None

        def on_reset(_event):
            canvas._zoom = 1.0
            canvas._panx = 0.0
            redesenhar()
            return "break"

        canvas.bind("<MouseWheel>", on_wheel)                 # Windows / Mac
        canvas.bind("<Button-4>", on_wheel_linux(120))        # Linux scroll up
        canvas.bind("<Button-5>", on_wheel_linux(-120))       # Linux scroll down
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        canvas.bind("<Double-Button-1>", on_reset)

    def _desenhar_linha(self, canvas, valores, rotulos=None, tooltip_extra=None):
        """Gráfico de LINHA com timeline no eixo X. `rotulos` é a lista de
        legendas (ex: 'Dia 1', 'Op 3') alinhada com `valores`."""
        canvas.delete("all")
        largura = max(canvas.winfo_width(), 300)
        altura = 190
        margem_base = 32  # espaço reservado para os rótulos do eixo X

        if not valores:
            canvas.create_text(largura // 2, altura // 2,
                                text="Sem operações registradas ainda", fill=COR["dim"])
            return

        minimo = min(valores + [0])
        maximo = max(valores + [0])
        faixa = (maximo - minimo) or 1
        n = len(valores)
        topo, base = 14, altura - margem_base

        # Zoom/pan interativos (roda do mouse amplia, arraste move, duplo-clique
        # reseta). O estado fica guardado no próprio canvas.
        zoom = getattr(canvas, "_zoom", 1.0)
        panx = getattr(canvas, "_panx", 0.0)
        centro = largura / 2

        def xy(i, v):
            x = (i / max(n - 1, 1)) * (largura - 40) + 20
            x = (x - centro) * zoom + centro + panx   # aplica zoom horizontal + deslocamento
            y = base - ((v - minimo) / faixa) * (base - topo)
            return x, y

        def visivel(x):
            return 16 <= x <= largura - 16

        # Linha do zero
        y_zero = base - ((0 - minimo) / faixa) * (base - topo)
        canvas.create_line(20, y_zero, largura - 20, y_zero, fill=COR["borda"], dash=(3, 3))
        canvas.create_text(largura - 22, y_zero - 8, text="0", fill=COR["dim"],
                            font=("Consolas", 8), anchor="e")

        cor = COR["verde"] if valores[-1] >= 0 else COR["vermelho"]

        # Linha e área
        pontos = []
        for i, v in enumerate(valores):
            pontos.extend(xy(i, v))
        if len(pontos) >= 4:
            canvas.create_line(*pontos, fill=cor, width=2, smooth=True)

        # Pontos + rótulos da timeline no eixo X
        # Se houver muitos pontos, mostra rótulos espaçados para não sobrepor.
        passo_rotulo = max(1, n // 8)
        for i, v in enumerate(valores):
            x, y = xy(i, v)
            if not visivel(x):   # fora da área visível (ampliado): não desenha
                continue
            cor_ponto = COR["verde"] if v >= 0 else COR["vermelho"]
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=cor_ponto, outline="")
            if rotulos and (i % passo_rotulo == 0 or i == n - 1):
                canvas.create_line(x, base, x, base + 4, fill=COR["borda"])
                canvas.create_text(x, base + 14, text=rotulos[i], fill=COR["dim"],
                                    font=("Consolas", 8))

        # Valor final anotado
        x_ult, y_ult = xy(n - 1, valores[-1])
        canvas.create_text(min(x_ult, largura - 45), max(y_ult - 12, 10),
                            text=f"US${valores[-1]:+.2f}", fill=cor,
                            font=("Consolas", 10, "bold"))

    def _desenhar_equity_curve(self):
        """LINHA: resultado acumulado em US$, operação a operação, do diário
        REAL (posições executadas e fechadas), com timeline Op 1, Op 2..."""
        posicoes = posicoes_do_ciclo()
        fechadas = [p for p in posicoes if p.get("status") == "FECHADA" and p.get("pnl_final") is not None]
        valores, rotulos = [], []
        acumulado = 0.0
        for i, p in enumerate(fechadas, start=1):
            acumulado += p["pnl_final"]
            valores.append(round(acumulado, 2))
            rotulos.append(f"Op {i}")
        # Só posições ABERTAS (executadas) somam P&L flutuante.
        flutuante = sum(p.get("pnl_atual", 0) for p in posicoes if p.get("status") == "ABERTA")
        if flutuante:
            valores.append(round(acumulado + flutuante, 2))
            rotulos.append("Agora")
        self._desenhar_linha(self.canvas_equity, valores, rotulos)

    def _desenhar_grafico_dias(self):
        """LINHA: resultado por dia operado (US$), com timeline Dia 1, Dia 2..."""
        dias = resultados_por_dia()
        valores = [round(v, 2) for _, v in dias]
        rotulos = [f"Dia {i}" for i in range(1, len(dias) + 1)]
        self._desenhar_linha(self.canvas_operacoes, valores, rotulos)

        # Legenda com as datas reais de cada dia (a timeline mostra Dia N)
        if dias:
            legenda = "  ".join(f"Dia {i} = {d}" for i, (d, _) in enumerate(dias, start=1))
            self.lbl_legenda_dias.configure(text=legenda[:180])
        else:
            self.lbl_legenda_dias.configure(text="")

    def _renderizar_lista_sinais(self):
        for widget in self.frame_sinais.winfo_children():
            widget.destroy()

        sinais = list(reversed(carregar_sinais_log()[-10:]))
        if not sinais:
            ctk.CTkLabel(self.frame_sinais, text="Nenhum sinal registrado ainda.").pack(pady=6)
            return

        for s in sinais:
            linha = ctk.CTkFrame(self.frame_sinais)
            linha.pack(fill="x", pady=3, padx=2)

            alvos = [a for a in (s.get("tp1"), s.get("tp2")) if a is not None]
            alvos_txt = " / ".join(f"{a}" for a in alvos) if alvos else "—"
            ativo_txt = f" {s.get('ativo', '')}" if s.get("ativo") and s["ativo"] != "DESCONHECIDO" else ""
            texto = (f"{s['data_hora']} | {s['direcao']}{ativo_txt}  ·  "
                     f"Entrada {s['entry']}  /  Alvo {alvos_txt}  /  Stop {s['stop']}")
            decisao_atual = s.get("decisao")
            if decisao_atual:
                texto += f"   →  [{decisao_atual}]"

            ctk.CTkLabel(linha, text=texto, anchor="w").pack(side="top", fill="x", padx=6, pady=(4, 0))

            frame_botoes = ctk.CTkFrame(linha, fg_color="transparent")
            frame_botoes.pack(side="top", pady=(2, 6))

            sinal_id = s["id"]
            ctk.CTkButton(frame_botoes, text="✅ Acatei (Comprei)", width=140, fg_color="#1f8b4c",
                          command=lambda i=sinal_id: self._registrar_decisao(i, "ACATOU_COMPRA")).pack(side="left", padx=3)
            ctk.CTkButton(frame_botoes, text="✅ Acatei (Vendi)", width=140, fg_color="#8b1f1f",
                          command=lambda i=sinal_id: self._registrar_decisao(i, "ACATOU_VENDA")).pack(side="left", padx=3)
            ctk.CTkButton(frame_botoes, text="❌ Não operei", width=120, fg_color="#555555",
                          command=lambda i=sinal_id: self._registrar_decisao(i, "NAO_OPEROU")).pack(side="left", padx=3)

    def _registrar_decisao(self, sinal_id, decisao):
        atualizar_decisao_sinal(sinal_id, decisao)

        # "Não operei": marca o sinal como dispensado para o robô ENCERRAR o
        # acompanhamento desse cenário no próximo ciclo (para de mandar
        # "Cenário em PENDENTE" no WhatsApp de algo que o trader não vai operar).
        if decisao == "NAO_OPEROU":
            self.sinais_dispensados.add(sinal_id)
            self.sinais_acatados.discard(sinal_id)
        # ACATOU: libera o acompanhamento desse cenário no WhatsApp.
        elif decisao in ("ACATOU_COMPRA", "ACATOU_VENDA"):
            self.sinais_acatados.add(sinal_id)
            self.sinais_dispensados.discard(sinal_id)

        # Ao ACATAR, a sugestão vira uma POSIÇÃO REAL no diário — aparece como
        # "rodando" no dashboard, com P&L atualizado a cada ciclo de preço.
        if decisao in ("ACATOU_COMPRA", "ACATOU_VENDA"):
            sinal = next((s for s in carregar_sinais_log() if s["id"] == sinal_id), None)
            if sinal:
                # Evita duplicar posição se clicar duas vezes no mesmo sinal
                ja_aberta = any(
                    p.get("origem") == "ROBO" and p.get("sinal_id") == sinal_id
                    for p in carregar_posicoes()
                )
                if not ja_aberta:
                    direcao = "BUY" if decisao == "ACATOU_COMPRA" else "SELL"
                    plano = carregar_config().get("plano_trading", {})
                    sizing = calcular_contratos(
                        sinal["entry"], sinal["stop"], sinal.get("ativo", ""),
                        plano.get("margem", 0), plano.get("risco_pct", 1.0),
                        plano.get("drawdown_maximo", 0)
                    )
                    pos = abrir_posicao(
                        "ROBO", direcao, sinal.get("ativo", "DESCONHECIDO"),
                        sinal["entry"], sinal["stop"], sinal.get("tp1"), sinal.get("tp2"),
                        sizing["contratos"] or 1,
                        status_inicial="PENDENTE"  # só executa se o preço tocar a entrada
                    )
                    # vincula ao sinal para não duplicar
                    lista = carregar_posicoes()
                    for p in lista:
                        if p["id"] == pos["id"]:
                            p["sinal_id"] = sinal_id
                    salvar_posicoes(lista)
                    self.log(f"⏳ Ordem PENDENTE registrada: {direcao} {pos['ativo']} @ {pos['entry']} "
                              f"({pos['contratos']} ctr) — aguardando o preço tocar a entrada.")
        self._atualizar_dashboard()

    def _ultimo_sinal_pendente(self):
        """O sinal mais recente que o trader ainda NÃO decidiu (acatar/dispensar).
        É a ele que os comandos ACATAR/DISPENSAR do WhatsApp se aplicam."""
        pendentes = [s for s in carregar_sinais_log() if not s.get("decisao")]
        return pendentes[-1] if pendentes else None

    def _poller_comandos_whatsapp(self):
        """Lê a fila de comandos do motor (GET /comandos) e aplica ACATAR/
        DISPENSAR ao último cenário pendente — o mesmo efeito dos botões do
        dashboard, mas acionado pela mensagem no WhatsApp."""
        while True:
            time.sleep(4)
            try:
                r = requests.get(f"{BAILEYS_URL}/comandos", timeout=3)
                if r.status_code != 200:
                    continue
                comandos = r.json().get("comandos", [])
            except Exception:
                continue  # motor fora do ar ou sem resposta: tenta no próximo ciclo

            for cmd in comandos:
                tipo = cmd.get("tipo")
                if tipo not in ("ACATAR", "DISPENSAR"):
                    continue
                sinal = self._ultimo_sinal_pendente()
                if not sinal:
                    self.log("💬 Comando do WhatsApp recebido, mas não há cenário recente "
                              "pendente para aplicar.")
                    continue
                if tipo == "ACATAR":
                    decisao = "ACATOU_COMPRA" if sinal.get("direcao") == "BUY" else "ACATOU_VENDA"
                else:
                    decisao = "NAO_OPEROU"
                sid = sinal["id"]
                self.log(f"💬 WhatsApp: {tipo} aplicado ao cenário {sinal.get('direcao')} "
                          f"{sinal.get('ativo')} (id {sid}).")
                # Executa na thread da GUI (mexe no diário e no dashboard).
                self.after(0, lambda s=sid, d=decisao: self._registrar_decisao(s, d))

    # ------------------------------------------------------------------
    # LIGAR MOTOR — dispara tudo numa thread separada para não travar a GUI
    # ------------------------------------------------------------------
    def alternar_motor(self):
        """Botão único: LIGAR quando parado, DESLIGAR quando rodando."""
        if self.motor_rodando or self.robo_ativo:
            self.desligar()
        else:
            self.iniciar()

    def desligar(self):
        self.log("🛑 Desligando motor...")
        self.btn_ligar.configure(state="disabled", text="Desligando...")
        # Sinaliza a parada; o loop do robô sai em até ~1 segundo.
        self.parar_solicitado = True
        self.motor_rodando = False
        threading.Thread(target=self._thread_desligar_motor, daemon=True).start()

    def _thread_desligar_motor(self):
        if self.processo_motor and self.processo_motor.poll() is None:
            try:
                self.processo_motor.terminate()
                self.processo_motor.wait(timeout=5)
            except Exception:
                try:
                    self.processo_motor.kill()
                except Exception:
                    pass
        self.processo_motor = None
        self.robo_ativo = False

        def _restaurar_ui():
            self._limpar_qr("Motor desligado.")
            self.btn_ligar.configure(state="normal", text="▶️ LIGAR MOTOR", fg_color="green",
                                      hover_color="#1f8b4c")
            self.log("✅ Motor desligado. As análises foram interrompidas.")
            self.log("ℹ️ Suas posições e o histórico continuam salvos no dashboard.")
        self.after(0, _restaurar_ui)

    def iniciar(self):
        api_key = self.api_entry.get().strip()
        if not api_key:
            self.log("⚠️ Cole a chave da Gemini API primeiro.")
            return

        try:
            intervalo_minutos = max(int(self.intervalo_vivo_var.get().strip()), 1)
        except ValueError:
            self.log("⚠️ Intervalo entre análises inválido — usando 15 min.")
            intervalo_minutos = 15

        salvar_api_key(api_key)
        salvar_config({
            "nome_janela_corretora": self.janela_var.get(),
            "intervalo_minutos": intervalo_minutos,
            "hora_inicio": self.entry_hora_inicio.get().strip() or "09:00",
            "hora_fim": self.entry_hora_fim.get().strip() or "17:00",
        })

        self.parar_solicitado = False
        self.btn_ligar.configure(state="disabled", text="Iniciando...")
        self.log("Iniciando motor Node.js...")
        threading.Thread(target=self._thread_iniciar_motor, daemon=True).start()

    def _thread_iniciar_motor(self):
        try:
            self._preparar_pasta_motor()
            self._garantir_dependencias_node()
            self._subir_processo_node()
        except Exception as e:
            self.log(f"⚠️ Falha: {e}")
            self.after(0, lambda: self.btn_ligar.configure(state="normal", text="▶️ LIGAR MOTOR", fg_color="green", hover_color="#1f8b4c"))
            return

        threading.Thread(target=self._ler_saida_motor, daemon=True).start()
        if self.motor_rodando:
            threading.Thread(target=self._poll_status_qr, daemon=True).start()

    def _preparar_pasta_motor(self):
        self.log("📁 Preparando pasta do motor...")
        os.makedirs(DIR_DADOS_MOTOR, exist_ok=True)

        for nome_arquivo in ("index.js", "package.json"):
            origem = os.path.join(DIR_ORIGEM_MOTOR, nome_arquivo)
            destino = os.path.join(DIR_DADOS_MOTOR, nome_arquivo)

            if os.path.exists(origem):
                with open(origem, "rb") as f_in, open(destino, "wb") as f_out:
                    f_out.write(f_in.read())

        # Validação CRÍTICA: sem esses dois arquivos, o `npm install` roda numa
        # pasta vazia e falha com "npm error enoent" — um erro incompreensível
        # para o usuário final. Melhor falhar aqui, com instrução clara.
        faltando = [
            nome for nome in ("index.js", "package.json")
            if not os.path.exists(os.path.join(DIR_DADOS_MOTOR, nome))
        ]
        if faltando:
            raise FileNotFoundError(
                f"Arquivos do motor não encontrados: {', '.join(faltando)}.\n\n"
                f"SOLUÇÃO: a pasta 'motor' (contendo index.js e package.json) precisa estar "
                f"na MESMA PASTA do programa:\n{DIR_ORIGEM_MOTOR}\n\n"
                f"Se você extraiu de um .zip, confirme que a pasta 'motor' veio junto e "
                f"está ao lado do SMC_Quant_Pro.exe."
            )

        self.log(f"✅ Motor preparado em: {DIR_DADOS_MOTOR}")

        # Se a distribuição já inclui o node_modules pronto (recomendado), copia
        # para os dados do usuário. Assim o cliente NÃO precisa rodar npm install
        # nem ter git instalado — a origem mais comum de falha no primeiro uso.
        origem_nm = os.path.join(DIR_ORIGEM_MOTOR, "node_modules")
        destino_nm = os.path.join(DIR_DADOS_MOTOR, "node_modules")
        if os.path.isdir(origem_nm) and not os.path.isdir(destino_nm):
            self.log("📦 Copiando dependências pré-instaladas (sem necessidade de internet ou git)...")
            try:
                import shutil
                shutil.copytree(origem_nm, destino_nm)
                self.log("✅ Dependências pré-instaladas copiadas com sucesso.")
            except Exception as e:
                self.log(f"⚠️ Não consegui copiar as dependências prontas ({e}). "
                          "Tentarei instalar via npm.")
        """O Baileys depende de 'libsignal' hospedado no GitHub, então o npm
        precisa do git instalado para baixá-lo. Verificamos antes de tentar."""
        try:
            subprocess.run(["git", "--version"], check=True, capture_output=True,
                            shell=(os.name == "nt"))
            return True
        except Exception:
            return False

    def _git_disponivel(self):
        """O Baileys depende de 'libsignal' hospedado no GitHub, então o npm
        precisa do git instalado para baixá-lo. Verificamos antes de tentar."""
        try:
            subprocess.run(["git", "--version"], check=True, capture_output=True,
                            shell=(os.name == "nt"))
            return True
        except Exception:
            return False

    def _garantir_dependencias_node(self):
        self.log("📦 Verificando dependências do motor...")
        node_modules = os.path.join(DIR_DADOS_MOTOR, "node_modules")
        if os.path.isdir(node_modules):
            self.log("✅ Dependências já instaladas — pulando npm install.")
            return

        # PRÉ-REQUISITO: o Baileys puxa 'libsignal' direto do GitHub, o que
        # exige git. Sem git, o npm falha com "spawn git ENOENT". Checamos
        # antes para dar uma instrução clara em vez do erro críptico.
        if not self._git_disponivel():
            raise RuntimeError(
                "O Git não está instalado neste computador.\n\n"
                "O motor do WhatsApp precisa do Git para baixar um de seus componentes "
                "de segurança (libsignal) na primeira instalação.\n\n"
                "COMO RESOLVER (uma única vez):\n"
                "1. Baixe o Git em: https://git-scm.com/download/win\n"
                "2. Instale (pode dar Avançar em tudo, as opções padrão servem)\n"
                "3. FECHE e abra o SMC Quant Pro novamente\n"
                "4. Clique em LIGAR MOTOR outra vez\n\n"
                "Isso só é necessário na primeira vez. Depois de instalado, o Git "
                "não precisa mais ser aberto nem configurado."
            )

        self.log("Instalando dependências do Node (primeira vez, pode levar 1-2 min)...")
        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
        processo = subprocess.Popen(
            [npm_cmd, "install"], cwd=DIR_DADOS_MOTOR, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            shell=(os.name == "nt")
        )
        saida_completa = []
        for linha in processo.stdout:
            saida_completa.append(linha)
            self.log(linha.rstrip())
        codigo = processo.wait()
        if codigo != 0:
            texto = "".join(saida_completa).lower()
            # Erro específico de git ausente/não encontrado no PATH
            if "spawn git" in texto or ("git" in texto and "enoent" in texto):
                raise RuntimeError(
                    "A instalação falhou porque o npm não encontrou o Git.\n\n"
                    "Se você ACABOU de instalar o Git, é preciso FECHAR e abrir o "
                    "SMC Quant Pro de novo para que ele reconheça o Git.\n\n"
                    "Se ainda não instalou: baixe em https://git-scm.com/download/win, "
                    "instale, reinicie o programa e tente novamente."
                )
            raise RuntimeError(
                f"A instalação das dependências falhou (código {codigo}).\n\n"
                "Causas mais comuns:\n"
                "• Sem conexão com a internet (o npm precisa baixar os pacotes)\n"
                "• Antivírus/firewall bloqueando o npm\n"
                "• Node.js instalado incorretamente\n\n"
                "Veja o log acima para o erro específico."
            )
        self.log("✅ Dependências instaladas.")

    def _subir_processo_node(self):
        self.log("🚀 Iniciando processo do motor (node index.js)...")

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW

        self.processo_motor = subprocess.Popen(
            ["node", "index.js"], cwd=DIR_DADOS_MOTOR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            startupinfo=startupinfo, creationflags=creationflags,
        )
        self.motor_rodando = True
        self.log(f"✅ Processo criado (PID {self.processo_motor.pid}). Aguardando resposta...")
        self.after(0, lambda: self.btn_ligar.configure(
            state="normal", text="⏹️ DESLIGAR MOTOR", fg_color="#8b1f1f", hover_color="#b52626"))

        time.sleep(1.5)
        if self.processo_motor.poll() is not None:
            self.motor_rodando = False
            self.log(f"⚠️ O processo do Node encerrou IMEDIATAMENTE (código {self.processo_motor.returncode}). "
                      "Causa mais provável: já existe um 'node.exe' órfão de um teste anterior segurando a "
                      "porta 3939. Abra o Gerenciador de Tarefas, finalize todo processo 'node.exe' e tente "
                      "'LIGAR MOTOR' de novo.")
            self.after(0, lambda: self.btn_ligar.configure(state="normal", text="▶️ LIGAR MOTOR", fg_color="green", hover_color="#1f8b4c"))

    def _ler_saida_motor(self):
        # Leitura do stdout do Node por linha, decodificando manualmente
        # (o stream vem em bytes). readline() bloqueia até ter uma linha ou
        # o processo fechar — isso funciona de forma confiável no Windows,
        # ao contrário do text=True + bufsize=1 que engasgava.
        try:
            for linha_bytes in iter(self.processo_motor.stdout.readline, b""):
                if not linha_bytes:
                    break
                texto = linha_bytes.decode("utf-8", errors="replace").rstrip()
                if texto:
                    self.log(texto)
        except Exception as e:
            self.log(f"(leitura de log encerrada: {e})")

        self.motor_rodando = False
        if not self.parar_solicitado:
            self.log("⚠️ O processo do motor foi encerrado.")
            self.after(0, lambda: self.btn_ligar.configure(state="normal", text="▶️ LIGAR MOTOR", fg_color="green", hover_color="#1f8b4c"))

    def _poll_status_qr(self):
        ultimo_status = None
        ultimo_qr_mostrado = None
        primeira_conexao_ok = False
        while self.motor_rodando:
            if self.processo_motor and self.processo_motor.poll() is not None:
                break
            try:
                resposta = requests.get(f"{BAILEYS_URL}/qrcode", timeout=3)
                dados = resposta.json()
                status = dados.get("status")
                qr_base64 = dados.get("qrCodeBase64")

                if not primeira_conexao_ok:
                    primeira_conexao_ok = True
                    self.log("✅ Comunicação com o motor estabelecida (porta 3939 respondendo).")

                # Ações de LIMPEZA só disparam na mudança de status — não a
                # cada ciclo de 2s (era isso que gerava erro em loop no Tk).
                if status != ultimo_status:
                    ultimo_status = status
                    self.log(f"📡 Status do WhatsApp: {status}")

                    if status == "CONECTADO":
                        self._limpar_qr("✅ WhatsApp conectado!")
                        if not self.robo_ativo:
                            self.robo_ativo = True
                            threading.Thread(target=self._loop_robo_quant, daemon=True).start()
                    elif status == "DESCONECTADO":
                        self._limpar_qr("⚠️ Desconectado — aguardando novo QR...")
                        ultimo_qr_mostrado = None

                # Exibição do QR: só redesenha se o conteúdo realmente mudou
                # (o WhatsApp pode gerar um QR novo periodicamente enquanto
                # aguarda o escaneamento, mesmo com o status permanecendo
                # "AGUARDANDO_QR").
                if status == "AGUARDANDO_QR" and qr_base64 and qr_base64 != ultimo_qr_mostrado:
                    ultimo_qr_mostrado = qr_base64
                    self._mostrar_qr(qr_base64)

            except requests.exceptions.ConnectionError:
                pass  # motor ainda subindo — normal nos primeiros segundos
            except Exception as e:
                self.log(f"(polling status: {e})")
            time.sleep(2)

    def _mostrar_qr(self, qr_base64_data_url: str):
        try:
            base64_puro = qr_base64_data_url.split(",", 1)[1]
            imagem_bytes = base64.b64decode(base64_puro)
            imagem_pil = Image.open(BytesIO(imagem_bytes)).convert("RGB")
            imagem_ctk = ctk.CTkImage(light_image=imagem_pil, dark_image=imagem_pil, size=(280, 280))

            def _atualizar():
                self.lbl_qr_titulo.configure(text="📲 Escaneie o QR Code no WhatsApp:")
                self.lbl_qr_imagem.configure(image=imagem_ctk, text="")
                self.lbl_qr_imagem.image = imagem_ctk
            self.after(0, _atualizar)
        except Exception as e:
            import traceback
            self.log(f"❌ ERRO REAL ao renderizar QR: {e}")
            self.log(traceback.format_exc())

    def _limpar_qr(self, mensagem: str):
        def _atualizar():
            self.lbl_qr_titulo.configure(text=mensagem)
            self.lbl_qr_imagem.configure(image=self._imagem_qr_vazia, text="")
            self.lbl_qr_imagem.image = self._imagem_qr_vazia
        self.after(0, _atualizar)

    # ------------------------------------------------------------------
    # NÚCLEO DO ROBÔ SMC (foco de janela + máquina de estados + aprendizado)
    # ------------------------------------------------------------------
    def _loop_robo_quant(self):
        self.log("\n🚀 ROBÔ SMC INICIADO COM MÓDULO DE APRENDIZADO E FOCO DE JANELA!")
        falar("Integração concluída. Sistemas de proteção visual e aprendizado ativados.")

        api_key = carregar_api_key()
        # Timeout de 25s (era 60s): uma análise de gráfico responde em ~5–15s.
        # Se um modelo fica "sobrecarregado" e trava, 60s de espera num único
        # modelo é inaceitável — 25s já derruba o modelo lento e passa ao próximo.
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=25_000))

        # Cooldown por modelo: quando um modelo dá cota esgotada (429) ou fica
        # sobrecarregado (503), ele é "estacionado" por um tempo. Assim paramos
        # de gastar ida-e-volta de rede tentando modelos mortos EM TODO CICLO —
        # o maior ralo de tempo quando a cota diária começa a estourar.
        cooldown_modelos = {}   # nome_modelo -> timestamp (epoch) até quando pular
        COOLDOWN_COTA = 900     # 429 cota esgotada: pula por 15 min
        COOLDOWN_SOBRECARGA = 120  # 503/timeout: pula por 2 min

        # Lista de modelos de reserva: se o principal esgotar a cota (comum
        # no plano gratuito — 20 requisições/dia por modelo), tenta os
        # próximos automaticamente em vez de travar o ciclo inteiro.
        def montar_lista_fallback():
            # Ordem de preferência: modelos atuais primeiro. O gemini-2.5-flash
            # foi descontinuado para novas contas (erro 404), por isso não
            # lidera mais a lista — fica só como reserva para contas antigas.
            # Ordem por VELOCIDADE + DISPONIBILIDADE real observada em produção.
            # Os aliases "-latest" e o "3.5-flash" vivem dando 503/sobrecarga e
            # gastavam segundos de espera todo ciclo antes de cair no que funciona,
            # por isso foram REBAIXADOS. Lideram agora os modelos flash estáveis e
            # os *-lite (os mais rápidos), que respondem na primeira tentativa.
            preferencia = [
                "gemini-2.0-flash",          # estável, rápido, amplamente disponível
                "gemini-2.0-flash-001",
                "gemini-2.5-flash",          # rápido; reserva imediata
                "gemini-2.5-flash-lite",     # ainda mais rápido (baixa latência)
                "gemini-2.0-flash-lite-001",
                "gemini-2.0-flash-lite",
                "gemini-3-flash-preview",    # respondeu bem nos testes recentes
                "gemini-flash-latest",       # alias — costuma estar sobrecarregado
                "gemini-flash-lite-latest",
                "gemini-3.5-flash",          # frequentemente indisponível
            ]
            try:
                disponiveis = [m.name.replace("models/", "") for m in client.models.list()
                                if "generateContent" in m.supported_actions]
                ordenados = [m for m in preferencia if m in disponiveis]
                # Variantes de tts/image/audio não servem para analisar gráfico.
                inadequados = ("tts", "image", "audio", "omni", "embedding")
                extras = [m for m in disponiveis
                           if "flash" in m and m not in ordenados
                           and not any(x in m.lower() for x in inadequados)]
                return ordenados + extras or preferencia
            except Exception as e:
                self.log(f"⚠️ Não consegui listar modelos disponíveis, usando lista padrão: {e}")
                return preferencia

        modelos_fallback = montar_lista_fallback()
        modelos_invalidos = set()  # descontinuados (404) — expurgados da lista
        self.log(f"✅ Modelos disponíveis (ordem de tentativa): {modelos_fallback}")

        SIGNAL_SCHEMA = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "asset_symbol": types.Schema(
                    type=types.Type.STRING,
                    description="O ticker/símbolo do ativo sendo operado, lido diretamente do gráfico "
                                "(ex: MESU6, MNQU6, ESZ5). Se não for possível identificar, retorne 'DESCONHECIDO'."
                ),
                "current_price": types.Schema(type=types.Type.NUMBER),
                "market_analysis": types.Schema(type=types.Type.STRING),
                "confluence_factors": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING)
                ),
                "confidence_score": types.Schema(type=types.Type.NUMBER),
                "probabilidade": types.Schema(
                    type=types.Type.NUMBER,
                    description="Probabilidade estimada (0 a 100) de o cenário se concretizar até o "
                                "objetivo 1 antes de invalidar. Baseie-se na quantidade e qualidade das "
                                "confluências, na clareza da estrutura e no histórico do feedback loop."
                ),
                "action": types.Schema(
                    type=types.Type.STRING,
                    enum=["BUY", "SELL", "HOLD"]
                ),
                "entry_price": types.Schema(type=types.Type.NUMBER),
                "stop_loss": types.Schema(type=types.Type.NUMBER),
                "take_profit_1": types.Schema(type=types.Type.NUMBER),
                "take_profit_2": types.Schema(type=types.Type.NUMBER),
                "ledger_update": types.Schema(type=types.Type.STRING)
            },
            required=[
                "asset_symbol", "current_price", "market_analysis", "confluence_factors",
                "confidence_score", "probabilidade", "action", "ledger_update"
            ]
        )

        config_horario = carregar_config()
        INTERVALO_MINUTOS = config_horario.get("intervalo_minutos", 15)
        BUFFER_SEGUNDOS = 5
        MAX_CANDLES = 6
        HORA_INICIO = config_horario.get("hora_inicio", "09:00")
        HORA_FIM = config_horario.get("hora_fim", "17:00")
        sinal_ativo = {"estado": "ENCERRADA"}
        ledger_text_memory = "Nenhuma operação aberta no momento. Aguardando primeiro sinal institucional."
        # Controle de captura congelada (ver hash_imagem)
        hash_captura_anterior = None
        capturas_congeladas = 0
        # Controle de preço estagnado
        preco_anterior_lido = None
        ciclos_preco_igual = 0
        self.log(f"⚙️ Intervalo: {INTERVALO_MINUTOS} min | Pregão: {HORA_INICIO}–{HORA_FIM} "
                  "(fora desse horário, ciclos são pulados pra economizar cota da API)")

        def dentro_do_horario_pregao():
            try:
                agora = datetime.datetime.now().time()
                inicio = datetime.datetime.strptime(HORA_INICIO, "%H:%M").time()
                fim = datetime.datetime.strptime(HORA_FIM, "%H:%M").time()
                return inicio <= agora <= fim
            except ValueError:
                return True  # horário mal configurado — não bloqueia, roda sempre

        def segundos_ate_proximo_fechamento(intervalo_min):
            agora = datetime.datetime.now()
            minutos_desde_meia_noite = agora.hour * 60 + agora.minute
            proximo_multiplo = ((minutos_desde_meia_noite // intervalo_min) + 1) * intervalo_min
            proximo_fechamento = agora.replace(second=0, microsecond=0) + datetime.timedelta(
                minutes=(proximo_multiplo - minutos_desde_meia_noite)
            )
            espera = (proximo_fechamento - agora).total_seconds() + BUFFER_SEGUNDOS
            return max(espera, 1)

        while not self.parar_solicitado:
            try:
                # Relê o intervalo a cada ciclo — permite que o usuário
                # altere no dropdown "ao vivo" sem reiniciar o motor.
                intervalo_atual = carregar_config().get("intervalo_minutos", INTERVALO_MINUTOS)
                espera = segundos_ate_proximo_fechamento(intervalo_atual)
                self.log(f"⏳ Aguardando {espera:.1f}s até o próximo ciclo (intervalo: {intervalo_atual} min)...")

                # Dorme em fatias de 1s para que DESLIGAR o motor tenha efeito
                # imediato, em vez de esperar até 60 min pelo fim do sleep.
                restante = espera
                while restante > 0 and not self.parar_solicitado:
                    time.sleep(min(1, restante))
                    restante -= 1
                if self.parar_solicitado:
                    break

                if not dentro_do_horario_pregao():
                    self.log(f"🌙 Fora do horário de pregão ({HORA_INICIO}–{HORA_FIM}) — ciclo pulado sem consumir a API.")
                    continue

                # --------------------------------------------------------
                # CAPTURA EM SEGUNDO PLANO: pega o conteúdo da janela da
                # corretora diretamente, SEM trazê-la para frente e sem
                # tirar o usuário do que ele estiver fazendo em outro
                # programa. Se não achar a janela ou a captura vier em
                # branco, pula o ciclo em vez de analisar lixo visual.
                # --------------------------------------------------------
                nome_janela = carregar_config().get("nome_janela_corretora", "").strip()
                hora_atual = time.strftime('%H:%M:%S')

                if nome_janela:
                    hwnd = encontrar_janela_por_titulo(nome_janela)
                    if not hwnd:
                        self.log(f"⚠️ ERRO DE VISUALIZAÇÃO: não encontrei a janela '{nome_janela}'. "
                                  "Pulando este ciclo.")
                        enviar_relatorio_whatsapp(
                            f"⚠️ *Erro de Visualização*\nJanela '{nome_janela}' não encontrada. "
                            "Verifique se a corretora está aberta. Ciclo pulado.",
                            None, self.log
                        )
                        falar("Atenção. Janela da corretora não encontrada. Ciclo pulado.")
                        continue

                    self.log(f"📸 [{hora_atual}] Capturando '{nome_janela}' em segundo plano...")

                    # ---------- CAPTURA EM CAMADAS (agnóstica de aplicativo) ----------
                    # Camada 1: prepara a janela (restaura se minimizada — só se o
                    # usuário permitir — e força repintura), depois PrintWindow.
                    # Se a janela já está visível, NADA aqui altera foco ou z-order.
                    permite_restaurar = carregar_config().get("restaurar_janela_minimizada", True)
                    if not garantir_janela_renderizando(hwnd, permite_restaurar):
                        self.log(f"⏸️ '{nome_janela}' está MINIMIZADA e a restauração automática está "
                                  "desativada. Ciclo pulado (janela minimizada não pode ser capturada).")
                        continue

                    screenshot = capturar_janela_em_segundo_plano(hwnd)
                    metodo = "PrintWindow"

                    if screenshot is not None and not imagem_esta_em_branco(screenshot):
                        h = hash_imagem(screenshot)
                        # Camada 2: se veio congelada, tenta uma segunda repintura
                        # mais agressiva e recaptura antes de desistir.
                        if h and h == hash_captura_anterior:
                            self.log("🧊 Quadro idêntico ao anterior — forçando repintura e recapturando...")
                            garantir_janela_renderizando(hwnd, permite_restaurar)
                            time.sleep(0.6)
                            nova = capturar_janela_em_segundo_plano(hwnd)
                            if nova is not None and hash_imagem(nova) != h:
                                screenshot, metodo = nova, "PrintWindow (após repintura)"
                            else:
                                # Camada 3: PrintWindow insiste em quadro velho.
                                # Recorta a tela — sempre conteúdo atual.
                                recorte, sobreposto = capturar_via_recorte_de_tela(hwnd)
                                if recorte is not None and not sobreposto:
                                    screenshot, metodo = recorte, "Recorte de tela"
                                    self.log("✅ Recuperado via recorte de tela (conteúdo atual).")
                                elif sobreposto:
                                    self.log("🧊 A janela está COBERTA por outra e não redesenha. "
                                              "Análise suspensa neste ciclo.")
                                    screenshot = None
                    if screenshot is None or imagem_esta_em_branco(screenshot):
                        self.log(f"⚠️ ERRO DE VISUALIZAÇÃO: não consegui uma imagem atual de '{nome_janela}'. "
                                  "Deixe a janela visível (pode estar atrás de outras, mas não 100% coberta). "
                                  "Ciclo pulado.")
                        capturas_congeladas += 1
                        if capturas_congeladas == 2:
                            enviar_relatorio_whatsapp(
                                f"⚠️ *Análises suspensas — {time.strftime('%d/%m/%Y %H:%M:%S')}*\n"
                                f"Não estou conseguindo ler o gráfico de '{nome_janela}' com conteúdo atual. "
                                "Deixe a janela visível na tela. Nenhum relatório será enviado com dado defasado.",
                                None, self.log
                            )
                            falar("Atenção. Não consigo ler o gráfico atualizado. Análises suspensas.")
                        continue
                else:
                    self.log(f"📸 [{hora_atual}] Nenhuma janela específica configurada — capturando tela inteira...")
                    screenshot = ImageGrab.grab()
                    metodo = "Tela inteira"

                # ------------------------------------------------------------
                # REDE DE SEGURANÇA FINAL: se, apesar de todas as camadas, a
                # imagem ainda for idêntica à anterior, NÃO analisamos. Um
                # relatório com preço defasado é pior do que nenhum relatório.
                # ------------------------------------------------------------
                hash_atual = hash_imagem(screenshot)
                if hash_atual and hash_atual == hash_captura_anterior:
                    capturas_congeladas += 1
                    self.log(f"🧊 CAPTURA CONGELADA ({capturas_congeladas}x): imagem idêntica à do ciclo "
                              f"anterior mesmo após todas as tentativas de recuperação. Nenhuma análise feita.")
                    if capturas_congeladas == 2:
                        enviar_relatorio_whatsapp(
                            f"🧊 *Análises suspensas — {time.strftime('%d/%m/%Y %H:%M:%S')}*\n"
                            "O gráfico não está sendo redesenhado na tela. Deixe a janela da corretora "
                            "visível. Nenhum relatório será enviado com preço defasado.",
                            None, self.log
                        )
                        falar("Atenção. Captura congelada. Análises suspensas.")
                    continue

                if capturas_congeladas > 0:
                    self.log("✅ Captura voltou a atualizar — retomando as análises.")
                    capturas_congeladas = 0
                hash_captura_anterior = hash_atual
                self.log(f"🖼️ Imagem atual obtida via: {metodo}")

                self.log("🧠 Processando análise com Memória Episódica...")

                memoria_dinamica = compilar_memoria_prompt()
                PROMPT_BASE = (
                    "Você é um trader institucional de Smart Money Concepts (SMC/ICT) "
                    "operando índices futuros (ES/MES, NQ/MNQ). Sua leitura é criteriosa, "
                    "paciente e prioriza QUALIDADE sobre quantidade: é melhor não operar do "
                    "que forçar um trade fraco."
                )
                PROMPT_FINAL = (
                    f"{PROMPT_BASE}\n{memoria_dinamica}\n"
                    f"ÚLTIMO ESTADO DO LEDGER:\n{ledger_text_memory}\n"
                    "Identifique o TICKER do ativo no gráfico (asset_symbol) e leia o PREÇO "
                    "ATUAL com precisão pela última vela e pela escala de preço à direita.\n"
                    "\n"
                    "SIGA ESTE ROTEIRO DE ANÁLISE, NESTA ORDEM:\n"
                    "1) VIÉS (HTF): determine a tendência dominante pela ESTRUTURA visível "
                    "(sequência de BOS/CHoCH, topos/fundos). Só é BUY se a estrutura for de "
                    "alta; SELL se de baixa. Contra-tendência exige CHoCH confirmado + varredura "
                    "de liquidez clara — caso contrário, HOLD.\n"
                    "2) PREMIUM/DISCOUNT: marque o range relevante (perna atual). Compras SÓ em "
                    "DISCOUNT (abaixo de 50%); vendas SÓ em PREMIUM (acima de 50%). Preço em "
                    "EQUILÍBRIO (perto de 50%) ou no meio do range = HOLD.\n"
                    "3) LIQUIDEZ: exija uma varredura de liquidez (sweep de topo/fundo, ou "
                    "inducement) ANTES da entrada. Nunca entre MIRANDO liquidez que ainda não "
                    "foi tomada — o preço tende a buscá-la primeiro.\n"
                    "4) PONTO DE ENTRADA (POI): a entrada deve estar num Order Block NÃO mitigado "
                    "ou num Fair Value Gap (FVG) coerente com o viés. ENTRY_PRICE é sempre ordem "
                    "PENDENTE nesse POI (não a mercado).\n"
                    "5) STOP e ALVOS: stop_loss logo além do POI/estrutura que invalida a ideia. "
                    "take_profit_1 na liquidez interna/oposta mais próxima; take_profit_2 na "
                    "liquidez externa seguinte. O RISCO:RETORNO até o objetivo 1 deve ser de no "
                    "mínimo ~1.5. Se não houver R:R decente, retorne HOLD.\n"
                    "\n"
                    "REGRAS DE HONESTIDADE:\n"
                    "- Liste em confluence_factors APENAS confluências REAIS e visíveis no "
                    "gráfico (BOS/CHoCH, OB, FVG, sweep, premium/discount, equilíbrio). Não "
                    "invente fatores para justificar um trade.\n"
                    "- Se faltar confluência, se a estrutura estiver ambígua, ou se o preço já "
                    "estiver longe do POI, retorne action=HOLD com probabilidade baixa. HOLD é "
                    "uma resposta válida e desejada.\n"
                    "- 'probabilidade' (0 a 100): estimativa CALIBRADA e honesta de atingir o "
                    "objetivo 1 antes de invalidar. Poucas confluências ou contra-tendência => "
                    "probabilidade baixa. Use o histórico do feedback loop acima para calibrar. "
                    "NÃO infle.\n"
                    "- Coerência obrigatória: para BUY, stop < entry < tp1 <= tp2; para SELL, "
                    "stop > entry > tp1 >= tp2. Se não conseguir montar um cenário coerente, HOLD.\n"
                    "\n"
                    # ---- Sizing é responsabilidade EXCLUSIVA do plano da mesa ----
                    "NUNCA sugira quantidade de contratos, tamanho de posição, número de "
                    "lotes, alavancagem ou valores de risco em dólar no texto da análise nem "
                    "nas confluências. O dimensionamento (contratos e risco) é calculado APENAS "
                    "pelo plano de trading da conta-mesa do trader, fora da IA. Limite-se a "
                    "identificar o cenário (viés, entrada, stop, alvos e confluências)."
                )
                # Instrução de sistema: reforça o mesmo limite no nível do schema.
                INSTRUCAO_SISTEMA = (
                    "Retorne estritamente o JSON validado pelo Schema. "
                    "Não inclua quantidade de contratos, tamanho de posição nem valores de "
                    "risco: o sizing é definido exclusivamente pelo plano da mesa do trader."
                )

                resposta = None
                ultimo_erro = None
                modelo_vencedor = None

                # Só tenta modelos que NÃO estão em cooldown (cota/sobrecarga
                # recentes). Se todos estiverem estacionados, tenta a lista
                # inteira mesmo assim — melhor uma chance do que pular o ciclo.
                agora_ts = time.time()
                candidatos = [m for m in modelos_fallback
                               if cooldown_modelos.get(m, 0) <= agora_ts]
                if not candidatos:
                    candidatos = list(modelos_fallback)
                    self.log("⏳ Todos os modelos estão em cooldown de cota/sobrecarga — "
                              "tentando mesmo assim. (Considere aumentar o intervalo ou usar chave paga.)")

                for modelo_atual in candidatos:
                    try:
                        resposta = client.models.generate_content(
                            model=modelo_atual,
                            contents=[PROMPT_FINAL, screenshot],
                            config=types.GenerateContentConfig(
                                system_instruction=INSTRUCAO_SISTEMA,
                                response_mime_type="application/json",
                                response_schema=SIGNAL_SCHEMA,
                            )
                        )
                        modelo_vencedor = modelo_atual
                        cooldown_modelos.pop(modelo_atual, None)  # respondeu: sai do cooldown
                        if modelo_atual != candidatos[0]:
                            self.log(f"ℹ️ Análise concluída usando modelo de reserva: {modelo_atual}")
                        break
                    except Exception as e:
                        ultimo_erro = e
                        erro_str = str(e).upper()

                        # 404 / NOT_FOUND = o modelo NÃO EXISTE mais para esta
                        # conta (foi descontinuado). Não adianta tentar de novo
                        # nos próximos ciclos: removemos da lista de vez.
                        if ("404" in erro_str or "NOT_FOUND" in erro_str
                                or "NO LONGER AVAILABLE" in erro_str):
                            self.log(f"🚫 {modelo_atual} foi descontinuado — removendo da lista permanentemente.")
                            modelos_invalidos.add(modelo_atual)
                            continue

                        # Erros TRANSITÓRIOS ou de cota: vale tentar o próximo
                        # modelo em vez de derrubar o ciclo inteiro.
                        #   429 / RESOURCE_EXHAUSTED -> cota esgotada
                        #   503 / UNAVAILABLE        -> modelo sobrecarregado (alta demanda)
                        #   500 / INTERNAL           -> falha temporária do servidor
                        #   504 / DEADLINE / TIMED OUT -> timeout de rede
                        # ATENÇÃO: a mensagem real do SDK é "The read operation
                        # timed out" (com espaço). Procurar só por "TIMEOUT"
                        # deixava esse erro passar como fatal e matava o ciclo.
                        transitorios = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE",
                                         "500", "INTERNAL", "504", "DEADLINE", "TIMEOUT",
                                         "TIMED OUT", "OVERLOADED", "CONNECTION", "SSL",
                                         "TEMPORARILY")
                        if any(t in erro_str for t in transitorios):
                            eh_cota = ("429" in erro_str or "RESOURCE_EXHAUSTED" in erro_str)
                            # Estaciona o modelo para não desperdiçar rede nos
                            # próximos ciclos: cota -> 15 min, sobrecarga -> 2 min.
                            cooldown_modelos[modelo_atual] = time.time() + (
                                COOLDOWN_COTA if eh_cota else COOLDOWN_SOBRECARGA)
                            motivo = "cota esgotada (pausado 15min)" if eh_cota \
                                      else "sobrecarregado (pausado 2min)"
                            self.log(f"⚠️ {modelo_atual} {motivo} — próximo modelo...")
                            continue  # sem sleep: o próximo modelo já é uma nova requisição
                        raise  # erro real (ex: chave inválida): sobe pro tratamento do ciclo

                # Expurga de vez os modelos descontinuados, para não perder
                # tempo tentando-os em todos os ciclos seguintes.
                if modelos_invalidos:
                    modelos_fallback = [m for m in modelos_fallback if m not in modelos_invalidos]
                    modelos_invalidos.clear()
                    if not modelos_fallback:
                        raise RuntimeError("Nenhum modelo Gemini válido para esta chave de API.")
                    self.log(f"📋 Lista de modelos atualizada: {modelos_fallback[:4]}...")

                # APRENDIZADO DE VELOCIDADE: o modelo que respondeu AGORA passa a
                # ser o primeiro tentado no próximo ciclo. Assim paramos de perder
                # tempo re-tentando modelos que vivem dando "indisponível" antes
                # dele — o ciclo seguinte já começa pelo que funciona.
                if modelo_vencedor and modelos_fallback and modelos_fallback[0] != modelo_vencedor:
                    modelos_fallback = ([modelo_vencedor] +
                                         [m for m in modelos_fallback if m != modelo_vencedor])

                if resposta is None:
                    raise RuntimeError(
                        f"Todos os modelos disponíveis falharam. Último erro: {ultimo_erro}"
                    )

                sinal = json.loads(resposta.text)
                preco = sinal.get("current_price")
                acao = sinal.get("action", "HOLD")
                confianca = sinal.get("confidence_score", 0)
                probabilidade = sinal.get("probabilidade", 0)
                confluencias = sinal.get("confluence_factors", []) or []
                ativo = sinal.get("asset_symbol", "DESCONHECIDO")
                ledger_text_memory = sinal.get("ledger_update", ledger_text_memory)

                self.log(f"📊 Ativo: {ativo} | Leitura IA: {acao} | Confiança: {confianca}% | "
                          f"Probabilidade: {probabilidade}% | Preço: {preco}")

                # Segunda camada de defesa: mesmo com a imagem mudando (relógio,
                # cursor), o PREÇO não deveria ficar idêntico por vários ciclos
                # com o mercado aberto. Se ficar, algo está errado na leitura.
                if preco is not None and preco == preco_anterior_lido:
                    ciclos_preco_igual += 1
                    if ciclos_preco_igual >= 2:
                        self.log(f"⚠️ ATENÇÃO: o preço lido ({preco}) não muda há {ciclos_preco_igual + 1} ciclos. "
                                  f"Verifique se o gráfico está realmente atualizando na tela e se o mercado "
                                  f"está aberto. Os relatórios podem estar refletindo dados defasados.")
                else:
                    ciclos_preco_igual = 0
                preco_anterior_lido = preco
                if confluencias:
                    self.log("🔎 Confluências identificadas:")
                    for c in confluencias:
                        self.log(f"    • {c}")
                else:
                    self.log("🔎 Nenhuma confluência relevante neste ciclo.")

                # ---------- DIÁRIO DE TRADER: máquina de estados das posições ----------
                eventos_pos = atualizar_posicoes_com_preco(preco, ativo)
                for tipo, pos in eventos_pos:
                    if tipo == "EXECUTADA":
                        self.log(f"✅ ENTRADA EXECUTADA: {pos['direcao']} {pos['ativo']} @ {pos['entry']} "
                                  f"— o preço tocou a região. Posição agora conta P&L.")
                    elif tipo == "CANCELADA":
                        self.log(f"🚫 ORDEM CANCELADA: {pos['direcao']} {pos['ativo']} @ {pos['entry']} — "
                                  f"o preço rompeu o stop antes de tocar a entrada. Nunca foi executada.")
                    else:
                        # STOP ou ALVO: operação real encerrada -> notifica no WhatsApp
                        emoji = "🔴" if tipo == "STOP" else "🟢"
                        msg_pos = (f"{emoji} *Operação encerrada ({tipo})*\n"
                                    f"🕐 {time.strftime('%d/%m/%Y %H:%M:%S')}\n"
                                    f"{pos['direcao']} {pos['ativo']} | Entrada {pos['entry']}\n"
                                    f"Resultado: US${pos['pnl_final']:+.2f} ({pos['contratos']} contrato(s))")
                        self.log(msg_pos.replace("*", ""))
                        enviar_relatorio_whatsapp(msg_pos, None, self.log)

                if preco is not None:
                    self.after(0, self._atualizar_dashboard)

                # DISPENSA PELO TRADER: se o cenário ativo corresponde a um sinal
                # que o trader marcou como "Não operei", encerramos o
                # acompanhamento — nada de seguir mandando "Cenário em PENDENTE".
                if (sinal_ativo.get("estado") != "ENCERRADA"
                        and sinal_ativo.get("sinal_id") in self.sinais_dispensados):
                    self.log("🚪 Cenário dispensado pelo trader (Não operei) — "
                              "acompanhamento encerrado, sem novos avisos de pendente.")
                    self.sinais_dispensados.discard(sinal_ativo.get("sinal_id"))
                    sinal_ativo = {"estado": "ENCERRADA"}

                # ACOMPANHAMENTO SÓ SE ACATADO: o robô só manda follow-up no
                # WhatsApp (entrada acionada, alvo, stop, acompanhamento) de um
                # cenário que o trader ACATOU (no dashboard ou no WhatsApp). Um
                # cenário não acatado recebe só a sugestão inicial, sem follow-up.
                acatado_atual = sinal_ativo.get("sinal_id") in self.sinais_acatados

                # ---------------- MÁQUINA DE ESTADOS ----------------
                if sinal_ativo["estado"] != "ENCERRADA" and preco is not None:
                    direcao = sinal_ativo["direcao"]

                    if sinal_ativo["estado"] == "PENDENTE":
                        sinal_ativo["candles"] += 1
                        bateu_entrada = (direcao == "BUY" and preco <= sinal_ativo["entry"]) or \
                                         (direcao == "SELL" and preco >= sinal_ativo["entry"])
                        rompeu_stop = (direcao == "BUY" and preco <= sinal_ativo["stop"]) or \
                                      (direcao == "SELL" and preco >= sinal_ativo["stop"])

                        if rompeu_stop:
                            sinal_ativo = {"estado": "ENCERRADA"}
                            self.log("🚫 SINAL CANCELADO: Stop rompido antes de mitigar a entrada.")
                        elif bateu_entrada:
                            sinal_ativo["estado"] = "ATIVA"
                            msg = f"🎯 *ENTRADA ACIONADA — {direcao}*\nPreço mitigou a zona em {sinal_ativo['entry']}."
                            self.log(msg)
                            if acatado_atual:
                                enviar_relatorio_whatsapp(msg, screenshot, self.log)
                                falar(f"Ordem de {direcao} ativada no mercado.")
                        elif sinal_ativo["candles"] >= MAX_CANDLES:
                            sinal_ativo = {"estado": "ENCERRADA"}
                            self.log("⌛ SINAL EXPIRADO: Nenhuma mitigação no tempo limite.")

                    elif sinal_ativo["estado"] == "ATIVA":
                        bateu_stop = (direcao == "BUY" and preco <= sinal_ativo["stop"]) or \
                                     (direcao == "SELL" and preco >= sinal_ativo["stop"])
                        bateu_tp2 = (direcao == "BUY" and preco >= sinal_ativo["tp2"]) or \
                                    (direcao == "SELL" and preco <= sinal_ativo["tp2"])
                        bateu_tp1 = (direcao == "BUY" and preco >= sinal_ativo["tp1"]) or \
                                    (direcao == "SELL" and preco <= sinal_ativo["tp1"])

                        if bateu_stop:
                            salvar_resultado_performance(direcao, sinal_ativo["entry"], sinal_ativo["stop"],
                                                          sinal_ativo["tp1"], preco, "LOSS", ativo)
                            sinal_ativo = {"estado": "ENCERRADA"}
                            msg = f"🔴 *STOP ATINGIDO (LOSS) — {direcao}*\nOperação invalidada em {preco}."
                            self.log(msg)
                            if acatado_atual:
                                enviar_relatorio_whatsapp(msg, screenshot, self.log)
                                falar("Stop atingido. Dados gravados no banco de aprendizado.")
                            self.after(0, self._atualizar_dashboard)

                        elif bateu_tp2:
                            salvar_resultado_performance(direcao, sinal_ativo["entry"], sinal_ativo["stop"],
                                                          sinal_ativo["tp2"], preco, "WIN", ativo)
                            sinal_ativo = {"estado": "ENCERRADA"}
                            msg = f"🟢🟢 *TAKE PROFIT 2 (WIN) — {direcao}*\nLucro máximo em {preco}."
                            self.log(msg)
                            if acatado_atual:
                                enviar_relatorio_whatsapp(msg, screenshot, self.log)
                                falar("Take profit final atingido. Excelente operação.")
                            self.after(0, self._atualizar_dashboard)

                        elif bateu_tp1 and not sinal_ativo.get("tp1_notificado"):
                            sinal_ativo["tp1_notificado"] = True
                            salvar_resultado_performance(direcao, sinal_ativo["entry"], sinal_ativo["stop"],
                                                          sinal_ativo["tp1"], preco, "WIN", ativo)
                            msg = f"🟢 *TAKE PROFIT 1 (WIN PARCIAL) — {direcao}*\nParcial realizada em {preco}."
                            self.log(msg)
                            if acatado_atual:
                                enviar_relatorio_whatsapp(msg, screenshot, self.log)
                            self.after(0, self._atualizar_dashboard)

                # ---------------- NOVO SINAL (se estado livre) ----------------
                if sinal_ativo["estado"] == "ENCERRADA" and acao in ("BUY", "SELL") \
                        and sinal.get("entry_price") is not None and sinal.get("stop_loss") is not None:
                    novo_sinal_id = registrar_novo_sinal_log(
                        acao, sinal.get("entry_price"), sinal.get("stop_loss"),
                        sinal.get("take_profit_1"), sinal.get("take_profit_2"), ativo)
                    sinal_ativo = {
                        "estado": "PENDENTE",
                        "direcao": acao,
                        "entry": sinal.get("entry_price"),
                        "stop": sinal.get("stop_loss"),
                        "tp1": sinal.get("take_profit_1"),
                        "tp2": sinal.get("take_profit_2"),
                        "candles": 0,
                        "tp1_notificado": False,
                        "sinal_id": novo_sinal_id,   # elo com a decisão do trader
                    }

                    # Dimensionamento de posição com base no Plano da Mesa
                    # (Margem, Risco%, Drawdown) e no valor por ponto do
                    # ativo identificado no gráfico.
                    plano = carregar_config().get("plano_trading", {})
                    sizing = calcular_contratos(
                        sinal_ativo["entry"], sinal_ativo["stop"], ativo,
                        plano.get("margem", 0), plano.get("risco_pct", 1.0),
                        plano.get("drawdown_maximo", 0)
                    )

                    rr1 = None
                    if sinal_ativo["tp1"] and sinal_ativo["entry"] != sinal_ativo["stop"]:
                        rr1 = round(abs((sinal_ativo["tp1"] - sinal_ativo["entry"]) /
                                        (sinal_ativo["entry"] - sinal_ativo["stop"])), 2)

                    linha_contratos = ""
                    if sizing["contratos"] > 0:
                        linha_contratos = (
                            f"\n📐 *Contratos (plano da mesa): {sizing['contratos']}* ({ativo})\n"
                            f"Risco: US${sizing['risco_real_usd']} "
                            f"(US${sizing['risco_por_contrato']}/contrato · teto US${sizing['risco_usd']})"
                        )
                    else:
                        linha_contratos = (
                            f"\n⚠️ 0 contratos: risco do trade excede o permitido pelo plano, "
                            f"ou Margem/Risco% não configurados no Plano de Trading."
                        )

                    bloco_confluencias = ""
                    if confluencias:
                        bloco_confluencias = "\n\n🔎 *Confluências:*\n" + "\n".join(
                            f"• {c}" for c in confluencias
                        )

                    mensagem_wpp = (
                        f"📘 *Estudo de Cenário — {ativo}*\n"
                        f"🕐 {time.strftime('%d/%m/%Y %H:%M:%S')}\n"
                        f"Viés: *{'Alta (compradora)' if acao == 'BUY' else 'Baixa (vendedora)'}*\n"
                        f"Confiança: *{confianca}%*  |  Probabilidade: *{probabilidade}%*\n\n"
                        f"Região de interesse: {sinal_ativo['entry']}\n"
                        f"Invalidação: {sinal_ativo['stop']}\n"
                        f"Objetivo 1: {sinal_ativo['tp1']}  |  Objetivo 2: {sinal_ativo['tp2']}"
                        f"{f'  |  R:R {rr1}' if rr1 else ''}"
                        f"{linha_contratos}"
                        f"{bloco_confluencias}\n\n"
                        f"_{sinal.get('market_analysis', '')}_\n\n"
                        f"_Material educacional. A decisão de operar é sua._"
                    )
                    enviar_relatorio_whatsapp(mensagem_wpp, screenshot, self.log)
                    falar(f"Novo cenário de {acao} em {ativo}, probabilidade {probabilidade:.0f} por cento.")
                    self.after(0, self._atualizar_dashboard)

                else:
                    # ------------------------------------------------------------
                    # RELATÓRIO INFORMATIVO — enviado em TODO ciclo sem sinal novo.
                    # Antes, ciclos HOLD (ou com sinal já em acompanhamento) não
                    # disparavam nada, o que dava a impressão de que os relatórios
                    # "pararam" de chegar mesmo com o WhatsApp conectado.
                    # ------------------------------------------------------------
                    bloco_confluencias = ""
                    if confluencias:
                        bloco_confluencias = "\n\n🔎 *Confluências observadas:*\n" + "\n".join(
                            f"• {c}" for c in confluencias
                        )

                    if sinal_ativo["estado"] != "ENCERRADA" and acatado_atual:
                        # Só faz ACOMPANHAMENTO de trade se o trader ACATOU o cenário.
                        cabecalho = (f"⏳ *Acompanhamento — {ativo}*\n"
                                      f"🕐 {time.strftime('%d/%m/%Y %H:%M:%S')}\n"
                                      f"Cenário {sinal_ativo['direcao']} em {sinal_ativo['estado']} "
                                      f"(entrada {sinal_ativo['entry']})")
                    elif sinal_ativo["estado"] != "ENCERRADA":
                        # Há um cenário aberto, mas o trader ainda NÃO acatou: nota
                        # neutra, sem tratar como se fosse a operação dele.
                        cabecalho = (f"👀 *Cenário aguardando sua decisão — {ativo}*\n"
                                      f"🕐 {time.strftime('%d/%m/%Y %H:%M:%S')}\n"
                                      f"Sugestão {sinal_ativo['direcao']} (entrada {sinal_ativo['entry']}). "
                                      f"Acate no app/WhatsApp para receber o acompanhamento.")
                    else:
                        cabecalho = (f"⚪ *Sem cenário acionável — {ativo}*\n"
                                      f"🕐 {time.strftime('%d/%m/%Y %H:%M:%S')}\n"
                                      f"Confluência insuficiente neste momento.")

                    mensagem_info = (
                        f"{cabecalho}\n"
                        f"Preço atual: {preco}  |  Confiança: {confianca}%  |  Probabilidade: {probabilidade}%"
                        f"{bloco_confluencias}\n\n"
                        f"_{sinal.get('market_analysis', '')[:400]}_\n\n"
                        f"_Material educacional. A decisão de operar é sua._"
                    )
                    enviar_relatorio_whatsapp(mensagem_info, screenshot, self.log)

            except Exception as e:
                self.log(f"⚠️ Erro no ciclo de análise: {e}")
                time.sleep(10)

    def ao_fechar(self):
        if self.processo_motor and self.processo_motor.poll() is None:
            self.log("Encerrando motor...")
            self.processo_motor.terminate()
            try:
                self.processo_motor.wait(timeout=3)
            except Exception:
                self.processo_motor.kill()
        self.destroy()


def tela_de_ativacao():
    """Janela de ativação exibida quando não há licença válida.
    Retorna True se a licença foi ativada com sucesso, False caso contrário."""
    import tkinter.messagebox as mb

    janela = ctk.CTk()
    janela.title("SMC Quant Pro — Ativação")
    janela.geometry("480x360")
    janela.resizable(False, False)

    resultado = {"ok": False}

    ctk.CTkLabel(janela, text="🔒 Ativação de Licença",
                 font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(28, 6))
    ctk.CTkLabel(janela, text="Cole a chave de licença que você recebeu ao adquirir o produto.",
                 wraplength=400, text_color="gray").pack(pady=(0, 4))

    motivo = verificar_licenca_valida()[1]
    if motivo == "maquina_diferente":
        ctk.CTkLabel(janela, text="⚠️ Esta licença foi ativada em outro computador.",
                     text_color="#ff6666", wraplength=400).pack(pady=(0, 4))
    elif motivo == "offline_expirado":
        ctk.CTkLabel(janela, text="⚠️ Sua licença precisa ser revalidada. Conecte-se à internet.",
                     text_color="#ffcc66", wraplength=400).pack(pady=(0, 4))
    elif motivo == "revogada":
        ctk.CTkLabel(janela, text="⚠️ Esta licença foi desativada. Contate o suporte.",
                     text_color="#ff6666", wraplength=400).pack(pady=(0, 4))

    entrada = ctk.CTkEntry(janela, width=380, placeholder_text="Ex: TIGER-XXXX-XXXX-XXXX",
                            justify="center")
    entrada.pack(pady=18)

    lbl_status = ctk.CTkLabel(janela, text="", text_color="gray")
    lbl_status.pack()

    def ativar():
        chave = entrada.get().strip()
        if not chave:
            lbl_status.configure(text="Digite a chave de licença.", text_color="#ffcc66")
            return
        btn.configure(state="disabled", text="Ativando...")
        janela.update()
        ok, msg = ativar_licenca_online(chave)
        if ok:
            resultado["ok"] = True
            mb.showinfo("Ativação", "Licença ativada com sucesso! O programa vai abrir.")
            janela.destroy()
        else:
            lbl_status.configure(text=msg, text_color="#ff6666")
            btn.configure(state="normal", text="Ativar")

    btn = ctk.CTkButton(janela, text="Ativar", width=200, command=ativar,
                        fg_color="green", hover_color="#1f8b4c")
    btn.pack(pady=14)

    ctk.CTkLabel(janela, text=f"ID desta máquina: {gerar_id_maquina()[:16]}...",
                 font=ctk.CTkFont(size=10), text_color="#555").pack(pady=(10, 0))

    janela.mainloop()
    return resultado["ok"]


if __name__ == "__main__":
    liberado, motivo = verificar_licenca_valida()
    if not liberado:
        # Precisa ativar (ou revalidar). Mostra a tela de ativação.
        if not tela_de_ativacao():
            sys.exit(0)  # usuário fechou sem ativar
    app = SmcQuantApp()
    app.mainloop()
