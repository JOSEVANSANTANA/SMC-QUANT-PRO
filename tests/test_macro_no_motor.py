"""O motor analisava o gráfico sem saber o que estava acontecendo no mundo.

19/08, ele: "nao aprende com a web". Fui conferir esperando não achar nada, e
achei o contrário do que imaginava. `bloco_web_para_prompt()` — a função que
traz cotação real e manchetes das casas — era chamada num lugar SÓ do programa
inteiro: o chat (main_app.py:12619).

O MOTOR, que é quem gera a sugestão de entrada, nunca a chamou. Ele lia o
gráfico sem saber que tinha saído CPI naquela manhã, que o payroll acabara de
ser publicado ou que o Powell falava às 15h. A notícia chegava quando ELE
perguntava, e não chegava quando ELA sugeria. No chat, macro é assunto; no
motor, é dinheiro — e era exatamente no motor que faltava.

E há a segunda metade, que é a que vale: colocar a manchete no prompt e torcer
para o modelo levar em conta não é trava, é esperança. Aqui o evento quente
vira NÚMERO — desconto limitado e auditável na probabilidade, do mesmo jeito
que o aprendizado por padrão. Prompt é PEDIDO; código é garantia.
"""

import time
import unittest

from harness import carregar, fonte_do_arquivo


def _noticia(titulo, minutos, fonte="Reuters", resumo=""):
    """Uma manchete publicada há `minutos`."""
    return {"titulo": titulo, "fonte": fonte, "resumo": resumo,
            "quando": time.time() - minutos * 60, "url": ""}


class TestEventoDeAltoImpacto(unittest.TestCase):

    def _ns(self):
        return carregar(["TOPICOS_DE_ALTO_IMPACTO", "MINUTOS_EVENTO_QUENTE",
                         "eventos_de_alto_impacto"])

    def test_cpi_recem_publicado_e_evento(self):
        ns = self._ns()
        achados = ns["eventos_de_alto_impacto"](
            [_noticia("US CPI rises 0.3% in July, above forecasts", 12)])
        self.assertEqual(len(achados), 1)
        self.assertIn("inflação", achados[0]["rotulo"])
        self.assertEqual(achados[0]["minutos"], 12)

    def test_fed_payroll_e_copom_tambem(self):
        ns = self._ns()
        for titulo in ("FOMC holds rates steady, Powell signals patience",
                       "Nonfarm payrolls surge in August",
                       "Copom eleva a Selic para 15%",
                       "ISM manufacturing PMI comes in weak"):
            achados = ns["eventos_de_alto_impacto"]([_noticia(titulo, 5)])
            self.assertTrue(achados, titulo)

    def test_manchete_velha_NAO_e_evento_quente(self):
        """Passada a janela, o número já foi digerido — e penalizar cenário
        por causa de uma manchete de ontem seria penalizar todo dia, o que é o
        mesmo que não penalizar nada."""
        ns = self._ns()
        velha = ns["MINUTOS_EVENTO_QUENTE"] + 30
        self.assertEqual(
            ns["eventos_de_alto_impacto"]([_noticia("US CPI rises 0.3%", velha)]),
            [])

    def test_manchete_sem_data_e_ignorada(self):
        """Sem data não dá para dizer 'acabou de sair'. Chutar que é recente
        derrubaria a probabilidade de todo cenário por causa de um feed que
        publica sem timestamp."""
        ns = self._ns()
        sem_data = {"titulo": "US CPI rises 0.3%", "fonte": "X",
                    "resumo": "", "quando": None}
        self.assertEqual(ns["eventos_de_alto_impacto"]([sem_data]), [])

    def test_noticia_comum_de_mercado_nao_vira_evento(self):
        """Falso positivo aqui custa dinheiro: cada evento inventado tira
        pontos de probabilidade de um cenário que estava bom."""
        ns = self._ns()
        for titulo in ("Apple shares rise after product launch",
                       "Bitcoin holds above 100k",
                       "Petrobras anuncia dividendos",
                       "Wall Street fecha em alta com tecnologia"):
            self.assertEqual(ns["eventos_de_alto_impacto"]([_noticia(titulo, 5)]),
                             [], titulo)

    def test_um_topico_aparece_UMA_vez_e_com_a_manchete_mais_nova(self):
        ns = self._ns()
        achados = ns["eventos_de_alto_impacto"]([
            _noticia("CPI report due later", 80, fonte="Velha"),
            _noticia("US CPI comes in hot", 6, fonte="Nova"),
        ])
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0]["fonte"], "Nova")

    def test_lista_vazia_ou_None_nao_quebra(self):
        ns = self._ns()
        self.assertEqual(ns["eventos_de_alto_impacto"]([]), [])
        self.assertEqual(ns["eventos_de_alto_impacto"](None), [])


