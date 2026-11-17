# -*- coding: utf-8 -*-
"""Testes unitários das melhorias institucionais v2.85+ (18 demandas)."""

import unittest

from harness import carregar
import market_regime
import tiger_predictive
import tradovate_auto


def _ns():
    return carregar([
        "validar_coerencia_sinal_ia",
        "freio_de_sugestoes",
        "data_do_pregao",
    ])


class TestCoerenciaSinalIA(unittest.TestCase):
    """Item 1: Bloqueia contradição entre action (BUY/SELL) e geometria/texto."""

    def test_buy_com_texto_e_confluencia_bearish_e_bloqueado(self):
        ns = _ns()
        sinal = {
            "action": "BUY",
            "entry_price": 29815.0,
            "stop_loss": 29795.0,
            "take_profit_1": 29860.0,
            "confluence_factors": [
                "Order Block bearish",
                "Liquidity sweep",
                "FVG / ineficiência",
            ],
            "market_analysis": (
                "O mercado testou uma zona de resistência importante marcada por um "
                "bloco de ordens vendedoras (Order Block bearish) no topo. "
                "A entrada curta posicionada no miolo do order block aproveita a "
                "assimetria para capturar o movimento de retração. O stop loss fica "
                "protegido acima do pavio máximo da manipulação."
            ),
        }
        ok, acao_corr, motivo = ns["validar_coerencia_sinal_ia"](sinal)
        self.assertFalse(ok)
        self.assertEqual(acao_corr, "HOLD")
        self.assertIn("contradição textual", motivo)

    def test_buy_com_geometria_invertida_e_bloqueado(self):
        ns = _ns()
        sinal = {
            "action": "BUY",
            "entry_price": 7700.0,
            "stop_loss": 7710.0,      # stop ACIMA da entrada num BUY!
            "take_profit_1": 7680.0,  # alvo ABAIXO da entrada num BUY!
            "confluence_factors": ["Order Block bullish"],
            "market_analysis": "Compra no desconto.",
        }
        ok, acao_corr, motivo = ns["validar_coerencia_sinal_ia"](sinal)
        self.assertFalse(ok)
        self.assertEqual(acao_corr, "HOLD")
        self.assertIn("geometria", motivo)

    def test_buy_coerente_passa_normalmente(self):
        ns = _ns()
        sinal = {
            "action": "BUY",
            "entry_price": 7700.0,
            "stop_loss": 7690.0,
            "take_profit_1": 7725.0,
            "confluence_factors": ["Bullish Order Block", "Liquidity Sweep", "Discount Zone"],
            "market_analysis": (
                "Varreu liquidez no fundo e reagiu no Order Block comprador em desconto, "
                "com stop protegido abaixo da mínima e alvo na liquidez compradora do topo."
            ),
        }
        ok, acao_corr, motivo = ns["validar_coerencia_sinal_ia"](sinal)
        self.assertTrue(ok)
        self.assertEqual(acao_corr, "BUY")
        self.assertEqual(motivo, "")


class TestContraTendenciaForte(unittest.TestCase):
    """Item 13: Bloqueia operações contra tendência direcional forte sem reversão estrutural."""

    def test_bloqueia_compra_contra_tendencia_forte_de_baixa(self):
        info_regime = {
            "regime": market_regime.REGIME_EXPANSAO,
            "efficiency_ratio": 0.78,
            "tendencia_forte": True,
            "direcao": "BEARISH",
        }
        ok, motivo = market_regime.avaliar_contra_tendencia_forte(
            "BUY", info_regime, ["Order Block", "Discount Zone"], probabilidade=72.0
        )
        self.assertFalse(ok)
        self.assertIn("tendência forte de BAIXA", motivo)

    def test_permite_reversao_estrutural_completa_com_alta_probabilidade(self):
        info_regime = {
            "regime": market_regime.REGIME_EXPANSAO,
            "efficiency_ratio": 0.75,
            "tendencia_forte": True,
            "direcao": "BEARISH",
        }
        ok, motivo = market_regime.avaliar_contra_tendencia_forte(
            "BUY",
            info_regime,
            ["CHoCH", "Liquidity Sweep", "Bullish Order Block", "FVG"],
            probabilidade=88.0,
        )
        self.assertTrue(ok)
        self.assertEqual(motivo, "")


