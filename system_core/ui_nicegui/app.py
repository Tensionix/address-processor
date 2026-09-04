from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
import atexit
import argparse
import ctypes
from ctypes import wintypes
import html
import importlib
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nicegui import app as nicegui_app, run, ui  # type: ignore
from system_core.ui_nicegui.workbench import (
    WorkbenchAdapter,
    WorkbenchConfig,
    WorkbenchHandlers,
    WorkbenchRenderer,
    WorkbenchRole,
    WORKBENCH_FEEDBACK_CSS,
    WORKBENCH_LAYOUT_CSS,
    WORKBENCH_OVERRIDE_CSS,
    canonical_role,
)

AUDION_CANONICAL_TOOLTIP_DELAY_MS = 1500
AUDION_CANONICAL_TOOLTIP_HIDE_DELAY_MS = 100
AUDION_CANONICAL_TOOLTIP_TRANSITION_MS = 100


def install_audion_canonical_tooltip_defaults() -> None:
    try:
        from nicegui.elements.tooltip import Tooltip as NiceGuiTooltip  # type: ignore
    except Exception:
        return
    if getattr(NiceGuiTooltip, "_audion_canonical_tooltip_defaults", False):
        return
    original_init = NiceGuiTooltip.__init__

    def audion_tooltip_init(self: Any, text: str = "") -> None:
        original_init(self, text)
        self.props["delay"] = AUDION_CANONICAL_TOOLTIP_DELAY_MS
        self.props["hide-delay"] = AUDION_CANONICAL_TOOLTIP_HIDE_DELAY_MS
        self.props["transition-duration"] = AUDION_CANONICAL_TOOLTIP_TRANSITION_MS
        self.classes("audion-tooltip")

    NiceGuiTooltip.__init__ = audion_tooltip_init  # type: ignore[method-assign]
    NiceGuiTooltip._audion_canonical_tooltip_defaults = True  # type: ignore[attr-defined]


install_audion_canonical_tooltip_defaults()


def soften_reconnect_copy_for_oktmo() -> None:
    """Use calm reconnect wording during heavy local OKTMO preparation."""
    try:
        from nicegui.translations import translations  # type: ignore
    except Exception:
        return

    replacement = {
        "connection_lost": "Идёт обработка данных ОКТМО...",
        "trying_to_reconnect": "Интерфейс вернётся автоматически.",
    }
    for language in ("ru", "en-US", "en-GB"):
        data = translations.setdefault(language, {})
        data.update(replacement)


soften_reconnect_copy_for_oktmo()


AUDION_CANONICAL_UI_CSS = """
<style id="audion-canonical-tooltip-icon-style">
  html body .q-tooltip,
  html body .audion-tooltip {
    background: rgb(23, 33, 43) !important;
    background-color: rgb(23, 33, 43) !important;
    color: #f4f8fb !important;
    border: 1px solid rgba(88, 166, 255, 0.24) !important;
    border-radius: 8px !important;
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.34) !important;
  }
  html body .q-icon.material-icons,
  html body .q-icon.material-symbols-outlined,
  html body .q-icon.material-symbols-rounded,
  html body i.material-icons,
  html body i.material-symbols-outlined,
  html body i.material-symbols-rounded,
  html body .q-btn .q-icon,
  html body .q-btn .material-icons,
  html body .q-btn .material-symbols-outlined,
  html body .q-btn .material-symbols-rounded,
  html body .q-field .q-field__append .q-icon,
  html body .q-field .q-field__prepend .q-icon,
  html body .q-item .q-icon,
  html body .q-menu .q-icon,
  html body .audion-label-icon,
  html body .audion-path-option-pin,
  html body .audion-select-option-pin {
    font-size: 14px !important;
    width: 14px !important;
    min-width: 14px !important;
    height: 14px !important;
    line-height: 14px !important;
  }
  html body .material-icons,
  html body .q-icon.material-icons {
    font-family: "Material Icons" !important;
  }
  html body .material-symbols-outlined,
  html body .q-icon.material-symbols-outlined {
    font-family: "Material Symbols Outlined" !important;
  }
  html body .material-symbols-rounded,
  html body .q-icon.material-symbols-rounded {
    font-family: "Material Symbols Rounded" !important;
  }
</style>
"""


def add_audion_canonical_ui_styles() -> None:
    ui.add_head_html(AUDION_CANONICAL_UI_CSS)



def audion_tooltip_path_text(path_value: Any) -> str:
    raw = str(path_value or "").strip()
    if not raw:
        return ""
    try:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        return str(path)
    except Exception:
        return raw


def audion_folder_button_tooltip(folder_id: str, path_value: Any) -> str:
    key = str(folder_id or "folder").strip().lower()
    path_text = audion_tooltip_path_text(path_value)
    if getattr(settings, "language", "ru") == "ru":
        descriptions = {
            "logs": "папку логов запусков и вывода терминала",
            "report": "папку отчётов и результатов операций",
            "reports": "папку отчётов и результатов операций",
            "config": "папку конфигурации проекта: manifest, GUI-настройки и кэши",
            "state": "папку рабочего состояния GUI",
            "project": "корневую папку проекта",
            "root": "корневую папку проекта",
            "data": "папку данных проекта",
            "pipeline": "папку pipeline-артефактов и промежуточных результатов",
            "github": "папку GitHub-артефактов проекта",
            "install": "папку install/runtime-артефактов проекта",
        }
        description = descriptions.get(key, f"папку {folder_id}")
        return f"Открыть {description}: {path_text}" if path_text else f"Открыть {description}."
    descriptions = {
        "logs": "the logs folder with run and terminal output",
        "report": "the reports/results folder",
        "reports": "the reports/results folder",
        "config": "the project config folder with manifest, GUI settings, and caches",
        "state": "the GUI state folder",
        "project": "the project root folder",
        "root": "the project root folder",
        "data": "the project data folder",
        "pipeline": "the pipeline artifacts and intermediate results folder",
        "github": "the project GitHub artifacts folder",
        "install": "the project install/runtime artifacts folder",
    }
    description = descriptions.get(key, f"the {folder_id} folder")
    return f"Open {description}: {path_text}" if path_text else f"Open {description}."


def audion_terminal_action_tooltip(action: str) -> str:
    key = str(action or "").strip().lower()
    if getattr(settings, "language", "ru") == "ru":
        tips = {
            "clear_terminal_window": "Очистить только видимое окно терминала. Файлы логов, отчёты и результаты операций не удаляются.",
            "expand": "Открыть терминал в большом окне, чтобы читать длинный вывод без тесной панели.",
            "expand_log": "Открыть терминал в большом окне, чтобы читать длинный вывод без тесной панели.",
            "pin_command": "Закрепить текущую команду в истории терминала для быстрого повторного запуска.",
            "unpin_command": "Открепить текущую команду от верхней части истории терминала.",
            "clear_history": "Очистить историю команд терминала. Закреплённые команды и файлы логов не удаляются.",
            "terminal_shell": "Выбрать оболочку, в которой будут запускаться команды терминала.",
            "terminal_history": "Выбрать ранее сохранённую или закреплённую команду терминала.",
            "terminal_command": "Команда, которая будет выполнена из выбранной рабочей папки.",
            "terminal_cwd": "Рабочая папка терминала. Команда будет запущена именно отсюда.",
            "pick_folder": "Выбрать рабочую папку терминала через системный диалог.",
            "terminal_run": "Запустить введённую команду в выбранной оболочке и рабочей папке.",
            "latest_report": "Открыть последний созданный отчёт, если он уже есть.",
            "command_preview": "Показать команду, которая будет запущена с текущими параметрами, без выполнения операции.",
            "report_view": "Открыть встроенный список отчётов без перехода в проводник.",
            "close": "Закрыть большое окно терминала и вернуться к основной панели.",
        }
    else:
        tips = {
            "clear_terminal_window": "Clear only the visible terminal window. Log files, reports, and operation results are not deleted.",
            "expand": "Open the terminal in a large window for reading long output comfortably.",
            "expand_log": "Open the terminal in a large window for reading long output comfortably.",
            "pin_command": "Pin the current terminal command for quick reuse.",
            "unpin_command": "Remove the current command from the pinned command list.",
            "clear_history": "Clear terminal command history. Pinned commands and log files are not deleted.",
            "terminal_shell": "Choose the shell used to run terminal commands.",
            "terminal_history": "Pick a saved or pinned terminal command.",
            "terminal_command": "Command to run from the selected working folder.",
            "terminal_cwd": "Terminal working folder. Commands are started from here.",
            "pick_folder": "Choose the terminal working folder with the system dialog.",
            "terminal_run": "Run the entered command in the selected shell and working folder.",
            "latest_report": "Open the latest generated report, if one exists.",
            "command_preview": "Show the command that would run with the current settings, without executing it.",
            "report_view": "Open the built-in reports list without switching to the file explorer.",
            "close": "Close the large terminal window and return to the main panel.",
        }
    return tips.get(key, key.replace("_", " ").strip())


from system_core.core.ansi_terminal import AnsiHtmlRenderer
from system_core.core.config import load_yaml_or_json
from system_core.core.jobs import execute_operation
from system_core.core.manifest import CommandNode, Operation, load_manifest
from system_core.core.paths import ensure_project_dirs, get_project_paths, open_folder
from system_core.core.ui_settings import load_ui_settings
from system_core.services import address_aligner_service as address_service


paths = get_project_paths(ROOT)
ensure_project_dirs(paths)
manifest = load_manifest(paths.config / "tool_manifest.yaml")
settings_path = paths.config / "gui_settings.yaml"
settings = load_ui_settings(settings_path)
tool_info: dict[str, Any] = manifest.raw.get("tool", {})
ui_info: dict[str, Any] = manifest.raw.get("ui", {})

def _workspace_history_file() -> Path:
    return paths.config / "path_history.json"


def _startup_workspace_path(role: str, configured: str, legacy: str, default_path: Path) -> str:
    return str(default_path)


def load_workspace_route_settings() -> tuple[str, str]:
    return (
        _startup_workspace_path("source", "", "", paths.input),
        _startup_workspace_path("target", "", "", paths.output),
    )


def _yaml_string(value: Any) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _workspace_setting_for_disk(role: str, path_value: Any, default_path: Path) -> str:
    return ""


