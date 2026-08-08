# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("PySide6")
a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("EnkiAgencyUniq.png", "."),
        ("EnkiAgencyUniq.ico", "."),
        ("captions.json", "."),
    ],
    hiddenimports=hiddenimports + ["uniquify_engine"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Enki Agency Uniq",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="EnkiAgencyUniq.ico",
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="Enki Agency Uniq",
)
