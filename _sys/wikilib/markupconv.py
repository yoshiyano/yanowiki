"""PukiWiki記法（`.txt`）と Markdown（`.md`）の本文を相互に変換する。

入り口は `pukiwiki_to_markdown` と `markdown_to_pukiwiki`。どちらも本文を受け取り、
変換後の本文と、変換で失ったものの一覧（`ConvertResult`）を返す。ファイルは
書き換えない。`build_options` は Wiki の設定と全ページの本文を読むだけ。

**読みかたは表示と同じパーサーに任せる。** 行の解釈を別に書くと、表示と食い違う。

  - PukiWiki は `pukiwiki.parse` の構造を使う。文字の部分は `inline` トークンの
    `content`（元の文字列）を読み直す。`wikiname=False` で読むのは、`[[Foo]]` と
    WikiName の `Foo` を見分けるため（どちらも同じリンクのトークンになる）
  - Markdown は、表示用と同じ規則に2つだけ足した markdown-it で読む。コメントを
    捨てずトークンにする規則と、`^[…]` を読む規則

## 設計者の決定（2026-11-07）

  - WikiName: Markdown → PukiWiki では本文を編集しない。「リンクにされてもOK」
    「リンク化が嫌なら wikiname の機能を止めて対応」。対応は `pukiwiki.wikiname` の
    有効・無効で変える
  - `&_date;` `&lastmod;`: 「7は未対応でOK」。Markdown では文字のまま出る
  - 文中のコード: `&icd{…};` と `` `…` `` を機械的に置き換える（`wikilib.icdbody`）

## クロコの案を設計者が「このまま」と了承したもの（2026-11-07）

  - 見出しのアンカー `[#x]`: Wiki の中で参照があるものだけ `&aname(x);` で残す
  - 注釈: `((x))` ↔ `^[x]`。**Markdown の表示側はまだ `^[x]` を読まない**
    （ここで足すのは変換用の読み取りだけ。表示側の対応は別の作業）
  - チェックリスト: PukiWiki では `[ ]` の文字のまま残す
  - 先頭の `# 題`: ページ名と同じなら消し、違えば `* 題` にする
  - WikiName（有効な Wiki の PukiWiki → Markdown）: 同名のページがあれば `[語](語)`、
    無ければ文字のまま。無効な Wiki では常に文字のまま

ほかの細部（表を GFM にするか `#table` にするか、整形済みテキストの形など）は
クロコの実装例で、設計者は未確認。
"""
import dataclasses
import html
import os
import re
from urllib.parse import unquote

from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin

from wikilib import htmlpolicy, icdbody, mdcomment, pukiwiki
from wikilib.extrarules import load_extra_rules, match_extra_rule
from wikilib.interwiki import load_interwiki
from wikilib.paths import farm_plugin_dir
from wikilib.plugins import build_markdown_renderer
from wikilib.subst import DISPLAY_TIME_NAMES, SAVE_TIME_NAMES

_INFINITY = float("inf")
_WIKINAME_RE = re.compile(r"(?:[A-Z][a-z]+){2,}(?!\w)")
_CELL_PREFIX_RE = re.compile(
    r"^(?:LEFT|CENTER|RIGHT|(?:BG)?COLOR\([#\w]+\)|SIZE\(\d+\)):")
_ALIGN_BLOCKDIV = "float=none, align={}, bordercolor=transparent"
_ALIGN_BLOCKDIV_RE = re.compile(
    r"^float=none, align=(left|center|right), bordercolor=transparent$")
_INS_HTML_RE = re.compile(r"^<ins>(.*)</ins>$", re.S)
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_TABLE_ROW_END_RE = re.compile(r"[hHfFcC]?\\\\[ \t]*(?:\n|$)")
_ANCHOR_REF_RE = re.compile(r"#([A-Za-z][\w-]*)")
_ANCHOR_DEF_RE = re.compile(r"\[#[A-Za-z][\w-]*\]\s*$", re.M)
_CODE_LANG_RE = re.compile(r"^\s*([\w+#.-]*)\s*$")
_SPAN_STYLES = (
    (re.compile(r'^<span style="color:([^"]+)">$'), "color", "{}"),
    (re.compile(r'^<span style="background-color:([^"]+)">$'), "color", ",{}"),
    (re.compile(r'^<span style="font-size:(\d+)px">$'), "size", "{}"),
)


@dataclasses.dataclass
class ConvertOptions:
    """変換に使う Wiki の情報。省略すると、Wiki を見ずに文字列だけで変換する。"""
    wikiname: bool = True               # pukiwiki.wikiname
    page_exists: object = None          # ページ名を受けて実在するかを返す関数
    referenced_anchors: frozenset = frozenset()  # 他のページから参照されるアンカー名
    extra_rules: object = None
    interwiki: object = None
    pukiwiki_html: bool = False         # pukiwiki.allow_html が生のHTMLを通すか
    page_name: str = ""                 # 先頭の `# 題` と見比べるページ名
    first_h1_as_title: bool = True      # markdown.first_h1_as_title
    config: dict = dataclasses.field(default_factory=dict)
    plugin_dir: str = None


@dataclasses.dataclass
class ConvertResult:
    text: str
    warnings: list


def pukiwiki_to_markdown(text, options=None):
    """PukiWiki記法の本文を Markdown にする。"""
    conv = _ToMarkdown(options or ConvertOptions())
    return ConvertResult(conv.document(text), _unique(conv.shared.warnings))


def markdown_to_pukiwiki(text, options=None):
    """Markdown の本文を PukiWiki記法にする。"""
    conv = _ToPukiWiki(options or ConvertOptions())
    return ConvertResult(conv.document(text), _unique(conv.shared.warnings))


def build_options(wiki_dir, config, page=""):
    """Wiki の設定と全ページの本文から `ConvertOptions` を作る。"""
    pw_conf = config.get("pukiwiki") or {}
    md_conf = config.get("markdown") or {}
    pages_dir = os.path.join(wiki_dir, "wiki")

    def exists(name):
        return any(os.path.isfile(os.path.join(pages_dir, name + ext))
                   or os.path.isfile(os.path.join(pages_dir, name, "index" + ext))
                   for ext in (".txt", ".md"))

    return ConvertOptions(
        wikiname=bool(pw_conf.get("wikiname", True)),
        page_exists=exists,
        referenced_anchors=collect_referenced_anchors(pages_dir),
        extra_rules=load_extra_rules(config, wiki_dir),
        interwiki=load_interwiki(wiki_dir),
        pukiwiki_html=htmlpolicy.parses_html(htmlpolicy.html_policy(config, ".txt")),
        page_name=page,
        first_h1_as_title=bool(md_conf.get("first_h1_as_title", True)),
        config=config,
        plugin_dir=farm_plugin_dir(wiki_dir),
    )


