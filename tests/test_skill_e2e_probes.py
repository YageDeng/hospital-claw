"""Tests for scripts/skill_e2e_probes.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from skill_e2e_probes import (  # type: ignore[import-not-found]
    probe_driver_command,
    probes_enabled,
    run_agent_probe,
)


class TestSkillE2EProbes(unittest.TestCase):
    def test_probes_enabled_requires_explicit_flag(self):
        self.assertFalse(probes_enabled({}))
        self.assertTrue(probes_enabled({"SKILL_E2E_ENABLE_PROBES": "1"}))

    def test_probe_driver_command_reads_environment(self):
        self.assertIsNone(probe_driver_command({}))
        self.assertEqual(
            probe_driver_command({"SKILL_E2E_AGENT_DRIVER": "python probe_driver.py"}),
            "python probe_driver.py",
        )

    def test_run_agent_probe_skips_without_driver(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outcome = run_agent_probe(
                "sample_probe",
                "Prompt",
                Path(tmpdir),
                env={"SKILL_E2E_ENABLE_PROBES": "1"},
            )

        self.assertEqual(outcome.status, "SKIP")
        self.assertIn("SKILL_E2E_AGENT_DRIVER", outcome.summary)

    def test_run_agent_probe_success_keeps_stable_artifact_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            driver_script = workspace_root / "probe_driver.py"
            driver_script.write_text(
                "import sys\nprint('probe ok')\n",
                encoding="utf-8",
            )

            outcome = run_agent_probe(
                "sample_probe",
                "Prompt",
                workspace_root,
                env={
                    "SKILL_E2E_ENABLE_PROBES": "1",
                    "SKILL_E2E_AGENT_DRIVER": f"{sys.executable} {driver_script}",
                },
            )

            self.assertEqual(outcome.status, "PASS")
            self.assertTrue(outcome.artifacts)
            self.assertTrue(Path(outcome.artifacts[0]).exists())


if __name__ == "__main__":
    unittest.main()
