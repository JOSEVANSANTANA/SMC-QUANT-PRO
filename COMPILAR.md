# Como compilar o SMC Quant Pro v2.3.0 (TIGER)

> **Resumo:** o processo de build **não mudou**. É o mesmo fluxo do `.spec`
> que você já usa. Nesta versão só o `main_app.py` mudou — substitua-o e compile.

---

## 0. O que mudou nesta versão

- `main_app.py` ← **único arquivo alterado**

O **motor NÃO mudou** — reaproveite a pasta `motor\` com o `node_modules` que
você já tem. O `tradovate_auto.py` também não mudou.

Novidades da v2.3.0 (aba 🐯 TIGER):

- **Ela liga e desliga o motor.** Diga *"liga o motor"* ou *"desliga o robô"* e
  ela chama o mesmo botão da aba Motor — e depois **confirma** se subiu mesmo.
  Antes o modelo respondia "motor ligado" sem ligar nada.
- **Ela enxerga o gráfico.** Cada captura do motor fica salva; peça *"olha o
  gráfico"* e ela analisa a **mesma imagem** que gerou a sugestão.
- **Ela pesquisa na internet** (notícia, agenda econômica, dado macro) e diz de
  onde tirou.
- **Fim das respostas cortadas** no meio da conta ("faltam 7.6"). O teto de
  saída subiu, o "raciocínio interno" que comia esse teto foi zerado, e se ainda
  assim bater no limite ela pede a continuação e emenda sozinha.
- **Perguntas viraram conversa de novo.** "Como está a situação?" não devolve
  mais o card fixo — ela responde pensando, com o **ritmo exigido por dia** já
  calculado e o detalhe das posições abertas.
- **Falha com motivo.** Em vez de "sem acesso à rede", ela diz se foi **cota da
  chave**, **chave recusada** ou **internet**.

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

Checklist da v2.3.0 (aba **🐯 TIGER**):

1. Com o motor **desligado**, pergunte *"você está acompanhando o mercado?"* —
   ela deve dizer que **não**, porque o motor está parado, e oferecer ligar.
2. Diga **"liga o motor"**. Ela avisa que está ligando e, quando o motor sobe,
   escreve *"Motor no ar"*. Confira na aba Motor que ligou mesmo.
3. Espere um ciclo de análise e peça **"olha o gráfico"** — ela analisa o print
   que o motor capturou e diz de que horas é a captura.
4. Pergunte **"quanto precisamos fazer por dia para bater a meta?"** — a
   resposta tem que vir **inteira**, com o número fechado (esse era o bug).
5. Pergunte algo que só a internet responde: *"tem notícia de CPI hoje?"*.
6. Diga **"desliga o motor"** e confirme que ele parou.
7. Repita 2, 3 e 6 **por voz**, com o modo 🐯 OLÁ TIGER ligado.

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
2. Confira que `MyAppVersion` está **"2.3.0"** (já está).
3. Pressione **F9** (Compile).

Sai em `instalador\Output\SMC_Quant_Pro_Setup_2.3.0.exe`.

---

## 7. Publicar a atualização

1. Suba o `SMC_Quant_Pro_Setup_2.3.0.exe` na pasta do Google Drive.
2. O `versao.json` **já está publicado como 2.3.0** — assim que o arquivo
   estiver no Drive, os clientes veem o aviso de nova versão.

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "A cota da sua chave Gemini estourou" | limite do plano gratuito | espere alguns minutos ou cole uma chave paga na aba Motor |
| "A chave da Gemini foi recusada" | chave errada/expirada | cole a chave de novo na aba Motor e ligue o motor uma vez para salvar |
| "Não consegui alcançar o servidor" | internet | verifique a conexão — o chat e a transcrição de voz usam a rede |
| Ela diz que não tem print do gráfico | motor nunca rodou um ciclo | ligue o motor e espere uma análise, ou mande um print pelo 📎 |
| Ela não liga o motor quando peço | frase sem o substantivo | diga "liga **o motor**" / "desliga **o robô**" — só o verbo não vale, de propósito |
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
