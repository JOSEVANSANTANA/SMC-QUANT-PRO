"""CANCELAR NA PLATAFORMA — e a fronteira entre "cancelei" e "não sei".

19/08, ele: "se estou deixando automacao ligada é porque precisa ter total
autonomia, entao, inclua opcao de cancelar as ordens caso o cenario mude para
posicionar uma nova... se a automacao estiver ligada é porque nao é para eu
lancar ordens manuais". E indicou o botão: "ali no topo, dentro da plataforma
tem a opcao sair em MKT &, essa opcao zera a posicao atual e cancela todas as
ordens".

A objeção que segurava o cancelamento automático até aqui era uma só — "lá
pode haver ordem que VOCÊ lançou na mão, e cancelar a errada é pior que não
cancelar nenhuma". Com a automação ligada, essa ordem não existe. A objeção
cai, e o cancelamento passa a ser o comportamento certo.

O QUE NÃO CAI é o resto, e é disso que este arquivo trata. O botão que ele
indicou faz DUAS coisas num clique: cancela as ordens E zera a posição a
mercado. Cancelar ordem à toa custa uma oportunidade; liquidar posição à toa
custa dinheiro na hora. Então a autorização exige LEITURA confirmando posição
zerada — nunca suposição. Não conseguir ler não é "está zerado": é a mesma
família de erro que ele já cobrou uma vez, a de afirmar o que não se sabe.

E o prazo, do segundo pedido dele: "no painel do diario de trading tem o prazo
para acatar, deixe esse mesmo prazo configurado para o prazo de execultar...
mas, tenha certeza que nao tenha execultado mesmo antes de cancelar".
"""

import os
import unittest

from harness import RAIZ, carregar, fonte_do_arquivo


class TestQuandoEuPossoCancelarNaPlataforma(unittest.TestCase):

    def _ns(self):
        return carregar(["decidir_cancelamento_na_corretora"])

    def _decidir(self, **kw):
        base = dict(autonomo=True, modo_teste=False, permitido=True,
                    pendentes_na_corretora=[{"ativo": "MESU6"}],
                    leitura_de_posicao_ok=True, posicao_aberta=False)
        base.update(kw)
        ns = self._ns()
        return ns["decidir_cancelamento_na_corretora"](**base)

    def test_automacao_ligada_e_posicao_zerada_CANCELA(self):
        """O caso que ele pediu: cenário morreu, ordem não pegou, some daqui
        e some de lá."""
        decisao, motivo = self._decidir()
        self.assertEqual(decisao, "CANCELA")
        self.assertIn("zerada", motivo)

    def test_sem_ordem_viva_nao_ha_o_que_fazer(self):
        decisao, _ = self._decidir(pendentes_na_corretora=[])
        self.assertEqual(decisao, "NADA")

    def test_automacao_desligada_volta_a_so_AVISAR(self):
        """Com a automação desligada, quem manda ordem para a corretora é ele.
        A ordem que está lá pode ser dele, e a regra antiga vale inteira."""
        decisao, motivo = self._decidir(autonomo=False)
        self.assertEqual(decisao, "AVISA")
        self.assertIn("desligada", motivo)

    def test_modo_teste_nao_encosta_na_plataforma_NEM_PARA_CANCELAR(self):
        """Modo teste não envia. Também não cancela — senão 'teste' passaria a
        significar duas coisas diferentes conforme o dia."""
        decisao, motivo = self._decidir(modo_teste=True)
        self.assertEqual(decisao, "AVISA")
        self.assertIn("TESTE", motivo)

    def test_caixinha_desmarcada_e_respeitada(self):
        decisao, _ = self._decidir(permitido=False)
        self.assertEqual(decisao, "AVISA")

    def test_NAO_CONSEGUIR_LER_A_POSICAO_nao_e_posicao_zerada(self):
        """O núcleo desta trava. O botão liquida a mercado: apertar sem saber
        se há posição é aposta, e aposta com o dinheiro dele."""
        decisao, motivo = self._decidir(leitura_de_posicao_ok=False)
        self.assertEqual(decisao, "AVISA")
        self.assertIn("LER", motivo)

    def test_com_posicao_aberta_quem_manda_e_o_stop(self):
        """Se há posição, a ordem executou — e posição executada se administra
        por stop e alvo, nunca por mudança de leitura minha. É a mesma regra
        que já governava o diário."""
        decisao, motivo = self._decidir(posicao_aberta=True)
        self.assertEqual(decisao, "AVISA")
        self.assertIn("stop", motivo)

    def test_com_posicao_aberta_e_inversao_autorizada_CANCELA(self):
        """Quando o trader autoriza a virada de mão (Stop & Reverse), o robô
        pode zerar a posição a mercado e cancelar ordens na corretora."""
        decisao, motivo = self._decidir(posicao_aberta=True, permitir_liquidar_posicao=True)
        self.assertEqual(decisao, "CANCELA")
        self.assertIn("virada de cenário", motivo)


