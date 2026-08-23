"""A MADRUGADA DE 23/08: SETE HORAS ANALISANDO UMA FIGURA PARADA.

O replay pausou sozinho às 04:30 e o preço ficou em 7574,00 até as 11:00 —
29 ciclos. O robô continuou analisando, e em cima da MESMA imagem devolveu:

    04:30  BUY  70%   entrada 7552,5
    05:15  BUY  70%   entrada 7562,5
    05:30  BUY  72%   entrada 7555,0
    05:45  BUY  70%   entrada 7560,0
    06:30  BUY  78%   entrada 7565,0
    07:15  HOLD 40%
    08:15  HOLD 35%
    09:15  BUY  75%   entrada 7552,5

Probabilidade de 35% a 78%. Cinco entradas diferentes. A figura não mudou; as
leituras mudaram. Não há outra palavra para isso: o modelo inventou estrutura.

POR QUE AS TRAVAS QUE EXISTIAM NÃO SEGURARAM
--------------------------------------------
Havia DUAS, e as duas falharam por motivos diferentes:

  · a de HASH DA IMAGEM nunca dispara na prática — o relógio do sistema, o
    cursor e o repintar da página mudam pixels mesmo com o replay pausado, e
    o hash nunca repete;

  · a de PREÇO REPETIDO rodava DEPOIS da chamada da API. Ela suprimia a
    SUGESTÃO, e só quando a ação era BUY/SELL. A leitura alucinada já tinha
    custado cota, ido para o WhatsApp e entrado no contexto que a TIGER
    recebe como fato. HOLD passava direto.

Vinte e nove chamadas de API numa tela parada, num log em que TRÊS modelos
apareceram com "cota esgotada". A cota que faltou ao meio-dia foi gasta de
madrugada analisando uma imagem congelada.

A trava agora lê o preço do DOM pelo CDP — exato e imune a ruído de pixel —
e roda ANTES. Tela parada não vira chamada de API.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _ns():
    return carregar(
        ["avaliar_tamanho_do_stop", "faixa_de_stop_do_ativo",
         "FAIXA_TICKS_STOP", "_instrucao_de_escala_do_stop",
         "CICLOS_PARA_PRECO_CONGELADO"],
        stubs={"tick_do_ativo": lambda a: (
            0.25 if str(a).upper().startswith(("MES", "ES", "MNQ", "NQ")) else None)})


class TestATelaParadaNaoViraChamadaDeAPI(unittest.TestCase):

    def _corpo(self, nome, tamanho=3000):
        fonte = fonte_do_arquivo()
        i = fonte.index(nome)
        return fonte[i:i + tamanho]

    def test_a_trava_roda_ANTES_da_analise(self):
        """O ponto inteiro da correção. Depois da chamada, o estrago já foi
        feito: cota gasta, leitura no WhatsApp, contexto contaminado."""
        fonte = fonte_do_arquivo()
        i_trava = fonte.index("_tela_parada_pelo_cdp()")
        i_analise = fonte.index("Processando análise com Memória Episódica", i_trava - 4000)
        self.assertLess(i_trava, i_analise,
                        "a conferência de tela parada tem de vir ANTES do "
                        "'Processando análise' — senão a API já foi chamada")

    def test_ela_pula_o_ciclo_de_verdade(self):
        """`continue`, e não um aviso. A trava antiga avisava e deixava passar
        — avisar sem agir é o mesmo que não avisar."""
        fonte = fonte_do_arquivo()
        i = fonte.index("_tela_parada_pelo_cdp()")
        trecho = fonte[i:i + 2200]
        self.assertIn("continue", trecho)
        self.assertIn("CICLO PULADO", trecho)

    def test_o_preco_vem_do_DOM_e_nao_da_imagem(self):
        """A trava de hash de imagem existia e nunca disparou: com o replay
        pausado a figura ainda muda um pouco. O preço no DOM não muda — ou é
        o mesmo número, ou não é."""
        corpo = self._corpo("def _tela_parada_pelo_cdp")
        self.assertIn("ler_preco_imediato", corpo)

    def test_sem_leitura_do_CDP_o_ciclo_segue_normal(self):
        """Barrar a análise por FALTA de leitura deixaria o robô cego
        justamente quando a conexão oscila. Ausência de dado não é conclusão
        — nem para o lado de parar."""
        corpo = self._corpo("def _tela_parada_pelo_cdp")
        self.assertIn("return False, None, 0", corpo)

    def test_o_aviso_sai_uma_vez_e_o_retorno_tambem(self):
        """Vinte e nove linhas iguais no log escondem o que importa; e voltar
        a analisar em silêncio deixaria o trader sem saber que voltou."""
        fonte = fonte_do_arquivo()
        i = fonte.index("_tela_parada_pelo_cdp()")
        trecho = fonte[i:i + 2500]
        self.assertIn("_avisou_congelado_cdp", trecho)
        self.assertIn("voltou a andar", trecho)


class TestAEscalaDoStopCabeNoAtivo(unittest.TestCase):
    """'Ultimamente só tomamos stops.' Os stops do log, no MESMO MESU6 e no
    MESMO dia: 19 · 30 · 32 · 33 · 48 · 76 · 76 · 106 ticks.

    Do menor ao maior, 5,6 vezes. Não existe 'stop do cenário' variando cinco
    vezes — existe modelo escolhendo distância sem referência nenhuma do que é
    um movimento normal daquele contrato.
    """

    def test_o_stop_de_106_ticks_do_log_e_recusado(self):
        """26,5 pontos no MES é quase a amplitude de um dia. Com R:R 1:2 o
        alvo pediria 53 pontos — movimento que raramente vem no intradiário."""
        ok, ticks, motivo = _ns()["avaliar_tamanho_do_stop"](7571.5, 7545.0, "MESU6")
        self.assertFalse(ok)
        self.assertEqual(ticks, 106)
        self.assertIn("largo demais", motivo)

    def test_o_stop_de_76_ticks_que_perdeu_285_dolares_e_recusado(self):
        """A operação das 02:00 — BUY 3 ctr @ 7552,5, stop 7533,5 — foi ao
        stop às 02:21 e custou US$285. Era exatamente 76 ticks."""
        ok, ticks, _ = _ns()["avaliar_tamanho_do_stop"](7552.5, 7533.5, "MESU6")
        self.assertFalse(ok)
        self.assertEqual(ticks, 76)

    def test_os_stops_de_escala_normal_continuam_passando(self):
        """A trava não pode virar um freio que barra tudo: 30 a 48 ticks é
        exatamente onde um setup intradiário de MES vive."""
        f = _ns()["avaliar_tamanho_do_stop"]
        for entrada, stop in ((7538.50, 7531.00), (7541.50, 7533.50),
                              (7540.00, 7531.75), (7540.00, 7528.00)):
            ok, ticks, motivo = f(entrada, stop, "MESU6")
            self.assertTrue(ok, f"{ticks} ticks foi recusado: {motivo}")

    def test_stop_de_ruido_tambem_e_recusado(self):
        """O outro extremo, e o que produz literalmente o 'só tomo stop': um
        stop que o preço varre sem o cenário ter sido invalidado."""
        ok, ticks, motivo = _ns()["avaliar_tamanho_do_stop"](7550.0, 7549.5, "MESU6")
        self.assertFalse(ok)
        self.assertIn("curto demais", motivo)
        self.assertIn("ruído", motivo)

    def test_ativo_desconhecido_NAO_e_julgado(self):
        """Num contrato fora da tabela eu não sei o que é movimento normal, e
        inventar uma faixa barraria cenário bom no escuro."""
        ok, ticks, motivo = _ns()["avaliar_tamanho_do_stop"](100.0, 99.0, "XYZW9")
        self.assertTrue(ok)
        self.assertIsNone(motivo)

    def test_cada_contrato_tem_a_sua_propria_faixa(self):
        """MNQ se move mais que MES em ticks; MYM, menos. Uma faixa única
        para todos seria a mesma falta de referência com outro nome."""
        faixa = _ns()["faixa_de_stop_do_ativo"]
        self.assertNotEqual(faixa("MESU6"), faixa("MNQU6"))
        self.assertIsNotNone(faixa("MYMZ5"))
        self.assertIsNone(faixa("XYZW9"))


class TestOModeloRECEBEAReguaAntesDeEscolher(unittest.TestCase):
    """Recusar depois protege o dinheiro e desperdiça o ciclo: o cenário morre
    e o trader fica sem sugestão. Dizer a régua antes faz o modelo mirar
    dentro dela."""

    def test_a_instrucao_traz_a_faixa_do_ativo_em_ticks_e_pontos(self):
        txt = _ns()["_instrucao_de_escala_do_stop"]("MESU6")
        self.assertIn("12", txt)
        self.assertIn("60", txt)
        self.assertIn("pontos", txt)

    def test_ela_manda_dar_HOLD_em_vez_de_espremer_o_stop(self):
        """A saída errada seria o modelo encolher o stop para caber na faixa —
        trocaria 'largo demais' por 'varrido por ruído', que é o mesmo
        prejuízo pela outra ponta."""
        txt = _ns()["_instrucao_de_escala_do_stop"]("MESU6")
        self.assertIn("HOLD", txt)
        self.assertIn("espremer", txt)

    def test_sem_ativo_conhecido_nao_inventa_regua(self):
        self.assertEqual(_ns()["_instrucao_de_escala_do_stop"]("XYZW9"), "")
        self.assertEqual(_ns()["_instrucao_de_escala_do_stop"](None), "")

    def test_a_regua_esta_ligada_no_prompt_da_analise(self):
        """Função que existe e não é chamada é o `self.order_flow` de novo."""
        fonte = fonte_do_arquivo()
        self.assertIn("_instrucao_de_escala_do_stop(", fonte)
        i = fonte.index("5) STOP (crítico")
        self.assertIn("_instrucao_de_escala_do_stop", fonte[i:i + 1400])


class TestATravaEstaNoCicloAntesDoDimensionamento(unittest.TestCase):

    def test_o_stop_fora_de_escala_recusa_o_CENARIO(self):
        """E não corrige o tamanho da posição. Dimensionar em cima de um stop
        fora de escala transforma leitura ruim em posição ruim."""
        fonte = fonte_do_arquivo()
        i = fonte.index("avaliar_tamanho_do_stop(\n")
        trecho = fonte[max(0, i - 900):i + 500]
        self.assertIn("repetido = True", trecho)
        self.assertIn("📐", trecho)

    def test_ela_vem_antes_da_trava_de_distancia(self):
        fonte = fonte_do_arquivo()
        i_stop = fonte.index("_ok_stop, _tk_stop, _motivo_stop")
        i_dist = fonte.index("_ok_dist, _dist_r = avaliar_distancia_da_entrada")
        self.assertLess(i_stop, i_dist)


if __name__ == "__main__":
    unittest.main(verbosity=2)
