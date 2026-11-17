"""表記の変換（PukiWiki記法 ⇔ Markdown）の管理ページ。`POST <ページパス>`（`cmd=convert`）。

編集画面のタブの行の右端にある**表記ボタン**から開く。変換そのものは
`wikilib.markupconv` が行い、ここは画面と、ファイルの置き換えを受け持つ。

## 流れ

    表記ボタン（step 無し）
        編集画面の今の本文（未保存の書き換えを含む）を受け取り、もう一方の書きかたへ
        変換する。変換先は**同じフォルダの `=名前.拡張子`**（`A.txt` なら `=A.md`）に
        書き出し、元と変換後をタブで切り替えて、それぞれコードとプレビューを見せる
    ［確定］（step=apply）
        `=` のファイルの中身で、ページをその書きかたで保存し直す。元の拡張子の
        ファイルは消す。ページの履歴には1回の保存として残る（直前の保存とはまとめない）
    ［やめる］（step=cancel）
        `=` のファイルを消して、編集画面へ戻る。書きかけはそのまま残る

## `=` で始まる名前にする理由

`=` で始まる名前は、ページ名には使えない（`paths.is_valid_pagepath`。Wiki 指定の印）。
そのため、ページの列挙・取り込み・ページ一覧・ファイル一覧のどれにも拾われない。
変換の途中のファイルを置いても、ほかの仕組みに影響しない（ロードマップの指定）。

## クロコの実装例（設計者は未確認）

  - 送り先はページ自身の URL に `cmd=convert`。編集画面まわりの操作（保存・プレビュー・
    差分・履歴）と同じ入口に揃えた
  - 管理ページを開くたびに変換し直し、`=` のファイルを上書きする（変換するのは
    その時点の編集画面の本文なので、前回のものを使い回すと食い違う）
  - ［確定］のとき、開いてからページが保存し直されていたり、`=` のファイルが
    書き換えられていたりしたら断る（見たものと違うものを保存しないため）
  - 新しいページ（まだファイルが無い）は変換しない。書きかたは編集画面の
    「書きかた」の選択で選ぶ
"""
import hashlib
import os
import time
from html import escape

from bottle import HTTPResponse, request

from wikilib import markupconv
from wikilib.draft import delete_draft
from wikilib.pagedb import load_page_body
from wikilib.pagesave import save_page
from wikilib.paths import (
    DEFAULT_THEMEFILE, EDITOR_URLPATH, FARM_PREFIX, MARKUP_FORMATS, PAGE_EXTS, THEME_URLPATH,
    farm_plugin_dir, is_valid_pagepath, markup_format_for, markup_name_for,
    page_file_path, resolve_page_ref,
)
from wikilib.plugins import build_markdown_renderer
from wikilib.subst import save_time_replace
from wikilib.themes import make_plugin_context
from wikilib.views import render_no_edit, render_no_page
from wikilib.web import plain
from wikilib.wikiconfig import default_markup

# 変換の向き。書きかたの名前（MARKUP_FORMATS のキー）→ (変換先, 変換する関数)
_DIRECTIONS = {
    "pukiwiki": ("markdown", markupconv.pukiwiki_to_markdown),
    "markdown": ("pukiwiki", markupconv.markdown_to_pukiwiki),
}


def target_markup(ext):
    """その拡張子のページを変換する先の書きかたの名前。変換できなければ None。"""
    direction = _DIRECTIONS.get(markup_name_for(ext))
    return direction[0] if direction else None


def temp_path(wiki_dir, subpath, ext):
    """変換先を置くファイル（`<フォルダ>/=<名前><拡張子>`）。Wiki の外へ出るなら None。"""
    folder, name = os.path.split(subpath)
    return page_file_path(wiki_dir, os.path.join(folder, FARM_PREFIX + name), ext)


def remove_temps(wiki_dir, subpath):
    """そのページの変換先のファイルを消す（ページを消す・名前を変えるときの後片付け）。"""
    for ext in PAGE_EXTS:
        path = temp_path(wiki_dir, subpath, ext)
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _edit_url(base_url, pagepath):
    return base_url + "/" + pagepath


