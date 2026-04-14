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
