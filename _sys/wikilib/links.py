"""ページ本文から取り出す情報（タイトル・目次・リンク）。

ページ間の参照関係をたどれるようにするため、そのページが**どこを参照して
いるか**を保存のたびに取り出す。あわせて、毎回パースし直さずに済むよう、
タイトルと目次も同じ機会に取り出しておく。

**置き場所はDB**（pageinfo/wikiall.db）で、本文と同じ行・同じリンクの表に入る。
本文から一意に決まる値なので、本文と一度に書けば食い違いが起こらない
（詳しくは pagedb の冒頭）。

**リンクは「書かれたままの文字列」をキーに持つ**（`links(source, href, kind,
owner, filename)`）。位置（文字オフセット）ではなく文字列を持たせているのは、
`pagelinks.link_spans` がそのときの本文へ毎回素直にかければ位置は見つかる
ため、ここでは「その文字列が何を指しているか」という**解決結果のキャッシュ**
だけを持てば足りるからである（rewrite_links がリライトのたびに resolve_link
を呼ばずに済む）。

拾うのは**本文の記法として書かれたリンク**（`pagelinks.link_spans`）と、
**`PLUGIN_INFO["args"]` で `"link": True` と宣言された引数の値**
（`plugin_arg_links`）。プラグインの引数はプラグインごとに形が違うため、
「この引数はページ/添付への参照だ」と宣言されたものだけを拾う（宣言が
無ければ、ただの文字列として無視する）。どちらもページか添付ファイルかは
`pagelinks.resolve_href` が決め、InterWiki（登録名が一致するもの）や
外部URL・別Wiki・ページ内アンカーはそこで除かれる（プラグインの引数が
外部URLを指していても構わない＝自動的にリンクの記録からは外れる）。

**プラグインは実行しない。** 引数の宣言（`bind_plugin_args`）だけを使って
解決した値を見るので、プラグインの`_convert`/`_inline`本体は呼ばれない
（実行の副作用や失敗を、リンクを数えるためだけの処理に持ち込まないため）。
"""
from wikilib import pagedb
from wikilib.paths import pagepath_of_subpath
from wikilib.pagelinks import link_spans, resolve_href
from wikilib.plugins import bind_plugin_args, parse_plugin_args
from wikilib.render import build_toc, parse_source, split_title, uses_title_heading


def page_links(text, ext, subpath, wiki_dir=None, interwiki=None):
    """本文から、同じWiki内の場所への参照を、**書かれたままの文字列**をキーに
    集める。[(href, 種別, 持ち主, ファイル名), ...] を href の昇順で返す。

    リンク先の読みかたは表示のときとまったく同じ（pagelinks.resolve_href）。
    画面で押したときに行く先と、ここに記録する先が食い違わないようにするため。
    同じ文字列が何度出てきても1つにまとめる（結果は常に同じになるため）。"""
    rows, seen = [], set()
    for _start, _end, href, _relative in link_spans(text, ext, interwiki=interwiki):
        if href in seen:
            continue
        seen.add(href)
        resolved = resolve_href(subpath, href, wiki_dir, interwiki)
        if resolved is None:
            continue
        kind, owner, filename = resolved
        rows.append((href, kind, owner, filename))
    rows.sort()
    return rows


def _iter_plugin_tokens(tokens):
    """トークン列から plugin_block / plugin_inline を（入れ子の1段ぶんも
    含めて）順に返す。plugin_block はブロックの並びに直接出てくるが、
    plugin_inline（`&name();`）は段落などの inline トークンの children に
    入っているため、そちらも見る（inline はそれ以上入れ子にならない）。"""
    for token in tokens:
        if token.type in ("plugin_block", "plugin_inline"):
            yield token
        for child in (token.children or ()):
            if child.type in ("plugin_block", "plugin_inline"):
                yield child


