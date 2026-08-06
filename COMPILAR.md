# Como compilar o SMC Quant Pro v2.10.1 (TIGER)

> **Resumo:** o processo de build **não mudou**. É o mesmo fluxo do `.spec`
> que você já usa. Nesta versão mudaram **dois** arquivos — substitua os dois
> e compile.

---

## 0. O que mudou nesta versão

- `main_app.py` ← alterado
- `tradovate_auto.py` ← **alterado** (leitura de posição e envio do bracket)

O **motor NÃO mudou** — reaproveite a pasta `motor\` com o `node_modules` que
você já tem.

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

Checklist da v2.10.1 — **comece pelos cinco primeiros**, que são os problemas
do pregão de 05–06/08. Os quatro primeiros exigem a Tradovate aberta com o
*"Chamado do pedido"* visível.

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
2. Confira que `MyAppVersion` está **"2.10.1"** (já está).
3. Pressione **F9** (Compile).

Sai em `instalador\Output\SMC_Quant_Pro_Setup_2.10.1.exe`.

---

## 7. Publicar a atualização

1. Suba o `SMC_Quant_Pro_Setup_2.10.1.exe` na pasta do Google Drive.
2. O `versao.json` **já está publicado como 2.10.1** — assim que o arquivo
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
