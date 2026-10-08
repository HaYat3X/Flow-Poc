"""保存済みClose判断の承認、版、次アクションを検証する（封印作成以外は読取専用）。"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

SCHEMA = "3"
VOLATILE_FIELDS = {"decision_status", "synced_at", "updated_at", "updated_by"}
FINAL_STATES = {"completed", "cancelled", "on_hold", "handoff"}
NEXT_ACTIONS = {"continue_work", "plan_remaining", "replan", "request_close", "resolve_blocker"}
HEADINGS = ("## 完了条件の判定", "## 候補の処理", "## 残件の行き先", "## 依頼全体と次アクション", "## 承認対象の版")
HASH = re.compile(r"[0-9a-f]{64}")
CANDIDATE = re.compile(r"C-(?:CTX|DEC|RSK|ISS|KNW|PRD)-\d{3}")
REQUIRED_WORK_REFS = ("work:作業内容.md", "work:入力/入力一覧.md", "work:作業メモ.md", "work:反映候補.md",
                      "work:入力/Work入力.md", "work:引継ぎ.md")
CLOSE_TARGET_WORK_REFS = REQUIRED_WORK_REFS[:4]
CLOSE_TARGET_LEDGERS = tuple("02_CT_管理/" + name for name in ("Work一覧.md", "現在地.md", "更新履歴.md"))
# 契約の「関係する索引」。版表に載らないファイルはSyncが書き換えても検出できないため、存在すれば監視対象にする。
INDEX_REFS = (
    "02_CT_管理/依頼一覧.md",
    "01_IN_入力/入力資料一覧.md",
    "03_CX_コンテキスト/Context一覧.md",
    "03_CX_コンテキスト/トレーサビリティ.md",
    "06_PD_プロダクト/リポジトリ情報.md",
    "07_KN_ナレッジ/ナレッジ一覧.md",
)


def nfc(value: str) -> str:
    """比較用にUnicodeをNFCへ揃える。macOSはファイル名をNFD（濁点の分解形）で返すことがある。"""
    return unicodedata.normalize("NFC", value)


def read_text(path: Path) -> str:
    """OSの既定文字コードに依存せずUTF-8で読み、比較用にNFCへ揃える。"""
    return nfc(path.read_text(encoding="utf-8"))


def path_key(path: Path) -> tuple:
    """同じファイルを指す参照を、NFC/NFD・大文字小文字・シンボリックリンクの差なく同一視する。"""
    try:
        stat = path.stat()
        return ("file", stat.st_dev, stat.st_ino)
    except OSError:
        return ("path", nfc(str(path.resolve())))


def metadata(path: Path) -> dict[str, str]:
    lines = read_text(path).splitlines()
    if not lines or lines[0] != "---":
        return {}
    result = {}
    for line in lines[1:]:
        if line == "---":
            break
        match = re.fullmatch(r"([a-zA-Z][a-zA-Z0-9_]*):\s*(.*)", line)
        if match:
            result[match[1]] = match[2].strip().strip('"\'')
    return result


def section(text: str, heading: str) -> str:
    marker = heading + "\n"
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].split("\n## ", 1)[0]


def table_rows(text: str) -> list[list[str]]:
    return [[c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            for line in text.splitlines() if line.startswith("|") and not re.match(r"^\|\s*:?-+", line)]



# --- WBSと進行計画（plan_format: split）-------------------------------------------
WBS_HEADING = "## 作業パッケージ"
WBS_MILESTONE_HEADING = "## マイルストーン・判断ゲート"
PLAN_WORK_HEADING = "## 今回始めるWork"
WBS_STATES = {"未着手", "進行中", "保留", "完了", "中止"}
PLAN_WORK_STATES = {"未着手", "開始済み", "完了", "中止"}
DATE_CONFIDENCE = {"確定", "仮"}
GANTT_START = "<!-- gantt:start -->"
GANTT_END = "<!-- gantt:end -->"
PLAN_ID = re.compile(r"P-\d{3}")


def wbs_rows(text: str) -> list[list[str]]:
    """作業パッケージ表の行（11列）。列: ID, 親, 名前, 成果物, 完了条件, 開始, 終了, 先行, 確度, 状態, 紐づくWork。"""
    return [r for r in table_rows(section(text, WBS_HEADING)) if r and PLAN_ID.fullmatch(r[0])]


def wbs_milestones(text: str) -> list[list[str]]:
    """マイルストーン表の行。列: 節目, 予定日, 確度, 到達条件, 判断者, 関連ID。"""
    return [r for r in table_rows(section(text, WBS_MILESTONE_HEADING)) if r and r[0] != "節目"]


def plan_work_rows(text: str) -> list[list[str]]:
    """進行計画の今回始めるWork（9列）。列: 順番, Work, 計画項目ID, 担当, 予定, 開始条件, 完了条件, 状態, Work ID。"""
    return [r for r in table_rows(section(text, PLAN_WORK_HEADING)) if r and r[0] != "順番"]


# 承認記録（テーマC）: 承認の対象ごとに、示した判断点と同意を1件1見出しで残す。
APPROVAL_SUFFIX = "承認記録"
APPROVAL_KINDS = {
    "request": {"登録承認", "改訂承認", "前提承認"},
    "plan": {"Plan承認", "区切り承認", "前提承認"},
    "work": {"開始承認", "変更承認", "途中Sync承認", "前提承認"},
}
APPROVAL_STATES = {"提示中", "承認済み", "差し戻し"}


def is_approval_record(path: Path) -> bool:
    return path.stem.endswith(APPROVAL_SUFFIX)


def request_documents(folder: Path, pattern: str) -> list[Path]:
    """依頼・進行計画フォルダの文書から承認記録を除いて列挙する。"""
    return sorted(path for path in folder.glob(pattern) if not is_approval_record(path))


def approval_record_paths(root: Path, request_id: str) -> dict[str, Path]:
    return {
        "request": root / "02_CT_管理/依頼" / f"{request_id}_依頼{APPROVAL_SUFFIX}.md",
        "plan": root / "02_CT_管理/進行計画" / f"{request_id}_計画{APPROVAL_SUFFIX}.md",
    }


def approval_entries(text: str) -> list[dict]:
    """「## 承認の記録」の見出しごとに、種別・項目・判断点を読む。"""
    body = section(text, "## 承認の記録")
    entries: list[dict] = []
    for match in re.finditer(r"^### (A-\d{2})[ \t]+([^\s（(]+)(.*)$((?:\n(?!### ).*)*)", body, re.MULTILINE):
        fields: dict[str, str] = {}
        points: list[str] = []
        current = ""
        for line in match.group(4).splitlines():
            top = re.match(r"^- ([^:：]+)[:：]\s*(.*)$", line)
            child = re.match(r"^\s{2,}- (.+)$", line)
            if top:
                current = top.group(1).strip()
                fields[current] = top.group(2).strip()
            elif child and current == "判断が要る点":
                points.append(child.group(1).strip())
        entries.append({"id": match.group(1), "kind": match.group(2), "title": match.group(2) + match.group(3),
                        "fields": fields, "points": points})
    return entries


