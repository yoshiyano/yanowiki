"""PukiWiki記法のパーサー。

`.txt` のページをPukiWiki記法として解釈する。書きかたは本家PukiWikiの
[テキスト整形ルール](https://pukiwiki.sourceforge.io/?FormattingRules)に準拠する。

**出力はMarkdownのレンダリング結果に揃える。** そのために、ここで作るのは
HTML文字列ではなく markdown-it-py のトークン列で、HTML化はmarkdown-itの
レンダラにそのまま任せる。こうすると次の3つが記法によらず同じになる。

  - 出力されるHTMLの形（テーマのCSSがそのまま効く）
  - プラグイン記法（`#name()` / `&name();`）の扱い（同じレンダリング規則を通る）
  - 目次・見出しのid・セクション編集の宛先（どちらもトークン列から取り出すため）

記法ごとにHTMLを直接組み立てると、この3つが記法の数だけ枝分かれしてしまう。

見出しは本家と同じ3段階・同じタグで、`*`→h2、`**`→h3、`***`→h4 に対応する
（本家PukiWikiの出力もh2〜h4）。

h1にしないのは、このシステムではページタイトルをテーマのヘッダが描くため。
本文の最上位の見出しをh1にすると、そこと重なってしまう。

**目次に出す深さの設定（`markdown.toc_depth`、既定は3）は見出しの生のレベルで
効くため、既定のままでは `***`（h4）が目次から漏れる。** PukiWiki記法のページで
3段階すべてを目次に出したい場合は、`toc_depth` を4以上にする必要がある。

PukiWikiではページ名がそのままタイトルなので、先頭の見出しをタイトルとして
抜き出す扱い（Markdown側の first_h1_as_title）は適用しない。

未対応の記法は、このファイル末尾の TODO を参照。
"""
import re
from html.entities import html5

from markdown_it.token import Token
from mdit_py_plugins.anchors.index import slugify, unique_slug

from wikilib.extrarules import MAX_NEST_DEPTH, match_extra_rule
from wikilib.paths import FOOTNOTE_TIP_MAX, IMAGE_EXTS
from wikilib.subst import DISPLAY_TIME_NAMES

# ---- ブロックの見分けかた ---------------------------------------------------

HEADING_RE = re.compile(r"^(\*{1,3})(.*)$")
# 見出し行の末尾に置くアンカー（`* 見出し [#anchor]`）
HEADING_ANCHOR_RE = re.compile(r"\s*\[#([A-Za-z][\w-]*)\]\s*$")
HR_RE = re.compile(r"^-{4,}\s*$")
LIST_RE = re.compile(r"^([-+]{1,3})(?![-+])(.*)$")
QUOTE_RE = re.compile(r"^(>{1,3})(.*)$")
ALIGN_RE = re.compile(r"^(LEFT|CENTER|RIGHT):(.*)$")
# 表組み。`|セル|セル|` の行。行末の h / f / c は行の種類（見出し行・フッタ行・書式指定行）
TABLE_RE = re.compile(r"^\|(.+)\|([hHfFcC])?$")
# セルの先頭に書ける書式指定。`CENTER:COLOR(red):字` のように重ねて書ける
CELL_STYLE_RE = re.compile(
    r"^(?:(LEFT|CENTER|RIGHT)|(BG)?COLOR\(([#\w]+)\)|SIZE\((\d+)\)):(.*)$")
CSV_TABLE_PREFIX = ","  # 行頭が半角カンマの行はCSV形式の表
CSV_MERGE_MARK = "=="  # CSV形式で左のセルと横につなげる目印
# 定義リスト。`:項目名|説明文` の行
# 項目名は省略できる（前の項目に説明文をもう1つ足す書きかた）ので、
# 空文字列にもマッチするよう ".*?" にしてある（"+?" だと1文字以上を要求してしまう）
DEFLIST_RE = re.compile(r"^:(.*?)\|(.*)$")
# ブロックプラグイン。本家は `#contents` のように括弧を省けるので、Markdown側の
# 定義（plugins.PLUGIN_BLOCK_RE）と違って括弧を任意にしている。
PLUGIN_BLOCK_RE = re.compile(
    r"^#([A-Za-z_][\w-]*)(?:\((.*)\))?(?:(\{\{+)|\{([^{}]*)\})?\s*$")
COMMENT_PREFIX = "//"
PRE_PREFIX = " "  # 行頭が半角空白の行は整形済みテキスト

# ---- 生HTML（markdown-it-pyの html_block / html_inline ルールに合わせてある） ---
# markdown_it.common.html_re / markdown_it.common.html_blocks と同じ組み立てかた。
# プラグインが返す文字列（例: note.py の `<div class="note...">...`）を、
# 展開のために再度パースし直したときにエスケープされてしまわないよう、
# 生のHTMLタグはタグのまま通す。allow_html（config: markdown.allow_html）が
# 偽の場面では使わない（不特定多数が書く運用での安全側の設定を尊重するため）。
_HTML_ATTR_NAME = r"[a-zA-Z_:][a-zA-Z0-9:._-]*"
_HTML_UNQUOTED = r"[^\"'=<>`\x00-\x20]+"
_HTML_SINGLE_QUOTED = r"'[^']*'"
_HTML_DOUBLE_QUOTED = r'"[^"]*"'
_HTML_ATTR_VALUE = "(?:" + _HTML_UNQUOTED + "|" + _HTML_SINGLE_QUOTED + "|" + _HTML_DOUBLE_QUOTED + ")"
_HTML_ATTRIBUTE = r"(?:\s+" + _HTML_ATTR_NAME + r"(?:\s*=\s*" + _HTML_ATTR_VALUE + r")?)"
_HTML_OPEN_TAG = r"<[A-Za-z][A-Za-z0-9\-]*" + _HTML_ATTRIBUTE + r"*\s*/?>"
_HTML_CLOSE_TAG = r"<\/[A-Za-z][A-Za-z0-9\-]*\s*>"
_HTML_COMMENT = r"<!---?>|<!--(?:[^-]|-[^-]|--[^>])*-->"
_HTML_PROCESSING = r"<[?][\s\S]*?[?]>"
_HTML_DECLARATION = r"<![A-Za-z][^>]*>"
_HTML_CDATA = r"<!\[CDATA\[[\s\S]*?\]\]>"

# インライン中に単体で書けるHTML（1つの完結したタグ・コメント等）。
# markdown_it.common.html_re.HTML_TAG_RE と同じ組み立て
# .match(text, pos) はpos位置に暗黙にアンカーされるため "^" は付けない
# （付けると pos>0 のとき常に不一致になる。re の既知の仕様）。
HTML_INLINE_RE = re.compile(
    "(?:" + _HTML_OPEN_TAG + "|" + _HTML_CLOSE_TAG + "|" + _HTML_COMMENT + "|"
    + _HTML_PROCESSING + "|" + _HTML_DECLARATION + "|" + _HTML_CDATA + ")"
)
_HTML_OPEN_CLOSE_TAG_RE_STR = "^(?:" + _HTML_OPEN_TAG + "|" + _HTML_CLOSE_TAG + ")"

# ブロックの開始行を見分ける (開始条件, 終了条件) の組。上から順に最初に
# マッチしたものを使う（markdown_it.rules_block.html_block.HTML_SEQUENCESと同じ）。
# 終了条件が `^$` のものは「空行が来るまで」の意味（本文中に単独で書ける
# ブロックレベルタグ・任意の完結したタグ行は、空行までを1ブロックとする）。
HTML_BLOCK_SEQUENCES = [
    (re.compile(r"^<(script|pre|style|textarea)(?=(\s|>|$))", re.IGNORECASE),
     re.compile(r"</(script|pre|style|textarea)>", re.IGNORECASE)),
    (re.compile(r"^<!--"), re.compile(r"-->")),
    (re.compile(r"^<\?"), re.compile(r"\?>")),
    (re.compile(r"^<![A-Z]"), re.compile(r">")),
    (re.compile(r"^<!\[CDATA\["), re.compile(r"\]\]>")),
    (re.compile("^</?(" + "|".join([
        "address", "article", "aside", "base", "basefont", "blockquote", "body",
        "caption", "center", "col", "colgroup", "dd", "details", "dialog", "dir",
        "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form",
        "frame", "frameset", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header",
        "hr", "html", "iframe", "legend", "li", "link", "main", "menu", "menuitem",
        "nav", "noframes", "ol", "optgroup", "option", "p", "param", "search",
        "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead",
        "title", "tr", "track", "ul",
    ]) + r")(?=(\s|/?>|$))", re.IGNORECASE), re.compile(r"^$")),
    (re.compile(_HTML_OPEN_CLOSE_TAG_RE_STR + r"\s*$"), re.compile(r"^$")),
]


def _html_block_end(line):
    """行がHTMLブロックの開始条件に当てはまれば、対応する終了条件（正規表現）を
    返す。当てはまらなければNoneを返す。"""
    for start_re, end_re in HTML_BLOCK_SEQUENCES:
        if start_re.search(line):
            return end_re
    return None


