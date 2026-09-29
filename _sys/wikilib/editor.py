"""編集画面。本文の入力・プレビュー・保存・削除と、添付ファイルタブ。

見た目と動きに必要なCSS/JSは、テーマではなく編集機能自身が持つ
（/.editor.css, /.editor.js）。どのテーマでも同じ操作感で使えるようにするため。
"""
import hashlib
import json
import os
import re
import time
from html import escape
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib.paths import (
    BASE_COLOR_NAMES, CONFLICT_URLPATH, DEFAULT_CUSTOM_COLORS,
    DEFAULT_THEMEFILE,
    EDITOR_DIR, EDITOR_URLPATH,
    FILES_URLPATH, TREEVIEW_URLPATH,
    MARKUP_FORMATS, PAGETREE_URLPATH, THEME_URLPATH, farm_plugin_dir,
    is_valid_pagepath, markup_ext_or, markup_format_for, markup_name_for,
    page_file_path, resolve_page_ref, selectable_markups,
)
from wikilib.attach import (
    ATTACH_MAX_BYTES, adopt_attachment, attach_max_bytes,
    delete_attachment, has_attach_files,
    format_attach_size, format_bytes, list_attachments, move_attachment, next_clip_name,
    rename_attachment, save_attachment,
)
from wikilib.backup import make_diff
from wikilib.backupui import history_url as history_action_url
from wikilib.chunked import (
    CHUNK_BYTES, chunk_name, finish_chunk, is_chunked, take_chunk,
)
from wikilib.draft import (
    delete_draft, load_draft, load_draft_origin, save_draft,
)
from wikilib.editdiff import build_diff_html, source_anchors
from wikilib import stafflog
from wikilib.pagedb import load_page_body
from wikilib.pagesave import remove_page, save_page
from wikilib.pagemove import convert_folder_to_page
from wikilib.pagetree import TOP_PAGE_LABEL, build_page_tree, with_top_page_row
from wikilib.subst import save_time_replace
from wikilib.plugins import (
    build_markdown_renderer, plugin_script_urls, plugin_style_urls,
)
from wikilib.render import (
    extract_section_text, heading_positions, is_pukiwiki, parse_source,
    render_source, split_section_text,
    rewrite_content_links, split_title, uses_title_heading,
)
from wikilib.themes import make_plugin_context, show_index
from wikilib.views import render_no_edit, render_no_page
from wikilib.wikiconfig import default_markup, listname_for
from wikilib.web import plain, serve_asset

ATTACH_ICON_SPRITE = """<svg class="attach-icon-defs" aria-hidden="true" focusable="false">
<symbol id="ai-file" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></symbol>
<symbol id="ai-image" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="m21 16-5-5-5 5-2-2-6 5"/></symbol>
<symbol id="ai-video" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3z"/></symbol>
<symbol id="ai-audio" viewBox="0 0 24 24"><path d="M9 18V5l10-2v13"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/></symbol>
<symbol id="ai-pdf" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 16h4"/></symbol>
<symbol id="ai-doc" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 12h6M9 15h6M9 18h3"/></symbol>
<symbol id="ai-sheet" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 10h16M4 15h16M10 4v16"/></symbol>
<symbol id="ai-slide" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8 20h8"/></symbol>
<symbol id="ai-archive" viewBox="0 0 24 24"><path d="M3 7h18v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M2 4h20v3H2z"/><path d="M11 11h2"/></symbol>
<symbol id="ai-code" viewBox="0 0 24 24"><path d="m9 8-5 4 5 4M15 8l5 4-5 4"/></symbol>
<symbol id="ai-text" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 16h6"/></symbol>
</svg>"""


def attach_ref_text(name, is_image, ext=None):
    """そのファイルを本文から参照する書きかたを返す。

    添付ファイルは「そのページの添付」として、裸のファイル名だけで参照できる
    （[本文中のリンク](/Tech/Reference/Routing) 参照）。画像は貼り込みたいことが多いので
    埋め込みの書きかたにしておく。

    **記法（`ext`）によって書きかたが違う。** Markdownは`![name](name)`の
    画像記法、PukiWikiには画像専用の記法が無いため`&img(name);`
    （インラインプラグイン、[img](/Syntax/Plugin/img)）を使う。画像以外は
    Markdownがリンク記法`[name](name)`、PukiWikiが角括弧リンク記法
    `[[name>name]]`。`ext`を渡さない・記法が判定できない場合は、従来どおり
    Markdownの書きかたを返す。

    一覧にはこの文字列をそのまま出す。「本文での書きかた」と書いてある欄に
    ファイル名だけが並んでいても、何を書けばよいのかは分からないため。"""
    if is_pukiwiki(ext):
        return f"&img({name});" if is_image else f"[[{name}>{name}]]"
    return ("![{}]({})" if is_image else "[{}]({})").format(name, name)


