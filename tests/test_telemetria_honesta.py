"""O CVD QUE O PROGRAMA INVENTAVA E ENTREGAVA À TIGER COMO FATO.

22/08, no chat, ela respondendo sobre por que não sugeria:

    3. **O delta não está confirmando a tendência**
       - O delta atual é **+1,380 (comprador forte)**, o que é positivo.

E antes, na telemetria: "CVD Delta: +1,420 (Comprador Forte)".

Nenhum dos dois números veio do mercado. Vinham daqui:

    self._cvd_acumulado = -1380.0 if "SELL" in direcao_sinal else 1420.0
    ...
    # Sincroniza a polaridade do Delta com o sinal consolidado do motor
    if "SELL" in direcao_sinal and self._cvd_acumulado > 0:
        self._cvd_acumulado = -abs(self._cvd_acumulado)
    ...
    if diff > 0: self._cvd_acumulado += 40.0

Uma semente fixa, o sinal TROCADO à força para concordar com a leitura da
IA, e um passo de ±40 conforme o preço subia ou descia. Sem volume, sem
agressão, sem bid/ask. Um delta que concorda com o sinal por construção não
confirma nada — é um espelho com nome técnico.

E ele não ficava na tela: `_mensagens_para_provedor` mandava a linha
"Telemetria de Fluxo e Delta" para a TIGER, que a recebe como FATO MEDIDO.
Foi assim que ela passou a raciocinar, com toda a lógica, em cima de um
número que o próprio programa tinha acabado de inventar — e o trader decidiu
em cima da resposta dela.

=====================================================================
POR QUE O ARQUIVO GUARDA A FAMÍLIA INTEIRA, E NÃO SÓ O CVD
=====================================================================
O CVD não estava sozinho. A mesma função — cuja docstring dizia "telemetria
viva e real do mercado" — preenchia TODO espaço vazio com um valor
plausível: score 82% aprovado sem análise nenhuma, três confluências que
ninguém identificou, "Claude 3.5 Sonnet" com outro provedor configurado,
"210ms (Rápida)" sem cronômetro, um trail fixo de 16 ticks enquanto a
plataforma recebia 19, 37 e 48, e um status de CDP que era VERDE nos dois
ramos do if — inclusive no ramo em que não havia conexão.

O padrão é um só: preferir um número bonito a um espaço vazio. Num programa
que manda ordem sozinho, essa preferência é o defeito mais caro que existe,
porque o painel é justamente onde o trader vai conferir se pode confiar.
"""

import re
import unittest

from harness import RAIZ, fonte_do_arquivo, pular_se_faltar

import os


def _so_codigo(texto):
    """Descarta comentários — pela mesma razão de `test_conta_orfa`."""
    return "\n".join(l for l in texto.splitlines()
                      if not l.lstrip().startswith("#"))


def _corpo_da_telemetria():
    """Só o que EXECUTA — comentários fora.

    A lição é de `test_conta_orfa`: a explicação do conserto cita o trecho
    antigo, e um teste que lesse comentários puniria justamente quem
    documentou o defeito.
    """
    fonte = fonte_do_arquivo()
    i = fonte.index("def _atualizar_telemetria_hud_embutido")
    bloco = fonte[i:fonte.index("r.desenhar()", i)]
    return "\n".join(l for l in bloco.splitlines()
                     if not l.lstrip().startswith("#"))


class TestOCVDNaoVoltaAserInventado(unittest.TestCase):

    def test_a_semente_fixa_sumiu(self):
        corpo = _corpo_da_telemetria()
        self.assertNotIn("_cvd_acumulado", corpo,
                         "o contador inventado voltou — e com ele o +1.420 "
                         "que a TIGER citou como fluxo medido")

    def test_o_delta_nao_troca_de_sinal_para_concordar_com_a_IA(self):
        """A parte mais perigosa do defeito antigo.

        Um delta que é forçado a concordar com o sinal transforma a
        confirmação em tautologia: o order flow 'confirma' porque foi obrigado
        a confirmar. É pior que não ter delta nenhum, porque parece uma
        segunda opinião.
        """
        corpo = _corpo_da_telemetria()
        for marca in ("abs(self._cvd_acumulado)", "Sincroniza a polaridade"):
            self.assertNotIn(marca, corpo)

    def test_o_delta_nao_e_derivado_so_do_preco(self):
        """Preço subiu não é agressão compradora. Sem tamanho de negócio não
        existe delta, e somar ±40 por vela é inventar com outro nome."""
        corpo = _corpo_da_telemetria()
        self.assertNotRegex(corpo, r"\+=\s*40\.0|\-=\s*40\.0")


