"""AUDITORIA DO LOG DE 31/08 — QUATRO GARGALOS, TODOS COM HORA MARCADA.

Ele pediu: "dê uma checada nos logs, tanto do motor quanto do TIGER IA,
encontre gargalos, corrija... o TIGER precisa conversar com o motor, com o
plano de trading e com as configurações, precisa ser tudo integrado".

1. A LEITURA INVENTADA (15:17) — A MAIS CARA
--------------------------------------------
    ❯ preciso que olhe para todos que estao selecionados
    ✳ Estou vendo o gráfico do ES (E-mini S&P 500, contrato cheio...) no 5m
      { "ticker": "ES", "structure": "DOWN", "last_bos": "BOS baixista 14:20",
        "premium_discount": { "equilibrium": "5.812,00" },
        "ob_ativo": { "faixa": "5.818,25 – 5.820,50" },
        "order_flow": { "delta_atual": "vendedor · -480 contratos" } }

NADA disso existiu. O ativo não era nenhum dos quatro monitorados, o preço
(5.812) não é o de contrato nenhum da mesa dele naquele dia — o MES estava em
7.690 — e delta, POC, VWAP e volume profile foram escritos do nada.

É PIOR QUE A ORDEM INVENTADA. Ordem inventada se desmente olhando a Tradovate.
Leitura inventada com aparência de telemetria — JSON, casas decimais, contagem
de contratos — é indistinguível de dado real, e é em cima dela que se decide
entrada.

A causa é o vazio: sem leitura no contexto, o modelo preenche. Duas correções,
porque uma só não segura: o contexto passa a trazer a PROIBIÇÃO junto do vazio,
e a saída é conferida contra o que foi lido de verdade.

2. O TRAIL MATANDO A ORDEM (13:16 e 13:55)
-------------------------------------------
    ❌ NÃO ENVIEI SELL MESU6 7 ctr @ 7695.0: campo STOP LOSS (auto trail):
       OCORRENCIA_INEXISTENTE. NENHUMA ordem foi para a plataforma.

DOIS cenários aprovados, dimensionados e anunciados, e nenhum virou ordem. O
bloco AUTO TRAIL só existe no DOM quando 'TIPO DE STOP LOSS' está em AT; fora
disso há UM rótulo 'STOP LOSS' na tela e a segunda ocorrência não existe.

Estava invertido: preço, quantidade, alvo e stop já tinham sido escritos E
CONFERIDOS — o risco estava definido e protegido. O trail só melhora a saída de
uma operação que já está certa. Trocar a operação inteira por ele é perder
dinheiro para não perder um enfeite.

3. A AUTÓPSIA DA OPERAÇÃO ERRADA (12:20)
-----------------------------------------
    [11:56] 🔴 Operação encerrada no STOP: SELL MESU6, US$-382.50.
    [12:20] ❯ o que deu errado nesse cenario ?
    [12:20] ✳ AUTÓPSIA — BUY MESU6 ... com US$+850.00

Uma operação GANHADORA em resposta a "o que deu errado". A função pegava
`fechadas[-1]` — a última linha do ARQUIVO, não a mais recente por fechamento —
e nunca olhava se a pergunta pedia o prejuízo.

4. 'JANELA' NÃO SIGNIFICAVA NADA PARA ELA (11:34 e 15:16)
----------------------------------------------------------
    ❯ qual é a janela principal ?
    ✳ A janela principal de negociação para o MESU6 é 09:30-10:30...

Ele perguntava da LISTA DE GRÁFICOS e recebeu horário de pregão. E às 15:16,
com quatro janelas configuradas: "não tenho nenhum gráfico aberto na tela".

Motor, Plano e Configurações são três abas do MESMO programa. Sem enxergar as
três, ela responde por adivinhação sobre a mesa que ela mesma opera.
"""

import os
import sys
import unittest

from harness import RAIZ, carregar, funcao_inteira

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def _fonte(nome="main_app.py"):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


NS = carregar([
    "escolher_ativo_do_rodizio",
    "censurar_leitura_inventada",
    "censurar_promessa_impossivel",
    "texto_da_mesa_multiativo",
    "registrar_leitura_do_ativo",
    "ativos_em_analise",
])
censurar = NS["censurar_leitura_inventada"]
promessa = NS["censurar_promessa_impossivel"]
texto_mesa = NS["texto_da_mesa_multiativo"]
rodizio = NS["escolher_ativo_do_rodizio"]

