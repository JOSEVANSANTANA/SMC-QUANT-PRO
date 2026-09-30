"""PERSEGUIR A META — o modo que ele pediu sabendo do risco.

22/08. Plano na tela: Margem US$2.000 · Risco 5% · R:R 1:2 · 5 operações/dia ·
Meta US$3.000 em 1 dia. O motor sugeria 1 contrato e ele perguntou: "ele tem
margem, tem drawdown disponível, o risco é 5% — o que explica tamanha
cautela?"

Não era cautela: 5% de US$2.000 são US$100, e um stop de 12 pontos no MES
custa US$60 por contrato. US$100 ÷ US$60 = 1. O dimensionamento era a única
parte do sistema obedecendo ao plano à risca.

Apresentada a conta — o melhor dia possível daquele plano eram US$1.000, um
terço da Meta — ele escolheu que o motor passasse a dimensionar olhando o que
FALTA para a meta. Escolha dele, com o risco dito antes.

=====================================================================
POR QUE ESTE ARQUIVO EXISTE
=====================================================================
"Dimensionar pelo que falta" é a definição de martingale: perder aumenta o que
falta, que aumenta a posição, que aumenta a perda. Um martingale dentro de um
robô que manda ordem sozinho é como uma conta acaba numa tarde.

O modo foi construído com três rédeas, e o que estes testes guardam NÃO é o
tamanho da posição — é que as três continuem lá:

  1. SÓ SOBE          — nunca fica abaixo do risco base do plano.
  2. TETO DURO        — `risco_max_pct` (0 = automático, 3x o risco base).
  3. FRAÇÃO DO QUE    — uma operação só gasta 33% do drawdown que resta
     RESTA HOJE         (`fracao_max_do_restante`, já existente e valendo com
                        o modo ligado ou desligado). Esta é a única que APERTA
                        quando o dia piora, e é ela que separa perseguir a
                        meta de dobrar a aposta.

O teste do dia ruim (TestNaoViraMartingale) é o mais importante do arquivo.
Se um dia ele falhar, o modo virou a coisa que ele jurou não ser.
"""

import unittest

from harness import carregar


PLANO = {"margem": 2000.0, "risco_pct": 5.0, "drawdown_maximo": 1000.0,
         "meta_alvo": 3000.0, "dias_meta": 1, "rr_minimo": 2.0,
         "max_operacoes_dia": 5, "max_contratos": 60, "min_ticks_stop": 8,
         "perseguir_meta": True, "risco_max_pct": 0}

RISCO_BASE = 100.0      # 5% de US$2.000
TETO_AUTO = 300.0       # 3x o risco base


def _ns(plano=None, feitas_hoje=0, dia=1):
    plano = plano if plano is not None else PLANO
    return carregar(
        ["risco_para_perseguir_a_meta", "oportunidades_restantes_do_ciclo",
         "calcular_contratos", "FRACAO_MAX_DO_RESTANTE_PADRAO"],
        stubs={"plano_da_conta_ativa": lambda: plano,
               "operacoes_fechadas_hoje": lambda: [None] * feitas_hoje,
               "posicoes_do_ciclo": lambda: [],
               "dias_meta_do_plano": lambda p: int(p.get("dias_meta", 1) or 1),
               "dia_do_ciclo": lambda p: dia,
               "valor_por_ponto_do_ativo": lambda a: 5.0,
               "tick_do_ativo": lambda a: 0.25})


class TestODesligadoContinuaSendoOPadrao(unittest.TestCase):
    """A mudança não pode vazar para quem não pediu por ela."""

    def test_plano_sem_o_campo_nao_persegue_nada(self):
        ns = _ns({k: v for k, v in PLANO.items() if k != "perseguir_meta"})
        risco, _ = ns["risco_para_perseguir_a_meta"](
            {k: v for k, v in PLANO.items() if k != "perseguir_meta"},
            lucro_ciclo=0)
        self.assertIsNone(risco, "sem o campo ligado, o tamanho é o de sempre")

    def test_desligado_explicitamente_tambem_nao(self):
        p = dict(PLANO, perseguir_meta=False)
        ns = _ns(p)
        risco, motivo = ns["risco_para_perseguir_a_meta"](p, lucro_ciclo=0)
        self.assertIsNone(risco)
        self.assertIn("desligado", motivo)

    def test_o_padrao_de_fabrica_vem_desligado(self):
        padrao = carregar(["PLANO_PADRAO",
                           "MIN_TICKS_STOP_PADRAO"])["PLANO_PADRAO"]
        self.assertFalse(padrao["perseguir_meta"],
                         "uma conta nova não pode nascer perseguindo meta")


