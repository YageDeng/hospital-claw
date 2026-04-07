# TCM Treatment Review Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a concurrent image review pipeline where one subagent handles one treatment form image at a time, saves structured results to SQLite, and a main agent summarizes all results — eliminating image-conclusion mismatches and handling multi-form images correctly.

**Architecture:** Main agent receives a batch of images → initializes a SQLite review session → dispatches one Task subagent per image (each subagent: detects form boundaries, filters irrelevant content, reviews each form against 7 dimensions, saves to SQLite) → main agent reads SQLite and generates a unified summary report.

**Tech Stack:** Python 3.10+ (sqlite3 stdlib), Cursor Task subagents, image analysis via vision model

**Spec:** This plan addresses three problems in the current `tcm-treatment-review` skill: (1) multi-image batch processing causes image-conclusion mismatches, (2) images with multiple stacked forms need per-form isolation, (3) no persistent storage or concurrent review pipeline.

**Dependency:** This plan produces the unified v2 SKILL.md for `tcm-treatment-review` that is referenced by the KB plan (`docs/superpowers/plans/2026-04-07-knowledge-base-implementation.md`, Task 10). The v2 includes both pipeline features AND KB/MCP integration. Execute this plan's Tasks 1-5 as part of the KB plan's Task 10.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/review_db.py` | SQLite database: schema, session management, result storage, summary generation. Zero external dependencies (stdlib only). |
| `tests/test_review_db.py` | Unit tests for all DB operations |
| `skills/tcm-treatment-review/SKILL.md` | Updated skill with concurrent pipeline instructions, single-image-per-subagent protocol, multi-form detection |
| `.gitignore` | Root gitignore (new) — ignore `data/*.db` and other runtime artifacts |

**Files unchanged:**
- `skills/tcm-treatment-review/standards.md` — pricing reference (unchanged)
- `skills/tcm-treatment-review/examples.md` — patterns reference (unchanged)

---

## Task 1: Create Root .gitignore

The project has no root `.gitignore`. The review pipeline will create SQLite files in `data/` that should not be committed.

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Create .gitignore**

Create `.gitignore` at the project root:

```gitignore
# Runtime data
data/
*.db
*.db-shm
*.db-wal

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/

# IDE
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Temp files from review pipeline
tmp_review_*.json
```

- [ ] **Step 2: Commit**

```powershell
git add .gitignore
git commit -m "chore: add root .gitignore for runtime data and Python artifacts"
```

---

## Task 2: Write Failing Tests for review_db.py

Write the test file first. All DB operations are tested before implementation.

**Files:**
- Create: `tests/test_review_db.py`

- [ ] **Step 1: Create tests directory**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p tests
```

- [ ] **Step 2: Write the test file**

Create `tests/test_review_db.py`:

```python
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
                "dim1_result": "通过", "dim1_findings": "",
                "dim2_result": "通过", "dim2_findings": "",
                "dim3_result": "通过", "dim3_findings": "",
                "dim4_result": "通过", "dim4_findings": "",
                "dim5_result": "通过", "dim5_findings": "",
                "dim6_result": "通过", "dim6_findings": "",
                "dim7_result": "通过", "dim7_findings": "",
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
                "dim1_result": "通过", "dim1_findings": "",
                "dim2_result": "通过", "dim2_findings": "",
                "dim3_result": "通过", "dim3_findings": "",
                "dim4_result": "通过", "dim4_findings": "",
                "dim5_result": "通过", "dim5_findings": "",
                "dim6_result": "通过", "dim6_findings": "",
                "dim7_result": "通过", "dim7_findings": "",
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
            "dim1_result": "通过", "dim1_findings": "",
            "dim2_result": "通过", "dim2_findings": "",
            "dim3_result": "通过", "dim3_findings": "",
            "dim4_result": "通过", "dim4_findings": "",
            "dim5_result": "通过", "dim5_findings": "",
            "dim6_result": "通过", "dim6_findings": "",
            "dim7_result": "通过", "dim7_findings": "",
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
                "dim3_result": "通过", "dim3_findings": "",
                "dim4_result": "通过", "dim4_findings": "",
                "dim5_result": "通过", "dim5_findings": "",
                "dim6_result": "通过", "dim6_findings": "",
                "dim7_result": "通过", "dim7_findings": "",
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
                "dim1_result": "通过", "dim1_findings": "",
                "dim2_result": "通过", "dim2_findings": "",
                "dim3_result": "通过", "dim3_findings": "",
                "dim4_result": "通过", "dim4_findings": "",
                "dim5_result": "通过", "dim5_findings": "",
                "dim6_result": "通过", "dim6_findings": "",
                "dim7_result": "通过", "dim7_findings": "",
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
            "dim1_result": "通过", "dim1_findings": "",
            "dim2_result": "通过", "dim2_findings": "",
            "dim3_result": "通过", "dim3_findings": "",
            "dim4_result": "通过", "dim4_findings": "",
            "dim5_result": "通过", "dim5_findings": "",
            "dim6_result": "通过", "dim6_findings": "",
            "dim7_result": "通过", "dim7_findings": "",
            "summary": "通过",
        }
        self.db.save_result(sid, result)
        exported = self.db.export_json(sid)
        data = json.loads(exported)
        self.assertEqual(data["session_id"], sid)
        self.assertEqual(len(data["results"]), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python -m pytest tests/test_review_db.py -v
```

Expected: All tests FAIL with `ModuleNotFoundError: No module named 'review_db'`

- [ ] **Step 4: Commit**

```powershell
git add tests/test_review_db.py
git commit -m "test: add failing tests for review pipeline SQLite database"
```

---

## Task 3: Implement review_db.py

Implement the SQLite database module to make all tests pass.

**Files:**
- Create: `scripts/review_db.py`

- [ ] **Step 1: Create scripts directory**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p scripts
```

- [ ] **Step 2: Write review_db.py**

Create `scripts/review_db.py`:

```python
"""TCM treatment review pipeline — SQLite database for storing review results.

Usage as CLI:
    python scripts/review_db.py init --image-count 5
    python scripts/review_db.py save --session <ID> --json-file result.json
    python scripts/review_db.py status --session <ID>
    python scripts/review_db.py summary --session <ID>
    python scripts/review_db.py export --session <ID>

Usage as module:
    from review_db import ReviewDB
    db = ReviewDB("data/reviews.db")
    sid = db.init_session(image_count=5)
    db.save_result(sid, {...})
    print(db.generate_summary(sid))
"""

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS review_sessions (
    session_id TEXT PRIMARY KEY,
    image_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS review_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    image_path TEXT NOT NULL,
    image_index INTEGER NOT NULL,
    form_index INTEGER NOT NULL DEFAULT 1,
    patient_name TEXT DEFAULT '',
    form_date TEXT DEFAULT '',
    form_type TEXT DEFAULT '',
    overall_result TEXT NOT NULL,
    dim1_result TEXT NOT NULL,
    dim1_findings TEXT DEFAULT '',
    dim2_result TEXT NOT NULL,
    dim2_findings TEXT DEFAULT '',
    dim3_result TEXT NOT NULL,
    dim3_findings TEXT DEFAULT '',
    dim4_result TEXT NOT NULL,
    dim4_findings TEXT DEFAULT '',
    dim5_result TEXT NOT NULL,
    dim5_findings TEXT DEFAULT '',
    dim6_result TEXT NOT NULL,
    dim6_findings TEXT DEFAULT '',
    dim7_result TEXT NOT NULL,
    dim7_findings TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES review_sessions(session_id)
);
"""

RESULT_FIELDS = [
    "image_path", "image_index", "form_index",
    "patient_name", "form_date", "form_type", "overall_result",
    "dim1_result", "dim1_findings",
    "dim2_result", "dim2_findings",
    "dim3_result", "dim3_findings",
    "dim4_result", "dim4_findings",
    "dim5_result", "dim5_findings",
    "dim6_result", "dim6_findings",
    "dim7_result", "dim7_findings",
    "summary",
]

DIM_LABELS = [
    "表单完整性",
    "诊治一致性",
    "针法不叠加",
    "加收项规则",
    "收费合规性",
    "治疗记录完整性",
    "部位/穴位标注",
]


class ReviewDB:
    def __init__(self, db_path: str = "data/reviews.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    def init_session(self, image_count: int) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO review_sessions (session_id, image_count, created_at) VALUES (?, ?, ?)",
            (session_id, image_count, now),
        )
        self.conn.commit()
        return session_id

    def save_result(self, session_id: str, result: dict) -> int:
        self._assert_session_exists(session_id)
        now = datetime.now().isoformat(timespec="seconds")
        values = [result.get(f, "") for f in RESULT_FIELDS]
        placeholders = ", ".join(["?"] * (len(RESULT_FIELDS) + 2))
        fields = ", ".join(["session_id"] + RESULT_FIELDS + ["created_at"])
        cursor = self.conn.execute(
            f"INSERT INTO review_results ({fields}) VALUES ({placeholders})",
            [session_id] + values + [now],
        )
        self.conn.commit()
        self._check_completion(session_id)
        return cursor.lastrowid

    def get_results(self, session_id: str) -> list[dict]:
        self._assert_session_exists(session_id)
        rows = self.conn.execute(
            "SELECT * FROM review_results WHERE session_id = ? ORDER BY image_index, form_index",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_status(self, session_id: str) -> dict:
        self._assert_session_exists(session_id)
        session = self.conn.execute(
            "SELECT * FROM review_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        reviewed = self.conn.execute(
            "SELECT COUNT(DISTINCT image_index) FROM review_results WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        return {
            "session_id": session_id,
            "image_count": session["image_count"],
            "reviewed_count": reviewed,
            "is_complete": reviewed >= session["image_count"],
            "created_at": session["created_at"],
            "completed_at": session["completed_at"],
        }

    def generate_summary(self, session_id: str) -> str:
        results = self.get_results(session_id)
        status = self.get_status(session_id)
        if not results:
            return f"会话 {session_id} 暂无审查结果。"

        total = len(results)
        qualified = sum(1 for r in results if r["overall_result"] == "合格")
        unqualified = total - qualified
        rate = f"{qualified / total * 100:.0f}%" if total > 0 else "N/A"

        lines = [
            f"# 治疗单批量审查报告",
            f"",
            f"- **会话ID**：{session_id}",
            f"- **审查时间**：{status['created_at']}",
            f"- **图片数量**：{status['image_count']}",
            f"- **治疗单数量**：{total}（含多表单图片拆分）",
            f"- **合格**：{qualified} | **不合格**：{unqualified} | **合格率**：{rate}",
            f"",
            f"---",
            f"",
        ]

        for r in results:
            img_label = Path(r["image_path"]).name if r["image_path"] else f"图片{r['image_index']}"
            form_label = f"（表单{r['form_index']}）" if r["form_index"] > 1 else ""
            header = f"## {r['patient_name'] or '未知'} - {r['form_date'] or '未知日期'}"
            lines.append(f"{header}")
            lines.append(f"**来源**：{img_label}{form_label}")
            lines.append(f"**审查结果：{r['overall_result']}**")
            lines.append("")
            lines.append("| 审查维度 | 结论 | 具体发现 |")
            lines.append("|---------|------|---------|")
            for dim_i in range(1, 8):
                label = DIM_LABELS[dim_i - 1]
                res = r[f"dim{dim_i}_result"]
                findings = r[f"dim{dim_i}_findings"] or ""
                lines.append(f"| {dim_i}. {label} | {res} | {findings} |")
            lines.append("")
            if r["summary"]:
                lines.append(f"**总结**：{r['summary']}")
                lines.append("")
            lines.append("---")
            lines.append("")

        lines.append(f"## 汇总统计")
        lines.append(f"")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 审查治疗单总数 | {total} |")
        lines.append(f"| 合格 | {qualified} |")
        lines.append(f"| 不合格 | {unqualified} |")
        lines.append(f"| 合格率 | {rate} |")

        if unqualified > 0:
            lines.append(f"")
            lines.append(f"### 不合格维度分布")
            lines.append(f"")
            dim_fail_counts = {i: 0 for i in range(1, 8)}
            for r in results:
                if r["overall_result"] == "不合格":
                    for dim_i in range(1, 8):
                        if r[f"dim{dim_i}_result"] == "不通过":
                            dim_fail_counts[dim_i] += 1
            lines.append(f"| 维度 | 不通过次数 |")
            lines.append(f"|------|----------|")
            for dim_i in range(1, 8):
                if dim_fail_counts[dim_i] > 0:
                    lines.append(
                        f"| {dim_i}. {DIM_LABELS[dim_i - 1]} | {dim_fail_counts[dim_i]} |"
                    )

        return "\n".join(lines)

    def export_json(self, session_id: str) -> str:
        results = self.get_results(session_id)
        status = self.get_status(session_id)
        data = {
            "session_id": session_id,
            "status": status,
            "results": results,
        }
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)

    def _assert_session_exists(self, session_id: str):
        row = self.conn.execute(
            "SELECT 1 FROM review_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Session not found: {session_id}")

    def _check_completion(self, session_id: str):
        status = self.get_status(session_id)
        if status["is_complete"] and status["completed_at"] is None:
            now = datetime.now().isoformat(timespec="seconds")
            self.conn.execute(
                "UPDATE review_sessions SET completed_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            self.conn.commit()


def main():
    parser = argparse.ArgumentParser(description="TCM Review Pipeline Database")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new review session")
    p_init.add_argument("--image-count", type=int, required=True)
    p_init.add_argument("--db", default="data/reviews.db")

    p_save = sub.add_parser("save", help="Save a review result from JSON file")
    p_save.add_argument("--session", required=True)
    p_save.add_argument("--json-file", required=True)
    p_save.add_argument("--db", default="data/reviews.db")

    p_status = sub.add_parser("status", help="Check session progress")
    p_status.add_argument("--session", required=True)
    p_status.add_argument("--db", default="data/reviews.db")

    p_summary = sub.add_parser("summary", help="Generate summary report")
    p_summary.add_argument("--session", required=True)
    p_summary.add_argument("--db", default="data/reviews.db")

    p_export = sub.add_parser("export", help="Export results as JSON")
    p_export.add_argument("--session", required=True)
    p_export.add_argument("--db", default="data/reviews.db")

    args = parser.parse_args()
    db = ReviewDB(args.db)

    try:
        if args.command == "init":
            sid = db.init_session(args.image_count)
            print(json.dumps({"session_id": sid}))

        elif args.command == "save":
            with open(args.json_file, "r", encoding="utf-8") as f:
                result = json.load(f)
            row_id = db.save_result(args.session, result)
            print(json.dumps({"saved": True, "row_id": row_id}))

        elif args.command == "status":
            status = db.get_status(args.session)
            print(json.dumps(status, default=str))

        elif args.command == "summary":
            report = db.generate_summary(args.session)
            print(report)

        elif args.command == "export":
            print(db.export_json(args.session))
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests to verify they pass**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python -m pytest tests/test_review_db.py -v
```

Expected: All 10 tests PASS

- [ ] **Step 4: Commit**

```powershell
git add scripts/review_db.py
git commit -m "feat: implement review pipeline SQLite database with CLI"
```

---

## Task 4: Test review_db.py CLI

Verify the CLI interface works correctly end-to-end.

**Files:** None (manual testing)

- [ ] **Step 1: Initialize a session via CLI**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python scripts/review_db.py init --image-count 2 --db data/test_reviews.db
```

Expected output (session_id will differ):

```json
{"session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
```

Copy the session_id for the next steps.

- [ ] **Step 2: Create a test result JSON file**

Create `tmp_review_test.json`:

```json
{
    "image_path": "test/sample1.jpg",
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
    "summary": "七大维度全部通过"
}
```

- [ ] **Step 3: Save the result via CLI**

```powershell
python scripts/review_db.py save --session <SESSION_ID> --json-file tmp_review_test.json --db data/test_reviews.db
```

Expected: `{"saved": true, "row_id": 1}`

- [ ] **Step 4: Check status**

```powershell
python scripts/review_db.py status --session <SESSION_ID> --db data/test_reviews.db
```

Expected: `{"session_id": "...", "image_count": 2, "reviewed_count": 1, "is_complete": false, ...}`

- [ ] **Step 5: Generate summary**

```powershell
python scripts/review_db.py summary --session <SESSION_ID> --db data/test_reviews.db
```

Expected: Formatted markdown report with 张三's review results and 合格率.

- [ ] **Step 6: Clean up**

```powershell
Remove-Item tmp_review_test.json -ErrorAction SilentlyContinue
Remove-Item data/test_reviews.db -ErrorAction SilentlyContinue
```

---

## Task 5: Update SKILL.md with Concurrent Pipeline + KB Integration

Rewrite the skill to use the one-image-per-subagent pipeline, multi-form detection, SQLite storage, AND KB-powered pricing via MCP.

> **CROSS-REFERENCE:** This task produces the unified v2 SKILL.md that is referenced by the
> KB plan (`docs/superpowers/plans/2026-04-07-knowledge-base-implementation.md`, Task 10).
> The v2 combines both pipeline features and KB integration into a single skill file.

**Files:**
- Modify: `skills/tcm-treatment-review/SKILL.md`

- [ ] **Step 1: Overwrite SKILL.md with pipeline + KB version**

Create `skills/tcm-treatment-review/SKILL.md`:

```markdown
---
name: tcm-treatment-review
version: v2
description: Review TCM (Traditional Chinese Medicine) treatment forms for medical insurance compliance. Check diagnosis-treatment consistency, pricing accuracy, needle method stacking rules, surcharge item pairing, treatment log completeness, and body part specification. Use when the user asks to review, audit, or judge TCM treatment forms (治疗单/治疗申请单) for qualification.
---

# 中医治疗单合规审查（v2 — 知识库驱动 + 并发流水线）

**重要：所有评审输出必须全部使用中文，包括表头、结论、分析说明等，不使用任何英文。**

**版本说明：** v2 包含两项改进：(1) 通过 MinerU 知识库动态查询最新价格标准和政策规则，替代 v1 中的硬编码数据；(2) 批量审查使用并发流水线（一图一代理），解决图片与结论错位问题。

## 前置条件

- MinerU MCP 服务应已启动（`qmd mcp --http --daemon`）
- 如 MCP 不可用，维度五（收费合规性）使用 `standards.md` 中的静态价格作为后备，并在输出中注明："⚠️ 知识库未连接，使用静态价格参考，可能非最新。"

## 审查模式

本技能支持两种审查模式：

| 模式 | 触发条件 | 处理方式 |
|------|---------|---------|
| **单图审查** | 用户提供1张图片 | 直接在当前会话中审查 |
| **批量审查** | 用户提供2张及以上图片 | 启动并发流水线，每张图片分配一个独立子代理 |

## 一、批量审查流水线（2张及以上图片）

### 流水线原则

1. **一图一代理**：每个子代理（Task subagent）只处理一张图片，避免图片与结论错位
2. **多表单拆分**：同一张图片中可能包含多份治疗单（叠放拍摄），每份单独审查
3. **结果持久化**：每份审查结果保存到 SQLite 数据库
4. **汇总等待**：主代理等待所有子代理完成后，生成统一汇总报告

### 第零步：查询知识库获取最新标准

在初始化流水线前，通过 MCP 工具一次性查询最新标准，将结果嵌入到子代理的 prompt 中：

1. **价格标准**：`query "一级机构 中医 各项目 最新价格标准"`
2. **针法规则**：`wiki_read "治疗方法规则/针法互斥与叠加规则"`
3. **加收项规则**：`query "加收项 配对 基础项目 规则"`

将查询结果整理为"最新价格参考"文本块，嵌入每个子代理的 prompt 中。

如 MCP 不可用，使用下方静态后备价格（见"后备价格参考"）。

### 第一步：初始化审查会话

收到用户图片后，统计图片数量并初始化数据库：

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python scripts/review_db.py init --image-count <图片数量>
```

记录输出的 `session_id`，后续所有步骤都需要用到。

### 第二步：为每张图片分派子代理

对每张图片，使用 Task 工具创建一个独立子代理。**同时**分派多个子代理以并发处理。

每个子代理的 prompt 必须包含以下完整信息：

```
你是一个中医治疗单合规审查员。你只负责审查下面这一张图片。

## 你的任务

1. 读取图片：<图片绝对路径>
2. 识别图片中有多少份独立的治疗单/治疗申请单
   - 一张图片可能包含多份表单（叠放拍摄）
   - 通过以下特征识别独立表单的边界：
     a. 不同的患者姓名
     b. 不同的日期
     c. 明显的表单分隔线或页面边界
     d. 不同的表单类型（治疗单 vs 治疗申请单）
   - 如果图片中有非治疗单的内容（如收据、通知、药方等），忽略这些无关内容
3. 对每一份独立的治疗单，执行七大维度审查（详见下方）
4. 将每份治疗单的结果保存为 JSON 文件，然后调用数据库保存命令

## 七大审查维度

### 维度一：表单完整性
必填字段：
- 患者信息：姓名、性别、年龄、电话/联系电话
- 科室/执行科室、门诊号/编号、处方号
- 费别：医保记账 或 医保已勾选
- 医保号/医保就诊卡号
- 日期/申请日期
- 临床诊断/诊断
- 医师姓名及签名
- 收费专用章/机构章

### 维度二：诊治一致性
- 治疗项目必须与诊断逻辑对应
- 治疗项目中的部位必须与诊断病症部位匹配
- 所选穴位必须与病症在解剖学上合理对应

### 维度三：针法不叠加
以下三类针法互斥——仅可按最高价项目收费，不可叠加：
- 常规针法
- 特殊针具针法
- 特殊手法针法

以下项目可与上述三类叠加收费：
- 特殊穴位（部位）针法
- 体表针法
- 仪器针法

### 维度四：加收项规则
- 加收项必须伴随其基础项目
- 中医拔罐-药物罐（加收）必须搭配中医拔罐
- 同系列加收项不可叠加（如主任医师与副主任医师取其一）
- 不同系列加收项可叠加（如主任医师加收 + 儿童加收）

### 维度五：收费合规性
使用以下从知识库查询到的最新价格标准验证：

<将第零步查询到的最新价格数据嵌入此处>

如价格数据来自知识库，标注"价格来源：知识库（最后更新：[日期]）"。
如价格数据来自静态后备，标注"⚠️ 价格来源：静态参考（知识库未连接），可能非最新。"

### 维度六：治疗记录完整性
每次治疗必须记录：治疗日期、起止时间、治疗项目、患者签名、医师签名。
处方次数多于已记录次数属于正常（后续治疗尚未发生）。
仅在以下情况判定为不通过：记录完全空白、已记录条目缺必要信息、治疗日期间隔超3个月。

### 维度七：部位/穴位标注
- 治疗单格式：部位/穴位栏必须填写
- 治疗申请单格式：部位栏应填写（手写可接受）

## 保存结果

对每份识别出的治疗单，生成一个 JSON 文件并保存到数据库。

JSON 文件格式（保存为 tmp_review_<image_index>_<form_index>.json）：

{
    "image_path": "<图片绝对路径>",
    "image_index": <图片序号，从1开始>,
    "form_index": <表单序号，一张图片中第几份，从1开始>,
    "patient_name": "<患者姓名>",
    "form_date": "<表单日期 YYYY-MM-DD>",
    "form_type": "<治疗单 或 治疗申请单>",
    "overall_result": "<合格 或 不合格>",
    "dim1_result": "<通过 或 不通过>",
    "dim1_findings": "<具体发现>",
    "dim2_result": "<通过 或 不通过>",
    "dim2_findings": "<具体发现>",
    "dim3_result": "<通过 或 不通过>",
    "dim3_findings": "<具体发现>",
    "dim4_result": "<通过 或 不通过>",
    "dim4_findings": "<具体发现>",
    "dim5_result": "<通过 或 不通过>",
    "dim5_findings": "<具体发现>",
    "dim6_result": "<通过 或 不通过>",
    "dim6_findings": "<具体发现>",
    "dim7_result": "<通过 或 不通过>",
    "dim7_findings": "<具体发现>",
    "summary": "<简要总结>"
}

保存到数据库的命令：

cd c:\Users\roger\Documents\Pyproject\hospital-claw
python scripts/review_db.py save --session <SESSION_ID> --json-file tmp_review_<image_index>_<form_index>.json

保存成功后，删除临时 JSON 文件。

## 你必须返回的信息

完成后，在你的最终回复中说明：
- 这张图片中识别到了几份治疗单
- 每份治疗单的患者姓名和审查结果（合格/不合格）
- 所有结果已保存到数据库
```

### 第三步：等待所有子代理完成

分派所有子代理后，通过轮询数据库状态确认进度：

```powershell
python scripts/review_db.py status --session <SESSION_ID>
```

检查 `is_complete` 是否为 `true`。如果还有子代理在处理中，等待后重新检查。

### 第四步：生成汇总报告

所有图片处理完成后，生成汇总报告：

```powershell
python scripts/review_db.py summary --session <SESSION_ID>
```

将输出的 Markdown 报告直接呈现给用户。报告包含：
- 每份治疗单的七大维度审查详情
- 汇总统计：合格数、不合格数、合格率
- 不合格维度分布

### 第五步：清理临时文件

```powershell
Remove-Item tmp_review_*.json -ErrorAction SilentlyContinue
```

---

## 二、单图审查（1张图片）

如果用户只提供了1张图片，无需启动流水线。直接在当前会话中执行审查。

### 第零步：查询知识库（如可用）

通过 MCP 工具查询最新标准：
1. **价格标准**：`query "一级机构 中医 各项目 最新价格标准"`
2. **针法规则**：`wiki_read "治疗方法规则/针法互斥与叠加规则"`

如 MCP 不可用，使用下方"后备价格参考"。

### 第一步：识别表单数量

查看图片，识别其中包含多少份独立的治疗单。判断标准：
- 不同的患者姓名 → 不同表单
- 不同的日期 → 不同表单
- 明显的表单分隔线 → 不同表单
- 非治疗单内容（收据、通知等）→ 忽略

### 第二步：逐表单审查

对每份独立的治疗单，按七大维度逐项检查。

#### 维度一：表单完整性

必填字段：
- 患者信息：姓名、性别、年龄、电话/联系电话
- 科室/执行科室、门诊号/编号、处方号
- 费别：医保记账 或 医保已勾选
- 医保号/医保就诊卡号
- 日期/申请日期
- 临床诊断/诊断
- 医师姓名及签名
- 收费专用章/机构章

#### 维度二：诊治一致性

- 治疗项目必须与诊断逻辑对应
- 治疗项目中的部位必须与诊断病症部位匹配
- 所选穴位必须与病症在解剖学上合理对应
- 不通过示例：诊断为扁桃体恶性肿瘤，治疗却开腰部疾病推拿

#### 维度三：针法不叠加

以下三类针法互斥——仅可按最高价项目收费，不可叠加：
- 常规针法
- 特殊针具针法
- 特殊手法针法

以下项目可与上述三类叠加收费：
- 特殊穴位（部位）针法
- 体表针法
- 仪器针法

#### 维度四：加收项规则

- 加收项必须伴随其基础项目
- 中医拔罐-药物罐（加收）必须搭配中医拔罐
- 同系列加收项不可叠加（如主任医师与副主任医师取其一）
- 不同系列加收项可叠加（如主任医师加收 + 儿童加收）

#### 维度五：收费合规性

**优先通过知识库查询验证**每个项目的单价是否符合一级机构官方价格表。

查询方式：`query "{项目名称} 一级 价格"`

如知识库不可用，使用后备价格参考（见下方）并标注为："⚠️ 价格来源：静态参考（知识库未连接），可能非最新。"

#### 维度六：治疗记录完整性

每次治疗必须记录：
- 治疗日期
- 起止时间
- 治疗项目（通常以项目序号标注）
- 患者签名
- 医师签名

**重要**：处方规定的治疗次数可能多于已记录的次数，这属于正常情况。仅在以下情况判定为不通过：
- 治疗记录完全空白
- 已记录的条目缺少必要信息
- 治疗日期之间存在明显不合理的间隔（超过3个月）

#### 维度七：部位/穴位标注

- 治疗单格式：部位/穴位栏必须填写
- 治疗申请单格式：部位栏应填写（手写可接受）

### 第三步：给出审查结论

对每份治疗单分别给出结论：
- **合格**：七大维度全部通过
- **不合格**：任一维度不通过——列出所有不通过的维度及具体原因

## 输出格式

对每份治疗单，输出如下格式（全部使用中文）：

```
## [患者姓名] - [表单日期]
**审查结果：合格 / 不合格**

| 审查维度 | 结论 | 具体发现 |
|---------|------|---------|
| 1. 表单完整性 | 通过/不通过 | ... |
| 2. 诊治一致性 | 通过/不通过 | ... |
| 3. 针法不叠加 | 通过/不通过 | ... |
| 4. 加收项规则 | 通过/不通过 | ... |
| 5. 收费合规性 | 通过/不通过 | ... |
| 6. 治疗记录完整性 | 通过/不通过 | ... |
| 7. 部位/穴位标注 | 通过/不通过 | ... |

**总结**：[简要说明整体结论]

**数据来源**：价格标准通过知识库查询验证（最后更新：[日期]）/ ⚠️ 使用静态价格参考
```

如果是批量审查，末尾附加汇总统计（由数据库自动生成）。

## 后备价格参考（知识库不可用时使用）

一级机构（沁宇堂）静态价格参考（来源：v1 standards.md，可能非最新）：
- 常规针法：50元，特殊针具针法：60元，特殊手法针法：90元
- 特殊穴位（部位）针法：15元/穴位，体表针法：24元，仪器针法：22元
- 悬空灸：21元，隔物灸：25元，铺灸：50元
- 中医拔罐：20元，药物罐加收：26元（合计46元）
- 头面部推拿：80元，颈部推拿：36元，脊柱推拿：70元
- 腰部推拿：80元，背部推拿：36元，肩部推拿：36元/单侧
- 髋骶部推拿：75元，四肢推拿：48元/单肢，脏腑推拿：78元
- 中药烫熨：43元，穴位埋入：15元/穴位，耳穴疗法：12元/单耳
- 针刀（钩活）疗法：75元/部位

完整价格表详见 [standards.md](standards.md)。

## 补充资料

- 优先通过知识库（MCP）查询最新价格和政策规则
- 完整价格表后备参考详见 [standards.md](standards.md)
- 常见合格/不合格模式及示例详见 [examples.md](examples.md)
- 审查结果数据库位于 `data/reviews.db`，可通过以下命令导出历史记录：

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python scripts/review_db.py export --session <SESSION_ID>
```
```

- [ ] **Step 2: Verify the skill file is syntactically correct**

Open the file in the editor and verify:
- YAML frontmatter is valid (between `---` markers)
- All markdown formatting renders correctly
- No broken links (standards.md, examples.md still referenced correctly)
- JSON example in the subagent prompt section is valid

- [ ] **Step 3: Commit**

```powershell
git add skills/tcm-treatment-review/SKILL.md
git commit -m "feat: rewrite tcm-treatment-review with concurrent pipeline and SQLite storage"
```

---

## Task 6: End-to-End Test — Single Image

Test the single-image review mode with a real or simulated treatment form.

**Files:** None (testing only)

- [ ] **Step 1: Identify a test image**

Check if there are any treatment form images in the project or docs folder:

```powershell
Get-ChildItem -Recurse "c:\Users\roger\Documents\Pyproject\hospital-claw\docs" -Include *.jpg,*.jpeg,*.png,*.bmp | Select-Object FullName
```

If no images exist, use a text-based test instead (see Step 2b).

- [ ] **Step 2a: Test with image (if available)**

In a Cursor agent chat, provide a single treatment form image and say:

"请审查这份治疗单"

Expected: The agent uses the single-image mode (Section 二 of the skill), identifies the form(s) in the image, and outputs the 7-dimension review table. No SQLite involved for single images.

- [ ] **Step 2b: Test with text description (if no image)**

"请审查以下治疗信息：患者王五，男，55岁，诊断腰痹（气滞血瘀证）/ 腰椎间盘突出，治疗项目：常规针法50元、腰部疾病推拿80元、中医拔罐20元、药物罐加收26元、中药烫熨43元、穴位埋入(5穴位)75元。治疗记录：2026-03-01至2026-03-10共5次，签名齐全。"

Expected:
- 维度1-7 all pass
- Overall: 合格
- 药物罐加收 correctly paired with 中医拔罐 (维度四通过)
- No needle stacking violation (only 常规针法, 维度三通过)

---

## Task 7: End-to-End Test — Batch Pipeline

Test the concurrent pipeline with multiple images (or simulated multi-image scenario).

**Files:** None (testing only)

- [ ] **Step 1: Prepare test data**

If real images are unavailable, create 3 text files simulating treatment form images to test the pipeline flow:

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p data/test_images
```

Create `data/test_images/form1.txt`:

```
患者：张三，男，45岁
诊断：项痹（气滞血瘀证）/ 混合型颈椎病
项目：颈部疾病推拿 36元，脊柱部位疾病推拿 70元，常规针法 50元，悬空灸 21元，中医拔罐 20元，药物罐加收 26元
治疗记录：3次，2026-03-01/03/05，签名齐全
```

Create `data/test_images/form2.txt`:

```
患者：李四，女，38岁
诊断：扁桃体恶性肿瘤 / 侠瘿痛
项目：腰部疾病推拿 80元，常规针法 50元，特殊针具针法 60元
治疗记录：空白
```

Create `data/test_images/form3.txt`:

```
患者：王五，男，60岁
诊断：腰痹（气滞血瘀证）/ 腰椎间盘突出
项目：腰部疾病推拿 80元，脊柱推拿 70元，特殊针具针法 60元，穴位埋入(5穴位) 75元，中药烫熨 43元
部位穴位：均已标注
治疗记录：5次，签名齐全

---（第二份表单）---

患者：赵六，女，42岁
诊断：胃痞（痰湿瘀滞证）/ 慢性胃炎
项目：脏腑疾病推拿 78元，常规针法 50元，穴位埋入(5穴位) 75元，耳穴疗法(双耳) 24元
部位穴位：均已标注
治疗记录：3次，签名齐全
```

- [ ] **Step 2: Test the pipeline**

In a Cursor agent chat, say:

"请批量审查以下3张治疗单图片：
1. data/test_images/form1.txt
2. data/test_images/form2.txt
3. data/test_images/form3.txt"

Expected behavior:
1. Agent initializes a session: `python scripts/review_db.py init --image-count 3`
2. Agent dispatches 3 Task subagents concurrently (one per file)
3. Subagent for form2.txt detects: 诊治不一致（扁桃体 vs 腰部推拿）+ 针法叠加（常规 + 特殊针具）+ 治疗记录空白 → 不合格
4. Subagent for form3.txt detects 2 forms in one image (王五 + 赵六), saves 2 separate results
5. Each subagent saves results to SQLite
6. Agent generates summary: `python scripts/review_db.py summary --session <ID>`
7. Summary shows: 4 forms reviewed, form2 不合格, others 合格

- [ ] **Step 3: Verify the database**

```powershell
python scripts/review_db.py export --session <SESSION_ID>
```

Expected: JSON output with 4 results (3 images, but form3 has 2 forms).

- [ ] **Step 4: Clean up test data**

```powershell
Remove-Item -Recurse data/test_images -ErrorAction SilentlyContinue
Remove-Item tmp_review_*.json -ErrorAction SilentlyContinue
```

---

## Task 8: Test Multi-Form Image Detection

Specifically test the edge case where one image contains multiple stacked treatment forms with irrelevant content mixed in.

**Files:** None (testing only)

- [ ] **Step 1: Create a complex test scenario**

In a Cursor agent chat, describe a complex image:

"请审查这张图片。图片中包含以下内容（从上到下）：

1. 一张收费收据（非治疗单，应忽略）

2. 治疗单-患者A：
   - 患者：陈七，男，50岁，电话13800138000
   - 科室：中医科，门诊号：20260301-001
   - 费别：医保记账，医保号：SH123456
   - 诊断：腰痹（气滞血瘀证）
   - 项目：腰部推拿80元，常规针法50元，中药烫熨43元
   - 部位：腰部、腰俞穴、委中穴
   - 治疗记录：3次，签名齐全
   - 医师签名：李医师，收费章已盖

3. 一张药方（非治疗单，应忽略）

4. 治疗申请单-患者B：
   - 患者：周八，女，35岁
   - 诊断：项痹（经络气滞证）/ 颈椎病
   - 项目：颈部推拿36元，常规针法50元，特殊针具针法60元
   - 部位：颈部、风池穴
   - 治疗记录：2次，签名齐全"

Expected:
- Agent identifies 2 treatment forms, ignores receipt and prescription
- 患者A (陈七): 合格 — all dimensions pass
- 患者B (周八): 不合格 — 维度三（针法叠加：常规针法 + 特殊针具针法互斥）

---

## Task 9: Final Commit and Verification

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python -m pytest tests/test_review_db.py -v
```

Expected: All 10 tests PASS

- [ ] **Step 2: Verify file structure**

```powershell
Get-ChildItem -Recurse scripts, tests, skills\tcm-treatment-review | Select-Object FullName
```

Expected:
```
scripts\review_db.py
tests\test_review_db.py
skills\tcm-treatment-review\SKILL.md          ← pipeline version
skills\tcm-treatment-review\standards.md      ← unchanged
skills\tcm-treatment-review\examples.md       ← unchanged
```

- [ ] **Step 3: Verify .gitignore**

```powershell
type .gitignore
```

Expected: Contains `data/`, `*.db`, `__pycache__/`, `tmp_review_*.json`

- [ ] **Step 4: Final commit**

```powershell
git add -A
git commit -m "feat: complete review pipeline — concurrent subagents, multi-form detection, SQLite storage"
```