class TestMetaDiariaAtingidaFreio(unittest.TestCase):
    """Item 18: Para sugestões e operações ao atingir a meta diária da conta."""

    def test_freio_para_ao_atingir_meta_diaria(self):
        ns = _ns()
        plano = {
            "meta_alvo": 2500.0,
            "dias_meta": 5,  # meta diária = US$ 500.00
            "parar_na_meta_diaria": True,
            "drawdown_maximo": 1000.0,
            "max_stops_seguidos": 2,
            "max_operacoes_dia": 6,
        }
        pos_ganho = [
            {
                "id": 1,
                "conta_id": "conta_teste",
                "status": "FECHADA",
                "pnl_final": 520.0,
                "data_fechamento": f"{ns['data_do_pregao']()} 11:30",
            }
        ]
        ns["carregar_posicoes"] = lambda: pos_ganho
        pode, motivo = ns["freio_de_sugestoes"](plano, conta_id="conta_teste")
        self.assertFalse(pode)
        self.assertIn("META DO DIA ATINGIDA", motivo)
        self.assertIn("próximo pregão", motivo)


class TestBlindagemZeroDevolucao(unittest.TestCase):
    """Item 10: Modo Blindagem Zero-Devolução (0.5R) no trailing inteligente."""

    def test_modo_blindagem_arma_em_meio_r(self):
        res = tradovate_auto.plano_trailing_inteligente(
            ticks_stop=20,
            rr=2.5,
            probabilidade=75,
            contratos=2,
            valor_do_tick=1.25,
            drawdown_restante=1000.0,
            ligado=True,
            modo_r="🛡️ Blindagem Zero-Devolução (0.5R)",
            ativo="MESU6",
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["acionar"], 10)  # 0.5 * 20 ticks = 10 ticks
        self.assertLessEqual(res["stop"], 10)
        self.assertIn("zero-devolução", res["motivo"].lower())


class TestPlanoTaticoMetaMomentum(unittest.TestCase):
    """Item 8: Consultor tático de Meta & Momentum."""

    def test_meta_batida_retorna_modo_blindado(self):
        plano = {"meta_alvo": 2000.0, "dias_meta": 4, "margem": 50000.0, "risco_pct": 1.0}
        res = tiger_predictive.calcular_plano_tatico_meta_momentum(
            plano, realizado_hoje=550.0, realizado_ciclo=1200.0, dd_restante=1000.0
        )
        self.assertTrue(res["meta_diaria_batida"])
        self.assertEqual(res["postura"], "META_BATIDA_ENCERRAR_DIA")


class TestAgenteAutocorretivoETravasAntiAlucinacao(unittest.TestCase):
    """Agente Autocorretivo em tempo real com as 5 Travas Anti-Alucinação."""

    def test_repara_index_error_em_runtime_e_valida_ast(self):
        import tempfile
        from pathlib import Path
        import agent_monitor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            arq = root / "modulo_teste.py"
            codigo_defeituoso = (
                "def processar(avaliacao_matrix):\n"
                "    msg = f\"Erro: {avaliacao_matrix['alertas'][0]}\"\n"
                "    return msg\n"
            )
            arq.write_text(codigo_defeituoso, encoding="utf-8")
            agente = agent_monitor.AgenteAutocorretivoInstitucional(
                app_root=root, user_data_dir=root / "dados"
            )
            ev = agente.intervir_em_falha_runtime(
                IndexError("list index out of range"),
                local_quebra="modulo_teste.py:2",
            )
            self.assertTrue(ev["sucesso"])
            novo_codigo = arq.read_text(encoding="utf-8")
            self.assertIn(".get('alertas')", novo_codigo)
            # Testa que o código reparado não levanta mais IndexError quando alertas=[]
            ns_exec = {}
            exec(novo_codigo, ns_exec)
            self.assertEqual(ns_exec["processar"]({"alertas": []}), "Erro: ")

    def test_trava_anti_alucinacao_bloqueia_exclusao_de_funcao_ou_markdown(self):
        import agent_monitor

        orig = "def f1():\n    return 1\n\ndef f2():\n    return 2\n"
        # Tentativa de apagar f2
        sem_f2 = "def f1():\n    return 1\n"
        ok, motivo = agent_monitor.validar_patch_anti_alucinacao(orig, sem_f2)
        self.assertFalse(ok)
        self.assertIn("f2", motivo)

        # Tentativa com markdown alucinado
        com_md = "def f1():\n    return 1\n```python\ndef f2():\n    return 2\n"
        ok_md, motivo_md = agent_monitor.validar_patch_anti_alucinacao(orig, com_md)
        self.assertFalse(ok_md)
        self.assertIn("markdown", motivo_md)

    def test_trava_anti_alucinacao_bloqueia_remocao_de_simbolo_critico(self):
        import agent_monitor

        orig = "TOLERANCIA_FATO_USD = 1.0\ndef f():\n    return TOLERANCIA_FATO_USD\n"
        novo = "def f():\n    return 1.0\n"
        ok, motivo = agent_monitor.validar_patch_anti_alucinacao(orig, novo)
        self.assertFalse(ok)
        self.assertIn("TOLERANCIA_FATO_USD", motivo)


