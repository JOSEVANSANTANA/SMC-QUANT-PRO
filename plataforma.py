# -*- coding: utf-8 -*-
"""
CAMADA DE PLATAFORMA — o único lugar do SMC Quant Pro que sabe em qual
sistema operacional ele está rodando.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Até a v2.13 o `main_app.py` chamava a API do Windows direto no meio da lógica
de trading: `win32gui.EnumWindows` para listar janelas, `PrintWindow` para
capturar o gráfico, `win32crypt` (DPAPI) para guardar a chave da Gemini,
`winsound` para o bipe do alerta. Isso amarrava o programa inteiro ao Windows —
não dava para rodar no Mac sem reescrever o miolo.

Agora existe UMA fronteira. O `main_app.py` pede "capture a janela do gráfico"
e é ESTE arquivo que sabe se isso significa `PrintWindow` (Windows) ou
`screencapture -l` (macOS). A lógica de SMC, o motor, o plano de trading e a
TIGER não mudam uma linha entre os dois sistemas.

REGRA DA CASA QUE VALE AQUI TAMBÉM
-----------------------------------
Nada aqui pode INVENTAR resultado. Se a captura falhar no Mac, a função devolve
None e quem chamou avisa o trader — jamais devolve uma imagem antiga, uma tela
preta ou um "deu certo" sem ter dado. Ausência de dado legível nunca é conclusão.

O QUE MUDA DE VERDADE ENTRE OS DOIS SISTEMAS
--------------------------------------------
    Recurso                  Windows                 macOS
    -----------------------  ----------------------  -------------------------
    Guardar a chave da API   DPAPI (win32crypt)      Chaveiro (security CLI)
    Listar janelas abertas   win32gui.EnumWindows    Quartz CGWindowList
    Capturar janela de fundo PrintWindow             screencapture -l <id>
    Recortar região da tela  ImageGrab(bbox)         screencapture -R
    Bipe do alerta           winsound.MessageBeep    afplay (som do sistema)
    Abrir a pasta de dados   os.startfile            open
    Pasta de dados           %APPDATA%               ~/Library/Application Support
    Esconder console do node CREATE_NO_WINDOW        (não precisa)

LIMITAÇÃO REAL DO macOS, DITA NA CARA
--------------------------------------
No macOS, ler o TÍTULO de uma janela de outro aplicativo e capturar o conteúdo
dela exigem a permissão **Gravação de Tela**. Sem ela o sistema devolve a lista
de janelas SEM os títulos (só o nome do aplicativo) e a captura sai preta. Isso
é do macOS, não do programa. O passo a passo de instalação cobre como conceder,
e `diagnostico()` diz em uma linha se a permissão está valendo.
"""
import base64
import os
import subprocess
import sys
import tempfile
import time

# --------------------------------------------------------------------
# QUAL SISTEMA
# --------------------------------------------------------------------
if sys.platform.startswith("win"):
    SISTEMA = "windows"
elif sys.platform == "darwin":
    SISTEMA = "macos"
else:
    SISTEMA = "linux"

E_WINDOWS = (SISTEMA == "windows")
E_MACOS = (SISTEMA == "macos")

NOME_SISTEMA = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}[SISTEMA]

# --------------------------------------------------------------------
# DEPENDÊNCIAS NATIVAS (importadas com guarda: faltando uma, o programa
# continua de pé e o recurso correspondente se explica em vez de estourar)
# --------------------------------------------------------------------
PYWIN32_DISPONIVEL = False
QUARTZ_DISPONIVEL = False

if E_WINDOWS:
    try:
        import ctypes
        import win32gui
        import win32crypt
        PYWIN32_DISPONIVEL = True
    except Exception:
        PYWIN32_DISPONIVEL = False
elif E_MACOS:
    try:
        import Quartz
        QUARTZ_DISPONIVEL = True
    except Exception:
        QUARTZ_DISPONIVEL = False

try:
    from PIL import Image, ImageGrab
    PIL_DISPONIVEL = True
except Exception:
    PIL_DISPONIVEL = False


def _sem_console():
    """Opções de subprocess que impedem uma janela preta de piscar na tela.
    Só o Windows precisa disso; no macOS o parâmetro nem existe."""
    if not E_WINDOWS:
        return {}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    except Exception:
        return {}


def opcoes_subprocess():
    """Use isto em TODO subprocess.Popen/run do app. No Windows esconde o
    console; no macOS devolve dicionário vazio (nada a esconder)."""
    return _sem_console()


