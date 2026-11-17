"""htmlref — 添付ファイルの HTML へのリンク。管理者が承認した HTML だけ、スクリプトを動かして開く。

    #htmlref(src)                          書いて保存すると、承認待ちの印（reqXX）が付く
    #htmlref(src, reqAB)                   承認待ち（管理者には［承認］ボタンが出る）
    #htmlref(src, as_XXXXXXXXXX)           承認済み（スクリプトが動く形で開く）
    #htmlref(src, title=説明書)              表示する文字を変える

 1. **src** … 添付ファイルの名前（拡張子が html・htm・HTML・HTM のもの。省略不可、常に1番目）
       書きかたは `ref` と同じ（`demo.html`・`../demo.html`・`/Tech/demo.html` など）
 2. allow … 承認待ちの印（`req` ＋ 2文字）か、承認のキー（`as_` ＋ 10文字）
       (default: 無し。ページを開いたときに承認待ちの印が書き足されます)
       自分で書く必要はありません。どちらも書き手が書き換えるものではありません
 3. title … 表示する文字。`title=…` と名前を付けて書きます (default: ファイル名)

添付の HTML は、ふだん（`/.attach/…` や `&ref`）はスクリプトが動かない形で開きます。
`#htmlref` で参照し、**管理者が承認した HTML だけ**、スクリプトが動く形で開きます。

- `#htmlref(demo.html)` と書いて保存すると、ページを開いたときに `#htmlref(demo.html, reqAB)`
  のような承認待ちの印が書き足されます。この間のリンクは、スクリプトが動かない形で開きます
- 管理者がそのページを開くと、承認待ちの `#htmlref` に［承認］ボタンが出ます。押すと印が
  承認のキー（`as_…`）に書き換わり、以後、そのリンクはスクリプトが動く形で開きます
- 承認のあとで添付を差し替えると、キーが合わなくなりエラーになります。キーを消して
  （`#htmlref(demo.html)` に戻して）保存し、もう一度承認してもらってください
- メニューや `#include` で差し込んだページの中では［承認］ボタンは出ません。差し込み元の
  ページを直接開いて承認してください

スクリプトが動く形で開いても、HTML は Wiki とは別のオリジンとして扱われます（Wiki の
cookie やログインの状態には触れません）。フォームの送信・ポップアップも許しません。
同じページの他の添付（CSS・JS・画像）を相対パスで読み込む HTML には対応していません。
"""

