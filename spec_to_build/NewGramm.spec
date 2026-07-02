# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

VLC_PATH = r"C:\Program Files\VideoLAN\VLC"   # <-- ИЗМЕНИТЕ ПРИ НЕОБХОДИМОСТИ

a = Analysis(
    ['client.py'],
    pathex=[],
    binaries=[
        # Добавляем основные DLL-файлы VLC
        (f"{VLC_PATH}\\libvlc.dll", "."),
        (f"{VLC_PATH}\\libvlccore.dll", "."),
    ],
    datas=[
        # Добавляем ВСЮ папку plugins (это важно!)
        (f"{VLC_PATH}\\plugins", "plugins"),
        ('server_addr.txt', '.'),
    ],
    hiddenimports=[
        'imageio',
        'imageio_ffmpeg',
        'imageio.plugins',
        'imageio.plugins.ffmpeg',
        'moviepy.audio.fx.all',
        'moviepy.video.fx.all',
        'moviepy.video.io.VideoFileClip',
        'moviepy.audio.io.AudioFileClip',
        'PIL',
        'PIL.Image',
    ],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=['runtime_hook.py'],  # <--- ДОБАВЬТЕ ЭТУ СТРОКУ
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NewGramm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # Временно True для отладки (увидите сообщения хука)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='NewGramm'
)