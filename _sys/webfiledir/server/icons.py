"""プロバイダが持ち込むアイコン（ネットワーク構造の HUB・端末など、ファイル以外のものを表すとき）。

プロバイダはクラスの icons に {名前: Icon} を置き、Entry.icon で項目ごとに名前を選ぶ（Wiki「プロバイダの作りかた > アイコン」）。
アイコンは SVG の図形で書くが、**画面へ HTML として差し込むとスクリプトを仕込めてしまう**ので、
使ってよい図形と属性だけを起動時に確かめ、JSON の図形の並び（to_json）にして送る。画面は要素を 1 つずつ作る。
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

SVG_NS = "http://www.w3.org/2000/svg"
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
VIEWBOX_RE = re.compile(r"^-?\d+(\.\d+)?( -?\d+(\.\d+)?){3}$")
MAX_SVG_LENGTH = 8000

SHAPES = frozenset({"g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon"})
SHAPE_ATTRS = frozenset({
    "d", "cx", "cy", "r", "rx", "ry", "x", "y", "x1", "y1", "x2", "y2", "width", "height", "points",
    "fill", "fill-rule", "fill-opacity", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
    "stroke-dasharray", "stroke-opacity", "opacity", "transform",
})
# 色などの値に書いてよい文字（url(...) で外のものを参照させない）
VALUE_RE = re.compile(r"^[A-Za-z0-9#.,\-\s()%]*$")


class IconError(ValueError):
    """アイコンの定義の誤り（プロバイダを書く人が読む文）。"""


@dataclass(frozen=True)
class Icon:
    """svg は図形の並び（例: '<rect x="3" y="8" width="18" height="8" rx="2"/>'）。<svg> で囲まない。
    色は currentColor を使うと、画面の文字の色（選択中などの色）に合わせて変わる。"""

    svg: str
    view_box: str = "0 0 24 24"

    def to_json(self) -> dict:
        return {"viewBox": self.view_box, "shapes": [_shape(e) for e in _parse(self.svg)]}


def _parse(svg: str) -> list:
    if not isinstance(svg, str) or not svg.strip():
        raise IconError("svg は図形を書いた空でない文字列にしてください")
    if len(svg) > MAX_SVG_LENGTH:
        raise IconError(f"svg は {MAX_SVG_LENGTH} 文字までにしてください")
    try:
        root = ET.fromstring(f'<svg xmlns="{SVG_NS}">{svg}</svg>')
    except ET.ParseError as e:
        raise IconError(f"svg を XML として読めません: {e}") from None
    if (root.text or "").strip():
        raise IconError("svg に図形の外の文字があります")
    return list(root)


def _shape(el) -> dict:
    tag = el.tag.split("}", 1)[-1]
    if tag not in SHAPES:
        raise IconError(f"svg に使えない要素があります: <{tag}>（使えるもの: {', '.join(sorted(SHAPES))}）")
    attrs = {}
    for k, v in el.attrib.items():
        if k not in SHAPE_ATTRS:
            raise IconError(f"<{tag}> に使えない属性があります: {k}")
        if not VALUE_RE.match(v) or "url" in v.lower():
            raise IconError(f"<{tag}> の {k} に使えない値があります: {v!r}")
        attrs[k] = v
    if (el.text or "").strip():
        raise IconError(f"<{tag}> の中に文字があります")
    return {"tag": tag, "attrs": attrs, "children": [_shape(c) for c in el]}


def check_icons(icons, mount_icon) -> str | None:
    """アイコンの定義の誤り。正しければ None。"""
    if not isinstance(icons, dict):
        return "icons は {名前: Icon} の辞書にしてください"
    for name, icon in icons.items():
        if not isinstance(name, str) or not NAME_RE.match(name):
            return f"アイコンの名前 {name!r} は英小文字で始まる英小文字・数字・- の 32 文字までにしてください"
        if not isinstance(icon, Icon):
            return f"アイコン {name!r} は Icon にしてください"
        if not isinstance(icon.view_box, str) or not VIEWBOX_RE.match(icon.view_box):
            return f"アイコン {name!r}: view_box は \"0 0 24 24\" の形にしてください"
        try:
            icon.to_json()
        except IconError as e:
            return f"アイコン {name!r}: {e}"
    if mount_icon is not None and (not isinstance(mount_icon, str) or not NAME_RE.match(mount_icon)):
        return "mount_icon はアイコンの名前か None にしてください"
    return None
