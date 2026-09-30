"""ATR DE VERDADE, SEM ABRIR PAINEL NENHUM.

A PERGUNTA QUE ISTO RESPONDE
-----------------------------
A régua de stop hoje é uma faixa FIXA por contrato (MES: 12 a 60 ticks). Ela
resolveu o caos de 23/08 — stops de 19 · 30 · 32 · 33 · 48 · 76 · 76 · 106
ticks no mesmo contrato e no mesmo dia. Mas é fixa: num dia parado, 60 ticks
é largo demais; num dia de FOMC, 60 é apertado demais.

O ATR move a faixa junto com o mercado. Para isso é preciso OHLC numérico, e
o motor lê o gráfico como IMAGEM — pixel não tem preço.

POR QUE NÃO SAIU DE UM PAINEL DE CANDLES
-----------------------------------------
Ele chegou a montar um gráfico de 15m no layout para isso. Não serve, por dois
motivos independentes:

  · gráfico de corretora é desenhado em `<canvas>` — um bitmap. Não existe nó
    de DOM por candle para o CDP ler. Abrir o painel não cria o dado;

  · e custou resolução ao gráfico principal, que é o que a IA de fato lê.

A fita (Time & Sales) já entrega, negócio a negócio, PREÇO, TAMANHO e HORA —
a matéria-prima exata de um candle. Agrupar por janela de tempo é aritmética.
Zero pixel, zero painel novo, e serve 1m, 5m e 15m da mesma leitura.

O QUE ISTO NÃO É
-----------------
Histórico. Os candles começam quando o robô começa a olhar. Um ATR de 14
períodos em 5m precisa de ~70 min de fita antes de significar alguma coisa —
e por isso ele entra em MODO OBSERVAÇÃO: mede, registra ao lado da faixa fixa,
e não recusa cenário nenhum. Trocar uma régua que funciona por uma que ainda
está aquecendo seria a mesma pressa que este projeto passou a semana desfazendo.
"""

import unittest

from harness import RAIZ, fonte_do_arquivo, funcao_inteira, carregar  # noqa: F401
import sys

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from order_flow import (agregar_candles, atr_de_candles,      # noqa: E402
                        faixa_de_stop_por_atr)


def _fita(precos, t0=1_700_000_000, passo=3, tam=5):
    """Uma fita sintética: um negócio a cada `passo` segundos."""
    return [{"preco": p, "tamanho": tam, "ts": t0 + i * passo}
            for i, p in enumerate(precos)]


class TestOsCandlesSaemDaFita(unittest.TestCase):

    def test_um_candle_por_janela_de_tempo(self):
        """5 min = 300 s. Com um negócio a cada 60 s, 12 negócios = 3 candles
        (0-299, 300-599, 600-659)."""
        neg = _fita([7550.0] * 12, passo=60)
        self.assertEqual(len(agregar_candles(neg, minutos=5)), 3)

    def test_o_OHLC_bate_com_os_negocios(self):
        neg = _fita([7550.0, 7553.0, 7548.0, 7551.0], passo=10)
        c = agregar_candles(neg, minutos=5)[0]
        self.assertEqual(c["abertura"], 7550.0)
        self.assertEqual(c["maxima"], 7553.0)
        self.assertEqual(c["minima"], 7548.0)
        self.assertEqual(c["fechamento"], 7551.0)

    def test_o_volume_soma_os_tamanhos(self):
        neg = _fita([7550.0, 7551.0], passo=10, tam=7)
        self.assertEqual(agregar_candles(neg, minutos=5)[0]["volume"], 14.0)

    def test_vem_do_mais_antigo_para_o_mais_novo(self):
        neg = _fita([7550.0] * 12, passo=60)
        c = agregar_candles(neg, minutos=5)
        self.assertEqual([x["inicio"] for x in c], sorted(x["inicio"] for x in c))

    def test_a_mesma_fita_serve_para_QUALQUER_timeframe(self):
        """É o ponto de tirar da fita em vez do painel: 5m e 15m saem da
        mesma leitura, sem abrir gráfico nenhum."""
        neg = _fita([7550.0] * 60, passo=60)     # 60 minutos
        self.assertGreater(len(agregar_candles(neg, minutos=5)),
                           len(agregar_candles(neg, minutos=15)))

    def test_negocio_sem_preco_ou_sem_hora_e_descartado(self):
        """Inventar a hora seria inventar o candle."""
        self.assertEqual(agregar_candles(
            [{"preco": None, "ts": 1}, {"preco": 7550, "ts": None},
             {"preco": 0, "ts": 1}, {"preco": "abc", "ts": 1}], 5), [])

    def test_fita_vazia_nao_levanta(self):
        for vazio in ([], None):
            self.assertEqual(agregar_candles(vazio, 5), [])
        self.assertEqual(agregar_candles(_fita([7550.0]), minutos=0), [])


