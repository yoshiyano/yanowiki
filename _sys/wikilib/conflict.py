"""編集が競合したときに、マージして統合する画面（/.conflict/<ページパス>）。

## 何を突き合わせるか

編集を始めてから保存するまでの間に、別の場所（別タブ・他の人・セクション編集）
から同じページが保存されると競合になる。突き合わせるのは2つ。

    B  自分の編集した内容（＝保存しようとしたもの）
    C  その間に別の場所で保存された、いまのページの内容

以前はここで「別の場所で更新されています」と断るだけで、押し直せばCを
まるごと上書きしていた。**BにCを取り込んで統合できる**ようにしたのが
この画面（Wiki設計者の指示、2026-09-01）。

左にC、右にBを置き、**右（B）が編集コラム＝保存される内容**になる。
自分の書いたものを土台に、相手の変更を相違点ごとに取り込む形である。

はじめは「編集を始めた時点の内容（A）」を中央に置く3文書マージで作ったが、
**BとCを突き合わせれば足りる**ため取り止めた（Wiki設計者の指示、2026-09-01:
「コンフリクトで3文書マージは不要と判断した」）。起点Aを探す仕組み
（バックアップの履歴からの復元・編集画面を開いた時点の控え）も一緒に外して
ある。取り止めるまでの経緯は
[更新履歴](/Tech/ChangeLog/2026-09-01) に残っている。

## どこから来るか

    編集画面から   保存を押したときに競合を見つけた（editor.render_edit）
    セクション編集から   編集していた節が、その間に書き換わっていた
                        （editor.save_section）

どちらも**自分の編集を書きかけとして預け直し**、この画面へ送ってくる。
画面はそれを「自分の編集」として読む。

## 保存と、統合中にまた更新された場合

保存の直前に、開いたときのCのハッシュ（base_rev）と、いまのページの
ハッシュを突き合わせる。食い違えば**統合した結果を書きかけとして預け直し、
この画面をもう一度開く**（Wiki設計者の指示: 「生成したページを保存した際に同様の
コンフリクトがあれば、改めてコンフリクト対応をする」）。2周目も1周目と
同じ形（B＝さっき統合した結果、C＝あらたに保存された内容）なので、
何度でも繰り返せる。

## 表示とマージ処理

diffmergeの2文書マージ（`render(..., {merge: true})`）に任せる。
**組み込まず、公開APIをそのまま呼ぶ**（バックアップ画面と同じ方針）。
呼んでいるのは `render()` と、その戻り値の `getMergedText()` だけ。
"""
import json
import os
from html import escape
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib.draft import delete_draft, load_draft, load_draft_origin, save_draft
from wikilib.editor import normalize_newlines, source_hash
from wikilib.pagedb import published_body
from wikilib.pagesave import save_page
from wikilib.paths import (
    CONFLICT_DIR, CONFLICT_URLPATH, VENDOR_URLPATH,
    markup_ext_or, page_file_path, resolve_page_ref,
)
from wikilib.themes import make_plugin_context
from wikilib.views import render_no_edit, render_no_page
from wikilib.web import serve_asset


def save_merged(wiki_dir, config, ref, merged_text, markup):
    """統合した結果をページとして保存する。(成否, 知らせる文言) を返す。

    競合の判定（base_rev）は呼び出し側で済ませてある。ここは書き込むだけ。

    「変更前」の基準（known）は、保存時・復元時と同じくDBの内容にそろえる
    （平文ファイルにすると、システムを通さない書き換えがあったときに
    その内容を変更前と見なしてしまう。backupui.restore_backup と同じ理由）。
    """
    if not merged_text.strip():
        # 空にする＝削除だが、削除には添付ファイルの確認などの手順がある。
        # ここで肩代わりせず、編集画面から行ってもらう（部分復元と同じ扱い）
        return False, ("統合した結果、ページが空になります。"
                       "削除したい場合は編集画面で本文を空にして保存してください。")

    ext = markup_ext_or(markup, ref.ext)
    path = page_file_path(wiki_dir, ref.subpath, ext)
    if path is None:
        return False, "保存先を決められませんでした。"

    known = published_body(wiki_dir, ref.subpath, ref.body)
    if merged_text == known:
        # 統合した結果が、いまのページとまったく同じになった（相手の更新を
        # そのまま受け入れて、自分の変更を捨てた場合など）。書き込むものは
        # 無いが、**競合そのものは解けている**。預かっている書きかけを消して
        # 成功として返す。
        #
        # ここを失敗として返すと、書きかけが残ったまま競合の画面へ戻され、
        # 何度「この内容で保存」を押しても同じ画面から出られなくなる
        # （下の描画で `not message` の脱出路も塞がれるため）。
        # 実際に出られなくなった（Wiki設計者の報告、2026-09-03）。
        delete_draft(wiki_dir, ref.subpath)
        return True, ""
    if not save_page(wiki_dir, config, ref.subpath, ext, merged_text,
                     path=path, known=known):
        return False, "保存できませんでした。"
    if ref.exists and ext != ref.ext:
        # 記法を移した。前の拡張子のファイルは必ず消す（編集画面と同じ理由。
        # 残すと同じ名前のページが2つできる）
        old_path = page_file_path(wiki_dir, ref.subpath, ref.ext)
        if old_path and os.path.isfile(old_path):
            os.remove(old_path)
    delete_draft(wiki_dir, ref.subpath)
    return True, ""