def _rodar(args, timeout=10, entrada=None):
    """Executa um comando e devolve (ok, saída). Nunca levanta exceção — em
    troca, devolve ok=False, para quem chamou poder avisar o trader."""
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout,
                           input=entrada, **_sem_console())
        saida = (r.stdout or b"").decode("utf-8", "ignore").strip()
        return (r.returncode == 0), saida
    except Exception as e:
        return False, str(e)


# ====================================================================
# 1. PASTA DE DADOS
# ====================================================================
def pasta_dados():
    """Onde ficam config, histórico, lições e o último print.

    Windows: %APPDATA%\\SMC_Quant_Pro
    macOS:   ~/Library/Application Support/SMC_Quant_Pro
             (é o lugar canônico do sistema; não é pasta escondida improvisada)
    """
    if E_MACOS:
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    pasta = os.path.join(base, "SMC_Quant_Pro")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def abrir_pasta(caminho):
    """Abre a pasta no explorador de arquivos do sistema."""
    try:
        if E_WINDOWS:
            os.startfile(caminho)            # noqa: pylint - só existe no Windows
        elif E_MACOS:
            subprocess.Popen(["open", caminho])
        else:
            subprocess.Popen(["xdg-open", caminho])
        return True
    except Exception:
        return False


# ====================================================================
# 2. SEGREDO (a chave da API da Gemini)
# ====================================================================
# No Windows era DPAPI: amarra o segredo à conta do usuário, sem precisar
# guardar outra chave. O equivalente exato no macOS é o CHAVEIRO (Keychain),
# que amarra do mesmo jeito à conta do Mac. Ambos têm a mesma propriedade que
# interessa: copiar o arquivo de config para outra máquina NÃO leva a chave.
_KC_SERVICO = "SMC_Quant_Pro"
_KC_CONTA = "gemini_api_key"
_MARCA_CHAVEIRO = "keychain:"       # o config guarda só um ponteiro, não o segredo
_MARCA_CLARO = "texto:"             # último recurso, declarado como tal


def _keychain_gravar(segredo):
    ok, _ = _rodar(["security", "add-generic-password", "-U",
                    "-s", _KC_SERVICO, "-a", _KC_CONTA, "-w", segredo])
    return ok


def _keychain_ler():
    ok, saida = _rodar(["security", "find-generic-password",
                        "-s", _KC_SERVICO, "-a", _KC_CONTA, "-w"])
    return saida if ok else ""


def _keychain_apagar():
    _rodar(["security", "delete-generic-password",
            "-s", _KC_SERVICO, "-a", _KC_CONTA])


def proteger_segredo(texto):
    """Devolve o que deve ser GRAVADO no config — nunca o segredo em claro,
    quando houver cofre disponível."""
    if not texto:
        return texto
    if E_WINDOWS and PYWIN32_DISPONIVEL:
        try:
            blob = win32crypt.CryptProtectData(
                texto.encode("utf-8"), "SMC_Quant_Pro_APIKey", None, None, None, 0)
            return base64.b64encode(blob).decode("utf-8")
        except Exception:
            pass
    if E_MACOS:
        # Apaga antes de gravar: sem isso, trocar de chave deixava a antiga
        # no chaveiro e o `find` podia devolver a errada.
        _keychain_apagar()
        if _keychain_gravar(texto):
            return _MARCA_CHAVEIRO + _KC_CONTA
    # Sem cofre: guarda codificado e DECLARADO como tal. Não é criptografia e
    # o programa não vai fingir que é — quem lê o config vê a marca "texto:".
    return _MARCA_CLARO + base64.b64encode(texto.encode("utf-8")).decode("utf-8")


def revelar_segredo(guardado):
    """Inverso de proteger_segredo(). Devolve "" se não der para recuperar —
    nunca um palpite."""
    if not guardado:
        return ""
    if guardado.startswith(_MARCA_CHAVEIRO):
        return _keychain_ler() if E_MACOS else ""
    if guardado.startswith(_MARCA_CLARO):
        try:
            return base64.b64decode(guardado[len(_MARCA_CLARO):]).decode("utf-8")
        except Exception:
            return ""
    if E_WINDOWS and PYWIN32_DISPONIVEL:
        try:
            blob = base64.b64decode(guardado)
            _, dados = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
            return dados.decode("utf-8")
        except Exception:
            return ""
    # Config antigo, do tempo em que a chave ia em claro. Aceita e segue.
    return guardado


