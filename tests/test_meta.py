"""A PERGUNTA DA META, QUE ELA NÃO SABIA RESPONDER TENDO TODOS OS DADOS.

13/08, 16:01. Ele perguntou:

    "O DIA ENCERRA AS 17:59, como estamos de probabilidade de bater a meta
     de hoje até la?"

E recebeu: "Com base nas condições atuais, não tenho dados suficientes para
prever com precisão se você alcançará sua meta de hoje."

A meta estava no Plano de Trading. O resultado do dia estava no diário. O
horário de fechamento estava na configuração. Quem não tinha os dados era o
MODELO — a pergunta nunca chegou ao código que sabia respondê-la.

Ele tentou consertar do jeito que dava: "olha no plano de trading e o motor
para responder essa pergunta - aprenda isso". Isso não podia funcionar, e vale
dizer por quê: lição vira TEXTO no prompt, não vira acesso ao diário. Nenhuma
frase gravada faz um modelo ler um arquivo. Às 16:05 ele perguntou de novo e
recebeu a mesma não-resposta.

Agora é conta, feita por código, antes de qualquer modelo.
"""

import datetime
import unittest

from harness import carregar, fonte_do_arquivo
from test_conversa import _ns_intencao


class TestAContaDaChance(unittest.TestCase):
    """Binomial exata sobre os números DELE. Nada estimado."""

    def _ns(self):
        return carregar(["_combinacoes", "chance_de_bater_a_meta"])

    def test_meta_ja_batida_e_100(self):
        ns = self._ns()
        prob, precisa, _n = ns["chance_de_bater_a_meta"](-50, 5, 0.4, 100, 80)
        self.assertEqual(prob, 100.0)
        self.assertEqual(precisa, 0)

    def test_sem_operacao_cabendo_e_zero(self):
        """Zero operações possíveis é 0%, não 'não sei'."""
        ns = self._ns()
        prob, _k, n = ns["chance_de_bater_a_meta"](500, 0, 0.5, 100, 100)
        self.assertEqual(prob, 0.0)
        self.assertEqual(n, 0)

    def test_nem_acertando_TUDO_da_e_isso_e_dito_como_zero(self):
        """Precisa de US$1000, cabem 3 operações de US$100. Acertar as três dá
        300. A resposta honesta é 0% — não 'baixa'."""
        ns = self._ns()
        prob, precisa, n = ns["chance_de_bater_a_meta"](1000, 3, 0.9, 100, 50)
        self.assertEqual(prob, 0.0)
        self.assertGreater(precisa, n)

    def test_uma_operacao_que_basta_vale_a_taxa_de_acerto(self):
        """Uma operação, um acerto basta: a chance É a taxa de acerto."""
        ns = self._ns()
        prob, precisa, _n = ns["chance_de_bater_a_meta"](90, 1, 0.38, 100, 80)
        self.assertEqual(precisa, 1)
        self.assertAlmostEqual(prob, 38.0, places=1)

    def test_a_conta_bate_com_a_binomial_feita_a_mao(self):
        """Falta 100; ganho 100, perda 100, 3 operações. k >= (100+300)/200 = 2.
        P(k>=2) com p=0.5 = C(3,2)*.125 + C(3,3)*.125 = 3/8 + 1/8 = 50%."""
        ns = self._ns()
        prob, precisa, _n = ns["chance_de_bater_a_meta"](100, 3, 0.5, 100, 100)
        self.assertEqual(precisa, 2)
        self.assertAlmostEqual(prob, 50.0, places=1)

    def test_perder_nao_conta_como_ganhar_menos(self):
        """Com perda média maior, a mesma meta exige mais acertos. Se a perda
        fosse ignorada, a chance sairia otimista — e otimismo na conta da meta
        é o que faz alguém dobrar a aposta às 17h."""
        ns = self._ns()
        sem_perda = ns["chance_de_bater_a_meta"](200, 4, 0.5, 100, 0)
        com_perda = ns["chance_de_bater_a_meta"](200, 4, 0.5, 100, 100)
        self.assertGreater(sem_perda[1] and com_perda[1], 0)
        self.assertGreater(com_perda[1], sem_perda[1])
        self.assertLess(com_perda[0], sem_perda[0])

    def test_numero_faltando_devolve_None_e_nao_um_palpite(self):
        ns = self._ns()
        for args in ((100, 3, 0.5, 0, 50),        # sem ganho médio
                     (100, 3, 1.5, 100, 50),      # taxa fora de 0..1
                     ("x", 3, 0.5, 100, 50),      # lixo
                     (100, -1, 0.5, 100, 50)):    # operações negativas
            self.assertIsNone(ns["chance_de_bater_a_meta"](*args), args)

    def test_combinacoes_confere(self):
        ns = self._ns()
        self.assertEqual(ns["_combinacoes"](5, 2), 10)
        self.assertEqual(ns["_combinacoes"](3, 0), 1)
        self.assertEqual(ns["_combinacoes"](3, 4), 0)