def approval_problems(entry: dict, scope: str) -> list[str]:
    """承認記録の1件について、記載の不足を返す。"""
    problems: list[str] = []
    fields = entry["fields"]
    state = fields.get("状態", "")
    if entry["kind"] not in APPROVAL_KINDS[scope]:
        problems.append(f"承認の種別が不正です（{'/'.join(sorted(APPROVAL_KINDS[scope]))}）")
    if state not in APPROVAL_STATES:
        problems.append("状態は提示中・承認済み・差し戻しのいずれかにしてください")
    if not re.match(r"\d{4}-\d{2}-\d{2}", fields.get("提示", "")):
        problems.append("提示の日時がありません")
    points = [p for p in entry["points"] if p != "示した判断点を1行ずつ書く"]
    if not points:
        problems.append("判断が要る点がありません")
    approval = fields.get("承認", "")
    if state == "承認済み":
        if not re.match(r"\d{4}-\d{2}-\d{2}", approval) or "記録の承認" not in approval:
            problems.append("承認済みには承認の日時・承認者と立場（記録の承認）が必要です")
        if fields.get("承認の発言", "未") in {"", "未", "「承認の発言を引用する」"}:
            problems.append("承認済みには承認の発言が必要です")
        if any(p.startswith("案件の判断") for p in points) and "案件の判断" not in approval:
            problems.append("案件の判断を含む承認では、承認者が案件の判断も承認したことを記録してください")
    if state == "差し戻し" and not fields.get("差し戻しの理由"):
        problems.append("差し戻しには差し戻しの理由が必要です")
    return problems


