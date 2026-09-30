"""O EXTRATO DE ORDENS DA CORRETORA VIRA DIÁRIO — SEM ADIVINHAR NADA.

O PEDIDO
--------
"Inclua uma opção de enviar o PDF do extrato de ordens gerado pela Tradovate
ou qualquer outra corretora para preenchimento dos envios de ordens manuais, e
o motor preencher automaticamente com base no relatório."

POR QUE ISTO É PERIGOSO, E O QUE SEGURA O PERIGO
-------------------------------------------------
Extrair texto de PDF é frágil por natureza. A tabela vira uma fita de
palavras, as colunas vazias somem, o cabeçalho se repete no meio dos dados e
um carimbo de hora se parte em duas na quebra de página. Um leitor descuidado
troca de coluna em silêncio, e nesse ponto o DIÁRIO fica errado — o mesmo
diário de onde sai a taxa de acerto que ele usa para decidir dinheiro.

O que segura é a coluna "Notional Value", que o próprio relatório traz:

    nocional = quantidade x preço x multiplicador

Conferindo linha a linha contra ela, um deslocamento de coluna deixa de ser
silencioso: a conta não fecha e a linha é recusada em vez de importada errada.
E o multiplicador sai do PRÓPRIO documento — o leitor não precisa de tabela de
contratos cadastrada para funcionar com o que ele operar amanhã.

O QUE ESTES TESTES CRAVAM, E POR QUÊ
-------------------------------------
Três recusas, cada uma protegendo um número que ele usa:

  · Canceled/Rejected/Working NÃO viram operação. No extrato real que serviu
    de base, 111 ordens continham 48 canceladas — quase todas brackets de
    proteção que morreram junto com a saída. Contá-las triplicaria a contagem
    do dia.
  · Posição que ficou aberta NÃO vira resultado, porque não existe preço de
    saída. Inventar um para "fechar o número" seria a mentira que o resto
    deste projeto passa o dia caçando.
  · Linha que não confere não entra.

DOIS DEFEITOS QUE ESTES TESTES EXISTEM PARA NÃO DEIXAR VOLTAR
--------------------------------------------------------------
Ambos apareceram rodando contra o extrato real dele, e ambos são do tipo que
passa despercebido:

  1. O título de seção ('8/24/26: 108 order(s)') grudava no fim da última
     ordem do dia anterior, e o '108' virava o VALOR NOCIONAL daquela linha —
     ou seja, o defeito corrompia justamente a coluna que serve de conferência.
     Pior: 108 / (8 x 7691,50) = 0,00175, que arredonda para ZERO, e zero
     passava no teste de "o multiplicador é redondo". O detector aprovava o
     absurdo por arredondamento.

  2. Uma execução real de US$ 38 mil era descartada porque a quebra de página
     tinha separado a hora da data, e o leitor exigia as duas coladas.
"""

import os
import sys
import unittest

from harness import RAIZ

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import extrato_pdf as E          # noqa: E402


def _so_codigo(texto):
    """Tira comentário e docstring: o teste mede o CÓDIGO, não a prosa que o
    explica (lição da casa — ver test_conta_orfa.py)."""
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


# O CABEÇALHO É COPIADO DO RELATÓRIO REAL, com as quebras onde elas caem de
# verdade. Um cabeçalho "limpo" aqui testaria um documento que não existe.
CAB = ("Order ID B/S Quantity Contract Type Limit \nPrice\nStop \nPrice\n"
       "Status Text Filled \nQty\nFill Time Avg Fill \nPrice\n"
       "Timestamp Account Venue Notional \nValue")

# Extrato sintético com OS MESMOS defeitos do arquivo real: título de seção
# entre os dias, conta partida ao meio, hora separada da data, e o cabeçalho
# repetido no meio dos dados. Números inventados; formato idêntico.
EXTRATO = f"""MESU6
Micro E-mini S&P 500
8/23/26: 3 order(s)
{CAB}
900000000001 Buy 2 MESU6 Limit 7000.00 Filled Chart 2 08/23/2026 10:
00:00
7000.00 08/23/2026 09:
59:00
APEX111111111
11111
USD
70,000.00
900000000002 Sell 2 MESU6 Limit 7020.00 Canceled multibracket 08/23/2026 10:
00:00
APEX111111111
11111
USD
900000000003 Sell 2 MESU6 Stop 6990.00 Filled multibracket 2 08/23/2026 11:
00:00
7010.00 08/23/2026 10:
30:00
APEX111111111
11111
USD
70,100.00
8/24/26: 2 order(s)
{CAB}
900000000004 Sell 1 MESU6 Market Rejected DOM 08/24/2026 09:
00:00
APEX111111111
11111
USD
900000000005 Buy 1 MESU6 Limit 6900.00 Working Chart 08/24/2026 09:
30:00
APEX111111111
11111
USD
TOTAL:  order(s)5
"""