class TestQuantasOperacoesAindaCabem(unittest.TestCase):
    """A cadência sai do que ELE fez hoje, não de uma média inventada."""

    def _ns(self):
        return carregar(["operacoes_que_ainda_cabem"])

    def test_no_ritmo_do_dia(self):
        """16 operações em 240 min = uma a cada 15 min. Em 120 min cabem 8."""
        ns = self._ns()
        self.assertEqual(ns["operacoes_que_ainda_cabem"](120, 16, 240), 8)

    def test_o_teto_do_plano_manda_quando_e_menor(self):
        """Teto de 20 no dia com 16 feitas: cabem 4, mesmo que o tempo dê 8."""
        ns = self._ns()
        self.assertEqual(ns["operacoes_que_ainda_cabem"](120, 16, 240, 20), 4)

    def test_teto_ja_estourado_e_zero_nao_negativo(self):
        ns = self._ns()
        self.assertEqual(ns["operacoes_que_ainda_cabem"](120, 16, 240, 10), 0)

    def test_sem_operacao_nenhuma_nao_ha_ritmo_para_medir(self):
        """Sem uma operação fechada não existe cadência. Inventar uma aqui
        inventaria a conta inteira que vem depois."""
        ns = self._ns()
        self.assertIsNone(ns["operacoes_que_ainda_cabem"](120, 0, 240))
        self.assertIsNone(ns["operacoes_que_ainda_cabem"](120, 3, 0))

    def test_pregao_fechado_nao_cabe_nada(self):
        ns = self._ns()
        self.assertEqual(ns["operacoes_que_ainda_cabem"](0, 16, 240), 0)


class TestMinutosAteOFechamento(unittest.TestCase):
    """O horário sai da CONFIGURAÇÃO dele, inclusive o pregão que vira o dia."""

    def _ns(self):
        return carregar(["PADRAO_CONFIG_APP", "minutos_ate_o_fim_do_pregao"],
                        stubs={"carregar_config": lambda: {
                            "hora_inicio": "19:00", "hora_fim": "17:59"}})

    def _ns_diurno(self):
        return carregar(["PADRAO_CONFIG_APP", "minutos_ate_o_fim_do_pregao"],
                        stubs={"carregar_config": lambda: {
                            "hora_inicio": "09:00", "hora_fim": "18:00"}})

    def test_a_pergunta_dele_as_16h01(self):
        """'o dia encerra às 17:59' — às 16:01 faltavam 118 minutos."""
        ns = self._ns()
        agora = datetime.datetime(2026, 8, 13, 16, 1)
        self.assertEqual(ns["minutos_ate_o_fim_do_pregao"](agora), 118)

    def test_pregao_que_vira_o_dia_conta_ate_amanha(self):
        """Às 22h de quinta, com o pregão 19:00→17:59, o fim é às 17:59 de
        sexta: 19h59 pela frente, não 'já fechou'."""
        ns = self._ns()
        agora = datetime.datetime(2026, 8, 13, 22, 0)
        self.assertEqual(ns["minutos_ate_o_fim_do_pregao"](agora),
                         19 * 60 + 59)

    def test_depois_do_fechamento_e_zero(self):
        ns = self._ns_diurno()
        agora = datetime.datetime(2026, 8, 13, 18, 30)
        self.assertEqual(ns["minutos_ate_o_fim_do_pregao"](agora), 0)

    def test_horario_ilegivel_devolve_None_e_nao_zero(self):
        """Zero significaria 'o pregão fechou', que é uma afirmação. None
        significa 'não sei ler o horário', que é a verdade."""
        ns = carregar(["PADRAO_CONFIG_APP", "minutos_ate_o_fim_do_pregao"],
                      stubs={"carregar_config": lambda: {"hora_fim": "abacaxi"}})
        self.assertIsNone(ns["minutos_ate_o_fim_do_pregao"](
            datetime.datetime(2026, 8, 13, 16, 1)))


