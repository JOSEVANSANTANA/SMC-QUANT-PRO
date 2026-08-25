"""Os dois pacotes de entrega — Windows e Mac.

O BURACO QUE ISTO FECHA
-----------------------
Por várias versões o repositório teve `SMC_Quant_Pro_MAC.spec` e
`requirements-mac.txt`, e NÃO teve os equivalentes do Windows. Ou seja: dava
para reconstruir a versão do Mac a partir do repositório, e não dava para
reconstruir a do Windows — o `.spec` que gera o `.exe` vivia só na máquina do
trader. Ninguém percebeu porque nada verificava.

Aqui a simetria vira teste: o que existe de um lado tem de existir do outro,
e o `empacotar.py` tem de saber montar os dois.
"""

import os
import unittest

from harness import RAIZ


def _existe(*partes):
    return os.path.exists(os.path.join(RAIZ, *partes))


def _pacotes(lista):
    """Os pacotes que o pip de fato instalaria — sem comentários nem vazios."""
    with open(os.path.join(RAIZ, lista), encoding="utf-8") as f:
        return [l.strip().lower() for l in f
                if l.strip() and not l.lstrip().startswith("#")]


class TestSimetriaEntreOsSistemas(unittest.TestCase):
    def test_cada_arquivo_de_mac_tem_o_par_de_windows(self):
        pares = [
            ("requirements-mac.txt", "requirements.txt"),
            ("SMC_Quant_Pro_MAC.spec", "SMC_Quant_Pro.spec"),
            ("LEIA-ME_MAC.txt", "LEIA-ME_WINDOWS.txt"),
        ]
        for do_mac, do_windows in pares:
            self.assertTrue(_existe(do_mac), f"sumiu: {do_mac}")
            self.assertTrue(
                _existe(do_windows),
                f"'{do_mac}' existe mas '{do_windows}' não — o repositório "
                "voltou a saber compilar só para um sistema.")

    def test_o_spec_do_windows_e_do_windows_mesmo(self):
        with open(os.path.join(RAIZ, "SMC_Quant_Pro.spec"), encoding="utf-8") as f:
            spec = f.read()
        # Sem os módulos do pywin32 declarados, o .exe sai sem listar janelas.
        for modulo in ("win32gui", "win32crypt", "pywintypes"):
            self.assertIn(modulo, spec, modulo)
        # E o que é do Mac tem de estar EXCLUÍDO, não incluído.
        self.assertIn("excludes=[", spec)
        i = spec.index("excludes=[")
        self.assertIn("Quartz", spec[i:i + 300])

    def test_o_spec_do_mac_continua_sendo_do_mac(self):
        with open(os.path.join(RAIZ, "SMC_Quant_Pro_MAC.spec"), encoding="utf-8") as f:
            spec = f.read()
        self.assertIn("target_arch='arm64'", spec)
        # As permissões do macOS: sem estas chaves o sistema nega em silêncio.
        self.assertIn("NSScreenCaptureUsageDescription", spec)
        self.assertIn("NSMicrophoneUsageDescription", spec)

    def test_numpy_nas_duas_listas_de_dependencia(self):
        """O sounddevice importa numpy nos DOIS sistemas. Faltou no Mac e matou
        o microfone; não pode faltar no Windows pelo mesmo motivo."""
        for lista in ("requirements.txt", "requirements-mac.txt"):
            self.assertTrue(any(p.startswith("numpy") for p in _pacotes(lista)),
                            lista)

    def test_cada_lista_tem_a_biblioteca_de_janelas_do_seu_sistema(self):
        # Só as linhas que o pip realmente instala. Comentário citando o outro
        # sistema é explicação, não dependência — e foi assim que este teste
        # falhou na primeira vez, acusando um comentário.
        win = _pacotes("requirements.txt")
        mac = _pacotes("requirements-mac.txt")
        self.assertTrue(any(p.startswith("pywin32") for p in win))
        self.assertFalse(any(p.startswith("pyobjc") for p in win),
                         "pyobjc não instala no Windows")
        self.assertTrue(any(p.startswith("pyobjc-framework-quartz") for p in mac))
        self.assertFalse(any(p.startswith("pywin32") for p in mac),
                         "pywin32 não instala no Mac")


