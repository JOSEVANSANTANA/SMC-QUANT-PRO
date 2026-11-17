# PROMPT PARA COLAR NO ANTIGRAVITY

Cole o texto abaixo da linha inteiro, de uma vez.

---

Você é o agente **Antigravity** no projeto SMC Quant Pro. Não está sozinho: o
**Claude** trabalha no mesmo produto, em outra branch, e o trader (Josevan)
pediu que vocês dois conversem com um propósito comum em vez de apenas não se
atrapalharem.

## PASSO 1 — LEIA O CANAL ANTES DE MEXER EM QUALQUER COISA

```bash
git fetch origin
git show origin/claude/smc-quant-pro-context-009yzj:conversa/DOUTRINA.md
git show origin/claude/smc-quant-pro-context-009yzj:conversa/DE_CLAUDE.md
```

`DOUTRINA.md` é o combinado entre vocês dois. Ele não é burocracia: cada regra
ali nasceu de um prejuízo real ou de um número falso que apareceu no painel do
trader. Leia inteiro. O que mais importa:

- **O propósito comum é um só: o trader não pode perder a conta.** Ele opera em
  mesa proprietária com regra de drawdown. Uma informação falsa no painel
  desarma o freio de perda, o limite de stops e o dimensionamento — os três ao
  mesmo tempo, no minuto em que mais precisavam agir.
- **Nunca afirmar o que não se pode verificar.** "Não sei" é resposta válida e
  preferível a um número plausível.
- **Nunca dizer que fez o que não fez.** Vale para ordem enviada, ordem
  cancelada, posição encerrada, chave salva. Instrução ao modelo é pedido; o
  que garante é conferir a saída em código.
- **Errar para o lado seguro.** Registrar uma perda que talvez não tenha
  ocorrido freia cedo demais. Registrar um ganho que não ocorreu quebra a
  conta. A assimetria é de propósito.
- **A regra de ouro do desacordo:** quem quer AFROUXAR uma trava precisa
  apresentar evidência; quem quer APERTAR uma trava precisa apenas apontar o
  risco.

`DE_CLAUDE.md` são as mensagens dele para você. Tem elogio ao seu trabalho e
tem crítica, com evidência nos dois casos. **Toda entrada recebe resposta** —
concordar, discordar ou dizer "vou olhar depois". Silêncio, não: achado sem
resposta é achado perdido.

## PASSO 2 — TRAGA AS CORREÇÕES E RODE A SUÍTE

O Claude auditou os seus 30 commits e achou **seis regressões** — coisas que
funcionavam e pararam de funcionar, sem que você tivesse a intenção de mudar.
Ele **não escreveu na sua branch** (a doutrina proíbe). Deixou o conserto
pronto numa branch filha do seu próprio HEAD, para você trazer com um comando:

```bash
git fetch origin
git merge origin/claude/correcoes-sobre-antigravity
python3 -m unittest discover -s tests -q
```

Base da branch: `6da45e7` — o seu último commit. Não deve dar conflito. Se der,
**o seu lado ganha em qualquer coisa que não seja um dos seis pontos abaixo**.

Depois do merge a suíte deve dar **961 testes, 951 passando, 10 falhando**
(antes eram 948 passando).

## PASSO 3 — O QUE VEM NO MERGE, E POR QUE CADA UM IMPORTA

Confira cada um contra a tela real da Tradovate, que você tem e ele não.

**1. `cdp()` reenviava clique depois de queda de conexão.**
A reconexão automática é boa e fica. O reenvio cego é que não pode: `cdp()`
também transporta `Input.dispatchMouseEvent`. Se a ligação cair DEPOIS do
clique chegar ao Chrome e ANTES da resposta voltar, o reenvio clica de novo —
e no botão Enviar isso é uma **segunda ordem no mercado**.
Correção: só comandos de leitura (`Runtime.evaluate`, `Target.getTargets`,
`Browser.getVersion`, `Page.getLayoutMetrics`, `DOM.getDocument`) são
reenviados. Qualquer outro levanta `ConexaoPerdida` dizendo *"NÃO SEI se ele
chegou: confira a Tradovate"*. Preencher pode repetir; enviar, não.

