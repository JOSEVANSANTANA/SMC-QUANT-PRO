"""O RELATÓRIO QUE CHEGAVA PELA METADE, O TICKER COMIDO E O TEMPO DA VELA.

Quatro coisas dele, no mesmo dia (04/09), e todas com a mesma cara: o
programa AFIRMAVA algo com convicção e o algo estava errado.

1. "OS RELATÓRIOS NÃO ESTÃO CHEGANDO COMPLETOS NO WHATSAPP" — e mandou o
   print: a análise termina em "O preço está testando uma zona de oferta en".
   Morre no meio da palavra "entre". Não foi o WhatsApp; era um `[:400]`.
   Quatrocentos caracteres cravados no meio do raciocínio que é justamente o
   PORQUÊ da sugestão — a parte pela qual ele decide acatar estando longe da
   mesa. Meio raciocínio é pior que nenhum: parece inteiro.

2. O ticker. A manhã inteira o log dizia "Ativo: ESU6" num gráfico de MESU6.
   O modelo comeu o M. Num contrato de US$50/ponto (dez vezes o micro), um
   stop de 8 pontos vira US$400 de risco e o plano dele autoriza US$100 —
   ZERO contrato, cenário atrás de cenário. E às 09:35 o robô chegou a TROCAR
   o instrumento do ticket na Tradovate para o contrato cheio.

3. O tempo gráfico. "Estou considerando mudar o meu timeframe de análise para
   10 minutos, a ferramenta também já possui capacidade além de 5 minutos?"
   Lia qualquer um — mas AFIRMAVA 5m ao modelo em toda análise, com um
   exemplo de vela fechada escrito à mão ("se a hora atual for 11:40...").

4. Os comandos. "Considere incluir comandos na interação com WhatsApp, por
   exemplo status, print, relatório telemetria, compro onde, vendo onde, onde
   é o stop." São para usar LONGE da mesa, que é quando ele não pode
   conferir — então nenhum deles pode passar por modelo.

E o quinto, que não é pedido dele e sim um estouro no log dele: às 12:35,
`'NoneType' object has no attribute 'startswith'`. Duas leituras perdidas
porque `get("conta", "")` devolve None quando a chave EXISTE com valor None.
"""

import datetime
import os
import unittest

from harness import carregar, fonte_do_arquivo, funcao_inteira

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ns():
    return carregar(["partir_para_whatsapp", "confundiu_micro_com_cheio",
                     "raiz_do_contrato", "timeframe_do_plano",
                     "texto_do_timeframe"],
                    stubs={"plano_da_conta_ativa": lambda: {}})


