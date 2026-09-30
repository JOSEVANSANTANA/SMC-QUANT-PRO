"""A notificação que roubava a tela, e o microfone que abria mudo.

Duas queixas do mesmo dia, no macOS, com a mesma raiz: comportamento do
SISTEMA que o programa estava tentando contornar do jeito errado.
"""

import ast
import unittest

from harness import ARQUIVO, fonte_do_arquivo

FONTE = fonte_do_arquivo(ARQUIVO)


def _corpo(nome):
    for no in ast.walk(ast.parse(FONTE)):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return "\n".join(FONTE.splitlines()[no.lineno - 1:no.end_lineno])
    raise AssertionError(f"função {nome} não existe mais")


class TestNotificacaoNaoRoubaAFocoNoMac(unittest.TestCase):
    """O estilo 'noActivates' do Tk NÃO bastou — a tela continuou pulando. A
    saída é não desenhar janela nenhuma no Mac: a Central de Notificações do
    próprio sistema aparece no canto e, por construção, não ativa app algum."""

    def test_no_mac_o_padrao_e_a_notificacao_do_sistema(self):
        corpo = _corpo("_estilo_notificacao")
        self.assertIn('"sistema" if plataforma.E_MACOS else "janela"', corpo)

    def test_a_notificacao_nativa_e_tentada_ANTES_de_criar_a_janela(self):
        corpo = _corpo("_notificar_desktop")
        self.assertLess(corpo.index("notificacao_do_sistema"),
                        corpo.index("def mostrar"),
                        "se a janela nascer antes, o foco já foi roubado")

    def test_se_a_nativa_falhar_ela_NAO_fica_calada(self):
        """Aviso que some em silêncio é pior que aviso que incomoda."""
        corpo = _corpo("_notificar_desktop")
        i = corpo.index("notificacao_do_sistema")
        self.assertIn("usando o aviso na tela", corpo[i:i + 700])

    def test_o_modo_silencioso_existe_e_nao_desenha_nada(self):
        corpo = _corpo("_notificar_desktop")
        self.assertIn('if self._estilo_notificacao() == "silencioso":', corpo)

    def test_a_escolha_e_relida_do_disco_antes_de_confirmar(self):
        """Regra da casa: grava, RELÊ, e só então diz que gravou."""
        corpo = _corpo("_salvar_estilo_notificacao")
        self.assertIn("gravado = self._estilo_notificacao()", corpo)
        self.assertIn("NÃO consegui gravar", corpo)

    def test_escolher_janela_no_mac_avisa_do_efeito(self):
        corpo = _corpo("_salvar_estilo_notificacao")
        self.assertIn("FAZ a tela pular", corpo)

    def test_a_camada_de_plataforma_so_notifica_no_mac(self):
        import plataforma
        import unittest.mock
        with unittest.mock.patch.object(plataforma, 'E_MACOS', False):
            self.assertFalse(plataforma.notificacao_do_sistema("t", "x"))

    def test_o_texto_da_notificacao_e_higienizado(self):
        """Aspas e barras quebram o AppleScript — e o texto vem de análise de
        mercado, que pode conter qualquer coisa."""
        import inspect
        import plataforma
        fonte = inspect.getsource(plataforma.notificacao_do_sistema)
        self.assertIn('replace(\'"\', "\'")', fonte)
        self.assertIn('replace("\\\\", " ")', fonte)


class TestMicrofoneMudoNoMac(unittest.TestCase):
    """18:32 — "escutando pelo MacBook Air Microphone" seguido de "não chega
    som nenhum". O stream ABRIU (o erro do numpy já não existe) e devolveu
    silêncio. No macOS, app sem permissão de microfone recebe zeros, não erro."""

    def test_a_mensagem_lidera_pela_permissao_e_nao_pelo_dispositivo(self):
        corpo = _corpo("_tiger_loop")
        i = corpo.index('if frase == b""')
        trecho = corpo[i:i + 3000]
        # O texto é quebrado em várias linhas de código; procuro os pedaços
        # como eles existem no fonte, não a frase remontada.
        self.assertIn("A PERMISSÃO DE ", trecho)
        self.assertIn("MICROFONE — e ela não dá erro", trecho)
        self.assertIn("simplesmente entrega silêncio", trecho)

    def test_ela_abre_a_tela_de_permissao_sozinha(self):
        corpo = _corpo("_tiger_loop")
        self.assertIn("plataforma.abrir_permissao_microfone()", corpo)

    def test_ela_diz_QUAL_app_marcar_na_lista(self):
        """Abrindo pelo .command, quem aparece na lista é o TERMINAL. Quem
        procura por 'SMC Quant Pro' não acha e conclui que já autorizou."""
        corpo = _corpo("_tiger_loop")
        self.assertIn("quem_pede_a_permissao", corpo)
        i = corpo.index('if frase == b""')
        self.assertIn("NÃO procure", corpo[i:i + 3000])

    def test_avisa_que_precisa_reabrir_o_programa(self):
        corpo = _corpo("_tiger_loop")
        i = corpo.index('if frase == b""')
        self.assertIn("FECHE e ABRA", corpo[i:i + 3000])

    def test_no_windows_a_mensagem_continua_sendo_a_do_dispositivo(self):
        corpo = _corpo("_tiger_loop")
        i = corpo.index('if frase == b""')
        self.assertIn("ONDE_TROCAR_MIC", corpo[i:i + 3500])

    def test_a_url_da_tela_de_permissao_e_a_do_microfone(self):
        import inspect
        import plataforma
        fonte = inspect.getsource(plataforma.abrir_permissao_microfone)
        self.assertIn("Privacy_Microphone", fonte)

    def test_quem_pede_a_permissao_nunca_devolve_vazio(self):
        import plataforma
        self.assertTrue(plataforma.quem_pede_a_permissao().strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
