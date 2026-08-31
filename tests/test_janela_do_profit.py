"""O PROFIT ESTAVA ABERTO, EM TELA CHEIA, E NÃO APARECIA NA LISTA.

28/08, 10:32. Duas fotos: na primeira, o Profit ocupando a tela inteira do
Mac, com o gráfico do WINFUT rodando, order blocks e FVG desenhados. Na
segunda, o seletor de janelas do SMC Quant Pro aberto, mostrando:

    (⚠️ SEM permissão de Gravação de Tela — os títulos vêm vazios)
    🌐 Chrome · Tradovate - SMC QUANT PRO
    🌐 Chrome · Calendário Econômico - Investing.com
    Claude — janela 1 (800x600)  [outra área de trabalho]
    Claude — janela 2 (800x600)  [outra área de trabalho]
    Google Chrome  [outra área de trabalho]
    Terminal  [outra área de trabalho]

Sem Profit. E — a prova que fecha o caso — SEM A JANELA DO PRÓPRIO SMC QUANT
PRO, que é de onde a foto foi tirada. Uma janela que existe, está na tela e é
inegavelmente de um aplicativo.

POR ELIMINAÇÃO, SÓ UM FILTRO PODIA COMER AQUELAS DUAS
------------------------------------------------------
As janelas passam por: camada 0, opacidade, tamanho mínimo, forma quando não
há título, e "o dono tem ícone no Dock". Profit em tela cheia e a janela do
próprio programa passam em todos, menos possivelmente no último —
`activationPolicy == Regular`, que eu tinha escrito como PORTEIRO.

Essa política mente em mais casos do que eu supus: programa rodando por
camada de compatibilidade, por máquina virtual, ou lançado de um jeito que o
macOS não classifica como aplicativo comum. E o preço do erro é assimétrico:
uma janela a mais na lista custa uma linha; a janela do gráfico escondida
custa o pregão, e sem dizer que escondeu.

Agora ela ORDENA (as do Dock primeiro) em vez de EXCLUIR.

E O DIAGNÓSTICO PASSA A MOSTRAR O QUE FOI DESCARTADO
-----------------------------------------------------
O diagnóstico listava as janelas que SOBRARAM. Para achar uma que sumiu, isso
não serve para nada: é preciso ver o que foi jogado fora e por quê. Se a
causa não for a que eu concluí acima, um clique em 'Diagnosticar janelas'
mostra qual filtro comeu o Profit.
"""

import os
import sys
import unittest

from harness import RAIZ, funcao_inteira

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import plataforma as P          # noqa: E402


