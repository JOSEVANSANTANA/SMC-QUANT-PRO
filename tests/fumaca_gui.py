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

    app = mod.SmcQuantApp()
    app.update_idletasks()
    app.update()
    print(f"janela criada — {app.winfo_geometry()}")

    print("\n[widgets que a refatoração da aba Motor precisa ter criado]")
    for attr in ("btn_ligar", "api_entry", "janela_dropdown", "console",
                 "sec_whatsapp", "_var_escala_motor", "txt_chat",
                 "entrada_chat", "entry_max_ctr", "entry_min_ticks",
                 "lbl_escala_ia", "entry_margem", "opt_com_posicao"):
        existe = getattr(app, attr, None) is not None
        print(f"  {'OK  ' if existe else 'FALTA'} {attr}")
        if not existe:
            falhas.append(f"widget ausente: {attr}")

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
