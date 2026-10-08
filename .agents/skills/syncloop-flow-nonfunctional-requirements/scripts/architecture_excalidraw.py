#!/usr/bin/env python3
"""構成データ（JSON）を検証し、決定的にExcalidrawファイルへ出力する。"""

from __future__ import annotations

import argparse
import json
import sys
import zlib
from pathlib import Path
from typing import Any


NODE_KINDS = {
    "client": ("#a5d8ff", "#4a9eed"),
    "boundary": ("#ffc9c9", "#ef4444"),
    "app": ("#d0bfff", "#8b5cf6"),
    "data": ("#c3fae8", "#22c55e"),
    "external": ("#ffd8a8", "#f59e0b"),
}
PENDING_COLORS = ("#fff3bf", "#f59e0b")
ZONE_KINDS = {
    "network": ("#dbe4ff", "#4a9eed", "#1e3a8a"),
    "server": ("#e5dbff", "#8b5cf6", "#5b21b6"),
    "external": ("#ffd8a8", "#f59e0b", "#9a3412"),
}
STATUSES = {"確認済み", "未確認"}
ROUTES = {"auto", "bottom"}

FONT_FAMILY = 2
LINE_HEIGHT = 1.25
NODE_FONT = 16
LABEL_FONT = 14
ZONE_FONT = 20
TITLE_FONT = 24
MIN_NODE_WIDTH = 190
MIN_NODE_HEIGHT = 90
NODE_PADDING = 16
GAP_X = 100
GAP_Y = 60
ZONE_PAD = 24
ZONE_LABEL_HEIGHT = 32
MARGIN = 40
BOTTOM_ROUTE_OFFSET = 36


class ArchitectureValidationError(ValueError):
    """構成データが出力条件を満たさない。"""


