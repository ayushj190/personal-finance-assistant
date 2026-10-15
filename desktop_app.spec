# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules
import sys
from pathlib import Path

block_cipher = None

datas = []
datas += copy_metadata("streamlit")
datas += collect_data_files("streamlit")

# Project application code, migrations, styles, and configs
datas += [
    ("app.py", "."),
    ("core", "core"),
    ("db", "db"),
    ("services", "services"),
    ("ui", "ui"),
    ("connectors", "connectors"),
    (".streamlit", ".streamlit"),
]

hiddenimports = []
hiddenimports += collect_submodules("streamlit")
hiddenimports += collect_submodules("ui")
hiddenimports += collect_submodules("services")
hiddenimports += collect_submodules("connectors")
hiddenimports += collect_submodules("db")
hiddenimports += collect_submodules("core")
hiddenimports += [
    "webview",
    "webview.platforms.cocoa",
    "plotly",
    "pandas",
    "pypdf",
    "openpyxl",
    "mt940",
    "keyring",
    "cryptography",
]

# Exclude heavy machine learning and broker libraries (AC-4)
excludes = [
    "ollama",
    "fastembed",
    "sqlite_vec",
    "pytr",
    "torch",
    "onnxruntime",
    "transformers",
    "tokenizers",
]

a = Analysis(
    ["desktop_app.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name="PersonalFinanceAssistant",
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
    name="PersonalFinanceAssistant",
)

app = BUNDLE(
    coll,
    name="Personal Finance Assistant.app",
    icon=None,
    bundle_identifier="com.ayush.personalfinanceassistant",
    info_plist={
        "CFBundleName": "Personal Finance Assistant",
        "CFBundleDisplayName": "Personal Finance Assistant",
        "CFBundleIdentifier": "com.ayush.personalfinanceassistant",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": "True",
        "LSMinimumSystemVersion": "12.0",
    },
)
