"""REINICIAR O CICLO NÃO APAGA PREJUÍZO DO FREIO DE PERDA.

Os dois casos abaixo são o diário real do trader, `positions_db.json`.

**22/08.** Três operações fechadas na conta ativa:

    11:15  +US$137,50
    11:44  -US$400,00
    12:07  -US$2.000,00     total real do dia: -US$2.262,50

Às 12:08 o freio anunciou "o prejuízo de hoje (US$-2.000,00) bateu o drawdown
máximo do plano". Contou UMA operação. E às 12:10:12 o `ciclo_inicio` do
config passou a ser `2026-08-22T12:10:12` — três minutos depois da perda.

**21/08.** Sete operações fechadas, com o mesmo teto de US$2.000:

    19:51 -258,30   20:37 +675,00   21:06 -641,55   22:00 -728,20
    22:19 -720,00   22:53 -960,00   23:16 -400,00

Total: -US$3.033,05. O limite estourou às 22:53, com -US$2.633,05 acumulados.
Às 22:57 o robô abriu mais uma, que perdeu outros US$400. O freio não travou
nenhuma vez naquela noite.

A causa é a mesma nos dois: `operacoes_fechadas_hoje` lia de
`posicoes_do_ciclo()`, que filtra por `data_criacao >= ciclo_inicio`. O CICLO é
relatório — o trader reinicia quando quer recontar uma meta. O DRAWDOWN DO DIA
é risco, e pertence à mesa proprietária, que não sabe que alguém apertou um
botão no aplicativo. Compartilhar o filtro fazia o clique apagar dinheiro
perdido de verdade.
"""

import unittest

from harness import carregar


DIA_22 = [
    {"id": 1, "status": "FECHADA", "pnl_final": 137.50,
     "data_criacao": "22/08/2026 11:05", "data_fechamento": "22/08/2026 11:15"},
    {"id": 2, "status": "FECHADA", "pnl_final": -400.00,
     "data_criacao": "22/08/2026 11:41", "data_fechamento": "22/08/2026 11:44"},
    {"id": 3, "status": "FECHADA", "pnl_final": -2000.00,
     "data_criacao": "22/08/2026 12:03", "data_fechamento": "22/08/2026 12:07"},
]

# A noite de 21/08, na ordem em que fechou.
DIA_21 = [
    {"id": 10, "status": "FECHADA", "pnl_final": -258.30,
     "data_criacao": "21/08/2026 19:42", "data_fechamento": "21/08/2026 19:51"},
    {"id": 11, "status": "FECHADA", "pnl_final": 675.00,
     "data_criacao": "21/08/2026 20:35", "data_fechamento": "21/08/2026 20:37"},
    {"id": 12, "status": "FECHADA", "pnl_final": -641.55,
     "data_criacao": "21/08/2026 20:40", "data_fechamento": "21/08/2026 21:06"},
    {"id": 13, "status": "FECHADA", "pnl_final": -728.20,
     "data_criacao": "21/08/2026 21:50", "data_fechamento": "21/08/2026 22:00"},
    {"id": 14, "status": "FECHADA", "pnl_final": -720.00,
     "data_criacao": "21/08/2026 22:00", "data_fechamento": "21/08/2026 22:19"},
    {"id": 15, "status": "FECHADA", "pnl_final": -960.00,
     "data_criacao": "21/08/2026 22:34", "data_fechamento": "21/08/2026 22:53"},
]

PLANO = {"drawdown_maximo": 2000.0, "max_stops_seguidos": 20,
         "cooldown_stop_min": 30, "max_operacoes_dia": 20}

# O config real dele: pregão que atravessa a meia-noite.
CFG = {"hora_inicio": "19:00", "hora_fim": "17:59"}


