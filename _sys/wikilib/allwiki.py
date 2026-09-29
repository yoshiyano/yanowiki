"""このサーバーで動いている全Wikiの一覧（既定では `/.allwiki`）。

1つのサーバーでいくつものWikiを動かせる（Wiki Farm）ので、**どこに何があるかを
1枚で見渡せる場所**を用意する。以前は新しいWikiを作る画面（`/.newwiki`）の下に
「いまあるWiki」を並べていたが、作る操作のついでに見るものではないので分けた。

## 開けるのは既定Wikiの管理者と助手だけ

関門は `/.newwiki`・`/.restart` と同じ `sysui.require_on_default_farm`
（Wiki設計者の指示、2026-09-16。「`.allwiki` は `.newwiki` と同様、デフォルト
wikiの admin 権限を持っている人のみ実行可能に。また `=subwiki/.allwiki` は
実行できないように」）。**`/=<Wiki名>/.allwiki` は既定Wikiのものでも403。**

これは妥当な線引きだと考える。ここに並ぶのは**このサーバーにある他のWikiの
名前＝そのままURL**で、非公開のWikiを立てていれば、その在り処を明かすことに
なる。一覧を見て回れるのは、Wikiを増やせる人（`/.newwiki` を開ける人）と
同じ範囲で足りる。

判定に使うのは**既定Wikiの管理者と助手（`g:staff`）**で、管理者だけには
絞っていない。`/.newwiki` と揃えるため（「`.newwiki` と同様」）で、
サービス全体に効く操作の持ち主を1組に保つという `require_on_default_farm` の
考えかたにも沿う。助手を外すなら `/.newwiki`・`/.restart` と一緒に変える話に
なる。

## URL名は設定で決まる

出す場所は `server.yaml` の `farm.allwiki` で決まり、既定は `allwiki`
（＝ `/.allwiki`）。**空にすると一覧を出さない。**

権限の関門が入った後もこの設定は残してある。**空にしたときは、権限のある人にも
出さない**（無いページとして扱う）——「このサーバーに一覧という画面は無い」と
いう運用を選べるようにするためで、関門とは目的が違う。名前を付け替えられるのも
同じ理由で、既定の名前で当てられたくない場合に変えられる。

## 何を並べるか

名前だけでは中身が分からないので、そのWikiの**トップページの見出し**と
**ページ数**を添える。どちらもDB（pageinfo/wikiall.db）から引くので、
Wikiの数が増えてもファイルを開いて回らずに済む。

まだ取り込まれていない（DBが無い）Wikiもあり得るので、その場合は数を出さずに
名前とリンクだけを出す。**開けること**のほうが大事なので、数が分からなくても
一覧から外さない。
"""
import os
from html import escape
from urllib.parse import quote as urlquote

from wikilib import pagedb, sysui
from wikilib.paths import (
    ALLWIKI_DIR, FARM_PREFIX, INDEX_NAME, WIKIDATA_DIR,
    farm_wiki_dir,
)
from wikilib.themes import make_plugin_context
from wikilib.web import serve_asset
from wikilib.wikiconfig import allwiki_command, load_default_farm


def wiki_names():
    """いま在るWikiの名前（wiki/ を持つフォルダだけを数える）。"""
    try:
        entries = sorted(os.listdir(WIKIDATA_DIR))
    except OSError:
        return []
    return [e for e in entries
            if os.path.isdir(os.path.join(WIKIDATA_DIR, e, "wiki"))]


def wiki_entries():
    """一覧に出す [{name, title, pages}, …]。DBが無ければ title/pages は空。"""
    found = []
    for name in wiki_names():
        wiki_dir = farm_wiki_dir(name)
        if wiki_dir is None:
            continue
        entry = {"name": name, "title": "", "pages": None}
        if pagedb.is_usable(wiki_dir):
            subpaths = pagedb.all_subpaths(wiki_dir)
            entry["pages"] = len(subpaths)
            info = pagedb.load_page_info(wiki_dir, INDEX_NAME)
            entry["title"] = (info or {}).get("title", "")
        found.append(entry)
    return found


def site_root_of(base_url):
    """Wiki名を付ける前のURL。`/=sandbox` を見ているときでもサイトの根に戻す。

    関門（`render_allwiki`）を通った時点で、開いているのは素の `/.allwiki` だけ
    なので `base_url` にWiki名は入っていない。ここは念のための処理として残す。"""
    return base_url.rsplit("/" + FARM_PREFIX, 1)[0]


def render_allwiki(wiki_dir, config, farm, explicit_farm):
    """全Wikiの一覧。設定で止められていれば「無いページ」として扱う。

    **見られるのは既定Wikiの管理者と助手だけ**（Wiki設計者の指示、2026-09-16。
    冒頭の説明参照）。確かめるのは**中身を組み立てる前**——並べる名前そのものが
    隠したい情報なので、`wiki_entries()` を呼ぶより先に断る。

    設定で止められているかを先に見るのは、そちらが**画面の有無**の話で、
    権限の有無より前に決まるため。止めてあれば、権限のある人にも無いページを
    返す。"""
    from wikilib import sysui  # 循環を避けるため呼び出し時に読み込む
    from wikilib.views import render_no_page

    command = allwiki_command(config)
    if not command:
        return render_no_page(wiki_dir, config, farm, "", explicit_farm)

    urlpath = "." + command
    denied = sysui.require_on_default_farm(config, farm, wiki_dir, explicit_farm,
                                           urlpath)
    if denied is not None:
        return denied

    context = make_plugin_context(config, farm, wiki_dir, urlpath, explicit_farm)
    root = site_root_of(context.base_url)
    default_farm = load_default_farm(config)

    rows = []
    for entry in wiki_entries():
        name = entry["name"]
        url = "{}/{}{}/".format(escape(root), FARM_PREFIX, escape(urlquote(name)))
        marks = []
        if name == default_farm:
            # 名前を付けずに開いたときに出るWiki。どれが表かは知りたい情報
            marks.append('<span class="allwiki-default">既定</span>')
        if name == farm:
            marks.append('<span class="allwiki-here">いま見ています</span>')
        count = ("—" if entry["pages"] is None
                 else "{}ページ".format(entry["pages"]))
        rows.append(
            '<li class="allwiki-item">'
            f'<a class="allwiki-name" href="{url}">{escape(name)}</a>'
            + "".join(marks) +
            f'<span class="allwiki-title">{escape(entry["title"])}</span>'
            f'<span class="allwiki-count">{count}</span>'
            "</li>"
        )

    listing = ('<ul class="allwiki-list">' + "".join(rows) + "</ul>" if rows else
               '<p class="allwiki-empty">Wikiがまだありません。</p>')
    body = f"""<div class="allwiki">
  <p class="allwiki-lead">このサーバーで動いているWikiの一覧です。
    名前を押すと、そのWikiのトップページへ移ります。</p>
  {listing}
  <p class="allwiki-hint">新しく増やしたいときは
    <a href="{escape(root)}/.newwiki">新しいWikiを作る</a>、
    消したいときは <a href="{escape(root)}/.delwiki">Wikiを消す</a> からどうぞ。</p>
</div>
<link rel="stylesheet" href="{escape(context.base_url)}/{escape(urlpath)}.css">
"""
    return sysui.page(wiki_dir, config, farm, explicit_farm, urlpath, "Wikiの一覧", body)


def serve_allwiki_asset(name):
    """Wiki一覧が自前で持つCSS（/.allwiki.css）。"""
    return serve_asset(ALLWIKI_DIR, "allwiki", name, kinds=("css",))