def split_ids(value: str) -> list[str]:
    return [] if value.strip() in {"", "なし", "none"} else [v.strip() for v in value.split(",") if v.strip()]


def render_gantt(text: str, title: str) -> list[str]:
    """作業パッケージ表とマイルストーン表から、毎回同じMermaidガントを生成する。日付が未定の行は図に載せない。"""
    rows = wbs_rows(text)
    by_id = {r[0]: r for r in rows if len(r) == 11}

    def top(row_id: str) -> str:
        seen = set()
        while by_id.get(row_id) and by_id[row_id][1] in by_id and row_id not in seen:
            seen.add(row_id)
            row_id = by_id[row_id][1]
        return row_id

    lines = ["```mermaid", "gantt", f"    title {title}", "    dateFormat YYYY-MM-DD",
             "    axisFormat %m/%d", "    todayMarker off"]
    sections: list[str] = []
    for row in by_id.values():
        root_id = top(row[0])
        if root_id not in sections:
            sections.append(root_id)
    for root_id in sections:
        lines.append("")
        lines.append(f"    section {root_id} {by_id[root_id][2]}")
        for row in by_id.values():
            if top(row[0]) != root_id or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[5]) \
                    or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[6]):
                continue
            label = f"{row[0]} {row[2]}" + ("（仮）" if row[8] == "仮" else "")
            tag = {"完了": "done, ", "進行中": "active, "}.get(row[9], "")
            span = "1d" if row[5] == row[6] else row[6]
            lines.append(f"    {label.replace(':', '：')} :{tag}{row[0].lower().replace('-', '')}, {row[5]}, {span}")
    undated = [r[0] for r in by_id.values() if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[5])
                                                    and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[6]))]
    if undated:
        lines.append("")
        lines.append(f"    %% 日付未定のため図に載せていない計画項目: {', '.join(undated)}")
    milestones = [m for m in wbs_milestones(text) if len(m) >= 3 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", m[1])]
    if milestones:
        lines.append("")
        lines.append("    section 判断ゲート")
        for index, row in enumerate(milestones, 1):
            label = row[0] + ("（仮）" if row[2] == "仮" else "")
            lines.append(f"    {label.replace(':', '：')} :milestone, m{index:02d}, {row[1]}, 0d")
    lines.append("```")
    return lines


def gantt_block(text: str) -> str | None:
    if GANTT_START not in text or GANTT_END not in text:
        return None
    return text.split(GANTT_START, 1)[1].split(GANTT_END, 1)[0].strip("\n")


def with_gantt(text: str, title: str) -> str:
    body = "\n".join(render_gantt(text, title))
    head, rest = text.split(GANTT_START, 1)
    return f"{head}{GANTT_START}\n{body}\n{GANTT_END}{rest.split(GANTT_END, 1)[1]}"


def wbs_title(text: str) -> str:
    match = re.search(r"^# (.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else "WBS"


def split_plan_summary(plan_text: str, wbs_text: str, work_id: str) -> dict:
    """終了判断の照合に使う、区切りの残りWork数・今回Workの行・未計画範囲の有無。"""
    rows = [r for r in plan_work_rows(plan_text) if len(r) == 9]
    remaining = [r for r in rows if r[7] in {"未着手", "開始済み"} and r[8] != work_id]
    current = [r for r in rows if r[8] == work_id]
    covered = {r[2] for r in remaining} | {r[2] for r in current if r[7] == "開始済み"}
    packages = [r for r in wbs_rows(wbs_text) if len(r) == 11]
    parents = {r[1] for r in packages}
    open_leaves = [r for r in packages if r[0] not in parents and r[9] not in {"完了", "中止"} and r[0] not in covered]
    return {"remaining": remaining, "current": current, "unplanned": bool(open_leaves)}

def next_action(request_completion: str, remaining_planned_work: int, unplanned_remaining: bool,
                plan_changed: bool = False, continuation_blocked: bool = False) -> str:
    """Closeが確定した事実から案内を選ぶ。Syncは保存済み案内との一致だけを検査する。"""
    if continuation_blocked or request_completion == "unknown":
        return "resolve_blocker"
    if request_completion == "satisfied":
        return "resolve_blocker" if remaining_planned_work or unplanned_remaining else "request_close"
    if plan_changed:
        return "replan"
    if remaining_planned_work:
        return "continue_work"
    return "plan_remaining"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


def approved_digest(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    in_frontmatter = False
    approved_lines = []
    for i, line in enumerate(lines):
        if line == "---" and (i == 0 or in_frontmatter):
            in_frontmatter = not in_frontmatter
        key = line.split(":", 1)[0] if in_frontmatter else ""
        if key not in VOLATILE_FIELDS:
            approved_lines.append(line)
    return hashlib.sha256(("\n".join(approved_lines) + "\n").encode()).hexdigest()


def resolve_ref(root: Path, work: Path, ref: str) -> Path:
    local = ref.startswith("work:")
    value = ref[5:] if local else ref
    relative = Path(value)
    if not value or relative.is_absolute() or ".." in relative.parts or ":" in value:
        raise ValueError(f"不正な版参照: {ref}")
    base = work.resolve() if local else root.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"版参照が対象外を指しています: {ref}")
    return path


class _SplitDone(Exception):
    """分離形式の計画の照合を終えたことを示す（旧形式の照合を飛ばす）。"""


def validate_split_plan(root: Path, work: Path, refs: dict, plan_path: Path, plan_text: str, data: dict,
                        final: str, remaining: str, work_id: str) -> list[str]:
    """WBSと進行計画を分けた計画（plan_format: split）で、終了判断の数値・次アクションを照合する。"""
    errors: list[str] = []
    wbs_ref = nfc(metadata(plan_path).get("wbs_file", "none"))
    if wbs_ref in {"", "none"}:
        return ["分離形式の進行計画にwbs_fileがありません"]
    if wbs_ref not in refs:
        return ["承認対象の版に関連WBSがありません"]
    row = refs[wbs_ref]
    if row[3] == "missing":
        return ["終了同期で関連WBSを削除できません"]
    wbs_path = resolve_ref(root, work, row[4] if row[0] == "target" else wbs_ref)
    if not wbs_path.is_file():
        return ["承認用WBSがありません"]
    summary = split_plan_summary(plan_text, read_text(wbs_path), work_id)
    if remaining.isdigit() and int(remaining) != len(summary["remaining"]):
        errors.append("終了判断の残りWork数が承認用進行計画と一致しません")
    if (data.get("unplanned_remaining") == "true") != summary["unplanned"]:
        errors.append("終了判断の未計画範囲が承認用WBS・進行計画と一致しません")
    expected = {"completed": "完了", "cancelled": "中止"}.get(final, "開始済み")
    if len(summary["current"]) != 1 or summary["current"][0][7] != expected:
        errors.append("今回Workの行の状態が承認用進行計画と一致しません")
    if data.get("next_action") == "continue_work":
        target = data.get("next_target", "")
        if not any(r[2] in target or (r[8] not in {"未発行", ""} and r[8] in target) for r in summary["remaining"]):
            errors.append("次の対象が進行計画の未完了の行にありません")
    if data.get("next_action") == "replan" and metadata(plan_path).get("planning_status") != "needs_revision":
        errors.append("再計画の承認用計画がneeds_revisionではありません")
    return errors


def validate(work: Path, root: Path, phase: str | None = None, require_seal: bool = True) -> list[str]:
    errors: list[str] = []
    path = work / "終了判断.md"
    if not path.is_file():
        return ["終了判断.mdがありません"] if phase else []
    data = metadata(path)
    scope = metadata(work / "作業内容.md") if (work / "作業内容.md").is_file() else {}
    state = data.get("decision_status")
    if state not in {"draft", "approved", "applying", "synced", "invalidated"}:
        errors.append("終了判断のdecision_statusが不正です")
    if phase:
        expected = "approved" if phase == "before" else "applying"
        if state != expected:
            errors.append(f"{phase}検証には終了判断が{expected}である必要があります")
    if state in {"draft", "invalidated"} and not phase:
        return errors
    for key, expected in (("workflow_schema", SCHEMA), ("document_type", "work_close_decision"),
                          ("work_id", scope.get("work_id")), ("request_id", scope.get("request_id")),
                          ("project_id", scope.get("project_id"))):
        if not expected or data.get(key) != expected:
            errors.append(f"終了判断の{key}が対象Workと一致しません")
    if not re.fullmatch(re.escape(scope.get("work_id", "")) + r"-C\d{2,}", data.get("close_id", "")):
        errors.append("終了判断のclose_idが不正です")
    for key in ("approved_by", "approved_at", "next_target", "next_reason", "updated_by", "updated_at"):
        if data.get(key, "") in {"", "none", "TBD"}:
            errors.append(f"終了判断の{key}が未設定です")
    for key in ("approved_at", "updated_at"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:]+(?:Z|[+-][0-9:]+)?)?", data.get(key, "")):
            errors.append(f"終了判断の{key}形式が不正です")
    final = data.get("final_status")
    if final not in FINAL_STATES:
        errors.append("終了判断のfinal_statusが不正です")
    completion = data.get("request_completion")
    if completion not in {"satisfied", "unsatisfied", "unknown"}:
        errors.append("終了判断のrequest_completionが不正です")
    revision = data.get("plan_revision", "")
    if not revision.isdigit():
        errors.append("終了判断のplan_revisionが不正です")
    remaining = data.get("remaining_planned_work", "")
    if not remaining.isdigit():
        errors.append("終了判断のremaining_planned_workが不正です")
    flags = ("unplanned_remaining", "plan_changed", "continuation_blocked")
    for key in flags:
        if data.get(key) not in {"true", "false"}:
            errors.append(f"終了判断の{key}が不正です")
    if remaining.isdigit() and all(data.get(k) in {"true", "false"} for k in flags):
        expected_action = next_action(completion or "unknown", int(remaining), *(data[k] == "true" for k in flags))
        if data.get("next_action") != expected_action:
            errors.append(f"終了判断の次アクションは{expected_action}である必要があります")
    if data.get("next_action") not in NEXT_ACTIONS:
        errors.append("終了判断のnext_actionが不正です")
    if data.get("next_action") == "continue_work" and not re.search(r"(?:P-\d{3}|W-\d{4})", data.get("next_target", "")):
        errors.append("次のWorkまたは計画項目の対象IDがありません")
    text = path.read_text(encoding="utf-8")
    for heading in HEADINGS:
        if not section(text, heading).strip():
            errors.append(f"終了判断に内容がありません: {heading}")
    conditions = [r for r in table_rows(section(text, HEADINGS[0])) if len(r) == 4 and r[2] in {"satisfied", "unsatisfied", "not_applicable"}]
    if not conditions or any(not r[3] for r in conditions):
        errors.append("終了判断に根拠付きの完了条件判定がありません")
    if final == "completed" and any(r[2] == "unsatisfied" for r in conditions):
        errors.append("未達のWork完了条件がありcompletedにできません")
    disposition_rows = []
    candidates_path = work / "反映候補.md"
    if candidates_path.is_file():
        ctext = read_text(candidates_path).split("## 反映候補の処理履歴", 1)[0]
        ids = set(CANDIDATE.findall(ctext))
        disposition_rows = [r for r in table_rows(section(text, HEADINGS[1])) if r and CANDIDATE.fullmatch(r[0])]
        chosen = {r[0] for r in disposition_rows}
        if chosen != ids or len(chosen) != len(disposition_rows):
            errors.append("終了判断の候補処理と反映候補が一致しません")
        for row in disposition_rows:
            if len(row) < 4 or row[1] not in {"反映", "見送り", "保留", "残作業化"} or not row[2] or not row[3]:
                errors.append(f"終了判断の候補処理・行き先・根拠が不足しています: {row[0]}")
    if require_seal:
        seal = work / "終了判断承認.sha256"
        if not seal.is_file() or seal.read_text(encoding="utf-8").strip() != approved_digest(path):
            errors.append("終了判断の承認封印がないか承認内容が変更されています")
    handoff = work / "引継ぎ.md"
    if not handoff.is_file():
        errors.append("引継ぎ.mdがありません")
    elif metadata(handoff).get("close_id") != data.get("close_id"):
        errors.append("引継ぎのclose_idが終了判断と一致しません")
    version_rows = table_rows(section(text, HEADINGS[4]))
    for row in version_rows:
        if row and row[0] not in {"種別", "source", "target"}:
            errors.append(f"承認対象の版の種別が不正です: {row[0]}")
    rows = [r for r in version_rows if r and r[0] in {"source", "target"}]
    if not rows:
        errors.append("終了判断の承認対象の版がありません")
    refs: dict[str, list[str]] = {}
    resolved_paths: set[tuple] = set()
    # Ordinary checks don't compare historical Context against a synchronized old decision.
    compare_phase = phase or ("before" if state == "approved" else "resume" if state == "applying" else None)
    for row in rows:
        if len(row) != 5:
            errors.append("終了判断の版表の列数が不正です")
            continue
        kind, ref, before, after, content = row
        if nfc(ref) in refs:
            errors.append(f"終了判断の版参照が重複しています: {ref}")
        refs[nfc(ref)] = row
        if before != "missing" and not HASH.fullmatch(before):
            errors.append(f"適用前SHA256が不正です: {ref}")
        if after != "missing" and not HASH.fullmatch(after):
            errors.append(f"適用後SHA256が不正です: {ref}")
        if kind == "source" and (before == "missing" or before != after or content != "none"):
            errors.append(f"sourceの版指定が不正です: {ref}")
        if kind == "target" and before == after == "missing":
            errors.append(f"targetの前後がともにmissingです: {ref}")
        try:
            actual_path = resolve_ref(root, work, ref)
            if path_key(actual_path) in resolved_paths:
                errors.append(f"同じファイルを複数の版参照で登録しています: {ref}")
            resolved_paths.add(path_key(actual_path))
            if actual_path.exists() and not actual_path.is_file():
                errors.append(f"版参照はファイルを指定してください: {ref}")
            if compare_phase:
                allowed = {before} if compare_phase == "before" or kind == "source" else {after} if compare_phase == "after" else {before, after}
                if digest(actual_path) not in allowed:
                    errors.append(f"承認対象の版が変更されています: {ref}")
            if kind == "target":
                if after == "missing":
                    if content != "none":
                        errors.append(f"削除targetの適用後内容はnoneにします: {ref}")
                else:
                    staged = resolve_ref(root, work, content)
                    if not content.startswith("work:終了反映案/") or digest(staged) != after:
                        errors.append(f"承認した適用後内容がないか変更されています: {ref}")
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
    for ref in sorted(set(REQUIRED_WORK_REFS) - refs.keys()):
        errors.append(f"承認対象の版に必須Work記録がありません: {ref}")
    if compare_phase:
        for ref in CLOSE_TARGET_WORK_REFS:
            row = refs.get(ref)
            if not row or row[0] != "target":
                errors.append(f"終了同期のWork記録をtargetとして指定してください: {ref}")
            elif row[3] == "missing":
                errors.append(f"必須Work記録は終了同期で削除できません: {ref}")
            else:
                try:
                    staged = resolve_ref(root, work, row[4])
                    if staged.is_file() and metadata(staged).get("record_status") != final:
                        errors.append(f"承認用Work記録の終了状態が一致しません: {ref}")
                except ValueError as exc:
                    errors.append(str(exc))
    if compare_phase:
        # macOSでは日本語パスのUnicode表現が列挙結果と版表で異なるため、ファイルの実体で照合する。
        for context in (root / "03_CX_コンテキスト").glob("*.md"):
            if metadata(context).get("document_type") == "project_context" and path_key(context) not in resolved_paths:
                errors.append(f"承認対象の版に案件Contextがありません: {context.name}")
        requests = request_documents(root / "02_CT_管理/依頼", f"{scope.get('request_id', '')}_*.md")
        for approval in [*approval_record_paths(root, scope.get("request_id", "")).values(), work / "承認記録.md"]:
            if approval.is_file() and path_key(approval) not in resolved_paths:
                errors.append(f"承認対象の版に承認記録がありません: {approval.name}")
        work_approval = work / "承認記録.md"
        if work_approval.is_file():
            for entry in approval_entries(read_text(work_approval)):
                if entry["fields"].get("状態") == "提示中":
                    errors.append(f"Workの承認記録に提示中のままの承認があります: {entry['id']}")
        if len(requests) != 1:
            errors.append("終了判断の関連依頼を一意に特定できません")
        else:
            ref = nfc(requests[0].relative_to(root).as_posix())
            if ref not in refs:
                errors.append("承認対象の版に関連依頼がありません")
            if ref in refs and refs[ref][3] == "missing":
                errors.append("終了同期で関連依頼を削除できません")
            plan = nfc(metadata(requests[0]).get("plan_file", "none"))
            if plan != "none" and plan not in refs:
                errors.append("承認対象の版に関連計画がありません")
            elif plan in refs:
                row = refs[plan]
                if row[3] == "missing":
                    errors.append("終了同期で関連計画を削除できません")
                try:
                    effective = resolve_ref(root, work, row[4] if row[0] == "target" else plan)
                    if effective.is_file():
                        plan_text = read_text(effective)
                        if metadata(effective).get("plan_revision") != revision:
                            errors.append("終了判断の計画改訂番号が承認用計画と一致しません")
                        if metadata(effective).get("plan_format") == "split":
                            errors += validate_split_plan(root, work, refs, effective, plan_text, data, final,
                                                          remaining, scope.get("work_id", ""))
                            raise _SplitDone
                        planned = [r for r in table_rows(section(plan_text, "## Work候補"))
                                   if len(r) == 10 and re.fullmatch(r"P-\d{3}", r[0])]
                        remaining_count = sum(r[8] == "planned" and r[9] != scope.get("work_id") for r in planned)
                        if remaining.isdigit() and int(remaining) != remaining_count:
                            errors.append("終了判断の残りWork数が承認用計画と一致しません")
                        partial = metadata(effective).get("plan_coverage") == "partial"
                        if (data.get("unplanned_remaining") == "true") != partial:
                            errors.append("終了判断の未計画範囲が承認用計画と一致しません")
                        current = [r for r in planned if r[9] == scope.get("work_id")]
                        expected_consumption = "completed" if final == "completed" else "cancelled" if final == "cancelled" else "planned"
                        if len(current) != 1 or current[0][8] != expected_consumption:
                            errors.append("今回Workの消化状態が承認用計画と一致しません")
                        if data.get("next_action") == "continue_work":
                            target = data.get("next_target", "")
                            if not any(r[8] == "planned" and r[9] != scope.get("work_id") and (r[0] in target or (r[9] not in {"none", "なし", ""} and r[9] in target)) for r in planned):
                                errors.append("次の対象が未消化の計画済み候補にありません")
                        if data.get("next_action") == "replan" and metadata(effective).get("planning_status") != "needs_revision":
                            errors.append("再計画の承認用計画がneeds_revisionではありません")
                except _SplitDone:
                    pass
                except (ValueError, OSError) as exc:
                    errors.append(str(exc))
        for ref in CLOSE_TARGET_LEDGERS:
            if ref not in refs or refs[ref][0] != "target":
                errors.append(f"終了同期の適用対象に{ref}がありません")
        for ref in INDEX_REFS:
            if (root / ref).is_file() and ref not in refs:
                errors.append(f"承認対象の版に索引がありません（変更しない場合もsourceで登録）: {ref}")
        # Newly added inputs/results must invalidate approval, even if omitted from the old manifest.
        for source in list((work / "入力").rglob("*")) + list((work / "作業成果").rglob("*")):
            if source.is_file() and not source.name.startswith(".") and path_key(source) not in resolved_paths:
                errors.append(f"承認後に未登録の入力・成果があります: {source.relative_to(work)}")
    if state == "synced" or phase == "after":
        if phase == "after":
            expected_parent = root / "04_WK_作業" / "完了" if final == "completed" else root / "04_WK_作業"
            if work.resolve().parent != expected_parent.resolve():
                errors.append("終了同期後のWork配置先が終了状態と一致しません")
            index = root / "02_CT_管理/Work一覧.md"
            index_rows = [r for r in table_rows(read_text(index)) if r and r[0] == scope.get("work_id")] if index.is_file() else []
            if len(index_rows) != 1 or len(index_rows[0]) != 10 or index_rows[0][3] != final or index_rows[0][9] != nfc(work.relative_to(root).as_posix()):
                errors.append("終了同期後のWork台帳が終了状態・配置先と一致しません")
        if candidates_path.is_file():
            resolutions = {}
            for row in table_rows(section(read_text(candidates_path), "## 反映候補の処理履歴")):
                if len(row) >= 7 and CANDIDATE.fullmatch(row[1]):
                    resolutions[row[1]] = row
            for row in disposition_rows:
                latest = resolutions.get(row[0])
                expected_sync = "同期済み" if row[1] == "反映" else "同期不要"
                if not latest or latest[2] != row[1] or latest[3] != expected_sync or not latest[4] or not latest[5] or not latest[6]:
                    errors.append(f"承認した候補の処理が完了していません: {row[0]}")

        if scope.get("record_status") != final:
            errors.append("終了同期後のWork状態が承認済みfinal_statusと一致しません")
        for name in ("作業メモ.md", "反映候補.md", "入力/入力一覧.md"):
            item = work / name
            if item.is_file() and metadata(item).get("record_status") != final:
                errors.append(f"終了同期後のrecord_statusが一致しません: {name}")
        if state == "synced" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:]+(?:Z|[+-][0-9:]+)?)?", data.get("synced_at", "")):
            errors.append("終了同期のsynced_atが未設定または不正です")
    elif scope.get("record_status") != "active" and state != "invalidated" and phase != "resume":
        errors.append("終了同期未完了なのにWorkの状態が確定されています")
    return errors


