"""Tests for skills/sh-yb-policy-monitor/scripts/fetch_policies.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "skills",
        "sh-yb-policy-monitor",
        "scripts",
    ),
)

from fetch_policies import main, resolve_save_dir, save_article  # type: ignore[import-not-found]


class TestFetchPolicies(unittest.TestCase):
    def test_main_returns_non_zero_when_channel_fetch_fails(self):
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            sys, "argv", ["fetch_policies.py", "--save-dir", tmpdir]
        ), patch(
            "fetch_policies.CHANNELS",
            [{"id": "ybdt", "name": "医保动态", "url": "https://ybj.sh.gov.cn/ybdt/index.html"}],
        ), patch(
            "fetch_policies.fetch_page",
            side_effect=Exception("boom"),
        ), patch(
            "sys.stdout", stdout
        ), patch(
            "sys.stderr", stderr
        ):
            exit_code = main()

        self.assertEqual(exit_code, 1)
        self.assertIn("获取失败", stderr.getvalue())

    def test_main_returns_zero_when_channels_complete_without_errors(self):
        stdout = StringIO()
        stderr = StringIO()

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            sys, "argv", ["fetch_policies.py", "--save-dir", tmpdir]
        ), patch(
            "fetch_policies.CHANNELS",
            [{"id": "ybdt", "name": "医保动态", "url": "https://ybj.sh.gov.cn/ybdt/index.html"}],
        ), patch(
            "fetch_policies.fetch_page",
            return_value="<html></html>",
        ), patch(
            "sys.stdout", stdout
        ), patch(
            "sys.stderr", stderr
        ):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")

    def test_resolve_save_dir_prefers_explicit_then_env_then_default(self):
        with patch.dict(os.environ, {"SH_YB_POLICY_SAVE_DIR": r"C:\env-dir"}, clear=False):
            explicit = resolve_save_dir(r"C:\explicit-dir")
            from_env = resolve_save_dir(None)

        self.assertTrue(str(explicit).endswith("explicit-dir"))
        self.assertTrue(str(from_env).endswith("env-dir"))

    def test_resolve_save_dir_uses_runtime_relative_default_when_no_override(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {}, clear=True):
            fake_root = Path(tmpdir) / "agent-home"
            fake_script = fake_root / "skills" / "sh-yb-policy-monitor" / "scripts" / "fetch_policies.py"
            fake_script.parent.mkdir(parents=True, exist_ok=True)
            fake_script.write_text("# test\n", encoding="utf-8")

            with patch("fetch_policies.__file__", str(fake_script)):
                resolved = resolve_save_dir(None)

        self.assertEqual(resolved, (fake_root / "data" / "sh-yb-policies").resolve())

    def test_save_article_honors_explicit_save_dir(self):
        article = {
            "title": "关于开展飞行检查的通知",
            "date": "2026-04-11",
            "url": "https://ybj.sh.gov.cn/example.html",
        }
        channel = {"id": "ybdt", "name": "医保动态"}

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            saved_path = save_article(
                article,
                channel,
                "正文内容",
                save_dir=save_dir,
            )

            self.assertIsNotNone(saved_path)
            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.parent, save_dir)
            self.assertIn("# 关于开展飞行检查的通知", saved_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