def build_attach_panel_html(items, subpath, action, tree_url, attach_message="",
                            attach_ok=True, max_bytes=ATTACH_MAX_BYTES,
                            index_shown=False, ext=None):
    """編集画面の「添付ファイル」タブの中身を組み立てる。

    `ext` は「本文での書きかた」欄の記法を決める（画面で選んでいる記法。
    保存済みファイルの拡張子とは限らない。呼び出し側を参照）。

    このページに添付されたファイルの一覧・追加・削除をここで完結させる。
    本文を書きながら画像を足す、といった行き来が多いため、
    別ページに分けずタブで切り替えられるようにしている。"""
    if items:
        rows = "".join(
            # 画像の行には data-thumb を付けておく。マウスを乗せたときに
            # JavaScriptがこれを見てサムネイルを出す（読み込みはそのときが初回）。
            '<tr class="attach-row"{thumb}>'
            '<td class="attach-icon attach-col-kind">'
            '<svg class="attach-icon-svg" aria-hidden="true" focusable="false">'
            '<use href="#ai-{kind}"></use></svg>'
            '<span class="attach-kind-label">{kind_label}</span></td>'
            '<td class="attach-name"><a href="{url}" target="_blank" '
            'rel="noopener">{name}</a></td>'
            '<td class="attach-size attach-col-size">{size}</td>'
            '<td class="attach-date attach-col-date">{mtime}</td>'
            '<td class="attach-ref attach-col-ref">'
            '<code class="attach-ref-code">{ref}</code></td>'
            '<td class="attach-ops">'
            '<button type="button" class="attach-rename" data-name="{name}">名前の変更</button>'
            '<button type="button" class="attach-move" data-name="{name}">添付ページの変更</button>'
            '<button type="submit" name="delete" value="{name}" '
            'class="attach-delete" data-name="{name}">削除</button>'
            '</td></tr>'.format(
                thumb=f' data-thumb="{escape(it["url"])}"' if it["is_image"] else "",
                ref=escape(attach_ref_text(it["name"], it["is_image"], ext), quote=True),
                kind=escape(it["kind"]),
                kind_label=escape(it["kind_label"]),
                url=escape(it["url"]),
                name=escape(it["name"]),
                size=escape(format_attach_size(it["size"], it["dimensions"], it["is_image"])),
                mtime=escape(it["mtime"]),
            )
            for it in items
        )
        listing = (
            ATTACH_ICON_SPRITE +
            '<table class="attach-table">'
            # 狭い画面では、右の欄から順に消していく（Wiki設計者の指示、2026-09-06）。
            # 消す順は「本文での書きかた」→「種別」→「大きさ」→「日時」。
            # 見出しと中身が別の行にあるので、同じ attach-col-* を両方に付けて
            # 1つの指定で消せるようにしてある（editor.css）
            '<thead><tr>'
            '<th class="attach-icon-head attach-col-kind">種別</th>'
            '<th>ファイル名</th>'
            '<th class="attach-col-size">大きさ</th>'
            '<th class="attach-col-date">日時</th>'
            '<th class="attach-col-ref">本文での書きかた</th>'
            '<th>操作</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )
    else:
        listing = '<p class="attach-empty">このページにはまだ添付ファイルがありません。</p>'

    notice = ""
    if attach_message:
        cls = "attach-notice" if attach_ok else "attach-notice attach-notice-error"
        notice = f'<div class="{cls}" role="status">{escape(attach_message)}</div>'

    # 添付ページの変更先を選ぶダイアログ。ページ一覧は開いたときに /.pagetree
    # から読む（編集画面を出すたびに全ページを走査せずに済むよう、
    # 必要になってから取りに行く）。
    index_flag = "1" if index_shown else ""
    picker = f"""
<dialog class="page-picker" data-tree-url="{escape(tree_url)}">
  <form method="dialog" class="page-picker-form">
    <div class="page-picker-head">
      <strong class="page-picker-title">添付ページの変更先を選ぶ</strong>
      <button type="submit" value="cancel" class="page-picker-x"
              aria-label="閉じる">×</button>
    </div>
    <p class="page-picker-target"></p>
    <label class="page-picker-filter">
      <input type="search" placeholder="ページ名で絞り込む" aria-label="ページ名で絞り込む">
    </label>
    <div class="page-picker-tree" role="tree" tabindex="0"
         aria-label="ページ一覧" data-show-index="{index_flag}"></div>
    <div class="page-picker-foot">
      <span class="page-picker-chosen">選択なし</span>
      <button type="submit" value="cancel" class="page-picker-cancel">やめる</button>
      <button type="submit" value="ok" class="page-picker-ok" disabled>ここへ移動</button>
    </div>
  </form>
</dialog>"""

    # 名前を変えるダイアログ。添付ページの変更（別のページへ移す）とは違い、
    # 同じ場所のまま名前だけを変えるので、ページ一覧は要らずテキスト入力1つで済む。
    rename_dialog = """
<dialog class="attach-rename-dialog">
  <form method="dialog" class="attach-rename-form">
    <div class="attach-rename-head">
      <strong class="attach-rename-title">名前を変える</strong>
      <button type="submit" value="cancel" class="attach-rename-x"
              aria-label="閉じる">×</button>
    </div>
    <p class="attach-rename-target"></p>
    <label class="attach-rename-row">
      <span>新しい名前</span>
      <input type="text" class="attach-rename-input" autocomplete="off" required>
    </label>
    <div class="attach-rename-foot">
      <button type="submit" value="cancel" class="attach-rename-cancel"
              formnovalidate>やめる</button>
      <button type="submit" value="ok" class="attach-rename-ok">名前を変える</button>
    </div>
  </form>
</dialog>"""

    return f"""{notice}
<form class="attach-manage" method="post" action="{escape(action)}"
      enctype="multipart/form-data"
      data-max-bytes="{max_bytes}" data-max-label="{escape(format_bytes(max_bytes))}"
      data-chunk-bytes="{CHUNK_BYTES}">
  <input type="hidden" name="cmd" value="attach">
  <input type="hidden" name="move" value="">
  <input type="hidden" name="move_to" value="">
  <input type="hidden" name="rename" value="">
  <input type="hidden" name="rename_to" value="">
  {listing}
  <div class="attach-upload attach-drop">
    <label class="attach-file">
      <input type="file" name="upload" multiple aria-label="添付するファイルを選ぶ">
    </label>
    <label class="attach-overwrite">
      <input type="checkbox" name="overwrite" value="1">同名を置き換える
    </label>
    <button type="submit" class="attach-add">追加</button>
    <button type="button" class="attach-paste" hidden
            title="クリップボードの画像をそのまま貼り付けます（この欄にいるときは Ctrl+V でも同じことができます）">
      クリップ貼付
    </button>
    <span class="attach-drop-hint">ここにファイルをドラッグしても追加できます（複数可）</span>
    <div class="attach-pastebox" contenteditable="true" role="textbox"
         aria-label="ここに画像を貼り付ける"
         data-placeholder="クリップボードからペースト"></div>
    <p class="attach-picked" hidden></p>
    <p class="attach-refused" role="alert" hidden></p>
    <div class="attach-progress" hidden>
      <progress class="attach-progress-bar" max="100" value="0"></progress>
      <span class="attach-progress-text"></span>
    </div>
  </div>
  <p class="attach-hint">
    置き場所は <code>attach/{escape(subpath)}/</code> です。
    本文からは <code>![説明](ファイル名)</code> のようにファイル名だけで参照できます。
    1ファイルの上限は {escape(format_bytes(max_bytes))} です。
  </p>
  <p class="attach-hint">
    この欄をクリックしてから Ctrl+V でクリップボードの画像を貼り付けられます。
    <strong>スマートフォンでは</strong>「クリップボードからペースト」の枠を押し、
    出てきた「ペースト」を選んでください（写真アプリで編集した写真を、
    ファイルに書き出さずそのまま貼り付けられます）。
    https接続もしくはlocalhostへの接続の場合、「クリップ貼付」のボタンが使えます。
  </p>
</form>
{picker}
{rename_dialog}
"""


def title_length_of(config):
    """サイドバーのページ一覧で、タイトルを打ち切る幅（config/default.yaml の
    edit.title_length、全角を2文字ぶんとして数える半角換算。既定24）。"""
    edit_conf = config.get("edit") or {}
    return edit_conf.get("title_length", 24)


def _apply_listnames(node, config):
    """一覧の行に、そのページの記法から決めた `listname`（"fname"/"title"）を足す。

    PukiWiki記法とMarkdownで一覧の基準（ファイル名／タイトル）が違う
    （`wikiconfig.listname_for`。Wiki設計者の指示、2026-09-18。「pukiwiki は
    ファイル名を基準に、markdown はタイトルを基準にするのがファイルの
    記述方法の背景にあるので、双方で統一のルールにはできない」）ため、
    木を組んだあとにここで解決する。`build_page_tree` 自体は設定を知らない
    （`ext` を運ぶだけ）ので、設定を持つこちら側でページ1件ごとに見て回る。

    記法が分からない行（実体の無い書きかけだけのページ・フォルダ自身の
    行）は "fname" のまま（`TreeView` 側もタイトルが無ければファイル名に
    落ちるので、実害は無い）。"""
    if node.get("kind") == "page":
        markup = markup_name_for(node["ext"]) if node.get("ext") else None
        node["listname"] = listname_for(config, markup) if markup else "fname"
    for child in node.get("children", []):
        _apply_listnames(child, config)
    return node


def build_page_list_html(base_url, wiki_dir, current_subpath, config, index_shown=False,
                         title_length=24):
    """編集画面のサイドバーに出すページ一覧を組み立てる。

    編集中はメニューの代わりにこれを出す。**編集は行き来が多い**作業なので、
    「どのページがあるか」「いまどこを編集しているか」「書きかけがどれか」を
    一覧で見せ、そこから直接次のページへ移れるようにしている。

    中身の組み立ては共通のTreeView（`_sys/treeview/`、`WikiTreeView`）に任せる。
    添付ファイルの移動先を選ぶダイアログ・名前を変える画面・バックアップ管理
    画面と同じ実装で、木の作りかた・開閉・キーボードでの操作がここでも揃う。

    **木のデータはこの場でJSONとして埋め込む**（`/.pagetree`への別取得はしない）。
    編集画面はページを開くたびに丸ごと作り直されるので、あとから取りに行っても
    二度手間になるだけ。埋め込んでおけば `editor.js` は届いた時点ですぐ
    組み立てられ、一覧が出るまでの間が空かない（＝選んだ行への
    `scrollIntoView` も読み込み直後に一度で済み、あとから飛んで
    入力の邪魔をすることもない）。

    印は2つ。
      is-chosen（TreeView標準） … いま編集しているページ（選択状態）
      ep-draft                … 一時保存を預かっているページ（赤い太字）

    赤い太字にしているのは、**本保存されていない**ことを見落とすと困るため。
    自分がさっき離れたページも、他のタブで書きかけたページも同じ印になる。

    タイトルは並記せず、行の名前として直接出す（幅の狭いサイドバーで
    ファイル名との並記は圧迫するため）。長いタイトルの打ち切り幅は
    `title_length`（`config/default.yaml` の `edit.title_length`、全角を
    2文字ぶんとして数える半角換算）で決める。実際の打ち切りは `editor.js`
    が行う（表示だけの都合のため）。

    **どちらを出すか（ファイル名／タイトル）はページごとに変わる。**
    PukiWiki記法はファイル名基準、Markdownはタイトル基準という記法ごとの
    流儀があるため（`markdown.listname`/`pukiwiki.listname`。Wiki設計者の
    指示、2026-09-18）、`_apply_listnames` で行ごとに決めてから埋め込む
    （`editor.js` 側は行に付いた `listname` を見るだけで、記法までは
    知らない）。

    **トップページ（`/`）だけは特別扱い。** 他のフォルダは自分の行が中の
    `index` を兼ねるが、木のいちばん外側（ルート）には行そのものが無いため、
    トップページだけが一覧から漏れてしまう。ルートの `index` を
    `TOP_PAGE_LABEL`（`(TopPage)`）という名前の行として先頭に差し込む。"""
    index_flag = "1" if index_shown else ""
    tree = _apply_listnames(with_top_page_row(build_page_tree(wiki_dir)), config)
    tree_json = json.dumps(tree, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<nav class="edit-pages" aria-label="ページ一覧"
     data-edit-url="{escape(base_url)}"
     data-current-subpath="{escape(current_subpath, quote=True)}">
  <h2 class="panel-title">ページ一覧</h2>
  <div class="ep-tree" role="tree" tabindex="0" aria-label="ページ一覧"
       data-show-index="{index_flag}" data-title-length="{int(title_length)}"></div>
  <script type="application/json" class="edit-pages-tree">{tree_json}</script>
  <p class="edit-pages-hint">選ぶとそのページの編集に移ります。
書きかけは自動で預かるので、保存しなくてもかまいません。</p>
</nav>"""


def build_toolbar_html(actions):
    """ツールバーのボタンを組み立てる。

    記法を切り替えたときは、ブラウザ側（editor.js）が同じ形のHTMLで中身を
    差し替える。作りを合わせておくことで、最初の表示と切り替え後の見た目が揃う。"""
    return "".join(
        '<button type="button" class="edit-tool" data-action="{name}" title="{label}" '
        'aria-label="{label}">{icon}</button>'.format(
            name=escape(a["name"]), label=escape(a["label"]), icon=escape(a.get("icon", "")))
        for a in actions
    )


def build_markup_choice_html(current):
    """記法を選ぶラジオボタンを組み立てる。

    ページの記法は拡張子で決まるので、ここでの選択は**保存先のファイル名**を
    決めることでもある。選び直せば、プレビューもツールバーもその記法のものに
    切り替わる（本文は書き換えない。書いたものはそのまま残る）。"""
    items = []
    for name, fmt in selectable_markups():
        checked = " checked" if name == current else ""
        items.append(
            '<label class="edit-markup-choice">'
            f'<input type="radio" name="markup" value="{escape(name)}"'
            f' data-ext="{escape(fmt["ext"])}" data-label="{escape(fmt["label"])}"{checked}>'
            f'<span class="edit-markup-name">{escape(fmt["label"])}</span>'
            f'<code class="edit-markup-ext">{escape(fmt["ext"])}</code>'
            "</label>"
        )
    return (
        '<div class="edit-markup" role="radiogroup" aria-label="記法">'
        '<span class="edit-markup-title">記法</span>' + "".join(items) + "</div>"
    )


def _custom_colors(config):
    """config の edit.custom_colors（wiki固有の色）。壊れていれば既定値。"""
    custom = (config or {}).get("edit", {}).get("custom_colors")
    if not isinstance(custom, list) or not custom:
        return list(DEFAULT_CUSTOM_COLORS)
    return list(custom)


def _formats_with_colors(config):
    """selectable_markups() の全書式に、palette アクションの色一覧を差し込む。

    色はwikiごとの設定（config）由来なので、静的な MARKUP_FORMATS
    （wikilib.paths）には持たせず、ここで実行時に合成する。「標準の色」
    「wikiの色」を別々に渡し、ブラウザ側では2段に分けて表示する（件数を
    ブラウザ側にハードコードせずに済む）。"""
    base_colors = list(BASE_COLOR_NAMES)
    custom_colors = _custom_colors(config)
    result = {}
    for name, fmt in selectable_markups():
        actions = [
            dict(a, base_colors=base_colors, custom_colors=custom_colors)
            if "palette" in a else a
            for a in fmt["actions"]
        ]
        result[name] = dict(fmt, actions=actions)
    return result


def files_url_of(base_url, pagepath):
    """ファイル一覧（/.files/）を、そのページが入っているフォルダを開いた形で指すURL。

    場所は webFileDir の画面のハッシュ（`#/<マウント>/<パス>`、要素ごとに符号化）で渡す。"""
    from wikilib.filesui import MOUNT_ID
    parent = (pagepath or "").strip("/").rpartition("/")[0]
    parts = [MOUNT_ID] + ([p for p in parent.split("/")] if parent else [])
    return "{}/{}/#/{}".format(base_url, FILES_URLPATH,
                               "/".join(urlquote(p, safe="") for p in parts))


def build_editor_html(markup, source, origin, is_new, action, preview_url,
                      editor_url, message="", attach_panel="",
                      active_tab="edit", diff_url="", origin_html="",
                      draft_notice="", config=None, saved_notice="",
                      saved_text=None, history_url="", files_url=""):
    """編集フォームのHTMLを組み立てる（ページ全体の中身になる部分）。

    「編集画面」「更新状況」「添付ファイル」をタブで切り替える構成にしてある。
    本文を書きながら画像を足す・差分を確かめる、といった行き来が多いため、
    別ページに分けていない。

    見た目と動きは編集機能自身が持つCSS/JS（`/.editor.css` `/.editor.js`）だけで
    決まる。テーマには載せない（build_edit_page_html を参照）。"""
    fmt = MARKUP_FORMATS.get(markup) or markup_format_for(None)

    # **保存と内容破棄は、本文が保存されている内容から変わっていないあいだ押せない**
    # （Wiki設計者の指示、2026-09-19。「変更なしの状態なら押しても意味がないので、
    # 無効化しておく」）。比べる相手は「更新状況」タブの差分と同じ、システムが
    # 知っている本文（`saved_text`。DBに無ければ平文ファイル）。**差分が空なら
    # 未変更**、という1つの規則に揃えてある。開いた直後の状態はここで決め、
    # 入力に合わせた付け外しは editor.js が受け持つ（比べる本文を下のJSONで渡す）。
    # `saved_text` が None なら比べる相手が無いので、いじらず押せるままにする。
    unchanged = (saved_text is not None
                 and normalize_newlines(source) == normalize_newlines(saved_text))
    off = ' disabled title="変更がありません"' if unchanged else ""
    saved_json = ("" if saved_text is None else
                  '<script type="application/json" class="edit-saved">'
                  + json.dumps(saved_text, ensure_ascii=False).replace("<", "\\u003c")
                  + "</script>")
    tools = build_toolbar_html(fmt["actions"])
    toolbar = (
        '<div class="edit-toolbar" role="toolbar" aria-label="記法のボタン">'
        f'<span class="edit-tools">{tools}</span>{build_markup_choice_html(markup)}</div>'
    )
    note = ""
    if is_new:
        note = (
            '<p class="edit-note">このページはまだありません。保存すると新しく作成されます'
            f'（<code class="edit-note-ext">{escape(fmt["ext"] or "")}</code>）。</p>'
        )
    warn = f'<div class="edit-message" role="alert">{escape(message)}</div>' if message else ""
    draft = (f'<div class="edit-draft-note" role="status">{escape(draft_notice)}</div>'
             if draft_notice else "")
    # 連続編集で保存・破棄したあと、画面に留まったことを知らせる
    saved = (f'<div class="edit-saved-note" role="status">{escape(saved_notice)}</div>'
             if saved_notice else "")
    # 記法を切り替えたときにツールバーを組み直せるよう、全書式の定義を渡しておく
    formats_json = json.dumps(
        _formats_with_colors(config), ensure_ascii=False
    ).replace("<", "\\u003c")

    # タブはJavaScriptが無くても内容が読める形にしておく（CSSで隠すのは有効時のみ）。
    if active_tab not in ("edit", "diff", "attach", "history"):
        active_tab = "edit"
    selected = {name: ("true" if active_tab == name else "false")
                for name in ("edit", "diff", "attach", "history")}

    # 「履歴」タブ。ページのバックアップ管理画面（`wikilib.backupui`）を埋め込む
    # （Wiki設計者の指示、2026-09-19）。**タブを開くまで読み込まない**
    # （`data-src`。editor.js が最初に開かれたときに `src` へ移す）——ふだん編集を
    # 始めるだけのときに、一覧と履歴の取得を走らせないため。`history_url` が
    # 無ければ（呼び出し側が渡さなければ）タブごと出さない。
    if history_url:
        history_tab = f"""
  <button type="button" class="edit-tab" role="tab" data-tab="history"
          id="edit-tab-history" aria-controls="edit-panel-history"
          aria-selected="{selected['history']}">履歴</button>"""
        history_panel = f"""
<section class="edit-panel" role="tabpanel" data-tab="history"
         id="edit-panel-history" aria-labelledby="edit-tab-history">
  <p class="edit-history-empty" hidden>変更履歴はありません</p>
  <iframe class="edit-history-frame" name="edit-history-frame" title="編集履歴" hidden data-src="{escape(history_url)}"></iframe>
</section>"""
    else:
        history_tab = history_panel = ""

    # ファイル一覧（/.files/）。編集中の本文を置いていかないよう、別のタブで開く
    files_link = (
        f'<a class="edit-files" href="{escape(files_url)}"'
        ' target="_blank" rel="noopener">ファイル一覧</a>'
        if files_url else "")

    return f"""<div class="edit-shell" data-active-tab="{escape(active_tab)}">
<div class="edit-tabs" role="tablist" aria-label="編集画面">
  <button type="button" class="edit-tab" role="tab" data-tab="edit"
          id="edit-tab-edit" aria-controls="edit-panel-edit"
          aria-selected="{selected['edit']}">編集画面</button>
  <button type="button" class="edit-tab" role="tab" data-tab="diff"
          id="edit-tab-diff" aria-controls="edit-panel-diff"
          aria-selected="{selected['diff']}">更新状況</button>
  <button type="button" class="edit-tab" role="tab" data-tab="attach"
          id="edit-tab-attach" aria-controls="edit-panel-attach"
          aria-selected="{selected['attach']}">添付ファイル</button>{history_tab}
</div>

{warn}{saved}{draft}{note}
<!-- **編集画面の全体を <form> で囲まない**（Wiki設計者の指示、2026-09-01）。
     囲むと、本文のプラグインが返す <form> が入れ子になって外側を壊す。
     送信するのはボタンだけの小さな <form>（.edit-actions）で、送る中身は
     JavaScriptがここから集めて詰める（editor.js の submit ハンドラ）。
     action と origin は、そのJSが使えるようにここへ持たせておく。 -->
<div class="page-editor" data-action="{escape(action)}" data-origin="{escape(origin)}"
      data-preview-url="{escape(preview_url)}" data-diff-url="{escape(diff_url)}"
      data-chunk-bytes="{CHUNK_BYTES}">

  <section class="edit-panel" role="tabpanel" data-tab="edit"
           id="edit-panel-edit" aria-labelledby="edit-tab-edit">
  <div class="edit-panes">
    <div class="edit-source-col">
      <textarea class="edit-source" name="source" spellcheck="false"
                aria-label="ページの内容">{escape(source)}</textarea>
    </div>
    <div class="edit-preview-col">
      <div class="edit-preview content" aria-live="polite"><p class="edit-preview-empty">プレビュー</p></div>
    </div>
  </div>
  {toolbar}
  </section>

  <section class="edit-panel" role="tabpanel" data-tab="diff"
           id="edit-panel-diff" aria-labelledby="edit-tab-diff">
  <div class="edit-diff-panes">
    <div class="edit-diff-col">
      <pre class="edit-diff" aria-live="polite"><span class="d-at">読み込み中…</span></pre>
      <h3 class="edit-col-title">差分<span class="edit-col-note">保存されている内容 → 編集中</span></h3>
    </div>
    <div class="edit-origin-col">
      <div class="edit-origin content">{origin_html}</div>
      <h3 class="edit-col-title">オリジナル<span class="edit-col-note">いま保存されている内容</span></h3>
    </div>
  </div>
  </section>

  <div class="edit-buttons">
    <!-- **送信するのはこのフォームだけ。** 本文・origin・記法は中に持たず、
         押された瞬間にJavaScriptが集めて下の隠し項目へ詰める。
         囲む範囲をボタンだけにしてあるので、本文に <form> が混じっても
         入れ子にならない（Wiki設計者の指示、2026-09-01） -->
    <!-- **空の hidden をここに置かない**（Wiki設計者の報告、2026-09-10）。
         JavaScriptが送信を横取りできなかった場合、ブラウザはこのフォームを
         そのまま送る。`source` が空のまま入っていると、サーバーには
         「本文を空にして保存した」＝**このページを消す**と読める。
         実際にiPhoneでページが消されかけた。
         値を詰めるのは editor.js の fill() で、**無ければその場で作る**ので、
         ここに置いておく必要はない。置かなければ、横取りできなかったときは
         「本文が届きませんでした」と断られて終わる（消えない）。 -->
    <form class="edit-actions" method="post" action="{escape(action)}">
      <button type="submit" name="cmd" value="save" class="edit-save"{off}>保存</button>
      <button type="submit" name="cmd" value="pause" class="edit-pause">一時中断<span class="edit-key">(ESC)</span></button>
      <button type="submit" name="cmd" value="discard" class="edit-discard"{off}>内容破棄</button>
    </form>
    {files_link}
    <!-- **連続編集**（Wiki設計者の指示、2026-09-19）。入っていれば、保存・内容破棄の
         あとに元のページへ戻らず、この編集画面に留まる。フォームの外に置いてあり、
         値は押された瞬間に editor.js が `continuous` として詰めて送る。
         既定は入れておく（JavaScriptが選び直しを覚えていれば、そちらが優先）。
         一時中断（ESC）と「ページを見る」は、これに関わらず常にページへ戻る。 -->
    <label class="edit-continuous"
           title="保存・内容破棄のあと、ページへ戻らずに編集を続けます。ページへは「ページを見る」か「一時中断」で戻れます">
      <input type="checkbox" class="edit-continuous-check" checked> 連続編集</label>
    <span class="edit-hint">Ctrl+S でも保存できます。
      <strong>本文を空にして保存すると、このページは削除されます</strong></span>
    <!-- 書きかけを預かった時刻を出す。預かれなかったときもここに出る -->
    <span class="edit-draft-state" role="status" aria-live="polite"></span>
  </div>
</div>

<section class="edit-panel" role="tabpanel" data-tab="attach"
         id="edit-panel-attach" aria-labelledby="edit-tab-attach">
{attach_panel}</section>{history_panel}
</div>
<script type="application/json" class="edit-formats">{formats_json}</script>
{saved_json}
"""


def build_edit_page_html(title, site_title, home_url, cancel_url, editor_url, treeview_url,
                         page_label, page_list, body, plugin_styles=(), plugin_scripts=(),
                         theme_css="", is_new=False):
    """編集画面のページ全体を組み立てる。**テーマは使わない。**

    編集画面をテーマの本文領域に埋め込んでいたときは、テーマが決めた本文幅
    （`--content-max` など）に閉じ込められ、**広い画面でも入力欄とプレビューが
    細いまま**だった。本文を書く場所なので、読む場所とは求められる形が違う。

    そこで編集画面は自前のページとして描く。画面の高さいっぱいを使い、
    左にページ一覧、右に編集の枠を置く。テーマを差し替えても・一から書いた
    テーマでも、編集画面はいつも同じ形と操作感になる。

    **テーマのCSSとプラグインのCSS/JSは読み込む。** プレビューとオリジナルは
    「保存したらこう見える」を確かめる場所なので、そこだけは本物と同じ見た目に
    なっていないと確かめる意味が薄い。読み込む順は
    プラグイン → テーマ → 編集画面 で、編集画面の枠組みが最後に勝つ。

    テーマのCSSが広い範囲に効かせているのは body・a・mark くらいなので、
    枠組みが崩れることはない（body の余白だけは全画面のために打ち消す）。"""
    styles = "".join(
        f'<link rel="stylesheet" href="{escape(url)}">\n' for url in plugin_styles)
    scripts = "".join(
        f'<script src="{escape(url)}" defer></script>\n' for url in plugin_scripts)
    theme = f'<link rel="stylesheet" href="{escape(theme_css)}">\n' if theme_css else ""
    kind = "新規作成" if is_new else "編集"
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
{styles}{scripts}{theme}<link rel="stylesheet" href="{escape(treeview_url)}.css">
<link rel="stylesheet" href="{escape(editor_url)}.css">
</head>
<body class="edit-body">
<header class="edit-head">
  <!-- 狭い画面でだけ出る、ページ一覧の開閉ボタン（Wiki設計者の指示、2026-09-06）。
       広い画面ではCSSで隠す。左上に固定するので、位置はDOMの並びで決まらないが、
       キーボードで辿る順（一覧より前）を合わせるためここに置いてある -->
  <button type="button" class="edit-side-toggle" aria-expanded="false"
          aria-controls="edit-side" aria-label="ページ一覧を開く">
    <span class="edit-side-toggle-bars" aria-hidden="true"></span>
  </button>
  <a class="edit-home" href="{escape(home_url)}">{escape(site_title)}</a>
  <span class="edit-kind">{kind}</span>
  <span class="edit-target">{escape(page_label)}</span>
  <a class="edit-back" href="{escape(cancel_url)}">ページを見る</a>
</header>
<div class="edit-layout">
  <aside class="edit-side" id="edit-side">{page_list}</aside>
  <!-- 一覧を開いているあいだ、後ろを覆う幕。押すと閉じる。
       広い画面では display:none なので、グリッドの桁を取らない -->
  <div class="edit-side-scrim"></div>
  <div class="edit-side-resizer" role="separator" aria-orientation="vertical"
       aria-label="ページ一覧の幅"></div>
  <main class="edit-main">{body}</main>
</div>
<script src="{escape(treeview_url)}.js"></script>
<script src="{escape(editor_url)}.js"></script>
</body>
</html>
"""


def serve_editor_asset(name):
    """編集機能自身のCSS/JSを配信する（_sys/editor/editor.css, editor.js）。
    テーマの theme/ とは別に持つことで、どのテーマを選んでいても編集画面が
    同じように動く（テーマがCSSを用意していなくても崩れない）。"""
    return serve_asset(EDITOR_DIR, "editor", name)

def source_hash(text):
    """保存時の競合検出に使う。編集を始めた時点の中身と比べる。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def page_has_attachments(wiki_dir, subpath):
    """そのページに添付ファイルが1つでもあるか（判定は attach.has_attach_files）。"""
    return has_attach_files(wiki_dir, subpath)


def remove_empty_dirs(directory, stop_at):
    """空になったフォルダを上へたどって片付ける。stop_at 自身までで止める。

    ページを消したあとに空のフォルダが残ると、ページ選択ダイアログに
    中身の無い階層が並んでしまうため。"""
    stop = os.path.realpath(stop_at)
    current = os.path.realpath(directory)
    while current != stop and current.startswith(stop + os.sep):
        try:
            if os.listdir(current):
                return  # 他のページが残っている
            os.rmdir(current)
        except OSError:
            return
        current = os.path.dirname(current)


def delete_page(wiki_dir, config, ref):
    """ページのファイルごと削除する。(成否, 知らせる文言) を返す。

    添付ファイルが残っているページは削除しない。ページだけ消すと参照元を失った
    添付が宙に浮き、かといって一緒に消すと取り返しがつかないため、
    先に添付を片付けてもらう。"""
    if not ref.exists:
        return False, "このページはまだありません。"
    if page_has_attachments(wiki_dir, ref.subpath):
        return False, ("このページには添付ファイルがあるため削除できません。"
                       "「添付ファイル」タブで先に削除するか、別のページへ移してください。")

    staff = stafflog.actor(wiki_dir)
    old_text = stafflog.read_text(ref.path) if staff is not None else None
    try:
        os.remove(ref.path)
    except OSError:
        return False, "ページを削除できませんでした。"
    if staff is not None:
        stafflog.record(wiki_dir, staff, "page.delete", ref.subpath, "削除した",
                        before={"ext": ref.ext, "text": old_text}, after=None)

    # 消す前の内容を「全文→空」の差分として残し、DBの行を消す（pagesave）。
    # 逆適用すれば元に戻せる。「消す前」は保存時と同じくDBの内容を基準にする
    known = load_page_body(wiki_dir, ref.subpath)
    remove_page(wiki_dir, ref.subpath, known=ref.body if known is None else known)
    remove_empty_dirs(os.path.dirname(ref.path), wiki_dir)
    # 下位ページを消した結果、入口ページだけになったフォルダはページに戻す
    # （X/index.md → X.md）。展開の逆で、これがあると下位フォルダの作成と削除を
    # 行き来できる。
    folder = os.path.dirname(ref.subpath)
    if folder:
        convert_folder_to_page(wiki_dir, config, folder)
    return True, "削除しました。"

def handle_attach_post(wiki_dir, config, subpath):
    """編集画面の「添付ファイル」タブからの操作を処理する。(成否, 知らせる文言) を返す。

    削除・添付ページの変更・名前の変更は1件ずつ（押したボタンのvalueに
    名前が入る）、追加はまとめて受け付ける。

    大きなファイルは何回かに分けて送られてくる。まだ続きがある回は
    成否のところに None を返す（呼び出し側はそれを見て204で返す）。"""
    overwrite = request.forms.get("overwrite") == "1"  # 追加・添付ページの変更・名前の変更で共通に使う

    moving = request.forms.getunicode("move")
    if moving:
        return move_attachment(wiki_dir, subpath, moving,
                               request.forms.getunicode("move_to"), overwrite)

    renaming = request.forms.getunicode("rename")
    if renaming:
        return rename_attachment(wiki_dir, subpath, renaming,
                                 request.forms.getunicode("rename_to"), overwrite)

    deleting = request.forms.getunicode("delete")
    if deleting:
        return delete_attachment(wiki_dir, subpath, deleting)

    if is_chunked():
        # 大きなファイルは何回かに分けて送られてくる。そろうまでは置いておき、
        # 最後の切れ端を受け取った回だけ、添付として置く。
        # **editor.js のアップロードは、大きさに関わらず常にこの経路を通る**
        # （sendChunkedは1件でも「1回で終わる分割」として送る作り）ため、
        # クリップボードからの貼り付け（pasted=1）の連番採番も、下の
        # uploadsループ側だけでなくここでも行う必要がある。
        limit = attach_max_bytes(config)
        state, path, refused = take_chunk(wiki_dir, max_bytes=limit)
        if state == "error":
            return False, refused
        if state == "more":
            return None, ""   # まだ続く。呼び出し側は204で返す
        chunk_id = request.forms.getunicode("chunk_id", "")
        name = chunk_name(wiki_dir, chunk_id)
        if request.forms.get("pasted") == "1":
            _, ext = os.path.splitext(name)
            name = next_clip_name(wiki_dir, subpath, ext.lower() or ".png")
        ok, notice = adopt_attachment(
            wiki_dir, subpath, path, name,
            overwrite, max_bytes=limit)
        finish_chunk(wiki_dir, chunk_id)
        return ok, notice

    uploads = [u for u in request.files.getall("upload") if getattr(u, "raw_filename", "")]
    if not uploads:
        return False, "追加するファイルを選んでください。"

    # クリップボードからの貼り付け（editor.js）は、名前を持たない画像に
    # 仮の名前（拡張子だけ合わせた "clip.png" 等）を付けて送ってくる。
    # ここで拡張子だけ引き継ぎ、本当の名前（clipNNN）に差し替える。
    # ループの中で1件ずつ振るのは、save_attachment が実際に書き込んだ
    # あとでないと「いま何番まで使われているか」が正しく反映されないため。
    pasted = request.forms.get("pasted") == "1"
    done, failed = [], []
    for upload in uploads:
        if pasted:
            _, ext = os.path.splitext(getattr(upload, "raw_filename", "") or "")
            upload.raw_filename = next_clip_name(wiki_dir, subpath, ext.lower() or ".png")
        ok, notice = save_attachment(wiki_dir, subpath, upload, overwrite,
                                      max_bytes=attach_max_bytes(config))
        (done if ok else failed).append(notice)
    if failed:
        # 一部だけ失敗した場合も、成功したぶんは残したうえで理由を伝える
        head = f"{len(done)}件を添付しました。" if done else ""
        return False, head + " ".join(failed)
    return True, f"{len(done)}件を添付しました。" if len(done) > 1 else done[0]


def normalize_newlines(text):
    """ブラウザはtextareaの改行をCRLFにして送るため、LFに戻す。
    そのままだと保存のたびにファイル全体の改行コードが変わってしまう。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def source_from_form():
    """フォームで送られてきた本文を取り出す。(本文, 断り文句, 返す番号) を返す。

    **「送られてこなかった」と「空だった」を必ず分ける。** 本文が空なら、それは
    「このページを消す」という指示になる決まりなので、届かなかったものを空と
    読むと、保存したつもりでページが消えてしまう。

    上限を超えた本文は、bottle が一時ファイルへ落として request.files のほうへ
    回す。request.forms からは見えなくなるだけで、例外にも 413 にもならない。
    そのまま「空」と読んでいたため、**一時保存が 204 を返しながら中身を捨てる**
    という起こりかたをしていた。ここで拾って断る。"""
    if "source" in request.files:
        return None, (
            "本文が大きすぎて受け取れませんでした（上限 {}MB）。"
            "ページを分けるか、大きな部分を添付ファイルにしてください。"
        ).format(request.MEMFILE_MAX // (1024 * 1024)), 413
    if "source" not in request.forms:
        return None, "本文が届きませんでした。もう一度お試しください。", 400
    return normalize_newlines(request.forms.getunicode("source", "")), "", 200


def posted_source(wiki_dir, subpath, original):
    """保存に使う本文を取り出す。(本文, 断り文句, 返す番号) を返す。

    本文は2つの道で届く。

    from_draft=1
        **預かってある書きかけをそのままファイルにする。** 編集画面は入力が
        止まるたびに書きかけを預けているので、保存のときに本文をもう一度
        送る必要がない。送らないぶん、長いページでも保存の送信は小さいまま
        （フォームの送信は日本語で3倍に膨らむため、ここが効く）。

        預かりが無い場合は、いま保存されている内容をそのまま使う。書きかけは
        **保存されている内容と同じになった時点で解かれる**ので、無いことは
        「変えていない」を意味する。断ってしまうと、開いて何も変えずに保存を
        押しただけで失敗することになる。

    source
        フォームに入っている本文そのもの。JavaScript が動かない場合は
        書きかけを預けられないので、こちらを通る。

    ## `from_draft` の道で「空」は受け取らない（Wiki設計者の報告、2026-09-10）

    **本文が空の保存は「そのページを消す」という指示**になる。ところが
    `from_draft=1` のときは本文が送られてこない——サーバーが読むのは預かって
    ある**ファイル**である。そこが空だったなら、それは利用者が消したいのでは
    なく、**預かるところで何かが失敗した**とみるほうが自然だ。

    実際に「iPhoneで本文を編集して保存したら、削除として扱われた」という報告が
    あった（添付ファイルが残っていたため削除は踏みとどまり、事なきを得た）。

    **消すつもりの空は、本文をそのまま送ってきたときだけ受け取る。** 画面側も、
    本文が空のときは預かりを使わずそのまま送る（`editor.js` の `collect`）。
    あわせて、空の書きかけはそもそも預からないようにした
    （`wikilib.draft.save_draft`）。"""
    if request.forms.getunicode("from_draft") == "1":
        text = load_draft(wiki_dir, subpath)
        if text is not None and not text.strip():
            # 預かってあるものが空。**消す指示として読まない**（上記）
            return None, (
                "本文が空のまま届きました。ページを消すつもりでなければ、"
                "画面を開き直して確かめてください"
                "（消す場合は、本文を空にしてもう一度保存してください）。"
            ), 400
        return normalize_newlines(original if text is None else text), "", 200
    return source_from_form()


def _saved_text(wiki_dir, attach_subpath, original):
    """保存されている本文。**システムが最後に知っている内容（DB）**で、無ければ
    平文ファイル（`original`）。「更新状況」タブの差分の「変更前」と同じ相手
    （`render_diff`）——保存・内容破棄を押せるかどうかは、この本文との差で決まる。"""
    known = load_page_body(wiki_dir, attach_subpath)
    return original if known is None else known


def render_edit(wiki_dir, config, farm, pagepath, explicit_farm, _reopened=None):
    """編集画面。GETで編集フォームを表示し、POSTで保存する。

    `_reopened` は内部用。**連続編集**（フォームの `continuous`）で保存・内容破棄
    したあと、元のページへ戻す代わりにこの関数を呼び直すときの、画面に出す
    知らせ。呼び直しは `cmd=edit`（フォームを開くだけの操作）として扱うので、
    保存し直された内容（本文・拡張子・新規かどうか）が、ふつうに開いたときと
    同じ経路で読み直される。

    **編集の権限（`W`）が無ければ、何もせず403で断る**（Wiki設計者の指示、
    2026-09-17）。テーマは権限に応じて編集の入口を出さないが、それは見た目の
    話でしかなく、`cmd=edit` のPOSTはURLさえ分かれば誰でも送れる。一時保存・
    添付・保存も同じこの関数を通るので、ここ1か所で断れば編集に連なる操作は
    すべて止まる。"""
    from wikilib import auth  # 循環を避けるため呼び出し時に読み込む

    if not is_valid_pagepath(pagepath):
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)

    uid = auth.current_uid(wiki_dir, farm)
    if auth.page_privilege(wiki_dir, uid).check(pagepath) != auth.PAGE_WRITE:
        return render_no_edit(wiki_dir, config, farm, pagepath, explicit_farm,
                              logged_in=uid is not None)

    # まだ無いページの拡張子は、そのWikiの既定の記法（edit.defaultwiki）で決まる。
    # ここで決まった ext が、下の markup（ツールバーの記法の選択）の初期値になる
    ref = resolve_page_ref(wiki_dir, pagepath, default_markup(config))
    if ref is None:
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)
    attach_subpath, ext, original, is_new = ref.subpath, ref.ext, ref.body, not ref.exists

    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm, ext=ext)
    if request.method == "GET":
        # ここへはwiki.pyのdispatchが「POST + cmdあり」のときしか回してこない
        # ので、通常は起こらない経路。念のための安全弁として、直接呼ばれても
        # 編集フォームを出さずそのページの表示へ戻す（URLさえ分かればGETで
        # 誰でもフォームを開けてしまう状況を避けるため）。
        return HTTPResponse(status=303, headers={
            "Location": context.base_url + "/" + pagepath,
        })
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    message = ""
    # 何の操作か。連続編集で開き直したときは、フォームを開くだけの操作にする
    cmd = "edit" if _reopened is not None else request.forms.getunicode("cmd")
    # 連続編集にするか（画面のチェック。入っていれば "1" で届く）。
    # **保存と内容破棄だけに効く。** 一時中断はいつもページへ戻る
    continuous = request.forms.getunicode("continuous") == "1"
    # '.edit' という別パスは持たない。編集に関わる送信先は常にページ自身の
    # 通常URLで、cmd の値だけで操作を区別する（wiki.py の dispatch 参照）。
    edit_url = context.base_url + "/" + pagepath

    if request.method == "POST" and cmd == "draft":
        # 一時保存。編集画面は入力が止まるたびにここへ書きかけを預ける。
        # 書いている最中に呼ばれるため、本文を返さず素早く終える。
        #
        # 一緒に origin（このとき画面に表示されていた本文のハッシュ）も
        # 覚えておく。あとで cmd=edit で開き直したとき、「書きかけを
        # 預けてから他の誰かが更新していないか」をこの origin で判定する
        # ため（save_draft のdocstring・下の「一時保存を預かっていれば」
        # 節を参照）。
        origin_sent = request.forms.getunicode("origin", "")

        def keep(text):
            """書きかけを預かる。"""
            save_draft(wiki_dir, attach_subpath, text, origin_sent)

        if is_chunked():
            # 長い本文は何回かに分けて送られてくる。そろうまでは置いておき、
            # 最後の切れ端を受け取った回だけ、書きかけとして預かる
            state, path, refused = take_chunk(wiki_dir)
            if state == "error":
                return plain(refused, status=400)
            if state == "more":
                return HTTPResponse(status=204)
            chunk_id = request.forms.getunicode("chunk_id", "")
            try:
                with open(path, encoding="utf-8") as f:
                    text = normalize_newlines(f.read())
            except OSError:
                finish_chunk(wiki_dir, chunk_id)
                return plain("受け取ったものを読めませんでした。", status=500)
            finish_chunk(wiki_dir, chunk_id)
            if text == original:
                delete_draft(wiki_dir, attach_subpath)
            else:
                keep(text)
            return HTTPResponse(status=204)

        text, refused, status = source_from_form()
        if refused:
            # 預かれなかったことは必ず伝える。黙って204を返すと、編集画面は
            # 預かってもらえたつもりで書き続け、いざ保存するときに失われる
            return plain(refused, status=status)
        if text == original:
            delete_draft(wiki_dir, attach_subpath)  # 元に戻ったなら預かる必要がない
        else:
            keep(text)
        return HTTPResponse(status=204)

    # 添付タブの状態。cmd=attach で更新される他は、?tab=attach というURL
    # （views.pyの添付ファイル案内）から引き継ぐ。
    attach_notice, attach_ok_flag = "", True
    # 開くタブ。ページを開き直す形（再読み込み・ページ一覧からの移動）は `?tab=`、
    # 連続編集の保存・破棄のあとはフォームの `tab`（選んでいたタブを保つ）
    initial_tab = (request.query.getunicode("tab")
                   or request.forms.getunicode("tab") or "edit")

    if request.method == "POST" and cmd == "attach":
        # 添付ファイルの追加・削除。以前は303でGETの編集画面（添付タブ）へ
        # 戻していたが、.editへのGETを塞いだためその経路は使えない。
        # POSTの応答としてそのまま編集画面（添付タブ）を返す
        # （二重送信防止よりURLを露出させないことを優先する）。
        ok, notice = handle_attach_post(wiki_dir, config, attach_subpath)
        if ok is None:
            return HTTPResponse(status=204)   # 切れ端を受け取った。まだ続く
        attach_notice, attach_ok_flag, initial_tab = notice, ok, "attach"

    if request.method == "POST" and cmd == "discard":
        # 内容破棄。書きかけを消して、そのページ（保存済みの内容）へ戻す。
        # 「一時中断」と違い、続きを書ける状態を残さない。
        delete_draft(wiki_dir, attach_subpath)
        if continuous:
            return render_edit(wiki_dir, config, farm, pagepath, explicit_farm,
                               _reopened="書きかけを破棄しました。保存されている内容を表示しています。")
        return HTTPResponse(status=303, headers={
            "Location": context.base_url + "/" + pagepath,
        })

    if request.method == "POST" and cmd == "pause":
        # 一時中断（ESC）。いま書いている内容を書きかけとして預け、
        # そのページへ戻る。「内容破棄」と違い、続きをあとで書けるように残す。
        text, refused, _status = source_from_form()
        if not refused:
            if text == original:
                delete_draft(wiki_dir, attach_subpath)
            else:
                save_draft(wiki_dir, attach_subpath, text,
                          request.forms.getunicode("origin", ""))
        return HTTPResponse(status=303, headers={
            "Location": context.base_url + "/" + pagepath,
        })

    # 保存できずに戻すとき、入力された本文を画面に残すための控え
    # （本文が送られてこなかった・添付が残っていて消せなかった、など）。
    # original（＝いま保存されている内容）とは別に持つ。混ぜてしまうと、
    # 競合の基準になるハッシュまで入力内容のものになり、押しても押しても
    # 断られ続ける状態から抜け出せなくなる。
    typed = None

    # cmd=attach は上ですでに処理済み。cmd=edit は「フォームを開くためだけの
    # POST」（テーマの「編集」ボタン・views.pyの添付ファイル案内から）で、
    # 本文を送ってこないので保存を試みてはいけない。
    if request.method == "POST" and cmd == "save":
        source, refused, _status = posted_source(wiki_dir, attach_subpath, original)
        sent_hash = request.forms.getunicode("origin", "")
        if refused:
            # 本文が手元に無い状態で先へ進むと、空とみなしてページを消しかねない。
            # 断りだけを伝えて編集画面に戻す。書きかけを預かっていれば、
            # 画面にはそれを出す（送れなかっただけで、書いたものは残っている）
            message = refused
            source = None
            typed = load_draft(wiki_dir, attach_subpath)
        elif sent_hash and sent_hash != source_hash(original) and source != original:
            # 編集中に他の誰か（別タブ・セクション編集など）が保存した。かつ、
            # 自分の編集結果（source）も、その保存後の内容（original）とは
            # 異なる。**この2つがそろって初めて競合**（Wiki設計者の指示、2026-09-04。
            # A≠C だけでなく B≠C も要る、というA/B/C三者の定義の見直し）。
            #
            # A≠Cだけで競合と決めていた以前は、自分の編集結果がたまたま
            # 相手の保存後の内容と一致していても（統合すべき差分が無くても）
            # 競合画面へ送っていた。統合画面のdiffmergeが「+0 -0」と出るだけの
            # 画面になり、利用者が戸惑う不具合として報告された。
            #
            # **統合する画面へ送る**（Wiki設計者の指示、2026-09-01）。以前はここで
            # 「別の場所で更新されています」と断るだけで、押し直せば相手の
            # 変更をまるごと上書きしていた。自分の編集に相手の変更を
            # 相違点ごとに取り込めるようにする（wikilib.conflict）。
            #
            # 送られた本文は書きかけとして預け直す。統合画面はそれを
            # 「自分の編集」として読む。origin（＝編集を始めた時点の
            # ハッシュ）も一緒に残し、統合の結果を保存するときまで
            # 「何から分かれた変更なのか」を保つ。
            save_draft(wiki_dir, attach_subpath, source, sent_hash)
            # 記法の選び直しも引き継ぐ。統合画面には記法を選ぶところが無いので、
            # ここで渡さないと、選び直したことが黙って無かったことになる
            chosen = request.forms.getunicode("markup", "")
            return HTTPResponse(status=303, headers={
                "Location": (context.base_url + "/" + CONFLICT_URLPATH + "/" + pagepath
                             + ("?markup=" + chosen if chosen in MARKUP_FORMATS else "")),
            })
        elif sent_hash and sent_hash != source_hash(original):
            # A≠C だが B＝C（自分の編集結果が、その保存後の内容と一致して
            # いる）。統合すべき差分が無いので競合ではない。書き込みは不要
            # （内容が同じため）で、書きかけを消してページへ戻る。
            delete_draft(wiki_dir, attach_subpath)
            if continuous:
                return render_edit(wiki_dir, config, farm, pagepath, explicit_farm,
                                   _reopened="内容は保存されているものと同じだったので、何も書き込みませんでした。")
            return HTTPResponse(status=303, headers={
                "Location": context.base_url + "/" + pagepath,
            })
        elif not source.strip():
            # 本文を空にして保存する＝そのページを消す、という約束にしてある。
            # ファイルごと消すので、空のページが残ることはない。
            if is_new:
                # まだ無いページを空のまま保存しても、作らずに戻るだけ
                if continuous:
                    return render_edit(wiki_dir, config, farm, pagepath, explicit_farm,
                                       _reopened="本文が空のままなので、ページは作りませんでした。")
                return HTTPResponse(status=303, headers={
                    "Location": context.base_url + "/" + pagepath,
                })
            ok, notice = delete_page(wiki_dir, config, ref)
            if not ok:
                message = notice
                typed = source
            else:
                delete_draft(wiki_dir, attach_subpath)
                # 消えたページへ戻す。「このページはまだありません」の画面になり、
                # そこから作り直すこともできる
                return HTTPResponse(status=303, headers={
                    "Location": context.base_url + "/" + pagepath,
                })
        else:
            # &date; &time; &now; &t; &page; &fpage; …保存した瞬間の値を
            # そのまま書き込む、プラグインではない置換（wikilib.subst）。
            # 一時保存ではなく、実際に保存されるこの場所でだけ行う
            # （書きかけの段階で日付を確定させてしまわないようにするため）。
            source = save_time_replace(source, pagepath)

            # 記法は画面のラジオボタンで選ばれる。ページの記法は拡張子で決まるので、
            # 選び直されていれば保存先のファイル名も変わる（本文はそのまま。
            # 記法を移す＝書き直す作業なので、システムが勝手に変換はしない）。
            # 置き場所の決まり（フォルダの階層・index）は記法によらず同じ。
            new_ext = markup_ext_or(request.forms.getunicode("markup", ""), ext)
            # 保存先は attach_subpath（実際に解決されたファイル、拡張子抜き）を使う。
            # "/Tech" のようなフォルダ相当のURLは "Tech/index" に解決されているため、
            # ページパスをそのまま使うと別のファイルを作ってしまう。
            path = page_file_path(wiki_dir, attach_subpath, new_ext)
            if path is None:
                return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)
            # 差分の「変更前」は、**システムが最後に知っている内容**（DB）を使う。
            # 平文ファイルのほう（original）だと、システムを通さない書き換えが
            # あった場合にその書き換え後を「変更前」と見なしてしまい、
            # 直接編集した分が記録から抜け落ちる。DBに無ければ平文で代える。
            # 新規作成も「空からの差分」として残るので、あとから差分を順に
            # 逆適用していけば最初の版までさかのぼれる。
            known = load_page_body(wiki_dir, attach_subpath)
            save_page(wiki_dir, config, attach_subpath, new_ext, source, engine=engine,
                      path=path, known=original if known is None else known)
            if not is_new and new_ext != ext:
                # 記法を移した。前の拡張子のファイルは必ず消す。残しておくと
                # 同じページが2つある状態になり、どちらが開かれるかは
                # PAGE_EXTS の順（.txt が先）で決まってしまう
                old_path = page_file_path(wiki_dir, attach_subpath, ext)
                if old_path and os.path.isfile(old_path):
                    os.remove(old_path)
            # 本保存できたので、預かっていた書きかけは役目を終える
            delete_draft(wiki_dir, attach_subpath)
            # 保存できたらページ本体へ戻す。**連続編集なら戻らず、保存した内容で
            # 編集画面を開き直す**（削除は別。消えたページの案内を見せるため、
            # 上でそのまま戻している）
            if continuous:
                return render_edit(wiki_dir, config, farm, pagepath, explicit_farm,
                                   _reopened="保存しました（" + time.strftime("%H:%M:%S") + "）。")
            return HTTPResponse(status=303, headers={
                "Location": context.base_url + "/" + pagepath,
            })

    # 一時保存を預かっていれば、その続きから書けるようにする。
    #
    # 競合の判定（origin）は、**書きかけが無ければ**今のファイルを基準にする。
    # 書きかけがある場合は、預けた時点の本文のハッシュ（load_draft_origin）を
    # そのまま使う（今のファイルの最新ハッシュに更新し直さない）。ここを
    # 最新化してしまうと、「書きかけを預けてから他の誰かがページを更新した」
    # ことを保存時に検出できなくなる（一時中断→再開の間に横から更新が
    # あっても、次の cmd=edit のたびに origin が最新へすり替わってしまい、
    # sent_hash != source_hash(original) のチェックを素通りしてしまうため。
    # wikiPluginからの報告で発覚）。
    shown, draft_notice = original if typed is None else typed, ""
    origin_for_form = source_hash(original)
    if cmd == "edit":
        # フォームを開くためだけのPOST（本文は送られてこない）。以前は
        # GETでここに来ていたときの判定（request.method != "POST"）だったが、
        # GETを塞いだのでcmd=editで区別する。
        drafted = load_draft(wiki_dir, attach_subpath)
        if drafted is not None and drafted != original:
            shown = drafted
            draft_notice = (
                "一時保存していた内容を開いています。"
                "保存すればページに反映され、本文を元に戻せば預かりも解けます。"
            )
            # 古い書きかけ（originを持たずに預けられたもの）は分からないので、
            # やむを得ず今のファイル基準のまま（origin_for_formは変えない）
            draft_origin = load_draft_origin(wiki_dir, attach_subpath)
            if draft_origin:
                origin_for_form = draft_origin
        elif drafted is not None:
            delete_draft(wiki_dir, attach_subpath)  # 中身が同じなら預かる意味がない


    # 記法の選択は、保存されているファイルの拡張子が初期値。POSTで戻ってきた
    # ときは選び直した内容を保つ（保存できずに画面へ戻す場合があるため）。
    markup = request.forms.getunicode("markup", "") if request.method == "POST" else ""
    if markup not in MARKUP_FORMATS:
        markup = markup_name_for(ext)
    attach_panel = build_attach_panel_html(
        list_attachments(wiki_dir, attach_subpath, context.base_url),
        attach_subpath, edit_url,
        tree_url=context.base_url + "/" + PAGETREE_URLPATH,
        attach_message=attach_notice,
        attach_ok=attach_ok_flag,
        max_bytes=attach_max_bytes(config),
        index_shown=show_index(config),
        ext=MARKUP_FORMATS[markup]["ext"],
    )
    body = build_editor_html(
        markup, shown, origin_for_form, is_new,
        action=edit_url,
        # プレビューと差分は、ページ自身の通常URLへ `?cmd=…` で送る
        # （Wiki設計者の指示、2026-09-17。編集・保存と同じ入口に揃えた）
        preview_url=context.base_url + "/" + pagepath + "?cmd=preview",
        editor_url=context.base_url + "/" + EDITOR_URLPATH,
        message=message,
        attach_panel=attach_panel,
        active_tab=initial_tab,
        diff_url=context.base_url + "/" + pagepath + "?cmd=diff",
        origin_html=render_original_html(engine, config, context, original, ext, attach_subpath),
        draft_notice=draft_notice,
        saved_notice=_reopened or "",
        saved_text=_saved_text(wiki_dir, attach_subpath, original),
        # 履歴タブは、プレビュー・差分と同じくページ自身のURLへ `?cmd=history`
        # （wikilib.backupui。以前の /.backup）
        history_url=history_action_url(context.base_url, pagepath),
        files_url=files_url_of(context.base_url, pagepath),
        config=config,
    )
    # 編集は行き来が多い作業なので、次に開くページをその場で選べるようにする
    page_list = build_page_list_html(
        context.base_url, wiki_dir, attach_subpath, config,
        index_shown=show_index(config), title_length=title_length_of(config))
    theme_conf = config.get("theme") or {}
    plugin_dir = farm_plugin_dir(wiki_dir)
    # 編集画面は「保存済みの本文で実際に使われたプラグイン」だけでなく、
    # レジストリにある全プラグインのCSS/JSを読み込む。編集中は保存前の
    # 本文にまだ現れていないプラグインも自由に書けるため、context.used_plugins
    # （保存済みの本文をレンダリングして得た集合）だけを見ていると、その場で
    # 新しく使ったプラグイン（例: 元々#preを使っていないページで#preを書き
    # 始めた場合）の資材が一切読み込まれず、プレビューの見た目・動作が
    # 通常表示と食い違ってしまう（セクション編集のプレビューは
    # innerHTMLへの差し込みだけで<head>への<link>追加は行わないため、
    # なおさら顕在化する）。通常のページ表示では逆に「実際に使われた
    # プラグインだけ」に絞る意味があるが、編集画面はその限りではない。
    all_plugin_names = (context.registry or {}).keys()
    page = build_edit_page_html(
        title=("新規作成: " if is_new else "編集: ") + (pagepath or farm),
        site_title=theme_conf.get("site_title", "wikiSystem"),
        home_url=context.base_url + "/",
        cancel_url=context.base_url + "/" + pagepath,
        editor_url=context.base_url + "/" + EDITOR_URLPATH,
        treeview_url=context.base_url + "/" + TREEVIEW_URLPATH,
        page_label=pagepath or TOP_PAGE_LABEL,
        page_list=page_list,
        body=body,
        plugin_styles=plugin_style_urls(context.base_url, plugin_dir, all_plugin_names),
        plugin_scripts=plugin_script_urls(context.base_url, plugin_dir, all_plugin_names),
        theme_css="{}/{}/{}.css".format(
            context.base_url, THEME_URLPATH, theme_conf.get("name", DEFAULT_THEMEFILE)),
        is_new=is_new,
    )
    return HTTPResponse(body=page, status=200,
                        content_type="text/html; charset=utf-8")


