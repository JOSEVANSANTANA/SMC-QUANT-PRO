"""UMA POSIÇÃO REAL VIRANDO DUAS LINHAS — e o lucro contado em dobro.

20/08, ele: "note no quarto print e ele passou a duplicar, a ordem enviada
posteriormente entrou no relatório duplicada".

O que o print mostrava:

    ABERTA [ROBO] BUY MESU6 | Entrada 7761.5 | Stop 7753.5 | 25 ctr | +1.672,50
    ABERTA [ROBO] BUY MESU6 | Entrada 7761.5 | Stop 7755.0 | 25 ctr | +1.672,50

Duas linhas, o MESMO lucro, e o painel somando +3.032,50 de um dinheiro que
existia uma vez só. Repare que a segunda linha diz 25 contratos — mas a ordem
que a criou era de 1 contrato. Ela copiou a quantidade da posição real.

SÃO DOIS DEFEITOS EMPILHADOS, e os dois estão testados aqui:

  1. A ORDEM NÃO DEVERIA TER SAÍDO. Às 10:36 saiu uma ordem de 25 contratos e
     ela executou. Às 10:57, com a posição ABERTA, a política classificou o
     cenário novo como AUMENTO e imprimiu "confira o risco somado antes de
     acatar" — uma frase escrita para um humano. O modo autônomo mandou a
     segunda ordem assim mesmo. Ninguém conferiu risco nenhum.

  2. A SINCRONIZAÇÃO CONFIRMOU A MESMA POSIÇÃO DUAS VEZES. A leitura da
     plataforma mostra UMA posição de 25 contratos, e ela foi casada com as
     DUAS linhas do diário. A fusão que já existia só juntava registro
     PLATAFORMA com registro ROBÔ; aqui os dois eram do ROBÔ.
"""

import unittest

from harness import fonte_do_arquivo, funcao_inteira


