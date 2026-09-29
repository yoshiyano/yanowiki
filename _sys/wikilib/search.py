"""ページの検索。

## 数えるのと、見せるのを分ける

当たったページが多いときのために、**2段階**にしてある。

    1段階目  当たったページを数える（subpath と一致語数だけ）
    2段階目  そのページに出す分（既定20件）だけ、抜粋と強調を作る

抜粋づくり（`make_snippet`）と強調（`highlight`）は本文全体を舐めるので、
当たった数だけ行うと件数に比例して重くなる。**見せるのは20件なのだから、
作るのも20件でよい。** 1段階目では本文を1件ずつ流して当たり外れだけを見るので、
当たりが何千件あってもメモリに載るのは subpath と一致語数だけになる。

件数は1段階目で確定するので、「N件中 21〜40件目」やページ送りの数は、
2段階目に入る前に決まっている。

## ページ送り

`?page=2` で2ページ目。画面の切り替えは `/.search.js` が
`?fragment=1` を付けて同じURLを読み、結果の部分だけを差し替える
（ページ全体を組み直さずに済む）。JavaScriptが使えない環境では、ページ送りは
ふつうのリンクとして働く。

## 見た目は検索自身が持つ

結果一覧とページ送りのHTMLはこのモジュールが組み立て、CSS/JSも
`_sys/search/` が持つ（`/.search.css`, `/.search.js`）。テーマ側は検索フォームの
体裁だけを受け持つ。

## 閲覧権限が無いページは検索結果から省く（2026-09-24実装）

[ページごとの権限](/Tech/PagePermissions) の要件6。`search_matches`・
`search_pages`・`render_results_block` は `auth.page_privilege(...)` の判定器
（`privilege`）を**必須の引数**として受け取り、`-`（閲覧不可）と判定される
ページを除く。**落とすのは `candidate_subpaths` の直後**（本文を流す前）
なので、落とした分は本文を読みもしない。省略可能にしなかったのは、渡し忘れて
こっそり全ページが対象になる側に倒れないようにするため——常に全ページを
対象にしたい場面（管理系のバッチ処理など）は `auth.page_privilege(wiki_dir,
auth.SYSTEM_UID)` を渡せばよい（`$sys` はどのページでも `W`）。
"""
import fnmatch
import re
from html import escape
from urllib.parse import quote as urlquote, urlencode

from bottle import HTTPResponse, request
from markupsafe import Markup

from wikilib import auth, pagedb
from wikilib.pagedb import ensure_db
from wikilib.paths import (
    SEARCH_DIR, SEARCH_URLPATH, farm_plugin_dir, pagepath_of_subpath,
)
from wikilib.plugins import build_markdown_renderer
from wikilib.themes import make_plugin_context, render_theme
from wikilib.web import serve_asset

SEARCH_TEMPLATE = "search.html"  # 検索結果ページのテンプレート
SEARCH_SNIPPET_LEN = 140  # 検索結果に表示する抜粋の長さ
SEARCH_PER_PAGE = 20  # 1ページに出す件数
SEARCH_PAGER_WINDOW = 2  # ページ送りで、現在ページの前後にいくつ数字を出すか


def quick_title(text, pagepath):
    """検索結果の見出し用に、先頭行のh1をざっと拾う。"""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            return stripped[2:].strip()
        break
    return pagepath.rsplit("/", 1)[-1] or "(トップページ)"


def parse_search_terms(query):
    """検索語を空白区切りで切り出す。"..." で囲めば空白を含む語として扱う。"""
    return [t for t in re.findall(r'"([^"]+)"|(\S+)', query) for t in t if t]


def make_snippet(text, terms):
    """最初に一致した語の周辺を抜き出す。"""
    flat = " ".join(text.split())
    lowered = flat.lower()
    positions = [lowered.find(t.lower()) for t in terms]
    positions = [p for p in positions if p >= 0]
    start = max(0, min(positions) - 30) if positions else 0
    snippet = flat[start:start + SEARCH_SNIPPET_LEN]
    if start > 0:
        snippet = "…" + snippet
    if start + SEARCH_SNIPPET_LEN < len(flat):
        snippet += "…"
    return snippet


