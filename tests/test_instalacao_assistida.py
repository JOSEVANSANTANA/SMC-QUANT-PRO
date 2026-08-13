"""O app instala — em vez de mandar o trader instalar.

"Baixe em ollama.com, escolha o instalador certo, instale, abra o Terminal e
rode `ollama pull qwen2.5:7b`, depois feche e abra o programa."

Esse roteiro o Josevan executa uma vez, com alguém por perto. O CLIENTE dele
não executa: erra o instalador, baixa o x86 num Apple Silicon, não abre
Terminal nenhum — e a conclusão vira "o programa não funciona".

Foi exatamente o que já aconteceu com o Node.js: o app dizia "Node.js não
encontrado" com o Node instalado e funcionando no Terminal, porque aberto pelo
Finder o PATH do macOS não traz /opt/homebrew/bin.

Aqui a instalação é do APP: ele descobre o instalador certo para ESTA máquina,
baixa mostrando progresso, instala, sobe o serviço, escolhe o modelo que CABE
na memória desta máquina, e testa com uma pergunta real antes de dizer pronto.
"""

import unittest

from harness import carregar, fonte_do_arquivo, RAIZ


def _plat():
    import os
    with open(os.path.join(RAIZ, "plataforma.py"), encoding="utf-8") as f:
        return f.read()


class TestModeloQueCabeNaMaquina(unittest.TestCase):
    """Um modelo que não cabe não é 'mais lento': ele estoura a memória e o
    sistema passa a usar disco como RAM, travando a máquina no pregão."""

    def _ns(self):
        return carregar(["MODELO_LOCAL_PADRAO", "MODELO_LOCAL_LEVE",
                         "_num_gb_de_ram", "_RAM_NAO_INFORMADA",
                         "modelo_local_recomendado"])

    def test_maquina_pequena_recebe_o_modelo_leve(self):
        ns = self._ns()
        modelo, motivo = ns["modelo_local_recomendado"](8)
        self.assertEqual(modelo, ns["MODELO_LOCAL_LEVE"])
        self.assertIn("8", motivo)

    def test_maquina_folgada_recebe_o_padrao(self):
        ns = self._ns()
        modelo, _m = ns["modelo_local_recomendado"](16)
        self.assertEqual(modelo, ns["MODELO_LOCAL_PADRAO"])

    def test_o_limite_e_9gb(self):
        """Mac de 8 GB é comum e precisa funcionar; o modelo padrão de ~4,7 GB
        brigaria por memória com o Chrome e a corretora abertos."""
        ns = self._ns()
        self.assertEqual(ns["modelo_local_recomendado"](8.9)[0],
                         ns["MODELO_LOCAL_LEVE"])
        self.assertEqual(ns["modelo_local_recomendado"](9.0)[0],
                         ns["MODELO_LOCAL_PADRAO"])

    def test_sem_conseguir_ler_a_memoria_ele_DIZ_isso(self):
        """Não saber é uma resposta legítima; fingir que mediu não é."""
        ns = self._ns()
        modelo, motivo = ns["modelo_local_recomendado"](None)
        self.assertEqual(modelo, ns["MODELO_LOCAL_PADRAO"])
        self.assertIn("não consegui ler", motivo)

    def test_a_leitura_de_ram_nunca_levanta(self):
        """Roda em três sistemas diferentes. Uma exceção aqui derrubaria a
        instalação inteira por causa de um número informativo."""
        ns = self._ns()
        v = ns["_num_gb_de_ram"]()
        self.assertTrue(v is None or v > 0)


class TestInstaladorCertoParaEstaMaquina(unittest.TestCase):

    def test_cada_sistema_tem_o_seu_instalador(self):
        """Baixar o x86 num Apple Silicon instala e funciona MAL — que é pior
        que não instalar, porque ninguém desconfia."""
        plat = _plat()
        self.assertIn("def url_do_instalador", plat)
        self.assertIn("Ollama-darwin.zip", plat)
        self.assertIn("OllamaSetup.exe", plat)
        self.assertIn("arm64", plat)

    def test_o_download_mostra_progresso(self):
        """1 GB baixando sem sinal de vida é indistinguível de um programa
        travado — e o trader fecha o app no meio."""
        plat = _plat()
        self.assertIn("def _baixar_arquivo", plat)
        self.assertIn("ao_progredir", plat)

    def test_arquivo_truncado_e_recusado(self):
        """Instalar meio download falha de um jeito muito mais confuso do que
        dizer 'o download veio incompleto'."""
        plat = _plat()
        i = plat.index("def _baixar_arquivo")
        self.assertIn("getsize", plat[i:i + 1400])

    def test_procura_o_programa_alem_do_PATH(self):
        """O defeito original do Node: aberto pelo Finder, o PATH do macOS não
        traz /opt/homebrew/bin, e o app dizia 'não encontrado' com o programa
        instalado e funcionando."""
        plat = _plat()
        self.assertIn("def onde_esta", plat)
        self.assertIn("/opt/homebrew/bin", plat)
        self.assertIn("LOCALAPPDATA", plat)

    def test_a_fronteira_de_sistema_e_respeitada(self):
        """Instalador, .pkg, msiexec e ditto são específicos de cada sistema —
        e a regra da casa é que isso mora só no plataforma.py."""
        fonte = fonte_do_arquivo()
        for especifico in ("msiexec", "OllamaSetup.exe", "ditto",
                           "Ollama-darwin.zip"):
            self.assertNotIn(especifico, fonte, especifico)


