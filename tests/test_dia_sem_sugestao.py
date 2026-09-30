"""O DIA INTEIRO SEM UMA SUGESTÃO — E NÃO FOI O MERCADO.

03/09. Ele: "sinceramente, acho que tem algo errado, o dia inteiro, várias
oportunidades nítidas, porém, nenhuma sugestão".

Vinte e nove ciclos entre 09:45 e 12:15. Vinte e sete leituras de BUY. ZERO
sugestões. A conta do dia estava escrita no log, linha por linha, e ninguém
somou as três:

    a IA lê 62% a 75%   →   o aprendizado desconta 10 a 12   →   o piso pede 70%

Não existia número que a IA pudesse emitir e passar. O motor estava morto por
aritmética, e as travas de mercado (stop, distância da entrada, R:R) nem
chegaram a opinar na maioria dos ciclos.

E o desconto vinha de CINCO operações fechadas — as mesmas cinco sobre as quais
o relatório de acerto, no mesmo minuto e na mesma tela de arranque, dizia:
"AMOSTRA PEQUENA: 5 de 20 ... o número está aqui para ser acompanhado, NÃO PARA
SER USADO AINDA".

Três defeitos, e este arquivo tranca os três:

  1. taxa crua de amostra minúscula virando veredito (1/4 = -10 pontos);
  2. as MESMAS operações contadas três vezes, porque uma operação leva vários
     rótulos de confluência e os descontos eram SOMADOS;
  3. o balanço culpando "o mercado" e o piso de qualidade, sem mencionar que
     seis cenários morreram por stop fora da faixa e quatro por entrada longe.
"""

import unittest

from harness import carregar, fonte_do_arquivo, funcao_inteira


def _ns(**stubs):
    base = {"carregar_performance": lambda: [],
            # Nos testes as confluências já chegam com o rótulo canônico, então
            # normalizar é identidade. O `_normalizar_padrao` de verdade tem
            # teste próprio; aqui o assunto é a ARITMÉTICA do ajuste.
            "_normalizar_padrao": lambda t: str(t).strip()}
    base.update(stubs)
    return carregar(
        ["taxa_encolhida", "ajuste_por_aprendizado", "aprendizado_pode_vetar",
         "AJUSTE_APRENDIZADO_MAX", "AMOSTRA_MINIMA_APRENDIZADO",
         "PESO_DA_DUVIDA_APRENDIZADO", "AMOSTRA_MINIMA_ACERTO"],
        stubs=base)


# ======================================================================
#  1) UMA AMOSTRA MINÚSCULA NÃO É UM VEREDITO
# ======================================================================
class TestATaxaEncolhePelaIgnorancia(unittest.TestCase):

    def test_amostra_minuscula_fica_perto_de_50(self):
        """1 acerto em 4 não é '25% de acerto'. É uma moeda que caiu cara uma
        vez em quatro — o intervalo de confiança vai de ~1% a ~81%."""
        ns = _ns()
        self.assertAlmostEqual(ns["taxa_encolhida"](1, 4), 42.857, places=2)

    def test_amostra_grande_devolve_quase_a_taxa_crua(self):
        """É assim que a medida vira regra: devagar, conforme os dados chegam.
        Com 100 operações o peso da dúvida responde por menos de 10% da conta."""
        ns = _ns()
        self.assertGreater(ns["taxa_encolhida"](25, 100), 27.0)
        self.assertLess(ns["taxa_encolhida"](25, 100), 30.0)

    def test_padrao_perfeito_com_amostra_grande_chega_perto_de_100(self):
        ns = _ns()
        self.assertGreater(ns["taxa_encolhida"](200, 200), 95.0)

    def test_amostra_zero_devolve_a_moeda_honesta(self):
        ns = _ns()
        for v, n in ((0, 0), (0, None), (None, None), ("x", "y")):
            self.assertEqual(ns["taxa_encolhida"](v, n), 50.0)

    def test_mais_vitorias_que_amostras_nao_estoura(self):
        """Registro torto não pode virar bônus de 120%."""
        ns = _ns()
        self.assertLessEqual(ns["taxa_encolhida"](99, 4), 100.0)