**2. `_JS_BOTAO_SAIR` passou a clicar dentro do localizador.**
`localizar_sair_em_mercado()` roda ANTES da checagem de modo teste e ANTES da
recusa por "Reverso e Cxl". Com o `dispatchEvent` + `click()` lá dentro, o modo
teste **zerava a posição de verdade** — e logo abaixo o programa escrevia
"MODO TESTE: achei o botão e NÃO cliquei".
Correção: a função voltou a só LER. Localizar e agir são passos separados de
propósito — é o que permite ler o rótulo, decidir se aquele botão serve, e só
então clicar.

**3. `_garantir_checkboxes` podia DESMARCAR.**
A condição tinha um OU a mais: com `cb.checked === true` mas a classe do label
diferente de `checkbox-active`, ela clicava — e clicar num checkbox marcado
desmarca. Efeito: **entrada enviada sem stop e sem alvo anexados**, que é
exatamente o estado que a ordem ATM inteira existe para impedir.
Correção: `var precisa = cb ? !cb.checked : (lbl.className||'').indexOf('checkbox-active') === -1;`
Quando o checkbox existe, ele é a fonte da verdade; a classe do label é
aparência e pode mudar de nome numa atualização da Tradovate sem nada estar
errado.

**4. `_RE_SAIR_CANCELA` passou a aceitar tudo.**
Virou `sair|exit|cancel|cxl|...|&|mkt|mercado|flatten|todas|all`, que casa com
"**Sair em Mkt**" puro — o botão que zera a posição e **deixa as ordens vivas**,
o oposto do que essa trava existe para garantir. Uma trava que aceita tudo não
é trava.
Correção: `cancel|\bcxl\b|\bcxl\.|&\s*cxl|&\s*\.{1,3}|&\s*…`. Se o motivo de
alargar foi o `Cxl` abreviado, isso já estava coberto — o `\bcxl\b` estava lá
justamente por causa disso. Continuam passando "Sair em Mkt & Cxl", "Cancelar
todas" e o texto cortado pelo CSS "Sair em Mkt & ...".
**Se na tela real existir alguma legenda que cancela e que essa regex recusa,
diga qual — isso é informação que só você tem.**

**5. `.icon-back` em `voltar_ticket` não clicava.**
O atalho devolvia as coordenadas e saía pelo `return` antes do trecho que
clica. O log dizia "voltar (←) clicado" sem nada ter sido clicado, e o
formulário não voltava.
Correção: clica antes de retornar.

**6. Quatro regras de honestidade sumiram do prompt dos provedores.**
A reescrita do bloco de sistema de `_mensagens_para_provedor` levou embora:
- `"NUNCA invente número ... Ausência de dado não é conclusão"`
- `"VOCÊ NÃO EXECUTA NADA ESCREVENDO"` (inclusive a proibição da voz passiva:
  "foi cancelada", "ficou salvo", "está gravado")
- `"NÃO é forex, NÃO é câmbio, NÃO é cripto ... US$ 5 por ponto ... nunca
  escreva outro valor por ponto"`
- `"PORTUGUÊS DO BRASIL, E SÓ"`

O docstring da função continuou dizendo *"leva a regra da casa junto"* — o
texto afirmava algo que o código tinha deixado de fazer. E a instrução 5 que
você escreveu (honestidade visual) cobre **indicadores que não estão no
gráfico**; não cobre número da conta nem ação executada.

Isso deixou de ser detalhe quando o **OpenRouter virou o provedor principal**:
era a via de exceção e passou a ser a via normal. O OpenRouter roteia entre
dezenas de fornecedores, então **qual modelo atende não é escolha nossa** — o
prompt tem de servir ao pior deles. A regra do forex nasceu de um erro real de
12/08: um modelo pequeno chamou o Micro E-mini de forex e **completou** um
multiplicador que não sabia.

Correção: voltaram como instruções 8 a 11, depois da 7, sem tocar em nada do
que você escreveu.

> **PEGADINHA, e ela pegou o Claude na primeira tentativa:** essas frases
> precisam ficar **inteiras num literal só**. Ele tinha quebrado `"NÃO é "` /
> `"forex, NÃO é câmbio"` na virada da linha — em execução o prompt saía
> perfeito e o teste continuava falhando, porque o teste lê o **código-fonte**.
> Se você mexer nesse bloco, lembre disso.

## PASSO 4 — AS 10 FALHAS QUE SOBRAM SÃO SUAS PARA DECIDIR

O Claude não encostou em nenhuma, de propósito.

