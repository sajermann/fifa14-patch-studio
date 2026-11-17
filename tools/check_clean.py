"""Checks the files git would publish: no game files, no big binaries, no absolute paths of a machine, no forbidden
words. The forbidden words live OUTSIDE this repository (a plain text file, one word per line), so the list itself is
never published:

    python tools/check_clean.py [--words <file>]        (default: the F14_FORBIDDEN_WORDS environment variable)

Exit code 1 when something is found."""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_EXTENSIONS = {'.big', '.bh', '.db', '.dds', '.rx3', '.ttf', '.sma', '.sh', '.exe', '.dll', '.zip'}
ALLOWED_BINARIES = {'.png', '.ico'}  # the app's own icons
MAX_SIZE = 2 * 1024 * 1024
ABSOLUTE_PATH = re.compile(r'(?<![A-Za-z])[A-Za-z]:\\\\?(?:Users|Coding|Games|Program Files)|/(?:home|Users)/[a-z]', re.I)
TEXT_EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.json', '.md', '.txt', '.html', '.css', '.yml', '.yaml', '.toml',
                   '.rs', '.ps1', '.bat', '.nsh', '.spec', '.cfg', '.ini', ''}


def published_files():
    out = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--words', default=os.environ.get('F14_FORBIDDEN_WORDS'))
    args = ap.parse_args()
    words = []
    if args.words:
        with open(args.words, encoding='utf-8') as f:
            words = [w.strip().lower() for w in f if w.strip() and not w.startswith('#')]
    problems = []
    for rel in published_files():
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(rel)[1].lower()
        if ext in GAME_EXTENSIONS:
            problems.append(f'{rel}: game file type')
            continue
        if os.path.getsize(full) > MAX_SIZE:
            problems.append(f'{rel}: larger than {MAX_SIZE // 1024 // 1024} MB')
        if ext in ALLOWED_BINARIES or ext not in TEXT_EXTENSIONS or rel.endswith('package-lock.json'):
            continue
        with open(full, encoding='utf-8', errors='replace') as f:
            text = f.read()
        if rel != 'tools/check_clean.py':
            for m in ABSOLUTE_PATH.finditer(text):
                line = text.count('\n', 0, m.start()) + 1
                problems.append(f'{rel}:{line}: absolute path ({m.group(0)})')
        low = text.lower()
        for w in words:
            if w in low:
                line = text.count('\n', 0, low.index(w)) + 1
                problems.append(f'{rel}:{line}: forbidden word')
    for p in problems:
        print(p)
    print(f'{len(problems)} problem(s)' + ('' if words else ' (no forbidden words list given)'))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
