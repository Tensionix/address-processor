"""The console command of Audion Address Processor.

A button of the window and the command line run the same thing: an operation of the manifest, by
the same runner (`execute_operation`), with the same defaults of its fields. While the window sat on
NiceGUI, an operation could be run "as in the window" only from the window - it called the service
in its own process.

  python -m system_core.cli describe
  python -m system_core.cli run --operation run_address_aligner --source input --target output
  python -m system_core.cli run --operation run_table_comparison --set file_a=C:\\a.xlsx --set file_b=C:\\b.xlsx
  python -m system_core.cli options --operation run_table_comparison --field sheet_a --set file_a=C:\\a.xlsx
  python -m system_core.cli oktmo --action load_keys
  python -m system_core.cli serve
  python -m system_core.cli stop-office --session-dir C:\\temp\\session
  python -m system_core.cli version

`run`: a plain line of the output is a line of the log of the operation; a line that starts with
`::address::` is a service line and carries JSON - where the log is written, the share of the work
done, the one live line under the log (a bar rewritten in place), the end. The outcome goes to the
file of `--result`.

Outcomes and exit codes: `done` 0; `failed` 1; `stopped` 130; a wrong call - 2, and nothing is run.

Stopping: the caller creates the file of `--cancel-file`. The operation sees it at its next safe point
and stops by itself. A caller that has to kill the process instead gives `--session-dir` first: the
Excel and Word the operation started are written down there, and `stop-office` closes them.

`serve` is for what a window asks while a person types: the options of a field and the actions of
the OKTMO panel, one JSON object a line on the standard input, one answer a line on the output. It
keeps what it read (the Rosstat registry takes about a second to read), which a command of its own
would read again on every call. An operation never runs in it - it is killed with its process.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_core import office_session  # noqa: E402
from system_core.core import operation_model as model  # noqa: E402
from system_core.core.ansi_terminal import strip_ansi  # noqa: E402
from system_core.core.jobs import execute_operation  # noqa: E402
from system_core.core.manifest import load_manifest  # noqa: E402
from system_core.core.paths import ensure_project_dirs, get_project_paths  # noqa: E402
from system_core.core.window_layout import load_layout  # noqa: E402

CONTROL = "::address::"
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_STOPPED = 0, 1, 2, 130
SERVICE = "system_core.services.address_aligner_service"

# The actions of the OKTMO panel: name -> (function of the service, the arguments it takes after the root).
# "values" - the values of the fields of the panel, "kind" - region or municipality.
OKTMO_ACTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "data_status": ("oktmo_data_status", ("values",)),
    "scope_pin_status": ("oktmo_scope_pin_status", ("values", "kind")),
    "pin_scope": ("oktmo_pin_scope_value", ("values", "kind")),
    "unpin_scope": ("oktmo_unpin_scope_value", ("values", "kind")),
    "add_scope_keys": ("oktmo_add_scope_keys", ("values", "kind")),
    "find_candidates": ("oktmo_find_settlement_candidates", ("values",)),
    "add_candidate_keys": ("oktmo_add_candidate_keys", ("values",)),
    "save_keys": ("oktmo_save_scope_keys", ("values",)),
    "load_keys": ("oktmo_load_key_file", ()),
    "clear_keys": ("oktmo_clear_key_file", ()),
    "reset_keys": ("oktmo_reset_project_keys", ()),
    "open_keys": ("oktmo_open_key_file", ()),
    "pins_status": ("oktmo_pin_file_status", ()),
    "pins_export": ("oktmo_export_pin_file", ()),
    "pins_import": ("oktmo_import_pin_file", ()),
    "pins_clear": ("oktmo_clear_pin_file", ()),
    "pins_open": ("oktmo_open_pin_file", ()),
}

# Nobody reads the output any more - the caller closed its end of the pipe. The operation goes on
# without it: its own log file is written all the same, and one ended in the middle would leave
# more behind than one that finishes unseen.
_nobody_listens = False


def say(line: str) -> None:
    """One line to the caller - on the real standard output, whatever the operation did to `sys.stdout`.

    The services redirect `sys.stdout` into their log (`_relay_output`) while the engine works, to
    catch what it prints. A `print` made from a callback inside that redirect would go into the same
    log, be passed to the callback again, and so on without end: found by running the alignment, 2 MB
    of one line in twenty seconds.
    """
    global _nobody_listens
    if _nobody_listens:
        return
    stream = sys.__stdout__ or sys.stdout
    try:
        stream.write(line + "\n")
        stream.flush()
    except UnicodeEncodeError:
        # A line with a sign the stream cannot write (a lone surrogate in a file name) goes with a mark in its
        # place: the window is still listening, and silence for the rest of the run would hide its end.
        try:
            stream.write(line.encode("utf-8", "replace").decode("utf-8") + "\n")
            stream.flush()
        except (OSError, ValueError):
            _nobody_listens = True
    except (OSError, ValueError):
        _nobody_listens = True


def control(payload: dict[str, Any]) -> None:
    say(CONTROL + json.dumps(payload, ensure_ascii=False, default=str))


def usage_error(message: str) -> int:
    try:
        print("[ERR] " + message, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass
    return EXIT_USAGE


def project(root: str | None):
    paths = get_project_paths(Path(root).resolve() if root else ROOT)
    manifest_path = paths.config / "tool_manifest.yaml"
    if not manifest_path.is_file():
        raise ValueError(f"not a project folder, no manifest: {manifest_path}")
    try:
        manifest = load_manifest(manifest_path)
    except Exception as error:  # noqa: BLE001 - whatever the manifest stumbles over, nothing was run
        raise ValueError(f"the manifest does not read: {manifest_path}: {error}") from error
    return paths, manifest


def project_version(paths) -> str:
    try:
        return str(json.loads((paths.config / "version.json").read_text(encoding="utf-8")).get("version", ""))
    except (OSError, ValueError):
        return ""


def read_values(args: argparse.Namespace, node) -> dict[str, Any]:
    """The values of the fields: the file of `--params`, over it each `--set name=value`."""
    values: dict[str, Any] = {}
    if getattr(args, "params", ""):
        loaded = json.loads(Path(args.params).read_text(encoding="utf-8-sig"))
        if not isinstance(loaded, dict):
            raise ValueError("--params: an object of JSON 'field: value' is expected")
        values.update(loaded)
    fields = {model.field_id(field): field for field in node.fields}
    for item in getattr(args, "set", None) or []:
        name, separator, text = item.partition("=")
        name = name.strip()
        if not separator or not name:
            raise ValueError(f"--set: name=value is expected, got {item!r}")
        if name not in fields:
            raise ValueError(f"--set: the operation has no field {name!r}")
        try:
            values[name] = model.coerce(fields[name], text)
        except ValueError as error:
            raise ValueError(f"--set {name}: {error}") from error
    return values


def write_result(path: str, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    draft = target.with_name(target.name + ".tmp")
    draft.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    draft.replace(target)


# ---------------------------------------------------------------------------------------------
# describe, version

def command_describe(args: argparse.Namespace) -> int:
    paths, manifest = project(args.root)
    try:
        layout = load_layout(paths.config / "window_layout.yaml", manifest)
    except ValueError as error:
        return usage_error(str(error))
    payload = model.describe(manifest, layout)
    payload["version"] = project_version(paths)
    payload["paths"] = {"root": str(paths.root), "input": str(paths.input), "output": str(paths.output),
                        "logs": str(paths.logs), "report": str(paths.report), "config": str(paths.config)}
    say(json.dumps(payload, ensure_ascii=False, default=str))
    return EXIT_OK


def command_version(args: argparse.Namespace) -> int:
    paths, _manifest = project(args.root)
    say(project_version(paths))
    return EXIT_OK


# ---------------------------------------------------------------------------------------------
# run

def command_run(args: argparse.Namespace) -> int:
    try:
        paths, manifest = project(args.root)
    except ValueError as error:
        return usage_error(str(error))
    node = model.find_node(manifest, args.operation)
    if node is None:
        return usage_error(f"the manifest has no operation {args.operation!r}")
    try:
        values = read_values(args, node)
    except (OSError, ValueError) as error:
        return usage_error(str(error))
    unknown = model.unknown_values(node, values)
    if unknown:
        return usage_error("the operation has no fields: " + ", ".join(unknown))
    wrong = model.wrong_choices(node, values)
    if wrong:
        return usage_error("not among the options of the field: " + ", ".join(wrong))
    short = model.short_selections(node, values)
    if short:
        return usage_error("fewer ticks than the field asks for: " + ", ".join(short))

    source = Path(args.source).expanduser() if args.source else paths.input
    target = Path(args.target).expanduser() if args.target else paths.output
    if not source.is_absolute():
        source = paths.root / source
    if not target.is_absolute():
        target = paths.root / target
    ensure_project_dirs(paths)
    if not source.exists():
        return usage_error(f"the source was not found: {source}")
    if args.session_dir:
        Path(args.session_dir).mkdir(parents=True, exist_ok=True)
        os.environ[office_session.SESSION_ENV] = str(Path(args.session_dir).resolve())
    cancel_file = Path(args.cancel_file) if args.cancel_file else None

    parameters = model.build_parameters(node, values)
    operation = node.to_operation(parameters) if hasattr(node, "to_operation") else dataclasses.replace(node, parameters=parameters)
    run_paths = dataclasses.replace(paths, input=source.resolve(strict=False), output=target.resolve(strict=False))
    shown = {"progress": -1.0}

    def log(line: str) -> None:
        say(strip_ansi(str(line)))

    def progress(value: float) -> None:
        # A share that moved by less than a thousandth is not news.
        if abs(value - shown["progress"]) >= 0.001 or value in (0.0, 1.0):
            shown["progress"] = value
            control({"progress": round(float(value), 4)})

    def live(line: str) -> None:
        control({"live": strip_ansi(str(line))})

    def started(context) -> None:
        control({"started": {"operation": operation.id, "log": str(context.log_file),
                             "report_dir": str(context.report_dir)}})

    began = time.monotonic()
    result = execute_operation(run_paths, operation, log, progress,
                               (lambda: cancel_file.exists()) if cancel_file is not None else None,
                               started, live)
    office_session.forget_session()
    stopped = cancel_file is not None and cancel_file.exists() and (not result.ok or bool(result.data.get("cancelled")))
    outcome = "stopped" if stopped else "failed" if not result.ok else "done"
    payload = {"operation": operation.id, "outcome": outcome, "ok": result.ok, "message": result.message,
               "data": result.data, "source": str(source), "target": str(target),
               "log": result.log_file, "report_dir": result.report_dir,
               "seconds": round(time.monotonic() - began, 1)}
    write_result(args.result, payload)
    control({"finished": {"outcome": outcome, "message": result.message, "seconds": payload["seconds"]}})
    return EXIT_STOPPED if stopped else EXIT_OK if result.ok else EXIT_FAILED


# ---------------------------------------------------------------------------------------------
# options, oktmo: what a window asks while a person types

class OptionCache:
    """The lists of options with the time the manifest gives them to live (`cache_seconds`, 45 by default).

    A list is kept per source and per the values of the fields it depends on (and the folder of the
    OKTMO data, which changes what the OKTMO lists hold) - the key the window on NiceGUI used.
    """

    def __init__(self) -> None:
        self._items: dict[Any, tuple[float, list[dict[str, Any]]]] = {}

    @staticmethod
    def key(field: dict[str, Any], values: dict[str, Any]) -> Any:
        source = model.option_source(field)
        signature = [(name, str(values.get(name) or "")) for name in model.depends_on(field)]
        if source.startswith(SERVICE + ":oktmo_"):
            signature.append(("oktmo_data_dir", str(values.get("oktmo_data_dir") or "")))
        return (source, tuple(signature))

    def get(self, field: dict[str, Any], values: dict[str, Any], root: Path) -> list[dict[str, Any]]:
        source = model.option_source(field)
        if not source:
            return [model.describe_option(option) for option in field.get("options") or []]
        lifetime = float(field.get("cache_seconds", 45) or 0)
        key = self.key(field, values)
        now = time.monotonic()
        cached = self._items.get(key)
        if cached and lifetime > 0 and now - cached[0] < lifetime:
            return cached[1]
        options = [model.describe_option(option) for option in model.resolve_options(source, root, values, field)]
        self._items[key] = (now, options)
        return options

    def forget(self) -> None:
        self._items.clear()


def options_for(manifest, root: Path, operation: str, field_name: str, values: dict[str, Any], cache: OptionCache) -> dict[str, Any]:
    node = model.find_node(manifest, operation)
    if node is None:
        raise ValueError(f"the manifest has no operation {operation!r}")
    field = next((item for item in node.fields if model.field_id(item) == field_name), None)
    if field is None:
        raise ValueError(f"the operation {operation!r} has no field {field_name!r}")
    return {"operation": operation, "field": field_name,
            "options": cache.get(field, model.form_values(node, values), root)}


def oktmo_action(root: Path, action: str, values: dict[str, Any], kind: str) -> Any:
    import importlib

    if action not in OKTMO_ACTIONS:
        raise ValueError(f"no such action of the OKTMO panel: {action!r}; there are {', '.join(OKTMO_ACTIONS)}")
    function_name, takes = OKTMO_ACTIONS[action]
    function = getattr(importlib.import_module(SERVICE), function_name)
    arguments: list[Any] = [root]
    for name in takes:
        arguments.append(dict(values) if name == "values" else kind)
    return function(*arguments)


def plain_values(args: argparse.Namespace) -> dict[str, Any]:
    """`--params` and `--set name=value` of a call that has no operation to take the field kinds from."""
    values: dict[str, Any] = {}
    if getattr(args, "params", ""):
        loaded = json.loads(Path(args.params).read_text(encoding="utf-8-sig"))
        if not isinstance(loaded, dict):
            raise ValueError("--params: an object of JSON 'field: value' is expected")
        values.update(loaded)
    for item in getattr(args, "set", None) or []:
        name, separator, text = item.partition("=")
        if not separator or not name.strip():
            raise ValueError(f"--set: name=value is expected, got {item!r}")
        values[name.strip()] = text
    return values


def answer(payload: dict[str, Any]) -> None:
    say(json.dumps(payload, ensure_ascii=False, default=str))


def command_options(args: argparse.Namespace) -> int:
    try:
        paths, manifest = project(args.root)
        node = model.find_node(manifest, args.operation)
        if node is None:
            return usage_error(f"the manifest has no operation {args.operation!r}")
        values = read_values(args, node)
        answer({"ok": True, **options_for(manifest, paths.root, args.operation, args.field, values, OptionCache())})
    except (OSError, ValueError) as error:
        return usage_error(str(error))
    except Exception as error:  # noqa: BLE001 - a provider's own words go to the caller, not a traceback
        answer({"ok": False, "error": f"{error.__class__.__name__}: {error}"})
        return EXIT_FAILED
    return EXIT_OK


def command_oktmo(args: argparse.Namespace) -> int:
    try:
        paths, _manifest = project(args.root)
        result = oktmo_action(paths.root, args.action, plain_values(args), args.kind)
    except (OSError, ValueError) as error:
        return usage_error(str(error))
    except Exception as error:  # noqa: BLE001
        answer({"ok": False, "error": f"{error.__class__.__name__}: {error}"})
        return EXIT_FAILED
    answer({"ok": True, "action": args.action, "result": result})
    return EXIT_OK


def command_serve(args: argparse.Namespace) -> int:
    """One JSON object a line in, one answer a line out; ends when the input does, or at "quit"."""
    try:
        paths, manifest = project(args.root)
    except ValueError as error:
        return usage_error(str(error))
    cache = OptionCache()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            answer({"ok": False, "error": "a line of JSON is expected"})
            continue
        name = str(request.get("command", ""))
        reply: dict[str, Any] = {"id": request.get("id")}
        try:
            if name == "quit":
                answer({**reply, "ok": True})
                return EXIT_OK
            if name == "ping":
                reply["ok"] = True
            elif name == "options":
                reply.update({"ok": True, **options_for(manifest, paths.root, str(request.get("operation", "")),
                                                        str(request.get("field", "")), dict(request.get("values") or {}), cache)})
            elif name == "oktmo":
                reply.update({"ok": True, "action": request.get("action"),
                              "result": oktmo_action(paths.root, str(request.get("action", "")),
                                                     dict(request.get("values") or {}), str(request.get("kind") or "region"))})
            elif name == "forget":
                # "options": only the lists built from the data are asked for again (a pin changed the order
                # of a list). Without it the Rosstat data changed: what was read of it is old too.
                cache.forget()
                if request.get("what") != "options":
                    from system_core.address_engine.oktmo_lookup import clear_oktmo_caches

                    clear_oktmo_caches()
                reply["ok"] = True
            else:
                reply.update({"ok": False, "error": f"no such command: {name!r}"})
        except Exception as error:  # noqa: BLE001 - the window is told, the loop goes on
            reply.update({"ok": False, "error": f"{error.__class__.__name__}: {error}"})
        answer(reply)
    return EXIT_OK


def command_stop_office(args: argparse.Namespace) -> int:
    answer(office_session.stop_session(Path(args.session_dir)))
    return EXIT_OK


# ---------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="address_cli", description="Audion Address Processor: the console command.")
    parser.add_argument("--root", default="", help="The project folder, if not the one this command lies in")
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("describe", help="The manifest as JSON: operations, fields, the layout of the window").set_defaults(func=command_describe)

    run = commands.add_parser("run", help="Run an operation of the manifest")
    run.add_argument("--operation", required=True, help="The id of the operation")
    run.add_argument("--source", default="", help="The source: a folder or one file; input by default")
    run.add_argument("--target", default="", help="The target; output by default")
    run.add_argument("--params", default="", help="A JSON file with the values of the fields by name")
    run.add_argument("--set", action="append", metavar="NAME=VALUE", help="The value of one field; may be repeated")
    run.add_argument("--result", default="", help="Where to write the outcome of the operation (JSON)")
    run.add_argument("--cancel-file", default="", help="A file that stops the operation when it appears")
    run.add_argument("--session-dir", default="", help="A folder for the records of the Excel and Word the operation starts")
    run.set_defaults(func=command_run)

    options = commands.add_parser("options", help="The options of a field that has a list from a provider")
    options.add_argument("--operation", required=True)
    options.add_argument("--field", required=True)
    options.add_argument("--params", default="")
    options.add_argument("--set", action="append", metavar="NAME=VALUE")
    options.set_defaults(func=command_options)

    oktmo = commands.add_parser("oktmo", help="An action of the OKTMO panel: " + ", ".join(OKTMO_ACTIONS))
    oktmo.add_argument("--action", required=True, choices=sorted(OKTMO_ACTIONS))
    oktmo.add_argument("--kind", default="region", choices=["region", "municipality"])
    oktmo.add_argument("--params", default="")
    oktmo.add_argument("--set", action="append", metavar="NAME=VALUE")
    oktmo.set_defaults(func=command_oktmo)

    commands.add_parser("serve", help="Options and OKTMO actions as lines of JSON on the standard input").set_defaults(func=command_serve)

    office = commands.add_parser("stop-office", help="Close the Excel and Word recorded in a session folder")
    office.add_argument("--session-dir", required=True)
    office.set_defaults(func=command_stop_office)

    commands.add_parser("version", help="The version").set_defaults(func=command_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return EXIT_USAGE if stop.code not in (0, None) else EXIT_OK
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
