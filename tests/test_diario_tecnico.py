"""O QUE O MOTOR FEZ, EM FORMA DE DADO.

O PEDIDO (31/08): "quero te propor criar uma branch local para manter tudo
localmente e você acompanhar os logs automaticamente... assim você terá acesso
em tempo real a tudo que o motor fizer e ainda conseguirá gerar insights que
vou precisar posteriormente".

A PARTE QUE NÃO DÁ, dita de uma vez: o assistente roda num contêiner na nuvem
e não enxerga o disco do Mac dele. "Tempo real" não existe daqui, e uma branch
local continua local até alguém empurrar para o GitHub. Prometer o contrário
seria a mesma família de mentira que este projeto passou meses arrancando.

A PARTE QUE DÁ, e é quase tudo o que ele quer: o log de hoje é PROSA numa
caixa de texto. Prosa serve para ler no pregão e não serve para analisar
depois — "descartei o BUY MNQU6" é a MESMA frase saindo de três travas
diferentes (stop largo, entrada distante, anti-repetição), e foi exatamente
isso que produziu o mal-entendido de 31/08 sobre a anti-repetição cruzando
ativos. Aqui cada acontecimento vira UMA LINHA JSON, com hora, tipo, ativo e
os números que decidiram — agrupável por motivo, somável por ativo.

E há uma regra de segurança que este arquivo existe para trancar: o .zip
nasceu para VIAJAR (chat, e-mail, WhatsApp). Chave de API vazada num anexo é
vazamento igual — pior, é o vazamento que ninguém procura, porque "é só um
log".
"""

import datetime
import json
import os
import shutil
import tempfile
import unittest

from harness import carregar, fonte_do_arquivo, funcao_inteira


def _ns():
    return carregar(
        ["censurar_segredos", "_CHAVES_DE_SEGREDO", "linha_de_evento",
         "registrar_evento", "limpar_diario_tecnico",
         "caminho_do_diario_tecnico", "DIARIO_TECNICO_DIAS",
         "DIARIO_TECNICO_MAX_MB"],
        stubs={"pasta_dados_usuario": lambda: tempfile.gettempdir()})


class TestNenhumaChaveSAIDAQUI(unittest.TestCase):
    """A trava mais importante do arquivo."""

    def test_campo_de_credencial_vira_asteriscos(self):
        ns = _ns()
        limpo = ns["censurar_segredos"]({
            "ativo": "MESU6", "api_key": "sk-abc123",
            "gemini_chave": "AIza-secreta", "senha": "1234",
            "TOKEN": "t-999", "Authorization": "Bearer x"})
        self.assertEqual(limpo["ativo"], "MESU6")
        for campo in ("api_key", "gemini_chave", "senha", "TOKEN",
                      "Authorization"):
            self.assertEqual(limpo[campo], "***", f"{campo} vazou")

    def test_censura_ENTRA_em_dicionario_aninhado(self):
        """Plano de trading e configuração vêm em árvore. Censurar só o nível
        de cima deixaria a chave um andar abaixo — que é onde ela mora."""
        ns = _ns()
        limpo = ns["censurar_segredos"](
            {"provedores": {"gemini": {"api_key": "sk-1", "modelo": "flash"}},
             "lista": [{"token": "t"}, {"ok": 1}]})
        self.assertEqual(limpo["provedores"]["gemini"]["api_key"], "***")
        self.assertEqual(limpo["provedores"]["gemini"]["modelo"], "flash")
        self.assertEqual(limpo["lista"][0]["token"], "***")
        self.assertEqual(limpo["lista"][1]["ok"], 1)

    def test_ciclo_ou_arvore_funda_nao_trava_o_programa(self):
        ns = _ns()
        d = {"a": 1}
        d["eu"] = d                       # referência circular
        self.assertIsInstance(ns["censurar_segredos"](d), dict)

    def test_a_censura_roda_ANTES_de_escrever_a_linha(self):
        ns = _ns()
        linha = ns["linha_de_evento"]("teste", api_key="sk-nao-pode-sair")
        self.assertNotIn("sk-nao-pode-sair", linha)
        self.assertIn("***", linha)

    def test_o_export_censura_o_plano(self):
        corpo = funcao_inteira(fonte_do_arquivo(), "_exportar_diario_tecnico")
        self.assertIn("censurar_segredos(plano_da_conta_ativa()", corpo)


