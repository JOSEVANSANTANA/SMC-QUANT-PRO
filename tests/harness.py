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
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO = os.path.join(RAIZ, "main_app.py")

# A raiz do projeto entra no path para que `import plataforma` funcione nos
# testes. O plataforma.py é importável de verdade (todos os módulos de sistema
# dele entram com guarda), ao contrário do main_app.py, que sobe a janela.
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


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


def pular_se_faltar(*relativos):
    """Pula o teste quando o arquivo que ele examina não veio NESTE pacote.

    POR QUE ISTO EXISTE
    -------------------
    A suíte vai dentro dos DOIS zips, e os dois zips não têm os mesmos
    arquivos: o do Windows não leva `requirements-mac.txt` nem os `.command`,
    e o do cliente não leva o painel de licenças nem o atalho dele.

    Sem esta função, um cliente de Windows rodava `python tests/run.py` — que
    é exatamente o que o guia de entrega manda fazer — e via ONZE falhas
    vermelhas sobre arquivos do Mac que nunca deveriam estar ali. Nenhuma
    delas era defeito do programa; todas destruíam a confiança no programa.

    PULAR não é varrer para debaixo do tapete: o teste continua rodando (e
    falhando, se for o caso) no repositório e no pacote do sistema a que ele
    pertence. O que ele deixa de fazer é acusar a ausência de um arquivo que,
    naquele pacote, tem de estar ausente mesmo.
    """
    import unittest
    faltando = [r for r in relativos
                if not os.path.exists(os.path.join(RAIZ, r))]
    if faltando:
        raise unittest.SkipTest(
            "não faz parte deste pacote: " + ", ".join(faltando))