def render_conflict(wiki_dir, config, farm, pagepath, explicit_farm):
    """`/.conflict/<ページパス>`。GETで統合の画面、POSTで保存を受ける。

    この画面へ来るのは、編集画面が保存時に競合を見つけて送り込んだとき
    （editor.render_edit）。自分の編集（B）は書きかけとして預かってあり、
    その origin が起点（A）を指すハッシュになっている。

    **編集の権限（`W`）が無ければ403で断る**（Wiki設計者の指示、2026-09-17）。
    統合した結果をそのページへ保存する画面なので、編集と同じ扱いにする。画面には
    いまの本文と自分の書きかけが並ぶので、**描く前に断る**。
    """
    from wikilib import auth  # 循環を避けるため呼び出し時に読み込む

    context = make_plugin_context(config, farm, wiki_dir, CONFLICT_URLPATH, explicit_farm)
    base_url = context.base_url
    ref = resolve_page_ref(wiki_dir, pagepath)
    if ref is None:
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)

    uid = auth.current_uid(wiki_dir, farm)
    if auth.page_privilege(wiki_dir, uid).check(pagepath) != auth.PAGE_WRITE:
        return render_no_edit(wiki_dir, config, farm, pagepath, explicit_farm,
                              logged_in=uid is not None)

    page_url = base_url + "/" + urlquote(pagepath)
    action = base_url + "/" + CONFLICT_URLPATH + "/" + urlquote(pagepath)
    message = ""

    if request.method == "POST" and request.forms.getunicode("cmd") == "save":
        merged = normalize_newlines(request.forms.getunicode("merged", "") or "")
        base_rev = request.forms.getunicode("base_rev", "")
        markup = request.forms.getunicode("markup", "")
        # 送られた統合結果は、まず預かる。ここで落とすと、画面で組み立てた
        # ぶんがそのまま消える。
        #
        # **origin（起点を指すハッシュ）は書き換えない。** 統合結果もその
        # 起点から派生したものなので、また競合したときの突き合わせにも
        # そのまま使える（詳しくはこのモジュールの冒頭）。
        #
        # origin は画面から送り返してもらう。預かりの側（draft）に置いた
        # ものは、**別の場所での保存が成功した時点で消える**（書きかけは
        # ページ単位で1つなので、誰の保存でも解かれる）。統合している最中は
        # まさにそれが起きうるので、預かりだけに頼れない。
        origin = (request.forms.getunicode("origin", "")
                  or load_draft_origin(wiki_dir, ref.subpath) or base_rev)
        save_draft(wiki_dir, ref.subpath, merged, origin)
        if source_hash(ref.body) != base_rev:
            # 統合している間に、また別の場所で保存された。改めて競合として扱う
            # （下の描画へ落ちる。A＝さっきのC、B＝統合結果、C＝いまの内容）
            message = ("統合している間に、このページはまた別の場所で更新されました。"
                       "あらためて突き合わせています。")
        else:
            ok, notice = save_merged(wiki_dir, config, ref, merged, markup)
            if ok:
                # 再読み込みでの二重実行を防ぐため303で戻す
                return HTTPResponse(status=303, headers={"Location": page_url})
            message = notice
            # 預かった書きかけはそのまま残す（もう一度直して保存できる）

    mine = load_draft(wiki_dir, ref.subpath)
    if mine is None:
        # 統合するものが無い（書きかけが消えた・直にURLを開いた）。
        # 突き合わせる相手がいないので、ページ本体へ返す
        return HTTPResponse(status=303, headers={"Location": page_url})

    theirs = ref.body
    origin = load_draft_origin(wiki_dir, ref.subpath) or ""
    if not message and source_hash(theirs) == origin:
        # もう競合していない（相手の更新が取り消された等）。ページ本体へ返す
        return HTTPResponse(status=303, headers={"Location": page_url})

    body = build_conflict_html(
        action=action,
        page_label=pagepath,
        page_url=page_url,
        mine=mine, theirs=theirs,
        base_rev=source_hash(theirs), origin=origin,
        # 記法の選び直しは編集画面から引き継ぐ（POSTなら送り返されたもの、
        # 最初に開いたときはURLの ?markup=…）。この画面には選ぶところが無い
        markup=(request.forms.getunicode("markup", "") if request.method == "POST"
                else request.query.getunicode("markup", "")),
        message=message,
    )
    theme_conf = config.get("theme") or {}
    page = build_conflict_page_html(
        site_title=theme_conf.get("site_title", "wikiSystem"),
        home_url=base_url + "/",
        page_label=pagepath,
        body=body,
        asset_url=base_url + "/" + CONFLICT_URLPATH,
        vendor_url=base_url + "/" + VENDOR_URLPATH,
    )
    return HTTPResponse(body=page, status=200, content_type="text/html; charset=utf-8")