def highlight(text, terms):
    """一致した語を<mark>で囲む。エスケープ後に一度だけ置換するため、
    語が複数あっても挿入したタグの中を再度置換してしまうことはない。"""
    escaped = escape(text)
    if not terms:
        return Markup(escaped)
    pattern = re.compile("|".join(re.escape(escape(t)) for t in terms), re.IGNORECASE)
    return Markup(pattern.sub(lambda m: "<mark>" + m.group(0) + "</mark>", escaped))


def name_matches(pagepath, pattern):
    """ページ名の照合。
    "*" や "?" を含むパターンはワイルドカード（glob）として全体一致で判定し、
    含まない場合は従来どおり部分一致で判定する。
    "*" は "/" にも一致するため、"Tech/*" は下の階層まで、"*Guide" はどの階層でも拾う。"""
    pattern = pattern.lower()
    name = pagepath.lower()
    if any(c in pattern for c in "*?["):
        return fnmatch.fnmatchcase(name, pattern)
    return pattern in name


def split_filters(raw):
    r"""";"区切りの指定を一覧にして返す。"\;" は区切りではなく";"そのもの。

    `recent`の`exclude`用に作った解析だが、`name_matches`と同じ「絞り込みの
    書きかた」を共有するプラグインならどれでも使える（`ls`の`exclude`等）。
    区切り文字を含む名前を書けなくなると逃げ道が無いので、エスケープを
    用意している。"\\"は特別扱いしない（ページ名に"\"は使えないため、
    そこまで見ると読みにくくなるだけ）。"""
    out, buf, i = [], [], 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and i + 1 < len(raw) and raw[i + 1] == ";":
            buf.append(";")
            i += 2
            continue
        if c == ";":
            out.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    out.append("".join(buf).strip())
    return out


def candidate_subpaths(wiki_dir, terms, target, path_filter):
    """当たる見込みのあるページの実体パスを返す。当たり外れの最終判断はしない。

    ここで返すのは**当たりうるものを取りこぼさない範囲**であって、絞り込みの
    最終判断ではない。当たったかどうかは呼び出し側がこれまでどおり見比べて決める。
    こうしておけば、絞り込みを足しても検索の結果は変わらない。

    当たりうるのは次のいずれか。

        本文か見出しにその語を含む     … SQLに探させる（subpaths_containing）
        ページ名がその語に当たる       … 名前は短いのでPythonで見る

    語に改行が入っている場合だけは絞り込みをやめて全ページを返す。
    見出しと本文をつないだ境目にまたがって当たる見込みがあり、
    本文だけ・見出しだけを見るSQLでは拾えないため。"""
    if any("\n" in t for t in terms):
        wanted = set(pagedb.all_subpaths(wiki_dir))
    else:
        wanted = set()
        for term in terms:
            wanted |= pagedb.subpaths_containing(wiki_dir, term)
        if target != "body":
            # 本文だけが対象のときは、ページ名で当たっても数えない決まりなので見ない
            for subpath in pagedb.all_subpaths(wiki_dir):
                pagepath = pagepath_of_subpath(subpath)
                if any(name_matches(pagepath, t) for t in terms):
                    wanted.add(subpath)

    if not path_filter:
        return wanted
    return {s for s in wanted if name_matches(pagepath_of_subpath(s), path_filter)}


def count_hits(pagepath, title, text, terms, lowered_terms, target):
    """そのページが当たった語の数。0なら当たっていない。"""
    if target == "name":
        body = title.lower()
    elif target == "body":
        body = text.lower()
    else:
        body = (title + "\n" + text).lower()

    hits = 0
    for term, lowered in zip(terms, lowered_terms):
        if lowered in body:
            hits += 1
        elif target != "body" and name_matches(pagepath, term):
            hits += 1
    return hits