class TestAutoAprendizadoRealEMemoriaEvolutiva(unittest.TestCase):
    """Auto-Aprendizado Real Bayesiano + EWMA + Shadow Book + Travas Anti-Alucinação."""

    def test_trava_anti_eco_bloqueia_bonus_apos_dois_stops_seguidos(self):
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            mem = tiger_predictive.MemoriaEvolutivaMercado(
                os.path.join(tmp, "mem.json")
            )
            # Histórico antigo positivo (5 wins)
            for _ in range(5):
                mem.registrar_resultado_verificado(
                    "NQZ6", "SELL", "WIN", rr_obtido=2.0,
                    entry=27350.0, stop=27370.0, tp1=27310.0
                )
            # Últimos 2 deram LOSS (stop)
            mem.registrar_resultado_verificado(
                "NQZ6", "SELL", "LOSS", entry=27350.0, stop=27370.0, tp1=27310.0
            )
            mem.registrar_resultado_verificado(
                "NQZ6", "SELL", "LOSS", entry=27350.0, stop=27370.0, tp1=27310.0
            )
            cal = mem.calibrar_probabilidade_real(78.0, "NQZ6", "SELL")
            self.assertTrue(cal["trava_anti_eco_acionada"])
            self.assertLess(cal["probabilidade_ajustada"], 78.0)

    def test_aprendizado_contrafactual_shadow_book_registra_stop_evitado(self):
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            mem = tiger_predictive.MemoriaEvolutivaMercado(
                os.path.join(tmp, "mem.json")
            )
            ok = mem.registrar_cenario_sombra(
                "NQZ6", "SELL", entry=27350.0, stop=27375.0, tp1=27300.0,
                motivo_descarte="stop fora da faixa do contrato"
            )
            self.assertTrue(ok)
            # Preço toca na entrada (27351) e depois explode o stop (27376)
            self.assertEqual(mem.atualizar_precos_sombra("NQZ6", 27351.0), [])
            res = mem.atualizar_precos_sombra("NQZ6", 27376.0)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["desfecho_sombra"], "STOP_EVITADO")

    def test_feedback_ciclo_a_ciclo_gera_instrucao_corretiva_no_prompt(self):
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            mem = tiger_predictive.MemoriaEvolutivaMercado(
                os.path.join(tmp, "mem.json")
            )
            mem.registrar_feedback_ciclo(
                "NQZ6",
                "stop de 100 ticks acima do máximo de 80 ticks",
                "Posicione entry_price no 50% do OB para manter stop <= 80 ticks.",
            )
            bloco = mem.gerar_prompt_autocorrecao_ciclo("NQZ6")
            self.assertIn("AUTOCORREÇÃO OBRIGATÓRIA DO AGENTE", bloco)
            self.assertIn("100 ticks", bloco)

    def test_trava_geometria_rejeita_dados_alucinados(self):
        ok, _ = tiger_predictive.MemoriaEvolutivaMercado.validar_geometria_anti_alucinacao(
            "BUY", entry=27350.0, stop=27380.0, tp1=27300.0
        )
        self.assertFalse(ok)