class TestARedeaDoTetoDuro(unittest.TestCase):

    def test_o_teto_automatico_e_tres_vezes_o_risco_base(self):
        """Faltando os US$3.000 inteiros, a conta pediria US$300 por operação
        — que é exatamente o teto. Acima disso ele não passa."""
        ns = _ns()
        risco, motivo = ns["risco_para_perseguir_a_meta"](PLANO, lucro_ciclo=0)
        self.assertEqual(risco, TETO_AUTO)
        self.assertIn("meta", motivo.lower())

    def test_meta_absurda_nao_estoura_o_teto(self):
        """US$50.000 em 1 dia não vira posição de US$50.000 de risco. O teto
        não negocia — é ele que impede a perseguição de virar aposta."""
        p = dict(PLANO, meta_alvo=50000.0)
        ns = _ns(p)
        risco, motivo = ns["risco_para_perseguir_a_meta"](p, lucro_ciclo=0)
        self.assertEqual(risco, TETO_AUTO)
        self.assertIn("LIMITADO", motivo)

    def test_teto_explicito_manda_no_automatico(self):
        p = dict(PLANO, risco_max_pct=8.0)     # 8% de 2000 = US$160
        ns = _ns(p)
        risco, _ = ns["risco_para_perseguir_a_meta"](p, lucro_ciclo=0)
        self.assertEqual(risco, 160.0)


class TestARedeaDoSoSobe(unittest.TestCase):

    def test_meta_que_cabe_no_risco_normal_nao_muda_nada(self):
        """Faltando US$500 em 5 chances a R:R 1:2, cada operação precisa
        arriscar US$50 — metade do risco base. O modo NÃO encolhe posição:
        ele existe para destravar tamanho, não para apertar."""
        ns = _ns()
        risco, motivo = ns["risco_para_perseguir_a_meta"](PLANO, lucro_ciclo=2500)
        self.assertIsNone(risco)
        self.assertIn("cabe no risco normal", motivo)

    def test_meta_batida_desliga_o_modo_sozinho(self):
        """Depois do alvo não há o que perseguir, e continuar grande é só
        devolver o que ganhou."""
        ns = _ns()
        risco, motivo = ns["risco_para_perseguir_a_meta"](PLANO, lucro_ciclo=3200)
        self.assertIsNone(risco)
        self.assertIn("já batida", motivo)

    def test_o_risco_DIMINUI_conforme_a_meta_se_aproxima(self):
        """A curva inteira, num teste só: quanto mais perto do alvo, menor a
        posição. É o contrário de um martingale — e é de graça, porque cai do
        próprio 'falta ÷ oportunidades'."""
        ns = _ns()
        f = ns["risco_para_perseguir_a_meta"]
        riscos = []
        for lucro in (0, 500, 1000, 1500, 2000):
            r, _ = f(PLANO, lucro_ciclo=lucro)
            riscos.append(r if r is not None else RISCO_BASE)
        self.assertEqual(riscos, sorted(riscos, reverse=True),
                         f"o risco tinha de cair a cada passo: {riscos}")


class TestNaoViraMartingale(unittest.TestCase):
    """O TESTE MAIS IMPORTANTE DESTE ARQUIVO.

    Um dia ruim, perdendo US$300 por operação. O que FALTA cresce a cada
    perda, então a meta puxa o tamanho para cima. Ao mesmo tempo o drawdown
    que resta encolhe, e só metade dele pode ir numa operação.

    Se as duas forças alguma vez se inverterem — se a posição CRESCER depois
    de uma perda — este modo virou a coisa que ele jurou não ser, e este teste
    é o que vai dizer isso em voz alta.
    """

    def _contratos_ao_longo_do_dia(self, perda_por_op=300.0):
        tamanhos, lucro = [], 0.0
        for i in range(5):
            ns = _ns(feitas_hoje=i)
            risco, _ = ns["risco_para_perseguir_a_meta"](PLANO, lucro_ciclo=lucro)
            restante = max(0.0, 1000.0 - abs(min(0.0, lucro)))
            r = ns["calcular_contratos"](
                7550.0, 7538.0, "MESU6", 2000.0, 5.0, 1000.0,
                max_contratos=60, min_ticks_stop=8, restante_dia=restante,
                risco_usd_override=risco,
                fracao_max_do_restante=ns["FRACAO_MAX_DO_RESTANTE_PADRAO"])
            tamanhos.append(r["contratos"])
            lucro -= perda_por_op
        return tamanhos

    def test_a_posicao_NUNCA_cresce_depois_de_uma_perda(self):
        t = self._contratos_ao_longo_do_dia()
        for i in range(1, len(t)):
            self.assertLessEqual(
                t[i], t[i - 1],
                f"MARTINGALE: a posição subiu de {t[i-1]} para {t[i]} depois "
                f"de perder. Sequência do dia: {t}")

    def test_o_dia_se_fecha_sozinho_antes_de_o_drawdown_acabar(self):
        """Chegar a zero contratos é a resposta certa: o freio do drawdown
        aperta mais rápido do que a meta puxa."""
        t = self._contratos_ao_longo_do_dia()
        self.assertEqual(t[-1], 0, f"o dia tinha de se fechar: {t}")

    def test_a_fracao_do_drawdown_e_o_que_segura(self):
        """Sem a fração, uma operação só gastaria TODO o limite do dia. Este
        teste mede a diferença entre ter e não ter a rédea."""
        ns = _ns(feitas_hoje=2)
        comum = dict(entry=7550.0, stop=7538.0, asset_symbol="MESU6",
                     margem=2000.0, risco_pct=5.0, drawdown_maximo=1000.0)
        com = ns["calcular_contratos"](
            comum["entry"], comum["stop"], comum["asset_symbol"],
            comum["margem"], comum["risco_pct"], comum["drawdown_maximo"],
            max_contratos=60, min_ticks_stop=8, restante_dia=400.0,
            risco_usd_override=300.0, fracao_max_do_restante=0.33)
        sem = ns["calcular_contratos"](
            comum["entry"], comum["stop"], comum["asset_symbol"],
            comum["margem"], comum["risco_pct"], comum["drawdown_maximo"],
            max_contratos=60, min_ticks_stop=8, restante_dia=400.0,
            risco_usd_override=300.0, fracao_max_do_restante=1.0)
        self.assertLess(com["contratos"], sem["contratos"],
                        "a fração tem de entregar posição MENOR que sem ela")


