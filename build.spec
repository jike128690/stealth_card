# -*- mode: python ; coding: utf-8 -*-
#
# StealthCard 定制打包配置（对应开发计划文档 4.3）
# 说明：文档原稿基于 PyInstaller 5 语法，其中 cipher / win_no_prefer_redirects /
# win_private_assemblies / a.zipped_data 在 PyInstaller 6 中已移除，
# 此处按 PyInstaller 6 的等效写法保留全部原有意图：剔除重型模块、关闭控制台、
# 注入伪装版本信息、隐藏 pynput Win32 后端依赖。
# 另：文档排除清单中的 'xml' 已移除——openpyxl.xml.functions 硬依赖
# xml.etree.ElementTree，排除后 EXE 启动即报 ModuleNotFoundError。

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pynput.keyboard._win32', 'pynput.mouse._win32'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'email', 'http', 'pydoc',
        'pandas', 'numpy', 'matplotlib', 'scipy',
        'PyQt5.QtNetwork', 'PyQt5.QtWebEngine', 'PyQt5.QtQml',
        'PyQt5.QtQuick', 'PyQt5.QtSql', 'PyQt5.QtMultimedia'
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RuntimeBrokerHost',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python3.dll'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
)
