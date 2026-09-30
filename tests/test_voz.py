"""A BIBLIOTECA DE VOZES E A VELOCIDADE DA FALA.

Ele escreveu, em 14/08: "a biblioteca de voz não está ativa para selecionar
outras, não tem outras disponíveis, por favor ajuste isso e incorpore outras
vozes, também a velocidade da voz não está disponível para alterar".

Eram DOIS defeitos meus, de naturezas diferentes:

1. A LISTA. `vozes_disponiveis()` filtrava `idioma.startswith("pt")`. Num Mac
   recém-instalado existe UMA voz pt-BR — as boas são download separado do
   sistema. Então a "biblioteca" abria com um item só, que é indistinguível
   de um menu quebrado.

2. O CONTROLE DE VELOCIDADE. Ele existia, com o comando ligado e o valor
   certo, e era INVISÍVEL: o `.set()` estava encadeado na construção do
   widget, `.set()` devolve None, e o `.pack()` nunca acontecia. Um widget
   sem `pack` não é um widget escondido — é um widget que não está na tela.
   Nenhum teste pegava isso porque nenhum teste olhava se o widget aparecia.
"""

import os
import unittest

from harness import fonte_do_arquivo, RAIZ

import plataforma


# Saída real de `say -v ?` num Mac. Serve para testar o analisador sem Mac.
# Repare no que ela tem de traiçoeiro: nomes com espaço e parênteses, um
# idioma escrito com hífen, e uma única voz de português no meio de outras.
SAIDA_DE_UM_MAC = """\
Albert              en_US    # Hello! My name is Albert.
Alice               it_IT    # Ciao! Mi chiamo Alice.
Bad News            en_US    # The light you see at the end of the tunnel.
Daniel (English (UK))  en_GB # Hello! My name is Daniel.
Eddy (Português (Brasil))  pt_BR # Olá! Eu me chamo Eddy.
Luciana             pt-BR    # Olá! O meu nome é Luciana.
Joana               pt_PT    # Olá! Chamo-me Joana.
Yuna                ko_KR    # 안녕하세요. 제 이름은 Yuna입니다.
"""


class TestOAnalisadorDaListaDoSistema(unittest.TestCase):

    def test_le_todas_as_vozes(self):
        vozes = plataforma.analisar_lista_de_vozes(SAIDA_DE_UM_MAC)
        self.assertEqual(len(vozes), 8)

    def test_nome_com_espaco_e_parenteses_nao_e_cortado(self):
        """O analisador antigo fazia `linha.split()` e pegava a primeira
        palavra: 'Daniel (English (UK))' virava a voz 'Daniel', que NÃO existe
        — e o `say -v Daniel` falharia calado."""
        vozes = plataforma.analisar_lista_de_vozes(SAIDA_DE_UM_MAC)
        nomes = [n for n, _i, _e in vozes]
        self.assertIn("Daniel (English (UK))", nomes)
        self.assertIn("Bad News", nomes)

    def test_idioma_com_hifen_tambem_conta(self):
        """O macOS moderno às vezes escreve pt-BR. Aceitar só pt_BR
        descartaria uma voz existente — em silêncio."""
        vozes = plataforma.analisar_lista_de_vozes(SAIDA_DE_UM_MAC)
        luciana = [v for v in vozes if v[0] == "Luciana"]
        self.assertEqual(len(luciana), 1)
        self.assertEqual(luciana[0][1], "pt_BR", "o hífen não foi normalizado")

    def test_linha_lixo_nao_derruba_nem_entra(self):
        vozes = plataforma.analisar_lista_de_vozes(
            "isto não é uma voz\n\n   \nAlbert   en_US  # Oi.")
        self.assertEqual(len(vozes), 1)

    def test_entrada_vazia_ou_None_devolve_lista_vazia(self):
        self.assertEqual(plataforma.analisar_lista_de_vozes(""), [])
        self.assertEqual(plataforma.analisar_lista_de_vozes(None), [])


def _nativas(vozes):
    """Só as vozes do sistema — as neurais do Jarvis marcam o idioma com
    "(Neural)" justamente para dar para separar as duas famílias."""
    return [v for v in vozes if "(Neural)" not in v[1]]


