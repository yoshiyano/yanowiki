"""Wikiの設定を画面から書き換える（/.admin/configwiki）。**管理者と助手**。

書き換えるのは `wikidata/<Wiki名>/config/default.yaml` ——**そのWikiぶんだけ**。
共通の設定（`config/default.example.yaml`）は触らない。

## 項目はタブで分ける・直したその場で保存する

**「保存する」のボタンは持たない**（Wiki設計者の指示、2026-09-18）。入力欄を
直した時点で、その項目1つだけを窓口（`/.admin/configwiki/api`）へ送って
書き込む。項目の数が多いので**タブで切り替える**のも同じ指示による。

このやりかたは`/.groups`・`/.admin/privileges`と同じ形に揃えてある
（タブの作りは`_sys/groups/groups.js`、JSONの窓口は`wikilib.groupsui`）。

**印（このWikiで指定する）の付け外しも、その場で書き込む。** 外すとその項目は
ファイルから消え、入力欄には共通の設定の値が戻る——「いま何が効いているか」と
画面が食い違わないようにするため。

送るのは**直した項目1つだけ**で、画面にある値をまとめて送り直すことはしない。
まとめて送ると、別のタブを開いたまま画面を放っておいた人の古い値で、他の人の
書き換えを上書きしてしまう。

## 取り返しが付かない項目は、警告を読んで「理解して編集」を入れたときだけ書ける

項目に `guard`（警告の文言）を持たせると、その項目は**警告と「理解して編集」のチェックが
付き、チェックを入れるまで印も入力欄も触れない**（Wiki設計者の指示、2026-09-21。
いまは `account.pw_salt` だけ——変えると全アカウントのパスワードが通らなくなる）。
チェックは画面だけの状態で、保存はしない。**窓口も、確認済みの印（`ack`）が無い書き込みは
断る**（画面を通らずに窓口を直接叩いても、うっかりでは書けない）。

## 「このWikiで指定する」に印を付けたものだけ書く

設定は、共通の値の上にそのWikiの値を重ねて決まる（`wikilib.wikiconfig`）。
**書かれていない項目は共通の値がそのまま効く**ので、この画面でも
「指定する」に印を付けた項目だけを書き出す。

全部を書き出さないのは、そうすると**共通の設定をあとから直しても、この
Wikiには届かなくなる**ため。かつて新規Wikiを作るときに全部を複製していて、
同じことが起きている（`wikiconfig.load_config` の断りを参照）。

## 保存すると失われるもの、残るもの

**コメントは残らない**（Wiki設計者の指示、2026-09-06）。書き出すのは目印の1行と、
コメントの無いYAMLだけ。

**この画面が知らない項目は残す。** 手で書き足した設定を、画面を開いて
保存しただけで消してしまわないため。**書き込むたびにファイルを読み直して**、
そこへ直された項目1つを重ねている。

人が直したファイルは、書き換える前に `default.yaml.YYMMDD_HHMMSS` として
控える（10世代まで。`wikilib.wikiconfig.backup_config`）。**この画面が
書いたままのファイルは控えない**——同じ内容が並ぶだけで、失うものが無い。

## 定義ルールのタブ

`COLOR(red){…}`・`&smile;` などの置き換えルール（`pukiwiki.extrarules.yaml`）は、
`default.yaml` とは**別のファイル**で、配列でしか書けないため、項目1つずつの
仕組みには載らない。専用のタブとして `wikilib.extrarulesui` が受け持つ
（行ごとの編集・追加・削除・並べ替えと、試験欄）。

## Wiki名だけは、その場では変えない

「Wiki名」のタブ（`wikilib.farmrename`）だけは即時保存から外してあり、
**いまの名前を書き写してもらってからボタンで実行する**。他の項目と違い、
これは設定ファイルへの書き込みではなく**フォルダの移動でURLが変わる操作**で、
入力の途中の値で走らせるわけにいかないため。**この一点はWiki設計者の
「保存ボタンは使わない」という指示から外れる**が、外す側に理由がある
と考えている（名前を打ちかけの `s` で実行されては困る）。

権限は画面と同じ（管理者と助手）にしてある。Wikiを増やす・消す
（`/.newwiki`・`/.delwiki`）は既定Wikiの管理者と助手に絞ってあるが、
名前を変えるのは**そのWikiの中で閉じた話**で、しかも名前を戻せば元に戻る。
消すこと（取り返しが付かない）と同じ関門にする理由は無いと考えた。
"""
import contextlib
import os
from html import escape

from bottle import request