class TestOEventoViraNUMERO(unittest.TestCase):
    """Prompt é PEDIDO, não garantia. Escrever 'cuidado, saiu CPI' no prompt e
    torcer para o modelo obedecer não é trava."""

    def _ns(self):
        return carregar(["PENALIDADE_EVENTO_MACRO", "ajuste_por_evento_macro"])

    def test_evento_quente_DESCONTA_probabilidade(self):
        ns = self._ns()
        delta, porques = ns["ajuste_por_evento_macro"](
            [{"rotulo": "inflação (CPI/PCE/IPCA)", "minutos": 10,
              "fonte": "Reuters", "titulo": "CPI", "penaliza": True}])
        self.assertEqual(delta, -ns["PENALIDADE_EVENTO_MACRO"])
        self.assertTrue(porques)

    def test_o_desconto_e_LIMITADO(self):
        """Macro CORRIGE a leitura, não a substitui. Três manchetes não podem
        zerar sozinhas um cenário que a estrutura sustenta."""
        ns = self._ns()
        muitos = [{"rotulo": f"t{i}", "minutos": i, "fonte": "X",
                   "titulo": "x", "penaliza": True} for i in range(6)]
        delta, _ = ns["ajuste_por_evento_macro"](muitos)
        self.assertEqual(delta, -ns["PENALIDADE_EVENTO_MACRO"])
        self.assertLessEqual(ns["PENALIDADE_EVENTO_MACRO"], 15.0)

    def test_o_desconto_nunca_e_BONUS(self):
        """Dado macro recém-publicado não melhora a confiabilidade de uma
        leitura de estrutura. Se um dia isso virar positivo, é defeito."""
        ns = self._ns()
        delta, _ = ns["ajuste_por_evento_macro"](
            [{"rotulo": "a", "minutos": 1, "fonte": "X", "titulo": "x",
              "penaliza": True}])
        self.assertLess(delta, 0)

    def test_geopolitica_entra_no_prompt_mas_NAO_desconta(self):
        """Guerra e tarifa saem o dia inteiro; descontar por isso seria
        descontar sempre — e desconto que vale sempre não informa nada."""
        ns = self._ns()
        delta, porques = ns["ajuste_por_evento_macro"](
            [{"rotulo": "choque geopolítico / tarifas", "minutos": 5,
              "fonte": "X", "titulo": "x", "penaliza": False}])
        self.assertEqual(delta, 0.0)
        self.assertEqual(porques, [])

    def test_sem_evento_nao_mexe_em_nada(self):
        ns = self._ns()
        self.assertEqual(ns["ajuste_por_evento_macro"]([]), (0.0, []))
        self.assertEqual(ns["ajuste_por_evento_macro"](None), (0.0, []))


class TestDoTickerParaACotacao(unittest.TestCase):
    """A tabela de apelidos conhece 'mes', mas nunca vai conhecer 'MESU2026' —
    e é isso que está escrito no gráfico dele."""

    def _ns(self):
        return carregar(["raiz_do_contrato", "simbolo_de_cotacao_do_ativo",
                         "VALOR_POR_PONTO", "SIMBOLOS_MERCADO",
                         "_MESES_FUTUROS", "simbolo_do_texto", "_sem_acento",
                         "_norm_busca", "_compacto", "_e_contrato_conhecido"])

    def test_a_raiz_sai_do_contrato_com_vencimento(self):
        ns = self._ns()
        for ticker, raiz in (("MESU6", "MES"), ("MESU2026", "MES"),
                             ("ES", "ES"), ("MNQZ5", "MNQ"), ("MES1!", "MES")):
            self.assertEqual(ns["raiz_do_contrato"](ticker), raiz, ticker)

    def test_palavra_qualquer_nao_vira_contrato(self):
        """'CLAUDE' começa com 'CL', que é petróleo. Já passou por aqui."""
        ns = self._ns()
        for texto in ("CLAUDE", "CHAT", "", None, "DESCONHECIDO"):
            self.assertIsNone(ns["raiz_do_contrato"](texto), repr(texto))

    def test_o_contrato_do_grafico_acha_o_simbolo_da_cotacao(self):
        ns = self._ns()
        achado = ns["simbolo_de_cotacao_do_ativo"]("MESU6")
        self.assertIsNotNone(achado, "sem símbolo não há cotação de referência")
        self.assertEqual(achado[0], ns["SIMBOLOS_MERCADO"]["mes"])

    def test_ticker_desconhecido_devolve_None_em_vez_de_chutar(self):
        ns = self._ns()
        self.assertIsNone(ns["simbolo_de_cotacao_do_ativo"]("DESCONHECIDO"))


