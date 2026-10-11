"""The console command (`address_cli.cmd`, `system_core/cli.py`) and the model behind it.

The window of 1.9.0 built the parameters of a run itself. The model that replaces it
(`system_core/core/operation_model.py`) has to give the same parameters for every operation of the
manifest - that is checked here against the record made of that window while it still ran
(`tests/former_window_parameters.json`). The rest are the commands: describe, run, options, oktmo,
serve, stop-office, and the layout of the window the manifest has to fill.

Run it as a file or by `runtime\\python.exe -m pytest`; the command itself is always started as a
file (the embedded Python does not look for modules in the current folder).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_core import office_session  # noqa: E402
from system_core.core import operation_model as model  # noqa: E402
from system_core.core.jobs import JobContext  # noqa: E402
from system_core.core.manifest import load_manifest  # noqa: E402
from system_core.core.window_layout import load_layout, placed_operations, runnable_ids  # noqa: E402

CLI = ROOT / "system_core" / "cli.py"
RECORD = ROOT / "tests" / "former_window_parameters.json"
MANIFEST = load_manifest(ROOT / "config" / "tool_manifest.yaml")

# The fields the window on NiceGUI never drew or sent: five flagged `gui_hidden` and three its rule
# of words took for paths. Showing one is a decision of the owner, not a side effect.
FORMER_UNDRAWN = {
    ("run_address_aligner", "normalize_before_match"),
    ("run_address_aligner", "normalize_after_match"),
    ("run_address_aligner", "collect_before_match"),
    ("run_address_aligner", "collect_whole_document"),
    ("run_address_aligner", "city"),
    ("run_address_collection", "source_root"),
    ("run_reference_normalization", "reference_file"),
    ("run_reference_processing", "reference_file"),
}


def leaves(nodes) -> list[Any]:
    found: list[Any] = []
    for node in nodes:
        found.extend(leaves(node.children) if node.children else [node])
    return found


def run_cli(*arguments: str, root: Path | None = None, stdin: str | None = None) -> subprocess.CompletedProcess:
    command = [sys.executable, "-X", "utf8", str(CLI)]
    if root is not None:
        command += ["--root", str(root)]
    return subprocess.run(command + list(arguments), input=stdin, capture_output=True, text=True,
                          encoding="utf-8", cwd=str(ROOT.parent), timeout=120)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project folder of our own: the manifest and the layout, and a place for logs, reports and files."""
    root = tmp_path / "project"
    shutil.copytree(ROOT / "config", root / "config")
    # The keys of the owner stay out of the tests: the project of a test has two of its own.
    (root / "config" / "oktmo_current_keys.txt").write_text("город Тест\nТеста\n", encoding="utf-8")
    (root / "data").mkdir()
    shutil.copy2(ROOT / "data" / "regions_reference.yaml", root / "data" / "regions_reference.yaml")
    (root / "system_core").mkdir()
    return root


# --- the model against the window it replaces ---------------------------------------------------

def test_the_record_of_the_former_window_covers_every_operation() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    assert set(record) == set(runnable_ids(MANIFEST))
    assert len(record) == 14


def test_parameters_are_those_the_former_window_sent() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    checked = 0
    for operation_id, item in record.items():
        node = model.find_node(MANIFEST, operation_id)
        assert node is not None, operation_id
        assert [[model.field_id(f), model.raw_kind(f), model.field_default(f)] for f in node.fields] == \
            json.loads(json.dumps(item["fields"])), f"{operation_id}: the fields are not those the record was made of"
        for case in item["cases"]:
            built = json.loads(json.dumps(model.build_parameters(node, case["values"]), default=str))
            assert built == case["parameters"], f"{operation_id} / {case['case']}"
            checked += 1
    assert checked == 62


def test_undrawn_fields_are_the_eight_the_former_window_left_out() -> None:
    undrawn = {(node.id, model.field_id(field))
               for node in leaves(MANIFEST.operation_groups) for field in node.fields
               if model.route_of(field) or model.is_gui_hidden(field)}
    assert undrawn == FORMER_UNDRAWN


def test_every_field_names_its_block() -> None:
    missing = [(node.id, model.field_id(field)) for node in leaves(MANIFEST.operation_groups)
               for field in node.fields if not str(field.get("group") or "").strip()]
    assert missing == []


