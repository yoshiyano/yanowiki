"""項目の属性（更新日時・サイズ・仮想構造に固有の属性など）の定義。

属性は「値」と「表現方法」の 2 つの規則を持つ（Wiki「API 設計 > 属性」）。

- 値の規則: kind（"number" は数として、"text" は自然順で比べる）と none（値が None の項目の置き場所。
  "first" は昇順でも降順でも先頭＝最優先、"last" は昇順でも降順でも末尾＝無効データ）
- 表現方法: format（詳細表示などでの見せかた）。関数は画面へ送れないので、決まった種類から選ぶ宣言にする

プロバイダはクラスの attributes に、詳細表示の列に並べる順で定義を置く。名前は属性ではない
（項目を指す ID なので、どのマウントにも必ずある）。定義は起動時（build_mounts）に check_attributes で確かめる。
"""

import re
from dataclasses import dataclass, field

KINDS = ("number", "text")
NONE_ORDERS = ("first", "last")
ALIGNS = ("start", "end")
SOURCES = ("entry", "filetype")  # filetype … 値は画面が名前の拡張子から決める（「種類」）

# 表現方法の種類と、その種類で書ける項目 → 値の型
FORMATS = {
    "text": {"prefix": str, "suffix": str},
    "number": {"prefix": str, "suffix": str, "digits": int, "minDigits": int, "grouping": bool},
    "bytes": {},
    "datetime": {},
    "date": {},
    "map": {"labels": dict},
}
FORMAT_COMMON = {"type": str, "none": str}  # none … 値が None のときに出す文字（既定は空）

KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
# 画面が別の意味で使うキー（名前、ごみ箱の画面の列）
RESERVED_KEYS = frozenset({"name", "originalPath", "deletedAt"})


@dataclass(frozen=True)
class Attribute:
    key: str                  # 値を入れるキー（Entry.to_json の attrs のキー）。並べ替えのキーにもなる
    label: str                # 列の見出し・並べ替えのメニューに出す名前
    kind: str = "text"        # 値の比べかた: "number" / "text"
    format: dict = field(default_factory=lambda: {"type": "text"})  # 表現方法
    none: str = "last"        # 値が None の項目: "first"（最優先）/ "last"（無効データ）
    align: str | None = None  # 列の寄せ: "start" / "end"。None なら number は右、text は左
    width: int | None = None  # 詳細表示の列の幅（px）。None なら画面の既定
    source: str = "entry"     # 値の出どころ: "entry"（プロバイダが返す）/ "filetype"（画面が名前から決める）

    def to_json(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "format": dict(self.format),
            "none": self.none,
            "align": self.align or ("end" if self.kind == "number" else "start"),
            "width": self.width,
            "source": self.source,
        }


# --- よく使う属性の作りかた ---

def mtime_attribute(label: str = "更新日時") -> Attribute:
    # 日時は数として比べるが、文字の幅が揃うので左寄せにする（これまでの詳細表示と同じ）
    return Attribute("mtime", label, "number", {"type": "datetime"}, align="start", width=150)


def size_attribute(label: str = "サイズ") -> Attribute:
    return Attribute("size", label, "number", {"type": "bytes"}, width=100)


def filetype_attribute(label: str = "種類") -> Attribute:
    return Attribute("type", label, "text", {"type": "text"}, width=170, source="filetype")


# 実ファイルと同じ列（これまでの詳細表示: 名前・更新日時・種類・サイズ）
DEFAULT_ATTRIBUTES = (mtime_attribute(), filetype_attribute(), size_attribute())


def check_attributes(attributes) -> str | None:
    """属性の定義の誤り（操作者ではなく、プロバイダを書く人が読む文）。正しければ None。"""
    if not isinstance(attributes, (list, tuple)):
        return "attributes は Attribute の並び（tuple か list）にしてください"
    seen = set()
    for a in attributes:
        if not isinstance(a, Attribute):
            return f"attributes に Attribute でないものがあります: {a!r}"
        where = f"属性 {a.key!r}"
        if not isinstance(a.key, str) or not KEY_RE.match(a.key):
            return f"{where}: key は英字で始まる英数字・_ の 32 文字までにしてください"
        if a.key in RESERVED_KEYS:
            return f"{where}: key の {a.key} は画面が使うので使えません"
        if a.key in seen:
            return f"{where}: key が重複しています"
        seen.add(a.key)
        if not isinstance(a.label, str) or not a.label:
            return f"{where}: label は空でない文字列にしてください"
        if a.kind not in KINDS:
            return f"{where}: kind は {', '.join(KINDS)} のどれかにしてください"
        if a.none not in NONE_ORDERS:
            return f"{where}: none は {', '.join(NONE_ORDERS)} のどれかにしてください"
        if a.align is not None and a.align not in ALIGNS:
            return f"{where}: align は {', '.join(ALIGNS)} か None にしてください"
        if a.width is not None and (isinstance(a.width, bool) or not isinstance(a.width, int) or not 20 <= a.width <= 1000):
            return f"{where}: width は 20〜1000 の整数か None にしてください"
        if a.source not in SOURCES:
            return f"{where}: source は {', '.join(SOURCES)} のどれかにしてください"
        err = _check_format(a.format)
        if err:
            return f"{where}: {err}"
    return None


def _check_format(fmt) -> str | None:
    if not isinstance(fmt, dict) or fmt.get("type") not in FORMATS:
        return f"format は {{\"type\": ...}} の形で、type は {', '.join(FORMATS)} のどれかにしてください"
    allowed = {**FORMAT_COMMON, **FORMATS[fmt["type"]]}
    for k, v in fmt.items():
        if k not in allowed:
            return f"format に知らない項目があります: {k}（type = {fmt['type']} で書けるもの: {', '.join(sorted(allowed))}）"
        t = allowed[k]
        if not isinstance(v, t) or (t is int and isinstance(v, bool)):
            return f"format の {k} は {t.__name__} にしてください"
    if fmt["type"] == "map" and not all(isinstance(k, str) and isinstance(v, str) for k, v in fmt.get("labels", {}).items()):
        return "format の labels は {値の文字列: 表示する文字} の形にしてください"
    for k in ("digits", "minDigits"):
        if k in fmt and not 0 <= fmt[k] <= 10:
            return f"format の {k} は 0〜10 にしてください"
    return None
