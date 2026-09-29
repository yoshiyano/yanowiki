"""ファイル一覧（`/.files/`）。webFileDir（別プロジェクト）を組み込み、Wikiのページを
エクスプローラーの形で見せる。

**変更は名前の変更・移動・削除と、フォルダ・ページの新規作成**（見るだけで始め
2026-09-28、2026-09-29 に足した）。コピーとごみ箱は無い（プロバイダの capabilities に無い）。

## 削除

削除は Wiki設計者の「削除もサポートしてください」（2026-09-29）で足した。

以下はクロコの実装例（設計者は未確認）:

- 中身は、編集画面で本文を空にして保存したときと同じ `editor.delete_page`。消す前の内容は
  「全文→空」の差分としてバックアップに残る。添付ファイルのあるページは消さない
  （`delete_page` の決まり）
- Wiki にごみ箱に当たるものは無いので、webFileDir には `delete`（完全に削除）だけを宣言する

    ページ     そのページだけを消す（配下のページは残る。編集画面と同じ）
    フォルダ   中のページすべて（入口を含む）を消す。先にすべてについて、編集の権限
               （W）があり添付が無いことを確かめ、1枚でも欠ければフォルダごと断る
               （途中まで消えて止まらないように）。深いページから順に消す
    (TopPage)  消せない

まとめて消すときは、移動と同じく webFileDir が1件ずつ行い、失敗したものだけが残る。

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
- 「index はデフォルトの wiki 形式に従った形式にして下さい」→ 入口の記法は Wikiの既定の
  記法（`edit.defaultwiki`）
- 「index のデフォルトとして #ls() を書き込んでおいて下さい」→ 入口の本文は `#ls()`
  （`NEW_FOLDER_BODY`）

以下はクロコの実装例（設計者は未確認）:

- ページ（ファイル）の記法も、入口と同じく Wikiの既定の記法にする（指示は入口についてだけ）
- 作るページの位置に編集の権限（W）が要る。同じ名前があれば `exists`
- ページ（ファイル）の本文は、見出しの無い一文（`NEW_PAGE_BODY`）。本文が空の保存は
  「ページを消す」の意味になるため。見出しが無いとタイトルはページ名になり、あとで名前を
  変えても表示が揃う（フォルダの入口の `#ls()` も同じ）
- webFileDir は新しいファイルに「新しいテキスト ドキュメント.txt」（番号付きも）を渡すが、
  拡張子の形で終わる名前はページ名に使えない。この既定の名前のときだけ
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

## 項目の権限（webFileDir v0.2.1 の `Entry.auth`）

画面がボタン・メニューを灰色にするための値。Wiki の権限を次のように当てはめる
（クロコの案を設計者が承認、2026-09-29）。

    動かす   名前を変えられるとき 1（動くページすべてに W。`unwritable_pages` が空）。
             トップページ・一覧の根は 0
    読む・実行   1（見えないページは一覧に出さない）
    書く     1。Wiki の権限はページごとで配下に引き継がれず、フォルダの時点では
             「中に作れるか」が決まらないため。作るときに確かめる

一覧では、判定器（`pagelist.judge_for`）と DB のページの一覧を1回だけ用意して、
各行で使い回す（`_Lookup`）。

**画面は、持たない機能（コピー・ごみ箱）を出さない。** 画面（`/.files/`）は webFileDir の
`index.html` ではなく wikiSystem が返し（`_screen_html`）、`createShell` に `features` を
直接渡して、そのボタン・メニュー・キー操作を止める（`DISABLED_FEATURES`）。webFileDir の
`?disable=` と同じ働きだが、URL にクエリを付けずに済む。Wiki設計者が「get の情報で停止は
見苦しい」と別の方法を求め、クロコが出したこの案を「その方法で機能を止めるのを実装して
ください」と採った（2026-09-29）。どの機能を止めるか（`DISABLED_FEATURES`）はクロコの実装例。
画面で出さないだけなので、断るのはプロバイダ（capabilities に無い操作は webFileDir が断る）。

**ページを参照できる**（`WikiPagesProvider.open`）。「開く」だけではフォルダに入るのか
ページを見るのか分からないので、ページを見る経路は「ページを参照」と呼ぶ（Wiki設計者の
「「開く」ではフォルダかページかわからないので、ファイルの「開く」も含め、「ページを参照」に
変更」、2026-09-29）。一覧を残すよう、どれも新しいタブで開く（クロコの実装例）。

    ファイル   ダブルクリック・Enter・右クリックの「開く（ページを参照）」
               （既定の経路は webFileDir の画面が「開く（…）」と包んで出す）
    フォルダ   ダブルクリック・Enter は中に入る（webFileDir の画面の既定）。入口のページ
               （`X/index`）は Shift を押しながら、または右クリックの「ページを参照」。
               入口の無い通り道のフォルダでは「ページがありません」と断る
               （経路はマウントごとの宣言で、フォルダごとには出し分けられない）

フォルダの経路は webFileDir の `dir_open_methods`（フォルダにも開く経路を持たせる仕組み）で
宣言する。フォルダのページを「Shift を押しながら開く処理、またはメニューから」開くのは
Wiki設計者の指示（2026-09-29）。Shift は webFileDir の既定では「新しいタブで開く」なので、
それをページを参照に回し、「新しいタブで開く」「隣の画面で開く」は Shift なしで残す
（中身は webFileDir に任せる。ここはクロコの実装例）。

**ページを編集できる**（右クリックの「ページの編集」。Wiki設計者の「メニューに「ページの
編集」を追加」、2026-09-29）。フォルダでは入口のページ。編集画面は `POST cmd=edit` でしか
開かない（GET では閲覧だけ。wiki.py の注記）ので、開く経路の navigate を POST にして
（webFileDir 1a9bea4 の `OpenResult.method`・`params`。POST を使う案1は設計者が選んだ）、
ページの見出しの「編集」ボタンと同じ値を新しいタブへ送る。複数を選んでいるときは出ない
（webFileDir の画面の作り。設計者は「エラー表示が必要ない仕様なので非常に良い」とした）。
ホットキー（Alt+E）は、設計者の「ホットキー実装はなしでも構いません」を受けて付けていない。
以下はクロコの実装例: 編集の権限（W）が無ければ編集画面を開かずに断る。

## 見せかた

    フォルダ   Wikiのフォルダ。入口（`X/index`）があれば、そのページの属性をフォルダの
               行に載せる。入口そのものはファイルとしては出さない。ただしWikiの直下の
               入口（トップページ）は `(TopPage)` というファイルとして出す
    ファイル   ページ。名前は拡張子を付けない（ページ名は拡張子の形で終われないので、
               名前がそのままURLの最後の要素になる）。記法は属性の列で見せる
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
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib import pagedb, pagelist, pagerename
from wikilib.auth import PAGE_WRITE
from wikilib.attach import attach_dir_for
from wikilib.pagemove import page_file_of
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
PAGE_METHOD = "page"   # ページを参照する開く経路の id（ファイルにもフォルダにも使う）
EDIT_METHOD = "edit"   # ページを編集する開く経路の id（同じ）
NEW_PAGE_NAME = "新しいページ"   # webFileDir の既定のファイル名の代わり（モジュール冒頭「新規作成」）
NEW_PAGE_BODY = "（まだ内容がありません）\n"   # 新しく作るページの本文（空は「消す」になるため）
NEW_FOLDER_BODY = "#ls()\n"   # 新しく作るフォルダの入口の本文（配下のページの一覧）

# 画面で止める webFileDir の機能（webFileDir の static/js/features.js の名前）。
# コピーとごみ箱を止める（どちらも持たない）。移動は切り取り→貼り付けとドラッグ＆ドロップ
# （Ctrl+ドラッグのコピーはサーバが断る）。削除は完全に削除になる。二画面（dual）は残す
DISABLED_FEATURES = ("copy", "trash")

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
    for name in ("app", "config", "errors", "attributes", "providers", "ops"):
        _loaded[name] = importlib.import_module(f"{PACKAGE}.{name}")
    return _loaded


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


def _make_provider_class(wfd):
    providers = wfd["providers"]
    ops = wfd["ops"]
    attrs = wfd["attributes"]   # クラスの本体で attributes に代入するので、別の名前で持つ
    Attribute = attrs.Attribute
    ApiError = wfd["errors"].ApiError
    OpenMethod = providers.OpenMethod
    OpenResult = providers.OpenResult

    class WikiPagesProvider(providers.Provider):
        """Wikiのページ階層を木として見せる。ページを参照・編集でき、名前を変え・動かし・消し、新しく作れる。"""

        capabilities = frozenset({"rename", "move", "delete", "mkdir", "touch"})   # モジュール冒頭
        # 開く経路（モジュール冒頭の「ページを参照できる」）。ファイルは1つだけで、
        # メニューでは「開く（ページを参照）」になる
        open_methods = (OpenMethod(PAGE_METHOD, "ページを参照"),
                        OpenMethod(EDIT_METHOD, "ページの編集"))
        # フォルダは中に入るのが既定（webFileDir の画面が持つ）。そのあとに続く経路。
        # tab・pane は webFileDir が扱う既定の経路と同じ id（open は None を返して任せる）
        dir_open_methods = (
            OpenMethod(PAGE_METHOD, "ページを参照", modifier="shift"),
            OpenMethod(EDIT_METHOD, "ページの編集"),
            OpenMethod("tab", "新しいタブで開く"),
            OpenMethod("pane", "隣の画面で開く"),
        )
        # 詳細表示の列の順（名前は webFileDir が必ず先頭に置く）。
        # 名前・タイトル・更新日時・サイズ・添付・記法（Wiki設計者の指示、2026-09-28）
        attributes = (
            Attribute("title", "タイトル", "text", {"type": "text"}, width=220),
            attrs.mtime_attribute(),
            attrs.size_attribute(),
            Attribute("attach", "添付", "number", {"type": "number"}, width=60),
            Attribute("markup", "記法", "text", {"type": "text"}, width=110),
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
                })

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
            problem = pagerename.check_name(name)
            if problem:
                raise ApiError("bad_name", problem, where)
            root = "/".join(parent + (name,))
            if (not parent and name == TOP_PAGE_NAME) or self._taken(root):
                raise ApiError("exists", f"«{name}» はすでにあります", where)
            return root

        def _create(self, parent, name, is_dir):
            """ページ（is_dir ならフォルダとその入口）を作る（モジュール冒頭「新規作成」）。"""
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
            name = new_name or src[-1]
            old_root = pagerename.rename_root_of(subpath)
            new_root = "/".join(dest_dir + (name,))
            if new_root == old_root or new_root.startswith(old_root + "/"):
                raise ApiError("into_self", "自分の中へは動かせません", where)
            self._new_place(dest_dir, name)
            if unwritable_pages(self.wiki_dir, subpath, pagelist.judge_for(self.wiki_dir)):
                raise ApiError("forbidden", "編集の権限が無いページが含まれるため、"
                               "動かせません", where)
            ok, message, _ = pagerename.rename_page(
                self.wiki_dir, load_wiki_config(self.wiki_dir), subpath, name,
                new_folder="/".join(dest_dir))
            if not ok:
                raise ApiError("bad_request", message, where)
            return self.stat(dest_dir + (name,))

        def rename(self, path, new_name):
            """名前を変える（決まりはモジュール冒頭の「名前の変更」）。"""
            where = "/" + "/".join(path)
            item = self._item(path)
            if not path[:-1] and item.name == TOP_PAGE_NAME and item.subpath == INDEX_NAME:
                raise ApiError("forbidden", "トップページは名前を変えられません", where)
            problem = pagerename.check_name(new_name)
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
            ok, message, _ = pagerename.rename_page(
                self.wiki_dir, load_wiki_config(self.wiki_dir), subpath, new_name)
            if not ok:
                raise ApiError("bad_request", message, where)
            return self.stat(path[:-1] + (new_name,))

        def open(self, path, method):
            """ページを参照する・編集する（新しいタブで開く）。フォルダなら入口のページ。
            フォルダの tab・pane は None を返し、webFileDir に任せる（フォルダを表示する）。
            編集は、ページのURLへ `cmd=edit` を POST で送る（モジュール冒頭）。

            URL は画面（`…/.files/`）からの相対にする。アプリは Wikiごとに1つで、
            ファームの名前をURLに出すかどうか（explicit_farm）は要求ごとに変わりうるため、
            絶対の URL は持たない。"""
            entry = self.stat(path)   # 見えないページは not_found（stat が pagelist を通す）
            if method not in (PAGE_METHOD, EDIT_METHOD):
                return None
            pagepath = entry.extra.get("pagepath")
            if pagepath is None:
                raise ApiError("not_found", "このフォルダにはページがありません",
                               "/" + "/".join(path))
            url = "../" + urlquote(pagepath)
            if method == PAGE_METHOD:
                return OpenResult("navigate", url, "_blank")
            if pagelist.judge_for(self.wiki_dir).check(pagepath) != PAGE_WRITE:
                raise ApiError("forbidden", "このページを編集する権限がありません",
                               "/" + "/".join(path))
            return OpenResult("navigate", url, "_blank", method="POST", params={"cmd": "edit"})

        def delete(self, path):
            """ページ・フォルダを消す（モジュール冒頭「削除」）。"""
            from wikilib.editor import delete_page, page_has_attachments
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
            judge = pagelist.judge_for(self.wiki_dir)
            if any(judge.check(pagepath_of_subpath(s)) != PAGE_WRITE for s in targets):
                raise ApiError("forbidden", "編集の権限が無いページが含まれるため、"
                               "削除できません", where)
            if any(page_has_attachments(self.wiki_dir, s) for s in targets):
                raise ApiError("bad_request", "添付ファイルのあるページが含まれるため、削除"
                               "できません。先に添付ファイルを片付けてください", where)
            config = load_wiki_config(self.wiki_dir)
            # 深いページから。同じ深さでは入口（index）を最後に。下位を消すと入口だけの
            # フォルダはページに戻る（X/index → X）ので、毎回ページパスで引き直す
            for s in sorted(targets, key=lambda s: (-s.count("/"), is_folder_entry(s))):
                ref = resolve_page_ref(self.wiki_dir, pagepath_of_subpath(s))
                ok, message = delete_page(self.wiki_dir, config, ref)
                if not ok:
                    raise ApiError("bad_request", message, where)

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
        if wfd is None:
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
    """ファイル一覧の画面。webFileDir の `index.html` と同じ組み立てで、features だけを
    クエリからではなく直接渡す（モジュール冒頭）。資材・APIの相対URLはそのまま webFileDir へ届く。"""
    features = json.dumps({name: False for name in DISABLED_FEATURES})
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ファイル一覧 - {html.escape(farm)}</title>
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
      createShell(app, {{ features: {features} }});
    }} catch (err) {{
      app.textContent = err.message; // webFileDir が機能の名前を変えたときなど
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
            status=503, body="ファイル一覧の部品（webFileDir）が見つかりません。",
            headers={"Content-Type": "text/plain; charset=utf-8"})

    if rest == "/" and env.get("REQUEST_METHOD") in ("GET", "HEAD"):
        # 画面そのものだけは wikiSystem が返す（_screen_html）。webFileDir と同じく毎回確かめさせる
        return HTTPResponse(_screen_html(farm), headers={
            "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache"})

    inner = {k: v for k, v in env.items() if k not in _ROUTE_KEYS}
    inner["SCRIPT_NAME"] = env.get("SCRIPT_NAME", "") + path_info[:at + len(marker)]
    inner["PATH_INFO"] = rest

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