def test_a_field_with_a_shared_name_but_other_options_is_kept_per_operation() -> None:
    owners = {node.id for node in leaves(MANIFEST.operation_groups) for field in node.fields
              if model.field_id(field) == "target_column_header"}
    assert owners == {"run_address_collection", "run_address_aligner"}
    for node in leaves(MANIFEST.operation_groups):
        for field in node.fields:
            if model.field_id(field) == "target_column_header":
                assert field.get("scope") == "operation"


def test_fast_alignment_puts_normalization_back_to_its_defaults() -> None:
    node = model.find_node(MANIFEST, "run_address_aligner")
    fast = model.build_parameters(node, {"alignment_mode": "fast", "use_oktmo": False})
    assert fast["use_oktmo"] is True
    slow = model.build_parameters(node, {"alignment_mode": "normalized", "use_oktmo": False})
    assert slow["use_oktmo"] is False and slow["alignment_mode"] == "normalized"
    assert "city" not in slow  # never drawn, never sent


def test_a_field_drawn_only_in_one_mode_is_still_sent_in_the_other() -> None:
    node = model.find_node(MANIFEST, "run_address_aligner")
    field = next(f for f in node.fields if model.field_id(f) == "use_oktmo")
    assert field["draw_when"] == {"alignment_mode": "normalized"}
    assert model.describe_field(field)["drawn"] is True  # the window decides by draw_when what to show now
    assert model.build_parameters(node, {"alignment_mode": "fast"})["use_oktmo"] is True


def test_slot_order_gives_each_slot_its_own_place() -> None:
    field = next(f for f in model.find_node(MANIFEST, "run_address_collection").fields if model.field_id(f) == "slot_order")
    default = model.slot_order_default(field)
    assert sorted(default.values()) == list(range(1, len(default) + 1))
    # Two slots that ask for the same place, and a slot that asks for one beyond the last: every
    # slot still has a place of its own, from 1 to the number of slots (the rule of the old window).
    crowded = model.normalize_slot_order(field, {"street": 1, "house": 1, "premise": 99})
    assert sorted(crowded.values()) == list(range(1, len(default) + 1))
    assert model.normalize_slot_order(field, {}) == default
    assert model.normalize_slot_order(field, "not a mapping") == default
    # A run takes the order the same way: the console cannot give two slots one place.
    node = model.find_node(MANIFEST, "run_address_collection")
    sent = model.build_parameters(node, {"slot_order": {"street": 1, "house": 1, "premise": 99}})["slot_order"]
    assert sorted(sent.values()) == list(range(1, len(default) + 1))
    assert model.build_parameters(node, {})["slot_order"] == default


def test_the_preview_follows_the_slots_chosen() -> None:
    values = {"enabled_slots": ["street", "house"], "slot_order": {"house": 1, "street": 2}}
    assert model.slot_preview(values) == "д. 10 · ул. Ленина"
    assert model.slot_preview({}, "fallback") == "fallback"


def test_wrong_choices_and_unknown_names_are_named() -> None:
    node = model.find_node(MANIFEST, "run_address_aligner")
    assert model.wrong_choices(node, {"alignment_mode": "turbo"}) == ["alignment_mode=turbo"]
    assert model.wrong_choices(node, {"alignment_mode": "fast"}) == []
    assert model.unknown_values(node, {"nonsense": 1, "city": "x"}) == ["nonsense"]


def test_command_line_values_come_in_the_shape_of_the_field() -> None:
    node = model.find_node(MANIFEST, "run_table_comparison")
    by_id = {model.field_id(f): f for f in node.fields}
    assert model.coerce(by_id["start_row_a"], "9") == 9
    assert model.coerce(by_id["sort_addresses"], "yes") is True
    with pytest.raises(ValueError):
        model.coerce(by_id["sort_addresses"], "maybe")
    slots = next(f for f in model.find_node(MANIFEST, "run_address_collection").fields if model.field_id(f) == "slot_order")
    assert model.coerce(slots, '{"street": 1}') == {"street": 1}


# --- the layout of the window -------------------------------------------------------------------

def test_every_operation_has_a_place_in_the_window() -> None:
    layout = load_layout(ROOT / "config" / "window_layout.yaml", MANIFEST)
    placed = placed_operations(layout)
    assert set(runnable_ids(MANIFEST)) <= set(placed)
    assert [s["id"] for s in layout["sections"]] == ["sources", "collect", "reference", "match", "oktmo"]