def search_matches(wiki_dir, terms, mode, privilege, target="all", path_filter=""):
    """当たったページを [(subpath, 一致語数), ...] で返す（一致語数の多い順）。

    **数えるだけ**で、抜粋や強調は作らない（そちらは表に出す分だけ build_results で
    作る）。本文はDBから1件ずつ流して読むので、当たりが多くてもメモリに残るのは
    subpath と一致語数だけになる。

    mode:   "and" は全語を含むページ、"or" はいずれかを含むページ
    target: "name" はページ名とタイトルだけ、"body" は本文だけ、"all" は両方を対象にする
    path_filter: ページ名で絞り込む（"Tech/" のような部分一致、"Tech/*" のようなワイルドカード）
    privilege: いまの閲覧者の判定器（`auth.page_privilege(wiki_dir, uid)`）。
        **閲覧権限が無い（`-`）ページは、本文の一致を見るまでもなく検索結果から
        除く**（Wiki設計者の想定、[ページごとの権限](/Tech/PagePermissions) の
        要件6・「検索から省くときの差し込み場所」。2026-09-24実装）。**候補を
        決める段（`candidate_subpaths` の直後）で落とす**——本文を流す前なので、
        落とした分は本文を読みもしない。省略できない引数にしてあるのは、
        渡し忘れてこっそり全ページが検索対象になる側に倒れないようにするため
        ——`$sys`（`auth.SYSTEM_UID`）で作った判定器を渡せば、これまでどおり
        全ページを対象にできる

    ページ名の照合にはワイルドカードが使えるが、本文の照合は常に部分一致。"""
    ensure_db(wiki_dir)
    lowered_terms = [t.lower() for t in terms]
    wanted = candidate_subpaths(wiki_dir, terms, target, path_filter)
    wanted = {s for s in wanted if privilege.check(pagepath_of_subpath(s)) != auth.PAGE_NONE}

    matches = []
    for subpath, db_title, text in pagedb.iter_page_texts_of(wiki_dir, wanted):
        pagepath = pagepath_of_subpath(subpath)
        # DBに取り出し済みの見出しがあればそれを使う。まだ無い場合
        # （作り直した直後など）は、これまでどおり本文の先頭から拾う
        title = db_title or quick_title(text, pagepath)
        hits = count_hits(pagepath, title, text, terms, lowered_terms, target)
        if hits == 0 or (mode == "and" and hits < len(lowered_terms)):
            continue
        matches.append((subpath, hits))
    # 一致語数の多い順、次にページパス順
    matches.sort(key=lambda m: (-m[1], pagepath_of_subpath(m[0])))
    return matches


def build_results(wiki_dir, matches, terms):
    """表に出す分だけ、抜粋と強調を作る。matches は search_matches の一部を切り出したもの。

    本文を舐める処理はここだけなので、当たりが何件あっても手間は出す件数で決まる。"""
    # "*Guide" のようなワイルドカード付きの語は、記号を外した部分を強調表示に使う
    marked = [t for t in (re.sub(r"[*?\[\]]", "", t) for t in terms) if t]
    hits_of = dict(matches)
    texts = {s: (t, b) for s, t, b in
             pagedb.iter_page_texts_of(wiki_dir, [s for s, _ in matches])}

    results = []
    for subpath, hits in matches:  # 並びは matches のまま保つ
        found = texts.get(subpath)
        if found is None:
            continue  # 数えたあとに消えた
        db_title, text = found
        pagepath = pagepath_of_subpath(subpath)
        title = db_title or quick_title(text, pagepath)
        results.append({
            "page": pagepath,
            "title": highlight(title, marked),
            "path": highlight(pagepath, marked),
            "snippet": highlight(make_snippet(text, marked), marked),
            "hits": hits_of.get(subpath, hits),
        })
    return results


def search_pages(wiki_dir, terms, mode, privilege, target="all", path_filter=""):
    """当たったページ全部を、これまでどおりの形（抜粋つき）で返す。

    ページ送りを使わずに全件が要る場合に使う。件数が多いと抜粋づくりが
    そのぶん重くなるので、画面に出す用途では search_matches と build_results を
    使い分けること。`privilege` は `search_matches` と同じ。"""
    matches = search_matches(wiki_dir, terms, mode, privilege, target, path_filter)
    return build_results(wiki_dir, matches, terms)


