"""EM REPLAY, O ROBÔ PAROU DE SUGERIR — e a leitura estava pronta.

22/08, 15:39 em diante, com Market Replay ligado (RPL2893430-7, 400%). Ciclo
após ciclo, o log mostrava a análise COMPLETA e nada saía:

    📊 Ativo: MESU6 | Leitura IA: BUY | Confiança: 75.0% | Probabilidade: 72.0%
    🔎 Confluências: Bullish Order Block · Fair Value Gap · Discount Zone ...
    🐞 DEFEITO DO PROGRAMA em main_app.py:22200: cannot access local variable
       'eventos_macro' where it is not associated with a value.

A causa: o ramo do replay definia `bloco_macro = ""` e parava aí. A variável
`eventos_macro` só nascia no `else`, onde as notícias do dia são buscadas —
e lá embaixo o código a usa SEM condição. Em mercado ao vivo o `else` sempre
rodava e ninguém via nada; em replay, o programa parava de sugerir.

O teste abaixo não guarda o nome `eventos_macro`. Guarda a REGRA que evita a
família inteira: num if/else, o que um lado define o outro também tem de
definir — senão quem usa depois herda uma bomba que só estoura num dos
caminhos. É o tipo de defeito que passa em toda revisão e aparece no pregão.
"""

import ast
import unittest

from harness import fonte_do_arquivo


def _ifs_com_else(arvore):
    for no in ast.walk(arvore):
        if isinstance(no, ast.If) and no.orelse:
            # `elif` chega aqui como um If dentro do orelse; só interessa o
            # if/else de verdade, com corpo em ambos os lados.
            if len(no.orelse) == 1 and isinstance(no.orelse[0], ast.If):
                continue
            yield no


def _nomes_definidos_antes(arvore, no_if):
    """Nomes já atribuídos ANTES deste if, na mesma função.

    Definir a variável antes do ramo é a defesa MELHOR que a simetria: cada
    ramo passa a sobrescrever só o que precisa, e um ramo novo já nasce
    seguro. O teste tem de reconhecer isso, senão empurraria para a solução
    pior — repetir a atribuição nos dois lados e torcer para ninguém
    esquecer no terceiro.
    """
    seguros = set()
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not (no.lineno <= no_if.lineno <= (no.end_lineno or no.lineno)):
            continue
        for filho in ast.walk(no):
            if isinstance(filho, ast.Assign) and filho.lineno < no_if.lineno:
                for alvo in filho.targets:
                    if isinstance(alvo, ast.Name):
                        seguros.add(alvo.id)
                    elif isinstance(alvo, ast.Tuple):
                        seguros.update(e.id for e in alvo.elts
                                       if isinstance(e, ast.Name))
    return seguros


def _lidos_depois(arvore, no_if):
    """Nomes LIDOS depois que o if/else termina, na mesma função.

    Este é o critério que importa, e não a convenção do sublinhado. Uma
    variável que nasce só num ramo é inofensiva enquanto morre nesse ramo —
    `_rpl_conta` e `_rpl_vel`, por exemplo, existem para montar o texto do
    replay e acabam ali. O que mata o ciclo é o nome que UM ramo define e o
    código LÁ DE BAIXO usa, sem saber por qual caminho chegou. Foi assim com
    `eventos_macro`.
    """
    lidos = set()
    fim = no_if.end_lineno or no_if.lineno
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not (no.lineno <= no_if.lineno <= (no.end_lineno or no.lineno)):
            continue
        for filho in ast.walk(no):
            if (isinstance(filho, ast.Name)
                    and isinstance(filho.ctx, ast.Load)
                    and filho.lineno > fim):
                lidos.add(filho.id)
    return lidos


def _nomes_atribuidos(corpo):
    nomes = set()
    for no in corpo:
        for filho in ast.walk(no):
            if isinstance(filho, ast.Assign):
                for alvo in filho.targets:
                    if isinstance(alvo, ast.Name):
                        nomes.add(alvo.id)
                    elif isinstance(alvo, ast.Tuple):
                        nomes.update(e.id for e in alvo.elts
                                     if isinstance(e, ast.Name))
    return nomes