class TestRegressoesLogsProducao(unittest.TestCase):
    """Testa especificamente os problemas capturados nos logs reais de 17/11."""

    def test_confluence_matrix_nunca_retorna_alertas_vazio_quando_reprovado(self):
        # Garante que avaliacao_matrix['alertas'][0] jamais cause IndexError
        sinal = {
            "action": "SELL",
            "entry_price": 27344.5,
            "stop_loss": 27364.5,
            "take_profit_1": 27304.5,
            "confluence_factors": ["MSS", "Bearish Order Block", "RSI Divergence"],
            "market_analysis": "Rejeição em topo com MSS e divergência no RSI.",
        }
        info_regime = {"regime": market_regime.REGIME_EXPANSAO, "direcao": "BAIXA"}
        res_aprovado = market_regime.ConfluenceMatrix.pontuar_setup(sinal, None, info_regime)
        self.assertTrue(res_aprovado["aprovado"])

        # Mesmo para um setup vazio/reprovado, alertas jamais é vazio
        res_vazio = market_regime.ConfluenceMatrix.pontuar_setup({"action": "BUY"}, None, info_regime)
        self.assertFalse(res_vazio["aprovado"])
        self.assertGreaterEqual(len(res_vazio["alertas"]), 1)

    def test_micro_oscilacao_nq_nao_dispara_tendencia_forte_falsa(self):
        # 4 leituras de preço variando apenas 7.25 pontos no NQ a 27.344 (0.026%)
        velas = [
            {"open": 27344.5, "high": 27344.5, "low": 27344.5, "close": 27344.5},
            {"open": 27344.5, "high": 27348.25, "low": 27348.25, "close": 27348.25},
            {"open": 27348.25, "high": 27350.5, "low": 27350.5, "close": 27350.5},
            {"open": 27350.5, "high": 27351.75, "low": 27351.75, "close": 27351.75},
        ]
        info = market_regime.MarketRegimeClassifier.classificar(velas)
        self.assertFalse(info["tendencia_forte"])

    def test_separador_markdown_nao_dispara_resposta_degenerada(self):
        ns = carregar(["_RE_ESCRITA_ESTRANHA", "_LIGACAO_PT", "_LIGACAO_EN", "resposta_degenerada"])
        texto_com_tabela = (
            "Bom dia, Josevan! Aqui está o resumo do mercado agora:\n"
            "| Ativo | Preço | Viés |\n"
            "|----------|----------|----------|\n"
            "| NQZ6 | 27350.0 | Venda |\n"
        )
        quebrada, motivo = ns["resposta_degenerada"](texto_com_tabela)
        self.assertFalse(quebrada, motivo)

    def test_drawdown_com_teto_entre_parenteses_nao_dispara_falso_alarme(self):
        ns = carregar(["_ROTULOS_DE_FATO", "TOLERANCIA_FATO_USD", "_valor_perto_do_rotulo", "conferir_numeros_da_mesa"])
        fatos = {"margem": 50000.0, "meta": 3000.0, "drawdown": 2000.0, "hoje": 0.0, "ciclo": 0.0}
        for frase in (
            "No plano, drawdown de US$ 0.00 (teto em US$ 2.000) e meta US$ 3.000.",
            "- Drawdown: **US$ 0.00** (teto: US$ 2.000)",
        ):
            _, div = ns["conferir_numeros_da_mesa"](frase, fatos)
            self.assertEqual(div, [], frase)


