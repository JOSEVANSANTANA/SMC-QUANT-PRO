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


class TestAsCamadasDoCluster(unittest.TestCase):
    """O QUADRO FLUTUANTE SAIU, E O MOTIVO FOI ELE QUEM DEU.

    Na v2.66.0 a última captura entrava num quadro de 210px no quadrante
    inferior-direito do cluster. Palavras dele: "ficou muito estranho...
    desalinhado e sobreposto, competindo visualmente com a telemetria e o
    equalizador. Isso não é contextual e parece um erro de alinhamento."

    Estava certo. Um retângulo solto no meio de um cockpit não lê como
    contexto — lê como widget esquecido.

    Agora são três camadas, e no Canvas do Tkinter a ORDEM DE DESENHO é a
    ordem das camadas:

        Camada 0 — o gráfico, ocupando o fundo do cluster inteiro
        Camada 1 — o rosto (PNG quando há, vetorial quando não)
        Camada 2 — telemetria, logs e equalizador, por cima de tudo

    Contexto é o que fica atrás; informação é o que fica na frente.
    """

    def setUp(self):
        self.hud = _fonte("tiger_hud.py")

    def test_o_quadro_flutuante_SUMIU(self):
        for morto in ("LIVE CHART INSIGHT", "definir_grafico",
                      "_seletor_grafico_bounds", "CHART SOURCE"):
            self.assertNotIn(morto, self.hud, f"sobrou resquício de {morto}")

    def test_a_camada_0_e_desenhada_ANTES_do_rosto(self):
        """Se o fundo vier depois, ele cobre o Orbe — e o cockpit inverte."""
        i_fundo = self.hud.index("self._desenhar_fundo_de_contexto(")
        i_rosto = self.hud.index("desenhar_rosto_de_imagem(")
        self.assertLess(i_fundo, i_rosto)

    def test_a_camada_0_e_desligavel(self):
        i = self.hud.index("def _desenhar_fundo_de_contexto")
        self.assertIn('getattr(self, "contexto_de_fundo", True)', self.hud[i:i + 2600])

    def test_o_fundo_leva_veu_escuro(self):
        """Sem véu, o gráfico compete em brilho com o rosto e o equalizador,
        e o cockpit vira sopa visual."""
        i = self.hud.index("def _desenhar_fundo_de_contexto")
        self.assertIn("stipple", self.hud[i:i + 2000])

    def test_sem_captura_o_fundo_apenas_NAO_desenha(self):
        """Fundo ausente é fundo escuro, não é erro."""
        i = self.hud.index("def _desenhar_fundo_de_contexto")
        trecho = self.hud[i:i + 2600]
        self.assertIn("if img is None:", trecho)
        self.assertIn("return", trecho)

    def test_as_referencias_das_DUAS_imagens_sao_guardadas(self):
        """O Tkinter não segura imagem sozinho: sem alguém guardando, o
        coletor leva e some sem erro nenhum."""
        self.assertIn("self.imagem_fundo = imagem_tk", self.hud)
        self.assertIn("self.imagem_rosto = imagem_tk", self.hud)

    def test_o_QUADRO_ESCURO_sai_sempre_ligado_ou_nao(self):
        """Pedido dele: "certifique-se do gráfico ficar posicionado naquele
        quadrado mais escuro cedido ao Orbe, por trás do Orbe".

        O quadro é a MOLDURA, não o conteúdo: sem ele, desligar o fundo
        deixava um vazio sem forma no meio do cockpit."""
        i = self.hud.index("def _desenhar_fundo_de_contexto")
        trecho = self.hud[i:i + 2600]
        i_quadro = trecho.index("create_rectangle")
        i_guarda = trecho.index('getattr(self, "contexto_de_fundo", True)')
        self.assertLess(i_quadro, i_guarda,
                        "o quadro escuro tem de ser desenhado ANTES do "
                        "interruptor — ele é a moldura, não o conteúdo")

    def test_a_area_do_cluster_e_PUBLICADA_para_quem_redimensiona(self):
        """Quem tem o Pillow é o main_app; quem sabe a geometria é o
        renderizador. Sem publicar, o main_app volta a chutar."""
        self.assertIn("def area_do_cluster", self.hud)
        self.assertIn("self._area_cluster = (x1, y1, x2, y2)", self.hud)

    def test_a_imagem_e_dimensionada_pela_AREA_e_nao_por_palpite(self):
        fonte = _fonte("main_app.py")
        i = fonte.index("CAMADA 0: o grafico ao fundo")
        trecho = fonte[i:i + 3000]
        self.assertIn("area_do_cluster()", trecho)
        self.assertNotIn('largura", 900) * 0.52', trecho)

    def test_sem_area_ainda_publicada_NAO_quebra(self):
        """Antes do primeiro desenho ela é None — vale a estimativa, e o
        quadro seguinte já sai no lugar certo."""
        fonte = _fonte("main_app.py")
        i = fonte.index("area_do_cluster()")
        self.assertIn("if area:", fonte[i:i + 400])
        self.assertIn("else:", fonte[i:i + 700])

    def test_o_chute_antigo_ESTOURAVA_o_quadro(self):
        """A régua em Python, com a mesma geometria do renderizador. Em HUD
        de 1400px o 52% dava 728px num quadro de 532px — o gráfico ia parar
        debaixo dos painéis laterais."""
        for w, h in ((1400, 700), (900, 420)):
            pw = max(290, min(420, int(w * 0.30))) if w > 600 else 0
            lc = w - 2 * pw if pw > 0 else w
            meia = max(120, int(lc * 0.5) - 14)
            largura_do_quadro = 2 * meia
            self.assertGreater(int(w * 0.52), largura_do_quadro,
                               f"em {w}px o chute antigo cabia — escolha outro caso")

    def test_o_veu_fica_contido_no_MESMO_retangulo(self):
        """Véu maior que o quadro escureceria a telemetria ao lado."""
        i = self.hud.index("VEU ESCURO POR CIMA")
        self.assertIn("create_rectangle(x1, y1, x2, y2", self.hud[i:i + 600])

    def test_o_fundo_le_o_ARQUIVO_e_nao_so_o_atributo_em_memoria(self):
        """O DEFEITO QUE ELE PEGOU: "não carregou, mesmo ligado".

        A primeira versão lia só `self._ultimo_print`, que só existe depois
        que um ciclo popula o atributo NAQUELA instância. A captura estava em
        disco o tempo todo; quem não estava era o atributo. O arquivo
        sobrevive a reinício do HUD, troca de aba e thread diferente."""
        fonte = _fonte("main_app.py")
        i = fonte.index("CAMADA 0: o grafico ao fundo")
        trecho = fonte[i:i + 2500]
        self.assertIn("ULTIMO_PRINT_FILE", trecho)
        self.assertIn("os.path.exists(ULTIMO_PRINT_FILE)", trecho)

    def test_toda_falha_do_fundo_TEM_MOTIVO_dito(self):
        """A versão anterior engolia tudo em `except: pass` — sem arquivo,
        sem Pillow, sem conversão, tudo virava o mesmo nada, e ele não tinha
        como saber se estava quebrado ou se faltava captura."""
        fonte = _fonte("main_app.py")
        self.assertIn("def _porque_sem_fundo", fonte)
        i = fonte.index("CAMADA 0: o grafico ao fundo")
        trecho = fonte[i:i + 2500]
        self.assertIn("_porque_sem_fundo", trecho)
        for causa in ("Pillow", "captura de gráfico em disco", "converter a captura"):
            self.assertIn(causa, fonte, f"a causa '{causa}' precisa ser dita")

    def test_o_motivo_sai_UMA_vez_e_nao_a_cada_quadro(self):
        """O HUD redesenha ~12x por segundo. Repetir encheria o log e
        esconderia o resto."""
        fonte = _fonte("main_app.py")
        i = fonte.index("def _porque_sem_fundo")
        self.assertIn("_sem_fundo_dito", fonte[i:i + 1600])

    def test_DESLIGADO_nao_e_tratado_como_defeito(self):
        """Quem desligou sabe por que desligou. Avisar ali seria ruído."""
        # Ancorado DENTRO da camada 0: existe outro "if not ligado:" no
        # caminho de desligar o motor, e casar com ele testaria outra coisa.
        fonte = _fonte("main_app.py")
        i = fonte.index("CAMADA 0: o grafico ao fundo")
        trecho = fonte[i:i + 2500]
        j = trecho.index("if not ligado:")
        self.assertIn("_sem_fundo_dito = None", trecho[j:j + 220])
        self.assertIn("desligado não é defeito", trecho[j:j + 220])

    def test_o_fundo_vem_da_MESMA_captura_que_o_motor_analisou(self):
        fonte = _fonte("main_app.py")
        i = fonte.index("def _alimentar_grafico_do_orbe")
        trecho = fonte[i:i + 3000]
        self.assertIn("_ultimo_print", trecho)
        self.assertIn("nao um feed ao vivo paralelo", trecho)


