# Como compilar o SMC Quant Pro v1.8.0

Passo a passo para gerar o `.exe` e o instalador na sua máquina Windows.

---

## 0. Antes de começar

Confirme que estes arquivos estão na pasta do projeto (`C:\Users\jovan\Documents\SMC_QUANT_PRO`):

- `main_app.py` (v1.8.0)
- `tradovate_auto.py` (v1.8.0 — agora com a leitura de posições)
- pasta `motor\` (com `index.js` e `node_modules`)
- `icone.ico` (se você usa ícone próprio)

> **O motor NÃO mudou** nesta versão. Se você já tem a pasta `motor\` com
> `node_modules` de uma build anterior, pode reaproveitá-la inteira.

---

## 1. Rodar local primeiro (recomendado, sem compilar)

Vale conferir tudo rodando antes de gastar tempo compilando:

```cmd
cd C:\Users\jovan\Documents\SMC_QUANT_PRO
python main_app.py
```

Checklist rápido:
- A barra **🏦 CONTA** aparece no topo da aba *Plano de Trading*.
- Seus dados atuais aparecem normalmente (viraram a **Conta 1**).
- **➕ Nova** cria uma conta; ao trocar, os KPIs/gráficos zeram para a conta nova.
- Voltando para a **Conta 1**, tudo reaparece como antes.

---

## 2. Instalar as dependências de build

```cmd
pip install --upgrade pyinstaller customtkinter pillow pyttsx3 requests google-genai pywin32
```

---

## 3. Gerar o executável (PyInstaller)

Um único comando, dentro da pasta do projeto:

```cmd
cd C:\Users\jovan\Documents\SMC_QUANT_PRO
pyinstaller --noconfirm --onefile --windowed ^
  --name SMC_Quant_Pro ^
  --icon icone.ico ^
  --add-data "tradovate_auto.py;." ^
  --hidden-import win32timezone ^
  --hidden-import PIL._tkinter_finder ^
  main_app.py
```

Sem ícone próprio? Remova a linha `--icon icone.ico`.

O executável sai em: `dist\SMC_Quant_Pro.exe`

---

## 4. Montar a pasta `dist` completa

O instalador copia **tudo** que estiver em `dist\`. Coloque a pasta do motor ao
lado do `.exe`:

```cmd
xcopy /E /I /Y motor dist\motor
```

A `dist` deve ficar assim:

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

Repita o checklist do passo 1. Vale testar também:
- **🔎 Detectar posições agora** (aba *Motor & WhatsApp*, painel Tradovate) com o
  Chrome aberto pelo botão do app e o painel de posições visível na Tradovate.

---

## 6. Gerar o instalador (Inno Setup)

1. Abra `instalador\SMC_Quant_Pro.iss` no Inno Setup Compiler.
2. Confira que `MyAppVersion` está **"1.8.0"** (já está).
3. Pressione **F9** (Compile).

O instalador sai em `instalador\Output\SMC_Quant_Pro_Setup_1.8.0.exe`.

---

## 7. Publicar a atualização

1. Suba o `SMC_Quant_Pro_Setup_1.8.0.exe` na pasta do Google Drive.
2. O `versao.json` **já está publicado como 1.8.0** — assim que o arquivo estiver
   no Drive, os clientes verão o aviso de nova versão e o botão de download.

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `ModuleNotFoundError: tradovate_auto` no .exe | faltou o `--add-data` | refaça o passo 3 com a linha `--add-data "tradovate_auto.py;."` |
| App abre e fecha na hora | erro na inicialização | rode `dist\SMC_Quant_Pro.exe` a partir do `cmd` para ver a mensagem |
| WhatsApp não conecta no cliente | `node_modules` faltando | confira o passo 4 (`dist\motor\node_modules`) |
| "Não consegui ler o painel de posições" | grade não visível/reconhecida | deixe o painel de posições da Tradovate aberto e visível na tela |
| Antivírus reclama do .exe | falso positivo comum do PyInstaller | assine o executável ou oriente a exceção |