# ======================================================================
#  2) AS MESMAS QUATRO OPERAÇÕES NÃO CONTAM TRÊS VEZES
# ======================================================================
class TestOsPadroesEntramPelaMEDIA(unittest.TestCase):
    """'order block', 'premium/discount' e 'varredura de liquidez' apareciam os
    três com "25% (1/4)" — porque são rótulos das MESMAS quatro operações
    fechadas, cada uma marcada com várias confluências. Os descontos eram
    SOMADOS: -10 -10 -10 = -30, e só o teto de 12 segurava.

    Somar exige evidências INDEPENDENTES. Estas não são: é a mesma amostra
    vista de três ângulos. A média é a estimativa; a soma é contar o mesmo
    dinheiro três vezes."""

    def _com_padroes(self, *trios):
        bons = [t for t in trios if t[3] >= 50]
        ruins = [t for t in trios if t[3] < 50]
        return _ns(aprendizado_por_padrao=lambda **_k: (bons, ruins, []))

    def test_tres_padroes_ruins_nao_somam_o_desconto(self):
        ns = self._com_padroes(
            ("order block", 1, 4, 25.0),
            ("premium/discount + OTE", 1, 4, 25.0),
            ("varredura de liquidez (sweep)", 1, 4, 25.0))
        delta, porques = ns["ajuste_por_aprendizado"](
            ["order block", "premium/discount + OTE",
             "varredura de liquidez (sweep)"])
        self.assertEqual(len(porques), 3, "os três continuam sendo EXPLICADOS")
        # Um sozinho vale -2,9. Os três juntos têm de valer o mesmo, não -8,6.
        um_so = self._com_padroes(("order block", 1, 4, 25.0))
        delta_um, _ = um_so["ajuste_por_aprendizado"](["order block"])
        self.assertAlmostEqual(delta, delta_um, places=1)

    def test_o_desconto_de_1_em_4_e_pequeno_e_nao_um_veto(self):
        """O número que matou o pregão de 03/09 era -10. Com a mesma amostra,
        agora é menos de -4: nudge, não veto."""
        ns = self._com_padroes(("order block", 1, 4, 25.0))
        delta, _ = ns["ajuste_por_aprendizado"](["order block"])
        self.assertLess(abs(delta), 4.0)
        self.assertLess(delta, 0.0, "continua sendo negativo — o sinal é real")

    def test_padrao_ruim_com_amostra_GRANDE_desconta_de_verdade(self):
        """O aprendizado não foi desligado: quando há dados, ele morde."""
        ns = self._com_padroes(("order block", 20, 100, 20.0))
        delta, _ = ns["ajuste_por_aprendizado"](["order block"])
        self.assertLess(delta, -8.0)

    def test_padrao_bom_com_amostra_grande_soma(self):
        ns = self._com_padroes(("order block", 80, 100, 80.0))
        delta, _ = ns["ajuste_por_aprendizado"](["order block"])
        self.assertGreater(delta, 8.0)

    def test_a_hora_soma_a_parte_porque_e_outro_eixo(self):
        """'que padrão é este' e 'que hora do dia é esta' são medidos em
        operações diferentes — aí somar é legítimo."""
        ns = _ns(aprendizado_por_padrao=lambda **_k: (
            [], [("order block", 20, 100, 20.0)], [("14", 10, 100, 10.0)]))
        so_padrao, _ = ns["ajuste_por_aprendizado"](["order block"])
        com_hora, porques = ns["ajuste_por_aprendizado"](["order block"], hora="14")
        self.assertLess(com_hora, so_padrao)
        self.assertTrue(any("horário" in p for p in porques))

    def test_o_teto_continua_valendo(self):
        ns = _ns(aprendizado_por_padrao=lambda **_k: (
            [], [("order block", 0, 500, 0.0)], [("14", 0, 500, 0.0)]))
        delta, _ = ns["ajuste_por_aprendizado"](["order block"], hora="14")
        self.assertGreaterEqual(delta, -ns["AJUSTE_APRENDIZADO_MAX"])

    def test_sem_historico_nao_mexe_em_nada(self):
        ns = _ns(aprendizado_por_padrao=lambda **_k: ([], [], []))
        self.assertEqual(ns["ajuste_por_aprendizado"](["order block"]), (0.0, []))

    def test_confluencia_desconhecida_e_ignorada(self):
        ns = self._com_padroes(("order block", 1, 4, 25.0))
        delta, porques = ns["ajuste_por_aprendizado"](["coisa que nunca vi"])
        self.assertEqual((delta, porques), (0.0, []))