# O bloco que saiu de verdade no chat dele, encurtado.
TELEMETRIA_INVENTADA = '''Estou vendo o gráfico do ES (E-mini S&P 500) no 5m.
{
  "ticker": "ES",
  "structure": "DOWN",
  "premium_discount": { "equilibrium": "5.812,00" },
  "order_flow": { "delta_atual": "vendedor · -480 contratos" }
}'''


class LeituraInventadaEDenunciada(unittest.TestCase):

    def test_sem_leitura_nenhuma_o_bloco_de_telemetria_e_denunciado(self):
        """O caso literal de 15:17."""
        saida, inventou = censurar(TELEMETRIA_INVENTADA, [])
        self.assertTrue(inventou)
        self.assertIn("NÃO LI GRÁFICO NENHUM", saida)

    def test_o_aviso_diz_que_os_NUMEROS_foram_inventados(self):
        """Não basta dizer 'não li'. Ele precisa saber que aqueles preços
        específicos não valem nada — é sobre eles que se decide entrada."""
        saida, _ = censurar(TELEMETRIA_INVENTADA, [])
        self.assertIn("INVENTADO", saida)
        self.assertIn("não serve para decidir", saida)

    def test_o_aviso_diz_O_QUE_FAZER(self):
        saida, _ = censurar(TELEMETRIA_INVENTADA, [])
        self.assertIn("LIGUE O MOTOR", saida)
        self.assertIn("print", saida)

    def test_a_frase_solta_de_estar_olhando_tambem_pega(self):
        for frase in ("Estou analisando o gráfico do MESU6 agora.",
                      "Estou olhando o gráfico e vejo rejeição.",
                      "Estou vendo o gráfico do ouro no 5 minutos."):
            _s, inventou = censurar(frase, [])
            self.assertTrue(inventou, frase)

    def test_ativo_QUE_NAO_ESTA_NA_MESA_e_denunciado_mesmo_havendo_leitura(self):
        """A leitura era do MESU6 e a resposta falou do ES — foi isso que
        aconteceu: ela trocou o micro pelo contrato cheio, que negocia em
        outro preço."""
        saida, inventou = censurar(TELEMETRIA_INVENTADA, ["MESU6"])
        self.assertTrue(inventou)
        self.assertIn("NÃO ESTOU LENDO", saida)
        self.assertIn("ES", saida)
        self.assertIn("MESU6", saida)

    def test_falar_do_ativo_QUE_FOI_LIDO_passa_limpo(self):
        """A guarda não pode calar a resposta certa."""
        saida, inventou = censurar(
            "Estou analisando o gráfico do MESU6, preço 7690.", ["MESU6"])
        self.assertFalse(inventou)
        self.assertNotIn("🛑", saida)

    def test_MES_e_MESU6_sao_o_mesmo_instrumento(self):
        """Casa pela raiz: a corretora e o motor grafam o vencimento
        diferente."""
        _s, inventou = censurar("Estou vendo o gráfico do MES.", ["MESU6"])
        self.assertFalse(inventou)

    def test_com_PRINT_anexado_a_guarda_se_cala(self):
        """Quando ele anexa uma imagem ela está mesmo olhando para alguma
        coisa. Censurar ali calaria a única resposta útil."""
        _s, inventou = censurar(TELEMETRIA_INVENTADA, [], tem_imagem=True)
        self.assertFalse(inventou)

    def test_resposta_sem_leitura_nenhuma_nao_e_tocada(self):
        for frase in ("Seu drawdown de hoje é US$ 1.200,00.",
                      "O freio não está segurando nada.",
                      ""):
            saida, inventou = censurar(frase, [])
            self.assertFalse(inventou, frase)
            self.assertEqual(saida, frase)


