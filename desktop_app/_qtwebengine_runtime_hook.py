"""Runtime hook executed before user code in the frozen PyInstaller build.

QtWebEngine is notoriously fragile inside PyInstaller bundles on
Windows: even when ``collect_all('PyQt6')`` packages all the data
files, Chromium often fails to locate them at runtime because it
hard-codes paths relative to ``QtWebEngineProcess.exe`` rather than to
the running .exe.

This hook walks the ``_MEIPASS`` directory (the temp dir PyInstaller
extracts the bundle into) for the PyQt6 ``Qt6`` folder, and explicitly
sets the three environment variables QtWebEngine looks at before
falling back to its compiled-in defaults:

* ``QTWEBENGINEPROCESS_PATH`` \u2014 absolute path to the helper exe.
* ``QTWEBENGINE_RESOURCES_PATH`` \u2014 directory containing
  ``icudtl.dat`` and ``qtwebengine_resources*.pak``.
* ``QTWEBENGINE_LOCALES_PATH`` \u2014 directory of locale .pak files.

We also disable Chromium's own sandbox in the frozen build, because
running QtWebEngine from a PyInstaller-extracted temp directory
typically fails the sandbox's path checks and falls back to a blank
page.
"""

from __future__ import annotations

import os
import sys


def _configure_qtwebengine_paths() -> None:
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        # Not running frozen \u2014 development mode, nothing to do.
        return

    # Try the well-known PyQt6 layout first; fall back to a recursive
    # search if the wheel layout changes.
    candidates = [
        os.path.join(base, "PyQt6", "Qt6"),
        os.path.join(base, "Qt6"),
    ]
    qt_root = None
    for c in candidates:
        if os.path.isdir(c):
            qt_root = c
            break

    if qt_root is None:
        for root, dirs, _ in os.walk(base):
            if "QtWebEngineProcess.exe" in os.listdir(root) if os.path.basename(root) == "bin" else False:
                qt_root = os.path.dirname(root)
                break

    if qt_root is None:
        # Last-ditch: look anywhere for the helper exe.
        for root, _, files in os.walk(base):
            if "QtWebEngineProcess.exe" in files:
                # The helper exe lives in <qt_root>/bin/ on Windows.
                qt_root = os.path.dirname(root)
                break

    if qt_root is None:
        return

    helper_candidates = [
        os.path.join(qt_root, "bin", "QtWebEngineProcess.exe"),
        os.path.join(qt_root, "bin", "QtWebEngineProcess"),
        os.path.join(qt_root, "libexec", "QtWebEngineProcess"),
    ]
    helper = next((h for h in helper_candidates if os.path.isfile(h)), None)
    if helper:
        os.environ.setdefault("QTWEBENGINEPROCESS_PATH", helper)

    resources = os.path.join(qt_root, "resources")
    if os.path.isdir(resources):
        os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", resources)

    locales = os.path.join(qt_root, "translations", "qtwebengine_locales")
    if os.path.isdir(locales):
        os.environ.setdefault("QTWEBENGINE_LOCALES_PATH", locales)

    # Frozen QtWebEngine bundles typically can't pass Chromium's
    # sandbox path checks on Windows because the helper exe lives
    # under the PyInstaller temp dir, and they often hit GPU /
    # rasterizer init failures on bare-metal Windows VMs without
    # proper graphics drivers. Disable everything that can blow up
    # the renderer so the browser can at least come up.
    existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    extra_flags = (
        "--no-sandbox "
        "--disable-gpu-sandbox "
        "--disable-gpu "
        "--disable-software-rasterizer "
        "--disable-dev-shm-usage "
        "--disable-features=VizDisplayCompositor"
    )
    if "--no-sandbox" not in existing_flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            f"{existing_flags} {extra_flags}".strip()
        )

    # Some Qt builds also honour this older env var instead of/in
    # addition to the Chromium flag.
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")


_configure_qtwebengine_paths()