class TestEmpacotador(unittest.TestCase):
    def _mod(self):
        import importlib.util
        caminho = os.path.join(RAIZ, "empacotar.py")
        spec = importlib.util.spec_from_file_location("empacotar", caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_todo_arquivo_listado_existe_de_verdade(self):
        """É a checagem que o próprio script faz antes de zipar. Se ela falhar
        aqui, o pacote sairia incompleto — e isso só apareceria na máquina do
        trader, no meio do pregão."""
        m = self._mod()
        m.conferir(m.COMUM + m.SO_WINDOWS + [m.PAINEL])
        m.conferir(m.COMUM + m.SO_MAC + [m.PAINEL])

    def test_o_codigo_e_o_mesmo_nos_dois_pacotes(self):
        """A lista COMUM é a prova de que não existe 'versão do Mac' do código.
        Se um destes migrar para SO_WINDOWS ou SO_MAC, os dois sistemas passam
        a divergir em silêncio."""
        m = self._mod()
        for arquivo in ("main_app.py", "plataforma.py", "tradovate_auto.py",
                        "motor/index.js", "versao.json"):
            self.assertIn(arquivo, m.COMUM, arquivo)
            self.assertNotIn(arquivo, m.SO_WINDOWS, arquivo)
            self.assertNotIn(arquivo, m.SO_MAC, arquivo)

    def test_a_suite_de_testes_vai_nos_dois_pacotes(self):
        m = self._mod()
        self.assertIn("tests/run.py", m.COMUM)

    def test_TODO_arquivo_de_teste_entra_no_pacote(self):
        """A lista do empacotador é escrita à mão, e mão esquece.

        Na 2.38.0 o `tests/test_burrice.py` nasceu com 19 testes — os quatro
        defeitos do log de 13 e 14/08 — e NÃO entrou na lista. Os zips teriam
        saído sem ele, calados: o cliente rodaria `tests/run.py` e veria 505
        testes passando, sem nenhum sinal de que 19 ficaram para trás.

        O teste antigo só perguntava pelo `run.py`, que é o corredor. Faltava
        perguntar pelos testes que ele corre. Agora é a pasta que manda: todo
        `tests/test_*.py` que existir no disco tem de estar na lista."""
        # ÚNICA EXCEÇÃO, E DECLARADA: este arquivo testa o `empacotar.py`, e o
        # `empacotar.py` não se inclui nos zips (é ferramenta de quem entrega,
        # não do cliente). Mandá-lo junto criaria um teste que falha na máquina
        # do cliente por falta do arquivo que ele testa — ruído no lugar de
        # sinal. Se alguém um dia passar a empacotar o `empacotar.py`, esta
        # linha sai e o arquivo entra.
        FORA_DE_PROPOSITO = {"tests/test_empacotamento.py"}
        import glob
        m = self._mod()
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertNotIn("empacotar.py", m.COMUM,
                         "o empacotador passou a ir junto — reveja a exceção")
        for caminho in sorted(glob.glob(os.path.join(raiz, "tests", "test_*.py"))):
            relativo = "tests/" + os.path.basename(caminho)
            if relativo in FORA_DE_PROPOSITO:
                continue
            self.assertIn(relativo, m.COMUM,
                          f"{relativo} existe mas não entra nos zips — o "
                          "cliente receberia a suíte incompleta sem saber")

    def test_nenhum_arquivo_esta_nas_duas_cascas(self):
        m = self._mod()
        repetidos = set(m.SO_WINDOWS) & set(m.SO_MAC)
        self.assertEqual(repetidos, set(),
                         f"arquivo em ambas as cascas: {repetidos}")

    def test_a_versao_vem_do_versao_json(self):
        """Nunca de um número digitado no script, que envelheceria em silêncio
        e batizaria o zip com a versão errada."""
        import json
        m = self._mod()
        with open(os.path.join(RAIZ, "versao.json"), encoding="utf-8") as f:
            self.assertEqual(m.versao(), json.load(f)["versao"])

    def test_o_painel_de_licencas_pode_ser_deixado_de_fora(self):
        """Ele carrega o token de administrador. Precisa existir um jeito de
        gerar o pacote sem ele antes de repassar a alguém."""
        m = self._mod()
        self.assertEqual(m.PAINEL, "painel_licencas.html")
        with open(os.path.join(RAIZ, "empacotar.py"), encoding="utf-8") as f:
            self.assertIn("--sem-painel", f.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestPainelDeLicencas(unittest.TestCase):
    """O painel é a chave do negócio, e o abridor dele tem duas regras.

    17/08: "gere o painel de licença para eu salvar junto com os arquivos,
    para ao clicar, abrir o chrome, e nas próximas atualizações me entregue
    tudo junto em um zip".

    O painel em si NÃO carrega segredo: a senha de administrador é digitada
    nele e fica no localStorage do navegador daquela máquina. O que ele
    carrega é PODER — com a senha, cria e revoga licença. Por isso ele vai no
    pacote DELE e nunca no do cliente."""

    def test_o_abridor_do_mac_usa_o_CHROME(self):
        """Antes usava `open` puro, que vai para o navegador padrão. O painel
        guarda servidor e senha por NAVEGADOR: abrir hoje no Safari e amanhã
        no Chrome faz o painel parecer que 'esqueceu tudo'."""
        with open(os.path.join(RAIZ, "ABRIR_PAINEL_LICENCAS.command"),
                  encoding="utf-8") as f:
            sh = f.read()
        self.assertIn('open -a "Google Chrome"', sh)
        self.assertIn("Google Chrome.app", sh, "não confere se o Chrome existe")

    def test_o_abridor_do_mac_nao_falha_calado_sem_chrome(self):
        """Máquina sem Chrome não pode ficar sem painel — mas o trader precisa
        saber que a memória vai ser outra."""
        with open(os.path.join(RAIZ, "ABRIR_PAINEL_LICENCAS.command"),
                  encoding="utf-8") as f:
            sh = f.read()
        self.assertIn("navegador padrão", sh)
        self.assertIn("else", sh)

    def test_o_WINDOWS_tambem_tem_abridor(self):
        """O painel ia no pacote do Windows e não tinha como abrir com dois
        cliques — ficava um HTML solto no meio dos arquivos."""
        self.assertTrue(_existe("ABRIR_PAINEL_LICENCAS.bat"))
        with open(os.path.join(RAIZ, "ABRIR_PAINEL_LICENCAS.bat"),
                  encoding="utf-8") as f:
            bat = f.read()
        self.assertIn("chrome.exe", bat)
        self.assertIn("navegador padrao", bat, "falha calado sem Chrome")


class TestOPainelNuncaVaiParaOCliente(unittest.TestCase):
    """A única regra desta entrega que não tem volta.

    Quem recebe o painel E a senha administra as licenças no lugar dele. O
    `--sem-painel` existe para isso, e precisa tirar o painel E os atalhos —
    um botão 'Abrir Painel de Licenças' num pacote de cliente avisa que existe
    um painel de licenças, o que já é informação demais."""

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "empacotar", os.path.join(RAIZ, "empacotar.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_sem_painel_tira_o_painel_E_os_dois_atalhos(self):
        m = self._mod()
        for sistema in ("windows", "mac"):
            especificos = m.SO_WINDOWS if sistema == "windows" else m.SO_MAC
            limpos = [a for a in especificos if "PAINEL_LICENCAS" not in a]
            arquivos = m.COMUM + limpos          # sem o PAINEL
            for a in arquivos:
                self.assertNotIn("painel_licencas", a.lower(),
                                 f"{sistema}: o painel ficou no pacote limpo")
                self.assertNotIn("PAINEL_LICENCAS", a,
                                 f"{sistema}: o atalho do painel ficou no "
                                 "pacote limpo — ele anuncia que o painel "
                                 "existe")

    def test_com_painel_os_dois_sistemas_levam_o_atalho(self):
        """O pacote dele tem de abrir com dois cliques nos dois sistemas."""
        m = self._mod()
        self.assertIn("ABRIR_PAINEL_LICENCAS.command", m.SO_MAC)
        self.assertIn("ABRIR_PAINEL_LICENCAS.bat", m.SO_WINDOWS)
        self.assertEqual(m.PAINEL, "painel_licencas.html")

    def test_o_painel_nao_carrega_senha_gravada(self):
        """Se a senha estivesse escrita no arquivo, o painel viraria segredo em
        si — e um zip esquecido numa pasta entregaria o negócio. Ela é digitada
        e fica no navegador."""
        with open(os.path.join(RAIZ, m_painel()), encoding="utf-8") as f:
            html = f.read()
        self.assertIn('type="password"', html,
                      "a senha deixou de ser um campo digitado")
        self.assertIn("localStorage", html)


def m_painel():
    return "painel_licencas.html"


class TestOZipUnicoDeEntrega(unittest.TestCase):
    """17/08: "nas próximas atualizações me entregue tudo junto em um zip".

    Não é só conforto. O pacote DELE e o do CLIENTE têm exatamente o MESMO
    NOME DE ARQUIVO — `SMC_QUANT_PRO_MAC_v2.42.1.zip` nos dois casos. Dois
    zips de mesmo nome em pastas diferentes do computador é a receita para
    enviar o errado uma vez, e enviar o painel de licenças a um cliente não
    tem volta. Aqui eles nascem dentro do mesmo zip, em SEU/ e CLIENTE/.
    """

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "empacotar", os.path.join(RAIZ, "empacotar.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_SEU_leva_o_painel_e_CLIENTE_nao(self):
        """CONSTRÓI o zip de verdade e abre os pacotes de dentro.

        Isto existe porque a primeira versão tinha um defeito que só a
        construção real pegaria: `montar()` grava sempre no MESMO nome, e o
        pacote do CLIENTE sobrescrevia o SEU antes de qualquer um ser lido.
        Os dois apontavam para o mesmo arquivo, e a pasta SEU/ saía com o
        conteúdo do cliente — silenciosamente, com o nome certo por cima."""
        import zipfile, io, shutil, tempfile
        m = self._mod()
        destino = os.path.join(RAIZ, f"SMC_QUANT_PRO_ENTREGA_v{m.versao()}.zip")
        ja_existia = os.path.exists(destino)
        reserva = None
        if ja_existia:
            reserva = tempfile.mktemp(suffix=".zip")
            shutil.copy2(destino, reserva)
        try:
            m.montar_entrega_unica(["mac"])
            with zipfile.ZipFile(destino) as z:
                nomes = z.namelist()
                self.assertIn("LEIA-PRIMEIRO.txt", nomes)
                seu = [n for n in nomes if n.startswith("SEU/")]
                cli = [n for n in nomes if n.startswith("CLIENTE/")]
                self.assertEqual(len(seu), 1, nomes)
                self.assertEqual(len(cli), 1, nomes)

                with zipfile.ZipFile(io.BytesIO(z.read(seu[0]))) as interno:
                    dentro = interno.namelist()
                self.assertTrue(
                    any("painel_licencas.html" in n for n in dentro),
                    "o pacote SEU saiu SEM o painel — provavelmente foi "
                    "sobrescrito pelo do cliente")
                self.assertTrue(
                    any("ABRIR_PAINEL_LICENCAS" in n for n in dentro),
                    "o pacote SEU saiu sem o atalho do painel")

                with zipfile.ZipFile(io.BytesIO(z.read(cli[0]))) as interno:
                    dentro = interno.namelist()
                for n in dentro:
                    self.assertNotIn("painel", n.lower(),
                                     "O PAINEL VAZOU PARA O PACOTE DO CLIENTE")
        finally:
            if os.path.exists(destino):
                os.remove(destino)
            if reserva:
                shutil.move(reserva, destino)

    def test_entrega_e_sem_painel_nao_combinam(self):
        """--entrega já traz as duas versões. Aceitar --sem-painel junto
        produziria um 'pacote de entrega' sem a metade que é dele."""
        m = self._mod()
        with self.assertRaises(SystemExit):
            m.main(["--entrega", "--sem-painel"])

    def test_o_leia_primeiro_diz_qual_e_qual_ANTES_de_tudo(self):
        m = self._mod()
        texto = m.LEIA_PRIMEIRO.format(v="0.0.0")
        self.assertIn("MESMO NOME", texto)
        self.assertIn("é o SEU", texto)
        self.assertIn("é o que você ENVIA", texto)
        self.assertIn("grep -i painel", texto,
                      "não ensina a conferência de cinco segundos")


class TestOSocorroDoMacVaiNoPacote(unittest.TestCase):
    """Estes testes vivem AQUI, e não no test_mac.py, por um motivo aprendido
    do jeito caro: eles consultam o `empacotar.py`, e o `empacotar.py` NÃO vai
    nos zips (é ferramenta de quem entrega). Postos no test_mac.py, a suíte
    passava aqui e QUEBRAVA na máquina do cliente com dois FileNotFoundError —
    o pacote entregava uma suíte que não roda, que é pior que não entregar
    suíte nenhuma. Foi o próprio 'rodar a suíte de dentro do pacote' que pegou.
    """

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "empacotar", os.path.join(RAIZ, "empacotar.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_o_desbloquear_VAI_no_pacote_do_mac(self):
        """Um arquivo de socorro que não é entregue não socorre ninguém."""
        m = self._mod()
        self.assertIn("DESBLOQUEAR_MAC.txt", m.SO_MAC)
        # e sai também no pacote do cliente — ele passa pelo mesmo bloqueio
        limpos = [a for a in m.SO_MAC if "PAINEL_LICENCAS" not in a]
        self.assertIn("DESBLOQUEAR_MAC.txt", limpos)

    def test_o_leia_primeiro_da_entrega_avisa_o_dono(self):
        """Ele precisa avisar o cliente ANTES de mandar o zip — é o momento
        em que mais gente desiste, e o mais fácil de resolver."""
        m = self._mod()
        texto = m.LEIA_PRIMEIRO.format(v="0.0.0")
        self.assertIn("GATEKEEPER", texto.upper())
        self.assertIn("DESBLOQUEAR_MAC.txt", texto)


class TestOGuiaDeRevendaTambemENaoVaiParaOCliente(unittest.TestCase):
    """Tirar o painel do zip do cliente não adianta se o pacote leva, ao lado,
    o passo a passo que diz "abra o painel_licencas.html na sua máquina e gere
    uma licença para ele".

    Conferido no zip de v2.43.1: o ENTREGA_AO_CLIENTE.md — o guia de REVENDA,
    escrito para ele — ia dentro do pacote do CLIENTE, junto com as seções do
    LEIA-ME que explicam o painel e a operação de licenças. A senha não vazava;
    o desenho do negócio, sim, inclusive a existência do painel, que é
    justamente o que o cliente não deveria saber."""

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "empacotar", os.path.join(RAIZ, "empacotar.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_o_guia_de_revenda_sai_do_pacote_do_cliente(self):
        m = self._mod()
        self.assertIn("ENTREGA_AO_CLIENTE.md", m.SO_SEU)
        self.assertIn("ENTREGA_AO_CLIENTE.md", m.COMUM,
                      "o guia continua indo no pacote DELE — é lá que serve")

    def test_o_trecho_marcado_some_no_do_cliente_e_fica_no_dele(self):
        m = self._mod()
        texto = ("linha de todos\n"
                 f"{m.MARCA_INICIO}\n"
                 "segredo do negocio\n"
                 f"{m.MARCA_FIM}\n"
                 "outra linha de todos\n")
        dele = m.texto_do_pacote(texto, com_painel=True)
        cliente = m.texto_do_pacote(texto, com_painel=False)
        self.assertIn("segredo do negocio", dele)
        self.assertNotIn("segredo do negocio", cliente)
        for saida in (dele, cliente):
            self.assertIn("linha de todos", saida)
            self.assertIn("outra linha de todos", saida)

    def test_as_MARCAS_nunca_aparecem_para_ninguem(self):
        """Marca é instrução para o empacotador. Se ela chega ao leitor, o
        arquivo fica com cara de rascunho — nos DOIS pacotes."""
        m = self._mod()
        texto = f"a\n{m.MARCA_INICIO}\nb\n{m.MARCA_FIM}\nc\n"
        for com in (True, False):
            saida = m.texto_do_pacote(texto, com_painel=com)
            self.assertNotIn("SO SEU", saida)
            self.assertNotIn("[[", saida)

    def test_texto_sem_marca_nenhuma_passa_intacto(self):
        """O filtro roda em TODO .txt e .md do pacote. Se ele mexesse num
        arquivo sem marca, estragaria o LEIA-ME inteiro em silêncio."""
        m = self._mod()
        for arq in ("DESBLOQUEAR_MAC.txt", "LEIA-ME_MAC.txt"):
            with open(os.path.join(RAIZ, arq), encoding="utf-8") as f:
                original = f.read()
            if m.MARCA_INICIO in original:
                continue
            self.assertEqual(m.texto_do_pacote(original, True), original, arq)
            self.assertEqual(m.texto_do_pacote(original, False), original, arq)

    def test_marca_aberta_e_nao_fechada_nao_engole_o_arquivo_inteiro(self):
        """Se eu esquecer de fechar a marca, o certo é perder o resto daquele
        trecho — nunca sobrar um LEIA-ME de duas linhas sem ninguém notar. Este
        teste existe para que a falha apareça aqui, e não no zip do cliente."""
        m = self._mod()
        for arq in ("LEIA-ME_MAC.txt", "LEIA-ME_WINDOWS.txt",
                    "DESBLOQUEAR_MAC.txt", "ENTREGA_AO_CLIENTE.md"):
            caminho = os.path.join(RAIZ, arq)
            if not os.path.exists(caminho):
                continue
            with open(caminho, encoding="utf-8") as f:
                texto = f.read()
            self.assertEqual(texto.count(m.MARCA_INICIO),
                             texto.count(m.MARCA_FIM),
                             f"{arq}: marca aberta sem fechar")
            cliente = m.texto_do_pacote(texto, com_painel=False)
            self.assertGreater(len(cliente), len(texto) * 0.5,
                               f"{arq}: o pacote do cliente perdeu mais da "
                               "metade do arquivo — marca sem fechamento?")

    def test_NENHUM_texto_do_cliente_fala_em_painel_de_licencas(self):
        """O teste que teria pego isto na v2.43.1, se existisse — e ele varre
        TODO texto que o cliente recebe, não só os que eu lembrei de olhar.

        Foi assim que apareceram os outros três: o DESBLOQUEAR_MAC.txt
        enumerava o ABRIR_PAINEL_LICENCAS.command no meio de uma lista, o
        COMPILAR.md ensinava o `--sem-painel`, e as notas do versao.json (que
        viajam dentro do zip) contavam a história inteira do conserto."""
        m = self._mod()
        proibidos = ("painel_licencas", "PAINEL_LICENCAS", "painel de licen",
                     "PAINEL DE LICEN", "ENTREGA_AO_CLIENTE", "sem-painel",
                     "token de administrador")
        for sistema in ("mac", "windows"):
            especificos = m.SO_MAC if sistema == "mac" else m.SO_WINDOWS
            especificos = [a for a in especificos if "PAINEL_LICENCAS" not in a]
            for rel in m.COMUM + especificos:
                if rel in m.SO_SEU or not rel.endswith((".txt", ".md", ".json")):
                    continue
                caminho = os.path.join(RAIZ, rel)
                if not os.path.exists(caminho):
                    continue
                with open(caminho, encoding="utf-8") as f:
                    cliente = m.texto_do_pacote(f.read(), com_painel=False)
                for termo in proibidos:
                    self.assertNotIn(
                        termo, cliente,
                        f"{rel} ({sistema}) entrega ao cliente a existência do "
                        f"painel de licenças, em '{termo}'")

    def test_as_notas_da_versao_nao_contam_o_negocio_dele(self):
        """O versao.json vai DENTRO do pacote, e as notas aparecem no aviso de
        atualização. Escrever ali "o painel de licenças carrega o seu token" é
        o mesmo vazamento por outra porta — e eu fiz isso ao documentar o
        conserto do vazamento. O que é dele se conta no ENTREGA_AO_CLIENTE.md,
        que fica em SEU/."""
        import json
        with open(os.path.join(RAIZ, "versao.json"), encoding="utf-8") as f:
            notas = json.load(f)["notas"].lower()
        # A PALAVRA "painel" SOZINHA NÃO É O PROBLEMA — e proibi-la foi meu
        # erro na v2.43.2. A Tradovate tem painel de ATMs, painel de posições
        # e painel de ordem, e as notas precisam poder falar deles. O que não
        # pode viajar no zip do cliente é o painel de LICENÇAS e a operação de
        # revenda em volta dele.
        for proibido in ("painel de licen", "painel_licencas", "revenda",
                         "admin_token", "token de administrador"):
            self.assertNotIn(proibido, notas,
                             f"as notas da versão mencionam '{proibido}' — "
                             "e elas viajam no pacote do cliente")


class TestOPacoteDoClienteNAOLevaFerramentaDeCompilacao(unittest.TestCase):
    """O CLIENTE ABRIU O INNO SETUP. Foto de 24/08.

    Ele recebeu o zip do Windows, abriu a pasta, não achou nada para dar dois
    cliques, foi vasculhar — e achou `instalador\\SMC_Quant_Pro.iss`. O Windows
    abriu no Inno Setup Compiler e ele ficou olhando para uma tela de
    programador. Perguntou: "era para ir desse jeito mesmo?".

    Não era. Aquela pasta é a ferramenta que gera o setup.exe. Três estragos
    de uma vez:

      1. NÃO TEM USO PARA O CLIENTE. É script de compilação.
      2. VAZAVA O CAMINHO DA MÁQUINA DELE. O .iss trazia
         "C:\\Users\\jovan\\Documents\\SMC_QUANT_PRO\\dist" cravado — o nome de
         usuário e o desenho das pastas dele, em todo pacote entregue.
      3. E QUEBRAVA. Quando o cliente tentou compilar, o erro foi
         "Line 85: No files found matching C:\\Users\\jovan\\...\\dist\\*",
         porque aquela pasta só existe na máquina dele.
    """

    def _mod(self):
        import importlib.util
        caminho = os.path.join(RAIZ, "empacotar.py")
        spec = importlib.util.spec_from_file_location("empacotar", caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_a_pasta_instalador_sai_do_pacote_do_CLIENTE(self):
        m = self._mod()
        for arquivo in m.SO_SEU:
            if arquivo.startswith("instalador/"):
                break
        else:
            self.fail("a pasta instalador/ voltou a ir no pacote do cliente")

    def test_o_iss_continua_indo_no_pacote_DELE(self):
        """Tirar do cliente não pode significar sumir: é com ele que ele gera
        o setup.exe."""
        m = self._mod()
        self.assertIn("instalador/SMC_Quant_Pro.iss", m.SO_WINDOWS)

    def test_o_iss_NAO_carrega_caminho_de_maquina_nenhuma(self):
        with open(os.path.join(RAIZ, "instalador", "SMC_Quant_Pro.iss"),
                  encoding="utf-8") as f:
            iss = f.read()
        # Só o CÓDIGO: os comentários citam o caminho antigo para explicar o
        # defeito, e punir a documentação seria o teste errado.
        codigo = "\n".join(l for l in iss.splitlines()
                           if not l.lstrip().startswith(";"))
        self.assertNotIn("C:\\Users\\", codigo,
                         "voltou a cravar o caminho de uma máquina no .iss")
        self.assertIn("SourcePath", codigo,
                      "o caminho tem de ser relativo à pasta do .iss")


class TestOWindowsTEMOndeClicar(unittest.TestCase):
    """A ASSIMETRIA QUE MANDOU O CLIENTE PARA O INNO SETUP.

    O pacote do Mac sempre teve seis arquivos de dois cliques. O do Windows
    tinha ZERO — só o do painel de licenças, que nem vai para o cliente. Quem
    abria o zip no Windows não tinha o que clicar, e ia procurar.
    """

    def _mod(self):
        import importlib.util
        caminho = os.path.join(RAIZ, "empacotar.py")
        spec = importlib.util.spec_from_file_location("empacotar", caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_existe_um_instalador_de_dois_cliques(self):
        self.assertTrue(_existe("INSTALAR_WINDOWS.bat"))
        self.assertIn("INSTALAR_WINDOWS.bat", self._mod().SO_WINDOWS)

    def test_existe_um_abridor_de_dois_cliques(self):
        self.assertTrue(_existe("ABRIR_SMC_QUANT_PRO.bat"))
        self.assertIn("ABRIR_SMC_QUANT_PRO.bat", self._mod().SO_WINDOWS)

    def test_cada_par_do_MAC_tem_o_par_do_WINDOWS(self):
        """Foi a assimetria que criou o problema. Cravada, ela não volta."""
        pares = [("INSTALAR_MAC.command", "INSTALAR_WINDOWS.bat"),
                 ("ABRIR_SMC_QUANT_PRO.command", "ABRIR_SMC_QUANT_PRO.bat")]
        for do_mac, do_win in pares:
            self.assertTrue(_existe(do_mac), do_mac)
            self.assertTrue(_existe(do_win),
                            f"'{do_mac}' existe e '{do_win}' não — o cliente "
                            "do Windows fica sem o que clicar")

    def test_o_instalador_tenta_o_py_launcher_ANTES_do_python(self):
        """No Windows o comando `python` pode cair na loja da Microsoft e
        abrir uma página em vez de rodar — beco sem saída que já fez gente
        achar que o Python não estava instalado quando estava."""
        with open(os.path.join(RAIZ, "INSTALAR_WINDOWS.bat"), encoding="utf-8") as f:
            bat = f.read()
        self.assertLess(bat.index("py -3"), bat.index("python --version"))

    def test_o_abridor_NAO_fecha_a_janela_engolindo_o_erro(self):
        """Sem o `pause` no caminho de erro, a janela some no instante da
        falha e leva a mensagem junto — o cliente vê um piscar e não tem o
        que relatar."""
        with open(os.path.join(RAIZ, "ABRIR_SMC_QUANT_PRO.bat"), encoding="utf-8") as f:
            bat = f.read()
        i = bat.index('if not "%SAIDA%"=="0"')
        self.assertIn("pause", bat[i:])


class TestAVersaoNAOSeEscreveMaisAMao(unittest.TestCase):
    """A MESMA DOENÇA DO main_app.py, QUE SOBREVIVEU NOS ARQUIVOS AO LADO.

        instalador/SMC_Quant_Pro.iss  ->  MyAppVersion "2.19.0"
        LEIA-ME_WINDOWS.txt           ->  "SMC QUANT PRO v2.37.0"
        versao.json                   ->  2.70.1

    Cinquenta e uma versões de defasagem numa, trinta e três na outra. O
    setup.exe sairia com o nome `SMC_Quant_Pro_Setup_2.19.0.exe` e apareceria
    como 2.19.0 em "Adicionar ou Remover Programas" — o cliente instalaria a
    versão mais nova achando que instalou uma de meses atrás.
    """

    def _mod(self):
        import importlib.util
        caminho = os.path.join(RAIZ, "empacotar.py")
        spec = importlib.util.spec_from_file_location("empacotar", caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_o_iss_recebe_a_versao_do_versao_json(self):
        m = self._mod()
        saida = m.carimbar_versao('#define MyAppVersion     "2.19.0"',
                                  "9.9.9", "x.iss")
        self.assertIn('"9.9.9"', saida)
        self.assertNotIn("2.19.0", saida)

    def test_o_cabecalho_do_LEIA_ME_recebe_a_versao(self):
        m = self._mod()
        saida = m.carimbar_versao("  SMC QUANT PRO v2.37.0 — WINDOWS\n",
                                  "9.9.9", "a.txt")
        self.assertIn("v9.9.9", saida)

    def test_o_CHANGELOG_do_LEIA_ME_e_PRESERVADO(self):
        """Mais abaixo os LEIA-ME trazem 'O QUE MUDOU NA v2.37.0', que é
        história e está certo. Trocar tudo apagaria o registro do que
        aconteceu em cada versão."""
        m = self._mod()
        texto = ("  SMC QUANT PRO v2.37.0 — WINDOWS\n" + ("\n" * 200)
                 + "  O QUE MUDOU NA v2.37.0\n")
        saida = m.carimbar_versao(texto, "9.9.9", "a.txt")
        self.assertIn("O QUE MUDOU NA v2.37.0", saida)

    def test_o_pacote_montado_LEVA_a_versao_certa(self):
        """Ponta a ponta, no repositório real."""
        m = self._mod()
        with open(os.path.join(RAIZ, "instalador", "SMC_Quant_Pro.iss"),
                  encoding="utf-8") as f:
            iss = f.read()
        saida = m.carimbar_versao(iss, m.versao(), "instalador/SMC_Quant_Pro.iss")
        self.assertIn(f'#define MyAppVersion     "{m.versao()}"', saida)
