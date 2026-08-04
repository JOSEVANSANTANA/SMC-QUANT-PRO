# Como compilar o SMC Quant Pro v2.6.0 (TIGER)

> **Resumo:** o processo de build **não mudou**. É o mesmo fluxo do `.spec`
> que você já usa. Nesta versão só o `main_app.py` mudou — substitua-o e compile.

---

## 0. O que mudou nesta versão

- `main_app.py` ← **único arquivo alterado**

O **motor NÃO mudou** — reaproveite a pasta `motor\` com o `node_modules` que
você já tem. O `tradovate_auto.py` também não mudou.

Novidades da v2.6.0 (aba 🐯 TIGER) — **ela busca o dado sozinha e para de
inventar**:

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

Checklist da v2.6.0 (aba **🐯 TIGER**) — comece pelos dois primeiros, que são
os erros do pregão de 04/08:

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
2. Confira que `MyAppVersion` está **"2.6.0"** (já está).
3. Pressione **F9** (Compile).

Sai em `instalador\Output\SMC_Quant_Pro_Setup_2.6.0.exe`.

---

## 7. Publicar a atualização

1. Suba o `SMC_Quant_Pro_Setup_2.6.0.exe` na pasta do Google Drive.
2. O `versao.json` **já está publicado como 2.6.0** — assim que o arquivo
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
| O motor desligou sozinho | era o bug do "para" (v2.4 e antes) | corrigido na v2.6.0; se voltar a acontecer, me mande a frase exata que você digitou |
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
