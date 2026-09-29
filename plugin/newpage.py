"""newpage — ページ名を入れて新しいページを作るための入力欄を出す、ブロック専用のプラグイン。

    #newpage()                   空の入力欄
    #newpage(./)                 このページの下に作る（入力欄に ./ を入れておく）
    #newpage(研究情報/)           研究情報 の下に作る
    #newpage(研究情報/, showlist)  入力欄の下に 研究情報 の下のページの一覧も出す
    #newpage(./, label=レポートを作る, button=作成, placeholder=第01回)

 1. page        … 入力欄に最初から入れておくページ名（1番目に固定） (default: 空)
       書きかたは本文のリンク [[ページ名]] と同じ決まりです。
       研究情報/ も /研究情報/ もwikiの先頭から、./ はこのページの下、
       ../ は1つ上から
 2. showlist    … 単語を書くと、入力欄の下に page の下のページの一覧を出す
       (default: 出さない)。`#newpage(研究情報/)` の次の行に
       `#ls(研究情報/)` を書いたのと同じ一覧です。page を省くときは
       `#newpage(, showlist)` のように1番目を空けます（このページの下の一覧）
 3. label       … `label=値` の形でのみ。入力欄の前の文字 (default: ページ新規作成)
 4. button      … `button=値` の形でのみ。ボタンの文字 (default: 編集)
 5. placeholder … `placeholder=値` の形でのみ。入力欄が空のときに薄く出す例 (default: 出さない)

ボタンを押すと、入れた名前をこのページから見て解決し、

- そのページがまだ無ければ、すぐに新規作成の編集画面が開きます
- もう在れば、そのページを開きます

入力欄を空のまま押すことはできません。このページを編集できない閲覧者には、
入力欄そのものを出しません。`showlist` の一覧は、入力欄を出さないときも出します
（`#ls` を並べて書いた場合と同じ）。

エラーになる書きかた:

- 作れない名前（`=` や `.` で始まる部分を含む名前）を入れて押した
  （「ページ名が正しくありません」と表示されます）
"""

