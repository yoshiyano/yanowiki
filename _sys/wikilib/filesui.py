"""ファイル一覧（`/.files/`）。webFileDir（別プロジェクト）を組み込み、Wikiのページを
エクスプローラーの形で見せる。

**変更は名前の変更・移動・コピー・削除と、フォルダ・ページの新規作成**（見るだけで始め
2026-09-28、2026-09-29 に足した。コピーは 2026-10-02）。ごみ箱は無い（プロバイダの
capabilities に無い）。

## 削除

削除は Wiki設計者の「削除もサポートしてください」（2026-09-29）で足した。

以下はクロコの実装例（設計者は未確認）:

- 中身は、編集画面で本文を空にして保存したときと同じ `editor.delete_page`。消す前の内容は
  「全文→空」の差分としてバックアップに残る。添付ファイルは `/trashbox` へ移す
  （`delete_page` の決まり。Wiki設計者が選んだ、2026-10-04。それまでは添付のあるページは
  消さずに断っていた）。フォルダを消したあとは、ページの無い下位フォルダに置いた添付も
  trashbox へ移す（持ち主の無い添付を残さない）
- Wiki にごみ箱に当たるものは無いので、webFileDir には `delete`（完全に削除）だけを宣言する
- **添付があれば、削除の前に［はい］［いいえ］で尋ねる**（Wiki設計者の指示、2026-10-06。
  文言も設計者のもの）。webFileDir 1.2.0 の `before_delete`（削除の前にプロバイダが問い返す）を
  使う。添付が無ければ webFileDir の既定の確認（完全に削除しますか？）のまま

    ページ     そのページだけを消す（配下のページは残る。編集画面と同じ）
    フォルダ   中のページすべて（入口を含む）を消す。先にすべてについて、編集の権限
               （W）があることを確かめ、1枚でも欠ければフォルダごと断る
               （途中まで消えて止まらないように）。深いページから順に消す
    (TopPage)  消せない

まとめて消すときは、移動と同じく webFileDir が1件ずつ行い、失敗したものだけが残る。

## 見出し連番

Wiki設計者の指示「winFD のサンプルに従って…見出し連番の機能を実装してください」（2026-10-02）。
webFileDir の見本 `numbering`（Wiki の =webfiledir/ServerSample/numbering）と同じ宣言・同じ
番号の付けかたで、独自のコマンド `page-numbering` として持つ（見本は「.」で始まる仮の名前を
使い、Wiki のページ名にできないので、見本のコマンドそのものは使わない）:
フォームで開始値を入れ、選んだページの名前の先頭に、送られた順（画面の今の並び順）で「番号.」を
付ける。桁数は開始値の桁数、元からある「数字.」は付け替える。選んでいない項目とぶつかる名前・
編集できないページは、その項目だけ付けない。

見本と違うところ（クロコの実装例）: 独自のコマンドは項目ごとの結果を返せないので、結果は知らせ
（Message）と読み直し（Reload）で返す。選んだもの同士で名前が入れ替わるものだけ仮の名前
（`numbering-…`。ページ名は「.」で始められない）を経る（名前の変更はリンクも直すので、
見本のように全部を仮の名前に通すと二度手間になる）。

## フォルダ化

Wiki設計者の指示「編集のファイル一覧で通常ページをフォルダ化するコマンドを右メニューに実装」
（2026-10-04）。ページ `X` を入口 `X/index` へ移してフォルダにする。中身は、編集画面で下位
ページを作るときの展開と同じ `pagemove.convert_page_to_folder`（本文・添付・変更の記録・
書きかけ・DB の実体パスを付け替える）。ページパスは `X` のままなので、URL・リンク・本文の
相対リンクの基準（`paths.resolve_link` はページパスから解く）は変わらない。

以下はクロコの実装例（設計者は未確認）:

- 独自のコマンド `page-to-folder`、表示は「フォルダ化」。ページ（ファイル）を右クリックした
  ときだけ出し、灰色にする条件は名前の変更と同じ「動かす」の権限（トップページは灰色）
- 複数を選べる。できないもの（編集の権限が無い・中断した操作と範囲が重なる）はその項目だけ
  飛ばし、結果は知らせ（Message）と読み直し（Reload）で返す（見出し連番と同じ形）
- 入口の本文はそのまま（新しいフォルダのように `#ls()` は足さない）
- フォルダになったあと下位ページを足さずにいても、ページに戻さない（戻すのは、下位ページを
  消して入口だけが残ったときの `editor.delete_page` だけ）

## コピー

Wiki設計者の指示「複製はやめて、コピー機能にしてください」（2026-10-02。webFileDir の見本の
「複製」の代わり）。capabilities に `copy` を持たせると、webFileDir の既定のコピー（Ctrl+C →
貼り付け・このフォルダに貼り付け、Ctrl を押しながらのドラッグ）が出る。名前の衝突（上書き・
スキップ・両方残す）も webFileDir が扱い、`copy` は `exists` を返すだけ。写す中身（アクセス制限・
添付・リンク）は `wikilib.pagecopy`。トップページは写さない（クロコの実装例）。

## 移動

名前の変更と同じ `pagerename.rename_page`（置き場所を変える `new_folder`）を呼ぶ。決まりも
名前の変更と同じ（下の「名前の変更」）。移動先の権限は見ない。

**まとめて動かすときは1件ずつ順に動かし、権限の無いものがあれば、それだけを失敗にする**
（Wiki設計者の「複数ファイルをまとめて移動にも対応。順次移動処理するだけ」「権限がないものが
あった場合、それだけ失敗にする」、2026-09-29）。1件ずつの処理と項目ごとの結果は webFileDir の
`ops.bulk` が行い、`move` は1件分だけを扱う。名前がぶつかったときの「飛ばす」「別名に
する」も webFileDir が扱う（`move` は `exists` を返すだけ）。

## 新規作成

Wikiのフォルダは下にページがあるときだけ存在する（一覧は DB のページから組み立てる）。
Wiki設計者の指示（2026-09-29）:

- 「フォルダ作成では index.md をあわせて作成して下さい」→ フォルダを作るときは入口の
  ページ（`X/index`）もあわせて作る
- 「index はデフォルトの wiki 形式に従った形式にして下さい」→ 入口の書きかたは Wikiの既定の
  書きかた（`edit.defaultwiki`）
- 「index のデフォルトとして #ls() を書き込んでおいて下さい」→ 入口の本文は `#ls()`
  （`NEW_FOLDER_BODY`）

以下はクロコの実装例（設計者は未確認）:

- ページ（ファイル）の書きかたも、入口と同じく Wikiの既定の書きかたにする（指示は入口についてだけ）
- 作るページの位置に編集の権限（W）が要る。同じ名前があれば `exists`
- ページ（ファイル）の本文は、見出しの無い一文（`NEW_PAGE_BODY`）。本文が空の保存は
  「ページを消す」の意味になるため。見出しが無いとタイトルはページ名になり、あとで名前を
  変えても表示が揃う（フォルダの入口の `#ls()` も同じ）
- webFileDir は新しいファイルに「新しいテキスト ドキュメント.txt」（番号付きも）を渡すが、
  添付ファイルの拡張子（`.txt` など）で終わる名前はページ名に使えない。この既定の名前のときだけ
  「新しいページ」（`NEW_PAGE_NAME`、ぶつかれば「新しいページ (2)」…）に置き換える
- 保存は `pagesave.save_page` を通す（差分がバックアップに残る）

## 名前の変更

`pagerename.rename_page` を呼ぶ。ページ・フォルダ（中のページごと）・添付・権限の記録が
一緒に動き、指していたリンクも直る。動くページすべてに編集の権限（W）が要り、1枚でも欠ければ断る
（`pagerename.unwritable_pages`）。フォルダを変えると、閲覧者に見えないページも中で一緒に
動くので、そういうページが混じっていても断る（どのページかは言わない。クロコの実装例）。

    ページ           そのページ（配下にページがあれば一緒に動く）
    フォルダ         入口（`X/index`）があればフォルダごと。入口の無い通り道の
                     フォルダも、中のページごと動かす
    (TopPage)        変えられない（Wikiの直下の入口。動かすとトップが無くなる）

マウントは書ける形（`rw`）にしてある。誰が何を変えられるかはページごとの権限で決まり、
プロバイダがそれを確かめる（webFileDir の API は項目の権限を見て断らないため）。

## 項目の権限（webFileDir の `Entry.auth`）

画面がボタン・メニューを灰色にするための値。Wiki の権限を次のように当てはめる
（クロコの案を設計者が承認、2026-09-29）。

    動かす   名前を変えられるとき 1（動くページすべてに W。`unwritable_pages` が空）。
             トップページ・一覧の根は 0
    読む・実行   1（見えないページは一覧に出さない）
    書く     1。Wiki の権限はページごとで配下に引き継がれず、フォルダの時点では
             「中に作れるか」が決まらないため。作るときに確かめる

一覧では、判定器（`pagelist.judge_for`）と DB のページの一覧を1回だけ用意して、
各行で使い回す（`_Lookup`）。

**画面は、持たない機能（コピー・ごみ箱）を出さない。** webFileDir 1.0 は、プロバイダの
capabilities に無い操作のコマンドを宣言しないので、画面にも出ず、直接呼んでも断る。
（0.2 系では、画面に機能の ON/OFF（`features`）を渡して止めていた。Wiki設計者が「get の
情報で停止は見苦しい」とクエリでない方法を求めた経緯がある、2026-09-29。1.0 では渡すもの
自体が無い。）画面（`/.files/`）は題名を Wiki の名前にするため wikiSystem が返す（`_screen_html`）。

**ページを参照できる**（独自のコマンド `page`・`dir-page`）。「開く」だけではフォルダに入るのか
ページを見るのか分からないので、ページを見る経路は「ページを参照」と呼ぶ（Wiki設計者の
「「開く」ではフォルダかページかわからないので、ファイルの「開く」も含め、「ページを参照」に
変更」、2026-09-29）。一覧を残すよう、どれも新しいタブで開く（クロコの実装例）。

    ファイル   ダブルクリック・Enter・右クリックの「ページを参照」（`page`、`open: default`）
    フォルダ   ダブルクリック・Enter は中に入る（webFileDir の画面の既定）。入口のページ
               （`X/index`）は Shift を押しながら、または右クリックの「ページを参照」
               （`dir-page`、`open: shift`）。入口の無い通り道のフォルダでは
               「ページがありません」と断る（宣言は種類ごとで、フォルダごとには出し分けられない）

フォルダのページを「Shift を押しながら開く処理、またはメニューから」開くのは
Wiki設計者の指示（2026-09-29）。Shift は webFileDir の既定のコマンド `tab`（新しいタブで開く）が
使うので、`tab` を止め（`disable_commands`）、Shift を使わない独自のコマンド `new-tab` として
作り直す。「隣の画面で開く」（`pane`）は既定のまま使う（ここはクロコの実装例）。

**ページを編集できる**（右クリックの「ページの編集」。Wiki設計者の「メニューに「ページの
編集」を追加」、2026-09-29）。フォルダでは入口のページ。編集画面は `POST cmd=edit` でしか
開かない（GET では閲覧だけ。wiki.py の注記）ので、結果の語彙 navigate を POST にして
（POST を使う案1は設計者が選んだ。2026-09-29）、ページの見出しの「編集」ボタンと同じ値を
新しいタブへ送る（独自のコマンド `edit`）。複数を選んでいるときは出ない（宣言の
`select: one`。設計者は「エラー表示が必要ない仕様なので非常に良い」とした）。
ホットキー（Alt+E）は、設計者の「ホットキー実装はなしでも構いません」を受けて付けていない。
以下はクロコの実装例: 編集の権限（W）が無ければ編集画面を開かずに断る。

## 見せかた

    フォルダ   Wikiのフォルダ。入口（`X/index`）があれば、そのページの属性をフォルダの
               行に載せる。入口そのものはファイルとしては出さない。ただしWikiの直下の
               入口（トップページ）は `(TopPage)` というファイルとして出す
    ファイル   ページ。名前は拡張子を付けない（ページの実体の拡張子 .md/.txt は見せず、
               名前がそのままURLの最後の要素になる）。書きかたは属性の列で見せる
    添付       項目としては出さず、ページの属性（添付の数）にだけ出す
    更新日時・サイズ   DB（pagedb）の値。本文のファイルの時刻を直接見ない。一覧の更新日時を
               ファイルの stat で出したところ、Wiki設計者が「ファイルから参照していますか？
               DBで完結するようにすべきです」とした（2026-09-29。更新日時についての指示）

**一覧は `pagelist.scandir` を通す。** 閲覧の権限（R 以上）が無いページは出さず、
見えるページの無いフォルダも出さない（読み手に見せる一覧は必ずここを通す決まり。
pagelist の冒頭）。

## 組み込みかた

webFileDir は bottle のアプリを作れるので、Wikiごとに1つ作って持ち、
`dispatch`（wiki.py）から `/=<Wiki>/.files/…` の要求をそのまま渡す。URLにWikiの名前が
入り、Wikiは後から増えるので、固定の接頭辞に `mount` する形は取らない。
渡しかたは bottle の `mount` と同じ（パスをずらして呼び、返りを HTTPResponse に詰める）。

## 止めて続きから（名前の変更・移動）

名前の変更・移動は、作業の手順のファイルに沿って行い（`wikilib.operations`）、webFileDir の
ジョブとして裏で行う（名前の変更は `command_overrides` でジョブにする。移動の貼り付け・
ドロップは webFileDir の既定でジョブ）。進み具合と［中止］はジョブにつなぐ（`_job_progress`）。
［中止］か時間の上限で止まったら `cancelled` で知らせ、webFileDir はその文をそのまま出して
一覧を読み直す。続きは、何も無いところの右クリックの「中断した操作を続ける」（`resume`）と、
管理の画面（`/.admin/operations`）から行う（Wiki設計者が了承、2026-10-01）。

以下はクロコの実装例: 続けてよいのは、その操作を今やり直せる人（動くページすべてに編集の
権限がある人。始めた本人には限らない）。中断している操作と範囲が重なる削除も断る
（名前の変更・移動は `pagerename` が断る）。

## webFileDir 1.0 に合わせたこと

webFileDir 1.0（同梱は 1.0.1）は、画面の操作をサーバが宣言する「コマンド」にした作り直しで、
0.2 系の開く経路（`OpenMethod`）と画面の機能の ON/OFF（`features`）が無くなった。Wiki設計者が
1.0 へ移ることを前提に webFileDirs へ作業を依頼し（2026-10-01）、1.0.1 で同梱を入れ替えた。
振る舞いは 0.2 系と同じにする（以下はクロコの実装例）:

- ページを参照・編集・新しいタブで開くは独自のコマンド（`commands`・`run_command`）。上の
  「ページを参照できる」「ページを編集できる」
- 項目に `ext=""` を付ける（webFileDir は名前から拡張子を切り出すので、`ver.0` が `0` になる）
- 削除・貼り付け・ドロップでの移動は、webFileDir が裏のスレッド（ジョブ）で行う。そこでは
  cookie が読めないので、要求の中で閲覧者を判定して固定する（`auth.fix_viewer`。webFileDir は
  ジョブへ文脈を写す。1.0.1 で入った）
- 0.2 系の webFileDir を読み込んだときは使わない（`_is_supported`。503 で知らせる）

webFileDir の最上位のパッケージ名は `server` で、`_sys` に並べると名前がぶつかりかねない。
そこで**webFileDir には手を入れず、`webfiledir` という名前で読み込む**
（中は相対 import だけなので、名前を変えても動く）。webFileDir は wikiSystem に同梱して
いる（置き場所は paths.WEBFILEDIR_DIR、既定は `_sys/webfiledir`）。
"""
import html
import importlib
import importlib.util
import json
import os
import re
import sys
import threading
import time
import uuid
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib import pagedb, pagelist, pagerename
from wikilib.auth import PAGE_WRITE
from wikilib.attach import attach_dir_for, has_attach_files
from wikilib.pagemove import convert_page_to_folder, page_file_of
from wikilib.pagerename import unwritable_pages
from wikilib.pagesave import save_page
from wikilib.pagetree import TOP_PAGE_LABEL
from wikilib.paths import (
    FILES_URLPATH, INDEX_NAME, MARKUP_FORMATS, WEBFILEDIR_DIR, default_markup_ext,
    entry_subpath_of, is_folder_entry, markup_name_for, pagepath_of_subpath, resolve_page_ref,
)
from wikilib.wikiconfig import default_markup, load_wiki_config