def _idioma_de(vozes, nome):
    return next(i for n, i, _e in vozes if n == nome)


class TestABibliotecaTemMaisDeUmaOpcao(unittest.TestCase):
    """O defeito, dito como ele o viu: 'não tem outras disponíveis'."""

    def _todas(self, monkey=True):
        """Roda vozes_disponiveis() como se este Linux fosse um Mac."""
        original_mac, original_rodar = plataforma.E_MACOS, plataforma._rodar
        plataforma.E_MACOS = True
        plataforma._rodar = lambda *a, **k: (True, SAIDA_DE_UM_MAC)
        try:
            return (plataforma.vozes_disponiveis(),
                    plataforma.vozes_disponiveis(so_portugues=True),
                    plataforma.voz_portugues_macos())
        finally:
            plataforma.E_MACOS, plataforma._rodar = original_mac, original_rodar

    def test_a_lista_completa_traz_TODAS_e_nao_so_portugues(self):
        """A REGRA, NÃO A CONTAGEM.

        Isto exigia `len(todas) == 8`, e as vozes neurais do Jarvis entraram
        na frente da lista — o número mudou e o teste ficou vermelho sem que
        nada tivesse quebrado. Contagem cravada é régua, não regra: ela proíbe
        acrescentar voz, que é justamente o que ele pediu. O que se trava é
        que a lista completa é MAIOR que a de português e que as vozes nativas
        do sistema continuam todas lá."""
        todas, so_pt, _melhor = self._todas()
        self.assertGreater(len(todas), len(so_pt),
                           "a biblioteca voltou a mostrar só português")
        for nome, _i, _e in _nativas(so_pt):
            self.assertTrue(_idioma_de(so_pt, nome).lower().startswith("pt"),
                            f"{nome} entrou na lista de português")
        nomes = [n for n, _i, _e in todas]
        for esperada in ("Luciana", "Joana", "Daniel (English (UK))"):
            self.assertIn(esperada, nomes,
                          "sumiu uma voz nativa do sistema da lista completa")

    def test_portugues_vem_PRIMEIRO(self):
        """As outras estão na lista porque ele pediu a biblioteca inteira —
        mas só as de português pronunciam os números da mesa direito."""
        todas, _so_pt, _m = self._todas()
        idiomas = [i for _n, i, _e in todas]
        self.assertTrue(idiomas[0].startswith("pt"), idiomas[:3])
        primeiro_nao_pt = next(k for k, i in enumerate(idiomas)
                               if not i.startswith("pt"))
        self.assertEqual(primeiro_nao_pt, 3, "português não ficou no topo")

    def test_pt_BR_vem_antes_de_pt_PT(self):
        """Ele opera no Brasil; 'Joana' de Portugal lê os números com outra
        prosódia."""
        todas, _s, _m = self._todas()
        # Só as NATIVAS: as neurais do Jarvis vêm de propósito antes de todas,
        # e são todas pt_BR — misturá-las aqui mediria outra coisa.
        idiomas = [i for _n, i, _e in _nativas(todas) if i.startswith("pt")]
        self.assertEqual(idiomas, ["pt_BR", "pt_BR", "pt_PT"])

    def test_a_melhor_voz_sai_da_lista_real(self):
        """Ela pode mudar de nome; o que não pode é ser um nome que ninguém
        consegue usar. Antes isto cravava "Luciana"; hoje o padrão é a neural
        do Jarvis, e a regra que importa continua a mesma."""
        todas, _s, melhor = self._todas()
        self.assertTrue(melhor)
        self.assertIn(melhor, [n for n, _i, _e in todas],
                      "a voz padrão não está na biblioteca — escolher ela "
                      "deixaria a ferramenta muda")

    def test_fora_do_mac_sobram_as_neurais_e_nenhuma_do_sistema(self):
        """Isto exigia lista VAZIA fora do Mac, e estava certo enquanto todas
        as vozes vinham do `say`. As neurais do Jarvis são sintetizadas pela
        rede (edge-tts) e funcionam no Windows também — devolver vazio ali
        deixaria o cliente de Windows sem voz nenhuma. O que continua proibido
        é oferecer voz NATIVA do macOS fora do macOS: escolher uma delas seria
        escolher algo que não fala."""
        original = plataforma.E_MACOS
        plataforma.E_MACOS = False
        try:
            fora = plataforma.vozes_disponiveis()
            self.assertTrue(fora, "nenhuma voz sobrou fora do Mac")
            for nome, _i, _e in fora:
                self.assertIn("Jarvis", nome,
                              f"{nome} é voz nativa do macOS e foi oferecida "
                              "fora do macOS")
            self.assertTrue(plataforma.voz_portugues_macos())
        finally:
            plataforma.E_MACOS = original


