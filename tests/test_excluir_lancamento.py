"""EXCLUIR A OPERAÇÃO QUE FOI REGISTRADA INDEVIDAMENTE.

O PEDIDO
--------
"inclua também a opção de excluir ordens lançadas / entradas lançadas
indevidamente no relatório de incluir e registrar sugestões no plano de
trading (notei que tem algumas que estão registrando erroneamente ou em
duplicidade com o extrato da corretora quando importo)".

POR QUE O AUTOMÁTICO NÃO BASTAVA
---------------------------------
Já existia a substituição pelo extrato (`posicoes_substituidas_pelo_extrato`):
importou o PDF, tudo que estava no diário DENTRO da janela que o documento
comprovadamente cobre é marcado como SUBSTITUIDA e sai da conta. É a regra
certa, e ela é deliberadamente conservadora — só mexe no que dá para PROVAR.

Sobra tudo que não dá: carimbo de hora ilegível, ativo grafado diferente,
operação que fechou depois da hora em que ele gerou o PDF. Nesses casos ficava
uma linha duplicada contando dinheiro duas vezes, e não havia mão nenhuma para
tirá-la — só editando o JSON.

Automatismo sem correção manual embaixo obriga a escolher entre apagar demais
e conviver com o erro. Aqui a decisão volta a ser dele.

AS DUAS REGRAS QUE ESTES TESTES SEGURAM
----------------------------------------
1. EXCLUIR NÃO APAGA. O status vira EXCLUIDA e a linha some de todo somatório
   (que filtra por FECHADA), mas o registro continua no disco e dá para
   restaurar. Linha apagada não se audita — e isto é dinheiro registrado.

2. A BUSCA DE DUPLICATAS NÃO PODE CASAR OPERAÇÃO LEGÍTIMA. Numa mesa que
   repete o mesmo setup, duas vendas de 11 contratos do MESU6 na mesma hora
   são NORMAIS. Só vira par quando uma das duas vem do EXTRATO e a outra não —
   e o par sai sempre com a do extrato na frente, porque a palavra dele foi
   "o que sempre tem mais validade são os importados".
"""

import datetime
import os
import sys
import unittest

from harness import RAIZ, carregar, funcao_inteira

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def _fonte(nome="main_app.py"):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


NS = carregar([
    "excluir_lancamento",
    "restaurar_lancamento",
    "possiveis_duplicatas",
    "_instante_da_posicao",
    "_parse_dt",
    "_conta_do_registro",
    "STATUS_EXCLUIDA",
    "ORIGEM_EXTRATO",
    "ID_CONTA_LEGADA",
], stubs={"datetime": datetime})

excluir = NS["excluir_lancamento"]
restaurar = NS["restaurar_lancamento"]
duplicatas = NS["possiveis_duplicatas"]
EXCLUIDA = NS["STATUS_EXCLUIDA"]
EXTRATO = NS["ORIGEM_EXTRATO"]


def _op(id_, ativo="MESU6", direcao="SELL", ctr=11, origem="ROBO",
        fecha="31/08/2026 11:56", pnl=-382.5, conta="conta-1", status="FECHADA"):
    return {"id": id_, "ativo": ativo, "direcao": direcao, "contratos": ctr,
            "origem": origem, "data_fechamento": fecha, "pnl_final": pnl,
            "conta_id": conta, "status": status, "entry": 7685.0}


