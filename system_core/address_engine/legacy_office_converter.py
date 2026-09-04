from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .source_cleanup import delete_office_temp_files
from .source_intake import discover_legacy_office_files


WORD_DOCX_FORMAT = 16
EXCEL_XLSX_FORMAT = 51
TEXT_DUPLICATE_SUFFIXES = {".pdf", ".txt", ".csv", ".md", ".markdown"}


@dataclass(frozen=True)
class LegacyConversionResult:
    converted: tuple[dict[str, str], ...]
    deleted: tuple[dict[str, str], ...]
    skipped: tuple[dict[str, str], ...]
    failed: tuple[dict[str, str], ...]


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[float], None]
CancelCallback = Callable[[], bool]


def convert_legacy_office_folder(
    input_dir: Path,
    *,
    overwrite: bool = False,
    delete_legacy_after_conversion: bool = True,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> LegacyConversionResult:
    converted: list[dict[str, str]] = []
    deleted: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    deleted.extend(
        {"source": str(record.path), "target": "", "reason": record.reason}
        for record in delete_office_temp_files(input_dir, log=log)
    )
    if delete_legacy_after_conversion:
        deleted.extend(_delete_same_stem_duplicate_sources(input_dir, log=log))

    files = discover_legacy_office_files(input_dir)
    if log:
        log(f"Legacy DOC/XLS files found: {len(files)}")
    if not files:
        return LegacyConversionResult(tuple(converted), tuple(deleted), tuple(skipped), tuple(failed))

    pythoncom, win32_client = _require_pywin32()
    pythoncom.CoInitialize()
    word = None
    excel = None
    try:
        for index, source in enumerate(files, start=1):
            if cancelled and cancelled():
                raise RuntimeError("Operation cancelled by user.")
            target = legacy_conversion_target(source)
            if progress:
                progress((index - 1) / max(1, len(files)))
            if target.exists() and not overwrite:
                if log:
                    log(f"[SKIP] Target exists: {target}")
                skipped.append({"source": str(source), "target": str(target), "reason": "target_exists"})
                if delete_legacy_after_conversion and target.stat().st_size > 0:
                    source.unlink()
                    if log:
                        log(f"[DELETE] Legacy duplicate removed: {source}")
                    deleted.append({"source": str(source), "target": str(target), "reason": "converted_target_exists"})
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.suffix.lower() == ".doc":
                    if word is None:
                        if log:
                            log("Starting Microsoft Word COM...")
                        word = _start_word_application(win32_client)
                    _convert_doc_to_docx(word, source, target)
                elif source.suffix.lower() == ".xls":
                    if excel is None:
                        if log:
                            log("Starting Microsoft Excel COM...")
                        excel = _start_excel_application(win32_client)
                    _convert_xls_to_xlsx(excel, source, target)
                else:
                    raise ValueError(f"Unsupported legacy Office file: {source}")
                if not target.exists() or target.stat().st_size <= 0:
                    raise RuntimeError("target file was not created or is empty")
                if log:
                    log(f"[OK] {source} -> {target}")
                converted.append({"source": str(source), "target": str(target)})
                if delete_legacy_after_conversion:
                    source.unlink()
                    if log:
                        log(f"[DELETE] Legacy source removed: {source}")
                    deleted.append({"source": str(source), "target": str(target), "reason": "converted"})
            except Exception as exc:
                if log:
                    log(f"[FAIL] {source}: {exc}")
                failed.append({"source": str(source), "target": str(target), "error": str(exc)})
        if progress:
            progress(1.0)
        if delete_legacy_after_conversion:
            deleted.extend(_delete_same_stem_duplicate_sources(input_dir, log=log))
    finally:
        _quit_office_application(word)
        _quit_office_application(excel)
        pythoncom.CoUninitialize()
    return LegacyConversionResult(tuple(converted), tuple(deleted), tuple(skipped), tuple(failed))


def legacy_conversion_target(path: Path) -> Path:
    suffix = path.suffix.lower()
    if suffix == ".doc":
        return path.with_suffix(".docx")
    if suffix == ".xls":
        return path.with_suffix(".xlsx")
    raise ValueError(f"Unsupported legacy Office file: {path}")


def _delete_same_stem_duplicate_sources(input_dir: Path, *, log: LogCallback | None = None) -> list[dict[str, str]]:
    deleted: list[dict[str, str]] = []
    folders = [input_dir, *sorted((path for path in input_dir.rglob("*") if path.is_dir()), key=lambda item: str(item))]
    for folder in folders:
        files_by_stem: dict[str, dict[str, Path]] = {}
        for path in folder.iterdir():
            if not path.is_file():
                continue
            files_by_stem.setdefault(path.stem.casefold(), {})[path.suffix.lower()] = path
        for suffixes in files_by_stem.values():
            if ".docx" in suffixes and _target_is_good(suffixes[".docx"]):
                deleted.extend(
                    _delete_duplicate_group(
                        suffixes,
                        keeper=suffixes[".docx"],
                        duplicate_suffixes={".doc", *TEXT_DUPLICATE_SUFFIXES},
                        log=log,
                    )
                )
            if ".xlsx" in suffixes and _target_is_good(suffixes[".xlsx"]):
                deleted.extend(
                    _delete_duplicate_group(
                        suffixes,
                        keeper=suffixes[".xlsx"],
                        duplicate_suffixes={".xls", *TEXT_DUPLICATE_SUFFIXES},
                        log=log,
                    )
                )
    return deleted


def _delete_duplicate_group(
    suffixes: dict[str, Path],
    *,
    keeper: Path,
    duplicate_suffixes: set[str],
    log: LogCallback | None = None,
) -> list[dict[str, str]]:
    deleted: list[dict[str, str]] = []
    for suffix in sorted(duplicate_suffixes):
        duplicate = suffixes.get(suffix)
        if not duplicate or not duplicate.exists() or duplicate.resolve() == keeper.resolve():
            continue
        duplicate.unlink()
        if log:
            log(f"[DELETE] Same-name duplicate removed: {duplicate} (kept {keeper.name})")
        deleted.append({"source": str(duplicate), "target": str(keeper), "reason": "same_stem_duplicate"})
    return deleted


def _target_is_good(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def _require_pywin32() -> tuple[Any, Any]:
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Для конвертации DOC/XLS нужен pywin32 и установленный Microsoft Office. "
            "Пересоберите portable runtime с pywin32 или установите его в текущий runtime."
        ) from exc
    return pythoncom, win32com.client


def _start_word_application(win32_client: Any) -> Any:
    try:
        app = win32_client.DispatchEx("Word.Application")
        app.Visible = False
        app.DisplayAlerts = 0
        try:
            app.AutomationSecurity = 3
        except Exception:
            pass
        return app
    except Exception as exc:
        raise RuntimeError("Microsoft Word COM is unavailable. Check Microsoft Office installation.") from exc


def _start_excel_application(win32_client: Any) -> Any:
    try:
        app = win32_client.DispatchEx("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        try:
            app.AutomationSecurity = 3
        except Exception:
            pass
        return app
    except Exception as exc:
        raise RuntimeError("Microsoft Excel COM is unavailable. Check Microsoft Office installation.") from exc


def _convert_doc_to_docx(word: Any, source: Path, target: Path) -> None:
    document = None
    try:
        document = word.Documents.Open(
            FileName=str(source),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
        )
        document.SaveAs2(FileName=str(target), FileFormat=WORD_DOCX_FORMAT)
    finally:
        if document is not None:
            try:
                document.Close(SaveChanges=False)
            except Exception:
                pass


def _convert_xls_to_xlsx(excel: Any, source: Path, target: Path) -> None:
    workbook = None
    try:
        workbook = excel.Workbooks.Open(
            Filename=str(source),
            UpdateLinks=0,
            ReadOnly=True,
            AddToMru=False,
        )
        workbook.SaveAs(Filename=str(target), FileFormat=EXCEL_XLSX_FORMAT)
    finally:
        if workbook is not None:
            try:
                workbook.Close(SaveChanges=False)
            except Exception:
                pass


def _quit_office_application(app: Any) -> None:
    if app is None:
        return
    try:
        app.Quit()
    except Exception:
        pass