from wikilib import auth, extrarulesui, farmrename, stafflog, sysui
from wikilib.paths import (
    BASE_DIR, CONFIGUI_DIR, CONFIGWIKI_URLPATH, farm_config_path, farm_wiki_dir,
)
from wikilib.themes import make_plugin_context
from wikilib.web import serve_asset
from wikilib.wikiconfig import (
    account_pw_salt, config_backups, load_config, merge_config, read_yaml,
    save_farm_config, written_by_system,
)

# この画面が自前で持つ資材（`/.admin/configwiki.css` `.js`）と、JSが叩く窓口。
CONFIGWIKI_CSS = f"{CONFIGWIKI_URLPATH}.css"
CONFIGWIKI_JS = f"{CONFIGWIKI_URLPATH}.js"
CONFIGWIKI_API = f"{CONFIGWIKI_URLPATH}/api"

# Wiki名のタブ。設定ファイルの項目ではないので、SECTIONS とは別に持つ
WIKINAME_TAB = "wikiname"

# PukiWiki記法の定義ルールのタブ。`default.yaml` の項目ではなく別のファイル
# （`pukiwiki.extrarules.yaml`）を書くので、これも SECTIONS とは別に持つ
# （`wikilib.extrarulesui`）。窓口の操作名は `rx_` で始まる。
EXTRARULES_TAB = "extrarules"
EXTRARULES_OP_PREFIX = "rx_"

