"""Tests for scripts/update_kb_manifest.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import update_kb_manifest


class TestUpdateKBManifest(unittest.TestCase):
    def test_default_scan_dirs_include_native_source_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_md = root / "docs" / "医院材料学习" / "本地规则说明.md"
            source_md.parent.mkdir(parents=True)
            source_md.write_text("# 本地规则说明\n", encoding="utf-8")

            scan_dirs = [root / path for path in update_kb_manifest.DEFAULT_SCAN_DIRS]
            entries = update_kb_manifest.build_entries(root, scan_dirs)
            paths = {entry["path"] for entry in entries}

            self.assertIn("docs/医院材料学习/本地规则说明.md", paths)

    def test_default_scan_dirs_include_wechat_monitor_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            article_dir = (
                root
                / "docs"
                / "医院材料学习"
                / "公众号每日监测"
                / "2026-04-11"
                / "上海医保"
                / "01_收费调整通知"
            )
            article_dir.mkdir(parents=True)
            markdown_path = article_dir / "收费调整通知.md"
            markdown_path.write_text("# 收费调整通知\n", encoding="utf-8")

            scan_dirs = [root / path for path in update_kb_manifest.DEFAULT_SCAN_DIRS]
            entries = update_kb_manifest.build_entries(root, scan_dirs)
            paths = {entry["path"] for entry in entries}

            self.assertIn(
                "docs/医院材料学习/公众号每日监测/2026-04-11/上海医保/01_收费调整通知/收费调整通知.md",
                paths,
            )

    def test_default_scan_dirs_skip_non_markdown_under_source_docs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            binary_doc = root / "docs" / "医院材料学习" / "培训材料.pdf"
            binary_doc.parent.mkdir(parents=True)
            binary_doc.write_bytes(b"%PDF-1.7")

            scan_dirs = [root / path for path in update_kb_manifest.DEFAULT_SCAN_DIRS]
            entries = update_kb_manifest.build_entries(root, scan_dirs)
            paths = {entry["path"] for entry in entries}

            self.assertNotIn("docs/医院材料学习/培训材料.pdf", paths)


if __name__ == "__main__":
    unittest.main()