class OVazioVemComAProibicaoJunto(unittest.TestCase):

    def test_sem_leitura_o_contexto_PROIBE_inventar(self):
        """'Nenhum gráfico lido' é verdade e não basta — vazio no contexto é
        convite para preencher, e foi o que aconteceu."""
        t = texto_mesa({}, [], agora=1_000_000.0)
        self.assertIn("NENHUM GRÁFICO FOI LIDO", t)
        self.assertIn("não invente", t.lower())

    def test_ele_lista_o_que_e_proibido_citar(self):
        t = texto_mesa({}, [], agora=1_000_000.0)
        for proibido in ("preço", "order block", "FVG", "VWAP", "delta"):
            self.assertIn(proibido, t)

    def test_e_diz_o_caminho_certo(self):
        t = texto_mesa({}, [], agora=1_000_000.0)
        self.assertIn("LIGAR O MOTOR", t)


class ElaNaoPedeDadoAoMotorPeloChat(unittest.TestCase):
    """15:41: 'Vou pedir ao motor para coletar a telemetria de todas as
    janelas ativas. Aguardando dados do sistema...' — e cinco minutos depois,
    'Ainda não recebi'. Não existe esse pedido: o motor entrega a leitura no
    contexto de cada turno. Ela inventou um canal e o deixou esperando."""

    def test_vou_pedir_ao_motor_e_barrado(self):
        _s, prometeu = promessa(
            "Vou pedir ao motor para coletar a telemetria de todas as janelas.")
        self.assertTrue(prometeu)

    def test_aguardando_dados_do_sistema_e_barrado(self):
        _s, prometeu = promessa("Aguardando dados do sistema...")
        self.assertTrue(prometeu)

    def test_frase_normal_sobre_preco_nao_e_barrada(self):
        _s, prometeu = promessa("O preço atual do MESU6 é 7690.")
        self.assertFalse(prometeu)


class OTrailNaoMataMaisAOrdem(unittest.TestCase):

    def _corpo(self):
        with open(os.path.join(RAIZ, "tradovate_auto.py"), encoding="utf-8") as f:
            fonte = f.read()
        i = fonte.index("n_obrigatorios = 3")
        return fonte[i:i + 6000]

    def test_o_campo_do_trail_e_opcional_NOS_DOIS_casos(self):
        """Era `limpando_trail and i >= n_obrigatorios`: opcional só quando
        estava ZERANDO o trail. Ligado, o campo faltando derrubava a ordem."""
        corpo = self._corpo()
        self.assertIn("opcional = i >= n_obrigatorios", corpo)
        self.assertNotIn("opcional = limpando_trail and", corpo)

    def test_os_TRES_primeiros_continuam_obrigatorios(self):
        """Unidade, alvo e stop são o risco da operação. Se esses falharem, a
        ordem NÃO pode ir — a trava original tem de continuar de pé."""
        corpo = self._corpo()
        self.assertIn("n_obrigatorios = 3", corpo)
        self.assertIn("return False", corpo)

    def test_quando_o_trail_falha_a_ordem_sai_e_ele_e_AVISADO(self):
        corpo = self._corpo()
        self.assertIn("SEM AUTO TRAIL", corpo)
        self.assertIn("SEM o auto trail", corpo)
        self.assertIn("protegida", corpo)


class AAutopsiaResponde_SOBRE_OQuePerguntaram(unittest.TestCase):

    def test_ela_aceita_preferir_o_prejuizo(self):
        corpo = funcao_inteira(_fonte(), "montar_postmortem")
        self.assertIn("preferir_prejuizo", corpo)
        self.assertIn("< 0", corpo)

    def test_a_lista_e_ordenada_POR_FECHAMENTO_nao_pela_ordem_do_arquivo(self):
        """`fechadas[-1]` é a última linha gravada. Registro importado do
        extrato entra no fim com data antiga."""
        corpo = funcao_inteira(_fonte(), "montar_postmortem")
        self.assertIn("sorted(fechadas", corpo)
        self.assertIn("data_fechamento", corpo)

    def test_o_chat_pede_o_prejuizo_quando_a_pergunta_e_o_que_deu_errado(self):
        # Há DOIS ramos POSTMORTEM: um responde sobre um cenário que ele
        # apontou pelo id (e aí o alvo já veio escolhido), o outro é a
        # pergunta solta — este. `rindex` pega o segundo.
        fonte = _fonte()
        i = fonte.rindex('if acao == "POSTMORTEM":')
        trecho = fonte[i:i + 1400]
        self.assertIn("preferir_prejuizo", trecho)
        self.assertIn("deu", trecho)