def append_html_block(tokens, lines, i, offset, end_re):
    """生HTMLブロックを追加する。次に読む行を返す。

    開始行そのものが終了条件も満たしていれば、その1行だけで完結させる
    （`<!-- コメント -->` の1行だけの書きかたなど）。それ以外は、終了条件に
    一致する行（多くは空行）が現れるまでをそのまま生で拾い集める。最後まで
    見つからなければ、文書の終わりまでを1つのブロックにする。"""
    start = i
    if not end_re.search(lines[i]):
        i += 1
        while i < len(lines):
            if end_re.pattern == r"^$":
                if not lines[i].strip():
                    break
            elif end_re.search(lines[i]):
                i += 1
                break
            i += 1
    else:
        i += 1
    token = Token("html_block", "", 0, block=True, content="\n".join(lines[start:i]) + "\n")
    token.map = [offset + start, offset + i]
    tokens.append(token)
    return i


# ---- インラインの見分けかた -------------------------------------------------
# 1つの正規表現にまとめ、左から順に最初に見つかったものを処理する。
# 同じ位置で始まりうるもの（''' と ''）は、長いほうを先に並べて取り違えを防ぐ。
#
# "&…" で始まるもの（インラインプラグイン・数値文字参照）はここに含めない。
# プラグインの本文（{…}）に別のプラグイン呼び出しを入れ子にできる
# （expand_plugin）ため、対応する閉じ括弧を数え上げる必要があり、固定長の
# 正規表現では書けない（"((…))" の注釈と同じ理由。find_annotation_end 参照。
# parse_inline が別途 find_amp_token で探す）。
INLINE_RE = re.compile(
    r"\[\[(?P<link>[^\[\]]+)\]\]"
    # "{[…]}" は "[[…]]" と同じ書式（表示名>リンク先 等）で、リンク先だけが
    # 既定でルートからの絶対ではなく、いま開いているページからの相対
    # （"./"を補う）になる。実装はlink_tokensのrelative引数に集約する
    # （Wiki設計者の指示、2026-09-04）。
    r"|\{\[(?P<rlink>[^\[\]{}]+)\]\}"
    r"|'''(?P<em>.+?)'''"
    r"|''(?P<strong>.+?)''"
    r"|%%%(?P<ins>.+?)%%%"
    r"|%%(?P<strike>.+?)%%"
    r"|(?P<url>(?:https?|ftp|news)://[^\s<>\"']+)"
    r"|(?P<mail>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"
    # WikiName。大文字始まりの単語（例: "Puki"）が2つ以上続くと、そのページへの
    # 自動リンクになる（本家の $WikiName = '(?:[A-Z][a-z]+){2,}(?!\w)' と同じ）。
    r"|(?P<wikiname>(?:[A-Z][a-z]+){2,})(?!\w)"
)

PLUGIN_AMP_NAME_RE = re.compile(r"&([A-Za-z_][\w-]*)")
PLUGIN_AMP_ARGS_RE = re.compile(r"\(([^()]*)\)")
NUMREF_AMP_RE = re.compile(r"&(#[0-9]+|#[xX][0-9A-Fa-f]+);")


def match_amp_token(text, pos):
    """text[pos] は '&'。&#10進数;・&#x16進数;（数値文字参照）、または
    &name; / &name(args); / &name(args){body}; （インラインプラグイン。
    bodyは波括弧の対応を数える）のどちらかに合うか調べる。

    ("ref", 元の文字列, 終端位置) か
    ("plugin", name, args, body, argsの開始位置, argsの終了位置, 終端位置)
    を返す（argsが無ければ開始・終了位置はNone）。どちらにも合わなければ
    None（呼び出し側は次の '&' を探す。find_annotation_end と同じ考えかた）。
    args の位置は wikilib.pluginlinks（リネーム時の値の書き換え）が使う。"""
    numref = NUMREF_AMP_RE.match(text, pos)
    if numref:
        return ("ref", numref.group(0), numref.end())

    name_m = PLUGIN_AMP_NAME_RE.match(text, pos)
    if not name_m:
        return None
    name = name_m.group(1)
    i = name_m.end()

    args = None
    args_start = args_end = None
    if i < len(text) and text[i] == "(":
        args_m = PLUGIN_AMP_ARGS_RE.match(text, i)
        if not args_m:
            return None
        args = args_m.group(1)
        args_start, args_end = args_m.start(1), args_m.end(1)
        i = args_m.end()

    body = None
    if i < len(text) and text[i] == "{":
        depth = 1
        j = i + 1
        n = len(text)
        while j < n:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body = text[i + 1:j]
                    i = j + 1
                    break
            j += 1
        else:
            return None  # 対応する閉じ括弧が見つからない

    if i < len(text) and text[i] == ";":
        return ("plugin", name, args, body, args_start, args_end, i + 1)
    return None


def find_amp_token(text, pos):
    """text[pos:] の中で、最初に見つかる有効な '&' トークン（数値文字参照・
    インラインプラグイン）の開始位置と結果を返す。無ければ None。
    合わない '&' は無視して次を探す。"""
    search_from = pos
    while True:
        amp = text.find("&", search_from)
        if amp == -1:
            return None
        result = match_amp_token(text, amp)
        if result is not None:
            return amp, result
        search_from = amp + 1
URL_SCHEME_RE = re.compile(r"^(?:https?|ftp|news)://")


_active_extra_rules = None  # 現在処理中の文書に効く「ユーザ定義ルール」「フェイスマーク定義ルール」
_active_interwiki = None    # 現在処理中の文書に効くInterWikiの登録表（wikilib.interwiki）
_active_wikiname = True     # 現在処理中の文書でWikiNameの自動リンクを行うか
_active_allow_html = True   # 現在処理中の文書で生HTMLをそのまま通すか（config: markdown.allow_html）


def _with_wiki_settings(extra_rules, interwiki, wikiname, allow_html, func):
    """Wikiの設定（ユーザ定義ルール・InterWiki・WikiName・生HTMLを許すか）を
    モジュール変数に持たせている間だけ func() を呼ぶ（parse/parse_inline_lines
    の共通部分）。"""
    global _active_extra_rules, _active_interwiki, _active_wikiname, _active_allow_html
    previous = (_active_extra_rules, _active_interwiki, _active_wikiname, _active_allow_html)
    _active_extra_rules = extra_rules
    _active_interwiki = interwiki
    _active_wikiname = wikiname
    _active_allow_html = allow_html
    try:
        return func()
    finally:
        _active_extra_rules, _active_interwiki, _active_wikiname, _active_allow_html = previous


def parse(text, extra_rules=None, interwiki=None, wikiname=True, allow_html=True):
    """PukiWiki記法のテキストをmarkdown-itのトークン列に変換する。

    extra_rules は wikilib.extrarules.load_extra_rules()、interwiki は
    wikilib.interwiki.load_interwiki() で読み込んだもの。省略すると
    （呼び出し側がWikiの設定を持たない場面向けに）その機能無しで解釈する。
    allow_html は config/default.yaml の markdown.allow_html と同じ意味
    （Markdown側と共通の設定。地の文に書いた生のHTMLタグをそのまま通すか）。
    1回のparse呼び出しの間だけモジュール変数に持つ（引用の中を再帰的に
    parse_blocksするときも同じ設定を使うが、インライン解析のあらゆる関数の
    引数にまで持ち回るのは大掛かりすぎるため。このサーバは1リクエストを
    最後まで処理してから次を受けるので、途中で別のリクエストの値と
    混ざる心配はない）。"""
    def run():
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        tokens = parse_blocks(lines, 0)
        assign_heading_ids(tokens)
        append_annotations(tokens)
        return tokens
    return _with_wiki_settings(extra_rules, interwiki, wikiname, allow_html, run)


def parse_inline_lines(text, extra_rules=None, interwiki=None, wikiname=True, allow_html=True):
    """複数行にまたがる生テキストを、1つの `inline` トークンにする
    （中身は `inline_token` が持つ、行ごとのsoftbreak/hardbreakを挟んだ列）。

    引数の意味は parse() と同じ。プラグインが返した文字列を**ブロックとしてで
    なくインラインとして**展開したい場面向け（`wikilib.plugins.
    expand_body`）。見出し・リスト・表のようなブロック要素は
    そもそも1行のインライン記法としては書けないので、対応しない。"""
    def run():
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        return inline_token(lines)
    return _with_wiki_settings(extra_rules, interwiki, wikiname, allow_html, run)


# ---- ブロック要素 -----------------------------------------------------------

def dequote_for_heading(line):
    """見出し・水平線の判定のためだけに、行の先頭にある引用の目印（`>`）を
    取り除く。見出し・水平線は本家の仕様上、いずれの子要素にもならない
    （出現すると、それまで開いていた要素は引用も含めてそこで打ち切られ、
    常にトップレベルへ直接出る）。この判定を `>` 越しでも行えるようにする
    ためのヘルパーで、実際に引用として取り込むかどうかとは無関係。
    目印の直後の空白1つは区切りとして捨てる（append_quote の depth 分の
    処理と同じ約束）。引用の目印が無ければ line をそのまま返す。"""
    m = QUOTE_RE.match(line)
    if not m:
        return line
    rest = m.group(2)
    return rest[1:] if rest.startswith(PRE_PREFIX) else rest


