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
                             "operacoes_fechadas_hoje": lambda **_: [
                                 {"pnl_final": -60.0, "data_fechamento": ""},
                                 {"pnl_final": -60.0, "data_fechamento": ""}],
                             # O freio deixou de somar o aberto por
                             # `posicoes_do_ciclo` em 22/08: risco não enxerga
                             # ciclo, senão reiniciar a contagem de meta apaga
                             # prejuízo do teto de perda diária.
                             "carregar_posicoes": lambda: [],
                             "_e_da_conta_ativa": lambda p: True,
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
        # O texto mudou de tempo verbal na v2.46.2: ele sai ANTES do envio, e
        # dizer "EXECUTADO" ali era afirmar um fato que ainda não existia.
        self.assertIn("EXECUTANDO SOZINHA", fonte)
        i = fonte.index("EXECUTANDO SOZINHA")
        bloco = fonte[i - 900:i + 900]
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


class TestNaoEmpilharOrdemNaCorretora(unittest.TestCase):
    """A pergunta dele, 19/08, olhando o comprovante da ordem que acabou de
    sair: "depois que ele envia a ordem, aparecem aquelas informacoes ali do
    lado, se surgir outra sugestao, ele esta programado para voltar ali na
    seta para preencher novamente?"

    Está — `_garantir_formulario` detecta o comprovante e clica no ← antes de
    escrever qualquer coisa. E era exatamente esse o problema: ele voltaria e
    preencheria, sem que NADA olhasse para a ordem que ficou viva lá.

    `posicao_aberta_no_ativo` só enxerga status 'ABERTA'. Uma limitada
    esperando o preço tocar a entrada está 'PENDENTE' — invisível para a
    política. No autônomo isso empilha: 30 contratos esperando em 7704,25 e,
    dez minutos depois, mais 30 em 7699,50, cada uma com o seu bracket. Se as
    duas preencherem, ele fica com o DOBRO do risco que o Plano dimensionou, e
    ninguém decidiu isso."""

    def _ns(self, posicoes):
        return carregar(["ordem_enviada_e_viva_no_ativo",
                         "politica_com_posicao_aberta",
                         "posicao_aberta_no_ativo"],
                        stubs={"carregar_posicoes": lambda: list(posicoes),
                               "_e_da_conta_ativa": lambda p: True,
                               "plano_da_conta_ativa": lambda: {
                                   "com_posicao_aberta": "alerta"}})

    def _pendente(self, **kw):
        base = {"status": "PENDENTE", "ativo": "MESU6", "direcao": "SELL",
                "entry": 7704.25, "contratos": 30, "origem": "ROBO",
                "enviada_plataforma": True}
        base.update(kw)
        return base

    def test_ordem_ja_na_corretora_BLOQUEIA_a_proxima(self):
        ns = self._ns([self._pendente()])
        dec, pos, motivo = ns["politica_com_posicao_aberta"]("SELL", "MESU6")
        self.assertEqual(dec, "ORDEM_VIVA")
        self.assertIn("7704.25", motivo)
        self.assertIn("empilharia", motivo)

    def test_bloqueia_tambem_o_lado_CONTRARIO(self):
        """Duas limitadas opostas vivas ao mesmo tempo é o pior dos dois
        mundos: quem preencher primeiro decide o trade."""
        ns = self._ns([self._pendente()])
        dec, _, _ = ns["politica_com_posicao_aberta"]("BUY", "MESU6")
        self.assertEqual(dec, "ORDEM_VIVA")

    def test_pendente_que_NAO_foi_para_a_plataforma_nao_bloqueia(self):
        """Com a automação desligada, a pendente é só um registro meu — e um
        registro meu não ocupa lugar na corretora."""
        ns = self._ns([self._pendente(enviada_plataforma=False)])
        self.assertIsNone(ns["ordem_enviada_e_viva_no_ativo"]("MESU6"))
        dec, _, _ = ns["politica_com_posicao_aberta"]("SELL", "MESU6")
        self.assertEqual(dec, "LIVRE")

    def test_ordem_de_OUTRO_ativo_nao_bloqueia(self):
        ns = self._ns([self._pendente(ativo="MNQU6")])
        dec, _, _ = ns["politica_com_posicao_aberta"]("SELL", "MESU6")
        self.assertEqual(dec, "LIVRE")

    def test_MESU6_e_MES_sao_o_mesmo_instrumento(self):
        ns = self._ns([self._pendente(ativo="MES")])
        self.assertIsNotNone(ns["ordem_enviada_e_viva_no_ativo"]("MESU6"))

    def test_ordem_ja_executada_ou_cancelada_nao_bloqueia(self):
        for st in ("ABERTA", "CANCELADA", "FECHADA"):
            ns = self._ns([self._pendente(status=st)])
            self.assertIsNone(ns["ordem_enviada_e_viva_no_ativo"]("MESU6"), st)

    def test_ativo_desconhecido_nao_bloqueia_tudo(self):
        ns = self._ns([self._pendente()])
        for a in ("", None, "DESCONHECIDO"):
            self.assertIsNone(ns["ordem_enviada_e_viva_no_ativo"](a), repr(a))

    def test_o_motor_SEGURA_a_sugestao_e_diz_como_destravar(self):
        """'Segurei a sugestão' sem saída vira ferramenta muda no pregão."""
        fonte = fonte_do_arquivo()
        self.assertIn('_dec == "ORDEM_VIVA"', fonte)
        i = fonte.index('_dec == "ORDEM_VIVA"')
        bloco = fonte[i:i + 1200]
        self.assertIn("repetido = True", bloco)
        self.assertIn("cancele a ordem antiga", bloco)

    def test_o_carimbo_so_e_posto_quando_a_corretora_RECEBEU(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _marcar_ordem_na_corretora(")
        self.assertIn('p["enviada_plataforma"] = True', fonte[i:i + 1200])
        j = fonte.index("self._marcar_ordem_na_corretora(sinal_id)")
        bloco = fonte[j - 800:j]
        self.assertIn("not dry", bloco, "modo teste não pode carimbar")
        self.assertIn('res.get("incerto")', bloco,
                      "se eu NÃO SEI se saiu, tenho de tratar como se tivesse "
                      "saído — empilhar em cima do que existe é pior")

    def test_cancelar_no_diario_NAO_cancela_na_corretora_e_isso_e_dito(self):
        """'Cancelada' no meu registro com a ordem viva na plataforma é a pior
        mentira que este programa poderia contar."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def cancelar_pendentes_do_sinal(")
        bloco = fonte[i:i + 1800]
        self.assertIn("_canceladas_ainda_na_corretora", bloco)
        self.assertIn("JÁ ESTAVA NA TRADOVATE", fonte)
        j = fonte.index("JÁ ESTAVA NA TRADOVATE")
        self.assertIn("CANCELE ESSA ORDEM NA PLATAFORMA", fonte[j:j + 700])


class TestElaNaoPodeDizerQueFezOQueNaoFEZ(unittest.TestCase):
    """19/08, ele: "ela esta mentindo"; "nao pode falar que fez e nao ter
    feito"; "certifique-se de manter ela verdadeira, sem inventar nada".

    Ele tinha razão duas vezes, e as duas são minhas.

    MENTIRA 1 — "CANCELADA sem executar (stop rompido antes da entrada)".
    A ordem TINHA ido para a Tradovate (Vender 30 @ 7704.25 com bracket), o
    preço entrou, bateu o stop e saiu — tudo entre duas leituras de 5 minutos.
    O capital da conta caiu de 50.000,00 para 49.495,05: a operação existiu.
    Aqui dentro a posição seguia PENDENTE (com a sincronização ligada, o preço
    não abre posição — quem confirma execução é a plataforma), e quando o preço
    apareceu além do stop o programa cravou "nunca foi executada". Isso não era
    leitura errada: era uma AFIRMAÇÃO sobre algo que ele não tinha como saber.
    E, pior, contradizia o que ele mesmo tinha anunciado minutos antes:
    "🎯 ENTRADA ACIONADA — SELL. Preço mitigou a zona em 7704.25".

    MENTIRA 2 — "🤖 Executei sozinha: ... Stop e alvo foram anexados à ordem."
    Essa mensagem saía ANTES do envio. Quando o envio falhava, nenhuma segunda
    linha desmentia a primeira — e ele ficava com a frase no celular e nada na
    corretora."""

    def _fonte(self):
        return fonte_do_arquivo()

    # ---- a máquina de estados ----
    def _ns(self, pos):
        return carregar(["atualizar_posicoes_com_preco"],
                        stubs={"carregar_posicoes": lambda: [dict(pos)],
                               "salvar_posicoes": lambda l: None,
                               "_e_da_conta_ativa": lambda p: True,
                               "valor_por_ponto_do_ativo": lambda a: 1.25,
                               "plano_da_conta_ativa": lambda: {}})

    def _pendente(self, **kw):
        base = {"id": "p1", "status": "PENDENTE", "ativo": "MESU6",
                "direcao": "SELL", "entry": 7704.25, "stop": 7708.25,
                "tp1": 7696.25, "contratos": 30, "origem": "ROBO"}
        base.update(kw)
        return base

    def test_ordem_que_ESTAVA_na_corretora_vira_NAO_SEI(self):
        """O caso dele, exatamente."""
        ns = self._ns(self._pendente(enviada_plataforma=True))
        eventos = ns["atualizar_posicoes_com_preco"](7710.0, "MESU6")
        self.assertEqual(len(eventos), 1)
        tipo, pos = eventos[0]
        self.assertEqual(tipo, "CANCELADA")
        self.assertTrue(pos.get("execucao_incerta"))
        self.assertIn("pode ter entrado e saído", pos["motivo_cancelamento"])

    def test_entrada_que_o_proprio_app_ANUNCIOU_tambem_vira_NAO_SEI(self):
        """Duas partes do programa não podem se contradizer no mesmo registro."""
        ns = self._ns(self._pendente(entrada_vista_no_preco=True))
        _, pos = ns["atualizar_posicoes_com_preco"](7710.0, "MESU6")[0]
        self.assertTrue(pos.get("execucao_incerta"))

    def test_ordem_que_NUNCA_foi_para_a_plataforma_continua_sendo_fato(self):
        """Sem ordem em lugar nenhum, "não executou" é verdade, e dizer 'não
        sei' aqui seria o erro oposto: dúvida inventada também é ruído."""
        ns = self._ns(self._pendente())
        _, pos = ns["atualizar_posicoes_com_preco"](7710.0, "MESU6")[0]
        self.assertFalse(pos.get("execucao_incerta"))
        self.assertIn("não chegou a ir para a plataforma",
                      pos["motivo_cancelamento"])

    def test_o_aviso_de_incerteza_MANDA_conferir_e_nao_registra_resultado(self):
        fonte = self._fonte()
        i = fonte.index("NÃO SEI SE ESTA ORDEM EXECUTOU")
        bloco = fonte[i:i + 900]
        self.assertIn("CONFIRA O EXTRATO DA CONTA", bloco)
        self.assertIn("não vou registrar", bloco.lower())

    def test_a_lista_de_sugestoes_para_de_cravar_sem_executar(self):
        fonte = self._fonte()
        i = fonte.index('if st == "CANCELADA":')
        bloco = fonte[i:i + 900]
        self.assertIn('pos.get("execucao_incerta")', bloco)
        self.assertIn("NÃO SEI se executou", bloco)

    # ---- as mensagens do modo autônomo ----
    def test_a_mensagem_ANTES_do_envio_fala_no_FUTURO(self):
        fonte = self._fonte()
        self.assertIn("EXECUTANDO SOZINHA", fonte)
        self.assertIn("Vou executar sozinha", fonte)
        self.assertNotIn("Stop e alvo foram anexados à ordem.", fonte)
        self.assertNotIn("EXECUTADO AUTOMATICAMENTE", fonte)

    def test_e_existe_uma_SEGUNDA_mensagem_com_o_que_aconteceu(self):
        """Sem ela, a única frase que ele lia era a do futuro, e ordem nenhuma
        desmentia."""
        fonte = self._fonte()
        i = fonte.index("A CONFIRMAÇÃO. O QUE ACONTECEU DE VERDADE.")
        bloco = fonte[i:i + 2200]
        self.assertIn("ORDEM ENVIADA", bloco)
        self.assertIn("NÃO ENVIEI", bloco)
        self.assertIn("NÃO SEI dizer se a ", bloco)
        self.assertIn("MODO TESTE", bloco)
        # e ela sai nos três canais
        self.assertIn("self.log(aviso)", bloco)
        self.assertIn("self._chat_feed(aviso)", bloco)
        self.assertIn("enviar_relatorio_whatsapp(aviso", bloco)

    def test_a_falha_de_envio_DIZ_que_nao_existe_posicao(self):
        fonte = self._fonte()
        i = fonte.index("NÃO ENVIEI")
        self.assertIn("NENHUMA ordem foi para a plataforma", fonte[i:i + 500])
