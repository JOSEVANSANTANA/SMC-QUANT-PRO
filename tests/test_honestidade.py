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


class TestLeituraInstavelDoIndicador(unittest.TestCase):
    """A guarda da 2.25.0 exigiu o número. Ela conseguiu o número — inventado.

    Print da Tradovate de 12/08 15:45, legenda do candle de 13:25:
        PSAR 7764.20 · SMA 7767.58 · SMA 7766.04 · RSI 55
        VWAP 7769.56 · OPEN 7770.25 · HIGH 7771.25 · LOW 7768.50
        CLOSE 7769.00 · VOLUME 3943 · marcador de preço 7770.24
        POSIÇÃO 0 (nas duas janelas) · ABRIR P/L 0.00 USD

    O que ela respondeu às 15:43:
        "a VWAP está exatamente em 7752.34, conforme indicado na legenda"
        "a média móvel de 50 períodos que está em 7751.28"
        "você está com uma posição de venda aberta em 7753.25"

    Três números que não existem em lugar nenhum daquela tela. Todos com a
    FORMA de uma resposta correta — e é por isso que exigir forma não basta.
    O que separa leitura de invenção é ESTABILIDADE: ler duas vezes o mesmo
    rótulo dá o mesmo número; inventar duas vezes dá dois.
    """

    def _ns(self):
        return carregar(
            ["_sem_acento", "_norm_busca", "_INDICADORES", "_RE_ONDE_INDICADOR",
             "pergunta_onde_esta_indicador", "indicador_da_pergunta",
             "extrair_valor_do_indicador", "numero_da_segunda_leitura",
             "leituras_do_indicador_batem", "_AVISO_LEITURA_INSTAVEL",
             "conferir_leitura_de_nivel"])

    RESPOSTA_1543 = (
        "Olá Josevan. Na captura de agora, a VWAP está exatamente em 7752.34, "
        "conforme indicado na legenda de dados do gráfico. O preço atual está "
        "em 7770.24, trabalhando bem acima dela.")

    def test_sabe_qual_indicador_foi_perguntado(self):
        ns = self._ns()
        self.assertEqual(
            ns["indicador_da_pergunta"]("TIRA UM PRINT, ONDE ESTA A VWAP AGORA?").upper(),
            "VWAP")
        self.assertEqual(ns["indicador_da_pergunta"]("qual o suporte?"), "suporte")
        self.assertIsNone(ns["indicador_da_pergunta"]("compro ou vendo?"))

    def test_pega_o_numero_do_indicador_e_nao_o_do_ativo(self):
        """Na frase real de 15:43 há DOIS números: 7752.34 (dito da VWAP) e
        7770.24 (do preço). Confundir os dois seria repetir o engano original."""
        ns = self._ns()
        self.assertEqual(
            ns["extrair_valor_do_indicador"]("VWAP", self.RESPOSTA_1543), 7752.34)

    def test_duas_leituras_iguais_passam(self):
        """Arredondar 7769.56 para 7769.5 é a mesma leitura."""
        ns = self._ns()
        self.assertTrue(ns["leituras_do_indicador_batem"](7769.56, 7769.5))
        self.assertTrue(ns["leituras_do_indicador_batem"](7769.56, 7769.56))
        self.assertTrue(ns["leituras_do_indicador_batem"](21500.0, 21500.25))

    def test_o_caso_real_nao_passa(self):
        """7752.34 contra os 7769.56 da legenda: 17 pontos. Não é leitura."""
        ns = self._ns()
        self.assertFalse(ns["leituras_do_indicador_batem"](7752.34, 7769.56))

    def test_segunda_leitura_ilegivel_tambem_reprova(self):
        """Não conseguir confirmar não é confirmar. Ausência de prova nunca
        autoriza entregar o número."""
        ns = self._ns()
        self.assertFalse(ns["leituras_do_indicador_batem"](7769.56, None))

    def test_le_a_resposta_curta_nos_dois_formatos(self):
        ns = self._ns()
        self.assertEqual(ns["numero_da_segunda_leitura"]("7769.56"), 7769.56)
        self.assertEqual(ns["numero_da_segunda_leitura"](" 7769,56 "), 7769.56)
        self.assertEqual(ns["numero_da_segunda_leitura"]("VWAP: 7769.56"), 7769.56)

    def test_nao_legivel_nao_vira_numero(self):
        ns = self._ns()
        for t in ("NAO_LEGIVEL", "não legível", "", None):
            self.assertIsNone(ns["numero_da_segunda_leitura"](t), repr(t))

    def test_o_numero_instavel_e_recusado_com_os_dois_valores_a_mostra(self):
        """Ele precisa VER que saíram dois valores — é o que torna a recusa
        verificável em vez de mais uma desculpa."""
        ns = self._ns()
        texto, instavel = ns["conferir_leitura_de_nivel"](
            self.RESPOSTA_1543, "VWAP", 7752.34, 7769.56)
        self.assertTrue(instavel)
        self.assertIn("7752.34", texto)
        self.assertIn("7769.56", texto)
        self.assertIn("não consigo ler esse valor nesta captura", texto.lower())

    def test_leitura_estavel_sai_intacta(self):
        ns = self._ns()
        boa = "A VWAP está em 7769.56."
        texto, instavel = ns["conferir_leitura_de_nivel"](boa, "VWAP", 7769.56, 7769.5)
        self.assertFalse(instavel)
        self.assertEqual(texto, boa)

    def test_sem_numero_afirmado_nao_ha_o_que_conferir(self):
        """Se ela não afirmou valor nenhum, a guarda anterior é que trata —
        esta não pode inventar um problema."""
        ns = self._ns()
        texto = "Não consigo ler esse valor nesta captura."
        saida, instavel = ns["conferir_leitura_de_nivel"](texto, "VWAP", None, None)
        self.assertFalse(instavel)
        self.assertEqual(saida, texto)

    def test_a_segunda_leitura_esta_ligada_no_caminho_da_imagem(self):
        """Função pura que ninguém chama é decoração."""
        fonte = fonte_do_arquivo()
        self.assertIn("_confirmar_nivel_lido", fonte)
        self.assertIn("self._confirmar_nivel_lido(", fonte)
        self.assertIn("temperature=0.0", fonte)