class TestUmaLinhaPorAcontecimento(unittest.TestCase):

    def test_a_linha_e_JSON_valido_com_hora_e_tipo(self):
        ns = _ns()
        quando = datetime.datetime(2026, 9, 3, 14, 30, 5)
        d = json.loads(ns["linha_de_evento"](
            "ordem_enviada", agora=quando, ativo="MESU6", contratos=3))
        self.assertEqual(d["tipo"], "ordem_enviada")
        self.assertEqual(d["ts"], "2026-09-03T14:30:05")
        self.assertEqual(d["ativo"], "MESU6")
        self.assertEqual(d["contratos"], 3)

    def test_NUNCA_sai_linha_quebrada(self):
        """Um JSONL com uma linha inválida no meio é um arquivo que ninguém lê
        até o fim — e o valor dele todo está em ser lido até o fim."""
        ns = _ns()
        class Esquisito:
            def __repr__(self):
                return "<obj>"
        for campos in ({"objeto": Esquisito()},
                       {"excecao": ValueError("x")},
                       {"conjunto": {1, 2, 3}},
                       {"data": datetime.datetime.now()}):
            linha = ns["linha_de_evento"]("t", **campos)
            self.assertIsInstance(json.loads(linha), dict)
            self.assertNotIn("\n", linha)

    def test_a_linha_nao_tem_quebra_no_meio(self):
        ns = _ns()
        linha = ns["linha_de_evento"]("t", motivo="primeira\nsegunda")
        self.assertNotIn("\n", linha)


class TestOArquivoDoDia(unittest.TestCase):

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="diario-tecnico-")
        self.addCleanup(shutil.rmtree, self.pasta, True)

    def test_um_arquivo_por_pregao_com_a_data_no_nome(self):
        ns = _ns()
        caminho = ns["caminho_do_diario_tecnico"](
            datetime.date(2026, 9, 3), self.pasta)
        self.assertTrue(caminho.endswith("motor-2026-09-03.jsonl"))

    def test_grava_e_da_para_reler_linha_a_linha(self):
        ns = _ns()
        quando = datetime.datetime(2026, 9, 3, 10, 0, 0)
        for i in range(3):
            self.assertTrue(ns["registrar_evento"](
                "ordem_enviada", pasta=self.pasta, agora=quando,
                ativo="MESU6", contratos=i))
        caminho = ns["caminho_do_diario_tecnico"](quando, self.pasta)
        with open(caminho, encoding="utf-8") as fh:
            linhas = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual([d["contratos"] for d in linhas], [0, 1, 2])

    def test_pasta_impossivel_NAO_derruba_o_envio(self):
        """Esta função é chamada de dentro do caminho que manda ordem.
        Registrar é importante; operar é mais."""
        ns = _ns()
        impossivel = os.path.join(self.pasta, "arquivo-nao-pasta")
        with open(impossivel, "w") as fh:
            fh.write("x")
        self.assertFalse(ns["registrar_evento"]("t", pasta=impossivel))

    def test_arquivo_velho_e_apagado_e_o_de_hoje_fica(self):
        ns = _ns()
        hoje = datetime.date(2026, 9, 3)
        for dia in (hoje, hoje - datetime.timedelta(days=40)):
            with open(ns["caminho_do_diario_tecnico"](dia, self.pasta),
                      "w", encoding="utf-8") as fh:
                fh.write("{}\n")
        with open(os.path.join(self.pasta, "outra-coisa.txt"), "w") as fh:
            fh.write("nao e meu")
        self.assertEqual(ns["limpar_diario_tecnico"](self.pasta, 30, hoje), 1)
        restou = sorted(os.listdir(self.pasta))
        self.assertIn("motor-2026-09-03.jsonl", restou)
        self.assertIn("outra-coisa.txt", restou,
                      "só apago os arquivos que eu mesma escrevi")

    def test_nome_estranho_nao_derruba_a_limpeza(self):
        ns = _ns()
        for nome in ("motor-nao-e-data.jsonl", "motor-.jsonl"):
            with open(os.path.join(self.pasta, nome), "w") as fh:
                fh.write("x")
        self.assertEqual(
            ns["limpar_diario_tecnico"](self.pasta, 30,
                                        datetime.date(2026, 9, 3)), 0)

    def test_pasta_inexistente_devolve_zero(self):
        ns = _ns()
        self.assertEqual(
            ns["limpar_diario_tecnico"](os.path.join(self.pasta, "nao-existe")),
            0)


