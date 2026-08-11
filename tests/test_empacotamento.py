"""Os dois pacotes de entrega — Windows e Mac.

O BURACO QUE ISTO FECHA
-----------------------
Por várias versões o repositório teve `SMC_Quant_Pro_MAC.spec` e
`requirements-mac.txt`, e NÃO teve os equivalentes do Windows. Ou seja: dava
para reconstruir a versão do Mac a partir do repositório, e não dava para
reconstruir a do Windows — o `.spec` que gera o `.exe` vivia só na máquina do
trader. Ninguém percebeu porque nada verificava.

Aqui a simetria vira teste: o que existe de um lado tem de existir do outro,
e o `empacotar.py` tem de saber montar os dois.
"""

import os
import unittest

from harness import RAIZ


def _existe(*partes):
    return os.path.exists(os.path.join(RAIZ, *partes))


def _pacotes(lista):
    """Os pacotes que o pip de fato instalaria — sem comentários nem vazios."""
    with open(os.path.join(RAIZ, lista), encoding="utf-8") as f:
        return [l.strip().lower() for l in f
                if l.strip() and not l.lstrip().startswith("#")]


class TestSimetriaEntreOsSistemas(unittest.TestCase):
    def test_cada_arquivo_de_mac_tem_o_par_de_windows(self):
        pares = [
            ("requirements-mac.txt", "requirements.txt"),
            ("SMC_Quant_Pro_MAC.spec", "SMC_Quant_Pro.spec"),
            ("LEIA-ME_MAC.txt", "LEIA-ME_WINDOWS.txt"),
        ]
        for do_mac, do_windows in pares:
            self.assertTrue(_existe(do_mac), f"sumiu: {do_mac}")
            self.assertTrue(
                _existe(do_windows),
                f"'{do_mac}' existe mas '{do_windows}' não — o repositório "
                "voltou a saber compilar só para um sistema.")

    def test_o_spec_do_windows_e_do_windows_mesmo(self):
        with open(os.path.join(RAIZ, "SMC_Quant_Pro.spec"), encoding="utf-8") as f:
            spec = f.read()
        # Sem os módulos do pywin32 declarados, o .exe sai sem listar janelas.
        for modulo in ("win32gui", "win32crypt", "pywintypes"):
            self.assertIn(modulo, spec, modulo)
        # E o que é do Mac tem de estar EXCLUÍDO, não incluído.
        self.assertIn("excludes=[", spec)
        i = spec.index("excludes=[")
        self.assertIn("Quartz", spec[i:i + 300])

    def test_o_spec_do_mac_continua_sendo_do_mac(self):
        with open(os.path.join(RAIZ, "SMC_Quant_Pro_MAC.spec"), encoding="utf-8") as f:
            spec = f.read()
        self.assertIn("target_arch='arm64'", spec)
        # As permissões do macOS: sem estas chaves o sistema nega em silêncio.
        self.assertIn("NSScreenCaptureUsageDescription", spec)
        self.assertIn("NSMicrophoneUsageDescription", spec)

    def test_numpy_nas_duas_listas_de_dependencia(self):
        """O sounddevice importa numpy nos DOIS sistemas. Faltou no Mac e matou
        o microfone; não pode faltar no Windows pelo mesmo motivo."""
        for lista in ("requirements.txt", "requirements-mac.txt"):
            self.assertTrue(any(p.startswith("numpy") for p in _pacotes(lista)),
                            lista)

    def test_cada_lista_tem_a_biblioteca_de_janelas_do_seu_sistema(self):
        # Só as linhas que o pip realmente instala. Comentário citando o outro
        # sistema é explicação, não dependência — e foi assim que este teste
        # falhou na primeira vez, acusando um comentário.
        win = _pacotes("requirements.txt")
        mac = _pacotes("requirements-mac.txt")
        self.assertTrue(any(p.startswith("pywin32") for p in win))
        self.assertFalse(any(p.startswith("pyobjc") for p in win),
                         "pyobjc não instala no Windows")
        self.assertTrue(any(p.startswith("pyobjc-framework-quartz") for p in mac))
        self.assertFalse(any(p.startswith("pywin32") for p in mac),
                         "pywin32 não instala no Mac")


class TestEmpacotador(unittest.TestCase):
    def _mod(self):
        import importlib.util
        caminho = os.path.join(RAIZ, "empacotar.py")
        spec = importlib.util.spec_from_file_location("empacotar", caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_todo_arquivo_listado_existe_de_verdade(self):
        """É a checagem que o próprio script faz antes de zipar. Se ela falhar
        aqui, o pacote sairia incompleto — e isso só apareceria na máquina do
        trader, no meio do pregão."""
        m = self._mod()
        m.conferir(m.COMUM + m.SO_WINDOWS + [m.PAINEL])
        m.conferir(m.COMUM + m.SO_MAC + [m.PAINEL])

    def test_o_codigo_e_o_mesmo_nos_dois_pacotes(self):
        """A lista COMUM é a prova de que não existe 'versão do Mac' do código.
        Se um destes migrar para SO_WINDOWS ou SO_MAC, os dois sistemas passam
        a divergir em silêncio."""
        m = self._mod()
        for arquivo in ("main_app.py", "plataforma.py", "tradovate_auto.py",
                        "motor/index.js", "versao.json"):
            self.assertIn(arquivo, m.COMUM, arquivo)
            self.assertNotIn(arquivo, m.SO_WINDOWS, arquivo)
            self.assertNotIn(arquivo, m.SO_MAC, arquivo)

    def test_a_suite_de_testes_vai_nos_dois_pacotes(self):
        m = self._mod()
        self.assertIn("tests/run.py", m.COMUM)

    def test_nenhum_arquivo_esta_nas_duas_cascas(self):
        m = self._mod()
        repetidos = set(m.SO_WINDOWS) & set(m.SO_MAC)
        self.assertEqual(repetidos, set(),
                         f"arquivo em ambas as cascas: {repetidos}")

    def test_a_versao_vem_do_versao_json(self):
        """Nunca de um número digitado no script, que envelheceria em silêncio
        e batizaria o zip com a versão errada."""
        import json
        m = self._mod()
        with open(os.path.join(RAIZ, "versao.json"), encoding="utf-8") as f:
            self.assertEqual(m.versao(), json.load(f)["versao"])

    def test_o_painel_de_licencas_pode_ser_deixado_de_fora(self):
        """Ele carrega o token de administrador. Precisa existir um jeito de
        gerar o pacote sem ele antes de repassar a alguém."""
        m = self._mod()
        self.assertEqual(m.PAINEL, "painel_licencas.html")
        with open(os.path.join(RAIZ, "empacotar.py"), encoding="utf-8") as f:
            self.assertIn("--sem-painel", f.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