_FORM_OPEN_TAG_RE = re.compile(r"<form\b", re.IGNORECASE)
_FORM_CLOSE_TAG_RE = re.compile(r"</form\s*>", re.IGNORECASE)
_FORM_CONTROL_TAG_RE = re.compile(r"<(input|select|textarea|button)\b", re.IGNORECASE)


def disable_embedded_forms(html):
    """本文（プラグインの出力を含む）に混じった <form> を、機能しない <div> に
    付け替える。

    編集画面の「オリジナル」欄・ライブプレビューは、本文をレンダリングした
    結果をそのまま埋め込む。プラグインが `<form>` を返すHTML（例:
    コメント投稿フォーム）だと、**プレビューを見ているだけのつもりで投稿
    できてしまう**。プレビューは見るためのものなので、送信できてはいけない。

    タグ名だけを `div` に差し替え、属性はそのまま残す（`method`/`action`
    などform向けの属性が `div` に付いても実害はない）。中の
    `<input>`/`<select>`/`<textarea>`/`<button>` にも `disabled` を付けて、
    押しても何も起きない・送信データにも入らない状態にする。

    **JavaScript側でも同じことを止めている**（editor.js の makeInert。
    送信は capture で握りつぶし、リンクはShift+クリックのときだけ通す）。
    どちらか一方ではなく両方でふさぐのは、JSが動かない場合にも
    「プレビューから投稿できてしまう」ことを起こさないため。

    ## 以前はもう1つ理由があった（2026-09-01に解消）

    かつては編集画面の全体が1つの `<form>` で囲まれていたため、本文の
    `<form>` がその内側に入ると**入れ子**になった。HTMLは `<form>` の
    入れ子を許さないので、ブラウザは内側の開始タグを無視した上で内側の
    終了タグで外側を閉じてしまい、それより後ろの保存ボタンがフォームの外に
    出て機能しなくなる。さらに、入れ子が消えた結果として中の部品が外側の
    フォームに所有され、`required` 付きの欄（例: `#comment()` の
    メッセージ欄）が未入力のまま必須項目と見なされて保存がブロックされる、
    という不具合も起きた（wikiPluginからの報告・実機確認済み）。

    いまは**囲んでいるのが送信ボタンだけ**（`.edit-actions`）で、本文の
    埋め込み先はその外にあるため、入れ子そのものが起こらない。この関数が
    受け持つのは「プレビューから送信できてしまう」ことだけになった。"""
    html = _FORM_OPEN_TAG_RE.sub("<div", html)
    html = _FORM_CLOSE_TAG_RE.sub("</div>", html)
    html = _FORM_CONTROL_TAG_RE.sub(lambda m: f"<{m.group(1)} disabled", html)
    return html