""" 技術資料
## 経緯と、決まったこと（設計者の指示）

添付の配信（`/.attach/…`。`_sys/wikilib/attach.py` の `guard_attach_response`）は、PDF 以外の
すべてに `Content-Security-Policy: sandbox` を付けるため、添付 HTML のスクリプトは動かない。
`sandbox allow-scripts` へ一律に緩める案は、設計者が「厳しい形のままでOK」として退けた
（スクリプトで偽のログイン画面を作れるため。2026-10-19）。

そこで、本体（`_sys`）を改造せず、**管理者が承認した HTML に限って** `allow-scripts` で開く
しくみを作ることになった。最初は `ref` に `allowscript` オプションを足す形で依頼された
（wikiSystem セッションから。2026-11-16）が、設計者が「実装が複雑になるため」中止し、
HTML 参照専用の新しいプラグインとして作り直すよう指示した（同日）。以下は設計者が決めたこと。

- HTML 参照専用のプラグイン。ハッシュ値（キー）が書かれていればスクリプトを許可し、
  誤ったキーはエラーにする。キーの作りかたは `ref` 改造のときの案に準じる
- オプション（キー）が無ければ、描画時に `reqXX`（XX はページ内で重ならない2文字）を
  書き足して保存する。描画時に XX が重なっていたら、後のほうを振り直す
- **ブロック記法だけ**（2026-11-16、設計者の選択。インラインも書けるようにする案は、
  本文の中の呼び出しを探す手間（下記）と［承認］のための JS が増えるので取らなかった）
- 見せかたは**リンクだけ**（同、設計者の選択。ページに iframe で埋め込む案は取らなかった）
- 承認の流れは `ref` 改造のときの決定をそのまま引き継ぐ（同）:
  - 管理者が閲覧したとき、`reqXX` の呼び出しにだけ［承認］ボタンを出す
  - ［承認］は `_action` へ送り、**その `reqXX` が本文中で一意に特定できたときだけ**キーに
    書き換えて保存する。複数一致したら重ならないように振り直してリロードし、もう一度
    承認させる。見つからないなど特定できなければ、書き換えずにリロードだけ
  - キーが合わない値（承認後に添付が変わった等）はエラー表示
  - メニュー・`#include` で差し込んだページなど、閲覧中のページでない場所では［承認］を出さない
  - 単体の HTML だけが対象。同じページの他の添付を相対パスで読ませる対応（`<base>` の
    差し込み等）はしない
  - 編集の衝突は、通常のページの編集衝突と同じ扱い。承認の情報が消えても、再度承認すればよい
  - キーの書き写し（同じページの別の呼び出しへのコピー）は問題にしない。キーが表すのは
    「管理者がそのファイル（その中身）を許可したか」だけ
  - 対象の拡張子は `html` `htm` `HTML` `HTM` だけ（`.Html` のような混在は対象外）

## キー（依頼元クロコの案を採用。設計者は方向に同意済み、細部は未確認）

HMAC-SHA256（鍵は `wikilib.auth.site_secret()`）に「`#htmlref` を書いたページの subpath ＋
添付（持ち主の subpath/ファイル名）＋添付の中身の SHA-256」をかけ、base64url の先頭10文字に
`as_` を付けたもの（`allow_key`）。

- 中身を含めるので、承認のあとで同じ名前で上書きされるとキーが合わなくなる
- ページと添付の置き場所を含めるので、ページや添付の名前を変えるとキーが合わなくなる
  （エラーになり、承認し直しになる）。クロコの見立てで、設計者は未確認
- 鍵を持たない書き手は、キーを作れない（10文字＝60ビット。描画で総当たりするのは現実的でない）

## 引数（クロコの実装例）

- `allow` は自由順序の項目で、`candidate` を `req`＋2文字 と `as_`＋10文字 の正規表現にした
  （設計者の「reqXX というオプション」をそのまま、名前を付けずに書ける形にした）
- `title` は**名前付き（`title=…`）でしか受けない**（`kw_only`）。`ref` のように「残りの
  位置引数」で受けると、形の崩れたキー（`as_` の書き損じ）が黙って表示文字になり、
  承認待ちの印が新しく付いてしまう。名前付きにしておけば、`src` の後ろに書いた位置引数は
  `allow` の形に合わなければ引数のエラーになる（設計者の「誤ったハッシュ値はエラー」を、
  形の崩れた値まで広げた）
- 拡張子が対象外・外部 URL・ページを指した `src` は引数のエラーにする（HTML 参照専用のため）

## 本文の中の呼び出しを探す

描画時の書き足し・振り直しと、［承認］の受信の両方で、保存されている本文の `#htmlref` を
`plugin/_polling.py` の `scan` で探す（`names=("htmlref",)` を渡す）。ページと同じパーサーの
トークンから拾うので、`#code` の本体の中は数えず、`#note` 等の本体や `#table` のセルの
中は見る。`#comment` が以前、通し番号方式で別のフォームへ書き込んでいた経緯があるため。
描画時に印を付けて重なりを振り直す考えかたも、`_polling.py` 冒頭の「呼び出しごとの ID の
決まり」（設計者の指示）と同じ。違いは、印を `id="…"` ではなく `allow` の値に持つこと。

ブロック記法だけにしたので、`scan` がそのまま使える（`scan` はブロックの呼び出しだけを探す。
インラインの呼び出しは、PukiWiki 記法ではトークンに行番号が付かず、位置の推定が要る）。

- **書き足すのは閲覧中のページの描画だけ**（`_viewing`）。メニュー（`context.in_menu`）・
  部分プレビュー（`context.partial`）・URL のページと違うページ（`#include` の中など）・
  `_action` の中・取り込み（`./wiki.py updatepage`。要求が無い）では書き足さない。
  URL のページは、本体の振り分け（`wiki.py` の `dispatch`）と同じく `request.path` から
  `strip_url_prefix`・`split_farm_and_page` で取り出す
- 書き足しは、ページごとに最初の `#htmlref` の描画で、全部の分を1度に保存する。保存の
  直前に本文が変わっていたら読み直す（3回まで）。保存すると、本体が新しい本文で最初から
  描き直す（`pagesave.watch_writes`）
- 書く位置は `_polling.locate` が返す丸括弧の中の範囲から求める。`allow` の値があれば
  それを、無ければ引数の終わりに `, reqXX` を足す

## ［承認］（クロコの実装例）

ブロックなので、ふつうの `<form method="post">` を置ける（JavaScript 無しで動く）。送る値は
ページ・`reqXX`・描いた時点の添付の SHA-256。`_action` は:

1. 管理者（`auth.ADMIN_ONLY`）かを確かめ直す（違えば 403）
2. 本文で `reqXX` の `#htmlref` を探す。1つなら、添付の今の SHA-256 が送られた値と同じか
   確かめ（押す直前の差し替え対策）、キーに書き換えて保存する。複数なら後のほうを振り直して
   保存する。無ければ何もしない
3. どの場合も、ページへ 303 で戻す（リロード）

保存は通常のページ保存（`pagesave.save_page`）。別サイトからの POST は、本体が `_action` の
前に 403 で断る（`wiki.py` の `dispatch`、`web.cross_site_reason`）。

## 配信（`_action` の GET。クロコの実装例）

承認済みの `#htmlref` は、リンクを `/.plugin/htmlref?page=<書いたページ>&src=<src>&key=<キー>`
にする。`_action` は、閲覧の権限（`attach.attach_viewable`。添付の配信と同じ判定）・拡張子・
キーを毎回確かめ、`bottle.static_file` で返して次の見出しを付ける。返せないときは、理由を
問わず添付の配信と同じ 404（`attach.attach_not_found`）。

- `Content-Security-Policy: sandbox allow-scripts`（`allow-same-origin` は付けない。
  Wiki とは別のオリジンのまま。フォームの送信・ポップアップ・最上位の移動も許さない）
- `X-Content-Type-Options: nosniff`
- `Content-Type` は `static_file` が付ける `text/html; charset=UTF-8`

## 表示（クロコの実装例）

- リンクは `ref` のファイルの札と同じ形（名前・種別・大きさと更新日時）。CSS は `htmlref.css`
  （`ref` を使っていないページでも見た目が揃うよう、`ref.css` と同じ値を持つ）
- 承認待ち・未承認には「スクリプト承認待ち」の札を添え、リンクは `/.attach/…`
  （スクリプトが動かない形）にする。承認済みには「スクリプト許可」の札を添える
- 持ち主のページを閲覧できない添付は、`ref` と同じく「閲覧できないファイル」の札だけ
  （実在の確認より先に見る）
- `/.attach/` 向けの右クリックメニュー（`ref.js`）は付けない
"""

