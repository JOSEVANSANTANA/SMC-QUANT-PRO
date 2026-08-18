"""O que o programa DIZ quando roda no Mac.

Duas coisas quebraram aqui, e as duas custaram um pregão:

1. `No module named 'numpy'` matando o microfone — DUAS vezes, por dois
   motivos diferentes:
     (a) o numpy não estava em requirements-mac.txt, e o app respondia
         "rode: pip install sounddevice", que era o que o trader já tinha feito;
     (b) mesmo com o pacote instalável, a dependência não precisava existir:
         o `sd.InputStream` exige numpy só para devolver as amostras como
         array — e este programa sempre leu o stream como bytes crus. O
         `RawInputStream` faz o mesmo sem numpy. Ver TestMicrofoneSemNumpy.
2. Mensagens mandando um usuário de macOS abrir telas do Windows.
"""

import os
import re
import unittest

from harness import RAIZ, carregar, fonte_do_arquivo, pular_se_faltar


class _Plataforma:
    def __init__(self, macos):
        self.E_MACOS = macos
        self.E_WINDOWS = not macos


def _ns(macos=True, sr_ok=True, sd_ok=True, erro=""):
    return carregar(
        ["texto_falta_voz"],
        stubs={"plataforma": _Plataforma(macos), "VOZ_SR": sr_ok,
               "VOZ_SD": sd_ok, "VOZ_SD_ERRO": erro})


class TestRequirementsMac(unittest.TestCase):

    def setUp(self):
        # No pacote do outro sistema este arquivo não existe — e não
        # existir ali é o certo. Falhar por isso assustaria o cliente
        # com um vermelho que não é defeito nenhum.
        pular_se_faltar("requirements-mac.txt")
    def test_numpy_esta_na_lista(self):
        """O sounddevice IMPORTA numpy. Sem esta linha, `pip install -r` termina
        com sucesso e o microfone morre no primeiro uso."""
        with open(os.path.join(RAIZ, "requirements-mac.txt"), encoding="utf-8") as f:
            texto = f.read()
        self.assertRegex(texto, r"(?mi)^numpy\b")

    def test_dependencias_de_janela_do_mac_continuam_la(self):
        with open(os.path.join(RAIZ, "requirements-mac.txt"), encoding="utf-8") as f:
            texto = f.read()
        for pacote in ("pyobjc-framework-Quartz", "pyobjc-framework-Cocoa",
                       "customtkinter", "Pillow", "google-genai"):
            self.assertIn(pacote, texto, pacote)


class TestMensagemDeMicrofone(unittest.TestCase):
    def test_diz_a_causa_real_quando_falta_numpy(self):
        ns = _ns(sd_ok=False, erro="No module named 'numpy'")
        msg = ns["texto_falta_voz"]()
        self.assertIn("numpy", msg)
        self.assertIn("No module named", msg)   # o erro exato, não uma versão minha

    def test_manda_instalar_numpy_junto(self):
        ns = _ns(sd_ok=False, erro="No module named 'numpy'")
        msg = ns["texto_falta_voz"]()
        instalar = re.search(r"pip install (.+?)\s\s", msg)
        self.assertIsNotNone(instalar, msg)
        self.assertIn("numpy", instalar.group(1))
        self.assertIn("sounddevice", instalar.group(1))

    def test_comando_do_mac_e_python3(self):
        ns = _ns(macos=True, sd_ok=False, erro="No module named 'numpy'")
        self.assertIn("python3 -m pip install", ns["texto_falta_voz"]())

    def test_comando_do_windows_e_python(self):
        ns = _ns(macos=False, sd_ok=False, erro="No module named 'numpy'")
        msg = ns["texto_falta_voz"]()
        self.assertIn("python -m pip install", msg)
        self.assertNotIn("python3", msg)

    def test_falta_so_o_speechrecognition(self):
        ns = _ns(sr_ok=False, sd_ok=True)
        msg = ns["texto_falta_voz"]()
        self.assertIn("SpeechRecognition", msg)
        self.assertNotIn("sounddevice", msg)

    def test_nada_faltando_nao_inventa_erro(self):
        ns = _ns(sr_ok=True, sd_ok=True)
        self.assertEqual(ns["texto_falta_voz"](), "microfone indisponível")


