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
        bloco = fonte[i:i + 4600]
        self.assertIn("salvar_plano_da_conta(self.plano)", bloco)
        self.assertNotIn("self.salvar_plano_trading()", bloco)

    def test_o_clique_forca_o_redesenho(self):
        """A assinatura do painel olha posições, configuração, sinais e
        desempenho — NÃO olha o arquivo do plano. Sem forcar=True o clique
        gravava e a tela não mudava na frente dele."""
        fonte = self._fonte()
        i = fonte.index("def _escolher_dia_do_ciclo")
        bloco = fonte[i:i + 4600]
        self.assertIn("_atualizar_dashboard(forcar=True)", bloco)

    def test_clicar_no_dia_aceso_desfaz(self):
        """Sem desfazer, um clique errado seria permanente."""
        fonte = self._fonte()
        i = fonte.index("def _escolher_dia_do_ciclo")
        bloco = fonte[i:i + 4600]
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
        bloco = fonte[i:i + 4200]
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

    def test_o_menu_do_dia_tem_tudo_o_que_ele_pediu(self):
        fonte = self._marca()
        i = fonte.index("def _menu_do_dia")
        bloco = fonte[i:i + 5200]
        self.assertIn("_escolher_dia_do_ciclo", bloco)      # hoje é este dia
        self.assertIn("_lancar_resultado_do_dia", bloco)    # resultado em US$
        self.assertIn('"concluido"', bloco)                 # concluído
        self.assertIn('"nao_operei"', bloco)                # ou não
        self.assertIn("_apagar_lancamentos_do_dia", bloco)  # e desfazer

    def test_marcar_grava_em_disco_e_redesenha(self):
        fonte = self._marca()
        i = fonte.index("def _marcar_dia")
        bloco = fonte[i:i + 2400]
        self.assertIn("_gravar_plano_silencioso", bloco)
        self.assertIn("_atualizar_dashboard(forcar=True)", bloco)

    def test_nao_operei_num_dia_COM_resultado_avisa(self):
        """No print de 17/08 o D1 estava marcado 'não operei' e mostrava +924
        no mesmo quadradinho. A ferramenta aceitava calada."""
        fonte = self._marca()
        i = fonte.index("def _marcar_dia")
        bloco = fonte[i:i + 2400]
        self.assertIn('if estado == "nao_operei":', bloco)
        self.assertIn("os dois não batem", bloco)


class TestApagarOValorLancado(unittest.TestCase):
    """17/08, 21:29: "adicione ali a opção de apagar o valor incluído também,
    não tem a opção de desfazer (apagar), adicione por favor".

    Estava certo: dava para pôr dinheiro no dia e não dava para tirar. E um
    valor lançado errado não fica quieto — ele entra na média por dia, no
    ritmo exigido, na projeção e na chance da meta. Sem desfazer, o único
    jeito de corrigir era reiniciar o ciclo inteiro, perdendo o que estava
    certo junto com o que estava errado."""

    def _fonte(self):
        from harness import fonte_do_arquivo
        return fonte_do_arquivo()

    def test_so_apaga_LANCAMENTO_e_nunca_operacao_real(self):
        """No mesmo dia convivem sugestões acatadas e posições lidas da
        corretora. Um desfazer que apagasse operação real seria bem pior que
        não ter desfazer nenhum. A checagem de origem é refeita na hora de
        apagar, e não só na hora de listar."""
        fonte = self._fonte()
        i = fonte.index("def apagar_lancamentos_do_dia")
        bloco = fonte[i:i + 1400]
        self.assertIn('p.get("origem") == "RESULTADO_DIA"', bloco)
        j = fonte.index("def lancamentos_do_dia")
        listar = fonte[j:j + 1600]
        self.assertIn('pos.get("origem") != "RESULTADO_DIA"', listar)
        self.assertIn('pos.get("conta_id") != conta', listar,
                      "apagaria lançamento de outra conta")

    def test_a_confirmacao_MOSTRA_o_que_vai_sair(self):
        """Apagar dinheiro do diário sem mostrar o que se está apagando é o
        tipo de botão que ninguém deveria clicar com confiança."""
        fonte = self._fonte()
        i = fonte.index("def _apagar_lancamentos_do_dia")
        bloco = fonte[i:i + 2800]
        self.assertIn("askyesno", bloco)
        self.assertIn("Total que sai do diário", bloco)
        self.assertIn("data_criacao", bloco, "não mostra quando foi lançado")

    def test_da_para_apagar_so_o_ULTIMO(self):
        """Lançou +54 e depois +900 por engano: apagar tudo e redigitar seria
        obrigá-lo a refazer o que estava certo."""
        fonte = self._fonte()
        i = fonte.index("def _apagar_lancamentos_do_dia")
        bloco = fonte[i:i + 2800]
        self.assertIn("so_o_ultimo", bloco)
        j = fonte.index("def lancamentos_do_dia")
        self.assertIn('achados.sort(key=lambda p: p.get("id") or 0)',
                      fonte[j:j + 1600],
                      "sem ordenar, 'o último' não é o último de verdade")

    def test_dia_sem_lancamento_explica_em_vez_de_apagar(self):
        """Quadradinho com valor que veio de operação real: o certo é dizer
        que aquilo não se apaga por ali, e por quê."""
        fonte = self._fonte()
        i = fonte.index("def _apagar_lancamentos_do_dia")
        bloco = fonte[i:i + 2800]
        self.assertIn("Nada lançado no dia", bloco)
        self.assertIn("posições lidas da", bloco)


