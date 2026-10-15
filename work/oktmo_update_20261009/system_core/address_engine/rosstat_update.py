from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen
import json
import os
import re
import shutil
import ssl
import time


DEFAULT_OKTMO_URL = "https://rosstat.gov.ru/opendata/7708234640-oktmo/"
DATA_FILE_RE = re.compile(r"data-(\d{8}T\d{4})-structure-\d{8}T\d{4}\.csv", re.IGNORECASE)
REPORT_FILENAME = "rosstat_oktmo_update_summary.json"
OKTMO_URL_ENV_NAMES = (
    "AUDION_ADDRESS_PROCESSOR_ROSSTAT_OKTMO_URL",
    "AUDION_ROSSTAT_OKTMO_URL",
    "AAP_ROSSTAT_OKTMO_URL",
)


@dataclass(frozen=True)
class ResolvedRosstatCsv:
    url: str
    filename: str
    source: str


def update_rosstat_oktmo_data(
    *,
    data_dir: Path,
    report_dir: Path,
    source_url: str | None = None,
    log: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, object]:
    url = _configured_source_url(source_url)
    resolved = _resolve_latest_csv_url(url)
    _log(log, f"Resolved CSV: {resolved.filename}")

    rosstat_dir = data_dir / "rosstat"
    rosstat_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    destination = rosstat_dir / resolved.filename
    temp_path = rosstat_dir / f".{resolved.filename}.{int(time.time())}.tmp"
    downloaded_bytes = 0
    try:
        downloaded_bytes = _download_csv(resolved.url, temp_path, log=log, cancelled=cancelled)
        _validate_csv_payload(temp_path)
        if destination.exists():
            destination.unlink()
        shutil.move(str(temp_path), str(destination))
    finally:
        if temp_path.exists():
            temp_path.unlink()

    cleanup = _prune_old_data_files(rosstat_dir, keep=destination)
    if cleanup["removed"]:
        _log(log, f"Removed old Rosstat OKTMO snapshots: {len(cleanup['removed'])}")
    if cleanup["errors"]:
        _log(log, f"Could not remove old Rosstat OKTMO snapshots: {len(cleanup['errors'])}")

    latest = _latest_data_file(rosstat_dir)
    summary: dict[str, object] = {
        "mode": "update-rosstat-oktmo",
        "requested_url": url,
        "resolved_url": resolved.url,
        "resolved_source": resolved.source,
        "output_path": str(destination),
        "downloaded_bytes": downloaded_bytes,
        "removed_data_files": cleanup["removed"],
        "cleanup_errors": cleanup["errors"],
        "available_data_files": [path.name for path in _list_data_files(rosstat_dir)],
        "latest_data_file": latest.name if latest else None,
    }
    summary_path = report_dir / REPORT_FILENAME
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def _configured_source_url(source_url: str | None) -> str:
    direct = str(source_url or "").strip()
    if direct:
        return direct
    for name in OKTMO_URL_ENV_NAMES:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return DEFAULT_OKTMO_URL


def _resolve_latest_csv_url(url: str) -> ResolvedRosstatCsv:
    direct_filename = _filename_from_data_url(url)
    if direct_filename:
        return ResolvedRosstatCsv(url=url, filename=direct_filename, source="direct_csv_url")

    html = _fetch_text(url)
    matches = _extract_data_csv_urls(html, url)
    if not matches and url.rstrip("/") != DEFAULT_OKTMO_URL.rstrip("/"):
        html = _fetch_text(DEFAULT_OKTMO_URL)
        matches = _extract_data_csv_urls(html, DEFAULT_OKTMO_URL)
    if not matches:
        raise RuntimeError(
            "Could not find a Rosstat OKTMO data-*.csv link. "
            "Use a direct CSV URL or the Rosstat OKTMO opendata page."
        )
    latest_url = max(matches, key=lambda item: _data_timestamp(item[1]))
    return ResolvedRosstatCsv(url=latest_url[0], filename=latest_url[1], source="discovered_from_page")


def _fetch_text(url: str) -> str:
    with _open_url(url, timeout=45) as response:
        payload = response.read()
    for encoding in ("utf-8", "cp1251"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="ignore")


def _download_csv(
    url: str,
    destination: Path,
    *,
    log: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> int:
    total = 0
    with _open_url(url, timeout=120) as response, destination.open("wb") as output:
        while True:
            if cancelled and cancelled():
                raise RuntimeError("Rosstat OKTMO update cancelled.")
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            output.write(chunk)
            if total and total % (10 * 1024 * 1024) < len(chunk):
                _log(log, f"Downloaded {total // (1024 * 1024)} MB...")
    return total


def _open_url(url: str, *, timeout: int):
    request = Request(url, headers={"User-Agent": "Audion Address Processor/1.0"})
    try:
        return urlopen(request, timeout=timeout)
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        context = ssl._create_unverified_context()
        return urlopen(request, timeout=timeout, context=context)


def _validate_csv_payload(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("Downloaded Rosstat OKTMO file is empty.")
    prefix = path.read_bytes()[:512].lstrip()
    if prefix.startswith((b"<html", b"<!doctype html", b"<HTML", b"<!DOCTYPE HTML")):
        raise RuntimeError("Downloaded Rosstat OKTMO payload looks like HTML, not CSV.")
    if b";" not in prefix and path.stat().st_size < 1024:
        raise RuntimeError("Downloaded Rosstat OKTMO payload does not look like a semicolon-separated CSV.")


def _extract_data_csv_urls(html: str, base_url: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    pattern = r"""(?:href=)?["']?([^"'<> ]*data-\d{8}T\d{4}-structure-\d{8}T\d{4}\.csv)["']?"""
    for match in re.finditer(pattern, html, re.IGNORECASE):
        raw = match.group(1).strip()
        full_url = urljoin(base_url, raw)
        filename = _filename_from_data_url(full_url)
        if not filename or full_url in seen:
            continue
        seen.add(full_url)
        result.append((full_url, filename))
    return result


def _filename_from_data_url(url: str) -> str | None:
    parsed = urlparse(url)
    filename = Path(unquote(parsed.path)).name
    if DATA_FILE_RE.fullmatch(filename):
        return filename
    return None


def _data_timestamp(filename: str) -> str:
    match = DATA_FILE_RE.search(filename)
    return match.group(1) if match else ""


def _list_data_files(rosstat_dir: Path) -> list[Path]:
    return sorted(path for path in rosstat_dir.glob("data-*.csv") if path.is_file())


def _latest_data_file(rosstat_dir: Path) -> Path | None:
    files = _list_data_files(rosstat_dir)
    if not files:
        return None
    return max(files, key=lambda path: (_data_timestamp(path.name), path.stat().st_mtime, path.name.lower()))


def _prune_old_data_files(rosstat_dir: Path, *, keep: Path) -> dict[str, list[str]]:
    keep_path = keep.resolve()
    removed: list[str] = []
    errors: list[str] = []
    for candidate in _list_data_files(rosstat_dir):
        try:
            if candidate.resolve() == keep_path:
                continue
            candidate.unlink()
            removed.append(candidate.name)
        except OSError as exc:
            errors.append(f"{candidate.name}: {exc}")
    return {"removed": removed, "errors": errors}


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log:
        log(message)
