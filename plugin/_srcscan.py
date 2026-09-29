"""ページの生テキストを、プラグインが自分の呼び出しを書き換えるために1行ずつ見る処理
（`new` などが使う共有モジュール）。

`_` で始まるのでプラグインとしては読み込まれない。使う側は自分の `__file__` の隣を
`importlib.util.spec_from_file_location` で読み込む（`_embedpage.py` と同じ）。

    classify_lines(text, ext)      → [(行, 種類)]。種類は "text" / "plugin" / "skip"
    code_span_parts(line)          → Markdownの1行を [(文字列, コードスパンか)] に分ける

**描いてもプラグインにならない所は書き換えない**ための区切り。書きかたの例として
書かれた呼び出し（説明ページの囲みコードなど）を、本物と取り違えて書き換えないようにする。
記法ごとに、実際の描画と同じ区切りにしてある（2026-09-26、`new` で確かめたもの）。

- "skip": 描いてもプラグインにならない行
    - Markdown: 囲みコード（```・~~~）の中、インデントのコード（4つの空白・タブ）
    - PukiWiki記法: 整形済みテキスト（行頭が空白）
    - どちらも: 他のプラグインの複数行の本体（`#code{{ … }}`）の中と、その閉じの行
      （PukiWiki記法は丸括弧の無い `#code{{` も本体になる。Markdownはならない）
- "plugin": ブロックのプラグインの行（Markdownは `#name(...)` の行すべて、PukiWiki記法は
  複数行の本体を開く行）。本体を開いたなら、続く本体の行は "skip"
- "text": それ以外（インラインの呼び出しは、ここに書かれる）。Markdownのコードスパン
  （`` `…` ``）の中は `code_span_parts` で分けて触らない
"""
import re

from wikilib.plugins import PLUGIN_BLOCK_FENCE_RE, match_plugin_block
from wikilib.render import is_pukiwiki

_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_PUKI_BODY_OPEN_RE = re.compile(r"^#[A-Za-z_][\w\-]*(?:\(.*\))?\s*(\{\{+)\s*$")
_CODE_SPAN_RE = re.compile(r"(`+[^`]*`+)")


def classify_lines(text, ext):
    markdown = not is_pukiwiki(ext)
    out = []
    fence_close = None
    body_close = None
    for line in text.split("\n"):
        if fence_close is not None:
            if fence_close.match(line):
                fence_close = None
            out.append((line, "skip"))
            continue
        if body_close is not None:
            if body_close.match(line):
                body_close = None
            out.append((line, "skip"))
            continue
        if markdown:
            m = _FENCE_OPEN_RE.match(line)
            if m:
                mark = m.group(1)
                fence_close = re.compile(
                    r"^ {0,3}" + re.escape(mark[0]) + "{" + str(len(mark)) + r",}\s*$")
                out.append((line, "skip"))
                continue
            if line.startswith(("    ", "\t")):
                out.append((line, "skip"))
                continue
        elif line[:1] in (" ", "\t"):
            out.append((line, "skip"))
            continue
        if markdown:
            parsed = match_plugin_block(line)
            opened = PLUGIN_BLOCK_FENCE_RE.fullmatch(parsed[2].rstrip()) if parsed else None
        else:
            parsed = opened = _PUKI_BODY_OPEN_RE.match(line)
        if parsed:
            if opened:
                body_close = re.compile(r"^\}{" + str(len(opened.group(1))) + r",}\s*$")
            out.append((line, "plugin"))
            continue
        out.append((line, "text"))
    return out


def code_span_parts(line):
    """Markdownの1行を [(文字列, コードスパンか)] に分ける。"""
    return [(p, bool(i % 2)) for i, p in enumerate(_CODE_SPAN_RE.split(line))]
