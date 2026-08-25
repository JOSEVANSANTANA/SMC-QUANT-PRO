# -*- mode: python ; coding: utf-8 -*-
"""
Empacotamento do SMC Quant Pro para macOS (Apple Silicon — M1/M2/M3).

COMO USAR, no Terminal, dentro da pasta do projeto:

    python3 -m PyInstaller SMC_Quant_Pro_MAC.spec

Sai em:  dist/SMC Quant Pro.app

DIFERENÇAS EM RELAÇÃO AO BUILD DO WINDOWS (e por que existem)
--------------------------------------------------------------
1. target_arch='arm64': o Mac M2 é ARM. Empacotar x86_64 faria o app rodar
   pelo Rosetta — mais lento e com risco de biblioteca nativa incompatível.

2. BUNDLE com info_plist: o macOS SÓ pede as permissões de Gravação de Tela e
   Microfone se o aplicativo DECLARAR que vai usá-las. Sem estas chaves o
   sistema nega em silêncio: a captura sai preta e o microfone não abre, sem
   nenhuma caixa de diálogo aparecer. É a causa nº 1 de "instalei e não
   funciona" no Mac.

3. A pasta `motor` (Node) vai junto como dado, igual no Windows.

4. Sem pywin32/win32com em lugar nenhum: no Mac quem faz esse papel é o
   pyobjc-framework-Quartz mais o `screencapture` do próprio sistema.
"""

bloco_cipher = None

a = Analysis(
    ['main_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # O motor Node inteiro (com node_modules pronto, se houver).
        ('motor', 'motor'),
        # O versao.json TEM de viajar dentro do executavel. Desde a v2.68 o
        # programa le a versao dele em vez de um numero escrito a mao; sem
        # esta linha, o build congelado nao acha o arquivo e todo cliente ve
        # "0.0.0" no cabecalho. O icone entra junto para o instalador e o
        # Painel de Controle terem o que mostrar.
        ('versao.json', '.'),
        ('icone.ico', '.'),
    ],
    hiddenimports=[
        # A camada de plataforma é importada por nome; garantimos que entra.
        'plataforma',
        'tradovate_auto',
        # O PyInstaller nem sempre segue o Quartz sozinho.
        'Quartz',
        'objc',
        'CoreFoundation',
        'AppKit',
        # customtkinter puxa estes em tempo de execução.
        'PIL._tkinter_finder',
        'darkdetect',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Nada de Windows aqui — se entrar, o build quebra ou incha à toa.
        'win32gui', 'win32ui', 'win32con', 'win32crypt', 'win32api',
        'pywintypes', 'winsound', 'pythoncom',
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
    name='SMC Quant Pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX não é confiável no macOS ARM; não use.
    console=False,          # app de janela, sem terminal preto atrás
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',    # Apple Silicon nativo (M1/M2/M3)
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SMC Quant Pro',
)

app = BUNDLE(
    coll,
    name='SMC Quant Pro.app',
    icon=None,              # troque por 'icone.icns' se converter o ícone
    bundle_identifier='com.tigerinvest.smcquantpro',
    info_plist={
        'CFBundleName': 'SMC Quant Pro',
        'CFBundleDisplayName': 'SMC Quant Pro',
        'CFBundleShortVersionString': '2.14.0',
        'CFBundleVersion': '2.14.0',
        'LSMinimumSystemVersion': '12.0',        # Monterey ou mais novo
        'NSHighResolutionCapable': True,
        # ---- PERMISSÕES: sem estas linhas o macOS nega em SILÊNCIO ----
        # Gravação de Tela: capturar a janela do gráfico da corretora.
        'NSScreenCaptureUsageDescription':
            'O SMC Quant Pro captura a janela do seu gráfico para que a análise '
            'seja feita sobre o que está REALMENTE na tela, sem inventar dados.',
        # Microfone: o comando de voz "Olá Tiger".
        'NSMicrophoneUsageDescription':
            'Usado apenas quando você liga o comando de voz "Olá Tiger".',
        'NSSpeechRecognitionUsageDescription':
            'Usado apenas para entender os comandos de voz que você fala.',
        # Automação: abrir/controlar o Chrome da corretora.
        'NSAppleEventsUsageDescription':
            'Usado para abrir o Google Chrome na página da corretora.',
    },
)