PACKAGE = "webfiledir"
MOUNT_ID = "wiki"   # 1つのアプリに1つだけのマウント（Wikiごとにアプリを分けている）
# Wikiの直下の入口（トップページ）をファイルとして出すときの名前（Wiki設計者の指示、2026-09-28）。
# ほかのフォルダの入口はフォルダの行に重ねるが、直下には重ねる行が無いため
TOP_PAGE_NAME = TOP_PAGE_LABEL   # 編集画面のページ一覧などと同じ表記
PAGE_METHOD = "page"   # ページを参照する開く経路の id（0.2 系はファイルにもフォルダにも使う）
EDIT_METHOD = "edit"   # ページを編集する開く経路の id（同じ）
# webFileDir 1.0.0 の独自のコマンドの id（開く経路の代わり。モジュール冒頭）
DIR_PAGE_METHOD = "dir-page"   # フォルダの入口のページを参照する（Shift で開く）
TAB_METHOD = "new-tab"         # フォルダを新しいタブで開く（既定の tab の代わり）
RESUME_COMMAND = "resume"      # 中断した操作（名前の変更・移動）を続ける
# 見出し連番（名前の先頭に「番号.」を振る。webFileDir の見本に従う）。見本の id「numbering」は
# webFileDir が見本のコマンドに取ってあり、独自のコマンドには使えない
NUMBERING_COMMAND = "page-numbering"
# 見出し連番で、名前の先頭から取り除く元の番号（webFileDir の見本 server/samples.py と同じ）
NUMBER_PREFIX_RE = re.compile(r"[0-9]+\.")
FOLDERIZE_COMMAND = "page-to-folder"   # ページをフォルダにする（モジュール冒頭「フォルダ化」）
# 削除するページに添付があるときの問い返し（モジュール冒頭「削除」。文言は Wiki設計者のもの）
TRASH_ATTACH_ANSWER = "trashAttach"
TRASH_ATTACH_QUESTION = ("添付ファイルを含むページを削除します。\n"
                         "削除をすると添付ファイルは管理者グループのみアクセスできる場所へ"
                         "退避され、後日削除されます。\n選択ページを削除しますか？")
