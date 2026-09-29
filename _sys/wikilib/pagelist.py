"""**読み手に見せるページの一覧**を作る層（Wiki設計者の指示、2026-09-17）。

ページの一覧は、これまで場所ごとに作られていた——`#ls` はフォルダを自分で走査し、
`#recent` はDBの並びをそのまま使い、検索は候補を自分で集め、`/.pagetree` は平文の
フォルダを辿る。**閲覧の権限を入れるには、その全部に同じ判定を書く必要があった。**

そこで、**一覧を得る道を4本に決め、そこで必ず権限を見る**ようにした。

    scandir(wiki_dir, under)      1階層ぶん（`os.scandir` にあたる）
    glob(wiki_dir, pattern)       パターンに当たるもの
    walk(wiki_dir, under)         その下にあるページ全部
    filter(wiki_dir, names)       手元にある名前の並びを絞る（並び順はそのまま）

**`filter` があることで、一覧の形をしていないものも同じ関門を通せる。**
更新順（`#recent`）・アクセスの多い順（`#popular`）・検索の候補は、ディレクトリの
列挙ではないので、**自分で並びを作ってから `filter` に通す**という使いかたになる。

## 名前ではなく項目を返す

返すのは名前ではなく `PageItem`（`os.listdir` ではなく `os.scandir` の側）。
名前だけを返すと、使う側がタイトルや更新日時を1件ずつ引き直すことになり、
ページ数が増えたときに効いてくる（`pagedb.page_entries` が1回のSQLで揃えている
ものを、わざわざ崩すことになる）。

## どこで使い、どこで使わないか

**画面・プラグインに出す一覧はここを通す。** 逆に、**システムの内部処理は
`pagedb` を直接使う**——取り込み（`pagesync`）・名前の変更（`pagerename`）・
日次の控え（`dbbackup`）・DBの作り直しは、権限に関わらず全ページを見る必要が
あり、ここを通すと「権限のせいで取り込みが漏れる」という事故になる。

    pagedb・backup・accesslog   記録をそのまま読む層（権限を見ない）
    pagelist（ここ）            読み手に見せる一覧を作る層（必ず権限を見る）

閲覧者は `auth.current_uid` から取る（`pagedb.published_ref` と同じ作法）。
システムとして全部を見たいときは `auth.act_as(auth.SYSTEM_UID)` で包む。
"""
import fnmatch
import os

from wikilib import pagedb
from wikilib.auth import PAGE_NONE, PAGE_READ, PAGE_WRITE
from wikilib.paths import (
    FARM_PREFIX, INDEX_NAME, PAGE_EXTS, SYSTEM_PREFIX, entry_subpath_of,
    pagepath_of_subpath,
)

# 出どころ。既定は「公開された内容」（DB）で、平文ファイルを見るのは編集の道具だけ
SOURCE_PUBLISHED = "published"
SOURCE_FILES = "files"


class PageItem:
    """一覧の1件。**本文は持たない**（要るときは `pagedb.published_ref`）。

        name       直下の名前（`scandir` のときだけ意味を持つ。他は最後の要素）
        pagepath   URL上のページパス（`""` はそのWikiのトップ）
        subpath    実体のwiki相対パス（拡張子抜き、`index` 解決済み）
        title      取り出し済みの見出し。無ければ空文字列
        created    初回登録日時（DBの値。平文側では空）
        updated    最終更新日時（同上）
        size       大きさ（同上）
        exists     そこにページの実体があるか。`scandir` は**通り道でしかない
                   フォルダ**も返すので、その場合だけ偽になる
        has_children  その下にページがあるか（折りたたむかどうかの判断に使う）
        privilege  いまの閲覧者のアクセス権（`W`/`R`/`-`）
        ext        実体ファイルの拡張子（`.txt`/`.md`）。記法（PukiWiki/
                   Markdown。`wikilib.paths.markup_name_for`）を知るために持つ。
                   実体が無い・出どころが分からないときは None

    `PageRef`（1ページを開くときの入れもの）と名前を揃えてある。あちらは本文を
    運び、こちらは一覧に出す値を運ぶ。"""

    __slots__ = ("name", "pagepath", "subpath", "title", "created", "updated",
                 "size", "exists", "has_children", "privilege", "ext")

    def __init__(self, name, pagepath, subpath, title="", created="", updated="",
                 size=0, exists=True, has_children=False, privilege=None, ext=None):
        self.name = name
        self.pagepath = pagepath
        self.subpath = subpath
        self.title = title
        self.created = created
        self.updated = updated
        self.size = size
        self.exists = exists
        self.has_children = has_children
        self.privilege = privilege
        self.ext = ext

    def __repr__(self):
        return "PageItem({!r}, privilege={!r})".format(self.pagepath, self.privilege)