def test_a_layout_that_leaves_an_operation_nowhere_is_refused(tmp_path: Path) -> None:
    text = (ROOT / "config" / "window_layout.yaml").read_text(encoding="utf-8")
    broken = tmp_path / "layout.yaml"
    broken.write_text(text.replace("  - package_output\n", ""), encoding="utf-8")
    with pytest.raises(ValueError, match="package_output"):
        load_layout(broken, MANIFEST)
    broken.write_text(text.replace("id: run_address_collection", "id: no_such_operation"), encoding="utf-8")
    with pytest.raises(ValueError, match="no_such_operation"):
        load_layout(broken, MANIFEST)


# --- the commands -------------------------------------------------------------------------------

def test_describe_tells_the_manifest_the_layout_and_the_slots() -> None:
    done = run_cli("describe")
    assert done.returncode == 0, done.stderr
    told = json.loads(done.stdout)
    assert {"tool", "nodes", "maintenance", "layout", "slots", "version", "paths"} <= set(told)
    aligner = next(n for n in told["nodes"] if n["id"] == "run_address_aligner")
    drawn = {f["id"] for f in aligner["fields"] if f["drawn"]}
    assert "city" not in drawn and "use_oktmo" in drawn
    assert told["slots"]["samples"]["street"] == "ул. Ленина"
    assert told["version"] == json.loads((ROOT / "config" / "version.json").read_text(encoding="utf-8"))["version"]


def test_run_executes_an_operation_and_tells_how_it_went(project: Path, tmp_path: Path) -> None:
    source, target = tmp_path / "in", tmp_path / "out"
    source.mkdir()
    (source / "one.xlsx").write_bytes(b"not a workbook, only a name")
    result = tmp_path / "result.json"
    done = run_cli("run", "--operation", "validate_input", "--source", str(source), "--target", str(target),
                   "--result", str(result), root=project)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert any(line.startswith("::address::") and '"started"' in line for line in lines)
    assert any(line.startswith("::address::") and '"finished"' in line for line in lines)
    assert any("one.xlsx" in line and not line.startswith("::address::") for line in lines)
    outcome = json.loads(result.read_text(encoding="utf-8"))
    assert outcome["outcome"] == "done" and outcome["ok"] is True
    assert outcome["data"]["count"] == 1
    assert Path(outcome["log"]).is_file() and Path(outcome["log"]).is_relative_to(project)