def render_original_html(engine, config, context, original, ext, attach_subpath):
    """「更新状況」の右側に並べる、保存されている内容の表示を作る。

    **1行目のh1はタイトルとして抜かず、見出しのまま描く。** 隣に並べる
    プレビューが生テキストをそのまま描いていて、そちらにはh1が残るためである。
    片方だけ抜くと、先頭がまるごと1つぶんずれるうえに、h1が対応点にならない
    （閲覧時の見た目に合わせるより、隣と揃うほうがこの画面では役に立つ）。

    まだ無いページは、そのまま出しても比べる意味が薄いので、
    断り書きだけを返す。"""
    if not original.strip():
        return '<p class="edit-origin-empty">まだ保存されていません（新しいページです）。</p>'
    md_conf = config.get("markdown") or {}
    content, _title, _toc = render_source(
        engine, original, ext, False, context, toc_depth=md_conf.get("toc_depth", 3),
    )
    content = rewrite_content_links(content, context.base_url, attach_subpath, context.wiki_dir)
    # ここは編集用の外側 <form> の内側に埋め込まれる（「オリジナル」欄）。
    # 本文の <form> を生かしたままだと、外側の <form> がHTML的に壊れる
    return disable_embedded_forms(content)


def render_diff(wiki_dir, config, farm, explicit_farm, pagepath):
    """差分（`POST <ページパス>?cmd=diff`）。編集中の内容と、保存されている内容の
    差分をHTMLで返す（編集画面の「更新状況」タブ用）。

    差分の各行には、その行がオリジナルのどの見出しに属するかを持たせる。
    左右のスクロール位置を見出しで揃えるため（editdiff.py 参照）。

    **編集の権限（`W`）が無ければ403**（Wiki設計者の指示、2026-09-17）。こちらは
    **保存されている本文を差分の相手として読む**ので、プレビューより強い理由がある。"""
    from wikilib import auth  # 循環を避けるため呼び出し時に読み込む

    if auth.page_privilege(wiki_dir, auth.current_uid(wiki_dir, farm)
                           ).check(pagepath) != auth.PAGE_WRITE:
        return plain("このページを編集する権限がありません。", status=403)
    ref = resolve_page_ref(wiki_dir, pagepath, default_markup(config))
    if ref is None or not is_valid_pagepath(pagepath):
        return plain("no page", status=404)

    source = request.body.read().decode("utf-8", errors="replace")
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm, partial=True,
                                  ext=ref.ext)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)

    # 比べる相手は**公開されている内容**（DB）。現存ファイルはまだ取り込んで
    # いない作業中のものかもしれず、確定していないものと比べても意味がない
    known = load_page_body(wiki_dir, ref.subpath)
    if known is None:
        known = ref.body
    diff_text = make_diff(known, source, ref.subpath, "公開されている内容", "編集中")
    html = build_diff_html(diff_text, source_anchors(engine, known, ref.ext))
    return HTTPResponse(body=html, status=200,
                        content_type="text/html; charset=utf-8")


