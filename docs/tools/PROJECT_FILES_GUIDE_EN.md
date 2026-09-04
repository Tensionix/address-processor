# Project File Map

[Русский](PROJECT_FILES_GUIDE_RU.md) · [Reference](../REFERENCE_EN.md) · [Install](../INSTALL_EN.md)

Where everything lives. This document is for whoever maintains the project; a
user does not need it.

Working folders (`input`, `output`, `logs`, `report`, `release`, `workspace`,
`runtime`, `wheelhouse`) are described by role rather than file by file — their
contents are produced by runs and rebuilt.

---

## Root

| File | What it is |
| --- | --- |
| `Start.exe` | Compiled window launcher |
| `launcher_gui.cmd` | Window launcher |
| `launcher_project.cmd` | Project menu, English |
| `launcher_project_ru.cmd` | Project menu, Russian |
| `launcher_tools.cmd` | Service menu: doctor, licenses, release |
| `builder_main.cmd` | Portable environment build |
| `cleanup_project.cmd` | Cleanup of generated artifacts |
| `pytest.ini` | Test settings |
| `release_manifest.json` | Manifest of the last release build |
| `README.md` | Public project description |

CMD files must stay UTF-8 without BOM with CRLF line endings. After editing, run
`install\Check-CmdEncoding.cmd`.

---

## `config` — Settings

| File | What it is |
| --- | --- |
| `project.yaml` | Engine settings: city, reference column, target columns, linked columns, safety limits |
| `gui_settings.yaml` | Language, theme, window behaviour |
| `tool_manifest.yaml` | Every command and field of the window; the interface is built from it |
| `version.json` | Version and the language of the root README |
| `ui_colors.yaml` | Interface colours |
| `path_history.json` | History and pins of source and target paths |
| `oktmo_current_keys.txt` | Current OKTMO search keys |
| `oktmo_region_pins.json` | Pinned regions |
| `oktmo_municipality_pins.json` | Pinned municipalities |
| `oktmo_pins_bundle.json` | The combined pin set |

---

## `system_core` — Code

### Top Level

| File | What it does |
| --- | --- |
| `Ultimate_GT_Aligner.py` | The matching engine: address parsing, passes, linked column transfer |
| `safe_table_join.py` | Comparison of two workbooks and column transfer through Excel |
| `excel_layout.py` | Result workbook formatting: column widths, text wrap, fill |
| `remove_empty_rows.py` | Removal of entirely empty rows |
| `Parser_Diagnostic.py` | Address parsing diagnostics |
| `inspect_md_tables.py` | Markdown table inspection |
| `doctor.py` | Environment and import checks |
| `main.py` | Direct matching run without the window |
| `fzf.exe` | Menu for the CMD launchers |

### `address_engine` — The Address Engine

| File | What it does |
| --- | --- |
| `audion_address_core.py` | Address decomposition, recognition of address-like text |
| `address_slots.py` | Slots: definition, filling, address line assembly |
| `slot_fill.py` | Filling slots from evidence |
| `models.py` | Data structures: observation, address parts, fingerprint, cluster |
| `source_intake.py` | Reading sources in every supported format |
| `source_table_assembly.py` | Collecting addresses from sources into a workbook |
| `source_cleanup.py` | Filtering out Office temporary files |
| `reference_builder.py` | Building the reference directory; slot and column definitions |
| `reference_processor.py` | Sorting and decomposing the directory by slots |
| `oktmo_lookup.py` | OKTMO index, disk cache, region / municipality / settlement lookup |
| `oktmo_user_keys.py` | The project key file and pins |
| `rosstat_update.py` | Downloading and updating the Rosstat registry |
| `region_reference.py` | Region reference |
| `russian_morphology.py` | Grammatical forms of names |
| `universal_address.py` | The common address normalizer |
| `normalizer_runtime.py` | Configuring the normalizer per run |
| `address_diagnostics.py` | Diagnostic extracts |
| `legacy_office_converter.py` | DOC/XLS conversion |

### `services` — The Service Layer

