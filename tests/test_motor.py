"""O motor que disse que subiu sem ter subido.

O LOG REAL (11/08, 13:05):
    ❯ liga o motor
    ✳ "Ligando o motor agora — vou analisar a janela 'Chrome · Tradovate'."
    ✳ "Motor no ar: já estou capturando e analisando o gráfico."
    [aba Motor, no MESMO minuto]
    ⚠️ O processo do Node encerrou IMEDIATAMENTE (código 1).
    ❌ ERRO: a porta 3939 já está em uso.
    ⚠️ O processo do motor foi encerrado.
  — e isso três vezes seguidas, com o app mandando o trader abrir o Terminal
  para matar o processo órfão que o PRÓPRIO app tinha deixado.

Duas causas, dois grupos de teste aqui:
  1. `motor_rodando` era ligada assim que o `Popen` retornava, 1,5 s ANTES da
     checagem que descobria o processo morto — e era essa flag que a TIGER
     olhava para dizer "motor no ar".
  2. A porta ocupada era problema do trader resolver, no Terminal, no meio do
     pregão.
"""

import ast
import unittest

from harness import ARQUIVO, carregar, fonte_do_arquivo

FONTE = fonte_do_arquivo(ARQUIVO)


def _metodo(nome, fonte=None):
    for no in ast.walk(ast.parse(fonte or FONTE)):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    raise AssertionError(f"método {nome} não existe mais")


def _corpo(nome, fonte=None):
    no = _metodo(nome, fonte)
    linhas = (fonte or FONTE).splitlines()
    return "\n".join(linhas[no.lineno - 1:no.end_lineno])


class TestNaoDizerQueSubiuSemTerSubido(unittest.TestCase):
    def test_a_confirmacao_olha_a_porta_e_nao_a_flag_do_popen(self):
        corpo = _corpo("_confirmar_motor")
        self.assertIn("motor_confirmado", corpo,
                      "a confirmação voltou a olhar só `motor_rodando`, que é "
                      "ligada antes de o processo provar que está vivo")
        self.assertIn("motor_morreu_ao_subir", corpo,
                      "sem isto a espera fica 180 s girando sobre um processo "
                      "que já morreu, em vez de contar o que aconteceu")

    def test_motor_confirmado_so_e_ligado_quando_a_porta_responde(self):
        """Um único ponto do arquivo pode ligar essa flag: o trecho que acabou
        de receber resposta na porta 3939."""
        ligacoes = [l.strip() for l in FONTE.splitlines()
                    if "self.motor_confirmado = True" in l]
        self.assertEqual(len(ligacoes), 1,
                         "há mais de um lugar declarando o motor confirmado")
        corpo = _corpo("_poll_status_qr")
        self.assertIn("self.motor_confirmado = True", corpo)
        self.assertIn("primeira_conexao_ok", corpo)

    def test_a_flag_e_zerada_a_cada_nova_tentativa(self):
        """Sem zerar, um LIGAR MOTOR novo herdaria o veredito da tentativa
        anterior — e diria 'no ar' de novo sem nada ter subido."""
        for metodo in ("iniciar", "desligar", "_subir_processo_node"):
            self.assertIn("motor_confirmado", _corpo(metodo), metodo)

    def test_a_mensagem_de_sucesso_cita_a_prova(self):
        corpo = _corpo("_confirmar_motor")
        self.assertIn("a porta respondeu", corpo,
                      "a frase de sucesso precisa dizer O QUE foi verificado")


def _liberar(mapa_pid_nome, porta=3939):
    """Roda `plataforma.liberar_porta` com a porta e os nomes de processo que
    EU escolhi, e com o kill trocado por um registro — o teste não mata
    processo nenhum de verdade."""
    import plataforma
    originais = (plataforma._pids_na_porta, plataforma._nome_do_processo,
                 plataforma.os.kill, plataforma.time.sleep)
    mortos_de_fato = []
    try:
        plataforma._pids_na_porta = lambda p: sorted(mapa_pid_nome)
        plataforma._nome_do_processo = lambda pid: mapa_pid_nome.get(pid, "")
        plataforma.os.kill = lambda pid, sinal: mortos_de_fato.append(pid)
        plataforma.time.sleep = lambda _s: None
        resultado = plataforma.liberar_porta(porta, so_processos=("node",))
    finally:
        (plataforma._pids_na_porta, plataforma._nome_do_processo,
         plataforma.os.kill, plataforma.time.sleep) = originais
    return resultado