class TestPrazoDeExecucao(unittest.TestCase):
    """O MESMO prazo do acatar, aplicado à ordem que ficou esperando preço."""

    def _ns(self):
        return carregar(["avaliar_prazo_de_execucao"])

    def test_dentro_do_prazo_nao_mexe(self):
        ns = self._ns()
        estourou, _ = ns["avaliar_prazo_de_execucao"](1000.0, 1000.0 + 300, 10)
        self.assertFalse(estourou)

    def test_passou_do_prazo_manda_cancelar(self):
        ns = self._ns()
        estourou, motivo = ns["avaliar_prazo_de_execucao"](
            1000.0, 1000.0 + 11 * 60, 10)
        self.assertTrue(estourou)
        self.assertIn("10 min", motivo)

    def test_o_prazo_vem_do_PLANO_e_nao_de_um_numero_fixo(self):
        """É o campo 'Prazo p/ acatar (min)' do Plano de Trading — o mesmo
        número, não um segundo campo que ele teria de lembrar de ajustar."""
        ns = self._ns()
        estourou, _ = ns["avaliar_prazo_de_execucao"](0.0, 25 * 60, 30)
        self.assertFalse(estourou, "com prazo de 30 min, 25 min ainda está dentro")
        estourou, _ = ns["avaliar_prazo_de_execucao"](0.0, 31 * 60, 30)
        self.assertTrue(estourou)

    def test_SE_O_PRECO_TOCOU_A_ENTRADA_eu_NAO_cancelo(self):
        """A ressalva dele: 'tenha certeza que nao tenha execultado mesmo antes
        de cancelar'. Se em algum ciclo eu anunciei que o preço mitigou a
        entrada, essa ordem PODE ter preenchido — e prazo nenhum me autoriza a
        cancelar por cima de uma execução possível."""
        ns = self._ns()
        estourou, motivo = ns["avaliar_prazo_de_execucao"](
            0.0, 999 * 60, 10, entrada_vista_no_preco=True)
        self.assertFalse(estourou)
        self.assertIn("pode ter executado", motivo)

    def test_sem_hora_de_criacao_nao_inventa(self):
        ns = self._ns()
        estourou, motivo = ns["avaliar_prazo_de_execucao"](None, 1000.0, 10)
        self.assertFalse(estourou)
        self.assertIn("não sei", motivo)


