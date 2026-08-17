#!/usr/bin/env python3
"""O FIM DE SEMANA COMIA DOIS DIAS DO PRAZO — e ele viu isso na tela.

Print de 17/08/2026, uma segunda-feira. A trilha do Plano de Trading mostrava:

    Trilha de 8 dia(s):  D1 ✅  D2 ❌  D3 ❌  D4 ⬜  D5 ⬜  D6 ⬜  D7 ⬜  D8 ⬜
    Falta p/ meta: US$ 2,767.10   |   Ritmo: US$ 553.42/dia

Os dois ❌ eram SÁBADO (15/08) e DOMINGO (16/08). O ciclo abriu na sexta, o
mercado ficou fechado o fim de semana inteiro, e mesmo assim dois dias do
prazo foram consumidos e marcados como dias PERDIDOS. O efeito no bolso: o
ritmo exigido saltou de US$ 400 para US$ 553,42 por dia por causa de dois
dias em que não havia como operar.

A causa era uma linha: `dias_passados = (datetime.date.today() -
data_inicio).days`. Subtração de calendário. Não sabe de fim de semana, não
sabe de feriado, e não sabe que ele pode decidir não operar num dia.

Palavras dele: "e se eu quiser ficar um dia sem operar? e se for feriado ou
final de semana? ajuste isso para que eu consiga clicar ali no quadradinho
dos dias e escolher."

Duas respostas, e as duas estão testadas aqui:
  • o que é objetivo o código resolve — sábado não é dia de pregão;
  • o que é julgamento dele (feriado, folga, viagem) vira um clique.
"""

import datetime
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from harness import carregar

# O pregão que ELE descreveu à ferramenta em 14/08: "o mercado começa às 19h
# de domingo e encerra às 17:59 de sexta-feira".
PREGAO_NOTURNO = {"hora_inicio": "19:00", "hora_fim": "17:59"}
PREGAO_DIURNO = {"hora_inicio": "09:00", "hora_fim": "17:00"}


def _ns(cfg=None):
    cfg = cfg or PREGAO_NOTURNO
    return carregar(
        ["dias_meta_do_plano", "_domingo_e_pregao", "dias_de_pregao_entre",
         "dia_do_ciclo", "_passo_de_pregao", "data_do_dia_do_ciclo"],
        stubs={"plano_da_conta_ativa": lambda: {},
               "carregar_config": lambda: cfg,
               "PADRAO_CONFIG_APP": cfg,
               "datetime": datetime})


def _d(iso):
    return datetime.date.fromisoformat(iso)


class TestSabadoNuncaConta(unittest.TestCase):
    """Sábado não é dia de pregão em configuração nenhuma. Não existe sessão."""

    def test_sexta_para_sabado_nao_anda(self):
        entre = _ns()["dias_de_pregao_entre"]
        self.assertEqual(entre(_d("2026-08-14"), _d("2026-08-15"),
                               PREGAO_NOTURNO), 0)

    def test_o_fim_de_semana_REAL_dele(self):
        """Sexta 14/08 → segunda 17/08. O calendário diz 3 dias. Com o pregão
        noturno, domingo 19h é sessão e sábado não: são 2."""
        entre = _ns()["dias_de_pregao_entre"]
        self.assertEqual((_d("2026-08-17") - _d("2026-08-14")).days, 3,
                         "o calendário continua sendo 3 — é a conta antiga")
        self.assertEqual(entre(_d("2026-08-14"), _d("2026-08-17"),
                               PREGAO_NOTURNO), 2)

    def test_com_pregao_diurno_o_domingo_tambem_sai(self):
        """Pregão 09:00→17:00 não abre domingo à noite. Sexta → segunda = 1."""
        entre = _ns(PREGAO_DIURNO)["dias_de_pregao_entre"]
        self.assertEqual(entre(_d("2026-08-14"), _d("2026-08-17"),
                               PREGAO_DIURNO), 1)

    def test_uma_semana_cheia(self):
        """Segunda a segunda: 7 dias de calendário, 6 de pregão noturno
        (só o sábado sai)."""
        entre = _ns()["dias_de_pregao_entre"]
        self.assertEqual(entre(_d("2026-08-17"), _d("2026-08-24"),
                               PREGAO_NOTURNO), 6)

    def test_datas_invertidas_ou_vazias_devolvem_zero(self):
        entre = _ns()["dias_de_pregao_entre"]
        self.assertEqual(entre(_d("2026-08-20"), _d("2026-08-14")), 0)
        self.assertEqual(entre(_d("2026-08-14"), _d("2026-08-14")), 0)
        self.assertEqual(entre(None, _d("2026-08-14")), 0)
        self.assertEqual(entre(_d("2026-08-14"), None), 0)


