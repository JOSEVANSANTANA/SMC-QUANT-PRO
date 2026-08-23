"""O ORBE DA TIGER: TEMAS COMO DADO, ESTADO COMO COR, E A BOCA QUE NÃO MENTE.

O PEDIDO, E O QUE DELE É POSSÍVEL
----------------------------------
Ele pediu quatro coisas para o Orbe: rosto novo em camadas, boca animada com
"lip-sync profissional", equalizador de voz, e um seletor de temas que troque
o estilo "sem exigir mudança no código da mesa de IA".

Três saíram inteiras. Uma saiu diferente do pedido, e o nome importa:

  LIP-SYNC DE VERDADE NÃO É POSSÍVEL POR ESTE CAMINHO. Lip-sync é a boca
  formando a FORMA de cada fonema, e isso exige o áudio amostrado quadro a
  quadro. A camada de voz aqui é `subprocess.run(["say", ...])` no macOS e
  `pyttsx3` no Windows — nenhum dos dois devolve amplitude, muito menos
  fonema. Não há de onde tirar o dado.

  O que existe é a boca dirigida pela ENERGIA da fala, com uma diferença que
  é o ponto: ela SÓ se mexe quando o estado é FALANDO. O estado vem da
  máquina de estados real, não de um timer. Ou seja, a boca mexendo é sempre
  um fato verdadeiro ("ela está falando agora"); o que é aproximado é o
  desenho, não a afirmação.

  O gancho `envelope_voz` já está no lugar: no dia em que a camada de voz
  medir amplitude de verdade, a boca passa a usar a medida sem mudar nada
  no resto.

POR QUE OS TEMAS SÃO ARQUIVO SEPARADO
--------------------------------------
Antes, paleta e rosto estavam escritos dentro do laço de desenho do
`tiger_hud.py`, junto com radar, telemetria e logs. Trocar de estilo exigia
editar o mesmo arquivo que mostra posição aberta e P&L. Agora um tema é um
dicionário em `orbe_temas.py`, e o laço só chama a função que ele entrega.
"""

import sys
import unittest

from harness import RAIZ

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import orbe_temas as T          # noqa: E402


def _fonte(nome):
    import os
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


class TestOsTemasSaoDADOeNaoCODIGO(unittest.TestCase):
    """Acrescentar um tema tem de ser acrescentar uma entrada num dicionário."""

    def test_todo_tema_tem_o_contrato_completo(self):
        for chave, t in T.TEMAS_DO_ORBE.items():
            for campo in ("rotulo", "descricao", "rosto", "aneis",
                          "particulas", "equalizador", "imagem"):
                self.assertIn(campo, t, f"{chave} não tem '{campo}'")
            self.assertTrue(callable(t["rosto"]), chave)

    def test_ha_mais_de_um_tema_para_escolher(self):
        """Um seletor com uma opção só não é seletor."""
        self.assertGreaterEqual(len(T.TEMAS_DO_ORBE), 4)

    def test_o_seletor_recebe_chave_e_rotulo(self):
        nomes = T.nomes_dos_temas()
        self.assertTrue(all(len(par) == 2 for par in nomes))
        self.assertIn("quantum_predator", [k for k, _ in nomes])

    def test_tema_desconhecido_NAO_apaga_o_painel(self):
        """Um KeyError aqui derrubaria o Orbe por causa de uma string errada
        na configuração — e esse painel mostra posição aberta."""
        for ruim in ("nao_existe", "", None, "   "):
            self.assertIsNotNone(T.tema(ruim))
            self.assertEqual(T.tema(ruim), T.TEMAS_DO_ORBE[T.TEMA_PADRAO])

    def test_o_padrao_existe_de_verdade(self):
        self.assertIn(T.TEMA_PADRAO, T.TEMAS_DO_ORBE)

    def test_o_modulo_de_temas_NAO_importa_tkinter(self):
        """Tema é dado. Se ele arrastar a interface junto, deixa de ser
        trocável e deixa de ser testável sem abrir janela."""
        fonte = _fonte("orbe_temas.py")
        self.assertNotIn("import tkinter", fonte)
        self.assertNotIn("from tkinter", fonte)

    def test_nenhum_tema_sabe_de_trade(self):
        """Tema é pele. Se um tema começar a ler plano, posição ou ordem, a
        separação morreu e trocar de estilo volta a ser risco."""
        fonte = _fonte("orbe_temas.py")
        for proibido in ("carregar_posicoes", "plano_da_conta_ativa",
                         "enviar_ordem", "tradovate", "drawdown"):
            self.assertNotIn(proibido, fonte, f"tema não pode conhecer {proibido}")