def serve_convert(wiki_dir, config, farm, explicit_farm, pagepath):
    """表記ボタン・［確定］・［やめる］を受ける。権限は編集（W）と同じ。"""
    from wikilib import auth
    from wikilib.editor import posted_source, render_edit, source_hash

    if not is_valid_pagepath(pagepath):
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)
    uid = auth.current_uid(wiki_dir, farm)
    if auth.page_privilege(wiki_dir, uid).check(pagepath) != auth.PAGE_WRITE:
        return render_no_edit(wiki_dir, config, farm, pagepath, explicit_farm,
                              logged_in=uid is not None)
    ref = resolve_page_ref(wiki_dir, pagepath, default_markup(config))
    if ref is None:
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)

    def back(notice):
        """編集画面を開き直す（連続編集のあとと同じ道。cmd=edit として読み直す）。"""
        return render_edit(wiki_dir, config, farm, pagepath, explicit_farm, _reopened=notice)

    if not ref.exists:
        return back("新しいページは変換できません。書きかたは右下の「書きかた」で選んでください。")
    to_name = target_markup(ref.ext)
    if to_name is None:
        return back("このページの書きかたは変換できません。")
    to_ext = MARKUP_FORMATS[to_name]["ext"]
    path = temp_path(wiki_dir, ref.subpath, to_ext)
    if path is None:
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)
    step = request.forms.getunicode("step", "")
    if os.path.isfile(page_file_path(wiki_dir, ref.subpath, to_ext) or ""):
        # 同じ名前の .txt と .md が両方ある（重複）。置き換えると、もう一方を上書きしてしまう
        remove_temps(wiki_dir, ref.subpath)
        return back("同じ名前の{}のファイルがあるため、変換できません。"
                    "先にページの重複を整理してください。".format(MARKUP_FORMATS[to_name]["label"]))

    if step == "cancel":
        remove_temps(wiki_dir, ref.subpath)
        return back("表記の変換をやめました。")

    if step == "apply":
        try:
            with open(path, encoding="utf-8") as f:
                converted = f.read()
        except OSError:
            return back("変換したものが見つかりませんでした。もう一度、表記ボタンから変換してください。")
        if (request.forms.getunicode("base", "") != source_hash(ref.body)
                or request.forms.getunicode("conv", "") != _hash(converted)):
            remove_temps(wiki_dir, ref.subpath)
            return back("変換を始めてから、ページか変換したものが書き換えられていました。"
                        "保存はしていません。もう一度、表記ボタンから変換してください。")
        target = page_file_path(wiki_dir, ref.subpath, to_ext)
        if target is None:
            return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)
        context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm, ext=to_ext)
        engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
        known = load_page_body(wiki_dir, ref.subpath)
        # 書き換えの記録は直前の保存とまとめない（変換したことを1つの履歴として残し、
        # 履歴から変換前へ戻せるように）
        save_page(wiki_dir, config, ref.subpath, to_ext, save_time_replace(converted, pagepath),
                  engine=engine, path=target, known=ref.body if known is None else known,
                  merge=False)
        old = page_file_path(wiki_dir, ref.subpath, ref.ext)
        if old and old != target and os.path.isfile(old):
            os.remove(old)
        remove_temps(wiki_dir, ref.subpath)
        # 変換したのは書きかけを含む本文なので、書きかけは役目を終える
        delete_draft(wiki_dir, ref.subpath)
        return back("{}に変換して保存しました（{}）。".format(
            MARKUP_FORMATS[to_name]["label"], time.strftime("%H:%M:%S")))

    # ---- 表記ボタンから: 変換して管理ページを出す ----
    source, refused, _status = posted_source(wiki_dir, ref.subpath, ref.body)
    if refused:
        return back(refused)
    sent_origin = request.forms.getunicode("origin", "")
    if sent_origin and sent_origin != source_hash(ref.body) and source != ref.body:
        # 編集しているあいだに、ほかの場所でページが保存されている（保存すれば
        # 競合の画面になる状態）。変換すると相手の変更を黙って捨てることになる
        return back("編集しているあいだに、ほかの場所でページが更新されています。"
                    "先に保存して、競合を片付けてから変換してください。")
    if not source.strip():
        return back("本文が空なので、変換できません。")
    options = markupconv.build_options(wiki_dir, config, pagepath)
    result = _DIRECTIONS[markup_name_for(ref.ext)][1](source, options)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(result.text)
    return _page(wiki_dir, config, farm, explicit_farm, pagepath, ref, source, result,
                 to_ext, base=source_hash(ref.body))


