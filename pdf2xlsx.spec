# -*- mode: python ; coding: utf-8 -*-
import sys

block_cipher = None

a = Analysis(
    ['src/pdf2xlsx/gui/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pdf2xlsx.extractor',
        'pdf2xlsx.postprocess',
        'pdf2xlsx.writer',
        'pdf2xlsx.models',
        'pdf2xlsx.gui.main_window',
        'pdf2xlsx.gui.pdf_panel',
        'pdf2xlsx.gui.xlsx_panel',
        'pdfplumber',
        'pymupdf',
        'openpyxl',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pdf2xlsx',
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
    name='pdf2xlsx',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='pdf2xlsx.app',
        bundle_identifier='com.securityronin.pdf2xlsx',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSHighResolutionCapable': True,
            'CFBundleVersion': '0.1.0',
            'CFBundleShortVersionString': '0.1.0',
        },
    )
