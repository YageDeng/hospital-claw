---
name: hospital-ops-daily-report
overview: 构建一个 agent skill，接收 6 类医院运营原始 XLSX 数据（营收、物料、门诊量、治疗项目、医保结算、人员工作量），进行 KPI 计算和异常检测的综合每日分析，读取知识库获取价格/政策基准，输出 Markdown 摘要和 XLSX 详细报告，并给出优化建议。
todos:
  - id: task-1-schemas
    content: "任务 1：定义数据 Schema 和指标基准参考文档 (metrics.md)"
    status: pending
  - id: task-2-fixtures
    content: "任务 2：构建测试数据夹具 (generate_fixtures.py + 6 个 XLSX 文件)"
    status: pending
  - id: task-3-tests
    content: "任务 3：编写分析引擎的失败测试用例"
    status: pending
  - id: task-4-loading
    content: "任务 4：实现数据加载 (load_source, load_all_sources)"
    status: pending
  - id: task-5-kpis
    content: "任务 5：实现 KPI 计算函数（6 个维度）"
    status: pending
  - id: task-6-anomaly
    content: "任务 6：实现异常检测和优化建议生成"
    status: pending
  - id: task-7-report
    content: "任务 7：实现 analyze_all 和 XLSX 报告生成 + CLI 入口"
    status: pending
  - id: task-8-skill
    content: "任务 8：编写 agent skill SKILL.md"
    status: pending
  - id: task-9-deploy
    content: "任务 9：创建版本化副本 (v1/) 并部署到 Cursor"
    status: pending
  - id: task-10-e2e
    content: "任务 10：端到端验证"
    status: pending
isProject: false
---

# 医院每日经营数据分析 Skill — 实施计划

> **给自动化执行者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实施本计划。步骤使用复选框 (`- [ ]`) 语法进行进度跟踪。

**目标：** 创建一个 agent skill + 配套 Python 脚本，将零散的医院每日运营数据表格转化为结构化分析报告，并给出可操作的优化建议。

**架构：** Python 分析引擎 (`scripts/hospital_ops_analysis.py`) 负责数据导入、KPI 计算和 XLSX 报告生成。Agent skill (`skills/hospital-ops-daily-report/SKILL.md`) 编排整个工作流：从用户收集文件、运行脚本、读取知识库获取基准对标数据、产出 Markdown 摘要和格式化 XLSX 报告。分析覆盖 6 个数据维度（营收、物料、门诊、治疗、医保、人效），并进行交叉维度洞察。

**技术栈：** Python 3.11+, pandas, openpyxl, 现有 `scripts/recalc.py` 用于公式验证, MinerU/qmd MCP 用于知识库读取。

---

## 文件结构

```text
skills/hospital-ops-daily-report/
  SKILL.md              -- 主技能文件 (v1)，agent 工作流 + 输出模板
  metrics.md            -- KPI 定义、基准值、阈值、预警规则
  v1/
    SKILL.md            -- 版本化副本
    metrics.md          -- 版本化副本

scripts/
  hospital_ops_analysis.py   -- 核心分析引擎（CLI 工具）

tests/
  test_hospital_ops_analysis.py  -- 单元测试
  fixtures/
    sample_revenue.xlsx          -- 最小测试夹具
    sample_materials.xlsx
    sample_visits.xlsx
    sample_treatments.xlsx
    sample_insurance.xlsx
    sample_staff.xlsx
```

---

### 任务 1：定义数据 Schema 和指标基准参考

**涉及文件：**
- 创建：`skills/hospital-ops-daily-report/metrics.md`

- [ ] **步骤 1：创建指标基准参考文档**

该文件定义 6 个数据源的预期列 Schema 和所有 KPI 计算公式，供脚本和 SKILL.md 共同引用。