class ExcluirTiraDaContaSemApagar(unittest.TestCase):

    def test_a_operacao_sai_do_status_FECHADA(self):
        """É o que a remove de dashboard, drawdown e taxa de acerto de uma vez:
        todo somatório do programa filtra por FECHADA."""
        lista, saiu = excluir([_op("a")], "a", agora="31/08 12:00")
        self.assertEqual(saiu["status"], EXCLUIDA)
        self.assertNotEqual(lista[0]["status"], "FECHADA")

    def test_o_registro_CONTINUA_lá(self):
        lista, _ = excluir([_op("a")], "a", agora="31/08 12:00")
        self.assertEqual(len(lista), 1)
        self.assertEqual(lista[0]["pnl_final"], -382.5)
        self.assertEqual(lista[0]["entry"], 7685.0)

    def test_guarda_o_status_ANTERIOR_para_poder_voltar(self):
        lista, _ = excluir([_op("a")], "a", agora="31/08 12:00")
        self.assertEqual(lista[0]["status_antes_da_exclusao"], "FECHADA")

    def test_grava_QUANDO_e_POR_QUE(self):
        """Exclusão sem rastro é indistinguível de registro que sumiu sozinho."""
        lista, _ = excluir([_op("a")], "a", motivo="duplicada com o extrato",
                           agora="31/08 12:00")
        self.assertEqual(lista[0]["excluida_em"], "31/08 12:00")
        self.assertIn("duplicada", lista[0]["motivo_exclusao"])

    def test_excluir_duas_vezes_nao_estraga_o_status_guardado(self):
        """Sem esta guarda, o segundo clique gravaria 'status anterior =
        EXCLUIDA' e restaurar devolveria a linha para o limbo."""
        lista, _ = excluir([_op("a")], "a", agora="31/08 12:00")
        lista2, saiu2 = excluir(lista, "a", agora="31/08 12:05")
        self.assertIsNone(saiu2)
        self.assertEqual(lista2[0]["status_antes_da_exclusao"], "FECHADA")

    def test_id_que_nao_existe_nao_mexe_em_nada(self):
        lista, saiu = excluir([_op("a")], "zzz")
        self.assertIsNone(saiu)
        self.assertEqual(lista[0]["status"], "FECHADA")

    def test_so_mexe_na_operacao_pedida(self):
        lista, _ = excluir([_op("a"), _op("b")], "a", agora="x")
        self.assertEqual(lista[1]["status"], "FECHADA")


class RestaurarDesfaz(unittest.TestCase):

    def test_volta_ao_status_que_tinha(self):
        lista, _ = excluir([_op("a")], "a", agora="x")
        lista, volta = restaurar(lista, "a")
        self.assertEqual(volta["status"], "FECHADA")
        self.assertEqual(lista[0]["status"], "FECHADA")

    def test_limpa_as_marcas_da_exclusao(self):
        lista, _ = excluir([_op("a")], "a", motivo="engano", agora="x")
        lista, _ = restaurar(lista, "a")
        self.assertNotIn("excluida_em", lista[0])
        self.assertNotIn("motivo_exclusao", lista[0])
        self.assertNotIn("status_antes_da_exclusao", lista[0])

    def test_nao_mexe_em_quem_nao_foi_excluida(self):
        lista, volta = restaurar([_op("a")], "a")
        self.assertIsNone(volta)
        self.assertEqual(lista[0]["status"], "FECHADA")