class TestOTextoViraOrdens(unittest.TestCase):

    def setUp(self):
        self.ordens = E.ler_ordens(EXTRATO)

    def test_le_todas_as_ordens_do_arquivo(self):
        self.assertEqual(len(self.ordens), 5)

    def test_o_total_declarado_pelo_relatorio_e_lido(self):
        """Serve para o programa comparar o que LEU com o que o documento DIZ
        ter. Sem isso, um leitor que perdesse metade das linhas numa quebra de
        página entregaria meio diário com cara de diário inteiro."""
        self.assertEqual(E.total_declarado(EXTRATO), 5)

    def test_os_campos_essenciais_saem_certos(self):
        o = self.ordens[0]
        self.assertEqual(o["id"], "900000000001")
        self.assertEqual(o["lado"], "BUY")
        self.assertEqual(o["qtd"], 2)
        self.assertEqual(o["ativo"], "MESU6")
        self.assertEqual(o["tipo"], "LIMITE")
        self.assertEqual(o["preco_limite"], 7000.00)
        self.assertEqual(o["estado"], "EXECUTADA")
        self.assertEqual(o["executados"], 2)
        self.assertEqual(o["preco_medio"], 7000.00)
        self.assertEqual(o["nocional"], 70000.00)

    def test_o_PRECO_vai_para_a_coluna_QUE_O_TIPO_MANDA(self):
        """As colunas 'Limit Price' e 'Stop Price' são duas, mas só uma vem
        preenchida, e a vazia SOME do texto extraído. Contar posições daria o
        stop como se fosse limite em metade das linhas."""
        stop = [o for o in self.ordens if o["id"] == "900000000003"][0]
        self.assertEqual(stop["tipo"], "STOP")
        self.assertEqual(stop["preco_stop"], 6990.00)
        self.assertIsNone(stop["preco_limite"])

    def test_ordem_a_MERCADO_nao_inventa_preco_de_entrada(self):
        m = [o for o in self.ordens if o["id"] == "900000000004"][0]
        self.assertEqual(m["tipo"], "MERCADO")
        self.assertIsNone(m["preco_limite"])
        self.assertIsNone(m["preco_stop"])

    def test_os_quatro_estados_sao_distinguidos(self):
        estados = {o["id"]: o["estado"] for o in self.ordens}
        self.assertEqual(estados["900000000001"], "EXECUTADA")
        self.assertEqual(estados["900000000002"], "CANCELADA")
        self.assertEqual(estados["900000000004"], "REJEITADA")
        self.assertEqual(estados["900000000005"], "ABERTA")

    def test_o_rotulo_da_origem_e_preservado(self):
        """'Chart', 'DOM', 'multibracket' dizem por onde a ordem saiu — é o
        que permite a ele separar o que foi dele do que foi do robô."""
        rotulos = {o["id"]: o["rotulo"] for o in self.ordens}
        self.assertEqual(rotulos["900000000001"], "Chart")
        self.assertEqual(rotulos["900000000002"], "multibracket")
        self.assertEqual(rotulos["900000000004"], "DOM")


class TestOTituloDeSecaoNaoVIRANUMERO(unittest.TestCase):
    """DEFEITO REAL, e o pior tipo: corrompia o próprio detector de defeito."""

    def test_o_titulo_do_dia_seguinte_nao_vira_valor_nocional(self):
        """'8/24/26: 2 order(s)' vem logo depois da última ordem do dia 23.
        Achatado, grudava nela, e o '2' virava o nocional."""
        o = [x for x in E.ler_ordens(EXTRATO) if x["id"] == "900000000003"][0]
        self.assertEqual(o["nocional"], 70100.00)

    def test_multiplicador_que_arredonda_para_ZERO_e_recusado(self):
        """108 / (8 x 7691,50) = 0,00175, que arredonda para 0 — e zero
        passava no teste de 'é número redondo'. Detector que aprova o absurdo
        por arredondamento é pior que detector nenhum: dá confiança falsa."""
        ruim = {"estado": "EXECUTADA", "executados": 8, "preco_medio": 7691.50,
                "nocional": 108.0, "qtd": 8}
        ok, motivo = E.conferir_pela_nocional(ruim)
        self.assertFalse(ok)
        self.assertIn("nocional", motivo)


