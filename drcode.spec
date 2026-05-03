# PyInstaller spec for building a single-folder Windows .exe of Dr Code.
# Build with:  pyinstaller drcode.spec
# Output goes to dist/DrCode/DrCode.exe

# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all


block_cipher = None


# Pull in *everything* PyQt6 ships — in particular QtWebEngine's data
# files (icudtl.dat, qtwebengine_resources*.pak, locales/, fonts) and
# its helper executable QtWebEngineProcess.exe. Without these the
# embedded ChatGPT browser tab loads as a blank white page in the
# frozen build, even though it works fine in `python drcode.py`.
pyqt6_datas, pyqt6_binaries, pyqt6_hidden = collect_all("PyQt6")


a = Analysis(
    ['drcode.py'],
    pathex=[],
    binaries=pyqt6_binaries,
    datas=pyqt6_datas + [
        ('desktop_app/resources/chatgpt_inject.js', 'desktop_app/resources'),
    ],
    hiddenimports=pyqt6_hidden + [
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebChannel',
        # The bundled JS bridge is loaded via importlib.resources, so
        # the frozen build needs to recognize this directory as a
        # real package.
        'desktop_app.resources',
        # pynput backends are loaded dynamically by platform.
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'pynput._util.win32',
        # mss platform backends are also dynamically imported.
        'mss.windows',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['desktop_app/_qtwebengine_runtime_hook.py'],
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
    name='DrCode',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX compression of QtWebEngineProcess.exe and the
    # Qt6WebEngineCore DLL has been known to break runtime loading on
    # Windows, so leave it off.
    upx=False,
    console=False,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DrCode',
)