class TestARelatorioNaoChegaPelaMetade(unittest.TestCase):
    """A frase dele: 'a análise está cortando em: O preço está testando uma
    zona de oferta en'."""

    def test_mensagem_curta_sai_inteira_e_sem_numeracao(self):
        ns = _ns()
        self.assertEqual(ns["partir_para_whatsapp"]("oi", 3000), ["oi"])

    def test_texto_vazio_nao_vira_mensagem_em_branco(self):
        ns = _ns()
        for vazio in ("", None, "   "[:0]):
            self.assertEqual(ns["partir_para_whatsapp"](vazio, 3000), [])

    def test_NENHUM_CARACTER_SE_PERDE(self):
        """A regra que o `[:400]` quebrava. Junte os pedaços de volta e o
        texto tem de estar todo lá — é a única prova que interessa."""
        ns = _ns()
        texto = ("O preço está testando uma zona de oferta entre 7720 e 7735. "
                 * 60)
        partes = ns["partir_para_whatsapp"](texto, 400)
        self.assertGreater(len(partes), 1)
        limpo = "".join(p.split("\n\n— (")[0] for p in partes)
        self.assertEqual(
            "".join(limpo.split()), "".join(texto.split()),
            "algum trecho da análise se perdeu no caminho")

    def test_a_palavra_nao_e_partida_no_meio_quando_ha_respiro(self):
        ns = _ns()
        texto = ("O preço está testando uma zona de oferta entre 7720 e 7735. "
                 * 40)
        for p in ns["partir_para_whatsapp"](texto, 300):
            corpo = p.split("\n\n— (")[0]
            self.assertFalse(corpo.endswith("en"),
                             "cortou no meio de 'entre' — o defeito de 04/09")

    def test_cada_pedaco_diz_qual_e_de_quantos(self):
        """Sem isso, três mensagens seguidas no celular parecem três
        relatórios diferentes."""
        ns = _ns()
        partes = ns["partir_para_whatsapp"]("linha. " * 400, 500)
        total = len(partes)
        for i, p in enumerate(partes, 1):
            self.assertTrue(p.rstrip().endswith(f"— ({i}/{total})"), p[-30:])

    def test_nenhum_pedaco_estoura_muito_o_limite(self):
        ns = _ns()
        for p in ns["partir_para_whatsapp"]("palavra " * 900, 400):
            self.assertLessEqual(len(p), 400 + 40)   # + o rodapé "— (i/n)"

    def test_texto_sem_nenhum_espaco_ainda_assim_e_partido(self):
        """Último recurso: sem respiro nenhum, corta no limite — mas continua
        entregando o texto inteiro, em vez de jogar o resto fora."""
        ns = _ns()
        texto = "A" * 1000
        partes = ns["partir_para_whatsapp"](texto, 300)
        self.assertGreater(len(partes), 1)
        self.assertEqual(
            len("".join(p.split("\n\n— (")[0] for p in partes)), 1000)

    def test_limite_absurdo_nao_derruba(self):
        ns = _ns()
        for limite in (None, 0, -5, "muito", 3):
            self.assertIsInstance(ns["partir_para_whatsapp"]("x " * 500,
                                                             limite), list)

    def test_o_CORTE_DE_400_SAIU_do_relatorio(self):
        fonte = fonte_do_arquivo()
        self.assertNotIn('market_analysis\', \'\')[:400]', fonte)
        self.assertNotIn('market_analysis", "")[:400]', fonte)

    def test_o_envio_PARTE_em_vez_de_truncar(self):
        corpo = funcao_inteira(fonte_do_arquivo(), "enviar_relatorio_whatsapp")
        self.assertIn("partir_para_whatsapp(mensagem)", corpo)

    def test_o_grafico_vai_UMA_vez_so(self):
        """Repetir a imagem em cada pedaço encheria a conversa dele de prints
        iguais do mesmo gráfico."""
        corpo = funcao_inteira(fonte_do_arquivo(), "enviar_relatorio_whatsapp")
        self.assertIn("if i == 0 and imagem64:", corpo)


class TestMicroOuCheioSaoDezVezesODinheiro(unittest.TestCase):

    def test_ES_lido_num_grafico_de_MES_e_corrigido(self):
        ns = _ns()
        corrigido, motivo = ns["confundiu_micro_com_cheio"]("ESU6", "MESU6")
        self.assertEqual(corrigido, "MESU6")
        self.assertIn("dez vezes", motivo)

    def test_vale_para_os_quatro_contratos_da_mesa(self):
        ns = _ns()
        for lido, real in (("ESU6", "MESU6"), ("NQU6", "MNQU6"),
                           ("GCV6", "MGCV6"), ("BTCU6", "MBTU6")):
            corrigido, _ = ns["confundiu_micro_com_cheio"](lido, real)
            self.assertEqual(corrigido, real, f"{lido} não virou {real}")

    def test_corrige_TAMBEM_no_sentido_contrario(self):
        """Se um dia ele operar o cheio, ler o micro é o mesmo erro com o
        prejuízo do outro lado: dimensiona dez vezes contratos demais."""
        ns = _ns()
        corrigido, _ = ns["confundiu_micro_com_cheio"]("MESU6", "ESU6")
        self.assertEqual(corrigido, "ESU6")

    def test_ativo_certo_NAO_e_mexido(self):
        ns = _ns()
        self.assertEqual(
            ns["confundiu_micro_com_cheio"]("MESU6", "MESU6")[0], None)

    def test_ativos_QUE_SO_SAO_DIFERENTES_nao_sao_assunto_desta_funcao(self):
        """MNQ num gráfico de MES não é 'comeu uma letra' — é outra coisa, e
        trocar o ticker aqui esconderia o problema de verdade."""
        ns = _ns()
        for lido, ref in (("MNQU6", "MESU6"), ("MGCV6", "MBTU6"),
                          ("MESU6", "MNQU6")):
            self.assertIsNone(ns["confundiu_micro_com_cheio"](lido, ref)[0],
                              f"{lido} vs {ref} não é par micro/cheio")

    def test_sem_referencia_ela_nao_inventa_nada(self):
        """Quando a plataforma não respondeu, não há autoridade para corrigir
        coisa nenhuma — e chutar seria trocar um ticker por adivinhação."""
        ns = _ns()
        for ref in (None, "", "DESCONHECIDO", "Claude — Claude"):
            self.assertIsNone(ns["confundiu_micro_com_cheio"]("ESU6", ref)[0])
        for lido in (None, "", "DESCONHECIDO"):
            self.assertIsNone(ns["confundiu_micro_com_cheio"](lido, "MESU6")[0])

    def test_a_correcao_ACONTECE_antes_de_dimensionar(self):
        """Corrigir depois do cálculo de contratos não serviria de nada: o
        'ZERO contrato' de 04/09 já teria acontecido — é o dimensionamento que
        lê o valor por ponto do ativo, e é ele que precisa do ticker certo."""
        fonte = fonte_do_arquivo()
        i_corr = fonte.index(
            "_corrigido, _porque_ativo = confundiu_micro_com_cheio")
        i_size = fonte.index("sizing = dimensionar_pelo_plano(", i_corr)
        i_leitura = fonte.index('ativo = sinal.get("asset_symbol"', 0)
        self.assertLess(i_leitura, i_corr, "corrigiu antes de ler o ticker")
        self.assertLess(i_corr, i_size)

    def test_a_correcao_reescreve_o_sinal_e_nao_so_a_variavel(self):
        """O `sinal` inteiro segue viagem para o diário, para o ticket e para
        o WhatsApp. Corrigir só a variável local deixaria ESU6 em todos eles."""
        fonte = fonte_do_arquivo()
        i = fonte.index('_corrigido, _porque_ativo = confundiu_micro_com_cheio')
        trecho = fonte[i:i + 800]
        self.assertIn('sinal["asset_symbol"] = _corrigido', trecho)
        self.assertIn("ATIVO CORRIGIDO", trecho)

    def test_a_referencia_vem_da_PLATAFORMA(self):
        fonte = fonte_do_arquivo()
        i = fonte.index('_corrigido, _porque_ativo = confundiu_micro_com_cheio')
        self.assertIn("self._ativo_da_fita()", fonte[i - 400:i])


