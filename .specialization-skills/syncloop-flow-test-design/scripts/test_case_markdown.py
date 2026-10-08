#!/usr/bin/env python3
"""根拠付きテスト設計データを検証し、決定的にMarkdownへ出力する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


MAX_CASES = 50
CONFIDENCES = {"確定", "要確認"}
SCOPES = {"対象", "対象外", "要確認"}
CATEGORIES = {"正常", "必須入力", "境界値", "選択肢", "状態遷移", "データ有無", "変更", "削除", "取消", "対象切替"}
OMISSION_PATTERN = re.compile(r"同上|同様|前ケース")
ABSTRACT_EXPECTATIONS = {"正常に表示される", "正しく表示される", "期待どおり", "成功する"}


class TestDesignValidationError(ValueError):
    """テスト設計データがPoCの出力条件を満たさない。"""


def load_data(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise TestDesignValidationError(f"テスト設計データがありません: {path}") from error
    except json.JSONDecodeError as error:
        raise TestDesignValidationError(f"JSON形式が不正です: {error.msg}") from error
    if not isinstance(data, dict):
        raise TestDesignValidationError("テスト設計データはオブジェクトである必要があります。")
    return data


def required_text(item: dict[str, Any], field: str, context: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TestDesignValidationError(f"{context}.{field} が必要です。")
    return value.strip()


def evidence_list(value: Any, context: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise TestDesignValidationError(f"{context}.evidence は1件以上必要です。")
    result = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise TestDesignValidationError(f"{context}.evidence[{index}] はオブジェクトである必要があります。")
        source = required_text(item, "source", f"{context}.evidence[{index}]")
        detail = required_text(item, "detail", f"{context}.evidence[{index}]")
        kind = required_text(item, "kind", f"{context}.evidence[{index}]")
        result.append({"source": source, "detail": detail, "kind": kind})
    return result


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def validate(data: dict[str, Any]) -> None:
    if data.get("approval_status") != "approved":
        raise TestDesignValidationError("approval_status が approved のテスト設計データだけを出力できます。")
    target = data.get("target")
    if not isinstance(target, dict):
        raise TestDesignValidationError("target はオブジェクトである必要があります。")
    for field in ("name", "version", "test_level"):
        required_text(target, field, "target")
    if target["test_level"] != "画面ブラックボックステスト":
        raise TestDesignValidationError("target.test_level は画面ブラックボックステストである必要があります。")

    requirements = data.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise TestDesignValidationError("requirements は1件以上必要です。")
    requirement_scopes: dict[str, str] = {}
    for index, item in enumerate(requirements, 1):
        context = f"requirements[{index}]"
        if not isinstance(item, dict):
            raise TestDesignValidationError(f"{context} はオブジェクトである必要があります。")
        identifier = required_text(item, "id", context)
        if identifier in requirement_scopes:
            raise TestDesignValidationError(f"要件IDが重複しています: {identifier}")
        required_text(item, "description", context)
        scope = required_text(item, "scope", context)
        if scope not in SCOPES:
            raise TestDesignValidationError(f"{context}.scope が不正です: {scope}")
        evidence_list(item.get("evidence"), context)
        requirement_scopes[identifier] = scope

    viewpoints = data.get("viewpoints")
    if not isinstance(viewpoints, list):
        raise TestDesignValidationError("viewpoints は配列である必要があります。")
    for index, item in enumerate(viewpoints, 1):
        context = f"viewpoints[{index}]"
        if not isinstance(item, dict):
            raise TestDesignValidationError(f"{context} はオブジェクトである必要があります。")
        required_text(item, "requirement_id", context)
        name = required_text(item, "name", context)
        if item["requirement_id"] not in requirement_scopes or name not in CATEGORIES:
            raise TestDesignValidationError(f"{context} の要件IDまたは観点名が不正です。")
        required_text(item, "decision", context)
        required_text(item, "reason", context)

    cases = data.get("test_cases")
    if not isinstance(cases, list) or len(cases) > MAX_CASES:
        raise TestDesignValidationError(f"test_cases は{MAX_CASES}件以下の配列である必要があります。")
    case_ids: set[str] = set()
    covered: set[str] = set()
    fingerprints: set[tuple[str, str, str, str]] = set()
    for index, item in enumerate(cases, 1):
        context = f"test_cases[{index}]"
        if not isinstance(item, dict):
            raise TestDesignValidationError(f"{context} はオブジェクトである必要があります。")
        case_id = required_text(item, "id", context)
        if case_id in case_ids:
            raise TestDesignValidationError(f"テストケースIDが重複しています: {case_id}")
        case_ids.add(case_id)
        requirement_ids = item.get("requirement_ids")
        if not isinstance(requirement_ids, list) or not requirement_ids or not all(isinstance(value, str) and value for value in requirement_ids):
            raise TestDesignValidationError(f"{context}.requirement_ids は1件以上必要です。")
        for requirement_id in requirement_ids:
            if requirement_id not in requirement_scopes:
                raise TestDesignValidationError(f"{context} の対応要件が存在しません: {requirement_id}")
            if requirement_scopes[requirement_id] == "対象外":
                raise TestDesignValidationError(f"対象外要件をテストケースに含められません: {requirement_id}")
            covered.add(requirement_id)
        for field in ("screen_feature", "purpose", "preconditions", "input_values", "expected_result"):
            required_text(item, field, context)
        category = required_text(item, "category", context)
        if category not in CATEGORIES:
            raise TestDesignValidationError(f"{context}.category が不正です: {category}")
        confidence = required_text(item, "confidence", context)
        if confidence not in CONFIDENCES:
            raise TestDesignValidationError(f"{context}.confidence が不正です: {confidence}")
        steps = item.get("steps")
        if not isinstance(steps, list) or not steps or not all(isinstance(step, str) and step.strip() for step in steps):
            raise TestDesignValidationError(f"{context}.steps は具体的な操作を1件以上含める必要があります。")
        joined_steps = " ".join(steps)
        if OMISSION_PATTERN.search(joined_steps):
            raise TestDesignValidationError(f"{context}.steps に省略表現を使用できません。")
        if "画面" not in joined_steps:
            raise TestDesignValidationError(f"{context}.steps には画面名を含めてください。")
        if item["expected_result"].strip() in ABSTRACT_EXPECTATIONS:
            raise TestDesignValidationError(f"{context}.expected_result が抽象的すぎます。")
        evidence = evidence_list(item.get("evidence"), context)
        if confidence == "確定" and not any(entry["kind"] != "実装" for entry in evidence):
            raise TestDesignValidationError(f"{context} の確定ケースには実装以外の上位根拠が必要です。")
        fingerprint = tuple(normalized(value) for value in (item["preconditions"], joined_steps, item["input_values"], item["expected_result"]))
        if fingerprint in fingerprints:
            raise TestDesignValidationError(f"重複するテストケースがあります: {case_id}")
        fingerprints.add(fingerprint)

    unresolved = data.get("unresolved_items")
    if not isinstance(unresolved, list):
        raise TestDesignValidationError("unresolved_items は配列である必要があります。")
    unresolved_ids: set[str] = set()
    for index, item in enumerate(unresolved, 1):
        context = f"unresolved_items[{index}]"
        if not isinstance(item, dict):
            raise TestDesignValidationError(f"{context} はオブジェクトである必要があります。")
        requirement_id = required_text(item, "requirement_id", context)
        if requirement_id not in requirement_scopes:
            raise TestDesignValidationError(f"{context} の対応要件が存在しません: {requirement_id}")
        required_text(item, "item", context)
        required_text(item, "reason", context)
        unresolved_ids.add(requirement_id)
    unclassified = [identifier for identifier, scope in requirement_scopes.items() if scope == "対象" and identifier not in covered and identifier not in unresolved_ids]
    if unclassified:
        raise TestDesignValidationError(f"対象要件がカバレッジ未分類です: {', '.join(unclassified)}")


def evidence_text(entries: list[dict[str, str]]) -> str:
    return "<br>".join(f"{entry['source']}（{entry['detail']} / {entry['kind']}）" for entry in entries)


def cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def coverage(data: dict[str, Any]) -> list[dict[str, str]]:
    cases_by_requirement: defaultdict[str, list[str]] = defaultdict(list)
    for case in data["test_cases"]:
        for requirement_id in case["requirement_ids"]:
            cases_by_requirement[requirement_id].append(case["id"])
    unresolved = {item["requirement_id"]: item for item in data["unresolved_items"]}
    rows = []
    for requirement in data["requirements"]:
        identifier = requirement["id"]
        if requirement["scope"] == "対象外":
            status, notes = "対象外", "対象外として承認済み"
        elif identifier in cases_by_requirement:
            status, notes = "ケースあり", ""
        else:
            status, notes = "要確認", unresolved[identifier]["reason"]
        rows.append({"id": identifier, "description": requirement["description"], "cases": ", ".join(cases_by_requirement[identifier]) or "-", "status": status, "notes": notes})
    return rows


def render_viewpoints(data: dict[str, Any]) -> str:
    target = data["target"]
    requirement_names = {item["id"]: item["description"] for item in data["requirements"]}
    header = f"---\nstatus: draft\ntarget: {target['name']}\ntarget_version: {target['version']}\n---\n\n# テスト観点一覧\n\n| 要件・機能ID | 内容 | 観点 | 判定 | 根拠・理由 |\n| --- | --- | --- | --- | --- |\n"
    viewpoint_rows = [f"| {cell(item['requirement_id'])} | {cell(requirement_names[item['requirement_id']])} | {cell(item['name'])} | {cell(item['decision'])} | {cell(item['reason'])} |" for item in data["viewpoints"]]
    unresolved = data["unresolved_items"]
    if unresolved:
        unresolved_rows = [f"| {cell(item['requirement_id'])} | {cell(item['item'])} | {cell(item['reason'])} |" for item in unresolved]
        return header + "\n".join(viewpoint_rows) + "\n\n## 要確認事項\n\n| 要件・機能ID | 内容 | 理由 |\n| --- | --- | --- |\n" + "\n".join(unresolved_rows) + "\n"
    return header + "\n".join(viewpoint_rows) + "\n"


def render_cases(data: dict[str, Any]) -> str:
    target = data["target"]
    header = f"---\nstatus: draft\ntarget: {target['name']}\ntarget_version: {target['version']}\ncase_count: {len(data['test_cases'])}\n---\n\n# テストケース\n\n| ID | 対応要件 | 画面・機能 | 分類 | テスト目的 | 前提条件 | 操作手順 | 入力値 | 期待結果 | 根拠 | 確度 |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    rows = []
    for item in data["test_cases"]:
        steps = "<br>".join(f"{index}. {step}" for index, step in enumerate(item["steps"], 1))
        rows.append(f"| {cell(item['id'])} | {cell(', '.join(item['requirement_ids']))} | {cell(item['screen_feature'])} | {cell(item['category'])} | {cell(item['purpose'])} | {cell(item['preconditions'])} | {cell(steps)} | {cell(item['input_values'])} | {cell(item['expected_result'])} | {cell(evidence_text(item['evidence']))} | {cell(item['confidence'])} |")
    coverage_rows = coverage(data)
    footer = "\n## 要件カバレッジ\n\n| 要件・機能ID | 内容 | 対応ケース | 状態 | 備考 |\n| --- | --- | --- | --- | --- |\n" + "\n".join(f"| {cell(row['id'])} | {cell(row['description'])} | {cell(row['cases'])} | {cell(row['status'])} | {cell(row['notes'])} |" for row in coverage_rows) + "\n"
    return header + "\n".join(rows) + footer


def summary(data: dict[str, Any]) -> str:
    counts = Counter(item["category"] for item in data["test_cases"])
    by_category = "、".join(f"{name}: {count}" for name, count in sorted(counts.items())) or "なし"
    rows = coverage(data)
    return f"対象: {data['target']['name']} ({data['target']['version']})\nケース数: {len(data['test_cases'])}\n分類別: {by_category}\n要確認: {len(data['unresolved_items'])}\nカバレッジ: ケースあり {sum(row['status'] == 'ケースあり' for row in rows)} / 要確認 {sum(row['status'] == '要確認' for row in rows)} / 対象外 {sum(row['status'] == '対象外' for row in rows)}"


def write_outputs(data: dict[str, Any], output_dir: Path) -> None:
    if not output_dir.is_dir():
        raise TestDesignValidationError(f"出力先Workフォルダがありません: {output_dir}")
    paths = (output_dir / "テスト観点一覧.md", output_dir / "テストケース.md")
    existing = [path.name for path in paths if path.exists()]
    if existing:
        raise TestDesignValidationError(f"既存成果物を上書きできません: {', '.join(existing)}")
    paths[0].write_text(render_viewpoints(data), encoding="utf-8")
    paths[1].write_text(render_cases(data), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "preview", "render"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--data", type=Path, required=True)
        if command == "render":
            subparser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = load_data(args.data)
        validate(data)
        if args.command == "render":
            write_outputs(data, args.output_dir)
        print(summary(data))
        return 0
    except TestDesignValidationError as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
