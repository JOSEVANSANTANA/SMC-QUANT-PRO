"""O GRÁFICO SAI DE TRÁS DO ORBE E VAI PARA O PAINEL ESQUERDO, FIXO.

O PEDIDO
--------
"Considere desligar o gráfico que está por detrás do orbe e tenta colocar ali
do lado esquerdo mesmo como recomendado anteriormente, fixo."

É a terceira vez que ele descreve o mesmo lugar. Antes já tinha escrito: "a
ideia era deixar a janela do gráfico ali do lado, abaixo de (posição), como na
imagem dois, até coloquei um quadro branco ali para deixar reservado".

A DIFERENÇA NÃO É DE GOSTO, É DE PAPEL
---------------------------------------
Atrás do Orbe o gráfico é PANO DE FUNDO: fica escurecido por véu para não
competir com o rosto e o equalizador, e serve de ambiente. No painel esquerdo
ele é INFORMAÇÃO: fica ao lado da telemetria que ele já lê — ATIVO, REGIME,
ORDER FLOW, CONFLUÊNCIAS, POSIÇÃO — no espaço que sobrava vazio dentro do
card. São dois usos diferentes, e por isso a escolha virou um menu de três
posições em vez de uma caixinha de liga/desliga.

O QUE ESTES TESTES CRAVAM
--------------------------
  · Um único método desenha o quadro nos dois lugares. Duas cópias divergem:
    a primeira correção entra numa e esquece a outra, e o defeito volta só em
    um dos modos — que é o mais difícil de reproduzir.
  · O quadro CABE dentro do card esquerdo em toda largura de HUD. Foi
    justamente um dimensionamento por palpite ("52% da largura") que na v2.67
    jogou a imagem para debaixo dos painéis laterais, cabendo por coincidência
    só no monitor grande.
  · Quando não cabe, o programa DIZ. Sumir em silêncio é o defeito que ele
    relatou duas vezes com outro nome.
  · A área morre a cada quadro. Guardá-la entre quadros faria a imagem sair no
    tamanho do lugar anterior depois de trocar de lugar ou redimensionar.
"""

import json
import os
import subprocess
import sys
import unittest