def load_data(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ArchitectureValidationError(f"構成データがありません: {path}") from error
    except json.JSONDecodeError as error:
        raise ArchitectureValidationError(f"JSON形式が不正です: {error.msg}") from error
    if not isinstance(data, dict):
        raise ArchitectureValidationError("構成データはオブジェクトである必要があります。")
    return data


def required_text(item: dict[str, Any], field: str, context: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ArchitectureValidationError(f"{context}.{field} が必要です。")
    return value.strip()


def grid_index(item: dict[str, Any], field: str, context: str) -> int:
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ArchitectureValidationError(f"{context}.{field} は0以上の整数で指定してください。")
    return value


def object_list(data: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = data.get(field)
    if not isinstance(value, list) or not value:
        raise ArchitectureValidationError(f"{field} は1件以上必要です。")
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise ArchitectureValidationError(f"{field}[{index}] はオブジェクトである必要があります。")
    return value


def text_width(text: str, font_size: int) -> float:
    return sum(font_size if ord(char) > 0x2E7F else font_size * 0.58 for char in text)


def text_size(text: str, font_size: int) -> tuple[float, float]:
    lines = text.split("\n")
    return max(text_width(line, font_size) for line in lines), len(lines) * font_size * LINE_HEIGHT


def node_text(node: dict[str, Any]) -> str:
    text = node["label"]
    if node["status"] == "未確認":
        text += "\n（未確認）"
    return text


def zone_children(zones: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {zone_id: [] for zone_id in zones}
    for zone_id, zone in zones.items():
        parent = zone.get("parent")
        if parent is not None:
            children[parent].append(zone_id)
    return children


def validate(data: dict[str, Any]) -> None:
    zones_raw = object_list(data, "zones")
    nodes_raw = object_list(data, "nodes")
    links_raw = data.get("links", [])
    if not isinstance(links_raw, list):
        raise ArchitectureValidationError("links は配列である必要があります。")
    if "title" in data:
        required_text(data, "title", "構成データ")

    zones: dict[str, dict[str, Any]] = {}
    for index, zone in enumerate(zones_raw, 1):
        context = f"zones[{index}]"
        zone_id = required_text(zone, "id", context)
        required_text(zone, "label", context)
        if zone_id in zones:
            raise ArchitectureValidationError(f"{context}.id が重複しています: {zone_id}")
        if zone.get("kind", "network") not in ZONE_KINDS:
            raise ArchitectureValidationError(f"{context}.kind は {', '.join(sorted(ZONE_KINDS))} のいずれかです。")
        zones[zone_id] = zone
    for zone_id, zone in zones.items():
        parent = zone.get("parent")
        if parent is None:
            continue
        if parent not in zones:
            raise ArchitectureValidationError(f"zones.{zone_id}.parent が存在しません: {parent}")
        seen = {zone_id}
        while parent is not None:
            if parent in seen:
                raise ArchitectureValidationError(f"zones.{zone_id}.parent が循環しています。")
            seen.add(parent)
            parent = zones[parent].get("parent")

    nodes: dict[str, dict[str, Any]] = {}
    cells: dict[tuple[int, int], str] = {}
    for index, node in enumerate(nodes_raw, 1):
        context = f"nodes[{index}]"
        node_id = required_text(node, "id", context)
        required_text(node, "label", context)
        if node_id in nodes:
            raise ArchitectureValidationError(f"{context}.id が重複しています: {node_id}")
        if node.get("zone") not in zones:
            raise ArchitectureValidationError(f"{context}.zone が存在しません: {node.get('zone')}")
        if node.get("kind") not in NODE_KINDS:
            raise ArchitectureValidationError(f"{context}.kind は {', '.join(sorted(NODE_KINDS))} のいずれかです。")
        if node.get("status") not in STATUSES:
            raise ArchitectureValidationError(f"{context}.status は 確認済み または 未確認 です。")
        cell = (grid_index(node, "col", context), grid_index(node, "row", context))
        if cell in cells:
            raise ArchitectureValidationError(f"{context} は {cells[cell]} と同じマス（col={cell[0]}, row={cell[1]}）です。")
        cells[cell] = node_id
        nodes[node_id] = node

    for index, link in enumerate(links_raw, 1):
        context = f"links[{index}]"
        if not isinstance(link, dict):
            raise ArchitectureValidationError(f"{context} はオブジェクトである必要があります。")
        for field in ("from", "to"):
            if link.get(field) not in nodes:
                raise ArchitectureValidationError(f"{context}.{field} が存在しません: {link.get(field)}")
        if link["from"] == link["to"]:
            raise ArchitectureValidationError(f"{context} は同じ構成要素同士をつないでいます。")
        if link.get("style", "solid") not in {"solid", "dashed"}:
            raise ArchitectureValidationError(f"{context}.style は solid または dashed です。")
        if link.get("route", "auto") not in ROUTES:
            raise ArchitectureValidationError(f"{context}.route は auto または bottom です。")
        if "label" in link:
            required_text(link, "label", context)
            src, dst = nodes[link["from"]], nodes[link["to"]]
            straight = src["row"] == dst["row"] or src["col"] == dst["col"]
            if link.get("route", "auto") == "auto" and not straight:
                raise ArchitectureValidationError(
                    f"{context} は折れ線になるためラベルを付けられません。同じ行・同じ列に置くか、構成要素のラベルへ書いてください。"
                )

    layout = compute_layout(data)
    check_zone_overlaps(layout, zones, nodes)


def compute_layout(data: dict[str, Any]) -> dict[str, Any]:
    zones = {zone["id"]: zone for zone in data["zones"]}
    nodes = {node["id"]: node for node in data["nodes"]}
    cols = sorted({node["col"] for node in nodes.values()})
    rows = sorted({node["row"] for node in nodes.values()})
    col_width = {col: MIN_NODE_WIDTH for col in cols}
    row_height = {row: MIN_NODE_HEIGHT for row in rows}
    for node in nodes.values():
        width, height = text_size(node_text(node), NODE_FONT)
        col_width[node["col"]] = max(col_width[node["col"]], width + NODE_PADDING * 2)
        row_height[node["row"]] = max(row_height[node["row"]], height + NODE_PADDING * 2)

    children = zone_children(zones)
    title_height = 0.0
    if data.get("title"):
        title_height = TITLE_FONT * LINE_HEIGHT + 20
    origin_x = 0.0
    origin_y = 0.0

    # 列・行の番号を詰め、空の列・行で図が間延びしないようにする
    col_x: dict[int, float] = {}
    cursor = origin_x
    for col in cols:
        col_x[col] = cursor
        cursor += col_width[col] + GAP_X
    row_y: dict[int, float] = {}
    cursor = origin_y
    for row in rows:
        row_y[row] = cursor
        cursor += row_height[row] + GAP_Y

    rects: dict[str, tuple[float, float, float, float]] = {}
    for node_id, node in nodes.items():
        rects[node_id] = (col_x[node["col"]], row_y[node["row"]], col_width[node["col"]], row_height[node["row"]])

    zone_rects: dict[str, tuple[float, float, float, float]] = {}

    def zone_rect(zone_id: str) -> tuple[float, float, float, float]:
        if zone_id in zone_rects:
            return zone_rects[zone_id]
        boxes = [rects[node_id] for node_id, node in nodes.items() if node["zone"] == zone_id]
        boxes += [zone_rect(child) for child in children[zone_id]]
        if not boxes:
            raise ArchitectureValidationError(f"ゾーン {zone_id} に構成要素がありません。")
        pad = ZONE_PAD
        left = min(box[0] for box in boxes) - pad
        top = min(box[1] for box in boxes) - pad - ZONE_LABEL_HEIGHT
        right = max(box[0] + box[2] for box in boxes) + pad
        bottom = max(box[1] + box[3] for box in boxes) + pad
        zone_rects[zone_id] = (left, top, right - left, bottom - top)
        return zone_rects[zone_id]

    for zone_id in zones:
        zone_rect(zone_id)

    # 図全体を余白とタイトルの下に寄せる
    shift_x = MARGIN - min(box[0] for box in list(zone_rects.values()) + list(rects.values()))
    shift_y = MARGIN + title_height - min(box[1] for box in list(zone_rects.values()) + list(rects.values()))
    rects = {key: (box[0] + shift_x, box[1] + shift_y, box[2], box[3]) for key, box in rects.items()}
    zone_rects = {key: (box[0] + shift_x, box[1] + shift_y, box[2], box[3]) for key, box in zone_rects.items()}
    return {"nodes": rects, "zones": zone_rects, "children": children}


def intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def descendants(zone_id: str, children: dict[str, list[str]]) -> set[str]:
    result = {zone_id}
    for child in children[zone_id]:
        result |= descendants(child, children)
    return result


def check_zone_overlaps(layout: dict[str, Any], zones: dict[str, dict[str, Any]], nodes: dict[str, dict[str, Any]]) -> None:
    for zone_id, zone_box in layout["zones"].items():
        members = descendants(zone_id, layout["children"])
        for node_id, node in nodes.items():
            if node["zone"] not in members and intersects(zone_box, layout["nodes"][node_id]):
                raise ArchitectureValidationError(
                    f"構成要素 {node_id} がゾーン {zone_id} の枠に入り込みます。col・row を見直してください。"
                )
    for zone_id, box in layout["zones"].items():
        for other_id, other_box in layout["zones"].items():
            if zone_id >= other_id:
                continue
            related = other_id in descendants(zone_id, layout["children"]) or zone_id in descendants(other_id, layout["children"])
            if not related and intersects(box, other_box):
                raise ArchitectureValidationError(f"ゾーン {zone_id} と {other_id} の枠が重なります。col・row を見直してください。")


def route_points(link: dict[str, Any], layout: dict[str, Any], nodes: dict[str, dict[str, Any]], bottom: float) -> tuple[list[tuple[float, float]], tuple[float, float], tuple[float, float]]:
    """(経路の点列, 始点の固定位置, 終点の固定位置) を返す。"""
    src = layout["nodes"][link["from"]]
    dst = layout["nodes"][link["to"]]
    s_col, s_row = nodes[link["from"]]["col"], nodes[link["from"]]["row"]
    d_col, d_row = nodes[link["to"]]["col"], nodes[link["to"]]["row"]
    s_cx, s_cy = src[0] + src[2] / 2, src[1] + src[3] / 2
    d_cx, d_cy = dst[0] + dst[2] / 2, dst[1] + dst[3] / 2

    if link.get("route", "auto") == "bottom":
        y = bottom + BOTTOM_ROUTE_OFFSET
        points = [(s_cx, src[1] + src[3]), (s_cx, y), (d_cx, y), (d_cx, dst[1] + dst[3])]
        return points, (0.5, 1.0), (0.5, 1.0)
    if s_row == d_row and s_col != d_col:
        if d_col > s_col:
            return [(src[0] + src[2], s_cy), (dst[0], d_cy)], (1.0, 0.5), (0.0, 0.5)
        return [(src[0], s_cy), (dst[0] + dst[2], d_cy)], (0.0, 0.5), (1.0, 0.5)
    if s_col == d_col:
        if d_row > s_row:
            return [(s_cx, src[1] + src[3]), (d_cx, dst[1])], (0.5, 1.0), (0.5, 0.0)
        return [(s_cx, src[1]), (d_cx, dst[1] + dst[3])], (0.5, 0.0), (0.5, 1.0)
    if d_col > s_col:
        start, end = (src[0] + src[2], s_cy), (dst[0], d_cy)
        mid_x = start[0] + GAP_X / 2
        return [start, (mid_x, start[1]), (mid_x, end[1]), end], (1.0, 0.5), (0.0, 0.5)
    start, end = (src[0], s_cy), (dst[0] + dst[2], d_cy)
    mid_x = start[0] - GAP_X / 2
    return [start, (mid_x, start[1]), (mid_x, end[1]), end], (0.0, 0.5), (1.0, 0.5)


def label_anchor(points: list[tuple[float, float]]) -> tuple[float, float]:
    best = max(range(len(points) - 1), key=lambda i: abs(points[i + 1][0] - points[i][0]) + abs(points[i + 1][1] - points[i][1]))
    return (points[best][0] + points[best + 1][0]) / 2, (points[best][1] + points[best + 1][1]) / 2


def base_element(element_id: str, kind: str, x: float, y: float, width: float, height: float) -> dict[str, Any]:
    seed = zlib.crc32(element_id.encode("utf-8"))
    return {
        "id": element_id,
        "type": kind,
        "x": round(x, 2),
        "y": round(y, 2),
        "width": round(width, 2),
        "height": round(height, 2),
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": seed,
        "version": 1,
        "versionNonce": seed,
        "isDeleted": False,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
    }


def text_element(element_id: str, text: str, font_size: int, cx: float, cy: float, *, container: str | None = None, color: str = "#1e1e1e", align: str = "center", left: float | None = None, top: float | None = None) -> dict[str, Any]:
    width, height = text_size(text, font_size)
    x = left if left is not None else cx - width / 2
    y = top if top is not None else cy - height / 2
    element = base_element(element_id, "text", x, y, width, height)
    element.update(
        {
            "strokeColor": color,
            "text": text,
            "originalText": text,
            "fontSize": font_size,
            "fontFamily": FONT_FAMILY,
            "textAlign": align,
            "verticalAlign": "middle" if container else "top",
            "containerId": container,
            "autoResize": True,
            "lineHeight": LINE_HEIGHT,
        }
    )
    return element


def render(data: dict[str, Any]) -> dict[str, Any]:
    validate(data)
    layout = compute_layout(data)
    zones = {zone["id"]: zone for zone in data["zones"]}
    nodes = {node["id"]: node for node in data["nodes"]}
    elements: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    def add(element: dict[str, Any]) -> dict[str, Any]:
        elements.append(element)
        by_id[element["id"]] = element
        return element

    if data.get("title"):
        title = text_element("title", data["title"], TITLE_FONT, 0, 0, left=MARGIN, top=MARGIN)
        add(title)

    # 外側のゾーンから先に描き、内側を前面にする
    def zone_depth(zone_id: str) -> int:
        depth, parent = 0, zones[zone_id].get("parent")
        while parent is not None:
            depth, parent = depth + 1, zones[parent].get("parent")
        return depth

    for zone_id in sorted(zones, key=lambda z: (zone_depth(z), list(zones).index(z))):
        fill, stroke, label_color = ZONE_KINDS[zones[zone_id].get("kind", "network")]
        x, y, width, height = layout["zones"][zone_id]
        rect = base_element(f"zone-{zone_id}", "rectangle", x, y, width, height)
        rect.update({"backgroundColor": fill, "strokeColor": stroke, "strokeWidth": 1, "opacity": 40, "roundness": {"type": 3}})
        add(rect)
        add(text_element(f"zone-{zone_id}-label", zones[zone_id]["label"], ZONE_FONT, 0, 0, color=label_color, align="left", left=x + 16, top=y + 12))

    for node_id, node in nodes.items():
        fill, stroke = PENDING_COLORS if node["status"] == "未確認" else NODE_KINDS[node["kind"]]
        x, y, width, height = layout["nodes"][node_id]
        rect = base_element(f"node-{node_id}", "rectangle", x, y, width, height)
        rect.update({"backgroundColor": fill, "strokeColor": stroke, "roundness": {"type": 3}})
        if node["status"] == "未確認":
            rect["strokeStyle"] = "dashed"
        label = text_element(f"node-{node_id}-label", node_text(node), NODE_FONT, x + width / 2, y + height / 2, container=rect["id"])
        rect["boundElements"].append({"id": label["id"], "type": "text"})
        add(rect)
        add(label)

    bottom = max(box[1] + box[3] for box in layout["zones"].values())
    bottom = max(bottom, max(box[1] + box[3] for box in layout["nodes"].values()))
    for index, link in enumerate(data.get("links", []), 1):
        points, start_fixed, end_fixed = route_points(link, layout, nodes, bottom)
        arrow_id = f"link-{index}"
        origin = points[0]
        relative = [[round(px - origin[0], 2), round(py - origin[1], 2)] for px, py in points]
        xs = [point[0] for point in relative]
        ys = [point[1] for point in relative]
        arrow = base_element(arrow_id, "arrow", origin[0], origin[1], max(xs) - min(xs), max(ys) - min(ys))
        arrow.update(
            {
                "points": relative,
                "lastCommittedPoint": None,
                "startBinding": {"elementId": f"node-{link['from']}", "focus": 0, "gap": 1, "fixedPoint": list(start_fixed)},
                "endBinding": {"elementId": f"node-{link['to']}", "focus": 0, "gap": 1, "fixedPoint": list(end_fixed)},
                "startArrowhead": None,
                "endArrowhead": "arrow",
                "elbowed": False,
            }
        )
        if link.get("style") == "dashed":
            arrow["strokeStyle"] = "dashed"
        by_id[f"node-{link['from']}"]["boundElements"].append({"id": arrow_id, "type": "arrow"})
        by_id[f"node-{link['to']}"]["boundElements"].append({"id": arrow_id, "type": "arrow"})
        add(arrow)
        if link.get("label"):
            cx, cy = label_anchor(points)
            label = text_element(f"{arrow_id}-label", link["label"], LABEL_FONT, cx, cy, container=arrow_id)
            arrow["boundElements"].append({"id": label["id"], "type": "text"})
            add(label)

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "syncloop-flow-nonfunctional-requirements",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
        "files": {},
    }


def write_scene(data: dict[str, Any], output: Path) -> None:
    if output.suffix != ".excalidraw":
        raise ArchitectureValidationError("出力ファイルの拡張子は .excalidraw にしてください。")
    if output.exists():
        raise ArchitectureValidationError(f"既存のファイルは上書きしません: {output}。差分を確認し、別名にするか利用者の判断を得てください。")
    scene = render(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(scene, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "render"):
        command = sub.add_parser(name)
        command.add_argument("--data", required=True, type=Path)
        if name == "render":
            command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        data = load_data(args.data)
        if args.command == "validate":
            validate(data)
            print("構成データは出力条件を満たしています。")
        else:
            write_scene(data, args.output)
            print(f"出力しました: {args.output}")
    except ArchitectureValidationError as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
