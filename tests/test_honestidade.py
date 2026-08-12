"""As três guardas que ficam entre o modelo e o trader — e a janela que não era gráfico.

O pregão de 12/08 não produziu um defeito: produziu uma família deles, toda
com a mesma raiz. O modelo escreve algo plausível e o app entrega sem conferir.

    14:14 ❯ TIRA UM PRINT, ONDE ESTA A VWAP?
    14:14 ✳ "O preço agora trabalha acima dela, em 7774.25"
    14:15 ❯ TIRA UM PRINT, CONSEGUE ME FALAR ONDE ESTA A VWAP?
    14:15 ✳ "O preço atual está trabalhando acima dela, em 7773.50"
    14:16 ❯ MAS A PORRA DO VWAP ESTA EM 7769,78

Três respostas, nenhuma delas dizendo onde estava a VWAP. O número citado era
o do ATIVO — por isso pareceu resposta, e por isso enganou.

    11:31 ✳ "Quer revisar o que deu errado nesse cenário?"
    11:32 ❯ sim
    11:32 ✳ "Não tenho como responder isso com segurança agora..."

Ela perguntou e não entendeu a própria resposta. Um assistente que pergunta e
não escuta é um formulário.

E, das 13h às 13h20, o motor capturou e mandou para o modelo esta janela:

    'Claude — Claude  [outra área de trabalho]'

Vinte minutos analisando um chat como se fosse mercado, queimando cota, sem
nunca avisar.

REGRA DA CASA: prompt é PEDIDO, não garantia. Onde o dinheiro do trader está em
jogo, quem confere é o app — determinístico, testável, e testado aqui.
"""

import unittest

from harness import carregar, fonte_do_arquivo


class TestNivelDoIndicador(unittest.TestCase):
    """'Onde está a VWAP?' exige o NÚMERO DELA. O pronome não responde."""

    def _ns(self):
        return carregar(
            ["_sem_acento", "_norm_busca", "_INDICADORES", "_RE_ONDE_INDICADOR",
             "pergunta_onde_esta_indicador", "resposta_enrola_o_nivel",
             "_AVISO_NIVEL_NAO_RESPONDIDO", "corrigir_enrolacao_de_nivel"])

    def test_reconhece_a_pergunta_de_nivel(self):
        ns = self._ns()
        for t in ("TIRA UM PRINT, ONDE ESTA A VWAP?",
                  "CONSEGUE ME FALAR ONDE ESTA A VWAP?",
                  "qual o suporte agora?",
                  "onde está a média móvel de 200?",
                  "em que preço está o order block?"):
            self.assertTrue(ns["pergunta_onde_esta_indicador"](t), t)

    def test_pergunta_que_nao_e_de_nivel_fica_de_fora(self):
        """A guarda não pode disparar em conversa normal — corretor que grita
        errado é desligado, e aí não corrige mais nada."""
        ns = self._ns()
        for t in ("compro ou vendo?", "status", "liga o motor",
                  "o que deu errado na sugestão?", "bom dia"):
            self.assertFalse(ns["pergunta_onde_esta_indicador"](t), t)

    def test_a_resposta_real_do_dia_12_08_e_pega(self):
        """A frase exata que ele recebeu três vezes."""
        ns = self._ns()
        self.assertTrue(ns["resposta_enrola_o_nivel"](
            "TIRA UM PRINT, ONDE ESTA A VWAP?",
            "O preço agora trabalha acima dela, em 7774.25"))
        self.assertTrue(ns["resposta_enrola_o_nivel"](
            "CONSEGUE ME FALAR ONDE ESTA A VWAP?",
            "O preço atual está trabalhando acima dela, em 7773.50"))

    def test_resposta_com_o_numero_do_indicador_passa(self):
        ns = self._ns()
        self.assertFalse(ns["resposta_enrola_o_nivel"](
            "ONDE ESTA A VWAP?",
            "A VWAP está em 7769.78; o preço trabalha acima dela, em 7774.25"))
        self.assertFalse(ns["resposta_enrola_o_nivel"](
            "qual o suporte?", "O suporte imediato está em 7739."))

    def test_admitir_que_nao_le_nao_e_enrolacao(self):
        """Dizer 'não consigo ler' é a resposta CERTA quando não dá para ler.
        Se a guarda punisse isso, empurraria o modelo de volta ao chute."""
        ns = self._ns()
        self.assertFalse(ns["resposta_enrola_o_nivel"](
            "ONDE ESTA A VWAP?",
            "Não consigo ler esse valor nesta captura — a legenda está cortada."))

    def test_a_correcao_e_anexada_e_o_texto_original_fica(self):
        """A leitura de contexto costuma estar certa; o que não pode é a
        evasão passar como resposta. Por isso anexa, não apaga."""
        ns = self._ns()
        original = "O preço agora trabalha acima dela, em 7774.25"
        texto, corrigiu = ns["corrigir_enrolacao_de_nivel"](
            "ONDE ESTA A VWAP?", original)
        self.assertTrue(corrigiu)
        self.assertIn(original, texto)
        self.assertIn("não consigo ler esse valor nesta captura", texto.lower())

    def test_resposta_boa_sai_intacta(self):
        ns = self._ns()
        boa = "A VWAP está em 7769.78."
        texto, corrigiu = ns["corrigir_enrolacao_de_nivel"]("ONDE ESTA A VWAP?", boa)
        self.assertFalse(corrigiu)
        self.assertEqual(texto, boa)

    def test_a_persona_tambem_proibe_o_pronome(self):
        """Cinto e suspensório: a guarda conserta o que escapa, mas o prompt
        precisa pedir certo — senão a correção vira o caminho normal."""
        fonte = fonte_do_arquivo()
        self.assertIn("PERGUNTA DE NÍVEL EXIGE O NÚMERO", fonte)


