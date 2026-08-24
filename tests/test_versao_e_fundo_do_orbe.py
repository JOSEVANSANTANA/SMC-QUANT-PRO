"""A VERSÃO QUE MENTIA, E O QUADRO DO ORBE QUE NÃO FALAVA.

O PEDIDO
--------
Ele mandou um log e uma frase: "por favor, pare de tentar acertar, resolva
isso definitivamente". O gráfico ao fundo do Orbe não aparecia, o interruptor
dizia "LIGADO", e nada acontecia na tela.

O QUE ESTAVA POR TRÁS — E POR QUE DUAS RODADAS SE PERDERAM
-----------------------------------------------------------
O defeito de fundo não era o desenho. Executando o renderizador com um Canvas
espião, a imagem entra no lugar certo em todos os tamanhos. O que faltava era
QUALQUER FORMA DE SABER O QUE ESTAVA RODANDO E O QUE ESTAVA ACONTECENDO:

  1. `VERSAO_ATUAL` era um literal escrito à mão, e o passo "incrementar
     VERSAO_ATUAL" do checklist de release foi esquecido por catorze versões:
     o `versao.json` chegou em 2.67.2 e o programa continuava se apresentando
     como 2.53.0 — no cabeçalho do HUD, no log, no relatório. Nem ele nem eu
     tínhamos como saber se o log que ele mandou era da build com a correção.
     Discutimos sintoma de um binário cuja identidade o binário escondia.

  2. O interruptor confirmava a INTENÇÃO, não o resultado: "LIGADO." saía
     igual tendo a imagem entrado ou não.

  3. O quadro do Orbe era #01060f com contorno #0a2036 sobre fundo #030712 —
     três quase-pretos a menos de 3% de luminância um do outro. Eu escrevi
     para ele "o quadrado mais escuro cedido ao Orbe"; na tela dele não havia
     quadrado nenhum para achar.

  4. A camada 0 alimentava só o HUD embutido. Quem clicasse em "Desacoplar
     HUD (Solta)" ficava com uma janela que nunca receberia fundo — sem erro,
     sem log. `_trocar_tema_orbe` já percorria os dois; esta não.

  5. O caminho periódico embrulhava tudo em `except Exception: pass`, então
     um erro real ficava com a MESMA cara de "ainda não há captura".

A regra que estes testes cravam é uma só: o programa tem de dizer quem é e o
que aconteceu. Defeito de enfeite não derruba o pregão — mas defeito MUDO de
enfeite consome a tarde de quem está tentando operar.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from harness import RAIZ, carregar

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def _fonte(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


def _sem_comentarios(texto):
    """Tira comentário e docstring antes de procurar código no fonte.

    A LIÇÃO DA CASA (test_conta_orfa.py): um teste que procura texto no fonte
    casa com o comentário que EXPLICA o defeito antigo e passa a punir a
    documentação. Aqui só sobra código.

    Linha a linha, e não por `tokenize`: juntar tokens quebra `def f(` em
    pedaços e nenhum `.index("def f")` acha mais nada — foi o que a primeira
    versão deste arquivo fez, e os testes acusaram ausência de código que
    estava lá. Contar delimitadores da linha inteira é o que resolve, porque
    as docstrings daqui fecham no fim do último parágrafo e não no começo de
    uma linha."""
    linhas = []
    dentro = False
    for ln in texto.splitlines():
        n = ln.count('"""') + ln.count("'''")
        if dentro:
            if n % 2 == 1:
                dentro = False
            continue
        if n % 2 == 1:
            dentro = True
            continue
        if n >= 2:          # docstring de uma linha só
            continue
        if ln.strip().startswith("#"):
            continue
        linhas.append(ln.split("  # ")[0])
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# 1. A VERSÃO SAI DO versao.json, E NÃO DE UM NÚMERO ESCRITO À MÃO
# ---------------------------------------------------------------------------
class TestAVersaoNaoPodeDivergir(unittest.TestCase):

    def setUp(self):
        self.ns = carregar(["_versao_do_pacote"])

    def test_le_a_versao_do_arquivo_que_viaja_junto(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "versao.json"), "w", encoding="utf-8") as f:
                json.dump({"versao": "9.9.9"}, f)
            self.assertEqual(self.ns["_versao_do_pacote"](base=d), "9.9.9")

    def test_sem_arquivo_devolve_o_padrao_e_o_padrao_GRITA(self):
        """0.0.0 é escolha deliberada: número absurdo faz alguém perguntar.
        Um número plausível chutado aqui recriaria a mentira silenciosa."""
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.ns["_versao_do_pacote"](base=d), "0.0.0")

    def test_json_corrompido_nao_derruba_o_programa(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "versao.json"), "w", encoding="utf-8") as f:
                f.write("{isto não é json")
            self.assertEqual(self.ns["_versao_do_pacote"](base=d, padrao="1.2.3"), "1.2.3")

    def test_campo_versao_vazio_cai_no_padrao(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "versao.json"), "w", encoding="utf-8") as f:
                json.dump({"versao": "   "}, f)
            self.assertEqual(self.ns["_versao_do_pacote"](base=d, padrao="7.7.7"), "7.7.7")

    def test_a_versao_de_verdade_do_projeto_e_lida(self):
        """Ponta a ponta, no repositório real: o número que sai da função é o
        mesmo do versao.json. É esta igualdade que ficou catorze versões
        quebrada."""
        with open(os.path.join(RAIZ, "versao.json"), encoding="utf-8") as f:
            esperado = json.load(f)["versao"]
        self.assertEqual(self.ns["_versao_do_pacote"](base=RAIZ), esperado)

    def test_VERSAO_ATUAL_NAO_e_mais_um_literal_no_codigo(self):
        """A regressão que este teste existe para pegar é alguém 'consertar'
        a versão escrevendo o número de volta aqui — que foi como ela
        divergiu da primeira vez."""
        codigo = _sem_comentarios(_fonte("main_app.py"))
        self.assertIn("VERSAO_ATUAL = _versao_do_pacote()", codigo)
        self.assertNotIn('VERSAO_ATUAL = "', codigo,
                         "VERSAO_ATUAL voltou a ser um número escrito à mão")

    def test_a_build_se_identifica_na_abertura(self):
        """Qualquer log que ele copie passa a dizer de que versão veio."""
        codigo = _fonte("main_app.py")
        i = codigo.index("plataforma.diagnostico()")
        trecho = codigo[max(0, i - 900):i]
        self.assertIn("VERSAO_ATUAL", trecho)
        self.assertIn("_data_do_arquivo", trecho)