def parse_blocks(lines, offset):
    """行の一覧をブロック要素のトークン列にする。

    offset は lines[0] が元の本文の何行目かを表す（引用の中を再帰的に解析しても
    見出しの行番号がずれないようにするため。行番号はセクション編集が使う）。

    本家PukiWiki（convert_html.php）と同じ「挿入カーソル」方式で組み立てる
    （_Node を参照）。行ごとに単純に「前の行がどうだったか」だけを見る作りでは、
    リストの入れ子や「リストの項目の次の行に他のブロック要素を書くと、その
    項目の子要素になる」という本家の仕様を再現できない
    （例: pukiwikiFormat の #ref パラメタ一覧で、整形済みテキストを挟むと
    リストが分断されていた）。"""
    root = _RootNode()
    cursor = root
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].rstrip()

        if line.startswith(COMMENT_PREFIX):
            i += 1  # コメント行は出力しない
            continue

        if not line.strip():
            cursor = root  # 空行でいったんトップへ戻る（本家と同じ）
            i += 1
            continue

        if _active_allow_html and line.startswith("<"):
            end_re = _html_block_end(line)
            if end_re is not None:
                t = []
                i = append_html_block(t, lines, i, offset, end_re)
                cursor = cursor.add(_OpaqueNode(t))
                continue

        m = PLUGIN_BLOCK_RE.match(line)
        if m:
            t = []
            i = append_plugin_block(t, lines, i, offset, m)
            cursor = cursor.add(_OpaqueNode(t))
            continue

        # 見出し・水平線は引用の目印（`>`）越しでも見出し・水平線として扱う
        # （いずれの子要素にもならないため、引用の中に書いても引用の子には
        # せず、引用ごとそこで打ち切ってトップレベルへ直接出す。
        # dequote_for_heading は目印を剥がすだけで、実際に引用として
        # 取り込むかどうかとは無関係）
        dequoted = dequote_for_heading(line)

        if HR_RE.match(dequoted):
            hr = Token("hr", "hr", 0, block=True, markup=dequoted)
            hr.map = [offset + i, offset + i + 1]
            # 見出しと同じく、常にトップレベルへ直接付ける（入れ子にしない）
            cursor = root.insert(_HeadingLikeNode([hr]))
            i += 1
            continue

        m = HEADING_RE.match(dequoted)
        if m:
            t = []
            append_heading(t, m.group(1), m.group(2), offset + i)
            # 見出しは常にトップレベルへ直接付ける。途中のリストや引用などの
            # 入れ子を気にせず必ずここで区切られる（本家の仕様）
            cursor = root.insert(_HeadingLikeNode(t))
            i += 1
            continue

        m = ALIGN_RE.match(line)
        if m:
            t = []
            append_paragraph(t, [m.group(2).strip()], offset + i,
                             align=m.group(1).lower())
            cursor = cursor.add(_OpaqueNode(t))
            i += 1
            continue

        if lines[i].startswith(PRE_PREFIX):
            body = []
            start_i = i
            while i < n and lines[i].startswith(PRE_PREFIX):
                body.append(lines[i][len(PRE_PREFIX):])
                i += 1
            cursor = cursor.add(_PreNode(body, offset + start_i, offset + i))
            continue

        m = LIST_RE.match(line)
        if m:
            marker = m.group(1)
            tag = "ul" if marker[0] == "-" else "ol"
            level = min(3, len(marker))
            text = m.group(2).strip()
            line_no = offset + i
            i += 1
            if text == "~" or text.startswith("~"):
                # "-~" … 項目自身は文字を持たず、続く段落を子要素にする
                # （地の文の頭に付ける "~"＝段落の明示と同じ目印の流用）
                container = _ListContainerNode(tag, "li", level, "", line_no)
                item = container.children[0]
                first = text[1:].strip()
                para_lines = [first] if first else []
                while i < n and _is_plain_content_line(lines[i]):
                    para_lines.append(lines[i].rstrip())
                    i += 1
                if para_lines:
                    para = _ParagraphNode(line_no)
                    _Node.insert(para, _InlineNode(para_lines, line_no))
                    container.last = item.insert(para)
                cursor = cursor.add(container)
                continue

            container = _ListContainerNode(tag, "li", level, text, line_no)
            cursor = cursor.add(container)
            continue

        if QUOTE_RE.match(line):
            t = []
            i = append_quote(t, lines, i, offset)
            cursor = cursor.add(_OpaqueNode(t))
            continue

        if TABLE_RE.match(line):
            t = []
            i = append_table(t, lines, i, offset)
            cursor = cursor.add(_OpaqueNode(t))
            continue

        if line.startswith(CSV_TABLE_PREFIX):
            t = []
            i = append_csv_table(t, lines, i, offset)
            cursor = cursor.add(_OpaqueNode(t))
            continue

        if DEFLIST_RE.match(line):
            t = []
            i = append_deflist(t, lines, i, offset)
            cursor = cursor.add(_OpaqueNode(t))
            continue

        # ここまでのどれにも当てはまらない、ただの地の文。"~" で始まる行は
        # 段落の明示（目印そのものは本文に出さない）で、リストの項目の中では
        # 独立した段落（子要素）を作る意味を持つ（_ListElementNode.can_contain）
        text = line[1:].lstrip() if line.startswith("~") else line
        inline = _InlineNode([text], offset + i)
        if line.startswith("~"):
            para = _ParagraphNode(offset + i)
            _Node.insert(para, inline)
            cursor = cursor.add(para)
        else:
            cursor = cursor.add(inline)
        i += 1

    return root.to_tokens()


class _Node:
    """本家 convert_html.php の Element/canContain/add/insert の移植。

    「直前に挿入した要素」を指すカーソルを1行ごとに動かしながら、その要素が
    「この行の内容を自分の中に含められるか」（can_contain）を見て、含められ
    なければ親へ委ねる（add）。これにより、リストの入れ子や「リストの項目の
    次の行に他のブロック要素を書くと、その項目の子要素になる」（本家の仕様）
    を再現する。HTML文字列の代わりに markdown-it のトークン列を組み立てる
    点だけが本家と違う（to_tokens）。"""

    def __init__(self):
        self.parent = None
        self.children = []
        self.last = self

    def set_parent(self, parent):
        self.parent = parent

    def add(self, obj):
        if self.can_contain(obj):
            return self.insert(obj)
        return self.parent.add(obj)

    def insert(self, obj):
        obj.set_parent(self)
        self.children.append(obj)
        self.last = obj.last
        return self.last

    def can_contain(self, obj):
        return True

    def to_tokens(self):
        out = []
        for child in self.children:
            out.extend(child.to_tokens())
        return out


class _RootNode(_Node):
    """文書全体、または引用の中身1つぶんのトップレベル。地の文（_InlineNode）が
    直接来たら、段落として包む（本家の Body::insert 相当。リストの項目の中では
    包まずそのまま持つので、同じ _InlineNode でも場所によって扱いが変わる）。"""

    def insert(self, obj):
        if isinstance(obj, _InlineNode):
            para = _ParagraphNode(obj.line_no)
            _Node.insert(para, obj)
            obj = para
        return _Node.insert(self, obj)


class _InlineNode(_Node):
    """地の文1行ぶん。連続する行はここに合流する（本家の Inline）。
    合流した結果は、段落（<p>）にもリスト項目自身の文字にもなりうる
    （包むかどうかは挿し込まれた側が決める。_RootNode/_ParagraphNode を参照）。"""

    def __init__(self, lines, line_no):
        super().__init__()
        self.lines = list(lines)
        self.line_no = line_no

    def can_contain(self, obj):
        return isinstance(obj, _InlineNode)

    def insert(self, obj):
        self.lines.extend(obj.lines)
        return self

    def to_tokens(self):
        return [inline_token(self.lines)]


class _ParagraphNode(_Node):
    """独立した段落（`<p>`）。ルート直下の地の文のほか、リスト項目で `~` を
    使って明示的に子要素にした段落もこの形になる。

    **地の文（_InlineNode）しか子にしない。** これが無いと、段落のあとに
    続く別のブロック（次のリストの項目など）までここへ紛れ込んでしまう
    （本家の Paragraph::canContain も Inline だけを受け付ける）。"""

    def __init__(self, line_no):
        super().__init__()
        self.line_no = line_no

    def can_contain(self, obj):
        return isinstance(obj, _InlineNode)

    def to_tokens(self):
        inline = self.children[0] if self.children else _InlineNode([""], self.line_no)
        open_token = Token("paragraph_open", "p", 1, block=True)
        open_token.map = [inline.line_no, inline.line_no + len(inline.lines)]
        return ([open_token] + inline.to_tokens()
                + [Token("paragraph_close", "p", -1, block=True)])


class _HeadingLikeNode(_Node):
    """見出し・水平線。本家と同じく、何が来ても自分の中には入れない
    （can_contain は常にFalse）。挿す側（root）は常にトップレベルへ直接
    付けるので、それまでどれだけ深く入れ子になっていても、見出し・水平線の
    あとは必ずそこで区切られる。"""

    def __init__(self, tokens):
        super().__init__()
        self._tokens = tokens

    def can_contain(self, obj):
        return False

    def to_tokens(self):
        return self._tokens


