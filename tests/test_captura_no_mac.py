"""A CAPTURA NO MAC: TENTAR DE VERDADE, E SÓ DEPOIS DIZER POR QUE NÃO DEU.

O DIA QUE ISTO CUSTOU
---------------------
28/08. "sendo bem sincero, voce me fez eu perder o tempo o dia inteiro".

Ele estava certo. Duas vezes eu apontei a permissão de Gravação de Tela como
causa, duas vezes o conserto não resolveu, e as duas vezes o log já dizia a
verdade em TODAS as linhas — eu é que não li:

    🔗 Janela 'Profit  [outra área de trabalho]' fixada (handle 95)
    📸 Capturando 'Profit  [outra área de trabalho]'...
    ⚠️ não consegui uma imagem atual de 'Profit  [outra área de trabalho]'

"[outra área de trabalho]" é o Mission Control: uma janela em TELA CHEIA no
macOS vira um espaço só dela, e o compositor não guarda os pixels de quem não
está sendo mostrado. Permissão nenhuma muda isso.

MAS A PRIMEIRA VERSÃO DESTE CONSERTO TAMBÉM ESTAVA ERRADA
----------------------------------------------------------
Ela RECUSAVA DE SAÍDA quando a janela estava noutro espaço, sem tentar. Isso
troca um diagnóstico errado por outro: há caso em que o servidor de janelas
ainda tem o conteúdo e a imagem sai. Um programa que se recusa a tentar não
tem como afirmar que não dava.

A ordem certa é: TENTAR TUDO, e só então explicar. É o que estes testes
cravam, e é a regra que impede a próxima versão de voltar a chutar.

AS TRÊS COISAS QUE ESTÃO TRAVADAS AQUI
---------------------------------------
1. A CAMADA DO QUARTZ VEM PRIMEIRO, E DENTRO DO PROCESSO. O caminho antigo
   chamava /usr/sbin/screencapture — processo SEPARADO. No macOS a permissão
   é concedida ao processo RESPONSÁVEL, e um binário do sistema disparado por
   nós pode ser atribuído a outro responsável e recusado com a permissão do
   aplicativo intacta. Pedir a imagem pela mesma API, dentro do processo que
   TEM a permissão, tira uma peça do caminho e uma classe de recusa junto.
   De quebra tira fork+exec, codificação PNG, escrita e leitura de disco do
   caminho crítico de cada ciclo.

2. CADA MOTIVO TEM UMA SAÍDA DIFERENTE. Mandar "libere a permissão" para quem
   está com a janela em tela cheia é o que consumiu o dia dele. O texto de
   outra-área-de-trabalho é PROIBIDO de mandar mexer em permissão.

3. O RECORTE DE TELA NÃO PODE FOTOGRAFAR O ESPAÇO ERRADO. Este era o pior dos
   dois defeitos e não tinha nada a ver com o dia perdido: `screencapture -R`
   recorta um retângulo da tela QUE ESTÁ SENDO MOSTRADA AGORA. Com o Profit
   noutro espaço, o plano C devolvia — sem erro, com cara de sucesso — o
   pedaço do que estivesse na tela naquelas coordenadas, e o motor anotava
   "✅ Recuperado via recorte de tela (conteúdo atual)" e mandava aquilo para
   a IA analisar como se fosse o gráfico dele. Imagem errada analisada como
   certa é a única classe de erro aqui que vira ordem e custa dinheiro.
"""

import os
import sys
import unittest

from harness import RAIZ

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import plataforma as P          # noqa: E402


def _fonte(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


def _corpo(nome, funcao):
    """O CÓDIGO de uma função, sem docstring nem comentário.

    Existe porque a docstring desta correção EXPLICA o defeito antigo pelo
    nome — e um teste que procura o nome no texto inteiro passa a punir quem
    documenta, que é o contrário do que se quer."""
    import ast
    fonte = _fonte(nome)
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.FunctionDef) and no.name == funcao:
            corpo = list(no.body)
            if (corpo and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)):
                corpo = corpo[1:]
            return "\n".join(ast.unparse(n) for n in corpo)
    raise AssertionError(f"não achei {funcao} em {nome}")


class _ImagemFalsa:
    """Só precisa ser distinguível de None e comparável."""

    def __init__(self, marca="imagem"):
        self.marca = marca

    def __repr__(self):
        return f"<{self.marca}>"