import base64
import datetime
import hashlib
import hmac
import importlib.util
import os
import random
import re
import string
from html import escape
from urllib.parse import quote as urlquote
from urllib.parse import urlencode

from bottle import HTTPResponse, request, static_file

from wikilib import auth
from wikilib.attach import (attach_dir_for, attach_kind, attach_not_found, attach_viewable,
                            format_bytes)
from wikilib.auth import PAGE_NONE
from wikilib.pagesave import save_page
from wikilib.pagesync import farm_of_wiki_dir
from wikilib.paths import (PLUGIN_URLPATH, as_attach_link, is_valid_pagepath, pagepath_of_subpath,
                           resolve_link, resolve_page_ref)
from wikilib.plugins import PluginArgumentError, parse_plugin_args_spans
from wikilib.web import plain
from wikilib.wikiconfig import load_config, split_farm_and_page, strip_url_prefix, url_prefix

NAME = "htmlref"
EXTS = ("html", "htm", "HTML", "HTM")  # `.Html` のような混在は対象外（設計者の指示）
REQ_PREFIX = "req"
REQ_CHARS = string.digits + string.ascii_letters
REQ_LEN = 2
KEY_PREFIX = "as_"
KEY_LEN = 10
REQ_RE = r"req[0-9A-Za-z]{2}"
KEY_RE = r"as_[0-9A-Za-z_-]{10}"
KEY_SALT = "htmlref-1"
CSP = "sandbox allow-scripts"
STALE = ("添付が変わったため、承認し直しが必要です"
         "（キーを消して #htmlref(ファイル名) に戻して保存し、管理者が承認）")
_RETRY = 3

PLUGIN_INFO = {
    "help": "#htmlref(src,allow,title)",
    "args": [
        {"name": "src", "num_order": 1, "link": "attach"},
        {"name": "allow", "default": None, "candidate": [(f"{REQ_RE}|{KEY_RE}", "re")],
         "label": "承認"},
        {"name": "title", "kw_only": True, "default": None, "label": "表示する文字"},
    ],
}