# ======================================================================
#  3) O DESCONTO NÃO VETA SOZINHO ENQUANTO A AMOSTRA NÃO SUSTENTA
# ======================================================================
class TestAContradicaoQueCustouOPregao(unittest.TestCase):
    """Na MESMA tela de arranque, no MESMO minuto:

        🎯 ACERTO DO MOTOR — 5 resolvido(s) ... AMOSTRA PEQUENA: 5 de 20 ...
           o número está aqui para ser acompanhado, NÃO PARA SER USADO AINDA.
        🧠 APRENDIZADO: probabilidade 70% → 58% (-12,0 pts pelo seu histórico)

    Um se recusava a usar a amostra de 5; o outro usava a mesma amostra para
    descontar 12 pontos de toda leitura do dia. Uma das duas estava errada, e
    não era a que se recusava."""

    def test_com_amostra_pequena_ele_NAO_pode_vetar(self):
        ns = _ns()
        for n in (0, 1, 5, 19):
            self.assertFalse(ns["aprendizado_pode_vetar"](n))

    def test_no_minimo_que_o_proprio_programa_exige_ele_passa_a_mandar(self):
        ns = _ns()
        self.assertTrue(ns["aprendizado_pode_vetar"](20))
        self.assertTrue(ns["aprendizado_pode_vetar"](200))

    def test_o_minimo_e_o_MESMO_do_relatorio_de_acerto(self):
        """Dois números diferentes para a mesma pergunta é como a contradição
        nasce. Se um dia mudarem, têm de mudar juntos."""
        ns = _ns()
        self.assertEqual(ns["aprendizado_pode_vetar"].__defaults__[0],
                         ns["AMOSTRA_MINIMA_ACERTO"])

    def test_entrada_torta_nao_libera_o_veto(self):
        ns = _ns()
        for n in (None, "muitas", [], {}):
            self.assertFalse(ns["aprendizado_pode_vetar"](n))

    def test_a_regra_ESTA_LIGADA_no_motor(self):
        """Função que existe e não é chamada não conserta pregão nenhum."""
        fonte = fonte_do_arquivo()
        self.assertIn("aprendizado_pode_vetar(_fechados)", fonte)
        i = fonte.index("aprendizado_pode_vetar(_fechados)")
        trecho = fonte[i:i + 700]
        self.assertIn("probabilidade = probabilidade_ia", trecho,
                      "volta para a leitura crua")
        self.assertIn("PROBABILIDADE_MINIMA", trecho)

    def test_ela_so_age_quando_o_desconto_foi_o_UNICO_culpado(self):
        """Se a leitura crua já não passava, não há o que devolver — e mexer
        ali seria aprovar cenário que o piso recusou por conta própria."""
        fonte = fonte_do_arquivo()
        i = fonte.index("aprendizado_pode_vetar(_fechados)")
        trecho = fonte[max(0, i - 300):i + 400]
        self.assertIn("_delta < 0", trecho)
        self.assertIn("probabilidade_ia >= PROBABILIDADE_MINIMA", trecho)
        self.assertIn("probabilidade < PROBABILIDADE_MINIMA", trecho)