def collect_referenced_anchors(pages_dir):
    """Wiki の本文に `#名前` の形で現れる名前を集める。

    リンクかどうかは見分けないので、実際より多めに拾う（残しすぎても `&aname` が
    増えるだけで、リンク切れにはならない）。Wiki の外からの参照は分からない。"""
    names = set()
    for root, dirs, files in os.walk(pages_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            if not filename.endswith((".txt", ".md")):
                continue
            try:
                with open(os.path.join(root, filename), encoding="utf-8") as f:
                    names.update(_anchor_refs(f.read()))
            except (OSError, UnicodeDecodeError):
                continue
    return frozenset(names)


def _anchor_refs(text):
    return set(_ANCHOR_REF_RE.findall(_ANCHOR_DEF_RE.sub("", text)))


def _unique(items):
    return list(dict.fromkeys(items))


class _Shared:
    """本体と、プラグインの中身を読む入れ子の変換で共有する状態。"""

    def __init__(self, options):
        self.options = options
        self.warnings = []
        self.needs_code = False
        self.registry = None
        self.engine = None

    def plugin_info(self, name):
        if self.registry is None:
            self.registry = self.markdown_engine().plugin_registry
        entry = self.registry.get(name)
        return entry["info"] if entry else {}

    def markdown_engine(self):
        if self.engine is None:
            self.engine = _conversion_engine(self.options)
        return self.engine


def _conversion_engine(options):
    """表示用と同じ規則に、コメントと `^[…]` のトークン化を足した markdown-it。"""
    engine = build_markdown_renderer(options.config, options.plugin_dir)

    def block_comment(state, start_line, end_line, silent):
        matched = mdcomment.comment_block(state, start_line, end_line, silent)
        if matched and not silent:
            first = state.bMarks[start_line] + state.tShift[start_line]
            token = state.push("md_comment", "", 0)
            token.content = state.src[first:state.eMarks[state.line - 1]]
            token.map = [start_line, state.line]
        return matched

    def inline_comment(state, silent):
        start = state.pos
        matched = mdcomment.comment_inline(state, silent)
        if matched and not silent:
            token = state.push("md_comment_inline", "", 0)
            token.content = state.src[start:state.pos]
        return matched

    engine.block.ruler.at("md_comment", block_comment,
                          {"alt": ["paragraph", "reference", "blockquote", "list"]})
    engine.inline.ruler.at("md_comment", inline_comment)
    engine.use(footnote_plugin, inline=True)
    engine.disable(["footnote_def", "footnote_ref", "footnote_tail"])
    return engine


def _nest(tokens, start=0, end=None):
    """平らなトークン列を [(開きトークン, 子の列 or None), …] にする。"""
    end = len(tokens) if end is None else end
    nodes = []
    i = start
    while i < end:
        token = tokens[i]
        if token.nesting != 1:
            nodes.append((token, None))
            i += 1
            continue
        depth = 1
        j = i + 1
        while depth:
            depth += tokens[j].nesting
            j += 1
        nodes.append((token, _nest(tokens, i + 1, j - 1)))
        i = j
    return nodes


def _join_blocks(blocks):
    lines = []
    for block in blocks:
        if block:
            if lines:
                lines.append("")
            lines.extend(block)
    return lines


def _braced(name, args, body, fenced):
    """`#name(args){…}` の形にする。1行の形は波括弧を含まない本文だけが取れる。"""
    head = "#%s(%s)" % (name, args or "")
    if body is None:
        return [head]
    if not fenced and "\n" not in body and not re.search(r"[{}]", body):
        return [head + "{" + body + "}"]
    closing = [len(line.strip()) for line in body.split("\n")
               if line.strip() and not line.strip("} ")]
    count = max(closing + [1]) + 1
    return [head + "{" * count] + body.split("\n") + ["}" * count]


class _BodyConverter:
    """プラグインの中身のうち、宣言に応じて変換が要るものを振り分ける。両方向で共通。"""

    def convert_body(self, name, args, body, is_inline):
        if body is None:
            return None
        info = self.shared.plugin_info(name)
        if name == "table":
            return self.table_plugin_body(args, body)
        if name == "pre":
            verb = "verb" in re.split(r"\s*,\s*", (args or "").strip())
            return self.inline_text(body) if verb else body
        if is_inline or not info.get("expand_block"):
            return self.inline_text(body) if info.get("expand_inline") else body
        return self.nested_document(body)

    def table_plugin_body(self, args, body):
        """`#table` の中身。セルの書式の目印は残し、文字の部分だけを変換する。"""
        arg_words = [a.strip() for a in (args or "").split(",")]
        if "tsv" in arg_words:
            return "\n".join("\t".join(self.inline_text(cell) for cell in line.split("\t"))
                             for line in body.split("\n"))
        # セルは複数行にまたがれるので、行ではなく本文全体を `|` で分ける
        parts = _CELL_SPLIT_RE.split(body)
        for index in range(1, len(parts)):
            row_end = _TABLE_ROW_END_RE.match(parts[index])
            if row_end or index == len(parts) - 1:
                continue  # `|` のあとが行の種類と `\\\\`（または本文の終わり）。セルではない
            parts[index] = self.table_plugin_cell(parts[index])
        return "|".join(parts)

    def table_plugin_cell(self, cell):
        """`|` と `|` のあいだ。前後の空白・改行と書式の目印は残し、文字だけ変換する。"""
        prefix, text = _split_cell(cell)
        core = text.strip()
        if not core:
            return cell
        start = len(text) - len(text.lstrip())
        lead, tail = text[:start], text[start + len(core):]
        source = core.replace("\\|", "|")
        if "\n" in source:
            converted = self.nested_document(source)
        else:
            converted = self.table_cell_text(source)
        return prefix + lead + _CELL_SPLIT_RE.sub(r"\\|", converted) + tail


def _split_cell(cell):
    """セルの頭の目印（`~`・`CENTER:` など）と、残りの文字に分ける。"""
    if cell.strip() in (">", "~"):
        return cell, ""
    text = cell.lstrip()
    if text.startswith("~"):
        text = text[1:]
    while True:
        m = _CELL_PREFIX_RE.match(text)
        if not m:
            break
        text = text[m.end():]
    return cell[:len(cell) - len(text)], text


# ---- PukiWiki → Markdown ----------------------------------------------------

class _ToMarkdown(_BodyConverter):

    def __init__(self, options, shared=None):
        self.options = options
        self.shared = shared or _Shared(options)
        self.nested = shared is not None
        self.lines = []
        self.comments = []
        self.local_anchors = set()

    def warn(self, message):
        self.shared.warnings.append(message)

    def document(self, text):
        options = self.options
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.local_anchors = _anchor_refs(text)
        tokens = pukiwiki.parse(text, extra_rules=options.extra_rules,
                                interwiki=options.interwiki, wikiname=False,
                                allow_html=options.pukiwiki_html)
        for i, token in enumerate(tokens):
            if token.type == "footnote_block_open":
                tokens = tokens[:i]  # 注釈は本文の中で `^[…]` にする
                break
        self.comments = self._collect_comments(tokens)
        lines = self.sequence(_nest(tokens), _INFINITY, tight=False)
        if self.shared.needs_code and not self.nested and not any(
                re.match(r"^#code\(\s*\)\s*$", line) for line in lines):
            lines += ["", "#code()"]  # どこに置いても効く。先頭の `# 題` を邪魔しないよう末尾に
        return "\n".join(lines).strip("\n") + "\n" if lines else ""

    def nested_document(self, body):
        return _ToMarkdown(self.options, self.shared).document(body).rstrip("\n")

    def _collect_comments(self, tokens):
        """`//` の行を集める（パーサーは読み捨てる）。プラグインの中身は対象外。"""
        verbatim = set()
        for token in tokens:
            if token.type in ("plugin_block", "html_block") and token.map:
                verbatim.update(range(token.map[0], token.map[1]))
        found = []
        for number, line in enumerate(self.lines):
            if number in verbatim:
                continue
            body = re.sub(r"^(?:>{1,3} ?)+", "", line)
            if body.startswith("//"):
                found.append((number, body[2:].rstrip()))
        return found

    def flush_comments(self, before):
        out = []
        while self.comments and self.comments[0][0] < before:
            text = self.comments.pop(0)[1].replace("-->", "-- >")
            out.append("<!--" + text + "-->")
        return out

    def sequence(self, nodes, limit, tight):
        """ブロックの並び。コメントはトークンの行番号を頼りに元の位置へ戻す。"""
        blocks = []
        for index, (token, children) in enumerate(nodes):
            if token.map:
                pending = self.flush_comments(token.map[0])
                if pending:
                    blocks.append(pending)
            following = next((n[0].map[0] for n in nodes[index + 1:] if n[0].map), limit)
            blocks.append(self.block(token, children, following, tight))
        pending = self.flush_comments(limit)
        if pending:
            blocks.append(pending)
        if tight:
            return [line for block in blocks for line in block]
        return _join_blocks(blocks)

    def block(self, token, children, limit, tight):
        kind = token.type
        if kind == "inline":
            return self.inline_text(token.content).split("\n")
        if kind == "paragraph_open":
            return self.paragraph(token, children)
        if kind == "heading_open":
            return [self.heading(token, children)]
        if kind == "hr":
            return ["---"]
        if kind == "code_block":
            return self.code_block(token.content, tight)
        if kind == "plugin_block":
            return self.plugin_block(token, tight)
        if kind == "html_block":
            return token.content.rstrip("\n").split("\n")
        if kind == "blockquote_open":
            return self.quote(token, children)
        if kind in ("bullet_list_open", "ordered_list_open", "ul_open", "ol_open"):
            return self.list_block(token, children, limit)
        if kind == "table_open":
            return self.table(token)
        if kind == "dl_open":
            return self.deflist(children)
        self.warn("変換できない要素があります: " + kind)
        return []

    def paragraph(self, token, children):
        content = children[0][0].content if children else ""
        text = self.inline_text(content)
        align = re.match(r"text-align:(\w+)", token.attrGet("style") or "")
        if align:
            args = _ALIGN_BLOCKDIV.format(align.group(1))
            return _braced("blockdiv", args, text, True)
        return text.split("\n")

    def heading(self, token, children):
        text = self.inline_text(children[0][0].content) if children else ""
        anchor = (token.meta or {}).get("anchor")
        if anchor and (anchor in self.options.referenced_anchors
                       or anchor in self.local_anchors):
            text = "&aname(%s);%s" % (anchor, text)
        return "#" * int(token.tag[1]) + " " + text

    def code_block(self, content, tight):
        body = content.rstrip("\n").split("\n")
        if tight:
            # 詰まった箇条書きの字下げコードは項目を段落に変えるので、フェンスにする
            return _fence("", content)
        return ["    " + line for line in body]

    def plugin_block(self, token, tight):
        meta = token.meta
        name, args, body = meta["name"], meta.get("args") or "", meta.get("body")
        if name == "code" and body is not None:
            lang = _CODE_LANG_RE.match(args)
            if lang:
                self.shared.needs_code = True
                return _fence(lang.group(1), body + "\n")
        fenced = bool(token.map and token.map[1] - token.map[0] > 1)
        return _braced(name, args, self.convert_body(name, args, body, False), fenced)

    def quote(self, token, children):
        saved = self.lines
        self.lines = [re.sub(r"^>{1,3} ?", "", line) for line in saved]
        inner = self.sequence(children, token.map[1] if token.map else _INFINITY, False)
        self.lines = saved
        return [("> " + line) if line else ">" for line in inner]

    def list_block(self, token, children, limit):
        ordered = token.tag == "ol"
        loose = any(child[0].type == "paragraph_open" and not child[0].hidden
                    for item in children for child in (item[1] or []))
        blocks = []
        for index, (item, item_children) in enumerate(children):
            marker = "%d. " % (index + 1) if ordered else "- "
            following = limit
            if index + 1 < len(children) and children[index + 1][0].map:
                following = children[index + 1][0].map[0]
            inner = self.sequence(item_children or [], following, not loose)
            pad = " " * len(marker)
            if not inner:
                inner = [""]
            blocks.append([marker + inner[0]] + [pad + line if line else ""
                                                  for line in inner[1:]])
        return _join_blocks(blocks) if loose else [line for b in blocks for line in b]

    def table(self, token):
        start, end = token.map
        source = [line.rstrip() for line in self.lines[start:end]]
        if source and source[0].startswith(pukiwiki.CSV_TABLE_PREFIX):
            return self.csv_table(self.lines[start:end])
        rows = []
        for line in source:
            m = pukiwiki.TABLE_RE.match(line)
            if m:
                parts = icdbody.split_outside_calls(m.group(1))
                rows.append(((m.group(2) or "").lower(), parts))
        return self.gfm_table(rows) or self.plugin_table(rows)

    def gfm_table(self, rows):
        """GFM の表で同じ表示になるときだけ、その形にする。"""
        columns = {}
        shown = []
        for kind, parts in rows:
            cells = [pukiwiki.parse_cell(part) for part in parts]
            if kind == "c":
                for col, cell in enumerate(cells):
                    if cell["merge"] or set(cell["style"]) - {"text-align"}:
                        return None
                    columns[col] = cell["style"].get("text-align")
            else:
                shown.append((kind, cells))
        heads = [row for row in shown if row[0] == "h"]
        bodies = [row for row in shown if row[0] == ""]
        if len(heads) != 1 or len(heads) + len(bodies) != len(shown):
            return None
        aligns = {}
        for kind, cells in [heads[0]] + bodies:
            for col, cell in enumerate(cells):
                if cell["merge"] or set(cell["style"]) - {"text-align"}:
                    return None
                if kind == "" and cell["header"]:
                    return None
                align = cell["style"].get("text-align") or columns.get(col)
                if aligns.setdefault(col, align) != align:
                    return None
        delimiter = {None: "---", "left": ":---", "center": ":---:", "right": "---:"}
        width = len(heads[0][1])
        lines = [self._gfm_row(heads[0][1]),
                 "|" + "|".join(delimiter[aligns.get(c)] for c in range(width)) + "|"]
        lines += [self._gfm_row(cells) for _, cells in bodies]
        return lines

    def _gfm_row(self, cells):
        return "| " + " | ".join(self.inline_text(c["text"], in_table=True)
                                 for c in cells) + " |"

    def table_cell_text(self, source):
        return self.inline_text(source, in_table=True)

    def plugin_table(self, rows):
        body = []
        for kind, parts in rows:
            cells = [self.table_plugin_cell(part.strip()) for part in parts]
            body.append("|" + "|".join(cells) + "|" + kind + "\\\\")
        return _braced("table", "", "\n".join(body), True)

    def csv_table(self, source):
        body = []
        for line in source:
            row = []
            for text, align, colspan in pukiwiki.csv_cells(pukiwiki.split_csv(line[1:])):
                row += [">"] * (colspan - 1)
                prefix = "" if align == "left" else align.upper() + ":"
                cell = self.inline_text(text, in_table=True)
                if cell.startswith(("~", ">")) or _CELL_PREFIX_RE.match(cell):
                    cell = "&#%d;" % ord(cell[0]) + cell[1:]  # CSV では目印でなかった文字
                row.append(prefix + cell)
            body.append("|" + "|".join(row) + "|\\\\")
        return _braced("table", "", "\n".join(body), True)

    def deflist(self, children):
        blocks = []
        current = None
        for token, inner in children:
            if token.type == "dt_open":
                term = self.inline_text(inner[0][0].content) if inner else ""
                if not term:
                    self.warn("用語の無い定義リストは、用語を空白文字にしました")
                    term = "&nbsp;"
                current = [term]
                blocks.append(current)
            elif token.type == "dd_open":
                content = ""
                for child, grand in inner or []:
                    if child.type == "paragraph_open" and grand:
                        content = grand[0][0].content
                # `:語|` のあとの行が説明のときは、先頭が空の行になっている
                text = self.inline_text(content).strip("\n") or "&nbsp;"
                lines = text.split("\n")
                current.append(": " + lines[0])
                current.extend("  " + line for line in lines[1:])
        return _join_blocks(blocks)

    # ---- インライン ---------------------------------------------------------

    def inline_text(self, text, in_table=False):
        options = self.options
        token = pukiwiki.parse_inline_lines(
            text, extra_rules=options.extra_rules, interwiki=options.interwiki,
            wikiname=False, allow_html=options.pukiwiki_html)
        # 末尾の行の変わり目だけを落とす（`C:\\` の `\\` まで削らないように）
        out = re.sub(r"\\?\n+$", "", self.children(token.children or [], in_table))
        self._warn_broken_emphasis(out)
        return out

    def _warn_broken_emphasis(self, out):
        """`**日本語(ja)**を` のように、記号と日本語の境目で太字が効かない形を知らせる。"""
        if "**" not in out or "\\*" in out:
            return
        for token in self.shared.markdown_engine().parseInline(out, {})[0].children or []:
            if token.type == "text" and "**" in token.content:
                self.warn("Markdown で太字が効かない箇所があります: " + out[:60])
                return

    def children(self, tokens, in_table):
        tokens = _merge_char_refs(tokens)
        stack = [[]]   # 開いている飾りごとの文字の入れ物
        marks = []
        spans = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            kind = token.type
            buffer = stack[-1]
            if kind == "text":
                buffer.append(self.text(token.content, buffer, stack, in_table))
            elif kind in ("strong_open", "em_open", "s_open"):
                marks.append({"strong_open": "**", "em_open": "*", "s_open": "~~"}[kind])
                stack.append([])
            elif kind in ("strong_close", "em_close", "s_close"):
                inner = "".join(stack.pop())
                stack[-1].append(_wrap(marks.pop(), inner))
            elif kind == "ins_open":
                close = next(j for j in range(i, len(tokens))
                             if tokens[j].type == "ins_close")
                label = "".join(t.content for t in tokens[i + 1:close])
                buffer.append("&html(){<ins>" + html.escape(label, False) + "</ins>};")
                i = close
            elif kind == "link_open":
                close = next(j for j in range(i, len(tokens))
                             if tokens[j].type == "link_close")
                label = "".join(t.content for t in tokens[i + 1:close])
                buffer.append(_markdown_link(label, token.attrGet("href"), token.info))
                i = close
            elif kind == "image":
                buffer.append("![%s](%s)" % (_label(token.content),
                                             _destination(token.attrGet("src"))))
            elif kind == "footnote_ref_pending":
                buffer.append("^[" + self.children(self._inline_children(token.content),
                                                   in_table) + "]")
            elif kind == "plugin_inline":
                buffer.append(self.plugin_inline(token.meta, in_table))
            elif kind == "subst_ref":
                self.warn("&_date; などの表示時の置き換えは Markdown では動きません")
                arg = token.meta.get("arg")
                buffer.append("&%s%s;" % (token.meta["name"], "(%s)" % arg if arg else ""))
            elif kind in ("char_ref", "html_inline"):
                buffer.append(token.content)
            elif kind == "extra_rule_html":
                value, i = _whole_html_fragment(tokens, i)
                self.extra_rule(value, stack, spans)
            elif kind == "softbreak":
                buffer.append("\n")
            elif kind == "hardbreak":
                buffer.append("\\\n")
            else:
                self.warn("変換できない要素があります: " + kind)
            i += 1
        while len(stack) > 1:  # 閉じていない飾り（定義ルールの途中など）は中身だけ残す
            inner = "".join(stack.pop())
            stack[-1].append(inner)
        return "".join(stack[0])

    def _inline_children(self, content):
        options = self.options
        return pukiwiki.parse_inline_lines(
            content, extra_rules=options.extra_rules, interwiki=options.interwiki,
            wikiname=False, allow_html=options.pukiwiki_html).children or []

    def extra_rule(self, value, stack, spans):
        """定義ルールの出力（管理者が書いた HTML の断片）を、同じ見た目の書きかたへ。"""
        for pattern, plugin, arg in _SPAN_STYLES:
            m = pattern.match(value)
            if m:
                spans.append("&%s(%s){" % (plugin, arg.format(m.group(1))))
                stack.append([])
                return
        if value == "</span>" and spans:
            inner = "".join(stack.pop())
            stack[-1].append(spans.pop() + inner + "};")
            return
        if value == "<strong>":
            spans.append("**")
            stack.append([])
            return
        if value == "</strong>" and spans:
            inner = "".join(stack.pop())
            stack[-1].append(_wrap(spans.pop(), inner))
            return
        if "<" in value:
            self.warn("定義ルールの HTML を &html に置き換えました: " + value)
            stack[-1].append("&html(){" + value + "};")
            return
        stack[-1].append(value)  # フェイスマーク（絵文字）

    def plugin_inline(self, meta, in_table):
        name, args, body = meta["name"], meta.get("args"), meta.get("body")
        if name == icdbody.ICD_NAME and body is not None:
            return icdbody.markdown_code(icdbody.decode_body(body), in_table)
        if args is None and body is None and name in SAVE_TIME_NAMES:
            return "&%s;" % name  # 保存時に値へ置き換わる。書きかたによらず同じ
        return self._inline_plugin_text(name, args, body)

    def _inline_plugin_text(self, name, args, body):
        converted = self.convert_body(name, args, body, True)
        tail = "{" + converted + "}" if converted is not None else ""
        return "&%s(%s)%s;" % (name, args or "", tail)

    def text(self, value, buffer, stack, in_table):
        at_line_start = (len(stack) == 1 and (not buffer or buffer[-1].endswith("\n")))
        return self._wikinames(value, at_line_start, in_table)

    def _wikinames(self, value, at_line_start, in_table):
        """文字を Markdown としてエスケープし、実在するページの WikiName をリンクにする。"""
        options = self.options
        exists = options.page_exists
        if not options.wikiname or exists is None:
            return _escape_markdown(value, at_line_start, in_table)
        out = []
        pos = 0
        for m in _WIKINAME_RE.finditer(value):
            if not exists(m.group(0)):
                continue
            out.append(_escape_markdown(value[pos:m.start()],
                                        at_line_start and not pos, in_table))
            out.append("[%s](%s)" % (m.group(0), m.group(0)))
            pos = m.end()
        out.append(_escape_markdown(value[pos:], at_line_start and not pos, in_table))
        return "".join(out)


def _merge_char_refs(tokens):
    """記号の数値文字参照を文字に戻し、前後の文字とつなぐ。

    PukiWiki で書きかたを避けるための `&#39;` などで、Markdown には要らない。
    要るエスケープは、つないだあとの文字全体を見て決める（`&#91;a](b)` の `[` のように、
    前後を見ないと決まらない）。`&` は実体参照の形に変わりうるので戻さない。"""
    out = []
    for token in tokens:
        value = None
        if token.type == "char_ref":
            m = re.fullmatch(r"&#(\d+);", token.content)
            code = int(m.group(1)) if m else 0
            if 33 <= code < 127 and not chr(code).isalnum() and code != 38:
                value = chr(code)
        if value is None and token.type != "text":
            out.append(token)
            continue
        value = token.content if value is None else value
        if out and out[-1].type == "text":
            merged = Token("text", "", 0, content=out[-1].content + value)
            out[-1] = merged
        else:
            out.append(Token("text", "", 0, content=value))
    return out


def _whole_html_fragment(tokens, start):
    """定義ルールの捕捉で切れたタグ（`<span style="color:`・`#f50`・`">`）をつなぐ。"""
    value = tokens[start].content
    i = start
    while value.count("<") > value.count(">") and i + 1 < len(tokens) and (
            tokens[i + 1].type in ("text", "extra_rule_html")):
        i += 1
        value += tokens[i].content
    return value, i


def _wrap(mark, inner):
    """飾りで囲む。内側の端の空白は、飾りが効くよう外へ出す。"""
    if not inner.strip():
        return inner
    stripped = inner.strip(" ")
    left = inner[:len(inner) - len(inner.lstrip(" "))]
    right = inner[len(inner.rstrip(" ")):]
    return left + mark + stripped + mark + right


def _fence(lang, content):
    runs = re.findall(r"^\s*(`{3,})", content, flags=re.M)
    fence = "`" * (max([len(r) for r in runs] + [2]) + 1)
    return [fence + lang] + content.rstrip("\n").split("\n") + [fence]


def _label(text):
    return re.sub(r"([\[\]\\])", r"\\\1", text)


def _destination(target):
    target = target or ""
    if re.search(r"[\s<>]", target) or target.count("(") != target.count(")"):
        return "<" + target.replace(">", "%3E") + ">"
    return target


def _markdown_link(label, href, info):
    if info == "auto" and label in (href, (href or "").replace("mailto:", "", 1)):
        return label  # 裸の URL・メールアドレスは、どちらでもそのまま書ける
    return "[%s](%s)" % (_label(label), _destination(href))


_MD_LINE_HEAD_RES = (
    (re.compile(r"^(#{1,6})(?=\s|$)"), lambda m: "\\" + m.group(1)),
    (re.compile(r"^#(?=[A-Za-z_][\w-]*\()"), lambda m: "\\#"),
    (re.compile(r"^([-+*])(?=\s|$)"), lambda m: "\\" + m.group(1)),
    (re.compile(r"^(\d+)([.)])(?=\s|$)"), lambda m: m.group(1) + "\\" + m.group(2)),
    (re.compile(r"^>"), lambda m: "\\>"),
    (re.compile(r"^:(?=\s)"), lambda m: "\\:"),
    (re.compile(r"^([-=_*])(?=\1*\s*$)"), lambda m: "\\" + m.group(1)),
    (re.compile(r"^(`{3,}|~{3,})"), lambda m: "\\" + m.group(1)),
)


def _escape_markdown(value, at_line_start, in_table):
    """PukiWiki では文字だったものが、Markdown の書きかたにならないようにする。

    見た目を変えずに読みやすさも保ちたいので、飾りになりうる形のときだけ逃がす
    （`snake_case` や `2 * 3` はそのまま）。"""
    out = re.sub(r"\\(?=[!-/:-@\[-`{-~]|$)", r"\\\\", value)
    out = re.sub(r"(?<!\s)\*|\*(?!\s)", r"\\*", out)
    out = re.sub(r"(?:^|(?<=[^A-Za-z0-9]))_|_(?=[^A-Za-z0-9]|$)", r"\\_", out)
    out = out.replace("`", "\\`").replace("~~", "\\~\\~")
    out = re.sub(r"\[(?=[^\]]*\]\()", r"\\[", out).replace("](", "\\](")
    out = re.sub(r"<(?=[A-Za-z/!?])", r"\\<", out)
    out = re.sub(r"\^\[", r"\\^[", out)
    if in_table:
        out = out.replace("|", "\\|")
    if at_line_start:
        for pattern, repl in _MD_LINE_HEAD_RES:
            out, done = pattern.subn(repl, out, count=1)
            if done:
                break
    return out


# ---- Markdown → PukiWiki ----------------------------------------------------

_HARDBREAK_MARK = "\x00"


class _ToPukiWiki(_BodyConverter):

    def __init__(self, options, shared=None):
        self.options = options
        self.shared = shared or _Shared(options)
        self.nested = shared is not None
        self.pending_comments = []
        self.footnotes = []

    def warn(self, message):
        self.shared.warnings.append(message)

    def document(self, text):
        env = {}
        tokens = self.shared.markdown_engine().parse(text, env)
        self.footnotes = (env.get("footnotes") or {}).get("list") or {}
        nodes = _nest(tokens)
        if not self.nested:
            nodes = self._drop_title(nodes)
        lines = self.sequence(nodes)
        return "\n".join(lines).strip("\n") + "\n" if lines else ""

    def nested_document(self, body):
        return _ToPukiWiki(self.options, self.shared).document(body).rstrip("\n")

    def _drop_title(self, nodes):
        """先頭の `# 題` がページ名と同じなら消す（PukiWiki はページ名がタイトル）。"""
        options = self.options
        if not (nodes and options.first_h1_as_title and nodes[0][0].type == "heading_open"
                and nodes[0][0].tag == "h1"):
            return nodes
        title = nodes[0][1][0][0].content.strip() if nodes[0][1] else ""
        segments = [s for s in options.page_name.split("/") if s and s != "index"]
        if title and segments and title in (segments[-1], "/".join(segments)):
            return nodes[1:]
        return nodes

    def sequence(self, nodes):
        return _join_blocks(self.block(token, children) for token, children in nodes)

    def block(self, token, children, depth=0):
        kind = token.type
        if kind == "paragraph_open":
            return self.paragraph(children)
        if kind == "heading_open":
            return self.heading(token, children)
        if kind == "hr":
            return ["----"]
        if kind == "fence":
            lang = token.info.strip().split(" ")[0] if token.info.strip() else ""
            return _braced("code", lang, token.content.rstrip("\n"), True)
        if kind == "code_block":
            return self.code_block(token.content)
        if kind == "plugin_block":
            return self.plugin_block(token)
        if kind == "html_block":
            return token.content.rstrip("\n").split("\n")
        if kind == "md_comment":
            return _comment_lines(token.content)
        if kind == "blockquote_open":
            inner = self.sequence(children)
            return [("> " + line) if line else ">" for line in inner]
        if kind in ("bullet_list_open", "ordered_list_open"):
            return self.list_block(token, children, depth + 1)
        if kind == "table_open":
            return self.table(children)
        if kind == "dl_open":
            return self.deflist(children)
        self.warn("変換できない要素があります: " + kind)
        return []

    def paragraph(self, children):
        lines = self.inline_lines(children[0][0])
        return lines + self._take_comments()

    def _take_comments(self):
        out = [line for text in self.pending_comments for line in _comment_lines(text)]
        self.pending_comments = []
        return out

    def heading(self, token, children):
        source_level = int(token.tag[1])
        if source_level > 4:
            self.warn("h5・h6 の見出しは *** にしました（PukiWiki は3段階まで）")
        marker = "*" * max(1, min(3, source_level - 1))
        text = self.inline_text_token(children[0][0]) if children else ""
        text = re.sub(r"\[(?=#[A-Za-z][\w-]*\]\s*$)", "&#91;", text)
        return [marker + " " + text] + self._take_comments()

    def code_block(self, content):
        lines = content.rstrip("\n").split("\n")
        if any(not line.strip() for line in lines):
            # 行頭の空白の形は空行で切れるので、まとめて書ける形にする
            return _braced("pre", "", content.rstrip("\n"), True)
        return [" " + line for line in lines]

    def plugin_block(self, token):
        meta = token.meta
        name, args, body = meta["name"], meta.get("args") or "", meta.get("body")
        if name == "blockdiv" and body is not None:
            align = _ALIGN_BLOCKDIV_RE.match(args)
            if align and "\n" not in body:
                return [align.group(1).upper() + ":" + self.inline_text(body)]
        fenced = bool(token.map and token.map[1] - token.map[0] > 1)
        return _braced(name, args, self.convert_body(name, args, body, False), fenced)

    def list_block(self, token, children, depth):
        if depth > 3:
            self.warn("4段以上の箇条書きは3段目にそろえました")
        if token.attrGet("start") not in (None, "1", 1):
            self.warn("番号の開始位置は PukiWiki では指定できません")
        mark = ("+" if token.type == "ordered_list_open" else "-") * min(depth, 3)
        out = []
        for _item, item_children in children:
            out.extend(self.list_item(mark, item_children or [], depth))
        return out

    def list_item(self, mark, children, depth):
        lines = []
        rest = children
        first = children[0] if children else None
        if first is not None and first[0].type == "paragraph_open":
            text = self.inline_lines(first[1][0][0], item_head=True)
            # `-~` の段落は次の `~` の行まで飲み込むので、段落が続くときは使わない
            more = any(child[0].type == "paragraph_open" for child in children[1:])
            lead = mark + " " if first[0].hidden or more else mark + "~ "
            lines.append(lead + text[0])
            lines.extend(text[1:])
            lines.extend(self._take_comments())
            rest = children[1:]
        else:
            # 文字の無い項目の中のブロックは `-~` の次の行に置く（`- #note()` は文字になる）
            lines.append(mark + "~")
        for token, inner in rest:
            if token.type == "paragraph_open":
                body = self.inline_lines(inner[0][0])
                lines.append("~" + body[0])
                lines.extend(body[1:])
                lines.extend(self._take_comments())
            elif token.type in ("bullet_list_open", "ordered_list_open"):
                lines.extend(self.list_block(token, inner, depth + 1))
            else:
                if token.type == "heading_open":
                    self.warn("箇条書きの中の見出しは、PukiWiki では箇条書きの外に出ます")
                lines.extend(line for line in self.block(token, inner) if line)
        return lines

    def table(self, children):
        heads, bodies = [], []
        for section, rows in children:
            target = heads if section.type == "thead_open" else bodies
            target.extend(rows or [])
        aligns = []
        for _cell, _ in (heads[0][1] if heads else []):
            m = re.match(r"text-align:(\w+)", _cell.attrGet("style") or "")
            aligns.append(m.group(1).upper() + ":" if m else "")
        lines = []
        if any(aligns):
            lines.append("|" + "|".join(a or " " for a in aligns) + "|c")
        for _row, cells in heads:
            lines.append("|" + "|".join(self.table_cell(c, True) for c in cells or []) + "|h")
        for _row, cells in bodies:
            lines.append("|" + "|".join(self.table_cell(c, False) for c in cells or []) + "|")
        return lines + self._take_comments()

    def table_cell(self, cell, header):
        text = self.inline_text_token(cell[1][0][0], in_table=True) if cell[1] else ""
        if text in (">", "~") or text.startswith("~") or _CELL_PREFIX_RE.match(text):
            text = "&#%d;" % ord(text[0]) + text[1:]
        if header:
            return "~" + (text or "&#32;")
        return text or " "

    def deflist(self, children):
        lines = []
        term = ""
        for token, inner in children:
            if token.type == "dt_open":
                term = self.inline_text_token(inner[0][0]).replace("|", "&#124;")
                continue
            paragraphs = [child for child in inner or [] if child[0].type == "paragraph_open"]
            if len(paragraphs) != len(inner or []):
                self.warn("定義リストの説明の中のブロックは、PukiWiki では書けません")
            for para, grand in paragraphs:
                text = self.inline_lines(grand[0][0], item_head=True)
                lines.append(":%s|%s%s" % (term, "" if para.hidden else "~", text[0]))
                lines.extend(text[1:])
                term = ""
        return lines + self._take_comments()

    # ---- インライン ---------------------------------------------------------

    def inline_lines(self, token, item_head=False):
        """段落などの文字を行に分け、行の頭と末尾が書きかたに読まれないようにする。"""
        text = self.inline_text_token(token)
        lines = text.split("\n")
        out = []
        for index, line in enumerate(lines):
            hard = line.endswith(_HARDBREAK_MARK)
            line = line[:-1] if hard else line
            if line.endswith("~"):
                line = line[:-1] + "&#126;"
            if not (item_head and index == 0):
                line = _guard_line_head(line, self.options.pukiwiki_html)
            elif line.startswith("~"):
                line = "&#126;" + line[1:]
            out.append(line + ("~" if hard and index + 1 < len(lines) else ""))
        return out

    def inline_text_token(self, token, in_table=False):
        return self.children(token.children or [], in_table)

    def inline_text(self, body, in_table=False):
        """プラグインの中身などの、1つの文字列を変換する。"""
        token = self.shared.markdown_engine().parseInline(body, {})[0]
        return self.children(token.children or [], in_table).replace(_HARDBREAK_MARK, "~")

    def children(self, tokens, in_table):
        stack = [[]]
        marks = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            kind = token.type
            buffer = stack[-1]
            if kind in ("text", "text_special"):
                buffer.append(self.text(token.content, in_table))
            elif kind in ("strong_open", "em_open", "s_open"):
                marks.append({"strong_open": "''", "em_open": "'''", "s_open": "%%"}[kind])
                stack.append([])
            elif kind in ("strong_close", "em_close", "s_close"):
                mark = marks.pop()
                inner = "".join(stack.pop())
                stack[-1].append(self.decorate(mark, inner, marks))
            elif kind == "code_inline":
                buffer.append("&icd{" + icdbody.encode_body(token.content) + "};")
            elif kind == "link_open":
                close = self._matching(tokens, i)
                buffer.append(self.link(token, tokens[i + 1:close]))
                i = close
            elif kind == "image":
                buffer.append(self.image(token))
            elif kind == "footnote_ref":
                buffer.append(self.footnote(token, in_table))
            elif kind == "plugin_inline":
                buffer.append(self.plugin_inline(token.meta))
            elif kind == "html_inline":
                buffer.append(self.html_inline(token.content))
            elif kind == "md_comment_inline":
                self.pending_comments.append(token.content)
            elif kind == "softbreak":
                buffer.append("\n")
            elif kind == "hardbreak":
                buffer.append(_HARDBREAK_MARK + "\n")
            else:
                self.warn("変換できない要素があります: " + kind)
            i += 1
        return "".join(stack[0])

    @staticmethod
    def _matching(tokens, start):
        depth = 0
        for j in range(start, len(tokens)):
            depth += tokens[j].nesting
            if depth == 0:
                return j
        return len(tokens) - 1

    def decorate(self, mark, inner, outer_marks):
        """PukiWiki の飾りは1行の中でしか効かないので、行ごとに囲む。

        `'''''a'''''` と、`''` の中の `'''` は表示が崩れる（`pukiwiki.INLINE_RE`）。
        崩れた表示を残さないよう、斜体を諦める。"""
        if mark == "'''" and ("''" in outer_marks or inner.startswith("''")
                              or inner.endswith("''")):
            self.warn("太字と斜体の重なりは PukiWiki で書けないので、太字だけにしました")
            return inner
        out = []
        for line in inner.split("\n"):
            hard = line.endswith(_HARDBREAK_MARK)
            body = line[:-1] if hard else line
            if body.strip():
                body = _wrap(mark, _guard_quote_edges(body))
            out.append(body + (_HARDBREAK_MARK if hard else ""))
        return "\n".join(out)

    def text(self, value, in_table):
        out = value
        out = re.sub(r"&(?=[A-Za-z_#])", "&amp;", out)
        for name in list(DISPLAY_TIME_NAMES) + list(SAVE_TIME_NAMES):
            out = out.replace("&amp;%s;" % name, "&%s;" % name)  # 文字のまま残した元の形へ
        out = re.sub(r"\[\[", "&#91;[", out)
        out = re.sub(r"\{\[", "&#123;[", out)
        out = re.sub(r"\(\(", "&#40;&#40;", out)
        out = re.sub(r"'{2,}", lambda m: "&#39;" * len(m.group(0)), out)
        out = re.sub(r"%{2,}", lambda m: "&#37;" * len(m.group(0)), out)
        if self.options.pukiwiki_html:
            out = out.replace("<", "&lt;")
        if in_table:
            out = out.replace("|", "&#124;")
        return self._guard_extra_rules(out)

    def _guard_extra_rules(self, out):
        """Markdown では文字だった `BOLD:` などが、定義ルールに読まれないようにする。"""
        rules = self.options.extra_rules
        pos = 0
        while rules and pos < len(out):
            found = match_extra_rule(rules, out, pos)
            if found is None:
                break
            ref = "&#%d;" % ord(out[found[0]])
            out = out[:found[0]] + ref + out[found[0] + 1:]
            pos = found[0] + len(ref)
        return out

    def link(self, token, inner):
        href = unquote(token.attrGet("href") or "")
        inner = [t for t in inner if t.content or t.type != "text"]  # 飾りの前後の空の文字
        if token.attrGet("title"):
            self.warn("リンクの title は PukiWiki では書けません")
        if token.info == "auto":
            label = "".join(t.content for t in inner)
            if label == href or href == "mailto:" + label:
                return label
        whole_strong = (len(inner) >= 2 and inner[0].type == "strong_open"
                        and self._matching(inner, 0) == len(inner) - 1)
        plain = _flatten(inner)
        if [t for t in inner if t.type not in ("text", "text_special")] and not whole_strong:
            self.warn("リンクの文字の飾りは PukiWiki では書けません")
        label = plain.replace(">", "＞").replace("[", "［").replace("]", "］")
        if pukiwiki.is_image_target(href):
            self.warn("画像へのリンクは、PukiWiki では画像の埋め込みになります: " + href)
        link = "[[%s]]" % href if label == href else "[[%s>%s]]" % (label, href)
        return "''" + link + "''" if whole_strong else link

    def image(self, token):
        src = unquote(token.attrGet("src") or "")
        alt = _flatten(token.children or []).replace(">", "＞")
        if not pukiwiki.is_image_target(src):
            self.warn("画像の拡張子でないものは、PukiWiki では画像になりません: " + src)
        return "[[%s>%s]]" % (alt, src) if alt else "[[%s]]" % src

    def footnote(self, token, in_table):
        note = self.footnotes[token.meta["id"]]
        return "((" + self.children(note.get("tokens") or [], in_table) + "))"

    def plugin_inline(self, meta):
        name, args, body = meta["name"], meta.get("args") or "", meta.get("body")
        if name == "html" and body is not None:
            ins = _INS_HTML_RE.match(body)
            if ins and not args:
                return "%%%" + html.unescape(ins.group(1)) + "%%%"
        converted = self.convert_body(name, args, body, True)
        if converted is None:
            return "&%s(%s);" % (name, args)
        return "".join(
            "&%s(%s){%s};" % (name, args, line) if line.strip() else line
            for line in converted.split("\n"))

    def html_inline(self, content):
        checkbox = "task-list-item-checkbox" in content
        if checkbox:
            return "[x]" if " checked" in content else "[ ]"
        return content

    def table_cell_text(self, source):
        # `#table` のセルはブロックとして読まれるので、`-18%` が箇条書きにならないようにする
        text = self.inline_text(source, in_table=True)
        return _guard_line_head(text, self.options.pukiwiki_html)


def _flatten(tokens):
    parts = []
    for token in tokens:
        if token.type in ("text", "text_special", "code_inline"):
            parts.append(token.content)
        elif token.type == "image":
            parts.append(_flatten(token.children or []))
        elif token.type in ("softbreak", "hardbreak"):
            parts.append(" ")
    return "".join(parts)


def _comment_lines(content):
    inner = content.strip()
    inner = inner[len(mdcomment.COMMENT_OPEN):]
    if inner.endswith(mdcomment.COMMENT_CLOSE):
        inner = inner[:-len(mdcomment.COMMENT_CLOSE)]
    return ["//" + line.rstrip() for line in inner.rstrip().split("\n")]


def _guard_quote_edges(body):
    """飾りの内側の端の `'` が、飾りの記号とつながらないようにする。"""
    if body.startswith("'"):
        body = "&#39;" + body[1:]
    if body.endswith("'"):
        body = body[:-1] + "&#39;"
    return body


def _guard_line_head(line, pukiwiki_html):
    """Markdown では文字だった行が、PukiWiki のブロックとして読まれないようにする。"""
    if not line:
        return line
    head = line[0]
    if head == "~" or pukiwiki._starts_block(line):
        # 行頭の `~` は段落を切るので使わず、数値文字参照で書く（続きの行でも同じ形で済む）
        return "&#%d;" % ord(head) + line[1:]
    return line
