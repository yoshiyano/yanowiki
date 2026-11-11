"""`&icd{…};`（文中のコード）の中身の読みかたと、Markdownの `` `…` `` との置き換え。

パーサー（`wikilib.pukiwiki`・`wikilib.plugins`）が中身の範囲を決める段階で
関わるので、`plugin/icd.py` ではなくここに置く。バックスラッシュのエスケープは
このプラグイン限定（設計者「このプラグインに限定の対応でも構いません」2026-11-07）。
ほかのプラグインは `&color(red){C:\\};` のように `\\` で終わる中身を今までどおり
書ける。

中身の決まり（クロコの実装例。設計者は未確認）:

    \\{  \\}  \\|  \\'  \\%     その文字（周りの書きかたに読まれない）
    \\\\                  上の文字の前か中身の末尾で `\\` 1文字

ほかの `\\` はそのままの文字（`C:\\Users` や `\\d+` を書き換えずに済むように）。

置き換えは `encode_body`（`` `a` `` → `&icd{a};`）と `decode_body`・`markdown_code`
（`&icd{a};` → `` `a` ``）。書きかたを切り替える変換器はまだ無い。
"""
import re

ICD_NAME = "icd"
_ICD_CALL_RE = re.compile(r"&icd(?:\(\s*\))?\{")
_ESCAPE_RE = re.compile(r"\\(?:([{}|'%])|(\\)(?=[{}|'%\\]|$))")


def find_body_end(name, text, start):
    """text[start] は `{` の直後。対応する `}` の位置を返す（無ければ None）。

    `name` が icd のときだけ、`\\{` `\\}` `\\\\` を波括弧として数えない。"""
    escapes = name == ICD_NAME
    depth = 1
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if escapes and ch == "\\" and i + 1 < n and text[i + 1] in "{}\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def match_call(text, pos):
    """text[pos:] が `&icd{…};` か `&icd(){…};` なら (中身, 終端位置) を返す。"""
    head = _ICD_CALL_RE.match(text, pos)
    if not head:
        return None
    close = find_body_end(ICD_NAME, text, head.end())
    if close is None or text[close + 1:close + 2] != ";":
        return None
    return text[head.end():close], close + 2


def split_outside_calls(text):
    """`|` で分ける。`&icd{…};` の中の `|` では分けない（PukiWiki記法の表・定義リスト）。"""
    parts = []
    start = pos = 0
    while True:
        bar = text.find("|", pos)
        if bar == -1:
            break
        amp = text.find("&icd", pos, bar)
        call = match_call(text, amp) if amp != -1 else None
        if call:
            pos = call[1]
            continue
        if amp != -1:
            pos = amp + 1
            continue
        parts.append(text[start:bar])
        start = pos = bar + 1
    parts.append(text[start:])
    return parts


def decode_body(body):
    """中身のエスケープを外して、表示する文字列にする。"""
    return _ESCAPE_RE.sub(lambda m: m.group(1) or m.group(2), body)


def encode_body(text):
    """表示する文字列を `&icd{…};` の中身にする（`decode_body` の逆）。

    エスケープは要るときだけ付ける。`\\` は記号の前か末尾のとき、波括弧は対に
    なっていないとき、`'` `%` は2つ以上続くとき（クロコの実装例）。"""
    body = re.sub(r"\\(?=[{}|'%\\]|$)", r"\\\\", text)
    depth = 0
    balanced = True
    for ch in text:
        depth += (ch == "{") - (ch == "}")
        balanced = balanced and depth >= 0
    if not (balanced and depth == 0):
        body = re.sub(r"[{}]", lambda m: "\\" + m.group(0), body)
    return re.sub(r"'{2,}|%{2,}", lambda m: "".join("\\" + c for c in m.group(0)), body)


def markdown_code(text, in_table=False):
    """文字列を、同じ表示になる Markdown の `` `…` `` にする。"""
    runs = re.findall(r"`+", text)
    fence = "`" * (max((len(r) for r in runs), default=0) + 1)
    pad = text.startswith("`") or text.endswith("`") or (
        text.startswith(" ") and text.endswith(" ") and text.strip())
    code = fence + (" " + text + " " if pad else text) + fence
    return code.replace("|", "\\|") if in_table else code
