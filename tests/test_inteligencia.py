"""Por que a TIGER parecia burra — e o que mudou.

O log de 12/08 tem a acusação inteira em quatro linhas:

    10:23 ❯ satatus
    10:23 ✳ "Não tenho como responder isso com segurança agora..."
    11:32 ❯ sim                    (respondendo à pergunta QUE ELA fez)
    11:32 ✳ [o mesmo parágrafo]
    11:35 ❯ o que deu errado na sugestão que você me passou
    11:35 ✳ [o mesmo parágrafo]
    11:36 ❯ era para você saber responder... você não é uma IA?
    11:36 ✳ [o mesmo parágrafo]

Duas causas distintas, tratadas aqui:
  1. ARQUITETURA — ela era Gemini-e-mais-nada. Estourada a cota do plano
     gratuito (o que acontece todo dia com o motor rodando de 5 em 5 minutos),
     não sobrava NINGUÉM para pensar.
  2. UMA LETRA — "satatus" e "tria um print" morriam num roteador que só
     conhece a grafia exata, e a resposta ao erro de digitação era a MESMA
     resposta de quando ela realmente não sabe.
"""

import unittest

from harness import carregar, fonte_do_arquivo


def _ns():
    return carregar(
        ["PROVEDORES_IA", "ORDEM_PROVEDORES", "_pedir_openai", "_pedir_anthropic",
         "responder_por_provedor_alternativo", "carregar_chave_provedor",
         "ia_local_no_ar", "provedores_configurados"],
        stubs={"carregar_config": lambda: {},
               "carregar_api_key": lambda: "",
               "dpapi_decrypt": lambda x: x,
               "requests": __import__("requests")})