class TestAPerguntaChegaNoCodigo(unittest.TestCase):
    """De nada adianta a conta existir se a pergunta continuar indo ao modelo."""

    def _ns(self):
        # O MESMO carregador do test_conversa: interpretar_intencao puxa meio
        # arquivo junto, e manter duas listas dessas dependências seria manter
        # duas chances de elas divergirem.
        return _ns_intencao()

    def test_a_frase_EXATA_que_ele_escreveu(self):
        ns = self._ns()
        self.assertEqual(
            ns["interpretar_intencao"](
                "O DIA ENCERRA AS 17:59, como estamos de probabilidade de "
                "bater a meta de hoje até la?"),
            "META")

    def test_as_outras_formas_de_perguntar_a_mesma_coisa(self):
        ns = self._ns()
        for frase in ("da pra bater a meta hoje?",
                      "qual a chance de batermos a meta?",
                      "quanto falta para a meta de hoje?",
                      "consigo atingir a meta ainda hoje?",
                      "vou conseguir bater a meta?"):
            self.assertEqual(ns["interpretar_intencao"](frase), "META", frase)

    def test_nao_rouba_o_turno_de_quem_so_falou_em_meta(self):
        """'mude a meta para 5000' é CONFIGURAR, não a conta da meta."""
        ns = self._ns()
        self.assertNotEqual(ns["interpretar_intencao"]("qual e a metodologia?"),
                            "META")
        self.assertNotEqual(ns["interpretar_intencao"]("status"), "META")

    def test_META_e_executada_como_acao_local(self):
        """Ação local = resposta instantânea, sem passar por modelo nenhum."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def processar_turno_chat")
        self.assertIn('"STATUS", "META"', fonte[i:i + 6000])
        j = fonte.index("def _chat_executar_acao")
        self.assertIn('if acao == "META":', fonte[j:j + 400])


class TestATextoDaMetaNaoInventa(unittest.TestCase):
    """A regra da casa vale aqui mais que em qualquer lugar: é um número que
    ele vai usar para decidir se opera mais ou se para."""

    def _bloco(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _texto_da_meta_de_hoje")
        return fonte[i:fonte.index("def _meta_falada")]

    def test_sem_operacao_fechada_ele_RECUSA_a_porcentagem(self):
        """Sem taxa de acerto medida, qualquer porcentagem seria invenção."""
        bloco = self._bloco()
        self.assertIn("NÃO vou te dar uma porcentagem", bloco)
        self.assertIn("seria inventada", bloco)

    def test_diz_de_onde_saiu_o_numero(self):
        """Conta sem premissa declarada vira promessa."""
        bloco = self._bloco()
        self.assertIn("Como eu cheguei nisso", bloco)
        self.assertIn("não previsão de mercado", bloco)

    def test_usa_a_meta_do_DIA_e_nao_a_do_ciclo(self):
        """Confundir o que falta HOJE com o que falta no ciclo inteiro daria
        uma conta impossível e um veredito errado."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _numeros_da_meta_de_hoje")
        bloco = fonte[i:i + 3000]
        self.assertIn('d["falta_hoje"]', bloco)
        self.assertIn('d["ritmo_dia"] - d["resultado_hoje"]', bloco)

    def test_chance_baixa_nao_vira_incentivo(self):
        """20% de chance às 17h é o momento exato em que um dia ruim vira um
        dia caro."""
        bloco = self._bloco()
        self.assertIn("dia ruim num dia caro", bloco)

    def test_meta_batida_lembra_que_da_para_PARAR(self):
        bloco = self._bloco()
        self.assertIn("permite parar", bloco)

    def test_le_os_carimbos_que_o_diario_realmente_grava(self):
        """`hora_abertura` não existe no diário — campo inventado devolveria
        None sempre, e a conta sumiria em silêncio."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _numeros_da_meta_de_hoje")
        bloco = fonte[i:i + 3000]
        self.assertIn('_hora_do_registro(p.get("data_abertura"))', bloco)
        self.assertNotIn("hora_abertura", bloco)


class TestAEsperaTemTETO(unittest.TestCase):
    """'não responde perguntas rápido, está demorando muito pensando'.

    Onze modelos × até quatro configurações × 60 s de prazo. Com a cota
    estourada isso passava de dez minutos ANTES de ela chegar na base própria
    — que responde na hora, do disco, sem cota. Ele ficava olhando
    '✳ pensando…' com a resposta pronta, presa atrás de uma fila."""

    def _ns(self):
        return carregar(["ORCAMENTO_CHAT_SEG", "TIMEOUT_CHAT_MS"])

    def test_existe_um_orcamento_de_tempo(self):
        ns = self._ns()
        self.assertLessEqual(ns["ORCAMENTO_CHAT_SEG"], 60)
        self.assertGreaterEqual(ns["ORCAMENTO_CHAT_SEG"], 20)

    def test_o_prazo_da_chamada_NAO_voltou_para_15s(self):
        """Os 15 s originais estouravam antes de a resposta com busca na
        internet chegar, e produziam 'estou sem acesso à rede' com a rede
        funcionando. O corte tinha de ser no total, não na chamada."""
        ns = self._ns()
        self.assertGreaterEqual(ns["TIMEOUT_CHAT_MS"], 30_000)

    def test_o_laco_confere_o_relogio_nos_DOIS_niveis(self):
        """Só no laço de fora, um modelo com quatro configurações lentas
        passaria muito do teto."""
        fonte = fonte_do_arquivo()
        i = fonte.index("inicio_espera = time.time()")
        bloco = fonte[i:i + 1800]
        self.assertEqual(
            bloco.count("(time.time() - inicio_espera) > orcamento"), 2)

    def test_VIDEO_nao_tem_teto_mas_IMAGEM_tem(self):
        """Ler um VÍDEO demora mesmo; ali a espera é o serviço.

        IMAGEM é outra coisa, e confundir as duas custou cinco minutos de
        silêncio. 18/08, 14:53: "tira um print, se atenta nesse indicador novo
        que coloquei na plataforma tradovate". Às 14:58 o cabeçalho ainda dizia
        "olhando o gráfico (print de 14:53)…" e nada tinha chegado — porque a
        regra "anexo não tem teto" tratava o print de gráfico como se fosse um
        vídeo: 300 s por chamada, nove modelos, teto do turno desligado.

        O print vai embutido na mensagem, tem alguns KB e é lido em segundos.
        Agora ele tem prazo e teto próprios."""
        fonte = fonte_do_arquivo()
        i = fonte.index("inicio_espera = time.time()")
        bloco = fonte[i:i + 900]
        self.assertIn("if anexo_e_imagem(anexo):", bloco)
        self.assertIn("orcamento = ORCAMENTO_CHAT_IMAGEM_SEG", bloco)
        self.assertIn("orcamento = None", bloco, "vídeo perdeu a paciência")
        self.assertNotIn("orcamento = None if anexo else", bloco,
                         "a imagem voltou a herdar a espera do vídeo")

    def test_a_imagem_tem_prazo_proprio_por_chamada(self):
        fonte = fonte_do_arquivo()
        self.assertIn("TIMEOUT_CHAT_IMAGEM_MS if anexo_e_imagem(anexo)", fonte)
        self.assertIn("ORCAMENTO_CHAT_IMAGEM_SEG = ", fonte)

    def test_estourar_o_teto_e_DITO_no_registro(self):
        """Resposta que veio da base em vez da Gemini tem origem diferente, e
        isso não pode ficar escondido. E o aviso diz o teto REAL do turno —
        45 s sem anexo, 90 s com imagem — em vez de citar sempre o de texto."""
        fonte = fonte_do_arquivo()
        self.assertIn("Passei de {orcamento}s tentando a Gemini", fonte)
        self.assertIn("com a imagem ", fonte)


class TestLicaoQueNaoEnsina(unittest.TestCase):
    """A lista dele tinha SEIS lições, e a de número 6 era uma pergunta:
    'o que aconteceu com HAPV3 HOJE?'. Ela entrava em toda análise e toda
    conversa, porque as lições vão inteiras para dentro do prompt."""

    def _ns(self):
        return carregar(["_sem_acento", "_e_pergunta", "_RE_FATO_EFEMERO",
                         "_e_fato_efemero",
                         "_LICAO_IMPOSSIVEL", "licao_pede_invencao",
                         "_LICAO_ACAO_WHATSAPP_RECEBE", "licao_pede_acao",
                         "separar_pergunta_da_regra", "licoes_que_nao_ensinam"])

    def test_a_lista_REAL_dele_e_limpa_na_medida_certa(self):
        ns = self._ns()
        boas, ruins = ns["licoes_que_nao_ensinam"]([
            "preste atencao nos detalhes, seja absurdamente atento, nao invente "
            "numeros, nao invente textos, nao tenha supsicoes",
            "nunca invente numeros, nunca alucine, nunca invente dados",
            "tira um print e olha o preco atual, nunca forneca recomendacoes "
            "sem olhar o preco atual",
            "toda vez que pedir alguma analise ou detalhe sobre algum "
            "indicador, tire um print novo e analise para me responder",
            "toda vez que te perguntar um preco de um determinado ativo/indice,"
            "voce acessa yahoo finance ou google finance na web e extraia a "
            "ultima atualizacao de preco daquele ativo ou indice etc",
            "o que aconteceu com HAPV3 HOJE?",
        ])
        self.assertEqual(len(boas), 5, "levou lição boa junto")
        self.assertEqual(len(ruins), 1)
        self.assertIn("HAPV3", ruins[0][0])
        self.assertIn("pergunta", ruins[0][1])

    def test_lista_vazia_nao_levanta(self):
        ns = self._ns()
        self.assertEqual(ns["licoes_que_nao_ensinam"]([]), ([], []))
        self.assertEqual(ns["licoes_que_nao_ensinam"](None), ([], []))

    def test_a_pergunta_do_meio_e_separada_da_regra(self):
        """A frase dele de 16:03: a regra é o que vem DEPOIS da interrogação."""
        ns = self._ns()
        regra, fora = ns["separar_pergunta_da_regra"](
            "qual a probabilidade de matermos a meta de hoje?olha no plano de "
            "trading e o motor para responder essa pergunta")
        self.assertTrue(regra.startswith("olha no plano"), regra)
        self.assertIn("probabilidade", fora)

    def test_regra_sem_pergunta_passa_intacta(self):
        ns = self._ns()
        regra, fora = ns["separar_pergunta_da_regra"](
            "nunca opere contra o H4 depois das 15h")
        self.assertEqual(regra, "nunca opere contra o H4 depois das 15h")
        self.assertEqual(fora, "")

    def test_pergunta_pura_continua_sendo_pergunta_pura(self):
        """Não pode virar 'regra vazia': quem recusa é a trava de sempre."""
        ns = self._ns()
        regra, fora = ns["separar_pergunta_da_regra"](
            "o que aconteceu com HAPV3 HOJE?")
        self.assertEqual(fora, "")
        self.assertTrue(ns["_e_pergunta"](regra))

    def test_o_que_sobra_precisa_ser_uma_regra_de_verdade(self):
        """'...meta de hoje? sim' não deixa regra nenhuma para trás."""
        ns = self._ns()
        regra, fora = ns["separar_pergunta_da_regra"](
            "qual a meta de hoje? sim")
        self.assertEqual(fora, "")
        self.assertIn("meta de hoje", regra)

    def test_a_faxina_DIZ_o_que_apagou(self):
        """Memória mexida em silêncio é pior que memória suja."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _faxina_de_licoes")
        bloco = fonte[i:i + 1600]
        self.assertIn("Tirei", bloco)
        self.assertIn("é só me ensinar de novo", bloco)

    def test_a_faxina_roda_na_abertura(self):
        fonte = fonte_do_arquivo()
        self.assertIn("self._faxina_de_licoes()", fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
