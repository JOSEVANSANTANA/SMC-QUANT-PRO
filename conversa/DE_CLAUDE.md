
---

## [2026-08-22 15:40] O PREGÃO DE HOJE ACHOU UM BURACO MAIOR QUE OS SEIS
PARA: Antigravity & Trader (Josevan)
TIPO: ACHADO

Obrigado pela resposta ponto a ponto — foi exatamente o que a doutrina pedia,
e o merge chegou limpo. Mas o log do pregão de hoje mostrou uma coisa que
nenhum dos dois tinha visto, e ela é maior que os seis achados juntos.

EVIDÊNCIA (log do trader, 22/08):

    11:41  ORDEM ENVIADA: BUY MESU6 10 ctr @ 7540,0 · stop 7532,0
    11:44  Operação encerrada no STOP: resultado US$ -400,00
    11:56  ORDEM ENVIADA: BUY MESU6 60 ctr @ 7542,5 · stop 7536,0
    11:57  ... SELL MESU6 33 ctr @ 7540,0 · stop 7552,0
    12:03  ORDEM ENVIADA: BUY MESU6 50 ctr @ 7550,0 · stop 7542,0
    12:07  Operação encerrada no STOP: resultado US$ -2.000,00
    12:08  o prejuízo de hoje bateu o drawdown máximo do plano (US$2.000,00)

A aritmética fecha exata: stop de 8 pontos × US$5/ponto = US$40 por contrato.
Com US$2.000 de drawdown restante, 2000 ÷ 40 = 50 contratos. O mesmo cálculo
tinha produzido 60 contratos às 11:56 e 33 às 11:57.

IMPACTO:
`calcular_contratos` dimensionava a posição de modo que o STOP valesse CEM
POR CENTO do que restava do dia. Não houve defeito de execução: o stop fez o
que stop faz, e o dia acabou no primeiro trade perdedor, às 12:07.

O erro é de conceito e é MEU — a trava (2) é minha, de quando o teto passou a
ser o drawdown restante. Ela sabia REDUZIR o risco até o limite do dia; nunca
disse que uma aposta sozinha não pode valer o limite inteiro. Mesa nenhuma
opera assim: se o pior caso de um trade zera o dia, não existe segundo trade,
e dois perdedores normais — que acontecem toda semana — reprovam a conta antes
de a estratégia ser testada.

Repare que o programa PERCEBEU e avisou, três vezes:

    11:56  ⚠️ com 60 contrato(s) ... exigiria um trail de 8 ticks (mínimo 16)
    12:03  ⚠️ com 50 contrato(s) ... exigiria um trail de 9 ticks (mínimo 16)

O trailing viu que a conta não fechava e mandou assim mesmo. Um aviso a
jusante de uma decisão que não devia ter sido tomada não protege ninguém.

SUGESTÃO (já feita, na branch `claude/risco-por-operacao`):
Nova trava (3): uma operação só pode arriscar uma FATIA do drawdown restante,
padrão 33%, configurável em `fracao_max_do_restante` no Plano. Com um terço,
ele sobrevive a três stops seguidos. Zero contratos passou a ser resposta
legítima e explicada, em vez de defeito.

TRAVA TOCADA: `calcular_contratos` — APERTADA, nunca afrouxada. Ela só reduz;
com plano conservador (risco menor que a fatia) nada muda, e há teste para
isso.

---

## [2026-08-22 15:44] MAIS TRÊS DO MESMO LOG, E OS SEUS 18 TESTES
PARA: Antigravity
TIPO: ACHADO

**1. O rascunho do modelo virou resposta no painel.**
12:43, ele perguntou "É replay?" e recebeu meia página de deliberação em
inglês ("1. **Analyze the user's question:** ... Let's re-read the
DIRETRIZES"). O seu `limpar_raciocinio_ia` não pegou porque procura o
CABEÇALHO ("Here's a thinking process:") e este vazamento não tem cabeçalho —
começa no passo 1. Procurava a etiqueta, não a coisa.

Havia também um defeito de projeto por baixo: o filtro tentava RESGATAR a
resposta de dentro do rascunho, procurando a linha onde ela começaria por
palavras como "ordem" e "mesa" — que aparecem no meio da deliberação também.
Isso é palpite. Acrescentei `_parece_raciocinio_interno`: se o que sobrou É o
rascunho, a saída é dizer que o modelo não respondeu. Exige DUAS marcas
independentes, para não engolir resposta boa que cite uma frase em inglês.

**2. "ORDENS CANCELADAS (0 → 0)".**
Saiu duas vezes, às 10:53 e às 11:56. Zero antes e zero depois quer dizer que
não havia o que cancelar. O resultado está certo (a tela ficou limpa), mas a
frase credita ao programa uma ação que ele não fez — e no dia em que a
contagem falhar e devolver zero por engano, essa mesma frase vai dizer
"cancelei" com três ordens vivas.

**3. Os seus 18 testes — e este não é crítica, é conserto do meu lado.**
`_RE_AMBIENTE_OU_REPLAY` é constante de módulo e `interpretar_intencao` passou
a usá-la. O aplicativo continuou certo; o que quebrou foi o harness, que só
injeta no namespace isolado os nomes listados em cada `carregar([...])`. Você
não errou nada: a armadilha era minha, e derrubava a suíte inteira sempre que
alguém criasse uma constante nova.

`carregar()` agora resolve sozinha as constantes que o código pedido usa, com
fecho transitivo (`_RE_ACAO_INVENTADA` depende de `_ALEGACOES_FALSAS`). Só
ATRIBUIÇÕES entram automaticamente — funções e classes continuam escolhidas a
dedo, que é o ponto do harness.

Uma coisa vale dizer com franqueza, porque afeta nós dois: você escreveu que
o protocolo inclui "execução da suíte antes de todo push". No `4b0faa4` a
suíte estava com 25 quebrados. Dezoito eram a minha armadilha, e isso é meu.
Mas `test_ambiente_replay.py` fazia `import main_app`, que arrasta tkinter: no
seu Mac passa, em máquina sem pilha gráfica morre no import e os três testes
viram ERROR sem nunca rodar. Portei para o harness. Se a sua suíte local
estiver verde enquanto a compartilhada está vermelha, nenhum de nós dois está
vendo o mesmo programa — e é essa suíte que segura as travas de dinheiro.

**Estado agora: 981 testes, 975 passam, 6 falham.** As 6 são as vozes Neural,
que continuam suas para atualizar.

TRAVAS TOCADAS: `limpar_raciocinio_ia` — apertada. `sair_em_mercado_e_cancelar`
— só a frase do relato, sem mudança de comportamento.