class TestNumerosDaMesa(unittest.TestCase):
    """O número da conta dele tem dono, e o dono é o disco."""

    def _ns(self):
        return carregar(["_ROTULOS_DE_FATO", "TOLERANCIA_FATO_USD",
                         "_valor_perto_do_rotulo", "conferir_numeros_da_mesa"])

    FATOS = {"margem": 1400.0, "meta": 1000.0, "drawdown": 1400.0,
             "hoje": -135.0, "ciclo": -135.0}

    def test_numero_certo_passa_sem_ruido(self):
        ns = self._ns()
        texto = "Sua margem é US$ 1.400 e a meta é US$ 1.000."
        saida, div = ns["conferir_numeros_da_mesa"](texto, self.FATOS)
        self.assertEqual(div, [])
        self.assertEqual(saida, texto)

    def test_numero_errado_e_corrigido_pelo_registro(self):
        ns = self._ns()
        saida, div = ns["conferir_numeros_da_mesa"](
            "Hoje você está em US$ -240,00, cuidado.", self.FATOS)
        self.assertEqual(len(div), 1)
        self.assertEqual(div[0][0], "hoje")
        self.assertIn("-135", saida.replace(",", "").replace(".00", ""))

    def test_o_sinal_por_extenso_nao_vira_divergencia(self):
        """'US$ 135 negativo' e 'US$ -135' são a mesma frase."""
        ns = self._ns()
        _s, div = ns["conferir_numeros_da_mesa"](
            "Resultado do dia: US$ 135 negativo.", self.FATOS)
        self.assertEqual(div, [])

    def test_meta_diaria_nao_e_a_meta_do_ciclo(self):
        """São números diferentes e ambos corretos. Corrigir um contra o outro
        seria inventar um erro onde não há."""
        ns = self._ns()
        for t in ("A meta diária é US$ 200,00.",
                  "A meta do dia é US$ 200,00.",
                  "Você precisa de US$ 200 por dia."):
            _s, div = ns["conferir_numeros_da_mesa"](t, self.FATOS)
            self.assertEqual(div, [], t)

    def test_drawdown_restante_nao_e_o_drawdown_do_plano(self):
        ns = self._ns()
        _s, div = ns["conferir_numeros_da_mesa"](
            "O drawdown restante hoje é US$ 1.265,00.", self.FATOS)
        self.assertEqual(div, [])

    def test_conversa_sem_numero_nao_e_tocada(self):
        ns = self._ns()
        texto = "Bom dia, Josevan. O viés é comprador e a estrutura está de alta."
        saida, div = ns["conferir_numeros_da_mesa"](texto, self.FATOS)
        self.assertEqual(div, [])
        self.assertEqual(saida, texto)

    def test_sem_fatos_no_disco_nada_e_corrigido(self):
        """Sem fonte, não há conferência. Corrigir contra o vazio seria trocar
        um erro por outro."""
        ns = self._ns()
        texto = "Sua margem é US$ 99.999."
        saida, div = ns["conferir_numeros_da_mesa"](texto, {})
        self.assertEqual(div, [])
        self.assertEqual(saida, texto)

    def test_arredondamento_de_centavos_nao_e_erro(self):
        ns = self._ns()
        _s, div = ns["conferir_numeros_da_mesa"](
            "A margem é US$ 1.400,50.", self.FATOS)
        self.assertEqual(div, [])

    def test_le_os_dois_formatos_de_numero(self):
        """1.400,50 (pt-BR) e 1,400.50 (en-US) aparecem na mesma resposta —
        o modelo troca de formato sem avisar."""
        ns = self._ns()
        v1, _ = ns["_valor_perto_do_rotulo"]("margem US$ 1.400,00",
                                             ns["_ROTULOS_DE_FATO"]["margem"])
        v2, _ = ns["_valor_perto_do_rotulo"]("margem US$ 1,400.00",
                                             ns["_ROTULOS_DE_FATO"]["margem"])
        self.assertEqual(v1, 1400.0)
        self.assertEqual(v2, 1400.0)