```markdown
# 经营数据分析 — 指标与基准参考

## 数据源 Schema

### 1. 营业额/收入明细表 (revenue)
| 列名 | 类型 | 说明 |
|------|------|------|
| 日期 | date | 营业日期 |
| 科室 | str | 科室名称 |
| 医师 | str | 接诊医师 |
| 项目类别 | str | 治疗/药品/检查/其他 |
| 收入金额 | float | 单笔收入（元） |
| 医保支付 | float | 医保支付部分（元） |
| 自费支付 | float | 自费部分（元） |
| 患者ID | str | 患者编号（可选） |

### 2. 物料/耗材消耗表 (materials)
| 列名 | 类型 | 说明 |
|------|------|------|
| 日期 | date | 领用日期 |
| 物料名称 | str | 物料/耗材名称 |
| 规格 | str | 规格型号 |
| 数量 | float | 领用数量 |
| 单价 | float | 单价（元） |
| 金额 | float | 总金额（元） |
| 科室 | str | 领用科室 |
| 用途 | str | 治疗/办公/其他 |

### 3. 门诊量/就诊人次表 (visits)
| 列名 | 类型 | 说明 |
|------|------|------|
| 日期 | date | 就诊日期 |
| 患者ID | str | 患者编号 |
| 科室 | str | 就诊科室 |
| 医师 | str | 接诊医师 |
| 就诊类型 | str | 初诊/复诊 |
| 支付类型 | str | 医保/自费 |

### 4. 治疗项目收费明细表 (treatments)
| 列名 | 类型 | 说明 |
|------|------|------|
| 日期 | date | 治疗日期 |
| 患者ID | str | 患者编号 |
| 治疗项目 | str | 项目名称 |
| 项目编码 | str | 医保编码（可选） |
| 单价 | float | 项目单价（元） |
| 数量 | int | 次数 |
| 金额 | float | 收费金额（元） |
| 医师 | str | 操作医师 |
| 科室 | str | 科室 |

### 5. 医保结算/报销表 (insurance)
| 列名 | 类型 | 说明 |
|------|------|------|
| 结算日期 | date | 结算日期 |
| 患者ID | str | 患者编号 |
| 总金额 | float | 总费用（元） |
| 统筹支付 | float | 统筹基金支付（元） |
| 个账支付 | float | 个人账户支付（元） |
| 自费金额 | float | 自费部分（元） |
| 结算状态 | str | 成功/拒付/扣减 |
| 拒付原因 | str | 拒付/扣减原因（可选） |

### 6. 医师/技师工作量表 (staff)
| 列名 | 类型 | 说明 |
|------|------|------|
| 日期 | date | 工作日期 |
| 姓名 | str | 医师/技师姓名 |
| 岗位 | str | 医师/技师/护士 |
| 科室 | str | 所属科室 |
| 接诊人次 | int | 当日接诊人次 |
| 治疗人次 | int | 当日治疗操作人次 |
| 加班时长 | float | 加班小时数（可选） |

## 核心 KPI 公式

### 营收维度
- **日均营收** = SUM(收入金额) / 营业天数
- **客单价** = SUM(收入金额) / 就诊人次
- **医保占比** = SUM(医保支付) / SUM(收入金额) * 100%
- **科室营收占比** = 科室收入 / 总收入 * 100%

### 物料维度
- **耗材成本率** = SUM(物料金额) / SUM(收入金额) * 100%
- **单次治疗耗材成本** = SUM(治疗用物料金额) / 治疗总人次
- **高值耗材占比** = 高值耗材金额 / 总物料金额 * 100%

### 就诊维度
- **日均门诊量** = SUM(就诊人次) / 营业天数
- **复诊率** = 复诊人次 / 总就诊人次 * 100%
- **医保患者占比** = 医保就诊人次 / 总就诊人次 * 100%

### 治疗维度
- **热门项目 TOP10** = 按收费金额降序排列
- **项目均价** = 项目总金额 / 项目总次数
- **人均治疗项目数** = 治疗总次数 / 就诊人次

### 医保维度
- **医保结算成功率** = 成功笔数 / 总结算笔数 * 100%
- **拒付率** = 拒付笔数 / 总结算笔数 * 100%
- **平均结算周期** = AVG(结算日期 - 治疗日期)

### 人效维度
- **人均产值** = 总收入 / 在岗人数
- **人均接诊量** = 总就诊人次 / 医师人数
- **医师产值排名** = 按个人对应收入降序

### 交叉维度
- **盈利能力** = (总收入 - 物料成本) / 总收入 * 100%（毛利率近似）
- **单患者贡献值** = 总收入 / 独立患者数
- **成本收入弹性** = 物料成本增长率 / 收入增长率

## 异常检测阈值

| 指标 | 预警条件 | 级别 |
|------|---------|------|
| 日营收 | 环比下降 > 20% | 红色预警 |
| 耗材成本率 | > 30% 或环比上升 > 5pp | 黄色预警 |
| 客单价 | 环比波动 > 15% | 黄色预警 |
| 医保拒付率 | > 5% | 红色预警 |
| 复诊率 | < 40% | 黄色预警 |
| 人均接诊量 | > 30人/天 或 < 5人/天 | 黄色预警 |
```

- [ ] **步骤 2：提交**

```bash
git add skills/hospital-ops-daily-report/metrics.md
git commit -m "feat(hospital-ops): add KPI definitions and data schemas"
```

---

### 任务 2：构建测试数据夹具

**涉及文件：**
- 创建：`tests/fixtures/sample_revenue.xlsx`
- 创建：`tests/fixtures/sample_materials.xlsx`
- 创建：`tests/fixtures/sample_visits.xlsx`
- 创建：`tests/fixtures/sample_treatments.xlsx`
- 创建：`tests/fixtures/sample_insurance.xlsx`
- 创建：`tests/fixtures/sample_staff.xlsx`
- 创建：`tests/generate_fixtures.py`