`address_aligner_service.py` is the only file. Every window command points to a
function here: the service takes the parameters, calls the engine, and writes the
log, the report, and the artifact list.

### `ui_nicegui` — The Window

| File | What it does |
| --- | --- |
| `window.py` | Window wrapper: port, icon, WebView2 engine |
| `app.py` | The interface itself: commands, fields, log, OKTMO panels |
| `workbench.py` | Source and target, path history, pins |
| `i18n.py` | Language switching |
| `tokens.css`, `base.css`, `theme.css` | Styling |

### `core` — Core

| File | What it does |
| --- | --- |
| `jobs.py` | Running operations, cancellation, progress |
| `manifest.py` | Parsing `tool_manifest.yaml` |
| `paths.py` | Managed project folders |
| `config.py` | Reading settings |
| `ui_settings.py` | Window settings |
| `ansi_terminal.py` | Terminal output into the log |
| `cmd_encoding.py` | CMD encoding checks |
| `output_decode.py` | Decoding subprocess output |
| `logging_utils.py` | Logging |

### Other

| Path | What it is |
| --- | --- |
| `license/` | Collection, deduplication, and pruning of third-party licenses |
| `icons/` | Window icons |
| `start_launcher/` | Source of `Start.exe` |
| `powershell/` | Helper scripts |

---

## `install` — Install and Build

| File | What it does |
| --- | --- |
| `Build_Portable_Env.cmd` / `.ps1` | Portable environment build |
| `install_portable_offline.cmd` | Install from the local `wheelhouse` |
| `verify_portable_env.cmd` | Verify the built environment |
| `init_folders.cmd` | Create the working folders |
| `Check-CmdEncoding.cmd`, `Repair-CmdEncoding.ps1` | Check and repair CMD encodings |
| `Clean-Install-Cache.cmd` / `.ps1` | Clean the build cache |
| `Update-Requirements-Lock.cmd` | Update the dependency lock file |
| `make_release_archive.cmd` | Build the release archive |
| `Build-StartLauncher.cmd` / `.ps1` | Build `Start.exe` |
| `launcher-tools-update_fzf.cmd` | Update `fzf.exe` |
| `requirements_full.in` | Dependency list |
| `README_INSTALL.md` | Install notes |

---

## `data` — Data

| Path | What it is |
| --- | --- |
| `regions_reference.yaml` | Region reference |
| `rosstat/data-*.csv` | The OKTMO registry, downloaded by a button in the window |
| `rosstat/oktmo_lookup_cache.json` | The parsed OKTMO index |

---

## `docs` — Documentation

| File | What it is |
| --- | --- |
| `README_RU.md`, `README_EN.md` | Project description, the entry point |
| `USER_GUIDE_RU.md`, `USER_GUIDE_EN.md` | User guide |
| `OKTMO_RU.md`, `OKTMO_EN.md` | The OKTMO registry, keys, and pins |
| `REFERENCE_RU.md`, `REFERENCE_EN.md` | Technical reference |
| `INSTALL_RU.md`, `INSTALL_EN.md` | Install and launch |
| `tools/PROJECT_FILES_GUIDE_*.md` | This document |
| `PDF/` | Rendered PDFs of every document in two themes |

PDFs are built by a separate tool from every `.md` in `docs`, nested folders
included. The folder structure is preserved.

---

## `tests` — Tests

| File | What it covers |
| --- | --- |
| `test_address_aligner_regression.py` | The matching passes |
| `test_safe_table_join.py` | Moving columns by address |
| `test_excel_layout.py` | Result workbook formatting |
| `test_gui_render.py` | Window rendering |
| `test_workbench_route_regression.py` | Source and target |
| `test_ansi_terminal.py` | Terminal output |

The window is tested with NiceGUI's headless fixture, parsing the rendered page
with BeautifulSoup; selenium is deliberately not used.

---

## `licenses` — Licenses

License texts of third-party components, `THIRD_PARTY_NOTICES.txt`,
`COMPONENTS.json`, the scan report, and the pack manifest. Produced by the tools
in `system_core/license/`.