# ---- 画面に出す ------------------------------------------------------------

def page_count(total, per_page=SEARCH_PER_PAGE):
    """総件数から、ページの数を求める。0件でも1ページとして数える。"""
    if total <= 0:
        return 1
    return (total + per_page - 1) // per_page


def clamp_page(page, total, per_page=SEARCH_PER_PAGE):
    """?page= に何が来ても、在るページの番号に収める。"""
    return max(1, min(page, page_count(total, per_page)))


def pager_numbers(page, pages, window=SEARCH_PAGER_WINDOW):
    """ページ送りに出す番号。間を飛ばすところには None を入れる。

    先頭・末尾と、いま見ているページの前後だけを出す。ページ数が増えても
    ボタンの数が増えないようにするため（1000ページあっても並ぶのは10個ほど）。"""
    shown = {1, pages}
    shown |= {p for p in range(page - window, page + window + 1) if 1 <= p <= pages}
    out, last = [], 0
    for p in sorted(shown):
        if last and p > last + 1:
            out.append(None)  # 「…」を出すところ
        out.append(p)
        last = p
    return out


def search_url_of(base_url, params, page=None):
    """検索結果のURL。ページ番号だけを差し替えられるようにしてある。"""
    query = dict(params)
    if page and page > 1:
        query["page"] = page
    else:
        query.pop("page", None)
    query = {k: v for k, v in query.items() if v not in ("", None)}
    return "{}/{}?{}".format(base_url, SEARCH_URLPATH, urlencode(query))


def render_pager(base_url, params, page, pages):
    """ページ送り。1ページに収まっているときは何も出さない。"""
    if pages <= 1:
        return ""

    def item(label, target, kind, disabled=False):
        cls = "search-pager-" + kind
        if disabled:
            return f'<span class="{cls} is-disabled" aria-hidden="true">{label}</span>'
        current = ' aria-current="page"' if kind == "num" and target == page else ""
        if current:
            cls += " is-current"
        href = escape(search_url_of(base_url, params, target))
        return (f'<a class="{cls}" href="{href}" data-search-page="{target}"'
                f'{current}>{label}</a>')

    parts = [item("前へ", page - 1, "prev", disabled=page <= 1)]
    for n in pager_numbers(page, pages):
        if n is None:
            parts.append('<span class="search-pager-gap" aria-hidden="true">…</span>')
        else:
            parts.append(item(str(n), n, "num"))
    parts.append(item("次へ", page + 1, "next", disabled=page >= pages))
    return ('<nav class="search-pager" aria-label="検索結果のページ送り">'
            + "".join(parts) + "</nav>")


def render_summary(terms, mode, target, path_filter, total, page, pages, per_page):
    """「N件中 21〜40件目」まで出す見出し。"""
    joiner = "と" if mode == "and" else "または"
    words = joiner.join(f"<code>{escape(t)}</code>" for t in terms)
    where = {"all": "ページ名と本文", "name": "ページ名", "body": "本文"}[target]
    limited = (f"（<code>{escape(path_filter)}</code> を含むページ名に限定）"
               if path_filter else "")
    if total == 0:
        return (f'<p class="search-summary">{words} を{where}から検索{limited}: '
                "<strong>0</strong> 件</p>")
    first = (page - 1) * per_page + 1
    last = min(page * per_page, total)
    shown = (f'<span class="search-range">{first}〜{last}件目</span>'
             if pages > 1 else "")
    return (f'<p class="search-summary">{words} を{where}から検索{limited}: '
            f"<strong>{total}</strong> 件{shown}</p>")