class TestOFluxoQueVaiParaAIADizAVerdade(unittest.TestCase):

    def test_a_IA_recebe_a_mesma_frase_do_painel(self):
        """Painel e IA não podem discordar: se o painel diz que não há fluxo
        e a IA recebe 'Sincronizado', a contradição aparece no meio do
        pregão — que foi o defeito de 14:44 com o drawdown."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _mensagens_para_provedor")
        corpo = _so_codigo(fonte[i:i + 9000])
        self.assertIn("_texto_de_order_flow()", corpo)
        self.assertNotIn("CVD Delta: Sincronizado", corpo)

    def test_sem_ticks_a_resposta_e_que_nao_ha_fluxo(self):
        """A régua: só sai número se vier de negócio observado.

        E o "não tenho" vem COM MOTIVO. Depois que a fita passou a ser lida
        de verdade, "sem fluxo" deixou de ser um estado só: pode ser a
        conexão, a fita fechada no layout, ou a agressão que não dá para
        classificar. Cada um pede uma ação diferente do trader, e um travessão
        mudo mandaria ele caçar defeito no escuro."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _texto_de_order_flow")
        corpo = _so_codigo(fonte[i:i + 2600])
        self.assertIn("n_ticks", corpo,
                      "a decisão tem de sair dos negócios REGISTRADOS")
        self.assertIn("obter_cvd", corpo,
                      "quando houver ticks de verdade, o número tem de vir do "
                      "motor real (order_flow.py), não de um cálculo paralelo")
        for motivo in ("sem conexão", "fita Time & Sales fechada", "no chute"):
            self.assertIn(motivo, corpo,
                          f"o painel precisa saber dizer {motivo!r}")


class TestNenhumCampoDoPainelInventaValor(unittest.TestCase):
    """A varredura da família inteira, e não de um caso por vez."""

    PROIBIDOS = {
        r'"Score: 8\d%': "score aprovado sem análise nenhuma",
        r'else "OB Bullish': "confluências que ninguém identificou",
        r'"210ms': "latência que ninguém cronometrou",
        r'"Claude 3\.5 Sonnet"': "modelo que pode nem estar configurado",
        r'= "Auto Trail: 1\.5R': "trail fixo, contradizendo o que foi à plataforma",
        r'or "MESU6"': "instrumento inventado antes da primeira leitura",
    }

    def test_os_valores_de_vitrine_nao_voltam(self):
        corpo = _corpo_da_telemetria()
        voltaram = [motivo for pat, motivo in self.PROIBIDOS.items()
                    if re.search(pat, corpo)]
        self.assertEqual(voltaram, [],
                         "campo de painel voltou a inventar: " + "; ".join(voltaram))

    def test_a_luz_do_CDP_consegue_acender_vermelho(self):
        """Os dois ramos do if eram verdes, e o de baixo dizia 'Conectado'
        justamente quando NÃO havia conexão. Uma luz que não acende vermelho
        não é status — e esta fica no lugar onde se confere se a ordem tem
        por onde sair."""
        corpo = _corpo_da_telemetria()
        self.assertNotRegex(corpo, r'else\s*"🟢 CDP')
        self.assertIn("🔴", corpo)


