# SMC Quant Pro no Mac (M1 / M2 / M3) — v2.14.0

> Este guia é para o **Mac com chip Apple Silicon** (o M2 é um deles). Tudo
> roda **nativo em ARM**, sem Rosetta.

---

## Antes de tudo: o que muda, e o que NÃO muda

**Não muda nada do que importa.** A metodologia SMC, o motor de análise, o plano
de trading, o freio de sugestões, a autoaprendizagem, a TIGER, o multi-janela e
a automação da corretora são **exatamente o mesmo código**. Nenhuma decisão de
dinheiro passa a depender do sistema operacional — isso é verificado por teste
automático a cada versão.

O que muda é só a **camada de baixo**, e ela foi isolada num arquivo só
(`plataforma.py`):

| O que o programa faz | No Windows | no seu Mac |
|---|---|---|
| Guardar a chave da Gemini | DPAPI | **Chaveiro do macOS** |
| Listar as janelas abertas | win32gui | **Quartz** |
| Capturar o gráfico sem atrapalhar você | PrintWindow | **`screencapture -l`** |
| Bipe do alerta | winsound | **som do sistema** |
| A TIGER falar | pyttsx3 (SAPI5) | **voz `say` nativa (Luciana)** |
| Onde ficam seus dados | `%APPDATA%` | **`~/Library/Application Support`** |

**Uma limitação real, dita na cara:** se você **minimizar** a janela do gráfico
no Dock, o macOS descarta o conteúdo dela e **não existe pixel para capturar**.
O programa **pula o ciclo e avisa** — ele não desminimiza sozinho porque, no
Mac, desminimizar obriga a **ativar** o aplicativo, ou seja, pular na sua frente
no meio do pregão. **Deixe a janela do gráfico aberta**, mesmo que atrás de
outras — atrás funciona perfeitamente.

---

## Passo 1 — Instalar o Python certo (5 min)

⚠️ **O Python que já vem no Mac NÃO serve.** Ele não traz o **Tk**, que é a
biblioteca da interface — o programa abriria com erro de `tkinter`.

1. Vá em **https://www.python.org/downloads/macos/**
2. Baixe o **"macOS 64-bit universal2 installer"** do **Python 3.12** (o 3.11
   também serve).
3. Abra o `.pkg` e siga o instalador.
4. Confira no **Terminal** (abra pelo Spotlight: `⌘ + Espaço` → "Terminal"):

```bash
python3 --version
python3 -c "import tkinter; print('Tk OK')"
```

Precisa aparecer `Python 3.12.x` e `Tk OK`. Se o `Tk OK` não aparecer, o Python
instalado ainda é o do sistema — reinstale pelo python.org.

---

## Passo 2 — Instalar o Node.js (3 min)

O motor de análise roda em Node, igual no Windows.

**Opção A (recomendada) — Homebrew:**
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install node
```

**Opção B — instalador oficial:** baixe o `.pkg` **ARM64** em
https://nodejs.org (versão **LTS**).

Confira:
```bash
node -v
npm -v
```

> **Sobre um problema clássico do Mac:** quando você abre um aplicativo pelo
> **Finder**, ele **não herda o PATH do Terminal** — e o Node instalado pelo
> Homebrew (`/opt/homebrew/bin`) "some". O sintoma é cruel: `node -v` funciona
> no Terminal e o programa jura que o Node não existe. **Isto já está resolvido
> nesta versão**: o programa completa o PATH sozinho no arranque e procura o
> Node nos caminhos reais do Mac. Você não precisa fazer nada.

---

## Passo 3 — Baixar o programa e instalar as dependências (5 min)

Coloque a pasta do programa em algum lugar fixo, por exemplo
`~/Documentos/SMC_QUANT_PRO`. Ela precisa conter:

```
main_app.py
plataforma.py          ← novo nesta versão
tradovate_auto.py
requirements-mac.txt
versao.json
motor/                 ← a pasta do motor Node, inteira
```

No Terminal:

```bash
cd ~/Documentos/SMC_QUANT_PRO
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-mac.txt
```

Isso instala, entre outros, o **`pyobjc-framework-Quartz`** — é o equivalente
do `pywin32` no Mac. **Sem ele o programa não enxerga as janelas abertas.**

---

## Passo 4 — Primeira abertura

```bash
cd ~/Documentos/SMC_QUANT_PRO
python3 main_app.py
```

Na aba **⚙️ Motor**, o log já começa com o diagnóstico do sistema:

```
🖥️ Sistema: macOS (darwin)
🖥️ Python: 3.12.x
🖥️ Pasta de dados: /Users/voce/Library/Application Support/SMC_Quant_Pro
🖥️ Chave da API: no Chaveiro do macOS, preso à sua conta do Mac
🖥️ Quartz (pyobjc): ok
🖥️ Gravação de Tela: NÃO concedida      ← vamos resolver no passo 5
🖥️ screencapture: ok
🖥️ Janelas visíveis encontradas: 14
```

---

## Passo 5 — A permissão que faz TUDO funcionar (importante)

⚠️ **Este é o passo que, se pulado, faz parecer que o programa está quebrado.**

No macOS, ler o **título** das janelas de outros aplicativos e **capturar** o
conteúdo delas exige a permissão **Gravação de Tela**. Sem ela, o sistema **não
dá erro**: ele simplesmente entrega a lista de janelas **sem os títulos** e a
captura sai **preta**.

1. Abra **Ajustes do Sistema** (menu  → Ajustes do Sistema).
2. Vá em **Privacidade e Segurança** → **Gravação de Tela**.
3. Clique em **+**, e adicione:
   - Se está rodando pelo Terminal (Passo 4): adicione o **Terminal**.
   - Se está usando o **SMC Quant Pro.app**: adicione o **SMC Quant Pro**.
4. **Feche o programa por completo e abra de novo.** O macOS só aplica a
   permissão em processo novo — não adianta só voltar para a janela.

Confira: o log tem que passar a mostrar `🖥️ Gravação de Tela: concedida`.

**Também conceda** (aparecem sozinhas na primeira vez que forem usadas):
- **Microfone** → só se você for usar o "Olá Tiger".
- **Automação** → para o programa abrir o Chrome da corretora.

---

## Passo 6 — Chrome da corretora

Instale o **Google Chrome** (versão **Apple Silicon**) em
https://www.google.com/chrome/ e deixe-o em `/Applications`.

Use o botão do próprio programa para abrir a corretora — ele sobe um Chrome com
a porta de depuração ligada e um **perfil separado**, sem mexer no seu Chrome do
dia a dia. Se preferir abrir na mão:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.smc_tradovate_chrome" \
  --disable-features=CalculateNativeWinOcclusion \
  --disable-backgrounding-occluded-windows \
  --disable-renderer-backgrounding \
  --new-window https://trader.tradovate.com
```