NEW_PAGE_NAME = "新しいページ"   # webFileDir の既定のファイル名の代わり（モジュール冒頭「新規作成」）
NEW_PAGE_BODY = "（まだ内容がありません）\n"   # 新しく作るページの本文（空は「消す」になるため）
NEW_FOLDER_BODY = "#ls()\n"   # 新しく作るフォルダの入口の本文（配下のページの一覧）

_lock = threading.Lock()
_apps = {}          # wiki_dir → webFileDir のアプリ
_loaded = {}        # 読み込んだ webFileDir の部品（1回だけ読む）


# ---- webFileDir を読み込む ----------------------------------------------------

def _webfiledir():
    """webFileDir の部品を読み込んで返す。置き場所に無ければ None。"""
    if _loaded:
        return _loaded
    package_dir = os.path.join(WEBFILEDIR_DIR, "server")
    init = os.path.join(package_dir, "__init__.py")
    if not os.path.isfile(init):
        return None
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, init, submodule_search_locations=[package_dir])
        module = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = module
        spec.loader.exec_module(module)
    for name in ("app", "config", "errors", "attributes", "providers", "ops", "jobs"):
        _loaded[name] = importlib.import_module(f"{PACKAGE}.{name}")
    return _loaded


def _is_supported(wfd):
    """読み込んだ webFileDir が使える版（1.0 以降。操作をコマンドで宣言する）か。"""
    return hasattr(wfd["providers"], "Command")


# ---- プロバイダ ----------------------------------------------------------------