class TestSegundaInteligencia(unittest.TestCase):
    def test_sem_chave_alternativa_ela_diz_isso_claramente(self):
        """Não é para fingir que tentou. Sem chave, o motivo é esse."""
        ns = _ns()
        texto, motivo = ns["responder_por_provedor_alternativo"](
            [{"role": "user", "content": "oi"}])
        self.assertIsNone(texto)
        self.assertIn("nenhum provedor alternativo", motivo)

    def test_a_fila_cobre_os_provedores_que_ele_pode_ter(self):
        ns = _ns()
        for pid in ("openai", "anthropic", "openrouter", "groq"):
            self.assertIn(pid, ns["ORDEM_PROVEDORES"], pid)
            self.assertIn(pid, ns["PROVEDORES_IA"], pid)

    def test_todo_provedor_tem_url_modelo_e_onde_pegar_a_chave(self):
        """Sem o link, o trader não sabe onde conseguir a chave — e a função
        vira decoração."""
        ns = _ns()
        for pid in ns["ORDEM_PROVEDORES"]:
            info = ns["PROVEDORES_IA"][pid]
            self.assertTrue(info.get("url"), pid)
            self.assertTrue(info.get("modelos"), pid)
            self.assertTrue(info.get("onde_pegar", "").startswith("http"), pid)

    def test_um_provedor_caido_nao_derruba_o_chat(self):
        """Cada falha é anotada e a fila continua. Se explodir, o trader fica
        sem resposta nenhuma — pior que a desculpa."""
        ns = _ns()
        ns["carregar_chave_provedor"] = lambda p: "chave-falsa"
        # Sem rede neste ambiente: todas falham. O contrato é devolver
        # (None, motivo), nunca levantar.
        try:
            texto, motivo = ns["responder_por_provedor_alternativo"](
                [{"role": "user", "content": "oi"}])
        except Exception as e:
            self.fail(f"levantou exceção em vez de devolver motivo: {e}")
        self.assertIsNone(texto)
        self.assertTrue(motivo)

    def test_o_formato_openai_serve_para_os_compativeis(self):
        """Groq, OpenRouter, DeepSeek e afins falam o mesmo protocolo — uma
        implementação só. Só a Anthropic tem formato próprio."""
        ns = _ns()
        formatos = {p: ns["PROVEDORES_IA"][p]["formato"]
                    for p in ns["ORDEM_PROVEDORES"]}
        self.assertEqual(formatos["anthropic"], "anthropic")
        for p in ("openai", "openrouter", "groq"):
            self.assertEqual(formatos[p], "openai", p)

    def test_a_regra_anti_invencao_vai_junto_no_prompt(self):
        """Trocar de provedor NÃO pode afrouxar a regra da casa."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _mensagens_para_provedor")
        corpo = fonte[i:i + 3000]
        self.assertIn("NUNCA invente número", corpo)
        self.assertIn("Ausência de dado não é conclusão", corpo)

    def test_o_alternativo_e_tentado_ANTES_do_despejo_generico(self):
        """A ordem certa tem TRÊS degraus, e cada um existe por um motivo:

            1. a BASE, quando há verbete para a pergunta
            2. o provedor alternativo (inclusive a IA local)
            3. o despejo genérico de "não tenho como responder"

        O degrau 1 nasceu do teste real de 12/08: com a IA local instalada, o
        último da fila nunca falha, então o degrau 3 deixou de ser alcançado —
        e junto com ele a base. "O QUE É SMC?" foi parar num modelo de 7B, que
        respondeu que E-mini de índice é forex. Verbete curado ganha de
        geração plausível.

        O degrau 3 continua vindo por último: se o despejo viesse antes, a
        segunda IA nunca seria usada — que era o defeito da 2.23."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _chat_worker")
        corpo = fonte[i:i + 20000]
        i_base = corpo.index("da_base = responder_offline(")
        # O PRIORITÁRIO (OpenRouter) roda ANTES da Gemini e, portanto, antes
        # da base no texto do arquivo. Ele não fura o degrau 1 por outro
        # caminho: é guardado por `buscar_base_smc`, testado logo abaixo.
        i_alt = corpo.index("responder_por_provedor_alternativo",
                            corpo.index("if not resposta and not anexo:"))
        i_generico = corpo.index("local = responder_offline(")
        self.assertLess(i_base, i_alt,
                        "com a IA local sempre de pé, a base nunca seria "
                        "alcançada se viesse depois dela")
        self.assertLess(i_alt, i_generico,
                        "se o despejo vier primeiro, a segunda IA nunca é usada")

    def test_o_prioritario_NAO_atropela_a_base(self):
        """O OpenRouter subiu para antes da Gemini — e o único jeito de isso
        ser seguro é ele não alcançar a pergunta que a base sabe responder.

        Sem esta guarda, "O QUE É SMC?" voltaria a ser respondido por um
        modelo generalista em vez do verbete escrito e revisado — que é
        exatamente o erro de 12/08 ("E-mini de índice é forex"), só que por
        uma porta nova."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _chat_worker")
        corpo = fonte[i:i + 20000]
        i_prio = corpo.index("PROVEDORES_PRIORITARIOS")
        trecho = corpo[i_prio - 400:i_prio + 400]
        self.assertIn("buscar_base_smc(pergunta)", trecho,
                      "a chamada prioritária tem de ser guardada pela base")

    def test_a_base_so_ganha_QUANDO_TEM_VERBETE(self):
        """A base não pode sequestrar toda pergunta: sem verbete, quem responde
        é o modelo. Por isso o degrau 1 é guardado por buscar_base_smc."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _chat_worker")
        corpo = fonte[i:i + 14000]
        i_guarda = corpo.index("if buscar_base_smc(pergunta):")
        i_base = corpo.index("da_base = responder_offline(")
        self.assertLess(i_guarda, i_base)

    def test_dinheiro_continua_fora_do_modelo(self):
        """A camada de provedores é só CONVERSA. Dimensionamento e piso de
        qualidade continuam determinísticos — trocar de modelo não pode mudar
        quantos contratos entram."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def responder_por_provedor_alternativo")
        corpo = fonte[i:i + 2000]
        for proibido in ("calcular_contratos", "dimensionar_pelo_plano",
                         "abrir_posicao", "registrar_novo_sinal_log"):
            self.assertNotIn(proibido, corpo, proibido)


class TestErroDeDigitacao(unittest.TestCase):
    def _ns(self):
        return carregar(["_COMANDOS_CONHECIDOS", "_distancia_edicao",
                         "corrigir_digitacao"])

    def test_as_duas_frases_do_log(self):
        ns = self._ns()
        self.assertEqual(ns["corrigir_digitacao"]("satatus")[0], "status")
        self.assertIn("tira", ns["corrigir_digitacao"]("tria um print")[0])

    def test_transposicao_conta_como_UM_erro(self):
        """'stauts' por 'status' é o erro mais comum que existe (dedo trocando
        a ordem). No Levenshtein puro custa 2 e ficaria de fora."""
        ns = self._ns()
        self.assertEqual(ns["_distancia_edicao"]("stauts", "status", 1), 1)
        self.assertEqual(ns["corrigir_digitacao"]("stauts")[0], "status")

    def test_palavra_curta_nunca_e_corrigida(self):
        """'sim' e 'nao' são palavras inteiras. Corrigi-las trocaria a intenção
        do trader em vez de consertar um deslize."""
        ns = self._ns()
        for p in ("sim", "nao", "não", "tp", "ok"):
            self.assertEqual(ns["corrigir_digitacao"](p), (p, False), p)

    def test_palavra_distante_nao_e_forcada_a_virar_comando(self):
        ns = self._ns()
        for frase in ("ibovespa", "petroleo", "obrigado", "mercado"):
            self.assertFalse(ns["corrigir_digitacao"](frase)[1], frase)

    def test_frase_certa_passa_intacta(self):
        ns = self._ns()
        frase = "porque o ibovespa cai hoje?"
        self.assertEqual(ns["corrigir_digitacao"](frase), (frase, False))


class TestMemoriaQueSePodeCorrigir(unittest.TestCase):
    """12/08, 14:16 — ela gravou "A PORRA DO VWAP ESTA EM 7769,78" como REGRA
    PERMANENTE. Um minuto depois a VWAP já era outra, e aquele número ficaria
    na memória para sempre. Às 14:16 ele escreveu "REMOVA ISSO" e às 14:17 ela
    respondeu repetindo a lição."""

    def _ns(self):
        return carregar(
            ["_sem_acento", "_norm_busca", "_LICAO_IMPOSSIVEL",
             "_RE_FATO_EFEMERO", "_e_pergunta", "_e_fato_efemero", "licao_pede_invencao",
             "_RE_ESQUECER", "pedido_de_esquecer"],
            stubs={"unicodedata": __import__("unicodedata")})

    def test_um_preco_nao_vira_regra_permanente(self):
        ns = self._ns()
        impossivel, porque = ns["licao_pede_invencao"](
            "MAS A PORRA DO VWAP ESTA EM 7769,78. ERA PARA VOCE SABER ISSO")
        self.assertTrue(impossivel)
        self.assertIn("NÚMERO DE AGORA", porque)

    def test_outros_niveis_de_agora_tambem_sao_recusados(self):
        ns = self._ns()
        for t in ("o preço está em 7753.25", "o stop foi 7748.25",
                  "o topo ficou em 7792", "a mínima do dia foi 7738.25"):
            self.assertTrue(ns["licao_pede_invencao"](t)[0], t)

    def test_regra_de_verdade_com_numero_continua_passando(self):
        """Percentual, horário e R:R têm número e SÃO regras. Se estas fossem
        recusadas, o trader perderia a capacidade de ensinar gestão."""
        ns = self._ns()
        for t in ("nunca arrisque mais de 2% por operação",
                  "não opere depois das 15h",
                  "exija R:R de 1:2 sempre",
                  "aprenda a identificar indicadores no gráfico"):
            self.assertFalse(ns["licao_pede_invencao"](t)[0], t)

    def test_da_para_apagar_uma_licao(self):
        ns = self._ns()
        self.assertEqual(ns["pedido_de_esquecer"]("REMOVA ISSO"), (True, ""))
        self.assertEqual(ns["pedido_de_esquecer"]("apaga a 2"), (True, "2"))
        self.assertEqual(ns["pedido_de_esquecer"]("apaga a lição 3"), (True, "3"))
        self.assertEqual(
            ns["pedido_de_esquecer"]("apaga a que fala de vwap"), (True, "vwap"))

    def test_ensinar_continua_sendo_ensinar(self):
        """'aprenda isso' não pode virar ordem de apagar."""
        ns = self._ns()
        for t in ("aprenda isso", "nunca opere contra o H4, aprenda isso"):
            self.assertFalse(ns["pedido_de_esquecer"](t)[0], t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
