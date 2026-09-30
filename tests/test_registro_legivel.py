""""NAO CONSIGO LER NADA, ELE É PRATICAMENTE FIXO, SE EU ROLAR A BARRA, O APP
INTEIRO VAI JUNTO."

Ele descreveu três sintomas e eram três defeitos DIFERENTES, cada um bastando
sozinho para inutilizar o campo. Nenhum era impressão.

1. NÃO TINHA BARRA DE ROLAGEM. Nenhuma. O `tk.Text` era criado solto, sem
   `yscrollcommand` e sem `Scrollbar` ao lado. Literalmente não havia o que
   arrastar — "praticamente fixo" era a descrição exata do que existia.

2. A RODA DO MOUSE ROLAVA A PÁGINA INTEIRA. Este tem causa localizável, e ela
   está no fonte do CustomTkinter que o projeto usa. O `CTkScrollableFrame`,
   que embala a aba, registra a roda com `bind_all` — a etiqueta "all" do Tk,
   que vale para o programa inteiro. Antes de rolar, ele pergunta em
   `_check_if_valid_scroll` se o widget sob o ponteiro tem rolagem própria, e
   a lista de exceções dele é FECHADA:

       elif isinstance(widget, (CTkScrollbar, CTkSlider, CTkTextbox)):
           return False

   Um `tk.Text` não é nenhum dos três. A função então sobe pelos `master` até
   o canvas e devolve True. Resultado: o evento vazava, a aba andava, e o log
   ficava parado. "O app inteiro vai junto", ao pé da letra.

   A cura é a ordem de etiquetas do Tk: widget → classe → janela → all. Tratar
   a roda no nível do WIDGET e devolver "break" encerra a fila ANTES do "all",
   que é onde mora o sequestro.

3. CADA LINHA NOVA CHAMAVA see(END). Com o motor ligado chega linha a cada
   poucos segundos. Mesmo que houvesse barra, o texto seria arrancado de volta
   para o fim antes de ele terminar de ler a linha. Agora a rolagem automática
   só acontece se ele JÁ estiver no fim — e o botão avisa, mudando de cor,
   quando chegou coisa nova enquanto ele lia mais acima.

E o campo, que era `height=22` cravado no código, virou preferência guardada.

POR QUE ESTES TESTES SÃO ASSIM
-------------------------------
O código mora dentro da classe da janela, que não dá para importar (subir a
interface num teste é o que a suíte existe para evitar). Então cada método é
extraído por AST e executado sozinho, com um `self` de mentira e um campo de
texto de mentira que só ANOTA o que foi pedido. É o que permite afirmar coisas
como "não chamou see(END)" — que é o defeito 3 — sem abrir janela nenhuma.
"""

import ast
import os
import sys
import unittest

from harness import RAIZ

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


_CACHE = {}


def _fonte(nome="main_app.py"):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


def _arvore():
    """O main_app tem ~25 mil linhas; reanalisá-lo a cada teste levava a suíte
    inteira a dezenas de segundos por si só."""
    if "arvore" not in _CACHE:
        fonte = _fonte()
        _CACHE["fonte"] = fonte
        _CACHE["arvore"] = ast.parse(fonte)
    return _CACHE["fonte"], _CACHE["arvore"]


def _constantes():
    """As constantes de módulo do main_app que estes métodos usam."""
    if "constantes" in _CACHE:
        return _CACHE["constantes"]
    fora = {}
    for no in _arvore()[1].body:
        if isinstance(no, ast.Assign) and len(no.targets) == 1 \
                and isinstance(no.targets[0], ast.Name) \
                and isinstance(no.value, ast.Constant):
            fora[no.targets[0].id] = no.value.value
    _CACHE["constantes"] = fora
    return fora


def metodo(nome, extras=None):
    """Puxa UM método da classe da janela e devolve como função solta.

    Sem instanciar nada: o `self` é passado à mão pelo teste."""
    fonte, arvore = _arvore()
    linhas = fonte.splitlines(keepends=True)
    for classe in arvore.body:
        if not isinstance(classe, ast.ClassDef):
            continue
        for no in classe.body:
            if isinstance(no, ast.FunctionDef) and no.name == nome:
                trecho = "".join(linhas[no.lineno - 1:no.end_lineno])
                # tira os 4 espaços de indentação da classe
                trecho = "\n".join(l[4:] if l.startswith("    ") else l
                                   for l in trecho.splitlines())
                espaco = dict(_constantes())
                espaco.update(extras or {})
                exec(compile(trecho, "<metodo>", "exec"), espaco)
                return espaco[nome]
    raise AssertionError(f"não achei o método {nome} na classe da janela")