class TestOCasoDoPrint(unittest.TestCase):
    """A conta que estava errada na tela dele, com os números da tela dele."""

    PLANO = {"dias_meta": 8, "data_inicio": "2026-08-14"}   # sexta

    def test_segunda_deixa_de_ser_o_dia_4(self):
        """Na tela dele, segunda 17/08 era o dia 4 de 8 — dois dias queimados
        pelo fim de semana. Com dia de pregão, é o dia 3."""
        dia = _ns()["dia_do_ciclo"]
        self.assertEqual(dia(self.PLANO, _d("2026-08-17"), PREGAO_NOTURNO), 3)

    def test_o_sabado_nao_avanca_o_contador(self):
        dia = _ns()["dia_do_ciclo"]
        self.assertEqual(dia(self.PLANO, _d("2026-08-14"), PREGAO_NOTURNO),
                         dia(self.PLANO, _d("2026-08-15"), PREGAO_NOTURNO))

    def test_o_prazo_nao_e_ultrapassado(self):
        """Um ciclo de 8 dias não vai para o dia 9. Ele acabou."""
        dia = _ns()["dia_do_ciclo"]
        self.assertEqual(dia(self.PLANO, _d("2026-12-31"), PREGAO_NOTURNO), 8)

    def test_nunca_menor_que_um(self):
        dia = _ns()["dia_do_ciclo"]
        self.assertEqual(dia(self.PLANO, _d("2026-08-14"), PREGAO_NOTURNO), 1)
        self.assertEqual(dia(self.PLANO, _d("2026-01-01"), PREGAO_NOTURNO), 1)

    def test_sem_data_de_inicio_e_o_primeiro_dia(self):
        dia = _ns()["dia_do_ciclo"]
        self.assertEqual(dia({"dias_meta": 8}, _d("2026-08-17")), 1)


class TestOCliqueDele(unittest.TestCase):
    """Feriado, folga e viagem não estão em calendário nenhum que eu possa
    consultar com honestidade. Quem sabe é ele — então é ele quem clica."""

    def test_clicar_no_dia_manda_no_automatico(self):
        dia = _ns()["dia_do_ciclo"]
        plano = {"dias_meta": 8, "data_inicio": "2026-08-14",
                 "dia_ciclo_ancora": {"dia": 2, "data": "2026-08-17"}}
        self.assertEqual(dia(plano, _d("2026-08-17"), PREGAO_NOTURNO), 2,
                         "a escolha dele tem de ganhar da conta automática")

    def test_a_escolha_nao_congela_o_contador(self):
        """Guardar só o número travaria o dia para sempre. A âncora é
        {dia, data}, então o contador segue andando a partir da escolha."""
        dia = _ns()["dia_do_ciclo"]
        plano = {"dias_meta": 8, "data_inicio": "2026-08-14",
                 "dia_ciclo_ancora": {"dia": 2, "data": "2026-08-17"}}
        self.assertEqual(dia(plano, _d("2026-08-18"), PREGAO_NOTURNO), 3)
        self.assertEqual(dia(plano, _d("2026-08-19"), PREGAO_NOTURNO), 4)

    def test_o_fim_de_semana_tambem_e_pulado_depois_da_escolha(self):
        """De nada adiantaria respeitar o clique e voltar a queimar sábado."""
        dia = _ns()["dia_do_ciclo"]
        plano = {"dias_meta": 8, "data_inicio": "2026-08-14",
                 "dia_ciclo_ancora": {"dia": 2, "data": "2026-08-21"}}  # sexta
        self.assertEqual(dia(plano, _d("2026-08-22"), PREGAO_NOTURNO), 2,
                         "o sábado seguinte à escolha avançou o dia")

    def test_ancora_corrompida_nao_derruba_nada(self):
        """Arquivo de plano editado à mão, versão antiga, JSON meio gravado —
        nada disso pode impedir o Plano de Trading de abrir."""
        dia = _ns()["dia_do_ciclo"]
        base = {"dias_meta": 8, "data_inicio": "2026-08-14"}
        for lixo in ({"dia": "x", "data": "??"}, {"dia": 2}, {"data": "2026-08-17"},
                     {}, "texto", 5, None):
            plano = dict(base, dia_ciclo_ancora=lixo)
            valor = dia(plano, _d("2026-08-17"), PREGAO_NOTURNO)
            self.assertTrue(1 <= valor <= 8, f"âncora {lixo!r} devolveu {valor}")


