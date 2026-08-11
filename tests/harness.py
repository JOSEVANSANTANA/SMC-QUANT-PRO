"""Extrator de funções do main_app.py para teste, sem abrir a interface.

POR QUE ISTO EXISTE E POR QUE ESTÁ NO REPOSITÓRIO
--------------------------------------------------
O main_app.py importa customtkinter e sobe uma janela. Não dá para `import
main_app` num teste. A saída é ler o arquivo, pegar por AST APENAS as funções
e constantes que o teste precisa, e executá-las num namespace montado à mão —
com stubs no lugar do que toca disco.

E está DENTRO do repositório porque a suíte anterior morava fora dele e foi
destruída num reset de container. Teste que não é versionado não existe.

Uso:
    from harness import carregar
    ns = carregar(["calcular_contratos", "valor_por_ponto_do_ativo"],
                  stubs={"plano_da_conta_ativa": lambda: {}})
    ns["calcular_contratos"](...)
"""

import ast
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO = os.path.join(RAIZ, "main_app.py")


def _arvore(caminho=None):
    with open(caminho or ARQUIVO, encoding="utf-8") as f:
        fonte = f.read()
    return fonte, ast.parse(fonte)


def carregar(nomes, stubs=None, caminho=None):
    """Devolve um namespace com `nomes` (funções, classes ou constantes de
    módulo) definidos, na ordem em que aparecem no arquivo.

    Um nome que não for encontrado levanta AssertionError — silêncio aqui
    esconderia exatamente o tipo de erro que a suíte existe para pegar
    (função renomeada, teste testando o vazio)."""
    fonte, arvore = _arvore(caminho)
    linhas = fonte.splitlines(keepends=True)
    procurados = set(nomes)
    achados, trechos = set(), []

    for no in arvore.body:
        alvo = None
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            alvo = no.name
        elif isinstance(no, ast.Assign):
            for t in no.targets:
                if isinstance(t, ast.Name) and t.id in procurados:
                    alvo = t.id
                    break
        if alvo and alvo in procurados:
            decoradores = getattr(no, "decorator_list", None)
            ini = (decoradores[0].lineno - 1) if decoradores else (no.lineno - 1)
            trechos.append("".join(linhas[ini:no.end_lineno]))
            achados.add(alvo)

    faltando = procurados - achados
    assert not faltando, f"não achei no main_app.py: {sorted(faltando)}"

    ns = {"re": re, "os": os}
    import datetime
    import json
    import math
    import time
    ns.update({"datetime": datetime, "json": json, "math": math, "time": time})
    ns.update(stubs or {})
    exec("".join(trechos), ns)
    return ns


def fonte_do_arquivo(caminho=None):
    """O texto cru — para as verificações que são sobre o CÓDIGO, não sobre o
    comportamento (ex.: 'este arquivo ainda manda o usuário de Mac abrir uma
    tela do Windows?')."""
    with open(caminho or os.path.join(RAIZ, "main_app.py"), encoding="utf-8") as f:
        return f.read()