def onde_fica_o_segredo():
    """Frase curta para a interface dizer ao trader onde a chave está guardada."""
    if E_WINDOWS and PYWIN32_DISPONIVEL:
        return "criptografada pelo Windows (DPAPI), presa à sua conta"
    if E_MACOS:
        return "no Chaveiro do macOS, preso à sua conta do Mac"
    return "codificada no arquivo de configuração (sem cofre do sistema aqui)"


# ====================================================================
# 3. JANELAS — listar, encontrar, capturar
# ====================================================================
# O "handle" é opaco de propósito: no Windows é um HWND (int), no macOS é o
# número da janela do Quartz (int). Quem chama nunca precisa saber a diferença.

def _janelas_macos(so_na_tela=True):
    """Lista de dicionários {id, titulo, app, bounds} pelo Quartz.

    ATENÇÃO À PERMISSÃO: sem "Gravação de Tela" liberada, o macOS devolve a
    lista COM os aplicativos mas SEM os títulos das janelas. Por isso o rótulo
    montado aqui sempre começa pelo nome do app — assim o trader consegue
    escolher a janela mesmo antes de conceder a permissão.
    """
    if not QUARTZ_DISPONIVEL:
        return []
    try:
        opcoes = (Quartz.kCGWindowListOptionOnScreenOnly if so_na_tela
                  else Quartz.kCGWindowListOptionAll)
        bruto = Quartz.CGWindowListCopyWindowInfo(
            opcoes | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID) or []
    except Exception:
        return []

    janelas = []
    for w in bruto:
        try:
            # Camada 0 = janela normal. Acima disso é menu, dock, overlay do
            # sistema — nada que contenha um gráfico de trading.
            if int(w.get("kCGWindowLayer", 0)) != 0:
                continue
            b = w.get("kCGWindowBounds") or {}
            larg, alt = int(b.get("Width", 0)), int(b.get("Height", 0))
            # Descarta só tranqueira de verdade. O limiar era 200x150 e cortava
            # janela legítima: quem opera com o gráfico numa metade da tela, ou
            # com a corretora numa janela estreita, ficava sem a janela na
            # lista e sem entender por quê.
            if larg < 120 or alt < 80:
                continue
            app = str(w.get("kCGWindowOwnerName") or "").strip()
            nome = str(w.get("kCGWindowName") or "").strip()
            if not app:
                continue
            janelas.append({
                "id": int(w.get("kCGWindowNumber", 0)),
                "app": app,
                "nome": nome,
                "titulo": f"{app} — {nome}" if nome else app,
                "x": int(b.get("X", 0)), "y": int(b.get("Y", 0)),
                "largura": larg, "altura": alt,
            })
        except Exception:
            continue

    # RÓTULO ÚNICO POR JANELA — este era o defeito que sumia com a janela da
    # corretora. Os rótulos iam para um CONJUNTO lá em listar_janelas(), e sem
    # a permissão de Gravação de Tela o macOS devolve TODAS as janelas do
    # Chrome com o nome VAZIO. Resultado: cinco janelas viravam cinco vezes
    # "Google Chrome", o conjunto colapsava tudo em UMA, e a do Tradovate
    # simplesmente não existia para escolher.
    #
    # Agora, quando o rótulo se repete, ele ganha a ORDEM e o TAMANHO — que é
    # o que dá para distinguir sem o título: "Google Chrome — janela 2
    # (1512x982)". Não é bonito, mas é honesto e dá para escolher.
    contagem = {}
    for j in janelas:
        contagem[j["titulo"]] = contagem.get(j["titulo"], 0) + 1
    vistos = {}
    for j in janelas:
        base_rot = j["titulo"]
        if contagem[base_rot] > 1:
            vistos[base_rot] = vistos.get(base_rot, 0) + 1
            j["titulo"] = (f"{base_rot} — janela {vistos[base_rot]} "
                           f"({j['largura']}x{j['altura']})")
    return janelas