class TestPortaOcupada(unittest.TestCase):
    def test_o_app_libera_a_porta_antes_de_subir(self):
        corpo = _corpo("_subir_processo_node")
        self.assertIn("_liberar_porta_do_motor", corpo)
        # E a limpeza vem ANTES do Popen, senão não adianta nada.
        self.assertLess(corpo.index("_liberar_porta_do_motor"),
                        corpo.index("subprocess.Popen"))

    def test_so_mata_processo_node(self):
        """Matar às cegas quem estiver na porta 3939 é matar programa dos
        outros. A trava é o nome do processo."""
        corpo = _corpo("_liberar_porta_do_motor")
        self.assertIn('so_processos=("node",)', corpo)
        self.assertIn("NÃO é o motor", corpo,
                      "quando a porta é de outro programa, isso tem de ser DITO")

    def test_liberar_porta_recusa_o_que_nao_e_node(self):
        """A camada de plataforma devolve (mortos, recusados) e NUNCA mata o que
        não confere com a lista — nem que isso signifique não liberar a porta."""
        mortos, recusados = _liberar({4242: "Google Chrome"})
        self.assertEqual(mortos, [])
        self.assertEqual(recusados, [(4242, "Google Chrome")])

    def test_liberar_porta_mata_o_node_orfao(self):
        mortos, recusados = _liberar({4242: "node"})
        self.assertEqual(mortos, [(4242, "node")])
        self.assertEqual(recusados, [])

    def test_porta_livre_nao_faz_nada(self):
        self.assertEqual(_liberar({}), ([], []))

    def test_nunca_mata_o_proprio_app(self):
        """Se o PID na porta for o do próprio programa, ele é pulado — um
        processo que se mata ao ligar o motor é pior que a porta ocupada."""
        import os
        mortos, recusados = _liberar({os.getpid(): "node"})
        self.assertEqual((mortos, recusados), ([], []))

    def test_sem_lsof_nao_conclui_que_esta_livre(self):
        """Não conseguir olhar a porta NÃO é o mesmo que a porta estar livre."""
        import plataforma
        original = plataforma._pids_na_porta
        try:
            plataforma._pids_na_porta = lambda porta: []   # é o que ela devolve ao falhar
            self.assertEqual(plataforma.liberar_porta(3939), ([], []))
        finally:
            plataforma._pids_na_porta = original


class TestMensagensDeSistema(unittest.TestCase):
    def test_o_motor_node_nao_fala_de_windows_dentro_do_mac(self):
        """A mensagem de porta ocupada mandava 'finalize node.exe no Gerenciador
        de Tarefas' — dentro de um Mac, uma tela que não existe."""
        with open(ARQUIVO.replace("main_app.py", "motor/index.js"),
                  encoding="utf-8") as f:
            js = f.read()
        i = js.index("EADDRINUSE")
        trecho = js[i:i + 900]
        self.assertIn("process.platform === 'darwin'", trecho,
                      "a instrução precisa depender do sistema")
        self.assertIn("lsof", trecho)
        self.assertIn("Gerenciador de Tarefas", trecho)


