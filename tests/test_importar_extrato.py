"""O EXTRATO ENTRA NO DIÁRIO SEM DUPLICAR E SEM TROCAR O DIA.

Este arquivo cuida da metade que TOCA O DINHEIRO. O `test_extrato_pdf.py`
cuida de ler o PDF; aqui é o que acontece depois: as operações lidas viram
registros no diário, e o diário é a base de onde sai a taxa de acerto que ele
usa para decidir tamanho de posição.

DUAS COISAS PODEM DAR ERRADO EM SILÊNCIO, E AS DUAS MUDAM NÚMERO
------------------------------------------------------------------
1. DUPLICAR. Ele vai importar mais de uma vez — no fim do dia, e de novo
   amanhã, quando o relatório trouxer os dois dias. Sem identidade estável,
   cada importação recontaria o que já estava lá e o diário passaria a contar
   duas vezes o mesmo dinheiro. A identidade é o par de números de ordem da
   corretora, e não data nem preço: duas saídas parciais no mesmo segundo,
   pelo mesmo preço, são operações diferentes e teriam a mesma chave.

2. CARIMBAR COM A HORA DE AGORA. É por `data_fechamento` que o resultado é
   atribuído a um pregão. Como o pregão dele vai das 19:00 às 17:59, carimbar
   a importação com a hora atual jogaria o dia inteiro de ontem para dentro do
   pregão de hoje — e o número do dia ficaria errado nos dois dias, sem nada
   na tela indicando isso.

E UMA QUE MUDA O RESULTADO POR UM FATOR
----------------------------------------
O extrato traz `quantidade x preço x multiplicador` na coluna nocional, e o
programa tem a sua própria tabela em `valor_por_ponto_do_ativo`. Quando os
dois discordam, o P&L sai errado por um fator — o tipo de erro que não parece
erro, porque o número continua plausível. O programa compara e DIZ antes de
gravar.

POR QUE STOP E ALVO FICAM VAZIOS
---------------------------------
Dá para enxergá-los no relatório: as `multibracket` canceladas ao lado de uma
entrada são a proteção que morreu junto com ela. Mas amarrar bracket a entrada
exige supor qual pertence a qual, porque o relatório não traz o vínculo. Como
stop e alvo não entram na conta do resultado, supor isso custaria risco de
erro sem comprar nada. Vazio aqui quer dizer "o documento não disse".
"""

import os
import sys
import unittest

from harness import RAIZ, carregar

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import extrato_pdf as E          # noqa: E402


