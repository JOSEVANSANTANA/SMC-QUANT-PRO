"""A MESA TEM MAIS DE UM ATIVO — E ELA SÓ SABIA FALAR DE UM.

O QUE ELE VIU, NO LOG DELE, EM DUAS HORAS
------------------------------------------
31/08, 10:34:
    ❯ esta analisando mesu6 e mgcv6?
    ✳ Foco principal: MGCV6 ... MESU6: Não está no foco do gráfico no momento.

31/08, 11:41 (com posição SELL MESU6 de 17 contratos aberta):
    ❯ qual tempo grafico voce esta analisando no MESU6?
    ✳ Estou analisando o gráfico do MGCV6 ... configurado no tempo de 5 minutos.

As duas respostas estavam erradas, e nenhuma das duas era invenção do modelo:
o programa guardava UMA leitura só, em `_ultima_analise`, e cada janela do
ciclo sobrescrevia a da janela anterior. Quem falava era sempre a última
janela do laço — e ela se apresentava como "o foco principal", que é uma
categoria que nem existe no motor.

O MOTOR NUNCA ESTEVE PRESO A UM ATIVO
--------------------------------------
Isto é o que mais importa, e é o oposto do que a conversa dava a entender. O
ciclo já percorre TODAS as janelas monitoradas, guarda estado separado para
cada uma, decide posição e ordem viva POR ATIVO (`posicao_aberta_no_ativo`,
`ordem_enviada_e_viva_no_ativo`), e o envio troca o instrumento no ticket
antes de mandar (`garantir_ativo_no_ticket`, no tradovate_auto). O que estava
preso a um ativo era o RELATO.

E relato errado sobre qual contrato está sendo lido, numa ferramenta que manda
ordem sozinha, é do tipo que faz o trader decidir o MESU6 olhando a resposta
sobre o gráfico do ouro.

O QUE ESTES TESTES CRAVAM
--------------------------
· A leitura é guardada POR ATIVO, com carimbo de hora — o carimbo é o que
  separa "está sendo lido agora" de "foi lido hoje de manhã".
· O texto que vai para o chat lista TODOS os ativos e diz, com todas as
  letras, que nenhum é o principal.
· Ativo que ficou sem gráfico mas tem posição viva aparece assim mesmo — foi
  esse o caso do MESU6 às 10:35, e o silêncio sobre ele é que abriu espaço
  para o "não está no foco".
· E a trava nova que o multi-ativo TORNA NECESSÁRIA: com dois ativos na mesa,
  uma linha de POSIÇÃO sem ticker deixa de ser associada ao ativo da janela
  principal. Com um gráfico só, chutar era a única hipótese possível; com
  dois, o chute carimbaria a posição do ouro com o ticker do índice, no
  registro que alimenta P&L, drawdown e o freio de stops.
"""

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
    "registrar_leitura_do_ativo",
    "ativos_em_analise",
    "texto_da_mesa_multiativo",
    "MINUTOS_LEITURA_RECENTE",
])

registrar = NS["registrar_leitura_do_ativo"]
em_analise = NS["ativos_em_analise"]
texto = NS["texto_da_mesa_multiativo"]

AGORA = 1_000_000.0


def _leitura(acao="SELL", preco=7709.5, prob=75, janela="Chrome · Tradovate",
             hora="10:31"):
    return {"acao": acao, "preco": preco, "probabilidade": prob,
            "janela": janela, "hora": hora}


class CadaAtivoGuardaAPropriaLeitura(unittest.TestCase):

    def test_o_segundo_ativo_NAO_apaga_o_primeiro(self):
        """A queixa inteira em uma linha."""
        r = registrar({}, "MESU6", _leitura(), agora=AGORA)
        r = registrar(r, "MGCV6", _leitura(preco=4457.5), agora=AGORA + 10)
        self.assertEqual(sorted(r), ["MESU6", "MGCV6"])
        self.assertEqual(r["MESU6"]["preco"], 7709.5)
        self.assertEqual(r["MGCV6"]["preco"], 4457.5)

    def test_a_leitura_nova_do_MESMO_ativo_substitui_a_velha(self):
        r = registrar({}, "MESU6", _leitura(preco=7709.5), agora=AGORA)
        r = registrar(r, "MESU6", _leitura(preco=7694.0), agora=AGORA + 300)
        self.assertEqual(len(r), 1)
        self.assertEqual(r["MESU6"]["preco"], 7694.0)

    def test_o_ticker_e_normalizado_para_maiusculas(self):
        r = registrar({}, "mesu6", _leitura(), agora=AGORA)
        self.assertIn("MESU6", r)
        self.assertEqual(r["MESU6"]["ativo"], "MESU6")

    def test_ativo_DESCONHECIDO_ou_vazio_nao_entra(self):
        """Instrumento que não foi lido não pode virar uma linha afirmando que
        foi — este programa manda ordem."""
        for ruim in ("", None, "  ", "DESCONHECIDO", "desconhecido"):
            self.assertEqual(registrar({}, ruim, _leitura(), agora=AGORA), {})

    def test_o_registro_original_nao_e_mutado(self):
        antes = registrar({}, "MESU6", _leitura(), agora=AGORA)
        registrar(antes, "MGCV6", _leitura(), agora=AGORA)
        self.assertEqual(list(antes), ["MESU6"])

    def test_toda_leitura_leva_carimbo_de_hora(self):
        r = registrar({}, "MESU6", _leitura(), agora=AGORA)
        self.assertEqual(r["MESU6"]["ts"], AGORA)


