"""スロットHTML のテーマを描く（Jinja2 を通さないテーマ）。

テーマは式・ループ・`<script>` を持たないふつうの HTML で、本体が値と部品を埋める場所に
目印（`data-text`・`data-slot`・`<wiki-slot>` など）を付けておく。本体は
**HTML5 パーサで解析 → 許可リストでサニタイズ → 目印を埋める** の順に処理する。評価する式が
無いので、テーマからサーバのコードは動かない。書きかた・スロット・許可リストは wikiThemes の
仕様案（`wikiThemes/slot/SPEC.md`）に従う。仕様案はクロコの案で、設計者は書きかた・名前・
許可リストを確認していない。

## 置き場所で分ける

Wiki設計者の指示「置き場所で分ける方針で、段階1から進めてください」（2026-10-03）。
閲覧者は cookie でテーマを選べるので、Jinja2 のローダが読む場所に置かれた `.html` は誰でも
描かせられる。そこで、スロットHTML は Jinja2 が一切読まない別のフォルダに置く。

    共通        `slottheme/`（`theme/` と並べる。SLOTTHEME_DIR）
    個別Wiki    `wikidata/<Wiki>/slottheme/`（farm_slottheme_dir。共通より先に探す）

テーマは `<名前>.html`、またはフォルダ形式の `<名前>/<名前>.html`（Jinja2 のテーマと同じ数えかた）。

以下はクロコの実装例（設計者は未確認）:

- フォルダの名前は仕様案の仮の名前（`slottheme`）のまま
- 同じ名前の Jinja2 のテーマがあれば、Jinja2 のほうを描く（管理者が入れたものを優先する。
  `themes.render_theme`）
- 解析とサニタイズの結果は、ファイルの更新日時と大きさごとに覚えておく（`_load`）
- `data-asset` の名前がスロットHTML のフォルダに無ければ、共通の `/.theme/` の資材を指す
  （試作と同じ。slotbase は `data-asset="base.css"` で共通の base.css を読む）

## 検索結果は Jinja2 のテーマで描く

テンプレートを名指しする画面（検索結果の `_sys/search/search.html`）では、スロットHTML を選んでいても Jinja2 の
テーマで描く（`themes.render_theme`）。Wiki設計者の「検索結果は jinja2 で記述すれば良い。問題に
しているのはユーザが設置するテーマについてのみ」（2026-10-04）。

## CSS の検査

CSS は tinycss2 で読み、次のものを取り除く（`clean_css`。保存のときは `check_css` で見つけて断る）。
tinycss2 の導入は設計者の決定（2026-10-05）。何を取り除くかはクロコの案（設計者は未確認）:

    @import・@namespace            検査を通さないものを読み込める
    外への url()・image-set の文字列  行き先はテーマの資材の名前（`/` を含まない）と data: の画像
                                   （svg も可。CSS から読む画像はスクリプトを動かせない）だけ。
                                   閲覧者の情報がよそへ漏れ、属性の値を外へ送る書きかたもこれで防ぐ
    expression()・behavior・-moz-binding   古いブラウザでスクリプトが動く書きかた

`position: fixed` などの画面の偽装は CSS だけでは防げないので、検査しない。文字のエスケープ
（`u\\72l(`）は tinycss2 が仕様どおりに解いてから見るので、すり抜けられない。

## 資材（`/.slottheme/<テーマ名>/<ファイル名>`）

スロットHTML のフォルダからだけ配り、`/.theme/` とは混ぜない（`/.theme/` は種類を問わず配り、
個別Wikiのファイルで共通の `base.js` なども上書きできるため）。配るのは CSS・画像・フォントだけ
（`ASSET_EXTS`）。`.html`・`.js`・`.svg` は配らない（svg は直接開くとスクリプトが動く）。
"""
import copy
import os
import re
import threading
from html import escape

import html5lib
from bottle import HTTPResponse

from wikilib.paths import SLOTTHEME_DIR, SLOTTHEME_URLPATH, farm_slottheme_dir
from wikilib.web import static_file

