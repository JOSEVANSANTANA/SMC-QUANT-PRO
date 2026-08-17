import time, json, threading, customtkinter as ctk, tkinter as tk, os, subprocess, sys, webbrowser
import base64
import concurrent.futures
import copy
import datetime
import ctypes
import re
import requests
from io import BytesIO
from PIL import ImageGrab, Image
import pyttsx3
from google import genai
from google.genai import types

# --------------------------------------------------------------------
# CAMADA DE PLATAFORMA (Windows / macOS)
# --------------------------------------------------------------------
# Até a v2.13 este arquivo chamava win32gui/win32crypt/winsound DIRETO no meio
# da lógica de trading, o que prendia o programa ao Windows. Agora existe UMA
# fronteira: plataforma.py sabe se "capturar a janela do gráfico" significa
# PrintWindow (Windows) ou screencapture -l (macOS). Nada da lógica de SMC,
# do motor, do plano ou da TIGER muda entre os dois sistemas.
import plataforma

# ARMADILHA DO macOS: aplicativo aberto pelo Finder NÃO herda o PATH do shell,
# então o Node instalado pelo Homebrew (/opt/homebrew/bin) some. No terminal
# funciona, no ícone não. Completar o PATH aqui, no arranque, evita isso.
plataforma.garantir_path_do_sistema()

SISTEMA = plataforma.SISTEMA
E_MACOS = plataforma.E_MACOS
E_WINDOWS = plataforma.E_WINDOWS

# Mantido com o nome antigo porque o resto do arquivo já o consulta: agora
# significa "sei mexer nas janelas deste sistema", seja ele qual for.
PYWIN32_DISPONIVEL = (plataforma.PYWIN32_DISPONIVEL or plataforma.QUARTZ_DISPONIVEL)
WINSOUND_DISPONIVEL = True      # o bipe existe nos dois; plataforma.bipe() decide como

# COMANDO POR VOZ (opcional). Instalação recomendada:
#     pip install SpeechRecognition sounddevice numpy
# O sounddevice tem instalador pronto para QUALQUER Python (inclusive 3.14);
# o pyaudio, não — em Python novo ele falha ao instalar. Por isso o microfone
# aqui usa sounddevice como captador principal e pyaudio só se já existir.
# Sem as libs, o app funciona normalmente e o botão 🎤 explica como habilitar.
try:
    import speech_recognition as sr
    VOZ_SR = True
except Exception:
    # Mesmo motivo do sounddevice logo abaixo: recurso opcional que falha no
    # import não pode impedir o programa de abrir.
    VOZ_SR = False
try:
    import sounddevice as _sd
    VOZ_SD = True
    VOZ_SD_ERRO = ""
except Exception as _e_sd:
    # `except Exception`, NÃO `except ImportError`. O sounddevice instalado
    # sem a biblioteca nativa do PortAudio levanta
    #     OSError: PortAudio library not found
    # já no import — que passava direto por um `except ImportError` e MATAVA O
    # PROGRAMA NA PARTIDA, com um traceback, antes de a janela existir. Um
    # recurso opcional (o microfone) não pode derrubar o app inteiro.
    # Descoberto pelo teste de fumaça da interface, não pelo pregão.
    #
    # O TEXTO DO ERRO IMPORTA. No Mac o pip instalava o sounddevice sem
    # problema e o import falhava mesmo assim, com "No module named 'numpy'" —
    # porque o sounddevice importa numpy e o numpy não vinha junto. O app
    # engolia a mensagem e mandava "rode: pip install sounddevice", que era
    # justamente o que o trader já tinha feito. Agora ele lê a causa real.
    VOZ_SD = False
    VOZ_SD_ERRO = str(_e_sd)
VOZ_DISPONIVEL = VOZ_SR  # STT precisa do SpeechRecognition; captura tem fallback

# ONDE o trader vai autorizar/trocar o microfone. Cada sistema tem um lugar, e
# mandar um usuário de Mac abrir "Configurações → Sistema → Som do Windows" é
# uma instrução que não existe na máquina dele.
ONDE_PERMITIR_MIC = (
    "Ajustes do Sistema → Privacidade e Segurança → Microfone (marque o "
    "SMC Quant Pro, ou o Terminal se você abre por lá)"
    if plataforma.E_MACOS else
    "Configurações → Privacidade → Microfone do Windows")
ONDE_TROCAR_MIC = (
    "Ajustes do Sistema → Som → Entrada (macOS)" if plataforma.E_MACOS else
    "Configurações → Sistema → Som (Windows)")

def abrir_stream_microfone(taxa, bloco):
    """Abre o microfone SEM depender do numpy.

    O DEFEITO (log de 11/08, 16:00 — no Mac):
        (🐯 modo OLÁ TIGER LIGADO — escutando pelo microfone "MacBook Air
         Microphone".)
        (🐯 não consegui abrir o microfone: No module named 'numpy'.)

    Repare na contradição: ela CONSEGUIU ler o nome do dispositivo e falhou
    logo depois. Não era falta do sounddevice — ele importou e o
    `query_devices` funcionou. O que faltava era o numpy, e ele só é exigido
    num ponto: o `sd.InputStream` devolve as amostras como array do numpy.

    Só que este programa NUNCA usou o array do numpy. Todo lugar que lê o
    stream faz `bytes(bloco)` na hora e trata como bytes crus (o RMS é
    calculado com `array.array("h", ...)`, da biblioteca padrão). Ou seja: a
    dependência era paga e não era usada.

    O `RawInputStream` entrega exatamente os mesmos bytes crus e não importa
    numpy nenhum. Com isso o microfone volta a funcionar sem instalar nada —
    nem no Mac, nem no Windows. O `InputStream` fica como segunda tentativa,
    para o caso de uma versão do sounddevice que não tenha o Raw.
    """
    try:
        return _sd.RawInputStream(samplerate=taxa, channels=1,
                                  dtype="int16", blocksize=bloco)
    except AttributeError:
        # sounddevice muito antigo, sem RawInputStream: cai no clássico (que
        # aí sim precisa do numpy — e o erro vai dizer isso com todas as letras).
        return _sd.InputStream(samplerate=taxa, channels=1,
                               dtype="int16", blocksize=bloco)


def explicar_falha_do_microfone(erro):
    """A mensagem certa para a falha certa.

    Antes, QUALQUER erro ao abrir o microfone virava "feche outros programas e
    confira as permissões". Quando a causa era uma biblioteca faltando, aquilo
    mandava o trader procurar num lugar onde não havia nada de errado — foi o
    que aconteceu com o numpy: ele foi conferir permissões do sistema por causa
    de um pacote do Python."""
    texto = str(erro)
    faltando = re.search(r"No module named ['\"]([\w.]+)['\"]", texto)
    if faltando or isinstance(erro, ImportError):
        pacote = faltando.group(1) if faltando else "uma biblioteca"
        py = "python3" if plataforma.E_MACOS else "python"
        return (f"falta a biblioteca {pacote} — isto NÃO é permissão nem "
                f"microfone ocupado. Rode no Terminal:  {py} -m pip install "
                f"{pacote}  e reabra o app.")
    return (f"{texto[:120]}. Feche outros programas que estejam usando o mic e "
            f"confira as permissões: {ONDE_PERMITIR_MIC}.")


def texto_falta_voz():
    """O que dizer quando o microfone não sobe — com a CAUSA e o comando certo
    para a máquina certa. A mensagem antiga era a mesma sempre, mandava
    reinstalar o que já estava instalado e falava em Windows dentro do Mac."""
    faltando = []
    if not VOZ_SR:
        faltando.append("SpeechRecognition")
    if not VOZ_SD:
        faltando.append("sounddevice")
        if "numpy" in (VOZ_SD_ERRO or ""):
            faltando.append("numpy")
    if not faltando:
        return "microfone indisponível"
    pacotes = " ".join(dict.fromkeys(faltando))
    py = "python3" if plataforma.E_MACOS else "python"
    causa = f" (o erro exato foi: {VOZ_SD_ERRO})" if VOZ_SD_ERRO else ""
    return (f"para o modo OLÁ TIGER e o 🎤, falta {', '.join(dict.fromkeys(faltando))}"
            f"{causa}. Rode no Terminal:  {py} -m pip install {pacotes}  "
            "e reabra o app.")

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
VERSAO_ATUAL = "2.40.0"

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

def limpar_chave_colada(texto, padrao=None):
    """Conserta o texto que sai do Cmd+V no macOS.

    O DEFEITO, e ele custou um pregao inteiro: no macOS o Tk tem uma ligacao
    propria para <<Paste>> E a classe Entry tambem trata o Cmd+V. As duas
    disparam, e o conteudo da area de transferencia entra DUAS VEZES. No campo
    da licenca isso apareceu como
        SMC-DDPX-XZUG-PH8GSMC-DDPX-XZUG-PH8G
    e no campo da CHAVE DA GEMINI, invisivel (o campo mostra asteriscos), a
    chave dobrada virava um texto que a Google recusa com
        401 UNAUTHENTICATED / ACCESS_TOKEN_TYPE_UNSUPPORTED
    -- que NAO e cota, e sim credencial malformada. Foi por isso que os dez
    modelos falharam em sequencia: nao havia chave valida nenhuma.

    Aqui a duplicacao e desfeita de forma conservadora: so quando o texto e
    EXATAMENTE a mesma coisa duas vezes coladas. Nada de adivinhar.
    """
    t = "".join(str(texto or "").split())      # tira espacos, quebras e tabs
    if not t:
        return ""
    meio = len(t) // 2
    if len(t) % 2 == 0 and t[:meio] == t[meio:]:
        t = t[:meio]
    if padrao:
        import re as _re
        m = _re.match(padrao, t)
        if m:
            t = m.group(0)
    return t


def ligar_colar_sem_duplicar(widget):
    """Faz o Cmd+V colar UMA vez neste campo.

    So mexe no macOS -- no Windows o comportamento sempre esteve certo, e
    trocar o que funciona seria criar defeito novo. A ligacao devolve 'break'
    para o Tk parar ali e nao rodar a segunda insercao.
    """
    if not plataforma.E_MACOS:
        return widget
    alvo = getattr(widget, "_entry", widget)      # CTkEntry embrulha um Entry

    def colar(_evento=None):
        try:
            try:
                if alvo.selection_present():
                    alvo.delete("sel.first", "sel.last")
            except Exception:
                pass
            texto = "".join(str(alvo.clipboard_get() or "").split())
            alvo.insert("insert", texto)
        except Exception:
            pass
        return "break"

    for atalho in ("<Command-v>", "<Command-V>", "<<Paste>>"):
        try:
            alvo.bind(atalho, colar)
        except Exception:
            pass
    return widget


def diretorio_da_aplicacao():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def pasta_dados_usuario():
    """Windows: %APPDATA%\\SMC_Quant_Pro.
    macOS:   ~/Library/Application Support/SMC_Quant_Pro (lugar canônico do
    sistema, o mesmo que qualquer app nativo usa)."""
    return plataforma.pasta_dados()

DIR_ORIGEM_MOTOR = os.path.join(diretorio_da_aplicacao(), "motor")
DIR_DADOS_MOTOR = os.path.join(pasta_dados_usuario(), "motor")
CONFIG_FILE = os.path.join(pasta_dados_usuario(), "config_smc.json")
PERFORMANCE_FILE = os.path.join(pasta_dados_usuario(), "performance_db.json")
SIGNALS_LOG_FILE = os.path.join(pasta_dados_usuario(), "signals_log.json")
POSITIONS_FILE = os.path.join(pasta_dados_usuario(), "positions_db.json")
LICENCA_FILE = os.path.join(pasta_dados_usuario(), "licenca.json")
# IA interativa: conversa persistida + lições que VOCÊ ensina ao robô.
CHAT_FILE = os.path.join(pasta_dados_usuario(), "chat_ia.json")
LICOES_FILE = os.path.join(pasta_dados_usuario(), "licoes_trader.json")
# OLHOS DA TIGER: a última captura que o motor fez do gráfico fica salva aqui.
# É o que permite perguntar no chat "olha o gráfico agora" e ela ver de fato a
# MESMA imagem que gerou a sugestão — sem você precisar tirar print à mão.
ULTIMO_PRINT_FILE = os.path.join(pasta_dados_usuario(), "ultimo_print.png")

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

def salvar_config(dados: dict, substituir: bool = False):
    """`substituir=True` grava o dicionário INTEIRO, em vez de mesclar. É o
    único jeito de REMOVER uma chave do config (apagar a chave de um provedor,
    por exemplo) — com o merge, uma chave apagada voltaria na próxima leitura."""
    atual = dict(dados) if substituir else carregar_config()
    if not substituir:
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

# Piso da casa: quantos ticks, no mínimo, um stop precisa ter para ser tratado
# como stop de verdade (ver `calcular_contratos` e a tabela TICK_MINIMO mais
# abaixo). É REGRA CONFIGURÁVEL por conta, não constante do mercado.
MIN_TICKS_STOP_PADRAO = 8

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
    # ---- TRAVAS DE TAMANHO DE POSIÇÃO ----
    #   max_contratos  -> teto duro por operação (0 = automático, sem teto fixo)
    #   min_ticks_stop -> stop mais curto que isso NÃO dimensiona posição
    # Ver `calcular_contratos`: sem esses dois, um stop de 1,87 ponto no MES
    # dimensionava 30 contratos numa conta de US$1.400.
    "max_contratos": 0,
    "min_ticks_stop": MIN_TICKS_STOP_PADRAO,
    # Em quantos dias operados a meta deve ser batida. Era fixo em 5; agora você
    # escolhe — 1 para "quero bater hoje", 20 para um mês de mesa, etc. Isso muda
    # o ritmo exigido por dia E entra no contexto que a IA recebe.
    "dias_meta": 5,
    "data_inicio": None,
    # QUAL DIA DO CICLO É HOJE — escolhido por ELE, clicando na trilha.
    #
    # Print de 17/08/2026, uma segunda-feira. A trilha mostrava
    #     D1 ✅  D2 ❌  D3 ❌  D4 ⬜ ...
    # e os dois ❌ eram SÁBADO (15/08) e DOMINGO (16/08). O ciclo começou na
    # sexta, o mercado ficou fechado o fim de semana inteiro, e mesmo assim
    # dois dias do prazo foram consumidos e marcados como dias PERDIDOS. O
    # efeito no bolso: o ritmo exigido saltou de US$ 400 para US$ 553,42 por
    # dia, por causa de dois dias em que não havia como operar.
    #
    # A causa era uma subtração de calendário — `(hoje - inicio).days`. Ela
    # não sabe de fim de semana, não sabe de feriado, e não sabe que ele pode
    # simplesmente decidir não operar num dia.
    #
    # Guarda uma ÂNCORA, não um número solto: {"dia": N, "data": "AAAA-MM-DD"}
    # significa "naquela data, o ciclo estava no dia N". Guardar só o número
    # congelaria o dia para sempre; guardar a âncora deixa o contador andar
    # sozinho a partir da escolha dele.
    "dia_ciclo_ancora": None,
    # O QUE ACONTECEU EM CADA DIA, quando quem diz é ELE.
    #
    # 17/08, 19:59: "repare que o dia 2, mesmo após eu ter incluso
    # manualmente, se eu clicar no dia 3 para preenchimento a partir de agora,
    # o dia dois fica como se não tivesse operado".
    #
    # A marca de cada quadradinho era deduzida de uma única conta: lucro
    # ACUMULADO do ciclo contra a meta acumulada esperada até aquele dia. Isso
    # nunca soube responder "eu operei neste dia?" — só "o ciclo está em dia?".
    # Um dia lucrativo aparecia com ❌ porque o ACUMULADO ainda não tinha
    # alcançado a meta, e um dia em que ele nem ligou a plataforma aparecia
    # igual a um dia de prejuízo.
    #
    # Aqui ele diz. {"2": "concluido"} | {"3": "nao_operei"} — o que estiver
    # marcado manda na dedução; o que não estiver segue automático.
    "dias_marcados": {},
    # ---- FREIO DE SUGESTÕES (proteção contra sequência de stops) ----
    # O robô analisa a cada poucos minutos e o mercado não muda de opinião nesse
    # ritmo: sem freio, ele reapresenta o mesmo cenário sem parar e o trader
    # acaba tomando stop atrás de stop. Estes números são o limite de quanto ele
    # pode insistir num dia. Todos configuráveis por conta.
    #   max_stops_seguidos -> depois de N stops seguidos, ele para e espera
    #   cooldown_stop_min  -> quanto tempo ele fica calado depois disso
    #   max_operacoes_dia  -> teto de operações executadas no dia (0 = sem teto)
    "max_stops_seguidos": 2,
    "cooldown_stop_min": 30,
    "max_operacoes_dia": 6,
    # O QUE FAZER QUANDO VOCÊ JÁ ESTÁ POSICIONADO NO ATIVO:
    #   "alerta"   (padrão) -> cenário CONTRA a posição vira ALERTA DE RISCO, e
    #                          cenário A FAVOR vira sugestão de AUMENTO
    #   "livre"             -> sugere normalmente, como se não houvesse posição
    #   "bloquear"          -> não sugere nada enquanto houver posição no ativo
    "com_posicao_aberta": "alerta",
}

def dias_meta_do_plano(plano=None):
    """Prazo (em dias) da meta na conta selecionada. Mínimo 1."""
    plano = plano if plano is not None else plano_da_conta_ativa()
    try:
        return max(1, int(float(plano.get("dias_meta", 5))))
    except (TypeError, ValueError):
        return 5


def _domingo_e_pregao(cfg=None):
    """O domingo conta como dia de pregão nesta configuração?

    Conta quando o pregão ATRAVESSA A MEIA-NOITE (19:00→17:59), porque aí a
    semana abre domingo às 19h — foi o próprio trader quem escreveu isso à
    ferramenta em 14/08: 'o mercado começa às 19h de domingo e encerra às
    17:59 de sexta-feira'. Com pregão que não vira o dia (09:00→17:00),
    domingo não existe como sessão."""
    try:
        c = cfg if cfg is not None else carregar_config()
        ini = str(c.get("hora_inicio", PADRAO_CONFIG_APP["hora_inicio"]))
        fim = str(c.get("hora_fim", PADRAO_CONFIG_APP["hora_fim"]))
        h_ini, m_ini = (int(x) for x in ini.split(":")[:2])
        h_fim, m_fim = (int(x) for x in fim.split(":")[:2])
    except Exception:
        return False
    return (h_ini, m_ini) > (h_fim, m_fim)


def dias_de_pregao_entre(inicio, fim, cfg=None):
    """Quantos dias de PREGÃO se passaram de `inicio` até `fim` (exclusivo).

    Função PURA, recebe e devolve datas — dá para testar sem abrir janela.

    SÁBADO NUNCA CONTA, em nenhuma configuração: não existe sessão. Domingo
    conta só quando o pregão atravessa a meia-noite (ver `_domingo_e_pregao`).

    É a substituição de `(fim - inicio).days`, que foi o que fez o fim de
    semana de 15 e 16/08 comer dois dias do prazo de oito dias dele e empurrar
    o ritmo exigido de US$ 400 para US$ 553,42 por dia. Dia em que o mercado
    está fechado não é dia perdido: é dia que não existe."""
    if not inicio or not fim or fim <= inicio:
        return 0
    domingo_conta = _domingo_e_pregao(cfg)
    dias = 0
    d = inicio
    while d < fim:
        d += datetime.timedelta(days=1)
        # weekday(): 5 = sábado, 6 = domingo
        if d.weekday() == 5:
            continue
        if d.weekday() == 6 and not domingo_conta:
            continue
        dias += 1
    return dias


def dia_do_ciclo(plano, hoje=None, cfg=None):
    """Em que dia do ciclo estamos — 1 = primeiro dia. Nunca menor que 1.

    Manda a ÂNCORA que ele escolheu clicando na trilha; sem âncora, conta os
    dias de pregão desde o início do ciclo. Os dois caminhos param no prazo:
    um ciclo de 8 dias não vai para o dia 9, ele acabou."""
    hoje = hoje or datetime.date.today()
    prazo = dias_meta_do_plano(plano)
    ancora = (plano or {}).get("dia_ciclo_ancora") or None
    if isinstance(ancora, dict) and ancora.get("data") and ancora.get("dia"):
        try:
            base_data = datetime.date.fromisoformat(str(ancora["data"]))
            base_dia = max(1, int(ancora["dia"]))
            andou = dias_de_pregao_entre(base_data, hoje, cfg)
            return max(1, min(base_dia + andou, prazo))
        except (ValueError, TypeError):
            pass
    inicio_str = (plano or {}).get("data_inicio")
    if not inicio_str:
        return 1
    try:
        inicio = datetime.date.fromisoformat(str(inicio_str))
    except (ValueError, TypeError):
        return 1
    return max(1, min(1 + dias_de_pregao_entre(inicio, hoje, cfg), prazo))


def _passo_de_pregao(data, adiante=True, cfg=None):
    """O próximo (ou o anterior) dia de PREGÃO a partir de `data`."""
    domingo_conta = _domingo_e_pregao(cfg)
    passo = datetime.timedelta(days=1 if adiante else -1)
    d = data + passo
    for _ in range(14):                    # 14 é folga de sobra para um fim de semana
        if d.weekday() == 5 or (d.weekday() == 6 and not domingo_conta):
            d += passo
            continue
        return d
    return d


def data_do_dia_do_ciclo(plano, n, cfg=None):
    """A data de calendário do dia N do ciclo. Devolve None sem referência.

    É a VOLTA de `dia_do_ciclo`, e existe porque ele precisa lançar o resultado
    de UM dia específico ("o dia 2 fica como se não tivesse operado"). Para
    gravar no dia certo é preciso saber que data é aquele dia.

    Anda pelos mesmos dias de pregão que a ida — se as duas contas
    divergissem, o dia 2 da trilha não seria o dia 2 do diário."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    plano = plano or {}
    # A referência é a âncora que ele escolheu; sem ela, o início do ciclo.
    ancora = plano.get("dia_ciclo_ancora") or None
    ref_data = ref_dia = None
    if isinstance(ancora, dict) and ancora.get("data") and ancora.get("dia"):
        try:
            ref_data = datetime.date.fromisoformat(str(ancora["data"]))
            ref_dia = max(1, int(ancora["dia"]))
        except (ValueError, TypeError):
            ref_data = ref_dia = None
    if ref_data is None:
        try:
            ref_data = datetime.date.fromisoformat(str(plano.get("data_inicio")))
            ref_dia = 1
        except (ValueError, TypeError):
            return None
    d = ref_data
    for _ in range(abs(n - ref_dia)):
        d = _passo_de_pregao(d, adiante=(n > ref_dia), cfg=cfg)
    return d


def carimbo_para_o_pregao(dia, cfg=None):
    """Um horário que a ferramenta lê como pertencendo AO PREGÃO de `dia`.

    Esta função é a resposta ao defeito que ele descreveu em 17/08 às 19:59:
        "hoje encerrou às 17:59, abriu às 19h, mas antes de fechar eu fiz 54
         dólares e incluí no diário, e não está contabilizando"
    Com o pregão 19:00→17:59, TODA hora anterior às 19:00 pertence ao pregão do
    dia ANTERIOR. Ele operou de tarde, lançou perto das 18h — e o lançamento,
    corretamente pela regra da sessão, caiu no pregão de ontem. Só que a
    ferramenta nunca disse isso: o dinheiro simplesmente não aparecia em 'hoje'.

    Então, para gravar num dia escolhido, não basta carimbar meio-dia: com
    pregão que vira, meio-dia do dia D pertence ao pregão D-1. Aqui o horário é
    escolhido para que `data_do_pregao` devolva exatamente o dia pedido.

    Devolve string 'dd/mm/aaaa HH:MM'. Função pura o bastante para testar."""
    if isinstance(dia, str):
        try:
            dia = datetime.datetime.strptime(dia, "%d/%m/%Y").date()
        except ValueError:
            try:
                dia = datetime.date.fromisoformat(dia)
            except ValueError:
                return None
    if not isinstance(dia, (datetime.date, datetime.datetime)):
        return None
    if isinstance(dia, datetime.datetime):
        dia = dia.date()
    try:
        c = cfg if cfg is not None else carregar_config()
        ini = str(c.get("hora_inicio", PADRAO_CONFIG_APP["hora_inicio"]))
        fim = str(c.get("hora_fim", PADRAO_CONFIG_APP["hora_fim"]))
        h_ini, m_ini = (int(x) for x in ini.split(":")[:2])
        h_fim, m_fim = (int(x) for x in fim.split(":")[:2])
    except Exception:
        return dia.strftime("%d/%m/%Y 12:00")
    if (h_ini, m_ini) <= (h_fim, m_fim):
        # Pregão que não vira o dia: qualquer hora do próprio dia serve.
        return dia.strftime("%d/%m/%Y ") + f"{h_ini:02d}:{max(m_ini, 1):02d}"
    # Pregão que VIRA: o dia começa na hora de abertura. Um minuto depois dela
    # está dentro da sessão e não corre risco de cair na véspera.
    minuto = m_ini + 1
    hora = h_ini + (1 if minuto > 59 else 0)
    minuto = 0 if minuto > 59 else minuto
    if hora > 23:                          # abertura às 23:59 — caso de borda
        hora, minuto = 23, 59
    return dia.strftime("%d/%m/%Y ") + f"{hora:02d}:{minuto:02d}"


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
    """Protege a chave da API com o cofre DO SISTEMA.
    Windows: DPAPI. macOS: Chaveiro. Os dois têm a propriedade que importa —
    copiar o config para outra máquina NÃO leva a chave junto."""
    return plataforma.proteger_segredo(texto)

def dpapi_decrypt(texto_cifrado: str) -> str:
    return plataforma.revelar_segredo(texto_cifrado)

def carregar_api_key() -> str:
    cfg = carregar_config()
    cifrado = cfg.get("gemini_api_key_enc")
    if cifrado:
        return dpapi_decrypt(cifrado)
    return ""

def salvar_api_key(api_key_texto: str):
    """Ultima barreira antes do disco: a chave passa pela limpeza mesmo que
    tenha vindo de outro caminho que nao o campo da interface."""
    api_key_texto = limpar_chave_colada(api_key_texto)
    salvar_config({"gemini_api_key_enc": dpapi_encrypt(api_key_texto)})


# ====================================================================
# SEGUNDA (E TERCEIRA) INTELIGÊNCIA — quando a Gemini cai, alguém responde
# ====================================================================
# O DIAGNÓSTICO, com as frases do log de 12/08:
#
#   10:23 ❯ satatus
#   10:23 ✳ "Não tenho como responder isso com segurança agora: não está na
#            minha base, não consegui confirmar na internet, e a API está fora"
#   11:32 ❯ sim            (respondendo à pergunta QUE ELA MESMA fez)
#   11:32 ✳ [o mesmo despejo]
#   11:35 ❯ o que deu errado na sugestão que você havia me passado
#   11:35 ✳ [o mesmo despejo]
#   11:36 ❯ era para você saber responder perguntas de modo geral, você não é
#            uma IA?
#   11:36 ✳ [o mesmo despejo]
#
# Ele tem razão, e a causa é de ARQUITETURA, não de prompt: a TIGER era
# Gemini-e-mais-nada. Estourada a cota do plano gratuito — que estoura todo
# dia, com o motor analisando de 5 em 5 minutos —, não sobrava NINGUÉM para
# pensar. Tudo caía no roteador local, que só cobre o que tem regra escrita.
#
# A correção é ter mais de um cérebro. Aqui está a camada de provedores: a
# mesma pergunta pode ser respondida pela Gemini, pela OpenAI, pela Anthropic
# ou por qualquer serviço compatível com a API da OpenAI (Groq, OpenRouter,
# DeepSeek, Together, xAI). Basta o trader colar UMA chave a mais na aba
# Motor — e a partir daí a queda de um não cala a ferramenta.
#
# Duas decisões de projeto que NÃO mudam:
#   • Nada disso toca dinheiro. Dimensionamento, piso de qualidade, freio e
#     execução continuam sendo código determinístico. Trocar de modelo não
#     pode mudar quantos contratos entram.
#   • A regra anti-invenção vale para todos: se ninguém responder, ela diz que
#     não sabe. Ter cinco provedores não autoriza chutar.
#
# Nenhuma biblioteca nova: OpenAI e Anthropic falam HTTP/JSON, e o `requests`
# já é dependência do programa desde a primeira versão.
PROVEDORES_IA = {
    "gemini": {
        "rotulo": "Google Gemini",
        "formato": "gemini",          # tratado pelo SDK próprio, já existente
        "onde_pegar": "https://aistudio.google.com/apikey",
        "modelos": [],                # descobertos na própria API
    },
    "openai": {
        "rotulo": "OpenAI (ChatGPT)",
        "formato": "openai",
        "url": "https://api.openai.com/v1/chat/completions",
        "onde_pegar": "https://platform.openai.com/api-keys",
        "modelos": ["gpt-4o-mini", "gpt-4o"],
    },
    "anthropic": {
        "rotulo": "Anthropic (Claude)",
        "formato": "anthropic",
        "url": "https://api.anthropic.com/v1/messages",
        "onde_pegar": "https://console.anthropic.com/settings/keys",
        "modelos": ["claude-sonnet-4-5", "claude-haiku-4-5"],
    },
    "openrouter": {
        "rotulo": "OpenRouter (vários modelos numa chave só)",
        "formato": "openai",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "onde_pegar": "https://openrouter.ai/keys",
        "modelos": ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"],
    },
    "groq": {
        "rotulo": "Groq (rápido e com camada gratuita)",
        "formato": "openai",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "onde_pegar": "https://console.groq.com/keys",
        "modelos": ["llama-3.3-70b-versatile"],
    },
    # A IA QUE RODA NA SUA MÁQUINA. Sem chave, sem internet, sem cota e sem
    # conta em lugar nenhum: o Ollama sobe um modelo local e expõe o MESMO
    # protocolo da OpenAI em localhost:11434 — por isso ele entra aqui sem
    # uma linha de código novo de rede.
    #
    # É o único provedor que não pode ficar sem responder por motivo de
    # dinheiro, que foi o que derrubou a segunda inteligência no dia 12/08
    # ("You have no credits remaining"). Em troca, o modelo é menor: serve
    # para CONVERSA e metodologia, não para ler número de gráfico — e não
    # precisa servir, porque quem lê número agora é o OCR.
    "local": {
        "rotulo": "IA LOCAL (Ollama — sem chave, sem internet)",
        "formato": "openai",
        "url": "http://localhost:11434/v1/chat/completions",
        "onde_pegar": "https://ollama.com/download",
        "sem_chave": True,
        "modelos": ["qwen2.5:7b", "llama3.1:8b", "gemma2:9b", "mistral:7b"],
    },
}

# A ordem em que os alternativos são tentados quando a Gemini não responde.
# A LOCAL vem por último de propósito: quando há um modelo grande disponível,
# ele responde melhor. Mas ela é a que NUNCA falta — é o chão da escada.
ORDEM_PROVEDORES = ["openai", "anthropic", "openrouter", "groq", "local"]


def diagnostico_de_provedor(erro, rotulo=""):
    """Traduz a recusa do provedor para uma frase que diz O QUE FAZER.

    A causa vinha ESCRITA na resposta e estava sendo trocada por um palpite.
    No log de 12/08 a OpenAI respondeu, com todas as letras:
        "You have no credits remaining. Add credits to continue..."
    e o app disse ao trader que a chave "pode estar errada, sem crédito, ou o
    modelo indisponível". Ele ficou sem saber qual das três — com a resposta
    na mão. Função PURA: recebe o erro, devolve a frase."""
    e = str(erro or "")
    E = e.upper()
    quem = f"{rotulo}: " if rotulo else ""
    if not e:
        return f"{quem}não veio resposta nem erro. Tente de novo em instantes."
    if "NO CREDITS" in E or "INSUFFICIENT_QUOTA" in E or "BILLING" in E:
        return (f"{quem}a chave é VÁLIDA, mas a conta está SEM CRÉDITO. "
                "Não é erro de digitação nem de configuração — é saldo. "
                "Adicione crédito no painel do provedor, ou use um provedor "
                "com camada gratuita.")
    if "429" in E or "RATE LIMIT" in E or "RESOURCE_EXHAUSTED" in E:
        return (f"{quem}limite de uso atingido agora (429). A chave funciona; "
                "espere alguns minutos e teste de novo.")
    if any(x in E for x in ("401", "INVALID_API_KEY", "UNAUTHORIZED",
                            "AUTHENTICATION")):
        return (f"{quem}a chave foi RECUSADA (401). Copie de novo do painel do "
                "provedor — sem espaços no começo ou no fim.")
    if "403" in E or "PERMISSION" in E:
        return (f"{quem}a chave existe mas não tem permissão para este modelo "
                "(403). Confira o que a sua conta libera.")
    if "404" in E or "MODEL_NOT_FOUND" in E or "DOES NOT EXIST" in E:
        return (f"{quem}o modelo pedido não existe para esta conta (404).")
    if any(x in E for x in ("TIMEOUT", "TIMED OUT", "CONNECTION",
                            "NAME OR SERVICE", "SSL")):
        return (f"{quem}não cheguei ao servidor (rede/timeout). "
                "Confira a internet e tente de novo.")
    return f"{quem}{e[:160]}"


def carregar_chave_provedor(pid: str) -> str:
    """A chave de um provedor alternativo, do cofre do sistema (Chaveiro no
    Mac, DPAPI no Windows) — o mesmo tratamento da chave da Gemini."""
    if pid == "gemini":
        return carregar_api_key()
    cifrado = carregar_config().get(f"chave_{pid}_enc")
    return dpapi_decrypt(cifrado) if cifrado else ""


def salvar_chave_provedor(pid: str, chave: str):
    if pid == "gemini":
        return salvar_api_key(chave)
    chave = limpar_chave_colada(chave)
    if chave:
        salvar_config({f"chave_{pid}_enc": dpapi_encrypt(chave)})
    else:
        # Campo apagado = remover a chave. Guardar cifra de string vazia
        # deixaria o provedor "configurado" e ele entraria na fila para falhar.
        cfg = carregar_config()
        cfg.pop(f"chave_{pid}_enc", None)
        salvar_config(cfg, substituir=True)


# O modelo padrão da IA local. Escolhido por CABER: ~4,7 GB, roda em Mac de
# 8 GB de RAM, fala português bem e segue instrução. Um modelo maior responde
# melhor e não abre numa máquina modesta — e a ferramenta que não abre na
# máquina do cliente não serve para nada.
_RAM_NAO_INFORMADA = object()

MODELO_LOCAL_PADRAO = "qwen2.5:7b"
# Para máquina apertada. Metade do tamanho, resposta mais curta e mais crua.
MODELO_LOCAL_LEVE = "qwen2.5:3b"
# O MODELO QUE ENXERGA. Sem ele, a IA local não serve para o motor: qwen2.5
# é modelo de TEXTO e não vê imagem nenhuma — foi por isso que, com a Gemini
# fora do ar, o ciclo morria inteiro mesmo com a IA local instalada e no ar.
# qwen2.5vl é a versão com visão do mesmo modelo, e lê gráfico razoavelmente.
MODELO_VISAO_LOCAL = "qwen2.5vl:7b"
MODELO_VISAO_LOCAL_LEVE = "qwen2.5vl:3b"


def modelo_visao_recomendado(ram_gb=_RAM_NAO_INFORMADA):
    """O modelo de VISÃO que cabe nesta máquina."""
    ram = _num_gb_de_ram() if ram_gb is _RAM_NAO_INFORMADA else ram_gb
    if ram is not None and ram < 12:
        return MODELO_VISAO_LOCAL_LEVE
    return MODELO_VISAO_LOCAL


# O LADO MAIOR DA IMAGEM QUE VAI PARA A IA LOCAL.
# A Gemini roda no servidor do Google e recebe a tela inteira sem reclamar.
# O modelo local roda NA MÁQUINA DELE, e um modelo de visão pica a imagem em
# quadradinhos de 28x28 antes de pensar: uma tela de MacBook (3024x1964) vira
# mais de sete mil pedaços. É por isso que o computador inteiro ficou lento e
# a leitura não voltou dentro do prazo. Em 1400px o gráfico continua legível
# (o preço tem uns 12px de altura) e o custo cai por volta de cinco vezes.
LADO_MAX_VISAO_LOCAL = 1400


def _b64_da_imagem(imagem_pil, lado_max=LADO_MAX_VISAO_LOCAL):
    """A imagem no formato que o Ollama espera (base64, sem prefixo),
    reduzida ao que o modelo local consegue mastigar."""
    img = imagem_pil.convert("RGB")
    try:
        maior = max(img.size)
        if lado_max and maior > lado_max:
            fator = lado_max / float(maior)
            novo = (max(1, int(img.size[0] * fator)),
                    max(1, int(img.size[1] * fator)))
            img = img.resize(novo, Image.LANCZOS)
    except Exception:
        pass          # reduzir é otimização; falhar aqui não pode custar a leitura
    saida = BytesIO()
    img.save(saida, format="JPEG", quality=90, subsampling=0)
    return base64.b64encode(saida.getvalue()).decode("utf-8")


# Como se reconhece um modelo que ENXERGA, pelo nome. É a convenção do
# Ollama: os modelos de visão trazem vl / vision / llava / moondream / gemma3
# no nome. Uma lista de nomes exatos envelheceria em uma semana.
_MARCAS_DE_VISAO = ("vl", "vision", "llava", "moondream", "bakllava",
                    "minicpm-v", "gemma3")


def tem_modelo_de_visao(instalados):
    """Existe, entre os modelos baixados, algum que enxerga imagem?

    Função PURA. Foi a falta dela que produziu o defeito: o app tratava
    'tem algum modelo' como 'está pronto', e com um modelo de TEXTO puro
    instalado ele dizia 'nada a fazer' e nunca baixava a visão."""
    for m in (instalados or []):
        n = str(m).lower()
        if any(marca in n for marca in _MARCAS_DE_VISAO):
            return True
    return False


def modelo_de_visao_instalado(instalados):
    """O NOME do modelo de visão baixado, ou None."""
    for m in (instalados or []):
        n = str(m).lower()
        if any(marca in n for marca in _MARCAS_DE_VISAO):
            return m
    return None


# AS CHAVES QUE A ANÁLISE PRECISA TER PARA VALER ALGUMA COISA.
# A Gemini recebe um `response_schema` e o servidor do Google OBRIGA o
# formato. O Ollama não tem nada disso: `format="json"` garante que sai JSON
# e mais nada. Sem dizer as chaves por extenso, o modelo local inventa as
# dele — "signal", "price", "trend" — o `json.loads` passa, e o ciclo morre
# logo depois lendo `current_price` que não existe. Reserva que nunca entrega
# é o mesmo que reserva nenhuma.
CHAVES_DA_ANALISE = ("asset_symbol", "current_price", "market_analysis",
                     "confluence_factors", "confidence_score",
                     "probabilidade", "action")

_CONTRATO_JSON_LOCAL = """

FORMATO DA RESPOSTA — OBRIGATÓRIO. Responda SOMENTE com um objeto JSON, sem
texto antes nem depois, sem ``` , com EXATAMENTE estas chaves:
{"asset_symbol": "o ticker lido no gráfico, ex MESU6; se não conseguir ler, DESCONHECIDO",
 "current_price": número do último preço,
 "market_analysis": "texto em português",
 "confluence_factors": ["lista", "de", "textos"],
 "confidence_score": número de 0 a 100,
 "probabilidade": número de 0 a 100,
 "action": "BUY" ou "SELL" ou "HOLD",
 "entry_price": número, "stop_loss": número,
 "take_profit_1": número, "take_profit_2": número,
 "ledger_update": "texto em português"}
Se não conseguir LER um preço no gráfico, use 0 — nunca invente um número."""


def prompt_para_visao_local(prompt):
    """O mesmo prompt da Gemini, com o contrato de saída escrito por extenso.

    Função PURA, para poder ser conferida sem subir modelo nenhum."""
    return (prompt or "") + _CONTRATO_JSON_LOCAL


def analise_local_valida(bruto):
    """O texto cru do modelo local vira dict — ou None, sem meio-termo.

    JSON válido NÃO é resposta válida: `{"trend": "alta"}` passa no
    `json.loads` e não tem uma única informação que o motor use. Aqui só
    passa o que traz TODAS as chaves obrigatórias."""
    try:
        dados = json.loads(bruto)
    except Exception:
        return None
    if not isinstance(dados, dict):
        return None
    for chave in CHAVES_DA_ANALISE:
        if chave not in dados:
            return None
    return dados


def analisar_grafico_local(imagem_pil, prompt, modelo=None, timeout=420):
    """Lê o gráfico com o modelo de VISÃO que roda nesta máquina.

    Existe porque, em 13/08, TODOS os dez modelos da Gemini devolveram 503 ou
    429 no mesmo ciclo e a análise morreu — com a IA local instalada, no ar, e
    inútil, porque o modelo baixado era de texto puro.

    DEVOLVE (texto, motivo). NUNCA levanta: a reserva não pode derrubar o
    ciclo que ela deveria salvar. O motivo é para o LOG — "não devolveu
    resposta neste ciclo" foi o que ele leu no dia 13, e essa frase não diz se
    o modelo demorou demais, se não estava baixado ou se o serviço caiu: três
    problemas com três soluções diferentes. Texto None sempre vem com motivo
    preenchido; texto preenchido vem com motivo vazio.

    O PRAZO É LARGO DE PROPÓSITO (7 min). Os 180s antigos não davam nem para
    o modelo sair do disco: 3,2 GB carregando + a imagem inteira picada em
    milhares de pedaços. Como o ciclo do motor é de 5 min e ela só entra
    quando a Gemini JÁ caiu, esperar é melhor que desistir — não há mais nada
    na fila atrás dela.

    HONESTIDADE QUE PRECISA FICAR ESCRITA: um modelo local de 3 a 7 bilhões de
    parâmetros lê gráfico PIOR que a Gemini. Ele entra como reserva, não como
    igual — e tudo o que ele produz passa pelas mesmas travas do resto
    (conferência do preço contra o título da janela, ticker de contrato
    conhecido, piso de qualidade). Uma leitura de reserva conferida vale mais
    que nenhuma leitura."""
    try:
        modelo = modelo or modelo_visao_recomendado()
        instalados = ia_local_no_ar(timeout=3) or []
        if not instalados:
            return None, "o serviço da IA local não respondeu (Ollama fora do ar)"
        if modelo not in instalados:
            candidato = modelo_de_visao_instalado(instalados)
            if not candidato:
                return None, ("nenhum modelo de visão baixado — os instalados "
                              f"({', '.join(instalados)}) são de texto puro")
            modelo = candidato
        t0 = time.time()
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": modelo, "prompt": prompt_para_visao_local(prompt),
                  "images": [_b64_da_imagem(imagem_pil)],
                  "stream": False, "format": "json",
                  # Mantém o modelo na memória entre os ciclos de 5 min: sem
                  # isto o Ollama descarrega em 5 min e a leitura seguinte
                  # paga de novo o carregamento de 3,2 GB do disco.
                  "keep_alive": "12m",
                  "options": {"temperature": 0.1}},
            timeout=timeout)
        gastou = time.time() - t0
        if r.status_code != 200:
            detalhe = ""
            try:
                detalhe = (r.json() or {}).get("error") or ""
            except Exception:
                detalhe = (r.text or "")[:160]
            return None, f"o Ollama respondeu HTTP {r.status_code}: {detalhe[:160]}"
        texto = ((r.json() or {}).get("response") or "").strip()
        if not texto:
            return None, f"o modelo {modelo} respondeu vazio (levou {gastou:.0f}s)"
        return texto, ""
    except requests.exceptions.Timeout:
        return None, (f"o modelo {modelo} passou de {timeout}s sem terminar. "
                      "Na PRIMEIRA leitura isso é normal: ele carrega alguns "
                      "GB do disco. Se repetir, esta máquina é apertada para "
                      "o modelo de visão")
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:160]}"


def _num_gb_de_ram():
    """RAM total em GB, ou None. Serve para escolher o modelo sem chutar."""
    try:
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
            return (os.sysconf("SC_PAGE_SIZE") *
                    os.sysconf("SC_PHYS_PAGES")) / (1024 ** 3)
    except Exception:
        pass
    try:
        import ctypes as _c

        class _MS(_c.Structure):
            _fields_ = [("dwLength", _c.c_ulong), ("dwMemoryLoad", _c.c_ulong),
                        ("ullTotalPhys", _c.c_ulonglong),
                        ("ullAvailPhys", _c.c_ulonglong),
                        ("ullTotalPageFile", _c.c_ulonglong),
                        ("ullAvailPageFile", _c.c_ulonglong),
                        ("ullTotalVirtual", _c.c_ulonglong),
                        ("ullAvailVirtual", _c.c_ulonglong),
                        ("ullAvailExtendedVirtual", _c.c_ulonglong)]
        st = _MS()
        st.dwLength = _c.sizeof(_MS)
        _c.windll.kernel32.GlobalMemoryStatusEx(_c.byref(st))
        return st.ullTotalPhys / (1024 ** 3)
    except Exception:
        return None


def modelo_local_recomendado(ram_gb=_RAM_NAO_INFORMADA):
    """Qual modelo cabe NESTA máquina. Devolve (modelo, motivo).

    Um modelo que não cabe não é 'mais lento': ele estoura a memória e o
    sistema começa a usar disco como RAM, o que trava a máquina inteira no
    meio do pregão. Melhor um modelo menor de pé que um grande que derruba."""
    # SENTINELA, não None. Sem ela não havia como dizer "não consegui medir":
    # passar None caía na leitura da máquina e devolvia um número — ou seja, a
    # função não sabia expressar a própria ignorância. Foi o teste que pegou.
    ram = _num_gb_de_ram() if ram_gb is _RAM_NAO_INFORMADA else ram_gb
    if ram is None:
        return MODELO_LOCAL_PADRAO, ("não consegui ler a memória desta máquina; "
                                     "indo pelo padrão")
    if ram < 9:
        return MODELO_LOCAL_LEVE, (f"esta máquina tem ~{ram:.0f} GB de RAM — o "
                                   "modelo leve cabe com folga; o padrão "
                                   "brigaria por memória com a corretora")
    return MODELO_LOCAL_PADRAO, (f"esta máquina tem ~{ram:.0f} GB de RAM, "
                                 "espaço de sobra para o modelo padrão")


def ia_local_no_ar(timeout=1.5):
    """O Ollama está rodando nesta máquina AGORA? Pergunta a ele, não adivinha.

    Sem esta checagem, a IA local entraria na fila e daria timeout em toda
    queda da Gemini — atrasando a resposta em vez de salvá-la."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=timeout)
        if r.status_code != 200:
            return []
        return [m.get("name", "") for m in (r.json().get("models") or [])]
    except Exception:
        return []


def provedores_configurados():
    """Quais alternativos estão USÁVEIS agora. Lista vazia = só a Gemini.

    A IA local não tem chave para conferir — o que vale para ela é se o
    Ollama está de pé. Colocá-la na lista sem checar faria a fila esperar um
    servidor que não existe justamente quando a Gemini caiu."""
    prontos = []
    for p in ORDEM_PROVEDORES:
        if PROVEDORES_IA.get(p, {}).get("sem_chave"):
            if ia_local_no_ar():
                prontos.append(p)
        elif carregar_chave_provedor(p):
            prontos.append(p)
    return prontos


def _pedir_openai(url, chave, modelo, mensagens, timeout=45):
    """Formato da OpenAI — o mesmo da Groq, OpenRouter, DeepSeek, Together,
    xAI e de praticamente todo serviço compatível. Uma implementação serve
    para todos."""
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {chave}",
                 "Content-Type": "application/json"},
        # TEMPERATURA BAIXA, DE PROPÓSITO. Numa mesa, criatividade é o defeito:
        # ela é o que faz um modelo pequeno "completar" um valor por ponto que
        # não sabe, ou escorregar de idioma no meio da frase. 0,2 mantém a
        # resposta natural e reduz muito a invenção.
        json={"model": modelo, "messages": mensagens, "max_tokens": 1200,
              "temperature": 0.2},
        timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:220]}")
    dados = r.json()
    return (dados.get("choices") or [{}])[0].get("message", {}).get("content", "")


def _pedir_anthropic(url, chave, modelo, mensagens, timeout=45):
    """A Anthropic separa o `system` do resto e usa cabeçalho próprio."""
    sistema = "\n".join(m["content"] for m in mensagens if m["role"] == "system")
    conversa = [m for m in mensagens if m["role"] != "system"] or \
               [{"role": "user", "content": "."}]
    corpo = {"model": modelo, "max_tokens": 1200, "messages": conversa}
    if sistema:
        corpo["system"] = sistema
    r = requests.post(
        url,
        headers={"x-api-key": chave, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
        json=corpo, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:220]}")
    partes = r.json().get("content") or []
    return "".join(p.get("text", "") for p in partes if p.get("type") == "text")


def responder_por_provedor_alternativo(mensagens, log=None):
    """Tenta os provedores alternativos, em ordem, até um responder.

    Devolve (texto, nome_do_provedor) ou (None, motivo). NUNCA levanta: a
    queda de um provedor não pode derrubar o chat.

    `mensagens` é a lista no formato da OpenAI ([{role, content}]) — é o
    denominador comum; a Anthropic é adaptada dentro de `_pedir_anthropic`.
    """
    tentados = []
    for pid in ORDEM_PROVEDORES:
        info = PROVEDORES_IA[pid]
        # A IA LOCAL NÃO TEM CHAVE — o que ela tem é o Ollama de pé. E os
        # modelos dela são os que estão BAIXADOS nesta máquina, não uma lista
        # fixa: tentar 'qwen2.5:7b' num computador que só tem 'llama3.1:8b'
        # falharia quatro vezes antes de acertar por acaso.
        if info.get("sem_chave"):
            instalados = ia_local_no_ar()
            if not instalados:
                continue
            chave = "local"          # o Ollama ignora o Bearer; precisa existir
            modelos = ([m for m in info["modelos"] if m in instalados]
                       or instalados[:2])
        else:
            chave = carregar_chave_provedor(pid)
            if not chave:
                continue
            modelos = info["modelos"]
        for modelo in modelos:
            try:
                if info["formato"] == "anthropic":
                    txt = _pedir_anthropic(info["url"], chave, modelo, mensagens)
                else:
                    txt = _pedir_openai(info["url"], chave, modelo, mensagens)
                if txt and txt.strip():
                    if log:
                        log(f"🧠 Respondido por {info['rotulo']} ({modelo}) — "
                            "a Gemini não estava disponível.")
                    return txt.strip(), info["rotulo"]
                tentados.append(f"{info['rotulo']}/{modelo}: resposta vazia")
            except Exception as e:
                tentados.append(f"{info['rotulo']}/{modelo}: {str(e)[:90]}")
                continue
    if not tentados:
        return None, "nenhum provedor alternativo configurado"
    return None, " · ".join(tentados[:4])

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

# TAMANHO DO TICK (menor variação de preço do contrato). É especificação de
# contrato, não estimativa. Serve para uma coisa só: saber quando um stop é
# CURTO DEMAIS para ser real.
#
# POR QUE ISTO PASSOU A EXISTIR: o dimensionamento divide o risco permitido
# pela distância até o stop. Quando o motor devolve um stop de 1,87 ponto no
# MES, essa divisão explode — US$280 ÷ US$9,35 = 30 contratos. Trinta contratos
# numa conta de US$1.400. O número está aritmeticamente certo e operacionalmente
# insano: um stop de 7 ticks no MES é ruído de mercado, não invalidação de
# estrutura. Divisor pequeno demais = posição grande demais. Agora existe piso.
TICK_MINIMO = {
    "MES": 0.25, "ES": 0.25,
    "MNQ": 0.25, "NQ": 0.25,
    "MYM": 1.0,  "YM": 1.0,
    "M2K": 0.1,  "RTY": 0.1,
    "MGC": 0.1,  "GC": 0.1,
    "MCL": 0.01, "CL": 0.01,
    "WIN": 5.0,  "IND": 5.0,
    "WDO": 0.5,  "DOL": 0.5,
}
# O piso em ticks (MIN_TICKS_STOP_PADRAO) fica lá em cima, junto do
# PLANO_PADRAO, porque o plano de cada conta já nasce com ele.

def tick_do_ativo(asset_symbol: str):
    """Tamanho do tick pelo ticker lido no gráfico. None quando o ativo não
    está na tabela — e aí o piso de ticks NÃO é aplicado (não dá para medir
    o que não se conhece; inventar um tick seria pior que não ter piso)."""
    if not asset_symbol:
        return None
    simbolo = str(asset_symbol).upper().strip()
    for prefixo in sorted(TICK_MINIMO.keys(), key=len, reverse=True):
        if simbolo.startswith(prefixo):
            return TICK_MINIMO[prefixo]
    return None

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

def calcular_contratos(entry, stop, asset_symbol, margem, risco_pct, drawdown_maximo,
                       max_contratos=0, min_ticks_stop=None, restante_dia=None):
    """
    Dimensiona a posição com base no plano da mesa:
    - risco em US$ por trade = margem × risco_pct%
    - risco por contrato = distância até o stop (pontos) × valor por ponto do ativo
    - contratos = risco permitido ÷ risco por contrato

    TRÊS TRAVAS, todas determinísticas (nada aqui passa por modelo):

    1) PISO DE STOP. Um stop mais curto que `min_ticks_stop` não dimensiona
       posição nenhuma. Sem esse piso, um stop de 1,87 ponto no MES virava
       30 contratos numa conta de US$1.400 — foi exatamente o que aconteceu.
    2) DRAWDOWN QUE AINDA RESTA HOJE. Antes o teto era o drawdown CHEIO do
       plano, mesmo depois de o dia já ter consumido quase todo ele. Agora,
       quem manda é o que sobrou: `restante_dia`.
    3) TETO DE CONTRATOS. Limite duro por operação, definido pelo trader
       (0 = automático, sem teto fixo).

    Retorna dict com os detalhes para exibir na mensagem. `motivo_limite` diz
    QUAL trava mandou no número — sem isso o trader vê "0 contratos" e não faz
    ideia do porquê.
    """
    vpp = valor_por_ponto_do_ativo(asset_symbol)
    vazio = {"contratos": 0, "risco_usd": 0, "risco_por_contrato": 0,
             "valor_por_ponto": vpp, "pontos_risco": 0, "risco_real_usd": 0,
             "motivo_limite": None, "ticks_risco": None}
    if entry is None or stop is None or entry == stop or not margem:
        vazio["motivo_limite"] = ("Margem não configurada no Plano de Trading."
                                  if not margem else
                                  "Entrada e stop iguais ou ausentes.")
        return dict(vazio)

    try:
        risco_usd_permitido = float(margem) * (float(risco_pct) / 100.0)
    except (TypeError, ValueError):
        vazio["motivo_limite"] = "Margem ou Risco/operação inválidos no plano."
        return dict(vazio)

    motivo = None

    # (2) O teto é o drawdown QUE AINDA RESTA hoje, não o drawdown cheio.
    teto_dd = None
    if restante_dia is not None:
        teto_dd = max(0.0, float(restante_dia))
    elif drawdown_maximo:
        teto_dd = abs(float(drawdown_maximo))
    if teto_dd is not None and risco_usd_permitido > teto_dd:
        risco_usd_permitido = teto_dd
        motivo = (f"limitado pelo drawdown que ainda resta hoje "
                  f"(US${teto_dd:,.2f})")

    pontos_risco = abs(entry - stop)
    risco_por_contrato = pontos_risco * vpp

    # (1) PISO DE STOP — só é aplicado em ativo cujo tick eu conheço.
    tick = tick_do_ativo(asset_symbol)
    ticks_risco = round(pontos_risco / tick, 1) if tick else None
    # min_ticks_stop=None significa SEM PISO — é o que os recálculos de
    # histórico usam, para que uma regra de hoje não reescreva o P&L de ontem.
    # Quem quer a trava é `dimensionar_pelo_plano`, que passa o valor do plano.
    try:
        piso_ticks = int(float(min_ticks_stop or 0))
    except (TypeError, ValueError):
        piso_ticks = 0
    if tick and piso_ticks > 0 and ticks_risco is not None and ticks_risco < piso_ticks:
        fora = dict(vazio)
        fora.update({"pontos_risco": round(pontos_risco, 2),
                     "risco_por_contrato": round(risco_por_contrato, 2),
                     "ticks_risco": ticks_risco,
                     "risco_usd": round(risco_usd_permitido, 2),
                     "motivo_limite": (
                         f"stop curto demais: {ticks_risco:g} tick(s) "
                         f"({pontos_risco:g} ponto(s)), e o piso do plano é "
                         f"{piso_ticks} tick(s). Um stop desse tamanho é ruído "
                         "de mercado, não invalidação de estrutura — dividir o "
                         "risco por ele inflaria a posição.")})
        return fora

    contratos = int(risco_usd_permitido // risco_por_contrato) if risco_por_contrato > 0 else 0
    contratos = max(contratos, 0)

    # (3) TETO DE CONTRATOS por operação.
    try:
        teto_ctr = int(float(max_contratos or 0))
    except (TypeError, ValueError):
        teto_ctr = 0
    if teto_ctr > 0 and contratos > teto_ctr:
        contratos = teto_ctr
        motivo = f"limitado pelo teto de {teto_ctr} contrato(s) do seu plano"

    # Risco REAL da posição = o que os contratos dimensionados de fato arriscam
    # (nunca ultrapassa o teto permitido pelo plano, pois os contratos são
    # arredondados para baixo). É este o número honesto para mostrar ao trader.
    risco_real_usd = round(contratos * risco_por_contrato, 2)

    if contratos == 0 and motivo is None:
        motivo = (f"o risco de 1 contrato (US${risco_por_contrato:,.2f}) já passa "
                  f"do que o plano permite por operação (US${risco_usd_permitido:,.2f}).")

    return {
        "contratos": contratos,
        "risco_usd": round(risco_usd_permitido, 2),   # teto permitido pelo plano
        "risco_real_usd": risco_real_usd,             # risco efetivo dos contratos
        "risco_por_contrato": round(risco_por_contrato, 2),
        "valor_por_ponto": vpp,
        "pontos_risco": round(pontos_risco, 2),
        "ticks_risco": ticks_risco,
        "motivo_limite": motivo,
    }

# Quantas leituras seguidas com o MESMO preço bastam para a leitura deixar de
# valer como base de decisão. Duas podem ser coincidência num mercado parado;
# três já significam que a tela não está atualizando (aba em segundo plano,
# gráfico congelado, mercado fechado) — e o log de 11/08 chegou a TREZE.
CICLOS_PARA_PRECO_CONGELADO = 3

# A entrada sugerida pode estar longe do preço atual — é assim que trabalha uma
# ordem limitada esperando o preço voltar à zona. Mas há um limite: entrada a
# 8,6 R do preço (SELL @7785 com o mercado em 7741,75, no log de 11/08) não é
# ordem, é um desejo. Ela nunca é tocada, o cenário expira, e o trader recebeu
# uma "sugestão" que nunca teve chance. Medimos em MÚLTIPLOS DO RISCO porque é
# a única régua que se ajusta sozinha ao ativo e à volatilidade do momento.
MAX_DISTANCIA_ENTRADA_R = 3.0

def avaliar_distancia_da_entrada(entry, stop, preco, max_r=MAX_DISTANCIA_ENTRADA_R):
    """A entrada está a uma distância operável do preço de agora?

    Função PURA. Devolve (ok, distancia_em_R). `ok` é True quando não dá para
    medir (falta preço, ou entrada e stop iguais) — na dúvida NÃO se barra um
    cenário, porque ausência de medida não é prova de defeito."""
    e, s, p = _num(entry), _num(stop), _num(preco)
    if e is None or s is None or p is None or e == s or p <= 0:
        return True, None
    risco = abs(e - s)
    if risco <= 0:
        return True, None
    dist_r = abs(p - e) / risco
    try:
        limite = float(max_r)
    except (TypeError, ValueError):
        limite = MAX_DISTANCIA_ENTRADA_R
    if limite <= 0:
        return True, round(dist_r, 2)
    return dist_r <= limite, round(dist_r, 2)


# --------------------------------------------------------------------
# ISSO NÃO É UM GRÁFICO
# --------------------------------------------------------------------
# Do log de 12/08. A janela escolhida no seletor era:
#     'Claude — Claude  [outra área de trabalho]'
# e o motor passou VINTE MINUTOS capturando e mandando para o modelo uma
# JANELA DE CONVERSA, ciclo após ciclo, queimando cota e produzindo leitura de
# mercado a partir de texto. Ninguém avisou o trader.
#
# A trava é deterministicamente simples porque a evidência é simples: gráfico
# de futuro tem PREÇO e tem TICKER. Faltando qualquer um dos dois, não há o que
# analisar — e "não há" é dito com essas palavras, nunca convertido em cenário.
#
# O TICKER TAMBÉM PRECISA SER CONHECIDO. Não é preciosismo: `valor_por_ponto_do_ativo`
# cai em VALOR_POR_PONTO_PADRAO (5,0) quando não reconhece o símbolo. Dimensionar
# em cima desse 5,0 chutado é inventar número com cara de cálculo — exatamente o
# que esta ferramenta não pode fazer.
_TICKER_VAZIO = {"", "DESCONHECIDO", "DESCONHECIDA", "N/A", "NA", "NONE",
                 "NULL", "NAO IDENTIFICADO", "NÃO IDENTIFICADO", "INDEFINIDO",
                 "-", "?", "--", "TICKER", "SYMBOL", "ATIVO"}

# Códigos de MÊS de contrato futuro (padrão CME, não é convenção nossa):
# F=jan G=fev H=mar J=abr K=mai M=jun N=jul Q=ago U=set V=out X=nov Z=dez.
# Só depois de exigir isto a trava ficou de pé: 'CLAUDE' começa com 'CL' —
# petróleo WTI — e passava por um `startswith` ingênuo. Foi o teste que pegou.
_MESES_FUTUROS = "FGHJKMNQUVXZ"


def _e_contrato_conhecido(simbolo):
    """O símbolo é uma RAIZ da tabela, sozinha ou seguida do vencimento?

    Aceita MES, MESU6, MESU25, MESU2026 e MES1! (contínuo do TradingView).
    Recusa CLAUDE, CHAT e qualquer palavra que só por acaso comece com uma
    raiz de contrato."""
    s = str(simbolo or "").strip().upper()
    for raiz in sorted(VALOR_POR_PONTO, key=len, reverse=True):
        if not s.startswith(raiz):
            continue
        resto = s[len(raiz):]
        if resto == "":
            return True
        if re.fullmatch(rf"[{_MESES_FUTUROS}]\d{{1,4}}", resto):
            return True
        if re.fullmatch(r"\d{1,2}!", resto):      # MES1! / ES1!
            return True
    return False


# --------------------------------------------------------------------
# O TÍTULO DA JANELA SABE O PREÇO — E ELE NÃO MENTE
# --------------------------------------------------------------------
# Log de 13/08. A janela monitorada chamava-se:
#     'Google Chrome — MESU2026 7.784,00 ▲ +0.23% josevan'
# e o motor mandou para o WhatsApp um cenário inteiro em cima de 7753.25 —
# trinta pontos abaixo, região que o preço já tinha deixado. Pior: 7753.25 é
# EXATAMENTE o número que o modelo tinha inventado no dia anterior ("você
# está com uma posição de venda aberta em 7753.25"). Ele grudou nesse valor.
#
# A trava de preço congelado não pegou porque o valor OSCILAVA (7753 · 7753 ·
# 7788 · 7753), e ela só age com repetição seguida.
#
# Mas a corretora escreve o preço AO VIVO no título da aba. Isso é texto do
# sistema operacional, não leitura de modelo: não tem como ser alucinado. Um
# cenário cujo preço não bate com o título é um cenário sobre outra realidade.
# Um número solto no título, em QUALQUER formato: 7.784,00 (pt-BR),
# 7784.00 (en-US), 7784. A validação de que aquilo é PREÇO vem depois, pelo
# valor — tentar decidir isso na expressão regular foi o que fez a primeira
# versão ignorar '7769.56', que é o formato que a Tradovate usa em inglês.
_RE_PRECO_TITULO = re.compile(r"(?:^|[\s·—-])(\d[\d.,]{2,12}\d)(?=\s|$|[▲▼%])")

# Quanto o preço lido pode diferir do título. Generoso de propósito: título e
# captura são de instantes diferentes. 0,25% no MES são ~19 pontos — muito
# mais que qualquer movimento entre uma leitura e outra, e ainda assim pega
# os 30,75 pontos de erro do caso real.
TOLERANCIA_PRECO_TITULO = 0.0025


def preco_do_titulo(titulo):
    """O preço que a corretora escreve no título da janela, ou None.

    Função PURA. Só aceita número com cara de PREÇO de índice (4 a 6 dígitos
    na parte inteira): '7.784,00' vale, '+0.23' e '2026' do nome do contrato
    não. None significa 'o título não diz o preço' — nunca 'não há preço'."""
    t = str(titulo or "")
    # O ticker traz o ano colado (MESU2026); tirar o ticker evita ler 2026
    # como se fosse cotação.
    t = re.sub(r"\b[A-Z]{2,4}[FGHJKMNQUVXZ]?\d{1,4}\b", " ", t)
    for m in _RE_PRECO_TITULO.finditer(t):
        v = _numero_da_legenda(m.group(1))
        # FAIXA DE PREÇO, NÃO DE PERCENTUAL. O '+0.23%' da variação e o '2026'
        # do vencimento moram no mesmo título; o que os separa de uma cotação
        # é a ordem de grandeza. Abaixo de 100 é variação; acima de 200 mil,
        # não é contrato que esta ferramenta acompanha.
        if v is not None and 100 <= v <= 200_000:
            return v
    return None


def preco_bate_com_o_titulo(preco, titulo, tolerancia=TOLERANCIA_PRECO_TITULO):
    """Devolve (bate, preco_do_titulo). `bate` é True quando não há título com
    preço — ausência de referência nunca reprova uma leitura."""
    do_titulo = preco_do_titulo(titulo)
    p = _num(preco)
    if do_titulo is None or p is None or p <= 0:
        return True, do_titulo
    return abs(p - do_titulo) <= do_titulo * tolerancia, do_titulo


def leitura_e_de_grafico(ativo, preco):
    """A imagem analisada era mesmo um gráfico? Função PURA.

    Devolve (é_grafico, motivo). `motivo` é None quando é gráfico, e uma frase
    pronta para o log/chat quando não é."""
    simbolo = str(ativo or "").strip().upper()
    p = _num(preco)

    if simbolo in _TICKER_VAZIO:
        return False, ("a leitura voltou SEM ticker — não dá para saber qual "
                       "instrumento está na tela")
    if not re.fullmatch(r"[A-Z0-9!]{2,9}", simbolo):
        return False, (f"o que veio no lugar do ticker ('{ativo}') não é "
                       "símbolo de contrato nenhum")
    if p is None or p <= 0:
        return False, (f"a leitura voltou SEM preço para {simbolo} — gráfico "
                       "de futuro sempre tem preço")
    if not _e_contrato_conhecido(simbolo):
        return False, (f"'{simbolo}' não está na tabela de contratos, então eu "
                       "não sei quanto vale um ponto dele — e sem isso qualquer "
                       "dimensionamento meu seria chute")
    return True, None


def avisos_do_plano(plano):
    """O que os números do plano IMPLICAM, dito em voz alta. Função pura.

    O plano da conta 1 no pregão de 10/08 era: Margem US$1.400 · Drawdown
    US$1.400 · Risco/operação 20%. Ninguém tinha dito ao trader o que isso
    significa em sequência: 20% de 1.400 são US$280 por trade, e o drawdown de
    US$1.400 acaba em CINCO stops. Com o teto de 6 operações por dia, o plano
    autoriza perder a conta inteira antes de bater o teto de operações.

    Nada aqui é opinião nem recomendação: é aritmética sobre os números que o
    próprio trader digitou. Se ele quer operar assim, é decisão dele — mas
    sabendo."""
    def _f(campo, padrao=0.0):
        try:
            return float(plano.get(campo, padrao) or 0)
        except (TypeError, ValueError):
            return padrao

    avisos = []
    margem = _f("margem")
    risco_pct = _f("risco_pct", 1.0)
    drawdown = abs(_f("drawdown_maximo"))
    max_ops = int(_f("max_operacoes_dia"))
    max_stops = int(_f("max_stops_seguidos"))

    risco_trade = margem * (risco_pct / 100.0)
    if margem > 0 and drawdown > 0 and risco_trade > 0:
        stops_ate_o_limite = drawdown / risco_trade
        if stops_ate_o_limite <= 6:
            avisos.append(
                f"⚠️ PLANO: com risco de {risco_pct:g}% sobre uma margem de "
                f"US${margem:,.2f}, cada operação arrisca US${risco_trade:,.2f}. "
                f"O seu drawdown máximo é US${drawdown:,.2f} — ou seja, "
                f"{stops_ate_o_limite:.1f} stop(s) encerram o seu dia."
                + (f" O seu teto é de {max_ops} operações por dia: o limite de "
                   "perda chega ANTES do limite de operações."
                   if max_ops and stops_ate_o_limite < max_ops else "")
                + (f" A pausa por stops seguidos ({max_stops}) entra antes, e é "
                   "hoje a sua principal proteção."
                   if 0 < max_stops < stops_ate_o_limite else ""))
    if drawdown > 0 and margem > 0 and drawdown >= margem:
        avisos.append(
            f"⚠️ PLANO: o seu drawdown máximo (US${drawdown:,.2f}) é igual ou "
            f"maior que a margem (US${margem:,.2f}). Isso quer dizer que o "
            "limite de perda do dia só é atingido quando a conta acabou — ele "
            "não está protegendo nada antes disso.")
    if _f("min_ticks_stop") <= 0:
        avisos.append(
            "ℹ️ PLANO: 'Mín. ticks de stop' está em 0, ou seja, desligado. Um "
            "stop muito curto vindo da leitura vai dimensionar uma posição "
            "grande — foi assim que um stop de 1,87 ponto no MES virou dezenas "
            "de contratos.")
    return avisos

def avaliar_piso_de_qualidade(acao, entry, stop, tp1, tp2, rr_minimo,
                              probabilidade, probabilidade_minima):
    """O cenário passa no piso da casa? Função PURA — é ela que decide se uma
    leitura vira sugestão, então precisa ser testável fora da interface.

    Devolve dict com:
      ok           -> passou nos DOIS pisos (R:R e probabilidade)
      rr           -> o R:R que vale para o piso
      alvo_do_piso -> 1 ou 2: qual alvo pagou o piso (0 = não há alvo)
      rr_tp1/rr_tp2-> os dois R:R medidos, para o log e para o aviso de gestão

    POR QUE O 2º ALVO ENTROU NA CONTA: no pregão de 10/08 saíram sete descartes
    seguidos de MESU6 (1:0,55 · 1:0,66 · 1:1,00 · 1:1,19 · 1:1,74 · 1:1,91 ·
    1:1,94) contra um piso de 1:2, e em parte deles o 2º alvo — o de liquidez
    cheia — pagava o piso com folga. O cenário ia para o lixo por causa da
    PARCIAL, não por causa da estrutura. Isso não afrouxa o piso: mede contra o
    alvo que de fato paga, e obriga a sugestão a dizer que foi o segundo.
    """
    entry = entry or 0
    stop = stop or 0
    tp1 = tp1 or 0
    tp2 = tp2 or 0
    risco = abs(entry - stop)
    rr_tp1 = (abs(tp1 - entry) / risco) if (risco and tp1) else 0.0
    rr_tp2 = (abs(tp2 - entry) / risco) if (risco and tp2) else 0.0

    alvo_do_piso = 1 if tp1 else (2 if tp2 else 0)
    rr = rr_tp1 if tp1 else rr_tp2

    if rr < rr_minimo and tp2 and risco and acao in ("BUY", "SELL"):
        # Alvo do lado ERRADO da entrada não é alvo — é preço atrás das costas.
        lado_ok = (tp2 > entry) if acao == "BUY" else (tp2 < entry)
        if lado_ok and rr_tp2 >= rr_minimo:
            rr = rr_tp2
            alvo_do_piso = 2

    return {
        "ok": bool(rr >= rr_minimo and probabilidade >= probabilidade_minima),
        "rr": rr,
        "alvo_do_piso": alvo_do_piso,
        "rr_tp1": rr_tp1,
        "rr_tp2": rr_tp2,
    }

def dimensionar_pelo_plano(entry, stop, ativo, plano=None, restante_dia=None):
    """Atalho que junta plano + travas — para nenhum ponto do código precisar
    lembrar de passar teto de contratos, piso de ticks e drawdown restante um
    por um (foi assim que o dimensionamento acabou com regras diferentes em
    lugares diferentes)."""
    plano = plano if plano is not None else plano_da_conta_ativa()
    if restante_dia is None:
        try:
            restante_dia = drawdown_restante_hoje(plano)
        except Exception:
            restante_dia = None
    return calcular_contratos(
        entry, stop, ativo,
        plano.get("margem", 0), plano.get("risco_pct", 1.0),
        plano.get("drawdown_maximo", 0),
        max_contratos=plano.get("max_contratos", 0),
        min_ticks_stop=plano.get("min_ticks_stop", MIN_TICKS_STOP_PADRAO),
        restante_dia=restante_dia,
    )

def calcular_r_multiplo(direcao, entry, stop, preco_saida):
    risco_pontos = abs(entry - stop)
    if risco_pontos == 0:
        return 0.0
    if direcao == "BUY":
        ganho_pontos = preco_saida - entry
    else:
        ganho_pontos = entry - preco_saida
    return round(ganho_pontos / risco_pontos, 2)

def salvar_resultado_performance(direcao, entry, stop, tp, preco_saida, resultado,
                                  ativo="DESCONHECIDO", confluencias=None):
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
        # Guardadas para o APRENDIZADO: é assim que o robô descobre QUAIS
        # padrões funcionam de verdade nas SUAS operações.
        "confluencias": [str(c)[:60] for c in (confluencias or [])][:8],
        "hora": time.strftime('%H'),
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

def lancar_resultado_do_dia(dia_pregao, valor, contratos=1, ativo="LANCAMENTO",
                            cfg=None, lista=None):
    """Grava no diário o RESULTADO FECHADO de um dia, em dólares.

    Nasceu de 17/08, 19:59, palavras dele: "às vezes faço operações fora das
    sugestões, então acho que uma forma de incluir o resultado do dia no diário
    seria viável".

    O formulário que existia exigia entrada, stop e preço de saída para deduzir
    o resultado. Quem operou cinco vezes na mão e sabe só que fechou o dia em
    +54 não tem esses números — e, obrigado a inventá-los, produz um registro
    que MENTE sobre os preços para acertar o total.

    Aqui o valor é o dado. Não há preço fingido: entrada e saída ficam nulas, e
    o P&L é exatamente o que ele digitou.

    O CARIMBO é o ponto delicado, e é o que perdia o dinheiro dele: com pregão
    19:00→17:59, um lançamento feito às 18h pertence ao pregão da VÉSPERA. Por
    isso a data passa por `carimbo_para_o_pregao`, que devolve um horário que a
    ferramenta relê como sendo do dia pedido."""
    carimbo = carimbo_para_o_pregao(dia_pregao, cfg)
    if not carimbo:
        return None
    try:
        valor = round(float(valor), 2)
    except (TypeError, ValueError):
        return None
    lista = carregar_posicoes() if lista is None else lista
    pos = {
        "id": _novo_id_posicao(lista),
        "conta_id": conta_ativa_id(),
        # Origem própria: não é sugestão acatada nem posição lida da corretora.
        # O comparativo do ciclo usa a origem para não misturar as três coisas.
        "origem": "RESULTADO_DIA",
        "direcao": "BUY" if valor >= 0 else "SELL",
        "ativo": ativo or "LANCAMENTO",
        # Sem preço FINGIDO. Um lançamento de resultado não tem entrada nem
        # saída, e escrever números aqui contaminaria toda estatística de
        # preço/ticks que lê o diário.
        "entry": None, "stop": None, "tp1": None, "tp2": None,
        "contratos": max(int(contratos or 1), 1),
        "vpp": None,
        "status": "FECHADA",
        "execucao": "CONFIRMADA",
        "confirmacoes_entrada": 0,
        "preco_atual": None,
        "pnl_atual": 0.0,
        "data_criacao": carimbo,
        "data_abertura": carimbo,
        "data_fechamento": carimbo,
        "pnl_final": valor,
    }
    lista.append(pos)
    salvar_posicoes(lista)
    return pos


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

def atualizar_posicoes_com_preco(preco, ativo=None, exigir_confirmacao_plataforma=False,
                                  preco_confiavel=False):
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

            # QUAL PREÇO ESTAMOS USANDO?
            #  • preco_confiavel=True  -> veio do DOM da corretora (número exato,
            #    amostrado a cada poucos segundos). Tocou o nível = executou.
            #    Sem margem e sem 2ª confirmação: era isso que fazia a ordem
            #    "passar batido" quando o preço tocava entre duas análises.
            #  • preco_confiavel=False -> veio da IA lendo a IMAGEM, de 5 em 5
            #    min. Aí sim exige folga e leitura repetida, porque um erro de
            #    leitura não pode abrir posição.
            if preco_confiavel:
                margem, confirmacoes_exigidas = 0.0, 1
            else:
                risco = abs(pos["entry"] - pos["stop"]) if pos.get("stop") else 0
                margem, confirmacoes_exigidas = risco * MARGEM_CONFIRMA_FILL, CONFIRMACOES_FILL
            passou = (direcao == "BUY" and preco <= pos["entry"] - margem) or \
                      (direcao == "SELL" and preco >= pos["entry"] + margem)
            if not passou:
                pos["confirmacoes_entrada"] = 0
                continue
            pos["confirmacoes_entrada"] = pos.get("confirmacoes_entrada", 0) + 1
            if pos["confirmacoes_entrada"] < confirmacoes_exigidas:
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
              "corrigidas": 0, "confirmadas": 0, "fundidas": 0}
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
            observados.discard(ativo)     # leitura suspeita não vale como "vi"
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
            # CRÍTICO: sair daqui deixando o ativo em `observados` fazia o app
            # concluir "vi o ativo e não há posição" — ou seja, tratava uma
            # leitura ILEGÍVEL como prova de que você está zerado. Era isso que
            # devolvia para PENDENTE uma ordem já executada e zerava o P&L real
            # ("↩️ Correção: ... NÃO está executada na plataforma"), fazendo o
            # dashboard do Plano de Trading parar de acompanhar a operação.
            # Não conseguir ler é AUSÊNCIA de informação, nunca uma conclusão.
            observados.discard(ativo)
            log(f"⚠️ Ignorei '{ativo}': a plataforma mostrou a quantidade, mas nem "
                "preço médio nem P&L vieram legíveis (não vou inventar número). "
                "Não concluí nada sobre a posição — o que já estava registrado "
                "continua de pé.")
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
            # Corrige NA HORA, de propósito: manter uma posição "aberta" que a
            # corretora não tem seria inventar P&L. Isto só é seguro porque uma
            # leitura ILEGÍVEL não chega até aqui — ela sai de `observados` lá
            # em cima, e ausência de leitura nunca vira conclusão.
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
            # ---- UMA POSIÇÃO REAL, UM REGISTRO ----
            # O DEFEITO (log de 11/08): às 16:05 a leitura da tela criou um
            # registro PLATAFORMA de SELL MESU6 40 ctr. Às 16:10 o trader acatou
            # uma sugestão e nasceu um registro ROBO, PENDENTE. Às 16:15 essa
            # ordem foi CONFIRMADA — contra a MESMA posição de 40 contratos que
            # já estava no diário como PLATAFORMA.
            #
            # A partir daí havia DOIS registros para UMA posição. Os dois
            # fecharam, e o diário somou o resultado duas vezes:
            #     🔻 encerrada na plataforma: SELL MESU6 — US$-600,00
            #     📕 FECHADA no diário:       SELL MESU6 — US$-1.176,00
            # Resultado do dia, win rate, drawdown e o freio de perda passaram
            # todos a trabalhar com número inflado.
            #
            # Quem sobrevive é o registro do ROBÔ: ele tem o elo com a sugestão
            # (sinal_id), o stop, o alvo e o dimensionamento planejado. O
            # registro da PLATAFORMA vira uma ANOTAÇÃO fundida — não some do
            # arquivo (histórico não se apaga), mas sai da contagem.
            gemeas = [g for g in lista
                      if g is not pos
                      and g.get("origem") == "PLATAFORMA"
                      and g.get("conta_id") == conta
                      and str(g.get("ativo", "")).upper() == nome
                      and g.get("status") in ("ABERTA", "PENDENTE")
                      and g.get("direcao") == pos.get("direcao")]
            for g in gemeas:
                g["status"] = "FUNDIDA"
                g["fundida_em"] = pos.get("id")
                g["pnl_final"] = 0.0        # o resultado é contado no registro do robô
                g["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
                resumo["fundidas"] += 1
                log(f"🔗 {pos.get('direcao')} {nome}: esta posição já estava no "
                    f"diário como leitura da plataforma. É a MESMA operação — "
                    "fundi os dois registros num só para o resultado não ser "
                    "contado em dobro.")

            # O QUE FOI PLANEJADO, antes de ser sobrescrito pelo que de fato
            # aconteceu. Sem guardar isto, a divergência some sem deixar rastro.
            entry_plan = _num(pos.get("entry"))
            ctr_plan = int(pos.get("contratos") or 0)
            stop_plan = _num(pos.get("stop"))

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
            # Guarda o plano ao lado do executado — é o que permite o diário
            # mostrar depois "planejado X, executado Y".
            pos["entry_planejado"] = entry_plan
            pos["contratos_planejados"] = ctr_plan or None
            resumo["confirmadas"] += 1
            log(f"✅ Execução CONFIRMADA pela plataforma: {pos.get('direcao')} "
                f"{pos.get('ativo')} @ {pos.get('entry')} "
                f"({pos['contratos']} contrato(s)).")

            # ---- DIVERGÊNCIA ENTRE O QUE FOI SUGERIDO E O QUE FOI EXECUTADO ----
            # Isto aconteceu de verdade: a sugestão dizia 14 contratos @ 7773,25
            # e a execução veio 30 contratos @ 7777,1. O app engolia a diferença
            # em silêncio e passava a acompanhar uma posição com MAIS DO DOBRO do
            # risco que o plano tinha autorizado. Silêncio aqui é o pior lugar
            # possível para silêncio.
            avisos = []
            ctr_real = pos["contratos"]
            if ctr_plan and ctr_real != ctr_plan:
                fator = ctr_real / ctr_plan
                avisos.append(
                    f"quantidade: o plano dimensionou {ctr_plan} contrato(s) e "
                    f"a plataforma executou {ctr_real}"
                    + (f" — {fator:.1f}× o risco autorizado" if fator > 1 else
                       " — abaixo do dimensionado"))
            entry_real = _num(pos.get("entry"))
            if entry_plan and entry_real and stop_plan and entry_plan != stop_plan:
                desvio = abs(entry_real - entry_plan)
                risco_pts = abs(entry_plan - stop_plan)
                if risco_pts > 0 and desvio >= risco_pts * 0.20:
                    avisos.append(
                        f"preço: sugerido {entry_plan:g}, executado {entry_real:g} "
                        f"({desvio:g} ponto(s) de diferença = "
                        f"{desvio / risco_pts * 100:.0f}% do risco do trade). "
                        "O stop e o alvo da sugestão foram calculados a partir "
                        f"de {entry_plan:g} — a partir de {entry_real:g} o R:R é outro")
            if avisos:
                risco_agora = round(
                    abs((entry_real or 0) - stop_plan) * pos.get("vpp",
                        valor_por_ponto_do_ativo(pos.get("ativo"))) * ctr_real, 2
                ) if (stop_plan and entry_real) else None
                texto = ("⚠️ A EXECUÇÃO NÃO BATE COM A SUGESTÃO — "
                         + "; ".join(avisos) + ".")
                if risco_agora is not None:
                    texto += (f" Risco real desta posição até o stop "
                              f"{stop_plan:g}: US${risco_agora:,.2f}.")
                log(texto)
                pos["divergencia_execucao"] = texto

        elif pos["status"] == "ABERTA" and mesma_direcao:
            # Posição do robô que a corretora confirma: P&L real vem de lá.
            pos["execucao"] = "CONFIRMADA"
            if atual["pnl"] is not None:
                pos["pnl_atual"] = round(atual["pnl"], 2)
            if atual["preco"] is not None:
                pos["preco_atual"] = atual["preco"]

        elif (pos["status"] == "ABERTA" and not mesma_direcao
                and pos.get("execucao") == "CONFIRMADA"):
            # POSIÇÃO DO ROBÔ QUE SUMIU DA PLATAFORMA = você encerrou lá.
            #
            # Antes NÃO havia este ramo: uma posição do robô já confirmada que
            # desaparecia da corretora ficava ABERTA no diário para sempre, e
            # só era encerrada se o preço batesse no stop/alvo registrados. Quem
            # fechava na mão saía da plataforma e continuava "em operação" aqui.
            # Isso não aparecia antes porque o registro DUPLICADO da plataforma
            # encerrava e dava a impressão de que o diário tinha fechado — com
            # o número errado, e ainda por cima em dobro.
            #
            # O resultado realizado é o ÚLTIMO P&L que a PRÓPRIA corretora
            # reportou: dado real dela, não estimativa nossa.
            pos["status"] = "FECHADA"
            pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
            pos["pnl_final"] = round(pos.get("pnl_atual") or 0.0, 2)
            resumo["encerradas"] += 1
            log(f"🔻 Posição encerrada na plataforma: {pos.get('direcao')} "
                f"{pos.get('ativo')} — resultado US${pos['pnl_final']:+.2f} "
                "(registrado no diário, uma única vez).")

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
        # POR QUE ESSA POSIÇÃO APARECE COM "stop None · alvo None": ela não veio
        # de uma sugestão minha, veio da plataforma. A leitura da tela dá ativo,
        # direção, quantidade e preço — não dá os níveis do bracket. Inventar um
        # stop aqui seria inventar risco. Mas ficar calado deixava o trader
        # olhando "None" sem saber o que fazer com aquilo.
        log(f"ℹ️ {direcao} {ativo}: não tenho o stop nem o alvo dessa posição "
            "(ela não saiu de uma sugestão minha e a plataforma não expõe o "
            "bracket na tela). Sem esses dois números eu não calculo o risco em "
            "US$ nem aviso quando a estrutura virar contra ela. Me diga no chat, "
            f"por exemplo: 'o stop do {ativo} é 7760 e o alvo é 7800'.")

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
    cfg = carregar_config()
    for pos in lista:
        if pos.get("status") == "FECHADA" and pos.get("pnl_final") is not None:
            # O DIA é o do PREGÃO, não o do calendário: com o pregão virando
            # às 19:00, a operação da madrugada pertence ao dia anterior. Sem
            # isso, o gráfico da curva quebrava um pregão em dois.
            quando = _hora_do_registro(pos.get("data_fechamento"))
            dia = (data_do_pregao(quando, cfg) if quando
                   else (pos.get("data_fechamento") or "")[:10])
            if dia:
                por_dia[dia] = por_dia.get(dia, 0.0) + pos["pnl_final"]
    hoje = data_do_pregao(cfg=cfg)
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

def _hora_do_registro(txt_data):
    """'05/08/2026 14:08' -> datetime. Devolve None se o formato não bater."""
    try:
        return datetime.datetime.strptime((txt_data or "").strip(), '%d/%m/%Y %H:%M')
    except (ValueError, TypeError):
        return None

# --------------------------------------------------------------------
# O DIA DO PREGÃO NÃO É O DIA DO CALENDÁRIO
# --------------------------------------------------------------------
# Do log de 12/08, 19:59, ele configurou: "o início do dia para essa conta é
# às 19hs até as 17:59". A ferramenta gravou certo e confirmou. E às 20:01,
# com o pregão NOVO já rodando havia uma hora, o freio respondeu:
#
#     "🛑 você já fechou 6 operações hoje, que é o teto do seu plano (6)"
#
# Aquelas seis operações eram do pregão ANTERIOR. Ele reclamou três vezes
# ("mas o dia já virou", "era para contabilizar no plano de trading", "vire o
# ciclo do dia") e chegou a gravar como lição.
#
# A causa: `hoje` era `time.strftime('%d/%m/%Y')` — o dia do CALENDÁRIO. Para
# quem opera índice americano de madrugada, meia-noite não é a virada de nada.
# O pregão dele começa às 19:00 e atravessa a meia-noite; o dia de operação
# vira às 19:00, não às 00:00.
#
# Não era um botão que faltava: era esta função.
def data_do_pregao(quando=None, cfg=None):
    """A data do PREGÃO a que este instante pertence, no formato dd/mm/aaaa.

    Com pregão normal (09:00→17:00) é o próprio dia do calendário. Com pregão
    que ATRAVESSA A MEIA-NOITE (19:00→17:59), tudo que acontece antes das
    19:00 ainda pertence ao pregão que começou às 19:00 do dia anterior."""
    agora = quando or datetime.datetime.now()
    try:
        c = cfg if cfg is not None else carregar_config()
        ini = str(c.get("hora_inicio", PADRAO_CONFIG_APP["hora_inicio"]))
        fim = str(c.get("hora_fim", PADRAO_CONFIG_APP["hora_fim"]))
        h_ini, m_ini = (int(x) for x in ini.split(":")[:2])
        h_fim, m_fim = (int(x) for x in fim.split(":")[:2])
    except Exception:
        return agora.strftime('%d/%m/%Y')
    # Pregão que não vira o dia: o calendário serve.
    if (h_ini, m_ini) <= (h_fim, m_fim):
        return agora.strftime('%d/%m/%Y')
    # Vira o dia: antes do horário de início, ainda é o pregão de ontem.
    if (agora.hour, agora.minute) < (h_ini, m_ini):
        return (agora - datetime.timedelta(days=1)).strftime('%d/%m/%Y')
    return agora.strftime('%d/%m/%Y')


def minutos_ate_o_fim_do_pregao(quando=None, cfg=None):
    """Quantos minutos faltam até a hora de encerramento configurada.

    Devolve 0 quando o pregão já fechou, e None quando não deu para ler o
    horário — nunca um palpite. Lida com o pregão que ATRAVESSA A MEIA-NOITE
    (19:00→17:59): às 22h de terça, o fim é às 17:59 de quarta."""
    agora = quando or datetime.datetime.now()
    try:
        c = cfg if cfg is not None else carregar_config()
        ini = str(c.get("hora_inicio", PADRAO_CONFIG_APP["hora_inicio"]))
        fim = str(c.get("hora_fim", PADRAO_CONFIG_APP["hora_fim"]))
        h_ini, m_ini = (int(x) for x in ini.split(":")[:2])
        h_fim, m_fim = (int(x) for x in fim.split(":")[:2])
    except Exception:
        return None
    fecha = agora.replace(hour=h_fim, minute=m_fim, second=0, microsecond=0)
    if (h_ini, m_ini) > (h_fim, m_fim) and \
            (agora.hour, agora.minute) >= (h_ini, m_ini):
        # Pregão noturno já iniciado: o fechamento é no dia seguinte.
        fecha += datetime.timedelta(days=1)
    return max(0, int((fecha - agora).total_seconds() // 60))


def _combinacoes(n, k):
    """C(n,k) sem depender do math.comb (Python antigo do cliente)."""
    if k < 0 or k > n:
        return 0
    r = 1
    for i in range(k):
        r = r * (n - i) // (i + 1)
    return r


def chance_de_bater_a_meta(falta, operacoes, taxa_acerto, ganho_medio,
                           perda_media):
    """A chance de somar `falta` em `operacoes` restantes. Binomial EXATA.

    POR QUE ISTO É CÓDIGO E NÃO PROMPT. Em 13/08 às 16:01 ele perguntou
    "o dia encerra às 17:59, como estamos de probabilidade de bater a meta de
    hoje até lá?" e recebeu "não tenho dados suficientes para prever". A
    ferramenta tinha TODOS os dados: a meta está no plano, o resultado do dia
    está no diário, o horário de fechamento está na configuração. Quem não
    tinha os dados era o modelo — e ele tentou consertar isso ensinando uma
    lição, o que nunca funcionaria: lição vira texto no prompt, não vira
    acesso ao diário.

    O QUE ESTE NÚMERO É, E O QUE ELE NÃO É. É a probabilidade de, em N
    operações do MESMO tamanho médio das de hoje, sair um número de acertos
    suficiente — dada a taxa de acerto DELE hoje. Nada aqui é estimado: os
    quatro números entram de fora, medidos. O que é SUPOSIÇÃO, e precisa ser
    dita junto do resultado, é que as próximas operações se pareçam com as de
    hoje e sejam independentes entre si. O mercado não assinou esse contrato.

    Devolve (probabilidade_0a100, acertos_necessarios, operacoes) ou None
    quando falta número para fazer a conta. None é resposta legítima; um
    número inventado não é."""
    try:
        falta = float(falta)
        n = int(operacoes)
        p = float(taxa_acerto)
        g = float(ganho_medio)
        perda = abs(float(perda_media))
    except (TypeError, ValueError):
        return None
    if n < 0 or not (0.0 <= p <= 1.0) or g <= 0:
        return None
    if falta <= 0:
        return (100.0, 0, n)
    if n == 0:
        return (0.0, None, 0)
    # k acertos e (n-k) perdas somam k*g - (n-k)*perda. Isso >= falta em
    # k >= (falta + n*perda) / (g + perda).
    denominador = g + perda
    if denominador <= 0:
        return None
    exato = (falta + n * perda) / denominador
    k_min = int(exato)
    if k_min < exato:
        k_min += 1                      # teto, sem depender do math.ceil
    if k_min > n:
        return (0.0, k_min, n)          # nem acertando tudo dá
    if k_min <= 0:
        return (100.0, 0, n)
    prob = 0.0
    for k in range(k_min, n + 1):
        prob += _combinacoes(n, k) * (p ** k) * ((1 - p) ** (n - k))
    return (round(min(100.0, max(0.0, prob * 100)), 1), k_min, n)


def operacoes_que_ainda_cabem(minutos_restantes, operacoes_feitas,
                              minutos_decorridos, teto_do_dia=None):
    """Quantas operações ainda cabem, no RITMO REAL de hoje.

    Não é chute: sai da cadência que ele mesmo imprimiu (minutos decorridos ÷
    operações feitas) e respeita o teto de operações do plano. Devolve None
    quando ainda não há operação nenhuma para medir a cadência — sem uma
    operação fechada não existe ritmo, e inventar um seria inventar a conta
    inteira que vem depois."""
    try:
        minutos_restantes = max(0, int(minutos_restantes))
        operacoes_feitas = int(operacoes_feitas)
        minutos_decorridos = max(0, int(minutos_decorridos))
    except (TypeError, ValueError):
        return None
    if operacoes_feitas <= 0 or minutos_decorridos <= 0:
        return None
    cadencia = minutos_decorridos / float(operacoes_feitas)
    cabem = int(minutos_restantes // cadencia)
    if teto_do_dia:
        try:
            cabem = min(cabem, max(0, int(teto_do_dia) - operacoes_feitas))
        except (TypeError, ValueError):
            pass
    return max(0, cabem)


def pregao_vira_o_dia(cfg=None):
    """O pregão configurado atravessa a meia-noite?"""
    try:
        c = cfg if cfg is not None else carregar_config()
        ini = [int(x) for x in str(c.get("hora_inicio",
               PADRAO_CONFIG_APP["hora_inicio"])).split(":")[:2]]
        fim = [int(x) for x in str(c.get("hora_fim",
               PADRAO_CONFIG_APP["hora_fim"])).split(":")[:2]]
        return tuple(ini) > tuple(fim)
    except Exception:
        return False


def operacoes_fechadas_hoje():
    """Operações da conta ativa fechadas NESTE PREGÃO, em ordem cronológica.

    'Neste pregão', não 'neste dia do calendário' — ver data_do_pregao."""
    hoje = data_do_pregao()
    cfg = carregar_config()
    # VIRADA MANUAL: ele pode encerrar o dia ANTES da hora configurada, com
    # 'vire o dia'. É um CORTE no tempo, não um rótulo de data — por isso mora
    # aqui e não em data_do_pregao, que precisa devolver dd/mm/aaaa comparável.
    # Vale 24h: uma virada de ontem não pode continuar mandando hoje.
    corte = _hora_do_registro(cfg.get("virada_manual"))
    if corte and (datetime.datetime.now() - corte) >= datetime.timedelta(hours=24):
        corte = None

    def e_deste_pregao(p):
        # Cada operação é mapeada para O PREGÃO DELA. Comparar o texto da data
        # com o rótulo de hoje daria errado justamente no caso que importa:
        # uma operação fechada às 10:00 de 13/08 pertence ao pregão de 12/08
        # quando o dia começa às 19:00 — e o texto dela diz "13/08".
        quando = _hora_do_registro(p.get("data_fechamento"))
        if quando is None:
            return (p.get("data_fechamento") or "").startswith(hoje)
        if corte and quando < corte:
            return False          # é do dia que ele encerrou na mão
        return data_do_pregao(quando, cfg) == hoje

    fechadas = [p for p in posicoes_do_ciclo()
                if p.get("status") == "FECHADA"
                and p.get("pnl_final") is not None
                and e_deste_pregao(p)]
    fechadas.sort(key=lambda p: _hora_do_registro(p.get("data_fechamento"))
                  or datetime.datetime.min)
    return fechadas

def drawdown_restante_hoje(plano=None):
    """Quanto do drawdown do dia AINDA SOBRA — realizado + aberto já descontados.

    Existe porque o dimensionamento usava o drawdown CHEIO como teto o dia
    inteiro: com drawdown de US$1.400 e risco de 20%, uma operação continuava
    autorizada a arriscar US$280 mesmo depois de o dia já ter perdido US$1.177.
    A trava que o trader configurou virava decorativa exatamente no momento em
    que ela deveria apertar. Devolve None quando não há drawdown configurado
    (nesse caso não existe teto para calcular — e None não é zero)."""
    plano = plano if plano is not None else plano_da_conta_ativa()
    try:
        drawdown = abs(float(plano.get("drawdown_maximo", 0) or 0))
    except (TypeError, ValueError):
        return None
    if drawdown <= 0:
        return None
    try:
        realizado = sum(p["pnl_final"] for p in operacoes_fechadas_hoje())
        aberto = sum(p.get("pnl_atual", 0) or 0 for p in posicoes_do_ciclo()
                     if p.get("status") == "ABERTA")
    except Exception:
        return drawdown
    usado = min(0.0, realizado + aberto)      # lucro NÃO aumenta o limite
    return max(0.0, drawdown - abs(usado))

def freio_de_sugestoes(plano=None, agora=None):
    """PROTEÇÃO CONTRA SEQUÊNCIA DE STOPS.

    Responde a uma pergunta só: o robô pode emitir uma sugestão nova AGORA?

    Por que isto existe: o motor analisa o gráfico a cada poucos minutos e, num
    mercado lateral, ele reencontra o mesmo cenário indefinidamente. O trader
    recebe sugestão atrás de sugestão, acata, toma stop, recebe outra — e o dia
    vira uma sequência de perdas que nenhum setup individual explica. Um trader
    de mesa tem limite de perda diária e para depois de dois stops seguidos.
    A ferramenta passa a ter o mesmo.

    É tudo DETERMINÍSTICO e lido do diário real da conta: nenhuma decisão aqui
    passa pelo modelo, e nenhum número é estimado.

    Devolve (pode_sugerir: bool, motivo: str|None).
    """
    plano = plano if plano is not None else plano_da_conta_ativa()
    agora = agora or datetime.datetime.now()

    def _int(campo, padrao):
        try:
            return int(float(plano.get(campo, padrao)))
        except (TypeError, ValueError):
            return padrao

    max_stops = _int("max_stops_seguidos", 2)
    cooldown_min = _int("cooldown_stop_min", 30)
    max_ops = _int("max_operacoes_dia", 6)

    fechadas = operacoes_fechadas_hoje()

    # 1) TETO DE PERDA DIÁRIA — o limite que o próprio trader configurou.
    #    Batido o drawdown do plano, o dia acabou. Continuar sugerindo depois
    #    disso é o caminho para o trader tentar recuperar no impulso.
    try:
        drawdown = float(plano.get("drawdown_maximo", 0) or 0)
    except (TypeError, ValueError):
        drawdown = 0.0
    if drawdown > 0:
        realizado = sum(p["pnl_final"] for p in fechadas)
        aberto = sum(p.get("pnl_atual", 0) or 0 for p in posicoes_do_ciclo()
                     if p.get("status") == "ABERTA")
        if (realizado + aberto) <= -abs(drawdown):
            return False, (
                f"o prejuízo de hoje (US${realizado + aberto:,.2f}) bateu o "
                f"drawdown máximo do plano (US${abs(drawdown):,.2f}). Não vou "
                "sugerir mais nada hoje — esse limite existe para proteger a "
                "conta, e ele já foi usado.")

    # 2) TETO DE OPERAÇÕES NO DIA — excesso de trade é o que corrói o resultado.
    if max_ops > 0 and len(fechadas) >= max_ops:
        return False, (
            f"você já fechou {len(fechadas)} operações hoje, que é o teto do seu "
            f"plano ({max_ops}). Parar aqui é decisão de gestão, não de mercado.")

    # 3) STOPS SEGUIDOS — depois de N stops em sequência, silêncio por um tempo.
    if max_stops > 0 and cooldown_min > 0:
        seguidos, ultimo_stop = 0, None
        for p in reversed(fechadas):
            if p["pnl_final"] < 0:
                seguidos += 1
                ultimo_stop = ultimo_stop or _hora_do_registro(p.get("data_fechamento"))
            else:
                break
        if seguidos >= max_stops and ultimo_stop:
            faltam = cooldown_min - (agora - ultimo_stop).total_seconds() / 60.0
            if faltam > 0:
                return False, (
                    f"foram {seguidos} stops seguidos. Estou em pausa por mais "
                    f"{faltam:.0f} min antes de sugerir de novo — depois de dois "
                    "stops, o problema deixa de ser o setup e passa a ser o "
                    "ritmo. Se quiser voltar antes, mude 'stops seguidos' ou "
                    "'pausa após stop' no Plano de Trading.")
    return True, None

# ====================================================================
# REGISTRO DE MODELOS — o motor e a TIGER usam a MESMA lista
# ====================================================================
# O DEFEITO QUE ISTO CORRIGE (pregão de 06-07/08): o motor analisava o gráfico
# normalmente de 5 em 5 minutos, caindo para os modelos de reserva
# (gemini-flash-lite-latest, gemini-3.1-flash-lite...), enquanto a TIGER, no
# chat, respondia "a cota da sua chave estourou" para o MESMO print, no MESMO
# minuto. Não era desculpa: eram DUAS listas diferentes. O motor tentava 14
# modelos, com cooldown por modelo; o chat tinha 5 fixos no código (4 quando
# havia anexo), todos da família 2.0 — justamente a que estava esgotada o dia
# inteiro. Acabada a lista curta, ela desistia.
#
# Agora existe UM registro só: a lista descoberta na conta, o cooldown de cada
# modelo e os descontinuados. Quem descobre que um modelo está sem cota avisa o
# outro — o motor poupa a TIGER e a TIGER poupa o motor.
_MODELOS_PREFERENCIA = [
    "gemini-2.0-flash",          # estável, rápido, amplamente disponível
    "gemini-2.0-flash-001",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-2.0-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
]
COOLDOWN_COTA_SEG = 900        # 429 (cota esgotada): estaciona por 15 min
COOLDOWN_SOBRECARGA_SEG = 120  # 503/timeout: estaciona por 2 min

# QUANTO TEMPO A CONVERSA PODE FICAR ESPERANDO A GEMINI.
# "não responde perguntas rápido, está demorando muito pensando" — 14/08.
# A conta antiga: onze modelos × até quatro configurações × 60 s de prazo.
# Com a cota estourada, isso passava de dez minutos ANTES de ela chegar na
# base própria — que responde na hora, do disco, sem cota. Ele ficava olhando
# "✳ pensando…" com a resposta pronta e presa atrás de uma fila.
#
# O CORTE É NO TOTAL, NÃO NA CHAMADA. Baixar o prazo individual seria repetir
# um erro já cometido: os 15 s originais estouravam ANTES de a resposta com
# busca na internet chegar, e produziam "estou sem acesso à rede" com a rede
# funcionando. Por isso a chamada continua com prazo largo (30 s, o dobro
# daquele) e quem limita é o RELÓGIO DE PAREDE do turno inteiro.
#
# 45 s no total dá para a primeira tentativa com busca ir até o fim e ainda
# sobra para uma segunda. Não vale para anexo: ler um vídeo demora mesmo, e
# ali a espera é o serviço.
ORCAMENTO_CHAT_SEG = 45
TIMEOUT_CHAT_MS = 30_000

_MODELOS = {
    "lista": list(_MODELOS_PREFERENCIA),
    "cooldown": {},        # modelo -> epoch até quando pular
    "invalidos": set(),    # descontinuados (404): nunca mais tentar
    "descoberta_ts": 0,    # quando a lista foi conferida na conta
}
_trava_modelos = threading.Lock()

def descobrir_modelos(client, forcar=False, log=None):
    """Pergunta à conta quais modelos existem e monta a ordem de tentativa.
    Reconfere no máximo a cada 30 min — não é dado que muda a toda hora."""
    agora = time.time()
    with _trava_modelos:
        if not forcar and (agora - _MODELOS["descoberta_ts"]) < 1800:
            return list(_MODELOS["lista"])
    try:
        disponiveis = [m.name.replace("models/", "") for m in client.models.list()
                       if "generateContent" in m.supported_actions]
        ordenados = [m for m in _MODELOS_PREFERENCIA if m in disponiveis]
        # Variantes de tts/imagem/áudio não servem para analisar gráfico.
        inadequados = ("tts", "image", "audio", "omni", "embedding")
        extras = [m for m in disponiveis
                  if "flash" in m and m not in ordenados
                  and not any(x in m.lower() for x in inadequados)]
        nova = ordenados + extras
    except Exception as e:
        if log:
            log(f"⚠️ Não consegui listar modelos disponíveis, usando lista padrão: {e}")
        nova = list(_MODELOS_PREFERENCIA)
    with _trava_modelos:
        _MODELOS["lista"] = [m for m in (nova or _MODELOS_PREFERENCIA)
                             if m not in _MODELOS["invalidos"]]
        _MODELOS["descoberta_ts"] = agora
        return list(_MODELOS["lista"])

def fila_por_cooldown(modelos, cooldown, agora, preferido=None):
    """A ordem de tentativa: quem está livre primeiro, quem está estacionado
    depois. NINGUÉM É CORTADO. Devolve (fila, quantos_parados).

    Função PURA, e ela existe por um motivo caro. Esta regra estava escrita
    em DOIS lugares: aqui, certa, para o chat; e dentro do ciclo do motor,
    ERRADA — lá o cooldown era um filtro que só relaxava se a lista ficasse
    vazia. Em 13/08 às 14:45 havia 11 modelos, 9 estacionados por cota (postos
    lá pela conversa do chat dois minutos antes) e 2 livres — justamente os 2
    que estavam mortos com 404. O motor tentou 2, falhou, e escreveu "todos os
    modelos falharam". Sem análise, sem relatório no WhatsApp, e sem pista.

    Cooldown é um PALPITE sobre o futuro ("este provavelmente ainda está sem
    cota"). Perder o ciclo por causa de um palpite custa 5 minutos de mercado;
    tentar um modelo estacionado custa uma requisição."""
    parados_ts = dict(cooldown or {})
    livres = [m for m in modelos if parados_ts.get(m, 0) <= agora]
    parados = [m for m in modelos if parados_ts.get(m, 0) > agora]
    fila = livres + parados
    if preferido and preferido in fila:
        fila = [preferido] + [m for m in fila if m != preferido]
    return fila, len(parados)


def modelos_para_tentar(excluir=(), preferido=None):
    """A ordem de tentativa AGORA: descontinuados fora, quem está em cooldown
    por último (não excluído — é melhor uma chance do que recusar a resposta),
    e o `preferido` na frente."""
    agora = time.time()
    with _trava_modelos:
        base = [m for m in _MODELOS["lista"]
                if m not in _MODELOS["invalidos"] and m not in excluir]
        cooldown = dict(_MODELOS["cooldown"])
    return fila_por_cooldown(base, cooldown, agora, preferido)[0]

def classificar_erro_modelo(erro):
    """'invalido' (404), 'cota' (429), 'transitorio' (503/timeout...) ou 'fatal'."""
    e = str(erro or "").upper()
    if "404" in e or "NOT_FOUND" in e or "NO LONGER AVAILABLE" in e:
        return "invalido"
    if "429" in e or "RESOURCE_EXHAUSTED" in e:
        return "cota"
    # 401 e credencial, nao cota. Tentar os outros modelos com a MESMA chave
    # invalida so gasta tempo e ainda faz o trader pensar que e limite de uso
    # -- foi o que aconteceu: "tentei 10 modelos" com uma chave que nao valia.
    if ("401" in e and "UNAUTHENTICATED" in e) or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in e \
            or "API KEY NOT VALID" in e or "API_KEY_INVALID" in e:
        return "fatal"
    transitorios = ("503", "UNAVAILABLE", "500", "INTERNAL", "504", "DEADLINE",
                    "TIMEOUT", "TIMED OUT", "OVERLOADED", "CONNECTION", "SSL",
                    "TEMPORARILY")
    if any(t in e for t in transitorios):
        return "transitorio"
    return "fatal"

def registrar_falha_modelo(modelo, erro):
    """Anota o que aconteceu com o modelo, para o OUTRO lado do app não repetir
    a mesma tentativa perdida. Devolve a classificação."""
    tipo = classificar_erro_modelo(erro)
    with _trava_modelos:
        if tipo == "invalido":
            _MODELOS["invalidos"].add(modelo)
            _MODELOS["lista"] = [m for m in _MODELOS["lista"] if m != modelo]
        elif tipo == "cota":
            _MODELOS["cooldown"][modelo] = time.time() + COOLDOWN_COTA_SEG
        elif tipo == "transitorio":
            _MODELOS["cooldown"][modelo] = time.time() + COOLDOWN_SOBRECARGA_SEG
    return tipo

def registrar_sucesso_modelo(modelo):
    """Respondeu: sai do cooldown e passa a liderar a fila dos dois lados."""
    with _trava_modelos:
        _MODELOS["cooldown"].pop(modelo, None)
        if modelo in _MODELOS["lista"] and _MODELOS["lista"][0] != modelo:
            _MODELOS["lista"] = ([modelo] +
                                 [m for m in _MODELOS["lista"] if m != modelo])

def diagnostico_modelos():
    """Frase curta sobre o estado dos modelos — para ela explicar em vez de só
    dizer 'a cota estourou'."""
    agora = time.time()
    with _trava_modelos:
        total = len(_MODELOS["lista"])
        parados = sum(1 for m in _MODELOS["lista"]
                      if _MODELOS["cooldown"].get(m, 0) > agora)
        proximo = min((t for t in _MODELOS["cooldown"].values() if t > agora),
                      default=None)
    livres = total - parados
    if livres > 0:
        return f"{livres} de {total} modelos disponíveis"
    falta = int((proximo - agora) / 60) + 1 if proximo else None
    return (f"todos os {total} modelos estão sem cota agora"
            + (f"; o primeiro volta em ~{falta} min" if falta else ""))

def janelas_monitoradas():
    """As janelas de gráfico que o motor analisa a cada ciclo.

    Até a v2.11 só existia UMA ("nome_janela_corretora"), então quem operava
    dois ativos precisava abrir o programa duas vezes — e a segunda cópia batia
    na porta 3939 já ocupada pelo motor da primeira. Agora é uma LISTA, e um
    motor só percorre todas.

    A janela antiga é migrada para dentro da lista automaticamente, então nada
    se perde ao atualizar.
    """
    cfg = carregar_config()
    lista = cfg.get("janelas_monitoradas")
    if not isinstance(lista, list):
        lista = []
    limpa, vistos = [], set()
    for t in lista:
        t = str(t or "").strip()
        if t and t not in vistos:
            vistos.add(t)
            limpa.append(t)
    if not limpa:
        antiga = str(cfg.get("nome_janela_corretora") or "").strip()
        if antiga:
            limpa = [antiga]
    return limpa

def salvar_janelas_monitoradas(lista):
    """Grava a lista e mantém 'nome_janela_corretora' apontando para a primeira.

    Esse espelho existe porque o envio de ordem e a leitura de posições da
    Tradovate continuam ligados a UMA janela — a principal. Assim a automação
    não fica ambígua quando há vários gráficos sendo analisados.
    """
    limpa, vistos = [], set()
    for t in (lista or []):
        t = str(t or "").strip()
        if t and t not in vistos:
            vistos.add(t)
            limpa.append(t)
    salvar_config({"janelas_monitoradas": limpa,
                   "nome_janela_corretora": limpa[0] if limpa else ""})
    return limpa

def posicao_aberta_no_ativo(ativo):
    """A posição que você tem AGORA nesse ativo, na conta ativa — venha ela de
    uma sugestão acatada ou de uma entrada que você fez na mão na plataforma.
    Devolve o registro, ou None."""
    alvo = str(ativo or "").upper()
    if not alvo or alvo == "DESCONHECIDO":
        return None
    for p in carregar_posicoes():
        if not _e_da_conta_ativa(p) or p.get("status") != "ABERTA":
            continue
        nome = str(p.get("ativo") or "").upper()
        # MESU6 e MES casam: o que importa é ser o mesmo instrumento.
        if nome and (nome.startswith(alvo[:3]) or alvo.startswith(nome[:3])):
            return p
    return None

def politica_com_posicao_aberta(acao, ativo, plano=None):
    """O QUE FAZER QUANDO ELE JÁ ESTÁ POSICIONADO.

    Antes isto era uma frase no prompt ("não sugira sinais em conflito direto
    com elas") e QUEM DECIDIA ERA O MODELO. Duas consequências ruins: o
    comportamento variava de ciclo para ciclo, e o modelo generalizava a
    instrução para "não sugerir nada" — inclusive quando o cenário novo era
    justamente o aviso de que o mercado virou CONTRA a posição dele. Ou seja: a
    informação mais valiosa para quem está posicionado era a que ficava calada.

    Agora é regra de código, com três decisões possíveis:
      • 'LIVRE'         -> não há posição no ativo (ou você escolheu 'livre')
      • 'ALERTA_CONTRA' -> o cenário aponta contra a sua posição aberta. NÃO
                           vira sugestão de entrada nova (entrar na direção
                           oposta é hedge, não é trade): vira um ALERTA para
                           você decidir se protege, reduz ou encerra.
      • 'AUMENTO'       -> o cenário aponta a favor. Vira sugestão, marcada como
                           aumento de posição — é você quem decide se acata.
      • 'BLOQUEIA'      -> você pediu silêncio total enquanto estiver posicionado.

    Devolve (decisao, posicao, motivo).
    """
    if acao not in ("BUY", "SELL"):
        return "LIVRE", None, ""
    plano = plano if plano is not None else plano_da_conta_ativa()
    modo = str(plano.get("com_posicao_aberta", "alerta")).strip().lower()
    if modo == "livre":
        return "LIVRE", None, ""
    pos = posicao_aberta_no_ativo(ativo)
    if not pos:
        return "LIVRE", None, ""
    if modo == "bloquear":
        return ("BLOQUEIA", pos,
                f"você está com {pos.get('direcao')} {pos.get('ativo')} aberto e "
                "pediu para eu não sugerir nada enquanto houver posição.")
    if pos.get("direcao") == acao:
        return ("AUMENTO", pos,
                f"você já está {pos.get('direcao')} em {pos.get('ativo')} — este "
                "cenário vai na MESMA direção, então é aumento de posição, não "
                "uma operação nova.")
    return ("ALERTA_CONTRA", pos,
            f"o cenário virou {acao} e você está {pos.get('direcao')} em "
            f"{pos.get('ativo')}. Não vou sugerir entrada contra a sua própria "
            "posição — isso é hedge, não trade. Mas você precisa saber que a "
            "leitura mudou de lado.")

def _normalizar_padrao(texto):
    """Reduz uma confluência a um RÓTULO CANÔNICO, para que 'Sweep de BSL no topo'
    e 'Liquidity Sweep (BSL)' contem como o MESMO padrão. Sem isso, cada frase
    da IA viraria um padrão diferente e nada seria aprendido."""
    t = (texto or "").lower()
    regras = [
        ("varredura de liquidez (sweep)", ("sweep", "varredura", "liquidity sweep", "bsl", "ssl")),
        ("quebra de estrutura (BOS/MSS/CHoCH)", ("bos", "mss", "choch", "break of structure",
                                                  "market structure", "quebra de estrutura")),
        ("order block", ("order block", "ob ", "bloco de ordem", "breaker", "mitigation")),
        ("FVG / ineficiência", ("fvg", "fair value", "ineficiencia", "ineficiência",
                                 "imbalance", "liquidity void", "bpr")),
        ("premium/discount + OTE", ("premium", "discount", "desconto", "ote",
                                     "equilibrium", "equilíbrio")),
        ("topos/fundos iguais (liquidez parada)", ("equal high", "equal low", "topos iguais",
                                                    "fundos iguais", "pdh", "pdl")),
        ("inducement / armadilha", ("inducement", "induc", "turtle soup", "judas",
                                     "sfp", "swing failure")),
        ("killzone / horário", ("killzone", "kill zone", "londres", "london",
                                 "ny am", "ny pm", "sessao", "sessão")),
        ("indicador (RSI/VWAP/média)", ("rsi", "vwap", "media", "média", "momentum",
                                         "divergenc", "divergênc", "volume")),
        ("power of 3 / distribuição", ("power of 3", "distribuic", "distribuiç",
                                        "acumulac", "acumulaç", "displacement",
                                        "deslocamento")),
    ]
    for rotulo, chaves in regras:
        for c in chaves:
            if c in t:
                return rotulo
    return None

def aprendizado_por_padrao(minimo=3):
    """AUTOAPRENDIZAGEM: olha o histórico REAL e descobre quais padrões SMC vêm
    dando certo e quais vêm falhando — nas SUAS operações, no SEU ativo.

    Devolve (bons, ruins, por_hora). Tudo calculado dos registros; nada é
    estimado ou inventado. Padrões com menos de `minimo` amostras são ignorados,
    porque 1 acerto não é evidência de nada.
    """
    db = carregar_performance()
    if not db:
        return [], [], []

    placar = {}
    horas = {}
    for op in db:
        venceu = 1 if op.get("resultado") == "WIN" else 0
        h = op.get("hora")
        if h:
            a, b = horas.get(h, (0, 0))
            horas[h] = (a + venceu, b + 1)
        vistos = set()
        for c in (op.get("confluencias") or []):
            rot = _normalizar_padrao(c)
            if not rot or rot in vistos:
                continue
            vistos.add(rot)
            a, b = placar.get(rot, (0, 0))
            placar[rot] = (a + venceu, b + 1)

    linhas = [(rot, v, n, v / n * 100.0) for rot, (v, n) in placar.items() if n >= minimo]
    linhas.sort(key=lambda x: x[3], reverse=True)
    bons = [l for l in linhas if l[3] >= 60.0][:4]
    ruins = [l for l in linhas if l[3] < 45.0][-4:]

    por_hora = [(h, v, n, v / n * 100.0) for h, (v, n) in horas.items() if n >= minimo]
    por_hora.sort(key=lambda x: x[3], reverse=True)
    return bons, ruins, por_hora

#  Limites do ajuste por aprendizado. Existem para o histórico CORRIGIR a
#  leitura da IA sem SUBSTITUIR a leitura: mesmo um padrão com péssimo
#  histórico não derruba sozinho um cenário excelente, e nem um padrão bom
#  aprova um cenário ruim.
AJUSTE_APRENDIZADO_MAX = 12.0     # teto do bônus/penalidade, em pontos de %
AMOSTRA_MINIMA_APRENDIZADO = 4    # abaixo disso, não é histórico: é acaso

def ajuste_por_aprendizado(confluencias, hora=None, minimo=AMOSTRA_MINIMA_APRENDIZADO):
    """AUTOAPRENDIZAGEM COM EFEITO REAL NA DECISÃO.

    `aprendizado_por_padrao()` já descobria quais padrões acertam e quais falham
    NAS OPERAÇÕES DELE — mas esse conhecimento só era escrito no prompt, e o
    modelo podia simplesmente ignorá-lo. Um padrão que perdeu 8 das 10 últimas
    vezes continuava gerando sugestão com 75% de probabilidade.

    Aqui o aprendizado vira NÚMERO: a probabilidade do cenário é corrigida para
    cima ou para baixo conforme o que a conta já viveu, antes de o piso de
    qualidade decidir. Determinístico, auditável e limitado — o histórico ajusta
    a leitura, nunca a substitui.

    Devolve (delta, explicacoes) — delta em pontos percentuais.
    """
    bons, ruins, por_hora = aprendizado_por_padrao(minimo=minimo)
    if not (bons or ruins or por_hora):
        return 0.0, []

    peso = {rot: pct for rot, _v, _n, pct in bons}
    peso.update({rot: pct for rot, _v, _n, pct in ruins})
    amostras = {rot: n for rot, _v, n, _pct in bons}
    amostras.update({rot: n for rot, _v, n, _pct in ruins})

    delta, explicacoes, vistos = 0.0, [], set()
    for c in (confluencias or []):
        rot = _normalizar_padrao(c)
        if not rot or rot in vistos or rot not in peso:
            continue
        vistos.add(rot)
        # Distância de 50% (moeda ao ar) convertida em pontos de probabilidade.
        # 80% de acerto -> +6 · 30% de acerto -> -8.
        d = (peso[rot] - 50.0) * 0.4
        delta += d
        explicacoes.append(
            f"'{rot}' acertou {peso[rot]:.0f}% em {amostras[rot]} cenários seus "
            f"({d:+.1f} pts)")

    # A HORA também é padrão: quase todo trader tem um horário em que perde.
    if hora and por_hora:
        for h, _v, n, pct in por_hora:
            if str(h) == str(hora) and n >= minimo:
                d = (pct - 50.0) * 0.3
                delta += d
                explicacoes.append(
                    f"no horário {h} você acertou {pct:.0f}% em {n} cenários "
                    f"({d:+.1f} pts)")
                break

    delta = max(-AJUSTE_APRENDIZADO_MAX, min(AJUSTE_APRENDIZADO_MAX, delta))
    return round(delta, 1), explicacoes

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
        # ANTES dizia "não sugira sinais em conflito direto com elas" — e o
        # modelo generalizava para "não sugira NADA", ficando mudo justamente
        # quando o mercado virava contra a posição dele. O que fazer com a
        # posição aberta é decisão de CÓDIGO (politica_com_posicao_aberta), não
        # do modelo. Aqui a posição entra só como CONTEXTO, para a leitura levar
        # em conta onde ele está — e a leitura tem de sair sempre, inclusive
        # (principalmente) quando aponta contra o que ele carrega.
        detalhe = ", ".join(
            f"{p.get('direcao')} {p.get('ativo')} {p.get('contratos') or ''}x @ {p.get('entry')}"
            for p in abertas[:3])
        contexto += (
            f"POSIÇÕES ABERTAS AGORA: {len(abertas)} ({detalhe}). Analise o "
            "gráfico normalmente e diga o que você VÊ. Se a leitura apontar "
            "contra essa posição, DIGA — é a informação mais útil para quem "
            "está posicionado. Não omita e não amenize o cenário por causa "
            "dela.\n")

    # 3) Performance hipotética do robô (sinais acompanhados internamente).
    db = carregar_performance()
    if db:
        total = len(db)
        wins = sum(1 for op in db if op["resultado"] == "WIN")
        winrate = (wins / total) * 100
        contexto += f"Taxa de acerto dos cenários do robô ({total}): {winrate:.1f}%\n"
    else:
        winrate = 100.0

    # 3b) AUTOAPRENDIZAGEM — o que a experiência REAL já mostrou.
    bons, ruins, por_hora = aprendizado_por_padrao()
    if bons or ruins:
        contexto += ("\nO QUE O HISTÓRICO DESTE TRADER JÁ ENSINOU (aprendido dos "
                      "resultados reais, não é teoria):\n")
        for rot, v, n, pct in bons:
            contexto += (f"• '{rot}' vem ACERTANDO: {v} de {n} cenários ({pct:.0f}%). "
                          "Quando este padrão aparecer, dê MAIS peso a ele.\n")
        for rot, v, n, pct in ruins:
            contexto += (f"• '{rot}' vem FALHANDO: {v} de {n} cenários ({pct:.0f}%). "
                          "Sozinho ele NÃO basta — exija outra confluência forte junto, "
                          "ou prefira HOLD.\n")
    if por_hora and len(por_hora) >= 2:
        melhor, pior = por_hora[0], por_hora[-1]
        if melhor[3] - pior[3] >= 20:
            contexto += (f"• Horário: por volta das {melhor[0]}h o acerto é "
                          f"{melhor[3]:.0f}% ({melhor[2]} cenários); por volta das "
                          f"{pior[0]}h cai para {pior[3]:.0f}% ({pior[2]} cenários). "
                          "Considere isso na sua confiança.\n")

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
    if decisao == "CANCELADO":
        return ("🚫 você cancelou a ordem — cenário encerrado", COR["dim"])
    if decisao == "EXPIRADO":
        return ("⌛ expirou — não foi acatada no prazo", COR["dim"])
    if decisao == "CANCELADO_STOP":
        return ("🚫 cancelada — stop rompido antes de o preço tocar a entrada",
                COR["dim"])
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
    """Handle da janela pelo título. Prefere o título EXATO (o dropdown guarda
    o título completo); se não houver, cai para correspondência parcial.
    None significa NÃO ACHEI — nunca "pode seguir assim mesmo".

    No Windows o handle é um HWND; no macOS, o número da janela do Quartz.
    Quem chama não precisa saber a diferença."""
    return plataforma.encontrar_janela(nome_parcial)

def garantir_janela_renderizando(hwnd, restaurar_se_minimizada=True):
    """Deixa a janela apta a ser capturada COM CONTEÚDO ATUAL, sem roubar o
    foco do trader.

    Windows: janela visível não é tocada (nem foco, nem posição, nem z-order).
    Minimizada é restaurada com SW_SHOWNOACTIVATE e empurrada para o fundo da
    pilha — reaparece renderizável sem pular na frente de ninguém.

    macOS: janela coberta continua com buffer válido, então nada precisa ser
    feito. Minimizada no Dock é outra história: desminimizar no Mac obriga a
    ATIVAR o aplicativo, e ativar é tomar a tela de quem está operando. Nesse
    caso devolvemos False e o ciclo é pulado com aviso — perder um ciclo é
    melhor do que interromper o pregão.

    Retorna True se a janela está apta a ser capturada."""
    return plataforma.preparar_janela(hwnd, restaurar_se_minimizada)

def capturar_via_recorte_de_tela(hwnd):
    """Plano C: recorta a região da TELA onde a janela está.
    Sempre conteúdo atual, nunca congelado. A limitação é real e declarada: se
    outra janela estiver POR CIMA, o recorte pega a de cima — por isso é o
    último recurso, usado só quando a captura direta devolve quadro velho.
    Retorna (imagem, houve_sobreposicao)."""
    return plataforma.capturar_regiao_da_tela(hwnd)

def capturar_janela_em_segundo_plano(hwnd):
    """Conteúdo da janela pelo handle, SEM trazê-la para o primeiro plano e sem
    tirar o trader do que ele estiver fazendo. Imagem PIL, ou None se falhar.

    Windows: PrintWindow com PW_RENDERFULLCONTENT — a flag é obrigatória para
    conteúdo desenhado pela GPU, que é o caso de uma aba do Chrome.
    macOS: screencapture -l <id>, que lê o buffer da janela pelo Quartz e
    funciona mesmo com a janela coberta por outras."""
    return plataforma.capturar_janela(hwnd)

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

def salvar_ultimo_print(imagem_pil, janela=""):
    """Guarda em disco a captura que o motor acabou de fazer do gráfico.

    POR QUE ISSO EXISTE: sem isso, a TIGER só enxergava o gráfico pelo TEXTO da
    última análise. Perguntas como "olha o gráfico agora" ou "confere pelo
    último print" não tinham resposta possível. Salvando a imagem, o chat pode
    mandá-la ao modelo e ela vê exatamente o que o motor viu — a mesma imagem
    que gerou a sugestão, sem você tirar print à mão.
    Devolve o dicionário com o que foi salvo, ou None se não deu para salvar.
    """
    try:
        imagem_pil.convert("RGB").save(ULTIMO_PRINT_FILE, format="PNG")
        return {"caminho": ULTIMO_PRINT_FILE, "hora": time.strftime("%H:%M"),
                "quando": time.time(), "janela": janela or ""}
    except Exception:
        return None

def idade_do_ultimo_print(info):
    """Minutos desde a captura. None se não há print. Serve para a TIGER dizer
    'esse print é de 3 minutos atrás' em vez de tratar imagem velha como atual."""
    if not info or not os.path.exists(info.get("caminho", "")):
        return None
    try:
        return max(0.0, (time.time() - float(info.get("quando", 0))) / 60.0)
    except Exception:
        return None

def listar_janelas_abertas():
    """Títulos das janelas visíveis, para popular o dropdown (em vez de o
    trader digitar na mão).

    No macOS o rótulo vem como "Aplicativo — Título da janela". O nome do
    aplicativo vem primeiro de propósito: sem a permissão de Gravação de Tela,
    o macOS entrega a lista SEM os títulos, e assim ainda dá para escolher a
    janela certa pelo aplicativo."""
    return plataforma.listar_janelas()

# --------------------------------------------------------------------
# NÚCLEO DE SUPORTE
# --------------------------------------------------------------------
def limpar_para_voz(texto: str) -> str:
    """Prepara um texto de chat para ser FALADO: remove asteriscos, marcação
    markdown, bullets e emojis, para a voz soar como conversa natural — e não
    ler símbolo por símbolo."""
    t = str(texto or "")
    t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)            # blocos de código
    t = re.sub(r"^[ \t]*[-•▸·*]+[ \t]+", "", t, flags=re.MULTILINE)  # bullets
    t = re.sub(r"[*_`#>|~\[\]{}]+", " ", t)                      # marcação markdown
    t = re.sub("[\U0001F000-\U0001FAFF"      # emojis (blocos principais)
               "\u2190-\u21FF\u2300-\u27BF"  # setas e símbolos diversos
               "\u2B00-\u2BFF\uFE0F\u200D]", " ", t)
    t = t.replace("R:R", "risco-retorno").replace("US$", "")
    t = t.replace("·", ", ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", ". ", t).replace("\n", ". ")
    return re.sub(r"\s+", " ", t).strip()

# Palavra de ativação da TIGER ("OLÁ TIGER", como Alexa/Siri/Ok Google).
# A comparação é TOLERANTE de propósito: o Google transcreve o chamado de
# vários jeitos (tiger, Tigre, taiguer, tagger, Tayler...) e a versão anterior,
# de regex exata, descartava tudo isso em silêncio — parecia que ela era surda.
def _sem_acento(texto):
    import unicodedata
    plano = unicodedata.normalize("NFD", texto)
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")

def _parece_tiger(palavra):
    """A palavra transcrita parece 'tiger'? Aceita variações e transcrições
    imperfeitas via similaridade (difflib), não só igualdade exata."""
    p = _sem_acento((palavra or "").lower()).strip(",.!?;:-()\"'")
    if len(p) < 4:
        return False
    if p.startswith(("tig", "taig", "tayg", "tyg")):
        return True
    import difflib
    return any(difflib.SequenceMatcher(None, p, alvo).ratio() >= 0.72
               for alvo in ("tiger", "tigre", "taiguer", "tigrer"))

def extrair_comando_tiger(texto):
    """Detecta o chamado 'Olá Tiger' (ou variações) numa fala transcrita.
    Devolve (acordou, resto): 'acordou' diz se a TIGER foi chamada, e 'resto'
    é o pedido que veio junto na MESMA frase ("olá tiger, qual o status?" →
    resto = "qual o status?"). Resto vazio = só chamou, aguardar o pedido.
    O resto preserva o texto ORIGINAL (acentos e pontuação das palavras)."""
    t = (texto or "").strip()
    if not t:
        return (False, "")
    palavras = t.split()
    for i, palavra in enumerate(palavras):
        if _parece_tiger(palavra):
            resto = " ".join(palavras[i + 1:]).strip(" ,.!?:;-")
            return (True, resto)
    return (False, "")

# Verdadeiro enquanto o alto-falante está falando. A escuta contínua do modo
# OLÁ TIGER pausa nesse período — senão o microfone transcreveria a própria voz.
TTS_FALANDO = False

VOZ_RATE_PADRAO = 165
VOZ_RATE_MIN = 110
VOZ_RATE_MAX = 260

def velocidade_da_voz():
    """Palavras por minuto do TTS, como o trader ajustou. Fica salvo na config,
    então vale também depois de fechar o programa."""
    try:
        v = int(carregar_config().get("voz_rate", VOZ_RATE_PADRAO))
    except (TypeError, ValueError):
        v = VOZ_RATE_PADRAO
    return max(VOZ_RATE_MIN, min(VOZ_RATE_MAX, v))

def voz_escolhida():
    """A voz que ele escolheu, do disco. Vazio = a melhor que o sistema tiver."""
    try:
        return str(carregar_config().get("voz_nome", "") or "").strip()
    except Exception:
        return ""


def salvar_voz_escolhida(nome):
    """Grava a voz e RELÊ do disco para confirmar — como toda gravação aqui."""
    salvar_config({"voz_nome": str(nome or "").strip()})
    return voz_escolhida()


def ajustar_velocidade_da_voz(passo):
    """Acelera (passo positivo) ou desacelera a fala. Devolve (novo, no_limite)."""
    atual = velocidade_da_voz()
    novo = max(VOZ_RATE_MIN, min(VOZ_RATE_MAX, atual + passo))
    salvar_config({"voz_rate": novo})
    return novo, novo == atual

# FALA INTERROMPÍVEL: guarda o motor de voz em uso para que outra thread possa
# calar a boca dela na hora. Sem isso, o trader falava por cima e tinha de
# esperar o parágrafo inteiro terminar — numa mesa, esperar é perder o momento.
_TTS_ENGINE = None
_TTS_LOCK = threading.Lock()
_TTS_TEXTO = ""              # o que ela está dizendo agora (para ignorar o eco)

def parar_fala():
    """Cala a TIGER imediatamente. Pode ser chamada de qualquer thread —
    do botão 🎤, do 'Olá Tiger' ouvido por cima, ou do comando 'para de falar'.
    Devolve True se havia mesmo algo sendo falado."""
    global _TTS_ENGINE
    with _TTS_LOCK:
        engine, _TTS_ENGINE = _TTS_ENGINE, None
    if engine is None:
        return False
    try:
        # No macOS o "engine" é o processo do `say`: calar é matá-lo.
        if plataforma.VOZ_NATIVA:
            engine.terminate()
        else:
            engine.stop()
    except Exception:
        pass
    return True

def falar(texto: str):
    global TTS_FALANDO, _TTS_ENGINE, _TTS_TEXTO
    try:
        texto = limpar_para_voz(texto)
        if not texto:
            return
        # Uma fala nova cancela a anterior: ela não acumula parágrafos.
        parar_fala()
        TTS_FALANDO = True
        _TTS_TEXTO = texto
        # Velocidade ajustável pelo trader ("acelere a fala" / "fala mais
        # devagar"). 165 é o padrão; a faixa evita ficar ininteligível.
        if plataforma.VOZ_NATIVA:
            # macOS: fala pelo `say` do sistema. O pyttsx3 aqui usa
            # NSSpeechSynthesizer, que precisa do run loop do Cocoa na thread
            # principal — a TIGER fala de uma thread de trabalho e ali ele
            # trava ou fica mudo.
            engine = plataforma.falar_nativo(texto, velocidade_da_voz(),
                                             voz_preferida=voz_escolhida())
            if engine is None:
                return
            with _TTS_LOCK:
                _TTS_ENGINE = engine
            engine.wait()            # parar_fala() mata o processo e libera
        else:
            engine = pyttsx3.init()
            engine.setProperty('rate', velocidade_da_voz())
            # Casa pelo NOME e também pelo ID/idioma: no Windows as vozes PT
            # trazem "Brazil"/"Portugu" no nome, mas em outros sistemas o que
            # identifica o idioma é o id ("...pt-BR...").
            for v in engine.getProperty('voices'):
                marca = f"{getattr(v, 'name', '')} {getattr(v, 'id', '')}".lower()
                if ('brazil' in marca or 'portugu' in marca
                        or 'pt-br' in marca or 'pt_br' in marca):
                    engine.setProperty('voice', v.id)
                    break
            with _TTS_LOCK:
                _TTS_ENGINE = engine
            engine.say(texto)
            engine.runAndWait()      # parar_fala() faz este retornar na hora
            try:
                engine.stop()
            except Exception:
                pass
    except Exception:
        pass
    finally:
        TTS_FALANDO = False
        _TTS_TEXTO = ""
        with _TTS_LOCK:
            if _TTS_ENGINE is not None:
                _TTS_ENGINE = None

# Teto de bytes da imagem no WhatsApp. Acima disso o envio começa a demorar e
# a falhar; abaixo disso não há por que economizar.
TETO_IMAGEM_WHATSAPP = 900_000


def comprimir_grafico(imagem_pil, teto=TETO_IMAGEM_WHATSAPP):
    """Comprime o gráfico PRESERVANDO O TEXTO. Devolve os bytes.

    POR QUE ISTO EXISTE: a imagem ia como JPEG com qualidade 80. Para foto,
    80 é ótimo. Para GRÁFICO, é destruição: o JPEG foi feito para imagem com
    variação suave, e um gráfico é o contrário disso — linha de um pixel,
    número de 10px, alto contraste. A compressão espalha borrão em volta de
    cada caractere (ringing), e é exatamente ali que está o preço.
    Queixa dele, 13/08 09:52: "essa qualidade de print está muito ruim".

    Estratégia, na ordem:
      1. PNG — sem perda nenhuma. Gráfico tem poucas cores chapadas, então o
         PNG costuma comprimir MUITO bem. Se couber no teto, é o melhor.
      2. JPEG 95 com subsampling desligado. Subsampling é o que borra a cor
         nas bordas do texto; desligá-lo custa poucos bytes e salva a leitura.
      3. Só então reduzir o TAMANHO da imagem — e reduzir é o último recurso,
         porque metade dos pixels é metade da chance de ler o número."""
    from PIL import Image
    img = imagem_pil.convert("RGB")

    saida = BytesIO()
    img.save(saida, format="PNG", optimize=True)
    if saida.tell() <= teto:
        return saida.getvalue()

    for qualidade in (95, 92, 88):
        saida = BytesIO()
        img.save(saida, format="JPEG", quality=qualidade, subsampling=0,
                 optimize=True)
        if saida.tell() <= teto:
            return saida.getvalue()

    # Ainda grande: reduz a imagem, nunca abaixo de 1280px de largura — que é
    # o mínimo para a legenda de um gráfico continuar legível.
    largura = img.width
    while largura > 1280:
        largura = int(largura * 0.8)
        menor = img.resize((largura, int(img.height * largura / img.width)),
                           Image.LANCZOS)
        saida = BytesIO()
        menor.save(saida, format="JPEG", quality=92, subsampling=0,
                   optimize=True)
        if saida.tell() <= teto:
            return saida.getvalue()
    return saida.getvalue()


def enviar_relatorio_whatsapp(mensagem: str, imagem_print, log_callback):
    log_callback("📲 Disparando relatório para o WhatsApp...")
    try:
        payload = {"jid": "", "texto": mensagem}
        if imagem_print is not None:
            payload["imagemBase64"] = base64.b64encode(
                comprimir_grafico(imagem_print)).decode("utf-8")

        response = requests.post(BAILEYS_API_URL, json=payload, timeout=45)
        if response.status_code == 200:
            log_callback("✅ Relatório enviado com sucesso!")
        else:
            log_callback(f"⚠️ Erro na API do WhatsApp: {response.text}")
    except Exception as e:
        log_callback(f"⚠️ Falha no disparo do relatório: {e}")

# --------------------------------------------------------------------
# INTERFACE GRÁFICA (GUI) E GERENCIADOR DE PROCESSOS
# --------------------------------------------------------------------
# ====================================================================
# IA INTERATIVA — converse com o robô por MENSAGEM ou VOZ, em tempo real
# ====================================================================
# É o mentor de mesa dentro do app: você pergunta sobre a análise, discute a
# sugestão, pede o status, acata/dispensa por linguagem natural e ENSINA lições
# que passam a valer tanto no chat quanto nas próximas análises do gráfico.

def carregar_chat():
    dados = _ler_json_cache(CHAT_FILE)
    if isinstance(dados, list):
        return _copia_rasa([m for m in dados
                            if isinstance(m, dict) and m.get("papel") and m.get("texto")])
    return []

def salvar_chat(lista):
    with open(CHAT_FILE, "w", encoding="utf-8") as f:
        json.dump(lista[-200:], f, ensure_ascii=False, indent=1)
    _cache_json.pop(CHAT_FILE, None)

def registrar_msg_chat(papel, texto):
    """papel: 'voce' | 'ia' | 'sistema'."""
    lista = carregar_chat()
    lista.append({"papel": papel, "texto": str(texto)[:4000],
                  "hora": time.strftime('%d/%m %H:%M')})
    salvar_chat(lista)
    return lista

def carregar_licoes():
    dados = _ler_json_cache(LICOES_FILE)
    if isinstance(dados, list):
        return [str(x)[:300] for x in dados if str(x).strip()]
    return []


def licoes_que_nao_ensinam(licoes):
    """Separa as lições GRAVADAS que não instruem nada. (boas, ruins).

    Isto é faxina retroativa, e existe porque as travas chegaram depois do
    estrago. A lista dele, em 13/08 às 12:40, tinha SEIS lições, e a de número
    6 era:
        "o que aconteceu com HAPV3 HOJE?"
    Uma pergunta. Ela foi gravada antes de a trava de pergunta existir, e
    continuava entrando em TODA análise e TODA conversa como se fosse regra —
    porque as lições vão inteiras para dentro do prompt.

    Isso não é decoração: cada linha de lixo ali dentro gasta contexto e
    empurra o modelo para responder a coisa errada. É parte da resposta a
    'ela não está mais tão inteligente'.

    Função PURA: recebe a lista, devolve duas. Quem apaga é quem chamou, e
    depois de dizer o que vai apagar."""
    boas, ruins = [], []
    for licao in (licoes or []):
        texto = str(licao).strip()
        if not texto:
            continue
        motivo = ""
        if _e_pergunta(texto):
            motivo = "é uma pergunta, e pergunta não instrui nada"
        else:
            impossivel, porque = licao_pede_invencao(texto)
            if impossivel:
                motivo = porque
            else:
                # As duas do WhatsApp gravadas em 14/08 às 10:57 e 10:58 caem
                # aqui: pediam AÇÃO, e ação nenhuma sai de lição. Ficaram na
                # lista entrando em toda análise sem instruir coisa alguma.
                acao, porque_acao = licao_pede_acao(texto)
                if acao:
                    motivo = porque_acao
        (ruins if motivo else boas).append(
            (texto, motivo) if motivo else texto)
    return boas, ruins

# LIÇÕES QUE NÃO PODEM SER ACEITAS.
#
# Caso real (06/08 15:33): com a cota da API fora, ele ensinou
#   "tira um print e leia off line se não tiver acesso a api kay gemini"
# e a ferramenta respondeu "Anotado e aprendido". O problema é que LER a imagem
# é a única coisa que depende da visão da API — offline não existe leitura, só
# invenção. Uma lição assim não é conhecimento: é uma ordem permanente para
# fabricar número de gráfico, gravada na memória, valendo em toda análise
# futura. Numa ferramenta que move dinheiro, isso é o pior defeito possível.
#
# A regra da casa ("nunca invente número") não pode ser revogada por lição.
_LICAO_IMPOSSIVEL = re.compile(
    r"(l[êe]r?|leia|analis\w*|interpret\w*|enxerg\w*|v[êe]r?)\b[^.;]{0,60}"
    r"\b(off ?line|sem (a )?(api|chave|internet|cota|conex[ãa]o)|"
    r"quando (a )?(api|cota|chave)\b[^.;]{0,20}(fora|acabar|estourar|cair))"
    r"|"
    r"\b(sem (a )?(api|chave|cota|internet)|off ?line)\b[^.;]{0,60}"
    r"\b(l[êe]r?|leia|analis\w*|interpret\w*|gr[áa]fico|imagem|print|tela)\b"
    r"|"
    r"\b(chut\w*|adivinh\w*|estim\w*|invent\w*|supon\w*|imagin\w*)\b[^.;]{0,40}"
    r"\b(pre[çc]o|n[úu]mero|valor|gr[áa]fico|cota[çc][ãa]o|entrada|stop|alvo)\b",
    re.IGNORECASE)

def licao_pede_invencao(texto):
    """True quando a 'lição' manda a ferramenta produzir dado que ela não tem.
    Devolve também o motivo, para ela explicar em vez de só recusar."""
    t = _sem_acento(str(texto or "")).lower()
    if not t:
        return False, ""
    if _LICAO_IMPOSSIVEL.search(t):
        return True, (
            "ler gráfico é a única coisa que depende da visão da API — sem ela "
            "não existe leitura offline, existe chute")
    if _e_fato_efemero(texto):
        return True, (
            "isso é um NÚMERO DE AGORA, não uma regra. Uma lição vale para "
            "sempre: se eu gravar um preço, vou repetir esse mesmo preço "
            "daqui a um mês, com o mercado em outro lugar — e aí eu estaria "
            "inventando, que é exatamente o que você não quer")
    if _e_pergunta(texto):
        return True, (
            "isso é uma PERGUNTA, não uma regra — e pergunta gravada não "
            "instrui nada, só entra em toda análise daqui pra frente como "
            "ruído. Se o que você quer ensinar é o que vem DEPOIS da "
            "pergunta, me mande só essa parte: 'quando eu perguntar de um "
            "ativo, pesquise na web — aprenda isso'")
    return False, ""


# LIÇÃO NÃO LIGA BOTÃO.
#
# Log de 14/08, 10:57 e 10:58 — ele mandou a MESMA coisa duas vezes seguidas,
# que é o que a gente faz quando desconfia que não pegou:
#     "toda vez que eu enviar STATUS pelo whatsapp, por favor, envie o status
#      para mim! - Aprenda isso"
# e as duas vezes recebeu:
#     "Anotado e aprendido. Está gravado na minha memória e passa a valer em
#      TODAS as análises e conversas daqui pra frente."
#
# Isso é falso de duas maneiras ao mesmo tempo, e a segunda é pior:
#
# 1. Lição vira TEXTO dentro do pedido ao modelo. Ela nunca vira código. Por
#    mais vezes que ele grave "envie o status", nenhum status sai — porque
#    quem envia é a função de WhatsApp, e ela é chamada por comando, não por
#    parágrafo no prompt.
# 2. O WhatsApp desta ferramenta SÓ ENVIA. Não existe nada escutando mensagem
#    que chega. O que ele pediu — "quando EU MANDAR status, você responde" —
#    não é uma regra que faltou ensinar: é um recurso que não existe. Dizer
#    "aprendido" fez ele acreditar que passaria a funcionar, e ficou uma
#    semana achando que a ferramenta estava ignorando a própria memória.
#
# Além de mentir, a frase entrava em toda análise dali pra frente gastando
# contexto — é literalmente o que ele descreveu como "ficou mais burra".
_LICAO_ACAO_WHATSAPP_RECEBE = re.compile(
    r"\b(quando|toda vez que|sempre que|cada vez que|se)\b[^.;\n]{0,40}"
    r"\b(eu|voce|vc)\b[^.;\n]{0,30}"
    r"\b(envi\w*|mand\w*|escrev\w*|manda\w*|digit\w*|pedir|perguntar)\b"
    r"[^.;\n]{0,40}\b(whats?app?|zap|wpp)\b"
    r"|\b(receb\w*|responde\w*|l[êe]r?|ler|monitor\w*|escut\w*|ouvir?)\b"
    r"[^.;\n]{0,40}\b(mensage\w*|comando\w*|texto\w*)\b[^.;\n]{0,30}"
    r"\b(whats?app?|zap|wpp)\b", re.IGNORECASE)

# O CONSERTO DE VERDADE FOI FAZER A COISA FUNCIONAR, NÃO RECUSAR MELHOR.
#
# A primeira versão desta trava recusava dizendo "o WhatsApp daqui só envia,
# não existe nada escutando o que chega". Estava ERRADO — e o erro apareceu
# num print da própria tela do app, na aba do WhatsApp: "um contato entra
# quando envia START no WhatsApp". O motor recebe mensagens desde sempre, e já
# tratava START, STOP, ACATAR, NÃO OPEREI e NOVA ANÁLISE.
#
# Ou seja: o que ele pediu em 14/08 era trivial de fazer, e passou três meses
# como "aprendido" porque ninguém foi olhar. STATUS agora é comando de
# verdade, do mesmo jeito que os outros — a lição continua recusada, mas
# agora a recusa aponta para uma coisa que existe.
#
# DE PROPÓSITO, ESTA TRAVA PEGA SÓ O WHATSAPP QUE CHEGA.
#
# A primeira versão que escrevi recusava qualquer lição que citasse uma ação —
# print, motor, zerar ciclo. A suíte derrubou na hora, e com razão: a lista
# REAL dele tem duas lições assim, e as duas são BOAS —
#     "tira um print e olha o preço atual, nunca forneça recomendações sem
#      olhar o preço atual"
#     "toda vez que pedir alguma análise sobre algum indicador, tire um print
#      novo e analise para me responder"
# Essas instruem o RACIOCÍNIO ("não opine sem olhar o preço"), e isso lição
# faz muito bem. Recusá-las teria consertado um defeito criando outro maior.
#
# O WhatsApp que CHEGA é diferente de todos eles por um motivo objetivo: não
# existe. Não é uma ação que sai por comando em vez de por lição — é uma ação
# que não sai de jeito nenhum, porque não há nada escutando do outro lado.
# Prometer isso é a única das quatro que não tem como dar certo nunca.
def licao_pede_acao(texto):
    """True quando a 'lição' pede algo que a ferramenta NÃO SABE FAZER.

    Devolve (True, explicação honesta). Dizer 'não faço isso, e olha o que eu
    faço' vale mais que 'aprendido' — porque é verdade, e porque ele para de
    esperar por uma coisa que não vem."""
    t = _sem_acento(str(texto or "")).lower()
    if not t:
        return False, ""
    if _LICAO_ACAO_WHATSAPP_RECEBE.search(t):
        return True, (
            "ISSO JÁ FUNCIONA, e não por lição — por comando. Mande STATUS no "
            "WhatsApp e eu respondo com a conta, a meta, o ritmo exigido, as "
            "posições abertas e a última leitura do gráfico. Também valem "
            "SITUAÇÃO e RESUMO.\n\n"
            "Gravar isso como lição é que não adiantaria: lição vira texto "
            "dentro do meu raciocínio, e texto não aperta botão. Foi por isso "
            "que você mandou a mesma frase duas vezes em 14/08 e ouviu "
            "'aprendido' nas duas sem nunca receber um status — o comando é "
            "que faltava, e ele existe agora")
    return False, ""


# UM PREÇO NÃO É UMA REGRA.
#
# O caso real (12/08, 14:16). Ele escreveu, irritado:
#     "MAS A PORRA DO VWAP ESTA EM 7769,78. ERA PARA VOCE SABER ISSO,
#      APRENDA ISSO! APRENDA IDENTIFICAR INDICADORES NO GRAFICO"
# e a ferramenta respondeu:
#     "Anotado e aprendido: 'MAS A PORRA DO VWAP ESTA EM 7769,78. ERA PARA
#      VOCE SABER ISSO'. Passa a valer em TODAS as análises daqui pra frente."
#
# Ela gravou um VALOR DE UM INSTANTE como verdade permanente. Um minuto depois
# a VWAP já era outra — e aquele número ficaria na memória para sempre, sendo
# repetido como fato em toda conversa futura. É a regra "nunca invente número"
# funcionando ao contrário: em vez de recusar um número inventado, ela adotou
# um número vencido.
#
# O que ele QUERIA ensinar estava na segunda linha: "aprenda a identificar
# indicadores no gráfico". Isso sim é regra. O número era só o exemplo raivoso.
_RE_FATO_EFEMERO = re.compile(
    r"\b(vwap|pre[çc]o|cota[çc][ãa]o|stop|alvo|entrada|topo|fundo|suporte|"
    r"resist[êe]ncia|m[íi]nima|m[áa]xima|abertura|fechamento)\b"
    r"[^.;\n]{0,40}"
    r"(\b(esta|est[áa]|e|é|em|foi|era|vale|marca|bateu|ficou)\b[^.;\n]{0,15})?"
    r"\d{2,}[.,]?\d*", re.IGNORECASE)

def _e_pergunta(texto):
    """True quando a 'lição' é uma PERGUNTA, não uma regra.

    Log de 13/08, 12:39. Ele escreveu, numa mensagem só:
        "O QUE ACONTECEU COM HAPV3 HOJE? -APRENDA ISSO, TODA VEZ QUE TIVER
         ALGUMA PERGUNTA ASSIM, PESQUISE NA WEB..."
    O que ele queria ensinar era a REGRA que vinha depois. O que ficou gravado
    foi "o que aconteceu com HAPV3 HOJE?" — a pergunta. Um minuto depois, a
    lista de lições tinha isso na posição 6, e aquilo passaria a entrar em
    TODA análise, para sempre, como se fosse instrução.

    Uma pergunta não instrui nada. Ela também não é 'errada' — é só a coisa
    errada para guardar, e recusar com explicação é melhor que guardar lixo."""
    t = str(texto or "").strip()
    if not t:
        return False
    if not t.endswith("?"):
        return False
    n = _sem_acento(t).lower()
    # Regra em forma de pergunta retórica existe ("já pensou em arriscar 5%?"),
    # mas é rara e ambígua. Aqui vale a forma: começou com interrogativo e
    # terminou com '?', é pergunta.
    return bool(re.match(r"^(o que|oque|qual|quais|quando|quanto|quantos|"
                         r"como|onde|por que|porque|porqu[êe]|pq|quem|"
                         r"sera que|tem |teve |houve |voce |vc )", n))


def separar_pergunta_da_regra(texto):
    """Quando a 'lição' é UMA PERGUNTA seguida de uma REGRA, fica só a regra.

    Log de 13/08, 16:03. Ele escreveu, numa mensagem só:
        'o dia encerrar "tal horario", qual a probabilidade de matermos a meta
         de hoje?olha no plano de trading e o motor para responder essa
         pergunta - aprenda isso'
    A regra é "olha no plano de trading e o motor". A pergunta é o EXEMPLO que
    motivou a regra. O que ficou gravado foi a frase inteira, exemplo e tudo —
    e aquilo passava a entrar em toda análise, para sempre.

    `_e_pergunta` não pegava porque exige que o texto TERMINE em '?', e aqui a
    interrogação está no meio. Devolve (regra, pergunta_descartada); quando não
    há esse formato, devolve (texto, "") e nada muda."""
    t = str(texto or "").strip()
    if "?" not in t or t.endswith("?"):
        return t, ""
    antes, _sep, depois = t.partition("?")
    depois = depois.strip(" -–—,.:;")
    if len(depois.split()) < 3:
        return t, ""            # o que sobra não é regra nenhuma
    if not _e_pergunta(antes.strip() + "?"):
        return t, ""            # o pedaço da frente não era pergunta
    return depois, antes.strip() + "?"


def _e_fato_efemero(texto):
    """True quando a 'lição' é um dado de UM MOMENTO (um preço, um nível de
    agora) em vez de uma regra que vale sempre.

    A régua: cita um conceito de PREÇO e traz um NÚMERO grande junto. Regras
    legítimas com número — 'nunca arrisque mais de 2% por operação', 'não opere
    depois das 15h', 'exija R:R de 1:2' — falam de percentual, hora ou razão,
    não de nível de preço, e passam sem problema."""
    t = str(texto or "")
    if not t.strip():
        return False
    # Percentual, horário e R:R são REGRAS, mesmo tendo número.
    if re.search(r"\d+\s*%|\bas?\s*\d{1,2}\s*(h|:\d{2})|\b1\s*[:x]\s*\d", t, re.I):
        return False
    return bool(_RE_FATO_EFEMERO.search(t))

def adicionar_licao(texto):
    """Uma LIÇÃO é conhecimento que VOCÊ dá ao robô ('aprenda: não opere contra
    a tendência do H4 depois das 15h'). Fica salva e entra em TODA análise e em
    TODA conversa dali em diante — é a autoaprendizagem dirigida por você."""
    texto = (texto or "").strip()
    if not texto:
        return False
    licoes = carregar_licoes()
    if texto in licoes:
        return False
    licoes.append(texto[:300])
    with open(LICOES_FILE, "w", encoding="utf-8") as f:
        json.dump(licoes[-40:], f, ensure_ascii=False, indent=1)
    _cache_json.pop(LICOES_FILE, None)
    return True

def remover_licao(alvo):
    """Apaga UMA lição. `alvo` pode ser o número dela na lista (1, 2, 3...) ou
    um trecho do texto.

    POR QUE ISTO FALTAVA: em 12/08 às 14:16 ela gravou um preço como regra
    permanente. Às 14:16 ele escreveu "REMOVA ISSO" e às 14:17 ela respondeu
    repetindo a lição gravada. Não havia como desfazer — só apagar TUDO, o que
    levaria junto as lições boas. Memória em que não se pode mexer não é
    memória, é entulho.

    Devolve o texto removido, ou None."""
    licoes = carregar_licoes()
    if not licoes:
        return None
    alvo = str(alvo or "").strip()
    indice = None
    if re.fullmatch(r"\d{1,2}", alvo):
        n = int(alvo)
        if 1 <= n <= len(licoes):
            indice = n - 1
    if indice is None and alvo:
        chave = _norm_busca(alvo)
        if chave:
            # Casamento pelo TRECHO: ele nunca vai redigitar a lição inteira.
            indice = next((i for i, l in enumerate(licoes)
                           if chave in _norm_busca(l)), None)
    if indice is None and not alvo:
        indice = len(licoes) - 1        # "esquece isso" = a última gravada
    if indice is None:
        return None
    removida = licoes.pop(indice)
    with open(LICOES_FILE, "w", encoding="utf-8") as f:
        json.dump(licoes, f, ensure_ascii=False, indent=1)
    _cache_json.pop(LICOES_FILE, None)
    return removida


# "REMOVA ISSO", "ESQUECE ESSA LIÇÃO", "APAGA A 3".
_RE_ESQUECER = re.compile(
    r"\b(remov\w+|apag\w+|esquec\w+|delet\w+|tir\w+|desfa[czç]\w*|cancel\w+)\b"
    r"[^.;\n]{0,30}?"
    r"\b(isso|isto|essa|esse|aquela|aquele|li[çc][ãa]o|li[çc][õo]es|"
    r"aprendizado|regra|mem[óo]ria|[uú]ltim\w+|\d{1,2}|que fala|que diz)\b",
    re.IGNORECASE)

def pedido_de_esquecer(texto):
    """Devolve (True, alvo) quando ele está mandando APAGAR uma lição.
    `alvo` é o número ou o trecho citado — string vazia significa 'a última'."""
    t = _norm_busca(texto or "")
    if not t or not _RE_ESQUECER.search(t):
        return False, ""
    # "aprenda isso" com "esquece" na mesma frase é ordem de apagar, não de
    # gravar: quem diz as duas coisas está corrigindo o que foi gravado.
    # "apaga a LIÇÃO 2" e também "apaga a 2" — ele não vai escrever a palavra
    # 'lição' toda vez. Sem este segundo padrão, "apaga a 2" caía no alvo vazio
    # e apagaria a ÚLTIMA, que é a lição errada.
    m = re.search(r"\b(li[çc][ãa]o|regra)\s*(n[úu]mero\s*)?(\d{1,2})\b", t)
    if m:
        return True, m.group(3)
    m = re.search(r"\b(remov\w+|apag\w+|esquec\w+|delet\w+|tir\w+)\b"
                  r"[^\d\n]{0,12}(\d{1,2})\b", t)
    if m:
        return True, m.group(2)
    m = re.search(r"\b(sobre|que fala de|do|da)\s+(.{3,40})$", t)
    if m:
        return True, m.group(2).strip()
    return True, ""


def apagar_licoes():
    with open(LICOES_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
    _cache_json.pop(LICOES_FILE, None)

def bloco_licoes_prompt():
    """Bloco injetado no prompt da ANÁLISE e no chat. Vazio se não há lições."""
    licoes = carregar_licoes()
    if not licoes:
        return ""
    corpo = "\n".join(f"• {l}" for l in licoes)
    return ("\nLIÇÕES QUE O TRADER TE ENSINOU (obedeça — são ordens dele, "
            f"aprendidas em sessões anteriores):\n{corpo}\n")

# ====================================================================
# JANELA PARA A WEB — dados reais SEM chave de API
# ====================================================================
# POR QUE ISSO EXISTE: com a cota da Gemini estourada a ferramenta ficava cega
# para o mundo, e quando respondia sobre o mercado o fazia de memória — ou seja,
# inventando. "O S&P sobe por causa de dados de inflação e resultados de
# tecnologia" pode estar certo ou ser puro chute: o modelo não tinha como saber.
#
# Aqui a TIGER busca o dado ELA MESMA, com o `requests` que o app já usa:
#   • COTAÇÃO real (Yahoo Finance) — preço, variação e faixa do dia
#   • NOTÍCIA fresca (RSS de 6 casas de mercado) — manchete, fonte e hora
#   • BUSCA na web (DuckDuckGo) — para o resto
# Nada disso precisa de chave, cota ou plano pago. E como o número vem da fonte,
# ela não tem o que inventar: ou tem o dado e cita de onde veio, ou diz que não
# conseguiu buscar.
_WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Feeds públicos, sem cadastro. Se algum sair do ar, os outros seguem servindo —
# por isso são vários e de casas diferentes (duas em português).
FONTES_NOTICIAS = [
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("CNBC Markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml"
                     "?partnerId=wrss01&id=20910258"),
    ("Investing.com", "https://www.investing.com/rss/news_25.rss"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("Nasdaq", "https://www.nasdaq.com/feed/rssoutbound?category=Markets"),
    ("InfoMoney", "https://www.infomoney.com.br/feed/"),
]

# Como o trader chama cada ativo -> símbolo do Yahoo. Os futuros que ele opera
# (MES/MNQ) seguem o índice à vista, então apontam para o contínuo.
SIMBOLOS_MERCADO = {
    "s&p": "^GSPC", "sp500": "^GSPC", "s&p500": "^GSPC", "sp 500": "^GSPC",
    "s&p 500": "^GSPC", "sp-500": "^GSPC", "smp500": "^GSPC", "smp 500": "^GSPC",
    "esse p 500": "^GSPC", "es e pe 500": "^GSPC", "s e p 500": "^GSPC",
    "spx": "^GSPC", "es": "ES=F", "mes": "ES=F", "mini indice": "^GSPC",
    "nasdaq": "^IXIC", "nasdac": "^IXIC", "nasdak": "^IXIC", "nasdaq 100": "^NDX",
    "nq": "NQ=F", "mnq": "NQ=F", "ndx": "^NDX",
    "dow": "^DJI", "dow jones": "^DJI", "ym": "YM=F",
    "russell": "^RUT", "vix": "^VIX", "volatilidade": "^VIX",
    "ouro": "GC=F", "gold": "GC=F", "prata": "SI=F",
    "petroleo": "CL=F", "petróleo": "CL=F", "oil": "CL=F", "brent": "BZ=F",
    "dolar": "BRL=X", "dólar": "BRL=X", "usdbrl": "BRL=X", "real": "BRL=X",
    "euro": "EURUSD=X", "eurusd": "EURUSD=X",
    "bitcoin": "BTC-USD", "btc": "BTC-USD", "ethereum": "ETH-USD",
    "ibovespa": "^BVSP", "ibov": "^BVSP",
    "juros": "^TNX", "treasury": "^TNX", "dxy": "DX-Y.NYB",
}

_cache_web = {}          # chave -> (quando, valor) — evita repetir a mesma busca

def _web_cacheado(chave, ttl, produtor):
    """Guarda o resultado por alguns segundos. Perguntar três vezes seguidas
    'como está o S&P' não deve virar três downloads."""
    agora = time.time()
    hit = _cache_web.get(chave)
    if hit and (agora - hit[0]) < ttl:
        return hit[1]
    valor = produtor()
    if valor:
        _cache_web[chave] = (agora, valor)
    return valor

def _web_get(url, params=None, timeout=10):
    r = requests.get(url, params=params, timeout=timeout,
                     headers={"User-Agent": _WEB_UA,
                              "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"})
    r.raise_for_status()
    return r

def _compacto(texto):
    """Só letras e números: 'sp-500' e 's&p 500' viram 'sp500'. É como o ativo
    sobrevive à transcrição de voz, que escreve o mesmo índice de cinco jeitos."""
    return re.sub(r"[^a-z0-9]", "", _norm_busca(texto))

def simbolo_do_texto(texto):
    """Descobre de qual ativo ele está falando. Devolve (símbolo, nome) ou None.

    Três passadas, da mais segura para a mais tolerante. A terceira existe
    porque o microfone devolveu 'smp500' e 'sp-500' para S&P 500, e a ferramenta
    respondia 'não tenho como responder' para uma cotação que ela tinha."""
    t = _norm_busca(texto)
    achado = None
    for apelido, simbolo in SIMBOLOS_MERCADO.items():
        a = _norm_busca(apelido)
        if re.search(rf"(^|[^a-z0-9]){re.escape(a)}([^a-z0-9]|$)", t):
            # o apelido mais longo ganha: "s&p 500" vale mais que "es"
            if not achado or len(a) > len(achado[0]):
                achado = (a, simbolo, apelido)
    if achado:
        return (achado[1], achado[2])

    # 2ª passada: sem pontuação nenhuma ("sp-500" e "s&p500" viram "sp500").
    palavras = re.findall(r"[a-z0-9&.\-]+", t)
    compactas = [(_compacto(p), p) for p in palavras]
    compactas = [(c, p) for c, p in compactas if len(c) >= 2]
    for apelido, simbolo in SIMBOLOS_MERCADO.items():
        a = _compacto(apelido)
        if len(a) >= 3 and any(c == a for c, _ in compactas):
            return (simbolo, apelido)

    # 3ª passada: semelhança, para a transcrição torta ('smp500' -> 'sp500').
    # O corte é alto de propósito: 'ouro' e 'euro' dão 0,75 e NÃO podem casar.
    melhor, nota_melhor = None, 0.0
    for apelido, simbolo in SIMBOLOS_MERCADO.items():
        a = _compacto(apelido)
        if len(a) < 4:
            continue                       # sigla curta erra demais por som
        for c, _ in compactas:
            if len(c) < 4:
                continue
            import difflib
            nota = difflib.SequenceMatcher(None, c, a).ratio()
            if nota >= 0.85 and nota > nota_melhor:
                melhor, nota_melhor = (simbolo, apelido), nota
    if melhor:
        return melhor

    # 4ª passada: TICKER DE AÇÃO, que a tabela de apelidos nunca vai cobrir.
    #
    # Log de 13/08, 12:15 a 12:39. Ele perguntou quatro vezes sobre HAPV3 e
    # recebeu, nesta ordem: manchetes do Yahoo sobre Birkenstock e Blue Bird,
    # "não tenho acesso direto aos dados do Ibovespa", "sugiro que você tire
    # um print do gráfico do Ibovespa", e de novo manchetes aleatórias. No
    # meio disso, 'nasdaq' e 'ibovespa' funcionaram perfeitamente — porque
    # estavam na tabela de apelidos escrita à mão.
    #
    # Uma tabela de apelidos nunca vai ter as 400 ações da B3. Mas o FORMATO
    # de um ticker da B3 é inconfundível: quatro letras e um dígito (PETR4,
    # VALE3, HAPV3, ITUB4). Nenhuma palavra do português tem essa forma, então
    # reconhecer o padrão não gera falso positivo — e o Yahoo aceita esses
    # papéis com o sufixo .SA.
    for m in re.finditer(r"(?<![A-Za-z0-9])([A-Za-z]{4}\d{1,2})(?![A-Za-z0-9])",
                         str(texto or "")):
        papel = m.group(1).upper()
        # CONTRATO FUTURO TEM A MESMA FORMA E NÃO É AÇÃO. 'MESU6' é quatro
        # letras e um dígito igualzinho a 'HAPV3' — mas é o Micro E-mini de
        # setembro, não um papel da B3. Mandar isso ao Yahoo como 'MESU6.SA'
        # devolveria nada, ou pior, outra coisa. O teste pegou.
        if _e_contrato_conhecido(papel):
            continue
        return (f"{papel}.SA", papel)
    return None

def cotacao_mercado(simbolo):
    """Preço REAL do ativo, direto do Yahoo Finance. Sem chave, sem cota.
    Devolve dict ou None. É o que impede a IA de inventar cotação."""
    def buscar():
        try:
            r = _web_get(f"https://query1.finance.yahoo.com/v8/finance/chart/"
                         f"{requests.utils.quote(simbolo)}",
                         params={"interval": "1d", "range": "5d"}, timeout=10)
            m = r.json()["chart"]["result"][0]["meta"]
            preco = m.get("regularMarketPrice")
            anterior = m.get("chartPreviousClose") or m.get("previousClose")
            if preco is None:
                return None
            var = (preco - anterior) if anterior else None
            return {
                "simbolo": m.get("symbol", simbolo),
                "preco": preco,
                "moeda": m.get("currency", ""),
                "fechamento_anterior": anterior,
                "variacao": var,
                "variacao_pct": (var / anterior * 100) if (var and anterior) else None,
                "maxima": m.get("regularMarketDayHigh"),
                "minima": m.get("regularMarketDayLow"),
                "hora": time.strftime("%H:%M"),
                "fonte": "Yahoo Finance",
            }
        except Exception:
            return None
    return _web_cacheado(f"cot:{simbolo}", 60, buscar)

def _data_do_item(texto):
    """As casas publicam a data em três formatos diferentes. Devolve timestamp
    ou None — sem quebrar por causa de um feed com formato exótico."""
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        import email.utils
        d = email.utils.parsedate_to_datetime(texto)      # "Tue, 04 Aug 2026 …"
        if d:
            return d.timestamp()
    except Exception:
        pass
    for formato in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(texto[:19], formato).timestamp()
        except ValueError:
            continue
    return None

def noticias_do_mercado(maximo=8, termo=None, fontes=None):
    """Manchetes frescas das casas de mercado, via RSS público. Sem chave.
    Devolve lista de dicts (titulo, fonte, url, quando, resumo), do mais novo
    para o mais velho. `termo` filtra por assunto ('inflação', 'fed', 'S&P')."""
    def buscar():
        import xml.etree.ElementTree as ET
        import html as _html

        def um_feed(par):
            """Baixa e converte UM feed. Erro aqui não derruba os outros."""
            nome, url = par
            saida = []
            try:
                r = _web_get(url, timeout=6)
                raiz = ET.fromstring(r.content)
            except Exception:
                return saida                 # feed fora do ar: ignora este
            for item in raiz.findall(".//item")[:20]:
                titulo = (item.findtext("title") or "").strip()
                if not titulo:
                    continue
                resumo = re.sub(r"<[^>]+>", " ",
                                item.findtext("description") or "")
                saida.append({
                    "titulo": _html.unescape(titulo),
                    "fonte": nome,
                    "url": (item.findtext("link") or "").strip(),
                    "quando": _data_do_item(item.findtext("pubDate") or
                                            item.findtext("published")),
                    "resumo": _html.unescape(re.sub(r"\s+", " ", resumo)).strip()[:300],
                })
            return saida

        # EM PARALELO, de propósito. Buscar os seis feeds um atrás do outro
        # custava até 48 segundos (6 × 8s de timeout) ANTES de a IA começar a
        # pensar — era a maior parte da demora que ele sentia no chat. Agora o
        # tempo total é o do feed mais lento, não a soma de todos.
        alvos = list(fontes or FONTES_NOTICIAS)
        colhidas = []
        try:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(8, len(alvos) or 1)) as pool:
                for parcial in pool.map(um_feed, alvos):
                    colhidas.extend(parcial)
        except Exception:
            for par in alvos:                # sem threads: modo antigo
                colhidas.extend(um_feed(par))
        colhidas.sort(key=lambda n: n["quando"] or 0, reverse=True)
        return colhidas
    todas = _web_cacheado("noticias", 180, buscar) or []
    if termo:
        alvo = _norm_busca(termo)
        chaves = [w for w in re.findall(r"[a-z0-9&]+", alvo) if len(w) >= 3]
        if chaves:
            filtradas = [n for n in todas
                         if any(k in _norm_busca(n["titulo"] + " " + n["resumo"])
                                for k in chaves)]
            if filtradas:
                todas = filtradas
    return todas[:maximo]

def buscar_na_web(consulta, maximo=5):
    """Busca aberta na internet, sem chave. Devolve lista (titulo, url, resumo).
    Lista vazia = não deu para pesquisar agora; quem chama tem de dizer isso ao
    trader, NUNCA responder de cabeça no lugar."""
    def buscar():
        import html as _html
        achados = []
        try:
            r = _web_get("https://html.duckduckgo.com/html/",
                         params={"q": consulta, "kl": "br-pt"}, timeout=12)
            bruto = r.text
            blocos = re.findall(
                r'result__a[^>]*href="(?P<u>[^"]+)"[^>]*>(?P<t>.*?)</a>'
                r'(?:.*?result__snippet[^>]*>(?P<s>.*?)</a>)?',
                bruto, re.S)
            for u, t, s in blocos[:maximo]:
                titulo = re.sub(r"<[^>]+>", "", t).strip()
                if not titulo:
                    continue
                achados.append({
                    "titulo": _html.unescape(titulo),
                    "url": _html.unescape(u),
                    "resumo": _html.unescape(
                        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or ""))).strip()[:300],
                })
        except Exception:
            return []
        return achados
    return _web_cacheado(f"busca:{_norm_busca(consulta)}", 300, buscar) or []

def _idade_texto(quando):
    if not quando:
        return ""
    minutos = max(0, (time.time() - quando) / 60)
    if minutos < 60:
        return f"há {minutos:.0f} min"
    if minutos < 60 * 36:
        return f"há {minutos / 60:.0f} h"
    return f"há {minutos / 1440:.0f} dia(s)"

_PESO_MANCHETE = [
    # o que de fato move índice, do mais forte para o mais fraco
    (6, ("fed", "fomc", "powell", "rate cut", "rate hike", "juros", "interest rate")),
    (6, ("cpi", "inflation", "inflacao", "pce", "payroll", "jobs report",
         "nonfarm", "unemployment")),
    (5, ("s&p", "sp 500", "nasdaq", "dow", "stocks", "wall street", "acoes",
         "bolsa", "market", "mercado", "rally", "selloff", "record")),
    (4, ("recession", "recessao", "gdp", "pib", "tariff", "tarifa", "war",
         "guerra", "oil", "petroleo", "opec")),
    (3, ("earnings", "balanco", "guidance", "resultados", "lucro")),
    (2, ("treasury", "yield", "dollar", "dolar", "bond")),
]

def relevancia_manchete(noticia):
    """Quanto essa manchete importa para QUEM OPERA ÍNDICE. Serve para
    responder 'qual a notícia mais impactante' — antes ela devolvia as seis
    primeiras da lista, que é ordem de horário, não de importância."""
    texto = _norm_busca(f"{noticia.get('titulo','')} {noticia.get('resumo','')}")
    nota = 0
    for peso, termos in _PESO_MANCHETE:
        if any(t in texto for t in termos):
            nota += peso
    # notícia velha vale menos: o pregão anda
    idade = noticia.get("quando")
    if idade:
        horas = max(0.0, (time.time() - idade) / 3600)
        nota -= min(4, int(horas / 3))
    return nota

def _mesma_noticia(a, b):
    """Duas casas publicando a mesma coisa não são duas notícias."""
    ta, tb = _norm_busca(a["titulo"]), _norm_busca(b["titulo"])
    if ta == tb:
        return True
    import difflib
    return difflib.SequenceMatcher(None, ta[:90], tb[:90]).ratio() >= 0.80

def selecionar_noticias(noticias, maximo=6, por_relevancia=False):
    """Escolhe o que mostrar: sem repetição e sem uma casa só dominando.

    No log de uso, as seis manchetes vinham TODAS do Investing.com — porque a
    ordenação é por horário e aquele feed publica em lote. Aqui as fontes se
    revezam, e títulos parecidos são colapsados."""
    unicas = []
    for n in noticias:
        if not any(_mesma_noticia(n, u) for u in unicas):
            unicas.append(n)
    if por_relevancia:
        unicas.sort(key=relevancia_manchete, reverse=True)
        return unicas[:maximo]
    # revezamento entre casas, preservando a ordem de novidade dentro de cada
    por_fonte = {}
    for n in unicas:
        por_fonte.setdefault(n["fonte"], []).append(n)
    escolhidas, rodada = [], 0
    while len(escolhidas) < maximo and any(v[rodada:] for v in por_fonte.values()):
        for fila in por_fonte.values():
            if rodada < len(fila) and len(escolhidas) < maximo:
                escolhidas.append(fila[rodada])
        rodada += 1
    return escolhidas

def formatar_cotacao(cot, apelido=""):
    """Cotação em frase natural — é lida em voz alta, então nada de tabela."""
    if not cot:
        return ""
    nome = apelido or cot["simbolo"]
    partes = [f"{nome} está em {cot['preco']:,.2f}"]
    if cot.get("variacao_pct") is not None:
        sinal = "alta" if cot["variacao"] >= 0 else "queda"
        partes.append(f"{sinal} de {abs(cot['variacao']):,.2f} pontos, "
                      f"{abs(cot['variacao_pct']):.2f} por cento no dia")
    if cot.get("maxima") and cot.get("minima"):
        partes.append(f"máxima do dia {cot['maxima']:,.2f} e mínima "
                      f"{cot['minima']:,.2f}")
    return ", ".join(partes) + f" (dado do {cot['fonte']}, às {cot['hora']})."

def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def ler_cenario_do_topico(item, cenario):
    """A parte que faz a resposta deixar de ser de manual: pega a teoria do
    tópico e AMARRA ao que está acontecendo na mesa dele agora.

    `cenario` é o dicionário montado por _cenario_da_mesa(): posição aberta,
    última leitura do gráfico, sugestão pendente, preço real e estado do motor.
    Devolve a leitura aplicada, ou "" quando não há nada de concreto a dizer —
    inventar ligação é pior que não fazer nenhuma."""
    if not item or not cenario:
        return ""
    tema = _norm_busca(item.get("t", ""))
    pos = cenario.get("posicao") or {}
    ua = cenario.get("analise") or {}
    cot = cenario.get("cotacao") or {}
    linhas = []

    # --- Posição aberta: é o que ele mais precisa ouvir aplicado ---
    if pos:
        entrada, atual = _num(pos.get("entry")), _num(cot.get("preco"))
        direcao = str(pos.get("direcao", "")).upper()
        contra = None
        if entrada and atual:
            subiu = atual > entrada
            contra = (subiu and direcao in ("SELL", "VENDA")) or \
                     (not subiu and direcao in ("BUY", "COMPRA"))
        if "revers" in tema:
            linhas.append(
                f"No SEU caso agora: você está {direcao} {pos.get('ativo','')} "
                f"em {pos.get('entry')}" +
                (f", e o preço está em {atual:,.2f}" if atual else "") +
                (". Essa posição está CONTRA o movimento do momento, então "
                 "vale conferir uma a uma as quatro etapas acima — se elas não "
                 "estavam presentes na entrada, o trade foi contra a tendência "
                 "sem confirmação, que é exatamente o cenário mais caro."
                 if contra else
                 ". Enquanto as quatro etapas seguirem válidas, não há motivo "
                 "para antecipar a saída."))
        elif any(k in tema for k in ("stop", "alvo", "gestao", "drawdown", "r:r",
                                     "risco")):
            # SEM STOP REGISTRADO não é "stop None": é um buraco de risco, e
            # tem de vir primeiro, com essas palavras.
            tem_stop = _num(pos.get("stop")) is not None
            tem_alvo = _num(pos.get("tp1")) is not None
            linhas.append(
                f"Aplicando à sua posição aberta: {direcao} {pos.get('ativo','')} "
                f"@ {pos.get('entry')}, " +
                (f"stop {pos.get('stop')}" if tem_stop
                 else "⚠️ SEM STOP registrado") + ", " +
                (f"alvo {pos.get('tp1')}" if tem_alvo else "sem alvo definido") +
                (f", P&L agora de US$ {_num(pos.get('pnl_atual')) or 0:+,.2f}"
                 if pos.get("pnl_atual") is not None else "") + ".")
            # O MOTOR JÁ CALCULOU ISSO — e era exatamente o que ficava de fora.
            # Antes, este ramo só olhava a posição registrada; a leitura fresca
            # do gráfico (que traz stop e alvo REAIS, com as confluências que os
            # justificam) só era usada quando NÃO havia posição aberta. Ou seja:
            # justo quando ele tinha dinheiro na mesa e perguntava "onde ponho o
            # stop?", a ferramenta respondia com o aforismo do manual e ignorava
            # o número que ela mesma tinha acabado de ler.
            m_stop, m_alvo = _num(ua.get("stop")), _num(ua.get("tp1"))
            mesmo_ativo = (str(ua.get("ativo", "")).upper() ==
                           str(pos.get("ativo", "")).upper())
            if mesmo_ativo and (m_stop is not None or m_alvo is not None):
                partes = [f"O MOTOR leu {ua.get('ativo')} às "
                          f"{ua.get('hora','—')} e calculou: "
                          + " · ".join(
                              ([f"stop {m_stop:g}"] if m_stop is not None else [])
                              + ([f"alvo {m_alvo:g}"] if m_alvo is not None else [])
                              + ([f"2º alvo {_num(ua.get('tp2')):g}"]
                                 if _num(ua.get("tp2")) is not None else []))
                          + "."]
                if ua.get("confluencias"):
                    partes.append("O que sustenta esses níveis: "
                                  + " · ".join(str(c) for c in
                                               list(ua["confluencias"])[:5]) + ".")
                # A leitura do motor pode ser do LADO OPOSTO ao dele. Dizer isso
                # é obrigatório: senão ele copia um stop que foi calculado para
                # a operação contrária.
                lado_motor = str(ua.get("acao", "")).upper()
                if lado_motor and direcao and lado_motor[:1] != direcao[:1]:
                    partes.append(
                        f"⚠️ Atenção: essa leitura do motor é de {lado_motor}, "
                        f"e você está {direcao}. Os níveis acima foram "
                        "calculados para a operação no OUTRO sentido — sirva-se "
                        "deles como mapa da liquidez, não como o seu stop.")
                elif not tem_stop:
                    partes.append(
                        f"Como você está SEM stop na plataforma e a leitura do "
                        f"motor é do mesmo lado, o número dele — {m_stop:g} — é "
                        "o candidato direto: é onde a leitura que gerou o "
                        "cenário deixa de valer." if m_stop is not None else "")
                linhas.append(" ".join(p for p in partes if p))
            elif not tem_stop:
                linhas.append(
                    "O motor ainda não tem leitura fresca deste ativo para eu "
                    "tirar o nível de você. Diga 'tira um print' que eu capturo "
                    "e leio agora — prefiro isso a chutar um número.")
        elif contra:
            linhas.append(
                f"Vale para agora: você está {direcao} {pos.get('ativo','')} "
                "contra o movimento do momento — leia o que está acima com essa "
                "posição em mente.")

    # --- Sem posição, mas com leitura recente do gráfico ---
    elif ua.get("ativo"):
        if any(k in tema for k in ("revers", "checklist", "quando nao operar",
                                   "premium", "estrutura", "liquidez")):
            linhas.append(
                f"No gráfico que o motor leu às {ua.get('hora','—')}: "
                f"{ua.get('acao')} {ua.get('ativo')} em {ua.get('preco')}, "
                f"probabilidade {_num(ua.get('probabilidade')) or 0:.0f}%. "
                "Confira o que está acima contra essa leitura antes de decidir.")

    # --- Macro: amarra ao preço real e ao que ele opera ---
    if cot.get("preco") is not None and any(
            k in tema for k in ("juros", "payroll", "inflacao", "fomc", "vix",
                                "balanco", "petroleo", "recessao", "pmi",
                                "dia de noticia", "correlacao")):
        var = cot.get("variacao_pct")
        linhas.append(
            f"Referência de agora: {cenario.get('ativo_nome','o ativo')} está em "
            f"{cot['preco']:,.2f}" +
            (f", {'alta' if var >= 0 else 'queda'} de {abs(var):.2f}% no dia"
             if var is not None else "") +
            f" (dado do {cot.get('fonte','Yahoo Finance')}).")

    # --- Meta apertada muda o peso do conselho ---
    ritmo = cenario.get("ritmo_dia")
    if ritmo and any(k in tema for k in ("gestao", "risco", "drawdown",
                                         "quando nao operar", "checklist")):
        linhas.append(
            f"E lembre do seu plano: faltam US$ {cenario.get('falta', 0):,.0f} "
            f"em {cenario.get('dias_restantes', 0)} dia(s), o que exige "
            f"US$ {ritmo:,.0f} por dia. Prazo apertado é justamente quando o "
            "tamanho da posição deve ser respeitado, não aumentado.")
    return " ".join(linhas)

# "vire o ciclo do dia no painel de trading" / "o dia já virou, contabiliza"
_RE_VIRAR_DIA = re.compile(
    r"\b(vir(a|e|ar)|troca|troque|trocar|reinicia|recomeça|recomecar|"
    r"comeca|come[çc]ar|abre|abrir|abra)\b[^.!?]{0,30}?"
    r"\b(dia|ciclo do dia|pregao|preg[ãa]o|dia de opera[çc][ãa]o)\b"
    r"|\bnovo (dia|preg[ãa]o|ciclo do dia)\b"
    r"|\bo dia (j[áa] )?virou\b", re.I)

# "em que pregão estamos?", "o dia já virou?", "que dia de operação é hoje?"
_RE_QUAL_PREGAO = re.compile(
    r"\b(que|qual|em que)\b[^.!?]{0,25}?\b(preg[ãa]o|dia de opera[çc][ãa]o)\b"
    r"|\bo dia (j[áa] )?virou\s*\?"
    r"|\bque dia (de opera[çc][ãa]o )?(e|[ée]) hoje\b", re.I)

_RE_SAUDACAO = re.compile(
    r"^\s*(oi|ola|ol[áa]|e a[íi]|eai|opa|bom dia|boa tarde|boa noite|"
    r"tudo bem|tudo bom|como vai|como voc[êe] est[áa]|bom te ver|"
    r"cheguei|voltei|estou aqui|to aqui)\b[\s!,.?]*$", re.I)


def texto_do_pregao_atual(agora=None, cfg=None):
    """Em que pregão a mesa está AGORA, e por quê. Sem API, sem internet.

    Responde a pergunta que ele fez três vezes ('mas o dia já virou') com o
    número, o horário e a regra — em vez de com uma desculpa."""
    c = cfg if cfg is not None else carregar_config()
    ini = c.get("hora_inicio", PADRAO_CONFIG_APP["hora_inicio"])
    fim = c.get("hora_fim", PADRAO_CONFIG_APP["hora_fim"])
    agora = agora or datetime.datetime.now()
    dia = data_do_pregao(agora, c)
    vira = pregao_vira_o_dia(c)
    linhas = [f"📅 Pregão em curso: **{dia}** "
              f"(agora são {agora.strftime('%H:%M de %d/%m/%Y')})."
              , f"Horário configurado: das {ini} às {fim}."]
    if vira:
        linhas.append(
            f"O seu pregão ATRAVESSA A MEIA-NOITE: começa às {ini} e vai até "
            f"as {fim} do dia seguinte. Por isso o dia de operação vira às "
            f"{ini} — não às 00:00. Tudo que acontece de madrugada ainda "
            f"pertence ao pregão que começou às {ini}.")
    else:
        linhas.append("O seu pregão fecha no mesmo dia, então o dia de "
                      "operação é o dia do calendário.")
    try:
        n = len(operacoes_fechadas_hoje())
        linhas.append(f"Operações fechadas NESTE pregão: {n}.")
    except Exception:
        pass
    return "\n".join(linhas)


def responder_saudacao(texto, agora=None):
    """Devolve o cumprimento — ou None se não era um.

    A régua é a FRASE INTEIRA: 'bom dia' cumprimenta, 'bom dia, o que deu
    errado no stop?' é uma pergunta com um cumprimento na frente e tem de
    seguir para quem responde perguntas."""
    t = _sem_acento(str(texto or "")).strip()
    if not t or not _RE_SAUDACAO.match(t):
        return None
    h = (agora or datetime.datetime.now()).hour
    parte = "Bom dia" if h < 12 else ("Boa tarde" if h < 18 else "Boa noite")
    return (f"{parte}, Josevan. Estou aqui.\n\n"
            "Se quiser começar pelo de sempre: 'status' para o placar da conta, "
            "'olha o gráfico' para a leitura de agora, ou me pergunte "
            "direto — 'compro ou vendo?'.")


def responder_offline(pergunta, cenario=None):
    """A MELHOR resposta que dá para montar sem a API, nesta ordem:
    capacidades da ferramenta → base (SMC + macro) → cotação real → notícia
    relevante. Devolve texto pronto para o trader, ou None se não há nada.

    POR QUE ISSO EXISTE: antes, tudo que não estava na base virava um DESPEJO
    das mesmas seis manchetes — inclusive para "o que você pode fazer?",
    "acelere a fala" e "como te dou acesso à web?". Aquilo não respondia nada e
    ainda mostrava na tela o texto interno do prompt ("cite a fonte ao usar…"),
    que nunca deveria sair do bastidor."""
    if not (pergunta or "").strip():
        return None
    # CUMPRIMENTO. Do log de 12/08, 15:41:
    #     ❯ BOA TARDE
    #     ✳ "Não tenho como responder isso com segurança agora: não está na
    #        minha base, não consegui confirmar na internet, e a API está fora"
    # Responder "bom dia" nunca precisou de API, de internet nem de base de
    # conhecimento. Uma ferramenta que não sabe dizer boa tarde não parece
    # cuidadosa — parece quebrada, e contamina a confiança em tudo o mais.
    saudacao = responder_saudacao(pergunta)
    if saudacao:
        return saudacao
    if pergunta_sobre_capacidades(pergunta):
        return texto_das_capacidades()
    # HISTÓRICO DE SUGESTÕES: dado que está no disco dela. Vem antes da base
    # de metodologia porque "onde foi a última sugestão de venda de MGCV6?" é
    # pergunta de FATO REGISTRADO, não de conceito — e caía no despejo de
    # "não está na minha base" com o arquivo ali do lado.
    if pergunta_sobre_historico_sugestoes(pergunta):
        hist = responder_historico_sugestoes(pergunta)
        if hist:
            return hist
    # Base própria (metodologia + macro) responde de verdade a pergunta —
    # e, quando há cenário, a teoria vem AMARRADA ao que está na mesa dele.
    item = buscar_base_smc(pergunta)
    if item:
        do_conhecimento = responder_do_conhecimento(pergunta)
        leitura = ler_cenario_do_topico(item, cenario)
        return f"{do_conhecimento}\n\n{leitura}" if leitura else do_conhecimento
    # Cotação: quando ele pediu preço, OU quando citou um ativo e perguntou o
    # que aconteceu com ELE — porque "o que aconteceu com HAPV3 hoje?" é uma
    # pergunta sobre o PAPEL, e a resposta útil começa pelo que ele fez no dia.
    alvo = simbolo_do_texto(pergunta)
    p_norm = _norm_busca(pergunta)
    quer_preco = re.search(r"\b(cota[çc][ãa]o|pre[çc]o|quanto|quanto est|"
                           r"em quanto|valor|subiu|caiu|fechou|abriu|"
                           r"aconteceu|acontecendo|como (est[áa]|foi|ta))\b",
                           p_norm)
    if alvo and quer_preco:
        cot = cotacao_mercado(alvo[0])
        if cot:
            return formatar_cotacao(cot, alvo[1].upper())
        # PERGUNTOU DE UM ATIVO E EU NÃO ACHEI: isso se DIZ.
        # Log de 13/08: ele perguntou de HAPV3 quatro vezes e recebeu, entre
        # outras coisas, manchetes sobre Birkenstock e Blue Bird. Manchete de
        # OUTRA empresa não é resposta parcial sobre a dele — é ruído com cara
        # de resposta, e o pior tipo, porque parece que a ferramenta respondeu.
        return (f"Não consegui a cotação de **{alvo[1].upper()}** agora — a "
                "fonte não respondeu ou o papel não existe com esse código. "
                "Não vou te mostrar notícia de outra empresa como se fosse "
                "resposta. Confira o código (na B3 são quatro letras e um "
                "número, como PETR4 ou HAPV3) e me pergunte de novo.")
    # Notícia: só quando o assunto é notícia/mercado EM GERAL. Se ele citou um
    # ativo específico, a pergunta é sobre AQUELE ativo, e o bloco acima já
    # respondeu — despejar manchete geral aqui seria mudar de assunto.
    if not alvo and re.search(
            r"\b(not[íi]cia|manchete|aconteceu|acontecendo|movend|"
            r"impact|relevante|mercado hoje|por que|porqu[êe])\b", p_norm):
        return resumo_de_noticias(pergunta)
    return None

def resumo_de_noticias(pergunta="", maximo=5):
    """Notícia em forma de RESPOSTA: as mais relevantes para quem opera índice,
    sem repetição, sem uma casa só dominando, com fonte e hora."""
    # Se ele citou uma casa ("tem notícia na Nasdaq?"), a CASA manda. Nomes
    # como Nasdaq e Investing são casa e ativo ao mesmo tempo; filtrar pelos
    # dois ao mesmo tempo não sobrava nada.
    casa = None
    for nome, _ in FONTES_NOTICIAS:
        if _norm_busca(nome.split()[0]) in _norm_busca(pergunta):
            casa = nome
            break
    # Casa que ele citou mas que eu NÃO leio (Bloomberg, Reuters, Valor...).
    # Dizer isso é melhor que devolver as minhas fontes como se fossem a dele.
    aviso_casa = ""
    if not casa:
        for outra in ("bloomberg", "reuters", "valor", "financial times",
                      "wall street journal", "wsj", "exame", "estadao",
                      "globo", "cnn", "forbes", "barron"):
            if outra in _norm_busca(pergunta):
                aviso_casa = (
                    f"Eu não leio a {outra.title()} diretamente — as fontes que "
                    "eu acompanho são " +
                    ", ".join(n for n, _ in FONTES_NOTICIAS) +
                    ". Do que ELAS estão publicando agora:")
                break
    if casa:
        brutas = [n for n in noticias_do_mercado(maximo=60) if n["fonte"] == casa]
        if not brutas:                     # a casa não publicou nada agora
            brutas = noticias_do_mercado(maximo=40)
    else:
        alvo = simbolo_do_texto(pergunta)
        brutas = noticias_do_mercado(maximo=40, termo=alvo[1] if alvo else None)
    if not brutas:
        return None
    quer_ranking = bool(re.search(r"\b(mais impact|principal|mais important|"
                                  r"destaque|resum)", _norm_busca(pergunta)))
    escolhidas = selecionar_noticias(brutas, maximo=maximo,
                                     por_relevancia=quer_ranking)
    if not escolhidas:
        return None
    cabeca = aviso_casa or (
        "O que está pesando mais no mercado agora, na ordem de impacto:"
        if quer_ranking else
        "O que as casas de mercado estão publicando agora:")
    linhas = [cabeca]
    for n in escolhidas:
        linhas.append(f"• [{n['fonte']} · {_idade_texto(n['quando'])}] "
                      f"{n['titulo']}")
    linhas.append("São as manchetes das fontes, com a hora de publicação — não "
                  "interpretação minha. Se quiser, eu ligo alguma delas ao seu "
                  "cenário no gráfico.")
    return "\n".join(linhas)

# A pergunta pede DADO DE AGORA (cotação/notícia), ou é conversa que a própria
# ferramenta responde de cabeça? Só a primeira justifica ir à internet.
_RE_PRECISA_WEB = re.compile(
    r"\b(hoje|agora|neste momento|no momento|nesse momento|ultimas?|últimas?|"
    r"cota[çc][ãa]o|pre[çc]o|quanto (est[áa]|vale|custa|subiu|caiu)|"
    r"not[íi]cias?|manchetes?|aconteceu|acontecendo|fato relevante|"
    r"calend[áa]rio|agenda|payroll|cpi|fed|copom|juros|infla[çc][ãa]o|"
    r"por que .{0,30}(subiu|caiu|sobe|cai|despenc|dispar)|"
    r"abriu|fechou|abertura|fechamento|pr[ée]-mercado|premarket)\b",
    re.IGNORECASE)

def pergunta_precisa_da_web(texto):
    """Evita ir à internet à toa. 'O que é um order block' não precisa de RSS
    nenhum — e a busca custava segundos de espera em TODA pergunta, inclusive
    nas que a base local responde sozinha. Continua indo à web sempre que houver
    qualquer sinal de dado do momento; na dúvida, vai."""
    t = _norm_busca(texto) or ""
    if not t:
        return False
    if pergunta_conceitual(texto):
        return False                     # metodologia SMC/macro: base local
    return bool(_RE_PRECISA_WEB.search(t)) or bool(simbolo_do_texto(texto))

def bloco_web_para_prompt(texto):
    """Dados REAIS da web para injetar no prompt do modelo quando a pergunta é
    sobre o mercado de hoje. Serve de coleira: com o número e a manchete na
    mão, ele não tem por que inventar."""
    if not pergunta_precisa_da_web(texto):
        return ""
    partes = []
    alvo = simbolo_do_texto(texto)
    # Cotação e notícias EM PARALELO: são duas viagens à rede independentes, e
    # esperar uma para começar a outra só somava atraso.
    def _cot():
        return cotacao_mercado(alvo[0]) if alvo else None
    def _news():
        return noticias_do_mercado(maximo=6, termo=alvo[1] if alvo else None)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f_cot, f_news = pool.submit(_cot), pool.submit(_news)
            cot, noticias = f_cot.result(), f_news.result()
    except Exception:
        cot, noticias = _cot(), _news()
    if alvo and cot:
        partes.append("COTAÇÃO REAL AGORA (use estes números, não invente "
                      f"outros): {formatar_cotacao(cot, alvo[1].upper())}")
    if noticias:
        linhas = "\n".join(
            f"• [{n['fonte']}, {_idade_texto(n['quando'])}] {n['titulo']}"
            for n in noticias)
        partes.append("MANCHETES REAIS DO MERCADO AGORA (cite a fonte ao usar; "
                      f"não invente notícia que não esteja aqui):\n{linhas}")
    return "\n\n".join(partes)

# ====================================================================
# BASE DE CONHECIMENTO SMC NATIVA — a TIGER pensa sem gastar cota
# ====================================================================
# POR QUE ISSO EXISTE: toda pergunta ia para a API do Gemini, inclusive as que
# não precisavam — "o que é um CHoCH?" não depende de modelo nenhum, é
# metodologia fixa. Resultado: a cota gratuita estourava no meio do pregão e a
# ferramenta ficava MUDA justamente na hora em que ele mais precisava dela.
#
# Aqui mora o conhecimento SMC/ICT em texto, dentro do programa. É a MESMA
# metodologia que o motor usa para analisar o gráfico, então a resposta do chat
# e a leitura do robô nunca se contradizem. Custa zero, responde na hora e
# funciona sem internet.
#
# Os textos são escritos para serem LIDOS EM VOZ ALTA: nada de asterisco, sigla
# solta ou lista picotada.
BASE_SMC = [
    # O VERBETE MAIS BÁSICO DE TODOS — E ELE NÃO EXISTIA.
    # A base tinha 51 verbetes SOBRE conceitos de SMC e nenhum sobre o que SMC
    # É. Resultado: "O QUE É SMC?" não achava verbete, ia para o modelo, e o
    # modelo pequeno respondeu (12/08, 21:18) que Micro E-mini de índice é
    # "forex". Foi um teste do trader que encontrou o buraco.
    {"t": "SMC — o que é, de onde vem e o que ele afirma",
     "k": ["smc", "smart money concepts", "dinheiro inteligente",
           "o que e smc", "metodologia smc", "ict", "conceito de smart money"],
     "r": "SMC (Smart Money Concepts) é uma forma de LER O GRÁFICO partindo de "
          "uma premissa: o preço não passeia, ele é levado até onde há ordem "
          "parada. Quem move volume grande — mesa institucional, formador de "
          "mercado — não consegue comprar tudo o que quer num preço só; "
          "precisa de alguém do outro lado. Esse alguém está onde o varejo "
          "deixa stop: acima de topos óbvios e abaixo de fundos óbvios. Daí a "
          "leitura: o mercado sobe para BUSCAR os stops de venda, e desce para "
          "buscar os de compra.\n\n"
          "O QUE ISSO MUDA NA PRÁTICA: em vez de comprar rompimento, você "
          "espera o rompimento FALHAR (a varredura de liquidez), a estrutura "
          "virar (CHoCH), e entra na volta ao ponto de origem do movimento "
          "(order block) ou na ineficiência que ele deixou (FVG). Você compra "
          "em desconto e vende em prêmio, não o contrário.\n\n"
          "AS PEÇAS: estrutura (CHoCH, BOS, MSS), liquidez (BSL, SSL, topos e "
          "fundos iguais, inducement), zonas (order block, breaker, FVG) e "
          "contexto (premium/discount, killzones, Power of 3).\n\n"
          "O QUE SMC NÃO É: não é indicador, não é sistema automático e não é "
          "garantia. É um jeito de organizar o que se vê — e uma leitura "
          "errada continua sendo uma leitura errada, por mais bonito que seja "
          "o nome do padrão. Por isso, aqui na mesa, quem decide TAMANHO de "
          "posição e limite de perda não é a leitura: é o plano, em cálculo "
          "determinístico.\n\n"
          "ONDE SE APLICA: o SMC nasceu no mercado de câmbio e foi levado para "
          "índices, ações e cripto. O que você opera — MES/MESU6, o Micro "
          "E-mini S&P 500 — é um contrato FUTURO DE ÍNDICE de ações da CME, "
          "não é câmbio nem cripto. Vale US$ 5 por ponto, com tick de 0,25 "
          "ponto (US$ 1,25)."},

    {"t": "CHoCH (mudança de caráter)",
     "k": ["choch", "change of character", "mudanca de carater", "mudança de caráter",
           "virada de estrutura", "troca de carater",
           # como a transcrição de voz costuma escrever quando ele fala CHoCH
           "choque", "chock", "tchoch", "chorch"],
     "r": "CHoCH é a primeira virada de chave do gráfico: o sinal de que a mão "
          "mudou de lado. Numa estrutura de alta, ele acontece quando o preço "
          "quebra o último fundo que tinha gerado o topo mais alto. Numa "
          "estrutura de baixa, quando quebra o último topo que gerou o fundo "
          "mais baixo. Três coisas fazem um CHoCH valer: veio depois de uma "
          "varredura de liquidez num extremo, o CORPO da vela fechou além do "
          "nível (pavio que cruza e volta é manipulação, não CHoCH), e ele "
          "deixou para trás uma ineficiência ou um order block novo. O CHoCH "
          "não é ordem de entrada: é o alerta. A entrada vem quando o preço "
          "volta para testar a zona que ele deixou."},
    {"t": "BOS (rompimento de estrutura)",
     "k": ["bos", "break of structure", "rompimento de estrutura", "quebra de estrutura"],
     "r": "BOS é o rompimento de estrutura A FAVOR da tendência que já estava "
          "valendo: em alta, o preço fecha acima do topo anterior; em baixa, "
          "fecha abaixo do fundo anterior. Ele confirma que a tendência segue "
          "viva. A diferença para o CHoCH é essa: BOS continua a história, "
          "CHoCH muda a história. Depois de um BOS, o lugar de entrar é o "
          "recuo para o order block ou para o gap que causou o rompimento — "
          "não é correr atrás do preço no topo."},
    {"t": "MSS (deslocamento de estrutura)",
     "k": ["mss", "market structure shift", "deslocamento de estrutura",
           "displacement", "deslocamento"],
     "r": "MSS é o deslocamento de estrutura: um movimento rápido e agressivo "
          "que rompe o nível e deixa um rastro de ineficiência atrás. É a "
          "assinatura de ordem institucional grande entrando de uma vez. Um "
          "rompimento devagar, arrastado, vale muito menos que um deslocamento "
          "com vela larga e gap. Quando você vir MSS, marque a ineficiência que "
          "ele deixou: é para lá que o preço tende a voltar antes de seguir."},
    {"t": "Order Block",
     "k": ["order block", "ob", "bloco de ordem", "bloco de ordens",
           "order bloc", "orderblock", "order bloquio"],
     "r": "Order block é a última vela contrária antes do movimento que rompeu a "
          "estrutura. É onde a instituição montou posição, e por isso o preço "
          "costuma respeitar quando volta ali. Prefira o order block de ORIGEM, "
          "aquele que causou o deslocamento, e prefira o que ainda NÃO foi "
          "mitigado, ou seja, que o preço ainda não voltou para testar. Order "
          "block bom tem três marcas: causou rompimento de estrutura, deixou "
          "ineficiência logo depois, e está em zona de desconto para compra ou "
          "de prêmio para venda. Order block no meio do range vale pouco."},
    {"t": "Breaker block",
     "k": ["breaker", "breaker block", "bloco quebrado"],
     "r": "Breaker é um order block que FALHOU e virou do avesso. O preço "
          "atravessou aquela zona de defesa, os que estavam posicionados ali "
          "ficaram presos, e agora aquela mesma zona passa a funcionar do lado "
          "contrário: o que era suporte vira resistência e vice-versa. É uma "
          "das entradas mais fortes do SMC porque você opera junto de quem "
          "quebrou o nível e contra quem está preso lá dentro."},
    {"t": "Mitigation block",
     "k": ["mitigation", "mitigation block", "mitigacao", "mitigação",
           "mitigado", "nao mitigado", "não mitigado"],
     "r": "Mitigar é o preço voltar a uma zona para a instituição fechar ou "
          "equilibrar ordens que ficaram penduradas. Mitigation block é o bloco "
          "onde isso acontece. Na prática: uma zona não mitigada é uma zona "
          "com ordem esperando, e por isso ela atrai o preço. Depois de "
          "mitigada, ela perde força — testar duas ou três vezes o mesmo order "
          "block enfraquece a zona."},
    {"t": "FVG (gap de valor justo)",
     "k": ["fvg", "fair value gap", "gap de valor", "ineficiencia", "ineficiência",
           "desequilibrio", "desequilíbrio", "imbalance"],
     "r": "FVG é o buraco que um movimento rápido deixa no gráfico: um espaço "
          "de preço em que quase não houve negociação dos dois lados. Em três "
          "velas, é a distância entre o pavio da primeira e o pavio da terceira, "
          "quando a do meio passa correndo. O mercado tende a voltar para "
          "preencher esse vazio antes de continuar, porque é ali que ficou "
          "ordem por executar. Serve para duas coisas: como alvo de correção e "
          "como zona de entrada quando o preço volta nele a favor da estrutura. "
          "O ponto mais usado para entrar é o meio do gap."},
    {"t": "iFVG (FVG invertido)",
     "k": ["ifvg", "inversion fvg", "fvg invertido", "gap invertido"],
     "r": "iFVG é um FVG que o preço atravessou por inteiro em vez de respeitar. "
          "Quando isso acontece, ele inverte o papel: um gap de alta que foi "
          "perdido passa a funcionar como resistência na volta. É o mesmo "
          "raciocínio do breaker, só que aplicado à ineficiência. Sinaliza que "
          "a força mudou de lado com convicção."},
    {"t": "BPR (faixa de preço equilibrada)",
     "k": ["bpr", "balanced price range", "faixa equilibrada"],
     "r": "BPR é a sobreposição de dois FVG opostos, um de alta e um de baixa, "
          "na mesma faixa de preço. Como os dois lados deixaram ineficiência "
          "ali, essa região vira uma zona de decisão muito sensível: costuma "
          "produzir reação forte quando o preço volta nela. Trate como um POI "
          "de qualidade alta."},
    {"t": "Liquidez (BSL e SSL)",
     "k": ["liquidez", "bsl", "ssl", "buy side", "sell side", "liquidity",
           "onde esta a liquidez", "onde estao os stops", "onde estão os stops"],
     "r": "Liquidez é onde estão os stops parados, e é para lá que o preço "
          "PRECISA ir para as instituições preencherem ordem grande. Acima dos "
          "topos fica a liquidez de compra, os stops de quem está vendido. "
          "Abaixo dos fundos fica a liquidez de venda, os stops de quem está "
          "comprado. A pergunta-mestra de toda leitura SMC é essa: onde está a "
          "liquidez parada, quem está preso, e para onde o preço tem de ir para "
          "tomá-la. Liquidez externa fica nos extremos do range; interna fica "
          "nos gaps e order blocks dentro dele."},
    {"t": "Topos e fundos iguais (EQH e EQL)",
     "k": ["topos iguais", "fundos iguais", "eqh", "eql", "equal highs",
           "equal lows", "duplo topo", "duplo fundo", "topo duplo", "fundo duplo"],
     "r": "Topos iguais ou fundos iguais são um ímã de liquidez. Quando o preço "
          "faz dois topos no mesmo nível, todo mundo põe stop logo acima — e "
          "aquele bolo de stops vira alvo. No SMC, topo duplo não é sinal de "
          "reversão como no varejo: é sinal de que o preço vai buscar aquele "
          "nível para varrer. A reversão só entra na conta DEPOIS da varredura, "
          "quando o preço volta para dentro e dá CHoCH."},
    {"t": "Inducement (a isca)",
     "k": ["inducement", "isca", "idm", "armadilha"],
     "r": "Inducement é a isca: um topo ou fundo menor, colocado ANTES do ponto "
          "de interesse de verdade, cuja função é atrair entradas cedo e criar "
          "os stops que a instituição vai usar como combustível. Na prática, se "
          "você vê um order block bonito e, no caminho até ele, existe um fundo "
          "óbvio que ainda não foi pego, o preço quase sempre pega aquele fundo "
          "primeiro. Esperar o inducement ser varrido é o que separa entrar no "
          "lugar de entrar cedo demais."},
    {"t": "PDH, PDL, PWH e PWL",
     "k": ["pdh", "pdl", "pwh", "pwl", "maxima do dia anterior", "minima do dia anterior",
           "máxima do dia anterior", "mínima do dia anterior", "topo da semana"],
     "r": "São os níveis de referência que o mercado inteiro enxerga: máxima e "
          "mínima do dia anterior, e máxima e mínima da semana anterior. Como "
          "todo mundo vê, todo mundo põe ordem e stop perto deles — e por isso "
          "eles concentram liquidez. Servem tanto como alvo de um movimento "
          "quanto como o lugar onde uma varredura acontece antes da virada."},
    {"t": "Turtle soup e SFP (falha de rompimento)",
     "k": ["turtle soup", "sfp", "swing failure", "falso rompimento",
           "varredura de liquidez", "sweep", "pavio que volta"],
     "r": "É a varredura clássica: o preço fura um topo ou fundo importante, pega "
          "os stops, e FECHA de volta para dentro do range. O pavio passa, o "
          "corpo não. Isso é manipulação, não rompimento. Quando aparece num "
          "extremo do range e vem seguido de CHoCH, é um dos gatilhos de "
          "reversão mais confiáveis que existem — e é justamente o que o motor "
          "procura antes de sugerir contra a tendência de curto prazo."},
    {"t": "Judas swing",
     "k": ["judas", "judas swing", "abertura falsa"],
     "r": "Judas swing é o movimento falso do começo da sessão: o preço sai da "
          "abertura para um lado, engana quem entrou na direção óbvia, e depois "
          "vira e vai para o outro. O nome vem da traição. Acontece muito nas "
          "primeiras horas de Londres e de Nova York. Regra prática: não "
          "confie no primeiro impulso da abertura sem ver estrutura confirmando."},
    {"t": "Premium e discount",
     "k": ["premium", "discount", "discaunt", "premio e desconto",
           "prêmio e desconto", "zona de desconto", "zona de premio",
           "caro ou barato", "equilibrio do range", "equilíbrio do range"],
     "r": "Pegue o range que interessa, do fundo ao topo, e marque o meio. Acima "
          "do meio é prêmio, ou seja, caro: é ali que se VENDE. Abaixo do meio é "
          "desconto, barato: é ali que se COMPRA. Instituição não compra caro "
          "nem vende barato, e essa é a peneira mais simples e mais poderosa do "
          "SMC. Se o setup parece bonito mas está do lado errado do meio do "
          "range, ele não é bom — é ansiedade."},
    {"t": "OTE (entrada ótima)",
     "k": ["ote", "optimal trade entry", "entrada otima", "entrada ótima",
           "61.8", "70.5", "79"],
     "r": "OTE é a faixa mais eficiente do recuo, entre 61,8 e 79 por cento da "
          "correção, com o coração em 70,5. Entrar nessa faixa dá o melhor "
          "risco-retorno porque o stop fica curto, logo além do extremo, e o "
          "alvo continua lá na liquidez oposta. É o que transforma um trade "
          "mediano de 1 para 1 num trade de 1 para 3."},
    {"t": "Power of 3 (acumulação, manipulação, distribuição)",
     "k": ["power of 3", "po3", "acumulacao", "acumulação", "manipulacao",
           "manipulação", "distribuicao", "distribuição", "amd"],
     "r": "Todo movimento institucional tem três fases. Primeiro a acumulação: o "
          "preço anda de lado num range apertado enquanto a posição é montada. "
          "Depois a manipulação: um empurrão falso para o lado errado, que varre "
          "os stops e dá o preço bom para quem está montando. Por último a "
          "distribuição: o movimento real, na direção contrária à manipulação. "
          "Se você identificar em qual fase o gráfico está, sabe se espera, se "
          "toma cuidado ou se entra."},
    {"t": "Killzones (janelas de horário)",
     "k": ["killzone", "kill zone", "quilzone", "quill zone", "kiuzone",
           "melhor horario para operar", "melhor hora para operar",
           "sessao de londres", "sessão de londres", "abertura de nova york"],
     "r": "São as janelas em que o dinheiro grande de fato opera. Londres pela "
          "manhã costuma criar o movimento do dia. Nova York na abertura traz o "
          "maior volume e é onde a manipulação da madrugada normalmente se "
          "desfaz. A sessão da tarde em Nova York dá a continuação ou a "
          "realização. Fora dessas janelas, o mercado anda sem convicção e "
          "setup bonito falha mais. Um setup dentro de killzone merece MAIS "
          "confiança, não menos."},
    {"t": "Divergência SMT",
     "k": ["smt", "divergencia smt", "divergência smt", "correlacao", "correlação",
           "es nq", "indices correlacionados"],
     "r": "SMT é a divergência entre ativos que normalmente andam juntos, como "
          "S&P e Nasdaq. Se um faz topo mais alto e o outro não acompanha, a "
          "força do movimento é mentira: alguém está segurando. É um sinal "
          "antecipado e muito bom de exaustão, especialmente quando aparece "
          "junto de uma varredura de liquidez num extremo."},
    {"t": "Dealing range",
     "k": ["dealing range", "range de negociacao", "range de negociação", "faixa"],
     "r": "Dealing range é a faixa entre o último fundo relevante e o último topo "
          "relevante — o campo onde o jogo está sendo jogado agora. É a partir "
          "dele que você mede prêmio e desconto, e é dentro dele que ficam os "
          "gaps e order blocks que interessam. Trocar de dealing range no meio "
          "da análise é o erro que faz a leitura inteira sair errada."},
    {"t": "Risco e retorno (R:R)",
     "k": ["r:r", "risco retorno", "risco e retorno", "risco/retorno",
           "relacao risco retorno", "relação risco retorno", "um para dois"],
     "r": "R:R é quanto você ganha para cada unidade que arrisca. O plano desta "
          "mesa exige no mínimo 1 para 2: se o stop custa cem dólares, o alvo "
          "tem que valer pelo menos duzentos. Isso não é preciosismo, é "
          "matemática de sobrevivência: com 1 para 2, você fica no lucro "
          "acertando só 40 por cento das vezes. Com 1 para 1, precisa acertar "
          "mais de 50 por cento só para empatar, e ninguém sustenta isso. Se o "
          "setup não entrega 1 para 2, ele não é setup — é vontade de operar."},
    {"t": "Onde colocar o stop",
     "k": ["onde colocar o stop", "onde colocar stop", "stop loss",
           "invalidacao", "invalidação", "onde fica o stop", "stop"],
     "r": "O stop vai onde a IDEIA morre, não onde a dor aperta. Se você comprou "
          "num order block porque acredita que aquela zona segura, o stop fica "
          "logo abaixo do extremo que originou a zona — se o preço passar dali, "
          "a leitura estava errada e não há motivo para continuar. Stop apertado "
          "no meio do nada só serve para você ser varrido antes do movimento "
          "que você mesmo previu."},
    {"t": "Onde colocar o alvo",
     "k": ["onde colocar o alvo", "take profit", "onde realizar",
           "onde sair da operacao", "onde sair da operação", "alvo"],
     "r": "O alvo é a próxima liquidez do lado oposto: o topo ou fundo que ainda "
          "não foi pego, a máxima do dia anterior, um FVG que ficou aberto. Você "
          "entra onde a instituição entra e sai onde a instituição realiza. "
          "Alvo em número redondo escolhido por gosto é chute. Se entre a "
          "entrada e a próxima liquidez não cabe 1 para 2, o trade não vale."},
    {"t": "Gestão de risco e tamanho da posição",
     "k": ["gestao de risco", "gestão de risco", "tamanho da posicao",
           "tamanho da posição", "sizing", "quantos contratos",
           "risco por operacao", "risco por operação", "quanto arriscar"],
     "r": "O tamanho vem da conta, nunca da confiança no setup. Você define "
          "quanto por cento da margem topa perder por operação, mede a "
          "distância até o stop, e o número de contratos sai dessa divisão. Se "
          "o stop é largo, entram menos contratos; se é curto, entram mais — o "
          "prejuízo máximo continua o mesmo. Aumentar tamanho porque o setup "
          "parece óbvio é o que quebra conta. Nesta ferramenta esse cálculo é "
          "feito pelo plano da mesa, fora da IA, justamente para não depender "
          "de opinião."},
    {"t": "Drawdown e recuperação",
     "k": ["drawdown", "rebaixamento", "recuperar a conta",
           "recuperar o prejuizo", "recuperar o prejuízo", "quanto preciso ganhar para voltar"],
     "r": "Drawdown é a distância entre o topo do seu resultado e o vale depois "
          "dele. O detalhe cruel: perder 20 por cento exige ganhar 25 para "
          "voltar; perder 50 exige ganhar 100. Por isso proteger capital vale "
          "mais que caçar lucro. Depois de uma sequência ruim, o certo é "
          "DIMINUIR o tamanho e voltar ao setup mais óbvio do seu plano, não "
          "aumentar para recuperar rápido. Aumentar depois de perder é o "
          "caminho mais curto para quebrar a conta."},
    {"t": "Win rate e expectativa",
     "k": ["win rate", "winrate", "taxa de acerto", "expectativa matematica",
           "expectativa matemática", "expectativa positiva"],
     "r": "Taxa de acerto sozinha não diz nada. O que paga a conta é a "
          "expectativa: acerto vezes ganho médio, menos erro vezes perda média. "
          "Um sistema que acerta 40 por cento com 1 para 3 ganha muito mais que "
          "um que acerta 70 por cento com 1 para 0,5. Por isso o plano desta "
          "mesa cobra R:R mínimo em vez de cobrar acerto: é o R:R que sustenta "
          "o resultado quando a sequência ruim chega — e ela sempre chega."},
    {"t": "Checklist de entrada",
     "k": ["checklist", "checklist de entrada", "roteiro de entrada",
           "passo a passo para entrar", "quando entrar", "criterios de entrada",
           "critérios de entrada"],
     "r": "O roteiro é este, em ordem. Um: qual a estrutura do tempo gráfico "
          "maior, alta ou baixa. Dois: onde está a liquidez que o preço ainda "
          "não pegou. Três: o preço já varreu essa liquidez. Quatro: houve CHoCH "
          "ou deslocamento depois da varredura. Cinco: existe order block ou FVG "
          "para o preço voltar. Seis: essa zona está em desconto para comprar ou "
          "em prêmio para vender. Sete: o alvo até a liquidez oposta paga pelo "
          "menos 1 para 2. Se qualquer um desses falhar, não é entrada."},
    {"t": "Quando NÃO operar",
     "k": ["quando nao operar", "quando não operar", "ficar de fora",
           "nao trade", "melhor trade e o nao feito", "hora de nao operar"],
     "r": "Fique de fora quando o preço está no meio do range, sem prêmio nem "
          "desconto claro. Quando não houve varredura de liquidez nenhuma. "
          "Quando o setup só existe se você forçar a vista. Quando está fora de "
          "killzone e o volume sumiu. E principalmente quando você está "
          "operando por raiva, medo de ficar de fora, ou pressa de recuperar "
          "prejuízo — nesse estado o gráfico mostra o que você quer ver. O "
          "melhor trade do dia muitas vezes é o que não foi feito."},
    {"t": "Confluência",
     "k": ["confluencia", "confluência", "quantos fatores", "juntar sinais",
           "empilhar motivos"],
     "r": "Confluência é o empilhamento de motivos independentes apontando para "
          "o mesmo lugar: estrutura a favor, liquidez varrida, order block não "
          "mitigado, FVG aberto, zona em desconto, dentro da killzone. Um motivo "
          "sozinho é opinião; quatro juntos é cenário. Mas cuidado com a "
          "confluência inventada: repetir o mesmo argumento com três nomes "
          "diferentes não conta como três motivos."},
    {"t": "Volume, VWAP e indicadores como apoio",
     # AS PALAVRAS QUE GANHARAM TOPICO PROPRIO SAIRAM DAQUI. 'vwap', 'rsi',
     # 'media movel' e 'perfil de volume' agora tem cada um o seu verbete, com
     # profundidade. Deixa-las aqui tambem fazia os dois topicos EMPATAREM — e
     # a busca recusa empate de proposito, para nao chutar entre dois assuntos.
     # Resultado pratico: "o que e vwap?" nao era respondido por NENHUM dos
     # dois. Este verbete continua sendo o da FILOSOFIA (indicador confirma,
     # nao manda); o especifico responde o que cada um e.
     "k": ["indicadores como apoio", "volume confirma", "indicador confirma",
           "indicadores mandam", "indicadores no grafico", "indicadores no gráfico",
           "indicadores no smc", "confirmacao por indicador",
           "confirmação por indicador", "volume no rompimento"],
     "r": "No SMC os indicadores não mandam, eles confirmam. Volume alto no "
          "rompimento apoia a leitura de deslocamento real; volume fraco sugere "
          "armadilha. VWAP e o pico de volume funcionam como ímã de preço e "
          "combinam bem com zona de desconto. Divergência de momentum ajuda a "
          "antecipar exaustão perto de um extremo. Use como confluência "
          "adicional, nunca como o motivo principal da entrada."},
    {"t": "Como te dar acesso à web e como te treinar",
     "k": ["acesso a web", "acesso a internet", "te dar acesso", "como te treinar",
           "treinar melhor", "como te ensino", "como voce aprende",
           "voce tem internet", "voce acessa a internet", "precisa de api",
           "precisa de chave", "como te dou acesso"],
     "r": "Eu já tenho acesso à web, e ele não depende de chave nenhuma: a "
          "própria ferramenta busca cotação no Yahoo Finance e manchete em seis "
          "casas de mercado, direto, sem passar por API paga. Isso funciona "
          "mesmo com a cota da Gemini estourada. A chave da Gemini só é "
          "necessária para duas coisas: ler a imagem do gráfico e conversar "
          "livremente sobre assunto que não está na minha base. Se ela estourar, "
          "eu continuo respondendo metodologia, macro, preço e notícia. Para me "
          "TREINAR é ainda mais simples: termine qualquer frase com aprenda "
          "isso, por exemplo, nunca opere contra o H4 depois das quinze horas, "
          "aprenda isso. A regra fica gravada para sempre, vale em toda análise "
          "e sobrevive a fechar o programa. Pergunte o que você aprendeu para "
          "conferir a lista, e o que você sabe para ver todos os assuntos que "
          "eu domino sem gastar nada."},
    {"t": "Confirmação de reversão",
     "k": ["confirmacao de reversao", "confirmação de reversão", "confirmar reversao",
           "confirmar reversão", "sinal de reversao", "sinal de reversão",
           "reversao", "reversão", "reverter", "como saber que virou",
           "topo ou fundo", "pegar o topo", "pegar o fundo", "contra a tendencia",
           "contra a tendência"],
     "r": "Reversão confirmada tem quatro pernas, nesta ordem, e sem elas é "
          "chute contra a tendência — que é o jeito mais caro de operar. "
          "Primeira: o preço tem que estar num EXTREMO do range, em prêmio se "
          "você quer vender ou em desconto se quer comprar. No meio do caminho "
          "não existe reversão, existe continuação. Segunda: varredura de "
          "liquidez. O preço fura o topo ou o fundo, pega os stops, e o corpo "
          "da vela FECHA de volta para dentro. Se só o pavio passou e voltou, é "
          "manipulação, e é justamente isso que você quer ver. Terceira: CHoCH "
          "no tempo gráfico menor. Depois da varredura, o preço precisa quebrar "
          "a estrutura no sentido novo, com fechamento de corpo, não com pavio. "
          "É a assinatura de que a mão virou. Quarta: o recuo até o ponto de "
          "interesse que esse CHoCH deixou, um order block ou um FVG, e a "
          "reação ali. A entrada é nesse retorno, não no rompimento. "
          "Faltando qualquer uma das quatro, o certo é esperar. E tem um "
          "contra-sinal que cancela tudo: se o movimento contra o qual você quer "
          "operar veio com deslocamento forte e deixou ineficiência aberta, ele "
          "ainda tem combustível, e vender só porque subiu muito é entregar "
          "liquidez para quem está comprando."},
    {"t": "Estrutura interna e externa",
     "k": ["estrutura interna", "estrutura externa", "swing interno",
           "swing externo", "fractal", "tempo grafico maior", "tempo gráfico maior",
           "qual timeframe usar", "multi timeframe"],
     "r": "O preço é fractal: dentro de uma perna de alta do gráfico de quatro "
          "horas existem altas e baixas inteiras no de cinco minutos. Estrutura "
          "externa é a do tempo maior, e é ela que dá a direção. Interna é a do "
          "tempo menor, e é ela que dá o momento de entrar. O erro clássico é "
          "operar contra a externa porque a interna virou — isso é pegar faca "
          "caindo. Direção vem de cima, gatilho vem de baixo."},
    {"t": "VWAP — o que é, como usar e onde ela ENGANA",
     "k": ["vwap", "preco medio ponderado", "preço médio ponderado por volume",
           "vwap ancorada", "anchored vwap", "bandas da vwap", "desvio da vwap"],
     "r": "VWAP é o preço médio ponderado pelo VOLUME desde a abertura da "
          "sessão. Ela responde a uma pergunta específica: quem comprou hoje "
          "está no lucro ou no prejuízo? Preço acima da VWAP significa que o "
          "comprador médio do dia está ganhando — e é isso que a torna ímã e "
          "suporte dinâmico, não mágica de indicador. TRÊS USOS QUE VALEM: "
          "(1) viés intradiário — acima dela, procure compra em recuo; abaixo, "
          "venda em repique; (2) reversão à média — preço muito esticado da "
          "VWAP tende a voltar, e as BANDAS de desvio padrão (1σ, 2σ) medem "
          "esse esticamento; (3) confluência — VWAP colada num order block ou "
          "no POC é zona de reação forte, porque duas leituras independentes "
          "apontam o mesmo lugar. ONDE ELA ENGANA: em dia de tendência forte, "
          "esperar a volta na VWAP faz você perder o movimento inteiro; e "
          "perto do fim da sessão ela fica praticamente parada, porque o "
          "volume acumulado é grande demais para o preço mover a média. "
          "VWAP ANCORADA é a mesma conta começando num ponto que VOCÊ escolhe "
          "(a mínima do dia, o dia do payroll, o topo histórico) — serve para "
          "medir o preço médio de quem entrou NAQUELE evento. "
          "REGRA DA CASA: a VWAP é confluência, nunca o motivo da entrada."},
    {"t": "Perfil de volume — POC, VAH, VAL e nós de baixo volume",
     "k": ["perfil de volume", "volume profile", "poc", "vpoc", "vah", "val",
           "value area", "area de valor", "nó de baixo volume", "lvn", "hvn",
           "naked poc", "poc virgem"],
     "r": "O perfil de volume vira o gráfico de lado: em vez de volume por "
          "TEMPO, mostra volume por PREÇO. Ele responde onde o negócio "
          "realmente aconteceu. POC (Point of Control) é o preço com mais "
          "volume — o lugar onde comprador e vendedor mais concordaram. VALUE "
          "AREA é a faixa que concentra ~70% do volume, com VAH no topo e VAL "
          "na base. COMO SE OPERA: dentro da área de valor o mercado é "
          "rotacional (o certo é operar as bordas ou ficar de fora); fora "
          "dela, é tendência. HVN (nó de ALTO volume) é área de aceitação — o "
          "preço trava ali; LVN (nó de BAIXO volume) é área de rejeição — o "
          "preço atravessa rápido, e por isso LVN é bom alvo e péssimo lugar "
          "para stop. POC VIRGEM (naked POC) é um POC de sessão passada que o "
          "preço ainda não voltou a tocar: funciona como ímã, porque ficou "
          "negócio inacabado ali. LIGAÇÃO COM SMC: um LVN é a mesma coisa que "
          "um FVG vista por outro ângulo — ineficiência. Quando os dois "
          "apontam o mesmo preço, a leitura fica muito mais forte."},
    {"t": "RSI e divergência — o que ele realmente mede",
     "k": ["rsi", "indice de forca relativa", "índice de força relativa",
           "sobrecomprado", "sobrevendido", "divergencia", "divergência",
           "overbought", "oversold"],
     "r": "RSI mede a VELOCIDADE do movimento, não a direção nem o valor "
          "justo. É por isso que o erro mais caro do varejo é vender só "
          "porque o RSI passou de 70: em tendência forte o RSI FICA acima de "
          "70 por horas, e quem vendeu 'sobrecomprado' vira combustível para a "
          "alta continuar. O uso que se sustenta é a DIVERGÊNCIA: preço faz "
          "topo mais alto e o RSI faz topo mais baixo (divergência de baixa), "
          "ou preço faz fundo mais baixo e o RSI faz fundo mais alto "
          "(divergência de alta). Isso mostra que o movimento perdeu força — e "
          "AINDA ASSIM não é entrada: é aviso. A entrada continua vindo da "
          "estrutura (um CHoCH confirmando). Divergência sem quebra de "
          "estrutura é o clássico 'pegar faca caindo'. E a divergência vale "
          "muito mais quando aparece EM CIMA de um extremo de liquidez "
          "(depois de varrer um topo ou fundo) do que solta no meio do range."},
    {"t": "Médias móveis — o que servem e o que não servem",
     "k": ["media movel", "média móvel", "mm", "sma", "ema", "media de 200",
           "média de 200", "cruzamento de medias", "golden cross", "death cross",
           "media exponencial"],
     "r": "Média móvel é preço passado suavizado — ela ATRASA por definição, e "
          "isso não é defeito, é a natureza dela. SMA dá peso igual a todos os "
          "períodos; EMA dá mais peso ao recente e por isso vira mais rápido. "
          "O QUE SERVE: (1) ler a inclinação como contexto de tendência num "
          "olhar; (2) as médias longas (50, 200) funcionam como suporte e "
          "resistência porque MUITA gente olha para elas — é profecia "
          "autorrealizável, e ainda assim é real; (3) a distância do preço até "
          "a média mede esticamento. O QUE NÃO SERVE: cruzamento de médias "
          "como gatilho de entrada em intradiário — ele avisa depois que o "
          "movimento já aconteceu, e em mercado lateral vira uma máquina de "
          "prejuízo (o famoso chicote). NO SMC a média entra como CONFLUÊNCIA: "
          "um order block que coincide com a média de 50 é mais respeitado que "
          "um order block solto. A média nunca é o motivo da entrada."},
    {"t": "ATR — medir volatilidade antes de escolher o stop",
     "k": ["atr", "average true range", "volatilidade", "amplitude media",
           "amplitude média", "stop pelo atr"],
     "r": "ATR mede a amplitude média de uma vela num período — em outras "
          "palavras, quanto este mercado costuma andar AGORA. Serve para uma "
          "coisa que vale dinheiro: dimensionar o stop pelo que o mercado "
          "está fazendo, e não pelo que você gostaria de arriscar. Um stop "
          "menor que 1 ATR do tempo gráfico que você opera é ruído — ele será "
          "tocado por respiração normal do preço, não por invalidação de "
          "estrutura. Foi exatamente esse o erro que gerou o piso de ticks "
          "desta ferramenta: um stop de 1,87 ponto no MES é ruído, e dividir "
          "o risco por um número pequeno demais explodiu o número de "
          "contratos. USO PRÁTICO: stop entre 1 e 2 ATR além do nível que "
          "invalida a sua leitura; e se o alvo que sobra não paga o seu R:R "
          "mínimo com esse stop, a operação não existe — não aperte o stop "
          "para forçar a conta a fechar."},
    {"t": "Conta de mesa proprietária (APEX, Topstep) — o drawdown que se move",
     "k": ["apex", "prop firm", "mesa proprietaria", "mesa proprietária",
           "conta de avaliacao", "conta de avaliação", "trailing drawdown",
           "drawdown trailing", "drawdown que acompanha",
           "drawdown movel", "drawdown móvel", "pa account", "conta pa",
           "regra de consistencia", "regra de consistência", "topstep"],
     "r": "Conta de mesa proprietária tem regras que MATAM a conta antes de o "
          "mercado matar, e a maioria dos traders só descobre depois de "
          "perder. AS TRÊS QUE MAIS QUEBRAM CONTA: (1) DRAWDOWN QUE ACOMPANHA "
          "(trailing). O limite de perda não é fixo no saldo inicial — ele "
          "SOBE junto com o seu maior pico de saldo, inclusive o pico "
          "FLUTUANTE, em muitas mesas. Ou seja: você abre um lucro grande na "
          "tela, devolve, e o limite subiu no meio do caminho. Consequência "
          "prática: proteger lucro flutuante não é frescura, é sobrevivência. "
          "(2) REGRA DE CONSISTÊNCIA. Um único dia responder por uma fatia "
          "grande demais do lucro total costuma travar o saque. Um dia de "
          "sorte pode adiar o pagamento em semanas. (3) LIMITES DE HORÁRIO E "
          "DE NOTÍCIA — posição aberta no fechamento, ou operar em evento "
          "proibido, pode zerar a avaliação. O QUE ISSO MUDA NA MESA: com "
          "conta de mesa, o freio de operações por dia e o drawdown restante "
          "valem MAIS do que a leitura do gráfico. É por isso que esta "
          "ferramenta calcula o tamanho da posição pelo que SOBROU do "
          "drawdown, e não pelo drawdown cheio. Confirme sempre as regras "
          "atuais no painel da SUA mesa: elas mudam, e mudam sem aviso."},
    {"t": "Order flow, DOM e footprint — ler quem está agredindo",
     "k": ["order flow", "fluxo de ordens", "dom", "book", "livro de ofertas",
           "footprint", "tape", "times and trades", "absorcao", "absorção",
           "agressao", "agressão", "delta", "iceberg"],
     "r": "Order flow olha a MICRO: quem está atravessando o spread (agredindo) "
          "e quem está apenas parado ofertando (passivo). DELTA é a diferença "
          "entre volume agredido na compra e na venda. O sinal mais útil não é "
          "delta grande — é DELTA GRANDE SEM PREÇO ANDAR: isso é ABSORÇÃO, "
          "alguém grande segurando o outro lado, e costuma preceder reversão. "
          "ICEBERG é a ordem que recompõe: você vê 50 no book, come 50, e "
          "aparecem outros 50 — é institucional escondendo tamanho. NO DOM da "
          "Tradovate, os números da coluna são ordens LIMITE pendentes, que "
          "podem sumir num instante (spoofing existe): livro é intenção, tape "
          "é fato. COMO CASA COM SMC: o order block responde ONDE olhar; o "
          "order flow responde SE naquele lugar está mesmo entrando dinheiro. "
          "Zona SMC + absorção no tape é a confirmação mais rápida que "
          "existe — bem antes de fechar a vela."},
    {"t": "Correlação ES/NQ e divergência entre índices",
     "k": ["correlacao", "correlação", "es nq", "mes mnq", "divergencia smt",
           "indices correlacionados", "índices correlacionados", "russell",
           "dow", "confirmacao entre indices"],
     "r": "S&P (ES/MES) e Nasdaq (NQ/MNQ) andam quase sempre juntos porque "
          "compartilham as mesmas empresas grandes. Por isso a DISCORDÂNCIA "
          "entre eles carrega informação: quando o NQ faz um topo mais alto e "
          "o ES não acompanha, um dos dois está mentindo — e normalmente é o "
          "que fez o topo isolado, varrendo liquidez sem participação real. "
          "Isso é a divergência SMT aplicada. LEITURA PRÁTICA: NQ liderando "
          "para cima costuma indicar apetite por risco (tecnologia puxando); "
          "ES firme com NQ fraco indica rotação defensiva. E o Russell (RTY/"
          "M2K) é o mais sensível a juros — quando ele descola muito, "
          "geralmente a história do dia é taxa, não lucro das empresas. "
          "CUIDADO: correlação NÃO é sincronia perfeita; usar como gatilho "
          "isolado gera muito sinal falso. Serve para CONFIRMAR ou para "
          "DESCONFIAR de um rompimento — nunca para entrar sozinho."},
    {"t": "Aberturas de sessão — Ásia, Londres e Nova York",
     "k": ["sessao asiatica", "sessão asiática", "londres", "nova york",
           "abertura de nova york", "rth", "globex", "cash open",
           "sessao de negociacao", "horario de mercado", "overnight"],
     "r": "O dia do índice americano tem personalidades diferentes. ÁSIA "
          "(noite, horário de Brasília): volume baixo, faixa estreita — o "
          "range formado ali costuma virar liquidez a ser varrida depois, e "
          "operar dentro dele é operar ruído. LONDRES (madrugada/começo da "
          "manhã): entra volume de verdade, e é comum a primeira manipulação "
          "do dia — o Judas swing, que quebra o range da Ásia para o lado "
          "errado antes de ir para o certo. NOVA YORK (abertura do pregão à "
          "vista, 10:30 no horário de Brasília no horário padrão): é onde "
          "está o volume real do índice; os primeiros 30 minutos costumam "
          "definir a máxima ou a mínima do dia. O FECHAMENTO tem seu próprio "
          "fluxo (rebalanceamento, MOC) e é traiçoeiro para posição nova. "
          "IMPLICAÇÃO DIRETA: o mesmo setup vale coisas diferentes conforme a "
          "hora. Um rompimento na Ásia é suspeito por padrão; o mesmo "
          "rompimento na abertura de Nova York tem volume para se sustentar. "
          "Confirme o horário do SEU relógio — o horário de verão americano "
          "desloca tudo em uma hora."},
    {"t": "Notícia e evento — por que o gráfico mente no minuto",
     "k": ["noticia", "notícia", "payroll", "cpi", "fomc", "ata do fed",
           "evento economico", "evento econômico", "calendario economico",
           "calendário econômico", "dia de notícia", "volatilidade de evento"],
     "r": "Em evento macro (CPI, payroll, decisão do Fed) o preço não está "
          "descobrindo valor — está repreçando de uma vez só, com liquidez "
          "muito fina no livro. Três coisas mudam e todas contra você: o "
          "SPREAD abre, o SLIPPAGE vira regra (seu stop executa longe de onde "
          "está), e a estrutura de SMC perde valor preditivo por alguns "
          "minutos, porque o movimento não é fluxo institucional acumulando — "
          "é reação a um número. A PRIMEIRA reação frequentemente é falsa: é "
          "comum ir para um lado, varrer os stops, e ir para o outro. O QUE "
          "FAZER: saber a agenda ANTES de abrir a posição (não depois); não "
          "abrir posição nova nos minutos que antecedem o dado; e se já "
          "estiver posicionado, decidir de antemão — reduzir, proteger ou "
          "aceitar a volatilidade. Depois que o mercado assenta (geralmente "
          "15 a 30 minutos), a estrutura volta a valer, e aí o range criado "
          "pelo evento vira referência ótima de liquidez."},
    {"t": "Tilt, sequência de perdas e o custo psicológico do dia",
     "k": ["tilt", "psicologia", "emocional", "revenge trade", "vinganca",
           "vingança", "sequencia de perdas", "sequência de perdas",
           "overtrading", "medo", "ansiedade", "disciplina"],
     "r": "Depois de dois stops seguidos, o problema deixa de ser técnico. O "
          "que acontece é mensurável: o intervalo entre as operações encurta, "
          "o tamanho da posição aumenta, e o critério de entrada afrouxa — "
          "exatamente os três sinais do revenge trade. Nenhuma leitura de "
          "gráfico corrige isso, porque a leitura não é o que mudou; quem "
          "mudou foi quem está lendo. O QUE FUNCIONA, e é por isso que esta "
          "ferramenta tem freio: limite de operações por dia, pausa "
          "obrigatória após stops seguidos, e teto de perda diária — todos "
          "definidos ANTES do pregão, quando você ainda está frio, e "
          "executados por código, que não sente nada. Se o freio disparou e "
          "você está pensando em desligar para 'recuperar', essa vontade é "
          "exatamente o motivo pelo qual o freio existe. O melhor dia de um "
          "trader consistente é frequentemente aquele em que ele não operou."},
    {"t": "Diário de operações — o que anotar para melhorar de verdade",
     "k": ["diario de trading", "diário de trading", "journaling", "anotar",
           "registro de operacoes", "registro de operações", "estatistica",
           "estatística", "backtest", "avaliar desempenho"],
     "r": "Anotar só entrada, saída e resultado não melhora ninguém — isso o "
          "extrato da corretora já faz. O que muda o jogo é registrar o "
          "PORQUÊ e conseguir agrupar depois. O mínimo útil por operação: "
          "hora, ativo, direção, os níveis, o SETUP que a justificou (CHoCH "
          "em desconto? varredura de liquidez? continuação?), a killzone, se "
          "você seguiu o plano ou improvisou, e o resultado em R (não em "
          "dólar — R permite comparar dias de tamanhos diferentes). Com isso "
          "você responde as perguntas que realmente importam: qual setup "
          "meu paga? em que horário eu perco? minhas operações fora do plano "
          "dão lucro? A resposta quase sempre incomoda, e é justamente por "
          "isso que ela vale. Esta ferramenta grava tudo isso sozinha e usa o "
          "resultado para ajustar a probabilidade dos cenários — mas o campo "
          "que só você pode preencher é 'segui o plano ou não'."},
    {"t": "Spread, slippage e custo por operação",
     "k": ["spread", "slippage", "derrapagem", "custo por operacao",
           "custo por operação", "corretagem", "taxa", "comissao", "comissão",
           "tick de custo"],
     "r": "O custo real de uma operação é corretagem + taxas de bolsa + "
          "spread + slippage — e o trader que só olha a corretagem subestima "
          "o total. No MES, uma ida e volta custa tipicamente algo em torno "
          "de um tick e meio a dois ticks em custo total. Isso parece pouco "
          "até você fazer a conta: se o seu alvo médio é 8 ticks e o custo é "
          "2, você já entrega 25% do lucro bruto. É por isso que scalp de "
          "alvo curto exige acerto altíssimo para sobreviver — a matemática "
          "trabalha contra. SLIPPAGE aparece pior justamente quando dói: no "
          "stop, em movimento rápido, com ordem a mercado. Ordem STOP vira "
          "ordem a mercado quando toca — em evento macro ela pode executar "
          "vários ticks além. CONCLUSÃO PRÁTICA: inclua o custo no cálculo do "
          "R:R antes de aceitar a operação. Um R:R de 1:2 no papel que vira "
          "1:1,4 depois do custo não é o mesmo negócio."},
    {"t": "Projeção por desvio padrão e alvos medidos",
     "k": ["desvio padrao", "desvio padrão", "projecao", "projeção",
           "alvo medido", "measured move", "extensao de fibonacci",
           "extensão de fibonacci", "range esperado do dia", "adr"],
     "r": "Um alvo precisa vir de uma medida, não de um número redondo "
          "bonito. Três medidas que se sustentam: (1) MOVIMENTO MEDIDO — a "
          "perna de impulso projetada a partir do fim da correção; se a "
          "primeira perna andou 20 pontos, a segunda tende a andar algo "
          "próximo disso. (2) AMPLITUDE MÉDIA DO DIA (ADR) — se o mercado "
          "costuma andar 40 pontos por dia e já andou 35, o espaço que sobra "
          "para o seu alvo é pequeno, e isso vale mais que qualquer padrão "
          "bonito no gráfico. (3) EXTENSÕES (1,272 / 1,618) a partir da perna "
          "anterior, que funcionam menos por matemática e mais porque muita "
          "gente coloca ordem ali. O ALVO MAIS CONFIÁVEL, porém, não é "
          "nenhuma dessas: é a LIQUIDEZ VISÍVEL — o topo ou fundo óbvio onde "
          "há stops acumulados. Preço busca dinheiro parado, e dinheiro "
          "parado está em nível que todo mundo vê."},
    {"t": "Timeframes — como combinar sem se confundir",
     "k": ["tempo grafico", "tempo gráfico", "timeframe", "htf", "ltf",
           "multi timeframe", "top down", "grafico de 5 minutos",
           "gráfico de 5 minutos", "diario", "diário", "h4", "h1", "m15", "m5"],
     "r": "Trabalhar com mais de um tempo gráfico não é olhar mais gráficos: "
          "é dar um PAPEL diferente para cada um. O tempo MAIOR (diário, H4) "
          "define o VIÉS e as zonas que importam — nele você marca order "
          "blocks, FVGs e os pools de liquidez. O tempo MÉDIO (H1, M15) "
          "mostra a estrutura chegando na zona. O tempo MENOR (M5, M1) serve "
          "só para o GATILHO: o CHoCH que confirma a reação dentro da zona já "
          "escolhida lá em cima. O ERRO CLÁSSICO é inverter: achar o setup no "
          "M1 e depois procurar justificativa no diário. Isso não é análise, "
          "é confirmação de uma decisão já tomada. REGRA SIMPLES: se a zona "
          "não existe no tempo maior, o gatilho no tempo menor não vale nada. "
          "E uma leitura do M5 nunca revoga uma estrutura do diário — ela "
          "apenas informa o momento de entrar dentro dela."},
    {"t": "Trailing stop e gestão da posição aberta",
     "k": ["trailing", "trailing stop", "stop movel", "stop móvel",
           "breakeven", "zero a zero",
           "parcial", "realizar parcial", "gestao da posicao",
           "gestão da posição", "proteger lucro", "mover o stop"],
     "r": "Depois que a operação está aberta, cada mexida no stop é uma "
          "decisão nova — e a maioria delas piora o resultado. TRÊS "
          "ABORDAGENS QUE SE SUSTENTAM: (1) NÃO MEXER até o alvo ou o stop. É "
          "a mais chata e frequentemente a mais lucrativa, porque respeita a "
          "estatística do setup. (2) BREAKEVEN APÓS 1R. Reduz o estresse e o "
          "prejuízo médio, mas AUMENTA a frequência de operações zeradas que "
          "iriam ao alvo — o mercado respira, volta no seu preço de entrada e "
          "só depois vai. Só faz sentido se o seu setup costuma não retornar "
          "à entrada. (3) TRAILING PELA ESTRUTURA: mover o stop para trás do "
          "último fundo (em compra) a cada novo topo confirmado. É o único "
          "trailing que segue uma lógica de mercado em vez de uma distância "
          "arbitrária em pontos. O QUE NUNCA: AFASTAR o stop porque o preço "
          "está chegando nele. Isso transforma uma perda planejada numa perda "
          "sem tamanho definido, e é assim que se estoura uma conta em uma "
          "única operação. PARCIAL em 1R paga o custo psicológico, mas corta "
          "a cauda dos ganhos grandes — que é justamente de onde vem o "
          "resultado do mês."},
    {"t": "Open interest e o que ele diz sobre a força do movimento",
     "k": ["open interest", "contratos em aberto", "volume x open interest",
           "liquidacao", "liquidação", "rolagem", "roll", "vencimento",
           "contrato futuro"],
     "r": "Volume conta quantos contratos trocaram de mão; OPEN INTEREST conta "
          "quantos continuam ABERTOS. A combinação dos dois diz se o movimento "
          "tem dinheiro novo entrando ou é só gente saindo. Preço subindo com "
          "open interest subindo = dinheiro NOVO comprando, movimento com "
          "sustentação. Preço subindo com open interest CAINDO = vendedor "
          "cobrindo posição (short covering) — sobe forte e acaba rápido, "
          "porque acaba quando os vendedores terminam de sair. O mesmo vale "
          "invertido na queda. ROLAGEM: contratos futuros vencem, e nos dias "
          "que antecedem o vencimento a liquidez migra para o contrato "
          "seguinte — se você continuar operando o contrato velho, encontra "
          "spread pior e movimentos estranhos que não têm nada a ver com "
          "análise. O ticker traz o vencimento no nome (MESU6 = setembro de "
          "2026): confira se está no contrato onde o volume está."},
]

# --------------------------------------------------------------------
# BASE MACRO — o "e se" que todo trader pergunta, respondido offline
# --------------------------------------------------------------------
# "Se o Fed cortar juros amanhã a bolsa cai ou sobe?" e "se o payroll vier
# acima do esperado, o S&P sobe ou cai?" são perguntas de mesa, e as relações
# são estáveis: não mudam com a cota da API. Antes ela respondia essas com um
# DESPEJO DE MANCHETES, que não responde nada.
#
# Regra de honestidade que vale para todo texto daqui: a relação vem com o
# PORQUÊ e com a exceção. Mercado não é fórmula, e prometer direção é o jeito
# mais rápido de fazer o trader perder dinheiro confiando na ferramenta.
BASE_MACRO = [
    {"t": "Corte de juros do Fed e a bolsa",
     "k": ["fed cortar juros", "corte de juros", "cortar juros", "corte de taxa",
           "fed cortar", "juros caindo", "afrouxamento monetario",
           "fed baixar juros", "reducao de juros"],
     "r": "A reação de manual é bolsa SUBINDO: juro menor barateia o crédito, "
          "reduz o retorno da renda fixa e aumenta o valor presente do lucro "
          "futuro das empresas. Mas cuidado com a armadilha, porque ela é "
          "frequente: o que move o preço não é o corte, é o corte COMPARADO ao "
          "que já estava embutido. Se o mercado já esperava o corte, a notícia "
          "sai e o preço não anda, ou até cai na realização, o clássico compra "
          "no boato e vende no fato. E existe o corte que derruba a bolsa: "
          "quando ele vem por medo, um corte de emergência ou fora do "
          "calendário, o recado é que a economia está quebrando, e aí a queda "
          "vem junto. Olhe também o tom do comunicado e as projeções, porque "
          "muitas vezes elas mexem mais que a decisão em si. Na prática, para a "
          "nossa mesa: em dia de Fed o certo é esperar a primeira reação passar. "
          "O movimento inicial costuma ser manipulação, varre os stops dos dois "
          "lados, e o movimento real aparece depois. Sem estrutura e sem "
          "varredura confirmadas, é notícia, não é setup."},
    {"t": "Payroll acima ou abaixo do esperado",
     "k": ["payroll", "nfp", "non farm", "nonfarm", "folha de pagamento",
           "criacao de vagas", "emprego nos eua", "dados de emprego"],
     "r": "O payroll forte é uma faca de dois gumes, e é por isso que ele "
          "engana tanta gente. Economia forte é bom para o lucro das empresas, "
          "o que empurra a bolsa para cima; mas emprego forte demais significa "
          "salário pressionando a inflação, o que atrasa o corte de juros e "
          "derruba a bolsa. Qual dos dois manda depende do REGIME em que o "
          "mercado está: quando a preocupação é inflação, dado forte costuma "
          "derrubar a bolsa e subir o juro de dez anos; quando a preocupação é "
          "recessão, dado forte costuma subir a bolsa. Repare também no salário "
          "médio por hora e na revisão dos meses anteriores, que muitas vezes "
          "mexem mais que o número principal. Para a mesa: o payroll sai às "
          "nove e meia da manhã em Brasília, e os primeiros minutos são de "
          "pura varredura, com pavios enormes para os dois lados. Não é hora de "
          "operar rompimento. Espere o mercado escolher um lado, deixar "
          "estrutura e ineficiência, e opere o retorno."},
    {"t": "Inflação, CPI e o mercado",
     "k": ["inflacao", "inflação", "cpi", "pce", "indice de precos",
           "core cpi", "nucleo da inflacao", "quanto esta a inflacao"],
     "r": "A regra é simples: inflação acima do esperado empurra o juro para "
          "cima, e juro para cima pesa na bolsa, principalmente nas empresas de "
          "tecnologia e de crescimento, que valem pelo lucro lá na frente. "
          "Inflação abaixo do esperado faz o contrário e costuma dar alívio nos "
          "índices. O número que o mercado olha de verdade é o núcleo, que tira "
          "alimentos e energia por serem voláteis, e a comparação mês a mês, "
          "não só a de doze meses. O Fed persegue uma meta de dois por cento e "
          "acompanha mais o PCE que o CPI. Se você quer o número mais recente, "
          "eu não invento: peça que eu busco a manchete das casas de mercado, "
          "porque dado macro muda e chutar valor é o pior serviço que eu podia "
          "te prestar. Para a mesa: dia de CPI tem o mesmo comportamento do "
          "payroll, varredura primeiro, movimento real depois."},
    {"t": "Juro de 10 anos, dólar e a bolsa",
     "k": ["treasury", "juro de 10 anos", "10 anos", "dxy", "dolar forte",
           "yield", "renda fixa", "curva de juros", "tnx"],
     "r": "O juro de dez anos americano é o preço do dinheiro no mundo. Quando "
          "ele sobe rápido, a bolsa sofre, porque a renda fixa fica competitiva "
          "e o lucro futuro das empresas vale menos hoje. Quando ele cede, a "
          "bolsa costuma respirar. O dólar forte, medido pelo DXY, tende a "
          "pesar em commodities, em mercados emergentes e no lucro das "
          "multinacionais americanas. E tem um sinal clássico de alerta: quando "
          "o juro de dois anos fica ACIMA do de dez, a chamada curva "
          "invertida, historicamente é aviso de recessão à frente, embora o "
          "atraso entre o sinal e o evento seja longo e irregular. Para a mesa, "
          "vale como contexto de viés, não como gatilho de entrada."},
    {"t": "FOMC, comunicado e dot plot",
     "k": ["fomc", "reuniao do fed", "reunião do fed", "comunicado do fed",
           "dot plot", "powell", "coletiva do fed", "ata do fed"],
     "r": "A decisão em si costuma estar precificada; quem move o mercado é o "
          "COMUNICADO, o dot plot com a projeção de juros de cada membro, e a "
          "coletiva do presidente do Fed meia hora depois. O padrão de "
          "comportamento do preço é quase sempre o mesmo: reação forte na "
          "decisão, reversão durante a coletiva, e só então o movimento que "
          "vale para o resto da semana. É o dia mais perigoso do calendário "
          "para quem opera rompimento e um dos melhores para quem sabe esperar "
          "a varredura e entrar no retorno ao ponto de interesse."},
    {"t": "VIX e volatilidade",
     "k": ["vix", "indice do medo", "índice do medo", "volatilidade implicita",
           "volatilidade implícita", "mercado nervoso"],
     "r": "O VIX mede o medo embutido nas opções do S&P. Ele anda quase sempre "
          "ao contrário da bolsa: índice caindo forte, VIX disparando. Abaixo "
          "de quinze o mercado está calmo e as tendências são mais suaves; "
          "acima de vinte e cinco o ambiente é de estresse, com pavios enormes "
          "e stop sendo pego com muito mais facilidade. Para a mesa isso é "
          "dimensionamento: com VIX alto, o mesmo stop em pontos vale muito "
          "mais dinheiro, então o tamanho da posição precisa cair. VIX "
          "explodindo com o índice em queda livre e depois cedendo costuma "
          "marcar exaustão de pânico."},
    {"t": "Temporada de balanços",
     "k": ["balanco", "balanços", "earnings", "resultado das empresas",
           "temporada de resultados", "lucro das empresas", "guidance"],
     "r": "Nos balanços o que move não é o lucro reportado, é o lucro contra o "
          "esperado e, principalmente, a projeção que a empresa dá para os "
          "próximos trimestres. Empresa que bate o número e corta a projeção "
          "costuma cair. Como as gigantes de tecnologia têm peso enorme nos "
          "índices, o resultado de uma delas move o S&P e o Nasdaq inteiros. "
          "Para a mesa: balanço sai fora do pregão, então o risco é o gap de "
          "abertura, e gap não respeita stop. Carregar posição de um dia para "
          "o outro em semana de balanço das grandes é assumir um risco que o "
          "seu plano não calculou."},
    {"t": "Petróleo, commodities e inflação",
     "k": ["petroleo", "petróleo", "commodities", "opep", "brent", "wti",
           "energia", "preco do barril"],
     "r": "Petróleo em alta é inflação em alta, porque energia entra no custo "
          "de tudo. Inflação em alta atrasa o corte de juros e pesa na bolsa. "
          "Por isso choque de oferta, tensão geopolítica em rota de "
          "escoamento, corte de produção da OPEP, costuma aparecer no índice "
          "algumas horas depois, e não no mesmo minuto. Para a mesa, isso é "
          "contexto de viés do dia: se o barril disparou de madrugada, o índice "
          "abre com esse peso, e o cenário de compra precisa de mais "
          "confirmação que o normal."},
    {"t": "Recessão e ciclo econômico",
     "k": ["recessao", "recessão", "ciclo economico", "ciclo econômico",
           "pib", "gdp", "desaceleracao", "pouso suave", "soft landing"],
     "r": "A bolsa antecipa o ciclo, não o acompanha. Ela costuma cair ANTES da "
          "recessão aparecer nos dados e subir ANTES da recuperação aparecer, "
          "o que faz manchete de economia ruim conviver com mercado subindo. "
          "Os sinais que o mercado observa são a curva de juros invertida, o "
          "desemprego começando a subir de um fundo muito baixo, o PMI abaixo "
          "de cinquenta e o crédito encarecendo. Para a mesa isso é pano de "
          "fundo: define se o mercado está no regime em que dado forte é bom ou "
          "ruim, e ajuda a entender por que a mesma notícia move o preço em "
          "direções diferentes em épocas diferentes."},
    {"t": "PMI, ISM e indicadores de atividade",
     "k": ["pmi", "ism", "atividade economica", "atividade econômica",
           "industria", "indicador antecedente", "confianca do consumidor"],
     "r": "O PMI e o ISM são pesquisas com gerentes de compras e funcionam como "
          "termômetro antecipado da economia. Acima de cinquenta indica "
          "expansão, abaixo indica contração. Valem porque saem antes dos dados "
          "oficiais e porque a reação da bolsa depende do regime: em ambiente "
          "de medo de inflação, dado forte pode derrubar o índice; em ambiente "
          "de medo de recessão, dado forte anima. Para a mesa, esses números "
          "saem geralmente às onze da manhã em Brasília e produzem o mesmo "
          "padrão de varredura dos demais dados macro."},
    {"t": "Como operar em dia de notícia",
     "k": ["dia de noticia", "dia de notícia", "operar noticia",
           "agenda economica", "agenda econômica", "calendario economico",
           "calendário econômico", "evento importante", "sair dado"],
     "r": "A regra da mesa em dia de dado forte é uma só: não opere o "
          "rompimento do primeiro movimento. O que acontece na prática é que o "
          "preço dispara para um lado, pega os stops de quem entrou correndo, "
          "volta e só então escolhe a direção real. Isso é manipulação de "
          "livro. O jeito certo é deixar o primeiro impulso acontecer, marcar a "
          "liquidez que foi varrida e a ineficiência que o deslocamento "
          "deixou, esperar o CHoCH, e entrar no retorno ao ponto de interesse. "
          "Se você não consegue esperar, o melhor trade do dia é não operar. E "
          "com o tamanho reduzido, porque o stop em dia de notícia precisa ser "
          "mais largo que o normal."},
    {"t": "Correlação entre índices e ativos",
     "k": ["correlacao", "correlação", "es nq", "s&p e nasdaq", "ouro e dolar",
           "bitcoin e bolsa", "ativos correlacionados"],
     "r": "S&P e Nasdaq andam juntos, com o Nasdaq mais volátil por causa do "
          "peso da tecnologia; quando um faz topo novo e o outro não acompanha, "
          "isso é divergência SMT e costuma antecipar exaustão. Ouro sobe com "
          "medo e com juro real caindo, e sofre com dólar forte. Bitcoin tem se "
          "comportado como ativo de risco, andando com o Nasdaq nos movimentos "
          "grandes. Dólar forte pesa em commodities e emergentes. Para a mesa, "
          "correlação serve para confirmar ou desconfiar de um movimento: "
          "rompimento em um índice que o correlato não acompanha merece "
          "desconfiança."},
]

def _norm_busca(texto):
    """Minúsculas e sem acento — para casar 'ineficiencia' com 'ineficiência'."""
    return _sem_acento(str(texto or "")).lower()

def _parecido(palavra, chave, corte=0.78):
    """Semelhança tolerante para a transcrição de voz. O Google devolveu 'bola
    do CHOQUE' quando ele falou CHoCH — sem isso, a pergunta mais comum da mesa
    não achava resposta nenhuma."""
    import difflib
    return difflib.SequenceMatcher(None, palavra, chave).ratio() >= corte

def _nota_base_smc(item, p, palavras):
    """Quanto este tópico casa com a pergunta. Devolve (exata, aproximada).

    ESCALA: 3 = expressão inteira ("fair value gap"); 2 = jargão isolado
    ("choch", "fvg"). Palavra genérica não entra na lista de chaves,
    justamente para não pontuar.

    AS DUAS NOTAS ANDAM SEPARADAS de propósito. "reversão" e "recessão" são
    quase idênticas para o casamento por som, e empatavam: a pergunta sobre
    CONFIRMAÇÃO DE REVERSÃO caía em RECESSÃO. Com as notas separadas, quem
    casou EXATO sempre ganha de quem casou só por semelhança."""
    exata = aprox = 0
    # 'inflacao' e 'inflação' viram a mesma coisa ao normalizar; sem o set,
    # a mesma chave contava duas vezes e inflava a nota do tópico.
    for c in {_norm_busca(k) for k in item["k"] if _norm_busca(k)}:
        if " " in c:
            if c in p:
                exata += 3
            continue
        # jargão curto casa como palavra inteira, senão 'ob' casa dentro de
        # 'objetivo' e a resposta sai completamente errada
        if re.search(rf"\b{re.escape(c)}\b", p):
            exata += 2
        elif len(c) >= 4 and any(
                # chave longa é distintiva: dá para ser mais tolerante sem
                # risco de casar errado ('choque' -> 'choch' dá 0,73)
                _parecido(w, c, 0.72 if len(c) >= 5 else 0.80)
                for w in palavras):
            aprox += 2                     # transcrição torta da voz
    # O TÍTULO TAMBÉM PRECISA CASAR COMO PALAVRA INTEIRA.
    #
    # Log de 14/08, 23:34. Ele escreveu "boa note" (era "boa noite", com um
    # dedo errado) e recebeu uma AULA sobre OTE — a faixa de 61,8% a 79% do
    # recuo. Precisou responder "eu disse, boa noite" para ser entendido.
    #
    # A causa estava nesta linha: as CHAVES do verbete já casavam com `\b`
    # (foi o que impediu 'ob' de casar dentro de 'objetivo'), mas o TÍTULO
    # era comparado com um `in` cru. O título de OTE, cortado no parêntese,
    # é a string "ote" — e "ote" está dentro de "n-OTE". Pelo mesmo caminho
    # caíam "anote isso", "note que o preço caiu", "bote", "pote".
    #
    # Isto não era uma resposta a mais: desde a 2.30.0 a base é consultada
    # ANTES do modelo, então o falso positivo SEQUESTRAVA a pergunta e o
    # modelo nunca via o que foi perguntado. Sete verbetes têm título curto
    # (OTE, BOS, MSS, FVG, iFVG, BPR, CHoCH) e todos corriam o mesmo risco.
    titulo = _norm_busca(item["t"]).split(" (")[0]
    if titulo and re.search(rf"\b{re.escape(titulo)}\b", p):
        exata += 3
    return exata, aprox

def _todos_os_topicos():
    """As duas bases juntas: metodologia SMC e macro de mercado."""
    return list(BASE_SMC) + list(BASE_MACRO)

def buscar_base_smc(pergunta, minimo=2):
    """Acha o tópico da base que responde a pergunta. Devolve o item ou None.

    O CORTE MÍNIMO É 2 DE PROPÓSITO. Com corte 1, "e o que seria uma
    CONFIRMAÇÃO de reversão?" bateu na palavra 'confirmação' e ela respondeu
    sobre CONFLUÊNCIA — assunto completamente diferente do perguntado. Uma
    única palavra fraca nunca pode ganhar: ou o jargão aparece, ou a pergunta
    vai para quem sabe pesquisar (internet/modelo).

    Também exige DISTÂNCIA do segundo colocado: quando dois tópicos empatam, a
    pergunta é ambígua e responder qualquer um dos dois é chutar."""
    p = _norm_busca(pergunta)
    if not p:
        return None
    palavras = [w for w in re.findall(r"[a-z0-9:.]+", p) if len(w) >= 4]
    notas = []
    for item in _todos_os_topicos():
        exata, aprox = _nota_base_smc(item, p, palavras)
        if exata + aprox:
            notas.append(((exata, aprox), item))
    # Ordena por nota EXATA e só depois pela aproximada: quem tem o jargão
    # escrito ganha de quem só se parece com ele.
    notas.sort(key=lambda x: x[0], reverse=True)
    if not notas or sum(notas[0][0]) < minimo:
        return None
    # PARECER NÃO BASTA: SEM UM ACERTO EXATO, NÃO É O ASSUNTO.
    # Log de 13/08, 09:52. Ele perguntou "essa qualidade de print está muito
    # ruim, como fazemos para melhorar?" e recebeu o verbete de TRAILING STOP.
    # A nota foi 2,0 — e os DOIS pontos vieram só de semelhança de palavra,
    # com ZERO jargão realmente escrito na pergunta.
    #
    # Isso já era ruim antes; virou grave na 2.30.0, quando a base passou a ser
    # consultada ANTES do modelo — um falso positivo aqui não é mais uma
    # resposta a mais, é uma resposta que SEQUESTRA a pergunta e impede o
    # modelo de responder o que foi perguntado. Semelhança serve para
    # DESEMPATAR entre candidatos, nunca para eleger um sozinha.
    if notas[0][0][0] <= 0:
        return None
    if len(notas) > 1 and notas[1][0] == notas[0][0]:
        return None                        # empate real = ambíguo, não chuta
    return notas[0][1]

# Perguntas que a base responde sozinha: são de CONCEITO, não dependem do
# gráfico de agora nem da conta. "O que é um CHoCH" tem a mesma resposta hoje e
# daqui a um mês — não faz sentido gastar cota da API com isso.
_RE_CONCEITUAL = re.compile(
    r"(^|\b)(o que (é|e|sao|são|significa|caracteriza|define)|que (é|e) (um|uma)|"
    r"como (identific|reconhec|sab|us|funciona|defin|calcul)|"
    r"me (explica|explique|ensina|ensine|fala sobre|diga o que)|"
    r"explica(r|-me)?|qual (a|é a|e a) (diferen[çc]a|defini[çc][ãa]o|regra)|"
    r"para que serve|quando (usar|entrar|n[ãa]o operar)|"
    r"pra que serve|o que caracteriza)", re.IGNORECASE)

# Quando ele diz "NÃO PERGUNTEI SOBRE CONFLUÊNCIA, PERGUNTEI SOBRE CONFIRMAÇÃO
# DE REVERSÃO", a resposta anterior foi REJEITADA. Insistir na mesma fonte
# devolve o mesmo texto — foi o que aconteceu, duas vezes seguidas. Correção
# dele manda a pergunta para quem pesquisa (modelo/web), nunca para a base.
_RE_CORRECAO = re.compile(
    r"(n[ãa]o (foi|era) (isso|essa)|n[ãa]o perguntei|n[ãa]o [ée] isso|"
    r"n[ãa]o entendi|nada a ver|fora do contexto|voc[êe] errou|"
    r"repetiu|de novo a mesma|mesma resposta|eu perguntei sobre|"
    r"n[ãa]o foi o que (eu )?pedi|preste aten[çc][ãa]o)", re.IGNORECASE)

def e_correcao_do_trader(texto):
    """Ele está dizendo que a resposta anterior não serviu."""
    return bool(_RE_CORRECAO.search(_norm_busca(texto) or ""))

def pergunta_conceitual(texto):
    """É pergunta de metodologia (responde offline) e não sobre o gráfico
    de AGORA? Se ele cita 'agora', 'nesse gráfico' ou 'minha posição', o
    assunto é o mercado ao vivo e tem de ir para o modelo."""
    t = _norm_busca(texto)
    if not t or not _RE_CONCEITUAL.search(t):
        return False
    if re.search(r"\b(agora|nesse grafico|neste grafico|no grafico|minha posicao|"
                 r"minha operacao|hoje|meu status|desse print|na tela)\b", t):
        return False
    return True

def responder_do_conhecimento(pergunta, com_licoes=True):
    """Resposta LOCAL: base SMC + lições que ele ensinou. Zero cota, zero
    internet, resposta instantânea. Devolve o texto ou None."""
    item = buscar_base_smc(pergunta)
    if not item:
        return None
    partes = [item["r"]]
    if com_licoes:
        # Lição dele sobre o mesmo assunto vem junto e tem a última palavra.
        p = _norm_busca(pergunta)
        relacionadas = [l for l in carregar_licoes()
                        if any(_norm_busca(k) in _norm_busca(l) for k in item["k"])
                        or any(w in _norm_busca(l) for w in p.split() if len(w) > 4)]
        if relacionadas:
            partes.append("E você já me ensinou o seguinte sobre isso: " +
                          "; ".join(relacionadas[:3]) + ".")
    return " ".join(partes)

def indice_da_base_smc():
    """Os assuntos que ela domina offline — para ele saber o que pode perguntar
    sem gastar cota."""
    return [item["t"] for item in _todos_os_topicos()]

# --------------------------------------------------------------------
# O QUE ELA MESMA FAZ — precisa ser resposta local e exata
# --------------------------------------------------------------------
# "O QUE VOCÊ PODE FAZER?" recebia um despejo de manchetes. A ferramenta tem de
# saber descrever a si mesma sem depender de modelo nenhum.
def texto_das_capacidades():
    return (
        "Eu sou a TIGER, a IA desta mesa. Isto é o que eu faço de verdade.\n"
        "\n"
        "EXECUTO na ferramenta, é o app que faz: 'liga o motor' e 'desliga o "
        "motor'; 'zera o ciclo', que limpa o dashboard do Plano de Trading com "
        "confirmação; 'tira um print', que captura a tela da corretora na hora; "
        "'olha o gráfico', que analisa a última captura do motor; 'manda no "
        "whatsapp' e 'conecta o whatsapp'; 'acatar', 'dispensar' e 'cancelar "
        "ordem'; e 'status', com o placar da conta e o ritmo por dia.\n"
        "\n"
        "CONFIGURO a própria ferramenta quando você manda, e mostro o valor de "
        "antes e o de depois: horário em que o seu dia começa e termina, "
        "intervalo entre as análises, e os números do Plano de Trading da conta "
        "(margem, meta, prazo da meta, drawdown máximo, risco por operação, "
        "R:R mínimo, probabilidade mínima, prazo para acatar e início do "
        "ciclo). Diga como se fala mesmo: 'o dia da conta 1 começa às 19h', "
        "'analisa a cada 5 minutos', 'risco de 1% por operação', 'meta de 6 mil "
        "em 10 dias'. E para conferir: 'como está configurado o risco do plano "
        "da conta 1'.\n"
        "\n"
        "BUSCO na internet sozinha, sem gastar cota de API: cotação real com "
        "preço, variação e faixa do dia (S&P, Nasdaq, Dow, Russell, VIX, ouro, "
        "prata, petróleo, dólar, euro, bitcoin, Ibovespa e juros de dez anos), e "
        "notícia fresca de seis casas de mercado, sempre com a fonte e a hora.\n"
        "\n"
        "RESPONDO de cabeça, também sem cota: metodologia SMC inteira "
        "(estrutura, liquidez, order blocks, ineficiências, premium e desconto, "
        "confirmação de reversão, gestão de risco) e as relações de macro "
        "(Fed e juros, payroll, inflação, VIX, balanços, dia de notícia).\n"
        "\n"
        "ANALISO o que você me manda pelo anexo: print, foto, vídeo da tela, "
        "PDF e planilha.\n"
        "\n"
        "APRENDO com você: termine qualquer frase com 'aprenda isso' e a regra "
        "fica gravada para sempre. Pergunte 'o que você aprendeu?' para "
        "conferir, e 'o que você sabe?' para ver todos os assuntos.\n"
        "\n"
        "APRENDO TAMBÉM COM O SEU RESULTADO, sem você pedir: os padrões que vêm "
        "falhando NAS SUAS operações perdem pontos de probabilidade e passam a "
        "ser barrados; os que vêm acertando ganham. Isso entra na conta do "
        "cenário, não é só conversa.\n"
        "\n"
        "SEGURO A SUA MÃO quando o dia vira: depois de dois stops seguidos eu "
        "fico em silêncio por um tempo, paro de vez ao bater o teto de "
        "operações do dia ou o seu drawdown, e não viro de compra para venda no "
        "mesmo ativo sem convicção acima do piso. Pergunte 'por que você não "
        "está sugerindo nada?' que eu digo qual limite está segurando.\n"
        "\n"
        "O QUE EU NÃO FAÇO: não envio ordem para a corretora sozinha, não "
        "prometo direção do mercado, e não invento número. Se eu não tiver o "
        "dado e não conseguir buscar, eu digo isso.")

_RE_CAPACIDADES = re.compile(
    r"(o que voce (pode|consegue|sabe) fazer|o que voce faz|"
    r"quais (sao )?(as )?suas (funcoes|capacidades|habilidades)|"
    r"para (o )?que voce (foi|serve)|qual (e )?(a )?sua funcao|"
    r"pra que voce serve|voce faz o que|no que voce ajuda|"
    r"sua funcao|como voce funciona|quem e voce|voce e o que)",
    re.IGNORECASE)

def pergunta_sobre_capacidades(texto):
    return bool(_RE_CAPACIDADES.search(_norm_busca(texto) or ""))

# Como o trader chama o motor de análise ao falar: "liga o motor", "desliga o
# robô", "para a análise".
#
# REGRA DURA: o verbo e o substantivo precisam estar GRUDADOS (no máximo um
# artigo no meio). Aprendemos isso do jeito caro: com verbo e substantivo
# soltos na mesma frase, a fala
#     "não precisa acionar a cota da API para algumas ANÁLISES"
# desligou o motor no meio do pregão — o "para" era preposição, não o verbo
# "parar". Qualquer folga aqui volta a derrubar o motor sem ele pedir.
_MOTOR_SUBSTANTIVOS = (r"(motor|rob[ôo]|an[áa]lises?|monitoramento|sistema|"
                       r"m[áa]quina|opera[çc][ãa]o autom[áa]tica|autom[áa]tico)")
_MOTOR_ARTIGO = r"\s+(o|a|os|as|esse|essa|meu|minha|toda|todas)?\s*"
_MOTOR_LIGAR = (r"\b(lig(a|ar|ue)|ativ(a|ar|e)|inici(a|ar|e)|sob(e|ir)|"
                r"comec(a|ar|e)|começ(a|ar|e)|start)" + _MOTOR_ARTIGO +
                _MOTOR_SUBSTANTIVOS + r"\b")
# "para" é o caso venenoso: em português é VERBO ("para o motor") e PREPOSIÇÃO
# ("espera PARA a análise ficar pronta"). Como verbo de comando ele aparece no
# começo da fala ou logo depois de uma vírgula/vocativo — como preposição, vem
# depois de outro verbo. Os demais verbos não têm essa ambiguidade.
# "deliga o motor" (sem o S) foi digitado no pregão e caiu no despejo genérico
# de "não tenho como responder". Tolerar o erro de digitação é seguro porque o
# SUBSTANTIVO continua obrigatório — a regra que impede o falso positivo é o
# verbo estar GRUDADO em "motor"/"robô"/"análises", e ela não mudou.
_MOTOR_DESLIGAR = (r"\b(desl?ig(a|ar|ue)|delig(a|ar|ue)|par(ar|e)|paus(a|ar|e)|encerr(a|ar|e)|"
                   r"desativ(a|ar|e)|interromp(e|er|a)|stop)" + _MOTOR_ARTIGO +
                   _MOTOR_SUBSTANTIVOS + r"\b")
_MOTOR_PARA = (r"(^|[,.;!?]\s*|\b(tiger|pode|favor|agora|j[áa])\s+)para" +
               _MOTOR_ARTIGO + _MOTOR_SUBSTANTIVOS + r"\b")
# "NÃO desliga o motor" / "sem parar as análises" é o oposto do comando.
_MOTOR_NEGADO = r"\b(n[ãa]o|nunca|sem|jamais)\s+(precisa\w*\s+)?$"

# O COMANDO PRECISA SER A ORDEM DA FRASE, NÃO UMA ORAÇÃO SUBORDINADA.
#
# Log de 14/08, 23:37. Palavras dele:
#     "por favor, ANTES DE LIGAR O MOTOR, ajuste o plano de trading para o
#      segundo dia de operação, pois foi final de semana... fica ciente que o
#      mercado começa às 19h de domingo e encerra às 17:59 de sexta-feira"
# A ferramenta ligou o motor e JOGOU FORA o resto da mensagem. Ele pediu três
# coisas — ajustar o dia do plano, considerar o fim de semana, gravar o
# horário do pregão — e não recebeu resposta para nenhuma. Nem um "não
# entendi": a frase inteira virou um clique de botão.
#
# "antes de ligar" não é ordem de ligar; é a MARCAÇÃO DE TEMPO de outra ordem.
# O mesmo vale para "depois de", "quando", "assim que", "toda vez que". Como o
# roteador devolve UM comando só, casar aqui é perder o pedido de verdade.
#
# Fica ancorado em `$` porque é testado contra o TRECHO ANTES do casamento
# (igual ao _MOTOR_NEGADO): assim "liga o motor antes que o pregão abra"
# continua ligando — ali o "antes" vem DEPOIS do verbo, e a ordem é real.
_MOTOR_SUBORDINADO = (
    r"\b(antes|depois|ap[óo]s|logo)\s+(de|da|do|que)\s+$"
    r"|\b(quando|caso|assim que|se|sempre que|toda vez que|cada vez que|"
    r"em vez de|ao inv[ée]s de|na hora de|no momento de)\s+$")

# --------------------------------------------------------------------
# GUARDA ANTI-MENTIRA
# --------------------------------------------------------------------
# O modelo NÃO executa nada. Mesmo assim ele escrevia "acabei de zerar os dados
# da Conta 1", "acabei de reenviar para o seu WhatsApp", "lição aprendida e
# registrada" — e nada disso tinha acontecido. O trader confiou, conferiu e o
# dashboard estava igual. É o pior tipo de erro numa mesa: a ferramenta mentindo
# sobre o próprio estado.
#
# Quem executa de verdade é o código (ZERAR_CICLO, ENVIAR_WHATSAPP, LIGAR_MOTOR,
# APRENDER) e essas respostas nunca passam por aqui. Então: em resposta VINDA DO
# MODELO, qualquer alegação de ação concluída é falsa por construção, e some.
#
# CUIDADO AO MEXER AQUI: só o VERBO NA PRIMEIRA PESSOA DO PASSADO ("zerei",
# "enviei") ou o "acabei de <fazer>" contam como alegação. O infinitivo NÃO —
# senão a guarda comeria a frase mais útil que ela tem: "para zerar o ciclo,
# diga zera o ciclo que eu executo".
_ALEGACOES_FALSAS = [
    # "zerei os dados", "resetei a conta", "limpei o histórico"
    r"\b(zerei|resetei|reiniciei|limpei|apaguei)\b[^.!?]{0,60}?"
    r"\b(ciclo|dashboard|painel|dados|conta|hist[óo]rico|n[úu]meros|registros)",
    # "enviei para o seu WhatsApp", "reenviei no zap"
    r"\b(enviei|mandei|disparei|reenviei|encaminhei)\b[^.!?]{0,60}?"
    r"\b(whats?app?|zap|wpp)",
    # "acabei de executar", "já processei a regra"
    r"\b(acabei de|acabo de|j[áa])\s+(\w+\s+){0,2}"
    r"(zerar|resetar|reiniciar|limpar|apagar|enviar|mandar|disparar|reenviar|"
    r"encaminhar|registrar|gravar|memorizar|salvar|processar|executar|realizar|"
    r"ligar|desligar|ativar|desativar|capturar|tirar)\b",
    # "aprendi essa regra", "registrei a lição", "gravei na memória"
    r"\b(aprendi|registrei|memorizei|gravei|salvei|processei)\b[^.!?]{0,40}?"
    r"\b(li[çc][ãa]o|regra|isso|comando|mem[óo]ria|sistema|ordem)",
    r"\bli[çc][ãa]o\s+(aprendida|registrada|memorizada|gravada|salva)",
    # "Claro, ficou salvo:" — o modelo LOCAL escreveu isto em 12/08 21:35,
    # respondendo a "DEIXE ISSO SALVO", e listou como salvo um resumo que ele
    # tinha acabado de inventar. A forma PASSIVA ("ficou salvo", "está
    # gravado") escapava de todos os padrões, que só olhavam a primeira
    # pessoa ("gravei", "salvei"). Mentira na voz passiva continua mentira.
    r"\b(ficou|fica|est[áa]|foi|j[áa] est[áa])\s+"
    r"(salv[oa]|gravad[oa]|registrad[oa]|memorizad[oa]|anotad[oa])\b",
    r"^\s*(pronto|claro|feito)[,.:]?\s*(j[áa]\s+)?"
    r"(salvei|gravei|registrei|anotei|ficou salvo|est[áa] salvo)\b",
    r"\bcomando\s+(interno\s+)?(executado|processado|enviado|realizado)",
    r"\b(liguei|desliguei|ativei|desativei)\b[^.!?]{0,40}?"
    r"\b(motor|rob[ôo]|an[áa]lise)",
    # resposta em forma de recibo: "Motor ligado, Josevan." logo no começo
    r"^\s*(motor|rob[ôo])\s+(ligado|desligado|no ar|ativado|parado)\b",
    r"\bprocedimento de reset\b",
    # "fico sempre ativa monitorando em segundo plano" / "fico por aqui
    # monitorando a liquidez em segundo plano" — quem monitora é o motor
    r"\b(estou|fico|sigo|continuo|permane[çc]o)\s+(\w+\s+){0,3}"
    r"(ativa|monitorando|varrendo|acompanhando|processando|vigiando)\b"
    r"[^.!?]{0,60}?\b(fundo|segundo plano|tempo real|por voc[êe])",
]
_RE_ALEGACOES = re.compile("|".join(_ALEGACOES_FALSAS),
                           re.IGNORECASE | re.MULTILINE)

_AVISO_ALEGACAO = (
    "Só um ajuste importante: eu não faço nada só de escrever que fiz. "
    "Para valer de verdade, use o comando — 'zera o ciclo', 'manda no "
    "whatsapp', 'liga o motor', 'desliga o motor', 'tira um print', ou termine "
    "a frase com 'aprenda isso'. Aí é o app que executa e eu confirmo com o "
    "resultado real.")

def censurar_alegacao_falsa(texto):
    """Tira da resposta do MODELO qualquer alegação de ação já executada.
    Devolve (texto_limpo, censurou). Frases boas são preservadas: só cai o
    trecho que afirma um feito que não aconteceu."""
    if not texto or not _RE_ALEGACOES.search(texto):
        return texto, False
    frases = re.split(r"(?<=[.!?])\s+", texto)
    limpas = [f for f in frases if not _RE_ALEGACOES.search(f)]
    corpo = " ".join(limpas).strip()
    if not corpo:
        corpo = ("Pera — eu ia dizer que tinha feito isso, mas não fiz: "
                 "escrever não executa nada aqui.")
    return f"{corpo}\n\n{_AVISO_ALEGACAO}", True

# "CAPTURE AGORA" não tinha substantivo nenhum e caía no genérico. O verbo de
# capturar já é inequívoco sozinho — ninguém diz "captura" numa mesa falando de
# outra coisa. "Tira/faz" continuam exigindo o substantivo (são ambíguos).
_PRINT_SOZINHO = (r"^\s*(captur(a|e|ar)|printa|printe|print|screenshot|"
                  r"tir(a|e|ar)\s+(um|uma)?\s*print)\b")
_PRINT_COM_AGORA = (r"\b(captur(a|e|ar)|printa|printe|screenshot)\s+"
                    r"(a\s+)?(tela|janela|gr[áa]fico|isso|agora|j[áa]|"
                    r"de novo|novamente|outra vez)\b")

# --------------------------------------------------------------------
# APRENDIZADO — as três formas como ele realmente ensina uma regra
# --------------------------------------------------------------------
# Por muito tempo só a primeira funcionava, e as outras duas — que são as que
# ele mais usa — caíam no modelo, que respondia "lição aprendida e registrada"
# sem gravar nada. Daí a queixa de que a IA "não estava aprendendo".
_LICAO_VERBO = (r"(aprend(a|e|er)|memoriz(a|e|ar)|guard(a|e|ar)|anot(a|e|ar)|"
                r"li[çc][ãa]o)")
# "APRENDA TUDO ISSO" e "APRENDA ISSO TUDO QUE PEDI ACIMA" caíam no despejo
# genérico ("não tenho como responder isso com segurança agora") — duas vezes
# seguidas no log de 10/08, 18:09 e 18:10. O objeto aceitava "isso", mas não
# "tudo isso" nem "isso tudo".
_LICAO_OBJETO = (r"((tudo|todo)\s+)?(isso|isto|essa regra|esse ponto|"
                 r"isso a[íi]|bem isso|tudo)(\s+(tudo|isso))?")
# Cortesias que sobram grudadas na ponta da lição e não fazem parte dela.
_LICAO_SOBRA = (r"[\s,;:]*\b(considere|considera|considerar|leve em conta|"
                r"quero que voc[êe]|gostaria que voc[êe]|por favor|e|ent[ãa]o|"
                r"da[íi]|ent[ãa]o)\s*$")

def extrair_licao(texto):
    """Devolve a lição que ele quer gravar, "" quando é o turno anterior, ou
    None se a frase não é uma lição.

    Três formas aceitas:
      1. PREFIXO   — "aprenda: nunca opere contra o H4"
      2. SUFIXO    — "nunca opere contra o H4, aprenda isso" (o jeito dele)
      3. SOZINHA   — "aprenda isso" (a lição é o que ele disse antes)
    """
    bruto = (texto or "").strip()
    t = bruto.lower()
    if not t:
        return None

    # A forma SOZINHA é testada ANTES das outras duas de propósito: "aprenda
    # isso tudo QUE pedi acima" tem um "que" no meio, e a forma PREFIXO tratava
    # esse "que" como separador, gravando a lição "pedi acima" — uma frase sem
    # sentido nenhum, gravada para sempre. Como esta forma exige casamento
    # COMPLETO da frase normalizada, ela não rouba lição de verdade.
    # ORDEM: a forma SOZINHA vem PRIMEIRO — "" avisa quem trata o turno para usar a fala anterior dele.
    #    Antes de comparar, tira a CAUDA de referência ("que pedi acima", "que
    #    eu falei") e as cortesias. Sem isso, "aprenda isso tudo que pedi
    #    acima" não casava com nada e virava despejo genérico. Cada pedaço sai
    #    numa substituição própria, sem quantificador sobre grupo opcional —
    #    aninhar isso num só padrão trava o motor de regex em frases longas.
    t3 = re.sub(r"\b(que\s+)?(eu\s+)?(pedi|falei|disse|escrevi|mandei|mostrei|"
                r"ensinei|ensinou|passei)\b", " ", t, flags=re.IGNORECASE)
    t3 = re.sub(r"\b(acima|em cima|a[íi] em cima|antes|agora|hoje|a[íi])\b",
                " ", t3, flags=re.IGNORECASE)
    t3 = re.sub(r"\b(por favor|ok|t[áa]|beleza|certo|valeu|obrigad[oa]|"
                r"voc[êe] pode|voc[êe] consegue)\b", " ", t3, flags=re.IGNORECASE)
    t3 = re.sub(r"[\s,.!?]+", " ", t3).strip()
    if re.fullmatch(r"(considere\s+)?" + _LICAO_VERBO + r"\s+" + _LICAO_OBJETO,
                    t3, re.IGNORECASE):
        return ""

    # 1. PREFIXO, com ou sem "considere" na frente. O separador pode ser
    #    dois-pontos, "que" — ou VÍRGULA/travessão, que é como ele escreve de
    #    verdade: "APRENDA, USE O MOTOR PARA TIRAR PRINT" virava comando de
    #    print em vez de lição. Com vírgula exigimos uma frase de verdade
    #    depois, senão "aprenda, por favor" viraria a lição "por favor".
    m = re.match(r"\s*(considere\s+|quero que voc[êe]\s+|leve em conta\s+)?"
                 + _LICAO_VERBO + r"\s*(" + _LICAO_OBJETO + r"\s*)?"
                 r"(?P<sep>:|,|—|-|\bque\b)\s*(?P<corpo>.+)",
                 t, re.IGNORECASE | re.DOTALL)
    if m and m.group("corpo").strip():
        corpo = bruto[m.start("corpo"):].strip(" ,.;:—-")
        if m.group("sep") in (":",) or "que" in m.group("sep") or \
                len(corpo.split()) >= 3:
            return corpo

    # 2. SUFIXO: "<a regra>, aprenda isso". Depois do gatilho pode vir uma
    #    justificativa ("…, aprenda isso, tendo em base que você já conhece
    #    SMC") — a lição é o que vem ANTES dele.
    # O separador aceita HÍFEN colado: ele escreveu
    # "É SÓ VOCÊ OLHAR NOS HISTÓRICOS DE SUGESTÕES-APRENDA ISSO" e a lição não
    # foi gravada — o padrão exigia espaço/vírgula antes do verbo.
    m = re.search(r"[,.;:\-–—\s]+" + _LICAO_VERBO + r"\s+" + _LICAO_OBJETO + r"\b",
                  t, re.IGNORECASE)
    if m:
        antes = bruto[:m.start()].strip(" ,.;:—-")
        antes = re.sub(_LICAO_SOBRA, "", antes, flags=re.IGNORECASE).strip(" ,.;:—-")
        # Exige uma frase de verdade antes do gatilho: sem isso, "eu quero
        # aprender isso melhor" viraria a lição "eu quero".
        if len(antes.split()) >= 4:
            return antes


# --------------------------------------------------------------------
# A IA CONFIGURA A PRÓPRIA FERRAMENTA (autorizado pelo trader)
# --------------------------------------------------------------------
# "deixa registrado que o dia para a conta 1 começa as 19hs" caía no genérico
# "não tenho como responder isso com segurança agora" — e "como está
# configurado o risco do plano da conta 1" também. Ela tinha o dado na mão e
# não olhava; tinha a chave do arquivo e não escrevia.
#
# Aqui é CÓDIGO, não modelo: quem lê e grava a configuração é a mesma função
# que os botões do app usam. E vale a REGRA DE OURO da casa — grava, RELÊ DO
# DISCO, e só então confirma, mostrando o valor de antes e o de depois. Se a
# releitura não bater, ela diz que NÃO conseguiu, em vez de dizer que fez.
PADRAO_CONFIG_APP = {
    "hora_inicio": "09:00",
    "hora_fim": "17:00",
    "intervalo_minutos": 15,
}

ROTULO_CONFIG = {
    "hora_inicio": "início do pregão",
    "hora_fim": "fim do pregão",
    "intervalo_minutos": "intervalo entre análises",
    "margem": "margem (banca)",
    "meta_alvo": "meta do ciclo",
    "drawdown_maximo": "drawdown máximo",
    "risco_pct": "risco por operação",
    "rr_minimo": "R:R mínimo",
    "probabilidade_minima": "probabilidade mínima",
    "dias_meta": "prazo da meta",
    "timeout_acatar_min": "prazo para acatar",
    "data_inicio": "início do ciclo",
    "max_stops_seguidos": "stops seguidos até a pausa",
    "cooldown_stop_min": "pausa após stops seguidos",
    "max_operacoes_dia": "teto de operações por dia",
    "max_contratos": "teto de contratos por operação",
    "min_ticks_stop": "mínimo de ticks de stop",
    "com_posicao_aberta": "quando você já está posicionado",
}

# Onde cada campo mora: "config" é da FERRAMENTA (o motor é um só, vale para
# todas as contas); "plano" é da CONTA (cada conta tem o seu).
DESTINO_CONFIG = {
    "hora_inicio": "config",
    "hora_fim": "config",
    "intervalo_minutos": "config",
    "margem": "plano",
    "meta_alvo": "plano",
    "drawdown_maximo": "plano",
    "risco_pct": "plano",
    "rr_minimo": "plano",
    "probabilidade_minima": "plano",
    "dias_meta": "plano",
    "timeout_acatar_min": "plano",
    "data_inicio": "plano",
    "max_stops_seguidos": "plano",
    "cooldown_stop_min": "plano",
    "max_operacoes_dia": "plano",
    "max_contratos": "plano",
    "min_ticks_stop": "plano",
    "com_posicao_aberta": "plano",
}

_ROTULO_POSICAO_ABERTA = {
    "alerta": "avisar quando o cenário virar contra (e sugerir aumento a favor)",
    "livre": "sugerir normalmente, como se não houvesse posição",
    "bloquear": "não sugerir nada enquanto houver posição no ativo",
}

def formatar_valor_config(campo, valor):
    """Como o valor aparece para o trader (e na leitura em voz alta)."""
    if valor is None or valor == "":
        return "não definido"
    if campo in ("hora_inicio", "hora_fim"):
        return str(valor)
    if campo == "com_posicao_aberta":
        return _ROTULO_POSICAO_ABERTA.get(str(valor).strip().lower(), str(valor))
    if campo == "data_inicio":
        try:
            return datetime.date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return str(valor)
    n = _num(valor)
    if n is None:
        return str(valor)
    if campo in ("margem", "meta_alvo", "drawdown_maximo"):
        return f"US$ {n:,.2f}"
    if campo in ("risco_pct", "probabilidade_minima"):
        return f"{n:g}%"
    if campo == "rr_minimo":
        return f"1:{n:g}"
    if campo == "dias_meta":
        return f"{int(n)} dia(s)"
    if campo in ("intervalo_minutos", "timeout_acatar_min", "cooldown_stop_min"):
        return f"{int(n)} minuto(s)"
    if campo == "max_stops_seguidos":
        return f"{int(n)} stop(s) seguidos"
    if campo == "max_operacoes_dia":
        return "sem teto" if int(n) <= 0 else f"{int(n)} operação(ões) por dia"
    if campo == "max_contratos":
        return "automático (sem teto fixo)" if int(n) <= 0 else f"{int(n)} contrato(s)"
    if campo == "min_ticks_stop":
        return "sem piso" if int(n) <= 0 else f"{int(n)} tick(s)"
    return f"{n:g}"


_RE_NUMERO_PT = re.compile(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)")

def _numero_pt(trecho):
    """Número como o brasileiro escreve: '6.000' -> 6000 · '1.234,56' ->
    1234.56 · '2,5' -> 2.5 · '6 mil' -> 6000. Devolve float ou None."""
    m = _RE_NUMERO_PT.search(trecho or "")
    if not m:
        return None
    bruto = m.group(1)
    if re.search(r"\.\d{3}", bruto):      # 6.000 / 1.234,56 -> ponto é milhar
        bruto = bruto.replace(".", "")
    try:
        v = float(bruto.replace(",", "."))
    except ValueError:
        return None
    if re.match(r"\s*(mil\b|k\b)", (trecho or "")[m.end():], re.IGNORECASE):
        v *= 1000
    return v

# "19hs", "19h30", "19:30", "9 horas" — e a forma solta "às 19".
_RE_HORA_A = re.compile(r"(\d{1,2})\s*(?::|h(?:s|rs|oras?)?)\s*(\d{2})?(?!\d)",
                        re.IGNORECASE)
_RE_HORA_B = re.compile(r"\b(?:[àáa]s|at[ée]|pras|para as)\s+(\d{1,2})(?![\d:h,.])",
                        re.IGNORECASE)
# "o pregão vai das 9h às 17h" configura os DOIS lados de uma vez.
_MEIA_HORA = r"(\d{1,2})(?:\s*(?::|h(?:s|rs|oras?)?)\s*(\d{2})?)?"
_RE_FAIXA_HORA = re.compile(r"\bd(?:as|e|os)\s+" + _MEIA_HORA +
                            r"\s*(?:[àáa]s|at[ée]|a|-|–)\s*" + _MEIA_HORA,
                            re.IGNORECASE)

def _hhmm(h, m=0):
    """'HH:MM' válido, ou None se o número não é hora de relógio."""
    try:
        h, m = int(h), int(m or 0)
    except (TypeError, ValueError):
        return None
    return f"{h:02d}:{m:02d}" if 0 <= h <= 23 and 0 <= m <= 59 else None

def _horas_no_texto(t):
    """Todas as horas citadas, como [(posição do número, 'HH:MM')]."""
    achados = {}
    for m in _RE_HORA_A.finditer(t):
        hora = _hhmm(m.group(1), m.group(2))
        if hora:
            achados[m.start(1)] = hora
    for m in _RE_HORA_B.finditer(t):
        if m.start(1) in achados:
            continue
        hora = _hhmm(m.group(1))
        if hora:
            achados[m.start(1)] = hora
    return sorted(achados.items())

# Do que ele está falando quando diz "começa às 19h": o DIA DELE, não o pregão
# de Nova York. Sem esse sujeito (ou sem um verbo de comando), a frase não
# mexe em nada — é conversa sobre o mercado.
_CFG_SUJEITO = (r"\b(dia|preg[ãa]o|sess[ãa]o|opera[çc][ãa]o|opera[çc][õo]es|"
                r"expediente|rotina|motor|an[áa]lises?|rob[ôo]|turno|mesa|"
                r"hor[áa]rio|ferramenta|jornada)\b")
_CFG_INICIO = (r"(come[çc]\w+|inici\w+|abr\w+|abertura|in[íi]cio|start|"
               r"entr(a|o|ar)\w*|ligo|liga\w*)")
_CFG_FIM = (r"(termin\w+|acab\w+|encerr\w+|fech\w+|finaliz\w+|t[ée]rmino|"
            r"\bfim\b|at[ée]\b|saio|sair|desligo|desliga\w*)")
# Pregão dos OUTROS: "o pregão americano abre às 9:30" é informação de mercado,
# não configuração da mesa dele.
_CFG_MERCADO_ALHEIO = (r"\b(americano|americana|eua|nova york|nova iorque|ny|"
                       r"brasileir[oa]|europeu|europeia|de chicago|de londres|"
                       r"asi[áa]tic[oa]|japon[êe]s|wall street|nyse|cme|b3|"
                       r"nasdaq|forex)\b")

# Verbo de comando: o que transforma uma frase em pedido de configuração.
_CFG_GATILHO = re.compile(
    r"\b(configur\w+|ajust(a|ar|e|em)\w*|defin(a|e|ir|o)\w*|"
    r"deix(a|e|ar)\s+\w*\s*(registrad\w+|configurad\w+|anotad\w+|marcad\w+|gravad\w+)|"
    r"registr(a|e|ar)\b|anot(a|e|ar)\b|mud(a|ar|e|ei)\b|alter(a|ar|e)\b|"
    r"troc(a|ar|e)\b|coloc(a|ar|e|ou)\b|p[õo]e\b|set(a|ar|e)\b|passa\s+a\b|"
    r"a partir de agora\b|de agora em diante\b|quero que\b|preciso que\b|"
    r"grav(a|ar|e)\b|salv(a|ar|e)\b|atualiz(a|ar|e)\b|aument(a|ar|e)\b|"
    r"reduz(a|ir|e)\b|diminu(a|ir|i)\b|sob(e|ir)\b|baix(a|ar|e)\b|"
    r"limit(a|ar|e)\b|meu\s+risco\b|minha\s+meta\b)", re.IGNORECASE)

# Pergunta nunca configura nada — "qual a meta do S&P hoje, 7800?" não pode
# virar "meta do ciclo = 7800".
_RE_SO_PERGUNTA = re.compile(
    r"^\s*\W*(qual|quais|quanto|quantos|quantas|como|quando|que horas|"
    r"a que horas|o que|onde|por que|porqu[êe]|pq|me diz|me fala|me mostra|"
    r"voc[êe] sabe)\b", re.IGNORECASE)

def interpretar_configuracao(texto):
    """Lê o pedido em português e devolve a LISTA de mudanças de configuração
    que ele pediu — sem tocar em disco (função pura, testável).

    Cada item: {"campo", "valor", "destino", "rotulo"}.

    REGRA DE SEGURANÇA (a mesma lição cara do motor): pergunta não configura,
    e número solto no meio de uma conversa sobre mercado não configura. Para
    um campo NUMÉRICO mudar, é preciso um verbo de comando na frase. Para o
    HORÁRIO mudar, é preciso o verbo de comando OU o sujeito ser o dia dele.
    """
    bruto = (texto or "").strip()
    if not bruto:
        return []
    t = bruto.lower()
    if _RE_SO_PERGUNTA.match(t):
        return []
    tem_gatilho = bool(_CFG_GATILHO.search(t))
    if "?" in t and not tem_gatilho:
        return []
    achados = {}
    usados = []          # trechos já consumidos: um número não vira dois campos

    def livre(ini, fim):
        return not any(ini < b and a < fim for a, b in usados)

    def guardar(campo, valor, ini=None, fim=None):
        if campo in achados:
            return
        achados[campo] = valor
        if ini is not None:
            usados.append((ini, fim))

    # ---------------- HORÁRIO DO DIA DE OPERAÇÃO ----------------
    tem_sujeito = bool(re.search(_CFG_SUJEITO, t))
    alheio = bool(re.search(_CFG_MERCADO_ALHEIO, t))
    if (tem_gatilho or tem_sujeito) and not (alheio and not tem_gatilho):
        faixa = _RE_FAIXA_HORA.search(t)
        if faixa and tem_sujeito:
            ini, fim = _hhmm(faixa.group(1), faixa.group(2)), \
                       _hhmm(faixa.group(3), faixa.group(4))
            if ini and fim:
                guardar("hora_inicio", ini, faixa.start(), faixa.end())
                guardar("hora_fim", fim)
        for pos, hora in _horas_no_texto(t):
            if not livre(pos, pos + 2):
                continue
            antes = t[max(0, pos - 70):pos]
            if re.search(_CFG_INICIO, antes) and "hora_inicio" not in achados:
                guardar("hora_inicio", hora, pos, pos + 2)
            elif re.search(_CFG_FIM, antes) and "hora_fim" not in achados:
                guardar("hora_fim", hora, pos, pos + 2)

    # ---------------- CAMPOS NUMÉRICOS ----------------
    # A ordem IMPORTA: quem fala em "minutos" vem antes de quem fala em
    # "dias"/"dólares", e o trecho consumido não é reaproveitado.
    _NUM = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
    especs = [
        ("timeout_acatar_min", r"\bacatar\b",
         r"(\d{1,3})\s*(?:min\b|minutos?\b)"),
        # Freio de sugestões. Vem cedo na lista porque fala em "minutos" e em
        # "stops" — se ficasse depois, "pausa de 30 minutos" seria capturado
        # pelo intervalo entre análises.
        # Os dois usam LOOKAHEAD de propósito: assim o trecho "consumido" é só a
        # palavra-âncora, e o número continua visível para a busca do valor.
        # Com o casamento largo, "pausa de 45 minutos depois do stop" engolia o
        # "45 minutos" dentro da própria chave e nada era configurado.
        ("cooldown_stop_min",
         r"\b(pausa|cooldown|descanso)\b(?=[^.;]{0,30}\bstop)",
         r"(\d{1,3})\s*(?:min\b|minutos?\b)"),
        ("cooldown_stop_min",
         r"\bstop\b(?=[^.;]{0,30}\b(pausa|cooldown|descanso|esperar|aguardar)\b)",
         r"(\d{1,3})\s*(?:min\b|minutos?\b)"),
        ("max_stops_seguidos",
         r"\b(stops?\s+seguidos?|stops?\s+consecutivos?|sequ[êe]ncia de stops?)\b",
         r"(\d{1,2})"),
        ("max_operacoes_dia",
         r"\b(m[áa]ximo de opera|teto de opera|limite de opera|opera[çc][õo]es por dia|"
         r"trades? por dia)\b",
         r"(\d{1,3})"),
        # TRAVAS DE TAMANHO. Vêm antes de "risco"/"margem" porque a frase
        # natural é "no máximo 5 contratos por operação" e "stop de pelo
        # menos 10 ticks" — as duas citam número sem citar dinheiro.
        ("max_contratos",
         r"\b(m[áa]ximo de contratos?|teto de contratos?|limite de contratos?|"
         r"no m[áa]ximo\s+\d{1,3}\s+contratos?|contratos? por opera[çc][ãa]o)\b",
         r"(\d{1,3})"),
        ("min_ticks_stop",
         r"\b(ticks?\s+de\s+stop|stop\s+m[íi]nimo|m[íi]nimo de ticks?|"
         r"piso de (stop|ticks?)|stop de pelo menos)\b",
         r"(\d{1,3})"),
        ("intervalo_minutos",
         r"\b(intervalo|a cada|de quanto em quanto|frequ[êe]ncia|periodicidade)\b",
         r"(\d{1,3})\s*(?:min\b|minutos?\b)"),
        ("dias_meta", r"\b(prazo|meta|ciclo|dias?)\b", r"(\d{1,3})\s*dias?\b"),
        ("risco_pct", r"\brisco\b(?![^.;]{0,12}retorno)",
         r"(\d{1,3}(?:[.,]\d+)?)\s*(?:%|por cento)"),
        ("probabilidade_minima",
         r"\b(probabilidade|assertividade|taxa de acerto)\b",
         r"(\d{1,3}(?:[.,]\d+)?)\s*(?:%|por cento)?"),
        ("rr_minimo",
         r"(\br\s*[:/x]\s*r\b|\brr\b|risco\s*[:/x]\s*retorno|"
         r"risco\s+(?:por|para)\s+retorno|rela[çc][ãa]o risco[\s/-]*retorno)",
         r"(\d{1,2}(?:[.,]\d+)?)"),
        ("drawdown_maximo",
         r"\b(drawdown|draw down|perda m[áa]xima|limite de perda|dd)\b", _NUM),
        ("margem", r"\b(margem|banca|capital|saldo inicial)\b", _NUM),
        ("meta_alvo", r"\b(meta|alvo do ciclo|objetivo)\b", _NUM),
    ]
    if tem_gatilho:
        for campo, chave_re, valor_re in especs:
            if campo in achados:
                continue
            chave = re.search(chave_re, t)
            if not chave:
                continue
            # O valor vem DEPOIS da palavra-chave ("risco de 1%") ou, mais
            # raramente, ANTES dela ("1% de risco por operação").
            alvo = None
            for janela_ini, janela_fim in ((chave.end(), chave.end() + 45),
                                           (max(0, chave.start() - 25), chave.start())):
                for m in re.finditer(valor_re, t[janela_ini:janela_fim]):
                    ini = janela_ini + m.start(1)
                    if livre(ini, janela_ini + m.end()):
                        alvo = (ini, janela_ini + m.end())
                        break
                if alvo:
                    break
            if not alvo:
                continue
            valor = _numero_pt(t[alvo[0]:alvo[0] + 24])
            if valor is None:
                continue
            # "R:R de 1:2" quer dizer 2, não 1.
            if campo == "rr_minimo":
                par = re.match(r"\s*\d+(?:[.,]\d+)?\s*[:x]\s*(\d+(?:[.,]\d+)?)",
                               t[alvo[0]:alvo[0] + 24])
                if par:
                    valor = _numero_pt(par.group(1)) or valor
            valor = _valor_config_valido(campo, valor)
            if valor is not None:
                guardar(campo, valor, alvo[0], alvo[1])

    # ---------------- CAMPO DE ESCOLHA (não é número) ----------------
    # "quando eu já estiver posicionado, me avise / não sugira nada / sugira
    # normal". Precisa de tratamento próprio porque o valor é uma palavra.
    if tem_gatilho and "com_posicao_aberta" not in achados:
        m_pos = re.search(r"(posi[cç][ãa]o aberta|posicionad\w*|com posi[cç][ãa]o)", t)
        if m_pos:
            trecho = t[max(0, m_pos.start() - 60):m_pos.end() + 80]
            escolha = None
            if re.search(r"\b(n[ãa]o suger\w*|nada|silenci\w*|calad\w*|n[ãa]o mand\w*|"
                         r"bloque\w*|par(e|ar) de suger\w*)\b", trecho):
                escolha = "bloquear"
            elif re.search(r"\b(normal\w*|livre|como se n[ãa]o|continue suger\w*|"
                           r"pode suger\w*|suger\w* do mesmo jeito)\b", trecho):
                escolha = "livre"
            elif re.search(r"\b(avis\w*|alert\w*|me diga|me avise|aviso)\b", trecho):
                escolha = "alerta"
            if escolha:
                guardar("com_posicao_aberta", escolha, m_pos.start(), m_pos.end())

    # ---------------- DATA DE INÍCIO DO CICLO ----------------
    if tem_gatilho and "data_inicio" not in achados and \
            re.search(r"\b(data|in[íi]cio|come[çc]\w+|desde|a partir|ciclo)\b", t):
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
        if m:
            dia, mes = int(m.group(1)), int(m.group(2))
            ano = int(m.group(3) or datetime.date.today().year)
            if ano < 100:
                ano += 2000
            try:
                guardar("data_inicio",
                        datetime.date(ano, mes, dia).isoformat(), m.start(), m.end())
            except ValueError:
                pass
        elif re.search(r"\bhoje\b", t):
            guardar("data_inicio", datetime.date.today().isoformat())

    return [{"campo": c, "valor": v, "destino": DESTINO_CONFIG.get(c, "plano"),
             "rotulo": ROTULO_CONFIG.get(c, c)}
            for c, v in achados.items()]

def _valor_config_valido(campo, valor):
    """Mesmos limites que os campos da tela aceitam. Devolve o valor já
    ajustado, ou None quando o número não faz sentido para o campo."""
    if valor is None:
        return None
    if campo in ("intervalo_minutos", "timeout_acatar_min", "dias_meta"):
        n = int(round(valor))
        return max(1, n) if n >= 1 else None
    if campo == "risco_pct":
        return round(valor, 4) if 0 < valor <= 100 else None
    if campo == "probabilidade_minima":
        return max(0.0, min(95.0, float(valor))) if 0 <= valor <= 100 else None
    if campo == "rr_minimo":
        return max(1.0, float(valor)) if valor > 0 else None
    if campo in ("margem", "meta_alvo", "drawdown_maximo"):
        return float(valor) if valor >= 0 else None
    if campo in ("max_stops_seguidos", "cooldown_stop_min", "max_operacoes_dia",
                 "max_contratos", "min_ticks_stop"):
        # Zero é escolha legítima em todos: significa "não quero essa trava".
        n = int(round(valor))
        return n if n >= 0 else None
    if campo == "com_posicao_aberta":
        v = str(valor).strip().lower()
        return v if v in ("alerta", "livre", "bloquear") else None
    return valor

# Sobre qual campo ele está perguntando quando pede "como está configurado".
_PALAVRAS_CAMPO = {
    "risco_pct": r"\brisco\b",
    "meta_alvo": r"\bmeta\b|\balvo\b",
    "margem": r"\bmargem\b|\bbanca\b|\bcapital\b",
    "drawdown_maximo": r"\bdrawdown\b|\bdraw down\b|\bdd\b|\bperda maxima\b",
    "rr_minimo": r"\br ?[:/x] ?r\b|\brr\b|risco[ /-]*retorno",
    "probabilidade_minima": r"\bprobabilidade\b|\bassertividade\b",
    "dias_meta": r"\bprazo da meta\b|\bdias\b",
    "timeout_acatar_min": r"\bacatar\b",
    "hora_inicio": r"\bcomec\w*\b|\binicio\b|\babre\b|\babertura\b",
    "hora_fim": r"\btermin\w*\b|\bfim\b|\bfecha\b|\bencerr\w*\b",
    "intervalo_minutos": r"\bintervalo\b|\ba cada\b|\bfrequencia\b",
    "max_stops_seguidos": r"\bstops? seguidos?\b|\bstops? consecutivos?\b",
    "cooldown_stop_min": r"\bpausa\b|\bcooldown\b|\bdescanso\b",
    "max_operacoes_dia": r"\bteto de opera\w*\b|\bmaximo de opera\w*\b|"
                         r"\bopera\w+ por dia\b|\btrades? por dia\b",
    "max_contratos": r"\bcontratos?\b|\btamanho da posicao\b|\bsizing\b|"
                     r"\bquantidade\b",
    "min_ticks_stop": r"\bticks?\b|\bstop minimo\b|\bpiso de stop\b",
    "com_posicao_aberta": r"\bposicao aberta\b|\bposicionad\w*\b|"
                          r"\bja (estou|esteja) (posicionad|com posicao)\w*\b",
}

_RE_VER_CONFIG = re.compile(
    r"(como\s+(esta|estao|ficou|ficaram|anda|ta|funciona)\w*\s+"
    r"((o|a|os|as|meu|minha|meus|minhas)\s+)*(configurad|configura|plano|"
    r"gestao de risco|gestao|gerenciamento|risco|meta|margem|drawdown|prazo|"
    r"horario|intervalo|parametros|numeros|pausa|freio|teto|limite)|"
    # "qual o MEU risco" é sobre a configuração; "qual o risco DISSO" é sobre o
    # trade que está na mesa. Sem essa diferença ela sequestrava a conversa.
    r"qual\s+(e\s+)?(o|a|os|as)?\s*(meu|minha|meus|minhas)\s*(configura|plano|meta|"
    r"risco|margem|drawdown|horario|prazo|intervalo|rr|probabilidade)|"
    r"qual\s+(e\s+)?(o|a|os|as)?\s*(configura\w*|plano|meta|risco|margem|drawdown|"
    r"horario|prazo|intervalo|rr|probabilidade)\b[^?]{0,30}?\b(do plano|da conta|"
    r"por operacao|da ferramenta|configurad|do ciclo|das analises|de analise|"
    r"do motor|do pregao|do dia)|"
    r"quais\s+(sao\s+)?((as|os|minhas|meus)\s+)*(configura|regras|parametros|"
    r"horarios|numeros do plano)|"
    r"(me\s+)?(mostr|list|diz|fal|lembr|repet)\w*\s+.{0,30}(configura|plano de trading|"
    r"parametros|horario|meu risco|minha meta)|"
    r"(configuracao|configuracoes|parametros)\s+(atual|atuais|da conta|do plano|"
    r"da ferramenta)|"
    r"(que|a que)\s+horas\s+.{0,30}(comec|termin|abre|fecha|acaba)|"
    r"esta\s+configurad|como\s+voce\s+esta\s+configurad)", re.IGNORECASE)

def pergunta_sobre_configuracao(texto):
    """'como está configurado o risco do plano da conta 1' e parentes."""
    return bool(_RE_VER_CONFIG.search(_norm_busca(texto) or ""))

def campos_citados(texto):
    """Os campos que ele nomeou na pergunta (vazio = quer ver tudo)."""
    t = _norm_busca(texto) or ""
    return [c for c, padrao in _PALAVRAS_CAMPO.items() if re.search(padrao, t)]

def conta_por_referencia(texto, contas):
    """De qual conta ele está falando ('na conta 1', 'na conta real').
    Devolve a conta, ou None quando ele não citou nenhuma (= a ativa)."""
    t = _norm_busca(texto) or ""
    for c in (contas or []):
        nome = _norm_busca(c.get("nome", ""))
        if nome and nome in t:
            return c
    m = re.search(r"\bconta\s*(?:n[uo]mero\s*)?(\d{1,2})\b", t)
    if m:
        i = int(m.group(1))
        if 1 <= i <= len(contas or []):
            return contas[i - 1]
    return None

def resumo_da_configuracao(cfg, plano, nome_conta="", campos=None):
    """O 'como está configurado' — SÓ com valores lidos do disco, nunca
    estimados. `campos` limita a resposta ao que ele perguntou."""
    cfg = cfg or {}
    plano = plano or {}
    ordem = ["hora_inicio", "hora_fim", "intervalo_minutos", "margem",
             "meta_alvo", "dias_meta", "drawdown_maximo", "risco_pct",
             "rr_minimo", "probabilidade_minima", "timeout_acatar_min",
             "max_contratos", "min_ticks_stop",
             "max_stops_seguidos", "cooldown_stop_min", "max_operacoes_dia",
             "com_posicao_aberta", "data_inicio"]
    escolhidos = [c for c in ordem if not campos or c in campos]
    if not escolhidos:
        escolhidos = ordem
    linhas_app, linhas_plano = [], []
    for campo in escolhidos:
        if DESTINO_CONFIG.get(campo) == "config":
            valor = cfg.get(campo, PADRAO_CONFIG_APP.get(campo))
            linhas_app.append(f"• {ROTULO_CONFIG[campo]}: "
                              f"{formatar_valor_config(campo, valor)}")
        else:
            valor = plano.get(campo, PLANO_PADRAO.get(campo))
            linhas_plano.append(f"• {ROTULO_CONFIG[campo]}: "
                                f"{formatar_valor_config(campo, valor)}")
    partes = []
    if linhas_app:
        partes.append("FERRAMENTA (vale para todas as contas — o motor é um "
                      "só):\n" + "\n".join(linhas_app))
    if linhas_plano:
        partes.append(f"PLANO DA CONTA '{nome_conta or 'ativa'}':\n" +
                      "\n".join(linhas_plano))
    partes.append("Isto é o que está gravado no arquivo agora, não é "
                  "estimativa. Para mudar qualquer um, é só me dizer — por "
                  "exemplo: 'o dia começa às 19h', 'risco de 1% por operação', "
                  "'meta de 6 mil em 10 dias'.")
    return "\n\n".join(partes)

# Pergunta que SÓ o gráfico responde: onde entra, onde para, onde sai.
# Repare no que NÃO entra aqui: "o que é um stop?" e "como se calcula o R:R?"
# são metodologia e continuam sendo respondidas de cabeça, sem gastar captura
# nem cota. O que dispara é o pedido de um NÚMERO para a operação DELE.
_RE_NIVEL = re.compile(
    r"\b(onde|qual|quais|quanto|em que (n[íi]vel|pre[çc]o|ponto)|"
    r"at[ée] onde|pra onde|para onde)\b[^?]{0,80}?"
    r"\b(stop|alvo|alvos|take|tp\d?|sa[íi]da|saio|sair|realiz\w+|parcial|"
    r"prote[çc][ãa]o|prote(g|j)\w+|entrada|entro|zerar|encerr\w+)\b"
    r"|\b(onde|como)\b[^?]{0,40}\b(posicion\w+|coloc\w+|ponho|por|p[ôo]e|"
    r"deixo|movo|mover|ajust\w+)\b[^?]{0,40}"
    r"\b(stop|alvo|take|tp\d?|prote[çc][ãa]o|parcial)\b", re.I)
# "o que é / o que significa / como funciona" = teoria, não é pedido de número.
_RE_NIVEL_TEORIA = re.compile(
    r"\b(o que (é|e|significa|seria)|que (é|e) um|como (se )?(calcula|funciona|"
    r"define)|defini[çc][ãa]o de|explica\w*|conceito)\b", re.I)

def pergunta_pede_nivel(texto):
    """True quando ele pede um NÚMERO da operação dele (stop, alvo, saída).

    Isto é o gatilho para ela CAPTURAR e LER o gráfico por conta própria, em
    vez de mandar o trader digitar 'tira um print' — que foi exatamente a
    reclamação: ela sabia fazer e devolvia a tarefa."""
    t = _norm_busca(texto or "")
    if not t:
        return False
    if _RE_NIVEL_TEORIA.search(t):
        return False
    return bool(_RE_NIVEL.search(t))

# --------------------------------------------------------------------
# HISTÓRICO DE SUGESTÕES — dado que a ferramenta TEM no disco
# --------------------------------------------------------------------
# 14:46 ❯ "onde foi a última sugestão de venda de MGCV6?"
# 14:46 ✳ "não está na minha base, não consegui confirmar na internet, e a API
#          está fora..."
# Ela tinha o arquivo de sugestões na mão. Ele respondeu: "É SÓ VOCÊ OLHAR NOS
# HISTÓRICOS DE SUGESTÕES - APRENDA ISSO". Estava certo: isto é leitura de
# arquivo local, não precisa de cota, de internet nem de modelo nenhum.
_RE_HISTORICO_SUG = re.compile(
    r"\b(ultim\w+|penultim\w+|anterior|passad\w+|hist[óo]ric\w+|"
    r"j[áa] sugeri\w*|voc[êe] sugeri\w*|foi sugerid\w*|sugest\w+|sugeri\w+)\b",
    re.I)
_RE_HISTORICO_PEDE = re.compile(
    r"\b(onde|qual|quais|quando|que horas?|quanto|lista|mostra|me diz|"
    r"teve|houve|existe|existiu)\b", re.I)

def pergunta_sobre_historico_sugestoes(texto):
    t = _norm_busca(texto or "")
    return bool(t and _RE_HISTORICO_SUG.search(t) and _RE_HISTORICO_PEDE.search(t))

def responder_historico_sugestoes(texto, sinais=None):
    """Responde do ARQUIVO de sugestões. Sem API, sem internet, sem chute.
    Devolve None quando não há o que responder — e "não achei" é dito com
    esses termos, nunca convertido em 'não sei'."""
    def _quando(reg):
        """'10/08/2026 13:02:41' -> '13:02'. O campo gravado é `data_hora`, com
        segundos; devolve string vazia quando não dá para ler — nunca inventa
        um horário."""
        txt = str(reg.get("data_hora") or reg.get("hora") or "").strip()
        m = re.search(r"(\d{1,2}:\d{2})", txt)
        return m.group(1) if m else ""

    try:
        registros = list(sinais if sinais is not None else
                         [r for r in carregar_sinais_log()
                          if _e_da_conta_ativa(r)])
    except Exception:
        return None
    if not registros:
        return ("Ainda não há nenhuma sugestão registrada nesta conta — o "
                "histórico está vazio. Não é falta de acesso: é que o motor "
                "não gerou cenário nenhum ainda.")
    t = _norm_busca(texto)
    # Filtro por ATIVO, se ele citou um.
    ativos = sorted({str(r.get("ativo", "")).upper() for r in registros
                     if r.get("ativo")}, key=len, reverse=True)
    ativo_alvo = next((a for a in ativos if a and _norm_busca(a) in t), None)
    # ELE CITOU UM ATIVO QUE NÃO ESTÁ NO HISTÓRICO? Isso tem de ser dito como
    # "procurei e não achei", nunca virar a sugestão de OUTRO ativo — devolver
    # o MGCV6 para quem perguntou de PETR4 seria pior que não responder.
    if not ativo_alvo:
        # QUE ERRO ISTO CONSERTA: o padrão antigo era `[A-Z]{3,6}\d{0,2}` sobre
        # o texto EM MAIÚSCULAS. O trader escreveu "qual a utima sugestao ?" e
        # ela respondeu "NÃO há sugestão de QUAL registrada" — porque "QUAL"
        # tem quatro letras maiúsculas e o dígito era opcional. Qualquer palavra
        # virava ticker.
        #
        # Os ativos que esta ferramenta opera SEMPRE têm dígito no código:
        # futuros (MESU6, MGCV6, WINZ5) e ações da B3 (PETR4). Exigir o dígito
        # elimina a palavra comum sem eliminar ticker nenhum. Palavra sem
        # dígito passa a ser ignorada — silêncio é melhor que afirmação errada.
        citados = [c for c in re.findall(r"\b[A-Z]{2,6}\d{1,2}\b",
                                         str(texto or "").upper())
                   if c not in ("SELL", "BUY", "STOP", "TP", "TP1", "TP2",
                                "SMC", "IA", "API", "USD", "PNL", "H1", "H4",
                                "M1", "M5", "M15", "M30", "D1", "W1", "RR",
                                "SP500", "S&P500")]
        if citados and not any(c in ativos for c in citados):
            return (f"Procurei no histórico e NÃO há sugestão de "
                    f"{citados[0]} registrada. O que existe lá: "
                    + ", ".join(sorted({f"{r.get('direcao','?')} {r.get('ativo','?')}"
                                        for r in registros[-25:]})) + ".")
    # Filtro por LADO, se ele disse compra ou venda.
    lado = None
    if re.search(r"\b(vend\w+|sell|short)\b", t):
        lado = "SELL"
    elif re.search(r"\b(compr\w+|buy|long)\b", t):
        lado = "BUY"
    filtrados = [r for r in registros
                 if (not ativo_alvo or str(r.get("ativo", "")).upper() == ativo_alvo)
                 and (not lado or str(r.get("direcao", "")).upper().startswith(lado[0]))]
    if not filtrados:
        alvo_txt = " ".join(x for x in (lado and ("de venda" if lado == "SELL"
                                                 else "de compra"),
                                        ativo_alvo and f"de {ativo_alvo}") if x)
        return (f"Procurei no histórico e NÃO há sugestão {alvo_txt} registrada. "
                "O que existe lá: " +
                ", ".join(sorted({f"{r.get('direcao','?')} {r.get('ativo','?')}"
                                  for r in registros[-25:]})) + ".")
    quer_lista = bool(re.search(r"\b(lista|todas|quais|hist[óo]ric)", t))
    escolhidos = filtrados[-8:] if quer_lista else filtrados[-1:]
    linhas = []
    for r in escolhidos:
        dec = r.get("decisao") or ""
        res = r.get("resultado")
        situacao = (f" · {dec}" if dec else "") + (
            f" · resultado US$ {_num(res):+,.2f}" if _num(res) is not None else "")
        linhas.append(
            f"• {_quando(r) or '—'} — {r.get('direcao','?')} "
            f"{r.get('ativo','?')}: entrada {r.get('entry','—')}, "
            f"stop {r.get('stop','—')}, alvo {r.get('tp1','—')}"
            + (f", probabilidade {_num(r.get('probabilidade')) or 0:.0f}%"
               if r.get("probabilidade") is not None else "") + situacao)
    cabeca = ("As últimas sugestões registradas:" if quer_lista else
              "A última sugestão registrada"
              + (f" de {ativo_alvo}" if ativo_alvo else "")
              + (" de venda" if lado == "SELL" else
                 " de compra" if lado == "BUY" else "") + ":")
    return cabeca + "\n" + "\n".join(linhas) + (
        "\n\nIsso vem do histórico gravado aqui no seu computador — não "
        "depende de cota nem de internet.")

# --------------------------------------------------------------------
# "COMPRO OU VENDO?" — a pergunta mais direta que existe na mesa
# --------------------------------------------------------------------
# No log de 10/08 ela recebeu exatamente isso e devolveu o despejo genérico de
# "não tenho como responder". É a pergunta mais simples e a mais importante do
# dia inteiro: o trader quer o LADO. Responder isso sem olhar o gráfico é
# adivinhação; então a pergunta vira captura + leitura, igual à pergunta de
# nível ("onde ponho o stop?").
_RE_QUAL_LADO = re.compile(
    r"\b(compr\w+\s+ou\s+vend\w+|vend\w+\s+ou\s+compr\w+|"
    r"compra\s+ou\s+venda|venda\s+ou\s+compra|"
    r"long\s+ou\s+short|short\s+ou\s+long|buy\s+ou\s+sell|sell\s+ou\s+buy|"
    r"(qual|que)\s+((é|e|a|o|as|os|meu|minha)\s+)*(lado|dire[çc][ãa]o|vi[ée]s)|"
    r"(devo|posso|vale a pena|melhor)\s+(compr\w+|vend\w+|entrar)|"
    r"entro\s+(comprad\w+|vendid\w+|na\s+(compra|venda))|"
    r"(t[áa]|ta|est[áa])\s+(comprad|vendid)\w*\s+ou)\b", re.I)

def pergunta_qual_lado(texto):
    """'compro ou vendo?', 'qual o lado?', 'devo comprar?'. Não confundir com
    'estou comprado ou vendido?', que é pergunta de POSIÇÃO — essa fala de
    'estou/minha posição' e sai daqui pela porta de baixo."""
    t = _norm_busca(texto or "")
    if not t:
        return False
    if re.search(r"\b(estou|to|tou|minha posi|minha operacao|na plataforma)\b", t):
        return False
    return bool(_RE_QUAL_LADO.search(t))

# --------------------------------------------------------------------
# "O STOP DO MESU6 É 7760 E O ALVO É 7800" — o trader informando o bracket
# --------------------------------------------------------------------
# Posição detectada NA PLATAFORMA entra no diário com stop e alvo vazios: a
# leitura da tela dá ativo, direção, quantidade e preço, e nada mais. Inventar
# os níveis seria inventar risco. Mas sem eles o app não calcula risco em US$
# nem avisa quando a estrutura vira contra — e o trader ficava olhando
# "stop None · alvo None" sem ter como consertar. Agora ele DIZ, e é código
# que grava.
_RE_DEFINIR_NIVEL = re.compile(
    r"\b(stop|alvo|alvos|take|tp1?|objetivo|gain)\b[^.;]{0,20}?"
    r"\b(é|e|eh|fica|ficou|est[áa]|ta|em|de|:|vai (ser|pra|para))\b", re.I)

def interpretar_niveis_da_posicao(texto, ativos_conhecidos=None):
    """Extrai {'ativo', 'stop', 'tp1'} de uma frase como
    'o stop do MESU6 é 7760 e o alvo é 7800'. Devolve None quando não há
    número nenhum atrelado a stop/alvo — melhor não fazer nada do que gravar
    um nível errado no risco do trader.

    `ativos_conhecidos` são os tickers que existem HOJE no diário. Só eles
    valem como ativo: assim a frase não vira um ticker inventado."""
    bruto = str(texto or "")
    if not bruto.strip() or not _RE_DEFINIR_NIVEL.search(bruto):
        return None

    def _apanhar(rotulos):
        """Número que vem logo DEPOIS de uma das palavras-âncora.

        O número tem de estar SOLTO — nem colado a letra, nem colado a outro
        dígito. Sem essa exigência, 'o stop do MESU6 é 7760' gravava stop = 6:
        o "6" do ticker vinha antes do 7760 e ganhava. Um stop de 6 pontos onde
        deveriam ser 7760 não é um erro de exibição, é o risco inteiro errado."""
        solto = r"(?<![A-Za-z0-9])(-?\d+(?:[.,]\d+)?)(?![A-Za-z0-9])"
        for rot in rotulos:
            m = re.search(rot, bruto, re.I)
            if not m:
                continue
            n = re.search(solto, bruto[m.end():m.end() + 40])
            if n:
                try:
                    return float(n.group(1).replace(",", "."))
                except ValueError:
                    continue
        return None

    stop = _apanhar([r"\bstops?\b"])
    tp1 = _apanhar([r"\balvos?\b", r"\btakes?\b", r"\btp1?\b", r"\bobjetivos?\b",
                    r"\bgain\b"])
    if stop is None and tp1 is None:
        return None

    ativo = None
    alto = bruto.upper()
    for cand in sorted({str(a).upper() for a in (ativos_conhecidos or []) if a},
                       key=len, reverse=True):
        if cand and cand in alto:
            ativo = cand
            break
    return {"ativo": ativo, "stop": stop, "tp1": tp1}

# --------------------------------------------------------------------
# ERRO DE DIGITAÇÃO NÃO É PERGUNTA NOVA
# --------------------------------------------------------------------
# Do log de 12/08:
#     10:22 ❯ status      → o placar da conta, certinho
#     10:23 ❯ satatus     → o despejo de "não tenho como responder isso"
#     10:31 ❯ tria um print → o mesmo despejo
#     10:31 ❯ tira um print → funcionou
#
# Uma letra trocada e o comando some. Pior: a resposta ao erro de digitação é
# a mesma resposta que ela dá quando não sabe nada — o trader lê aquilo e
# conclui que a ferramenta é burra, quando ela só não reconheceu "satatus".
#
# A correção é comparação por DISTÂNCIA DE EDIÇÃO, com a régua apertada: só
# corrige quando a palavra digitada está a UM erro de distância de um comando
# conhecido E tem tamanho parecido. "satatus"→"status" (1 inserção) corrige;
# "sim" nunca vira "status". Nenhuma correção mexe em dinheiro: o ACATAR
# continua exigindo confirmação depois de corrigido.
_COMANDOS_CONHECIDOS = (
    # substantivos
    "status", "print", "grafico", "gráfico", "motor", "whatsapp",
    "sugestao", "sugestão", "ajuda", "tela", "captura",
    # verbos — é neles que o dedo escorrega ("tria um print")
    "acatar", "dispensar", "cancelar", "tira", "tire", "tirar",
    "olha", "olhar", "mostra", "mostrar", "liga", "ligar",
    "desliga", "desligar", "zera", "zerar", "manda", "mandar",
    "analisa", "analisar", "captura", "capturar",
    # APAGAR UMA LIÇÃO. Faltavam aqui, e o custo apareceu no log: às 14:16 ele
    # escreveu "REMORA ISSO" (um R no lugar do V — distância 1) e a lição
    # ficou gravada; às 14:17 ela repetiu a mesma lição que ele acabara de
    # mandar apagar. Um comando de DESFAZER que só funciona com a grafia
    # perfeita é um comando que falha justo quando mais se precisa dele.
    "remova", "remove", "remover", "apaga", "apague", "apagar",
    "esquece", "esqueça", "esquecer", "deleta", "delete", "deletar",
)

def _distancia_edicao(a, b, teto=2):
    """Distância de Damerau-Levenshtein: conta inserção, remoção, troca de
    letra E TRANSPOSIÇÃO de duas letras vizinhas.

    A transposição é o que separa este código de um Levenshtein comum, e não é
    detalhe: 'stauts' por 'status' é o erro de digitação mais frequente que
    existe (dedo trocando a ordem), e no Levenshtein puro ele custa 2 — cairia
    fora de um teto de 1 e o comando continuaria perdido.

    Desiste cedo: devolve `teto+1` quando passa do teto, porque não interessa
    o valor exato, só se cabe."""
    if abs(len(a) - len(b)) > teto:
        return teto + 1
    anteanterior = None
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            custo = min(anterior[j] + 1,          # remoção
                        atual[j - 1] + 1,          # inserção
                        anterior[j - 1] + (ca != cb))   # troca
            if (i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb):
                custo = min(custo, anteanterior[j - 2] + 1)   # transposição
            atual.append(custo)
        if min(atual) > teto:
            return teto + 1
        anteanterior, anterior = anterior, atual
    return anterior[-1]

def corrigir_digitacao(texto):
    """Troca palavras que estão a UM erro de um comando conhecido. Devolve
    (texto_corrigido, houve_correcao). Palavras curtas (até 3 letras) NUNCA
    são corrigidas: 'sim', 'nao' e 'tp' são palavras inteiras, e mexer nelas
    trocaria a intenção do trader em vez de consertar um deslize."""
    palavras = str(texto or "").split()
    saida, mudou = [], False
    for p in palavras:
        nu = re.sub(r"[^\wáàâãéêíóôõúç]", "", p.lower())
        if len(nu) <= 3 or nu in _COMANDOS_CONHECIDOS:
            saida.append(p)
            continue
        alvo = next((c for c in _COMANDOS_CONHECIDOS
                     if _distancia_edicao(nu, c, 1) == 1), None)
        if alvo:
            saida.append(alvo)
            mudou = True
        else:
            saida.append(p)
    return " ".join(saida), mudou


# --------------------------------------------------------------------
# POST-MORTEM: "o que deu errado nessa sugestão?"
# --------------------------------------------------------------------
# Do log de 12/08:
#     11:31 ✳ "Operação encerrada no STOP: BUY MESU6, US$-135,00.
#              Quer revisar o que deu errado nesse cenário?"
#     11:32 ❯ sim
#     11:32 ✳ "Não tenho como responder isso com segurança agora..."
#     11:35 ❯ o que deu errado na sugestão que você havia me passado
#     11:35 ✳ [o mesmo parágrafo]
#
# ELA PERGUNTOU e não soube responder o próprio convite. E o pior: a resposta
# estava INTEIRA no disco — entrada, stop, alvo, contratos, confluências,
# resultado, e a leitura que o motor fez enquanto a operação corria. Nada disso
# precisa de modelo, de cota ou de internet. É aritmética sobre o diário.
_RE_POSTMORTEM = re.compile(
    r"\b(o que|por ?que|porqu[êe]|pq|como)\b[^?]{0,60}?"
    r"\b(deu errado|errou|falhou|n[ãa]o deu certo|perdi|tomei stop|stopou|"
    r"foi stopad\w+|deu ruim|furou)\b"
    r"|\b(revis\w+|analis\w+|explic\w+|entend\w+)\b[^?]{0,40}?"
    r"\b(cen[áa]rio|sugest[ãa]o|opera[çc][ãa]o|trade|stop|perda)\b"
    r"|\bpost.?mortem\b", re.I)

# O PRONOME NÃO RESPONDE "ONDE".
#
# 12/08, três vezes seguidas:
#   14:14 ❯ TIRA UM PRINT, ONDE ESTA A VWAP?
#   14:14 ✳ "O preço agora trabalha acima dela, em 7774.25"
#   14:15 ❯ TIRA UM PRINT, CONSEGUE ME FALAR ONDE ESTA A VWAP?
#   14:15 ✳ "O preço atual está trabalhando acima dela, em 7773.50"
#   14:16 ❯ MAS A PORRA DO VWAP ESTA EM 7769,78
#
# Ela citou o preço (que ele já via na tela) e NUNCA disse onde estava a VWAP.
# "acima dela" não responde "onde está ela". O número que ela deu era o do
# ativo, não o do indicador — e é por isso que ele achou que ela estava
# respondendo, quando não estava.
_INDICADORES = (r"vwap|m[ée]dia m[óo]vel|\bmm\d*\b|\bema\d*\b|\bsma\d*\b|"
                r"bollinger|fibonacci|\brsi\b|order block|\bob\b|\bfvg\b|"
                r"suporte|resist[êe]ncia|pivot|poc|va[hl]\b")
_RE_ONDE_INDICADOR = re.compile(
    r"\b(onde|qual|quanto|em que (n[íi]vel|pre[çc]o)|que valor)\b[^?]{0,40}?"
    r"(" + _INDICADORES + r")", re.I)

def pergunta_onde_esta_indicador(texto):
    t = _norm_busca(texto or "")
    return bool(t and _RE_ONDE_INDICADOR.search(t))

def resposta_enrola_o_nivel(pergunta, resposta):
    """True quando ele perguntou ONDE está um indicador e a resposta não traz
    NENHUM número junto do nome dele — só pronome.

    A régua é deliberadamente simples: procura o nome do indicador no texto da
    resposta e exige um número a até 60 caracteres dele. Citar o preço do ativo
    em outro trecho não conta: foi exatamente esse o engano."""
    if not pergunta_onde_esta_indicador(pergunta):
        return False
    r = str(resposta or "")
    if not r.strip():
        return False
    # Ela já admitiu que não consegue ler? Então não está enrolando.
    if re.search(r"n[ãa]o (consigo|consegui|d[áa] para) (ler|identificar|ver)",
                 r, re.I):
        return False
    for m in re.finditer(_INDICADORES, r, re.I):
        janela = r[m.start():m.end() + 60]
        if re.search(r"\d{2,}[.,]?\d*", janela):
            return False         # nome DO INDICADOR com número junto: respondeu
    return True                  # só pronome, ou número solto longe do nome


# --------------------------------------------------------------------
# LER O NÚMERO EM VEZ DE PERGUNTAR O NÚMERO
# --------------------------------------------------------------------
# A raiz do caso da VWAP não era o prompt, nem a falta de guarda: era estar
# usando a ferramenta ERRADA. "VWAP 7769.56" na legenda é TEXTO IMPRESSO. Um
# LLM não lê pixel, ele PREVÊ o texto mais provável — e por isso nunca diz
# "não sei", ele completa. Foi assim que 7769.56 virou 7752.34.
#
# OCR lê. E OCR não precisa de chave, de internet nem de cota: os dois
# sistemas trazem um motor embutido (Vision no macOS, Windows.Media.Ocr no
# Windows). Aqui a leitura vira número, deterministicamente.
#
# Os rótulos são os que aparecem de fato na legenda das plataformas que ele
# usa. Cada um mapeia para o nome que o trader fala.
_ROTULOS_LEGENDA = {
    "VWAP": r"VWAP",
    "SMA": r"SMA|MA|M[ÉE]DIA M[ÓO]VEL",
    "EMA": r"EMA",
    "RSI": r"RSI",
    "PSAR": r"PSAR|SAR PARAB[ÓO]LICO",
    "ABERTURA": r"OPEN|ABERTURA",
    "MAXIMA": r"HIGH|M[ÁA]XIMA",
    "MINIMA": r"LOW|M[ÍI]NIMA",
    "FECHAMENTO": r"CLOSE|FECHAMENTO",
    "VOLUME": r"VOL(?:UME)?",
    "BOLLINGER": r"BOLL(?:INGER)?|BB",
    "POC": r"\bPOC\b|VPOC",
}
# Rótulos que NÃO são leitura de mercado: são a configuração do indicador,
# impressa junto dele. Ler "OVERBOUGHT 70" como se fosse um nível de preço é
# o tipo de erro que passaria despercebido — 70 é um parâmetro, não um preço.
_ROTULOS_IGNORADOS = r"^(MIDDLE|OVERBOU\w*|OVERSOL\w*|UPPER|LOWER|LENGTH|PER[ÍI]ODO)$"


def _numero_da_legenda(bruto):
    """'7.769,56' e '7,769.56' e '7769.56' viram 7769.56. None se não for número."""
    b = str(bruto or "").strip().replace(" ", "")
    if not re.fullmatch(r"-?[\d.,]+", b) or not re.search(r"\d", b):
        return None
    # O separador DECIMAL é o ÚLTIMO ponto ou vírgula, quando sobram 1 ou 2
    # dígitos depois dele. Fatiar posição fixa (b[:-3]) presumia SEMPRE dois
    # decimais e quebrava em '-12,5' — e o tick do M2K é 0,1. Foi o teste que
    # pegou; num pregão isso viraria um número errado com cara de certo.
    m = re.search(r"[.,](\d{1,2})$", b)
    if m:
        b = b[:m.start()].replace(".", "").replace(",", "") + "." + m.group(1)
    else:
        b = b.replace(".", "").replace(",", "")
    try:
        return float(b)
    except ValueError:
        return None


def ler_indicadores_da_legenda(texto_ocr):
    """Transforma o texto lido pelo OCR nos VALORES dos indicadores.

    Função PURA — é o coração desta camada e por isso é a parte testada.
    Devolve {'VWAP': 7769.56, 'SMA': [7767.58, 7766.04], ...}. Rótulo repetido
    (duas SMAs no mesmo gráfico) vira LISTA: dizer que a média é 7767.58
    quando há duas seria escolher uma às escondidas.

    Dicionário vazio significa 'não li nada' — nunca 'não há nada'."""
    achados = {}
    for linha in str(texto_ocr or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        # A legenda vem como "RÓTULO valor" na mesma linha. Aceita ':' e '=' no
        # meio, que algumas plataformas usam.
        m = re.match(r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ \-\.]{0,24}?)\s*[:=]?\s+"
                     r"(-?[\d.,]+)\s*$", linha)
        if not m:
            continue
        rotulo, bruto = m.group(1).strip().upper(), m.group(2)
        if re.match(_ROTULOS_IGNORADOS, rotulo):
            continue
        valor = _numero_da_legenda(bruto)
        if valor is None:
            continue
        for chave, padrao in _ROTULOS_LEGENDA.items():
            if re.fullmatch(padrao, rotulo, re.I):
                if chave in achados:
                    if not isinstance(achados[chave], list):
                        achados[chave] = [achados[chave]]
                    achados[chave].append(valor)
                else:
                    achados[chave] = valor
                break
    return achados


# Como o trader chama cada coisa → a chave da legenda.
_APELIDOS_INDICADOR = {
    "VWAP": "VWAP",
    "MEDIA MOVEL": "SMA", "MEDIA": "SMA", "MM": "SMA", "SMA": "SMA",
    "EMA": "EMA", "RSI": "RSI", "PSAR": "PSAR", "SAR": "PSAR",
    "VOLUME": "VOLUME", "POC": "POC", "BOLLINGER": "BOLLINGER",
    "ABERTURA": "ABERTURA", "MAXIMA": "MAXIMA", "MINIMA": "MINIMA",
    "FECHAMENTO": "FECHAMENTO",
}


def chave_do_indicador(nome):
    """'a média móvel' / 'VWAP' / 'o RSI' → a chave da legenda, ou None."""
    n = _sem_acento(str(nome or "")).upper().strip()
    n = re.sub(r"\b(DE|DA|DO|A|O)\b", " ", n)
    n = re.sub(r"\d+", " ", n)                 # "média móvel de 50" → "média móvel"
    n = re.sub(r"\s+", " ", n).strip()
    for apelido, chave in _APELIDOS_INDICADOR.items():
        if _sem_acento(apelido).upper() == n:
            return chave
    for apelido, chave in _APELIDOS_INDICADOR.items():
        if _sem_acento(apelido).upper() in n:
            return chave
    return None


def resposta_do_indicador_lido(nome, valores):
    """A resposta PRONTA, montada só com o que o OCR leu — sem modelo nenhum.

    Devolve None quando não deu para ler: aí o caminho normal segue. Ausência
    de leitura nunca vira conclusão."""
    chave = chave_do_indicador(nome)
    if not chave or not valores or chave not in valores:
        return None
    v = valores[chave]
    if isinstance(v, list):
        lista = ", ".join(f"{x:g}" for x in v)
        return (f"Li direto da legenda do gráfico: há {len(v)} {nome} na tela, "
                f"em {lista}. Não vou escolher uma por você — se quiser saber "
                "de qual delas estou falando, me diga o período.")
    return (f"Li direto da legenda do gráfico: **{nome} = {v:g}**.\n\n"
            "Este número não passou por modelo nenhum — foi lido do texto da "
            "imagem aqui na sua máquina, sem API e sem internet. Se estiver "
            "diferente do que você vê na tela, a captura está velha: peça "
            "'tira um print' que eu leio de novo.")


def indicador_da_pergunta(texto):
    """QUAL indicador ele perguntou. Devolve o trecho como ele escreveu (para
    a segunda leitura pedir exatamente aquilo), ou None."""
    m = re.search(_INDICADORES, str(texto or ""), re.I)
    return m.group(0).strip() if m else None


# --------------------------------------------------------------------
# A EVASÃO VIROU INVENÇÃO — E INVENÇÃO É PIOR
# --------------------------------------------------------------------
# A guarda da 2.25.0 exigia o NÚMERO do indicador junto do nome dele. Ela
# cumpriu o que prometia e produziu o efeito seguinte, no print de 12/08 15:43:
#
#     "a VWAP está exatamente em 7752.34, conforme indicado na legenda"
#
# A legenda da imagem diz VWAP 7769.56. Ela também disse "média móvel de 50
# períodos em 7751.28" (a legenda tem duas SMAs: 7767.58 e 7766.04) e "você
# está com uma posição de venda aberta em 7753.25" (a plataforma mostra
# POSIÇÃO 0). Três números inventados numa resposta só — todos com a forma
# certa, e por isso todos passariam pela guarda anterior.
#
# Exigir a FORMA de uma resposta só muda a forma da mentira. O que separa uma
# leitura de uma invenção não é o formato: é a ESTABILIDADE. Ler duas vezes o
# mesmo texto na mesma imagem dá o mesmo número; inventar duas vezes dá dois
# números diferentes. É nisso que esta segunda leitura se apoia — e ela custa
# uma chamada extra só quando a pergunta é de nível, que é raro.
def extrair_valor_do_indicador(indicador, texto):
    """O número que o texto atribui AO INDICADOR — não o preço do ativo.

    Função PURA. Devolve float ou None. A janela é curta de propósito: em
    "a VWAP está em 7769.56; o preço trabalha acima dela, em 7774.25" o número
    do indicador é o primeiro, e o do ativo não pode ser confundido com ele."""
    nome = str(indicador or "").strip()
    if not nome:
        return None
    for m in re.finditer(re.escape(nome), str(texto or ""), re.I):
        janela = str(texto)[m.end():m.end() + 45]
        v = re.search(r"(-?\d{1,7}(?:[.,]\d{1,4})?)", janela)
        if v:
            try:
                return float(v.group(1).replace(",", "."))
            except ValueError:
                continue
    return None


def numero_da_segunda_leitura(texto):
    """A segunda leitura responde SÓ o número (ou NAO_LEGIVEL). Devolve float
    ou None — e None aqui significa 'ela não leu', nunca 'pode seguir'."""
    t = str(texto or "").strip()
    if not t or re.search(r"NAO_?LEG[ÍI]VEL|N[ÃA]O_?LEG", t, re.I):
        return None
    v = re.search(r"(-?\d{1,7}(?:[.,]\d{1,4})?)", t)
    if not v:
        return None
    try:
        return float(v.group(1).replace(",", "."))
    except ValueError:
        return None


def leituras_do_indicador_batem(a, b):
    """Duas leituras do MESMO valor impresso na MESMA imagem.

    Tolerância apertada de propósito: OCR do mesmo texto ou bate, ou erra
    feio. Meio ponto (ou 0,02% em contrato caro) cobre o arredondamento de
    quem lê '7769.56' e escreve '7769.5'; não cobre 7752 contra 7769."""
    if a is None or b is None:
        return False
    limite = max(0.5, abs(a) * 0.0002)
    return abs(a - b) <= limite


_AVISO_LEITURA_INSTAVEL = (
    "\n\n⚠️ Não vou entregar esse número. Eu li a MESMA imagem duas vezes e "
    "saíram valores diferentes ({a} e {b}) — quando isso acontece, não é "
    "leitura, é chute com cara de leitura, e chute na sua mesa vira prejuízo. "
    "**Não consigo ler esse valor nesta captura.** Se o rótulo do indicador "
    "estiver visível no gráfico, tire o print com ele à mostra que eu leio; se "
    "não estiver, o número certo é o da sua plataforma.")


def conferir_leitura_de_nivel(resposta, indicador, dito, confirmado):
    """Devolve (texto, instavel). Quando as duas leituras não batem, a resposta
    sai SEM o número, com a admissão no lugar."""
    if leituras_do_indicador_batem(dito, confirmado):
        return resposta, False
    if dito is None:
        return resposta, False        # ela não afirmou número nenhum: nada a conferir
    corpo = str(resposta or "").rstrip()
    aviso = _AVISO_LEITURA_INSTAVEL.format(
        a=f"{dito:g}",
        b=(f"{confirmado:g}" if confirmado is not None
           else "nada legível na segunda passada"))
    return f"{corpo}{aviso}", True


# --------------------------------------------------------------------
# ELA DISSE QUE ELE ESTAVA VENDIDO. ELE ESTAVA ZERADO.
# --------------------------------------------------------------------
# Do print de 12/08 15:43: "Note que você está com uma posição de venda aberta
# em 7753.25". As duas janelas da Tradovate mostram POSIÇÃO 0 e ABRIR P/L
# 0.00 USD. Não é detalhe de redação: é dizer a alguém que ele está no mercado
# quando não está — e a recíproca, dizer que está zerado carregando posição, é
# ainda pior. O app SABE a resposta; basta conferir antes de entregar.
_RE_ALEGA_POSICAO = re.compile(
    r"\bvoc[êe]\s+(est[áa]|segue|continua|permanece)\s+"
    r"(com\s+)?(uma\s+|um\s+)?(posi[çc][ãa]o\s+)?(de\s+)?"
    r"(compra(?:d[oa])?|venda|vendid[oa]|comprad[oa]|long|short|buy|sell)\b",
    re.I)
_RE_ALEGA_ZERADO = re.compile(
    r"(\bvoc[êe]\s+(est[áa]|segue|continua)\s+(zerad[oa]|fora do mercado|flat)\b"
    r"|\bn[ãa]o\s+(h[áa]|tem|existe|possui)\s+(nenhuma\s+)?posi[çc][ãa]o\s+"
    r"(sua\s+)?(aberta|em aberto)\b"
    r"|\bvoc[êe]\s+n[ãa]o\s+est[áa]\s+posicionad[oa]\b)", re.I)


def conferir_posicao_alegada(resposta, abertas):
    """A resposta afirma algo sobre a posição dele que o disco desmente?

    Função PURA. `abertas` é a lista de posições ABERTAS conhecidas.
    Devolve (texto, divergencia) — divergencia em {None, 'inventou', 'omitiu'}."""
    texto = str(resposta or "")
    if not texto.strip():
        return texto, None
    tem = bool(abertas)
    if _RE_ALEGA_POSICAO.search(texto) and not tem:
        aviso = ("\n\n⚠️ Corrigindo: eu disse que você está posicionado, e o "
                 "registro diz que **não há nenhuma posição aberta** nesta "
                 "conta. Não opere em cima do que eu escrevi — confira na sua "
                 "plataforma. Dizer a alguém que ele está no mercado quando "
                 "não está é o erro mais caro que eu poderia cometer.")
        return f"{texto.rstrip()}{aviso}", "inventou"
    if _RE_ALEGA_ZERADO.search(texto) and tem:
        detalhe = ", ".join(
            f"{p.get('direcao')} {p.get('ativo')} "
            f"{p.get('contratos') or '?'}x @ {p.get('entry')}"
            for p in abertas[:3])
        aviso = (f"\n\n⚠️ Corrigindo: eu disse que você está fora do mercado, e "
                 f"o registro tem posição ABERTA — {detalhe}. Confira na sua "
                 "plataforma antes de qualquer coisa.")
        return f"{texto.rstrip()}{aviso}", "omitiu"
    return texto, None


_AVISO_NIVEL_NAO_RESPONDIDO = (
    "\n\n⚠️ Corrigindo a mim mesma: você perguntou ONDE está o indicador e eu "
    "não disse o número dele — falei do preço do ativo, que é outra coisa. "
    "Não vou fingir que respondi: **não consigo ler esse valor nesta "
    "captura**. Se o indicador estiver com o rótulo visível no gráfico, tire "
    "o print com ele à mostra que eu leio; se não estiver, o número certo é o "
    "da sua plataforma, não o meu chute.")


# --------------------------------------------------------------------
# A TERCEIRA GUARDA: O NÚMERO DA MESA TEM DONO, E O DONO É O DISCO
# --------------------------------------------------------------------
# As duas guardas anteriores pegam a MENTIRA DE AÇÃO ("já enviei") e a EVASÃO
# DE NÍVEL ("acima dela"). Falta a terceira, que é a que mais custa dinheiro:
# o número ERRADO dito com confiança sobre a conta dele.
#
# O modelo recebe os números certos no contexto e mesmo assim, de vez em
# quando, devolve outro — arredonda, soma errado, mistura o resultado do dia
# com o do ciclo. Pedir no prompt para "não errar" não é engenharia: prompt é
# pedido. Aqui o app CONFERE, e onde a conferência bate de frente com o disco,
# o disco ganha.
#
# Deliberadamente ESTREITO: só entram os fatos que têm UMA fonte inequívoca no
# disco e um rótulo que ninguém usa por acaso numa frase. Vale mais deixar
# passar um erro do que corrigir uma frase certa — corretor que grita errado é
# desligado no segundo dia, e aí não corrige mais nada.
_ROTULOS_DE_FATO = {
    "margem":    r"(?:margem|banca|capital da conta)",
    # "meta diária" e "quanto falta para a meta" são OUTROS números, calculados
    # a partir deste. Corrigir a meta diária contra a meta total seria inventar
    # um erro onde não há — daí as exclusões explícitas.
    "meta":      r"(?:meta(?!\s+(?:di[áa]ria|do dia|de hoje|por dia))"
                 r"(?:\s+de\s+lucro|\s+total|\s+do ciclo)?|objetivo da conta)",
    # Idem: "drawdown restante hoje" é o que sobrou, não o do plano.
    "drawdown":  r"(?:drawdown(?!\s+(?:restante|dispon[íi]vel|de hoje|do dia))"
                 r"(?:\s+m[áa]ximo|\s+total)?|perda m[áa]xima)",
    "hoje":      r"(?:resultado (?:de )?hoje|hoje (?:voc[êe] )?(?:est[áa]|fez)|"
                 r"resultado do dia|no dia de hoje)",
    "ciclo":     r"(?:resultado do ciclo|acumulado do ciclo|no ciclo)",
}
# Tolerância em dólares. Abaixo disso é arredondamento, não erro.
TOLERANCIA_FATO_USD = 1.0


def _valor_perto_do_rotulo(texto, padrao_rotulo, alcance=70):
    """O primeiro valor em dinheiro que aparece logo depois do rótulo.
    Devolve (valor, trecho) ou (None, None)."""
    for m in re.finditer(padrao_rotulo, texto, re.I):
        janela = texto[m.end():m.end() + alcance]
        v = re.search(r"(?:US\$|R\$|\$)\s*(-?[\d.,]+)", janela)
        if not v:
            continue
        bruto = v.group(1).strip().rstrip(".,")
        # 1.400,50 (pt-BR) e 1,400.50 (en-US) na mesma frase acontecem — o
        # separador DECIMAL é o último que aparecer com 1 ou 2 dígitos depois.
        if re.search(r"[.,]\d{1,2}$", bruto):
            corpo, _, dec = bruto[:-3], bruto[-3], bruto[-2:]
            numero = corpo.replace(".", "").replace(",", "") + "." + dec
        else:
            numero = bruto.replace(".", "").replace(",", "")
        try:
            return float(numero), texto[m.start():m.end() + alcance]
        except ValueError:
            continue
    return None, None


def conferir_numeros_da_mesa(resposta, fatos):
    """Confere os números da CONTA DELE citados na resposta contra o disco.

    Função PURA. `fatos` é {chave: valor_real} com as chaves de _ROTULOS_DE_FATO.
    Devolve (texto, divergencias) — `divergencias` é a lista de
    (chave, dito, real). Quando não há divergência, o texto volta intacto."""
    texto = str(resposta or "")
    if not texto.strip() or not fatos:
        return texto, []
    divergencias = []
    for chave, padrao in _ROTULOS_DE_FATO.items():
        real = fatos.get(chave)
        if real is None:
            continue
        dito, _trecho = _valor_perto_do_rotulo(texto, padrao)
        if dito is None:
            continue
        # Comparação por VALOR ABSOLUTO: "hoje você está em US$ 135 negativo"
        # e "US$ -135" são a mesma frase, e o sinal costuma vir por extenso.
        if abs(abs(dito) - abs(float(real))) > TOLERANCIA_FATO_USD:
            divergencias.append((chave, dito, float(real)))
    if not divergencias:
        return texto, []

    nomes = {"margem": "a margem", "meta": "a meta",
             "drawdown": "o drawdown máximo", "hoje": "o resultado de hoje",
             "ciclo": "o resultado do ciclo"}
    linhas = [f"• {nomes.get(k, k)}: eu disse US$ {d:,.2f}; o registrado é "
              f"US$ {r:,.2f}" for k, d, r in divergencias]
    aviso = ("\n\n⚠️ Conferindo o que eu mesma escrevi contra o que está "
             "gravado, dois números não batem — e quem manda é o registro:\n"
             + "\n".join(linhas)
             + "\nUse os do registro. Errar um número da SUA conta é o tipo de "
               "erro que eu não posso deixar passar como se fosse detalhe.")
    if len(divergencias) == 1:
        aviso = aviso.replace("dois números não batem", "um número não bate")
    return f"{texto.rstrip()}{aviso}", divergencias


# A MÁXIMA HISTÓRICA NÃO PODE ESTAR ABAIXO DO PREÇO DE AGORA.
#
# Log de 13/08, 16:31. Ele perguntou a máxima histórica do S&P 500 e recebeu:
#     "A máxima histórica do S&P 500 é de aproximadamente 2.924 pontos,
#      atingido em abril de 2000 durante a crise da bolsa americana."
# Três erros numa frase só, e a ferramenta imprimiu como fato. No MESMO dia,
# no MESMO chat, o motor dela estava lendo o MES em 7.812 — ou seja, ela
# afirmou um teto histórico MENOR que o preço que ela própria tinha acabado de
# ler no gráfico. Não é preciso saber nada de mercado para pegar isso: é
# aritmética. Um recorde abaixo do preço de agora é impossível por definição.
#
# É a diferença entre "o modelo errou" e "a ferramenta deixou passar". O
# modelo vai errar de novo — não tenho como impedir. O que dá para impedir é
# a ferramenta ENTREGAR o erro sem conferir o que ela mesma tem na mão.
_RE_MAXIMA_HISTORICA = re.compile(
    r"(m[áa]xim[ao]|topo|pico|recorde|m[áa]ximo)\s+"
    r"(hist[óo]ric[ao]|de todos os tempos|absolut[ao])"
    r"|all[\- ]time high|\bath\b", re.IGNORECASE)

# O NÚMERO QUE VEM COLADO NO NOME DO ÍNDICE É NOME, NÃO PREÇO.
# "S&P 500", "Nasdaq 100", "Russell 2000" — o 500 ali é batismo. Sem esta
# exclusão, a primeira conferência que eu escrevi acusou "máxima histórica de
# 500" na frase que fala do S&P 500, que é exatamente o tipo de falso positivo
# que faria o trader parar de ler os avisos.
_RE_NOME_DE_INDICE = re.compile(
    r"(s\s*&\s*p|sp|nasdaq|russell|dow(\s+jones)?|ibovespa|ibov|cac|dax|ftse|"
    r"nikkei|euro\s*stoxx)\s*$", re.IGNORECASE)

# Data por extenso: só descarta quando o número REALMENTE parece um ano.
# A primeira versão descartava tudo que vinha depois de "em", e engolia
# "o topo histórico ficou EM 6.147 pontos" — o caso que a trava existe para pegar.
_RE_CONTEXTO_DE_DATA = re.compile(
    r"(\b(em|de|desde|ano de|até|entre)\s+|"
    r"\b(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|"
    r"outubro|novembro|dezembro)\s+de\s+)$", re.IGNORECASE)

def _numeros_de_preco(trecho):
    """Números do trecho que podem ser PREÇO — sem ano, nome de índice ou %.

    '2.924' em português é dois mil novecentos e vinte e quatro, não 2,924:
    ponto seguido de exatamente três dígitos, sem vírgula depois, é separador
    de milhar. Errar isso aqui transformaria a conferência em ruído."""
    achados = []
    for m in re.finditer(r"\d[\d.,]*", trecho):
        bruto = m.group(0).rstrip(".,")
        if not bruto:
            continue
        antes = trecho[:m.start()]
        depois = trecho[m.end():m.end() + 3]
        if _RE_NOME_DE_INDICE.search(antes):
            continue                       # o 500 de "S&P 500" é nome
        if depois.strip().startswith("%"):
            continue                       # percentual não é nível
        if "," in bruto:
            valor = bruto.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", bruto):
            valor = bruto.replace(".", "")   # 2.924 e 12.345 são milhares
        else:
            valor = bruto
        try:
            numero = float(valor)
        except ValueError:
            continue
        # Ano só é descartado quando PARECE ano: inteiro de quatro dígitos numa
        # faixa plausível E precedido de contexto de data. Assim "abril de
        # 2000" sai e "ficou em 6.147 pontos" fica.
        if (1900 <= numero <= 2100 and bruto.isdigit()
                and _RE_CONTEXTO_DE_DATA.search(antes)):
            continue
        achados.append(numero)
    return achados

def conferir_maxima_historica(resposta, preco_agora, nome_ativo=""):
    """Pega o recorde histórico afirmado ABAIXO do preço que a ferramenta lê.

    Função PURA. `preco_agora` é o preço real que o app tem em mãos (leitura do
    motor ou cotação da web); None desliga a conferência — sem preço não há o
    que conferir, e inventar uma checagem seria repetir o defeito.

    Devolve (texto, impossivel) — `impossivel` é o valor afirmado, ou None."""
    texto = str(resposta or "")
    if not texto.strip() or not preco_agora:
        return texto, None
    try:
        agora = float(preco_agora)
    except (TypeError, ValueError):
        return texto, None
    if agora <= 0:
        return texto, None
    for frase in re.split(r"(?<=[.!?])\s+|\n", texto):
        if not _RE_MAXIMA_HISTORICA.search(frase):
            continue
        for valor in _numeros_de_preco(frase):
            # O corte de 20% evita brigar por arredondamento de quem escreveu
            # "a máxima é cerca de 7.800" com o preço em 7.812. O caso real
            # errava por 63% — passa longe de qualquer tolerância.
            if 0 < valor < agora * 0.8:
                nome = f" do {nome_ativo}" if nome_ativo else ""
                aviso = (
                    f"\n\n⚠️ Parei para conferir o que eu mesma escrevi. Eu "
                    f"disse que a máxima histórica{nome} é {valor:,.2f}, e o "
                    f"preço que eu estou lendo AGORA é {agora:,.2f} — maior "
                    f"que o suposto recorde. Isso é impossível: o preço de "
                    f"hoje não pode estar acima do topo de todos os tempos.\n"
                    f"Então o número que eu dei está errado, e eu prefiro "
                    f"dizer isso a deixar você levar um dado furado para a "
                    f"mesa. O que eu tenho de verdade é o preço de agora: "
                    f"{agora:,.2f}.")
                return f"{texto.rstrip()}{aviso}", valor
    return texto, None


# NUMA COMPRA, O STOP FICA ABAIXO DA ENTRADA. SEMPRE.
#
# Log de 17/08, das 10:43 às 10:59 — dezesseis minutos de discussão sobre um
# erro que é aritmética pura. Ela escreveu:
#
#     "Vamos considerar uma entrada de COMPRA (buy):
#      • Entrada:   7805.25
#      • Stop Loss: 7813.50      ← ACIMA da entrada
#      • Alvo:      7796.75      ← ABAIXO da entrada
#      • R:R: 2.0"
#
# Isso não é uma compra. Numa compra o stop fica ABAIXO (é onde a ideia morre)
# e o alvo ACIMA (é onde ela se paga). Aqueles números são uma VENDA com o
# rótulo trocado — e o "R:R 2.0" no fim dá ao conjunto uma cara de conta feita.
#
# Ele perguntou "tem certeza que essa lógica está certa?", depois "revise a
# recomendação", depois "é compra ou venda?", depois "então não é buy, é sell,
# olha a recomendação que você me passou, de compra, sendo que o correto seria
# venda!!!". Quatro vezes. Nas quatro ela pediu desculpa e REPETIU os mesmos
# três números. Às 11:03, num "nova análise", repetiu de novo.
#
# Nenhum prompt conserta isso de forma confiável — é o modelo pequeno perdendo
# o fio. O app, esse, consegue: são duas comparações.
_RE_LADO_DO_CENARIO = re.compile(
    r"\b(compra|comprar|buy|long|vend[ae]|vender|sell|short)\b", re.IGNORECASE)
_RE_NIVEL_ROTULADO = {
    "entrada": re.compile(
        r"\b(entrada|entry|preço de entrada|preco de entrada)\b\s*[:\-–]?\s*"
        r"(?:de\s+|em\s+|R\$\s*|US\$\s*)?(\d[\d.,]*)", re.IGNORECASE),
    "stop": re.compile(
        r"\b(stop(?:\s*loss)?|stop-loss)\b\s*[:\-–]?\s*"
        r"(?:de\s+|em\s+|R\$\s*|US\$\s*)?(\d[\d.,]*)", re.IGNORECASE),
    "alvo": re.compile(
        r"\b(alvo|alvo\s*1|target|take\s*profit|tp1?)\b\s*[:\-–]?\s*"
        r"(?:de\s+|em\s+|R\$\s*|US\$\s*)?(\d[\d.,]*)", re.IGNORECASE),
}

def _numero_rotulado(texto, chave):
    """O número que vem logo depois do rótulo. None quando o rótulo não aparece."""
    m = _RE_NIVEL_ROTULADO[chave].search(texto or "")
    if not m:
        return None
    valores = _numeros_de_preco(m.group(2))
    return valores[0] if valores else None


def lado_do_cenario(texto):
    """'BUY', 'SELL' ou None — de que lado a resposta está recomendando.

    Usa a ÚLTIMA menção de propósito: o modelo costuma abrir com o contexto
    ('o viés institucional é de venda') e fechar com a recomendação. Quando as
    duas brigam, o defeito aparece de qualquer forma na conferência dos níveis."""
    achados = _RE_LADO_DO_CENARIO.findall(str(texto or ""))
    if not achados:
        return None
    ultimo = achados[-1].lower()
    if ultimo.startswith(("compra", "comprar", "buy", "long")):
        return "BUY"
    return "SELL"


def conferir_coerencia_do_cenario(resposta):
    """Pega o cenário cujo stop e alvo estão do lado errado da entrada.

    Função PURA. Devolve (texto, problema) — `problema` é None quando está
    tudo certo, ou uma frase curta dizendo o que não fecha.

    Só age quando os TRÊS números aparecem rotulados. Com dois, não dá para
    saber se falta informação ou se está errado — e acusar sem certeza é o
    caminho mais rápido para ele parar de ler os avisos."""
    texto = str(resposta or "")
    if not texto.strip():
        return texto, None
    lado = lado_do_cenario(texto)
    if lado is None:
        return texto, None
    entrada = _numero_rotulado(texto, "entrada")
    stop = _numero_rotulado(texto, "stop")
    alvo = _numero_rotulado(texto, "alvo")
    if entrada is None or stop is None or alvo is None:
        return texto, None
    if not (entrada > 0 and stop > 0 and alvo > 0):
        return texto, None

    erros = []
    if lado == "BUY":
        if stop > entrada:
            erros.append(f"o stop ({stop:,.2f}) está ACIMA da entrada "
                         f"({entrada:,.2f}) — numa compra ele fica abaixo")
        if alvo < entrada:
            erros.append(f"o alvo ({alvo:,.2f}) está ABAIXO da entrada "
                         f"({entrada:,.2f}) — numa compra ele fica acima")
    else:
        if stop < entrada:
            erros.append(f"o stop ({stop:,.2f}) está ABAIXO da entrada "
                         f"({entrada:,.2f}) — numa venda ele fica acima")
        if alvo > entrada:
            erros.append(f"o alvo ({alvo:,.2f}) está ACIMA da entrada "
                         f"({entrada:,.2f}) — numa venda ele fica abaixo")
    if not erros:
        return texto, None

    virado = "VENDA" if lado == "BUY" else "COMPRA"
    aviso = (
        f"\n\n⛔ PARE — esse cenário não fecha, e o erro é meu.\n"
        f"Eu escrevi {'COMPRA' if lado == 'BUY' else 'VENDA'}, mas "
        + "; ".join(erros) + ".\n"
        f"Do jeito que os números estão, isso é uma {virado} com o rótulo "
        f"trocado. NÃO opere por esta mensagem.\n"
        f"Me peça de novo ('nova análise') e confira: numa compra o stop fica "
        f"abaixo da entrada e o alvo acima; numa venda é o contrário.")
    return f"{texto.rstrip()}{aviso}", "; ".join(erros)


def corrigir_enrolacao_de_nivel(pergunta, resposta):
    """Devolve (texto, corrigiu). Quando ela enrolou o nível, a resposta segue
    — mas com a admissão colada no fim. Apagar o parágrafo inteiro tiraria a
    leitura de contexto, que costuma estar certa; o que não pode é a evasão
    passar como se fosse resposta."""
    if not resposta_enrola_o_nivel(pergunta, resposta):
        return resposta, False
    return f"{str(resposta).rstrip()}{_AVISO_NIVEL_NAO_RESPONDIDO}", True


def pergunta_postmortem(texto):
    t = _norm_busca(texto or "")
    return bool(t and _RE_POSTMORTEM.search(t))

def montar_postmortem(pos=None):
    """A autópsia da última operação FECHADA, feita só com o que está gravado.

    Sem API, sem internet, sem modelo. Devolve None quando não há operação
    fechada — e "não há" é dito com essas palavras, nunca convertido em
    "não sei responder"."""
    try:
        fechadas = [p for p in posicoes_do_ciclo()
                    if p.get("status") == "FECHADA"
                    and p.get("pnl_final") is not None]
    except Exception:
        return None
    alvo = pos or (fechadas[-1] if fechadas else None)
    if not alvo:
        return ("Não há operação encerrada nesta conta para eu revisar. Assim "
                "que uma fechar — no stop, no alvo ou na mão — eu monto a "
                "autópsia com os números reais dela.")

    e, s = _num(alvo.get("entry")), _num(alvo.get("stop"))
    t1, t2 = _num(alvo.get("tp1")), _num(alvo.get("tp2"))
    pnl = _num(alvo.get("pnl_final")) or 0.0
    ctr = int(alvo.get("contratos") or 1)
    ativo = alvo.get("ativo", "?")
    direcao = alvo.get("direcao", "?")
    vpp = alvo.get("vpp") or valor_por_ponto_do_ativo(ativo)
    ganhou = pnl > 0

    linhas = [
        f"AUTÓPSIA — {direcao} {ativo}, encerrada em "
        f"{alvo.get('data_fechamento', '—')} com US${pnl:+,.2f} ({ctr} ctr).",
        ""]

    # 1. O QUE ESTAVA PLANEJADO
    risco_pts = abs(e - s) if (e is not None and s is not None) else None
    alvo_pts = abs((t1 or t2) - e) if (e is not None and (t1 or t2)) else None
    linhas.append("O QUE ESTAVA NO PLANO:")
    linhas.append(f"• Entrada {e if e is not None else '—'} · "
                  f"stop {s if s is not None else '—'} · "
                  f"alvo {t1 if t1 is not None else '—'}")
    if risco_pts:
        linhas.append(
            f"• Risco planejado: {risco_pts:g} ponto(s) = "
            f"US${risco_pts * vpp * ctr:,.2f} com {ctr} contrato(s)")
        tick = tick_do_ativo(ativo)
        if tick:
            linhas.append(f"• Isso é {risco_pts / tick:.0f} tick(s) de stop")
    if risco_pts and alvo_pts:
        linhas.append(f"• R:R planejado: 1:{alvo_pts / risco_pts:.2f}")

    # 2. O QUE ACONTECEU DE FATO
    linhas.append("")
    linhas.append("O QUE ACONTECEU:")
    if alvo.get("entry_planejado") and _num(alvo["entry_planejado"]) != e:
        linhas.append(
            f"• A entrada SAIU DIFERENTE do sugerido: planejado "
            f"{alvo['entry_planejado']}, executado {e}. Todo o R:R foi "
            "calculado a partir do número planejado.")
    if alvo.get("contratos_planejados") and \
            int(alvo["contratos_planejados"]) != ctr:
        linhas.append(
            f"• A QUANTIDADE saiu diferente: o plano dimensionou "
            f"{alvo['contratos_planejados']} contrato(s), foram executados "
            f"{ctr}. O risco real foi "
            f"{ctr / int(alvo['contratos_planejados']):.1f}× o autorizado.")
    if risco_pts and pnl < 0:
        perda_planejada = risco_pts * vpp * ctr
        if abs(pnl) > perda_planejada * 1.15:
            linhas.append(
                f"• A perda ({abs(pnl):,.2f}) foi MAIOR que o risco planejado "
                f"(US${perda_planejada:,.2f}). Isso significa que o stop não "
                "segurou no nível — houve deslizamento, ou ele não estava na "
                "plataforma.")
        else:
            linhas.append(
                f"• A perda ficou dentro do risco planejado "
                f"(US${perda_planejada:,.2f}). O stop fez o trabalho dele: "
                "limitou o prejuízo ao que o plano previa.")
    if ganhou:
        linhas.append(f"• Resultado positivo de US${pnl:,.2f}.")

    # 3. O QUE O MOTOR VIU ENQUANTO A OPERAÇÃO CORRIA
    confl = alvo.get("confluencias") or []
    if confl:
        linhas.append("")
        linhas.append("A LEITURA QUE JUSTIFICOU A ENTRADA:")
        for c in confl[:8]:
            linhas.append(f"• {c}")

    # 4. A LIÇÃO — sem moral da história inventada
    linhas.append("")
    if pnl < 0 and risco_pts:
        tick = tick_do_ativo(ativo)
        curto = tick and (risco_pts / tick) < MIN_TICKS_STOP_PADRAO
        if curto:
            linhas.append(
                f"O QUE EU VEJO: o stop tinha {risco_pts / tick:.0f} tick(s) — "
                "abaixo do piso da casa. Stop desse tamanho é ruído de mercado, "
                "não invalidação de estrutura: ele é acionado por oscilação "
                "normal, mesmo com a leitura certa.")
        else:
            linhas.append(
                "O QUE EU VEJO: o stop tinha tamanho adequado e foi respeitado. "
                "Um trade com stop correto que perde não é erro de execução — é "
                "o custo estatístico da estratégia. O que importa é a série, "
                "não este trade.")
    linhas.append("")
    linhas.append("(Isto vem do diário gravado no seu computador — não depende "
                  "de cota, de internet nem de modelo.)")
    return "\n".join(linhas)


def interpretar_intencao(texto):
    """Detecta comandos em LINGUAGEM NATURAL, sem depender da IA (dinheiro e
    controle do motor não passam por modelo — o modelo ALUCINA "motor ligado"
    sem ligar nada; aqui é código, então o que ela diz é o que aconteceu).
    Retorna:
      'ACATAR' | 'DISPENSAR' | 'CANCELAR' | 'STATUS' | 'AJUDA' | 'SIM' | 'NAO'
      | 'LIGAR_MOTOR' | 'DESLIGAR_MOTOR' | 'VER_GRAFICO'
      | ('APRENDER', conteudo) | None (conversa livre -> vai para a IA).
    """
    t = (texto or "").strip().lower()
    if not t:
        return None
    # APAGAR vem ANTES de gravar. "REMOVA ISSO, APRENDA QUE ..." tem as duas
    # palavras na mesma frase, e quem escreve isso está CORRIGINDO o que foi
    # gravado — não pedindo para gravar de novo. Foi o caso de 12/08 14:16.
    esquecer, alvo = pedido_de_esquecer(texto)
    if esquecer:
        return ("ESQUECER", alvo)
    licao = extrair_licao(texto)
    if licao is not None:
        return ("APRENDER", licao)
    palavras = set(re.findall(r"[a-zà-ú]+", t))
    curto = len(palavras) <= 6

    # ORDEM IMPORTA: ações específicas ANTES dos genéricos sim/não — senão
    # "pode acatar essa" vira SIM (por causa do "pode") em vez de ACATAR.
    # E nada de gírias ambíguas no ACATAR: "topo" dispararia numa conversa
    # sobre "topo duplo" do gráfico.
    if re.search(r"\b(dispens\w*|não opero|nao opero|não vou operar|nao vou operar|"
                 r"passo essa|fico de fora)\b", t):
        return "DISPENSAR"
    if re.search(r"\bcancel\w*\b.*\b(ordem|pendente|entrada)\b", t) or \
            re.search(r"\b(ordem|pendente)\b.*\bcancel\w*\b", t) or t == "cancelar":
        return "CANCELAR"
    if re.search(r"\b(acat\w*|aceito|bora|entra(r)? nessa)\b", t) \
            and not re.search(r"\b(não|nao|nunca|sem)\b", t):
        return "ACATAR"
    # MOTOR: verbo GRUDADO no substantivo, não pode estar negado ("não desliga
    # o motor") nem ser oração subordinada ("ANTES DE ligar o motor, ajuste o
    # plano" — ali a ordem é ajustar o plano, e ligar é só a marcação de tempo).
    #
    # `finditer` e não `search`: basta UMA ocorrência legítima para ser comando.
    # Com `search`, "antes de ligar o motor, liga o motor" morreria na primeira.
    def _motor(padrao):
        for m in re.finditer(padrao, t):
            antes = t[:m.start()]
            if re.search(_MOTOR_NEGADO, antes):
                continue
            if re.search(_MOTOR_SUBORDINADO, antes):
                continue
            return True
        return False
    if _motor(_MOTOR_DESLIGAR) or _motor(_MOTOR_PARA):
        return "DESLIGAR_MOTOR"
    if _motor(_MOTOR_LIGAR):
        return "LIGAR_MOTOR"
    # CALAR: "para de falar", "silêncio", "chega". Vem ANTES do bloco do motor
    # porque "para de falar" tem o verbo 'para' e não pode desligar o robô.
    if re.search(r"\b(par(a|e|ar) de falar|cala(-se| a boca)?|silencio|"
                 r"sil[êe]ncio|quieta|chega|shh+|pode parar de falar|"
                 r"n[ãa]o precisa falar)\b", t):
        return "CALAR"
    # VELOCIDADE DA FALA: "acelere a fala" é comando da ferramenta, não assunto
    # de mercado — antes caía no despejo de manchetes.
    if re.search(r"\b(fala|voz|leitura|narra[çc][ãa]o)\b", t) and \
            re.search(r"\b(aceler(a|ar|e)|r[áa]pid[ao]|devagar|lent[ao]|"
                      r"diminu(a|ir|i)|desacelera|aument(a|ar|e)|velocidade)\b", t):
        return "VOZ_RAPIDA" if re.search(
            r"\b(aceler\w*|r[áa]pid\w*|aument\w*|mais r[áa]pido)\b", t) \
            else "VOZ_LENTA"
    # CONFIGURAR A PRÓPRIA FERRAMENTA — ele autorizou, e é código que faz.
    # Vem ANTES da busca na web: "o dia da conta 1 começa às 19h" é ordem de
    # configuração, não pergunta de mercado (era aí que ela se perdia).
    mudancas = interpretar_configuracao(texto)
    if mudancas:
        return ("CONFIGURAR", mudancas)
    # "por que você não está sugerindo nada?" — quando o FREIO age, ele precisa
    # ouvir o motivo. Sem isto ela cairia no genérico e ele acharia que a
    # ferramenta travou, quando na verdade ela está protegendo a conta.
    # A marca de AUSÊNCIA é obrigatória. Sem ela, "por que sugeriu compra se
    # estamos em premium?" — que é pergunta sobre o RACIOCÍNIO de um cenário
    # que saiu — cairia aqui em vez de ir para a IA.
    if re.search(r"\b(por que|porqu[êe]|pq|cad[êe]|o que houve|houve)\b", t) and \
            re.search(r"\b(sugest\w*|sugeri\w*|sinal|sinais|cen[áa]rio\w*)\b", t) and \
            re.search(r"\b(n[ãa]o|nenhum\w*|nada|parou|sumi\w*|cad[êe]|calad\w*|"
                      r"silenci\w*|pausad\w*|travad\w*)\b", t):
        return "POR_QUE_SEM_SUGESTAO"
    if re.search(r"\b(freio|trava|pausa|cooldown|limite do dia|teto de opera)\b", t) and \
            re.search(r"\b(est[áa]|ativ|ligad|como|qual|situa)\b", t):
        return "POR_QUE_SEM_SUGESTAO"
    # VIRAR O DIA NO PLANO DE TRADING.
    # 20:09 de 12/08, palavras dele: "o claude precisa incluir opcao de virar
    # o dia, porque eu falei para voce que o dia comeca as 19hs e o sistema
    # ainda nao virou o meu ciclo diario no painel de trading". Ele pediu
    # duas vezes e ainda gravou como licao — e as duas vezes a resposta foi o
    # despejo generico. Agora e comando, e roda sem API.
    # ACENTO IMPORTA AQUI: neste ponto `t` está em minúsculas mas NÃO teve os
    # acentos removidos, então 'diagnóstico' precisa estar escrito com o 'ó'
    # na expressão. Foi o teste que pegou — a versão sem acento passava e a
    # com acento (a que ele digita) caía no genérico.
    if re.search(r"\b(test|diagn[óo]stic|confer|verific|checa)\w*\b[^.!?]{0,20}?"
                 r"\b(microfone|mic|audio|[áa]udio|voz|escuta)\b"
                 r"|\b(microfone|mic)\b[^.!?]{0,20}?"
                 r"\b(nao|n[ãa]o)\s+(funciona|pega|escuta|capta)\b", t):
        return "DIAG_MICROFONE"
    if _RE_VIRAR_DIA.search(t):
        return "VIRAR_DIA"
    # "o dia ja virou?", "em que pregao estamos?" — pergunta de FATO, que o
    # app responde do relogio e da configuracao, sem modelo nenhum.
    if _RE_QUAL_PREGAO.search(t):
        return "QUAL_PREGAO"
    if pergunta_sobre_configuracao(texto):
        return "VER_CONFIG"
    # NOTÍCIA E COTAÇÃO: buscadas na web pela PRÓPRIA ferramenta, sem chave de
    # API. É o que impede ela de responder "o S&P sobe por causa da inflação"
    # de cabeça, sem ter visto manchete nenhuma.
    if re.search(r"\b(not[íi]cias?|manchetes?|aconteceu|acontecendo|movend[oa]|"
                 r"movimentou|agenda|calend[áa]rio|fato relevante|por que|porqu[êe]|"
                 r"pq)\b", t) and \
            re.search(r"\b(mercado|s&p|sp500|nasdaq|d[óo]lar|ouro|bitcoin|hoje|"
                      r"agora|economia|fed|juros|infla[çc][ãa]o|not[íi]cias?)\b", t):
        return "NOTICIAS"
    if re.search(r"\b(cota[çc][ãa]o|pre[çc]o|quanto (est[áa]|vale|custa)|"
                 r"em quanto|quanto t[áa])\b", t) and simbolo_do_texto(t):
        return "COTACAO"
    if re.search(r"\b(pesquis(a|ar|e)|busc(a|ar|e)|procur(a|ar|e)|"
                 r"d[áa] uma olhada na (internet|web)|na internet|no google)\b", t):
        return "PESQUISAR"
    # O QUE ELA SABE SEM GASTAR COTA: os assuntos da base nativa.
    if re.search(r"\b(sabe|conhece|domina|treinada|treinado|treinamento|"
                 r"conhecimento|base)\b", t) and \
            re.search(r"\b(o que|quais|sobre o que|assuntos|t[óo]picos|"
                      r"me diga|mostra)\b", t):
        return "LISTAR_CONHECIMENTO"
    # VER O QUE ELA APRENDEU: sem isso o trader não tem como CONFERIR se a
    # lição entrou mesmo — e era exatamente essa a desconfiança dele.
    if re.search(r"\b(li[çc][õo]es|aprendeu|aprendido|aprendizado|mem[óo]ria|"
                 r"regras)\b", t) and \
            re.search(r"\b(o que|quais|mostr(a|ar|e)|list(a|ar|e)|lembr(a|ar|e)|"
                      r"me diga|tem|guardou|sabe)\b", t):
        return "LISTAR_LICOES"
    # ZERAR O CICLO: é o botão "Reiniciar Ciclo" do Plano de Trading. Ela
    # dizia "acabei de zerar" sem zerar nada — agora é o código que zera, e
    # com confirmação, porque limpa o dashboard da conta.
    if re.search(r"\b(zer(a|ar|e)|reinici(a|ar|e)|recome[çc](a|ar|e)|limp(a|ar|e)|"
                 r"resetar?|reset)\b", t) and \
            re.search(r"\b(ciclo|dashboard|painel|plano|conta|meta|contagem|"
                      r"n[úu]meros|resultados?|tudo|hist[óo]rico)\b", t):
        return "ZERAR_CICLO"
    if re.search(r"\b(whats?app?|whats|zap|wpp)\b", t):
        # CONECTAR: quem tem a ponte com o WhatsApp é o motor. Ela dizia "não
        # tenho acesso para conectar o seu WhatsApp" — tem: é ligar o motor e
        # ler o QR code.
        if re.search(r"\b(conect(a|ar|e)|vincul(a|ar|e)|par(eia|ear|eie)|"
                     r"lig(a|ar|ue)|ativ(a|ar|e)|sincroniz(a|ar|e))\b", t):
            return "CONECTAR_WHATSAPP"
        # MANDAR: ela dizia "acabei de enviar" sem enviar — agora ou envia de
        # verdade, ou explica por que não deu.
        if re.search(r"\b(envi(a|ar|e)|mand(a|ar|e)|manda[- ]?me|dispar(a|ar|e)|"
                     r"encaminh(a|ar|e)|repass(a|ar|e)|reenvi(a|ar|e))\b", t):
            return "ENVIAR_WHATSAPP"
    # "envie novamente" logo depois de um envio: aqui o único disparo que
    # existe é o do WhatsApp, então não há a que outra coisa se referir.
    if re.search(r"\b(reenvi(a|ar|e)|envi(a|ar|e)|mand(a|ar|e)|dispar(a|ar|e))\b"
                 r"\s*(isso|isto|o cen[áa]rio|a sugest[ãa]o)?\s*"
                 r"\b(de novo|novamente|outra vez|mais uma vez)\b", t):
        return "ENVIAR_WHATSAPP"
    # PRINT AGORA: capturar a tela NA HORA, sem esperar o ciclo do motor.
    if re.search(r"\b(tir(a|ar|e)|captur(a|ar|e)|faz|fazer|fa[çc](a|o)|bat(e|er)|"
                 r"pega|pegar)\b.{0,20}\b(print|screenshot|captura|foto|tela)\b", t) or \
            re.search(r"\bprint\s*window\b", t) or \
            re.search(_PRINT_SOZINHO, t) or re.search(_PRINT_COM_AGORA, t):
        return "PRINT_AGORA"
    # "ME MOSTRE O PRINT" — ele quer VER a imagem, não uma análise dela. Caía
    # no despejo genérico ("não está na minha base, a API está fora"), com o
    # arquivo PNG salvo no disco ali do lado. Abrir um arquivo local não
    # depende de cota, de internet nem de modelo nenhum.
    if re.search(r"\b(mostr(a|ar|e)|me mostra|exib(e|ir)|abr(e|ir)|v[êe]r?|"
                 r"cad[êe]|onde (est[áa]|ficou|salvou))\b", t) and \
            re.search(r"\b(print|captura|screenshot|imagem|foto)\b", t) and \
            not re.search(r"\b(analis\w+|l[êe]|ler|leitura|interpret\w+)\b", t):
        return "MOSTRAR_PRINT"
    # PERGUNTA DE NÍVEL = OLHAR O GRÁFICO. Esta é a correção do pregão de
    # 10/08, e o log mostra o defeito com todas as letras:
    #   14:26 ❯ ONDE POSICIONO MEU STOP DA OPERAÇÃO EM ANDAMENTO?
    #   14:26 ✳ "...o motor não tem leitura fresca. Diga 'tira um print'."
    #   14:26 ❯ TIRA UM PRINT
    #   14:26 ✳ "seu stop técnico ideal fica entre 7791.00 e 7792.50."   ← perfeito
    #   14:27 ❯ ONDE EU DEVERIA POSICIONAR MEU ALVO?
    #   14:27 ✳ "...diga 'tira um print'."                               ← de novo
    #
    # Ou seja: ela SABIA fazer, e mesmo assim devolvia a tarefa para ele
    # digitar o comando. Ele chegou a ENSINAR ("TIRA UM PRINT, USA O MOTOR
    # PARA DETERMINAR ISSO") e ela passou a CITAR a lição sem cumpri-la.
    # Perguntar onde vai o stop JÁ É pedir para olhar o gráfico: não existe
    # responder isso sem ver o preço. Então a pergunta captura e lê, sozinha.
    # O TRADER INFORMANDO O BRACKET de uma posição que ele abriu na mão.
    # Vem ANTES da pergunta de nível porque as duas falam de "stop" e "alvo" —
    # a diferença é que aqui ELE traz o número, e ali ele PEDE o número.
    # Pergunta nunca é definição: se a frase começa perguntando, não grava nada.
    if not re.search(r"^\s*(onde|qual|quais|quanto|quando|como|sera|será|"
                     r"me diga|me diz|voce|você)\b", t) and \
            not t.rstrip().endswith("?") and \
            interpretar_niveis_da_posicao(texto) is not None:
        return ("DEFINIR_NIVEIS", texto)
    # POST-MORTEM: respondido do DIÁRIO, sem cota nenhuma. Vem antes da
    # pergunta de nível porque "o que deu errado no stop" cita 'stop' e cairia
    # em VER_GRAFICO, gastando cota para responder algo que já está no disco.
    if pergunta_postmortem(t):
        return "POSTMORTEM"
    if pergunta_pede_nivel(t):
        return "VER_GRAFICO"
    # "COMPRO OU VENDO?" — pergunta de LADO. Igual à pergunta de nível: não dá
    # para responder sem olhar o gráfico, então ela olha.
    if pergunta_qual_lado(t):
        return "VER_GRAFICO"
    # OLHAR O GRÁFICO: ela busca o último print capturado pelo motor e analisa
    # a imagem de verdade, em vez de responder de memória sobre o texto velho.
    if re.search(r"\b(gr[áa]fico|print|tela|captura|imagem|screenshot)\b", t) and \
            re.search(r"\b(olh(a|ar|e)|v[êe]|ver|vendo|visualiz\w*|analis\w*|"
                      r"confer(e|ir|indo)|l[êe]|ler|mostra|checa|checar|"
                      r"o que|como est[áa]|qual)\b", t):
        return "VER_GRAFICO"
    # A META DO DIA É CONTA, NÃO É CONVERSA.
    # 13/08, 16:01 e 16:05. Ele perguntou duas vezes "o dia encerra às 17:59,
    # como estamos de probabilidade de bater a meta de hoje até lá?" e recebeu
    # as duas vezes: "não tenho dados suficientes para prever com precisão".
    # A ferramenta tinha TODOS os dados — a meta está no plano, o resultado do
    # dia está no diário, o horário de fechamento está na configuração. Quem
    # não tinha os dados era o modelo, porque a pergunta nunca chegou até o
    # código que sabe respondê-la.
    #
    # Ele tentou consertar ensinando: "olha no plano de trading e o motor para
    # responder essa pergunta - aprenda isso". Isso nunca poderia funcionar, e
    # é importante dizer por quê: lição vira TEXTO no prompt, não vira acesso
    # ao diário. Nenhuma frase gravada faz um modelo ler um arquivo.
    #
    # Agora é intenção própria, respondida por aritmética, antes de qualquer
    # modelo — e por isso instantânea.
    _sem_ac = _sem_acento(t)
    if re.search(r"\bmeta\b|\bobjetivo do dia\b", _sem_ac) and \
            re.search(r"\bbater\b|\bbatermos\b|\balcancar\b|\batingir\b|"
                      r"\bchance\b|\bprobabilidade\b|\bconsigo\b|\bda tempo\b|"
                      r"\bvou conseguir\b|\bcomo estamos\b|\bfalta\b|"
                      r"\bda para\b|\bdah para\b", _sem_ac):
        return "META"

    # STATUS é o CARD determinístico. Só para pedido literal e curto: perguntas
    # conversacionais ("como está a situação?", "como estamos?") merecem a
    # resposta pensada da IA, que recebe estes mesmos números no contexto.
    if curto and palavras & {"status", "placar", "resumo"}:
        return "STATUS"
    if curto and palavras & {"ajuda", "comandos", "help"}:
        return "AJUDA"
    if curto and palavras & {"sim", "confirmo", "confirmar", "pode", "manda"} \
            and not palavras & {"não", "nao"}:
        return "SIM"
    if curto and palavras & {"não", "nao", "negativo", "deixa", "espera"}:
        return "NAO"
    return None

def processar_turno_chat(texto, confirmacao_pendente=None):
    """Máquina de turno do chat (pura, testável).
    Devolve (tipo, dado):
      ('EXECUTAR', acao)        -> ação local imediata (STATUS/DISPENSAR/...)
      ('PEDIR_CONFIRMACAO', a)  -> ação com dinheiro pede 'sim' antes
      ('CONF_CANCELADA', None)  -> usuário desistiu da confirmação
      ('APRENDER', conteudo)    -> gravar lição
      ('IA', None)              -> conversa livre com o modelo
    Regra de responsabilidade: ACATAR (que pode enviar ordem real) SEMPRE passa
    por confirmação explícita. A IA nunca dispara ação — só estes comandos
    determinísticos disparam.
    """
    intencao = interpretar_intencao(texto)
    # NADA RECONHECIDO? Pode ser só um erro de digitação. "satatus" e "tria um
    # print" caíam no despejo de "não tenho como responder", que é a mesma
    # resposta de quando ela realmente não sabe — e é isso que faz a ferramenta
    # parecer burra. Só tenta a correção quando a frase original não virou
    # comando nenhum: assim nenhuma intenção legítima é reescrita.
    if intencao is None:
        corrigido, mudou = corrigir_digitacao(texto)
        if mudou:
            intencao = interpretar_intencao(corrigido)
    if confirmacao_pendente:
        if intencao == "SIM":
            return ("EXECUTAR", confirmacao_pendente)
        # REPETIR O MESMO COMANDO É CONFIRMAR.
        #
        # No log de 11/08, 19:21:
        #     ❯ ACATAR
        #     ✳ "Confirmando: ACATAR o BUY MESU6 ... Responda 'sim'"
        # e o trader relatou que "nada aconteceu". Do lado do código estava
        # tudo certo — ela perguntou e ficou esperando. Do lado dele, ele deu
        # a ordem e o programa devolveu uma pergunta.
        #
        # Digitar ACATAR de novo, com um ACATAR pendente, não é ambíguo: é a
        # mesma ordem, dita duas vezes, pela mesma pessoa. Isso confirma. A
        # trava de responsabilidade continua de pé — nada roda no PRIMEIRO
        # comando, e trocar de assunto continua derrubando a confirmação.
        if intencao == confirmacao_pendente:
            return ("EXECUTAR", confirmacao_pendente)
        if intencao in ("NAO", "DISPENSAR"):
            return ("CONF_CANCELADA", None)
        # qualquer outra coisa derruba a confirmação e segue o fluxo normal
    if isinstance(intencao, tuple) and intencao[0] == "APRENDER":
        return ("APRENDER", intencao[1])
    if isinstance(intencao, tuple) and intencao[0] == "ESQUECER":
        return ("ESQUECER", intencao[1])
    # CONFIGURAR não pede confirmação de propósito: ele deu autonomia explícita
    # para a IA configurar a ferramenta. A trava é outra — ela mostra o valor
    # de ANTES e o de DEPOIS, relidos do disco, para ele conferir e desfazer.
    if isinstance(intencao, tuple) and intencao[0] == "CONFIGURAR":
        return ("CONFIGURAR", intencao[1])
    # DEFINIR_NIVEIS não pede confirmação: ele está me DANDO um dado que eu não
    # tinha, não me mandando operar. A trava é a mesma da configuração — eu
    # releio do disco e mostro o que ficou gravado.
    if isinstance(intencao, tuple) and intencao[0] == "DEFINIR_NIVEIS":
        return ("DEFINIR_NIVEIS", intencao[1])
    if intencao == "ACATAR":
        return ("PEDIR_CONFIRMACAO", "ACATAR")
    # Zerar o ciclo limpa o dashboard da conta: passa por confirmação, igual
    # ao ACATAR. Nada que apaga números do trader roda sem ele dizer "sim".
    if intencao == "ZERAR_CICLO":
        return ("PEDIR_CONFIRMACAO", "ZERAR_CICLO")
    if intencao in ("VER_GRAFICO", "PRINT_AGORA"):
        return (intencao, None)
    if intencao in ("DISPENSAR", "CANCELAR", "STATUS", "META", "AJUDA",
                    "MOSTRAR_PRINT", "POSTMORTEM",
                    "LIGAR_MOTOR", "DESLIGAR_MOTOR", "ENVIAR_WHATSAPP",
                    "CONECTAR_WHATSAPP", "LISTAR_LICOES", "LISTAR_CONHECIMENTO",
                    "NOTICIAS", "COTACAO", "PESQUISAR", "VER_CONFIG",
                    "POR_QUE_SEM_SUGESTAO", "VIRAR_DIA", "QUAL_PREGAO",
                    "DIAG_MICROFONE",
                    "VOZ_RAPIDA", "VOZ_LENTA", "CALAR"):
        return ("EXECUTAR", intencao)
    return ("IA", None)

def montar_persona_ia():
    """Quem é a IA do chat. A bússola é a metodologia Smart Money Concepts
    (leitura institucional) somada aos princípios clássicos de análise técnica
    (tendência, momentum, divergência, suportes/resistências e pontos de
    virada) — as escolas dos livros de referência do trader."""
    return (
        "Você é a TIGER: a IA da mesa SMC Quant Pro, mentora de trading "
        "institucional do Josevan, conversando em tempo real dentro da "
        "ferramenta dele. Seu nome é TIGER e ele te chama por voz com 'Olá Tiger'.\n"
        "\n"
        "FORMATO DAS RESPOSTAS: escreva em TEXTO CORRIDO natural, SEM asteriscos, "
        "sem markdown (nada de **negrito**, listas com * ou #) — suas respostas "
        "também são LIDAS EM VOZ ALTA, e símbolos estragam a fala. Seja objetiva: "
        "responda em poucas frases, direto ao ponto. REGRA DE OURO: TERMINE o "
        "raciocínio dentro da resposta. É melhor uma resposta curta e COMPLETA "
        "do que uma longa cortada no meio — nunca deixe uma conta ou uma frase "
        "pela metade.\n"
        "\n"
        "PERGUNTA DE NÍVEL EXIGE O NÚMERO — NUNCA O PRONOME:\n"
        "Quando ele perguntar ONDE está alguma coisa no gráfico (VWAP, média, "
        "suporte, resistência, order block, FVG, um topo, um fundo), a resposta "
        "TEM DE CONTER O VALOR. É PROIBIDO responder com pronome sem o número: "
        "'o preço está acima dela', 'ela está sendo respeitada', 'o preço testou "
        "essa região' — nada disso responde 'onde está?'. Isso aconteceu de "
        "verdade: ele perguntou onde estava a VWAP três vezes seguidas e recebeu "
        "três vezes 'o preço está acima dela', sem nunca saber onde 'ela' "
        "estava. Se você CONSEGUE ler o número na imagem, diga o número. Se NÃO "
        "consegue ler, diga exatamente isto: 'não consigo ler esse valor nesta "
        "captura' — e diga o que atrapalhou (indicador não está no gráfico, "
        "legenda cortada, resolução baixa). Não saber é uma resposta legítima; "
        "enrolar com pronome não é.\n"
        "\n"
        "E O NÚMERO TEM DE SER LIDO, NÃO PRODUZIDO:\n"
        "Só diga um valor de indicador se você estiver LENDO ele escrito na "
        "imagem — na legenda de dados, no rótulo da linha, na escala. É "
        "PROIBIDO estimar 'onde a linha parece estar', calcular de cabeça, ou "
        "usar o preço do ativo no lugar do valor do indicador. Isso também já "
        "aconteceu: com a legenda mostrando VWAP 7769.56, você respondeu 'a "
        "VWAP está exatamente em 7752.34, conforme indicado na legenda' — a "
        "palavra 'exatamente' e a citação da fonte estavam lá, o número não. "
        "Um número inventado com cara de leitura é PIOR que 'não consigo ler', "
        "porque ele é usado. Na dúvida entre um valor aproximado e a admissão, "
        "a admissão vence sempre.\n"
        "\n"
        "A POSIÇÃO DELE NÃO SE DEDUZ DO GRÁFICO:\n"
        "NUNCA afirme que ele está comprado, vendido ou zerado com base no que "
        "você vê na imagem. Se ele estiver posicionado, isso vem escrito no "
        "bloco DADOS REAIS DA MESA acima — se não estiver escrito lá, ele NÃO "
        "está posicionado, e dizer o contrário é inventar uma operação que não "
        "existe. Você já disse 'você está com uma posição de venda aberta em "
        "7753.25' com a plataforma mostrando POSIÇÃO 0.\n"
        "\n"
        "REGRA NÚMERO UM — ESCREVER NÃO É FAZER:\n"
        "Você é a voz da ferramenta, não a mão dela. Quem executa ação é o "
        "CÓDIGO do app, disparado por comandos que o trader diz. Você NUNCA "
        "zera ciclo, NUNCA envia WhatsApp, NUNCA liga motor e NUNCA grava lição "
        "só por escrever que fez. É PROIBIDO escrever qualquer frase do tipo "
        "'acabei de zerar', 'já enviei no seu WhatsApp', 'lição registrada', "
        "'comando executado', 'estou monitorando em segundo plano'. Se ele "
        "pedir uma dessas coisas e a ação não tiver acontecido nesta conversa, "
        "a resposta certa é ENSINAR O COMANDO: 'diga zera o ciclo', 'diga manda "
        "no whatsapp', 'diga liga o motor', 'termine a frase com aprenda isso'. "
        "Quando o app executa de verdade, é o próprio app que escreve a "
        "confirmação — não você.\n"
        "\n"
        "COMANDOS REAIS DA FERRAMENTA (o app executa; você só orienta e "
        "comenta o resultado):\n"
        "• 'liga o motor' / 'desliga o motor' — liga e desliga a análise.\n"
        "• 'zera o ciclo' — zera o dashboard do Plano de Trading da conta ativa "
        "(pede confirmação; o histórico não é apagado).\n"
        "• 'manda no whatsapp' — o MOTOR dispara o cenário e o status. Só "
        "funciona com o motor ligado e o WhatsApp conectado.\n"
        "• 'tira um print' — captura a tela da corretora na hora.\n"
        "• 'olha o gráfico' — você analisa a última captura do motor.\n"
        "• 'acatar' / 'dispensar' / 'cancelar ordem' — decisão sobre o cenário.\n"
        "• 'status' — o placar da conta.\n"
        "• '<a regra>, aprenda isso' — grava a regra na sua memória permanente.\n"
        "• CONFIGURAR A FERRAMENTA — ele te autorizou a isso. 'o dia da conta 1 "
        "começa às 19h', 'analisa a cada 5 minutos', 'risco de 1% por "
        "operação', 'meta de 6 mil em 10 dias', 'drawdown máximo de 2000'. "
        "Quem grava é o app, que relê o arquivo e mostra o de-para. E 'como "
        "está configurado o risco do plano da conta 1' mostra o que está "
        "gravado agora. NUNCA responda de cabeça sobre a configuração dele: se "
        "o valor não veio no contexto, mande ele perguntar assim que o app "
        "responde com o número real.\n"
        "\n"
        "DE ONDE VEM A SUA RESPOSTA — NESTA ORDEM, SEMPRE:\n"
        "1) BASE PRÓPRIA DE SMC: a ferramenta carrega a metodologia SMC/ICT "
        "dentro dela — a MESMA que o motor usa para ler o gráfico. Conceito e "
        "metodologia saem daqui, na hora, sem gastar cota.\n"
        "2) WEB: se NÃO estiver na base, o dado é buscado na internet pela "
        "própria ferramenta (cotação real do Yahoo Finance e manchetes das "
        "casas de mercado). Quando esses dados vierem no contexto, eles são a "
        "VERDADE: use os números de lá, cite a fonte e a hora.\n"
        "3) SEU RACIOCÍNIO, em cima de 1 e 2 — nunca no lugar deles.\n"
        "Se o assunto não está na base E a busca não trouxe nada, a resposta "
        "certa é: 'não tenho esse dado e não consegui pesquisar agora'. Ele "
        "prefere mil vezes ouvir isso a receber um número inventado.\n"
        "\n"
        "PROIBIDO INVENTAR — a regra que mais importa numa mesa:\n"
        "• NUNCA cite preço, cotação, variação, horário de evento ou número de "
        "qualquer espécie que não esteja no contexto, no arquivo anexado ou nos "
        "dados da web. Se não tem, diga que não tem.\n"
        "• NUNCA explique um movimento do mercado por 'dados de inflação', "
        "'resultados corporativos' ou qualquer motivo que você não leu numa "
        "manchete real desta conversa. Motivo sem fonte é chute, e chute numa "
        "mesa vira prejuízo.\n"
        "• Ao usar notícia, diga a casa e quando saiu ('segundo a CNBC, há 20 "
        "minutos'). Sem fonte, não fale.\n"
        "\n"
        "O QUE VOCÊ FAZ SOZINHA (isto sim é seu):\n"
        "• VER O GRÁFICO: quando a imagem vier anexada, analise-a de verdade. "
        "Descreva só o que está visível; nunca invente preço que não aparece.\n"
        "• RESPONDER O QUE ELE PERGUNTOU: se ele disser que a resposta não foi "
        "sobre o que perguntou, ele está certo. Não repita o texto anterior: "
        "leia de novo a pergunta e responda EXATAMENTE aquilo.\n"
        "• CONTAS: os números da mesa (resultado, meta, quanto falta, ritmo por "
        "dia) vêm calculados no contexto. Use os números de lá, tal como estão. "
        "Se precisar de uma conta nova, faça a aritmética com CUIDADO e mostre "
        "o resultado fechado.\n"
        "\n"
        "SUA BÚSSOLA METODOLÓGICA (nesta ordem de prioridade):\n"
        "1) SMART MONEY CONCEPTS — leia o mercado pelas pegadas das instituições: "
        "estrutura (topos/fundos, BOS, CHoCH, MSS), o preço como fractal, liquidez "
        "interna vs externa, inducement como armadilha, tipos de manipulação, "
        "order blocks e breaker/mitigation, FVG e ineficiências, premium/discount "
        "com OTE, Power of 3 (acumulação → manipulação → distribuição), killzones. "
        "A pergunta-mestra é sempre: onde está a liquidez parada, quem está preso, "
        "e para onde o preço PRECISA ir para as instituições preencherem ordem?\n"
        "2) ANÁLISE TÉCNICA CLÁSSICA (a escola de identificação de tendências e "
        "pontos de virada): a tendência é sua amiga até dar sinais objetivos de "
        "reversão; momentum antecede preço (divergências importam); suportes e "
        "resistências trocam de papel; volume confirma movimento; rompimento sem "
        "confirmação é armadilha. Use-a como CONFLUÊNCIA da leitura SMC.\n"
        "\n"
        "COMO SE COMPORTAR:\n"
        "• LINGUAGEM NATURAL: converse como gente, em português claro, direto e "
        "caloroso — como um mentor experiente do lado da mesa. Explique os termos "
        "técnicos quando usar. Respostas curtas por padrão; aprofunde se pedirem.\n"
        "• RESPONSÁVEL: você orienta, quem decide é o trader. NUNCA invente "
        "números, preços ou resultados — se não estiver nos dados do contexto, "
        "diga que não tem o dado. Nada de promessa de ganho. Se ele estiver "
        "emocionado (raiva/medo/revanche), traga-o de volta ao plano de trading.\n"
        "• ORDEM É DECISÃO DELE: você NÃO executa ordens e não manda nada para "
        "a corretora. O que existe é o 'acatar', que ele diz e o app confirma "
        "antes de registrar. Nunca sugira que você comprou, vendeu ou zerou "
        "uma posição.\n"
        "• NUNCA DIGA QUE FEZ ALGO QUE VOCÊ NÃO FEZ (ver REGRA NÚMERO UM). Você "
        "não fica 'monitorando em segundo plano' por conta própria — quem "
        "monitora é o motor, e só quando está ligado. Se ele pedir algo que "
        "depende do motor e o motor estiver desligado, diga isso e ofereça "
        "ligar. Se ele te der 'permissão' para fazer algo que a ferramenta não "
        "faz, o problema não é permissão: explique o caminho real.\n"
        "• SE ELE RECLAMAR QUE VOCÊ NÃO FEZ: ele tem razão. Não insista, não "
        "diga que 'tentou processar internamente'. Reconheça em uma frase e "
        "aponte o comando exato que resolve.\n"
        "• AUTOAPRENDIZAGEM: use as lições dele e o histórico de padrões (nos "
        "dados do contexto) para calibrar suas opiniões — e diga quando uma "
        "opinião vem do histórico dele ('esse padrão vem acertando nas suas "
        "operações').\n"
    )

# --------------------------------------------------------------------
# O TEMA É ESCURO, E ISSO PRECISA SER DITO AO CustomTkinter
# --------------------------------------------------------------------
# ESTE PROGRAMA PINTA A PRÓPRIA PALETA (o dicionário COR, lá em cima): fundo
# #0a0e14, cartões #12161f, texto claro. Só que 22 dos 101 rótulos da interface
# não declaram cor de texto — eles usam o padrão do tema do CustomTkinter.
#
# E o CustomTkinter começa em modo "System". Num sistema em MODO CLARO — que é
# o padrão do macOS e do Windows recém-instalados — esse padrão vira `gray10`,
# quase preto, desenhado em cima do NOSSO fundo escuro. O resultado é texto
# invisível: "Janela do gráfico a monitorar", "Plataforma:", o rótulo do
# "Restaurar a janela minimizada" e mais uma dúzia de linhas somem da tela.
#
# Isto foi encontrado abrindo o programa de verdade num servidor gráfico
# virtual e OLHANDO a imagem (ver tests/fumaca_gui.py). Nenhum teste de lógica
# pegaria: a janela abre, os widgets existem, nada levanta exceção — e o
# trader simplesmente não consegue ler metade da aba.
#
# Como a paleta é escura por decisão de projeto, o modo é FIXADO em escuro.
# Não é preferência: é coerência com as cores que o próprio app desenha.
ctk.set_appearance_mode("dark")

# --------------------------------------------------------------------
# TAMANHO DA LETRA — acessibilidade de verdade, não zoom do sistema
# --------------------------------------------------------------------
# Pedido direto do trader: "inclua uma opção de aumentar as letras em todos os
# dashboards, principalmente na IA". Quem passa o pregão lendo número pequeno
# em tela grande erra de leitura, e errar de leitura na mesa custa dinheiro.
#
# O CustomTkinter tem UM lever global (`set_widget_scaling`) que escala fonte E
# widget de uma vez, em todas as abas, ao vivo. Os dois campos de texto puro
# (o terminal da TIGER e o log do motor) são `tk.Text` e ficam de fora desse
# lever — por isso são reconfigurados na mão junto.
ESCALAS_LETRA = {
    "Normal": 1.00,
    "Grande": 1.15,
    "Maior": 1.30,
    "Máximo": 1.50,
}
ESCALA_LETRA_PADRAO = 1.00
# Tamanho base de cada campo de texto puro, em pontos. Multiplicado pela escala.
_FONTE_BASE_CHAT = 11
_FONTE_BASE_CONSOLE = 10

def escala_letra_salva():
    """A escala gravada, presa à faixa que a interface oferece. Valor estranho
    no config (editado à mão, arquivo corrompido) volta ao padrão em vez de
    deixar a janela inutilizável."""
    try:
        v = float(carregar_config().get("escala_letra", ESCALA_LETRA_PADRAO))
    except (TypeError, ValueError):
        return ESCALA_LETRA_PADRAO
    return min(max(v, 1.0), 2.0)

def nome_da_escala(valor):
    """O rótulo que corresponde a uma escala — o mais próximo, nunca um chute."""
    return min(ESCALAS_LETRA.items(), key=lambda kv: abs(kv[1] - valor))[0]


class SmcQuantApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SMC Quant Pro - Trader Institucional AI")
        # A escala é aplicada ANTES de montar as abas: assim os widgets já
        # nascem no tamanho certo, sem precisar redesenhar a tela inteira.
        self._escala_letra = escala_letra_salva()
        try:
            ctk.set_widget_scaling(self._escala_letra)
        except Exception:
            self._escala_letra = 1.0
        # A janela cresce junto: com letra maior, a mesma largura em pixels
        # cabe menos coisa, e botão cortado é pior que letra pequena.
        _larg = int(680 * self._escala_letra)
        _alt = min(int(900 * self._escala_letra), 1000)
        self.geometry(f"{_larg}x{_alt}")
        self.minsize(_larg, min(int(800 * self._escala_letra), 900))
        self.protocol("WM_DELETE_WINDOW", self.ao_fechar)

        self.processo_motor = None
        self.motor_rodando = False
        # motor_rodando = "o Popen voltou". motor_confirmado = "a porta 3939
        # respondeu". A diferença entre as duas é a diferença entre dizer que o
        # motor subiu e o motor ter subido — só a segunda vale como resposta.
        self.motor_confirmado = False
        self.motor_morreu_ao_subir = False
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

        # Poller do PREÇO AO VIVO da corretora: é ele que aciona entrada, stop e
        # alvo em tempo quase real (a análise da IA é lenta demais para isso).
        self._preco_ao_vivo = None
        threading.Thread(target=self._poller_preco_plataforma, daemon=True).start()

        config_atual = carregar_config()
        # Plano da CONTA SELECIONADA (migra automaticamente a estrutura antiga).
        self.plano = plano_da_conta_ativa()

        self.tabview = ctk.CTkTabview(self, width=660, height=720)
        self.tabview.pack(padx=10, pady=10, fill="both", expand=True)
        # QUATRO ABAS, DIVIDIDAS POR *QUANDO* SE MEXE NELAS.
        # Pedido dele, 14/08: "o que for possível e considerado configuração,
        # organize em uma opção chamada Configurações, tem muita coisa que
        # está solta e aleatória, isso não é legal". Estava certo: a aba
        # Motor tinha NOVE seções, e a chave da API (que se põe uma vez na
        # vida) dividia espaço com o Registro de atividade (que se olha a
        # cada cinco minutos, no meio do pregão).
        #
        # O corte é esse, e é o único que se sustenta: MOTOR é o que se opera
        # com o mercado aberto; CONFIGURAÇÕES é o que se ajusta uma vez e se
        # esquece. Nada foi removido nem renomeado — cada seção continua
        # sendo a mesma, e lembrando se está aberta ou fechada.
        self.tabview.add("⚙️ Motor & WhatsApp")
        self.tabview.add("📊 Plano de Trading")
        self.tabview.add("🐯 TIGER")
        self.tabview.add("🎛️ Configurações")
        tab_motor = self.tabview.tab("⚙️ Motor & WhatsApp")
        tab_plano = self.tabview.tab("📊 Plano de Trading")
        tab_ia = self.tabview.tab("🐯 TIGER")
        tab_cfg = self.tabview.tab("🎛️ Configurações")

        self._montar_tab_motor(tab_motor, config_atual, tab_cfg)
        self._montar_tab_plano(tab_plano)
        self._montar_tab_ia(tab_ia)

        # DIAGNÓSTICO DE PLATAFORMA no arranque. No Mac isto responde de cara
        # as duas perguntas que quebram a instalação: a permissão de Gravação
        # de Tela está concedida? o Node foi encontrado apesar do PATH pobre
        # do Finder? Sem isso, o sintoma aparece só na hora do pregão.
        try:
            for linha in plataforma.diagnostico().split("\n"):
                self.log(f"🖥️ {linha}")
            if plataforma.E_MACOS and not plataforma.permissao_de_tela_ok():
                self.log(
                    "⚠️ macOS: NÃO estou conseguindo ler o TÍTULO das janelas — "
                    "elas vão aparecer só com o nome do aplicativo, e a captura "
                    "pode sair preta.\n"
                    "   Existem DUAS permissões, e basta uma delas funcionar:\n"
                    "   1) Ajustes do Sistema → Privacidade e Segurança → "
                    "GRAVAÇÃO DE TELA\n"
                    "   2) Ajustes do Sistema → Privacidade e Segurança → "
                    "ACESSIBILIDADE\n"
                    "   Ligue o SMC Quant Pro (ou o Terminal, se abriu por ele) "
                    "nas DUAS e REABRA o programa.\n"
                    "   Depois clique em '🩺 Diagnosticar janelas' para conferir "
                    "qual das duas passou a responder.")
        except Exception as e:
            self.log(f"⚠️ Não consegui montar o diagnóstico do sistema: {e}")

        # FAXINA DAS LIÇÕES GRAVADAS ANTES DAS TRAVAS EXISTIREM.
        # A lista dele tinha uma pergunta gravada como regra ("o que aconteceu
        # com HAPV3 HOJE?"), e ela entrava em toda análise e toda conversa,
        # porque as lições vão inteiras para dentro do prompt.
        self._faxina_de_licoes()

        self.verificar_node()
        self.after(3000, self._loop_atualizar_dashboard)

    # ------------------------------------------------------------------
    # ABA 1: MOTOR / WHATSAPP / SETUP
    # ------------------------------------------------------------------
    def _montar_tab_motor(self, master, config_atual, master_cfg=None):
        """Monta a aba MOTOR e, em `master_cfg`, a aba CONFIGURAÇÕES.

        As duas nascem aqui de propósito. Os widgets conversam entre si (o
        campo da chave da API alimenta o botão que testa o provedor, que
        escreve no Registro), e separá-los em dois métodos obrigaria a passar
        uma dúzia de referências de um lado para o outro — que é como se
        criam dois lugares para a mesma verdade.

        O CORTE: em `master` fica o que se OPERA com o mercado aberto — o
        status, o botão LIGAR MOTOR, as janelas do gráfico, o WhatsApp e o
        Registro de atividade. Em `master_cfg` fica o que se AJUSTA uma vez e
        se esquece — chave da API, IA local, pregão e intervalo, alertas, voz,
        tamanho da letra, automação e modo desenvolvedor.

        Cada bloco continua abrindo e fechando com um clique no título, e o
        app continua lembrando como você deixou.

        O que NÃO entra em seção nenhuma: o status e o botão LIGAR MOTOR. São
        a ação principal e ficam sempre à vista, no topo."""
        scroll_motor = ctk.CTkScrollableFrame(master)
        scroll_motor.pack(fill="both", expand=True)
        master = scroll_motor  # todos os widgets vão para o frame rolável

        # A aba de configurações. Quando não vier (algum caminho antigo que
        # chame com dois argumentos), tudo volta a morar numa aba só — feio,
        # mas funcionando, que é melhor que estourar na abertura do programa.
        if master_cfg is not None:
            scroll_cfg = ctk.CTkScrollableFrame(master_cfg)
            scroll_cfg.pack(fill="both", expand=True)
            cfg = scroll_cfg
            ctk.CTkLabel(
                cfg, justify="left", wraplength=600, text_color=COR["dim"],
                font=ctk.CTkFont(size=11),
                text=("Tudo o que se ajusta UMA vez e se esquece mora aqui. "
                      "O que se opera com o mercado aberto — ligar o motor, "
                      "escolher a janela do gráfico, ler o Registro — ficou na "
                      "aba ⚙️ Motor & WhatsApp.\nCada bloco abre e fecha "
                      "clicando no título, e eu lembro como você deixou.")
            ).pack(anchor="w", padx=12, pady=(10, 6))
        else:
            cfg = master

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
        # A IA LOCAL SOBE SOZINHA — ele diagnosticou isso melhor que eu.
        # Do log de 13/08: das 09:46 às 10:02 ela respondeu "a API está fora"
        # a TUDO, porque o Ollama estava instalado e PARADO. Ele percebeu
        # sozinho ("meio que o ollama não estava ativa") e teve de clicar em
        # 'Instalar a IA LOCAL' de novo só para subir um serviço.
        # Exigir um clique todo dia para religar algo que já está instalado
        # não é configuração, é tarefa — e tarefa que ninguém lembra de fazer
        # é recurso que não existe. Só sobe o que JÁ está instalado; nada é
        # baixado sem ele mandar.
        threading.Thread(target=self._subir_ia_local_no_inicio,
                         daemon=True).start()

        sec_inst = self._secao(cfg, "⚙️  INSTALAÇÃO E CHAVE DA API",
                               "motor_instalacao", aberta_padrao=True)
        self.btn_instalar = ctk.CTkButton(sec_inst, text="1. Baixar Node.js (Obrigatório)", fg_color="blue", command=self.abrir_download)
        self.btn_instalar.pack(pady=4)

        self.btn_verificar = ctk.CTkButton(sec_inst, text="2. Verificar Instalação", fg_color="gray", command=self.verificar_node)
        self.btn_verificar.pack(pady=4)

        self.api_entry = ctk.CTkEntry(sec_inst, placeholder_text="Cole sua Chave da API Gemini", width=420, show="*")
        # O campo mostra asteriscos: uma chave colada em DOBRO passaria
        # despercebida e so apareceria como 401 na hora do pregao.
        ligar_colar_sem_duplicar(self.api_entry)
        self.api_entry.pack(pady=8)

        api_key_salva = carregar_api_key()
        if api_key_salva:
            self.api_entry.insert(0, api_key_salva)

        # ---------- SEGUNDA INTELIGÊNCIA (chaves alternativas) ----------
        sec_alt = self._secao(
            master, "🧠  SEGUNDA INTELIGÊNCIA — quando a Gemini fica sem cota",
            "motor_provedores", aberta_padrao=False)
        ctk.CTkLabel(
            sec_alt, justify="left", text_color=COR["texto"],
            font=ctk.CTkFont(size=11), wraplength=580,
            text="A cota gratuita da Gemini estoura todo dia com o motor "
                 "analisando de 5 em 5 minutos. Quando isso acontecia, a TIGER "
                 "ficava SEM CÉREBRO — qualquer pergunta virava “não tenho como "
                 "responder isso com segurança agora”.\n\n"
                 "Cole aqui a chave de QUALQUER um destes. Basta um. Quando a "
                 "Gemini cair, a mesma pergunta vai para o próximo da fila e "
                 "você recebe uma resposta de verdade."
        ).pack(anchor="w", padx=12, pady=(8, 6))
        # ---------- A IA QUE NÃO PEDE CHAVE ----------
        # Vem ANTES dos campos de chave de propósito: é a única opção que não
        # depende de conta em lugar nenhum nem de saldo para acabar — e foi
        # saldo que derrubou a segunda inteligência no dia 12/08.
        quadro_local = ctk.CTkFrame(sec_alt, fg_color=COR["card"])
        quadro_local.pack(fill="x", padx=12, pady=(4, 10))
        ctk.CTkLabel(quadro_local, text="🖥  IA LOCAL — roda na SUA máquina",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COR["texto"]).pack(anchor="w", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            quadro_local, justify="left", text_color=COR["dim"],
            font=ctk.CTkFont(size=10), wraplength=560,
            text="Sem chave, sem conta, sem cota e sem saldo para acabar. Um "
                 "clique aqui e EU faço tudo: baixo o instalador certo para "
                 "este sistema, instalo, subo o serviço, trago o modelo que "
                 "cabe nesta máquina e TESTO com uma pergunta real.\n"
                 "Precisa de internet só NESTA vez, e de alguns GB de disco. "
                 "Depois disso ela funciona offline, para sempre."
        ).pack(anchor="w", padx=10, pady=(2, 6))
        linha_local = ctk.CTkFrame(quadro_local, fg_color="transparent")
        linha_local.pack(anchor="w", padx=10, pady=(0, 10))
        self.btn_instalar_ia = ctk.CTkButton(
            linha_local, text="⬇️ Instalar a IA LOCAL (sem chave)", width=280,
            fg_color=COR["verde_esc"], hover_color=COR["verde"],
            command=self._instalar_ia_local)
        self.btn_instalar_ia.pack(side="left")
        ctk.CTkButton(linha_local, text="🔎 Verificar", width=110,
                      fg_color=COR["borda"], hover_color=COR["input"],
                      command=self._verificar_ia_local).pack(side="left", padx=6)

        self._campos_provedor = {}
        for pid in ORDEM_PROVEDORES:
            if PROVEDORES_IA[pid].get("sem_chave"):
                continue          # a IA local não tem campo de chave a preencher
            info = PROVEDORES_IA[pid]
            linha = ctk.CTkFrame(sec_alt, fg_color="transparent")
            linha.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(linha, text=info["rotulo"], width=250, anchor="w",
                         text_color=COR["texto"],
                         font=ctk.CTkFont(size=11)).pack(side="left")
            campo = ctk.CTkEntry(linha, width=260, show="*",
                                 placeholder_text="cole a chave (opcional)",
                                 fg_color=COR["input"], border_color=COR["borda"])
            # Mesma proteção do campo da Gemini: no macOS o Cmd+V colava duas
            # vezes e a chave dobrada era recusada com 401 — sem aparecer nada,
            # porque o campo mostra asteriscos.
            ligar_colar_sem_duplicar(campo)
            campo.pack(side="left", padx=6)
            salva = carregar_chave_provedor(pid)
            if salva:
                campo.insert(0, salva)
            ctk.CTkButton(linha, text="🔑 obter", width=70,
                          fg_color=COR["borda"], hover_color=COR["input"],
                          command=lambda u=info["onde_pegar"]: webbrowser.open(u)
                          ).pack(side="left", padx=2)
            self._campos_provedor[pid] = campo
        ctk.CTkButton(sec_alt, text="💾 Salvar chaves e testar agora", width=280,
                      fg_color=COR["verde_esc"], hover_color=COR["verde"],
                      command=self._salvar_e_testar_provedores
                      ).pack(anchor="w", padx=12, pady=(8, 4))
        ctk.CTkLabel(
            sec_alt, justify="left", text_color=COR["dim"],
            font=ctk.CTkFont(size=10), wraplength=580,
            text="As chaves ficam no cofre do sistema (Chaveiro no Mac, DPAPI no "
                 "Windows), igual à da Gemini — copiar o arquivo de configuração "
                 "para outra máquina NÃO leva a chave junto. Nada disso toca em "
                 "dinheiro: dimensionamento, piso de qualidade, freio e execução "
                 "continuam sendo cálculo do programa, não do modelo. E a regra "
                 "vale para todos os provedores: sem dado, ela diz que não sabe — "
                 "ter cinco cérebros não autoriza chutar um número."
        ).pack(anchor="w", padx=12, pady=(0, 10))

        sec_jan = self._secao(master, "🪟  JANELAS DO GRÁFICO E PLATAFORMA",
                              "motor_janelas", aberta_padrao=True)
        ctk.CTkLabel(sec_jan, text="Janela do gráfico a monitorar (qualquer plataforma):"
                     ).pack(pady=(6, 0))
        nome_janela_salvo = config_atual.get("nome_janela_corretora", "")
        self.janela_var = tk.StringVar(value=nome_janela_salvo or "(clique em Atualizar lista)")
        self.janela_dropdown = ctk.CTkOptionMenu(sec_jan, variable=self.janela_var,
                                                 values=[self.janela_var.get()], width=420,
                                                 command=self._ao_trocar_janela)
        self.janela_dropdown.pack(pady=4)
        ctk.CTkButton(sec_jan, text="🔄 Atualizar lista de janelas abertas", fg_color="#555555",
                      command=self._atualizar_lista_janelas).pack(pady=(0, 4))

        # ---------- VER O QUE O MOTOR VÊ ----------
        # Escolher janela por TÍTULO é adivinhação: "Chrome — janela 2" não diz
        # nada, e foi assim que o motor passou 20 minutos analisando a janela
        # do Claude achando que era gráfico. Aqui ele CONFERE antes: captura a
        # janela selecionada e mostra a miniatura. Se o que aparece não é o
        # gráfico, ele descobre em dois segundos, não em vinte minutos.
        quadro_prev = ctk.CTkFrame(sec_jan, fg_color=COR["card"])
        quadro_prev.pack(fill="x", padx=10, pady=(0, 6))
        linha_prev = ctk.CTkFrame(quadro_prev, fg_color="transparent")
        linha_prev.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkButton(linha_prev, text="👁 Ver o que o motor vê", width=200,
                      command=self._previsualizar_janela).pack(side="left")
        self.lbl_previa = ctk.CTkLabel(
            linha_prev, text="", text_color=COR["dim"],
            font=ctk.CTkFont(size=10), justify="left")
        self.lbl_previa.pack(side="left", padx=10)
        self.img_previa = ctk.CTkLabel(quadro_prev, text="")
        self.img_previa.pack(padx=10, pady=(4, 8))

        # ---------- MAIS DE UM ATIVO AO MESMO TEMPO ----------
        # Um motor só percorre todas estas janelas a cada ciclo. Antes era uma
        # janela por vez, e abrir o programa duas vezes esbarrava na porta 3939.
        frame_multi = ctk.CTkFrame(sec_jan, fg_color=COR["card"])
        frame_multi.pack(fill="x", padx=10, pady=(4, 6))
        ctk.CTkLabel(frame_multi, text="🪟  Gráficos analisados a cada ciclo",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COR["texto"]).pack(anchor="w", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            frame_multi, justify="left", text_color=COR["dim"],
            font=ctk.CTkFont(size=10),
            text="Cada janela é um ativo, com cenário e histórico próprios — o motor "
                 "não mistura um com o outro.\nA PRIMEIRA da lista é a principal: é nela "
                 "que o envio de ordem e a leitura de posições trabalham.\n"
                 "Atenção: mais gráficos = mais consumo da cota da API por ciclo."
        ).pack(anchor="w", padx=10, pady=(2, 4))
        self.frame_lista_janelas = ctk.CTkFrame(frame_multi, fg_color="transparent")
        self.frame_lista_janelas.pack(fill="x", padx=6, pady=(0, 4))
        frame_btn_janelas = ctk.CTkFrame(frame_multi, fg_color="transparent")
        frame_btn_janelas.pack(anchor="w", padx=10, pady=(0, 10))
        ctk.CTkButton(frame_btn_janelas, text="➕ Incluir a janela selecionada acima",
                      fg_color=COR["verde"], width=250,
                      command=self._incluir_janela_monitorada).pack(side="left", padx=(0, 6))
        ctk.CTkButton(frame_btn_janelas, text="🔄 Atualizar", fg_color="#555555", width=110,
                      command=self._render_lista_janelas).pack(side="left")
        ctk.CTkButton(frame_btn_janelas,
                      text="🩺 Diagnosticar janelas", width=190,
                      fg_color=COR["borda"], hover_color=COR["input"],
                      command=self._diagnosticar_janelas).pack(side="left", padx=(6, 0))
        self._render_lista_janelas()

        # ---------- PLATAFORMA (detectada automaticamente) ----------
        frame_plat = ctk.CTkFrame(sec_jan, fg_color="transparent")
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
            sec_jan, justify="left", text_color="gray", font=ctk.CTkFont(size=10),
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
            sec_jan,
            text="Restaurar a janela se ela estiver minimizada (não rouba o foco)",
            variable=self.restaurar_minimizada_var,
            command=self._salvar_pref_restaurar
        ).pack(pady=(2, 0))
        ctk.CTkLabel(
            sec_jan,
            text="Se desmarcado e a janela estiver minimizada, o ciclo é pulado com aviso.\n"
                 "Uma janela minimizada não é desenhada pelo Windows — não há como capturá-la.",
            text_color="gray", font=ctk.CTkFont(size=10), justify="left"
        ).pack(pady=(0, 4))
        self._atualizar_lista_janelas(manter_selecao=nome_janela_salvo)

        if not PYWIN32_DISPONIVEL:
            ctk.CTkLabel(sec_jan, text="⚠️ pywin32 não encontrado — foco automático de janela desativado.",
                         text_color="orange").pack(pady=2)

        # ---------- WHATSAPP: quem recebe + QR code ----------
        # Bloco recolhível próprio: depois que o WhatsApp está pareado, isso
        # aqui não se toca mais no dia a dia e só ocupava a tela.
        self.sec_whatsapp = self._secao(
            master, "📱  WHATSAPP — CONTATOS E CONEXÃO (QR CODE)",
            "motor_whatsapp", aberta_padrao=False)
        self._montar_painel_inscritos(self.sec_whatsapp)

        # ---------- APARÊNCIA: TAMANHO DA LETRA ----------
        sec_letra = self._secao(cfg, "🔠  TAMANHO DA LETRA (todas as abas)",
                                "motor_aparencia", aberta_padrao=False)
        linha_letra = ctk.CTkFrame(sec_letra, fg_color="transparent")
        linha_letra.pack(anchor="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(linha_letra, text="Tamanho da letra:",
                     text_color=COR["texto"]).pack(side="left", padx=(0, 8))
        self._var_escala_motor = tk.StringVar(
            value=nome_da_escala(getattr(self, "_escala_letra", 1.0)))
        ctk.CTkOptionMenu(
            linha_letra, variable=self._var_escala_motor, width=140,
            values=list(ESCALAS_LETRA.keys()),
            command=lambda nome: self._aplicar_escala_letra(ESCALAS_LETRA[nome])
        ).pack(side="left")
        ctk.CTkLabel(
            sec_letra, justify="left", text_color=COR["dim"],
            font=ctk.CTkFont(size=10),
            text="Vale para TODAS as abas — dashboard, plano, log do motor e o "
                 "terminal da TIGER.\nA janela cresce junto para nada ficar "
                 "cortado. Na aba da TIGER há os botões A－ e A＋ para\najustar "
                 "sem sair da conversa. A escolha fica salva."
        ).pack(anchor="w", padx=12, pady=(2, 10))

        # ---------- VOZ: VELOCIDADE E QUAL VOZ ----------
        # Pedido dele, 13/08: "uma opção de configurar a velocidade da fala e
        # uma biblioteca de opções de voz para não ser apenas essa chata".
        # A lista sai do SISTEMA (`say -v ?`), não de uma tabela escrita à
        # mão: presumir que 'Luciana' está instalada seria o mesmo tipo de
        # chute que a ferramenta inteira existe para evitar.
        sec_voz = self._secao(cfg, "🔊  VOZ DA TIGER",
                              "motor_voz", aberta_padrao=False)
        # Guardada para o teste de fumaça poder ABRIR a seção e conferir que
        # o slider da velocidade está mesmo na tela. Widget dentro de bloco
        # recolhido não é mapeado, e a pergunta que importa ("aparece?") só
        # tem resposta com o bloco aberto.
        self.sec_voz_conteudo = sec_voz
        linha_vel = ctk.CTkFrame(sec_voz, fg_color="transparent")
        linha_vel.pack(anchor="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(linha_vel, text="Velocidade da fala:",
                     text_color=COR["texto"]).pack(side="left", padx=(0, 8))
        self.lbl_vel_voz = ctk.CTkLabel(linha_vel, width=140,
                                        text_color=COR["dim"], anchor="w")
        _vel = velocidade_da_voz()

        def _mostrar_vel(v):
            rotulo = ("bem devagar" if v < 130 else "devagar" if v < 155
                      else "normal" if v < 195 else "rápida" if v < 240
                      else "muito rápida")
            self.lbl_vel_voz.configure(text=f"{int(v)} palavras/min ({rotulo})")

        def _ao_mover_vel(v):
            salvar_config({"voz_rate": int(float(v))})
            _mostrar_vel(float(v))

        # DEFEITO MEU, E ERA POR ISSO QUE "A VELOCIDADE NÃO ESTAVA
        # DISPONÍVEL PARA ALTERAR". O slider era criado e o `.set()` era
        # encadeado direto na construção; `.set()` devolve None, a cadeia
        # morria ali, e o `.pack()` nunca acontecia. O controle existia, com
        # o comando ligado e o valor certo — e era INVISÍVEL. Um widget sem
        # `pack` não é um widget escondido: é um widget que não está na tela.
        self.sld_vel_voz = ctk.CTkSlider(
            linha_vel, from_=VOZ_RATE_MIN, to=VOZ_RATE_MAX, width=240,
            number_of_steps=(VOZ_RATE_MAX - VOZ_RATE_MIN) // 5,
            command=_ao_mover_vel)
        self.sld_vel_voz.pack(side="left")
        self.sld_vel_voz.set(_vel)
        self.lbl_vel_voz.pack(side="left", padx=6)
        _mostrar_vel(_vel)

        linha_voz = ctk.CTkFrame(sec_voz, fg_color="transparent")
        linha_voz.pack(anchor="w", padx=12, pady=(4, 2))
        ctk.CTkLabel(linha_voz, text="Voz:",
                     text_color=COR["texto"]).pack(side="left", padx=(0, 8))
        try:
            _vozes = plataforma.vozes_disponiveis()
        except Exception:
            _vozes = []
        # A LISTA COMPLETA DA MÁQUINA, NÃO SÓ AS DE PORTUGUÊS.
        # Ele escreveu: "a biblioteca de voz não está ativa para selecionar
        # outras, não tem outras disponíveis". Estava certo, e a culpa era
        # minha: eu filtrava por português, e num Mac recém-instalado existe
        # UMA voz pt-BR — as boas são download separado do sistema. Um menu
        # com um item só é indistinguível de um menu quebrado.
        self._vozes_por_rotulo = {}
        for _n, _i, _e in _vozes:
            # O idioma no rótulo evita a escolha às cegas: 'Daniel' em en_GB
            # vai ler os números da mesa com sotaque inglês.
            self._vozes_por_rotulo[f"{_n}  ·  {_i}"] = _n
        _rotulos = list(self._vozes_por_rotulo) or ["(a melhor do sistema)"]
        _atual = voz_escolhida()
        self._var_voz = tk.StringVar(
            value=next((r for r, n in self._vozes_por_rotulo.items()
                        if n == _atual), _rotulos[0]))
        ctk.CTkOptionMenu(linha_voz, variable=self._var_voz, values=_rotulos,
                          width=260,
                          command=lambda r: self._trocar_voz(r)).pack(side="left")
        # OUVIR ANTES DE ESCOLHER. Escolher voz por NOME, sem ouvir, é escolher
        # no escuro — e depois descobrir no meio do pregão.
        ctk.CTkButton(linha_voz, text="🔈 ouvir", width=90,
                      fg_color=COR["borda"], hover_color=COR["input"],
                      command=self._experimentar_voz).pack(side="left", padx=6)

        _pt = sum(1 for _n, _i, _e in _vozes if _i.lower().startswith("pt"))
        linha_mais = ctk.CTkFrame(sec_voz, fg_color="transparent")
        linha_mais.pack(anchor="w", padx=12, pady=(4, 2))
        # UM BOTÃO, NÃO UM ROTEIRO DE SEIS PASSOS. "Ajustes do Sistema →
        # Acessibilidade → Conteúdo Falado → Voz do sistema → Gerenciar
        # vozes" é a mesma instrução escrita que já falhou com o Node.js e
        # com o Ollama.
        ctk.CTkButton(linha_mais, text="⬇️ Baixar mais vozes (Ajustes do Mac)",
                      width=280, fg_color=COR["borda"],
                      hover_color=COR["input"],
                      command=self._abrir_ajustes_de_voz).pack(side="left")
        ctk.CTkLabel(
            sec_voz, justify="left", text_color=COR["dim"],
            font=ctk.CTkFont(size=10), wraplength=580,
            text=(f"São {len(_vozes)} voz(es) instaladas nesta máquina, {_pt} "
                  "em português — a lista é a REAL do seu Mac, não uma tabela "
                  "que eu escrevi. As de português vêm primeiro porque só elas "
                  "pronunciam os números da mesa corretamente; as outras estão "
                  "aqui porque você pediu a biblioteca inteira.\nNo painel do "
                  "Mac, procure 'Voz do sistema → Gerenciar vozes' e baixe as "
                  "de português marcadas como Premium ou Aprimorada: são bem "
                  "melhores que a padrão.\nVocê também pode falar comigo: "
                  "'acelere a fala', 'fala mais devagar'.")
        ).pack(anchor="w", padx=12, pady=(2, 10))

        sec_horario = self._secao(cfg, "⏰  PREGÃO E INTERVALO DE ANÁLISE",
                                  "motor_horario", aberta_padrao=False)
        frame_horario = ctk.CTkFrame(sec_horario, fg_color="transparent")
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
            sec_horario,
            text="Dica: no plano gratuito da API Gemini (20 análises/dia por modelo), 15 min\n"
                 "dentro do horário de pregão cabe folgado na cota. A cada 5 min estoura rápido.",
            text_color="gray", font=ctk.CTkFont(size=11), justify="left"
        ).pack(pady=(0, 4))

        # AÇÃO PRINCIPAL DA ABA — fica FORA de qualquer seção recolhível, para
        # nunca ficar escondida atrás de um bloco fechado.
        self.btn_ligar = ctk.CTkButton(master, text="▶️ LIGAR MOTOR", fg_color="gray",
                                        state="disabled", command=self.alternar_motor,
                                        height=40,
                                        font=ctk.CTkFont(size=14, weight="bold"))
        self.btn_ligar.pack(pady=8, padx=10, fill="x")

        # Dropdown de intervalo alterável AO VIVO (mesmo com o motor ligado).
        # O loop de análise relê esse valor a cada ciclo, então mudar aqui
        # ajusta a frequência sem precisar reiniciar o motor.
        frame_intervalo_vivo = ctk.CTkFrame(sec_horario, fg_color="transparent")
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
        sec_notif = self._secao(cfg, "🔔  ALERTAS NA TELA DO COMPUTADOR",
                                "motor_alertas", aberta_padrao=False)
        frame_notif = ctk.CTkFrame(sec_notif, fg_color="#1b2735",
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
        # COMO o aviso aparece. No Mac isto não é preferência estética: a
        # janela desenhada pelo Tk ATIVA o aplicativo e faz a tela pular da
        # corretora para cá. Por isso o padrão no Mac é a notificação nativa.
        linha_estilo = ctk.CTkFrame(frame_notif, fg_color="transparent")
        linha_estilo.pack(pady=(2, 2), padx=12, anchor="w", fill="x")
        ctk.CTkLabel(linha_estilo, text="Como avisar:", text_color=COR["texto"],
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 8))
        self._var_estilo_notif = tk.StringVar(
            value=self.ESTILOS_NOTIFICACAO[self._estilo_notificacao()])
        ctk.CTkOptionMenu(
            linha_estilo, variable=self._var_estilo_notif, width=330,
            values=list(self.ESTILOS_NOTIFICACAO.values()),
            fg_color=COR["input"], button_color=COR["borda"],
            text_color=COR["texto"],
            command=self._salvar_estilo_notificacao).pack(side="left")
        ctk.CTkLabel(
            frame_notif, justify="left", text_color=COR["dim"],
            font=ctk.CTkFont(size=10), wraplength=560,
            text="No macOS, uma janela desenhada pelo programa ATIVA o aplicativo — "
                 "a tela pula da corretora para cá a cada sugestão, sem você clicar "
                 "em nada. É comportamento do sistema, não escolha do app. Por isso "
                 "o padrão no Mac é a NOTIFICAÇÃO DO SISTEMA, que aparece no canto e "
                 "não tira o foco de ninguém. Nela não cabem os botões ACATAR / NÃO "
                 "OPEREI: a decisão sai pelo chat ('acatar') ou pelo dashboard."
        ).pack(pady=(0, 4), padx=12, anchor="w")

        linha_notif = ctk.CTkFrame(frame_notif, fg_color="transparent")
        linha_notif.pack(pady=(0, 10), padx=12, anchor="w")
        ctk.CTkButton(linha_notif, text="🔔 Testar notificação", width=170,
                      fg_color="#2a3f5f", hover_color="#3a5580",
                      command=lambda: self._notificar_desktop(
                          "🔔 Teste de notificação",
                          ["Se você está vendo isto, os alertas estão funcionando.",
                           "Novas sugestões vão aparecer assim.",
                           "Botão direito no aviso também fecha."])
                      ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(linha_notif, text="🔕 Fechar avisos na tela", width=180,
                      fg_color="#5a3a3a", hover_color="#8b4513",
                      command=self._fechar_todas_notificacoes).pack(side="left", padx=6)

        self.lbl_qr_titulo = ctk.CTkLabel(self.sec_whatsapp, text="", text_color="white",
                                           font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_qr_titulo.pack(pady=(12, 4))
        self.lbl_qr_imagem = ctk.CTkLabel(self.sec_whatsapp, text="")
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

        sec_log = self._secao(master, "📋  REGISTRO DE ATIVIDADE (log do motor)",
                              "motor_log", aberta_padrao=True)
        self.console = tk.Text(sec_log, height=22, bg="#0d0d0d", fg="#00ff00",
                                font=("Consolas",
                                      max(8, int(round(_FONTE_BASE_CONSOLE *
                                                       getattr(self, "_escala_letra", 1.0))))),
                                relief="flat", borderwidth=0,
                                insertbackground="#00ff00")
        self.console.pack(pady=(0, 8), padx=10, fill="both", expand=True)

        # ---------- AUTOMAÇÃO TRADOVATE (opcional) ----------
        self._montar_painel_tradovate(
            self._secao(cfg, "🤖  AUTOMAÇÃO TRADOVATE (envio de ordem)",
                        "motor_tradovate", aberta_padrao=False))

        # ---------- SEÇÃO DESENVOLVEDOR (oculta no app do cliente) ----------
        if MODO_DEV:
            frame_dev = ctk.CTkFrame(
                self._secao(cfg, "🛠️  MODO DESENVOLVEDOR", "motor_dev",
                            aberta_padrao=False),
                fg_color="#2b1b1b", border_color="#8b4513", border_width=1)
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
                          command=lambda: plataforma.abrir_pasta(pasta_dados_usuario())).pack(side="left", padx=6)

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

    # ------------------------------------------------------------------
    # MULTI-JANELA — vários gráficos, um motor só
    # ------------------------------------------------------------------
    def _render_lista_janelas(self):
        """Desenha a lista das janelas que entram em cada ciclo."""
        for w in self.frame_lista_janelas.winfo_children():
            w.destroy()
        lista = janelas_monitoradas()
        if not lista:
            ctk.CTkLabel(self.frame_lista_janelas, text_color=COR["dim"],
                         font=ctk.CTkFont(size=11),
                         text="Nenhuma janela na lista — o motor captura a tela inteira."
                         ).pack(anchor="w", padx=6, pady=4)
            return
        for i, titulo in enumerate(lista):
            linha = ctk.CTkFrame(self.frame_lista_janelas, fg_color=COR["input"])
            linha.pack(fill="x", padx=4, pady=2)
            marca = "⭐ principal" if i == 0 else f"{i + 1}º"
            ctk.CTkLabel(linha, text=f"{marca}", width=90, text_color=COR["dim"],
                         font=ctk.CTkFont(size=10)).pack(side="left", padx=(8, 4))
            ctk.CTkLabel(linha, text=titulo[:70], anchor="w",
                         text_color=COR["texto"], font=ctk.CTkFont(size=11)
                         ).pack(side="left", fill="x", expand=True, padx=4, pady=6)
            ctk.CTkButton(linha, text="🗑 Remover", width=90, fg_color=COR["vermelho"],
                          command=lambda t=titulo: self._remover_janela_monitorada(t)
                          ).pack(side="right", padx=6, pady=4)

    def _diagnosticar_janelas(self):
        """Despeja no log TUDO o que o sistema reporta sobre as janelas.

        Serve para o caso em que a janela esperada não aparece no seletor: em
        vez de adivinhar, olha-se o dado cru. No Mac isso mostra também as
        janelas que estão em OUTRA ÁREA DE TRABALHO — que era o motivo real de
        a janela da corretora sumir mesmo com a permissão concedida."""
        try:
            self.log("🩺 DIAGNÓSTICO DE JANELAS")
            for linha in plataforma.diagnostico_janelas().split("\n"):
                self.log("   " + linha)
            self.log("   ——— fim do diagnóstico ———")
        except Exception as e:
            self.log(f"⚠️ Não consegui montar o diagnóstico de janelas: {e}")

    def _incluir_janela_monitorada(self):
        titulo = (self.janela_var.get() or "").strip()
        if not titulo or titulo.startswith("("):
            self.log("⚠️ Escolha uma janela no seletor acima antes de incluir "
                      "(use '🔄 Atualizar lista de janelas abertas').")
            return
        lista = janelas_monitoradas()
        if titulo in lista:
            self.log(f"ℹ️ '{titulo}' já está na lista de gráficos analisados.")
            return
        lista.append(titulo)
        salvar_janelas_monitoradas(lista)
        self._render_lista_janelas()
        self.log(f"🪟 '{titulo}' entrou na análise. Agora são {len(lista)} gráfico(s) "
                  "por ciclo — cada um com cenário e histórico próprios. "
                  "Lembre: cada gráfico a mais consome cota da API por ciclo.")

    def _remover_janela_monitorada(self, titulo):
        lista = [t for t in janelas_monitoradas() if t != titulo]
        salvar_janelas_monitoradas(lista)
        self._render_lista_janelas()
        self.log(f"🪟 '{titulo}' saiu da análise. "
                  + (f"Restam {len(lista)} gráfico(s)." if lista
                     else "A lista ficou vazia — o motor volta a capturar a tela inteira."))

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

    # ==================================================================
    # ABA 🐯 TIGER — chat por mensagem e voz, estilo terminal (Claude Code)
    # ==================================================================
    def _montar_tab_ia(self, master):
        # Estado da conversa
        self._chat_conf = None          # ação aguardando "sim" (ex.: ACATAR)
        self._chat_ocupada = False      # evita duas perguntas simultâneas
        self._ultima_analise = {}       # última leitura do gráfico (p/ contexto)
        self._chat_por_voz = False      # o último pedido veio por VOZ? → responde por voz
        self._chat_fila = []            # fila ÚNICA de escrita no terminal
        self._chat_render_ativo = False # há algo sendo escrito/digitado agora?
        self._ouvindo = False           # microfone em uso (botão ou OLÁ TIGER)
        self._tiger_rodando = False     # loop da palavra de ativação ativo?
        self._chat_anexo = None         # arquivo (foto/vídeo/doc) aguardando envio
        self._ultimo_pedido = ""        # fala deste turno (as buscas web usam)
        self._ultima_resposta_local = None   # evita repetir a mesma resposta da base
        # Última captura do gráfico feita pelo motor — os "olhos" dela no chat.
        # Se o app reabriu e o print da sessão passada ainda está no disco, ela
        # já começa enxergando (com a idade correta, para não tratá-lo como novo).
        self._ultimo_print = None
        if os.path.exists(ULTIMO_PRINT_FILE):
            try:
                self._ultimo_print = {
                    "caminho": ULTIMO_PRINT_FILE,
                    "quando": os.path.getmtime(ULTIMO_PRINT_FILE),
                    "hora": time.strftime("%H:%M", time.localtime(
                        os.path.getmtime(ULTIMO_PRINT_FILE))),
                    "janela": carregar_config().get("nome_janela_corretora", "")}
            except Exception:
                self._ultimo_print = None
        cfg = carregar_config()
        self.ia_voz_var = tk.BooleanVar(value=cfg.get("ia_voz", False))
        self.ia_tiger_var = tk.BooleanVar(value=cfg.get("ia_tiger", False))

        raiz = ctk.CTkFrame(master, fg_color="#0d1117")
        raiz.pack(fill="both", expand=True)

        # ---------- Cabeçalho (barra do terminal) ----------
        topo = ctk.CTkFrame(raiz, fg_color="#161b22", corner_radius=0, height=40)
        topo.pack(fill="x")
        ctk.CTkLabel(topo, text="🐯", text_color="#ff9f43",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=(12, 4), pady=8)
        # A VERSÃO FICA À VISTA: sem isso não dá para saber, olhando o chat, se
        # o .exe rodando é o novo ou o antigo — e um teste feito no build velho
        # parece um defeito que já foi corrigido.
        ctk.CTkLabel(topo, text=f"TIGER — IA da mesa · v{VERSAO_ATUAL}",
                     text_color="#e6edf3",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", pady=8)
        # Vínculo EXPLÍCITO com a conta selecionada: a TIGER conversa sempre
        # sobre o plano/números DESTA conta (mesma seleção do Plano de Trading).
        self.lbl_ia_conta = ctk.CTkLabel(topo, text=f"🏦 {nome_conta_ativa()}",
                                          text_color="#79c0ff",
                                          font=ctk.CTkFont(size=11, weight="bold"))
        self.lbl_ia_conta.pack(side="left", padx=10)
        self.lbl_ia_status = ctk.CTkLabel(topo, text="pronta", text_color="#3fb950",
                                           font=ctk.CTkFont(size=11))
        self.lbl_ia_status.pack(side="right", padx=12)
        # TAMANHO DA LETRA, à mão, aqui na barra — é nesta tela que ele mais lê.
        # Dois botões em vez de um menu: no meio do pregão, um clique resolve.
        ctk.CTkButton(topo, text="A＋", width=38, height=26,
                      fg_color="#21262d", hover_color="#30363d",
                      text_color="#e6edf3",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=lambda: self._escala_por_passo(+1)
                      ).pack(side="right", padx=(0, 4))
        ctk.CTkButton(topo, text="A－", width=38, height=26,
                      fg_color="#21262d", hover_color="#30363d",
                      text_color="#e6edf3",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      command=lambda: self._escala_por_passo(-1)
                      ).pack(side="right", padx=(6, 2))
        self.lbl_escala_ia = ctk.CTkLabel(
            topo, text=f"letra: {nome_da_escala(getattr(self, '_escala_letra', 1.0))}",
            text_color="#4a5163", font=ctk.CTkFont(size=10))
        self.lbl_escala_ia.pack(side="right", padx=(6, 0))
        ctk.CTkLabel(topo, text="Smart Money Concepts + análise técnica clássica",
                     text_color="#4a5163", font=ctk.CTkFont(size=10)
                     ).pack(side="right", padx=8)

        # ---------- Transcript (a "tela" do terminal) ----------
        # O tk.Text NÃO é escalado pelo CustomTkinter — a fonte dele é calculada
        # aqui, com a escala de letra escolhida pelo trader (botões A− / A+ na
        # barra acima). Sem isto, aumentar a letra deixava tudo maior MENOS a
        # tela onde ele mais lê.
        _tam = max(8, int(round(_FONTE_BASE_CHAT * getattr(self, "_escala_letra", 1.0))))
        self.txt_chat = tk.Text(raiz, bg="#0d1117", fg="#c9d1d9", wrap="word",
                                 relief="flat", padx=14, pady=10,
                                 font=("Consolas", _tam), insertbackground="#c9d1d9",
                                 selectbackground="#264f78", state="disabled")
        self.txt_chat.pack(fill="both", expand=True, padx=2, pady=(2, 0))
        self.txt_chat.tag_configure("prompt", foreground="#00E676",
                                     font=("Consolas", _tam, "bold"))
        self.txt_chat.tag_configure("voce", foreground="#e6edf3")
        self.txt_chat.tag_configure("ia_pref", foreground="#ff9f43",
                                     font=("Consolas", _tam, "bold"))
        self.txt_chat.tag_configure("ia", foreground="#c9d1d9")
        self.txt_chat.tag_configure("sistema", foreground="#8a92a5",
                                     font=("Consolas", max(8, _tam - 1), "italic"))
        self.txt_chat.tag_configure("hora", foreground="#3d434f",
                                     font=("Consolas", max(7, _tam - 3)))

        # ---------- Entrada ----------
        rodape = ctk.CTkFrame(raiz, fg_color="#161b22", corner_radius=0)
        rodape.pack(fill="x", side="bottom")

        self.entrada_chat = ctk.CTkTextbox(rodape, height=58, fg_color="#0d1117",
                                            text_color="#e6edf3", corner_radius=8,
                                            border_width=1, border_color="#30363d",
                                            font=ctk.CTkFont(
                                                family="Consolas",
                                                size=max(9, int(round(12 * getattr(self, "_escala_letra", 1.0))))))
        self.entrada_chat.pack(fill="x", padx=10, pady=(8, 4))
        self.entrada_chat.bind("<Return>", self._chat_enviar)
        self.entrada_chat.bind("<Shift-Return>", lambda e: None)  # quebra de linha

        barra = ctk.CTkFrame(rodape, fg_color="transparent")
        barra.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(barra, text="➤ Enviar", width=100, height=28,
                      fg_color="#1f6feb", hover_color="#388bfd",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._chat_enviar).pack(side="left")
        ctk.CTkButton(barra, text="🎤 Falar", width=90, height=28,
                      fg_color="#21262d", hover_color="#30363d",
                      command=self._chat_ouvir).pack(side="left", padx=6)
        ctk.CTkButton(barra, text="📎 Anexar", width=90, height=28,
                      fg_color="#21262d", hover_color="#30363d",
                      command=self._chat_anexar).pack(side="left")
        # BOTÃO DE CALAR: um clique e ela para de falar na hora. Fica sempre à
        # vista (não só quando ela fala) porque procurar botão que aparece e
        # some, no meio do pregão, é pior que ter um botão a mais.
        ctk.CTkButton(barra, text="⏹ Parar fala", width=100, height=28,
                      fg_color="#3d1f24", hover_color="#5a2a32",
                      text_color="#ff9f9f",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._chat_parar_fala).pack(side="left", padx=6)
        # Chip do anexo pendente: aparece quando há arquivo esperando envio;
        # clicar nele cancela o anexo.
        self.btn_anexo = ctk.CTkButton(barra, text="", width=10, height=28,
                                        fg_color="#1c2a3a", hover_color="#30363d",
                                        text_color="#79c0ff",
                                        font=ctk.CTkFont(size=10),
                                        command=self._chat_anexo_limpar)
        ctk.CTkCheckBox(barra, text="🔊 responder por voz", variable=self.ia_voz_var,
                        command=lambda: salvar_config({"ia_voz": self.ia_voz_var.get()}),
                        text_color="#8a92a5", fg_color="#1f6feb",
                        checkbox_width=18, checkbox_height=18,
                        font=ctk.CTkFont(size=11)).pack(side="left", padx=10)
        ctk.CTkCheckBox(barra, text="🐯 OLÁ TIGER (sempre à escuta)",
                        variable=self.ia_tiger_var, command=self._tiger_alternar,
                        text_color="#ff9f43", fg_color="#ff9f43",
                        checkbox_width=18, checkbox_height=18,
                        font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
        ctk.CTkButton(barra, text="🧹 limpar", width=80, height=28,
                      fg_color="#21262d", hover_color="#30363d",
                      command=self._chat_limpar).pack(side="right")
        ctk.CTkLabel(barra, text="Enter envia · acatar · dispensar · cancelar ordem · "
                                 "status · liga/desliga o motor · zera o ciclo · "
                                 "manda no whatsapp · tira um print · olha o gráfico · "
                                 "<regra>, aprenda isso",
                     text_color="#4a5163", font=ctk.CTkFont(size=9)
                     ).pack(side="right", padx=10)

        # Recarrega a conversa anterior (persistida em disco)
        historico = carregar_chat()
        for m in historico[-40:]:
            self._chat_escrever(m["papel"], m["texto"], persistir=False,
                                 hora=m.get("hora", ""))
        if not historico:
            self._chat_escrever(
                "ia",
                "Olá, Josevan! Eu sou a TIGER, a IA da sua mesa — leitura Smart "
                "Money com confluência de análise técnica clássica. Fale comigo "
                "por texto, pelo 🎤, ou ligue o modo OLÁ TIGER e me chame de "
                "qualquer lugar: 'Olá Tiger, qual o status?'. Eu ligo e desligo o "
                "motor quando você pedir, olho o último print que ele capturou "
                "('olha o gráfico'), pesquiso notícia e agenda do mercado na "
                "internet, e analiso prints, fotos e vídeos que você mandar pelo "
                "📎. Você me ensina regras com 'aprenda: ...'. Como quer começar?",
                persistir=False)
        # Retoma a escuta da palavra de ativação se ficou ligada da última vez.
        if self.ia_tiger_var.get():
            self.after(1500, self._tiger_iniciar)

    # ---------------- Escrita no terminal ----------------
    # REGRA DE OURO: NADA escreve direto no txt_chat. Toda mensagem entra numa
    # FILA ÚNICA e é escrita uma por vez. Antes, duas animações de digitação
    # simultâneas (resposta + evento do feed) intercalavam os caracteres e a
    # conversa saía embaralhada na tela — isto elimina o problema na raiz.
    def _chat_agendar(self, modo, papel, texto, hora=None):
        try:
            self._chat_fila.append((modo, papel, texto, hora))
            if not self._chat_render_ativo:
                self._chat_render_ativo = True
                self.after(0, self._chat_render_proximo)
        except Exception:
            pass

    def _chat_render_proximo(self):
        if not self._chat_fila:
            self._chat_render_ativo = False
            return
        modo, papel, texto, hora = self._chat_fila.pop(0)
        if modo == "digitar":
            self._chat_digitar_passo(texto, 0)
        else:
            self._chat_inserir(papel, texto, hora)
            self.after(1, self._chat_render_proximo)

    def _chat_inserir(self, papel, texto, hora=None):
        """Escreve uma mensagem INTEIRA no terminal (sem animação)."""
        try:
            self.txt_chat.configure(state="normal")
            hora = hora or time.strftime('%H:%M')
            self.txt_chat.insert("end", f"{hora}  ", "hora")
            if papel == "voce":
                self.txt_chat.insert("end", "❯ ", "prompt")
                self.txt_chat.insert("end", texto + "\n\n", "voce")
            elif papel == "ia":
                self.txt_chat.insert("end", "✳ ", "ia_pref")
                self.txt_chat.insert("end", texto + "\n\n", "ia")
            else:
                self.txt_chat.insert("end", texto + "\n\n", "sistema")
            self.txt_chat.configure(state="disabled")
            self.txt_chat.see("end")
        except Exception:
            pass

    def _chat_escrever(self, papel, texto, persistir=True, hora=None):
        if persistir:
            registrar_msg_chat(papel, texto)
        self._chat_agendar("inteira", papel, texto, hora)

    def _chat_digitar(self, texto):
        """Resposta da TIGER com efeito de digitação (entra na fila única)."""
        self._chat_agendar("digitar", "ia", texto)

    def _chat_digitar_passo(self, texto, _pos):
        """Um quadro da animação. VELOCIDADE ADAPTATIVA: o passo cresce com o
        tamanho do texto, então mesmo resposta longa termina em ~0,5 s."""
        passo = max(4, len(texto) // 50)
        try:
            if _pos == 0:
                self.txt_chat.configure(state="normal")
                self.txt_chat.insert("end", f"{time.strftime('%H:%M')}  ", "hora")
                self.txt_chat.insert("end", "✳ ", "ia_pref")
                self.txt_chat.configure(state="disabled")
            trecho = texto[_pos:_pos + passo]
            if trecho:
                self.txt_chat.configure(state="normal")
                self.txt_chat.insert("end", trecho, "ia")
                self.txt_chat.configure(state="disabled")
                self.txt_chat.see("end")
                self.after(8, lambda: self._chat_digitar_passo(texto, _pos + passo))
                return
            self.txt_chat.configure(state="normal")
            self.txt_chat.insert("end", "\n\n", "ia")
            self.txt_chat.configure(state="disabled")
            self.txt_chat.see("end")
        except Exception:
            pass
        # "pronta" só quando NÃO há decisão esperando por ele. Sem isto, a
        # animação de digitação terminava e apagava o "⏳ aguardando
        # confirmação" que tinha acabado de ser posto — o trader digitava
        # ACATAR, via a pergunta, o indicador voltava para "pronta" e ele
        # concluía que nada estava pendente.
        if getattr(self, "_chat_conf", None) == "ACATAR":
            self._chat_status("⏳ aguardando confirmação do ACATAR", "#ffcc66")
        elif getattr(self, "_chat_conf", None) == "ZERAR_CICLO":
            self._chat_status("⏳ aguardando o seu 'sim' para ZERAR", "#ffcc66")
        else:
            self._chat_status("pronta", "#3fb950")
        self._chat_ocupada = False
        self.after(1, self._chat_render_proximo)

    def _chat_status(self, texto, cor="#8a92a5"):
        try:
            self.lbl_ia_status.configure(text=texto, text_color=cor)
        except Exception:
            pass

    def _chat_limpar(self):
        salvar_chat([])
        try:
            self.txt_chat.configure(state="normal")
            self.txt_chat.delete("1.0", "end")
            self.txt_chat.configure(state="disabled")
        except Exception:
            pass
        self._chat_escrever("sistema", "(conversa limpa — as lições ensinadas "
                                        "continuam guardadas)", persistir=False)

    # ---------------- Anexos (fotos, vídeos e arquivos) ----------------
    def _chat_anexar(self):
        """Escolhe um arquivo para mandar à TIGER: print/foto do gráfico,
        VÍDEO da tela, PDF, planilha... Imagens vão inline; arquivos grandes
        (vídeos até ~1,9 GB) sobem pela File API do Gemini."""
        from tkinter import filedialog
        caminho = filedialog.askopenfilename(
            parent=self, title="Enviar arquivo para a TIGER",
            filetypes=[
                ("Tudo que a TIGER lê", "*.png *.jpg *.jpeg *.webp *.gif *.bmp "
                                         "*.mp4 *.mov *.avi *.mkv *.webm *.mpeg "
                                         "*.pdf *.txt *.csv *.log *.md"),
                ("Imagens (prints do gráfico)", "*.png *.jpg *.jpeg *.webp *.gif *.bmp"),
                ("Vídeos (gravação da tela)", "*.mp4 *.mov *.avi *.mkv *.webm *.mpeg"),
                ("Documentos", "*.pdf *.txt *.csv *.log *.md"),
                ("Todos os arquivos", "*.*")])
        if not caminho:
            return
        try:
            tamanho = os.path.getsize(caminho)
        except OSError:
            self._chat_escrever("sistema", "(não consegui ler esse arquivo)",
                                 persistir=False)
            return
        if tamanho > 1_900_000_000:
            self._chat_escrever(
                "sistema", "(arquivo grande demais — o limite é ~1,9 GB. "
                "Para vídeos longos, grave um trecho menor.)", persistir=False)
            return
        self._chat_anexo = caminho
        nome = os.path.basename(caminho)
        mb = tamanho / 1_000_000
        self.btn_anexo.configure(text=f"📎 {nome[:28]} ({mb:.1f} MB)  ✕")
        self.btn_anexo.pack(side="left", padx=6)
        self._chat_escrever(
            "sistema",
            f"(📎 anexado: {nome} ({mb:.1f} MB) — escreva a pergunta e aperte "
            "Enter; ou Enter direto para eu analisar já. Clique no chip para "
            "cancelar.)", persistir=False)

    def _chat_anexo_limpar(self):
        self._chat_anexo = None
        try:
            self.btn_anexo.pack_forget()
        except Exception:
            pass

    # ---------------- Fluxo de um turno ----------------
    def _chat_enviar(self, event=None):
        # Shift+Enter deixa quebrar linha; Enter puro envia.
        if event is not None and getattr(event, "state", 0) & 0x0001:
            return None
        texto = self.entrada_chat.get("1.0", "end").strip()
        anexo = self._chat_anexo
        if not texto and not anexo:
            return "break"
        if not texto:
            texto = "Analise este arquivo para mim, no contexto da mesa."
        self.entrada_chat.delete("1.0", "end")
        self._chat_por_voz = False   # pedido digitado → resposta segue o checkbox 🔊
        if anexo:
            self._chat_anexo_limpar()
            self._chat_escrever("voce", f"{texto}\n📎 {os.path.basename(anexo)}")
            self._chat_processar(texto, anexo=anexo)
        else:
            self._chat_escrever("voce", texto)
            self._chat_processar(texto)
        return "break"

    def _chat_processar(self, texto, anexo=None):
        # Guarda a fala deste turno ANTES de qualquer desvio: as ações de web
        # precisam do texto para saber o que pesquisar, e a guarda de nível
        # precisa dele para saber o que foi perguntado — inclusive no turno
        # com arquivo anexado, que também pode perguntar "onde está a VWAP?".
        self._ultimo_pedido = texto
        # Com arquivo junto, o turno é sempre conversa com o modelo (não faz
        # sentido interpretar 'acatar/status' num envio de vídeo/print).
        if anexo:
            if self._chat_ocupada:
                self._chat_escrever("sistema", "(aguarde — ainda estou "
                                     "respondendo a anterior)", persistir=False)
                return
            self._chat_ocupada = True
            self._chat_status("📎 lendo o arquivo…", "#ff9f43")
            threading.Thread(target=self._chat_worker, args=(texto, anexo),
                             daemon=True).start()
            return

        # "SIM" RESPONDENDO A UMA PERGUNTA QUE ELA FEZ.
        # Quando ela oferece ("Quer revisar o que deu errado?"), a resposta do
        # trader tem um dono. Sem este bloco, o "sim" chegava solto ao modelo —
        # que estava sem cota — e virava a desculpa genérica. Uma IA que
        # pergunta e não entende a resposta não é uma IA, é um formulário.
        pendente = getattr(self, "_topico_pendente", None)
        if pendente and interpretar_intencao(texto) == "SIM":
            self._topico_pendente = None
            acao, ref = pendente
            if acao == "POSTMORTEM":
                alvo = next((p for p in posicoes_do_ciclo()
                             if p.get("id") == ref), None)
                self._chat_responder(montar_postmortem(alvo))
                return
            if acao == "VER_GRAFICO":
                tipo, dado = "VER_GRAFICO", None
                self._chat_conf = None
            else:
                tipo, dado = "EXECUTAR", acao
                self._chat_conf = None
        else:
            # Qualquer outra coisa encerra o tópico: ele mudou de assunto.
            if pendente:
                self._topico_pendente = None
            tipo, dado = processar_turno_chat(texto, self._chat_conf)
            self._chat_conf = None

        if tipo == "PEDIR_CONFIRMACAO":
            self._chat_conf = dado
            if dado == "ZERAR_CICLO":
                self._chat_responder(
                    f"Confirmando: ZERAR o ciclo da conta '{nome_conta_ativa()}'? "
                    "Isso limpa resultado, gráficos e contagem de dias no "
                    "dashboard e começa um ciclo novo agora. Seu histórico NÃO "
                    "é apagado — fica arquivado. Responda 'sim' para eu zerar "
                    "ou 'não' para deixar como está.")
                self._chat_status("⏳ aguardando o seu 'sim' para ZERAR",
                                  "#ffcc66")
                return
            sinal = self._ultimo_sinal_pendente()
            if not sinal:
                self._chat_conf = None
                self._chat_responder(self._motivo_sem_pendente())
                return
            self._chat_responder(
                f"Confirmando: ACATAR o {sinal.get('direcao')} {sinal.get('ativo','')} "
                f"com entrada {sinal.get('entry')} e stop {sinal.get('stop')}?\n\n"
                "👉 Responda 'sim' — ou digite ACATAR de novo, que eu tomo como "
                "confirmado. 'não' deixa quieto.\n"
                "NADA foi registrado ainda: dinheiro nunca sai de um comando só.")
            # O ESTADO DE ESPERA PRECISA APARECER. O trader digitou ACATAR,
            # recebeu uma pergunta e concluiu que "nada aconteceu" — o programa
            # estava esperando e não mostrava isso em lugar nenhum.
            self._chat_status("⏳ aguardando confirmação do ACATAR", "#ffcc66")
            return
        if tipo == "CONF_CANCELADA":
            self._chat_responder("Certo, deixei como estava — nada foi feito.")
            return
        if tipo == "ESQUECER":
            removida = remover_licao(dado)
            if removida:
                restantes = carregar_licoes()
                self._chat_responder(
                    f"Apaguei da memória: “{removida[:180]}”.\n\n"
                    + (f"Ainda tenho {len(restantes)} lição(ões) gravada(s) — "
                       "peça 'liste o que você aprendeu' para conferir."
                       if restantes else
                       "Não sobrou nenhuma lição gravada."))
            else:
                self._chat_responder(
                    "Não achei essa lição para apagar. Peça 'liste o que você "
                    "aprendeu' — elas saem numeradas, e aí você diz 'apaga a 2'.")
            return
        if tipo == "CONFIGURAR":
            self._chat_configurar(dado, texto)
            return
        if tipo == "DEFINIR_NIVEIS":
            self._chat_definir_niveis(dado)
            return
        if tipo == "APRENDER":
            # "aprenda isso" sozinho: a lição é o que ELE disse no turno
            # anterior, que é exatamente o que "isso" quer dizer.
            if not dado:
                anteriores = [m["texto"] for m in carregar_chat()
                              if m.get("papel") == "voce" and m.get("texto")]
                # o último é o próprio "aprenda isso"; a lição é o de antes
                dado = anteriores[-2].strip() if len(anteriores) >= 2 else ""
                if not dado:
                    self._chat_responder(
                        "Aprender o quê? Me diga a regra na mesma frase — por "
                        "exemplo: 'nunca opere contra o H4 depois das 15h, "
                        "aprenda isso'.")
                    return
                # "APRENDA TUDO ISSO" — ele está apontando para VÁRIAS falas, e
                # eu não sei onde "tudo" começa. Gravar a última e dizer
                # "aprendi tudo" seria mentira; adivinhar o resto seria gravar
                # lixo na memória permanente. Então gravo a última (que é o que
                # eu sei) e mostro as outras para ele apontar.
                if re.search(r"\b(tudo|todo)\b", texto, re.IGNORECASE):
                    recentes = [t for t in anteriores[-7:-1] if t.strip()][-5:]
                    if len(recentes) > 1:
                        lista = "\n".join(f"  {i}. “{t.strip()[:110]}”"
                                          for i, t in enumerate(recentes, 1))
                        self._chat_responder(
                            f"Vou gravar a última: “{dado[:160]}”.\n\n"
                            "Mas “tudo isso” eu NÃO sei onde começa, e chutar "
                            "aqui é gravar regra errada na memória permanente. "
                            "Estas são as suas últimas falas:\n" + lista +
                            "\n\nMe diga qual delas virar regra — ou repita a "
                            "regra na mesma frase, que é como eu gravo com "
                            "certeza: '<a regra>, aprenda isso'.")
            # A PERGUNTA É O EXEMPLO; A REGRA É O QUE VEM DEPOIS DELA.
            # 13/08, 16:03: 'qual a probabilidade de batermos a meta de hoje?
            # olha no plano de trading e o motor para responder essa pergunta —
            # aprenda isso'. Gravar a frase inteira guardava o exemplo junto
            # com a regra, e o exemplo passava a entrar em toda análise.
            dado, pergunta_fora = separar_pergunta_da_regra(dado)
            if pergunta_fora:
                self.log(f"✂️ Da lição, tirei a pergunta que era só o exemplo: "
                         f"“{pergunta_fora[:120]}”. Gravo a regra.")

            # UMA LIÇÃO NÃO REVOGA A REGRA DA CASA. Se o que ele está pedindo é
            # que ela produza dado que NÃO TEM, gravar isso seria transformar
            # "nunca invente número" em "invente quando faltar" — e para sempre,
            # já que lição vale em toda análise futura.
            impossivel, porque = licao_pede_invencao(dado)
            if impossivel:
                self._chat_responder(
                    f"NÃO vou gravar essa: “{dado}”.\n\n"
                    f"O motivo é que {porque}. Se eu aceitasse, estaria "
                    "prometendo uma coisa que não sei fazer — e o resultado não "
                    "seria uma leitura ruim, seria um número inventado com cara "
                    "de análise. Na sua mesa isso vira prejuízo.\n\n"
                    "O que eu faço de verdade quando a cota cai: digo que a cota "
                    "caiu, e sigo respondendo o que não depende dela — cotação "
                    "real do ativo, notícia das casas de mercado, metodologia "
                    "SMC, o seu plano e os números da sua conta.\n\n"
                    "Se você quiser mesmo tirar essa dependência, a saída é uma "
                    "chave paga da Gemini colada na aba Motor — aí eu leio o "
                    "gráfico sempre.")
                return

            # LIÇÃO NÃO LIGA BOTÃO. 14/08, 10:57 e 10:58: ele mandou duas vezes
            # "toda vez que eu enviar STATUS pelo whatsapp, envie o status para
            # mim - aprenda isso" e ouviu "aprendido" nas duas. Nunca ia
            # funcionar: o WhatsApp daqui só envia, e lição nunca vira código.
            acao, explica = licao_pede_acao(dado)
            if acao:
                self._chat_responder(
                    f"NÃO vou gravar essa: “{dado}”.\n\n"
                    f"O motivo é que {explica}.")
                return
            if adicionar_licao(dado):
                self._chat_responder(
                    f"Anotado e aprendido: “{dado}”. Está gravado na minha "
                    "memória e passa a valer em TODAS as análises e conversas "
                    "daqui pra frente — inclusive depois de fechar o programa.")
            else:
                self._chat_responder(f"Essa lição já estava gravada: “{dado}”. "
                                      "Segue valendo, não precisa repetir.")
            return
        if tipo == "PRINT_AGORA":
            # "tira um print e vê minha posição": captura NA HORA, sem esperar
            # o ciclo do motor. Antes ela mandava esperar 5 minutos (ou pior,
            # dizia que já tinha visto). Se a captura falhar, ela diz por quê.
            info = self._capturar_print_agora()
            if info:
                self._ultimo_print = info
                tipo = "VER_GRAFICO"
            else:
                self._chat_responder(
                    "Não consegui capturar a tela agora. Confira na aba Motor "
                    "qual janela está selecionada e deixe ela visível (pode "
                    "estar atrás de outras, mas não totalmente coberta nem "
                    "minimizada). Se preferir, me mande o print pelo 📎.")
                return
        if tipo == "VER_GRAFICO":
            # LIÇÃO DELE, 04/08 22:13: "quando pedir para analisar o gráfico,
            # use o motor, tire um print NOVO e analise imediatamente". Antes
            # ela lia a captura velha do ciclo anterior e comentava um preço
            # que já tinha mudado. Agora, se a captura tem mais de 1 minuto,
            # tira uma nova ANTES de olhar — e se a nova falhar, usa a antiga
            # (melhor a de 5 minutos atrás do que nenhuma).
            info = getattr(self, "_ultimo_print", None)
            if idade_do_ultimo_print(info) is None or \
                    (idade_do_ultimo_print(info) or 0) >= 1:
                info = self._capturar_print_agora() or info
                if info:
                    self._ultimo_print = info
            caminho = (info or {}).get("caminho")
            # ---- O OCR RESPONDE ANTES DO MODELO ----
            # Pergunta de NÍVEL não é pergunta de interpretação: é leitura de
            # texto impresso. Aqui ela é respondida sem chave, sem internet e
            # sem cota — e sem o risco que fez 7769.56 virar 7752.34.
            if caminho and pergunta_onde_esta_indicador(texto):
                lido = self._ler_nivel_por_ocr(caminho, texto)
                if lido:
                    self._chat_responder(lido)
                    return
            if caminho and os.path.exists(caminho):
                if self._chat_ocupada:
                    self._chat_escrever("sistema", "(aguarde — ainda estou "
                                         "respondendo a anterior)", persistir=False)
                    return
                self._chat_ocupada = True
                idade = idade_do_ultimo_print(info)
                self._chat_status(f"🔎 olhando o gráfico (print de "
                                   f"{info.get('hora', '—')})…", "#ff9f43")
                pedido = (f"{texto}\n\n[A imagem anexada é a captura que o MOTOR "
                          f"fez da janela '{info.get('janela', '—')}' às "
                          f"{info.get('hora', '—')}"
                          + (f", há cerca de {idade:.0f} minuto(s)" if idade is not None else "")
                          + ". É o gráfico que ele está lendo. Se a captura "
                          "estiver velha demais para a pergunta, avise.]")
                threading.Thread(target=self._chat_worker,
                                 args=(pedido, caminho), daemon=True).start()
                return
            # SEM PRINT GUARDADO: tenta capturar NA HORA em vez de desistir.
            # "analise meu gráfico agora" caía no genérico "não tenho como
            # responder" — sendo que bastava tirar o print.
            novo = self._capturar_print_agora()
            if novo:
                self._ultimo_print = novo
                self._chat_processar(texto)
                return
            self._chat_responder(
                "Não consegui capturar o gráfico agora. Se o motor estiver "
                "desligado, diga 'liga o motor'; se estiver ligado, confira na "
                "aba Motor qual janela está selecionada e deixe ela visível. "
                "Se preferir, me mande o print pelo 📎 que eu analiso na hora.")
            return
        if tipo == "EXECUTAR":
            self._chat_executar_acao(dado)
            return
        # CONHECIMENTO LOCAL ANTES DA API: pergunta de metodologia ("o que é um
        # CHoCH?") tem resposta fixa — não faz sentido queimar cota com ela. Sai
        # na hora, funciona sem internet, e sobra cota para o que é do momento
        # (leitura de gráfico, notícia, análise da posição de agora).
        # ...MENOS quando ele acabou de dizer que a resposta anterior não
        # serviu. Aí a base já falhou uma vez: insistir devolve o mesmo texto.
        if pergunta_sobre_capacidades(texto):
            self._chat_responder(texto_das_capacidades(), falar_tb=False,
                                  texto_voz="Eu executo os comandos da mesa, "
                                            "busco cotação e notícia na "
                                            "internet, respondo metodologia e "
                                            "macro de cabeça, analiso os prints "
                                            "do gráfico e aprendo as regras que "
                                            "você me ensina.")
            return
        if pergunta_conceitual(texto) and not e_correcao_do_trader(texto):
            # A leitura do cenário toca a rede (cotação real), então sai da
            # thread da interface — senão a janela congela por alguns segundos.
            if buscar_base_smc(texto):
                self._chat_ocupada = True
                self._chat_status("🔎 lendo o seu cenário…", "#ff9f43")
                threading.Thread(target=self._responder_com_cenario,
                                 args=(texto,), daemon=True).start()
                return
        # Conversa livre -> modelo
        if self._chat_ocupada:
            self._chat_escrever("sistema", "(aguarde — ainda estou respondendo a anterior)",
                                 persistir=False)
            return
        self._chat_ocupada = True
        self._chat_status("✳ pensando…", "#ff9f43")
        threading.Thread(target=self._chat_worker, args=(texto,), daemon=True).start()

    def _chat_feed(self, texto):
        """Evento da mesa entra na CONVERSA (sugestão nova, entrada executada,
        stop/alvo). É o que deixa a IA interativa em tempo integral: o aviso
        chega no chat e você responde ali mesmo — por texto ou voz."""
        def escrever():
            try:
                self._chat_escrever("ia", texto)
            except Exception:
                registrar_msg_chat("ia", texto)
        self.after(0, escrever)

    def _chat_responder(self, texto, falar_tb=True, texto_voz=None):
        """Resposta imediata (sem modelo): digita no terminal + voz.
        REGRA: se o pedido veio por VOZ, a resposta SEMPRE sai por voz também
        (com o registro em texto no histórico) — independente do checkbox 🔊.
        `texto_voz` permite falar uma versão natural do que está escrito (o card
        de status, por exemplo, é ótimo na tela e horrível lido em voz alta)."""
        registrar_msg_chat("ia", texto)
        self._chat_digitar(texto)
        if texto_voz == "":
            return                 # resposta muda de propósito (ex.: 'cala')
        dito = texto_voz or texto
        if getattr(self, "_chat_por_voz", False):
            self._ia_falar(dito, forcar=True)
        elif falar_tb:
            self._ia_falar(dito)

    def _responder_com_cenario(self, texto):
        """Resposta local COM leitura da mesa. Roda fora da interface porque
        busca o preço real na web."""
        try:
            local = responder_offline(texto, self._cenario_da_mesa(texto))
        except Exception:
            local = responder_do_conhecimento(texto)
        if not local or local == getattr(self, "_ultima_resposta_local", None):
            # Sem resposta nova aqui, o turno segue para o modelo em vez de
            # repetir o que ele acabou de ler.
            self.after(0, lambda: self._chat_status("✳ pensando…", "#ff9f43"))
            threading.Thread(target=self._chat_worker, args=(texto,),
                             daemon=True).start()
            return
        self._ultima_resposta_local = local
        self._chat_ocupada = False
        self.after(0, lambda: self._chat_responder(local))

    def _cenario_da_mesa(self, pergunta=""):
        """Fotografia do que está acontecendo AGORA, para a resposta deixar de
        ser de manual: posição aberta, última leitura do gráfico, sugestão
        pendente, ritmo exigido e o preço real do ativo citado.

        Tudo aqui é dado REAL da ferramenta ou da web — nada é estimado."""
        cenario = {}
        try:
            for p in posicoes_do_ciclo():
                if p.get("status") == "ABERTA":
                    cenario["posicao"] = p
                    break
        except Exception:
            pass
        # LEITURA DO MOTOR DO ATIVO QUE ELE OPERA — não a do último ativo
        # analisado. Sem isto, com posição no MES e o motor tendo acabado de
        # ler o ouro, a resposta sobre "minha operação" vinha com o ouro.
        cenario["analise"] = getattr(self, "_ultima_analise", None) or {}
        _ativo_foco = ((cenario.get("posicao") or {}).get("ativo") or "").upper()
        if not _ativo_foco:
            _alvo_txt = simbolo_do_texto(pergunta)
            _ativo_foco = (_alvo_txt[1].upper() if _alvo_txt else "")
        if _ativo_foco:
            _porativo = getattr(self, "_analises_por_ativo", {}) or {}
            for _k, _v in _porativo.items():
                if _k == _ativo_foco or _ativo_foco in _k or _k in _ativo_foco:
                    cenario["analise"] = _v
                    break
        try:
            cenario["pendente"] = self._ultimo_sinal_pendente()
        except Exception:
            cenario["pendente"] = None
        try:
            stats = self._computar_stats_plano()
            cenario["ritmo_dia"] = stats.get("meta_diaria")
            cenario["falta"] = stats.get("falta")
            cenario["dias_restantes"] = stats.get("dias_restantes")
        except Exception:
            pass
        cenario["motor"] = bool(getattr(self, "motor_rodando", False) or
                                getattr(self, "robo_ativo", False))
        # Preço real: do ativo que ele citou, ou do que ele está operando.
        alvo = simbolo_do_texto(pergunta)
        if not alvo:
            ativo = (cenario.get("posicao") or {}).get("ativo") or \
                    cenario["analise"].get("ativo") or ""
            alvo = simbolo_do_texto(ativo) if ativo else None
        if alvo:
            try:
                cenario["cotacao"] = cotacao_mercado(alvo[0]) or {}
                cenario["ativo_nome"] = alvo[1].upper()
            except Exception:
                pass
        return cenario

    # ---------------- Janela para a web (sem chave de API) ----------------
    def _chat_web(self, acao, texto):
        """Notícia, cotação e busca — a ferramenta vai à internet SOZINHA.

        Nada aqui passa pela Gemini: é o `requests` do próprio app batendo em
        RSS público e no Yahoo Finance. Por isso funciona com a cota estourada,
        e por isso o número é REAL — ela cita a fonte e a hora, em vez de
        responder de cabeça como fazia antes ("o S&P sobe por causa da
        inflação", sem ter visto manchete nenhuma)."""
        try:
            self.after(0, lambda: self._chat_status("🌐 buscando na internet…",
                                                     "#79c0ff"))
            if acao == "COTACAO":
                self._chat_web_cotacao(texto)
            elif acao == "NOTICIAS":
                self._chat_web_noticias(texto)
            else:
                self._chat_web_pesquisa(texto)
        except Exception as e:
            self._chat_entregar_resposta(
                "Não consegui buscar na internet agora. Confira a conexão e me "
                f"peça de novo. (detalhe técnico: {str(e)[:120]})")

    def _chat_web_cotacao(self, texto):
        alvo = simbolo_do_texto(texto)
        cot = cotacao_mercado(alvo[0]) if alvo else None
        if not cot:
            self._chat_entregar_resposta(
                "Não consegui puxar essa cotação agora — ou o ativo não está na "
                "minha lista, ou a internet falhou. Eu acompanho S&P, Nasdaq, "
                "Dow, Russell, VIX, ouro, prata, petróleo, dólar, euro, "
                "bitcoin, Ibovespa e juros de 10 anos. Não vou chutar um número.")
            return
        self._chat_entregar_resposta(formatar_cotacao(cot, alvo[1].upper()))

    def _chat_web_noticias(self, texto):
        alvo = simbolo_do_texto(texto)
        cot = cotacao_mercado(alvo[0]) if alvo else None
        resumo = resumo_de_noticias(texto)
        if not resumo and not cot:
            self._chat_entregar_resposta(
                "Não consegui alcançar as fontes de notícia agora — parece "
                "internet. Prefiro dizer isso a inventar um motivo para o "
                "movimento. Tente de novo em instantes.")
            return
        partes = []
        if cot:
            partes.append(formatar_cotacao(cot, alvo[1].upper()))
        if resumo:
            partes.append(resumo)
        self._chat_entregar_resposta("\n".join(partes))

    def _chat_web_pesquisa(self, texto):
        # Tira as palavras de comando para sobrar só o assunto.
        consulta = re.sub(r"\b(pesquis\w*|busc\w*|procur\w*|na internet|no google|"
                          r"pra mim|para mim|por favor|sobre|d[áa] uma olhada)\b",
                          " ", texto, flags=re.IGNORECASE)
        consulta = re.sub(r"\s+", " ", consulta).strip(" ,.?!")
        if len(consulta) < 3:
            self._chat_entregar_resposta("Pesquisar o quê? Me diga o assunto — "
                                          "por exemplo: 'pesquisa na internet "
                                          "sobre a decisão do Fed de hoje'.")
            return
        # NÃO É TODA FRASE COM "PESQUISAR" QUE É UM PEDIDO DE PESQUISA.
        # Log de 12/08, 21:38. Ele escreveu:
        #     "VOCE CONSEGUE SIM, VOCE TEM CAPACIDADE PARA ISSO... É SÓ VOCE
        #      PESQUISAR E APRENDER"
        # Aquilo era uma OPINIÃO sobre ela, não um assunto para buscar. A
        # palavra 'pesquisar' bastou para virar consulta — e a resposta foi
        # uma lista de resultados da Lotofácil e balanços de empresas.
        # Frase DIRIGIDA A ELA não é termo de busca.
        if re.search(r"\bvoc[êe]s?\b|\bte\b|\bti\b", consulta, re.I) or \
                len(consulta.split()) > 12:
            self._chat_entregar_resposta(
                "Isso soou como uma frase para mim, não como um assunto para "
                "eu pesquisar — e eu não quero jogar manchete aleatória na sua "
                "tela. Se for para buscar, me diga o TERMO: 'pesquisa a "
                "decisão do Fed de hoje', por exemplo.")
            return
        achados = buscar_na_web(consulta)
        if not achados:
            # ANTES, quando a busca falhava, ela despejava as manchetes do dia
            # — que não tinham NADA a ver com o que foi perguntado. Foi assim
            # que "é só você pesquisar e aprender" devolveu o resultado da
            # Lotofácil e o balanço da Copasa. Manchete sem relação com a
            # pergunta não é resposta parcial: é ruído com cara de resposta.
            # Agora só entram as que casam com alguma palavra da consulta.
            termos = {p.lower() for p in re.findall(r"\w{4,}", consulta)}
            noticias = [n for n in (noticias_do_mercado(maximo=8, termo=consulta) or [])
                        if termos & set(re.findall(r"\w{4,}", n["titulo"].lower()))]
            if noticias:
                linhas = "\n".join(f"• [{n['fonte']} · {_idade_texto(n['quando'])}] "
                                   f"{n['titulo']}" for n in noticias[:5])
                self._chat_entregar_resposta(
                    f"A busca aberta não respondeu agora, mas achei isso nas "
                    f"fontes de mercado sobre “{consulta}”:\n{linhas}")
                return
            self._chat_entregar_resposta(
                f"Não consegui pesquisar “{consulta}” agora — a busca não "
                "respondeu. Não vou responder de cabeça para não te passar "
                "informação inventada. Tente de novo em instantes; se for "
                "assunto de mercado, posso trazer as manchetes das casas.")
            return
        linhas = [f"O que encontrei na internet sobre “{consulta}”:"]
        for a in achados:
            linhas.append(f"• {a['titulo']}" +
                          (f" — {a['resumo']}" if a['resumo'] else ""))
        linhas.append("Fontes acima, não interpretação minha. Quer que eu ligue "
                      "isso ao seu cenário no gráfico?")
        self._chat_entregar_resposta("\n".join(linhas))

    # ---------------- Mão no motor (ação real, não conversa) ----------------
    def _chat_motor(self, ligar):
        """Liga/desliga o MOTOR de análise a pedido do trader.

        POR QUE É CÓDIGO E NÃO CONVERSA: pedindo ao modelo, ele respondia
        "motor ligado" sem ligar coisa alguma — alucinação com custo real (o
        trader achava que estava sendo monitorado e não estava). Aqui quem liga
        é a mesma função do botão da aba Motor, e o que ela responde é o que de
        fato aconteceu."""
        ligado = bool(getattr(self, "motor_rodando", False) or
                      getattr(self, "robo_ativo", False))
        if ligar:
            if ligado:
                self._chat_responder("O motor já está ligado — sigo analisando o "
                                      "gráfico a cada ciclo. Se quiser, digo o status.")
                return
            chave = ""
            try:
                chave = limpar_chave_colada(self.api_entry.get()) or carregar_api_key()
            except Exception:
                chave = carregar_api_key()
            if not chave:
                self._chat_responder(
                    "Não consigo ligar sem a chave da Gemini: vá na aba Motor, "
                    "cole a chave da API no campo dela e peça de novo que eu ligo.")
                return
            janela = carregar_config().get("nome_janela_corretora", "").strip()
            alvo = f"a janela '{janela}'" if janela else "a tela inteira (nenhuma janela escolhida na aba Motor)"
            self._chat_responder(f"Ligando o motor agora — vou analisar {alvo}. "
                                  "Te aviso assim que ele estiver de pé.")
            self.after(0, self.iniciar)
            threading.Thread(target=self._confirmar_motor, args=(True,),
                             daemon=True).start()
            return
        if not ligado:
            self._chat_responder("O motor já está desligado — nenhuma análise "
                                  "rodando. Suas posições e o histórico seguem salvos.")
            return
        self._chat_responder("Desligando o motor. Paro as análises e os "
                              "relatórios; as posições abertas continuam "
                              "registradas no dashboard.")
        self.after(0, self.desligar)
        threading.Thread(target=self._confirmar_motor, args=(False,),
                         daemon=True).start()

    def _chat_zerar_ciclo(self):
        """Zera o ciclo da conta ativa — o MESMO efeito do botão 'Reiniciar
        Ciclo' do Plano de Trading, só que pelo chat.

        Ela dizia "acabei de resetar os dados da Conta 1" e o dashboard
        continuava igual, porque nada era executado. Agora quem zera é este
        código, e a confirmação só é escrita DEPOIS de reler o plano do disco.
        """
        try:
            antes = dict(plano_da_conta_ativa() or {})
            agora = datetime.datetime.now()
            self.plano["data_inicio"] = agora.date().isoformat()
            self.plano["ciclo_inicio"] = agora.isoformat(timespec="seconds")
            # CICLO NOVO ZERA O DIA ESCOLHIDO À MÃO. A âncora diz "naquela data
            # era o dia N"; com um ciclo novo ela aponta para um ciclo que não
            # existe mais, e o dashboard abriria no dia 4 de um ciclo que
            # começou agora.
            self.plano["dia_ciclo_ancora"] = None
            salvar_plano_da_conta(self.plano)
            # PROVA: relê do disco. Se o arquivo não mudou, ela NÃO diz que zerou.
            depois = plano_da_conta_ativa() or {}
            if depois.get("ciclo_inicio") != self.plano["ciclo_inicio"]:
                raise RuntimeError("o plano não gravou o novo ciclo")
            self.after(0, lambda: self._atualizar_dashboard(forcar=True))
            self.log(f"🔄 Ciclo zerado pela TIGER em "
                     f"{agora.strftime('%d/%m/%Y %H:%M:%S')} para a conta "
                     f"'{nome_conta_ativa()}' (histórico preservado).")
            anterior = antes.get("data_inicio") or "—"
            self._chat_responder(
                f"Pronto, zerei o ciclo da conta '{nome_conta_ativa()}' agora "
                f"({agora.strftime('%d/%m %H:%M')}). O dashboard começa do zero: "
                f"resultado, gráficos e a contagem de "
                f"{dias_meta_do_plano(self.plano)} dia(s) recomeçam hoje — o "
                f"ciclo anterior tinha começado em {anterior} e continua "
                "arquivado no histórico. Confere no Plano de Trading que já "
                "mudou.")
        except Exception as e:
            self._chat_responder(
                f"NÃO consegui zerar o ciclo — o dashboard continua como está. "
                f"Motivo: {str(e)[:150]}. Dá para zerar na mão pelo botão "
                "'Reiniciar Ciclo', na aba Plano de Trading.")

    # ---------------- A IA MEXE NA CONFIGURAÇÃO (autorizado) ----------------
    @staticmethod
    def _mesmo_valor(a, b):
        """Compara o que foi pedido com o que ficou no disco. Número é
        comparado como número (1 e 1.0 são o mesmo valor)."""
        na, nb = _num(a), _num(b)
        if na is not None and nb is not None:
            return abs(na - nb) < 1e-9
        return str(a).strip() == str(b).strip()

    def _chat_definir_niveis(self, texto):
        """'o stop do MESU6 é 7760 e o alvo é 7800' — o trader completando o
        bracket de uma posição que a plataforma reportou sem níveis.

        Mesma regra da casa da configuração: GRAVA, RELÊ DO DISCO e só então
        confirma. E não escolhe posição por adivinhação: se ele não disse o
        ativo e há mais de uma posição aberta, PERGUNTA qual."""
        abertas = [p for p in posicoes_do_ciclo()
                   if p.get("status") in ("ABERTA", "PENDENTE")]
        if not abertas:
            self._chat_responder(
                "Não há posição aberta nem ordem pendente nesta conta para eu "
                "anexar esses níveis. Se você acabou de entrar na plataforma, "
                "espere o próximo ciclo do motor detectar a posição e me diga de novo.")
            return
        dados = interpretar_niveis_da_posicao(
            texto, [p.get("ativo") for p in abertas])
        if not dados:
            self._chat_responder(
                "Entendi que você quer definir stop/alvo, mas não achei o número "
                "na frase. Diga assim: 'o stop do MESU6 é 7760 e o alvo é 7800'.")
            return
        if dados["ativo"]:
            escolhidas = [p for p in abertas
                          if str(p.get("ativo", "")).upper() == dados["ativo"]]
        elif len(abertas) == 1:
            escolhidas = abertas
        else:
            nomes = ", ".join(sorted({str(p.get("ativo")) for p in abertas}))
            self._chat_responder(
                f"Você tem posição em mais de um ativo agora ({nomes}) e não "
                "disse de qual. Repita citando o ativo — por exemplo: 'o stop "
                f"do {nomes.split(',')[0].strip()} é {dados['stop'] or 7760:g}'. "
                "Não vou chutar em qual posição mexer.")
            return
        if not escolhidas:
            self._chat_responder(
                f"Não encontrei posição aberta de {dados['ativo']} nesta conta.")
            return

        lista = carregar_posicoes()
        ids = {p["id"] for p in escolhidas}
        for p in lista:
            if p.get("id") in ids:
                if dados["stop"] is not None:
                    p["stop"] = dados["stop"]
                if dados["tp1"] is not None:
                    p["tp1"] = dados["tp1"]
                p["niveis_informados"] = True   # veio do trader, não da leitura
        salvar_posicoes(lista)

        # RELÊ DO DISCO — é isso que separa "gravei" de "disse que gravei".
        confirmadas = [p for p in carregar_posicoes() if p.get("id") in ids]
        linhas = []
        for p in confirmadas:
            risco = None
            _e, _s = _num(p.get("entry")), _num(p.get("stop"))
            if _e is not None and _s is not None:
                risco = round(abs(_e - _s) * (p.get("vpp") or
                              valor_por_ponto_do_ativo(p.get("ativo"))) *
                              int(p.get("contratos") or 1), 2)
            linhas.append(
                f"• {p.get('direcao')} {p.get('ativo')} "
                f"{p.get('contratos')} contrato(s) @ {p.get('entry')} · "
                f"stop {p.get('stop') if p.get('stop') is not None else '—'} · "
                f"alvo {p.get('tp1') if p.get('tp1') is not None else '—'}"
                + (f" · risco até o stop US${risco:,.2f}" if risco is not None else ""))
        self.after(0, self._atualizar_dashboard)
        self._chat_responder(
            "Gravado. Reli do disco e ficou assim:\n" + "\n".join(linhas) +
            "\n\nAgora eu consigo calcular o risco em US$ dessa posição e te "
            "avisar quando a estrutura virar contra ela.")

    def _chat_configurar(self, mudancas, texto=""):
        """Configura a PRÓPRIA ferramenta a pedido dele — horário do pregão,
        intervalo das análises e os números do Plano de Trading da conta.

        Ele autorizou explicitamente ("mediante solicitação, autonomia para
        configurar e editar"). Mesmo assim vale a regra da casa: GRAVA, RELÊ DO
        DISCO e só então confirma, mostrando de-para. O que não gravou, ela diz
        que não gravou."""
        if not mudancas:
            return
        contas = carregar_contas()
        alvo = conta_por_referencia(texto, contas) or conta_ativa() or \
            (contas[0] if contas else None)
        nome_alvo = (alvo or {}).get("nome", "conta ativa")
        cfg_antes = carregar_config()
        plano_antes = dict(PLANO_PADRAO)
        plano_antes.update((alvo or {}).get("plano_trading") or {})
        novo_cfg, novo_plano = {}, dict(plano_antes)
        for m in mudancas:
            if m["destino"] == "config":
                m["antes"] = cfg_antes.get(m["campo"],
                                           PADRAO_CONFIG_APP.get(m["campo"]))
                novo_cfg[m["campo"]] = m["valor"]
            else:
                m["antes"] = plano_antes.get(m["campo"], PLANO_PADRAO.get(m["campo"]))
                novo_plano[m["campo"]] = m["valor"]
        try:
            if novo_cfg:
                salvar_config(novo_cfg)
            if novo_plano != plano_antes:
                if not alvo:
                    raise RuntimeError("nenhuma conta cadastrada para receber o plano")
                salvar_plano_da_conta(novo_plano, alvo["id"])
        except Exception as e:
            self._chat_responder(
                f"NÃO consegui gravar a configuração — está tudo como estava. "
                f"Motivo: {str(e)[:150]}. Dá para ajustar na mão: horário e "
                "intervalo na aba Motor, e os números na aba Plano de Trading.")
            return
        # PROVA: relê do disco. O que não bater aqui NÃO é dito como feito.
        cfg_lido = carregar_config()
        plano_lido = {}
        for c in carregar_contas():
            if alvo and c.get("id") == alvo.get("id"):
                plano_lido = dict(PLANO_PADRAO)
                plano_lido.update(c.get("plano_trading") or {})
        aplicadas, falhas = [], []
        for m in mudancas:
            lido = cfg_lido.get(m["campo"]) if m["destino"] == "config" \
                else plano_lido.get(m["campo"])
            (aplicadas if self._mesmo_valor(lido, m["valor"]) else falhas).append(m)
        self.after(0, lambda: self._refletir_config_na_tela(aplicadas, alvo))
        for m in aplicadas:
            self.log(f"⚙️ TIGER configurou {m['rotulo']}: "
                     f"{formatar_valor_config(m['campo'], m.get('antes'))} → "
                     f"{formatar_valor_config(m['campo'], m['valor'])}"
                     + (f" (conta '{nome_alvo}')" if m["destino"] == "plano" else ""))
        if not aplicadas:
            self._chat_responder(
                "NÃO consegui aplicar a configuração: gravei e, ao reler o "
                "arquivo, o valor continuava o antigo. Prefiro te dizer isso a "
                "dizer que fiz. Ajuste na mão — horário e intervalo na aba "
                "Motor, os números na aba Plano de Trading.")
            return
        linhas = [f"• {m['rotulo']}: era "
                  f"{formatar_valor_config(m['campo'], m.get('antes'))}, "
                  f"agora é {formatar_valor_config(m['campo'], m['valor'])}"
                  for m in aplicadas]
        corpo = ["Pronto, configurei a ferramenta:", "\n".join(linhas)]
        # Pregão que VIRA O DIA (19:00 → 17:59) é o caso dele. Sem explicar,
        # a confirmação parecia erro — ele respondeu "NÃO ENTENDI".
        novos = {m["campo"]: m["valor"] for m in aplicadas}
        h_ini = novos.get("hora_inicio", cfg_lido.get("hora_inicio"))
        h_fim = novos.get("hora_fim", cfg_lido.get("hora_fim"))
        if h_ini and h_fim and str(h_ini) > str(h_fim):
            corpo.append(f"Reparei que o seu pregão VIRA O DIA: começa às "
                         f"{h_ini} e só termina às {h_fim} do dia seguinte. "
                         "Está tratado assim — o motor analisa a noite inteira "
                         "e a madrugada, sem pular ciclo na virada.")
        if any(m["destino"] == "plano" for m in aplicadas):
            corpo.append(f"O que é do plano ficou gravado na conta '{nome_alvo}'.")
        if any(m["destino"] == "config" for m in aplicadas):
            aviso = ("O horário e o intervalo são da FERRAMENTA, não de uma "
                     "conta só — o motor é um só, então valem para todas as "
                     "contas.")
            if getattr(self, "motor_rodando", False) or getattr(self, "robo_ativo", False):
                aviso += " Como o motor está ligado, passa a valer no próximo ciclo."
            corpo.append(aviso)
        if falhas:
            corpo.append("Não consegui aplicar: " +
                         ", ".join(m["rotulo"] for m in falhas) +
                         ". Esses continuam como estavam.")
        corpo.append("Já reli o arquivo para conferir — é isso que está "
                     "gravado. Confere na tela; se quiser voltar, me diga o "
                     "valor antigo que eu reconfiguro.")
        voz = ("Configurei: " +
               "; ".join(f"{m['rotulo']} agora é "
                         f"{formatar_valor_config(m['campo'], m['valor'])}"
                         for m in aplicadas) + ".")
        self._chat_responder("\n\n".join(corpo), falar_tb=False, texto_voz=voz)

    def _refletir_config_na_tela(self, mudancas, alvo=None):
        """Leva a mudança para os campos da interface. Sem isso, o valor certo
        estaria no arquivo e o antigo continuaria na tela — e o botão Ligar
        regravaria o antigo por cima."""
        try:
            valores = {m["campo"]: m["valor"] for m in mudancas}
            for campo, attr in (("hora_inicio", "entry_hora_inicio"),
                                ("hora_fim", "entry_hora_fim")):
                widget = getattr(self, attr, None)
                if campo in valores and widget is not None:
                    widget.delete(0, tk.END)
                    widget.insert(0, str(valores[campo]))
            if "intervalo_minutos" in valores and hasattr(self, "intervalo_vivo_var"):
                self.intervalo_vivo_var.set(str(int(valores["intervalo_minutos"])))
            if any(m["destino"] == "plano" for m in mudancas) and \
                    alvo and alvo.get("id") == conta_ativa_id():
                self._aplicar_conta_na_tela()
        except Exception as e:
            self.log(f"⚠️ Configuração gravada, mas a tela não recarregou: {e}")

    def _chat_ver_configuracao(self, texto=""):
        """'Como está configurado o risco do plano da conta 1' — lê do disco e
        mostra. Ela tinha esse dado na mão e respondia 'não sei'."""
        contas = carregar_contas()
        alvo = conta_por_referencia(texto, contas) or conta_ativa() or \
            (contas[0] if contas else None)
        plano = dict(PLANO_PADRAO)
        plano.update((alvo or {}).get("plano_trading") or {})
        campos = campos_citados(texto)
        resumo = resumo_da_configuracao(carregar_config(), plano,
                                        (alvo or {}).get("nome", ""), campos)
        curtos = campos or ["risco_pct", "meta_alvo", "hora_inicio", "hora_fim"]
        voz = "; ".join(
            f"{ROTULO_CONFIG[c]}: "
            f"{formatar_valor_config(c, (carregar_config() if DESTINO_CONFIG.get(c) == 'config' else plano).get(c, PADRAO_CONFIG_APP.get(c, PLANO_PADRAO.get(c))))}"
            for c in curtos if c in ROTULO_CONFIG)
        self._chat_responder(resumo, falar_tb=False, texto_voz=voz)

    # Intervalo mínimo entre dois alertas do MESMO tipo para a MESMA posição.
    # O motor roda a cada poucos minutos; sem isto o aviso viraria ruído e ele
    # pararia de ler justamente o alerta que importa.
    INTERVALO_ALERTA_CONTRA_SEG = 15 * 60

    def _alertar_cenario_contra_posicao(self, pos, acao, ativo, preco,
                                        probabilidade, confluencias, stop_cenario):
        """O mercado virou contra a posição que ele já tem. Isto NÃO é sugestão
        de entrada — é aviso de gestão, e é a coisa mais útil que a ferramenta
        pode dizer para quem está dentro de uma operação.

        Antes esse cenário simplesmente sumia: a instrução no prompt fazia o
        modelo devolver HOLD, e ele ficava sem saber que a leitura mudou de lado.
        """
        chave = (pos.get("id"), acao)
        agora = time.time()
        ultimo = getattr(self, "_ultimo_alerta_contra", (None, 0))
        if ultimo[0] == chave and (agora - ultimo[1]) < self.INTERVALO_ALERTA_CONTRA_SEG:
            return
        self._ultimo_alerta_contra = (chave, agora)

        direcao_pos = pos.get("direcao")
        contratos = pos.get("contratos") or 0
        entrada = pos.get("entry")
        pnl = pos.get("pnl_atual")
        linha_pnl = (f"Resultado agora: US${pnl:+,.2f}." if isinstance(pnl, (int, float))
                     else "Resultado atual: a plataforma não informou.")
        stop_pos = pos.get("stop")
        linha_stop = (f"Seu stop está em {stop_pos}."
                      if stop_pos else
                      "⚠️ Não há stop registrado para essa posição — se ainda não "
                      "colocou na plataforma, é a primeira coisa a fazer.")
        conf = " · ".join(list(confluencias)[:4]) if confluencias else "—"

        texto = (
            f"⚠️ *A LEITURA VIROU CONTRA A SUA POSIÇÃO*\n"
            f"Você está {direcao_pos} {ativo}"
            + (f" ({contratos} contrato(s) @ {entrada})" if contratos else "")
            + f".\nO gráfico agora aponta {acao} em {preco} "
            f"(probabilidade {probabilidade:.0f}%).\n"
            f"{linha_pnl}\n{linha_stop}\n"
            f"Leitura: {conf}\n"
            "NÃO vou sugerir entrada na direção oposta — isso seria hedge, não "
            "operação. A decisão é sua: proteger, reduzir, encerrar, ou segurar "
            "porque o seu plano previa esse repique."
        )
        self.log(f"⚠️ CENÁRIO CONTRA A POSIÇÃO ABERTA: você está {direcao_pos} "
                 f"{ativo} e a leitura virou {acao} @ {preco} "
                 f"(prob. {probabilidade:.0f}%). {linha_stop}")
        self._notificar_desktop(
            f"⚠️ Leitura virou contra sua posição — {ativo}",
            [f"Você está {direcao_pos}" + (f" ({contratos} ctr)" if contratos else ""),
             f"O gráfico agora aponta {acao} em {preco}",
             linha_stop],
            cor="#d97706")
        try:
            enviar_relatorio_whatsapp(texto, None, self.log)
        except Exception:
            pass
        self._chat_feed(texto.replace("*", ""))

    def _previsualizar_janela(self):
        """Captura a janela selecionada e mostra a miniatura, com o veredito.

        Roda em thread: capturar janela pode levar segundos e travar a
        interface no meio seria pior que não ter o recurso."""
        nome = (self.janela_var.get() or "").strip()
        self.lbl_previa.configure(text="capturando…", text_color="#ff9f43")
        threading.Thread(target=self._previa_worker, args=(nome,),
                         daemon=True).start()

    def _previa_worker(self, nome):
        try:
            if not nome or nome.startswith("("):
                self.after(0, lambda: self.lbl_previa.configure(
                    text="Escolha uma janela na lista acima primeiro.",
                    text_color="#e0a458"))
                return
            hwnd = self._resolver_hwnd_corretora(nome)
            imagem = (capturar_janela_em_segundo_plano(hwnd) if hwnd
                      else plataforma.capturar_tela_inteira())
            if imagem is None or imagem_esta_em_branco(imagem):
                self.after(0, lambda: self.lbl_previa.configure(
                    text="Não consegui uma imagem desta janela. Ela pode estar "
                         "minimizada ou totalmente coberta.", text_color="#ff6b6b"))
                return
            # O MESMO OCR que responde 'onde está a VWAP'. Se ele acha os
            # rótulos de um gráfico aqui, a janela é a certa — e isso é um
            # veredito, não um palpite sobre o título.
            achados = {}
            try:
                import tempfile
                caminho = os.path.join(tempfile.gettempdir(), "smc_previa.png")
                imagem.save(caminho)
                achados = ler_indicadores_da_legenda(
                    plataforma.ler_texto_da_imagem(caminho))
            except Exception:
                achados = {}
            larg = 460
            copia = imagem.copy()
            copia.thumbnail((larg, int(larg * 0.62)))
            foto = ctk.CTkImage(light_image=copia, dark_image=copia,
                                size=copia.size)
            if achados:
                nomes = ", ".join(sorted(achados)[:6])
                veredito = (f"✅ É um gráfico — li nesta janela: {nomes}.", "#4ade80")
            else:
                veredito = ("⚠️ Não achei legenda de indicador nesta janela. "
                            "Confira se é mesmo o gráfico (e se a legenda está "
                            "visível na tela).", "#e0a458")

            def mostrar():
                self.img_previa.configure(image=foto)
                self.img_previa.image = foto      # sem isto o Tk descarta a imagem
                self.lbl_previa.configure(text=veredito[0], text_color=veredito[1])
            self.after(0, mostrar)
        except Exception as e:
            msg = str(e)[:110]
            self.after(0, lambda: self.lbl_previa.configure(
                text=f"Falha ao pré-visualizar: {msg}", text_color="#ff6b6b"))

    def _chat_virar_dia(self):
        """Vira o dia de operação AGORA — o comando que ele pediu duas vezes.

        Na prática quase nunca é preciso: desde esta versão o dia vira sozinho
        no horário configurado (data_do_pregao). Este comando existe para o
        caso em que ele quer recomeçar a contagem ANTES da hora — encerrar o
        dia mais cedo e zerar o freio.

        NÃO apaga nada. As operações continuam no diário; o que muda é a
        marca de onde este dia começou. Apagar histórico para destravar um
        freio seria trocar uma trava de gestão por uma amnésia."""
        antes = len(operacoes_fechadas_hoje())
        agora = datetime.datetime.now()
        salvar_config({"virada_manual": agora.strftime('%d/%m/%Y %H:%M')})
        gravado = carregar_config().get("virada_manual")
        if gravado != agora.strftime('%d/%m/%Y %H:%M'):
            self._chat_responder(
                "NÃO consegui gravar a virada do dia — o arquivo de "
                "configuração não aceitou a mudança. Nada mudou; prefiro te "
                "dizer isso a confirmar uma coisa que não aconteceu.")
            return
        depois = len(operacoes_fechadas_hoje())
        self.log(f"📅 TIGER virou o dia de operação em {gravado} — "
                 f"contagem do freio: {antes} → {depois} operação(ões).")
        self.after(0, self._atualizar_dashboard)
        self._chat_responder(
            f"📅 Pronto: o dia de operação virou agora, às "
            f"{agora.strftime('%H:%M')}.\n\n"
            f"• Operações contando para o freio: era {antes}, agora é {depois}.\n"
            f"• O seu histórico NÃO foi apagado — as {antes} operações "
            "continuam no diário e no relatório. O que mudou foi só onde "
            "este dia começa.\n\n"
            + texto_do_pregao_atual())

    def _chat_estado_do_freio(self):
        """'Por que você não está sugerindo nada?' — responde com os números
        reais do dia, lidos do diário. Quando o FREIO está segurando as
        sugestões, ele precisa saber que é proteção, e não travamento."""
        plano = plano_da_conta_ativa()
        pode, motivo = freio_de_sugestoes(plano)
        fechadas = operacoes_fechadas_hoje()
        realizado = sum(p["pnl_final"] for p in fechadas)
        perdas = sum(1 for p in fechadas if p["pnl_final"] < 0)

        linhas = [
            f"Hoje na conta '{nome_conta_ativa()}': {len(fechadas)} operação(ões) "
            f"fechada(s), {perdas} no prejuízo, resultado US${realizado:+,.2f}."
        ]
        if pode:
            linhas.append(
                "O freio NÃO está segurando nada — estou livre para sugerir. Se "
                "não saiu cenário, é porque nenhum passou no piso de qualidade "
                f"(R:R mínimo 1:{plano.get('rr_minimo', 2.0):g} e probabilidade "
                f"mínima {plano.get('probabilidade_minima', 55):g}%), ou o motor "
                "está desligado.")
        else:
            linhas.append(f"🛑 O FREIO ESTÁ ATIVO: {motivo}")

        # O NÚMERO QUE FALTAVA: quantos cenários o piso barrou e por quanto.
        # Sem isto a resposta era teórica ("é porque nenhum passou no piso") e o
        # trader não tinha como saber se o piso está calibrado para o mercado
        # de hoje. Vem do contador do motor, não de estimativa.
        descartes = getattr(self, "_descartes_qualidade", None) or {}
        if descartes:
            detalhe = " · ".join(
                f"{chave}: {d['n']} descarte(s), melhor R:R 1:{d['melhor_rr']:.2f}, "
                f"melhor probabilidade {d['melhor_prob']:.0f}%"
                for chave, d in sorted(descartes.items()))
            linhas.append(
                "O que o piso barrou desde que o motor ligou — " + detalhe + ". "
                "Compare com os seus pisos acima: se o melhor R:R do dia ficou "
                "sempre perto do seu mínimo, o mercado está lateral e o certo é "
                "ficar de fora; se ficou muito longe, o problema é a leitura, "
                "não o piso.")
        linhas.append(
            f"Seus limites de hoje: pausa após {plano.get('max_stops_seguidos', 2)} "
            f"stops seguidos por {plano.get('cooldown_stop_min', 30)} min · teto de "
            f"{plano.get('max_operacoes_dia', 6)} operações no dia · drawdown "
            f"US${float(plano.get('drawdown_maximo', 0) or 0):,.2f}. "
            "Qualquer um deles eu mudo na hora, é só pedir.")
        self._chat_responder("\n".join(linhas), falar_tb=True,
                             texto_voz=linhas[1])

    def _chat_enviar_whatsapp(self):
        """Manda para o WhatsApp pelo MOTOR — que é quem tem a ponte.

        Ela respondeu "acabei de reenviar os detalhes para o seu WhatsApp" sem
        enviar nada. Agora ou o disparo acontece, ou ela diz exatamente por que
        não aconteceu (motor desligado é o caso mais comum)."""
        if not (getattr(self, "motor_rodando", False) or
                getattr(self, "robo_ativo", False)):
            self._chat_responder(
                "Não dá para enviar: quem fala com o WhatsApp é o motor, e ele "
                "está DESLIGADO. Diga 'liga o motor', espere ele subir e me "
                "peça de novo que eu disparo.")
            return
        # "ENVIA O PRINT NO WHATSAPP" mandava só texto — e, quando não havia
        # sugestão, respondia "não tenho nada para enviar" com a imagem do
        # gráfico salva no disco ali do lado. Se ele pediu o PRINT, vai o print.
        pedido = str(getattr(self, "_ultimo_pedido", "") or "")
        quer_imagem = bool(re.search(
            r"\b(print|imagem|foto|captura|screenshot|gr[áa]fico|tela)\b",
            pedido, re.IGNORECASE))
        info = getattr(self, "_ultimo_print", None)
        idade = idade_do_ultimo_print(info)
        imagem = None
        if quer_imagem and idade is not None:
            try:
                imagem = Image.open(info["caminho"])
            except Exception as e:
                self.log(f"(não consegui abrir o último print para enviar: {e})")

        texto = self._resumo_para_whatsapp()
        if imagem is not None and not texto:
            # Sem cenário e sem leitura, mas COM print: o print já é o conteúdo.
            texto = (f"📸 *Captura do gráfico* — {info.get('hora','—')}"
                     + (f" · {info.get('janela')}" if info.get("janela") else "")
                     + f"\n(enviada a pedido, {idade:.0f} min após a captura)")
        if not texto:
            if quer_imagem:
                self._chat_responder(
                    "Não tenho print nenhum guardado para enviar. Peça 'tira um "
                    "print' primeiro — aí eu capturo e mando.")
                return
            self._chat_responder(
                "Não tenho nada para enviar ainda: não há sugestão nem leitura "
                "do gráfico nesta sessão. Assim que o motor fizer a primeira "
                "análise, é só pedir que eu mando.")
            return
        self._chat_status("📲 enviando no WhatsApp…", "#ff9f43")
        recibo = []
        try:
            enviar_relatorio_whatsapp(texto, imagem, lambda m: (self.log(m),
                                                                recibo.append(m)))
        except Exception as e:
            recibo.append(f"⚠️ Falha no disparo: {e}")
        # Só diz que enviou se o próprio disparo confirmou o sucesso.
        if any("✅" in m for m in recibo):
            self._chat_responder(
                "Enviado no seu WhatsApp agora, pelo motor."
                + (f" Mandei a IMAGEM do gráfico (captura das {info.get('hora','—')})"
                   " junto com o texto." if imagem is not None else
                   " Mandei o cenário com entrada, stop, alvo e o status da conta."))
        else:
            motivo = next((m for m in recibo if "⚠️" in m), "sem resposta do motor")
            self._chat_responder(
                f"NÃO consegui enviar — nada saiu para o seu WhatsApp. "
                f"{motivo.lstrip('⚠️ ').strip()}. Confira na aba Motor se o "
                "WhatsApp está conectado (o QR code precisa ter sido lido).")

    def _resumo_para_whatsapp(self):
        """O que vai na mensagem: a sugestão em aberto (ou a última leitura) +
        o status da conta. Só dados REAIS da mesa — nada gerado por modelo."""
        partes = []
        pend = self._ultimo_sinal_pendente()
        if pend:
            partes.append(
                f"📘 *Cenário aguardando decisão*\n{pend.get('direcao')} "
                f"{pend.get('ativo', '')} — entrada {pend.get('entry')} · "
                f"stop {pend.get('stop')} · alvo {pend.get('tp1')}")
        else:
            ua = getattr(self, "_ultima_analise", None) or {}
            if ua.get("ativo"):
                partes.append(
                    f"📊 *Última leitura ({ua.get('hora', '—')})*\n"
                    f"{ua.get('acao')} {ua.get('ativo')} @ {ua.get('preco')} · "
                    f"probabilidade {ua.get('probabilidade', 0):.0f}%")
        if not partes:
            return ""
        partes.append(self._chat_status_texto())
        return "\n\n".join(partes)

    def _capturar_print_agora(self):
        """Captura a tela NA HORA, a pedido do trader, sem esperar o ciclo.
        Devolve o mesmo dicionário de _ultimo_print, ou None se não deu."""
        try:
            nome_janela = carregar_config().get("nome_janela_corretora", "").strip()
            imagem = None
            if nome_janela:
                hwnd = self._resolver_hwnd_corretora(nome_janela)
                if hwnd:
                    permite = carregar_config().get("restaurar_janela_minimizada", True)
                    garantir_janela_renderizando(hwnd, permite)
                    imagem = capturar_janela_em_segundo_plano(hwnd)
                    if imagem is None or imagem_esta_em_branco(imagem):
                        recorte, sobreposto = capturar_via_recorte_de_tela(hwnd)
                        imagem = None if sobreposto else recorte
            if imagem is None or imagem_esta_em_branco(imagem):
                imagem = plataforma.capturar_tela_inteira()
                nome_janela = nome_janela or "tela inteira"
            if imagem is None or imagem_esta_em_branco(imagem):
                return None
            return salvar_ultimo_print(imagem, nome_janela or "tela inteira")
        except Exception as e:
            self.log(f"⚠️ Falha ao capturar print a pedido da TIGER: {e}")
            return None

    def _confirmar_motor(self, esperado_ligado):
        """Confere o que REALMENTE aconteceu e avisa no chat.

        O DEFEITO QUE ISTO CORRIGE (log de 11/08, 13:05):
            ❯ liga o motor
            ✳ "Ligando o motor agora..."
            ✳ "Motor no ar: já estou capturando e analisando o gráfico."
            [log da aba Motor, no mesmo minuto]
            ⚠️ O processo do Node encerrou IMEDIATAMENTE (código 1).
            ❌ ERRO: a porta 3939 já está em uso.

        Ela anunciou "motor no ar" porque olhava a flag `motor_rodando`, que era
        ligada assim que o Popen retornava — 1,5 segundo ANTES da checagem que
        descobria o processo morto. Era um relatório de sucesso sobre um
        processo que não existia mais. Agora ela espera a porta RESPONDER
        (`motor_confirmado`), e a morte do processo interrompe a espera na hora,
        com o motivo real."""
        limite = 180 if esperado_ligado else 20
        for _ in range(limite):
            time.sleep(1)
            if esperado_ligado:
                if getattr(self, "motor_morreu_ao_subir", False):
                    self._chat_feed(
                        "O motor NÃO subiu. O processo do Node morreu ao "
                        "iniciar — o motivo está no log da aba Motor, logo "
                        "acima. Quando é a porta 3939 ocupada, eu já tento "
                        "liberar sozinha antes de ligar; se a mensagem disser "
                        "que quem está na porta não é o motor, feche aquele "
                        "programa e mande ligar de novo.")
                    return
                if getattr(self, "motor_confirmado", False):
                    self._chat_feed("Motor no ar: a porta respondeu, já estou "
                                     "capturando e analisando o gráfico. Quando "
                                     "aparecer um cenário válido eu te aviso aqui.")
                    return
            else:
                if not (getattr(self, "motor_rodando", False) or
                        getattr(self, "robo_ativo", False)):
                    self._chat_feed("Motor desligado, confirmado. Nenhuma "
                                     "análise nova sai até você mandar ligar.")
                    return
        self._chat_feed(
            "Não consegui confirmar que o motor " +
            ("subiu" if esperado_ligado else "parou") +
            ". Dá uma olhada no log da aba Motor — costuma ser Node.js "
            "faltando, chave da API recusada ou a janela da corretora fechada.")

    def _ia_falar(self, texto, forcar=False):
        if forcar or (getattr(self, "ia_voz_var", None) and self.ia_voz_var.get()):
            # falar() já limpa asteriscos/markdown/emoji para fala natural.
            # O corte era 600 e engolia o fim de respostas mais longas — agora
            # cabe a resposta inteira (a persona é que pede concisão).
            threading.Thread(target=falar, args=(texto[:1800],), daemon=True).start()

    # ---------------- Ações locais (determinísticas) ----------------
    def _chat_executar_acao(self, acao):
        if acao == "META":
            self._chat_responder(self._texto_da_meta_de_hoje(),
                                  falar_tb=False,
                                  texto_voz=self._meta_falada())
            return
        if acao == "STATUS":
            # Na tela vai o card completo; na VOZ vai a frase falada (ler
            # bullet por bullet em voz alta é insuportável).
            self._chat_responder(self._chat_status_texto(), falar_tb=False,
                                  texto_voz=self._status_falado())
            return
        if acao == "LIGAR_MOTOR":
            self._chat_motor(True)
            return
        if acao == "DESLIGAR_MOTOR":
            self._chat_motor(False)
            return
        if acao == "ZERAR_CICLO":
            self._chat_zerar_ciclo()
            return
        if acao == "VER_CONFIG":
            self._chat_ver_configuracao(getattr(self, "_ultimo_pedido", ""))
            return
        if acao == "POR_QUE_SEM_SUGESTAO":
            self._chat_estado_do_freio()
            return
        if acao == "DIAG_MICROFONE":
            self._chat_responder(self.diagnostico_microfone(), falar_tb=False)
            return
        if acao == "QUAL_PREGAO":
            self._chat_responder(texto_do_pregao_atual())
            return
        if acao == "VIRAR_DIA":
            self._chat_virar_dia()
            return
        if acao == "CALAR":
            estava = parar_fala()
            # Responde só por texto: falar aqui seria contrariar o pedido.
            self._chat_responder(
                "Calei." if estava else "Já estava calada.", falar_tb=False,
                texto_voz="")
            return
        if acao in ("VOZ_RAPIDA", "VOZ_LENTA"):
            passo = 25 if acao == "VOZ_RAPIDA" else -25
            novo, no_limite = ajustar_velocidade_da_voz(passo)
            if no_limite:
                self._chat_responder(
                    f"Já estou no {'mais rápido' if passo > 0 else 'mais devagar'} "
                    f"que consigo falar ({novo} palavras por minuto) — além "
                    "disso vira ininteligível.")
            else:
                self._chat_responder(
                    f"Pronto, {'acelerei' if passo > 0 else 'desacelerei'} a "
                    f"fala para {novo} palavras por minuto. Assim está bom, ou "
                    f"quer que eu {'acelere' if passo > 0 else 'reduza'} mais?")
            return
        if acao in ("NOTICIAS", "COTACAO", "PESQUISAR"):
            # Estes rodam na WEB, pela própria ferramenta — sem chave, sem cota.
            threading.Thread(target=self._chat_web, args=(acao, self._ultimo_pedido),
                             daemon=True).start()
            return
        if acao == "LISTAR_CONHECIMENTO":
            temas = indice_da_base_smc()
            licoes = carregar_licoes()
            corpo = "\n".join(f"• {t}" for t in temas)
            self._chat_responder(
                f"Tenho {len(temas)} assuntos de SMC gravados aqui dentro, que "
                "eu respondo NA HORA e sem gastar nada da cota da API (funciona "
                f"até sem internet):\n{corpo}\n\nAlém desses, tenho "
                f"{len(licoes)} lição(ões) que VOCÊ me ensinou. Pergunte "
                "qualquer um desses temas que eu explico direto. Para o que é do "
                "momento — leitura do gráfico de agora, notícia, análise da sua "
                "posição — aí sim eu uso a API.",
                falar_tb=False,
                texto_voz=f"Tenho {len(temas)} assuntos de SMC gravados aqui "
                          f"dentro e {len(licoes)} lições suas. Respondo todos "
                          "eles sem gastar cota da API.")
            return
        if acao == "LISTAR_LICOES":
            # Ele precisa CONFERIR o que entrou de verdade na memória — a
            # desconfiança dele era justa, porque antes nada entrava.
            licoes = carregar_licoes()
            if not licoes:
                self._chat_responder(
                    "Ainda não gravei nenhuma lição sua. Para gravar, termine a "
                    "frase com 'aprenda isso' — por exemplo: 'não opere contra "
                    "o H4 depois das 15h, aprenda isso'. Aí ela passa a valer "
                    "em todas as análises, inclusive depois de fechar o app.")
                return
            corpo = "\n".join(f"{i}. {l}" for i, l in enumerate(licoes, 1))
            self._chat_responder(
                f"Tenho {len(licoes)} lição(ões) sua(s) gravadas, e todas "
                f"entram em cada análise e cada conversa:\n{corpo}",
                falar_tb=False,
                texto_voz=f"Tenho {len(licoes)} lições suas gravadas. "
                          f"A mais recente é: {licoes[-1]}")
            return
        if acao == "ENVIAR_WHATSAPP":
            self._chat_enviar_whatsapp()
            return
        if acao == "CONECTAR_WHATSAPP":
            # Quem conecta o WhatsApp é o motor (é ele que gera o QR code).
            if getattr(self, "motor_rodando", False) or getattr(self, "robo_ativo", False):
                self._chat_responder(
                    "O motor já está ligado — é ele que conecta o WhatsApp. "
                    "Se ainda não pareou, abra a aba Motor: o QR code aparece "
                    "lá e você lê com o celular em Aparelhos conectados. "
                    "Depois é só me pedir 'manda no whatsapp'.")
                return
            self._chat_responder(
                "Quem conversa com o WhatsApp é o motor, e ele está desligado. "
                "Vou ligar agora — quando subir, o QR code aparece na aba Motor "
                "para você ler com o celular em Aparelhos conectados.")
            self.after(0, self.iniciar)
            threading.Thread(target=self._confirmar_motor, args=(True,),
                             daemon=True).start()
            return
        if acao == "AJUDA":
            self._chat_responder(
                "O que eu EXECUTO de verdade (é o app que faz, não é conversa): "
                "'liga o motor' e 'desliga o motor'; 'zera o ciclo' (limpa o "
                "dashboard da conta, com confirmação); 'manda no whatsapp' e "
                "'conecta o whatsapp'; 'tira um print' (captura a tela na hora) "
                "e 'olha o gráfico' (analiso a última captura); 'acatar' (com "
                "confirmação), 'dispensar', 'cancelar ordem'; 'status'; "
                "CONFIGURAR a ferramenta em português ('o dia da conta 1 "
                "começa às 19h', 'analisa a cada 5 minutos', 'risco de 1% por "
                "operação', 'meta de 6 mil em 10 dias') e conferir com 'como "
                "está configurado o risco do plano da conta 1'; e para "
                "eu gravar uma regra sua, termine a frase com 'aprenda isso' — "
                "por exemplo: 'nunca opere contra o H4 depois das 15h, aprenda "
                "isso'. Fora esses comandos, é conversa: pergunte por que "
                "sugeri um cenário, peça notícia do mercado que eu pesquiso na "
                "internet, discuta o plano — por texto, pelo 🎤 ou dizendo "
                "'Olá Tiger'.")
            return
        if acao == "POSTMORTEM":
            self._chat_responder(montar_postmortem())
            return
        if acao == "MOSTRAR_PRINT":
            info = getattr(self, "_ultimo_print", None)
            idade = idade_do_ultimo_print(info)
            if idade is None:
                self._chat_responder(
                    "Não tenho print guardado. Peça 'tira um print' que eu "
                    "capturo a janela do gráfico agora.")
                return
            try:
                plataforma.abrir_arquivo(info["caminho"])
                abriu = True
            except Exception as e:
                self.log(f"(não consegui abrir o print: {e})")
                abriu = False
            self._chat_responder(
                f"É esta: captura das {info.get('hora','—')}"
                + (f", da janela “{info.get('janela')}”" if info.get("janela") else "")
                + f", {idade:.0f} min atrás."
                + (" Abri a imagem no seu visualizador."
                   if abriu else " Não consegui abrir o visualizador daqui.")
                + f"\nArquivo: {info['caminho']}")
            return
        if acao == "ACATAR":
            sinal = self._ultimo_sinal_pendente()
            if not sinal:
                self._chat_responder(self._motivo_sem_pendente())
                return
            direcao = "ACATOU_VENDA" if str(sinal.get("direcao")).upper() == "SELL" \
                else "ACATOU_COMPRA"
            self.after(0, lambda s=sinal["id"], d=direcao: self._registrar_decisao(s, d))
            self._chat_responder(
                f"Feito: {sinal.get('direcao')} {sinal.get('ativo','')} ACATADO e "
                "registrado no diário. Acompanho entrada, stop e alvo daqui.")
            return
        if acao == "DISPENSAR":
            sinal = self._ultimo_sinal_pendente()
            if not sinal:
                self._chat_responder(self._motivo_sem_pendente())
                return
            self.after(0, lambda s=sinal["id"]: self._registrar_decisao(s, "NAO_OPEROU"))
            self._chat_responder(f"Dispensado o {sinal.get('direcao')} "
                                  f"{sinal.get('ativo','')} — sem acompanhamento dele.")
            return
        if acao == "CANCELAR":
            pendentes = [p for p in posicoes_do_ciclo() if p.get("status") == "PENDENTE"]
            if not pendentes:
                self._chat_responder("Não há ordem pendente para cancelar nesta conta.")
                return
            alvo = pendentes[-1]
            self.after(0, lambda i=alvo["id"]: self._cancelar_posicao_click(i))
            self._chat_responder(
                f"Cancelada a ordem pendente {alvo.get('direcao')} "
                f"{alvo.get('ativo')} @ {alvo.get('entry')} — e encerrei o "
                "acompanhamento do cenário junto.")
            return

    def _fatos_da_mesa(self):
        """Os números da conta que TÊM fonte única no disco, para a conferência.

        Só entra aqui o que é inequívoco. Um fato que eu não consiga ler com
        certeza fica de fora: conferir contra um valor duvidoso seria trocar um
        erro por outro."""
        fatos = {}
        try:
            p = plano_da_conta_ativa()
            for chave, campo in (("margem", "margem"), ("meta", "meta_alvo"),
                                 ("drawdown", "drawdown_maximo")):
                v = _num(p.get(campo))
                if v is not None and v > 0:
                    fatos[chave] = v
        except Exception:
            pass
        try:
            s = self._computar_stats_plano()
            for chave, campo in (("hoje", "resultado_hoje"), ("ciclo", "lucro_usd")):
                v = _num(s.get(campo))
                if v is not None:
                    fatos[chave] = v
        except Exception:
            pass
        return fatos

    def _chat_status_texto(self):
        try:
            stats = self._computar_stats_plano()
        except Exception:
            return "Ainda não tenho dados suficientes do ciclo para um status."
        partes = [f"Conta '{nome_conta_ativa()}':",
                  f"• Hoje: US$ {stats['resultado_hoje']:+,.2f} · ciclo: "
                  f"US$ {stats['lucro_usd']:+,.2f} ({stats['total_ops']} op. fechadas, "
                  f"win rate {stats['winrate']:.0f}%)",
                  f"• Meta: US$ {stats['meta']:,.2f} em {stats.get('dias_meta', 5)} dia(s) "
                  f"— faltam US$ {stats['falta']:,.2f} "
                  f"({stats['dias_restantes']} dia(s) restantes)"]
        # RITMO EXIGIDO: a conta que o trader mais pergunta ("quanto por dia?").
        # Sai daqui pronta, calculada em código — a IA não precisa (nem deve)
        # fazer essa divisão de cabeça e arriscar errar.
        ritmo = stats.get("meta_diaria")
        if ritmo is not None:
            partes.append(f"• Ritmo necessário: US$ {ritmo:,.2f} por dia nos "
                          f"{stats['dias_restantes']} dia(s) que restam")
        elif stats.get("falta", 0) > 0:
            partes.append("• Ritmo necessário: o prazo da meta já venceu — "
                          "reinicie o ciclo no Plano de Trading para um novo prazo")
        partes.append(f"• Posições abertas agora: {stats['abertas']}")
        # Detalhe das posições abertas: sem isso ela só sabia o NÚMERO e não
        # conseguia responder "como está minha operação agora".
        try:
            for p in posicoes_do_ciclo():
                if p.get("status") == "ABERTA":
                    partes.append(
                        f"   – {p.get('direcao')} {p.get('ativo')} "
                        f"{p.get('contratos', '?')} contrato(s) @ {p.get('entry')} · "
                        f"stop {p.get('stop')} · alvo {p.get('tp1')} · "
                        f"P&L agora US$ {p.get('pnl_atual', 0):+,.2f}")
        except Exception:
            pass
        ua = getattr(self, "_ultima_analise", None) or {}
        if ua.get("ativo"):
            partes.append(
                f"• Última leitura ({ua.get('hora', '—')}): {ua.get('acao')} "
                f"{ua.get('ativo')} @ {ua.get('preco')} · probabilidade "
                f"{ua.get('probabilidade', 0):.0f}%")
        pend = self._ultimo_sinal_pendente()
        if pend:
            partes.append(f"• Sugestão AGUARDANDO decisão: {pend.get('direcao')} "
                          f"{pend.get('ativo','')} entrada {pend.get('entry')} — "
                          "diga 'acatar' ou 'dispensar'.")
        return "\n".join(partes)

    def _faxina_de_licoes(self):
        """Tira da memória permanente as lições que não ensinam nada.

        Roda na abertura, uma vez. Não é cosmético: cada lição vai INTEIRA
        para dentro do prompt de toda análise e toda conversa, então uma
        pergunta gravada como regra gasta contexto e empurra o modelo para
        responder a coisa errada. Faz parte da resposta a 'ela não está mais
        tão inteligente'.

        E ela DIZ o que apagou. Memória mexida em silêncio é pior que memória
        suja — ele precisa poder discordar."""
        try:
            boas, ruins = licoes_que_nao_ensinam(carregar_licoes())
            if not ruins:
                return
            with open(LICOES_FILE, "w", encoding="utf-8") as f:
                json.dump(boas[-40:], f, ensure_ascii=False, indent=1)
            _cache_json.pop(LICOES_FILE, None)
            linhas = [f"   • “{t[:150]}” — {m}" for t, m in ruins]
            self.log(f"🧹 Tirei {len(ruins)} lição(ões) da memória permanente "
                     "porque elas não ensinavam nada e entravam em toda "
                     "análise:\n" + "\n".join(linhas) +
                     f"\n   Sobraram {len(boas)} lição(ões) de verdade. "
                     "Se alguma dessas fazia falta, é só me ensinar de novo "
                     "em forma de regra.")
        except Exception as e:
            self.log(f"(faxina de lições não rodou: {str(e)[:120]})")

    def _numeros_da_meta_de_hoje(self):
        """Todos os números da pergunta "dá para bater a meta hoje?".

        Sai do PLANO (meta e ritmo exigido), do DIÁRIO (o que ele fez hoje,
        operação por operação) e da CONFIGURAÇÃO (hora de fechamento). Nada
        aqui é estimado; o que não dá para medir volta como None e a resposta
        diz isso com todas as letras."""
        d = {}
        stats = self._computar_stats_plano()
        # META ZERO É "NÃO CONFIGURADA", NÃO "JÁ BATIDA".
        # O teste de fumaça pegou: numa instalação nova, meta=0 fazia
        # falta=0, e a resposta saía "a meta do ciclo já foi batida 🎯" —
        # uma afirmação FALSA e simpática, que é o pior tipo. Quem nunca
        # configurou meta não bateu meta nenhuma.
        d["meta_configurada"] = bool(stats.get("meta"))
        d["ritmo_dia"] = stats.get("meta_diaria")
        d["falta_ciclo"] = stats.get("falta")
        d["resultado_hoje"] = stats.get("resultado_hoje") or 0.0
        d["dias_restantes"] = stats.get("dias_restantes")
        # A META DE HOJE é o ritmo diário exigido, e o que falta para ela é o
        # ritmo menos o que ele já fez hoje. Confundir isso com o que falta no
        # CICLO inteiro daria uma conta impossível e um veredito errado.
        d["meta_hoje"] = d["ritmo_dia"]
        d["falta_hoje"] = (None if d["ritmo_dia"] is None
                           else d["ritmo_dia"] - d["resultado_hoje"])
        d["minutos_restantes"] = minutos_ate_o_fim_do_pregao()

        fechadas = [p for p in operacoes_fechadas_hoje()
                    if p.get("pnl_final") is not None]
        ganhos = [p["pnl_final"] for p in fechadas if p["pnl_final"] > 0]
        perdas = [-p["pnl_final"] for p in fechadas if p["pnl_final"] <= 0]
        d["fechadas_hoje"] = len(fechadas)
        d["ganho_medio"] = (sum(ganhos) / len(ganhos)) if ganhos else None
        d["perda_media"] = (sum(perdas) / len(perdas)) if perdas else 0.0
        d["taxa_acerto"] = (len(ganhos) / len(fechadas)) if fechadas else None

        # A CADÊNCIA REAL DO DIA, para saber quantas operações ainda cabem.
        # Sai dos carimbos que o diário JÁ grava ('dd/mm/aaaa HH:MM'): da
        # abertura da primeira operação do pregão até agora. Nada de campo
        # inventado — se o carimbo não estiver lá, a cadência volta None e a
        # resposta diz que não dá para projetar.
        minutos_decorridos = None
        try:
            marcos = [_hora_do_registro(p.get("data_abertura"))
                      or _hora_do_registro(p.get("data_fechamento"))
                      for p in fechadas]
            marcos = sorted(m for m in marcos if m)
            if marcos:
                minutos_decorridos = int(
                    (datetime.datetime.now() - marcos[0]).total_seconds() // 60)
        except Exception:
            minutos_decorridos = None
        d["minutos_decorridos"] = minutos_decorridos
        try:
            teto = int(float(self.plano.get("max_operacoes_dia") or 0)) or None
        except (TypeError, ValueError):
            teto = None
        d["teto_do_dia"] = teto
        d["cabem"] = operacoes_que_ainda_cabem(
            d["minutos_restantes"] or 0, d["fechadas_hoje"],
            minutos_decorridos or 0, teto)
        return d

    def _texto_da_meta_de_hoje(self):
        """A resposta que faltava em 13/08 às 16:01.

        Ele perguntou "o dia encerra às 17:59, como estamos de probabilidade de
        bater a meta de hoje até lá?" e recebeu "não tenho dados suficientes
        para prever com precisão" — com a meta no plano, o resultado no diário
        e o horário na configuração. O que faltava não era dado: era esta
        função."""
        try:
            d = self._numeros_da_meta_de_hoje()
        except Exception as e:
            return ("Não consegui montar a conta da meta agora "
                    f"({type(e).__name__}). Confira se o Plano de Trading tem "
                    "meta e prazo preenchidos — sem isso não há o que calcular, "
                    "e eu não vou estimar por cima.")

        if not d.get("meta_configurada"):
            return ("Você ainda não configurou uma META nesta conta, então não "
                    "há o que eu conferir — e eu não vou dizer 'meta batida' "
                    "sobre uma meta que não existe.\nAbra 📊 Plano de Trading, "
                    "preencha 'Meta (US$)' e o prazo em dias, e me pergunte de "
                    "novo: a partir daí eu faço a conta a qualquer hora do "
                    "pregão.")
        if not d.get("meta_hoje"):
            return ("Não há meta para hoje que eu possa conferir: "
                    + ("o prazo da meta já venceu — reinicie o ciclo no Plano "
                       "de Trading para um novo prazo."
                       if (d.get("falta_ciclo") or 0) > 0 else
                       "a meta do ciclo já foi batida. 🎯"))

        linhas = [f"META DE HOJE — conta '{nome_conta_ativa()}'"]
        linhas.append(f"• Meta do dia: US$ {d['meta_hoje']:,.2f} "
                      f"(ritmo exigido para fechar o ciclo em "
                      f"{d['dias_restantes']} dia(s))")
        linhas.append(f"• Feito até agora hoje: US$ {d['resultado_hoje']:+,.2f} "
                      f"em {d['fechadas_hoje']} operação(ões) fechada(s)")

        if d["falta_hoje"] <= 0:
            linhas.append("• 🎯 A meta de HOJE já está batida. O que vier agora "
                          "é acima do plano — e é exatamente aqui que se "
                          "devolve o dia inteiro. Seu plano permite parar.")
            return "\n".join(linhas)

        linhas.append(f"• Falta hoje: US$ {d['falta_hoje']:,.2f}")

        mins = d["minutos_restantes"]
        if mins is None:
            linhas.append("• Não consegui ler a hora de fechamento do pregão "
                          "na configuração — sem ela não dá para dizer quanto "
                          "tempo resta.")
        else:
            linhas.append(f"• Tempo até o fechamento: {mins // 60}h{mins % 60:02d}")
            if mins == 0:
                linhas.append("• O pregão configurado já fechou. A meta de hoje "
                              "não será batida hoje — e isso é informação, não "
                              "julgamento.")
                return "\n".join(linhas)

        # A PARTE QUE ELE PEDIU: a probabilidade. Só sai se os quatro números
        # existirem de verdade. Sem histórico do dia não há taxa de acerto, e
        # sem taxa de acerto qualquer porcentagem seria invenção.
        if not d["fechadas_hoje"] or d["ganho_medio"] is None or \
                d["taxa_acerto"] is None:
            linhas.append(
                "\nNÃO vou te dar uma porcentagem: hoje ainda não há operação "
                "fechada com ganho para medir a sua taxa de acerto e o seu "
                "ganho médio do dia. Sem esses dois números, qualquer "
                "probabilidade que eu dissesse seria inventada — e é justamente "
                "isso que você me pediu para nunca fazer.\n"
                f"O que dá para afirmar: faltam US$ {d['falta_hoje']:,.2f}"
                + (f" e restam {mins // 60}h{mins % 60:02d} de pregão."
                   if mins else "."))
            return "\n".join(linhas)
        if d["cabem"] is None:
            # Sem cadência medida não dá para projetar quantas operações
            # cabem — e sem isso não há conta. Dizer o motivo CERTO importa:
            # mandar ele procurar taxa de acerto quando o que falta é ritmo
            # é mandá-lo olhar para o lugar errado.
            linhas.append(
                "\nNÃO vou te dar uma porcentagem: não consegui medir o seu "
                "ritmo de hoje (os carimbos de hora das operações não estão "
                "legíveis), e sem ritmo não dá para saber quantas operações "
                "ainda cabem até o fechamento.")
            return "\n".join(linhas)

        linhas.append(
            f"• No seu ritmo de hoje ainda cabem ~{d['cabem']} operação(ões) "
            + (f"(teto do plano: {d['teto_do_dia']}/dia)"
               if d["teto_do_dia"] else "até o fechamento"))
        linhas.append(f"• Hoje: acerto {d['taxa_acerto'] * 100:.0f}%, ganho "
                      f"médio US$ {d['ganho_medio']:,.2f}, perda média "
                      f"US$ {d['perda_media']:,.2f}")

        conta = chance_de_bater_a_meta(d["falta_hoje"], d["cabem"],
                                       d["taxa_acerto"], d["ganho_medio"],
                                       d["perda_media"])
        if conta is None:
            linhas.append("\nNão consegui fechar a conta com esses números.")
            return "\n".join(linhas)
        prob, precisa, n = conta
        if precisa is not None and n and precisa > n:
            linhas.append(
                f"\n➡️ CHANCE: 0%. Precisaria de {precisa} acerto(s) e só cabem "
                f"{n} operação(ões) até o fechamento. Acertando TODAS ainda não "
                "chega. A meta de hoje não sai hoje — o que resta é não "
                "estragar o que já está feito.")
        elif n == 0:
            linhas.append("\n➡️ CHANCE: 0%. Não cabe mais operação nenhuma até o "
                          "fechamento, seja por tempo ou pelo teto do plano.")
        else:
            linhas.append(
                f"\n➡️ CHANCE: {prob:.0f}% — precisa de {precisa} acerto(s) nas "
                f"{n} operação(ões) que ainda cabem.")
            if prob < 20:
                linhas.append("   Baixa. Correr atrás disso é o caminho mais "
                              "curto para transformar um dia ruim num dia caro.")
            elif prob < 55:
                linhas.append("   Dá, mas depende de o mercado colaborar. "
                              "Forçar setup para chegar lá é o oposto do plano.")
            else:
                linhas.append("   Está ao alcance no seu ritmo. Nada aqui "
                              "autoriza baixar o piso de qualidade.")

        # O QUE ESTE NÚMERO NÃO É. Sem isto, uma conta vira uma promessa.
        linhas.append(
            "\n(Como eu cheguei nisso: são as SUAS operações de hoje — taxa de "
            "acerto, ganho e perda médios — projetadas nas operações que ainda "
            "cabem no tempo que resta. É aritmética sobre o que já aconteceu, "
            "não previsão de mercado: supõe que as próximas se pareçam com as "
            "de hoje. O mercado não assinou esse contrato.)")
        return "\n".join(linhas)

    def _meta_falada(self):
        """A mesma conta em uma frase — bullet lido em voz alta é ruído."""
        try:
            d = self._numeros_da_meta_de_hoje()
        except Exception:
            return "Não consegui montar a conta da meta agora."
        if not d.get("meta_configurada"):
            return ("Você ainda não configurou uma meta nesta conta. Preencha "
                    "no Plano de Trading e me pergunte de novo.")
        if not d.get("meta_hoje"):
            return "Não há meta de hoje configurada para eu conferir."
        if d["falta_hoje"] <= 0:
            return "A meta de hoje já está batida. Seu plano permite parar."
        mins = d["minutos_restantes"]
        frase = (f"Faltam {d['falta_hoje']:,.0f} dólares para a meta de hoje")
        if mins:
            frase += f", e restam {mins // 60} horas e {mins % 60} minutos"
        frase += ". "
        # O MOTIVO CERTO PARA CADA CASO. Dizer "não há operação fechada
        # suficiente" quando o problema real é falta de TEMPO é uma mentira
        # por descuido — e manda ele olhar para o lugar errado.
        if not d["fechadas_hoje"] or d["ganho_medio"] is None or \
                d["taxa_acerto"] is None:
            frase += ("Não vou dar porcentagem: ainda não há operação fechada "
                      "suficiente hoje para medir a sua taxa de acerto sem "
                      "inventar.")
            return frase
        if not d["cabem"]:
            frase += ("A chance é zero: não cabe mais operação nenhuma até o "
                      "fechamento, seja por tempo ou pelo teto do plano.")
            return frase
        conta = chance_de_bater_a_meta(d["falta_hoje"], d["cabem"],
                                       d["taxa_acerto"], d["ganho_medio"],
                                       d["perda_media"])
        if conta:
            prob, precisa, n = conta
            frase += (f"A chance é de {prob:.0f} por cento: precisa de "
                      f"{precisa} acertos nas {n} operações que ainda cabem.")
        else:
            frase += "Não consegui fechar a conta com os números de hoje."
        return frase

    def _status_falado(self):
        """O mesmo status, em UMA frase natural — é isso que sai pelo alto-falante
        quando ele pede status por voz. Bullet lido em voz alta é ruído."""
        try:
            stats = self._computar_stats_plano()
        except Exception:
            return "Ainda não tenho dados suficientes do ciclo para um status."
        frase = (f"Na conta {nome_conta_ativa()}, hoje você está em "
                 f"{stats['resultado_hoje']:+,.0f} dólares e o ciclo em "
                 f"{stats['lucro_usd']:+,.0f}, com {stats['total_ops']} operações "
                 f"fechadas e {stats['winrate']:.0f} por cento de acerto. ")
        if stats.get("falta", 0) > 0:
            frase += (f"Faltam {stats['falta']:,.0f} dólares para a meta em "
                      f"{stats['dias_restantes']} dia ou dias")
            ritmo = stats.get("meta_diaria")
            frase += (f", o que dá {ritmo:,.0f} dólares por dia. " if ritmo is not None
                      else ", mas o prazo já venceu. ")
        else:
            frase += "A meta do ciclo já foi batida. "
        frase += (f"Você tem {stats['abertas']} posição ou posições abertas agora."
                  if stats["abertas"] else "Você não tem posição aberta agora.")
        return frase

    # ---------------- Conversa com o modelo ----------------
    def _chat_contexto(self):
        """Tudo o que a IA precisa saber AGORA: persona, estado real da mesa,
        última análise, aprendizado e lições. Nada de número inventado — o que
        não estiver aqui, ela deve dizer que não tem."""
        partes = [montar_persona_ia()]
        partes.append("\n--- DADOS REAIS DA MESA NESTE MOMENTO ---")
        partes.append(f"AGORA SÃO {time.strftime('%H:%M de %d/%m/%Y')} "
                      "(horário do computador do trader).")
        # ESTADO DO MOTOR: sem isso ela dizia "estou monitorando em segundo
        # plano" com o motor desligado — mentira que custa dinheiro.
        ligado = bool(getattr(self, "motor_rodando", False) or
                      getattr(self, "robo_ativo", False))
        janela = carregar_config().get("nome_janela_corretora", "").strip()
        if ligado:
            partes.append(
                f"MOTOR DE ANÁLISE: LIGADO — capturando e analisando "
                f"{'a janela ' + repr(janela) if janela else 'a tela inteira'} a cada "
                f"{carregar_config().get('intervalo_minutos', 15)} minuto(s). "
                "Pode dizer que está acompanhando, porque está mesmo.")
        else:
            partes.append(
                "MOTOR DE ANÁLISE: DESLIGADO — NENHUMA análise nova está "
                "rodando e nenhum gráfico está sendo capturado agora. NÃO diga "
                "que está monitorando ou acompanhando o mercado. Se ele quiser "
                "que você acompanhe, diga que basta pedir 'liga o motor'.")
        # OLHOS: existe print recente do gráfico para ela pedir/analisar?
        info_print = getattr(self, "_ultimo_print", None)
        idade = idade_do_ultimo_print(info_print)
        if idade is None:
            partes.append("PRINT DO GRÁFICO: não há nenhuma captura disponível "
                          "ainda (o motor precisa rodar ao menos um ciclo). Se "
                          "ele pedir para você olhar o gráfico, explique isso e "
                          "ofereça: ou ele liga o motor, ou manda um print pelo 📎.")
        else:
            partes.append(
                f"PRINT DO GRÁFICO: existe uma captura de "
                f"{(info_print or {}).get('hora', '—')} (há {idade:.0f} minuto(s)), "
                "da janela que o motor monitora. Quando ele pedir 'olha o "
                "gráfico', essa imagem chega anexada para você analisar.")
        # Vínculo com a conta SELECIONADA no Plano de Trading: a TIGER opina
        # sempre com o plano DESTA conta (meta, prazo, risco, R:R mínimo).
        try:
            p = plano_da_conta_ativa()
            partes.append(
                f"PLANO DE TRADING DA CONTA SELECIONADA ('{nome_conta_ativa()}'): "
                f"margem US$ {p.get('margem', 0):,.0f} · meta US$ "
                f"{p.get('meta_alvo', 0):,.0f} em {p.get('dias_meta', 5)} dia(s) · "
                f"drawdown máximo US$ {p.get('drawdown_maximo', 0):,.0f} · risco "
                f"por operação {p.get('risco_pct', 1.0)}% · R:R mínimo "
                f"1:{p.get('rr_minimo', 2.0)} · probabilidade mínima "
                f"{p.get('probabilidade_minima', 55)}%. Todas as suas orientações "
                "devem respeitar ESTE plano.")
        except Exception:
            pass
        # Configuração da FERRAMENTA (horário do dia dele e ritmo das análises).
        # Sem isto no contexto ela respondia "não sei" sobre a própria casa.
        try:
            c = carregar_config()
            partes.append(
                f"CONFIGURAÇÃO DA FERRAMENTA (vale para todas as contas): o dia "
                f"de operação dele começa às "
                f"{c.get('hora_inicio', PADRAO_CONFIG_APP['hora_inicio'])} e "
                f"termina às {c.get('hora_fim', PADRAO_CONFIG_APP['hora_fim'])}; "
                f"o motor analisa a cada "
                f"{c.get('intervalo_minutos', PADRAO_CONFIG_APP['intervalo_minutos'])} "
                "minuto(s). Ele PODE mudar qualquer um desses valores falando "
                "com você (o app é que grava e confirma) — nunca diga que não "
                "dá para configurar.")
        except Exception:
            pass
        partes.append(self._chat_status_texto())
        ua = getattr(self, "_ultima_analise", None) or {}
        if ua.get("analise"):
            partes.append(f"\nÚLTIMA ANÁLISE COMPLETA DO GRÁFICO "
                          f"({ua.get('hora')}):\n{ua.get('analise')}")
            if ua.get("confluencias"):
                partes.append("Confluências vistas: " + "; ".join(ua["confluencias"]))
        # AS OUTRAS JANELAS TAMBÉM FORAM LIDAS. Com dois ou três gráficos
        # monitorados, só a ÚLTIMA leitura chegava aqui — perguntar "e o NQ?"
        # logo depois de o motor ler o MES devolvia a leitura do MES com o nome
        # errado, ou um "não tenho isso". A leitura de cada ativo já estava
        # guardada em memória; faltava entregá-la. Contexto que existe e não
        # chega ao modelo é a forma mais barata de burrice.
        outras = getattr(self, "_analises_por_ativo", None) or {}
        linhas_outras = [
            f"• {sym}: {a.get('acao')} @ {a.get('preco')} · probabilidade "
            f"{a.get('probabilidade', 0):.0f}% · lido às {a.get('hora', '—')} "
            f"(janela {a.get('janela', '—')})"
            for sym, a in outras.items()
            if sym != str(ua.get("ativo", "")).upper()]
        if linhas_outras:
            partes.append("\nLEITURA MAIS RECENTE DOS OUTROS ATIVOS MONITORADOS "
                          "(cada uma da SUA janela, nunca misturadas):\n"
                          + "\n".join(linhas_outras))
        try:
            partes.append(compilar_memoria_prompt())
        except Exception:
            pass
        partes.append(bloco_licoes_prompt())
        return "\n".join(p for p in partes if p)

    def _preparar_anexo(self, client, anexo):
        """Transforma o arquivo em conteúdo para o modelo. Imagem pequena vai
        inline; vídeo/PDF/arquivo grande sobe pela File API (até ~1,9 GB) e
        espera o processamento terminar. Devolve a parte pronta, ou None."""
        import mimetypes
        mime = mimetypes.guess_type(anexo)[0] or "application/octet-stream"
        tamanho = os.path.getsize(anexo)
        if mime.startswith("image/") and tamanho <= 15_000_000:
            with open(anexo, "rb") as f:
                return types.Part.from_bytes(data=f.read(), mime_type=mime)
        # Arquivo grande/vídeo: sobe e aguarda ficar ATIVO (vídeo processa).
        self.after(0, lambda: self._chat_status("📎 enviando o arquivo…", "#ff9f43"))
        try:
            arq = client.files.upload(file=anexo)
        except TypeError:
            arq = client.files.upload(path=anexo)      # SDK mais antigo
        for _ in range(90):                            # até ~3 min de processamento
            estado = str(getattr(arq, "state", "") or "")
            if "ACTIVE" in estado:
                return arq
            if "FAILED" in estado:
                return None
            time.sleep(2)
            arq = client.files.get(name=arq.name)
        return None

    def _chat_configs(self, modelo, teto, com_busca):
        """Configurações a tentar para UM modelo, da melhor para a mais simples.

        Duas coisas importam aqui:
        • BUSCA NA INTERNET (google_search): é o que dá acesso a notícia,
          calendário econômico e dado macro atual. Nem todo modelo/SDK aceita a
          ferramenta, então sempre existe uma configuração sem ela como reserva.
        • RACIOCÍNIO INTERNO ZERADO nos modelos que pensam por padrão: o
          "pensamento" consome o orçamento de saída e era o que fazia a resposta
          chegar cortada no meio da frase — ou vazia.
        """
        tentativas = []
        ferramentas = None
        if com_busca:
            try:
                ferramentas = [types.Tool(google_search=types.GoogleSearch())]
            except Exception:
                ferramentas = None            # SDK sem a ferramenta de busca
        pensa = "latest" in modelo or "-3-" in modelo
        for tools in ([ferramentas, None] if ferramentas else [None]):
            base = {"temperature": 0.6, "max_output_tokens": teto}
            if tools:
                base["tools"] = tools
            if pensa:
                try:
                    tentativas.append(types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                        **base))
                except Exception:
                    pass                      # SDK antigo sem ThinkingConfig
            try:
                tentativas.append(types.GenerateContentConfig(**base))
            except Exception:
                pass
        return tentativas

    @staticmethod
    def _resposta_cortada(r):
        """A resposta bateu no teto de tokens e parou no meio da frase?
        É o que produzia aquelas respostas como 'faltam 7.6' — a conta certa,
        interrompida antes do número terminar."""
        try:
            return "MAX_TOKEN" in str(
                getattr(r.candidates[0], "finish_reason", "") or "").upper()
        except Exception:
            return False

    @staticmethod
    def _diagnostico_erro(erro):
        """Traduz a falha do SDK para uma frase que diz O QUE FAZER. Antes tudo
        virava 'estou sem acesso à rede ou ao modelo' — o trader não tinha como
        saber se era cota, chave ou internet."""
        e = str(erro or "").upper()
        if not e:
            return ("Não consegui resposta de nenhum modelo agora. Se acabou de "
                    "acontecer, tente de novo em alguns segundos.")
        if "429" in e or "RESOURCE_EXHAUSTED" in e or "QUOTA" in e:
            return ("A cota da sua chave Gemini estourou (o plano gratuito tem "
                    "limite por minuto e por dia). Espere alguns minutos ou use "
                    "uma chave paga — é só colar na aba Motor.")
        if any(x in e for x in ("API KEY", "API_KEY", "PERMISSION", "UNAUTHENTICATED",
                                "401", "403")):
            return ("A chave da Gemini foi recusada. Cole a chave de novo no "
                    "campo da aba Motor e ligue o motor uma vez para salvar.")
        if any(x in e for x in ("TIMEOUT", "TIMED OUT", "CONNECTION", "SSL", "DNS",
                                "NETWORK", "UNREACHABLE", "GETADDRINFO", "PROXY")):
            return ("Não consegui alcançar o servidor do modelo — parece "
                    "internet. Confira a conexão e me chame de novo.")
        if "404" in e or "NOT_FOUND" in e:
            return ("Os modelos que eu uso não respondem para essa chave. "
                    "Confira se a API Gemini está habilitada para ela no "
                    "Google AI Studio.")
        if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in e or ("401" in e and "UNAUTHENTICATED" in e):
            return ("A chave da Gemini foi RECUSADA — e isso não é cota, é a "
                    "chave em si.\n\nO caso mais comum: no Mac, o Cmd+V colava "
                    "o texto DUAS VEZES, e a chave dobrada é inválida. Como o "
                    "campo mostra asteriscos, não dava para ver.\n\nApague o "
                    "campo da chave na aba Motor (Cmd+A e Delete), cole de novo "
                    "UMA vez, e ligue o motor para salvar.")
        if "500" in e or "503" in e or "INTERNAL" in e or "UNAVAILABLE" in e:
            return ("O servidor do modelo está sobrecarregado neste momento. "
                    "Me chame de novo em instantes.")
        return f"Falhou aqui: {str(erro)[:180]}"

    def _garantir_modelos(self, client):
        """Garante que a lista de modelos foi descoberta NA CONTA, e não é só a
        lista padrão do código.

        Importa quando o motor está DESLIGADO: quem descobria os modelos era só
        o motor, então, com ele parado, a TIGER ficava presa aos nomes fixos —
        e perdia os de reserva que a conta tem e que funcionam."""
        try:
            descobrir_modelos(client, log=self.log)
        except Exception:
            pass          # sem a lista da conta, segue com a padrão

    def _mensagens_para_provedor(self, pergunta):
        """Monta a conversa no formato da OpenAI para o provedor alternativo.

        Leva a MESMA persona e os MESMOS números da mesa que a Gemini recebe —
        senão a resposta de reserva sairia genérica, sem saber de que conta,
        de que posição e de que plano se está falando. E leva a regra da casa
        junto: trocar de provedor não autoriza inventar número."""
        cenario = ""
        try:
            c = self._cenario_da_mesa(pergunta) or {}
            partes = []
            if c.get("ativo_nome"):
                partes.append(f"Ativo em análise: {c['ativo_nome']}")
            ua = getattr(self, "_ultima_analise", None) or {}
            if ua.get("ativo"):
                partes.append(
                    f"Última leitura do motor ({ua.get('hora','—')}): "
                    f"{ua.get('acao')} {ua.get('ativo')} @ {ua.get('preco')}, "
                    f"probabilidade {ua.get('probabilidade','—')}%")
            for p in posicoes_do_ciclo():
                if p.get("status") in ("ABERTA", "PENDENTE"):
                    partes.append(
                        f"Posição {p.get('status')}: {p.get('direcao')} "
                        f"{p.get('ativo')} {p.get('contratos')} ctr @ "
                        f"{p.get('entry')} · stop {p.get('stop')} · "
                        f"alvo {p.get('tp1')}")
            cenario = "\n".join(partes)
        except Exception:
            cenario = ""

        sistema = (
            "Você é a TIGER, a IA de mesa do SMC Quant Pro, falando com um "
            "trader profissional de futuros (Micro E-mini). Responda em "
            "português do Brasil, direto, sem enrolação, como um mentor de "
            "mesa experiente em Smart Money Concepts.\n\n"
            "REGRA INEGOCIÁVEL: NUNCA invente número. Preço, stop, alvo, "
            "resultado, VWAP — se você não tem o dado, diga que não tem. "
            "Ausência de dado não é conclusão. Um número inventado numa mesa "
            "vira prejuízo.\n\n"
            "Você NÃO executa nada escrevendo: quem liga o motor, tira print, "
            "acata ordem ou envia WhatsApp é o programa, por comando. Nunca "
            "diga que fez algo — diga qual comando faz. Isso inclui a voz "
            "PASSIVA: é proibido escrever 'ficou salvo', 'está gravado' ou "
            "'foi registrado'.\n\n"
            # AS TRÊS REGRAS ABAIXO NASCERAM DO TESTE DE 12/08 COM O MODELO
            # LOCAL, que é menor e escorrega em coisas que o modelo grande não
            # erra. Elas custam nada para um modelo bom e salvam o pequeno.
            "PORTUGUÊS DO BRASIL, E SÓ. Nada de palavra em inglês solta no "
            "meio da frase, nada de outro alfabeto. Se a palavra técnica for "
            "em inglês (order block, FVG, sweep), escreva-a normalmente — mas "
            "o resto da frase é português.\n\n"
            "O QUE ELE OPERA: MES/MESU6 é o MICRO E-MINI S&P 500, um contrato "
            "futuro de ÍNDICE de ações negociado na CME. NÃO é forex, NÃO é "
            "câmbio, NÃO é cripto. O MES vale US$ 5 por ponto e o tick é 0,25 "
            "ponto (US$ 1,25). Nunca escreva outro valor por ponto: se você "
            "não tem certeza do multiplicador de um contrato, diga que não "
            "tem — não estime.\n\n"
            "SEJA CURTO. Três a seis frases resolvem quase tudo. Encher "
            "linguiça com lista genérica ('verifique sua conexão', 'consulte "
            "o suporte') não é resposta — é ruído, e numa mesa ruído custa "
            "atenção na hora errada. Se não souber, uma frase dizendo isso "
            "vale mais que vinte enrolando.\n"
            + (f"\nSITUAÇÃO ATUAL DA MESA:\n{cenario}" if cenario else ""))

        mensagens = [{"role": "system", "content": sistema}]
        for m in carregar_chat()[-10:]:
            if not m.get("texto"):
                continue
            mensagens.append({
                "role": "user" if m.get("papel") == "voce" else "assistant",
                "content": str(m["texto"])[:1500]})
        # A pergunta do turno pode já estar no histórico (ela é registrada
        # antes de o worker rodar). Só acrescenta se não for a última.
        if not mensagens[-1:] or mensagens[-1].get("content") != pergunta:
            mensagens.append({"role": "user", "content": pergunta})
        return mensagens

    def _chat_worker(self, pergunta, anexo=None):
        resposta = None
        ultimo_erro = None
        # Inicializado aqui de propósito: se a criação do cliente falhar (chave
        # inválida, por exemplo), a mensagem de erro lá embaixo ainda cita a
        # lista — sem isso ela quebraria com NameError e ele não receberia nada.
        modelos = []
        try:
            # Com anexo o tempo é maior (upload + vídeo processando). Sem anexo
            # o limite subiu de 15 s para 60 s: com busca na internet ligada a
            # primeira resposta demora mais, e 15 s estourava ANTES de responder
            # — foi o que gerava tanto "estou sem acesso à rede".
            client = genai.Client(
                api_key=carregar_api_key(),
                http_options=types.HttpOptions(
                    timeout=300_000 if anexo else TIMEOUT_CHAT_MS))
            historico = carregar_chat()[-12:]
            corpo = "\n".join(
                f"{'TRADER' if m['papel'] == 'voce' else 'IA'}: {m['texto']}"
                for m in historico if m["papel"] in ("voce", "ia"))
            # DADOS REAIS DA WEB junto do prompt: preço de agora e manchetes das
            # casas de mercado. É a coleira contra invenção — com o número na
            # mão, o modelo não tem por que chutar um motivo para o movimento.
            bloco_web = ""
            if not anexo:
                try:
                    bloco_web = bloco_web_para_prompt(pergunta)
                except Exception:
                    bloco_web = ""
            prompt = (f"{self._chat_contexto()}\n"
                      + (f"\n--- DADOS REAIS DA WEB AGORA ---\n{bloco_web}\n"
                         if bloco_web else "")
                      + f"\n--- CONVERSA RECENTE ---\n"
                      f"{corpo}\nTRADER: {pergunta}\nIA:")
            parte_anexo = None
            if anexo:
                try:
                    parte_anexo = self._preparar_anexo(client, anexo)
                except Exception:
                    parte_anexo = None
                if parte_anexo is None:
                    self._chat_entregar_resposta(
                        "Não consegui processar esse arquivo "
                        f"({os.path.basename(anexo)}). Confere se ele abre "
                        "normal na sua máquina e tenta de novo — vídeos muito "
                        "longos podem falhar; um trecho menor resolve.")
                    return
                prompt = (f"{self._chat_contexto()}\n\n"
                          "O TRADER ENVIOU UM ARQUIVO (anexado nesta mensagem: "
                          f"{os.path.basename(anexo)}). Analise-o de verdade — "
                          "se for print/vídeo de gráfico, faça a leitura SMC "
                          "(estrutura, liquidez, order blocks, FVG) com a "
                          "análise técnica clássica de confluência. Descreva "
                          "APENAS o que está visível no arquivo: NUNCA invente "
                          "preços ou números que não apareçam nele.\n\n"
                          f"--- CONVERSA RECENTE ---\n{corpo}\n"
                          f"TRADER: {pergunta}\nIA:")
            # O que vai para o modelo: só o texto, ou texto + arquivo anexado.
            conteudo = [prompt] if parte_anexo is None else [parte_anexo, prompt]
            # TETO DE SAÍDA: era 500 e cortava a resposta no meio da conta
            # ("faltam 7.6"). Com espaço de sobra ela termina o raciocínio; a
            # persona é quem pede concisão, não a guilhotina do token.
            teto = 4096 if anexo else 2048
            # A MESMA LISTA DO MOTOR — este era o defeito que mais atrapalhava.
            # Aqui havia CINCO modelos escritos à mão (quatro com anexo), todos
            # da família 2.0. O motor tentava catorze e seguia analisando o
            # gráfico de 5 em 5 minutos usando os de reserva
            # (gemini-flash-lite-latest, gemini-3.1-flash-lite...), enquanto ela
            # respondia "a cota da sua chave estourou" para o MESMO print, no
            # MESMO minuto — porque a lista curta dela acabava antes.
            # Agora ela puxa a lista descoberta na conta, respeita o cooldown
            # compartilhado e só desiste depois de tentar TODOS.
            self._garantir_modelos(client)
            excluir = ()
            if anexo and not str(anexo).lower().endswith(
                    (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")):
                # Vídeo/PDF: os *-lite tropeçam. Com IMAGEM eles servem bem e
                # ficam na lista — é justamente o print do gráfico que ela mais
                # precisa ler quando os modelos maiores estão sem cota.
                excluir = ("gemini-2.0-flash-lite", "gemini-2.0-flash-lite-001",
                           "gemini-flash-lite-latest", "gemini-2.5-flash-lite")
            modelos = modelos_para_tentar(
                excluir=excluir, preferido=getattr(self, "_chat_modelo_bom", None))
            if not modelos:
                modelos = list(_MODELOS_PREFERENCIA)
            # ORÇAMENTO DE ESPERA. "não responde perguntas rápido, está
            # demorando muito pensando" — 14/08.
            #
            # A conta era esta: onze modelos, cada um com até quatro
            # configurações, cada chamada com prazo de 60 s. Com a cota
            # estourada isso podia passar de dez minutos ANTES de ela chegar
            # na base própria, que responderia na hora e sem cota nenhuma.
            # Ele ficava olhando "✳ pensando…" enquanto a resposta estava
            # pronta no disco, esperando a fila terminar.
            #
            # Agora existe um teto de tempo de parede. Estourou, o turno
            # segue para a base e para a IA local em vez de continuar batendo
            # numa porta que não abre. O teto NÃO se aplica quando há anexo:
            # ler um vídeo demora mesmo, e ali a espera é o serviço.
            inicio_espera = time.time()
            orcamento = None if anexo else ORCAMENTO_CHAT_SEG
            estourou = False
            for modelo in modelos:
                if orcamento and (time.time() - inicio_espera) > orcamento:
                    estourou = True
                    break
                for config in self._chat_configs(modelo, teto, com_busca=not anexo):
                    if orcamento and (time.time() - inicio_espera) > orcamento:
                        estourou = True
                        break
                    try:
                        r = client.models.generate_content(
                            model=modelo, contents=conteudo, config=config)
                        if r and r.text:
                            resposta = r.text.strip()
                            # Só memoriza o modelo em turno SEM arquivo: a lista
                            # de anexo é diferente e não deve viciar a de texto.
                            # Vem ANTES da emenda de propósito: o modelo já
                            # provou que responde, mesmo que a continuação falhe.
                            if not anexo:
                                self._chat_modelo_bom = modelo
                            # Avisa o motor: este modelo está de pé agora.
                            registrar_sucesso_modelo(modelo)
                            # Cortou no teto? Pede a continuação e emenda, para
                            # a frase nunca morrer pela metade na tela.
                            if self._resposta_cortada(r):
                                resposta = self._completar_resposta(
                                    client, modelo, config, conteudo, resposta)
                            break
                    except Exception as e:
                        ultimo_erro = e
                        # Anota no registro compartilhado: cota, sobrecarga ou
                        # descontinuado. Assim o motor não repete a tentativa
                        # perdida no ciclo seguinte.
                        tipo_falha = registrar_falha_modelo(modelo, e)
                        if tipo_falha in ("cota", "invalido"):
                            break      # não adianta tentar outra config do mesmo
                        continue
                if resposta or estourou:
                    break
            if estourou and not resposta:
                self.log(f"⏱️ Passei de {ORCAMENTO_CHAT_SEG}s tentando a Gemini "
                         "sem resposta — parei a fila e fui responder com o que "
                         "tenho aqui. Esperar mais não deixaria a resposta "
                         "melhor, só mais tarde.")

            # ---- SEGUNDA LEITURA DO MESMO NÚMERO ----
            # Só quando a pergunta é de NÍVEL e há imagem: é o único caso em
            # que uma chamada extra se paga. Ler duas vezes o mesmo rótulo dá
            # o mesmo número; inventar duas vezes dá dois.
            if resposta and anexo and parte_anexo is not None:
                resposta = self._confirmar_nivel_lido(
                    client, modelos, parte_anexo, pergunta, resposta)
        except Exception as e:
            ultimo_erro = e

        # ---- SEGUNDA INTELIGÊNCIA: a Gemini caiu, mas o pensamento não ----
        # Este é o bloco que responde à queixa "você não é uma IA?". Antes,
        # com a cota estourada, a TIGER só tinha o roteador local — e tudo que
        # não tivesse regra escrita virava o mesmo parágrafo de desculpa.
        # Agora, se houver OUTRA chave configurada (OpenAI, Anthropic,
        # OpenRouter, Groq), a MESMA pergunta vai para lá.
        # ---- A BASE VEM ANTES DO MODELO DE RESERVA ----
        # REGRESSÃO QUE EU MESMO CRIEI NA 2.27.0, E QUE O TESTE DELE EXPÔS.
        # A base própria (51 verbetes escritos e revisados) só era tentada
        # DEPOIS que todos os modelos falhavam. Enquanto o último da fila era
        # a Gemini, isso funcionava: sem cota, a base respondia.
        #
        # Com a IA LOCAL instalada, o último da fila NUNCA falha. Resultado: a
        # base deixou de ser alcançada, e "O QUE É SMC?" — que ela responde
        # com precisão e sem cota — foi parar num modelo de 7B, que devolveu
        # (log de 12/08, 21:18):
        #     "SMC ... in which we're discussing futures trading e altamente
        #      volátil como o forex (minúcias como E-mini)"
        # E-mini de índice não é forex. A base nunca escreveria isso.
        #
        # A regra certa: quando existe verbete, o VERBETE ganha do modelo
        # pequeno. Conhecimento curado vale mais que geração plausível.
        if not resposta and not anexo:
            try:
                if buscar_base_smc(pergunta):
                    da_base = responder_offline(pergunta,
                                                self._cenario_da_mesa(pergunta))
                    if da_base and da_base != getattr(
                            self, "_ultima_resposta_local", None):
                        self._ultima_resposta_local = da_base
                        resposta = da_base
                        self.log("📚 Respondido pela BASE PRÓPRIA — o verbete "
                                 "ganha do modelo pequeno.")
            except Exception:
                pass

        if not resposta and not anexo:
            try:
                mensagens = self._mensagens_para_provedor(pergunta)
                alt, quem = responder_por_provedor_alternativo(mensagens, self.log)
                if alt:
                    resposta = alt
                    self._provedor_da_resposta = quem
            except Exception as e:
                self.log(f"(provedor alternativo falhou: {str(e)[:120]})")

        if not resposta:
            # A API caiu (cota, chave ou rede). Antes disso virar uma resposta
            # vazia, tenta o CONHECIMENTO LOCAL: se a pergunta for de
            # metodologia, ela responde do mesmo jeito — sem cota nenhuma.
            # ROTEADOR OFFLINE: a melhor resposta que dá para montar sem a API
            # — capacidades, base própria (SMC + macro), cotação real ou
            # notícia relevante. Nunca o bloco interno do prompt: aquilo é
            # bastidor do modelo e virava um despejo de manchetes na tela.
            local = None
            try:
                if not anexo:
                    local = responder_offline(pergunta,
                                              self._cenario_da_mesa(pergunta))
            except Exception:
                local = None
            # A GUARDA ANTI-REPETIÇÃO ERA FURADA AQUI. O caminho local já
            # evitava repetir mandando o turno para o modelo; com a cota
            # estourada o modelo falhava, caía neste bloco, chamava
            # responder_offline() DE NOVO e devolvia o MESMO texto. Foi assim
            # que a mesma resposta sobre alvo saiu três vezes seguidas, palavra
            # por palavra. Agora, texto repetido aqui é recusado.
            if local and local == getattr(self, "_ultima_resposta_local", None):
                local = None
            if local:
                self._ultima_resposta_local = local
                resposta = (f"{local}\n\n(Respondi sem a API, com o que eu tenho "
                            "aqui e o que busquei na internet — a API está "
                            f"indisponível: {self._diagnostico_erro(ultimo_erro)})")
            elif anexo:
                # LER IMAGEM É A ÚNICA COISA QUE EU NÃO FAÇO SEM A API. Antes
                # isso caía no texto genérico "não está na minha base" — o que
                # é falso e confunde: o print FOI capturado, o que faltou foi
                # a visão. Aqui a resposta diz exatamente o que aconteceu.
                e_imagem = str(anexo).lower().endswith(
                    (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"))
                onde = "o print" if e_imagem else "o arquivo"
                resposta = (
                    f"{onde.capitalize()} está aqui comigo — capturei/recebi "
                    "certinho. O que eu NÃO consigo agora é LER a imagem: essa "
                    "é a única parte que depende da API da Gemini, e ela está "
                    f"fora ({self._diagnostico_erro(ultimo_erro)}).\n\n"
                    + (f"Tentei {len(modelos)} modelos, um por um, antes de te "
                       f"dizer isso — {diagnostico_modelos()}. Não é desculpa: "
                       "se sobrasse um só de pé, eu teria lido.\n\n"
                       if modelos and classificar_erro_modelo(ultimo_erro) != "fatal"
                       else "")
                    +
                    "Nada do que eu dissesse sobre esse gráfico agora seria "
                    "leitura de verdade — seria chute, e chute na mesa vira "
                    "prejuízo. Assim que a cota voltar (ou com uma chave paga "
                    "colada na aba Motor), me peça de novo 'analisa o gráfico' "
                    "que eu leio na hora.\n\n"
                    "Enquanto isso, sem depender de nada: peça 'status' para o "
                    "placar da conta, a cotação real de qualquer ativo, notícia "
                    "das casas de mercado, metodologia SMC, ou a configuração "
                    "da ferramenta.")
            else:
                resposta = (
                    "Não tenho como responder isso com segurança agora: não "
                    "está na minha base, não consegui confirmar na internet, e "
                    f"a API está fora ({self._diagnostico_erro(ultimo_erro)}). "
                    "Prefiro te dizer isso a inventar. Enquanto isso eu "
                    "respondo, sem depender de nada: metodologia SMC "
                    "(estrutura, liquidez, order block, FVG, premium e "
                    "desconto, confirmação de reversão, gestão de risco), "
                    "macro (Fed e juros, payroll, inflação, VIX, balanços, dia "
                    "de notícia), cotação real e notícia das casas de mercado. "
                    "E os comandos seguem: 'status', 'liga o motor', 'zera o "
                    "ciclo', 'manda no whatsapp', 'olha o gráfico' — e a "
                    "configuração da ferramenta ('o dia da conta 1 começa às "
                    "19h', 'risco de 1% por operação', ou 'como está "
                    "configurado o risco do plano da conta 1'), que eu leio e "
                    "gravo aqui mesmo, sem depender da API.")
        self._chat_entregar_resposta(resposta)

    def _ler_nivel_por_ocr(self, caminho, pergunta):
        """A resposta da pergunta de nível, lida do PIXEL — ou None.

        None aqui NUNCA significa 'não tem'. Significa 'não li', e o caminho
        normal (modelo + segunda leitura + guardas) continua valendo. Esta
        camada só ADICIONA certeza; ela não pode tirar resposta de ninguém."""
        try:
            if not os.path.exists(caminho):
                return None
            nome = indicador_da_pergunta(pergunta)
            if not nome:
                return None
            texto = plataforma.ler_texto_da_imagem(caminho)
            if not texto.strip():
                motor, ok = plataforma.motor_de_ocr()
                if not ok and not getattr(self, "_avisou_sem_ocr", False):
                    self._avisou_sem_ocr = True
                    self.log(f"ℹ️ Leitura exata de indicadores DESLIGADA: {motor}. "
                             "Sem ela, o número do indicador depende do modelo "
                             "— que erra e não avisa.")
                return None
            valores = ler_indicadores_da_legenda(texto)
            resposta = resposta_do_indicador_lido(nome, valores)
            if resposta:
                self.log(f"🔍 OCR local leu '{nome}' na legenda — resposta "
                         "montada sem API, sem internet e sem cota.")
            return resposta
        except Exception as e:
            self.log(f"(OCR não conseguiu ler a imagem: {str(e)[:100]})")
            return None

    def _confirmar_nivel_lido(self, client, modelos, parte_anexo, pergunta, resposta):
        """Lê o MESMO indicador uma segunda vez, na MESMA imagem, com um pedido
        mínimo — e compara.

        Por que uma segunda leitura e não um prompt melhor: prompt melhor muda
        a FORMA da resposta, não a verdade dela. A 2.25.0 exigiu o número junto
        do nome do indicador e conseguiu exatamente isso — a evasão ('acima
        dela') virou invenção ('exatamente em 7752.34', com a legenda dizendo
        7769.56). Número inventado não se repete igual; número lido, sim.

        Falha aqui nunca piora a resposta: sem confirmação, entrega o que veio.
        """
        try:
            if not pergunta_onde_esta_indicador(pergunta):
                return resposta
            indicador = indicador_da_pergunta(pergunta)
            if not indicador:
                return resposta
            dito = extrair_valor_do_indicador(indicador, resposta)
            if dito is None:
                return resposta          # não afirmou número: nada a conferir
            pedido = (
                f"Olhe SOMENTE a legenda de dados desta imagem e responda com "
                f"UM NÚMERO e nada mais: qual é o valor de {indicador}?\n"
                "Se o valor não estiver escrito na imagem, responda exatamente "
                "NAO_LEGIVEL. Não estime, não calcule, não use o preço do "
                "ativo no lugar. Só o número que está impresso.")
            confirmado = None
            for modelo in (modelos or [])[:2]:
                try:
                    r = client.models.generate_content(
                        model=modelo, contents=[parte_anexo, pedido],
                        config=types.GenerateContentConfig(
                            temperature=0.0, max_output_tokens=24))
                    if r and r.text:
                        confirmado = numero_da_segunda_leitura(r.text)
                        break
                except Exception:
                    continue
            texto, instavel = conferir_leitura_de_nivel(
                resposta, indicador, dito, confirmado)
            if instavel:
                self.log(f"🛡️ TIGER: li '{indicador}' duas vezes na mesma "
                         f"imagem e saíram {dito:g} e "
                         f"{('%g' % confirmado) if confirmado is not None else 'nada'}"
                         " — número recusado em vez de entregue.")
            return texto
        except Exception:
            return resposta

    def _completar_resposta(self, client, modelo, config, conteudo, comeco):
        """Pede a continuação de uma resposta que bateu no teto e emenda as duas.
        Uma rodada só: se ainda assim não fechar, devolve o que tem em vez de
        ficar queimando cota."""
        try:
            pedido = list(conteudo) + [
                f"\nVocê já escreveu isto:\n{comeco}\n\n"
                "Continue EXATAMENTE de onde parou, sem repetir nada do que já "
                "está escrito, e FECHE o raciocínio em no máximo 3 frases."]
            r2 = client.models.generate_content(
                model=modelo, contents=pedido, config=config)
            if r2 and r2.text:
                emenda = r2.text.strip()
                if emenda:
                    junta = "" if comeco.endswith((" ", "\n")) else " "
                    return f"{comeco}{junta}{emenda}"
        except Exception:
            pass
        return comeco

    def _preco_de_referencia(self, pergunta, resposta=""):
        """Preço REAL do ativo de que se está falando. Devolve (preço, nome).

        Serve para conferir número afirmado contra número medido. O ativo sai
        da PERGUNTA primeiro e só depois da resposta — se saísse do último
        ativo que o motor leu, uma pergunta sobre ouro seria conferida contra
        o preço do índice, e a trava viraria uma fábrica de alarme falso.

        Sem cotação confiável devolve (None, "") — e aí não se confere nada.
        Uma conferência com preço chutado seria o mesmo defeito que ela existe
        para pegar."""
        alvo = simbolo_do_texto(pergunta) or simbolo_do_texto(resposta)
        if not alvo:
            return None, ""
        simbolo, nome = alvo[0], alvo[1]
        try:
            cot = cotacao_mercado(simbolo) or {}
        except Exception:
            cot = {}
        preco = cot.get("preco")
        if preco:
            return float(preco), str(nome).upper()
        # Sem web: só vale a leitura do motor se for do MESMO ativo.
        ua = getattr(self, "_ultima_analise", None) or {}
        lido = simbolo_do_texto(str(ua.get("ativo") or ""))
        if lido and lido[0] == simbolo and ua.get("preco"):
            return float(ua["preco"]), str(nome).upper()
        return None, ""

    def _chat_entregar_resposta(self, resposta):
        """Fim de um turno com o modelo: registra em texto, fala se for o caso
        e digita no terminal (sempre pela fila única).

        Aqui passa SÓ o que veio do modelo — e o modelo não executa nada. Por
        isso a guarda anti-mentira roda incondicionalmente neste ponto: as
        respostas de ação real (zerar, WhatsApp, motor, lição) são escritas por
        _chat_responder e nunca chegam aqui."""
        resposta, censurou = censurar_alegacao_falsa(resposta)
        if censurou:
            self.log("🛡️ TIGER: removida uma alegação de ação não executada "
                     "da resposta do modelo.")
        # A EVASÃO DE NÍVEL. "Onde está a VWAP?" → "o preço está acima dela".
        # O prompt já proíbe, mas prompt é pedido, não garantia: aqui é o app
        # que confere se o número do indicador saiu, e cola a admissão quando
        # não saiu. Vale para qualquer provedor — Gemini, OpenAI, o que for.
        resposta, corrigiu = corrigir_enrolacao_de_nivel(
            getattr(self, "_ultimo_pedido", ""), resposta)
        if corrigiu:
            self.log("🛡️ TIGER: a resposta não trazia o nível do indicador — "
                     "admissão anexada em vez da enrolação.")
        # ELE ESTÁ POSICIONADO OU NÃO? O app SABE — basta conferir.
        try:
            abertas = [p for p in posicoes_do_ciclo()
                       if p.get("status") == "ABERTA"]
        except Exception:
            abertas = None          # sem leitura confiável, não se corrige nada
        if abertas is not None:
            resposta, erro_pos = conferir_posicao_alegada(resposta, abertas)
            if erro_pos == "inventou":
                self.log("🛡️ TIGER: a resposta dizia que ele está posicionado e "
                         "não há posição aberta — correção anexada.")
            elif erro_pos == "omitiu":
                self.log("🛡️ TIGER: a resposta dizia que ele está zerado e há "
                         "posição ABERTA — correção anexada.")
        # UM RECORDE ABAIXO DO PREÇO DE AGORA É IMPOSSÍVEL.
        # 13/08 16:31: "a máxima histórica do S&P 500 é aproximadamente 2.924
        # pontos" — com o motor dela lendo 7.812 no mesmo chat. O preço vem do
        # ativo que a PERGUNTA cita (nunca do último ativo lido por acaso),
        # senão a conferência compararia ouro com índice.
        try:
            ref_preco, ref_nome = self._preco_de_referencia(
                getattr(self, "_ultimo_pedido", "") or "", resposta)
            resposta, impossivel = conferir_maxima_historica(
                resposta, ref_preco, ref_nome)
            if impossivel:
                self.log(f"🛡️ TIGER: a resposta afirmou máxima histórica "
                         f"{impossivel:,.2f} com o preço real em "
                         f"{ref_preco:,.2f} — impossível. Correção anexada.")
        except Exception:
            pass          # conferência é rede de proteção, nunca derruba o turno
        # COMPRA COM STOP ACIMA DA ENTRADA NÃO É COMPRA.
        # 17/08, das 10:43 às 10:59: ela sugeriu COMPRA com stop 7813.50 acima
        # da entrada 7805.25 e alvo 7796.75 abaixo. Ele perguntou quatro vezes
        # se estava certo; nas quatro ela pediu desculpa e repetiu os mesmos
        # números. É aritmética — o app consegue o que o prompt não conseguiu.
        resposta, incoerencia = conferir_coerencia_do_cenario(resposta)
        if incoerencia:
            self.log(f"⛔ TIGER: cenário incoerente barrado — {incoerencia}.")
        # OS NÚMEROS DA CONTA DELE, CONFERIDOS CONTRA O DISCO.
        resposta, divergencias = conferir_numeros_da_mesa(
            resposta, self._fatos_da_mesa())
        for chave, dito, real in divergencias:
            self.log(f"🛡️ TIGER: '{chave}' saiu como US$ {dito:,.2f} e o "
                     f"registrado é US$ {real:,.2f} — correção anexada.")
        registrar_msg_chat("ia", resposta)
        self._ia_falar(resposta, forcar=bool(getattr(self, "_chat_por_voz", False)))
        self.after(0, lambda: self._chat_digitar(resposta))

    # ---------------- Comando por VOZ ----------------
    def _capturar_audio(self, rec):
        """Grava a sua fala e devolve um AudioData para transcrição.
        1º caminho: sounddevice (instala em qualquer Python — inclusive 3.14).
        2º caminho: sr.Microphone/pyaudio, se por acaso estiver instalado.
        PACIÊNCIA: só corta após ~2,2 s de silêncio — pausa para pensar no meio
        da frase NÃO encerra a gravação (antes cortava com 1 s e atropelava)."""
        if VOZ_SD:
            TAXA, BLOCO = 16000, 1600            # blocos de 0,1 s
            MAX_SEG = 25                         # teto de 25 s de fala
            SILENCIO_CORTE = 22                  # corta com 2,2 s mudo
            ESPERA_INICIO = 80                   # até 8 s esperando começar a falar
            import array
            capturado, silencio, falou, mudo_inicio = [], 0, False, 0

            def energia_de(dados):
                amostras = array.array("h", dados)
                return (sum(a * a for a in amostras) / max(len(amostras), 1)) ** 0.5

            with abrir_stream_microfone(TAXA, BLOCO) as stream:
                # Limiar calibrado pelo silêncio da SUA sala (com piso e teto):
                # microfone de ganho baixo passava despercebido com valor fixo.
                ambiente = []
                for _ in range(4):
                    bloco, _ov = stream.read(BLOCO)
                    capturado.append(bytes(bloco))
                    ambiente.append(energia_de(bytes(bloco)))
                limiar = min(max(min(ambiente) * 2.5, 90), 400)
                for _ in range(int(MAX_SEG * TAXA / BLOCO) + ESPERA_INICIO):
                    bloco, _ov = stream.read(BLOCO)
                    dados = bytes(bloco)
                    capturado.append(dados)
                    energia = energia_de(dados)
                    if energia > limiar:
                        falou, silencio = True, 0
                    elif falou:
                        silencio += 1
                        if silencio >= SILENCIO_CORTE:
                            break
                    else:
                        mudo_inicio += 1
                        if mudo_inicio >= ESPERA_INICIO:
                            break
            if not falou:
                raise sr.WaitTimeoutError("nenhuma fala detectada")
            return sr.AudioData(b"".join(capturado), TAXA, 2)
        # Fallback: microfone clássico (exige pyaudio)
        with sr.Microphone() as mic:
            rec.adjust_for_ambient_noise(mic, duration=0.4)
            return rec.listen(mic, timeout=8, phrase_time_limit=25)

    def _chat_parar_fala(self):
        """Botão ⏹ Parar fala. Cala na hora, sem esperar o fim do parágrafo."""
        if parar_fala():
            self._chat_status("⏹ parei de falar", "#ff9f9f")
        else:
            self._chat_status("não estava falando", "#8a92a5")

    def _chat_ouvir(self):
        # CLICOU NO 🎤 = "cala a boca e me escuta". Se ela estiver falando,
        # para na hora: quem clicou quer falar AGORA, não no fim do parágrafo.
        if parar_fala():
            self._chat_status("🐯 parei de falar — pode falar", "#3fb950")
        if not VOZ_SR:
            self._chat_escrever(
                "sistema", f"({texto_falta_voz()})", persistir=False)
            return
        if not VOZ_SD:
            # Sem sounddevice, o único captador é o pyaudio — avisa se faltar.
            try:
                import pyaudio  # noqa: F401
            except ImportError:
                self._chat_escrever(
                    "sistema", f"({texto_falta_voz()})", persistir=False)
                return
        if self._chat_ocupada or self._ouvindo:
            return
        # Marca ANTES de abrir a thread: assim a escuta contínua (OLÁ TIGER)
        # enxerga na hora que o microfone foi tomado e não abre um segundo
        # stream em cima deste — dois streams brigando deixavam o microfone
        # "em uso" sem ninguém conseguir ouvir de fato.
        self._ouvindo = True

        def tarefa():
            self.after(0, lambda: self._chat_status(
                "🎤 ouvindo… (pode falar com calma)", "#ff6b6b"))
            try:
                rec = sr.Recognizer()
                rec.energy_threshold = 300
                rec.dynamic_energy_threshold = True
                audio = self._capturar_audio(rec)
                self.after(0, lambda: self._chat_status("transcrevendo…", "#ff9f43"))
                texto = rec.recognize_google(audio, language="pt-BR")
            except sr.WaitTimeoutError:
                self.after(0, lambda: self._chat_status("pronta", "#3fb950"))
                self.after(0, lambda: self._chat_escrever(
                    "sistema", "(não ouvi nada — clique no 🎤 e fale em seguida)",
                    persistir=False))
                return
            except sr.UnknownValueError:
                self.after(0, lambda: self._chat_status("pronta", "#3fb950"))
                self.after(0, lambda: self._chat_escrever(
                    "sistema", "(não entendi o áudio — pode repetir?)", persistir=False))
                return
            except sr.RequestError:
                self.after(0, lambda: self._chat_status("pronta", "#3fb950"))
                self.after(0, lambda: self._chat_escrever(
                    "sistema", "(transcrição indisponível — sem internet no momento)",
                    persistir=False))
                return
            except Exception as e:
                # Mesma regra do OLÁ TIGER: biblioteca faltando NÃO é permissão
                # nem microfone ocupado, e a mensagem tem de dizer qual é e o
                # comando exato — não deixar o trader caçando no lugar errado.
                self.after(0, lambda: self._chat_status("pronta", "#3fb950"))
                self.after(0, lambda er=e: self._chat_escrever(
                    "sistema", "(🎤 " + explicar_falha_do_microfone(er) + ")",
                    persistir=False))
                return
            finally:
                self._ouvindo = False
            self.after(0, lambda: self._chat_status("pronta", "#3fb950"))

            def entregar(t=texto):
                # Pedido chegou por VOZ → toda a resposta deste turno sai por
                # voz também (com o texto registrado no histórico).
                self._chat_por_voz = True
                self._chat_escrever("voce", f"🎤 {t}")
                self._chat_processar(t)
            self.after(0, entregar)

        threading.Thread(target=tarefa, daemon=True).start()

    # ---------------- "OLÁ TIGER" — palavra de ativação ----------------
    # Escuta contínua e leve em segundo plano (como Alexa/Siri/Ok Google):
    # grava trechos curtos, ignora silêncio, e só transcreve quando há som.
    # Ao ouvir "Olá Tiger" ela atende — se o pedido veio na mesma frase
    # ("Olá Tiger, qual o status?"), já executa direto.
    def _tiger_alternar(self):
        salvar_config({"ia_tiger": bool(self.ia_tiger_var.get())})
        if self.ia_tiger_var.get():
            self._tiger_iniciar()
        else:
            self._chat_escrever("sistema", "(modo OLÁ TIGER desligado)",
                                 persistir=False)

    def _nome_da_voz_no_menu(self):
        """O NOME da voz a partir do rótulo do menu ('Luciana  ·  pt_BR').

        O rótulo mostra o idioma para ele não escolher às cegas; o `say`
        precisa só do nome. Traduzir num lugar só evita que a metade errada
        do rótulo chegue ao sistema."""
        rotulo = (self._var_voz.get() or "").strip()
        if rotulo.startswith("("):
            return ""
        return (getattr(self, "_vozes_por_rotulo", {}).get(rotulo)
                or rotulo.split("  ·  ")[0].strip())

    def _trocar_voz(self, _rotulo=None):
        """Grava a voz, RELÊ do disco e fala uma frase com ela — confirmação
        que se ouve vale mais que confirmação que se lê."""
        nome = self._nome_da_voz_no_menu()
        gravado = salvar_voz_escolhida(nome)
        if str(gravado or "").lower() != str(nome or "").lower():
            self.log("⚠️ NÃO consegui gravar a voz escolhida.")
            return
        self.log(f"🔊 Voz da TIGER: {gravado or 'a melhor do sistema'}.")
        self._experimentar_voz()

    def _experimentar_voz(self):
        nome = self._nome_da_voz_no_menu()
        if not nome:
            nome = plataforma.voz_portugues_macos() or ""
        if not nome:
            self.log("ℹ️ Não achei nenhuma voz de português instalada neste "
                     "Mac. Clique em '⬇️ Baixar mais vozes' aqui na aba que "
                     "eu abro o painel certo do sistema.")
            return
        plataforma.experimentar_voz(nome, velocidade_da_voz())

    def _abrir_ajustes_de_voz(self):
        """Abre o painel do Mac onde se BAIXAM vozes novas.

        As boas de português (Premium, Aprimorada) não vêm instaladas. Mandar
        alguém navegar cinco menus foi o roteiro que já falhou duas vezes
        nesta casa — com o Node.js e com o Ollama."""
        if not plataforma.E_MACOS:
            self.log("ℹ️ A biblioteca de vozes que dá para escolher aqui é "
                     "do macOS. Neste sistema a fala sai com a voz que o "
                     "próprio sistema já traz.")
            return
        if plataforma.abrir_ajustes_de_voz():
            self.log("🔊 Abri os Ajustes do Sistema. Vá em 'Conteúdo Falado' → "
                     "'Voz do sistema' → 'Gerenciar vozes' e baixe as de "
                     "Português (Brasil) marcadas como Premium ou Aprimorada. "
                     "Depois reabra o SMC Quant Pro: elas aparecem na lista.")
        else:
            self.log("⚠️ Não consegui abrir os Ajustes daqui. Abra à mão: "
                     "Ajustes do Sistema → Acessibilidade → Conteúdo Falado → "
                     "Voz do sistema → Gerenciar vozes.")

    def diagnostico_microfone(self):
        """Diz TUDO o que se sabe sobre o microfone, em uma tela.

        Isto existe porque ele já relatou o mesmo defeito quatro vezes e cada
        rodada minha corrigiu uma causa possível sem NUNCA saber qual era a
        real. Adivinhar em série é caro. Estas seis linhas são a diferença
        entre 'não funciona' e 'não funciona POR ISTO'."""
        linhas = ["🎤 DIAGNÓSTICO DO MICROFONE", ""]
        linhas.append(f"• Bibliotecas: SpeechRecognition={'ok' if VOZ_SR else 'FALTA'}"
                      f" · sounddevice={'ok' if VOZ_SD else 'FALTA'}")
        if not VOZ_SD and VOZ_SD_ERRO:
            linhas.append(f"  causa: {VOZ_SD_ERRO[:150]}")
        if plataforma.E_MACOS:
            estado = plataforma.estado_permissao_microfone()
            quem = plataforma.quem_pede_a_permissao()
            linhas.append(f"• Permissão do macOS: {estado.upper()}")
            linhas.append(f"• Quem o macOS lista: “{quem}” "
                          "(procure ESTE nome, não 'SMC Quant Pro')")
            if estado == "nunca_pedido":
                linhas.append("  ⚠️ NUNCA PEDIDO é a explicação de 'não aparece "
                              "na lista': o macOS só lista quem já pediu. Ligue "
                              "o OLÁ TIGER que eu peço agora.")
            elif estado == "negado":
                linhas.append("  ⚠️ NEGADO. Marque na tela que vou abrir, FECHE "
                              "e ABRA o programa (a permissão só vale a partir "
                              "do próximo arranque).")
            elif estado == "desconhecido":
                linhas.append("  ⚠️ Não consegui consultar — falta o "
                              "pyobjc-framework-AVFoundation. Rode o "
                              "INSTALAR_MAC.command de novo.")
        try:
            if VOZ_SD:
                dev = _sd.query_devices(kind="input")
                linhas.append(f"• Entrada padrão: {dev['name']} "
                              f"({int(dev.get('default_samplerate', 0))} Hz)")
        except Exception as e:
            linhas.append(f"• Entrada padrão: NÃO consegui ler ({str(e)[:80]})")
        linhas.append("")
        linhas.append("Se tudo acima estiver ok e ainda vier silêncio, é o "
                      "dispositivo errado: troque a entrada padrão em Ajustes "
                      "do Sistema → Som → Entrada.")
        texto = "\n".join(linhas)
        self.log(texto)
        return texto

    def _tiger_iniciar(self):
        if not (VOZ_SR and VOZ_SD):
            self.ia_tiger_var.set(False)
            salvar_config({"ia_tiger": False})
            self._chat_escrever("sistema", f"({texto_falta_voz()})",
                                persistir=False)
            return
        # ---- A PERMISSÃO É PEDIDA ANTES DE ABRIR O MICROFONE ----
        # Queixa dele, 13/08: "não aparece na lista de permissão do Mac".
        # Essa é a chave. No macOS, um programa só ENTRA na lista de Microfone
        # depois de PEDIR a permissão pela API do sistema. O PortAudio abre o
        # dispositivo por um caminho que nem sempre dispara esse pedido — então
        # não aparece prompt, não aparece na lista, e o sistema devolve
        # SILÊNCIO, sem erro nenhum. Era exatamente o sintoma.
        if plataforma.E_MACOS:
            estado = plataforma.pedir_permissao_microfone()
            quem = plataforma.quem_pede_a_permissao()
            if estado == "negado":
                self.ia_tiger_var.set(False)
                salvar_config({"ia_tiger": False})
                plataforma.abrir_permissao_microfone()
                self._chat_escrever("sistema", (
                    f"(🐯 o microfone está NEGADO para “{quem}” no macOS — por "
                    "isso não chega som nenhum. Abri a tela de permissões: "
                    f"marque “{quem}” em Microfone, FECHE e ABRA o programa, e "
                    "ligue o OLÁ TIGER de novo. Enquanto estiver negado, eu "
                    "não consigo ouvir — e prefiro te dizer isso a ficar "
                    "escutando o silêncio.)"), persistir=False)
                return
            if estado == "desconhecido":
                self.log("ℹ️ Não consegui consultar a permissão de microfone "
                         "(falta o pyobjc-framework-AVFoundation). Vou tentar "
                         "abrir o microfone assim mesmo — se vier silêncio, é "
                         "quase certo que é permissão.")
            elif estado == "restrito":
                self._chat_escrever("sistema", (
                    "(🐯 o microfone está RESTRITO por política deste Mac — "
                    "não é algo que eu ou você consigamos liberar aqui.)"),
                    persistir=False)
            else:
                self.log(f"🎤 Permissão de microfone: {estado} (o macOS lista "
                         f"este pedido como “{quem}”).")
        if self._tiger_rodando:
            return
        self._tiger_rodando = True
        self._tiger_avisou_mudo = False
        self._tiger_avisou_erro = False
        try:
            dispositivo = _sd.query_devices(kind="input")["name"]
        except Exception:
            dispositivo = "padrão do sistema"
        self._chat_escrever(
            "sistema",
            "(🐯 modo OLÁ TIGER LIGADO — escutando pelo microfone "
            f"“{dispositivo}”. Diga 'Olá Tiger' para me chamar, ou já emende o "
            "pedido: 'Olá Tiger, qual o status?'. Tudo o que eu ouvir aparece "
            "aqui no chat — você VÊ que estou escutando.)", persistir=False)
        threading.Thread(target=self._tiger_loop, daemon=True).start()

    def _tiger_pausada(self):
        """A escuta contínua dá lugar quando o 🎤 está gravando um pedido ou a
        TIGER está pensando/digitando.

        ELA NÃO PAUSA MAIS ENQUANTO FALA — de propósito. Antes pausava, e por
        isso era impossível cortá-la no meio: você falava por cima e ela seguia
        até o fim do parágrafo. Agora continua ouvindo durante a própria fala,
        justamente para pegar o 'Olá Tiger' e se calar na hora. O eco da voz
        dela é filtrado em _tiger_eco()."""
        return self._ouvindo or self._chat_ocupada

    @staticmethod
    def _tiger_eco(texto):
        """O que o microfone captou é a VOZ DELA saindo do alto-falante?
        Enquanto fala, o mic ouve o próprio programa; sem este filtro ela
        transcreveria a si mesma e responderia à própria fala."""
        dito = _norm_busca(_TTS_TEXTO)
        ouvido = _norm_busca(texto)
        if not dito or not ouvido:
            return False
        if ouvido in dito:
            return True
        # Trecho do meio da fala: compara palavra a palavra.
        palavras = [p for p in re.findall(r"[a-z0-9]+", ouvido) if len(p) > 3]
        if not palavras:
            return False
        dentro = sum(1 for p in palavras if p in dito)
        return dentro >= max(2, len(palavras) * 0.6)

    def _tiger_capturar_frase(self, stream, rms):
        """Escuta pelo stream JÁ ABERTO até pegar uma FRASE completa.
        Diferente da versão anterior (que gravava blocos fixos de 2,5 s e
        perdia o chamado dito na fronteira ou durante a transcrição), aqui:
        • o microfone fica aberto o tempo todo (sem janelas surdas);
        • a gravação começa quando há som e só fecha após ~1 s de silêncio;
        • um pré-rolo de 0,4 s garante que o 'Ei' do começo não seja cortado.
        Devolve: os bytes da frase; b"" se ficou um bom tempo sem captar som
        nenhum (o loop usa isso para avisar que o microfone está mudo); ou
        None se a escuta foi interrompida (🎤 / pensando / TTS / desligada)."""
        import collections
        BLOCO = 1600
        SEM_SOM_LIMITE = 450                       # ~45 s sem nada = mudo
        sem_som = 0
        # Calibração do ambiente (~0,5 s): o limiar de "tem voz" se adapta ao
        # ruído da sala, MAS com piso e TETO fixos. O teto é essencial: se a
        # calibração pegar um momento barulhento, sem ele o limiar subia tanto
        # que a fala normal nunca disparava — e a escuta parecia surda.
        ambiente = []
        for _ in range(5):
            bloco, _ov = stream.read(BLOCO)
            ambiente.append(rms(bytes(bloco)))
        limiar = min(max(min(ambiente) * 2.5, 90), 400)
        prerolo = collections.deque(maxlen=6)      # 0,6 s antes do 1º som
        frase, silencio, falando = [], 0, False
        while True:
            try:
                if not self.ia_tiger_var.get():
                    return None
            except Exception:
                return None                        # janela fechada
            if self._tiger_pausada():
                return None
            bloco, _ov = stream.read(BLOCO)
            dados = bytes(bloco)
            energia = rms(dados)
            if not falando:
                prerolo.append(dados)
                if energia > limiar:
                    falando = True
                    frase = list(prerolo)
                    silencio = 0
                else:
                    sem_som += 1
                    if sem_som >= SEM_SOM_LIMITE:
                        return b""                 # microfone mudo — avisa
            else:
                frase.append(dados)
                if energia > limiar:
                    silencio = 0
                else:
                    silencio += 1
                    if silencio >= 12:             # ~1,2 s calado = frase completa
                        return b"".join(frase)
                if len(frase) >= 80:               # teto de 8 s por frase
                    return b"".join(frase)

    def _tiger_loop(self):
        TAXA, BLOCO = 16000, 1600
        import array

        def rms(dados):
            amostras = array.array("h", dados)
            return (sum(a * a for a in amostras) / max(len(amostras), 1)) ** 0.5

        rec = sr.Recognizer()
        try:
            while True:
                try:
                    if not self.ia_tiger_var.get():
                        break
                except Exception:
                    break                          # janela fechada
                if self._tiger_pausada():
                    time.sleep(0.3)
                    continue
                # Não sobrescreve na hora um aviso recente de "ouvi ..." — era
                # por isso que o retorno visual sumia antes de você conseguir ler.
                if time.time() >= getattr(self, "_tiger_status_ate", 0):
                    self.after(0, lambda: self._chat_status(
                        "🐯 à escuta — diga 'Olá Tiger'", "#ff9f43"))
                try:
                    with abrir_stream_microfone(TAXA, BLOCO) as stream:
                        frase = self._tiger_capturar_frase(stream, rms)
                except Exception as e:
                    self.after(0, lambda er=e: self._chat_escrever(
                        "sistema",
                        "(🐯 não consegui abrir o microfone: "
                        + explicar_falha_do_microfone(er) + ")",
                        persistir=False))
                    time.sleep(5)
                    continue
                if frase is None:
                    continue                       # interrompida (🎤/pensando/TTS)
                if frase == b"":
                    # MICROFONE ABERTO E MUDO. No macOS isto tem UMA causa
                    # dominante, e não é o dispositivo errado: é a PERMISSÃO DE
                    # MICROFONE. Quando o app não tem a permissão, o macOS NÃO
                    # devolve erro — ele entrega silêncio, zeros. O stream abre,
                    # o nome do dispositivo é lido corretamente, e não chega som
                    # nenhum. Foi exatamente o que o log de 11/08 mostrou às
                    # 18:32: "escutando pelo MacBook Air Microphone" seguido de
                    # "não chega som nenhum".
                    #
                    # A mensagem anterior mandava trocar o dispositivo de
                    # entrada — o lugar errado. E há uma armadilha a mais: quem
                    # aparece na lista de permissões é o processo RESPONSÁVEL.
                    # Abrindo pelo .command (que abre o Terminal), quem precisa
                    # do visto é o TERMINAL, não o "SMC Quant Pro". O trader
                    # procura pelo nome do programa, não acha, e conclui que já
                    # autorizou.
                    if not getattr(self, "_tiger_avisou_mudo", False):
                        self._tiger_avisou_mudo = True
                        try:
                            dev = _sd.query_devices(kind="input")["name"]
                        except Exception:
                            dev = "desconhecido"
                        if plataforma.E_MACOS:
                            quem = plataforma.quem_pede_a_permissao()
                            msg = (
                                f"(🐯 o microfone “{dev}” abriu, mas não chega "
                                "som nenhum.\n\n"
                                "NO MAC ISSO É QUASE SEMPRE A PERMISSÃO DE "
                                "MICROFONE — e ela não dá erro: o sistema "
                                "simplesmente entrega silêncio.\n\n"
                                "Abri a tela de permissões para você. Marque "
                                f"“{quem}” na lista de Microfone.\n"
                                "ATENÇÃO: como você abriu o programa por aí, é "
                                f"“{quem}” que aparece na lista — NÃO procure "
                                "por 'SMC Quant Pro'.\n\n"
                                "Depois de marcar, FECHE e ABRA o programa "
                                "(a permissão só vale a partir do próximo "
                                "arranque) e ligue o OLÁ TIGER de novo.\n\n"
                                f"Se “{quem}” já estiver marcado, aí sim pode "
                                "ser o dispositivo errado: troque a entrada "
                                "padrão em Ajustes do Sistema → Som → Entrada.)")
                            try:
                                plataforma.abrir_permissao_microfone()
                            except Exception:
                                pass
                        else:
                            msg = (
                                f"(🐯 estou escutando pelo microfone “{dev}” mas "
                                "não chega som nenhum há um tempo. Se esse não é "
                                "o seu microfone, troque o dispositivo de ENTRADA "
                                f"padrão em {ONDE_TROCAR_MIC} e desligue/religue "
                                "o OLÁ TIGER.)")
                        self.after(0, lambda m=msg: self._chat_escrever(
                            "sistema", m, persistir=False))
                    continue
                self._tiger_avisou_mudo = False    # chegou som: zera o aviso
                try:
                    texto = rec.recognize_google(
                        sr.AudioData(frase, TAXA, 2), language="pt-BR")
                except sr.UnknownValueError:
                    continue                       # ruído sem fala — segue escutando
                except Exception as e:
                    # Falha de transcrição NUNCA fica muda: se a internet ou o
                    # serviço do Google cair, você vê o motivo no chat (a versão
                    # anterior engolia o erro e parecia que ela era surda).
                    self._tiger_status_ate = time.time() + 4
                    self.after(0, lambda: self._chat_status(
                        "🐯 falha ao transcrever — tentando de novo", "#ff6b6b"))
                    if not getattr(self, "_tiger_avisou_erro", False):
                        self._tiger_avisou_erro = True
                        self.after(0, lambda er=e: self._chat_escrever(
                            "sistema",
                            "(🐯 eu OUVI você, mas não consegui transcrever: "
                            f"{str(er)[:120]}. A transcrição usa a internet — "
                            "confira a conexão. Sigo tentando.)", persistir=False))
                    time.sleep(2)
                    continue
                self._tiger_avisou_erro = False     # transcreveu: zera o aviso
                # ENQUANTO ELA FALA: só o chamado interessa, e o eco da própria
                # voz é descartado. É isso que permite você cortá-la no meio.
                if TTS_FALANDO and self._tiger_eco(texto):
                    continue
                acordou, resto = extrair_comando_tiger(texto)
                if acordou and TTS_FALANDO:
                    parar_fala()
                    self._tiger_status_ate = time.time() + 3
                    self.after(0, lambda: self._chat_status(
                        "🐯 parei de falar — pode falar", "#3fb950"))
                if not acordou:
                    # TRANSPARÊNCIA TOTAL: o que ela ouviu aparece NO CHAT.
                    # Você vê que a escuta está viva e como a fala foi
                    # transcrita — sem adivinhação.
                    self._tiger_status_ate = time.time() + 5
                    agora = time.time()
                    if agora - getattr(self, "_tiger_ult_feedback", 0) > 6:
                        self._tiger_ult_feedback = agora
                        self.after(0, lambda t=texto: self._chat_escrever(
                            "sistema",
                            f"(🐯 ouvi: “{t[:70]}” — para me chamar, diga "
                            "'Olá Tiger')", persistir=False))
                    else:
                        self.after(0, lambda t=texto: self._chat_status(
                            f"🐯 ouvi “{t[:38]}” — não era comigo", "#8a92a5"))
                    continue
                self._tiger_status_ate = time.time() + 3
                self.after(0, lambda: self._chat_status("🐯 te ouvi!", "#3fb950"))
                if resto:
                    # O pedido veio junto do chamado — executa direto.
                    def entregar(t=resto):
                        self._chat_por_voz = True
                        self._chat_escrever("voce", f"🎤 Olá Tiger, {t}")
                        self._chat_processar(t)
                    self.after(0, entregar)
                    time.sleep(1.5)
                else:
                    # Só chamou: responde (síncrono, para o mic não gravar a
                    # própria voz) e abre a escuta do pedido.
                    falar("Oi! Pode falar.")
                    self.after(0, self._chat_ouvir)
                    time.sleep(1.0)
        finally:
            self._tiger_rodando = False
            self.after(0, lambda: self._chat_status("pronta", "#3fb950"))

    # ------------------------------------------------------------------
    # NOTIFICAÇÃO NO COMPUTADOR (independente do WhatsApp)
    # ------------------------------------------------------------------
    # ---------------- INSTALAÇÃO ASSISTIDA DA IA LOCAL ----------------
    def _instalar_ia_local(self):
        """Um botão: baixa, instala, sobe o serviço e traz o modelo.

        POR QUE ISTO EXISTE: "baixe em ollama.com, instale, abra o Terminal e
        rode `ollama pull qwen2.5:7b`" é um roteiro que o Josevan executa uma
        vez. O CLIENTE dele não executa — ele erra o instalador, não abre
        Terminal nenhum, e a conclusão vira "o programa não funciona".

        Cada passo é reportado no Registro. Instalação silenciosa que falha
        calada é pior que instrução escrita, porque ninguém sabe onde parou."""
        if getattr(self, "_instalando_ia", False):
            self.log("⏭️ A instalação da IA local já está em andamento.")
            return
        self._instalando_ia = True
        self.btn_instalar_ia.configure(state="disabled", text="⏳ instalando…")
        threading.Thread(target=self._instalar_ia_worker, daemon=True).start()

    def _instalar_ia_worker(self):
        import tempfile
        try:
            self.log("━━━ INSTALAÇÃO DA IA LOCAL ━━━")
            # PASSO 0 — já está pronto? Reinstalar o que funciona é desperdício
            # de 5 GB e de paciência.
            #
            # DEFEITO MEU, CORRIGIDO AQUI. Esta saída antecipada só olhava se
            # havia ALGUM modelo. Com o qwen2.5:3b (texto puro) instalado, ela
            # respondia "Nada a fazer" e retornava — ANTES do passo que baixa o
            # modelo de VISÃO. Ou seja: o botão que eu criei para instalar a
            # visão nunca conseguia instalá-la, e no log dele ficou exatamente
            # isto: "A IA local JÁ está no ar. Modelos: qwen2.5:3b. Nada a
            # fazer." — com o motor logo depois sem ninguém para ler o gráfico.
            #
            # "Pronto" agora significa TEXTO E VISÃO. Faltando a visão, segue.
            instalados = ia_local_no_ar(timeout=3)
            if instalados and tem_modelo_de_visao(instalados):
                self.log(f"✅ A IA local JÁ está completa. Modelos: "
                         f"{', '.join(instalados)}. Nada a fazer.")
                return
            if instalados:
                self.log(f"ℹ️ A IA local está no ar ({', '.join(instalados)}), "
                         "mas SEM modelo de visão — e sem visão ela não lê "
                         "gráfico nenhum. Vou buscar o modelo que enxerga.")
            exe = plataforma.onde_esta("ollama")
            # PASSO 1 — baixar e instalar, se ainda não existe.
            if not exe:
                url, nome = plataforma.url_do_instalador("ollama")
                if not url:
                    self.log(f"⛔ {nome}")
                    return
                destino = os.path.join(tempfile.gettempdir(), nome)
                self.log(f"⬇️ Baixando o instalador ({nome})… "
                         "são cerca de 1 GB, pode levar alguns minutos.")
                ultimo = [0]

                def progresso(baixado, total):
                    pct = int(baixado * 100 / total) if total else 0
                    if pct >= ultimo[0] + 10:
                        ultimo[0] = pct
                        self.log(f"   ⬇️ {pct}% ({baixado/1e6:.0f} MB"
                                 + (f" de {total/1e6:.0f} MB)" if total else ")"))
                ok, msg = plataforma._baixar_arquivo(url, destino, progresso)
                if not ok:
                    self.log(f"⛔ Não consegui baixar: {msg}\n"
                             "   Confira a internet e tente de novo. Se estiver "
                             "atrás de firewall corporativo, baixe manualmente "
                             "em https://ollama.com/download")
                    return
                self.log("📦 Baixado. Instalando…")
                ok, msg = plataforma.instalar_pacote("ollama", destino, self.log)
                if not ok:
                    self.log(f"⛔ A instalação falhou: {msg}")
                    return
                exe = plataforma.onde_esta("ollama")
                self.log(f"✅ Instalado: {msg}")

            # PASSO 2 — subir o serviço. Instalado não é o mesmo que rodando,
            # e confundir os dois foi o erro do "motor no ar" na v2.19.
            if not ia_local_no_ar(timeout=3):
                self.log("🚀 Subindo o serviço da IA local…")
                plataforma.subir_servico_ia_local(exe)
                for _ in range(20):                 # até ~40 s
                    time.sleep(2)
                    if ia_local_no_ar(timeout=2) is not None and \
                            plataforma.porta_responde(11434):
                        break
                if not plataforma.porta_responde(11434):
                    self.log("⛔ O serviço não subiu. No Mac, abra o aplicativo "
                             "Ollama uma vez pelo Finder (ele pede permissão na "
                             "primeira execução) e clique aqui de novo.")
                    return
                self.log("✅ Serviço no ar (localhost:11434).")

            # PASSO 3 — o modelo. Sem ele, o serviço sobe e não pensa.
            modelo, motivo = modelo_local_recomendado()
            ja = ia_local_no_ar(timeout=3) or []
            if any(m.startswith(modelo.split(":")[0]) for m in ja):
                self.log(f"✅ Modelo já presente: {', '.join(ja)}")
            else:
                self.log(f"🧠 Baixando o modelo {modelo} — {motivo}.\n"
                         "   São alguns GB; é a parte demorada, e acontece "
                         "UMA vez só.")
                ok, msg = plataforma.baixar_modelo_ia_local(exe, modelo, self.log)
                if not ok:
                    self.log(f"⛔ Não consegui trazer o modelo: {msg}")
                    return

            # PASSO 3b — O MODELO QUE ENXERGA. Sem ele a IA local não serve
            # para o motor: qwen2.5 é texto puro e não vê imagem nenhuma. Foi
            # por isso que, em 13/08, o ciclo morreu com a Gemini fora do ar e
            # a IA local instalada e no ar.
            visao = modelo_visao_recomendado()
            ja = ia_local_no_ar(timeout=3) or []
            if not tem_modelo_de_visao(ja):
                self.log(f"👁 Baixando o modelo de VISÃO {visao} — é ele que "
                         "permite ler o gráfico quando a Gemini estiver fora. "
                         "Mais alguns GB, também uma vez só.")
                ok, msg = plataforma.baixar_modelo_ia_local(exe, visao, self.log)
                if not ok:
                    self.log(f"⚠️ Não consegui trazer o modelo de visão: {msg}. "
                             "A IA local ainda responde por texto; a leitura de "
                             "gráfico continua dependendo da Gemini.")
            else:
                self.log("✅ Modelo de visão já presente: "
                         f"{modelo_de_visao_instalado(ja)}")

            # PASSO 4 — CONFERIR DE VERDADE, com uma pergunta real. Dizer
            # "instalado" sem testar seria repetir o erro da chave dobrada.
            self.log("🧪 Testando com uma pergunta real…")
            mensagens = [{"role": "user", "content": "Responda apenas: OK"}]
            try:
                texto = _pedir_openai(PROVEDORES_IA["local"]["url"], "local",
                                      modelo, mensagens, timeout=120)
            except Exception as e:
                texto = None
                self.log(f"   (falha no teste: {str(e)[:140]})")
            if texto and texto.strip():
                self.log("━━━ ✅ PRONTO. A IA LOCAL RESPONDEU. ━━━\n"
                         "   A partir de agora, quando a Gemini ficar sem cota, "
                         "a pergunta vai para o modelo que roda AQUI — sem "
                         "chave, sem internet e sem saldo para acabar.")
                self._chat_feed("🧠 IA local instalada e respondendo. Não "
                                "dependo mais de cota para conversar.")
            else:
                self.log("⚠️ Instalei tudo, mas o teste não voltou resposta. "
                         "Reabra o SMC Quant Pro e clique em 'Verificar' — "
                         "prefiro te dizer isso a cravar que está pronto.")
        except Exception as e:
            self.log(f"⛔ Erro na instalação da IA local: {str(e)[:200]}")
        finally:
            self._instalando_ia = False
            self.after(0, lambda: self.btn_instalar_ia.configure(
                state="normal", text="⬇️ Instalar a IA LOCAL (sem chave)"))

    def _subir_ia_local_no_inicio(self):
        """Religa a IA local na abertura do programa, se ela já foi instalada.

        NUNCA instala nada: se o Ollama não estiver na máquina, esta função
        sai calada. Instalar é decisão dele, e continua sendo o botão.

        Também sai calada quando já está no ar — dizer 'subi o serviço' sobre
        um serviço que já estava rodando seria o mesmo tipo de mentira que o
        'Motor no ar' sobre processo morto, só que ao contrário."""
        try:
            time.sleep(2)                      # deixa a janela abrir primeiro
            if plataforma.porta_responde(11434):
                return
            exe = plataforma.onde_esta("ollama")
            if not exe:
                return                         # não instalado: não é problema
            plataforma.subir_servico_ia_local(exe)
            for _ in range(15):                # até ~30 s
                time.sleep(2)
                if plataforma.porta_responde(11434):
                    modelos = ia_local_no_ar(timeout=3) or []
                    self.log("🧠 IA local religada automaticamente"
                             + (f" ({', '.join(modelos[:3])})." if modelos
                                else " — mas nenhum modelo baixado ainda; "
                                     "use o botão 'Instalar a IA LOCAL'."))
                    return
            self.log("ℹ️ A IA local está instalada mas o serviço não subiu "
                     "sozinho. Clique em 'Instalar a IA LOCAL' na aba Motor "
                     "que eu tento de novo e digo o que aconteceu.")
        except Exception:
            pass          # nunca pode atrapalhar a abertura do programa

    def _verificar_ia_local(self):
        """Diz o estado REAL, com o que está de pé — nunca um palpite."""
        exe = plataforma.onde_esta("ollama")
        modelos = ia_local_no_ar(timeout=3)
        if modelos:
            self.log(f"✅ IA LOCAL no ar. Modelos: {', '.join(modelos)}. "
                     "Ela entra sozinha quando a Gemini falhar.")
        elif exe:
            self.log(f"⚠️ O Ollama está instalado ({exe}) mas o serviço NÃO "
                     "está respondendo em localhost:11434. Clique em "
                     "'Instalar a IA LOCAL' que eu subo o serviço.")
        else:
            ram = _num_gb_de_ram()
            modelo, motivo = modelo_local_recomendado(ram)
            self.log("ℹ️ IA local ainda não instalada. Clicando no botão eu "
                     f"baixo e configuro tudo — {motivo}, então o modelo "
                     f"escolhido seria o {modelo}. Precisa de internet só "
                     "nesta vez, e de alguns GB de disco.")

    def _salvar_e_testar_provedores(self):
        """Grava as chaves, RELÊ DO DISCO e TESTA de verdade — uma pergunta real
        para cada provedor configurado. Dizer 'salvo' sem testar seria repetir o
        erro da chave dobrada: o trader só descobriria que não funciona no meio
        do pregão."""
        for pid, campo in getattr(self, "_campos_provedor", {}).items():
            try:
                salvar_chave_provedor(pid, campo.get().strip())
            except Exception as e:
                self.log(f"⚠️ Não consegui gravar a chave de "
                         f"{PROVEDORES_IA[pid]['rotulo']}: {e}")
        configurados = provedores_configurados()   # releitura do disco
        if not configurados:
            self.log("ℹ️ Nenhuma chave alternativa configurada. Quando a cota da "
                     "Gemini estourar, a TIGER continua respondendo só o que dá "
                     "para responder sem modelo (status, plano, histórico, "
                     "cotação e notícia).")
            return
        self.log(f"💾 Chaves gravadas no cofre do sistema: "
                 + ", ".join(PROVEDORES_IA[p]["rotulo"] for p in configurados))
        self.log("🧪 Testando cada uma com uma pergunta real...")

        def testar():
            for pid in configurados:
                info = PROVEDORES_IA[pid]
                chave = carregar_chave_provedor(pid)
                ok, ultimo = False, None
                for modelo in info["modelos"]:
                    try:
                        msg = [{"role": "user",
                                "content": "Responda apenas: OK"}]
                        if info["formato"] == "anthropic":
                            t = _pedir_anthropic(info["url"], chave, modelo, msg, 25)
                        else:
                            t = _pedir_openai(info["url"], chave, modelo, msg, 25)
                        if t and t.strip():
                            self.log(f"   ✅ {info['rotulo']} respondeu "
                                     f"({modelo}).")
                            ok = True
                            break
                    except Exception as e:
                        ultimo = e
                        self.log(f"   ⚠️ {info['rotulo']} / {modelo}: "
                                 f"{diagnostico_de_provedor(e, info['rotulo'])}")
                if not ok:
                    # A CAUSA REAL VEM NA RESPOSTA DA API — e estava sendo
                    # trocada por um palpite triplo. No log de 12/08 a OpenAI
                    # respondeu, com todas as letras, "You have no credits
                    # remaining"; o app leu isso e disse ao trader que a chave
                    # "pode estar errada, sem crédito, ou indisponível". Ele
                    # ficou sem saber qual das três, com a resposta na mão.
                    self.log(f"   ❌ {info['rotulo']} NÃO respondeu — "
                             f"{diagnostico_de_provedor(ultimo, info['rotulo'])}")
                    if pid != "groq":
                        self.log("   💡 A Groq tem camada GRATUITA e fala o "
                                 "mesmo protocolo: console.groq.com/keys — "
                                 "cole a chave no campo Groq e teste de novo.")
        threading.Thread(target=testar, daemon=True).start()

    def _salvar_estilo_notificacao(self, rotulo=None):
        """Grava a escolha, RELÊ DO DISCO e confirma com o que ficou gravado."""
        escolha = next((k for k, v in self.ESTILOS_NOTIFICACAO.items()
                        if v == (rotulo or self._var_estilo_notif.get())), None)
        if not escolha:
            return
        salvar_config({"estilo_notificacao": escolha})
        gravado = self._estilo_notificacao()
        if gravado != escolha:
            self.log(f"⚠️ NÃO consegui gravar o estilo de aviso — continua "
                     f"'{self.ESTILOS_NOTIFICACAO[gravado]}'.")
            return
        self.log(f"🔔 Aviso de sugestão: {self.ESTILOS_NOTIFICACAO[gravado]}.")
        if gravado == "sistema":
            self.log("   (a decisão sai por 'acatar' / 'dispensar' no chat, ou "
                     "pelos botões do dashboard)")
        elif gravado == "janela" and plataforma.E_MACOS:
            self.log("   ⚠️ No macOS esta opção FAZ a tela pular para o programa "
                     "a cada aviso — é o sistema que ativa o app quando a janela "
                     "nasce. Você escolheu com essa informação.")

    def _salvar_pref_notificacao(self):
        salvar_config({"notificar_desktop": bool(self.notif_var.get())})
        self.log("🔔 Notificações no computador LIGADAS."
                  if self.notif_var.get() else
                  "🔕 Notificações no computador desligadas.")

    def _fechar_notificacao(self, win):
        """Fecha um aviso com segurança e o tira da pilha. Nunca lança erro —
        um aviso que não fecha é pior do que aviso nenhum."""
        try:
            if win.winfo_exists():
                win.destroy()
        except Exception:
            pass
        try:
            self._notif_abertas = [w for w in self._notif_abertas
                                   if w is not win and w.winfo_exists()]
        except Exception:
            self._notif_abertas = []

    def _fechar_todas_notificacoes(self):
        """Limpa a tela de uma vez. Fica no botão '🔕 Fechar avisos'."""
        for w in list(getattr(self, "_notif_abertas", [])):
            self._fechar_notificacao(w)
        self._notif_abertas = []

    # Como o aviso de nova sugestão aparece. No macOS o padrão é a notificação
    # NATIVA, porque a janela desenhada pelo Tk ativa o aplicativo e faz a tela
    # pular da corretora para cá — foi a queixa, e é comportamento do sistema,
    # não escolha do programa.
    ESTILOS_NOTIFICACAO = {
        "sistema": "Notificação do sistema (não rouba o foco)",
        "janela": "Janela na tela, com botões ACATAR / NÃO OPEREI",
        "silencioso": "Nenhum aviso na tela (só log e WhatsApp)",
    }

    def _estilo_notificacao(self):
        """'sistema' | 'janela' | 'silencioso'. Padrão: nativo no Mac, janela
        no Windows (lá a janela nunca roubou foco)."""
        padrao = "sistema" if plataforma.E_MACOS else "janela"
        v = str(carregar_config().get("estilo_notificacao", padrao)).lower()
        return v if v in self.ESTILOS_NOTIFICACAO else padrao

    def _notificar_desktop(self, titulo, linhas, cor="#1f8b4c", segundos=15,
                            sinal_id=None, direcao=None):
        """Mostra um aviso no canto da tela (sempre por cima) + um bipe. Não usa
        biblioteca externa, então funciona no .exe sem nada a mais. Respeita o
        interruptor: desligado, não aparece nada.

        Com `sinal_id`, o aviso ganha os botões ACATAR / NÃO OPEREI: você decide
        a sugestão direto da notificação, sem abrir o app."""
        if not (getattr(self, "notif_var", None) and self.notif_var.get()):
            return

        # ---- NOTIFICAÇÃO NATIVA: a única que NÃO rouba o foco ----
        # Tentei resolver isso pelo Tk (estilo 'help/noActivates') e não bastou:
        # no macOS, criar um Toplevel ATIVA o aplicativo, e brigar com isso é
        # brigar com o comportamento do sistema. A Central de Notificações do
        # próprio macOS já faz exatamente o que se quer — aparece no canto, não
        # tira o foco de ninguém, some sozinha.
        #
        # O preço é perder os botões ACATAR / NÃO OPEREI de dentro do aviso. Por
        # isso a mensagem diz, ali mesmo, que a decisão sai pelo chat ('acatar')
        # ou pelo dashboard. E quem prefere os botões escolhe "janela" na aba
        # Motor, ciente de que ali a tela vai pular.
        if self._estilo_notificacao() == "silencioso":
            return
        if self._estilo_notificacao() == "sistema":
            corpo = " · ".join(str(l) for l in linhas if l)[:230]
            if plataforma.notificacao_do_sistema(
                    titulo, corpo,
                    subtitulo=("Responda 'acatar' ou 'dispensar' no chat"
                               if sinal_id is not None else "")):
                return
            # A notificação nativa falhou: NÃO ficar calado. Cai na janela.
            self.log("(a notificação do sistema não saiu — usando o aviso na tela)")

        def mostrar():
            try:
                # Limpa da lista as janelas que já fecharam, para empilhar certo.
                self._notif_abertas = [w for w in self._notif_abertas
                                       if w.winfo_exists()]
                win = ctk.CTkToplevel(self)
                win.overrideredirect(True)          # sem barra de título
                win.attributes("-topmost", True)    # sempre visível
                # NÃO ROUBAR A TELA. No macOS, criar um Toplevel ATIVA o
                # aplicativo — o trader estava na corretora e a tela pulava
                # para cá a cada sugestão. O estilo 'help/noActivates' é o
                # mecanismo do Tk-macOS para janela flutuante que não ativa.
                # No Windows isto é um no-op (lá o problema não existe).
                plataforma.janela_sem_roubar_foco(win)
                decidivel = sinal_id is not None
                larg = 430 if decidivel else 400
                # A altura é calculada DEPOIS de montar o conteúdo (mais abaixo).
                # Antes ela era estimada na mão e ficava curta: o botão "fechar"
                # nascia fora da janela e o aviso não tinha como ser dispensado —
                # ficava preso na tela até fechar o programa.
                win.geometry(f"{larg}x60+{win.winfo_screenwidth()}+0")

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

                ctk.CTkButton(barra, text="✕ fechar", width=70, height=26,
                              fg_color="#5a3a3a", hover_color="#8b4513",
                              font=ctk.CTkFont(size=11, weight="bold"),
                              command=lambda: self._fechar_notificacao(win)
                              ).pack(side="right")

                def focar(_e=None):
                    """Clique no corpo traz o app para frente."""
                    try:
                        self.deiconify(); self.lift(); self.focus_force()
                    except Exception:
                        pass
                quadro.bind("<Button-1>", focar)
                # Botão DIREITO em qualquer lugar do aviso dispensa — saída de
                # emergência caso algum botão fique escondido por tema/DPI.
                for w in (win, quadro):
                    w.bind("<Button-3>", lambda _e, j=win: self._fechar_notificacao(j))
                win.bind("<Escape>", lambda _e, j=win: self._fechar_notificacao(j))

                # AGORA sim: mede o conteúdo montado e dimensiona a janela para
                # caber TUDO (inclusive os botões). Nada mais fica cortado.
                win.update_idletasks()
                alt = max(quadro.winfo_reqheight() + 6, 90)
                larg = max(larg, quadro.winfo_reqwidth() + 6)
                tela_l, tela_a = win.winfo_screenwidth(), win.winfo_screenheight()
                desloc = 0
                for w in self._notif_abertas:
                    try:
                        desloc += w.winfo_height() + 8
                    except Exception:
                        pass
                x = tela_l - larg - 20
                y = tela_a - alt - 70 - desloc
                win.geometry(f"{larg}x{alt}+{x}+{max(y, 10)}")

                self._notif_abertas.append(win)
                # Fechamento automático com teto de segurança: nenhum aviso passa
                # de 90 s na tela, por mais crítico que seja. O conteúdo continua
                # no log e no WhatsApp — a tela não é o registro.
                espera = int(max(5, min(segundos, 90)) * 1000)
                win.after(espera, lambda j=win: self._fechar_notificacao(j))

                # Bipe do alerta: MessageBeep no Windows, som do sistema
                # (afplay) no macOS. Falhar o som nunca derruba o aviso.
                plataforma.bipe()
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

    # ------------------------------------------------------------------
    # PREÇO AO VIVO — acompanhamento em tempo quase real
    # ------------------------------------------------------------------
    # A análise da IA roda de 5 em 5 min (custa cota de API) e lê o preço de uma
    # IMAGEM. Isso serve para ACHAR cenário, mas é lento e impreciso demais para
    # GERENCIAR ordem: o preço tocava a entrada entre duas análises e ninguém
    # via. Este poller lê o preço EXATO direto do painel da corretora a cada
    # poucos segundos (via CDP, sem custo de API) e é ele quem aciona
    # entrada/stop/alvo. Custo zero de cota, precisão de centavo.
    INTERVALO_POLLER_SEG = 3

    def _poller_preco_plataforma(self):
        """Roda a vida toda em segundo plano. Só trabalha quando há posição
        PENDENTE/ABERTA na conta ativa — sem posição, nem consulta a corretora."""
        while True:
            time.sleep(self.INTERVALO_POLLER_SEG)
            try:
                if not TRADOVATE_DISPONIVEL:
                    continue
                if not plataforma_tem_cdp(getattr(self, "plataforma_atual", "tradovate")):
                    continue
                # Nada para acompanhar? não incomoda a corretora.
                vivas = [p for p in carregar_posicoes()
                         if p.get("conta_id") == conta_ativa_id()
                         and p.get("status") in ("PENDENTE", "ABERTA")]
                if not vivas:
                    continue
                bot = self._tv_bot
                if bot is None or bot.ws is None:
                    continue      # conexão é estabelecida pelo ciclo de análise
                preco = bot.ler_preco()
                if not preco or preco <= 0:
                    continue
                self._preco_ao_vivo = preco
                ativo = vivas[0].get("ativo") or getattr(self, "_ultimo_ativo_lido", None)
                eventos = atualizar_posicoes_com_preco(
                    preco, ativo,
                    exigir_confirmacao_plataforma=self._plataforma_confirma_fills(),
                    preco_confiavel=True)
                for tipo, pos in eventos:
                    self._tratar_evento_posicao(tipo, pos, origem_preco="ao vivo")
                if eventos:
                    self.after(0, lambda: self._atualizar_dashboard(forcar=True))
            except tradovate_auto.ConexaoPerdida:
                self._tv_bot = None      # reconecta no próximo ciclo de análise
            except Exception:
                pass                      # nunca derruba o app por causa do poller

    def _tratar_evento_posicao(self, tipo, pos, origem_preco="análise"):
        """Log + WhatsApp + alerta de tela para um evento de posição. Usado tanto
        pelo ciclo de análise quanto pelo poller de preço ao vivo."""
        if tipo == "EXECUTADA":
            como = ("confirmada pela plataforma"
                    if pos.get("execucao") == "CONFIRMADA"
                    else f"detectada pelo preço {origem_preco}")
            self.log(f"✅ ENTRADA EXECUTADA: {pos['direcao']} {pos['ativo']} "
                      f"@ {pos['entry']} — {como}.")
            self._notificar_desktop(
                f"🎯 Entrada executada — {pos['direcao']} {pos['ativo']}",
                [f"Entrada {pos['entry']}  ·  {pos['contratos']} contrato(s)",
                 f"Stop {pos['stop']}  ·  Alvo {pos.get('tp1')}",
                 f"Execução {como}."],
                cor="#3d7fc0")
            enviar_relatorio_whatsapp(
                f"🎯 *ENTRADA EXECUTADA — {pos['direcao']} {pos['ativo']}*\n"
                f"Entrada {pos['entry']} · {pos['contratos']} contrato(s)\n"
                f"Stop {pos['stop']} · Alvo {pos.get('tp1')}", None, self.log)
            self._chat_feed(f"🎯 Sua entrada {pos['direcao']} {pos['ativo']} @ "
                            f"{pos['entry']} EXECUTOU ({pos['contratos']} contrato(s)). "
                            "Estou acompanhando até o stop/alvo — me chame se quiser "
                            "discutir a gestão.")
        elif tipo == "CANCELADA":
            self.log(f"🚫 ORDEM CANCELADA: {pos['direcao']} {pos['ativo']} @ {pos['entry']} — "
                      "o preço rompeu o stop antes de tocar a entrada. Nunca foi executada.")
            self._notificar_desktop(
                f"🚫 Ordem cancelada — {pos['direcao']} {pos['ativo']}",
                [f"O preço rompeu o stop antes de tocar {pos['entry']}.",
                 "A ordem nunca foi executada."],
                cor="#a0a0a0")
        else:
            emoji = "🔴" if tipo == "STOP" else "🟢"
            msg = (f"{emoji} *Operação encerrada ({tipo})*\n"
                   f"🕐 {time.strftime('%d/%m/%Y %H:%M:%S')}\n"
                   f"{pos['direcao']} {pos['ativo']} | Entrada {pos['entry']}\n"
                   f"Resultado: US${pos['pnl_final']:+.2f} ({pos['contratos']} contrato(s))")
            self.log(msg.replace("*", ""))
            enviar_relatorio_whatsapp(msg, None, self.log)
            self._notificar_desktop(
                f"{emoji} Operação encerrada ({tipo}) — {pos['ativo']}",
                [f"{pos['direcao']} · entrada {pos['entry']} · "
                 f"{pos['contratos']} contrato(s)",
                 f"Resultado: US${pos['pnl_final']:+.2f}"],
                cor="#c53030" if tipo == "STOP" else "#1f8b4c")
            self._chat_feed(
                f"{emoji} Operação encerrada no {tipo}: {pos['direcao']} "
                f"{pos['ativo']}, resultado US${pos['pnl_final']:+.2f}. "
                + ("Quer revisar o que deu errado nesse cenário?" if tipo == "STOP"
                   else "Parabéns pela execução — quer que eu analise o próximo?"))
            # ELA PERGUNTOU — então ela tem de saber a que o "sim" responde.
            # Sem isto, o "sim" do trader chegava sem dono e caía no modelo, que
            # estava sem cota, e virava o despejo de "não tenho como responder".
            # Ela fazia uma pergunta e não sabia responder o próprio convite.
            self._topico_pendente = ("POSTMORTEM", pos.get("id")) \
                if tipo == "STOP" else ("VER_GRAFICO", None)

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
                            ("criadas", "encerradas", "corrigidas", "confirmadas",
                             "fundidas"))
                if houve or not silencioso:
                    self.log(
                        f"🔎 Posições da plataforma (conta '{nome_conta_ativa()}'): "
                        f"{resumo['criadas']} nova(s), {resumo['atualizadas']} atualizada(s), "
                        f"{resumo['encerradas']} encerrada(s), "
                        f"{resumo['confirmadas']} confirmada(s), "
                        f"{resumo['corrigidas']} corrigida(s)"
                        + (f", {resumo['fundidas']} fundida(s) com o registro do robô"
                           if resumo["fundidas"] else "")
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

    # ------------------------------------------------------------------
    # TAMANHO DA LETRA
    # ------------------------------------------------------------------
    def _aplicar_escala_letra(self, escala, avisar=True):
        """Muda o tamanho da letra em TODAS as abas, na hora, e grava a escolha.

        O `set_widget_scaling` do CustomTkinter cuida de tudo que é widget dele
        (botões, rótulos, campos, menus) em todas as abas de uma vez. O que ele
        NÃO alcança são os dois campos de texto puro do Tk — o terminal da TIGER
        e o log do motor —, que são justamente onde o trader mais lê. Esses dois
        são reconfigurados aqui, com o mesmo fator."""
        try:
            escala = min(max(float(escala), 1.0), 2.0)
        except (TypeError, ValueError):
            return
        self._escala_letra = escala
        salvar_config({"escala_letra": escala})
        try:
            ctk.set_widget_scaling(escala)
        except Exception as e:
            if getattr(self, "console", None) is not None:
                self.log(f"(não consegui aplicar a escala dos widgets: {e})")

        # Terminal da TIGER (tk.Text) — inclusive as tags, que têm fonte própria.
        tam = max(8, int(round(_FONTE_BASE_CHAT * escala)))
        chat = getattr(self, "txt_chat", None)
        if chat is not None:
            try:
                chat.configure(font=("Consolas", tam))
                chat.tag_configure("prompt", font=("Consolas", tam, "bold"))
                chat.tag_configure("ia_pref", font=("Consolas", tam, "bold"))
                chat.tag_configure("sistema",
                                   font=("Consolas", max(8, tam - 1), "italic"))
                chat.tag_configure("hora", font=("Consolas", max(7, tam - 3)))
            except Exception:
                pass
        entrada = getattr(self, "entrada_chat", None)
        if entrada is not None:
            try:
                entrada.configure(
                    font=ctk.CTkFont(family="Consolas",
                                     size=max(9, int(round(12 * escala)))))
            except Exception:
                pass
        console = getattr(self, "console", None)
        if console is not None:
            try:
                console.configure(
                    font=("Consolas",
                          max(8, int(round(_FONTE_BASE_CONSOLE * escala)))))
            except Exception:
                pass

        # A janela acompanha: letra maior na mesma largura corta botão.
        try:
            larg = int(680 * escala)
            self.minsize(larg, min(int(800 * escala), 900))
            if self.winfo_width() < larg:
                self.geometry(f"{larg}x{self.winfo_height()}")
        except Exception:
            pass

        # Os dois controles ficam em sincronia: o menu da aba Motor e o rótulo
        # entre os botões A－ / A＋ da barra da TIGER. Um mostrando "Normal"
        # enquanto o outro está em "Máximo" seria pior que não ter indicador.
        rotulo = nome_da_escala(escala)
        var = getattr(self, "_var_escala_motor", None)
        if var is not None:
            try:
                var.set(rotulo)
            except Exception:
                pass
        lbl = getattr(self, "lbl_escala_ia", None)
        if lbl is not None:
            try:
                lbl.configure(text=f"letra: {rotulo}")
            except Exception:
                pass
        if avisar and getattr(self, "console", None) is not None:
            self.log(f"🔠 Tamanho da letra: {rotulo} ({escala:.2f}×). "
                     "Vale para todas as abas e fica salvo.")

    def _escala_por_passo(self, passo):
        """Botões A− / A+ da barra da TIGER: anda um degrau na lista."""
        ordem = sorted(ESCALAS_LETRA.values())
        atual = getattr(self, "_escala_letra", 1.0)
        i = min(range(len(ordem)), key=lambda k: abs(ordem[k] - atual))
        self._aplicar_escala_letra(ordem[min(max(i + passo, 0), len(ordem) - 1)])

    def _secao(self, master, titulo, chave, aberta_padrao=True, cor_borda=None):
        """Cria um bloco RECOLHÍVEL e devolve o frame de conteúdo.

        Era isso que faltava para o painel deixar de ser engessado: cada bloco
        abre e fecha com um clique no título, e o app LEMBRA como você deixou.
        Assim você monta a tela do seu jeito — só gráficos num dia, só o diário
        no outro — sem rolar por coisa que não quer ver agora.
        """
        estado = carregar_config().get("secoes_abertas", {})
        aberta = bool(estado.get(chave, aberta_padrao))

        wrap = ctk.CTkFrame(master, fg_color=COR["card"], corner_radius=8,
                             border_width=1, border_color=cor_borda or COR["borda"])
        wrap.pack(padx=8, pady=5, fill="x")

        cabecalho = ctk.CTkFrame(wrap, fg_color="transparent", cursor="hand2")
        cabecalho.pack(fill="x")
        seta = ctk.CTkLabel(cabecalho, text="▾" if aberta else "▸", width=16,
                             text_color=COR["verde"],
                             font=ctk.CTkFont(size=13, weight="bold"))
        seta.pack(side="left", padx=(10, 2), pady=7)
        rotulo = ctk.CTkLabel(cabecalho, text=titulo, anchor="w",
                               font=ctk.CTkFont(size=11, weight="bold"),
                               text_color=COR["dim"])
        rotulo.pack(side="left", pady=7)
        dica = ctk.CTkLabel(cabecalho, text="clique para recolher", anchor="e",
                             font=ctk.CTkFont(size=9), text_color="#4a5163")
        dica.pack(side="right", padx=10)

        conteudo = ctk.CTkFrame(wrap, fg_color="transparent")
        if aberta:
            conteudo.pack(fill="both", expand=True)

        def alternar(_e=None):
            nonlocal aberta
            aberta = not aberta
            if aberta:
                conteudo.pack(fill="both", expand=True)
            else:
                conteudo.pack_forget()
            seta.configure(text="▾" if aberta else "▸")
            dica.configure(text="clique para recolher" if aberta else "clique para abrir")
            est = carregar_config().get("secoes_abertas", {})
            est[chave] = aberta
            salvar_config({"secoes_abertas": est})

        def abrir():
            """Força a seção a aparecer. Existe porque uma seção RECOLHIDA pode
            esconder algo que o app precisa mostrar na hora — o QR code do
            WhatsApp é o caso: se ele nasce dentro de um bloco fechado, o
            trader nunca vê o código para parear."""
            if not aberta:
                alternar()

        for w in (cabecalho, seta, rotulo, dica):
            w.bind("<Button-1>", alternar)
        conteudo.abrir_secao = abrir
        conteudo.alternar_secao = alternar
        return conteudo

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
        frame_config = self._secao(scroll, "⚙️  PLANO DE TRADING DESTA CONTA",
                                    "plano", aberta_padrao=True)
        # Rótulo mantido (o dashboard atualiza o nome da conta nele), mas agora
        # some junto com a seção quando você a recolhe.
        self.lbl_titulo_plano = ctk.CTkLabel(
            frame_config, text="PLANO DE TRADING DESTA CONTA",
            font=ctk.CTkFont(size=10), text_color="#4a5163")
        self.lbl_titulo_plano.grid(row=0, column=0, columnspan=4, pady=(2, 8))

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
            # TRAVAS DE TAMANHO — o que impede um stop curto de virar posição
            # gigante. Ver `calcular_contratos`.
            ("Máx. contratos (0=auto):", "entry_max_ctr", "max_contratos", 7, 0, 0),
            ("Mín. ticks de stop:", "entry_min_ticks", "min_ticks_stop", 7, 2,
             MIN_TICKS_STOP_PADRAO),
            # FREIO DE SUGESTÕES — a trava que impede o dia de virar sequência
            # de stops. Fica no plano de cada conta.
            ("Stops seguidos p/ pausar:", "entry_max_stops", "max_stops_seguidos", 9, 0, 2),
            ("Pausa após stops (min):", "entry_cooldown", "cooldown_stop_min", 9, 2, 30),
            ("Máx. operações no dia:", "entry_max_ops", "max_operacoes_dia", 10, 0, 6),
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

        ctk.CTkLabel(frame_config,
                     text="📐 TAMANHO DA POSIÇÃO: o nº de contratos sai de "
                          "(Margem × Risco%) ÷ (distância até o stop × valor do ponto). "
                          "Stop curto = posição grande, e é assim que um stop de 2 pontos "
                          "vira 30 contratos. 'Mín. ticks de stop' recusa o cenário quando "
                          "o stop é ruído (0 desliga); 'Máx. contratos' é o teto duro por "
                          "operação (0 = sem teto fixo).",
                     text_color=COR["dim"], font=ctk.CTkFont(size=9), justify="left",
                     wraplength=560
                     ).grid(row=8, column=0, columnspan=4, sticky="w", padx=12, pady=(6, 2))

        ctk.CTkLabel(frame_config,
                     text="🛑 FREIO: depois dessa quantidade de stops seguidos o robô fica em "
                          "silêncio pelo tempo da pausa, e para de vez ao bater o teto de "
                          "operações ou o Drawdown Máx. do dia. Use 0 para desligar cada um.",
                     text_color=COR["dim"], font=ctk.CTkFont(size=9), justify="left"
                     ).grid(row=11, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 2))

        # QUANDO VOCÊ JÁ ESTÁ POSICIONADO — inclusive numa entrada que você fez
        # na mão, fora da sugestão dele.
        ctk.CTkLabel(frame_config, text="Já posicionado no ativo:", text_color=COR["dim"],
                     font=ctk.CTkFont(size=11)).grid(row=12, column=0, sticky="e",
                                                      padx=(12, 4), pady=4)
        self.opt_com_posicao = ctk.CTkOptionMenu(
            frame_config, width=250,
            values=["Avisar quando virar contra (recomendado)",
                    "Sugerir normalmente",
                    "Não sugerir nada"],
            fg_color=COR["input"], button_color=COR["borda"], text_color=COR["texto"])
        self.opt_com_posicao.grid(row=12, column=1, columnspan=3, sticky="w",
                                  padx=(0, 12), pady=4)
        self.opt_com_posicao.set(self._rotulo_com_posicao(
            self.plano.get("com_posicao_aberta", "alerta")))

        ctk.CTkLabel(frame_config,
                     text="Com posição aberta (mesmo aberta na mão), o cenário CONTRA ela não "
                          "vira sugestão de entrada — entrar do outro lado é hedge, não trade. "
                          "No modo recomendado ele te AVISA que a leitura virou, e segue "
                          "sugerindo a favor e nos outros ativos.",
                     text_color=COR["dim"], font=ctk.CTkFont(size=9), justify="left"
                     ).grid(row=13, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 2))

        frame_botoes_plano = ctk.CTkFrame(frame_config, fg_color="transparent")
        frame_botoes_plano.grid(row=14, column=0, columnspan=4, pady=(6, 10))
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
        sec_graf = self._secao(scroll, "📈  GRÁFICOS — EQUITY E RESULTADO POR DIA",
                                "graficos", aberta_padrao=True)

        # Altura ajustável: gráfico baixinho para caber tudo na tela, ou alto
        # para analisar a curva com calma. Fica salvo entre sessões.
        self._altura_graf = int(carregar_config().get("altura_graficos", 175))
        barra_alt = ctk.CTkFrame(sec_graf, fg_color="transparent")
        barra_alt.pack(fill="x", padx=10, pady=(2, 0))
        ctk.CTkLabel(barra_alt, text="altura:", text_color=COR["dim"],
                     font=ctk.CTkFont(size=9)).pack(side="left")
        for rotulo, delta in (("⌃ maior", 40), ("⌄ menor", -40)):
            ctk.CTkButton(barra_alt, text=rotulo, width=70, height=20,
                          fg_color="#2a3f5f", hover_color="#3a5580",
                          font=ctk.CTkFont(size=9),
                          command=lambda d=delta: self._ajustar_altura_graficos(d)
                          ).pack(side="left", padx=3)
        ctk.CTkLabel(barra_alt,
                     text="roda do mouse = zoom · arraste = mover · passe o mouse p/ ver o valor",
                     text_color="#4a5163", font=ctk.CTkFont(size=9)).pack(side="left", padx=10)

        frame_graficos = ctk.CTkFrame(sec_graf, fg_color="transparent")
        frame_graficos.pack(padx=4, pady=4, fill="x")
        frame_graficos.grid_columnconfigure(0, weight=1)
        frame_graficos.grid_columnconfigure(1, weight=1)

        for coluna, (titulo, attr) in enumerate([
            ("📈 EQUITY — RESULTADO ACUMULADO (US$)", "canvas_equity"),
            ("📅 RESULTADO POR DIA OPERADO (US$)", "canvas_operacoes"),
        ]):
            col = ctk.CTkFrame(frame_graficos, fg_color=COR["fundo"], corner_radius=8,
                                border_width=1, border_color=COR["borda"])
            col.grid(row=0, column=coluna, sticky="nsew", padx=(0, 4) if coluna == 0 else (4, 0))
            ctk.CTkLabel(col, text=titulo, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=COR["dim"]).pack(anchor="w", padx=10, pady=(8, 2))
            canvas = tk.Canvas(col, bg=COR["fundo"], height=self._altura_graf,
                                highlightthickness=0)
            canvas.pack(fill="x", padx=6, pady=(0, 2))
            setattr(self, attr, canvas)
            self._ativar_zoom_pan(canvas)

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

        self.lbl_legenda_dias = ctk.CTkLabel(sec_graf, text="", justify="left", anchor="w",
                                              text_color=COR["dim"], font=ctk.CTkFont(size=9))
        self.lbl_legenda_dias.pack(padx=12, pady=(0, 6), fill="x")

        # ================= COMPARATIVO: ACATADAS vs TODAS AS SUGESTÕES =================
        frame_comp = self._secao(
            scroll, "⚖️  COMPARATIVO DO CICLO — O QUE VOCÊ FEZ vs. TODAS AS SUGESTÕES",
            "comparativo", aberta_padrao=True, cor_borda="#3a3a5a")
        self.lbl_comparativo = ctk.CTkLabel(frame_comp, text="Sem dados ainda.", justify="left",
                                             anchor="w", font=("Consolas", 11))
        self.lbl_comparativo.pack(padx=14, pady=(2, 10), fill="x")

        # ================= EVOLUÇÃO PATRIMONIAL =================
        frame_patrimonio = self._secao(scroll, "💰  EVOLUÇÃO PATRIMONIAL",
                                        "patrimonio", aberta_padrao=True,
                                        cor_borda=COR["verde_esc"])
        self.lbl_patrimonio = ctk.CTkLabel(frame_patrimonio, text="Sem dados ainda.",
                                            justify="left", anchor="w", font=("Consolas", 11))
        self.lbl_patrimonio.pack(padx=14, pady=(2, 4), fill="x")

        # A TRILHA DOS DIAS, AGORA CLICÁVEL — pedido dele em 17/08.
        # Ela era TEXTO dentro do rótulo acima, montada por uma subtração de
        # calendário, e não havia como discordar dela. Palavras dele: "e se eu
        # quiser ficar um dia sem operar? e se for feriado ou final de semana?
        # ajuste isso para que eu consiga clicar ali no quadradinho dos dias e
        # escolher". Agora cada quadradinho é um botão: clicou, aquele passa a
        # ser o dia de hoje, e o contador segue sozinho a partir dali.
        self.frame_trilha = ctk.CTkFrame(frame_patrimonio, fg_color="transparent")
        self.frame_trilha.pack(padx=14, pady=(0, 2), fill="x")
        # wraplength É OBRIGATÓRIO. Sem ele a explicação sai numa linha só e o
        # fim dela fica FORA da janela — a frase que diz como usar o recurso
        # seria a única parte que ele não conseguiria ler.
        self.lbl_trilha_ajuda = ctk.CTkLabel(
            frame_patrimonio, justify="left", anchor="w", text_color="#a0aec0",
            font=("Arial", 10), wraplength=560,
            text="Clique no dia para dizer em que dia do ciclo você está "
                 "(feriado, folga, fim de semana).")
        self.lbl_trilha_ajuda.pack(padx=14, pady=(0, 10), fill="x")
        self._botoes_trilha = []

        # ================= POSIÇÕES =================
        self.frame_posicoes = self._secao(
            scroll, "🔥  ORDENS PENDENTES E OPERAÇÕES EM ANDAMENTO",
            "posicoes", aberta_padrao=True, cor_borda="#5a4a1a")

        # ================= INCLUSÃO MANUAL NO DIÁRIO =================
        # Recolhida por padrão: só é usada de vez em quando, e ocupava muito
        # espaço fixo no meio do painel.
        frame_manual = self._secao(
            scroll, "✍️  INCLUIR OPERAÇÃO NO DIÁRIO (FORA DA SUGESTÃO)",
            "manual", aberta_padrao=False)

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
        sec_sinais = self._secao(scroll, "📋  SUGESTÕES E ACOMPANHAMENTO",
                                  "sinais", aberta_padrao=True)

        # FILTRO: em vez de uma lista única e longa, você escolhe o que quer ver.
        self.filtro_sinais = tk.StringVar(
            value=carregar_config().get("filtro_sinais", "Todas"))
        barra_filtro = ctk.CTkFrame(sec_sinais, fg_color="transparent")
        barra_filtro.pack(fill="x", padx=10, pady=(2, 4))
        ctk.CTkLabel(barra_filtro, text="mostrar:", text_color=COR["dim"],
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for opcao in ("Todas", "Aguardando", "Em operação", "Encerradas"):
            ctk.CTkRadioButton(
                barra_filtro, text=opcao, value=opcao, variable=self.filtro_sinais,
                radiobutton_width=14, radiobutton_height=14, border_width_unchecked=2,
                font=ctk.CTkFont(size=10), text_color=COR["texto"],
                fg_color=COR["verde_esc"], hover_color=COR["verde"],
                command=self._trocar_filtro_sinais).pack(side="left", padx=6)
        self.lbl_qtd_sinais = ctk.CTkLabel(barra_filtro, text="", text_color="#4a5163",
                                            font=ctk.CTkFont(size=9))
        self.lbl_qtd_sinais.pack(side="right", padx=6)

        self.frame_sinais = ctk.CTkFrame(sec_sinais, fg_color="transparent")
        self.frame_sinais.pack(padx=4, pady=(0, 8), fill="both", expand=True)

        self._atualizar_dashboard()

    def _ajustar_altura_graficos(self, delta):
        """Deixa os gráficos mais altos ou mais baixos, do jeito que você prefere.
        A escolha fica salva para as próximas vezes."""
        nova = max(110, min(460, int(getattr(self, "_altura_graf", 175)) + delta))
        self._altura_graf = nova
        salvar_config({"altura_graficos": nova})
        for attr in ("canvas_equity", "canvas_operacoes"):
            c = getattr(self, attr, None)
            if c is not None:
                c.configure(height=nova)
        self._atualizar_dashboard(forcar=True)

    def _trocar_filtro_sinais(self):
        salvar_config({"filtro_sinais": self.filtro_sinais.get()})
        self._assin_sinais = None      # força reconstruir a lista com o filtro novo
        self._atualizar_dashboard(forcar=True)

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
            # EM QUE PREGÃO ISSO CAIU — e por quê, quando não for o dia de hoje
            # no calendário.
            #
            # 17/08, 19:59: "hoje encerrou às 17:59, abriu às 19h, mas antes de
            # fechar eu fiz 54 dólares e incluí no diário, e não está
            # contabilizando". Ele lançou perto das 18h. Com o pregão
            # 19:00→17:59, TODA hora antes das 19:00 pertence ao pregão da
            # véspera — então o lançamento foi para o dia anterior, corretamente
            # pela regra da sessão, e sumiu do "hoje" que ele estava olhando.
            #
            # A regra não está errada. Errado era não dizer. Agora diz.
            pregao = data_do_pregao()
            hoje_calendario = time.strftime('%d/%m/%Y')
            aviso_dia = ""
            if pregao != hoje_calendario:
                cfg = carregar_config()
                aviso_dia = (
                    f"  ⚠️ Entrou no pregão de {pregao}, NÃO no de "
                    f"{hoje_calendario}: o seu pregão vai das "
                    f"{cfg.get('hora_inicio', '?')} às {cfg.get('hora_fim', '?')}, "
                    f"então tudo que acontece antes das "
                    f"{cfg.get('hora_inicio', '?')} ainda pertence ao pregão "
                    f"anterior. Se o resultado é de outro dia, use a trilha de "
                    f"dias (Evolução Patrimonial) e lance no dia certo.")
            self.log(f"📕 Operação CONCLUÍDA incluída no diário: {direcao} {ativo} "
                      f"{entry} → {preco_saida}  |  Resultado: US$ "
                      f"{fechada['pnl_final']:+,.2f}  |  pregão de {pregao}."
                      f"{aviso_dia}")
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
        sinal_id = None
        for pos in lista:
            if pos["id"] == pos_id and pos["status"] == "PENDENTE":
                pos["status"] = "CANCELADA"
                pos["data_fechamento"] = time.strftime('%d/%m/%Y %H:%M')
                pos["pnl_final"] = 0.0
                pos["motivo_cancelamento"] = "cancelada por você"
                sinal_id = pos.get("sinal_id")
                self.log(f"🚫 Ordem pendente cancelada: {pos['direcao']} {pos['ativo']} @ {pos['entry']}")
                break
        salvar_posicoes(lista)

        # RELATÓRIO FIEL: cancelar a ordem TEM de encerrar o acompanhamento do
        # cenário também. Antes, o robô continuava rastreando por dentro e
        # chegava a anunciar "ENTRADA ACIONADA" de uma ordem que você já havia
        # cancelado — relatório contando uma história que não aconteceu.
        if sinal_id:
            atualizar_decisao_sinal(sinal_id, "CANCELADO")
            self.sinais_acatados.discard(sinal_id)
            self.sinais_dispensados.add(sinal_id)
            self._sinais_notificados.discard(sinal_id)
            self.log("🔗 Acompanhamento do cenário encerrado junto com a ordem — "
                      "não haverá mais avisos de entrada/stop/alvo dele.")
        self._atualizar_dashboard(forcar=True)

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
                if PYWIN32_DISPONIVEL and plataforma.janela_existe(cache):
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
        # A LISTA DE COMANDOS ESTAVA SÓ NO LEIA-ME. Ele pediu STATUS pelo
        # WhatsApp em 14/08 e tentou ENSINAR como lição, porque não tinha como
        # saber que existia um jeito de mandar comando por ali — a tela só
        # falava de START. Comando que ninguém descobre é comando que não existe.
        ctk.CTkLabel(
            frame, justify="left", text_color="#a0aec0",
            text="Comandos que você pode mandar em qualquer chat seu:\n"
                 "STATUS (conta, meta, ritmo, posições abertas) · NOVA ANÁLISE "
                 "(lê o gráfico agora)\n"
                 "ACATAR / NÃO OPEREI (decide o último cenário) · START · STOP"
        ).pack(pady=(0, 8), padx=12, anchor="w")
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
            try:
                self.after(0, lambda: self._render_inscritos(subs))
            except RuntimeError:
                # A janela foi fechada enquanto esta consulta estava no ar:
                # `after` de uma thread depois do fim do loop do Tk levanta
                # "main thread is not in main loop". Não é erro do trader nem
                # do motor — é o app terminando. Encontrado pelo teste de
                # fumaça da interface, no encerramento.
                pass
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
        # No Mac M2 o instalador certo é o ARM64 (Apple Silicon). O link direto
        # da página de download já oferece o pacote correto para o sistema.
        webbrowser.open_new("https://nodejs.org/en/download/")
        self.log(plataforma.como_instalar_node())

    def verificar_node(self):
        """Procura o Node de verdade, não só no PATH herdado.

        No Mac, aberto pelo Finder, o PATH não traz /opt/homebrew/bin — e o
        programa dizia "Node.js não encontrado" com o Node instalado e
        funcionando no terminal. Aqui resolvemos o caminho completo antes de
        desistir, e o erro diz COMO instalar NESTE sistema."""
        node = plataforma.caminho_node()
        if not node:
            self.lbl_status.configure(text="STATUS: Node.js não encontrado.", text_color="red")
            self.btn_ligar.configure(state="disabled", fg_color="gray")
            self.log("❌ Node.js não encontrado.\n" + plataforma.como_instalar_node())
            return
        try:
            r = subprocess.run([node, "-v"], check=True, capture_output=True,
                               **plataforma.opcoes_subprocess())
            versao = (r.stdout or b"").decode("utf-8", "ignore").strip()
            self.lbl_status.configure(text="STATUS: Ambiente pronto!", text_color="lime")
            self.btn_ligar.configure(state="normal", text="▶️ LIGAR MOTOR", fg_color="green")
            self.log(f"Node.js detectado ({versao or 'versão não lida'}) em {node}")
        except Exception as e:
            self.lbl_status.configure(text="STATUS: Node.js não encontrado.", text_color="red")
            self.btn_ligar.configure(state="disabled", fg_color="gray")
            self.log(f"❌ Node.js está em {node} mas não executou: {e}\n"
                     + plataforma.como_instalar_node())

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
            (self.entry_max_ctr, "max_contratos", 0),
            (self.entry_min_ticks, "min_ticks_stop", MIN_TICKS_STOP_PADRAO),
            (self.entry_max_stops, "max_stops_seguidos", 2),
            (self.entry_cooldown, "cooldown_stop_min", 30),
            (self.entry_max_ops, "max_operacoes_dia", 6),
        ]
        for widget, chave, padrao in campos:
            widget.delete(0, tk.END)
            widget.insert(0, str(self.plano.get(chave, padrao)))
        self.opt_com_posicao.set(self._rotulo_com_posicao(
            self.plano.get("com_posicao_aberta", "alerta")))
        # Invalida os caches de render: a conta mudou, as listas TÊM de ser
        # redesenhadas mesmo que a assinatura anterior fosse igual.
        self._assin_posicoes = None
        self._assin_sinais = None
        self._assin_dashboard = None
        self._recarregar_menu_contas()
        # A TIGER acompanha a troca: o cabeçalho do chat mostra a conta e a
        # conversa passa a usar o plano/números dela imediatamente.
        try:
            self.lbl_ia_conta.configure(text=f"🏦 {nome_conta_ativa()}")
            self._chat_escrever(
                "sistema",
                f"(conversa agora vinculada à conta '{nome_conta_ativa()}' — "
                "plano de trading e números são desta conta)", persistir=False)
        except Exception:
            pass
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
    # De/para entre o texto do menu e o valor gravado no plano.
    _COM_POSICAO_ROTULOS = {
        "alerta": "Avisar quando virar contra (recomendado)",
        "livre": "Sugerir normalmente",
        "bloquear": "Não sugerir nada",
    }

    def _rotulo_com_posicao(self, valor):
        return self._COM_POSICAO_ROTULOS.get(
            str(valor).strip().lower(), self._COM_POSICAO_ROTULOS["alerta"])

    def _valor_com_posicao(self, rotulo):
        for chave, texto in self._COM_POSICAO_ROTULOS.items():
            if texto == rotulo:
                return chave
        return "alerta"

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
            # TRAVAS DE TAMANHO. Zero é opção legítima nas duas: 0 contratos =
            # sem teto fixo; 0 ticks = sem piso de stop. Negativo, não.
            _mc = int(float(self.entry_max_ctr.get().replace(",", ".")))
            self.plano["max_contratos"] = max(0, _mc)
            _mt = int(float(self.entry_min_ticks.get().replace(",", ".")))
            self.plano["min_ticks_stop"] = max(0, _mt)
            # FREIO DE SUGESTÕES. Zero é opção legítima em todos: significa
            # "não quero essa trava". Por isso o piso aqui é 0, e não 1.
            _ms = int(float(self.entry_max_stops.get().replace(",", ".")))
            self.plano["max_stops_seguidos"] = max(0, _ms)
            _cd = int(float(self.entry_cooldown.get().replace(",", ".")))
            self.plano["cooldown_stop_min"] = max(0, _cd)
            _mo = int(float(self.entry_max_ops.get().replace(",", ".")))
            self.plano["max_operacoes_dia"] = max(0, _mo)
            self.plano["com_posicao_aberta"] = self._valor_com_posicao(
                self.opt_com_posicao.get())
        except ValueError:
            self.log("⚠️ Valores do plano de trading inválidos — use apenas números.")
            return

        if not self.plano.get("data_inicio"):
            self.plano["data_inicio"] = datetime.date.today().isoformat()

        salvar_plano_da_conta(self.plano)
        self.log(f"💾 Plano de trading salvo para a conta '{nome_conta_ativa()}'.")
        for aviso in avisos_do_plano(self.plano):
            self.log(aviso)
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
        self.plano["dia_ciclo_ancora"] = None      # ciclo novo, contagem nova
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
        # QUE DIA DO CICLO É HOJE. Era `(hoje - inicio).days`, subtração de
        # calendário — e foi ela que deixou o fim de semana de 15 e 16/08
        # consumir dois dos oito dias do prazo dele, marcados como dias
        # PERDIDOS na trilha, empurrando o ritmo exigido de US$ 400 para
        # US$ 553,42 por dia. Agora conta dia de PREGÃO, e ele pode dizer qual
        # é o dia clicando na trilha (feriado, folga, viagem).
        #
        # `dias_passados` continua sendo "dias já consumidos" — o dia de hoje
        # ainda está em curso, então é o número do dia menos um.
        dia_atual = dia_do_ciclo(self.plano)
        dias_passados = dia_atual - 1
        dias_restantes = max(dias_meta - dias_passados, 0)

        falta = meta - lucro_usd
        meta_diaria = (falta / dias_restantes) if dias_restantes > 0 else None
        hoje = data_do_pregao()
        resultado_hoje = dict(resultados_por_dia()).get(hoje, 0.0)

        return {
            "curva": curva, "winrate": winrate, "max_dd_usd": max_dd_usd,
            "lucro_usd": lucro_usd, "realizado": realizado, "flutuante": flutuante,
            "risco_usd": risco_usd, "dias_passados": dias_passados,
            "dias_restantes": dias_restantes, "falta": falta, "abertas": len(abertas),
            "meta_diaria": meta_diaria, "total_ops": total, "meta": meta,
            "resultado_hoje": resultado_hoje, "dias_meta": dias_meta,
            # O NÚMERO DO DIA DE HOJE, para a trilha marcar onde ele está e
            # para os botões saberem qual quadradinho está aceso.
            "dia_atual": dia_atual,
            "dia_manual": bool((self.plano or {}).get("dia_ciclo_ancora")),
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

        dias_meta = stats.get("dias_meta", 5)
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
            f"{'─' * 46}"
        )
        self.lbl_patrimonio.configure(text=texto, text_color=cor)
        self._renderizar_trilha(stats)

    def _renderizar_trilha(self, stats):
        """A trilha dos dias, em BOTÕES — clicar diz em que dia do ciclo ele está.

        Antes isto era texto dentro do rótulo, montado por uma subtração de
        calendário, e não havia como discordar. No print de 17/08 (segunda) a
        trilha mostrava D2 ❌ e D3 ❌ para o SÁBADO e o DOMINGO do fim de
        semana anterior: dois dias sem mercado, contados como dias perdidos,
        empurrando o ritmo exigido de US$ 400 para US$ 553,42 por dia.

        As marcas, e nenhuma delas mente:
          ✅ dia concluído (marcado por ele, ou fechado no azul)
          ❌ dia que já passou e fechou abaixo do exigido
          🚪 dia em que ele NÃO OPEROU (disse isso clicando)
          📍 o dia de hoje         ⬜ dia que ainda não chegou
        O dia de HOJE fica com a borda acesa, para ele ver onde está.

        A MARCA AUTOMÁTICA PASSOU A OLHAR O DIA, NÃO O ACUMULADO.
        17/08: "o dia dois fica como se não tivesse operado". Estava certo — a
        conta antiga comparava o lucro ACUMULADO do ciclo com a meta acumulada
        até aquele dia, então um dia lucrativo aparecia com ❌ só porque o
        ciclo inteiro ainda estava atrás. Agora cada quadradinho pergunta o que
        aconteceu NAQUELE dia, no diário. E o que ele marcar à mão ganha.
        """
        frame = getattr(self, "frame_trilha", None)
        if frame is None:
            return
        for w in frame.winfo_children():
            w.destroy()
        self._botoes_trilha = []

        dias_meta = stats.get("dias_meta", 5)
        meta = stats.get("meta") or 0
        dia_atual = stats.get("dia_atual", 1)
        marcados = (self.plano or {}).get("dias_marcados") or {}
        # Resultado REAL de cada dia, vindo do diário — é o que responde
        # "operei neste dia?", que o acumulado nunca soube responder.
        try:
            por_dia = dict(resultados_por_dia())
        except Exception:
            por_dia = {}
        meta_por_dia = (meta / dias_meta) if (meta and dias_meta) else 0

        linha = None
        for dia in range(1, dias_meta + 1):
            # Prazo longo não cabe numa linha só; quebra a cada 10 quadradinhos.
            if (dia - 1) % 10 == 0:
                linha = ctk.CTkFrame(frame, fg_color="transparent")
                linha.pack(anchor="w", pady=1)
            marca, resultado = self._marca_do_dia(
                dia, dia_atual, marcados, por_dia, meta_por_dia)
            e_hoje = (dia == dia_atual)
            e_manual = str(dia) in marcados
            # O VALOR DO DIA VAI NO PRÓPRIO QUADRADINHO. A pergunta dele era
            # "operei neste dia?" — e a resposta honesta é o número que está no
            # diário daquele dia. Escondê-lo atrás de um tooltip seria manter a
            # resposta a um passo de distância da pergunta.
            rotulo = f"D{dia}\n{marca}"
            if resultado is not None:
                rotulo += f"\n{resultado:+,.0f}"
            btn = ctk.CTkButton(
                linha, text=rotulo, width=54, height=54,
                font=("Arial", 10),
                fg_color="#2b4a6f" if e_hoje else "#2a2a3a",
                hover_color="#3a5a8f",
                border_width=2 if (e_hoje or e_manual) else 0,
                border_color=(COR["verde"] if e_hoje else "#7a6a2a"),
                text_color=COR["texto"],
                command=lambda d=dia: self._menu_do_dia(d))
            btn.pack(side="left", padx=2)
            self._botoes_trilha.append(btn)

        # O RÓTULO DE AJUDA DIZ DE ONDE VEIO O NÚMERO. Sem isso ele não teria
        # como saber se está vendo a conta automática ou a escolha dele — e foi
        # justamente não saber que gerou o pedido.
        restam = stats.get("dias_restantes", 0)
        if stats.get("dia_manual"):
            ajuda = (f"Hoje é o dia {dia_atual} de {dias_meta} — VOCÊ escolheu "
                     f"(restam {restam}).")
        else:
            ajuda = (f"Hoje é o dia {dia_atual} de {dias_meta} — contado "
                     f"automaticamente, pulando sábado"
                     f"{'' if _domingo_e_pregao() else ' e domingo'} "
                     f"(restam {restam}).")
        ajuda += ("  Clique em qualquer dia para: dizer que HOJE é ele, lançar "
                  "o resultado daquele dia em dólares, ou marcá-lo como "
                  "concluído / não operei.")
        if getattr(self, "lbl_trilha_ajuda", None) is not None:
            self.lbl_trilha_ajuda.configure(text=ajuda)

    def _marca_do_dia(self, dia, dia_atual, marcados, por_dia, meta_por_dia):
        """Que marca este dia leva, e qual o resultado dele. (marca, resultado).

        ORDEM DE QUEM MANDA: primeiro o que ELE marcou; depois o diário; e só
        no fim a posição do dia na linha do tempo. Uma marca dele nunca pode
        ser sobrescrita por dedução — foi para isso que ele clicou."""
        estado = marcados.get(str(dia))
        data = None
        try:
            data = data_do_dia_do_ciclo(self.plano, dia)
        except Exception:
            data = None
        resultado = por_dia.get(data.strftime("%d/%m/%Y")) if data else None

        if estado == "nao_operei":
            return "🚪", resultado
        if estado == "concluido":
            return "✅", resultado
        if dia == dia_atual:
            return "📍", resultado
        if dia > dia_atual:
            return "⬜", resultado
        # Dia que já passou, sem marca dele: manda o DIÁRIO daquele dia.
        if resultado is None:
            # Nenhuma operação registrada naquele dia. Isso não é derrota —
            # é ausência. ❌ aqui foi exatamente a queixa dele.
            return "⬜", None
        if meta_por_dia and resultado >= meta_por_dia:
            return "✅", resultado
        return ("✅" if resultado > 0 else "❌"), resultado

    def _menu_do_dia(self, dia):
        """Clicar num quadradinho abre o que dá para fazer COM AQUELE DIA.

        Antes o clique só fazia uma coisa: "hoje é este dia". Em 17/08 ele
        pediu mais duas, e as duas são do mesmo assunto — o dia:
          • "às vezes faço operações fora das sugestões, então acho que uma
             forma de incluir o resultado do dia no diário seria viável"
          • "além disso, selecionar como aquele dia concluído, ou não"
        Por isso vira menu, e não mais botões espalhados: tudo o que se faz com
        um dia sai de onde aquele dia está desenhado."""
        import tkinter as _tk
        try:
            stats = self._computar_stats_plano()
        except Exception:
            stats = {}
        marcados = (self.plano or {}).get("dias_marcados") or {}
        estado = marcados.get(str(dia))
        e_hoje_manual = (stats.get("dia_atual") == dia and stats.get("dia_manual"))
        data = None
        try:
            data = data_do_dia_do_ciclo(self.plano, dia)
        except Exception:
            pass
        # A DATA APARECE NO TÍTULO DO MENU de propósito: é a única forma de ele
        # conferir que o "dia 2" da trilha é o dia que ele tem na cabeça, antes
        # de lançar dinheiro nele.
        titulo = f"Dia {dia}" + (f" — {data.strftime('%d/%m/%Y')}" if data else "")

        menu = _tk.Menu(self, tearoff=0)
        menu.add_command(label=titulo, state="disabled")
        menu.add_separator()
        if e_hoje_manual:
            menu.add_command(label="📍 Voltar à contagem automática",
                             command=lambda: self._escolher_dia_do_ciclo(dia))
        else:
            menu.add_command(label=f"📍 Hoje é o dia {dia}",
                             command=lambda: self._escolher_dia_do_ciclo(dia))
        menu.add_separator()
        menu.add_command(label=f"💵 Lançar o resultado do dia {dia}…",
                         command=lambda: self._lancar_resultado_do_dia(dia))
        menu.add_separator()
        if estado == "concluido":
            menu.add_command(label="✅ Concluído — clique para desmarcar",
                             command=lambda: self._marcar_dia(dia, None))
        else:
            menu.add_command(label="✅ Marcar como concluído",
                             command=lambda: self._marcar_dia(dia, "concluido"))
        if estado == "nao_operei":
            menu.add_command(label="🚪 Não operei — clique para desmarcar",
                             command=lambda: self._marcar_dia(dia, None))
        else:
            menu.add_command(label="🚪 Marcar: não operei neste dia",
                             command=lambda: self._marcar_dia(dia, "nao_operei"))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _marcar_dia(self, dia, estado):
        """Grava (ou apaga) o que ELE disse sobre um dia do ciclo."""
        marcados = dict((self.plano or {}).get("dias_marcados") or {})
        if estado is None:
            marcados.pop(str(dia), None)
            self.log(f"📅 Dia {dia}: marca removida — volta a ser deduzido do "
                     "diário daquele dia.")
        else:
            marcados[str(dia)] = estado
            nome = "CONCLUÍDO" if estado == "concluido" else "NÃO OPEREI"
            self.log(f"📅 Dia {dia} marcado por você como {nome}.")
        self.plano["dias_marcados"] = marcados
        self._gravar_plano_silencioso()
        self._atualizar_dashboard(forcar=True)

    def _lancar_resultado_do_dia(self, dia):
        """O resultado de um dia, em dólares, direto no diário.

        O formulário de 'incluir operação' exige entrada, stop e preço de
        saída. Quem operou na mão cinco vezes e só sabe que fechou o dia em
        +54 não tem esses números — e, obrigado a preenchê-los, inventa preços
        para acertar o total. Aqui o dado é o valor, e nada é fingido."""
        from tkinter import simpledialog, messagebox
        data = None
        try:
            data = data_do_dia_do_ciclo(self.plano, dia)
        except Exception:
            pass
        if data is None:
            messagebox.showwarning(
                "Sem data para esse dia",
                "Ainda não sei em que data cai o dia " f"{dia} deste ciclo. "
                "Salve o Plano de Trading uma vez (isso grava o início do "
                "ciclo) e tente de novo.")
            return
        dia_txt = data.strftime("%d/%m/%Y")
        texto = simpledialog.askstring(
            f"Resultado do dia {dia}",
            f"Resultado FECHADO do dia {dia} ({dia_txt}), em dólares.\n"
            "Use ponto ou vírgula, e sinal negativo para prejuízo.\n"
            "Exemplos:  54    -120,50    +300\n\n"
            "Isto entra no diário como resultado realizado daquele pregão.",
            parent=self)
        if texto is None:
            return
        texto = str(texto).strip().replace(" ", "").replace("$", "")
        texto = texto.replace("US", "").replace("us", "")
        # Aceita 1.234,56 (brasileiro) e 1234.56 (inglês) sem adivinhar errado.
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            valor = float(texto)
        except ValueError:
            messagebox.showwarning(
                "Não entendi o valor",
                f"'{texto}' não é um número. Escreva só o resultado em "
                "dólares, por exemplo 54 ou -120,50.")
            return
        if valor == 0:
            messagebox.showinfo(
                "Zero não muda nada",
                "Um resultado de zero não altera o diário. Se você quis dizer "
                "que não operou nesse dia, use 'Marcar: não operei neste dia'.")
            return
        pos = lancar_resultado_do_dia(dia_txt, valor)
        if not pos:
            self.log(f"⚠️ Não consegui lançar o resultado do dia {dia}.")
            return
        # DIZ EM QUE PREGÃO ENTROU. Foi o silêncio sobre isto que fez os 54
        # dólares dele sumirem: o lançamento caiu no pregão da véspera e a
        # ferramenta não falou nada.
        self.log(f"📕 Resultado do dia {dia} lançado no diário: "
                 f"US$ {valor:+,.2f} no pregão de {dia_txt} "
                 f"(carimbo {pos.get('data_fechamento')}).")
        # Lançar resultado é dizer que o dia aconteceu.
        marcados = dict((self.plano or {}).get("dias_marcados") or {})
        if marcados.get(str(dia)) == "nao_operei":
            marcados.pop(str(dia), None)
            self.plano["dias_marcados"] = marcados
            self._gravar_plano_silencioso()
        self._atualizar_dashboard(forcar=True)

    def _gravar_plano_silencioso(self):
        """Grava o plano em disco sem passar pelo formulário.

        `salvar_plano_trading` relê TODOS os campos da tela e desiste em bloco
        se qualquer um tiver texto inválido — a escolha do dia sumiria por
        causa de uma vírgula errada na caixa da margem, e sem aviso."""
        try:
            salvar_plano_da_conta(self.plano)
            return True
        except Exception as e:
            self.log(f"⚠️ Não consegui gravar no plano ({type(e).__name__}) — "
                     "vale nesta sessão, mas volta ao anterior se você fechar "
                     "o programa.")
            return False

    def _escolher_dia_do_ciclo(self, dia):
        """Ele clicou num quadradinho da trilha: aquele passa a ser HOJE.

        Grava uma ÂNCORA ({dia, data}), não um número solto — assim o contador
        continua andando sozinho a partir da escolha, em vez de congelar. E
        clicar no dia que já está aceso DESFAZ a escolha e devolve a contagem
        automática: sem isso, um clique errado seria permanente."""
        try:
            atual = self._computar_stats_plano()
            ja_era = (atual.get("dia_atual") == dia and atual.get("dia_manual"))
        except Exception:
            ja_era = False
        if ja_era:
            self.plano["dia_ciclo_ancora"] = None
            self.log("📅 Dia do ciclo: de volta à contagem automática "
                     "(pulando fim de semana).")
        else:
            self.plano["dia_ciclo_ancora"] = {
                "dia": int(dia),
                "data": datetime.date.today().isoformat()}
            self.log(f"📅 Dia do ciclo definido por você: hoje é o dia {dia}. "
                     f"A partir daqui ele anda sozinho a cada dia de pregão.")
        # Grava DIRETO, sem passar por `salvar_plano_trading`: aquela relê
        # todos os campos do formulário e desiste em bloco se qualquer um
        # estiver com texto inválido. O dia escolhido sumiria por causa de uma
        # vírgula errada na caixa da margem — e sem aviso nenhum.
        try:
            salvar_plano_da_conta(self.plano)
        except Exception as e:
            # Sem gravar em disco a escolha morre ao fechar o app. A tela já
            # está certa, então isto nunca pode passar em silêncio.
            self.log(f"⚠️ Não consegui gravar o dia do ciclo no plano "
                     f"({type(e).__name__}) — ele vale nesta sessão, mas "
                     "volta ao automático se você fechar o programa.")
        # forcar=True É OBRIGATÓRIO AQUI. A assinatura do painel olha as
        # posições, a configuração, os sinais e o desempenho — NÃO olha o
        # arquivo do plano. Sem forçar, o clique gravava em disco e a tela não
        # se redesenhava: ele clicaria no dia e nada mudaria na frente dele,
        # que é pior que não ter o botão.
        self._atualizar_dashboard(forcar=True)

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
        # Pega mais sugestões do histórico quando há filtro — senão, filtrar as
        # 10 últimas costuma devolver lista vazia.
        filtro = getattr(self, "filtro_sinais", None)
        filtro = filtro.get() if filtro else "Todas"
        todas = sinais_da_conta_ativa()
        posicoes = carregar_posicoes()
        bruto = list(reversed(todas[-(60 if filtro != "Todas" else 10):]))

        def _classe(s):
            dec = s.get("decisao")
            if dec in ("NAO_OPEROU", "EXPIRADO", "INVALIDADO", "CANCELADO",
                       "CANCELADO_STOP"):
                return "Encerradas"
            if dec in ("ACATOU_COMPRA", "ACATOU_VENDA"):
                p = next((x for x in posicoes if x.get("sinal_id") == s.get("id")), None)
                st = (p or {}).get("status")
                if st in ("FECHADA", "CANCELADA"):
                    return "Encerradas"
                return "Em operação"
            return "Aguardando"

        if filtro == "Todas":
            sinais = bruto[:10]
        else:
            sinais = [s for s in bruto if _classe(s) == filtro][:10]

        if hasattr(self, "lbl_qtd_sinais"):
            self.lbl_qtd_sinais.configure(
                text=f"{len(sinais)} de {len(todas)} no ciclo")

        situacoes = {s["id"]: situacao_do_sinal(s, posicoes) for s in sinais}

        # DESEMPENHO: só reconstrói a lista quando algo muda de verdade — agora
        # a situação/P&L também entram na assinatura, para o acompanhamento
        # aparecer atualizado sem redesenhar tudo a cada 5 s.
        assinatura = (filtro,) + tuple((s["id"], s.get("decisao"), situacoes[s["id"]][0])
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
            resolvido = s.get("decisao") in ("NAO_OPEROU", "EXPIRADO", "INVALIDADO",
                                              "CANCELADO", "CANCELADO_STOP")
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
                    sizing = dimensionar_pelo_plano(
                        sinal["entry"], sinal["stop"], sinal.get("ativo", ""))
                    if sizing["contratos"] <= 0 and sizing.get("motivo_limite"):
                        self.log(f"⚠️ Acatado, mas o plano dimensionou 0 contrato: "
                                 f"{sizing['motivo_limite']}")
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

    # Quantos minutos entre um balanço de descartes e o próximo.
    RESUMO_DESCARTE_MIN = 20

    def _registrar_descarte_qualidade(self, acao, ativo, motivo, rr, prob,
                                       rr_min, prob_min):
        """O piso de qualidade rejeitando cenário é o robô TRABALHANDO — mas do
        jeito antigo ele escrevia a mesma linha a cada ciclo e o log virava um
        muro de '🚧 descartado'. Sete linhas seguidas de MESU6 no pregão de
        10/08 diziam ao trader 'a ferramenta não acerta uma', quando o que elas
        de fato diziam era 'o mercado não está pagando 1:2 agora'.

        Agora: a PRIMEIRA rejeição de cada par ativo+lado aparece na hora (é
        informação nova), as repetições são contadas em silêncio, e de tempos em
        tempos sai um BALANÇO com o melhor R:R que apareceu no período — o
        número que responde 'o piso está alto demais para este mercado?'."""
        chave = f"{acao} {ativo}"
        agora = time.time()
        registro = getattr(self, "_descartes_qualidade", None)
        if registro is None:
            registro = self._descartes_qualidade = {}
        atual = registro.get(chave)
        if atual is None:
            registro[chave] = {"n": 1, "melhor_rr": rr, "melhor_prob": prob,
                               "desde": agora, "ultimo_aviso": agora}
            self.log(f"🚧 {acao} {ativo} descartado pelo piso de qualidade: "
                     f"{motivo}. Aguardando um setup melhor.")
            return
        atual["n"] += 1
        atual["melhor_rr"] = max(atual["melhor_rr"], rr)
        atual["melhor_prob"] = max(atual["melhor_prob"], prob)
        if agora - atual["ultimo_aviso"] < self.RESUMO_DESCARTE_MIN * 60:
            return
        atual["ultimo_aviso"] = agora
        minutos = max(1, int((agora - atual["desde"]) / 60))
        self.log(
            f"🚧 BALANÇO: {atual['n']} cenários de {acao} {ativo} descartados "
            f"nos últimos {minutos} min. O melhor deles chegou a "
            f"R:R 1:{atual['melhor_rr']:.2f} (seu piso é 1:{rr_min:g}) e a "
            f"{atual['melhor_prob']:.0f}% de probabilidade (seu piso é "
            f"{prob_min:g}%). Não é a ferramenta parada: é o mercado não "
            "pagando o que o seu plano exige. Se quiser operar este mercado, "
            "o que muda isso é o piso — 'configura o R:R mínimo para 1.5', "
            "por exemplo. Se não quiser, o certo é exatamente isto: ficar de fora.")

    def _motivo_sem_pendente(self):
        """Por que não há cenário para acatar. Ele disse 'ACATAR' 9 minutos
        depois da sugestão e recebeu só 'não há cenário aguardando decisão' —
        sem saber que o prazo tinha estourado. Agora a resposta diz o motivo."""
        try:
            minutos = max(1, int(self._janela_acatar_seg() / 60))
            todos = sinais_da_conta_ativa()
            sem_decisao = [s for s in todos if not s.get("decisao")]
            if not sem_decisao:
                # AQUI ESTAVA A MENTIRA. O motor marca sozinho a sugestão como
                # EXPIRADO (prazo estourou) ou INVALIDADO (o cenário virou), e
                # a partir daí ela some da lista de "sem decisão". A resposta
                # virava "não há cenário aguardando decisão" — como se nunca
                # tivesse existido sugestão nenhuma, enquanto o botão da
                # notificação na tela ainda funcionava. Agora ela conta o que
                # de fato aconteceu com a última.
                if not todos:
                    return ("Não há cenário aguardando decisão agora — e o "
                            "histórico desta conta está vazio: o motor ainda "
                            "não gerou sugestão nenhuma. Assim que gerar, é só "
                            "dizer 'acatar'.")
                ult = todos[-1]
                idade = max(0, (time.time() * 1000 - ult.get("id", 0)) / 60000)
                rotulos = {
                    "EXPIRADO": (f"EXPIROU — você não respondeu dentro dos "
                                 f"{minutos} minuto(s) do prazo de acatar"),
                    "INVALIDADO": ("foi INVALIDADA — o motor leu um cenário "
                                   "válido na direção contrária e cancelou a "
                                   "sugestão antiga"),
                    "NAO_OPEROU": "foi DISPENSADA por você",
                    "CANCELADO": "teve a ordem CANCELADA por você",
                    "CANCELADO_STOP": ("MORREU antes de nascer — o preço rompeu "
                                       "o stop ANTES de voltar à zona de entrada, "
                                       "então o cenário deixou de existir e não "
                                       "há o que acatar"),
                    "ACATOU_COMPRA": "já foi ACATADA por você",
                    "ACATOU_VENDA": "já foi ACATADA por você",
                }
                dec = str(ult.get("decisao") or "")
                fim = rotulos.get(dec, f"está marcada como {dec}")
                extra = ""
                if dec == "EXPIRADO":
                    extra = (" Se o prazo está curto para o seu ritmo, me diga "
                             "'configura o prazo para acatar em 30 minutos'.")
                elif dec in ("ACATOU_COMPRA", "ACATOU_VENDA"):
                    extra = " Ela já está no diário; acompanho entrada, stop e alvo."
                return (f"Não há cenário AGUARDANDO decisão agora. A última "
                        f"sugestão foi {ult.get('direcao','?')} "
                        f"{ult.get('ativo','?')} @ {ult.get('entry','—')}, de "
                        f"cerca de {idade:.0f} minuto(s) atrás, e ela {fim}."
                        + extra)
            ultimo = sem_decisao[-1]
            idade = max(0, (time.time() * 1000 - ultimo.get("id", 0)) / 60000)
            return (f"Esse cenário EXPIROU: o {ultimo.get('direcao', '')} "
                    f"{ultimo.get('ativo', '')} saiu há cerca de {idade:.0f} "
                    f"minuto(s), e o prazo para acatar é de {minutos} minuto(s) "
                    "— depois disso o preço já não é o mesmo e acatar viraria "
                    "entrada às cegas. Espere a próxima sugestão, ou aumente o "
                    "prazo me dizendo 'configura o prazo para acatar em 30 "
                    "minutos'.")
        except Exception:
            return ("Não há cenário aguardando decisão agora. Assim que sair "
                    "uma sugestão nova, é só dizer 'acatar'.")

    def _analise_sob_demanda(self):
        """Responde ao 'NOVA ANALISE' vindo do WhatsApp: captura AGORA e manda.

        Duas honestidades que esta função precisa ter, porque ele vai estar
        longe do computador quando pedir:
        • se o motor está DESLIGADO, ela diz isso — em vez de silêncio, que
          ele leria como 'a ferramenta parou';
        • se a captura ou a leitura falharem, ela diz o motivo. Um pedido que
          some sem resposta é pior que um 'não consegui'."""
        try:
            self.log("🔄 NOVA ANÁLISE pedida pelo WhatsApp — capturando agora…")
            if not (getattr(self, "motor_rodando", False) or
                    getattr(self, "robo_ativo", False)):
                enviar_relatorio_whatsapp(
                    "⚠️ *Não consegui analisar agora*\nO motor está DESLIGADO "
                    "no computador, então não há como capturar o gráfico. "
                    "Ligue o motor (ou peça 'liga o motor' no chat da TIGER) e "
                    "mande NOVA ANALISE de novo.", None, self.log)
                return
            info = self._capturar_print_agora()
            if not info or not os.path.exists(info.get("caminho", "")):
                enviar_relatorio_whatsapp(
                    "⚠️ *Não consegui capturar o gráfico agora*\nA janela pode "
                    "estar minimizada ou totalmente coberta. Deixe-a visível "
                    "(pode ficar atrás de outras) e mande NOVA ANALISE.",
                    None, self.log)
                return
            self._ultimo_print = info
            ua = getattr(self, "_ultima_analise", None) or {}
            linhas = [f"🔄 *Análise sob demanda — "
                      f"{time.strftime('%d/%m/%Y %H:%M')}*"]
            if ua.get("ativo"):
                linhas.append(
                    f"Última leitura do motor ({ua.get('hora','—')}): "
                    f"*{ua.get('acao')} {ua.get('ativo')}* @ {ua.get('preco')} "
                    f"· probabilidade {ua.get('probabilidade', 0):.0f}%")
                if ua.get("confluencias"):
                    linhas.append("Confluências: "
                                  + " · ".join(ua["confluencias"][:6]))
            else:
                linhas.append("O motor ainda não completou um ciclo de leitura "
                              "— esta é a captura de agora, sem análise nova.")
            try:
                linhas.append("")
                linhas.append(self._chat_status_texto())
            except Exception:
                pass
            linhas.append("")
            linhas.append("_Imagem: a captura de agora. A próxima leitura "
                          "completa sai no ciclo normal do motor._")
            imagem = None
            try:
                from PIL import Image as _Img
                imagem = _Img.open(info["caminho"])
            except Exception:
                imagem = None
            enviar_relatorio_whatsapp("\n".join(linhas), imagem, self.log)
        except Exception as e:
            self.log(f"⚠️ Falha na análise sob demanda: {str(e)[:150]}")
            try:
                enviar_relatorio_whatsapp(
                    "⚠️ *Não consegui completar a análise sob demanda.* "
                    "Confira o Registro no computador — o motivo está lá.",
                    None, self.log)
            except Exception:
                pass

    def _conferir_saude_do_whatsapp(self):
        """Pergunta ao motor como está a ponte e AVISA quando ela está caindo.

        Só avisa na virada de estado — nunca a cada minuto. Aviso repetido vira
        ruído, e ruído é ignorado exatamente quando importa."""
        try:
            r = requests.get(f"{BAILEYS_URL}/status", timeout=3)
            if r.status_code != 200:
                return
            dados = r.json()
        except Exception:
            return
        tentativas = int(dados.get("tentativas_reconexao") or 0)
        instavel = tentativas >= 3
        antes = getattr(self, "_wpp_instavel", False)
        self._wpp_instavel = instavel
        if instavel and not antes:
            quedas = dados.get("quedas_recentes") or []
            codigos = [str(q.get("codigo")) for q in quedas[-5:] if q.get("codigo")]
            detalhe = f" Últimos códigos: {', '.join(codigos)}." if codigos else ""
            self.log(f"📵 A ponte do WhatsApp está INSTÁVEL: {tentativas} tentativas "
                     f"de reconexão seguidas sem conseguir abrir.{detalhe} "
                     "As análises continuam normalmente aqui na tela; o que pode "
                     "atrasar é o relatório no celular.")
            self._chat_feed(
                f"📵 O WhatsApp está caindo e voltando ({tentativas} tentativas "
                "seguidas). Não é o motor: a análise segue rodando e aparecendo "
                "aqui. Se o código 500 se repetir, eu gero um QR novo sozinha — "
                "aí é só escanear de novo pela aba Motor.")
        elif antes and not instavel:
            self.log("✅ A ponte do WhatsApp voltou a ficar estável.")

    def _poller_comandos_whatsapp(self):
        """Lê a fila de comandos do motor (GET /comandos) e aplica ACATAR/
        DISPENSAR ao último cenário pendente — o mesmo efeito dos botões do
        dashboard, mas acionado pela mensagem no WhatsApp."""
        voltas = 0
        while True:
            time.sleep(4)
            voltas += 1
            # A PONTE INSTÁVEL PRECISA APARECER. No pregão de 12/08 o WhatsApp
            # caiu e voltou a tarde toda (códigos 428 e 500) e isso só existia
            # dentro do log do motor. Quem esperava relatório concluía que a
            # ferramenta tinha parado — sem saber de quê. Uma vez por minuto o
            # app pergunta ao motor como anda a ponte, e fala quando não vai bem.
            if voltas % 15 == 0:
                self._conferir_saude_do_whatsapp()
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
                    # NOVA ANÁLISE PELO WHATSAPP. Até aqui o WhatsApp só servia
                    # para DECIDIR sobre um cenário que já tinha saído; não
                    # havia como PEDIR uma leitura. Longe da mesa, isso
                    # significava esperar o próximo ciclo de 5 minutos sem
                    # saber se valia a pena voltar para o computador.
                    if tipo == "NOVA_ANALISE":
                        ts_cmd = cmd.get("ts", 0)
                        if ts_cmd and (time.time() * 1000 - ts_cmd) > 120000:
                            self.log("⌛ Pedido de NOVA ANÁLISE ignorado "
                                     "(obsoleto na fila).")
                            continue
                        threading.Thread(target=self._analise_sob_demanda,
                                         daemon=True).start()
                        continue
                    # STATUS PELO WHATSAPP — o pedido de 14/08, 10:57 e 10:58.
                    # Ele mandou duas vezes e recebeu "aprendido" nas duas,
                    # porque tentou ENSINAR uma ação. Lição vira texto no
                    # pedido ao modelo; quem executa é comando. Agora é comando.
                    #
                    # O texto é o MESMO do 'status' digitado no chat — montado
                    # em código, com os números do disco. Não passa por modelo
                    # nenhum: funciona com a cota estourada e não tem como
                    # inventar número.
                    if tipo == "STATUS":
                        ts_cmd = cmd.get("ts", 0)
                        if ts_cmd and (time.time() * 1000 - ts_cmd) > 120000:
                            self.log("⌛ Pedido de STATUS ignorado "
                                     "(obsoleto na fila).")
                            continue
                        try:
                            texto_status = self._chat_status_texto()
                        except Exception as e:
                            texto_status = ("Não consegui montar o status agora "
                                            f"({type(e).__name__}). Abra o app e "
                                            "confira o Plano de Trading.")
                        self.log("📊 STATUS pedido pelo WhatsApp — respondendo.")
                        enviar_relatorio_whatsapp(
                            f"📊 STATUS\n{texto_status}", None, self.log)
                        continue
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
        self.motor_confirmado = False
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
        api_key = limpar_chave_colada(self.api_entry.get())
        if not api_key:
            self.log("⚠️ Cole a chave da Gemini API primeiro.")
            return

        try:
            intervalo_minutos = max(int(self.intervalo_vivo_var.get().strip()), 1)
        except ValueError:
            self.log("⚠️ Intervalo entre análises inválido — usando 15 min.")
            intervalo_minutos = 15

        salvar_api_key(api_key)
        # A janela do dropdown é a PRINCIPAL (é nela que a automação de ordem e
        # a leitura de posições trabalham). Ela entra na frente da lista sem
        # derrubar as outras que você adicionou para análise.
        _principal = self.janela_var.get().strip()
        _lista = janelas_monitoradas()
        if _principal and not _principal.startswith("("):
            _lista = [_principal] + [j for j in _lista if j != _principal]
        salvar_janelas_monitoradas(_lista)
        salvar_config({
            "intervalo_minutos": intervalo_minutos,
            "hora_inicio": self.entry_hora_inicio.get().strip() or "09:00",
            "hora_fim": self.entry_hora_fim.get().strip() or "17:00",
        })

        self.parar_solicitado = False
        # Zera o veredito da tentativa anterior: sem isto, um LIGAR MOTOR novo
        # herdaria o "morreu ao subir" da tentativa passada.
        self.motor_confirmado = False
        self.motor_morreu_ao_subir = False
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
                f"está ao lado do {plataforma.nome_do_executavel()}."
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
        npm_cmd = plataforma.comando_npm()
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

    def _liberar_porta_do_motor(self):
        """Tira da frente o Node ÓRFÃO que sobrou de uma execução anterior.

        Aquele processo é lixo que o PRÓPRIO programa deixou: o motor é um Node
        que ele sobe, e quando o app é fechado à força o filho fica de pé
        segurando a porta 3939. A partir daí, todo LIGAR MOTOR morre com
        EADDRINUSE — foi o que aconteceu três vezes seguidas no log de 11/08.
        A versão anterior mandava o trader abrir o Terminal e digitar
        `lsof -ti :3939 | xargs kill -9`. Passar para o trader a limpeza do
        nosso lixo, no meio do pregão, não é aceitável. Agora o programa limpa.

        Só mata processo chamado 'node'. Se a porta estiver ocupada por outra
        coisa, ele NÃO mata nada e diz o que encontrou."""
        try:
            mortos, recusados = plataforma.liberar_porta(3939, so_processos=("node",))
        except Exception as e:
            self.log(f"(não consegui checar a porta 3939: {e})")
            return
        for pid, nome in mortos:
            self.log(f"🧹 Encerrei um motor órfão que estava segurando a porta "
                     f"3939 (PID {pid}, {nome}). Era sobra de uma execução "
                     "anterior — agora a porta está livre.")
        for pid, nome in recusados:
            self.log(f"⛔ A porta 3939 está ocupada por '{nome}' (PID {pid}), que "
                     "NÃO é o motor. Não vou matar um processo que não é meu. "
                     "Feche esse programa e ligue o motor de novo.")

    def _subir_processo_node(self):
        # Limpa ANTES de tentar subir: é a diferença entre "não liga e você que
        # se vire" e "não liga, então eu resolvo e ligo".
        self._liberar_porta_do_motor()
        self.log("🚀 Iniciando processo do motor (node index.js)...")

        # No Windows isso esconde o console preto do node; no macOS o
        # dicionário volta vazio, porque lá não existe console para esconder.
        self.processo_motor = subprocess.Popen(
            [plataforma.caminho_node() or "node", "index.js"], cwd=DIR_DADOS_MOTOR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            **plataforma.opcoes_subprocess(),
        )
        self.motor_confirmado = False   # só vira True quando a porta responder
        self.motor_rodando = True
        self.log(f"✅ Processo criado (PID {self.processo_motor.pid}). Aguardando resposta...")
        self.after(0, lambda: self.btn_ligar.configure(
            state="normal", text="⏹️ DESLIGAR MOTOR", fg_color="#8b1f1f", hover_color="#b52626"))

        time.sleep(1.5)
        if self.processo_motor.poll() is not None:
            self.motor_rodando = False
            self.motor_morreu_ao_subir = True
            self.log(f"⚠️ O processo do Node encerrou IMEDIATAMENTE (código {self.processo_motor.returncode}). "
                      "Causa mais provável: a porta 3939 já está ocupada por um processo de um teste "
                      f"anterior.\n{plataforma.como_matar_processo_travado(3939)}")
            self.after(0, lambda: self.btn_ligar.configure(state="normal", text="▶️ LIGAR MOTOR", fg_color="green", hover_color="#1f8b4c"))
            return
        self.motor_morreu_ao_subir = False

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
                    # ESTE é o único ponto em que o motor está PROVADAMENTE de
                    # pé: a porta respondeu. É o que a TIGER espera antes de
                    # dizer "motor no ar" — antes ela olhava só a flag
                    # `motor_rodando`, que era ligada assim que o Popen voltava,
                    # e por isso anunciava "motor no ar" 1,5 s antes de o
                    # processo morrer com a porta ocupada.
                    self.motor_confirmado = True
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
                # A seção do WhatsApp nasce RECOLHIDA (depois de pareado, ela
                # não se toca mais). Mas um QR code dentro de um bloco fechado
                # é um QR que ninguém escaneia — quando ele chega, o bloco abre
                # sozinho.
                secao = getattr(self, "sec_whatsapp", None)
                if secao is not None and hasattr(secao, "abrir_secao"):
                    try:
                        secao.abrir_secao()
                    except Exception:
                        pass
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
        # COOLDOWN COMPARTILHADO COM A TIGER. Antes cada lado tinha o seu, e o
        # chat gastava rede tentando modelos que o motor já sabia estarem sem
        # cota — e vice-versa. Agora é o mesmo dicionário: quem descobre, avisa.
        cooldown_modelos = _MODELOS["cooldown"]
        COOLDOWN_COTA = COOLDOWN_COTA_SEG
        COOLDOWN_SOBRECARGA = COOLDOWN_SOBRECARGA_SEG

        # Lista de modelos de reserva: se o principal esgotar a cota (comum
        # no plano gratuito — 20 requisições/dia por modelo), tenta os
        # próximos automaticamente em vez de travar o ciclo inteiro.
        # A LISTA VEM DO REGISTRO COMPARTILHADO — a mesma que a TIGER usa.
        # Duas listas diferentes foi o que fez o motor analisar normalmente
        # enquanto ela dizia "cota estourada" para o mesmo print, no mesmo
        # minuto: o chat só conhecia cinco modelos da família 2.0, justamente
        # a que estava esgotada.
        modelos_fallback = descobrir_modelos(client, forcar=True, log=self.log)
        # Mesmo conjunto de descontinuados que a TIGER enxerga.
        modelos_invalidos = _MODELOS["invalidos"]
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
        # ANTI-CHICOTE: janela em que uma INVERSÃO de direção no mesmo ativo é
        # tratada como indecisão do mercado, não como cenário novo. Nela, virar
        # a mão exige probabilidade acima do piso normal.
        JANELA_ANTI_CHICOTE_SEG = 30 * 60
        MARGEM_ANTI_CHICOTE = 10.0
        HORA_INICIO = config_horario.get("hora_inicio", "09:00")
        HORA_FIM = config_horario.get("hora_fim", "17:00")
        # ---------------- ESTADO POR JANELA (multi-ativo) ----------------
        # Cada janela monitorada é um ATIVO DIFERENTE, e cada uma precisa da sua
        # própria memória de ciclo. Se o cenário ativo, o hash da última captura
        # e o preço anterior fossem compartilhados, o robô trataria o gráfico do
        # MES e o do NQ como se fossem o mesmo: o hash de um marcaria o outro
        # como "quadro congelado", e um cenário aberto num ativo seria fechado
        # pelo preço do outro. É o erro que não pode acontecer aqui.
        def novo_estado_janela():
            return {
                "sinal_ativo": {"estado": "ENCERRADA"},
                "ledger_text_memory": ("Nenhuma operação aberta no momento. "
                                        "Aguardando primeiro sinal institucional."),
                "hash_captura_anterior": None,
                "capturas_congeladas": 0,
                "preco_anterior_lido": None,
                "ciclos_preco_igual": 0,
                # Quantos ciclos seguidos esta janela devolveu algo que não é
                # gráfico. Por janela, nunca global: uma janela errada não pode
                # calar o alerta da outra, que pode estar certa.
                "ciclos_sem_grafico": 0,
                # Ciclos seguidos perdidos por falha do modelo. Por janela: uma
                # janela com problema não pode disparar aviso pela outra.
                "ciclos_perdidos": 0,
            }

        estados_janela = {}

        def janelas_para_analisar():
            """As janelas que entram neste ciclo, lidas do disco a cada volta —
            você pode incluir ou remover uma com o motor ligado.

            Lista vazia devolve [""] de propósito: é o comportamento antigo de
            capturar a tela inteira quando nenhuma janela foi escolhida."""
            return janelas_monitoradas() or [""]

        sinal_ativo = {"estado": "ENCERRADA"}
        ledger_text_memory = "Nenhuma operação aberta no momento. Aguardando primeiro sinal institucional."
        hash_captura_anterior = None
        capturas_congeladas = 0
        preco_anterior_lido = None
        ciclos_preco_igual = 0
        self.log(f"⚙️ Intervalo: {INTERVALO_MINUTOS} min | Pregão: {HORA_INICIO}–{HORA_FIM} "
                  "(fora desse horário, ciclos são pulados pra economizar cota da API)")

        def horario_pregao_atual():
            """Relê o horário a CADA ciclo — a TIGER pode reconfigurar o pregão
            pelo chat com o motor ligado, e a mudança tem de valer sem
            reiniciar (era lido uma vez só, na subida)."""
            cfg = carregar_config()
            return (cfg.get("hora_inicio", HORA_INICIO) or HORA_INICIO,
                    cfg.get("hora_fim", HORA_FIM) or HORA_FIM)

        def dentro_do_horario_pregao():
            ini_txt, fim_txt = horario_pregao_atual()
            try:
                agora = datetime.datetime.now().time()
                inicio = datetime.datetime.strptime(ini_txt, "%H:%M").time()
                fim = datetime.datetime.strptime(fim_txt, "%H:%M").time()
                # Pregão que vira o dia (ex.: 19:00 às 02:00) é legítimo para
                # quem opera índice americano de madrugada.
                if inicio <= fim:
                    return inicio <= agora <= fim
                return agora >= inicio or agora <= fim
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
                    _ini, _fim = horario_pregao_atual()
                    self.log(f"🌙 Fora do horário de pregão ({_ini}–{_fim}) — ciclo pulado sem consumir a API.")
                    continue

                # --------------------------------------------------------
                # CAPTURA EM SEGUNDO PLANO: pega o conteúdo da janela da
                # corretora diretamente, SEM trazê-la para frente e sem
                # tirar o usuário do que ele estiver fazendo em outro
                # programa. Se não achar a janela ou a captura vier em
                # branco, pula o ciclo em vez de analisar lixo visual.
                # --------------------------------------------------------
                # MULTI-JANELA: o motor percorre TODAS as janelas configuradas em
                # cada ciclo. O estado de análise (cenário ativo, hash da última
                # captura, preço anterior) é POR JANELA — sem isso o robô
                # confundiria o gráfico de um ativo com o do outro, que é
                # exatamente o erro que não pode acontecer aqui.
                _janelas_ciclo = janelas_para_analisar()
                for _idx_janela, nome_janela in enumerate(_janelas_ciclo):
                    # A PRINCIPAL é a primeira da lista. Só ela conversa com a
                    # corretora (leitura de posições e envio de ordem): ler
                    # posição da Tradovate enquanto se analisa o gráfico do
                    # Profit misturaria dois mundos diferentes.
                    janela_principal = (_idx_janela == 0)
                    est = estados_janela.setdefault(nome_janela, novo_estado_janela())
                    sinal_ativo = est["sinal_ativo"]
                    hash_captura_anterior = est["hash_captura_anterior"]
                    capturas_congeladas = est["capturas_congeladas"]
                    preco_anterior_lido = est["preco_anterior_lido"]
                    ciclos_preco_igual = est["ciclos_preco_igual"]
                    ciclos_sem_grafico = est["ciclos_sem_grafico"]
                    ledger_text_memory = est["ledger_text_memory"]
                    try:
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
                            screenshot = plataforma.capturar_tela_inteira()
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

                        # OLHOS DA TIGER: guarda esta captura para o chat. A partir daqui
                        # dá para perguntar "olha o gráfico agora" e ela analisa ESTA
                        # imagem — a mesma que o motor está lendo neste ciclo.
                        info_print = salvar_ultimo_print(
                            screenshot, nome_janela or "tela inteira")
                        if info_print:
                            self._ultimo_print = info_print

                        # DETECÇÃO DE POSIÇÃO NA PLATAFORMA: antes de analisar, confere na
                        # corretora se você já está posicionado (inclusive numa operação
                        # aberta por fora da sugestão) e reflete isso no diário/dashboard.
                        # Só na janela PRINCIPAL: a leitura de posições vem da
                        # aba da Tradovate via CDP e não tem relação com o
                        # gráfico das outras janelas. Rodar isso a cada janela
                        # repetiria a mesma leitura e, pior, associaria a
                        # posição ao ativo da janela errada.
                        if (janela_principal
                                and getattr(self, "tv_sync_var", None)
                                and self.tv_sync_var.get()):
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
                            f"{bloco_licoes_prompt()}"
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
                            "COMO ESCREVER O 'market_analysis' (linguagem natural):\n"
                            "Escreva em PORTUGUÊS CLARO E CORRIDO, como um mentor de mesa "
                            "explicando ao vivo para o trader ao lado — não como um relatório "
                            "técnico picotado. Conte a HISTÓRIA do gráfico nesta ordem: (1) o "
                            "que o preço vinha fazendo; (2) o que mudou agora e por quê; "
                            "(3) onde está a liquidez que o mercado ainda vai buscar; (4) por "
                            "que a entrada é NESTE ponto e não noutro; (5) o que invalidaria a "
                            "ideia. Use os nomes técnicos (BOS, order block, FVG, sweep) mas "
                            "SEMPRE explicando o que significam naquele gráfico — 'varreu os "
                            "fundos iguais em 7541, pegando os stops de quem estava comprado, "
                            "e voltou' vale mais que 'SSL sweep'. Evite siglas soltas e "
                            "listas secas. De 3 a 6 frases.\n"
                            "\n"
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

                        # O COOLDOWN ORDENA A FILA. ELE NÃO CORTA NINGUÉM.
                        #
                        # DEFEITO MEU, E FOI ELE QUE MATOU AS ANÁLISES DO DIA 13.
                        # Antes isto era um FILTRO: modelo em cooldown ficava de
                        # fora, e a lista só era restaurada se ficasse VAZIA. No
                        # log das 14:45 havia 11 modelos; 9 tinham entrado em
                        # cooldown de cota dois minutos antes, postos lá pela
                        # conversa do chat; sobraram exatamente os 2 que estavam
                        # mortos com 404. O motor tentou esses 2, falhou, e
                        # escreveu "Todos os modelos disponíveis falharam" —
                        # tendo tentado 2 de 11. Daí em diante: nenhuma análise,
                        # nenhum relatório no WhatsApp, e nenhuma pista no log.
                        #
                        # Cooldown é uma APOSTA sobre o futuro ("este aqui
                        # provavelmente ainda está sem cota"). Perder o ciclo
                        # inteiro por causa de uma aposta custa 5 minutos de
                        # mercado; tentar um modelo estacionado custa uma
                        # requisição. Agora os estacionados vão para o FIM da
                        # fila — que é o que o lado do chat (`modelos_para_tentar`)
                        # já fazia certo desde a v2.24.
                        # MESMA função do lado do chat. Antes eram duas cópias
                        # da regra, e a daqui era a errada.
                        agora_ts = time.time()
                        candidatos, n_parados = fila_por_cooldown(
                            modelos_fallback, cooldown_modelos, agora_ts)
                        n_livres = len(candidatos) - n_parados
                        if n_parados and not n_livres:
                            self.log("⏳ Todos os modelos estão em cooldown de cota/sobrecarga — "
                                      "tentando mesmo assim. (Considere aumentar o intervalo ou usar chave paga.)")
                        elif n_parados:
                            self.log(f"⏳ {n_parados} modelo(s) em cooldown foram para o fim "
                                      f"da fila — {n_livres} livre(s) primeiro. Nenhum fica de fora: "
                                      "perder o ciclo custa mais que uma tentativa.")

                        # UMA SEGUNDA PASSADA, PORQUE 503 SIGNIFICA "TENTE DE NOVO".
                        # Log de 13/08, 10:35 e 10:40: dois ciclos seguidos
                        # perdidos inteiros com 503 UNAVAILABLE ("high demand,
                        # spikes are usually temporary") e 504 DEADLINE.
                        # A palavra do próprio Google é TEMPORÁRIO — e a
                        # ferramenta respondia a isso jogando fora CINCO
                        # MINUTOS de mercado e esperando o ciclo seguinte.
                        # Vinte segundos de espera custam quase nada e
                        # recuperam a maioria desses casos. Uma passada extra
                        # só, e só para erro transitório: com cota estourada
                        # ou chave inválida, insistir é desperdício.
                        for tentativa in (1, 2):
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
                                    # Respondeu: sai do cooldown E passa a liderar a
                                    # fila também no chat — a TIGER começa pelo que
                                    # acabou de funcionar, em vez de descobrir sozinha.
                                    registrar_sucesso_modelo(modelo_atual)
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

                            if resposta is not None:
                                break            # respondeu: nada a repetir
                            if tentativa == 1 and \
                                    classificar_erro_modelo(ultimo_erro) == "transitorio":
                                self.log("⏳ Todos os modelos deram erro TEMPORÁRIO "
                                         "(o próprio Google chama de 'pico de demanda'). "
                                         "Esperando 20s e tentando de novo — jogar o "
                                         "ciclo fora custaria 5 minutos de mercado.")
                                time.sleep(20)
                                continue
                            break                # cota, chave ou erro real: não insiste

                        # Expurga de vez os modelos descontinuados, para não perder
                        # tempo tentando-os em todos os ciclos seguintes.
                        if modelos_invalidos & set(modelos_fallback):
                            # NÃO limpa o conjunto: ele é compartilhado com a
                            # TIGER, e esquecer o que foi descontinuado faria os
                            # dois lados tentarem de novo o que já morreu.
                            modelos_fallback = [m for m in modelos_fallback if m not in modelos_invalidos]
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

                        # ---- A IA LOCAL COM VISÃO É A ÚLTIMA RESERVA ----
                        # Em 13/08, TODOS os dez modelos da Gemini devolveram
                        # 503 ou 429 no mesmo ciclo, duas passadas seguidas, e
                        # a análise morreu — com a IA local instalada, no ar e
                        # INÚTIL, porque o modelo baixado era de texto puro e
                        # não enxerga imagem. Ele perguntou, com razão: "por
                        # que não tenta a IA local?".
                        #
                        # Agora tenta. Uma leitura de reserva, que passa pelas
                        # MESMAS travas (preço conferido contra o título,
                        # ticker conhecido, piso de qualidade), vale mais que
                        # nenhuma leitura. E ela é declarada como reserva no
                        # log — não vou deixar parecer leitura da Gemini.
                        if resposta is None:
                            instalados_local = ia_local_no_ar(timeout=3) or []
                            if not instalados_local:
                                self.log("🖥️ A IA local não está no ar — não há "
                                         "reserva para assumir. Ligue-a na aba "
                                         "Motor ('Instalar a IA LOCAL').")
                            elif not tem_modelo_de_visao(instalados_local):
                                self.log(
                                    "🖥️ A IA local está no ar "
                                    f"({', '.join(instalados_local)}), mas "
                                    "NENHUM desses modelos enxerga imagem — "
                                    "são de texto puro. Sem modelo de visão "
                                    "ela não lê gráfico nenhum. Clique em "
                                    "'Instalar a IA LOCAL' na aba Motor que "
                                    "eu trago o modelo que enxerga.")
                            else:
                                self.log("🖥️ Gemini fora — chamando a IA LOCAL "
                                         f"com visão ({modelo_de_visao_instalado(instalados_local)}). "
                                         "A primeira leitura é lenta: ela "
                                         "carrega alguns GB do disco.")
                                t_local = time.time()
                                bruto, porque = analisar_grafico_local(
                                    screenshot, PROMPT_FINAL)
                                if analise_local_valida(bruto):
                                    self.log("🖥️ Leitura feita pela IA LOCAL em "
                                             f"{time.time() - t_local:.0f}s. É "
                                             "reserva: lê pior que a Gemini, e "
                                             "passa pelas mesmas travas.")
                                    resposta = type("R", (), {"text": bruto})()
                                    modelo_vencedor = "IA local (visão)"
                                elif bruto:
                                    self.log("🖥️ A IA local respondeu, mas fora "
                                             "do formato esperado (faltaram "
                                             "campos obrigatórios) — descartado. "
                                             "Chutar o que faltou seria inventar.")
                                else:
                                    # O MOTIVO, POR EXTENSO. "não devolveu
                                    # resposta neste ciclo" foi o que ele leu
                                    # no dia 13, e essa frase não permite
                                    # fazer nada a respeito.
                                    self.log(f"🖥️ A IA local não leu: {porque}.")
                        if resposta is None:
                            # QUANTOS, POR NOME. "Todos os modelos falharam"
                            # sobre 2 tentativas de 11 foi exatamente o que
                            # escondeu o defeito do cooldown por um dia inteiro:
                            # a frase estava certa sobre os que tentou, e
                            # calada sobre os que não tentou.
                            raise RuntimeError(
                                f"Falharam os {len(candidatos)} modelo(s) tentados "
                                f"({', '.join(candidatos)}). Último erro: {ultimo_erro}"
                            )

                        sinal = json.loads(resposta.text)
                        preco = sinal.get("current_price")
                        acao = sinal.get("action", "HOLD")
                        confianca = sinal.get("confidence_score", 0)
                        probabilidade = sinal.get("probabilidade", 0)
                        confluencias = sinal.get("confluence_factors", []) or []
                        ativo = sinal.get("asset_symbol", "DESCONHECIDO")

                        # ---- ISSO NÃO É UM GRÁFICO ----
                        # A janela 'Claude — Claude' ficou 20 minutos sendo
                        # analisada como se fosse mercado. Nada do que vem
                        # daqui pode seguir adiante: nem leitura, nem posição,
                        # nem sugestão. E o trader precisa SABER, senão vai
                        # continuar esperando um sinal que nunca vem.
                        # ---- O TÍTULO DA JANELA CONFERE O PREÇO ----
                        # 13/08, 10:05: a janela dizia 'MESU2026 7.784,00' e o
                        # motor mandou um cenário inteiro em cima de 7753.25 —
                        # 30 pontos fora, numa região que o preço já tinha
                        # deixado. E 7753.25 era o número que o modelo tinha
                        # INVENTADO no dia anterior; ele grudou nele.
                        # A trava de preço congelado não pega isso porque o
                        # valor oscilava. O título, sim: ele é texto do sistema
                        # operacional, escrito pela corretora ao vivo, e não
                        # tem como ser alucinado.
                        bate_titulo, preco_titulo = preco_bate_com_o_titulo(
                            preco, nome_janela)
                        if not bate_titulo:
                            self.log(
                                f"🚫 LEITURA DESCARTADA: o modelo leu {preco} e "
                                f"o título da janela diz {preco_titulo}. São "
                                f"{abs(preco - preco_titulo):.2f} pontos de "
                                "diferença — isso não é a mesma tela. Nenhuma "
                                "sugestão sai desta leitura.")
                            self._chat_feed(
                                f"🚫 Descartei a leitura de agora: eu li "
                                f"{preco} e a janela mostra {preco_titulo}. "
                                "Não vou te sugerir nada em cima de um preço "
                                "que não é o da sua tela.")
                            continue
                        e_grafico, motivo_nao_grafico = leitura_e_de_grafico(ativo, preco)
                        if not e_grafico:
                            ciclos_sem_grafico += 1
                            onde = nome_janela or "tela inteira"
                            self.log(
                                f"🚫 '{onde}' NÃO é um gráfico: {motivo_nao_grafico}. "
                                f"Nenhuma análise feita ({ciclos_sem_grafico}º ciclo "
                                "seguido). Escolha a janela do gráfico na aba Motor.")
                            if ciclos_sem_grafico == 2:
                                self._chat_feed(
                                    f"🚫 Estou olhando para '{onde}' e ali não há "
                                    f"gráfico nenhum — {motivo_nao_grafico}. Não vou "
                                    "fingir leitura de mercado em cima disso. Troque a "
                                    "janela monitorada na aba Motor que eu volto a "
                                    "analisar no ciclo seguinte.")
                                enviar_relatorio_whatsapp(
                                    f"🚫 *Janela errada — {time.strftime('%d/%m/%Y %H:%M:%S')}*\n"
                                    f"A janela monitorada é '{onde}', e ali não há "
                                    f"gráfico: {motivo_nao_grafico}.\n"
                                    "Nenhuma sugestão será gerada até a janela certa "
                                    "ser escolhida.", None, self.log)
                                falar("Atenção. A janela monitorada não é um gráfico. "
                                      "Análises suspensas.")
                            continue
                        if ciclos_sem_grafico:
                            self.log(f"✅ '{nome_janela or 'tela inteira'}' voltou a "
                                     f"entregar gráfico ({ativo}) — análises retomadas.")
                            ciclos_sem_grafico = 0

                        # Guardado para a detecção de posições associar a leitura do campo
                        # POSIÇÃO quando o painel não mostra o ticker ao lado.
                        # SÓ da janela PRINCIPAL: é a única ligada à corretora.
                        # Deixar a última janela analisada sobrescrever isso faria
                        # a posição do MES ser rotulada com o ticker do NQ — é o
                        # tipo de mistura que não pode existir aqui.
                        if janela_principal:
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

                        # Alimenta o CHAT da IA com a leitura mais recente do gráfico —
                        # é o que permite conversar "sobre a análise de agora".
                        # Com vários gráficos, a leitura carrega DE QUAL JANELA
                        # ela veio — senão, no chat, a resposta sobre "o gráfico"
                        # seria a do último ativo analisado, sem ele saber.
                        self._ultima_analise = {
                            "hora": time.strftime('%H:%M'),
                            "janela": nome_janela or "tela inteira",
                            "ativo": ativo, "acao": acao, "preco": preco,
                            "confianca": confianca, "probabilidade": probabilidade,
                            "confluencias": list(confluencias),
                            "analise": str(sinal.get("market_analysis", ""))[:1200],
                            "entry": sinal.get("entry_price"), "stop": sinal.get("stop_loss"),
                            "tp1": sinal.get("take_profit_1"), "tp2": sinal.get("take_profit_2"),
                        }
                        # Guarda também POR ATIVO: assim ele pode perguntar "e o
                        # NQ?" sem perder a leitura do MES feita segundos antes.
                        if not hasattr(self, "_analises_por_ativo"):
                            self._analises_por_ativo = {}
                        if ativo and ativo != "DESCONHECIDO":
                            self._analises_por_ativo[str(ativo).upper()] = \
                                dict(self._ultima_analise)

                        _marca_janela = (f" | Janela: {nome_janela[:28]}"
                                         if len(_janelas_ciclo) > 1 and nome_janela else "")
                        self.log(f"📊 Ativo: {ativo} | Leitura IA: {acao} | Confiança: {confianca}% | "
                                  f"Probabilidade: {probabilidade}% | Preço: {preco}{_marca_janela}")

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

                        # ---- LEITURA CONGELADA NÃO GERA SUGESTÃO ----
                        # Este é o defeito que explica "nenhuma entrada de hoje foi
                        # válida". No log de 11/08, das 18:01 às 18:11, o preço ficou
                        # travado em 7753,25 por TREZE ciclos — e o motor seguiu
                        # despejando cenário em cima da MESMA imagem parada, virando
                        # de SELL para BUY e de volta para SELL:
                        #     18:05 BUY · 18:06 SELL · 18:07 SELL · 18:10 BUY · 18:11 BUY
                        # Não era leitura de mercado: era o modelo inventando estrutura
                        # numa figura que não mudava. O aviso existia e não impedia
                        # nada — avisar sem agir é o mesmo que não avisar.
                        leitura_congelada = (
                            ciclos_preco_igual + 1 >= CICLOS_PARA_PRECO_CONGELADO)
                        if leitura_congelada and acao in ("BUY", "SELL"):
                            if not getattr(self, "_avisou_congelado", False):
                                self._avisou_congelado = True
                                self.log(
                                    f"🧊 SUGESTÕES SUSPENSAS: o preço de {ativo} está "
                                    f"parado em {preco} há {ciclos_preco_igual + 1} "
                                    "leituras. Uma tela que não muda não é análise — "
                                    "qualquer cenário daqui seria o modelo inventando "
                                    "estrutura numa figura parada. Volto a sugerir no "
                                    "instante em que o preço se mexer. Se o mercado "
                                    "está aberto, confira se a janela do gráfico é a "
                                    "certa e se ela está atualizando.")
                                self._chat_feed(
                                    f"🧊 Parei de sugerir: o preço de {ativo} não se "
                                    f"mexe há {ciclos_preco_igual + 1} leituras. "
                                    "Volto sozinha quando a tela atualizar.")
                        elif not leitura_congelada:
                            self._avisou_congelado = False
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
                            self._tratar_evento_posicao(tipo, pos,
                                                        origem_preco="da análise")

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

                        # SINCRONIA COM O DIÁRIO (relatório fiel). O cenário e a ordem no
                        # diário são duas visões da MESMA coisa. Se a ordem já saiu de
                        # cena — você cancelou, bateu stop/alvo, ou a plataforma encerrou
                        # — o acompanhamento do cenário TEM de morrer junto. Sem esta
                        # trava, o robô seguia narrando um trade que não existia mais.
                        if sinal_ativo.get("estado") != "ENCERRADA" and sinal_ativo.get("sinal_id"):
                            _pos_lig = next((p for p in carregar_posicoes()
                                             if p.get("sinal_id") == sinal_ativo["sinal_id"]), None)
                            if _pos_lig and _pos_lig.get("status") not in ("PENDENTE", "ABERTA"):
                                self.log(f"🔗 A ordem deste cenário está "
                                          f"{_pos_lig.get('status')} — encerrando o "
                                          "acompanhamento para o relatório não divergir.")
                                self.sinais_acatados.discard(sinal_ativo["sinal_id"])
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
                                    # O CENÁRIO MORREU AQUI — e o registro dele
                                    # precisa saber disso. Antes o motor encerrava
                                    # só o estado em memória e o sinal no disco
                                    # continuava com `decisao: None`, ou seja,
                                    # "aguardando sua decisão" no dashboard, para
                                    # sempre, num cenário que já não existe. E o
                                    # 'acatar' no chat ficava tentando acatar um
                                    # morto.
                                    _sid_rs = sinal_ativo.get("sinal_id")
                                    if _sid_rs:
                                        atualizar_decisao_sinal(_sid_rs, "CANCELADO_STOP")
                                        cancelar_pendentes_do_sinal(
                                            _sid_rs, "stop rompido antes da entrada")
                                    sinal_ativo = {"estado": "ENCERRADA"}
                                    self.log("🚫 SINAL CANCELADO: Stop rompido antes de mitigar a entrada.")
                                    self.after(0, self._atualizar_dashboard)
                                elif bateu_entrada:
                                    sinal_ativo["estado"] = "ATIVA"
                                    msg = f"🎯 *ENTRADA ACIONADA — {direcao}*\nPreço mitigou a zona em {sinal_ativo['entry']}."
                                    self.log(msg)
                                    if acatado_atual:
                                        enviar_relatorio_whatsapp(msg, screenshot, self.log)
                                        falar(f"Ordem de {direcao} ativada no mercado.")
                                elif sinal_ativo["candles"] >= MAX_CANDLES:
                                    _sid_mc = sinal_ativo.get("sinal_id")
                                    if _sid_mc:
                                        atualizar_decisao_sinal(_sid_mc, "EXPIRADO")
                                        cancelar_pendentes_do_sinal(
                                            _sid_mc, "preço não voltou à zona de entrada")
                                    sinal_ativo = {"estado": "ENCERRADA"}
                                    self.log("⌛ SINAL EXPIRADO: Nenhuma mitigação no tempo limite.")
                                    self.after(0, self._atualizar_dashboard)

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
                                                                  sinal_ativo["tp1"], sinal_ativo["stop"], "LOSS", ativo,
                                                                  sinal_ativo.get("confluencias"))
                                    sinal_ativo = {"estado": "ENCERRADA"}
                                    msg = f"🔴 *STOP ATINGIDO (LOSS) — {direcao}*\nOperação invalidada em {preco}."
                                    self.log(msg)
                                    if acatado_atual:
                                        enviar_relatorio_whatsapp(msg, screenshot, self.log)
                                        falar("Stop atingido. Dados gravados no banco de aprendizado.")
                                    self.after(0, self._atualizar_dashboard)

                                elif bateu_tp2:
                                    salvar_resultado_performance(direcao, sinal_ativo["entry"], sinal_ativo["stop"],
                                                                  sinal_ativo["tp2"], sinal_ativo["tp2"], "WIN", ativo,
                                                                  sinal_ativo.get("confluencias"))
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
                                                                  sinal_ativo["tp1"], sinal_ativo["tp1"], "WIN", ativo,
                                                                  sinal_ativo.get("confluencias"))
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
                        _tp1 = sinal.get("take_profit_1") or 0
                        _tp2 = sinal.get("take_profit_2") or 0
                        _risco = abs(_ep - _sl)

                        # APRENDIZADO ENTRA NA CONTA. A probabilidade que a IA leu do
                        # gráfico é corrigida pelo que ESTA conta já viveu com estes
                        # mesmos padrões e neste mesmo horário. Um padrão que vem
                        # falhando perde pontos e passa a ser barrado pelo piso; um que
                        # vem acertando ganha. O número original fica guardado, para o
                        # log mostrar de onde veio a diferença.
                        probabilidade_ia = probabilidade
                        _delta, _porques = ajuste_por_aprendizado(
                            confluencias, time.strftime('%H'))
                        if _delta:
                            probabilidade = round(
                                max(0.0, min(100.0, probabilidade + _delta)), 1)
                            if acao in ("BUY", "SELL"):
                                self.log(
                                    f"🧠 APRENDIZADO: probabilidade {probabilidade_ia:.0f}% → "
                                    f"{probabilidade:.0f}% ({_delta:+.1f} pts pelo seu "
                                    f"histórico). " + " · ".join(_porques))

                        # PISO DE QUALIDADE — decisão de código, em função pura e
                        # testada (ver tests/test_piso_qualidade.py).
                        _piso = avaliar_piso_de_qualidade(
                            acao, _ep, _sl, _tp1, _tp2, RR_MINIMO,
                            probabilidade, PROBABILIDADE_MINIMA)
                        qualidade_ok = _piso["ok"]
                        rr_sinal = _piso["rr"]
                        rr_tp1, rr_tp2 = _piso["rr_tp1"], _piso["rr_tp2"]
                        alvo_do_piso = _piso["alvo_do_piso"]

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

                        # LEITURA CONGELADA: entra na MESMA porta que os outros
                        # filtros (`repetido`), porque o efeito é o mesmo — não
                        # emitir. O aviso já saiu acima; aqui é a ação.
                        if leitura_congelada and acao in ("BUY", "SELL"):
                            repetido = True

                        # ENTRADA LONGE DEMAIS DO PREÇO. No log de 11/08 saiu um
                        # SELL com entrada em 7785,00 com o mercado em 7741,75 —
                        # 8,6 vezes o risco de distância. Aquilo não é ordem
                        # limitada esperando o preço voltar; é um nível que não
                        # seria tocado, e não foi: a ordem ficou pendente e
                        # morreu. Sugestão que não tem chance de acontecer não
                        # deveria ocupar o lugar de uma que tem.
                        if not repetido and acao in ("BUY", "SELL"):
                            _ok_dist, _dist_r = avaliar_distancia_da_entrada(
                                _ep, _sl, preco)
                            if not _ok_dist:
                                repetido = True
                                self.log(
                                    f"📏 {acao} {ativo} @ {_ep} descartado: a entrada "
                                    f"está a {_dist_r:.1f}× o risco de distância do "
                                    f"preço atual ({preco}), acima do limite de "
                                    f"{MAX_DISTANCIA_ENTRADA_R:g}×. Uma ordem tão "
                                    "longe raramente é tocada — ela expiraria sem "
                                    "nunca ter tido chance.")

                        if not repetido and acao in ("BUY", "SELL") and _ep > 0 and _risco:
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

                        # ANTI-CHICOTE: o motor virou de BUY para SELL (ou o contrário)
                        # no mesmo ativo em poucos minutos. Num mercado lateral isso
                        # acontece o tempo todo, e é exatamente o padrão que faz o trader
                        # tomar stop nas duas pontas. Trocar de lado exige convicção
                        # acima do piso — não basta passar raspando.
                        chicote = False
                        if acao in ("BUY", "SELL") and _ep > 0:
                            limite_chic = (time.time() - JANELA_ANTI_CHICOTE_SEG) * 1000
                            for s_ant in sinais_da_conta_ativa():
                                if s_ant.get("id", 0) < limite_chic:
                                    continue
                                if (str(s_ant.get("ativo", "")).upper() == str(ativo).upper()
                                        and s_ant.get("direcao") in ("BUY", "SELL")
                                        and s_ant.get("direcao") != acao):
                                    chicote = True
                                    break
                        if chicote and probabilidade < PROBABILIDADE_MINIMA + MARGEM_ANTI_CHICOTE:
                            repetido = True     # trata como "não emitir"
                            self.log(
                                f"↔️ {acao} {ativo}: o cenário inverteu de lado nos últimos "
                                f"{JANELA_ANTI_CHICOTE_SEG // 60} min e a probabilidade "
                                f"({probabilidade:.0f}%) não chega aos "
                                f"{PROBABILIDADE_MINIMA + MARGEM_ANTI_CHICOTE:.0f}% que eu exijo "
                                "para virar a mão. Mercado indeciso não é oportunidade — "
                                "é a armadilha que faz tomar stop nas duas pontas.")

                        # JÁ ESTÁ POSICIONADO NESSE ATIVO? A decisão é de CÓDIGO, não do
                        # modelo — e o cenário contra a posição NÃO é engolido: vira
                        # alerta, que é a informação mais útil para quem está dentro.
                        if not repetido and acao in ("BUY", "SELL") and qualidade_ok:
                            _dec, _pos_ab, _motivo_pa = politica_com_posicao_aberta(acao, ativo)
                            if _dec == "ALERTA_CONTRA":
                                repetido = True      # não vira sugestão de entrada
                                self._alertar_cenario_contra_posicao(
                                    _pos_ab, acao, ativo, preco, probabilidade,
                                    confluencias, sinal.get("stop_loss"))
                            elif _dec == "BLOQUEIA":
                                repetido = True
                                self.log(f"⏸️ {acao} {ativo}: {_motivo_pa}")
                            elif _dec == "AUMENTO":
                                self.log(f"➕ {acao} {ativo}: {_motivo_pa} Vai como "
                                         "sugestão de AUMENTO — confira o risco somado "
                                         "antes de acatar.")

                        # FREIO DE SUGESTÕES: perda diária, stops seguidos e teto de
                        # operações. É a trava que impede o dia de virar sequência de
                        # stops. Roda depois dos outros filtros para o log mostrar o
                        # motivo real de o cenário não ter virado sugestão.
                        if not repetido and acao in ("BUY", "SELL") and qualidade_ok:
                            pode, motivo_freio = freio_de_sugestoes()
                            if not pode:
                                repetido = True
                                if motivo_freio != getattr(self, "_ultimo_motivo_freio", None):
                                    self._ultimo_motivo_freio = motivo_freio
                                    self.log(f"🛑 FREIO: {motivo_freio}")
                                    self._chat_feed(f"🛑 Segurei a sugestão: {motivo_freio}")
                            else:
                                self._ultimo_motivo_freio = None

                        # Loga a rejeição só quando havia um candidato REAL (BUY/SELL válido)
                        # com estado livre — pra você ver o filtro trabalhando.
                        if (sinal_ativo["estado"] == "ENCERRADA" and acao in ("BUY", "SELL")
                                and preco and _ep > 0 and _sl > 0 and not qualidade_ok and not repetido):
                            motivo = (f"R:R 1:{rr_sinal:.2f} (mínimo 1:{RR_MINIMO:.0f})"
                                      if rr_sinal < RR_MINIMO
                                      else f"probabilidade {probabilidade:.0f}% (mínimo {PROBABILIDADE_MINIMA:.0f}%)")
                            if rr_sinal < RR_MINIMO and rr_tp2 and rr_tp2 > rr_tp1:
                                motivo += f" · o 2º alvo pagaria 1:{rr_tp2:.2f}"
                            self._registrar_descarte_qualidade(
                                acao, ativo, motivo, rr_sinal, probabilidade,
                                RR_MINIMO, PROBABILIDADE_MINIMA)

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
                            # Saiu cenário: a contagem de descartes deste ativo+lado
                            # zera, para o próximo balanço falar do período novo.
                            getattr(self, "_descartes_qualidade", {}).pop(
                                f"{acao} {ativo}", None)
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
                                "confluencias": list(confluencias),  # p/ o aprendizado
                                "ts_criacao": time.time(),   # p/ o timeout de acatar (10 min)
                            }

                            # Dimensionamento de posição com base no Plano da Mesa
                            # (Margem, Risco%, Drawdown) e no valor por ponto do
                            # ativo identificado no gráfico, na CONTA SELECIONADA.
                            plano = plano_da_conta_ativa()
                            sizing = dimensionar_pelo_plano(
                                sinal_ativo["entry"], sinal_ativo["stop"], ativo, plano)

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
                                if sizing.get("motivo_limite"):
                                    linha_contratos += f"\n🔒 {sizing['motivo_limite']}"
                            else:
                                # O trader via "0 contratos" e três hipóteses. Agora vem
                                # o motivo REAL, calculado — nunca uma lista de talvez.
                                linha_contratos = (
                                    "\n⚠️ *0 contratos* — "
                                    + (sizing.get("motivo_limite")
                                       or "Margem/Risco% não configurados no Plano de Trading.")
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

                            # QUEM PAGOU O PISO FOI O 2º ALVO? Então a parcial no 1º
                            # alvo cobra um preço, e o trader tem de saber disso ANTES
                            # de entrar — senão ele realiza metade num alvo que não
                            # paga 1:2 e depois pergunta por que o resultado não fecha.
                            if alvo_do_piso == 2 and rr_tp1:
                                bloco_gestao += (
                                    f"\n• ⚠️ ATENÇÃO: quem paga o seu piso de "
                                    f"1:{RR_MINIMO:g} aqui é o Objetivo 2 "
                                    f"(1:{rr_tp2:.2f}). O Objetivo 1 paga só "
                                    f"1:{rr_tp1:.2f} — realizar metade nele derruba o "
                                    "R:R do trade inteiro. Se você quer o 1:2 cheio, "
                                    "leve tudo até o Objetivo 2.")

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
                            # A sugestão também entra na CONVERSA da aba 🐯 TIGER — você
                            # pode responder 'acatar' / 'dispensar' ali, por texto ou voz.
                            self._chat_feed(
                                f"📘 Nova sugestão: {acao} {ativo} — entrada "
                                f"{sinal_ativo['entry']}, stop {sinal_ativo['stop']}, alvo "
                                f"{sinal_ativo['tp1']}"
                                + (f", R:R {rr1}" if rr1 else "") +
                                f", probabilidade {probabilidade:.0f}%. Quer conversar sobre "
                                "o cenário? Ou diga 'acatar' / 'dispensar'.")
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
                        # Falha numa janela NÃO pode calar as outras: cada uma é
                        # um ativo, e um erro de captura no MES não pode impedir
                        # a análise do NQ no mesmo ciclo.
                        self.log(f"⚠️ Erro ao analisar '{nome_janela or 'tela cheia'}': {e}")
                        # CICLO PERDIDO PRECISA APARECER PARA ELE.
                        # Em 13/08 dois ciclos seguidos morreram em 503/504 e
                        # isso existiu só dentro do Registro. Quem esperava
                        # sugestão no celular concluiu que a ferramenta tinha
                        # parado — de novo. Silêncio nunca explica silêncio.
                        est["ciclos_perdidos"] = est.get("ciclos_perdidos", 0) + 1
                        if est["ciclos_perdidos"] == 2:
                            motivo = ("os modelos da Gemini estão sobrecarregados "
                                      "ou sem cota agora"
                                      if classificar_erro_modelo(e) in
                                      ("transitorio", "cota")
                                      else f"{str(e)[:120]}")
                            self._chat_feed(
                                f"⚠️ Perdi as 2 últimas análises de "
                                f"'{nome_janela or 'tela cheia'}': {motivo}. "
                                "A captura funciona; o que falhou foi a leitura. "
                                "Sigo tentando a cada ciclo e aviso quando "
                                "voltar — não estou parada, estou sem quem leia "
                                "o gráfico.")
                            try:
                                enviar_relatorio_whatsapp(
                                    f"⚠️ *Análises falhando — "
                                    f"{time.strftime('%d/%m/%Y %H:%M')}*\n"
                                    f"Perdi as 2 últimas leituras: {motivo}.\n"
                                    "O motor continua tentando. Nenhuma "
                                    "sugestão sai enquanto isso — prefiro te "
                                    "avisar a te deixar esperando.", None,
                                    self.log)
                            except Exception:
                                pass
                    else:
                        est["ciclos_perdidos"] = 0
                    finally:
                        est["sinal_ativo"] = sinal_ativo
                        est["hash_captura_anterior"] = hash_captura_anterior
                        est["capturas_congeladas"] = capturas_congeladas
                        est["preco_anterior_lido"] = preco_anterior_lido
                        est["ciclos_preco_igual"] = ciclos_preco_igual
                        est["ciclos_sem_grafico"] = ciclos_sem_grafico
                        est["ledger_text_memory"] = ledger_text_memory
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

    entrada = ctk.CTkEntry(janela, width=380, placeholder_text="Ex: SMC-XXXX-XXXX-XXXX",
                            justify="center")
    entrada.pack(pady=18)
    # No Mac o Cmd+V colava DUAS vezes: a chave virava
    # "SMC-DDPX-XZUG-PH8GSMC-DDPX-XZUG-PH8G" e o servidor recusava, com razao.
    ligar_colar_sem_duplicar(entrada)

    lbl_status = ctk.CTkLabel(janela, text="", text_color="gray")
    lbl_status.pack()

    def ativar():
        # Corrige a colagem dobrada e recorta no formato da chave, para um
        # espaco ou uma quebra de linha invisivel nao virar "chave invalida".
        chave = limpar_chave_colada(entrada.get(),
                                    r"[A-Z0-9]{3,6}(?:-[A-Z0-9]{2,8}){2,5}")
        if chave and chave != (entrada.get() or "").strip():
            entrada.delete(0, "end")
            entrada.insert(0, chave)          # ele VE o que vai ser enviado
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