class TestJanelaQueNaoEGrafico(unittest.TestCase):
    """'Claude — Claude' foi analisada por 20 minutos como se fosse mercado."""

    def _ns(self):
        return carregar(["VALOR_POR_PONTO", "VALOR_POR_PONTO_PADRAO", "_num",
                         "_TICKER_VAZIO", "_MESES_FUTUROS",
                         "_e_contrato_conhecido", "leitura_e_de_grafico"])

    def test_grafico_de_verdade_passa(self):
        ns = self._ns()
        for ativo, preco in (("MESU6", 7774.25), ("MES", 7774.25),
                             ("MNQZ5", 21500.0), ("WINQ6", 137000.0)):
            ok, motivo = ns["leitura_e_de_grafico"](ativo, preco)
            self.assertTrue(ok, f"{ativo}: {motivo}")
            self.assertIsNone(motivo)

    def test_sem_ticker_nao_e_grafico(self):
        ns = self._ns()
        for ativo in ("DESCONHECIDO", "", None, "N/A", "-", "?", "não identificado"):
            ok, motivo = ns["leitura_e_de_grafico"](ativo, 7774.25)
            self.assertFalse(ok, repr(ativo))
            self.assertTrue(motivo)

    def test_sem_preco_nao_e_grafico(self):
        """Gráfico de futuro sempre tem preço. Uma janela de conversa não."""
        ns = self._ns()
        for preco in (None, 0, -1, "", "n/a"):
            ok, _m = ns["leitura_e_de_grafico"]("MESU6", preco)
            self.assertFalse(ok, repr(preco))

    def test_ticker_que_nao_e_ticker_e_recusado(self):
        ns = self._ns()
        for ativo in ("Claude", "Chat", "Google Chrome", "MES U6", "MESU6-CONT"):
            ok, _m = ns["leitura_e_de_grafico"](ativo, 7774.25)
            self.assertFalse(ok, ativo)

    def test_contrato_fora_da_tabela_nao_dimensiona(self):
        """Não é preciosismo: valor_por_ponto_do_ativo cai no padrão de 5,0
        quando não reconhece o símbolo. Dimensionar em cima desse 5,0 chutado
        é inventar número com cara de cálculo."""
        ns = self._ns()
        ok, motivo = ns["leitura_e_de_grafico"]("AAPL", 230.0)
        self.assertFalse(ok)
        self.assertIn("quanto vale um ponto", motivo)

    def test_o_motivo_e_uma_frase_util_e_nao_um_codigo(self):
        """O trader lê isto no log e no chat. Tem de dizer o que houve."""
        ns = self._ns()
        for ativo, preco in (("DESCONHECIDO", 7774.0), ("MESU6", None),
                             ("Claude", 7774.0), ("AAPL", 230.0)):
            _ok, motivo = ns["leitura_e_de_grafico"](ativo, preco)
            self.assertGreater(len(motivo), 25, f"{ativo}/{preco}: {motivo}")

    def test_o_motor_realmente_usa_a_trava(self):
        """A função pode existir e não estar ligada em lugar nenhum — foi assim
        que o aviso de preço congelado passou versões avisando sem impedir."""
        fonte = fonte_do_arquivo()
        self.assertIn("leitura_e_de_grafico(ativo, preco)", fonte)
        self.assertIn("ciclos_sem_grafico", fonte)

    def test_a_contagem_e_por_janela_e_nao_global(self):
        """Uma janela errada não pode calar o alerta da outra, que pode estar
        certa. Este é o requisito de 'nunca confundir uma análise com a outra'."""
        fonte = fonte_do_arquivo()
        self.assertIn('"ciclos_sem_grafico": 0', fonte)
        self.assertIn('est["ciclos_sem_grafico"] = ciclos_sem_grafico', fonte)