def listar_janelas():
    """Títulos das janelas visíveis, para o trader escolher no dropdown."""
    if E_WINDOWS:
        if not PYWIN32_DISPONIVEL:
            return []
        titulos = []

        def callback(hwnd, _extra):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if t.strip():
                    titulos.append(t)
            return True

        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            pass
        return sorted(set(titulos))

    if E_MACOS:
        # Sem `set`: cada janela é uma linha. Ordena pelo nome do aplicativo e
        # depois pela posição na tela, para a lista sair estável entre uma
        # atualização e outra.
        js = sorted(_janelas_macos(),
                    key=lambda j: (j["app"].lower(), j["y"], j["x"]))
        rotulos = [j["titulo"] for j in js]
        # A LISTA MENTE SE A PERMISSÃO FALTA — e mente calada. Sem Gravação de
        # Tela os títulos vêm vazios e o trader não descobre o motivo sozinho.
        # Então o próprio seletor diz.
        if rotulos and permissao_de_tela_ok() is False:
            rotulos.insert(0, "(⚠️ SEM permissão de Gravação de Tela — os "
                              "títulos das janelas vêm vazios; veja o log)")
        return rotulos

    return []


def encontrar_janela(nome_parcial):
    """Handle da janela pelo título. Prefere o título EXATO (o dropdown guarda
    o título completo); se não houver, cai para correspondência parcial.
    Devolve None se não encontrar — e None aqui significa 'não achei', nunca
    'pode seguir assim mesmo'."""
    if not nome_parcial:
        return None
    alvo = str(nome_parcial).strip().lower()

    if E_WINDOWS:
        if not PYWIN32_DISPONIVEL:
            return None
        achado = {"exato": None, "parcial": None}

        def callback(hwnd, _extra):
            if win32gui.IsWindowVisible(hwnd):
                titulo = win32gui.GetWindowText(hwnd)
                if titulo:
                    t = titulo.strip().lower()
                    if t == alvo and achado["exato"] is None:
                        achado["exato"] = hwnd
                    elif alvo in t and achado["parcial"] is None:
                        achado["parcial"] = hwnd
            return True

        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            pass
        return achado["exato"] or achado["parcial"]

    if E_MACOS:
        # O item de aviso não é janela: escolher ele não pode virar captura.
        if alvo.startswith("(⚠"):
            return None
        janelas = sorted(_janelas_macos(),
                         key=lambda j: (j["app"].lower(), j["y"], j["x"]))
        for j in janelas:                       # 1) rótulo completo, exato
            if j["titulo"].strip().lower() == alvo:
                return j["id"]
        for j in janelas:                       # 2) trecho do rótulo
            if alvo in j["titulo"].strip().lower():
                return j["id"]
        # 3) O rótulo pode ter sido salvo com a numeração de OUTRO momento
        #    ("Google Chrome — janela 2 (1512x982)"). Reaproveita o que dele é
        #    estável: o aplicativo e o TAMANHO da janela.
        import re as _re
        m = _re.search(r"^(.*?)\s+—\s+janela\s+\d+\s+\((\d+)x(\d+)\)$",
                       str(nome_parcial).strip(), _re.I)
        if m:
            app_alvo = m.group(1).strip().lower()
            lg, at = int(m.group(2)), int(m.group(3))
            for j in janelas:
                if (j["app"].strip().lower() == app_alvo
                        and abs(j["largura"] - lg) <= 4
                        and abs(j["altura"] - at) <= 4):
                    return j["id"]
            for j in janelas:                   # mesmo app, tamanho mudou
                if j["app"].strip().lower() == app_alvo:
                    return j["id"]
        for j in janelas:                       # 4) só o nome do aplicativo
            if alvo in j["app"].strip().lower():
                return j["id"]
        return None

    return None


def janela_existe(handle):
    if handle is None:
        return False
    if E_WINDOWS:
        try:
            return bool(win32gui.IsWindow(handle))
        except Exception:
            return False
    if E_MACOS:
        return any(j["id"] == handle for j in _janelas_macos(so_na_tela=False))
    return False