class TestOMotorRECEBEIssoDeVerdade(unittest.TestCase):
    """Função escrita e nunca chamada é o defeito que eu vim consertar. Não
    adianta trocá-lo por outro do mesmo formato."""

    def _fonte(self):
        return fonte_do_arquivo()

    def test_o_prompt_do_motor_carrega_o_bloco_do_mundo(self):
        fonte = self._fonte()
        self.assertIn("contexto_de_mercado_do_motor(", fonte)
        i = fonte.index("PROMPT_FINAL = (")
        # a chamada tem de estar ANTES da montagem do prompt, e o resultado
        # dentro dele
        self.assertIn("contexto_de_mercado_do_motor(", fonte[i - 1200:i])
        self.assertIn("O QUE ESTÁ ACONTECENDO NO MUNDO AGORA",
                      fonte[i:i + 900])

    def test_a_probabilidade_do_motor_passa_pelo_ajuste_macro(self):
        fonte = self._fonte()
        self.assertIn("ajuste_por_evento_macro(eventos_macro)", fonte)
        i = fonte.index("ajuste_por_evento_macro(eventos_macro)")
        # e o ajuste tem de vir ANTES do piso de qualidade decidir
        depois = fonte[i:i + 2500]
        self.assertIn("avaliar_piso_de_qualidade(", depois,
                      "o desconto macro precisa acontecer antes de o piso "
                      "decidir, senão ele não barra nada")

    def test_o_registro_DIZ_de_onde_veio_o_desconto(self):
        fonte = self._fonte()
        self.assertIn("📰 MACRO: probabilidade", fonte)

    def test_o_aviso_vai_junto_no_WHATSAPP(self):
        """Ele lê a sugestão no celular, longe da tela do programa."""
        fonte = self._fonte()
        self.assertIn("Atenção — evento macro agora", fonte)
        self.assertIn("bloco_macro_wpp", fonte)

    def test_falha_de_rede_nao_derruba_o_ciclo(self):
        """Feed fora do ar não pode impedir a leitura do gráfico — o macro é
        um extra, e extra que derruba o principal é defeito."""
        fonte = self._fonte()
        i = fonte.index("def contexto_de_mercado_do_motor(")
        bloco = fonte[i:i + 3000]
        self.assertGreaterEqual(bloco.count("except Exception"), 4)
        self.assertIn('return ("", [])', bloco)


if __name__ == "__main__":
    unittest.main()


class TestOMacroNUNCAAtrasaOCiclo(unittest.TestCase):
    """A queixa que abriu esta versão foi "esta muito lento para pensar".
    Seria piada de mau gosto consertar a lentidão e, na mesma entrega,
    pendurar quinze segundos de feed RSS na frente de cada análise."""

    def test_tem_teto_de_espera_e_ele_e_curto(self):
        ns = carregar(["ORCAMENTO_MACRO_SEG"])
        self.assertLessEqual(ns["ORCAMENTO_MACRO_SEG"], 20)
        self.assertGreaterEqual(ns["ORCAMENTO_MACRO_SEG"], 5)

    def test_estourou_o_teto_o_ciclo_SEGUE_sem_o_macro(self):
        """Ler o gráfico é o principal, e o principal nunca espera pelo
        acessório."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def contexto_de_mercado_do_motor(")
        bloco = fonte[i:i + 3600]
        self.assertIn("concurrent.futures.TimeoutError", bloco)
        self.assertIn("result(timeout=orcamento)", bloco)

    def test_o_download_lento_nao_e_jogado_fora(self):
        """Quem chegou tarde para este ciclo serve para o próximo: a thread
        segue e o resultado entra no cache."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def contexto_de_mercado_do_motor(")
        bloco = fonte[i:i + 3600]
        self.assertIn("_web_cacheado(", bloco)