# 画面に出す項目。ここに無い項目は画面に出ないが、消えもしない
# （モジュール冒頭参照）。説明は config/default.example.yaml の注記と
# 同じことを、画面で読める長さに詰めたもの。
#
# **help はHTMLとしてそのまま出す**（エスケープしない）。強調は <strong>、
# 記号は &amp; &lt; と書くこと——Markdownは通らないので "**…**" と書いても
# 星がそのまま出る（2026-09-06にWiki設計者から指摘。実際にそうなっていた）。
SECTIONS = [
    ("edit", "編集", [
        {"path": "edit.defaultwiki", "label": "新しいページの記法",
         "type": "choice",
         "choices": [("pukiwiki", "PukiWiki記法（.txt）"),
                     ("markdown", "Markdown（.md）")],
         "help": "新しく作るページをどちらで書き始めるか。すでにあるページの"
                 "記法は拡張子で決まっているので関係しません。編集画面の"
                 "ツールバー右端から選び直せます（保存先の拡張子も変わります）。"},
        {"path": "edit.title_length", "label": "一覧のタイトルの幅",
         "type": "int",
         "help": "編集画面のサイドバーのページ一覧で、長いタイトルをどこで"
                 "打ち切るか。全角は2文字ぶんとして数えます（半角換算）。"},
        {"path": "edit.custom_colors", "label": "このWiki固有の色",
         "type": "lines",
         "help": "ツールバーの「文字色」「背景色」に、標準の16色に加えて出す色"
                 "（#rrggbb を1行に1つ、16個）。PukiWiki記法の "
                 "&amp;color(fg=/bg=){…}; にそのまま渡ります。"},
    ]),
    ("account", "アカウント", [
        {"path": "account.policy", "label": "ユーザ登録の受け入れかた",
         "type": "choice",
         "choices": [("open", "誰でも自由に作れる（既定）"),
                     ("approval", "誰でも申請できるが、承認されるまで使えない")],
         "help": "ログイン画面の「アカウント作成」の受け入れかたです。"
                 "<strong>決めるのは登録だけ</strong>で、誰が何を読めて書けるかは"
                 "アクセス制限（/.admin/privileges）が決めます。ログインは「誰が"
                 "編集したか」を記録するための仕組みで、編集を制限する関門では"
                 "ありません。<br>"
                 "<strong>承認制</strong>にすると、申請されたアカウントは承認待ちで"
                 "始まり、管理者か助手が「アカウントの承認」（/.admin/approvals）で"
                 "承認するまでログインできません（権限の上でも未ログインと同じ扱いです）。"
                 "意味は解説ページ（/Tech/Accounts/Policy）の「ユーザ登録の受け入れかた」"
                 "にあります。"},
        {"path": "account.pw_salt", "label": "パスワードの塩", "type": "text",
         "guard": "<strong>この値を変えると、このWikiの全アカウントのパスワードが通らなく"
                  "なります。</strong>パスワードのハッシュには、この塩とIDが混ざります。"
                  "生のパスワードは保存していないので、<strong>作り直せません</strong>"
                  "（全員がパスワードを付け直すことになります）。"
                  "変えるなら、変える前の値を控えてください——元の値に戻せば、また通ります。"
                  "<strong>Wiki名を変えるときは、旧名がここへ自動で書かれます</strong>"
                  "（手で書く必要はふつうありません）。",
         "help": "パスワードのハッシュに混ぜる塩です。<strong>空のままなら Wiki名</strong>"
                 "（既定）。別のWikiで同じID・同じパスワードでも、ハッシュが違うように"
                 "するためのものです。塩は秘密ではありません。"},
    ]),
    ("attach", "添付ファイル", [
        {"path": "attach.max_size", "label": "1つあたりの上限",
         "type": "text",
         "help": "「20MB」のような書きかたのほか、単位なしの数（byte）でも"
                 "指定できます。読めない書きかたのときは 20MB として扱います。"},
    ]),
    ("plugin", "プラグイン", [
        {"path": "plugin.debug", "label": "使いかたを画面に出す",
         "type": "bool",
         "help": "プラグインが動かなかったとき、そのプラグインの使いかた"
                 "（_help やモジュールの説明）を折りたたみで添えます。"
                 "server.yaml の debug（実装を追う開発者向け）とは別で、"
                 "こちらは「どう書けば動くか」を示す使い手向けです。"},
    ]),
    ("markdown", "Markdown", [
        {"path": "markdown.preset", "label": "プリセット", "type": "text",
         "help": "markdown-it-py のプリセット名（既定の gfm-like は "
                 "GitHub Flavored Markdown 相当）。"},
        {"path": "markdown.linkify", "label": "裸のURLをリンクにする",
         "type": "bool",
         "help": "本文にそのまま書かれた http://… を自動でリンクにします。"},
        {"path": "markdown.linkify_fuzzy", "label": "http:// の無い語もリンクにする",
         "type": "bool",
         "help": "「CLAUDE.md」のような語まで、ドメインらしければリンクにします。"
                 "誤ってリンクになるときは「いいえ」に。"
                 "本物のURLはこの設定に関わらずリンクになります。"},
        {"path": "markdown.allow_html", "label": "生HTMLを通すか",
         "type": "html",
         "help": "本文に書かれたHTMLをどこまで通すか。<strong>通さない</strong>"
                 "が既定です。"
                 "「一部だけ」は script・style・iframe・form・on* 属性・"
                 "javascript: などを文字に落とします。"
                 "「すべて」は編集できる人を全面的に信頼できる場合だけ。"},
        {"path": "markdown.anchors", "label": "見出しにidを振る", "type": "bool",
         "help": "<strong>切ると様々な機能で不具合が出るため、「はい」を"
                 "推奨します。</strong> 目次のリンク先・セクション編集の宛先・"
                 "ページ内アンカー（<code>#見出し</code>）・差分画面の"
                 "見出しジャンプが、すべてこのidを使っています。"
                 "「いいえ」にすると、Markdownのページでこれらが黙って"
                 "効かなくなります（画面には何も出ません）。"},
        {"path": "markdown.toc_depth", "label": "目次に出す深さ", "type": "int",
         "help": "サイドバーの目次に h1〜hN のどこまで出すか。表示の都合だけの"
                 "設定で、idは常に h1〜h6 すべてに振られます。"},
        {"path": "markdown.first_h1_as_title", "label": "1行目のh1を題名にする",
         "type": "bool",
         "help": "1行目が h1 ならページの題名として扱い、本文と目次から"
                 "取り除きます。2つ目以降の h1 は章見出しのままです。"},
    ]),
    ("pukiwiki", "PukiWiki記法", [
        {"path": "pukiwiki.allow_html", "label": "生HTMLを通すか", "type": "html",
         "help": "値の意味は Markdown 側と同じ。本家PukiWikiもHTMLは書けない"
                 "決まりなので、既定を緩める理由は薄いところです。"},
        {"path": "pukiwiki.facemark", "label": "フェイスマークを使う",
         "type": "bool",
         "help": "config/pukiwiki.extrarules.yaml の facemark_rules を使うか"
                 "（本家の $usefacemark）。ユーザ定義ルール（line_rules）は"
                 "この設定と関係なく常に有効です。"},
        {"path": "pukiwiki.wikiname", "label": "WikiName を自動リンクにする",
         "type": "bool",
         "help": "「PukiWiki」のように大文字始まりの語が2つ以上続くものを、"
                 "そのページへのリンクにします（本家の $nowikiname の逆）。"},
    ]),
    ("theme", "テーマと画面", [
        {"path": "theme.name", "label": "テーマ", "type": "text",
         "help": "theme/&lt;名前&gt;.html（＋.css/.js）を使います。"
                 "theme/&lt;名前&gt;/ というフォルダがあれば、そちらが"
                 "そのテーマ専用の置き場所になります。"},
        {"path": "theme.site_title", "label": "サイト名", "type": "text",
         "help": "ヘッダに出る名前です。"},
        {"path": "theme.show_index", "label": "一覧に index を出す", "type": "bool",
         "help": "index はファイルの置き場所を決めるための名前で、使う人から見れば"
                 "フォルダそのものです。既定では出さず、フォルダの行がその入口を"
                 "兼ねます。"},
        {"path": "theme.selector", "label": "テーマを選ぶセレクタを出す",
         "type": "bool",
         "help": "サイドバー上段の先頭に差し込まれます。主に<strong>作る人が"
                 "実際の画面で見比べるための道具</strong>です。"
                 "選んだテーマはcookieに1日"
                 "おぼえ、そのWikiの中だけで効きます（上のテーマより優先）。"},
        {"path": "theme.menu1_page", "label": "サイドバー上段のページ", "type": "text",
         "help": "そのページが無ければ、その枠は出ません。"},
        {"path": "theme.menu2_page", "label": "サイドバー下段のページ", "type": "text",
         "help": "そのページが無ければ、その枠は出ません。"},
        {"path": "theme.menu1_mode", "label": "上段を開いたままにするページ",
         "type": "lines",
         "help": "狭い画面では、サイドバー上段はふつう<strong>帯にたたまれ、"
                 "押すと開く</strong>形になります。ここに書いたページを"
                 "見ているあいだは、たたまずに開いたままにします。<br>"
                 "書きかたは <code>ページ名,fix</code> を1行に1つ"
                 "（例: <code>FrontPage,fix</code>）。"
                 "<strong>そのページを見ているとき</strong>の話であって、"
                 "サイドバーに出す中身の指定ではありません（中身は上の"
                 "「サイドバー上段のページ」）。"
                 "書かなければ、どのページでもたたまれます。"},
        {"path": "theme.menu2_mode", "label": "下段を開いたままにするページ",
         "type": "lines",
         "help": "書きかたは上段と同じ（<code>ページ名,fix</code> を1行に1つ）。"
                 "こちらはサイドバー下段にかかります。"},
    ]),
]

