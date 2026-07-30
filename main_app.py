import time, json, threading, customtkinter as ctk, tkinter as tk, os, subprocess, sys, webbrowser
import base64
import copy
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

# Som do alerta no desktop. winsound é da biblioteca padrão do Windows — não
# adiciona dependência; em outro sistema o alerta sai apenas visual.
try:
    import winsound
    WINSOUND_DISPONIVEL = True
except ImportError:
    WINSOUND_DISPONIVEL = False

# --------------------------------------------------------------------
# AUTOMAÇÃO OPCIONAL DA TRADOVATE (item #7) — envio de ordem por CDP.
# Importa com guarda: se o arquivo não estiver junto (ou faltar algo), o app
# continua funcionando normalmente; a automação só aparece se estiver ligada.
# --------------------------------------------------------------------
try:
    import tradovate_auto
    TRADOVATE_DISPONIVEL = True
except Exception:
    TRADOVATE_DISPONIVEL = False

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
VERSAO_ATUAL = "1.9.3"

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
URL_VERSAO = "https://raw.githubusercontent.com/JOSEVANSANTANA/SMC-QUANT-PRO/main/versao.json"

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


# --------------------------------------------------------------------
# CACHE DE LEITURA DOS ARQUIVOS JSON (desempenho da interface)
# --------------------------------------------------------------------
# O dashboard se redesenha a cada 5 s e cada redesenho lia os mesmos arquivos
# várias vezes (config, posições, performance, sinais) — era a maior causa da
# interface "travada". Agora o conteúdo fica em memória e só é relido quando o
# arquivo REALMENTE muda no disco (mtime + tamanho). A cópia devolvida é rasa,
# então quem altera a lista não corrompe o cache.
_cache_json = {}

def _ler_json_cache(caminho):
    """Lê um JSON com cache por mtime. Devolve None se não existir/for inválido."""
    try:
        st = os.stat(caminho)
    except OSError:
        _cache_json.pop(caminho, None)
        return None
    assinatura = (st.st_mtime_ns, st.st_size)
    entrada = _cache_json.get(caminho)
    if entrada and entrada[0] == assinatura:
        return entrada[1]
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        return None
    _cache_json[caminho] = (assinatura, dados)
    return dados

def _copia_rasa(dados):
    """Cópia segura para o chamador mexer sem sujar o cache."""
    if isinstance(dados, list):
        return [dict(d) if isinstance(d, dict) else d for d in dados]
    return dados

def carregar_config():
    dados = _ler_json_cache(CONFIG_FILE)
    if not isinstance(dados, dict):
        return {}
    # O config é aninhado (contas -> plano_trading), então precisa de cópia
    # profunda para ninguém alterar o cache por referência.
    return copy.deepcopy(dados)

def salvar_config(dados: dict):
    atual = carregar_config()
    atual.update(dados)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False, indent=2)
    _cache_json.pop(CONFIG_FILE, None)   # força releitura na próxima consulta

# --------------------------------------------------------------------
# MULTI-CONTA — cada conta tem PLANO, CICLO, DIÁRIO e HISTÓRICO próprios
# --------------------------------------------------------------------
# O app nasceu com UMA conta só (um único "plano_trading" no topo do config).
# Agora o trader pode cadastrar quantas contas quiser (mesas diferentes, contas
# de avaliação, conta real...) e alternar entre elas: ao selecionar uma conta,
# TODO o dashboard, o dimensionamento das sugestões e a gestão de risco passam
# a ser daquela conta.
#
# COMPATIBILIDADE: a estrutura antiga é migrada automaticamente para a "Conta 1"
# e os registros antigos (sem conta_id) são atribuídos a ela — nenhum histórico
# se perde ao atualizar.
ID_CONTA_LEGADA = "conta_1"

PLANO_PADRAO = {
    "margem": 0,
    "meta_alvo": 0,
    "drawdown_maximo": 0,
    "risco_pct": 1.0,
    "timeout_acatar_min": 10,
    # Piso de qualidade das sugestões (calibra a agressividade):
    #   rr_minimo            -> R:R mínimo até o 1º alvo (regra da casa: 2.0)
    #   probabilidade_minima -> abaixo disso o cenário vira HOLD
    "rr_minimo": 2.0,
    "probabilidade_minima": 55,
    # Em quantos dias operados a meta deve ser batida. Era fixo em 5; agora você
    # escolhe — 1 para "quero bater hoje", 20 para um mês de mesa, etc. Isso muda
    # o ritmo exigido por dia E entra no contexto que a IA recebe.
    "dias_meta": 5,
    "data_inicio": None,
}

def dias_meta_do_plano(plano=None):
    """Prazo (em dias) da meta na conta selecionada. Mínimo 1."""
    plano = plano if plano is not None else plano_da_conta_ativa()
    try:
        return max(1, int(float(plano.get("dias_meta", 5))))
    except (TypeError, ValueError):
        return 5

def _novo_id_conta(existentes=None):
    """ID único de conta. O timestamp em milissegundos sozinho NÃO basta: duas
    contas criadas no mesmo milissegundo receberiam o mesmo ID e passariam a
    compartilhar posições/sinais. Aqui garantimos unicidade de verdade."""
    existentes = set(existentes or [])
    base = f"conta_{int(time.time() * 1000)}"
    if base not in existentes:
        return base
    n = 2
    while f"{base}_{n}" in existentes:
        n += 1
    return f"{base}_{n}"

def carregar_contas():
    """Lista de contas cadastradas. Migra a estrutura antiga na primeira vez."""
    cfg = carregar_config()
    contas = cfg.get("contas")
    if isinstance(contas, list) and contas:
        return [c for c in contas if isinstance(c, dict) and c.get("id")]
    # ---- MIGRAÇÃO: o plano único vira a "Conta 1", preservando tudo ----
    plano_legado = dict(PLANO_PADRAO)
    plano_legado.update(cfg.get("plano_trading") or {})
    contas = [{"id": ID_CONTA_LEGADA, "nome": "Conta 1", "plano_trading": plano_legado}]
    salvar_config({"contas": contas, "conta_ativa": ID_CONTA_LEGADA})
    return contas

def conta_ativa_id():
    """ID da conta selecionada. Se a salva não existir mais, cai na primeira."""
    cfg = carregar_config()
    contas = carregar_contas()
    ids = [c["id"] for c in contas]
    cid = cfg.get("conta_ativa")
    if cid in ids:
        return cid
    salvar_config({"conta_ativa": ids[0]})
    return ids[0]

def conta_ativa():
    cid = conta_ativa_id()
    return next((c for c in carregar_contas() if c["id"] == cid), None)

def nome_conta_ativa():
    c = conta_ativa() or {}
    return c.get("nome", "Conta 1")

def plano_da_conta_ativa():
    """Plano de trading da conta selecionada (com os padrões preenchidos)."""
    plano = dict(PLANO_PADRAO)
    plano.update((conta_ativa() or {}).get("plano_trading") or {})
    return plano

def salvar_plano_da_conta(plano, conta_id=None):
    conta_id = conta_id or conta_ativa_id()
    contas = carregar_contas()
    for c in contas:
        if c["id"] == conta_id:
            c["plano_trading"] = plano
    salvar_config({"contas": contas})

def criar_conta(nome=""):
    contas = carregar_contas()
    nova = {
        "id": _novo_id_conta([c["id"] for c in contas]),
        "nome": (nome or "").strip() or f"Conta {len(contas) + 1}",
        "plano_trading": dict(PLANO_PADRAO),
    }
    contas.append(nova)
    salvar_config({"contas": contas})
    return nova

def renomear_conta(conta_id, novo_nome):
    novo_nome = (novo_nome or "").strip()
    if not novo_nome:
        return False
    contas = carregar_contas()
    for c in contas:
        if c["id"] == conta_id:
            c["nome"] = novo_nome
            salvar_config({"contas": contas})
            return True
    return False

def excluir_conta(conta_id):
    """Remove a conta do cadastro. NUNCA deixa o app sem nenhuma conta.
    Os registros dela continuam no disco (histórico preservado), apenas deixam
    de aparecer — assim uma exclusão por engano não destrói dado nenhum."""
    contas = carregar_contas()
    if len(contas) <= 1:
        return False
    restantes = [c for c in contas if c["id"] != conta_id]
    if len(restantes) == len(contas):
        return False
    salvar_config({"contas": restantes})
    if conta_ativa_id() == conta_id:
        salvar_config({"conta_ativa": restantes[0]["id"]})
    return True

def definir_conta_ativa(conta_id):
    if any(c["id"] == conta_id for c in carregar_contas()):
        salvar_config({"conta_ativa": conta_id})
        return True
    return False

def _conta_do_registro(reg):
    """Conta dona do registro. Registro antigo (sem o campo) pertence à Conta 1."""
    return reg.get("conta_id") or ID_CONTA_LEGADA

def _e_da_conta_ativa(reg):
    return _conta_do_registro(reg) == conta_ativa_id()

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
    dados = _ler_json_cache(PERFORMANCE_FILE)
    if isinstance(dados, list):
        # Filtra qualquer entrada malformada (ex: de uma versão antiga do
        # arquivo, ou escrita parcial) — nunca confia cegamente em dado
        # persistido em disco.
        return _copia_rasa([op for op in dados
                            if isinstance(op, dict) and "resultado" in op])
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
    # --- Outros mercados CME comuns ---
    "MGC": 10.0,   # Micro Ouro
    "GC": 100.0,   # Ouro
    "MCL": 100.0,  # Micro Petróleo WTI
    "CL": 1000.0,  # Petróleo WTI
    "M6E": 12500.0,  # Micro Euro FX
    "6E": 125000.0,  # Euro FX
    # --- B3 (para quem analisa no Profit/Nelogica ou NinjaTrader) ---
    # Valores em REAIS por ponto; o dashboard mostra na moeda do seu plano.
    "WIN": 0.20,   # Mini Índice Bovespa (R$ 0,20 por ponto)
    "IND": 1.00,   # Índice Bovespa cheio
    "WDO": 10.00,  # Mini Dólar (R$ 10 por ponto)
    "DOL": 50.00,  # Dólar cheio
}
VALOR_POR_PONTO_PADRAO = 5.0  # fallback se o ativo não for reconhecido

# --------------------------------------------------------------------
# PLATAFORMAS SUPORTADAS
# --------------------------------------------------------------------
# A ANÁLISE funciona com QUALQUER plataforma: o robô captura a janela que você
# escolher e lê o gráfico pela imagem — não depende de integração. O que é
# exclusivo da Tradovate é o envio automático de ordem e a leitura de posições
# (feitos por CDP, no Chrome). Saber QUAL plataforma está na tela também melhora
# a leitura: cada uma escreve o símbolo e o preço de um jeito.
PLATAFORMAS = {
    "tradovate":   {"rotulo": "Tradovate (navegador)", "cdp": True,
                    "pistas": ["tradovate"]},
    "tradingview": {"rotulo": "TradingView", "cdp": False,
                    "pistas": ["tradingview", "trading view"]},
    "profit":      {"rotulo": "Profit / Nelogica", "cdp": False,
                    "pistas": ["profit", "nelogica"]},
    "ninjatrader": {"rotulo": "NinjaTrader", "cdp": False,
                    "pistas": ["ninjatrader", "ninja trader"]},
    "mt5":         {"rotulo": "MetaTrader 5", "cdp": False,
                    "pistas": ["metatrader", "mt5"]},
    "outra":       {"rotulo": "Outra plataforma", "cdp": False, "pistas": []},
}

def detectar_plataforma_do_titulo(titulo):
    """Descobre a plataforma pelo título da janela escolhida. É o que permite ao
    robô se adaptar sozinho quando você troca de TradingView para Profit, por
    exemplo. Retorna a chave em PLATAFORMAS ('outra' se não reconhecer)."""
    t = (titulo or "").lower()
    for chave, info in PLATAFORMAS.items():
        for pista in info["pistas"]:
            if pista in t:
                return chave
    return "outra"

def rotulo_plataforma(chave):
    return PLATAFORMAS.get(chave, PLATAFORMAS["outra"])["rotulo"]

def plataforma_tem_cdp(chave):
    """True só para plataformas em que o envio de ordem / leitura de posição
    por CDP faz sentido (hoje, a Tradovate no Chrome)."""
    return PLATAFORMAS.get(chave, PLATAFORMAS["outra"])["cdp"]

