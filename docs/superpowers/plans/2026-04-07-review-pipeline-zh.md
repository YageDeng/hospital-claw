# 中医治疗单审查流水线实施计划

> **致代理工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 来逐任务实施本计划。各步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 构建一个并发图片审查流水线——每个子代理一次处理一张治疗单图片，将结构化结果保存到 SQLite，最后由主代理汇总所有结果。消除图片与结论错位问题，并正确处理单张图片中包含多份表单的情况。

**架构：** 主代理接收一批图片 → 初始化 SQLite 审查会话 → 为每张图片分派一个 Task 子代理（每个子代理：检测表单边界、过滤无关内容、按7大维度审查每份表单、保存到 SQLite）→ 主代理读取 SQLite 并生成统一的汇总报告。

**技术栈：** Python 3.10+（sqlite3 标准库）、Cursor Task 子代理、通过视觉模型进行图片分析

**规格说明：** 本计划解决当前 `tcm-treatment-review` 技能的三个问题：(1) 多图批量处理导致图片与结论错位；(2) 单张图片中叠放的多份表单需要逐表单隔离；(3) 缺少持久化存储和并发审查流水线。

**依赖关系：** 本计划生成 `tcm-treatment-review` 的统一 v2 SKILL.md，该文件被知识库计划引用（`docs/superpowers/plans/2026-04-07-knowledge-base-implementation.md`，任务10）。v2 同时包含流水线功能和知识库/MCP 集成。请将本计划的任务1-5作为知识库计划任务10的一部分来执行。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `scripts/review_db.py` | SQLite 数据库：模式定义、会话管理、结果存储、汇总生成。零外部依赖（仅使用标准库）。 |
| `tests/test_review_db.py` | 所有数据库操作的单元测试 |
| `skills/tcm-treatment-review/SKILL.md` | 更新后的技能文件，包含并发流水线指令、单图单代理协议、多表单检测 |
| `.gitignore` | 项目根目录 gitignore（新建）— 忽略 `data/*.db` 及其他运行时产物 |

**未修改的文件：**
- `skills/tcm-treatment-review/standards.md` — 价格参考（未修改）
- `skills/tcm-treatment-review/examples.md` — 模式参考（未修改）

---

## 任务1：创建根目录 .gitignore

项目当前没有根目录 `.gitignore`。审查流水线将在 `data/` 目录中创建 SQLite 文件，这些文件不应被提交。

**文件：**
- 创建：`.gitignore`

- [ ] **步骤1：创建 .gitignore**

在项目根目录创建 `.gitignore`：

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

- [ ] **步骤2：提交**

```powershell
git add .gitignore
git commit -m "chore: add root .gitignore for runtime data and Python artifacts"
```

---

## 任务2：为 review_db.py 编写失败测试

先编写测试文件。所有数据库操作在实现之前先测试。

**文件：**
- 创建：`tests/test_review_db.py`

- [ ] **步骤1：创建 tests 目录**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p tests
```

- [ ] **步骤2：编写测试文件**

创建 `tests/test_review_db.py`：

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

- [ ] **步骤3：运行测试以验证全部失败**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python -m pytest tests/test_review_db.py -v
```

预期结果：所有测试失败，报错 `ModuleNotFoundError: No module named 'review_db'`

- [ ] **步骤4：提交**

```powershell
git add tests/test_review_db.py
git commit -m "test: add failing tests for review pipeline SQLite database"
```

---

## 任务3：实现 review_db.py

实现 SQLite 数据库模块，使所有测试通过。

**文件：**
- 创建：`scripts/review_db.py`

- [ ] **步骤1：创建 scripts 目录**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p scripts
```

- [ ] **步骤2：编写 review_db.py**

创建 `scripts/review_db.py`：

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

- [ ] **步骤3：运行测试以验证全部通过**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python -m pytest tests/test_review_db.py -v
```

预期结果：全部10个测试通过

- [ ] **步骤4：提交**

```powershell
git add scripts/review_db.py
git commit -m "feat: implement review pipeline SQLite database with CLI"
```

---

## 任务4：测试 review_db.py 命令行界面