class _Mac:
    """Põe o módulo em modo macOS com as peças trocadas por espiões.

    Restaura TUDO na saída — a suíte inteira roda no mesmo processo, e um
    atributo esquecido aqui vira falha fantasma num arquivo de teste que nem
    fala de Mac (lição de `test_fora_do_mac_as_duas_devolvem_None`, que passava
    sozinho e quebrava acompanhado)."""

    ATRIBUTOS = ("E_MACOS", "E_WINDOWS", "PIL_DISPONIVEL", "QUARTZ_DISPONIVEL",
                 "_captura_quartz", "_rodar", "_png_para_pil", "_ids_na_tela",
                 "permissao_de_tela_ok", "_janelas_macos")

    def __init__(self, quartz=None, screencapture=None, png=None,
                 na_tela=(), permissao=True, janelas=None):
        self.quartz = quartz
        self.screencapture = screencapture or (False, "", "")
        self.png = png
        self.na_tela = set(na_tela)
        self.permissao = permissao
        self.janelas = janelas or []
        self.comandos = []
        self.arquivos_pedidos = []

    def __enter__(self):
        self._antes = {n: getattr(P, n) for n in self.ATRIBUTOS}
        P.E_MACOS, P.E_WINDOWS = True, False
        P.PIL_DISPONIVEL = True
        P.QUARTZ_DISPONIVEL = True
        P._captura_quartz = lambda h: self.quartz
        P._png_para_pil = self._ler_png
        P._ids_na_tela = lambda: set(self.na_tela)
        P.permissao_de_tela_ok = lambda: self.permissao
        P._janelas_macos = lambda *a, **k: list(self.janelas)
        P._rodar = self._executar
        return self

    def __exit__(self, *_):
        for nome, valor in self._antes.items():
            setattr(P, nome, valor)
        return False

    # -- peças espiãs -------------------------------------------------
    def _executar(self, args, timeout=10, entrada=None, com_erro=False):
        self.comandos.append(list(args))
        ok, saida, erro = self.screencapture
        if ok and args and args[0] == "screencapture":
            # O binário de verdade ESCREVE o arquivo. Sem isso o código sob
            # teste cai no ramo "não existe" e o teste mediria outra coisa.
            with open(args[-1], "wb") as f:
                f.write(b"png de mentira")
        return (ok, saida, erro) if com_erro else (ok, saida)

    def _ler_png(self, caminho):
        self.arquivos_pedidos.append(caminho)
        return self.png


class CamadaDoQuartzVemPrimeiro(unittest.TestCase):

    def test_quando_o_quartz_resolve_o_screencapture_nem_e_chamado(self):
        """Menos um processo por captura, e uma classe de recusa a menos."""
        img = _ImagemFalsa("pelo quartz")
        with _Mac(quartz=img, na_tela={95}) as mac:
            saida, motivo = P.capturar_janela_macos(95)
        self.assertIs(saida, img)
        self.assertEqual(motivo, "")
        self.assertEqual(mac.comandos, [],
                         "chamou screencapture mesmo com o Quartz tendo dado "
                         "a imagem — é um fork+exec e um PNG em disco por "
                         "ciclo, jogados fora")

    def test_sem_quartz_cai_no_screencapture_e_ainda_assim_entrega(self):
        img = _ImagemFalsa("pelo screencapture")
        with _Mac(quartz=None, screencapture=(True, "", ""), png=img,
                  na_tela={95}) as mac:
            saida, motivo = P.capturar_janela_macos(95)
        self.assertIs(saida, img)
        self.assertEqual(motivo, "")
        self.assertTrue(any(c[0] == "screencapture" for c in mac.comandos))

    def test_o_arquivo_temporario_some_mesmo_quando_da_certo(self):
        with _Mac(quartz=None, screencapture=(True, "", ""),
                  png=_ImagemFalsa(), na_tela={95}) as mac:
            P.capturar_janela_macos(95)
        for caminho in mac.arquivos_pedidos:
            self.assertFalse(os.path.exists(caminho),
                             "deixou PNG na pasta temporária — um por ciclo, "
                             "o dia inteiro")


