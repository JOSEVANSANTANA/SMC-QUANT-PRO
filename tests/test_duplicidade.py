"""Uma posição real, UM registro no diário.

O DEFEITO (log de 11/08, entre 16:05 e 16:25):

    16:05  🔎 Detectei que você está posicionado: SELL MESU6 40 ctr @ 7746.5
           → nasce um registro origem=PLATAFORMA
    16:10  ⏳ Ordem PENDENTE registrada: SELL MESU6 @ 7748.0 (12 ctr)
           → nasce um registro origem=ROBO, status PENDENTE
    16:15  ✅ Execução CONFIRMADA pela plataforma: SELL MESU6 @ 7746.5 (40 ctr)
           → o registro do ROBO vira ABERTA contra a MESMA posição de 40 ctr

    A partir daí havia DOIS registros para UMA operação, e os dois fecharam:
        🔻 encerrada na plataforma: SELL MESU6 — US$-600,00
        📕 FECHADA no diário:       SELL MESU6 — US$-1.176,00

Resultado do dia, win rate, drawdown e o FREIO DE PERDA passaram todos a
trabalhar com número inflado — e foi o freio inflado que travou o pregão.
"""

import ast
import unittest

from harness import ARQUIVO, fonte_do_arquivo

FONTE = fonte_do_arquivo(ARQUIVO)


def _corpo(nome):
    for no in ast.walk(ast.parse(FONTE)):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            linhas = FONTE.splitlines()
            return "\n".join(linhas[no.lineno - 1:no.end_lineno])
    raise AssertionError(f"função {nome} não existe mais")


class TestFusaoDosRegistros(unittest.TestCase):
    def test_a_confirmacao_funde_o_registro_da_plataforma(self):
        corpo = _corpo("sincronizar_posicoes_plataforma")
        self.assertIn('g["status"] = "FUNDIDA"', corpo)
        self.assertIn('g.get("origem") == "PLATAFORMA"', corpo)

    def test_a_fusao_exige_mesmo_ativo_e_mesma_direcao(self):
        """Fundir por ativo apenas juntaria um BUY com um SELL do mesmo papel —
        duas operações de verdade viram uma, e o diário perde uma delas."""
        corpo = _corpo("sincronizar_posicoes_plataforma")
        i = corpo.index('g["status"] = "FUNDIDA"')
        criterio = corpo[max(0, i - 900):i]
        self.assertIn('str(g.get("ativo", "")).upper() == nome', criterio)
        self.assertIn('g.get("direcao") == pos.get("direcao")', criterio)

    def test_o_registro_fundido_nao_conta_dinheiro(self):
        """Os contadores filtram status == 'FECHADA'. FUNDIDA não é FECHADA,
        então sai da conta sem sumir do arquivo — histórico não se apaga."""
        self.assertIn('status") == "FECHADA"', FONTE)
        for fn in ("operacoes_fechadas_hoje", "resultados_por_dia"):
            self.assertIn('"FECHADA"', _corpo(fn), fn)
            self.assertNotIn('"FUNDIDA"', _corpo(fn), fn)

    def test_o_registro_do_robo_e_o_que_sobrevive(self):
        """É ele que tem o elo com a sugestão (sinal_id), o stop, o alvo e o
        dimensionamento planejado. O da plataforma tem só ativo/qtd/preço."""
        corpo = _corpo("sincronizar_posicoes_plataforma")
        i = corpo.index('g["status"] = "FUNDIDA"')
        self.assertIn('g["fundida_em"] = pos.get("id")', corpo[i:i + 400])

    def test_a_fusao_e_dita_no_log(self):
        corpo = _corpo("sincronizar_posicoes_plataforma")
        self.assertIn("contado em dobro", corpo,
                      "o trader precisa VER que dois registros viraram um")


class TestPosicaoDoRoboQueSomeDaPlataforma(unittest.TestCase):
    def test_existe_o_ramo_que_encerra(self):
        """Sem este ramo, uma posição do robô já confirmada que desaparece da
        corretora fica ABERTA para sempre. Isso não aparecia porque o registro
        DUPLICADO encerrava e dava a impressão de que o diário tinha fechado."""
        corpo = _corpo("sincronizar_posicoes_plataforma")
        self.assertIn('pos.get("execucao") == "CONFIRMADA"', corpo)
        self.assertIn("uma única vez", corpo)

    def test_o_resultado_vem_do_pnl_reportado_pela_corretora(self):
        corpo = _corpo("sincronizar_posicoes_plataforma")
        i = corpo.index("uma única vez")
        trecho = corpo[max(0, i - 700):i]
        self.assertIn('pos["pnl_final"] = round(pos.get("pnl_atual") or 0.0, 2)',
                      trecho)


class TestNotificacaoNaoRoubaFoco(unittest.TestCase):
    def test_a_janela_de_aviso_pede_para_nao_ativar_o_app(self):
        """No macOS, criar um Toplevel ATIVA o aplicativo — a tela pulava da
        corretora para cá a cada sugestão, sem ninguém clicar em nada."""
        corpo = _corpo("_notificar_desktop")
        self.assertIn("plataforma.janela_sem_roubar_foco(win)", corpo)

    def test_e_aplicado_antes_de_a_janela_aparecer(self):
        corpo = _corpo("_notificar_desktop")
        self.assertLess(corpo.index("janela_sem_roubar_foco"),
                        corpo.index("quadro.pack("))

    def test_a_camada_de_plataforma_so_mexe_no_mac(self):
        import plataforma
        self.assertTrue(hasattr(plataforma, "janela_sem_roubar_foco"))
        # Neste ambiente E_MACOS é False: tem de devolver False sem explodir,
        # sem tocar em Tk nenhum.
        self.assertFalse(plataforma.janela_sem_roubar_foco(object()))

    def test_o_foco_so_e_forcado_por_clique_do_trader(self):
        """`focus_force` pode existir — mas só dentro do handler de clique."""
        corpo = _corpo("_notificar_desktop")
        for n, linha in enumerate(corpo.splitlines()):
            if "focus_force" in linha:
                anteriores = "\n".join(corpo.splitlines()[max(0, n - 6):n])
                self.assertIn("def focar", anteriores,
                              "foco forçado fora do clique do trader")


if __name__ == "__main__":
    unittest.main(verbosity=2)