class TestAsCoresDizemOEstado(unittest.TestCase):
    """O trader olha o Orbe de longe, sem ler texto. A cor é a única
    informação que atravessa a periferia da visão."""

    def test_os_quatro_estados_que_ele_pediu_existem(self):
        for est in ("STANDBY", "PENSANDO", "FALANDO", "ACAO"):
            self.assertIn(est, T.CORES_DE_ESTADO)

    def test_falando_e_verde_e_acao_e_ambar(self):
        self.assertEqual(T.cores_do_estado("FALANDO")["principal"], "#00ff9d")
        self.assertEqual(T.cores_do_estado("ACAO")["principal"], "#ffb400")

    def test_cada_estado_tem_cor_DIFERENTE(self):
        """Duas cores iguais em estados diferentes é o mesmo que não ter cor."""
        cores = [v["principal"] for v in T.CORES_DE_ESTADO.values()]
        self.assertEqual(len(cores), len(set(cores)))

    def test_estado_desconhecido_cai_no_padrao_sem_quebrar(self):
        self.assertEqual(T.cores_do_estado("XPTO"), T.CORES_DE_ESTADO["STANDBY"])
        self.assertEqual(T.cores_do_estado(None), T.CORES_DE_ESTADO["STANDBY"])

    def test_minusculo_tambem_casa(self):
        self.assertEqual(T.cores_do_estado("falando")["principal"], "#00ff9d")


class TestABocaSoSeMexeQuandoELAFALA(unittest.TestCase):
    """O ponto honesto deste módulo inteiro."""

    def test_calada_a_boca_fica_fechada(self):
        for est in ("STANDBY", "PENSANDO", "OUVINDO", "ACAO", "", None):
            self.assertEqual(T.abertura_da_boca(est, None, 1.0), 0.0, repr(est))

    def test_falando_a_boca_abre(self):
        self.assertGreater(T.abertura_da_boca("FALANDO", None, 1.0), 0.0)

    def test_a_abertura_fica_no_intervalo_valido(self):
        for fase in [i * 0.37 for i in range(200)]:
            a = T.abertura_da_boca("FALANDO", None, fase)
            self.assertGreaterEqual(a, 0.0)
            self.assertLessEqual(a, 1.0)

    def test_a_boca_NAO_e_periodica_demais(self):
        """Uma senoide só produz o 'boneco de ventríloquo'. Duas de períodos
        diferentes quebram o padrão para o olho."""
        vals = [T.abertura_da_boca("FALANDO", None, i * 0.15) for i in range(60)]
        self.assertGreater(len(set(round(v, 2) for v in vals)), 20)

    def test_quando_HOUVER_medida_ela_manda(self):
        """O gancho para o dia em que a camada de voz medir amplitude."""
        self.assertEqual(T.abertura_da_boca("FALANDO", 0.42, 9.9), 0.42)
        self.assertEqual(T.abertura_da_boca("FALANDO", 1.0, 0.0), 1.0)

    def test_medida_fora_da_escala_e_contida_e_nao_explode(self):
        self.assertEqual(T.abertura_da_boca("FALANDO", 5.0, 0.0), 1.0)
        self.assertEqual(T.abertura_da_boca("FALANDO", -3.0, 0.0), 0.0)
        self.assertEqual(T.abertura_da_boca("FALANDO", "abc", 0.0), 0.0)

    def test_o_codigo_NAO_promete_lip_sync(self):
        """Chamar de lip-sync o que é envelope de energia seria vender o que
        não foi feito — a mesma família da telemetria inventada."""
        fonte = _fonte("orbe_temas.py")
        self.assertIn("lip-sync", fonte.lower())
        self.assertIn("fonema", fonte.lower())


class TestOEqualizadorDeVoz(unittest.TestCase):

    def test_em_silencio_repousa_baixo_mas_NAO_em_zero(self):
        """Zero absoluto leria como 'desligado'. Ela está quieta, não morta."""
        b = T.barras_do_equalizador("STANDBY", None, 1.0)
        self.assertTrue(all(0 < x < 0.2 for x in b))

    def test_falando_e_ouvindo_levantam_as_barras(self):
        for est in ("FALANDO", "OUVINDO"):
            b = T.barras_do_equalizador(est, None, 1.0)
            self.assertGreater(max(b), 0.3, est)

    def test_devolve_a_quantidade_pedida(self):
        for n in (8, 24, 40):
            self.assertEqual(len(T.barras_do_equalizador("FALANDO", None, 1.0, n=n)), n)

    def test_toda_barra_fica_no_intervalo(self):
        for fase in [i * 0.41 for i in range(80)]:
            for x in T.barras_do_equalizador("FALANDO", None, fase):
                self.assertGreaterEqual(x, 0.0)
                self.assertLessEqual(x, 1.0)

    def test_o_meio_e_mais_alto_que_as_pontas(self):
        """Voz tem mais energia no meio; visualmente é o formato de sino que
        o olho espera de um equalizador."""
        b = T.barras_do_equalizador("FALANDO", 1.0, 0.0, n=21)
        self.assertGreater(b[10], min(b[0], b[-1]))

    def test_n_bobo_nao_quebra(self):
        self.assertEqual(len(T.barras_do_equalizador("FALANDO", None, 1.0, n=1)), 1)


