"""Nenhum nome usado no código pode ser um nome que não existe.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
18/08, log do motor dele, ciclo após ciclo:

    📊 Ativo: MES | Leitura IA: SELL | Confiança: 72% | Preço: 6512.75
    🔎 Confluências identificadas:
        • ...
    ⚠️ Erro ao analisar: name 'analise' is not defined

E a frase dele: "o que voce fez que ate mais cedo tudo funcionava
perfeitamente, o que voce incluiu nessa ultima atualizacao que esta dando
esse erro agora?"

Fui eu. Na v2.43.0 escrevi `(analise or {}).get("indicadores_na_tela")`
dentro do laço do motor. O dicionário da leitura ali se chama `sinal`;
`analise` é só uma CHAVE de texto, nunca uma variável. Python não reclama
disso na hora de importar — o nome só é procurado quando a linha roda. E a
linha rodava tarde, DEPOIS de ler o gráfico e imprimir as confluências: o
log parecia saudável até a última linha, e nenhuma sugestão saía.

Compilar não pega. Rodar a suíte não pega, porque nenhum teste sobe o laço
do motor inteiro. O que pega é ler o arquivo e conferir, nome por nome, se
cada nome usado está ligado em algum escopo que o alcança. É o que este
arquivo faz — sem depender de pyflakes instalado, porque a máquina DELE não
tem pyflakes, e um teste que pula na máquina do dono não protege ninguém.

O critério é conservador de propósito: um nome só é acusado quando não está
ligado em lugar NENHUM que o alcance (nem no escopo, nem em nenhum escopo
acima, nem no módulo, nem nos builtins). Falso positivo aqui custa caro.
"""

import ast
import builtins
import os
import unittest

from harness import ARQUIVO, RAIZ, pular_se_faltar

# Nomes que existem em tempo de execução sem estarem escritos em lugar nenhum.
IMPLICITOS = {
    "__file__", "__name__", "__doc__", "__builtins__", "__spec__",
    "__package__", "__loader__", "__debug__", "__class__", "__module__",
    "__qualname__", "__dict__",
}


def _alvos(no):
    """Todos os nomes ligados por um alvo de atribuição (a, (b, c), [d], *e)."""
    if isinstance(no, ast.Name):
        yield no.id
    elif isinstance(no, (ast.Tuple, ast.List)):
        for e in no.elts:
            yield from _alvos(e)
    elif isinstance(no, ast.Starred):
        yield from _alvos(no.value)
    # Attribute e Subscript (self.x = 1, d["k"] = 1) não ligam nome nenhum.


def _ligados_no_padrao(no):
    """Nomes ligados por um `match`/`case`."""
    for sub in ast.walk(no):
        if isinstance(sub, (ast.MatchAs, ast.MatchStar)) and sub.name:
            yield sub.name
        elif isinstance(sub, ast.MatchMapping) and sub.rest:
            yield sub.rest


def _e_escopo(no):
    return isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                           ast.ClassDef, ast.ListComp, ast.SetComp,
                           ast.DictComp, ast.GeneratorExp))


def _corpo_do_escopo(no):
    """Os nós que pertencem ao escopo `no` — não o que é avaliado fora dele.

    Decoradores, valores-padrão de argumento e bases de classe rodam no escopo
    de FORA, então não entram aqui. O primeiro iterável de uma compreensão
    também é avaliado fora.
    """
    if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return list(no.body)
    if isinstance(no, ast.Lambda):
        return [no.body]
    if isinstance(no, ast.ClassDef):
        return list(no.body)
    # Compreensões: tudo menos o iterável do primeiro `for`.
    partes = []
    if isinstance(no, ast.DictComp):
        partes += [no.key, no.value]
    else:
        partes.append(no.elt)
    for i, ger in enumerate(no.generators):
        partes.append(ger.target)
        if i:
            partes.append(ger.iter)
        partes += list(ger.ifs)
    return partes