# 生HTMLの扱いは true / false / all の3択。YAMLでは前2つが真偽値、
# 最後だけ文字列という混ざりかたなので、画面の値との行き来をここに閉じる
HTML_CHOICES = [("false", "通さない（既定）"), ("true", "一部だけ通す"),
                ("all", "すべて通す")]


def fields_by_path():
    """`"edit.title_length"` から項目の定義を引く表。

    窓口（API）は**項目の名前だけを受け取る**ので、画面を組み立てずに
    定義を引けるようにしておく。"""
    return {f["path"]: f for _key, _title, fields in SECTIONS for f in fields}


def shown_path(path):
    """画面に出す置き場所。**wikidata/ から書く**（Wiki設計者の指示、2026-09-06）。

    絶対パスをそのまま出すと、どこに置いてあるかがそのまま外に出るうえ、
    長くて読みにくい。この設置の中のものは、設置場所からの相対で書く。"""
    try:
        inside = os.path.relpath(path, BASE_DIR)
    except ValueError:      # 別のドライブなど、相対にできないとき
        return path
    return path if inside.startswith("..") else inside


def _walk(data, path):
    """"a.b.c" をたどる。(見つかったか, 値) を返す。"""
    node = data
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return False, None
        node = node[key]
    return True, node


def _put(data, path, value):
    keys = path.split(".")
    node = data
    for key in keys[:-1]:
        if not isinstance(node.get(key), dict):
            node[key] = {}
        node = node[key]
    node[keys[-1]] = value


def _drop(data, path):
    """その項目を消す。空になった入れ物も片付ける。"""
    keys = path.split(".")
    stack, node = [], data
    for key in keys[:-1]:
        if not isinstance(node, dict) or key not in node:
            return
        stack.append((node, key))
        node = node[key]
    if isinstance(node, dict):
        node.pop(keys[-1], None)
    for parent, key in reversed(stack):
        if isinstance(parent.get(key), dict) and not parent[key]:
            del parent[key]


def _to_text(field, value):
    """設定の値を、入力欄に出す文字列にする。"""
    if value is None:
        return ""
    if field["type"] == "lines":
        return "\n".join(str(v) for v in value) if isinstance(value, list) else str(value)
    if field["type"] == "bool":
        return "true" if value else "false"
    if field["type"] == "html":
        return "all" if value == "all" else ("true" if value is True else "false")
    return str(value)


def _from_text(field, text):
    """入力欄の文字列を設定の値にする。(値, 断りの文言) を返す。"""
    text = (text or "").strip()
    kind = field["type"]
    if kind == "int":
        try:
            return int(text), ""
        except ValueError:
            return None, f"「{field['label']}」には数を入れてください。"
    if kind == "bool":
        return text == "true", ""
    if kind == "html":
        return ("all" if text == "all" else text == "true"), ""
    if kind == "lines":
        return [line.strip() for line in (text or "").splitlines() if line.strip()], ""
    if kind == "choice":
        allowed = [v for v, _label in field["choices"]]
        if text not in allowed:
            return None, f"「{field['label']}」に知らない値が来ました。"
        return text, ""
    return text, ""