class TestAsOutrasTravasContinuamValendo(unittest.TestCase):
    """O modo meta muda o ORÇAMENTO. Não muda mais nada — e o que ele não
    pode fazer é servir de porta dos fundos para as travas já existentes."""

    def _r(self, entry, stop, **kw):
        ns = _ns()
        base = dict(max_contratos=60, min_ticks_stop=8, restante_dia=1000.0,
                    risco_usd_override=TETO_AUTO, fracao_max_do_restante=0.33)
        base.update(kw)
        return ns["calcular_contratos"](entry, stop, "MESU6", 2000.0, 5.0,
                                        1000.0, **base)

    def test_o_piso_de_ticks_continua_recusando_stop_curto(self):
        r = self._r(7550.0, 7549.5)          # 2 ticks, piso é 8
        self.assertEqual(r["contratos"], 0)
        self.assertIn("curto demais", r["motivo_limite"])

    def test_o_teto_de_contratos_continua_cortando(self):
        r = self._r(7550.0, 7548.0, max_contratos=4)   # caberiam 30
        self.assertEqual(r["contratos"], 4)
        self.assertIn("teto de 4", r["motivo_limite"])

    def test_drawdown_esgotado_continua_zerando(self):
        r = self._r(7550.0, 7538.0, restante_dia=0.0)
        self.assertEqual(r["contratos"], 0)


class TestOAvisoDoPlanoMudaDeTomComOModoLigado(unittest.TestCase):
    """Desligado, o programa promete NÃO crescer sozinho. Ligado, essa promessa
    vira mentira — e mentira no log é o defeito que este projeto mais persegue.
    A frase tem de trocar junto com o comportamento."""

    def _aviso(self, ligado):
        ns = carregar(["avisos_do_plano", "TICK_MINIMO", "VALOR_POR_PONTO"])
        p = dict(PLANO, perseguir_meta=ligado)
        return " ".join(a for a in ns["avisos_do_plano"](p) if "NÃO CABE" in a)

    def test_desligado_promete_nao_crescer(self):
        self.assertIn("não vou aumentar posição", self._aviso(False))

    def test_ligado_nao_repete_a_promessa_que_deixou_de_valer(self):
        self.assertNotIn("não vou aumentar posição", self._aviso(True))

    def test_ligado_diz_onde_o_teto_para(self):
        aviso = self._aviso(True)
        self.assertIn("PERSEGUIR A META está LIGADO", aviso)
        self.assertIn("US$300.00", aviso)     # o teto automático por operação

    def test_ligado_lembra_que_o_drawdown_continua_mandando(self):
        aviso = self._aviso(True)
        self.assertIn("metade do que resta", aviso)
        self.assertIn("DIMINUI", aviso)


class TestOTraderConsegueVerPorQue(unittest.TestCase):

    def test_o_dimensionamento_carrega_o_motivo_da_meta(self):
        """Tamanho que muda sem explicação é como o '1 contrato' de 22/08:
        manda o trader procurar defeito onde não há."""
        from harness import fonte_do_arquivo
        fonte = fonte_do_arquivo()
        i = fonte.index("def dimensionar_pelo_plano")
        corpo = fonte[i:i + 2500]
        self.assertIn('r["motivo_meta"] = motivo_meta', corpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