class TestOBotaoSairEmMercado(unittest.TestCase):
    """O que o robô faz na tela da Tradovate, lido do próprio código."""

    def _fonte(self):
        return fonte_do_arquivo(os.path.join(RAIZ, "tradovate_auto.py"))

    def test_existe_o_metodo_e_ele_exige_posicao_zerada_por_padrao(self):
        fonte = self._fonte()
        self.assertIn("def sair_em_mercado_e_cancelar(", fonte)
        i = fonte.index("def sair_em_mercado_e_cancelar(")
        assinatura = fonte[i:i + 200]
        self.assertIn("exigir_zerado=True", assinatura,
                      "o padrão tem de ser o seguro: sem posição, sem clique")

    def test_a_leitura_da_posicao_vem_ANTES_do_clique(self):
        """Ordem importa: conferir depois de liquidar não conserta nada."""
        fonte = self._fonte()
        i = fonte.index("def sair_em_mercado_e_cancelar(")
        corpo = fonte[i:i + 9000]
        i_le = corpo.index("self.ler_estado()")
        i_clica = corpo.index("self.clicar_pagina(")
        self.assertLess(i_le, i_clica)

    def test_conta_as_ordens_ANTES_e_DEPOIS(self):
        """É a conferência que transforma 'cliquei' em 'cancelei'. Sem ela eu
        estaria trocando uma frase que não posso provar por outra pior, porque
        a segunda desliga a atenção dele."""
        fonte = self._fonte()
        i = fonte.index("def sair_em_mercado_e_cancelar(")
        corpo = fonte[i:i + 9000]
        self.assertGreaterEqual(corpo.count("contar_ordens_vivas()"), 2)
        self.assertIn("vivas_antes", corpo)
        self.assertIn("vivas_depois", corpo)

    def test_ordens_ainda_vivas_depois_do_clique_NAO_e_sucesso(self):
        fonte = self._fonte()
        i = fonte.index("def sair_em_mercado_e_cancelar(")
        corpo = fonte[i:i + 9000]
        i_falha = corpo.index('if depois.get("vivas"):')
        i_ok = corpo.index('r["ok"] = True', i_falha)
        self.assertLess(i_falha, i_ok,
                        "o ramo de sucesso só pode vir depois de descartar o "
                        "caso em que as ordens continuam lá")

    def test_nao_saber_reler_vira_INCERTO_e_nao_sucesso(self):
        fonte = self._fonte()
        i = fonte.index("def sair_em_mercado_e_cancelar(")
        corpo = fonte[i:i + 9000]
        self.assertIn('r["incerto"] = True', corpo)
        self.assertIn("CONFIRA A PLATAFORMA", corpo)

    def test_nao_clica_se_a_legenda_do_botao_nao_fala_em_cancelar(self):
        """O seletor ao lado troca a ação do botão. 'Sair em Mkt' sem o
        '& Cancelar' zeraria a posição e deixaria as ordens — o contrário do
        que se pediu. Sem confirmar a legenda, não clico."""
        fonte = self._fonte()
        i = fonte.index("def sair_em_mercado_e_cancelar(")
        corpo = fonte[i:i + 9000]
        self.assertIn('if not btn.get("cancela_ordens"):', corpo)

    def test_contar_ordens_distingue_ZERO_de_NAO_SEI(self):
        """Painel fechado e conta limpa são idênticos na tela. Tratar os dois
        como 'zero ordens' faria o robô dizer que cancelou o que nunca viu."""
        fonte = self._fonte()
        i = fonte.index("_JS_ORDENS_VIVAS")
        corpo = fonte[i:i + 4000]
        self.assertIn("viuPainel", corpo)
        self.assertIn("ok:false", corpo)