- [ ] **步骤 1：创建夹具生成脚本**

一个小脚本，根据 `metrics.md` 中定义的 Schema 创建 6 个示例 XLSX 文件，包含真实的测试数据。每个文件应包含 7 天数据，且有足够的变化来触发异常检测。

```python
"""Generate minimal XLSX fixtures for hospital_ops_analysis tests."""
import datetime
from pathlib import Path
from openpyxl import Workbook

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def _write(wb: Workbook, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)

def generate_revenue():
    wb = Workbook()
    ws = wb.active
    ws.title = "收入明细"
    ws.append(["日期", "科室", "医师", "项目类别", "收入金额", "医保支付", "自费支付", "患者ID"])
    base = datetime.date(2026, 4, 1)
    rows = [
        (base, "针灸科", "张医师", "治疗", 350, 280, 70, "P001"),
        (base, "针灸科", "张医师", "治疗", 420, 336, 84, "P002"),
        (base, "推拿科", "李医师", "治疗", 280, 224, 56, "P003"),
        (base + datetime.timedelta(1), "针灸科", "张医师", "治疗", 500, 400, 100, "P004"),
        (base + datetime.timedelta(1), "推拿科", "李医师", "治疗", 310, 248, 62, "P005"),
        (base + datetime.timedelta(1), "推拿科", "王医师", "药品", 150, 120, 30, "P006"),
        (base + datetime.timedelta(2), "针灸科", "张医师", "治疗", 60, 48, 12, "P007"),  # 异常：低值
    ]
    for r in rows:
        ws.append(r)
    _write(wb, FIXTURES_DIR / "sample_revenue.xlsx")

def generate_materials():
    wb = Workbook()
    ws = wb.active
    ws.title = "物料消耗"
    ws.append(["日期", "物料名称", "规格", "数量", "单价", "金额", "科室", "用途"])
    base = datetime.date(2026, 4, 1)
    rows = [
        (base, "一次性针灸针", "0.25x40mm", 100, 0.5, 50, "针灸科", "治疗"),
        (base, "艾条", "标准", 20, 8, 160, "针灸科", "治疗"),
        (base + datetime.timedelta(1), "一次性针灸针", "0.25x40mm", 120, 0.5, 60, "针灸科", "治疗"),
        (base + datetime.timedelta(1), "推拿油", "500ml", 2, 45, 90, "推拿科", "治疗"),
        (base + datetime.timedelta(2), "一次性针灸针", "0.25x40mm", 500, 0.5, 250, "针灸科", "治疗"),  # 异常：激增
    ]
    for r in rows:
        ws.append(r)
    _write(wb, FIXTURES_DIR / "sample_materials.xlsx")

def generate_visits():
    wb = Workbook()
    ws = wb.active
    ws.title = "就诊记录"
    ws.append(["日期", "患者ID", "科室", "医师", "就诊类型", "支付类型"])
    base = datetime.date(2026, 4, 1)
    rows = [
        (base, "P001", "针灸科", "张医师", "初诊", "医保"),
        (base, "P002", "针灸科", "张医师", "复诊", "医保"),
        (base, "P003", "推拿科", "李医师", "初诊", "自费"),
        (base + datetime.timedelta(1), "P004", "针灸科", "张医师", "初诊", "医保"),
        (base + datetime.timedelta(1), "P005", "推拿科", "李医师", "复诊", "医保"),
        (base + datetime.timedelta(1), "P006", "推拿科", "王医师", "初诊", "医保"),
        (base + datetime.timedelta(2), "P007", "针灸科", "张医师", "初诊", "自费"),
    ]
    for r in rows:
        ws.append(r)
    _write(wb, FIXTURES_DIR / "sample_visits.xlsx")

def generate_treatments():
    wb = Workbook()
    ws = wb.active
    ws.title = "治疗明细"
    ws.append(["日期", "患者ID", "治疗项目", "项目编码", "单价", "数量", "金额", "医师", "科室"])
    base = datetime.date(2026, 4, 1)
    rows = [
        (base, "P001", "针刺", "HLZ001", 50, 1, 50, "张医师", "针灸科"),
        (base, "P001", "电针", "HLZ002", 60, 1, 60, "张医师", "针灸科"),
        (base, "P002", "灸法", "HLZ003", 40, 2, 80, "张医师", "针灸科"),
        (base, "P003", "推拿", "HLZ004", 70, 1, 70, "李医师", "推拿科"),
        (base + datetime.timedelta(1), "P004", "针刺", "HLZ001", 50, 2, 100, "张医师", "针灸科"),
        (base + datetime.timedelta(1), "P005", "推拿", "HLZ004", 70, 1, 70, "李医师", "推拿科"),
    ]
    for r in rows:
        ws.append(r)
    _write(wb, FIXTURES_DIR / "sample_treatments.xlsx")

def generate_insurance():
    wb = Workbook()
    ws = wb.active
    ws.title = "医保结算"
    ws.append(["结算日期", "患者ID", "总金额", "统筹支付", "个账支付", "自费金额", "结算状态", "拒付原因"])
    base = datetime.date(2026, 4, 1)
    rows = [
        (base, "P001", 350, 200, 80, 70, "成功", ""),
        (base, "P002", 420, 250, 86, 84, "成功", ""),
        (base + datetime.timedelta(1), "P004", 500, 300, 100, 100, "成功", ""),
        (base + datetime.timedelta(1), "P005", 310, 180, 68, 62, "拒付", "诊断与治疗不一致"),
        (base + datetime.timedelta(1), "P006", 150, 90, 30, 30, "扣减", "超量开药"),
    ]
    for r in rows:
        ws.append(r)
    _write(wb, FIXTURES_DIR / "sample_insurance.xlsx")

def generate_staff():
    wb = Workbook()
    ws = wb.active
    ws.title = "工作量"
    ws.append(["日期", "姓名", "岗位", "科室", "接诊人次", "治疗人次", "加班时长"])
    base = datetime.date(2026, 4, 1)
    rows = [
        (base, "张医师", "医师", "针灸科", 12, 10, 0),
        (base, "李医师", "医师", "推拿科", 8, 8, 1.5),
        (base + datetime.timedelta(1), "张医师", "医师", "针灸科", 15, 12, 2),
        (base + datetime.timedelta(1), "李医师", "医师", "推拿科", 6, 5, 0),
        (base + datetime.timedelta(1), "王医师", "医师", "推拿科", 4, 3, 0),
        (base + datetime.timedelta(2), "张医师", "医师", "针灸科", 2, 1, 0),  # 异常：低值
    ]
    for r in rows:
        ws.append(r)
    _write(wb, FIXTURES_DIR / "sample_staff.xlsx")

if __name__ == "__main__":
    generate_revenue()
    generate_materials()
    generate_visits()
    generate_treatments()
    generate_insurance()
    generate_staff()
    print(f"Fixtures generated in {FIXTURES_DIR}")
```