def _argumentos(no):
    a = no.args
    for arg in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
                + [a.vararg, a.kwarg]):
        if arg is not None:
            yield arg.arg


def ligados(no):
    """Nomes ligados DENTRO do escopo `no`, sem entrar nos escopos aninhados.

    O nome de uma função/classe aninhada é ligado aqui (é isso que permite
    chamá-la depois); o corpo dela, não.
    """
    nomes = set()
    if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        nomes.update(_argumentos(no))
    if isinstance(no, (ast.ListComp, ast.SetComp, ast.DictComp,
                       ast.GeneratorExp)):
        # `{x for x in lista}` — o alvo de cada `for` é ligado AQUI, no escopo
        # da própria compreensão, e é a única coisa que o `elt` enxerga.
        for ger in no.generators:
            nomes.update(_alvos(ger.target))

    pilha = list(_corpo_do_escopo(no)) if _e_escopo(no) else list(
        ast.iter_child_nodes(no))
    while pilha:
        atual = pilha.pop()
        if isinstance(atual, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
            nomes.add(atual.name)
            # O corpo não entra, mas decorador/padrão/base rodam AQUI fora.
            pilha += list(getattr(atual, "decorator_list", []))
            if not isinstance(atual, ast.ClassDef):
                a = atual.args
                pilha += [d for d in a.defaults if d is not None]
                pilha += [d for d in a.kw_defaults if d is not None]
            continue
        if isinstance(atual, ast.Lambda):
            a = atual.args
            pilha += [d for d in a.defaults if d is not None]
            pilha += [d for d in a.kw_defaults if d is not None]
            continue
        if isinstance(atual, (ast.ListComp, ast.SetComp, ast.DictComp,
                              ast.GeneratorExp)):
            # O walrus dentro de uma compreensão liga no escopo de FORA.
            for sub in ast.walk(atual):
                if isinstance(sub, ast.NamedExpr):
                    nomes.update(_alvos(sub.target))
            if atual.generators:
                pilha.append(atual.generators[0].iter)
            continue

        if isinstance(atual, (ast.Assign,)):
            for t in atual.targets:
                nomes.update(_alvos(t))
        elif isinstance(atual, (ast.AugAssign, ast.AnnAssign, ast.NamedExpr)):
            nomes.update(_alvos(atual.target))
        elif isinstance(atual, (ast.For, ast.AsyncFor, ast.comprehension)):
            nomes.update(_alvos(atual.target))
        elif isinstance(atual, ast.withitem):
            if atual.optional_vars is not None:
                nomes.update(_alvos(atual.optional_vars))
        elif isinstance(atual, ast.ExceptHandler):
            if atual.name:
                nomes.add(atual.name)
        elif isinstance(atual, (ast.Import, ast.ImportFrom)):
            for a in atual.names:
                nomes.add(a.asname or a.name.split(".")[0])
        elif isinstance(atual, (ast.Global, ast.Nonlocal)):
            nomes.update(atual.names)
        elif isinstance(atual, ast.match_case):
            nomes.update(_ligados_no_padrao(atual.pattern))

        pilha += list(ast.iter_child_nodes(atual))
    return nomes


def _usos(no):
    """Nomes LIDOS diretamente neste escopo (sem entrar nos aninhados)."""
    pilha = list(_corpo_do_escopo(no)) if _e_escopo(no) else list(
        ast.iter_child_nodes(no))
    while pilha:
        atual = pilha.pop()
        if _e_escopo(atual):
            # O que roda fora do escopo aninhado é uso DAQUI.
            pilha += list(getattr(atual, "decorator_list", []))
            if isinstance(atual, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.Lambda)):
                a = atual.args
                pilha += [d for d in a.defaults if d is not None]
                pilha += [d for d in a.kw_defaults if d is not None]
            elif isinstance(atual, ast.ClassDef):
                pilha += list(atual.bases) + [k.value for k in atual.keywords]
            elif atual.generators:
                pilha.append(atual.generators[0].iter)
            continue
        if isinstance(atual, ast.Name) and isinstance(atual.ctx, ast.Load):
            yield atual.id, atual.lineno
        pilha += list(ast.iter_child_nodes(atual))