def heading_positions_of(wiki_dir, config, text, ext):
    """生ソースから見出し位置一覧と、タイトルの終了行を返す。"""
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir))
    tokens = parse_source(engine, text, ext)
    md_conf = config.get("markdown") or {}
    _, tokens, intro_start = split_title(
        tokens, uses_title_heading(ext, md_conf.get("first_h1_as_title", True)))
    return heading_positions(tokens), intro_start


def page_heading_positions(wiki_dir, config, pagepath):
    """ページの生ソースと見出し位置一覧 (heading_positions)、タイトルの終了行を返す。
    ページが無ければNone。first_h1_as_titleでタイトルとして抜き出された見出しは
    セクションの対象から外れる（本文にも目次にも出てこないため）。"""
    ref = resolve_page_ref(wiki_dir, pagepath)
    if ref is None or not ref.exists:
        return None
    positions, intro_start = heading_positions_of(
        wiki_dir, config, ref.body, ref.ext)
    return ref.body, positions, intro_start


def page_view_block(wiki_dir, config, farm, pagepath, explicit_farm=False):
    """そのページがプラグインに表示を止められていれば、その中身を返す。
    止められていなければNone（`PluginContext.block_view`）。

    **描いてみないと分からない。** 止めるかどうかを決めるのはプラグインの
    `_convert` で、それが動くのは解析のときではなく描画のとき。見出しの位置を
    数えるだけの `heading_positions_of` が解析しか通さないのはそのためで、
    こちらは本文を1回描いて確かめている。

    使うのはセクション編集の入口（`serve_section`）だけ。押されたときにしか
    通らない道なので、1回ぶんの描画は引き合う。"""
    ref = resolve_page_ref(wiki_dir, pagepath)
    if ref is None or not ref.exists:
        return None
    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm,
                                  ext=ref.ext)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    md_conf = config.get("markdown") or {}
    render_source(engine, ref.body, ref.ext,
                  md_conf.get("first_h1_as_title", True), context)
    return context.view_block