def render_result_list(base_url, results, query):
    """結果の一覧。リンクに検索語(?q=)を付けておくと、移動先のページで
    common.js が該当語を強調表示し、最初の箇所までスクロールする。"""
    if not results:
        return '<p class="search-empty">一致するページはありませんでした。</p>'
    rows = []
    for item in results:
        page_url = "{}/{}?q={}".format(
            escape(base_url), escape(urlquote(item["page"])), escape(urlquote(query)))
        rows.append(
            '<li class="search-result">'
            f'<a class="search-result-title" href="{page_url}">{item["title"]}</a>'
            f'<div class="search-result-path">{escape(base_url)}/{item["path"]}</div>'
            '<p class="search-result-snippet">'
            f'<a class="search-result-jump" href="{page_url}">{item["snippet"]}</a>'
            "</p></li>"
        )
    return '<ul class="search-results">' + "".join(rows) + "</ul>"


def render_results_block(wiki_dir, base_url, params, terms, mode, target,
                         path_filter, page, privilege, per_page=SEARCH_PER_PAGE):
    """検索結果のかたまり（見出し・一覧・ページ送り）を組み立てて返す。

    ページ全体を出すときも、`?fragment=1` で結果だけを差し替えるときも、
    **同じものを使う**。2つに分けると、片方だけ直す事故が起きるため。
    `privilege` は `search_matches` と同じ（閲覧権限が無いページを除く）。"""
    matches = search_matches(wiki_dir, terms, mode, privilege, target, path_filter)
    total = len(matches)
    pages = page_count(total, per_page)
    page = clamp_page(page, total, per_page)
    shown = matches[(page - 1) * per_page: page * per_page]
    results = build_results(wiki_dir, shown, terms)

    query = params.get("q", "")
    return Markup(
        '<div class="search-block" data-search-page-now="{}" data-search-pages="{}">'
        "{}{}{}</div>".format(
            page, pages,
            render_summary(terms, mode, target, path_filter,
                           total, page, pages, per_page),
            render_result_list(base_url, results, query),
            render_pager(base_url, params, page, pages),
        )
    )


def serve_search_asset(name):
    """検索が自前で持つCSS/JS（/.search.css, /.search.js）。
    渡ってくるのは拡張子だけ（編集画面・バックアップ管理画面の資材と同じ扱い）。"""
    return serve_asset(SEARCH_DIR, "search", name)


def render_search(wiki_dir, config, farm, explicit_farm):
    # bottleの request.query.get() はWSGIの生の値（latin-1）を返すため、
    # 日本語の検索語が化ける。getunicode() でUTF-8として取り出す。
    query = request.query.getunicode("q", "").strip()
    mode = "or" if request.query.getunicode("mode") == "or" else "and"
    target = request.query.getunicode("target", "all")
    if target not in ("all", "name", "body"):
        target = "all"
    path_filter = request.query.getunicode("path", "").strip()
    try:
        page = int(request.query.getunicode("page", "1"))
    except ValueError:
        page = 1

    terms = parse_search_terms(query)
    context = make_plugin_context(config, farm, wiki_dir, SEARCH_URLPATH, explicit_farm)
    params = {"q": query, "mode": mode, "target": target, "path": path_filter}
    privilege = auth.page_privilege(wiki_dir, auth.current_uid(wiki_dir, farm))

    block = Markup("")
    if terms:
        block = render_results_block(
            wiki_dir, context.base_url, params, terms, mode, target, path_filter, page,
            privilege)

    if request.query.get("fragment"):
        # ページ送りで結果だけを差し替えるときの返し。テーマも資材も通さない
        # （CSS/JSはすでに読み込まれているので、付け直すと二重になる）
        return HTTPResponse(body=str(block), status=200,
                            content_type="text/html; charset=utf-8")

    # 見た目と動きは検索自身が持つ（バックアップ管理画面と同じ形）
    asset_url = escape(context.base_url + "/" + SEARCH_URLPATH)
    block = Markup(
        f'<link rel="stylesheet" href="{asset_url}.css">'
        + str(block)
        + f'<script src="{asset_url}.js" defer></script>'
    )

    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    return render_theme(
        engine, wiki_dir, config, farm, SEARCH_URLPATH, "検索", "",
        template=SEARCH_TEMPLATE, editable=False, explicit_farm=explicit_farm, context=context,
        query=query, mode=mode, target=target, path_filter=path_filter,
        terms=terms, results_block=block,
    )
