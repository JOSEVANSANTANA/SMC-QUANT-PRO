"""O dia do pregão não é o dia do calendário — e "BOA TARDE" não precisa de API.

Log de 12/08, 19:59. Ele configurou, com estas palavras:

    "o dia ja virou, deixa registrado, o inicio do dia para essa conta é
     as 19hs até as 17:59"

A ferramenta gravou certo e confirmou. E às 20:01, com o pregão NOVO rodando
havia uma hora, o freio respondeu:

    "🛑 você já fechou 6 operações hoje, que é o teto do seu plano (6)"

Aquelas seis eram do pregão ANTERIOR. Ele reclamou três vezes — "mas o dia já
virou", "era para contabilizar no plano de trading", "vire o ciclo do dia no
painel de trading" — e chegou a gravar como lição:

    "o claude precisa incluir opcao de virar o dia... deveria ter uma opcao
     de virar o ciclo. Vire o ciclo do dia no painel de trading quando eu
     pedi, aprenda isso!"

Não era um botão que faltava: era `hoje = time.strftime('%d/%m/%Y')`. Para quem
opera índice americano de madrugada, meia-noite não é a virada de nada.

E no mesmo dia, 15:41:

    ❯ BOA TARDE
    ✳ "Não tenho como responder isso com segurança agora: não está na minha
       base, não consegui confirmar na internet, e a API está fora..."

Dizer boa tarde nunca precisou de API. Uma ferramenta que não sabe cumprimentar
não parece cuidadosa — parece quebrada, e isso contamina a confiança em tudo.
"""

import datetime
import unittest

from harness import carregar, fonte_do_arquivo

D = datetime.datetime
VIRA = {"hora_inicio": "19:00", "hora_fim": "17:59"}      # o pregão dele
NORMAL = {"hora_inicio": "09:00", "hora_fim": "17:00"}


def _ns(cfg):
    return carregar(
        ["_sem_acento", "PADRAO_CONFIG_APP", "_hora_do_registro",
         "data_do_pregao", "pregao_vira_o_dia", "_RE_SAUDACAO",
         "responder_saudacao", "_RE_VIRAR_DIA", "_RE_QUAL_PREGAO"],
        stubs={"unicodedata": __import__("unicodedata"),
               "carregar_config": lambda: dict(cfg)})


