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
    "image_path",
    "image_index",
    "form_index",
    "patient_name",
    "form_date",
    "form_type",
    "overall_result",
    "dim1_result",
    "dim1_findings",
    "dim2_result",
    "dim2_findings",
    "dim3_result",
    "dim3_findings",
    "dim4_result",
    "dim4_findings",
    "dim5_result",
    "dim5_findings",
    "dim6_result",
    "dim6_findings",
    "dim7_result",
    "dim7_findings",
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
            "# 治疗单批量审查报告",
            "",
            f"- **会话ID**：{session_id}",
            f"- **审查时间**：{status['created_at']}",
            f"- **图片数量**：{status['image_count']}",
            f"- **治疗单数量**：{total}（含多表单图片拆分）",
            f"- **合格**：{qualified} | **不合格**：{unqualified} | **合格率**：{rate}",
            "",
            "---",
            "",
        ]

        for r in results:
            img_label = (
                Path(r["image_path"]).name if r["image_path"] else f"图片{r['image_index']}"
            )
            form_label = f"（表单{r['form_index']}）" if r["form_index"] > 1 else ""
            header = f"## {r['patient_name'] or '未知'} - {r['form_date'] or '未知日期'}"
            lines.append(header)
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

        lines.append("## 汇总统计")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 审查治疗单总数 | {total} |")
        lines.append(f"| 合格 | {qualified} |")
        lines.append(f"| 不合格 | {unqualified} |")
        lines.append(f"| 合格率 | {rate} |")

        if unqualified > 0:
            lines.append("")
            lines.append("### 不合格维度分布")
            lines.append("")
            dim_fail_counts = {i: 0 for i in range(1, 8)}
            for r in results:
                if r["overall_result"] == "不合格":
                    for dim_i in range(1, 8):
                        if r[f"dim{dim_i}_result"] == "不通过":
                            dim_fail_counts[dim_i] += 1
            lines.append("| 维度 | 不通过次数 |")
            lines.append("|------|----------|")
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
            # Accept UTF-8 with/without BOM from different editors/shells.
            with open(args.json_file, "r", encoding="utf-8-sig") as f:
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

