"""O PAINEL DIZIA +US$2.212,20. A CORRETORA DIZIA (2.113,97). A TERCEIRA MENTIRA.

20/08, ele: "NOTE NO PRIMEIRO PRINT QUE AS OPERACOES DERAM PREJUIZO, EM
CONTRAPARTIDA NO PAINEL DE TRADING DA FERRAMENTA APARECE ALI COMO RESULTADO...
ISSO NAO PODE OCORRER EM HIPOTESE ALGUMA PORQUE VAI CONVERSAR DIRETAMENTE COM A
GESTAO DE RISCO E PLANO DE TRADING, COM INFORMACOES DIVERGENTES A CONTA NAO
BATE".

Os números, lado a lado:

    Tradovate ....... CAPITAL 47.886,03  ·  P/L TOTAL (2.113,97)
    SMC Quant Pro ... RESULTADO DO DIA +2.212,20  ·  WIN RATE 100% (2 ops)

As duas "vitórias" do diário (+2.071,20 e +141,00) somam exatamente os
+2.212,20 do painel. Num dia de PERDA.

A CAUSA, achada no código: `exigir_confirmacao_plataforma` protegia só a
transição PENDENTE -> ABERTA. O fechamento ABERTA -> FECHADA decidia "alvo ou
stop" olhando o PREÇO LIDO, e o preço é lido de 5 em 5 minutos. Uma das
vitórias foi registrada 15 minutos depois da entrada: três ciclos cegos. O
preço podia ter tocado 7762,50, o OCO da corretora ter fechado a operação ali,
e o mercado depois subir até 7785 — eu veria só a última leitura e cravaria
ALVO.

E o ponto que resolve: quando a ordem está na plataforma, stop e alvo são um
OCO DELA. Quem sabe qual perna preencheu é a corretora. Nunca eu, olhando o
gráfico de longe.

POR QUE ISTO É PIOR QUE UM RELATÓRIO ERRADO: o resultado daqui alimenta o freio
de perda diária, o limite de stops seguidos e o dimensionamento. Um dia de
perda registrado como ganho DESARMA as três travas ao mesmo tempo, no minuto
em que elas mais precisavam agir.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _f():
    return carregar(["decidir_desfecho_da_posicao"])["decidir_desfecho_da_posicao"]


def _pos(**kw):
    base = dict(direcao="BUY", entry=7770.0, stop=7762.5, tp2=7785.0)
    base.update(kw)
    return base


class TestOAlvoQueEuNaoPossoAFIRMAR(unittest.TestCase):

    def test_ordem_na_plataforma_e_preco_no_alvo_vira_INCERTO(self):
        """O caso exato de 20/08. O OCO é da corretora; entre duas leituras
        minhas cabe a operação inteira."""
        desfecho, motivo = _f()(_pos(enviada_plataforma=True), 7786.0, True)
        self.assertEqual(desfecho, "INCERTO")
        self.assertIn("NÃO SEI", motivo)

    def test_se_o_preco_JA_PASSOU_DO_STOP_antes_o_alvo_nao_vale(self):
        """Carimbo barato que sobrevive entre ciclos: se o mercado já esteve
        além do stop, o alvo alcançado depois pode ter chegado com a operação
        já encerrada."""
        desfecho, motivo = _f()(_pos(tocou_stop_em_algum_ciclo=True), 7786.0, False)
        self.assertEqual(desfecho, "INCERTO")
        self.assertIn("STOP", motivo)

    def test_sem_plataforma_o_preco_AINDA_decide(self):
        """Sem ordem na corretora, o preço lido é tudo o que existe — e aí
        afirmar é honesto. Transformar TUDO em 'não sei' seria o erro oposto,
        e ele já me avisou disso: 'dizer não sei onde eu sei também é erro'."""
        desfecho, _ = _f()(_pos(), 7786.0, False)
        self.assertEqual(desfecho, "ALVO")

    def test_o_STOP_continua_sendo_afirmado(self):
        """Assimetria deliberada: o stop é o pior desfecho possível do cenário.
        Registrar a perda quando ela talvez não tenha ocorrido freia CEDO
        demais — nunca tarde demais. É o lado seguro do erro."""
        desfecho, _ = _f()(_pos(enviada_plataforma=True), 7760.0, True)
        self.assertEqual(desfecho, "STOP")

    def test_preco_no_meio_nao_fecha_nada(self):
        self.assertEqual(_f()(_pos(enviada_plataforma=True), 7775.0, True)[0], "NADA")

    def test_posicao_sem_stop_nao_e_avaliada(self):
        self.assertEqual(_f()(_pos(stop=None), 7786.0, False)[0], "NADA")

    def test_short_tambem(self):
        """A regra não pode valer só para compra."""
        p = dict(direcao="SELL", entry=7770.0, stop=7777.5, tp2=7755.0,
                 enviada_plataforma=True)
        self.assertEqual(_f()(p, 7754.0, True)[0], "INCERTO")
        self.assertEqual(_f()(p, 7778.0, True)[0], "STOP")


class TestOIncertoNAOVIRANUMERO(unittest.TestCase):
    """Sem número é o ponto todo. `pnl_final = None` é o que mantém este
    desfecho fora do resultado do dia, do win rate e do freio."""

    def _corpo(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def atualizar_posicoes_com_preco")
        return fonte[i:i + 9000]

    def test_incerto_grava_pnl_final_None(self):
        corpo = self._corpo()
        i = corpo.index('if desfecho == "INCERTO":')
        trecho = corpo[i:i + 700]
        self.assertIn('pos["pnl_final"] = None', trecho)
        self.assertIn('pos["desfecho_incerto"] = True', trecho)

    def test_o_fechamento_passa_pela_funcao_de_decisao(self):
        """Se alguém voltar a decidir alvo/stop no meio do laço, a trava some
        junto e o bug de 20/08 volta inteiro."""
        corpo = self._corpo()
        self.assertIn("decidir_desfecho_da_posicao(", corpo)
        self.assertIn('pos["tocou_stop_em_algum_ciclo"] = True', corpo)

    def test_todas_as_somas_de_resultado_ignoram_pnl_final_None(self):
        """Regressão que eu poderia ter criado: se UMA agregação somasse
        pnl_final sem checar None, o painel quebraria com TypeError — ou pior,
        trataria None como zero e o buraco viraria 'empate'."""
        fonte = fonte_do_arquivo()
        alvo = 'status") == "FECHADA"'
        for i, linha in enumerate(fonte.splitlines()):
            if alvo not in linha:
                continue
            janela = "\n".join(fonte.splitlines()[i:i + 3])
            self.assertIn('pnl_final") is not None', janela,
                          f"linha {i + 1} agrega FECHADA sem checar pnl_final")

    def test_o_evento_INCERTO_tem_tratamento_proprio_na_interface(self):
        """Sem este ramo, o INCERTO cairia no `else` que formata
        `pos['pnl_final']:+.2f` — e estouraria TypeError com None."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tratar_evento_posicao")
        corpo = fonte[i:i + 6000]
        i_inc = corpo.index('elif tipo == "INCERTO":')
        i_else = corpo.index("        else:", i_inc)
        self.assertLess(i_inc, i_else, "o INCERTO tem de ser tratado ANTES do else")
        self.assertIn("NÃO SEI COMO ESTA OPERAÇÃO TERMINOU", corpo)


