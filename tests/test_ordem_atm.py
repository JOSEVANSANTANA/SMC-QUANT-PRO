"""A ordem inteira numa submissão só — e o campo certo, conferido.

19/08, print dele do 'Chamado do pedido' com o painel de ATMs aberto:

    PREÇO         29542.00      <- o MESU6 estava em 7732.50
    OBTER LUCRO   80 ticks  ->  29562.00
    STOP LOSS     40 ticks  ->  29532.00

Os três números são coerentes ENTRE SI (80 e 40 ticks de 0,25 a partir de
29542), e nenhum deles tem relação com o gráfico. Ou seja: o ticket estava
sendo preenchido, e no lugar errado.

DOIS DEFEITOS, E O SEGUNDO É O QUE ASSUSTA
------------------------------------------
1) `definir_campo_ticket` mirava por POSIÇÃO: "o primeiro input do painel da
   esquerda, sem placeholder, cujo valor pareça número". Isso funciona com o
   ticket sozinho na tela. Com o painel de ATMs ABERTO — que é como ele opera
   — a mesma coluna passa a ter OBTER LUCRO, STOP LOSS, ACIONAR LUCROS e
   FREQUÊNCIA, todos numéricos e todos sem placeholder.

2) A função devolvia 'OK' por ter ENCONTRADO um input, nunca por ter CONFERIDO
   que o número entrou onde devia. Escrever no campo errado e reportar sucesso
   é a pior combinação possível quando o passo seguinte é clicar em Enviar.

E O CAMINHO NOVO, QUE É IDEIA DELE
----------------------------------
"ela tem opcao de colocar a entrada com ordem ATMs marcados em tiks, assim, a
ordem ja entra com stop e gains e quando acionada a saida tanto de stop quanto
de gain, ela cancela as pendentes".

Está certo, e é melhor que o que estava lá. O caminho antigo mandava TRÊS
ordens separadas, e entre uma e outra o painel vira comprovante e precisa
voltar ao formulário. Toda vez que essa volta falha existe uma janela em que a
ENTRADA está no mercado e a PROTEÇÃO não — o pior estado que este programa
pode produzir. Com a ATM é uma submissão só, e o OCO é da corretora.
"""

import unittest

from harness import RAIZ, carregar, fonte_do_arquivo  # noqa: F401
import os
import sys

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import tradovate_auto as tv


class TestLerNumeroDoCampo(unittest.TestCase):
    """A Tradovate reescreve o número no campo com a formatação da localidade,
    e o campo é lido de volta como TEXTO. Comparar '7732.5' com '7,732.50' como
    string diria que o valor não entrou — e o robô abortaria uma ordem certa."""

    def test_o_mesmo_numero_em_tres_formatos(self):
        for texto in ("29542", "29542.00", "29,542.00", "29.542,00"):
            self.assertEqual(tv._como_numero(texto), 29542.0, texto)

    def test_decimal_com_virgula_continua_decimal(self):
        self.assertEqual(tv._como_numero("7732,50"), 7732.5)
        self.assertEqual(tv._como_numero("1,5"), 1.5)

    def test_milhar_com_virgula_e_tres_casas(self):
        self.assertEqual(tv._como_numero("1,500"), 1500.0)

    def test_texto_que_nao_e_numero_devolve_None(self):
        for t in ("", None, "Selecionar", "abc", "--"):
            self.assertIsNone(tv._como_numero(t), repr(t))

    def test_valores_batem_compara_como_NUMERO(self):
        self.assertTrue(tv.valores_batem(7732.5, "7,732.50"))
        self.assertTrue(tv.valores_batem(40, "40"))
        self.assertFalse(tv.valores_batem(40, "41"))

    def test_tolerancia_existe_para_arredondamento_de_tick(self):
        """A plataforma arredonda para o tick dela. Recusar a ordem por causa
        disso seria recusar por estar certa."""
        self.assertTrue(tv.valores_batem(7732.60, "7732.50", tolerancia=0.125))
        self.assertFalse(tv.valores_batem(7735.00, "7732.50", tolerancia=0.125))

    def test_sem_tolerancia_a_igualdade_e_exata(self):
        self.assertFalse(tv.valores_batem(7732.60, "7732.50"))


