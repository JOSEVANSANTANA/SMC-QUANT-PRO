# Como compilar o SMC Quant Pro (Windows)

## UM CÓDIGO, DOIS PACOTES

`main_app.py`, `plataforma.py`, `tradovate_auto.py` e a pasta `motor/` são os
**mesmos arquivos** no Windows e no Mac. Quem decide "PrintWindow ou
`screencapture`", "DPAPI ou Chaveiro", "win32gui ou Quartz" é o
`plataforma.py`, em tempo de execução.

**Consequência:** toda correção já nasce valendo para os dois sistemas. Não
existe "corrigir no Mac e depois portar para o Windows".

O que muda entre um pacote e outro é só a casca:

| | Windows | Mac |
|---|---|---|
| Dependências | `requirements.txt` | `requirements-mac.txt` |
| Empacotador | `SMC_Quant_Pro.spec` | `SMC_Quant_Pro_MAC.spec` |
| Passo a passo | `LEIA-ME_WINDOWS.txt` | `LEIA-ME_MAC.txt`, `INSTALAR_NO_MAC.md` |
| Instalador | `instalador/SMC_Quant_Pro.iss` | `INSTALAR_MAC.command`, `CRIAR_APP.command` |

Os dois pacotes saem de um comando só, do próprio repositório:

```
python empacotar.py            # gera os dois zips
python empacotar.py windows    # só o do Windows
python empacotar.py mac        # só o do Mac
```
[[SO SEU — nao vai no pacote do cliente]]
```
python empacotar.py --sem-painel   # sem o painel de licenças (para repasse)
python empacotar.py --entrega      # um zip só, com SEU/ e CLIENTE/ dentro
```
[[FIM SO SEU]]

O script recusa gerar um pacote incompleto: se um arquivo da lista sumir do
repositório, ele para e diz qual, em vez de entregar um zip capenga.

---

## 0. Qual versão é esta

A versão vigente está no `versao.json` — é de lá que o app, o verificador de
atualização e o `empacotar.py` leem o número. Não há versão digitada em outro
lugar que possa envelhecer em silêncio.

