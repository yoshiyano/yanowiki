"""Markdown記法の `<!-- … -->` をコメントとして扱い、出力から取り除く。

生のHTMLを受け付けない設定（`markdown.allow_html: false`、既定）では、
markdown-it は `<!-- … -->` をHTMLとして読まず、文字のまま画面に出していた。
コメントは「書いた人のためのメモ」で、表示すべきものではないので、
**allow_html の設定にかかわらず取り除く。** HTMLとして通すのではなく
消すだけなので、allow_html: false の安全性は変わらない。

- 行頭から始まるコメント（`<!--` の行から `-->` を含む行まで）は、
  空行をはさんでいてもまとめて消す（CommonMark の HTMLブロック 種別2 と同じ範囲）。
  閉じの `-->` が無ければ、文書の終わりまでがコメントになる（これも同じ）
- 文中のコメント（`あいう <!-- メモ --> えお`）は、その部分だけを消す
- コードの中（`` `<!-- -->` ``・フェンス・字下げ）は消さない。コードの規則が
  先に働くので、ここまで来ない

**消えるのは表示だけ**で、ページの元のテキストには残る。閲覧の権限がある人は
編集画面や平文ファイルから読めるので、秘密を書く場所にはならない。

PukiWiki記法（`.txt`）はこの規則を通らない（あちらの行コメントは `//`）。
"""

COMMENT_OPEN = "<!--"
COMMENT_CLOSE = "-->"


def comment_block(state, start_line, end_line, silent):
    """行頭の `<!--` から、`-->` を含む行までを読み飛ばす（トークンは作らない）。"""
    if state.sCount[start_line] - state.blkIndent >= 4:
        return False  # 字下げ4つ以上はコード
    pos = state.bMarks[start_line] + state.tShift[start_line]
    if not state.src.startswith(COMMENT_OPEN, pos):
        return False

    line = start_line
    search_from = pos + len(COMMENT_OPEN)
    close_at = -1
    while line < end_line:
        close_at = state.src.find(COMMENT_CLOSE, search_from, state.eMarks[line])
        if close_at != -1:
            break
        line += 1
        if line < end_line:
            search_from = state.bMarks[line]

    if close_at != -1:
        rest = state.src[close_at + len(COMMENT_CLOSE):state.eMarks[line]]
        if rest.strip():
            # `<!-- メモ --> 本文` のように後ろに文字が続く。行ごと消すと本文を
            # 失うので、ここでは受けず、段落の中で comment_inline に任せる
            return False
    else:
        line = end_line - 1  # 閉じが無い: 文書の終わりまで

    if silent:
        return True
    state.line = line + 1
    return True


def comment_inline(state, silent):
    """文中の `<!-- … -->` を読み飛ばす。閉じが無ければ何もしない（文字のまま）。"""
    pos = state.pos
    if not state.src.startswith(COMMENT_OPEN, pos):
        return False
    close_at = state.src.find(COMMENT_CLOSE, pos + len(COMMENT_OPEN))
    if close_at == -1:
        return False
    state.pos = close_at + len(COMMENT_CLOSE)
    return True


def install(engine):
    """markdown-it のインスタンスに、コメントを取り除く規則を足す。"""
    engine.block.ruler.before(
        "html_block", "md_comment", comment_block,
        {"alt": ["paragraph", "reference", "blockquote", "list"]})
    engine.inline.ruler.before("html_inline", "md_comment", comment_inline)