class TestCenarioMortoNaoFicaAguardandoDecisao(unittest.TestCase):
    def test_stop_rompido_antes_da_entrada_marca_o_registro(self):
        """O motor encerrava o cenário só em memória; o registro no disco
        continuava com decisao=None, ou seja, 'aguardando sua decisão' no
        dashboard, para sempre — e o 'acatar' no chat tentava acatar um morto."""
        i = FONTE.index("SINAL CANCELADO: Stop rompido")
        trecho = FONTE[i - 1200:i + 200]
        self.assertIn('atualizar_decisao_sinal(_sid_rs, "CANCELADO_STOP")', trecho)
        self.assertIn("cancelar_pendentes_do_sinal", trecho)

    def test_expiracao_por_falta_de_mitigacao_tambem_marca(self):
        i = FONTE.index("SINAL EXPIRADO: Nenhuma mitigação")
        trecho = FONTE[i - 800:i + 200]
        self.assertIn('atualizar_decisao_sinal(_sid_mc, "EXPIRADO")', trecho)

    def test_o_novo_estado_tem_rotulo_em_todo_lugar_que_lista_decisoes(self):
        """Um estado novo sem rótulo aparece como código cru na tela do trader."""
        self.assertIn('"CANCELADO_STOP": (', FONTE)        # resposta do 'acatar'
        self.assertIn('if decisao == "CANCELADO_STOP"', FONTE)  # lista de sinais
        # e conta como cenário RESOLVIDO (apagado na lista), não como pendente
        i = FONTE.index('resolvido = s.get("decisao")')
        self.assertIn("CANCELADO_STOP", FONTE[i:i + 260])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCicloPerdidoPorErroTemporario(unittest.TestCase):
    """Log de 13/08, 10:35 e 10:40 — dois ciclos seguidos perdidos inteiros:

        ⚠️ Erro ao analisar '...': 503 UNAVAILABLE. {'message': 'This model is
           currently experiencing high demand. Spikes in demand are usually
           temporary. Please try again later.'}
        ⚠️ Erro ao analisar '...': 504 DEADLINE_EXCEEDED

    A própria mensagem do Google diz TEMPORÁRIO e "tente de novo mais tarde".
    A ferramenta respondia a isso jogando fora CINCO MINUTOS de mercado e
    esperando o ciclo seguinte. E o trader, longe da mesa, não ficava sabendo
    de nada: o fato existia só dentro do Registro.
    """

    def _ns(self):
        return carregar(["classificar_erro_modelo"])

    def test_503_e_504_sao_temporarios_e_nao_fatais(self):
        ns = self._ns()
        for erro in ("503 UNAVAILABLE. This model is currently experiencing "
                     "high demand.",
                     "504 DEADLINE_EXCEEDED. Deadline expired.",
                     "500 INTERNAL", "The read operation timed out"):
            self.assertEqual(ns["classificar_erro_modelo"](erro), "transitorio",
                             erro[:40])

    def test_cota_e_chave_NAO_sao_temporarios(self):
        """Insistir com cota estourada ou chave inválida é desperdício — o
        retry só pode valer para o que realmente passa sozinho."""
        ns = self._ns()
        self.assertEqual(ns["classificar_erro_modelo"]("429 RESOURCE_EXHAUSTED"),
                         "cota")
        self.assertEqual(
            ns["classificar_erro_modelo"]("401 UNAUTHENTICATED API_KEY_INVALID"),
            "fatal")

    def test_o_motor_tenta_uma_segunda_passada(self):
        """Vinte segundos custam quase nada; cinco minutos de mercado, não."""
        fonte = fonte_do_arquivo()
        i = fonte.index("for tentativa in (1, 2):")
        bloco = fonte[i:i + 6000]
        self.assertIn("time.sleep(20)", bloco)
        self.assertIn('classificar_erro_modelo(ultimo_erro) == "transitorio"',
                      bloco)

    def test_a_segunda_passada_e_SO_para_erro_temporario(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("for tentativa in (1, 2):")
        bloco = fonte[i:i + 6000]
        self.assertIn("if tentativa == 1", bloco)
        self.assertIn("não insiste", bloco)

    def test_resposta_boa_nao_dispara_segunda_passada(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("for tentativa in (1, 2):")
        bloco = fonte[i:i + 6000]
        self.assertIn("if resposta is not None:", bloco)

    def test_ciclo_perdido_chega_ao_trader(self):
        """Silêncio nunca explica silêncio. Quem espera sugestão no celular
        conclui que a ferramenta parou."""
        fonte = fonte_do_arquivo()
        self.assertIn("ciclos_perdidos", fonte)
        i = fonte.index('est["ciclos_perdidos"] = est.get("ciclos_perdidos", 0) + 1')
        bloco = fonte[i:i + 1800]
        self.assertIn("_chat_feed", bloco)
        self.assertIn("enviar_relatorio_whatsapp", bloco)
        self.assertIn("não estou parada", bloco)

    def test_o_aviso_nao_se_repete_a_cada_ciclo(self):
        """Aviso repetido vira ruído, e ruído é ignorado quando importa."""
        fonte = fonte_do_arquivo()
        i = fonte.index('est["ciclos_perdidos"] = est.get("ciclos_perdidos", 0) + 1')
        self.assertIn('est["ciclos_perdidos"] == 2', fonte[i:i + 500])

    def test_a_contagem_zera_quando_volta_a_funcionar(self):
        fonte = fonte_do_arquivo()
        self.assertIn('est["ciclos_perdidos"] = 0', fonte)

    def test_a_contagem_e_por_janela(self):
        """Uma janela com problema não pode disparar aviso pela outra — é a
        mesma regra de 'nunca confundir uma análise com a outra'."""
        fonte = fonte_do_arquivo()
        self.assertIn('"ciclos_perdidos": 0,', fonte)
