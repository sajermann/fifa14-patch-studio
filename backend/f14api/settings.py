"""Paths and the local user configuration (config.json in the data folder, never in git)."""
import json
import logging
import os
import sys
from typing import Literal, Optional

from pydantic import BaseModel, field_validator

log = logging.getLogger('f14api')

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(BACKEND_DIR)
CORE_DIR = os.path.join(APP_DIR, 'core')
FROZEN = getattr(sys, 'frozen', False)  # packaged backend (PyInstaller, desktop app)
FRONTEND_DIST = (os.path.join(sys._MEIPASS, 'frontend_dist') if FROZEN
                 else os.path.join(APP_DIR, 'frontend', 'dist'))
# the app's own data (config, project, caches, built patch): backend/data in development; the desktop app sets it
DATA_DIR = os.environ.get('F14_DATA_DIR') or (
    os.path.join(os.path.dirname(sys.executable), 'data') if FROZEN else os.path.join(BACKEND_DIR, 'data'))
CONFIG_PATH = os.environ.get('F14_CONFIG', os.path.join(DATA_DIR, 'config.json'))
LOG_DIR = os.path.join(DATA_DIR, 'logs')
CACHE_DIR = os.path.join(DATA_DIR, 'cache')          # can be deleted at any time
PROJECT_DIR = os.path.join(DATA_DIR, 'project')      # the user's work
PATCH_DIR = os.environ.get('F14_PATCH_DIR') or os.path.join(DATA_DIR, 'patch')  # the last built patch


def _version() -> str:
    """The desktop app passes its version; in development it comes from desktop/src-tauri/tauri.conf.json."""
    if os.environ.get('F14_APP_VERSION'):
        return os.environ['F14_APP_VERSION']
    try:
        with open(os.path.join(APP_DIR, 'desktop', 'src-tauri', 'tauri.conf.json'), encoding='utf-8') as f:
            return json.load(f).get('version') or '0.0.0'
    except (OSError, ValueError):
        return '0.0.0'


APP_VERSION = _version()

if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

from f14mod import workers  # noqa: E402 - after the core folder is on the path

Language = Literal['pt-BR', 'en']
GAME_LANGUAGE_OF = {'pt-BR': 'por_br', 'en': 'eng_us'}
TERMS_VERSION = 1  # bump when the text of the first-run notice changes: everyone accepts it again


class Config(BaseModel):
    language: Optional[Language] = None  # interface language
    game_dir: Optional[str] = None       # the FIFA 14 installation the app patches
    names_language: Optional[str] = None  # game language the lists show names in (None = the interface's)
    face_pack_dirs: list[str] = []         # folders of face packs (one folder = one pack, read in place)
    # where the project lives (the Street Studio's project folder). Added 20/11/2026, optional: None = PROJECT_DIR,
    # older files load unchanged. A new folder starts an empty project there; the old one stays where it was
    project_dir: Optional[str] = None
    # what the build may use (f14mod.workers; None = the defaults). Added 19/11/2026, optional: older files load
    # unchanged; out-of-range values (more cores than the machine has, memory outside 10-90%) are brought into range
    build_cores: Optional[int] = None
    build_memory_percent: Optional[int] = None
    # version of the first-run notice the user accepted (TERMS_VERSION). Added 20/11/2026, optional: older files
    # load unchanged and show the first-run screen once
    terms_version: Optional[int] = None

    @field_validator('build_cores', mode='after')
    @classmethod
    def _cores_in_range(cls, v):
        return workers.clamp_cores(v)

    @field_validator('build_memory_percent', mode='after')
    @classmethod
    def _memory_in_range(cls, v):
        return workers.clamp_memory_percent(v)

    def project_folder(self) -> str:
        return self.project_dir or PROJECT_DIR

    def shown_language(self) -> str:
        return self.names_language or GAME_LANGUAGE_OF.get(self.language or 'en', 'eng_us')


def load() -> Config:
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return Config.model_validate(json.load(f))
    except FileNotFoundError:
        return Config()
    except (OSError, ValueError) as e:  # a damaged file: start with the defaults, keep the file for the user
        log.warning('config.json not read (%s): using the defaults', e)
        return Config()


def save(cfg: Config) -> Config:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg.model_dump(), f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)
    return cfg
