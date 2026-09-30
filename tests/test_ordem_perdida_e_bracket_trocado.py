"""23/08, 12:33 — O PROGRAMA TINHA UMA POSIÇÃO E NÃO SABIA.

O que a Tradovate registrou:

    #119531042 Comprar 3 MESU6 LMT em 7552.50 - Filled   - 3/3
    #119531048 Vender  3 MESU6 LMT em 7559.50 - Filled   - 3/3
    #119531050 Vender  3 MESU6 STP em 7524.50 - Cancelado - 0/3

O que o painel dele mostrava, na mesma hora:

    23/08 12:33:12 | BUY MESU6 · Entrada 7552.5 / Alvo 7575.0 / Stop 7540.0
    🚫 CANCELADA sem executar (stop rompido antes da entrada
       (a ordem não chegou a ir para a plataforma))

Três contratos entraram e saíram. O diário disse que a ordem nunca tinha
saído daqui. E no chat, a última linha foi a promessa — "Mandando a ordem
agora, confirmo aqui se ela foi aceita" — seguida de silêncio.

SÃO QUATRO DEFEITOS ENCADEADOS, e cada um sozinho já bastaria:

  1. o carimbo `enviada_plataforma` só era posto DEPOIS que o envio voltava
     dizendo `ok`. Exceção depois do clique em Enviar = ordem na corretora,
     carimbo nunca posto;

  2. o ramo de exceção escrevia no LOG e não no CHAT. A promessa de confirmar
     era quebrada exatamente no único caso em que ele não sabe o que houve;

  3. sem o carimbo, a lógica de PREÇO deu a ordem por "cancelada, nunca foi
     para a plataforma" — uma afirmação sobre a corretora feita sem olhar
     para a corretora;

  4. e ao virar CANCELADA a posição saía da varredura do extrato. O palpite
     virava sentença: nenhuma leitura futura podia mais desmentir.

Um erro que se tranca sozinho. Estes testes são a fechadura arrombada.

E o quinto, que ninguém tinha visto: o bracket que CHEGOU não era o que foi
DECIDIDO. Stop 7524.50 no lugar de 7540.00 — 28 pontos de risco onde o plano
autorizou 12,5. Em 3 contratos, US$420 expostos contra US$187,50 planejados.
Ninguém conferiu, e todo o dimensionamento seguinte saiu desse número falso.
"""

import unittest

from harness import carregar, fonte_do_arquivo, funcao_inteira


def _ns():
    return carregar(["reconciliavel_pelo_extrato", "divergencia_do_bracket",
                     "desfecho_pelas_execucoes"])


def _sem_comentarios(texto):
    """Tira comentário e docstring antes de procurar código no fonte.

    A LIÇÃO DA CASA (test_conta_orfa.py): um teste que procura texto no fonte
    casa com o comentário que EXPLICA o defeito antigo e passa a punir a
    documentação. Aqui só sobra código."""
    linhas = []
    dentro = False
    for ln in texto.splitlines():
        # A DOCSTRING NÃO FECHA NO INÍCIO DA LINHA. A primeira versão desta
        # função só olhava linhas COMEÇADAS por aspas triplas — e como toda
        # docstring longa daqui fecha no fim do último parágrafo, ela entrava
        # e nunca mais saía. Todo o corpo da função sumia, e os testes
        # acusavam ausência de código que estava lá. Contar os delimitadores
        # da linha inteira é o que resolve.
        n = ln.count('"""') + ln.count("'''")
        if dentro:
            if n % 2 == 1:
                dentro = False
            continue
        if n % 2 == 1:
            dentro = True
            continue
        if n >= 2:          # docstring de uma linha só
            continue
        if ln.strip().startswith("#"):
            continue
        linhas.append(ln.split("  # ")[0])
    return "\n".join(linhas)


