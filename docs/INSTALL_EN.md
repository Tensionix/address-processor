# Install and Launch

[Русский](INSTALL_RU.md) · [User Guide](USER_GUIDE_EN.md) · [Reference](REFERENCE_EN.md)

**Contents**

- [Requirements](#requirements)
- [Launching](#launching)
- [Building the Environment](#building-the-environment)
- [Dependencies](#dependencies)
- [Project Folders](#project-folders)
- [Maintenance](#maintenance)
- [Before a Large Run](#before-a-large-run)

The project is portable: it is not installed into the system, writes nothing to
the registry, and lives entirely inside its own folder. Copying the folder to
another machine is a sufficient "install".

---

## Requirements

**Windows.** The program targets Windows: moving columns by address works through
Excel, and the window runs on the system Edge WebView2 engine.

**Excel.** Needed only by the "Move columns by address" command — it is what
preserves the formulas, formatting, and row order of the primary workbook. Every
other command works without Excel.

**Internet.** Needed once to build the environment, and occasionally afterwards
to download the OKTMO registry.

A built portable project needs nothing else: Python lives inside, in the
`runtime` folder.

---

## Launching

| Way | What it does |
| --- | --- |
| `Start.exe` | Open the program window |
| `launcher_gui.cmd` | The same |
| `launcher_project.cmd` | Project menu: runs, settings, build |
| `launcher_project_ru.cmd` | The same menu in Russian |
| `launcher_tools.cmd` | Service menu: environment check, licenses, release |
| `builder_main.cmd` | Portable environment build |

The window launcher looks for Python in this order:

1. `runtime\pythonw.exe`
2. `runtime\python.exe`
3. `runtime\python\pythonw.exe`
4. `runtime\python\python.exe`
5. a system `py -3.12`

The resolved interpreter raises a local server on `127.0.0.1:8080` and opens a
window on the Edge WebView2 engine. The window process id is written to
`logs/gui_server.pid`.

### If the Window Does Not Open

Set `AUDION_GUI_CONSOLE=1` and run the launcher again — it opens in a console and
the error messages become visible:

```bat
set AUDION_GUI_CONSOLE=1 && launcher_gui.cmd
```

Common causes:

* **The environment is not built.** There is no `python.exe` in `runtime` — build
  the environment.
* **Port 8080 is taken.** The window comes up on another port or not at all; free
  the port.
* **No WebView2.** The component ships with modern Windows; on older builds it is
  installed separately. As a fallback, the window opens in a browser.

---

## Building the Environment

Needed only when the project arrived without a `runtime` folder, or when you
rebuild it.

`builder_main.cmd` is the build menu:

| Item | What it does |
| --- | --- |
| `[01] PYTHON ENV CMD` | Build the portable environment (the main path) |
| `[02] PYTHON ENV PS` | The same via PowerShell |
| `[03] FZF` | Install or update `system_core\fzf.exe` for the launcher menus |
| `[09] PORTABLE OFFLINE` | Install from the local `wheelhouse` without network |
| `[70] CLEAN INSTALL CACHE` | Clean the build cache; the built runtime survives |
| `[71] VERIFY / DOCTOR` | Check the environment and imports |
| `[77] MAKE RELEASE ARCHIVE` | Build a release archive |

### Installing Without Internet

If the project carries a `wheelhouse` folder with dependency wheels, the
environment is built from it: `install\install_portable_offline.cmd` or menu item
`[09] PORTABLE OFFLINE`.

### Verification

`[71] VERIFY / DOCTOR` — or `install\verify_portable_env.cmd` — checks the
interpreter and the import of every dependency. It is the first thing to run when
something does not work.

---

## Dependencies

| Package | What for |
| --- | --- |
| `pandas` | Table operations |
| `openpyxl` | Reading and writing XLSX |
| `rapidfuzz` | Approximate comparison of street names |
| `pymorphy3`, `pymorphy3-dicts-ru` | Grammatical forms of settlement names |
| `PyMuPDF` | PDF text layer |
| `pywin32` | Excel automation for column transfer |
| `nicegui`, `pywebview` | The program window |
| `pyyaml` | Configuration files |
| `tqdm`, `rich` | Progress and log output |
| `pytest`, `beautifulsoup4` | Tests |

License texts of every third-party component live in `licenses/`.

---

## Project Folders

| Folder | Contents | Safe to clean |
| --- | --- | --- |
| `system_core` | Source code | No |
| `config` | Settings, OKTMO keys and pins | No |
| `data` | OKTMO registry and region reference | The registry can be re-downloaded |
| `runtime` | Portable Python | Rebuildable |
| `wheelhouse` | Wheels for offline install | Yes |
| `input` | Source files | Yes |
| `output` | Results | Yes |
| `report` | Run reports | Yes |
| `logs` | Logs | Yes |
| `workspace` | Intermediate files | Yes |
| `release` | Result archives | Yes |
| `docs` | Documentation | No |
| `licenses` | Third-party licenses | No |
| `tests` | Tests | No |

Initial creation of the working folders: `install\init_folders.cmd`.

---

## Maintenance

**Project cleanup.** `cleanup_project.cmd` removes generated artifacts: caches,
temporary conversions, logs, reports, and the rebuildable runtime. Code,
settings, documentation, sources, results, and approved references are kept.

**CMD file encoding.** After editing any `.cmd`, run
`install\Check-CmdEncoding.cmd`: the files must stay UTF-8 without BOM with CRLF
line endings. Otherwise Cyrillic in the menus turns into garbage.

**Dependency updates.** `install\Update-Requirements-Lock.cmd` regenerates the
lock file.

**The OKTMO registry** is not updated from here but by a button in the window —
see [OKTMO](OKTMO_EN.md).

---

## Before a Large Run

Check the environment (`VERIFY / DOCTOR`), work with copies of important tables,
and keep sources, reference, and results in separate folders.

Make the first run on a new dataset over a dozen rows whose answer you know in
advance.