def _page(wiki_dir, config, farm, explicit_farm, pagepath, ref, source, result, to_ext, base):
    """管理ページ全体。元と変換後をタブで切り替え、それぞれコードとプレビューを並べる。"""
    from wikilib.pagetree import TOP_PAGE_LABEL
    from wikilib.solvedup import render_previews

    base_url = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm).base_url
    from_fmt, to_fmt = markup_format_for(ref.ext), markup_format_for(to_ext)
    files = [
        {"key": "from", "ext": ref.ext, "body": source},
        {"key": "to", "ext": to_ext, "body": result.text},
    ]
    htmls, styles, scripts, _auth = render_previews(
        wiki_dir, config, farm, explicit_farm, pagepath, ref.subpath, files)

    def tab(key, fmt, note, selected):
        return ('<button type="button" class="edit-tab" role="tab" data-tab="{k}" '
                'id="mc-tab-{k}" aria-controls="mc-panel-{k}" aria-selected="{s}">'
                '<span class="mc-tab-note mc-tab-note-{k}">{note}</span>'
                '{label} <code class="edit-markup-badge-ext">{ext}</code></button>').format(
            k=key, s="true" if selected else "false", label=escape(fmt["label"]),
            ext=escape(fmt["ext"]), note=escape(note))

    def panel(key, body, selected):
        return ('<section class="mc-panel" role="tabpanel" data-tab="{k}" id="mc-panel-{k}" '
                'aria-labelledby="mc-tab-{k}"{h}><div class="mc-panes">'
                '<textarea class="mc-code" readonly spellcheck="false" '
                'aria-label="コード">{src}</textarea>'
                '<div class="mc-preview content">{html}</div></div></section>').format(
            k=key, h="" if selected else " hidden", src=escape(body), html=htmls[key])

    if result.warnings:
        warn = ('<details class="mc-warnings" open><summary>変換で失われるもの・確かめてほしいもの'
                '（{}件）</summary><ul>{}</ul></details>').format(
            len(result.warnings), "".join("<li>{}</li>".format(escape(w)) for w in result.warnings))
    else:
        warn = '<p class="mc-lead">変換で失われるものはありません。</p>'

    old_name = os.path.basename(ref.subpath) + ref.ext
    new_name = os.path.basename(ref.subpath) + to_ext
    lead = ('<p class="mc-lead">{f}を{t}に変換したものです。［確定］すると、このページを'
            '<code>{n}</code> として保存し直し、<code>{o}</code> は無くなります'
            '（変換前の内容は、ページの履歴から戻せます）。</p>').format(
        f=escape(from_fmt["label"]), t=escape(to_fmt["label"]),
        n=escape(new_name), o=escape(old_name))
    confirm = "{} を {} に置き換えます。よろしいですか？".format(old_name, new_name)
    form = (
        '<form class="mc-actions" method="post" action="{action}">'
        '<input type="hidden" name="cmd" value="convert">'
        '<input type="hidden" name="base" value="{base}">'
        '<input type="hidden" name="conv" value="{conv}">'
        '<button type="submit" name="step" value="apply" class="edit-save" '
        'data-confirm="{confirm}" title="変換後の内容で、このページを保存し直します">確定</button>'
        '<button type="submit" name="step" value="cancel" class="edit-pause" '
        'title="変換したものを捨てて、編集画面へ戻ります（Esc でも）">'
        'やめる<span class="edit-key">(ESC)</span></button>'
        "</form>").format(
        action=escape(_edit_url(base_url, pagepath)), base=escape(base),
        conv=escape(_hash(result.text)), confirm=escape(confirm))

    body = (
        '<div class="edit-shell mc-shell">'
        '<div class="edit-tabs" role="tablist" aria-label="表記の変換">{t1}{t2}</div>'
        '{lead}{warn}{p1}{p2}{form}</div>').format(
        t1=tab("from", from_fmt, "変換前", False), t2=tab("to", to_fmt, "変換後", True),
        lead=lead, warn=warn, p1=panel("from", source, False), p2=panel("to", result.text, True),
        form=form)

    theme_conf = config.get("theme") or {}
    editor_url = base_url + "/" + EDITOR_URLPATH
    head_assets = "".join('<link rel="stylesheet" href="{}">\n'.format(escape(u)) for u in styles)
    head_assets += "".join('<script src="{}" defer></script>\n'.format(escape(u)) for u in scripts)
    page = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>表記の変換: {label}</title>
{assets}<link rel="stylesheet" href="{theme}">
<link rel="stylesheet" href="{editor}.css">
</head>
<body class="edit-body mc-body">
<header class="edit-head">
  <a class="edit-home" href="{home}">{site}</a>
  <span class="edit-kind">表記の変換</span>
  <span class="edit-target">{label}</span>
</header>
<main class="mc-main">{body}</main>
<script>{script}</script>
</body>
</html>
""".format(
        label=escape(pagepath or TOP_PAGE_LABEL), assets=head_assets,
        theme=escape("{}/{}/{}.css".format(base_url, THEME_URLPATH,
                                           theme_conf.get("name", DEFAULT_THEMEFILE))),
        editor=escape(editor_url), home=escape(base_url + "/"),
        site=escape(theme_conf.get("site_title", "wikiSystem")), body=body, script=_SCRIPT)
    return HTTPResponse(body=page, status=200, content_type="text/html; charset=utf-8")


# タブの切り替えと、［確定］の確かめ。編集画面の editor.js は読み込まない
# （本文の入力・一時保存などの仕組みは、この画面には無いため）
_SCRIPT = r"""
(function () {
  var tabs = document.querySelectorAll(".mc-shell .edit-tab");
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      tabs.forEach(function (t) { t.setAttribute("aria-selected", t === tab ? "true" : "false"); });
      document.querySelectorAll(".mc-panel").forEach(function (p) {
        p.hidden = p.dataset.tab !== tab.dataset.tab;
      });
    });
  });
  var form = document.querySelector(".mc-actions");
  if (form) form.addEventListener("submit", function (event) {
    var b = event.submitter;
    if (b && b.dataset.confirm && !window.confirm(b.dataset.confirm)) event.preventDefault();
  });
  // Esc で［やめる］（編集画面の一時中断と同じキー）。開いているダイアログや、
  // 先に Esc を受けたもの（preventDefault 済み）があれば、そちらに任せる
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || event.defaultPrevented || event.isComposing) return;
    if (document.querySelector("dialog[open]")) return;
    var cancel = document.querySelector('.mc-actions button[value="cancel"]');
    if (cancel) cancel.click();
  });
})();
"""