class _OpaqueNode(_Node):
    """引用・表・CSV形式の表・定義リスト・ブロックプラグイン・寄せ指定など、
    それ自身の関数が複数行をまとめて読み切り、完結したトークン列を返してくる
    もの。それらの記法どうしの連続吸収は各関数が内部ですでに行っているため、
    ここでは _HeadingLikeNode と同じく「これ以上何も受け付けない」だけでよい
    （リスト項目の子要素として取り込まれる余地は can_contain の側で判定される
    ので、ここが常にFalseでも問題ない）。"""

    def __init__(self, tokens):
        super().__init__()
        self._tokens = tokens

    def can_contain(self, obj):
        return False

    def to_tokens(self):
        return self._tokens


class _PreNode(_Node):
    """整形済みテキスト（`<pre>`）。連続する行はここに合流する（本家の Pre）。"""

    def __init__(self, body_lines, line_no, end_line):
        super().__init__()
        self.body = list(body_lines)
        self.line_no = line_no
        self.end_line = end_line

    def can_contain(self, obj):
        return isinstance(obj, _PreNode)

    def insert(self, obj):
        self.body.extend(obj.body)
        self.end_line = obj.end_line
        return self

    def to_tokens(self):
        token = Token("code_block", "code", 0, block=True,
                      content="\n".join(self.body) + "\n")
        token.map = [self.line_no, self.end_line]
        return [token]


class _ListElementNode(_Node):
    """`<li>`。本文（インライン）のほか、他のブロック要素も子要素にできる
    （本家の仕様）。ただし、より深いリストでなければ、別のリストを子には
    しない（同じ深さ・より浅いリストは、いったんここで打ち切って親へ委ねる。
    ListContainer 側でまとめ直される）。"""

    def __init__(self, level, tag, line_no=None):
        super().__init__()
        self.level = level
        self.tag = tag
        self.line_no = line_no

    def can_contain(self, obj):
        if isinstance(obj, _ListContainerNode):
            return obj.level > self.level
        return True

    def to_tokens(self):
        open_token = Token("list_item_open", self.tag, 1, block=True)
        if self.line_no is not None:
            open_token.map = [self.line_no, self.line_no + 1]
        out = [open_token]
        out.extend(_Node.to_tokens(self))
        out.append(Token("list_item_close", self.tag, -1, block=True))
        return out


class _ListContainerNode(_Node):
    """`<ul>` / `<ol>`。`-`・`+` の1行から作る、その場限りの器。実際に文書へ
    挿入されるとき（insert）に、本家と同じ2つのことをする。

    - 深さ・種類が同じ既存のリストがあれば、そちらへ項目を合流させる
      （新しく `<ul>` を作らず、1つの `<ul>` の中に `<li>` を並べる）。
    - **項目名（本文）が空だった行（`-` だけ）からは、新しい `<li>` を
      作らない。** カーソルだけを「直前の要素の親」へ戻す（本家の
      BugTrack/524）。空の弾（●）が見た目に出ないようにするための特例で、
      副作用として「そのあとに続くブロックは、区切り直前の要素の子として
      続けて拾われる」という挙動になる
      （pukiwikiFormat の #ref パラメタ一覧の `left`/`center`/`right` が
      これにあたる）。"""

    def __init__(self, tag, item_tag, level, text, line_no):
        super().__init__()
        self.tag = tag
        self.item_tag = item_tag
        self.level = level
        self.line_no = line_no
        item = _ListElementNode(level, item_tag, line_no)
        _Node.insert(self, item)
        if text:
            inline = _InlineNode([text], line_no)
            self.last = item.insert(inline)

    def can_contain(self, obj):
        if not isinstance(obj, _ListContainerNode):
            return True
        return self.tag == obj.tag and self.level == obj.level

    def insert(self, obj):
        if not isinstance(obj, _ListContainerNode) or obj.tag != self.tag:
            self.last = self.last.insert(obj)
            return self.last

        only_item = obj.children[0]
        if len(obj.children) == 1 and not only_item.children:
            # 空の項目。新しい<li>は作らず、直前の要素の親へ戻るだけ
            return self.last.parent

        for child in obj.children:
            _Node.insert(self, child)
        return self.last

    def to_tokens(self):
        open_token = Token(self.tag + "_open", self.tag, 1, block=True, markup=self.tag)
        if self.line_no is not None:
            open_token.map = [self.line_no, self.line_no + 1]
        out = [open_token]
        out.extend(_Node.to_tokens(self))
        out.append(Token(self.tag + "_close", self.tag, -1, block=True))
        return out


def append_paragraph(tokens, lines, line_no, align=None):
    """段落を1つ追加する。align は LEFT:/CENTER:/RIGHT: 用の寄せかた。"""
    open_token = Token("paragraph_open", "p", 1, block=True)
    if align:
        open_token.attrSet("style", "text-align:" + align)
    open_token.map = [line_no, line_no + len(lines)]
    tokens.append(open_token)
    tokens.append(inline_token(lines))
    tokens.append(Token("paragraph_close", "p", -1, block=True))


def append_heading(tokens, marker, text, line_no):
    """見出しを追加する。`*`→h2、`**`→h3、`***`→h4（タグを決めた理由はこのファイルの冒頭）。

    行末の `[#anchor]` は見出しのidになる（idの確定は assign_heading_ids で行う。
    同じ見出しが複数あったときの重複解消を、まとめて済ませるため）。"""
    anchor = None
    m = HEADING_ANCHOR_RE.search(text)
    if m:
        anchor = m.group(1)
        text = text[: m.start()]
    level = len(marker) + 1
    open_token = Token("heading_open", "h%d" % level, 1, block=True, markup=marker)
    open_token.map = [line_no, line_no + 1]
    open_token.meta = {"anchor": anchor}
    tokens.append(open_token)
    tokens.append(inline_token([text.strip()]))
    tokens.append(Token("heading_close", "h%d" % level, -1, block=True))


def append_pre(tokens, lines, i, offset):
    """行頭が半角空白の行を集めて整形済みテキストにする。次に読む行を返す。"""
    body = []
    start = i
    while i < len(lines) and lines[i].startswith(PRE_PREFIX):
        body.append(lines[i][len(PRE_PREFIX):])
        i += 1
    token = Token("code_block", "code", 0, block=True, content="\n".join(body) + "\n")
    token.map = [offset + start, offset + i]
    tokens.append(token)
    return i


def append_quote(tokens, lines, i, offset):
    """引用を追加する。中身は再帰的に解析するので、引用の中に見出しやリストも書ける。

    ただし見出し・水平線はいずれの子要素にもならない（本家の仕様）ため、
    引用の目印越しでもそれらと判定できる行が来たら、そこで引用を打ち切る
    （呼び出し元の parse_blocks が、打ち切ったあとの行を改めて見出し・水平線
    として拾い、トップレベルへ直接出す。この関数の最初の1行がすでに
    見出し・水平線であることは無い。呼び出し元がその場合はそもそもこの
    関数を呼ばないため）。

    `>>` のような深い引用は、目印を1段だけ外して再帰する。外した結果まだ `>` が
    残っていれば、その中で改めて引用として解釈され、入れ子の構造になる。"""
    depth = len(QUOTE_RE.match(lines[i].rstrip()).group(1))
    start = i
    inner = []
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            break
        m = QUOTE_RE.match(line)
        if not m:
            break
        dequoted = dequote_for_heading(line)
        if HR_RE.match(dequoted) or HEADING_RE.match(dequoted):
            break  # 見出し・水平線は引用の子にしない。ここで引用を打ち切る
        # 自分より浅い引用が来た場合に備え、外す数はその行の目印の数までにとどめる。
        # 目印の直後の空白1つは区切りとして捨てる（残すと行頭が空白の行、つまり
        # 整形済みテキストとして解釈されてしまう）。
        text = line[min(depth, len(m.group(1))):]
        inner.append(text[1:] if text.startswith(PRE_PREFIX) else text)
        i += 1

    open_token = Token("blockquote_open", "blockquote", 1, block=True, markup=">" * depth)
    open_token.map = [offset + start, offset + i]
    tokens.append(open_token)
    tokens.extend(parse_blocks(inner, offset + start))
    tokens.append(Token("blockquote_close", "blockquote", -1, block=True))
    return i


def append_tight_paragraph(tokens, lines, line_no):
    """リスト項目・定義リストの説明文の中身。`<p>` で包まずに文字が並ぶよう、
    段落を hidden にする（markdown-itが詰まったリストを描くときと同じ作り）。

    lines は1行の文字列でも、複数行のリストでもよい（定義リストの説明文は
    複数行にわたれるため。append_deflist を参照）。"""
    if isinstance(lines, str):
        lines = [lines]
    open_token = Token("paragraph_open", "p", 1, block=True, hidden=True)
    open_token.map = [line_no, line_no + len(lines)]
    tokens.append(open_token)
    tokens.append(inline_token(lines))
    tokens.append(Token("paragraph_close", "p", -1, block=True, hidden=True))


# ---- 表組み -----------------------------------------------------------------
# 本家には表の書きかたが2つある。`|セル|セル|` は結合や書式指定まで細かく指定できる
# もので、`,セル,セル` はCSVをそのまま貼れる簡易版。どちらもトークンの形は
# markdown-itの表（table/thead/tbody/tr/th/td）に揃えてあるので、Markdownで書いた
# 表と同じHTMLになり、テーマのCSSもそのまま効く。