def _fonte(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


def _janela(app, pid, larg, alt, nome="", camada=0, alpha=1.0, wid=1):
    """Uma linha crua do Quartz, no formato que o macOS devolve."""
    return {"kCGWindowOwnerName": app, "kCGWindowOwnerPID": pid,
            "kCGWindowLayer": camada, "kCGWindowAlpha": alpha,
            "kCGWindowName": nome, "kCGWindowNumber": wid,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": larg, "Height": alt}}


class _QuartzFalso:
    """O mínimo do Quartz para a listagem rodar fora do Mac. Sem isto, esta
    regra só poderia ser testada na máquina dele — que é onde ela falhou."""
    kCGWindowListOptionOnScreenOnly = 1
    kCGWindowListOptionAll = 0
    kCGWindowListExcludeDesktopElements = 16
    kCGNullWindowID = 0

    def __init__(self, janelas, na_tela=()):
        self._janelas = janelas
        self._na_tela = list(na_tela)

    def CGWindowListCopyWindowInfo(self, opcoes, _id):
        if opcoes & self.kCGWindowListOptionOnScreenOnly:
            return [w for w in self._janelas
                    if w["kCGWindowNumber"] in self._na_tela]
        return list(self._janelas)


class _Cenario:
    """A máquina dele, montada à mão: Profit em tela cheia, a janela do
    próprio programa, Chrome, Terminal — e um processo de sistema."""

    JANELAS = [
        _janela("Profit", pid=900, larg=2000, alt=1250, wid=11),
        _janela("python-smc", pid=901, larg=1400, alt=900, wid=12),
        _janela("Google Chrome", pid=902, larg=1710, alt=985, wid=13),
        _janela("Terminal", pid=903, larg=900, alt=600, wid=14),
        _janela("Accessibility Services", pid=904, larg=800, alt=600, wid=15),
        _janela("Google Chrome", pid=902, larg=1710, alt=140, wid=16),
        _janela("Dock", pid=905, larg=1710, alt=90, camada=20, wid=17),
    ]
    # O AppKit só reconhece Chrome e Terminal como "aplicativo com ícone no
    # Dock" — que foi, exatamente, o que aconteceu na máquina dele.
    PIDS_REGULAR = {902, 903}

    # Fora do Mac o `Quartz` nem existe no módulo, então guardar/repor tem de
    # ser por nome — `P.Quartz` levantaria AttributeError no Linux, que é
    # justamente onde esta suíte roda.
    _NOMES = ("QUARTZ_DISPONIVEL", "E_MACOS", "Quartz", "_pids_de_aplicativos",
              "abas_chrome", "permissao_de_tela_ok",
              "titulos_por_acessibilidade")
    _AUSENTE = object()

    def __enter__(self):
        self._salvos = {n: getattr(P, n, self._AUSENTE) for n in self._NOMES}
        P.QUARTZ_DISPONIVEL = True
        P.E_MACOS = True
        P.Quartz = _QuartzFalso(self.JANELAS, na_tela=[11, 12, 13])
        P._pids_de_aplicativos = lambda: set(self.PIDS_REGULAR)
        P.abas_chrome = lambda *a, **k: []
        P.permissao_de_tela_ok = lambda: False
        P.titulos_por_acessibilidade = lambda *a, **k: []
        return self

    def __exit__(self, *_e):
        for nome, valor in self._salvos.items():
            if valor is self._AUSENTE:
                if hasattr(P, nome):
                    delattr(P, nome)
            else:
                setattr(P, nome, valor)
        return False


class TestOProfitVOLTAParaALista(unittest.TestCase):

    def test_o_Profit_aparece(self):
        """A queixa inteira em uma linha."""
        with _Cenario():
            apps = [j["app"] for j in P._janelas_macos()]
        self.assertIn("Profit", apps)

    def test_a_janela_do_PROPRIO_programa_aparece(self):
        """Era a prova de que o filtro estava errado: ela existe, está na
        tela, e sumia da lista que ela mesma monta."""
        with _Cenario():
            apps = [j["app"] for j in P._janelas_macos()]
        self.assertIn("python-smc", apps)

    def test_processo_de_SISTEMA_continua_de_fora(self):
        """Consertar o falso negativo não pode desfazer a queixa original —
        o seletor já mostrou 'Accessibility Services' uma vez."""
        with _Cenario():
            apps = [j["app"] for j in P._janelas_macos()]
        self.assertNotIn("Accessibility Services", apps)

    def test_camada_de_sistema_continua_de_fora(self):
        with _Cenario():
            apps = [j["app"] for j in P._janelas_macos()]
        self.assertNotIn("Dock", apps)

    def test_camada_auxiliar_do_Chrome_continua_de_fora(self):
        """1710x140 sem título é sombra de janela, não é janela."""
        with _Cenario():
            alturas = [j["altura"] for j in P._janelas_macos()
                       if j["app"] == "Google Chrome"]
        self.assertEqual(alturas, [985])

    def test_quem_TEM_icone_no_Dock_vem_primeiro_no_seletor(self):
        """O filtro virou ordem: o que o macOS reconhece sobe, o resto desce,
        mas tudo aparece."""
        with _Cenario():
            rotulos = [r for r in P.listar_janelas() if not r.startswith("(")]
        self.assertTrue(rotulos)
        i_chrome = next(i for i, r in enumerate(rotulos) if "Chrome" in r)
        i_profit = next(i for i, r in enumerate(rotulos) if "Profit" in r)
        self.assertLess(i_chrome, i_profit)

    def test_o_Profit_ESTA_no_seletor_e_da_para_escolher(self):
        with _Cenario():
            rotulos = P.listar_janelas()
        self.assertTrue(any("Profit" in r for r in rotulos), rotulos)

    def test_a_marca_do_Dock_viaja_com_a_janela(self):
        with _Cenario():
            porto = {j["app"]: j.get("do_dock") for j in P._janelas_macos()}
        self.assertFalse(porto["Profit"])
        self.assertTrue(porto["Google Chrome"])

    def test_sem_AppKit_ninguem_e_excluido_e_ninguem_e_rebaixado(self):
        """Quando o AppKit não responde, a política não existe — e não pode
        virar uma exclusão silenciosa por omissão."""
        with _Cenario():
            P._pids_de_aplicativos = lambda: None
            js = P._janelas_macos()
        self.assertTrue(all(j.get("do_dock") for j in js))
        self.assertIn("Profit", [j["app"] for j in js])


class TestOAvisoDeixaDeSerAOpcaoPadrao(unittest.TestCase):
    """Na foto, o campo selecionado era '(⚠️ SEM permissão...)' — que não é
    janela nenhuma. O primeiro item de uma lista de escolha tem de ser uma
    escolha válida."""

    def test_o_aviso_vai_para_o_FIM_da_lista(self):
        with _Cenario():
            rotulos = P.listar_janelas()
        self.assertTrue(rotulos[-1].startswith("(⚠"))
        self.assertFalse(rotulos[0].startswith("(⚠"))

    def test_o_aviso_explica_que_ABA_do_Chrome_nao_depende_disso(self):
        with _Cenario():
            aviso = P.listar_janelas()[-1]
        self.assertIn("Chrome", aviso)

    def test_escolher_o_aviso_continua_nao_virando_captura(self):
        with _Cenario():
            aviso = P.listar_janelas()[-1]
            self.assertIsNone(P.encontrar_janela(aviso))


class TestODiagnosticoMOSTRAOQueFoiDescartado(unittest.TestCase):
    """Uma lista que só mostra o que passou não diagnostica ausência."""

    def test_o_descarte_e_registrado_com_o_motivo(self):
        with _Cenario():
            P._janelas_macos()
            descartes = list(P._DESCARTADAS)
        apps = {d["app"] for d in descartes}
        self.assertIn("Accessibility Services", apps)
        self.assertIn("Dock", apps)
        for d in descartes:
            self.assertTrue(d["motivo"], d)

    def test_o_Profit_NAO_esta_mais_entre_os_descartados(self):
        with _Cenario():
            P._janelas_macos()
            apps = {d["app"] for d in P._DESCARTADAS}
        self.assertNotIn("Profit", apps)

    def test_o_texto_do_diagnostico_traz_a_secao_de_descartes(self):
        with _Cenario():
            texto = P.diagnostico_janelas()
        self.assertIn("DESCARTADAS", texto)
        self.assertIn("é este filtro que precisa mudar", texto)

    def test_o_diagnostico_lista_o_Profit_entre_as_ENCONTRADAS(self):
        with _Cenario():
            texto = P.diagnostico_janelas()
        self.assertIn("Profit", texto)

    def test_a_lista_de_descartes_nao_cresce_para_sempre(self):
        """Ela é reescrita a cada listagem — um registro de diagnóstico que
        acumula vira vazamento de memória num programa que roda o dia todo."""
        with _Cenario():
            P._janelas_macos()
            n1 = len(P._DESCARTADAS)
            P._janelas_macos()
            n2 = len(P._DESCARTADAS)
        self.assertEqual(n1, n2)


class TestOProgramaAVISAQuePrecisaDaPermissao(unittest.TestCase):
    """Aba do Chrome é capturada pelo próprio navegador e não depende de
    permissão nenhuma. QUALQUER outra janela depende — e sem ela a imagem sai
    preta, sem erro. A hora de dizer isso é quando ele inclui a janela, não
    depois de três ciclos pulados."""

    def setUp(self):
        # A FUNÇÃO INTEIRA, NÃO UMA JANELA DE N BYTES.
        #
        # Isto era `self.codigo[i:i + 3200]`, e a correção de 28/08 acrescentou
        # um aviso ANTES do da permissão — empurrando o trecho procurado para
        # fora da janela. Cinco testes ficaram vermelhos sem que nada tivesse
        # se quebrado. Um recorte por tamanho mede a POSIÇÃO do código, que não
        # é regra nenhuma; o que se quer medir é se a regra continua no lugar.
        self.codigo = _fonte("main_app.py")
        self.corpo = funcao_inteira(self.codigo, "_incluir_janela_monitorada")

    def test_o_aviso_existe_no_caminho_de_incluir(self):
        self.assertIn("GRAVAÇÃO DE TELA", self.corpo)

    def test_a_outra_AREA_DE_TRABALHO_e_avisada_ANTES_da_permissao(self):
        """A ordem aqui é a lição de 28/08, e por isso está travada.

        Ele passou o dia mexendo na permissão porque foi para lá que a
        ferramenta o mandou — enquanto o Profit estava em TELA CHEIA, noutra
        área de trabalho, onde não há pixel para ler e permissão nenhuma
        resolve. Quem avisa primeiro decide onde a pessoa vai procurar."""
        area = self.corpo.index("[outra área de trabalho]")
        permissao = self.corpo.index("permissao_de_tela_ok")
        self.assertLess(area, permissao,
                        "o aviso de permissão voltou a vir primeiro — é assim "
                        "que se manda o trader procurar no lugar errado")

    def test_o_aviso_de_outra_area_DIZ_que_nao_e_permissao(self):
        trecho = self.corpo[self.corpo.index("[outra área de trabalho]"):]
        trecho = trecho[:trecho.index("permissao_de_tela_ok")]
        # A frase é quebrada em duas linhas no fonte ("...ISSO NÃO " + "É
        # PERMISSÃO:..."), então o teste procura a metade que carrega o
        # sentido, e não a costura entre as duas.
        self.assertIn("É PERMISSÃO:", trecho.upper())
        self.assertIn("Ctrl+Cmd+F", trecho)

    def test_ele_so_avisa_para_janela_que_NAO_e_aba(self):
        self.assertIn("e_aba_de_navegador", self.corpo)

    def test_ele_so_avisa_quando_a_permissao_FALTA(self):
        self.assertIn("permissao_de_tela_ok", self.corpo)

    def test_o_aviso_diz_QUAL_processo_autorizar(self):
        """'marque o SMC Quant Pro' pode ser uma linha que nem existe naquela
        tela — o macOS concede ao processo responsável."""
        self.assertIn("quem_precisa_da_permissao", self.corpo)

    def test_o_aviso_manda_REABRIR_o_programa(self):
        """O macOS só lê a permissão quando o processo nasce."""
        self.assertIn("REABRA o", self.corpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestAPromessaQueElaNaoPodeCumprir(unittest.TestCase):
    """28/08, 10:38 e 10:40.

        "Vou encaminhar ao time de desenvolvimento a sugestão de integrar um
         calendário de eventos econômicos..."
        "Já encaminhei sua solicitação ao time de desenvolvimento para incluir
         alertas automáticos... Atualização em breve."

    Não há time de desenvolvimento do outro lado do chat, não há fila de
    solicitações, e nada foi agendado. Ele ficou esperando uma novidade que
    nunca viria — e a espera é o dano: quem acredita numa promessa dessas para
    de procurar o dado sozinho bem na hora em que precisa dele.

    É o mesmo defeito do alarme de ordem inventada, com outro verbo."""

    def _f(self):
        from harness import carregar
        return carregar(["_RE_PROMESSA_IMPOSSIVEL",
                         "censurar_promessa_impossivel"]
                        )["censurar_promessa_impossivel"]

    def test_as_TRES_frases_reais_sao_pegas(self):
        f = self._f()
        for frase in (
                "Entendido, Josevan. Vou encaminhar ao time de desenvolvimento "
                "a sugestão de integrar um calendário de eventos econômicos.",
                "Já encaminhei sua solicitação ao time de desenvolvimento para "
                "incluir alertas automáticos de eventos. Atualização em breve.",
                "Se quiser, posso te alertar automaticamente quando houver "
                "novidades sobre agendas de eventos. Deseja isso?"):
            _txt, pegou = f(frase)
            self.assertTrue(pegou, frase)

    def test_o_aviso_manda_NAO_FICAR_ESPERANDO(self):
        """É a instrução que importa: o dano dessa promessa é a espera."""
        texto, _p = self._f()("Já encaminhei sua solicitação ao time de "
                              "desenvolvimento.")
        self.assertIn("NÃO FIQUE ESPERANDO", texto)

    def test_a_resposta_original_CONTINUA_visivel(self):
        """Apagar a frase esconderia o defeito; deixá-la sozinha repetiria a
        mentira. O aviso vai anexado, como no alarme de ordem inventada."""
        original = "Já encaminhei sua solicitação ao time de desenvolvimento."
        texto, _p = self._f()(original)
        self.assertIn(original, texto)

    def test_promessa_LEGITIMA_passa_intacta(self):
        """'eu te aviso aqui no chat quando sair um cenário' é uma coisa que
        o programa faz de verdade, todo ciclo. Se o filtro engolisse isso,
        engoliria o trabalho da ferramenta."""
        f = self._f()
        for frase in (
                "Assim que o motor achar um cenário válido eu te aviso aqui.",
        # 31/08: a guarda passou a pegar "vou pedir ao motor" e
        # "aguardando dados do sistema". Estas duas continuam
        # legítimas — é literalmente o que o ciclo faz.
        "Assim que o motor ler o gráfico eu trago a análise.",
                "Vou analisar o gráfico agora e te digo o que vejo.",
                "Não tenho acesso a agendas de eventos externos.",
                "O cenário é de compra no MESU6, alvo em 7745.50."):
            texto, pegou = f(frase)
            self.assertFalse(pegou, frase)
            self.assertEqual(texto, frase)

    def test_vazio_nao_levanta(self):
        self.assertEqual(self._f()(None), ("", False))


class TestAgendaDeEventoVaiParaABuscaReal(unittest.TestCase):
    """A primeira resposta, às 10:37, foi CERTA: 'não tenho acesso a agendas
    de eventos externos'. Ele insistiu e a segunda inventou quatro coisas —
    entre elas que Kevin Warsh seria 'CTO da Tradovate' (ele é ex-diretor do
    Federal Reserve, e um discurso dele mexe com juro).

    A pergunta não chegava à busca por UMA palavra: o filtro pedia
    'agenda/calendário/notícia' e ele escreveu 'discurso'. A ferramenta tem
    busca na web sem chave de API; faltava a pergunta chegar nela."""

    def _intencao(self, txt):
        from test_conversa import _ns_intencao
        return _ns_intencao()["interpretar_intencao"](txt)

    def test_a_pergunta_EXATA_dele_vai_para_NOTICIAS(self):
        self.assertEqual(
            self._intencao("Tiger Que horas é o discurso de Kevin Warsh hoje"),
            "NOTICIAS")

    def test_os_eventos_de_macro_que_movem_o_indice(self):
        for frase in ("que horas sai o payroll hoje",
                      "tem reunião do FOMC essa semana?",
                      "quando sai o CPI hoje",
                      "que horas é a fala do Powell hoje"):
            self.assertEqual(self._intencao(frase), "NOTICIAS", frase)

    def test_pergunta_de_grafico_NAO_vira_busca_na_web(self):
        """Consertar um caminho não pode roubar o outro: 'que horas' também
        aparece em pergunta de tela."""
        self.assertNotEqual(
            self._intencao("que horas foi o último print da tela?"), "NOTICIAS")


class TestElaTEMAcessoAWebEDizQueNaoTem(unittest.TestCase):
    """28/08, 10:46.

        ❯ VERIFICA PARA MIM O INDICE BOVESPA FUTURO WINV26
        ✳ não está listado nos dados da mesa em tempo real
        ❯ VERIFICA NA WEB
        ✳ Não tenho acesso direto à web
        ❯ PRECISO QUE VOCE FACA ISSO
        ✳ Não tenho acesso direto à web

    Três vezes, a última depois de ele mandar fazer. E ELA TEM: o programa
    busca cotação no Yahoo, manchete por RSS e o resto no DuckDuckGo, tudo sem
    chave de API. O modelo não sabe do que o programa é capaz — quem sabe é o
    roteador, e nele faltavam DUAS palavras: 'verificar' na lista de verbos de
    cotação e 'na web' na de pesquisa (havia 'na internet')."""

    def _intencao(self, txt):
        from test_conversa import _ns_intencao
        return _ns_intencao()["interpretar_intencao"](txt)

    def test_as_DUAS_frases_dele_chegam_a_busca(self):
        self.assertEqual(
            self._intencao("VERIFICA PARA MIM O INDICE BOVESPA FUTURO WINV26"),
            "COTACAO")
        self.assertEqual(self._intencao("VERIFICA NA WEB"), "PESQUISAR")

    def test_os_outros_verbos_de_conferir_tambem(self):
        for frase in ("confere o ibovespa pra mim",
                      "checa o dolar hoje",
                      "consulta o preço do ouro"):
            self.assertEqual(self._intencao(frase), "COTACAO", frase)

    def test_web_e_internet_valem_a_mesma_coisa(self):
        for frase in ("procura na web", "pesquisa na internet",
                      "dá uma olhada na web"):
            self.assertEqual(self._intencao(frase), "PESQUISAR", frase)

    def test_o_grafico_NAO_e_roubado_pela_cotacao(self):
        """'olha o gráfico' e 'tira um print' continuam sendo o que eram —
        consertar um caminho não pode comer o outro."""
        self.assertEqual(self._intencao("olha o gráfico"), "VER_GRAFICO")
        self.assertNotIn(self._intencao("tira um print"),
                         ("COTACAO", "PESQUISAR"))


class TestElaSeCONFUNDIACOMSIMESMA(unittest.TestCase):
    """'EMBORA JA TENHA PERMITIDO ELA CONTINUA PEDINDO PERMISSAO' (28/08).

    A foto dos Ajustes mostra 'SMC Quant Pro' marcado em Gravação de Tela. E
    no MESMO log do programa, duas linhas se contradiziam:

        🖥️ Gravação de Tela: NÃO concedida         (banner do arranque)
           Permissão de Gravação de Tela: concedida  (diagnóstico, depois)

    A regra era: 'se existe janela de OUTRO aplicativo com título legível, a
    permissão vale'. A comparação era por NOME DE EXECUTÁVEL —
    basename(sys.executable) dá 'python-smc', e o macOS reporta a janela dele
    como aplicativo 'Python'. 'python-smc' não está contido em 'python', então
    a PRÓPRIA janela passava no teste de 'é de outro aplicativo'.

    E o título da própria janela é legível SEMPRE, com permissão ou sem. Ou
    seja: o programa podia declarar 'concedida' só de enxergar a si mesmo, e
    'NÃO concedida' no arranque, quando sua janela ainda não tinha título. A
    resposta oscilava com o MOMENTO, não com a permissão — e ele levava a
    culpa por uma coisa que já tinha feito certo."""

    def _com(self, janelas, meu_pid):
        # A função sob teste É `permissao_de_tela_ok`, então ela NÃO pode
        # entrar no cenário como stub — aqui a verdadeira é reposta por cima.
        import os as _os
        salvo_pid, verdadeira = _os.getpid, P.permissao_de_tela_ok
        try:
            _os.getpid = lambda: meu_pid
            cen = _Cenario()
            cen.JANELAS = janelas
            cen.PIDS_REGULAR = {j["kCGWindowOwnerPID"] for j in janelas}
            with cen:
                P.permissao_de_tela_ok = verdadeira
                return P.permissao_de_tela_ok()
        finally:
            _os.getpid = salvo_pid

    def test_ver_a_PROPRIA_janela_com_titulo_NAO_prova_permissao(self):
        """O caso exato: a única janela titulada é a dele, e o macOS a chama
        de 'Python' enquanto o executável se chama 'python-smc'."""
        so_a_dele = [_janela("Python", pid=4240, larg=1710, alt=1012,
                             nome="SMC Quant Pro - Trader Institucional AI",
                             wid=1)]
        self.assertFalse(self._com(so_a_dele, meu_pid=4240))

    def test_janela_de_OUTRO_processo_com_titulo_prova(self):
        com_outra = [
            _janela("Python", pid=4240, larg=1710, alt=1012,
                    nome="SMC Quant Pro", wid=1),
            _janela("Profit", pid=18760, larg=2000, alt=1250,
                    nome="Profit Pro - WINFUT", wid=2),
        ]
        self.assertTrue(self._com(com_outra, meu_pid=4240))

    def test_ninguem_com_titulo_e_permissao_faltando(self):
        """Sem a permissão, o macOS entrega a lista SEM os títulos."""
        sem_titulo = [
            _janela("Python", pid=4240, larg=1710, alt=1012, wid=1),
            _janela("Profit", pid=18760, larg=2000, alt=1250, wid=2),
        ]
        self.assertFalse(self._com(sem_titulo, meu_pid=4240))

    def test_o_PID_viaja_com_a_janela(self):
        """É o dado que substituiu a comparação por nome."""
        with _Cenario():
            pids = {j["app"]: j.get("pid") for j in P._janelas_macos()}
        self.assertEqual(pids["Profit"], 900)
        self.assertEqual(pids["Terminal"], 903)


class TestAViradaDaPermissaoEANUNCIADA(unittest.TestCase):
    """Ele concedeu no meio do pregão e não recebeu retorno nenhum de que
    tinha dado certo — a pergunta só era feita uma vez, no arranque do motor.
    Ficar calado depois de ter reclamado alto é o que faz alguém refazer uma
    configuração que já estava certa."""

    def setUp(self):
        self.codigo = _fonte("main_app.py")
        i = self.codigo.index("def _avisar_olho_cego_no_autonomo")
        self.corpo = self.codigo[i:i + 4200]

    def test_a_virada_para_CONCEDIDA_e_anunciada(self):
        self.assertIn("GRAVAÇÃO DE TELA CONCEDIDA", self.corpo)

    def test_o_anuncio_so_sai_se_ELA_TINHA_reclamado(self):
        """Elogio a cada ciclo é tão ruim quanto queixa a cada ciclo."""
        self.assertIn("_avisou_sem_permissao", self.corpo)

    def test_a_QUEIXA_tambem_sai_uma_vez_por_virada(self):
        """A função passou a rodar a cada ciclo; sem trava, a queixa iria ao
        log, ao chat E ao WhatsApp de cinco em cinco minutos — o defeito do
        alarme que toca sozinho, já consertado uma vez aqui."""
        self.assertIn("UMA VEZ POR VIRADA, NUNCA A CADA CICLO", self.corpo)

    def test_o_motor_reconfere_a_cada_ciclo(self):
        i = self.codigo.index("_janelas_ciclo = janelas_para_analisar()")
        antes = self.codigo[max(0, i - 900):i]
        self.assertIn("_avisar_olho_cego_no_autonomo", antes)

    def test_a_mensagem_NAO_manda_mais_reiniciar_a_toa(self):
        """Antes ela mandava fechar e reabrir. Agora ela mesma percebe."""
        self.assertIn("não precisa", self.corpo.lower())


class TestAPermissaoEPERGUNTADAAoMacOS(unittest.TestCase):
    """PARAR DE DEDUZIR. 28/08: o banner dizia "NÃO concedida" e o diagnóstico
    dizia "concedida" no mesmo log, porque a resposta saía de uma DEDUÇÃO
    (existe janela de outro app com título?) em vez da pergunta direta.

    O macOS tem `CGPreflightScreenCaptureAccess` desde o Catalina: responde
    exatamente isso, para ESTE processo, sem abrir caixa nenhuma. A dedução
    erra em dois sentidos — o Acessibilidade também devolve título (é outra
    permissão) e a própria janela do programa é sempre legível."""

    def test_ela_pergunta_ao_sistema_antes_de_deduzir(self):
        fonte = _fonte("plataforma.py")
        i = fonte.index("def permissao_de_tela_ok")
        # Janela larga: o comentário que explica o defeito de 28/08 mora
        # dentro da função, e janela curta mediria a prosa em vez do código.
        corpo = fonte[i:i + 3600]
        self.assertIn("CGPreflightScreenCaptureAccess", corpo)
        # A dedução continua como RESERVA, para macOS antigo ou pyobjc sem a
        # função — tirar a reserva trocaria um defeito por outro.
        self.assertIn("meu_pid", corpo)

    def test_a_reserva_vem_DEPOIS_da_pergunta_direta(self):
        fonte = _fonte("plataforma.py")
        i = fonte.index("def permissao_de_tela_ok")
        corpo = fonte[i:i + 3600]
        self.assertLess(corpo.index("CGPreflightScreenCaptureAccess"),
                        corpo.index("meu_pid"))

    def test_existe_um_jeito_de_PEDIR_a_permissao(self):
        """A caixa do macOS só aparece quando alguém pede. Sem isto, o
        programa reclamava e não tinha como provocar a pergunta."""
        self.assertTrue(callable(P.pedir_permissao_de_tela))
        fonte = _fonte("plataforma.py")
        i = fonte.index("def pedir_permissao_de_tela")
        self.assertIn("CGRequestScreenCaptureAccess", fonte[i:i + 900])

    def test_fora_do_mac_as_duas_devolvem_None(self):
        """None é 'não se aplica', não é 'não'.

        O sistema é FIXADO aqui em vez de confiar no estado global do módulo:
        outros arquivos da suíte ligam `E_MACOS` para exercitar o caminho do
        Mac, e um teste que depende de quem rodou antes acusa defeito onde
        não há."""
        salvo = P.E_MACOS
        try:
            P.E_MACOS = False
            self.assertIsNone(P.permissao_de_tela_ok())
            self.assertIsNone(P.pedir_permissao_de_tela())
        finally:
            P.E_MACOS = salvo


class TestOPassoAPassoCOBREOCasoDaLinhaJaMarcada(unittest.TestCase):
    """A foto dos Ajustes mostrava "SMC Quant Pro" LIGADO e o macOS reexibindo
    a caixa de permissão. As duas coisas eram verdade.

    O aplicativo não é assinado, então o macOS o identifica pelo CONTEÚDO do
    binário — que muda a cada versão. Para o sistema, a versão nova é outro
    programa, sem autorização; e a linha antiga continua na lista, marcada.
    A tela mostra concedida, o núcleo nega.

    Mandar "marque a caixinha" para quem já marcou é mandar repetir o que não
    funcionou. Era o laço em que ele estava preso."""

    def setUp(self):
        self.txt = P.como_liberar_gravacao_de_tela()

    def test_o_caso_da_linha_JA_MARCADA_vem_PRIMEIRO(self):
        i_ja = self.txt.index("JÁ APARECE MARCADO")
        i_nao = self.txt.index("NÃO APARECE NA LISTA")
        self.assertLess(i_ja, i_nao)

    def test_ele_manda_REMOVER_a_linha_e_nao_remarcar(self):
        self.assertIn("−", self.txt)
        self.assertIn("REMOVÊ-LA", self.txt)
        self.assertIn("Marcar de novo não adianta", self.txt)

    def test_ele_EXPLICA_por_que_isso_acontece_a_cada_versao(self):
        """Sem o porquê, a instrução vira superstição — e ele repete o passo
        errado na próxima atualização."""
        self.assertIn("não é\nassinado", self.txt)
        self.assertIn("versão nova", self.txt)

    def test_ele_diz_QUAL_processo_o_macOS_ve(self):
        self.assertIn("O PROCESSO QUE O macOS VÊ RODANDO", self.txt)

    def test_ele_diz_o_que_CONTINUA_funcionando(self):
        """Sem esta linha, o aviso soa como 'a ferramenta parou' — e ela não
        parou: as abas do Chrome não dependem desta permissão."""
        self.assertIn("abas do Chrome", self.txt)

    def test_o_aviso_do_motor_USA_este_passo_a_passo(self):
        codigo = _fonte("main_app.py")
        i = codigo.index("VOU OPERAR SOZINHA COM A VISÃO EM RISCO")
        trecho = codigo[max(0, i - 1200):i + 1200]
        self.assertIn("como_liberar_gravacao_de_tela", trecho)


class TestOAppPassaASerAssinado(unittest.TestCase):
    """A causa raiz da permissão que morre a cada versão. A assinatura ad-hoc
    dá ao pacote uma identidade estável — não substitui uma Developer ID da
    Apple, mas encerra a revogação silenciosa a cada atualização."""

    def setUp(self):
        with open(os.path.join(RAIZ, "CRIAR_APP.command"), encoding="utf-8") as f:
            self.sh = f.read()

    def test_o_criador_do_app_assina_o_pacote(self):
        self.assertIn("codesign --force --deep --sign -", self.sh)

    def test_a_assinatura_NAO_derruba_a_instalacao_se_falhar(self):
        """App sem assinatura funciona — só perde a permissão nas
        atualizações. Abortar a instalação por isso seria pior."""
        i = self.sh.index("codesign --force")
        trecho = self.sh[max(0, i - 200):i + 700]
        self.assertNotIn("falhou ", trecho)
        self.assertIn("funciona igual", trecho)

    def test_ela_so_roda_se_o_codesign_existir(self):
        i = self.sh.index("codesign --force")
        self.assertIn("command -v codesign", self.sh[max(0, i - 300):i])

    def test_o_texto_final_cobre_a_linha_ja_marcada(self):
        self.assertIn("JÁ APARECE MARCADO", self.sh)
        self.assertIn("REMOVÊ-LA", self.sh)
