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