# テーマ名・資材の名前（パスの区切りや「..」を含まない）
NAME_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*$")
ASSET_RE = re.compile(r"^(common:)?[A-Za-z0-9_-][A-Za-z0-9_.-]*$")
ASSET_EXTS = frozenset({".css", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico",
                        ".woff", ".woff2"})

VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                       "meta", "source", "track", "wbr"})

# ---- サニタイズの許可リスト（仕様案の3章） ---------------------------------------
ALLOWED_TAGS = frozenset({
    "html", "head", "body", "title", "meta", "link",
    "header", "footer", "nav", "main", "aside", "section", "article", "div", "span",
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "a", "ul", "ol", "li", "dl", "dt", "dd",
    "img", "figure", "figcaption", "em", "strong", "small", "b", "i", "u", "s", "br", "hr",
    "blockquote", "code", "pre", "sup", "sub", "abbr", "mark", "time",
    "table", "caption", "thead", "tbody", "tfoot", "tr", "th", "td",
    "wiki-slot",
})
GLOBAL_ATTRS = frozenset({"class", "title", "lang", "dir", "hidden", "role"})
TAG_ATTRS = {
    "a": {"href"},          # "#…" だけ。ほかのリンク先は data-href で本体が埋める
    "img": {"alt", "width", "height"},   # src は data-asset から
    "meta": {"charset", "name", "content"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "wiki-slot": {"name"},
}
DIRECTIVES = frozenset({"data-text", "data-href", "data-if", "data-unless", "data-slot",
                        "data-asset"})
META_NAMES = frozenset({"viewport", "wiki-slot", "wiki-behaviors"})
# 本体の部品の class（common.js が頼る）。部品はスロットとして本体が差し込むので、テーマの要素からは除く
PART_CLASSES = frozenset({"search", "section-editor"})
PART_CLASS_PREFIXES = ("search-", "page-search-", "marker-", "zoom-", "new-page-")

# 値（data-text・data-if）
VALUE_NAMES = ("site_title", "page_title", "head_title", "login_as", "render_ms",
               "source_mtime", "disk_usage", "version", "copyright_year")
# 本体が用意する動き（JS）。テーマは名前で選ぶだけ
BEHAVIORS = {"menu1-fold": "base.js"}
LINKS = {"home"}   # data-href で埋められる場所


class Raw:
    """本体が組み立てた HTML。エスケープせずにそのまま出す。"""

    def __init__(self, html):
        self.html = html


class Element:
    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []


# ---- 置き場所 ------------------------------------------------------------------

def slot_theme_dirs(wiki_dir):
    """スロットHTML を探す場所（個別Wiki → 共通）。"""
    return [farm_slottheme_dir(wiki_dir), SLOTTHEME_DIR]


def find_slot_theme(wiki_dir, name):
    """スロットHTML のテーマのファイル。無ければ None。"""
    if not name or not NAME_RE.match(name):
        return None
    for d in slot_theme_dirs(wiki_dir):
        for cand in (os.path.join(d, name, name + ".html"), os.path.join(d, name + ".html")):
            if os.path.isfile(cand):
                return cand
    return None


def list_slot_theme_names(wiki_dir):
    names = set()
    for d in slot_theme_dirs(wiki_dir):
        if not os.path.isdir(d):
            continue
        for entry in os.listdir(d):
            full = os.path.join(d, entry)
            if entry.endswith(".html") and os.path.isfile(full):
                name = entry[:-len(".html")]
            elif os.path.isfile(os.path.join(full, entry + ".html")):
                name = entry
            else:
                continue
            if NAME_RE.match(name):
                names.add(name)
    return names


def _asset_file(wiki_dir, theme, name):
    """スロットHTML のフォルダにある資材の実パス（テーマのフォルダ → フォルダの直下、個別Wiki → 共通）。"""
    for d in slot_theme_dirs(wiki_dir):
        for cand in (os.path.join(d, theme, name), os.path.join(d, name)):
            if os.path.isfile(cand):
                return cand
    return None


# ---- 解析とサニタイズ ------------------------------------------------------------

def _convert(e, out):
    """html5lib の木（etree）を Element に写す。コメントは落とす。"""
    if callable(e.tag):   # コメント
        if e.tail:
            out.append(e.tail)
        return
    el = Element(e.tag, e.attrib.items())
    if e.text:
        el.children.append(e.text)
    for c in e:
        _convert(c, el.children)
    out.append(el)
    if e.tail:
        out.append(e.tail)


def parse(text):
    root = html5lib.parse(text, treebuilder="etree", namespaceHTMLElements=False)
    holder = []
    _convert(root, holder)
    return holder[0]


def _keep_class(token):
    return token not in PART_CLASSES and not token.startswith(PART_CLASS_PREFIXES)


def _attr_ok(tag, name, value, attrs):
    if name in GLOBAL_ATTRS or name in TAG_ATTRS.get(tag, ()) or name in DIRECTIVES:
        pass
    elif name.startswith("aria-") or name.startswith("data-theme-"):
        return True
    elif name == "id":
        return value.startswith("theme-")
    else:
        return False
    if name == "href" and tag == "a":
        return value.startswith("#")
    if name == "data-asset":
        return bool(ASSET_RE.match(value))
    return True


def sanitize(el, report, path="html"):
    """許可リストに無い要素・属性・class を取り除く。取り除いたものを report に足す。"""
    kept = []
    for ch in el.children:
        if isinstance(ch, str):
            kept.append(ch)
            continue
        where = f"{path} > {ch.tag}"
        if ch.tag not in ALLOWED_TAGS:
            report.append(f"要素を削除: <{ch.tag}>（{path}）")
            continue
        a = ch.attrs
        if a.get("data-asset"):
            a.pop("href" if ch.tag == "link" else "src", None)   # 直接開いたとき用の見本の参照
        is_stylesheet = ch.tag == "link" and (a.get("rel") or "").strip().lower() == "stylesheet"
        for name, value in list(a.items()):
            if not _attr_ok(ch.tag, name, value or "", a):
                if not (name == "rel" and is_stylesheet):
                    report.append(f"属性を削除: {name}=\"{value}\"（{where}）")
                del a[name]
        if "class" in a:
            tokens = a["class"].split()
            keep = [t for t in tokens if _keep_class(t)
                    and (t != "content" or a.get("data-slot") == "content")]
            if len(keep) != len(tokens):
                report.append(f"class を削除: {' '.join(t for t in tokens if t not in keep)}（{where}）")
            if keep:
                a["class"] = " ".join(keep)
            else:
                del a["class"]
        if ch.tag == "meta" and "charset" not in a and a.get("name") not in META_NAMES:
            report.append(f"要素を削除: <meta name=\"{a.get('name')}\">（{path}）")
            continue
        if ch.tag == "link":
            if not (is_stylesheet and a.get("data-asset")):
                report.append(f"要素を削除: data-asset の無い <link>（{path}）")
                continue
            a["rel"] = "stylesheet"
        sanitize(ch, report, where)
        kept.append(ch)
    el.children = kept


_lock = threading.Lock()
_cache = {}   # 実パス → (更新日時, 大きさ, サニタイズした木, 報告)


def _load(path):
    """解析とサニタイズの結果（木の写しと報告）。ファイルが変わったときだけ読み直す。"""
    st = os.stat(path)
    key = (st.st_mtime_ns, st.st_size)
    with _lock:
        hit = _cache.get(path)
    if hit is None or hit[0] != key:
        with open(path, encoding="utf-8", errors="replace") as f:
            root = parse(f.read())
        report = []
        holder = Element("#root", [])
        holder.children = [root]
        sanitize(holder, report)
        hit = (key, holder, report)
        with _lock:
            _cache[path] = hit
    return copy.deepcopy(hit[1]), list(hit[2])


def check(text):
    """テーマの HTML をサニタイズしたときに取り除かれるものの一覧（保存時に作者へ知らせるため）。"""
    holder = Element("#root", [])
    holder.children = [parse(text)]
    report = []
    sanitize(holder, report)
    return report


# ---- 値とスロット ----------------------------------------------------------------

def _get(item, key):
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def _str(v):
    return "" if v is None else str(v)


def make_values(ctx):
    du = ctx.get("disk_usage")
    values = {name: ctx.get(name) for name in VALUE_NAMES}
    values["disk_usage"] = du.text if du is not None else None
    values["head_title"] = f"{_str(ctx.get('page_title'))} - {_str(ctx.get('site_title'))}"
    return {k: _str(v) for k, v in values.items()}


def _selected(cond):
    return " selected" if cond else ""


def make_slots(ctx, behaviors):
    """本体が組み立てる部品。マークアップは theme/base.html と同じ class にする（common.js が
    その class を頼りに動くため）。base.html の部品を直したら、ここも合わせる。"""
    e = lambda v: escape(_str(v))  # noqa: E731
    base_url = _str(ctx.get("base_url"))
    theme_url = _str(ctx.get("theme_url"))
    mode, target = ctx.get("mode"), ctx.get("target")

    plugin_assets = "".join(
        f'<link rel="stylesheet" href="{e(u)}">\n' for u in ctx.get("plugin_styles") or ()
    ) + "".join(
        f'<script src="{e(u)}" defer></script>\n' for u in ctx.get("plugin_scripts") or ()
    )

    topic = f'<a href="{e(base_url)}/">Top /</a>'
    for item in ctx.get("topic_path") or ():
        label, url = _get(item, "label"), _get(item, "url")
        topic += f' <a href="{e(url)}">{e(label)} /</a>' if url else f" {e(label)}"

    toc_items = list(ctx.get("toc") or ())
    toc = "".join(
        f'<li class="toc-l{e(_get(i, "level"))}"><a href="#{e(_get(i, "id"))}">'
        f'{e(_get(i, "title"))}</a></li>'
        for i in toc_items
    ) if len(toc_items) > 1 else ""

    scripts = f'<script src="{e(theme_url)}/common.js"></script>'
    for name in behaviors:
        if name in BEHAVIORS:
            scripts += f'\n<script src="{e(theme_url)}/{BEHAVIORS[name]}"></script>'

    return {
        "plugin-assets": plugin_assets,
        "common-menu": _str(ctx.get("common_menu")),
        "zoom-controls": (
            '<span class="zoom-controls">'
            '<button type="button" class="zoom-in" aria-label="表示を拡大"></button>'
            '<input type="number" class="zoom-value" aria-label="表示倍率(%)" inputmode="decimal">'
            '<button type="button" class="zoom-out" aria-label="表示を縮小"></button>'
            '</span>'),
        "marker-controls": (
            '<span class="marker-controls" hidden>'
            '<button type="button" class="command marker-panel-toggle">マーカー</button>'
            '<label class="marker-toggle" title="表示切り替え">'
            '<input type="checkbox" class="marker-toggle-input" aria-label="マーカー表示の切り替え">'
            '<span class="marker-toggle-track"><span class="marker-toggle-thumb"></span></span>'
            '</label>'
            '<select class="marker-set-select" aria-label="マーカーセットの切り替え"></select>'
            '</span>'),
        "search-form": (
            f'<form class="search" id="site-search-form" action="{e(ctx.get("search_url"))}" '
            'method="get" role="search">'
            f'<input class="search-word" type="search" name="q" value="{e(ctx.get("query"))}" '
            'placeholder="検索" aria-label="検索語">'
            '<button class="search-scope" type="button" data-scope="site" aria-pressed="false" '
            'aria-label="検索範囲を切り替え（現在: サイト全体）">サイト全体</button>'
            '<button class="search-submit" type="submit">検索</button>'
            '<span class="page-search-nav" hidden>'
            '<button class="page-search-prev" type="button" aria-label="前の一致へ">‹</button>'
            '<button class="page-search-next" type="button" aria-label="次の一致へ">›</button>'
            '<span class="page-search-count" role="status" aria-live="polite"></span>'
            '</span></form>'),
        "search-options": (
            '<div class="search-options" hidden>'
            '<div class="search-options-row">'
            '<label class="search-options-label" for="so-mode">条件</label>'
            '<select id="so-mode" name="mode" form="site-search-form">'
            f'<option value="and"{_selected(mode == "and")}>すべての語を含む（AND）</option>'
            f'<option value="or"{_selected(mode == "or")}>いずれかの語を含む（OR）</option>'
            '</select></div>'
            '<div class="search-options-row">'
            '<label class="search-options-label" for="so-target">対象</label>'
            '<select id="so-target" name="target" form="site-search-form">'
            f'<option value="all"{_selected(target == "all")}>ページ名と本文</option>'
            f'<option value="name"{_selected(target == "name")}>ページ名だけ</option>'
            f'<option value="body"{_selected(target == "body")}>本文だけ</option>'
            '</select></div>'
            '<div class="search-options-row">'
            '<label class="search-options-label" for="so-path">絞り込み</label>'
            f'<input id="so-path" type="search" name="path" value="{e(ctx.get("path_filter"))}" '
            'form="site-search-form" placeholder="例: Tech/* （* と ? が使えます）">'
            '</div>'
            '<div class="search-options-row search-options-actions">'
            '<button type="submit" form="site-search-form">この条件で検索</button>'
            '</div></div>'),
        "page-search-panel": (
            '<aside class="page-search-panel" hidden aria-label="ページ内検索の結果">'
            '<div class="page-search-panel-head"><div class="page-search-panel-head-row">'
            '<span class="page-search-panel-title">ページ内検索</span>'
            '<button class="page-search-close" type="button" aria-label="検索を閉じる">×</button>'
            '</div><p class="search-hotkey-hint">↑↓←→キーで検索ワードの候補を移動できます</p></div>'
            '<ol class="page-search-list"></ol><p class="page-search-more" hidden></p>'
            '</aside>'),
        "title-note": _str(ctx.get("title_note")),
        # info の知らせ（page_info。<a> の並び）。base.html の .page-info-slot と同じ入れ物で包む。
        # 知らせが無ければ空にして、テーマが data-if="page-info" で入れ物ごと出し分けられるようにする
        "page-info": (f'<span class="page-info-slot">{_str(ctx.get("page_info"))}</span>'
                      if _str(ctx.get("page_info")).strip() else ""),
        "topic-path": topic,
        "menu1": _str(ctx.get("menu1")),
        "menu2": _str(ctx.get("menu2")),
        "content": _str(ctx.get("content")),
        "toc": toc,
        "scripts": scripts,
    }


def _behaviors(el):
    found = []
    for ch in el.children:
        if isinstance(ch, Element):
            if ch.tag == "meta" and ch.attrs.get("name") == "wiki-behaviors":
                found += (ch.attrs.get("content") or "").split()
            found += _behaviors(ch)
    return found


def _asset_url(wiki_dir, ctx, theme, name):
    """data-asset の名前を URL にする（モジュール冒頭「資材」）。"""
    if name.startswith("common:"):
        return f"{_str(ctx.get('theme_url'))}/{name[len('common:'):]}"
    if os.path.splitext(name)[1].lower() in ASSET_EXTS and _asset_file(wiki_dir, theme, name):
        return f"{_str(ctx.get('base_url'))}/{SLOTTHEME_URLPATH}/{theme}/{name}"
    return f"{_str(ctx.get('theme_url'))}/{name}"


def _fill(el, wiki_dir, theme, ctx, values, slots, report):
    """目印（data-* と wiki-slot）を本体の値で埋める。"""

    def truthy(name):
        if name in slots:
            return bool(slots[name].strip())
        return bool(values.get(name, ""))

    out = []
    for ch in el.children:
        if isinstance(ch, str):
            out.append(ch)
            continue
        a = ch.attrs
        if ch.tag == "wiki-slot":
            name = a.get("name", "")
            if name not in slots:
                report.append(f"知らないスロット: {name}")
            out.append(Raw(slots.get(name, "")))
            continue
        if ch.tag == "meta" and a.get("name") == "wiki-slot":
            out.append(Raw(slots.get(a.get("content", ""), "")))
            continue
        if ch.tag == "meta" and a.get("name") == "wiki-behaviors":
            continue
        if "data-if" in a and not truthy(a.pop("data-if")):
            continue
        if "data-unless" in a and truthy(a.pop("data-unless")):
            continue
        if ch.tag == "html":
            for n in (1, 2):
                if ctx.get(f"menu{n}_mode") == "fix":
                    a[f"data-menu{n}-mode"] = "fix"
            # 標準の拡大率と幅（theme.zoom・theme.content_wide）。common.js が読む。
            # Jinja2 のテーマが <html> に付けるものと同じ属性
            if ctx.get("default_zoom") is not None:
                a["data-default-zoom"] = _str(ctx["default_zoom"])
            if ctx.get("default_content_wide"):
                a["data-default-wide"] = "1"
        if "data-href" in a:
            where = a.pop("data-href")
            a["href"] = _str(ctx.get("base_url")) + "/" if where in LINKS else "#"
        if "data-asset" in a:
            a["src" if ch.tag == "img" else "href"] = _asset_url(
                wiki_dir, ctx, theme, a.pop("data-asset"))
        if "data-text" in a:
            name = a.pop("data-text")
            if name not in values:
                report.append(f"知らない値: {name}")
            ch.children = [values.get(name, "")]
        elif "data-slot" in a:
            name = a.pop("data-slot")
            if name not in slots:
                report.append(f"知らないスロット: {name}")
            ch.children = [Raw(slots.get(name, ""))]
            if name == "content":
                # セクション編集が使うページ情報（base.html の <main> と同じ）
                if ctx.get("editable"):
                    a["data-editable"] = None
                    a["data-base-url"] = _str(ctx.get("base_url"))
                    a["data-page"] = _str(ctx.get("page"))
                if ctx.get("editing"):
                    a["data-draft"] = "1"
        else:
            _fill(ch, wiki_dir, theme, ctx, values, slots, report)
        out.append(ch)
    el.children = out


def _serialize(node, out):
    if isinstance(node, str):
        out.append(escape(node, quote=False))
    elif isinstance(node, Raw):
        out.append(node.html)
    else:
        if node.tag != "#root":
            attrs = "".join(
                f" {k}" if v is None else f' {k}="{escape(v)}"' for k, v in node.attrs.items())
            out.append(f"<{node.tag}{attrs}>")
            if node.tag in VOID_TAGS:
                return
        for ch in node.children:
            _serialize(ch, out)
        if node.tag != "#root":
            out.append(f"</{node.tag}>")


def render(wiki_dir, theme_path, theme, ctx):
    """スロットHTML を、本体が組み立てた context（`themes.render_theme`）で描く。(HTML, 報告) を返す。"""
    root, report = _load(theme_path)
    values = make_values(ctx)
    slots = make_slots(ctx, _behaviors(root))
    _fill(root, wiki_dir, theme, ctx, values, slots, report)
    out = ["<!DOCTYPE html>\n"]
    _serialize(root, out)
    return "".join(out), report


# ---- CSS の検査（モジュール冒頭「CSS の検査」） ------------------------------------

URL_FUNCS = frozenset({"url", "src"})
IMAGE_SET_FUNCS = frozenset({"image-set", "-webkit-image-set"})
BAD_FUNCS = frozenset({"expression"})
BAD_PROPS = frozenset({"behavior", "-moz-binding"})
BAD_AT_RULES = frozenset({"import", "namespace"})
# CSS から読む画像はスクリプトを動かせないので、data: の SVG も許す（資材として配る .svg は断る）
DATA_IMAGE_RE = re.compile(r"^data:image/(png|jpeg|gif|webp|avif|svg\+xml)[;,]", re.I)


def _url_ok(url):
    url = (url or "").strip()
    return bool(NAME_RE.match(url)) or bool(DATA_IMAGE_RE.match(url))


def _token_problems(tokens, where, problems):
    """値の中の url()・expression() などを調べ、見つけたものを problems に足す。"""
    import tinycss2
    for t in tokens or ():
        if t.type == "url":
            if not _url_ok(t.value):
                problems.append(f"url({t.value}) を削除（{where}）")
        elif t.type == "function":
            name = t.lower_name
            if name in URL_FUNCS:
                value = "".join(a.value for a in t.arguments if a.type == "string") \
                    or tinycss2.serialize(t.arguments)
                if not _url_ok(value):
                    problems.append(f"{name}({value}) を削除（{where}）")
            elif name in BAD_FUNCS:
                problems.append(f"{name}() を削除（{where}）")
            else:
                if name in IMAGE_SET_FUNCS:
                    for a in t.arguments:
                        if a.type == "string" and not _url_ok(a.value):
                            problems.append(f"{name}(\"{a.value}\") を削除（{where}）")
                _token_problems(t.arguments, where, problems)
        elif t.type in ("() block", "[] block", "{} block"):
            _token_problems(t.content, where, problems)


def _clean_block(content, where, problems):
    """`{ … }` の中（宣言と入れ子の規則）を調べて、残すものを文字列で返す。"""
    import tinycss2
    parts = []
    for n in tinycss2.parse_blocks_contents(content, skip_comments=True, skip_whitespace=True):
        if n.type == "declaration":
            if n.lower_name in BAD_PROPS:
                problems.append(f"{n.name} を削除（{where}）")
                continue
            found = []
            _token_problems(n.value, f"{where} {n.name}", found)
            if found:
                problems.extend(found)
                continue
            parts.append(n.serialize() + ";")
        elif n.type == "error":
            problems.append(f"読めない部分を削除（{where}）")
        else:
            rule = _clean_rule(n, where, problems)
            if rule:
                parts.append(rule)
    return "".join(parts)   # 宣言のあとにだけ「;」を付ける（規則どうしの間に置くと、後ろの規則が捨てられる）


def _clean_rule(n, where, problems):
    import tinycss2
    if n.type == "error":
        problems.append(f"読めない部分を削除（{where}）")
        return ""
    found = []
    _token_problems(n.prelude, where, found)
    if n.type == "at-rule":
        name = f"@{n.lower_at_keyword}"
        if n.lower_at_keyword in BAD_AT_RULES:
            problems.append(f"{name} を削除")
            return ""
        if found:
            problems.extend(found)
            return ""
        head = "@" + n.at_keyword + tinycss2.serialize(n.prelude)
        if n.content is None:
            return head + ";"
        return head + "{" + _clean_block(n.content, name, problems) + "}"
    if found:
        problems.extend(found)
        return ""
    selector = tinycss2.serialize(n.prelude).strip()
    return selector + "{" + _clean_block(n.content, selector, problems) + "}"


def clean_css(text):
    """CSS から取り除くものを除いた CSS と、取り除いたものの一覧。"""
    import tinycss2
    problems = []
    rules = tinycss2.parse_stylesheet(text, skip_comments=True, skip_whitespace=True)
    out = [r for r in (_clean_rule(n, "", problems) for n in rules) if r]
    return "\n".join(out) + ("\n" if out else ""), problems


def check_css(text):
    """CSS を検査したときに取り除かれるものの一覧（保存時に作者へ知らせるため）。"""
    return clean_css(text)[1]


_css_cache = {}   # 実パス → (更新日時, 大きさ, 取り除いたあとの CSS)


def _cleaned_css_file(path):
    st = os.stat(path)
    key = (st.st_mtime_ns, st.st_size)
    with _lock:
        hit = _css_cache.get(path)
    if hit is None or hit[0] != key:
        with open(path, encoding="utf-8", errors="replace") as f:
            hit = (key, clean_css(f.read())[0])
        with _lock:
            _css_cache[path] = hit
    return hit[1]


# ---- 資材の配信 ------------------------------------------------------------------

def serve_slot_asset(wiki_dir, rest):
    """`/.slottheme/<テーマ名>/<ファイル名>` を配る。CSS・画像・フォントだけ。"""
    theme, _, name = rest.partition("/")
    if (not NAME_RE.match(theme) or not NAME_RE.match(name)
            or os.path.splitext(name)[1].lower() not in ASSET_EXTS):
        return HTTPResponse(status=404, body="no page")
    full = _asset_file(wiki_dir, theme, name)
    if full is None:
        return HTTPResponse(status=404, body="no page")
    if name.lower().endswith(".css"):
        # git やコピーで入ったファイルにも効くよう、配るときにも取り除く（結果は覚えておく）
        return HTTPResponse(_cleaned_css_file(full), headers={
            "Content-Type": "text/css; charset=utf-8", "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff"})
    response = static_file(os.path.basename(full), root=os.path.dirname(full))
    response.set_header("X-Content-Type-Options", "nosniff")
    return response