def _epoch(stamp):
    """pagedb の日時（"YYYY-mm-dd HH:MM:SS"、その土地の時刻）を UNIX 時刻に。"""
    try:
        return time.mktime(time.strptime(stamp, pagedb.TIME_FORMAT))
    except (TypeError, ValueError):
        return None


def _attach_count(wiki_dir, subpath):
    """そのページの添付の数（置き場所の直下のファイルだけ。下のフォルダは下位ページのもの）。"""
    directory = attach_dir_for(wiki_dir, subpath)
    if directory is None or not os.path.isdir(directory):
        return 0
    return sum(1 for e in os.scandir(directory) if e.is_file())


# 項目の権限のビット（webFileDir の Entry.auth。8 = 動かす・4 = 読む・2 = 書く・1 = 実行）
AUTH_MOVE = 0o10
AUTH_READ_WRITE_EXEC = 0o7


class _Lookup:
    """権限の判定に使うもの。一覧では1回だけ作り、各行で使い回す。"""

    def __init__(self, wiki_dir):
        self.judge = pagelist.judge_for(wiki_dir)
        self.subpaths = pagedb.all_subpaths(wiki_dir)


def _rename_subpath(item):
    """名前を変えるときに rename_page へ渡す実体パス。入口の無い通り道のフォルダは、
    入口の形（`X/index`）で渡すと中のページごと動く。"""
    return item.subpath if item.exists else entry_subpath_of(item.subpath)


def _clean_name(name):
    """画面から届いた名前の前後の空白を落とす。

    `pagerename.rename_page` は前後の空白を落とした名前で動かすので、検査・ぶつかりの
    確認・動かしたあとの項目の引き直しも、同じ名前で行わないと食い違う。食い違うと、
    `ver_0 `（末尾に空白）への変更が実際には済んでいるのに、引き直しで見つからず
    404 を返し、画面は古い名前のまま「変えられませんでした」と出していた
    （2026-10-01、設計者の報告。=webfiledir/ の ver.0 → ver_0）。新しく作るときも
    同じで、空白の付いたページ名を作らない。落とすか断るかはクロコの判断で、
    rename_page とエクスプローラー（末尾の空白を落とす）に合わせた。"""
    return (name or "").strip()


def numbered_names(names, start):
    """names の順に、start からの番号を「番号.」で先頭に付けた名前（webFileDir の見本と同じ）。
    桁数は start の文字数（足りなければ 0 で埋め、超えたらそのまま桁が増える）。
    先頭の「数字.」は取り除いてから付ける。"""
    width, n = len(start), int(start)
    return [f"{n + i:0{width}d}." + NUMBER_PREFIX_RE.sub("", name, count=1)
            for i, name in enumerate(names)]


def _job_progress(wfd):
    """作業の手順（`wikilib.operations`）の進み具合と中止を、webFileDir のジョブにつなぐ。
    ジョブの外（webFileDir が裏で行っていない要求）では、何も数えず中止もしない。"""
    from wikilib import operations
    jobs = wfd["jobs"]

    class JobProgress(operations.Progress):
        def add_total(self, n):
            jobs.add_total(n)

        def begin(self, item):
            jobs.begin(item)

        def advance(self):
            jobs.advance()

        def cancelled(self):
            return jobs.cancelled()

    return JobProgress()