def build_conflict_html(action, page_label, page_url, mine, theirs,
                        base_rev, origin, markup, message=""):
    """画面の中身。2つの文書はJSONにして埋め込み、描画はJSに任せる。

    本文をHTMLの属性やtextareaに直に入れず `application/json` で渡すのは、
    どちらも「生のテキスト」であって表示物ではないため（バックアップ画面が
    data=version の応答をそのまま渡しているのと同じ扱い）。
    """
    docs = json.dumps(
        {"mine": mine, "theirs": theirs},
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    notice = (f'<div class="cf-notice" role="alert">{escape(message)}</div>'
              if message else "")
    lead = (
        "<strong>自分の編集</strong>（右）へ、"
        "<strong>別の場所での更新</strong>（左）から相違点を取り込んでください。"
        "<strong>右がそのまま保存されます。</strong>"
    )
    return f"""{notice}
<div class="cf" data-page="{escape(page_label)}">
  <p class="cf-lead">{lead}</p>
  <div class="cf-view" role="region" aria-label="統合するマージ表示">読み込み中…</div>
  <div class="cf-buttons">
    <!-- **送信するのはこのフォームだけ。** 統合結果はJSが押された瞬間に
         diffmergeから受け取って隠し項目へ詰める（編集画面と同じ作り） -->
    <form class="cf-actions" method="post" action="{escape(action)}">
      <input type="hidden" name="cmd" value="save">
      <input type="hidden" name="merged" value="">
      <input type="hidden" name="base_rev" value="{escape(base_rev)}">
      <!-- この編集が何から分かれたかを指すハッシュ。預かり側は他の人の
           保存で消えることがあるので、画面が持って送り返す
           （render_conflict のPOST側を参照） -->
      <input type="hidden" name="origin" value="{escape(origin)}">
      <input type="hidden" name="markup" value="{escape(markup)}">
      <button type="submit" class="cf-save">この内容で保存</button>
    </form>
    <!-- 編集画面はリンクでは開けない（入口は cmd=edit のPOSTだけ。
         URLに編集の入口を出さないための決まり＝paths.EDIT_URLPATH参照）。
         テーマの「編集」ボタンと同じ形にしてある -->
    <form class="cf-back" method="post" action="{escape(page_url)}">
      <button type="submit" name="cmd" value="edit">編集画面へ戻る</button>
    </form>
    <span class="cf-hint">戻っても、書きかけは預かったままです。
      そのまま保存すればここへ戻ってきます</span>
  </div>
</div>
<script type="application/json" class="cf-docs">{docs}</script>
"""


def build_conflict_page_html(site_title, home_url, page_label, body,
                             asset_url, vendor_url):
    """ページ全体を組み立てる。**テーマは使わない。**

    バックアップ管理画面（backupui.build_backup_page_html）と同じ理由。
    突き合わせているのは生のテキストで、テーマの見た目を確かめる場所では
    ないうえ、テーマの表向けの指定がdiffmergeの表と衝突する。
    """
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>編集の競合 - {escape(page_label)}</title>
<link rel="stylesheet" href="{escape(vendor_url)}/diffmerge/diffmerge.css">
<link rel="stylesheet" href="{escape(asset_url)}.css">
</head>
<body class="cf-body">
<header class="cf-head">
  <a class="cf-home" href="{escape(home_url)}">{escape(site_title)}</a>
  <span class="cf-head-title">編集の競合</span>
  <span class="cf-target">{escape(page_label)}</span>
</header>
<main class="cf-page">
{body}</main>
<script src="{escape(vendor_url)}/diffmerge/diffmerge.umd.js"></script>
<script src="{escape(asset_url)}.js"></script>
</body>
</html>
"""


def serve_conflict_asset(name):
    """この画面が自前で持つCSS/JS（/.conflict.css, /.conflict.js）。
    テーマに置かないので、どのテーマを選んでいても同じ操作感で使える。"""
    return serve_asset(CONFLICT_DIR, "conflict", name)
