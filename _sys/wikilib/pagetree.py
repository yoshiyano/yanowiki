"""ページ一覧のツリー（ページ選択ダイアログが読むJSON）。

名前は wiki/ の中身をそのまま読んで採る。ページパスから組み立て直すと、
大文字小文字が実ファイルとずれるおそれがあるため。
"""
import json
import os

from bottle import HTTPResponse

from wikilib.attach import has_attach_files
from wikilib.draft import drafted_subpaths
from wikilib.paths import (
    FARM_PREFIX, INDEX_NAME, SYSTEM_PREFIX, entry_subpath_of, markup_name_for,
    pagepath_of_subpath,
)
from wikilib.pukiwiki import HEADING_ANCHOR_RE

PAGETREE_TITLE_MAX = 30       # 浅い階層（単体のフォルダ・ファイル）に許す文字数
PAGETREE_TITLE_MIN = 10       # どれだけ深くなっても、これ以下には縮めない
PAGETREE_TITLE_PER_DEPTH = 4  # 1階層深くなるごとに削る文字数
PAGETREE_DIR_PENALTY = 8      # フォルダはページより短くする分
PAGETREE_TITLE_BYTES = 4096   # タイトルを探すために読む先頭部分の大きさ


def pagetree_title_limit(depth, is_dir):
    """その行に許すタイトルの文字数を返す。

    深い階層ほど字下げで横幅が食われるため短くする。
    同じ深さならフォルダを短めにして、そのぶんをページに回す
    （選ぶ対象はページなので、ページ名のほうを読めるようにしたい）。"""
    limit = PAGETREE_TITLE_MAX - max(0, depth - 1) * PAGETREE_TITLE_PER_DEPTH
    if is_dir:
        limit -= PAGETREE_DIR_PENALTY
    return max(PAGETREE_TITLE_MIN, limit)


def page_title_of(wiki_dir, subpath, path):
    """一覧に添えるタイトル。**公開されたもの**（DBに取り出し済みの見出し）を使う。

    DBにまだ無い（取り込む前・作り直した直後）ときだけ、平文ファイルの先頭を
    読んで拾う。一覧に出す名前が、表示したページの見出しと食い違わないようにするため。"""
    from wikilib.pagedb import load_page_info

    info = load_page_info(wiki_dir, subpath)
    if info is not None and info["title"]:
        return info["title"]
    return read_page_title(path) if path else ""