def append_table(tokens, lines, i, offset):
    """`|セル|セル|` の表を追加する。次に読む行を返す。

    行末の1文字が行の種類で、`h` は見出し行（thead）、`f` はフッタ行（tfoot）、
    `c` は書式指定だけの行（表には出さず、その列の既定の書式になる）。
    **`h` は置き場所（thead）を決めるだけで、セルを th にはしない**（本家と同じ）。
    列数が変わったらそこで表を切る（本家と同じ。列数の違う行を同じ表に混ぜると、
    結合の位置が縦に揃わなくなるため）。"""
    rows = []
    start = i
    columns = None
    while i < len(lines):
        m = TABLE_RE.match(lines[i].rstrip())
        if not m:
            break
        cells = m.group(1).split("|")
        if columns is not None and len(cells) != columns:
            break
        columns = len(cells)
        rows.append({"kind": (m.group(2) or "").lower(),
                     "cells": [parse_cell(text) for text in cells],
                     "line": offset + i})
        i += 1
    append_table_tokens(tokens, rows, offset + start, offset + i)
    return i


def parse_cell(text):
    """`|…|` の表のセル1つを解釈する。

    見るものは3つ。結合の目印（`>` は右のセルと、`~` は上のセルと結合）、
    見出しセルの目印（先頭の `~`）、書式指定（`CENTER:` など。重ねて書ける）。
    目印を書式指定より先に外すのは本家と同じ順で、`|~CENTER:字|` のように
    目印→書式の順に書く。セルの前後の空白は無視する（`| CENTER:字 |` のように
    読みやすく書いても効くようにするため）。"""
    text = text.strip()
    if text == ">":
        return {"merge": "right"}
    if text == "~":
        return {"merge": "up"}
    header = text.startswith("~")
    if header:
        text = text[1:].strip()
    style = {}
    while True:
        m = CELL_STYLE_RE.match(text)
        if not m:
            break
        if m.group(1):
            style["text-align"] = m.group(1).lower()
        elif m.group(3):
            style["background-color" if m.group(2) else "color"] = m.group(3)
        else:
            style["font-size"] = m.group(4) + "px"
        text = m.group(5).strip()
    return {"merge": None, "header": header, "style": style, "text": text}


def append_table_tokens(tokens, rows, start_line, end_line):
    """解釈済みの行から表のトークンを組み立てる。

    `h`→thead、`f`→tfoot、残り→tbody にまとめ、thead・tbody・tfoot の順に出す
    （HTMLでtfootを置ける位置に合わせるため。書いた順とは関係なくこの順になる）。"""
    column_styles = {}
    for row in rows:
        if row["kind"] == "c":
            for column, cell in enumerate(row["cells"]):
                if not cell["merge"]:
                    column_styles[column] = cell["style"]
    if not any(row["kind"] != "c" for row in rows):
        return  # 書式指定行だけ。表として出すものが無い

    open_token = Token("table_open", "table", 1, block=True)
    open_token.map = [start_line, end_line]
    tokens.append(open_token)
    for kind, tag in (("h", "thead"), ("", "tbody"), ("f", "tfoot")):
        group = [row for row in rows if row["kind"] == kind]
        if not group:
            continue
        tokens.append(Token(tag + "_open", tag, 1, block=True))
        append_table_rows(tokens, group, column_styles)
        tokens.append(Token(tag + "_close", tag, -1, block=True))
    tokens.append(Token("table_close", "table", -1, block=True))


def append_table_rows(tokens, rows, column_styles):
    """thead / tbody / tfoot の中身。

    **見出しセル（th）にするかを決めるのは、セル自身の `~` だけ。** 行末の `h` は
    その行を thead へ入れるだけで、セルは td のままにする（本家がそうなっている）。
    `|~品名|~数|h` のように、見出しにしたいセルには1つずつ `~` を付ける。

    縦の結合（`~`）は、その列に最後に置いたセルの rowspan を足していく。
    同じ列に `~` が続けば、そのセルが2行・3行…と伸びる。"""
    owners = {}  # 列の位置 → その列に最後に置いたセルの開きトークン
    for row in rows:
        row_open = Token("tr_open", "tr", 1, block=True)
        row_open.map = [row["line"], row["line"] + 1]
        tokens.append(row_open)
        column = 0
        for cell, colspan in placed_cells(row["cells"]):
            if cell["merge"] == "up":
                owner = owners.get(column)
                if owner is not None:
                    owner.attrSet("rowspan", str(int(owner.attrGet("rowspan") or 1) + 1))
                    column += 1
                    continue
                cell = blank_cell()  # 上にセルが無い。結合できないので空のセルにする
            tag = "th" if cell["header"] else "td"
            style = dict(column_styles.get(column, {}))
            style.update(cell["style"])
            cell_open = Token(tag + "_open", tag, 1, block=True)
            if colspan > 1:
                cell_open.attrSet("colspan", str(colspan))
            if style:
                cell_open.attrSet("style", ";".join("%s:%s" % kv for kv in style.items()))
            tokens.append(cell_open)
            tokens.append(inline_token([cell["text"]]))
            tokens.append(Token(tag + "_close", tag, -1, block=True))
            owners[column] = cell_open
            column += colspan
        tokens.append(Token("tr_close", "tr", -1, block=True))


def placed_cells(cells):
    """行のセルを [(セル, colspan), …] にする。

    `>` のセルは、その右にあるセルに吸収される（`|>|>|字|` なら3列ぶんの1セル）。
    右に相手がいないまま行が終わったら、その`>`は空のセルとして置く。"""
    placed = []
    colspan = 1
    for cell in cells:
        if cell["merge"] == "right":
            colspan += 1
            continue
        placed.append((cell, colspan))
        colspan = 1
    if colspan > 1:
        placed.append((blank_cell(), colspan - 1))
    return placed


def blank_cell():
    return {"merge": None, "header": False, "style": {}, "text": ""}


def append_csv_table(tokens, lines, i, offset):
    """`,セル,セル` の表（CSV形式）を追加する。次に読む行を返す。

    表計算ソフトから貼ったCSVをそのまま表にするためのもので、見出し行や結合の
    細かい指定は無い代わりに、セルの前後の空白で寄せかたが決まる。
    `|…|` の表と同じく、列数が変わったらそこで表を切る。

    行末の空白は落とさない（最後のセルの寄せかたに使われるため）。"""
    rows = []
    start = i
    columns = None
    while i < len(lines):
        line = lines[i]
        if not line.startswith(CSV_TABLE_PREFIX):
            break
        cells = split_csv(line[len(CSV_TABLE_PREFIX):])
        if columns is not None and len(cells) != columns:
            break
        columns = len(cells)
        rows.append({"cells": cells, "line": offset + i})
        i += 1
    append_csv_table_tokens(tokens, rows, offset + start, offset + i)
    return i


def split_csv(text):
    """CSV形式の1行をセルに分ける。

    `"…"` で囲んだ中のカンマは区切りにならず、囲みの中の `""` は `"` 1つになる
    （表計算ソフトが書き出すCSVと同じ約束）。囲みとみなすのはセルの先頭に来た
    `"` だけで、それ以外の `"` はただの文字として扱う（`15"モニタ` のような
    書きかたで字が落ちないように）。"""
    cells = []
    cell = []
    quoted = False  # いま囲みの中か
    pos = 0
    while pos < len(text):
        char = text[pos]
        if quoted:
            if char != '"':
                cell.append(char)
            elif text.startswith('""', pos):
                cell.append('"')
                pos += 1
            else:
                quoted = False
        elif char == '"' and not cell:
            quoted = True
        elif char == ",":
            cells.append("".join(cell))
            del cell[:]
        else:
            cell.append(char)
        pos += 1
    cells.append("".join(cell))
    return cells


def append_csv_table_tokens(tokens, rows, start_line, end_line):
    """CSV形式の表のトークンを組み立てる。見出し行は無いので中身は全部tbody。"""
    if not rows:
        return
    open_token = Token("table_open", "table", 1, block=True)
    open_token.map = [start_line, end_line]
    tokens.append(open_token)
    tokens.append(Token("tbody_open", "tbody", 1, block=True))
    for row in rows:
        row_open = Token("tr_open", "tr", 1, block=True)
        row_open.map = [row["line"], row["line"] + 1]
        tokens.append(row_open)
        for text, align, colspan in csv_cells(row["cells"]):
            cell_open = Token("td_open", "td", 1, block=True)
            if colspan > 1:
                cell_open.attrSet("colspan", str(colspan))
            if align != "left":
                cell_open.attrSet("style", "text-align:" + align)
            tokens.append(cell_open)
            tokens.append(inline_token([text]))
            tokens.append(Token("td_close", "td", -1, block=True))
        tokens.append(Token("tr_close", "tr", -1, block=True))
    tokens.append(Token("tbody_close", "tbody", -1, block=True))
    tokens.append(Token("table_close", "table", -1, block=True))


def csv_cells(cells):
    """CSV形式の1行を [(本文, 寄せかた, colspan), …] にする。

    `==` のセルは左のセルにつながる（結合したセルは中央寄せになる）。"""
    placed = []
    index = 0
    while index < len(cells):
        text, align = cells[index].strip(), csv_align(cells[index])
        colspan = 1
        while index + 1 < len(cells) and cells[index + 1].strip() == CSV_MERGE_MARK:
            colspan += 1
            index += 1
        placed.append((text, "center" if colspan > 1 else align, colspan))
        index += 1
    return placed