def preparar_janela(handle, restaurar_se_minimizada=True):
    """Deixa a janela em condição de ser capturada COM CONTEÚDO ATUAL, sem
    roubar o foco do trader.

    Windows: se estiver minimizada, restaura sem ativar (SW_SHOWNOACTIVATE) e
    empurra para o fundo da pilha; depois pede repintura.

    macOS: o sistema mantém o buffer da janela mesmo coberta, então janela
    visível não precisa de nada. Minimizada (no Dock) é outra história — o
    conteúdo deixa de existir. Aqui NÃO desminimizamos: fazer isso no Mac
    obriga a ativar o aplicativo, e ativar significa pular na frente do trader
    no meio do pregão. Devolvemos False e o ciclo é pulado com aviso — melhor
    perder um ciclo do que tomar a tela de quem está operando.
    """
    if handle is None:
        return False

    if E_WINDOWS:
        if not PYWIN32_DISPONIVEL:
            return True
        try:
            if win32gui.IsIconic(handle):
                if not restaurar_se_minimizada:
                    return False
                win32gui.ShowWindow(handle, 4)      # SW_SHOWNOACTIVATE
                time.sleep(0.4)
                try:
                    # HWND_BOTTOM=1; NOSIZE|NOMOVE|NOACTIVATE = 0x13
                    ctypes.windll.user32.SetWindowPos(handle, 1, 0, 0, 0, 0, 0x13)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            # RDW_INVALIDATE|RDW_UPDATENOW|RDW_ALLCHILDREN
            ctypes.windll.user32.RedrawWindow(handle, None, None, 0x1 | 0x100 | 0x80)
            time.sleep(0.15)
        except Exception:
            pass
        return True

    if E_MACOS:
        # Está na lista de janelas NA TELA? Se sim, dá para capturar.
        if any(j["id"] == handle for j in _janelas_macos(so_na_tela=True)):
            return True
        # Existe, mas fora da tela = minimizada no Dock.
        return False

    return True


def _png_para_pil(caminho):
    if not PIL_DISPONIVEL:
        return None
    try:
        with Image.open(caminho) as im:
            return im.convert("RGB").copy()      # copy(): solta o arquivo
    except Exception:
        return None


