#!/usr/bin/env python3
"""TESTE DE FUMAÇA DA INTERFACE — abre o programa de verdade e mexe nele.

    python3 tests/fumaca_gui.py            # precisa de tela (ou Xvfb)
    xvfb-run -a python3 tests/fumaca_gui.py

POR QUE ISTO EXISTE
-------------------
A suíte do `run.py` testa LÓGICA sem abrir janela — é rápida e roda em
qualquer lugar. Mas há uma classe inteira de defeito que ela não alcança:
a janela abre, nenhum widget levanta exceção, e mesmo assim o trader não
consegue usar o programa.

Foi assim que se descobriu que 22 dos 101 rótulos da interface não declaravam
cor de texto e, com o CustomTkinter em modo "System" num sistema em MODO CLARO,
saíam quase pretos sobre o fundo escuro do próprio app — invisíveis. Nenhum
teste de lógica pegaria isso. Abrir e OLHAR pegou.

O que este arquivo faz: sobe a janela, percorre as três abas, aplica todas as
escalas de letra, recolhe e abre seções, dispara notificações, salva o plano e
grava um PNG da tela para conferência humana.

Ele NÃO substitui o `run.py` — é o complemento que exige tela.
"""

import os
import sys
import tempfile
import traceback

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

falhas = []


def esperar(app, ms=250):
    """Deixa o Tk escoar os `after()` pendentes antes de conferir a tela.

    Precisa existir por causa do `CTkTabview.set()`: ele agenda um
    `after(100, _grid_forget_all_tabs(exclude_name=...))` que só ESCONDE abas
    e nunca regride a atual. Vários `set()` em sequência deixam a fila cheia
    de limpezas antigas, e a última a disparar esconde a aba que acabou de
    ser escolhida. Não é defeito do app — o app nunca chama `set()`; quem
    troca de aba é o clique, que segue outro caminho. É defeito de um teste
    que pergunta 'está na tela?' antes de a tela ter assentado."""
    fim = [False]
    app.after(ms, lambda: fim.__setitem__(0, True))
    while not fim[0]:
        app.update_idletasks()
        app.update()


def passo(app, nome, fn):
    """Executa um passo e força o Tk a processar tudo antes de seguir."""
    try:
        fn()
        app.update_idletasks()
        app.update()
        print(f"  OK   {nome}")
    except Exception as e:
        falhas.append(f"{nome}: {type(e).__name__}: {e}")
        print(f"  FALHA {nome}: {type(e).__name__}: {e}")
        traceback.print_exc()