def csv_align(cell):
    """CSV形式のセルの寄せかた。前後を空白で挟めば中央、前だけなら右、それ以外は左。"""
    if not cell.strip():
        return "left"
    if cell[0].isspace():
        return "center" if cell[-1].isspace() else "right"
    return "left"


# ---- 定義リスト --------------------------------------------------------------

def append_deflist(tokens, lines, i, offset):
    """`:項目名|説明文` の定義リストを追加する。次に読む行を返す。

    連続する行を1つの `<dl>` にまとめる（本家と同じ）。トークンの形はMarkdown側の
    定義リスト（Pandoc形式の `用語` / `: 説明`）と同じ dl/dt/dd に揃えてあるので、
    テーマのCSSはそのまま両方に効く（このシステムではMarkdown側の記法そのものは
    意図的に無効にしてあるが、出力の形だけ合わせておくことで、あとでテーマ側に
    CSSを1種類だけ用意してもらえばよいようにしている）。

    項目名・説明文はインライン要素で書く（本家の仕様）。**説明文は複数行に
    わたれる。** 次の行が新しい項目（`:...|...`）や空行、他のブロック記法
    でない限り、続く行をそのまま同じ説明文の続きとして拾う（ふつうの段落が
    複数行を1つにまとめるのと同じ扱い）。

    **項目名を省いた行（`:|説明文`）を続けて書くと、直前の項目と `<dt>` を
    共有したまま、もう1つ `<dd>` を追加できる**（本家の仕様）。

    **説明文の頭に `~` を書くと、その説明文は段落（`<p>`）になる**
    （`:用語|~説明文`。本家の Factory_Inline と同じ扱い）。ふつうの説明文は
    `<dd>` の中に文字がそのまま並ぶ（`<p>` で包まない）ので、段落として
    余白を取りたいときや、複数の段落に分けたいときにこちらを使う。
    リストの `-~` と同じ目印の流用で、`~` そのものは本文に出ない。"""
    start = i
    entries = []  # [(term, [説明文の行, ...], line_no, 段落にするか), ...]
    while i < len(lines):
        m = DEFLIST_RE.match(lines[i].rstrip())
        if not m:
            break
        term = m.group(1).strip()
        line_no = offset + i
        first = m.group(2).strip()
        # 頭の "~" は「この説明文は段落」という目印。目印そのものは残さない
        as_paragraph = first.startswith("~")
        if as_paragraph:
            first = first[1:].strip()
        desc_lines = [first] if first or not as_paragraph else []
        i += 1
        while i < len(lines) and _is_plain_content_line(lines[i]):
            desc_lines.append(lines[i].rstrip())
            i += 1
        entries.append((term, desc_lines, line_no, as_paragraph))

    open_token = Token("dl_open", "dl", 1, block=True)
    open_token.map = [offset + start, offset + i]
    tokens.append(open_token)
    for index, (term, desc_lines, line_no, as_paragraph) in enumerate(entries):
        # 項目名が書かれていれば新しい <dt> を始める。先頭の項目は、
        # 項目名を省いていても（空の）<dt> を1つ持たせておく
        if term or index == 0:
            dt_open = Token("dt_open", "dt", 1, block=True)
            dt_open.map = [line_no, line_no + 1]
            tokens.append(dt_open)
            tokens.append(inline_token([term]))
            tokens.append(Token("dt_close", "dt", -1, block=True))

        dd_open = Token("dd_open", "dd", 1, block=True)
        dd_open.map = [line_no, line_no + len(desc_lines)]
        tokens.append(dd_open)
        if desc_lines:
            # "~" が付いていれば <p> で包む。付いていなければ、これまでどおり
            # 文字がそのまま並ぶ（hidden な段落）
            add = append_paragraph if as_paragraph else append_tight_paragraph
            add(tokens, desc_lines, line_no)
        tokens.append(Token("dd_close", "dd", -1, block=True))
    tokens.append(Token("dl_close", "dl", -1, block=True))
    return i


def _starts_block(line):
    """行が、何らかのブロック記法の始まりになっているかどうか（解析はしない、
    見分けるだけ）。段落として拾ってよい「ただの地の文」かどうかを判定する
    材料として使う（_is_plain_content_line から呼ばれる）。

    parse_blocks の行の見分けかたと同じ条件を並べている。2か所に分かれて
    食い違わないよう、本当は共有したいところだが、parse_blocks 側は
    「解析してカーソルに挿す」ところまで一体になっているため、
    ここでは判定だけを独立させてある。"""
    stripped = line.rstrip()
    if stripped.startswith(COMMENT_PREFIX):
        return True
    if PLUGIN_BLOCK_RE.match(stripped):
        return True
    if HR_RE.match(stripped):
        return True
    if HEADING_RE.match(stripped):
        return True
    if ALIGN_RE.match(stripped):
        return True
    if stripped.startswith(PRE_PREFIX):
        return True
    if LIST_RE.match(stripped):
        return True
    if QUOTE_RE.match(stripped):
        return True
    if TABLE_RE.match(stripped):
        return True
    if stripped.startswith(CSV_TABLE_PREFIX):
        return True
    if DEFLIST_RE.match(stripped):
        return True
    return False


def _is_plain_content_line(line):
    """段落の続きとして拾ってよい行か（空行でも、他のブロック記法の
    始まりでもない、ただの地の文）。

    定義リストの説明文の続き（append_deflist）、リスト項目の `-~` に続く
    段落（append_list）など、複数の場所で同じ判定を使う。"""
    stripped = line.rstrip()
    if not stripped.strip():
        return False
    return not _starts_block(stripped)


def append_plugin_block(tokens, lines, i, offset, m):
    """ブロックプラグイン（`#name(引数){{ … }}`）を追加する。次に読む行を返す。

    トークンの形はMarkdown側（plugins.plugin_block_rule）と同じにしてあるので、
    レンダリング規則も引数の解釈もそのまま共通のものが使われる。"""
    name, args, fence, oneline = m.group(1), m.group(2), m.group(3), m.group(4)
    body = oneline
    start = i

    if fence:
        # 開いた波括弧と同じ数以上の閉じ括弧が現れるまでが本文
        close_re = re.compile(r"^\}{%d,}\s*$" % len(fence))
        j = i + 1
        collected = []
        while j < len(lines) and not close_re.match(lines[j].rstrip()):
            collected.append(lines[j])
            j += 1
        if j >= len(lines):
            # 閉じられていない。プラグインとして扱わず、ただの段落にする
            append_paragraph(tokens, [lines[i].rstrip()], offset + i)
            return i + 1
        body = "\n".join(collected)
        i = j

    token = Token("plugin_block", "div", 0, block=True)
    token.meta = {"name": name, "args": args or "", "body": body}
    token.map = [offset + start, offset + i + 1]
    tokens.append(token)
    return i + 1


def assign_heading_ids(tokens):
    """見出しにidを振る。

    振りかたはMarkdown側（mdit_py_plugins の anchors）と同じ関数を使う。
    idは目次のリンク先だけでなくページ内アンカーやセクション編集の宛先にも使うため、
    記法が違っても同じ見出しからは同じidが得られるようにしておく。
    `[#anchor]` で明示されていればそちらを優先する。"""
    slugs = set()
    for i, token in enumerate(tokens):
        if token.type != "heading_open" or i + 1 >= len(tokens):
            continue
        explicit = (token.meta or {}).get("anchor")
        if not explicit:
            children = tokens[i + 1].children or []
            title = "".join(c.content for c in children if c.type in ("text", "code_inline"))
            explicit = slugify(title)
        if explicit:  # 記号だけの見出しなどでidが空になる場合は、振らずにおく
            token.attrSet("id", unique_slug(explicit, slugs))


# ---- インライン要素 ---------------------------------------------------------

def inline_token(lines):
    """複数行をまとめて1つの inline トークンにする。

    行末の `~` はそこで改行（hardbreak）。それ以外の行の変わり目は、Markdownと
    同じくsoftbreakにする（HTMLとしては改行文字になり、表示上はつながる）。
    content に元の文字列を入れておくのは、目次が見出しの文字列をここから取るため。"""
    children = []
    previous_hard = False
    for i, line in enumerate(lines):
        hard = line.endswith("~")
        text = line[:-1] if hard else line
        if i:
            children.append(Token("hardbreak" if previous_hard else "softbreak", "br", 0))
        children.extend(parse_inline(text))
        previous_hard = hard
    return Token("inline", "", 0, children=children, content="\n".join(lines))


