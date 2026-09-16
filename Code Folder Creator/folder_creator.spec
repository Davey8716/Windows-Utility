# PyInstaller build contract for the bundled Windows Resurface companion.
# The EXE builder should build this spec and place its output at
# <release root>/Code Folder Creator/Folder Creator.exe.

from pathlib import Path


SOURCE_ROOT = Path(SPECPATH).resolve().parent
REPOSITORY_ROOT = SOURCE_ROOT.parent

analysis = Analysis(
    [str(SOURCE_ROOT / "main.py")],
    pathex=[str(SOURCE_ROOT), str(REPOSITORY_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    [],
    name="Folder Creator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