GUARD_REFUSED = ("この項目は取り返しが付かないので、警告を読んで「理解して編集」に"
                 "チェックを入れたときだけ書き換えられます。")


def apply_change(wiki_dir, path, use, text, ack=False):
    """項目1つを書き込む。`(成否, 文言, 入力欄に戻す文字列)` を返す。

    **いま書かれている内容から始める。** この画面が知らない項目を、直した
    拍子に消してしまわないため（モジュール冒頭参照）。

    印を外したとき（`use` が偽）は、その項目を消したうえで**共通の設定の値**を
    返す——入力欄に出しておく値は「いま効いているもの」なので。"""
    field = fields_by_path().get(path)
    if field is None:
        return False, "知らない項目です。", None
    if field.get("guard") and not ack:
        # 警告を読んで確かめた印（`ack`）が無いものは書かない（モジュール冒頭）
        return False, GUARD_REFUSED, None
    data = read_yaml(farm_config_path(wiki_dir))
    value = None
    if use:
        value, problem = _from_text(field, text)
        if problem:
            return False, problem, None
        _put(data, path, value)
    else:
        _drop(data, path)
    ok, _saved, message = save_farm_config(wiki_dir, data)
    if not ok:
        return False, message, None
    if not use:
        _found, value = _walk(load_config(), path)
    return True, message, _to_text(field, value)


def render_configwiki(wiki_dir, config, farm, explicit_farm):
    """Wikiの設定を書き換える画面。**管理者と助手が開ける**（Wiki設計者の指示、
    2026-09-08）。ここから管理者になれるわけではないので、「管理者だけ」
    には入れていない（`wikilib.accounts` の冒頭の表）。

    書き込みは受け取らない（窓口は `render_configwiki_api`）。"""
    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           CONFIGWIKI_URLPATH, auth.STAFF)
    if denied is not None:
        return denied
    base_url = _base_url(config, farm, wiki_dir, explicit_farm)
    path = farm_config_path(wiki_dir)
    body = _screen_html(load_config(), read_yaml(path), path, farm, base_url,
                        _opening_tab(), wiki_dir)
    return sysui.page(wiki_dir, config, farm, explicit_farm, CONFIGWIKI_URLPATH,
                      "Wikiの設定", body, css_url=CONFIGWIKI_CSS)


def render_configwiki_api(wiki_dir, config, farm, explicit_farm):
    """直した項目1つを受け取る窓口（`/.admin/configwiki/api`）。

    **断りもJSONで返す**（画面のHTMLを返さない）。読むのは画面のJSなので、
    403で戻されたときも文言をその場に出せるようにしておく。"""
    if not auth.allows(wiki_dir, farm, auth.STAFF):
        return sysui.json_out({"ok": False, "message": "この画面を使う権限がありません。"},
                              status=403)
    body = sysui.json_body()
    op = body.get("op") or "set"
    if op == "rename":
        return _rename(wiki_dir, config, farm, explicit_farm, body)
    if op.startswith(EXTRARULES_OP_PREFIX):
        with _staff_file(wiki_dir, farm, extrarulesui.own_path(wiki_dir), "定義ルール"):
            return _extrarules(wiki_dir, config, farm, explicit_farm, op, body)
    if op != "set":
        return sysui.json_out({"ok": False, "message": "知らない操作です。"}, status=400)

    path = body.get("path") or ""
    use = bool(body.get("use"))
    with _staff_file(wiki_dir, farm, farm_config_path(wiki_dir), path):
        ok, message, text = apply_change(wiki_dir, path, use, body.get("value") or "",
                                         ack=bool(body.get("ack")))
    if not ok:
        return sysui.json_out({"ok": False, "message": message}, status=400)
    config_path = farm_config_path(wiki_dir)
    return sysui.json_out({
        "ok": True, "message": message, "value": text, "own": use,
        # 状態の1行と控えの一覧は**書くたびに変わる**（初回は控えを取り、
        # 以後は取らない）。組み立ては画面と同じ関数に任せ、文言を1か所に保つ
        "state": _state_html(config_path),
        "backups": _backups_html(config_path),
    })


@contextlib.contextmanager
def _staff_file(wiki_dir, farm, file_path, what):
    """助手の操作なら、設定ファイルの中身を前後で控えて記録する（wikilib.stafflog）。
    中身が変わらなかった（断られた・同じ値）ときは記録しない。"""
    staff = stafflog.actor(wiki_dir, farm)
    before = stafflog.read_text(file_path) if staff is not None else None
    yield
    if staff is None:
        return
    after = stafflog.read_text(file_path)
    if after != before:
        target = os.path.relpath(file_path, os.path.dirname(wiki_dir)).replace(os.sep, "/")
        stafflog.record(wiki_dir, staff, "config.file", target, f"「{what}」を変えた",
                        before={"text": before}, after={"text": after})