class TestOLancamentoQueNaoAparecia(unittest.TestCase):
    """17/08, 21:29: "lancei, mas nao esta atualizando la no relatorio, no
    resultado do dia!!"

    Ele estava certo, e o defeito era meu — introduzido na versao anterior.

    Um registro de posicao tem DUAS datas com trabalhos diferentes:
        data_criacao    -> QUANDO o registro foi feito. `_dentro_do_ciclo`
                           usa ela: data_criacao >= ciclo_inicio.
        data_fechamento -> A QUE PREGAO o resultado pertence.
                           `resultados_por_dia` agrupa por ela.

    Eu tinha posto o CARIMBO DO PREGAO nas duas. Resultado: um lancamento
    feito as 21:29, num ciclo iniciado as 21:00, nascia com data_criacao
    19:01 — ANTES do proprio ciclo. `posicoes_do_ciclo` o descartava e o
    Resultado do dia ficava US$ 0,00 com o dinheiro gravado no disco.

    Pior que sumir: o menu do dia CONTINUAVA mostrando o lancamento (ele le o
    disco direto, sem filtro de ciclo). A ferramenta afirmava duas coisas
    contrarias na mesma tela.
    """

    def test_as_duas_datas_nao_podem_ser_a_mesma(self):
        fonte = self._fonte()
        i = fonte.index("def lancar_resultado_do_dia")
        bloco = fonte[i:i + 4200]
        self.assertIn('"data_fechamento": carimbo', bloco,
                      "o dia do pregao tem de vir do carimbo")
        self.assertIn("\"data_criacao\": time.strftime", bloco,
                      "data_criacao voltou a ser o carimbo — o lancamento "
                      "nasce de novo fora do proprio ciclo")

    def _fonte(self):
        from harness import fonte_do_arquivo
        return fonte_do_arquivo()

    def test_o_resgate_so_toca_no_que_tem_a_assinatura_do_defeito(self):
        """Mexer no diario de alguem exige precisao. A faxina so pega:
        origem RESULTADO_DIA, com data_criacao IGUAL a data_fechamento, e
        cujo pregao cai dentro do ciclo da conta."""
        fonte = self._fonte()
        i = fonte.index("def consertar_lancamentos_fora_do_ciclo")
        bloco = fonte[i:i + 4600]
        self.assertIn('pos.get("origem") != "RESULTADO_DIA"', bloco)
        self.assertIn("criacao != fechamento", bloco,
                      "sem a assinatura, a faxina mexeria em registro sadio")
        self.assertIn("dt.date() < partida", bloco,
                      "puxaria lancamento de ciclo ANTERIOR para o ciclo de "
                      "agora — isso seria inventar resultado")

    def test_o_resgate_e_DITO_no_registro(self):
        """Mexer no diario em silencio e pior que deixar o defeito."""
        fonte = self._fonte()
        i = fonte.index("def _resgatar_lancamentos_fora_do_ciclo")
        bloco = fonte[i:i + 2000]
        self.assertIn("Total devolvido ao ciclo", bloco)
        self.assertIn("apague pelo menu do dia", bloco)

    def test_o_resgate_roda_na_abertura(self):
        fonte = self._fonte()
        self.assertIn("self._resgatar_lancamentos_fora_do_ciclo()", fonte)
        i = fonte.index("self._faxina_de_licoes()")
        self.assertIn("_resgatar_lancamentos_fora_do_ciclo", fonte[i:i + 200],
                      "o resgate saiu da abertura")