- [ ] **步骤 2：运行夹具生成器**

```powershell
.\.venv\Scripts\Activate.ps1
python tests/generate_fixtures.py
```

预期输出："Fixtures generated in tests\fixtures"，且创建 6 个 `.xlsx` 文件。

- [ ] **步骤 3：提交**

```bash
git add tests/generate_fixtures.py tests/fixtures/
git commit -m "test: add fixture generator and sample XLSX for ops analysis"
```

---

### 任务 3：编写分析引擎的失败测试用例

**涉及文件：**
- 创建：`tests/test_hospital_ops_analysis.py`

- [ ] **步骤 1：编写数据加载和 KPI 计算的单元测试**

```python
"""Tests for hospital_ops_analysis module."""
import datetime
import json
from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def revenue_df():
    from scripts.hospital_ops_analysis import load_source
    return load_source(FIXTURES / "sample_revenue.xlsx", "revenue")


@pytest.fixture
def all_sources():
    from scripts.hospital_ops_analysis import load_all_sources
    return load_all_sources(FIXTURES)


class TestLoadSource:
    def test_load_revenue_returns_dataframe(self, revenue_df):
        assert isinstance(revenue_df, pd.DataFrame)
        assert len(revenue_df) > 0

    def test_revenue_has_required_columns(self, revenue_df):
        required = {"日期", "科室", "收入金额", "医保支付", "自费支付"}
        assert required.issubset(set(revenue_df.columns))

    def test_date_column_is_datetime(self, revenue_df):
        assert pd.api.types.is_datetime64_any_dtype(revenue_df["日期"])


class TestLoadAllSources:
    def test_returns_dict_of_dataframes(self, all_sources):
        assert isinstance(all_sources, dict)
        assert "revenue" in all_sources
        assert "materials" in all_sources

    def test_missing_source_returns_none(self, tmp_path):
        from scripts.hospital_ops_analysis import load_all_sources
        result = load_all_sources(tmp_path)
        for v in result.values():
            assert v is None


class TestRevenueKPIs:
    def test_daily_avg_revenue(self, all_sources):
        from scripts.hospital_ops_analysis import compute_revenue_kpis
        kpis = compute_revenue_kpis(all_sources["revenue"])
        assert "daily_avg_revenue" in kpis
        assert kpis["daily_avg_revenue"] > 0

    def test_insurance_ratio(self, all_sources):
        from scripts.hospital_ops_analysis import compute_revenue_kpis
        kpis = compute_revenue_kpis(all_sources["revenue"])
        assert 0 <= kpis["insurance_ratio"] <= 1

    def test_revenue_by_department(self, all_sources):
        from scripts.hospital_ops_analysis import compute_revenue_kpis
        kpis = compute_revenue_kpis(all_sources["revenue"])
        assert "dept_breakdown" in kpis
        assert len(kpis["dept_breakdown"]) > 0


class TestMaterialKPIs:
    def test_material_cost_rate(self, all_sources):
        from scripts.hospital_ops_analysis import compute_material_kpis
        kpis = compute_material_kpis(
            all_sources["materials"], all_sources["revenue"]
        )
        assert "cost_rate" in kpis
        assert 0 <= kpis["cost_rate"] <= 1


class TestAnomalyDetection:
    def test_detects_revenue_drop(self, all_sources):
        from scripts.hospital_ops_analysis import detect_anomalies
        anomalies = detect_anomalies(all_sources)
        alerts = [a for a in anomalies if a["metric"] == "daily_revenue"]
        assert len(alerts) > 0, "应检测到第 3 天营收异常下降"

    def test_detects_material_spike(self, all_sources):
        from scripts.hospital_ops_analysis import detect_anomalies
        anomalies = detect_anomalies(all_sources)
        alerts = [a for a in anomalies if a["metric"] == "material_consumption"]
        assert len(alerts) > 0, "应检测到第 3 天物料消耗激增"


class TestAnalyzeAll:
    def test_full_analysis_returns_report(self, all_sources):
        from scripts.hospital_ops_analysis import analyze_all
        report = analyze_all(all_sources)
        assert "summary" in report
        assert "revenue" in report
        assert "materials" in report
        assert "visits" in report
        assert "treatments" in report
        assert "insurance" in report
        assert "staff" in report
        assert "anomalies" in report
        assert "suggestions" in report

    def test_report_is_json_serializable(self, all_sources):
        from scripts.hospital_ops_analysis import analyze_all
        report = analyze_all(all_sources)
        json.dumps(report, ensure_ascii=False, default=str)
```