class TestAsPontasNoApp(unittest.TestCase):
    """A conta certa não serve de nada se a tela não usar, se o clique não
    gravar, ou se o painel não se redesenhar depois do clique."""

    def _fonte(self):
        from harness import fonte_do_arquivo
        return fonte_do_arquivo()

    def test_a_subtracao_de_calendario_saiu_do_plano(self):
        fonte = self._fonte()
        i = fonte.index("def _computar_stats_plano")
        bloco = fonte[i:i + 3000]
        self.assertNotIn("(datetime.date.today() - data_inicio).days", bloco,
                         "a subtração de calendário voltou para a conta do plano")
        self.assertIn("dia_do_ciclo(self.plano)", bloco)

    def test_o_clique_grava_direto_no_plano(self):
        """`salvar_plano_trading` relê TODOS os campos do formulário e desiste
        em bloco se um estiver com texto inválido — o dia escolhido sumiria por
        causa de uma vírgula errada na caixa da margem."""
        fonte = self._fonte()
        i = fonte.index("def _escolher_dia_do_ciclo")
        bloco = fonte[i:i + 3200]
        self.assertIn("salvar_plano_da_conta(self.plano)", bloco)
        self.assertNotIn("self.salvar_plano_trading()", bloco)

    def test_o_clique_forca_o_redesenho(self):
        """A assinatura do painel olha posições, configuração, sinais e
        desempenho — NÃO olha o arquivo do plano. Sem forcar=True o clique
        gravava e a tela não mudava na frente dele."""
        fonte = self._fonte()
        i = fonte.index("def _escolher_dia_do_ciclo")
        bloco = fonte[i:i + 3200]
        self.assertIn("_atualizar_dashboard(forcar=True)", bloco)

    def test_clicar_no_dia_aceso_desfaz(self):
        """Sem desfazer, um clique errado seria permanente."""
        fonte = self._fonte()
        i = fonte.index("def _escolher_dia_do_ciclo")
        bloco = fonte[i:i + 3200]
        self.assertIn('self.plano["dia_ciclo_ancora"] = None', bloco)

    def test_ciclo_novo_zera_a_escolha(self):
        """A âncora diz 'naquela data era o dia N'. Com um ciclo novo ela
        aponta para um ciclo que não existe mais, e o painel abriria no dia 4
        de um ciclo que começou agora."""
        fonte = self._fonte()
        for marca in ("ciclo_inicio",):
            self.assertIn(marca, fonte)
        # os dois pontos que reiniciam o ciclo têm de limpar a âncora
        ocorrencias = fonte.count('self.plano["ciclo_inicio"] = '
                                  'agora.isoformat(timespec="seconds")')
        self.assertEqual(ocorrencias, 2, "os pontos de reinício de ciclo mudaram")
        for pedaco in fonte.split('self.plano["ciclo_inicio"] = '
                                  'agora.isoformat(timespec="seconds")')[1:]:
            self.assertIn('dia_ciclo_ancora"] = None', pedaco[:600],
                          "um reinício de ciclo não limpa o dia escolhido à mão")

    def test_a_trilha_e_de_BOTOES_e_nao_de_texto(self):
        """Era texto dentro de um rótulo: não havia onde clicar."""
        fonte = self._fonte()
        i = fonte.index("def _renderizar_trilha")
        bloco = fonte[i:i + 4200]
        self.assertIn("CTkButton", bloco)
        # O clique deixou de fazer UMA coisa e passou a abrir o menu do dia
        # (definir como hoje · lançar resultado · concluído / não operei).
        self.assertIn("_menu_do_dia", bloco)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOsCinquentaEQuatroDolaresQueSumiram(unittest.TestCase):
    """17/08, 19:59, palavras dele:

        "falha no registro. hoje por exemplo encerrou as 17:59, abriu as 19hs,
         mas antes de fechar eu fiz 54 dolares, e incluir no diario, mas nao
         esta contabilizando"

    Ele estava certo, e a causa não era o diário: era o CARIMBO. Com o pregão
    19:00→17:59, TODA hora anterior às 19:00 pertence ao pregão do dia
    ANTERIOR. Ele operou de tarde e lançou perto das 18h — o lançamento foi,
    corretamente pela regra da sessão, para o pregão da véspera. E some do
    "hoje" que ele estava olhando às 19:59.

    A regra da sessão não está errada. Errado era a ferramenta não dizer nada.
    """

    def _ns(self, cfg):
        return carregar(
            ["data_do_pregao", "_hora_do_registro", "carimbo_para_o_pregao"],
            stubs={"carregar_config": lambda: cfg, "PADRAO_CONFIG_APP": cfg,
                   "datetime": datetime})

    def test_o_lancamento_das_18h_cai_na_vespera(self):
        """O defeito, reproduzido. Se um dia isto deixar de ser verdade, é
        porque a regra do pregão mudou — e aí este teste precisa mudar junto."""
        ns = self._ns(PREGAO_NOTURNO)
        às18 = datetime.datetime(2026, 8, 17, 18, 30)
        self.assertEqual(ns["data_do_pregao"](às18, PREGAO_NOTURNO), "16/08/2026")
        às20 = datetime.datetime(2026, 8, 17, 20, 0)
        self.assertEqual(ns["data_do_pregao"](às20, PREGAO_NOTURNO), "17/08/2026")

    def test_o_carimbo_acerta_o_pregao_pedido(self):
        """É a correção: para gravar NO dia escolhido não basta carimbar
        meio-dia — com pregão que vira, meio-dia do dia D é o pregão D-1."""
        for cfg in (PREGAO_NOTURNO, PREGAO_DIURNO):
            ns = self._ns(cfg)
            for iso in ("2026-08-14", "2026-08-16", "2026-08-17", "2026-12-31"):
                d = _d(iso)
                carimbo = ns["carimbo_para_o_pregao"](d, cfg)
                volta = ns["data_do_pregao"](ns["_hora_do_registro"](carimbo), cfg)
                self.assertEqual(volta, d.strftime("%d/%m/%Y"),
                                 f"cfg={cfg} dia={iso} carimbo={carimbo}")

    def test_aceita_data_em_texto_nos_dois_formatos(self):
        ns = self._ns(PREGAO_NOTURNO)
        self.assertTrue(ns["carimbo_para_o_pregao"]("17/08/2026", PREGAO_NOTURNO)
                        .startswith("17/08/2026"))
        self.assertTrue(ns["carimbo_para_o_pregao"]("2026-08-17", PREGAO_NOTURNO)
                        .startswith("17/08/2026"))

    def test_lixo_devolve_None_em_vez_de_gravar_errado(self):
        """Carimbo errado grava dinheiro no dia errado — calado. Melhor não
        gravar do que gravar em lugar nenhum."""
        ns = self._ns(PREGAO_NOTURNO)
        for lixo in ("", "ontem", "32/13/2026", None, 42):
            self.assertIsNone(ns["carimbo_para_o_pregao"](lixo, PREGAO_NOTURNO),
                              f"{lixo!r} produziu carimbo")

    def test_a_inclusao_manual_DIZ_em_que_pregao_caiu(self):
        """O silêncio era o defeito. Se a data do lançamento não for o dia do
        calendário, a ferramenta tem de explicar por quê."""
        from harness import fonte_do_arquivo
        fonte = fonte_do_arquivo()
        i = fonte.index("Operação CONCLUÍDA incluída no diário")
        bloco = fonte[max(0, i - 2000):i + 400]
        self.assertIn("pregao = data_do_pregao()", bloco)
        self.assertIn("hoje_calendario", bloco)