端到端验证命令行界面是否正常工作。

**文件：** 无（手动测试）

- [ ] **步骤1：通过命令行初始化会话**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python scripts/review_db.py init --image-count 2 --db data/test_reviews.db
```

预期输出（session_id 会不同）：

```json
{"session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
```

复制 session_id 以用于后续步骤。

- [ ] **步骤2：创建测试结果 JSON 文件**

创建 `tmp_review_test.json`：

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

- [ ] **步骤3：通过命令行保存结果**

```powershell
python scripts/review_db.py save --session <SESSION_ID> --json-file tmp_review_test.json --db data/test_reviews.db
```

预期结果：`{"saved": true, "row_id": 1}`

- [ ] **步骤4：检查状态**

```powershell
python scripts/review_db.py status --session <SESSION_ID> --db data/test_reviews.db
```

预期结果：`{"session_id": "...", "image_count": 2, "reviewed_count": 1, "is_complete": false, ...}`

- [ ] **步骤5：生成汇总报告**

```powershell
python scripts/review_db.py summary --session <SESSION_ID> --db data/test_reviews.db
```

预期结果：格式化的 Markdown 报告，包含张三的审查结果和合格率。

- [ ] **步骤6：清理**

```powershell
Remove-Item tmp_review_test.json -ErrorAction SilentlyContinue
Remove-Item data/test_reviews.db -ErrorAction SilentlyContinue
```

---

## 任务5：更新 SKILL.md 以支持并发流水线 + 知识库集成

重写技能文件，采用一图一代理流水线、多表单检测、SQLite 存储，以及通过 MCP 驱动的知识库定价查询。

> **交叉引用：** 本任务生成统一的 v2 SKILL.md，该文件被知识库计划引用
> （`docs/superpowers/plans/2026-04-07-knowledge-base-implementation.md`，任务10）。
> v2 将流水线功能和知识库集成合并到单个技能文件中。

**文件：**
- 修改：`skills/tcm-treatment-review/SKILL.md`

- [ ] **步骤1：用流水线 + 知识库版本覆盖 SKILL.md**

创建 `skills/tcm-treatment-review/SKILL.md`：

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

- [ ] **步骤2：验证技能文件语法正确**

打开文件在编辑器中验证：
- YAML 前置元数据有效（在 `---` 标记之间）
- 所有 Markdown 格式正确渲染
- 无断链（standards.md、examples.md 仍正确引用）
- 子代理 prompt 部分中的 JSON 示例有效

- [ ] **步骤3：提交**

```powershell
git add skills/tcm-treatment-review/SKILL.md
git commit -m "feat: rewrite tcm-treatment-review with concurrent pipeline and SQLite storage"
```

---

## 任务6：端到端测试 — 单图审查

使用真实或模拟的治疗单测试单图审查模式。

**文件：** 无（仅测试）

- [ ] **步骤1：确定测试图片**

检查项目或 docs 目录下是否有治疗单图片：

```powershell
Get-ChildItem -Recurse "c:\Users\roger\Documents\Pyproject\hospital-claw\docs" -Include *.jpg,*.jpeg,*.png,*.bmp | Select-Object FullName
```

如果没有图片，则使用基于文本的测试（见步骤2b）。

- [ ] **步骤2a：使用图片测试（如有）**

在 Cursor 代理聊天中，提供一张治疗单图片并说：

"请审查这份治疗单"

预期结果：代理使用单图模式（技能文件第二节），识别图片中的表单，并输出七大维度审查表格。单图不涉及 SQLite。

- [ ] **步骤2b：使用文本描述测试（如无图片）**

"请审查以下治疗信息：患者王五，男，55岁，诊断腰痹（气滞血瘀证）/ 腰椎间盘突出，治疗项目：常规针法50元、腰部疾病推拿80元、中医拔罐20元、药物罐加收26元、中药烫熨43元、穴位埋入(5穴位)75元。治疗记录：2026-03-01至2026-03-10共5次，签名齐全。"

预期结果：
- 维度1-7全部通过
- 总体结果：合格
- 药物罐加收正确搭配中医拔罐（维度四通过）
- 无针法叠加违规（仅有常规针法，维度三通过）

---

## 任务7：端到端测试 — 批量流水线

使用多张图片（或模拟的多图场景）测试并发流水线。

**文件：** 无（仅测试）

- [ ] **步骤1：准备测试数据**

如果没有真实图片，创建3个文本文件模拟治疗单图片以测试流水线流程：

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
mkdir -p data/test_images
```

创建 `data/test_images/form1.txt`：

```
患者：张三，男，45岁
诊断：项痹（气滞血瘀证）/ 混合型颈椎病
项目：颈部疾病推拿 36元，脊柱部位疾病推拿 70元，常规针法 50元，悬空灸 21元，中医拔罐 20元，药物罐加收 26元
治疗记录：3次，2026-03-01/03/05，签名齐全
```

创建 `data/test_images/form2.txt`：

```
患者：李四，女，38岁
诊断：扁桃体恶性肿瘤 / 侠瘿痛
项目：腰部疾病推拿 80元，常规针法 50元，特殊针具针法 60元
治疗记录：空白
```

创建 `data/test_images/form3.txt`：

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

- [ ] **步骤2：测试流水线**

在 Cursor 代理聊天中说：

"请批量审查以下3张治疗单图片：
1. data/test_images/form1.txt
2. data/test_images/form2.txt
3. data/test_images/form3.txt"

预期行为：
1. 代理初始化会话：`python scripts/review_db.py init --image-count 3`
2. 代理同时分派3个 Task 子代理（每个文件一个）
3. form2.txt 的子代理检测到：诊治不一致（扁桃体 vs 腰部推拿）+ 针法叠加（常规 + 特殊针具）+ 治疗记录空白 → 不合格
4. form3.txt 的子代理检测到一张图中有2份表单（王五 + 赵六），保存2条独立结果
5. 每个子代理将结果保存到 SQLite
6. 代理生成汇总：`python scripts/review_db.py summary --session <ID>`
7. 汇总显示：共审查4份表单，form2 不合格，其余合格

- [ ] **步骤3：验证数据库**

```powershell
python scripts/review_db.py export --session <SESSION_ID>
```

预期结果：JSON 输出包含4条结果（3张图片，但 form3 包含2份表单）。

- [ ] **步骤4：清理测试数据**

```powershell
Remove-Item -Recurse data/test_images -ErrorAction SilentlyContinue
Remove-Item tmp_review_*.json -ErrorAction SilentlyContinue
```

---

## 任务8：测试多表单图片检测

专门测试一张图片中包含多份叠放治疗单并混有无关内容的边缘情况。

**文件：** 无（仅测试）

- [ ] **步骤1：创建复杂测试场景**

在 Cursor 代理聊天中，描述一张复杂图片：

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

预期结果：
- 代理识别出2份治疗单，忽略收据和药方
- 患者A（陈七）：合格 — 所有维度通过
- 患者B（周八）：不合格 — 维度三（针法叠加：常规针法 + 特殊针具针法互斥）

---

## 任务9：最终提交与验证

**文件：** 无（仅验证）

- [ ] **步骤1：运行所有测试**

```powershell
cd c:\Users\roger\Documents\Pyproject\hospital-claw
python -m pytest tests/test_review_db.py -v
```

预期结果：全部10个测试通过

- [ ] **步骤2：验证文件结构**

```powershell
Get-ChildItem -Recurse scripts, tests, skills\tcm-treatment-review | Select-Object FullName
```

预期结果：
```
scripts\review_db.py
tests\test_review_db.py
skills\tcm-treatment-review\SKILL.md          ← 流水线版本
skills\tcm-treatment-review\standards.md      ← 未修改
skills\tcm-treatment-review\examples.md       ← 未修改
```

- [ ] **步骤3：验证 .gitignore**

```powershell
type .gitignore
```

预期结果：包含 `data/`、`*.db`、`__pycache__/`、`tmp_review_*.json`

- [ ] **步骤4：最终提交**

```powershell
git add -A
git commit -m "feat: complete review pipeline — concurrent subagents, multi-form detection, SQLite storage"
```
