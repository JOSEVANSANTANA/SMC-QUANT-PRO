# Como compilar o SMC Quant Pro v2.1.2 (TIGER)

> **Resumo:** o processo de build **não mudou**. É o mesmo fluxo do `.spec`
> que você já usa. Nesta versão só o `main_app.py` mudou — substitua-o e compile.

---

## 0. O que mudou nesta versão

- `main_app.py` ← **único arquivo alterado**

O **motor NÃO mudou** — reaproveite a pasta `motor\` com o `node_modules` que
você já tem. O `tradovate_auto.py` também não mudou.

Novidades da v2.1.2 (aba 🐯 TIGER):
- A IA agora se chama **TIGER** e tem palavra de ativação: ligue o checkbox
  **🐯 EI TIGER (sempre à escuta)** e chame por voz: *"Ei Tiger, qual o status?"*
- Voz **natural**: ela não lê mais asteriscos/símbolos das respostas.
- Microfone **paciente**: só encerra ~2 s depois que você para de falar.
- Pedido por **voz** → resposta por **voz** (sempre, com o texto no histórico).
- Chat não embaralha mais mensagens e responde mais rápido.
- Cabeçalho do chat mostra a **conta selecionada** — a TIGER orienta pelo
  plano de trading DELA.

---

## 1. Dependências de voz (uma vez só)

A voz usa `SpeechRecognition` + `sounddevice` (funciona em qualquer Python,
inclusive 3.13/3.14):

```cmd
pip install SpeechRecognition sounddevice
```

> **NÃO instale `pyaudio`** — ele falha para compilar no Python 3.13/3.14 e
> não é necessário. O app usa o `sounddevice` para captar o microfone.

Se o `.spec` tiver a lista `hiddenimports`, garanta que contenha:

```python
hiddenimports=['speech_recognition', 'sounddevice', 'tkinter.simpledialog'],
```

---

## 2. Rodar local primeiro (opcional, recomendado)

```cmd
cd C:\Users\jovan\Documents\SMC_QUANT_PRO
python main_app.py
```

Checklist rápido da v2.1.2 (aba **🐯 TIGER**):
- O cabeçalho mostra **🏦 <nome da conta ativa>**; troque de conta no Plano de
  Trading e veja o aviso "(conversa agora vinculada à conta ...)" no chat.
- Clique no **🎤 Falar**, faça uma pergunta LONGA com pausas — ela espera você
  terminar (corta só após ~2 s de silêncio).
- A resposta de um pedido por voz **sai falada** (mesmo com o 🔊 desmarcado).
- Marque **🐯 EI TIGER** e diga *"Ei Tiger, status"* — ela executa direto.
- A voz não fala "asterisco" em nenhuma resposta.

---

## 3. Compilar (fluxo padrão — pelo `.spec`)

```cmd
cd C:\Users\jovan\Documents\SMC_QUANT_PRO
rd /s /q build
rd /s /q dist
python -m PyInstaller SMC_Quant_Pro.spec
```

O executável sai em: `dist\SMC_Quant_Pro.exe`

> **Sobre o `icone.ico`:** o arquivo está no pacote (foi recriado na v2.1.1).
> Se o PyInstaller reclamar `Icon input file ... not found`, confira que o
> `icone.ico` está na pasta do projeto — ou troque `icon='icone.ico'` por
> `icon=None` no `.spec`.

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

Repita o checklist do passo 2 dentro do `.exe` (principalmente o 🎤 e o
modo EI TIGER).

---

## 6. Gerar o instalador (Inno Setup)

1. Abra `instalador\SMC_Quant_Pro.iss` no Inno Setup Compiler.
2. Confira que `MyAppVersion` está **"2.1.2"** (já está).
3. Pressione **F9** (Compile).

Sai em `instalador\Output\SMC_Quant_Pro_Setup_2.1.2.exe`.

---

## 7. Publicar a atualização

1. Suba o `SMC_Quant_Pro_Setup_2.1.2.exe` na pasta do Google Drive.
2. O `versao.json` **já está publicado como 2.1.2** — assim que o arquivo
   estiver no Drive, os clientes veem o aviso de nova versão.

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| 🎤 diz "voz não instalada" | faltam as libs de voz | `pip install SpeechRecognition sounddevice` e recompile |
| EI TIGER não reage | checkbox desligado ou sem internet | ligue o 🐯 na aba TIGER; a transcrição usa a internet |
| Voz corta sua fala | ambiente MUITO barulhento | fale um pouco mais perto do microfone |
| `Icon input file ... not found` | `icone.ico` fora da pasta | recoloque o `icone.ico` ou use `icon=None` no `.spec` |
| `ModuleNotFoundError: tradovate_auto` | `.spec` sem o módulo | confira `datas`/`hiddenimports` do `.spec` |
| App abre e fecha na hora | erro na inicialização | rode `dist\SMC_Quant_Pro.exe` pelo `cmd` para ver a mensagem |
| WhatsApp não conecta no cliente | `node_modules` faltando | confira o passo 4 (`dist\motor\node_modules`) |
| Build antigo "grudado" | cache do PyInstaller | é para isso que servem os `rd /s /q build` e `rd /s /q dist` |