class TestOControleDeVelocidadeAPARECE(unittest.TestCase):
    """'a velocidade da voz não está disponível para alterar'.

    Ele estava certo: o widget era construído e nunca empacotado."""

    def _bloco(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("VOZ: VELOCIDADE E QUAL VOZ")
        return fonte[i:i + 5000]

    def test_o_slider_e_EMPACOTADO(self):
        """Sem `.pack()` o widget não está na tela. Este é o teste que
        faltava: eu testava que o controle existia, não que ele aparecia."""
        bloco = self._bloco()
        self.assertIn("self.sld_vel_voz.pack(", bloco)

    def test_o_set_nao_volta_a_ser_encadeado_na_construcao(self):
        """`CTkSlider(...).set(v)` devolve None e engole o widget. Foi
        exatamente essa linha."""
        bloco = self._bloco()
        self.assertNotIn(").set(_vel)", bloco)

    def test_mover_o_slider_GRAVA_na_hora(self):
        """Configuração que só vale depois de reabrir o programa é
        configuração que o trader acha que não funcionou."""
        bloco = self._bloco()
        self.assertIn('salvar_config({"voz_rate"', bloco)

    def test_o_numero_vem_com_o_nome_do_ritmo(self):
        """'165' não significa nada para quem não é fonoaudiólogo."""
        bloco = self._bloco()
        for rotulo in ("devagar", "normal", "rápida"):
            self.assertIn(rotulo, bloco, rotulo)


class TestEscolherVozSemChutar(unittest.TestCase):

    def test_o_menu_mostra_o_IDIOMA_junto_do_nome(self):
        """'Daniel' sozinho não avisa que vai ler os números em inglês."""
        fonte = fonte_do_arquivo()
        self.assertIn('self._vozes_por_rotulo[f"{_n}  ·  {_i}"] = _n', fonte)

    def test_o_rotulo_vira_NOME_antes_de_ir_para_o_sistema(self):
        """`say -v "Luciana  ·  pt_BR"` não existe. A tradução mora num
        lugar só."""
        fonte = fonte_do_arquivo()
        self.assertIn("def _nome_da_voz_no_menu", fonte)
        i = fonte.index("def _trocar_voz")
        self.assertIn("self._nome_da_voz_no_menu()", fonte[i:i + 600])
        j = fonte.index("def _experimentar_voz")
        self.assertIn("self._nome_da_voz_no_menu()", fonte[j:j + 600])

    def test_existe_um_BOTAO_para_baixar_mais_vozes(self):
        """'Ajustes → Acessibilidade → Conteúdo Falado → Voz do sistema →
        Gerenciar vozes' é o mesmo roteiro de cinco passos que já falhou com
        o Node.js e com o Ollama."""
        fonte = fonte_do_arquivo()
        self.assertIn("def _abrir_ajustes_de_voz", fonte)
        self.assertIn("Baixar mais vozes", fonte)
        with open(os.path.join(RAIZ, "plataforma.py"), encoding="utf-8") as f:
            self.assertIn("def abrir_ajustes_de_voz", f.read())

    def test_a_fronteira_de_sistema_e_respeitada(self):
        """`open x-apple.systempreferences:` é do macOS e mora no
        plataforma.py — regra da casa desde a v2.12."""
        fonte = fonte_do_arquivo()
        self.assertNotIn("x-apple.systempreferences", fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