def display_path(path_value: Any) -> str:
    text = str(path_value or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(ROOT)
    except (OSError, ValueError):
        return str(path)
    return str(relative) or "."


def save_app_settings() -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    source_path = _workspace_setting_for_disk("source", getattr(settings, "source_path", ""), paths.input)
    destination_path = _workspace_setting_for_disk("target", getattr(settings, "destination_path", ""), paths.output)
    text = (
        "gui:\n"
        "  # Change to \"en\" for public GitHub builds.\n"
        f"  language: \"{settings.language if settings.language in {'en', 'ru'} else 'ru'}\"\n"
        f"  theme: \"{normalize_theme_id(settings.theme)}\"\n"
        f"  emoji: {str(bool(getattr(settings, 'emoji', False))).lower()}\n"
        f"  allow_runtime_switching: {str(bool(getattr(settings, 'allow_runtime_switching', True))).lower()}\n"
        f"  advanced_open: {str(bool(getattr(settings, 'advanced_open', False))).lower()}\n"
        f"  source_path: {_yaml_string(source_path)}\n"
        f"  destination_path: {_yaml_string(destination_path)}\n"
    )
    settings_path.write_text(text, encoding="utf-8", newline="\n")


settings.source_path, settings.destination_path = load_workspace_route_settings()

DEFAULT_THEME_ID = "code_dark"
THEME_ALIASES = {"dark": "code_dark", "light": "code_light"}


def _string_map(value: Any) -> dict[str, str]:
    return {str(key).strip(): str(item).strip() for key, item in dict(value).items() if str(key).strip()} if isinstance(value, dict) else {}


def load_ui_colors(path: Path) -> dict[str, Any]:
    data = load_yaml_or_json(path) if path.exists() else {}
    if not isinstance(data, dict):
        data = {}
    themes: dict[str, dict[str, Any]] = {}
    themes_raw = data.get("themes", {})
    if not isinstance(themes_raw, dict):
        themes_raw = {}
    for theme_id, theme_data in themes_raw.items():
        if not isinstance(theme_data, dict):
            continue
        normalized_id = str(theme_id).strip().lower()
        if not normalized_id:
            continue
        themes[normalized_id] = {
            "label": str(theme_data.get("label") or normalized_id).strip(),
            "label_ru": str(theme_data.get("label_ru") or theme_data.get("label") or normalized_id).strip(),
            "mode": "dark" if str(theme_data.get("mode", "dark")).lower() == "dark" else "light",
            "tokens": _string_map(theme_data.get("tokens", {})),
        }
    if DEFAULT_THEME_ID not in themes:
        themes[DEFAULT_THEME_ID] = {
            "label": "Code Dark",
            "label_ru": "Code Темная",
            "mode": "dark",
            "tokens": {
                "color-background-primary": "#141413",
                "color-background-secondary": "#1f1e1a",
                "color-background-tertiary": "#0f0f0e",
                "color-text-primary": "#faf9f5",
                "color-text-secondary": "#e8e6dc",
                "color-text-tertiary": "#b0aea5",
                "color-border-tertiary": "rgba(250, 249, 245, 0.15)",
                "color-border-secondary": "rgba(250, 249, 245, 0.3)",
                "color-border-primary": "rgba(250, 249, 245, 0.4)",
                "color-accent-primary": "#d97757",
            },
        }
    return {
        "ramps": data.get("ramps", {}) if isinstance(data.get("ramps", {}), dict) else {},
        "tokens": _string_map(data.get("tokens", {})),
        "themes": themes,
    }


ui_colors = load_ui_colors(paths.config / "ui_colors.yaml")


def tolerate_missing_process_pool() -> None:
    """Keep NiceGUI alive when multiprocessing is blocked by the environment.

    NiceGUI initializes a process pool even when the GUI only uses thread/io-bound
    jobs. Some portable, sandboxed, or enterprise Windows environments reject the
    underlying multiprocessing handles, but the shell can still work without CPU
    pool tasks.
    """
    try:
        import nicegui.run as nicegui_run  # type: ignore
    except Exception:
        return

    original_setup = getattr(nicegui_run, "setup", None)
    if not callable(original_setup):
        return

    def safe_setup() -> None:
        try:
            original_setup()
        except (OSError, PermissionError) as exc:
            logging.warning("NiceGUI process pool disabled: %s", exc)
            nicegui_run.process_pool = None

    nicegui_run.setup = safe_setup


tolerate_missing_process_pool()

LABELS = {
    "ru": {
        "workspace": "Рабочие папки",
        "operations": "Операции",
        "maintenance": "Обслуживание",
        "status": "Статус",
        "log": "Журнал операции",
        "idle": "Ожидание",
        "running": "Выполняется",
        "done": "Готово",
        "error": "Ошибка",
        "cancel": "Отменить",
        "another_running": "Другая операция уже выполняется.",
        "confirm_title": "Подтвердите действие",
        "confirm_note": "Действие может изменить управляемую рабочую область.",
        "confirm_impact_title": "Что будет затронуто",
        "confirm_parameters_note": "Перед запуском проверьте выбранные параметры и рабочие папки.",
        "confirm_irreversible_note": "Отмена после запуска может потребовать ручной очистки уже созданных файлов.",
        "confirm_run_dangerous": "Подтвердить запуск",
        "run": "Запустить",
        "back": "Назад",
        "selected_operation": "Выбрана команда",
        "open_menu": "Открыть",
        "parameters": "Параметры",
        "advanced": "Дополнительно",
        "actions": "Действия",
        "close": "Закрыть",
        "logs": "Журнал",
        "report": "Отчёт",
        "config": "Настройки",
        "expand": "Развернуть",
        "clear_terminal_window": "Очистить окно терминала",
        "add_file_short": "Добавить файл...",
        "add_files": "Добавить файлы...",
        "add_folder": "Добавить папку...",
        "file_list": "File List",
        "file_list_button": "Список",
        "file_list_empty": "INPUT has no files.",
        "file_list_missing": "INPUT was not found: {path}",
        "file_list_ready": "File list generated: {count}.",
        "terminal_file": "File",
        "stage_files": "Добавление файлов в исходники",
        "stage_folder": "Добавление папки в исходники",
        "picker_cancelled": "Выбор отменен.",
        "operation_done": "Операция завершена.",
        "operation_failed": "Операция завершилась с кодом {code}.",
        "select_required": "Выберите хотя бы один пункт: {field}",
        "refresh_options": "Обновить список",
        "download_oktmo": "Скачать ОКТМО",
        "oktmo_registry_missing": "Реестр ОКТМО не найден: data/rosstat/data-*.csv. Списки регионов и муниципалитетов будут неполными.",
        "oktmo_registry_ready": "Реестр ОКТМО: {file}.",
        "resize_panels": "Изменить ширину панелей",
        "source_folder": "Источник",
        "target_folder": "Назначение",
        "source_selected": "Источник выбран.",
        "target_selected": "Назначение выбрано.",
        "source_folder_missing": "Источник не найден: {path}",
        "clear_io_short": "Сбросить",
        "delete_io_short": "Удалить",
        "path_pinned": "Путь закреплен.",
        "path_unpinned": "Закрепление снято.",
        "path_required": "Выберите путь.",
        "section_preset": "Профиль",
        "section_source": "Исходники",
        "section_files": "Файлы",
        "section_sheets": "Листы",
        "section_addresses": "Адреса",
        "section_rows": "Строки данных",
        "section_territory": "Территория",
        "section_columns": "Колонки",
        "section_alignment_mode": "Режим",
        "section_alignment_normalization": "Выравнивание и нормализация",
        "section_related_columns": "Связанные колонки",
        "section_format": "Формат",
        "section_output": "Результат",
        "section_encoding": "Кодирование",
        "section_options": "Опции",
        "section_run": "Запуск",
        "section_parameters": "Параметры",
        "artifacts": "Артефакты",
        "artifact_output": "OUTPUT",
        "artifact_report": "REPORT",
        "artifact_staging": "ПРОВЕРКА",
        "report_summary": "Сводка отчёта",
        "raw_json": "JSON",
        "theme": "Тема",
        "theme_saved": "Тема сохранена. Перезагружаю интерфейс.",
        "lang_switch": "EN",
    },
    "en": {
        "workspace": "Workspace folders",
        "operations": "Operations",
        "maintenance": "Maintenance",
        "status": "Status",
        "log": "Operation log",
        "idle": "Idle",
        "running": "Running",
        "done": "Done",
        "error": "Error",
        "cancel": "Cancel",
        "another_running": "Another operation is already running.",
        "confirm_title": "Confirm action",
        "confirm_note": "This action may change the managed workspace.",
        "confirm_impact_title": "Affected area",
        "confirm_parameters_note": "Check the selected parameters and workspace folders before running.",
        "confirm_irreversible_note": "Cancelling after start may require manual cleanup of already created files.",
        "confirm_run_dangerous": "Confirm run",
        "run": "Run",
        "back": "Back",
        "selected_operation": "Selected command",
        "open_menu": "Open",
        "parameters": "Parameters",
        "advanced": "Advanced",
        "actions": "Actions",
        "close": "Close",
        "logs": "Logs",
        "report": "Report",
        "config": "CONFIG",
        "expand": "Expand",
        "clear_terminal_window": "Clear terminal window",
        "add_file_short": "Add file...",
        "add_files": "Add files...",
        "add_folder": "Add folder...",
        "file_list": "File List",
        "file_list_button": "List",
        "file_list_empty": "INPUT has no files.",
        "file_list_missing": "INPUT was not found: {path}",
        "file_list_ready": "File list generated: {count}.",
        "terminal_file": "File",
        "stage_files": "Adding files to input",
        "stage_folder": "Adding folder to input",
        "picker_cancelled": "Selection cancelled.",
        "operation_done": "Operation finished.",
        "operation_failed": "Operation finished with exit code {code}.",
        "select_required": "Select at least one item: {field}",
        "refresh_options": "Refresh list",
        "download_oktmo": "Download OKTMO",
        "oktmo_registry_missing": "OKTMO registry was not found: data/rosstat/data-*.csv. Region and municipality lists will be incomplete.",
        "oktmo_registry_ready": "OKTMO registry: {file}.",
        "resize_panels": "Resize panels",
        "source_folder": "Source",
        "target_folder": "Target",
        "source_selected": "Source selected.",
        "target_selected": "Target selected.",
        "source_folder_missing": "Source was not found: {path}",
        "clear_io_short": "Reset",
        "delete_io_short": "Delete",
        "path_pinned": "Path pinned.",
        "path_unpinned": "Path unpinned.",
        "path_required": "Choose a path.",
        "section_preset": "Preset",
        "section_source": "Source",
        "section_files": "Files",
        "section_sheets": "Sheets",
        "section_addresses": "Addresses",
        "section_rows": "Data rows",
        "section_territory": "Territory",
        "section_columns": "Columns",
        "section_alignment_mode": "Mode",
        "section_alignment_normalization": "Alignment + Normalization",
        "section_related_columns": "Linked Columns",
        "section_format": "Format",
        "section_output": "Output",
        "section_encoding": "Encoding",
        "section_options": "Options",
        "section_run": "Run",
        "section_parameters": "Parameters",
        "artifacts": "Artifacts",
        "artifact_output": "OUTPUT",
        "artifact_report": "REPORT",
        "artifact_staging": "AUDIT",
        "report_summary": "Report Summary",
        "raw_json": "JSON",
        "theme": "Theme",
        "theme_saved": "Theme saved. Reloading UI.",
        "lang_switch": "RU",
    },
}

PICKER_BOOTSTRAP = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
  Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class AudionDpiAwareness {
  [DllImport("user32.dll")]
  public static extern bool SetProcessDpiAwarenessContext(IntPtr dpiContext);
  [DllImport("shcore.dll")]
  public static extern int SetProcessDpiAwareness(int value);
}
"@
  try { [AudionDpiAwareness]::SetProcessDpiAwarenessContext([IntPtr](-4)) | Out-Null }
  catch { [AudionDpiAwareness]::SetProcessDpiAwareness(2) | Out-Null }
} catch {}
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
"""

state: dict[str, Any] = {
    "running": False,
    "cancel": False,
    "progress": 0.0,
    "status": "",
    "lines": [],
    "line_offset": 0,
    "log_version": 0,
    "terminal_scroll_top_seq": 0,
    "exit_code": None,
    "command_path": [],
    "pending_command": None,
    "field_values": {},
    "source_path": str(getattr(settings, "source_path", "") or ""),
    "destination_path": str(getattr(settings, "destination_path", "") or ""),
    "workspace_feedback": {},
    "last_artifacts": {},
    "last_artifacts_version": 0,
}

dynamic_option_cache: dict[Any, tuple[float, list[Any]]] = {}
TERMINAL_HISTORY_LIMIT = 1500
PATH_HISTORY_LIMIT = 100


def tr(key: str, **kwargs: Any) -> str:
    lang = settings.language if settings.language in LABELS else "en"
    text = LABELS.get(lang, LABELS["en"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


def em(key: str) -> str:
    if not bool(getattr(settings, "emoji", False)):
        return ""
    return {
        "workspace": "📁 ",
        "operations": "⚙ ",
        "maintenance": "🧰 ",
        "status": "● ",
        "log": "🖥 ",
    }.get(key, "")


def app_title() -> str:
    title = str(ui_info.get("title") or tool_info.get("name") or "Audion GUI Tool")
    return title[:-3] if title.endswith(" UI") else title


def normalize_theme_id(theme_id: Any) -> str:
    text = str(theme_id or DEFAULT_THEME_ID).strip().lower()
    return THEME_ALIASES.get(text, text)


def active_theme() -> str:
    theme_id = normalize_theme_id(settings.theme)
    themes = ui_colors["themes"]
    if theme_id in themes:
        return theme_id
    return DEFAULT_THEME_ID if DEFAULT_THEME_ID in themes else next(iter(themes))


def active_theme_data() -> dict[str, Any]:
    return dict(ui_colors["themes"][active_theme()])


def active_theme_mode() -> str:
    return str(active_theme_data().get("mode", "dark"))


def theme_label(theme_id: str) -> str:
    theme_data = ui_colors["themes"].get(theme_id, {})
    label_key = "label_ru" if settings.language == "ru" else "label"
    return str(theme_data.get(label_key) or theme_data.get("label") or theme_id)


def theme_options() -> dict[str, str]:
    return {theme_id: theme_label(theme_id) for theme_id in ui_colors["themes"]}


def set_theme(theme_id: Any) -> None:
    selected = normalize_theme_id(theme_id)
    if selected not in ui_colors["themes"]:
        return
    settings.theme = selected
    save_app_settings()
    safe_notify(tr("theme_saved"), "positive")
    reload_ui()


def theme_change_handler(event: Any) -> None:
    set_theme(getattr(event, "value", None))

def reload_ui(delay_ms: int = 0) -> None:
    script = """
        (() => {
          try {
            if ('scrollRestoration' in window.history) {
              window.history.scrollRestoration = 'manual';
            }
            window.sessionStorage.setItem('audion_force_scroll_top', '1');
            window.scrollTo(0, 0);
            document.documentElement.scrollTop = 0;
            document.body.scrollTop = 0;
          } catch (error) {}
          window.setTimeout(() => window.location.reload(), __RELOAD_DELAY__);
        })();
        """
    script = script.replace("__RELOAD_DELAY__", str(max(0, int(delay_ms))))
    delivered = False
    for client in list(nicegui_app.clients()):
        if getattr(client, "_deleted", False) or not client.has_socket_connection:
            continue
        client.run_javascript(script)
        delivered = True
    if not delivered:
        ui.run_javascript(script)

def theme_variables() -> dict[str, str]:
    variables: dict[str, str] = {}
    for ramp_name, stops in ui_colors["ramps"].items():
        if not isinstance(stops, dict):
            continue
        for stop, color in stops.items():
            variables[f"color-{ramp_name}-{stop}"] = str(color).strip()
    variables.update(ui_colors["tokens"])
    variables.update(_string_map(active_theme_data().get("tokens", {})))
    variables.setdefault("color-background-primary", "#141413")
    variables.setdefault("color-background-secondary", "#1f1e1a")
    variables.setdefault("color-background-tertiary", "#0f0f0e")
    variables.setdefault("color-text-primary", "#faf9f5")
    variables.setdefault("color-text-secondary", "#e8e6dc")
    variables.setdefault("color-text-tertiary", "#b0aea5")
    variables.setdefault("color-border-tertiary", "rgba(250, 249, 245, 0.15)")
    variables.setdefault("color-border-secondary", "rgba(250, 249, 245, 0.3)")
    variables.setdefault("color-border-primary", "rgba(250, 249, 245, 0.4)")
    variables.setdefault("color-accent-primary", "#d97757")
    variables.setdefault("font-sans", "Inter, Segoe UI, Arial, sans-serif")
    variables.setdefault("font-mono", "Cascadia Mono, Consolas, monospace")
    variables.setdefault("border-radius-md", "8px")
    variables.setdefault("border-radius-lg", "12px")
    return variables


def add_log(message: str) -> None:
    if not str(message).strip():
        return
    lines = state.setdefault("lines", [])
    lines.append(str(message).rstrip())
    overflow = max(0, len(lines) - TERMINAL_HISTORY_LIMIT)
    if overflow:
        del lines[:overflow]
        state["line_offset"] = int(state.get("line_offset", 0)) + overflow
    state["log_version"] = int(state["log_version"]) + 1


def clear_terminal_log() -> None:
    state["lines"] = []
    state["line_offset"] = 0
    state["terminal_scroll_top_seq"] = 0
    state["log_version"] = int(state["log_version"]) + 1


def terminal_lines_html(
    lines: list[str] | tuple[str, ...],
    *,
    leading_newline: bool = False,
    renderer: AnsiHtmlRenderer | None = None,
) -> str:
    active_renderer = renderer or AnsiHtmlRenderer()
    return "".join(
        f'<span class="audion-terminal-line">{active_renderer.render(str(line))}</span>'
        for line in lines
    )


def progress_text() -> str:
    return f"{round(max(0.0, min(1.0, float(state['progress']))) * 100):.0f}%"


def safe_notify(message: str, kind: str = "info", **notify_kwargs: Any) -> None:
    notify_type = str(notify_kwargs.pop("type", kind))
    options = {"message": str(message), "type": notify_type, **notify_kwargs}
    delivered = False
    for client in list(nicegui_app.clients()):
        if getattr(client, "_deleted", False) or not client.has_socket_connection:
            continue
        try:
            client.outbox.enqueue_message("notify", options, client.id)
            delivered = True
        except Exception as exc:
            logging.warning("NiceGUI notification delivery failed for client %s: %s", getattr(client, "id", "?"), exc)
    if delivered:
        return

    try:
        ui.notify(message, type=notify_type, **notify_kwargs)
    except RuntimeError as exc:
        message_text = str(exc)
        if "slot belongs to has been deleted" not in message_text and "current slot cannot be determined" not in message_text:
            raise
        logging.warning("NiceGUI notification skipped because no live client slot was available: %s", message)


def copy_text_to_clipboard(text: str, success_message: str | None = None) -> None:
    payload = str(text or "")
    if not payload:
        safe_notify(
            "Нечего копировать." if settings.language == "ru" else "Nothing to copy.",
            "warning",
        )
        return
    ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(payload)});")
    safe_notify(
        success_message or ("Скопировано." if settings.language == "ru" else "Copied."),
        "positive",
    )


def dangerous_operation_notes(operation: Operation) -> list[str]:
    text = " ".join(
        [
            operation.id,
            operation.service,
            operation.display_title(settings.language),
            operation.display_description(settings.language),
        ]
    ).lower()
    notes: list[str] = []

    if any(word in text for word in ("delete", "remove", "clean", "cleanup", "purge", "reset", "clear")):
        notes.append(
            "Файлы или содержимое управляемых рабочих папок могут быть удалены."
            if settings.language == "ru"
            else "Files or managed workspace folder contents may be removed."
        )
    if any(word in text for word in ("input", "output", "исход", "результ")):
        notes.append(
            "Проверьте, что нужные исходники и результаты уже сохранены вне очищаемых папок."
            if settings.language == "ru"
            else "Check that important sources and results are already saved outside the folders being cleared."
        )

    if not notes:
        notes.append(operation.display_description(settings.language) or tr("confirm_parameters_note"))
    notes.append(tr("confirm_parameters_note"))
    return notes


RUN_STATE_LABELS = {
    "idle": ("idle", "audion-status-idle"),
    "running": ("running", "audion-status-running"),
    "done": ("done", "audion-status-done"),
    "error": ("error", "audion-status-error"),
}


def run_state() -> str:
    """Which of the four states the panel is showing.

    Colour carries this everywhere it appears, so it is decided once.
    """
    if bool(state["running"]):
        return "running"
    exit_code = state.get("exit_code")
    if exit_code is None:
        return "idle"
    return "done" if int(exit_code or 0) == 0 else "error"


def status_row_classes() -> str:
    return f"audion-status-row {RUN_STATE_LABELS[run_state()][1]}"


def status_state_text() -> str:
    return tr(RUN_STATE_LABELS[run_state()][0]).upper()


def elapsed_text(seconds: float | None) -> str:
    """A run's own clock, mm:ss, or an em dash before anything has run.

    The start is noticed by the refresh timer rather than written by the code that
    starts a run: there are several such places, and none of them has to know
    about the panel.
    """
    if seconds is None:
        return "—"
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def status_dot_classes() -> str:
    base = "audion-status-dot text-lg leading-none"
    if bool(state["running"]):
        return f"{base} text-sky-400 animate-pulse"
    if state.get("exit_code") is None:
        return f"{base} text-gray-500"
    if int(state.get("exit_code") or 0) == 0:
        return f"{base} text-green-400"
    return f"{base} text-red-400"


def set_progress(value: float) -> None:
    state["progress"] = max(0.0, min(1.0, float(value)))


def cancel_requested() -> bool:
    return bool(state["cancel"])


def hidden_subprocess_flags() -> int:
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return int(subprocess.CREATE_NO_WINDOW)
    return 0


def hidden_subprocess_startupinfo() -> subprocess.STARTUPINFO | None:
    if os.name != "nt" or not hasattr(subprocess, "STARTUPINFO"):
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return startupinfo


def resolve_dialog_powershell() -> list[str]:
    candidates = [
        [str(paths.system_core / "powershell" / "pwsh.exe"), "-NoLogo", "-NoProfile", "-STA", "-Command"],
        ["pwsh.exe", "-NoLogo", "-NoProfile", "-STA", "-Command"],
        ["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command"],
    ]
    for candidate in candidates:
        exe = candidate[0]
        if Path(exe).exists() or shutil.which(exe):
            return candidate
    raise RuntimeError("PowerShell was not found for Windows picker.")


_PICKER_RUN_LOCK = threading.Lock()
_PICKER_JOB_LOCK = threading.Lock()
_PICKER_JOB_HANDLE: int | None = None


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def close_picker_job() -> None:
    global _PICKER_JOB_HANDLE
    with _PICKER_JOB_LOCK:
        handle = _PICKER_JOB_HANDLE
        _PICKER_JOB_HANDLE = None
    if os.name == "nt" and handle:
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(wintypes.HANDLE(handle))


def _picker_job_handle() -> int | None:
    global _PICKER_JOB_HANDLE
    if os.name != "nt":
        return None
    with _PICKER_JOB_LOCK:
        if _PICKER_JOB_HANDLE:
            return _PICKER_JOB_HANDLE
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            logging.warning("Could not create the Windows picker job: %s", ctypes.get_last_error())
            return None
        info = _JobObjectExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        configured = kernel32.SetInformationJobObject(
            wintypes.HANDLE(job),
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not configured:
            error = ctypes.get_last_error()
            kernel32.CloseHandle(wintypes.HANDLE(job))
            logging.warning("Could not configure the Windows picker job: %s", error)
            return None
        _PICKER_JOB_HANDLE = int(job)
        return _PICKER_JOB_HANDLE


def _assign_picker_to_job(process: subprocess.Popen[str]) -> None:
    handle = _picker_job_handle()
    if os.name != "nt" or not handle:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    assigned = kernel32.AssignProcessToJobObject(
        wintypes.HANDLE(handle),
        wintypes.HANDLE(int(process._handle)),  # type: ignore[attr-defined]
    )
    if not assigned:
        logging.warning("Could not attach picker PID %s to its Windows job: %s", process.pid, ctypes.get_last_error())


def run_picker_script(script: str, failure_message: str) -> str:
    if not _PICKER_RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("A Windows picker is already open.")
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            [*resolve_dialog_powershell(), script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=hidden_subprocess_flags(),
            startupinfo=hidden_subprocess_startupinfo(),
        )
        _assign_picker_to_job(process)
        try:
            stdout, stderr = process.communicate(timeout=3600)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise RuntimeError("Windows picker timed out.") from exc
        if process.returncode != 0:
            raise RuntimeError(stderr.strip() or failure_message)
        return stdout
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        _PICKER_RUN_LOCK.release()


atexit.register(close_picker_job)
nicegui_app.on_shutdown(close_picker_job)


def parse_picker_paths(text: str) -> list[Path]:
    import json

    payload = text.strip()
    if not payload:
        return []
    data = json.loads(payload)
    if isinstance(data, str):
        data = [data]
    return [Path(str(item)).resolve() for item in data if str(item).strip()]


def ps_single_quote(value: str) -> str:
    return value.replace("'", "''")


def pick_files() -> list[Path]:
    dialog_title = "Добавить файлы в исходники" if settings.language == "ru" else "Add files to input"
    all_supported = "Все поддерживаемые файлы" if settings.language == "ru" else "All supported files"
    all_files = "Все файлы" if settings.language == "ru" else "All files"
    script = (
        PICKER_BOOTSTRAP
        + r"""
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = '__DIALOG_TITLE__'
$dialog.Multiselect = $true
$dialog.Filter = '__ALL_SUPPORTED__|*.*|__ALL_FILES__|*.*'
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  $dialog.FileNames | ConvertTo-Json -Compress
}
"""
    )
    script = (
        script.replace("__DIALOG_TITLE__", ps_single_quote(dialog_title))
        .replace("__ALL_SUPPORTED__", ps_single_quote(all_supported))
        .replace("__ALL_FILES__", ps_single_quote(all_files))
    )
    return parse_picker_paths(run_picker_script(script, "File picker failed."))


def pick_single_file() -> list[Path]:
    dialog_title = "Выбрать один файл-источник" if settings.language == "ru" else "Choose one source file"
    all_supported = "Все поддерживаемые файлы" if settings.language == "ru" else "All supported files"
    all_files = "Все файлы" if settings.language == "ru" else "All files"
    script = (
        PICKER_BOOTSTRAP
        + r"""
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = '__DIALOG_TITLE__'
$dialog.Multiselect = $false
$dialog.Filter = '__ALL_SUPPORTED__|*.*|__ALL_FILES__|*.*'
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  @($dialog.FileName) | ConvertTo-Json -Compress
}
"""
    )
    script = (
        script.replace("__DIALOG_TITLE__", ps_single_quote(dialog_title))
        .replace("__ALL_SUPPORTED__", ps_single_quote(all_supported))
        .replace("__ALL_FILES__", ps_single_quote(all_files))
    )
    return parse_picker_paths(run_picker_script(script, "File picker failed."))


def pick_xlsx_file() -> list[Path]:
    dialog_title = "Выбрать готовую адресную таблицу" if settings.language == "ru" else "Choose ready address workbook"
    excel_files = "Книги Excel (*.xlsx)" if settings.language == "ru" else "Excel workbooks (*.xlsx)"
    all_files = "Все файлы" if settings.language == "ru" else "All files"
    script = (
        PICKER_BOOTSTRAP
        + r"""
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = '__DIALOG_TITLE__'
$dialog.Multiselect = $false
$dialog.Filter = '__EXCEL_FILES__|*.xlsx|__ALL_FILES__|*.*'
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  @($dialog.FileName) | ConvertTo-Json -Compress
}
"""
    )
    script = (
        script.replace("__DIALOG_TITLE__", ps_single_quote(dialog_title))
        .replace("__EXCEL_FILES__", ps_single_quote(excel_files))
        .replace("__ALL_FILES__", ps_single_quote(all_files))
    )
    return parse_picker_paths(run_picker_script(script, "XLSX picker failed."))


def pick_folder() -> list[Path]:
    dialog_title = "Добавить папку в исходники" if settings.language == "ru" else "Add folder to input"
    script = (
        PICKER_BOOTSTRAP
        + r"""
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '__DIALOG_TITLE__'
$dialog.ShowNewFolderButton = $false
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  @($dialog.SelectedPath) | ConvertTo-Json -Compress
}
"""
    ).replace("__DIALOG_TITLE__", ps_single_quote(dialog_title))
    return parse_picker_paths(run_picker_script(script, "Folder picker failed."))


def unique_target(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate a unique target name for {path.name}")


def copy_item_to_input(source: Path) -> Path:
    input_resolved = paths.input.resolve()
    source_resolved = source.resolve()

    if source_resolved == input_resolved:
        raise RuntimeError("Cannot import the input folder into itself.")
    if input_resolved.is_relative_to(source_resolved):
        raise RuntimeError(f"Cannot import a parent folder of input: {source}")
    if source_resolved.is_relative_to(input_resolved):
        add_log(f"SKIP already in input -> {source}")
        return source

    target = unique_target(paths.input / source.name)
    if source.is_dir():
        shutil.copytree(source, target)
        return target
    if source.is_file():
        shutil.copy2(source, target)
        return target
    raise RuntimeError(f"Unsupported source path: {source}")


def import_to_input(kind: str) -> int:
    sources = pick_files() if kind == "files" else pick_folder()
    if not sources:
        add_log(tr("picker_cancelled"))
        return 0

    total = len(sources)
    for index, source in enumerate(sources, start=1):
        if cancel_requested():
            add_log("Cancellation requested.")
            return 2
        target = copy_item_to_input(source)
        add_log(f"[{index}/{total}] COPIED -> {target}")
        set_progress(index / max(1, total))
    return 0


def input_file_list_lines(source: Path) -> list[str]:
    if not source.exists():
        return [tr("file_list_missing", path=source)]
    if not source.is_dir():
        return [f"INPUT is not a folder: {source}"]

    names = sorted((path.name for path in source.rglob("*") if path.is_file()), key=lambda item: item.casefold())
    if not names:
        return [tr("file_list_empty")]

    number_width = max(3, len(str(len(names))))
    lines = [
        f"{'No.':>{number_width}}  List",
        f"{'-' * number_width}  ----",
    ]
    lines.extend(f"{index:0{number_width}d}. {name}" for index, name in enumerate(names, start=1))
    return lines


async def show_input_file_list() -> None:
    if state["running"]:
        safe_notify(tr("another_running"), "warning")
        return

    title = tr("file_list")
    state.update(
        {
            "running": True,
            "cancel": False,
            "progress": 0.02,
            "status": f"{tr('running')}: {title}",
            "lines": [],
            "line_offset": int(state.get("line_offset", 0)) + len(state.get("lines", [])) + 1,
            "log_version": int(state["log_version"]) + 1,
            "exit_code": None,
        }
    )
    try:
        lines = await run.io_bound(input_file_list_lines, current_source_path())
        for line in lines:
            add_log(line)
        count = max(0, len(lines) - 2)
        state["terminal_scroll_top_seq"] = int(state["log_version"])
        state["exit_code"] = 0
        state["progress"] = 1.0
        state["status"] = f"{tr('done')}: {title} [{count}]"
        safe_notify(tr("file_list_ready", count=count), "positive")
    except Exception as exc:
        state["exit_code"] = 1
        state["progress"] = max(float(state["progress"]), 0.98)
        state["status"] = f"{tr('error')}: {exc}"
        add_log(f"ERROR: {exc.__class__.__name__}: {exc}")
        safe_notify(str(exc), "negative")
    finally:
        state["running"] = False


async def start_import(kind: str) -> None:
    if state["running"]:
        safe_notify(tr("another_running"), "warning")
        return

    title = tr("stage_files") if kind == "files" else tr("stage_folder")
    state.update(
        {
            "running": True,
            "cancel": False,
            "progress": 0.02,
            "status": f"{tr('running')}: {title}",
            "lines": [],
            "line_offset": 0,
            "log_version": int(state["log_version"]) + 1,
            "exit_code": None,
        }
    )
    try:
        exit_code = await run.io_bound(import_to_input, kind)
        state["exit_code"] = exit_code
        state["progress"] = 1.0
        state["status"] = f"{tr('done')}: {title} [{exit_code}]"
        safe_notify(tr("operation_done") if exit_code == 0 else tr("operation_failed", code=exit_code), "positive" if exit_code == 0 else "negative")
    except Exception as exc:
        state["exit_code"] = 1
        state["progress"] = max(float(state["progress"]), 0.98)
        state["status"] = f"{tr('error')}: {exc}"
        add_log(f"ERROR: {exc.__class__.__name__}: {exc}")
        safe_notify(str(exc), "negative")
    finally:
        state["running"] = False


async def start_operation(operation: Operation) -> None:
    if state["running"]:
        safe_notify(tr("another_running"), "warning")
        return

    if operation.kind == "dangerous":
        with ui.dialog() as dialog, ui.card().classes("audion-dialog audion-confirm-card rounded-lg"):
            ui.label(tr("confirm_title")).classes("text-base font-semibold")
            ui.label(operation.display_title(settings.language)).classes("text-sm font-semibold")
            description = operation.display_description(settings.language)
            if description:
                ui.label(description).classes("text-sm text-gray-400")
            ui.label(tr("confirm_impact_title")).classes("audion-confirm-subtitle")
            for note in dangerous_operation_notes(operation):
                ui.label(f"- {note}").classes("audion-confirm-note")
            ui.label(tr("confirm_irreversible_note")).classes("audion-confirm-warning")
            with ui.row().classes("gap-2"):
                cancel_button = ui.button(tr("cancel"), on_click=dialog.close).props("dense flat").classes("audion-action rounded-lg")
                attach_tooltip(cancel_button, tr("cancel"))
                confirm_button = ui.button(tr("confirm_run_dangerous"), on_click=lambda: dialog.submit(True)).props("dense flat no-wrap").classes("audion-action audion-danger-action rounded-lg")
                attach_tooltip(confirm_button, tr("confirm_run_dangerous"))
        confirmed = await dialog
        if not confirmed:
            return

    state.update(
        {
            "running": True,
            "cancel": False,
            "progress": 0.02,
            "status": f"{tr('running')}: {operation.display_title(settings.language)}",
            "lines": [],
            "line_offset": 0,
            "log_version": int(state["log_version"]) + 1,
            "exit_code": None,
        }
    )
    set_last_artifacts({})
    refresh_artifact_panel_safely()
    started = time.perf_counter()
    try:
        result = await run.io_bound(
            execute_operation,
            active_project_paths(),
            operation,
            add_log,
            set_progress,
            cancel_requested,
        )
        elapsed = time.perf_counter() - started
        state["exit_code"] = 0 if result.ok else 1
        state["progress"] = 1.0
        state["status"] = f"{tr('done') if result.ok else tr('error')}: {operation.display_title(settings.language)} [{state['exit_code']}] {elapsed:.1f}s"
        set_last_artifacts(result.data.get("artifacts") if result.ok else {})
        if result.ok and operation.id == "update_rosstat_oktmo":
            clear_oktmo_option_caches()
            command_tree.refresh()
        refresh_artifact_panel_safely()
        safe_notify(result.message, "positive" if result.ok else "negative")
    except Exception as exc:
        state["exit_code"] = 1
        state["progress"] = max(float(state["progress"]), 0.98)
        state["status"] = f"{tr('error')}: {exc}"
        set_last_artifacts({})
        refresh_artifact_panel_safely()
        add_log(f"ERROR: {exc.__class__.__name__}: {exc}")
        safe_notify(str(exc), "negative")
    finally:
        state["running"] = False


def toggle_language() -> None:
    settings.language = "en" if settings.language == "ru" else "ru"
    save_app_settings()
    reload_ui()


def save_advanced_open(event: Any) -> None:
    settings.advanced_open = bool(getattr(event, "value", False))
    save_app_settings()


def current_source_path() -> Path:
    return Path(str(state.get("source_path") or getattr(settings, "source_path", "") or paths.input)).expanduser()


def current_target_path() -> Path:
    return Path(str(state.get("destination_path") or getattr(settings, "destination_path", "") or paths.output)).expanduser()


def active_project_paths():
    return replace(
        paths,
        input=current_source_path(),
        output=current_target_path(),
    )


def save_workspace_path(kind: str, value: Any) -> None:
    text = str(value or "").strip()
    if kind == "source":
        settings.source_path = text
        state["source_path"] = text
    elif kind == "destination":
        settings.destination_path = text
        state["destination_path"] = text
    else:
        raise RuntimeError(f"Unsupported workspace path kind: {kind}")
    save_app_settings()


def open_workspace_folder(role: str) -> None:
    folder = current_target_path() if role == "target" else current_source_path()
    if role != "target" and not folder.exists():
        raise FileNotFoundError(tr("source_folder_missing", path=folder))
    if folder.is_file():
        if os.name == "nt":
            subprocess.Popen(
                ["explorer.exe", f"/select,{folder}"],
                creationflags=hidden_subprocess_flags(),
                startupinfo=hidden_subprocess_startupinfo(),
            )
        else:
            open_folder(folder.parent)
        return
    open_folder(folder)


def absolute_project_path(path_value: Any) -> Path:
    path = Path(str(path_value or "")).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def remove_path_tree(path: Path) -> int:
    is_junction = bool(getattr(os.path, "isjunction", lambda _path: False)(path))
    if path.is_symlink() or is_junction:
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
        return 1
    if path.is_file():
        path.unlink()
        return 1
    if path.is_dir():
        shutil.rmtree(path)
        return 1
    return 0


def clear_directory_contents(folder: Path) -> int:
    removed = 0
    if not folder.exists():
        return removed
    for child in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
        # .gitkeep is not spared: input and output must be genuinely empty after
        # a clear, so nobody has to wonder what the leftover file is or whether it
        # is safe to delete. The folders come from install/init_folders.cmd.
        removed += remove_path_tree(child)
    return removed


def normalized_absolute_path(path_value: Any) -> Path:
    return absolute_project_path(path_value).resolve(strict=False)


def paths_equal(left: Any, right: Any) -> bool:
    return os.path.normcase(str(normalized_absolute_path(left))) == os.path.normcase(str(normalized_absolute_path(right)))


def validate_workspace_delete_target(path_value: Any) -> Path:
    target = normalized_absolute_path(path_value)
    if target.parent == target:
        raise RuntimeError(f"Refusing to delete a filesystem root: {target}")
    if paths_equal(target, ROOT):
        raise RuntimeError(f"Refusing to delete the project root: {target}")
    return target


def delete_workspace_path_contents(path_value: Any) -> dict[str, Any]:
    target = validate_workspace_delete_target(path_value)
    if not target.exists() and not target.is_symlink():
        return {"path": str(target), "kind": "missing", "removed": 0}
    is_junction = bool(getattr(os.path, "isjunction", lambda _path: False)(target))
    if target.is_file() or target.is_symlink() or is_junction:
        removed = remove_path_tree(target)
        return {"path": str(target), "kind": "file", "removed": removed}
    if not target.is_dir():
        raise RuntimeError(f"Unsupported workspace path: {target}")
    removed = clear_directory_contents(target)
    return {"path": str(target), "kind": "folder", "removed": removed}


def delete_workspace_io_contents(source: Path, target: Path) -> dict[str, Any]:
    source_result = delete_workspace_path_contents(source)
    if paths_equal(source, target):
        target_result = {"path": str(normalized_absolute_path(target)), "kind": "same", "removed": 0}
    else:
        target_result = delete_workspace_path_contents(target)
    return {"source": source_result, "target": target_result}


def mark_workspace_feedback(role: str, action: str) -> None:
    state["workspace_feedback"] = {"role": canonical_role(role), "action": str(action or "path")}


def _save_workspace_adapter_path(role: WorkbenchRole, value: Any) -> None:
    save_workspace_path("destination" if role == "target" else "source", value)


def _workspace_feedback() -> dict[str, str]:
    value = state.get("workspace_feedback")
    return dict(value) if isinstance(value, dict) else {}


def _clear_workspace_feedback() -> None:
    state["workspace_feedback"] = {}


WORKBENCH_CONFIG = WorkbenchConfig(
    root=ROOT,
    input_path=paths.input,
    output_path=paths.output,
    history_path=_workspace_history_file(),
    history_limit=PATH_HISTORY_LIMIT,
)
WORKBENCH_ADAPTER = WorkbenchAdapter(
    config=WORKBENCH_CONFIG,
    current_path_callback=lambda role: current_target_path() if role == "target" else current_source_path(),
    save_path_callback=_save_workspace_adapter_path,
    language_callback=lambda: settings.language,
    translate_callback=tr,
    log_callback=add_log,
    notify_callback=safe_notify,
    reload_callback=reload_ui,
    busy_callback=lambda: bool(state.get("running")),
    feedback_callback=_workspace_feedback,
    set_feedback_callback=mark_workspace_feedback,
    clear_feedback_callback=_clear_workspace_feedback,
)
WORKBENCH_ADAPTER.validate()
WORKBENCH_ADAPTER.ensure_initial_history()


def normalize_artifacts(value: Any) -> dict[str, list[str]]:
    data = value if isinstance(value, dict) else {}
    return {
        "outputs": _artifact_paths_for_ui(data.get("outputs")),
        "reports": _artifact_paths_for_ui(data.get("reports")),
        "staging": _artifact_paths_for_ui(data.get("staging")),
        "inputs": _artifact_paths_for_ui(data.get("inputs")),
    }


def _artifact_paths_for_ui(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (str, Path)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, dict):
        return _artifact_paths_for_ui(list(value.values()))
    if isinstance(value, (list, tuple, set, frozenset)):
        result: list[str] = []
        for item in value:
            result.extend(_artifact_paths_for_ui(item))
        return list(dict.fromkeys(result))
    return [str(value)]


def set_last_artifacts(value: Any) -> None:
    state["last_artifacts"] = normalize_artifacts(value)
    state["last_artifacts_version"] = int(state.get("last_artifacts_version", 0)) + 1


def open_artifact_path(path_value: str) -> None:
    path = Path(str(path_value or "")).expanduser()
    folder = path if path.is_dir() else path.parent
    if not str(folder):
        folder = paths.output
    open_folder(folder)


def artifact_button_tooltip(items: list[str]) -> str:
    if not items:
        return ""
    preview = "\n".join(items[:5])
    if len(items) > 5:
        preview += f"\n+{len(items) - 5}"
    return preview


def report_summary_rows(data: dict[str, Any], path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [("file", path.name)]

    def add(key: str, label: str | None = None) -> None:
        value = data.get(key)
        if value not in (None, "", [], {}):
            rows.append((label or key, str(value)))

    for key in (
        "mode",
        "action",
        "source_file_count",
        "raw_candidates",
        "scanned_values",
        "plausible_values",
        "accepted_candidates",
        "normalized_rows",
        "duplicate_rows",
        "rejected_rows",
        "appended_rows",
        "data_rows",
        "sorted_rows",
        "deconstructed_rows",
        "matched_unique_key_count",
        "missing_unique_key_count",
        "extra_unique_key_count",
    ):
        add(key)

    quality = data.get("quality")
    if isinstance(quality, dict):
        coverage = quality.get("coverage_percent")
        precision = quality.get("precision_percent")
        if coverage is not None or precision is not None:
            rows.append(("quality", f"coverage={coverage}%, precision={precision}%"))

    diagnostics = data.get("address_diagnostics")
    if isinstance(diagnostics, dict):
        rows.extend(_diagnostic_summary_rows(diagnostics))

    slot_fill = data.get("slot_fill")
    if isinstance(slot_fill, dict):
        rows.extend(_slot_fill_summary_rows(slot_fill))

    normalizer = data.get("normalizer") or (data.get("address_runtime") or {}).get("normalizer")
    if isinstance(normalizer, dict):
        rows.append(
            (
                "normalizer",
                "use_oktmo="
                f"{normalizer.get('use_oktmo')}, "
                f"TER={normalizer.get('subject_ter_hint') or '-'}, "
                f"municipality={normalizer.get('municipality_hint') or '-'}",
            )
        )
    return rows[:40]


def _diagnostic_summary_rows(diagnostics: dict[str, Any]) -> list[tuple[str, str]]:
    if "total" in diagnostics:
        return [("diagnostics", f"total={diagnostics.get('total')}, issues={diagnostics.get('issue_rows')}")]
    rows: list[tuple[str, str]] = []
    for name, value in diagnostics.items():
        if isinstance(value, dict) and "total" in value:
            rows.append((f"diagnostics.{name}", f"total={value.get('total')}, issues={value.get('issue_rows')}"))
    return rows


def _slot_fill_summary_rows(slot_fill: dict[str, Any]) -> list[tuple[str, str]]:
    if "rows_total" in slot_fill:
        return [
            (
                "slot_fill",
                f"rows={slot_fill.get('rows_total')}, "
                f"complete={slot_fill.get('complete_rows')}, "
                f"incomplete={slot_fill.get('incomplete_rows')}",
            )
        ]
    rows: list[tuple[str, str]] = []
    for name, value in slot_fill.items():
        if isinstance(value, dict) and "rows_total" in value:
            rows.append(
                (
                    f"slot_fill.{name}",
                    f"rows={value.get('rows_total')}, "
                    f"complete={value.get('complete_rows')}, "
                    f"incomplete={value.get('incomplete_rows')}",
                )
            )
    return rows


def show_report_summary(path_value: str) -> None:
    report_path = Path(str(path_value or "")).expanduser()
    if not report_path.exists():
        safe_notify(f"Report not found: {report_path}", "negative")
        return
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        safe_notify(f"Could not read report: {exc}", "negative")
        open_artifact_path(str(report_path))
        return
    if not isinstance(data, dict):
        safe_notify("Report JSON root is not an object.", "negative")
        return

    with ui.dialog() as dialog, ui.card().classes("audion-dialog w-[min(860px,92vw)] rounded-lg p-3"):
        with ui.row().classes("w-full items-center gap-2"):
            ui.label(tr("report_summary")).classes("text-base font-semibold")
            ui.space()
            open_button = ui.button(tr("open_menu"), icon="folder_open", on_click=lambda: open_artifact_path(str(report_path))).props("dense flat no-wrap").classes("audion-action rounded-lg")
            attach_tooltip(open_button, tr("open_menu"))
            close_button = ui.button(tr("close"), on_click=dialog.close).props("dense flat").classes("audion-action rounded-lg")
            attach_tooltip(close_button, tr("close"))
        ui.label(str(report_path)).classes("text-xs text-gray-400")
        with ui.element("div").classes("audion-report-summary-grid"):
            for label, value in report_summary_rows(data, report_path):
                ui.label(label).classes("audion-report-summary-key")
                ui.label(value).classes("audion-report-summary-value")
        with ui.expansion(tr("raw_json")).classes("w-full"):
            raw = html.escape(json.dumps(data, ensure_ascii=False, indent=2)[:20000])
            ui.html(f"<pre class=\"audion-report-json\">{raw}</pre>", sanitize=False)
    dialog.open()


@ui.refreshable
def artifact_panel() -> None:
    artifacts = normalize_artifacts(state.get("last_artifacts"))
    entries = (
        ("outputs", "artifact_output", "folder_open"),
        ("reports", "artifact_report", "summarize"),
        ("staging", "artifact_staging", "fact_check"),
    )
    visible_entries = [(key, label_key, icon) for key, label_key, icon in entries if artifacts.get(key)]
    if not visible_entries:
        return
    with ui.row().classes("audion-artifact-row w-full items-center gap-2"):
        ui.label(tr("artifacts")).classes("audion-artifact-title")
        for key, label_key, icon in visible_entries:
            items = artifacts[key]
            label = tr(label_key)
            if len(items) > 1:
                label = f"{label} {len(items)}"
            action = (lambda first=items[0]: show_report_summary(first)) if key == "reports" else (lambda first=items[0]: open_artifact_path(first))
            button = ui.button(label, icon=icon, on_click=action)
            button.props("dense flat no-wrap").classes("audion-action audion-artifact-button rounded-lg")
            button.tooltip(artifact_button_tooltip(items))


def refresh_artifact_panel_safely() -> None:
    try:
        artifact_panel.refresh()
    except RuntimeError as exc:
        message = str(exc)
        if "slot belongs to has been deleted" not in message and "current slot cannot be determined" not in message:
            raise
        logging.warning("Artifact panel refresh skipped because the client slot was deleted.")


def workspace_pin_click_handler(role: str, pinned: bool):
    async def handler() -> None:
        path_value = str(current_target_path() if role == "target" else current_source_path())
        if not path_value:
            safe_notify(tr("path_required"), "warning")
            return
        try:
            await run.io_bound(WORKBENCH_ADAPTER.set_path_pinned, role, path_value, pinned)
            mark_workspace_feedback(role, "pin" if pinned else "unpin")
            add_log(f"{'Pinned' if pinned else 'Unpinned'} {role} path: {path_value}")
            reload_ui(150)
        except Exception as exc:
            add_log(f"ERROR: {exc.__class__.__name__}: {exc}")
            safe_notify(str(exc), "negative")

    return handler


def workspace_delete_path_click_handler(role: str):
    async def handler() -> None:
        if state["running"]:
            safe_notify(tr("another_running"), "warning")
            return
        path = current_target_path() if role == "target" else current_source_path()
        path_value = str(path)
        if not path_value:
            safe_notify(tr("path_required"), "warning")
            return
        external_source = role != "target" and not paths_equal(path, paths.input)
        if external_source:
            is_file = path.is_file()
            with ui.dialog() as dialog, ui.card().classes("audion-dialog rounded-lg"):
                title = "Удалить исходный файл?" if is_file else "Очистить внешний ИСТОЧНИК?"
                if settings.language != "ru":
                    title = "Delete the source file?" if is_file else "Clear the external SOURCE?"
                ui.label(title).classes("text-base font-semibold")
                warning = (
                    "Будет удалён исходный файл. Другой копии может не существовать."
                    if is_file
                    else "Будут безвозвратно удалены все файлы и вложенные папки."
                )
                if settings.language != "ru":
                    warning = (
                        "The source file will be deleted. Another copy may not exist."
                        if is_file
                        else "All files and nested folders will be permanently deleted."
                    )
                ui.label(warning).classes("text-sm text-gray-300")
                ui.label(str(normalized_absolute_path(path))).classes("max-w-3xl break-all font-mono text-xs text-gray-400")
                with ui.row().classes("gap-2"):
                    ui.button(tr("cancel"), on_click=dialog.close).props("dense flat")
                    ui.button(tr("delete_io_short"), on_click=lambda: dialog.submit(True)).props("dense color=negative")
            confirmed = await dialog
            if not confirmed:
                return
        try:
            result = await run.io_bound(delete_workspace_path_contents, path)
            if result.get("kind") == "file":
                await run.io_bound(WORKBENCH_ADAPTER.delete_path_history, role, path_value)
                save_workspace_path("destination" if role == "target" else "source", "")
            mark_workspace_feedback(role, "delete")
            add_log(
                f"Cleared {'TARGET' if role == 'target' else 'SOURCE'}: {result.get('path')} "
                f"[kind={result.get('kind')}, removed={result.get('removed', 0)}]"
            )
            reload_ui(150)
        except Exception as exc:
            add_log(f"ERROR: {exc.__class__.__name__}: {exc}")
            safe_notify(str(exc), "negative")

    return handler


def workspace_single_file_click_handler():
    async def handler() -> None:
        if state["running"]:
            safe_notify(tr("another_running"), "warning")
            return
        try:
            selected = await run.io_bound(pick_single_file)
        except Exception as exc:
            add_log(f"ERROR: {exc.__class__.__name__}: {exc}")
            safe_notify(str(exc), "negative")
            return
        if not selected:
            add_log(tr("picker_cancelled"))
            return
        path_value = str(selected[0])
        save_workspace_path("source", path_value)
        await run.io_bound(WORKBENCH_ADAPTER.remember_path, "source", path_value)
        mark_workspace_feedback("source", "path")
        add_log(f"SOURCE FILE -> {path_value}")
        reload_ui(150)

    return handler


def workspace_open_click_handler(role: str):
    async def handler() -> None:
        try:
            await run.io_bound(open_workspace_folder, role)
            add_log(f"Opened {'target' if role == 'target' else 'source'} folder: {current_target_path() if role == 'target' else current_source_path()}")
        except Exception as exc:
            add_log(f"ERROR: {exc.__class__.__name__}: {exc}")
            safe_notify(str(exc), "negative")

    return handler


def reset_workspace_paths_click_handler():
    async def handler() -> None:
        if state["running"]:
            safe_notify(tr("another_running"), "warning")
            return
        result = await run.io_bound(WORKBENCH_ADAPTER.clear_path_history_cache_keep_pins)
        save_workspace_path("source", "")
        save_workspace_path("destination", "")
        add_log(f"Workspace route reset: SOURCE -> {paths.input}")
        add_log(f"Workspace route reset: TARGET -> {paths.output}")
        add_log(
            "Workspace path cache cleared: "
            f"sources={result.get('removed_sources', 0)}, targets={result.get('removed_targets', 0)}, "
            f"pins kept={result.get('kept_pins', 0)}"
        )
        safe_notify(tr("operation_done"), "positive")
        reload_ui()

    return handler


def workspace_path_select_handler(role: str):
    async def handler(event: Any) -> None:
        path_value = str(getattr(event, "value", "") or "").strip()
        if not path_value:
            return
        save_workspace_path("destination" if role == "target" else "source", path_value)
        await run.io_bound(WORKBENCH_ADAPTER.remember_path, role, path_value)
        mark_workspace_feedback(role, "path")
        add_log(f"{'TARGET' if role == 'target' else 'SOURCE'} -> {path_value}")
        reload_ui(150)

    return handler


def workspace_delete_both_click_handler():
    async def handler() -> None:
        if state["running"]:
            safe_notify(tr("another_running"), "warning")
            return
        source = current_source_path()
        target = current_target_path()
        source_external = not paths_equal(source, paths.input)
        with ui.dialog() as dialog, ui.card().classes("audion-dialog rounded-lg"):
            ui.label("Удалить содержимое I/O?" if settings.language == "ru" else "Delete I/O contents?").classes("text-base font-semibold")
            warning = (
                "Будут удалены файлы ИСТОЧНИКА и НАЗНАЧЕНИЯ. Внешний ИСТОЧНИК может быть единственным экземпляром."
                if source_external
                else "Будут удалены файлы ИСТОЧНИКА и НАЗНАЧЕНИЯ."
            )
            if settings.language != "ru":
                warning = (
                    "SOURCE and TARGET files will be deleted. The external SOURCE may be the only copy."
                    if source_external
                    else "SOURCE and TARGET files will be deleted."
                )
            ui.label(warning).classes("text-sm text-gray-300")
            ui.label(f"SOURCE: {normalized_absolute_path(source)}").classes("max-w-3xl break-all font-mono text-xs text-gray-400")
            ui.label(f"TARGET: {normalized_absolute_path(target)}").classes("max-w-3xl break-all font-mono text-xs text-gray-400")
            with ui.row().classes("gap-2"):
                ui.button(tr("cancel"), on_click=dialog.close).props("dense flat")
                ui.button(tr("delete_io_short"), on_click=lambda: dialog.submit(True)).props("dense color=negative")
        confirmed = await dialog
        if not confirmed:
            return
        state["running"] = True
        try:
            result = await run.io_bound(delete_workspace_io_contents, source, target)
            source_result = result.get("source", {})
            target_result = result.get("target", {})
            if source_result.get("kind") == "file":
                await run.io_bound(WORKBENCH_ADAPTER.delete_path_history, "source", str(source))
                save_workspace_path("source", "")
            if target_result.get("kind") == "file":
                await run.io_bound(WORKBENCH_ADAPTER.delete_path_history, "target", str(target))
                save_workspace_path("destination", "")
            add_log(
                f"Cleared SOURCE: {source_result.get('path')} "
                f"[kind={source_result.get('kind')}, removed={source_result.get('removed', 0)}]"
            )
            add_log(
                f"Cleared TARGET: {target_result.get('path')} "
                f"[kind={target_result.get('kind')}, removed={target_result.get('removed', 0)}]"
            )
            mark_workspace_feedback("source", "delete")
            reload_ui(150)
        except Exception as exc:
            add_log(f"ERROR: {exc.__class__.__name__}: {exc}")
            safe_notify(str(exc), "negative")
        finally:
            state["running"] = False

    return handler


def workspace_pick_click_handler(role: str):
    async def handler() -> None:
        if state["running"]:
            safe_notify(tr("another_running"), "warning")
            return
        try:
            selected = await run.io_bound(pick_folder)
        except Exception as exc:
            safe_notify(str(exc), "negative")
            return
        if not selected:
            add_log(tr("picker_cancelled"))
            return
        save_workspace_path("destination" if role == "target" else "source", str(selected[0]))
        await run.io_bound(WORKBENCH_ADAPTER.remember_path, role, str(selected[0]))
        mark_workspace_feedback(role, "path")
        add_log(f"{'TARGET' if role == 'target' else 'SOURCE'} -> {selected[0]}")
        reload_ui(150)

    return handler


WORKBENCH_RENDERER = WorkbenchRenderer(
    adapter=WORKBENCH_ADAPTER,
    handlers=WorkbenchHandlers(
        delete_path=workspace_delete_path_click_handler,
        pin_path=workspace_pin_click_handler,
        select_path=workspace_path_select_handler,
        pick_path=workspace_pick_click_handler,
        open_path=workspace_open_click_handler,
        add_file=workspace_single_file_click_handler,
        reset_paths=reset_workspace_paths_click_handler,
        delete_io=workspace_delete_both_click_handler,
        list_files=show_input_file_list,
    ),
    display_path_callback=display_path,
)


def operation_button(operation: Operation) -> None:
    with ui.element("div").classes("audion-operation-row"):
        button = ui.button(
            operation.display_title(settings.language),
            on_click=operation_click_handler(operation),
        ).props("dense flat no-wrap").classes("audion-action audion-operation-button rounded-lg")
        attach_tooltip(button, operation.display_description(settings.language) or operation.display_title(settings.language))
        ui.label(operation.display_description(settings.language)).classes("audion-operation-description")


def operation_click_handler(operation: Operation):
    async def handler() -> None:
        await start_operation(operation)

    return handler


def import_click_handler(kind: str):
    async def handler() -> None:
        await start_import(kind)

    return handler


def operation_to_command_node(operation: Operation) -> CommandNode:
    return CommandNode(
        id=operation.id,
        title=operation.title,
        description=operation.description,
        service=operation.service,
        kind=operation.kind,
        title_ru=operation.title_ru,
        description_ru=operation.description_ru,
        parameters=dict(operation.parameters),
        fields=operation.fields,
    )


def root_command_nodes() -> list[CommandNode]:
    if manifest.operation_groups:
        nodes = list(manifest.operation_groups)
        by_id = {node.id: node for node in nodes}
        ordered: list[CommandNode] = []
        oktmo = by_id.get("oktmo_tools")
        if oktmo is not None:
            ordered.append(oktmo)
        deferred_ids = {
            "oktmo_tools",
            "run_table_comparison",
            "run_safe_table_join",
            "convert_legacy_office_sources",
            "diagnostics",
        }
        for node in nodes:
            if node.id not in deferred_ids:
                ordered.append(node)
        for node_id in ("run_table_comparison", "run_safe_table_join", "convert_legacy_office_sources", "diagnostics"):
            node = by_id.get(node_id)
            if node is not None:
                ordered.append(node)
        return ordered
    return [operation_to_command_node(operation) for operation in manifest.operations]


def command_node_visible(node: CommandNode) -> bool:
    return not bool(getattr(node, "gui_hidden", False))


def command_visible_nodes(nodes: list[CommandNode] | tuple[CommandNode, ...]) -> list[CommandNode]:
    return [node for node in nodes if command_node_visible(node)]


def command_auto_open_child(node: CommandNode) -> CommandNode | None:
    child_id = str(getattr(node, "auto_open_child", "") or "").strip()
    if not child_id:
        return None
    return next((child for child in node.children if child.id == child_id), None)


def current_command_level() -> tuple[list[CommandNode], list[CommandNode]]:
    trail: list[CommandNode] = []
    nodes = root_command_nodes()
    for node_id in list(state.get("command_path", [])):
        node = next((candidate for candidate in nodes if candidate.id == node_id), None)
        if node is None:
            state["command_path"] = []
            state["pending_command"] = None
            return [], root_command_nodes()
        trail.append(node)
        nodes = list(node.children)
    return trail, nodes


def enter_command_node(node: CommandNode) -> None:
    state["pending_command"] = None
    state["command_path"] = [*state.get("command_path", []), node.id]
    command_tree.refresh()


def select_command_node(node: CommandNode) -> None:
    state["pending_command"] = node
    command_tree.refresh()


async def activate_command_node(node: CommandNode) -> None:
    if node.children:
        child = command_auto_open_child(node)
        if child is not None:
            state["command_path"] = [*state.get("command_path", []), node.id]
            state["pending_command"] = child
            command_tree.refresh()
            return
        enter_command_node(node)
        return
    select_command_node(node)


def command_click_handler(node: CommandNode):
    async def handler() -> None:
        await activate_command_node(node)

    return handler


def go_back_command() -> None:
    if state.get("pending_command") is not None:
        pending = state.get("pending_command")
        trail, _nodes = current_command_level()
        if trail and isinstance(pending, CommandNode) and command_auto_open_child(trail[-1]) == pending:
            path = list(state.get("command_path", []))
            if path:
                path.pop()
            state["command_path"] = path
        state["pending_command"] = None
    else:
        path = list(state.get("command_path", []))
        if path:
            path.pop()
        state["command_path"] = path
    command_tree.refresh()


def field_id(field: dict[str, Any]) -> str:
    return str(field.get("id") or field.get("name") or "").strip()


def field_label(field: dict[str, Any]) -> str:
    language = settings.language
    if language == "ru" and field.get("label_ru"):
        return str(field["label_ru"])
    return str(field.get("label") or field.get("title") or field_id(field))


def field_hint(field: dict[str, Any]) -> str:
    language = settings.language
    if language == "ru" and field.get("hint_ru"):
        return str(field["hint_ru"])
    return str(field.get("hint") or "")


def attach_tooltip(control: Any, text: str | None) -> Any:
    tooltip_text = str(text or "").strip()
    if tooltip_text:
        control.tooltip(tooltip_text)
    return control


def field_tooltip_text(label: str, hint: str) -> str:
    label_text = str(label or "").strip()
    hint_text = str(hint or "").strip()
    if label_text and hint_text:
        return f"{label_text}\n{hint_text}"
    return hint_text or label_text


def field_default(field: dict[str, Any]) -> Any:
    if "default" in field:
        return field["default"]
    kind = str(field.get("type", field.get("kind", "text"))).lower()
    options = field.get("options", [])
    if kind in {"slot_order", "slot-order", "slotorder"}:
        return slot_order_default(field)
    if kind in {"checkboxes", "multi_checkbox", "multicheckbox", "multi-select", "multiselect"}:
        if not isinstance(options, list):
            return []
        selected: list[Any] = []
        for option in options:
            if isinstance(option, dict) and option.get("default", False):
                selected.append(option.get("value", option.get("id", option.get("label"))))
        return selected
    if isinstance(options, list) and options:
        first = options[0]
        if isinstance(first, dict):
            return first.get("value", first.get("id", ""))
        return first
    return ""


def current_field_value(field: dict[str, Any]) -> Any:
    key = field_id(field)
    values = state.setdefault("field_values", {})
    if key not in values:
        values[key] = field_default(field)
    return values[key]


def set_field_value(key: str, value: Any) -> None:
    state.setdefault("field_values", {})[key] = value


def set_field_value_from_event(key: str, field: dict[str, Any], value: Any) -> None:
    set_field_value(key, value)
    if key == "oktmo_scope_region":
        state.setdefault("field_values", {}).pop("oktmo_scope_municipality", None)
        clear_dynamic_option_cache("system_core.services.address_aligner_service:oktmo_municipality_scope_options")
    if bool(field.get("refresh_on_change", False)) or key in OKTMO_SCOPE_SELECT_IDS:
        command_tree.refresh()


def adjusted_number_value(field: dict[str, Any], current: Any, direction: int) -> int | float:
    step_raw = field.get("step", 1)
    try:
        step = float(step_raw)
    except (TypeError, ValueError):
        step = 1.0

    seed = current
    if seed is None or seed == "":
        seed = field_default(field) or 0
    try:
        value = float(seed)
    except (TypeError, ValueError):
        value = 0.0

    value += step * (1 if direction > 0 else -1)
    for bound_key, clamp in (("min", max), ("max", min)):
        bound = field.get(bound_key)
        if bound is None or bound == "":
            continue
        try:
            value = clamp(value, float(bound))
        except (TypeError, ValueError):
            continue

    kind = str(field.get("type", field.get("kind", "number"))).lower()
    integer_like = kind in {"number", "int", "integer"} and float(step).is_integer()
    return int(round(value)) if integer_like else round(value, 6)


def spin_number_field(key: str, field: dict[str, Any], control: Any, direction: int) -> None:
    value = adjusted_number_value(field, state.setdefault("field_values", {}).get(key), direction)
    set_field_value(key, value)
    control.set_value(value)


def dynamic_option_source(field: dict[str, Any]) -> str:
    return str(field.get("options_source") or field.get("source") or "").strip()


def refresh_dynamic_options(field: dict[str, Any]) -> None:
    source = dynamic_option_source(field)
    if source:
        clear_dynamic_option_cache(source)
    key = field_id(field)
    if key:
        state.setdefault("field_values", {}).pop(key, None)
    command_tree.refresh()


def refresh_options_click_handler(field: dict[str, Any]):
    def handler() -> None:
        refresh_dynamic_options(field)

    return handler


OKTMO_SCOPE_SELECT_IDS = {
    "oktmo_scope_region": "region",
    "oktmo_scope_municipality": "municipality",
}
OKTMO_FULL_WIDTH_FIELD_IDS = {
    "use_oktmo",
    "oktmo_scope_enabled",
    "oktmo_scope_region",
    "oktmo_scope_municipality",
    "oktmo_key_toolbar",
}
OKTMO_OPTION_SOURCES = (
    "system_core.services.address_aligner_service:oktmo_region_scope_options",
    "system_core.services.address_aligner_service:oktmo_municipality_scope_options",
)
UI_ONLY_FIELD_TYPES = {"oktmo_key_toolbar", "oktmo-key-toolbar"}


def clear_dynamic_option_cache(source: str) -> None:
    for key in list(dynamic_option_cache):
        if key == source or (isinstance(key, tuple) and key and key[0] == source):
            dynamic_option_cache.pop(key, None)


def clear_oktmo_option_caches() -> None:
    for source in OKTMO_OPTION_SOURCES:
        clear_dynamic_option_cache(source)


def oktmo_data_status(field: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return address_service.oktmo_data_status(ROOT, dict(state.setdefault("field_values", {})), field or {})
    except Exception as exc:
        return {"ok": False, "error": str(exc), "latest_name": "", "rosstat_dir": str(paths.root / "data" / "rosstat")}


def update_oktmo_click_handler():
    async def handler() -> None:
        operation = operation_by_id("update_rosstat_oktmo") or command_default_operation("update_rosstat_oktmo")
        if operation is None:
            safe_notify("Команда обновления ОКТМО не найдена." if settings.language == "ru" else "OKTMO update command was not found.", "negative")
            return
        await start_operation(operation)

    return handler


def render_oktmo_data_status(field: dict[str, Any]) -> None:
    status = oktmo_data_status(field)
    if bool(status.get("ok")):
        latest = str(status.get("latest_name") or display_path(status.get("latest")))
        ui.label(tr("oktmo_registry_ready", file=latest)).classes("audion-field-hint audion-oktmo-data-status")
        return

    detail = str(status.get("error") or "")
    message = tr("oktmo_registry_missing")
    if detail:
        message = f"{message} {detail}"
    with ui.row().classes("audion-oktmo-data-warning items-center gap-2"):
        ui.label(message).classes("audion-field-hint audion-oktmo-data-warning-text")
        button = ui.button(
            tr("download_oktmo"),
            icon="cloud_download",
            on_click=update_oktmo_click_handler(),
        ).props("dense flat no-wrap").classes("audion-action audion-oktmo-download-button rounded-lg")
        attach_tooltip(button, tr("download_oktmo"))


def render_oktmo_console_actions() -> None:
    update_text = "ОБНОВИТЬ БАЗУ ДАННЫХ ОКТМО" if settings.language == "ru" else "UPDATE OKTMO DATABASE"
    reset_text = "СБРОСИТЬ КЛЮЧИ ОКТМО" if settings.language == "ru" else "RESET OKTMO KEYS"
    reset_tooltip = (
        "Очистить выбранный регион, муниципалитет, поиск НП и текущий файл ключей. Пины и сохранённые пути остаются."
        if settings.language == "ru"
        else "Clear selected region, municipality, settlement search, and the current key file. Pins and saved paths remain."
    )
    with ui.element("div").classes("audion-oktmo-console-actions"):
        update_button = ui.button(
            update_text,
            icon="cloud_download",
            on_click=update_oktmo_click_handler(),
        ).props("dense flat no-wrap").classes("audion-action audion-oktmo-key-button audion-oktmo-console-action rounded-lg")
        attach_tooltip(update_button, update_text)
        reset_button = ui.button(
            reset_text,
            icon="restart_alt",
            on_click=oktmo_reset_keys_click_handler(),
        ).props("dense flat no-wrap").classes("audion-action audion-oktmo-key-button audion-oktmo-console-action rounded-lg")
        attach_tooltip(reset_button, reset_tooltip)


def is_ui_only_field(field: dict[str, Any]) -> bool:
    kind = str(field.get("type", field.get("kind", "text"))).lower()
    return kind in UI_ONLY_FIELD_TYPES or bool(field.get("ui_only", False))


def is_gui_hidden_field(field: dict[str, Any]) -> bool:
    return bool(field.get("gui_hidden", field.get("hide_in_gui", False)))


def _oktmo_scope_label(kind: str) -> str:
    if settings.language == "ru":
        return "регион" if kind == "region" else "муниципалитет"
    return "region" if kind == "region" else "municipality"


def _oktmo_action_message(action: str, result: dict[str, Any]) -> str:
    path = display_path(result.get("path"))
    keys = int(result.get("keys") or result.get("saved") or 0)
    regions = int(result.get("regions") or 0)
    municipalities = int(result.get("municipalities") or 0)
    if action == "pin":
        return "Закреплено." if settings.language == "ru" else "Pinned."
    if action == "unpin":
        return "Откреплено." if settings.language == "ru" else "Unpinned."
    if action == "add":
        added = int(result.get("added") or 0)
        return (
            f"Добавлено ключей: {added}. Всего в файле: {keys}."
            if settings.language == "ru"
            else f"Added keys: {added}. Total in file: {keys}."
        )
    if action == "find_candidate":
        count = int(result.get("count") or 0)
        return (
            f"Найдено кандидатов ОКТМО: {count}."
            if settings.language == "ru"
            else f"OKTMO candidates found: {count}."
        )
    if action == "add_candidate":
        added = int(result.get("added") or 0)
        return (
            f"Добавлено ключей по найденному НП: {added}. Всего в файле: {keys}."
            if settings.language == "ru"
            else f"Added keys from candidate: {added}. Total in file: {keys}."
        )
    if action == "save":
        return (
            f"Ключи сохранены: {keys}. {path}"
            if settings.language == "ru"
            else f"Keys saved: {keys}. {path}"
        )
    if action == "load":
        return (
            f"Ключи загружены: {keys}. {path}"
            if settings.language == "ru"
            else f"Keys loaded: {keys}. {path}"
        )
    if action == "clear":
        return "Ключи очищены." if settings.language == "ru" else "Keys cleared."
    if action == "reset_keys":
        return (
            "Ключи ОКТМО сброшены. Регион, муниципалитет и поиск НП очищены."
            if settings.language == "ru"
            else "OKTMO keys reset. Region, municipality, and settlement search were cleared."
        )
    if action == "open":
        return (
            f"Файл ключей открыт: {path}"
            if settings.language == "ru"
            else f"Key file opened: {path}"
        )
    if action == "pins_open":
        return (
            f"Файл пинов открыт: {path}"
            if settings.language == "ru"
            else f"Pin file opened: {path}"
        )
    if action == "pins_export":
        return (
            f"Пины экспортированы: регионов {regions}, МО {municipalities}. {path}"
            if settings.language == "ru"
            else f"Pins exported: regions {regions}, municipalities {municipalities}. {path}"
        )
    if action == "pins_import":
        return (
            f"Пины импортированы: регионов {regions}, МО {municipalities}. {path}"
            if settings.language == "ru"
            else f"Pins imported: regions {regions}, municipalities {municipalities}. {path}"
        )
    if action == "pins_clear":
        return "Пины очищены." if settings.language == "ru" else "Pins cleared."
    return "Готово." if settings.language == "ru" else "Done."


async def _run_oktmo_scope_action(kind: str, action: str) -> None:
    if state["running"]:
        safe_notify(tr("another_running"), "warning")
        return
    values = dict(state.setdefault("field_values", {}))
    try:
        if action == "pin":
            result = await run.io_bound(address_service.oktmo_pin_scope_value, ROOT, values, kind)
            clear_oktmo_option_caches()
        elif action == "unpin":
            result = await run.io_bound(address_service.oktmo_unpin_scope_value, ROOT, values, kind)
            clear_oktmo_option_caches()
        elif action == "add":
            safe_notify(
                "Добавляю ключи ОКТМО..." if settings.language == "ru" else "Adding OKTMO keys...",
                "info",
                timeout=2500,
            )
            result = await run.io_bound(address_service.oktmo_add_scope_keys, ROOT, values, kind)
        else:
            return
    except Exception as exc:
        safe_notify(str(exc), "negative")
        return
    message = _oktmo_action_message(action, result)
    add_log(f"OKTMO {_oktmo_scope_label(kind)}: {message}")
    safe_notify(message, "positive")
    command_tree.refresh()


def oktmo_scope_action_click_handler(kind: str, action: str):
    async def handler() -> None:
        await _run_oktmo_scope_action(kind, action)

    return handler


async def _run_oktmo_key_file_action(action: str) -> None:
    if state["running"]:
        safe_notify(tr("another_running"), "warning")
        return
    values = dict(state.setdefault("field_values", {}))
    try:
        if action == "open":
            result = await run.io_bound(address_service.oktmo_open_key_file, ROOT)
        elif action == "save":
            result = await run.io_bound(address_service.oktmo_save_scope_keys, ROOT, values)
        elif action == "load":
            result = await run.io_bound(address_service.oktmo_load_key_file, ROOT)
        elif action == "clear":
            result = await run.io_bound(address_service.oktmo_clear_key_file, ROOT)
        else:
            return
    except Exception as exc:
        safe_notify(str(exc), "negative")
        return
    message = _oktmo_action_message(action, result)
    add_log(f"OKTMO keys: {message}")
    safe_notify(message, "positive")
    command_tree.refresh()


def oktmo_key_file_action_click_handler(action: str):
    async def handler() -> None:
        await _run_oktmo_key_file_action(action)

    return handler


async def _run_oktmo_reset_keys_action() -> None:
    if state["running"]:
        safe_notify(tr("another_running"), "warning")
        return
    try:
        result = await run.io_bound(address_service.oktmo_reset_project_keys, ROOT)
    except Exception as exc:
        safe_notify(str(exc), "negative")
        return
    apply_oktmo_field_updates(result)
    message = _oktmo_action_message("reset_keys", result)
    add_log(f"OKTMO keys: {message}")
    safe_notify(message, "positive")
    command_tree.refresh()


def oktmo_reset_keys_click_handler():
    async def handler() -> None:
        await _run_oktmo_reset_keys_action()

    return handler


def apply_oktmo_field_updates(result: dict[str, Any]) -> None:
    updates = result.get("field_updates")
    if not isinstance(updates, dict):
        return
    values = state.setdefault("field_values", {})
    for key, value in updates.items():
        values[str(key)] = value


async def _run_oktmo_candidate_action(action: str) -> None:
    if state["running"]:
        safe_notify(tr("another_running"), "warning")
        return
    values = dict(state.setdefault("field_values", {}))
    try:
        if action == "find_candidate":
            state.setdefault("field_values", {})["oktmo_candidate_preview"] = (
                "Идет поиск..." if settings.language == "ru" else "Searching..."
            )
            state.setdefault("field_values", {})["oktmo_candidate_ref"] = ""
            state.setdefault("field_values", {})["oktmo_candidate_options"] = []
            command_tree.refresh()
            result = await run.io_bound(address_service.oktmo_find_settlement_candidates, ROOT, values)
        elif action == "add_candidate":
            result = await run.io_bound(address_service.oktmo_add_candidate_keys, ROOT, values)
        else:
            return
    except Exception as exc:
        safe_notify(str(exc), "negative")
        return
    apply_oktmo_field_updates(result)
    message = _oktmo_action_message(action, result)
    add_log(f"OKTMO candidate: {message}")
    safe_notify(message, "positive")
    command_tree.refresh()


def oktmo_candidate_action_click_handler(action: str):
    async def handler() -> None:
        await _run_oktmo_candidate_action(action)

    return handler


async def _run_oktmo_pin_file_action(action: str) -> None:
    if state["running"]:
        safe_notify(tr("another_running"), "warning")
        return
    try:
        if action == "pins_open":
            result = await run.io_bound(address_service.oktmo_open_pin_file, ROOT)
        elif action == "pins_export":
            result = await run.io_bound(address_service.oktmo_export_pin_file, ROOT)
        elif action == "pins_import":
            result = await run.io_bound(address_service.oktmo_import_pin_file, ROOT)
            clear_oktmo_option_caches()
        elif action == "pins_clear":
            result = await run.io_bound(address_service.oktmo_clear_pin_file, ROOT)
            clear_oktmo_option_caches()
        else:
            return
    except Exception as exc:
        safe_notify(str(exc), "negative")
        return
    message = _oktmo_action_message(action, result)
    add_log(f"OKTMO pins: {message}")
    safe_notify(message, "positive")
    command_tree.refresh()


def oktmo_pin_file_action_click_handler(action: str):
    async def handler() -> None:
        await _run_oktmo_pin_file_action(action)

    return handler


def oktmo_scope_pin_status(kind: str) -> dict[str, Any]:
    try:
        return address_service.oktmo_scope_pin_status(ROOT, dict(state.setdefault("field_values", {})), kind)
    except Exception:
        return {"kind": kind, "value": "", "pinned": False}


def decorate_oktmo_select_option_props(select: Any, field: dict[str, Any]) -> None:
    pinned_by_value: dict[Any, bool] = {}
    for option in field_options(field):
        if isinstance(option, dict):
            value = option_value(option)
            pinned_by_value[value] = str(option.get("pinned") or "").strip().lower() == "true"
    values = list(getattr(select, "_values", []))
    pinned_indexes = [index for index, value in enumerate(values) if pinned_by_value.get(value)]
    pinned_indexes_json = json.dumps(pinned_indexes, ensure_ascii=False)
    select.add_slot(
        "option",
        f"""
        <q-item
          v-bind="props.itemProps"
          dense
          :class="['audion-select-option-item', {pinned_indexes_json}.includes(props.opt.value) ? 'audion-select-option-pinned' : '']"
        >
          <q-item-section avatar class="audion-select-option-pin-cell">
            <q-icon v-if="{pinned_indexes_json}.includes(props.opt.value)" name="push_pin" class="audion-select-option-pin" />
          </q-item-section>
          <q-item-section>
            <q-item-label class="audion-select-option-label">{{{{ props.opt.label || props.opt.value }}}}</q-item-label>
          </q-item-section>
        </q-item>
        """,
    )


def render_oktmo_scope_action_buttons(key: str) -> None:
    kind = OKTMO_SCOPE_SELECT_IDS.get(key)
    if not kind:
        return
    status = oktmo_scope_pin_status(kind)
    has_value = bool(status.get("value"))
    pinned = bool(status.get("pinned"))
    with ui.element("div").classes("audion-scope-action-buttons"):
        pin_classes = "audion-scope-icon-button audion-scope-pin-button"
        if pinned:
            pin_classes += " audion-scope-pin-button-active"
        pin_button = ui.button(
            icon="push_pin",
            on_click=oktmo_scope_action_click_handler(kind, "pin"),
        ).props("dense flat round tabindex=-1").classes(pin_classes)
        if not has_value:
            pin_button.props("disable")
        attach_tooltip(
            pin_button,
            (
                "Значение закреплено. Нажмите ещё раз, чтобы поднять его в начало списка."
                if settings.language == "ru" and pinned
                else "Закрепить значение в списке выбора."
                if settings.language == "ru"
                else "This value is pinned. Click again to move it to the top."
                if pinned
                else "Pin this value in the selector."
            ),
        )
        unpin_button = ui.button(
            icon="remove_circle_outline",
            on_click=oktmo_scope_action_click_handler(kind, "unpin"),
        ).props("dense flat round tabindex=-1").classes(
            "audion-scope-icon-button audion-scope-unpin-button"
        )
        if not has_value or not pinned:
            unpin_button.props("disable")
        attach_tooltip(
            unpin_button,
            "Открепить значение из списка выбора." if settings.language == "ru" else "Unpin this value from the selector.",
        )
        add_button = ui.button(
            icon="add_circle",
            on_click=oktmo_scope_action_click_handler(kind, "add"),
        ).props("dense flat round tabindex=-1").classes(
            "audion-scope-icon-button audion-scope-add-button"
        )
        if not has_value:
            add_button.props("disable")
        attach_tooltip(
            add_button,
            (
                "Добавить выбранный регион или МО в файл ключей поиска. Для МО добавляются формы МО и все НП внутри."
                if settings.language == "ru"
                else "Add selected region or municipality to the search key file. Municipality adds its forms and all localities inside."
            ),
        )


def render_oktmo_key_items(key_items: list[str], *, expanded: bool = False) -> None:
    classes = "audion-oktmo-key-viewer"
    if expanded:
        classes += " audion-oktmo-key-viewer-expanded"
    with ui.element("div").classes(classes):
        if key_items:
            for item in key_items:
                ui.label(item).classes("audion-oktmo-key-item").tooltip(item)
        else:
            ui.label(
                "Ключи пока не загружены." if settings.language == "ru" else "No keys loaded yet."
            ).classes("audion-oktmo-key-empty")


def oktmo_candidate_select_options() -> dict[str, str]:
    raw_options = state.setdefault("field_values", {}).get("oktmo_candidate_options")
    if not isinstance(raw_options, list):
        return {}
    result: dict[str, str] = {}
    for item in raw_options:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or item.get("code") or "").strip()
        label = str(item.get("label_ru" if settings.language == "ru" else "label") or item.get("label") or value).strip()
        if value and label:
            result[value] = label
    return result


def render_oktmo_candidate_search() -> None:
    values = state.setdefault("field_values", {})
    query = str(values.get("oktmo_settlement_query") or "").strip()
    candidate_ref = str(values.get("oktmo_candidate_ref") or "").strip()
    preview = str(values.get("oktmo_candidate_preview") or "").strip()
    selected_municipality = str(values.get("oktmo_selected_municipality") or "").strip()
    selected_settlement = str(values.get("oktmo_selected_settlement") or "").strip()
    selected_code = str(values.get("oktmo_selected_code") or "").strip()
    candidate_options = oktmo_candidate_select_options()
    candidate_value = candidate_ref if candidate_ref in candidate_options else None

    ui.label("Поиск населённого пункта" if settings.language == "ru" else "Settlement search").classes("audion-field-label audion-oktmo-search-title")
    with ui.row().classes("audion-oktmo-search-row items-end gap-2"):
        search_input = ui.input(
            label="Населённый пункт или МО" if settings.language == "ru" else "Settlement or municipality",
            value=query,
            placeholder="Ключи, Мирный, 17-й километр",
            on_change=lambda event: set_field_value("oktmo_settlement_query", event.value),
        ).props("dense outlined").classes("audion-input audion-oktmo-search-input")
        attach_tooltip(
            search_input,
            (
                "Введите НП или муниципальный объект, затем нажмите поиск."
                if settings.language == "ru"
                else "Type a settlement or municipality and search for exact OKTMO rows."
            ),
        )
        search_button = ui.button(
            "Найти кандидатов" if settings.language == "ru" else "Find candidates",
            icon="search",
            on_click=oktmo_candidate_action_click_handler("find_candidate"),
        ).props("dense flat no-wrap").classes("audion-action audion-oktmo-key-button rounded-lg")
        attach_tooltip(search_button, "Найти точные строки ОКТМО" if settings.language == "ru" else "Find exact OKTMO rows")

    with ui.row().classes("audion-oktmo-search-row items-end gap-2"):
        candidate_select = ui.select(
            options=candidate_options,
            label="Точная строка ОКТМО" if settings.language == "ru" else "Exact OKTMO row",
            value=candidate_value,
            on_change=lambda event: (set_field_value("oktmo_candidate_ref", event.value), command_tree.refresh()),
        ).props("dense outlined popup-content-class=audion-select-popup use-input input-debounce=0").classes(
            "audion-select audion-oktmo-candidate-select"
        )
        if not candidate_options:
            candidate_select.props("disable")
        attach_tooltip(
            candidate_select,
            (
                "Выберите найденный населённый пункт или муниципальную строку."
                if settings.language == "ru"
                else "Choose one found settlement or municipality row."
            ),
        )
        add_button = ui.button(
            "Добавить найденные НП" if settings.language == "ru" else "Add found places",
            icon="add_circle",
            on_click=oktmo_candidate_action_click_handler("add_candidate"),
        ).props("dense flat no-wrap").classes("audion-action audion-oktmo-key-button rounded-lg")
        if not candidate_value:
            add_button.props("disable")
        attach_tooltip(
            add_button,
            (
                "Добавить выбранную строку в текущие ключи. Для всего МО используйте + в поле муниципалитета."
                if settings.language == "ru"
                else "Add the selected row to current keys. Use + in the municipality field for a whole municipality."
            ),
        )

    if preview:
        ui.textarea(
            label="Найденные кандидаты" if settings.language == "ru" else "Found candidates",
            value=preview,
        ).props("dense outlined readonly rows=4").classes("audion-oktmo-candidate-preview")

    summary_parts = [
        item
        for item in (
            f"МО: {selected_municipality}" if selected_municipality else "",
            f"НП: {selected_settlement}" if selected_settlement else "",
            f"ОКТМО: {selected_code}" if selected_code else "",
        )
        if item
    ]
    if summary_parts:
        ui.label(" | ".join(summary_parts)).classes("audion-field-hint audion-oktmo-selected-summary")


def render_oktmo_key_toolbar(field: dict[str, Any], label: str, hint: str, tooltip_text: str) -> None:
    attach_tooltip(ui.label(label).classes("audion-field-label"), tooltip_text)
    summary = address_service.oktmo_load_key_file(ROOT)
    pin_summary = address_service.oktmo_pin_file_status(ROOT)
    buttons = (
        ("open", "folder_open", "Открыть" if settings.language == "ru" else "Open"),
        ("save", "save", "Сохранить" if settings.language == "ru" else "Save"),
        ("load", "upload_file", "Загрузить" if settings.language == "ru" else "Load"),
        ("clear", "delete_sweep", "Очистить" if settings.language == "ru" else "Clear"),
    )
    with ui.row().classes("audion-oktmo-key-toolbar items-center gap-2"):
        for action, icon, text in buttons:
            button = ui.button(
                text,
                icon=icon,
                on_click=oktmo_key_file_action_click_handler(action),
            ).props("dense flat no-wrap").classes("audion-action audion-oktmo-key-button rounded-lg")
            attach_tooltip(button, f"{text}: {field_hint(field) or label}")
    render_oktmo_candidate_search()
    summary_text = (
        f"{summary.get('keys', 0)} ключей: {display_path(summary.get('path'))}"
        if settings.language == "ru"
        else f"{summary.get('keys', 0)} keys: {display_path(summary.get('path'))}"
    )
    key_items = [str(item) for item in (summary.get("items") or []) if str(item).strip()]
    key_text = "\n".join(key_items)
    with ui.dialog() as key_dialog:
        with ui.card().classes("audion-dialog audion-oktmo-key-dialog-card rounded-lg p-3"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(
                    f"Ключи ОКТМО ({len(key_items)})" if settings.language == "ru" else f"OKTMO keys ({len(key_items)})"
                ).classes("text-sm font-semibold text-gray-300 min-w-0 flex-1")
                copy_expanded = ui.button(
                    icon="content_copy",
                    on_click=lambda text=key_text: copy_text_to_clipboard(
                        text,
                        "Ключи ОКТМО скопированы." if settings.language == "ru" else "OKTMO keys copied.",
                    ),
                ).props("dense flat round").classes("audion-action audion-log-icon-button")
                if not key_items:
                    copy_expanded.props("disable")
                attach_tooltip(copy_expanded, "Скопировать ключи" if settings.language == "ru" else "Copy keys")
                close_button = ui.button(tr("close"), on_click=key_dialog.close).props("dense flat").classes("audion-action rounded-lg")
                attach_tooltip(close_button, tr("close"))
            ui.label(summary_text).classes("audion-field-hint audion-oktmo-key-summary")
            render_oktmo_key_items(key_items, expanded=True)
    with ui.element("div").classes("audion-oktmo-key-field"):
        with ui.row().classes("audion-oktmo-key-field-header w-full items-center gap-2"):
            ui.label(
                f"Текущие ключи ({len(key_items)})" if settings.language == "ru" else f"Current keys ({len(key_items)})"
            ).classes("audion-field-label min-w-0 flex-1")
            copy_button = ui.button(
                icon="content_copy",
                on_click=lambda text=key_text: copy_text_to_clipboard(
                    text,
                    "Ключи ОКТМО скопированы." if settings.language == "ru" else "OKTMO keys copied.",
                ),
            ).props("dense flat round").classes("audion-action audion-oktmo-key-icon-button")
            if not key_items:
                copy_button.props("disable")
            attach_tooltip(copy_button, "Скопировать ключи" if settings.language == "ru" else "Copy keys")
            expand_button = ui.button(
                icon="open_in_full",
                on_click=key_dialog.open,
            ).props("dense flat round").classes("audion-action audion-oktmo-key-icon-button")
            attach_tooltip(expand_button, tr("expand"))
        ui.label(summary_text).classes("audion-field-hint audion-oktmo-key-summary")
        render_oktmo_key_items(key_items)
    ui.label("Пины ОКТМО" if settings.language == "ru" else "OKTMO pins").classes("audion-field-label audion-oktmo-pin-toolbar-title")
    pin_buttons = (
        ("pins_open", "folder_open", "Открыть пины" if settings.language == "ru" else "Open pins"),
        ("pins_export", "save", "Экспорт пинов" if settings.language == "ru" else "Export pins"),
        ("pins_import", "upload_file", "Импорт пинов" if settings.language == "ru" else "Import pins"),
        ("pins_clear", "delete_sweep", "Очистить пины ОКТМО" if settings.language == "ru" else "Clear OKTMO pins"),
    )
    with ui.row().classes("audion-oktmo-key-toolbar audion-oktmo-pin-toolbar items-center gap-2"):
        for action, icon, text in pin_buttons:
            button = ui.button(
                text,
                icon=icon,
                on_click=oktmo_pin_file_action_click_handler(action),
            ).props("dense flat no-wrap").classes("audion-action audion-oktmo-key-button rounded-lg")
            attach_tooltip(button, text)
    pin_summary_text = (
        f"Пинов: регионов {pin_summary.get('regions', 0)}, МО {pin_summary.get('municipalities', 0)}: {display_path(pin_summary.get('path'))}"
        if settings.language == "ru"
        else f"Pins: regions {pin_summary.get('regions', 0)}, municipalities {pin_summary.get('municipalities', 0)}: {display_path(pin_summary.get('path'))}"
    )
    ui.label(pin_summary_text).classes("audion-field-hint audion-oktmo-key-summary")
    if hint:
        ui.label(hint).classes("audion-field-hint")


def apply_preset(preset: dict[str, Any]) -> None:
    values = preset.get("values", {})
    if not isinstance(values, dict):
        return
    field_values = state.setdefault("field_values", {})
    for key, value in values.items():
        field_values[str(key)] = value
    command_tree.refresh()


def preset_label(preset: dict[str, Any]) -> str:
    if settings.language == "ru" and preset.get("label_ru"):
        return str(preset["label_ru"])
    return str(preset.get("label") or preset.get("title") or preset.get("id") or "Preset")


def preset_click_handler(preset: dict[str, Any]):
    def handler() -> None:
        apply_preset(preset)

    return handler


def field_dependency_ids(field: dict[str, Any]) -> list[str]:
    raw = field.get("depends_on", [])
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def field_dependencies_met(field: dict[str, Any]) -> bool:
    values = state.setdefault("field_values", {})
    for dependency in field_dependency_ids(field):
        value = values.get(dependency)
        if str(value or "").strip().lower() in {"", "0", "false", "none", "null"}:
            return False
    show_when = field.get("show_when")
    if isinstance(show_when, dict):
        for dependency, expected in show_when.items():
            actual = values.get(str(dependency))
            if isinstance(expected, (list, tuple, set)):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
    return True


SLOT_PREVIEW_VALUES = {
    "postal_index": "625000",
    "federal_district": "Уральский федеральный округ",
    "parent_subject": "Российская Федерация",
    "subject": "Тюменская область",
    "autonomous_okrug": "Ханты-Мансийский автономный округ — Югра",
    "municipality": "Тюменский муниципальный округ",
    "locality": "г. Тюмень",
    "territory": "территория СНТ Берёзка",
    "microdistrict": "мкр. Центральный",
    "street": "ул. Ленина",
    "house": "д. 10",
    "building": "корп. 2",
    "structure": "стр. 1",
    "apartment": "кв. 15",
    "room": "комн. 3",
}


def slot_preview_value(field: dict[str, Any]) -> str:
    enabled = state.setdefault("field_values", {}).get("enabled_slots")
    if not isinstance(enabled, list):
        return str(field_default(field) or "")
    order = state.setdefault("field_values", {}).get("slot_order")
    keys = [key for key in SLOT_PREVIEW_VALUES if key in enabled]
    if isinstance(order, dict):
        keys.sort(key=lambda key: (int(order.get(key) or 999), list(SLOT_PREVIEW_VALUES).index(key)))
    return " · ".join(SLOT_PREVIEW_VALUES[key] for key in keys)


def dynamic_option_cache_key(field: dict[str, Any]) -> Any:
    source = dynamic_option_source(field)
    if not source:
        return ""
    values = state.setdefault("field_values", {})
    signature: list[tuple[str, str]] = []
    for dependency in field_dependency_ids(field):
        signature.append((dependency, str(values.get(dependency) or "")))
    if source in OKTMO_OPTION_SOURCES:
        signature.append(("oktmo_data_dir", str(values.get("oktmo_data_dir") or "")))
    return (source, tuple(signature)) if signature else source


def load_dynamic_options(field: dict[str, Any]) -> list[Any]:
    source = dynamic_option_source(field)
    if not source:
        return []

    cache_seconds = float(field.get("cache_seconds", 45) or 0)
    now = time.monotonic()
    cache_key = dynamic_option_cache_key(field)
    cached = dynamic_option_cache.get(cache_key)
    if cached and cache_seconds > 0 and now - cached[0] < cache_seconds:
        return cached[1]

    try:
        if ":" not in source:
            raise RuntimeError(f"Dynamic option source must use module:function syntax: {source}")
        module_name, function_name = source.split(":", 1)
        module = importlib.import_module(module_name)
        provider = getattr(module, function_name)
        try:
            options = provider(ROOT, dict(state.setdefault("field_values", {})), field)
        except TypeError:
            try:
                options = provider(ROOT)
            except TypeError:
                options = provider()
        if not isinstance(options, list):
            raise RuntimeError(f"Dynamic option source returned {type(options).__name__}, expected list.")
    except Exception as exc:
        message = f"Option source failed: {exc.__class__.__name__}: {exc}"
        options = [{"value": "", "label": message, "label_ru": message}]

    dynamic_option_cache[cache_key] = (now, options)
    return options


def field_options(field: dict[str, Any]) -> list[Any]:
    dynamic_options = load_dynamic_options(field)
    if dynamic_options:
        return dynamic_options
    options = field.get("options", [])
    return options if isinstance(options, list) else []


def select_options(field: dict[str, Any]) -> dict[Any, str] | list[Any]:
    options = field_options(field)
    if all(isinstance(option, dict) for option in options):
        result: dict[Any, str] = {}
        for option in options:
            value = option.get("value", option.get("id", ""))
            if settings.language == "ru" and option.get("label_ru"):
                label = str(option["label_ru"])
            else:
                label = str(option.get("label") or option.get("title") or value)
            result[value] = label
        return result
    return options


def option_value(option: Any) -> Any:
    if isinstance(option, dict):
        return option.get("value", option.get("id", option.get("label", "")))
    return option


def option_label(option: Any) -> str:
    if not isinstance(option, dict):
        return str(option)
    language = settings.language
    if language == "ru" and option.get("label_ru"):
        return str(option["label_ru"])
    return str(option.get("label") or option.get("title") or option_value(option))


SLOT_SHORT_LABELS_RU = {
    "postal_index": "Индекс",
    "federal_district": "ФО",
    "parent_subject": "Рег.-род.",
    "subject": "Субъект",
    "autonomous_okrug": "АО",
    "municipality": "МО",
    "locality": "НП",
    "territory": "Терр.",
    "microdistrict": "Мкр/кв.",
    "street": "Улица",
    "house": "Дом",
    "premise": "Пом.",
    "oktmo_code": "ОКТМО",
    "oktmo_name": "Имя ОКТМО",
    "house_base": "№ дома",
    "house_mods": "Мод. дома",
    "house_modifiers": "Корп./стр.",
    "street_numbers": "№ улицы",
    "territory_key": "Ключ терр.",
    "match_key": "Ключ",
}
SLOT_SHORT_LABELS_EN = {
    "postal_index": "Index",
    "federal_district": "Fed.",
    "parent_subject": "Parent",
    "subject": "Subject",
    "autonomous_okrug": "AO",
    "municipality": "Mun.",
    "locality": "Locality",
    "territory": "Terr.",
    "microdistrict": "Mkr/Qtr",
    "street": "Street",
    "house": "House",
    "premise": "Prem.",
    "oktmo_code": "OKTMO",
    "oktmo_name": "OKTMO name",
    "house_base": "House no.",
    "house_mods": "Mods",
    "house_modifiers": "Bldg cols",
    "street_numbers": "St. nums",
    "territory_key": "Terr. key",
    "match_key": "Key",
}


def option_short_label(option: Any) -> str:
    if not isinstance(option, dict):
        return str(option)
    language = settings.language
    if language == "ru" and option.get("short_label_ru"):
        return str(option["short_label_ru"])
    if option.get("short_label"):
        return str(option["short_label"])
    slot_key = str(option_value(option))
    if language == "ru" and slot_key in SLOT_SHORT_LABELS_RU:
        return SLOT_SHORT_LABELS_RU[slot_key]
    if slot_key in SLOT_SHORT_LABELS_EN:
        return SLOT_SHORT_LABELS_EN[slot_key]
    return option_label(option)


def option_tooltip(option: Any) -> str:
    if not isinstance(option, dict):
        return str(option)
    language = settings.language
    tooltip = option.get("tooltip_ru") if language == "ru" else option.get("tooltip")
    if tooltip:
        return str(tooltip)
    hint = option.get("hint_ru") if language == "ru" else option.get("hint")
    if hint:
        return str(hint)
    label = option_label(option)
    short = option_short_label(option)
    return label if label != short else ""


def checkbox_options(field: dict[str, Any]) -> list[tuple[Any, str, str, str]]:
    options = field_options(field)
    return [
        (option_value(option), option_short_label(option), option_label(option), option_tooltip(option))
        for option in options
    ]


def slot_order_options(field: dict[str, Any]) -> list[tuple[str, str, str, str, int]]:
    result: list[tuple[str, str, str, str, int]] = []
    for index, option in enumerate(field_options(field), start=1):
        value = str(option_value(option)).strip()
        if not value:
            continue
        try:
            default_order = int(option.get("default_order", index)) if isinstance(option, dict) else index
        except (TypeError, ValueError):
            default_order = index
        result.append((value, option_short_label(option), option_label(option), option_tooltip(option), max(1, default_order)))
    return result


def slot_order_default(field: dict[str, Any]) -> dict[str, int]:
    configured = field.get("default", {})
    if isinstance(configured, dict):
        result: dict[str, int] = {}
        for key, value in configured.items():
            try:
                result[str(key)] = max(1, int(value))
            except (TypeError, ValueError):
                continue
        if result:
            return result
    return {slot: default_order for slot, _short, _label, _tooltip, default_order in slot_order_options(field)}


def normalize_slot_order_payload(field: dict[str, Any], payload: Any) -> dict[str, int]:
    options = slot_order_options(field)
    if not options:
        return {}
    max_order = len(options)
    defaults = {slot: default_order for slot, _short, _label, _tooltip, default_order in options}
    raw_payload = payload if isinstance(payload, dict) else {}
    result: dict[str, int] = {}
    used: set[int] = set()

    def coerce_position(raw: Any, fallback: int) -> int:
        try:
            position = int(raw)
        except (TypeError, ValueError):
            position = fallback
        return min(max(1, position), max_order)

    def nearest_free(preferred: int) -> int:
        if preferred not in used:
            return preferred
        for position in range(preferred + 1, max_order + 1):
            if position not in used:
                return position
        for position in range(preferred - 1, 0, -1):
            if position not in used:
                return position
        return preferred

    for slot, _short, _label, _tooltip, default_order in options:
        preferred = coerce_position(raw_payload.get(slot, defaults.get(slot, default_order)), default_order)
        position = nearest_free(preferred)
        result[slot] = position
        used.add(position)
    return result


def enabled_slots_for_order(options: list[tuple[str, str, str, str, int]]) -> set[str]:
    option_slots = {slot for slot, _short, _label, _tooltip, _default_order in options}
    raw_enabled = state.setdefault("field_values", {}).get("enabled_slots")
    if isinstance(raw_enabled, (list, tuple, set)):
        selected = {str(item) for item in raw_enabled}
        return option_slots & selected
    return set(option_slots)


def active_slot_order(
    payload: dict[str, int],
    options: list[tuple[str, str, str, str, int]],
    enabled_slots: set[str],
) -> list[str]:
    option_index = {slot: index for index, (slot, _short, _label, _tooltip, _default_order) in enumerate(options)}
    return sorted(
        (slot for slot in option_index if slot in enabled_slots),
        key=lambda slot: (payload.get(slot, len(options) + option_index[slot] + 1), option_index[slot]),
    )


def slot_order_display_positions(
    payload: dict[str, int],
    options: list[tuple[str, str, str, str, int]],
    enabled_slots: set[str],
) -> dict[str, int]:
    positions = {slot: 0 for slot, _short, _label, _tooltip, _default_order in options}
    for display_position, slot in enumerate(active_slot_order(payload, options, enabled_slots), start=1):
        positions[slot] = display_position
    return positions


def is_checkbox_group(field: dict[str, Any]) -> bool:
    kind = str(field.get("type", field.get("kind", "text"))).lower()
    return kind in {"checkboxes", "multi_checkbox", "multicheckbox", "multi-select", "multiselect"}


def is_workbench_route_field(field: dict[str, Any]) -> bool:
    key = field_id(field).lower()
    kind = str(field.get("type", field.get("kind", ""))).lower()
    if kind in {"xlsx_file_picker", "xlsx-file-picker", "file_picker", "file-picker"}:
        return False
    label_text = " ".join(
        str(field.get(item) or "").lower()
        for item in ("label", "label_ru", "title", "hint", "hint_ru", "placeholder")
    )
    haystack = f"{key} {label_text}"
    route_markers = (
        "input",
        "output",
        "source",
        "destination",
        "target",
        "src",
        "dst",
        "исход",
        "источник",
        "вход",
        "выход",
        "цель",
        "результ",
        "приём",
        "прием",
    )
    path_markers = ("path", "folder", "directory", "dir", "пап", "каталог", "путь")
    return kind in {"path", "folder", "directory"} or (
        any(marker in haystack for marker in route_markers)
        and any(marker in haystack for marker in path_markers)
    )


def command_visible_fields(fields: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        field
        for field in fields
        if not is_workbench_route_field(field)
        and not is_gui_hidden_field(field)
        and field_dependencies_met(field)
    ]


def field_container_classes(field: dict[str, Any]) -> str:
    span = str(field.get("span") or field.get("width") or "").lower()
    kind = str(field.get("type", field.get("kind", "text"))).lower()
    key = field_id(field)
    if span in {"full", "wide", "100%", "1/-1"}:
        return "audion-field audion-field-wide"
    if key in OKTMO_FULL_WIDTH_FIELD_IDS:
        return "audion-field audion-field-wide audion-field-oktmo-scope"
    if key in OKTMO_SCOPE_SELECT_IDS:
        return "audion-field audion-field-wide audion-field-oktmo-scope"
    if kind in {"select", "choice", "format"}:
        return "audion-field audion-field-select"
    if kind in {"textarea", "multiline", "path", "file", "folder", "xlsx_file_picker", "xlsx-file-picker", "file_picker", "file-picker"}:
        return "audion-field audion-field-wide"
    if kind in {"preset_buttons", "presets", "profile_buttons", "profiles"}:
        return "audion-field audion-field-wide"
    if kind in {"radio", "radiobuttons", "radio-buttons"}:
        return "audion-field audion-field-wide"
    if kind in {"slot_preview", "slot-preview", "readonly_badge", "readonly-badge", "slot_order", "slot-order", "slotorder"}:
        return "audion-field audion-field-wide"
    if kind in UI_ONLY_FIELD_TYPES:
        return "audion-field audion-field-wide"
    if kind in {"checkboxes", "multi_checkbox", "multicheckbox", "multi-select", "multiselect"}:
        return "audion-field audion-field-wide"
    return "audion-field"


def render_field(field: dict[str, Any]) -> None:
    key = field_id(field)
    if not key:
        return
    kind = str(field.get("type", field.get("kind", "text"))).lower()
    label = field_label(field)
    value = current_field_value(field)
    hint = field_hint(field)
    tooltip_text = field_tooltip_text(label, hint)

    with ui.element("div").classes(field_container_classes(field)):
        if kind in {"slot_preview", "slot-preview", "readonly_badge", "readonly-badge"}:
            attach_tooltip(ui.label(label).classes("audion-field-label"), tooltip_text)
            preview_value = slot_preview_value(field) if kind in {"slot_preview", "slot-preview"} else str(value or "")
            attach_tooltip(ui.label(preview_value).classes("audion-slot-preview-badge"), tooltip_text)
            if hint:
                ui.label(hint).classes("audion-field-hint")
            return

        if kind in {"slot_order", "slot-order", "slotorder"}:
            payload = value if isinstance(value, dict) else slot_order_default(field)
            normalized_payload = normalize_slot_order_payload(field, payload)
            set_field_value(key, normalized_payload)

            options = slot_order_options(field)
            enabled_order_slots = enabled_slots_for_order(options)
            display_positions = slot_order_display_positions(normalized_payload, options, enabled_order_slots)
            max_order = max(len(enabled_order_slots), 1)
            number_options = {index: str(index) for index in range(1, max_order + 1)}
            disabled_number_options = {0: "—"}
            select_controls: dict[str, Any] = {}

            def update_slot_order_controls(next_payload: dict[str, int]) -> None:
                next_display_positions = slot_order_display_positions(next_payload, options, enabled_order_slots)
                for control_slot, control in select_controls.items():
                    next_value = next_display_positions.get(control_slot, 0)
                    if next_value is not None and getattr(control, "value", None) != next_value:
                        control.set_value(next_value)

            def sync_slot_order(slot_key: str, event: Any) -> None:
                if slot_key not in enabled_order_slots:
                    return
                current = state.setdefault("field_values", {}).get(key, normalized_payload)
                next_payload = normalize_slot_order_payload(field, current)
                try:
                    new_display_position = min(max(1, int(event.value)), max_order)
                except (TypeError, ValueError):
                    return
                ordered_active_slots = active_slot_order(next_payload, options, enabled_order_slots)
                if not ordered_active_slots or new_display_position > len(ordered_active_slots):
                    return
                displaced_slot = ordered_active_slots[new_display_position - 1]
                if displaced_slot == slot_key:
                    return
                old_position = next_payload.get(slot_key)
                displaced_position = next_payload.get(displaced_slot)
                if old_position is None or displaced_position is None:
                    return
                next_payload[slot_key] = displaced_position
                next_payload[displaced_slot] = old_position
                next_payload = normalize_slot_order_payload(field, next_payload)
                set_field_value(key, next_payload)
                update_slot_order_controls(next_payload)

            attach_tooltip(ui.label(label).classes("audion-field-label"), tooltip_text)
            with ui.element("div").classes("audion-slot-order-grid"):
                for slot, option_text, full_text, tooltip_text, default_order in options:
                    is_enabled = slot in enabled_order_slots
                    current_position = display_positions.get(slot, 0)
                    item_classes = "audion-slot-order-item"
                    if not is_enabled:
                        item_classes += " audion-slot-order-item-disabled"
                    with ui.element("div").classes(item_classes):
                        label_element = ui.label(option_text).classes("audion-slot-order-label")
                        tooltip_body = tooltip_text or full_text
                        if not is_enabled:
                            disabled_note = (
                                "Слот выключен чекбоксом и не участвует в адресной строке."
                                if settings.language == "ru"
                                else "This slot is unchecked and is ignored in the address line."
                            )
                            tooltip_body = f"{tooltip_body}\n{disabled_note}" if tooltip_body else disabled_note
                        if tooltip_body:
                            label_element.tooltip(tooltip_body)
                        select = ui.select(
                            options=number_options if is_enabled else disabled_number_options,
                            value=current_position,
                            on_change=lambda event, item_slot=slot: sync_slot_order(item_slot, event),
                        ).props("dense outlined options-dense popup-content-class=audion-select-popup").classes(
                            "audion-select audion-slot-order-select"
                        )
                        if not is_enabled:
                            select.props("disable")
                        if tooltip_body:
                            select.tooltip(tooltip_body)
                        select_controls[slot] = select
            if hint:
                ui.label(hint).classes("audion-field-hint")
            return

        if kind in {"preset_buttons", "presets", "profile_buttons", "profiles"}:
            presets = field.get("presets", field.get("options", []))
            if not isinstance(presets, list):
                presets = []
            attach_tooltip(ui.label(label).classes("audion-field-label"), tooltip_text)
            with ui.row().classes("audion-choice-row"):
                for preset in presets:
                    if not isinstance(preset, dict):
                        continue
                    preset_button = ui.button(
                        preset_label(preset),
                        on_click=preset_click_handler(preset),
                    ).props("dense flat no-wrap").classes("audion-action rounded-lg")
                    attach_tooltip(preset_button, preset.get("hint_ru" if settings.language == "ru" else "hint") or preset_label(preset))
            if hint:
                ui.label(hint).classes("audion-field-hint")
            return

        if kind in UI_ONLY_FIELD_TYPES:
            render_oktmo_key_toolbar(field, label, hint, tooltip_text)
            return

        if kind in {"select", "choice", "format"}:
            if key in OKTMO_SCOPE_SELECT_IDS:
                with ui.element("div").classes("audion-oktmo-scope-select-row"):
                    select = ui.select(
                        options=select_options(field),
                        label=label,
                        value=value,
                        on_change=lambda event, item_key=key, item_field=field: set_field_value_from_event(
                            item_key,
                            item_field,
                            event.value,
                        ),
                    )
                    props = "dense outlined popup-content-class=audion-select-popup"
                    if bool(field.get("searchable", field.get("with_input", False))):
                        props += " use-input input-debounce=0"
                    select_classes = "audion-select w-full audion-oktmo-scope-select audion-oktmo-scope-select-control"
                    if oktmo_scope_pin_status(OKTMO_SCOPE_SELECT_IDS[key]).get("pinned"):
                        select_classes += " audion-select-pinned"
                    select.props(props).classes(select_classes)
                    attach_tooltip(select, tooltip_text)
                    decorate_oktmo_select_option_props(select, field)
                    render_oktmo_scope_action_buttons(key)
                render_oktmo_data_status(field)
                if dynamic_option_source(field):
                    refresh_button = ui.button(
                        tr("refresh_options"),
                        on_click=refresh_options_click_handler(field),
                    ).props("dense flat no-wrap").classes("audion-action mt-1 rounded-lg")
                    attach_tooltip(refresh_button, tr("refresh_options"))
                if hint:
                    ui.label(hint).classes("audion-field-hint")
                return

            select = ui.select(
                options=select_options(field),
                label=label,
                value=value,
                on_change=lambda event, item_key=key, item_field=field: set_field_value_from_event(
                    item_key,
                    item_field,
                    event.value,
                ),
            )
            props = "dense outlined popup-content-class=audion-select-popup"
            if bool(field.get("searchable", field.get("with_input", False))):
                props += " use-input input-debounce=0"
            select_classes = "audion-select w-full"
            if key in OKTMO_SCOPE_SELECT_IDS:
                select_classes += " audion-oktmo-scope-select"
                if oktmo_scope_pin_status(OKTMO_SCOPE_SELECT_IDS[key]).get("pinned"):
                    select_classes += " audion-select-pinned"
            select.props(props).classes(select_classes)
            attach_tooltip(select, tooltip_text)
            if dynamic_option_source(field):
                refresh_button = ui.button(
                    tr("refresh_options"),
                    on_click=refresh_options_click_handler(field),
                ).props("dense flat no-wrap").classes("audion-action mt-1 rounded-lg")
                attach_tooltip(refresh_button, tr("refresh_options"))
            if hint:
                ui.label(hint).classes("audion-field-hint")
            return

        if kind in {"radio", "radiobuttons", "radio-buttons"}:
            attach_tooltip(ui.label(label).classes("audion-field-label"), tooltip_text)
            radio = ui.radio(
                options=select_options(field),
                value=value,
                on_change=lambda event, item_key=key, item_field=field: set_field_value_from_event(
                    item_key,
                    item_field,
                    event.value,
                ),
            ).props("dense inline").classes("audion-choice-row")
            attach_tooltip(radio, tooltip_text)
            if dynamic_option_source(field):
                refresh_button = ui.button(
                    tr("refresh_options"),
                    on_click=refresh_options_click_handler(field),
                ).props("dense flat no-wrap").classes("audion-action mt-1 rounded-lg")
                attach_tooltip(refresh_button, tr("refresh_options"))
            if hint:
                ui.label(hint).classes("audion-field-hint")
            return

        if kind in {"number", "int", "integer", "float"}:
            number_input = ui.number(
                label=label,
                value=value if value != "" else None,
                min=field.get("min"),
                max=field.get("max"),
                step=field.get("step", 1),
                on_change=lambda event, item_key=key: set_field_value(item_key, event.value),
            ).props("dense outlined").classes("audion-number w-full")
            attach_tooltip(number_input, tooltip_text)
            with number_input.add_slot("append"):
                with ui.element("div").classes("audion-number-spinner"):
                    up_button = ui.button(
                        icon="keyboard_arrow_up",
                        on_click=lambda item_key=key, item_field=field, control=number_input: spin_number_field(item_key, item_field, control, 1),
                    ).props("dense flat round tabindex=-1").classes("audion-number-spin-button")
                    attach_tooltip(up_button, tooltip_text)
                    down_button = ui.button(
                        icon="keyboard_arrow_down",
                        on_click=lambda item_key=key, item_field=field, control=number_input: spin_number_field(item_key, item_field, control, -1),
                    ).props("dense flat round tabindex=-1").classes("audion-number-spin-button")
                    attach_tooltip(down_button, tooltip_text)
            if hint:
                ui.label(hint).classes("audion-field-hint")
            return

        if kind in {"xlsx_file_picker", "xlsx-file-picker", "file_picker", "file-picker"}:
            async def pick_xlsx_handler(control: Any) -> None:
                if state["running"]:
                    safe_notify(tr("another_running"), "warning")
                    return
                try:
                    selected = await run.io_bound(pick_xlsx_file)
                except Exception as exc:
                    safe_notify(str(exc), "negative")
                    return
                if not selected:
                    add_log(tr("picker_cancelled"))
                    return
                selected_text = str(selected[0])
                set_field_value(key, selected_text)
                control.value = selected_text
                dynamic_option_cache.clear()
                safe_notify(tr("target_selected"), "positive")
                command_tree.refresh()

            attach_tooltip(ui.label(label).classes("audion-field-label"), tooltip_text)
            with ui.row().classes("items-center gap-2 w-full no-wrap"):
                text_input = ui.input(
                    value=str(value) if value is not None else "",
                    placeholder=str(field.get("placeholder", "")),
                    on_change=lambda event, item_key=key, item_field=field: set_field_value_from_event(item_key, item_field, event.value),
                ).props("dense outlined").classes("flex-1")
                attach_tooltip(text_input, tooltip_text)
                async def pick_xlsx_click(control: Any = text_input) -> None:
                    await pick_xlsx_handler(control)

                picker_button = ui.button(
                    icon="attach_file",
                    on_click=pick_xlsx_click,
                ).props("dense flat no-wrap").classes("audion-action audion-file-picker-button")
                attach_tooltip(picker_button, tooltip_text)
            if hint:
                ui.label(hint).classes("audion-field-hint")
            return

        if kind in {"checkbox", "bool", "boolean", "toggle"}:
            checkbox = ui.checkbox(
                label,
                value=bool(value),
                on_change=lambda event, item_key=key: set_field_value(item_key, bool(event.value)),
            ).props("dense").classes("audion-single-checkbox")
            attach_tooltip(checkbox, tooltip_text)
            if hint:
                ui.label(hint).classes("audion-field-hint")
            return

        if is_checkbox_group(field):
            selected = set(value if isinstance(value, list) else [])
            controls: dict[Any, Any] = {}

            def sync_checkboxes(item_key: str = key, refresh_layout: bool = False) -> None:
                set_field_value(
                    item_key,
                    [option_key for option_key, checkbox in controls.items() if bool(checkbox.value)],
                )
                if refresh_layout and item_key == "enabled_slots":
                    command_tree.refresh()

            attach_tooltip(ui.label(label).classes("audion-field-label"), tooltip_text)
            if dynamic_option_source(field):
                refresh_button = ui.button(
                    tr("refresh_options"),
                    on_click=refresh_options_click_handler(field),
                ).props("dense flat no-wrap").classes("audion-action mb-1 rounded-lg")
                attach_tooltip(refresh_button, tr("refresh_options"))
            with ui.element("div").classes("audion-checkbox-grid"):
                for option_key, option_text, full_text, tooltip_text in checkbox_options(field):
                    tooltip_body = tooltip_text or full_text
                    with ui.element("div").classes("audion-checkbox-grid-item"):
                        checkbox = ui.checkbox(
                            option_text,
                            value=option_key in selected,
                            on_change=lambda _event: sync_checkboxes(refresh_layout=True),
                        ).props("dense")
                        if tooltip_body:
                            checkbox.tooltip(tooltip_body)
                        controls[option_key] = checkbox
            if hint:
                ui.label(hint).classes("audion-field-hint")
            sync_checkboxes()
            return

        text_input = ui.input(
            label=label,
            value=str(value) if value is not None else "",
            placeholder=str(field.get("placeholder", "")),
            on_change=lambda event, item_key=key: set_field_value(item_key, event.value),
        ).props("dense outlined").classes("w-full")
        attach_tooltip(text_input, tooltip_text)
        if hint:
            ui.label(hint).classes("audion-field-hint")


def operation_from_pending_command(node: CommandNode) -> Operation:
    parameters = dict(node.parameters)
    values = state.setdefault("field_values", {})
    for field in command_visible_fields(node.fields):
        if is_ui_only_field(field):
            continue
        key = field_id(field)
        if key:
            parameters[key] = values.get(key, field_default(field))
    parameters = apply_command_parameter_guards(node, parameters)
    return node.to_operation(parameters)


def validate_pending_fields(node: CommandNode) -> bool:
    values = state.setdefault("field_values", {})
    for field in command_visible_fields(node.fields):
        if not is_checkbox_group(field):
            continue
        min_selected = int(field.get("min_selected", 0) or 0)
        if min_selected <= 0:
            continue
        key = field_id(field)
        selected = values.get(key, field_default(field))
        if not isinstance(selected, list) or len(selected) < min_selected:
            safe_notify(tr("select_required", field=field_label(field)), "warning")
            return False
    return True


async def run_pending_command(node: CommandNode) -> None:
    if validate_pending_fields(node):
        await start_operation(operation_from_pending_command(node))


def run_pending_click_handler(node: CommandNode):
    async def handler() -> None:
        await run_pending_command(node)

    return handler


def field_signature(fields: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    return tuple(field_id(field) for field in fields if field_id(field))


def can_inline_child_actions(parent: CommandNode | None, children: list[CommandNode]) -> bool:
    if parent is None or not command_visible_fields(parent.fields) or not children:
        return False
    parent_signature = field_signature(tuple(command_visible_fields(parent.fields)))
    if not parent_signature:
        return False
    return all(not child.children and field_signature(tuple(command_visible_fields(child.fields))) == parent_signature for child in children)


def render_inline_child_action(node: CommandNode) -> None:
    button = ui.button(
        node.display_title(settings.language),
        on_click=run_pending_click_handler(node),
    ).props("dense flat no-wrap").classes("audion-action rounded-lg")
    attach_tooltip(button, node.display_description(settings.language) or node.display_title(settings.language))


ADVANCED_FIELD_SUFFIXES = (
    "_model_override",
    "_chunk_tokens",
    "_overlap_tokens",
    "_min_chunks",
    "_max_retries",
    "_max_output_tokens",
    "_timeout_sec",
    "_resume",
)
ALIGNMENT_MODE_FIELD_ID = "alignment_mode"
ALIGNMENT_NORMALIZATION_SECTION_ID = "alignment_normalization"
ALIGNMENT_NORMALIZATION_FIELD_IDS = {
    "normalize_before_match",
    "normalize_after_match",
    "collect_before_match",
    "collect_whole_document",
    "use_oktmo",
    "oktmo_scope_enabled",
    "oktmo_scope_region",
    "oktmo_scope_municipality",
    "oktmo_key_toolbar",
    "city",
    "subject_ter_hint",
    "municipality_hint",
    "oktmo_data_dir",
}


def is_advanced_field(field: dict[str, Any]) -> bool:
    if bool(field.get("advanced", False)):
        return True
    priority = str(field.get("priority") or field.get("section") or "").strip().lower()
    if priority in {"advanced", "expert", "rare"}:
        return True
    key = field_id(field)
    return any(key.endswith(suffix) for suffix in ADVANCED_FIELD_SUFFIXES)


def split_primary_advanced_fields(fields: tuple[dict[str, Any], ...]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    primary: list[dict[str, Any]] = []
    advanced: list[dict[str, Any]] = []
    for field in fields:
        if is_advanced_field(field):
            advanced.append(field)
        else:
            primary.append(field)
    return primary, advanced


def field_section_id(field: dict[str, Any]) -> str:
    key = field_id(field)
    kind = str(field.get("type", field.get("kind", "text"))).lower()
    section = str(field.get("section") or "").strip().lower()
    explicit = str(field.get("group") or field.get("ui_group") or field.get("section_group") or "").strip().lower()
    if not explicit and section and section not in {"advanced", "expert", "rare"}:
        explicit = section
    if explicit:
        return explicit
    if kind in {"profile_select", "profile-select", "preset_select", "preset-select", "preset_buttons", "presets", "profile_buttons", "profiles"}:
        return "preset"
    if any(part in key for part in ("ground_truth", "target_column", "column")):
        return "columns"
    if key in {"overwrite", "dry_run", "limit_first_file", "test_first_file"} or key.endswith(("_dry_run", "_overwrite")):
        return "run"
    if any(part in key for part in ("source", "input", "url", "file", "folder", "path")):
        return "source"
    if any(part in key for part in ("format", "container", "profile", "preset", "quality", "dpi", "bitrate", "resolution")):
        return "format"
    if any(part in key for part in ("output", "report", "export", "package", "release")):
        return "output"
    if any(part in key for part in ("codec", "encode", "model", "engine")):
        return "encoding"
    if kind in {"checkbox", "bool", "boolean", "toggle", "checkboxes", "multi_checkbox", "multicheckbox", "multi-select", "multiselect"}:
        return "options"
    return "parameters"


def _find_field(fields: tuple[dict[str, Any], ...] | list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for field in fields:
        if field_id(field) == key:
            return field
    return None


def _normalized_alignment_mode_value(value: Any) -> str:
    mode = str(value or "fast").strip().lower()
    aliases = {
        "normalization": "normalized",
        "normalize": "normalized",
        "post_normalize": "normalized",
        "post-normalize": "normalized",
        "alignment_normalization": "normalized",
        "alignment+normalization": "normalized",
    }
    mode = aliases.get(mode, mode)
    return "normalized" if mode in {"normalized", "normalised"} else "fast"


def current_alignment_mode(fields: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> str:
    mode_field = _find_field(fields, ALIGNMENT_MODE_FIELD_ID)
    if mode_field is None:
        return "fast"
    return _normalized_alignment_mode_value(current_field_value(mode_field))


def is_alignment_command(node: CommandNode | None) -> bool:
    return bool(node and node.id == "run_address_aligner")


def is_alignment_normalization_field(field: dict[str, Any]) -> bool:
    return field_section_id(field) == ALIGNMENT_NORMALIZATION_SECTION_ID or field_id(field) in ALIGNMENT_NORMALIZATION_FIELD_IDS


def reset_alignment_normalization_values(fields: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> None:
    values = state.setdefault("field_values", {})
    for field in fields:
        if is_alignment_normalization_field(field):
            key = field_id(field)
            if key:
                values[key] = field_default(field)


def select_alignment_mode(fields: tuple[dict[str, Any], ...] | list[dict[str, Any]], mode: str) -> None:
    values = state.setdefault("field_values", {})
    next_mode = _normalized_alignment_mode_value(mode)
    values[ALIGNMENT_MODE_FIELD_ID] = next_mode
    if next_mode == "fast":
        reset_alignment_normalization_values(fields)
    command_tree.refresh()


def render_alignment_mode_switcher(node: CommandNode, fields: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> None:
    if not is_alignment_command(node):
        return
    mode_field = _find_field(fields, ALIGNMENT_MODE_FIELD_ID)
    if mode_field is None:
        return
    current_mode = current_alignment_mode(fields)
    options = field_options(mode_field)
    label = field_section_label(ALIGNMENT_MODE_FIELD_ID)
    with ui.element("div").classes("audion-window-mode-block"):
        ui.label(label).classes("audion-window-mode-title")
        with ui.element("div").classes("audion-window-mode-tabs"):
            for option in options:
                value = _normalized_alignment_mode_value(option_value(option))
                text = option_label(option)
                classes = "audion-window-mode-tab"
                if value == current_mode:
                    classes += " audion-window-mode-tab-active"
                ui.button(
                    text,
                    on_click=lambda item_mode=value: select_alignment_mode(fields, item_mode),
                ).props("dense flat no-wrap").classes(classes)


def command_render_fields(node: CommandNode, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not is_alignment_command(node):
        return fields
    mode = current_alignment_mode(fields)
    result: list[dict[str, Any]] = []
    for field in fields:
        key = field_id(field)
        if key == ALIGNMENT_MODE_FIELD_ID:
            continue
        if mode == "fast" and is_alignment_normalization_field(field):
            continue
        result.append(field)
    return result


def apply_command_parameter_guards(node: CommandNode, parameters: dict[str, Any]) -> dict[str, Any]:
    if not is_alignment_command(node):
        return parameters
    mode = _normalized_alignment_mode_value(parameters.get(ALIGNMENT_MODE_FIELD_ID))
    parameters[ALIGNMENT_MODE_FIELD_ID] = mode
    if mode == "fast":
        for field in command_visible_fields(node.fields):
            if is_alignment_normalization_field(field):
                key = field_id(field)
                if key:
                    parameters[key] = field_default(field)
    return parameters


def field_section_label(section_id: str) -> str:
    key = f"section_{section_id}"
    label = tr(key)
    if label != key:
        return label
    return section_id.replace("_", " ").title()


def group_fields_by_section(fields: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    group_index: dict[str, int] = {}
    for field in fields:
        section_id = field_section_id(field)
        if section_id not in group_index:
            group_index[section_id] = len(groups)
            groups.append((section_id, [field]))
        else:
            groups[group_index[section_id]][1].append(field)
    return groups


def render_field_grid(fields: list[dict[str, Any]]) -> None:
    if not fields:
        return
    with ui.element("div").classes("audion-fields-grid"):
        for section_id, section_fields in group_fields_by_section(fields):
            with ui.element("section").classes(f"audion-field-section audion-field-section-{section_id}"):
                ui.label(field_section_label(section_id)).classes("audion-section-title")
                with ui.element("div").classes("audion-section-fields"):
                    for field in section_fields:
                        render_field(field)


def render_advanced_fields(fields: list[dict[str, Any]]) -> None:
    if not fields:
        return
    with ui.expansion(
        tr("advanced"),
        value=bool(getattr(settings, "advanced_open", False)),
        on_value_change=save_advanced_open,
    ).classes("audion-advanced-expansion w-full") as expansion:
        expansion.props("dense switch-toggle-side")
        render_field_grid(fields)


def command_node_button(node: CommandNode) -> None:
    has_children = bool(node.children)
    label = node.display_title(settings.language)
    description = node.display_description(settings.language)
    if has_children and not description:
        description = tr("open_menu")

    with ui.element("div").classes("audion-operation-row"):
        button = ui.button(
            label,
            on_click=command_click_handler(node),
        ).props("dense flat no-wrap").classes("audion-action audion-operation-button rounded-lg")
        attach_tooltip(button, description or label)
        ui.label(description).classes("audion-operation-description")


def command_nav_row(
    trail: list[CommandNode],
    pending: CommandNode | None,
    inline_actions: list[CommandNode] | None = None,
) -> None:
    can_go_back = pending is not None or bool(trail)
    if not can_go_back and pending is None and not inline_actions:
        return
    if pending is not None:
        title = pending.display_title(settings.language)
    elif trail:
        title = " / ".join(node.display_title(settings.language) for node in trail)
    else:
        title = ""

    with ui.row().classes("audion-command-nav w-full items-center gap-2"):
        if can_go_back:
            back_button = ui.button(
                tr("back"),
                on_click=go_back_command,
            ).props("dense flat no-wrap").classes("audion-action w-28 rounded-lg")
            attach_tooltip(back_button, tr("back"))
        ui.label(title).classes("audion-command-title min-w-0 flex-1 truncate text-sm text-gray-400")
        if pending is not None:
            run_button = ui.button(
                tr("run"),
                on_click=run_pending_click_handler(pending),
            ).props("dense flat no-wrap").classes("audion-action audion-nav-run-button rounded-lg")
            attach_tooltip(run_button, pending.display_description(settings.language) or tr("run"))
        elif inline_actions:
            with ui.row().classes("audion-command-nav-actions items-center gap-2"):
                for node in inline_actions:
                    inline_button = ui.button(
                        node.display_title(settings.language),
                        on_click=run_pending_click_handler(node),
                    ).props("dense flat no-wrap").classes("audion-action audion-nav-run-button rounded-lg")
                    attach_tooltip(inline_button, node.display_description(settings.language) or node.display_title(settings.language))


@ui.refreshable
def command_tree() -> None:
    trail, nodes = current_command_level()
    pending = state.get("pending_command")
    parent = trail[-1] if trail else None
    visible_nodes = command_visible_nodes(nodes)
    inline_actions = visible_nodes if pending is None and can_inline_child_actions(parent, visible_nodes) else []
    command_nav_row(trail, pending, inline_actions)

    if pending is not None:
        visible_fields = command_visible_fields(pending.fields)
        if visible_fields:
            if pending.id == "oktmo_key_console":
                render_oktmo_console_actions()
            render_alignment_mode_switcher(pending, visible_fields)
            render_fields = command_render_fields(pending, visible_fields)
            primary_fields, advanced_fields = split_primary_advanced_fields(tuple(render_fields))
            ui.label(tr("parameters")).classes("text-sm font-semibold text-gray-300")
            render_field_grid(primary_fields)
            render_advanced_fields(advanced_fields)
        description = pending.display_description(settings.language)
        if description:
            ui.label(description).classes("text-sm text-gray-400")
        return

    if inline_actions:
        visible_fields = command_visible_fields(parent.fields)
        render_alignment_mode_switcher(parent, visible_fields)
        render_fields = command_render_fields(parent, visible_fields)
        primary_fields, advanced_fields = split_primary_advanced_fields(tuple(render_fields))
        ui.label(tr("parameters")).classes("text-sm font-semibold text-gray-300")
        render_field_grid(primary_fields)
        render_advanced_fields(advanced_fields)
        return

    for node in visible_nodes:
        command_node_button(node)


def operation_by_id(operation_id: str) -> Operation | None:
    for operation in [*manifest.operations, *manifest.maintenance_operations]:
        if operation.id == operation_id:
            return operation
    return None


def command_node_by_id(node_id: str, nodes: list[CommandNode] | tuple[CommandNode, ...] | None = None) -> CommandNode | None:
    iterable = nodes if nodes is not None else manifest.operation_groups
    for node in iterable:
        if node.id == node_id:
            return node
        found = command_node_by_id(node_id, node.children)
        if found is not None:
            return found
    return None


def command_default_operation(node_id: str) -> Operation | None:
    node = command_node_by_id(node_id)
    if node is None or node.children:
        return None
    parameters = dict(node.parameters)
    for field in command_visible_fields(node.fields):
        if is_ui_only_field(field):
            continue
        key = field_id(field)
        if key:
            parameters[key] = field_default(field)
    return node.to_operation(parameters)


_application_css_cache: dict[str, str] = {}


def application_css(name: str) -> str:
    """A stylesheet that lives next to this module rather than inside it."""
    if name not in _application_css_cache:
        path = Path(__file__).resolve().with_name(name)
        _application_css_cache[name] = path.read_text(encoding="utf-8")
    return _application_css_cache[name]


def add_styles() -> None:
    add_audion_canonical_ui_styles()
    variables_css = "\n".join(
        f"            --{key}: {value};"
        for key, value in sorted(theme_variables().items())
    )
    ui.add_head_html(
        "<style>\n"
        ":root {\n"
        f"{variables_css}\n"
        "}\n"
        + application_css("tokens.css")
        + application_css("base.css")
        + WORKBENCH_LAYOUT_CSS
        + WORKBENCH_OVERRIDE_CSS
        + application_css("theme.css")
        + "\n</style>\n"
    )
    ui.add_head_html(
        """
        <script>
        (() => {
          const replacements = new Map([
            ['Connection lost.', 'Идёт загрузка данных...'],
            ['Trying to reconnect...', 'Пожалуйста, подождите...'],
            ['Trying to reconnect…', 'Пожалуйста, подождите...'],
          ]);
          const patchReconnectText = () => {
            const root = document.body || document.documentElement;
            if (!root) return;
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            const nodes = [];
            while (walker.nextNode()) nodes.push(walker.currentNode);
            for (const node of nodes) {
              const current = (node.nodeValue || '').trim();
              const replacement = replacements.get(current);
              if (replacement) node.nodeValue = (node.nodeValue || '').replace(current, replacement);
            }
          };
          const start = () => {
            patchReconnectText();
            new MutationObserver(patchReconnectText).observe(
              document.body || document.documentElement,
              { childList: true, subtree: true, characterData: true }
            );
          };
          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', start, { once: true });
          } else {
            start();
          }
        })();
        </script>
        """
    )


def build_ui() -> None:
    ensure_project_dirs(paths)
    if not state["status"]:
        state["status"] = tr("idle")
    if active_theme_mode() == "dark":
        ui.dark_mode().enable()
    else:
        ui.dark_mode().disable()
    add_styles()
    ui.add_head_html(WORKBENCH_FEEDBACK_CSS)

    with ui.header().classes("audion-header h-[42px] items-center justify-between px-4"):
        ui.label(app_title()).classes("audion-header-title text-lg font-bold")
        with ui.row().classes("audion-header-controls items-center gap-2"):
            ui.icon("palette").classes("text-lg")
            theme_select = ui.select(
                options=theme_options(),
                value=active_theme(),
                on_change=theme_change_handler,
            ).props("dense outlined options-dense").classes("audion-theme-select")
            attach_tooltip(theme_select, tr("theme"))
            lang_button = ui.button(tr("lang_switch"), on_click=toggle_language).props("dense flat").classes("audion-action rounded-lg")
            attach_tooltip(lang_button, tr("lang_switch"))
            cancel_button = ui.button(tr("cancel"), on_click=lambda: state.update({"cancel": True})).props("dense flat color=negative")
            attach_tooltip(cancel_button, tr("cancel"))
            cancel_button.visible = False

    with ui.element("div").classes("audion-shell"):
        with ui.column().classes("audion-pane audion-scroll gap-3"):
            with ui.column().classes("audion-panel audion-workspace-panel w-full gap-2 p-2"):
                WORKBENCH_RENDERER.render_address_rows()
                WORKBENCH_RENDERER.render_action_bar()

            ui.label(f"{em('operations')}{tr('operations')}").classes("text-lg font-bold")
            command_tree()

            if manifest.maintenance_operations:
                ui.label(f"{em('maintenance')}{tr('maintenance')}").classes("text-lg font-bold pt-2")
                for operation in manifest.maintenance_operations:
                    if operation.id == "cleanup_input_output":
                        continue
                    operation_button(operation)

        ui.element("div").classes("audion-splitter").props(f'title="{tr("resize_panels")}"')

        with ui.element("div").classes("audion-pane audion-right gap-2 pt-3"):
            with ui.column().classes("audion-panel w-full gap-2 p-3"):
                with ui.element("div").classes(status_row_classes()) as status_row:
                    status_dot_main = ui.element("span").classes("audion-status-dot-mark")
                    status_state_label = ui.label(status_state_text()).classes("audion-status-state")
                    status_label = ui.label(str(state["status"])).classes("audion-status-message")
                    status_clock = ui.label(elapsed_text(None)).classes("audion-status-clock")
                    with ui.element("div").classes("audion-status-bar"):
                        status_bar_fill = ui.element("i").style("width: 0%")
                    status_percent = ui.label(progress_text()).classes("audion-status-percent")
                artifact_panel()

            with ui.column().classes("audion-terminal-panel w-full gap-2 p-3"):
                with ui.row().classes("audion-log-toolbar w-full items-center gap-2"):
                    ui.label(f"{em('log')}{tr('log')}").classes("text-base font-semibold")
                    ui.space()
                    logs_button = ui.button(tr("logs"), on_click=lambda: open_folder(paths.logs)).props("dense flat").classes("audion-action rounded-lg")
                    attach_tooltip(logs_button, audion_folder_button_tooltip("logs", paths.logs))
                    report_button = ui.button(tr("report"), on_click=lambda: open_folder(paths.report)).props("dense flat").classes("audion-action rounded-lg")
                    attach_tooltip(report_button, audion_folder_button_tooltip("report", paths.report))
                    config_button = ui.button(tr("config"), on_click=lambda: open_folder(paths.config)).props("dense flat").classes("audion-action rounded-lg")
                    attach_tooltip(config_button, audion_folder_button_tooltip("config", paths.config))
                    clear_log_button = ui.button(icon="delete_sweep", on_click=clear_terminal_log).props("dense flat round").classes("audion-action audion-log-icon-button")
                    attach_tooltip(clear_log_button, audion_terminal_action_tooltip("clear_terminal_window"))
                    expand_log_button = ui.button(icon="open_in_full", on_click=lambda: log_dialog.open()).props("dense flat round").classes("audion-action audion-log-icon-button")
                    attach_tooltip(expand_log_button, audion_terminal_action_tooltip("expand"))
                log_view = ui.html("", sanitize=False, tag="pre").classes("audion-terminal w-full min-h-[66vh]")
                with ui.row().classes("audion-terminal-footer w-full items-center gap-2 px-1 pt-1"):
                    status_dot = ui.label("●").classes(status_dot_classes())
                    terminal_status_label = ui.label(str(state["status"])).classes("min-w-0 flex-1 truncate text-xs")

    with ui.dialog() as log_dialog:
        with ui.card().classes("audion-dialog h-[92vh] w-[92vw] rounded-lg p-3"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(f"{em('log')}{tr('log')}").classes("text-base font-semibold")
                ui.space()
                config_button = ui.button(tr("config"), on_click=lambda: open_folder(paths.config)).props("dense flat").classes("audion-action rounded-lg")
                attach_tooltip(config_button, audion_folder_button_tooltip("config", paths.config))
                clear_expanded_log_button = ui.button(icon="delete_sweep", on_click=clear_terminal_log).props("dense flat round").classes("audion-action audion-log-icon-button")
                attach_tooltip(clear_expanded_log_button, tr("clear_terminal_window"))
                close_button = ui.button(tr("close"), on_click=log_dialog.close).props("dense flat").classes("audion-action rounded-lg").tooltip(audion_terminal_action_tooltip("close"))
                attach_tooltip(close_button, tr("close"))
            expanded_log_view = ui.html("", sanitize=False, tag="pre").classes("audion-terminal audion-terminal-expanded w-full")

    ui.run_javascript(
        """
        (() => {
          const storageKey = 'audion_gui_terminal_width_px';
          const defaultWidth = 666;
          const minLeft = 460;
          const minRight = 460;

          const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

          const applyWidth = (width) => {
            const shell = document.querySelector('.audion-shell');
            if (!shell) return;
            const rect = shell.getBoundingClientRect();
            const maxRight = Math.max(minRight, rect.width - minLeft - 40);
            const next = clamp(Number(width) || defaultWidth, minRight, maxRight);
            shell.style.setProperty('--audion-terminal-width', `${Math.round(next)}px`);
            localStorage.setItem(storageKey, String(Math.round(next)));
          };

          const setup = () => {
            const shell = document.querySelector('.audion-shell');
            const splitter = document.querySelector('.audion-splitter');
            if (!shell || !splitter) {
              setTimeout(setup, 80);
              return;
            }
            if (splitter.dataset.audionReady === '1') return;
            splitter.dataset.audionReady = '1';

            applyWidth(localStorage.getItem(storageKey) || defaultWidth);

            let dragging = false;
            const updateFromEvent = (event) => {
              if (!dragging) return;
              const rect = shell.getBoundingClientRect();
              const rightWidth = rect.right - event.clientX - 10;
              applyWidth(rightWidth);
            };

            splitter.addEventListener('pointerdown', (event) => {
              dragging = true;
              splitter.setPointerCapture?.(event.pointerId);
              document.body.classList.add('audion-resizing');
              event.preventDefault();
            });
            splitter.addEventListener('pointermove', updateFromEvent);
            splitter.addEventListener('pointerup', (event) => {
              dragging = false;
              splitter.releasePointerCapture?.(event.pointerId);
              document.body.classList.remove('audion-resizing');
            });
            splitter.addEventListener('pointercancel', () => {
              dragging = false;
              document.body.classList.remove('audion-resizing');
            });
            window.addEventListener('resize', () => applyWidth(localStorage.getItem(storageKey) || defaultWidth));
          };

          setup();
        })();
        """
    )

    last_log_version = {"value": -1}
    rendered_line_count = {"value": 0}
    rendered_line_offset = {"value": 0}
    terminal_renderer = {"value": AnsiHtmlRenderer()}

    refresh_timer: Any | None = None

    def sync_terminal_fragment(html_fragment: str, *, clear: bool = False) -> None:
        if not html_fragment and not clear:
            return
        fragment_json = json.dumps(html_fragment)
        clear_json = "true" if clear else "false"
        ui.run_javascript(
            f"""
            requestAnimationFrame(() => {{
              const html = {fragment_json};
              const clear = {clear_json};
              document.querySelectorAll('.audion-terminal').forEach((el) => {{
                const wasAtBottom = clear || (el.scrollHeight - el.scrollTop - el.clientHeight <= 4);
                if (clear) {{
                  el.replaceChildren();
                }}
                if (html) {{
                  el.insertAdjacentHTML('beforeend', html);
                }}
                if (wasAtBottom) {{
                  el.scrollTop = el.scrollHeight;
                }}
              }});
            }});
            """
        )

    # Every one of these used to be written twice a second whether or not it had
    # changed, so an idle window still sent ten element updates a second. Holding
    # the last value makes an idle panel cost nothing and pays for the clock.
    shown = {"status": None, "state": None, "row": None, "clock": None, "percent": None, "fill": None}
    run_clock: dict[str, float | None] = {"started": None, "frozen": None}

    def refresh() -> None:
        nonlocal refresh_timer
        try:
            running = bool(state["running"])
            if running and run_clock["started"] is None:
                run_clock["started"] = time.monotonic()
                run_clock["frozen"] = None
            elif not running and run_clock["started"] is not None:
                run_clock["frozen"] = time.monotonic() - run_clock["started"]
                run_clock["started"] = None
            seconds = (
                time.monotonic() - run_clock["started"]
                if run_clock["started"] is not None
                else run_clock["frozen"]
            )

            def show(key: str, value: Any, assign: Any) -> None:
                if shown[key] != value:
                    shown[key] = value
                    assign(value)

            message = str(state["status"])
            show("status", message, lambda value: (
                setattr(status_label, "text", value),
                setattr(terminal_status_label, "text", value),
            ))
            show("state", status_state_text(), lambda value: setattr(status_state_label, "text", value))
            show("row", status_row_classes(), lambda value: (
                status_row.classes(replace=value),
                status_dot.classes(replace=status_dot_classes()),
            ))
            show("clock", elapsed_text(seconds), lambda value: setattr(status_clock, "text", value))
            show("percent", progress_text(), lambda value: setattr(status_percent, "text", value))
            show("fill", f"{float(state['progress']) * 100:.1f}%",
                 lambda value: status_bar_fill.style(f"width: {value}"))
            log_version = int(state["log_version"])
            if log_version != last_log_version["value"]:
                last_log_version["value"] = log_version
                lines = list(state.get("lines", []))
                line_offset = int(state.get("line_offset", 0))
                clear_terminal = (
                    line_offset != rendered_line_offset["value"]
                    or len(lines) < rendered_line_count["value"]
                )
                if clear_terminal:
                    terminal_renderer["value"] = AnsiHtmlRenderer()
                    html_fragment = terminal_lines_html(lines, renderer=terminal_renderer["value"])
                    rendered_line_count["value"] = len(lines)
                    rendered_line_offset["value"] = line_offset
                    log_view.set_content(html_fragment)
                    expanded_log_view.set_content(html_fragment)
                    ui.run_javascript(
                        """
                        requestAnimationFrame(() => {
                          document.querySelectorAll('.audion-terminal').forEach((el) => {
                            el.scrollTop = el.scrollHeight;
                          });
                        });
                        """
                    )
                else:
                    start_index = rendered_line_count["value"]
                    append_lines = lines[start_index:]
                    html_fragment = terminal_lines_html(
                        append_lines,
                        leading_newline=start_index > 0 and bool(append_lines),
                        renderer=terminal_renderer["value"],
                    )
                    rendered_line_count["value"] = len(lines)
                    rendered_line_offset["value"] = line_offset
                    sync_terminal_fragment(html_fragment, clear=False)
            cancel_button.visible = bool(state["running"])
        except RuntimeError as exc:
            message = str(exc)
            if "slot belongs to has been deleted" not in message and "current slot cannot be determined" not in message:
                raise
            logging.warning("NiceGUI refresh timer stopped because the client slot was deleted.")
            if refresh_timer is not None:
                refresh_timer.deactivate()

    refresh_timer = ui.timer(0.5, refresh)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audion NiceGUI shell.")
    parser.add_argument("--host", default=str(ui_info.get("host", "127.0.0.1")))
    parser.add_argument("--port", type=int, default=int(ui_info.get("port", 8080)))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    return parser.parse_args()


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def build_ui_once() -> dict[str, int]:
    """Build the whole page once, headlessly, and report what came of it.

    `--smoke` used to print a line and return, so an app could ship a `build_ui`
    that raised on its first statement and still pass — twice in this fleet it did.
    Here the page is actually built: no browser and no HTTP request, so whatever
    the app defers until a client attaches is skipped, but every widget is
    constructed and the stylesheet has to arrive.
    """
    import asyncio
    import logging
    import re

    from nicegui import core
    from nicegui.client import Client
    from nicegui.page import page as page_definition

    async def build() -> tuple[int, str]:
        core.loop = asyncio.get_running_loop()
        # Work deferred to a connected browser fails here and says nothing about
        # the build. An exception raised by build_ui itself still propagates.
        core.loop.set_exception_handler(lambda _loop, _context: None)
        logging.getLogger("nicegui").setLevel(logging.CRITICAL)
        client = Client(page_definition("/__smoke__"))
        with client:
            build_ui()
        report = len(client.elements), client.shared_head_html + client.head_html
        # The page starts work that waits for a browser to attach. Nothing will
        # attach, so stop it deliberately instead of letting the loop close on it.
        pending = asyncio.all_tasks(core.loop) - {asyncio.current_task()}
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return report

    element_count, head = asyncio.run(build())
    if element_count < 2:
        raise RuntimeError("build_ui produced no widgets")
    # Token prefixes differ between apps, so look for any custom property rather
    # than for one project's naming.
    if not re.search(r"--[\w-]+\s*:", head):
        raise RuntimeError("the stylesheet never reached the page")
    return {"elements": element_count, "stylesheet_bytes": len(head)}


def main() -> int:
    args = parse_args()
    ensure_project_dirs(paths)
    if args.smoke:
        try:
            report = build_ui_once()
        except Exception as error:  # noqa: BLE001
            print(f"FAIL nicegui shell: {ROOT}: {error}")
            return 1
        print(
            f"OK nicegui shell: {ROOT}"
            f" | widgets={report['elements']}"
            f" | stylesheet={report['stylesheet_bytes']} bytes"
        )
        return 0

    if port_is_open(args.host, args.port):
        url = f"http://{args.host}:{args.port}/"
        print(f"GUI already appears to be running: {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    ui.run(
        root=build_ui,
        title=app_title(),
        host=args.host,
        port=args.port,
        reload=False,
        native=False,
        show=not args.no_browser,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