def seal(work: Path, root: Path) -> list[str]:
    errors = validate(work, root, "before", require_seal=False)
    if errors:
        return errors
    path = work / "終了判断承認.sha256"
    value = approved_digest(work / "終了判断.md") + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != value:
        return ["既存の承認封印は上書きできません。旧判断を保存し新しいclose_idで再承認してください"]
    path.write_text(value, encoding="utf-8")
    return []


def version_table_refs(work: Path, root: Path) -> list[str]:
    """終了判断の版表に必要な参照を、現在のファイル構成から列挙する。"""
    scope = metadata(work / "作業内容.md") if (work / "作業内容.md").is_file() else {}
    refs = list(REQUIRED_WORK_REFS)
    for folder in ("入力", "作業成果"):
        for item in sorted((work / folder).rglob("*")):
            ref = "work:" + item.relative_to(work).as_posix()
            if item.is_file() and not item.name.startswith(".") and ref not in refs:
                refs.append(ref)
    if (work / "承認記録.md").is_file():
        refs.append("work:承認記録.md")
    requests = request_documents(root / "02_CT_管理/依頼", f"{scope.get('request_id', '')}_*.md")
    for request in requests[:1]:
        refs.append(request.relative_to(root).as_posix())
        plan = metadata(request).get("plan_file", "none")
        if plan not in {"", "none"}:
            refs.append(plan)
            if (root / plan).is_file():
                wbs = metadata(root / plan).get("wbs_file", "none")
                if wbs not in {"", "none"}:
                    refs.append(wbs)
        refs += [nfc(path.relative_to(root).as_posix())
                 for path in approval_record_paths(root, scope.get("request_id", "")).values() if path.is_file()]
    for context in sorted((root / "03_CX_コンテキスト").glob("*.md")):
        if metadata(context).get("document_type") == "project_context":
            refs.append(context.relative_to(root).as_posix())
    refs += [ref for ref in CLOSE_TARGET_LEDGERS + INDEX_REFS if (root / ref).is_file() and ref not in refs]
    return refs