class TigerEnxergaMotorPlanoEConfiguracoes(unittest.TestCase):

    def _corpo(self):
        return funcao_inteira(_fonte(), "_chat_status_texto")

    def test_o_contexto_diz_se_a_ANALISE_esta_rodando(self):
        """`motor_rodando` é só a ponte Node ter subido. Quem analisa é
        `robo_ativo`. Olhar para a flag errada foi o que fez a mesa parecer
        viva com zero captura em duas horas."""
        corpo = self._corpo()
        self.assertIn("robo_ativo", corpo)
        self.assertIn("PARADA", corpo)

    def test_o_contexto_LISTA_as_janelas_monitoradas(self):
        """11:34: 'qual é a janela principal?' virou horário de pregão porque
        a palavra não tinha significado nenhum no contexto dela."""
        corpo = self._corpo()
        self.assertIn("janelas_monitoradas()", corpo)
        self.assertIn("não horário de pregão", corpo)

    def test_o_contexto_marca_QUAL_e_a_aba_de_execucao(self):
        self.assertIn("aba de execução", self._corpo())

    def test_o_contexto_traz_os_PISOS_do_disco(self):
        """13:04 e 13:05: a mesma pergunta devolveu 75% e depois 65% sem nada
        ter mudado na tela. Piso recitado de memória é piso inventado."""
        corpo = self._corpo()
        self.assertIn("rr_minimo", corpo)
        self.assertIn("probabilidade_minima", corpo)
        self.assertIn("não recite de", corpo)

    def test_o_contexto_traz_os_LIMITES_de_risco(self):
        corpo = self._corpo()
        self.assertIn("drawdown_maximo", corpo)
        self.assertIn("max_operacoes_dia", corpo)
        self.assertIn("max_stops_seguidos", corpo)

    def test_o_contexto_diz_se_o_AUTONOMO_esta_ligado(self):
        self.assertIn("_modo_autonomo()", self._corpo())


class OMotivoDoDescarteNaoPodeSerTROCADO(unittest.TestCase):
    """31/08, 16:20, com quatro ativos na mesa:

        📐 BUY MNQU6 descartado: stop de 96 tick(s) é largo demais...
        🔁 BUY MNQU6 @ 19412.0 é o MESMO setup já sugerido há pouco.

    Duas linhas, uma causa só. O MNQU6 tinha ACABADO de entrar na mesa e não
    havia sugestão anterior dele — o que barrou foi o stop largo, três blocos
    acima. Mas leitura congelada, stop fora de escala e entrada distante
    escrevem todos na mesma variável `repetido`, e no fim o programa imprimia
    a frase da anti-repetição para qualquer um deles.

    Ele leu aquilo como 'o robô achou que MNQU6 e MESU6 são o mesmo cenário' —
    e teria razão em desconfiar da ferramenta inteira. Motivo errado no log é
    defeito com a mesma gravidade de decisão errada: é por ele que se decide
    onde procurar."""

    def _laco(self):
        fonte = _fonte()
        i = fonte.index("repetido_por_semelhanca = False")
        return fonte[i - 2500:i + 2000]

    def test_a_anti_repeticao_tem_bandeira_PROPRIA(self):
        self.assertIn("repetido_por_semelhanca", self._laco())

    def test_so_ela_imprime_a_frase_dela(self):
        laco = self._laco()
        self.assertIn("if repetido_por_semelhanca:", laco)
        self.assertNotIn("if repetido:\n                            self.log(f\"🔁", laco)

    def test_a_comparacao_SEMPRE_foi_por_ativo(self):
        """A regra nunca cruzou ativos — quem cruzou foi a mensagem. Este
        teste existe para que ninguém 'conserte' a regra certa."""
        laco = self._laco()
        self.assertIn('str(s_ant.get("ativo", "")).upper() == str(ativo).upper()',
                      laco)

    def test_a_frase_diz_que_os_OUTROS_ativos_seguem(self):
        self.assertIn("Os outros ativos da mesa seguem normalmente",
                      self._laco())


