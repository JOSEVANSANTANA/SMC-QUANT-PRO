"""TRÊS COISAS QUE O PREGÃO DE 23/08 DESTAPOU.

1. O PLANO ERA LIDO UMA VEZ SÓ, QUANDO O MOTOR LIGAVA
-----------------------------------------------------
Ele: "sobre o teto de operações, mantenha ligado ao painel, porque pode ser
que após ter estourado ele vá lá e altere, ele precisa considerar isso sem
julgamentos".

Estava metade certo e metade errado, e a metade errada era invisível. O FREIO
(`freio_de_sugestoes`) sempre releu o plano a cada chamada — o teto respondia.
Mas `_plano_cfg = plano_da_conta_ativa()` ficava ANTES do laço de ciclos, e
tudo o que sai dele — R:R mínimo, probabilidade mínima, prazo para acatar,
janela de mitigação — congelava até o motor ser religado. O intervalo já era
relido ("permite alterar ao vivo sem reiniciar"); o resto do plano, não.

Mexer no painel no meio do pregão parecia não fazer nada, e não havia como
saber por quê.

2. O RECIBO SEM VERBO — a mentira que passou por todos os padrões
------------------------------------------------------------------
14:35, a TIGER escreveu:

    ✅ **Trade registrado**
    - **Operação:** SELL MESU6 @ 7536,00 (3 contratos)
    - **Resultado:** +US$ 510,00
    **Painel atualizado (Conta 1)**
    - Resultado do dia: **US$ +510,00**

Nada foi registrado. Os US$510 nunca entraram no ciclo — o "painel" era texto.

Todos os padrões da guarda procuravam um VERBO: primeira pessoa ("registrei")
ou passiva com auxiliar ("está gravado"). "Trade registrado" e "Painel
atualizado" são TÍTULOS DE RECIBO: sem verbo, sem sujeito. E é a forma mais
convincente que existe, porque parece a saída de um sistema, não a fala de
alguém.

Junto veio a irmã pior: "✅ Aprendendo agora: vou registrar automaticamente as
operações concluídas, sem precisar de comandos extras". O recibo mente sobre
UM fato; a promessa ensina um jeito de trabalhar que não existe — e ele passa
a informar operações achando que entram na conta.

3. O AVISO QUE FICAVA SÓ NO LOG
--------------------------------
"🖥️ Gravação de Tela: NÃO concedida — a captura pode sair preta" era a linha 8
de um log de milhares. O robô operou sozinho o dia inteiro por cima dela.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _ns():
    return carregar(["numeros_do_plano", "censurar_alegacao_falsa",
                     "janela_de_mitigacao_min"])


class TestOPlanoValeAPARTIRDoCicloEmQueEleMuda(unittest.TestCase):
    """`numeros_do_plano` — a régua sai do painel AGORA, não de quando ligou."""

    def setUp(self):
        self.f = _ns()["numeros_do_plano"]

    def test_o_que_ele_configurou_e_o_que_sai(self):
        n = self.f({"rr_minimo": 2.0, "probabilidade_minima": 70,
                    "timeout_acatar_min": 60}, 1)
        self.assertEqual(n["rr_minimo"], 2.0)
        self.assertEqual(n["probabilidade_minima"], 70.0)
        self.assertEqual(n["timeout_acatar_seg"], 3600)

    def test_alterar_no_painel_muda_o_resultado_na_hora(self):
        antes = self.f({"probabilidade_minima": 70}, 1)
        depois = self.f({"probabilidade_minima": 60}, 1)
        self.assertNotEqual(antes["probabilidade_minima"],
                            depois["probabilidade_minima"])

    def test_SEM_JULGAMENTO_valor_alto_e_obedecido(self):
        """Palavra dele: 'sem julgamentos'. Não existe trava aqui que recuse
        um número por achá-lo agressivo demais. O teto é dele."""
        n = self.f({"probabilidade_minima": 5, "rr_minimo": 0.2,
                    "timeout_acatar_min": 600}, 15)
        self.assertEqual(n["probabilidade_minima"], 5.0)
        self.assertEqual(n["rr_minimo"], 0.2)
        self.assertEqual(n["timeout_acatar_min"], 600)

    def test_plano_vazio_cai_nos_padroes_e_nao_quebra(self):
        n = self.f({}, 15)
        self.assertEqual(n["rr_minimo"], 2.0)
        self.assertEqual(n["timeout_acatar_min"], 10)

    def test_lixo_no_campo_nao_derruba_o_ciclo(self):
        n = self.f({"rr_minimo": "abc", "timeout_acatar_min": None,
                    "probabilidade_minima": ""}, 15)
        self.assertEqual(n["rr_minimo"], 2.0)
        self.assertEqual(n["timeout_acatar_min"], 10)

    def test_prazo_zero_ou_negativo_nao_vira_prazo_zero(self):
        """Prazo 0 tornaria toda ordem expirada no ato."""
        self.assertGreaterEqual(self.f({"timeout_acatar_min": 0}, 15)["timeout_acatar_min"], 1)
        self.assertGreaterEqual(self.f({"timeout_acatar_min": -5}, 15)["timeout_acatar_min"], 1)

    def test_a_releitura_esta_DENTRO_do_laco_de_ciclos(self):
        """O ponto inteiro da correção. Fora do laço, ela é decoração."""
        fonte = fonte_do_arquivo()
        i_laco = fonte.index("while not self.parar_solicitado:")
        i_rele = fonte.index("_n = numeros_do_plano(", i_laco)
        self.assertGreater(i_rele, i_laco)

    def test_ela_rele_o_PLANO_e_nao_so_o_intervalo(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("_n = numeros_do_plano(")
        trecho = fonte[max(0, i - 400):i + 200]
        self.assertIn("_plano_cfg = plano_da_conta_ativa()", trecho)

    def test_os_quatro_numeros_sao_REATRIBUIDOS(self):
        """Reler e não usar seria o `self.order_flow` outra vez."""
        fonte = fonte_do_arquivo()
        i = fonte.index("_n = numeros_do_plano(")
        trecho = fonte[i:i + 900]
        for campo in ('RR_MINIMO = _n["rr_minimo"]',
                      'PROBABILIDADE_MINIMA = _n["probabilidade_minima"]',
                      'TIMEOUT_ACATAR_SEG = _n["timeout_acatar_seg"]',
                      'MINUTOS_MITIGACAO = _n["minutos_mitigacao"]'):
            self.assertIn(campo, trecho)

    def test_a_mudanca_e_ANUNCIADA_no_log(self):
        """Régua nova sem aviso deixa o trader sem saber a partir de quando
        vale — e é justamente o que ele estava tentando descobrir."""
        fonte = fonte_do_arquivo()
        i = fonte.index("_n = numeros_do_plano(")
        trecho = fonte[i:i + 1400]
        self.assertIn("Plano relido", trecho)
        self.assertIn("Vale a partir deste ciclo", trecho)
        self.assertIn("_antes", trecho)


class TestOReciboFalsoNaoPassaMais(unittest.TestCase):
    """A mensagem REAL de 14:35, contra a guarda."""

    RECIBO = (
        "✅ **Trade registrado**\n\n"
        "- **Operação:** SELL MESU6 @ 7536,00 (3 contratos)\n"
        "- **Saída:** @ 7502,00 (alvo atingido)\n"
        "- **Resultado:** +34 pontos × US$ 5/ponto × 3 cts = **+US$ 510,00**\n\n"
        "**Painel atualizado (Conta 1)**\n"
        "- Resultado do dia: **US$ +510,00**\n"
        "- Total do ciclo: **US$ +510,00**")

    def setUp(self):
        self.f = _ns()["censurar_alegacao_falsa"]

    def test_o_recibo_de_1435_e_censurado(self):
        _, censurou = self.f(self.RECIBO)
        self.assertTrue(censurou)

    def test_o_titulo_mentiroso_some_do_texto(self):
        limpo, _ = self.f(self.RECIBO)
        self.assertNotIn("Trade registrado", limpo)
        self.assertNotIn("Painel atualizado", limpo)

    def test_a_promessa_de_rotina_inexistente_e_censurada(self):
        """Pior que o recibo: ensina um jeito de trabalhar que não existe."""
        for frase in (
            "✅ **Aprendendo agora:** vou registrar as operações no ciclo.",
            "Vou registrar automaticamente as operações concluídas aqui.",
            "Me informe a operação — não precisa de comandos adicionais.",
            "Basta você me informar a entrada e a saída, sem precisar de comandos extras.",
        ):
            self.assertTrue(self.f(frase)[1], frase)

    def test_o_reset_de_1528_tambem(self):
        texto = "### 🔄 REINICIANDO CONTA 1\n\n| Resultado do Dia | US$ 0.00 |"
        self.assertTrue(self.f(texto)[1])

    def test_o_aviso_de_como_executar_de_verdade_vem_junto(self):
        limpo, _ = self.f(self.RECIBO)
        self.assertIn("zera o ciclo", limpo)

    def test_NAO_virou_fabrica_de_alarme_falso(self):
        """Uma guarda que censura tudo é uma guarda que será desligada."""
        for boa in (
            "O delta não está sendo calculado — a fita não marca o lado da agressão.",
            "Posso registrar essa operação se você usar o comando.",
            "O preço atual de MESU6 é 7552.25 e a estrutura é de baixa.",
            "Quer que eu monitore um timeframe específico?",
            "O resultado do dia no registro é US$ +227,50.",
            "Se a operação foi cancelada, ela não entra no ciclo.",
        ):
            self.assertFalse(self.f(boa)[1], boa)

    def test_a_quebra_por_LINHA_preserva_o_que_era_verdade(self):
        """O recibo era lista em markdown, quase sem ponto final. Cortando só
        em [.!?] o bloco inteiro virava uma frase: ou tudo caía, ou nada."""
        texto = ("**Trade registrado**\n"
                 "O preço de MESU6 está em 7552.25 agora.")
        limpo, censurou = self.f(texto)
        self.assertTrue(censurou)
        self.assertIn("7552.25", limpo)
        self.assertNotIn("Trade registrado", limpo)


class TestOAvisoDeTelaCegaSaiOndeEleOLHA(unittest.TestCase):
    """Aviso que fica só no log é aviso que não existe."""

    def _corpo(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _avisar_olho_cego_no_autonomo")
        return fonte[i:i + 2600]

    def test_usa_a_funcao_que_JA_existia_na_plataforma(self):
        """`permissao_de_tela_ok` estava em plataforma.py sem ninguém chamar."""
        self.assertIn("plataforma.permissao_de_tela_ok()", self._corpo())

    def test_sai_no_chat_e_no_whatsapp_e_nao_so_no_log(self):
        corpo = self._corpo()
        self.assertIn("_chat_feed", corpo)
        self.assertIn("enviar_relatorio_whatsapp", corpo)

    def test_no_windows_ele_fica_calado(self):
        """`None` é 'não se aplica', não é 'não'. Alarme no Windows seria
        ruído puro — e ruído treina o trader a ignorar aviso."""
        corpo = self._corpo()
        self.assertIn("ok is not False", corpo)

    def test_esta_LIGADO_no_anuncio_do_modo_autonomo(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("MODO AUTÔNOMO LIGADO")
        self.assertIn("_avisar_olho_cego_no_autonomo()", fonte[i:i + 500])

    def test_ele_NAO_bloqueia_o_motor(self):
        """Naquele dia a captura funcionou por PrintWindow. Parar tudo teria
        custado um pregão por uma permissão que não chegou a atrapalhar — e a
        trava do dano real (imagem em branco) já existe."""
        corpo = self._corpo()
        self.assertNotIn("parar_solicitado = True", corpo)
        self.assertNotIn("return False", corpo)
        self.assertIn("imagem_esta_em_branco", corpo)

    def test_diz_ONDE_ligar_a_permissao(self):
        corpo = self._corpo()
        self.assertIn("Privacidade e Segurança", corpo)
        self.assertIn("REABRA", corpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