class TestNaoFalarDeWindowsNoMac(unittest.TestCase):
    def test_nenhuma_mensagem_de_microfone_fixa_o_windows(self):
        """Estas frases iam para a tela do trader. Num Mac, 'Configurações →
        Sistema → Som' do Windows é uma instrução para uma tela que não existe.
        As duas agora saem de ONDE_PERMITIR_MIC / ONDE_TROCAR_MIC, que olham o
        sistema em que o programa está rodando."""
        fonte = fonte_do_arquivo()
        # Estas duas sumiram do arquivo inteiro.
        for frase in ("permissões do Windows", "padrão do Windows"):
            self.assertNotIn(frase, fonte, frase)
        # A frase do WINDOWS é "Configurações → Sistema → Som". A do macOS é
        # "Ajustes do Sistema → Som → Entrada" — palavras diferentes de
        # propósito, porque são telas diferentes. O que não pode é a versão do
        # Windows aparecer solta; a do Mac é livre.
        for n, linha in enumerate(fonte.splitlines(), 1):
            if "Configurações → Sistema → Som" not in linha:
                continue
            self.assertTrue(
                linha.lstrip().startswith("#") or "(Windows)" in linha
                or "E_MACOS" in linha,
                f"linha {n} manda o trader para uma tela do Windows sem "
                f"checar o sistema: {linha.strip()}")

    def test_as_constantes_de_ajuda_existem(self):
        fonte = fonte_do_arquivo()
        self.assertIn("ONDE_PERMITIR_MIC", fonte)
        self.assertIn("ONDE_TROCAR_MIC", fonte)