class AAnaliseNaoDependeDoWHATSAPP(unittest.TestCase):
    """31/08: "ta parado, nao esta analisando a cada ciclo" — e, na mesma
    mensagem, "tambem nao conectei o whatsapp de proposito".

    As duas coisas eram a MESMA coisa: o laço de análise só era disparado
    dentro do ramo `if status == "CONECTADO"` do WhatsApp. Sem parear o
    celular, o robô nunca analisava, e nada na tela dizia isso — o log mostra
    o motor de pé, o ensaio da ordem OK, o diagnóstico rodando, e nenhuma
    linha '📸 Capturando' em duas horas.

    WhatsApp é CANAL DE RELATÓRIO. Análise é o produto."""

    def test_o_laco_comeca_quando_a_PORTA_do_motor_responde(self):
        fonte = _fonte()
        i = fonte.index("self.motor_confirmado = True")
        trecho = fonte[i:i + 2000]
        self.assertIn("_loop_robo_quant", trecho)
        self.assertIn("robo_ativo", trecho)

    def test_e_o_log_DIZ_que_o_whatsapp_nao_e_pre_requisito(self):
        fonte = _fonte()
        i = fonte.index("self.motor_confirmado = True")
        trecho = fonte[i:i + 2000]
        self.assertIn("canal de relatório", trecho)

    def test_o_arranque_pelo_whatsapp_nao_dispara_duas_vezes(self):
        """Os dois caminhos existem; `robo_ativo` é o que impede o segundo de
        subir uma thread duplicada analisando em paralelo."""
        fonte = _fonte()
        i = fonte.index('if status == "CONECTADO":')
        trecho = fonte[i:i + 500]
        self.assertIn("if not self.robo_ativo", trecho)


class NaoExisteMAIS_O_GRAFICO(unittest.TestCase):
    """31/08, 16:21: o motor leu os QUATRO ativos (MESU6, MNQU6, MGCV6,
    MBTU6). Às 16:23:

        ❯ quais ativos voce esta acompanhando :
        ✳ Só o MESU6. Não há outros ativos sendo monitorados no momento.

    E na resposta anterior, no mesmo minuto, a tabela dela trazia
    "Preço atual (MBTU6) 79385.0" — o ÚLTIMO ativo do laço.

    A lista multiativo já estava no contexto. O que a atropelava era o bloco
    logo abaixo: um texto longo, em prosa, chamado "ÚLTIMA ANÁLISE COMPLETA DO
    GRÁFICO", sem dizer de QUAL gráfico e sempre o da última janela. Entre uma
    lista compacta e um ensaio detalhado sobre 'o gráfico', o modelo responde
    sobre o ensaio. O nome do bloco criava um ativo principal que o motor não
    tem."""

    def _contexto(self):
        return funcao_inteira(_fonte(), "_montar_contexto_chat") \
            if "_montar_contexto_chat" in _fonte() else _fonte()

    def test_a_analise_completa_DIZ_de_qual_ativo_e(self):
        fonte = _fonte()
        self.assertIn("ANÁLISE COMPLETA DO {_qual}", fonte)
        self.assertNotIn("ÚLTIMA ANÁLISE COMPLETA DO GRÁFICO", fonte)

    def test_e_avisa_que_e_UM_dos_ativos_nao_O_grafico(self):
        fonte = _fonte()
        i = fonte.index("ANÁLISE COMPLETA DO {_qual}")
        trecho = fonte[i:i + 500]
        self.assertIn("UM dos ativos da mesa", trecho)
        self.assertIn("não 'o gráfico'", trecho)

    def test_os_indicadores_tambem_dizem_de_qual_janela_sao(self):
        fonte = _fonte()
        i = fonte.index("INDICADORES VISÍVEIS NO GRÁFICO DO")
        self.assertIn("DESSA janela", fonte[i:i + 300])

    def test_a_lista_dos_outros_ativos_tem_recorte_por_TEMPO(self):
        """Sem isso, um gráfico que ele tirou da lista de manhã continuaria
        sendo anunciado como monitorado à tarde."""
        fonte = _fonte()
        i = fonte.index("linhas_outras = [")
        trecho = fonte[max(0, i - 500):i]
        self.assertIn("ativos_em_analise(", trecho)