class TestPreencherUmNaoApagaOOutro(unittest.TestCase):
    """18/08, 14:56, palavras dele:

        "conserte o plano de trading, no mesmo menu de preenchimento dos
         dias, ta muito dificil de prenher, se prenenhcer um, apaga o outro,
         ta uma bagunaca, parare que um esta ligado ao outro"

    Ele estava certo, e a causa era do jeito que eu desenhei. Dizer "hoje é o
    dia 3" reposiciona TODO o calendário do ciclo — o dia 1 deixa de ser uma
    data e passa a ser outra. Os lançamentos ficavam presos à DATA, então o
    +433 posto no D1 reaparecia no D2 no clique seguinte e o D1 ficava vazio.

    No log do motor dele há DEZ desses cliques em sequência (dia 2, 4, 5, 6,
    8, 2, 3, 2...). É alguém tentando fazer a conta fechar contra uma
    ferramenta que embaralhava a cada tentativa.
    """

    def _fonte(self):
        from harness import fonte_do_arquivo
        return fonte_do_arquivo()

    def test_o_lancamento_segue_o_NUMERO_do_dia(self):
        fonte = self._fonte()
        i = fonte.index("def remapear_lancamentos_para_o_novo_dia")
        bloco = fonte[i:i + 3600]
        self.assertIn("dia_do_ciclo_de_uma_data", bloco,
                      "não descobre a que dia o lançamento pertencia")
        self.assertIn("data_do_dia_do_ciclo(plano_depois, dia", bloco,
                      "não recarimba para a nova data do MESMO dia")

    def test_operacao_REAL_nunca_se_move(self):
        """Ela é um fato sobre uma data. Reescrevê-la seria falsificar o
        histórico para caber num rótulo."""
        fonte = self._fonte()
        i = fonte.index("def remapear_lancamentos_para_o_novo_dia")
        bloco = fonte[i:i + 3600]
        self.assertIn('pos.get("origem") != "RESULTADO_DIA"', bloco)

    def test_o_clique_no_dia_CHAMA_o_remapeamento(self):
        """A função certa não serve de nada se o clique não a usar."""
        fonte = self._fonte()
        i = fonte.index("def _escolher_dia_do_ciclo")
        bloco = fonte[i:i + 3600]
        self.assertIn("plano_antes = dict(self.plano)", bloco,
                      "não guarda o mapa ANTIGO antes de mexer")
        self.assertIn("remapear_lancamentos_para_o_novo_dia", bloco)
        # E tem de dizer o que moveu: mexer no diário em silêncio é pior.
        self.assertIn("junto com o", bloco)

    def test_o_quadradinho_mostra_a_DATA(self):
        """Sem a data à vista, 'dia 2' é um rótulo sem âncora: ele clicava, o
        mapa inteiro se movia, e não havia como ver o que tinha mudado."""
        fonte = self._fonte()
        i = fonte.index("def _renderizar_trilha")
        bloco = fonte[i:i + 4600]
        self.assertIn("data_do_dia_do_ciclo(self.plano, dia)", bloco)
        self.assertIn("strftime('%d/%m')", bloco)

    def test_a_volta_da_data_para_o_dia_confere_com_a_ida(self):
        ns = _ns()
        carregar_extra = carregar(
            ["dias_meta_do_plano", "_domingo_e_pregao", "dias_de_pregao_entre",
             "dia_do_ciclo", "_passo_de_pregao", "data_do_dia_do_ciclo",
             "dia_do_ciclo_de_uma_data"],
            stubs={"plano_da_conta_ativa": lambda: {},
                   "carregar_config": lambda: PREGAO_NOTURNO,
                   "PADRAO_CONFIG_APP": PREGAO_NOTURNO, "datetime": datetime})
        plano = {"dias_meta": 8, "data_inicio": "2026-08-14"}
        for n in range(1, 9):
            data = ns["data_do_dia_do_ciclo"](plano, n, PREGAO_NOTURNO)
            self.assertEqual(
                carregar_extra["dia_do_ciclo_de_uma_data"](
                    plano, data, PREGAO_NOTURNO), n)
        # data fora do prazo do ciclo não pertence a dia nenhum
        self.assertIsNone(carregar_extra["dia_do_ciclo_de_uma_data"](
            plano, _d("2026-12-31"), PREGAO_NOTURNO))