class TestAQuebraDePaginaNaoPodeSUMIRCOMExecucao(unittest.TestCase):
    """DEFEITO REAL: uma execução de US$ 38 mil ia para o lixo porque a hora
    tinha ficado separada da data."""

    LINHA = ("900000000009 Buy 1 MESU6 Limit 7676.25 Filled DOM 1 08/24/2026 "
             "7676.25 08/24/2026 14: APEX22174900 USD 14:16:12 11:29 000137 "
             "38,381.25")

    def test_a_execucao_e_lida_mesmo_com_a_hora_partida(self):
        o = E.ler_ordens(self.LINHA)[0]
        self.assertEqual(o["estado"], "EXECUTADA")
        self.assertEqual(o["executados"], 1)
        self.assertEqual(o["preco_medio"], 7676.25)

    def test_e_o_nocional_certo_e_encontrado_no_meio_da_bagunca(self):
        """Depois da praça vêm fragmentos que a quebra empurrou para o fim:
        '14:16:12', '11:29', '000137'. O último é metade de um número de
        conta, e `float()` o aceita como 137."""
        o = E.ler_ordens(self.LINHA)[0]
        self.assertEqual(o["nocional"], 38381.25)

    def test_e_a_linha_remontada_PASSA_na_conferencia(self):
        """38.381,25 / (1 x 7676,25) = 5,0 exato. É a prova de que remontar a
        linha não afrouxou nada: quem valida é a conta, não o carimbo."""
        o = E.ler_ordens(self.LINHA)[0]
        self.assertEqual(E.multiplicador_implicito(o), 5.0)
        self.assertTrue(E.conferir_pela_nocional(o)[0])

    def test_pedaco_de_identificador_nao_e_lido_como_dinheiro(self):
        """Chutar por magnitude ('o número grande deve ser o nocional')
        acertaria neste extrato e erraria no primeiro contrato barato. A regra
        é do formato: valor não começa com zero à esquerda."""
        self.assertIsNone(E._numero_de_dinheiro("000137"))
        self.assertEqual(E._numero_de_dinheiro("38,381.25"), 38381.25)


class TestOMultiplicadorSaiDoDOCUMENTO(unittest.TestCase):

    def test_o_multiplicador_e_deduzido_da_coluna_nocional(self):
        """Assim o leitor funciona para o contrato que ele operar amanhã sem
        ninguém vir aqui cadastrar tabela de contratos."""
        o = {"estado": "EXECUTADA", "executados": 8, "preco_medio": 7691.50,
             "nocional": 307660.00, "qtd": 8}
        self.assertEqual(E.multiplicador_implicito(o), 5.0)

    def test_sem_numeros_suficientes_ele_diz_que_NAO_DEU_para_conferir(self):
        """None aqui quer dizer 'não deu para conferir', que é diferente de
        'confere'. Tratar os dois como a mesma coisa é como um painel dizer
        zero quando não mediu."""
        self.assertIsNone(E.multiplicador_implicito(
            {"estado": "EXECUTADA", "executados": 8, "preco_medio": 7691.50}))

    def test_linha_sem_nocional_passa_MAS_PASSA_AVISADA(self):
        ok, motivo = E.conferir_pela_nocional(
            {"estado": "EXECUTADA", "executados": 1, "preco_medio": 100.0})
        self.assertTrue(ok)
        self.assertTrue(motivo)