- [ ] **步骤 2：运行测试验证失败**

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_hospital_ops_analysis.py -v
```

预期：所有测试 FAIL，报 `ModuleNotFoundError: No module named 'scripts.hospital_ops_analysis'`

- [ ] **步骤 3：提交**

```bash
git add tests/test_hospital_ops_analysis.py
git commit -m "test: add failing tests for hospital ops analysis engine"
```

---

### 任务 4：实现分析引擎 — 数据加载

**涉及文件：**
- 创建：`scripts/hospital_ops_analysis.py`

- [ ] **步骤 1：实现 `load_source` 和 `load_all_sources`**

```python
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
```

- [ ] **步骤 2：运行数据加载相关测试**

```powershell
python -m pytest tests/test_hospital_ops_analysis.py::TestLoadSource -v
python -m pytest tests/test_hospital_ops_analysis.py::TestLoadAllSources::test_returns_dict_of_dataframes -v
```

预期：`TestLoadSource` 和字典测试通过。

- [ ] **步骤 3：提交**

```bash
git add scripts/hospital_ops_analysis.py
git commit -m "feat(hospital-ops): implement data loading for 6 source categories"
```

---

### 任务 5：实现 KPI 计算函数

**涉及文件：**
- 修改：`scripts/hospital_ops_analysis.py`（追加函数）

- [ ] **步骤 1：实现全部 KPI 计算函数**

在 `scripts/hospital_ops_analysis.py` 末尾追加以下函数：

```python
def compute_revenue_kpis(df: pd.DataFrame) -> dict[str, Any]:
    total = df["收入金额"].sum()
    days = df["日期"].dt.date.nunique()
    dept = df.groupby("科室")["收入金额"].sum()
    return {
        "total_revenue": float(total),
        "daily_avg_revenue": float(total / max(days, 1)),
        "insurance_ratio": float(df["医保支付"].sum() / max(total, 1)),
        "avg_ticket": float(total / max(len(df), 1)),
        "dept_breakdown": dept.to_dict(),
        "daily_trend": df.groupby(df["日期"].dt.date)["收入金额"]
            .sum().reset_index().rename(columns={"日期": "date", "收入金额": "amount"})
            .to_dict(orient="records"),
    }


def compute_material_kpis(
    mat_df: pd.DataFrame, rev_df: pd.DataFrame | None = None
) -> dict[str, Any]:
    total_cost = mat_df["金额"].sum()
    rev_total = rev_df["收入金额"].sum() if rev_df is not None else 0
    dept = mat_df.groupby("科室")["金额"].sum()
    return {
        "total_cost": float(total_cost),
        "cost_rate": float(total_cost / max(rev_total, 1)) if rev_total else 0,
        "dept_breakdown": dept.to_dict(),
        "top_items": mat_df.groupby("物料名称")["金额"]
            .sum().sort_values(ascending=False).head(10).to_dict(),
        "daily_trend": mat_df.groupby(mat_df["日期"].dt.date)["金额"]
            .sum().reset_index().rename(columns={"日期": "date", "金额": "amount"})
            .to_dict(orient="records"),
    }