def escopos_aninhados(no):
    """Os escopos filhos diretos de `no`."""
    pilha = list(_corpo_do_escopo(no)) if _e_escopo(no) else list(
        ast.iter_child_nodes(no))
    while pilha:
        atual = pilha.pop()
        if _e_escopo(atual):
            yield atual
            continue
        pilha += list(ast.iter_child_nodes(atual))


def nomes_indefinidos(fonte, arquivo="<fonte>"):
    """Devolve [(arquivo, linha, nome)] dos nomes que não existem em lugar
    nenhum que os alcance."""
    arvore = ast.parse(fonte)
    embutidos = set(dir(builtins)) | IMPLICITOS
    achados = []

    def descer(no, visiveis):
        # Escopo de CLASSE não é visível para as funções de dentro dele, mas
        # incluí-lo só torna o teste mais permissivo — e permissivo aqui é o
        # lado seguro de errar.
        aqui = visiveis | ligados(no)
        for nome, linha in _usos(no):
            if nome not in aqui and nome not in embutidos:
                achados.append((arquivo, linha, nome))
        for filho in escopos_aninhados(no):
            descer(filho, aqui)

    descer(arvore, set())
    return sorted(set(achados), key=lambda x: x[1])


class TestNomesIndefinidos(unittest.TestCase):

    def test_o_defeito_de_18_08_seria_pego(self):
        """A linha exata que matou todo ciclo do motor dele."""
        fonte = (
            "def motor(sinal):\n"
            "    confluencias = sinal.get('confluencias')\n"
            "    indicadores = (analise or {}).get('indicadores_na_tela') or []\n"
            "    return confluencias, indicadores\n"
        )
        achados = nomes_indefinidos(fonte, "motor_falso.py")
        self.assertEqual([(a[1], a[2]) for a in achados], [(3, "analise")],
                         "o checador não pegaria o erro que ele viu no log")

    def test_main_app_nao_usa_nenhum_nome_inexistente(self):
        with open(ARQUIVO, encoding="utf-8") as f:
            fonte = f.read()
        achados = nomes_indefinidos(fonte, "main_app.py")
        if achados:
            linhas = "\n".join(f"  main_app.py:{l}: nome inexistente {n!r}"
                               for _, l, n in achados)
            self.fail(
                "nome usado que não existe em escopo nenhum — em tempo de "
                "execução isso vira NameError e derruba o ciclo:\n" + linhas)

    def test_os_outros_arquivos_do_pacote_tambem(self):
        for relativo in ("plataforma.py", "empacotar.py", "gerar_licenca.py"):
            caminho = os.path.join(RAIZ, relativo)
            if not os.path.exists(caminho):
                continue
            with open(caminho, encoding="utf-8") as f:
                fonte = f.read()
            achados = nomes_indefinidos(fonte, relativo)
            self.assertEqual(
                achados, [],
                f"{relativo} usa nome que não existe: "
                + ", ".join(f"linha {l}: {n!r}" for _, l, n in achados))

    def test_os_proprios_testes_passam_pelo_mesmo_crivo(self):
        """Teste com NameError dentro passa despercebido como 'erro', não como
        falha, e é fácil de ignorar. Aqui não."""
        pasta = os.path.dirname(os.path.abspath(__file__))
        for arquivo in sorted(os.listdir(pasta)):
            if not arquivo.endswith(".py"):
                continue
            with open(os.path.join(pasta, arquivo), encoding="utf-8") as f:
                fonte = f.read()
            achados = nomes_indefinidos(fonte, arquivo)
            self.assertEqual(
                achados, [],
                f"tests/{arquivo} usa nome que não existe: "
                + ", ".join(f"linha {l}: {n!r}" for _, l, n in achados))


if __name__ == "__main__":
    unittest.main()
