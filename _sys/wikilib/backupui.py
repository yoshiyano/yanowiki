"""編集画面の「履歴」タブ（Wiki設計者の指示、2026-09-24・2026-09-28）。

右側の「すべて戻す」「部分的に戻す」の2タブは、どちらもdiffmerge（この時点↔現在）の
表示。差分計算やアルゴリズムはサーバー側で持たず、選んだ時点の本文と現在の本文を
そのまま渡して、あとはdiffmergeにまかせる（自前で差分を組み立てない。ライブラリ側の
更新に乗れるようにするため＝Wiki設計者の指示、2026-08-31）。

**テーマを使わない独立したページ**を `<iframe>` で編集画面に埋め込む。テーマのCSSも
読み込まない（theme/base.css等の`.content table`がdiffmergeの表と衝突していた不具合の
根も、これで断てる）。見た目と動きに必要なCSS/JSはこの機能自身が持つ
（`/.history.css`・`/.history.js`。中身は `_sys/backupui/`）。

- ページの選択は、編集画面のサイドバーの共通のページ一覧（editor.js）
- 履歴の一覧は、そのページ一覧の下（履歴タブのときだけ）に編集画面が出す。
  選ぶと親から `postMessage`（`wiki-backup-select`）で知らせ、ここが内容を出す
- **復元が済んだら、親の編集画面へ知らせる**（`postMessage`、`wiki-backup-restored`）。
  復元でページの保存内容が変わるので、編集画面は開き直す（editor.js）

## 受け口はページ自身のURL

以前は `/.backup` という別のURLだったが、**ページ自身のURLへのPOST（`?cmd=history`）**に
移した（Wiki設計者の指示、2026-09-28。`/.backup` をURLごとやめる）。プレビュー・差分
（`?cmd=preview`・`?cmd=diff`）と同じ形で、GETでは常に閲覧の画面が返る（URLだけを見ても
編集の入口があることが分からないようにする、編集画面と同じ決まり）。そのため
`<iframe>` も、iframe を宛先にしたフォームのPOSTで開く（editor.js）。

    POST <ページ>?cmd=history                      埋め込みの表示
    POST <ページ>?cmd=history  data=history|version 履歴の一覧・その時点の本文（JSON）
    POST <ページ>?cmd=history  do=restore|merge-restore  すべて戻す・部分的に戻す

**どれもそのページの編集の権限（`W`）が要る**（編集画面を開く条件と同じ）。
対象のページはURLから決め、フォームの値では受けない。

復元・部分復元のあとは、303で戻さずに、結果の知らせを添えた表示をそのまま返す
（戻り先をGETで開くと閲覧の画面になるため）。親は知らせを受けて編集画面を開き直すので、
この表示を読み込み直すことはない。
"""
from html import escape
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib.backup import (
    backed_up_subpaths, backup_history, content_rev, find_backup_version,
)
from wikilib.backupmerge import apply_partial_merge
from wikilib.pagedb import load_page_body, published_body
from wikilib.pagesave import save_page
from wikilib.paths import (
    BACKUPUI_DIR, HISTORY_URLPATH, VENDOR_URLPATH,
    page_ext_of_subpath, page_file_path, pagepath_of_subpath, resolve_page_ref,
)
from wikilib.themes import make_plugin_context
from wikilib import sysui
from wikilib.web import serve_asset


def may_edit(wiki_dir, farm, subpath):
    """いまの閲覧者が、実体パス subpath のページを編集できるか（編集画面と同じ判定）。"""
    from wikilib import auth  # 循環を避けるため呼び出し時に読み込む
    if not subpath:
        return False
    uid = auth.current_uid(wiki_dir, farm)
    return auth.page_privilege(wiki_dir, uid).check(pagepath_of_subpath(subpath)) == auth.PAGE_WRITE


def _forbidden():
    return HTTPResponse(body="このページを編集する権限がありません。", status=403,
                        content_type="text/plain; charset=utf-8")


