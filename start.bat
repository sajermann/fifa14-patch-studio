@echo off
rem Starts the app in development mode (hot reload):
rem   backend: uvicorn with --reload on http://localhost:8773, in its own window
rem   frontend: Vite dev server on http://localhost:5177 (proxies /api to 8773), opened in the browser
rem Close both windows (or Ctrl+C) to stop.
cd /d "%~dp0backend"
python -c "import fastapi, uvicorn, numpy, PIL; assert tuple(int(x) for x in PIL.__version__.split('.')[:2]) >= (11, 2)" 2>nul || python -m pip install -r requirements.txt
if not exist "%~dp0frontend\node_modules" (
  pushd "%~dp0frontend"
  call npm install
  popd
)
start "FIFA 14 Patch Studio - backend" cmd /k python -m uvicorn f14api.main:app --host 127.0.0.1 --port 8773 --reload --reload-dir . --reload-dir ..\core\f14mod
cd /d "%~dp0frontend"
call npm run dev -- --open
