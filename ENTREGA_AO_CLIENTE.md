# ENTREGA AO CLIENTE — passo a passo

Josevan, este arquivo é **seu**, não do cliente. Ele descreve o que fazer,
na ordem, para colocar o SMC Quant Pro na máquina de outra pessoa.

---

## ⛔ ANTES DE TUDO: o que NUNCA pode ir junto

Um único arquivo não pode sair da sua máquina:

**`painel_licencas.html`** — ele carrega o **seu token de administrador**.
Quem tiver esse arquivo pode criar, revogar e listar licenças. É a chave do
negócio, não um arquivo do programa.

O `empacotar.py` inclui esse painel por padrão, porque os zips normais são
para **você**. Para gerar os pacotes que vão para o cliente:

```
python3 empacotar.py --sem-painel
```

Confira antes de enviar — leva cinco segundos e evita um problema que não
tem volta:

```
unzip -l SMC_QUANT_PRO_MAC_vX.Y.Z.zip | grep painel
```

Se essa linha imprimir alguma coisa, **não envie esse zip**. Gere de novo com
`--sem-painel`. No Mac há também o `ABRIR_PAINEL_LICENCAS.command`, que só
serve para abrir o painel: sem o painel, ele não faz nada — mas prefira
mandar o pacote gerado com `--sem-painel`, que já resolve os dois.

---

## PASSO 1 — Descobrir em que sistema o cliente está

São **dois pacotes diferentes**, e mandar o errado é a forma mais rápida de
gerar um "não funciona":

| Cliente usa | Mande |
|---|---|
| MacBook / iMac (Apple Silicon M1, M2, M3, M4) | `SMC_QUANT_PRO_MAC_vX.Y.Z.zip` |
| Windows 10 ou 11 | `SMC_QUANT_PRO_WINDOWS_vX.Y.Z.zip` |

Não existe pacote "que serve para os dois". Cada um traz o instalador, o
LEIA-ME e os scripts do seu próprio sistema.

---

## PASSO 2 — Entregar a licença

Cada cliente precisa de uma licença. Abra o `painel_licencas.html` **na sua
máquina** e gere uma para ele. Anote:

- para quem é;
- a data de validade;
- o e-mail ou telefone de contato.

Se você não anotar, o painel continua funcionando e você deixa de saber quem
é quem — que é um problema de negócio, não de software.

---

## PASSO 3 — O que o cliente faz (e o que você faz por ele)

O LEIA-ME dentro do zip tem o passo a passo completo, escrito para quem não
é técnico. O resumo do que vai acontecer:

### No Mac
1. Descompacta e arrasta a pasta `SMC_QUANT_PRO` para **Documentos**.
   Depois disso, **não mover mais a pasta**.
2. Instala o **Python 3.12** do site python.org (o Python que já vem no Mac
   não serve — ele não traz o Tk, e o programa nem abre).
3. Instala o **Node.js LTS ARM64** (nodejs.org).
4. Dá um duplo clique em **`INSTALAR_MAC.command`**.
5. Dá um duplo clique em **`CRIAR_APP.command`** — é ele que cria o ícone do
   aplicativo. **Este passo não é opcional.**
6. Abre pelo **ÍCONE do aplicativo**, nunca pelo `.command`.

> **Por que o item 6 importa:** o macOS dá permissão de microfone ao
> *binário que pede*, e ao *pacote que contém esse binário*. Aberto pelo
> `.command`, quem pede é um Python que mora fora do aplicativo — e a
> permissão nunca aparece na lista de Privacidade. Foi um defeito real, e
> levou cinco relatos até a causa aparecer.

### No Windows
1. Descompacta em `C:\Users\<usuário>\Documents\SMC_QUANT_PRO`.
2. Instala Python 3.12 e Node.js LTS.
3. Roda o `INSTALAR.bat` (ou o instalador gerado pelo Inno Setup, se você
   preferir entregar um `.exe` único — veja `instalador/LEIA-ME.md`).