class TestOHUDUSAOsTemasEDegradaSemEles(unittest.TestCase):
    """Módulo que existe e não é chamado é o `self.order_flow` de novo."""

    def setUp(self):
        self.fonte = _fonte("tiger_hud.py")

    def test_o_hud_importa_os_temas(self):
        self.assertIn("import orbe_temas", self.fonte)

    def test_o_rosto_vem_do_TEMA_e_nao_esta_mais_escrito_no_laco(self):
        self.assertIn('_t["rosto"](self.canvas', self.fonte)
        # A antiga assinatura do rosto fixo saiu do laço de desenho.
        self.assertNotIn("ROSTO E OLHOS DE TIGRE CIBERNÉTICOS", self.fonte)

    def test_sem_o_modulo_o_HUD_ainda_abre(self):
        """Painel que não abre esconde posição aberta. Degradar é obrigatório."""
        self.assertIn("orbe_temas = None", self.fonte)
        self.assertIn("if orbe_temas is None:", self.fonte)

    def test_a_interface_troca_tema_por_UM_metodo(self):
        self.assertIn("def definir_tema", self.fonte)

    def test_o_equalizador_de_barras_substituiu_a_senoide(self):
        self.assertIn("_barras_voz", self.fonte)
        self.assertNotIn("pontos_onda", self.fonte)

    def test_um_tema_quebrado_nao_derruba_o_painel(self):
        i = self.fonte.index('_t["rosto"](self.canvas')
        self.assertIn("except Exception", self.fonte[i:i + 400])


class TestOQuadroDoGraficoDentroDoOrbe(unittest.TestCase):

    def setUp(self):
        self.hud = _fonte("tiger_hud.py")

    def test_o_quadro_existe(self):
        self.assertIn("LIVE CHART INSIGHT", self.hud)
        self.assertIn("def _desenhar_painel_do_grafico", self.hud)

    def test_sem_captura_ele_DIZ_que_nao_tem(self):
        """Um quadro vazio e bonito faria o trader achar que o motor está
        olhando algo quando não está."""
        i = self.hud.index("def _desenhar_painel_do_grafico")
        trecho = self.hud[i:i + 2200]
        self.assertIn("sem captura ainda", trecho)

    def test_a_referencia_da_imagem_e_GUARDADA(self):
        """O Tkinter não segura imagem sozinho: sem alguém guardando, o
        coletor de lixo leva e o quadro fica preto sem erro nenhum."""
        i = self.hud.index("def definir_grafico")
        self.assertIn("self.imagem_grafico = imagem_tk", self.hud[i:i + 1500])

    def test_o_seletor_so_aparece_com_mais_de_uma_fonte(self):
        """Não se oferece escolha que não existe."""
        i = self.hud.index("CHART SOURCE")
        self.assertIn("len(fontes) > 1", self.hud[max(0, i - 400):i])

    def test_a_imagem_vem_da_MESMA_captura_que_o_motor_analisou(self):
        fonte = _fonte("main_app.py")
        i = fonte.index("def _alimentar_grafico_do_orbe")
        trecho = fonte[i:i + 2200]
        self.assertIn("_ultimo_print", trecho)
        self.assertIn("não um feed ao vivo", trecho)

    def test_o_rotulo_carrega_a_HORA_da_captura(self):
        """Um quadro que parece ao vivo e está defasado é pior que quadro
        nenhum."""
        fonte = _fonte("main_app.py")
        i = fonte.index("def _alimentar_grafico_do_orbe")
        self.assertIn('info.get("hora")', fonte[i:i + 2200])


class TestOSeletorNaAbaDeConfiguracoes(unittest.TestCase):

    def setUp(self):
        self.fonte = _fonte("main_app.py")

    def test_o_seletor_existe(self):
        self.assertIn("Estilo do Orbe:", self.fonte)
        self.assertIn("def _trocar_tema_orbe", self.fonte)

    def test_a_escolha_e_GUARDADA(self):
        i = self.fonte.index("def _trocar_tema_orbe")
        self.assertIn('salvar_config({"tema_orbe"', self.fonte[i:i + 1400])

    def test_trocar_tema_NAO_toca_em_nada_do_motor(self):
        """O pedido literal: 'sem exigir mudança no código da mesa de IA'."""
        i = self.fonte.index("def _trocar_tema_orbe")
        corpo = self.fonte[i:i + 1400]
        for proibido in ("carregar_posicoes", "salvar_posicoes",
                         "_tv_enviar_bracket", "plano_da_conta_ativa",
                         "freio_de_sugestoes"):
            self.assertNotIn(proibido, corpo, f"tema não pode tocar {proibido}")

    def test_rotulo_desconhecido_nao_faz_nada(self):
        i = self.fonte.index("def _trocar_tema_orbe")
        self.assertIn("if not chave:", self.fonte[i:i + 1400])

    def test_o_tema_salvo_e_aplicado_quando_o_HUD_nasce(self):
        """Salvar e não aplicar na abertura faria a escolha durar uma sessão."""
        self.assertIn('carregar_config().get(\n                        "tema_orbe"',
                      self.fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