def _fonte(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


class TestAIdentidadeDaOperacaoImportada(unittest.TestCase):

    def setUp(self):
        self.ns = carregar(["chave_da_operacao_importada", "separar_ja_importadas"])

    def test_a_chave_e_o_par_de_numeros_de_ordem(self):
        chave = self.ns["chave_da_operacao_importada"](
            {"id_entrada": "631593261057", "id_saida": "631593261106"})
        self.assertIn("631593261057", chave)
        self.assertIn("631593261106", chave)

    def test_operacoes_diferentes_com_mesmo_preco_e_hora_tem_chaves_DIFERENTES(self):
        """Duas saídas parciais no mesmo segundo pelo mesmo preço são
        operações diferentes. Se a identidade fosse data+preço, a segunda
        sumiria como se fosse repetida."""
        f = self.ns["chave_da_operacao_importada"]
        a = f({"id_entrada": "1", "id_saida": "9"})
        b = f({"id_entrada": "2", "id_saida": "9"})
        self.assertNotEqual(a, b)

    def test_o_que_ja_esta_no_diario_nao_entra_de_novo(self):
        novas, repetidas = self.ns["separar_ja_importadas"](
            [{"id_entrada": "1", "id_saida": "2"},
             {"id_entrada": "3", "id_saida": "4"}],
            [{"chave_extrato": "1>2"}])
        self.assertEqual(len(novas), 1)
        self.assertEqual(len(repetidas), 1)
        self.assertEqual(novas[0]["id_entrada"], "3")

    def test_diario_vazio_deixa_tudo_entrar(self):
        novas, repetidas = self.ns["separar_ja_importadas"](
            [{"id_entrada": "1", "id_saida": "2"}], [])
        self.assertEqual(len(novas), 1)
        self.assertEqual(repetidas, [])

    def test_devolve_AS_DUAS_listas_e_nao_so_filtra(self):
        """O programa vai DIZER quantas ignorou. Importação que silenciosamente
        pula metade das linhas é indistinguível de importação que falhou pela
        metade."""
        novas, repetidas = self.ns["separar_ja_importadas"](
            [{"id_entrada": "1", "id_saida": "2"}], [{"chave_extrato": "1>2"}])
        self.assertEqual(novas, [])
        self.assertEqual(len(repetidas), 1)

    def test_posicao_sem_chave_de_extrato_nao_bloqueia_nada(self):
        """As operações do robô e as lançadas na mão não têm essa chave — e um
        `None` casando com `None` bloquearia a importação inteira."""
        novas, _ = self.ns["separar_ja_importadas"](
            [{"id_entrada": "1", "id_saida": "2"}],
            [{"origem": "ROBO"}, {"origem": "MANUAL"}])
        self.assertEqual(len(novas), 1)


class TestADataVemDoEXTRATOeNaoDeAgora(unittest.TestCase):

    def test_o_formato_e_decidido_PELO_DOCUMENTO(self):
        """Basta uma data com componente maior que 12 para o arquivo
        responder: 08/24 só pode ser mês 08, dia 24."""
        self.assertEqual(E.formato_de_data("08/24/2026 00:07:24"), "MDY")
        self.assertEqual(E.formato_de_data("24/08/2026 00:07:24"), "DMY")

    def test_arquivo_que_NAO_desempata_devolve_None(self):
        """None quer dizer 'o arquivo não me disse'. Quem chamou trata como
        pergunta em aberto, não como MDY silencioso."""
        self.assertIsNone(E.formato_de_data("08/07/2026 10:00:00"))

    def test_a_conversao_para_o_formato_do_diario(self):
        self.assertEqual(E.data_br("08/24/2026 00:07:24", "MDY"), "24/08/2026 00:07")
        self.assertEqual(E.data_br("24/08/2026 00:07:24", "DMY"), "24/08/2026 00:07")

    def test_ano_de_dois_digitos_e_completado(self):
        self.assertEqual(E.data_br("8/24/26", "MDY"), "24/08/2026")

    def test_sem_data_devolve_VAZIO_e_nao_a_data_de_hoje(self):
        """Devolver hoje colocaria uma operação antiga no pregão de agora sem
        ninguém perceber."""
        self.assertEqual(E.data_br(""), "")
        self.assertEqual(E.data_br("sem data aqui"), "")

    def test_a_importacao_usa_a_data_do_extrato_no_fechamento(self):
        """É por `data_fechamento` que o resultado é atribuído a um pregão."""
        codigo = _fonte("main_app.py")
        i = codigo.index("def importar_operacoes_do_extrato")
        corpo = codigo[i:i + 3000]
        self.assertIn("data_fechamento", corpo)
        self.assertIn("extrato_pdf.data_br", corpo)
        self.assertNotIn("time.strftime", corpo,
                         "carimbou com a hora de agora em vez da hora do extrato")


class TestOQueEntraNoDiario(unittest.TestCase):

    def setUp(self):
        self.codigo = _fonte("main_app.py")
        i = self.codigo.index("def importar_operacoes_do_extrato")
        self.corpo = self.codigo[i:i + 3000]

    def test_a_origem_e_propria_e_separavel(self):
        """Dá para separar no diário o que veio do extrato do que é do robô e
        do que ele lançou na mão."""
        self.assertIn("ORIGEM_EXTRATO", self.corpo)
        self.assertIn('ORIGEM_EXTRATO = "EXTRATO"', self.codigo)

    def test_stop_e_alvo_ficam_VAZIOS(self):
        """Amarrar bracket a entrada exige supor qual pertence a qual, e o
        relatório não traz o vínculo. Vazio quer dizer 'o documento não disse'."""
        self.assertIn("None, None, None", self.corpo)

    def test_a_operacao_entra_FECHADA_com_o_preco_de_saida_lido(self):
        self.assertIn('"FECHADA"', self.corpo)
        self.assertIn("calcular_pnl_posicao", self.corpo)

    def test_a_chave_de_extrato_e_gravada_na_posicao(self):
        """Sem ela, a próxima importação duplicaria tudo."""
        self.assertIn("chave_extrato", self.corpo)


class TestODivergenciaDeMultiplicadorEDITA(unittest.TestCase):

    def setUp(self):
        self.ns = carregar(["conferir_multiplicador_do_extrato"],
                           stubs={"valor_por_ponto_do_ativo": lambda a: 5.0})

    def test_quando_bate_nao_ha_o_que_dizer(self):
        fora = self.ns["conferir_multiplicador_do_extrato"](
            [{"ativo": "MESU6", "multiplicador": 5.0}])
        self.assertEqual(fora, [])

    def test_quando_discorda_ele_DIZ_os_dois_numeros(self):
        """O P&L sairia errado por um fator, e o número continuaria plausível."""
        fora = self.ns["conferir_multiplicador_do_extrato"](
            [{"ativo": "MNQU6", "multiplicador": 2.0}])
        self.assertEqual(len(fora), 1)
        self.assertEqual(fora[0]["do_extrato"], 2.0)
        self.assertEqual(fora[0]["do_programa"], 5.0)

    def test_a_mesma_divergencia_e_dita_UMA_VEZ_por_ativo(self):
        """Repetir a mesma linha 55 vezes esconderia as outras."""
        fora = self.ns["conferir_multiplicador_do_extrato"](
            [{"ativo": "MNQU6", "multiplicador": 2.0}] * 55)
        self.assertEqual(len(fora), 1)

    def test_operacao_sem_multiplicador_no_extrato_nao_vira_alarme_falso(self):
        fora = self.ns["conferir_multiplicador_do_extrato"](
            [{"ativo": "MESU6", "multiplicador": None}])
        self.assertEqual(fora, [])


class TestAConferenciaVemANTESDaGravacao(unittest.TestCase):

    def setUp(self):
        self.codigo = _fonte("main_app.py")
        i = self.codigo.index("def _importar_extrato_pdf")
        # Janela larga: o bloco de substituição entrou no meio deste método na
        # mesma rodada, e janela curta mede a prosa e não o código.
        self.corpo = self.codigo[i:i + 9000]

    def test_ele_pergunta_antes_de_gravar(self):
        """O diário é a base do cálculo de acerto: uma operação a mais ou a
        menos ali muda um número que ele usa para decidir dinheiro."""
        i_pergunta = self.corpo.index("askyesno")
        i_grava = self.corpo.index("importar_operacoes_do_extrato")
        self.assertLess(i_pergunta, i_grava, "gravou antes de perguntar")

    def test_o_nao_dele_NAO_grava_nada(self):
        self.assertIn("Importação cancelada", self.corpo)

    def test_arquivo_que_nao_e_extrato_e_dito_e_nao_gravado_como_zero(self):
        """Gravar zero operações com cara de sucesso faria ele achar que o dia
        não teve trade."""
        self.assertIn("if not ordens:", self.corpo)
        self.assertIn("relatório de ORDENS", self.corpo)

    def test_sem_leitor_de_pdf_ele_diz_O_QUE_INSTALAR(self):
        self.assertIn("SemLeitorDePdf", self.corpo)

    def test_o_resumo_mostrado_e_o_MESMO_que_vai_para_o_log(self):
        """Duas versões do mesmo fato divergem, e aí a tela e o log passam a
        contar histórias diferentes sobre a mesma importação."""
        self.assertIn("texto_final", self.corpo)
        self.assertIn("self.log", self.corpo)

    def test_o_formato_de_data_ambiguo_e_DITO_e_nao_engolido(self):
        self.assertIn("formato is None", self.corpo)
        self.assertIn("mês/dia", self.corpo)


class TestDoPDF_AoDIARIO_PontaAPonta(unittest.TestCase):
    """A cadeia inteira num só teste, com um extrato de dois dias."""

    EXTRATO = (
        "MESU6 Micro E-mini S&P 500 8/23/26: 4 order(s) "
        "900000000001 Buy 2 MESU6 Limit 7000.00 Filled Chart 2 "
        "08/23/2026 10:00:00 7000.00 08/23/2026 09:59:00 APEX111 USD 70,000.00 "
        "900000000002 Sell 2 MESU6 Limit 7020.00 Canceled multibracket "
        "08/23/2026 10:00:00 APEX111 USD "
        "900000000003 Sell 2 MESU6 Limit 7010.00 Filled Chart 2 "
        "08/23/2026 11:00:00 7010.00 08/23/2026 10:30:00 APEX111 USD 70,100.00 "
        "900000000004 Buy 1 MESU6 Market Filled DOM 1 "
        "08/24/2026 09:00:00 7050.00 08/24/2026 09:00:00 APEX111 USD 35,250.00 "
        "TOTAL:  order(s)4")

    def test_le_casa_e_deixa_a_posicao_aberta_de_fora(self):
        ordens = E.ler_ordens(self.EXTRATO)
        self.assertEqual(len(ordens), 4)
        self.assertEqual(E.total_declarado(self.EXTRATO), 4)

        fechadas, sobras, recusadas = E.operacoes_fechadas(ordens)
        self.assertEqual(recusadas, [])
        self.assertEqual(len(fechadas), 1)
        self.assertEqual(len(sobras), 1)

        op = fechadas[0]
        self.assertEqual(op["direcao"], "BUY")
        self.assertEqual(op["contratos"], 2)
        self.assertEqual(op["entrada"], 7000.00)
        self.assertEqual(op["saida"], 7010.00)
        self.assertEqual(op["multiplicador"], 5.0)

        # A compra a mercado do dia 24 ficou aberta: NÃO vira resultado.
        self.assertEqual(sobras[0]["direcao"], "BUY")
        self.assertEqual(sobras[0]["contratos"], 1)

        # E a data sai no dia certo, no formato do diário.
        formato = E.formato_de_data(self.EXTRATO)
        self.assertEqual(formato, "MDY")
        self.assertEqual(E.data_br(op["fechamento"], formato), "23/08/2026 11:00")

    def test_o_bracket_cancelado_nao_aparece_em_lugar_nenhum(self):
        fechadas, sobras, _ = E.operacoes_fechadas(E.ler_ordens(self.EXTRATO))
        ids = ({f["id_entrada"] for f in fechadas}
               | {f["id_saida"] for f in fechadas}
               | {s["id_entrada"] for s in sobras})
        self.assertNotIn("900000000002", ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOExtratoMANDA_ENaoDuplica(unittest.TestCase):
    """Pedido dele, no meio da implementação: "certifique-se de não duplicar
    os registros do diário com os que serem importados, o que sempre tem mais
    validade são os importados".

    O BURACO ERA MAIOR DO QUE A CHAVE DE IMPORTAÇÃO COBRIA. A chave impede
    importar o MESMO PDF duas vezes. Mas o extrato traz TODAS as ordens da
    conta — inclusive as que o próprio robô enviou, que já estão no diário
    como origem ROBO, e as que ele lançou na mão. Sem esta camada, a PRIMEIRA
    importação já contaria o dia em dobro.

    E a saída não é casar operação com operação: isso exigiria supor qual
    registro corresponde a qual execução, e os preços nem sempre batem (o robô
    grava o que PEDIU, a corretora grava o que EXECUTOU). A saída é usar uma
    propriedade que o documento tem de verdade — dentro do período que cobre,
    ele é completo.
    """

    def setUp(self):
        import datetime
        self.ns = carregar(
            ["periodo_coberto_pelo_extrato", "posicoes_substituidas_pelo_extrato",
             "_parse_dt", "ORIGEM_EXTRATO", "STATUS_SUBSTITUIDA"],
            stubs={"extrato_pdf": E, "datetime": datetime})
        self.faixas = self.ns["periodo_coberto_pelo_extrato"](
            [{"ativo": "MESU6", "abertura": "08/24/2026 10:00:00",
              "fechamento": "08/24/2026 11:00:00"}], [], "MDY")

    def _pos(self, **kw):
        base = {"id": 1, "status": "FECHADA", "origem": "ROBO", "ativo": "MESU6",
                "conta_id": "c1", "data_fechamento": "24/08/2026 10:30",
                "pnl_final": 50.0}
        base.update(kw)
        return base

    def test_o_registro_do_ROBO_dentro_da_janela_e_substituido(self):
        """É o caso que conta o dia em dobro: o robô mandou a ordem, gravou no
        diário, e a mesma ordem está no extrato."""
        alvos = self.ns["posicoes_substituidas_pelo_extrato"](
            [self._pos()], self.faixas, "c1")
        self.assertEqual(len(alvos), 1)

    def test_o_lancamento_MANUAL_dentro_da_janela_tambem(self):
        alvos = self.ns["posicoes_substituidas_pelo_extrato"](
            [self._pos(origem="MANUAL")], self.faixas, "c1")
        self.assertEqual(len(alvos), 1)

    def test_FORA_da_janela_coberta_nada_e_tocado(self):
        """Ele gerou o extrato às 14:21 com o pregão ainda aberto. Substituir
        'o dia todo' apagaria uma operação que fechasse às 15:00 e que o
        extrato não tinha como conter."""
        alvos = self.ns["posicoes_substituidas_pelo_extrato"](
            [self._pos(data_fechamento="24/08/2026 15:00")], self.faixas, "c1")
        self.assertEqual(alvos, [])

    def test_posicao_ABERTA_nao_e_substituida(self):
        """Posição aberta não é resultado e não tem par no que foi importado."""
        alvos = self.ns["posicoes_substituidas_pelo_extrato"](
            [self._pos(status="ABERTA", data_fechamento=None)], self.faixas, "c1")
        self.assertEqual(alvos, [])

    def test_importacao_ANTERIOR_nao_e_substituida_por_esta(self):
        """A chave de ordem já filtra repetição entre importações. Substituir
        importação por importação começaria a apagar histórico legítimo."""
        alvos = self.ns["posicoes_substituidas_pelo_extrato"](
            [self._pos(origem=self.ns["ORIGEM_EXTRATO"])], self.faixas, "c1")
        self.assertEqual(alvos, [])

    def test_OUTRO_ativo_nao_e_tocado(self):
        """O extrato de MESU6 não fala nada sobre MNQU6."""
        alvos = self.ns["posicoes_substituidas_pelo_extrato"](
            [self._pos(ativo="MNQU6")], self.faixas, "c1")
        self.assertEqual(alvos, [])

    def test_OUTRA_conta_nao_e_tocada(self):
        alvos = self.ns["posicoes_substituidas_pelo_extrato"](
            [self._pos(conta_id="OUTRA")], self.faixas, "c1")
        self.assertEqual(alvos, [])

    def test_sem_carimbo_legivel_NAO_substitui(self):
        """Não dá para provar que está dentro da janela, e apagar por suposição
        é exatamente o que esta função existe para não fazer."""
        for ruim in ("", None, "ontem de manhã"):
            alvos = self.ns["posicoes_substituidas_pelo_extrato"](
                [self._pos(data_fechamento=ruim)], self.faixas, "c1")
            self.assertEqual(alvos, [], repr(ruim))

    def test_a_cobertura_sai_do_PRIMEIRO_ao_ULTIMO_instante(self):
        ini, fim = self.faixas["MESU6"]
        self.assertEqual(ini.strftime("%d/%m %H:%M"), "24/08 10:00")
        self.assertEqual(fim.strftime("%d/%m %H:%M"), "24/08 11:00")

    def test_a_posicao_que_ficou_ABERTA_no_extrato_tambem_conta_para_a_janela(self):
        """A compra que ficou aberta é a última coisa que aconteceu na conta.
        Ignorá-la encurtaria a janela e deixaria de fora registros que o
        extrato de fato cobre."""
        faixas = self.ns["periodo_coberto_pelo_extrato"](
            [{"ativo": "MESU6", "abertura": "08/24/2026 10:00:00",
              "fechamento": "08/24/2026 11:00:00"}],
            [{"ativo": "MESU6", "abertura": "08/24/2026 13:00:00"}], "MDY")
        self.assertEqual(faixas["MESU6"][1].strftime("%H:%M"), "13:00")


class TestSubstituirNAOEApagar(unittest.TestCase):

    def setUp(self):
        self.codigo = _fonte("main_app.py")

    def test_o_registro_antigo_continua_no_disco(self):
        """Linha apagada não se audita. Se um dia a substituição se mostrar
        errada, o que havia antes ainda tem de estar lá."""
        i = self.codigo.index("def marcar_substituidas_pelo_extrato")
        corpo = self.codigo[i:i + 1800]
        self.assertIn("STATUS_SUBSTITUIDA", corpo)
        self.assertNotIn("remove(", corpo)
        self.assertNotIn("del ", corpo)

    def test_o_status_novo_sai_de_TODA_soma_de_uma_vez_so(self):
        """Todo somatório filtra por FECHADA. Uma troca de status já os remove
        de dashboard, taxa de acerto, evolução e relatório — sem tocar em dez
        lugares que contam dinheiro."""
        self.assertIn('STATUS_SUBSTITUIDA = "SUBSTITUIDA"', self.codigo)
        self.assertNotEqual("SUBSTITUIDA", "FECHADA")

    def test_o_programa_DIZ_quantos_vai_aposentar_antes_de_gravar(self):
        """Substituir registro de dinheiro em silêncio seria trocar um erro
        (contar em dobro) por outro pior (apagar sem avisar)."""
        i = self.codigo.index("def _importar_extrato_pdf")
        corpo = self.codigo[i:i + 7000]
        i_aviso = corpo.index("aposentar")
        i_pergunta = corpo.index("askyesno")
        self.assertLess(i_aviso, i_pergunta)

    def test_aposenta_ANTES_de_incluir(self):
        """Se o programa cair no meio, o pior estado é o diário sem os
        registros antigos e sem os novos — falta dinheiro, e falta é visível.
        Na ordem inversa o pior estado é com os dois, ou seja, tudo em dobro:
        um número maior, plausível, que ninguém questiona."""
        i = self.codigo.index("def _importar_extrato_pdf")
        corpo = self.codigo[i:i + 8000]
        self.assertLess(corpo.index("marcar_substituidas_pelo_extrato"),
                        corpo.index("criadas = importar_operacoes_do_extrato"))


class TestImportarVARIOSPDFsNoMesmoDia(unittest.TestCase):
    """Pergunta dele: "posso importar quantos pdfs forem durante o dia que ele
    não duplicará, certo?"

    A resposta é sim, e este teste é a prova — não a promessa. Ele vai exportar
    o relatório às 12h, de novo às 15h, de novo no fim do dia, e cada exportação
    contém TUDO o que veio antes. Sem esta garantia, a terceira importação
    contaria a manhã três vezes.

    DUAS COISAS SEGURAM, E ELAS SÃO INDEPENDENTES:
      · a chave de ordem impede a MESMA operação de entrar duas vezes;
      · a aposentadoria pula quem tem origem EXTRATO, então uma importação
        nunca aposenta a anterior.

    E há um terceiro efeito, mais sutil, que este teste também cobre: um lote
    que estava ABERTO na exportação das 12h aparece FECHADO na das 15h. Ele
    tem de entrar — e entra, porque o par entrada>saída é novo.
    """

    CAB = ("MESU6 Micro E-mini S&P 500 8/24/26: N order(s) ")

    def _linha(self, id_, lado, qtd, preco, hora):
        # ID com 12 dígitos como o da corretora: o leitor exige 9 ou mais para
        # não confundir número de ordem com qualquer inteiro solto no texto.
        id_ = f"63159326{int(id_):04d}"
        return (f"{id_} {lado} {qtd} MESU6 Limit {preco:.2f} Filled Chart {qtd} "
                f"08/24/2026 {hora} {preco:.2f} 08/24/2026 {hora} "
                f"APEX111 USD {qtd * preco * 5:,.2f} ")

    def _cadeia(self, texto, diario):
        """Repete o caminho real: ler, casar, e separar o que já está lá."""
        ns = carregar(["separar_ja_importadas", "chave_da_operacao_importada"])
        fechadas, sobras, recusadas = E.operacoes_fechadas(E.ler_ordens(texto))
        novas, repetidas = ns["separar_ja_importadas"](fechadas, diario)
        for op in novas:
            diario.append({"chave_extrato": ns["chave_da_operacao_importada"](op),
                           "origem": "EXTRATO", "status": "FECHADA",
                           "contratos": op["contratos"], "ativo": op["ativo"]})
        return novas, repetidas, sobras

    def test_tres_importacoes_no_mesmo_dia_nao_repetem_nada(self):
        manha = self.CAB + (
            self._linha("1", "Buy", 2, 7000.0, "10:00:00")
            + self._linha("2", "Sell", 2, 7010.0, "10:30:00"))
        tarde = manha + (
            self._linha("3", "Buy", 1, 7020.0, "13:00:00")
            + self._linha("4", "Sell", 1, 7030.0, "13:30:00"))
        fim = tarde + (
            self._linha("5", "Buy", 3, 7040.0, "16:00:00")
            + self._linha("6", "Sell", 3, 7050.0, "16:30:00"))

        diario = []
        n1, r1, _ = self._cadeia(manha, diario)
        n2, r2, _ = self._cadeia(tarde, diario)
        n3, r3, _ = self._cadeia(fim, diario)

        self.assertEqual((len(n1), len(r1)), (1, 0), "1ª importação")
        self.assertEqual((len(n2), len(r2)), (1, 1), "2ª: só a tarde é nova")
        self.assertEqual((len(n3), len(r3)), (1, 2), "3ª: só o fim é novo")

        # O diário terminou com UMA operação por par de ordens, e nenhuma
        # chave repetida — que é a definição de não ter duplicado.
        chaves = [p["chave_extrato"] for p in diario]
        self.assertEqual(len(chaves), 3)
        self.assertEqual(len(set(chaves)), 3)
        self.assertEqual(sum(p["contratos"] for p in diario), 6)

    def test_importar_o_MESMO_pdf_duas_vezes_nao_faz_nada(self):
        """O caso mais provável de todos: ele clica duas vezes sem lembrar."""
        texto = self.CAB + (self._linha("1", "Buy", 2, 7000.0, "10:00:00")
                            + self._linha("2", "Sell", 2, 7010.0, "10:30:00"))
        diario = []
        self._cadeia(texto, diario)
        novas, repetidas, _ = self._cadeia(texto, diario)
        self.assertEqual(novas, [])
        self.assertEqual(len(repetidas), 1)
        self.assertEqual(len(diario), 1)

    def test_o_lote_que_estava_ABERTO_entra_quando_fechar(self):
        """Às 12h a compra ainda não tinha saída e virou sobra, não resultado.
        Às 15h ela fechou — e tem de entrar, senão o dia fica faltando dinheiro."""
        meio_dia = self.CAB + self._linha("1", "Buy", 2, 7000.0, "10:00:00")
        depois = meio_dia + self._linha("2", "Sell", 2, 7010.0, "14:00:00")

        diario = []
        n1, _, sobras1 = self._cadeia(meio_dia, diario)
        self.assertEqual(n1, [])
        self.assertEqual(sobras1[0]["contratos"], 2)

        n2, _, sobras2 = self._cadeia(depois, diario)
        self.assertEqual(len(n2), 1)
        self.assertEqual(n2[0]["entrada"], 7000.0)
        self.assertEqual(n2[0]["saida"], 7010.0)
        self.assertEqual(sobras2, [])

    def test_uma_importacao_NUNCA_aposenta_a_anterior(self):
        """Se aposentasse, a segunda importação apagaria a primeira e depois
        se recusaria a reinserir (a chave já existe) — o dia sumiria."""
        import datetime
        ns = carregar(["posicoes_substituidas_pelo_extrato", "_parse_dt",
                       "ORIGEM_EXTRATO"],
                      stubs={"extrato_pdf": E, "datetime": datetime})
        faixas = {"MESU6": (datetime.datetime(2026, 8, 24, 9, 0),
                            datetime.datetime(2026, 8, 24, 17, 0))}
        ja_importada = {"id": 1, "status": "FECHADA", "ativo": "MESU6",
                        "origem": ns["ORIGEM_EXTRATO"], "conta_id": "c1",
                        "data_fechamento": "24/08/2026 10:30"}
        self.assertEqual(
            ns["posicoes_substituidas_pelo_extrato"]([ja_importada], faixas, "c1"), [])

    def test_aposentar_e_IDEMPOTENTE(self):
        """Na 2ª importação o registro do robô da manhã já está SUBSTITUIDA.
        Ele não pode ser 'aposentado de novo' nem voltar para a conta."""
        import datetime
        ns = carregar(["posicoes_substituidas_pelo_extrato", "_parse_dt",
                       "STATUS_SUBSTITUIDA", "ORIGEM_EXTRATO"],
                      stubs={"extrato_pdf": E, "datetime": datetime})
        faixas = {"MESU6": (datetime.datetime(2026, 8, 24, 9, 0),
                            datetime.datetime(2026, 8, 24, 17, 0))}
        ja_aposentada = {"id": 1, "status": ns["STATUS_SUBSTITUIDA"],
                         "ativo": "MESU6", "origem": "ROBO", "conta_id": "c1",
                         "data_fechamento": "24/08/2026 10:30"}
        self.assertEqual(
            ns["posicoes_substituidas_pelo_extrato"]([ja_aposentada], faixas, "c1"), [])