# ---------------------------------------------------------------------------
# 2. O QUADRO DO ORBE — EXECUTADO DE VERDADE, COM CANVAS ESPIÃO
# ---------------------------------------------------------------------------
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

w, h, ligado, tem_img, aviso = %(args)r
c = _C()
r = T.CyberHUDCanvasRenderer(c, largura=w, altura=h)
r.definir_fundo_de_contexto("<IMG>" if tem_img else None, ligado=ligado, aviso=aviso)
r.desenhar()
textos = [k.get("text", "") for n, a, k in c.ch if n == "create_text"]
imgs = [i for i, (n, a, k) in enumerate(c.ch) if n == "create_image"]
quadro = [i for i, (n, a, k) in enumerate(c.ch)
          if n == "create_rectangle" and k.get("fill") == "#01060f"]
print(json.dumps({
    "area": r.area_do_cluster(),
    "imagens": imgs,
    "quadro": quadro,
    "textos": textos,
    "total": len(c.ch),
}))
'''


def _desenhar(w=1400, h=700, ligado=True, tem_img=True, aviso=""):
    """Roda o renderizador NUM SUBPROCESSO, com tkinter substituído por um
    Canvas que só anota o que foi pedido.

    Subprocesso, e não stub em `sys.modules`, porque trocar o tkinter do
    processo estragaria qualquer outro teste da suíte que rode depois — e um
    teste que quebra o vizinho é pior que teste nenhum."""
    codigo = _ESPIAO % {"raiz": RAIZ, "args": (w, h, ligado, tem_img, aviso)}
    saida = subprocess.run([sys.executable, "-c", codigo],
                           capture_output=True, text=True, timeout=60)
    assert saida.returncode == 0, saida.stderr
    return json.loads(saida.stdout.strip().splitlines()[-1])


class TestOQuadroDoOrbeDesenhaOGrafico(unittest.TestCase):

    def test_a_imagem_entra_no_quadro_em_todos_os_tamanhos(self):
        """A prova de que o renderizador nunca foi o problema. O defeito da
        v2.67.1 era o `main_app` mandar 52% da largura TOTAL — que num HUD de
        1400px virava 728px de imagem num quadro de 532."""
        for w, h in ((1900, 850), (1400, 700), (900, 280)):
            with self.subTest(hud=f"{w}x{h}"):
                d = _desenhar(w, h)
                self.assertEqual(len(d["imagens"]), 1)
                x1, y1, x2, y2 = d["area"]
                self.assertGreater(x2 - x1, 0)
                self.assertGreater(y2 - y1, 0)

    def test_o_quadro_e_desenhado_ANTES_da_imagem(self):
        """Ordem de desenho é ordem de camada no Canvas do Tkinter: quadro,
        imagem, e só então rosto e telemetria por cima."""
        d = _desenhar()
        self.assertLess(d["quadro"][0], d["imagens"][0])

    def test_o_quadro_existe_mesmo_com_o_fundo_DESLIGADO(self):
        """Ele é a MOLDURA, não o conteúdo. Sem isto, desligar o fundo deixa
        um vazio sem forma no meio do cockpit."""
        d = _desenhar(ligado=False)
        self.assertEqual(len(d["quadro"]), 1)
        self.assertEqual(len(d["imagens"]), 0)

    def test_o_quadro_tem_etiqueta_para_poder_ser_APONTADO(self):
        """Eu disse a ele 'o quadrado mais escuro cedido ao Orbe' e ele não
        tinha como identificar qual era."""
        d = _desenhar()
        self.assertTrue(any("CONTEXTO" in t for t in d["textos"]))

    def test_LIGADO_e_SEM_IMAGEM_escreve_o_motivo_NA_TELA(self):
        """O caso que ele viveu duas vezes. Quadro vazio não distingue
        'quebrou' de 'a captura ainda não existe' de 'cliquei errado' — e as
        três pedem ações diferentes de quem está na frente do computador."""
        d = _desenhar(tem_img=False, aviso="aguardando a primeira captura do motor")
        na_tela = [t for t in d["textos"] if "SEM IMAGEM" in t]
        self.assertEqual(len(na_tela), 1)
        self.assertIn("aguardando a primeira captura", na_tela[0])

    def test_com_imagem_o_quadro_NAO_escreve_aviso(self):
        """Aviso que aparece quando está tudo certo vira ruído, e ruído é a
        razão de ninguém ler o aviso no dia em que ele importa."""
        d = _desenhar(tem_img=True)
        self.assertFalse(any("SEM IMAGEM" in t for t in d["textos"]))

    def test_DESLIGADO_nao_escreve_aviso(self):
        """Desligado é escolha dele, não defeito."""
        d = _desenhar(ligado=False, tem_img=False, aviso="qualquer coisa")
        self.assertFalse(any("SEM IMAGEM" in t for t in d["textos"]))


class TestAAssinaturaAntigaContinuaValendo(unittest.TestCase):

    def test_definir_fundo_aceita_chamada_sem_aviso(self):
        """`aviso` entrou com padrão para que um renderizador ou chamador
        fora de sincronia não derrube o HUD — painel que não abre esconde
        posição aberta."""
        fonte = _fonte("tiger_hud.py")
        self.assertIn("def definir_fundo_de_contexto(self, imagem_tk, ligado=True, aviso=\"\")",
                      fonte)

    def test_o_chamador_tem_rede_para_renderizador_antigo(self):
        codigo = _sem_comentarios(_fonte("main_app.py"))
        # Ancorado na CHAMADA e não no `hasattr` que aparece antes — âncora
        # imprecisa mede o trecho errado do arquivo e falha sem defeito.
        i = codigo.index("r.definir_fundo_de_contexto(tk_fundo")
        self.assertIn("except TypeError", codigo[i:i + 400])


# ---------------------------------------------------------------------------
# 3. OS DOIS HUDs, E O RECIBO NO CLIQUE
# ---------------------------------------------------------------------------
class TestOsDoisHUDsSaoAlimentados(unittest.TestCase):

    def setUp(self):
        self.codigo = _sem_comentarios(_fonte("main_app.py"))

    def test_a_camada_de_fundo_percorre_embutido_E_solto(self):
        """O botão 'Desacoplar HUD (Solta)' está no cabeçalho, ao lado do
        'HUD Jarvis': é um caminho que ele toma sozinho, e o recurso
        simplesmente não existia lá."""
        i = self.codigo.index("def _alimentar_grafico_do_orbe")
        corpo = self.codigo[i:i + 1200]
        self.assertIn("hud_embutido", corpo)
        self.assertIn("_hud_jarvis", corpo)

    def test_sem_HUD_nenhum_ele_DIZ(self):
        i = self.codigo.index("def _alimentar_grafico_do_orbe")
        self.assertIn("_porque_sem_fundo", self.codigo[i:i + 1200])

    def test_cada_HUD_e_dimensionado_pela_PROPRIA_area(self):
        """A mesma PhotoImage em dois tamanhos ficaria certa num e esticada
        no outro."""
        i = self.codigo.index("def _alimentar_um_orbe")
        self.assertIn("area_do_cluster", self.codigo[i:i + 2200])


class TestOInterruptorDaRecibo(unittest.TestCase):

    def setUp(self):
        self.codigo = _sem_comentarios(_fonte("main_app.py"))
        i = self.codigo.index("def _alternar_contexto_de_fundo")
        self.corpo = self.codigo[i:i + 1600]

    def test_o_clique_conta_o_RESULTADO_e_nao_so_a_intencao(self):
        """Ele leu 'LIGADO', não viu gráfico, e escreveu 'ESTÁ LIGADO, MAS
        NÃO SUBIU'. Não havia como ele saber."""
        self.assertIn("_fundo_aplicado", self.corpo)

    def test_o_clique_zera_o_silenciador_para_ouvir_a_causa_de_novo(self):
        """`_porque_sem_fundo` fala uma vez por causa para não inundar o log a
        12 quadros por segundo. No clique manual, ele PRECISA ouvir de novo."""
        self.assertIn("_sem_fundo_dito = None", self.corpo)

    def test_o_recibo_traz_o_arquivo_e_as_medidas(self):
        i = self.codigo.index("def _alimentar_um_orbe")
        corpo = self.codigo[i:i + 3000]
        self.assertIn("os.path.basename(caminho)", corpo)
        self.assertIn("_fundo_aplicado", corpo)


class TestNadaMaisEEngolidoEmSilencio(unittest.TestCase):

    def test_o_caminho_periodico_nao_tem_mais_except_pass(self):
        """Era `except Exception: pass`. Um erro real ficava com a MESMA cara
        de 'ainda não há captura' — dois defeitos diferentes, um sintoma só."""
        codigo = _sem_comentarios(_fonte("main_app.py"))
        i = codigo.index("def _atualizar_telemetria_hud_embutido")
        j = codigo.index("_alimentar_grafico_do_orbe", i)
        trecho = codigo[j:j + 400]
        self.assertIn("_porque_sem_fundo", trecho)


if __name__ == "__main__":
    unittest.main(verbosity=2)
