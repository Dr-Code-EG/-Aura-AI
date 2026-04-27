# PyInstaller spec for building a single-folder Windows .exe of Aura Desktop.
# Build with:  pyinstaller aura_desktop.spec
# Output goes to dist/AuraDesktop/AuraDesktop.exe

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(
    ['aura_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('desktop_app/resources/chatgpt_inject.js', 'desktop_app/resources'),
    ],
    hiddenimports=[
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebChannel',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='AuraDesktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AuraDesktop',
)