class TestAEsperaDoPrint(unittest.TestCase):
    """18/08, 14:53 → 14:58: cinco minutos sem resposta a "tira um print".

    "está muito lento para pensar" — e a causa era uma regra minha que
    tratava TODO anexo como vídeo: 300 s por chamada e teto de tempo do turno
    DESLIGADO. Nove modelos nessas condições dão quarenta e cinco minutos de
    espera possível, sem nada na tela.

    Faz sentido para vídeo, que sobe e processa. Não faz nenhum para o print
    de um gráfico, que vai embutido na mensagem e tem alguns KB."""

    def _fonte(self):
        from harness import fonte_do_arquivo
        return fonte_do_arquivo()

    def test_imagem_e_video_sao_coisas_diferentes(self):
        fonte = self._fonte()
        self.assertIn("def anexo_e_imagem(anexo)", fonte)
        i = fonte.index("def anexo_e_imagem")
        self.assertIn("EXTENSOES_DE_IMAGEM", fonte[i:i + 400])

    def test_o_print_tem_teto_e_o_video_nao(self):
        fonte = self._fonte()
        i = fonte.index("inicio_espera = time.time()")
        bloco = fonte[i:i + 900]
        self.assertIn("ORCAMENTO_CHAT_IMAGEM_SEG", bloco)
        self.assertIn("orcamento = None", bloco)

    def test_o_teto_da_imagem_e_maior_que_o_de_texto_e_finito(self):
        """A visão é mais lenta que texto — o teto tem de ser maior. Mas
        continua tendo fim, senão volta o silêncio de cinco minutos."""
        ns = carregar(["ORCAMENTO_CHAT_SEG", "ORCAMENTO_CHAT_IMAGEM_SEG",
                       "TIMEOUT_CHAT_MS", "TIMEOUT_CHAT_IMAGEM_MS"])
        self.assertGreater(ns["ORCAMENTO_CHAT_IMAGEM_SEG"],
                           ns["ORCAMENTO_CHAT_SEG"])
        self.assertLessEqual(ns["ORCAMENTO_CHAT_IMAGEM_SEG"], 180)
        self.assertLess(ns["TIMEOUT_CHAT_IMAGEM_MS"], 300_000)