class TestOsDoisLadosDoRamoDoReplay(unittest.TestCase):

    def _o_if_do_replay(self):
        arvore = ast.parse(fonte_do_arquivo())
        for no in _ifs_com_else(arvore):
            teste = ast.dump(no.test)
            if "_eh_replay" in teste:
                return no
        self.fail("não achei o if/else que separa replay de mercado ao vivo")

    def test_o_ramo_do_replay_define_tudo_que_o_outro_define(self):
        """O defeito de 22/08, guardado pela regra e não pelo nome."""
        arvore = ast.parse(fonte_do_arquivo())
        no = self._o_if_do_replay()
        seguros = _nomes_definidos_antes(arvore, no)
        no_replay = _nomes_atribuidos(no.body) | seguros
        no_ao_vivo = _nomes_atribuidos(no.orelse) | seguros
        # Só condena o que o código de baixo realmente vai LER.
        usados = _lidos_depois(arvore, no)
        so_ao_vivo = (no_ao_vivo - no_replay) & usados
        so_replay = (no_replay - no_ao_vivo) & usados
        self.assertEqual(
            so_ao_vivo, set(),
            "estas variáveis nascem só quando NÃO é replay: %s. Em replay "
            "elas chegam ao código de baixo sem valor, e o ciclo morre — foi "
            "exatamente o que aconteceu com 'eventos_macro'." % sorted(so_ao_vivo))
        self.assertEqual(
            so_replay, set(),
            "estas nascem só EM replay: %s — o espelho do mesmo defeito, "
            "esperando o mercado abrir para aparecer." % sorted(so_replay))

    def test_eventos_macro_nasce_antes_do_ramo(self):
        """A defesa estrutural: inicializar antes do `if` faz um ramo novo
        (outro modo de simulação, amanhã) já nascer seguro, sem ninguém
        precisar lembrar desta lição."""
        fonte = fonte_do_arquivo()
        i = fonte.index("_eh_replay = bool(")
        j = fonte.index("if _eh_replay:", i)
        antes = fonte[i:j]
        self.assertIn("eventos_macro", antes)
        self.assertIn("bloco_macro", antes)


class TestNenhumRamoDeixaVariavelSoltaNoCicloDeAnalise(unittest.TestCase):
    """A mesma regra, varrida sobre TODO if/else do arquivo.

    Não é perfeccionismo: `eventos_macro` passou por revisão, por suíte e por
    dois agentes, e só apareceu no pregão — em replay, que é justamente onde
    o trader testa antes de arriscar dinheiro. Uma varredura barata que pega
    a família inteira vale mais que um teste para cada nome.
    """

    def test_lista_os_desequilibrios_conhecidos_e_nao_cresce(self):
        arvore = ast.parse(fonte_do_arquivo())
        desequilibrados = []
        for no in _ifs_com_else(arvore):
            seguros = _nomes_definidos_antes(arvore, no)
            corpo = _nomes_atribuidos(no.body) | seguros
            senao = _nomes_atribuidos(no.orelse) | seguros
            usados = _lidos_depois(arvore, no)
            for nome in sorted(((corpo - senao) | (senao - corpo)) & usados):
                desequilibrados.append((no.lineno, nome))

        # DOIS, e os dois são falso positivo conhecido:
        #
        #   linha 12671 `acao`  — nasce dentro do if e morre ali; o `acao`
        #                         lido mais abaixo é outro, atribuído noutro
        #                         caminho.
        #   linha 16987 `aviso` — idem, dentro do ramo de execução incerta.
        #
        # Distinguir os dois casos exigiria seguir o fluxo de dados de
        # verdade (saber que o nome foi REATRIBUÍDO antes da leitura de
        # baixo), e isso é caro para o que se ganha. Fixar o teto em 2 e
        # nomear quais são resolve o mesmo problema: qualquer imprecisão
        # NOVA estoura o teste e vem com a linha.
        #
        # É teto, não meta — ele só pode cair.
        self.assertLessEqual(
            len(desequilibrados), 2,
            "ramos novos com variável definida em um lado só:\n" +
            "\n".join(f"  linha {l}: {n}" for l, n in desequilibrados[:40]))


if __name__ == "__main__":
    unittest.main()