def _section_params():
    """開くときの宛先（見出しid・範囲）を取り出す。**保存では使わない。**

    保存はページ全体を受け取るので、そのとき見出しidを見る必要がない
    （Wiki設計者の指示、2026-09-01。「これが実現できるなら id 管理なども不要」）。"""
    heading_id = request.query.getunicode("heading") or None
    scope = request.query.getunicode("scope", "body")
    return heading_id, (scope if scope in ("header", "body") else "body")


def serve_section(wiki_dir, config, farm, pagepath, explicit_farm=False):
    """セクション単位の生テキスト。**GETで取り出し、POSTで保存する。**

    GETのクエリは heading（見出しid。省略時は最初の見出しより前の領域）と
    scope（header/body。既定はbody）。

        （既定）    その節の生テキストだけをそのまま返す
        parts=1     前後も添えてJSONで返す（保存まで行うならこちら）

    `parts=1` を足したのは、**保存の送信をページ全体にした**ため
    （Wiki設計者の指示、2026-09-01）。画面は前後を隠し持っておき、編集した節と
    繋いで送り返す。3つを繋ぐと元のページに戻るので、保存は編集画面からの
    保存とまったく同じ扱いになる。

        {"before": …, "section": …, "after": …, "origin": …}

    origin は**そのときのページ全体のハッシュ**で、保存のときに競合の判定に
    使う（editor.source_hash。編集画面の origin と同じもの）。

    ## 表示を止められているページでは受け付けない

    `#viewable_period` のようなプラグインが表示を止めているページでは、
    画面に出ているのは案内文で、本文ではない。そこで節を選ぼうとしても
    **選んでいるつもりの場所と、実際に編集される場所が食い違う**
    （どの節かは画面が見出しidで指すが、切り出すのはサーバーが本物の本文
    から行うため）。書き戻す位置が狂うことは無いが、分かりにくい。

    **対象の節が正しく選べない以上、そもそも受け付けない**
    （Wiki設計者の指示、2026-09-05）。取り出し（GET）も保存（POST）も断る。
    **編集そのものは止めない**——編集ボタンからの通常の編集画面は
    これまでどおり開ける（そちらは本文の全体を扱うので、食い違いが無い）。

    ## 編集の権限が無ければ受け付けない

    権限が `W` でなければ、取り出し（GET）も保存（POST）も403で断る
    （Wiki設計者の指示、2026-09-17）。テーマは権限が無ければ `data-editable` を
    出さないので画面からは始まらないが、URLを直に叩けばここへ届く。"""
    from wikilib import auth  # 循環を避けるため呼び出し時に読み込む

    uid = auth.current_uid(wiki_dir, farm)
    if auth.page_privilege(wiki_dir, uid).check(pagepath) != auth.PAGE_WRITE:
        return plain("このページを編集する権限がありません。", status=403)
    if page_view_block(wiki_dir, config, farm, pagepath, explicit_farm) is not None:
        return plain("このページはいま表示できないため、"
                     "セクション編集はできません（編集画面からは編集できます）。",
                     status=403)
    if request.method == "POST":
        return save_section(wiki_dir, config, farm, pagepath, explicit_farm)

    found = page_heading_positions(wiki_dir, config, pagepath)
    if found is None:
        return plain("no page", status=404)
    body, positions, intro_start = found
    heading_id, scope = _section_params()

    if request.query.get("parts"):
        parts = split_section_text(body, positions, heading_id, scope, intro_start)
        if parts is None:
            return plain("no page", status=404)
        before, section, after = parts
        return _section_json({"before": before, "section": section,
                              "after": after, "origin": source_hash(body)})

    text = extract_section_text(body, positions, heading_id, scope, intro_start)
    if text is None:
        return plain("no page", status=404)
    return plain(text)


