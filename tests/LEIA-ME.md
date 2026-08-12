# Testes do SMC Quant Pro

## Como rodar

```
python3 tests/run.py
```

Sem instalar nada. Não abre janela, não toca em disco do app, não precisa de
chave de API nem de internet.

### E o teste que ABRE a janela

```
xvfb-run -a python3 tests/fumaca_gui.py     # sem monitor (servidor/CI)
python3 tests/fumaca_gui.py                 # com monitor
```

Precisa de tela e das bibliotecas da interface instaladas. Ele sobe o programa
de verdade, percorre as abas, aplica todas as escalas de letra, recolhe e abre
seções, dispara notificações, salva o plano e grava um PNG para conferência
humana.

Existe porque há uma classe de defeito que o `run.py` não alcança: a janela
abre, nenhum widget levanta exceção, e mesmo assim o trader não consegue usar.
Foi assim que se descobriu que 22 rótulos ficavam **invisíveis** quando o
sistema está em modo claro.

## Por que estes testes estão AQUI dentro

A suíte anterior morava numa pasta temporária, fora do repositório, e foi
destruída num reset de máquina. Teste que não é versionado não existe. Estes
ficam junto do código: quem clonar o projeto tem a suíte.

## Como funciona

`main_app.py` importa `customtkinter` e sobe a interface — não dá para
`import main_app` num teste. O `harness.py` lê o arquivo, extrai por AST
**apenas** as funções e constantes que cada teste precisa, e executa esse
pedaço num namespace montado à mão, com stubs no lugar do que toca disco.

Se uma função for renomeada, o harness falha com "não achei no main_app.py" em
vez de passar testando o vazio.

## O que cada arquivo cobre

| Arquivo | O defeito real que ele trava |
|---|---|
| `test_dimensionamento.py` | Stop de 1,87 ponto no MES virando 29 contratos numa conta de US$1.400; drawdown do dia usado cheio depois de já ter sido gasto; teto de contratos. |
| `test_piso_qualidade.py` | Sete descartes seguidos por R:R, com o 2º alvo pagando o piso e sendo ignorado; e a garantia de que o piso de 1:2 **não** foi afrouxado. |
| `test_conversa.py` | "qual a utima sugestao?" virando "não há sugestão de QUAL"; "compro ou vendo?" caindo no despejo genérico; "o stop do MESU6 é 7760" gravando stop = 6. |
| `test_mac.py` | `No module named 'numpy'` matando o microfone; mensagens mandando um usuário de Mac abrir telas do Windows. |
| `test_motor.py` | "Motor no ar" dito sobre um processo que já tinha morrido; a porta 3939 ocupada virando tarefa do trader no Terminal; cenário morto ficando "aguardando decisão" para sempre. |
| `test_interface.py` | A aba Motor recolhível: um widget cujo bloco pai é criado DEPOIS dele impede o app de abrir, e o pyflakes não pega isso. Também o tamanho de letra (valor absurdo no config não pode inutilizar a janela). |
| `test_qualidade_leitura.py` | Preço congelado por 13 ciclos com o motor sugerindo em cima; entrada a 8,6 R do preço; tema escuro não fixado (rótulos invisíveis em sistema no modo claro). |
| `test_duplicidade.py` | A MESMA operação virando dois registros no diário e o resultado sendo contado em dobro; a notificação roubando a tela no macOS. |
| `test_notificacao.py` | A notificação roubando a tela no macOS (resolvida com a notificação nativa, não com truque de Tk); o microfone que abre e devolve silêncio por falta de permissão. |
| `test_inteligencia.py` | A TIGER sendo Gemini-e-mais-nada (sem cota = sem cérebro); `satatus` e `tria um print` morrendo por uma letra; um preço virando regra permanente e não havendo como apagá-la. |
| `test_empacotamento.py` | O repositório ficou versões inteiras sabendo compilar para Mac e **não** para Windows — o `.spec` do `.exe` vivia só na máquina do trader. A simetria entre os dois sistemas virou teste. |
| `test_honestidade.py` | "Onde está a VWAP?" respondida três vezes com "o preço está acima dela" e o número do ATIVO; um número da conta dito errado com confiança; a janela `'Claude — Claude'` analisada por 20 minutos como se fosse gráfico; o "sim" que respondia à pergunta dela mesma e caía no despejo genérico; e o WhatsApp reconectando de 5 em 5 segundos, para sempre, com o código 500. **E a rodada seguinte:** obrigada a dizer o número, ela passou a inventá-lo (`VWAP 7752.34` com a legenda em `7769.56`), afirmou posição vendida com a plataforma em `POSIÇÃO 0`, e o "sem crédito" que a OpenAI escreveu virou um palpite de três causas. |

## Regra da casa

Todo defeito que chegar pelo log do trader vira um teste **antes** de virar
correção. O comentário de cada teste guarda a frase real e a resposta errada —
é isso que impede a mesma regressão de voltar em duas versões.
