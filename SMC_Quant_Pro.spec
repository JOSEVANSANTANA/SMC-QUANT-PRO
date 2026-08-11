# -*- mode: python ; coding: utf-8 -*-
"""
Empacotamento do SMC Quant Pro para WINDOWS.

COMO USAR, no Prompt de Comando, dentro da pasta do projeto:

    cd C:\\Users\\jovan\\Documents\\SMC_QUANT_PRO
    rd /s /q build
    rd /s /q dist
    python -m PyInstaller SMC_Quant_Pro.spec

Sai em:  dist\\SMC_Quant_Pro\\SMC_Quant_Pro.exe


⚠️ LEIA ANTES DE USAR ESTE ARQUIVO
-----------------------------------
Este .spec foi ESCRITO PARA O REPOSITÓRIO, espelhando o
SMC_Quant_Pro_MAC.spec — ele NÃO é uma cópia do .spec que já existe na sua
máquina, porque aquele nunca foi versionado aqui (era esse o buraco: o
repositório sabia compilar para Mac e não sabia compilar para Windows).

Se o seu build atual funciona, COMPARE os dois antes de trocar. Se houver
diferença (um `datas` a mais, um ícone, um hiddenimport que você adicionou),
o certo é o SEU vencer — e aí me mande o arquivo para eu guardar o original
aqui, e a partir daí é este que vale para os dois.


DIFERENÇAS EM RELAÇÃO AO BUILD DO MAC (e por que existem)
----------------------------------------------------------
1. pywin32 nos hiddenimports: no Windows é ele quem lista as janelas, captura
   com PrintWindow e protege a chave da API com a DPAPI. No Mac esse papel é
   do pyobjc + `screencapture`.

2. Sem BUNDLE / info_plist: aquilo é o mecanismo do macOS para PEDIR as
   permissões de Gravação de Tela e Microfone. O Windows não tem equivalente
   — lá não se declara permissão, ela simplesmente existe.

3. console=False e icone.ico: no Windows o executável carrega o ícone dentro
   do próprio .exe.

4. A pasta `motor` (Node) vai junto como dado, igual no Mac.

5. Nada de pyobjc/Quartz aqui — se entrar, o build incha à toa e pode quebrar.
"""

import os

bloco_cipher = None

# O ícone é opcional: se o arquivo não estiver na pasta, o build continua (com
# o ícone padrão do Windows) em vez de falhar com um erro obscuro.
_icone = 'icone.ico' if os.path.exists('icone.ico') else None

a = Analysis(
    ['main_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # O motor Node inteiro (com node_modules pronto, se houver).
        ('motor', 'motor'),
    ],
    hiddenimports=[
        # A camada de plataforma é importada por nome; garantimos que entra.
        'plataforma',
        'tradovate_auto',
        # O PyInstaller nem sempre segue os módulos do pywin32 sozinho.
        'win32gui',
        'win32ui',
        'win32con',
        'win32api',
        'win32crypt',
        'pywintypes',
        'winsound',
        # customtkinter puxa estes em tempo de execução.
        'PIL._tkinter_finder',
        'darkdetect',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Nada de macOS aqui.
        'Quartz', 'AppKit', 'objc', 'CoreFoundation', 'Foundation',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=bloco_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=bloco_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SMC_Quant_Pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX costuma disparar falso positivo de antivírus
    console=False,          # app de janela, sem terminal preto atrás
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icone,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SMC_Quant_Pro',
)
