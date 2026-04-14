"""Hospital daily operations analysis engine.

Usage:
    python scripts/hospital_ops_analysis.py --input <dir> [--output <dir>] [--date YYYY-MM-DD]

读取 6 类 XLSX 文件，计算 KPI，检测异常，
输出 JSON 分析结果 + 格式化 XLSX 报告。
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

SOURCE_MAPPING = {
    "revenue": ("sample_revenue.xlsx", "营业额", "收入"),
    "materials": ("sample_materials.xlsx", "物料", "耗材"),
    "visits": ("sample_visits.xlsx", "门诊", "就诊"),
    "treatments": ("sample_treatments.xlsx", "治疗项目", "治疗明细"),
    "insurance": ("sample_insurance.xlsx", "医保", "结算"),
    "staff": ("sample_staff.xlsx", "工作量", "人员"),
}

DATE_COLUMNS = {
    "revenue": "日期",
    "materials": "日期",
    "visits": "日期",
    "treatments": "日期",
    "insurance": "结算日期",
    "staff": "日期",
}


def _find_file(directory: Path, category: str) -> Path | None:
    """通过关键词匹配查找指定类别的 XLSX 文件。"""
    keywords = SOURCE_MAPPING[category]
    for f in directory.glob("*.xlsx"):
        name_lower = f.stem.lower()
        if any(kw in name_lower for kw in keywords):
            return f
    exact = directory / SOURCE_MAPPING[category][0]
    return exact if exact.exists() else None


def load_source(path: Path, category: str) -> pd.DataFrame | None:
    """加载单个 XLSX 数据源并标准化日期列。"""
    if not path.exists():
        return None
    df = pd.read_excel(path)
    date_col = DATE_COLUMNS.get(category)
    if date_col and date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col])
    return df


def load_all_sources(directory: Path) -> dict[str, pd.DataFrame | None]:
    """从目录中加载全部 6 个数据源。"""
    result = {}
    for cat in SOURCE_MAPPING:
        path = _find_file(directory, cat)
        result[cat] = load_source(path, cat) if path else None
    return result


# ─── KPI 计算函数 ────────────────────────────────────────────────


def compute_revenue_kpis(df: pd.DataFrame) -> dict[str, Any]:
    """营收维度 KPI。"""
    total = df["收入金额"].sum()
    days = df["日期"].dt.date.nunique()
    dept = df.groupby("科室")["收入金额"].sum()
    return {
        "total_revenue": float(total),
        "daily_avg_revenue": float(total / max(days, 1)),
        "insurance_ratio": float(df["医保支付"].sum() / max(total, 1)),
        "avg_ticket": float(total / max(len(df), 1)),
        "dept_breakdown": dept.to_dict(),
        "daily_trend": (
            df.groupby(df["日期"].dt.date)["收入金额"]
            .sum()
            .reset_index()
            .rename(columns={"日期": "date", "收入金额": "amount"})
            .to_dict(orient="records")
        ),
    }


def compute_material_kpis(
    mat_df: pd.DataFrame, rev_df: pd.DataFrame | None = None
) -> dict[str, Any]:
    """物料维度 KPI。"""
    total_cost = mat_df["金额"].sum()
    rev_total = rev_df["收入金额"].sum() if rev_df is not None else 0
    dept = mat_df.groupby("科室")["金额"].sum()
    return {
        "total_cost": float(total_cost),
        "cost_rate": float(total_cost / max(rev_total, 1)) if rev_total else 0,
        "dept_breakdown": dept.to_dict(),
        "top_items": (
            mat_df.groupby("物料名称")["金额"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .to_dict()
        ),
        "daily_trend": (
            mat_df.groupby(mat_df["日期"].dt.date)["金额"]
            .sum()
            .reset_index()
            .rename(columns={"日期": "date", "金额": "amount"})
            .to_dict(orient="records")
        ),
    }


def compute_visit_kpis(df: pd.DataFrame) -> dict[str, Any]:
    """就诊维度 KPI。"""
    total = len(df)
    days = df["日期"].dt.date.nunique()
    revisit = df[df["就诊类型"] == "复诊"]
    insurance = df[df["支付类型"] == "医保"]
    return {
        "total_visits": total,
        "daily_avg_visits": round(total / max(days, 1), 1),
        "revisit_rate": float(len(revisit) / max(total, 1)),
        "insurance_patient_ratio": float(len(insurance) / max(total, 1)),
        "dept_breakdown": df.groupby("科室").size().to_dict(),
        "doctor_breakdown": df.groupby("医师").size().to_dict(),
    }


def compute_treatment_kpis(df: pd.DataFrame) -> dict[str, Any]:
    """治疗维度 KPI。"""
    top = (
        df.groupby("治疗项目")["金额"]
        .agg(["sum", "count"])
        .sort_values("sum", ascending=False)
    )
    return {
        "total_treatment_revenue": float(df["金额"].sum()),
        "total_treatment_count": int(df["数量"].sum()),
        "top_items": [
            {"name": name, "revenue": float(row["sum"]), "count": int(row["count"])}
            for name, row in top.head(10).iterrows()
        ],
        "avg_price_per_item": float(df["金额"].sum() / max(df["数量"].sum(), 1)),
    }


def compute_insurance_kpis(df: pd.DataFrame) -> dict[str, Any]:
    """医保维度 KPI。"""
    total = len(df)
    success = df[df["结算状态"] == "成功"]
    rejected = df[df["结算状态"].isin(["拒付", "扣减"])]
    reasons = rejected["拒付原因"].value_counts().to_dict() if len(rejected) else {}
    return {
        "total_settlements": total,
        "success_rate": float(len(success) / max(total, 1)),
        "rejection_rate": float(len(rejected) / max(total, 1)),
        "total_amount": float(df["总金额"].sum()),
        "pooling_payment": float(df["统筹支付"].sum()),
        "rejection_reasons": reasons,
    }


def compute_staff_kpis(df: pd.DataFrame) -> dict[str, Any]:
    """人效维度 KPI。"""
    per_person = df.groupby("姓名").agg(
        total_patients=("接诊人次", "sum"),
        total_treatments=("治疗人次", "sum"),
        days_worked=("日期", "nunique"),
        overtime_hours=("加班时长", "sum"),
    )
    return {
        "staff_count": int(df["姓名"].nunique()),
        "avg_patients_per_doctor": float(
            df["接诊人次"].sum() / max(df["姓名"].nunique(), 1)
        ),
        "staff_details": [
            {
                "name": name,
                "total_patients": int(row["total_patients"]),
                "total_treatments": int(row["total_treatments"]),
                "days_worked": int(row["days_worked"]),
                "daily_avg_patients": round(
                    row["total_patients"] / max(row["days_worked"], 1), 1
                ),
                "overtime_hours": float(row["overtime_hours"]),
            }
            for name, row in per_person.iterrows()
        ],
    }


# ─── 异常检测与建议 ──────────────────────────────────────────────


THRESHOLDS = {
    "revenue_drop_pct": 0.20,
    "material_cost_rate_max": 0.30,
    "material_spike_pct": 0.50,
    "ticket_swing_pct": 0.15,
    "rejection_rate_max": 0.05,
    "revisit_rate_min": 0.40,
    "patient_per_doctor_max": 30,
    "patient_per_doctor_min": 5,
}


def detect_anomalies(sources: dict[str, pd.DataFrame | None]) -> list[dict]:
    """
    对所有数据源执行异常检测。
    逐日环比检测营收下降和物料激增，全量检测医保拒付率。
    """
    alerts: list[dict] = []

    rev = sources.get("revenue")
    if rev is not None:
        daily_rev = rev.groupby(rev["日期"].dt.date)["收入金额"].sum()
        if len(daily_rev) >= 2:
            for i in range(1, len(daily_rev)):
                prev, curr = daily_rev.iloc[i - 1], daily_rev.iloc[i]
                if prev > 0 and (prev - curr) / prev > THRESHOLDS["revenue_drop_pct"]:
                    alerts.append({
                        "metric": "daily_revenue",
                        "level": "red",
                        "date": str(daily_rev.index[i]),
                        "message": f"日营收环比下降 {(prev-curr)/prev:.0%}（{prev:.0f} → {curr:.0f}）",
                    })

    mat = sources.get("materials")
    if mat is not None:
        daily_mat = mat.groupby(mat["日期"].dt.date)["金额"].sum()
        if len(daily_mat) >= 2:
            for i in range(1, len(daily_mat)):
                prev, curr = daily_mat.iloc[i - 1], daily_mat.iloc[i]
                if prev > 0 and (curr - prev) / prev > THRESHOLDS["material_spike_pct"]:
                    alerts.append({
                        "metric": "material_consumption",
                        "level": "yellow",
                        "date": str(daily_mat.index[i]),
                        "message": f"物料消耗环比上升 {(curr-prev)/prev:.0%}（{prev:.0f} → {curr:.0f}）",
                    })

    ins = sources.get("insurance")
    if ins is not None:
        rejected = ins[ins["结算状态"].isin(["拒付", "扣减"])]
        rate = len(rejected) / max(len(ins), 1)
        if rate > THRESHOLDS["rejection_rate_max"]:
            alerts.append({
                "metric": "insurance_rejection",
                "level": "red",
                "date": "",
                "message": f"医保拒付/扣减率 {rate:.0%}，超过 {THRESHOLDS['rejection_rate_max']:.0%} 阈值",
            })

    return alerts


def generate_suggestions(
    kpis: dict[str, Any], anomalies: list[dict]
) -> list[dict[str, str]]:
    """根据 KPI 和异常列表生成优化建议。"""
    suggestions: list[dict[str, str]] = []

    for a in anomalies:
        if a["metric"] == "daily_revenue" and a["level"] == "red":
            suggestions.append({
                "category": "营收",
                "priority": "高",
                "suggestion": (
                    f"[{a['date']}] {a['message']}。"
                    "建议排查当日排班是否异常、是否有停诊，并对比同期数据确认是否为周期性波动。"
                ),
            })
        elif a["metric"] == "material_consumption":
            suggestions.append({
                "category": "物料",
                "priority": "中",
                "suggestion": (
                    f"[{a['date']}] {a['message']}。"
                    "建议核查是否为批量领用或异常浪费，对照治疗量确认耗材用量合理性。"
                ),
            })
        elif a["metric"] == "insurance_rejection":
            suggestions.append({
                "category": "医保",
                "priority": "高",
                "suggestion": (
                    f"{a['message']}。"
                    "建议立即排查拒付原因，重点关注诊断-治疗一致性和医保编码合规性。"
                ),
            })

    rev_kpis = kpis.get("revenue", {})
    if rev_kpis.get("insurance_ratio", 0) > 0.85:
        suggestions.append({
            "category": "营收结构",
            "priority": "中",
            "suggestion": "医保收入占比超过 85%，建议拓展自费特色项目以降低医保依赖风险。",
        })

    visit_kpis = kpis.get("visits", {})
    if visit_kpis.get("revisit_rate", 1) < THRESHOLDS["revisit_rate_min"]:
        suggestions.append({
            "category": "患者运营",
            "priority": "中",
            "suggestion": (
                f"复诊率 {visit_kpis['revisit_rate']:.0%}，低于 {THRESHOLDS['revisit_rate_min']:.0%} 基准。"
                "建议加强诊后随访和疗程管理。"
            ),
        })

    return suggestions


# ─── 主分析函数 ──────────────────────────────────────────────────


def analyze_all(sources: dict[str, pd.DataFrame | None]) -> dict[str, Any]:
    """对全部可用数据源执行完整分析，返回结构化报告字典。"""
    report: dict[str, Any] = {}

    if sources.get("revenue") is not None:
        report["revenue"] = compute_revenue_kpis(sources["revenue"])
    if sources.get("materials") is not None:
        report["materials"] = compute_material_kpis(
            sources["materials"], sources.get("revenue")
        )
    if sources.get("visits") is not None:
        report["visits"] = compute_visit_kpis(sources["visits"])
    if sources.get("treatments") is not None:
        report["treatments"] = compute_treatment_kpis(sources["treatments"])
    if sources.get("insurance") is not None:
        report["insurance"] = compute_insurance_kpis(sources["insurance"])
    if sources.get("staff") is not None:
        report["staff"] = compute_staff_kpis(sources["staff"])

    report["anomalies"] = detect_anomalies(sources)
    report["suggestions"] = generate_suggestions(report, report["anomalies"])

    available = [k for k in ("revenue", "materials", "visits") if k in report]
    report["summary"] = {
        "analysis_date": datetime.date.today().isoformat(),
        "sources_loaded": available + [
            k for k in ("treatments", "insurance", "staff") if k in report
        ],
        "total_anomalies": len(report["anomalies"]),
        "total_suggestions": len(report["suggestions"]),
    }

    return report


# ─── XLSX 报告生成 ───────────────────────────────────────────────


def generate_xlsx_report(report: dict[str, Any], output_path: Path) -> Path:
    """
    将分析报告生成为格式化 XLSX 文件。
    包含 Sheet：分析概览、营收分析、异常预警。
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    header_fill = PatternFill("solid", fgColor="4472C4")
    header_font = Font(bold=True, size=11, color="FFFFFF")
    red_fill = PatternFill("solid", fgColor="FFC7CE")
    yellow_fill = PatternFill("solid", fgColor="FFEB9C")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    # ── Sheet 1：分析概览 ──────────────────────────────────────
    ws = wb.active
    ws.title = "分析概览"
    ws["A1"] = "每日经营数据分析报告"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A2"] = f"分析日期：{report.get('summary', {}).get('analysis_date', '')}"
    ws["A3"] = f"数据源：{', '.join(report.get('summary', {}).get('sources_loaded', []))}"

    row = 5
    ws.cell(row, 1, "预警与建议").font = Font(bold=True, size=12)
    row += 1
    for col, title in enumerate(["类别", "优先级", "建议"], 1):
        c = ws.cell(row, col, title)
        c.font, c.fill, c.border = header_font, header_fill, thin_border
    for s in report.get("suggestions", []):
        row += 1
        ws.cell(row, 1, s["category"]).border = thin_border
        cell_p = ws.cell(row, 2, s["priority"])
        cell_p.border = thin_border
        if s["priority"] == "高":
            cell_p.fill = red_fill
        elif s["priority"] == "中":
            cell_p.fill = yellow_fill
        ws.cell(row, 3, s["suggestion"]).border = thin_border

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 80

    # ── Sheet 2：营收分析 ───────────────────────────────────────
    if "revenue" in report:
        ws_rev = wb.create_sheet("营收分析")
        rv = report["revenue"]
        ws_rev["A1"] = "营收 KPI"
        ws_rev["A1"].font = Font(bold=True, size=12)
        metrics = [
            ("总营收（元）", rv.get("total_revenue")),
            ("日均营收（元）", rv.get("daily_avg_revenue")),
            ("医保占比", f"{rv.get('insurance_ratio', 0):.1%}"),
            ("平均客单价（元）", rv.get("avg_ticket")),
        ]
        for i, (label, val) in enumerate(metrics, 2):
            ws_rev.cell(i, 1, label)
            ws_rev.cell(i, 2, val)
        ws_rev.column_dimensions["A"].width = 20
        ws_rev.column_dimensions["B"].width = 16

    # ── Sheet 3：异常预警 ───────────────────────────────────────
    if report.get("anomalies"):
        ws_anom = wb.create_sheet("异常预警")
        ws_anom["A1"] = "异常预警明细"
        ws_anom["A1"].font = Font(bold=True, size=12)
        for col, title in enumerate(["指标", "级别", "日期", "说明"], 1):
            c = ws_anom.cell(2, col, title)
            c.font, c.fill, c.border = header_font, header_fill, thin_border
        for i, a in enumerate(report["anomalies"], 3):
            ws_anom.cell(i, 1, a["metric"]).border = thin_border
            lvl = ws_anom.cell(i, 2, a["level"])
            lvl.border = thin_border
            lvl.fill = red_fill if a["level"] == "red" else yellow_fill
            ws_anom.cell(i, 3, a.get("date", "")).border = thin_border
            ws_anom.cell(i, 4, a["message"]).border = thin_border
        ws_anom.column_dimensions["A"].width = 20
        ws_anom.column_dimensions["D"].width = 60

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


# ─── CLI 入口 ────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Hospital daily ops analysis")
    parser.add_argument("--input", required=True, help="包含 XLSX 文件的目录")
    parser.add_argument("--output", default=None, help="报告输出目录")
    parser.add_argument("--date", default=None, help="分析日期 (YYYY-MM-DD)")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output) if args.output else input_dir / "analysis_output"

    sources = load_all_sources(input_dir)
    loaded = [k for k, v in sources.items() if v is not None]
    if not loaded:
        print(json.dumps({"error": "未找到有效数据源"}, ensure_ascii=False))
        return

    report = analyze_all(sources)

    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = args.date or datetime.date.today().isoformat()

    json_path = output_dir / f"analysis_{date_str}.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    xlsx_path = output_dir / f"经营分析报告_{date_str}.xlsx"
    generate_xlsx_report(report, xlsx_path)

    print(json.dumps({
        "status": "success",
        "sources_loaded": loaded,
        "json_report": str(json_path),
        "xlsx_report": str(xlsx_path),
        "anomalies": len(report["anomalies"]),
        "suggestions": len(report["suggestions"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
