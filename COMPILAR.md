# Como compilar o SMC Quant Pro v2.9.0 (TIGER)

> **Resumo:** o processo de build **não mudou**. É o mesmo fluxo do `.spec`
> que você já usa. Nesta versão só o `main_app.py` mudou — substitua-o e compile.

---

## 0. O que mudou nesta versão

- `main_app.py` ← **único arquivo alterado**

O **motor NÃO mudou** — reaproveite a pasta `motor\` com o `node_modules` que
você já tem. O `tradovate_auto.py` também não mudou.

Novidades da v2.9.0 (aba 🐯 TIGER) — **ela configura a própria ferramenta,
falando**:

- ⚙️ **VOCÊ MANDA, ELA CONFIGURA.** *"deixa registrado que o dia para a conta 1
  começa as 19hs"* caía no genérico *"não tenho como responder isso com
  segurança"*. Agora ela configura de verdade, em português:
  - **horário do seu dia** — *"o dia da conta 1 começa às 19h"*, *"o pregão vai
    das 19h às 23h"*, *"muda o fim do dia para 17:30"*;
  - **ritmo das análises** — *"analisa a cada 5 minutos"*;
  - **os números do Plano de Trading da conta** — margem, meta, prazo da meta,
    drawdown máximo, risco por operação, R:R mínimo, probabilidade mínima,
    prazo para acatar e início do ciclo: *"risco de 1% por operação"*, *"meta de
    6 mil em 10 dias"*, *"drawdown máximo de 2000"*, *"R:R mínimo 1:3"*.
  Se você citar a conta (*"na conta 2"*), é **naquela conta** que grava.
- 🔎 **E CONSULTA.** *"COMO ESTÁ CONFIGURADO O RISCO DO PLANO DA CONTA 1"* dava
  a mesma resposta genérica. Agora ela **lê o arquivo** e mostra o que está
  gravado — da conta que você citar.
- ✅ **A REGRA DA CASA VALE AQUI TAMBÉM:** ela **grava, relê o arquivo do disco
  e só então confirma**, mostrando **o valor de antes e o de depois**. Se a
  releitura não bater, ela diz que **NÃO** conseguiu, em vez de dizer que fez.
  Cada mudança também entra no **log do motor**.
- 🖥️ **A tela acompanha o arquivo:** o campo de horário, o intervalo e os
  campos do Plano de Trading são atualizados junto — assim o botão **Ligar**
  não regrava o valor antigo por cima.
- ⏱️ **O motor relê o horário a cada ciclo:** dá para mudar o pregão com o motor
  **ligado**, sem reiniciar. E **pregão que vira o dia** (19h às 02h) passou a
  ser aceito.
- 🛡️ **A trava de segurança continua:** **pergunta NUNCA configura nada**.
  *"qual a meta do S&P hoje, 7800?"*, *"o pregão americano abre às 9:30"* e
  *"qual o risco disso?"* continuam sendo conversa — só muda a configuração
  quem manda mudar.

Continua valendo tudo da v2.8.1 — **ela lê o seu cenário e você pode
cortá-la no meio da fala**:

- 🎯 **Fim da resposta de manual.** A teoria da base agora vem **amarrada ao que
  está na sua mesa**. Com uma venda aberta contra o movimento, *"o que seria uma
  confirmação de reversão?"* responde as 4 etapas **e** completa: *"no SEU caso,
  você está vendido em 7700.25 e o preço está em 7745.65 — essa posição está
  CONTRA o movimento, então confira uma a uma as etapas acima"*. Pergunta sobre
  tamanho de posição vem com **o seu stop, o seu alvo, o seu P&L** e o ritmo por
  dia que o plano exige. Macro vem ancorada no **preço real**, com a fonte.
  Sem posição, usa a última leitura do gráfico. Sem cenário, volta ao texto
  puro — **nunca inventa ligação**.
- ⏹ **BOTÃO "PARAR FALA"** na barra do chat — o que faltava. Um clique e ela
  cala na hora, sem esperar o fim do parágrafo. Fica sempre à vista.
- 🔇 **Fala interrompível por 4 caminhos.** A escuta **pausava** enquanto ela
  falava — por isso era impossível cortá-la. Agora ela **continua ouvindo
  durante a própria fala** (filtrando o eco) e para quando você:
  - clica em **⏹ Parar fala**;
  - diz **"Olá Tiger"** por cima;
  - clica no botão **🎤**;
  - manda **"para de falar"** / *"silêncio"* / *"chega"*.
  Uma fala nova também cancela a anterior.
- 🎙️ **O ativo sobrevive à transcrição torta.** *"smp500"*, *"sp-500"*,
  *"s&p 500"* e *"nasdac"* recebiam *"não tenho como responder"* — para uma
  cotação que a ferramenta tinha na mão. A busca do ativo agora tem 3 passadas
  (exata, sem pontuação e por semelhança com corte alto — **euro e ouro não se
  confundem**).
- 🖼️ **"Analise meu gráfico agora" captura na hora.** Sem print guardado ela
  caía no genérico; agora tira o print na hora e, se nem isso der, diz
  exatamente o que fazer (ligar o motor, conferir a janela, ou mandar pelo 📎).
- 🔴 **CORREÇÃO:** *"como confirmar uma reversão"* caía no tópico de
  **recessão** — as duas palavras são quase idênticas para o casamento por som.
  Agora quem casa **exato** sempre ganha de quem só se parece.

Da v2.7 (junto nesta entrega) — **ela responde, em vez de despejar
manchete**:

- 🔴 **CORREÇÃO — o despejo de manchetes.** Tudo que não estava na base virava
  a **mesma lista de seis manchetes**: *"o que você pode fazer?"*, *"acelere a
  fala"*, *"se o Fed cortar juros a bolsa sobe?"* — todas recebiam o mesmo
  despejo. E ele ainda mostrava na tela o **texto interno do prompt** do modelo
  (*"cite a fonte ao usar…"*), que é bastidor. Agora existe um **roteador de
  resposta** que tenta, nesta ordem: o que ela mesma faz → base própria →
  cotação real → notícia relevante — e **só responde quando tem o que dizer**.
- 🧠 **Base MACRO nova: 12 assuntos, offline e sem cota.** Corte de juros do Fed
  e a bolsa; payroll acima/abaixo do esperado; inflação e CPI; juro de 10 anos e
  dólar; FOMC e dot plot; VIX; temporada de balanços; petróleo; recessão e
  ciclo; PMI/ISM; como operar em dia de notícia; correlação entre ativos. Cada
  um com **o porquê e a exceção** — nunca promessa de direção.
- 📰 **Notícia virou resposta:** as casas se revezam (antes vinham 6 seguidas da
  mesma), manchete repetida é colapsada, *"qual a mais impactante?"* ordena por
  **peso de mercado** em vez de horário, e citar uma casa filtra por ela.
- 🗣️ **"Acelere a fala"** agora muda a velocidade da voz de verdade, e o ajuste
  fica salvo entre sessões.
- 💬 **"O que você pode fazer?"** tem resposta completa e exata, sem modelo.

- 🌐 **Janela para a web SEM chave de API.** A ferramenta vai à internet por
  conta própria — não passa pela Gemini, não gasta cota, não precisa de plano:
  - **Cotação real** (Yahoo Finance): preço, variação do dia, máxima e mínima.
  - **Notícia fresca** de 6 casas: Yahoo, CNBC, Investing, MarketWatch, Nasdaq
    e InfoMoney — sempre com **a fonte e a hora**.
  - **Busca aberta** para o resto.
  Antes ela explicava a alta do S&P com *"dados de inflação e resultados de
  tecnologia"* **sem ter lido manchete nenhuma**. Agora ou tem a manchete real e
  cita de onde veio, ou diz que não conseguiu buscar.
- **Esses dados também vão para o modelo**, então até a resposta que usa a API
  fica amarrada ao número verdadeiro.
- **Comandos novos, todos sem cota:** *"por que o S&P sobe hoje?"*, *"quanto
  está o ouro"*, *"cotação do dólar"*, *"pesquisa na internet sobre X"*.
- 🔴 **CORREÇÃO — resposta de outro assunto, repetida.** *"O que seria uma
  confirmação de reversão?"* recebia a resposta de **Confluência**, e repetia o
  mesmo texto quando você corrigia. A base ganhou nota mínima e desempate
  (palavra genérica nunca mais decide sozinha), entrou o tópico **Confirmação de
  reversão** com as 4 etapas, e a sua correção agora **bloqueia a base** e força
  resposta nova.
- **Ordem explícita das fontes:** base própria de SMC → web → raciocínio.
  Nunca invenção.

- 🔴 **CORREÇÃO CRÍTICA — o motor desligava sozinho.** A frase *"não precisa
  acionar a cota da API **para** algumas **análises**"* foi entendida como
  "**parar** as análises" e **desligou o motor no meio do pregão**. O "para"
  era preposição. Agora o verbo precisa estar **grudado** no substantivo
  (*"desliga o motor"*), negação não vira comando (*"não desliga o motor"*), e o
  "para" ambíguo só conta como verbo no começo da fala ou depois de vírgula.
- **Base de conhecimento SMC nativa: 32 assuntos gravados dentro do programa.**
  Estrutura (BOS, CHoCH, MSS), order blocks (com breaker e mitigation),
  ineficiências (FVG, iFVG, BPR), liquidez (BSL/SSL, topos iguais, inducement,
  PDH/PDL, turtle soup, judas swing), precificação (premium/discount, OTE),
  Power of 3, killzones, SMT, dealing range, e a parte de gestão (R:R, stop,
  alvo, tamanho de posição, drawdown, win rate, checklist, quando não operar).
  Pergunta de metodologia é respondida **na hora, sem tocar na API** e até
  **sem internet**. A cota fica reservada para o que é do momento.
- **Cota estourada deixa de ser resposta vazia** — ela responde do próprio
  conhecimento e avisa que a API está fora.
- **Entende a transcrição torta da voz**: *"bola do Choque"* acha CHoCH.
- **É treinável**: a lição que você grava com *"aprenda isso"* entra junto na
  resposta da base. Pergunte *"o que você sabe?"* para ver a lista inteira.
- **Aprendizado mais esperto**: aceita `aprenda:`, *"…, aprenda isso"* no fim, e
  *"considere aprender isso"* com justificativa depois.

Das v2.3/v2.4, que vieram junto: liga/desliga o motor de verdade, enxerga o
último print, pesquisa na internet, guarda anti-mentira nas respostas do
modelo, *"zera o ciclo"*, *"manda no whatsapp"*, *"tira um print"*, e respostas
que não saem mais cortadas no meio da conta.

---

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

Checklist da v2.9.0 (aba **🐯 TIGER**) — comece pelos três primeiros, que são
os erros do pregão de 04/08:

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
2. Confira que `MyAppVersion` está **"2.9.0"** (já está).
3. Pressione **F9** (Compile).

Sai em `instalador\Output\SMC_Quant_Pro_Setup_2.9.0.exe`.

---

## 7. Publicar a atualização

1. Suba o `SMC_Quant_Pro_Setup_2.9.0.exe` na pasta do Google Drive.
2. O `versao.json` **já está publicado como 2.9.0** — assim que o arquivo
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