def corpo(nome):
    """O CÓDIGO de um método, sem docstring nem comentário — para as regras
    que são sobre o fonte. Sem isto, um teste que procura "see(" acabaria
    casando com o comentário que EXPLICA o defeito antigo, e passaria a punir
    quem documenta."""
    for classe in _arvore()[1].body:
        if not isinstance(classe, ast.ClassDef):
            continue
        for no in classe.body:
            if isinstance(no, ast.FunctionDef) and no.name == nome:
                itens = list(no.body)
                if (itens and isinstance(itens[0], ast.Expr)
                        and isinstance(itens[0].value, ast.Constant)
                        and isinstance(itens[0].value.value, str)):
                    itens = itens[1:]
                return "\n".join(ast.unparse(n) for n in itens)
    raise AssertionError(f"não achei o método {nome}")


class _Campo:
    """Um campo de texto que só ANOTA o que pediram a ele."""

    def __init__(self, linhas=1, fim=1.0):
        self.linhas = linhas
        self.fim = fim
        self.escrito = []
        self.viu_o_fim = 0
        self.rolagens = []
        self.apagado = []
        self.config = {}
        self.ligacoes = {}
        self.existe = True

    def yview(self):
        return (0.0, self.fim)

    def yview_scroll(self, quanto, _unidade):
        self.rolagens.append(quanto)

    def insert(self, _onde, texto):
        self.escrito.append(texto)
        self.linhas += texto.count("\n")

    def see(self, _onde):
        self.viu_o_fim += 1
        self.fim = 1.0

    def delete(self, de, ate):
        self.apagado.append((de, ate))
        self.linhas -= int(str(ate).split(".")[0]) - int(str(de).split(".")[0])

    def index(self, _expr):
        return f"{self.linhas}.0"

    def get(self, _de, _ate):
        return "".join(self.escrito)

    def configure(self, **kw):
        self.config.update(kw)

    def bind(self, evento, funcao):
        self.ligacoes[evento] = funcao

    def winfo_exists(self):
        return self.existe


class _Botao:
    def __init__(self):
        self.config = {}

    def configure(self, **kw):
        self.config.update(kw)


class _Janela:
    """O `self` de mentira. Só carrega o que os métodos tocam."""

    def __init__(self, campo=None, altura=22):
        self.console = campo if campo is not None else _Campo()
        self.btn_fim_do_log = _Botao()
        self.lbl_altura_log = _Botao()
        self.barra_do_console = _Botao()
        self.barra_do_console.set = lambda a, b: self.barra_do_console.config.update(
            {"faixa": (a, b)})
        self._texto_do_log_grande = None
        self.altura = altura
        self.gravado = {}
        self.registrado = []

    def log(self, msg):
        self.registrado.append(msg)


_TK = type("tk", (), {"END": "end"})


def _com(*metodos, **extras):
    """Monta uma janela de mentira com os métodos pedidos já ligados nela."""
    janela = extras.pop("janela", None) or _Janela()
    ambiente = {
        "tk": _TK,
        "carregar_config": lambda: {"altura_do_log": janela.altura},
        "salvar_config": janela.gravado.update,
    }
    ambiente.update(extras)
    for nome in metodos:
        setattr(type(janela), nome, metodo(nome, ambiente))
    return janela


class ARodaDoMouseFicaDentroDoCampo(unittest.TestCase):
    """O defeito 2 — "se eu rolar a barra, o app inteiro vai junto"."""

    def _handler(self):
        janela = _com("_prender_a_roda")
        campo = _Campo()
        janela._prender_a_roda(campo)
        return campo

    def test_liga_os_tres_eventos_de_roda(self):
        """Windows e Mac mandam <MouseWheel>; o X11 manda Button-4 e 5. Faltar
        um deixa o defeito vivo num sistema inteiro."""
        campo = self._handler()
        for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.assertIn(evento, campo.ligacoes)

    def test_TODO_tratador_devolve_break(self):
        """ESTA é a linha que conserta o sintoma dele. Sem o "break", a fila de
        etiquetas do Tk segue até "all", que é onde o CTkScrollableFrame está
        esperando para rolar a aba inteira."""
        campo = self._handler()
        eventos = {
            "<MouseWheel>": type("e", (), {"delta": 120, "num": None}),
            "<Button-4>": type("e", (), {"delta": 0, "num": 4}),
            "<Button-5>": type("e", (), {"delta": 0, "num": 5}),
        }
        for nome, evento in eventos.items():
            self.assertEqual(campo.ligacoes[nome](evento()), "break",
                             f"{nome} não devolveu 'break' — a página volta a "
                             "andar junto com o log")

    def test_roda_para_cima_sobe_e_para_baixo_desce(self):
        campo = self._handler()
        campo.ligacoes["<Button-4>"](type("e", (), {"delta": 0, "num": 4})())
        campo.ligacoes["<Button-5>"](type("e", (), {"delta": 0, "num": 5})())
        self.assertLess(campo.rolagens[0], 0, "roda para cima desceu o texto")
        self.assertGreater(campo.rolagens[1], 0)

    def test_windows_manda_multiplo_de_120_e_isso_nao_vira_360_linhas(self):
        """delta=120 é UM clique de roda. Usar o número cru rolaria o log
        inteiro num toque."""
        campo = self._handler()
        campo.ligacoes["<MouseWheel>"](
            type("e", (), {"delta": 120, "num": None})())
        self.assertEqual(abs(campo.rolagens[0]), 3)

    def test_mac_manda_a_contagem_ja_pronta(self):
        campo = self._handler()
        campo.ligacoes["<MouseWheel>"](
            type("e", (), {"delta": 2, "num": None})())
        self.assertEqual(campo.rolagens[0], -2)

    def test_delta_zero_nao_mexe_no_texto_mas_ainda_segura_o_evento(self):
        campo = self._handler()
        saida = campo.ligacoes["<MouseWheel>"](
            type("e", (), {"delta": 0, "num": None})())
        self.assertEqual(saida, "break")
        self.assertEqual(campo.rolagens, [])