class TestOsIndicadoresDaTela(unittest.TestCase):
    """18/08: "treine a ferramenta para se atentar e analisar sempre os novos
    indicadores", logo depois de "tira um print, se atenta nesse indicador
    novo que coloquei na plataforma tradovate".

    A instrução já existia no prompt, mas frouxa ("use-os como confluência
    adicional"). Neste projeto a regra é que prompt é PEDIDO, não garantia —
    o que vale é o que dá para conferir."""

    def _fonte(self):
        from harness import fonte_do_arquivo
        return fonte_do_arquivo()

    def test_ela_precisa_LISTAR_o_que_ve(self):
        fonte = self._fonte()
        self.assertIn("indicadores_na_tela", fonte)
        self.assertIn("OS INDICADORES DA TELA SÃO PARTE DO TRABALHO", fonte)

    def test_indicador_que_ela_nao_sabe_nomear_e_DESCRITO(self):
        """Omitir o que não reconhece é o pior resultado possível: o que ele
        acabou de colocar no gráfico é justamente o que ela não conhece."""
        fonte = self._fonte()
        i = fonte.index("OS INDICADORES DA TELA SÃO PARTE DO TRABALHO")
        bloco = fonte[i:i + 1600]
        self.assertIn("POR DESCRIÇÃO", bloco)
        self.assertIn("NÃO pode ser omitido", bloco)

    def test_o_registro_MOSTRA_os_indicadores_lidos(self):
        """É assim que ele confere se o indicador novo foi enxergado, em vez
        de supor que foi."""
        fonte = self._fonte()
        self.assertIn("Indicadores que ela ENXERGOU no gráfico", fonte)
        i = fonte.index("Indicadores que ela ENXERGOU no gráfico")
        # e quando NÃO vê nada, diz isso em vez de ficar calado
        self.assertIn("não listou nenhum indicador", fonte[i - 900:i + 900])

    def test_os_indicadores_entram_na_CONVERSA(self):
        """Sem isso ela não teria como responder 'se atenta nesse indicador
        novo' — responderia sobre indicador nenhum, ou inventaria um."""
        # O RÓTULO PASSOU A DIZER DE QUAL ATIVO SÃO. Com quatro gráficos na
        # mesa, "no gráfico DELE" nomeia um gráfico que não existe — e foi
        # esse tipo de frase que fez o chat responder sobre um ativo só
        # (31/08, 16:23). A regra que importa continua a mesma: os
        # indicadores chegam ao modelo, e ele é proibido de inventar.
        fonte = self._fonte()
        self.assertIn("INDICADORES VISÍVEIS NO GRÁFICO DO", fonte)
        i = fonte.index("INDICADORES VISÍVEIS NO GRÁFICO DO")
        trecho = fonte[i:i + 800]
        self.assertIn("em vez de inventar", trecho)
        self.assertIn("DESSA janela", trecho)

    def test_o_campo_novo_NAO_pode_invalidar_a_leitura(self):
        """Se `indicadores_na_tela` entrasse nas chaves obrigatórias, o modelo
        local pequeno passaria a ter a análise inteira recusada por não emitir
        um campo novo — trocaria um problema por um pior."""
        ns = carregar(["CHAVES_DA_ANALISE"])
        self.assertNotIn("indicadores_na_tela", ns["CHAVES_DA_ANALISE"])

    def test_o_SCHEMA_da_gemini_declara_o_campo(self):
        """SEM ISTO, PEDIR NO PROMPT NÃO ADIANTA NADA — e foi o que aconteceu.

        O `response_schema` não é sugestão: o servidor do Google devolve SÓ as
        chaves declaradas ali. Eu escrevi a instrução em maiúsculas no prompt e
        esqueci do schema. A resposta voltava sem o campo, e o programa
        anunciava, ciclo após ciclo, "ela não listou nenhum indicador na tela"
        — como se fosse falha de leitura dela, quando era omissão minha.
        Prompt é PEDIDO; schema é GARANTIA."""
        fonte = self._fonte()
        i = fonte.index("SIGNAL_SCHEMA = types.Schema(")
        bloco = fonte[i:fonte.index("config_horario = carregar_config()", i)]
        self.assertIn('"indicadores_na_tela": types.Schema(', bloco,
                      "o campo não está declarado no schema — a Gemini nunca "
                      "vai devolvê-lo, por mais que o prompt peça")
        # e é OBRIGATÓRIO: assim vem sempre, nem que seja lista vazia, e
        # "vazio" passa a significar "olhei e não havia".
        j = bloco.index("required=[")
        self.assertIn("indicadores_na_tela", bloco[j:])

    def test_o_campo_e_lido_do_dicionario_QUE_EXISTE(self):
        """O defeito de 18/08, o que derrubou todo ciclo do motor dele:

            ⚠️ Erro ao analisar: name 'analise' is not defined

        Eu li o campo de `analise`, um nome que não existe naquele escopo — o
        dicionário da leitura ali se chama `sinal`. O ciclo lia o gráfico,
        imprimia as confluências e morria na linha seguinte, sem sugestão
        nenhuma. (O crivo geral está em test_nomes_indefinidos.py; aqui fica a
        linha específica, porque foi esta que quebrou.)"""
        fonte = self._fonte()
        self.assertIn('indicadores = (sinal or {}).get("indicadores_na_tela")',
                      fonte)
        self.assertNotIn('(analise or {}).get("indicadores_na_tela")', fonte)

    def test_os_indicadores_ficam_junto_da_leitura_DAQUELE_ativo(self):
        """Com dois gráficos monitorados, uma variável solta guarda sempre o
        da última janela lida — e "e o indicador novo do NQ?" responderia com
        os indicadores do MES."""
        fonte = self._fonte()
        self.assertIn('self._ultima_analise["indicadores"] = list(indicadores)',
                      fonte)
        i = fonte.index('self._ultima_analise["indicadores"]')
        self.assertIn("_analises_por_ativo", fonte[i:i + 500])