class TestSoExecucaoViraOperacao(unittest.TestCase):

    def setUp(self):
        self.ordens = E.ler_ordens(EXTRATO)
        self.fech, self.sobras, self.rec = E.operacoes_fechadas(self.ordens)

    def test_o_bracket_cancelado_NAO_vira_trade(self):
        """No extrato real, 48 das 111 ordens eram canceladas — quase todas
        brackets de proteção que morreram junto com a saída. Contá-las
        triplicaria a contagem do dia."""
        ids = {f["id_entrada"] for f in self.fech} | {f["id_saida"] for f in self.fech}
        self.assertNotIn("900000000002", ids)

    def test_ordem_rejeitada_e_ordem_ainda_aberta_tambem_nao(self):
        ids = {f["id_entrada"] for f in self.fech} | {f["id_saida"] for f in self.fech}
        self.assertNotIn("900000000004", ids)
        self.assertNotIn("900000000005", ids)

    def test_a_operacao_fechada_traz_entrada_saida_e_quantidade(self):
        self.assertEqual(len(self.fech), 1)
        f = self.fech[0]
        self.assertEqual(f["direcao"], "BUY")
        self.assertEqual(f["contratos"], 2)
        self.assertEqual(f["entrada"], 7000.00)
        self.assertEqual(f["saida"], 7010.00)
        self.assertEqual(f["pontos"], 10.0)
        self.assertEqual(f["multiplicador"], 5.0)


class TestOFIFOEAsSobras(unittest.TestCase):

    def _ordem(self, id_, lado, qtd, preco, hora):
        return {"id": id_, "lado": lado, "qtd": qtd, "ativo": "MESU6",
                "estado": "EXECUTADA", "executados": qtd, "preco_medio": preco,
                "nocional": qtd * preco * 5, "hora_execucao": hora,
                "carimbo": hora, "rotulo": "Chart"}

    def test_primeiro_a_entrar_e_o_primeiro_a_sair(self):
        """FIFO porque é a regra que a própria corretora usa para apurar
        resultado. Qualquer outra escolha aqui seria minha, não dele."""
        fech, sobras, _ = E.operacoes_fechadas([
            self._ordem("1", "BUY", 1, 100.0, "08/24/2026 10:00:00"),
            self._ordem("2", "BUY", 1, 110.0, "08/24/2026 10:01:00"),
            self._ordem("3", "SELL", 1, 120.0, "08/24/2026 10:02:00"),
        ])
        self.assertEqual(len(fech), 1)
        self.assertEqual(fech[0]["entrada"], 100.0)      # o de 100, não o de 110
        self.assertEqual(sobras[0]["entrada"], 110.0)

    def test_uma_saida_grande_fecha_VARIAS_entradas(self):
        fech, sobras, _ = E.operacoes_fechadas([
            self._ordem("1", "BUY", 2, 100.0, "08/24/2026 10:00:00"),
            self._ordem("2", "BUY", 3, 110.0, "08/24/2026 10:01:00"),
            self._ordem("3", "SELL", 5, 120.0, "08/24/2026 10:02:00"),
        ])
        self.assertEqual(sorted(f["contratos"] for f in fech), [2, 3])
        self.assertEqual(sobras, [])

    def test_reversao_direta_fecha_e_abre_do_outro_lado(self):
        """Vendido 5 e compra 12: fecha os 5 e abre 7 comprado. Sai do laço
        naturalmente, sem caso especial."""
        fech, sobras, _ = E.operacoes_fechadas([
            self._ordem("1", "SELL", 5, 100.0, "08/24/2026 10:00:00"),
            self._ordem("2", "BUY", 12, 90.0, "08/24/2026 10:01:00"),
        ])
        self.assertEqual(sum(f["contratos"] for f in fech), 5)
        self.assertEqual(fech[0]["direcao"], "SELL")
        self.assertEqual(sobras[0]["direcao"], "BUY")
        self.assertEqual(sobras[0]["contratos"], 7)

    def test_posicao_que_ficou_ABERTA_nao_vira_resultado(self):
        """Não existe preço de saída. Inventar um para 'fechar o número' seria
        a mentira que o resto deste projeto passa o dia caçando."""
        fech, sobras, _ = E.operacoes_fechadas([
            self._ordem("1", "BUY", 3, 100.0, "08/24/2026 10:00:00"),
        ])
        self.assertEqual(fech, [])
        self.assertEqual(sobras[0]["contratos"], 3)
        self.assertNotIn("saida", sobras[0])

    def test_ativos_diferentes_nao_se_casam(self):
        a = self._ordem("1", "BUY", 1, 100.0, "08/24/2026 10:00:00")
        b = self._ordem("2", "SELL", 1, 120.0, "08/24/2026 10:01:00")
        b["ativo"] = "MNQU6"
        fech, sobras, _ = E.operacoes_fechadas([a, b])
        self.assertEqual(fech, [])
        self.assertEqual(len(sobras), 2)

    def test_o_resultado_do_FIFO_bate_com_o_fluxo_de_CAIXA(self):
        """CONFERÊNCIA POR OUTRO CAMINHO. O FIFO casa entrada com saída; o
        caixa só soma dinheiro que entrou e saiu, sem casar nada. Dois métodos
        independentes com o mesmo número é o que dá para chamar de conferido.

        No extrato real dele: 55 operações, 209 contratos, US$ +2.303,75 pelos
        dois caminhos, diferença zero."""
        ordens = [
            self._ordem("1", "BUY", 2, 100.0, "08/24/2026 10:00:00"),
            self._ordem("2", "BUY", 3, 110.0, "08/24/2026 10:01:00"),
            self._ordem("3", "SELL", 4, 120.0, "08/24/2026 10:02:00"),
            self._ordem("4", "SELL", 6, 130.0, "08/24/2026 10:03:00"),
            self._ordem("5", "BUY", 5, 125.0, "08/24/2026 10:04:00"),
        ]
        fech, sobras, _ = E.operacoes_fechadas(ordens)
        pelo_fifo = sum(f["pontos"] * f["contratos"] * f["multiplicador"] for f in fech)
        caixa = sum((-1 if o["lado"] == "BUY" else 1) * o["executados"]
                    * o["preco_medio"] * 5 for o in ordens)
        aberto = sum((-1 if s["direcao"] == "BUY" else 1) * s["contratos"]
                     * s["entrada"] * 5 for s in sobras)
        self.assertAlmostEqual(pelo_fifo, caixa - aberto, places=6)


