# Como compilar o SMC Quant Pro v2.2.0 (TIGER)

> **Resumo:** o processo de build **não mudou**. É o mesmo fluxo do `.spec`
> que você já usa. Nesta versão só o `main_app.py` mudou — substitua-o e compile.

---

## 0. O que mudou nesta versão

- `main_app.py` ← **único arquivo alterado**

O **motor NÃO mudou** — reaproveite a pasta `motor\` com o `node_modules` que
você já tem. O `tradovate_auto.py` também não mudou.

Novidades da v2.2.0 (aba 🐯 TIGER):
- O chamado agora é **"Olá Tiger"** e o reconhecimento ficou **tolerante**:
  aceita as variações que a transcrição devolve (Tigre, taiguer, tigger…).
- A escuta ficou **visível**: tudo o que ela ouve aparece no chat, e se algo
  falhar (internet, microfone mudo) ela **diz o motivo** em vez de ficar calada.
- Novo botão **📎 Anexar**: mande prints, fotos, **vídeos** da tela, PDFs e
  planilhas (até ~1,9 GB) para a TIGER analisar.

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

## 2. Rodar local primeiro (recomendado — 2 minutos)

```cmd
cd C:\Users\jovan\Documents\SMC_QUANT_PRO
python main_app.py
```

Checklist da v2.2.0 (aba **🐯 TIGER**):

1. Marque **🐯 OLÁ TIGER**. Ela escreve no chat qual **microfone** está usando —
   confira que é o seu. Se não for, troque o dispositivo de entrada padrão em
   *Configurações → Sistema → Som* e desligue/religue o checkbox.
2. Fale qualquer coisa perto do microfone. **Tudo o que ela ouvir aparece no
   chat** (`🐯 ouvi: "..."`). É assim que você confirma que a escuta está viva.
3. Diga **"Olá Tiger, qual o status?"** — ela responde falando.
4. Diga só **"Olá Tiger"** — ela responde "Oi! Pode falar" e abre o microfone.
5. Clique em **📎 Anexar**, escolha um print do gráfico, aperte Enter — ela lê
   a imagem e comenta. Repita com um **vídeo** curto da tela.

> Se aparecer *"estou escutando pelo microfone X mas não chega som nenhum"*, é
> microfone errado selecionado no Windows — o passo 1 resolve.

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
2. Confira que `MyAppVersion` está **"2.2.0"** (já está).
3. Pressione **F9** (Compile).

Sai em `instalador\Output\SMC_Quant_Pro_Setup_2.2.0.exe`.

---

## 7. Publicar a atualização

1. Suba o `SMC_Quant_Pro_Setup_2.2.0.exe` na pasta do Google Drive.
2. O `versao.json` **já está publicado como 2.2.0** — assim que o arquivo
   estiver no Drive, os clientes veem o aviso de nova versão.

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "não chega som nenhum" no chat | microfone errado no Windows | *Configurações → Sistema → Som* → escolha o mic certo como entrada padrão |
| "não consegui transcrever" | sem internet | a transcrição da voz usa a internet; verifique a conexão |
| "não consegui abrir o microfone" | outro programa segurando o mic | feche Zoom/Meet/OBS e religue o OLÁ TIGER |
| Ela ouve mas não reage ao chamado | fala rápida demais no começo | diga "Olá Tiger" e faça uma pausa curta antes do pedido |
| 🎤 diz "voz não instalada" | faltam as libs de voz | `pip install SpeechRecognition sounddevice` e recompile |
| Anexo grande demora | vídeo processando no servidor | é normal; o status mostra "enviando/lendo o arquivo" |
| `Icon input file ... not found` | `icone.ico` fora da pasta | recoloque o `icone.ico` ou use `icon=None` no `.spec` |
| `ModuleNotFoundError: tradovate_auto` | `.spec` sem o módulo | confira `datas`/`hiddenimports` do `.spec` |
| App abre e fecha na hora | erro na inicialização | rode `dist\SMC_Quant_Pro.exe` pelo `cmd` para ver a mensagem |
| WhatsApp não conecta no cliente | `node_modules` faltando | confira o passo 4 (`dist\motor\node_modules`) |
| Build antigo "grudado" | cache do PyInstaller | é para isso que servem os `rd /s /q build` e `rd /s /q dist` |