# As ordens REAIS do extrato da Tradovate, como `ler_execucoes` as devolve.
ORDENS_1233 = [
    {"id": "119531042", "estado": "executada", "lado": "BUY", "tipo": "LIMITE",
     "preco": 7552.50, "ativo": "MESU6", "executados": 3, "total": 3},
    {"id": "119531048", "estado": "executada", "lado": "SELL", "tipo": "LIMITE",
     "preco": 7559.50, "ativo": "MESU6", "executados": 3, "total": 3},
    {"id": "119531050", "estado": "cancelada", "lado": "SELL", "tipo": "STOP",
     "preco": 7524.50, "ativo": "MESU6", "executados": 0, "total": 3},
]


class TestOCarimboVemANTESDoClique(unittest.TestCase):
    """A pergunta certa não é 'deu certo?', é 'pode ter saído?'."""

    def test_marca_antes_de_abrir_a_thread_de_envio(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_enviar_bracket")
        trecho = _sem_comentarios(fonte[i:i + 20000])
        i_marca = trecho.index("_marcar_ordem_na_corretora(sinal_id)")
        i_thread = trecho.index("threading.Thread(target=tarefa")
        self.assertLess(i_marca, i_thread,
                        "o carimbo tem de ser posto ANTES de a thread clicar "
                        "em Enviar — depois já pode ser tarde")

    def test_o_carimbo_nao_e_posto_em_modo_teste(self):
        """Modo teste preenche o ticket e não envia. Carimbar ali faria o
        robô segurar sugestões por causa de uma ordem que não existe."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_enviar_bracket")
        trecho = _sem_comentarios(fonte[i:i + 20000])
        i_marca = trecho.index("_marcar_ordem_na_corretora(sinal_id)")
        self.assertIn("if not dry:", trecho[max(0, i_marca - 200):i_marca])

    def test_existe_o_caminho_de_volta(self):
        fonte = fonte_do_arquivo()
        self.assertIn("def _desmarcar_ordem_na_corretora", fonte)

    def test_so_desfaz_quando_a_falha_e_PROVADA(self):
        """`incerto` e `exposto` são casos em que a ordem PODE estar lá. Nos
        dois o carimbo fica: supor que existe custa uma oportunidade; supor
        que não existe custa a conta."""
        fonte = fonte_do_arquivo()
        # O PRIMEIRO ponto que desfaz o carimbo passou a ser a recusa da
        # conferência contra a plataforma, que volta ANTES de qualquer clique
        # — prova mais forte do que qualquer campo de resultado. Este teste
        # continua sendo sobre o ponto de DEPOIS do envio, que é onde
        # `incerto` e `exposto` existem para pesar.
        corpo = funcao_inteira(fonte, "_tv_enviar_bracket")
        i = corpo.index("_desmarcar_ordem_na_corretora(sinal_id)",
                        corpo.index("bot.enviar_ordem_com_atm("))
        trecho = _sem_comentarios(corpo[max(0, i - 700):i])
        self.assertIn('not res.get("ok")', trecho)
        self.assertIn('not res.get("incerto")', trecho)
        self.assertIn('not res.get("exposto")', trecho)


class TestAExcecaoDeixaDeSerMuda(unittest.TestCase):
    """'Confirmo aqui se ela foi aceita' — e depois nada. A promessa é feita
    no chat; ela tem de ser cumprida no chat, em TODOS os desfechos."""

    def _corpo_do_except(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("a ligação com o Chrome falhou no meio do envio")
        return _sem_comentarios(fonte[i - 600:i + 1800])

    def test_a_falha_no_envio_chega_ao_chat(self):
        self.assertIn("_chat_feed", self._corpo_do_except())

    def test_e_tambem_ao_whatsapp(self):
        self.assertIn("enviar_relatorio_whatsapp", self._corpo_do_except())

    def test_e_marca_a_execucao_como_incerta(self):
        """É esta marca que mantém a posição sob a vigilância do extrato
        depois que a lógica de preço a der por cancelada."""
        self.assertIn("_marcar_execucao_incerta", self._corpo_do_except())
        self.assertIn("def _marcar_execucao_incerta", fonte_do_arquivo())

    def test_o_carimbo_NAO_e_desfeito_na_excecao(self):
        """Exceção depois do Enviar é o caso que criou o bug. Desfazer o
        carimbo aqui reconstruiria o defeito inteiro."""
        self.assertNotIn("_desmarcar_ordem_na_corretora",
                         self._corpo_do_except())


class TestACorretoraTemAUltimaPalavra(unittest.TestCase):
    """`reconciliavel_pelo_extrato`: quem pode ser desmentido pelo extrato."""

    def setUp(self):
        self.f = _ns()["reconciliavel_pelo_extrato"]

    def test_pendente_e_aberta_sempre(self):
        self.assertTrue(self.f({"status": "PENDENTE"}))
        self.assertTrue(self.f({"status": "ABERTA"}))

    def test_a_cancelada_de_hoje_que_FOI_para_a_plataforma_ainda_e_olhada(self):
        """O caso de 12:33. Sem isto, o palpite do preço é a última palavra."""
        self.assertTrue(self.f({"status": "CANCELADA",
                                "enviada_plataforma": True,
                                "data_fechamento": "23/08/2026 12:33"},
                               hoje="23/08/2026"))

    def test_a_cancelada_com_execucao_incerta_tambem(self):
        self.assertTrue(self.f({"status": "CANCELADA",
                                "execucao_incerta": True,
                                "data_fechamento": "23/08/2026 12:33"},
                               hoje="23/08/2026"))

    def test_sugestao_que_nunca_saiu_do_diario_NAO_e_procurada_la(self):
        """Não há o que conferir na corretora sobre uma ordem que nunca foi
        para a corretora — e procurar casaria com a ordem de outra pessoa."""
        self.assertFalse(self.f({"status": "CANCELADA",
                                 "data_fechamento": "23/08/2026 12:33"},
                                hoje="23/08/2026"))

    def test_cancelada_de_ONTEM_nao_ressuscita(self):
        """O extrato da tela mostra as ordens recentes. Casar uma cancelada
        de terça com o extrato de hoje inventaria operação."""
        self.assertFalse(self.f({"status": "CANCELADA",
                                 "enviada_plataforma": True,
                                 "data_fechamento": "22/08/2026 03:00"},
                                hoje="23/08/2026"))

    def test_fechada_fica_de_fora(self):
        """Ou veio do extrato, ou de um fechamento confirmado. Reabrir seria
        contar o mesmo resultado duas vezes no drawdown."""
        self.assertFalse(self.f({"status": "FECHADA",
                                 "enviada_plataforma": True}))

    def test_o_que_o_extrato_ja_resolveu_nao_volta_para_a_fila(self):
        self.assertFalse(self.f({"status": "CANCELADA",
                                 "enviada_plataforma": True,
                                 "desfecho_por": "extrato_plataforma",
                                 "data_fechamento": "23/08/2026 12:33"},
                                hoje="23/08/2026"))

    def test_a_varredura_usa_ESTA_regra_nos_dois_lugares(self):
        """A regra estava escrita duas vezes (no filtro e dentro do laço), e
        era no laço que a CANCELADA voltava a ser descartada."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _reconciliar_pelo_extrato")
        trecho = _sem_comentarios(fonte[i:i + 3500])
        self.assertEqual(trecho.count("reconciliavel_pelo_extrato("), 2)
        self.assertNotIn('status") not in ("PENDENTE", "ABERTA")', trecho)


