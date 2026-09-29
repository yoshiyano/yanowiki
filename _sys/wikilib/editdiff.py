"""編集中の内容と、保存されている内容の差分をHTMLにする。

「更新状況」タブの左側に出す。右側にはオリジナルのページを並べるため、
**差分の各行に「その行がオリジナルのどの見出しに属するか」を持たせる**
（`data-anchor`）。左右のスクロール位置を、見出しを手がかりに揃えるのに使う。

対応づけに見出しを選んだのは、行番号だと編集で簡単にずれてしまうのに対し、
見出しは追加・削除されない限り同じ場所を指し続けるためである。
見出しが1つも無いページでは対応点が取れないので、その場合は
呼び出し側（editor.js）が比率でのおおまかな追従に切り替える。
"""
import re
from html import escape

from wikilib.backup import NO_NEWLINE_MARK
from wikilib.render import heading_positions, parse_source

# unified diff のハンク見出し: @@ -旧開始,旧行数 +新開始,新行数 @@
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def source_anchors(engine, text, ext=".md"):
    """生テキストから [(開始行, 見出しid), ...] を作る（行は0始まり）。

    その行がどの見出しの配下かを引くための表。見出しより前の行は
    どの見出しにも属さないので、表には入れない。"""
    tokens = parse_source(engine, text, ext, {"wiki": None})
    return [(p["start"], p["id"]) for p in heading_positions(tokens)]


def anchor_for_line(anchors, line):
    """その行が属する見出しのidを返す。最初の見出しより前なら空文字列。

    anchors は行の昇順。ページの見出し数はたかが知れているので、
    素直に前から見ていく。"""
    found = ""
    for start, anchor in anchors:
        if start > line:
            break
        found = anchor
    return found


def _line_class(line):
    """その行に付ける印。変更のない行も含め、必ず1つ返す。

    どの行も同じ「1行＝1ブロック」の形にしておくと、行の高さが揃い、
    背景色も行いっぱいに敷ける。"""
    if line.startswith(("+++", "---")):
        return "d-at"
    if line.startswith("+"):
        return "d-add"
    if line.startswith("-"):
        return "d-del"
    if line.startswith("@"):
        return "d-at"
    return "d-ctx"


def build_diff_html(diff_text, old_anchors):
    """unified diff を、行ごとに色と対応見出しを付けたHTMLにする。

    対応づけは**オリジナル側の行番号**で行う。右側に並べるのがオリジナルの
    ページなので、追加された行（+）についても「オリジナルのどこに入るか」を
    指させたほうが、左右の対応が取れる。"""
    if not diff_text.strip():
        return '<p class="edit-diff-same">保存されている内容と同じです。</p>'

    out = []
    old_line = 0  # いま見ている行が、オリジナルの何行目にあたるか（1始まり）
    lines = diff_text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # 末尾の改行で生じる空要素。行としては数えない
    for line in lines:
        cls = _line_class(line)
        m = HUNK_RE.match(line)
        if m:
            old_line = int(m.group(1))
        elif line.startswith("+") or line.startswith(NO_NEWLINE_MARK):
            # 追加された行はオリジナルに無いので進めない（挿入位置を指したままにする）。
            # 「改行なし」の印も行ではないので数えない。
            pass
        elif line.startswith("-"):
            old_line += 1
        else:
            old_line += 1  # 変更のない行（先頭が空白）

        # ファイル名の行（--- / +++）は本文のどこも指さないので対応づけない
        header = line.startswith(("+++", "---"))
        anchor = "" if header else anchor_for_line(old_anchors, max(0, old_line - 1))
        attrs = f' class="{cls}"'
        if anchor:
            attrs += f' data-anchor="{escape(anchor, quote=True)}"'
        out.append(f"<span{attrs}>{escape(line)}</span>")
    # 改行文字は入れない。各行がブロックとして1行を占めるので、
    # 改行を挟むと1行ごとに空行が入ってしまう
    return "".join(out)