---

## PASSO 4 — As permissões do macOS (a parte que mais gera chamado)

Peça ao cliente para ligar o **SMC Quant Pro** em:

- Ajustes do Sistema → Privacidade e Segurança → **Gravação de Tela**
- Ajustes do Sistema → Privacidade e Segurança → **Acessibilidade**

e **reabrir o programa** depois. Sem pelo menos uma das duas, os títulos das
janelas saem vazios e a captura sai preta — o programa abre e não lê nada.

O microfone é diferente: ele só aparece na lista **depois** que o programa
pede pela primeira vez. Mande o cliente clicar em falar uma vez; aí o macOS
pergunta, e só então o SMC Quant Pro passa a existir naquela lista.

Se der problema, há um botão **🩺 Diagnosticar** na aba Motor que diz o
estado real de cada permissão — use isso antes de tentar adivinhar.

---

## PASSO 5 — A chave da Gemini

O cliente precisa da própria chave (aistudio.google.com → *Get API key*).
Ela é colada na aba **🎛️ Configurações → Instalação e chave da API**, e fica
guardada no cofre do sistema (Chaveiro no Mac, DPAPI no Windows) — nunca em
arquivo de texto.

**Explique o limite do plano gratuito.** Ele tem cota por minuto e por dia, e
quando estoura o programa avisa com todas as letras que não conseguiu ler o
gráfico. Isso não é defeito: é a cota. Para uso sério, chave paga.

---

## PASSO 6 — A IA local (opcional, mas recomende)

Na aba **🎛️ Configurações**, o botão **⬇️ Instalar a IA LOCAL (sem chave)**
baixa e instala tudo sozinho: o serviço, o modelo de texto e o **modelo de
visão**. São alguns GB, uma vez só, e a partir daí:

- quando a Gemini fica sem cota ou fora do ar, a leitura do gráfico não
  morre — a IA local assume, **declarada como reserva no Registro**;
- ela lê **pior** que a Gemini. Diga isso ao cliente. Ela existe para o
  ciclo não se perder, não para substituir a Gemini;
- tudo o que ela produz passa pelas mesmas travas: preço conferido contra o
  título da janela, ticker de contrato conhecido, piso de qualidade.

Avise também que, na primeira leitura, ela demora — está carregando alguns
GB do disco — e que a máquina fica mais pesada enquanto isso acontece.

---

## PASSO 7 — Conferir que ficou de pé, antes de dizer que ficou

Não entregue no "deve estar funcionando". Peça ao cliente três coisas:

1. Abrir o programa e mandar um print da aba **Motor** — a linha de status
   diz o que o programa achou do sistema dele.
2. Clicar em **🩺 Diagnosticar janelas** e mandar o resultado.
3. Ligar o motor com o gráfico aberto e esperar um ciclo. Se aparecer
   `📸 Capturando...` seguido de uma análise, está de pé.

Se o Registro disser que a Gemini falhou, ele diz **quantos** modelos foram
tentados e **por quê** — e, se a IA local não assumir, diz qual dos três
motivos aconteceu (não está no ar / não tem modelo de visão / não respondeu
a tempo). Peça o texto do Registro; ele responde quase tudo sozinho.

---

## PASSO 8 — Atualizações

Quando você publicar uma versão nova:

1. Suba os dois zips para a pasta do Drive.
2. Atualize o `versao.json` (número e notas).

O programa do cliente checa sozinho na abertura e mostra um aviso verde com
o botão de baixar. Você não precisa avisar ninguém um por um.

---

## Resumo de bolso

```
python3 tests/run.py            # 577 testes — rode ANTES de empacotar
python3 empacotar.py --sem-painel
unzip -l SMC_QUANT_PRO_MAC_v*.zip | grep painel     # tem de sair vazio
```

Manda o zip do sistema certo + a licença. O resto está no LEIA-ME de dentro
do pacote.