class TestOTempoDaVelaDeixaDeSerCravado(unittest.TestCase):
    """'A ferramenta também já possui capacidade para análises e sugestões
    além do timeframe de 5 minutos?'"""

    def test_o_plano_manda(self):
        ns = _ns()
        self.assertEqual(ns["timeframe_do_plano"]({"timeframe_min": 10}), 10)
        self.assertEqual(ns["timeframe_do_plano"]({"timeframe_min": 15}), 15)

    def test_o_padrao_continua_5(self):
        ns = _ns()
        for plano in ({}, {"timeframe_min": None}, {"timeframe_min": 0}, None):
            self.assertEqual(ns["timeframe_do_plano"](plano), 5)

    def test_valor_estranho_volta_ao_padrao_em_vez_de_virar_afirmacao(self):
        """7 minutos não é tempo gráfico de ninguém. Se entrasse, o pedido ao
        modelo passaria a AFIRMAR 7m — o mesmo defeito, só que ao contrário."""
        ns = _ns()
        for ruim in ("dez", 7, -5, 999, [], {"a": 1}):
            self.assertEqual(ns["timeframe_do_plano"]({"timeframe_min": ruim}), 5)

    def test_dez_minutos_e_um_tempo_aceito(self):
        """O que ele disse que ia usar."""
        ns = carregar(["TIMEFRAMES_ACEITOS"])
        self.assertIn(10, ns["TIMEFRAMES_ACEITOS"])

    def test_a_ultima_vela_fechada_e_CALCULADA(self):
        ns = _ns()
        agora = datetime.datetime(2026, 9, 4, 11, 43, 20)
        t5 = ns["texto_do_timeframe"]({"timeframe_min": 5}, agora)
        self.assertIn("11:40", t5)
        t10 = ns["texto_do_timeframe"]({"timeframe_min": 10}, agora)
        self.assertIn("11:40", t10)
        t15 = ns["texto_do_timeframe"]({"timeframe_min": 15}, agora)
        self.assertIn("11:30", t15)

    def test_o_texto_diz_o_tempo_do_plano(self):
        ns = _ns()
        agora = datetime.datetime(2026, 9, 4, 11, 43, 20)
        self.assertIn("10 minuto", ns["texto_do_timeframe"](
            {"timeframe_min": 10}, agora))

    def test_o_EXEMPLO_DE_5m_ESCRITO_A_MAO_SUMIU_dos_pedidos(self):
        fonte = fonte_do_arquivo()
        i_defaults = fonte.index('"timeframe_min": 5,')
        depois = fonte[i_defaults:]
        self.assertNotIn("O gráfico opera em timeframe de 5 minutos", depois)

    def test_os_DOIS_pedidos_ao_modelo_recebem_o_tempo_certo(self):
        """A análise do gráfico E a conversa. Só um dos dois deixaria o robô
        dizendo uma coisa na tela e outra no chat."""
        self.assertEqual(fonte_do_arquivo().count("texto_do_timeframe()"), 2)

    def test_ele_CONSEGUE_MUDAR_pela_tela(self):
        fonte = fonte_do_arquivo()
        self.assertIn('"entry_timeframe", "timeframe_min"', fonte)
        self.assertIn('(self.entry_timeframe, "timeframe_min", 5)', fonte)

    def test_a_tela_RECUSA_um_tempo_que_o_motor_nao_conhece(self):
        """Gravar 7 no plano faria a validação da leitura devolver 5 e o campo
        mostrar 7: a tela mentindo sobre o que o motor usa."""
        fonte = fonte_do_arquivo()
        i = fonte.index("self.entry_timeframe.get()")
        trecho = fonte[i:i + 700]
        self.assertIn("not in TIMEFRAMES_ACEITOS", trecho)
        self.assertIn("Mantive o que estava", trecho)