class LinhaNovaNaoArrancaALeitura(unittest.TestCase):
    """O defeito 3 — "é praticamente fixo"."""

    def _logar(self, fim, campo=None):
        campo = campo or _Campo(linhas=10, fim=fim)
        janela = _com("log", "_console_no_fim", "_aparar_console",
                      "_ecoar_no_log_grande",
                      janela=_Janela(campo=campo))
        # `after` executa na hora: o teste quer o efeito, não o agendamento.
        janela.after = lambda _ms, f: f()
        janela.log("linha nova")
        return campo

    def test_lendo_mais_acima_o_texto_NAO_pula_para_o_fim(self):
        campo = self._logar(fim=0.4)
        self.assertEqual(campo.escrito, ["linha nova\n"],
                         "não escreveu a linha")
        self.assertEqual(campo.viu_o_fim, 0,
                         "arrancou a leitura dele de volta para o fim — é "
                         "exatamente o defeito relatado")

    def test_ja_estando_no_fim_ele_continua_acompanhando_sozinho(self):
        """A trava não pode virar o contrário: quem está no fim quer ver
        chegar."""
        campo = self._logar(fim=1.0)
        self.assertEqual(campo.viu_o_fim, 1)

    def test_a_decisao_e_tomada_ANTES_de_escrever(self):
        """Depois da inserção a visão já mudou, e a conta responderia sobre o
        texto novo em vez do que ele estava lendo."""
        codigo = corpo("log")
        self.assertLess(codigo.index("_console_no_fim"), codigo.index("insert"),
                        "perguntou 'estava no fim?' depois de já ter escrito")

    def test_o_see_do_fim_esta_sob_condicao_nunca_solto(self):
        codigo = corpo("log")
        self.assertIn("if colado_no_fim", codigo)

    def test_a_janela_grande_tambem_respeita_a_posicao_de_leitura(self):
        grande = _Campo(fim=0.3)
        janela = _com("_ecoar_no_log_grande")
        janela._texto_do_log_grande = grande
        janela._ecoar_no_log_grande("chegou")
        self.assertEqual(grande.escrito, ["chegou\n"])
        self.assertEqual(grande.viu_o_fim, 0)

    def test_janela_grande_ja_fechada_e_esquecida_sem_estourar(self):
        grande = _Campo()
        grande.existe = False
        janela = _com("_ecoar_no_log_grande")
        janela._texto_do_log_grande = grande
        janela._ecoar_no_log_grande("chegou")
        self.assertIsNone(janela._texto_do_log_grande)


class OBotaoAvisaQueChegouCoisaNova(unittest.TestCase):

    def test_fora_do_fim_o_botao_muda_de_cor_e_de_texto(self):
        janela = _com("_console_rolou", "_pintar_botao_do_fim")
        janela._console_rolou(0.2, 0.5)
        self.assertIn("IR PARA O FIM", janela.btn_fim_do_log.config["text"])
        self.assertNotEqual(janela.btn_fim_do_log.config["fg_color"], "#2a3f5f")

    def test_no_fim_ele_volta_ao_normal(self):
        janela = _com("_console_rolou", "_pintar_botao_do_fim")
        janela._console_rolou(0.6, 1.0)
        self.assertIn("fim", janela.btn_fim_do_log.config["text"].lower())
        self.assertEqual(janela.btn_fim_do_log.config["fg_color"], "#2a3f5f")

    def test_a_barra_de_rolagem_recebe_a_faixa(self):
        """Se o yscrollcommand não repassar, a barra fica desenhada e morta."""
        janela = _com("_console_rolou", "_pintar_botao_do_fim")
        janela._console_rolou(0.2, 0.5)
        self.assertEqual(janela.barra_do_console.config["faixa"], (0.2, 0.5))

    def test_o_botao_leva_de_volta_ao_fim(self):
        janela = _com("_ir_para_o_fim_do_log", "_pintar_botao_do_fim")
        janela._ir_para_o_fim_do_log()
        self.assertEqual(janela.console.viu_o_fim, 1)