def _extrarules(wiki_dir, config, farm, explicit_farm, op, body):
    """定義ルールの窓口（`op=rx_…`）。組み立ては `wikilib.extrarulesui`。

    書き込んだ操作には、**作り直した一覧（`body`）を添えて返す**。行の追加・
    削除・並べ替えのあとは番号が変わるため、画面がその部分を差し替える。"""
    name = op[len(EXTRARULES_OP_PREFIX):]
    if name == "test":
        out = extrarulesui.run_test(wiki_dir, config, farm, explicit_farm, body)
        return sysui.json_out(out, status=200 if out["ok"] else 400)
    ok, message = extrarulesui.apply_op(wiki_dir, dict(body, op=name))
    if not ok:
        return sysui.json_out({"ok": False, "message": message}, status=400)
    return sysui.json_out({"ok": True, "message": message,
                           "body": extrarulesui.body_html(wiki_dir)})


def _rename(wiki_dir, config, farm, explicit_farm, body):
    """Wiki名を変える（`op=rename`）。`wikilib.farmrename` の窓口。

    **移す前にいまの相手を控えておき、移したあとで新しいURLにcookieを置き直す。**
    ログイン状態のcookieはWikiごとのPathに置かれ、合言葉にもWiki名が混ざる
    （`auth.remember_login` / `auth.session_token`）ので、何もしないと
    名前を変えた本人が、その場で入り直しになる。"""
    new = (body.get("name") or "").strip()
    confirm = (body.get("confirm") or "").strip()
    if confirm != farm:
        return sysui.json_out(
            {"ok": False,
             "message": f"確かめの欄に、いまの名前（{farm}）をそのまま書き写してください。"},
            status=400)
    user = auth.current_user(wiki_dir, farm)
    staff = stafflog.actor(wiki_dir, farm)
    ok, message, new_default = farmrename.rename_farm(farm, new, config)
    if not ok:
        return sysui.json_out({"ok": False, "message": message}, status=400)
    if staff is not None:
        # 記録は移った先のWikiに残す（記録の置き場所もWikiと一緒に動く）
        stafflog.record(farm_wiki_dir(new), staff, "farm.rename", new,
                        f"{farm} → {new}", before={"name": farm}, after={"name": new})

    # 付け替えたばかりの既定Wiki名は、手元の config にはまだ入っていない。
    # 新しいURLを組み立てるのに要るので、この応答のあいだだけ重ねておく
    after = _config_with_default(config, new_default) if new_default else config
    new_dir = farm_wiki_dir(new)
    new_base = _base_url(after, new, new_dir, explicit_farm)
    out = sysui.json_out({"ok": True, "message": message,
                          "url": f"{new_base}/{CONFIGWIKI_URLPATH}?tab={WIKINAME_TAB}"})
    # 古い名前のcookieは捨て、新しい名前で置き直す。**名前が衝突することは無い**
    # ——cookieの名前自体がWikiごとに分かれている（`paths.wiki_cookie_name`）
    auth.forget_login(out, config, farm, wiki_dir, explicit_farm)
    auth.remember_login(out, after, new, new_dir, explicit_farm, user)
    return out


def _config_with_default(config, name):
    """`farm.default` だけを差し替えた設定を返す（元は書き換えない）。"""
    copied = dict(config)
    copied["farm"] = dict(config.get("farm") or {})
    copied["farm"]["default"] = name
    return copied


def _base_url(config, farm, wiki_dir, explicit_farm):
    """このWikiの入口のURL。cookieのPathと戻り先の組み立てに使う。"""
    return make_plugin_context(config, farm, wiki_dir, "", explicit_farm).base_url


def _opening_tab():
    """最初に開くタブ。`?tab=` があればそれ、無ければ先頭。

    名前を変えたあとの戻り先で使う（`?tab=wikiname`）——変えた結果を、
    変えた画面のまま見せるため。"""
    asked = request.query.get("tab") or ""
    known = [key for key, _title, _fields in SECTIONS] + [EXTRARULES_TAB, WIKINAME_TAB]
    return asked if asked in known else known[0]