class TentarAntesDeCulpar(unittest.TestCase):

    def test_janela_em_outro_espaco_AINDA_ASSIM_e_tentada(self):
        """A correção da minha própria correção.

        Recusar sem tentar é chutar com sinal trocado. Se o servidor de
        janelas ainda tem o conteúdo, a imagem sai — e ela é o que ele quer."""
        img = _ImagemFalsa("saiu mesmo estando noutro espaço")
        with _Mac(quartz=img, na_tela={1, 2, 3}) as mac:   # 95 fora da lista
            saida, motivo = P.capturar_janela_macos(95)
        self.assertIs(saida, img)
        self.assertEqual(motivo, "",
                         "acusou outra área de trabalho para uma captura que "
                         "DEU CERTO")

    def test_so_depois_de_tudo_falhar_e_que_sai_o_motivo_do_espaco(self):
        with _Mac(quartz=None, screencapture=(False, "", ""),
                  na_tela={1, 2, 3}) as mac:
            saida, motivo = P.capturar_janela_macos(95)
        self.assertIsNone(saida)
        self.assertEqual(motivo, P.FALHA_OUTRA_AREA)
        self.assertTrue(any(c[0] == "screencapture" for c in mac.comandos),
                        "desistiu sem sequer tentar o screencapture")


class CadaMotivoTemONomeCerto(unittest.TestCase):

    def test_sem_permissao_nao_executa_nada(self):
        with _Mac(permissao=False) as mac:
            saida, motivo = P.capturar_janela_macos(95)
        self.assertIsNone(saida)
        self.assertEqual(motivo, P.FALHA_PERMISSAO)
        self.assertEqual(mac.comandos, [])

    def test_o_stderr_do_macos_e_lido_e_vira_permissao(self):
        """O stderr do screencapture ia inteiro para o lixo — era ali que o
        sistema dizia o motivo, o tempo todo."""
        with _Mac(quartz=None,
                  screencapture=(False, "", "screencapture: not authorized"),
                  na_tela={1}) as mac:
            saida, motivo = P.capturar_janela_macos(95)
        self.assertEqual(motivo, P.FALHA_PERMISSAO,
                         "o macOS disse 'not authorized' e o programa chamou "
                         "de outra coisa")

    def test_png_escrito_mas_ilegivel_tem_nome_proprio(self):
        """Não é espaço de trabalho nem permissão: é disco ou PIL."""
        with _Mac(quartz=None, screencapture=(True, "", ""), png=None,
                  na_tela={95}) as mac:
            saida, motivo = P.capturar_janela_macos(95)
        self.assertIsNone(saida)
        self.assertEqual(motivo, P.FALHA_IMAGEM_VAZIA)

    def test_quando_o_macos_explica_a_explicacao_dele_e_que_vale(self):
        with _Mac(quartz=None, screencapture=(False, "", "disk full"),
                  na_tela={95}) as mac:
            saida, motivo = P.capturar_janela_macos(95)
        self.assertIn("disk full", motivo)

    def test_fora_do_mac_devolve_par_vazio_sem_tentar(self):
        antes = (P.E_MACOS, P.E_WINDOWS)
        P.E_MACOS, P.E_WINDOWS = False, True
        try:
            self.assertEqual(P.capturar_janela_macos(95), (None, ""))
        finally:
            P.E_MACOS, P.E_WINDOWS = antes


class OTextoQueEleVaiLer(unittest.TestCase):

    def test_outra_area_NAO_manda_mexer_em_permissao(self):
        """A regra que custou o dia dele. Nunca mais."""
        with _Mac(quartz=None, screencapture=(False, "", ""), na_tela={1}):
            texto = P.porque_a_captura_falhou(95, "Profit")
        baixo = texto.lower()
        self.assertIn("outra área de trabalho", baixo)
        self.assertIn("tela cheia", baixo)
        self.assertNotIn("gravação de tela", baixo,
                         "voltou a mandar ele mexer na permissão para um "
                         "problema que não é de permissão")
        self.assertNotIn("ajustes do sistema", baixo)

    def test_outra_area_diz_O_QUE_FAZER_e_que_atras_de_outra_janela_pode(self):
        with _Mac(quartz=None, screencapture=(False, "", ""), na_tela={1}):
            texto = P.porque_a_captura_falhou(95, "Profit")
        self.assertIn("COMO RESOLVER", texto)
        self.assertIn("Ctrl+Cmd+F", texto)
        self.assertIn("ATRÁS", texto,
                      "não disse que janela coberta ele LÊ sem problema — sem "
                      "isso o trader esconde a corretora atrás de nada")

    def test_permissao_de_verdade_ai_sim_manda_liberar(self):
        with _Mac(permissao=False):
            texto = P.porque_a_captura_falhou(95, "Profit")
        self.assertIn("GRAVAÇÃO DE TELA", texto)

    def test_quando_deu_certo_o_texto_e_vazio(self):
        with _Mac(quartz=_ImagemFalsa(), na_tela={95}):
            self.assertEqual(P.porque_a_captura_falhou(95, "Profit"), "")

    def test_o_nome_da_janela_aparece_no_texto(self):
        with _Mac(quartz=None, screencapture=(False, "", ""), na_tela={1}):
            texto = P.porque_a_captura_falhou(95, "Profit MGC")
        self.assertIn("Profit MGC", texto)


