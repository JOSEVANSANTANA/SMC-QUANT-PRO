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

    # AS CONSTANTES DE MÓDULO QUE O CÓDIGO PEDIDO USA VÊM JUNTO, SOZINHAS.
    #
    # 22/08: um commit acrescentou `_RE_AMBIENTE_OU_REPLAY` e passou a usá-lo
    # dentro de `interpretar_intencao`. A função continuou correta e o
    # aplicativo continuou funcionando — mas DEZOITO testes quebraram com
    # NameError, porque o namespace isolado só recebia os nomes listados em
    # cada `carregar([...])`. O teste acusava um defeito que não existia, e
    # consertar exigia editar a lista de cinco arquivos de teste.
    #
    # Isso fazia do harness uma armadilha: quem criasse uma constante nova
    # derrubava a suíte sem ter errado nada — e, pior, aprendia a desconfiar
    # dela. Uma suíte em que a falha nem sempre significa defeito para de ser
    # lida, e é justamente ela que segura as travas de dinheiro deste projeto.
    #
    # Só ATRIBUIÇÕES entram automaticamente, nunca funções ou classes. Cada
    # teste continua escolhendo a dedo QUAIS funções quer isolar, que é o
    # ponto do harness; o que ele deixa de exigir é a lista de constantes que
    # essas funções usam por dentro — detalhe de implementação que o teste não
    # tem como conhecer e que muda a cada refatoração legítima.
    constantes = {}
    for no in arvore.body:
        if isinstance(no, ast.Assign):
            for t in no.targets:
                if isinstance(t, ast.Name):
                    constantes[t.id] = no

    def _nomes_usados(no):
        return {n.id for n in ast.walk(no) if isinstance(n, ast.Name)}

    # Fecho transitivo: `_RE_ACAO_INVENTADA` é montada a partir de
    # `_ALEGACOES_FALSAS`, então trazer só a primeira não bastava.
    necessarias, fila = set(), []
    for no in arvore.body:
        nome = getattr(no, "name", None)
        if nome in procurados:
            fila.append(no)
        elif isinstance(no, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in procurados for t in no.targets):
            fila.append(no)
    while fila:
        atual = fila.pop()
        for usado in _nomes_usados(atual):
            if usado in constantes and usado not in necessarias and usado not in procurados:
                necessarias.add(usado)
                fila.append(constantes[usado])

    for no in arvore.body:
        alvo = None
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            alvo = no.name
        elif isinstance(no, ast.Assign):
            for t in no.targets:
                if isinstance(t, ast.Name) and (t.id in procurados or t.id in necessarias):
                    alvo = t.id
                    break
        if alvo and (alvo in procurados or alvo in necessarias):
            decoradores = getattr(no, "decorator_list", None)
            ini = (decoradores[0].lineno - 1) if decoradores else (no.lineno - 1)
            trechos.append("".join(linhas[ini:no.end_lineno]))
            if alvo in procurados:
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