class TestOsPassosDaInstalacao(unittest.TestCase):

    def test_nao_reinstala_o_que_ja_funciona(self):
        """Baixar 5 GB de novo por não ter olhado antes seria desperdiçar o
        tempo e a franquia de internet do cliente."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _instalar_ia_worker")
        bloco = fonte[i:i + 900]
        self.assertIn("ia_local_no_ar", bloco)
        self.assertIn("Nada a fazer", bloco)

    def test_instalado_nao_e_o_mesmo_que_rodando(self):
        """Foi essa confusão que produziu o 'Motor no ar' sobre um processo já
        morto. Aqui, depois de subir o serviço, o app CONFERE a porta."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _instalar_ia_worker")
        bloco = fonte[i:i + 4000]
        self.assertIn("subir_servico_ia_local", bloco)
        self.assertIn("porta_responde(11434)", bloco)
        plat = _plat()
        j = plat.index("def subir_servico_ia_local")
        self.assertIn("quem confere se subiu é quem chamou", plat[j:j + 800])

    def test_o_servico_sozinho_nao_basta_o_modelo_tambem_vem(self):
        """Serviço no ar sem modelo sobe e não pensa."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _instalar_ia_worker")
        self.assertIn("baixar_modelo_ia_local", fonte[i:i + 4000])

    def test_termina_TESTANDO_com_pergunta_real(self):
        """Dizer 'instalado' sem testar seria repetir o erro da chave dobrada,
        que só apareceu como 401 no meio do pregão."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _instalar_ia_worker")
        bloco = fonte[i:i + 8000]
        self.assertIn("_pedir_openai", bloco)
        self.assertIn("Responda apenas: OK", bloco)
        # E se o teste não voltar, ela NÃO crava que está pronto.
        self.assertIn("prefiro te dizer isso a cravar", bloco)

    def test_cada_passo_aparece_no_registro(self):
        """Instalação silenciosa que falha calada é pior que instrução
        escrita: ninguém sabe onde parou."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _instalar_ia_worker")
        bloco = fonte[i:i + 8000]
        for marca in ("Baixando o instalador", "Instalando…",
                      "Subindo o serviço", "Baixando o modelo",
                      "Testando com uma pergunta real"):
            self.assertIn(marca, bloco, marca)

    def test_o_botao_nao_dispara_duas_instalacoes(self):
        """Dois downloads de 5 GB ao mesmo tempo corrompem um ao outro."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _instalar_ia_local")
        bloco = fonte[i:i + 900]
        self.assertIn("_instalando_ia", bloco)
        self.assertIn('state="disabled"', bloco)

    def test_o_botao_volta_ao_normal_mesmo_se_falhar(self):
        """Botão que fica travado em 'instalando…' para sempre depois de um
        erro obriga a reabrir o programa."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _instalar_ia_worker")
        bloco = fonte[i:i + 8000]
        self.assertIn("finally:", bloco)
        self.assertIn('state="normal"', bloco)

    def test_o_progresso_do_modelo_nao_inunda_o_registro(self):
        """O `pull` reescreve a linha de porcentagem centenas de vezes; sem
        filtro, o Registro fica ilegível e o trader para de ler o log."""
        plat = _plat()
        i = plat.index("def baixar_modelo_ia_local")
        self.assertIn("marca != ultimo", plat[i:i + 1800])


class TestOBotaoNaInterface(unittest.TestCase):

    def test_existe_botao_de_instalar_e_de_verificar(self):
        fonte = fonte_do_arquivo()
        self.assertIn("Instalar a IA LOCAL (sem chave)", fonte)
        self.assertIn("def _verificar_ia_local", fonte)

    def test_a_ia_local_nao_ganha_campo_de_chave(self):
        """Um campo de chave para quem não usa chave é confusão pura."""
        fonte = fonte_do_arquivo()
        i = fonte.index("self._campos_provedor = {}")
        self.assertIn('sem_chave', fonte[i:i + 400])

    def test_o_texto_diz_a_verdade_sobre_a_internet(self):
        """Prometer 'sem internet' e exigir 1 GB de download seria mentira na
        primeira tela que o cliente lê."""
        fonte = fonte_do_arquivo()
        i = fonte.index("IA LOCAL — roda na SUA máquina")
        bloco = fonte[i:i + 1200]
        self.assertIn("só NESTA vez", bloco)
        self.assertIn("GB de disco", bloco)

    def test_verificar_distingue_os_tres_estados(self):
        """'Não instalado', 'instalado mas parado' e 'no ar' pedem ações
        diferentes — juntar os três num 'não encontrado' foi o que fez o
        trader reinstalar o Node que já estava lá."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _verificar_ia_local")
        bloco = fonte[i:i + 1600]
        self.assertIn("IA LOCAL no ar", bloco)
        self.assertIn("está instalado", bloco)
        self.assertIn("ainda não instalada", bloco)


if __name__ == "__main__":
    unittest.main(verbosity=2)
