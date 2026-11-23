@echo off
rem Starts the app in development mode (hot reload), backend and frontend in this same window:
rem   [back]  uvicorn with --reload on http://localhost:8773 (restarts when a .py file changes)
rem   [front] Vite dev server on http://localhost:5177 (proxies /api to 8773), opened in the browser
rem Ctrl+C stops both.
cd /d "%~dp0backend"
python -c "import fastapi, uvicorn, numpy, PIL; assert tuple(int(x) for x in PIL.__version__.split('.')[:2]) >= (11, 2)" 2>nul || python -m pip install -r requirements.txt
if not exist "%~dp0frontend\node_modules\.bin\concurrently.cmd" (
  pushd "%~dp0frontend"
  call npm install
  popd
)
set PYTHONUNBUFFERED=1
cd /d "%~dp0frontend"
call node_modules\.bin\concurrently.cmd --kill-others --names back,front --prefix-colors cyan,green ^
  "cd ..\backend && python -m uvicorn f14api.main:app --host 127.0.0.1 --port 8773 --reload --reload-dir . --reload-dir ..\core\f14mod" ^
  "npm run dev -- --open"
