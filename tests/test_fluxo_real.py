"""O CVD DE VERDADE — lido da fita, e nunca inventado quando ela não está lá.

O delta que existia antes era um contador com semente fixa que trocava de
sinal para concordar com a IA (ver `test_telemetria_honesta`). Ele saiu. Este
arquivo guarda o que entrou no lugar, e a régua é a mesma dos dois lados:

    só sai número quando vem de negócio observado, com tamanho e com lado.

DE ONDE VEM O DADO
------------------
Da fita (Time & Sales) da própria Tradovate, lida por CDP —
`Runtime.evaluate` roda JS DENTRO da página, ou seja, é DOM e não pixel. A
janela pode estar atrás de outras, em outra aba ou fora da tela: a leitura é
igual. O que o CDP não consegue é ler o que não existe — a Tradovate é React,
e painel fechado não tem nó no DOM. Por isso a fita precisa estar ABERTA no
layout; não precisa estar à vista.

O QUE ESTES TESTES PROTEGEM
---------------------------
1. A PRIMEIRA leitura não conta o passado. A fita é uma janela rolante com
   negócios que já aconteceram; somá-la inteira faria o CVD nascer com um
   valor herdado e sem significado — parecido demais com a semente de 1.420
   que acabou de sair daqui.
2. Cada negócio entra UMA vez. Sem a marca do topo, todo ciclo recontaria a
   janela e o CVD viraria um número que só cresce.
3. Negócio sem lado determinável NÃO entra. É a regra que impede o defeito
   antigo de voltar com outro nome: preferir um chute a um espaço vazio.
4. Sem fita, o prompt da análise não recebe fluxo nenhum — a IA decide sem
   ele, que é honesto. O que não pode é ela receber um delta inventado e
   tratá-lo como confirmação.
"""

import os
import sys
import unittest

from harness import RAIZ, fonte_do_arquivo

sys.path.insert(0, RAIZ)
from order_flow import OrderFlowEngine          # noqa: E402
from tradovate_stream import TradovateStream    # noqa: E402


def _leitura(linhas, bid=7547.75, ask=7548.00, metodo="bid_ask"):
    return {"ok": True, "bid": bid, "ask": ask, "linhas": linhas,
            "diag": {"painel": True, "linhas_vistas": len(linhas),
                     "metodo": metodo}}


class TestAClassificacaoDaAgressao(unittest.TestCase):
    """Quem cruzou o spread — e a coragem de responder 'não sei'."""

    def setUp(self):
        self.f = TradovateStream()

    def test_o_lado_marcado_na_linha_manda(self):
        self.assertIs(self.f.classificar_agressao({"lado": "compra"}, None, None), True)
        self.assertIs(self.f.classificar_agressao({"lado": "venda"}, None, None), False)

    def test_sem_lado_usa_preco_contra_bid_ask(self):
        """Lee-Ready: no ask foi o comprador que cruzou; no bid, o vendedor."""
        self.assertIs(self.f.classificar_agressao(
            {"preco": 7548.00, "lado": None}, 7547.75, 7548.00), True)
        self.assertIs(self.f.classificar_agressao(
            {"preco": 7547.75, "lado": None}, 7547.75, 7548.00), False)

    def test_negocio_no_meio_do_spread_e_NAO_SEI(self):
        """E `None` aqui não é falha: é a resposta certa.

        Um negócio entre bid e ask não diz quem foi o agressor. Chutar um
        lado para não deixar o campo vazio é exatamente o defeito que este
        módulo substituiu."""
        self.assertIsNone(self.f.classificar_agressao(
            {"preco": 7547.90, "lado": None}, 7547.75, 7548.00))

    def test_sem_bid_ask_e_sem_rotulo_tambem_e_NAO_SEI(self):
        self.assertIsNone(self.f.classificar_agressao(
            {"preco": 7548.0, "lado": None}, None, None))


