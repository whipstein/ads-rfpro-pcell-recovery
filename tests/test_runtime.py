from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rfpro_pcell_recovery import (
    force_active_rfpro_geometry_update,
    refresh_active_rfpro_layout,
)


class _Parameters:
    def __init__(self, formulas: dict[str, str]) -> None:
        self._formulas = formulas

    def names(self) -> list[str]:
        return list(self._formulas)

    def formula(self, name: str) -> str:
        return self._formulas[name]


class _Layout:
    def __init__(self) -> None:
        self.refresh_count = 0
        self.received_updates: dict[str, str] | None = None

    def refresh(self) -> None:
        self.refresh_count += 1

    def _designParameters(self) -> dict[str, str]:
        # Reproduce the ADS 2026 U2.1 observation: this private map can remain
        # empty even while activeProject.parameters contains the UI formulas.
        return {}

    def _updateDesignParameters(self, updates: dict[str, str]) -> str:
        self.received_updates = dict(updates)
        return "native update accepted"


class _Project:
    def __init__(self, formulas: dict[str, str]) -> None:
        self.layout = _Layout()
        self.parameters = _Parameters(formulas)
        self.load_count = 0

    def _loadOaParametersFromDesignSpec(self) -> None:
        self.load_count += 1


def _empro(formulas: dict[str, str]) -> SimpleNamespace:
    project = _Project(formulas)
    gui = SimpleNamespace(processEvents=lambda: None)
    return SimpleNamespace(activeProject=project, gui=gui)


class RuntimeTests(unittest.TestCase):
    def test_targeted_geometry_update_uses_current_formulas(self) -> None:
        empro = _empro({"p1": "1.2 mm", "p2": "0.35 mm", "other": "7"})
        with patch.dict(sys.modules, {"empro": empro}):
            report = force_active_rfpro_geometry_update(("p1", "p2"))

        expected = {"p1": "1.2 mm", "p2": "0.35 mm"}
        self.assertEqual(empro.activeProject.layout.received_updates, expected)
        self.assertEqual(report["updates"], expected)
        self.assertEqual(report["native_status"], "native update accepted")
        self.assertEqual(empro.activeProject.load_count, 1)
        self.assertEqual(empro.activeProject.layout.refresh_count, 0)

    def test_explicit_geometry_updates_are_passed_unchanged(self) -> None:
        empro = _empro({"p1": "old"})
        updates = {"p1": "1.3 mm"}
        with patch.dict(sys.modules, {"empro": empro}):
            report = force_active_rfpro_geometry_update(updates=updates)

        self.assertEqual(empro.activeProject.layout.received_updates, updates)
        self.assertEqual(report["updates"], updates)

    def test_single_parameter_name_string_is_not_split(self) -> None:
        empro = _empro({"p1": "1.2 mm"})
        with patch.dict(sys.modules, {"empro": empro}):
            report = force_active_rfpro_geometry_update("p1")

        self.assertEqual(report["updates"], {"p1": "1.2 mm"})

    def test_metadata_refresh_uses_project_list_not_private_map(self) -> None:
        empro = _empro({"p1": "1.2 mm", "p2": "0.35 mm"})
        with patch.dict(sys.modules, {"empro": empro}):
            formulas = refresh_active_rfpro_layout()

        self.assertEqual(formulas, {"p1": "1.2 mm", "p2": "0.35 mm"})
        self.assertEqual(empro.activeProject.layout.refresh_count, 1)
        self.assertEqual(empro.activeProject.load_count, 1)


if __name__ == "__main__":
    unittest.main()