class OTamanhoDeixouDeSerCravado(unittest.TestCase):

    def test_a_altura_vem_da_preferencia(self):
        janela = _com("_altura_do_log", janela=_Janela(altura=40))
        self.assertEqual(janela._altura_do_log(), 40)

    def test_valor_absurdo_no_arquivo_nao_inutiliza_a_janela(self):
        for gravado, esperado in ((9999, "teto"), (-3, "piso"), ("xis", "padrão")):
            janela = _com("_altura_do_log", janela=_Janela(altura=gravado))
            altura = janela._altura_do_log()
            self.assertGreaterEqual(altura, 8, esperado)
            self.assertLessEqual(altura, 60, esperado)

    def test_mudar_grava_aplica_e_atualiza_o_rotulo(self):
        janela = _com("_altura_do_log", "_mudar_altura_do_log",
                      janela=_Janela(altura=22))
        janela._mudar_altura_do_log(+4)
        self.assertEqual(janela.gravado["altura_do_log"], 26)
        self.assertEqual(janela.console.config["height"], 26)
        self.assertIn("26", janela.lbl_altura_log.config["text"])

    def test_nao_passa_do_teto_nem_do_piso(self):
        janela = _com("_altura_do_log", "_mudar_altura_do_log",
                      janela=_Janela(altura=60))
        janela._mudar_altura_do_log(+4)
        self.assertEqual(janela.gravado["altura_do_log"], 60)


class ORegistroNaoCresceSemFim(unittest.TestCase):

    def test_abaixo_do_teto_nao_apaga_nada(self):
        campo = _Campo(linhas=100)
        janela = _com("_aparar_console", janela=_Janela(campo=campo))
        janela._aparar_console()
        self.assertEqual(campo.apagado, [])

    def test_corta_so_depois_da_folga_e_corta_em_bloco(self):
        """Apagar do início de um Text é caro. Cortar linha a linha custaria
        mais que o problema que resolve."""
        campo = _Campo(linhas=6000)
        janela = _com("_aparar_console", janela=_Janela(campo=campo))
        janela._aparar_console()
        self.assertEqual(len(campo.apagado), 1)
        self.assertEqual(campo.apagado[0][0], "1.0")
        self.assertEqual(campo.linhas, 4000,
                         "sobrou um número de linhas diferente do teto")

    def test_logo_acima_do_teto_ainda_nao_corta(self):
        campo = _Campo(linhas=4200)
        janela = _com("_aparar_console", janela=_Janela(campo=campo))
        janela._aparar_console()
        self.assertEqual(campo.apagado, [])


class RegrasDoFonte(unittest.TestCase):

    def test_o_campo_do_log_tem_barra_de_rolagem_de_verdade(self):
        """O defeito 1: ele era criado solto, sem barra nenhuma."""
        fonte = _fonte()
        trecho = fonte.split("self.console = tk.Text(")[1][:2000]
        self.assertIn("CTkScrollbar", trecho,
                      "o campo do log continua sem barra para arrastar")
        self.assertIn("yscrollcommand", trecho)

    def test_a_roda_e_presa_no_campo_do_log(self):
        fonte = _fonte()
        trecho = fonte.split("self.console = tk.Text(")[1][:2000]
        self.assertIn("_prender_a_roda(self.console)", trecho)

    def test_a_janela_grande_tambem_prende_a_roda(self):
        """bind_all é do interpretador inteiro, não da janela: sem prender
        aqui, rolar na janela do log mexeria a aba lá atrás."""
        self.assertIn("_prender_a_roda(texto)", corpo("_abrir_log_em_janela"))

    def test_a_altura_nao_volta_a_ser_numero_cravado(self):
        fonte = _fonte()
        trecho = fonte.split("self.console = tk.Text(")[1][:400]
        self.assertIn("self._altura_do_log()", trecho)
        self.assertNotIn("height=22", trecho)

    def test_o_texto_quebra_por_PALAVRA(self):
        """O padrão do Tk quebra no meio da palavra. Num log cheio de caminho
        de arquivo e mensagem de erro, isso sozinho já atrapalha a leitura."""
        fonte = _fonte()
        trecho = fonte.split("self.console = tk.Text(")[1][:600]
        self.assertIn('wrap="word"', trecho)


if __name__ == "__main__":
    unittest.main(verbosity=2)