class TestPacoteSniper500Porcento(unittest.TestCase):
    """Testa as 7 Alavancas Algorítmicas de Hiper-Lucro e Proteção de Conta."""

    def test_refinamento_sniper_ote_converte_stop_100_ticks_em_80_ticks_com_maior_rr(self):
        # Caso real do log: SELL NQZ6 com entrada 27345.0, stop 27370.0 (100 ticks), alvo 27295.0 (200 ticks)
        res = tiger_predictive.normalizar_entrada_ote_para_caber_no_stop(
            direcao="SELL",
            entry=27345.0,
            stop=27370.0,
            tp1=27295.0,
            tp2=27250.0,
            preco_atual=27344.5,
            tick=0.25,
            faixa_ticks=(12, 80),
            rr_minimo=2.0,
        )
        self.assertTrue(res["ajustado"])
        self.assertEqual(res["entry"], 27350.0)
        self.assertEqual(res["ticks_depois"], 80.0)
        self.assertGreater(res["rr_novo"], 2.5)

    def test_front_run_institucional_antecipa_entrada_em_2_ticks_sem_violar_rr(self):
        res = tiger_predictive.otimizar_entrada_sniper_anti_perdida(
            direcao="SELL",
            entry=27350.0,
            stop=27365.0,  # 60 ticks
            tp1=27310.0,   # 160 ticks
            preco_atual=27342.0,
            tick=0.25,
            faixa_ticks=(12, 80),
            rr_minimo=2.0,
        )
        self.assertTrue(res["ajustado"])
        self.assertEqual(res["entry"], 27349.5)  # +2 ticks de front-run na borda
        self.assertGreaterEqual(res["rr_novo"], 2.05)

    def test_despertar_sniper_0s_dispara_em_explosao_de_volume_zscore_3(self):
        negocios = [{"preco": 27350.0, "tamanho": 2.0} for _ in range(20)]
        negocios.append({"preco": 27355.0, "tamanho": 45.0})  # Spike institucional
        res = tiger_predictive.detectar_gatilho_despertar_imediato(
            negocios, ultimo_despertar_ts=0.0, cooldown_s=45.0, agora_ts=1000.0
        )
        self.assertTrue(res["despertar"])
        self.assertGreaterEqual(res["z_score"], 3.0)

    def test_divergencia_smt_detecta_bearish_e_bullish_smt_entre_nq_e_es(self):
        # NQ faz Higher High (27300 -> 27360), ES faz Lower High (5850 -> 5840)
        hist = {
            "NQZ6": [(1, 27280.0), (2, 27300.0), (3, 27290.0), (4, 27360.0)],
            "MESZ6": [(1, 5830.0), (2, 5850.0), (3, 5835.0), (4, 5840.0)],
        }
        res = market_regime.DetectorDivergenciaSMT.detectar("NQZ6", "SELL", hist)
        self.assertTrue(res["smt_confirmado"])
        self.assertEqual(res["tipo"], "BEARISH_SMT")
        self.assertGreater(res["bonus_prob"], 0)

    def test_vwap_bandas_e_killzone_ict(self):
        neg = [
            {"preco": 100.0, "tamanho": 10},
            {"preco": 101.0, "tamanho": 10},
            {"preco": 102.0, "tamanho": 10},
            {"preco": 103.0, "tamanho": 10},
            {"preco": 104.0, "tamanho": 10},
        ]
        info = market_regime.calcular_vwap_e_bandas_fita(neg, preco_atual=105.5)
        self.assertTrue(info["disponivel"])
        self.assertAlmostEqual(info["vwap"], 102.0)
        self.assertEqual(info["zona"], "EXTREMO_PREMIUM_2SD")

    def test_multiplicador_kelly_escudo_anti_quebra_e_house_money(self):
        # 1. Drawdown restante crítico (30% do limite) -> corta lote a 0.50x
        defesa = tiger_predictive.calcular_multiplicador_kelly_institucional(
            probabilidade=88.0, rr=3.0, realizado_hoje=-700.0,
            drawdown_restante=300.0, drawdown_maximo=1000.0
        )
        self.assertEqual(defesa["multiplicador"], 0.50)

        # 2. Dia positivo + Setup Sniper S+ -> House Money 1.30x
        ataque = tiger_predictive.calcular_multiplicador_kelly_institucional(
            probabilidade=88.0, rr=3.0, realizado_hoje=450.0,
            drawdown_restante=1000.0, drawdown_maximo=1000.0, smt_confirmado=True
        )
        self.assertEqual(ataque["multiplicador"], 1.30)

    def test_catraca_lucro_4_estagios_e_parciais_70_30_runner(self):
        # Estágio 3: +1.5R atingido -> trava +1.0R no bolso
        cat = tiger_predictive.calcular_catraca_lucro_multinivel(
            direcao="BUY", entry=100.0, stop_inicial=90.0, stop_atual=90.0,
            preco_atual=115.0, tp1=120.0, tp2=135.0, tick=0.25
        )
        self.assertTrue(cat["mover"])
        self.assertEqual(cat["estagio"], 3)
        self.assertEqual(cat["novo_stop"], 110.0)  # +1.0R garantido

        # Plano 70/30 para 3 contratos -> 2 no TP1 + 1 Runner no TP2
        pl = tiger_predictive.calcular_plano_parciais_e_runner(
            contratos=3, entry=100.0, stop=90.0, tp1=120.0, tp2=140.0
        )
        self.assertTrue(pl["tem_runner"])
        self.assertEqual(pl["contratos_tp1"], 2)
        self.assertEqual(pl["contratos_runner"], 1)


if __name__ == "__main__":
    unittest.main()