class OPainelPASSA_DE_UM_EM_UM(unittest.TestCase):
    """Pedido dele: "a IA TIGER precisa acompanhar a telemetria de todos,
    considere colocar um loop passando de um em um onde fica a telemetria".

    O painel tem espaço para UM ativo — é um cockpit, não uma planilha.
    Espremer quatro leituras ali deixaria as quatro ilegíveis. Então o espaço
    é dividido no TEMPO."""

    def _fila(self, *nomes):
        return [{"ativo": n, "preco": 1.0} for n in nomes]

    def test_passa_por_TODOS_e_volta_ao_primeiro(self):
        fila = self._fila("MESU6", "MGCV6", "MNQU6")
        vistos = [rodizio(fila, i)[0]["ativo"] for i in range(6)]
        self.assertEqual(vistos, ["MESU6", "MGCV6", "MNQU6"] * 2)

    def test_a_ordem_e_ALFABETICA_e_estavel(self):
        """`ativos_em_analise` devolve do mais recente para o mais velho, e
        essa ordem muda a cada ciclo — o rodízio ficaria pulando e repetindo
        em vez de passar por todos."""
        a = [rodizio(self._fila("MNQU6", "MESU6", "MGCV6"), i)[0]["ativo"]
             for i in range(3)]
        b = [rodizio(self._fila("MGCV6", "MNQU6", "MESU6"), i)[0]["ativo"]
             for i in range(3)]
        self.assertEqual(a, b)
        self.assertEqual(a, ["MESU6", "MGCV6", "MNQU6"])

    def test_devolve_a_POSICAO_e_o_TOTAL(self):
        """O contador é o que impede o painel de parecer que a mesa tem um
        ativo só — foi essa impressão que o fez perguntar três vezes se o robô
        olhava todos."""
        _l, pos, tot = rodizio(self._fila("MESU6", "MGCV6"), 1)
        self.assertEqual((pos, tot), (2, 2))

    def test_um_ativo_so_nao_gira(self):
        for i in range(3):
            leitura, pos, tot = rodizio(self._fila("MESU6"), i)
            self.assertEqual((leitura["ativo"], pos, tot), ("MESU6", 1, 1))

    def test_sem_leitura_nenhuma_devolve_vazio_sem_estourar(self):
        self.assertEqual(rodizio([], 0), (None, 0, 0))
        self.assertEqual(rodizio(None, 5), (None, 0, 0))

    def test_leitura_sem_ticker_nao_entra_no_rodizio(self):
        fila = self._fila("MESU6") + [{"preco": 9.0}]
        _l, _pos, tot = rodizio(fila, 0)
        self.assertEqual(tot, 1)

    def test_o_painel_avanca_o_rodizio_a_cada_atualizacao(self):
        corpo = funcao_inteira(_fonte(), "_atualizar_telemetria_hud_embutido")
        self.assertIn("escolher_ativo_do_rodizio(", corpo)
        self.assertIn("_passo_rodizio_hud", corpo)

    def test_o_painel_MOSTRA_o_contador(self):
        corpo = funcao_inteira(_fonte(), "_atualizar_telemetria_hud_embutido")
        self.assertIn("{_pos}/{_tot}", corpo)


class AGuardaEstaLIGADANoFluxoDoChat(unittest.TestCase):

    def test_censurar_leitura_inventada_roda_no_pipeline(self):
        fonte = _fonte()
        i = fonte.index("resposta, inventou_acao = censurar_acao_inventada")
        trecho = fonte[i:i + 3000]
        self.assertIn("censurar_leitura_inventada(", trecho)

    def test_ela_recebe_os_ativos_REALMENTE_lidos(self):
        fonte = _fonte()
        i = fonte.index("censurar_leitura_inventada(\n")
        trecho = fonte[max(0, i - 700):i + 300]
        self.assertIn("ativos_em_analise(", trecho)

    def test_ela_sabe_quando_ha_imagem_anexada(self):
        fonte = _fonte()
        i = fonte.index("censurar_leitura_inventada(\n")
        self.assertIn("tem_imagem", fonte[i:i + 300])


if __name__ == "__main__":
    unittest.main(verbosity=2)
