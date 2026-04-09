"""Tests for scripts/review_db.py — TCM treatment review SQLite database."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from review_db import ReviewDB


class TestReviewDB(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = ReviewDB(self.tmp.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_init_session_returns_session_id(self):
        sid = self.db.init_session(image_count=3)
        self.assertIsInstance(sid, str)
        self.assertEqual(len(sid), 36)  # UUID4 format

    def test_init_session_stores_image_count(self):
        sid = self.db.init_session(image_count=5)
        status = self.db.get_status(sid)
        self.assertEqual(status["image_count"], 5)
        self.assertEqual(status["reviewed_count"], 0)

    def test_save_result_and_retrieve(self):
        sid = self.db.init_session(image_count=1)
        result = {
            "image_path": "test/image1.jpg",
            "image_index": 1,
            "form_index": 1,
            "patient_name": "张三",
            "form_date": "2026-01-15",
            "form_type": "治疗单",
            "overall_result": "合格",
            "dim1_result": "通过",
            "dim1_findings": "所有必填字段齐全",
            "dim2_result": "通过",
            "dim2_findings": "诊治一致",
            "dim3_result": "通过",
            "dim3_findings": "无针法叠加",
            "dim4_result": "通过",
            "dim4_findings": "加收项配对正确",
            "dim5_result": "通过",
            "dim5_findings": "价格符合一级标准",
            "dim6_result": "通过",
            "dim6_findings": "治疗记录完整",
            "dim7_result": "通过",
            "dim7_findings": "部位穴位标注清晰",
            "summary": "七大维度全部通过",
        }
        self.db.save_result(sid, result)
        results = self.db.get_results(sid)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["patient_name"], "张三")
        self.assertEqual(results[0]["overall_result"], "合格")

    def test_save_multiple_forms_from_one_image(self):
        sid = self.db.init_session(image_count=1)
        for form_idx in [1, 2]:
            result = {
                "image_path": "test/stacked.jpg",
                "image_index": 1,
                "form_index": form_idx,
                "patient_name": f"患者{form_idx}",
                "form_date": "2026-01-15",
                "form_type": "治疗申请单",
                "overall_result": "合格",
                "dim1_result": "通过",
                "dim1_findings": "",
                "dim2_result": "通过",
                "dim2_findings": "",
                "dim3_result": "通过",
                "dim3_findings": "",
                "dim4_result": "通过",
                "dim4_findings": "",
                "dim5_result": "通过",
                "dim5_findings": "",
                "dim6_result": "通过",
                "dim6_findings": "",
                "dim7_result": "通过",
                "dim7_findings": "",
                "summary": "通过",
            }
            self.db.save_result(sid, result)
        results = self.db.get_results(sid)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["form_index"], 1)
        self.assertEqual(results[1]["form_index"], 2)

    def test_status_tracks_reviewed_images(self):
        sid = self.db.init_session(image_count=3)
        self.assertEqual(self.db.get_status(sid)["reviewed_count"], 0)

        for i in range(1, 4):
            result = {
                "image_path": f"test/img{i}.jpg",
                "image_index": i,
                "form_index": 1,
                "patient_name": f"P{i}",
                "form_date": "2026-01-01",
                "form_type": "治疗单",
                "overall_result": "合格",
                "dim1_result": "通过",
                "dim1_findings": "",
                "dim2_result": "通过",
                "dim2_findings": "",
                "dim3_result": "通过",
                "dim3_findings": "",
                "dim4_result": "通过",
                "dim4_findings": "",
                "dim5_result": "通过",
                "dim5_findings": "",
                "dim6_result": "通过",
                "dim6_findings": "",
                "dim7_result": "通过",
                "dim7_findings": "",
                "summary": "",
            }
            self.db.save_result(sid, result)

        status = self.db.get_status(sid)
        self.assertEqual(status["reviewed_count"], 3)
        self.assertTrue(status["is_complete"])

    def test_status_not_complete_when_partial(self):
        sid = self.db.init_session(image_count=3)
        result = {
            "image_path": "test/img1.jpg",
            "image_index": 1,
            "form_index": 1,
            "patient_name": "P1",
            "form_date": "2026-01-01",
            "form_type": "治疗单",
            "overall_result": "合格",
            "dim1_result": "通过",
            "dim1_findings": "",
            "dim2_result": "通过",
            "dim2_findings": "",
            "dim3_result": "通过",
            "dim3_findings": "",
            "dim4_result": "通过",
            "dim4_findings": "",
            "dim5_result": "通过",
            "dim5_findings": "",
            "dim6_result": "通过",
            "dim6_findings": "",
            "dim7_result": "通过",
            "dim7_findings": "",
            "summary": "",
        }
        self.db.save_result(sid, result)
        status = self.db.get_status(sid)
        self.assertEqual(status["reviewed_count"], 1)
        self.assertFalse(status["is_complete"])

    def test_generate_summary_report(self):
        sid = self.db.init_session(image_count=2)
        for i, (name, result_val) in enumerate(
            [("张三", "合格"), ("李四", "不合格")], start=1
        ):
            result = {
                "image_path": f"test/img{i}.jpg",
                "image_index": i,
                "form_index": 1,
                "patient_name": name,
                "form_date": "2026-01-15",
                "form_type": "治疗单",
                "overall_result": result_val,
                "dim1_result": "通过",
                "dim1_findings": "齐全",
                "dim2_result": "通过" if result_val == "合格" else "不通过",
                "dim2_findings": "一致" if result_val == "合格" else "诊治不符",
                "dim3_result": "通过",
                "dim3_findings": "",
                "dim4_result": "通过",
                "dim4_findings": "",
                "dim5_result": "通过",
                "dim5_findings": "",
                "dim6_result": "通过",
                "dim6_findings": "",
                "dim7_result": "通过",
                "dim7_findings": "",
                "summary": "全部通过" if result_val == "合格" else "诊治不一致",
            }
            self.db.save_result(sid, result)

        report = self.db.generate_summary(sid)
        self.assertIn("张三", report)
        self.assertIn("李四", report)
        self.assertIn("合格", report)
        self.assertIn("不合格", report)
        self.assertIn("合格率", report)

    def test_get_results_ordered_by_image_and_form_index(self):
        sid = self.db.init_session(image_count=2)
        for img_i in [2, 1]:
            result = {
                "image_path": f"test/img{img_i}.jpg",
                "image_index": img_i,
                "form_index": 1,
                "patient_name": f"P{img_i}",
                "form_date": "2026-01-01",
                "form_type": "治疗单",
                "overall_result": "合格",
                "dim1_result": "通过",
                "dim1_findings": "",
                "dim2_result": "通过",
                "dim2_findings": "",
                "dim3_result": "通过",
                "dim3_findings": "",
                "dim4_result": "通过",
                "dim4_findings": "",
                "dim5_result": "通过",
                "dim5_findings": "",
                "dim6_result": "通过",
                "dim6_findings": "",
                "dim7_result": "通过",
                "dim7_findings": "",
                "summary": "",
            }
            self.db.save_result(sid, result)
        results = self.db.get_results(sid)
        self.assertEqual(results[0]["image_index"], 1)
        self.assertEqual(results[1]["image_index"], 2)

    def test_invalid_session_raises(self):
        with self.assertRaises(ValueError):
            self.db.get_status("nonexistent-session-id")

    def test_export_json(self):
        sid = self.db.init_session(image_count=1)
        result = {
            "image_path": "test/img1.jpg",
            "image_index": 1,
            "form_index": 1,
            "patient_name": "测试",
            "form_date": "2026-01-01",
            "form_type": "治疗单",
            "overall_result": "合格",
            "dim1_result": "通过",
            "dim1_findings": "",
            "dim2_result": "通过",
            "dim2_findings": "",
            "dim3_result": "通过",
            "dim3_findings": "",
            "dim4_result": "通过",
            "dim4_findings": "",
            "dim5_result": "通过",
            "dim5_findings": "",
            "dim6_result": "通过",
            "dim6_findings": "",
            "dim7_result": "通过",
            "dim7_findings": "",
            "summary": "通过",
        }
        self.db.save_result(sid, result)
        exported = self.db.export_json(sid)
        data = json.loads(exported)
        self.assertEqual(data["session_id"], sid)
        self.assertEqual(len(data["results"]), 1)


if __name__ == "__main__":
    unittest.main()