class TestPostMortem(unittest.TestCase):
    """'sim' respondendo à pergunta que ELA fez, e a autópsia sem depender de API."""

    def _ns(self):
        return carregar(
            ["_sem_acento", "_norm_busca", "_RE_POSTMORTEM",
             "pergunta_postmortem"])

    def test_reconhece_o_pedido_de_autopsia(self):
        ns = self._ns()
        for t in ("o que deu errado na sugestão que você havia me passado",
                  "por que tomei stop?",
                  "quer revisar o que deu errado nesse cenário",
                  "analisa a operação que deu ruim",
                  "post mortem"):
            self.assertTrue(ns["pergunta_postmortem"](t), t)

    def test_nao_confunde_com_conversa_normal(self):
        ns = self._ns()
        for t in ("bom dia", "status", "compro ou vendo?", "liga o motor"):
            self.assertFalse(ns["pergunta_postmortem"](t), t)

    def test_a_autopsia_vem_antes_de_pedir_grafico(self):
        """'o que deu errado no stop' tem 'stop' no meio e cairia em
        VER_GRAFICO, queimando cota da API para responder algo que está
        inteiro no disco. A ordem no roteador é a correção."""
        fonte = fonte_do_arquivo()
        i_post = fonte.index("if pergunta_postmortem(t):")
        i_nivel = fonte.index("def pergunta_pede_nivel")
        self.assertLess(i_post, fonte.index("pergunta_pede_nivel(t)", i_nivel),
                        "POSTMORTEM precisa ser testado antes de VER_GRAFICO")

    def test_o_sim_dela_tem_dono(self):
        """Sem o tópico pendente, o 'sim' chegava solto ao modelo — que estava
        sem cota — e virava a desculpa genérica."""
        fonte = fonte_do_arquivo()
        self.assertIn("_topico_pendente", fonte)
        self.assertIn('if pendente and interpretar_intencao(texto) == "SIM":', fonte)

    def test_mudar_de_assunto_encerra_o_topico(self):
        """Senão um 'sim' de outra conversa, dez minutos depois, dispararia a
        autópsia de uma operação que ele já esqueceu."""
        fonte = fonte_do_arquivo()
        self.assertIn("Qualquer outra coisa encerra o tópico", fonte)