""" 技術資料
本家 `~/pukiwiki/.wkcommon/plugin/newpage.inc.php` を読んで移植した。

## 本家の動き

- `_convert`: `refer`（いまのページ）と `page`（入力欄。引数1つ目を
  `$BracketName` に合えば初期値にする）を `?plugin=newpage` へPOSTするフォーム。
  ラベルは `$_msg_newpage`（ja: ページ新規作成）、ボタンは `$_btn_edit`（ja: 編集）、
  入力欄は `size="30"`。`PKWK_READONLY` なら何も出さない。
- `_action`: `page` が空ならフォームだけのページを出す。空でなければ
  `strip_bracket` → `get_fullname(page, refer)`（`./` 等を refer から解決）→
  `?cmd=read&page=…` へリダイレクト。`read` は在るページなら表示、無ければ
  そのまま編集画面を出すので、結果として「無ければ即編集」になる。

## このシステムでの置き換え

- 解決は `paths.full_pagepath(refer, page)`（`get_fullname` と同じ決まり）。
- **無いページ → 307 で同じPOSTを相手のページのURLへ渡す。** このシステムの
  編集画面は「そのページ自身の通常URLへ `cmd=edit` をPOST」でしか開かない
  （GETは常に閲覧画面。`Tech/EditGuide`）。フォームに `cmd=edit` を hidden で
  入れておき、`_action` が 307（メソッドと本文を保ったまま転送する）で
  `/<ページ>` へ送り直すと、ブラウザが同じ本文をPOSTし直して編集画面が開く。
  `page`/`refer` のフィールドも一緒に届くが、編集画面はこの名前を読まない
  （`editor.py` が読むのは `cmd`/`origin`/`tab`/`source` 等）。JavaScriptは要らない。
  303（GET）で `/<ページ>` へ送ると「このページはまだありません」の画面を
  挟むことになり、本家より1クリック多くなる。
- **在るページ → 303 で閲覧画面へ。** 本家の `cmd=read` と同じ。
- 空の名前: 本家はフォームだけのページを出したが、入力欄に `required` を
  付けてブラウザ側で止め、それでも空で届いたら（JS/HTML5以前の環境）元の
  ページへ 303 で戻すだけにした。フォームだけのページをテーマ付きで組む口が
  `_action` に無いため。
- `[[名前]]` の角括弧は本家の `strip_bracket` どおり外す。
- `PKWK_READONLY` の代わりに、閲覧者がこのページを編集できない
  （`context.privilege.check(page)` が `W` でない）ときは何も出さない。作る先のページの権限はまだ分からないので、
  いまのページの権限で代用している（編集できない閲覧者に入力欄を見せても、
  押した先の編集画面が403で断るだけになるため）。権限の最終判断は編集画面側
  （`editor.render_edit`）が行う。
## 編集権限の無い閲覧者（2026-09-25、設計者の指示で確認）

設計者の指示:「編集権限を持たないユーザに対してはフォームを表示させない。showlist が
あれば ls としてのみ動作させる」。最初の実装からこの方針（上の「`PKWK_READONLY` の
代わりに…」）だったが、権限を判定できずに例外が出たときだけは「出す」側に倒して
いた。指示の趣旨（編集できない閲覧者にフォームを見せない）に対して危うい側なので、
「出さない」側に直した。判定は `context.privilege.check(いまのページ)` が `W` かどうか
（テーマが編集の入口を出すかの判定 `ref.privilege == PAGE_WRITE` と同じ判定器）。
フォームを出さないときも `showlist` の一覧は出すので、`#newpage(hoge/, showlist)` は
編集できない閲覧者には `#ls(hoge/)` とまったく同じ出力になる（一時的なWikiで、
編集できる人・できない人・未ログインの人を作って確かめた）。

- `page` 引数は `link: True` にしていない。値は「入力欄に最初から入れておく
  文字」で、`./` や `研究情報/` のように**名前の前半（フォルダの接頭辞）**を
  書くのが実際の使いかた（2026-09-25に `~/pukiwiki/*/wiki/*.txt` を調べた範囲で
  `#newpage(./)` 41件、`#newpage(フォルダ/)` 多数）。リンクとして記録すると
  `./` が自分自身へのリンクとして数えられるなど、参照関係として意味を持たない。
- 入力欄の `id` は本家の `_p_newpage_<連番>` にならい、1ページに複数置いても
  `<label for>` がずれないよう `context._newpage_counters`（ページごとの連番。
  `comment.py` と同じ持ち回しかた）で振る。
- 本家に無い `label`/`button`/`placeholder` は、表示文字を差し替えたいという
  よくある要望に応えるための拡張（既定値は本家の文字のまま）。最初は位置引数
  （2〜4番目）で作ったが、同じ日に `showlist` を単語で書けるようにしたとき
  `kw_only` に改めた（位置のままだと `#newpage(hoge/,showlist)` の `showlist` が
  `label` に入る。位置で書いたページはまだ無かった）。

## showlist（本家に無い拡張、2026-09-25）

設計者の指示:「showlist を付けた場合、newpage で指定したページの配下の一覧を
ページ作成の下に表示させる。#ls をそのまま利用すればよい」。`#newpage(hoge/)` ＋
`#ls(hoge/)` の2行を `#newpage(hoge/,showlist)` の1行で書けるようにするもの。

`ls` の処理を複製せず、`wikilib.plugins.call_plugin(context, "ls", 引数, None,
"_convert", "#")` で**本文に `#ls(hoge/)` と書いたときと同じ経路**で呼ぶ。引数の
束ね・`ls` 自身のエラー表示・`context.used_plugins` への記録（`ls.css`/`ls.js` の
読み込み）まで `#ls` と同じになる。フォルダは `page` の値を引用符で囲んでそのまま
渡すだけ（`ls` も `full_pagepath` で同じページから解決するので、`./` も含めて
`#ls(同じ値)` と同じ場所になる）。`page` が空なら `#ls()`（このページの下）。

**返り値に `#ls(...)` という文字列を埋めて再展開させる方法は使えない。**
2026-09-02 以降、プラグインの返り値は再パースされない（`call_plugin` の
「プラグインが返したものは、そのまま出す」）。`expand_*` が展開するのは
中身（body）だけ。
"""