# ---- 添付 ----

def _is_html(name):
    return "." in name and name.rsplit(".", 1)[1] in EXTS


def _target(wiki_dir, page, src):
    """`page` に書いた `src` の (種類, 値)。添付なら値は `持ち主のsubpath/ファイル名`。"""
    ref = resolve_page_ref(wiki_dir, page or "")
    if ref is None:
        return None, None
    return resolve_link(ref.subpath, as_attach_link(src), wiki_dir)


def _attach_path(wiki_dir, target):
    owner_subpath, _, name = target.rpartition("/")
    directory = attach_dir_for(wiki_dir, owner_subpath)
    return os.path.join(directory, name) if directory else None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allow_key(wiki_dir, page, target, sha):
    """承認のキー（技術資料「キー」）。"""
    ref = resolve_page_ref(wiki_dir, page or "")
    page_subpath = ref.subpath if ref is not None else (page or "")
    message = "\0".join((KEY_SALT, page_subpath, target, sha)).encode("utf-8")
    mac = hmac.new(auth.site_secret().encode("utf-8"), message, hashlib.sha256).digest()
    return KEY_PREFIX + base64.urlsafe_b64encode(mac).decode("ascii")[:KEY_LEN]


def _is_admin(context):
    return auth.allows(context.wiki_dir, farm_of_wiki_dir(context.wiki_dir), auth.ADMIN_ONLY)


def _viewing(context):
    """閲覧中のページそのものを描いているか（技術資料「本文の中の呼び出しを探す」）。"""
    if (context.partial or getattr(context, "in_menu", False) or context.page is None
            or not context.wiki_dir):
        return False
    try:
        path = request.path
    except (RuntimeError, KeyError):
        return False
    config = load_config()
    urlpath = strip_url_prefix(path.lstrip("/"), url_prefix(config))
    farm, page, _explicit = split_farm_and_page(urlpath, config)
    if farm != farm_of_wiki_dir(context.wiki_dir):
        return False
    return page.strip("/") == (context.page or "").strip("/")


# ---- 本文の中の呼び出し ----