def _current_text(wiki_dir, subpath):
    """そのページの今の内容。**公開されている内容**（DB）を読む。無ければ空文字列。

    ここを平文ファイルにしてはいけない。**差分は公開されていた内容を基準に
    記録されている**ので（backup_page の「変更前」＝DBの内容）、さかのぼるときの
    起点も同じでなければ、逆適用の結果が別物になる。平文だけを直接書き換えた
    状態で起点を平文にすると、保存した覚えのない内容が「その時点の記録」として
    出てしまい、しかも差分としては辻褄が合うので壊れたことに気づけない。"""
    return published_body(wiki_dir, subpath, "")

def _is_published(wiki_dir, subpath):
    """そのページが今も公開されているか（＝この画面での「まだ在る」）。

    平文ファイルの有無で決めると、消したがまだ取り込んでいないページを
    「もう無い」と見なす一方、そのページのURLはまだ開ける、という食い違いが出る。

    ページ選択ダイアログが持つ `has_file`（平文ファイルがあるか）とは別のもの。
    あちらは編集の道具なので平文を見る。**同じ「在る」でも見ている先が違う**ので、
    どちらの木も `exists` とは呼ばずに、見ている先が分かる名前にしてある。"""
    return load_page_body(wiki_dir, subpath) is not None


def history_data(wiki_dir, subpath, what, key=""):
    """履歴の一覧（`history`）・その時点の本文（`version`）をJSONで返す。
    **権限は呼ぶ側（render_history）が確かめてある。**"""
    if what not in ("history", "version"):
        return sysui.json_out({"error": "不明な要求です。"}, status=404)
    if not subpath or subpath not in backed_up_subpaths(wiki_dir):
        return sysui.json_out({"error": "そのページのバックアップはありません。"}, status=404)

    current = _current_text(wiki_dir, subpath)
    history = backup_history(wiki_dir, subpath, current)

    if what == "history":
        # 一覧には本文を載せない（世代が多いページで無駄に重くなるため）
        return sysui.json_out({
            "page": subpath,
            "pagepath": pagepath_of_subpath(subpath),
            "published": _is_published(wiki_dir, subpath),
            "history": [
                {k: v for k, v in item.items() if k != "text"} for item in history
            ],
        })

    item = next((h for h in history if h["key"] == key), None)
    if item is None:
        return sysui.json_out({"error": "その時点の記録は見つかりません。"}, status=404)
    # 「すべて戻す」「部分的に戻す」の2タブぶんを、1回の応答にまとめて返す。
    # タブ切替のたびに取りに行かない・タブごとに別の差分アルゴリズムを
    # 使わない、という組み立てにするため（text と current の2つさえあれば、
    # 差分・マージの両方をdiffmergeで画面側が組み立てられる）。
    # text はその保存を行う「前」の内容（backup_history参照）。
    return sysui.json_out({
        "key": key,
        "stamp": item["stamp"],
        "text": item["text"],
        "current": current,
        # 「一部を戻す」を保存するときの楽観ロック用。この値を送り返して
        # もらい、保存直前の実際の現在と食い違っていれば断る
        # （apply_partial_merge参照）
        "current_rev": content_rev(current),
        "same_as_current": item["text"] == current,
        "empty": not item["text"].strip(),
    })


