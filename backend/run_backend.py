"""Entry point of the packaged backend (PyInstaller, desktop app): same as python -m f14api."""
import multiprocessing

from f14api.__main__ import main

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