class TestAFitaNaoRecontaNemHerdaOPassado(unittest.TestCase):

    def setUp(self):
        self.f = TradovateStream()

    def test_a_primeira_leitura_nao_conta_nada(self):
        """O CVD começa do zero AGORA, não com o que já tinha rolado."""
        novos, _ = self.f.negocios_novos(_leitura([
            {"preco": 7548.0, "tamanho": 5, "lado": None},
            {"preco": 7547.75, "tamanho": 2, "lado": None}]))
        self.assertEqual(novos, [])

    def test_so_o_que_e_novo_entra_na_segunda_leitura(self):
        self.f.negocios_novos(_leitura([
            {"preco": 7548.0, "tamanho": 5, "lado": None},
            {"preco": 7547.75, "tamanho": 2, "lado": None}]))
        novos, _ = self.f.negocios_novos(_leitura([
            {"preco": 7548.0, "tamanho": 12, "lado": None},   # novo
            {"preco": 7547.75, "tamanho": 4, "lado": None},   # novo
            {"preco": 7548.0, "tamanho": 5, "lado": None},    # já contado
            {"preco": 7547.75, "tamanho": 2, "lado": None}]))
        self.assertEqual(len(novos), 2)

    def test_os_novos_vem_do_mais_antigo_para_o_mais_novo(self):
        """A fita chega invertida (topo = mais recente) e o CVD é acumulado:
        registrar fora de ordem embaralha a sequência de `ticks`, que é o que
        a absorção e o sweep leem depois."""
        self.f.negocios_novos(_leitura([{"preco": 7548.0, "tamanho": 5, "lado": None}]))
        novos, _ = self.f.negocios_novos(_leitura([
            {"preco": 7549.0, "tamanho": 3, "lado": None},    # mais recente
            {"preco": 7548.5, "tamanho": 7, "lado": None},
            {"preco": 7548.0, "tamanho": 5, "lado": None}]))
        self.assertEqual([n["tamanho"] for n in novos], [7, 3])

    def test_fita_parada_nao_gera_negocio_novo(self):
        self.f.negocios_novos(_leitura([{"preco": 7548.0, "tamanho": 5, "lado": None}]))
        novos, _ = self.f.negocios_novos(_leitura([{"preco": 7548.0, "tamanho": 5, "lado": None}]))
        self.assertEqual(novos, [])

    def test_fita_fechada_nao_inventa_leitura(self):
        novos, diag = self.f.negocios_novos(
            {"ok": False, "motivo": "fita_nao_encontrada",
             "diag": {"painel": False, "linhas_vistas": 0, "metodo": None}})
        self.assertEqual(novos, [])
        self.assertFalse(diag.get("painel"))


class TestOCVDBateAConta(unittest.TestCase):

    def test_doze_no_ask_menos_quatro_no_bid_da_mais_oito(self):
        f, motor = TradovateStream(), OrderFlowEngine()
        f.negocios_novos(_leitura([{"preco": 7548.0, "tamanho": 5, "lado": None}]))
        novos, _ = f.negocios_novos(_leitura([
            {"preco": 7548.0, "tamanho": 12, "lado": None},
            {"preco": 7547.75, "tamanho": 4, "lado": None},
            {"preco": 7548.0, "tamanho": 5, "lado": None}]))
        for ln in novos:
            lado = f.classificar_agressao(ln, 7547.75, 7548.00)
            motor.registrar_tick(ln["preco"], ln["tamanho"], lado)
        self.assertEqual(motor.obter_cvd(), 8.0)
        self.assertEqual(motor.volume_total, 16.0)

    def test_negocio_sem_lado_fica_de_fora_do_delta(self):
        """A regra central. 10 no meio do spread não viram +10 nem -10."""
        f, motor = TradovateStream(), OrderFlowEngine()
        f.negocios_novos(_leitura([{"preco": 7548.0, "tamanho": 1, "lado": None}]))
        novos, _ = f.negocios_novos(_leitura([
            {"preco": 7547.90, "tamanho": 10, "lado": None},   # meio do spread
            {"preco": 7548.0, "tamanho": 3, "lado": None},     # no ask
            {"preco": 7548.0, "tamanho": 1, "lado": None}]))
        entraram = 0
        for ln in novos:
            lado = f.classificar_agressao(ln, 7547.75, 7548.00)
            if lado is None:
                continue
            motor.registrar_tick(ln["preco"], ln["tamanho"], lado)
            entraram += 1
        self.assertEqual(entraram, 1)
        self.assertEqual(motor.obter_cvd(), 3.0)