class TestDoCenarioSMCParaOsTicksDaATM(unittest.TestCase):
    """A ATM não recebe preço de stop: recebe DISTÂNCIA em ticks a partir do
    preenchimento. Esta conta é a que decide onde fica a proteção de uma ordem
    que vai ser enviada sem ninguém olhando."""

    def test_a_conta_do_print_dele(self):
        """MES, tick 0,25: 40 ticks de stop e 80 de alvo — exatamente os
        números que apareciam na tela."""
        t_stop, t_alvo, erro = tv.plano_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25)
        self.assertIsNone(erro)
        self.assertEqual((t_stop, t_alvo), (40, 80))

    def test_venda_mede_a_distancia_do_mesmo_jeito(self):
        t_stop, t_alvo, erro = tv.plano_atm("SELL", 7732.50, 7742.50, 7712.50, 0.25)
        self.assertIsNone(erro)
        self.assertEqual((t_stop, t_alvo), (40, 80))

    def test_COMPRA_com_stop_ACIMA_da_entrada_e_recusada(self):
        """A ATM é cega: ela mede distância e não sabe de que lado o stop
        está. Um BUY com stop acima da entrada viraria, na Tradovate, um stop
        de N ticks ABAIXO — ela inverteria em silêncio a proteção que o
        cenário pedia."""
        t_stop, t_alvo, erro = tv.plano_atm("BUY", 7732.50, 7742.50, 7752.50, 0.25)
        self.assertIsNone(t_stop)
        self.assertIn("incoerente", erro)

    def test_VENDA_com_alvo_ACIMA_da_entrada_e_recusada(self):
        _, _, erro = tv.plano_atm("SELL", 7732.50, 7742.50, 7752.50, 0.25)
        self.assertIn("incoerente", erro)

    def test_distancia_zero_nao_vira_ordem(self):
        """ATM com zero tick é ordem sem proteção nenhuma. 'None' aqui
        significa NÃO ENVIE, nunca 'use zero'."""
        _, _, erro = tv.plano_atm("BUY", 7732.50, 7732.50, 7752.50, 0.25)
        self.assertIsNotNone(erro)

    def test_tick_invalido_nao_vira_ordem(self):
        for tick in (0, None, -1, "abc"):
            _, _, erro = tv.plano_atm("BUY", 7732.5, 7722.5, 7752.5, tick)
            self.assertIsNotNone(erro, repr(tick))

    def test_preco_nao_numerico_nao_vira_ordem(self):
        _, _, erro = tv.plano_atm("BUY", None, 7722.5, 7752.5, 0.25)
        self.assertIn("números", erro)

    def test_ticks_entre_arredonda_para_o_inteiro_mais_proximo(self):
        self.assertEqual(tv.ticks_entre(100.0, 99.0, 0.25), 4)
        self.assertEqual(tv.ticks_entre(100.0, 100.30, 0.25), 1)
        self.assertIsNone(tv.ticks_entre(100.0, 100.0, 0.25))

    def test_o_tick_de_cada_ativo_vem_da_tabela_do_app(self):
        """A conta em ticks só existe se eu souber o tick do contrato. Chutar
        um tick seria inventar a distância do stop."""
        ns = carregar(["tick_do_ativo", "TICK_MINIMO"])
        self.assertEqual(ns["tick_do_ativo"]("MESU6"), 0.25)
        self.assertEqual(ns["tick_do_ativo"]("MYMZ5"), 1.0)
        self.assertIsNone(ns["tick_do_ativo"]("PAPELDESCONHECIDO"))