def _control_html(field, value, has_own):
    """入力欄1つぶん。印が付いていない項目は触れないようにしておく。"""
    path, kind = field["path"], field["type"]
    ident = "wcfg-" + path.replace(".", "-")
    disabled = "" if has_own else " disabled"
    text = _to_text(field, value)
    if kind in ("bool", "choice", "html"):
        choices = (field["choices"] if kind == "choice" else
                   HTML_CHOICES if kind == "html" else
                   [("true", "はい"), ("false", "いいえ")])
        options = "".join(
            f'<option value="{escape(v)}"'
            f'{" selected" if text == v else ""}>{escape(label)}</option>'
            for v, label in choices)
        return (f'<select id="{ident}" data-role="value"{disabled}>'
                f'{options}</select>')
    if kind == "lines":
        return (f'<textarea id="{ident}" data-role="value" rows="4"'
                f'{disabled}>{escape(text)}</textarea>')
    itype = "number" if kind == "int" else "text"
    return (f'<input id="{ident}" type="{itype}" data-role="value" '
            f'value="{escape(text)}" autocomplete="off"{disabled}>')


def _guard_html(field):
    """警告と「理解して編集」のチェック。`guard` の無い項目は空。"""
    if not field.get("guard"):
        return ""
    return f"""        <div class="wcfg-guard">
          <p class="wcfg-guard-warn">{field["guard"]}</p>
          <label class="wcfg-guard-ack"><input type="checkbox" data-role="guard">
            上の注意を理解したうえで編集する</label>
        </div>
"""


def _field_html(field, common, own, note=""):
    """項目1つ。名前（`data-path`）はJSが窓口へそのまま送る。

    `guard` のある項目は、**チェックを入れるまで印も入力欄も無効**で始める
    （モジュール冒頭）。`note` は、その場で計算した補足（例: いま効いている値）。"""
    path = field["path"]
    guarded = bool(field.get("guard"))
    has_own, own_value = _walk(own, path)
    _found, common_value = _walk(common, path)
    value = own_value if has_own else common_value
    ident = "wcfg-" + path.replace(".", "-")
    inherited = escape(_to_text(field, common_value)) or "（指定なし）"
    return f"""      <div class="wcfg-field{' is-own' if has_own else ''}{' wcfg-guarded' if guarded else ''}"
           data-path="{escape(path)}">
{_guard_html(field)}        <div class="wcfg-head">
          <label class="wcfg-use">
            <input type="checkbox" data-role="use"
                   {'checked' if has_own else ''}{' disabled' if guarded else ''}> このWikiで指定する</label>
          <label class="wcfg-label" for="{ident}">{escape(field["label"])}</label>
          <code class="wcfg-key">{escape(path)}</code>
          <span class="wcfg-said" data-role="said" role="status"></span>
        </div>
        <div class="wcfg-value">{_control_html(field, value, has_own and not guarded)}</div>
        <p class="wcfg-help">{field["help"]}</p>
        <p class="wcfg-common">共通の設定: <code>{inherited}</code></p>{note}
      </div>"""


def _tabs_html(opening):
    """タブの見出し。並びは SECTIONS の順で、Wiki名を最後に置く。

    Wiki名を最後にしてあるのは、**日々書き換える項目ではない**ため
    （URLが変わる操作なので、手前に置いて押し間違えたくない）。"""
    buttons = [(key, title) for key, title, _fields in SECTIONS]
    buttons.append((EXTRARULES_TAB, "定義ルール"))
    buttons.append((WIKINAME_TAB, "Wiki名"))
    return "".join(
        f'<button type="button" class="wcfg-tab-btn'
        f'{" wcfg-tab-active" if key == opening else ""}" data-tab="{escape(key)}"'
        f' role="tab" aria-selected="{"true" if key == opening else "false"}">'
        f'{escape(title)}</button>'
        for key, title in buttons)


def _panel_html(key, fields, common, own, opening, notes=None):
    notes = notes or {}
    body = "".join(_field_html(f, common, own, notes.get(f["path"], "")) for f in fields)
    hidden = "" if key == opening else " hidden"
    return (f'  <div class="wcfg-panel" data-panel="{escape(key)}"{hidden}>\n'
            f'{body}\n  </div>')