class TestOResumoDIZOQueVaiEntrarEOQueNAO(unittest.TestCase):

    def test_o_resumo_conta_o_que_entra_e_o_que_fica_de_fora(self):
        ordens = E.ler_ordens(EXTRATO)
        fech, sobras, rec = E.operacoes_fechadas(ordens)
        txt = E.resumo_da_leitura(ordens, fech, sobras, rec, E.total_declarado(EXTRATO))
        self.assertIn("5 ordem(ns)", txt)
        self.assertIn("cancelada", txt)
        self.assertIn("rejeitada", txt)
        self.assertIn("Viram operação fechada: 1", txt)

    def test_o_resumo_AVISA_quando_leu_menos_do_que_o_relatorio_diz_ter(self):
        """Sem isso, um leitor que perdesse linha numa quebra de página
        entregaria meio diário com cara de diário inteiro."""
        txt = E.resumo_da_leitura([{"estado": "EXECUTADA"}], [], [], [], total=9)
        self.assertIn("⚠️", txt)
        self.assertIn("9", txt)

    def test_o_resumo_DIZ_a_posicao_que_ficou_aberta(self):
        txt = E.resumo_da_leitura(
            [], [], [{"direcao": "SELL", "contratos": 8, "ativo": "MESU6",
                      "entrada": 7678.5}], [])
        self.assertIn("ABERTA", txt)
        self.assertIn("SELL 8 MESU6", txt)