from html import escape
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib.auth import PAGE_WRITE
from wikilib.pagedb import resolve_page_ref
from wikilib.paths import PLUGIN_URLPATH, full_pagepath, is_valid_pagepath
from wikilib.plugins import FREE_TEXT, call_plugin
from wikilib.web import plain

PLUGIN_INFO = {
    "help": "#newpage(page,showlist,label,button,placeholder)",
    "args": [
        {"name": "page", "num_order": 1, "candidate": [FREE_TEXT], "default": ""},
        {"name": "showlist", "flag": True, "default": False},
        {"name": "label", "kw_only": True, "default": "ページ新規作成"},
        {"name": "button", "kw_only": True, "default": "編集"},
        {"name": "placeholder", "kw_only": True, "default": ""},
    ],
}


def _strip_bracket(name):
    """本家の strip_bracket: `[[名前]]` と書かれていたら角括弧を外す。"""
    name = (name or "").strip()
    if name.startswith("[[") and name.endswith("]]"):
        name = name[2:-2].strip()
    return name


def _can_edit(context):
    try:
        return context.privilege.check((context.page or "").strip("/")) == PAGE_WRITE
    except Exception:
        # 権限を判定できないときは出さない（編集できない閲覧者にフォームを見せない
        # ことを優先する。技術資料「編集権限の無い閲覧者」参照）
        return False


def _next_id(context):
    counters = getattr(context, "_newpage_counters", None)
    if counters is None:
        counters = {}
        context._newpage_counters = counters
    page = context.page or ""
    counters[page] = counters.get(page, 0) + 1
    return counters[page]


def _list_html(resolved, context):
    """showlist: `#ls(page)` と書いたときと同じ経路で一覧を作る。"""
    folder = _strip_bracket(resolved["page"])
    if not folder:
        argstr = ""
    else:
        quote = "'" if '"' in folder else '"'
        argstr = f"{quote}{folder}{quote}"
    return call_plugin(context, "ls", argstr, None, "_convert", "#")


def _convert(resolved, body, context):
    listing = _list_html(resolved, context) if resolved["showlist"] else ""
    if not _can_edit(context):
        return listing
    api = escape(f"{context.base_url}/{PLUGIN_URLPATH}/newpage", quote=True)
    field_id = f"_p_newpage_{_next_id(context)}"
    placeholder = resolved["placeholder"] or ""
    placeholder_attr = f' placeholder="{escape(placeholder, quote=True)}"' if placeholder else ""
    return (
        f'<form class="newpage" method="post" action="{api}">\n'
        " <div>\n"
        '  <input type="hidden" name="cmd" value="edit">\n'
        f'  <input type="hidden" name="refer" value="{escape(context.page or "", quote=True)}">\n'
        f'  <label for="{field_id}">{escape(resolved["label"] or "")}:</label>\n'
        f'  <input type="text" name="page" id="{field_id}"'
        f' value="{escape(_strip_bracket(resolved["page"]), quote=True)}" size="30" required{placeholder_attr}>\n'
        f'  <input type="submit" value="{escape(resolved["button"] or "", quote=True)}">\n'
        " </div>\n"
        "</form>\n"
        + listing
    )


def _action(context):
    refer = (request.forms.getunicode("refer", "") or "").strip("/")
    name = _strip_bracket(request.forms.getunicode("page", ""))
    if not name:
        return HTTPResponse(status=303, headers={"Location": f"{context.base_url}/{urlquote(refer)}"})

    pagepath = full_pagepath(refer, name).strip("/")
    if not pagepath:
        # トップ階層で `./` だけを送った場合など。トップページは必ず在るのでそこを開く
        return HTTPResponse(status=303, headers={"Location": f"{context.base_url}/"})
    if not is_valid_pagepath(pagepath):
        return plain(f"ページ名が正しくありません: {name}", status=400)

    ref = resolve_page_ref(context.wiki_dir, pagepath)
    if ref is None:
        return plain(f"ページ名が正しくありません: {name}", status=400)
    target = f"{context.base_url}/{urlquote(pagepath)}"
    if ref.exists:
        return HTTPResponse(status=303, headers={"Location": target})
    # 無いページ: cmd=edit を含む同じPOSTを、そのページのURLへ送り直させる（編集画面が開く）
    return HTTPResponse(status=307, headers={"Location": target})