class TestOsEventosQueDecidemDINHEIROEstaoGravados(unittest.TestCase):
    """Diário técnico que não registra a recusa é diário que só conta a
    metade boa da história — e a metade que ele precisa entender depois do
    pregão é justamente a outra."""

    def test_a_ordem_enviada(self):
        corpo = funcao_inteira(fonte_do_arquivo(), "_tv_enviar_bracket")
        self.assertIn('registrar_evento(\n                    "ordem_enviada"',
                      corpo)

    def test_a_recusa_por_exposicao_na_plataforma(self):
        corpo = funcao_inteira(fonte_do_arquivo(), "_tv_enviar_bracket")
        self.assertIn('"ordem_recusada_pela_plataforma"', corpo)

    def test_o_cenario_que_o_plano_nao_dimensionou(self):
        self.assertIn('"cenario_sem_tamanho"', fonte_do_arquivo())

    def test_o_cancelamento_COM_o_colateral(self):
        """Sem o colateral gravado, "cancelei o MGCV6" continua sendo uma
        frase sem prova — e foi essa frase, sem prova, que escondeu por um dia
        inteiro o cancelamento que varria o desk."""
        corpo = funcao_inteira(fonte_do_arquivo(), "_tv_cancelar_na_plataforma")
        self.assertIn('"cancelamento"', corpo)
        self.assertIn("colateral=", corpo)
        self.assertIn("alvo_antes=", corpo)

    def test_res_existe_em_TODOS_os_ramos_do_cancelamento(self):
        """O registro lê `res` no fim. Sem inicializar, o ramo 'sem conexão'
        estouraria NameError — e o único jeito de descobrir seria perdendo o
        registro justamente do dia em que o Chrome caiu."""
        corpo = funcao_inteira(fonte_do_arquivo(), "_tv_cancelar_na_plataforma")
        i_init = corpo.index("res = None")
        i_uso = corpo.index('registrar_evento(\n                "cancelamento"')
        self.assertLess(i_init, i_uso)


class TestOBotaoDeExportar(unittest.TestCase):

    def test_ele_ESTA_na_barra_do_log(self):
        """Função que existe e não tem botão é função que ninguém usa."""
        fonte = fonte_do_arquivo()
        self.assertIn("Exportar diário técnico", fonte)
        self.assertIn("command=self._exportar_diario_tecnico", fonte)

    def test_sem_nada_gravado_ele_EXPLICA_em_vez_de_falhar(self):
        corpo = funcao_inteira(fonte_do_arquivo(), "_exportar_diario_tecnico")
        self.assertIn("Ainda não há nada gravado", corpo)

    def test_ele_limpa_o_que_esta_velho_antes_de_empacotar(self):
        corpo = funcao_inteira(fonte_do_arquivo(), "_exportar_diario_tecnico")
        i_limpa = corpo.index("limpar_diario_tecnico()")
        i_zip = corpo.index("zipfile.ZipFile(")
        self.assertLess(i_limpa, i_zip)

    def test_o_zip_leva_a_versao_junto(self):
        """Um log sem a versão que o produziu é um log que não dá para
        comparar com o código de nenhum dia específico."""
        corpo = funcao_inteira(fonte_do_arquivo(), "_exportar_diario_tecnico")
        self.assertIn("VERSAO_ATUAL", corpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
