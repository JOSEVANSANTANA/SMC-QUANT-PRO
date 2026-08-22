"""TRÊS NÚMEROS PARA A MESMA POSIÇÃO, NO MESMO INSTANTE.

22/08, 16:10. Ele tinha acabado de excluir a conta 'TESTES SMC QUANT' e ativar
a 'testes zero', com Margem US$2.000 e Risco 5% salvos e VISÍVEIS na tela.
Saíram estas três linhas, uma atrás da outra:

    🤖 MODO AUTÔNOMO: acatando BUY MESU6 sozinha (3 ctr)
    ⚠️ Acatado, mas o plano dimensionou 0 contrato: Margem não configurada
       no Plano de Trading.
    ⏳ Ordem PENDENTE registrada: BUY MESU6 @ 7544.0 (1 ctr)

Três, e o de baixo virou ordem de verdade na Tradovate.

DOIS DEFEITOS, encaixados um no outro:

**O plano de zeros.** `conta_ativa()` devolve None quando o ponteiro da conta
ativa aponta para um id que saiu da lista. O `(None or {})` fazia o plano cair
inteiro no PLANO_PADRAO — margem 0, meta 0, drawdown 0 — e o programa
anunciava "Margem não configurada" enquanto a tela mostrava US$2.000, porque
a tela lê de outro lugar. O mesmo zero envenenava o freio: às 14:44 saiu
"teto configurado em US$ 0.00" numa conta cujo teto era US$150.

**O `or 1`.** Com o dimensionamento em zero, `sizing["contratos"] or 1` abria
a posição com um contrato que ninguém dimensionou. Zero não veio de arredondar
para baixo — veio de uma trava dizendo NÃO. Um contrato de MES parece pouco, e
é exatamente por isso que passou despercebido.
"""

import unittest

from harness import carregar


PLANO_REAL = {"margem": 2000.0, "risco_pct": 5.0, "drawdown_maximo": 1000.0,
              "max_contratos": 20, "min_ticks_stop": 8}

CONTA = {"id": "conta_testes_zero", "nome": "testes zero",
         "plano_trading": dict(PLANO_REAL)}


def _ns(contas, id_ativo):
    return carregar(
        ["PLANO_PADRAO", "conta_ativa", "plano_da_conta_ativa"],
        stubs={"carregar_contas": lambda: [dict(c) for c in contas],
               "conta_ativa_id": lambda: id_ativo,
               "print": lambda *a, **k: None})


class TestOPonteiroOrfao(unittest.TestCase):

    def test_conta_excluida_nao_vira_plano_de_zeros(self):
        """O caso exato: o ponteiro ficou apontando para a conta excluída."""
        ns = _ns([CONTA], "conta_QUE_FOI_EXCLUIDA")
        plano = ns["plano_da_conta_ativa"]()
        self.assertEqual(plano["margem"], 2000.0,
                         "com o ponteiro órfão, o plano caía todo em zero e o "
                         "programa dizia 'Margem não configurada' com US$2.000 "
                         "na tela")
        self.assertEqual(plano["drawdown_maximo"], 1000.0,
                         "drawdown zerado faz o freio achar que o teto do dia "
                         "é zero — foi o 'teto configurado em US$ 0.00' das 14:44")
        self.assertEqual(plano["risco_pct"], 5.0)

    def test_com_o_ponteiro_certo_nada_muda(self):
        ns = _ns([CONTA], "conta_testes_zero")
        self.assertEqual(ns["plano_da_conta_ativa"]()["margem"], 2000.0)

    def test_sem_conta_nenhuma_o_zero_e_a_verdade(self):
        """Aqui 'margem não configurada' é resposta honesta, não defeito.

        A trava aperta o caso do ponteiro órfão, e SÓ ele. Sem conta alguma
        cadastrada, não existe plano — e inventar um seria o erro oposto.
        """
        ns = _ns([], "seja_la_qual_for")
        self.assertEqual(ns["plano_da_conta_ativa"]()["margem"], 0)

    def test_adota_a_primeira_conta_e_nao_uma_qualquer(self):
        outra = {"id": "conta_2", "nome": "outra", "plano_trading": {"margem": 99.0}}
        ns = _ns([CONTA, outra], "id_que_nao_existe")
        self.assertEqual(ns["plano_da_conta_ativa"]()["margem"], 2000.0)


class TestZeroContratoNaoViraUm(unittest.TestCase):
    """A regra, medida no dimensionamento que alimenta o acatar."""

    def _sizing(self):
        return carregar(
            ["FRACAO_MAX_DO_RESTANTE_PADRAO", "calcular_contratos"],
            stubs={"valor_por_ponto_do_ativo": lambda a: 5.0,
                   "tick_do_ativo": lambda a: 0.25})

    def test_plano_sem_margem_devolve_zero_com_motivo(self):
        ns = self._sizing()
        r = ns["calcular_contratos"](7544.0, 7538.5, "MESU6", 0, 5.0, 1000.0)
        self.assertEqual(r["contratos"], 0)
        self.assertIn("Margem não configurada", r["motivo_limite"])

    def test_stop_curto_demais_tambem_devolve_zero(self):
        """O outro caminho para o zero — e o `or 1` atropelava os dois."""
        ns = self._sizing()
        r = ns["calcular_contratos"](7544.0, 7543.5, "MESU6", 2000, 5.0, 1000.0,
                                     min_ticks_stop=8)
        self.assertEqual(r["contratos"], 0)
        self.assertIn("curto demais", r["motivo_limite"])

    def test_o_plano_real_dele_dimensiona_os_3_contratos(self):
        """O número que o modo autônomo mostrou primeiro estava certo.

        Entrada 7544,0 · stop 7538,5 = 5,5 pontos = US$27,50 por contrato.
        Margem US$2.000 × 5% = US$100. 100 ÷ 27,50 = 3.
        """
        ns = self._sizing()
        r = ns["calcular_contratos"](7544.0, 7538.5, "MESU6", 2000.0, 5.0,
                                     1000.0, max_contratos=20, min_ticks_stop=8,
                                     restante_dia=1000.0)
        self.assertEqual(r["contratos"], 3)


class TestOCodigoNaoTemMaisOAtalho(unittest.TestCase):

    def test_o_or_1_saiu_do_caminho_do_acatar(self):
        """`sizing["contratos"] or 1` não pode voltar: é uma linha só, some
        numa revisão distraída, e vira ordem no mercado.

        Descarta COMENTÁRIOS: a lição de 22/08 ficou escrita junto do
        conserto, e ela cita o trecho antigo. O teste mede o que o programa
        EXECUTA, não o que ele conta sobre si — do contrário puniria quem
        documenta, que foi o que aconteceu com o teste do 'DEFEITO DO
        PROGRAMA'.
        """
        from harness import fonte_do_arquivo
        linhas = [l for l in fonte_do_arquivo().splitlines()
                  if not l.lstrip().startswith("#")]
        culpadas = [(i + 1, l.strip()) for i, l in enumerate(linhas)
                    if 'contratos"] or 1' in l]
        # A mensagem não despeja o arquivo: aponta a linha.
        self.assertEqual(culpadas, [], "o atalho voltou em: %s" % culpadas)
        self.assertIn("🚫 NÃO ABRI a posição", "\n".join(linhas))


if __name__ == "__main__":
    unittest.main()