def _make_provider_class(wfd):
    providers = wfd["providers"]
    ops = wfd["ops"]
    attrs = wfd["attributes"]   # クラスの本体で attributes に代入するので、別の名前で持つ
    Attribute = attrs.Attribute
    ApiError = wfd["errors"].ApiError
    Command = providers.Command

    class WikiPagesProvider(providers.Provider):
        """Wikiのページ階層を木として見せる。ページを参照・編集でき、名前を変え・動かし・消し、新しく作れる。"""

        # before_delete は、知っている webFileDir（1.2.0 から）でだけ宣言する。知らない版は
        # 知らない capabilities を断るので、そのときは添付を尋ねずに今までどおり消す
        capabilities = frozenset({"rename", "move", "copy", "delete", "mkdir", "touch"}
                                 | ({"before_delete"} & wfd["app"].KNOWN_CAPABILITIES))   # モジュール冒頭
        # 開く経路は独自のコマンドで宣言する（モジュール冒頭「ページを参照できる」）。
        # ファイルはダブルクリック・Enter、フォルダは Shift でページを参照する。
        # 既定の tab（新しいタブで開く）はフォルダの Shift を使うので止め、Shift を
        # 使わない独自のコマンドとして作り直す（pane はそのまま使う）
        _one = {"select": "one", "items": {"auth": "read"}}
        commands = (
            Command(PAGE_METHOD, "ページを参照", places=("item",), group="open", order=10,
                    open="default", when={"kinds": ["file"], **_one}),
            Command(DIR_PAGE_METHOD, "ページを参照", places=("item",), group="open", order=10,
                    open="shift", when={"kinds": ["dir"], **_one}),
            Command(EDIT_METHOD, "ページの編集", places=("item",), group="open", order=11,
                    when=_one),
            Command(TAB_METHOD, "新しいタブで開く", places=("item",), group="open", order=20,
                    when={"kinds": ["dir"], "select": "one", "items": {"auth": "exec"},
                          "reachable": True}),
            # 中断した名前の変更・移動の続き（モジュール冒頭「止めて続きから」）
            Command(RESUME_COMMAND, "中断した操作を続ける", places=("background",),
                    group="resume", order=90, job=True),
            # 見出し連番（モジュール冒頭「見出し連番」。宣言は webFileDir の見本と同じ）
            Command(NUMBERING_COMMAND, "見出し連番", places=("item",), group="edit", order=33,
                    job=True,
                    when={"kinds": ["file"], "select": "some",
                          "items": {"auth": "move", "partial": True}},
                    input={"part": "prompt", "title": "@promptTitle", "label": "@promptLabel",
                           "value": "001", "detail": "@promptDetail"},
                    on_error={"bad_input": [{"do": "retryInput"}]},
                    texts={"promptTitle": "見出し連番", "promptLabel": "開始値",
                           "promptDetail": "今の並び順に、名前の先頭へ「番号.」を付けます。"
                                           "桁数は開始値の桁数（01 なら 2 桁、001 なら 3 桁）。"
                                           "先頭に元からある「数字.」は付け替えます。"}),
            # フォルダ化（モジュール冒頭「フォルダ化」）。灰色にする条件は名前の変更と同じ
            # 「動かす」（トップページは持たない）
            Command(FOLDERIZE_COMMAND, "フォルダ化", places=("item",), group="edit", order=34,
                    when={"kinds": ["file"], "select": "some",
                          "items": {"auth": "move", "partial": True}}),
        )
        disable_commands = frozenset({"tab"})
        # 名前の変更は、指していたページを1枚ずつ直すので時間がかかりうる。裏で行い（ジョブ）、
        # 進み具合と［中止］を出す（webFileDir 1.0.1 で既定のコマンドもジョブにできるようになった）
        command_overrides = {"rename": {"job": True}}
        # 詳細表示の列の順（名前は webFileDir が必ず先頭に置く）。
        # 名前・タイトル・更新日時・サイズ・添付・書きかた（Wiki設計者の指示、2026-09-28）
        attributes = (
            Attribute("title", "タイトル", "text", {"type": "text"}, width=220),
            attrs.mtime_attribute(),
            attrs.size_attribute(),
            Attribute("attach", "添付", "number", {"type": "number"}, width=60),
            Attribute("markup", "書きかた", "text", {"type": "text"}, width=110),
        )

        def __init__(self, wiki_dir):
            self.wiki_dir = wiki_dir

        def _auth(self, item, lookup):
            """項目の権限（モジュール冒頭「項目の権限」）。"""
            movable = (item.subpath != INDEX_NAME and not unwritable_pages(
                self.wiki_dir, _rename_subpath(item), lookup.judge, lookup.subpaths))
            return AUTH_READ_WRITE_EXEC | (AUTH_MOVE if movable else 0)

        def _entry(self, item, lookup=None):
            # 入口（X/index）か、ページを持たない通り道ならフォルダ。それ以外はページ。
            # トップページ（直下の index）だけは入口でもファイルとして出す（TOP_PAGE_NAME）
            is_dir = not item.exists or (is_folder_entry(item.subpath)
                                         and item.subpath != INDEX_NAME)
            has_page = item.exists
            markup = None
            if has_page and item.ext:
                markup = MARKUP_FORMATS[markup_name_for(item.ext)]["label"]
            return providers.Entry(
                name=item.name,
                kind="dir" if is_dir else "file",
                size=item.size if has_page else None,
                mtime=_epoch(item.updated) if has_page else None,
                has_children=None,
                auth=self._auth(item, lookup or _Lookup(self.wiki_dir)),
                extra={"pagepath": item.pagepath if has_page else None},
                attrs={
                    "title": (item.title or None) if has_page else None,
                    "attach": _attach_count(self.wiki_dir, item.subpath) if has_page else None,
                    "markup": markup,
                },
                # webFileDir は名前から拡張子を切り出す（`ver1.2` なら `2`）。ページ名の
                # `.` 以降は拡張子ではないので、拡張子は無いと明示する
                ext="")

        def _items(self, path):
            """path（フォルダ）の直下の PageItem。そのフォルダ自身の入口は除く
            （フォルダの行に重ねてある）。

            ただし**Wikiの直下の入口（トップページ）は `TOP_PAGE_NAME` という名前で出す。**
            直下のフォルダには重ねる行が無く、除くと一覧のどこにも出なくなるため。
            同じ名前の本物のページが直下にあれば、そちらは出さない（名前は項目を指す
            IDなので、2つ並べられない）。"""
            under = "/".join(path)
            own = entry_subpath_of(under)
            items = []
            for i in pagelist.scandir(self.wiki_dir, under):
                if i.subpath == own:
                    if path:
                        continue
                    i.name = TOP_PAGE_NAME
                elif not path and i.name == TOP_PAGE_NAME:
                    continue
                items.append(i)
            return items

        def _item(self, path):
            """path の PageItem（閲覧者に見えるものだけ）。無ければ not_found。"""
            for item in self._items(path[:-1]):
                if item.name == path[-1]:
                    return item
            raise ApiError("not_found", "見つかりません", "/" + "/".join(path))

        def stat(self, path):
            if not path:
                # 一覧の根は動かせない
                return providers.Entry(name="", kind="dir", size=None, mtime=None,
                                       auth=AUTH_READ_WRITE_EXEC)
            return self._entry(self._item(path))

        def _is_default_file_name(self, name):
            """webFileDir が新しいファイルに付ける既定の名前（`ops.numbered` の番号付きも）か。"""
            stem, ext = ops.split_ext(ops.DEFAULT_FILE)
            return re.fullmatch(re.escape(stem) + r"( \(\d+\))?\." + re.escape(ext),
                                name) is not None

        def _taken(self, root):
            """そのページパスが使われているか（閲覧者に見えないページも含める）。"""
            return (os.path.exists(os.path.join(self.wiki_dir, root))
                    or page_file_of(self.wiki_dir, root)[0] is not None
                    or any(s == root or s.startswith(root + "/")
                           for s in pagedb.all_subpaths(self.wiki_dir)))

        def _new_place(self, parent, name):
            """フォルダ parent の中の name を、新しく作る・移す先として確かめ、ページパスを返す。"""
            where = "/" + "/".join(parent + (name,))
            if parent and self.stat(parent).kind != "dir":
                raise ApiError("bad_path", "フォルダではありません", "/" + "/".join(parent))
            problem = pagerename.check_name(name, self.wiki_dir)
            if problem:
                raise ApiError("bad_name", problem, where)
            root = "/".join(parent + (name,))
            if (not parent and name == TOP_PAGE_NAME) or self._taken(root):
                raise ApiError("exists", f"«{name}» はすでにあります", where)
            return root

        def _create(self, parent, name, is_dir):
            """ページ（is_dir ならフォルダとその入口）を作る（モジュール冒頭「新規作成」）。"""
            name = _clean_name(name)
            where = "/" + "/".join(parent + (name,))
            root = self._new_place(parent, name)
            if pagelist.judge_for(self.wiki_dir).check(root) != PAGE_WRITE:
                raise ApiError("forbidden", "ここにページを作る権限がありません", where)
            config = load_wiki_config(self.wiki_dir)
            subpath = entry_subpath_of(root) if is_dir else root
            if not save_page(self.wiki_dir, config, subpath,
                             default_markup_ext(default_markup(config)),
                             NEW_FOLDER_BODY if is_dir else NEW_PAGE_BODY):
                raise ApiError("internal", "ページを書き出せませんでした", where)
            return self.stat(parent + (name,))

        def mkdir(self, parent, name):
            return self._create(parent, name, True)

        def create_file(self, parent, name):
            if self._is_default_file_name(name):
                name = next(c for c in (ops.numbered(NEW_PAGE_NAME, n, True)
                                        for n in range(1, ops.MAX_NUMBER + 1))
                            if not self._taken("/".join(parent + (c,))))
            return self._create(parent, name, False)

        def move(self, src, dest_dir, new_name=None):
            """src をフォルダ dest_dir の中へ動かす（モジュール冒頭「移動」）。"""
            where = "/" + "/".join(src)
            item = self._item(src)
            if not src[:-1] and item.subpath == INDEX_NAME:
                raise ApiError("forbidden", "トップページは動かせません", where)
            subpath = _rename_subpath(item)
            name = _clean_name(new_name) or src[-1]
            old_root = pagerename.rename_root_of(subpath)
            new_root = "/".join(dest_dir + (name,))
            if new_root == old_root or new_root.startswith(old_root + "/"):
                raise ApiError("into_self", "自分の中へは動かせません", where)
            self._new_place(dest_dir, name)
            if unwritable_pages(self.wiki_dir, subpath, pagelist.judge_for(self.wiki_dir)):
                raise ApiError("forbidden", "編集の権限が無いページが含まれるため、"
                               "動かせません", where)
            self._rename(subpath, name, "/".join(dest_dir), where)
            return self.stat(dest_dir + (name,))

        def copy(self, src, dest_dir, new_name=None):
            """src をフォルダ dest_dir の中へ写す（モジュール冒頭「コピー」。中身は pagecopy）。"""
            from wikilib import pagecopy
            where = "/" + "/".join(src)
            item = self._item(src)
            if not src[:-1] and item.subpath == INDEX_NAME:
                raise ApiError("forbidden", "トップページは写せません", where)
            subpath = _rename_subpath(item)
            name = _clean_name(new_name) or src[-1]
            old_root = pagerename.rename_root_of(subpath)
            new_root = "/".join(dest_dir + (name,))
            if new_root == old_root or new_root.startswith(old_root + "/"):
                raise ApiError("into_self", "自分の中へは写せません", where)
            self._new_place(dest_dir, name)
            try:
                pagecopy.copy_pages(self.wiki_dir, load_wiki_config(self.wiki_dir), old_root,
                                    new_root, is_folder_entry(subpath),
                                    progress=_job_progress(wfd))
            except pagecopy.CopyError as e:
                raise ApiError(e.code, e.message, where)
            return self.stat(dest_dir + (name,))

        def rename(self, path, new_name):
            """名前を変える（決まりはモジュール冒頭の「名前の変更」）。"""
            where = "/" + "/".join(path)
            item = self._item(path)
            if not path[:-1] and item.name == TOP_PAGE_NAME and item.subpath == INDEX_NAME:
                raise ApiError("forbidden", "トップページは名前を変えられません", where)
            new_name = _clean_name(new_name)
            problem = pagerename.check_name(new_name, self.wiki_dir)
            if problem:
                raise ApiError("bad_name", problem, where)
            if new_name == path[-1]:
                return self._entry(item)
            if any(i.name == new_name for i in self._items(path[:-1])):
                raise ApiError("exists", f"«{new_name}» はすでにあります", where)
            subpath = _rename_subpath(item)
            if unwritable_pages(self.wiki_dir, subpath, pagelist.judge_for(self.wiki_dir)):
                raise ApiError("forbidden", "編集の権限が無いページが含まれるため、"
                               "名前を変えられません", where)
            self._rename(subpath, new_name, None, where)
            return self.stat(path[:-1] + (new_name,))

        def _rename(self, subpath, new_name, new_folder, where):
            """名前の変更・移動を行う。止めたら（［中止］・時間切れ）cancelled で知らせる
            （webFileDir はその文をそのまま出し、一覧を読み直す）。"""
            progress = _job_progress(wfd)
            ok, message, _ = pagerename.rename_page(
                self.wiki_dir, load_wiki_config(self.wiki_dir), subpath, new_name,
                new_folder, progress=progress)
            if ok:
                return
            if progress.paused is not None:
                raise ApiError("cancelled", message, where)
            raise ApiError("bad_request", message, where)

        def _page_target(self, path, edit):
            """ページを参照する・編集するときの (URL, 送りかた)。フォルダなら入口のページ。
            編集は、ページのURLへ `cmd=edit` を POST で送る（モジュール冒頭）。

            URL は画面（`…/.files/`）からの相対にする。アプリは Wikiごとに1つで、
            ファームの名前をURLに出すかどうか（explicit_farm）は要求ごとに変わりうるため、
            絶対の URL は持たない。"""
            entry = self.stat(path)   # 見えないページは not_found（stat が pagelist を通す）
            pagepath = entry.extra.get("pagepath")
            if pagepath is None:
                raise ApiError("not_found", "このフォルダにはページがありません",
                               "/" + "/".join(path))
            url = "../" + urlquote(pagepath)
            if not edit:
                return url, None
            if pagelist.judge_for(self.wiki_dir).check(pagepath) != PAGE_WRITE:
                raise ApiError("forbidden", "このページを編集する権限がありません",
                               "/" + "/".join(path))
            return url, {"cmd": "edit"}

        def run_command(self, command_id, ctx):
            """webFileDir 1.0.0 の独自のコマンド（ページを参照・編集、新しいタブで開く）。"""
            if command_id == RESUME_COMMAND:
                return self._resume()
            if command_id == NUMBERING_COMMAND:
                return self._numbering(ctx)
            if command_id == FOLDERIZE_COMMAND:
                return self._folderize(ctx)
            if command_id not in (PAGE_METHOD, DIR_PAGE_METHOD, EDIT_METHOD, TAB_METHOD):
                return super().run_command(command_id, ctx)
            if len(ctx.paths) != 1:
                raise ApiError("bad_request", "1つだけ選んでください")
            path = tuple(ctx.paths[0])
            if command_id == TAB_METHOD:
                if self.stat(path).kind != "dir":
                    raise ApiError("bad_path", "フォルダではありません", "/" + "/".join(path))
                return [providers.Browse(ctx.mount, "/" + "/".join(path), "_blank")]
            url, params = self._page_target(path, command_id == EDIT_METHOD)
            if params is None:
                return [providers.Navigate(url, "_blank")]
            return [providers.Navigate(url, "_blank", "POST", params)]

        def _resume(self):
            """中断した名前の変更・移動の続きを、古いものから行う（ジョブの中）。

            続けてよいのは、その操作を今やり直せる人＝動くページすべてに編集の権限が
            ある人（`unwritable_pages`。名前の変更と同じ考えかた。始めた本人には限らない。
            クロコの判断）。続けられないものは飛ばして知らせる。"""
            from wikilib import operations
            judge = pagelist.judge_for(self.wiki_dir)
            config = load_wiki_config(self.wiki_dir)
            done, skipped = 0, 0
            for op in operations.unfinished(self.wiki_dir):
                if operations.is_active(op):
                    continue
                if not self._may_resume(op, judge):
                    skipped += 1
                    continue
                progress = _job_progress(wfd)
                ok, message, _ = pagerename.resume_operation(
                    self.wiki_dir, config, op["id"], progress=progress)
                if not ok:
                    raise ApiError("cancelled" if progress.paused is not None else "bad_request",
                                   message)
                done += 1
            if not done and not skipped:
                return [providers.Message("中断している操作はありません。", "info")]
            text = f"中断していた操作を {done} 件、最後まで済ませました。" if done else ""
            if skipped:
                text += (f"続ける権限の無い操作が {skipped} 件あります"
                         "（動くページすべてを編集できる人か、管理の画面から続けてください）。")
            return [providers.Message(text, "info"), providers.Reload()]

        def _numbering(self, ctx):
            """見出し連番（モジュール冒頭）。送られた順（画面の今の並び順）に番号を振る。"""
            start = (ctx.input or "").strip()
            if not re.fullmatch(r"[0-9]+", start):
                raise ApiError("bad_input", "開始値は半角の数字で入力してください（例: 001）")
            srcs = [tuple(p) for p in ctx.paths]
            if not srcs or any(p[:-1] != srcs[0][:-1] for p in srcs):
                raise ApiError("bad_request", "同じフォルダの項目を選んでください")
            folder = srcs[0][:-1]
            names = [p[-1] for p in srcs]
            targets = numbered_names(names, start)
            selected = set(names)
            present = {i.name for i in self._items(folder)}
            judge = pagelist.judge_for(self.wiki_dir)
            failed = []          # (名前, 理由)
            plan = []            # (今の名前, 付ける名前)
            for name, target in zip(names, targets):
                if name == target:
                    continue
                if target not in selected and (target in present or self._taken(
                        "/".join(folder + (target,)))):
                    failed.append((name, f"«{target}» はすでにあります"))
                    continue
                problem = pagerename.check_name(target, self.wiki_dir)
                if problem:
                    failed.append((name, problem))
                    continue
                item = self._item(folder + (name,))
                if unwritable_pages(self.wiki_dir, _rename_subpath(item), judge):
                    failed.append((name, "編集の権限が無いページが含まれます"))
                    continue
                plan.append((name, target))
            # 選んだもの同士で名前が入れ替わるものは、いったん仮の名前へ（webFileDir の見本と同じ
            # 考えかた）。名前の変更はリンクを直すので、仮の名前を経るのは要るものだけにする
            current = {name for name, _ in plan}
            staged = []
            for name, target in plan:
                if target in current:
                    temporary = f"numbering-{uuid.uuid4().hex[:12]}"
                    if self._rename_or_fail(folder, name, temporary, failed):
                        staged.append((temporary, target, name))
                else:
                    staged.append((name, target, name))
            done = []
            for now, target, original in staged:
                if self._rename_or_fail(folder, now, target, failed, original):
                    done.append(target)
                elif now != original:
                    self._rename_or_fail(folder, now, original, failed)   # 元の名前に戻す
            text = f"{len(done)} 個の項目に番号を付けました。" if done else "番号を付けた項目はありません。"
            if failed:
                text += " 付けられなかった項目: " + "、".join(
                    f"{name}（{why}）" for name, why in failed)
            return [providers.Message(text, "error" if failed else "info"),
                    providers.Reload(done or None)]

        def _folderize(self, ctx):
            """選んだページをフォルダにする（モジュール冒頭「フォルダ化」）。できないものは
            その項目だけ飛ばし、知らせにまとめる。"""
            from wikilib import operations
            judge = pagelist.judge_for(self.wiki_dir)
            config = load_wiki_config(self.wiki_dir)
            done, failed = [], []   # 済んだ名前 / (名前, 理由)
            for path in (tuple(p) for p in ctx.paths):
                name = path[-1] if path else ""
                try:
                    item = self._item(path)
                except ApiError as e:
                    failed.append((name, e.message))
                    continue
                if is_folder_entry(item.subpath) or not item.exists:
                    failed.append((name, "ページではありません"))   # トップページ・フォルダ
                    continue
                if unwritable_pages(self.wiki_dir, item.subpath, judge):
                    failed.append((name, "編集の権限がありません"))
                    continue
                busy = operations.overlapping(self.wiki_dir, (item.pagepath,))
                if busy is not None:
                    failed.append((name, operations.busy_message(busy)))
                    continue
                if not convert_page_to_folder(self.wiki_dir, config, item.subpath):
                    failed.append((name, "フォルダにできませんでした"))
                    continue
                done.append(name)
            text = (f"{len(done)} 個のページをフォルダにしました。" if done
                    else "フォルダにしたページはありません。")
            if failed:
                text += " できなかった項目: " + "、".join(f"{n}（{why}）" for n, why in failed)
            return [providers.Message(text, "error" if failed else "info"),
                    providers.Reload(done or None)]

        def _rename_or_fail(self, folder, name, new_name, failed, label=None):
            """folder の中の name を new_name に変える。できなければ failed に足して False。"""
            try:
                item = self._item(folder + (name,))
                self._rename(_rename_subpath(item), new_name, None, "/" + "/".join(folder + (name,)))
                return True
            except ApiError as e:
                failed.append((label or name, e.message))
                if e.code == "cancelled":
                    raise
                return False

        def _may_resume(self, op, judge):
            plan = op.get("plan") or {}
            root = plan.get("new_root") if "move" in op.get("done", []) else plan.get("old_root")
            if not root:
                return False
            subpath = entry_subpath_of(root) if plan.get("is_folder") else root
            return not unwritable_pages(self.wiki_dir, subpath, judge)

        def before_delete(self, paths, answers):
            """削除の前に、添付があれば尋ねる（モジュール冒頭「削除」）。

            添付が無ければ None（webFileDir の既定の確認に任せる）。フォルダは、ページの無い
            下位フォルダに置いた添付も trashbox へ移るので、置き場所を下までたどって数える。
            項目が見つからないなどの誤りは、ここでは問わない（delete が知らせる）。"""
            if not any(self._has_attachments(tuple(p)) for p in paths):
                return None
            answer = answers.get(TRASH_ATTACH_ANSWER)
            if answer is None:
                return [providers.Modal(
                    "削除", TRASH_ATTACH_QUESTION,
                    type="yesno", answer=TRASH_ATTACH_ANSWER, default="no")]
            return answer == "yes"

        def _has_attachments(self, path):
            try:
                subpath = _rename_subpath(self._item(path))
            except ApiError:
                return False
            if not is_folder_entry(subpath):
                return has_attach_files(self.wiki_dir, subpath)
            directory = attach_dir_for(self.wiki_dir, pagerename.rename_root_of(subpath))
            if directory is None:
                return False
            return any(files for _, _, files in os.walk(directory))

        def delete(self, path):
            """ページ・フォルダを消す（モジュール冒頭「削除」）。"""
            from wikilib.editor import delete_page
            where = "/" + "/".join(path)
            item = self._item(path)
            if not path[:-1] and item.subpath == INDEX_NAME:
                raise ApiError("forbidden", "トップページは削除できません", where)
            subpath = _rename_subpath(item)
            if is_folder_entry(subpath):
                prefix = pagerename.rename_root_of(subpath) + "/"
                targets = [s for s in pagedb.all_subpaths(self.wiki_dir) if s.startswith(prefix)]
            else:
                targets = [subpath]
            from wikilib import operations
            busy = operations.overlapping(self.wiki_dir, (pagerename.rename_root_of(subpath),))
            if busy is not None:
                raise ApiError("bad_request", operations.busy_message(busy), where)
            judge = pagelist.judge_for(self.wiki_dir)
            if any(judge.check(pagepath_of_subpath(s)) != PAGE_WRITE for s in targets):
                raise ApiError("forbidden", "編集の権限が無いページが含まれるため、"
                               "削除できません", where)
            config = load_wiki_config(self.wiki_dir)
            # 深いページから。同じ深さでは入口（index）を最後に。下位を消すと入口だけの
            # フォルダはページに戻る（X/index → X）ので、毎回ページパスで引き直す
            for s in sorted(targets, key=lambda s: (-s.count("/"), is_folder_entry(s))):
                ref = resolve_page_ref(self.wiki_dir, pagepath_of_subpath(s))
                ok, message = delete_page(self.wiki_dir, config, ref)
                if not ok:
                    raise ApiError("bad_request", message, where)
            if is_folder_entry(subpath):
                # ページの無い下位フォルダに置いた添付も、持ち主ごと消えたので trashbox へ
                from wikilib.garbagecollect import trash_attachments
                trash_attachments(self.wiki_dir, config, pagerename.rename_root_of(subpath),
                                  tree=True)

        def listdir(self, path):
            if path and self.stat(path).kind != "dir":
                raise ApiError("bad_path", "フォルダではありません", "/" + "/".join(path))
            lookup = _Lookup(self.wiki_dir)
            return [self._entry(i, lookup) for i in self._items(path)]

    return WikiPagesProvider


