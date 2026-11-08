# Build on the target OS. PyInstaller is not a cross-compiler.
from pathlib import Path

project = Path(SPECPATH)
a = Analysis(
    [str(project / "run.py")],
    pathex=[str(project)], binaries=[],
    datas=[
        (str(project / "templates"), "templates"),
        (str(project / "static"), "static"),
        (str(project / "China-City-List-latest.csv"), "."),
        (str(project / "VERSION"), "."),
    ],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="Meteo-Command", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True, disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Meteo-Command")
