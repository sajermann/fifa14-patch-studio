"""What a bug report needs (the Street Studio's diagnostics): the user's machine and the support report (Settings >
"Copy report").

The desktop app sends the backend's output to <data>/logs/backend.log and keeps the run before as backend.prev.log
(desktop/src-tauri/src/main.rs); its own failures go to desktop.log.
"""
import os
import platform
import sys
from collections import deque

from . import settings

LOG_FILES = ('backend.log', 'backend.prev.log', 'desktop.log')
REPORT_TAIL_LINES = 400  # last lines of each log file in the report


def environment_lines() -> list[str]:
    win = sys.getwindowsversion() if sys.platform == 'win32' else None
    return [
        f'app version: {settings.APP_VERSION}',
        f'os: {platform.platform()} | {platform.machine()}'
        + (f' | build {win.build}, service pack "{win.service_pack}"' if win else ''),
        f'python: {platform.python_version()} | packaged: {settings.FROZEN}',
        f'data folder: {settings.DATA_DIR}',
        _machine_line(),
    ]


def _machine_line() -> str:
    try:
        from f14mod import workers
        info = workers.describe()
        return (f'machine: {info["cores"] or "unknown"} cores, {info["memory_mb"] or "unknown"} MB of memory, '
                f'{info["workers"]} build worker(s) by default')
    except Exception as e:  # noqa: BLE001 - the report must never fail for this line
        return f'machine: unknown ({type(e).__name__})'


def log_files() -> list[str]:
    """Log files of the desktop app that exist (none in development, where the log is the console)."""
    return [os.path.join(settings.LOG_DIR, name) for name in LOG_FILES
            if os.path.isfile(os.path.join(settings.LOG_DIR, name))]


def _tail(path: str, lines: int = REPORT_TAIL_LINES) -> str:
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return ''.join(deque(f, maxlen=lines))
    except OSError as e:
        return f'(could not read: {e})\n'


def report(sections: dict[str, list[str]]) -> str:
    """Plain-text support report: the machine, `sections` ({title: lines}, from the app's state) and the end of
    every log file."""
    out = ['FIFA 14 Patch Studio - support report', '']
    for title, lines in {'environment': environment_lines(), **sections}.items():
        out.append(f'== {title}')
        out.extend(f'  {line}' for line in lines)
        out.append('')
    files = log_files()
    if not files:
        out.append('(no log files: development runs log to the console)')
    for path in files:
        out.append(f'== {os.path.basename(path)} (last {REPORT_TAIL_LINES} lines)')
        out.append(_tail(path).rstrip('\n'))
        out.append('')
    return '\n'.join(out) + '\n'