class TestDiaDoPregao(unittest.TestCase):

    def test_o_caso_real_das_2001(self):
        """Às 20:01 de 12/08, com o pregão começando às 19:00, o dia de
        operação é 12/08 — e as operações fechadas ANTES das 19:00 daquele
        mesmo 12/08 pertencem ao pregão de 11/08. É isso que solta o freio."""
        ns = _ns(VIRA)
        self.assertEqual(ns["data_do_pregao"](D(2026, 8, 12, 20, 1)), "12/08/2026")
        self.assertEqual(ns["data_do_pregao"](D(2026, 8, 12, 15, 55)), "11/08/2026")

    def test_a_madrugada_pertence_ao_pregao_que_comecou_ontem(self):
        """Operar às 03:00 de 13/08 é continuar o pregão que abriu às 19:00 de
        12/08. Sem isto, um pregão só virava dois no relatório."""
        ns = _ns(VIRA)
        for hora in (D(2026, 8, 13, 3, 0), D(2026, 8, 13, 10, 0),
                     D(2026, 8, 13, 17, 58)):
            self.assertEqual(ns["data_do_pregao"](hora), "12/08/2026",
                             hora.strftime("%d/%m %H:%M"))

    def test_a_virada_acontece_exatamente_na_hora_configurada(self):
        ns = _ns(VIRA)
        self.assertEqual(ns["data_do_pregao"](D(2026, 8, 13, 18, 59)), "12/08/2026")
        self.assertEqual(ns["data_do_pregao"](D(2026, 8, 13, 19, 0)), "13/08/2026")

    def test_pregao_normal_continua_sendo_o_dia_do_calendario(self):
        """Quem opera 09:00-17:00 não pode ver o comportamento mudar. Uma
        correção que conserta o caso dele e quebra o de todo mundo não é
        correção."""
        ns = _ns(NORMAL)
        for hora in (D(2026, 8, 12, 20, 1), D(2026, 8, 13, 3, 0),
                     D(2026, 8, 12, 10, 0)):
            self.assertEqual(ns["data_do_pregao"](hora),
                             hora.strftime('%d/%m/%Y'), str(hora))

    def test_sabe_dizer_se_o_pregao_vira_o_dia(self):
        self.assertTrue(_ns(VIRA)["pregao_vira_o_dia"]())
        self.assertFalse(_ns(NORMAL)["pregao_vira_o_dia"]())

    def test_configuracao_quebrada_nao_derruba_nada(self):
        """Hora inválida no arquivo não pode impedir o app de saber que dia é.
        Cai no calendário, que é o comportamento antigo e seguro."""
        ns = _ns({"hora_inicio": "banana", "hora_fim": ""})
        self.assertEqual(ns["data_do_pregao"](D(2026, 8, 12, 20, 1)), "12/08/2026")

    def test_o_calculo_de_hoje_usa_o_pregao_e_nao_o_calendario(self):
        """A função pode existir e o resto do app continuar no calendário —
        que era exatamente o defeito."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def operacoes_fechadas_hoje")
        bloco = fonte[i:i + 1500]
        self.assertIn("data_do_pregao", bloco)
        self.assertNotIn("time.strftime('%d/%m/%Y')", bloco)
        # E o resultado do dia no dashboard também.
        j = fonte.index("resultado_hoje = dict(resultados_por_dia())")
        self.assertIn("data_do_pregao()", fonte[j - 200:j])


class TestVirarODiaNaMao(unittest.TestCase):
    """'vire o ciclo do dia no painel de trading' — pedido duas vezes, e as
    duas caiu no despejo genérico."""

    def test_reconhece_o_pedido_como_ele_escreveu(self):
        ns = _ns(VIRA)
        for t in ("vire o ciclo do dia no painel de trading",
                  "vira o dia", "virar o dia",
                  "altere o plano de trading para novo dia",
                  "o dia já virou",
                  "reinicia o dia de operação"):
            self.assertTrue(ns["_RE_VIRAR_DIA"].search(t), t)

    def test_nao_confunde_com_zerar_o_ciclo(self):
        """ZERAR o ciclo apaga o ciclo inteiro do plano. VIRAR o dia só move a
        marca de onde este dia começou. Trocar um pelo outro seria destruir o
        histórico dele por causa de um freio."""
        ns = _ns(VIRA)
        for t in ("status", "liga o motor", "compro ou vendo?", "bom dia"):
            self.assertFalse(ns["_RE_VIRAR_DIA"].search(t), t)

    def test_pergunta_sobre_o_pregao_e_respondida_localmente(self):
        ns = _ns(VIRA)
        for t in ("em que pregão estamos?", "qual o dia de operação?"):
            self.assertTrue(ns["_RE_QUAL_PREGAO"].search(t), t)

    def test_virar_o_dia_nao_apaga_historico(self):
        """Apagar operações para destravar um freio seria trocar uma trava de
        gestão por uma amnésia — e sumir com o resultado do dia dele."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _chat_virar_dia")
        bloco = fonte[i:i + 2200]
        self.assertIn("NÃO foi apagado", bloco)
        self.assertNotIn("salvar_posicoes([])", bloco)
        # E confirma relendo do disco, como toda ação que grava nesta casa.
        self.assertIn("carregar_config().get(\"virada_manual\")", bloco)

    def test_a_virada_manual_expira(self):
        """Uma virada de ontem não pode continuar mandando hoje — senão o
        freio ficaria desligado para sempre depois de um único comando."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def operacoes_fechadas_hoje")
        bloco = fonte[i:i + 1500]
        self.assertIn("timedelta(hours=24)", bloco)


class TestSaudacao(unittest.TestCase):

    def test_boa_tarde_e_respondido(self):
        """A frase exata de 15:41, que virou um parágrafo de desculpa."""
        ns = _ns(VIRA)
        r = ns["responder_saudacao"]("BOA TARDE", D(2026, 8, 12, 15, 41))
        self.assertIsNotNone(r)
        self.assertIn("Boa tarde", r)
        self.assertNotIn("não tenho como responder", r.lower())
        self.assertNotIn("API", r)

    def test_o_cumprimento_segue_o_relogio_e_nao_o_que_ele_digitou(self):
        """Se ele escreve 'bom dia' às 21h, responder 'bom dia' seria repetir
        sem ler. O relógio é a fonte."""
        ns = _ns(VIRA)
        self.assertIn("Boa noite",
                      ns["responder_saudacao"]("bom dia", D(2026, 8, 12, 21, 0)))
        self.assertIn("Bom dia",
                      ns["responder_saudacao"]("boa noite", D(2026, 8, 12, 8, 0)))

    def test_varias_formas_de_cumprimentar(self):
        ns = _ns(VIRA)
        for t in ("oi", "olá", "opa", "e aí", "tudo bem?", "bom dia!",
                  "boa noite", "cheguei"):
            self.assertIsNotNone(ns["responder_saudacao"](t), t)

    def test_cumprimento_COM_pergunta_junto_nao_e_cumprimento(self):
        """'bom dia, o que deu errado no stop?' é uma PERGUNTA. Responder só
        'bom dia' e parar seria ignorar o que ele quer."""
        ns = _ns(VIRA)
        for t in ("bom dia, o que deu errado no stop?",
                  "oi, compro ou vendo?",
                  "boa tarde, qual o status?"):
            self.assertIsNone(ns["responder_saudacao"](t), t)

    def test_comando_nao_vira_cumprimento(self):
        ns = _ns(VIRA)
        for t in ("status", "liga o motor", "acatar", "tira um print"):
            self.assertIsNone(ns["responder_saudacao"](t), t)

    def test_a_saudacao_vem_antes_de_tudo_no_caminho_offline(self):
        """Se viesse depois da base, 'boa tarde' cairia na busca por tópico e
        de lá no despejo — que é exatamente o que acontecia."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def responder_offline")
        bloco = fonte[i:i + 3000]
        self.assertLess(bloco.index("responder_saudacao"),
                        bloco.index("buscar_base_smc"))