class TestOsComandosDoWhatsApp(unittest.TestCase):
    """'Considere incluir comandos na interação com WhatsApp, por exemplo
    status, print, relatório telemetria, compro onde, vendo onde, onde é o
    stop etc.'"""

    def _motor(self):
        with open(os.path.join(RAIZ, "motor", "index.js"),
                  encoding="utf-8") as fh:
            return fh.read()

    def test_o_motor_RECONHECE_as_palavras_que_ele_escreveria(self):
        js = self._motor()
        for palavra in ("'TELEMETRIA'", "'PRINT'", "'RELATORIO'",
                        "'COMPRO ONDE'", "'VENDO ONDE'", "'ONDE É O STOP'"):
            self.assertIn(palavra, js, f"{palavra} não é reconhecida")

    def test_cada_comando_ENTRA_na_lista_de_comandos_do_motor(self):
        """Palavra reconhecida que não entra em `ehComando` é mensagem que o
        motor ignora em silêncio — o pior desfecho possível."""
        js = self._motor()
        i = js.index("const ehComando")
        trecho = js[i:i + 800]
        for lista in ("CMD_TELEMETRIA.includes", "CMD_PRINT.includes",
                      "CMD_RELATORIO.includes", "CMD_ONDE.includes"):
            self.assertIn(lista, trecho)

    def test_cada_comando_VIRA_UM_PEDIDO_NA_FILA(self):
        js = self._motor()
        for tipo in ("TELEMETRIA", "PRINT", "RELATORIO", "ONDE"):
            self.assertIn(f"filaComandos.push({{ tipo: '{tipo}'",
                          js, f"{tipo} não vai para a fila")

    def test_o_python_ATENDE_os_quatro(self):
        """Comando na fila que o app não trata fica preso lá para sempre e ele
        fica olhando o celular esperando resposta."""
        fonte = fonte_do_arquivo()
        self.assertIn('if tipo in ("TELEMETRIA", "RELATORIO", "ONDE", "PRINT"):',
                      fonte)

    def test_pedido_VELHO_na_fila_nao_e_atendido(self):
        """Mesma regra do ACATAR: comando que ficou preso enquanto o app estava
        fechado não vale mais — o mercado já é outro."""
        fonte = fonte_do_arquivo()
        i = fonte.index('if tipo in ("TELEMETRIA", "RELATORIO", "ONDE", "PRINT"):')
        trecho = fonte[i:i + 900]
        self.assertIn("> 120000", trecho)
        self.assertIn("obsoleto na fila", trecho)

    def test_NENHUM_dos_quatro_passa_por_modelo(self):
        """São para usar longe da mesa, que é justamente quando ele não pode
        conferir. E continuam funcionando com a cota da API estourada."""
        for nome in ("_texto_telemetria_whatsapp", "_texto_relatorio_whatsapp",
                     "_texto_niveis_whatsapp"):
            corpo = funcao_inteira(fonte_do_arquivo(), nome)
            for proibido in ("requests.post", "chamar_ia", "generateContent",
                             "openrouter", "gemini_"):
                self.assertNotIn(proibido, corpo,
                                 f"{nome} está passando por modelo")

    def test_uma_falha_do_comando_NAO_derruba_o_motor(self):
        fonte = fonte_do_arquivo()
        i = fonte.index('if tipo in ("TELEMETRIA", "RELATORIO", "ONDE", "PRINT"):')
        trecho = fonte[i:i + 1400]
        self.assertIn("except Exception as e:", trecho)
        self.assertIn("Abra o app", trecho)

    def test_ONDE_sem_cenario_DIZ_QUE_NAO_HA_em_vez_de_inventar(self):
        """A pergunta é 'compro onde'. Um nível inventado numa resposta que
        chega no celular é a família de defeito mais cara deste projeto."""
        corpo = funcao_inteira(fonte_do_arquivo(), "_texto_niveis_whatsapp")
        self.assertIn("Não há cenário valendo agora", corpo)
        self.assertIn("Não vou inventar", corpo)

    def test_ONDE_responde_com_ENTRADA_STOP_e_ALVO(self):
        corpo = funcao_inteira(fonte_do_arquivo(), "_texto_niveis_whatsapp")
        for pedaco in ("entro em", "stop em", "alvo em"):
            self.assertIn(pedaco, corpo)

    def test_ONDE_olha_a_posicao_VIVA_antes_da_sugestao_pendente(self):
        """O que já está na mesa vale mais que o que ainda está esperando
        decisão: é onde o dinheiro dele está agora."""
        corpo = funcao_inteira(fonte_do_arquivo(), "_texto_niveis_whatsapp")
        self.assertLess(corpo.index("carregar_posicoes()"),
                        corpo.index("_ultimo_sinal_pendente()"))

    def test_PRINT_manda_a_imagem_QUE_FOI_ANALISADA(self):
        """Uma captura nova responderia 'como está agora'. A pergunta dele é
        'o que você está vendo' — que é outra coisa, e é a que permite
        conferir se o robô está olhando o gráfico certo."""
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_responder_print_no_whatsapp")
        self.assertIn("ULTIMO_PRINT_FILE", corpo)
        self.assertNotIn("capturar_janela", corpo)
        self.assertIn("MESMA", corpo)

    def test_PRINT_sem_captura_EXPLICA_em_vez_de_emudecer(self):
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_responder_print_no_whatsapp")
        self.assertIn("Ainda não tenho nenhuma captura", corpo)

    def test_RELATORIO_leva_o_tempo_grafico_e_o_drawdown_que_resta(self):
        corpo = funcao_inteira(fonte_do_arquivo(), "_texto_relatorio_whatsapp")
        self.assertIn("timeframe_do_plano(plano)", corpo)
        self.assertIn("drawdown_restante_hoje", corpo)