# Dicas de leitura por plataforma, injetadas no prompt. Melhora a precisão do
# ticker e do preço — cada plataforma desenha essas informações num lugar.
DICAS_PLATAFORMA = {
    "tradovate": "A plataforma é a TRADOVATE. O ticker aparece na aba do gráfico "
                 "(ex.: MESU6, MNQU6) e o preço atual fica destacado na escala à "
                 "direita e no book/DOM. Decimal com PONTO.",
    "tradingview": "A plataforma é o TRADINGVIEW. O ticker fica no CANTO SUPERIOR "
                   "ESQUERDO do gráfico, junto do timeframe. O último preço aparece "
                   "na etiqueta colorida da escala à direita. Atenção ao separador "
                   "decimal do ativo.",
    "profit": "A plataforma é o PROFIT (Nelogica). Ativos brasileiros como WINFUT/"
              "WDOFUT/PETR4. O ticker fica no topo da janela do gráfico e o preço na "
              "escala à direita. O separador decimal é VÍRGULA e o milhar é PONTO — "
              "converta corretamente (ex.: 137.500 significa cento e trinta e sete "
              "mil e quinhentos pontos).",
    "ninjatrader": "A plataforma é o NINJATRADER. O ticker fica na barra de título "
                   "do gráfico e o preço na escala à direita. Decimal com PONTO.",
    "mt5": "A plataforma é o METATRADER 5. O ticker está na barra de título da "
           "janela do gráfico e o preço na escala à direita.",
    "outra": "Identifique o ticker e o preço atual onde a plataforma os exibir "
             "(normalmente no topo do gráfico e na escala de preço à direita).",
}

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
    # BLINDAGEM CONTRA DADO INVÁLIDO: quando a captura falha, a IA devolve
    # preço 0 (ativo DESCONHECIDO). Fechar um cenário com entry/saída 0 gerava
    # um P&L ABSURDO (ex.: saída 0 -> "lucro" de +112 mil) que poluía o KPI
    # "se acatasse todas". Nesses casos, NÃO registramos o cenário.
    try:
        entry_f, stop_f, saida_f = float(entry), float(stop), float(preco_saida)
    except (TypeError, ValueError):
        return
    if entry_f <= 0 or stop_f <= 0 or saida_f <= 0:
        return
    # Nenhum sinal intradiário de índice move >10% do preço num único cenário;
    # acima disso é leitura corrompida — descarta.
    if abs(saida_f - entry_f) > abs(entry_f) * 0.10:
        return

    r_multiplo = calcular_r_multiplo(direcao, entry, stop, preco_saida)

    plano = plano_da_conta_ativa()
    sizing = calcular_contratos(entry, stop, ativo, plano.get("margem", 0),
                                 plano.get("risco_pct", 1.0), plano.get("drawdown_maximo", 0))
    contratos = max(sizing["contratos"], 1)
    vpp = valor_por_ponto_do_ativo(ativo)
    pontos = (preco_saida - entry) if direcao == "BUY" else (entry - preco_saida)
    pnl_usd = round(pontos * vpp * contratos, 2)

    db = carregar_performance()
    db.append({
        "conta_id": conta_ativa_id(),
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
    _cache_json.pop(PERFORMANCE_FILE, None)

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
    """Momento em que o ciclo de 5 dias foi (re)iniciado NA CONTA SELECIONADA.
    Cada conta tem o seu próprio ciclo — reiniciar uma não mexe nas outras."""
    plano = plano_da_conta_ativa()
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
    """Posições DA CONTA SELECIONADA criadas a partir do início do ciclo dela."""
    return [p for p in carregar_posicoes()
            if _e_da_conta_ativa(p) and _dentro_do_ciclo(p, "data_criacao")]

def pnl_usd_do_registro(op):
    """P&L em US$ de um registro de performance (cenário hipotético do robô).

    Registros gravados antes da v1.2 não possuem o campo 'pnl_usd'. Em vez de
    tratá-los como zero (o que zerava o comparativo), recalculamos a partir de
    entrada, saída, ativo e contratos.
    """
    entry = op.get("entry")
    saida = op.get("preco_saida")
    direcao = op.get("direcao", "BUY")
    # Filtro de sanidade (também vale para registros ANTIGOS já salvos com lixo):
    # preço 0/ausente ou movimento absurdo (>10% do preço) = captura corrompida.
    try:
        entry_f, saida_f = float(entry), float(saida)
    except (TypeError, ValueError):
        return 0.0
    if entry_f <= 0 or saida_f <= 0 or abs(saida_f - entry_f) > abs(entry_f) * 0.10:
        return 0.0
    # Registro válido: se já tem o P&L calculado, usa; senão recalcula.
    if op.get("pnl_usd") is not None:
        return op["pnl_usd"]
    ativo = op.get("ativo", "DESCONHECIDO")
    contratos = op.get("contratos")
    if not contratos:
        plano = plano_da_conta_ativa()
        sizing = calcular_contratos(entry, op.get("stop", entry), ativo,
                                     plano.get("margem", 0), plano.get("risco_pct", 1.0),
                                     plano.get("drawdown_maximo", 0))
        contratos = max(sizing["contratos"], 1)
    pontos = (saida - entry) if direcao == "BUY" else (entry - saida)
    return round(pontos * valor_por_ponto_do_ativo(ativo) * contratos, 2)

def performance_do_ciclo():
    """Resultados hipotéticos do robô no ciclo DA CONTA SELECIONADA (todas as
    sugestões, acatadas ou não) — usado no comparativo. O sizing embutido em
    cada registro é o do plano da conta que estava ativa quando ele foi gerado."""
    return [op for op in carregar_performance()
            if _e_da_conta_ativa(op) and _dentro_do_ciclo(op, "data_hora")]

def carregar_posicoes():
    dados = _ler_json_cache(POSITIONS_FILE)
    if isinstance(dados, list):
        return _copia_rasa([p for p in dados if isinstance(p, dict) and "id" in p])
    return []

def salvar_posicoes(lista):
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(lista[-500:], f, ensure_ascii=False, indent=2)
    _cache_json.pop(POSITIONS_FILE, None)

def _novo_id_posicao(lista=None):
    """ID único de posição. O id identifica a posição nos botões Fechar/Cancelar,
    então uma colisão (duas posições criadas no mesmo milissegundo) faria o app
    agir na posição ERRADA. Aqui a unicidade é garantida."""
    usados = {p.get("id") for p in (lista if lista is not None else carregar_posicoes())}
    novo = int(time.time() * 1000)
    while novo in usados:
        novo += 1
    return novo

def abrir_posicao(origem, direcao, ativo, entry, stop, tp1, tp2, contratos, status_inicial="ABERTA"):
    """
    status_inicial:
      - "PENDENTE": aguardando o preço tocar a região de entrada (sinais acatados).
        Só vira ABERTA (e passa a contar P&L) quando o preço de fato chega lá.
      - "ABERTA": posição já executada (entrada manual, trader já está posicionado).
    """
    lista = carregar_posicoes()
    pos = {
        "id": _novo_id_posicao(lista),
        "conta_id": conta_ativa_id(),   # a posição pertence à conta selecionada
        # "ROBO" (acatou sugestão), "MANUAL" (diário) ou "PLATAFORMA" (detectada
        # automaticamente na corretora)
        "origem": origem,
        "direcao": direcao,
        "ativo": ativo or "DESCONHECIDO",
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "contratos": max(int(contratos or 1), 1),
        "vpp": valor_por_ponto_do_ativo(ativo),
        "status": status_inicial,
        # Como a execução foi apurada: "CONFIRMADA" (a corretora reportou a
        # posição, ou você lançou na mão) ou "ESTIMADA" (deduzida do preço lido).
        "execucao": "CONFIRMADA" if status_inicial == "ABERTA" else None,
        "confirmacoes_entrada": 0,
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

# Margem de confirmação de execução, como fração da distância do risco
# (entrada -> stop). O preço tem de passar ALÉM da entrada por essa margem para
# a execução ser considerada — encostar no nível não é execução.
MARGEM_CONFIRMA_FILL = 0.15
# Nº de leituras consecutivas além da entrada exigidas quando não há plataforma
# confirmando. Duas leituras evitam "preencher" por um único preço mal lido.
CONFIRMACOES_FILL = 2

def atualizar_posicoes_com_preco(preco, ativo=None, exigir_confirmacao_plataforma=False):
    """
    Governa o ciclo de vida das posições do diário, comparando com o preço real:
      PENDENTE -> ABERTA    (execução confirmada)
      PENDENTE -> CANCELADA (o preço rompeu o stop ANTES de tocar a entrada)
      ABERTA   -> FECHADA   (bateu stop ou alvo final)

    SOBRE A EXECUÇÃO (corrige a "operação aberta que nunca executou"):
    o preço aqui vem da LEITURA DA IMAGEM do gráfico, a cada N minutos. Isso NÃO
    prova que a SUA ordem limitada foi preenchida — o preço pode encostar no nível
    e voltar (ou a leitura sair imprecisa). Por isso:
      • se `exigir_confirmacao_plataforma` (sincronização com a corretora ligada e
        funcionando), o preço NÃO abre posição nenhuma: quem confirma execução é a
        plataforma, que é a fonte da verdade;
      • sem plataforma, exige-se que o preço passe ALÉM da entrada por uma margem
        do risco E em leituras CONSECUTIVAS. A posição fica marcada como
        execução ESTIMADA, e o dashboard mostra isso.
    """
    # Preço inválido (captura falhou -> IA devolve 0/None) NÃO pode acionar
    # stop/alvo nem realizar P&L. Antes, um preço 0 fechava posições com perda/
    # ganho fantasma. Espelha o guard da máquina de estados.
    if preco is None or preco <= 0:
        return []
    lista = carregar_posicoes()
    eventos = []
    for pos in lista:
        status = pos.get("status")
        if status not in ("PENDENTE", "ABERTA"):
            continue
        # Posição DETECTADA NA PLATAFORMA é governada pela sincronização com a
        # corretora (P&L e encerramento vêm de lá, que é a fonte da verdade).
        # A máquina de preço não a toca — assim não inventamos saída para uma
        # operação cujo stop/alvo estão na plataforma, não aqui.
        if pos.get("origem") == "PLATAFORMA":
            continue
        # Sem stop registrado não há como avaliar níveis — evita comparar com None.
        if pos.get("stop") in (None, ""):
            continue
        # Não marca P&L de MES com preço de MNQ.
        if ativo and pos.get("ativo") not in (None, "", "DESCONHECIDO"):
            if not pos["ativo"].upper().startswith(ativo.upper()[:3]):
                continue
        # Leitura corrompida: um preço a mais de 10% da entrada da posição não é
        # movimento real de índice — é captura ruim. Não aciona nada neste ciclo
        # (evita stop/alvo e P&L fantasma a partir de um preço absurdo).
        if pos.get("entry") and abs(preco - pos["entry"]) > abs(pos["entry"]) * 0.10:
            continue

        direcao = pos["direcao"]
        bateu_stop = (direcao == "BUY" and preco <= pos["stop"]) or \
                     (direcao == "SELL" and preco >= pos["stop"])

        # ---------- PENDENTE: aguardando execução ----------
        if status == "PENDENTE":
            # O preço ainda serve para MOSTRAR onde o mercado está...
            pos["preco_atual"] = preco
            if bateu_stop:
                # Stop rompido antes da entrada: o setup nunca foi executado.
                pos["status"] = "CANCELADA"
                pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
                pos["pnl_final"] = 0.0
                eventos.append(("CANCELADA", dict(pos)))
                continue

            # ...mas NÃO serve para declarar execução quando a plataforma está
            # disponível: só ela sabe se a SUA ordem foi realmente preenchida.
            if exigir_confirmacao_plataforma:
                continue

            # Sem plataforma: exige passar ALÉM da entrada por uma margem do
            # risco, em leituras CONSECUTIVAS. "Encostou e voltou" não executa.
            risco = abs(pos["entry"] - pos["stop"]) if pos.get("stop") else 0
            margem = risco * MARGEM_CONFIRMA_FILL
            passou = (direcao == "BUY" and preco <= pos["entry"] - margem) or \
                      (direcao == "SELL" and preco >= pos["entry"] + margem)
            if not passou:
                pos["confirmacoes_entrada"] = 0
                continue
            pos["confirmacoes_entrada"] = pos.get("confirmacoes_entrada", 0) + 1
            if pos["confirmacoes_entrada"] < CONFIRMACOES_FILL:
                continue
            pos["status"] = "ABERTA"
            pos["execucao"] = "ESTIMADA"   # não foi confirmada pela corretora
            pos["data_abertura"] = time.strftime('%d/%m/%Y %H:%M')
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
            # Realiza o P&L no NÍVEL DA ORDEM (stop ou alvo), NUNCA no preço lido.
            # Um preço com overshoot (ou leitura tardia) além do stop inflaria a
            # perda para além do risco planejado — foi o que gerou o -US$325 acima
            # do teto. O resultado agora é o valor exato e determinístico do plano.
            preco_saida = pos["stop"] if bateu_stop else pos["tp2"]
            pos["status"] = "FECHADA"
            pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
            pos["preco_atual"] = preco_saida
            pos["pnl_atual"] = calcular_pnl_posicao(pos, preco_saida)
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

# --------------------------------------------------------------------
# SINCRONIZAÇÃO COM A PLATAFORMA — "estou posicionado?"
# --------------------------------------------------------------------
# Recebe o que foi LIDO na corretora e reconcilia com o diário da conta ativa:
#   • posição nova na plataforma  -> entra no diário (origem PLATAFORMA)
#   • posição que sumiu de lá     -> é encerrada aqui, com o ÚLTIMO P&L lido
#   • posição que continua lá     -> atualiza quantidade/preço médio/P&L
#
# ANTI-INVENÇÃO: só entra no diário o que veio COM NÚMERO VÁLIDO da plataforma.
# Linha sem preço médio, com quantidade zero/absurda ou P&L fora de escala é
# ignorada — o robô prefere não registrar nada a registrar um número inventado.
# E se já existe uma posição sua (ROBO/MANUAL) do mesmo ativo e direção aberta,
# não criamos uma segunda: seria a MESMA operação contada em dobro.
MAX_CONTRATOS_PLAUSIVEL = 1000
MAX_PNL_PLAUSIVEL = 1_000_000

def sincronizar_posicoes_plataforma(linhas_lidas, log=None):
    """linhas_lidas: lista de dicts {'ativo','qtd_liquida','preco_medio','pnl'}.
    Devolve um resumo {'criadas','atualizadas','encerradas','ignoradas'}."""
    log = log or (lambda _m: None)
    resumo = {"criadas": 0, "atualizadas": 0, "encerradas": 0, "ignoradas": 0,
              "corrigidas": 0, "confirmadas": 0}
    conta = conta_ativa_id()
    lista = carregar_posicoes()

    # --- 1) Valida e normaliza o que veio da plataforma ---
    # `observados` = ativos que a leitura REALMENTE viu na tela (mesmo zerados).
    # É a diferença entre "vi o MESU6 e você está zerado nele" (informação, que
    # permite corrigir uma execução falsa) e "não vi esse ativo na tela"
    # (ausência de informação, que NÃO autoriza concluir nada).
    validas = {}
    observados = set()
    for ln in (linhas_lidas or []):
        try:
            ativo = str(ln.get("ativo") or "").strip().upper()
            qtd = ln.get("qtd_liquida")
            preco = ln.get("preco_medio")
            pnl = ln.get("pnl")
            qtd = float(qtd) if qtd is not None else None
        except (TypeError, ValueError):
            resumo["ignoradas"] += 1
            continue
        if not ativo or qtd is None:
            continue
        observados.add(ativo)             # vi este ativo na tela (mesmo zerado)
        if qtd == 0:
            continue                      # zerado: sem posição líquida a registrar
        if abs(qtd) > MAX_CONTRATOS_PLAUSIVEL:
            resumo["ignoradas"] += 1
            log(f"⚠️ Ignorei '{ativo}': quantidade implausível ({qtd}).")
            continue
        try:
            preco = float(preco) if preco is not None else None
        except (TypeError, ValueError):
            preco = None
        if preco is not None and preco <= 0:
            preco = None
        try:
            pnl = float(pnl) if pnl is not None else None
        except (TypeError, ValueError):
            pnl = None
        if pnl is not None and abs(pnl) > MAX_PNL_PLAUSIVEL:
            pnl = None
        # Precisa de pelo menos UM número confiável além da quantidade: o preço
        # médio (para calcularmos) ou o P&L (que a plataforma já calculou).
        # Sem nenhum dos dois, não há o que registrar sem inventar.
        if preco is None and pnl is None:
            resumo["ignoradas"] += 1
            log(f"⚠️ Ignorei '{ativo}': a plataforma mostrou a quantidade, mas nem "
                "preço médio nem P&L vieram legíveis (não vou inventar número).")
            continue
        validas[ativo] = {"ativo": ativo, "qtd": qtd, "preco": preco, "pnl": pnl}

    # --- 2) Atualiza/encerra as posições PLATAFORMA já existentes ---
    abertas_plataforma = [p for p in lista
                          if p.get("origem") == "PLATAFORMA"
                          and p.get("conta_id") == conta
                          and p.get("status") == "ABERTA"]
    for pos in abertas_plataforma:
        nome = str(pos.get("ativo", "")).upper()
        atual = validas.get(nome)
        if atual:
            pos["contratos"] = max(int(abs(atual["qtd"])), 1)
            if atual["preco"] is not None:
                pos["entry"] = atual["preco"]
                pos["preco_atual"] = atual["preco"]
            if atual["pnl"] is not None:
                pos["pnl_atual"] = round(atual["pnl"], 2)
            resumo["atualizadas"] += 1
        elif nome not in observados:
            # Não vi esse ativo na tela agora — ausência de leitura NÃO é prova
            # de que você encerrou. Deixa como está.
            continue
        else:
            # Sumiu da plataforma => você encerrou a operação lá. Realizamos com
            # o ÚLTIMO P&L que a própria plataforma reportou (dado real, não
            # estimativa nossa).
            pos["status"] = "FECHADA"
            pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
            pos["pnl_final"] = round(pos.get("pnl_atual") or 0.0, 2)
            resumo["encerradas"] += 1
            log(f"🔻 Posição encerrada na plataforma: {pos.get('direcao')} "
                f"{pos.get('ativo')} — resultado US${pos['pnl_final']:+.2f} "
                "(registrado no diário).")

    # --- 2b) RECONCILIA as posições do ROBÔ com a realidade da corretora ---
    # É aqui que se corrige a "operação aberta que nunca executou": se o diário
    # diz que a sugestão acatada está ABERTA por ESTIMATIVA (deduzida do preço
    # lido), mas a plataforma não mostra posição nenhuma naquele ativo, então a
    # ordem NÃO foi preenchida — volta a PENDENTE e o P&L falso é zerado.
    # E o inverso: se a plataforma mostra posição e o diário ainda diz PENDENTE,
    # a execução é CONFIRMADA com o preço médio REAL do preenchimento.
    for pos in lista:
        if pos.get("origem") != "ROBO" or pos.get("conta_id") != conta:
            continue
        if pos.get("status") not in ("PENDENTE", "ABERTA"):
            continue
        nome = str(pos.get("ativo", "")).upper()
        if nome not in observados:
            continue      # ativo fora da tela: sem informação, não mexe
        atual = validas.get(nome)
        mesma_direcao = bool(atual) and (
            (pos.get("direcao") == "BUY" and atual["qtd"] > 0) or
            (pos.get("direcao") == "SELL" and atual["qtd"] < 0)
        )

        if pos["status"] == "ABERTA" and not mesma_direcao \
                and pos.get("execucao") != "CONFIRMADA":
            # Estava "aberta" só por estimativa e a corretora não confirma.
            pos["status"] = "PENDENTE"
            pos["execucao"] = None
            pos["confirmacoes_entrada"] = 0
            pos["data_abertura"] = None
            pos["pnl_atual"] = 0.0
            resumo["corrigidas"] += 1
            log(f"↩️ Correção: {pos.get('direcao')} {pos.get('ativo')} @ "
                f"{pos.get('entry')} NÃO está executada na plataforma — voltei "
                "para PENDENTE e zerei o resultado falso.")

        elif pos["status"] == "PENDENTE" and mesma_direcao:
            pos["status"] = "ABERTA"
            pos["execucao"] = "CONFIRMADA"
            # Preço médio REAL do preenchimento, quando a plataforma informa.
            # Se ela só mostra quantidade/P&L, mantemos a entrada planejada da
            # sugestão (é um dado nosso, não um número inventado).
            if atual["preco"] is not None:
                pos["entry"] = atual["preco"]
                pos["preco_atual"] = atual["preco"]
            pos["contratos"] = max(int(abs(atual["qtd"])), 1)
            pos["data_abertura"] = time.strftime('%d/%m/%Y %H:%M')
            pos["pnl_atual"] = round(atual["pnl"], 2) if atual["pnl"] is not None else 0.0
            resumo["confirmadas"] += 1
            log(f"✅ Execução CONFIRMADA pela plataforma: {pos.get('direcao')} "
                f"{pos.get('ativo')} @ {pos.get('entry')} "
                f"({pos['contratos']} contrato(s)).")

        elif pos["status"] == "ABERTA" and mesma_direcao:
            # Posição do robô que a corretora confirma: P&L real vem de lá.
            pos["execucao"] = "CONFIRMADA"
            if atual["pnl"] is not None:
                pos["pnl_atual"] = round(atual["pnl"], 2)
            if atual["preco"] is not None:
                pos["preco_atual"] = atual["preco"]

    # --- 3) Cria as que ainda não existem no diário ---
    ja_no_diario = {str(p.get("ativo", "")).upper() for p in lista
                    if p.get("conta_id") == conta and p.get("status") in ("ABERTA", "PENDENTE")}
    for ativo, dados in validas.items():
        if ativo in ja_no_diario:
            continue      # mesma operação já registrada (sua ou do robô): não duplica
        direcao = "BUY" if dados["qtd"] > 0 else "SELL"
        pos = {
            "id": _novo_id_posicao(lista),
            "conta_id": conta,
            "origem": "PLATAFORMA",
            "direcao": direcao,
            "ativo": ativo,
            "entry": dados["preco"],
            "stop": None,        # a plataforma gerencia; não inventamos níveis
            "tp1": None,
            "tp2": None,
            "contratos": max(int(abs(dados["qtd"])), 1),
            "vpp": valor_por_ponto_do_ativo(ativo),
            "status": "ABERTA",
            "execucao": "CONFIRMADA",     # a própria corretora está reportando
            "confirmacoes_entrada": 0,
            "preco_atual": dados["preco"],
            "pnl_atual": round(dados["pnl"], 2) if dados["pnl"] is not None else 0.0,
            "data_criacao": time.strftime('%d/%m/%Y %H:%M'),
            "data_abertura": time.strftime('%d/%m/%Y %H:%M'),
            "data_fechamento": None,
            "pnl_final": None,
        }
        lista.append(pos)
        resumo["criadas"] += 1
        onde = f" @ {dados['preco']}" if dados["preco"] is not None else ""
        log(f"🔎 Detectei que você está posicionado: {direcao} {ativo} "
            f"{pos['contratos']} contrato(s){onde} — incluído no diário "
            f"da conta '{nome_conta_ativa()}'.")

    salvar_posicoes(lista)
    return resumo

def cancelar_pendentes_do_sinal(sinal_id, motivo="cenário invalidado"):
    """Cancela as ordens PENDENTES (não executadas) ligadas a uma sugestão que
    perdeu validade. Só mexe no que AINDA NÃO entrou no mercado — posição já
    executada é gerida por stop/alvo, nunca cancelada por mudança de leitura."""
    if not sinal_id:
        return 0
    lista = carregar_posicoes()
    n = 0
    for pos in lista:
        if (pos.get("sinal_id") == sinal_id and pos.get("origem") == "ROBO"
                and pos.get("status") == "PENDENTE"):
            pos["status"] = "CANCELADA"
            pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
            pos["pnl_final"] = 0.0
            pos["motivo_cancelamento"] = motivo
            n += 1
    if n:
        salvar_posicoes(lista)
    return n

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

    # 1) A DECISÃO (viés/entrada) é 100% técnica (SMC + indicadores no gráfico).
    # O dimensionamento (contratos/risco) é calculado FORA da IA, pelo plano da
    # mesa. Por isso NÃO passamos meta/drawdown aqui: injetar a meta deixava a IA
    # conservadora demais (ela "se segurava" pela meta e só mandava HOLD).

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
    contexto += "\nCALIBRAGEM (use o histórico só para ajustar o CRITÉRIO, não para travar):\n"
    if winrate < 50.0 or perdeu_recente:
        contexto += ("Houve perdas recentes — exija confluência SMC clara (estrutura + liquidez "
                      "+ POI), MAS continue sinalizando sempre que houver um setup válido, "
                      "inclusive de REVERSÃO bem configurada. NÃO trave em HOLD por excesso de "
                      "cautela: HOLD é apenas para quando realmente não existe cenário.\n")
    else:
        contexto += ("Sistema calibrado: sinalize TODO cenário SMC válido — de continuação OU de "
                      "reversão — que tenha confluência real. Evite HOLD quando houver setup legítimo.\n")

    return contexto

# --------------------------------------------------------------------
# REGISTRO DE SINAIS + DECISÃO DO TRADER (acatou ou não a sugestão)
# --------------------------------------------------------------------
def carregar_sinais_log():
    dados = _ler_json_cache(SIGNALS_LOG_FILE)
    if isinstance(dados, list):
        return _copia_rasa([s for s in dados if isinstance(s, dict) and "id" in s])
    return []

def salvar_sinais_log(lista):
    lista = lista[-100:]
    with open(SIGNALS_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)
    _cache_json.pop(SIGNALS_LOG_FILE, None)

def sinais_da_conta_ativa():
    """Sugestões pertencentes à conta selecionada (as antigas, sem conta_id,
    ficam na Conta 1). É o que a lista do dashboard e o ACATAR enxergam."""
    return [s for s in carregar_sinais_log() if _e_da_conta_ativa(s)]

def situacao_do_sinal(sinal, posicoes=None):
    """Em que pé está uma sugestão, para mostrar DENTRO da própria lista:
    aguardando decisão, dispensada, expirada, invalidada, ou — se você acatou —
    se a ordem ainda está pendente, se entrou (com o P&L ao vivo) e quanto deu
    quando encerrou. Devolve (texto, cor)."""
    lista = carregar_posicoes() if posicoes is None else posicoes
    sid = sinal.get("id")
    decisao = sinal.get("decisao")
    pos = next((p for p in lista if p.get("sinal_id") == sid), None)

    if decisao in ("ACATOU_COMPRA", "ACATOU_VENDA") and pos:
        st = pos.get("status")
        if st == "PENDENTE":
            return (f"⏳ ACATADA · aguardando o preço tocar {pos.get('entry')} "
                    f"(atual: {pos.get('preco_atual', '—')})", COR["amarelo"])
        if st == "ABERTA":
            pnl = pos.get("pnl_atual") or 0.0
            selo = ("✔ confirmada na plataforma"
                    if pos.get("execucao") == "CONFIRMADA" else "≈ execução estimada")
            return (f"🔥 EM OPERAÇÃO · {pos.get('contratos')} ctr · "
                    f"resultado agora US${pnl:+.2f} · {selo}",
                    COR["verde"] if pnl >= 0 else COR["vermelho"])
        if st == "FECHADA":
            pnl = pos.get("pnl_final") or 0.0
            fim = pos.get("data_fechamento") or ""
            return (f"{'✅' if pnl >= 0 else '🔴'} ENCERRADA em {fim} · "
                    f"resultado US${pnl:+.2f}",
                    COR["verde"] if pnl >= 0 else COR["vermelho"])
        if st == "CANCELADA":
            motivo = pos.get("motivo_cancelamento") or "stop rompido antes da entrada"
            return (f"🚫 CANCELADA sem executar ({motivo})", COR["dim"])

    if decisao in ("ACATOU_COMPRA", "ACATOU_VENDA"):
        return ("✅ acatada por você", COR["verde"])
    if decisao == "NAO_OPEROU":
        return ("🚪 dispensada por você", COR["dim"])
    if decisao == "EXPIRADO":
        return ("⌛ expirou — não foi acatada no prazo", COR["dim"])
    if decisao == "INVALIDADO":
        return ("🔄 invalidada — o cenário mudou antes de você acatar", COR["dim"])
    return ("⏳ aguardando sua decisão", COR["amarelo"])

def registrar_novo_sinal_log(direcao, entry, stop, tp1, tp2, ativo="DESCONHECIDO"):
    lista = carregar_sinais_log()
    # ID único: o ACATAR do WhatsApp e os botões do dashboard identificam a
    # sugestão por este id — uma colisão decidiria o cenário errado.
    usados = {s.get("id") for s in lista}
    novo_id = int(time.time() * 1000)
    while novo_id in usados:
        novo_id += 1
    lista.append({
        "id": novo_id,
        "conta_id": conta_ativa_id(),   # sugestão dimensionada para esta conta
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
    """Retorna o hwnd de uma janela visível pelo título. Prefere o título
    EXATO (o dropdown guarda o título completo); se não houver, cai para
    correspondência parcial. Retorna None se não encontrar."""
    if not nome_parcial or not PYWIN32_DISPONIVEL:
        return None

    alvo = nome_parcial.strip().lower()
    resultado = {"exato": None, "parcial": None}

    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            titulo = win32gui.GetWindowText(hwnd)
            if titulo:
                t = titulo.strip().lower()
                if t == alvo and resultado["exato"] is None:
                    resultado["exato"] = hwnd
                elif alvo in t and resultado["parcial"] is None:
                    resultado["parcial"] = hwnd
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        pass
    return resultado["exato"] or resultado["parcial"]

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

        # --- Automação Tradovate (opcional, DESLIGADA por padrão) ---
        tv_cfg = carregar_config().get("tradovate", {})
        # auto_ativo: se o robô envia ordem à Tradovate ao ACATAR um sinal.
        self.tv_auto_var = tk.BooleanVar(value=tv_cfg.get("auto_ativo", False))
        # dry_run: modo teste — só PREENCHE o ticket, não clica Enviar. Padrão
        # DESLIGADO: ao ligar a automação, ela envia de verdade. Fica como opção
        # pra quem quiser só pré-visualizar antes de mandar.
        self.tv_dry_var = tk.BooleanVar(value=tv_cfg.get("dry_run", False))
        # sync_posicoes: lê o painel de posições da corretora a cada ciclo para
        # descobrir se você já está posicionado (inclusive fora da sugestão).
        self.tv_sync_var = tk.BooleanVar(value=tv_cfg.get("sync_posicoes", False))

        # --- Notificação no COMPUTADOR (além do WhatsApp) ---
        self.notif_var = tk.BooleanVar(
            value=carregar_config().get("notificar_desktop", True))
        self._notif_abertas = []        # janelas de alerta na tela (p/ empilhar)
        self._sinais_notificados = set()  # evita notificar o mesmo sinal 2x
        self._tv_bot = None  # instância TradovateAuto criada sob demanda
        self._tv_sync_ok_ts = 0          # última leitura de posições bem-sucedida
        self._tv_ultimo_aviso_falha = 0  # p/ não repetir o aviso a cada ciclo
        self._ultimo_ativo_lido = None   # ticker do último gráfico analisado

        # --- Plataforma de análise (qualquer uma; a Tradovate só ganha os
        #     recursos extras de ordem/posição por CDP) ---
        self.plataforma_atual = carregar_config().get("plataforma", "tradovate")

        # Cache do handle da janela da corretora. O título do Chrome muda com a
        # aba ativa; fixar o hwnd evita "não encontrei a janela" quando a aba da
        # corretora não está em foco.
        self._hwnd_cache = None
        self._hwnd_cache_nome = None

        # Poller dos comandos recebidos por WhatsApp (ACATAR/DISPENSAR). Roda
        # em segundo plano por toda a vida do app; se o motor estiver fora do
        # ar, a chamada falha em silêncio e ele tenta de novo depois.
        threading.Thread(target=self._poller_comandos_whatsapp, daemon=True).start()

        config_atual = carregar_config()
        # Plano da CONTA SELECIONADA (migra automaticamente a estrutura antiga).
        self.plano = plano_da_conta_ativa()

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

        ctk.CTkLabel(master, text="Janela do gráfico a monitorar (qualquer plataforma):"
                     ).pack(pady=(6, 0))
        nome_janela_salvo = config_atual.get("nome_janela_corretora", "")
        self.janela_var = tk.StringVar(value=nome_janela_salvo or "(clique em Atualizar lista)")
        self.janela_dropdown = ctk.CTkOptionMenu(master, variable=self.janela_var,
                                                 values=[self.janela_var.get()], width=420,
                                                 command=self._ao_trocar_janela)
        self.janela_dropdown.pack(pady=4)
        ctk.CTkButton(master, text="🔄 Atualizar lista de janelas abertas", fg_color="#555555",
                      command=self._atualizar_lista_janelas).pack(pady=(0, 4))

        # ---------- PLATAFORMA (detectada automaticamente) ----------
        frame_plat = ctk.CTkFrame(master, fg_color="transparent")
        frame_plat.pack(pady=(2, 0))
        ctk.CTkLabel(frame_plat, text="Plataforma:").pack(side="left", padx=(4, 4))
        self.plataforma_var = tk.StringVar(value=rotulo_plataforma(self.plataforma_atual))
        ctk.CTkOptionMenu(frame_plat, variable=self.plataforma_var,
                          values=[info["rotulo"] for info in PLATAFORMAS.values()],
                          width=200, command=self._ao_trocar_plataforma
                          ).pack(side="left", padx=4)
        self.lbl_plataforma_info = ctk.CTkLabel(frame_plat, text="", text_color=COR["dim"],
                                                 font=ctk.CTkFont(size=10))
        self.lbl_plataforma_info.pack(side="left", padx=8)
        ctk.CTkLabel(
            master, justify="left", text_color="gray", font=ctk.CTkFont(size=10),
            text="A ANÁLISE funciona em qualquer plataforma (TradingView, Profit/Nelogica,\n"
                 "NinjaTrader, MT5...): o robô lê o gráfico da janela escolhida acima.\n"
                 "Só o envio automático de ordem e a leitura de posições são exclusivos\n"
                 "da Tradovate no Chrome. Ao trocar a janela, a plataforma é detectada."
        ).pack(pady=(0, 4))
        self._atualizar_info_plataforma()

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

        # ---------- CONTATOS QUE RECEBEM RELATÓRIO (WhatsApp) ----------
        self._montar_painel_inscritos(master)

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

        # ---------- NOTIFICAÇÃO NO COMPUTADOR ----------
        frame_notif = ctk.CTkFrame(master, fg_color="#1b2735",
                                    border_color="#3d7fc0", border_width=1)
        frame_notif.pack(padx=10, pady=(8, 2), fill="x")
        ctk.CTkLabel(frame_notif, text="🔔 Alertas no computador",
                     font=ctk.CTkFont(weight="bold", size=13),
                     text_color="#63b3ed").pack(pady=(8, 0), anchor="w", padx=12)
        ctk.CTkLabel(frame_notif, justify="left", text_color=COR["texto"],
                     font=ctk.CTkFont(size=11),
                     text="Além do WhatsApp, mostra um aviso na tela (com bipe) a cada nova\n"
                          "sugestão e quando uma operação bate stop/alvo. Clique no aviso para\n"
                          "abrir o app. Pode ligar e desligar quando quiser."
                     ).pack(pady=(2, 4), padx=12, anchor="w")
        ctk.CTkCheckBox(frame_notif,
                        text="Mostrar notificações na tela do computador",
                        variable=self.notif_var, command=self._salvar_pref_notificacao,
                        text_color=COR["texto"], fg_color="#1f8b4c",
                        border_color="#63b3ed", hover_color="#25a35a"
                        ).pack(pady=(0, 4), padx=12, anchor="w")
        ctk.CTkButton(frame_notif, text="🔔 Testar notificação", width=170,
                      fg_color="#2a3f5f", hover_color="#3a5580",
                      command=lambda: self._notificar_desktop(
                          "🔔 Teste de notificação",
                          ["Se você está vendo isto, os alertas estão funcionando.",
                           "Novas sugestões vão aparecer assim."])
                      ).pack(pady=(0, 10), padx=12, anchor="w")

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

        # ---------- AUTOMAÇÃO TRADOVATE (opcional) ----------
        self._montar_painel_tradovate(master)

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

    # ==================================================================
    # AUTOMAÇÃO TRADOVATE (item #7) — opcional, desligada por padrão.
    # Envia a estrutura entrada/stop/alvo pelo "Chamado do pedido" via CDP,
    # com o preço EXATO do SMC, em segundo plano (sem roubar o foco).
    # ==================================================================
    def _montar_painel_tradovate(self, master):
        frame = ctk.CTkFrame(master, fg_color="#1b2735", border_color="#3d7fc0", border_width=1)
        frame.pack(padx=10, pady=8, fill="x")
        ctk.CTkLabel(frame, text="🎯 Automação Tradovate (opcional)",
                     font=ctk.CTkFont(weight="bold", size=13),
                     text_color="#63b3ed").pack(pady=(8, 0), anchor="w", padx=12)

        if not TRADOVATE_DISPONIVEL:
            ctk.CTkLabel(frame, text="Módulo tradovate_auto.py não encontrado ao lado do app.",
                         text_color="#e0a458").pack(pady=(2, 10), padx=12, anchor="w")
            return

        ctk.CTkLabel(
            frame, justify="left", text_color=COR["texto"],
            text="Ao ACATAR um sinal, o robô coloca entrada + stop + alvo na Tradovate\n"
                 "(preço exato do SMC), em 2º plano. Requer o Chrome aberto pelo botão\n"
                 "abaixo e o 'Chamado do pedido' visível. Quem não usa Tradovate é só\n"
                 "deixar desligado.  Com a automação LIGADA, as ordens são ENVIADAS de\n"
                 "verdade — marque 'Modo teste' se quiser só pré-visualizar sem enviar."
        ).pack(pady=(2, 6), padx=12, anchor="w")

        # text_color explícito: sem definir modo de aparência, o padrão do
        # CustomTkinter deixa o texto do checkbox escuro (some no fundo escuro).
        ctk.CTkCheckBox(frame, text="Ligar automação (enviar ordem ao Acatar)",
                        variable=self.tv_auto_var, command=self._tv_salvar_prefs,
                        text_color=COR["texto"], fg_color="#1f8b4c",
                        border_color="#63b3ed", hover_color="#25a35a"
                        ).pack(pady=3, padx=12, anchor="w")
        ctk.CTkCheckBox(frame, text="Modo teste (só PREENCHE o ticket, não envia)",
                        variable=self.tv_dry_var, command=self._tv_salvar_prefs,
                        text_color=COR["texto"], fg_color="#1f8b4c",
                        border_color="#63b3ed", hover_color="#25a35a"
                        ).pack(pady=3, padx=12, anchor="w")

        linha = ctk.CTkFrame(frame, fg_color="transparent")
        linha.pack(pady=(4, 4), padx=8, anchor="w")
        ctk.CTkButton(linha, text="🌐 Abrir Chrome (Tradovate)", fg_color="#2b6cb0",
                      text_color="#ffffff", width=190,
                      command=self._tv_abrir_chrome).pack(side="left", padx=4)
        ctk.CTkButton(linha, text="🔌 Testar conexão", fg_color="#555555",
                      text_color="#ffffff", width=140,
                      command=self._tv_testar_conexao).pack(side="left", padx=4)

        # ---------- DETECÇÃO DE POSIÇÃO ABERTA NA PLATAFORMA ----------
        ctk.CTkLabel(frame, text="— Posições abertas na plataforma —",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#63b3ed").pack(pady=(8, 0), padx=12, anchor="w")
        ctk.CTkLabel(
            frame, justify="left", text_color=COR["texto"], font=ctk.CTkFont(size=11),
            text="O robô lê o painel de posições da Tradovate e descobre se você já está\n"
                 "posicionado — inclusive numa operação que VOCÊ abriu por fora (antecipou\n"
                 "ou não seguiu a sugestão). Preço médio, quantidade e P&L vêm da própria\n"
                 "plataforma e entram no diário da CONTA SELECIONADA, preenchendo o dia.\n"
                 "Se a leitura não for confiável, nada é registrado (nunca inventa número)."
        ).pack(pady=(2, 4), padx=12, anchor="w")

        ctk.CTkCheckBox(frame, text="Detectar automaticamente a cada ciclo de análise",
                        variable=self.tv_sync_var, command=self._tv_salvar_prefs,
                        text_color=COR["texto"], fg_color="#1f8b4c",
                        border_color="#63b3ed", hover_color="#25a35a"
                        ).pack(pady=3, padx=12, anchor="w")

        linha2 = ctk.CTkFrame(frame, fg_color="transparent")
        linha2.pack(pady=(2, 10), padx=8, anchor="w")
        ctk.CTkButton(linha2, text="🔎 Detectar posições agora", fg_color="#1f8b4c",
                      hover_color="#25a35a", text_color="#ffffff", width=200,
                      command=self._tv_sincronizar_posicoes).pack(side="left", padx=4)
        ctk.CTkButton(linha2, text="🩺 Diagnosticar leitura", fg_color="#555555",
                      hover_color="#777777", text_color="#ffffff", width=170,
                      command=self._tv_diagnosticar).pack(side="left", padx=4)

    def _tv_salvar_prefs(self):
        salvar_config({"tradovate": {
            "auto_ativo": self.tv_auto_var.get(),
            "dry_run": self.tv_dry_var.get(),
            "sync_posicoes": self.tv_sync_var.get(),
        }})
        if self.tv_auto_var.get():
            modo = "TESTE (não envia)" if self.tv_dry_var.get() else "REAL (envia ordem)"
            self.log(f"🎯 Automação Tradovate LIGADA — modo {modo}.")
        else:
            self.log("🎯 Automação Tradovate desligada.")
        # Ao LIGAR a detecção automática, testa na hora e mostra o resultado.
        # Antes a caixinha ficava marcada sem nenhum retorno, dando a impressão
        # de que a detecção não funcionava.
        if self.tv_sync_var.get():
            self.log("🔎 Detecção automática de posições LIGADA — testando agora...")
            self._tv_ultimo_aviso_falha = 0
            self._tv_sincronizar_posicoes(silencioso=False)
        else:
            self.log("🔎 Detecção automática de posições desligada.")

    def _tv_abrir_chrome(self):
        try:
            # Se já houver um Chrome de depuração aberto, ele será REUTILIZADO e
            # as flags anti-congelamento NÃO se aplicam. Avisa pra fechar antes.
            ja_aberto = False
            try:
                ja_aberto = tradovate_auto.TradovateAuto(log=lambda *_: None).chrome_ligado()
            except Exception:
                pass
            if ja_aberto:
                self.log("⚠️ Já existe um Chrome de automação aberto. Para as flags "
                         "anti-congelamento valerem, FECHE-O primeiro e clique de novo.")
            tradovate_auto.abrir_chrome_debug(log=self.log)
            self.log("🌐 Chrome (Tradovate) aberto em modo SEMPRE-RENDERIZANDO.")
            self.log("👉 Nesta MESMA janela: (1) faça login e deixe o gráfico do seu ativo; "
                     "(2) deixe o 'Chamado do pedido' visível se for usar automação; "
                     "(3) em 'Janela da corretora' (acima), selecione ESTA janela do Chrome.")
            self.log("⚠️ IMPORTANTE: NÃO minimize essa janela. Pode deixá-la ATRÁS de "
                     "outras à vontade — com as flags novas, o robô lê o gráfico mesmo "
                     "coberta, sem trazer ela pra frente (sem roubar seu foco).")
        except Exception as e:
            self.log(f"⚠️ Falha ao abrir o Chrome: {e}")

    def _tv_conectar(self):
        """Devolve uma instância de TradovateAuto REALMENTE conectada.

        Antes bastava `bot.ws` estar preenchido para o app achar que estava tudo
        certo. Só que o socket morre calado (Chrome reaberto, aba trocada,
        WinError 10053) e o objeto continuava com `ws` setado — resultado: todas
        as leituras falhavam para sempre, sem nunca reconectar. Agora a conexão é
        VERIFICADA a cada uso e refeita quando cai.
        """
        if self._tv_bot is None:
            self._tv_bot = tradovate_auto.TradovateAuto(log=self.log)
        bot = self._tv_bot

        # Já conectado? confirma que ainda responde antes de confiar.
        if bot.ws is not None and bot.conexao_viva():
            return bot

        if bot.ws is not None:
            self.log("🔌 A conexão com o Chrome tinha caído — reconectando...")
        if not bot.conectar():
            return None
        # Nova conexão de pé: zera o intervalo de aviso para você ver o próximo
        # resultado na hora.
        self._tv_ultimo_aviso_falha = 0
        return bot

    def _tv_testar_conexao(self):
        def tarefa():
            bot = self._tv_conectar()
            if not bot:
                self.log("❌ Não conectei ao Chrome/Tradovate. Abra pelo botão e faça login.")
                return
            achou = bot.localizar("Comprar") or bot.localizar("Vender")
            if achou:
                self.log("✅ Tradovate pronta: 'Chamado do pedido' encontrado.")
            else:
                self.log("⚠️ Conectei, mas não achei o formulário de ordem. "
                         "Abra o 'Chamado do pedido' na Tradovate.")
        threading.Thread(target=tarefa, daemon=True).start()

    # ------------------------------------------------------------------
    # PLATAFORMA DE ANÁLISE — detecção automática + ajuste manual
    # ------------------------------------------------------------------
    def _atualizar_info_plataforma(self):
        """Mostra ao lado do seletor o que aquela plataforma habilita."""
        if not hasattr(self, "lbl_plataforma_info"):
            return
        if plataforma_tem_cdp(self.plataforma_atual):
            txt, cor = "✔ análise + ordem automática + posições", COR["verde"]
        else:
            txt, cor = "✔ análise por imagem (ordem/posições: manual)", COR["amarelo"]
        self.lbl_plataforma_info.configure(text=txt, text_color=cor)

    def _ao_trocar_janela(self, titulo_escolhido=None):
        """Ao escolher outra janela, tenta descobrir sozinho a plataforma."""
        titulo = titulo_escolhido or self.janela_var.get()
        detectada = detectar_plataforma_do_titulo(titulo)
        if detectada != "outra" and detectada != self.plataforma_atual:
            self.plataforma_atual = detectada
            self.plataforma_var.set(rotulo_plataforma(detectada))
            salvar_config({"plataforma": detectada})
            self.log(f"🖥️ Plataforma detectada pela janela: {rotulo_plataforma(detectada)}.")
        self._atualizar_info_plataforma()

    def _ao_trocar_plataforma(self, rotulo_escolhido):
        chave = next((k for k, v in PLATAFORMAS.items()
                      if v["rotulo"] == rotulo_escolhido), "outra")
        self.plataforma_atual = chave
        salvar_config({"plataforma": chave})
        self._atualizar_info_plataforma()
        if plataforma_tem_cdp(chave):
            self.log(f"🖥️ Plataforma: {rotulo_plataforma(chave)} — análise, envio de "
                      "ordem e leitura de posições disponíveis.")
        else:
            self.log(f"🖥️ Plataforma: {rotulo_plataforma(chave)} — a análise do gráfico "
                      "funciona normalmente. O envio automático de ordem e a leitura de "
                      "posições existem só para a Tradovate; nessa plataforma você "
                      "executa na mão e pode lançar a operação no diário.")

    # ------------------------------------------------------------------
    # NOTIFICAÇÃO NO COMPUTADOR (independente do WhatsApp)
    # ------------------------------------------------------------------
    def _salvar_pref_notificacao(self):
        salvar_config({"notificar_desktop": bool(self.notif_var.get())})
        self.log("🔔 Notificações no computador LIGADAS."
                  if self.notif_var.get() else
                  "🔕 Notificações no computador desligadas.")

    def _notificar_desktop(self, titulo, linhas, cor="#1f8b4c", segundos=15,
                            sinal_id=None, direcao=None):
        """Mostra um aviso no canto da tela (sempre por cima) + um bipe. Não usa
        biblioteca externa, então funciona no .exe sem nada a mais. Respeita o
        interruptor: desligado, não aparece nada.

        Com `sinal_id`, o aviso ganha os botões ACATAR / NÃO OPEREI: você decide
        a sugestão direto da notificação, sem abrir o app."""
        if not (getattr(self, "notif_var", None) and self.notif_var.get()):
            return

        def mostrar():
            try:
                # Limpa da lista as janelas que já fecharam, para empilhar certo.
                self._notif_abertas = [w for w in self._notif_abertas
                                       if w.winfo_exists()]
                win = ctk.CTkToplevel(self)
                win.overrideredirect(True)          # sem barra de título
                win.attributes("-topmost", True)    # sempre visível
                decidivel = sinal_id is not None
                larg = 430 if decidivel else 400
                alt = 46 + 20 * (len(linhas) + 1) + (34 if decidivel else 0)
                tela_l = win.winfo_screenwidth()
                tela_a = win.winfo_screenheight()
                # Empilha de baixo para cima, acima da barra de tarefas.
                desloc = sum(w.winfo_height() + 8 for w in self._notif_abertas)
                x = tela_l - larg - 20
                y = tela_a - alt - 70 - desloc
                win.geometry(f"{larg}x{alt}+{x}+{max(y, 10)}")

                quadro = ctk.CTkFrame(win, fg_color="#12161f",
                                       border_color=cor, border_width=2,
                                       corner_radius=8)
                quadro.pack(fill="both", expand=True)
                ctk.CTkLabel(quadro, text=titulo, text_color=cor, anchor="w",
                             font=ctk.CTkFont(size=13, weight="bold")
                             ).pack(fill="x", padx=12, pady=(8, 2))
                for ln in linhas:
                    ctk.CTkLabel(quadro, text=ln, text_color="#e6e6e6", anchor="w",
                                 justify="left", font=ctk.CTkFont(size=11)
                                 ).pack(fill="x", padx=12)
                barra = ctk.CTkFrame(quadro, fg_color="transparent")
                barra.pack(fill="x", padx=10, pady=(4, 8))

                if decidivel:
                    # DECIDIR DIRETO DO AVISO — sem precisar abrir o app.
                    def decidir(dec):
                        try:
                            # O aviso pode ter ficado na tela depois de o cenário
                            # expirar/ser invalidado. Não deixa um clique atrasado
                            # ressuscitar uma sugestão que já morreu.
                            s = next((x for x in carregar_sinais_log()
                                      if x.get("id") == sinal_id), None)
                            if s is None or s.get("decisao"):
                                estado = (s or {}).get("decisao") or "removida"
                                self.log(f"⌛ Notificação vencida: essa sugestão já está "
                                          f"como [{estado}]. Nada foi alterado.")
                                return
                            self._registrar_decisao(sinal_id, dec)
                            rotulo = ("ACATADA" if dec.startswith("ACATOU")
                                      else "dispensada")
                            self.log(f"🔔 Sugestão {rotulo} pela notificação da tela.")
                        except Exception as e:
                            self.log(f"⚠️ Não consegui registrar a decisão: {e}")
                        finally:
                            if win.winfo_exists():
                                win.destroy()

                    dec_acatar = ("ACATOU_VENDA" if str(direcao).upper() == "SELL"
                                  else "ACATOU_COMPRA")
                    ctk.CTkButton(barra, text="✅ ACATAR", width=110, height=26,
                                  fg_color="#1f8b4c", hover_color="#25a35a",
                                  font=ctk.CTkFont(size=11, weight="bold"),
                                  command=lambda: decidir(dec_acatar)
                                  ).pack(side="left", padx=(0, 6))
                    ctk.CTkButton(barra, text="❌ NÃO OPEREI", width=120, height=26,
                                  fg_color="#8b1f1f", hover_color="#a52a2a",
                                  font=ctk.CTkFont(size=11, weight="bold"),
                                  command=lambda: decidir("NAO_OPEROU")
                                  ).pack(side="left", padx=6)

                ctk.CTkButton(barra, text="fechar", width=60, height=24,
                              fg_color="#333333", hover_color="#555555",
                              font=ctk.CTkFont(size=10),
                              command=win.destroy).pack(side="right")

                # Clicar no corpo do aviso traz o app para frente.
                def focar(_e=None):
                    try:
                        self.deiconify(); self.lift(); self.focus_force()
                    except Exception:
                        pass
                quadro.bind("<Button-1>", focar)

                self._notif_abertas.append(win)
                win.after(int(segundos * 1000),
                          lambda: win.winfo_exists() and win.destroy())

                if WINSOUND_DISPONIVEL:
                    try:
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    except Exception:
                        pass
            except Exception as e:
                # Notificação nunca pode derrubar o app.
                self.log(f"⚠️ Não consegui exibir a notificação: {e}")

        self.after(0, mostrar)

    def _tv_diagnosticar(self):
        """Mostra no log EXATAMENTE o que a leitura de posições está enxergando
        na tela da corretora. Se a detecção não pegar na sua Tradovate, rode isto
        e me mande o resultado — com ele eu ajusto sem chutar."""
        if not TRADOVATE_DISPONIVEL:
            self.log("ℹ️ Módulo tradovate_auto.py não está junto do app.")
            return

        def tarefa():
            bot = self._tv_conectar()
            if not bot:
                self.log("❌ Sem conexão com a Tradovate. Abra o Chrome pelo botão "
                          "e faça login primeiro.")
                return
            try:
                bot.diagnosticar_posicoes()
            except Exception as e:
                self.log(f"⚠️ Falha no diagnóstico: {e}")
                self._tv_bot = None

        threading.Thread(target=tarefa, daemon=True).start()

    def _plataforma_confirma_fills(self):
        """True quando a leitura de posições da corretora está LIGADA e funcionou
        há pouco. Nesse caso ela é a fonte da verdade sobre execução, e o preço
        lido do gráfico não abre posição por conta própria."""
        if not plataforma_tem_cdp(getattr(self, "plataforma_atual", "tradovate")):
            return False
        if not (getattr(self, "tv_sync_var", None) and self.tv_sync_var.get()):
            return False
        ultimo = getattr(self, "_tv_sync_ok_ts", 0)
        # Vale por 10 min: se a leitura parar de funcionar, voltamos ao modo
        # estimado em vez de travar as posições em PENDENTE para sempre.
        return (time.time() - ultimo) < 600

    def _tv_sincronizar_posicoes(self, silencioso=False):
        """Lê as posições abertas na Tradovate e reconcilia com o diário da conta
        selecionada. Roda em thread para não travar a GUI.
        silencioso=True (uso automático a cada ciclo) só fala quando há novidade."""
        if not TRADOVATE_DISPONIVEL:
            if not silencioso:
                self.log("ℹ️ Módulo tradovate_auto.py não está junto do app.")
            return
        if not plataforma_tem_cdp(getattr(self, "plataforma_atual", "tradovate")):
            if not silencioso:
                self.log(f"ℹ️ A leitura automática de posições existe só para a "
                          f"Tradovate. Em {rotulo_plataforma(self.plataforma_atual)}, "
                          "lance a operação em '✍️ Incluir operação no diário' que o "
                          "robô acompanha o resultado normalmente.")
            return

        def tarefa():
            try:
                bot = self._tv_conectar()
                if not bot:
                    # ANTES isso era silencioso no modo automático — você marcava
                    # a caixinha e ficava sem nenhum retorno na tela, parecendo
                    # que "não detecta". Agora avisa (com intervalo, p/ não spamar).
                    self._avisar_falha_sync(
                        "❌ Detecção de posições: sem conexão com a Tradovate. "
                        "Clique em '🌐 Abrir Chrome (Tradovate)' e faça login — a "
                        "leitura só funciona no Chrome aberto por esse botão.",
                        silencioso)
                    return
                dados = bot.ler_posicoes() or {}
                if dados.get("conexao_perdida"):
                    # Socket caiu no meio da leitura: derruba a instância para o
                    # próximo ciclo reconectar do zero (antes ficava travado).
                    self._tv_bot = None
                    self._avisar_falha_sync(
                        "🔌 Detecção de posições: a conexão com o Chrome caiu. "
                        "Vou reconectar sozinho no próximo ciclo. (Isso acontece "
                        "quando o Chrome é fechado/reaberto ou a aba muda.)",
                        silencioso)
                    return
                if not dados.get("ok"):
                    self._avisar_falha_sync(
                        "⚠️ Detecção de posições: não consegui ler com segurança "
                        f"({dados.get('motivo', 'motivo desconhecido')}). Nada foi "
                        "registrado. Use '🩺 Diagnosticar leitura' e me mande o "
                        "resultado.", silencioso)
                    return

                # Leitura válida: a partir daqui a plataforma é a fonte da verdade
                # sobre execução (usado por _plataforma_confirma_fills).
                self._tv_sync_ok_ts = time.time()
                self._tv_ultimo_aviso_falha = 0

                linhas = dados.get("linhas", [])
                # O painel nem sempre mostra o ticker ao lado do campo POSIÇÃO.
                # Quando vier exatamente UMA linha sem ativo, associamos ao ativo
                # que o robô acabou de ler no gráfico — e dizemos isso no log.
                # Com mais de uma, não há como saber qual é qual: descartamos.
                sem_ativo = [ln for ln in linhas if not ln.get("ativo")]
                if sem_ativo:
                    atual = getattr(self, "_ultimo_ativo_lido", None)
                    if len(sem_ativo) == 1 and atual and atual != "DESCONHECIDO":
                        sem_ativo[0]["ativo"] = atual
                        self.log(f"ℹ️ O painel não mostrou o ticker ao lado de POSIÇÃO; "
                                  f"associei ao ativo em análise ({atual}).")
                    else:
                        linhas = [ln for ln in linhas if ln.get("ativo")]
                        self.log("⚠️ Havia leitura(s) de POSIÇÃO sem ticker identificável "
                                  "— descartadas para não atribuir ao ativo errado.")

                resumo = sincronizar_posicoes_plataforma(linhas, log=self.log)
                houve = any(resumo[k] for k in
                            ("criadas", "encerradas", "corrigidas", "confirmadas"))
                if houve or not silencioso:
                    self.log(
                        f"🔎 Posições da plataforma (conta '{nome_conta_ativa()}'): "
                        f"{resumo['criadas']} nova(s), {resumo['atualizadas']} atualizada(s), "
                        f"{resumo['encerradas']} encerrada(s), "
                        f"{resumo['confirmadas']} confirmada(s), "
                        f"{resumo['corrigidas']} corrigida(s)"
                        + (f", {resumo['ignoradas']} ignorada(s) por leitura duvidosa"
                           if resumo["ignoradas"] else "")
                        + "."
                    )
                    if not linhas and not silencioso:
                        self.log("   (nenhuma posição aberta na plataforma neste momento)")
                self.after(0, self._atualizar_dashboard)
            except Exception as e:
                self._avisar_falha_sync(
                    f"⚠️ Detecção de posições falhou: {e}", silencioso)
                self._tv_bot = None   # força reconexão limpa na próxima

        threading.Thread(target=tarefa, daemon=True).start()

    def _avisar_falha_sync(self, mensagem, silencioso):
        """No modo manual avisa sempre. No automático, avisa na primeira falha e
        depois no máximo a cada 5 min — assim você fica sabendo que a detecção
        não está funcionando, sem encher o log a cada ciclo."""
        if not silencioso:
            self.log(mensagem)
            return
        agora = time.time()
        if agora - getattr(self, "_tv_ultimo_aviso_falha", 0) > 300:
            self._tv_ultimo_aviso_falha = agora
            self.log(mensagem)

    def _tv_enviar_bracket(self, direcao, entry, stop, alvo, qtd):
        """Dispara o envio em thread separada (não trava a GUI). Usa dry-run
        conforme o interruptor. direcao: 'BUY'/'SELL'."""
        if not TRADOVATE_DISPONIVEL:
            return
        dry = self.tv_dry_var.get()

        def tarefa():
            try:
                bot = self._tv_conectar()
                if not bot:
                    self.log("❌ Tradovate: sem conexão. Abra o Chrome pelo botão e faça login.")
                    return
                # ws pode ter caído entre um uso e outro — força reconferir
                self.log(f"🎯 Tradovate: enviando bracket {direcao} "
                         f"(entrada {entry} · stop {stop} · alvo {alvo} · {qtd} ctr)"
                         + (" [TESTE]" if dry else ""))
                res = bot.enviar_bracket_ticket(direcao, entry, stop, alvo,
                                                 qtd=qtd, enviar=not dry)
                # Compatível com versões que devolviam só True/False.
                if not isinstance(res, dict):
                    return

                if res.get("exposto"):
                    # ENTRADA no mercado SEM proteção: é o pior estado possível.
                    # Grita no log, no alerta da tela e no WhatsApp.
                    faltando = " e ".join(res.get("faltando", [])) or "a proteção"
                    aviso = (f"🚨 ATENÇÃO — {direcao} {qtd} contrato(s): a ENTRADA foi "
                             f"enviada, mas {faltando} NÃO. Se ela executar, a posição "
                             f"fica SEM PROTEÇÃO. Coloque stop ({stop}) e alvo ({alvo}) "
                             f"na mão na plataforma AGORA.")
                    self.log(aviso)
                    self._notificar_desktop(
                        "🚨 POSIÇÃO SEM PROTEÇÃO NA PLATAFORMA",
                        [f"{direcao} {qtd} ctr — entrada {entry} enviada.",
                         f"NÃO foi enviado: {faltando}.",
                         f"Coloque stop {stop} e alvo {alvo} na mão AGORA."],
                        cor="#c53030", segundos=600)
                    enviar_relatorio_whatsapp(aviso, None, self.log)
                elif not res.get("ok"):
                    self.log("⚠️ Tradovate: o bracket NÃO foi enviado por completo "
                             f"({res.get('erro') or 'motivo não informado'}). "
                             "Nenhuma ordem sua ficou solta — confira a plataforma.")
            except Exception as e:
                self.log(f"⚠️ Tradovate: falha ao enviar ordem: {e}. "
                          "CONFIRA A PLATAFORMA: pode ter ficado ordem parcial.")
                # zera a conexão pra forçar reconexão limpa no próximo envio
                self._tv_bot = None

        threading.Thread(target=tarefa, daemon=True).start()

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

        # ================= BARRA DE CONTAS (multi-conta) =================
        # Tudo abaixo desta barra — KPIs, gráficos, plano, diário e as próprias
        # sugestões do robô — pertence à conta selecionada aqui.
        frame_conta = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=8,
                                    border_width=1, border_color="#2a4a7a")
        frame_conta.pack(padx=8, pady=(8, 2), fill="x")

        ctk.CTkLabel(frame_conta, text="🏦 CONTA", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COR["dim"]).pack(side="left", padx=(12, 6), pady=10)

        self.conta_var = tk.StringVar(value=nome_conta_ativa())
        self.menu_contas = ctk.CTkOptionMenu(
            frame_conta, variable=self.conta_var, values=[c["nome"] for c in carregar_contas()],
            width=230, fg_color=COR["input"], button_color="#2a4a7a",
            font=ctk.CTkFont(size=12, weight="bold"), command=self._trocar_conta)
        self.menu_contas.pack(side="left", padx=4, pady=10)

        ctk.CTkButton(frame_conta, text="➕ Nova", width=70, fg_color=COR["verde_esc"],
                      hover_color=COR["verde"], command=self._nova_conta
                      ).pack(side="left", padx=(10, 3), pady=10)
        ctk.CTkButton(frame_conta, text="✏️ Renomear", width=95, fg_color="#2a3f5f",
                      hover_color="#3a5580", command=self._renomear_conta
                      ).pack(side="left", padx=3, pady=10)
        ctk.CTkButton(frame_conta, text="🗑️ Excluir", width=80, fg_color="#5a1f1f",
                      hover_color="#8b1f1f", command=self._excluir_conta
                      ).pack(side="left", padx=3, pady=10)

        self.lbl_conta_resumo = ctk.CTkLabel(frame_conta, text="", text_color=COR["dim"],
                                              font=ctk.CTkFont(size=10))
        self.lbl_conta_resumo.pack(side="right", padx=12, pady=10)

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

        self.lbl_titulo_plano = ctk.CTkLabel(
            frame_config, text="PLANO DE TRADING DESTA CONTA",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COR["dim"])
        self.lbl_titulo_plano.grid(row=0, column=0, columnspan=4, pady=(10, 8))

        # (rótulo, atributo, chave no plano, linha, coluna, valor padrão)
        campos = [
            ("Margem (US$):", "entry_margem", "margem", 1, 0, 0),
            ("Meta Alvo (US$):", "entry_meta", "meta_alvo", 1, 2, 0),
            ("Drawdown Máx. (US$):", "entry_dd", "drawdown_maximo", 2, 0, 0),
            ("Risco/operação (%):", "entry_risco", "risco_pct", 2, 2, 1.0),
            ("Dias p/ bater a meta:", "entry_dias_meta", "dias_meta", 5, 0, 5),
            ("Prazo p/ acatar (min):", "entry_timeout", "timeout_acatar_min", 3, 0, 10),
            ("R:R mínimo (1:X):", "entry_rr", "rr_minimo", 4, 0, 2.0),
            ("Probabilidade mín. (%):", "entry_prob", "probabilidade_minima", 4, 2, 55),
        ]
        for rotulo, attr, chave, linha, col, padrao in campos:
            ctk.CTkLabel(frame_config, text=rotulo, text_color=COR["dim"],
                         font=ctk.CTkFont(size=11)).grid(row=linha, column=col, sticky="e", padx=(12, 4), pady=4)
            entrada = ctk.CTkEntry(frame_config, width=110, fg_color=COR["input"],
                                    border_color=COR["borda"], text_color=COR["texto"])
            entrada.grid(row=linha, column=col + 1, padx=(0, 12), pady=4)
            entrada.insert(0, str(self.plano.get(chave, padrao)))
            setattr(self, attr, entrada)

        ctk.CTkLabel(frame_config,
                     text="(tempo até a sugestão ser cancelada se você não responder ACATAR)",
                     text_color=COR["dim"], font=ctk.CTkFont(size=9)
                     ).grid(row=3, column=2, columnspan=2, sticky="w", padx=(0, 12), pady=4)

        ctk.CTkLabel(frame_config,
                     text="(em quantos dias operados a Meta Alvo deve ser batida — use 1 se "
                          "quer bater hoje)",
                     text_color=COR["dim"], font=ctk.CTkFont(size=9), justify="left"
                     ).grid(row=5, column=2, columnspan=2, sticky="w", padx=(0, 12), pady=4)

        ctk.CTkLabel(frame_config,
                     text="Piso de qualidade: abaixo disso o cenário vira HOLD. Menor probabilidade "
                          "mínima = mais sugestões (mais agressivo). O R:R 1:2 é a regra da casa.",
                     text_color=COR["dim"], font=ctk.CTkFont(size=9), justify="left"
                     ).grid(row=6, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 2))

        frame_botoes_plano = ctk.CTkFrame(frame_config, fg_color="transparent")
        frame_botoes_plano.grid(row=7, column=0, columnspan=4, pady=(6, 10))
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
            canvas.pack(fill="x", padx=6, pady=(0, 2))
            setattr(self, attr, canvas)
            self._ativar_zoom_pan(canvas)

            # Barra de controles do gráfico: zoom +/-, reset e dica de uso.
            barra = ctk.CTkFrame(col, fg_color="transparent")
            barra.pack(fill="x", padx=6, pady=(0, 6))
            ctk.CTkButton(barra, text="➕", width=30, height=22, fg_color="#2a3f5f",
                          hover_color="#3a5580",
                          command=lambda c=canvas: c._aplicar_zoom(1.3)).pack(side="left", padx=(0, 3))
            ctk.CTkButton(barra, text="➖", width=30, height=22, fg_color="#2a3f5f",
                          hover_color="#3a5580",
                          command=lambda c=canvas: c._aplicar_zoom(1 / 1.3)).pack(side="left", padx=3)
            ctk.CTkButton(barra, text="⟳", width=30, height=22, fg_color="#3a3a3a",
                          hover_color="#555555",
                          command=lambda c=canvas: c._reset_zoom()).pack(side="left", padx=3)
            ctk.CTkLabel(barra, text="roda do mouse = zoom · arraste = mover · passe o mouse p/ ver o valor",
                         text_color=COR["dim"], font=ctk.CTkFont(size=8)
                         ).pack(side="left", padx=8)

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
        todas = posicoes_do_ciclo()
        pendentes = [p for p in todas if p.get("status") == "PENDENTE"]
        abertas = [p for p in todas if p.get("status") == "ABERTA"]

        # DESEMPENHO: destruir e recriar estes widgets a cada 5 s é o que deixava
        # a interface pesada. Só reconstrói quando algo REALMENTE mudou.
        assinatura = tuple(
            (p["id"], p.get("status"), round(p.get("pnl_atual") or 0, 2),
             p.get("preco_atual"), p.get("contratos"))
            for p in pendentes + abertas
        )
        if getattr(self, "_assin_posicoes", None) == assinatura:
            return
        self._assin_posicoes = assinatura

        for widget in self.frame_posicoes.winfo_children():
            widget.destroy()

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
    def _resolver_hwnd_corretora(self, nome_janela):
        """Resolve o hwnd da janela da corretora REUSANDO o handle já achado
        enquanto a janela existir. O título do Chrome muda conforme a aba ativa,
        então buscar por título todo ciclo falha quando a aba da corretora não
        está em foco. Fixando o hwnd, seguimos capturando a MESMA janela mesmo
        com a aba trocada; só rebuscamos se ela fechar ou o alvo mudar."""
        cache = self._hwnd_cache
        if cache and self._hwnd_cache_nome == nome_janela:
            try:
                if PYWIN32_DISPONIVEL and win32gui.IsWindow(cache):
                    return cache
            except Exception:
                pass
        hwnd = encontrar_janela_por_titulo(nome_janela)
        self._hwnd_cache = hwnd
        self._hwnd_cache_nome = nome_janela
        if hwnd:
            self.log(f"🔗 Janela da corretora fixada (handle {hwnd}) — seguirei "
                     "capturando ela mesmo se a aba/título mudar.")
        return hwnd

    # ==================================================================
    # CONTATOS QUE RECEBEM RELATÓRIO (WhatsApp) — gerência pelo app.
    # Segurança: só quem está NESTA lista recebe. O usuário vê e remove
    # qualquer chat indevido, e pode zerar tudo.
    # ==================================================================
    def _montar_painel_inscritos(self, master):
        frame = ctk.CTkFrame(master, fg_color="#1a1f2b", border_color="#2b6cb0", border_width=1)
        frame.pack(padx=10, pady=8, fill="x")
        ctk.CTkLabel(frame, text="📇 Contatos que recebem relatório (WhatsApp)",
                     font=ctk.CTkFont(weight="bold", size=13),
                     text_color="#63b3ed").pack(pady=(8, 0), anchor="w", padx=12)
        ctk.CTkLabel(
            frame, justify="left", text_color=COR["texto"],
            text="SÓ estes chats recebem os relatórios. Um contato entra quando envia START\n"
                 "no WhatsApp — remova aqui qualquer um que não deva receber, ou zere tudo."
        ).pack(pady=(2, 6), padx=12, anchor="w")
        self.frame_lista_inscritos = ctk.CTkFrame(frame, fg_color="transparent")
        self.frame_lista_inscritos.pack(fill="x", padx=8, pady=(0, 4))
        linha = ctk.CTkFrame(frame, fg_color="transparent")
        linha.pack(pady=(0, 10), padx=8, anchor="w")
        ctk.CTkButton(linha, text="🔄 Atualizar", width=110, fg_color="#555555",
                      command=self._wpp_atualizar_inscritos).pack(side="left", padx=4)
        ctk.CTkButton(linha, text="🧹 Limpar todos", width=140, fg_color="#8b1f1f",
                      command=self._wpp_limpar_inscritos).pack(side="left", padx=4)
        self._wpp_atualizar_inscritos()

    def _wpp_atualizar_inscritos(self):
        def tarefa():
            try:
                r = requests.get(f"{BAILEYS_URL}/inscritos", timeout=3)
                subs = r.json().get("subscribers", []) if r.status_code == 200 else None
            except Exception:
                subs = None
            self.after(0, lambda: self._render_inscritos(subs))
        threading.Thread(target=tarefa, daemon=True).start()

    def _render_inscritos(self, subs):
        if not hasattr(self, "frame_lista_inscritos"):
            return
        for w in self.frame_lista_inscritos.winfo_children():
            w.destroy()
        if subs is None:
            ctk.CTkLabel(self.frame_lista_inscritos, text_color="#e0a458",
                         text="Motor offline — ligue o motor para ver/gerenciar os contatos."
                         ).pack(anchor="w", padx=6, pady=2)
            return
        if not subs:
            ctk.CTkLabel(self.frame_lista_inscritos, text_color=COR["dim"],
                         text="Nenhum contato inscrito. Envie START no chat que deve receber."
                         ).pack(anchor="w", padx=6, pady=2)
            return
        for jid in subs:
            row = ctk.CTkFrame(self.frame_lista_inscritos, fg_color="#141b26")
            row.pack(fill="x", pady=2, padx=2)
            ctk.CTkLabel(row, text=jid, anchor="w", text_color=COR["texto"]
                         ).pack(side="left", fill="x", expand=True, padx=8, pady=4)
            ctk.CTkButton(row, text="🗑️ Remover", width=100, fg_color="#8b1f1f",
                          command=lambda j=jid: self._wpp_remover_inscrito(j)
                          ).pack(side="right", padx=6, pady=3)

    def _wpp_remover_inscrito(self, jid):
        def tarefa():
            try:
                requests.post(f"{BAILEYS_URL}/remover-inscrito", json={"jid": jid}, timeout=3)
                self.log(f"🗑️ Contato removido dos relatórios: {jid}")
            except Exception as e:
                self.log(f"⚠️ Falha ao remover contato: {e}")
            self._wpp_atualizar_inscritos()
        threading.Thread(target=tarefa, daemon=True).start()

    def _wpp_limpar_inscritos(self):
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Limpar contatos",
            "Remover TODOS os contatos que recebem relatório?\n\n"
            "Ninguém receberá até você enviar START de novo nos chats desejados."):
            return
        def tarefa():
            try:
                requests.post(f"{BAILEYS_URL}/limpar-inscritos", timeout=3)
                self.log("🧹 Lista de contatos do WhatsApp zerada.")
            except Exception as e:
                self.log(f"⚠️ Falha ao limpar contatos: {e}")
            self._wpp_atualizar_inscritos()
        threading.Thread(target=tarefa, daemon=True).start()

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
        # Detecta a plataforma pela janela escolhida (se der para reconhecer).
        if hasattr(self, "plataforma_var"):
            self._ao_trocar_janela(selecionar)

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
    # MULTI-CONTA — criar, renomear, excluir e trocar a conta ativa
    # ------------------------------------------------------------------
    def _recarregar_menu_contas(self):
        """Repopula o seletor e marca a conta ativa."""
        contas = carregar_contas()
        self.menu_contas.configure(values=[c["nome"] for c in contas])
        self.conta_var.set(nome_conta_ativa())

    def _aplicar_conta_na_tela(self):
        """Recarrega o plano da conta selecionada nos campos e redesenha TUDO
        (KPIs, gráficos, diário, sugestões) com os dados dela."""
        self.plano = plano_da_conta_ativa()
        campos = [
            (self.entry_margem, "margem", 0),
            (self.entry_meta, "meta_alvo", 0),
            (self.entry_dd, "drawdown_maximo", 0),
            (self.entry_risco, "risco_pct", 1.0),
            (self.entry_timeout, "timeout_acatar_min", 10),
            (self.entry_rr, "rr_minimo", 2.0),
            (self.entry_prob, "probabilidade_minima", 55),
            (self.entry_dias_meta, "dias_meta", 5),
        ]
        for widget, chave, padrao in campos:
            widget.delete(0, tk.END)
            widget.insert(0, str(self.plano.get(chave, padrao)))
        # Invalida os caches de render: a conta mudou, as listas TÊM de ser
        # redesenhadas mesmo que a assinatura anterior fosse igual.
        self._assin_posicoes = None
        self._assin_sinais = None
        self._assin_dashboard = None
        self._recarregar_menu_contas()
        self._atualizar_dashboard(forcar=True)

    def _trocar_conta(self, nome_escolhido):
        conta = next((c for c in carregar_contas() if c["nome"] == nome_escolhido), None)
        if not conta:
            return
        definir_conta_ativa(conta["id"])
        self.log(f"🏦 Conta ativa: '{conta['nome']}'. Dashboard, plano e sugestões "
                  "agora são desta conta.")
        self._aplicar_conta_na_tela()

    def _nova_conta(self):
        from tkinter import simpledialog
        nome = simpledialog.askstring("Nova conta",
                                       "Nome da conta (ex.: Apex 50k, Conta Real, Avaliação 2):",
                                       parent=self)
        if not nome or not nome.strip():
            return
        nova = criar_conta(nome)
        definir_conta_ativa(nova["id"])
        self.log(f"🏦 Conta '{nova['nome']}' criada e selecionada. "
                  "Configure o plano dela (margem, meta, drawdown, risco) e salve.")
        self._aplicar_conta_na_tela()

    def _renomear_conta(self):
        from tkinter import simpledialog
        atual = conta_ativa() or {}
        nome = simpledialog.askstring("Renomear conta", "Novo nome:",
                                       initialvalue=atual.get("nome", ""), parent=self)
        if not nome or not nome.strip():
            return
        if renomear_conta(atual.get("id"), nome):
            self.log(f"✏️ Conta renomeada para '{nome.strip()}'.")
            self._aplicar_conta_na_tela()

    def _excluir_conta(self):
        from tkinter import messagebox
        atual = conta_ativa() or {}
        if len(carregar_contas()) <= 1:
            messagebox.showinfo("Excluir conta",
                                 "Esta é a sua única conta — o app precisa de pelo menos uma.")
            return
        if not messagebox.askyesno(
            "Excluir conta",
            f"Remover a conta '{atual.get('nome')}' da lista?\n\n"
            "O histórico dela permanece salvo no disco (nada é apagado); ela apenas "
            "deixa de aparecer. As demais contas não são afetadas."
        ):
            return
        if excluir_conta(atual.get("id")):
            self.log(f"🗑️ Conta '{atual.get('nome')}' removida da lista "
                      "(histórico preservado no disco).")
            self._aplicar_conta_na_tela()

    # ------------------------------------------------------------------
    # PLANO DE TRADING — salvar / reiniciar
    # ------------------------------------------------------------------
    def salvar_plano_trading(self):
        try:
            self.plano["margem"] = float(self.entry_margem.get().replace(",", "."))
            self.plano["meta_alvo"] = float(self.entry_meta.get().replace(",", "."))
            self.plano["drawdown_maximo"] = float(self.entry_dd.get().replace(",", "."))
            self.plano["risco_pct"] = float(self.entry_risco.get().replace(",", "."))
            # Prazo p/ acatar: inteiro em minutos, mínimo 1 (evita 0 = sem prazo).
            _tmo = int(float(self.entry_timeout.get().replace(",", ".")))
            self.plano["timeout_acatar_min"] = max(1, _tmo)
            # Piso de qualidade. R:R travado em no mínimo 1 (abaixo disso não faz
            # sentido); probabilidade entre 0 e 95.
            _rr = float(self.entry_rr.get().replace(",", "."))
            self.plano["rr_minimo"] = max(1.0, _rr)
            _prob = float(self.entry_prob.get().replace(",", "."))
            self.plano["probabilidade_minima"] = max(0.0, min(95.0, _prob))
            # Prazo da meta: pelo menos 1 dia (1 = "quero bater hoje").
            _dm = int(float(self.entry_dias_meta.get().replace(",", ".")))
            self.plano["dias_meta"] = max(1, _dm)
        except ValueError:
            self.log("⚠️ Valores do plano de trading inválidos — use apenas números.")
            return

        if not self.plano.get("data_inicio"):
            self.plano["data_inicio"] = datetime.date.today().isoformat()

        salvar_plano_da_conta(self.plano)
        self.log(f"💾 Plano de trading salvo para a conta '{nome_conta_ativa()}'.")
        self._atualizar_dashboard()

    def reiniciar_plano_trading(self):
        from tkinter import messagebox
        abertas = [p for p in posicoes_do_ciclo() if p.get("status") in ("ABERTA", "PENDENTE")]
        aviso = ""
        if abertas:
            aviso = (f"\n\nATENÇÃO: você tem {len(abertas)} posição(ões) aberta(s)/pendente(s). "
                      "Elas sairão do dashboard, mas continuarão sendo acompanhadas internamente.")

        confirmado = messagebox.askyesno(
            f"Reiniciar contagem de {dias_meta_do_plano(self.plano)} dia(s)",
            f"Isso vai ZERAR os indicadores do dashboard DA CONTA '{nome_conta_ativa()}' "
            "(resultado, gráficos, operações e comparativo) e iniciar um novo ciclo a "
            "partir de agora.\n\nAs SUAS OUTRAS CONTAS não são afetadas.\n"
            "Seu histórico NÃO será apagado — ele fica arquivado nos arquivos de dados."
            + aviso + "\n\nDeseja continuar?"
        )
        if not confirmado:
            self.log("↩️ Reinício de ciclo cancelado.")
            return

        agora = datetime.datetime.now()
        self.plano["data_inicio"] = agora.date().isoformat()
        self.plano["ciclo_inicio"] = agora.isoformat(timespec="seconds")
        salvar_plano_da_conta(self.plano)
        self.log(f"🔄 Novo ciclo de {dias_meta_do_plano(self.plano)} dia(s) iniciado em "
                  f"{agora.strftime('%d/%m/%Y %H:%M:%S')} para a conta "
                  f"'{nome_conta_ativa()}'. "
                  "Dashboard zerado (histórico preservado nos arquivos).")
        self._atualizar_dashboard(forcar=True)

    # ------------------------------------------------------------------
    # DASHBOARD — equity curve, drawdown, plano da meta, sinais
    # ------------------------------------------------------------------
    def _loop_atualizar_dashboard(self):
        try:
            self._atualizar_dashboard()
        except Exception as e:
            self.log(f"⚠️ Erro ao atualizar dashboard (não crítico): {e}")
        # 2 s deixa o painel BEM mais vivo. Só é viável porque o
        # _atualizar_dashboard sai na hora quando nada mudou (ver assinatura):
        # o tique custa 4 os.stat, não um redesenho inteiro.
        self.after(2000, self._loop_atualizar_dashboard)

    def _assinatura_dashboard(self):
        """Impressão digital baratíssima de tudo que alimenta o painel: se ela
        não mudou, não há nada para redesenhar. É o que tira o travamento —
        antes, todo tique de 5 s reconstruía KPIs, gráficos, textos e listas."""
        partes = [conta_ativa_id(), time.strftime('%d/%m/%Y')]
        for caminho in (POSITIONS_FILE, CONFIG_FILE, SIGNALS_LOG_FILE, PERFORMANCE_FILE):
            try:
                st = os.stat(caminho)
                partes.append(f"{st.st_mtime_ns}:{st.st_size}")
            except OSError:
                partes.append("-")
        # Largura do gráfico entra na conta para o painel se redesenhar quando
        # você redimensiona a janela.
        try:
            partes.append(str(self.canvas_equity.winfo_width()))
        except Exception:
            pass
        return "|".join(partes)

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
        # Prazo da meta configurável (era fixo em 5 dias).
        dias_meta = dias_meta_do_plano(self.plano)
        data_inicio_str = self.plano.get("data_inicio")
        dias_passados = 0
        dias_restantes = dias_meta
        if data_inicio_str:
            try:
                data_inicio = datetime.date.fromisoformat(data_inicio_str)
                dias_passados = (datetime.date.today() - data_inicio).days
                dias_restantes = max(dias_meta - dias_passados, 0)
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
            "resultado_hoje": resultado_hoje, "dias_meta": dias_meta,
        }

    def _contexto_do_plano(self):
        """Bloco que entra no prompt contando à IA o PLANO DA MESA: meta, prazo
        escolhido, quanto falta e qual o ritmo exigido por dia. É o que faz a
        recomendação sair alinhada ao seu plano — quem quer bater a meta HOJE
        precisa de um cenário diferente de quem tem 20 dias pela frente.

        Importante: isto NUNCA autoriza forçar trade. O plano ajusta a POSTURA
        (o quanto vale esperar o setup perfeito), jamais a honestidade da leitura.
        """
        try:
            stats = self._computar_stats_plano()
        except Exception:
            return ""
        meta = stats.get("meta") or 0
        if not meta:
            return ("PLANO DA MESA: sem meta configurada — priorize apenas a "
                    "qualidade do setup.\n")

        dias_meta = stats.get("dias_meta", 5)
        restantes = stats.get("dias_restantes", dias_meta)
        falta = stats.get("falta", meta)
        risco_trade = stats.get("risco_usd") or 0
        ritmo = stats.get("meta_diaria")

        if falta <= 0:
            postura = ("A META JÁ FOI ATINGIDA no ciclo. Postura: PRESERVAR. Só "
                       "sinalize setups A+ (confluência máxima); na dúvida, HOLD.")
        elif restantes <= 0:
            postura = ("O PRAZO DA META ESGOTOU e ela não foi batida. Postura: não "
                       "force recuperação. Continue exigindo setup de qualidade — "
                       "operar mal para 'correr atrás' é como se destrói conta.")
        else:
            # Quantos trades no R:R mínimo seriam necessários para fechar a meta.
            alvo_por_trade = risco_trade * 2 if risco_trade else 0
            n_trades = (falta / alvo_por_trade) if alvo_por_trade > 0 else 0
            if restantes == 1:
                postura = ("PRAZO CURTO (último dia). Postura: AGRESSIVA na busca — "
                           "vasculhe TODOS os setups SMC válidos do gráfico, inclusive "
                           "reversões e continuações de menor timeframe, e prefira "
                           "alvos que capturem o movimento CHEIO (liquidez completa). "
                           "Mas NÃO relaxe o R:R nem invente cenário: agressividade "
                           "é achar mais oportunidade real, não aceitar trade ruim.")
            elif n_trades and n_trades <= 2:
                postura = ("O ritmo exigido é confortável (1 a 2 trades no R:R mínimo "
                           "resolvem). Postura: SELETIVA — priorize os setups de maior "
                           "confluência e alvo amplo.")
            else:
                postura = ("O ritmo exigido é puxado. Postura: AGRESSIVA na busca de "
                           "oportunidades (todo setup SMC válido conta) e alvos no "
                           "pool de liquidez cheio, mantendo o R:R mínimo intacto.")

        ritmo_txt = (f"US$ {ritmo:,.2f}/dia" if ritmo is not None else "prazo esgotado")
        return (
            "PLANO DA MESA (use para calibrar a POSTURA, nunca para forçar trade):\n"
            f"• Meta do ciclo: US$ {meta:,.2f} · já feito: US$ {stats['lucro_usd']:,.2f} "
            f"· falta: US$ {falta:,.2f}\n"
            f"• Prazo escolhido: {dias_meta} dia(s) · decorridos: "
            f"{stats['dias_passados']} · restam: {restantes}\n"
            f"• Ritmo necessário: {ritmo_txt} · risco por operação: "
            f"US$ {risco_trade:,.2f}\n"
            f"• {postura}\n"
        )

    def _atualizar_dashboard(self, forcar=False):
        # SAÍDA ANTECIPADA: nada mudou desde o último desenho -> não faz nada.
        # (forcar=True para quando a mudança não está nos arquivos, p.ex. troca
        # de conta ou redesenho pedido pelo usuário.)
        try:
            assin = self._assinatura_dashboard()
            if not forcar and assin == getattr(self, "_assin_dashboard", None):
                return
            self._assin_dashboard = assin
        except Exception:
            pass   # se a assinatura falhar, segue e redesenha normalmente

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

            # Resumo ao lado do seletor: deixa explícito de QUAL conta é o painel.
            if hasattr(self, "lbl_conta_resumo"):
                total_contas = len(carregar_contas())
                self.lbl_conta_resumo.configure(
                    text=f"Exibindo: {nome_conta_ativa()}  ·  {stats['abertas']} posição(ões) aberta(s)"
                         f"  ·  {total_contas} conta(s) cadastrada(s)")
            if hasattr(self, "lbl_titulo_plano"):
                self.lbl_titulo_plano.configure(
                    text=f"PLANO DE TRADING — {nome_conta_ativa().upper()}")

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

        # Trilha do prazo escolhido, com a meta acumulada esperada em cada dia.
        # Com prazos longos, mostra só os primeiros dias para não estourar a linha.
        dias_meta = stats.get("dias_meta", 5)
        trilha = []
        for dia in range(1, min(dias_meta, 10) + 1):
            meta_dia = meta * (dia / dias_meta) if meta else 0
            if stats["dias_passados"] >= dia:
                marca = "✅" if stats["lucro_usd"] >= meta_dia else "❌"
            else:
                marca = "⬜"
            trilha.append(f"D{dia} {marca}")
        if dias_meta > 10:
            trilha.append(f"… (+{dias_meta - 10})")

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
            f"Trilha de {dias_meta} dia(s):  {'   '.join(trilha)}   "
            f"({stats['dias_passados']}/{dias_meta} · restam {stats['dias_restantes']})"
        )
        self.lbl_patrimonio.configure(text=texto, text_color=cor)

    def _ativar_zoom_pan(self, canvas):
        """Torna um gráfico totalmente MANIPULÁVEL:
          • roda do mouse = zoom (amplia/reduz) CENTRADO no cursor;
          • arraste (segurar botão esq. + mover) = deslocar (pan) em X e Y;
          • passar o mouse sobre a linha = tooltip com o valor e o rótulo do ponto;
          • duplo-clique OU botão ⟳ = volta ao enquadramento original.
        O estado (_zoom/_zoomy/_panx/_pany) vive no próprio canvas."""
        canvas._zoom = 1.0     # zoom horizontal (tempo)
        canvas._zoomy = 1.0    # zoom vertical (US$)
        canvas._panx = 0.0
        canvas._pany = 0.0
        canvas._arraste_x = None
        canvas._arraste_y = None

        def redesenhar():
            # Redesenha os dois gráficos (barato e mantém tudo consistente).
            try:
                self._desenhar_equity_curve()
                self._desenhar_grafico_dias()
            except Exception:
                pass

        def aplicar_zoom(fator, cx=None, cy=None):
            # Zoom CENTRADO no cursor: o ponto sob o mouse fica parado enquanto o
            # resto expande/contrai (comportamento de mapa). Faixa 1x a 12x.
            antigo, antigoy = canvas._zoom, canvas._zoomy
            novo = min(max(antigo * fator, 1.0), 12.0)
            novoy = min(max(antigoy * fator, 1.0), 12.0)
            if cx is None:
                cx = canvas.winfo_width() / 2
            if cy is None:
                cy = canvas.winfo_height() / 2
            # Mantém o ponto sob o cursor fixo ao mudar a escala.
            canvas._panx = cx - (cx - canvas._panx) * (novo / antigo)
            canvas._pany = cy - (cy - canvas._pany) * (novoy / antigoy)
            canvas._zoom, canvas._zoomy = novo, novoy
            if novo <= 1.0 and novoy <= 1.0:   # voltou ao mínimo: recentraliza
                canvas._panx = canvas._pany = 0.0
            redesenhar()

        def on_wheel(event):
            fator = 1.18 if getattr(event, "delta", 0) > 0 else (1 / 1.18)
            aplicar_zoom(fator, getattr(event, "x", None), getattr(event, "y", None))
            return "break"

        def on_wheel_linux(delta):
            return lambda e: (setattr(e, "delta", delta), on_wheel(e))[1]

        def on_press(event):
            canvas._arraste_x, canvas._arraste_y = event.x, event.y

        def on_drag(event):
            if canvas._arraste_x is not None:
                canvas._panx += event.x - canvas._arraste_x
                canvas._pany += event.y - canvas._arraste_y
                canvas._arraste_x, canvas._arraste_y = event.x, event.y
                redesenhar()

        def on_release(_event):
            canvas._arraste_x = canvas._arraste_y = None

        def on_reset(_event=None):
            canvas._zoom = canvas._zoomy = 1.0
            canvas._panx = canvas._pany = 0.0
            redesenhar()
            return "break"

        def on_hover(event):
            # Tooltip do ponto mais próximo do cursor (sem redesenhar o gráfico
            # inteiro — só apaga/redesenha a camada "tooltip").
            canvas.delete("tooltip")
            pontos = getattr(canvas, "_pontos_dados", None)
            if not pontos:
                return
            alvo = min(pontos, key=lambda p: abs(p[0] - event.x))
            if abs(alvo[0] - event.x) > 40:   # longe demais de qualquer ponto
                return
            px, py, valor, rotulo = alvo
            canvas.create_oval(px - 5, py - 5, px + 5, py + 5, outline="#ffffff",
                                width=2, tags="tooltip")
            texto = f"{rotulo}: US${valor:+.2f}"
            larg = 8 + len(texto) * 6.5
            tx = min(max(px, larg / 2 + 2), canvas.winfo_width() - larg / 2 - 2)
            ty = max(py - 22, 12)
            canvas.create_rectangle(tx - larg / 2, ty - 9, tx + larg / 2, ty + 9,
                                     fill="#0e1117", outline="#3a3a5a", tags="tooltip")
            canvas.create_text(tx, ty, text=texto, fill="#ffffff",
                                font=("Consolas", 9, "bold"), tags="tooltip")

        def on_leave(_event):
            canvas.delete("tooltip")

        # guarda para os botões ＋ / － / ⟳ e para o wheel
        canvas._aplicar_zoom = aplicar_zoom
        canvas._reset_zoom = on_reset

        canvas.bind("<MouseWheel>", on_wheel)                 # Windows / Mac
        canvas.bind("<Button-4>", on_wheel_linux(120))        # Linux scroll up
        canvas.bind("<Button-5>", on_wheel_linux(-120))       # Linux scroll down
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        canvas.bind("<Double-Button-1>", on_reset)
        canvas.bind("<Motion>", on_hover)
        canvas.bind("<Leave>", on_leave)

    def _desenhar_linha(self, canvas, valores, rotulos=None, tooltip_extra=None):
        """Gráfico de LINHA com timeline no eixo X. `rotulos` é a lista de
        legendas (ex: 'Dia 1', 'Op 3') alinhada com `valores`."""
        canvas.delete("all")
        canvas._pontos_dados = []   # zera o hit-test do tooltip a cada redesenho
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

        # Zoom/pan interativos (roda do mouse amplia CENTRADO no cursor, arraste
        # move em X e Y, duplo-clique reseta). O estado vive no próprio canvas.
        # A transformação é linear (x' = x*zoom + panx) para casar exatamente com
        # o zoom-no-cursor de _ativar_zoom_pan.
        zoom = getattr(canvas, "_zoom", 1.0)
        zoomy = getattr(canvas, "_zoomy", 1.0)
        panx = getattr(canvas, "_panx", 0.0)
        pany = getattr(canvas, "_pany", 0.0)

        def xy(i, v):
            x_base = (i / max(n - 1, 1)) * (largura - 40) + 20
            y_base = base - ((v - minimo) / faixa) * (base - topo)
            return x_base * zoom + panx, y_base * zoomy + pany

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
            rot = rotulos[i] if rotulos and i < len(rotulos) else f"#{i + 1}"
            # Registra o ponto para o tooltip (mesmo levemente fora, p/ hit-test).
            if -40 <= x <= largura + 40:
                canvas._pontos_dados.append((x, y, v, rot))
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
        sinais = list(reversed(sinais_da_conta_ativa()[-10:]))
        posicoes = carregar_posicoes()
        situacoes = {s["id"]: situacao_do_sinal(s, posicoes) for s in sinais}

        # DESEMPENHO: só reconstrói a lista quando algo muda de verdade — agora
        # a situação/P&L também entram na assinatura, para o acompanhamento
        # aparecer atualizado sem redesenhar tudo a cada 5 s.
        assinatura = tuple((s["id"], s.get("decisao"), situacoes[s["id"]][0])
                           for s in sinais)
        if getattr(self, "_assin_sinais", None) == assinatura:
            return
        self._assin_sinais = assinatura

        for widget in self.frame_sinais.winfo_children():
            widget.destroy()

        if not sinais:
            ctk.CTkLabel(self.frame_sinais, text="Nenhum sinal registrado ainda.").pack(pady=6)
            return

        for s in sinais:
            texto_sit, cor_sit = situacoes[s["id"]]
            # Cenário já resolvido fica visualmente apagado; o que ainda pede
            # decisão (ou está em operação) fica destacado.
            resolvido = s.get("decisao") in ("NAO_OPEROU", "EXPIRADO", "INVALIDADO")
            linha = ctk.CTkFrame(self.frame_sinais,
                                  fg_color="#1a1a24" if resolvido else "#20283a",
                                  border_width=1,
                                  border_color="#2a2a3a" if resolvido else cor_sit)
            linha.pack(fill="x", pady=3, padx=2)

            alvos = [a for a in (s.get("tp1"), s.get("tp2")) if a is not None]
            alvos_txt = " / ".join(f"{a}" for a in alvos) if alvos else "—"
            ativo_txt = f" {s.get('ativo', '')}" if s.get("ativo") and s["ativo"] != "DESCONHECIDO" else ""
            rr = None
            try:
                risco = abs(float(s["entry"]) - float(s["stop"]))
                alvo1 = s.get("tp1") or s.get("tp2")
                if risco and alvo1:
                    rr = round(abs(float(alvo1) - float(s["entry"])) / risco, 2)
            except (TypeError, ValueError, KeyError):
                rr = None

            texto = (f"{s['data_hora']} | {s['direcao']}{ativo_txt}  ·  "
                     f"Entrada {s['entry']}  /  Alvo {alvos_txt}  /  Stop {s['stop']}"
                     + (f"  /  R:R {rr}" if rr else ""))
            ctk.CTkLabel(linha, text=texto, anchor="w",
                         text_color=COR["dim"] if resolvido else COR["texto"]
                         ).pack(side="top", fill="x", padx=8, pady=(5, 0))

            # ---- ACOMPANHAMENTO: situação atual e resultado ----
            ctk.CTkLabel(linha, text=texto_sit, anchor="w", text_color=cor_sit,
                         font=ctk.CTkFont(size=12, weight="bold")
                         ).pack(side="top", fill="x", padx=8, pady=(1, 2))

            # Os botões só aparecem enquanto a decisão faz sentido — depois de
            # resolvido, a linha vira só histórico (menos poluição visual).
            if resolvido or s.get("decisao") in ("ACATOU_COMPRA", "ACATOU_VENDA"):
                ctk.CTkLabel(linha, text="", height=2).pack(side="top")
                continue

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
                    plano = plano_da_conta_ativa()
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

                    # AUTOMAÇÃO TRADOVATE (opcional): se ligada, envia a estrutura
                    # entrada/stop/alvo com o preço EXATO do SMC. O alvo é o
                    # primeiro objetivo (tp1) — mais provável de ser atingido;
                    # cai para tp2 se não houver tp1.
                    if getattr(self, "tv_auto_var", None) and self.tv_auto_var.get():
                        alvo = sinal.get("tp1") or sinal.get("tp2")
                        self._tv_enviar_bracket(
                            direcao, sinal["entry"], sinal["stop"], alvo,
                            sizing["contratos"] or 1
                        )
        self._atualizar_dashboard()

    def _janela_acatar_seg(self):
        """Prazo (em segundos) dentro do qual uma sugestão ainda pode ser acatada.
        Lê o campo configurável do Plano de Trading da conta ativa (padrão 10 min)."""
        plano = plano_da_conta_ativa()
        try:
            minutos = int(float(plano.get("timeout_acatar_min", 10)))
        except (TypeError, ValueError):
            minutos = 10
        return max(1, minutos) * 60

    def _ultimo_sinal_pendente(self):
        """O sinal mais recente que o trader ainda NÃO decidiu, E que ainda está
        DENTRO da janela de acatar. Um comando ACATAR/DISPENSAR do WhatsApp só se
        aplica a um cenário FRESCO — nunca a um sinal antigo já esquecido/expirado.
        Isso evita que uma sugestão velha (ou um comando preso na fila) vire uma
        operação sem você mandar acatar AGORA.
        Só considera sugestões DA CONTA SELECIONADA."""
        limite_ms = (time.time() - self._janela_acatar_seg()) * 1000
        pendentes = [s for s in sinais_da_conta_ativa()
                     if not s.get("decisao") and s.get("id", 0) >= limite_ms]
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
                # Blindado: um erro num comando não pode derrubar o poller (senão
                # ACATAR/DISPENSAR parariam de funcionar até reiniciar o app).
                try:
                    tipo = cmd.get("tipo")
                    if tipo not in ("ACATAR", "DISPENSAR"):
                        continue
                    # ANTI-FANTASMA: comando obsoleto (ficou preso na fila do motor
                    # enquanto o app estava fechado/desconectado) NÃO é aplicado.
                    # Um comando legítimo é lido em segundos; qualquer coisa acima
                    # de 2 min é resíduo antigo e não pode virar operação agora.
                    ts_cmd = cmd.get("ts", 0)
                    if ts_cmd and (time.time() * 1000 - ts_cmd) > 120000:
                        idade = int((time.time() * 1000 - ts_cmd) / 1000)
                        self.log(f"⌛ Comando {tipo} do WhatsApp ignorado (obsoleto: "
                                  f"{idade}s na fila — provavelmente de antes de reabrir o app).")
                        continue
                    sinal = self._ultimo_sinal_pendente()
                    if not sinal:
                        self.log("💬 WhatsApp: comando recebido, mas não há cenário "
                                  "pendente para aplicar.")
                        enviar_relatorio_whatsapp(
                            "ℹ️ Não há um cenário recente aguardando decisão. "
                            "Assim que sair uma nova sugestão, responda ACATAR ou NÃO ACATAR.",
                            None, self.log)
                        continue
                    direcao_sinal = str(sinal.get("direcao", "")).upper()
                    if tipo == "ACATAR":
                        decisao = "ACATOU_COMPRA" if direcao_sinal in ("BUY", "COMPRA") else "ACATOU_VENDA"
                        confirma = (f"✅ Cenário {sinal.get('direcao')} {sinal.get('ativo','')} "
                                    f"ACATADO. Registrando no diário e enviando as ordens "
                                    f"(entrada/stop/alvo).")
                    else:
                        decisao = "NAO_OPEROU"
                        confirma = (f"🚪 Cenário {sinal.get('direcao')} {sinal.get('ativo','')} "
                                    f"DISPENSADO. Não farei acompanhamento dele.")
                    sid = sinal["id"]
                    self.log(f"💬 WhatsApp: {tipo} aplicado ao cenário {sinal.get('direcao')} "
                              f"{sinal.get('ativo')} (id {sid}).")
                    # Executa na thread da GUI (mexe no diário/dashboard/ordens).
                    self.after(0, lambda s=sid, d=decisao: self._registrar_decisao(s, d))
                    # Confirma no WhatsApp o que REALMENTE aconteceu.
                    enviar_relatorio_whatsapp(confirma, None, self.log)
                except Exception as e:
                    self.log(f"⚠️ Erro ao aplicar comando do WhatsApp: {e}")

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
        # Prazo para você ACATAR uma sugestão. Se não acatar dentro desse tempo,
        # o cenário é cancelado automaticamente e o robô passa a considerar novos.
        # Configurável no Plano de Trading ("Prazo p/ acatar (min)"). Padrão 10 min.
        # Lido da CONTA SELECIONADA (cada conta tem o seu prazo).
        _plano_cfg = plano_da_conta_ativa()
        try:
            _timeout_min = int(float(_plano_cfg.get("timeout_acatar_min", 10)))
        except (TypeError, ValueError):
            _timeout_min = 10
        TIMEOUT_ACATAR_SEG = max(1, _timeout_min) * 60

        # PISO DE QUALIDADE (corta ruído sem travar a agressividade). Um cenário
        # só vira sugestão se passar destes dois filtros:
        #   • R:R até o 1º alvo >= 2.0 (alvo no mínimo 2x o risco — "a conta fecha")
        #   • probabilidade >= mínimo (cenários fracos viram HOLD)
        # R:R continua RÍGIDO em 1:2 (regra da casa: "senão a conta não fecha").
        # A agressividade vem de ACHAR MAIS SETUPS VÁLIDOS e de EXTRAIR MAIS de
        # cada um — não de aceitar trade ruim. O piso de probabilidade é o que
        # foi afrouxado (60 -> 55) para não barrar setups legítimos.
        # Configuráveis por CONTA no Plano de Trading — assim você calibra o
        # quanto quer de agressividade sem mexer no código.
        try:
            RR_MINIMO = float(_plano_cfg.get("rr_minimo", 2.0))
        except (TypeError, ValueError):
            RR_MINIMO = 2.0
        try:
            PROBABILIDADE_MINIMA = float(_plano_cfg.get("probabilidade_minima", 55))
        except (TypeError, ValueError):
            PROBABILIDADE_MINIMA = 55.0
        # Janela em que o MESMO setup (ativo+direção+entrada quase igual) não é
        # sugerido de novo. Encurtada para 20 min: se o preço volta ao POI e o
        # setup se reapresenta, queremos a oportunidade de novo.
        JANELA_ANTI_REPETICAO_SEG = 20 * 60
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
                    hwnd = self._resolver_hwnd_corretora(nome_janela)
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

                # DETECÇÃO DE POSIÇÃO NA PLATAFORMA: antes de analisar, confere na
                # corretora se você já está posicionado (inclusive numa operação
                # aberta por fora da sugestão) e reflete isso no diário/dashboard.
                if getattr(self, "tv_sync_var", None) and self.tv_sync_var.get():
                    self._tv_sincronizar_posicoes(silencioso=True)

                self.log("🧠 Processando análise com Memória Episódica...")

                memoria_dinamica = compilar_memoria_prompt()
                contexto_meta = self._contexto_do_plano()
                PROMPT_BASE = (
                    "Você é um trader institucional de Smart Money Concepts (SMC/ICT) "
                    "operando índices futuros (ES/MES, NQ/MNQ). Você é criterioso, mas "
                    "PROATIVO: sinaliza todo cenário SMC válido — tanto de CONTINUAÇÃO quanto "
                    "de REVERSÃO — e busca se ANTECIPAR a reversões prováveis. Qualidade "
                    "importa, mas não seja conservador a ponto de deixar passar setups "
                    "legítimos. Se houver OUTROS indicadores visíveis no gráfico (volume, "
                    "perfil de volume/VPOC, RSI, médias móveis, VWAP, etc.), use-os como "
                    "confluência adicional junto do SMC.\n"
                    "\n"
                    "POSTURA — VOCÊ É UMA MESA INSTITUCIONAL, NÃO UM VAREJISTA MEDROSO:\n"
                    "Pense como quem PRECISA preencher ordem grande: onde está a liquidez "
                    "parada (stops do varejo), quem está preso, e para onde o preço TEM de "
                    "ir para essa liquidez ser tomada. Seu trabalho é RASPAR O MÁXIMO que o "
                    "movimento oferece — entrar onde a instituição entra (no desconto/prêmio "
                    "extremo, depois da manipulação) e sair onde a instituição realiza (na "
                    "liquidez oposta). Ser 'moderado' aqui é erro: um setup SMC válido, com "
                    "estrutura, liquidez e POI claros, DEVE virar sinal. Só use HOLD quando "
                    "realmente não houver vantagem — não por medo.\n"
                    "\n"
                    "ARSENAL SMC/ICT COMPLETO (use TUDO que estiver visível, não só o básico):\n"
                    "• Estrutura: BOS, CHoCH, MSS (market structure shift), swings internos "
                    "x externos, dealing range e a fase do Power of 3 (acumulação → "
                    "manipulação → distribuição).\n"
                    "• Order Blocks: bullish/bearish OB, BREAKER block, MITIGATION block, "
                    "REJECTION block, propulsion block. Prefira OB de origem (o que causou "
                    "o deslocamento) e OB não mitigado.\n"
                    "• Ineficiências: FVG, INVERSION FVG (iFVG), BPR (balanced price range), "
                    "liquidity void, gap de abertura.\n"
                    "• Liquidez: BSL/SSL (buy/sell side), topos e fundos IGUAIS, liquidez de "
                    "linha de tendência, INDUCEMENT (a isca antes do POI), PDH/PDL (máx/mín "
                    "do dia anterior), PWH/PWL (semana), abertura diária/semanal, "
                    "TURTLE SOUP e JUDAS SWING (falso rompimento da abertura).\n"
                    "• Precificação: premium/discount, equilíbrio (50%), OTE (61,8–79%), "
                    "níveis de padrão institucional.\n"
                    "• Tempo: killzones (Londres, NY AM, NY PM) e horários de virada. "
                    "Setup dentro de killzone merece MAIS confiança, não menos.\n"
                    "• Correlação: divergência SMT entre índices correlacionados (ES/NQ/YM), "
                    "quando ambos estiverem visíveis.\n"
                    "Cite em confluence_factors os nomes REAIS dos conceitos que você "
                    "de fato identificou no gráfico."
                )
                PROMPT_FINAL = (
                    f"{PROMPT_BASE}\n{memoria_dinamica}\n"
                    f"ÚLTIMO ESTADO DO LEDGER:\n{ledger_text_memory}\n"
                    f"CONTEXTO DA TELA: {DICAS_PLATAFORMA.get(self.plataforma_atual, DICAS_PLATAFORMA['outra'])}\n"
                    f"{contexto_meta}"
                    "Identifique o TICKER do ativo no gráfico (asset_symbol) e leia o PREÇO "
                    "ATUAL com precisão pela última vela e pela escala de preço à direita.\n"
                    "\n"
                    "SIGA ESTE ROTEIRO DE ANÁLISE, NESTA ORDEM:\n"
                    "1) VIÉS (HTF): determine a tendência dominante pela ESTRUTURA visível "
                    "(sequência de BOS/CHoCH, topos/fundos). Continuação a favor da tendência é "
                    "o cenário-base (BUY em estrutura de alta, SELL em estrutura de baixa).\n"
                    "1b) REVERSÃO E ANTECIPAÇÃO (importante): procure ATIVAMENTE reversões e "
                    "antecipe-as. Gatilhos SMC de reversão válidos: CHoCH (troca de caráter) "
                    "contra a tendência logo após varredura de liquidez num EXTREMO do range; "
                    "SFP / swing failure (pavio que varre um topo/fundo e FECHA de volta pra "
                    "dentro); rejeição forte em Order Block/FVG de timeframe maior em PREMIUM "
                    "(para venda) ou DISCOUNT (para compra); esgotamento de momentum / divergência "
                    "em indicador visível. Uma reversão bem configurada (sweep do extremo + CHoCH "
                    "+ POI) é um sinal TÃO válido quanto a continuação — sinalize-a, não espere "
                    "confirmação tardia demais.\n"
                    "2) PREMIUM/DISCOUNT: marque o range relevante (perna atual). Compras SÓ em "
                    "DISCOUNT (abaixo de 50%); vendas SÓ em PREMIUM (acima de 50%). Preço em "
                    "EQUILÍBRIO (perto de 50%) ou no meio do range = HOLD.\n"
                    "3) LIQUIDEZ: exija uma varredura de liquidez (sweep de topo/fundo, ou "
                    "inducement) ANTES da entrada. Nunca entre MIRANDO liquidez que ainda não "
                    "foi tomada — o preço tende a buscá-la primeiro.\n"
                    "4) PONTO DE ENTRADA (POI): a entrada deve estar num Order Block NÃO mitigado "
                    "ou num Fair Value Gap (FVG) coerente com o viés. ENTRY_PRICE é sempre ordem "
                    "PENDENTE nesse POI (não a mercado).\n"
                    "4b) ONDE EXATAMENTE COLOCAR A ENTRADA (crítico — evita 'o preço encostou "
                    "e voltou'): NÃO coloque a entrada na BORDA externa do POI, no ponto que o "
                    "preço só alcança com a ponta do pavio. Use o MIOLO da zona: o equilíbrio "
                    "(50%) do corpo do Order Block, ou a zona OTE (61,8%–79% de retração da "
                    "perna de impulso), ou o meio do FVG. Se o preço já está MUITO perto do POI "
                    "(a menos de ~20% da distância do stop), o setup perdeu a assimetria — "
                    "retorne HOLD em vez de forçar uma entrada colada no preço atual.\n"
                    "4c) ASSERTIVIDADE NOS EXTREMOS: priorize POIs que estejam em EXTREMOS "
                    "REAIS de liquidez — máxima/mínima do dia anterior, extremos da sessão, "
                    "topos/fundos iguais (equal highs/lows), abertura semanal, POIs de "
                    "timeframe maior. É nesses extremos que existe liquidez de verdade para "
                    "o preço reagir. POI no MEIO do range, sem liquidez atrás, é o que produz "
                    "o 'encostou e voltou' — nesse caso, HOLD.\n"
                    "5) STOP (crítico — evita ser varrido por um pavio): o stop_loss vai ALÉM "
                    "do EXTREMO DO PAVIO que varreu a liquidez, mais uma folga de respiro — "
                    "NUNCA rente ao nível, nem no meio do corpo do candle de sweep. Pergunte-se: "
                    "'se o preço der mais uma lambida nesse extremo, meu stop sobrevive?' Se a "
                    "resposta for não, o stop está apertado demais. O stop só é válido se, "
                    "colocado assim (largo o suficiente), o R:R do 1º alvo AINDA fechar 1:2.\n"
                    "5b) ALVOS — RASPAR O MÁXIMO (não seja tímido no alvo): take_profit_1 a "
                    "PELO MENOS 2x a distância do stop (R:R >= 1:2, idealmente 1:3), na "
                    "PRIMEIRA liquidez/estrutura REAL do caminho. take_profit_2 é o ALVO "
                    "INSTITUCIONAL: o pool de liquidez COMPLETO para onde o preço está sendo "
                    "levado (PDH/PDL, topos/fundos iguais, extremo do dealing range, FVG de "
                    "timeframe maior por preencher). NÃO encurte o tp2 por cautela — ele é o "
                    "que o movimento entrega quando o cenário funciona. Se o alvo lógico mais "
                    "próximo não alcançar 1:2 a partir de um stop tecnicamente correto (item "
                    "5), o trade NÃO vale — retorne action=HOLD. NUNCA encurte o alvo nem "
                    "aperte o stop só para 'fechar' o R:R no papel.\n"
                    "\n"
                    "REGRAS DE HONESTIDADE:\n"
                    "- NUNCA invente números, preços, níveis, teses ou confluências. "
                    "entry_price, stop_loss, take_profit_1 e take_profit_2 são níveis REAIS "
                    "lidos do gráfico (topos/fundos, OB, FVG, liquidez visíveis). Se você não "
                    "consegue ler um nível com clareza no gráfico, NÃO o chute — retorne "
                    "action=HOLD. Uma análise honesta com HOLD vale mais que um número inventado.\n"
                    "- Liste em confluence_factors APENAS confluências REAIS e visíveis no "
                    "gráfico (BOS/CHoCH, OB, FVG, sweep, premium/discount, equilíbrio). Não "
                    "invente fatores para justificar um trade.\n"
                    "- Se faltar confluência, se a estrutura estiver ambígua, ou se o preço já "
                    "estiver longe do POI, retorne action=HOLD com probabilidade baixa. Porém "
                    "NÃO use HOLD quando existir um setup real (continuação OU reversão) com "
                    "confluência SMC — nesse caso, sinalize BUY/SELL.\n"
                    "- 'confidence_score' E 'probabilidade' são SEMPRE inteiros na ESCALA 0 a 100 "
                    "(ex.: 72, nunca 0.72). 'probabilidade' é a estimativa CALIBRADA e honesta de "
                    "atingir o objetivo 1 antes de invalidar. Poucas confluências ou contra-tendência "
                    "=> probabilidade baixa. Use o histórico do feedback loop acima para calibrar. "
                    "Cenário abaixo de ~60% de probabilidade deve virar HOLD. NÃO infle.\n"
                    "- Coerência obrigatória: para BUY, stop < entry < tp1 <= tp2; para SELL, "
                    "stop > entry > tp1 >= tp2. Se não conseguir montar um cenário coerente, HOLD.\n"
                    "\n"
                    "FILTRO DE RUÍDO (evite stops bobos):\n"
                    "- 90% das operações DEVEM ser fundamentadas em SMC/ICT (estrutura BOS/CHoCH, "
                    "varredura de liquidez, Order Block/FVG não mitigado, premium/discount), em "
                    "QUALQUER timeframe. Indicadores (RSI, VWAP, médias, volume) são apenas "
                    "confluência SECUNDÁRIA — nunca o motivo principal de um trade.\n"
                    "- NÃO opere dentro de range/consolidação sem direção (chop): mercado lateral, "
                    "preço colado na média/VWAP em equilíbrio, velas pequenas e sobrepostas = HOLD. "
                    "É melhor perder o trade do que tomar stop em ruído.\n"
                    "- Exija SEMPRE o gatilho + o POI JÁ mitigável: só sinalize quando a varredura de "
                    "liquidez JÁ ocorreu e o preço está reagindo no POI. Sem sweep + reação, é HOLD.\n"
                    "- NÃO fique alternando BUY/SELL a cada leitura: se o cenário anterior ainda é "
                    "válido estruturalmente, mantenha o viés; só inverta com CHoCH/sweep NOVO e claro.\n"
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
                # Guardado para a detecção de posições associar a leitura do campo
                # POSIÇÃO quando o painel não mostra o ticker ao lado.
                self._ultimo_ativo_lido = ativo
                ledger_text_memory = sinal.get("ledger_update", ledger_text_memory)

                # NORMALIZA A ESCALA (0-100). A IA às vezes devolve 0.78 (escala
                # 0-1) e às vezes 75 (escala 0-100). Padroniza tudo para 0-100.
                def _pct(v):
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        return 0.0
                    if v <= 1.0:      # veio em 0-1 -> converte para 0-100
                        v *= 100.0
                    return round(max(0.0, min(100.0, v)), 1)
                confianca = _pct(confianca)
                probabilidade = _pct(probabilidade)

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
                # Se a leitura de posições da corretora está funcionando, é ELA
                # que confirma execução — o preço lido não abre posição sozinho.
                eventos_pos = atualizar_posicoes_com_preco(
                    preco, ativo,
                    exigir_confirmacao_plataforma=self._plataforma_confirma_fills())
                for tipo, pos in eventos_pos:
                    if tipo == "EXECUTADA":
                        como = ("confirmada pela plataforma"
                                if pos.get("execucao") == "CONFIRMADA"
                                else "ESTIMADA pelo preço lido (a corretora não está "
                                     "sendo consultada)")
                        self.log(f"✅ ENTRADA EXECUTADA: {pos['direcao']} {pos['ativo']} "
                                  f"@ {pos['entry']} — {como}.")
                        self._notificar_desktop(
                            f"🎯 Entrada executada — {pos['direcao']} {pos['ativo']}",
                            [f"Entrada {pos['entry']}  ·  {pos['contratos']} contrato(s)",
                             f"Stop {pos['stop']}  ·  Alvo {pos.get('tp1')}",
                             f"Execução {como}."],
                            cor="#3d7fc0")
                    elif tipo == "CANCELADA":
                        self.log(f"🚫 ORDEM CANCELADA: {pos['direcao']} {pos['ativo']} @ {pos['entry']} — "
                                  f"o preço rompeu o stop antes de tocar a entrada. Nunca foi executada.")
                        self._notificar_desktop(
                            f"🚫 Ordem cancelada — {pos['direcao']} {pos['ativo']}",
                            [f"O preço rompeu o stop antes de tocar {pos['entry']}.",
                             "A ordem nunca foi executada."],
                            cor="#a0a0a0")
                    else:
                        # STOP ou ALVO: operação real encerrada -> notifica no WhatsApp
                        emoji = "🔴" if tipo == "STOP" else "🟢"
                        msg_pos = (f"{emoji} *Operação encerrada ({tipo})*\n"
                                    f"🕐 {time.strftime('%d/%m/%Y %H:%M:%S')}\n"
                                    f"{pos['direcao']} {pos['ativo']} | Entrada {pos['entry']}\n"
                                    f"Resultado: US${pos['pnl_final']:+.2f} ({pos['contratos']} contrato(s))")
                        self.log(msg_pos.replace("*", ""))
                        enviar_relatorio_whatsapp(msg_pos, None, self.log)
                        self._notificar_desktop(
                            f"{emoji} Operação encerrada ({tipo}) — {pos['ativo']}",
                            [f"{pos['direcao']} · entrada {pos['entry']} · "
                             f"{pos['contratos']} contrato(s)",
                             f"Resultado: US${pos['pnl_final']:+.2f}"],
                            cor="#c53030" if tipo == "STOP" else "#1f8b4c")

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

                # ---------------- TIMEOUT DE ACATAR (10 min) ----------------
                # Se você NÃO acatou a sugestão dentro do prazo, ela é cancelada
                # automaticamente e o robô fica livre para considerar novos
                # cenários — não fica preso numa sugestão velha que você não vai
                # operar. (Uma sugestão ACATADA vira sua operação e não expira.)
                if (sinal_ativo["estado"] != "ENCERRADA" and not acatado_atual
                        and (time.time() - sinal_ativo.get("ts_criacao", 0)) > TIMEOUT_ACATAR_SEG):
                    sid_exp = sinal_ativo.get("sinal_id")
                    atualizar_decisao_sinal(sid_exp, "EXPIRADO")
                    self.sinais_dispensados.discard(sid_exp)
                    self.log(f"⌛ Sugestão não acatada em {TIMEOUT_ACATAR_SEG // 60} min — "
                              "cancelada automaticamente. Considerando novos cenários.")
                    sinal_ativo = {"estado": "ENCERRADA"}
                    self.after(0, self._atualizar_dashboard)

                # ---------------- MÁQUINA DE ESTADOS ----------------
                # Exige preço VÁLIDO (>0). Quando a captura falha, a IA devolve
                # preço 0 — processar isso disparava stop/alvo fantasma (ex.:
                # "TAKE PROFIT em 0") e poluía o diário/KPI.
                if sinal_ativo["estado"] != "ENCERRADA" and preco is not None and preco > 0:
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
                            # Resultado realizado no NÍVEL do stop (não no preço lido,
                            # que pode ter overshoot) — mantém o comparativo honesto.
                            salvar_resultado_performance(direcao, sinal_ativo["entry"], sinal_ativo["stop"],
                                                          sinal_ativo["tp1"], sinal_ativo["stop"], "LOSS", ativo)
                            sinal_ativo = {"estado": "ENCERRADA"}
                            msg = f"🔴 *STOP ATINGIDO (LOSS) — {direcao}*\nOperação invalidada em {preco}."
                            self.log(msg)
                            if acatado_atual:
                                enviar_relatorio_whatsapp(msg, screenshot, self.log)
                                falar("Stop atingido. Dados gravados no banco de aprendizado.")
                            self.after(0, self._atualizar_dashboard)

                        elif bateu_tp2:
                            salvar_resultado_performance(direcao, sinal_ativo["entry"], sinal_ativo["stop"],
                                                          sinal_ativo["tp2"], sinal_ativo["tp2"], "WIN", ativo)
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
                                                          sinal_ativo["tp1"], sinal_ativo["tp1"], "WIN", ativo)
                            msg = f"🟢 *TAKE PROFIT 1 (WIN PARCIAL) — {direcao}*\nParcial realizada em {preco}."
                            self.log(msg)
                            if acatado_atual:
                                enviar_relatorio_whatsapp(msg, screenshot, self.log)
                            self.after(0, self._atualizar_dashboard)

                # ---------------- NOVO SINAL (se estado livre) ----------------
                # PISO DE QUALIDADE: calcula o R:R até o 1º alvo e exige R:R>=2
                # e probabilidade>=mínimo. Setups fracos (alvo curto, baixa
                # convicção) NÃO viram sugestão — cortam o ruído.
                _ep = sinal.get("entry_price") or 0
                _sl = sinal.get("stop_loss") or 0
                _alvo_rr = sinal.get("take_profit_1") or sinal.get("take_profit_2") or 0
                _risco = abs(_ep - _sl)
                rr_sinal = (abs(_alvo_rr - _ep) / _risco) if (_risco and _alvo_rr) else 0
                qualidade_ok = (rr_sinal >= RR_MINIMO and probabilidade >= PROBABILIDADE_MINIMA)

                # ---- INVALIDAÇÃO POR MUDANÇA DE CENÁRIO ----
                # Antes, uma sugestão pendente só saía por cancelamento manual ou
                # pelo timeout — ficava acompanhando um cenário que já morreu.
                # Agora, se a leitura nova traz um setup VÁLIDO na direção
                # CONTRÁRIA, a sugestão pendente é invalidada na hora e a ordem
                # pendente ligada a ela é cancelada, liberando o robô para o
                # cenário novo. Posição JÁ EXECUTADA não é tocada.
                if (sinal_ativo.get("estado") == "PENDENTE"
                        and acao in ("BUY", "SELL")
                        and acao != sinal_ativo.get("direcao")
                        and qualidade_ok and _ep > 0 and _sl > 0):
                    sid_inv = sinal_ativo.get("sinal_id")
                    atualizar_decisao_sinal(sid_inv, "INVALIDADO")
                    self.sinais_dispensados.discard(sid_inv)
                    self.sinais_acatados.discard(sid_inv)
                    n_canc = cancelar_pendentes_do_sinal(
                        sid_inv, f"cenário mudou para {acao}")
                    self.log(
                        f"🔄 CENÁRIO MUDOU: a sugestão {sinal_ativo.get('direcao')} "
                        f"{ativo} @ {sinal_ativo.get('entry')} foi INVALIDADA (surgiu "
                        f"um setup de {acao} com qualidade)."
                        + (f" {n_canc} ordem(ns) pendente(s) cancelada(s)." if n_canc else "")
                    )
                    if sid_inv in getattr(self, "_sinais_notificados", set()):
                        self._sinais_notificados.discard(sid_inv)
                    sinal_ativo = {"estado": "ENCERRADA"}
                    self.after(0, self._atualizar_dashboard)

                # ANTI-REPETIÇÃO: se o MESMO setup (ativo + direção + entrada
                # praticamente igual) já foi sugerido há pouco, não vira sugestão
                # nova. Sem isso, o mesmo POI era reemitido a cada ciclo, enchendo
                # a lista de cenários idênticos que só expiravam.
                repetido = False
                if acao in ("BUY", "SELL") and _ep > 0 and _risco:
                    limite_rep = (time.time() - JANELA_ANTI_REPETICAO_SEG) * 1000
                    for s_ant in sinais_da_conta_ativa():
                        if s_ant.get("id", 0) < limite_rep:
                            continue
                        if (s_ant.get("direcao") == acao
                                and str(s_ant.get("ativo", "")).upper() == str(ativo).upper()
                                and s_ant.get("entry")
                                and abs(s_ant["entry"] - _ep) <= _risco * 0.25):
                            repetido = True
                            break
                if repetido:
                    self.log(f"🔁 {acao} {ativo} @ {_ep} é o MESMO setup já sugerido há pouco "
                              "— não vou repetir a sugestão. Aguardando cenário novo.")

                # Loga a rejeição só quando havia um candidato REAL (BUY/SELL válido)
                # com estado livre — pra você ver o filtro trabalhando.
                if (sinal_ativo["estado"] == "ENCERRADA" and acao in ("BUY", "SELL")
                        and preco and _ep > 0 and _sl > 0 and not qualidade_ok and not repetido):
                    motivo = (f"R:R 1:{rr_sinal:.2f} (mínimo 1:{RR_MINIMO:.0f})"
                              if rr_sinal < RR_MINIMO
                              else f"probabilidade {probabilidade:.0f}% (mínimo {PROBABILIDADE_MINIMA:.0f}%)")
                    self.log(f"🚧 {acao} {ativo} descartado pelo piso de qualidade: {motivo}. "
                              "Aguardando um setup melhor.")

                # Só cria sinal com preços VÁLIDOS (>0), preço de tela lido E que
                # passe no piso de qualidade.
                if sinal_ativo["estado"] == "ENCERRADA" and acao in ("BUY", "SELL") \
                        and preco is not None and preco > 0 \
                        and sinal.get("entry_price") and sinal.get("stop_loss") \
                        and sinal.get("entry_price") > 0 and sinal.get("stop_loss") > 0 \
                        and qualidade_ok and not repetido:
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
                        "ts_criacao": time.time(),   # p/ o timeout de acatar (10 min)
                    }

                    # Dimensionamento de posição com base no Plano da Mesa
                    # (Margem, Risco%, Drawdown) e no valor por ponto do
                    # ativo identificado no gráfico, na CONTA SELECIONADA.
                    plano = plano_da_conta_ativa()
                    sizing = calcular_contratos(
                        sinal_ativo["entry"], sinal_ativo["stop"], ativo,
                        plano.get("margem", 0), plano.get("risco_pct", 1.0),
                        plano.get("drawdown_maximo", 0)
                    )

                    # R:R do relatório é SEMPRE calculado dos preços reais (nunca
                    # vem do texto da IA). Usa o mesmo alvo do piso de qualidade
                    # (tp1, ou tp2 se não houver tp1), então o número exibido nunca
                    # fica abaixo do RR_MINIMO que aprovou o sinal.
                    rr1 = None
                    _alvo_rr_disp = sinal_ativo["tp1"] or sinal_ativo["tp2"]
                    if _alvo_rr_disp and sinal_ativo["entry"] != sinal_ativo["stop"]:
                        rr1 = round(abs((_alvo_rr_disp - sinal_ativo["entry"]) /
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

                    # PLANO DE GESTÃO — como raspar o máximo do movimento sem
                    # devolver o lucro. Parcial no 1º alvo, risco zerado, e o
                    # restante corre até o alvo institucional.
                    n_ctr = sizing["contratos"]
                    if n_ctr >= 2:
                        parcial = max(1, n_ctr // 2)
                        runner = n_ctr - parcial
                        bloco_gestao = (
                            f"\n\n🎯 *Gestão (para extrair o máximo):*\n"
                            f"• No Objetivo 1 ({sinal_ativo['tp1']}): realize {parcial} de "
                            f"{n_ctr} contrato(s) e leve o stop para o preço de entrada "
                            f"({sinal_ativo['entry']}) — a partir daí o trade não perde mais.\n"
                            f"• Deixe {runner} contrato(s) correndo até o Objetivo 2 "
                            f"({sinal_ativo['tp2']}), que é o alvo de liquidez cheio.\n"
                            f"• Só saia antes se a estrutura virar contra (CHoCH oposto)."
                        )
                    else:
                        bloco_gestao = (
                            f"\n\n🎯 *Gestão:* com 1 contrato não dá para fracionar. "
                            f"Leve até o Objetivo 1 ({sinal_ativo['tp1']}) OU, se quiser "
                            f"raspar o movimento cheio, segure até o Objetivo 2 "
                            f"({sinal_ativo['tp2']}) movendo o stop para a entrada assim "
                            f"que o preço passar do Objetivo 1."
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
                        f"{bloco_confluencias}"
                        f"{bloco_gestao}\n\n"
                        f"_{sinal.get('market_analysis', '')}_\n\n"
                        f"❓ *Deseja acatar este cenário?*\n"
                        f"Responda *ACATAR* para eu registrar e plotar as ordens (entrada, "
                        f"stop e alvo) na plataforma, ou *NÃO ACATAR* para dispensar.\n\n"
                        f"_Material educacional. A decisão de operar é sua._"
                    )
                    enviar_relatorio_whatsapp(mensagem_wpp, screenshot, self.log)
                    falar(f"Novo cenário de {acao} em {ativo}, probabilidade {probabilidade:.0f} por cento.")

                    # Alerta na tela do computador (além do WhatsApp).
                    self._sinais_notificados.add(novo_sinal_id)
                    self._notificar_desktop(
                        f"📘 Nova sugestão — {acao} {ativo}",
                        [f"Entrada {sinal_ativo['entry']}  ·  Stop {sinal_ativo['stop']}",
                         f"Alvo {sinal_ativo['tp1']}" + (f"  ·  R:R {rr1}" if rr1 else ""),
                         f"Probabilidade {probabilidade:.0f}%  ·  {sizing['contratos']} ctr"
                         f"  ·  conta {nome_conta_ativa()}",
                         f"Decida aqui ou no app (prazo {TIMEOUT_ACATAR_SEG // 60} min)."],
                        cor="#1f8b4c" if acao == "BUY" else "#c53030",
                        # O aviso fica de pé durante todo o prazo de acatar,
                        # com os botões de decisão.
                        segundos=TIMEOUT_ACATAR_SEG,
                        sinal_id=novo_sinal_id, direcao=acao)
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