def restore_backup(wiki_dir, config, subpath, key, base_rev):
    """選んだ時点の保存前の内容にページを書き戻す。(成否, 知らせる文言) を返す。

    履歴の各項目が持つのは「その保存を行う前」の内容（backup_history参照）
    なので、書き戻すとその保存で入った変更がまるごと取り消される。

    base_rev は、画面が時点を選んだときの「現在」のハッシュ。**押すまでの間に
    他の変更が入っていたら断る**（Wiki設計者の指示、2026-09-01。「部分的に戻す」に
    先に入れていた仕組みを、こちらにも同じ形で入れた）。

    ここは保存の直前に現在を読み直して組み立て直すので、放っておいても内容が
    壊れることは無い。それでも断るのは、**画面に出ていた差分と、実際に起きる
    ことが食い違う**ため。利用者は「この30行を取り消す」と思って押しているのに、
    その間に入った他人の変更まで巻き戻してしまう。"""
    if not subpath or subpath not in backed_up_subpaths(wiki_dir):
        return False, "復元するページを選んでください。"

    current = _current_text(wiki_dir, subpath)
    if content_rev(current) != base_rev:
        return False, ("復元の間に他の変更が入ったため、戻せませんでした。"
                       "画面を読み込み直してください。")
    item = find_backup_version(wiki_dir, subpath, key, current)
    if item is None:
        return False, "その時点の記録は見つかりません。"
    if item["text"] == current:
        return False, "その保存前の内容は、いまのページと同じです。"
    if not item["text"].strip():
        # 空に戻す＝削除だが、削除には添付の確認などの手順がある。
        # ここで肩代わりせず、編集画面から行ってもらう。
        return False, ("その保存の前には、ページがまだありません。"
                       "削除したい場合は編集画面で本文を空にして保存してください。")

    # 書き戻す先は、そのページが実際に使っている拡張子（＝記法）に合わせる。
    # .txt のページを .md として書き出すと、同じ名前のページが2つできてしまう
    ext = page_ext_of_subpath(wiki_dir, subpath)
    path = page_file_path(wiki_dir, subpath, ext)
    if path is None:
        return False, "書き戻す先を決められませんでした。"

    # 書き戻しも1つの保存として記録する（pagesave）。統合すると直前の差分と
    # 相殺されて「戻った」という事実が残らないことがあるため、まとめずに1本残す。
    # 「変更前」は保存時と同じくDBの内容（＝current）を基準にする
    if not save_page(wiki_dir, config, subpath, ext, item["text"],
                     path=path, known=current, merge=False):
        return False, "書き戻せませんでした。"
    return True, "{} の保存前の状態に戻しました。".format(_stamp_label(item))

def _stamp_label(item):
    """履歴の1項目を指す文言。"""
    return _pretty_stamp(item["stamp"])

def _pretty_stamp(stamp):
    """yymmdd_hhmmss を読みやすくする。"""
    if len(stamp) != 13:
        return stamp
    return "20{}-{}-{} {}:{}:{}".format(
        stamp[0:2], stamp[2:4], stamp[4:6], stamp[7:9], stamp[9:11], stamp[11:13])


def serve_history_asset(name):
    """履歴タブが自前で持つCSS/JS（/.history.css, /.history.js）。
    渡ってくるのは拡張子だけ（編集画面の資材と同じ扱い）。"""
    return serve_asset(BACKUPUI_DIR, "backup", name)


def history_url(base_url, pagepath):
    """履歴タブの受け口（ページ自身のURLに `?cmd=history`）。"""
    return "{}/{}?cmd=history".format(
        base_url, "/".join(urlquote(p) for p in pagepath.split("/")) if pagepath else "")


def render_history(wiki_dir, config, farm, explicit_farm, pagepath):
    """`POST <ページ>?cmd=history`（モジュール冒頭）。"""
    ref = resolve_page_ref(wiki_dir, pagepath)
    subpath = ref.subpath if ref is not None else ""
    wants_json = bool(request.forms.getunicode("data"))
    if not may_edit(wiki_dir, farm, subpath):
        if wants_json:
            return sysui.json_out({"error": "このページを編集する権限がありません。"}, status=403)
        return _forbidden()
    if wants_json:
        return history_data(wiki_dir, subpath, request.forms.getunicode("data", ""),
                            request.forms.getunicode("key", ""))

    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm)
    base_url = context.base_url
    action = history_url(base_url, pagepath)
    message, ok, restored = "", True, False
    do = request.forms.getunicode("do", "")
    if do == "restore":
        ok, message = restore_backup(wiki_dir, config, subpath,
                                     request.forms.getunicode("key", ""),
                                     request.forms.getunicode("base_rev", ""))
        restored = ok
    elif do == "merge-restore":
        ok, message = apply_partial_merge(wiki_dir, config, subpath,
                                          request.forms.getunicode("merged", ""),
                                          request.forms.getunicode("base_rev", ""))
        restored = ok
    elif do:
        return sysui.json_out({"error": "不明な操作です。"}, status=400)

    content = build_history_html(action, subpath, message=message, ok=ok, restored=restored)
    theme_conf = config.get("theme") or {}
    page = build_history_page_html(
        site_title=theme_conf.get("site_title", "wikiSystem"),
        body=content,
        asset_url=base_url + "/" + HISTORY_URLPATH,
        vendor_url=base_url + "/" + VENDOR_URLPATH,
    )
    return HTTPResponse(body=page, status=200, content_type="text/html; charset=utf-8")