# ---- アプリ ------------------------------------------------------------------

def _app_for(wiki_dir, farm):
    """そのWikiの webFileDir のアプリ（初めて使うときに作って持っておく）。"""
    with _lock:
        app = _apps.get(wiki_dir)
        if app is not None:
            return app
        wfd = _webfiledir()
        if wfd is None or not _is_supported(wfd):
            return None
        cfg = wfd["config"]
        provider_class = _make_provider_class(wfd)
        config = cfg.Config(
            server=cfg.ServerConfig(),
            mounts=(cfg.MountConfig(id=MOUNT_ID, type="wikipages", root=None,
                                    readonly=False, label=farm),))
        app = wfd["app"].create_app(
            config,
            # マウントとしてはどの閲覧者にも書ける形で見せる。何が見え、何を変えられるかは
            # ページごとの権限で決まる（WikiPagesProvider が pagelist・unwritable_pages で確かめる）
            mount_access=lambda req, mid: "rw",
            # 開いたままの接続（自動更新）は使わない。Wiki のサーバは要求ごとにスレッドを
            # 立てるが、ページは Wiki の画面からも変わり、その変化はどのみち届かないため
            live_updates=False,
            providers={"wikipages": lambda m: provider_class(wiki_dir)})
        _apps[wiki_dir] = app
        return app