# ======================================================================
#  4) O BALANÇO APONTAVA PARA O LUGAR ERRADO
# ======================================================================
class TestOBalancoDizONDEODiaFoiEmbora(unittest.TestCase):

    def test_o_balanco_conta_os_outros_motivos(self):
        """Ele lia 'é o mercado não pagando o que o seu plano exige' e ia
        mexer no piso — enquanto seis cenários daquela manhã morreram por stop
        fora da faixa e quatro por entrada longe demais, dois motivos que o
        balanço não conhecia."""
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_registrar_descarte_qualidade")
        self.assertIn("_motivos_do_descarte", corpo)
        self.assertIn("motivos que o piso não alcança", corpo)

    def test_os_dois_descartes_de_MERCADO_sao_contados(self):
        fonte = fonte_do_arquivo()
        self.assertIn('"stop fora da faixa do contrato"', fonte)
        self.assertIn('"entrada longe demais do preço"', fonte)
        self.assertEqual(fonte.count("self._contar_motivo_do_descarte("), 2)

    def test_o_balanco_diz_quantos_o_APRENDIZADO_derrubou_sozinho(self):
        """A linha que teria salvado o dia dele: 'N destes passariam no seu
        piso pela leitura crua e caíram pela MINHA correção'."""
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_registrar_descarte_qualidade")
        self.assertIn("so_aprendizado", corpo)
        self.assertIn("leitura CRUA", corpo)
        self.assertIn("não é o mercado", corpo)

    def test_a_primeira_recusa_ja_avisa_quando_a_culpa_e_minha(self):
        corpo = funcao_inteira(fonte_do_arquivo(),
                               "_registrar_descarte_qualidade")
        i = corpo.index('atual.pop("primeira"')
        self.assertIn("so_o_aprendizado", corpo[i:i + 800])

    def test_o_motor_calcula_se_foi_SO_o_aprendizado(self):
        fonte = fonte_do_arquivo()
        self.assertIn("_so_o_aprendizado = bool(", fonte)
        i = fonte.index("_so_o_aprendizado = bool(")
        trecho = fonte[i:i + 400]
        self.assertIn("rr_sinal >= RR_MINIMO", trecho,
                      "R:R ruim não é culpa do aprendizado")


