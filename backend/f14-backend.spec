# PyInstaller spec of the packaged backend used by the desktop app (desktop/).
# Build from backend/ (after npm run build in frontend/):  python -m PyInstaller --noconfirm f14-backend.spec
# Output: backend/dist/f14-backend/ (f14-backend.exe + _internal/), bundled by Tauri as a resource.
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['run_backend.py'],
    pathex=['.', '../core'],
    datas=[('../frontend/dist', 'frontend_dist')],
    # uvicorn picks its loop/protocol implementations by name at runtime
    hiddenimports=collect_submodules('uvicorn') + collect_submodules('f14mod') + collect_submodules('f14api'),
    excludes=['pytest', 'httpx'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='f14-backend',
    console=True,  # started hidden by the desktop app; its output goes to the log file
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='f14-backend', upx=False)