def _ns(posicoes, agora, ciclo=None):
    """Monta o freio com um diário e um relógio fixos.

    `ciclo` é o `ciclo_inicio` — o que o trader zera ao reiniciar a contagem.

    O RELÓGIO É CONGELADO DE PROPÓSITO. `data_do_pregao()` chama
    `datetime.datetime.now()`, e o pregão dele atravessa a meia-noite
    (19:00→17:59): sem congelar, este arquivo passaria de manhã e falharia
    depois das 19h, porque a noite de 21/08 sairia do pregão corrente. Teste
    que depende da hora em que roda ensina a suíte a ser ignorada — e é esta
    suíte que segura as travas de dinheiro.
    """
    import datetime as _dt

    def _parse(txt):
        if not txt:
            return None
        try:
            return _dt.datetime.strptime(str(txt), "%d/%m/%Y %H:%M")
        except ValueError:
            return None

    class _DataHoraCongelada(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return agora

    class _RelogioParado:
        datetime = _DataHoraCongelada
        timedelta = _dt.timedelta
        date = _dt.date

    return carregar(
        ["operacoes_fechadas_hoje", "drawdown_restante_hoje",
         "freio_de_sugestoes", "data_do_pregao"],
        stubs={
            "carregar_posicoes": lambda: list(posicoes),
            "posicoes_do_ciclo": lambda: [
                p for p in posicoes
                if ciclo is None or (_parse(p.get("data_criacao")) or
                                     _dt.datetime.min) >= ciclo],
            "_e_da_conta_ativa": lambda p: True,
            "_hora_do_registro": _parse,
            "carregar_config": lambda: dict(CFG),
            "plano_da_conta_ativa": lambda: dict(PLANO),
            "PADRAO_CONFIG_APP": CFG,
            "datetime": _RelogioParado,
        })


class TestODiaDe22(unittest.TestCase):
    """O freio anunciou -2.000 quando o dia real era -2.262,50."""

    def test_com_o_ciclo_reiniciado_o_freio_ainda_ve_o_dia_inteiro(self):
        import datetime as dt
        # O ciclo foi reiniciado às 12:10 — depois de TUDO ter fechado.
        ns = _ns(DIA_22, dt.datetime(2026, 8, 22, 12, 30),
                 ciclo=dt.datetime(2026, 8, 22, 12, 10, 12))
        fechadas = ns["operacoes_fechadas_hoje"](ignorar_ciclo=True)
        self.assertEqual(len(fechadas), 3,
                         "o clique em 'reiniciar ciclo' não pode sumir com "
                         "operação fechada do mesmo pregão")
        self.assertAlmostEqual(sum(p["pnl_final"] for p in fechadas), -2262.50, 2)

    def test_o_relatorio_continua_respeitando_o_ciclo(self):
        """A trava não pode atropelar o que o ciclo existe para fazer.

        Reiniciar o ciclo tem de continuar zerando a contagem de META. O que
        muda é só quem calcula RISCO.
        """
        import datetime as dt
        ns = _ns(DIA_22, dt.datetime(2026, 8, 22, 12, 30),
                 ciclo=dt.datetime(2026, 8, 22, 12, 10, 12))
        self.assertEqual(ns["operacoes_fechadas_hoje"](), [])


class TestANoiteDe21(unittest.TestCase):
    """Sete operações, -US$3.033,05, teto de US$2.000, e nenhuma trava."""

    def test_depois_de_estourar_o_teto_o_robo_para(self):
        import datetime as dt
        # 22:57, o instante em que ele abriu a sétima operação.
        ns = _ns(DIA_21, dt.datetime(2026, 8, 21, 22, 57))
        pode, motivo = ns["freio_de_sugestoes"]()
        self.assertFalse(pode, "com -2.633,05 contra teto de 2.000, o dia acabou")
        self.assertIn("drawdown máximo", motivo)

    def test_o_numero_que_ele_ve_e_o_numero_real(self):
        """Freio que trava com o valor errado ensina o trader a desconfiar."""
        import datetime as dt
        ns = _ns(DIA_21, dt.datetime(2026, 8, 21, 22, 57))
        _, motivo = ns["freio_de_sugestoes"]()
        self.assertIn("2,633.05", motivo)

    def test_antes_de_estourar_ele_nao_atrapalha(self):
        """Travar cedo demais é o outro jeito de perder a conta — por não
        operar. Às 22:19 o acumulado era -1.673,05, dentro do teto."""
        import datetime as dt
        ns = _ns(DIA_21[:5], dt.datetime(2026, 8, 21, 22, 30))
        pode, _ = ns["freio_de_sugestoes"]()
        self.assertTrue(pode)


class TestODimensionamentoTambemEnxerga(unittest.TestCase):

    def test_drawdown_restante_nao_e_apagado_pelo_ciclo(self):
        """Se o teto do dimensionamento voltar a 2.000 depois do reinício, a
        próxima ordem é dimensionada como se o dia não tivesse acontecido."""
        import datetime as dt
        ns = _ns(DIA_22, dt.datetime(2026, 8, 22, 12, 30),
                 ciclo=dt.datetime(2026, 8, 22, 12, 10, 12))
        self.assertEqual(ns["drawdown_restante_hoje"](), 0.0)


if __name__ == "__main__":
    unittest.main()