class TestAumentoNaoSaiSozinho(unittest.TestCase):
    """Aumentar posição é decisão de GESTÃO, não execução de sinal: muda o
    risco total de uma operação que já está correndo, e o dimensionamento do
    Plano foi calculado para UMA entrada, não para a soma de duas."""

    def _motor(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("elif _dec == \"AUMENTO\":")
        return fonte[i - 200:i + 9000]

    def test_o_ramo_de_aumento_marca_a_flag(self):
        self.assertIn("_e_aumento = True", self._motor())

    def test_a_flag_e_zerada_a_cada_ciclo(self):
        """Estado destes vazando de um ciclo para o outro seria pior do que
        não existir."""
        fonte = fonte_do_arquivo()
        i = fonte.index("repetido = False")
        self.assertIn("_e_aumento = False", fonte[i:i + 500])

    def test_o_autonomo_NAO_executa_aumento(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("_acatar_sozinha(")
        i = fonte.index("_acatar_sozinha(", i + 10)      # a chamada do motor
        trecho = fonte[i - 1200:i + 200]
        self.assertIn("_e_aumento", trecho,
                      "a chamada autônoma tem de conhecer o aumento")

    def test_a_mensagem_NAO_promete_ordem_que_nao_vai_sair(self):
        """'Vou executar sozinha' é anúncio de futuro. Se o aumento não sai,
        essa frase vira mentira — a mesma família de erro de 19/08."""
        fonte = fonte_do_arquivo()
        i = fonte.index("_autonomo = self._modo_autonomo()")
        self.assertIn("not _e_aumento", fonte[i:i + 120])

    def test_ele_e_avisado_de_que_eu_NAO_executei(self):
        """Interruptor ligado e ordem não saindo, em silêncio, pareceria
        falha. Ele precisa saber que foi decisão, e qual."""
        fonte = fonte_do_arquivo()
        self.assertIn("NÃO executei sozinha o", fonte)
        self.assertIn("é AUMENTO de uma posição que já está", fonte)


class TestUmaPosicaoConfirmaUmaLinhaSO(unittest.TestCase):

    def _corpo(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def sincronizar_posicoes_plataforma")
        return fonte[i:i + 20000]

    def test_existe_o_controle_de_consumo(self):
        """A leitura da corretora é um RECURSO que se gasta ao ser usado."""
        corpo = self._corpo()
        self.assertIn("consumidas = set()", corpo)
        self.assertIn("consumidas.add(", corpo)

    def test_a_pendente_so_confirma_se_a_posicao_estiver_LIVRE(self):
        corpo = self._corpo()
        self.assertIn('not in consumidas', corpo)

    def test_quem_ja_esta_ABERTO_e_CONFIRMADO_tem_a_posse(self):
        """Sem a pré-passagem, a ORDEM DO ARQUIVO decidiria de quem é o
        dinheiro — que é um jeito espetacularmente ruim de decidir isso."""
        corpo = self._corpo()
        i_pre = corpo.index("consumidas = set()")
        i_laco = corpo.index("for pos in lista:", i_pre)
        pre = corpo[i_pre:i_laco]
        self.assertIn('_p.get("execucao") == "CONFIRMADA"', pre)
        self.assertIn('_p.get("status") == "ABERTA"', pre)

    def test_a_linha_duplicada_fica_SEM_P_E_L(self):
        """Copiar o P&L na segunda linha é literalmente o que duplicou os
        +1.672,50 no painel: duas linhas exibindo o mesmo lucro."""
        corpo = self._corpo()
        i = corpo.index("ja_e_de_outro")
        trecho = corpo[i:i + 900]
        self.assertIn('pos["duplicada_da_plataforma"] = True', trecho)
        self.assertIn('pos["pnl_atual"] = 0.0', trecho)


class TestOBotaoCxl(unittest.TestCase):
    """'Sair em Mkt & Cxl' É o botão de cancelar. Recusar por não reconhecer
    uma abreviação é o pior tipo de trava: tem cara de cuidado e é só
    ignorância — as ordens ficaram vivas na plataforma por causa disso."""

    def _re(self):
        import os
        import re as _re
        fonte = fonte_do_arquivo(os.path.join(
            __import__("harness").RAIZ, "tradovate_auto.py"))
        i = fonte.index("_RE_SAIR_CANCELA = re.compile(")
        corpo = fonte[i:fonte.index(")", fonte.index("re.IGNORECASE", i))]
        padrao = corpo.split("r\"")[1].split("\"")[0]
        return _re.compile(padrao, _re.IGNORECASE)

    def test_reconhece_a_abreviacao_do_menu_real(self):
        r = self._re()
        for rotulo in ("Sair em Mkt & Cxl", "Cancelar todos",
                       "Sair em Mkt & Cancelar", "Exit at Mkt & Cxl"):
            self.assertTrue(r.search(rotulo), rotulo)

    def test_sair_sem_cancelar_continua_recusado(self):
        r = self._re()
        for rotulo in ("Sair em Mkt", "Exit at Mkt", "Flatten"):
            self.assertIsNone(r.search(rotulo), rotulo)

    def test_REVERSO_e_proibido_mesmo_falando_em_cancelar(self):
        """'Reverso e Cxl' cancela E INVERTE a posição — sai do comprado e
        entra vendido, a mercado, no mesmo clique. Abrir posição que ninguém
        pediu é pior do que tudo o que este botão vem resolver."""
        import os
        import re as _re
        fonte = fonte_do_arquivo(os.path.join(
            __import__("harness").RAIZ, "tradovate_auto.py"))
        self.assertIn("_RE_SAIR_PROIBIDO", fonte)
        self.assertTrue(_re.search(r"revers", "Reverso e Cxl", _re.IGNORECASE))
        i = fonte.index("def sair_em_mercado_e_cancelar(")
        corpo = fonte[i:i + 9000]
        i_prob = corpo.index('btn.get("inverte_posicao")')
        i_canc = corpo.index('not btn.get("cancela_ordens")')
        self.assertLess(i_prob, i_canc,
                        "a proibição tem de ser avaliada ANTES da permissão")


class TestOAutoTrailFantasma(unittest.TestCase):
    """"a opção trail stop, às vezes mesmo desativada ela está funcionando".

    O ticket da Tradovate GUARDA o que foi digitado antes. Bastava UMA ordem
    com trail ligado para todas as seguintes herdarem aquele trail."""

    def _fonte_tv(self):
        import os
        return fonte_do_arquivo(os.path.join(
            __import__("harness").RAIZ, "tradovate_auto.py"))

    def _corpo(self):
        # A FUNÇÃO INTEIRA, não 9000 bytes a partir do `def`. A correção de
        # 31/08 acrescentou umas quarenta linhas no meio dela e empurrou o
        # trecho procurado para fora da janela — régua, não regra.
        return funcao_inteira(self._fonte_tv(), "configurar_atm")

    def test_desligado_ZERA_os_campos_em_vez_de_ignorar(self):
        corpo = self._corpo()
        i = corpo.index("else:", corpo.index("if trailing:"))
        trecho = corpo[i:i + 1400]
        self.assertIn("ROTULO_TRAIL_ACIONAR, 0, 0", trecho)
        self.assertIn("ROTULO_TRAIL_FREQ, 0, 0", trecho)

    def test_campo_de_trail_NAO_pode_recusar_a_ordem(self):
        """Se os campos do trail não existirem neste layout, exigir que eles
        confiram bloqueia a operação por causa de um extra — trocar um
        problema pequeno por um grande.

        A REGRA VALE NOS DOIS SENTIDOS AGORA. Antes ela só valia quando o
        trail estava sendo ZERADO (`opcional = limpando_trail and ...`), e por
        isso, em 31/08, com o trail LIGADO, dois cenários aprovados morreram
        com 'OCORRENCIA_INEXISTENTE' sem nunca virar ordem. Este teste
        travava a metade errada da regra."""
        corpo = funcao_inteira(self._fonte_tv(), "configurar_atm")
        self.assertIn("opcional = i >= n_obrigatorios", corpo)
        self.assertNotIn("opcional = limpando_trail and", corpo)
        i = corpo.index("opcional = i >= n_obrigatorios")
        trecho = corpo[i:i + 1600]
        self.assertIn("if opcional:", trecho)
        self.assertIn("continue", trecho)

    def test_os_TRES_obrigatorios_continuam_derrubando_a_ordem(self):
        """Unidade, alvo e stop do bracket são o risco da operação. Afrouxar o
        trail não pode ter afrouxado estes."""
        corpo = funcao_inteira(self._fonte_tv(), "configurar_atm")
        self.assertIn("n_obrigatorios = 3", corpo)
        self.assertIn("return False", corpo)

    def test_meia_configuracao_de_trail_e_ZERADA_antes_de_enviar(self):
        """Um stop que anda com gatilho errado tira a operação na hora errada,
        sozinho. Se um campo do trail falhou, os que entraram são apagados —
        e se nem isso der certo, aí sim a ordem não vai."""
        corpo = funcao_inteira(self._fonte_tv(), "configurar_atm")
        self.assertIn("pior que trail nenhum", corpo)
        i = corpo.index("trail_falhou and trailing")
        trecho = corpo[i:i + 1600]
        self.assertIn("ROTULO_TRAIL_ACIONAR, 0, 0", trecho)
        self.assertIn("return False", trecho)

    def test_o_log_diz_que_o_trail_foi_zerado(self):
        self.assertIn("AUTO TRAIL zerado",
                      funcao_inteira(self._fonte_tv(), "configurar_atm"))


if __name__ == "__main__":
    unittest.main()