class TestOFluxoSoEntraNoPromptQuandoEMedido(unittest.TestCase):
    """A porta que impede o defeito antigo de voltar pela análise."""

    def test_a_porta_existe_e_e_o_motor_que_a_abre(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tem_fluxo_medido")
        corpo = fonte[i:i + 700]
        self.assertIn('getattr(motor, "ticks", [])', corpo,
                      "a porta tem de olhar os negócios REGISTRADOS, não uma "
                      "variável de estado que alguém pode ligar por engano")

    def test_o_prompt_da_analise_so_recebe_fluxo_por_essa_porta(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("FLUXO DE ORDENS MEDIDO NA FITA")
        trecho = fonte[i:i + 1200]
        self.assertIn("_tem_fluxo_medido()", trecho)

    def test_o_prompt_manda_usar_fluxo_como_CONFIRMACAO_e_nao_como_motivo(self):
        """Foi o pedido dele desde o começo: SMC é a metodologia principal,
        order flow confirma dentro do viés. Delta contra a estrutura vira
        HOLD — nunca inversão de mão."""
        fonte = fonte_do_arquivo()
        i = fonte.index("FLUXO DE ORDENS MEDIDO NA FITA")
        trecho = fonte[i:i + 1200]
        self.assertIn("CONFIRMAÇÃO", trecho)
        self.assertIn("HOLD", trecho)


class TestODiagnosticoDizOQueFazer(unittest.TestCase):
    """'Sem fluxo' tem de ser distinguível de 'está quebrado'."""

    def test_a_fita_fechada_explica_que_basta_abrir_no_layout(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def diagnostico_da_fita")
        corpo = fonte[i:i + 2600]
        self.assertIn("ABERTO no layout", corpo)
        self.assertIn("não precisa estar à sua frente", corpo)

    def test_o_diagnostico_cobre_os_quatro_estados(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def diagnostico_da_fita")
        corpo = fonte[i:i + 2600]
        for estado in ("sem_conexao_cdp", "painel", "linhas_vistas", "metodo"):
            self.assertIn(estado, corpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOSeletorCasaComATelaREAL(unittest.TestCase):
    """23/08: ele mandou o print da fita aberta, e ela desmentiu meu seletor.

    O cabeçalho da fita dele é:

        SELO DE DATA E HORA | PREÇO | TAMA | CONT.

    A expressão "Time & Sales" NÃO APARECE em lugar nenhum do painel — o
    seletor procurava pelo NOME da janela e não acharia nada, com a fita
    aberta bem na frente dele.

    E havia coisa pior. A primeira coluna traz "10:42:56.611"; sem os
    separadores isso vira 104256.611, MAIOR que o preço 7557.25. A regra de
    "o maior número da linha é o preço" leria a HORA como preço, e o CVD
    sairia calculado sobre um número que não é preço de nada.

    Os dois defeitos eram meus, e nenhum apareceria em teste sintético: só o
    print da tela real os revelou.
    """

    def _js(self):
        import os
        return fonte_do_arquivo(os.path.join(RAIZ, "tradovate_stream.py"))

    def test_a_fita_e_achada_pelos_TITULOS_das_colunas(self):
        js = self._js()
        self.assertIn("selo de data", js,
                      "a âncora tem de ser o que as colunas dizem, não o nome "
                      "da janela — 'Time & Sales' não existe na tela dele")
        for coluna in ("preco|price", "tama|size"):
            self.assertIn(coluna, js)

    def test_carimbo_de_hora_e_de_data_nao_viram_numero(self):
        """A regra que impede a hora de ser lida como preço."""
        js = self._js()
        self.assertIn("ehCarimbo", js)
        i = js.index("function ehCarimbo")
        corpo = js[i:i + 260]
        self.assertIn(r"\d{1,2}:\d{2}", corpo)        # 10:42:56
        self.assertIn(r"\d{1,2}\/\d{1,2}\/\d{2,4}", corpo)   # 7/9/26

    def test_o_preco_vem_da_ORDEM_das_colunas_e_nao_do_maior_numero(self):
        js = self._js()
        i = js.index("ORDEM DAS COLUNAS")
        self.assertIn("nums[0]", js[i:i + 400])
        self.assertNotIn("Math.max.apply(null,nums)", js,
                         "o 'maior número da linha' é exatamente o que fazia a "
                         "hora virar preço")

    def test_a_linha_sem_carimbo_de_hora_e_descartada(self):
        """É assim que o cabeçalho fica de fora sozinho: ele tem as palavras
        das colunas, mas não tem hora."""
        js = self._js()
        self.assertIn("if(!temHora) continue;", js)

    def test_a_cor_da_linha_e_lida_como_lado_da_agressao(self):
        """Na fita da Tradovate a linha inteira é vermelha ou verde, e é a
        marca mais confiável de quem agrediu — mais que classe de CSS, que
        muda a cada release.

        A LEITURA MUDOU DE ENDEREÇO EM 23/08. Estava em linha no `_lerLinha`
        e passou para `_JS_LADO_PELA_COR`, porque `getComputedStyle` não herda
        fundo: quando a Tradovate pinta a CÉLULA, a linha volta transparente e
        o lado saía nulo em silêncio. A regra que este teste protege é a
        mesma; só o lugar dela é outro."""
        import tradovate_stream
        js = tradovate_stream.TradovateStream._JS_LADO_PELA_COR
        self.assertIn("getComputedStyle", js)
        i = js.index("getComputedStyle")
        corpo = js[i:i + 800]
        self.assertIn("'venda'", corpo)
        self.assertIn("'compra'", corpo)

    def test_a_cor_e_lida_pelos_dois_leitores_da_fita(self):
        """O observador contínuo e a leitura pontual têm de classificar
        igual: dois critérios de agressão dariam dois CVDs diferentes."""
        import tradovate_stream
        T = tradovate_stream.TradovateStream
        s = T.__new__(T)
        observador = T._js_com_achador(s, T._JS_INSTALAR_OBSERVADOR)
        pontual = T._JS_TIME_AND_SALES.replace(
            "PLACEHOLDER_LADO_PELA_COR", T._JS_LADO_PELA_COR)
        for nome, js in (("observador", observador), ("pontual", pontual)):
            self.assertIn("_ladoPelaCor(", js, nome)
            self.assertIn("function _ladoPelaCor", js, nome)


class TestOParserSobreAsLinhasREAIS(unittest.TestCase):
    """A mesma lógica do JS, medida em Python sobre as linhas do print."""

    @staticmethod
    def _eh_carimbo(s):
        import re
        return bool(re.search(r"\d{1,2}:\d{2}", s)
                    or re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", s))

    @classmethod
    def _num(cls, s):
        import re
        if not s or cls._eh_carimbo(s):
            return None
        t = re.sub(r"[^0-9.,-]", "", s)
        try:
            return float(t)
        except ValueError:
            return None

    def _ler(self, textos):
        if not any(self._eh_carimbo(t) for t in textos):
            return None
        nums = [v for v in (self._num(t) for t in textos) if v is not None]
        if len(nums) < 2:
            return None
        preco = nums[0]
        tam = next((n for n in nums[1:] if n > 0 and n == int(n)), None)
        return (preco, tam) if tam else None

    def test_as_quatro_linhas_do_print_sao_lidas_certo(self):
        casos = [
            (["10:42:56.611", "7/9/26", "7557.25", "1", "10"], (7557.25, 1)),
            (["10:42:56.545", "7/9/26", "7557.50", "2", "3"], (7557.50, 2)),
            (["10:42:55.519", "7/9/26", "7557.00", "18", "24"], (7557.00, 18)),
            (["10:42:55.394", "7/9/26", "7556.75", "9", "9"], (7556.75, 9)),
        ]
        for textos, esperado in casos:
            self.assertEqual(self._ler(textos), esperado, f"linha {textos}")

    def test_o_cabecalho_da_fita_dele_nao_vira_negocio(self):
        self.assertIsNone(
            self._ler(["SELO DE DATA E HORA", "PREÇO", "TAMA", "CONT."]))

    def test_a_hora_nunca_e_o_preco(self):
        """104256.611 é maior que 7557.25 — e é o defeito inteiro num número."""
        preco, _ = self._ler(["10:42:56.611", "7/9/26", "7557.25", "1", "10"])
        self.assertEqual(preco, 7557.25)
        self.assertLess(preco, 100000)
