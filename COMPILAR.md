# Como compilar o SMC Quant Pro v1.8.0

> **Resumo:** o processo de build **não mudou** na v1.8.0. Se você já compila pelo
> `.spec`, continue exatamente como sempre — não há arquivo novo a incluir.

---

## 0. O que mudou nesta versão

Apenas o **conteúdo** de dois arquivos que já faziam parte do build:

- `main_app.py`
- `tradovate_auto.py`  ← mudou também! (ganhou a leitura de posições)

**Nenhum arquivo novo** foi criado. O **motor NÃO mudou** — pode reaproveitar a
pasta `motor\` com o `node_modules` que você já tem.

Substitua os dois `.py` na pasta do projeto e siga para o passo 2.

---

## 1. Rodar local primeiro (opcional, recomendado)

Vale conferir antes de gastar tempo compilando:

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

## 2. Compilar (fluxo padrão — pelo `.spec`)

É o fluxo que você já usa. O `.spec` guarda ícone, nome e opções, então não há
nada para redigitar:

```cmd
cd C:\Users\jovan\Documents\SMC_QUANT_PRO
rd /s /q build
rd /s /q dist
python -m PyInstaller SMC_Quant_Pro.spec
```

O executável sai em: `dist\SMC_Quant_Pro.exe`

<details>
<summary>Não tem o <code>.spec</code>? (só nesse caso)</summary>

```cmd
pyinstaller --noconfirm --onefile --windowed ^
  --name SMC_Quant_Pro ^
  --icon icone.ico ^
  --add-data "tradovate_auto.py;." ^
  --hidden-import win32timezone ^
  --hidden-import PIL._tkinter_finder ^
  main_app.py
```

Isso **gera** um `SMC_Quant_Pro.spec` — a partir daí use o fluxo do passo 2.
</details>

---

## 3. Montar a pasta `dist` completa

O instalador copia **tudo** que estiver em `dist\`. Coloque o motor ao lado do `.exe`:

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

## 4. Testar o executável

```cmd
dist\SMC_Quant_Pro.exe
```

Repita o checklist do passo 1 e confira estes dois pontos novos da v1.8.0:

- **➕ Nova** abre a caixinha pedindo o nome da conta.
  (É o único import novo da versão — `tkinter.simpledialog`. Se por algum motivo
  o botão não abrir nada, acrescente `hiddenimports=['tkinter.simpledialog'],`
  no `Analysis(...)` do `.spec` e recompile.)
- **🔎 Detectar posições agora** (aba *Motor & WhatsApp*, painel Tradovate), com o
  Chrome aberto pelo botão do app e o painel de posições visível na Tradovate.

---

## 5. Gerar o instalador (Inno Setup)

1. Abra `instalador\SMC_Quant_Pro.iss` no Inno Setup Compiler.
2. Confira que `MyAppVersion` está **"1.8.0"** (já está).
3. Pressione **F9** (Compile).

O instalador sai em `instalador\Output\SMC_Quant_Pro_Setup_1.8.0.exe`.

---

## 6. Publicar a atualização

1. Suba o `SMC_Quant_Pro_Setup_1.8.0.exe` na pasta do Google Drive.
2. O `versao.json` **já está publicado como 1.8.0** — assim que o arquivo estiver
   no Drive, os clientes verão o aviso de nova versão e o botão de download.

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Botão "➕ Nova" não abre nada no .exe | `tkinter.simpledialog` não empacotado | some `hiddenimports=['tkinter.simpledialog'],` no `.spec` |
| `ModuleNotFoundError: tradovate_auto` | `.spec` sem o módulo | confira `datas`/`hiddenimports` do `.spec` |
| App abre e fecha na hora | erro na inicialização | rode `dist\SMC_Quant_Pro.exe` pelo `cmd` para ver a mensagem |
| WhatsApp não conecta no cliente | `node_modules` faltando | confira o passo 3 (`dist\motor\node_modules`) |
| "Não consegui ler o painel de posições" | grade não visível/reconhecida | deixe o painel de posições da Tradovate aberto e visível |
| Build antigo "grudado" | cache do PyInstaller | é para isso que servem os `rd /s /q build` e `rd /s /q dist` |
