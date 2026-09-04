from __future__ import annotations

from pathlib import Path
import importlib
import platform
import shutil
import sys

REQUIRED_MODULES = [
    ("pandas", "pandas"),
    ("rapidfuzz", "rapidfuzz"),
    ("openpyxl", "openpyxl"),
    ("tqdm", "tqdm"),
    ("nicegui", "nicegui"),
    ("yaml", "pyyaml"),
    ("rich", "rich"),
    ("setuptools", "setuptools"),
    ("wheel", "wheel"),
    ("packaging", "packaging"),
    ("webview", "pywebview"),
]

OPTIONAL_MODULES: list[tuple[str, str]] = []


def check_module(import_name: str) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(import_name)
        version = getattr(mod, "__version__", "unknown")
        return True, str(version)
    except Exception as exc:
        return False, exc.__class__.__name__


def detect_python_mode(root: Path) -> str:
    if (root / "runtime" / "python.exe").exists():
        return "portable-runtime"
    if (root / "runtime" / "python" / "python.exe").exists():
        return "portable-runtime"
    return "system-python"


def check_picker_powershell(root: Path) -> tuple[bool, list[tuple[str, bool, str]]]:
    candidates = [
        ("portable pwsh", root / "system_core" / "powershell" / "pwsh.exe"),
        ("PATH pwsh", "pwsh.exe"),
        ("Windows PowerShell", "powershell.exe"),
    ]
    rows: list[tuple[str, bool, str]] = []
    any_ok = False
    for label, candidate in candidates:
        if isinstance(candidate, Path):
            ok = candidate.exists()
            detail = str(candidate)
        else:
            resolved = shutil.which(candidate)
            ok = bool(resolved)
            detail = resolved or "not found"
        rows.append((label, ok, detail))
        any_ok = any_ok or ok
    return any_ok, rows


def check_manifest_operations(root: Path) -> tuple[bool, list[tuple[str, str, str]]]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        from system_core.core.manifest import load_manifest
    except Exception as exc:
        return False, [("(loader)", "MANIFEST_FAIL", f"{exc.__class__.__name__}: {exc}")]

    manifest_path = root / "config" / "tool_manifest.yaml"
    if not manifest_path.exists():
        return False, [("(loader)", "MANIFEST_FAIL", f"Not found: {manifest_path}")]

    try:
        manifest = load_manifest(manifest_path)
    except Exception as exc:
        return False, [("(loader)", "MANIFEST_FAIL", f"{exc.__class__.__name__}: {exc}")]

    rows: list[tuple[str, str, str]] = []
    all_ok = True
    for operation in [*manifest.operations, *manifest.maintenance_operations]:
        if ":" not in operation.service:
            rows.append((operation.id, "BAD_SYNTAX", operation.service))
            all_ok = False
            continue

        module_name, function_name = operation.service.split(":", 1)
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            rows.append((operation.id, "IMPORT_FAIL", f"{module_name} ({exc.__class__.__name__})"))
            all_ok = False
            continue

        if not hasattr(module, function_name):
            rows.append((operation.id, "MISSING_FUNC", f"{module_name}:{function_name}"))
            all_ok = False
            continue

        if not callable(getattr(module, function_name)):
            rows.append((operation.id, "NOT_CALLABLE", f"{module_name}:{function_name}"))
            all_ok = False
            continue

        rows.append((operation.id, "OK", operation.service))

    return all_ok, rows


def check_cmd_encoding(root: Path) -> tuple[bool, list[tuple[str, bool, str]]]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        from system_core.core.cmd_encoding import check_cmd_files
    except Exception as exc:
        return False, [("(loader)", False, f"{exc.__class__.__name__}: {exc}")]

    rows: list[tuple[str, bool, str]] = []
    all_ok = True
    for result in check_cmd_files(root):
        try:
            relative = str(result.path.resolve().relative_to(root.resolve()))
        except ValueError:
            relative = str(result.path)
        detail = result.summary()
        if result.error:
            detail = f"{detail} {result.error}"
        rows.append((relative, result.ok, detail))
        if not result.ok:
            all_ok = False
    return all_ok, rows


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    print("======================================================================")
    print("AUDION ADDRESS ALIGNER - DOCTOR")
    print("======================================================================")
    print(f"Project root : {root}")
    print(f"Executable   : {sys.executable}")
    print(f"Python       : {sys.version.split()[0]}")
    print(f"Python mode  : {detect_python_mode(root)}")
    print(f"Platform     : {platform.platform()}")
    print()

    failed = False

    print("[Required modules]")
    for import_name, package_name in REQUIRED_MODULES:
        ok, detail = check_module(import_name)
        status = "OK" if ok else "FAIL"
        print(f"  - {package_name:<18} : {status:<4} {detail}")
        if not ok:
            failed = True

    print()
    print("[GUI portability]")
    picker_ok, picker_rows = check_picker_powershell(root)
    for label, ok, detail in picker_rows:
        status = "OK" if ok else "MISS"
        print(f"  - {label:<18} : {status:<4} {detail}")
    if not picker_ok:
        print("  - picker dialogs     : FAIL PowerShell was not found")
        failed = True
    else:
        print("  - picker dialogs     : OK   PowerShell-backed Windows dialogs available")

    print()
    print("[Optional modules]")
    for import_name, package_name in OPTIONAL_MODULES:
        ok, detail = check_module(import_name)
        status = "OK" if ok else "MISS"
        print(f"  - {package_name:<18} : {status:<4} {detail}")

    print()
    print("[Manifest operations]")
    manifest_ok, rows = check_manifest_operations(root)
    if not rows:
        print("  (no operations found)")
    else:
        for op_id, status, detail in rows:
            print(f"  - {op_id:<22} : {status:<13} {detail}")
    if not manifest_ok:
        failed = True

    print()
    print("[CMD encoding]")
    cmd_ok, cmd_rows = check_cmd_encoding(root)
    if not cmd_rows:
        print("  (no CMD files found)")
    else:
        for relative, result_ok, detail in cmd_rows:
            status = "OK" if result_ok else "FAIL"
            print(f"  - {relative:<58} : {status:<4} {detail}")
    if not cmd_ok:
        failed = True

    print()
    if failed:
        print("[RESULT] One or more checks failed.")
        return 1

    print("[RESULT] Required environment looks good.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