class TestOBuracoAPARECE(unittest.TestCase):
    """Omitir em silêncio é a mesma doença por outro caminho: o painel mostraria
    um total limpo enquanto a corretora mostra outro."""

    def test_os_stats_contam_as_incertas(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _computar_stats_plano")
        corpo = fonte[i:i + 4000]
        self.assertIn("incertas", corpo)
        self.assertIn("desfecho_incerto", corpo)

    def test_o_painel_avisa_que_o_resultado_esta_INCOMPLETO(self):
        fonte = fonte_do_arquivo()
        self.assertIn("SEM desfecho confirmado", fonte)
        self.assertIn("INCOMPLETO", fonte)


class TestAGeminiNAOSaiDaLeituraDeGrafico(unittest.TestCase):
    """Ele pediu o OpenRouter como inteligência principal, e é o que está feito
    para CONVERSA. Mas o motor não conversa: manda um PRINT e pede níveis.

    Um modelo de texto que recebesse essa pergunta sem enxergar a imagem
    responderia com confiança sobre um gráfico que não viu, devolvendo entrada,
    stop e alvo inventados — que viram ordem de verdade no modo autônomo. É a
    única família de erro deste programa com dinheiro do outro lado."""

    def test_turno_COM_anexo_nao_passa_pelo_prioritario(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("PROVEDORES_PRIORITARIOS")
        corpo = fonte[fonte.index("def _chat_worker"):]
        i_uso = corpo.index("PROVEDORES_PRIORITARIOS")
        trecho = corpo[max(0, i_uso - 600):i_uso + 300]
        self.assertIn("if not anexo:", trecho,
                      "a prioridade de texto não pode receber turno com imagem")


if __name__ == "__main__":
    unittest.main()