class TestORostoEmImagem(unittest.TestCase):
    """O tigre fotorrealista não se desenha com linha e polígono. A única
    forma honesta é carregar o arquivo — e o arquivo é dele."""

    def test_o_caminho_vem_da_CONFIGURACAO_e_nao_do_codigo(self):
        """Um nome cravado só funcionaria se ele batizasse o arquivo
        exatamente assim, e falharia em silêncio para qualquer outro — o
        defeito que faz o usuário achar que o recurso não existe."""
        fonte = _fonte("main_app.py")
        self.assertIn('cfg.get("imagem_do_orbe"', fonte)
        self.assertIn("def _escolher_imagem_do_orbe", fonte)

    def test_arquivo_que_nao_serve_e_RECUSADO_com_motivo(self):
        self.assertEqual(T.caminho_de_imagem_valido("")[0], False)
        self.assertIn("não encontrado",
                      T.caminho_de_imagem_valido("/nao/existe/x.png")[1])
        self.assertIn("não suportado",
                      T.caminho_de_imagem_valido(__file__)[1])

    def test_png_passa_limpo(self):
        import os
        png = os.path.join(RAIZ, "icone.png")
        if os.path.exists(png):
            self.assertEqual(T.caminho_de_imagem_valido(png), (True, ""))

    def test_jpeg_passa_COM_aviso_e_nao_e_recusado(self):
        """O Pillow abre. Recusar seria barrar um formato que funciona."""
        import os, tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            nome = f.name
        try:
            ok, motivo = T.caminho_de_imagem_valido(nome)
            self.assertTrue(ok)
            self.assertIn("Pillow", motivo)
        finally:
            os.unlink(nome)

    def test_a_funcao_NAO_abre_o_arquivo(self):
        """A regra tem de ser conferível sem tela e sem Tk."""
        fonte = _fonte("orbe_temas.py")
        i = fonte.index("def caminho_de_imagem_valido")
        corpo = fonte[i:i + 1600]
        self.assertNotIn("open(", corpo)
        self.assertNotIn("PhotoImage", corpo)

    def test_imagem_que_nao_carrega_CAI_no_rosto_vetorial(self):
        """Uma imagem quebrada não pode deixar o Orbe sem cara nenhuma."""
        self.assertFalse(T.desenhar_rosto_de_imagem(None, 0, 0, 1, None))
        hud = _fonte("tiger_hud.py")
        i = hud.index("_usou_imagem")
        self.assertIn("if not _usou_imagem and _t is not None:", hud[i:i + 900])

    def test_o_contrato_do_tema_ainda_tem_o_campo_imagem(self):
        for chave, t in T.TEMAS_DO_ORBE.items():
            self.assertIn("imagem", t, chave)


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

    def test_o_interruptor_do_fundo_existe_e_e_guardado(self):
        self.assertIn("def _alternar_contexto_de_fundo", self.fonte)
        i = self.fonte.index("def _alternar_contexto_de_fundo")
        self.assertIn('salvar_config({"contexto_de_fundo"', self.fonte[i:i + 800])

    def test_escolher_imagem_DIZ_quando_o_arquivo_nao_serve(self):
        """Guardar um caminho ruim em silêncio faria ele achar que escolheu
        e que o programa ignorou."""
        i = self.fonte.index("def _escolher_imagem_do_orbe")
        corpo = self.fonte[i:i + 1800]
        self.assertIn("caminho_de_imagem_valido", corpo)
        self.assertIn("Não usei essa imagem", corpo)

    def test_da_para_TIRAR_a_imagem_e_voltar_ao_rosto_do_tema(self):
        self.assertIn("def _limpar_imagem_do_orbe", self.fonte)

    def test_o_tema_salvo_e_aplicado_quando_o_HUD_nasce(self):
        """Salvar e não aplicar na abertura faria a escolha durar uma sessão."""
        self.assertIn('carregar_config().get(\n                        "tema_orbe"',
                      self.fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