def main():
    # Pasta de dados limpa: o teste NUNCA toca no diário real do trader.
    os.environ["HOME"] = tempfile.mkdtemp(prefix="smc_fumaca_")

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "main_app", os.path.join(RAIZ, "main_app.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["main_app"] = mod
    spec.loader.exec_module(mod)
    print(f"import OK — v{mod.VERSAO_ATUAL}")

    import customtkinter as ctk
    modo = ctk.get_appearance_mode()
    print(f"modo de aparência: {modo}")
    if modo != "Dark":
        falhas.append(
            f"modo de aparência é '{modo}', não 'Dark' — os rótulos que não "
            "declaram cor de texto ficam invisíveis sobre o fundo escuro do app")

    # LIÇÕES ENVENENADAS, gravadas ANTES de a janela abrir — é assim que elas
    # existem na máquina dele. A lista real de 13/08 tinha uma PERGUNTA na
    # posição 6 ("o que aconteceu com HAPV3 HOJE?"), gravada antes de a trava
    # existir, e ela entrava em toda análise porque as lições vão inteiras
    # para dentro do prompt.
    # As DUAS do WhatsApp (14/08, 10:57 e 10:58) estão gravadas na máquina
    # dele agora: ele mandou a mesma coisa duas vezes porque desconfiou que
    # não tinha pego, e ouviu "aprendido" nas duas. Nunca ia funcionar — o
    # WhatsApp daqui só ENVIA. Elas entram aqui para a faxina ser provada com
    # o app de verdade aberto, e não só na função pura.
    import json as _json
    with open(mod.LICOES_FILE, "w", encoding="utf-8") as f:
        _json.dump(["nunca invente numeros, nunca alucine",
                    "o que aconteceu com HAPV3 HOJE?",
                    "toda vez que eu enviar STATUS pelo whatsapp, por favor, "
                    "envie o status para mim!",
                    "acompanhe o motor,  toda vez que eu enviar STATUS pelo "
                    "whatsapp, por favor, envie o status para mim!",
                    "tira um print e olha o preco atual, nunca forneca "
                    "recomendacoes sem olhar o preco atual"],
                   f, ensure_ascii=False)

    app = mod.SmcQuantApp()
    app.update_idletasks()
    app.update()
    print(f"janela criada — {app.winfo_geometry()}")

    print("\n[faxina das lições que não ensinam nada]")
    restantes = mod.carregar_licoes()
    print(f"       sobraram: {restantes}")
    if any("HAPV3" in l for l in restantes):
        falhas.append("faxina: a pergunta gravada como lição continua lá, "
                      "entrando em toda análise")
        print("  FALHA a pergunta continua gravada como lição")
    elif any("whatsapp" in l.lower() for l in restantes):
        falhas.append("faxina: a lição do WhatsApp continua gravada — ela "
                      "promete um recurso que não existe e entra em toda análise")
        print("  FALHA a lição do WhatsApp continua gravada")
    elif len(restantes) != 2:
        falhas.append(f"faxina: levou lição boa junto — sobrou {restantes}")
        print("  FALHA levou lição boa junto")
    else:
        print("  OK   tirou a pergunta e as duas do WhatsApp, manteve as regras")

    print("\n[widgets que a refatoração da aba Motor precisa ter criado]")
    for attr in ("btn_ligar", "api_entry", "janela_dropdown", "console",
                 "sec_whatsapp", "_var_escala_motor", "txt_chat",
                 "entrada_chat", "entry_max_ctr", "entry_min_ticks",
                 "lbl_escala_ia", "entry_margem", "opt_com_posicao"):
        existe = getattr(app, attr, None) is not None
        print(f"  {'OK  ' if existe else 'FALTA'} {attr}")
        if not existe:
            falhas.append(f"widget ausente: {attr}")

    # AS QUATRO ABAS. Pedido dele em 14/08: "o que for possível e considerado
    # configuração, organize em uma opção chamada Configurações". Se a aba
    # não nascer, tudo o que foi movido para dentro dela some da tela — e
    # some CALADO, sem exceção nenhuma.
    print("\n[abas]")
    abas = list(app.tabview._name_list)
    print(f"       {abas}")
    for esperada in ("⚙️ Motor & WhatsApp", "📊 Plano de Trading", "🐯 TIGER",
                     "🎛️ Configurações"):
        if esperada in abas:
            print(f"  OK   {esperada}")
        else:
            falhas.append(f"aba ausente: {esperada}")
            print(f"  FALHA aba ausente: {esperada}")
    for aba in abas:
        passo(app, f"abrir a aba {aba}", lambda a=aba: app.tabview.set(a))
        esperar(app)          # escoa a limpeza atrasada antes da próxima troca

    # O SLIDER DA VELOCIDADE DA FALA PRECISA ESTAR *NA TELA*.
    # Ele existia, com o comando ligado e o valor certo, e nunca apareceu: o
    # `.set()` estava encadeado na construção, `.set()` devolve None, e o
    # `.pack()` nunca aconteceu. Ele escreveu "a velocidade da voz não está
    # disponível para alterar" e estava certo. `winfo_ismapped()` é a única
    # pergunta que separa "o widget existe" de "o widget está na tela".
    print("\n[controles que precisam APARECER, não só existir]")
    app.tabview.set("🎛️ Configurações")
    esperar(app)
    passo(app, "abrir a seção VOZ DA TIGER", app.sec_voz_conteudo.abrir_secao)
    esperar(app)
    for attr, quem in (("sld_vel_voz", "slider da velocidade da fala"),
                       ("lbl_vel_voz", "rótulo do ritmo da fala")):
        w = getattr(app, attr, None)
        if w is None:
            falhas.append(f"widget ausente: {attr} ({quem})")
            print(f"  FALHA {attr} nem existe")
        elif not w.winfo_ismapped():
            falhas.append(f"{attr} existe mas NÃO está na tela ({quem}) — "
                          "faltou pack/grid")
            print(f"  FALHA {attr} existe e não está na tela")
        else:
            print(f"  OK   {quem} visível ({w.winfo_width()}x{w.winfo_height()}px)")
    app.tabview.set("⚙️ Motor & WhatsApp")

    print("\n[tamanho da letra — todas as escalas, ao vivo]")
    for nome, valor in mod.ESCALAS_LETRA.items():
        passo(app, f"escala {nome} ({valor}×)",
              lambda v=valor: app._aplicar_escala_letra(v, avisar=False))
        print(f"       terminal={app.txt_chat.cget('font')} "
              f"console={app.console.cget('font')} "
              f"rótulo={app.lbl_escala_ia.cget('text')!r}")
    passo(app, "botão A＋", lambda: app._escala_por_passo(+1))
    passo(app, "botão A－", lambda: app._escala_por_passo(-1))
    app._aplicar_escala_letra(1.0, avisar=False)

    print("\n[seções recolhíveis]")
    passo(app, "recolher a seção do WhatsApp", app.sec_whatsapp.alternar_secao)
    passo(app, "abrir (é o que o QR code faz)", app.sec_whatsapp.abrir_secao)
    passo(app, "abrir de novo — tem de ser idempotente",
          app.sec_whatsapp.abrir_secao)

    print("\n[notificações na tela]")
    app.notif_var.set(True)
    passo(app, "aviso simples",
          lambda: app._notificar_desktop("Teste", ["linha 1", "linha 2"]))
    passo(app, "aviso com ACATAR / NÃO OPEREI",
          lambda: app._notificar_desktop("Sugestão", ["BUY MESU6"],
                                         sinal_id=123, direcao="BUY"))
    abertas = len([w for w in app._notif_abertas if w.winfo_exists()])
    print(f"       janelas de aviso abertas: {abertas}")
    passo(app, "fechar todas", app._fechar_todas_notificacoes)

    print("\n[plano de trading e dashboard]")
    passo(app, "salvar plano", app.salvar_plano_trading)
    passo(app, "atualizar dashboard", app._atualizar_dashboard)

    # A CONTA DA META, COM O APP DE VERDADE ABERTO.
    # 13/08, 16:01: "o dia encerra às 17:59, como estamos de probabilidade de
    # bater a meta de hoje até lá?" → "não tenho dados suficientes para
    # prever". Tinha todos os dados. Aqui o caminho inteiro é percorrido —
    # plano, diário e horário do pregão — para provar que ele responde em vez
    # de estourar ou devolver vazio.
    print("\n[a conta da meta de hoje]")
    # SEM META CONFIGURADA ele não pode dizer "meta batida". Foi este passo
    # que pegou a afirmação falsa e simpática numa instalação nova.
    sem_meta = app._texto_da_meta_de_hoje()
    if "batida" in sem_meta.lower() and "não configurou" not in sem_meta:
        falhas.append("meta: sem meta configurada, ele disse que a meta foi "
                      f"batida — {sem_meta[:120]}")
        print("  FALHA disse 'meta batida' sem meta configurada")
    else:
        print("  OK   sem meta configurada, ele diz isso em vez de inventar")

    # AGORA COM META E COM DIÁRIO. Aqui a aritmética é exercitada de verdade:
    # meta de US$400 em 2 dias (US$200/dia), duas operações fechadas hoje —
    # uma de +100 e uma de -50 — e o pregão ainda aberto.
    app.plano["meta_alvo"] = 400.0
    app.plano["dias_meta"] = 2
    app.plano["data_inicio"] = mod.datetime.date.today().isoformat()
    app.plano["max_operacoes_dia"] = 10
    # PREGÃO ABERTO DE PROPÓSITO. Com o horário padrão, este teste rodaria de
    # madrugada com o pregão fechado e nunca exercitaria a conta da chance —
    # passaria verde sem ter testado a parte que importa.
    agora = mod.datetime.datetime.now()
    # A JANELA É RELATIVA A AGORA, e não "00:01 até agora+3h". Rodando às 23h,
    # agora+3h vira 02:12 do dia seguinte: com início fixo em 00:01 isso vira
    # um pregão 00:01→02:12 que JÁ FECHOU, e o teste da chance passava batido
    # sem nunca ter exercitado a conta. Abre uma hora atrás, fecha em três.
    abre = (agora - mod.datetime.timedelta(hours=1)).strftime("%H:%M")
    fecha = (agora + mod.datetime.timedelta(hours=3)).strftime("%H:%M")
    mod.salvar_config({"hora_inicio": abre, "hora_fim": fecha})
    print(f"       pregão do teste: {abre} → {fecha} (aberto agora)")
    carimbo = (agora - mod.datetime.timedelta(hours=2)).strftime('%d/%m/%Y %H:%M')
    fim = agora.strftime('%d/%m/%Y %H:%M')
    # conta_id e data_criacao são obrigatórios: sem eles a posição não passa
    # pelos filtros de conta e de ciclo, e o diário sairia vazio — o teste
    # passaria sem ter testado nada.
    conta = mod.conta_ativa_id()
    posicoes = [
        {"id": 901, "conta_id": conta, "status": "FECHADA", "direcao": "BUY",
         "ativo": "MESU6", "contratos": 2, "entry": 7800.0, "pnl_final": 100.0,
         "data_criacao": carimbo, "data_abertura": carimbo,
         "data_fechamento": fim},
        {"id": 902, "conta_id": conta, "status": "FECHADA", "direcao": "SELL",
         "ativo": "MESU6", "contratos": 2, "entry": 7810.0, "pnl_final": -50.0,
         "data_criacao": carimbo, "data_abertura": carimbo,
         "data_fechamento": fim},
    ]
    passo(app, "gravar duas operações fechadas no diário",
          lambda: mod.salvar_posicoes(posicoes))
    fechadas_hoje = len(mod.operacoes_fechadas_hoje())
    print(f"       o diário enxergou {fechadas_hoje} operação(ões) de hoje")
    if fechadas_hoje != 2:
        falhas.append("meta: o diário não enxergou as duas operações gravadas "
                      f"({fechadas_hoje}) — a conta seria feita sobre o vazio")

    texto_meta = app._texto_da_meta_de_hoje()
    if "CHANCE:" not in texto_meta:
        falhas.append("meta: com pregão aberto, meta configurada e duas "
                      "operações fechadas, a conta da chance NÃO saiu — "
                      f"veio: {texto_meta[:200]}")
        print("  FALHA a conta da chance não saiu")
    else:
        print("  OK   a conta da chance saiu")

    for nome, fn in (("texto na tela", app._texto_da_meta_de_hoje),
                     ("versão falada", app._meta_falada),
                     ("números crus", app._numeros_da_meta_de_hoje)):
        try:
            saida = fn()
            if not saida:
                falhas.append(f"meta: {nome} veio vazio")
                print(f"  FALHA {nome} veio vazio")
            else:
                print(f"  OK   {nome}")
                if isinstance(saida, str):
                    for linha in saida.splitlines():
                        print(f"       {linha}")
        except Exception as e:
            falhas.append(f"meta ({nome}): {type(e).__name__}: {e}")
            print(f"  FALHA {nome}: {type(e).__name__}: {e}")
            traceback.print_exc()

    # A TRILHA VEM DEPOIS DA META DE PROPÓSITO: ela configura meta,
    # prazo e diário para exercitar os quadradinhos, e o bloco da meta
    # precisa rodar com o plano VIRGEM para provar que, sem meta
    # configurada, a ferramenta diz isso em vez de inventar 'meta batida'.
    # A TRILHA DOS DIAS PRECISA SER CLICÁVEL — pedido dele em 17/08.
    # "e se eu quiser ficar um dia sem operar? e se for feriado ou final de
    # semana? ajuste isso para que eu consiga clicar ali no quadradinho dos
    # dias e escolher". Antes era texto dentro de um rótulo: não havia onde
    # clicar. Aqui os botões são criados, clicados e conferidos de verdade.
    print("\n[trilha dos dias — tem de dar para CLICAR]")
    app.plano["meta_alvo"] = 3200.0
    app.plano["dias_meta"] = 8
    app.plano["data_inicio"] = (mod.datetime.date.today()
                                - mod.datetime.timedelta(days=3)).isoformat()
    app.plano["dia_ciclo_ancora"] = None
    mod.salvar_plano_da_conta(app.plano)
    # forcar=True: a assinatura do painel não olha o arquivo do plano, então
    # sem isto o desenho é pulado e o teste mediria a tela anterior.
    passo(app, "desenhar a trilha",
          lambda: app._atualizar_dashboard(forcar=True))
    botoes = getattr(app, "_botoes_trilha", [])
    print(f"       quadradinhos na tela: {len(botoes)}")
    if len(botoes) != 8:
        falhas.append(f"trilha: esperava 8 quadradinhos, vieram {len(botoes)}")
    elif not botoes[0].winfo_ismapped():
        falhas.append("trilha: os quadradinhos existem e NÃO estão na tela")
        print("  FALHA os quadradinhos não estão na tela")
    else:
        print(f"  OK   clicáveis e visíveis "
              f"({botoes[0].winfo_width()}x{botoes[0].winfo_height()}px)")

    # O RESULTADO DO DIA, LANÇADO NO DIA CERTO.
    # 17/08, 19:59: "hoje encerrou às 17:59, abriu às 19h, mas antes de fechar
    # eu fiz 54 dólares e incluí no diário, e não está contabilizando". O
    # lançamento tinha caído no pregão da véspera, calado. Aqui o caminho
    # inteiro é percorrido: dia do ciclo -> data -> carimbo -> diário.
    print("\n[lançar o resultado de UM dia — os 54 dólares que sumiram]")
    dia_alvo = 2
    data_alvo = mod.data_do_dia_do_ciclo(app.plano, dia_alvo)
    print(f"       o dia {dia_alvo} do ciclo cai em {data_alvo}")
    if data_alvo is None:
        falhas.append("resultado do dia: não descobri a data do dia 2")
    else:
        alvo_txt = data_alvo.strftime("%d/%m/%Y")
        antes_dia2 = dict(mod.resultados_por_dia()).get(alvo_txt, 0.0)
        passo(app, "lançar US$ +54 no dia 2",
              lambda: mod.lancar_resultado_do_dia(alvo_txt, 54.0))
        depois_dia2 = dict(mod.resultados_por_dia()).get(alvo_txt)
        print(f"       diário do dia {alvo_txt}: {antes_dia2} → {depois_dia2}")
        if depois_dia2 is None or abs(depois_dia2 - (antes_dia2 + 54.0)) > 0.01:
            falhas.append(
                f"resultado do dia: lancei +54 em {alvo_txt} e o diário desse "
                f"pregão ficou {depois_dia2} (era {antes_dia2}) — é o defeito "
                "dos 54 dólares que sumiram")
            print("  FALHA o valor não entrou no pregão pedido")
        else:
            print("  OK   os 54 dólares entraram NO DIA PEDIDO")
        # E precisa APARECER na trilha, senão ele continua sem ver.
        app._atualizar_dashboard(forcar=True)
        esperar(app)
        txt_d2 = app._botoes_trilha[dia_alvo - 1].cget("text")
        print(f"       quadradinho do dia {dia_alvo}: {txt_d2!r}")
        # O ESPERADO É O TOTAL DO DIA, não os 54. O dia 2 é hoje e já carrega
        # as duas operações que o bloco da meta gravou — procurar "54" no
        # texto era a asserção errada, não a conta.
        esperado = f"{(antes_dia2 + 54.0):+,.0f}"
        if esperado not in txt_d2:
            falhas.append(f"trilha: o dia {dia_alvo} não mostra o resultado do "
                          f"dia ({esperado}) — veio {txt_d2!r}")
            print(f"  FALHA o quadradinho não mostra {esperado}")
        else:
            print("  OK   o quadradinho mostra o resultado do dia")

    # MARCAR O DIA COMO CONCLUÍDO / NÃO OPEREI — o outro pedido de 17/08.
    print("\n[marcar o dia como concluído ou não operado]")
    passo(app, "marcar o dia 1 como CONCLUÍDO",
          lambda: app._marcar_dia(1, "concluido"))
    if (mod.plano_da_conta_ativa() or {}).get("dias_marcados", {}).get("1") != "concluido":
        falhas.append("marca do dia: 'concluído' não foi gravado em disco")
        print("  FALHA não gravou em disco")
    elif "✅" not in app._botoes_trilha[0].cget("text"):
        falhas.append("marca do dia: marquei concluído e o quadradinho não "
                      f"mostra ✅ — veio {app._botoes_trilha[0].cget('text')!r}")
        print("  FALHA o quadradinho não mudou")
    else:
        print("  OK   marcou, gravou e apareceu na tela")
    passo(app, "marcar o dia 4 como NÃO OPEREI",
          lambda: app._marcar_dia(4, "nao_operei"))
    if "🚪" not in app._botoes_trilha[3].cget("text"):
        falhas.append("marca do dia: 'não operei' não apareceu no quadradinho")
        print("  FALHA 'não operei' não apareceu")
    else:
        print("  OK   'não operei' aparece com marca própria")
    passo(app, "desmarcar o dia 1", lambda: app._marcar_dia(1, None))
    if (mod.plano_da_conta_ativa() or {}).get("dias_marcados", {}).get("1"):
        falhas.append("marca do dia: desmarcar não apagou a marca")
        print("  FALHA desmarcar não funcionou")
    else:
        print("  OK   desmarcar volta o dia para o automático")

    # CLICA NUM DIA DIFERENTE DO ATUAL. Clicar no dia que já está aceso não
    # provaria nada: passaria verde sem o clique ter feito efeito nenhum.
    antes_dia = app._computar_stats_plano().get("dia_atual")
    alvo = 5 if antes_dia != 5 else 3
    passo(app, f"clicar no D{alvo} (hoje estava no D{antes_dia})",
          lambda: app._escolher_dia_do_ciclo(alvo))
    depois = app._computar_stats_plano()
    print(f"       dia antes do clique: {antes_dia} · depois: {depois.get('dia_atual')}")
    if depois.get("dia_atual") != alvo:
        falhas.append(f"trilha: cliquei em D{alvo} e o dia ficou "
                      f"{depois.get('dia_atual')}")
        print("  FALHA o clique não mudou o dia")
    elif not depois.get("dia_manual"):
        falhas.append("trilha: o dia mudou mas não ficou marcado como escolha dele")
    else:
        print("  OK   o clique mandou, e a escolha ficou registrada como dele")

    # GRAVOU EM DISCO? Escolha que morre ao fechar o programa não serve.
    if (mod.plano_da_conta_ativa() or {}).get("dia_ciclo_ancora"):
        print("  OK   a escolha foi gravada no plano em disco")
    else:
        falhas.append("trilha: a escolha do dia não foi gravada em disco")
        print("  FALHA a escolha não foi gravada")

    # CLICAR NO MESMO DIA DESFAZ. Sem isso, um clique errado seria permanente.
    passo(app, f"clicar de novo no D{alvo} (desfazer)",
          lambda: app._escolher_dia_do_ciclo(alvo))
    if app._computar_stats_plano().get("dia_manual"):
        falhas.append("trilha: clicar no dia aceso não voltou ao automático")
        print("  FALHA não voltou para a contagem automática")
    else:
        print("  OK   clicar no dia aceso volta para a contagem automática")


    destino = os.path.join(tempfile.gettempdir(), "smc_fumaca.png")
    try:
        from PIL import ImageGrab
        tela = ImageGrab.grab(xdisplay=os.environ.get("DISPLAY"))
        tela.save(destino)
        print(f"\nprint da tela: {destino}  (abra e confira se dá para LER tudo)")
    except Exception as e:
        print(f"\n(print da tela não saiu: {e})")

    app.destroy()

    print("\n" + "=" * 60)
    if falhas:
        print(f"FALHOU — {len(falhas)} problema(s):")
        for f in falhas:
            print(f"  • {f}")
        return 1
    print("TUDO OK — a interface abriu, respondeu e fechou.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        print("\nSem tela? Rode com:  xvfb-run -a python3 tests/fumaca_gui.py")
        sys.exit(1)