class ORecorteNaoFotografaOEspacoErrado(unittest.TestCase):
    """O defeito que virava ordem."""

    JANELA = {"id": 95, "titulo": "Profit", "app": "Profit", "pid": 3957,
              "x": 0, "y": 34, "largura": 1710, "altura": 1073, "na_tela": False}

    def test_janela_em_outro_espaco_e_RECUSADA_nao_recortada(self):
        with _Mac(na_tela={1, 2}, janelas=[self.JANELA]) as mac:
            imagem, sobreposto = P.capturar_regiao_da_tela(95)
        self.assertIsNone(imagem,
                          "devolveu um recorte da tela ATUAL como se fosse a "
                          "janela que está noutro espaço")
        self.assertTrue(sobreposto,
                        "sem o sinal de sobreposição os chamadores ACEITAM a "
                        "imagem — é assim que a foto errada vira análise")
        self.assertEqual(mac.comandos, [],
                         "chegou a rodar o screencapture para uma região que "
                         "sabidamente mostra outra coisa")

    def test_janela_no_espaco_atual_continua_sendo_recortada(self):
        """A trava não pode virar uma recusa geral: o plano C existe e serve."""
        img = _ImagemFalsa("recorte legítimo")
        with _Mac(na_tela={95}, janelas=[self.JANELA],
                  screencapture=(True, "", ""), png=img) as mac:
            imagem, sobreposto = P.capturar_regiao_da_tela(95)
        self.assertIs(imagem, img)
        self.assertFalse(sobreposto)

    def test_sem_saber_quem_esta_na_tela_nao_acusa_ninguem(self):
        """Conjunto vazio quer dizer 'não consegui perguntar' — e nesse caso
        recusar tudo seria trocar um defeito por uma paralisia."""
        img = _ImagemFalsa()
        with _Mac(na_tela=set(), janelas=[self.JANELA],
                  screencapture=(True, "", ""), png=img):
            imagem, sobreposto = P.capturar_regiao_da_tela(95)
        self.assertIs(imagem, img)


class RegrasDoFonte(unittest.TestCase):

    def test_o_rodar_sabe_devolver_o_stderr(self):
        self.assertIn("com_erro", P._rodar.__code__.co_varnames)

    def test_a_aba_do_chrome_e_capturada_em_JPEG_nao_em_PNG(self):
        """PNG obriga o Chrome a comprimir sem perda a página inteira DENTRO
        do processo que está desenhando o gráfico ao vivo, e ainda manda o
        resultado em base64. A imagem é reduzida antes de subir ao modelo de
        qualquer jeito — o lossless aqui é trabalho jogado fora."""
        fonte = _fonte("plataforma.py")
        trecho = fonte.split("def capturar_aba_cdp")[1].split("\ndef ")[0]
        self.assertIn('"format": "jpeg"', trecho)
        self.assertNotIn('"format": "png"', trecho)

    def test_a_camada_do_quartz_nao_usa_subprocesso(self):
        # Sem a docstring: ela EXPLICA o screencapture, e punir a explicação
        # é ensinar a apagar comentário (lição da casa).
        trecho = _corpo("plataforma.py", "_captura_quartz")
        self.assertNotIn("_rodar(", trecho)
        self.assertNotIn("screencapture", trecho)
        self.assertIn("CGWindowListCreateImage", trecho)

    def test_o_quartz_respeita_o_passo_de_linha(self):
        """Sem passar o bytes-per-row do Quartz ao PIL, a imagem sai enviesada
        em diagonal — e uma IA olhando um gráfico torto responde qualquer
        coisa com confiança total."""
        fonte = _fonte("plataforma.py")
        trecho = fonte.split("def _captura_quartz")[1].split("\ndef ")[0]
        self.assertIn("CGImageGetBytesPerRow", trecho)
        self.assertIn("BGRA", trecho)


if __name__ == "__main__":
    unittest.main(verbosity=2)