def version_table(work: Path, root: Path, targets: dict[str, str], deletes: set[str]) -> tuple[list[str], list[str]]:
    """版表の雛形を作る。targetsは参照→承認用内容（work:終了反映案/…）、deletesは削除する参照。"""
    errors: list[str] = []
    refs = version_table_refs(work, root)
    refs += [ref for ref in list(targets) + sorted(deletes) if ref not in refs]
    lines = ["| 種別 | 参照 | 適用前SHA256 | 適用後SHA256 | 適用後内容 |", "| --- | --- | --- | --- | --- |"]
    for ref in refs:
        try:
            before = digest(resolve_ref(root, work, ref))
            if ref in deletes:
                lines.append(f"| target | {ref} | {before} | missing | none |")
            elif ref in targets:
                content = targets[ref]
                if not content.startswith("work:終了反映案/"):
                    errors.append(f"適用後内容は work:終了反映案/ 配下を指定してください: {ref}")
                    continue
                after = digest(resolve_ref(root, work, content))
                if after == "missing":
                    errors.append(f"承認用内容のファイルがありません: {content}")
                lines.append(f"| target | {ref} | {before} | {after} | {content} |")
            else:
                if before == "missing":
                    errors.append(f"sourceのファイルがありません: {ref}")
                lines.append(f"| source | {ref} | {before} | {before} | none |")
        except ValueError as exc:
            errors.append(str(exc))
    for ref in CLOSE_TARGET_WORK_REFS + CLOSE_TARGET_LEDGERS:
        if ref not in targets:
            errors.append(f"終了同期ではtargetにする必要があります（--target {ref}=work:終了反映案/…）: {ref}")
    return lines, errors
