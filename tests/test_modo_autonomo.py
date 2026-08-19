"""A ferramenta acata sozinha — e o que continua valendo quando ela acata.

19/08, ele, em maiúsculas: "CERTIFIQUE-SE DE DEIXAR TOTALMENTE AUTONOMA SEM A
NECESSIDADE DE ACATAR OU NAO, DESDE QUE NA GESTAO DA FERRAMENTA A AUTOMACAO
TRADOVATE ESTEJA ATIVADA". Ambiente simulado, riscos declarados por escrito.

O QUE SOME É UM PASSO, NÃO UMA TRAVA — e isso precisa estar escrito num teste,
porque "autônomo" é fácil de confundir com "sem freio". Quando uma sugestão
chega ao ponto de virar ordem, ela já passou, tudo em código e nesta ordem:

  • piso de qualidade (R:R mínimo e probabilidade mínima),
  • desconto por evento macro recém-publicado,
  • correção pelo aprendizado das operações dele,
  • política de posição aberta,
  • freio: perda diária, stops seguidos e teto de operações do dia,
  • anti-repetição do mesmo setup.

O ACATAR nunca foi uma dessas travas — era a confirmação humana em cima delas,
e é exatamente ela que ele está mandando tirar. A única que não se negocia é o
DIMENSIONAMENTO: zero contrato não é "envia um", é "hoje não".
"""

import unittest

from harness import carregar, fonte_do_arquivo


class TestADecisaoDeExecutarSozinha(unittest.TestCase):

    def _ns(self):
        return carregar(["decidir_execucao_autonoma"])

    def test_automacao_ligada_e_contratos_na_mao_EXECUTA(self):
        ns = self._ns()
        executa, motivo = ns["decidir_execucao_autonoma"](True, False, 2)
        self.assertTrue(executa)
        self.assertIn("sozinha", motivo)

    def test_automacao_desligada_volta_a_esperar_o_ACATAR(self):
        """Quem não ligou a automação não pode receber uma ordem de surpresa."""
        ns = self._ns()
        executa, motivo = ns["decidir_execucao_autonoma"](False, False, 2)
        self.assertFalse(executa)
        self.assertIn("ACATAR", motivo)

    def test_ZERO_contrato_nao_vira_ordem_de_um(self):
        """Zero contrato é o plano dizendo 'hoje não' — drawdown consumido,
        margem insuficiente ou stop curto demais. Arredondar para 1 seria
        furar a única trava que sobrou."""
        ns = self._ns()
        for n in (0, None, -1, "", "abc"):
            executa, motivo = ns["decidir_execucao_autonoma"](True, False, n)
            self.assertFalse(executa, repr(n))
            self.assertIn("ZERO", motivo)

    def test_o_motivo_do_limite_aparece_na_explicacao(self):
        ns = self._ns()
        _, motivo = ns["decidir_execucao_autonoma"](
            True, False, 0, "drawdown do dia consumido")
        self.assertIn("drawdown do dia consumido", motivo)

    def test_modo_teste_executa_o_fluxo_mas_avisa_que_nao_envia(self):
        ns = self._ns()
        executa, motivo = ns["decidir_execucao_autonoma"](True, True, 2)
        self.assertTrue(executa)
        self.assertIn("TESTE", motivo)
        self.assertIn("NÃO clico em Enviar", motivo)

    def test_modo_teste_com_automacao_desligada_continua_parado(self):
        ns = self._ns()
        executa, _ = ns["decidir_execucao_autonoma"](False, True, 2)
        self.assertFalse(executa)


class TestAsTravasCONTINUAMValendo(unittest.TestCase):
    """O ponto que este arquivo existe para provar."""

    def _fonte(self):
        return fonte_do_arquivo()

    def test_o_autonomo_acata_DEPOIS_de_todos_os_filtros(self):
        """O gancho fica dentro do bloco que só roda quando o cenário passou
        no piso de qualidade, no freio e na política de posição aberta. Se ele
        subisse para antes disso, a ferramenta operaria o que ela mesma
        rejeitou."""
        fonte = self._fonte()
        i = fonte.index("_acatar_sozinha(")
        # o gancho de execução, não a definição do método
        i = fonte.index("self._acatar_sozinha(", i)
        antes = fonte[:i]
        self.assertIn("freio_de_sugestoes()", antes)
        self.assertIn("avaliar_piso_de_qualidade(", antes)
        self.assertIn("politica_com_posicao_aberta(", antes)
        # e depois do registro do sinal, que é o que dá o id
        self.assertIn("novo_sinal_id = registrar_novo_sinal_log(", antes)

    def test_o_freio_continua_no_codigo_e_nao_foi_afrouxado(self):
        ns = carregar(["freio_de_sugestoes"],
                      stubs={"plano_da_conta_ativa": lambda: {
                                 "drawdown_maximo": 100, "max_stops_seguidos": 2,
                                 "cooldown_stop_min": 30, "max_operacoes_dia": 6},
                             "operacoes_fechadas_hoje": lambda: [
                                 {"pnl_final": -60.0, "data_fechamento": ""},
                                 {"pnl_final": -60.0, "data_fechamento": ""}],
                             "posicoes_do_ciclo": lambda: []})
        pode, motivo = ns["freio_de_sugestoes"]()
        self.assertFalse(pode, "o teto de perda diária tem de continuar parando o dia")
        self.assertTrue(motivo)

    def test_acata_pelo_MESMO_caminho_do_botao(self):
        """Um atalho próprio aqui viraria um segundo caminho para manter, e é
        sempre o segundo caminho que fica para trás."""
        fonte = self._fonte()
        i = fonte.index("def _acatar_sozinha(")
        bloco = fonte[i:i + 2000]
        self.assertIn("_registrar_decisao(", bloco)
        self.assertIn("ACATOU_COMPRA", bloco)
        self.assertIn("ACATOU_VENDA", bloco)

    def test_volta_para_a_thread_da_interface(self):
        """`_registrar_decisao` mexe no dashboard, e o Tk não aceita isso
        vindo da thread do motor — daria pane no meio do pregão."""
        fonte = self._fonte()
        i = fonte.index("def _acatar_sozinha(")
        self.assertIn("self.after(0,", fonte[i:i + 2000])


