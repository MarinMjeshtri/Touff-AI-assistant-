# PyInstaller spec: one folder with Touff.exe (tray app, no console) and touff-cli.exe
# (the same program with a console, for --download, --install-voice-pack, --text ...).
# Build with packaging\build.ps1, which also draws the icon and finds uv.exe.
import os
import re
import shutil
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

HERE = Path(SPECPATH)
APP = HERE.parent
PKG = APP / "touff"
ICON = HERE / "build" / "touff.ico"
VERSION = re.search(r'__version__ = "([^"]+)"', (PKG / "__init__.py").read_text()).group(1)
UV = os.environ.get("TOUFF_UV") or shutil.which("uv")
if not UV:
    raise SystemExit("uv.exe not found (it is shipped to build the voice pack): install uv or set TOUFF_UV")

datas = [
    (str(PKG / "ui" / "web"), "touff/ui/web"),  # the whole folder, whatever the UI adds
    (str(PKG / "voice_server.py"), "touff"),  # run by the voice pack's Python, not imported
    (UV, "."),
]
# Piper: espeak-ng-data. The Hebrew/Arabic helper models are skipped (English voices only).
datas += collect_data_files("piper", excludes=["hebrew/*.onnx", "tashkeel/*.onnx", "train/**", "img/**"])
datas += collect_data_files("faster_whisper")  # Silero VAD model
datas += collect_data_files("webview")  # WebView2 interop DLLs + js
binaries = collect_dynamic_libs("vosk") + collect_dynamic_libs("ctranslate2")
hiddenimports = [
    "webview.platforms.winforms", "webview.platforms.edgechromium", "clr",
    "pystray._win32", "_cffi_backend", "piper.espeakbridge",
] + collect_submodules("touff", filter=lambda name: name != "touff.voice_server")

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(APP)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(HERE / "hooks")],
    excludes=["tkinter", "pytest", "PyInstaller"],
)
pyz = PYZ(a.pure)

nums = tuple(int(n) for n in re.findall(r"\d+", VERSION)[:3]) + (0,) * 4
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=nums[:4], prodvers=nums[:4]),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("ProductName", "Touff"),
            StringStruct("FileDescription", "Touff voice assistant"),
            StringStruct("FileVersion", VERSION),
            StringStruct("ProductVersion", VERSION),
            StringStruct("OriginalFilename", "Touff.exe"),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)
common = dict(exclude_binaries=True, strip=False, upx=False, icon=str(ICON), version=version_info)
gui = EXE(pyz, a.scripts, [], name="Touff", console=False, **common)
cli = EXE(pyz, a.scripts, [], name="touff-cli", console=True, **common)
COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name="Touff")