class TestOResultadoDoDiaLancadoNaMao(unittest.TestCase):
    """17/08: "às vezes faço operações fora das sugestões, então acho que uma
    forma de incluir o resultado do dia no diário seria viável".

    O formulário que existia exige entrada, stop e preço de saída. Quem operou
    cinco vezes na mão e sabe só que fechou o dia em +54 não tem esses números
    — e, obrigado a preenchê-los, INVENTA preços para acertar o total."""

    def test_o_lancamento_nao_inventa_preco(self):
        """Um resultado do dia não tem entrada nem saída. Escrever números ali
        contaminaria toda estatística de preço e de ticks que lê o diário."""
        from harness import fonte_do_arquivo
        fonte = fonte_do_arquivo()
        i = fonte.index("def lancar_resultado_do_dia")
        bloco = fonte[i:i + 2600]
        self.assertIn('"entry": None', bloco)
        self.assertIn('"pnl_final": valor', bloco)
        self.assertIn("carimbo_para_o_pregao", bloco)
        self.assertIn('"origem": "RESULTADO_DIA"', bloco)

    def test_o_dia_da_trilha_e_o_dia_do_diario(self):
        """Se a ida e a volta divergissem, o 'dia 2' da trilha não seria o dia
        2 do diário — e o dinheiro entraria no quadradinho errado."""
        ns = _ns()
        plano = {"dias_meta": 8, "data_inicio": "2026-08-14"}
        for n in range(1, 9):
            data = ns["data_do_dia_do_ciclo"](plano, n, PREGAO_NOTURNO)
            self.assertIsNotNone(data, f"dia {n} sem data")
            self.assertEqual(ns["dia_do_ciclo"](plano, data, PREGAO_NOTURNO), n)

    def test_a_ancora_dele_move_as_datas_junto(self):
        """Se ele diz que hoje é o dia 2, o dia 3 é o próximo pregão — e não a
        data que a contagem automática tinha calculado."""
        ns = _ns()
        plano = {"dias_meta": 8, "data_inicio": "2026-08-14",
                 "dia_ciclo_ancora": {"dia": 2, "data": "2026-08-17"}}
        self.assertEqual(ns["data_do_dia_do_ciclo"](plano, 2, PREGAO_NOTURNO),
                         _d("2026-08-17"))
        self.assertEqual(ns["data_do_dia_do_ciclo"](plano, 3, PREGAO_NOTURNO),
                         _d("2026-08-18"))
        # para trás também, e pulando o sábado
        self.assertEqual(ns["data_do_dia_do_ciclo"](plano, 1, PREGAO_NOTURNO),
                         _d("2026-08-16"))

    def test_sem_referencia_nenhuma_devolve_None(self):
        """Sem início de ciclo não dá para saber que data é o dia 2. Melhor
        dizer isso do que gravar dinheiro num dia chutado."""
        ns = _ns()
        self.assertIsNone(ns["data_do_dia_do_ciclo"]({}, 2, PREGAO_NOTURNO))
        self.assertIsNone(ns["data_do_dia_do_ciclo"](
            {"data_inicio": "2026-08-14"}, 0, PREGAO_NOTURNO))
        self.assertIsNone(ns["data_do_dia_do_ciclo"](
            {"data_inicio": "2026-08-14"}, "x", PREGAO_NOTURNO))