def judge_for(wiki_dir, privilege=None):
    """いまの閲覧者の判定器。すでに持っていれば、それをそのまま使う。

    1回の要求で何度も一覧を作る場面（メニュー＋`#ls`＋`#recent` など）では、
    判定器を持ち回せば下ごしらえが1回で済む（`PluginContext.privilege`）。"""
    if privilege is not None:
        return privilege
    from wikilib import auth
    from wikilib.pagesync import farm_of_wiki_dir
    uid = auth.current_uid(wiki_dir, farm_of_wiki_dir(wiki_dir))
    return auth.page_privilege(wiki_dir, uid)


def _allowed(value, need):
    """そのアクセス権が `need` を満たすか。`need=None` なら絞らない。"""
    if need is None:
        return True
    if need == PAGE_WRITE:
        return value == PAGE_WRITE
    return value != PAGE_NONE


def _item_of_row(row, name=None, has_children=False):
    """`pagedb` の1行（`page_entries` の形）を `PageItem` にする。

    `ext` は `row["ext"]`（`_file_rows` が添えたもの）があればそれを使い、
    無ければ `row["path"]`（DB側。`subpath + ext` の形）の拡張子から拾う。"""
    subpath = row["subpath"]
    pagepath = pagepath_of_subpath(subpath)
    ext = row.get("ext")
    if ext is None and row.get("path"):
        ext = os.path.splitext(row["path"])[1] or None
    return PageItem(
        name=name if name is not None else (pagepath.rsplit("/", 1)[-1] or pagepath),
        pagepath=pagepath, subpath=subpath, title=row.get("title") or "",
        created=row.get("created") or "", updated=row.get("updated") or "",
        size=row.get("size") or 0, exists=True, has_children=has_children, ext=ext)


def _by_pagepath(items):
    """**ページパスの順**に並べる。

    DBは実体パス（`subpath`）順で返すので、そのままだと `Tech/index`（＝ページ
    `Tech`）が `Tech/Secret` の後ろに来て、読み手から見た名前順とずれる。
    一覧は見える名前で並んでいるほうが自然なので、ここで揃える。"""
    return sorted(items, key=lambda i: i.pagepath)


def _judged(items, judge, need):
    """アクセス権を入れ、`need` を満たすものだけを返す。"""
    kept = []
    for item in items:
        item.privilege = judge.check(item.pagepath)
        if _allowed(item.privilege, need):
            kept.append(item)
    return kept


# ---- 出どころ（published / files） -------------------------------------------

def _rows_under(wiki_dir, under):
    """その下にあるページの行（`page_entries`）。`under` は実体パスの接頭辞。"""
    prefix = (under or "").strip("/")
    return pagedb.page_entries(wiki_dir, prefix + "/" if prefix else "")


def _file_rows(wiki_dir, under):
    """平文ファイル側の一覧（本文は読まない）。タイトルはDBにあれば添える。

    編集の道具（ページ選択ダイアログ・編集画面の一覧）は**平文ファイル**を扱う。
    取り込む前のページも出す必要があるので、こちらだけ出どころが違う。"""
    root = os.path.join(wiki_dir, (under or "").strip("/"))
    titles = {r["subpath"]: r.get("title") or ""
              for r in _rows_under(wiki_dir, under)}
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in sorted(dirnames)
                       if not d.startswith((FARM_PREFIX, SYSTEM_PREFIX))]
        for fname in sorted(filenames):
            stem, ext = os.path.splitext(fname)
            if ext not in PAGE_EXTS or stem.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
                continue
            target = os.path.join(dirpath, stem)
            subpath = os.path.relpath(target, wiki_dir).replace(os.sep, "/")
            if subpath in found:
                continue  # 同じ名前の .txt と .md は1ページ（閲覧時も .txt が優先）
            found[subpath] = {"subpath": subpath, "title": titles.get(subpath, ""), "ext": ext}
    return [found[s] for s in sorted(found)]


def _rows(wiki_dir, under, source):
    if source == SOURCE_FILES:
        return _file_rows(wiki_dir, under)
    return _rows_under(wiki_dir, under)


# ---- 一覧を得る4つの道 -------------------------------------------------------

def walk(wiki_dir, under="", need=PAGE_READ, source=SOURCE_PUBLISHED,
         privilege=None, config=None):
    """`under` の下にあるページを、名前順ですべて返す。

    `under` は実体パスの接頭辞（`"Tech"`）。空ならWiki全体。
    フォルダそのものは返さない（**ページだけ**が並ぶ）。"""
    judge = judge_for(wiki_dir, privilege)
    items = _by_pagepath([_item_of_row(row) for row in _rows(wiki_dir, under, source)])
    return _judged(items, judge, need)


