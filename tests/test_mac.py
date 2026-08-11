"""O que o programa DIZ quando roda no Mac.

Duas coisas quebraram aqui, e as duas custaram um pregão:

1. `No module named 'numpy'` — o sounddevice importa numpy, o numpy não estava
   em requirements-mac.txt, e o app respondia "rode: pip install sounddevice",
   que era exatamente o que o trader já tinha feito. O microfone e a fala da
   TIGER ficaram mortos sem que nada na tela explicasse por quê.
2. Mensagens mandando um usuário de macOS abrir telas do Windows.
"""

import os
import re
import unittest

from harness import RAIZ, carregar, fonte_do_arquivo


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
        # Esta pode existir, mas SÓ dentro do ramo do Windows das constantes de
        # ajuda (ou num comentário). Nunca solta no meio de uma mensagem.
        for n, linha in enumerate(fonte.splitlines(), 1):
            if "Sistema → Som" not in linha:
                continue
            self.assertTrue(
                linha.lstrip().startswith("#") or "(Windows)" in linha
                or "(macOS)" in linha or "E_MACOS" in linha,
                f"linha {n} manda o trader para uma tela do Windows sem "
                f"checar o sistema: {linha.strip()}")

    def test_as_constantes_de_ajuda_existem(self):
        fonte = fonte_do_arquivo()
        self.assertIn("ONDE_PERMITIR_MIC", fonte)
        self.assertIn("ONDE_TROCAR_MIC", fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