class TestNenhumaOrdemSOMEEMSILENCIO(unittest.TestCase):
    """Os três caminhos que tiram uma pendente do diário têm de falar.

    Até aqui só o de 'cenário mudou' avisava. Stop rompido antes da entrada e
    cenário expirado cancelavam no diário e ficavam MUDOS — dois buracos por
    onde uma ordem viva na corretora sumia da conversa."""

    def test_os_tres_ramos_chamam_o_resolvedor(self):
        fonte = fonte_do_arquivo()
        self.assertGreaterEqual(
            fonte.count("self._resolver_ordens_orfas_na_corretora("), 4,
            "cenário mudou, stop rompido, cenário expirado e prazo de execução")

    def test_o_resolvedor_ou_cancela_ou_avisa_mas_nunca_cala(self):
        fonte = fonte_do_arquivo()
        i = fonte.index("def _resolver_ordens_orfas_na_corretora")
        corpo = fonte[i:i + 3000]
        self.assertIn('if decisao == "AVISA":', corpo)
        self.assertIn("CANCELE ESSA ORDEM NA PLATAFORMA", corpo)
        self.assertIn("_tv_cancelar_na_plataforma", corpo)

    def test_o_anuncio_do_cancelamento_vem_DEPOIS_do_resultado(self):
        """Mesma lição do envio: 'nao pode falar que fez e nao ter feito'. A
        frase antes do clique fala no gerúndio e promete a confirmação; a
        segunda diz o que aconteceu de verdade."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def _tv_cancelar_na_plataforma")
        corpo = fonte[i:i + 3000]
        self.assertIn("❌ NÃO CANCELEI", corpo)
        self.assertIn("✅ ORDENS CANCELADAS NA PLATAFORMA", corpo)
        self.assertIn("CONTINUAM VIVAS", corpo)

    def test_o_prazo_de_execucao_e_varrido_a_cada_ciclo(self):
        fonte = fonte_do_arquivo()
        self.assertIn("self._varrer_prazo_de_execucao()", fonte)
        i = fonte.index("def _varrer_prazo_de_execucao")
        corpo = fonte[i:i + 2500]
        self.assertIn("timeout_acatar_min", corpo,
                      "é o MESMO prazo do acatar, não um segundo campo")
        self.assertIn("enviada_plataforma", corpo,
                      "só o que está na corretora tem o que cancelar lá")
        self.assertIn("entrada_vista_no_preco", corpo,
                      "a trava do 'tenha certeza que não executou'")


if __name__ == "__main__":
    unittest.main()


class TestAVoltaAoFormularioDe20_08(unittest.TestCase):
    """A seta ← estava na tela e o robô não a achou. A ordem não saiu.

    20/08, 00:15, no log dele:
        "🤖 Vou executar sozinha: BUY MESU6 — entrada 7771.0, stop 7764.0..."
        "❌ NÃO ENVIEI ...: formulário do ticket não está à vista."
    e a observação: "NOTE QUE NAO FOI ENVIADO JUSTAMENTE PORQUE NAO CONSEGUIU
    VOLTAR ALI NO CHAMADO DO PEDIDO".

    A CAUSA. A busca da seta era feita dentro da subárvore de um ancestral do
    comprovante, alcançado SUBINDO cinco níveis a partir do menor bloco que
    contivesse "Funcionando/Filled/...". Naquele comprovante os brackets
    traziam os próprios estados ("- Filled", "- Cancelado"), então o menor
    bloco marcado virou uma LINHA DE BRACKET, vários níveis mais fundo do que
    a tabela de eventos de antes. Cinco níveis não chegavam mais ao painel, e
    `querySelectorAll` só enxerga descendentes: a seta, que fica ACIMA na
    linha do título, não era descendente de nada disso.

    A LIÇÃO. Contar níveis de aninhamento de um app React é apostar numa coisa
    que muda sozinha — e foi a segunda vez que essa aposta custou uma ordem. A
    âncora passou a ser a POSIÇÃO NA TELA, que é o que um humano usa."""

    def _fonte(self):
        return fonte_do_arquivo(os.path.join(RAIZ, "tradovate_auto.py"))

    def _corpo(self):
        fonte = self._fonte()
        i = fonte.index("def voltar_ticket(")
        return fonte[i:i + 9000]

    def test_a_busca_NAO_sobe_a_arvore_do_DOM(self):
        """Se voltar a contar parentesco, volta a quebrar quando a Tradovate
        mexer no aninhamento — que ela mexe sem avisar."""
        corpo = self._corpo()
        self.assertNotIn("parentElement", corpo,
                         "a âncora tem de ser geométrica, não de parentesco")

    def test_o_escopo_da_busca_e_o_documento_inteiro(self):
        """Preso a uma subárvore, o que está ACIMA dela é invisível — e a seta
        está sempre acima do corpo do comprovante."""
        corpo = self._corpo()
        self.assertIn("var escopo = document;", corpo)

    def test_a_faixa_cobre_ACIMA_do_comprovante(self):
        """A seta fica na linha do título, acima do recibo. Uma faixa que só
        olhasse para baixo do núcleo nunca a alcançaria."""
        corpo = self._corpo()
        i = corpo.index("var faixa=null;")
        trecho = corpo[i:i + 700]
        self.assertIn("rn.y - 220", trecho,
                      "a faixa precisa subir acima do topo do comprovante")

    def test_desempate_prefere_o_icone_MAIS_A_ESQUERDA(self):
        """Na linha do título pode haver mais de um ícone. A seta de voltar é
        a primeira, encostada na margem; só o tamanho não separava."""
        corpo = self._corpo()
        self.assertIn("mx*4", corpo)

    def test_a_falha_diz_QUANTOS_icones_foram_avaliados(self):
        """'não achei o botão de voltar' não permite investigar nada. Com o
        número de candidatos dá para separar 'não vi ícone nenhum' de 'vi e
        barrei todos por segurança'."""
        fonte = self._fonte()
        i = fonte.index("não achei o botão de voltar")
        self.assertIn("candidatos", fonte[i - 400:i + 400])

    def test_as_travas_de_seguranca_continuam_de_pe(self):
        """Alargar a busca não pode reabrir o clique que fechou o módulo dele
        no pregão de 06/08. A barreira vale para o ícone E para o botão em
        volta dele."""
        corpo = self._corpo()
        self.assertIn("PROIBIDO", corpo)
        self.assertIn("chamado do pedido|order ticket", corpo)
        self.assertIn("if(alvo2 && !seguro(alvo2)) continue;", corpo)

    def test_a_rota_por_atributo_tambem_olha_a_CLASSE(self):
        """Ícone de app React costuma se declarar pela classe e não ter
        aria-label nenhum. Era uma rota inteira de recuperação ficando de fora
        por não olhar o atributo mais óbvio."""
        fonte = self._fonte()
        i = fonte.index("def _voltar_por_atributo")
        corpo = fonte[i:i + 2000]
        self.assertIn("[class]", corpo, "o seletor tem de alcançar quem só tem classe")
        self.assertIn("baseVal", corpo, "em <svg> o className é objeto, não string")


