# FIFA 14 Patch Studio

Make your own patches for **FIFA 14 (PC)**: edit leagues, teams and players in a modern editor, build the patch and
install it into the game — and take it out again, leaving the game exactly as it was.

- **Always over the clean game.** The app checks the installation you choose and only works with a clean one (or one
  with a patch of this app installed): it needs the original files to build every patch.
- **One item at a time.** Open a team, change it, press **Save**. Leaving with unsaved changes asks first; what you
  saved is your project, kept apart from the game.
- **Names in every language.** The game has several names for each team (full, 15, 10, 7 and 3 letters, commentary)
  in each of its languages. Give one value for every language, and a value of its own only where a language needs it.
- **Fast with big databases.** The game's originals are read once into a local cache; every list, filter, search and
  page is answered by the backend and only what is on screen is loaded.
- **Install and uninstall.** Installing keeps a copy of every game file it replaces and a manifest in the game folder;
  uninstalling puts everything back. The game's big archives are never rewritten.

> Independent fan-made tool. Not affiliated with, sponsored or endorsed by Electronic Arts or FIFA; "FIFA" and
> "EA SPORTS" are trademarks of their respective owners. The app contains no game files: it only reads and changes the
> installation you provide. Keep a clean copy of your game as a backup.

## Use

Download the installer or the portable zip from the **Releases** page, open the app and choose your FIFA 14 folder.

## Development

Python 3.12+ and Node 22+:

```
start.bat
```

or by hand: `python -m f14api` in `backend/` (API and interface on http://localhost:8773) and `npm run dev` in
`frontend/` (http://localhost:5177).

- `core/f14mod/` — the game, no web: `gamefs` (loose files + BIG archives), `big` (read and rebuild), `bh` (the .bh
  indexes), `chunk`, `t3db` (fast database reading), `dbedit` (editable database with every CRC), `install_check`
  (is the installation usable), `catalog` (the originals cache, SQLite), `project` (the user's work, SQLite),
  `builder` (the patch) and `installer` (install / uninstall).
- `backend/f14api/` — FastAPI: game check and preparation, paged lists, details, saving, pictures, build/install jobs.
- `frontend/` — React + Vite + TypeScript + Tailwind + shadcn/ui; texts in `src/i18n/` (pt-BR and English).
- `desktop/` — Tauri packaging (see [desktop/README.md](desktop/README.md)).

How a patch reaches the game: a changed entry of an archive with a `.bh` index is written as a loose file and its
record in the `.bh` loses its hash words, so the game opens the loose file; the language archive
(`data/loc/locale.big`) has no index and is written whole.

Tests use a small invented installation built by the tests themselves (`core/tests/fakegame.py`), never a real one:

```
cd core && python -m pytest -q
cd backend && python -m pytest -q
```

Before publishing, `python tools/check_clean.py` checks that no game file, absolute path or private note slipped into
the repository.

## License

GPL v3 with an attribution term — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Suggestions and questions are welcome
in the Discussions tab ([CONTRIBUTING.md](CONTRIBUTING.md)).

---

## Português

Faça seus próprios patches para o **FIFA 14 (PC)**: edite ligas, times e jogadores num editor moderno, gere o patch e
instale no jogo — e tire de novo, deixando o jogo exatamente como estava.

- **Sempre sobre o jogo limpo.** O app verifica a instalação escolhida e só trabalha com uma limpa (ou com um patch
  deste app instalado): ele precisa dos arquivos originais para montar cada patch.
- **Um item de cada vez.** Abra um time, altere, clique em **Salvar**. Sair com alterações não salvas pede
  confirmação; o que você salva é o seu projeto, guardado à parte do jogo.
- **Nomes em todos os idiomas.** O jogo tem vários nomes para cada time (completo, 15, 10, 7 e 3 letras, narração) em
  cada idioma. Dê um valor para todos os idiomas e um valor próprio só onde um idioma precisar.
- **Rápido com bancos grandes.** Os originais do jogo são lidos uma vez para um cache local; listas, filtros, busca e
  páginas são respondidos pelo backend e só o que está na tela é carregado.
- **Instalar e desinstalar.** Instalar guarda uma cópia de cada arquivo do jogo que for trocado e um registro na pasta
  do jogo; desinstalar devolve tudo. Os arquivos grandes do jogo nunca são reescritos.

> Ferramenta independente feita por fãs. Não é afiliada, patrocinada nem aprovada pela Electronic Arts nem pela FIFA.
> O app não traz nenhum arquivo do jogo: ele só lê e altera a instalação que você tem. Guarde uma cópia limpa do jogo
> como backup.