def read_page_title(path):
    """ページの先頭にある最上位の見出しをタイトルとして拾う。無ければ空文字列。

    探す目印はその記法のもので、Markdownなら `# `、PukiWiki記法なら `*`。
    記法を見ずに両方を探すと、Markdownの `*強調*` で始まる行を
    見出しと取り違えてしまう。

    一覧に添えるだけなので、ファイル全体は読まずに先頭だけを見る
    （ページ数が増えても、ツリーの組み立てが重くならないようにするため）。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(PAGETREE_TITLE_BYTES)
    except OSError:
        return ""
    pukiwiki_page = markup_name_for(os.path.splitext(path)[1]) == "pukiwiki"
    for line in head.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if pukiwiki_page:
            if stripped.startswith("*"):
                return HEADING_ANCHOR_RE.sub("", stripped.lstrip("*")).strip()
        elif stripped.startswith("# "):
            return stripped[2:].strip()
        break  # 先頭が見出しでなければタイトルは無い扱い
    return ""


def shorten_title(title, limit):
    """長いタイトルを詰める。切ったことが分かるよう末尾に省略記号を付ける。"""
    title = " ".join(title.split())  # 改行や連続する空白は1つに畳む
    if len(title) <= limit:
        return title
    return title[:limit - 1].rstrip() + "…"


def sort_key(node):
    """並び順: そのフォルダ自身のページ（index）→ フォルダ → ページ。
    いずれも大小文字を無視した名前順にする。

    素の sorted() だと大文字で始まる名前がすべて先に来てしまい
    （"UsageGuide" より "mainmenu" が後ろ）、目で追いにくい。
    フォルダとページも混ざると構造が読み取りにくいので、群に分けている。"""
    if node["name"] == INDEX_NAME:
        group = 0
    elif node["kind"] == "dir":
        group = 1
    else:
        group = 2
    return (group, node["name"].lower(), node["name"])


def new_page_node(subpath, name):
    """まだ実体の無いページの項目。"""
    return {"name": name, "kind": "page", "pagepath": pagepath_of_subpath(subpath),
            "subpath": subpath, "has_file": False, "children": [], "raw_title": ""}


def new_dir_node(parts):
    """まだ実体の無いフォルダの項目。中には空の index を1つ置く
    （実体のあるフォルダを walk が組むときと形をそろえるため）。"""
    sub = "/".join(parts)
    return {"name": parts[-1], "kind": "dir", "pagepath": sub, "subpath": sub,
            "has_file": True, "raw_title": "",
            "children": [new_page_node(entry_subpath_of(sub), INDEX_NAME)]}


def add_drafted_pages(root, drafts):
    """書きかけだけがあるページを木に足す。足したら True を返す。

    **書きかけを預かっている＝そのページは作りかけ**である。保存を終えていない
    新規ページは wiki/ に実体が無いので、フォルダを走査するだけでは一覧に出て
    こない。出てこないと、別のページを見にいったあとで**どこに戻れば続きを
    書けるのかが分からなくなる**（書きかけは残っているのに辿り着けない）。

    実体はまだ無いので has_file は偽。一覧では「まだ無いページ」の見た目に
    「書きかけあり」の印が重なる。"""
    added = False
    for subpath in sorted(drafts):
        parts = subpath.split("/")
        node = root
        for depth, part in enumerate(parts[:-1]):
            found = next((c for c in node["children"]
                          if c["kind"] == "dir" and c["name"] == part), None)
            if found is None:
                found = new_dir_node(parts[:depth + 1])
                node["children"].append(found)
                added = True
            node = found
        name = parts[-1]
        if any(c["kind"] == "page" and c["name"] == name for c in node["children"]):
            continue  # 実体があるページ（や walk が置いた index）はそのまま
        node["children"].append(new_page_node(subpath, name))
        added = True
    return added


TOP_PAGE_LABEL = "(TopPage)"  # ファイル一覧（filesui）と共通の表記


def with_top_page_row(tree):
    """木に、トップページ（`/`）の行を先頭へ差し込む。

    どのフォルダも自分の行が中の `index` を兼ねるが、木のいちばん外側
    （ルート）は行そのものが無いため、この仕組みに乗れない。ルートの
    子にある `index`（トップページ）を取り出し、`TOP_PAGE_LABEL` という
    名前・タイトルの行に差し替えて先頭に置く（タイトルも揃えるのは、
    実際のページタイトルが出ると特別扱いだと分かりにくくなるため）。

    editor.build_page_list_html（ページ選択ダイアログ）・
    backupui.build_backup_tree（バックアップ管理画面）の両方が使う共通処理
    （2026-08-29、後者に同じ手当てを足したときにここへ移した）。"""
    children = list(tree.get("children") or [])
    index_pos = next((i for i, c in enumerate(children) if c.get("name") == INDEX_NAME), None)
    if index_pos is None:
        return tree
    top_row = dict(children.pop(index_pos))
    top_row["name"] = TOP_PAGE_LABEL
    top_row["title"] = TOP_PAGE_LABEL
    tree = dict(tree)
    tree["children"] = [top_row] + children
    return tree


def sort_tree(node):
    """木全体を並べ直す。書きかけを足したあとに使う。"""
    node["children"].sort(key=sort_key)
    for child in node["children"]:
        sort_tree(child)


def mark_drafts(node, drafts):
    """一時保存を預かっているページに `draft` を立てる。

    実体があるページ（保存済みだが、そのあと一時保存もされているもの）と、
    `add_drafted_pages` が足した実体の無いページの両方をここでまとめて見る。
    どちらも同じ意味（**本保存されていない書きかけがある**）なので、
    木の組み立てかたが違っても印は1か所の判定だけで済む。"""
    node["draft"] = node["subpath"] in drafts
    for child in node["children"]:
        mark_drafts(child, drafts)


def build_page_tree(wiki_dir):
    """全ページを、実体のファイル構成そのままの木にして返す（ページ選択ダイアログ用）。

    **フォルダの中の index も1つの項目として出す。** 添付ファイルの置き場所は
    実体のパス（subpath）で決まるため、"/Tech" が Tech/index を指していることが
    木を見て分かるようにしている（フォルダと index をまとめてしまうと、
    どこへ置かれるのかが見えない）。

    ノードは {name, kind, pagepath, subpath, has_file, draft, children}。
    kind は "dir"（階層。それ自体はページではない）か "page"。

    **`ext`（`.txt`/`.md`）は実体があるページだけに付く。** 記法
    （PukiWiki/Markdown）ごとに一覧の見せかた（ファイル名／タイトル優先）を
    変える設定（`wikiconfig.listname_for`）の元になる（Wiki設計者の指示、
    2026-09-18）。この関数自体は設定を知らないので、ここでは拡張子を
    運ぶだけにしてある——見せかたを決めるのは呼び出し側（`editor.
    build_page_list_html`）の役目。

    **`has_file` は「平文ファイルがあるか」で、「公開されているか」ではない。**
    この木は編集の道具（ページ選択ダイアログ・編集画面のページ一覧）が読むもので、
    編集が扱うのは平文ファイルのほうだから、ここも平文にそろえてある。公開の
    有無を表す `published`（バックアップ管理画面のツリー）とは別のものなので、
    同じ `exists` という名前を使わずに区別している。

    **`draft` は「一時保存を預かっているか」。** `has_file` の有無に関わらず
    立つ（実体があるページでも、そのあと一時保存されていれば真になる）。
    編集画面のページ一覧が「書きかけ」の印を出すのに使う。

    **名前は wiki/ の中身をそのまま読んで採る。** ページパスから組み立て直すと、
    大文字小文字が実ファイルとずれるおそれがあるため。

    **中身の何も無いフォルダは出さない**（Wiki設計者の指示、2026-09-25）。
    ページも下位のフォルダも無く、入口（`X/index`）に添付も無いフォルダは、
    開いても空の `index` が1つ見えるだけで、読み手には何のことか分からない。
    消すのは取り込み（`pagesync.prune_empty_folders`）の役目で、ここは表示から
    外すだけにしてある（一覧は読むだけの処理なので、ファイルには触らない）。
    入口に添付があるフォルダは、先に添付だけ置いておく使いかたなので出す。

    実体がまだ無くても、**書きかけを預かっているページは出す**
    （add_drafted_pages）。"""

    def walk(directory, parts):
        try:
            entries = sorted(os.listdir(directory))
        except OSError:
            entries = []

        children, seen = [], set()
        for entry in entries:
            # ページ名のルールどおり "=" や "." で始まるものは対象外
            if entry.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
                continue
            path = os.path.join(directory, entry)
            if os.path.isdir(path):
                child = walk(path, parts + [entry])
                if child is not None:
                    children.append(child)
                continue
            stem, ext = os.path.splitext(entry)
            # 同じ名前の .txt と .md は1つのページ（閲覧時も .txt が優先されるだけ）
            if ext not in (".txt", ".md") or stem in seen:
                continue
            seen.add(stem)
            sub = "/".join(parts + [stem])
            children.append({
                "name": stem, "kind": "page", "pagepath": pagepath_of_subpath(sub),
                "subpath": sub, "has_file": True, "children": [], "ext": ext,
                "raw_title": page_title_of(wiki_dir, sub, path),
            })

        if parts and not children and not has_attach_files(
                wiki_dir, entry_subpath_of("/".join(parts))):
            return None  # 中身の何も無いフォルダは出さない（docstring参照）

        if INDEX_NAME not in seen:
            # ページの実体がまだ無いフォルダにも index を出す。
            # 「先に添付だけ置いておく」ができるようにするため。
            sub = entry_subpath_of("/".join(parts))
            children.append({
                "name": INDEX_NAME, "kind": "page", "pagepath": pagepath_of_subpath(sub),
                "subpath": sub, "has_file": False, "children": [],
            })

        children.sort(key=sort_key)
        # フォルダの見出しには、その中の index のタイトルを借りる
        # （"Tech" だけでは中身が分からないため）
        own = next((c for c in children if c["name"] == INDEX_NAME), None)
        return {
            "name": parts[-1] if parts else "",
            "kind": "dir",
            "pagepath": "/".join(parts),
            "subpath": "/".join(parts),
            "has_file": True,
            "children": children,
            "raw_title": own.get("raw_title", "") if own else "",
        }

    def apply_titles(node, depth):
        """タイトルを深さに応じて詰める。木を組み終えてから一度に行う
        （フォルダは中の index を見るので、子が揃ってからでないと決まらない）。"""
        limit = pagetree_title_limit(depth, node["kind"] == "dir")
        node["title"] = shorten_title(node.pop("raw_title", ""), limit)
        for child in node["children"]:
            apply_titles(child, depth + 1)
        return node

    tree = walk(wiki_dir, [])
    drafts = drafted_subpaths(wiki_dir)
    # 書きかけしか無いページも一覧に出す。並び順は足してから決め直す
    if add_drafted_pages(tree, drafts):
        sort_tree(tree)
    mark_drafts(tree, drafts)
    return apply_titles(tree, 0)


def serve_page_tree(wiki_dir):
    """ページ一覧をツリー構造のJSONで返す。ページ選択ダイアログが読む。"""
    body = json.dumps(build_page_tree(wiki_dir), ensure_ascii=False)
    return HTTPResponse(body=body, status=200,
                        content_type="application/json; charset=utf-8")