class TestPonteDoWhatsApp(unittest.TestCase):
    """Códigos 428 e 500 a cada ~10 minutos, a tarde inteira, com espera fixa."""

    def _motor(self):
        import os
        from harness import RAIZ
        with open(os.path.join(RAIZ, "motor", "index.js"), encoding="utf-8") as f:
            return f.read()

    def test_a_espera_dobra_em_vez_de_ficar_em_5s(self):
        js = self._motor()
        self.assertIn("function esperaDaProximaTentativa", js)
        self.assertIn("Math.pow(2, tentativasReconexao)", js)
        self.assertIn("ESPERA_TETO_MS", js)

    def test_a_escada_zera_so_com_a_conexao_aberta(self):
        """Zerar em 'connecting' faria o backoff nunca subir — o defeito
        clássico de quem implementa backoff sem testar."""
        js = self._motor()
        i_open = js.index("if (connection === 'open')")
        i_zera = js.index("tentativasReconexao = 0", i_open)
        i_close = js.index("if (connection === 'close')")
        self.assertLess(i_zera, i_close)

    def test_o_500_repetido_gera_QR_novo_em_vez_de_insistir(self):
        """DisconnectReason.badSession === 500: reconectar com a MESMA
        credencial nunca vai funcionar. Insistir foi o loop da tarde toda."""
        js = self._motor()
        self.assertIn("DisconnectReason.badSession", js)
        self.assertIn("QUEDAS_500_PARA_REPAREAR", js)
        self.assertIn("quedas500Seguidas", js)

    def test_nenhuma_reconexao_ficou_com_espera_fixa(self):
        js = self._motor()
        self.assertNotIn("agendarReconexao(5000", js)

    def test_a_instabilidade_chega_ao_trader(self):
        """Instabilidade que só existe dentro do log do motor faz o trader
        concluir que a ferramenta parou — sem saber de quê."""
        js = self._motor()
        self.assertIn("quedas_recentes", js)
        self.assertIn("tentativas_reconexao", js)
        fonte = fonte_do_arquivo()
        self.assertIn("_conferir_saude_do_whatsapp", fonte)
        self.assertIn("/status", fonte)

    def test_o_aviso_nao_se_repete_a_cada_minuto(self):
        """Aviso repetido vira ruído, e ruído é ignorado quando importa."""
        fonte = fonte_do_arquivo()
        self.assertIn("_wpp_instavel", fonte)


class TestContextoQueChegaAoModelo(unittest.TestCase):
    """Contexto que existe em memória e não chega ao modelo é burrice barata."""

    def test_a_leitura_dos_outros_ativos_entra_no_contexto(self):
        fonte = fonte_do_arquivo()
        self.assertIn("_analises_por_ativo", fonte)
        self.assertIn("LEITURA MAIS RECENTE DOS OUTROS ATIVOS MONITORADOS", fonte)

    def test_cada_leitura_diz_de_qual_janela_veio(self):
        """'Nunca confundir uma análise com a outra, de uma janela com a
        outra' — a exigência do trader, virada teste."""
        fonte = fonte_do_arquivo()
        i = fonte.index("LEITURA MAIS RECENTE DOS OUTROS ATIVOS MONITORADOS")
        bloco = fonte[i - 900:i + 400]
        self.assertIn("janela", bloco)
        self.assertIn("nunca misturadas", bloco)

    def test_as_tres_guardas_rodam_no_mesmo_ponto(self):
        """Uma guarda que roda só em alguns caminhos é uma guarda que não
        existe. As três ficam onde TODA resposta de modelo passa."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _chat_entregar_resposta")
        bloco = fonte[i:i + 2200]
        self.assertIn("censurar_alegacao_falsa", bloco)
        self.assertIn("corrigir_enrolacao_de_nivel", bloco)
        self.assertIn("conferir_numeros_da_mesa", bloco)


if __name__ == "__main__":
    unittest.main(verbosity=2)
