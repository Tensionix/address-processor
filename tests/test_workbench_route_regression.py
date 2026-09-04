from __future__ import annotations

import asyncio
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_core.core.manifest import Operation
from system_core.ui_nicegui import app as gui_app


class WorkbenchRouteRegressionTests(unittest.TestCase):
    def test_active_project_paths_uses_current_workbench_route(self) -> None:
        source = Path(r"S:\Release")
        target = Path(r"S:\TOOLS")
        with (
            patch.object(gui_app, "current_source_path", return_value=source),
            patch.object(gui_app, "current_target_path", return_value=target),
        ):
            routed = gui_app.active_project_paths()

        self.assertEqual(routed.input, source)
        self.assertEqual(routed.output, target)
        self.assertEqual(routed.root, gui_app.paths.root)

    def test_start_operation_passes_active_workbench_paths(self) -> None:
        source = Path(r"S:\Release")
        target = Path(r"S:\TOOLS")
        captured: dict[str, object] = {}

        async def capture_io_bound(callback, *args, **_kwargs):
            if callback is gui_app.execute_operation:
                captured["paths"] = args[0]
            return SimpleNamespace(ok=True, data={}, message="ok")

        operation = Operation(
            id="workbench_route_probe",
            title="Workbench route probe",
            description="",
            service="tests:probe",
        )
        gui_app.state["running"] = False
        with ExitStack() as stack:
            stack.enter_context(patch.object(gui_app, "current_source_path", return_value=source))
            stack.enter_context(patch.object(gui_app, "current_target_path", return_value=target))
            stack.enter_context(patch.object(gui_app, "set_last_artifacts", return_value=None))
            stack.enter_context(patch.object(gui_app, "refresh_artifact_panel_safely", return_value=None))
            stack.enter_context(patch.object(gui_app, "safe_notify", return_value=None))
            stack.enter_context(patch.object(gui_app.run, "io_bound", side_effect=capture_io_bound))
            asyncio.run(gui_app.start_operation(operation))

        routed = captured["paths"]
        self.assertEqual(routed.input, source)
        self.assertEqual(routed.output, target)


if __name__ == "__main__":
    unittest.main()