---

## Passo 7 — Configurar e ligar

1. Aba **⚙️ Motor**: cole a **chave da Gemini** (ela vai para o **Chaveiro**, não
   para o arquivo de configuração).
2. Ainda na aba Motor: na **lista de gráficos**, escolha a janela do gráfico. No
   Mac o rótulo vem como **`Google Chrome — Tradovate`** (aplicativo primeiro, e
   isso é de propósito: sem a permissão de tela o título vem vazio, e assim você
   ainda consegue escolher pelo aplicativo).
3. Aba **📊 Plano de Trading**: confira meta, risco, drawdown, stops seguidos.
4. **▶️ LIGAR MOTOR**.

---

## Passo 8 (opcional) — Gerar o aplicativo `.app`

Para ter o ícone e abrir com duplo clique, sem Terminal:

```bash
cd ~/Documentos/SMC_QUANT_PRO
python3 -m pip install pyinstaller
rm -rf build dist
python3 -m PyInstaller SMC_Quant_Pro_MAC.spec
```

Sai em **`dist/SMC Quant Pro.app`**. Arraste para a pasta **Aplicativos**.

Na **primeira abertura**, o macOS vai barrar porque o app não tem assinatura da
Apple. É esperado:

- Clique com o **botão direito** no app → **Abrir** → **Abrir** de novo.
- Se ainda barrar: **Ajustes do Sistema → Privacidade e Segurança**, role até o
  aviso do SMC Quant Pro e clique em **Abrir Mesmo Assim**.
- Em último caso, no Terminal:
  ```bash
  xattr -dr com.apple.quarantine "/Applications/SMC Quant Pro.app"
  ```

⚠️ **Depois de gerar o `.app`, refaça o Passo 5** concedendo a Gravação de Tela
**ao aplicativo** (antes você concedeu ao Terminal — são permissões separadas).

---

## Se algo não funcionar

| Sintoma | Causa | Solução |
|---|---|---|
| `ModuleNotFoundError: tkinter` | Python do sistema, sem Tk | Passo 1: Python do python.org |
| Lista de janelas **vazia** | falta o pyobjc | `pip install pyobjc-framework-Quartz` |
| Janelas aparecem **só com o nome do app**, sem título | Gravação de Tela não concedida | Passo 5 |
| Captura sai **preta** | Gravação de Tela não concedida | Passo 5 (e **reabrir** o programa) |
| "Node.js não encontrado" mas `node -v` funciona | PATH do Finder | já resolvido; se persistir, abra pelo Terminal e me mande o log |
| Motor não sobe, porta ocupada | processo órfão | `lsof -ti :3939 \| xargs kill -9` |
| A TIGER fala **em inglês** | voz PT não instalada | Ajustes → Acessibilidade → Conteúdo Falado → Voz do Sistema → Português (Brasil) → **Luciana** |
| Gráfico "congelado" a cada ciclo | janela **minimizada** no Dock | deixe a janela aberta, mesmo atrás de outras |
| App não abre (desenvolvedor não identificado) | Gatekeeper | botão direito → Abrir, ou `xattr -dr com.apple.quarantine` |

---

## O que eu testei — e o que só o seu Mac pode testar

**Testado aqui, automatizado (31 suítes Python + 6 JS, todas passando):**

- a camada de plataforma reconhece macOS e monta os comandos certos:
  `screencapture -x -o -l <id>`, `security add-generic-password`, `say -v Luciana`;
- a chave da API **nunca** é gravada em claro no arquivo de configuração;
- falha de captura devolve **None** — nunca uma imagem inventada ou antiga;
- a correção do PATH do Finder acrescenta `/opt/homebrew/bin` e não duplica;
- as mensagens de erro são as do sistema certo (Mac não recebe instrução de `.exe`);
- **nenhuma** função de decisão de trading consulta o sistema operacional;
- `main_app.py` não chama mais `win32gui`, `win32ui`, `win32crypt`, `winsound`,
  `ctypes.windll` nem `os.startfile` em lugar nenhum;
- toda a lógica de SMC, freio, aprendizado, multi-janela, rotação de modelos e
  automação da corretora continua passando igual.

**O que eu NÃO tenho como testar daqui:** não tenho um Mac. A permissão de
Gravação de Tela concedida de verdade, a captura real da janela do Chrome, a voz
da Luciana saindo no alto-falante e o `.app` empacotado só podem ser conferidos
na sua máquina. Se algo escapar, o log do arranque (as linhas `🖥️`) diz
exatamente onde parou — me mande e eu ajusto sem chutar.