class ACacaDeDuplicatasNaoCASAOperacaoLegITIMA(unittest.TestCase):

    def test_acha_o_par_robo_mais_extrato(self):
        """O caso dele: a linha que o robô gravou ao mandar a ordem e a mesma
        operação impressa pela corretora."""
        pares = duplicatas([_op("robo", origem="ROBO"),
                            _op("pdf", origem=EXTRATO,
                                fecha="31/08/2026 11:57")],
                           conta_id="conta-1")
        self.assertEqual(len(pares), 1)

    def test_o_registro_do_EXTRATO_vem_primeiro_no_par(self):
        """'o que sempre tem mais validade são os importados' — quem vai
        apagar precisa ver, na ordem, qual é o bom."""
        for ordem in ([_op("robo"), _op("pdf", origem=EXTRATO)],
                      [_op("pdf", origem=EXTRATO), _op("robo")]):
            pares = duplicatas(ordem, conta_id="conta-1")
            self.assertEqual(pares[0][0]["origem"], EXTRATO)
            self.assertEqual(pares[0][1]["origem"], "ROBO")

    def test_DUAS_do_robo_no_mesmo_setup_NAO_sao_duplicata(self):
        """Ele repete o mesmo cenário o dia inteiro — o log mostra quatro
        SELL MESU6 de 11 contratos @ 7709.5 numa manhã. Chamar isso de
        duplicata apagaria operação de verdade."""
        pares = duplicatas([_op("a", origem="ROBO"), _op("b", origem="ROBO")],
                           conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_duas_do_EXTRATO_tambem_nao(self):
        pares = duplicatas([_op("a", origem=EXTRATO), _op("b", origem=EXTRATO)],
                           conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_ativos_diferentes_nao_casam(self):
        pares = duplicatas([_op("a", ativo="MESU6"),
                            _op("b", ativo="MGCV6", origem=EXTRATO)],
                           conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_MES_casa_com_MESU6_pela_RAIZ(self):
        """A corretora e o robô nem sempre grafam o vencimento igual."""
        pares = duplicatas([_op("a", ativo="MES"),
                            _op("b", ativo="MESU6", origem=EXTRATO)],
                           conta_id="conta-1")
        self.assertEqual(len(pares), 1)

    def test_MES_nao_casa_com_MNQ(self):
        pares = duplicatas([_op("a", ativo="MESU6"),
                            _op("b", ativo="MNQU6", origem=EXTRATO)],
                           conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_direcoes_opostas_nao_casam(self):
        pares = duplicatas([_op("a", direcao="BUY"),
                            _op("b", direcao="SELL", origem=EXTRATO)],
                           conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_quantidades_diferentes_nao_casam(self):
        pares = duplicatas([_op("a", ctr=11),
                            _op("b", ctr=14, origem=EXTRATO)],
                           conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_longe_no_tempo_nao_casa(self):
        pares = duplicatas([_op("a", fecha="31/08/2026 09:10"),
                            _op("b", fecha="31/08/2026 16:41", origem=EXTRATO)],
                           conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_contas_diferentes_nao_se_misturam(self):
        pares = duplicatas([_op("a", conta="conta-1"),
                            _op("b", conta="conta-2", origem=EXTRATO)],
                           conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_sem_carimbo_de_hora_legivel_nao_casa(self):
        """Sem poder provar proximidade no tempo, o casamento vira chute sobre
        dinheiro registrado."""
        pares = duplicatas([_op("a", fecha="sem data"),
                            _op("b", fecha="também não", origem=EXTRATO)],
                           conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_operacao_ABERTA_nao_entra(self):
        pares = duplicatas([_op("a", status="ABERTA"),
                            _op("b", origem=EXTRATO)], conta_id="conta-1")
        self.assertEqual(pares, [])

    def test_ja_EXCLUIDA_nao_volta_a_ser_apontada(self):
        lista, _ = excluir([_op("robo"), _op("pdf", origem=EXTRATO)],
                           "robo", agora="x")
        self.assertEqual(duplicatas(lista, conta_id="conta-1"), [])

    def test_cada_registro_entra_em_no_maximo_UM_par(self):
        """Três linhas do mesmo setup não podem virar três pares cruzados —
        seria oferecer para excluir mais do que existe de sobra."""
        pares = duplicatas([_op("a", origem="ROBO"),
                            _op("b", origem="ROBO"),
                            _op("c", origem=EXTRATO)], conta_id="conta-1")
        ids = [p["id"] for par in pares for p in par]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(pares), 1)

    def test_registro_antigo_SEM_conta_id_conta_como_conta_legada(self):
        """Comparar `p['conta_id']` cru faria a duplicata do histórico dele
        passar despercebida justamente na conta 1."""
        legada = NS["ID_CONTA_LEGADA"]
        a, b = _op("a"), _op("b", origem=EXTRATO)
        a.pop("conta_id"), b.pop("conta_id")
        self.assertEqual(len(duplicatas([a, b], conta_id=legada)), 1)


class RegrasDaTela(unittest.TestCase):

    def test_o_painel_de_exclusao_existe_e_lista_as_FECHADAS(self):
        corpo = funcao_inteira(_fonte(), "_renderizar_lancamentos")
        self.assertIn("FECHADA", corpo)
        self.assertIn("possiveis_duplicatas", corpo)

    def test_o_botao_de_excluir_PERGUNTA_antes(self):
        """Este painel se redesenha sozinho junto do dashboard. Sem a pergunta,
        um clique errado tira dinheiro do relatório do dia sem aviso."""
        corpo = funcao_inteira(_fonte(), "_excluir_lancamento_click")
        self.assertIn("askyesno", corpo)

    def test_a_pergunta_MOSTRA_o_resultado_que_vai_sair_da_conta(self):
        corpo = funcao_inteira(_fonte(), "_excluir_lancamento_click")
        self.assertIn("pnl", corpo)
        self.assertIn("Resultado", corpo)

    def test_a_tela_oferece_RESTAURAR(self):
        corpo = funcao_inteira(_fonte(), "_renderizar_lancamentos")
        self.assertIn("_restaurar_lancamento_click", corpo)

    def test_o_painel_e_redesenhado_so_quando_muda(self):
        """Ele nasce dentro do dashboard, que roda a cada poucos segundos —
        destruir e recriar dezenas de widgets nessa cadência é o que já
        deixou a lista de posições pesada uma vez."""
        corpo = funcao_inteira(_fonte(), "_renderizar_lancamentos")
        self.assertIn("_assin_lancamentos", corpo)

    def test_o_dashboard_chama_o_painel(self):
        self.assertIn("self._renderizar_lancamentos()", _fonte())


if __name__ == "__main__":
    unittest.main(verbosity=2)