def _wikiname_panel_html(farm, opening):
    """Wiki名のタブ。**ここだけボタンで実行する**（モジュール冒頭参照）。"""
    hidden = "" if WIKINAME_TAB == opening else " hidden"
    blocked = farmrename.renamable(farm)
    if blocked:
        inside = f'<p class="wcfg-hint">{escape(blocked)}</p>'
    else:
        inside = f"""    <div class="wcfg-rename">
      <div class="wcfg-rename-row">
        <label for="wcfg-newname">新しい名前</label>
        <input id="wcfg-newname" type="text" autocomplete="off"
               placeholder="半角英数字と - _ 、先頭は英数字">
      </div>
      <div class="wcfg-rename-row">
        <label for="wcfg-confirm">確かめ</label>
        <input id="wcfg-confirm" type="text" autocomplete="off"
               placeholder="いまの名前（{escape(farm)}）を書き写してください">
      </div>
      <button type="button" class="wcfg-go" id="wcfg-rename-go">名前を変える</button>
      <p class="wcfg-said" id="wcfg-rename-said" role="status"></p>
    </div>"""
    return f"""  <div class="wcfg-panel" data-panel="{WIKINAME_TAB}"{hidden}>
    <p class="wcfg-lead">このWikiの名前は <code>{escape(farm)}</code> です。
      名前は置き場所（<code>wikidata/{escape(farm)}/</code>）であると同時に、
      <strong>URL（<code>/={escape(farm)}/</code>）そのもの</strong>です。</p>
    <p class="wcfg-hint">中身は1つも書き換えません（フォルダを移すだけです）。
      名前を戻せば元どおりになるので、控えは取りません。
      ただし<strong>URLが変わる</strong>ので、次のものは切れます。</p>
    <ul class="wcfg-hint">
      <li>外からのリンク・ブックマーク（<code>/={escape(farm)}/…</code> は無いページになります）</li>
      <li><strong>このWikiに入っている人のログイン状態</strong>（全員が入り直しです。
        変えたあなたは、そのまま続けられます）</li>
      <li>テーマを選ぶセレクタで選んでいたテーマ</li>
    </ul>
    <p class="wcfg-hint"><strong>パスワードは、そのまま通ります。</strong>
      パスワードのハッシュにはWiki名が混ざる（塩。<code>account.pw_salt</code>）ので、
      移す前にいまの名前を設定へ書き残します。</p>
    <p class="wcfg-hint">この項目だけは、書いたそばから保存しません。
      <strong>いまの名前を書き写してからボタンで実行します</strong>——
      打ちかけの名前で走らせるわけにいかないためです。</p>
{inside}
  </div>"""


def _screen_html(common, own, path, farm, base_url, opening, wiki_dir):
    # その場で計算する補足。**いま効いているパスワードの塩**（空のときは Wiki名）
    salt = account_pw_salt(merge_config(common, own), farm)
    notes = {"account.pw_salt": (
        f'\n        <p class="wcfg-common">いま効いている塩: <code>{escape(salt)}</code>'
        "（空のときは Wiki名）</p>")}
    panels = "\n".join(
        _panel_html(key, fields, common, own, opening, notes)
        for key, _title, fields in SECTIONS)
    return f"""<div class="wcfg" data-api="{escape(base_url)}/{CONFIGWIKI_API}">
  <p class="wcfg-lead">このWikiの設定（<code>{escape(shown_path(path))}</code>）を書き換えます。
    <strong>印を付けた項目だけ</strong>がこのファイルに書かれ、付けていない項目は
    共通の設定がそのまま効きます。
    <strong>直したその場で保存します</strong>（「保存する」のボタンはありません）。</p>
  <div class="wcfg-state" id="wcfg-state">{_state_html(path)}</div>
  <div class="wcfg-tabs" role="tablist">{_tabs_html(opening)}</div>
{panels}
{extrarulesui.panel_html(wiki_dir, opening, EXTRARULES_TAB)}
{_wikiname_panel_html(farm, opening)}
  <div class="wcfg-backups-box" id="wcfg-backups">{_backups_html(path)}</div>
</div>
<script src="{escape(base_url)}/{CONFIGWIKI_JS}" defer></script>
"""


def _state_html(path):
    if not os.path.isfile(path):
        return ('<p class="wcfg-hint">このWikiにはまだ設定ファイルがありません。'
                'どれかに印を付けると作られます。</p>')
    if written_by_system(path):
        return ('<p class="wcfg-hint">いまのファイルは、この画面が書いたままです。'
                '書き換えても控えは取りません（同じものが並ぶだけのため）。</p>')
    return ('<p class="wcfg-hint wcfg-hand">いまのファイルは<strong>手で直された'
            'もの</strong>です（1行目の目印と中身が合いません）。次に書き換えると、'
            '<strong>コメントは失われます</strong>——直前のものは控えに残ります。</p>')


def _backups_html(path):
    found = config_backups(path)
    if not found:
        return ""
    items = "".join(f"<li><code>{escape(os.path.basename(p))}</code></li>"
                    for p in found)
    return f"""  <details class="wcfg-backups">
    <summary>控え（新しい順、{len(found)}件）</summary>
    <ul>{items}</ul>
    <p class="wcfg-help">置き場所は設定ファイルと同じフォルダです。
      戻すときはファイルを置き換えてください（画面からは戻せません）。</p>
  </details>"""


def serve_configui_asset(name):
    """設定画面の資材（/.admin/configwiki.css・.js）。"""
    return serve_asset(CONFIGUI_DIR, "configui", name, kinds=("css", "js"))