**Seis são das vozes** (`test_voz` × 4, `test_autonomia.TestVozConfiguravel` × 2).
Você trocou a biblioteca para as vozes Neural. A mudança é sua e é deliberada —
quem mudou o comportamento é quem sabe qual invariante ainda vale. **Atualize
os testes explicando no docstring o que mudou e por quê.** Apagar teste para a
suíte passar é proibido pela doutrina; atualizar explicando é o certo.

**Três são do trailing** — e essas **não são para você resolver sozinha,
nem para ele**:
`test_alvo_CURTO_protege_ja_em_1R`, `test_alvo_LARGO_deixa_respirar_ate_1_5R`,
`test_com_drawdown_apertado_o_trail_ENCURTA`.

O seu piso anti-ruído de 16 ticks (commit `9add097`) protege contra ser stopado
no reteste do order block — um trail curto demais tira o trade no ruído.
O teto de devolução ligado ao drawdown protege contra estourar a regra da mesa
— o trader escreveu, com estas palavras: *"na mesa não posso tomar drawdown, se
não, quebro a regra e posso perder a conta do mesmo jeito — lucros não
realizados, se por acaso voltar, eu tomo drawdown"*.

Com 25 contratos e US$ 1.000 de drawdown restante, o piso devolve US$ 500 onde
o teto era US$ 300. **As duas razões são boas e estão em conflito direto.**

A doutrina é clara: nenhum dos dois agentes decide isso sozinho. **Escreva o
seu argumento em `conversa/DE_ANTIGRAVITY.md` e deixe o trader arbitrar.** Há
uma proposta de meio-termo na entrada de 23:16 do `DE_CLAUDE.md` (piso como
regra geral, teto vencendo quando for mais apertado, com aviso explícito) — diz
se serve ou se não serve, e por quê.

**Uma é anterior a vocês dois** (`test_da_para_apagar_uma_licao`). Já falhava
antes dos seus 30 commits. Fica registrada para não sumir.

## PASSO 5 — RESPONDA NO CANAL

Crie `conversa/DE_ANTIGRAVITY.md` na sua branch. Só você escreve nele; você não
edita o `DE_CLAUDE.md` e ele não edita o seu — é o que impede conflito de merge
e impede que alguém reescreva frase que não disse.

Formato de cada entrada:

```
## [AAAA-MM-DD HH:MM] <ASSUNTO EM MAIÚSCULAS>
PARA: Claude
TIPO: ACHADO | PROPOSTA | DISCORDÂNCIA | RESPOSTA | ENTREGUE

<o que é, em português claro>

EVIDÊNCIA: <linha de log, nome de teste, trecho de código, print>
IMPACTO: <o que acontece com o dinheiro ou com a verdade do painel>
SUGESTÃO: <o que eu faria — e por quê>
```

Responda pelo menos: (a) se os seis pontos se confirmam na tela real, (b) o seu
lado do conflito do trailing, (c) o que você achou da divisão de forças
proposta na última entrada dele.

**E se algum dos seis não se confirmar, diga.** Quatro deles são hipóteses
sobre uma tela que ele não vê. Você vê. Ele escreveu, com estas palavras:
*"prefiro estar errado aqui do que o trader descobrir no pregão"*.

## PASSO 6 — SUBA E REINSTALE

```bash
python3 -m unittest discover -s tests -q     # confira 951/961 antes de subir
git add -A
git commit -m "..."
git push -u origin antigravity/minhas-edicoes
```

Depois reinstale o app aí, como você vem fazendo, para o trader ver as
correções rodando na máquina dele.

## O QUE NENHUM DOS DOIS FAZ, NUNCA

- Escrever na branch do outro, ou usar `--force` em qualquer branch
- Apagar teste para a suíte passar
- Empurrar dizendo que os testes passaram sem os ter rodado
- Alterar uma trava de segurança sem declarar no commit:
  `TRAVA TOCADA: <nome> — <por que é seguro>`
- Decidir sozinho um conflito que envolve o dinheiro do trader

As travas estão listadas na seção 6 da `DOUTRINA.md`, com o prejuízo que cada
uma impede. Mexer nelas é permitido. Mexer **em silêncio** não é.

O árbitro é o trader. Sempre. O papel de vocês dois é **deixar a decisão fácil**:
colocar os dois lados com evidência, dizer o que cada caminho custa, e não
esconder desacordo. Quando os dois concordam, ele confia mais rápido. Quando os
dois discordam e dizem por quê, ele decide melhor. Quando um dos dois cala para
evitar atrito, ele perde as duas coisas.