class TestOPainelNaoNasceMentindo(unittest.TestCase):
    """Os padrões do próprio HUD, antes de qualquer atualização chegar.

    Abrir a aba já bastava para ver uma mesa inteira funcionando: MESU6 a
    7698,75, regime de alta, score 82%, CVD +1.420 comprador forte, CDP ao
    vivo. Nada disso tinha acontecido.
    """

    def setUp(self):
        pular_se_faltar("tiger_hud.py")

    def _padroes(self):
        fonte = fonte_do_arquivo(os.path.join(RAIZ, "tiger_hud.py"))
        i = fonte.index("self.ativo_smc")
        return fonte[i:i + 1800]

    def test_nao_nasce_com_preco_regime_e_score_prontos(self):
        p = self._padroes()
        for invento in ("MESU6 @ 7698.75", "Expansão Bullish (Alta)",
                        "Score: 82% (Aprovado)", "OB Bullish + BOS + SSL Sweep"):
            self.assertNotIn(invento, p, f"o HUD volta a abrir afirmando {invento!r}")

    def test_nao_nasce_com_CVD_de_1420(self):
        p = self._padroes()
        self.assertNotIn("+1,420", p)
        self.assertNotIn("1420.0", p,
                         "era a semente do delta inventado, e o número que a "
                         "TIGER repetiu ao trader como fluxo medido")

    def test_nao_nasce_com_log_de_ordem_que_nunca_foi_enviada(self):
        """A pior linha do painel antigo, e a que este teste encontrou depois
        de o resto já estar consertado:

            ("09:35", "ORDEM", "BUY MESU6 6 ctr @ 7690.0 enviada")

        Log é registro do que aconteceu. Um log de exemplo é registro do que
        NÃO aconteceu — e aqui é a diferença entre o trader achar que está
        posicionado e estar."""
        fonte = fonte_do_arquivo(os.path.join(RAIZ, "tiger_hud.py"))
        i = fonte.index("self.logs_recentes")
        trecho = _so_codigo(fonte[i:i + 400])
        self.assertNotIn("enviada", trecho)
        self.assertIn("self.logs_recentes = []", trecho)

    def test_nao_nasce_afirmando_conexao_com_a_corretora(self):
        p = self._padroes()
        self.assertNotIn("🟢 CDP Tradovate: Ao Vivo", p,
                         "afirmar CDP ao vivo antes de verificar é dizer que "
                         "há caminho para a ordem sair sem ter olhado")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestNenhumaChaveFantasmaNoPlano(unittest.TestCase):
    """O TETO DE US$ 0,00 QUE ELA ANUNCIOU EM TODA CONVERSA.

    22/08, 14:44:

        ✳ O ciclo foi reiniciado com Drawdown Registrado: US$ 0.00
          (teto configurado em US$ 0.00)
        ⚠️ Conferindo o que eu mesma escrevi contra o que está gravado, um
           número não bate: o drawdown máximo — eu disse US$ 0.00; o
           registrado é US$ 150.00

    A conferência de números salvou a resposta, mas ninguém foi atrás da
    causa, e ela não era o ponteiro órfão de conta (esse era outro caso, e já
    tinha sido consertado). Era isto, no contexto que a TIGER recebe:

        self.plano.get('drawdown_max', 0)

    A chave do plano é `drawdown_maximo`. `drawdown_max` nunca existiu — e o
    segundo argumento do `.get` engolia o erro em silêncio, entregando US$
    0,00 em toda conversa, de toda conta, desde sempre.

    É uma letra a menos, e o `.get` com padrão é justamente o que a torna
    invisível: sem ele haveria um KeyError no primeiro uso. Por isso o teste
    não guarda o nome consertado — varre TODAS as leituras do plano e exige
    que a chave exista.
    """

    def _chaves_do_plano_padrao(self):
        import ast
        arvore = ast.parse(fonte_do_arquivo())
        for no in arvore.body:
            if isinstance(no, ast.Assign) and any(
                    getattr(t, "id", None) == "PLANO_PADRAO" for t in no.targets):
                return {k.value for k in no.value.keys
                        if isinstance(k, ast.Constant)}
        self.fail("não achei o PLANO_PADRAO")

    # Chaves gravadas em tempo de execução, que legitimamente não nascem no
    # PLANO_PADRAO. Lista curta e nomeada de propósito: qualquer nome NOVO
    # fora dela estoura o teste, que é o ponto.
    DE_RUNTIME = {"ciclo_inicio", "fracao_max_do_restante"}

    def test_toda_chave_lida_do_plano_existe_de_verdade(self):
        fonte = fonte_do_arquivo()
        reais = self._chaves_do_plano_padrao() | self.DE_RUNTIME
        # `stats_plano.get(...)` é outro dicionário — não confundir.
        lidas = set(re.findall(
            r'(?<!stats_)(?:self\.)?plano\.get\(\s*["\']([a-z_]+)["\']', fonte))
        fantasmas = sorted(lidas - reais)
        self.assertEqual(
            fantasmas, [],
            "estas chaves são lidas do plano e não existem nele: "
            f"{fantasmas}. O `.get` devolve o padrão e o erro some — foi "
            "assim que 'drawdown_max' anunciou teto US$ 0,00 por semanas.")