class TestOEstouroQueCOMEUDUASLEITURAS(unittest.TestCase):
    """04/09 12:35, no log dele:

        main_app.py:27019 ('NoneType' object has no attribute 'startswith')

    `dict.get(k, "")` devolve None quando a chave EXISTE com valor None — o
    padrão só cobre a chave AUSENTE. A leitura do ambiente devolvia
    `{"conta": None}` e o ciclo inteiro morria ali."""

    def test_conta_None_nao_estoura_na_deteccao_de_replay(self):
        for amb in ({"conta": None}, {}, {"conta": ""},
                    {"conta": "RPL-123"}, {"conta": 12345}):
            conta = str(amb.get("conta") or "")
            self.assertIsInstance(conta.startswith("RPL"), bool)

    def test_o_codigo_usa_OR_e_nao_o_padrao_do_get(self):
        fonte = fonte_do_arquivo()
        self.assertIn('_conta_amb = str(_amb_tv.get("conta") or "")', fonte)
        self.assertNotIn('_amb_tv.get("conta", "").startswith', fonte)

    def test_replay_continua_sendo_detectado_pelos_DOIS_caminhos(self):
        """A bandeira explícita e o prefixo da conta. Perder um dos dois
        deixaria uma conta de treino passando por conta real."""
        fonte = fonte_do_arquivo()
        i = fonte.index('_conta_amb = str(_amb_tv.get("conta") or "")')
        trecho = fonte[i:i + 300]
        self.assertIn('_amb_tv.get("eh_replay")', trecho)
        self.assertIn('_conta_amb.startswith("RPL")', trecho)


if __name__ == "__main__":
    unittest.main(verbosity=2)