# ======================================================================
#  5) "COMO ELE PODE ESTAR ANALISANDO BANDAS DE BOLLINGER?"
# ======================================================================
class TestOsIndicadoresPodemEstarPRESOSNumaVelaAntiga(unittest.TestCase):
    """A pergunta dele, no mesmo dia: "como ele pode estar analisando bandas de
    bollinger se não tem esse indicador no gráfico?".

    No print há uma caixa de dados FIXADA numa vela, carimbada
    "03/09/2026 08:05", com UPPER · LOWER · SMA · RSI · MIDDLE · OVERBOU ·
    OVERSOL · OPEN/HIGH/LOW/CLOSE · VOLUME. É o tooltip do cursor, preso — não
    é indicador desenhado, e não é o estado de AGORA. O modelo lia aquela caixa
    e reportava como "indicadores que enxerguei no gráfico".

    E estavam congelados. Entre 10:45 e 11:10 daquela manhã, quatro leituras:

        SMA 7672.80 · RSI 67 · OPEN 7675.75 · HIGH 7679.00 · CLOSE 7679.00
        SMA 7672.80 · RSI 67 · OPEN 7675.75 · HIGH 7679.00 · CLOSE 7679.00
        SMA 7672.80 ...

    Vinte e cinco minutos, os mesmos números, com o preço indo de 7723 a 7703.
    São os valores da vela das 08:05 — três horas antes — entrando na análise
    como se fossem o mercado de agora. Mesma família do CVD inventado que saiu
    daqui em 23/08: um número que PARECE medida e não é."""

    def _ns(self):
        return carregar(["indicadores_congelados", "numeros_dos_indicadores",
                         "LEITURAS_PARA_CONGELADO", "_RE_NUMERO_DO_INDICADOR"])

    def test_o_caso_real_de_03_09_e_pego(self):
        ns = self._ns()
        congelado = ["Upper 7687.97", "Lower 7663.15", "SMA 7672.80", "RSI 67"]
        preso, quantas, _ = ns["indicadores_congelados"](
            [(congelado, 7723.5), (congelado, 7712.25), (congelado, 7703.5)])
        self.assertTrue(preso)
        self.assertEqual(quantas, 3)

    def test_o_TEXTO_pode_mudar_que_os_NUMEROS_denunciam(self):
        """Quem escreve a linha é um modelo de linguagem: 'Bandas de Bollinger
        (Upper, Lower)' vira 'Upper Band · Lower Band' de um ciclo para o
        outro. Os números, não."""
        ns = self._ns()
        preso, _q, _n = ns["indicadores_congelados"]([
            (["Bandas de Bollinger (Upper 7687.97, Lower 7663.15)"], 7723.5),
            (["Upper Band 7687.97 · Lower Band 7663.15"], 7712.25),
            (["UPPER 7687.97 / LOWER 7663.15"], 7703.5)])
        self.assertTrue(preso)

    def test_numeros_que_MUDAM_nao_sao_congelados(self):
        ns = self._ns()
        preso, _q, _n = ns["indicadores_congelados"]([
            (["SMA 7672.80"], 7723.5),
            (["SMA 7675.10"], 7712.25),
            (["SMA 7679.40"], 7703.5)])
        self.assertFalse(preso)

    def test_mercado_PARADO_nao_e_acusado_de_tela_presa(self):
        """Se o preço não andou, números iguais podem ser só um minuto
        tranquilo. Acusar defeito aí seria inventar defeito — o oposto do que
        esta função existe para fazer."""
        ns = self._ns()
        iguais = ["SMA 7672.80", "RSI 67"]
        preso, _q, _n = ns["indicadores_congelados"](
            [(iguais, 7700.0), (iguais, 7700.0), (iguais, 7700.0)])
        self.assertFalse(preso)

    def test_duas_leituras_ainda_nao_bastam(self):
        ns = self._ns()
        iguais = ["SMA 7672.80"]
        preso, _q, _n = ns["indicadores_congelados"](
            [(iguais, 7723.5), (iguais, 7703.5)])
        self.assertFalse(preso)

    def test_indicadores_SEM_numero_nao_disparam_alarme(self):
        """'RSI · Bandas de Bollinger', sem valores, é a mesma frase toda vez e
        não prova nada sobre congelamento."""
        ns = self._ns()
        sem_numero = ["RSI", "Bandas de Bollinger", "Order Blocks verdes"]
        preso, _q, _n = ns["indicadores_congelados"](
            [(sem_numero, 7723.5), (sem_numero, 7712.0), (sem_numero, 7703.5)])
        self.assertFalse(preso)

    def test_lista_vazia_ou_curta_nao_explode(self):
        ns = self._ns()
        for h in (None, [], [(["SMA 1"], 1.0)]):
            self.assertEqual(ns["indicadores_congelados"](h)[0], False)

    def test_virgula_decimal_e_ponto_decimal_sao_o_mesmo_numero(self):
        ns = self._ns()
        self.assertEqual(ns["numeros_dos_indicadores"](["SMA 7672,80"]),
                         ns["numeros_dos_indicadores"](["SMA 7672.80"]))

    def test_o_alarme_ESTA_LIGADO_no_ciclo_de_analise(self):
        fonte = fonte_do_arquivo()
        self.assertIn("indicadores_congelados(_fila)", fonte)
        i = fonte.index("indicadores_congelados(_fila)")
        trecho = fonte[i:i + 1600]
        self.assertIn("caixa de dados do cursor", trecho)
        self.assertIn("PRESA numa vela antiga", trecho)

    def test_o_aviso_sai_UMA_vez_por_ativo(self):
        """A cada ciclo seria a linha repetida que esconde o resto do log."""
        fonte = fonte_do_arquivo()
        i = fonte.index("indicadores_congelados(_fila)")
        self.assertIn("_avisou_congelado", fonte[i:i + 1800])

    def test_e_o_aviso_RESSUSCITA_quando_a_tela_destrava(self):
        """Sem isto, ele fecha a caixa, o problema some e o robô nunca mais
        avisaria se ela fosse fixada de novo."""
        fonte = fonte_do_arquivo()
        i = fonte.index("indicadores_congelados(_fila)")
        trecho = fonte[i:i + 2000]
        self.assertIn("_avisou_congelado.pop", trecho)


if __name__ == "__main__":
    unittest.main(verbosity=2)