class TestOATRSoSaiQuandoTemLASTRO(unittest.TestCase):
    """`None` é resposta legítima. Um ATR de três candles é um número que
    parece medida e não é — e ele dimensionaria stop de verdade."""

    def _candles(self, n):
        # 300s por candle; 100 negócios por candle a cada 3s.
        precos, p = [], 7550.0
        for i in range(n * 100):
            p += 0.25 if (i // 7) % 2 else -0.25
            precos.append(round(p, 2))
        return agregar_candles(_fita(precos, passo=3), minutos=5)

    def test_sem_candle_suficiente_devolve_None(self):
        self.assertIsNone(atr_de_candles(self._candles(5), 14))
        self.assertIsNone(atr_de_candles([], 14))
        self.assertIsNone(atr_de_candles(None, 14))

    def test_com_lastro_devolve_numero_positivo(self):
        atr = atr_de_candles(self._candles(30), 14)
        self.assertIsNotNone(atr)
        self.assertGreater(atr, 0)

    def test_o_candle_EM_FORMACAO_fica_de_fora(self):
        """A máxima e a mínima dele ainda crescem até o fim da janela. Incluí-lo
        faria o ATR encolher e crescer sozinho dentro do mesmo período, sem o
        mercado ter mudado."""
        c = self._candles(30)
        aberto = dict(c[-1])
        c_com_pico = c[:-1] + [dict(aberto, maxima=aberto["maxima"] + 500)]
        self.assertEqual(atr_de_candles(c, 14),
                         atr_de_candles(c_com_pico, 14))

    def test_mercado_mais_volatil_da_ATR_maior(self):
        estreito = [{"inicio": i * 300, "abertura": 7550, "maxima": 7551,
                     "minima": 7549, "fechamento": 7550} for i in range(20)]
        largo = [{"inicio": i * 300, "abertura": 7550, "maxima": 7560,
                  "minima": 7540, "fechamento": 7550} for i in range(20)]
        self.assertGreater(atr_de_candles(largo, 14),
                           atr_de_candles(estreito, 14))

    def test_candle_corrompido_nao_derruba_a_conta(self):
        c = [{"inicio": i * 300, "abertura": 7550, "maxima": 7552,
              "minima": 7548, "fechamento": 7550} for i in range(20)]
        c[5] = {"inicio": 1500, "maxima": None, "minima": "x", "fechamento": None}
        self.assertIsNotNone(atr_de_candles(c, 14))


class TestAFaixaQueOATRSugere(unittest.TestCase):

    def test_a_faixa_sai_em_TICKS(self):
        """ATR de 3 pts no MES (tick 0,25): 0,8x = 2,4 pts = 10 ticks;
        2,5x = 7,5 pts = 30 ticks."""
        self.assertEqual(faixa_de_stop_por_atr(3.0, 0.25), (10, 30))

    def test_mercado_calmo_aperta_a_faixa(self):
        calmo = faixa_de_stop_por_atr(1.5, 0.25)
        agitado = faixa_de_stop_por_atr(6.0, 0.25)
        self.assertLess(calmo[1], agitado[1])

    def test_sem_ATR_ou_sem_tick_NAO_inventa_faixa(self):
        self.assertIsNone(faixa_de_stop_por_atr(None, 0.25))
        self.assertIsNone(faixa_de_stop_por_atr(3.0, None))
        self.assertIsNone(faixa_de_stop_por_atr(0, 0.25))
        self.assertIsNone(faixa_de_stop_por_atr(3.0, 0))
        self.assertIsNone(faixa_de_stop_por_atr("abc", 0.25))

    def test_o_minimo_e_menor_que_o_maximo(self):
        for atr in (0.5, 2.0, 5.0, 20.0):
            lo, hi = faixa_de_stop_por_atr(atr, 0.25)
            self.assertLess(lo, hi)


class TestOATREOBSERVACAOENaoDecisao(unittest.TestCase):
    """O ponto mais importante deste arquivo."""

    def _corpo(self):
        # FUNÇÃO INTEIRA, não uma janela de bytes. A janela de 3.200 bytes
        # quebrou sozinha no dia em que a função ganhou comentário — e um
        # teste que reprova documentação ensina a não documentar.
        return funcao_inteira(fonte_do_arquivo(), "_medir_atr_em_observacao")

    def test_ele_NAO_recusa_cenario(self):
        """Quem recusa continua sendo `avaliar_tamanho_do_stop` com a faixa
        fixa. Se um dia isto aqui passar a barrar, é decisão consciente e
        este teste tem de ser reescrito — não silenciado."""
        corpo = self._corpo()
        self.assertNotIn("repetido = True", corpo)
        self.assertNotIn("return False", corpo)

    def test_ele_mostra_os_DOIS_numeros_lado_a_lado(self):
        """É assim que a troca deixa de ser aposta: depois de alguns pregões
        os dois ficam no log e a comparação é dado, não opinião."""
        corpo = self._corpo()
        self.assertIn("faixa_de_stop_do_ativo(ativo)", corpo)
        self.assertIn("faixa fixa em uso", corpo)
        # A frase mudou em 31/08 (o ATR passou a calibrar o trailing), mas a
        # afirmação que ela precisa carregar é a mesma: quem RECUSA cenário
        # continua sendo a faixa fixa.
        self.assertIn("faixa fixa", corpo)
        self.assertIn("recusa cenário", corpo)

    def test_o_ATR_e_guardado_COM_DONO_E_COM_HORA(self):
        """31/08. Existia um `self._ultimo_atr` só, sem ativo e sem hora, e
        alguém o dividiu pelo tick do ativo DA ORDEM para calibrar trailing.
        Numa mesa de quatro janelas isso é o ATR do bitcoin virando distância
        de stop do MES. Guardar por ativo e com carimbo de hora é o que torna
        a pergunta 'esse número é DESTE contrato?' possível de responder."""
        corpo = self._corpo()
        self.assertIn("_atr_por_ativo", corpo)
        self.assertIn('"ts"', corpo)
        self.assertIn("raiz_do_contrato(ativo)", corpo)

    def test_balde_de_UM_contrato_so(self):
        """Um contrato não varia 25% em meia hora. Se o balde variou, ali
        dentro tem mais de um instrumento — e o ATR disso não é um número
        grande, é lixo com cara de número."""
        corpo = self._corpo()
        self.assertIn("1.25", corpo)
        self.assertIn("_avisou_fita_misturada", corpo)

    def test_a_fita_e_guardada_COM_O_ATIVO_DELA(self):
        """O 'Chamado do pedido' e a fita são o mesmo painel, e o robô troca
        o instrumento dele a cada envio. Um balde só, sem dono, mistura MES a
        7.600 com MBT a 79.000 no mesmo candle."""
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_guardar_negocios_para_candles")
        self.assertIn("_negocios_por_ativo", corpo)
        self.assertIn("ativo", corpo.split("\n")[0])   # o ativo é PARÂMETRO

    def test_ele_diz_quanto_falta_para_aquecer(self):
        """Silêncio deixaria ele sem saber se está aquecendo ou quebrado."""
        corpo = self._corpo()
        self.assertIn("aquecendo", corpo)
        self.assertIn("faltam", corpo)

    def test_o_aviso_de_aquecimento_sai_UMA_vez(self):
        """A cada ciclo seria a linha repetida que esconde o resto do log."""
        self.assertIn("_avisou_atr_aquecendo", self._corpo())

    def test_esta_LIGADO_no_ciclo(self):
        """Função que existe e não é chamada é o `self.order_flow` de novo."""
        fonte = fonte_do_arquivo()
        self.assertIn("self._medir_atr_em_observacao(", fonte)
        i = fonte.index("_n_fluxo, _ = self._coletar_order_flow()")
        self.assertIn("_medir_atr_em_observacao", fonte[i:i + 900])

    def test_os_negocios_SEM_LADO_tambem_viram_candle(self):
        """O delta descarta negócio sem lado, e com razão. Mas OHLC não
        precisa de lado — precisa de preço, tamanho e hora. Descartar aqui
        faria o candle nascer com buraco e o ATR sair menor que o mercado."""
        fonte = fonte_do_arquivo()
        i = fonte.index("self._guardar_negocios_para_candles(novos")
        j = fonte.index("lado = fita.classificar_agressao(", i - 3000)
        self.assertLess(i, j, "os candles têm de ser guardados ANTES do "
                              "filtro de lado da agressão")

    def test_o_balde_de_negocios_tem_teto(self):
        """Sem teto, um pregão inteiro de fita líquida vira memória parada."""
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_guardar_negocios_para_candles")
        self.assertIn("maxlen=", corpo)

    def test_o_ruido_do_trailing_NAO_vem_de_um_ATR_global(self):
        """A linha que quase entrou em produção era:

            _atr_ticks = float(self._ultimo_atr) / tick

        Um ATR sem dono dividido pelo tick do ativo DA ORDEM. Se este teste
        um dia falhar porque alguém voltou a essa forma, o defeito não é o
        teste."""
        fonte = fonte_do_arquivo()
        self.assertNotIn('getattr(self, "_ultimo_atr", 0)) / tick', fonte)
        self.assertIn("_ruido_ticks_do_ativo(", fonte)

    def test_sem_o_modulo_de_fluxo_o_app_nao_quebra(self):
        """As três funções vêm de `order_flow.py`, que é opcional na
        instalação. Sem elas o import tem de degradar, não explodir."""
        fonte = fonte_do_arquivo()
        i = fonte.index("from order_flow import (OrderFlowEngine")
        trecho = fonte[i:i + 700]
        self.assertIn("def agregar_candles(*_a, **_k)", trecho)
        self.assertIn("def atr_de_candles(*_a, **_k)", trecho)
        self.assertIn("def faixa_de_stop_por_atr(*_a, **_k)", trecho)


class TestORuidoQuePodeEncostarNoTrailing(unittest.TestCase):
    """`ruido_ticks_do_atr` — a peneira entre uma medição e um stop real.

    O CASO (31/08). A ideia de afastar o trailing do ruído medido é do
    trader e é boa: "tomo muito stop no ruído". O que quase entrou foi um
    ATR global dividido pelo tick do ativo da ordem. Com a fita do MBTU6 no
    balde e uma ordem de MESU6 na mão, a conta dá milhares de ticks — e
    `plano_trailing_inteligente` faz `max(distancia, ruido * 1,5)`. O
    trailing viraria um stop a centenas de pontos: trailing nenhum, calado.

    Cinco perguntas, e uma resposta só quando as cinco passam.
    """

    def _ns(self):
        return carregar(["ruido_ticks_do_atr", "raiz_do_contrato",
                         "faixa_de_stop_do_ativo", "FAIXA_TICKS_STOP",
                         "VALOR_POR_PONTO", "_MESES_FUTUROS",
                         "VALIDADE_DO_ATR_S"])

    def test_o_ATR_do_vizinho_NAO_serve(self):
        ns = self._ns()
        agora = 1_000_000.0
        tabela = {"MBT": {"atr": 300.0, "ts": agora}}
        # Ordem de MESU6, medição só do MBT: sem medição DESTE contrato, é
        # None — e None aqui significa "usa a regra que já existia".
        self.assertIsNone(ns["ruido_ticks_do_atr"](
            tabela, "MESU6", 0.25, agora=agora))

    def test_medicao_velha_NAO_serve(self):
        ns = self._ns()
        agora = 1_000_000.0
        tabela = {"MES": {"atr": 3.0, "ts": agora - 3600}}
        self.assertIsNone(ns["ruido_ticks_do_atr"](
            tabela, "MESU6", 0.25, agora=agora))
        # A mesma medição, feita agora, passa: 3 pts ÷ 0,25 = 12 ticks.
        tabela = {"MES": {"atr": 3.0, "ts": agora}}
        self.assertEqual(ns["ruido_ticks_do_atr"](
            tabela, "MESU6", 0.25, agora=agora), 12.0)

    def test_ruido_maior_que_o_MAIOR_stop_do_contrato_e_recusado(self):
        """Esta é a trava que salva o pregão mesmo se todas as outras
        falharem. A faixa fixa do MES vai até 60 ticks; um "ruído" de 1.200
        ticks não é mercado agitado, é medida errada — e medida errada não
        vira distância de stop."""
        ns = self._ns()
        agora = 1_000_000.0
        # ATR do bitcoin (300 pts) com o tick do MES (0,25) = 1.200 ticks.
        tabela = {"MES": {"atr": 300.0, "ts": agora}}
        avisos = []
        self.assertIsNone(ns["ruido_ticks_do_atr"](
            tabela, "MESU6", 0.25, agora=agora, aviso=avisos.append))
        self.assertTrue(avisos, "recusar em silêncio é a metade errada")
        self.assertIn("1200", avisos[0].replace(".", ""))

    def test_ruido_dentro_da_faixa_passa(self):
        ns = self._ns()
        agora = 1_000_000.0
        # 5 pts no MES = 20 ticks, dentro da faixa 12–60.
        tabela = {"MES": {"atr": 5.0, "ts": agora}}
        self.assertEqual(ns["ruido_ticks_do_atr"](
            tabela, "MESU6", 0.25, agora=agora), 20.0)

    def test_entradas_ausentes_devolvem_None_e_nao_explodem(self):
        ns = self._ns()
        agora = 1_000_000.0
        bom = {"MES": {"atr": 3.0, "ts": agora}}
        for args in ((None, "MESU6", 0.25), ({}, "MESU6", 0.25),
                     (bom, "", 0.25), (bom, "MESU6", 0), (bom, "MESU6", None),
                     ({"MES": {"atr": 0, "ts": agora}}, "MESU6", 0.25),
                     ({"MES": {"atr": 3.0, "ts": 0}}, "MESU6", 0.25),
                     ({"MES": {"atr": "x", "ts": agora}}, "MESU6", 0.25)):
            self.assertIsNone(ns["ruido_ticks_do_atr"](*args, agora=agora))

    def test_contrato_fora_da_tabela_nao_ganha_teto_inventado(self):
        """Sem faixa fixa conhecida não há teto para comparar. O número
        passa — mas só porque as outras quatro perguntas passaram."""
        ns = self._ns()
        agora = 1_000_000.0
        tabela = {"XYZW9": {"atr": 10.0, "ts": agora}}
        self.assertEqual(ns["ruido_ticks_do_atr"](
            tabela, "XYZW9", 1.0, agora=agora), 10.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
