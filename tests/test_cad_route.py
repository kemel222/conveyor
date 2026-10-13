"""Регрессии маршрута CAD: только Codex/Astra, с высоким reasoning."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import llm


class AstraCadRoute(unittest.TestCase):
    def test_command_uses_astra_high_and_workspace_write(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            seen = {}

            def fake_run(cmd, cwd, log_prefix, timeout, stdin_text=None, stall=None, watch=None):
                seen.update(cmd=cmd, cwd=cwd, timeout=timeout, stdin=stdin_text, stall=stall)
                return llm.RunResult(True, 0, 0.0, log_prefix.with_suffix(".stdout.txt"),
                                     log_prefix.with_suffix(".stderr.txt"))

            with patch.object(llm, "find_exe", return_value="codex.exe"), patch.object(llm, "run_bounded", side_effect=fake_run):
                result = llm.astra_cad_task("полное задание", work, {"astra_model": "gpt-6-astra",
                    "astra_reasoning_effort": "high", "astra_timeout": 17, "astra_stall": 8}, "astra1")

            self.assertTrue(result.ok)
            self.assertEqual(seen["cmd"][0:2], ["codex.exe", "exec"])
            # В установленном CLI --approve-for-me включает автоматическое
            # подтверждение в workspace-write и несовместим с явным --sandbox.
            self.assertIn("--approve-for-me", seen["cmd"])
            self.assertIn("gpt-6-astra", seen["cmd"])
            self.assertIn("model_reasoning_effort=high", seen["cmd"])
            self.assertEqual(seen["timeout"], 17)
            self.assertEqual(seen["stall"], 8)
            self.assertTrue((work / "astra1.prompt.md").is_file())

    def test_legacy_gemini_route_is_gone(self):
        source = Path(__file__).parents[1].joinpath("core", "llm.py").read_text(encoding="utf-8")
        self.assertNotIn("gemini_task", source)
        self.assertNotIn("agy", source)


if __name__ == "__main__":
    unittest.main()