def _load_polling():
    """兄弟の `_polling.py`（呼び出しを探す `scan` を借りる）を読み込む。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_polling.py")
    spec = importlib.util.spec_from_file_location("wikiplugin__polling", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _allow_span(args):
    """引数の文字列 `args` の中の `allow` の値と位置。(値か None, (開始, 終了)か None)。
    値が無ければ位置も None（技術資料「引数」と同じ束ねかた）。"""
    positional, keyword = parse_plugin_args_spans(args)
    if "allow" in keyword:
        value, span = keyword["allow"]
        return value, span
    for item in positional[1:]:
        if item is not None and re.fullmatch(f"{REQ_RE}|{KEY_RE}", item[0]):
            return item
    return None, None


def find_calls(context, text, ext):
    """保存されている本文 `text` の、描かれる `#htmlref` を本文の順に返す。
    [{"line", "loc", "value", "span"（行の中の値の位置か None）}]"""
    out = []
    for call in _load_polling().scan(context, text, ext, names=(NAME,)):
        loc = call["loc"]
        if not loc["paren"]:
            continue
        a0, a1 = loc["args"]
        line = text.split("\n")[call["line"]]
        value, span = _allow_span(line[a0:a1])
        out.append({"line": call["line"], "loc": loc, "value": value,
                    "span": (a0 + span[0], a0 + span[1]) if span else None})
    return out


def _new_req(taken):
    while True:
        value = REQ_PREFIX + "".join(random.choice(REQ_CHARS) for _ in range(REQ_LEN))
        if value not in taken:
            return value


def _retag(calls):
    """印の無い呼び出しと、ページの中で重なった `reqXX` の後のほうへ、新しい `reqXX` を
    振る。[(呼び出し, 新しい値)]"""
    taken = {c["value"] for c in calls if c["value"]}
    seen = set()
    changes = []
    for call in calls:
        value = call["value"]
        if value and not value.startswith(REQ_PREFIX):
            continue  # 承認のキー（書き写しは問題にしない）
        if value and value not in seen:
            seen.add(value)
            continue
        new = _new_req(taken)
        taken.add(new)
        seen.add(new)
        changes.append((call, new))
    return changes


def _rewrite(text, changes):
    """`changes`（[(呼び出し, 新しい値)]）を書いた本文。1行に複数あれば右から書き換える。"""
    lines = text.split("\n")
    for call, value in sorted(changes, key=lambda c: (c[0]["line"], -c[0]["loc"]["pos"])):
        line = lines[call["line"]]
        if call["span"] is not None:
            s, e = call["span"]
            lines[call["line"]] = line[:s] + value + line[e:]
        else:
            a0, a1 = call["loc"]["args"]
            sep = ", " if line[a0:a1].strip() else ""
            lines[call["line"]] = line[:a1] + sep + value + line[a1:]
    return "\n".join(lines)


def _save(context, ref, text, new_text):
    """読んだときの本文 `text` が変わっていなければ `new_text` を保存する。"""
    now = resolve_page_ref(context.wiki_dir, ref.pagepath)
    if now is None or not now.exists or (now.body or "") != text:
        return False
    return bool(save_page(context.wiki_dir, context.config, ref.subpath, ref.ext, new_text,
                          path=ref.path))


def _tag_page(context):
    """閲覧中のページの `#htmlref` に印を付け、重なりを振り直して保存する（ページごとに
    最初の1回）。保存したら、本体がこの描画を捨てて描き直す。"""
    done = getattr(context, "_htmlref_pages", None)
    if done is None:
        done = context._htmlref_pages = set()
    if context.page in done:
        return
    done.add(context.page)
    for _ in range(_RETRY):
        ref = resolve_page_ref(context.wiki_dir, context.page or "")
        if ref is None or not ref.exists:
            return
        text = ref.body or ""
        changes = _retag(find_calls(context, text, ref.ext))
        if not changes or _save(context, ref, text, _rewrite(text, changes)):
            return


# ---- 描く ----

def _approve_form(context, value, sha):
    action = f"{context.base_url}/{PLUGIN_URLPATH}/{NAME}"
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{escape(v, quote=True)}">'
        for k, v in (("page", context.page or ""), ("req", value), ("sha", sha)))
    return (f'<form class="plugin-htmlref-approve" method="post" action="{escape(action, quote=True)}">'
            f'{hidden}<button type="submit" title="この HTML のスクリプトの実行を許可します（管理者）">'
            '承認</button></form>')


def _convert(resolved, body, context):
    src = (resolved["src"] or "").strip()
    if not src:
        raise PluginArgumentError("ファイルを指定してください: #htmlref(src)")
    if not context.wiki_dir:
        raise PluginArgumentError("ページの置き場所が分かりません。")

    kind, target = _target(context.wiki_dir, context.page, src)
    if kind != "attach":
        raise PluginArgumentError(f"添付ファイルの HTML を指定してください: {src}")
    owner_subpath, _, name = target.rpartition("/")
    if not _is_html(name):
        raise PluginArgumentError(
            f"HTML の添付ファイル（拡張子 {'・'.join(EXTS)}）を指定してください: {src}")
    label = resolved["title"] or name

    # 実在を確かめるより先に見る（読めないページの添付の有無を漏らさない。`ref` と同じ）
    if context.privilege.check(pagepath_of_subpath(owner_subpath)) == PAGE_NONE:
        return ('<div class="plugin-htmlref"><span class="plugin-htmlref-file">'
                f'<span class="htmlref-name">{escape(label)}</span>'
                '<span class="htmlref-kind htmlref-kind-denied">閲覧できないファイル</span>'
                '</span></div>')
    path = _attach_path(context.wiki_dir, target)
    if not path or not os.path.isfile(path):
        raise PluginArgumentError(f"見つかりません: {src}")

    allow = resolved["allow"]
    sha = _sha256(path)
    after = ""
    if allow and allow.startswith(KEY_PREFIX):
        if not hmac.compare_digest(allow, allow_key(context.wiki_dir, context.page, target, sha)):
            raise PluginArgumentError(STALE)
        query = urlencode({"page": context.page or "", "src": src, "key": allow})
        href = f"{context.base_url}/{PLUGIN_URLPATH}/{NAME}?{query}"
        mark = '<span class="htmlref-kind htmlref-kind-script">スクリプト許可</span>'
    else:
        viewing = _viewing(context)
        if viewing:
            _tag_page(context)
        href = as_attach_link(src)  # 表示時の書き換えで /.attach/… になる（`ref` と同じ）
        mark = '<span class="htmlref-kind htmlref-kind-pending">スクリプト承認待ち</span>'
        if viewing and allow and _is_admin(context):
            after = _approve_form(context, allow, sha)

    stat = os.stat(path)
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
    info = f"{format_bytes(stat.st_size)}・{mtime:%Y-%m-%d %H:%M} 更新"
    file_kind, kind_label = attach_kind(name)
    link = (f'<a href="{escape(href, quote=True)}" class="plugin-htmlref-file" '
            f'title="{escape(info, quote=True)}">'
            f'<span class="htmlref-name">{escape(label)}</span>'
            f'<span class="htmlref-kind htmlref-kind-{escape(file_kind, quote=True)}">'
            f'{escape(kind_label)}</span>'
            f'{mark}<span class="htmlref-info">{escape(info)}</span></a>')
    return f'<div class="plugin-htmlref">{link}{after}</div>'


# ---- _action ----

def _back(context, page):
    return HTTPResponse(status=303, headers={"Location": f"{context.base_url}/{urlquote(page)}"})


def _approve(context):
    """［承認］を受ける（技術資料「［承認］」）。"""
    if not _is_admin(context):
        return plain("承認できるのは管理者だけです。", status=403)
    page = (request.forms.getunicode("page", "") or "").strip("/")
    if page and not is_valid_pagepath(page):
        return plain("ページの指定が正しくありません。", status=400)
    req = request.forms.getunicode("req", "") or ""
    sha = request.forms.getunicode("sha", "") or ""
    ref = resolve_page_ref(context.wiki_dir, page)
    if ref is None or not ref.exists:
        return plain("そのページはまだありません。", status=404)

    sub = _page_context(context, page, ref.ext)
    text = ref.body or ""
    calls = find_calls(sub, text, ref.ext)
    hits = [c for c in calls if c["value"] == req] if req.startswith(REQ_PREFIX) else []
    if len(hits) > 1:
        # 重なっている。後のほうを振り直して、もう一度承認してもらう
        taken = {c["value"] for c in calls if c["value"]}
        changes = []
        for call in hits[1:]:
            new = _new_req(taken)
            taken.add(new)
            changes.append((call, new))
        _save(sub, ref, text, _rewrite(text, changes))
    elif len(hits) == 1:
        call = hits[0]
        line = text.split("\n")[call["line"]]
        a0, a1 = call["loc"]["args"]
        positional, keyword = parse_plugin_args_spans(line[a0:a1])
        if "src" in keyword:
            src = keyword["src"][0]
        else:
            src = positional[0][0] if positional and positional[0] else ""
        src = src.strip()
        kind, target = _target(context.wiki_dir, page, src) if src else (None, None)
        path = _attach_path(context.wiki_dir, target) if kind == "attach" else None
        if (path and os.path.isfile(path) and _is_html(target.rpartition("/")[2])
                and hmac.compare_digest(sha, _sha256(path))):
            key = allow_key(context.wiki_dir, page, target, sha)
            _save(sub, ref, text, _rewrite(text, [(call, key)]))
    return _back(context, page)


def _page_context(context, page, ext):
    from wikilib.plugins import PluginContext
    return PluginContext(config=context.config, farm=context.farm, wiki_dir=context.wiki_dir,
                         page=page, base_url=context.base_url, ext=ext)


def _serve(context):
    """承認済みの HTML を、スクリプトが動く形で返す（技術資料「配信」）。"""
    page = (request.query.getunicode("page", "") or "").strip("/")
    src = (request.query.getunicode("src", "") or "").strip()
    key = request.query.getunicode("key", "") or ""
    if (page and not is_valid_pagepath(page)) or not src or not key:
        return attach_not_found()
    kind, target = _target(context.wiki_dir, page, src)
    if kind != "attach" or not _is_html(target.rpartition("/")[2]):
        return attach_not_found()
    if not attach_viewable(context.wiki_dir, farm_of_wiki_dir(context.wiki_dir), target):
        return attach_not_found()
    path = _attach_path(context.wiki_dir, target)
    if not path or not os.path.isfile(path):
        return attach_not_found()
    if not hmac.compare_digest(key, allow_key(context.wiki_dir, page, target, _sha256(path))):
        return attach_not_found()
    directory, filename = os.path.split(path)
    response = static_file(filename, root=directory, mimetype="text/html")
    if response.status_code < 400:
        response.set_header("X-Content-Type-Options", "nosniff")
        response.set_header("Content-Security-Policy", CSP)
    return response


def _action(context):
    if request.method == "POST":
        return _approve(context)
    return _serve(context)