Arquivos que mudam com mais frequência: `main_app.py`, `plataforma.py`,
`tradovate_auto.py`, `motor/index.js`, `versao.json`. O **motor** só precisa
ser reinstalado (`npm install`) quando o `motor/package.json` muda — fora
isso, reaproveite a pasta `motor\` com o `node_modules` que você já tem.

### Antes de compilar, rode a suíte

```
python tests\run.py
```

Sem janela, sem tocar nos seus dados, sem chave de API e sem internet. Se algo
quebrou, aparece aqui em segundos — e é bem mais barato descobrir aqui do que
depois de gerar o `.exe`.

### Novidades da 2.16.0

**🎯 Ela FAZ, em vez de mandar você fazer.** Este é o defeito, e o log de 10/08
mostra em quatro linhas:

> 14:26 ❯ *ONDE POSICIONO MEU STOP DA OPERAÇÃO EM ANDAMENTO?*
> 14:26 ✳ *"…o motor não tem leitura fresca. **Diga 'tira um print'**."*
> 14:26 ❯ *TIRA UM PRINT*
> 14:26 ✳ *"seu stop técnico ideal fica entre **7791.00 e 7792.50**."* ← perfeito
> 14:27 ❯ *ONDE EU DEVERIA POSICIONAR MEU ALVO?*
> 14:27 ✳ *"…**diga 'tira um print'**."* ← de novo

**Ela sabia fazer.** Só devolvia a tarefa para você digitar o comando. Você
chegou a **ensinar** (*"TIRA UM PRINT, USA O MOTOR PARA DETERMINAR ISSO"*) e ela
passou a **citar a lição** sem cumpri-la — que é a definição exata de "não está
aprendendo".

Agora, **perguntar onde vai o stop JÁ É pedir para olhar o gráfico**. Não existe
responder isso sem ver o preço. Então a pergunta **captura e lê sozinha**:

*"onde posiciono meu stop"* · *"onde deveria posicionar meu alvo"* · *"qual o
alvo"* · *"onde eu saio"* · *"onde coloco a proteção"* · *"onde faço a parcial"*

**O que NÃO dispara captura** (para não gastar cota à toa): *"o que é um stop"*,
*"como se calcula o R:R"*, *"explica o conceito"* — teoria continua sendo
respondida de cabeça, na hora, sem tocar na API.

**📒 Ela passa a consultar o HISTÓRICO DE SUGESTÕES.** Às 14:46:

> ❯ *onde foi a última sugestão de venda de MGCV6?*
> ✳ *"não está na minha base, não consegui confirmar na internet, e a API está
> fora…"*

Com o arquivo de sugestões **ali no disco dela**. Você respondeu certo: *"É SÓ
VOCÊ OLHAR NOS HISTÓRICOS DE SUGESTÕES"*. Agora ela olha — e devolve a sugestão
com entrada, stop, alvo, hora e o que aconteceu com ela (acatada, dispensada,
resultado). **Sem cota, sem internet, sem modelo.** Pedindo "o histórico do X"
ela lista as últimas.

Com duas travas: se você perguntar de um ativo que **não está** no histórico,
ela diz *"procurei e NÃO há sugestão de PETR4"* e mostra o que existe — **nunca**
devolve a sugestão de outro ativo no lugar. E histórico vazio é dito como vazio,
sem culpar a API.

**✍️ "SUGESTÕES-APRENDA ISSO".** Você escreveu assim, com o hífen colado, e a
lição **não foi gravada** — o padrão exigia espaço ou vírgula antes do verbo.
Agora o hífen (e o travessão) valem como separador.

### Novidades da 2.15.0

**🔧 A TIGER passa a USAR O MOTOR para responder sobre stop e alvo.** Era este o
defeito que você apontou — *"ela está cega, não usa o motor"*. E era literal.

Dia 10/08, às 14:02, com a operação aberta:

> ❯ *ONDE DEVERIA POSICIONAR MEU ALVO NESSA OPERAÇÃO QUE ESTOU POSICIONADO?*
> ✳ *"O alvo é a próxima liquidez do lado oposto… Aplicando à sua posição
> aberta: SELL MESU6 @ 7784.75, **stop None, alvo None**."*

E o **motor já tinha calculado, para o MESMO ativo**, às 12:16:
`SELL MESU6 — stop 7796.5, alvo 7761.25`.

A causa está numa linha só de `ler_cenario_do_topico`: a leitura fresca do
gráfico era consultada num ramo `elif` que **só rodava quando NÃO havia posição
aberta**. Ou seja — exatamente quando você tinha dinheiro na mesa e perguntava
onde pôr o stop, a ferramenta respondia com o aforismo do manual e **ignorava o
número que ela mesma tinha acabado de ler**.

Agora, com posição aberta e pergunta sobre stop/alvo/risco, a resposta traz:

- os **níveis calculados pelo motor** (stop, alvo, 2º alvo) e a **hora** da leitura;
- as **confluências** que sustentam esses níveis;
- **⚠️ SEM STOP registrado** com essas palavras, em vez de `stop None`;
- e o número do motor apontado como **candidato direto** ao seu stop.

Com três travas que os testes cobrem:
- leitura do motor **no lado oposto** ao seu (o caso das 11:55, você SELL e o
  motor virando BUY) → **avisa** que aqueles níveis são da operação contrária e
  servem de mapa de liquidez, **nunca** entrega como "o seu stop";
- leitura de **outro ativo** (motor acabou de ler o ouro, sua posição é no MES)
  → **não mistura**, oferece capturar o gráfico agora;
- **sem leitura nenhuma** → oferece *"tira um print"*, e **não chuta nível**.

**🔁 A mesma resposta três vezes seguidas.** Às 14:01 e 14:02 saiu texto
idêntico, palavra por palavra, três vezes. A guarda anti-repetição existia, mas
tinha um furo: ela mandava o turno para o modelo em vez de repetir — e, com a
cota estourada, o modelo falhava, caía no caminho de emergência e ali
`responder_offline()` era chamado **de novo**, devolvendo o mesmo texto. A guarda
agora também vale nesse caminho.

**⌨️ "deliga o motor".** Você digitou assim (sem o S) e caiu no despejo de *"não
tenho como responder"*. Agora o erro de digitação é tolerado — com segurança: o
**substantivo continua obrigatório**, que é a regra que impede o falso positivo
que já desligou o motor no meio de um pregão. Os testes conferem que
*"não precisa acionar a cota da API para algumas análises"* e *"vou deligar para
o meu corretor"* continuam **não** desligando nada.

### Novidades da 2.14.0

**🍎 O programa roda no Mac (Apple Silicon M1/M2/M3).** Até aqui o `main_app.py`
chamava a API do Windows DIRETO no meio da lógica de trading: `win32gui` para
listar janelas, `PrintWindow` para capturar o gráfico, `win32crypt` (DPAPI) para
guardar a chave da Gemini, `winsound` para o bipe. Isso prendia o programa
inteiro ao Windows.

Agora existe **uma fronteira só**, o `plataforma.py`. O resto do programa pede
*"capture a janela do gráfico"* e é lá dentro que se decide se isso significa
`PrintWindow` (Windows) ou `screencapture -l` (macOS).

| O que o programa faz | Windows | macOS |
|---|---|---|
| Guardar a chave da Gemini | DPAPI | **Chaveiro do macOS** |
| Listar janelas abertas | win32gui | **Quartz (pyobjc)** |
| Capturar o gráfico em 2º plano | PrintWindow | **`screencapture -l`** |
| Bipe do alerta | winsound | **som do sistema** |
| A TIGER falar | pyttsx3 / SAPI5 | **voz `say` nativa** |
| Pasta de dados | `%APPDATA%` | **`~/Library/Application Support`** |

**Nada da lógica de trading mudou** — e isso é verificado por teste: nenhuma das
funções de decisão (`freio_de_sugestoes`, `ajuste_por_aprendizado`,
`politica_com_posicao_aberta`, `posicao_aberta_no_ativo`, `modelos_para_tentar`,
`classificar_erro_modelo`) consulta o sistema operacional. **No Windows tudo
continua exatamente como está** — a rota do Windows é o mesmo código de antes,
só que agora mora no `plataforma.py`.

Três defeitos reais foram corrigidos no caminho, e valem para os dois sistemas:

- **A voz sairia em inglês no Mac.** A escolha da voz procurava
  `"brazil"`/`"portugu"` **no nome** — e no Mac as vozes de português se chamam
  *Luciana*, *Joana*, *Catarina*. Agora a busca olha o **id/idioma** também.
- **O motor não subiria no Mac.** Um app aberto pelo **Finder não herda o PATH
  do shell**, então o Node do Homebrew (`/opt/homebrew/bin`) "sumia": `node -v`
  funcionava no Terminal e o programa jurava que o Node não existia. O PATH é
  completado no arranque e o Node é procurado pelo caminho real.
- **Mensagens de erro mandavam o usuário de Mac abrir o Gerenciador de Tarefas
  e procurar `node.exe`.** Agora cada sistema recebe a instrução dele
  (`lsof -ti :3939 | xargs kill -9` no Mac).

**Diagnóstico no arranque:** a aba Motor passa a abrir com as linhas `🖥️`
dizendo sistema, Python, onde a chave está guardada, se o Quartz está instalado
e — no Mac — **se a permissão de Gravação de Tela está concedida**. Sem essa
permissão o macOS não dá erro: ele entrega as janelas sem título e a captura sai
preta. Agora isso aparece de cara, não no meio do pregão.

> 📖 **Instalação no Mac: `INSTALAR_NO_MAC.md`**, passo a passo do zero.

### Novidades da 2.13.0

**🎯 A TIGER usa a MESMA lista de modelos do motor** — este era o defeito que
você apontou: *"de 5 em 5 minutos ele analisa normalmente usando Gemini, quando
peço pela IA ela fica inventando essa desculpa"*.

**Não era desculpa dela: eram duas listas.** O motor tentava **catorze** modelos
com cooldown e seguia lendo o gráfico com os de reserva
(`gemini-flash-lite-latest`, `gemini-3.1-flash-lite`, `gemini-3-flash-preview`).
A TIGER tinha **cinco escritos à mão no código** (quatro quando havia anexo),
**todos da família 2.0** — justamente a que o log mostrava `cota esgotada
(pausado 15min)` o dia inteiro. Acabada a lista curta, ela desistia e dizia que
a cota tinha estourado. No mesmo minuto, para o mesmo print, o motor lia.

Agora existe **um registro só**, compartilhado pelos dois:

- a lista é **descoberta na sua conta** (não é a lista fixa do código), e ela
  descobre **mesmo com o motor desligado** — antes só o motor descobria, então,
  com ele parado, ela ficava presa aos nomes fixos e perdia os de reserva que a
  sua conta tem e que funcionam;
- **cooldown compartilhado**: quem descobre que um modelo está sem cota avisa o
  outro. Cota (`429`) estaciona **15 min**; sobrecarga (`503`/timeout),
  **2 min**. O motor poupa a TIGER e a TIGER poupa o motor;
- modelo em cooldown vai para o **fim da fila, não some** — é melhor uma
  tentativa do que recusar a resposta antes de tentar;
- modelo **descontinuado** (`404`) sai de vez, dos dois lados — e a memória
  disso **não é mais apagada** a cada troca de dia;
- o modelo que **respondeu** passa a liderar a fila nos dois lados;
- com **imagem**, os `*-lite` continuam na lista (só saem em vídeo/PDF, onde
  tropeçam). É justamente o print do gráfico que ela mais precisa ler quando os
  modelos maiores estão sem cota.

E quando **realmente** não houver nenhum de pé, a resposta deixa de ser genérica:
ela diz **quantos modelos tentou** e o estado real deles — *"tentei 10 modelos,
um por um, antes de te dizer isso — todos os 10 estão sem cota agora; o primeiro
volta em ~7 min"*. Continua **sem inventar leitura de gráfico**: isso não mudou
e não vai mudar.

**🩺 Setinha ← do comprovante: âncora à prova de painel fora do lugar.** A busca
sobe do texto do comprovante até o painel do ticket. Faltava conferir que o
ancestral escolhido **contém** o comprovante — um wrapper de geometria
degenerada era aceito mesmo sendo menor que o ticket, o "topo do painel" ia
parar em outro lugar da tela e a seta caía fora da janela de busca. Resultado
possível: **entrada enviada, stop e alvo não**. Acontecia com o ticket desenhado
na parte de **baixo** da tela. Agora o ancestral só vira âncora se contiver o
ticket.

### Novidades da 2.12.0

**🪟 Vários gráficos ao mesmo tempo.** Antes era um ativo por vez, e abrir o
programa duas vezes esbarrava na **porta 3939** já ocupada pelo motor da
primeira cópia. Agora existe uma **lista de gráficos** na aba Motor, e **um
motor só** percorre todos a cada ciclo.

Como a segurança foi tratada — que é o que você pediu:

- O **estado é por janela**: cenário ativo, hash da última captura e preço
  anterior. Compartilhar isso faria o hash do MES marcar a captura do NQ como
  *"quadro congelado"*, e um cenário aberto num ativo ser fechado pelo preço do
  outro. Cada gráfico tem a sua própria memória de ciclo.
- **Erro numa janela não derruba as outras**: cada uma é analisada dentro do seu
  próprio bloco de proteção.
- A **primeira da lista é a principal**, e só ela conversa com a corretora
  (envio de ordem e leitura de posições). Sem isso, a leitura de posição da
  Tradovate poderia ser associada ao ativo da janela errada.
- A leitura guardada para o chat diz **de qual janela veio**, e fica guardada
  também **por ativo** — dá para perguntar de um sem perder a do outro.
- A janela que você já usava é **migrada sozinha** para a lista.

> ⚠️ Cada gráfico a mais **consome cota da API por ciclo**. Com a chave gratuita,
> dois gráficos a cada 5 min gastam o dobro do que um. Se a cota estourar, aumente
> o intervalo ou use chave paga.

**⚡ TIGER muito mais rápida.** Os seis feeds de notícia eram buscados **em
sequência**, com 8 s de timeout cada — até **48 segundos** antes de ela começar a
pensar, e isso acontecia em **toda** pergunta, inclusive *"o que é um order
block"*. Agora:

- os feeds são buscados **em paralelo** (o tempo passa a ser o do mais lento, não
  a soma de todos);
- **cotação e notícias** vão juntas, não uma esperando a outra;
- a internet só é consultada quando a pergunta **pede dado do momento**. Pergunta
  de metodologia responde na hora, pela base local, sem tocar na rede.

**🛡️ Trava contra lição impossível.** Dia 06/08 ela aceitou gravar *"tira um
print e leia off line se não tiver acesso a api gemini"* e respondeu **"Anotado e
aprendido"**. Ler imagem é a única coisa que depende da visão da API — **offline
não existe leitura, existe invenção**. Aquilo virou uma ordem permanente para
fabricar número de gráfico, valendo em toda análise futura. Agora ela **recusa**
lições desse tipo e explica o porquê.

> **Confira suas lições gravadas** com *"o que você aprendeu?"* e apague essa se
> ela ainda estiver lá. A regra da casa — *nunca invente número* — não pode ser
> revogada por lição.

---

### Novidade da 2.11.0 — posição aberta agora AVISA, não emudece

Você notou que ela parava de sugerir quando já havia uma operação em andamento,
inclusive aberta **na mão**. Não era trava de código: era uma frase que ia no
prompt (*"não sugira sinais em conflito direto com elas"*) e **quem decidia era
o modelo** — que generalizava para "não sugira nada". O efeito colateral era o
pior possível: quando o mercado virava **contra** a sua posição, a leitura mais
útil de todas era exatamente a que ficava calada.

Agora a decisão é de **código**, com três comportamentos:

| Situação | O que ela faz |
|---|---|
| Cenário **contra** a sua posição | **⚠️ ALERTA DE RISCO** — não vira sugestão de entrada |
| Cenário **a favor** | Sugere, marcado como **aumento de posição** |
| **Outro ativo** | Livre, sem nenhuma restrição |

O alerta traz o seu lado, o resultado atual, **o seu stop** e a leitura nova. Se
a posição estiver **sem stop registrado**, isso vem primeiro. Tem trava
anti-spam de 15 minutos, para o aviso não virar ruído.

Por que o cenário contrário **não** vira sugestão de entrada: entrar do outro
lado do que você já carrega é **hedge, não operação** — trava o prejuízo, paga
custo duas vezes e, em conta de avaliação, costuma esbarrar em regra de contratos
máximos. Quem decide proteger, reduzir, encerrar ou segurar é você; a ferramenta
garante que você **saiba**.

Configurável por conta no Plano de Trading, campo **"Já posicionado no ativo"**,
ou pela fala: *"quando eu já estiver posicionado, me avise"* · *"...sugira
normalmente"* · *"...não sugira nada"*.

---

### ⛔ LEIA ANTES: por que a 2.10.0 foi substituída

Na 2.10.0 eu criei três rotas para o robô voltar do comprovante ao formulário do
ticket. Uma delas clicava no **título do painel "Chamado do pedido"** — e na
Tradovate esse gesto **fecha o módulo**. No pregão de 06/08 às 15:45 subiu o
diálogo *"Fechar este módulo o removerá do seu espaço de trabalho"*, que é
**modal**: travou a plataforma inteira, com a ordem de entrada já enviada, e
desmontou a área de trabalho. **Foi erro meu, e essa rota já não existe.**

Regra que ficou gravada no código, para não se repetir:

> Uma rota de recuperação só pode tocar em **ícone de navegação dentro do
> painel**. Nunca em título, aba, `×`, nem em nada com atributo de
> fechar/remover/minimizar. Não conseguir voltar é ruim; **desmontar a mesa do
> trader no meio do pregão é pior**.

O que a 2.10.1 traz junto:

- A busca por "voltar" via `aria-label`/`title` **não aceita mais** `fechar`
  nem `close` — voltar e fechar não são sinônimos aqui.
- Toda escolha de clique passa por uma barreira que rejeita o título do painel,
  o `×` e atributos de fechar/remover/minimizar — **inclusive o botão em volta
  do ícone**, de nada adianta a setinha ser inofensiva se o botão que a contém
  fecha o módulo.
- Se o diálogo aparecer por **qualquer** motivo, a ferramenta o reconhece e sai
  por **CANCELAR** — nunca por OK. A resposta certa para uma confirmação que o
  robô não pediu é sempre "não".
- **A setinha volta a ser encontrada.** Ela existe (`← MESU6`), mas a busca era
  feita dentro do *menor bloco* que contém o texto do comprovante — que é a
  **tabela de eventos** da ordem. A seta fica uma linha acima, no cabeçalho,
  logo **fora** desse bloco. Agora a busca sobe até o painel do ticket.
- **Fim do martelamento.** Eram até 45 tentativas de clique por bracket
  (5 × 3 pernas × 3 rodadas). Agora são no máximo 6, e ao falhar ele **para e
  avisa** em vez de continuar batendo na plataforma.

Isto é coberto por teste automatizado com DOM simulado a partir do seu print
(`test_voltar.js`): ele confirma que a setinha é clicada, que o título e o `×`
**nunca** são tocados — mesmo quando a setinha não existe — e que o diálogo é
dispensado pelo Cancelar.

### Os quatro problemas do pregão de 05–06/08

- 🚨 **POSIÇÃO SEM STOP — o mais grave.** No log, três vezes: *"a ENTRADA foi
  enviada, mas STOP e ALVO NÃO"*. A causa era única e boba: depois de mandar a
  entrada, o painel vira **comprovante**, e o robô procurava a setinha `←` de
  volta ao formulário de **um jeito só**; não achando, desistia — com a ordem
  já no mercado. Agora existem **três caminhos independentes** de volta
  (setinha, `aria-label`/`title` de voltar, tecla **ESC** e o cabeçalho do
  *"Chamado do pedido"*), cada um **verificado de verdade** (só conta como
  volta quando o formulário reaparece), e o stop e o alvo têm **três rodadas
  completas** antes de desistir. Se mesmo assim faltar o stop, ela aponta a
  saída segura: *enquanto a entrada limitada não for preenchida, o risco é
  zero* — cancele a entrada ou ponha o stop na mão.

- 🔎 **A LEITURA DA POSIÇÃO, CORRIGIDA NA RAIZ.** A Tradovate escreve
  `POSIÇÃO 50@7730.00 62.50 USD`. O robô jogava fora o `@`, lia **507730**,
  reprovava por absurdo e repetia o pregão inteiro *"achei o rótulo POSIÇÃO mas
  não consegui ler o número ao lado"*. Agora ele lê o **bloco inteiro**:
  quantidade, **preço médio** (que antes ficava sempre nulo) e P&L — com
  parênteses valendo **prejuízo** e `-.--` valendo **ausência de valor**, não
  zero.

- 📊 **O DASHBOARD DO PLANO DE TRADING VOLTA A ACOMPANHAR.** Como a leitura
  falhava, o app concluía *"vi o ativo e não há posição"* e devolvia para
  **PENDENTE** uma ordem **já executada**, zerando o resultado real — era o
  *"↩️ Correção: NÃO está executada na plataforma"* do log. Não conseguir ler
  passou a ser tratado como **ausência de informação, nunca como conclusão**:
  o que já estava registrado continua de pé. A correção legítima (quando a
  corretora realmente mostra você zerado) **continua funcionando**.

- 🛑 **FREIO DE SUGESTÕES — o fim dos stops reiterados.** O motor reencontrava
  o mesmo cenário a cada ciclo e o dia virava sequência de perdas. Agora ela se
  comporta como mesa: **2 stops seguidos → 30 min de silêncio**; para de vez ao
  bater o **teto de operações do dia** ou o **Drawdown Máximo** do plano; e não
  vira de compra para venda no mesmo ativo sem probabilidade **acima do piso**
  (guarda **anti-chicote**, que é o padrão que faz tomar stop nas duas pontas).
  Tudo configurável por conta, na tela ou pela fala.

### E mais duas que mudam o comportamento dela

- 🧠 **AUTOAPRENDIZAGEM COM EFEITO REAL.** O que o histórico já ensinava era só
  um texto no prompt — e o modelo podia ignorar. Agora vira **número**: um
  padrão que vem falhando **nas suas operações** derruba a probabilidade do
  cenário e passa a ser barrado pelo piso; o que vem acertando ganha pontos. O
  log mostra a conta: `🧠 APRENDIZADO: probabilidade 75% → 66% (-9.0 pts pelo
  seu histórico)`. O ajuste é limitado a ±12 pontos e exige pelo menos 4
  amostras — histórico corrige a leitura, **não a substitui**.

- 💬 **ELA EXPLICA O SILÊNCIO.** Pergunte *"por que você não está sugerindo
  nada?"*, *"cadê as sugestões?"* ou *"o freio está ativo?"* e ela responde com
  os números do dia e **qual limite** está segurando.

## 1. Dependências (uma vez só)

```cmd
pip install SpeechRecognition sounddevice
```

> **NÃO instale `pyaudio`** — ele falha para compilar no Python 3.13/3.14 e
> não é necessário. O app usa o `sounddevice` para captar o microfone.

Se o `.spec` tiver a lista `hiddenimports`, garanta que contenha:

```python
hiddenimports=['speech_recognition', 'sounddevice',
               'tkinter.simpledialog', 'tkinter.filedialog'],
