"""Our own Excel and Word: whoever started one closes it.

An operation drives Microsoft Excel and Word through COM (`DispatchEx`): each is a process of its
own, not a child of ours. While an operation was a thread of the window, a stop was a flag and the
`finally` blocks quit both. Now an operation is a process the window can kill, and a killed process
runs no `finally`: Excel stays behind, invisible, holding the workbook.

So an operation that starts one writes down its process (`dispatch_own`), and whoever kills the
operation closes exactly those (`stop_session`). Before it closes one it checks that the process
under the number is still an Excel or a Word started at the time written - a process of someone
else that got the number afterwards is left alone, and the Excel or Word of the person is never
touched: we find our own by what appeared when we started it, not by the name of the program.

The folder of the records is given by the caller of the operation (`ADDRESS_SESSION_DIR`, the
`--session-dir` of the console command). Without it nothing is written and nothing is closed.
"""
from __future__ import annotations

import ctypes
import json
import os
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

SESSION_ENV = "ADDRESS_SESSION_DIR"
IMAGE_NAMES = {"excel": "excel.exe", "word": "winword.exe"}
PROGRAM_IDS = {"Excel.Application": "excel", "Word.Application": "word"}

_TH32CS_SNAPPROCESS = 0x2
_PROCESS_TERMINATE = 0x1
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x100000


class _ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def session_dir() -> Path | None:
    raw = os.environ.get(SESSION_ENV, "").strip()
    return Path(raw) if raw else None


def processes() -> dict[int, str]:
    """Number and image name (lower case) of every process now running; {} where this cannot be asked."""
    if os.name != "nt":
        return {}
    kernel = ctypes.windll.kernel32
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, wintypes.HANDLE(-1).value, -1):
        return {}
    found: dict[int, str] = {}
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        more = kernel.Process32FirstW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
        while more:
            found[int(entry.th32ProcessID)] = entry.szExeFile.lower()
            more = kernel.Process32NextW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
    finally:
        kernel.CloseHandle(wintypes.HANDLE(snapshot))
    return found


def running(kind: str) -> set[int]:
    """The numbers of the processes of this program (Excel or Word) running now."""
    image = IMAGE_NAMES[kind]
    return {pid for pid, name in processes().items() if name == image}


def started_at(pid: int) -> int:
    """When the process began, as a Windows FILETIME; 0 when it is gone or cannot be asked."""
    if os.name != "nt":
        return 0
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return 0
    try:
        created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(wintypes.HANDLE(handle), ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(kernel_time), ctypes.byref(user_time)):
            return 0
        return (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle))


def _window_process(app: Any) -> int:
    """The process an Excel window belongs to (`Application.Hwnd`); 0 for a program that has none."""
    try:
        import win32process  # type: ignore

        return int(win32process.GetWindowThreadProcessId(int(app.Hwnd))[1])
    except Exception:  # noqa: BLE001 - Word has no such property; the caller falls back to what appeared
        return 0


def _record(kind: str, pid: int) -> Path | None:
    folder = session_dir()
    if folder is None or not pid:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{kind}-{pid}.json"
    path.write_text(json.dumps({"kind": kind, "pid": pid, "started": started_at(pid)}), encoding="utf-8")
    return path


def dispatch_own(client: Any, program_id: str) -> Any:
    """`client.DispatchEx(program_id)` that writes down the process it started.

    `client` is `win32com.client`. A program id that is neither Excel nor Word is just dispatched.
    """
    kind = PROGRAM_IDS.get(program_id)
    if kind is None or session_dir() is None:
        return client.DispatchEx(program_id)
    before = running(kind)
    app = client.DispatchEx(program_id)
    appeared = running(kind) - before
    exact = _window_process(app) if kind == "excel" else 0
    if exact in appeared:
        appeared = {exact}
    # Two programs of the same name appeared at once and nothing tells ours apart: write down none
    # rather than close someone else's. The operation still quits its own in its `finally`.
    if len(appeared) == 1:
        _record(kind, next(iter(appeared)))
    return app


def forget_session() -> None:
    """The operation ended in order: its programs were quit, there is nothing left to close."""
    folder = session_dir()
    if folder is None or not folder.is_dir():
        return
    for path in folder.glob("*-*.json"):
        try:
            path.unlink()
        except OSError:
            pass


def _terminate(pid: int) -> bool:
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(_PROCESS_TERMINATE | _SYNCHRONIZE, False, int(pid))
    if not handle:
        return False
    try:
        done = bool(kernel.TerminateProcess(wintypes.HANDLE(handle), 1))
        if done:
            kernel.WaitForSingleObject(wintypes.HANDLE(handle), 5000)
        return done
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle))


def stop_session(folder: Path) -> dict[str, int]:
    """Close the programs recorded in `folder`: {"stopped": closed now, "lost": already gone or not ours any more}."""
    stopped = lost = 0
    if os.name != "nt" or not folder.is_dir():
        return {"stopped": 0, "lost": 0}
    now = processes()
    for path in sorted(folder.glob("*-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            kind, pid, born = str(record["kind"]), int(record["pid"]), int(record.get("started") or 0)
            ours = bool(born) and now.get(pid) == IMAGE_NAMES.get(kind) and started_at(pid) == born
        except (OSError, ValueError, KeyError):
            ours = False
        if ours and _terminate(pid):
            stopped += 1
        else:
            lost += 1
        try:
            path.unlink()
        except OSError:
            pass
    return {"stopped": stopped, "lost": lost}


def wait_until_gone(kind: str, numbers: set[int], seconds: float = 5.0) -> bool:
    """Whether none of these processes of the program is left within the time given."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not (running(kind) & numbers):
            return True
        time.sleep(0.1)
    return not (running(kind) & numbers)
