"""Tests for scripts/wechat_article_pipeline.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from io import BytesIO, TextIOWrapper
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from wechat_article_pipeline import (  # type: ignore[import-not-found]
    ArticleBundle,
    main,
    build_kb_refresh_commands,
    build_article_output_dir,
    build_monitor_report,
    classify_article,
    process_article_urls,
    publish_date_string,
    save_article_bundle,
)


class TestWeChatArticlePipeline(unittest.TestCase):
    def test_classify_article_marks_policy_alert_as_p0(self):
        result = classify_article(
            title="国家医保局发布实施细则，4月1日施行",
            body_text="涉及收费项目调整，要求门诊同步落实。",
            account_name="国家医保局",
        )

        self.assertEqual(result["priority"], "P0")
        self.assertIn("4月1日施行", result["matched_keywords"])

    def test_classify_article_marks_promotional_content_as_p4(self):
        result = classify_article(
            title="春季养生课程推广",
            body_text="节气养生、食疗方与课程优惠报名。",
            account_name="健康课堂",
        )

        self.assertEqual(result["priority"], "P4")
        self.assertTrue(result["matched_keywords"])

    def test_classify_article_marks_drg_dip_content_as_p1(self):
        result = classify_article(
            title="DIP 支付改革与 DRG 结算提醒",
            body_text="门诊需关注病种付费与分值调整。",
            account_name="管理内参",
        )

        self.assertEqual(result["priority"], "P1")
        self.assertIn("DIP", result["matched_keywords"])
        self.assertIn("DRG", result["matched_keywords"])

    def test_classify_article_uses_title_only_for_priority(self):
        result = classify_article(
            title="普通晨报",
            body_text="这里提到了 DIP 支付改革与 DRG 结算。",
            account_name="管理内参",
        )

        self.assertEqual(result["priority"], "P3")

    def test_classify_article_prefers_p3_for_professional_training_content(self):
        result = classify_article(
            title="继续教育培训课程通知",
            body_text="报名通道已开放。",
            account_name="行业学堂",
        )

        self.assertEqual(result["priority"], "P3")

    def test_build_article_output_dir_uses_date_account_and_sequence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir)

            first = build_article_output_dir(
                output_root=output_root,
                publish_time="2026-04-11 08:00:00",
                account_name="上海医保",
                title="收费调整通知",
            )
            second = build_article_output_dir(
                output_root=output_root,
                publish_time="2026-04-11 09:30:00",
                account_name="上海医保",
                title="飞检启动通知",
            )

            self.assertEqual(
                first.relative_to(output_root).as_posix(),
                "2026-04-11/上海医保/01_收费调整通知",
            )
            self.assertEqual(
                second.relative_to(output_root).as_posix(),
                "2026-04-11/上海医保/02_飞检启动通知",
            )

    def test_save_article_bundle_writes_markdown_metadata_and_optional_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir)
            article = ArticleBundle(
                title="医保结算规则提醒",
                account_name="医保飞检",
                publish_time="2026-04-11 08:00:00",
                source_url="https://mp.weixin.qq.com/s/example",
                markdown_body="第一条重点\n\n第二条重点\n",
                cleaned_html="<div><p>第一条重点</p></div>",
                priority="P1",
                matched_keywords=["医保", "结算", "规则"],
                summary_lines=["第一条重点", "第二条重点"],
            )

            saved = save_article_bundle(article, output_root, save_html=True)

            markdown_path = Path(saved["markdown_path"])
            metadata_path = Path(saved["metadata_path"])
            html_path = Path(saved["html_path"])

            self.assertTrue(markdown_path.exists())
            self.assertTrue(metadata_path.exists())
            self.assertTrue(html_path.exists())

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["source_account"], "医保飞检")
            self.assertEqual(metadata["priority"], "P1")
            self.assertEqual(
                metadata["local_path"],
                markdown_path.parent.as_posix(),
            )

    def test_build_monitor_report_groups_by_priority(self):
        report = build_monitor_report(
            [
                {
                    "title": "紧急通知",
                    "priority": "P0",
                    "local_path": "docs/医院材料学习/公众号每日监测/2026-04-11/a/01_x",
                },
                {
                    "title": "合规解读",
                    "priority": "P1",
                    "local_path": "docs/医院材料学习/公众号每日监测/2026-04-11/b/01_y",
                },
                {
                    "title": "运营案例",
                    "priority": "P2",
                    "local_path": "docs/医院材料学习/公众号每日监测/2026-04-11/c/01_z",
                },
                {
                    "title": "养生软文",
                    "priority": "P4",
                    "local_path": "docs/医院材料学习/公众号每日监测/2026-04-11/d/01_q",
                },
            ]
        )

        self.assertEqual(len(report["urgent_alerts"]), 1)
        self.assertEqual(len(report["daily_summary"]), 1)
        self.assertEqual(len(report["weekly_candidates"]), 1)
        self.assertEqual(len(report["archive_trail"]), 1)

    def test_process_article_urls_continues_after_single_url_failure(self):
        successes = [
            {
                "title": "文章一",
                "priority": "P1",
                "local_path": "docs/医院材料学习/公众号每日监测/2026-04-11/a/01_x",
            },
            {
                "title": "文章二",
                "priority": "P0",
                "local_path": "docs/医院材料学习/公众号每日监测/2026-04-11/b/01_y",
            },
        ]

        with patch(
            "wechat_article_pipeline.process_article_url",
            side_effect=[successes[0], ValueError("bad url"), successes[1]],
        ):
            result = process_article_urls(
                urls=["u1", "bad", "u2"],
                output_root=Path("unused"),
                timeout=30,
                save_html=False,
            )

        self.assertEqual(result["articles"], successes)
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(result["failures"][0]["url"], "bad")
        self.assertIn("bad url", result["failures"][0]["error"])

    def test_build_kb_refresh_commands_uses_active_python(self):
        commands = build_kb_refresh_commands()

        self.assertEqual(commands[0][0], sys.executable)
        self.assertEqual(commands[0][1:], ["scripts/update_kb_manifest.py"])

    def test_publish_date_string_supports_chinese_date_format(self):
        self.assertEqual(publish_date_string("2026年04月11日 08:00"), "2026-04-11")

    def test_main_does_not_crash_on_gbk_stdout(self):
        stdout_buffer = BytesIO()
        stdout_stream = TextIOWrapper(stdout_buffer, encoding="gbk")

        saved_articles = [
            {
                "priority": "P1",
                "source_account": "account",
                "title": "title",
                "local_path": "temp/out",
            }
        ]
        report = {
            "urgent_alerts": [],
            "daily_summary": [{}],
            "weekly_candidates": [],
            "archive_trail": [],
        }

        with patch.object(
            sys,
            "argv",
            ["wechat_article_pipeline.py", "https://mp.weixin.qq.com/s/example"],
        ), patch(
            "wechat_article_pipeline.process_article_urls",
            return_value={"articles": saved_articles, "failures": []},
        ), patch(
            "wechat_article_pipeline.build_monitor_report",
            return_value=report,
        ), patch(
            "wechat_article_pipeline.write_monitor_report",
            return_value=Path("temp/report.json"),
        ), patch(
            "sys.stdout",
            stdout_stream,
        ):
            main()

        stdout_stream.flush()
        output = stdout_buffer.getvalue().decode("gbk")
        self.assertIn("WeChat monitor run complete", output)


if __name__ == "__main__":
    unittest.main()