def parse_inline(text, _rule_depth=0):
    """1行ぶんのインライン要素を子トークンの一覧にする。

    `_rule_depth` は定義ルール（extrarules）の入れ子の深さで、内部用。
    ルールが捕捉した部分をこの関数で解釈し直すとき（下の extra の処理）に
    1つ足して渡す。`(foo)` を `<i>\\1</i>` に置き換える定義のように、捕捉した
    部分にまた同じルールが当たる定義でも、上限で止まる。"""
    tokens = []
    buffer = []

    def flush():
        if buffer:
            tokens.append(Token("text", "", 0, content="".join(buffer)))
            del buffer[:]

    pos = 0
    while True:
        # 「ユーザ定義ルール」「フェイスマーク定義ルール」（wikilib.extrarules）は
        # 管理者が明示的に書いた定義なので、他の記法と同じ位置から始まる場合は
        # 最優先で使う（例: facemark_rules に "&smile;" を定義していれば、
        # HTML5の実体参照名との衝突判定より先にそちらが勝つ）。
        extra = (match_extra_rule(_active_extra_rules, text, pos)
                if _active_extra_rules and _rule_depth <= MAX_NEST_DEPTH else None)
        if extra is not None:
            extra_start, extra_parts, extra_end = extra
        else:
            extra_start = -1

        # 注釈 "((…))" の開始は、他の記法とは別に探す（find_annotation_end の
        # 説明を参照）。"&…"（プラグイン・数値文字参照）も同じ理由で別に探す
        # （find_amp_token参照）。同じ位置から始まる記法は無いので、
        # 最も手前のものから順に使う。
        ann_start = text.find("((", pos)
        amp_found = find_amp_token(text, pos)
        amp_start = amp_found[0] if amp_found else -1
        m = INLINE_RE.search(text, pos)

        # 生のHTMLタグ（1つで完結するもの）は、他の候補のうち最も手前の
        # ものより前にある場合だけ拾う（探索の打ち切り位置を決めるため、
        # 他の候補を先に集計してから探す。amp_start より後ろにしか見当たら
        # ないタグを拾ってしまうと、amp_start側の処理を素通りさせてしまう）。
        # プラグインが返した文字列（例: note.py の `<span class="...">`）を
        # 展開のために再度パースし直したとき、タグごとエスケープされて
        # しまわないようにするための処理。allow_html が偽なら探さない
        # （不特定多数が書く運用の安全側の設定）。
        provisional = min((x for x in (extra_start, ann_start, amp_start,
                                       m.start() if m else -1) if x != -1),
                          default=-1)
        html_m = None
        html_start = -1
        if _active_allow_html:
            search_from = pos
            while True:
                lt = text.find("<", search_from)
                if lt == -1 or (provisional != -1 and lt >= provisional):
                    break
                candidate = HTML_INLINE_RE.match(text, lt)
                if candidate:
                    html_m = candidate
                    html_start = lt
                    break
                search_from = lt + 1

        # 以降の判定に使う「いまのところの最有力候補の開始位置」。
        # -1（見つからない）は比較から除く
        earliest = min((x for x in (extra_start, ann_start, amp_start,
                                    m.start() if m else -1,
                                    html_start if html_m is not None else -1)
                        if x != -1),
                       default=-1)

        if extra_start != -1 and extra_start == earliest:
            buffer.append(text[pos:extra_start])
            flush()
            # html_inline ではなく専用の extra_rule_html で受ける（render_extra_rule_html
            # 参照）。html_inline にすると、読み手が本文に直接書いた生HTMLと
            # 同じものとしてhtmlpolicyの検閲（allow_html）にかかってしまい、
            # `pukiwiki.allow_html` が既定のfalseのままではCOLOR()/SIZE()等の
            # 標準ルールが常にエスケープされて効かなくなる。extrarulesは
            # 読み手ではなくWiki管理者が書く設定（wikilib.extrarules、
            # config/pukiwiki.extrarules.example.yaml参照）で信頼レベルが
            # 異なるため、allow_htmlの対象外として素通しする。
            #
            # **信頼するのは置換文字列の固定部分（"html"）だけ。** 捕捉した部分
            # （"inline"）は読み手が書いた文字列なので、通常のインライン記法として
            # 解釈し直す（`COLOR(red):''foo''` の強調が効き、生HTMLは
            # allow_html の検閲を受ける）。詳しくは extrarules.match_extra_rule。
            for kind, value in extra_parts:
                if kind == "html":
                    tokens.append(Token("extra_rule_html", "", 0, content=value))
                else:
                    tokens.extend(parse_inline(value, _rule_depth + 1))
            pos = extra_end
            continue

        if ann_start != -1 and ann_start == earliest:
            ann_end = find_annotation_end(text, ann_start)
            if ann_end is not None:
                buffer.append(text[pos:ann_start])
                flush()
                tokens.append(Token("footnote_ref_pending", "", 0,
                                    content=text[ann_start + 2:ann_end]))
                pos = ann_end + 2
                continue
            # 閉じる "))" が最後まで見つからなかった。記法として扱わず、
            # この2文字だけを地の文として進める（この先に別の、閉じている
            # "((…))" があれば、そちらは改めて見つかる）
            buffer.append(text[pos:ann_start + 2])
            pos = ann_start + 2
            continue

        if html_m is not None and html_start == earliest:
            buffer.append(text[pos:html_start])
            flush()
            tokens.append(Token("html_inline", "", 0, content=html_m.group(0)))
            pos = html_start + len(html_m.group(0))
            continue

        if amp_start != -1 and amp_start == earliest:
            buffer.append(text[pos:amp_start])
            flush()
            tokens.extend(amp_tokens(amp_found[1]))
            pos = amp_found[1][-1]  # 各結果タプルの最後の要素が終端位置
            continue

        if m is None:
            buffer.append(text[pos:])
            break
        buffer.append(text[pos:m.start()])
        result = inline_match(m)
        if isinstance(result, str):
            buffer.append(result)  # 記法ではなかった。書かれたままの文字として扱う
        else:
            flush()
            tokens.extend(result)
        pos = m.end()
    flush()
    return tokens


def amp_tokens(result):
    """match_amp_token の結果をトークンにする（inline_match の '&' 関連
    分岐だった処理をそのまま移した）。"""
    if result[0] == "ref":
        _, content, _end = result
        # `&#38;` のような数値文字参照。"char_ref"で通す（下のコメント参照）
        return [Token("char_ref", "", 0, content=content)]
    _, name, args, body, _args_start, _args_end, _end = result
    bare = args is None and body is None
    if bare and (name + ";") in html5:
        # `&amp;` のような文字実体参照。"html_inline"ではなく専用の
        # "char_ref"トークンにして、allow_html（wikilib.htmlpolicy）の
        # 対象から外す。ここへ来る内容は数字だけの数値参照か、
        # html.entities.html5（Python標準）に実在が確認できた名前だけに
        # 限られ、タグ・属性・スクリプトを注入する余地が無い
        # （本家PukiWikiでも実体参照はallow_html相当の設定と無関係に働く。
        # Wiki設計者の報告: allow_html=falseだと`&amp;`が二重エスケープされ
        # `&amp;amp;`とそのまま表示されてしまっていた。とくにPukiWiki
        # Formattingの文書のように、インラインプラグインの記法を
        # `&amp;counter;`と書いて説明する慣習と相性が悪かった）。
        return [Token("char_ref", "", 0, content="&" + name + ";")]
    if name in DISPLAY_TIME_NAMES:
        # `&_date;` `&_time;` `&_now;` `&lastmod;` `&lastmod(ページ名);`。
        # プラグイン（`plugin/*.py` を要る `&name();`）ではなく、
        # 表示のたびに評価し直される組み込みの置換（wikilib.subst）。
        token = Token("subst_ref", "", 0)
        token.meta = {"name": name, "arg": (args or "").strip()}
        return [token]
    token = Token("plugin_inline", "span", 0)
    token.meta = {"name": name, "args": args or "", "body": body}
    return [token]


def find_annotation_end(text, start):
    """text[start:start+2] は "((" の開始。対応する "))" の開始位置を返す
    （無ければNone）。

    注釈は入れ子に書ける（`((外側((内側))続き))`）ので、開き "((" が出るたび
    深さを1増やし、閉じ "))" で1減らして、0に戻った位置を対応する閉じとする。
    正規表現では任意の深さを数え上げられないため、ここだけ手で走査する。"""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        if text.startswith("((", i):
            depth += 1
            i += 2
        elif text.startswith("))", i):
            depth -= 1
            if depth == 0:
                return i
            i += 2
        else:
            i += 1
    return None


def inline_match(m):
    """INLINE_RE のマッチ1つをトークンにする。記法でなければ文字列のまま返す。

    "&…"（インラインプラグイン・数値文字参照）は INLINE_RE に含まれない
    （find_amp_token/amp_tokens が別に処理する）ため、ここでは扱わない。"""
    if m.group("link") is not None:
        return link_tokens(m.group("link"))
    if m.group("rlink") is not None:
        return link_tokens(m.group("rlink"), relative=True)

    for group, kind, tag, markup in (
        ("em", "em", "em", "'''"),
        ("strong", "strong", "strong", "''"),
        ("ins", "ins", "ins", "%%%"),
        ("strike", "s", "s", "%%"),
    ):
        inner = m.group(group)
        if inner is not None:
            return wrap_tokens(kind, tag, inner, markup)

    if m.group("url") is not None:
        return autolink_tokens(m.group("url"), m.group("url"))
    if m.group("mail") is not None:
        return autolink_tokens("mailto:" + m.group("mail"), m.group("mail"))
    if m.group("wikiname") is not None:
        if not _active_wikiname:
            return m.group("wikiname")  # 機能をオフにしている。ただの文字列
        return link_tokens(m.group("wikiname"))
    return m.group(0)