def test_run_refuses_a_wrong_call_and_runs_nothing(project: Path, tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    for arguments in (
        ["run", "--operation", "no_such_operation"],
        ["run", "--operation", "validate_input", "--set", "nonsense=1"],
        ["run", "--operation", "run_address_aligner", "--set", "alignment_mode=turbo"],
        ["run", "--operation", "validate_input", "--source", str(tmp_path / "missing")],
    ):
        done = run_cli(*arguments, root=project)
        assert done.returncode == 2, (arguments, done.stdout, done.stderr)
        assert "[ERR]" in done.stderr
    assert not (project / "report").exists() or not any((project / "report").iterdir())


def test_run_stops_when_the_cancel_file_is_there(project: Path, tmp_path: Path) -> None:
    target = tmp_path / "out"
    target.mkdir()
    (target / "a.txt").write_text("a", encoding="utf-8")
    (target / "b.txt").write_text("b", encoding="utf-8")
    cancel = tmp_path / "stop.flag"
    cancel.write_text("", encoding="utf-8")
    result = tmp_path / "result.json"
    done = run_cli("run", "--operation", "package_output", "--target", str(target), "--cancel-file", str(cancel),
                   "--result", str(result), root=project)
    assert done.returncode == 130, (done.stdout, done.stderr)
    assert json.loads(result.read_text(encoding="utf-8"))["outcome"] == "stopped"


def test_the_alignment_runs_to_its_end_through_the_command(project: Path, tmp_path: Path) -> None:
    """The services redirect `sys.stdout` into their log while the engine works. A line the command
    prints from inside that redirect went into the same log and came back to the command: the
    first run of the alignment grew one log line to 2 MB in twenty seconds and never ended."""
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "in"
    source.mkdir()
    book = openpyxl.Workbook()
    for row in (("г. Тюмень, ул. Альфа, д. 2", "Тюмень ул Альфа 2"), ("г. Тюмень, ул. Бета, д. 10", "Тюмень, улица Бета, дом 10")):
        book.active.append(row)
    book.save(source / "align.xlsx")
    result = tmp_path / "result.json"
    done = run_cli("run", "--operation", "run_address_aligner", "--source", str(source), "--target", str(tmp_path / "out"),
                   "--set", "ground_truth_column=A", "--set", "target_columns=B", "--set", "companion_mode=none",
                   "--set", "use_oktmo=false", "--result", str(result), root=project)
    assert done.returncode == 0, (done.stdout[-500:], done.stderr[-500:])
    outcome = json.loads(result.read_text(encoding="utf-8"))
    assert outcome["outcome"] == "done" and outcome["data"]["outputs"]
    assert Path(outcome["data"]["outputs"][0]).is_file()
    assert Path(outcome["log"]).stat().st_size < 200_000


def test_run_packs_the_result_without_a_stop(project: Path, tmp_path: Path) -> None:
    target = tmp_path / "out"
    target.mkdir()
    (target / "a.txt").write_text("a", encoding="utf-8")
    done = run_cli("run", "--operation", "package_output", "--target", str(target), root=project)
    assert done.returncode == 0, (done.stdout, done.stderr)
    assert (project / "release" / "address_aligner_output.zip").is_file()


def test_options_lists_the_sheets_of_the_workbook_chosen(project: Path, tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    book.active.title = "Первый"
    book.create_sheet("Второй")
    path = tmp_path / "a.xlsx"
    book.save(path)
    done = run_cli("options", "--operation", "run_table_comparison", "--field", "sheet_a",
                   "--set", f"file_a={path}", root=project)
    assert done.returncode == 0, done.stderr
    told = json.loads(done.stdout)
    assert told["ok"] is True
    assert [option["value"] for option in told["options"]] == ["Первый", "Второй"]


def test_options_of_a_field_without_a_provider_are_its_own(project: Path) -> None:
    done = run_cli("options", "--operation", "run_address_aligner", "--field", "alignment_mode", root=project)
    assert done.returncode == 0, done.stderr
    assert [o["value"] for o in json.loads(done.stdout)["options"]] == ["fast", "normalized"]


def test_the_oktmo_actions_are_all_there_and_take_what_they_are_given() -> None:
    import inspect

    from system_core import cli

    service = __import__(cli.SERVICE, fromlist=["x"])
    assert len(cli.OKTMO_ACTIONS) == 17
    for action, (name, takes) in cli.OKTMO_ACTIONS.items():
        parameters = list(inspect.signature(getattr(service, name)).parameters)
        assert parameters[0] == "root", action
        assert parameters[1:1 + len(takes)] == list(takes), action


def test_oktmo_reads_the_key_file_of_the_project(project: Path) -> None:
    done = run_cli("oktmo", "--action", "load_keys", root=project)
    assert done.returncode == 0, done.stderr
    told = json.loads(done.stdout)
    assert told["ok"] is True and told["result"]["keys"] == 2
    assert run_cli("oktmo", "--action", "pins_status", root=project).returncode == 0


def test_serve_answers_line_by_line_and_goes_on_after_an_error(project: Path) -> None:
    requests = "\n".join([
        json.dumps({"id": 1, "command": "ping"}),
        "this is not json",
        json.dumps({"id": 2, "command": "oktmo", "action": "load_keys"}),
        json.dumps({"id": 3, "command": "options", "operation": "run_address_aligner", "field": "alignment_mode"}),
        json.dumps({"id": 4, "command": "oktmo", "action": "nonsense"}),
        json.dumps({"id": 5, "command": "forget"}),
        json.dumps({"id": 6, "command": "quit"}),
    ]) + "\n"
    done = run_cli("serve", root=project, stdin=requests)
    assert done.returncode == 0, done.stderr
    replies = [json.loads(line) for line in done.stdout.splitlines()]
    assert len(replies) == 7
    assert replies[0] == {"id": 1, "ok": True}
    assert replies[1]["ok"] is False
    assert replies[2]["ok"] is True and replies[2]["result"]["keys"] == 2
    assert [o["value"] for o in replies[3]["options"]] == ["fast", "normalized"]
    assert replies[4]["ok"] is False and "nonsense" in replies[4]["error"]
    assert replies[5]["ok"] is True and replies[6]["ok"] is True


# --- the live line and the programs of Office ---------------------------------------------------

def test_the_live_line_goes_to_the_window_or_else_to_the_log(tmp_path: Path) -> None:
    lines: list[str] = []
    live: list[str] = []
    operation = model.find_node(MANIFEST, "validate_input").to_operation({})
    paths = __import__("system_core.core.paths", fromlist=["x"]).get_project_paths(ROOT)
    with_live = JobContext(paths, operation, tmp_path / "a.log", tmp_path, lines.append, None, None, live.append)
    with_live.live("bar 42%")
    assert live == ["bar 42%"] and lines == []
    without = JobContext(paths, operation, tmp_path / "b.log", tmp_path, lines.append)
    without.live("bar 43%")
    assert lines == ["bar 43%"]


def test_a_bar_rewritten_in_place_becomes_the_live_line(tmp_path: Path) -> None:
    from system_core.services import address_aligner_service as service

    live: list[str] = []
    lines: list[str] = []
    operation = model.find_node(MANIFEST, "validate_input").to_operation({})
    paths = __import__("system_core.core.paths", fromlist=["x"]).get_project_paths(ROOT)
    context = JobContext(paths, operation, tmp_path / "c.log", tmp_path, lines.append, None, None, live.append)
    stream = service._LogStream(context)
    stream.write("Stage 1:  10%|#         |\rStage 1: 100%|##########|\n")
    stream.flush()
    assert live == ["Stage 1:  10%|#         |"]
    assert lines == ["Stage 1: 100%|##########|"]


def test_a_recorded_process_that_is_not_ours_any_more_is_left_alone(tmp_path: Path, monkeypatch) -> None:
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        folder = tmp_path / "session"
        folder.mkdir()
        # A record that says this process is an Excel: it is not (another image), and it must live.
        (folder / f"excel-{sleeper.pid}.json").write_text(
            json.dumps({"kind": "excel", "pid": sleeper.pid, "started": office_session.started_at(sleeper.pid)}),
            encoding="utf-8")
        (folder / "word-1.json").write_text("not json", encoding="utf-8")
        assert office_session.stop_session(folder) == {"stopped": 0, "lost": 2}
        assert sleeper.poll() is None
        assert list(folder.iterdir()) == []
    finally:
        sleeper.kill()
        sleeper.wait()


def test_without_a_session_folder_nothing_is_written(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(office_session.SESSION_ENV, raising=False)

    class Client:
        def DispatchEx(self, program_id: str) -> str:  # noqa: N802 - the name of the COM call
            return "app:" + program_id

    assert office_session.dispatch_own(Client(), "Excel.Application") == "app:Excel.Application"
    assert office_session.stop_session(tmp_path / "nothing") == {"stopped": 0, "lost": 0}


OPERATION_THAT_STARTS_EXCEL = """
import sys, time
sys.path.insert(0, {root!r})
import pythoncom, win32com.client
from system_core import office_session
pythoncom.CoInitialize()
app = office_session.dispatch_own(win32com.client, "Excel.Application")
app.Visible = False
print("ready", flush=True)
time.sleep(120)
"""


@pytest.mark.skipif(os.name != "nt", reason="Excel is driven through COM on Windows")
def test_the_excel_of_a_killed_operation_is_closed(tmp_path: Path) -> None:
    """An operation starts its own Excel and is killed before it can quit it: `stop_session` closes that Excel."""
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Excel.Application\CLSID"))
    except OSError:
        pytest.skip("Microsoft Excel is not installed")
    folder = tmp_path / "session"
    before = office_session.running("excel")
    operation = subprocess.Popen(
        [sys.executable, "-c", OPERATION_THAT_STARTS_EXCEL.format(root=str(ROOT))],
        stdout=subprocess.PIPE, text=True, env={**os.environ, office_session.SESSION_ENV: str(folder)})
    appeared: set[int] = set()
    try:
        assert operation.stdout.readline().strip() == "ready"
        appeared = office_session.running("excel") - before
        records = list(folder.glob("excel-*.json"))
        assert len(appeared) == 1 and len(records) == 1
        assert records[0].name == f"excel-{next(iter(appeared))}.json"
        operation.kill()  # no Quit, no finally: what the window does when an operation does not stop in time
        operation.wait(timeout=10)
        assert office_session.running("excel") & appeared, "Excel should outlive its killed operation"
        assert office_session.stop_session(folder) == {"stopped": 1, "lost": 0}
        assert office_session.wait_until_gone("excel", appeared)
        assert list(folder.glob("*.json")) == []
    finally:
        if operation.poll() is None:
            operation.kill()
        for pid in office_session.running("excel") & appeared:  # whatever is left of our own test
            office_session._terminate(pid)