def build_history_page_html(site_title, body, asset_url, vendor_url):
    """履歴タブのページ全体。**テーマは使わない**（モジュール冒頭）。

    diffmergeのcss/jsは「現在との差分」「一部を戻す」の両タブが使うため、
    この画面自身のcss/js（asset_url）と並べて読み込む。"""
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>編集履歴 - {escape(site_title)}</title>
<link rel="stylesheet" href="{escape(vendor_url)}/diffmerge/diffmerge.css">
<link rel="stylesheet" href="{escape(asset_url)}.css">
</head>
<body class="bk-body bk-embed">
<main class="bk-page">
{body}</main>
<script src="{escape(vendor_url)}/diffmerge/diffmerge.umd.js"></script>
<script src="{escape(asset_url)}.js"></script>
</body>
</html>
"""


def build_history_html(action, subpath, message="", ok=True, restored=False):
    """中身（`.bk-shell`とその内側）。右の「すべて戻す」「部分的に戻す」の2タブで、
    どちらもdiffmergeの描画先（`.bk-restore-view`/`.bk-merge-view`）を持つだけ。
    本文はJSが data=version の応答から流し込む。

    `restored` は復元・部分復元が済んだ直後の表示であることの印で、JSはこれを見て
    親の編集画面へ知らせる（モジュール冒頭）。"""
    notice = ""
    if message:
        cls = "bk-notice" if ok else "bk-notice bk-notice-error"
        notice = f'<div class="{cls}" role="status">{escape(message)}</div>'
    done = (f' data-restored="1" data-message="{escape(message, quote=True)}"'
            if restored else "")
    return f"""{notice}
<div class="bk-shell" data-action="{escape(action)}" data-page="{escape(subpath, quote=True)}"{done}>
  <section class="bk-detail" aria-label="内容">
    <div class="bk-tabs" role="tablist">
      <button type="button" class="bk-tab" role="tab" data-tab="restore"
              aria-selected="true">すべて戻す</button>
      <button type="button" class="bk-tab" role="tab" data-tab="merge"
              aria-selected="false">部分的に戻す</button>
    </div>
    <div class="bk-panel" data-tab="restore">
      <div class="bk-restore-view"></div>
      <form class="bk-restore" method="post" action="{escape(action)}">
        <input type="hidden" name="do" value="restore">
        <input type="hidden" name="key" value="">
        <input type="hidden" name="base_rev" value="">
        <span class="bk-restore-note">履歴から時点を選ぶと、その内容が出ます。</span>
        <button type="submit" class="bk-restore-btn" disabled>この状態に復元</button>
      </form>
    </div>
    <div class="bk-panel bk-merge-panel" data-tab="merge" hidden>
      <div class="bk-merge-view"></div>
      <form class="bk-merge-form" method="post" action="{escape(action)}">
        <input type="hidden" name="do" value="merge-restore">
        <input type="hidden" name="merged" value="">
        <input type="hidden" name="base_rev" value="">
        <span class="bk-merge-note">履歴から時点を選ぶと、取り込みができます。</span>
        <button type="submit" class="bk-merge-save" disabled>選んだ内容を保存</button>
      </form>
    </div>
  </section>
</div>
"""
