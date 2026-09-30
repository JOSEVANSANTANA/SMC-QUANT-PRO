"""A aba Motor virou seções recolhíveis — e este arquivo vigia essa refatoração.

Não existe tkinter no ambiente onde a suíte roda, então NÃO dá para abrir a
janela e olhar. O que dá para verificar, e é exatamente onde esse tipo de
refatoração quebra, é a ESTRUTURA: um widget cujo pai (`sec_janelas`, por
exemplo) é criado DEPOIS dele explode com NameError na abertura do app — e o
app não abre. O pyflakes não pega isso, porque o nome existe na função.

Também trava o que não pode se perder: o botão LIGAR MOTOR fora de qualquer
seção recolhível, e as chaves de estado das seções sem colisão (duas seções
com a mesma chave abrem e fecham juntas).
"""

import ast
import unittest

from harness import ARQUIVO, carregar, fonte_do_arquivo


def _metodo(nome):
    arvore = ast.parse(fonte_do_arquivo(ARQUIVO))
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    raise AssertionError(f"método {nome} não existe mais em main_app.py")


class TestSecoesDaAbaMotor(unittest.TestCase):
    def test_todo_pai_de_secao_e_criado_antes_de_ser_usado(self):
        """O erro que derruba o app na abertura: usar `sec_log` na linha 100 e
        criá-lo na linha 140."""
        metodo = _metodo("_montar_tab_motor")
        criado_em = {}
        for no in ast.walk(metodo):
            if isinstance(no, ast.Assign):
                for alvo in no.targets:
                    if isinstance(alvo, ast.Name) and alvo.id.startswith("sec_"):
                        criado_em.setdefault(alvo.id, no.lineno)
                    if isinstance(alvo, ast.Attribute) and \
                            alvo.attr.startswith("sec_"):
                        criado_em.setdefault("self." + alvo.attr, no.lineno)
        self.assertTrue(criado_em, "nenhuma seção encontrada na aba Motor")

        for no in ast.walk(metodo):
            if isinstance(no, ast.Name) and no.id in criado_em \
                    and isinstance(no.ctx, ast.Load):
                self.assertGreaterEqual(
                    no.lineno, criado_em[no.id],
                    f"'{no.id}' é usado na linha {no.lineno} mas só é criado na "
                    f"linha {criado_em[no.id]} — o app não abriria.")

    def test_chaves_de_secao_nao_colidem(self):
        """Duas seções com a mesma chave compartilham o estado aberto/fechado:
        recolher uma recolheria a outra."""
        arvore = ast.parse(fonte_do_arquivo(ARQUIVO))
        chaves = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) \
                    and no.func.attr == "_secao" and len(no.args) >= 3:
                arg = no.args[2]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    chaves.append(arg.value)
        self.assertGreater(len(chaves), 5, "as seções sumiram")
        repetidas = {c for c in chaves if chaves.count(c) > 1}
        self.assertEqual(repetidas, set(), f"chaves repetidas: {repetidas}")

    def test_ligar_motor_fica_fora_de_secao_recolhivel(self):
        """A ação principal da aba não pode ficar escondida atrás de um bloco
        fechado. O pai dela tem de ser o frame rolável, não uma seção."""
        metodo = _metodo("_montar_tab_motor")
        pai = None
        for no in ast.walk(metodo):
            if not isinstance(no, ast.Assign):
                continue
            alvo = no.targets[0]
            if isinstance(alvo, ast.Attribute) and alvo.attr == "btn_ligar" \
                    and isinstance(no.value, ast.Call) and no.value.args:
                primeiro = no.value.args[0]
                pai = primeiro.id if isinstance(primeiro, ast.Name) else "?"
        self.assertEqual(pai, "master",
                         "o botão LIGAR MOTOR saiu do nível principal da aba e "
                         f"foi parar dentro de '{pai}' — se essa seção estiver "
                         "recolhida, o trader não acha o botão.")

    def test_o_qr_code_abre_a_secao_dele(self):
        """A seção do WhatsApp nasce recolhida. Um QR dentro de um bloco fechado
        é um QR que ninguém escaneia."""
        fonte = fonte_do_arquivo(ARQUIVO)
        i = fonte.index("def _mostrar_qr")
        corpo = fonte[i:i + 2000]
        self.assertIn("abrir_secao", corpo)
        self.assertIn("sec_whatsapp", corpo)

    def test_secao_expoe_abrir_e_alternar(self):
        fonte = fonte_do_arquivo(ARQUIVO)
        i = fonte.index("def _secao")
        corpo = fonte[i:i + 3000]
        self.assertIn("conteudo.abrir_secao = abrir", corpo)
        self.assertIn("conteudo.alternar_secao = alternar", corpo)


