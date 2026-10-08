#!/usr/bin/env python3
"""Excel由来の計算ルールで見積を算出し、転記しやすいMarkdownを生成する。"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


BASE_HOURS = {
    "画面": {"internal_design": 0.6, "pg_development": 1.0, "program_test": 0.5},
    "帳票": {"internal_design": 0.4, "pg_development": 1.0, "program_test": 0.4},
    "バッチ": {"internal_design": 0.4, "pg_development": 1.0, "program_test": 0.5},
}
PHASES = {
    "summary": ("見積.md", None),
    "conditions": ("01_見積条件.md", None),
    "functions": ("02_機能一覧.md", "01_見積条件.md"),
    "wbs": ("03_WBS.md", "02_機能一覧.md"),
    "allocation": ("04_ランク配賦.md", "03_WBS.md"),
    "pricing": ("05_見積金額.md", "04_ランク配賦.md"),
}
FUNCTION_DOCUMENT = "02_機能一覧.md"
WBS_CATALOG_PATH = Path(__file__).parents[1] / "references" / "スクラッチWBS項目.json"
COST_MASTER_PATH = Path(__file__).parents[1] / "references" / "原価マスタ_第3システム部.json"


class EstimateValidationError(ValueError):
    """見積データまたは承認状態に不足がある。"""


def round_half_hour(hours: float) -> float:
    return math.floor(hours * 2 + 0.5) / 2


def round_thousand(yen: float) -> int:
    return math.floor(yen / 1000 + 0.5) * 1000


def load_data(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise EstimateValidationError(f"見積データがありません: {path}") from error
    except json.JSONDecodeError as error:
        raise EstimateValidationError(f"JSON形式が不正です: {error.msg}") from error


def require_approved(path: Path) -> None:
    if not path.is_file():
        raise EstimateValidationError(f"前段の成果物がありません: {path.name}")
    if "status: approved" not in path.read_text(encoding="utf-8"):
        raise EstimateValidationError(f"前段の成果物が未承認です: {path.name} の status を approved にしてください。")


def validate_project(data: dict[str, Any]) -> dict[str, Any]:
    project = data.get("project")
    if not isinstance(project, dict):
        raise EstimateValidationError("project はオブジェクトである必要があります。")
    for field in ("customer_name", "project_name", "contract_type", "estimate_type"):
        if not isinstance(project.get(field), str) or not project[field].strip():
            raise EstimateValidationError(f"project.{field} が必要です。")
    return project


def nonnegative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def cost_master(data: dict[str, Any]) -> dict[str, Any]:
    master = load_data(Path(data.get("_cost_master_path", COST_MASTER_PATH)))
    if master.get("department_code") != "3375" or master.get("includes_indirect_cost") is not True:
        raise EstimateValidationError("原価マスタは間接原価を含む第3システム部（3375）の単価を指定してください。")
    if data.get("project", {}).get("cost_year") != master.get("fiscal_year"):
        raise EstimateValidationError("project.cost_year に原価マスタの年度を明示してください。2025年度値を現年度値とみなしません。")
    if str(data.get("project", {}).get("cost_department", "3375")) != "3375":
        raise EstimateValidationError("原価マスタは第3システム部（3375）だけを対象にします。")
    if not isinstance(master.get("cost_rates_per_hour"), dict) or not all(nonnegative_number(value) for value in master["cost_rates_per_hour"].values()) or not nonnegative_number(master.get("indirect_cost_per_hour")):
        raise EstimateValidationError("原価マスタの単価が不正です。")
    return master


def calculated_functions(data: dict[str, Any]) -> list[dict[str, Any]]:
    functions = data.get("functions")
    if not isinstance(functions, list) or not functions:
        raise EstimateValidationError("functions は1件以上の配列である必要があります。")
    result = []
    for index, item in enumerate(functions, 1):
        if not isinstance(item, dict) or not all(item.get(field) != "" and field in item for field in ("function_name", "function_type", "difficulty", "basis")):
            raise EstimateValidationError(f"functions[{index}] の必須項目が不足しています。")
        if item["function_type"] not in BASE_HOURS or not nonnegative_number(item["difficulty"]):
            raise EstimateValidationError(f"functions[{index}] の種別または難易度が不正です。")
        base = BASE_HOURS[item["function_type"]]
        result.append({**item, "internal_design_hours": round_half_hour(item["difficulty"] * base["internal_design"]), "pg_development_hours": round_half_hour(item["difficulty"] * base["pg_development"]), "program_test_hours": round_half_hour(item["difficulty"] * base["program_test"])})
    return result




def load_wbs_catalog() -> list[dict[str, str]]:
    try:
        catalog = json.loads(WBS_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EstimateValidationError(f"WBS項目カタログを読めません: {WBS_CATALOG_PATH}") from error
    if not isinstance(catalog, list):
        raise EstimateValidationError("WBS項目カタログは配列である必要があります。")
    return catalog


def parse_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def parse_hours(value: str, context: str) -> float:
    matched = re.fullmatch(r"\*{0,2}\s*(\d+(?:\.\d+)?)h\s*\*{0,2}", value)
    if not matched:
        raise EstimateValidationError(f"{context} の工数形式が不正です: {value}")
    return float(matched.group(1))


def verify_functions_document(path: Path, data: dict[str, Any]) -> None:
    if not path.is_file():
        raise EstimateValidationError(f"機能一覧がありません: {path.name}")
    lines = path.read_text(encoding="utf-8").splitlines()
    header_index = next((index for index, line in enumerate(lines) if line.startswith("|") and "機能名" in line and "難易度" in line), None)
    if header_index is None or header_index + 1 >= len(lines):
        raise EstimateValidationError(f"{path.name} に難易度を含む機能一覧表がありません。")
    headers = parse_markdown_row(lines[header_index])
    required_columns = ("機能名", "難易度", "内部設計", "PG開発", "プログラムテスト")
    if any(column not in headers for column in required_columns):
        raise EstimateValidationError(f"{path.name} の必須列が不足しています。")
    rows: dict[str, list[str]] = {}
    for line in lines[header_index + 1:]:
        if not line.startswith("|"):
            break
        cells = parse_markdown_row(line)
        if len(cells) != len(headers) or is_separator_row(cells):
            continue
        if cells[headers.index("機能名")] == "**合計**":
            break
        rows[cells[headers.index("機能名")]] = cells

    expected_functions = calculated_functions(data)
    for item in expected_functions:
        name = item["function_name"]
        cells = rows.get(name)
        if cells is None:
            raise EstimateValidationError(f"{path.name} に機能がありません: {name}")
        expected_values = {
            "難易度": float(item["difficulty"]),
            "内部設計": item["internal_design_hours"],
            "PG開発": item["pg_development_hours"],
            "プログラムテスト": item["program_test_hours"],
        }
        for column, expected in expected_values.items():
            actual = float(cells[headers.index(column)]) if column == "難易度" else parse_hours(cells[headers.index(column)], f"{name} の{column}")
            if actual != expected:
                raise EstimateValidationError(f"{path.name} の{name}の{column} {actual:.1f} が、難易度 {item['difficulty']} に基づく算定値 {expected:.1f} と一致しません。")

    totals = {"内部設計": 0.0, "PG開発": 0.0, "プログラムテスト": 0.0}
    for item in expected_functions:
        totals["内部設計"] += item["internal_design_hours"]
        totals["PG開発"] += item["pg_development_hours"]
        totals["プログラムテスト"] += item["program_test_hours"]
    total_row = rows.get("**合計**")
    if total_row:
        for column, expected in totals.items():
            actual = parse_hours(total_row[headers.index(column)], f"合計の{column}")
            if actual != expected:
                raise EstimateValidationError(f"{path.name} の合計{column} {actual:.1f}h が明細合計 {expected:.1f}h と一致しません。")


def build_wbs(data: dict[str, Any]) -> list[dict[str, Any]]:
    method = data.get("estimate_method", "functions")
    if method not in {"functions", "activities", "staffing", "hybrid"}:
        raise EstimateValidationError("estimate_method は functions / activities / staffing / hybrid です。")
    if method == "staffing":
        if data.get("wbs") or data.get("functions"):
            raise EstimateValidationError("staffing は体制工数だけを採用します。機能・活動工数を重ねて入力しないでください。")
        staffing = data.get("staffing")
        if not isinstance(staffing, list) or not staffing:
            raise EstimateValidationError("staffing は1件以上の体制配列である必要があります。")
        result = []
        for index, item in enumerate(staffing, 1):
            if not isinstance(item, dict) or not all(item.get(field) for field in ("task_name", "role", "basis")) or item["role"] not in {"SE", "PG"}:
                raise EstimateValidationError(f"staffing[{index}] の必須項目が不足しています。")
            if not all(nonnegative_number(item.get(field)) for field in ("people", "utilization", "months", "hours_per_month")) or item["utilization"] > 1 or any(item[field] == 0 for field in ("people", "months", "hours_per_month")):
                raise EstimateValidationError(f"staffing[{index}] の人数、稼働率、期間、月間基準時間が不正です。")
            quantity = item["people"] * item["utilization"] * item["months"]
            result.append({**item, "phase": item.get("phase", "体制・期間"), "quantity": quantity, "unit_hours": item["hours_per_month"], "hours": round_half_hour(quantity * item["hours_per_month"]), "source": "体制算出"})
        return result
    if data.get("staffing"):
        raise EstimateValidationError("体制を見積工数に採用する場合は estimate_method を staffing にしてください。活動工数との二重計上を避けます。")
    if method == "activities" and data.get("functions"):
        raise EstimateValidationError("activities では機能工数を算出しません。併用する場合は hybrid を指定してください。")
    functions = calculated_functions(data) if method in {"functions", "hybrid"} else []
    internal_design = sum(item["internal_design_hours"] for item in functions)
    wbs = [
        {"phase": "内部設計", "task_name": "プログラム設計書作成", "role": "SE", "hours": internal_design, "basis": "機能一覧の内部設計工数合計", "source": "自動算出"},
        {"phase": "内部設計", "task_name": "成果物レビュー", "role": "SE", "hours": round_half_hour(internal_design * 0.2), "basis": "プログラム設計書作成の20%", "source": "自動算出"},
        {"phase": "内部設計", "task_name": "成果物レビュー指摘対応", "role": "SE", "hours": round_half_hour(internal_design * 0.05), "basis": "プログラム設計書作成の5%", "source": "自動算出"},
        {"phase": "プログラム作成＋プログラムテスト", "task_name": "プログラム作成", "role": "PG", "hours": sum(item["pg_development_hours"] for item in functions), "basis": "機能一覧のPG開発工数合計", "source": "自動算出"},
        {"phase": "プログラム作成＋プログラムテスト", "task_name": "プログラムテスト", "role": "PG", "hours": sum(item["program_test_hours"] for item in functions), "basis": "機能一覧のプログラムテスト工数合計", "source": "自動算出"},
    ]
    if not functions:
        wbs = []
    activities = data.get("wbs", [])
    if not isinstance(activities, list):
        raise EstimateValidationError("wbs は活動配列である必要があります。")
    automatic_keys = {(item["phase"], item["task_name"], item["role"]) for item in wbs}
    for index, item in enumerate(activities, 1):
        if not isinstance(item, dict) or not all(field in item and item[field] != "" for field in ("phase", "task_name", "role", "quantity", "unit_hours", "basis")):
            raise EstimateValidationError(f"wbs[{index}] の必須項目が不足しています。")
        if item["role"] not in {"SE", "PG"} or not all(nonnegative_number(item[field]) for field in ("quantity", "unit_hours")):
            raise EstimateValidationError(f"wbs[{index}] の役割、数量、単位工数が不正です。")
        people = item.get("people", 1)
        if not nonnegative_number(people) or people <= 0:
            raise EstimateValidationError(f"wbs[{index}].people は正の人数である必要があります。")
        if (item["phase"], item["task_name"], item["role"]) in automatic_keys:
            raise EstimateValidationError("機能一覧から自動算出する作業を活動工数へ重ねて計上できません。")
        rounding = item.get("rounding", "half_hour")
        if rounding not in {"half_hour", "none"}:
            raise EstimateValidationError("wbs.rounding は half_hour または none を指定してください。")
        raw_hours = item["quantity"] * item["unit_hours"] * people
        wbs.append({**item, "hours": round_half_hour(raw_hours) if rounding == "half_hour" else raw_hours, "source": "入力"})
    result = [item for item in wbs if item["hours"] > 0]
    if not result:
        raise EstimateValidationError("算出対象の作業工数がありません。")
    return result


def wbs_checklist(data: dict[str, Any]) -> list[dict[str, Any]]:
    selected = {(item["phase"], item["task_name"], item["role"]): item for item in build_wbs(data)}
    rows = []
    for item in load_wbs_catalog():
        key = (item["phase"], item["task_name"])
        se_item = selected.get((*key, "SE"))
        pg_item = selected.get((*key, "PG"))
        rows.append({**item, "se": se_item, "pg": pg_item, "status": "対象" if se_item or pg_item else "未選択"})
    return rows


def wbs_totals(wbs: list[dict[str, Any]]) -> dict[str, float]:
    totals = defaultdict(float)
    for item in wbs:
        totals[item["role"]] += item["hours"]
    totals["total"] = totals["SE"] + totals["PG"]
    return totals


def allocation(data: dict[str, Any], wbs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = data.get("allocation")
    if not isinstance(items, list) or not items:
        raise EstimateValidationError("allocation は1件以上の配賦配列である必要があります。")
    allocated = defaultdict(float)
    result = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or not all(field in item and item[field] != "" for field in ("rank", "role", "hours", "basis")):
            raise EstimateValidationError(f"allocation[{index}] の必須項目が不足しています。")
        if not isinstance(item["rank"], str) or item["rank"] not in {"SE作業4", "SE作業3", "SE作業2", "SE作業1", "PG作業4", "PG作業3", "PG作業2", "PG作業1", "PJ管理費", "予備工数"}:
            raise EstimateValidationError("allocation.rank に確認済みの原価ランクを指定してください。")
        if item["rank"].startswith(("SE", "PG")) and not item["rank"].startswith(item["role"]):
            raise EstimateValidationError("原価ランクとSE／PG区分が一致しません。")
        rate = item.get("hourly_rate")
        if rate is None:
            master = cost_master(data)
            rate = master["cost_rates_per_hour"].get(item["rank"])
        if item["role"] not in {"SE", "PG"} or not all(nonnegative_number(value) for value in (item["hours"], rate)):
            raise EstimateValidationError(f"allocation[{index}] の役割、工数、単価が不正です。")
        allocated[item["role"]] += item["hours"]
        result.append({**item, "hourly_rate": rate, "amount": item["hours"] * rate, "rate_source": "案件指定" if "hourly_rate" in item else "第3システム部原価マスタ"})
    required = defaultdict(float)
    for item in wbs:
        required[item["role"]] += item["hours"]
    for role in ("SE", "PG"):
        if not math.isclose(allocated[role], required[role], abs_tol=1e-9, rel_tol=0):
            raise EstimateValidationError(f"{role}の配賦工数 {allocated[role]:.1f}h がWBS合計 {required[role]:.1f}h と一致しません。")
        for phase, rank in (("プロジェクト管理", "PJ管理費"), ("予備工数", "予備工数")):
            expected = sum(item["hours"] for item in wbs if item["role"] == role and item["phase"] == phase)
            actual = sum(item["hours"] for item in result if item["role"] == role and item["rank"] == rank)
            if not math.isclose(actual, expected, abs_tol=1e-9, rel_tol=0):
                raise EstimateValidationError(f"{role}の{phase}工数と{rank}への配賦が一致しません。")
    return result


def pricing_totals(data: dict[str, Any], allocated: list[dict[str, Any]]) -> dict[str, float]:
    pricing = data.get("pricing")
    if not isinstance(pricing, dict) or not all(nonnegative_number(pricing.get(field)) for field in ("gross_margin_rate", "outsourcing_cost", "other_expenses")) or pricing["gross_margin_rate"] >= 1:
        raise EstimateValidationError("pricing の粗利率、外注費、その他経費が不正です。粗利率は1未満にしてください。")
    if not isinstance(pricing.get("auto_overheads", False), bool):
        raise EstimateValidationError("pricing.auto_overheads は true / false を指定してください。")
    totals = {
        "se_cost": sum(item["amount"] for item in allocated if item["role"] == "SE" and item["rank"] not in {"PJ管理費", "予備工数"}),
        "pg_cost": sum(item["amount"] for item in allocated if item["role"] == "PG" and item["rank"] not in {"PJ管理費", "予備工数"}),
        "management_cost": sum(item["amount"] for item in allocated if item["rank"] == "PJ管理費"),
        "contingency_cost": sum(item["amount"] for item in allocated if item["rank"] == "予備工数"),
        "management_hours": sum(item["hours"] for item in allocated if item["rank"] == "PJ管理費"),
        "contingency_hours": sum(item["hours"] for item in allocated if item["rank"] == "予備工数"),
        "total_hours": sum(item["hours"] for item in allocated),
    }
    if pricing.get("auto_overheads", False):
        master = cost_master(data)
        base_cost = totals["se_cost"] + totals["pg_cost"] + pricing["outsourcing_cost"]
        if not any(item["rank"] == "PJ管理費" for item in allocated):
            rate = 0.15 if base_cost > 5000000 else 0.10 if base_cost > 1000000 else 0.05
            work_hours = totals["total_hours"] - totals["management_hours"] - totals["contingency_hours"]
            totals["management_hours"] = math.floor(work_hours * rate + 0.5)
            totals["management_cost"] = totals["management_hours"] * master["cost_rates_per_hour"]["PJ管理費"]
            totals["total_hours"] += totals["management_hours"]
        if data["project"]["contract_type"] == "準委任":
            if totals["contingency_hours"]:
                raise EstimateValidationError("Excelの準委任ルールでは予備工数は0です。配賦から予備工数を外してください。")
        elif not any(item["rank"] == "予備工数" for item in allocated):
            base_cost = totals["se_cost"] + totals["pg_cost"] + totals["management_cost"]
            rate = 0.15 if base_cost > 5000000 else 0.10 if base_cost > 1000000 else 0.05 if base_cost > 499999 else 0
            totals["contingency_hours"] = math.floor(totals["total_hours"] * rate + 0.5)
            totals["contingency_cost"] = totals["contingency_hours"] * master["cost_rates_per_hour"]["予備工数"]
            totals["total_hours"] += totals["contingency_hours"]
    if data["project"]["contract_type"] == "準委任" and totals["contingency_hours"]:
        raise EstimateValidationError("Excelの準委任ルールでは予備工数は0です。")
    totals["internal_cost"] = totals["se_cost"] + totals["pg_cost"] + totals["management_cost"] + totals["contingency_cost"]
    totals["total_cost"] = totals["internal_cost"] + pricing["outsourcing_cost"] + pricing["other_expenses"]
    totals["estimate"] = round_thousand((totals["internal_cost"] + pricing["outsourcing_cost"]) / (1 - pricing["gross_margin_rate"]) + pricing["other_expenses"])
    totals["gross_profit"] = totals["estimate"] - totals["total_cost"]
    if all(item["rate_source"] == "第3システム部原価マスタ" for item in allocated):
        totals["indirect_cost"] = totals["total_hours"] * cost_master(data)["indirect_cost_per_hour"]
        totals["direct_cost"] = totals["total_cost"] - totals["indirect_cost"]
    return totals


def frontmatter() -> str:
    return "---\nstatus: draft\n---\n\n"


def hours(value: float) -> str:
    return f"{value:.1f}h"


def yen(value: float) -> str:
    return f"{value:,.0f}円"


def table_cell(value: Any) -> str:
    return str(value).replace("|", "&#124;").replace("\n", "<br>")


def render_work(wbs: list[dict[str, Any]]) -> str:
    totals = wbs_totals(wbs)
    rows = []
    for item in wbs:
        if item["source"] == "体制算出":
            calculation = f"{item['people']}人 × {item['utilization']:.0%} × {item['months']}月 × {item['hours_per_month']}h/月"
        elif "quantity" in item:
            calculation = f"{item['quantity']} × {item['unit_hours']}h × {item.get('people', 1)}人"
            if item.get("rounding") == "none":
                calculation += "（丸めなし）"
        else:
            calculation = item["source"]
        rows.append(f"| {table_cell(item['phase'])} | {table_cell(item['task_name'])} | {item['role']} | {calculation} | {hours(item['hours'])} | {table_cell(item['basis'])} |")
    return "## 算出内訳\n\n| 工程 | 作業 | 区分 | 算出式 | 工数 | 根拠 |\n| --- | --- | --- | --- | ---: | --- |\n" + "\n".join(rows) + f"\n\nSE合計: {hours(totals['SE'])} / PG合計: {hours(totals['PG'])} / 作業合計: {hours(totals['total'])}\n"


def render_pricing(data: dict[str, Any], allocated: list[dict[str, Any]]) -> str:
    totals = pricing_totals(data, allocated)
    pricing = data["pricing"]
    rows = [("SE原価（管理・予備を除く）", totals["se_cost"]), ("PG原価（管理・予備を除く）", totals["pg_cost"]), ("PJ管理原価", totals["management_cost"]), ("予備工数原価", totals["contingency_cost"]), ("社内原価合計", totals["internal_cost"]), ("外注費", pricing["outsourcing_cost"]), ("その他経費", pricing["other_expenses"]), ("見積総原価", totals["total_cost"])]
    if "indirect_cost" in totals:
        rows.extend([("製造間接原価（社内原価の内数）", totals["indirect_cost"]), ("PJ直接原価（参考）", totals["direct_cost"])])
    rows.append(("粗利額", totals["gross_profit"]))
    document = "## 社内用原価・金額\n\n| 項目 | 金額 |\n| --- | ---: |\n" + "\n".join(f"| {label} | {yen(value)} |" for label, value in rows)
    actual_margin = totals["gross_profit"] / totals["estimate"] if totals["estimate"] else 0
    document += f"\n\n設定粗利率: {pricing['gross_margin_rate']:.1%} / 実効粗利率: {actual_margin:.1%}\n"
    document += f"\nPJ管理: {hours(totals['management_hours'])} / 予備: {hours(totals['contingency_hours'])} / 原価対象社内工数: {hours(totals['total_hours'])}\n"
    document += "\nExcel計算式: `ROUND((社内原価 + 外注費) / (1 - 粗利率) + その他経費, -3)`。その他経費に粗利率を適用しません。\n"
    if pricing.get("auto_overheads", False):
        document += "\n管理・予備の未入力分はExcelルールで自動補完し、原価対象社内工数に含めています。\n"
    if "indirect_cost" not in totals:
        document += "\n案件指定単価を含むため、製造間接原価・PJ直接原価は未算出です。\n"
    document += f"\n## 顧客向け転記用\n\n| 作業名 | 見積金額（税別） |\n| --- | ---: |\n| {table_cell(data['project']['project_name'])} | {yen(totals['estimate'])} |\n"
    for label, field in (("対象範囲", "scope"), ("対象外", "exclusions"), ("顧客側の作業", "customer_tasks"), ("変更・超過時の扱い", "change_policy"), ("契約・精算条件", "billing_terms")):
        document += f"\n{label}: {table_cell(data['project'].get(field, '未確認'))}\n"
    return document


def render(phase: str, data: dict[str, Any]) -> str:
    project = validate_project(data)
    if phase == "conditions":
        rows = [("見積日", project.get("estimate_date", "未確認")), ("顧客名", project["customer_name"]), ("作業名", project["project_name"]), ("契約形態", project["contract_type"]), ("見積区分", project["estimate_type"]), ("作業フェーズ", project.get("work_phase", "未確認")), ("対象期間", project.get("period", "未確認")), ("算出方式", data.get("estimate_method", "functions")), ("見積部署", project.get("estimate_department", "未確認")), ("原価年度", project.get("cost_year", "未確認"))]
        return frontmatter() + "# 見積条件\n\n| 項目 | 値 |\n| --- | --- |\n" + "\n".join(f"| {name} | {table_cell(value)} |" for name, value in rows) + "\n\n## 前提・未確認事項\n\n" + "\n".join(f"- {item}" for item in project.get("assumptions", ["なし"])) + "\n"
    if phase == "functions":
        functions = calculated_functions(data)
        return frontmatter() + "# 機能一覧\n\n| 機能名 | 種別 | 難易度 | 内部設計 | PG開発 | プログラムテスト | 根拠 |\n| --- | --- | ---: | ---: | ---: | ---: | --- |\n" + "\n".join(f"| {table_cell(item['function_name'])} | {item['function_type']} | {item['difficulty']} | {hours(item['internal_design_hours'])} | {hours(item['pg_development_hours'])} | {hours(item['program_test_hours'])} | {table_cell(item['basis'])} |" for item in functions) + "\n"
    wbs = build_wbs(data)
    if phase == "wbs":
        return frontmatter() + "# WBS\n\n" + render_work(wbs)
    if phase == "summary":
        conditions = render("conditions", data).removeprefix(frontmatter()).replace("# 見積条件", "# 見積", 1)
        document = frontmatter() + conditions + "\n" + render_work(wbs)
        if data.get("estimate_method", "functions") in {"functions", "hybrid"}:
            document += "\n" + render("functions", data).removeprefix(frontmatter()).replace("# 機能一覧", "## 機能一覧", 1)
        if data.get("allocation"):
            allocated = allocation(data, wbs)
            document += "\n" + render("allocation", data).removeprefix(frontmatter()).replace("# ランク配賦", "## 原価内訳（社内用）", 1)
            if data.get("pricing"):
                document += "\n" + render_pricing(data, allocated)
            else:
                document += "\n見積金額は未算出です。粗利率・外注費・その他経費を確認してください。\n"
        else:
            document += "\n原価・見積金額は未算出です。ランク別工数と原価年度または原価単価を確認してください。\n"
        return document
    allocated = allocation(data, wbs)
    if phase == "allocation":
        return frontmatter() + "# ランク配賦\n\n| ランク | 区分 | 配賦工数 | 原価時間単価 | 原価 | 単価の出典 | 根拠 |\n| --- | --- | ---: | ---: | ---: | --- | --- |\n" + "\n".join(f"| {table_cell(item['rank'])} | {item['role']} | {hours(item['hours'])} | {yen(item['hourly_rate'])} | {yen(item['amount'])} | {item['rate_source']} | {table_cell(item['basis'])} |" for item in allocated) + "\n"
    return frontmatter() + "# 見積金額\n\n" + render_pricing(data, allocated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", nargs="?", default="summary", choices=PHASES, help="既定は1つの見積MD。必要な段階だけの出力も可能")
    parser.add_argument("--data", required=True, type=Path, help="見積データJSON")
    parser.add_argument("--output-dir", required=True, type=Path, help="成果物フォルダ")
    parser.add_argument("--cost-master", type=Path, help="第3システム部の原価マスタ。未指定時は同梱2025年度版")
    parser.add_argument("--require-approval", action="store_true", help="段階出力で前段の承認を要求する")
    args = parser.parse_args()
    try:
        filename, predecessor = PHASES[args.phase]
        data = load_data(args.data)
        if args.cost_master:
            data["_cost_master_path"] = str(args.cost_master)
        if args.phase == "wbs" and data.get("estimate_method", "functions") in {"activities", "staffing"}:
            predecessor = PHASES["conditions"][0]
        if args.require_approval and args.phase == "summary" and data.get("approval_status") != "approved":
            raise EstimateValidationError("承認付きの一括出力には approval_status: approved が必要です。")
        if args.require_approval and predecessor:
            require_approved(args.output_dir / predecessor)
        if args.require_approval and args.phase == "wbs" and data.get("estimate_method", "functions") in {"functions", "hybrid"}:
            verify_functions_document(args.output_dir / FUNCTION_DOCUMENT, data)
        document = render(args.phase, data)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output = args.output_dir / filename
        if output.is_file() and re.search(r"(?m)^status:\s*approved\s*$", output.read_text(encoding="utf-8")):
            raise EstimateValidationError("承認済み成果物は上書きしません。別の出力先を指定してください。")
        output.write_text(document, encoding="utf-8")
    except EstimateValidationError as error:
        print(f"停止: {error}", file=sys.stderr)
        return 2
    print(f"出力完了: {args.output_dir / filename}")
    print("下書きとして出力しました。顧客提示前に対象範囲・単価・金額・契約条件を確認してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())