class TestOQueEleVEQuandoElaOperaSozinha(unittest.TestCase):
    """Uma ordem que aparece na plataforma sem uma linha em lugar nenhum
    dizendo por quê é a pior coisa que esta ferramenta poderia fazer."""

    def _fonte(self):
        return fonte_do_arquivo()

    def test_o_whatsapp_para_de_perguntar_o_que_ja_foi_decidido(self):
        """Mandar 'deseja acatar?' para o celular de alguém cuja ordem já está
        na plataforma é pior que não mandar nada."""
        fonte = self._fonte()
        self.assertIn("EXECUTADO AUTOMATICAMENTE", fonte)
        i = fonte.index("EXECUTADO AUTOMATICAMENTE")
        bloco = fonte[i - 600:i + 900]
        self.assertIn("_modo_autonomo()", bloco)
        self.assertIn("Deseja acatar este cenário", bloco,
                      "o texto antigo tem de continuar existindo para o modo "
                      "assistido")

    def test_o_interruptor_DIZ_que_opera_sozinha(self):
        """Ele deixou de significar 'envia quando você acatar'. Quem ligar
        achando que é o de antes descobriria vendo uma ordem aparecer."""
        fonte = self._fonte()
        self.assertIn("A FERRAMENTA OPERA SOZINHA", fonte)
        self.assertIn("OPERA SOZINHA — acata e envia", fonte)

    def test_ligar_a_automacao_avisa_no_registro_e_na_conversa(self):
        fonte = self._fonte()
        i = fonte.index("def _tv_salvar_prefs(")
        bloco = fonte[i:i + 2000]
        self.assertIn("MODO AUTÔNOMO ATIVO", bloco)
        self.assertIn("_chat_feed(", bloco)

    def test_o_motor_diz_em_que_modo_subiu(self):
        """Ligar o motor sem saber se ele vai sugerir ou EXECUTAR é a única
        dúvida que não pode existir aqui."""
        fonte = self._fonte()
        i = fonte.index("ROBÔ SMC INICIADO COM MÓDULO DE APRENDIZADO")
        bloco = fonte[i:i + 1800]
        self.assertIn("MODO AUTÔNOMO LIGADO", bloco)
        self.assertIn("MODO ASSISTIDO", bloco)

    def test_o_aviso_de_tela_nao_oferece_botao_de_decidir_o_que_ja_foi(self):
        fonte = self._fonte()
        self.assertIn("sinal_id=None if _autonomo else novo_sinal_id", fonte)

    def test_ela_avisa_ANTES_de_mandar_a_ordem(self):
        """Se o envio falhar, o aviso já existe. O contrário deixaria ordem na
        plataforma sem registro nenhum do porquê."""
        fonte = self._fonte()
        i_wpp = fonte.index("enviar_relatorio_whatsapp(mensagem_wpp, screenshot, self.log)")
        i_exec = fonte.index("self._acatar_sozinha(")
        self.assertLess(i_wpp, i_exec)

    def test_quando_NAO_executa_ele_fica_sabendo_o_motivo(self):
        fonte = self._fonte()
        i = fonte.index("def _acatar_sozinha(")
        bloco = fonte[i:i + 2000]
        self.assertIn("NÃO executei sozinha", bloco)


class TestOInterruptorEUmSo(unittest.TestCase):
    def test_o_modo_autonomo_depende_da_automacao_tradovate(self):
        """Dois interruptores para uma decisão só é a forma mais confiável de
        alguém ligar um e achar que ligou os dois."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _modo_autonomo(")
        bloco = fonte[i:i + 700]
        self.assertIn("tv_auto_var", bloco)
        self.assertIn("TRADOVATE_DISPONIVEL", bloco)


if __name__ == "__main__":
    unittest.main()