# ---- 画面 --------------------------------------------------------------------

def _screen_html(farm):
    """ファイル一覧の画面（題名を Wiki の名前にする）。"""
    return screen_html(f"ファイル一覧 - {farm}")


def screen_html(title):
    """webFileDir の `index.html` と同じ組み立ての画面で、題名だけを変えたもの。
    出す操作はプロバイダの宣言で決まる。資材・APIの相対URLはそのまま webFileDir へ届く。
    テーマのファイル（`wikilib.themefilesui`）も使う。"""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="static/css/app.css">
  <style>
    html, body {{ height: 100%; margin: 0; }}
  </style>
</head>
<body>
  <main id="app"></main>
  <script type="module">
    import {{ createShell }} from "./static/js/shell.js";
    const app = document.getElementById("app");
    try {{
      createShell(app);
    }} catch (err) {{
      app.textContent = err.message;
    }}
  </script>
</body>
</html>
"""


# 渡す要求から落とす、bottle が経路ごとに覚えている値（パスをずらすので使えない）
_ROUTE_KEYS = ("bottle.app", "bottle.route", "route.handle", "route.url_args",
               "bottle.request", "bottle.request.urlparts")


def serve_files(wiki_dir, farm, files_base_url):
    """`/.files/…` の要求を webFileDir へ渡す。files_base_url は `…/.files`（末尾の / 無し）。"""
    env = request.environ
    path_info = env.get("PATH_INFO", "")
    marker = "/" + FILES_URLPATH
    at = path_info.find(marker)
    rest = path_info[at + len(marker):] if at >= 0 else ""
    if not rest:
        # 画面の相対URLが末尾の / を前提にしている（webFileDir の embed と同じ扱い）
        query = env.get("QUERY_STRING", "")
        return HTTPResponse(status=303, headers={
            "Location": files_base_url + "/" + ("?" + query if query else "")})

    app = _app_for(wiki_dir, farm)
    if app is None:
        return HTTPResponse(
            status=503, body="ファイル一覧の部品（webFileDir 1.0 以降）が見つかりません。",
            headers={"Content-Type": "text/plain; charset=utf-8"})

    if rest == "/" and env.get("REQUEST_METHOD") in ("GET", "HEAD"):
        # 画面そのものだけは wikiSystem が返す（_screen_html）。webFileDir と同じく毎回確かめさせる
        return HTTPResponse(_screen_html(farm), headers={
            "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache"})

    # 閲覧者を要求の中で判定して固定する。webFileDir 1.0.0 は時間のかかるコマンドを別の
    # スレッド（ジョブ）で行い、そこでは cookie が読めないため（auth.fix_viewer）。
    # 文脈ごとジョブへ写すのは webFileDir の側（依頼中、2026-10-01）
    from wikilib import auth
    from wikilib.pagesync import farm_of_wiki_dir
    uid = auth.current_uid(wiki_dir, farm_of_wiki_dir(wiki_dir))
    with auth.fix_viewer(uid):
        return call_app(app, at + len(marker))


def call_app(app, prefix_len):
    """今の要求を webFileDir のアプリへ渡し、返りを HTTPResponse に詰める。PATH_INFO の先頭
    prefix_len 文字（`/=<Wiki>/.files` など）を SCRIPT_NAME へ移して呼ぶ（bottle の mount と同じ）。
    テーマのファイル（`wikilib.themefilesui`）も使う。"""
    env = request.environ
    path_info = env.get("PATH_INFO", "")
    inner = {k: v for k, v in env.items() if k not in _ROUTE_KEYS}
    inner["SCRIPT_NAME"] = env.get("SCRIPT_NAME", "") + path_info[:prefix_len]
    inner["PATH_INFO"] = path_info[prefix_len:]

    out = HTTPResponse([])

    def start_response(status, headerlist, exc_info=None):
        if exc_info:
            raise exc_info[1].with_traceback(exc_info[2])
        out.status = status
        for name, value in headerlist:
            out.add_header(name, value)
        return out.body.append

    body = app(inner, start_response)
    out.body = body if not out.body else list(out.body) + list(body)
    return out