class _BotFalso(tv.TradovateAuto):
    """Um TradovateAuto que nunca fala com Chrome nenhum.

    Guarda o JS pedido e devolve o que o teste mandar — é assim que dá para
    conferir a lógica de decisão sem plataforma aberta."""

    def __init__(self, respostas=None):
        self.log_linhas = []
        self.log = self.log_linhas.append
        self.js = []
        self.cliques = []
        self.respostas = respostas or {}
        self.campos = {}

    def avaliar_js(self, expressao):
        self.js.append(expressao)
        for chave, valor in self.respostas.items():
            if chave in expressao:
                return valor
        return "{}"

    def clicar_pagina(self, x, y, dry_run=False):
        self.cliques.append((x, y))

    def _garantir_formulario(self, tentativas=3):
        return self.respostas.get("_formulario", True)

    def localizar(self, palavra):
        if palavra in self.respostas.get("_sem_botao", ()):
            return None
        return {"x": 10, "y": 20}

    def _achar_por_texto(self, palavras):
        return {p: {"x": 1, "y": 2} for p in palavras}

    def _selecionar_tipo(self, tipo, pausa=0.45, dry_run=False):
        return True

    # ESTA é a costura que os testes observam: o lote de campos numa ida só ao
    # Chrome. Era `_campo_por_rotulo` (um por vez) até o travamento de 19/08 —
    # seis viagens ao CDP no meio de uma ordem, e a ordem morreu numa delas.
    def campos_por_rotulo(self, pedidos, tolerancia=18):
        falhos = self.respostas.get("_campos_que_falham", ())
        errados = self.respostas.get("_campos_que_mentem", ())
        saida = []
        for rotulo, ocorrencia, valor in pedidos:
            chave = rotulo if not ocorrencia else f"{rotulo}#{ocorrencia}"
            if rotulo in falhos or chave in falhos:
                saida.append({"estado": "CAMPO_NAO_ACHADO"})
                continue
            if rotulo == "EXIBIR EM":
                saida.append({"estado": "OK",
                              "valor": self.respostas.get("_exibir_em", "Ticks"),
                              "tipo": "texto"})
                continue
            if valor is not None:
                self.campos[chave] = valor
            lido = self.campos.get(chave, "")
            if rotulo in errados or chave in errados:
                lido = "999999"
            saida.append({"estado": "OK", "valor": str(lido), "x": 5, "y": 6})
        return saida


class TestAOrdemSoSAIComTudoConferido(unittest.TestCase):
    """A regra de ouro: nada é enviado antes de todos os campos terem sido
    escritos E conferidos por leitura de volta. Com qualquer um falhando, o
    pior resultado passa a ser 'não operou' — que é um resultado com o qual dá
    para viver."""

    def _bot(self, **respostas):
        return _BotFalso(respostas)

    def test_o_caminho_feliz_envia_uma_vez_e_leva_stop_e_alvo(self):
        bot = self._bot()
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["enviadas"], ["ENTRADA", "STOP", "ALVO"])
        self.assertEqual((r["ticks_stop"], r["ticks_alvo"]), (40, 80))
        self.assertFalse(r["exposto"])
        self.assertEqual(bot.campos["PREÇO"], 7732.50)
        self.assertEqual(bot.campos["QTD"], 2)
        self.assertEqual(bot.campos["OBTER LUCRO"], 80)
        self.assertEqual(bot.campos["STOP LOSS"], 40)

    def test_campo_de_preco_que_MENTE_aborta_antes_do_enviar(self):
        """Era isto que faltava: o campo dizia OK e o número estava noutro
        lugar."""
        bot = self._bot(_campos_que_mentem=("PREÇO",))
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertIn("PREÇO", r["erro"])
        self.assertFalse(r["exposto"], "nada foi enviado, então nada ficou exposto")

    def test_ATM_que_nao_grava_o_stop_NAO_manda_a_entrada(self):
        """Entrada sem proteção anexada é exatamente o que este caminho veio
        eliminar. Melhor não operar."""
        bot = self._bot(_campos_que_falham=("STOP LOSS",))
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertFalse(r["exposto"])
        self.assertEqual(sorted(r["faltando"]), ["ALVO", "ENTRADA", "STOP"])

    def test_cenario_incoerente_nem_chega_a_tocar_no_formulario(self):
        bot = self._bot()
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7742.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertIn("incoerente", r["erro"])
        self.assertEqual(bot.campos, {}, "não podia ter escrito nada")

    def test_sem_quantidade_nao_envia(self):
        bot = self._bot()
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=None, enviar=True)
        self.assertFalse(r["ok"])
        self.assertIn("quantidade", r["erro"])

    def test_modo_teste_preenche_e_NAO_clica_em_enviar(self):
        bot = self._bot()
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["enviadas"], ["PRE-VISUALIZACAO"])
        self.assertEqual(bot.campos["OBTER LUCRO"], 80)
        self.assertTrue(any("NÃO enviei" in l for l in bot.log_linhas))

    def test_formulario_ausente_nao_vira_ordem(self):
        bot = self._bot(_formulario=False)
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertIn("formulário", r["erro"])

    def test_sem_o_botao_ENVIAR_nada_e_dado_como_enviado(self):
        bot = self._bot(_sem_botao=("Enviar",))
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertFalse(r["exposto"])

    def test_EXIBIR_EM_fora_de_ticks_BLOQUEIA_a_ordem(self):
        """Em 'Preço', o mesmo número 40 deixa de ser 40 ticks e vira o preço
        40. Não é detalhe de tela: é a diferença entre um stop de dez pontos e
        uma ordem sem sentido nenhum. Por isso não é aviso — é bloqueio."""
        bot = self._bot(_exibir_em="Preço")
        r = bot.enviar_ordem_com_atm("BUY", 7732.50, 7722.50, 7752.50, 0.25,
                                     qtd=2, enviar=True)
        self.assertFalse(r["ok"])
        self.assertIn("EXIBIR EM", r["erro"])
        self.assertFalse(r["exposto"])


