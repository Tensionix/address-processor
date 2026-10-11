# Audion Address Processor - install notes

## What a build is for

`builder_main.cmd` refreshes the components the program is assembled from: the
embedded Python in `runtime\` and its packages, kept as wheels in `wheelhouse\`.
`cleanup_project.cmd` empties both; a build brings back the current ones.

`App\` - the window and the PowerShell the program carries (`AudionPs.exe`) - is
not a product of a build. It stays through a cleanup and travels in a release as
it is. `install\Build-App.cmd` (builder step `[05]`) rebuilds it, and only after
a change in `Source\`; that needs the .NET 10 SDK.

## Main build paths

### CMD route
Run:

```bat
builder_main.cmd
```

or directly:

```bat
install\Build_Portable_Env_Build.cmd
```

This is the main CMD build script: `curl.exe` and `tar.exe`. When one of them is
missing it hands the work to the PowerShell route.

### PowerShell route
Run:

```bat
install\Build_Portable_Env.cmd
```

This is a thin wrapper for the same-name `Build_Portable_Env.ps1`.

The wrapper looks for PowerShell in:

1. `App\AudionPs.exe` - the PowerShell the program carries
2. `pwsh.exe` in `PATH`
3. `powershell.exe` in `PATH`

The script keeps to what all three have: no `Expand-Archive`, the archive of
Python is unpacked by .NET.

## Portable flow

1. Create folders
2. Resolve and download latest Python Embedded `3.12.x` ZIP
3. Extract to `runtime\`
4. Enable `import site` in `python3<minor>._pth`
5. Download `get-pip.py`
6. Build local `wheelhouse\`
7. Install packages into portable runtime
8. Verify with `system_core\doctor.py`

## Offline flow

If `runtime\` and `wheelhouse\` are already populated, run:

```bat
install\install_portable_offline.cmd
```

Then verify with:

```bat
install\verify_portable_env.cmd
```

---

## Builder Steps And Dependency Hygiene

`builder_main.cmd` uses fixed numeric entries:

```text
[01] PYTHON ENV CMD
[02] PYTHON ENV PS
[05] WINDOW
[09] PORTABLE OFFLINE
[70] CLEAN INSTALL CACHE
[71] VERIFY / DOCTOR
[95] OPEN install
[96] OPEN runtime
[97] OPEN wheelhouse
[98] OPEN licenses
[99] OPEN release
[00] EXIT
```

A release build runs three of them: `02:build_ps` brings Python and its packages
back, `71:verify` checks the environment, the console door and the built window,
`70:clean_cache` clears the cache of the install. Nothing is fetched from GitHub:
Python comes from python.org, the packages from PyPI. The .NET SDK is not needed.

`71:verify` does not build the window, it checks the one that travels in `App\`:
`AudionAddressProcessor.exe`, `AudionPs.exe` and `Start.exe` are in place, and the window
draws every operation and field of the manifest (`--self-check`). It is not asked
to carry the number of the project: the engine and the manifest move on from
version to version, the window is rebuilt only when `Source\` changes, and the
number it shows it reads from `config\version.json`. A manifest that brings
something new for the window is where a window that is not rebuilt falls behind -
the check says so.

Step bodies are read by the orchestrator, not only run from the menu: it finds a
step by its line `if /I "%RAW%"=="<code>" goto <LABEL>` and cuts everything
between the label and `goto MAIN` into its own batch file. A body must stand
alone.

Dependency hygiene rules:

- Python Embedded tracks the latest `3.12.x`; do not pin a concrete patch version in docs or scripts.
- Use the active embedded Python `_pth` file for path edits; do not hard-code a concrete filename.
- Bootstrap installs must include `setuptools`, `wheel`, and `packaging` before building or installing project wheels.
- A package the engine imports is listed in `install\requirements_full.in`. One installed into `runtime\` by hand works until the next cleanup; `tests\test_builder_steps.py` compares the imports of the engine with the list.
- `runtime\` and `wheelhouse\` are reproducible payloads. Install scripts may cleanly replace only their owned targets.
- `install\Clean-Install-Cache.cmd` / `.ps1` is the general install-cache cleanup. It removes transient `install\download\` artifacts (preserving `.gitkeep`, `get-pip.py`, and `7z*-extra.7z`), what building the window leaves in `Source\` (`bin` and `obj` of the window and of its PowerShell) and Python bytecode caches outside runtime, wheelhouse, `App\`, and user-data zones.
- `cleanup_project.cmd` is a separate source/release cleanup tool. It can remove runtime payloads and user-output zones after explicit confirmation; do not describe it as the general install-cache cleaner and do not wire it into install flow.