def scandir(wiki_dir, under="", need=PAGE_READ, source=SOURCE_PUBLISHED,
            privilege=None, config=None):
    """`under` の**1階層下**を返す（`os.scandir` にあたる）。

    **通り道でしかないフォルダも返す**（そこ自身にページは無いが、下にはある）。
    その場合は `exists=False`・`title=""` で、`has_children` が真になる。
    フォルダの入口（`Tech/index`）は、ページ `Tech` として1件にまとまる。

    **`has_children` は「その人に見えるページが下にあるか」**である（権限を
    通したあとで数える）。下が全部隠れたフォルダを「開けるもの」として出すと、
    開いても何も無い行が並ぶことになる。同じ理由で、**自分のページを持たない
    通り道のフォルダは、下に見えるページが1枚も無ければ返さない**。

    見せかたの都合（自分自身を落とす・`index` を出すかどうか）は呼ぶ側で決める。"""
    judge = judge_for(wiki_dir, privilege)
    prefix = (under or "").strip("/")
    head = prefix + "/" if prefix else ""
    rows = {row["subpath"]: row for row in _rows(wiki_dir, under, source)}

    items, seen = [], set()
    for subpath in sorted(rows):
        rest = subpath[len(head):]
        name = rest.split("/", 1)[0]
        if not name or name in seen:
            continue
        seen.add(name)
        own = head + name                      # 直下の実体（ページそのもの）
        entry = entry_subpath_of(own)          # フォルダの入口（own + "/index"）
        row = rows.get(own) or rows.get(entry)
        # 下にあるページのうち、**その人に見えるもの**だけを数える
        deeper = [s for s in rows if s.startswith(own + "/") and s != entry]
        visible = any(_allowed(judge.check(pagepath_of_subpath(s)), need) for s in deeper)
        if row is None:
            # 通り道でしかないフォルダ。ページとしては開けないので、下に
            # 見えるページが無ければ出さない（開いても空の行になるため）
            if not visible:
                continue
            items.append(PageItem(name=name, pagepath=pagepath_of_subpath(own),
                                  subpath=own, exists=False, has_children=True))
            continue
        items.append(_item_of_row(row, name=name, has_children=visible))
    return _judged(_by_pagepath(items), judge, need)


def glob(wiki_dir, pattern, need=PAGE_READ, source=SOURCE_PUBLISHED,
         privilege=None, config=None):
    """ページパスがパターンに当たるものを返す。

    **照合は検索（`search.name_matches`）と同じ `fnmatch`** で、大文字小文字は
    区別しない。**`*` は `/` にも当たる**ので、`"Tech/*"` は孫まで拾う
    （Wiki設計者の選択、2026-09-17。権限の記録（`config/privileges`）は前方一致・
    後方一致だけという別の流儀だが、あちらは保存時に並べ替える都合によるもの）。"""
    judge = judge_for(wiki_dir, privilege)
    lowered = (pattern or "").lower()
    items = [_item_of_row(row) for row in _rows(wiki_dir, "", source)]
    items = [i for i in items if fnmatch.fnmatchcase(i.pagepath.lower(), lowered)]
    return _judged(_by_pagepath(items), judge, need)


def filter(wiki_dir, names, need=PAGE_READ, by="pagepath",  # noqa: A001
           source=SOURCE_PUBLISHED, privilege=None, config=None):
    """**手元にある名前の並び**を絞り、`PageItem` にして返す（並び順はそのまま）。

    更新順・アクセスの多い順・検索の候補のように、**ディレクトリの列挙ではない
    一覧**のための道。名前の出どころは呼ぶ側が自由に決められる。

        by="pagepath"   URL上のページパス（`#popular` のログなど）
        by="subpath"    実体パス（`pagedb` から取った並びなど）

    DBに無い名前は、**まだ無いページ**として `exists=False` で返る（権限は
    ページパスに対して判定するので、規則があれば絞られる）。同じ名前が2度
    現れたら1度だけ返す。"""
    judge = judge_for(wiki_dir, privilege)
    rows = {row["subpath"]: row for row in _rows(wiki_dir, "", source)}

    items, seen = [], set()
    for raw in names:
        name = (raw or "").strip("/")
        if by == "subpath":
            subpath = name
        else:
            subpath = name if name in rows else entry_subpath_of(name)
            if subpath not in rows:
                subpath = name or INDEX_NAME
        if subpath in seen:
            continue
        seen.add(subpath)
        row = rows.get(subpath)
        if row is not None:
            items.append(_item_of_row(row))
        else:
            items.append(PageItem(name=subpath.rsplit("/", 1)[-1],
                                  pagepath=pagepath_of_subpath(subpath),
                                  subpath=subpath, exists=False))
    return _judged(items, judge, need)