class TestOCasoRealDas1233(unittest.TestCase):
    """A operação inteira, contra o extrato de verdade."""

    def test_a_cancelada_vira_FECHADA_com_o_resultado_certo(self):
        pos = {"direcao": "BUY", "ativo": "MESU6", "contratos": 3,
               "entry": 7552.5, "status": "CANCELADA",
               "enviada_plataforma": True, "vpp": 5.0}
        novo, saida, pnl, motivo = _ns()["desfecho_pelas_execucoes"](
            pos, ORDENS_1233)
        self.assertEqual(novo, "FECHADA")
        self.assertEqual(saida, 7559.50)
        # 7559,50 - 7552,50 = 7 pontos · US$5 · 3 contratos
        self.assertEqual(pnl, 105.00)

    def test_o_desmentido_e_anunciado_e_nao_corrigido_de_fininho(self):
        """O programa afirmou a ele que a ordem não tinha ido para a
        plataforma. Foi. Consertar em silêncio seria a mesma doença."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _reconciliar_pelo_extrato")
        trecho = fonte[i:i + 4000]
        self.assertIn("era_cancelada", trecho)
        self.assertIn("CORRIGINDO O QUE EU TINHA DITO", trecho)
        i_aviso = trecho.index("CORRIGINDO O QUE EU TINHA DITO")
        janela = trecho[i_aviso:i_aviso + 900]
        self.assertIn("_chat_feed", janela)
        self.assertIn("enviar_relatorio_whatsapp", janela)


class TestOBracketQueChegouNaoEraOQueEuDecidi(unittest.TestCase):
    """`divergencia_do_bracket`. O motor decidiu stop 7540,00; a plataforma
    ficou com 7524,50. Ninguém comparou, e todo o risco seguinte foi
    calculado em cima do número que só existia aqui dentro."""

    def setUp(self):
        self.f = _ns()["divergencia_do_bracket"]

    def test_pega_o_stop_trocado_do_dia_23(self):
        bate, avisos = self.f(ORDENS_1233, "BUY", 7540.0, 7575.0,
                              ativo="MESU6", tick=0.25)
        self.assertFalse(bate)
        junto = " ".join(avisos)
        self.assertIn("7524.5", junto)
        self.assertIn("7540.0", junto)

    def test_pega_o_alvo_trocado_do_dia_23(self):
        """Saiu em 7559,50 — que não é o 7575,0 decidido."""
        _, avisos = self.f(ORDENS_1233, "BUY", 7540.0, 7575.0,
                           ativo="MESU6", tick=0.25)
        self.assertTrue(any("7559.5" in a and "ALVO" in a for a in avisos))

    def test_bracket_certo_nao_gera_alarme(self):
        """Uma trava que grita sempre é uma trava que ninguém lê."""
        bate, avisos = self.f(ORDENS_1233, "BUY", 7524.50, 7559.50,
                              ativo="MESU6", tick=0.25)
        self.assertTrue(bate)
        self.assertEqual(avisos, [])

    def test_meio_tick_de_folga_nao_vira_alarme_falso(self):
        """A plataforma arredonda para o tick do contrato."""
        bate, _ = self.f(ORDENS_1233, "BUY", 7524.40, 7559.60,
                         ativo="MESU6", tick=0.25)
        self.assertTrue(bate)

    def test_stop_ausente_no_extrato_e_denunciado(self):
        """Pior que o stop errado: o stop que não está lá."""
        sem_stop = [o for o in ORDENS_1233 if o["tipo"] != "STOP"]
        bate, avisos = self.f(sem_stop, "BUY", 7540.0, 7559.50,
                              ativo="MESU6", tick=0.25)
        self.assertFalse(bate)
        self.assertTrue(any("STOP" in a and "NÃO APARECE" in a for a in avisos))

    def test_extrato_vazio_nao_acusa_nada(self):
        """Ausência de leitura não é conclusão — nem para acusar."""
        self.assertEqual(self.f([], "BUY", 7540.0, 7575.0), (True, []))
        self.assertEqual(self.f(None, "BUY", 7540.0, 7575.0), (True, []))

    def test_ordem_de_outro_contrato_nao_entra_na_conta(self):
        """O prejuízo de 20/08 nasceu de confundir MNQU6 com MESU6."""
        outro = [dict(o, ativo="MNQU6") for o in ORDENS_1233]
        bate, avisos = self.f(outro, "BUY", 7540.0, 7575.0,
                              ativo="MESU6", tick=0.25)
        self.assertFalse(bate)
        self.assertTrue(all("NÃO APARECE" in a for a in avisos))

    def test_no_SELL_o_bracket_esta_do_lado_da_compra(self):
        ordens = [
            {"estado": "executada", "lado": "SELL", "tipo": "LIMITE",
             "preco": 7600.0, "ativo": "MESU6"},
            {"estado": "cancelada", "lado": "BUY", "tipo": "STOP",
             "preco": 7610.0, "ativo": "MESU6"},
        ]
        bate, _ = self.f(ordens, "SELL", 7610.0, None,
                         ativo="MESU6", tick=0.25)
        self.assertTrue(bate)

    def test_a_conferencia_esta_LIGADA_no_envio(self):
        """Função que existe e não é chamada é o `self.order_flow` de novo."""
        fonte = fonte_do_arquivo()
        self.assertIn("divergencia_do_bracket(", fonte)
        i = fonte.index("def _tv_enviar_bracket")
        trecho = fonte[i:i + 14000]
        self.assertIn("divergencia_do_bracket(", trecho)
        j = trecho.index("divergencia_do_bracket(")
        self.assertIn("_chat_feed", trecho[j:j + 1400])

    def test_nao_conseguir_conferir_nao_e_conferir_e_estar_certo(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("divergencia_do_bracket(", fonte.index("def _tv_enviar_bracket"))
        trecho = fonte[i:i + 2600]
        self.assertIn("não os confirmei na plataforma", trecho)


class TestAFitaLeOLadoSemDependerDaLinhaEstarPintada(unittest.TestCase):
    """12:05: 'a fita não marca o lado da agressão'. Mas ela marca — os prints
    mostram cada linha em vermelho ou verde. O que falhava era ONDE se
    procurava a tinta: `getComputedStyle` não herda fundo, e se a Tradovate
    pinta a CÉLULA a linha volta transparente."""

    def _stream(self):
        import tradovate_stream
        return tradovate_stream.TradovateStream

    def test_transparente_nao_e_lido_como_preto(self):
        """`rgba(0,0,0,0)` casava no regex de três números e virava R=G=B=0.
        Era assim que a leitura morria em silêncio."""
        js = self._stream()._JS_LADO_PELA_COR
        self.assertIn("rgba", js)
        self.assertIn("return null", js)

    def test_se_a_linha_nao_esta_pintada_olha_a_celula(self):
        js = self._stream()._JS_LADO_PELA_COR
        self.assertIn("ln.children", js)

    def test_cinza_e_branco_nao_viram_lado(self):
        """Linha alternada de tabela é cinza. Chutar lado nela envenenaria o
        delta com metade dos negócios do lado errado."""
        self.assertIn("R===G && G===B", self._stream()._JS_LADO_PELA_COR)

    def test_a_funcao_esta_DEFINIDA_nos_dois_scripts_que_a_usam(self):
        """Usar `_ladoPelaCor` sem injetar a definição é ReferenceError
        dentro da página — e a leitura voltaria vazia sem dizer por quê."""
        T = self._stream()
        s = T.__new__(T)
        observador = T._js_com_achador(s, T._JS_INSTALAR_OBSERVADOR)
        pontual = T._JS_TIME_AND_SALES.replace(
            "PLACEHOLDER_LADO_PELA_COR", T._JS_LADO_PELA_COR)
        for nome, js in (("observador", observador), ("pontual", pontual)):
            self.assertIn("_ladoPelaCor(", js, nome)
            self.assertIn("function _ladoPelaCor", js, nome)
            self.assertNotIn("PLACEHOLDER", js, f"{nome}: sobrou placeholder")

    def test_o_leitor_pontual_injeta_de_verdade_na_chamada(self):
        """O `replace` tem de estar no ponto da chamada, e não só no teste."""
        import inspect
        fonte = inspect.getsource(self._stream().ler_time_and_sales)
        self.assertIn("PLACEHOLDER_LADO_PELA_COR", fonte)


class TestBidAskComRotuloEValorSeparados(unittest.TestCase):
    """`num("COMPRA")` é sempre None. O leitor antigo exigia rótulo e valor no
    MESMO nó — e na tela dele eles estão empilhados:

        COMPRA            PREÇO DE VENDA
        7536.75           7537.00
    """

    def _js(self):
        import tradovate_stream
        return tradovate_stream.TradovateStream._JS_TIME_AND_SALES

    def test_procura_o_numero_ao_lado_do_rotulo(self):
        js = self._js()
        self.assertIn("_valorPerto", js)
        self.assertIn("nextElementSibling", js)
        self.assertIn("parentElement", js)

    def test_nao_pega_qualquer_numero_da_pagina(self):
        """O primeiro número solto do documento não tem relação com o book."""
        js = self._js()
        i = js.index("function _valorPerto")
        fim = js.index("var bid=null", i)
        self.assertNotIn("document.querySelectorAll", js[i:fim])


class TestOBookParadoNaoViraDelta(unittest.TestCase):
    """A armadilha que o conserto do bid/ask abriria.

    Nos prints de 23/08 o cabeçalho marca COMPRA 7536,75 e PREÇO DE VENDA
    7537,00 enquanto a fita imprime negócio a 7583 e a 7591 — o book do replay
    não acompanha. Com esses números no Lee-Ready, TODO negócio sai "acima do
    ask", logo agressão compradora, e o CVD vira uma reta subindo para sempre.

    Consertar a leitura sem esta trava teria produzido um delta pior que
    nenhum: errado com cara de medido.
    """

    def _js(self):
        import tradovate_stream
        return tradovate_stream.TradovateStream._JS_TIME_AND_SALES

    def test_existe_a_trava_de_book_defasado(self):
        js = self._js()
        self.assertIn("bid_ask_descartado", js)
        self.assertIn("0.002", js)

    def test_a_regra_reprova_os_numeros_REAIS_do_print(self):
        """A régua em Python, com os números da tela dele."""
        bid, ask, ultimo = 7536.75, 7537.00, 7591.25
        meio = (bid + ask) / 2
        self.assertGreater(abs(ultimo - meio) / meio, 0.002)

    def test_e_aprova_um_book_vivo(self):
        """Spread normal de MES: um tick. Não pode ser descartado."""
        bid, ask, ultimo = 7586.50, 7586.75, 7586.50
        meio = (bid + ask) / 2
        self.assertLessEqual(abs(ultimo - meio) / meio, 0.002)

    def test_o_descarte_zera_os_DOIS_lados(self):
        """Meio book é pior que nenhum: o Lee-Ready compara com os dois."""
        js = self._js()
        i = js.index("bid_ask_descartado")
        trecho = js[i:i + 200]
        self.assertIn("bid = null", trecho)
        self.assertIn("ask = null", trecho)


class TestOObservadorNaoRefazTrabalhoCaro(unittest.TestCase):
    """'melhore a sondagem geral do T&S para evitar gargalos'.

    O balde já tem teto de 4000 e o `vistos` já é podado em 8000 chaves — não
    havia vazamento ali. O custo era outro: cada nó adicionado ia direto para
    `_lerLinha`, que varre a subárvore inteira e chama `getComputedStyle`
    (que força recálculo de estilo). Como o laço de fora JÁ expande os
    descendentes, um bloco de linhas trocado de uma vez pagava isso n vezes
    para os mesmos n nós.
    """

    def _js(self):
        import tradovate_stream
        return tradovate_stream.TradovateStream._JS_INSTALAR_OBSERVADOR

    def test_ha_um_porteiro_barato_antes_do_trabalho_caro(self):
        js = self._js()
        self.assertIn("function pareceLinha", js)
        i_reg = js.index("function registrar")
        self.assertIn("pareceLinha(ln)", js[i_reg:i_reg + 200])

    def test_o_porteiro_usa_so_texto_e_regex(self):
        """Se ele próprio varresse a subárvore não seria porteiro nenhum."""
        js = self._js()
        i = js.index("function pareceLinha")
        corpo = js[i:i + 500]
        self.assertNotIn("querySelectorAll(", corpo)
        self.assertNotIn("getComputedStyle", corpo)

    def test_o_teto_do_balde_e_a_poda_do_vistos_continuam_de_pe(self):
        js = self._js()
        self.assertIn("st.balde.length > 4000", js)
        self.assertIn("ks.length > 8000", js)
        self.assertIn("st.perdidos", js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