class SoContaOQueFoiLidoHaPOUCO(unittest.TestCase):

    def test_os_dois_ativos_recentes_aparecem(self):
        r = registrar({}, "MESU6", _leitura(), agora=AGORA)
        r = registrar(r, "MGCV6", _leitura(), agora=AGORA + 60)
        nomes = [v["ativo"] for v in em_analise(r, agora=AGORA + 120)]
        self.assertEqual(sorted(nomes), ["MESU6", "MGCV6"])

    def test_o_mais_recente_vem_primeiro(self):
        r = registrar({}, "MESU6", _leitura(), agora=AGORA)
        r = registrar(r, "MGCV6", _leitura(), agora=AGORA + 60)
        self.assertEqual(em_analise(r, agora=AGORA + 120)[0]["ativo"], "MGCV6")

    def test_janela_tirada_da_lista_de_manha_para_de_aparecer(self):
        """Sem o recorte por tempo, um gráfico que ele removeu continuaria
        sendo anunciado como 'em análise' o dia inteiro — foi assim que a
        resposta das 10:35 virou ficção."""
        r = registrar({}, "MESU6", _leitura(), agora=AGORA)
        r = registrar(r, "MGCV6", _leitura(), agora=AGORA + 3600)
        nomes = [v["ativo"] for v in em_analise(r, minutos=15,
                                                agora=AGORA + 3600)]
        self.assertEqual(nomes, ["MGCV6"])

    def test_registro_vazio_nao_estoura(self):
        self.assertEqual(em_analise({}, agora=AGORA), [])
        self.assertEqual(em_analise(None, agora=AGORA), [])


class OTextoQueVaiParaOChat(unittest.TestCase):

    def _texto(self, posicoes=None, agora=AGORA + 60):
        r = registrar({}, "MESU6", _leitura(acao="SELL", preco=7709.5, prob=75),
                      agora=AGORA)
        r = registrar(r, "MGCV6", _leitura(acao="HOLD", preco=4457.5, prob=50),
                      agora=AGORA + 30)
        return texto(r, posicoes, agora=agora)

    def test_OS_DOIS_ativos_saem_no_texto(self):
        t = self._texto()
        self.assertIn("MESU6", t)
        self.assertIn("MGCV6", t)

    def test_diz_com_todas_as_letras_que_NENHUM_e_o_principal(self):
        """É a frase que impede o modelo de eleger um e chamá-lo de foco — o
        erro literal de 10:35."""
        self.assertIn("nenhum é 'o principal'", self._texto())

    def test_cada_ativo_leva_a_PROPRIA_leitura(self):
        t = self._texto()
        linha_mes = next(l for l in t.splitlines() if "MESU6" in l)
        linha_mgc = next(l for l in t.splitlines() if "MGCV6" in l)
        self.assertIn("7709.5", linha_mes)
        self.assertIn("SELL", linha_mes)
        self.assertIn("4457.5", linha_mgc)
        self.assertIn("HOLD", linha_mgc)
        self.assertNotIn("4457.5", linha_mes)

    def test_a_posicao_aberta_sai_COLADA_no_ativo_dela(self):
        t = self._texto(posicoes=[{"status": "ABERTA", "ativo": "MESU6",
                                   "direcao": "SELL", "contratos": 17,
                                   "entry": 7685.0}])
        linhas = t.splitlines()
        i_mes = next(i for i, l in enumerate(linhas) if "– MESU6" in l)
        self.assertIn("17 ctr", linhas[i_mes + 1])
        self.assertIn("ABERTA", linhas[i_mes + 1])

    def test_ativo_com_posicao_viva_e_SEM_grafico_e_denunciado(self):
        """Foi exatamente o caso do MESU6 às 10:35: posição de 11 contratos
        pendurada e nenhum gráfico monitorado. Calar sobre isso é o que abriu
        espaço para o 'não está no foco'."""
        r = registrar({}, "MGCV6", _leitura(), agora=AGORA)
        t = texto(r, [{"status": "PENDENTE", "ativo": "MESU6",
                       "direcao": "SELL", "contratos": 11, "entry": 7709.5}],
                  agora=AGORA + 10)
        self.assertIn("SEM gráfico monitorado", t)
        self.assertIn("MESU6", t.split("SEM gráfico monitorado")[1])

    def test_sem_leitura_nenhuma_ele_DIZ_isso_em_vez_de_inventar(self):
        # O texto virou uma PROIBIÇÃO, não uma constatação: em 31/08, 15:17,
        # diante do "nenhum gráfico lido", o modelo escreveu um bloco inteiro
        # de telemetria inventada. Ver test_gargalos_do_log.
        self.assertIn("NENHUM GRÁFICO FOI LIDO", texto({}, [], agora=AGORA))

    def test_probabilidade_ilegivel_nao_derruba_o_texto(self):
        r = registrar({}, "MESU6", {"acao": "SELL", "preco": 7709.5,
                                    "probabilidade": None}, agora=AGORA)
        self.assertIn("MESU6", texto(r, [], agora=AGORA + 10))


