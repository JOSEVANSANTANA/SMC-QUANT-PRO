# Testes do SMC Quant Pro

## Como rodar

```
python3 tests/run.py
```

Sem instalar nada. Não abre janela, não toca em disco do app, não precisa de
chave de API nem de internet.

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
| `test_empacotamento.py` | O repositório ficou versões inteiras sabendo compilar para Mac e **não** para Windows — o `.spec` do `.exe` vivia só na máquina do trader. A simetria entre os dois sistemas virou teste. |

## Regra da casa

Todo defeito que chegar pelo log do trader vira um teste **antes** de virar
correção. O comentário de cada teste guarda a frase real e a resposta errada —
é isso que impede a mesma regressão de voltar em duas versões.