class TestASegundaRotaDeCancelamento(unittest.TestCase):
    """20/08, 12:26: cliquei em 'Sair em Mkt & Cxl' e as TRÊS ordens
    continuaram vivas. Relatei isso corretamente — mas parei ali.

    E o botão que resolveria estava no MEU PRÓPRIO diagnóstico, impresso a
    cada ciclo, na lista de textos com "posi" na tela dele:

        · 'Sair de todas as posições Cancelar todas'

    Existia um segundo botão, explícito, visível, e eu nunca tentei. Desistir
    tendo uma rota inteira sem usar não é cautela — é preguiça. A cautela está
    em conferir DE NOVO depois de clicar, que é o que continua acontecendo."""

    def _fonte(self):
        return fonte_do_arquivo(os.path.join(RAIZ, "tradovate_auto.py"))

    def test_existe_a_rota_cancelar_todas(self):
        self.assertIn("def cancelar_todas_as_ordens", self._fonte())

    def test_ela_e_tentada_ANTES_de_desistir(self):
        fonte = self._fonte()
        i = fonte.index("def sair_em_mercado_e_cancelar(")
        corpo = fonte[i:i + 8000]
        i_falha = corpo.index('if depois.get("vivas"):')
        trecho = corpo[i_falha:i_falha + 1800]
        self.assertIn("cancelar_todas_as_ordens()", trecho)
        self.assertIn("Cancele na mão", trecho,
                      "e continua havendo desistência honesta no fim")

    def test_a_terceira_contagem_e_quem_declara_sucesso(self):
        """Clicar não é cancelar. Só a releitura com zero ordens autoriza o
        'ok' — a mesma regra do primeiro botão."""
        fonte = self._fonte()
        i = fonte.index("def sair_em_mercado_e_cancelar(")
        corpo = fonte[i:i + 8000]
        self.assertIn("terceira = self.contar_ordens_vivas()", corpo)
        i_t = corpo.index("terceira = self.contar_ordens_vivas()")
        self.assertIn('if terceira.get("ok") and not terceira.get("vivas")',
                      corpo[i_t:i_t + 400])

    def test_reverter_continua_proibido_na_segunda_rota(self):
        """A rota nova não pode reabrir o buraco que a primeira fechou: abrir
        posição contrária é pior do que não cancelar."""
        fonte = self._fonte()
        i = fonte.index("_JS_CANCELAR_TODAS")
        corpo = fonte[i:i + 2500]
        self.assertIn("revers", corpo)
        self.assertIn("proibido.test(n)", corpo)

    def test_escolhe_o_MENOR_elemento_com_o_texto(self):
        """Clicar no centro de um painel erra o alvo — foi o que produziu o
        clique em (1400, 79) que não cancelou nada."""
        fonte = self._fonte()
        i = fonte.index("_JS_CANCELAR_TODAS")
        corpo = fonte[i:i + 2500]
        self.assertIn("a < melhor.area", corpo)


class TestALhamaDesligadaPorPadrao(unittest.TestCase):
    """"LEMBRA DE DESLIGA A LHAMA, NAO QUERO, É MUITO PESADA E SÓ ATRAPALHA,
    TRABALHAREMOS COM OPENROUTER MESMO, NO FUTURO, CASO NECESSARIO RETOMAMOS".

    O padrão mudou de mão porque a premissa mudou: a IA local existia para ser
    o degrau que nunca falta quando a nuvem cai. Com o OpenRouter roteando
    entre dezenas de fornecedores, "a nuvem inteira cair" deixou de ser o caso
    comum — e no Mac dele o Ollama nem sobe."""

    def test_desligada_por_padrao(self):
        ns = carregar(["ia_local_ligada"], stubs={"carregar_config": lambda: {}})
        self.assertFalse(ns["ia_local_ligada"]())

    def test_mas_a_caixinha_continua_religando(self):
        ns = carregar(["ia_local_ligada"],
                      stubs={"carregar_config": lambda: {"ia_local_ativa": True}})
        self.assertTrue(ns["ia_local_ligada"]())

    def test_o_motivo_da_volta_fica_escrito(self):
        """Para que religar seja uma DECISÃO, e não alguém achando que o
        padrão sempre foi este."""
        fonte = fonte_do_arquivo()
        i = fonte.index("def ia_local_ligada")
        self.assertIn("religar é um clique", fonte[i:i + 1600])