class TestOAppUSAOCaminhoNovo(unittest.TestCase):
    """Método escrito e nunca chamado é o defeito de sempre."""

    def test_o_envio_do_app_tenta_a_ATM_primeiro(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_enviar_bracket(")
        bloco = fonte[i:i + 3500]
        self.assertIn("enviar_ordem_com_atm(", bloco)
        j = bloco.index("enviar_ordem_com_atm(")
        k = bloco.index("enviar_bracket_ticket(")
        self.assertLess(j, k, "o caminho das três ordens tem de ser a reserva")

    def test_a_reserva_so_entra_quando_NADA_foi_enviado(self):
        """Cair para o caminho antigo depois de a entrada já ter ido seria
        duplicar posição."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_enviar_bracket(")
        bloco = fonte[i:i + 3500]
        self.assertIn('not res.get("exposto")', bloco)

    def test_o_ativo_e_repassado_para_achar_o_tick(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_enviar_bracket(")
        self.assertIn("tick_do_ativo(", fonte[i:i + 1200])
        j = fonte.index("self._tv_enviar_bracket(")
        self.assertIn("ativo=", fonte[j:j + 400])


if __name__ == "__main__":
    unittest.main()


class TestOTravamentoDoCDPDe19_08(unittest.TestCase):
    """O log dele, 20:12, com o ticket praticamente pronto:

        📦 Ordem ÚNICA com ATM [ENVIAR]: Vender LIMITE @ 7719.0 · stop 16
           ticks (7723.0) · alvo 32 ticks (7711.0) · qtd=30
           ✏️ preço 7719.0 conferido no campo (7719.00).
           ✏️ quantidade 30 conferida no campo.
        ⚠️ falha ao enviar ordem: sem resposta do CDP para Runtime.evaluate
           (conexão travada).

    A mira por rótulo funcionou — o print da plataforma mostra PREÇO 7719.00 e
    QTD 30, escritos por ela. O que morreu foi o passo seguinte, e não por
    culpa da Tradovate: o socket AFOGOU.

    `Runtime.enable` faz o Chrome empurrar todo console.log e toda criação de
    contexto; `Page.enable` empurra o ciclo de vida de cada frame. A Tradovate
    é um app ao vivo, com iframes e cotação entrando o tempo todo — e o laço
    que espera a resposta do NOSSO comando passava os 10 segundos lendo evento
    dos outros. A resposta existia, atrás de uma fila que não parava de
    crescer. E nada disso era usado: nenhum evento de Runtime ou de Page é
    consumido em lugar nenhum do arquivo."""

    def _fonte(self):
        with open(os.path.join(RAIZ, "tradovate_auto.py"), encoding="utf-8") as f:
            return f.read()

    def test_a_conexao_NAO_liga_os_dominios_que_inundam(self):
        fonte = self._fonte()
        self.assertNotIn('self.cdp("Runtime.enable")', fonte)
        self.assertNotIn('self.cdp("Page.enable")', fonte)

    def test_e_ninguem_consome_evento_desses_dominios(self):
        """Se um dia alguém precisar dos eventos, este teste falha junto — e
        aí a decisão volta a ser consciente, em vez de um enable esquecido."""
        fonte = self._fonte()
        for evento in ("Runtime.consoleAPICalled", "Page.loadEventFired",
                       "Page.frameNavigated", "Runtime.executionContextCreated"):
            self.assertNotIn(evento, fonte)

    def test_o_erro_de_travamento_DIZ_quantos_eventos_passaram_na_frente(self):
        """Sem esse número, o diagnóstico recomeça do zero na próxima vez."""
        fonte = self._fonte()
        # `rindex`: a PRIMEIRA ocorrência é o comentário que conta a história
        # do travamento. A que vale é a mensagem de erro de verdade.
        i = fonte.rindex("sem resposta do CDP para")
        self.assertIn("evento(s) da página chegaram na frente", fonte[i:i + 400])

    def test_preencher_o_ticket_custa_UMA_ida_ao_chrome_por_lote(self):
        """Seis viagens ao CDP no meio de uma ordem eram seis chances de
        travar. O ATM inteiro agora vai num lote só."""
        fonte = self._fonte()
        i = fonte.index("def configurar_atm(")
        bloco = fonte[i:fonte.index("\n    def ", i + 10)]
        self.assertIn("self.campos_por_rotulo(pedidos)", bloco)
        self.assertNotIn("definir_campo_por_rotulo(", bloco)


class TestRepetirEPossivelATEOEnviar(unittest.TestCase):
    """Enquanto NADA foi enviado, tentar de novo não tem risco nenhum — e é a
    diferença entre operar e não operar quando o Chrome engasga."""

    class _EngasgaUmaVez(_BotFalso):
        def __init__(self, respostas=None):
            super().__init__(respostas)
            self.engasgos = 0
            self.reconexoes = 0

        def campos_por_rotulo(self, pedidos, tolerancia=18):
            rotulos = [p[0] for p in pedidos]
            if "OBTER LUCRO" in rotulos and self.engasgos == 0:
                self.engasgos += 1
                raise tv.ConexaoPerdida("sem resposta do CDP para "
                                        "Runtime.evaluate")
            return super().campos_por_rotulo(pedidos, tolerancia)

        def conectar(self):
            self.reconexoes += 1
            return True

    def test_engasgo_no_meio_do_preenchimento_e_REFEITO_e_a_ordem_sai(self):
        bot = self._EngasgaUmaVez()
        r = bot.enviar_ordem_com_atm("SELL", 7719.0, 7723.0, 7711.0, 0.25,
                                     qtd=30, enviar=True)
        self.assertTrue(r["ok"], r.get("erro"))
        self.assertEqual(bot.reconexoes, 1, "tinha de reconectar antes de repetir")
        self.assertEqual(r["enviadas"], ["ENTRADA", "STOP", "ALVO"])
        self.assertTrue(any("refazendo o preenchimento" in l
                            for l in bot.log_linhas))

    def test_os_ticks_do_caso_REAL_dele(self):
        """entrada 7719.0 · stop 7723.0 · alvo 7711.0 no MES = 16 e 32."""
        t_stop, t_alvo, erro = tv.plano_atm("SELL", 7719.0, 7723.0, 7711.0, 0.25)
        self.assertIsNone(erro)
        self.assertEqual((t_stop, t_alvo), (16, 32))

    def test_engasgo_NO_CLIQUE_de_enviar_admite_que_nao_sabe(self):
        """Aqui a incerteza é real: o clique pode ter saído ou não. Dizer 'não
        enviei' seria um palpite, e o palpite errado deixa uma ordem viva sem
        ninguém sabendo."""
        class _CaiNoEnviar(_BotFalso):
            def clicar_pagina(self, x, y, dry_run=False):
                if (x, y) == (10, 20) and self.campos.get("OBTER LUCRO"):
                    raise tv.ConexaoPerdida("socket abortado")
                return super().clicar_pagina(x, y, dry_run)

        bot = _CaiNoEnviar({})
        r = bot.enviar_ordem_com_atm("SELL", 7719.0, 7723.0, 7711.0, 0.25,
                                     qtd=30, enviar=True)
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("incerto"))
        self.assertIn("NÃO SEI", r["erro"])
        self.assertTrue(any("CONFIRA A PLATAFORMA" in l for l in bot.log_linhas))


class TestOAutoTrailDoTicket(unittest.TestCase):
    """19/08, ele: "ali na janela do chamado do pedido voce tem todas as
    opcoes, selecionar se e compra ou venda, stop loss, stop gain, e ainda
    trailing SE FOR O CASO".

    O "se for o caso" é o que decide o desenho. Trailing não é detalhe de
    preenchimento: "stop fixo até o alvo" e "stop que persegue" são gestões
    diferentes do mesmo trade. Por isso ele entra como opção, desligada por
    padrão — mudar a estratégia dele de carona numa correção de outra coisa
    seria a pior forma de entregar um recurso que ele pediu."""

    def test_desligado_NAO_mexe_no_auto_trail(self):
        self.assertIsNone(tv.plano_trailing(40, ligado=False))
        self.assertIsNone(tv.plano_trailing(40))

    def test_ligado_usa_a_MESMA_distancia_do_stop(self):
        """Qualquer outra distância mudaria em silêncio o risco que o Plano
        dimensionou."""
        p = tv.plano_trailing(40, ligado=True)
        self.assertEqual(p["stop"], 40)

    def test_so_comeca_a_perseguir_depois_de_1R(self):
        """Antes disso o trade ainda não pagou o próprio risco, e arrastar o
        stop ali só antecipa saída no ruído."""
        p = tv.plano_trailing(16, ligado=True)
        self.assertEqual(p["acionar"], 16)

    def test_frequencia_de_um_tick(self):
        self.assertEqual(tv.plano_trailing(40, ligado=True)["frequencia"], 1)

    def test_stop_invalido_nao_liga_trailing(self):
        for n in (0, None, -5, "abc"):
            self.assertIsNone(tv.plano_trailing(n, ligado=True), repr(n))

    def test_os_campos_do_AUTO_TRAIL_sao_escritos_no_lugar_certo(self):
        """O 'STOP LOSS' do auto trail é o SEGUNDO da tela — o primeiro é o do
        bracket. Trocar um pelo outro escreveria a distância do trail no stop
        de proteção."""
        bot = _BotFalso({})
        r = bot.enviar_ordem_com_atm(
            "SELL", 7719.0, 7723.0, 7711.0, 0.25, qtd=30, enviar=True,
            trailing=tv.plano_trailing(16, ligado=True))
        self.assertTrue(r["ok"], r.get("erro"))
        self.assertEqual(bot.campos["STOP LOSS"], 16)        # bracket
        self.assertEqual(bot.campos["STOP LOSS#1"], 16)      # auto trail
        self.assertEqual(bot.campos["ACIONAR LUCROS"], 16)
        self.assertEqual(bot.campos["FREQUÊNCIA"], 1)

    def test_sem_trailing_os_campos_do_auto_trail_NAO_sao_tocados(self):
        bot = _BotFalso({})
        bot.enviar_ordem_com_atm("SELL", 7719.0, 7723.0, 7711.0, 0.25,
                                 qtd=30, enviar=True)
        self.assertNotIn("STOP LOSS#1", bot.campos)
        self.assertNotIn("ACIONAR LUCROS", bot.campos)

    def test_campo_do_trail_que_falha_NAO_deixa_a_ordem_sair(self):
        """Metade do trailing configurado é pior que trailing nenhum."""
        bot = _BotFalso({"_campos_que_falham": ("ACIONAR LUCROS",)})
        r = bot.enviar_ordem_com_atm(
            "SELL", 7719.0, 7723.0, 7711.0, 0.25, qtd=30, enviar=True,
            trailing=tv.plano_trailing(16, ligado=True))
        self.assertFalse(r["ok"])
        self.assertIn("ACIONAR LUCROS", r["erro"])

    def test_o_app_LIGA_isso_por_um_interruptor_proprio(self):
        fonte = fonte_do_arquivo()
        self.assertIn("tv_trail_var", fonte)
        self.assertIn("plano_trailing(", fonte)
        i = fonte.index("self.tv_trail_var = ")
        self.assertIn('tv_cfg.get("trailing", False)', fonte[i:i + 200],
                      "tem de vir DESLIGADO por padrão")
        j = fonte.index('"trailing": self.tv_trail_var.get()')
        self.assertGreater(j, 0, "a escolha precisa ser gravada em disco")