def capturar_janela(handle):
    """Conteúdo da janela, SEM trazê-la para frente. Imagem PIL ou None.

    Windows: PrintWindow com PW_RENDERFULLCONTENT (necessário para conteúdo
    desenhado pela GPU, que é o caso de uma aba do Chrome).

    macOS: `screencapture -l <id>`, que lê o buffer da janela pelo Quartz.
    Funciona com a janela coberta por outras — que é exatamente o que o motor
    precisa para não interromper o trader a cada 5 minutos.
    """
    if handle is None:
        return None

    if E_WINDOWS:
        if not (PYWIN32_DISPONIVEL and PIL_DISPONIVEL):
            return None
        try:
            import win32ui
            left, top, right, bottom = win32gui.GetWindowRect(handle)
            largura, altura = right - left, bottom - top
            if largura <= 0 or altura <= 0:
                return None
            hwndDC = win32gui.GetWindowDC(handle)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfcDC, largura, altura)
            saveDC.SelectObject(bitmap)
            PW_RENDERFULLCONTENT = 0x00000002
            resultado = ctypes.windll.user32.PrintWindow(
                handle, saveDC.GetSafeHdc(), PW_RENDERFULLCONTENT)
            info = bitmap.GetInfo()
            bits = bitmap.GetBitmapBits(True)
            imagem = Image.frombuffer(
                "RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)
            win32gui.DeleteObject(bitmap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(handle, hwndDC)
            return imagem if resultado == 1 else None
        except Exception:
            return None

    if E_MACOS:
        destino = os.path.join(tempfile.gettempdir(),
                               f"smc_captura_{int(time.time()*1000)}.png")
        try:
            # -x  sem o som de câmera (o trader não quer "click" a cada ciclo)
            # -o  sem a sombra da janela (borda inútil que só ocupa pixel)
            # -l  captura ESTA janela, mesmo atrás de outras
            ok, _ = _rodar(["screencapture", "-x", "-o", "-l", str(handle), destino],
                           timeout=20)
            if not ok or not os.path.exists(destino):
                return None
            return _png_para_pil(destino)
        finally:
            try:
                os.remove(destino)
            except Exception:
                pass

    return None


def capturar_regiao_da_tela(handle):
    """Plano C: recorta a região da TELA onde a janela está.
    Devolve (imagem, houve_sobreposicao). A limitação é conhecida e declarada:
    se outra janela estiver por cima, o recorte pega a de cima — por isso só é
    usado quando a captura direta devolve quadro velho.
    """
    if handle is None or not PIL_DISPONIVEL:
        return None, False

    if E_WINDOWS:
        if not PYWIN32_DISPONIVEL:
            return None, False
        try:
            left, top, right, bottom = win32gui.GetWindowRect(handle)
            if right - left <= 0 or bottom - top <= 0:
                return None, False
            centro = ((left + right) // 2, (top + bottom) // 2)
            sobreposto = True
            try:
                hwnd_ponto = win32gui.WindowFromPoint(centro)
                raiz = ctypes.windll.user32.GetAncestor(hwnd_ponto, 2)   # GA_ROOT
                sobreposto = (raiz != handle)
            except Exception:
                pass
            return ImageGrab.grab(bbox=(left, top, right, bottom)), sobreposto
        except Exception:
            return None, False

    if E_MACOS:
        alvo = next((j for j in _janelas_macos() if j["id"] == handle), None)
        if not alvo:
            return None, False
        # Sobreposição no macOS: a lista do Quartz vem de frente para trás.
        # Se alguma janela ANTES da nossa cruza a mesma área, há algo por cima.
        sobreposto = False
        for j in _janelas_macos():
            if j["id"] == handle:
                break
            if not (j["x"] + j["largura"] <= alvo["x"] or
                    alvo["x"] + alvo["largura"] <= j["x"] or
                    j["y"] + j["altura"] <= alvo["y"] or
                    alvo["y"] + alvo["altura"] <= j["y"]):
                sobreposto = True
                break
        destino = os.path.join(tempfile.gettempdir(),
                               f"smc_regiao_{int(time.time()*1000)}.png")
        try:
            regiao = f'{alvo["x"]},{alvo["y"]},{alvo["largura"]},{alvo["altura"]}'
            ok, _ = _rodar(["screencapture", "-x", "-R", regiao, destino], timeout=20)
            if not ok or not os.path.exists(destino):
                return None, sobreposto
            return _png_para_pil(destino), sobreposto
        finally:
            try:
                os.remove(destino)
            except Exception:
                pass

    return None, False


def capturar_tela_inteira():
    """A tela toda. Usado quando não há janela escolhida."""
    if not PIL_DISPONIVEL:
        return None
    if E_MACOS:
        destino = os.path.join(tempfile.gettempdir(),
                               f"smc_tela_{int(time.time()*1000)}.png")
        try:
            ok, _ = _rodar(["screencapture", "-x", destino], timeout=20)
            if ok and os.path.exists(destino):
                return _png_para_pil(destino)
            return None
        finally:
            try:
                os.remove(destino)
            except Exception:
                pass
    try:
        return ImageGrab.grab()
    except Exception:
        return None


# ====================================================================
# 4. SOM DO ALERTA
# ====================================================================
_SONS_MACOS = ("/System/Library/Sounds/Ping.aiff",
               "/System/Library/Sounds/Submarine.aiff",
               "/System/Library/Sounds/Glass.aiff")


def bipe():
    """Bipe curto do alerta. Nunca derruba nada se o som falhar."""
    try:
        if E_WINDOWS:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return True
        if E_MACOS:
            som = next((s for s in _SONS_MACOS if os.path.exists(s)), None)
            if som:
                subprocess.Popen(["afplay", som])
                return True
            subprocess.Popen(["osascript", "-e", "beep"])
            return True
    except Exception:
        pass
    return False


# ====================================================================
# 4b. VOZ DA TIGER
# ====================================================================
# NO WINDOWS o pyttsx3 usa SAPI5 e funciona bem em thread — fica como está.
#
# NO macOS ele usa NSSpeechSynthesizer, que exige o run loop do Cocoa rodando
# na thread principal. A TIGER fala a partir de uma thread de trabalho, então
# ali o pyttsx3 ou trava ou não emite som. Além disso, a busca de voz do app
# procurava "brazil"/"portugu" NO NOME da voz — e no Mac as vozes de português
# se chamam "Luciana", "Joana", "Catarina": nenhuma casaria, e a TIGER sairia
# falando inglês.
#
# Por isso, no macOS a fala usa o comando `say` do próprio sistema: é nativo,
# aceita voz e velocidade, e — o que mais importa aqui — é um processo que dá
# para MATAR na hora quando o trader manda calar a boca no meio do pregão.
VOZ_NATIVA = E_MACOS

_VOZES_PT_MACOS = ("Luciana", "Joana", "Catarina", "Raquel", "Felipe")


def voz_portugues_macos():
    """Nome da melhor voz de português instalada, ou None. Só fatos: lê a
    lista real do sistema, não presume que 'Luciana' está instalada."""
    if not E_MACOS:
        return None
    ok, saida = _rodar(["say", "-v", "?"], timeout=8)
    if not ok or not saida:
        return None
    disponiveis = []
    for linha in saida.splitlines():
        # Formato: "Luciana            pt_BR    # Olá, o meu nome é Luciana."
        partes = linha.split()
        if len(partes) >= 2:
            disponiveis.append((partes[0], " ".join(partes[:2])))
    # 1) preferidas, na ordem
    for preferida in _VOZES_PT_MACOS:
        for nome, _ in disponiveis:
            if nome.lower() == preferida.lower():
                return nome
    # 2) qualquer uma marcada como pt_BR, depois qualquer pt_
    for marca in ("pt_BR", "pt_"):
        for nome, linha in disponiveis:
            if marca in linha:
                return nome
    return None


def falar_nativo(texto, palavras_por_minuto=165):
    """Fala pelo sistema e devolve o processo (para poder ser interrompido).
    None se este sistema não usa fala nativa ou se não deu para iniciar."""
    if not E_MACOS or not texto:
        return None
    args = ["say", "-r", str(int(max(90, min(palavras_por_minuto, 320))))]
    voz = voz_portugues_macos()
    if voz:
        args += ["-v", voz]
    try:
        return subprocess.Popen(args + ["--", str(texto)], **_sem_console())
    except Exception:
        return None


# ====================================================================
# 5. CHROME (automação da corretora por CDP)
# ====================================================================
def caminhos_chrome():
    """Onde procurar o Chrome, na ordem. O Mac M2 roda o Chrome universal
    instalado em /Applications; o Chromium e o Edge servem de reserva porque
    falam o mesmo protocolo CDP."""
    if E_WINDOWS:
        return [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         r"Google\Chrome\Application\chrome.exe"),
        ]
    if E_MACOS:
        casa = os.path.expanduser("~")
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.join(casa, "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    return ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]


def nome_do_navegador():
    return "Google Chrome" if not E_WINDOWS else "chrome.exe"


# ====================================================================
# 5b. NODE / NPM — o PATH do Finder não é o PATH do terminal
# ====================================================================
# ARMADILHA CLÁSSICA DO macOS: um aplicativo aberto pelo FINDER (duplo clique)
# NÃO herda o PATH do seu shell. Ele recebe um PATH mínimo do launchd, sem
# /opt/homebrew/bin e sem /usr/local/bin. Resultado: o trader instala o Node
# pelo Homebrew, digita `node -v` no terminal e funciona — mas o programa jura
# que o Node não existe e o motor não sobe. No terminal funciona, no ícone não.
#
# Aqui o PATH é completado com os lugares onde o Node realmente mora no Mac,
# ANTES de qualquer tentativa de subir o motor.
_PASTAS_BIN_MACOS = (
    "/opt/homebrew/bin",        # Homebrew no Apple Silicon (M1/M2/M3) - o padrão do M2
    "/usr/local/bin",           # Homebrew no Intel e instalador oficial do nodejs.org
    "/opt/local/bin",           # MacPorts
    os.path.expanduser("~/.nvm/versions/node"),   # nvm (tratado abaixo)
    os.path.expanduser("~/.volta/bin"),
    os.path.expanduser("~/n/bin"),
)


def _pastas_nvm():
    """O nvm guarda cada versão numa pasta própria; devolve os bin/ existentes,
    da versão mais recente para a mais antiga."""
    raiz = os.path.expanduser("~/.nvm/versions/node")
    if not os.path.isdir(raiz):
        return []
    try:
        versoes = sorted(os.listdir(raiz), reverse=True)
    except Exception:
        return []
    return [os.path.join(raiz, v, "bin") for v in versoes
            if os.path.isdir(os.path.join(raiz, v, "bin"))]


def garantir_path_do_sistema():
    """Completa o PATH do processo com as pastas de binários do Mac.
    Idempotente: chamar várias vezes não duplica nada. Devolve o que foi
    acrescentado, para o log poder dizer exatamente o que mudou."""
    if not E_MACOS:
        return []
    atual = os.environ.get("PATH", "").split(os.pathsep)
    acrescentados = []
    candidatas = [p for p in _PASTAS_BIN_MACOS if not p.endswith("versions/node")]
    candidatas += _pastas_nvm()
    for pasta in candidatas:
        if pasta and os.path.isdir(pasta) and pasta not in atual:
            atual.insert(0, pasta)
            acrescentados.append(pasta)
    if acrescentados:
        os.environ["PATH"] = os.pathsep.join(atual)
    return acrescentados


def caminho_node():
    """Caminho completo do node, ou None. Procura no PATH já completado e,
    se não achar, nos lugares conhecidos — porque 'não achei no PATH' não é a
    mesma coisa que 'não está instalado'."""
    garantir_path_do_sistema()
    import shutil
    achado = shutil.which("node")
    if achado:
        return achado
    if E_MACOS:
        for pasta in list(_PASTAS_BIN_MACOS) + _pastas_nvm():
            alvo = os.path.join(pasta, "node")
            if os.path.isfile(alvo) and os.access(alvo, os.X_OK):
                return alvo
    return None


def comando_npm():
    """No Windows o npm é um .cmd e precisa de shell; no macOS é executável."""
    if E_WINDOWS:
        return "npm.cmd"
    garantir_path_do_sistema()
    import shutil
    return shutil.which("npm") or "npm"


def como_instalar_node():
    """Instrução certa para ESTE sistema — nada de mandar o usuário do Mac
    baixar um .exe."""
    if E_MACOS:
        return ("Instale o Node.js no Mac com UM destes:\n"
                "  • Homebrew (recomendado):  brew install node\n"
                "  • Ou baixe o instalador .pkg para Apple Silicon (ARM64) "
                "em https://nodejs.org\n"
                "Depois FECHE e ABRA o SMC Quant Pro de novo.")
    return ("Instale o Node.js em https://nodejs.org (versão LTS) e reabra o "
            "SMC Quant Pro.")


def como_matar_processo_travado(porta=3939):
    """Texto de socorro quando a porta do motor está ocupada — com o comando
    REAL de cada sistema."""
    if E_MACOS:
        return (f"Já existe um processo segurando a porta {porta}. No Terminal:\n"
                f"    lsof -ti :{porta} | xargs kill -9\n"
                "Depois tente LIGAR MOTOR de novo.")
    return (f"Já existe um 'node.exe' órfão segurando a porta {porta}. Abra o "
            "Gerenciador de Tarefas, finalize todo processo 'node.exe' e tente "
            "LIGAR MOTOR de novo.")


def nome_do_executavel():
    """Como o programa se chama no disco, para as mensagens de erro."""
    return "SMC_Quant_Pro.exe" if E_WINDOWS else "SMC Quant Pro.app"


# ====================================================================
# 6. DIAGNÓSTICO — para o trader saber o que está valendo na máquina dele
# ====================================================================
def permissao_de_tela_ok():
    """No macOS, responde se a permissão de Gravação de Tela está concedida.

    COMO DÁ PARA SABER SEM CHUTAR: sem a permissão, o macOS entrega a lista de
    janelas sem o campo de título. Se existe pelo menos uma janela de outro
    aplicativo COM título legível, a permissão está valendo. Devolve None
    quando a pergunta não se aplica (Windows) — None é "não se aplica", não é
    "não".
    """
    if not E_MACOS:
        return None
    if not QUARTZ_DISPONIVEL:
        return False
    meu = os.path.basename(sys.executable or "")
    for j in _janelas_macos():
        if j["nome"] and meu.lower() not in j["app"].lower():
            return True
    return False


def diagnostico():
    """Linhas curtas sobre o estado da plataforma. Só fatos verificados."""
    linhas = [f"Sistema: {NOME_SISTEMA} ({sys.platform})",
              f"Python: {sys.version.split()[0]}",
              f"Pasta de dados: {pasta_dados()}",
              f"Chave da API: {onde_fica_o_segredo()}"]
    if E_WINDOWS:
        linhas.append(f"pywin32: {'ok' if PYWIN32_DISPONIVEL else 'AUSENTE — captura de janela indisponível'}")
    if E_MACOS:
        linhas.append(f"Quartz (pyobjc): {'ok' if QUARTZ_DISPONIVEL else 'AUSENTE — instale pyobjc-framework-Quartz'}")
        perm = permissao_de_tela_ok()
        linhas.append("Gravação de Tela: " + (
            "concedida" if perm else
            "NÃO concedida — os títulos das janelas vêm vazios e a captura sai preta"))
        ok_sc, _ = _rodar(["which", "screencapture"], timeout=5)
        linhas.append(f"screencapture: {'ok' if ok_sc else 'AUSENTE (inesperado no macOS)'}")
    janelas = listar_janelas()
    linhas.append(f"Janelas visíveis encontradas: {len(janelas)}")
    return "\n".join(linhas)


if __name__ == "__main__":
    print(diagnostico())
    print("\nJanelas:")
    for t in listar_janelas()[:20]:
        print("  -", t)
