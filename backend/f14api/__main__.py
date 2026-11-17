"""python -m f14api [--port 8773] [--no-browser] [--parent-pid PID]
python -m f14api --dialog <json>: shows one Windows dialog and prints the answer (f14api.dialogs; the server runs it)."""
import argparse
import ctypes
import logging
import os
import platform
import sys
import threading
import webbrowser

import uvicorn

from . import dialogs, settings

log = logging.getLogger('f14api')

LOG_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {'()': 'uvicorn.logging.DefaultFormatter', 'use_colors': False,
                    'fmt': '%(asctime)s %(levelprefix)s %(message)s', 'datefmt': '%Y-%m-%d %H:%M:%S'},
        'access': {'()': 'uvicorn.logging.AccessFormatter', 'use_colors': False,
                   'fmt': '%(asctime)s %(levelprefix)s "%(request_line)s" %(status_code)s',
                   'datefmt': '%Y-%m-%d %H:%M:%S'},
    },
    'handlers': {
        'default': {'formatter': 'default', 'class': 'logging.StreamHandler', 'stream': 'ext://sys.stderr'},
        'access': {'formatter': 'access', 'class': 'logging.StreamHandler', 'stream': 'ext://sys.stdout'},
    },
    'loggers': {
        'uvicorn': {'handlers': ['default'], 'level': 'INFO', 'propagate': False},
        'uvicorn.error': {'level': 'INFO'},
        'uvicorn.access': {'handlers': ['access'], 'level': 'WARNING', 'propagate': False},
        'f14api': {'handlers': ['default'], 'level': 'INFO', 'propagate': False},
    },
}


def exit_with_parent(pid):
    """Desktop app: the backend ends when the window process ends, even if it crashed and could not stop us."""
    synchronize, infinite = 0x00100000, 0xFFFFFFFF
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        os._exit(0)

    def wait():
        ctypes.windll.kernel32.WaitForSingleObject(handle, infinite)
        os._exit(0)
    threading.Thread(target=wait, daemon=True).start()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == dialogs.DIALOG_ARG:  # child process of one dialog, not the server
        dialogs.run_child(sys.argv[2])
        return
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8773)
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--parent-pid', type=int)
    args = ap.parse_args()
    import logging.config
    logging.config.dictConfig(LOG_CONFIG)
    log.info('version %s | python %s | %s | data folder %s', settings.APP_VERSION, platform.python_version(),
             platform.platform(), settings.DATA_DIR)
    if args.parent_pid:
        exit_with_parent(args.parent_pid)
    from .main import app
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (f'http://localhost:{args.port}',)).start()
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_config=LOG_CONFIG)


if __name__ == '__main__':
    main()
