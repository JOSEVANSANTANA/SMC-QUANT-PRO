"""A OPERAÇÃO FECHOU NA PLATAFORMA E O PAINEL FICOU PRESO EM "PENDENTE".

23/08, 00:36. O print da Tradovate mostrava a operação inteira, concluída:

    #84649004 Comprar 8 MESU6 LMT em 7538.50 - Filled - 8/8
    #84649011 Vender  8 MESU6 LMT em 7549.25 - Filled - 8/8
    #84649013 Vender  8 MESU6 STP em 7541.00 - Cancelado - 0/8

Entrada preenchida, alvo preenchido, stop cancelado pelo OCO. US$430 de lucro
(10,75 pontos × US$5 × 8 contratos). E o painel do app, na mesma hora:

    ⏳ PENDENTE [ROBO] BUY MESU6 | Aguardando preço tocar 7538.5 | 8 ctr

O ciclo marcava US$ 0,00, o win rate 0%, o drawdown 0. Nada tinha se movido.

A CAUSA
-------
A reconciliação olhava a POSIÇÃO ATUAL da corretora. A operação entrou e saiu
entre dois ciclos de análise, e quando o robô foi olhar, a posição já era
zero. Sem posição aberta, a PENDENTE nunca virou ABERTA — e, não estando
ABERTA, nunca virou FECHADA. Ficou pendurada para sempre.

Posição é um retrato do AGORA: ela some quando a operação acaba, justamente
no instante em que o diário mais precisa dela. O extrato de ordens é memória:
sobrevive ao fechamento e traz o preço de execução de cada perna.

O QUE ESTES TESTES GUARDAM
--------------------------
A regra é medida numa função PURA, sem corretora e sem tela, porque decidir
que uma operação fechou — e por quanto — é a conta que vira resultado do dia,
win rate, drawdown e o freio de perda. Errar aqui contamina todos eles de uma
vez, que foi o defeito de 11/08 com o resultado contado em dobro.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _f():
    return carregar(["desfecho_pelas_execucoes"])["desfecho_pelas_execucoes"]


def _ordem(lado, preco, estado="executada", exec_=8, total=8, ativo="MESU6"):
    return {"id": "#846", "estado": estado, "lado": lado, "preco": preco,
            "ativo": ativo, "executados": exec_, "total": total}


POS = {"direcao": "BUY", "ativo": "MESU6", "contratos": 8, "vpp": 5.0,
       "status": "PENDENTE"}


class TestOCasoRealDe23De08(unittest.TestCase):

    def test_a_operacao_do_print_fecha_com_430_dolares(self):
        """O número que o painel deveria ter mostrado e não mostrou."""
        st, saida, pnl, _ = _f()(POS, [
            _ordem("BUY", 7538.50),
            _ordem("SELL", 7549.25),
            _ordem("SELL", 7541.00, estado="cancelada", exec_=0)])
        self.assertEqual(st, "FECHADA")
        self.assertEqual(saida, 7549.25)
        self.assertEqual(pnl, 430.00)      # 10,75 pts × US$5 × 8 ctr

    def test_a_ordem_cancelada_nao_conta_como_saida(self):
        """O stop foi CANCELADO pelo OCO, não executado. Tratá-lo como saída
        fecharia a operação no preço errado — e com o sinal errado."""
        _, saida, _, _ = _f()(POS, [
            _ordem("BUY", 7538.50),
            _ordem("SELL", 7549.25),
            _ordem("SELL", 7541.00, estado="cancelada", exec_=0)])
        self.assertNotEqual(saida, 7541.00)

    def test_so_a_entrada_preenchida_vira_ABERTA_e_nao_FECHADA(self):
        st, _, _, motivo = _f()(POS, [_ordem("BUY", 7538.50)])
        self.assertEqual(st, "ABERTA")
        self.assertIn("7538.5", motivo)


class TestAContaBateNosDoisSentidos(unittest.TestCase):

    def test_compra_no_alvo_e_no_stop(self):
        f = _f()
        _, _, ganho, _ = f(POS, [_ordem("BUY", 7538.50), _ordem("SELL", 7549.25)])
        _, _, perda, _ = f(POS, [_ordem("BUY", 7538.50), _ordem("SELL", 7531.00)])
        self.assertEqual(ganho, 430.00)
        self.assertEqual(perda, -300.00)

    def test_venda_no_alvo_e_no_stop(self):
        f = _f()
        pos = {"direcao": "SELL", "ativo": "MESU6", "contratos": 4, "vpp": 5.0}
        _, _, ganho, _ = f(pos, [_ordem("SELL", 7550.0, exec_=4, total=4),
                                 _ordem("BUY", 7540.0, exec_=4, total=4)])
        _, _, perda, _ = f(pos, [_ordem("SELL", 7550.0, exec_=4, total=4),
                                 _ordem("BUY", 7556.0, exec_=4, total=4)])
        self.assertEqual(ganho, 200.00)
        self.assertEqual(perda, -120.00)

    def test_saida_pelo_trail_acima_da_entrada_da_LUCRO(self):
        """No print de 23/08 o stop estava em 7541,00 com entrada em 7538,50 —
        ACIMA dela, porque o auto trail já o tinha subido. Se essa saída fosse
        tratada como prejuízo por ser 'o stop', o diário registraria perda
        numa operação que ganhou."""
        _, _, pnl, _ = _f()(POS, [_ordem("BUY", 7538.50), _ordem("SELL", 7541.00)])
        self.assertEqual(pnl, 100.00)


class TestOQueNAOPodeVirarConclusao(unittest.TestCase):
    """Ausência de leitura nunca é resultado — a regra mais antiga da casa."""

    def test_sem_extrato_nao_conclui_nada(self):
        self.assertEqual(_f()(POS, [])[0], None)

    def test_preenchimento_PARCIAL_nao_vira_posicao_cheia(self):
        """'3/8' com o diário achando que são 8 contratos calcularia um P&L
        quase três vezes maior que o real."""
        self.assertEqual(_f()(POS, [_ordem("BUY", 7538.50, exec_=3)])[0], None)

    def test_ordem_de_OUTRO_ativo_nao_fecha_esta_posicao(self):
        """MESU6 e MNQU6 no mesmo layout: fechar uma com o extrato da outra é
        a família de erro que custou a ordem de 20/08."""
        st, _, _, _ = _f()(POS, [_ordem("BUY", 7538.50),
                                 _ordem("SELL", 29500.0, ativo="MNQU6")])
        self.assertEqual(st, "ABERTA")     # a entrada, sim; a saída, não

    def test_sem_preco_no_extrato_nao_inventa_resultado(self):
        st, _, _, _ = _f()(POS, [_ordem("BUY", None), _ordem("SELL", None)])
        self.assertIsNone(st)

    def test_posicao_sem_contratos_nao_gera_pnl(self):
        pos = dict(POS, contratos=0)
        self.assertIsNone(_f()(pos, [_ordem("BUY", 7538.50),
                                     _ordem("SELL", 7549.25)])[0])


class TestOLacoDeTempoRealExisteEEDisciplinado(unittest.TestCase):

    def _corpo(self, nome, tamanho=4200):
        fonte = fonte_do_arquivo()
        i = fonte.index(nome)
        return fonte[i:i + tamanho]

    def test_o_laco_roda_sozinho_e_se_reagenda(self):
        corpo = self._corpo("def _loop_reconciliar_extrato")
        self.assertIn("self.after(6000, self._loop_reconciliar_extrato)", corpo)

    def test_o_laco_e_ligado_na_inicializacao(self):
        """Um laço que existe e nunca é chamado é o `self.order_flow` de
        novo: código correto, morto no arquivo."""
        fonte = fonte_do_arquivo()
        self.assertIn("self.after(6000, self._loop_reconciliar_extrato)", fonte)
        # duas ocorrências: a que arma e a que se reagenda
        self.assertGreaterEqual(
            fonte.count("_loop_reconciliar_extrato"), 3)

    def test_sem_posicao_viva_ele_nao_toca_na_plataforma(self):
        """Ler o extrato a cada seis segundos com o diário limpo seria
        gastar CDP à toa — e foi excesso de chamada que derrubou uma ordem
        em 20/08."""
        corpo = self._corpo("def _reconciliar_pelo_extrato")
        self.assertIn("if not minhas:", corpo)
        i_minhas = corpo.index("if not minhas:")
        i_leitura = corpo.index("ler_execucoes")
        self.assertLess(i_minhas, i_leitura,
                        "a saída por 'nada vivo' tem de vir ANTES da leitura")

    def test_leitura_falha_nao_mexe_no_diario(self):
        corpo = self._corpo("def _reconciliar_pelo_extrato")
        self.assertIn('if not extrato.get("ok"):', corpo)

    def test_o_painel_e_atualizado_na_hora(self):
        """Foi o pedido dele: 'nem atualização no acompanhamento da ordem no
        painel de trading'. Gravar no disco sem redesenhar deixaria a tela
        mentindo até o próximo ciclo."""
        corpo = self._corpo("def _reconciliar_pelo_extrato")
        self.assertIn("self._atualizar_dashboard()", corpo)
        self.assertIn("self._assin_posicoes = None", corpo,
                      "sem invalidar a assinatura, o redesenho é descartado "
                      "por 'nada mudou'")


if __name__ == "__main__":
    unittest.main(verbosity=2)