class TestMicrofoneSemNumpy(unittest.TestCase):
    """11/08, 16:00 — a contradição que apontou o defeito exato:

        (🐯 modo OLÁ TIGER LIGADO — escutando pelo microfone
         "MacBook Air Microphone".)
        (🐯 não consegui abrir o microfone: No module named 'numpy'.)

    Ela LEU o nome do dispositivo e falhou logo depois. Ou seja: o sounddevice
    importou e o `query_devices` funcionou — não faltava o sounddevice. O numpy
    era exigido num ponto só: `sd.InputStream` devolve as amostras como array
    do numpy.

    Só que este programa nunca usou esse array. Todo lugar que lê o stream faz
    `bytes(bloco)` na hora. O `RawInputStream` entrega os mesmos bytes e não
    importa numpy — a dependência era paga e não era usada.
    """

    def test_o_stream_padrao_e_o_raw(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def abrir_stream_microfone")
        corpo = fonte[i:i + 2200]
        # O Raw vem PRIMEIRO; o InputStream clássico só como segunda tentativa.
        self.assertLess(corpo.index("RawInputStream"), corpo.index("_sd.InputStream"))

    def test_ninguem_mais_abre_InputStream_direto(self):
        """Se um caminho novo voltar a chamar `_sd.InputStream(` na mão, o
        numpy volta a ser obrigatório sem ninguém perceber."""
        fonte = fonte_do_arquivo()
        chamadas = [n for n, l in enumerate(fonte.splitlines(), 1)
                    if "_sd.InputStream(" in l]
        self.assertEqual(
            len(chamadas), 1,
            f"há {len(chamadas)} chamadas a _sd.InputStream (linhas {chamadas}); "
            "só a de dentro de abrir_stream_microfone pode existir")
        # E a única que sobra tem de estar DENTRO do fallback.
        i = fonte.index("def abrir_stream_microfone")
        fim = fonte.index("\ndef ", i + 10)
        linha_inicio = fonte[:i].count("\n") + 1
        linha_fim = fonte[:fim].count("\n") + 1
        self.assertTrue(linha_inicio <= chamadas[0] <= linha_fim)

    def test_o_codigo_le_o_stream_como_bytes(self):
        """A premissa do RawInputStream: nada aqui usa recurso de numpy. Se
        alguém passar a indexar o bloco como array, isto quebra em silêncio."""
        fonte = fonte_do_arquivo()
        for linha in fonte.splitlines():
            if "stream.read(" in linha:
                self.assertIn("_ov", linha,
                              "read() devolve (dados, overflowed) nos dois modos")


class TestMensagemDeFalhaDoMicrofone(unittest.TestCase):
    def _f(self, macos=True):
        return carregar(
            ["explicar_falha_do_microfone"],
            stubs={"plataforma": _Plataforma(macos),
                   "ONDE_PERMITIR_MIC": "Ajustes → Privacidade → Microfone",
                   "re": __import__("re")})["explicar_falha_do_microfone"]

    def test_biblioteca_faltando_nao_e_tratada_como_permissao(self):
        """O erro do log mandava o trader conferir permissões do sistema por
        causa de um pacote do Python. Ele foi procurar no lugar errado."""
        msg = self._f()(ModuleNotFoundError("No module named 'numpy'"))
        self.assertIn("numpy", msg)
        self.assertIn("NÃO é permissão", msg)
        self.assertIn("pip install numpy", msg)
        self.assertNotIn("Privacidade", msg)

    def test_comando_certo_para_cada_sistema(self):
        erro = ModuleNotFoundError("No module named 'numpy'")
        self.assertIn("python3 -m pip install", self._f(macos=True)(erro))
        win = self._f(macos=False)(erro)
        self.assertIn("python -m pip install", win)
        self.assertNotIn("python3", win)

    def test_erro_de_verdade_do_microfone_continua_falando_de_permissao(self):
        msg = self._f()(OSError("Device unavailable"))
        self.assertIn("Device unavailable", msg)
        self.assertIn("Privacidade", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOGatekeeperBloqueouTudo(unittest.TestCase):
    """18/08, 15:37 — o print dele, dois cliques no CRIAR_APP.command:

        "O item CRIAR_APP.command Não Foi Aberto
         A Apple não pôde verificar se o item está livre de algum malware"
                  [ Mover para o Lixo ]   [ OK ]

    Todo arquivo que sai de um zip baixado leva a marca de QUARENTENA, e
    script sem assinatura paga da Apple é bloqueado. Não é defeito do
    programa — mas é o ponto onde a instalação para, e um botão "Mover para o
    Lixo" ao lado do aviso é o convite para apagar o pacote inteiro.

    O `.command` já citava o LEIA-ME, e isso nunca resolveu nada: texto dentro
    de um arquivo bloqueado não desarma o Gatekeeper.
    """

    def setUp(self):
        # No pacote do outro sistema este arquivo não existe — e não
        # existir ali é o certo. Falhar por isso assustaria o cliente
        # com um vermelho que não é defeito nenhum.
        pular_se_faltar("DESBLOQUEAR_MAC.txt")

    def _ler(self, nome):
        with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
            return f.read()

    def test_existe_um_arquivo_de_TEXTO_com_a_saida(self):
        """Texto puro é a única coisa que o Gatekeeper nunca bloqueia — por
        isso a saída tem de estar num .txt, e não dentro de um .command."""
        self.assertTrue(os.path.exists(os.path.join(RAIZ, "DESBLOQUEAR_MAC.txt")))
        txt = self._ler("DESBLOQUEAR_MAC.txt")
        self.assertIn("xattr -dr com.apple.quarantine", txt)
        self.assertIn("ARRASTE", txt, "não ensina a arrastar a pasta — sem "
                      "isso ele teria de digitar o caminho à mão")
        self.assertIn("NUNCA", txt.upper())
        self.assertIn("Mover para o Lixo", txt,
                      "não avisa qual botão NÃO clicar")

    def test_o_txt_explica_que_nao_e_virus(self):
        """'A Apple não pôde verificar' não é 'a Apple encontrou algo'. Quem
        não sabe a diferença apaga o pacote."""
        txt = self._ler("DESBLOQUEAR_MAC.txt")
        self.assertIn("NÃO PÔDE VERIFICAR", txt.upper())

    def _todos_os_command(self):
        """Os .command que existem NESTA pasta.

        Lista fixa não serve: o `ABRIR_PAINEL_LICENCAS.command` sai do pacote
        do CLIENTE (o `--sem-painel` o remove de propósito). Com a lista
        escrita à mão, a suíte passava aqui e quebrava com FileNotFoundError
        dentro do zip do cliente — quem pegou foi rodar a suíte de dentro do
        pacote descompactado. Perguntar à pasta funciona nos dois."""
        import glob
        achados = sorted(glob.glob(os.path.join(RAIZ, "*.command")))
        self.assertGreaterEqual(len(achados), 3,
                                "sumiram os .command do Mac desta pasta")
        return achados

    def test_todo_command_se_AUTO_CURA(self):
        """O primeiro script que conseguir rodar limpa a pasta inteira. Sem
        isso ele levaria o mesmo susto quatro vezes, uma por arquivo."""
        for caminho in self._todos_os_command():
            sh = self._ler(os.path.basename(caminho))
            self.assertIn('xattr -dr com.apple.quarantine "$(pwd)"', sh,
                          os.path.basename(caminho))

    def test_todo_command_avisa_do_iCLOUD(self):
        """No print de 18/08 a pasta estava em iCloud Drive e o Finder já
        mostrava 'Não foi possível concluir a sincronização'. O iCloud retira
        do disco o arquivo parado e deixa um marcador — o programa quebra no
        meio do pregão, num arquivo que funcionava ontem."""
        for caminho in self._todos_os_command():
            nome = os.path.basename(caminho)
            sh = self._ler(nome)
            self.assertIn("Mobile Documents", sh, nome)
            self.assertIn("ICLOUD DRIVE", sh.upper(), nome)