def compute_visit_kpis(df: pd.DataFrame) -> dict[str, Any]:
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
    top = df.groupby("治疗项目")["金额"].agg(["sum", "count"]).sort_values(
        "sum", ascending=False
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
```

- [ ] **步骤 2：运行 KPI 测试**

```powershell
python -m pytest tests/test_hospital_ops_analysis.py::TestRevenueKPIs -v
python -m pytest tests/test_hospital_ops_analysis.py::TestMaterialKPIs -v
```

预期：所有 KPI 测试通过。

- [ ] **步骤 3：提交**

```bash
git add scripts/hospital_ops_analysis.py
git commit -m "feat(hospital-ops): implement KPI computation for all 6 dimensions"
```

---

### 任务 6：实现异常检测和优化建议生成

**涉及文件：**
- 修改：`scripts/hospital_ops_analysis.py`（追加函数）

- [ ] **步骤 1：实现 `detect_anomalies` 和 `generate_suggestions`**

在 `scripts/hospital_ops_analysis.py` 末尾追加：

```python
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
    suggestions: list[dict[str, str]] = []

    for a in anomalies:
        if a["metric"] == "daily_revenue" and a["level"] == "red":
            suggestions.append({
                "category": "营收",
                "priority": "高",
                "suggestion": f"[{a['date']}] {a['message']}。建议排查当日排班是否异常、是否有停诊，并对比同期数据确认是否为周期性波动。",
            })
        elif a["metric"] == "material_consumption":
            suggestions.append({
                "category": "物料",
                "priority": "中",
                "suggestion": f"[{a['date']}] {a['message']}。建议核查是否为批量领用或异常浪费，对照治疗量确认耗材用量合理性。",
            })
        elif a["metric"] == "insurance_rejection":
            suggestions.append({
                "category": "医保",
                "priority": "高",
                "suggestion": f"{a['message']}。建议立即排查拒付原因，重点关注诊断-治疗一致性和医保编码合规性。",
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
            "suggestion": f"复诊率 {visit_kpis['revisit_rate']:.0%}，低于 {THRESHOLDS['revisit_rate_min']:.0%} 基准。建议加强诊后随访和疗程管理。",
        })

    return suggestions
```

- [ ] **步骤 2：运行异常检测和全量分析测试**

```powershell
python -m pytest tests/test_hospital_ops_analysis.py::TestAnomalyDetection -v
```

预期：两个异常检测测试通过。

- [ ] **步骤 3：提交**

```bash
git add scripts/hospital_ops_analysis.py
git commit -m "feat(hospital-ops): implement anomaly detection and suggestion generation"
```

---

### 任务 7：实现 `analyze_all` 和 XLSX 报告生成

**涉及文件：**
- 修改：`scripts/hospital_ops_analysis.py`（追加函数 + CLI 入口）

- [ ] **步骤 1：实现 `analyze_all` 和 `generate_xlsx_report`**

在 `scripts/hospital_ops_analysis.py` 末尾追加：

```python
def analyze_all(sources: dict[str, pd.DataFrame | None]) -> dict[str, Any]:
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


def generate_xlsx_report(report: dict[str, Any], output_path: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    header_font = Font(bold=True, size=12)
    header_fill = PatternFill("solid", fgColor="4472C4")
    header_font_white = Font(bold=True, size=11, color="FFFFFF")
    red_fill = PatternFill("solid", fgColor="FFC7CE")
    yellow_fill = PatternFill("solid", fgColor="FFEB9C")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # -- 概览 Sheet --
    ws = wb.active
    ws.title = "分析概览"
    ws["A1"] = "每日经营数据分析报告"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A2"] = f"分析日期：{report.get('summary', {}).get('analysis_date', '')}"
    ws["A3"] = f"数据源：{', '.join(report.get('summary', {}).get('sources_loaded', []))}"

    row = 5
    ws.cell(row, 1, "预警与建议").font = header_font
    row += 1
    for col, title in enumerate(["类别", "优先级", "建议"], 1):
        c = ws.cell(row, col, title)
        c.font, c.fill, c.border = header_font_white, header_fill, thin_border
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

    # -- 营收分析 Sheet --
    if "revenue" in report:
        ws_rev = wb.create_sheet("营收分析")
        rv = report["revenue"]
        ws_rev["A1"] = "营收 KPI"
        ws_rev["A1"].font = header_font
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

    # -- 异常预警 Sheet --
    if report.get("anomalies"):
        ws_anom = wb.create_sheet("异常预警")
        ws_anom["A1"] = "异常预警明细"
        ws_anom["A1"].font = header_font
        for col, title in enumerate(["指标", "级别", "日期", "说明"], 1):
            c = ws_anom.cell(2, col, title)
            c.font, c.fill, c.border = header_font_white, header_fill, thin_border
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
```

- [ ] **步骤 2：在文件末尾添加 CLI 入口**

```python
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
```

- [ ] **步骤 3：运行全部测试**

```powershell
python -m pytest tests/test_hospital_ops_analysis.py -v
```

预期：所有测试通过。

- [ ] **步骤 4：使用夹具数据端到端运行脚本**

```powershell
python scripts/hospital_ops_analysis.py --input tests/fixtures --output tests/fixtures/output --date 2026-04-13
```

预期：JSON 输出 `"status": "success"` 并检测到异常。

- [ ] **步骤 5：提交**

```bash
git add scripts/hospital_ops_analysis.py
git commit -m "feat(hospital-ops): implement full analysis pipeline with XLSX report generation"
```

---

### 任务 8：编写 Agent Skill SKILL.md

**涉及文件：**
- 创建：`skills/hospital-ops-daily-report/SKILL.md`

- [ ] **步骤 1：编写完整的 SKILL.md**

```markdown
---
name: hospital-ops-daily-report
version: v1
description: 当用户提供医院每日经营原始数据表格（营业额、物料消耗、门诊量、治疗项目、医保结算、人员工作量等XLSX文件），需要进行综合经营分析并给出优化建议时使用。
---

# 医院每日经营数据分析（v1）

**重要：所有输出必须全部使用中文。**

## 目标

本技能用于将零散的医院运营 XLSX 数据文件转化为结构化的经营分析报告：

1. 接收用户提供的一个或多个原始数据表格
2. 运行 `scripts/hospital_ops_analysis.py` 完成自动化分析
3. 可选：查询共享知识库获取价格标准和政策基准进行对标分析
4. 产出 Markdown 摘要报告（在对话中展示）和 XLSX 详细报告（保存文件）

## 触发语

以下请求优先触发本技能：

- "分析今天的经营数据"
- "帮我看下这些运营报表"
- "做个每日经营分析"
- "分析一下营业额和耗材数据"
- "生成经营分析报告"

## 前置条件

1. 在仓库根目录执行
2. 使用当前项目的 Python venv
3. `pandas` 与 `openpyxl` 可用；如缺失，安装：

    ```powershell
    uv pip install --python .\.venv\Scripts\python.exe pandas openpyxl
    ```

## 支持的数据源

| 类别 | 文件关键词 | 必需列 |
|------|-----------|--------|
| 营业额/收入 | 营业额、收入 | 日期, 科室, 收入金额, 医保支付, 自费支付 |
| 物料/耗材 | 物料、耗材 | 日期, 物料名称, 数量, 单价, 金额, 科室 |
| 门诊量 | 门诊、就诊 | 日期, 患者ID, 科室, 医师, 就诊类型, 支付类型 |
| 治疗项目 | 治疗项目、治疗明细 | 日期, 治疗项目, 单价, 数量, 金额 |
| 医保结算 | 医保、结算 | 结算日期, 总金额, 统筹支付, 结算状态 |
| 工作量 | 工作量、人员 | 日期, 姓名, 岗位, 接诊人次, 治疗人次 |

**列名匹配规则：** 脚本按关键词匹配文件名，用户提供的文件如果列名不完全一致，agent 应先读取文件表头，确认列名映射后再运行脚本。如需列名重映射，在运行脚本前用 pandas 预处理。

## 共享知识库路径

优先读取 `_shared_runtime/knowledge-base-paths.json`：

- `<KB_ROOT>` = `knowledgeBase.rootDir`
- `<KB_SOURCE_ROOT>` = `knowledgeBase.sourceDocsDir`

共享文件缺失时回退到：

- `<KB_ROOT>` = `docs/knowledge-base`
- `<KB_SOURCE_ROOT>` = `docs/医院材料学习`

## 跨技能协作约定

- 本技能只读共享知识库，用于查询价格标准和政策基准对标。
- 如需按最新政策进行合规对标，先由 `sh-yb-policy-monitor` 抓取最新政策、`knowledge-base-update` 刷新知识库后再执行分析。
- 如分析中发现治疗项目合规风险，建议用户使用 `tcm-treatment-review` 进行详细审查。

## 执行流程

### 第一步：收集数据文件

向用户确认以下信息：

1. 数据文件存放路径（一个目录，或多个文件路径）
2. 分析的目标日期（默认今天）
3. 是否需要对标知识库中的价格/政策基准

### 第二步：检查数据文件

读取每个 XLSX 的表头（前 3 行），确认：

- 文件能被正确分类到 6 个数据源之一
- 列名与预期 schema 兼容（参见 `skills/hospital-ops-daily-report/metrics.md`）
- 如列名不一致，使用 pandas 创建临时预处理脚本进行重映射

### 第三步：运行分析脚本

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/hospital_ops_analysis.py --input "<数据目录>" --output "<输出目录>" --date "YYYY-MM-DD"
```

脚本输出 JSON 格式结果，包含：`status`, `sources_loaded`, `json_report`, `xlsx_report`, `anomalies`, `suggestions`

### 第四步：读取分析结果

读取 JSON 报告文件，提取各维度 KPI 和异常预警。

### 第五步：知识库对标（可选）

如用户要求对标分析，通过 MCP 查询知识库：

- `query("中医治疗项目 医保价格标准")` — 获取价格基准
- `query("耗材 成本 标准")` — 获取耗材成本基准
- `wiki_read("医院运营管理")` — 获取运营管理知识

将对标结果纳入优化建议。

### 第六步：输出报告

**Markdown 摘要格式（在对话中输出）：**

    ## 每日经营分析报告 — YYYY-MM-DD

    ### 一、核心指标概览
    | 指标 | 数值 | 环比 |
    |------|------|------|
    | 总营收 | ¥XX,XXX | +X% |
    | 日均门诊量 | XX 人次 | -X% |
    | 耗材成本率 | XX% | +Xpp |
    | 医保结算成功率 | XX% | - |
    | 人均产值 | ¥X,XXX | +X% |

    ### 二、异常预警
    - [红色预警内容]
    - [黄色预警内容]

    ### 三、各维度分析
    #### 营收分析
    - ...
    #### 物料分析
    - ...
    #### 就诊分析
    - ...
    #### 治疗项目分析
    - ...
    #### 医保分析
    - ...
    #### 人效分析
    - ...

    ### 四、优化建议
    #### 高优先级
    1. ...
    #### 中优先级
    1. ...

    ### 五、详细报告
    XLSX 报告已保存至：`<路径>`

**XLSX 报告**由脚本自动生成，包含多个 Sheet：分析概览、营收分析、异常预警等。

## 失败处理

- 目录中无可识别的 XLSX 文件：提示用户确认文件路径和命名
- 列名不匹配：展示实际列名，建议用户确认对应关系
- 部分数据源缺失：使用已有数据源完成分析，在报告中标注缺失维度
- 知识库不可用：跳过对标分析，在报告中注明

## 指标与基准参考

详见 `skills/hospital-ops-daily-report/metrics.md`
```

- [ ] **步骤 2：提交**

```bash
git add skills/hospital-ops-daily-report/SKILL.md
git commit -m "feat(hospital-ops): add agent skill SKILL.md for daily ops analysis"
```

---

### 任务 9：创建版本化副本并部署

**涉及文件：**
- 创建：`skills/hospital-ops-daily-report/v1/SKILL.md`（从根目录复制）
- 创建：`skills/hospital-ops-daily-report/v1/metrics.md`（从根目录复制）

- [ ] **步骤 1：创建 v1 目录并复制文件**

```powershell
New-Item -ItemType Directory -Path skills/hospital-ops-daily-report/v1 -Force
Copy-Item skills/hospital-ops-daily-report/SKILL.md skills/hospital-ops-daily-report/v1/SKILL.md
Copy-Item skills/hospital-ops-daily-report/metrics.md skills/hospital-ops-daily-report/v1/metrics.md
```

- [ ] **步骤 2：部署到 Cursor skills 目录**

如果 `scripts/deploy_agent_skills.py` 支持，使用部署脚本；否则手动复制：

```powershell
$dest = "$env:USERPROFILE\.cursor\skills\hospital-ops-daily-report"
New-Item -ItemType Directory -Path $dest -Force
Copy-Item skills/hospital-ops-daily-report/SKILL.md $dest/SKILL.md
```

- [ ] **步骤 3：验证部署**

```powershell
Get-Content "$env:USERPROFILE\.cursor\skills\hospital-ops-daily-report\SKILL.md" | Select-Object -First 5
```

预期：显示 SKILL.md 的 YAML 前置元数据。

- [ ] **步骤 4：提交**

```bash
git add skills/hospital-ops-daily-report/
git commit -m "feat(hospital-ops): add v1 versioned copies and finalize skill structure"
```

---

### 任务 10：端到端验证

**涉及文件：**（无新文件）

- [ ] **步骤 1：运行完整测试套件**

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_hospital_ops_analysis.py -v --tb=short
```

预期：所有测试通过。

- [ ] **步骤 2：CLI 端到端运行**

```powershell
python scripts/hospital_ops_analysis.py --input tests/fixtures --output tests/fixtures/output --date 2026-04-13
```

预期：JSON 输出 `"status": "success"`，同时创建 `analysis_2026-04-13.json` 和 `经营分析报告_2026-04-13.xlsx`。

- [ ] **步骤 3：验证 XLSX 报告可正确打开**

打开生成的 XLSX 文件，验证包含以下 Sheet："分析概览"、"营收分析"、"异常预警"。

- [ ] **步骤 4：最终提交**

```bash
git add -A
git commit -m "feat(hospital-ops): complete daily operations analysis skill v1"
```
