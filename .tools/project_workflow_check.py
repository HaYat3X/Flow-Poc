#!/usr/bin/env python3
"""Syncloop Flow schema v3の構造、ID、一覧、Work入力・記録を読み取り専用で検査する。"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import unquote


sys.path.insert(0, str(Path(__file__).resolve().parent))
import work_close_gate as close_gate

nfc = close_gate.nfc
read_text = close_gate.read_text

SCHEMA_VERSION = "3"
REQUIRED_DIRECTORIES = (
    ".agents/policies",
    ".agents/skills",
    ".tools",
    "02_CT_管理/依頼",
    "02_CT_管理/進行計画",
    "01_IN_入力/入力",
    "03_CX_コンテキスト",
    "04_WK_作業",
    "04_WK_作業/完了",
    "06_PD_プロダクト/リリース",
    "07_KN_ナレッジ",
    "99_AX_アーカイブ/依頼",
)
REQUIRED_FILES = {
    "02_CT_管理/現在地.md": "current_status",
    "02_CT_管理/依頼一覧.md": "request_index",
    "02_CT_管理/Work一覧.md": "work_index",
    "02_CT_管理/更新履歴.md": "update_history",
    "01_IN_入力/依頼受付.md": "request_intake",
    "01_IN_入力/入力資料一覧.md": "input_material_index",
    "03_CX_コンテキスト/Context一覧.md": "context_index",
    "03_CX_コンテキスト/トレーサビリティ.md": "traceability",
    "06_PD_プロダクト/リポジトリ情報.md": "repository_index",
    "07_KN_ナレッジ/ナレッジ一覧.md": "knowledge_index",
}
REQUIRED_PLAIN_FILES = (
    "AGENTS.md",
    ".agents/policies/project-record-updates.md",
    ".agents/policies/cx-context.md",
    ".agents/policies/workspace-structure.md",
    ".agents/policies/work-close-contract.md",
    ".tools/work_close_gate.py",
    ".agents/skills/syncloop-flow-request-start/SKILL.md",
    ".agents/skills/syncloop-flow-status/SKILL.md",
    ".agents/skills/syncloop-flow-request-plan/SKILL.md",
    ".agents/skills/syncloop-flow-work-start/SKILL.md",
    ".agents/skills/syncloop-flow-sync/SKILL.md",
    ".agents/skills/syncloop-flow-work-close/SKILL.md",
    ".agents/skills/syncloop-flow-request-close/SKILL.md",
    ".tools/project_workflow_check.py",
)
LEGACY_TOP_LEVEL = (
    "00_受付・見積",
    "01_プロジェクト計画",
    "02_要件定義",
    "03_設計",
    "04_実装",
    "05_テスト",
    "06_導入・移行",
    "07_運用支援",
    "_受領資料",
    "_既存資料",
    "_work",
    "_source",
    "_ナレッジ",
)
ID_PATTERNS = {
    "request": re.compile(r"RQ-\d{4}"),
    "material": re.compile(r"MAT-\d{4}"),
    "work": re.compile(r"W-\d{4}"),
    "knowledge": re.compile(r"K-(?:TERM|BIZ|SYS|OPS|PAT|TRB)-\d{4}"),
    "decision": re.compile(r"DEC-\d{4}"),
    "risk": re.compile(r"RSK-\d{4}"),
    "issue": re.compile(r"ISS-\d{4}"),
    "context": re.compile(r"CTX-\d{4}"),
}
PLACEHOLDER_VALUES = {"", "TBD", "RQ-TBD", "W-TBD", "CTX-TBD"}
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:]+(?:Z|[+-][0-9:]+)?)?")
REQUEST_STATUSES = {"registered", "active", "on_hold", "completed", "cancelled", "archived"}
PLANNING_STATUSES = {"unplanned", "approved", "needs_revision"}
PLAN_HEADINGS = (
    "## 進め方の要約",
    "## 依頼全体の到達点・終了条件",
    "## 今回計画する範囲",
    "## 未計画の範囲",
    "## 優先して解消する不確実性",
    "## Work候補",
    "## 実施順序・並行関係",
    "## 判断ゲート",
    "## Context同期ポイント",
    "## 最初に開始するWork候補",
    "## 改訂履歴",
)
SPLIT_PLAN_HEADINGS = (
    "## 今回の区切り",
    "## 今回始めるWork",
    "## この区切りで気にすること",
    "## 区切りに着いたらやること",
    "## 改訂履歴",
)
WBS_HEADINGS = (
    "## 到達点",
    "## 作業パッケージ",
    "## マイルストーン・判断ゲート",
    "## ガントチャート",
    "## 改訂履歴",
)
UNASSIGNED_TASK_REF = "未割当（Plan）"
INTAKE_STATUSES = {"empty", "draft", "ready", "registered"}
WORK_STATUSES = {"active", "on_hold", "handoff", "completed", "cancelled"}
KNOWLEDGE_STATUSES = {"active", "needs_review", "retired"}
KNOWLEDGE_TYPES = {
    "TERM": "term",
    "BIZ": "business",
    "SYS": "system",
    "OPS": "operation",
    "PAT": "pattern",
    "TRB": "troubleshooting",
}
TODO_STATES = {"未着手", "作業中", "保留", "完了", "中止"}
WORK_INPUT_TYPES = {"management", "context", "received", "existing", "knowledge", "product", "work_output"}
WORK_INPUT_METHODS = {"copy", "snapshot", "reference"}
WORK_INPUT_STATES = {"confirmed", "candidate", "unknown", "conflict"}
CONTEXT_CANDIDATE_TYPES = {
    "objective", "success_condition", "stakeholder", "authority", "scope", "out_of_scope",
    "requirement", "expectation", "business_rule", "assumption", "constraint", "unknown",
    "conflict", "solution_policy", "architecture", "non_functional", "data",
    "external_dependency", "operation", "commercial_boundary", "quality_policy", "acceptance", "decision", "risk", "issue",
}
CONTEXT_CANDIDATE_SECTIONS = {
    "objective": ("02",), "success_condition": ("03",), "scope": ("03",), "out_of_scope": ("03",),
    "quality_policy": ("03",), "acceptance": ("03",), "commercial_boundary": ("03",),
    "constraint": ("03", "16"), "business_rule": ("04", "16"),
    "requirement": ("05",), "expectation": ("05",), "solution_policy": ("05",),
    "architecture": ("05",), "non_functional": ("05",), "external_dependency": ("06", "16"),
    "data": ("07",), "operation": ("09", "08", "11", "16"),
    "stakeholder": ("10",), "authority": ("10",), "risk": ("13",), "issue": ("13",),
    "assumption": ("14",), "unknown": ("14",), "conflict": ("14",), "decision": ("15",),
}
CONTEXT_CHANGE_TYPES = {"追加", "変更", "廃止"}
CONTEXT_ITEM_PATTERN = re.compile(r"^#{3,4}\s+(?:(CTX-\d{4}):\s+.+|.+\((CTX-\d{4})\))$", re.MULTILINE)
CONTEXT_SECTION_TITLES = (
    "基本情報", "案件の背景", "ゴール・成功条件", "対象業務", "システム概要",
    "外部システム・連携", "データ概要", "環境", "開発・運用ルール", "プロジェクト体制",
    "コミュニケーション", "現在の進捗", "課題・リスク", "未決事項", "重要な経緯・意思決定",
    "注意事項・ハマりポイント", "次にやること", "関連資料", "引き継ぎ時に最初に読むもの",
    "3分で把握する案件サマリ",
)
CONTEXT_SINGLE_HEADINGS = tuple(f"## {number}. {title}"
                                for number, title in enumerate(CONTEXT_SECTION_TITLES, 1))
CONTEXT_SPLIT_FILES = {
    f"{number:02d}_{title}.md": f"## {number}. {title}"
    for number, title in enumerate(CONTEXT_SECTION_TITLES, 1)
    if number not in {1, 12, 17, 20}
}
CONTEXT_SECTION_LIMIT = 6000
CONTEXT_MAIN_LIMIT = 25000
WORK_INPUT_ID_PATTERN = re.compile(r"WI-\d{3}")
WORK_INPUT_HEADINGS = (
    "## 入力セット",
    "## 確認した索引と参照しなかった領域",
)
WORK_LOG_HEADINGS = (
    "## 作業開始時の整理",
    "### Context観測対象",
    "## TODO一覧",
    "## TODOごとの作業記録",
)
WORK_CANDIDATE_HEADINGS = (
    "## Context候補",
    "## 意思決定候補",
    "## リスク・課題候補",
    "## Knowledge候補",
    "## Product反映候補",
    "## 反映候補の処理履歴",
)
WORK_LOG_ENTRY_HEADINGS = (
    "##### TODOの作業内容",
    "##### 実施内容",
    "##### 観測事実",
    "##### 解釈・暫定判断",
    "##### 根拠",
    "##### 未解決事項・次の対応",
    "##### 反映候補の確認",
)
CANDIDATE_ID_PATTERN = re.compile(r"C-(?:CTX|DEC|RSK|ISS|KNW|PRD)-\d{3}")
STATUS_HEADINGS = (
    "## サマリ",
    "## 依頼ごとの現在地",
    "## 判断待ち",
    "## 阻害要因",
    "## 未同期候補・不整合",
    "## 次アクション",
)
INTAKE_HEADINGS = (
    "## 依頼名",
    "## 依頼元・窓口",
    "## 背景・解決したい課題",
    "## 希望する結果・終了条件",
    "## 対象範囲",
    "## 対象外",
    "## 希望する成果物",
    "## 希望時期・期限",
    "## 予算・契約状況",
    "## 関係者・判断者",
    "## 分かっている前提・制約",
    "## 未確認事項",
    "## 関連する依頼・契約・Context",
    "## 関連資料",
)


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


def context_paths(root: Path) -> list[Path]:
    return [p for p in (root / "03_CX_コンテキスト").glob("*.md")
            if read_frontmatter(p).get("document_type") == "project_context"
            or unicodedata.normalize("NFC", p.name) in set(CONTEXT_SPLIT_FILES) | {"プロジェクトコンテキスト.md"}]


def project_identity_path(root: Path) -> Path:
    return root / "03_CX_コンテキスト/プロジェクトコンテキスト.md"


def project_identity(root: Path) -> dict[str, str]:
    path = project_identity_path(root)
    return read_frontmatter(path) if path.is_file() else {}


def read_frontmatter(path: Path) -> dict[str, str]:
    lines = read_text(path).splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return metadata
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*):(?:\s*(.*))?$", line)
        if match:
            metadata[match.group(1)] = (match.group(2) or "").strip().strip('"\'')
    return {}


def add(findings: list[Finding], level: str, message: str) -> None:
    findings.append(Finding(level, message))


def is_placeholder(value: str | None) -> bool:
    return value is None or value.strip() in PLACEHOLDER_VALUES


def section_text(text: str, heading: str) -> str:
    marker = f"{heading}\n"
    if marker not in text:
        return ""
    remainder = text.split(marker, 1)[1]
    return remainder.split("\n## ", 1)[0]


def context_structure(text: str) -> str:
    lines = []
    fence = ""
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        inside = bool(fence)
        if marker:
            if not fence:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = ""
        lines.append(re.sub(r"[^\r\n]", " ", line) if inside or fence else line)
    return "".join(lines)


def context_sections(text: str) -> dict[str, str]:
    headings = list(re.finditer(r"^## [^\r\n]+", context_structure(text), re.MULTILINE))
    return {match[0]: text[match.end():headings[position + 1].start() if position + 1 < len(headings) else len(text)]
            for position, match in enumerate(headings)}


def context_body_length(text: str) -> int:
    text = re.sub(r"\A---\r?\n.*?\r?\n---(?:\r?\n|\Z)", "", text, count=1, flags=re.S)
    structure_lines = context_structure(text).splitlines()
    return sum(len(line.strip()) for line, structure in zip(text.splitlines(), structure_lines)
               if line.strip() and not re.match(r"^#{1,6}\s", structure))


def context_items(text: str) -> list[tuple[str, str]]:
    structure = context_structure(text)
    items = []
    for match in CONTEXT_ITEM_PATTERN.finditer(structure):
        level = len(match[0].split(" ", 1)[0])
        end = re.search(rf"^#{{1,{level}}}\s", structure[match.end():], re.MULTILINE)
        stop = match.end() + end.start() if end else len(text)
        items.append((match[1] or match[2], text[match.start():stop]))
    return items


CANDIDATE_FIELDS = {
    "## Context候補": ("元TODO・作業メモ", "候補種別", "変更種別", "対象CTX", "適用範囲", "現在値", "変更案", "状態", "根拠", "反映先セクション"),
    "## 意思決定候補": ("元TODO・作業メモ", "決定事項", "決定者", "決定日", "根拠", "影響範囲", "適用条件"),
    "## リスク・課題候補": ("元TODO・作業メモ", "種別", "内容", "原因・発生条件", "影響", "可能性・緊急度", "対応案", "担当・期限候補", "根拠"),
    "## Knowledge候補": ("元TODO・作業メモ", "分類・タイトル", "再利用できる内容", "適用条件", "根拠", "例外・限界"),
    "## Product反映候補": ("元TODO・作業メモ", "種別", "内容・参照先", "用途・反映先", "現在の状態", "根拠"),
}


def record_attributes(text: str) -> dict[str, str]:
    """本文と区別された補足属性。旧属性表も読み取る。"""
    attrs = {r[0]: r[1] for r in close_gate.table_rows(text.split("\n現在値", 1)[0]) if len(r) == 2}
    structure = context_structure(text)
    for match in re.finditer(r"^- ([^:\n]+):[ \t]*(.*)$", structure, re.MULTILINE):
        attrs[match[1]] = match[2].strip().strip("`")
    return attrs


def candidate_rows(text: str, heading: str) -> list[list[str]]:
    """文章形式の候補を既存の検査項目へ対応させる。旧候補表も保持する。"""
    structure = context_structure(text)
    rows = [row for row in close_gate.table_rows(structure) if row and CANDIDATE_ID_PATTERN.fullmatch(row[0])]
    matches = list(re.finditer(r"^### .+\((C-(?:CTX|DEC|RSK|ISS|KNW|PRD)-\d{3})\)$", structure, re.MULTILINE))
    for match in matches:
        end = re.search(r"^#{1,3}\s", structure[match.end():], re.MULTILINE)
        stop = match.end() + end.start() if end else len(text)
        block = text[match.end():stop]
        fields = record_attributes(block)
        # 長い変更案等は小見出しの下に複数段落で書ける。
        for name in CANDIDATE_FIELDS[heading]:
            part = re.search(rf"^#### {re.escape(name)}\n(.*?)(?=^#{{1,4}} |\Z)", context_structure(block), re.MULTILINE | re.DOTALL)
            if part:
                fields[name] = block[part.start(1):part.end(1)].strip()
        rows.append([match[1]] + [fields.get(name, "-" if name == "反映先セクション" else "") for name in CANDIDATE_FIELDS[heading]])
    return rows


def context_detail_links(text: str) -> set[str]:
    return {unquote(target).split("#", 1)[0]
            for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", context_structure(text))}


def intake_has_content(text: str) -> bool:
    start = "<!-- intake-form:start -->"
    end = "<!-- intake-form:end -->"
    if start not in text or end not in text:
        return False
    form = text.split(start, 1)[1].split(end, 1)[0]
    values = [
        line.strip()
        for line in form.splitlines()
        if line.strip() and not line.startswith("## ") and not line.startswith("<!--")
    ]
    return any(value not in {"未定", "未記入"} for value in values)


def check_structure(root: Path, findings: list[Finding]) -> None:
    for relative in REQUIRED_DIRECTORIES:
        if not (root / relative).is_dir():
            add(findings, "error", f"必須フォルダがありません: {relative}")
    for relative, expected_type in REQUIRED_FILES.items():
        path = root / relative
        if not path.is_file():
            add(findings, "error", f"必須ファイルがありません: {relative}")
            continue
        metadata = read_frontmatter(path)
        if not metadata:
            add(findings, "error", f"frontmatterがありません: {relative}")
            continue
        if metadata.get("workflow_schema") != SCHEMA_VERSION:
            add(findings, "error", f"workflow_schemaは{SCHEMA_VERSION}である必要があります: {relative}")
        if metadata.get("document_type") != expected_type:
            add(findings, "error", f"document_typeは{expected_type}である必要があります: {relative}")
    for relative in REQUIRED_PLAIN_FILES:
        if not (root / relative).is_file():
            add(findings, "error", f"必須ファイルがありません: {relative}")
    for legacy in LEGACY_TOP_LEVEL:
        if (root / legacy).exists():
            add(findings, "warning", f"旧構成のパスが残っています: {legacy}")


def check_document_contracts(root: Path, findings: list[Finding]) -> None:
    status_path = root / "02_CT_管理/現在地.md"
    status_text = read_text(status_path) if status_path.is_file() else ""
    for heading in STATUS_HEADINGS:
        if heading not in status_text:
            add(findings, "error", f"現在地に必須見出しがありません: {heading}")
    present_status_positions = [status_text.index(heading) for heading in STATUS_HEADINGS if heading in status_text]
    if present_status_positions != sorted(present_status_positions):
        add(findings, "error", "現在地の必須見出しの順序が不正です")

    intake_path = root / "01_IN_入力/依頼受付.md"
    if not intake_path.is_file():
        return
    intake_text = read_text(intake_path)
    for heading in INTAKE_HEADINGS:
        if heading not in intake_text:
            add(findings, "error", f"依頼受付に必須見出しがありません: {heading}")
    present_intake_positions = [intake_text.index(heading) for heading in INTAKE_HEADINGS if heading in intake_text]
    if present_intake_positions != sorted(present_intake_positions):
        add(findings, "error", "依頼受付の必須見出しの順序が不正です")
    intake_metadata = read_frontmatter(intake_path)
    intake_status = intake_metadata.get("record_status")
    if intake_status not in INTAKE_STATUSES:
        add(findings, "error", f"依頼受付のrecord_statusが不正です: {intake_status or '未設定'}")
    if intake_has_content(intake_text) and intake_status == "empty":
        add(findings, "error", "依頼受付に入力がありますがrecord_statusがemptyです")
    if not intake_has_content(intake_text) and intake_status == "registered":
        add(findings, "error", "依頼受付が空ですがrecord_statusがregisteredです")


def check_initialized_project(root: Path, findings: list[Finding]) -> None:
    request_paths = close_gate.request_documents(root / "02_CT_管理/依頼", "RQ-*.md")
    archived_request_paths = sorted((root / "99_AX_アーカイブ/依頼").glob("RQ-*"))
    if not request_paths and not archived_request_paths:
        return
    status_path = root / "02_CT_管理/現在地.md"
    status_text = read_text(status_path) if status_path.is_file() else ""

    project_ids: dict[str, str] = {}
    for relative in list(REQUIRED_FILES) + [p.relative_to(root).as_posix() for p in context_paths(root)]:
        path = root / relative
        if not path.is_file():
            continue
        metadata = read_frontmatter(path)
        project_id = metadata.get("project_id")
        if is_placeholder(project_id):
            add(findings, "error", f"初回依頼登録後にproject_idが未設定です: {relative}")
        else:
            project_ids[relative] = project_id or ""
        for field in ("updated_at", "updated_by"):
            if is_placeholder(metadata.get(field)):
                add(findings, "error", f"初回依頼登録後に{field}が未設定です: {relative}")
        updated_at = metadata.get("updated_at", "")
        if not is_placeholder(updated_at) and not DATE_PATTERN.fullmatch(updated_at):
            add(findings, "error", f"updated_atの形式が不正です: {relative}")

    distinct_ids = set(project_ids.values())
    if len(distinct_ids) > 1:
        details = ", ".join(f"{path}={value}" for path, value in project_ids.items())
        add(findings, "error", f"project_idが管理文書間で一致しません: {details}")

    overview = project_identity(root)
    if is_placeholder(overview.get("flow_project_id")):
        add(findings, "error", "初回依頼登録後に案件Contextのflow_project_idが未設定です")
    if is_placeholder(overview.get("project_name")):
        add(findings, "error", "初回依頼登録後に案件Contextのproject_nameが未設定です")
    initialized_from = overview.get("initialized_from_request")
    all_request_paths = request_paths + archived_request_paths
    request_ids = {
        match.group(0)
        for path in all_request_paths
        if (match := ID_PATTERNS["request"].search(path.name))
    }
    if is_placeholder(initialized_from):
        add(findings, "error", "案件Contextのinitialized_from_requestが未設定です")
    elif initialized_from not in request_ids:
        add(findings, "error", "案件Contextのinitialized_from_requestに対応する依頼がありません")

    for path in request_paths:
        relative = nfc(path.relative_to(root).as_posix())
        metadata = read_frontmatter(path)
        required = (
            "workflow_schema",
            "document_type",
            "project_id",
            "request_id",
            "request_name",
            "request_type",
            "request_status",
            "lifecycle_start",
            "created_at",
            "updated_at",
            "updated_by",
            "planning_status",
            "plan_file",
        )
        for field in required:
            if is_placeholder(metadata.get(field)):
                add(findings, "error", f"依頼frontmatterの{field}が未設定です: {relative}")
        if metadata.get("document_type") != "request":
            add(findings, "error", f"依頼のdocument_typeはrequestである必要があります: {relative}")
        if metadata.get("request_status") not in REQUEST_STATUSES:
            add(findings, "error", f"依頼のrequest_statusが不正です: {relative}")
        if metadata.get("planning_status") not in PLANNING_STATUSES:
            add(findings, "error", f"依頼のplanning_statusが不正です: {relative}")
        for field in ("created_at", "updated_at"):
            value = metadata.get(field, "")
            if not is_placeholder(value) and not DATE_PATTERN.fullmatch(value):
                add(findings, "error", f"依頼frontmatterの{field}の形式が不正です: {relative}")
        filename_id = ID_PATTERNS["request"].search(path.name)
        if filename_id and metadata.get("request_id") != filename_id.group(0):
            add(findings, "error", f"ファイル名とrequest_idが一致しません: {relative}")
        if distinct_ids and metadata.get("project_id") not in distinct_ids:
            add(findings, "error", f"依頼のproject_idが案件と一致しません: {relative}")

        request_id = metadata.get("request_id", "")
        index_path = root / "02_CT_管理/依頼一覧.md"
        index_lines = read_text(index_path).splitlines()
        matching_rows = [line for line in index_lines if re.match(rf"^\|\s*{re.escape(request_id)}\s*\|", line)]
        if len(matching_rows) == 1:
            cells = [cell.strip().strip("`") for cell in matching_rows[0].strip().strip("|").split("|")]
            expected = {
                1: ("request_name", metadata.get("request_name", "")),
                2: ("request_type", metadata.get("request_type", "")),
                3: ("request_status", metadata.get("request_status", "")),
                4: ("lifecycle_start", metadata.get("lifecycle_start", "")),
            }
            for position, (field, value) in expected.items():
                if len(cells) <= position or cells[position] != value:
                    add(findings, "error", f"依頼一覧と依頼frontmatterの{field}が一致しません: {request_id}")
            if len(cells) <= 8 or cells[8] != relative:
                add(findings, "error", f"依頼一覧の依頼ファイルが実体と一致しません: {request_id}")

        approval_paths = close_gate.approval_record_paths(root, request_id)
        check_approval_record(approval_paths["request"], "request", root, findings, request_id,
                              required_kinds={"登録承認"})
        planned = metadata.get("planning_status") in {"approved", "needs_revision"}
        plan_approvals = check_approval_record(approval_paths["plan"], "plan", root, findings, request_id,
                                               required_kinds={"Plan承認"} if planned else None)

        request_status_section = section_text(status_text, "## 依頼ごとの現在地")
        if request_id not in request_status_section:
            add(findings, "error", f"現在地の依頼別状態に依頼がありません: {request_id}")
        planning_status = metadata.get("planning_status", "")
        request_text = read_text(path)
        if metadata.get("request_format") == "execution_plan":
            for heading in ("## 背景・目的", "## 案件共通事項の参照", "## 期待する結果・終了条件",
                            "## 成果物・受入条件", "## 対象・対象外", "## 責任者・関係者",
                            "## 制約・前提・要求期限", "## 未確認事項・矛盾", "## 変更・報告のルール"):
                if heading not in request_text:
                    add(findings, "error", f"依頼の実施計画書に必須見出しがありません: {heading}: {request_id}")
        plan_section = section_text(request_text, "## 進行計画")
        if "## 進行計画" not in request_text:
            add(findings, "error", f"依頼に進行計画セクションがありません: {request_id}")
        body_planning_status = re.search(r"計画状態:\s*`?(unplanned|approved|needs_revision)`?", plan_section)
        if not body_planning_status or body_planning_status.group(1) != planning_status:
            add(findings, "error", f"依頼本文とfrontmatterのplanning_statusが一致しません: {request_id}")
        plan_file = metadata.get("plan_file", "")
        body_plan_file = re.search(r"計画ファイル:\s*`?([^`\n]+)`?", plan_section)
        if not body_plan_file or body_plan_file.group(1).strip() != plan_file:
            add(findings, "error", f"依頼本文とfrontmatterのplan_fileが一致しません: {request_id}")
        if planning_status == "unplanned":
            if plan_file != "none":
                add(findings, "error", f"未計画の依頼のplan_fileはnoneである必要があります: {request_id}")
        elif plan_file == "none" or is_placeholder(plan_file):
            add(findings, "error", f"計画済みの依頼にplan_fileがありません: {request_id}")
        else:
            expected_plan_file = f"02_CT_管理/進行計画/{request_id}_進行計画.md"
            if plan_file != expected_plan_file:
                add(findings, "error", f"plan_fileの配置またはファイル名が不正です: {request_id}")
            plan_path = root / plan_file
            if not plan_path.is_file():
                add(findings, "error", f"依頼の進行計画MDがありません: {plan_file}")
            else:
                check_request_plan(plan_path, request_id, planning_status, distinct_ids, root, findings)
                check_plan_revision_approvals(plan_path, plan_approvals, root, findings)
        if planning_status and planning_status not in request_status_section:
            add(findings, "error", f"現在地と依頼frontmatterのplanning_statusが一致しません: {request_id}")
        if planning_status != "approved" and "syncloop-flow-request-plan" not in section_text(status_text, "## 次アクション"):
            add(findings, "error", f"計画未承認の依頼にrequest-planが次アクションとして設定されていません: {request_id}")

    has_open_questions = any(
        re.search(r"^\|\s*(?:unknown|conflict)\s*\|", section_text(read_text(path), "## 未確認事項・矛盾"), re.MULTILINE)
        for path in request_paths
    )
    decision_section = section_text(status_text, "## 判断待ち")
    if has_open_questions and re.search(r"^\|\s*なし\s*\|\s*なし\s*\|", decision_section, re.MULTILINE):
        add(findings, "error", "依頼に未確認事項がありますが、現在地の判断待ちがなしです")


def check_request_plan(
    path: Path,
    request_id: str,
    planning_status: str,
    project_ids: set[str],
    root: Path,
    findings: list[Finding],
) -> None:
    relative = nfc(path.relative_to(root).as_posix())
    metadata = read_frontmatter(path)
    required = (
        "workflow_schema", "document_type", "project_id", "request_id",
        "planning_status", "plan_revision", "approved_at", "approved_by",
        "updated_at", "updated_by",
    ) + (() if metadata.get("plan_format") == "split" else ("plan_coverage",))
    for field in required:
        if is_placeholder(metadata.get(field)):
            add(findings, "error", f"進行計画frontmatterの{field}が未設定です: {relative}")
    if metadata.get("workflow_schema") != SCHEMA_VERSION:
        add(findings, "error", f"進行計画のworkflow_schemaは{SCHEMA_VERSION}である必要があります: {relative}")
    if metadata.get("document_type") != "request_plan":
        add(findings, "error", f"進行計画のdocument_typeはrequest_planである必要があります: {relative}")
    if metadata.get("request_id") != request_id:
        add(findings, "error", f"進行計画のrequest_idが依頼と一致しません: {relative}")
    if metadata.get("planning_status") != planning_status:
        add(findings, "error", f"進行計画と依頼のplanning_statusが一致しません: {request_id}")
    if project_ids and metadata.get("project_id") not in project_ids:
        add(findings, "error", f"進行計画のproject_idが案件と一致しません: {relative}")
    revision = metadata.get("plan_revision", "")
    if not revision.isdigit() or int(revision) < 1:
        add(findings, "error", f"進行計画のplan_revisionは1以上の整数である必要があります: {relative}")
    for field in ("approved_at", "updated_at"):
        value = metadata.get(field, "")
        if not is_placeholder(value) and not DATE_PATTERN.fullmatch(value):
            add(findings, "error", f"進行計画frontmatterの{field}の形式が不正です: {relative}")
    text = read_text(path)
    if metadata.get("plan_format") == "split":
        check_split_plan(path, metadata, request_id, planning_status, project_ids, root, findings)
        return
    for heading in PLAN_HEADINGS:
        if heading not in text:
            add(findings, "error", f"進行計画に必須見出しがありません: {heading}: {relative}")
    coverage = metadata.get("plan_coverage")
    if coverage not in {"partial", "full"}:
        add(findings, "error", f"進行計画のplan_coverageが不正です: {relative}")
    unplanned = section_text(text, "## 未計画の範囲")
    if coverage == "partial" and not any(len(r) >= 3 and r[0] != "範囲" and all(r[:3])
                                          for r in close_gate.table_rows(unplanned)):
        add(findings, "error", f"部分計画に未計画範囲と具体化条件がありません: {request_id}")
    if coverage == "full" and "なし" not in unplanned:
        add(findings, "error", f"全体計画の未計画範囲はなしと明示してください: {request_id}")
    rows = [r for r in close_gate.table_rows(section_text(text, "## Work候補")) if r and re.fullmatch(r"P-\d{3}", r[0])]
    if planning_status == "approved" and not rows:
        add(findings, "error", f"計画承認済みですがWork候補がありません: {request_id}")
    ids: set[str] = set()
    works: set[str] = set()
    for row in rows:
        if row[0] in ids:
            add(findings, "error", f"進行計画のP-IDが重複しています: {row[0]}")
        ids.add(row[0])
        if len(row) != 10 or row[8] not in {"planned", "completed", "cancelled"}:
            add(findings, "error", f"進行計画のWork候補行が不正です: {row[0]}")
            continue
        wid = row[9]
        if wid not in {"なし", "none", ""}:
            if not ID_PATTERNS["work"].fullmatch(wid) or wid in works:
                add(findings, "error", f"進行計画のWork IDが不正または重複しています: {wid}")
            works.add(wid)
            work = next((w for w in current_work_dirs(root) if w.name.startswith(wid + "_")), None)
            if not work or not (work / "作業内容.md").is_file():
                add(findings, "error", f"進行計画のWork IDに実体がありません: {wid}")
            else:
                scope = read_frontmatter(work / "作業内容.md")
                if scope.get("request_id") != request_id or scope.get("plan_item_id") != row[0]:
                    add(findings, "error", f"進行計画とWorkの関連が一致しません: {wid}")
                if row[8] in {"completed", "cancelled"} and scope.get("record_status") != row[8]:
                    add(findings, "error", f"計画の消化状態とWork状態が一致しません: {wid}")
        elif row[8] == "completed":
            add(findings, "error", f"消化済み計画項目にWork IDがありません: {row[0]}")

    if metadata.get("plan_format") == "wbs" and "## WBS・担当・日程" not in text:
        add(findings, "error", f"WBS型の進行計画にWBS表がありません: {request_id}")
    if "## WBS・担当・日程" in text:
        check_wbs(text, ids, findings)


def check_split_plan(path: Path, metadata: dict[str, str], request_id: str, planning_status: str,
                     project_ids: set[str], root: Path, findings: list[Finding]) -> None:
    """WBS（長期）と進行計画（次の区切り）を分けた計画を検査する。"""
    relative = nfc(path.relative_to(root).as_posix())
    text = read_text(path)
    for heading in SPLIT_PLAN_HEADINGS:
        if heading not in text:
            add(findings, "error", f"進行計画に必須見出しがありません: {heading}: {relative}")
    wbs_file = metadata.get("wbs_file", "")
    if wbs_file != f"02_CT_管理/進行計画/{request_id}_WBS.md":
        add(findings, "error", f"進行計画のwbs_fileの配置またはファイル名が不正です: {request_id}")
    wbs_path = root / wbs_file
    if not wbs_file or not wbs_path.is_file():
        add(findings, "error", f"進行計画のWBSがありません: {request_id}")
        return
    wbs_relative = nfc(wbs_path.relative_to(root).as_posix())
    wbs_meta = read_frontmatter(wbs_path)
    for key, expected in (("workflow_schema", SCHEMA_VERSION), ("document_type", "request_wbs"),
                          ("request_id", request_id)):
        if wbs_meta.get(key) != expected:
            add(findings, "error", f"WBSの{key}が一致しません: {wbs_relative}")
    if project_ids and wbs_meta.get("project_id") not in project_ids:
        add(findings, "error", f"WBSのproject_idが案件と一致しません: {wbs_relative}")
    for field in ("updated_at", "updated_by"):
        if is_placeholder(wbs_meta.get(field)):
            add(findings, "error", f"WBS frontmatterの{field}が未設定です: {wbs_relative}")
    wbs_text = read_text(wbs_path)
    for heading in WBS_HEADINGS:
        if heading not in wbs_text:
            add(findings, "error", f"WBSに必須見出しがありません: {heading}: {wbs_relative}")

    works = {}
    for work in current_work_dirs(root):
        scope_path = work / "作業内容.md"
        if scope_path.is_file():
            scope = read_frontmatter(scope_path)
            if scope.get("request_id") == request_id:
                works[scope.get("work_id", "")] = scope

    packages = close_gate.wbs_rows(wbs_text)
    if planning_status == "approved" and not packages:
        add(findings, "error", f"計画承認済みですがWBSに作業パッケージがありません: {request_id}")
    nodes: dict[str, list[str]] = {}
    for row in packages:
        if len(row) != 11:
            add(findings, "error", f"WBSの作業パッケージ行の列数が不正です: {row[0]}")
            continue
        if row[0] in nodes:
            add(findings, "error", f"WBSの計画項目IDが重複しています: {row[0]}")
        nodes[row[0]] = row
    for node_id, row in nodes.items():
        _, parent, title, _, _, start, end, predecessors, confidence, state, linked = row
        if parent != "なし" and parent not in nodes:
            add(findings, "error", f"WBSの親項目がありません: {node_id}")
        if not title:
            add(findings, "error", f"WBSの作業パッケージ名がありません: {node_id}")
        for value in (start, end):
            if value != "未定":
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                        raise ValueError(value)
                    date.fromisoformat(value)
                except ValueError:
                    add(findings, "error", f"WBSの予定日の形式が不正です: {node_id}")
        if start != "未定" and end != "未定" and start > end:
            add(findings, "error", f"WBSの開始・終了予定が逆転しています: {node_id}")
        if confidence not in close_gate.DATE_CONFIDENCE:
            add(findings, "error", f"WBSの日付の確度が不正です: {node_id}")
        if state not in close_gate.WBS_STATES:
            add(findings, "error", f"WBSの状態が不正です: {node_id}")
        for predecessor in close_gate.split_ids(predecessors):
            if predecessor not in nodes:
                add(findings, "error", f"WBSの先行IDがありません: {node_id} -> {predecessor}")
            elif start != "未定" and nodes[predecessor][6] != "未定" and start < nodes[predecessor][6]:
                add(findings, "error", f"WBSの先行作業が終了予定前です: {node_id}")
        expected_works = sorted(w for w, scope in works.items() if scope.get("plan_item_id") == node_id)
        if sorted(close_gate.split_ids(linked)) != expected_works:
            add(findings, "error", f"WBSの紐づくWorkがWorkのplan_item_idと一致しません: {node_id}")
    for work_id, scope in works.items():
        if scope.get("plan_item_id") not in nodes:
            add(findings, "error", f"Workのplan_item_idがWBSにありません: {work_id}")
    graph = {node_id: close_gate.split_ids(row[7]) + [c for c, r in nodes.items() if r[1] == node_id]
             for node_id, row in nodes.items()}
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            add(findings, "error", f"WBSの依存関係が循環しています: {node_id}")
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for nxt in graph.get(node_id, []):
            if nxt in nodes:
                visit(nxt)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in graph:
        visit(node_id)
    for row in close_gate.wbs_milestones(wbs_text):
        if len(row) != 6 or (row[1] != "未定" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[1])) \
                or row[2] not in close_gate.DATE_CONFIDENCE:
            add(findings, "error", f"WBSのマイルストーン行が不正です: {row[0]}")
    block = close_gate.gantt_block(wbs_text)
    if block is None:
        add(findings, "error", f"WBSにガントの生成区間がありません: {wbs_relative}")
    elif block != "\n".join(close_gate.render_gantt(wbs_text, close_gate.wbs_title(wbs_text))):
        add(findings, "error", f"WBSのガントが作業パッケージ表と一致しません（ganttコマンドで再生成してください）: {wbs_relative}")

    seen_works: set[str] = set()
    rows = close_gate.plan_work_rows(text)
    if planning_status == "approved" and not rows:
        add(findings, "error", f"計画承認済みですが今回始めるWorkがありません: {request_id}")
    for row in rows:
        if len(row) != 9:
            add(findings, "error", f"進行計画の今回始めるWorkの列数が不正です: {row[0]}")
            continue
        order, _, plan_id, _, _, _, _, state, work_id = row
        if plan_id not in nodes:
            add(findings, "error", f"進行計画の計画項目IDがWBSにありません: {order}: {plan_id}")
        if state not in close_gate.PLAN_WORK_STATES:
            add(findings, "error", f"進行計画のWorkの状態が不正です: {order}")
            continue
        if work_id == "未発行":
            if state not in {"未着手", "中止"}:
                add(findings, "error", f"開始済みの行にWork IDがありません: {order}")
            continue
        if state == "未着手":
            add(findings, "error", f"未着手の行にWork IDがあります: {order}")
        if not ID_PATTERNS["work"].fullmatch(work_id) or work_id in seen_works:
            add(findings, "error", f"進行計画のWork IDが不正または重複しています: {work_id}")
            continue
        seen_works.add(work_id)
        scope = works.get(work_id)
        if not scope:
            add(findings, "error", f"進行計画のWork IDに実体がありません: {work_id}")
            continue
        if scope.get("plan_item_id") != plan_id:
            add(findings, "error", f"進行計画とWorkの計画項目IDが一致しません: {work_id}")
        expected = {"完了": {"completed"}, "中止": {"cancelled"}}.get(state, {"active", "on_hold", "handoff"})
        if scope.get("record_status") not in expected:
            add(findings, "error", f"進行計画の行の状態とWork状態が一致しません: {work_id}")


def check_wbs(text: str, plan_ids: set[str], findings: list[Finding]) -> None:
    rows = [row for row in close_gate.table_rows(section_text(text, "## WBS・担当・日程"))
            if row and row[0] != "WBS ID"]
    nodes: dict[str, list[str]] = {}
    mapped: list[str] = []
    for row in rows:
        if len(row) != 8 or not re.fullmatch(r"[1-9]\d*(?:\.[1-9]\d*)*", row[0]):
            add(findings, "error", "WBSの行・ID形式が不正です")
            continue
        node_id, parent, title, plan_id, owner, start, end, predecessors = row
        if node_id in nodes:
            add(findings, "error", f"WBS IDが重複しています: {node_id}")
        nodes[node_id] = row
        expected_parent = node_id.rsplit(".", 1)[0] if "." in node_id else "なし"
        if parent != expected_parent:
            add(findings, "error", f"WBSの親階層が不正です: {node_id}")
        if not title or not owner:
            add(findings, "error", f"WBSの作業名・担当がありません: {node_id}")
        if plan_id != "なし":
            mapped.append(plan_id)
            if plan_id not in plan_ids:
                add(findings, "error", f"WBSに対応するP-IDがありません: {plan_id}")
        for value in (start, end):
            if value != "unknown":
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                        raise ValueError(value)
                    date.fromisoformat(value)
                except ValueError:
                    add(findings, "error", f"WBSの予定日の形式が不正です: {node_id}")
        if start != "unknown" and end != "unknown" and start > end:
            add(findings, "error", f"WBSの開始・終了予定が逆転しています: {node_id}")
    for plan_id in plan_ids:
        if mapped.count(plan_id) != 1:
            add(findings, "error", f"WBSとP-IDは1対1で対応させてください: {plan_id}")
    graph: dict[str, list[str]] = {}
    for node_id, row in nodes.items():
        children = [child for child in nodes.values() if child[1] == node_id]
        if row[1] != "なし" and row[1] not in nodes:
            add(findings, "error", f"WBSの親がありません: {node_id}")
        if children and row[3] != "なし":
            add(findings, "error", f"WBS集約行にP-IDがあります: {node_id}")
        predecessors = [] if row[7] == "なし" else [value.strip() for value in row[7].split(",")]
        graph[node_id] = predecessors + [child[0] for child in children]
        for predecessor in predecessors:
            if predecessor not in nodes:
                add(findings, "error", f"WBSの先行IDがありません: {node_id} -> {predecessor}")
            elif row[5] != "unknown" and nodes[predecessor][6] != "unknown" and row[5] < nodes[predecessor][6]:
                add(findings, "error", f"WBSの先行作業が終了予定前です: {node_id}")
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            add(findings, "error", f"WBSの依存関係が循環しています: {node_id}")
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for predecessor in graph.get(node_id, []):
            visit(predecessor)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in graph:
        visit(node_id)


def collect_ids(paths: list[Path], pattern: re.Pattern[str]) -> dict[str, list[Path]]:
    collected: dict[str, list[Path]] = {}
    for path in paths:
        match = pattern.search(path.name)
        if match:
            collected.setdefault(match.group(0), []).append(path)
    return collected


def current_work_dirs(root: Path) -> list[Path]:
    work_root = root / "04_WK_作業"
    return list(work_root.glob("W-*")) + list((work_root / "完了").glob("W-*"))


def check_duplicate_ids(root: Path, findings: list[Finding]) -> None:
    request_paths = close_gate.request_documents(root / "02_CT_管理/依頼", "RQ-*.md")
    request_paths += list((root / "99_AX_アーカイブ/依頼").glob("RQ-*"))
    work_paths = current_work_dirs(root)
    work_paths += list((root / "99_AX_アーカイブ/依頼").glob("RQ-*/work/W-*"))
    knowledge_paths = list((root / "07_KN_ナレッジ").glob("**/K-*.md"))
    for kind, paths in (
        ("request", request_paths),
        ("work", work_paths),
        ("knowledge", knowledge_paths),
    ):
        for item_id, occurrences in collect_ids(paths, ID_PATTERNS[kind]).items():
            if len(occurrences) > 1:
                joined = ", ".join(str(path.relative_to(root)) for path in occurrences)
                add(findings, "error", f"{item_id}が重複しています: {joined}")


def ids_in_file(path: Path, pattern: re.Pattern[str]) -> set[str]:
    if not path.is_file():
        return set()
    return set(pattern.findall(read_text(path)))


def work_todo_rows(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in section_text(text, "## TODO一覧").splitlines():
        if not re.match(r"^\|\s*T-\d{3}\s*\|", line):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 5:
            rows[cells[0]] = cells[4]
    return rows


def todo_log_section(text: str, todo_id: str) -> str:
    match = re.search(
        rf"^### TODO\s+{re.escape(todo_id)}(?:：|:|\s).*?(?=^###?\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(0) if match else ""


def dated_log_entries(todo_section: str) -> list[str]:
    return [
        match.group(0)
        for match in re.finditer(
            r"^#### 追記 \d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?.*?(?=^#### 追記 |\Z)",
            todo_section,
            re.MULTILINE | re.DOTALL,
        )
    ]


def check_work_record(work_dir: Path, root: Path, findings: list[Finding]) -> None:
    relative_dir = nfc(work_dir.relative_to(root).as_posix())
    directory_match = ID_PATTERNS["work"].search(work_dir.name)
    directory_id = directory_match.group(0) if directory_match else ""
    scope_path = work_dir / "作業内容.md"
    log_path = work_dir / "作業メモ.md"
    candidate_path = work_dir / "反映候補.md"
    input_path = work_dir / "入力" / "入力一覧.md"
    if not scope_path.is_file() or not log_path.is_file() or not candidate_path.is_file() or not input_path.is_file():
        return

    scope_metadata = read_frontmatter(scope_path)
    log_metadata = read_frontmatter(log_path)
    candidate_metadata = read_frontmatter(candidate_path)
    input_metadata = read_frontmatter(input_path)
    project_id = project_identity(root).get("project_id")
    request_ids = set(collect_ids(close_gate.request_documents(root / "02_CT_管理/依頼", "RQ-*.md"), ID_PATTERNS["request"]))
    request_ids.update(collect_ids(list((root / "99_AX_アーカイブ/依頼").glob("RQ-*")), ID_PATTERNS["request"]))
    for path, metadata, expected_type in (
        (scope_path, scope_metadata, "work_scope"),
        (log_path, log_metadata, "work_log"),
        (candidate_path, candidate_metadata, "work_candidates"),
        (input_path, input_metadata, "work_input_index"),
    ):
        relative = nfc(path.relative_to(root).as_posix())
        if not metadata:
            add(findings, "error", f"Work文書にfrontmatterがありません: {relative}")
            continue
        if metadata.get("workflow_schema") != SCHEMA_VERSION:
            add(findings, "error", f"Work文書のworkflow_schemaは{SCHEMA_VERSION}である必要があります: {relative}")
        if metadata.get("document_type") != expected_type:
            add(findings, "error", f"Work文書のdocument_typeは{expected_type}である必要があります: {relative}")
        if metadata.get("work_id") != directory_id:
            add(findings, "error", f"Workフォルダ名とwork_idが一致しません: {relative}")
        if metadata.get("record_status") not in WORK_STATUSES:
            add(findings, "error", f"Work文書のrecord_statusが不正です: {relative}")
        if not is_placeholder(project_id) and metadata.get("project_id") != project_id:
            add(findings, "error", f"Work文書のproject_idが案件と一致しません: {relative}")
        for field in ("project_id", "request_id", "updated_at", "updated_by"):
            if is_placeholder(metadata.get(field)):
                add(findings, "error", f"Work文書の{field}が未設定です: {relative}")
        updated_at = metadata.get("updated_at", "")
        if not is_placeholder(updated_at) and not DATE_PATTERN.fullmatch(updated_at):
            add(findings, "error", f"Work文書のupdated_at形式が不正です: {relative}")
        if expected_type == "work_input_index":
            for field in ("created_at", "baseline_at"):
                if is_placeholder(metadata.get(field)):
                    add(findings, "error", f"Work入力一覧の{field}が未設定です: {relative}")
                elif not DATE_PATTERN.fullmatch(metadata.get(field, "")):
                    add(findings, "error", f"Work入力一覧の{field}形式が不正です: {relative}")

    if scope_metadata.get("request_id") != log_metadata.get("request_id"):
        add(findings, "error", f"作業内容と作業メモのrequest_idが一致しません: {relative_dir}")
    if scope_metadata.get("request_id") != candidate_metadata.get("request_id"):
        add(findings, "error", f"作業内容と反映候補のrequest_idが一致しません: {relative_dir}")
    if scope_metadata.get("request_id") != input_metadata.get("request_id"):
        add(findings, "error", f"作業内容とWork入力一覧のrequest_idが一致しません: {relative_dir}")
    elif scope_metadata.get("request_id") not in request_ids:
        add(findings, "error", f"Workに対応する依頼がありません: {relative_dir}")
    if scope_metadata.get("record_status") != log_metadata.get("record_status"):
        add(findings, "error", f"作業内容と作業メモのrecord_statusが一致しません: {relative_dir}")
    if scope_metadata.get("record_status") != candidate_metadata.get("record_status"):
        add(findings, "error", f"作業内容と反映候補のrecord_statusが一致しません: {relative_dir}")
    if scope_metadata.get("record_status") != input_metadata.get("record_status"):
        add(findings, "error", f"作業内容とWork入力一覧のrecord_statusが一致しません: {relative_dir}")

    scope_text = read_text(scope_path)
    log_text = read_text(log_path)
    candidate_text = read_text(candidate_path)
    input_text = read_text(input_path)
    material_index_path = root / "01_IN_入力" / "入力資料一覧.md"
    material_index_text = read_text(material_index_path) if material_index_path.is_file() else ""
    for heading in ("## 目的・背景", "## 作業対象・対象外", "## 入力資料", "## 完了条件・確認方法", "## 関連作業"):
        if heading not in scope_text:
            add(findings, "error", f"作業内容に必須見出しがありません: {heading}: {relative_dir}")
    for heading in WORK_INPUT_HEADINGS:
        if heading not in input_text:
            add(findings, "error", f"Work入力一覧に必須見出しがありません: {heading}: {relative_dir}")
    for heading in WORK_LOG_HEADINGS:
        if heading not in log_text:
            add(findings, "error", f"作業メモに必須見出しがありません: {heading}: {relative_dir}")
    for heading in WORK_CANDIDATE_HEADINGS:
        if heading not in candidate_text:
            add(findings, "error", f"反映候補に必須見出しがありません: {heading}: {relative_dir}")
    if re.search(r"^###\s.*TODOの題名|^#### 追記 YYYY-MM-DD HH:MM", log_text, re.MULTILINE):
        add(findings, "error", f"作業メモにテンプレートのプレースホルダーが残っています: {relative_dir}")

    plan_item = scope_metadata.get("plan_item_id", "")
    requests = close_gate.request_documents(root / "02_CT_管理/依頼", f"{scope_metadata.get('request_id', '')}_*.md")
    if requests:
        rq = read_frontmatter(requests[0])
        plan = root / rq.get("plan_file", "none")
        if plan.is_file() and read_frontmatter(plan).get("plan_format") == "split":
            pass  # WBSの紐づくWork・進行計画の行との照合はcheck_split_planで行う
        elif plan.is_file():
            rows = [r for r in close_gate.table_rows(section_text(read_text(plan), "## Work候補")) if len(r) == 10 and r[0] == plan_item and r[9] == directory_id]
            if len(rows) != 1:
                add(findings, "error", f"Workのplan_item_idが計画の対応と一致しません: {relative_dir}")

    input_rows: dict[str, list[str]] = {}
    for line in section_text(input_text, "## 入力セット").splitlines():
        if not re.match(r"^\|\s*WI-\d{3}\s*\|", line):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        input_id = cells[0]
        if input_id in input_rows:
            add(findings, "error", f"Work入力IDが重複しています: {input_id}: {relative_dir}")
            continue
        input_rows[input_id] = cells
        if len(cells) < 9:
            add(findings, "error", f"Work入力行の列が不足しています: {input_id}: {relative_dir}")
            continue
        if cells[1] not in WORK_INPUT_TYPES:
            add(findings, "error", f"Work入力の区分が不正です: {input_id}: {relative_dir}")
        if cells[5] not in WORK_INPUT_METHODS:
            add(findings, "error", f"Work入力の取込方式が不正です: {input_id}: {relative_dir}")
        if cells[8] not in WORK_INPUT_STATES:
            add(findings, "error", f"Work入力の状態が不正です: {input_id}: {relative_dir}")
        if cells[3] in {"", "未設定"}:
            add(findings, "error", f"Work入力の元ID・元パスが未設定です: {input_id}: {relative_dir}")
        if cells[6] in {"", "未設定"}:
            add(findings, "error", f"Work入力の版・時点が未設定です: {input_id}: {relative_dir}")
        if cells[1] in {"received", "existing"}:
            material_ids = ID_PATTERNS["material"].findall(cells[3])
            if material_ids and any(material_id not in material_index_text for material_id in material_ids):
                add(findings, "error", f"Work入力のMAT IDが入力資料一覧にありません: {input_id}: {relative_dir}")
            elif not material_ids and "01_IN_入力/入力/" in cells[3]:
                add(findings, "error", f"受付資料台帳の入力にMAT IDがありません: {input_id}: {relative_dir}")
            elif not material_ids:
                source_fields = dict(
                    field.strip().split(": ", 1) for field in cells[3].split("; ") if ": " in field
                )
                if (not source_fields.get("入手元") or not source_fields.get("元資料")
                        or not DATE_PATTERN.fullmatch(source_fields.get("確認日", ""))):
                    add(findings, "error", f"Work追加資料の入手元・確認日・元資料が不足しています: {input_id}: {relative_dir}")
                local_source = (root / cells[4]).resolve()
                if (not local_source.is_relative_to((work_dir / "入力").resolve())
                        or not local_source.is_file()):
                    add(findings, "error", f"Work追加資料の保管先に実体がありません: {input_id}: {relative_dir}")
        if cells[5] in {"copy", "snapshot"} and cells[4] in {"", "なし", "未設定"}:
            add(findings, "error", f"copyまたはsnapshotのWork内配置先がありません: {input_id}: {relative_dir}")
        elif cells[5] in {"copy", "snapshot"}:
            local_path = (root / cells[4]).resolve()
            if not local_path.is_relative_to((work_dir / "入力").resolve()):
                add(findings, "error", f"copyまたはsnapshotの配置先がWorkの入力配下ではありません: {input_id}: {relative_dir}")
            elif not local_path.is_file():
                add(findings, "error", f"Work入力の配置先に実体がありません: {input_id}: {relative_dir}")
    if not input_rows:
        add(findings, "error", f"Work入力一覧に入力がありません: {relative_dir}")
    for local_input in (work_dir / "入力").rglob("*"):
        if not local_input.is_file() or local_input == input_path or local_input.name.startswith("."):
            continue
        local_relative = nfc(local_input.relative_to(root).as_posix())
        if local_relative not in input_text:
            add(findings, "error", f"Work内入力が入力一覧に登録されていません: {local_relative}")

    summary = work_dir / "入力/Work入力.md"
    if not summary.is_file():
        add(findings, "error", f"1枚のWork入力がありません: {relative_dir}")
    else:
        sm = read_frontmatter(summary)
        for key, expected in (("workflow_schema", SCHEMA_VERSION), ("document_type", "work_input_summary"),
                              ("work_id", directory_id), ("request_id", scope_metadata.get("request_id"))):
            if sm.get(key) != expected:
                add(findings, "error", f"Work入力要約の{key}が一致しません: {relative_dir}")
    if scope_metadata.get("record_status") != "active" and not (work_dir / "終了判断.md").is_file():
        add(findings, "error", f"終了状態のWorkに終了判断がありません: {relative_dir}")
    for error in close_gate.validate(work_dir, root):
        add(findings, "error", f"{error}: {relative_dir}")
    if (work_dir / "終了判断.md").is_file() and scope_metadata.get("record_status") != "active":
        if read_frontmatter(work_dir / "終了判断.md").get("decision_status") != "synced":
            add(findings, "error", f"終了状態のWorkに未同期の終了判断があります: {relative_dir}")

    todo_rows = work_todo_rows(log_text)
    if not todo_rows:
        add(findings, "error", f"作業メモにTODOがありません: {relative_dir}")
    for todo_id, state in todo_rows.items():
        if state not in TODO_STATES:
            add(findings, "error", f"TODOの状態が不正です: {todo_id}: {relative_dir}")
        todo_section = todo_log_section(log_text, todo_id)
        if not todo_section:
            add(findings, "error", f"作業メモにTODOの記録先がありません: {todo_id}: {relative_dir}")
            continue
        entries = dated_log_entries(todo_section)
        if state != "未着手" and not entries:
            add(findings, "error", f"着手済みTODOに日付付き作業記録がありません: {todo_id}: {relative_dir}")
        for entry in entries:
            for heading in WORK_LOG_ENTRY_HEADINGS:
                if heading not in entry:
                    add(findings, "error", f"TODOの日付付き作業記録に必須欄がありません: {heading}: {todo_id}: {relative_dir}")

    resolution_section = section_text(candidate_text, "## 反映候補の処理履歴")
    candidate_counts: dict[str, int] = {}
    for heading in WORK_CANDIDATE_HEADINGS[:-1]:
        for cells in candidate_rows(section_text(candidate_text, heading), heading):
            candidate_id = cells[0]
            candidate_counts[candidate_id] = candidate_counts.get(candidate_id, 0) + 1
            expected_prefix = {"## Context候補": "CTX", "## 意思決定候補": "DEC", "## Knowledge候補": "KNW", "## Product反映候補": "PRD"}
            if heading in expected_prefix and not candidate_id.startswith(f"C-{expected_prefix[heading]}-"):
                add(findings, "error", f"反映候補IDの区分が見出しと一致しません: {candidate_id}: {relative_dir}")
            if heading == "## リスク・課題候補" and not candidate_id.startswith(("C-RSK-", "C-ISS-")):
                add(findings, "error", f"反映候補IDの区分が見出しと一致しません: {candidate_id}: {relative_dir}")
            if len(cells) < {"## Context候補": 10, "## 意思決定候補": 8, "## リスク・課題候補": 10, "## Knowledge候補": 7, "## Product反映候補": 7}[heading]:
                add(findings, "error", f"反映候補の項目が不足しています: {candidate_id}: {relative_dir}")
                continue
            if any(not value for value in cells[1:10 if heading == "## Context候補" else len(cells)]):
                add(findings, "error", f"反映候補の必須項目が未設定です: {candidate_id}: {relative_dir}")
            source_todo = re.search(r"T-\d{3}", cells[1])
            if not source_todo or source_todo.group(0) not in todo_rows or "作業メモ" not in cells[1]:
                add(findings, "error", f"反映候補の元TODO・作業メモが不正です: {candidate_id}: {relative_dir}")
            elif candidate_id not in todo_log_section(log_text, source_todo.group(0)):
                add(findings, "error", f"反映候補が元TODOの作業メモから参照されていません: {candidate_id}: {relative_dir}")
            if candidate_id.startswith("C-CTX-") and heading == "## Context候補":
                if cells[2] not in CONTEXT_CANDIDATE_TYPES:
                    add(findings, "error", f"Context反映候補の候補種別が不正です: {candidate_id}: {relative_dir}")
                if len(cells) > 10 and cells[10] not in {"", "-"} and cells[10] not in CONTEXT_CANDIDATE_SECTIONS.get(cells[2], ()):
                    add(findings, "error", f"Context反映先セクションが候補種別と一致しません: {candidate_id}: {relative_dir}")
                if cells[3] not in CONTEXT_CHANGE_TYPES:
                    add(findings, "error", f"Context反映候補の変更種別が不正です: {candidate_id}: {relative_dir}")
                if cells[3] == "追加" and cells[4] != "新規":
                    add(findings, "error", f"Context追加候補の対象CTXは新規である必要があります: {candidate_id}: {relative_dir}")
                if cells[3] in {"変更", "廃止"} and not ID_PATTERNS["context"].fullmatch(cells[4]):
                    add(findings, "error", f"Context変更・廃止候補の対象CTXが不正です: {candidate_id}: {relative_dir}")
                if cells[5] in {"", "-", "未設定"}:
                    add(findings, "error", f"Context反映候補の適用範囲が未設定です: {candidate_id}: {relative_dir}")
                if cells[8] not in WORK_INPUT_STATES:
                    add(findings, "error", f"Context反映候補の状態が不正です: {candidate_id}: {relative_dir}")
                if cells[9] in {"", "-", "未設定"}:
                    add(findings, "error", f"Context反映候補の根拠が未設定です: {candidate_id}: {relative_dir}")
    # 見出し前の説明文にある書式例は記録ではないため、### 見出し以降だけを照合する。
    record_text = section_text(log_text, "## TODOごとの作業記録").partition("\n### ")[2]
    log_ids = set(CANDIDATE_ID_PATTERN.findall(record_text))
    for candidate_id in sorted(log_ids - candidate_counts.keys()):
        add(findings, "error", f"作業メモの候補IDが反映候補にありません: {candidate_id}: {relative_dir}")
    for candidate_id, count in sorted(candidate_counts.items()):
        if count > 1:
            add(findings, "error", f"反映候補IDが重複しています: {candidate_id}: {relative_dir}")
    candidate_ids = set(candidate_counts)
    resolution_ids = set(CANDIDATE_ID_PATTERN.findall(resolution_section))
    latest_resolution_state: dict[str, str] = {}
    for line in resolution_section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and CANDIDATE_ID_PATTERN.fullmatch(cells[1]):
            latest_resolution_state[cells[1]] = cells[3]
    for candidate_id in sorted(resolution_ids - candidate_ids):
        add(findings, "error", f"反映候補の処理履歴に対応する候補がありません: {candidate_id}: {relative_dir}")

    if scope_metadata.get("record_status") != "active":
        unresolved_candidate_ids = candidate_ids - resolution_ids
        for candidate_id in sorted(unresolved_candidate_ids):
            add(findings, "error", f"終了状態のWorkに未処理の反映候補があります: {candidate_id}: {relative_dir}")
        for candidate_id in sorted(candidate_ids & resolution_ids):
            if latest_resolution_state.get(candidate_id) not in {"同期済み", "同期不要"}:
                add(findings, "error", f"終了状態のWorkに未同期の反映候補があります: {candidate_id}: {relative_dir}")


def check_knowledge(root: Path, findings: list[Finding]) -> None:
    index_path = root / "07_KN_ナレッジ/ナレッジ一覧.md"
    index_text = read_text(index_path) if index_path.is_file() else ""
    knowledge_paths = [
        path for path in (root / "07_KN_ナレッジ").rglob("K-*.md")
        if nfc(path.name) != "ナレッジ一覧.md"
    ]
    knowledge_ids = set(collect_ids(knowledge_paths, ID_PATTERNS["knowledge"]))
    indexed_ids = set(ID_PATTERNS["knowledge"].findall(index_text))
    project_id = project_identity(root).get("project_id")
    request_ids = set(collect_ids(close_gate.request_documents(root / "02_CT_管理/依頼", "RQ-*.md"), ID_PATTERNS["request"]))
    request_ids.update(collect_ids(list((root / "99_AX_アーカイブ/依頼").glob("RQ-*")), ID_PATTERNS["request"]))
    work_ids = set(collect_ids(current_work_dirs(root), ID_PATTERNS["work"]))
    work_ids.update(collect_ids(list((root / "99_AX_アーカイブ/依頼").glob("RQ-*/work/W-*")), ID_PATTERNS["work"]))
    for knowledge_id in sorted(knowledge_ids - indexed_ids):
        add(findings, "error", f"ナレッジ一覧に登録されていません: {knowledge_id}")
    for knowledge_id in sorted(indexed_ids - knowledge_ids):
        add(findings, "error", f"ナレッジ一覧に実体がありません: {knowledge_id}")

    for path in knowledge_paths:
        relative = nfc(path.relative_to(root).as_posix())
        metadata = read_frontmatter(path)
        match = ID_PATTERNS["knowledge"].search(path.name)
        filename_id = match.group(0) if match else ""
        required = (
            "workflow_schema", "document_type", "project_id", "knowledge_id",
            "knowledge_type", "title", "knowledge_status", "source_request",
            "source_work", "approved_at", "approved_by", "created_at",
            "updated_at", "updated_by",
        )
        for field in required:
            if is_placeholder(metadata.get(field)):
                add(findings, "error", f"Knowledge frontmatterの{field}が未設定です: {relative}")
        if metadata.get("workflow_schema") != SCHEMA_VERSION:
            add(findings, "error", f"Knowledgeのworkflow_schemaは{SCHEMA_VERSION}である必要があります: {relative}")
        if metadata.get("document_type") != "project_knowledge":
            add(findings, "error", f"Knowledgeのdocument_typeはproject_knowledgeである必要があります: {relative}")
        if metadata.get("knowledge_id") != filename_id:
            add(findings, "error", f"Knowledgeファイル名とknowledge_idが一致しません: {relative}")
        id_parts = filename_id.split("-")
        expected_type = KNOWLEDGE_TYPES.get(id_parts[1]) if len(id_parts) >= 3 else None
        if expected_type and metadata.get("knowledge_type") != expected_type:
            add(findings, "error", f"Knowledge IDとknowledge_typeが一致しません: {relative}")
        if metadata.get("knowledge_status") not in KNOWLEDGE_STATUSES:
            add(findings, "error", f"Knowledgeのknowledge_statusが不正です: {relative}")
        if not is_placeholder(project_id) and metadata.get("project_id") != project_id:
            add(findings, "error", f"Knowledgeのproject_idが案件と一致しません: {relative}")
        source_requests = set(ID_PATTERNS["request"].findall(metadata.get("source_request", "")))
        source_works = set(ID_PATTERNS["work"].findall(metadata.get("source_work", "")))
        if not source_requests:
            add(findings, "error", f"Knowledgeのsource_requestにRQ IDがありません: {relative}")
        elif source_requests - request_ids:
            add(findings, "error", f"Knowledgeのsource_requestに対応する依頼がありません: {relative}")
        if not source_works:
            add(findings, "error", f"Knowledgeのsource_workにWork IDがありません: {relative}")
        elif source_works - work_ids:
            add(findings, "error", f"Knowledgeのsource_workに対応するWorkがありません: {relative}")
        for field in ("approved_at", "created_at", "updated_at"):
            value = metadata.get(field, "")
            if not is_placeholder(value) and not DATE_PATTERN.fullmatch(value):
                add(findings, "error", f"Knowledge frontmatterの{field}形式が不正です: {relative}")
        matching_rows = [
            line for line in index_text.splitlines()
            if re.match(rf"^\|\s*{re.escape(filename_id)}\s*\|", line)
        ]
        if len(matching_rows) > 1:
            add(findings, "error", f"ナレッジ一覧で{filename_id}が重複しています")
        elif len(matching_rows) == 1:
            cells = [cell.strip().strip("`") for cell in matching_rows[0].strip().strip("|").split("|")]
            if len(cells) <= 3 or cells[2] != metadata.get("title"):
                add(findings, "error", f"ナレッジ一覧とKnowledge frontmatterのtitleが一致しません: {filename_id}")
            if len(cells) <= 3 or cells[3] != metadata.get("knowledge_status"):
                add(findings, "error", f"ナレッジ一覧とKnowledge frontmatterのknowledge_statusが一致しません: {filename_id}")
            if len(cells) <= 8 or cells[8] != relative:
                add(findings, "error", f"ナレッジ一覧の参照先が実体と一致しません: {filename_id}")


def check_context_records(root: Path, findings: list[Finding]) -> None:
    # 登録時は解消作業を「未割当（Plan）」にでき、計画承認後に計画項目IDへ付け替える（IMP-005）。
    planned_request_ids = {
        meta.get("request_id", "") for path in close_gate.request_documents(root / "02_CT_管理/依頼", "RQ-*.md")
        if (meta := read_frontmatter(path)).get("planning_status") == "approved"
    }
    legacy: dict[str, int] = {}
    types: set[str] = set()
    for path in context_paths(root):
        text = read_text(path)
        for item_id, item_text in context_items(text):
            attrs = record_attributes(item_text)
            kind = attrs.get("種別", "")
            types.add(kind)
            if kind not in CONTEXT_CANDIDATE_TYPES:
                add(findings, "error", f"Contextの種別が不正です: {item_id}")
            for field in ("applies_to", "applicability"):
                if not attrs.get(field):
                    add(findings, "error", f"Contextの{field}がありません: {item_id}")
            if attrs.get("applicability") not in {"applicable", "not_applicable"}:
                add(findings, "error", f"Contextのapplicabilityが不正です: {item_id}")
            if attrs.get("knowledge_state") in {"unknown", "conflict"}:
                for field in ("resolution_task_ref", "required_by", "impact"):
                    if not attrs.get(field):
                        add(findings, "error", f"未確認Contextの{field}がありません: {item_id}")
                scope_ids = set(ID_PATTERNS["request"].findall(attrs.get("applies_to", "")))
                targets = planned_request_ids if attrs.get("applies_to") == "project" else scope_ids & planned_request_ids
                if attrs.get("resolution_task_ref", "").startswith(UNASSIGNED_TASK_REF) and targets:
                    add(findings, "warning", f"計画承認後も解消作業が未割当です（Planで計画項目IDを割り当ててください）: {item_id}")
            if attrs.get("knowledge_state") in {"unknown", "conflict"} or attrs.get("approval_state") == "pending":
                if attrs.get("blocking") not in {"true", "false"}:
                    add(findings, "error", f"Contextのblockingが未設定または不正です: {item_id}")
            if attrs.get("due_at") not in {None, "unknown"} and not DATE_PATTERN.fullmatch(attrs["due_at"]):
                add(findings, "error", f"Contextのdue_at形式が不正です: {item_id}")
            index = root / "03_CX_コンテキスト/Context一覧.md"
            indexed = [r for r in close_gate.table_rows(read_text(index)) if r and r[0] == item_id] if index.is_file() else []
            if len(indexed) == 1 and len(indexed[0]) >= 10:
                for column, field in ((1, "種別"), (3, "applies_to"), (4, "knowledge_state"), (5, "approval_state"), (6, "lifecycle_state"), (7, "blocking")):
                    if attrs.get(field, "") != indexed[0][column]:
                        add(findings, "error", f"Context一覧と本体の{field}が一致しません: {item_id}")
                if unicodedata.normalize("NFC", indexed[0][9]) != unicodedata.normalize("NFC", path.name):
                    add(findings, "error", f"Context一覧と本体の配置先が一致しません: {item_id}")
            if attrs.get("applicability") == "not_applicable":
                if not attrs.get("reason"):
                    add(findings, "error", f"適用外Contextのreasonがありません: {item_id}")
                continue
            for field, allowed in (("knowledge_state", {"confirmed", "assumption", "unknown", "conflict"}),
                                   ("approval_state", {"not_required", "pending", "approved"}),
                                   ("lifecycle_state", {"active", "scheduled", "suspended"})):
                if attrs.get(field) not in allowed:
                    add(findings, "error", f"Contextの{field}が不正です: {item_id}")
            if attrs.get("knowledge_state") in {"confirmed", "conflict"} and not (attrs.get("evidence") or attrs.get("basis")):
                add(findings, "error", f"Contextの根拠がありません: {item_id}")
            if attrs.get("knowledge_state") == "assumption" and not any(attrs.get(k) for k in ("basis", "evidence", "rationale", "approval_ref")):
                add(findings, "error", f"Contextの仮定の根拠がありません: {item_id}")
            if attrs.get("approval_state") == "approved" and not all(attrs.get(k) for k in ("approval_ref", "approved_by", "approved_at")):
                add(findings, "error", f"Contextの承認根拠が不足しています: {item_id}")
            for field in ({"decision": ("decided_by", "decided_at", "rationale", "impact"),
                           "risk": ("cause", "impact", "likelihood", "response", "owner", "due_at", "resolution_task_ref"),
                           "issue": ("cause", "impact", "response", "owner", "due_at", "resolution_task_ref")}.get(kind, ())):
                if not attrs.get(field):
                    add(findings, "error", f"{kind} Contextの{field}がありません: {item_id}")
            for old_id in re.findall(r"(?:DEC|RSK|ISS)-\d{4}", attrs.get("legacy_id", "")):
                legacy[old_id] = legacy.get(old_id, 0) + 1
    for old_id, count in legacy.items():
        if count > 1:
            add(findings, "error", f"Contextのlegacy_idで{old_id}が重複しています")
    if close_gate.request_documents(root / "02_CT_管理/依頼", "RQ-*.md"):
        for group in ({"objective", "success_condition"}, {"stakeholder", "authority"}, {"scope"}, {"requirement", "expectation"},
                      {"assumption", "constraint", "unknown", "conflict"}, {"acceptance"}):
            if not types & group:
                add(findings, "error", f"案件Contextの最小核が不足しています: {'/'.join(sorted(group))}")
    for old in ("案件概要.md", "意思決定記録.md"):
        if (root / "02_CT_管理" / old).exists():
            add(findings, "error", f"旧管理正本をContextへ移行してください: 02_CT_管理/{old}")
    for old in ("依頼", "進行計画"):
        if (root / "03_CX_コンテキスト" / old).exists():
            add(findings, "error", f"依頼・進行計画の正本を管理へ移行してください: 03_CX_コンテキスト/{old}")


def check_indexes(root: Path, findings: list[Finding]) -> None:
    request_files = close_gate.request_documents(root / "02_CT_管理/依頼", "RQ-*.md")
    request_ids = set(collect_ids(request_files, ID_PATTERNS["request"]))
    indexed_requests = ids_in_file(root / "02_CT_管理/依頼一覧.md", ID_PATTERNS["request"])
    for request_id in sorted(request_ids - indexed_requests):
        add(findings, "error", f"依頼一覧に登録されていません: {request_id}")

    request_by_id = {
        metadata.get("request_id", ""): (path, metadata)
        for path in request_files
        if (metadata := read_frontmatter(path))
    }
    for plan_path in close_gate.request_documents(root / "02_CT_管理/進行計画", "RQ-*.md"):
        plan_metadata = read_frontmatter(plan_path)
        request_id = plan_metadata.get("request_id", "")
        relative = nfc(plan_path.relative_to(root).as_posix())
        if request_id not in request_by_id:
            add(findings, "error", f"対応する現行依頼がない進行計画です: {relative}")
            continue
        _, request_metadata = request_by_id[request_id]
        if plan_metadata.get("document_type") == "request_wbs":
            linked_plan = root / request_metadata.get("plan_file", "none")
            if not linked_plan.is_file() or read_frontmatter(linked_plan).get("wbs_file") != relative:
                add(findings, "error", f"進行計画から参照されていないWBSです: {relative}")
            continue
        if request_metadata.get("plan_file") != relative:
            add(findings, "error", f"依頼から参照されていない進行計画です: {relative}")

    # 登録前の依頼承認記録（提示中の登録案）は依頼の検査対象にならないため、ここで書式と提示中を確認する。
    for folder, scope in (("依頼", "request"), ("進行計画", "plan")):
        for approval in sorted((root / "02_CT_管理" / folder).glob(f"RQ-*_*{close_gate.APPROVAL_SUFFIX}.md")):
            approval_request = approval.name.split("_", 1)[0]
            if approval_request not in request_by_id:
                check_approval_record(approval, scope, root, findings, approval_request)

    work_dirs = current_work_dirs(root)
    work_ids = set(collect_ids(work_dirs, ID_PATTERNS["work"]))
    indexed_work = ids_in_file(root / "02_CT_管理/Work一覧.md", ID_PATTERNS["work"])
    work_index_path = root / "02_CT_管理/Work一覧.md"
    work_index_text = read_text(work_index_path) if work_index_path.is_file() else ""
    for work_id in sorted(work_ids - indexed_work):
        add(findings, "error", f"Work一覧に登録されていません: {work_id}")
    for work_dir in work_dirs:
        if work_dir.parent.name == "完了" and read_frontmatter(work_dir / "作業内容.md").get("record_status") != "completed":
            add(findings, "error", f"完了フォルダに未完了Workがあります: {work_dir.relative_to(root)}")
        if work_dir.parent == root / "04_WK_作業" and read_frontmatter(work_dir / "作業内容.md").get("record_status") == "completed":
            add(findings, "error", f"完了Workが完了フォルダへ移動されていません: {work_dir.relative_to(root)}")
        for required in ("作業内容.md", "作業メモ.md", "反映候補.md", "入力/入力一覧.md"):
            if not (work_dir / required).is_file():
                add(findings, "error", f"{required}がありません: {work_dir.relative_to(root)}")
        check_work_record(work_dir, root, findings)
        match = ID_PATTERNS["work"].search(work_dir.name)
        work_id = match.group(0) if match else ""
        if (work_dir / "作業内容.md").is_file():
            check_approval_record(work_dir / "承認記録.md", "work", root, findings,
                                  read_frontmatter(work_dir / "作業内容.md").get("request_id", ""), work_id,
                                  required_kinds={"開始承認"})
        matching_rows = [
            line for line in work_index_text.splitlines()
            if re.match(rf"^\|\s*{re.escape(work_id)}\s*\|", line)
        ]
        if len(matching_rows) > 1:
            add(findings, "error", f"Work一覧で{work_id}が重複しています")
        elif len(matching_rows) == 1 and (work_dir / "作業内容.md").is_file():
            cells = [cell.strip().strip("`") for cell in matching_rows[0].strip().strip("|").split("|")]
            metadata = read_frontmatter(work_dir / "作業内容.md")
            if len(cells) <= 3 or cells[3] != metadata.get("record_status"):
                add(findings, "error", f"Work一覧と作業内容のrecord_statusが一致しません: {work_id}")
            expected_path = nfc(work_dir.relative_to(root).as_posix())
            if len(cells) <= 9 or cells[9] != expected_path:
                add(findings, "error", f"Work一覧のWorkフォルダが実体と一致しません: {work_id}")

def check_input_materials(root: Path, findings: list[Finding]) -> None:
    index_path = root / "01_IN_入力/入力資料一覧.md"
    if not index_path.is_file():
        return
    index_text = read_text(index_path)
    material_occurrences: dict[str, int] = {}
    for line in index_text.splitlines():
        if not line.startswith("|"):
            continue
        for material_id in ID_PATTERNS["material"].findall(line):
            material_occurrences[material_id] = material_occurrences.get(material_id, 0) + 1
    for material_id, count in sorted(material_occurrences.items()):
        if count > 1:
            add(findings, "error", f"入力資料一覧で{material_id}が重複しています")

    # 受付中（draft/ready）は、原本を置いてからRequest StartでMATを採番するまでの正常な中間状態。
    intake_path = root / "01_IN_入力/依頼受付.md"
    intake_open = intake_path.is_file() and read_frontmatter(intake_path).get("record_status") in {"draft", "ready"}
    for path in (root / "01_IN_入力/入力").rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        relative = nfc(path.relative_to(root).as_posix())
        if relative not in index_text:
            if intake_open:
                add(findings, "warning", f"受付中の原本が入力資料一覧に未登録です（Request Startで登録）: {relative}")
            else:
                add(findings, "error", f"入力資料一覧に登録されていません: {relative}")


REQUEST_CLOSURE_HEADINGS = (
    "## 終了理由と結果",
    "## 関連Workの最終状態",
    "## 作業結果・Product・Knowledge",
    "## 残件と引継ぎ先",
    "## 継続して参照するContext",
    "## Context反映の最終確認",
    "## 入力の保存と初期化",
    "## 管理文書の整理",
    "## 参照移動対応",
    "## 承認と検査結果",
)
REQUEST_CONTEXT_CHECKS = (
    "成果・確定事項", "未反映候補・残件", "進捗・次アクション・サマリ", "参照・トレーサビリティ",
)
REQUEST_CLOSURE_RECORDS = (
    "依頼受付.md", "入力資料一覧.md", "現在地.md", "依頼一覧.md", "Work一覧.md", "更新履歴.md",
)


def check_request_closure(summary_path: Path, request_id: str, findings: list[Finding]) -> None:
    metadata = read_frontmatter(summary_path)
    if "closure_contract" not in metadata:
        return
    if metadata.get("closure_contract") != "1":
        add(findings, "error", f"終了サマリのclosure_contractが不正です: {request_id}")
    for key, expected in (("workflow_schema", SCHEMA_VERSION),
                          ("document_type", "request_closure_summary"), ("request_id", request_id)):
        if metadata.get(key) != expected:
            add(findings, "error", f"終了サマリの{key}が一致しません: {request_id}")
    # pendingは整理途中の正常な状態。完了可否はverify-request-closeで対象依頼だけを判定する。
    if metadata.get("cleanup_status") == "pending":
        add(findings, "warning", f"依頼終了の整理が未完了です（cleanup_status: pending）: {request_id}")
    elif metadata.get("cleanup_status") != "completed":
        add(findings, "error", f"終了サマリのcleanup_statusが不正です: {request_id}")
    if metadata.get("final_status") not in {"completed", "cancelled"}:
        add(findings, "error", f"終了サマリのfinal_statusが不正です: {request_id}")
    for key in ("project_id", "closed_at", "closed_by", "approved_at", "approved_by"):
        if is_placeholder(metadata.get(key)) or metadata.get(key) == "none":
            add(findings, "error", f"終了サマリの{key}が未設定です: {request_id}")
    for key in ("closed_at", "approved_at"):
        if not DATE_PATTERN.fullmatch(metadata.get(key, "")):
            add(findings, "error", f"終了サマリの{key}形式が不正です: {request_id}")
    text = read_text(summary_path)
    for heading in REQUEST_CLOSURE_HEADINGS:
        content = close_gate.section(text, heading).strip()
        if not content or content in {"TBD", "未記入"}:
            add(findings, "error", f"終了サマリに内容がありません: {heading}: {request_id}")
    context_rows = close_gate.table_rows(close_gate.section(text, "## Context反映の最終確認"))
    for target in REQUEST_CONTEXT_CHECKS:
        rows = [row for row in context_rows if row and row[0] == target]
        if (len(rows) != 1 or len(rows[0]) != 4
                or rows[0][1] not in {"reflected", "no_change"}
                or is_placeholder(rows[0][2])
                or (rows[0][1] == "no_change" and is_placeholder(rows[0][3]))):
            add(findings, "error", f"Context最終確認の判定・根拠・更新不要理由が不足しています: {target}: {request_id}")


def check_request_archive_cleanup(root: Path, request_dir: Path, request_id: str,
                                  findings: list[Finding]) -> None:
    summary = request_dir / "終了サマリ.md"
    if read_frontmatter(summary).get("closure_contract") != "1":
        return
    records = request_dir / "記録"
    for name in REQUEST_CLOSURE_RECORDS:
        if not (records / name).is_file():
            add(findings, "error", f"整理前記録がありません: {request_id}: 記録/{name}")
    current_materials = root / "01_IN_入力/入力資料一覧.md"
    current_rows = close_gate.table_rows(read_text(current_materials)) if current_materials.is_file() else []
    mappings = []
    for row in close_gate.table_rows(close_gate.section(read_text(summary), "## 参照移動対応")):
        if row and row[0] == "旧参照":
            continue
        if len(row) != 4 or row[2] not in {"input", "record", "request", "plan", "work"}:
            add(findings, "error", f"参照移動対応の行が不正です: {request_id}")
            continue
        valid = True
        for value in row[:2]:
            path = Path(value)
            if (not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value
                    or not (root / path).resolve().is_relative_to(root.resolve())):
                add(findings, "error", f"参照移動対応のパスが不正です: {request_id}: {value}")
                valid = False
        if not valid:
            continue
        source, destination = (root / row[0], root / row[1])
        is_work = row[2] == "work"
        if not (destination.is_dir() if is_work else destination.is_file()):
            add(findings, "error", f"参照移動先がありません: {request_id}: {row[1]}")
        if row[2] in {"input", "record"}:
            if not re.fullmatch(r"[0-9a-fA-F]{64}", row[3]):
                add(findings, "error", f"原本・整理前記録のSHA256が不正です: {request_id}: {row[1]}")
            elif destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() != row[3].lower():
                add(findings, "error", f"原本・整理前記録のSHA256が一致しません: {request_id}: {row[1]}")
        expected_root = request_dir / {"input": "input", "record": "記録", "work": "work"}.get(row[2], "")
        retained_input = row[2] == "input" and row[0] == row[1] and destination.is_relative_to(root / "01_IN_入力/入力")
        if not retained_input and not destination.is_relative_to(expected_root):
            add(findings, "error", f"参照移動先が対象依頼の保存先ではありません: {request_id}: {row[1]}")
        reused_input_path = row[2] == "input" and any(
            len(current) >= 9 and ID_PATTERNS["material"].fullmatch(current[0])
            and current[4] == row[0] and request_id not in ID_PATTERNS["request"].findall(current[7])
            for current in current_rows
        )
        if row[2] != "record" and row[0] != row[1] and source.exists() and not reused_input_path:
            add(findings, "error", f"移動済み資料・管理実体が旧配置に残っています: {request_id}: {row[0]}")
        mappings.append(row)
    mapped_destinations = {row[1] for row in mappings}
    for name in REQUEST_CLOSURE_RECORDS:
        relative = nfc((records / name).relative_to(root).as_posix())
        if not any(row[1] == relative and row[2] == "record" for row in mappings):
            add(findings, "error", f"整理前記録の保存対応がありません: {request_id}: {name}")
    old_materials = records / "入力資料一覧.md"
    if old_materials.is_file():
        for row in close_gate.table_rows(read_text(old_materials)):
            if len(row) < 9 or not ID_PATTERNS["material"].fullmatch(row[0]) or request_id not in ID_PATTERNS["request"].findall(row[7]):
                continue
            matches = [current for current in current_rows if current and current[0] == row[0]]
            if len(matches) != 1 or len(matches[0]) < 9:
                add(findings, "error", f"終了依頼のMAT索引が失われています: {request_id}: {row[0]}")
            elif not any(mapping[0] == row[4] and mapping[1] == matches[0][4] and mapping[2] == "input" for mapping in mappings):
                add(findings, "error", f"受付原本の保存対応がありません: {request_id}: {row[0]}")
    archived_work_ids = set(collect_ids(list((request_dir / "work").glob("W-*")), ID_PATTERNS["work"]))
    work_snapshot = records / "Work一覧.md"
    if work_snapshot.is_file():
        for row in close_gate.table_rows(read_text(work_snapshot)):
            if len(row) >= 10 and ID_PATTERNS["work"].fullmatch(row[0]) and row[1] == request_id:
                if row[0] not in archived_work_ids:
                    add(findings, "error", f"関連Workがアーカイブされていません: {request_id}: {row[0]}")
                if not any(mapping[0] == row[9] and mapping[2] == "work" for mapping in mappings):
                    add(findings, "error", f"Workの移動対応がありません: {request_id}: {row[0]}")
    for path in current_work_dirs(root):
        if read_frontmatter(path / "作業内容.md").get("request_id") == request_id:
            add(findings, "error", f"終了依頼のWorkが現行領域に残っています: {request_id}: {path.name}")
    for directory in ("依頼", "進行計画"):
        if list((root / "02_CT_管理" / directory).glob(f"{request_id}_*.md")):
            add(findings, "error", f"終了依頼の管理実体が現行領域に残っています: {request_id}: {directory}")
    work_index = root / "02_CT_管理/Work一覧.md"
    if work_index.is_file():
        for row in close_gate.table_rows(read_text(work_index)):
            if len(row) >= 2 and (row[0] in archived_work_ids or row[1] == request_id):
                add(findings, "error", f"終了依頼のWork行が現行一覧に残っています: {request_id}: {row[0]}")
    status_path = root / "02_CT_管理/現在地.md"
    if status_path.is_file():
        status = read_text(status_path)
        for row in close_gate.table_rows(close_gate.section(status, "## サマリ")):
            if len(row) > 1 and row[0] == "主対象依頼" and request_id in ID_PATTERNS["request"].findall(row[1]):
                add(findings, "error", f"終了依頼が主対象依頼に残っています: {request_id}")
        for heading in STATUS_HEADINGS[1:]:
            position = 1 if heading == "## 次アクション" else 0
            for row in close_gate.table_rows(close_gate.section(status, heading)):
                if len(row) > position and ({request_id} | archived_work_ids).intersection(
                        ID_PATTERNS["request"].findall(row[position]) + ID_PATTERNS["work"].findall(row[position])):
                    add(findings, "error", f"終了対象が現在地に残っています: {request_id}: {heading}")
    intake = root / "01_IN_入力/依頼受付.md"
    if intake.is_file() and read_frontmatter(intake).get("registered_request_id") == request_id:
        add(findings, "error", f"終了依頼の受付フォームが初期化されていません: {request_id}")
    request_index = root / "02_CT_管理/依頼一覧.md"
    rows = close_gate.table_rows(read_text(request_index)) if request_index.is_file() else []
    rows = [row for row in rows if row and row[0] == request_id]
    if len(rows) != 1 or len(rows[0]) < 9 or rows[0][3] != "archived" or not DATE_PATTERN.fullmatch(rows[0][7]):
        add(findings, "error", f"依頼一覧の終了索引が不足しています: {request_id}")
    elif not any(row[1] == rows[0][8] and row[2] == "request" for row in mappings):
        add(findings, "error", f"依頼一覧のアーカイブ参照が一致しません: {request_id}")
    request_files = [path for path in close_gate.request_documents(request_dir, f"{request_id}_*.md") if "_進行計画" not in path.stem and not path.stem.endswith("_WBS")]
    if len(request_files) == 1:
        expected_path = nfc(request_files[0].relative_to(root).as_posix())
        if expected_path not in mapped_destinations or (len(rows) == 1 and len(rows[0]) >= 9 and rows[0][8] != expected_path):
            add(findings, "error", f"依頼本文の移動対応が一致しません: {request_id}")
        metadata = read_frontmatter(request_files[0])
        if metadata.get("request_status") != "archived":
            add(findings, "error", f"アーカイブ依頼本文の終了状態が一致しません: {request_id}")
    history_path = root / "02_CT_管理/更新履歴.md"
    history_rows = close_gate.table_rows(read_text(history_path)) if history_path.is_file() else []
    summary_relative = nfc(summary.relative_to(root).as_posix())
    history_relative = nfc((records / "更新履歴.md").relative_to(root).as_posix())
    if not any(len(row) >= 7 and request_id in ID_PATTERNS["request"].findall(row[2])
               and summary_relative in row[6] and history_relative in row[6] for row in history_rows):
        add(findings, "error", f"更新履歴の終了索引がありません: {request_id}")


def check_archives(root: Path, findings: list[Finding]) -> None:
    for request_dir in (root / "99_AX_アーカイブ/依頼").glob("RQ-*"):
        if not request_dir.is_dir():
            add(findings, "error", f"アーカイブ依頼はフォルダである必要があります: {request_dir.relative_to(root)}")
            continue
        check_request_archive(root, request_dir, findings)


def check_request_archive(root: Path, request_dir: Path, findings: list[Finding]) -> None:
    request_id_match = ID_PATTERNS["request"].search(request_dir.name)
    request_id = request_id_match.group(0) if request_id_match else "RQ不明"
    request_files = close_gate.request_documents(request_dir, f"{request_id}_*.md")
    request_files = [path for path in request_files if "_進行計画" not in path.stem and not path.stem.endswith("_WBS")]
    if len(request_files) != 1:
        add(findings, "error", f"依頼MDは1件必要です: {request_dir.relative_to(root)}")
    elif (metadata := read_frontmatter(request_files[0])) and metadata.get("planning_status") in {"approved", "needs_revision"}:
        plan_files = list(request_dir.glob(f"{request_id}_進行計画.md"))
        if len(plan_files) != 1:
            add(findings, "error", f"計画済み依頼の進行計画MDは1件必要です: {request_dir.relative_to(root)}")
        else:
            plan_relative = nfc(plan_files[0].relative_to(root).as_posix())
            if metadata.get("plan_file") != plan_relative:
                add(findings, "error", f"アーカイブ依頼のplan_fileが移動先と一致しません: {request_id}")
            plan_meta = read_frontmatter(plan_files[0])
            if plan_meta.get("plan_format") == "split":
                wbs_relative = nfc((request_dir / f"{request_id}_WBS.md").relative_to(root).as_posix())
                if not (root / wbs_relative).is_file() or plan_meta.get("wbs_file") != wbs_relative:
                    add(findings, "error", f"アーカイブ進行計画のwbs_fileが移動先と一致しません: {request_id}")
    if not (request_dir / "終了サマリ.md").is_file():
        add(findings, "error", f"終了サマリ.mdがありません: {request_dir.relative_to(root)}")
    else:
        check_request_closure(request_dir / "終了サマリ.md", request_id, findings)
        check_request_archive_cleanup(root, request_dir, request_id, findings)
    work_root = request_dir / "work"
    if not work_root.is_dir():
        add(findings, "error", f"workフォルダがありません: {request_dir.relative_to(root)}")
        return
    for work_dir in work_root.glob("W-*"):
        if not work_dir.is_dir():
            add(findings, "error", f"アーカイブWorkはフォルダである必要があります: {work_dir.relative_to(root)}")
            continue
        for required in ("作業内容.md", "作業メモ.md", "反映候補.md", "入力/入力一覧.md"):
            if not (work_dir / required).is_file():
                add(findings, "error", f"{required}がありません: {work_dir.relative_to(root)}")
        check_work_record(work_dir, root, findings)


def check_context_index(root: Path, findings: list[Finding]) -> None:
    index_path = root / "03_CX_コンテキスト/Context一覧.md"
    if not index_path.is_file():
        return
    index_text = read_text(index_path)
    indexed_rows: dict[str, list[str]] = {}
    for line in index_text.splitlines():
        match = re.match(r"^\|\s*(CTX-\d{4})\s*\|", line)
        if not match:
            continue
        item_id = match.group(1)
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        indexed_rows.setdefault(item_id, []).append(line)
        if len(cells) > 4 and cells[4] not in {"confirmed", "assumption", "unknown", "conflict", "", "TBD"}:
            add(findings, "error", f"Context一覧のknowledge値が不正です: {item_id}")
        if len(cells) > 6 and cells[6] not in {"active", "scheduled", "suspended", "", "TBD"}:
            add(findings, "error", f"Context一覧のlifecycle値が不正です: {item_id}")
        if len(cells) > 7 and cells[7] not in {"true", "false", "", "TBD"}:
            add(findings, "error", f"Context一覧のblocking値が不正です: {item_id}")
        if len(cells) > 9 and cells[9] not in {"", "TBD"}:
            target = root / "03_CX_コンテキスト" / cells[9]
            if not target.is_file():
                add(findings, "error", f"Context一覧の配置先に実体がありません: {item_id} -> {cells[9]}")
    for item_id, lines in sorted(indexed_rows.items()):
        if len(lines) > 1:
            add(findings, "error", f"Context一覧で{item_id}が重複しています")

    context_files = context_paths(root)
    project_context = project_identity_path(root)
    split_paths = [root / "03_CX_コンテキスト" / name for name in sorted(CONTEXT_SPLIT_FILES)]
    existing_split_paths = [path for path in split_paths if path.is_file()]
    if not project_context.is_file():
        add(findings, "error", "Contextの入口であるプロジェクトコンテキスト.mdがありません")
    main_sections = context_sections(read_text(project_context)) if project_context.is_file() else {}

    embodied_occurrences: dict[str, list[str]] = {}
    for path in context_files:
        relative = nfc(path.relative_to(root).as_posix())
        metadata = read_frontmatter(path)
        filename = unicodedata.normalize("NFC", path.name)
        if filename not in set(CONTEXT_SPLIT_FILES) | {"プロジェクトコンテキスト.md"}:
            add(findings, "error", f"Context正本の配置先が固定規則にありません: {relative}")
        if not metadata:
            add(findings, "error", f"Context正本のfrontmatterがありません: {relative}")
        if metadata:
            if metadata.get("workflow_schema") != SCHEMA_VERSION:
                add(findings, "error", f"CXのworkflow_schemaは{SCHEMA_VERSION}である必要があります: {relative}")
            if metadata.get("document_type") != "project_context":
                add(findings, "error", f"CXのdocument_typeはproject_contextである必要があります: {relative}")
            expected_layout = "split" if existing_split_paths else "single"
            if metadata.get("context_layout") != expected_layout:
                add(findings, "error", f"CXのcontext_layoutは{expected_layout}である必要があります: {relative}")
            identity = project_identity(root)
            if not is_placeholder(identity.get("project_id")) and metadata.get("project_id") != identity["project_id"]:
                add(findings, "error", f"CXのproject_idが案件と一致しません: {relative}")
        try:
            text = read_text(path)
        except OSError:
            continue
        for item_id, item_text in context_items(text):
            embodied_occurrences.setdefault(item_id, []).append(relative)
        sections = context_sections(text)
        if filename == "プロジェクトコンテキスト.md":
            for heading in CONTEXT_SINGLE_HEADINGS:
                if heading not in sections:
                    add(findings, "error", f"プロジェクトコンテキスト.mdに固定セクションがありません: {heading}")
            headings = re.findall(r"^## [^\r\n]+", context_structure(text), re.MULTILINE)
            if headings != list(CONTEXT_SINGLE_HEADINGS):
                add(findings, "error", "プロジェクトコンテキスト.mdの20セクションの順序・重複・見出しを確認してください")
            if context_body_length(text) > CONTEXT_MAIN_LIMIT or any(context_body_length(body) > CONTEXT_SECTION_LIMIT for body in sections.values()):
                add(findings, "error", "プロジェクトコンテキスト.mdが自動分割閾値を超えています。syncloop-flow-syncで分割してください")
            for name, heading in CONTEXT_SPLIT_FILES.items():
                links = context_detail_links(sections.get(heading, ""))
                if name in links and not (path.parent / name).is_file():
                    add(findings, "error", f"Contextの詳細リンク先がありません: {name}")
        elif filename in CONTEXT_SPLIT_FILES:
            heading = CONTEXT_SPLIT_FILES[filename]
            if re.findall(r"^## [^\r\n]+", context_structure(text), re.MULTILINE) != [heading]:
                add(findings, "error", f"分離Contextのセクションが配置先と一致しません: {relative}")
            if metadata.get("context_section") != filename[:2]:
                add(findings, "error", f"分離Contextのcontext_sectionが配置先と一致しません: {relative}")
            links = context_detail_links(main_sections.get(heading, ""))
            if filename not in links:
                add(findings, "error", f"メインContextから分離Contextへの詳細リンクがありません: {relative}")
    for item_id, paths in sorted(embodied_occurrences.items()):
        if len(paths) > 1:
            add(findings, "error", f"Context正本で{item_id}が重複しています: {', '.join(paths)}")
    embodied_ids = set(embodied_occurrences)
    for item_id in sorted(set(indexed_rows) - embodied_ids):
        add(findings, "error", f"Context一覧に実体がありません: {item_id}")
    for item_id in sorted(embodied_ids - set(indexed_rows)):
        add(findings, "error", f"Context一覧に登録されていません: {item_id}")


def check_approval_record(path: Path, scope: str, root: Path, findings: list[Finding], request_id: str,
                          work_id: str = "", required_kinds: set[str] | None = None) -> dict[str, dict]:
    """承認記録（依頼・計画・Work）の書式と承認の中身を検査する（テーマC）。"""
    relative = nfc(path.relative_to(root).as_posix())
    if not path.is_file():
        if required_kinds:
            add(findings, "error", f"承認記録がありません: {relative}")
        return {}
    metadata = read_frontmatter(path)
    expected = [("workflow_schema", SCHEMA_VERSION), ("document_type", "approval_record"),
                ("approval_scope", scope), ("request_id", request_id)] + ([("work_id", work_id)] if work_id else [])
    for key, value in expected:
        if metadata.get(key) != value:
            add(findings, "error", f"承認記録の{key}が一致しません: {relative}")
    for field in ("updated_at", "updated_by"):
        if is_placeholder(metadata.get(field)):
            add(findings, "error", f"承認記録frontmatterの{field}が未設定です: {relative}")
    text = read_text(path)
    if "## 承認の記録" not in text:
        add(findings, "error", f"承認記録に必須見出しがありません: ## 承認の記録: {relative}")
    entries: dict[str, dict] = {}
    for entry in close_gate.approval_entries(text):
        if entry["id"] in entries:
            add(findings, "error", f"承認記録の見出しIDが重複しています: {relative}#{entry['id']}")
        entries[entry["id"]] = entry
        for problem in close_gate.approval_problems(entry, scope):
            add(findings, "error", f"承認記録の{entry['id']}: {problem}: {relative}")
        if entry["fields"].get("状態") == "提示中":
            add(findings, "warning", f"提示中のままの承認案があります（正本は未変更。承認か差し戻しを記録してください）: {relative}#{entry['id']}")
    if required_kinds and not any(entry["kind"] in required_kinds and entry["fields"].get("状態") == "承認済み"
                                  for entry in entries.values()):
        add(findings, "error", f"承認記録に承認済みの{'・'.join(sorted(required_kinds))}がありません: {relative}")
    return entries


def check_plan_revision_approvals(plan_path: Path, entries: dict[str, dict], root: Path,
                                  findings: list[Finding]) -> None:
    """進行計画の改訂履歴の承認記録欄が、計画承認記録の承認済みの見出しを指しているかを見る。"""
    rows = close_gate.table_rows(section_text(read_text(plan_path), "## 改訂履歴"))
    if not rows or "承認記録" not in rows[0]:
        return  # 旧書式（承認者欄）は読み取りだけ
    relative = nfc(plan_path.relative_to(root).as_posix())
    for row in rows[1:]:
        if len(row) != 6:
            add(findings, "error", f"進行計画の改訂履歴の列数が不正です: {relative}: {row[0]}")
            continue
        kind, ref = row[2], row[5]
        if kind not in {"Plan承認", "区切り承認"}:
            continue
        entry = entries.get(ref)
        if not entry or entry["kind"] != kind or entry["fields"].get("状態") != "承認済み":
            add(findings, "error", f"進行計画の改訂{row[0]}の承認記録が計画承認記録の承認済み{kind}と一致しません: {ref}")


def approval_record_file(root: Path, owner: str, kind: str) -> Path | None:
    """承認記録への参照（RQ-xxxx_依頼承認記録 / RQ-xxxx_計画承認記録 / W-xxxx_承認記録）を実ファイルに解決する。"""
    if owner.startswith("RQ-"):
        name = f"{owner}_{kind}{close_gate.APPROVAL_SUFFIX}.md"
        folder = "依頼" if kind == "依頼" else "進行計画"
        candidates = [root / "02_CT_管理" / folder / name] + list((root / "99_AX_アーカイブ/依頼").glob(f"{owner}_*/{name}"))
    else:
        candidates = [work / "承認記録.md" for work in current_work_dirs(root) if work.name.startswith(owner + "_")]
        candidates += [work / "承認記録.md" for work in (root / "99_AX_アーカイブ/依頼").glob(f"RQ-*/work/{owner}_*")]
    return next((path for path in candidates if path.is_file()), None)


def check_approval_references(root: Path, findings: list[Finding]) -> None:
    history = root / "02_CT_管理/更新履歴.md"
    if not history.is_file():
        return
    pattern = re.compile(r"(RQ-\d{4}|W-\d{4})_(依頼|計画)?" + close_gate.APPROVAL_SUFFIX + r"(?:\.md)?#(A-\d{2})")
    for match in pattern.finditer(read_text(history)):
        owner, kind, approval_id = match.group(1), match.group(2) or "", match.group(3)
        if owner.startswith("RQ-") == (not kind):
            add(findings, "error", f"更新履歴の承認記録参照の書式が不正です: {match.group(0)}")
            continue
        path = approval_record_file(root, owner, kind)
        if not path:
            add(findings, "error", f"更新履歴が参照する承認記録がありません: {match.group(0)}")
        elif approval_id not in {entry["id"] for entry in close_gate.approval_entries(read_text(path))}:
            add(findings, "error", f"更新履歴が参照する承認記録の見出しがありません: {match.group(0)}")


def check_project(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    check_structure(root, findings)
    check_document_contracts(root, findings)
    check_duplicate_ids(root, findings)
    check_indexes(root, findings)
    check_input_materials(root, findings)
    check_knowledge(root, findings)
    check_context_index(root, findings)
    check_context_records(root, findings)
    check_initialized_project(root, findings)
    check_archives(root, findings)
    check_approval_references(root, findings)
    return findings


def verify_request_close(root: Path, request_id: str) -> list[Finding]:
    """対象依頼のアーカイブ・終了サマリ・関連Workだけを検査する（cleanup_statusの完了判定用）。"""
    findings: list[Finding] = []
    request_dirs = [path for path in (root / "99_AX_アーカイブ/依頼").glob(f"{request_id}_*") if path.is_dir()]
    if len(request_dirs) != 1:
        add(findings, "error", f"対象依頼のアーカイブフォルダは1件必要です: {request_id}")
        return findings
    check_request_archive(root, request_dirs[0], findings)
    return [item for item in findings if item.level == "error"]


def next_action(findings: list[Finding]) -> str:
    if any(finding.level == "error" for finding in findings):
        return "構造または台帳のエラーを解消してから状態遷移を行ってください。"
    if any(finding.level == "warning" for finding in findings):
        return "旧構成の残存などの注意を確認してください。"
    return "共通構造と主要な参照関係に問題はありません。"


def print_result(root: Path, findings: list[Finding]) -> None:
    errors = [finding for finding in findings if finding.level == "error"]
    warnings = [finding for finding in findings if finding.level == "warning"]
    print("Syncloop Flow check")
    print(f"対象: {root}")
    print(f"エラー: {len(errors)}件")
    for finding in errors:
        print(f"- {finding.message}")
    print(f"注意: {len(warnings)}件")
    for finding in warnings:
        print(f"- {finding.message}")
    print(f"次にすること: {next_action(findings)}")


def main() -> int:
    # Windowsのパイプ出力（cp932等）で表現できない文字があっても検査結果を出し切る。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("check", "verify-close", "seal-close", "version-table", "verify-request-close", "gantt"),
                        default="check")
    parser.add_argument("--root", default=".", help="案件ワークスペースのルート")
    parser.add_argument("--strict", action="store_true", help="エラーがあれば終了コード1を返す")
    parser.add_argument("--work", help="対象Workのルート相対パス")
    parser.add_argument("--request", help="verify-request-close: 対象依頼のRQ-ID")
    parser.add_argument("--wbs", help="gantt: 対象WBSのルート相対パス")
    parser.add_argument("--write", action="store_true", help="gantt: WBSの生成区間を書き換える")
    parser.add_argument("--phase", choices=("before", "resume", "after"), default="before")
    parser.add_argument("--target", action="append", default=[], metavar="参照=work:終了反映案/…",
                        help="version-table: 変更する正本と承認用内容（複数指定可）")
    parser.add_argument("--delete", action="append", default=[], metavar="参照",
                        help="version-table: 削除する正本（複数指定可）")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "gantt":
        if not args.wbs:
            parser.error("--wbs が必要です")
        wbs_path = (root / args.wbs).resolve()
        if not wbs_path.is_relative_to(root) or not wbs_path.is_file():
            parser.error(f"WBSが見つかりません: {args.wbs}")
        text = read_text(wbs_path)
        if close_gate.gantt_block(text) is None:
            print("WBSにガントの生成区間（<!-- gantt:start --> と <!-- gantt:end -->）がありません")
            return 1
        if args.write:
            wbs_path.write_text(close_gate.with_gantt(text, close_gate.wbs_title(text)), encoding="utf-8")
            print(f"ガントを更新しました: {args.wbs}")
        else:
            print("\n".join(close_gate.render_gantt(text, close_gate.wbs_title(text))))
        return 0
    if args.command == "verify-request-close":
        if not args.request or not ID_PATTERNS["request"].fullmatch(args.request):
            parser.error("--request RQ-xxxx が必要です")
        errors = verify_request_close(root, args.request)
        for finding in errors:
            print(finding.message)
        if not errors:
            print(f"依頼終了の保存・整理に問題はありません: {args.request}")
        return 1 if errors else 0
    if args.command != "check":
        if not args.work:
            parser.error("--workが必要です")
        try:
            work = close_gate.resolve_ref(root, root, args.work)
        except ValueError as exc:
            parser.error(str(exc))
        if args.command == "version-table":
            targets = {}
            for item in args.target:
                ref, sep, content = item.partition("=")
                if not sep or not ref or not content:
                    parser.error(f"--targetは 参照=work:終了反映案/… の形式で指定してください: {item}")
                targets[ref] = content
            lines, errors = close_gate.version_table(work, root, targets, set(args.delete))
            print("\n".join(lines))
            for error in errors:
                print(f"要対応: {error}")
            return 1 if errors else 0
        errors = close_gate.seal(work, root) if args.command == "seal-close" else close_gate.validate(work, root, args.phase)
        for error in errors:
            print(error)
        if not errors:
            print("承認封印を保存しました" if args.command == "seal-close" else "終了判断と承認対象の版が一致しています")
        return 1 if errors else 0
    findings = check_project(root)
    print_result(root, findings)
    return 1 if args.strict and any(item.level == "error" for item in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