def save_section(wiki_dir, config, farm, pagepath, explicit_farm):
    """セクション編集からの保存（`POST /.section/<ページパス>`）。

    **送られてくるのはページ全体**なので、保存そのものは編集画面からの保存と
    同じ扱いになる（Wiki設計者の指示、2026-09-01。「POSTするのは編集領域前後の
    テキストを hidden にて。これによりページ全体を送信することとなり、
    新規保存と等価となる」）。

    受け取るもの（フォーム）:

        source    ページ全体（前 ＋ 編集した節 ＋ 後）
        origin    開いたときのページ全体のハッシュ（parts=1 が返したもの）

    **どの節をどこへ書き戻すか、という話がここには出てこない。** 見出しidが
    後から変わっても、切り出した範囲が画面とサーバーで食い違っていても、
    保存の正しさには関わらなくなった。画面側が編集領域を上下へ広げるのも、
    前後の持ちかたを変えるだけで済む。

    **長い本文は何回かに分けて送れる**（wikilib.chunked。編集画面の一時保存と
    同じ仕組み）。ページ全体を送ることになるので、1回のPOSTの上限に届く
    ページが出てくるため。そろうまでは204を返す。

    応答はJSON。呼ぶ側はページの中に居るので、画面をまるごと入れ替えるのでは
    なく、結果だけを返して画面側に決めさせる。

        {"ok": true,  "changed": …, "url": …}        保存できた
        {"ok": false, "conflict": true, "url": …}    統合する画面へ行ってほしい
        {"ok": false, "message": …}                  断った（理由を出す）
    """
    ref = resolve_page_ref(wiki_dir, pagepath)
    if ref is None or not ref.exists:
        return _section_json({"ok": False, "message": "そのページはありません。"}, 404)

    origin_sent = request.forms.getunicode("origin", "")
    if is_chunked():
        # 切って送られてきた。そろうまでは置いておき、最後の1つを受け取った
        # 回だけ先へ進む（編集画面の一時保存と同じ道）
        state, path, refused = take_chunk(wiki_dir)
        if state == "error":
            return _section_json({"ok": False, "message": refused}, 400)
        if state == "more":
            return HTTPResponse(status=204)
        chunk_id = request.forms.getunicode("chunk_id", "")
        try:
            with open(path, encoding="utf-8") as f:
                text = normalize_newlines(f.read())
        except OSError:
            finish_chunk(wiki_dir, chunk_id)
            return _section_json(
                {"ok": False, "message": "受け取ったものを読めませんでした。"}, 500)
        finish_chunk(wiki_dir, chunk_id)
    else:
        text, refused, status = source_from_form()
        if refused:
            return _section_json({"ok": False, "message": refused}, status)

    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm)
    page_url = context.base_url + "/" + pagepath

    if origin_sent and origin_sent != source_hash(ref.body) and text != ref.body:
        # 開いてからの間に、このページは別の場所で保存されている。かつ、
        # 自分のこの節の編集結果も、その保存後の内容とは異なる。**この2つが
        # そろって初めて競合**（Wiki設計者の指示、2026-09-04。編集画面の保存と
        # 同じ定義に揃えた）。text == ref.body（自分の結果が保存後の内容と
        # 一致）なら、統合すべき差分が無いので下の「変更なし」へ素通りする。
        # 編集画面からの保存と同じ扱いで、統合する画面へ送る
        return _section_conflict(wiki_dir, ref, context, pagepath, text, origin_sent)

    if text == ref.body:
        return _section_json({"ok": True, "changed": False, "url": page_url})
    if not text.strip():
        # 節を空にしただけでページごと消えるのは意外すぎる。削除は編集画面から
        return _section_json({"ok": False, "message": (
            "保存するとページが空になります。"
            "削除したい場合は編集画面から行ってください。")}, 409)

    path = page_file_path(wiki_dir, ref.subpath, ref.ext)
    if path is None:
        return _section_json({"ok": False, "message": "保存先を決められませんでした。"}, 500)
    # 差分の「変更前」はDBの内容（＝システムが最後に知っている内容）。
    # 詳しくは pagesave の冒頭
    known = load_page_body(wiki_dir, ref.subpath)
    if not save_page(wiki_dir, config, ref.subpath, ref.ext,
                     save_time_replace(text, pagepath), path=path,
                     known=ref.body if known is None else known):
        return _section_json({"ok": False, "message": "保存できませんでした。"}, 500)
    # **書きかけには触らない。** 別の場所で編集中の人のものなので、消すと
    # その人の書きかけが黙って失われる（編集画面からの保存は自分のものを
    # 片付けているので、そちらとは事情が違う）
    return _section_json({"ok": True, "changed": True, "url": page_url})