class TestTamanhoDaLetra(unittest.TestCase):
    def _ns(self, cfg=None):
        return carregar(["ESCALAS_LETRA", "ESCALA_LETRA_PADRAO",
                         "_FONTE_BASE_CHAT", "_FONTE_BASE_CONSOLE",
                         "escala_letra_salva", "nome_da_escala"],
                        stubs={"carregar_config": lambda: dict(cfg or {})})

    def test_escala_padrao_quando_nao_ha_nada_salvo(self):
        self.assertEqual(self._ns()["escala_letra_salva"](), 1.0)

    def test_le_a_escala_salva(self):
        self.assertEqual(
            self._ns({"escala_letra": 1.3})["escala_letra_salva"](), 1.3)

    def test_valor_absurdo_nao_inutiliza_a_janela(self):
        """Config editado à mão / arquivo corrompido. Uma escala de 40× deixaria
        um botão maior que a tela, sem como voltar atrás pela interface."""
        ns = self._ns({"escala_letra": 40})
        self.assertEqual(ns["escala_letra_salva"](), 2.0)
        ns2 = self._ns({"escala_letra": 0.01})
        self.assertEqual(ns2["escala_letra_salva"](), 1.0)
        ns3 = self._ns({"escala_letra": "grande"})
        self.assertEqual(ns3["escala_letra_salva"](), 1.0)

    def test_nome_da_escala_nunca_chuta(self):
        ns = self._ns()
        self.assertEqual(ns["nome_da_escala"](1.00), "Normal")
        self.assertEqual(ns["nome_da_escala"](1.50), "Máximo")
        # Valor entre dois degraus devolve o mais próximo, não um nome inventado.
        self.assertIn(ns["nome_da_escala"](1.22), ns["ESCALAS_LETRA"])

    def test_os_degraus_estao_em_ordem_crescente(self):
        valores = list(self._ns()["ESCALAS_LETRA"].values())
        self.assertEqual(valores, sorted(valores))
        self.assertEqual(valores[0], 1.0, "o primeiro degrau é o tamanho normal")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestAbaDeConfiguracoes(unittest.TestCase):
    """'o que for possível e considerado configuração, por favor organize em
    uma opção chamada Configurações, tem muita coisa que está solta e
    aleatória, isso não é legal' — 14/08.

    Ele tinha razão. A aba Motor acumulou NOVE seções, e a chave da API (que
    se põe uma vez na vida) dividia espaço com o Registro de atividade, que
    se olha a cada cinco minutos no meio do pregão.

    O corte é por QUANDO se mexe: MOTOR é o que se opera com o mercado
    aberto; CONFIGURAÇÕES é o que se ajusta uma vez e se esquece."""

    def test_a_aba_existe(self):
        fonte = fonte_do_arquivo()
        self.assertIn('self.tabview.add("🎛️ Configurações")', fonte)
        self.assertIn('tab_cfg = self.tabview.tab("🎛️ Configurações")', fonte)

    def test_o_que_se_OPERA_fica_no_motor(self):
        """Janela do gráfico, WhatsApp e Registro são usados COM o mercado
        aberto. Enterrá-los numa aba de configurações seria trocar um
        problema por outro."""
        fonte = fonte_do_arquivo()
        for secao in ("🪟  JANELAS DO GRÁFICO E PLATAFORMA",
                      "📋  REGISTRO DE ATIVIDADE (log do motor)"):
            i = fonte.index(secao)
            trecho = fonte[max(0, i - 200):i]
            self.assertIn("self._secao(master,", trecho, secao)

    def test_o_que_se_AJUSTA_UMA_VEZ_vai_para_configuracoes(self):
        fonte = fonte_do_arquivo()
        for secao in ("⚙️  INSTALAÇÃO E CHAVE DA API",
                      "🔠  TAMANHO DA LETRA (todas as abas)",
                      "🔊  VOZ DA TIGER",
                      "⏰  PREGÃO E INTERVALO DE ANÁLISE",
                      "🔔  ALERTAS NA TELA DO COMPUTADOR",
                      "🤖  AUTOMAÇÃO TRADOVATE (envio de ordem)",
                      "🛠️  MODO DESENVOLVEDOR"):
            i = fonte.index(secao)
            trecho = fonte[max(0, i - 200):i]
            self.assertIn("self._secao(cfg,", trecho, secao)

    def test_nenhuma_secao_foi_PERDIDA_no_caminho(self):
        """Mover é mover. Uma seção que some da aba antiga e não aparece na
        nova vira um recurso que existe no código e não na tela — que foi
        exatamente o que aconteceu com o slider da velocidade da fala."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _montar_tab_motor")
        corpo = fonte[i:fonte.index("def _montar_tab_plano")]
        self.assertEqual(corpo.count("self._secao(master,")
                         + corpo.count("self._secao(cfg,"), 9)

    def test_sem_a_aba_nova_nada_se_perde(self):
        """Se `master_cfg` não vier, tudo volta a morar numa aba só. Feio, e
        muito melhor que estourar na abertura do programa."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _montar_tab_motor")
        bloco = fonte[i:i + 3000]
        self.assertIn("master_cfg=None", bloco)
        self.assertIn("else:\n            cfg = master", bloco)

    def test_a_aba_explica_o_criterio_da_divisao(self):
        """Divisão sem critério escrito é outra forma de 'solto e aleatório':
        na próxima vez ninguém sabe de que lado a coisa nova entra."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _montar_tab_motor")
        self.assertIn("se AJUSTA uma vez e\n        se esquece", fonte[i:i + 3000])
