"""Used only with the synthetic workbooks created by smoke_excel.ps1."""
import hashlib
import sys
import json
from decimal import Decimal
from pathlib import Path
from market_rates.demo import fixtures, offer
from market_rates.rules import build_views, build_updates
from market_rates.export import make_plan
from market_rates.xlsx_read import read_xlsx
from market_rates.common import load

def close_rate(actual, expected):
    # XLSX numeric cells use IEEE-754 doubles; business rules still use Decimal.
    assert abs(Decimal(actual) - Decimal(expected)) < Decimal("0.000000000001"), (actual, expected)

extra_product='--extra-product' in sys.argv
args=[a for a in sys.argv if a!='--extra-product']
root = Path(args[1])
config, run = fixtures()
if len(args) == 2:
    offers = run["llm"]["offers"]
    withdrawn = offer("DEMO_C", "demo-c", rate=None); withdrawn["availability"] = "withdrawn"
    offers.append(withdrawn)
    if extra_product:offers.append(offer('DEMO_A','demo-a-new',rate='1.6'))
    previous = {"as_of": "2026-09-16", "offers": [offer(rate="1.5"), offer("DEMO_C", "demo-c", rate="1.4")]}
    result = {"pending": 0, "demo": True, "run_id": "excel-smoke", "as_of": "2026-09-24",
              "updates": build_updates(offers, previous, config, "2026-09-24"), **build_views(offers, config, {}, "2026-09-24")}
    mapping = {"template_sha256": hashlib.sha256((root / "report-template.xlsx").read_bytes()).hexdigest(),
               "entries": [{"group_id": "DEMO_A/demo-a/SGD/promo/6/M", "row": 5, "expected_bank_label": "DEMO_A", "confirmed": True},
                           {"group_id": "DEMO_B/demo-b/SGD/promo/6/M", "insert_before": 5, "expected_bank_label": "DEMO_A", "confirmed": True},
                           {"group_id": "DEMO_C/demo-c/SGD/promo/6/M", "row": 9, "expected_bank_label": "DEMO_C", "confirmed": True}]}
    if extra_product:
        mapping['entries'][1].update(insert_before=9,expected_bank_label='DEMO_C')
        mapping['entries'].append(dict(group_id='DEMO_A/demo-a-new/SGD/promo/6/M',insert_before=5,bank_row=5,expected_bank_label='DEMO_A',confirmed=True))
    print(make_plan(result, config, mapping, root / "report-template.xlsx", root / "rainbow-template.xlsx", root / "output"))
else:
    plan = load(root / "output/export-plan.json")
    data = read_xlsx(plan["report_output"])
    close_rate(data["SGD促销"]["C6"], "0.017")
    close_rate(data["SGD促销"]["D6"], "0.015")
    close_rate(data["SGD促销"]["E6"], "0.014")
    close_rate(data["SGD促销"]["C5"], "0.016" if extra_product else "0.0165")
    assert data["SGD促销"].get("D5") is None
    assert Decimal(data["SGD促销"]["F6"]).quantize(Decimal("0.000001")) == Decimal("0.002000")
    assert data["USD挂牌"]["A1"] == "UNCHANGED"
    stopped=11 if extra_product else 10
    assert data["SGD促销"][f"C{stopped}"] == "-"
    close_rate(data["SGD促销"][f"D{stopped}"], "0.014")
    assert "已停止提供" in data["SGD促销"][f"B{stopped}"]
    assert "已停止提供" in data["本期逐项检查"].values()
    close_rate(data["最高报价汇总 "]["E4"], "0.018")
    close_rate(data["最高报价汇总 "]["E5"], "0.0165")
    rainbow = read_xlsx(plan["rainbow_output"])
    close_rate(rainbow["SGD Promotional Rate"]["H3"], "0.017")
    close_rate(rainbow["SGD Promotional Rate"]["H4"], "0.018")
    if extra_product:
        import openpyxl
        report_book=openpyxl.load_workbook(plan['report_output'],data_only=True)
        rainbow_book=openpyxl.load_workbook(plan['rainbow_output'],data_only=True)
        assert 'A5:A9' in {str(m) for m in report_book['SGD促销'].merged_cells.ranges}
        assert 'G3:G5' in {str(m) for m in rainbow_book['SGD Promotional Rate'].merged_cells.ranges}
        assert report_book['SGD促销']['A6'].value is None
        close_rate(rainbow['SGD Promotional Rate']['H5'],'0.016')
        assert rainbow_book['SGD Promotional Rate']['G6'].value=='DEMO_B'
    assert rainbow["Other"]["A1"] == "UNCHANGED"
    for prefix in ("report", "rainbow"):
        assert hashlib.sha256(Path(plan[prefix+"_template"]).read_bytes()).hexdigest() == plan[prefix+"_sha256"]
    print("PASS: inserted row, history column, previous values, recalculated delta, Personal rank, all-audience maximum, stopped status/audit, untouched scope, original file hashes")