def _section_conflict(wiki_dir, ref, context, pagepath, text, origin_sent):
    """セクション保存が競合したとき、統合する画面へ渡す下ごしらえをする。"""
    drafted = load_draft(wiki_dir, ref.subpath)
    if drafted is not None and drafted != ref.body:
        # 預かっている書きかけは、別の場所で編集中の誰かのもの。ここで
        # 自分の内容を預けると、その人の書きかけを黙って上書きしてしまう
        # （書きかけはページに1つしか持てない）。この場合だけは断る
        return _section_json({"ok": False, "message": (
            "このページは別の場所で編集中（書きかけを預かっています）で、"
            "しかもその間に更新もありました。編集画面から統合してください。")}, 409)

    save_draft(wiki_dir, ref.subpath, text, origin_sent)
    return _section_json({
        "ok": False, "conflict": True,
        "url": context.base_url + "/" + CONFLICT_URLPATH + "/" + pagepath,
        "message": ("開いてからの間に、このページは別の場所で更新されました。"
                    "統合する画面で突き合わせてください。"),
    }, 409)


def _section_json(obj, status=200):
    return HTTPResponse(body=json.dumps(obj, ensure_ascii=False), status=status,
                        content_type="application/json; charset=utf-8")


def tag_source_lines(tokens):
    """ブロック要素の開始トークンに、元テキストの行番号を `data-line` として
    振る（本文とプレビューのスクロール同期に使う。編集画面のプレビューだけに
    適用し、保存後の通常表示には影響しない）。

    `token.map`（行範囲）は開始トークン（`nesting` が 1＝開くタグ、または
    0＝`html_block`/`code_block`のような単体トークン）にだけ入っており、
    閉じトークン（`nesting == -1`）には無いので、そちらは対象にしない。"""
    for token in tokens:
        if token.block and token.map and token.nesting >= 0:
            token.attrSet("data-line", str(token.map[0]))


# プレビューの応答で、描いた断片が使ったプラグインのCSS・JSのURLを渡すヘッダー
# （JSONの配列。`json.dumps` の既定で非ASCIIは \uXXXX になり、ヘッダーに載せられる）
PREVIEW_STYLES_HEADER = "X-Wiki-Plugin-Styles"
PREVIEW_SCRIPTS_HEADER = "X-Wiki-Plugin-Scripts"


def render_preview(wiki_dir, config, farm, explicit_farm, pagepath):
    """プレビュー（`POST <ページパス>?cmd=preview`）。POSTされた生テキストを、
    保存時と同じレンダラでHTML断片に変換して返す（テーマは適用しない）。ページ全体では
    なく編集中の断片を渡すため、そのページのタイトル抽出（first_h1_as_title）は適用しない。

    編集画面のプレビューと、セクション編集のプレビューが使う。

    **編集の権限（`W`）が無ければ403**（Wiki設計者の指示、2026-09-17）。返すのは送られた
    本文を描いたものだけだが、プレビューは編集の途中にしか出てこないので、編集画面・
    セクション編集と同じ扱いに揃える。"""
    from wikilib import auth  # 循環を避けるため呼び出し時に読み込む

    if auth.page_privilege(wiki_dir, auth.current_uid(wiki_dir, farm)
                           ).check(pagepath) != auth.PAGE_WRITE:
        return plain("このページを編集する権限がありません。", status=403)
    # まだ保存していない新規ページも編集画面からプレビューできるよう、
    # 実在するかどうかは問わない（添付の参照先は解決済みのsubpathを使う）。
    ref = resolve_page_ref(wiki_dir, pagepath, default_markup(config))
    if ref is None or not is_valid_pagepath(pagepath):
        return plain("no page", status=404)
    attach_subpath = ref.subpath

    text = request.body.read().decode("utf-8", errors="replace")
    # 描く記法は、編集画面で選ばれているもの（?markup=…）。指定が無ければ
    # 保存されているページの記法。**保存前に切り替えた記法で確かめられる**ように
    # するためで、ここが保存済みの拡張子に固定だと、記法を移すときに
    # プレビューだけ古い記法のままになる。
    ext = markup_ext_or(request.query.getunicode("markup", ""), ref.ext)
    # partial=True。ページ全体の情報が要るプラグインは、ここでは処理せず断り書きを出す
    context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm, partial=True,
                                  ext=ext)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
    env = {"wiki": context}
    tokens = parse_source(engine, text, ext, env)
    tag_source_lines(tokens)
    html = engine.renderer.render(tokens, engine.options, env)

    html = rewrite_content_links(html, context.base_url, attach_subpath, wiki_dir)
    # 保存前の見た目確認でしかない。本文の <form>（コメント投稿等）が
    # 生きたままだと、プレビュー中に本物の投稿ができてしまう
    html = disable_embedded_forms(html)
    # 描いた断片が使ったプラグインの資材。節編集のプレビュー（theme/common.js）は、
    # ページがまだ読み込んでいないものだけを後から読み込む（ページが元々使って
    # いないプラグイン、たとえば初めて書いた数式も組版されるように）。本文は
    # 変えずヘッダーで渡すので、全資材を読み込み済みの編集画面は読まなくてよい
    plugin_dir = farm_plugin_dir(wiki_dir)
    headers = {
        PREVIEW_STYLES_HEADER: json.dumps(
            plugin_style_urls(context.base_url, plugin_dir, context.used_plugins)),
        PREVIEW_SCRIPTS_HEADER: json.dumps(
            plugin_script_urls(context.base_url, plugin_dir, context.used_plugins)),
    }
    return HTTPResponse(body=html, status=200, content_type="text/html; charset=utf-8",
                        headers=headers)