```

---

## 2. Rodar local primeiro (recomendado — 3 minutos)

```cmd
cd C:\Users\jovan\Documents\SMC_QUANT_PRO
python main_app.py
```

Checklist da v2.16.0 — **comece pelo primeiro**, que é o defeito desta versão.
Os itens A a D exigem a Tradovate aberta com o *"Chamado do pedido"* visível.

0. **MOTOR LÊ E TIGER LÊ (o defeito desta versão).** Com o **motor ligado** e
   analisando normalmente de 5 em 5 minutos, peça no chat **"olha o gráfico"**.
   Ela **tem que ler**. Não pode mais acontecer o que aconteceu em 06/08 e
   07/08: o motor analisando com os modelos de reserva no mesmo minuto em que
   ela respondia *"a cota da sua chave Gemini estourou"*.
   Repita com o **motor desligado** — tem que ler igual (ela descobre os
   modelos da conta sozinha agora).
   Se um dia realmente não houver nenhum modelo de pé, a resposta tem que
   trazer **quantos ela tentou** e **em quantos minutos o primeiro volta** — se
   vier só *"a cota estourou"*, sem esse número, algo ficou para trás.

A. **BRACKET COMPLETO (o mais importante).** Com a automação em modo real,
   acate um cenário e acompanhe o log. Tem que sair **ENTRADA, STOP e ALVO**.
   Se aparecer *"não achei o botão de voltar (←)"*, a linha seguinte tem que
   ser **"tentando as outras saídas do comprovante"** e, logo depois,
   **"voltei ao formulário pela …"**. O que **não pode mais acontecer** é
   parar em *"formulário não está visível"* com a entrada já enviada.

B. **LEITURA DA POSIÇÃO.** Com posição aberta, clique em **🩺 Diagnosticar
   leitura**. Na linha final, `preço_médio` **não pode mais vir `None`** quando
   a tela mostra `50@7730.00`. Confira também que um prejuízo entre parênteses
   — `(62.50) USD` — aparece **negativo**.

C. **DASHBOARD ACOMPANHA A ENTRADA.** Acate um cenário e espere o preço tocar a
   entrada. O card tem que sair de *"aguardando o preço tocar"* para
   **executada**, e **não pode mais** aparecer *"↩️ Correção: NÃO está
   executada"* logo em seguida enquanto a posição existe de verdade na tela.

D. **FREIO.** No Plano de Trading, deixe *"Stops seguidos p/ pausar"* em **2** e
   *"Pausa após stops"* em **30**. Depois de dois stops no dia, o log tem que
   mostrar **🛑 FREIO** e parar de sugerir. Pergunte no chat *"por que você não
   está sugerindo nada?"* — ela tem que responder com os números do dia e o
   limite que está segurando.

E. **APRENDIZADO NA CONTA.** Com histórico suficiente (4+ cenários do mesmo
   padrão), o log de uma sugestão tem que trazer a linha
   **🧠 APRENDIZADO: probabilidade X% → Y%**, com o motivo.

Depois siga com o checklist da v2.9.1 abaixo, que continua valendo:

00000. **OS QUATRO BURACOS DAS 22:12.** Um de cada vez:
   *"CAPTURE AGORA"* → tem que capturar, não dar o genérico.
   *"APRENDA, USE O MOTOR PARA TIRAR PRINT"* → tem que responder **"Anotado e
   aprendido"**, não tirar print.
   *"COMO ESTÁ A GESTÃO DE RISCO DA MINHA CONTA 1"* → tem que vir o número
   gravado, não a resposta do modelo.
   Com a **cota estourada**, *"tire um print novo e analise o gráfico"* → tem
   que dizer que **o print foi capturado mas ler a imagem depende da API** —
   nunca *"não está na minha base"*.

0000. **CONFIGURAR FALANDO.** Digite exatamente: *"deixa registrado que o dia
   para a conta 1 começa as 19hs"*. Ela tem que responder **"Pronto, configurei
   a ferramenta"** com o de-para (*09:00 → 19:00*) — e o campo **Início** da aba
   Motor tem que estar em **19:00**. Repita com *"configura o risco de 1% por
   operação"* e confira o campo **Risco/operação (%)** no Plano de Trading.
   Depois teste em outra conta: *"na conta 2, meta de 6 mil em 10 dias"* — tem
   que gravar **na Conta 2** e **não** mexer na Conta 1.
0000a. **CONSULTAR.** Digite *"COMO ESTÁ CONFIGURADO O RISCO DO PLANO DA CONTA
   1"* — tem que vir o número real, não o genérico. Depois *"quais são as
   minhas configurações?"* — vem o bloco da FERRAMENTA e o do PLANO DA CONTA.
0000b. **PERGUNTA NÃO CONFIGURA (importante).** Digite *"qual a meta do S&P
   hoje, 7800?"* e *"o pregão americano abre às 9:30"*. **Nada** pode mudar no
   Plano de Trading nem na aba Motor — confira os dois depois.

000. **Cortar a fala.** Peça algo longo (*"me explica o power of 3"*) com a voz
   ligada e, no meio da fala, clique em **⏹ Parar fala** — tem que parar na
   hora. Repita clicando no **🎤**, depois dizendo **"Olá Tiger"** por cima
   (modo 🐯 ligado), e por fim mandando *"para de falar"* — que **não pode**
   desligar o motor.
000a. **Ativo por voz.** Pergunte *"quanto está o smp500"* e *"como está o
   sp-500 agora"* — os dois têm que trazer o **preço real**, não o genérico.
   E *"analise meu gráfico agora"* tem que **tirar o print**, não desistir.
000b. **Cenário aplicado.** Com uma posição aberta, pergunte *"o que seria uma
   confirmação de reversão?"* — depois da teoria tem que vir *"No SEU caso
   agora: você está …"* com a sua direção, entrada e o preço real. Depois
   pergunte *"como calcular o tamanho da posição?"* — tem que vir com o seu
   stop, alvo e P&L.
00. **Fim do despejo de manchetes.** Pergunte, uma de cada vez: *"o que você
   pode fazer?"*, *"se o Fed cortar juros a bolsa cai ou sobe?"*, *"se o
   payroll vier acima do esperado o S&P sobe ou cai?"* e *"acelere a fala"*.
   Cada uma tem que receber uma **resposta diferente e específica** — nenhuma
   pode devolver lista de manchete, e nenhuma pode mostrar *"cite a fonte ao
   usar"* na tela.
0a. **Web sem cota:** pergunte *"quanto está o S&P?"* — vem o **preço real**
   com a fonte e a hora. Depois *"por que o S&P sobe hoje?"* — vêm as
   **manchetes reais** com a casa e há quantos minutos saíram. Isso funciona
   **mesmo com a cota da Gemini estourada** (dá para testar tirando a chave).
0. **O motor NÃO pode desligar sozinho.** Com o motor ligado, digite a frase
   inteira: *"não precisa acionar a cota da api para algumas analises,
   considere aprender isso"*. O motor tem que **continuar ligado**, e ela tem
   que responder *"Anotado e aprendido…"*.
0b. **Sem cota:** pergunte *"o que é um order block?"* e *"o que caracteriza um
   CHoCH?"*. A resposta sai **na hora**, da base própria — dá para conferir
   desligando a internet. Depois pergunte *"o que você sabe?"* para ver os 32
   assuntos.
1. **Aprender:** diga *"sempre confira o R:R antes de sugerir, aprenda isso"*.
   Ela responde **"Anotado e aprendido: …"**. Agora pergunte *"o que você
   aprendeu?"* — a lição tem que aparecer na lista. Feche e reabra o app e
   pergunte de novo: tem que continuar lá.
2. **Zerar:** diga *"zera o ciclo"*, responda **sim** e olhe o Plano de
   Trading — os números têm que ter zerado de verdade.
3. **Print na hora:** com o motor ligado, diga *"tira um print e vê minha
   posição"*. Ela captura e analisa **na hora** (antes mandava esperar 5 min).
4. **WhatsApp:** com o motor **desligado**, diga *"manda no whatsapp"* — ela
   tem que dizer que **não dá**, porque o motor está parado. Ligue o motor e
   repita: aí ela envia (ou diz o motivo exato da falha).
5. Com o motor desligado, pergunte *"você está acompanhando o mercado?"* — ela
   deve dizer que **não**.
6. Diga **"liga o motor"** e confira na aba Motor que ligou mesmo.
7. Pergunte **"quanto precisamos fazer por dia?"** — resposta **inteira**, com
   o número fechado.
8. Repita 1, 2, 3 e 6 **por voz**, com o modo 🐯 OLÁ TIGER ligado.

> Se aparecer *"estou escutando pelo microfone X mas não chega som nenhum"*, é
> microfone errado selecionado no Windows — troque em *Configurações → Sistema
> → Som* e desligue/religue o checkbox.

---

## 3. Compilar (fluxo padrão — pelo `.spec`)

```cmd
cd C:\Users\jovan\Documents\SMC_QUANT_PRO
rd /s /q build
rd /s /q dist
python -m PyInstaller SMC_Quant_Pro.spec
```

O executável sai em: `dist\SMC_Quant_Pro.exe`

> **Sobre o `icone.ico`:** se o PyInstaller reclamar `Icon input file ... not
> found`, confira que o `icone.ico` está na pasta do projeto — ou troque
> `icon='icone.ico'` por `icon=None` no `.spec`.

---

## 4. Montar a pasta `dist` completa

```cmd
xcopy /E /I /Y motor dist\motor
```

```
dist\
  SMC_Quant_Pro.exe
  motor\
    index.js
    package.json
    node_modules\