class TestPosicaoAlegada(unittest.TestCase):
    """Ela disse que ele estava vendido. As duas janelas mostravam POSIÇÃO 0."""

    def _ns(self):
        return carregar(["_RE_ALEGA_POSICAO", "_RE_ALEGA_ZERADO",
                         "conferir_posicao_alegada"])

    ABERTA = [{"direcao": "SELL", "ativo": "MESU6", "contratos": 2,
               "entry": 7767.75}]

    def test_a_frase_real_de_1543_e_pega(self):
        ns = self._ns()
        _t, d = ns["conferir_posicao_alegada"](
            "Note que você está com uma posição de venda aberta em 7753.25, e "
            "o preço está subindo contra você.", [])
        self.assertEqual(d, "inventou")

    def test_a_mesma_frase_com_posicao_de_verdade_passa(self):
        ns = self._ns()
        _t, d = ns["conferir_posicao_alegada"](
            "Note que você está com uma posição de venda aberta.", self.ABERTA)
        self.assertIsNone(d)

    def test_dizer_que_esta_zerado_carregando_posicao_tambem_e_erro(self):
        """A recíproca é pior: ele relaxa com risco na mesa."""
        ns = self._ns()
        for t in ("Você está zerado agora.",
                  "Não há nenhuma posição aberta no momento.",
                  "Você não está posicionado."):
            _s, d = ns["conferir_posicao_alegada"](t, self.ABERTA)
            self.assertEqual(d, "omitiu", t)

    def test_a_correcao_diz_qual_posicao_e(self):
        ns = self._ns()
        texto, _d = ns["conferir_posicao_alegada"]("Você está zerado agora.",
                                                   self.ABERTA)
        self.assertIn("SELL", texto)
        self.assertIn("MESU6", texto)
        self.assertIn("7767.75", texto)

    def test_condicional_nao_e_afirmacao(self):
        """'Se você estiver comprado' é hipótese, não alegação de fato."""
        ns = self._ns()
        for t in ("Se você estiver com uma posição de venda, proteja o stop.",
                  "Caso você esteja comprado, considere reduzir.",
                  "Quem estiver vendido deve observar o suporte."):
            _s, d = ns["conferir_posicao_alegada"](t, [])
            self.assertIsNone(d, t)

    def test_conversa_normal_nao_e_tocada(self):
        ns = self._ns()
        texto = "O viés é comprador e a estrutura de alta segue intacta."
        saida, d = ns["conferir_posicao_alegada"](texto, [])
        self.assertIsNone(d)
        self.assertEqual(saida, texto)

    def test_a_guarda_esta_ligada_onde_toda_resposta_passa(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _chat_entregar_resposta")
        bloco = fonte[i:i + 3000]
        self.assertIn("conferir_posicao_alegada", bloco)


class TestDiagnosticoDeProvedor(unittest.TestCase):
    """A OpenAI disse 'no credits remaining'. O app disse 'pode ser uma de três'."""

    def _ns(self):
        return carregar(["diagnostico_de_provedor"])

    ERRO_REAL = ('HTTP 429: {"error": {"message": "You have no credits '
                 'remaining. Add credits to continue using the API at '
                 'https://platform.openai.com/settings"}}')

    def test_sem_credito_e_dito_como_sem_credito(self):
        """Ele passou o dia achando que tinha errado a chave. A chave estava
        certa: a conta é que estava zerada — e a API disse isso."""
        ns = self._ns()
        d = ns["diagnostico_de_provedor"](self.ERRO_REAL, "OpenAI (ChatGPT)")
        self.assertIn("SEM CRÉDITO", d)
        self.assertIn("VÁLIDA", d)

    def test_chave_recusada_e_outra_coisa(self):
        ns = self._ns()
        d = ns["diagnostico_de_provedor"]("HTTP 401 invalid_api_key", "Groq")
        self.assertIn("401", d)
        self.assertIn("RECUSADA", d)

    def test_limite_temporario_nao_vira_chave_errada(self):
        """Um 429 de rate limit some sozinho; um 429 de saldo, não. Tratar os
        dois igual mandava o trader trocar uma chave que estava boa."""
        ns = self._ns()
        d = ns["diagnostico_de_provedor"]("HTTP 429 Rate limit reached", "Groq")
        self.assertIn("limite de uso", d)
        self.assertNotIn("SEM CRÉDITO", d)

    def test_rede_fora_nao_vira_problema_de_chave(self):
        ns = self._ns()
        d = ns["diagnostico_de_provedor"]("Connection timed out", "OpenAI")
        self.assertIn("rede", d.lower())

    def test_erro_desconhecido_mostra_o_texto_original(self):
        """Não conhecer a causa não autoriza esconder a mensagem do provedor."""
        ns = self._ns()
        d = ns["diagnostico_de_provedor"]("Erro esquisito 987", "X")
        self.assertIn("987", d)

    def test_o_app_usa_o_diagnostico_em_vez_do_palpite_triplo(self):
        fonte = fonte_do_arquivo()
        self.assertIn("diagnostico_de_provedor(", fonte)
        self.assertNotIn("pode estar errada, sem crédito, ou o modelo", fonte)

    def test_aponta_a_alternativa_gratuita(self):
        """Sem crédito na OpenAI, mandar 'adicione crédito' e parar aí deixa o
        trader sem cérebro reserva. A Groq tem camada gratuita."""
        fonte = fonte_do_arquivo()
        self.assertIn("console.groq.com/keys", fonte)


class TestApagarLicaoComErroDeDigitacao(unittest.TestCase):
    """14:16 'REMORA ISSO' → nada apagado. 14:17 ela repetiu a lição."""

    def _ns(self):
        return carregar(
            ["_sem_acento", "_norm_busca", "_RE_QUAL_LADO", "pergunta_qual_lado",
             "_RE_DEFINIR_NIVEL", "interpretar_niveis_da_posicao",
             "_RE_NIVEL", "_RE_NIVEL_TEORIA", "pergunta_pede_nivel",
             "_RE_POSTMORTEM", "pergunta_postmortem",
         "_RE_VIRAR_DIA", "_RE_QUAL_PREGAO",
             "_MOTOR_SUBSTANTIVOS", "_MOTOR_ARTIGO", "_MOTOR_NEGADO",
             "_MOTOR_DESLIGAR", "_MOTOR_PARA", "_MOTOR_LIGAR",
             "_PRINT_SOZINHO", "_PRINT_COM_AGORA",
             "_RE_ESQUECER", "pedido_de_esquecer",
             "_COMANDOS_CONHECIDOS", "_distancia_edicao", "corrigir_digitacao",
             "interpretar_intencao", "processar_turno_chat"],
            stubs={"extrair_licao": lambda t: None,
                   "interpretar_configuracao": lambda t: None,
                   "pergunta_sobre_configuracao": lambda t: False,
                   "simbolo_do_texto": lambda t: None,
                   "unicodedata": __import__("unicodedata")})

    def test_remora_isso_apaga(self):
        """Um R no lugar do V. Um comando de DESFAZER que só funciona com a
        grafia perfeita falha justo quando mais se precisa dele."""
        ns = self._ns()
        self.assertEqual(ns["processar_turno_chat"]("REMORA ISSO"),
                         ("ESQUECER", ""))

    def test_o_comando_certo_continua_funcionando(self):
        ns = self._ns()
        self.assertEqual(ns["processar_turno_chat"]("REMOVA ISSO"),
                         ("ESQUECER", ""))
        self.assertEqual(ns["processar_turno_chat"]("apaga a 2"),
                         ("ESQUECER", "2"))

    def test_ensinar_nao_vira_apagar_por_causa_da_correcao(self):
        """A correção de digitação não pode transformar uma intenção em outra."""
        ns = self._ns()
        for t in ("aprenda isso", "sim", "nao", "status"):
            self.assertNotEqual(ns["processar_turno_chat"](t)[0], "ESQUECER", t)


class TestPrecoContraOTitulo(unittest.TestCase):
    """13/08, 10:05. A janela monitorada era:

        'Google Chrome — MESU2026 7.784,00 ▲ +0.23% josevan'

    e o motor mandou ao WhatsApp um cenário inteiro em cima de 7753.25 — trinta
    pontos abaixo, região que o preço já tinha deixado. Pior: 7753.25 era o
    número que o modelo INVENTOU no dia anterior ("você está com uma posição de
    venda aberta em 7753.25"). Ele grudou nele.

    A trava de preço congelado não pegou porque o valor OSCILAVA:
        09:50 → 7753.25 · 09:55 → 7753.25 · 10:00 → 7788.25 · 10:05 → 7753.25

    Mas a corretora escreve o preço AO VIVO no título da aba. Isso é texto do
    sistema operacional — não tem como ser alucinado.
    """

    def _ns(self):
        return carregar(["_num", "_numero_da_legenda", "_RE_PRECO_TITULO",
                         "TOLERANCIA_PRECO_TITULO", "preco_do_titulo",
                         "preco_bate_com_o_titulo"])

    TITULO = "Google Chrome — MESU2026 7.784,00 ▲ +0.23% josevan"

    def test_le_o_preco_do_titulo_real(self):
        self.assertEqual(self._ns()["preco_do_titulo"](self.TITULO), 7784.0)

    def test_le_os_dois_formatos_de_numero(self):
        """A Tradovate em português escreve 7.784,00; em inglês, 7784.00. A
        primeira versão desta função só lia o formato brasileiro."""
        ns = self._ns()
        self.assertEqual(ns["preco_do_titulo"]("MESU2026 7784.00 ▲ +0.23%"), 7784.0)
        self.assertEqual(ns["preco_do_titulo"]("MESU6 7769.56"), 7769.56)
        self.assertEqual(ns["preco_do_titulo"]("MNQZ5 21.500,25 ▼ -0.11%"), 21500.25)

    def test_o_ano_do_contrato_nao_e_preco(self):
        """'MESU2026' tem 2026 dentro. Ler isso como cotação seria trocar um
        erro por outro."""
        ns = self._ns()
        self.assertNotEqual(ns["preco_do_titulo"](self.TITULO), 2026)

    def test_a_variacao_percentual_nao_e_preco(self):
        ns = self._ns()
        self.assertNotEqual(ns["preco_do_titulo"](self.TITULO), 0.23)

    def test_titulo_sem_preco_devolve_None(self):
        ns = self._ns()
        for t in ("🌐 Chrome · Tradovate - brewnt", "Claude — Claude",
                  "Componentes Índice Japão 2", "", None):
            self.assertIsNone(ns["preco_do_titulo"](t), repr(t))

    def test_o_caso_real_e_reprovado(self):
        """7753.25 contra 7784.00: 30,75 pontos. Não é a mesma tela."""
        ns = self._ns()
        bate, do_titulo = ns["preco_bate_com_o_titulo"](7753.25, self.TITULO)
        self.assertFalse(bate)
        self.assertEqual(do_titulo, 7784.0)

    def test_leitura_boa_passa_com_folga(self):
        """Título e captura são de instantes diferentes: alguns pontos de
        diferença são normais e não podem reprovar."""
        ns = self._ns()
        for p in (7784.0, 7784.25, 7788.25, 7780.0, 7790.0):
            self.assertTrue(ns["preco_bate_com_o_titulo"](p, self.TITULO)[0], p)

    def test_sem_titulo_com_preco_nada_e_reprovado(self):
        """Ausência de referência nunca vira reprovação — é a mesma regra do
        piso de qualidade e da distância da entrada."""
        ns = self._ns()
        self.assertTrue(ns["preco_bate_com_o_titulo"](7753.25, "Chrome")[0])
        self.assertTrue(ns["preco_bate_com_o_titulo"](None, self.TITULO)[0])

    def test_a_trava_esta_ligada_ANTES_da_sugestao(self):
        """Se rodasse depois, o cenário já teria ido para o WhatsApp."""
        fonte = fonte_do_arquivo()
        i_conf = fonte.index("bate_titulo, preco_titulo = preco_bate_com_o_titulo(")
        i_grafico = fonte.index("e_grafico, motivo_nao_grafico = leitura_e_de_grafico")
        self.assertLess(i_conf, i_grafico)


class TestImagemDoGrafico(unittest.TestCase):
    """'essa qualidade de print está muito ruim' — 13/08, 09:52.

    A imagem ia como JPEG qualidade 80. Para foto, 80 é ótimo. Para GRÁFICO é
    destruição: o JPEG foi feito para variação suave, e um gráfico é o oposto —
    linha de um pixel, número de 10px, alto contraste. A compressão espalha
    borrão em volta de cada caractere, e é ali que está o preço.
    """

    def test_prefere_PNG_que_nao_perde_nada(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def comprimir_grafico")
        bloco = fonte[i:i + 2200]
        self.assertIn('format="PNG"', bloco)
        self.assertLess(bloco.index('format="PNG"'), bloco.index('format="JPEG"'))

    def test_o_jpeg_de_reserva_desliga_o_subsampling(self):
        """Subsampling é o que borra a cor nas bordas do texto. Desligar custa
        poucos bytes e salva a leitura do número."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def comprimir_grafico")
        self.assertIn("subsampling=0", fonte[i:i + 2200])

    def test_reduzir_o_tamanho_e_o_ULTIMO_recurso(self):
        """Metade dos pixels é metade da chance de ler o número."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def comprimir_grafico")
        bloco = fonte[i:i + 2200]
        self.assertLess(bloco.index('format="JPEG"'), bloco.index("resize("))
        self.assertIn("1280", bloco)

    def test_o_envio_usa_a_compressao_nova(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def enviar_relatorio_whatsapp")
        bloco = fonte[i:i + 900]
        self.assertIn("comprimir_grafico(imagem_print)", bloco)
        self.assertNotIn("quality=80", bloco)


class TestNovaAnalisePeloWhatsApp(unittest.TestCase):
    """Pedido dele: um comando como START/STOP que peça uma leitura AGORA.

    Até aqui o WhatsApp só servia para DECIDIR sobre um cenário que já tinha
    saído. Longe da mesa, isso significava esperar o próximo ciclo de 5 minutos
    sem saber se valia a pena voltar para o computador."""

    def _motor(self):
        import os
        from harness import RAIZ
        with open(os.path.join(RAIZ, "motor", "index.js"), encoding="utf-8") as f:
            return f.read()

    def test_o_motor_reconhece_o_comando(self):
        js = self._motor()
        self.assertIn("CMD_ANALISE", js)
        self.assertIn("'NOVA ANALISE'", js)
        self.assertIn("NOVA_ANALISE", js)

    def test_entra_na_mesma_fila_dos_outros_comandos(self):
        """A fila já trata comando obsoleto — um pedido preso com o app fechado
        não pode virar análise fantasma horas depois."""
        js = self._motor()
        i = js.index("if (CMD_ANALISE.includes(texto))")
        self.assertIn("filaComandos.push", js[i:i + 600])

    def test_o_app_consome_e_dispara(self):
        fonte = fonte_do_arquivo()
        self.assertIn('if tipo == "NOVA_ANALISE":', fonte)
        self.assertIn("def _analise_sob_demanda", fonte)

    def test_o_pedido_obsoleto_e_ignorado(self):
        fonte = fonte_do_arquivo()
        i = fonte.index('if tipo == "NOVA_ANALISE":')
        self.assertIn("120000", fonte[i:i + 700])

    def test_motor_desligado_e_DITO_e_nao_silencio(self):
        """Ele vai estar longe do computador. Silêncio ele leria como 'a
        ferramenta parou'."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _analise_sob_demanda")
        bloco = fonte[i:i + 2600]
        self.assertIn("motor está DESLIGADO", bloco)
        self.assertIn("Não consegui capturar", bloco)

    def test_roda_fora_da_interface(self):
        fonte = fonte_do_arquivo()
        i = fonte.index('if tipo == "NOVA_ANALISE":')
        self.assertIn("threading.Thread", fonte[i:i + 700])


class TestIALocalReligaSozinha(unittest.TestCase):
    """13/08, 09:46 às 10:02: ela respondeu 'a API está fora' a TUDO, porque o
    Ollama estava instalado e PARADO. Ele diagnosticou sozinho e teve de clicar
    em 'Instalar a IA LOCAL' só para subir um serviço.

    Exigir um clique todo dia para religar algo já instalado não é
    configuração, é tarefa — e tarefa que ninguém lembra de fazer é recurso que
    não existe."""

    def test_sobe_na_abertura_do_programa(self):
        fonte = fonte_do_arquivo()
        self.assertIn("_subir_ia_local_no_inicio", fonte)
        self.assertIn("threading.Thread(target=self._subir_ia_local_no_inicio",
                      fonte)

    def test_NUNCA_instala_sozinha(self):
        """Instalar é decisão dele, e continua sendo o botão. Baixar 5 GB sem
        pedir seria abusar da máquina e da internet do cliente."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _subir_ia_local_no_inicio")
        bloco = fonte[i:i + 1800]
        self.assertIn("NUNCA instala nada", bloco)
        self.assertNotIn("_baixar_arquivo", bloco)
        self.assertNotIn("instalar_pacote", bloco)
        self.assertIn("if not exe:", bloco)

    def test_sai_calada_quando_ja_esta_no_ar(self):
        """Dizer 'subi o serviço' sobre um serviço que já rodava é o mesmo tipo
        de mentira do 'Motor no ar' sobre processo morto, ao contrário."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _subir_ia_local_no_inicio")
        bloco = fonte[i:i + 1800]
        self.assertIn("porta_responde(11434)", bloco)
        self.assertIn("return", bloco)

    def test_nunca_atrapalha_a_abertura(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _subir_ia_local_no_inicio")
        bloco = fonte[i:i + 1800]
        self.assertIn("except Exception", bloco)


class TestPermissaoDeMicrofoneNoMac(unittest.TestCase):
    """'não aparece na lista de permissão do Mac' — e essa é a chave.

    No macOS um programa só ENTRA em Ajustes → Privacidade → Microfone depois
    de PEDIR a permissão pela API do sistema (TCC). O PortAudio abre o
    dispositivo por baixo, num caminho que nem sempre dispara esse pedido:
    não aparece prompt, não aparece na lista, e o sistema devolve SILÊNCIO
    sem erro nenhum."""

    def _plat(self):
        import os
        from harness import RAIZ
        with open(os.path.join(RAIZ, "plataforma.py"), encoding="utf-8") as f:
            return f.read()

    def test_existe_como_PEDIR_a_permissao(self):
        plat = self._plat()
        self.assertIn("def pedir_permissao_microfone", plat)
        self.assertIn("requestAccessForMediaType_completionHandler_", plat)

    def test_existe_como_SABER_o_estado_real(self):
        """Quatro estados, e cada um pede uma conversa diferente. Adivinhar
        entre eles foi o que produziu meses de 'troque o dispositivo de
        entrada' para um problema de permissão."""
        plat = self._plat()
        self.assertIn("def estado_permissao_microfone", plat)
        for estado in ("nunca_pedido", "negado", "autorizado", "restrito"):
            self.assertIn(estado, plat, estado)

    def test_o_pedido_acontece_ANTES_de_abrir_o_microfone(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tiger_iniciar")
        bloco = fonte[i:i + 2600]
        self.assertIn("pedir_permissao_microfone", bloco)

    def test_negado_NAO_fica_escutando_o_silencio(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tiger_iniciar")
        bloco = fonte[i:i + 2600]
        self.assertIn('estado == "negado"', bloco)
        self.assertIn("abrir_permissao_microfone", bloco)

    def test_sem_a_biblioteca_ele_DIZ_que_nao_sabe(self):
        """'desconhecido' não pode virar 'autorizado'. Ausência de informação
        não é conclusão — nem aqui."""
        plat = self._plat()
        self.assertIn('"desconhecido"', plat)
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tiger_iniciar")
        self.assertIn('estado == "desconhecido"', fonte[i:i + 2600])

    def test_a_dependencia_esta_declarada(self):
        import os
        from harness import RAIZ
        with open(os.path.join(RAIZ, "requirements-mac.txt"), encoding="utf-8") as f:
            self.assertIn("pyobjc-framework-AVFoundation", f.read())


class TestBaseNaoSequestraPergunta(unittest.TestCase):
    """13/08, 09:52 — regressão que eu criei na 2.30.0 ao pôr a base primeiro:

        ❯ essa qualidade de print está muito ruim, como fazemos para melhorar?
        ✳ [o verbete inteiro de TRAILING STOP]

    A nota foi 2,0 e os DOIS pontos vieram só de semelhança de palavra, com
    ZERO jargão realmente escrito na pergunta. Semelhança serve para
    DESEMPATAR entre candidatos, nunca para eleger um sozinha."""

    def _ns(self):
        return carregar(
            ["_sem_acento", "_norm_busca", "_parecido", "BASE_SMC", "BASE_MACRO",
             "_todos_os_topicos", "_nota_base_smc", "buscar_base_smc"],
            stubs={"unicodedata": __import__("unicodedata")})

    def test_a_frase_real_nao_acha_verbete(self):
        ns = self._ns()
        self.assertIsNone(ns["buscar_base_smc"](
            "essa qualidade de print esta muito ruim, como fazemos para melhorar?"))

    def test_conversa_solta_nao_acha_verbete(self):
        ns = self._ns()
        for t in ("cuidado com isso", "não foi isso que te perguntei",
                  "como foi a última análise?", "obrigado",
                  "você está muito rápida"):
            self.assertIsNone(ns["buscar_base_smc"](t), t)

    def test_e_os_acertos_de_verdade_continuam(self):
        """A trava não pode ter derrubado o que funcionava — senão eu troco um
        defeito por outro maior."""
        ns = self._ns()
        for t in ("o que é smc?", "o que é vwap?", "o que é choch?",
                  "o que é order block?", "o que é atr?", "o que é fvg?",
                  "como fazer trailing stop?", "onde colocar o stop?",
                  "o que é premium e discount?", "o que é inducement?",
                  "o que é tilt?", "o que é poc?"):
            self.assertIsNotNone(ns["buscar_base_smc"](t), t)