def plugin_arg_links(tokens, registry, subpath, wiki_dir=None, interwiki=None):
    """本文中のプラグイン呼び出しから、`"link": True` と宣言された引数の値を
    集める。戻り値の形は page_links と同じ [(href, 種別, 持ち主, ファイル名), ...]
    （ここではまだ href の昇順に整えない。呼び出し側で page_links の結果と
    まとめてから整える）。

    registry は `wikilib.plugins.load_plugins` の戻り値（`build_markdown_renderer`
    が組み立てて `engine.plugin_registry` に持たせているもの）。見つからない
    プラグイン名・読み込みに失敗しているプラグイン・"link" を1つも宣言して
    いないプラグインは黙って読み飛ばす（本文の描画時に出るエラー表示は
    ここでは扱わない。あくまでリンクの抽出なので）。"""
    rows = []
    for token in _iter_plugin_tokens(tokens):
        meta = token.meta or {}
        entry = registry.get(meta.get("name"))
        if entry is None or entry.get("error"):
            continue
        schema = (entry.get("info") or {}).get("args") or ()
        link_names = [item["name"] for item in schema if item.get("link")]
        if not link_names:
            continue
        args, kwargs = parse_plugin_args(meta.get("args") or "")
        resolved, err = bind_plugin_args(args, kwargs, schema)
        if err is not None:
            continue
        for name in link_names:
            href = resolved.get(name)
            if not isinstance(href, str) or not href.strip():
                continue
            resolved_link = resolve_href(subpath, href, wiki_dir, interwiki)
            if resolved_link is None:
                continue
            kind, owner, filename = resolved_link
            rows.append((href, kind, owner, filename))
    return rows


def extract_page_info(engine, text, ext, subpath, first_h1_as_title=True, wiki_dir=None,
                      interwiki=None):
    """本文から (タイトル, 目次, リンク) を取り出す。

    タイトル・目次はトークン列から、本文のリンクは本文の文字列から
    （page_links）別々に取り出す。リンクの抽出に本文側だけmarkdown-itの
    トークンを使わないのは、書かれた位置と文字列をそのまま扱いたいため
    （詳しくは page_links）。プラグインの引数のリンク（plugin_arg_links）は
    もとよりトークンからしか取れないので、そちらはトークン列を見る。

    目次は**深さで絞らずに全部**入れる。どこまで見せるかは使う側の都合
    （サイドバーは `markdown.toc_depth`、`#contents` はその指定）で違うので、
    絞った状態で持つと浅いほうに合わせた分しか取り出せなくなる。"""
    tokens = parse_source(engine, text, ext)
    title, body_tokens, _ = split_title(
        tokens, uses_title_heading(ext, first_h1_as_title))
    links = page_links(text, ext, subpath, wiki_dir, interwiki)
    registry = getattr(engine, "plugin_registry", None)
    if registry:
        seen = {href for href, _, _, _ in links}
        for href, kind, owner, filename in plugin_arg_links(
                tokens, registry, subpath, wiki_dir, interwiki):
            if href in seen:
                continue
            seen.add(href)
            links.append((href, kind, owner, filename))
        links.sort()
    return title or "", build_toc(body_tokens), links


def update_page_info(wiki_dir, subpath, engine, text, ext, config=None, now=None):
    """本文から取り出し直してDBに入れる。保存・復元・取り込みのたびに呼ぶ。"""
    md_conf = (config or {}).get("markdown") or {}
    from wikilib.interwiki import load_interwiki
    interwiki = load_interwiki(wiki_dir) if wiki_dir else None
    title, toc, links = extract_page_info(
        engine, text, ext, subpath,
        first_h1_as_title=md_conf.get("first_h1_as_title", True), wiki_dir=wiki_dir,
        interwiki=interwiki)
    return pagedb.record_page_info(wiki_dir, subpath, title, toc, links, now=now)


def ensure_page_info(wiki_dir, subpath, engine, text, ext, config=None):
    """まだ取り出していなければ取り出す。取り出したらTrueを返す。

    DBを作り直した直後は本文しか入っていない（全文のパースが重いため、
    作り直しでは省いている）。ページを開いたときにここで補う。"""
    if pagedb.load_page_info(wiki_dir, subpath) is not None:
        return False
    update_page_info(wiki_dir, subpath, engine, text, ext, config)
    return True


def links_of(wiki_dir, subpath):
    """そのページが指しているページ。"""
    return pagedb.links_of(wiki_dir, subpath)


def backlinks_of(wiki_dir, subpath):
    """そのページを指しているページ（実体パス）を名前順で返す。

    リンク先はページパス（URLの形）で記録してあるので、実体パスのほうを
    そろえてから引く（`Tech/index` と `/Tech` を同じものとして数えるため）。"""
    return pagedb.backlinks_of(wiki_dir, "/" + pagepath_of_subpath(subpath))