```

> Confirme que `dist\motor\node_modules` existe. Sem ele, o WhatsApp não sobe
> na máquina do cliente.

---

## 5. Testar o executável

```cmd
dist\SMC_Quant_Pro.exe
```

Repita o checklist do passo 2 dentro do `.exe`.

---

## 6. Gerar o instalador (Inno Setup)

1. Abra `instalador\SMC_Quant_Pro.iss` no Inno Setup Compiler.
2. Confira que `MyAppVersion` está **"2.16.0"** (já está).
3. Pressione **F9** (Compile).

Sai em `instalador\Output\SMC_Quant_Pro_Setup_2.16.0.exe`.

---

## 7. Publicar a atualização

1. Suba o `SMC_Quant_Pro_Setup_2.16.0.exe` na pasta do Google Drive.
2. O `versao.json` **já está publicado como 2.16.0** — assim que o arquivo
   estiver no Drive, os clientes veem o aviso de nova versão.

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "A cota da sua chave Gemini estourou" | limite do plano gratuito | espere ou cole uma chave paga — mas metodologia, cotação e notícia ela responde igual, sem a API |
| "Não consegui alcançar as fontes de notícia" | internet ou firewall | as fontes são RSS público e o Yahoo Finance; libere o acesso ou tente de novo |
| "Não vou chutar um número" | ativo fora da lista dela | ela cobre S&P, Nasdaq, Dow, Russell, VIX, ouro, prata, petróleo, dólar, euro, bitcoin, Ibovespa e juros 10a |
| Ela respondeu outro assunto | pergunta ambígua para a base | diga "não foi isso que perguntei" — isso bloqueia a base e força resposta nova |
| Ela responde teoria quando eu quero o gráfico | pergunta sem referência ao agora | diga "agora", "nesse gráfico" ou "minha posição" — aí ela usa a API e olha o print |
| O motor desligou sozinho | era o bug do "para" (v2.4 e antes) | corrigido desde a v2.5.0; se voltar a acontecer, me mande a frase exata que você digitou |
| Ela não configurou o que pedi | frase sem verbo de comando | comece com um verbo — "configura", "muda", "ajusta", "define", "deixa registrado que…". Perguntar **nunca** configura, de propósito |
| Ela disse "NÃO consegui aplicar a configuração" | o arquivo não gravou | é a guarda funcionando (ela releu o disco e o valor era o antigo): ajuste na mão — horário e intervalo na aba Motor, os números no Plano de Trading |
| Configurou na conta errada | conta não citada na frase | ela usa a **conta selecionada** quando você não cita nenhuma; diga "na conta 2" para gravar em outra |
| Mudei o horário e o motor ignorou | motor lê o pregão a cada ciclo | vale no **próximo ciclo** (até 15 min, conforme o intervalo) — não precisa reiniciar |
| "A chave da Gemini foi recusada" | chave errada/expirada | cole a chave de novo na aba Motor e ligue o motor uma vez para salvar |
| "Não consegui alcançar o servidor" | internet | verifique a conexão — o chat e a transcrição de voz usam a rede |
| Ela diz que não tem print do gráfico | motor nunca rodou um ciclo | ligue o motor e espere uma análise, ou mande um print pelo 📎 |
| Ela não liga o motor quando peço | frase sem o substantivo | diga "liga **o motor**" / "desliga **o robô**" — só o verbo não vale, de propósito |
| A lição não foi gravada | frase sem o gatilho | termine com "**aprenda isso**" (ou comece com "aprenda:") e confira com "o que você aprendeu?" |
| Aparece "Só um ajuste importante…" | ela tentou alegar uma ação que não fez | é a guarda funcionando: use o comando que ela indica (zera o ciclo, manda no whatsapp…) |
| "manda no whatsapp" não envia | motor desligado ou QR não lido | ligue o motor e leia o QR code na aba Motor |
| "zera o ciclo" não zerou | o plano não gravou | ela avisa e diz o motivo; dá para zerar no botão "Reiniciar Ciclo" do Plano de Trading |
| "não chega som nenhum" no chat | microfone errado no Windows | *Configurações → Sistema → Som* → escolha o mic certo como entrada padrão |
| "não consegui abrir o microfone" | outro programa segurando o mic | feche Zoom/Meet/OBS e religue o OLÁ TIGER |
| Ela ouve mas não reage ao chamado | fala rápida demais no começo | diga "Olá Tiger" e faça uma pausa curta antes do pedido |
| 🎤 diz "voz não instalada" | faltam as libs de voz | `pip install SpeechRecognition sounddevice` e recompile |
| Anexo grande demora | vídeo processando no servidor | é normal; o status mostra "enviando/lendo o arquivo" |
| `Icon input file ... not found` | `icone.ico` fora da pasta | recoloque o `icone.ico` ou use `icon=None` no `.spec` |
| `ModuleNotFoundError: tradovate_auto` | `.spec` sem o módulo | confira `datas`/`hiddenimports` do `.spec` |
| App abre e fecha na hora | erro na inicialização | rode `dist\SMC_Quant_Pro.exe` pelo `cmd` para ver a mensagem |
| WhatsApp não conecta no cliente | `node_modules` faltando | confira o passo 4 (`dist\motor\node_modules`) |
| Build antigo "grudado" | cache do PyInstaller | é para isso que servem os `rd /s /q build` e `rd /s /q dist` |