from harness import RAIZ, carregar

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def _fonte(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


def _sem_comentarios(texto):
    """Tira comentário e docstring antes de procurar código no fonte (lição da
    casa: senão o teste casa com o comentário que EXPLICA o defeito antigo e
    passa a punir a documentação)."""
    linhas, dentro = [], False
    for ln in texto.splitlines():
        n = ln.count('"""') + ln.count("'''")
        if dentro:
            if n % 2 == 1:
                dentro = False
            continue
        if n % 2 == 1:
            dentro = True
            continue
        if n >= 2 or ln.strip().startswith("#"):
            continue
        linhas.append(ln.split("  # ")[0])
    return "\n".join(linhas)


# O renderizador roda NUM SUBPROCESSO, com tkinter trocado por um Canvas que
# só anota o que foi pedido. Subprocesso, e não stub em `sys.modules`, porque
# trocar o tkinter do processo estragaria qualquer outro teste que rode depois.
_ESPIAO = r'''
import sys, types, json
sys.path.insert(0, %(raiz)r)
tk = types.ModuleType("tkinter")
class _C:
    def __init__(self, *a, **k): self.ch = []
    def delete(self, *a, **k): pass
    def __getattr__(self, n):
        def f(*a, **k):
            self.ch.append((n, list(a), k)); return len(self.ch)
        return f
tk.Canvas = _C; tk.Frame = object; tk.Tk = object; tk.Toplevel = object
ttk = types.ModuleType("tkinter.ttk"); tk.ttk = ttk
sys.modules["tkinter"] = tk; sys.modules["tkinter.ttk"] = ttk
import tiger_hud as T

w, h, lugar, tem_img, aviso = %(args)r
c = _C()
r = T.CyberHUDCanvasRenderer(c, largura=w, altura=h)
r.definir_fundo_de_contexto("<IMG>" if tem_img else None,
                            ligado=(lugar != "nenhum"), aviso=aviso, lugar=lugar)
r.desenhar()
pw = max(290, min(420, int(w * 0.30))) if w > 600 else 0
print(json.dumps({
    "area": r.area_do_grafico(),
    "area_cluster": r.area_do_cluster(),
    "sem_espaco": r.grafico_sem_espaco(),
    "imagens": [i for i, (n, a, k) in enumerate(c.ch) if n == "create_image"],
    "textos": [k.get("text", "") for n, a, k in c.ch if n == "create_text"],
    "card_esquerdo": [20, 48, 20 + pw, h - 16],
    "total": len(c.ch),
}))
'''


def _desenhar(w=1400, h=700, lugar="esquerda", tem_img=True, aviso=""):
    codigo = _ESPIAO % {"raiz": RAIZ, "args": (w, h, lugar, tem_img, aviso)}
    saida = subprocess.run([sys.executable, "-c", codigo],
                           capture_output=True, text=True, timeout=60)
    assert saida.returncode == 0, saida.stderr
    return json.loads(saida.stdout.strip().splitlines()[-1])


class TestOGraficoVaiParaOPainelEsquerdo(unittest.TestCase):

    def test_o_padrao_e_o_painel_esquerdo(self):
        """Ele pediu três vezes. O padrão passa a ser o lugar que ele quer,
        e não o que estava construído."""
        d = _desenhar(lugar="")
        self.assertIsNotNone(d["area"])
        x1, y1, x2, y2 = d["area"]
        cx1, cy1, cx2, cy2 = d["card_esquerdo"]
        self.assertGreaterEqual(x1, cx1)
        self.assertLessEqual(x2, cx2)

    def test_o_quadro_CABE_no_card_esquerdo_em_toda_largura(self):
        """Foi um dimensionamento por palpite que na v2.67 jogou a imagem para
        debaixo dos painéis laterais, cabendo por coincidência só no monitor
        grande — o que tornou o defeito intermitente."""
        for w, h in ((1900, 850), (1600, 900), (1400, 700), (1000, 600)):
            with self.subTest(hud=f"{w}x{h}"):
                d = _desenhar(w, h, "esquerda")
                if d["area"] is None:
                    continue                      # não coube; outro teste cobre
                x1, y1, x2, y2 = d["area"]
                cx1, cy1, cx2, cy2 = d["card_esquerdo"]
                self.assertGreaterEqual(x1, cx1, "vazou pela esquerda do card")
                self.assertLessEqual(x2, cx2, "vazou por cima do Orbe")
                self.assertLessEqual(y2, cy2, "vazou pelo rodapé do card")

    def test_o_quadro_fica_ABAIXO_da_telemetria_e_nao_por_cima(self):
        """'abaixo de (posição)' — palavras dele. O topo sai da conta dos itens
        e não de um número fixo: `item_h` encolhe em HUD baixo, e um 'y = 300'
        cravado colidiria com POSIÇÃO na primeira janela pequena."""
        alto = _desenhar(1900, 850, "esquerda")["area"]
        baixo = _desenhar(1400, 700, "esquerda")["area"]
        self.assertGreater(alto[1], 48 + 42, "começou dentro do cabeçalho do card")
        self.assertEqual(alto[1], baixo[1],
                         "o topo deveria vir da mesma conta nos dois tamanhos")

    def test_a_imagem_e_desenhada_dentro_dele(self):
        d = _desenhar(1400, 700, "esquerda")
        self.assertEqual(len(d["imagens"]), 1)

    def test_o_quadro_tem_titulo_PROPRIO_e_nao_o_de_contexto(self):
        """Ali ele é informação ao lado da telemetria, não pano de fundo."""
        d = _desenhar(1400, 700, "esquerda")
        self.assertTrue(any("GRAFICO DO ATIVO" in t for t in d["textos"]))


class TestAtrasDoOrbeContinuaExistindo(unittest.TestCase):

    def test_o_modo_fundo_ainda_funciona(self):
        """Foi construído e funciona; deixou de ser o padrão, não foi apagado."""
        d = _desenhar(1900, 850, "fundo")
        self.assertEqual(len(d["imagens"]), 1)
        self.assertIsNotNone(d["area_cluster"])

    def test_no_modo_esquerda_o_quadro_do_CLUSTER_nao_e_desenhado(self):
        """Com o gráfico morando à esquerda, o quadro escuro do meio vira uma
        caixa vazia em volta do Orbe — um elemento que não contém nada e não
        explica nada. Enquanto o gráfico morava lá ele era a moldura e
        precisava existir sempre; agora não."""
        d = _desenhar(1900, 850, "esquerda")
        self.assertIsNone(d["area_cluster"])

    def test_nenhum_nao_desenha_grafico_em_lugar_algum(self):
        d = _desenhar(1900, 850, "nenhum")
        self.assertEqual(len(d["imagens"]), 0)
        self.assertIsNone(d["area"])
        self.assertIsNone(d["area_cluster"])


class TestQuandoNAOCabeOProgramaDIZ(unittest.TestCase):

    def test_HUD_baixo_nao_desenha_um_quadro_ilegivel(self):
        """Um quadro de 40px de altura não mostra gráfico nenhum e só tira
        espaço de quem tem o que dizer."""
        d = _desenhar(900, 280, "esquerda")
        self.assertIsNone(d["area"])
        self.assertEqual(len(d["imagens"]), 0)

    def test_e_PUBLICA_que_nao_coube_para_o_log_poder_falar(self):
        """Nem sempre dá para escrever o aviso na tela: num HUD de 280px os
        cinco itens da telemetria já consomem o card inteiro. Quem tem voz
        nesse caso é o log — e quem sabe do problema é o renderizador."""
        self.assertTrue(_desenhar(900, 280, "esquerda")["sem_espaco"])
        self.assertFalse(_desenhar(1400, 700, "esquerda")["sem_espaco"])

    def test_o_main_app_FALA_quando_nao_coube(self):
        codigo = _sem_comentarios(_fonte("main_app.py"))
        i = codigo.index("grafico_sem_espaco")
        self.assertIn("_porque_sem_fundo", codigo[i:i + 500])

    def test_ligado_e_sem_imagem_o_quadro_escreve_o_motivo(self):
        d = _desenhar(1400, 700, "esquerda", tem_img=False,
                      aviso="aguardando a primeira captura do motor")
        na_tela = [t for t in d["textos"] if "SEM IMAGEM" in t]
        self.assertEqual(len(na_tela), 1)
        self.assertIn("aguardando a primeira captura", na_tela[0])


class TestAAreaMorreACadaQuadro(unittest.TestCase):

    def test_a_area_e_zerada_no_inicio_do_desenho(self):
        """Guardá-la entre quadros faria o main_app dimensionar a imagem por um
        retângulo que já não existe — depois de trocar o lugar ou redimensionar
        a janela, a medida velha continuaria valendo."""
        fonte = _sem_comentarios(_fonte("tiger_hud.py"))
        i = fonte.index("def desenhar(self):")
        self.assertIn("self._area_grafico = None", fonte[i:i + 400])


class TestUmQuadroSO_ParaOsDoisLugares(unittest.TestCase):

    def setUp(self):
        self.fonte = _sem_comentarios(_fonte("tiger_hud.py"))

    def test_existe_UM_metodo_que_desenha_o_quadro(self):
        """Duas cópias divergem: a primeira correção entra numa e esquece a
        outra, e o defeito volta só em um dos modos."""
        self.assertEqual(self.fonte.count("def _desenhar_quadro_do_grafico"), 1)

    def test_os_dois_lugares_chamam_o_MESMO_metodo(self):
        i = self.fonte.index("def _desenhar_fundo_de_contexto")
        j = self.fonte.index("def _desenhar_grafico_lateral")
        self.assertIn("_desenhar_quadro_do_grafico", self.fonte[i:i + 1200])
        self.assertIn("_desenhar_quadro_do_grafico", self.fonte[j:j + 1600])

    def test_o_veu_e_o_aviso_moram_no_metodo_compartilhado(self):
        i = self.fonte.index("def _desenhar_quadro_do_grafico")
        corpo = self.fonte[i:i + 2400]
        self.assertIn("stipple", corpo)
        self.assertIn("SEM IMAGEM", corpo)


class TestAEscolhaNaConfiguracao(unittest.TestCase):

    def setUp(self):
        self.ns = carregar(["lugar_do_grafico_pelo_rotulo", "_ROTULO_DO_LUGAR"])

    def test_os_tres_lugares_existem(self):
        self.assertEqual(set(self.ns["_ROTULO_DO_LUGAR"]),
                         {"esquerda", "fundo", "nenhum"})

    def test_o_rotulo_do_menu_vira_a_chave_guardada(self):
        rot = self.ns["_ROTULO_DO_LUGAR"]
        for chave, texto in rot.items():
            self.assertEqual(self.ns["lugar_do_grafico_pelo_rotulo"](texto), chave)

    def test_rotulo_desconhecido_devolve_None_e_nao_um_padrao(self):
        """Gravar um padrão aqui trocaria a escolha dele por uma minha sem
        avisar."""
        self.assertIsNone(self.ns["lugar_do_grafico_pelo_rotulo"]("qualquer coisa"))

    def test_o_rotulo_diz_o_que_a_escolha_FAZ(self):
        """'esquerda' sozinho não explica que ali o gráfico deixa de ser pano
        de fundo e passa a ser informação ao lado da telemetria."""
        rot = self.ns["_ROTULO_DO_LUGAR"]
        self.assertIn("POSIÇÃO", rot["esquerda"])
        self.assertIn("fundo", rot["fundo"])


class TestQuemJaTinhaDesligadoNaoVeOGraficoVoltar(unittest.TestCase):

    def test_a_preferencia_antiga_e_respeitada_quando_nao_ha_a_nova(self):
        """O padrão mudou. Quem já tinha desligado o fundo não pode ver o
        gráfico reaparecer sozinho num canto novo só por causa disso."""
        codigo = _sem_comentarios(_fonte("main_app.py"))
        # Ancorado na LEITURA da configuração, e não no primeiro lugar onde o
        # nome aparece — âncora frouxa mede o trecho errado do arquivo e falha
        # (ou passa) sem relação com a regra.
        i = codigo.index('cfg.get("lugar_do_grafico"')
        trecho = codigo[i:i + 500]
        self.assertIn("contexto_de_fundo", trecho)
        self.assertIn("nenhum", trecho)

    def test_a_troca_grava_as_DUAS_chaves_juntas(self):
        """Duas verdades sobre o mesmo assunto divergem."""
        codigo = _sem_comentarios(_fonte("main_app.py"))
        i = codigo.index("def _trocar_lugar_do_grafico")
        corpo = codigo[i:i + 1200]
        self.assertIn('"lugar_do_grafico"', corpo)
        self.assertIn('"contexto_de_fundo"', corpo)

    def test_a_troca_da_RECIBO_do_que_aconteceu(self):
        """Mesma regra do interruptor que ele reclamou: 'escolhi' não é
        resposta — o que vale é se a imagem entrou."""
        codigo = _sem_comentarios(_fonte("main_app.py"))
        i = codigo.index("def _trocar_lugar_do_grafico")
        self.assertIn("_fundo_aplicado", codigo[i:i + 1400])


if __name__ == "__main__":
    unittest.main(verbosity=2)