class OChatUsaAMESAINTEIRA(unittest.TestCase):

    def test_o_status_do_chat_chama_o_texto_multiativo(self):
        corpo = funcao_inteira(_fonte(), "_chat_status_texto")
        self.assertIn("texto_da_mesa_multiativo", corpo)

    def test_o_motor_registra_TODA_janela_e_nao_so_a_principal(self):
        """A gravação por ativo não pode viver dentro de um `if
        janela_principal` — seria trocar o defeito de lugar."""
        fonte = _fonte()
        # `self._ultima_analise = {` já roda para TODA janela do ciclo (é ele
        # que alimenta a linha "📊 Ativo: ..." que sai duas vezes por ciclo no
        # log dele). Ancorar aqui e exigir que nada de janela principal se
        # meta entre os dois é o que trava a gravação por ativo no mesmo
        # caminho.
        # com a quebra de linha: o `= {}` do __init__ não é este.
        i_analise = fonte.index("self._ultima_analise = {\n")
        i_registro = fonte.index("registrar_leitura_do_ativo(", i_analise)
        entre = fonte[i_analise:i_registro]
        self.assertNotIn("janela_principal", entre,
                         "a gravação por ativo caiu dentro do ramo da janela "
                         "principal — o defeito só mudaria de lugar")
        # E a chamada usa o dicionário anterior, em vez de recomeçar do zero a
        # cada janela (o que devolveria o comportamento de 'a última ganha').
        chamada = fonte[i_registro:i_registro + 260]
        self.assertIn("_analises_por_ativo", chamada)


class ComDoisAtivosNaoSeCHUTAOTicker(unittest.TestCase):
    """A trava que o multi-ativo torna necessária."""

    def test_a_leitura_sem_ticker_e_DESCARTADA_quando_ha_mais_de_um_ativo(self):
        corpo = funcao_inteira(_fonte(), "_tv_sincronizar_posicoes")
        i_guarda = corpo.index("ativos_em_analise(")
        i_chute = corpo.index('sem_ativo[0]["ativo"] = atual')
        self.assertLess(i_guarda, i_chute,
                        "o chute pelo ativo da janela principal voltou a vir "
                        "antes da checagem de quantos ativos estão na mesa")
        self.assertIn("len(_lidos) > 1", corpo)

    def test_o_log_DIZ_quais_ativos_causaram_a_duvida(self):
        """'Descartei a leitura' sem dizer por quê vira defeito fantasma."""
        corpo = funcao_inteira(_fonte(), "_tv_sincronizar_posicoes")
        self.assertIn("ativos em análise", corpo)


class ElaNaoPodeNEGARUmaOrdemQueELAMandou(unittest.TestCase):
    """31/08, 11:40 o autônomo enviou SELL MESU6 17 ctr @ 7685.0. 11:42:

        ❯ E PORQUE ENVIOU ORDEM NO MESU6?
        ✳ Eu NÃO enviei ordem nenhuma. ... a posição já estava na sua mesa
          quando esta conversa começou.

    Mentira, sobre a conta dele, dois minutos depois do envio. A guarda de
    ação inventada até disparou — mas ela existe para o caso OPOSTO (a IA
    dizendo que mandou quando não mandou), e o aviso que ela grudou embaixo
    REFORÇOU a negação.

    A causa era banal: o contexto do chat listava as posições abertas sem
    dizer QUEM as abriu."""

    def test_o_contexto_do_chat_nomeia_as_ordens_que_o_ROBO_enviou(self):
        corpo = funcao_inteira(_fonte(), "_chat_status_texto")
        self.assertIn('"ROBO"', corpo)
        self.assertIn("ENVIEI HOJE", corpo)

    def test_o_contexto_PROIBE_negar_essas_ordens(self):
        corpo = funcao_inteira(_fonte(), "_chat_status_texto")
        self.assertIn("nunca negue", corpo.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