class TestBaseDeConhecimento(unittest.TestCase):
    """A base local é o que faz a ferramenta responder sem API nenhuma."""

    def _ns(self):
        return carregar(
            ["_sem_acento", "_norm_busca", "_parecido", "BASE_SMC", "BASE_MACRO",
             "_todos_os_topicos", "_nota_base_smc", "buscar_base_smc"],
            stubs={"unicodedata": __import__("unicodedata")})

    def test_os_assuntos_que_ele_opera_todo_dia_tem_verbete(self):
        ns = self._ns()
        for pergunta in ("o que é vwap?", "o que significa poc?",
                         "o que é atr?", "o que é rsi?",
                         "como usar média móvel de 200?",
                         "o que é order flow?", "o que é slippage?",
                         "o que é open interest?",
                         "como fazer trailing stop?",
                         "o que é drawdown trailing?",
                         "o que é tilt?"):
            self.assertIsNotNone(ns["buscar_base_smc"](pergunta), pergunta)

    def test_o_smc_de_sempre_continua_respondendo(self):
        """A base cresceu; nada do que já funcionava pode ter sido empurrado
        para fora por uma colisão de palavra-chave."""
        ns = self._ns()
        for pergunta in ("o que é choch?", "o que é bos?",
                         "o que é order block?", "o que é fvg?",
                         "o que é premium e discount?",
                         "o que é inducement?", "onde colocar o stop?"):
            self.assertIsNotNone(ns["buscar_base_smc"](pergunta), pergunta)

    def test_a_base_cresceu_de_verdade(self):
        ns = self._ns()
        self.assertGreaterEqual(len(ns["BASE_SMC"]), 50)

    def test_todo_verbete_tem_titulo_palavras_e_resposta(self):
        """Verbete sem resposta é buraco silencioso: a busca acha e devolve
        vazio."""
        ns = self._ns()
        for item in ns["_todos_os_topicos"]():
            self.assertTrue(item.get("t"), item)
            self.assertTrue(item.get("k"), item.get("t"))
            self.assertGreater(len(item.get("r", "")), 120, item.get("t"))

    def test_a_conta_de_mesa_dele_esta_coberta(self):
        """Ele opera conta APEX — o drawdown que acompanha o pico é a regra
        que mais quebra conta, e não estava em lugar nenhum da base."""
        ns = self._ns()
        item = ns["buscar_base_smc"]("como funciona o trailing drawdown da apex?")
        self.assertIsNotNone(item)
        self.assertIn("flutuante", item["r"].lower())


class TestPrevisualizacaoDaJanela(unittest.TestCase):
    """Escolher janela por título é adivinhação — foi assim que a janela do
    Claude virou 'gráfico' por 20 minutos."""

    def test_o_botao_existe_e_chama_a_previa(self):
        fonte = fonte_do_arquivo()
        self.assertIn("Ver o que o motor vê", fonte)
        self.assertIn("def _previsualizar_janela", fonte)
        self.assertIn("def _previa_worker", fonte)

    def test_a_previa_roda_fora_da_interface(self):
        """Capturar janela leva segundos; travar a janela no meio seria pior
        que não ter o recurso."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _previsualizar_janela")
        self.assertIn("threading.Thread", fonte[i:i + 700])

    def test_a_previa_da_um_VEREDITO_e_nao_so_a_imagem(self):
        """O mesmo OCR que lê a VWAP diz se aquilo é um gráfico. Mostrar a
        miniatura e calar seria devolver a adivinhação para ele."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _previa_worker")
        bloco = fonte[i:i + 2600]
        self.assertIn("ler_indicadores_da_legenda", bloco)
        self.assertIn("É um gráfico", bloco)

    def test_a_referencia_da_imagem_e_guardada(self):
        """No Tk, imagem sem referência viva some da tela — o clássico
        'apareceu em branco'."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _previa_worker")
        self.assertIn("self.img_previa.image = foto", fonte[i:i + 2600])


if __name__ == "__main__":
    unittest.main(verbosity=2)