class TestSemLeitorDePdfELEDIZOQueInstalar(unittest.TestCase):

    def test_a_excecao_e_PROPRIA_e_nao_generica(self):
        """A interface precisa distinguir 'não abro PDF nenhum nesta máquina'
        (resolve-se instalando) de 'este PDF não é um extrato' (resolve-se
        escolhendo outro arquivo). Mensagem única faria ele tentar a correção
        errada."""
        self.assertTrue(issubclass(E.SemLeitorDePdf, Exception))

    def test_arquivo_inexistente_levanta_com_mensagem_util(self):
        with self.assertRaises(Exception) as ctx:
            E.texto_do_pdf(os.path.join(RAIZ, "nao_existe_isto.pdf"))
        self.assertTrue(str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOLeitorQueVIAJAJUNTO(unittest.TestCase):
    """NA MÁQUINA DELE NÃO HAVIA LEITOR NENHUM, e o recurso nasceu morto.

    Log de 24/08:
        📄 Não consegui abrir o PDF: achei um leitor de PDF mas ele não
           conseguiu abrir este arquivo (_texto_pdftotext: [Errno 2] No such
           file or directory: 'pdftotext')

    Duas coisas erradas numa linha só:

      1. A MENSAGEM MENTIA O DIAGNÓSTICO. `pdftotext` ausente levanta
         FileNotFoundError, e só o ImportError era tratado como "não existe".
         Então "o programa não está instalado" foi classificado como "o
         programa tentou e não conseguiu abrir este arquivo" — e a frase
         mandava ele conferir o PDF quando o problema era a instalação. Era
         exatamente a distinção que a classe `SemLeitorDePdf` existe para
         preservar, e que eu perdi na implementação.

      2. NENHUM dos quatro leitores existia ali: nem pypdf, nem pdfplumber,
         nem pymupdf, nem o binário do poppler. Um recurso que só funciona em
         metade das instalações é um recurso que ele não pode usar no dia que
         precisa, e "roda pip install" não é resposta para quem abre o
         programa pelo ícone.

    Agora existe um leitor embutido que usa só a biblioteca padrão (zlib), e
    ele lê o extrato real de ponta a ponta.
    """

    PDF_REAL = None          # preenchido no setUpClass quando houver um

    def test_o_binario_ausente_e_tratado_como_leitor_INEXISTENTE(self):
        """FileNotFoundError tem de cair no mesmo caminho do ImportError."""
        fonte = open(os.path.join(RAIZ, "extrato_pdf.py"), encoding="utf-8").read()
        i = fonte.index("def texto_do_pdf")
        corpo = fonte[i:i + 2000]
        self.assertIn("except (ImportError, FileNotFoundError)", corpo)

    def test_o_leitor_embutido_e_a_ULTIMA_tentativa(self):
        """As bibliotecas de verdade vêm antes: elas lidam com PDFs que o
        leitor simples não alcança (fonte com CMap próprio, por exemplo)."""
        fonte = open(os.path.join(RAIZ, "extrato_pdf.py"), encoding="utf-8").read()
        i = fonte.index("for tentativa in (")
        ordem = fonte[i:i + 200]
        self.assertLess(ordem.index("_texto_pypdf"), ordem.index("_texto_embutido"))

    def test_o_leitor_embutido_usa_SO_biblioteca_padrao(self):
        """Se ele passar a depender de pacote, deixa de ser a rede de
        segurança e vira mais um leitor que pode faltar."""
        fonte = open(os.path.join(RAIZ, "extrato_pdf.py"), encoding="utf-8").read()
        i = fonte.index("def _texto_embutido")
        j = fonte.index("def _texto_do_fluxo")
        # SEM A DOCSTRING: ela CITA os outros leitores para explicar por que
        # este existe, e um teste que procura texto no fonte casaria com a
        # explicação e puniria a documentação. Lição já paga neste projeto.
        corpo = _so_codigo(fonte[i:j])
        self.assertIn("import zlib", corpo)
        for pacote in ("pypdf", "PyPDF2", "pdfplumber", "fitz", "subprocess"):
            self.assertNotIn(pacote, corpo, f"o leitor embutido não pode usar {pacote}")

    def test_arquivo_que_nao_e_PDF_e_recusado_de_cara(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
            fh.write(b"isto nao e um PDF de jeito nenhum")
            caminho = fh.name
        try:
            with self.assertRaises(Exception):
                E._texto_embutido(caminho)
        finally:
            os.unlink(caminho)

    def test_os_escapes_de_string_do_PDF_sao_desfeitos(self):
        self.assertEqual(E._texto_de_literal(rb"MES\(U6\)"), "MES(U6)")
        self.assertEqual(E._texto_de_literal(rb"a\\b"), "a\\b")
        self.assertEqual(E._texto_de_literal(rb"\101\102"), "AB")

    def test_os_operadores_de_linha_viram_QUEBRA_DE_LINHA(self):
        """Sem isso a tabela inteira sairia numa linha só e as colunas de uma
        ordem grudariam na seguinte — que é o defeito que fez o título de
        seção virar valor nocional na primeira versão do leitor."""
        fluxo = b"BT (7000.00) Tj 0 -12 Td (Filled) Tj ET"
        saida = E._texto_do_fluxo(fluxo)
        self.assertIn("7000.00", saida)
        self.assertIn("Filled", saida)
        self.assertIn("\n", saida)

    def test_pedacos_de_texto_saem_SEPARADOS_e_nao_colados(self):
        """Separar de menos colaria dois números em um só, e aí a leitura
        vira ficção."""
        saida = E._texto_do_fluxo(b"BT [(7000) -300 (8000)] TJ ET")
        self.assertIn("7000", saida)
        self.assertIn("8000", saida)
        self.assertNotIn("70008000", saida,
                         "os dois números grudaram e viraram um só")
