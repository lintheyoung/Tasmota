# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['gui_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.py', '.'),
        ('aws_iot_client.py', '.'),
        ('virtual_vibration_sensor.py', '.'),
        ('AmazonRootCA1.pem', '.'),
        # 默认证书（可选，用户可在 GUI 中切换）
        ('IoT-Gateway-000011.cert.pem', '.'),
        ('IoT-Gateway-000011.private.key', '.'),
    ],
    hiddenimports=[
        'awscrt',
        'awscrt.io',
        'awscrt.mqtt',
        'awscrt.auth',
        'awsiot',
        'customtkinter',
        'PIL._tkinter_finder',
        'PIL.Image',
        'PIL.ImageTk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AWS_IoT_Simulator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AWS_IoT_Simulator',
)

app = BUNDLE(
    coll,
    name='AWS_IoT_Simulator.app',
    icon=None,
    bundle_identifier='com.awsiot.simulator',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '1.0.0',
    },
)
