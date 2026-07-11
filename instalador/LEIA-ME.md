# Instalador profissional — SMC Quant Pro (Inno Setup)

Este é o script para gerar um `setup.exe` único que o cliente roda para instalar
o SMC Quant Pro do jeito certo: coloca os arquivos no lugar, cria os atalhos,
instala o Node.js se faltar, e **não apaga os dados do cliente** nas atualizações.

> ⚠️ O Inno Setup só roda no **Windows**. Este script foi escrito aqui, mas a
> compilação (gerar o `setup.exe`) precisa ser feita na sua máquina Windows.

---

## Passo a passo

### 1. Instale o Inno Setup 6
Baixe e instale de: https://jrsoftware.org/isdl.php (gratuito).

### 2. Organize as pastas de origem
O script espera três coisas prontas na sua máquina:

| O quê | Onde o script procura (padrão) | O que é |
|---|---|---|
| App compilado | `C:\SMC\dist\SMC_Quant_Pro` | A pasta que o **PyInstaller** gera. Use o modo **onedir** (pasta), não onefile. |
| Motor Node.js | `C:\SMC\motor` | A pasta `motor/` com o `node_modules` **já pronto** do Baileys. |
| Node.js (opcional) | `C:\SMC\redist\node-v20.17.0-x64.msi` | O `.msi` LTS x64 baixado de https://nodejs.org, para instalar no cliente que não tem Node. |
| Ícone (opcional) | `C:\SMC\assets\icone.ico` | Ícone `.ico` do app. |

Se as suas pastas estiverem em outro lugar, **ajuste os caminhos** no topo do
arquivo `SMC_Quant_Pro.iss`, nas linhas marcadas com `<<< AJUSTE`.

> **Sobre o PyInstaller:** para o instalador funcionar bem, compile em modo
> pasta. No seu `.spec`, isso corresponde a ter um `COLLECT(...)` no final
> (onedir). O resultado fica em `dist\SMC_Quant_Pro\` com o `.exe` + arquivos.
> Se hoje você gera um `.exe` único (onefile), aponte o `SourceApp` para a
> pasta que contém esse único `.exe` — o script copia tudo que estiver lá.

### 3. Confira a versão
No topo do `.iss`, ajuste:
```
#define MyAppVersion     "1.6.1"
```
para bater com o `VERSAO_ATUAL` do `main_app.py` **e** com o campo `versao` do
gist de atualização. (Mesma regra de release de sempre: os números têm que bater.)

### 4. Compile
Abra o `SMC_Quant_Pro.iss` no **Inno Setup Compiler** e aperte **F9** (ou
menu *Build → Compile*). O instalador sai em:
```
instalador\Output\SMC_Quant_Pro_Setup_1.6.1.exe
```

Pronto — é esse arquivo que você distribui (sobe no Drive no lugar/junto do .zip).

---

## O que o instalador faz por dentro

1. **Instala em** `C:\Program Files\SMC Quant Pro\` (pede permissão de admin).
2. **Copia** todo o app + a pasta `motor\` para lá.
3. **Cria atalhos** no Menu Iniciar (sempre) e na Área de Trabalho (opção marcada).
4. **Node.js:** roda `where node` para ver se já existe. Só instala o `.msi`
   embutido, em silêncio, se o cliente **não** tiver Node. Quem já tem, não
   reinstala.
5. **Oferece abrir o app** ao terminar.
6. **Atualizações:** como o `AppId` é fixo, rodar um `setup.exe` mais novo por
   cima **atualiza no mesmo lugar**. Os dados em `%APPDATA%\SMC_Quant_Pro`
   (licença, histórico, chave da API) **não são tocados**.
7. **Desinstalação:** remove os arquivos de programa, mas **preserva** de
   propósito os dados em `%APPDATA%` — assim reinstalar não perde nada.

---

## Ainda pendente na lista de comercialização

- [x] **3. Instalador profissional** — este script.
- [ ] **4. Assinatura digital do `.exe`** — remove o aviso "Windows protegeu seu
  PC". Precisa de um certificado *Code Signing* (idealmente EV) de uma
  autoridade certificadora. Depois de ter o certificado, dá para assinar tanto o
  `SMC_Quant_Pro.exe` quanto o próprio `setup.exe` (o Inno Setup tem suporte a
  assinatura via `SignTool`). Quando você tiver o certificado, me chama que eu
  adapto este script para assinar automaticamente na compilação.
- [ ] **1. Documentos legais** (Termos de Uso + Política de Privacidade LGPD).
- [ ] **2. Proteção do código** (Nuitka / ofuscação).

### Dica que casa com a assinatura digital
Se quiser, dá para o instalador **mostrar os Termos de Uso** durante a
instalação (o cliente marca "aceito" antes de instalar). Basta ter o
`TERMOS.txt`/`.rtf` pronto e adicionar uma seção `[Setup] LicenseFile=`. Isso
conecta o item 3 com o item 1 — me avise quando os documentos legais estiverem
prontos que eu ligo os dois.
