""""MAS ESTÁ CAPTURANDO. ESTÁ TUDO AUTORIZADO NO MAC."

A RECLAMAÇÃO, E POR QUE ELE ESTAVA CERTO
-----------------------------------------
O programa gritava, a cada arranque, no log, no chat E no WhatsApp:

    ⚠️ ATENÇÃO — VOU OPERAR SOZINHA COM A VISÃO EM RISCO: a permissão de
    GRAVAÇÃO DE TELA do macOS não está concedida.

E, ao mesmo tempo, no mesmo log, capturava sem falhar uma vez:

    📸 Capturando '🌐 Chrome · Tradovate - SMC QUANT PRO' em segundo plano...
    🖼️ Imagem atual obtida via: PrintWindow

As duas coisas eram verdade. O que faltava era cruzá-las.

TODAS as janelas que ele monitora são ABAS DO CHROME, capturadas pelo próprio
navegador via protocolo de depuração — que não passa por Gravação de Tela, não
exige a janela visível e nem pega a moldura. O diagnóstico do próprio programa
já imprimia isso com todas as letras:

    ABAS DO CHROME (porta 9222) — estas capturam SEM permissão do macOS

Ou seja: o programa TINHA as duas informações e nunca as juntou. O alarme
disparava olhando só para a permissão, sem perguntar o que estava sendo lido.

É O MESMO DEFEITO DO ALARME DE ORDEM INVENTADA, pego no mesmo dia: aviso que
aparece quando não há problema ensina a ignorar aviso. E este saía nos três
canais, todo arranque — o jeito mais rápido de treinar alguém a não ler nada
que o programa escreve.

A OUTRA METADE: "ESTÁ TUDO AUTORIZADO"
---------------------------------------
Pode estar — para o aplicativo errado. O macOS concede a permissão ao processo
RESPONSÁVEL, não ao nome do produto. Quem abre pelo Terminal precisa marcar o
Terminal; quem abre o .app marca o .app; quem roda pelo Python do Homebrew
pode ver "Python" na lista. A mensagem antiga mandava "marque o SMC Quant Pro",
que para ele podia ser uma linha que nem existe naquela tela.

Agora o programa DIZ o caminho do executável que está rodando, e ele confere.
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


ABA_TRADOVATE = "🌐 Chrome · Tradovate - SMC QUANT PRO"
ABA_WHATSAPP = "🌐 Chrome · (78) WhatsApp"


class TestAbaDeNavegadorNaoDependeDoMacOS(unittest.TestCase):

    def test_reconhece_a_aba_pelo_rotulo(self):
        self.assertTrue(P.e_aba_de_navegador(ABA_TRADOVATE))
        self.assertTrue(P.e_aba_de_navegador(ABA_WHATSAPP))

    def test_janela_de_aplicativo_NAO_e_aba(self):
        for j in ("Google Chrome", "Terminal", "MetaTrader 5", ""):
            self.assertFalse(P.e_aba_de_navegador(j), repr(j))

    def test_espaco_em_volta_nao_confunde(self):
        self.assertTrue(P.e_aba_de_navegador("  " + ABA_TRADOVATE + "  "))

    def test_None_nao_levanta(self):
        self.assertFalse(P.e_aba_de_navegador(None))


class TestOAlarmeSoTocaQuandoAfetaOQueELELE(unittest.TestCase):

    def test_O_CASO_DELE_so_abas_do_Chrome_NAO_alarma(self):
        """A reclamação inteira em um teste: permissão negada, mas tudo que
        ele monitora é aba do Chrome — que o navegador captura sozinho."""
        em_risco, _motivo = P.visao_em_risco([ABA_TRADOVATE, ABA_WHATSAPP], False)
        self.assertFalse(em_risco)

    def test_uma_janela_do_sistema_JA_justifica_o_alerta(self):
        """Uma só que dependa da captura do sistema é motivo suficiente — o
        que muda é que agora o alerta diz QUAL, em vez de acusar o conjunto."""
        em_risco, motivo = P.visao_em_risco([ABA_TRADOVATE, "Google Chrome"], False)
        self.assertTrue(em_risco)
        self.assertIn("Google Chrome", motivo)

    def test_o_motivo_NOMEIA_as_janelas_afetadas(self):
        """'a captura pode sair preta' não diz a ele o que fazer. O nome da
        janela diz."""
        _r, motivo = P.visao_em_risco(["MetaTrader 5", "Terminal"], False)
        self.assertIn("MetaTrader 5", motivo)

    def test_permissao_concedida_nao_alarma_nunca(self):
        self.assertFalse(P.visao_em_risco(["Google Chrome"], True)[0])

    def test_fora_do_mac_a_pergunta_nao_se_aplica(self):
        """None é 'não se aplica' (Windows), e não 'não concedida'. Tratar os
        dois como a mesma coisa faria o Windows receber um alerta sobre uma
        permissão que não existe lá."""
        self.assertFalse(P.visao_em_risco(["qualquer janela"], None)[0])

    def test_sem_janela_escolhida_ele_AVISA_mas_explica(self):
        """Não dá para dizer que está tudo bem: a próxima janela que ele
        escolher pode depender da permissão. Mas dá para dizer isso em vez de
        gritar 'VISÃO EM RISCO'."""
        em_risco, motivo = P.visao_em_risco([], False)
        self.assertTrue(em_risco)
        self.assertIn("nenhuma janela escolhida", motivo)


class TestOProgramaDIZQualProcessoAutorizar(unittest.TestCase):

    def test_devolve_nome_e_caminho_do_executavel(self):
        app, caminho = P.quem_precisa_da_permissao()
        self.assertTrue(app)
        self.assertTrue(caminho)
        self.assertIn(app.split(".")[0].lower(),
                      os.path.basename(caminho).lower() + app.lower())

    def test_o_caminho_e_o_do_processo_QUE_ESTA_RODANDO(self):
        """É esta a resposta para 'está tudo autorizado': pode estar, para o
        aplicativo errado. O macOS concede ao processo responsável, não ao
        nome do produto."""
        _app, caminho = P.quem_precisa_da_permissao()
        self.assertEqual(caminho, sys.executable)

    def test_o_diagnostico_de_arranque_mostra_o_processo(self):
        fonte = _fonte("plataforma.py")
        # Âncora COM os parênteses: `def diagnostico` casa antes com
        # `diagnostico_janelas`, que é outra função — âncora frouxa mede
        # o trecho errado do arquivo e falha sem defeito nenhum.
        i = fonte.index("def diagnostico():")
        self.assertIn("quem_precisa_da_permissao", fonte[i:i + 2500])
        self.assertIn("Autorize ESTE processo", fonte[i:i + 2500])

    def test_o_diagnostico_diz_que_ABA_nao_depende_disto(self):
        """Sem esta ressalva, a linha 'NÃO concedida' continua sugerindo que
        ele está cego quando não está."""
        fonte = _fonte("plataforma.py")
        i = fonte.index("def diagnostico():")
        self.assertIn("abas do Chrome", fonte[i:i + 2500])


class TestOAvisoNoMotorUsaARegraNova(unittest.TestCase):

    def setUp(self):
        self.codigo = _fonte("main_app.py")

    def test_o_alarme_do_motor_consulta_visao_em_risco(self):
        i = self.codigo.index("VOU OPERAR SOZINHA COM A VISÃO EM RISCO")
        trecho = self.codigo[max(0, i - 2000):i]
        self.assertIn("visao_em_risco", trecho)

    def test_o_alarme_NOMEIA_o_processo_a_autorizar(self):
        i = self.codigo.index("VOU OPERAR SOZINHA COM A VISÃO EM RISCO")
        trecho = self.codigo[max(0, i - 2000):i + 1800]
        self.assertIn("quem_precisa_da_permissao", trecho)

    def test_o_alarme_NAO_manda_mais_reiniciar_a_toa(self):
        """REGRA TROCADA EM 28/08, e a nova é melhor.

        A antiga mandava fechar e reabrir, porque o macOS lê a permissão
        quando o processo nasce. Só que o log dele PROVOU que o título das
        janelas volta a ser legível na mesma execução, sem reinício — e ele
        concedeu a permissão no meio do pregão, com posição aberta. Mandar
        reiniciar ali é mandar desligar o motor à toa.

        Agora o programa reconfere a cada ciclo e ANUNCIA quando passa a
        valer. A instrução certa deixou de ser 'reabra' e passou a ser
        'marque, que eu percebo sozinha'."""
        i = self.codigo.index("VOU OPERAR SOZINHA COM A VISÃO EM RISCO")
        trecho = self.codigo[i:i + 1800].lower()
        self.assertNotIn("reabra o programa", trecho)
        self.assertIn("não precisa", trecho)

    def test_o_alarme_promete_CONFERIR_sozinha_depois(self):
        i = self.codigo.index("VOU OPERAR SOZINHA COM A VISÃO EM RISCO")
        trecho = self.codigo[i:i + 1800].lower()
        self.assertIn("confiro sozinha", trecho)

    def test_o_aviso_de_arranque_tem_o_ramo_SEM_RISCO(self):
        """Quando só há abas, o programa explica em vez de alarmar — e diz
        quando isso passa a importar."""
        i = self.codigo.index("NÃO estou conseguindo ler o TÍTULO das")
        trecho = self.codigo[max(0, i - 900):i + 2200]
        self.assertIn("visao_em_risco", trecho)
        self.assertIn("ISSO NÃO TE ATRAPALHA AGORA", trecho)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOProgramaACHAOnodeNoWindows(unittest.TestCase):
    """O CLIENTE AUTORIZOU A INSTALACAO DO NODE E O PAINEL DIZIA QUE NAO TINHA.

    Foto de 25/08: "STATUS: Node.js não encontrado", em vermelho, num
    Windows onde o cliente tinha acabado de autorizar a instalação — e ela
    tinha funcionado.

    A CAUSA. `caminho_node()` procurava no PATH e, se não achasse, ia aos
    lugares conhecidos — SÓ QUE ESSA SEGUNDA BUSCA existia apenas para o
    macOS. No Windows ele parava no `shutil.which("node")`.

    E o PATH é lido quando o PROCESSO NASCE. O instalador do Node acrescenta
    a pasta ao PATH do sistema, mas nenhuma janela já aberta — nem o Explorer
    que lançou o programa — enxerga a mudança até ser reiniciada. Então o
    Node estava lá, instalado e funcionando, e o programa dizia que não.

    O mais irritante: o comentário da própria função já dizia a regra certa
    — "'não achei no PATH' não é a mesma coisa que 'não está instalado'".
    A regra estava escrita; faltava aplicá-la ao outro sistema.
    """

    def test_existe_lista_de_pastas_conhecidas_do_Windows(self):
        self.assertTrue(hasattr(P, "_PASTAS_BIN_WINDOWS"))
        self.assertGreaterEqual(len(P._PASTAS_BIN_WINDOWS), 3)

    def test_a_lista_cobre_onde_o_instalador_oficial_poe_o_node(self):
        """O instalador do nodejs.org põe em Program Files\\nodejs; a
        instalação por usuário vai para LOCALAPPDATA\\Programs."""
        juntas = " ".join(P._PASTAS_BIN_WINDOWS).lower()
        self.assertIn("nodejs", juntas)
        self.assertIn("programs", juntas)

    def test_caminho_node_procura_no_Windows_e_nao_so_no_PATH(self):
        fonte = _fonte("plataforma.py")
        i = fonte.index("def caminho_node")
        corpo = fonte[i:i + 2200]
        self.assertIn("E_WINDOWS", corpo)
        self.assertIn("_PASTAS_BIN_WINDOWS", corpo)
        self.assertIn("node.exe", corpo)

    def test_garantir_path_completa_o_PATH_no_Windows_tambem(self):
        """Antes ele devolvia lista vazia fora do Mac, e o resto do programa
        seguia com o PATH que a janela tinha ao nascer."""
        fonte = _fonte("plataforma.py")
        i = fonte.index("def garantir_path_do_sistema")
        corpo = fonte[i:i + 2500]
        self.assertIn("E_WINDOWS", corpo)
        self.assertIn("_PASTAS_BIN_WINDOWS", corpo)

    def test_a_busca_do_Mac_continua_intacta(self):
        """Consertar um sistema não pode quebrar o outro."""
        fonte = _fonte("plataforma.py")
        i = fonte.index("def caminho_node")
        self.assertIn("_PASTAS_BIN_MACOS", fonte[i:i + 2200])