class TestAMarcaDeCadaDia(unittest.TestCase):
    """17/08: "repare que o dia 2, mesmo após eu ter incluso manualmente, se eu
    clicar no dia 3 para preenchimento a partir de agora, o dia dois fica como
    se não tivesse operado".

    A marca vinha de UMA conta: lucro ACUMULADO do ciclo contra a meta
    acumulada até aquele dia. Ela nunca soube responder "eu operei neste dia?"
    — só "o ciclo está em dia?". Um dia lucrativo saía com ❌ porque o
    acumulado ainda estava atrás, e um dia sem operar saía igual a um dia de
    prejuízo."""

    def _marca(self):
        from harness import fonte_do_arquivo
        return fonte_do_arquivo()

    def test_a_marca_olha_o_DIA_e_nao_o_acumulado(self):
        fonte = self._marca()
        i = fonte.index("def _marca_do_dia")
        bloco = fonte[i:i + 2200]
        self.assertIn("por_dia", bloco)
        self.assertNotIn('stats["lucro_usd"]', bloco,
                         "a marca voltou a ser deduzida do acumulado do ciclo")

    def test_dia_sem_operacao_nao_leva_X(self):
        """Ausência não é derrota. Foi exatamente esta a queixa."""
        fonte = self._marca()
        i = fonte.index("def _marca_do_dia")
        bloco = fonte[i:i + 2200]
        j = bloco.index("if resultado is None:")
        self.assertIn('return "⬜", None', bloco[j:j + 400])

    def test_a_marca_DELE_ganha_da_deducao(self):
        """Uma marca que ele clicou não pode ser sobrescrita por dedução —
        foi para isso que ele clicou."""
        fonte = self._marca()
        i = fonte.index("def _marca_do_dia")
        bloco = fonte[i:i + 2200]
        pos_estado = bloco.index('estado = marcados.get(str(dia))')
        pos_hoje = bloco.index('if dia == dia_atual:')
        self.assertLess(bloco.index('if estado == "nao_operei":'), pos_hoje,
                        "a dedução passou na frente da marca dele")
        self.assertLess(pos_estado, pos_hoje)

    def test_o_menu_do_dia_tem_as_tres_coisas_que_ele_pediu(self):
        fonte = self._marca()
        i = fonte.index("def _menu_do_dia")
        bloco = fonte[i:i + 3000]
        self.assertIn("_escolher_dia_do_ciclo", bloco)    # hoje é este dia
        self.assertIn("_lancar_resultado_do_dia", bloco)  # resultado em US$
        self.assertIn('"concluido"', bloco)               # concluído
        self.assertIn('"nao_operei"', bloco)              # ou não

    def test_marcar_grava_em_disco_e_redesenha(self):
        fonte = self._marca()
        i = fonte.index("def _marcar_dia")
        bloco = fonte[i:i + 1200]
        self.assertIn("_gravar_plano_silencioso", bloco)
        self.assertIn("_atualizar_dashboard(forcar=True)", bloco)