def wrap_tokens(kind, tag, inner, markup):
    """強調・斜体・取消線。中身も入れ子の記法として解釈する。"""
    tokens = [Token(kind + "_open", tag, 1, markup=markup)]
    tokens.extend(parse_inline(inner))
    tokens.append(Token(kind + "_close", tag, -1, markup=markup))
    return tokens


def autolink_tokens(href, label):
    open_token = Token("link_open", "a", 1, info="auto")
    open_token.attrSet("href", href)
    return [open_token, Token("text", "", 0, content=label),
            Token("link_close", "a", -1, info="auto")]


def link_tokens(inner, relative=False):
    """`[[…]]`（`relative=False`）・`{[…]}`（`relative=True`）を解釈する。

    受ける形はどちらも同じ: `表示名>リンク先`、`表示名:URL`、`ページ名`、
    `ページ名#アンカー`、`表示名>#アンカー`、`InterWikiの登録名:ページ名`。

    リンク先は**書かれたまま**トークンに載せる。`ページ名` のように `/` を
    付けずに書いた場合の意味づけ（相対パスとして解き、ページがあればページ、
    無ければ添付）は Markdown と共通で、paths.resolve_link が引き受ける。
    ここで `/` を補ってしまうと、同じ書きかたが記法によって違う意味になり、
    解釈も2か所に分かれてしまう。

    `relative=True`（`{[…]}`）のときだけ、`relativize_target` が
    リンク先の先頭に `./` を補う——**"[[ページ名]]" はルートからの絶対
    という決まりを変えずに、「いま開いているページの下」を指したいときの
    書きかたを別に用意する**、というWiki設計者の指示（2026-09-04）。すでに
    `/`・`./`・`../` を書いている場合やURL・アンカー単体・
    InterWiki・mailto:/tel: はそのまま（補うと意味が変わる、または
    壊れるため）。"""
    label, arrow, target = inner.partition(">")
    if not arrow:
        head, colon, rest = inner.partition(":")
        if colon and is_url(rest):
            label, target = head, rest
        else:
            label = target = inner
    label = label.strip()
    target = target.strip() or label

    # InterWiki（"登録名:ページ名" の形）は、URLへ変換したうえで外部リンクと
    # して扱う。resolve_link に渡すとこのWiki内のページ名だと誤解されるため、
    # ここで先に判定しておく必要がある（relativizeより前に行う。
    # InterWikiの登録名に"./"を補うと登録名として一致しなくなるため）。
    if _active_interwiki:
        href = _active_interwiki.resolve(target)
        if href is not None:
            return autolink_tokens(href, label)

    if relative:
        target = relativize_target(target)

    # 本家PukiWikiの仕様どおり、リンク先が画像ファイルなら通常のリンクではなく
    # 画像として展開する（Markdownの `![alt](src)` に相当する専用の書きかたが
    # PukiWiki記法には無いため、`[[alt>image.jpg]]` のような通常のリンク記法を
    # そのまま使う）。判定は拡張子だけで行う（実在確認はしない。resolve_link と
    # 同じく、書かれた形だけで意味を決める）。
    if is_image_target(target):
        return image_tokens(target, label)

    open_token = Token("link_open", "a", 1)
    open_token.attrSet("href", target)
    return [open_token, Token("text", "", 0, content=label), Token("link_close", "a", -1)]


def relativize_target(target):
    """`{[…]}`のリンク先に、書かれていなければ`./`を補う。

    すでに`/`・`./`・`../`で始まる場合、URL（`://`を含む）、`#`・
    `mailto:`・`tel:`で始まる場合はそのまま返す——`[[…]]`側で既に
    書き手が明示した意味（絶対・相対・外部・アンカー単体）を、
    `{[…]}`が上書きしてしまわないようにするため。"""
    if not target or target.startswith(("#", "mailto:", "tel:", "/", "./", "../")):
        return target
    if "://" in target:
        return target
    bare, sep, anchor = target.partition("#")
    if not bare:
        return target
    return "./" + bare + sep + anchor


def is_image_target(target):
    """`[[…]]` のリンク先が画像ファイルを指しているか（拡張子だけで判定）。
    アンカー（`#foo`）・クエリ（`?v=1`）が付いていても、その手前の拡張子で見る。"""
    path = target.split("#", 1)[0].split("?", 1)[0]
    return path.lower().endswith(IMAGE_EXTS)


def image_tokens(src, alt):
    """画像トークンを1つ作る。markdown-it-py標準の `![alt](src)` が作るのと
    同じ形（type="image", tag="img"）にしておくことで、レンダリング規則
    （altの再計算・rewrite_content_linksによるsrcの書き換え）をそのまま共有する。"""
    token = Token("image", "img", 0)
    token.attrSet("src", src)
    token.content = alt
    token.children = [Token("text", "", 0, content=alt)]
    return [token]


def is_url(target):
    return bool(URL_SCHEME_RE.match(target)) or target.startswith("mailto:")


# ---- 注釈 --------------------------------------------------------------------
# `((…))` は、文中にその場で書ける注釈。番号は出てきた順に振られ、本文の末尾に
# 注釈の一覧としてまとめて出る（脚注）。トークンの形はMarkdown側のインライン脚注
# （mdit_py_plugins.footnote の `^[…]` 相当）に揃えてあるので、レンダリング規則を
# 共有できる。ただしMarkdown記法そのもの（`[^1]` 等）は意図的に無効にしてあるため
# （[使えない書きかた](/Syntax/Markdown#使えない書きかた)）、plugins.py 側では
# 描画規則だけを登録している。

def annotation_tip(children):
    """注釈の中身を、マウスを乗せたときに出す短い文にする。

    飾りを落とした素の文字だけを集める（強調やリンクの記号は出さない）。
    長ければ途中で切る（`FOOTNOTE_TIP_MAX`）。**入れ子の注釈は数に入れない**
    ——まだ `footnote_ref_pending` のままで、そちらはそちらで自分の吹き出しを
    持つため。"""
    parts = [child.content for child in children
             if child.type in ("text", "code_inline") and child.content]
    text = " ".join("".join(parts).split())
    if len(text) > FOOTNOTE_TIP_MAX:
        text = text[:FOOTNOTE_TIP_MAX].rstrip() + "…"
    return text


def append_annotations(tokens):
    """`(( ))` の注釈を集めて、本文末尾に一覧を追加する。

    parse_inline の時点では、中身をそのまま footnote_ref_pending トークンに
    包んでおくだけにしてある（何番目の注釈になるかは文書全体を見ないと決まらない
    ため）。ここで出てきた順に番号を振り、pendingトークンを footnote_ref に
    差し替えつつ、中身を改めて parse_inline する（注釈の中でも強調やリンクなど
    他のインライン記法を使えるようにするため）。

    **注釈は入れ子にできる**（`((外側((内側))続き))`）。中身を改めて
    parse_inline すると、内側の `((…))` からも新しい footnote_ref_pending が
    出てくるので、それも同じ列に積んで続けて処理する。本文中に出てきた注釈が
    先に番号を持ち、その中の入れ子はそのあとで番号を持つ（外側→内側の順）。"""
    notes = []
    queue = []

    def collect(children):
        for child in children:
            if child.type == "footnote_ref_pending":
                queue.append(child)

    for token in tokens:
        if token.type == "inline":
            collect(token.children)

    i = 0
    while i < len(queue):
        child = queue[i]
        i += 1
        note_id = len(notes)
        inner = parse_inline(child.content)
        notes.append(inner)
        child.type = "footnote_ref"
        child.content = ""
        # tip は、参照（[1]）にマウスを乗せたときに出す中身。ここで作るのは、
        # 描画のときには本文のトークン列（注釈の一覧）が見えないため
        # （plugins.render_footnote_ref_with_tip 参照）。
        child.meta = {"id": note_id, "tip": annotation_tip(inner)}
        collect(inner)  # 中に入れ子の注釈があれば、続けて番号を振る対象に積む

    if not notes:
        return

    tokens.append(Token("footnote_block_open", "", 1))
    for note_id, inner in enumerate(notes):
        tokens.append(Token("footnote_open", "", 1, meta={"id": note_id, "label": None}))
        tokens.append(Token("paragraph_open", "p", 1, block=True))
        tokens.append(Token("inline", "", 0, children=inner))
        tokens.append(Token("footnote_anchor", "", 0,
                             meta={"id": note_id, "subId": 0, "label": None}))
        tokens.append(Token("paragraph_close", "p", -1, block=True))
        tokens.append(Token("footnote_close", "", -1))
    tokens.append(Token("footnote_block_close", "", -1))


# ---- TODO -------------------------------------------------------------------
# 次の記法はまだ実装していない（本家のテキスト整形ルールにはあるもの）。
#   - 定義リストの項目を子要素にする `|~`（リストの `-~` は実装済み）
#   - WikiName（CamelCaseの自動リンク）とInterWiki
#   - `&heart;` `&smile;` のような顔文字系の文字参照
#   - 標準プラグイン群（#ref・#comment・#calendar 等。plugin/*.py で個別に用意する形）
#
# 置換系（`&date;` `&time;` `&now;` `&t;` `&page;` `&fpage;` `&_date;` `&_time;`
# `&_now;` `&lastmod;`）は wikilib.subst として実装済み。
