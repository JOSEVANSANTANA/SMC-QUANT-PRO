"""UM SLOT SÓ NO CHAVEIRO — e por que isso deu seis 401 seguidos.

20/08, ele: "encontre alguma forma de adicionar essa chave porque ainda está
dando erro". Chave nova, recém-gerada, colada no campo certo, e o OpenRouter
recusando em todos os seis modelos.

A chave estava certa. O cofre é que estava errado.

    _KC_CONTA = "gemini_api_key"     # CONSTANTE

As três funções do Chaveiro usavam essa constante sem perguntar de quem era o
segredo. Ou seja: UM slot para TODAS as chaves do programa. Salvar a do
OpenRouter APAGAVA a da Gemini e escrevia a nova no lugar dela; salvar a da
OpenAI apagava a do OpenRouter. E na leitura, `chave_openrouter_enc`,
`chave_openai_enc` e `gemini_api_key_enc` apontavam todos para o mesmo lugar,
devolvendo a última chave salva.

O SINTOMA, no log dele, foi o diagnóstico de formato batendo em cheio:

    🔎 a chave tem 53 caracteres e a deste provedor tem 73
       (começa com 'AQ.Ab8RN6...')                    <- campo OpenRouter
    🔎 a chave começa com 'AQ.Ab8RN6...'              <- campo OpenAI

`AQ.` é o formato novo da chave do Google. Os dois campos estavam devolvendo a
chave da Gemini, e o programa mandava, com toda a confiança, uma credencial
que não era daquele serviço.

O desenho já previa slot por nome — o config guarda "keychain:<nome>", não
"keychain:" seco. Faltava passar o nome, de um lado e do outro.
"""

import os
import unittest

from harness import RAIZ, carregar, fonte_do_arquivo


class TestCadaSegredoNoSeuSlot(unittest.TestCase):

    def _plataforma_fake_macos(self):
        """Um Chaveiro de mentira: dicionário de slots, como o security(1)."""
        import importlib
        import plataforma
        importlib.reload(plataforma)
        cofre = {}
        plataforma.E_MACOS, plataforma.E_WINDOWS = True, False
        plataforma._keychain_gravar = (
            lambda s, nome=plataforma._KC_CONTA: cofre.__setitem__(nome, s) or True)
        plataforma._keychain_ler = (
            lambda nome=plataforma._KC_CONTA: cofre.get(nome, ""))
        plataforma._keychain_apagar = (
            lambda nome=plataforma._KC_CONTA: cofre.pop(nome, None))
        return plataforma, cofre

    def test_salvar_uma_chave_NAO_apaga_a_outra(self):
        """O coração do defeito. Salvar o OpenRouter derrubava a Gemini."""
        p, cofre = self._plataforma_fake_macos()
        gem = "AQ.Ab8RN6" + "x" * 44
        orr = "sk-or-v1-" + "5" * 64
        p.proteger_segredo(gem, "gemini_api_key")
        p.proteger_segredo(orr, "chave_openrouter")
        self.assertEqual(cofre.get("gemini_api_key"), gem,
                         "a Gemini foi apagada ao salvar o OpenRouter")
        self.assertEqual(cofre.get("chave_openrouter"), orr)
        self.assertEqual(len(cofre), 2, "cada segredo tem de ter o seu slot")

    def test_cada_ponteiro_devolve_o_SEU_segredo(self):
        p, _ = self._plataforma_fake_macos()
        gem = "AQ.Ab8RN6" + "x" * 44
        orr = "sk-or-v1-" + "5" * 64
        pg = p.proteger_segredo(gem, "gemini_api_key")
        po = p.proteger_segredo(orr, "chave_openrouter")
        self.assertEqual(p.revelar_segredo(pg), gem)
        self.assertEqual(p.revelar_segredo(po), orr)

    def test_o_ponteiro_gravado_LEVA_O_NOME_do_slot(self):
        """Sem o nome escrito no ponteiro, a leitura não teria como acertar."""
        p, _ = self._plataforma_fake_macos()
        self.assertEqual(
            p.proteger_segredo("x" * 40, "chave_openrouter"),
            "keychain:chave_openrouter")

    def test_ponteiro_antigo_sem_nome_ainda_e_lido(self):
        """Config gravado antes desta correção não pode virar lixo."""
        p, cofre = self._plataforma_fake_macos()
        cofre["gemini_api_key"] = "chave-velha"
        self.assertEqual(p.revelar_segredo("keychain:"), "chave-velha")


class TestOPonteiroQueMiraOSegredoDeOutro(unittest.TestCase):
    """Corrigir a gravação não conserta o config que já está no disco.

    Todo campo salvo no macOS antes desta versão ficou gravado como
    'keychain:gemini_api_key' — inclusive o do OpenRouter. Esses ponteiros
    continuam mirando o segredo da Gemini, e devolver a chave da Gemini quando
    alguém pede a do OpenRouter é exatamente o que produziu os 401."""

    def _f(self):
        return carregar(["ponteiro_do_cofre_e_de_outro"])[
            "ponteiro_do_cofre_e_de_outro"]

    def test_ponteiro_da_gemini_no_campo_do_openrouter_e_recusado(self):
        self.assertTrue(self._f()("openrouter", "keychain:gemini_api_key"))

    def test_ponteiro_proprio_passa(self):
        self.assertFalse(self._f()("openrouter", "keychain:chave_openrouter"))

    def test_blob_do_windows_nao_e_ponteiro(self):
        """No DPAPI o dado vem dentro do próprio blob — não há slot para errar,
        e tratar o blob como ponteiro apagaria a chave de quem usa Windows."""
        self.assertFalse(self._f()("openrouter", "AQIDBAUGBwg="))
        self.assertFalse(self._f()("openrouter", "texto:c2stb3ItdjEt"))

    def test_carregar_chave_devolve_VAZIO_e_nao_a_chave_alheia(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def carregar_chave_provedor")
        corpo = fonte[i:i + 800]
        self.assertIn("ponteiro_do_cofre_e_de_outro", corpo)


class TestVerAChave(unittest.TestCase):
    """"adicione também no painel a opção de ver a chave, porque atualmente ela
    fica somente ****** quando a gente cola na ferramenta."

    Ele tinha razão, e o campo escondido não era só desconforto: foi ele que
    permitiu a chave da Gemini ficar parada no campo do OpenRouter sem ninguém
    perceber. Asterisco protege de quem olha por cima do ombro; não protege de
    erro — e erro em campo de credencial vira 401 no meio do pregão."""

    def test_existe_o_alternador(self):
        fonte = fonte_do_arquivo()
        self.assertIn("def _alternar_ver_chave", fonte)
        i = fonte.index("def _alternar_ver_chave")
        corpo = fonte[i:i + 900]
        self.assertIn('show=""', corpo)
        self.assertIn('cget("show")', corpo)

    def test_o_olho_aparece_nos_campos_de_provedor_E_no_da_gemini(self):
        fonte = fonte_do_arquivo()
        self.assertGreaterEqual(
            fonte.count("_alternar_ver_chave(c)")
            + fonte.count("_alternar_ver_chave(self.api_entry)"), 2)


if __name__ == "__main__":
    unittest.main()
