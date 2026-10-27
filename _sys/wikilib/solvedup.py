"""同じ名前の `.txt` と `.md` を整理する画面（`/.solveDupPage/<ページ名>`）。

ページのタイトル右端の info に出る警告（`wikilib.pagenotice`）から開く。2つのファイルの
プレビューを左右に並べ、**どちらを採用するか**を選んでもらう。採用しなかったほうは、
名前に `_bak` を付けたページ（`A.md` → `A_bak.md`）として残し、閲覧も編集もできる。
詳しい説明は `UsageGuide/Edit/Duplicate`。画面の先頭からつなぐ。

## 既存の名前の変更（`pagerename`）は使わない

`pagerename.rename_page` はページ名を単位にするので、同じ名前の2つのうち `.txt` 側を動かし、
**添付・履歴・書きかけ・DBの行・アクセス制限の記録まで新しい名前へ付け替えてしまう**。
今回は片方のファイルだけを `_bak` にして、残すほうは今の記録のままにしたいので、ここで
専用に行う。

    A.txt（残す）  そのまま。DBの行は、残したファイルの内容に合わせて入れ直す
    A.md（退ける） A_bak.md へ動かす。**新しいページとして取り込む**（差分は新しく始まる）
    添付           2つのファイルは同じ添付の置き場所を使っていた。**ファイルごとに、どちらの
                   ページに持たせるかを選ぶ**（両方・.txt 側・.md 側。下の「添付の移動先」）
    履歴・書きかけ  A のまま（A_bak には引き継がない）

## 添付の移動先（ファイルごと）

画面の「.txt 側」「.md 側」は、そのファイルのページ。**採用したファイルのページが元の名前
（`A`）、採用しなかったほうが `A_bak`** になるので、どちらを採用するかで、どちらの側が
どちらのページになるかが決まる。

    両方     A に残したまま、A_bak へ写す
    .txt 側  .txt のファイルのページだけに持たせる（A なら残す、A_bak なら移す）
    .md 側   .md のファイルのページだけに持たせる（同上）

## アクセス制限は触らない（案内だけ）

`A_bak` は新しい名前なので、**`A` だけに効いていた制限が当たらず、整理した瞬間から、制限が
外れる（緩くなる）可能性がある**。完全一致（`A`）だけでなく、後方一致（`*Secret` は `MySecret`
に当たるが `MySecret_bak` には当たらない）でも起きる。ここでは**書き換えず**、元のページと
`_bak` に当たっている指定を並べて見せ、違うときは目立つ形で知らせ、**アクセス制限の画面
（`/.admin/privileges`）へ、この画面を残したまま別ウィンドウで移れるリンク**を付ける。制限の
管理は、開いた先の画面に任せる（Wiki設計者の指示、2026-10-13）。`#readauth`・`#writeauth` の
記録は内容（許可者）を出さず、**どちらのファイルの本文に何が書かれているか**だけを示す
（`.txt` と `.md` の本文は別なので、採用するほうで整理後の制限が変わる）。見つけかたは
`updatepageauth` と同じ——本文の字面ではなく、プレビューと同じ描画で `context.used_plugins`
を見る（囲みコードの中などを読み違えない）。

## 名前の空きと、その場の確かめ

`A_bak` が使えなければ（ページ・フォルダ・添付・書きかけ・履歴・アクセス制限の行のどれかが
すでにある）`A_bak2`・`A_bak3` …と空きを探す。上書きはしない。

アクセス制限の許可者（ログインID・グループ名）の一覧は、**管理者と助手にだけ**見せる
（`/.admin/privileges` が管理者向けに持つ情報なので、編集の権限だけで見せない）。それ以外には
「何件の指定があるか」だけを出す。

画面を開いてから押すまでの間にファイルが書き換えられていたら、断る（本文のハッシュを
フォームに持たせて照合する）。権限は、元のページの編集（W）と、`_bak` のページの編集（W）の
両方を見る。**編集の権限が無い人には、取り込み前のほうの中身（プレビュー）も見せない**
（読むだけの人に、公開前の内容が見えてしまうため）。

助手の操作は `page.dupsolve` で記録する。記録だけで、戻す操作は無い。

## 同じ名前のファイルとフォルダ（`X.md` と `X/`）

フォルダがあると `X/index` が読まれ、`X.md` は読まれない（`paths.shadowed_twin`）。これも重複として
扱い、`X.拡張子` と `X/index.拡張子` のどちらを採用するかを選んでもらう（`solve_folder`）。

    X/index を採用   X.md を X_bak.md へ動かす
    X.md を採用      X/index.md を X_bak.md へ動かし、X.md を X/index.md へ動かす（ページ名 X は変わらない）
    X/index が無い   X.md を X/index.md へ動かすだけ（_bak は作らない）

**`.txt` と `.md` の重複と違い、2つのファイルは実体パスが別で、添付・履歴・書きかけ・DBの行も
もともと別々**にある。そこで、どれもファイルに付いたまま動かす（添付の移動先は選ばせない。
設計者の判断、2026-10-19）。添付は置き場所の直下のファイルだけを動かす——`attach/X/` の下には、
`X/index` や下位ページの添付のフォルダが並んでいるため。

重複が重なっているときは1段ずつ整理する（`pagenotice.duplicate_stage`。設計者の判断、2026-10-19）。
`X.txt` と `X.md` の重複（ページ名 `X` で開くとフォルダの入口が開くので、ほかの道が無い）も、
この画面の1段めとして `.txt` と `.md` の整理で片付ける。そのときは `X` を取り込まない
（取り込みはページ名で行うので、フォルダの入口を読んでしまう）。
"""
import hashlib
import os
import shutil
import time
from html import escape
from urllib.parse import quote as urlquote

from bottle import request

from wikilib import auth, operations, pagedb, privilege_records, stafflog
from wikilib.attach import attach_dir_for
from wikilib.backup import move_backups
from wikilib.draft import draft_path, move_draft
from wikilib.pagenotice import (
    DUPLICATE_GUIDE_PAGE, STAGE_EXT, STAGE_FOLDER, duplicate_stage, guide_url,
)
from wikilib.pagesync import adopt_page, sync_page
from wikilib.paths import (
    ATTACH_URLPATH, IMAGE_EXTS, INDEX_NAME, PAGE_EXTS, PRIVILEGES_URLPATH, SOLVEDUP_URLPATH,
    farm_plugin_dir, is_valid_pagepath, markup_format_for, page_file_path, page_files,
    pagepath_of_subpath, resolve_page_ref, shadowed_twin,
)
from wikilib.plugins import build_markdown_renderer, plugin_script_urls, plugin_style_urls
from wikilib.updatepageauth import PLUGIN_OF_KIND

# 添付1件の移動先（画面の「両方」「.txt 側」「.md 側」）。値は拡張子から付けた名前
DEST_BOTH, DEST_TXT, DEST_MD = "both", "txt", "md"
DESTS = (DEST_BOTH, DEST_TXT, DEST_MD)
DEST_EXT = {DEST_TXT: ".txt", DEST_MD: ".md"}
# 移動先から決まる、添付1件の扱い。KEEP=元のページだけに残す、MOVE=`_bak` へ移す、
# BOTH=元のページに残したまま `_bak` へ写す
ATTACH_KEEP, ATTACH_MOVE, ATTACH_BOTH = "keep", "move", "both"
BAK_SUFFIX = "_bak"
MAX_BAK_TRIES = 99  # `_bak`・`_bak2` … `_bak99`。ここまで空きが無ければ諦める
# ファイルとフォルダの重複で、どちらを採用するか（画面のボタンの値・フォームの `hash<値>`）。
# FILE=フォルダに隠れたファイル `X.拡張子`、FOLDER=フォルダの入口 `X/index.拡張子`
SIDE_FILE, SIDE_FOLDER = "file", "folder"
# 案内ページ（`DUPLICATE_GUIDE_PAGE`）の、ファイルとフォルダの重複の見出し（画面からその節へつなぐ）
FOLDER_GUIDE_HEADING = "同じ名前のファイルとフォルダがあるとき"


# ---- 調べる ------------------------------------------------------------------

def _file_hash(raw):
    return hashlib.sha1(raw).hexdigest()[:12]


def _bak_name_free(wiki_dir, subpath, rows):
    """`subpath` を `_bak` のページの名前に使ってよいか。ページ・フォルダ・添付・書きかけ・
    履歴・DBの行・手で書いたアクセス制限の行の、どれにも当たっていなければ真。"""
    if page_files(os.path.join(wiki_dir, subpath)) or os.path.exists(os.path.join(wiki_dir, subpath)):
        return False
    attach = attach_dir_for(wiki_dir, subpath)
    if attach is not None and os.path.exists(attach):
        return False
    draft = draft_path(wiki_dir, subpath)
    if draft is not None and os.path.exists(draft):
        return False
    if pagedb.load_page(wiki_dir, subpath) is not None:
        return False
    if pagedb.first_backup_stamp(wiki_dir, subpath) is not None:
        return False
    page = pagepath_of_subpath(subpath)
    return not any(e["page"] == page for e in rows)


def bak_subpath(wiki_dir, subpath):
    """`_bak` のページの実体パス。空きが無ければ None。"""
    rows = privilege_records.load(wiki_dir)
    for n in range(1, MAX_BAK_TRIES + 1):
        candidate = subpath + BAK_SUFFIX + ("" if n == 1 else str(n))
        if _bak_name_free(wiki_dir, candidate, rows):
            return candidate
    return None


def _read_file(path, key, subpath, name=None):
    """ページのファイル1つを読む。読めなければ None。

    `key` は画面とフォームでそのファイルを指す名前（`.txt` と `.md` の重複では拡張子、
    ファイルとフォルダの重複では `SIDE_*`）。`subpath` はそのファイルの実体パス（添付の置き場所）。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        stat = os.stat(path)
    except OSError:
        return None
    return {
        "key": key, "subpath": subpath,
        "ext": os.path.splitext(path)[1], "name": name or os.path.basename(path), "path": path,
        "raw": raw, "body": raw.decode("utf-8", errors="replace"),
        "hash": _file_hash(raw), "size": len(raw), "mtime": stat.st_mtime,
    }


def inspect_duplicate(wiki_dir, subpath):
    """重複の状態を調べる。同じ名前のファイルが2つなければ None。

    戻り値は `{"stage", "subpath", "pagepath", "files", "shown_ext", "bak_subpath", "shadowed"}`。
    `files` は閲覧で読まれる順（`.txt` が先）の `{"key", "subpath", "ext", "name", "path", "raw",
    "body", "hash", "size", "mtime"}`（`key` は拡張子）。`shown_ext` は、いま画面に出ている
    （取り込み済みの）内容の拡張子（無ければ None）。`shadowed` は、同じ名前のフォルダがあって
    どちらのファイルも読まれていないか（冒頭の「同じ名前のファイルとフォルダ」）。"""
    paths = page_files(os.path.join(wiki_dir, subpath))
    if len(paths) < 2:
        return None
    files = []
    for path in paths:
        f = _read_file(path, os.path.splitext(path)[1], subpath)
        if f is None:
            return None
        files.append(f)
    shadowed = os.path.isdir(os.path.join(wiki_dir, subpath))
    row = pagedb.load_page(wiki_dir, subpath)
    shown_ext = os.path.splitext(row["path"])[1] if row is not None and not shadowed else None
    return {"stage": STAGE_EXT, "subpath": subpath, "pagepath": pagepath_of_subpath(subpath),
            "files": files, "shown_ext": shown_ext, "bak_subpath": bak_subpath(wiki_dir, subpath),
            "shadowed": shadowed}


def _relative_name(subpath, path):
    """画面に出すファイル名。フォルダの入口は、フォルダの名前を付けて `X/index.md` と書く。"""
    name = os.path.basename(path)
    return os.path.basename(os.path.dirname(subpath)) + "/" + name \
        if os.path.basename(subpath) == INDEX_NAME else name


def inspect_folder(wiki_dir, subpath):
    """フォルダの入口 `subpath`（`X/index`）と、同じ名前のファイル `X.拡張子` の重複を調べる。
    無ければ（どちらかに `.txt` と `.md` の重複が残っていても）None。

    戻り値は `inspect_duplicate` と同じ形で、`stage` は `STAGE_FOLDER`、`twin` は `X`。
    `files` は、入口のファイル（`key` は `SIDE_FOLDER`。無ければ入らない）、隠れたファイル
    （`SIDE_FILE`）の順。入口が無ければ `bak_subpath` は None（`_bak` は作らない）。"""
    twin = shadowed_twin(wiki_dir, subpath)
    if twin is None:
        return None
    entry_paths = page_files(os.path.join(wiki_dir, subpath))
    twin_paths = page_files(os.path.join(wiki_dir, twin))
    if len(entry_paths) > 1 or len(twin_paths) != 1:
        return None
    files = []
    for path, key, owner in ([(p, SIDE_FOLDER, subpath) for p in entry_paths]
                             + [(twin_paths[0], SIDE_FILE, twin)]):
        f = _read_file(path, key, owner, _relative_name(owner, path))
        if f is None:
            return None
        f["attach_count"] = len(attachment_files(wiki_dir, owner))
        files.append(f)
    return {"stage": STAGE_FOLDER, "subpath": subpath, "twin": twin,
            "pagepath": pagepath_of_subpath(subpath), "files": files, "shown_ext": None,
            "bak_subpath": bak_subpath(wiki_dir, twin) if entry_paths else None,
            "shadowed": False}


# ---- アクセス制限（見せるだけ。書き換えない） --------------------------------

def access_report(wiki_dir, pagepath, new_pagepath):
    """元のページと `_bak` のページに当たっているアクセス制限の指定を並べる（読むだけ）。

    `{"rules", "bak_rules", "differs", "plugin"}`。`rules`・`bak_rules` は
    `auth.page_privilege_rules` の答え（`new_pagepath` が無ければ `bak_rules` は None）。
    `differs` は、元のページに指定があるのに、`_bak` に当たる許可者が違う（指定が無い）種類
    （"read"・"write"）。`_bak` のほうが厳しいだけの場合は含めない。`plugin` は、
    `#readauth`・`#writeauth` の記録がある種類（"R"・"W"）。内容は出さない。"""
    rows = privilege_records.load(wiki_dir)
    mine = auth.page_privilege_rules(wiki_dir, pagepath, rows)
    bak = (auth.page_privilege_rules(wiki_dir, new_pagepath, rows)
           if new_pagepath is not None else None)
    differs = []
    if bak is not None:
        for key in ("read", "write"):
            if mine[key] is not None and (bak[key] is None or bak[key]["who"] != mine[key]["who"]):
                differs.append(key)
    plugin = sorted({e["kind"] for e in privilege_records.load_plugin(wiki_dir)
                     if e["page"] == pagepath})
    return {"rules": mine, "bak_rules": bak, "differs": differs, "plugin": plugin}


def describe_state(wiki_dir, plan):
    """採用を選ぶ前に見せる、添付とアクセス制限の状態。`{"attachments", "access"}`。"""
    new_pagepath = pagepath_of_subpath(plan["bak_subpath"]) if plan["bak_subpath"] else None
    return {"attachments": attachment_files(wiki_dir, plan["subpath"]),
            "access": access_report(wiki_dir, plan["pagepath"], new_pagepath)}


# ---- 整理する ----------------------------------------------------------------

def attach_modes(keep_ext, dests, names):
    """添付ごとの扱い `{名前: ATTACH_*}`。`dests` は `{名前: 移動先}`（無い名前は「両方」）。

    「.txt 側」「.md 側」は、そのファイルのページ。そのファイルを採用するなら元のページ、
    しないなら `_bak` のページになる。"""
    modes = {}
    for name in names:
        dest = (dests or {}).get(name, DEST_BOTH)
        if dest == DEST_BOTH:
            modes[name] = ATTACH_BOTH
        else:
            modes[name] = ATTACH_KEEP if DEST_EXT[dest] == keep_ext else ATTACH_MOVE
    return modes


def solve(wiki_dir, config, subpath, keep_ext, hashes, uid, dests=None):
    """`keep_ext`（`.txt` か `.md`）を採用し、もう一方を `_bak` のページとして残す。

    `hashes` は画面を開いたときの `{拡張子: ハッシュ}`。`uid` は操作している人
    （`_bak` のページを編集できるかの確認に使う）。`dests` は添付ごとの移動先
    `{ファイル名: DEST_*}`（省略・無い名前は「両方」）。**アクセス制限の記録は書き換えない**。

    戻り値は `(成功か, 知らせの文, 結果)`。結果は成功のときだけ
    `{"kept", "bak_name", "bak_pagepath", "attach", "access", "synced"}`。`attach` は
    `{ATTACH_BOTH: 件数, ATTACH_KEEP: 件数, ATTACH_MOVE: 件数}`、`access` は
    `access_report` の答え（整理のあとの状態）。
    **どこで失敗しても、ファイルは動かさないか、動かす前の状態へ戻す。**"""
    plan = inspect_duplicate(wiki_dir, subpath)
    if plan is None:
        return False, "同じ名前の .txt と .md は、もうありません。ページを開き直してください。", None
    by_ext = {f["ext"]: f for f in plan["files"]}
    if keep_ext not in by_ext:
        return False, "採用するファイルを選んでください。", None
    if any(hashes.get(f["ext"]) != f["hash"] for f in plan["files"]):
        return False, ("開いてから、ページのファイルが書き換えられました。"
                       "内容を確かめ直してください。"), None
    if any(d not in DESTS for d in (dests or {}).values()):
        return False, "添付ファイルの移動先を選び直してください。", None
    keep = by_ext[keep_ext]
    drop = next(f for f in plan["files"] if f["ext"] != keep_ext)
    new_subpath = plan["bak_subpath"]
    if new_subpath is None:
        return False, "_bak の名前に空きがありません（_bak〜_bak{}）。".format(MAX_BAK_TRIES), None
    new_pagepath = pagepath_of_subpath(new_subpath)
    busy = operations.overlapping(wiki_dir, (subpath, new_subpath))
    if busy is not None:
        return False, operations.busy_message(busy), None
    new_path = page_file_path(wiki_dir, new_subpath, drop["ext"])
    if new_path is None:
        return False, "«/{}» の置き場所を決められません。".format(new_pagepath), None
    # この人が _bak のページを編集できなければ、整理しない（作っても直せない）。
    # アクセス制限は書き換えないので、いま当たっている指定のまま見る
    if auth.page_privilege(wiki_dir, uid).check(new_pagepath) != auth.PAGE_WRITE:
        return False, "«/{}» を編集する権限がありません。".format(new_pagepath), None

    # 1. 添付を、ファイルごとの移動先に従って動かす。_bak 側の置き場所はまだ無いので、
    #    失敗したら置き場所ごと戻せる
    modes = attach_modes(keep_ext, dests,
                         [name for name, _size in attachment_files(wiki_dir, subpath)])
    try:
        done = _transfer_attachments(wiki_dir, subpath, new_subpath, modes)
    except OSError:
        return False, "添付ファイルを動かせませんでした。", None

    # 2. 退けるほうのファイルを動かす（直前にもう一度、中身が同じかを見る）
    try:
        with open(drop["path"], "rb") as f:
            same = _file_hash(f.read()) == drop["hash"]
        if not same or os.path.exists(new_path):
            raise OSError("changed")
        os.replace(drop["path"], new_path)
    except OSError:
        _undo_attachments(wiki_dir, subpath, new_subpath, done)
        return False, "ファイルを動かせませんでした（途中で書き換えられた可能性があります）。", None
    if any(mode == ATTACH_MOVE for _name, mode in done):
        _remove_empty_dir(attach_dir_for(wiki_dir, subpath))

    # 3. DBを合わせる。ここで失敗しても、ファイルは動いている。取り込み（1時間ごと・
    #    updatepage）が同じことをするので、整理自体は成功として扱い、知らせる
    synced = True
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir))
    with stafflog.quiet():  # 保存の記録は、呼び出し側の1件にまとめる
        # フォルダに隠れたファイル（冒頭の「同じ名前のファイルとフォルダ」）は取り込まない。
        # 取り込みはページ名で読むので、フォルダの入口を読んでしまう。続くフォルダとの整理で取り込む
        if not plan["shadowed"]:
            try:
                synced = sync_page(wiki_dir, config, engine, subpath, "updated") is not False
            except Exception:
                synced = False
        try:
            adopt_page(wiki_dir, new_subpath, config)
        except Exception:
            synced = False

    counts = {ATTACH_BOTH: 0, ATTACH_KEEP: 0, ATTACH_MOVE: 0}
    for mode in modes.values():
        counts[mode] += 1
    return True, "", {"kept": keep["name"], "bak_name": os.path.basename(new_path),
                      "bak_pagepath": new_pagepath, "attach": counts,
                      "access": access_report(wiki_dir, plan["pagepath"], new_pagepath),
                      "synced": synced}


def attachment_files(wiki_dir, subpath):
    """そのページの添付（置き場所の直下のファイル）の `[(名前, バイト数), …]`（名前順）。
    下のフォルダは下位ページの添付なので数えない（`pagecopy` と同じ）。"""
    src = attach_dir_for(wiki_dir, subpath)
    if src is None or not os.path.isdir(src):
        return []
    found = []
    for entry in os.scandir(src):
        if entry.is_file():
            try:
                found.append((entry.name, entry.stat().st_size))
            except OSError:
                found.append((entry.name, 0))
    return sorted(found)


def _remove_empty_dir(path):
    """空になった添付の置き場所を消す（空でなければ、そのまま残す）。"""
    try:
        if path is not None:
            os.rmdir(path)
    except OSError:
        pass


def _transfer_attachments(wiki_dir, subpath, new_subpath, modes):
    """添付（置き場所の直下のファイル）を、`modes`（`{名前: ATTACH_*}`）に従って `_bak` の
    ページへ写す・移す。動かしたものの `[(名前, ATTACH_BOTH|ATTACH_MOVE), …]` を返す。
    元のページだけに残すもの（`ATTACH_KEEP`）は動かさない。

    途中で失敗したら、元へ戻してから `OSError` を送る。"""
    src = attach_dir_for(wiki_dir, subpath)
    dst = attach_dir_for(wiki_dir, new_subpath)
    todo = sorted((name, mode) for name, mode in modes.items() if mode != ATTACH_KEEP)
    if src is None or dst is None or not todo:
        return []
    os.makedirs(dst, exist_ok=True)
    done = []
    try:
        for name, mode in todo:
            if mode == ATTACH_MOVE:
                os.replace(os.path.join(src, name), os.path.join(dst, name))
            else:
                shutil.copy2(os.path.join(src, name), os.path.join(dst, name))
            done.append((name, mode))
    except OSError:
        _undo_attachments(wiki_dir, subpath, new_subpath, done)
        raise
    return done


def _undo_attachments(wiki_dir, subpath, new_subpath, done):
    """`_transfer_attachments` で動かしたものを戻す。`_bak` 側の置き場所は整理の前には
    無かったので、ファイルを戻せたら置き場所ごと消す（戻せなかったものがあれば消さない。
    **移したファイルの唯一の置き場所になっているため**）。"""
    src = attach_dir_for(wiki_dir, subpath)
    dst = attach_dir_for(wiki_dir, new_subpath)
    if dst is None or not os.path.isdir(dst):
        return
    for name, mode in done:
        if mode != ATTACH_MOVE or src is None:
            continue
        try:
            os.makedirs(src, exist_ok=True)
            os.replace(os.path.join(dst, name), os.path.join(src, name))
        except OSError:
            return
    shutil.rmtree(dst, ignore_errors=True)


# ---- ファイルとフォルダの重複を整理する ----------------------------------------

def _move_own_attachments(wiki_dir, src_subpath, dst_subpath):
    """`src_subpath` の添付（置き場所の直下のファイル）を `dst_subpath` の置き場所へ移す。
    移した名前の一覧を返す。下のフォルダ（`X/index` や下位ページの添付）は動かさない。
    移し先に同じ名前があれば、移したものを戻してから `OSError` を送る。"""
    src = attach_dir_for(wiki_dir, src_subpath)
    dst = attach_dir_for(wiki_dir, dst_subpath)
    names = [name for name, _size in attachment_files(wiki_dir, src_subpath)]
    if not names:
        return []
    if src is None or dst is None:
        raise OSError("attach")
    created = not os.path.isdir(dst)
    os.makedirs(dst, exist_ok=True)
    done = []
    try:
        for name in names:
            if os.path.exists(os.path.join(dst, name)):
                raise OSError("exists")
            os.replace(os.path.join(src, name), os.path.join(dst, name))
            done.append(name)
    except OSError:
        _return_own_attachments(wiki_dir, src_subpath, dst_subpath, done, created)
        raise
    _remove_empty_dir(src)
    return done


def _return_own_attachments(wiki_dir, src_subpath, dst_subpath, names, created=True):
    """`_move_own_attachments` で移した `names` を元へ戻す。移し先の置き場所を作ったのなら、
    空になれば消す。"""
    src = attach_dir_for(wiki_dir, src_subpath)
    dst = attach_dir_for(wiki_dir, dst_subpath)
    if src is None or dst is None:
        return
    for name in names:
        try:
            os.makedirs(src, exist_ok=True)
            os.replace(os.path.join(dst, name), os.path.join(src, name))
        except OSError:
            pass
    if created:
        _remove_empty_dir(dst)


def _move_file(wiki_dir, f, dst_subpath):
    """ページのファイル `f`（`_read_file` の答え）と、その添付を `dst_subpath` へ動かす。
    `(移し先のパス, 移した添付の名前)` を返す。直前にもう一度中身を確かめ、移し先が
    埋まっていれば動かさない。失敗したら動かしたものを戻して `OSError` を送る。"""
    dst = page_file_path(wiki_dir, dst_subpath, f["ext"])
    if dst is None or page_files(os.path.join(wiki_dir, dst_subpath)):
        raise OSError("taken")
    with open(f["path"], "rb") as fp:
        if _file_hash(fp.read()) != f["hash"]:
            raise OSError("changed")
    moved = _move_own_attachments(wiki_dir, f["subpath"], dst_subpath)
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(f["path"], dst)
    except OSError:
        _return_own_attachments(wiki_dir, f["subpath"], dst_subpath, moved)
        raise
    return dst, moved


def _sync_moved(wiki_dir, config, engine, subpath):
    """動かしたページをDBに合わせる。行があれば取り込み直し（差分は出ない。中身は同じ）、
    無ければ（手で置いて、まだ取り込まれていなかったファイル）新しく取り込む。"""
    if pagedb.load_page(wiki_dir, subpath) is not None:
        return sync_page(wiki_dir, config, engine, subpath, "updated") is not False
    adopt_page(wiki_dir, subpath, config)
    return pagedb.load_page(wiki_dir, subpath) is not None


def solve_folder(wiki_dir, config, subpath, keep, hashes, uid):
    """ファイルとフォルダの重複を整理する。`subpath` はフォルダの入口（`X/index`）、`keep` は
    採用するほう（`SIDE_FILE`・`SIDE_FOLDER`）、`hashes` は画面を開いたときの `{SIDE_*: ハッシュ}`。

    採用しなかったファイルは `_bak` のページへ、採用したのが隠れたファイルなら、それを
    フォルダの入口へ動かす（冒頭の「同じ名前のファイルとフォルダ」）。**添付・履歴・書きかけ・
    DBの行は、それぞれのファイルに付いたまま動く。アクセス制限の記録は書き換えない。**

    戻り値は `(成功か, 知らせの文, 結果)`。結果は成功のときだけ `{"kept", "kept_name",
    "moved_to", "bak_name", "bak_pagepath", "access", "synced"}`（入口が無かったときは
    `bak_*` が None）。**どこで失敗しても、ファイルは動かさないか、動かす前の状態へ戻す。**"""
    plan = inspect_folder(wiki_dir, subpath)
    if plan is None:
        return False, "同じ名前のファイルとフォルダの重複は、もうありません。ページを開き直してください。", None
    by_key = {f["key"]: f for f in plan["files"]}
    if keep not in by_key:
        return False, "採用するファイルを選んでください。", None
    if any(hashes.get(f["key"]) != f["hash"] for f in plan["files"]):
        return False, ("開いてから、ページのファイルが書き換えられました。"
                       "内容を確かめ直してください。"), None
    twin_file = by_key[SIDE_FILE]
    entry_file = by_key.get(SIDE_FOLDER)
    new_subpath = plan["bak_subpath"]
    if entry_file is not None and new_subpath is None:
        return False, "_bak の名前に空きがありません（_bak〜_bak{}）。".format(MAX_BAK_TRIES), None
    new_pagepath = pagepath_of_subpath(new_subpath) if new_subpath else None
    busy = operations.overlapping(wiki_dir, tuple(p for p in (subpath, plan["twin"], new_subpath) if p))
    if busy is not None:
        return False, operations.busy_message(busy), None
    if new_pagepath is not None and \
            auth.page_privilege(wiki_dir, uid).check(new_pagepath) != auth.PAGE_WRITE:
        return False, "«/{}» を編集する権限がありません。".format(new_pagepath), None

    # 動かす順。入口を先に空けてから、隠れたファイルを入口へ入れる
    if keep == SIDE_FOLDER:
        steps = [(twin_file, new_subpath)]
    elif entry_file is not None:
        steps = [(entry_file, new_subpath), (twin_file, subpath)]
    else:
        steps = [(twin_file, subpath)]

    # 1. ファイルと添付を動かす。失敗したら、それまでに動かしたものを逆の順に戻す
    done = []
    try:
        for f, dst_subpath in steps:
            dst, moved = _move_file(wiki_dir, f, dst_subpath)
            done.append((f, dst_subpath, dst, moved))
    except OSError:
        for f, dst_subpath, dst, moved in reversed(done):
            try:
                os.replace(dst, f["path"])
            except OSError:
                pass
            _return_own_attachments(wiki_dir, f["subpath"], dst_subpath, moved)
        return False, "ファイルを動かせませんでした（途中で書き換えられた可能性があります）。", None

    # 2. 履歴・書きかけ・DBの行を、ファイルと同じ順に付け替える。3. 取り込み直す。
    #    ここで失敗しても、ファイルは動いている。取り込み（1時間ごと・updatepage）が残りを
    #    揃えるので、整理自体は成功として扱い、知らせる
    synced = True
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir))
    with stafflog.quiet():  # 保存の記録は、呼び出し側の1件にまとめる
        for f, dst_subpath, _dst, _moved in done:
            try:
                move_backups(wiki_dir, f["subpath"], dst_subpath)
                move_draft(wiki_dir, f["subpath"], dst_subpath)
                if not pagedb.rename_page(wiki_dir, f["subpath"], dst_subpath, f["ext"]):
                    synced = False
            except Exception:
                synced = False
        for _f, dst_subpath, _dst, _moved in done:
            try:
                synced = _sync_moved(wiki_dir, config, engine, dst_subpath) and synced
            except Exception:
                synced = False

    kept = by_key[keep]
    bak_path = next((dst for f, _s, dst, _m in done if f is not kept), None)
    return True, "", {
        "kept": keep, "kept_name": kept["name"],
        "moved_to": _relative_name(subpath, done[-1][2]) if keep == SIDE_FILE else None,
        "bak_name": os.path.basename(bak_path) if bak_path else None,
        "bak_pagepath": new_pagepath if bak_path else None,
        "access": (access_report(wiki_dir, plan["pagepath"], new_pagepath) if bak_path else None),
        "synced": synced}


# ---- 画面 --------------------------------------------------------------------

STYLE = """
.dup { max-width: 1200px; margin: 0 auto; }
.dup-lead { margin: 0 0 1em; padding: .7em 1em; border: 1px solid var(--border);
  border-left: 4px solid #d97706; border-radius: var(--radius); background: var(--panel-bg); }
.dup-lead p { margin: .3em 0; }
.dup-error { border-left-color: #cf222e; }
.dup-alert { margin: .6em 0; padding: .5em .8em; border: 1px solid #cf222e;
  border-left-width: 4px; border-radius: var(--radius); }
.dup-cols { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1em;
  align-items: stretch; }
.dup-info { grid-column: 1 / -1; padding: .8em 1em; border: 1px solid var(--border);
  border-radius: var(--radius); }
.dup-info h2 { margin: 0 0 .3em; font-size: 1.05rem; }
.dup-info h2:not(:first-child) { margin-top: 1em; }
.dup-info table { width: 100%; font-size: .9rem; }
.dup-info th, .dup-info td { border: 1px solid var(--border); padding: .2em .6em; text-align: left;
  vertical-align: top; }
.dup-info th { background: var(--panel-bg); font-weight: normal; white-space: nowrap; }
.dup-info p { margin: .3em 0; }
.dup-info .dup-then { color: var(--muted); }
.dup-att td.dup-att-dest, .dup-att th.dup-att-dest { white-space: nowrap; }
.dup-att td[data-img] { text-decoration: underline dotted; cursor: zoom-in; }
.dup-att tr.dup-att-bulk th, .dup-att tr.dup-att-bulk td { background: var(--panel-bg); }
.dup-dest { display: inline-block; margin-right: .8em; cursor: pointer; }
.dup-who { color: var(--muted); font-size: .85rem; }
.dup-pop { position: fixed; z-index: 1000; padding: 4px; background: var(--bg);
  border: 1px solid var(--border); border-radius: var(--radius); pointer-events: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .25); }
.dup-pop[hidden] { display: none; }
.dup-pop img { display: block; max-width: 360px; max-height: 360px; }
.dup-act { text-align: center; }
.dup-cols.dup-single { grid-template-columns: minmax(0, 1fr); }
@media (max-width: 760px) { .dup-cols { grid-template-columns: minmax(0, 1fr); } }
.dup-col { min-width: 0; border: 1px solid var(--border); border-radius: var(--radius);
  padding: .8em 1em; }
.dup-col h2 { margin: 0 0 .3em; font-size: 1.1rem; }
.dup-tag { margin-left: .5em; font-size: .8rem; font-weight: normal; color: var(--muted); }
.dup-meta { margin: .2em 0 .6em; font-size: .85rem; color: var(--muted); }
.dup-badge { display: inline-block; margin-right: .4em; padding: 0 .5em; border-radius: 1em;
  border: 1px solid var(--border); background: var(--panel-bg); color: var(--fg); }
.dup-preview { max-height: 720px; overflow: auto; padding: .5em .8em; border: 1px solid var(--border);
  border-radius: var(--radius); background: var(--bg); }
.dup-preview > :first-child { margin-top: 0; }
.dup-preview img { max-width: 100%; height: auto; }
.dup-preview table { border-collapse: collapse; }
.dup-preview th, .dup-preview td { border: 1px solid var(--border); padding: .2em .5em; }
.dup-act button { padding: .4em 1em; cursor: pointer; }
.dup-note { margin: .4em 0 0; font-size: .85rem; color: var(--muted); }
/* 入れ物は <div>（<p> の中に <form> は置けず、ブラウザがそこで <p> を閉じて縦に積まれるため） */
.dup-done { margin: .6em 0 .3em; }
.dup-done a, .dup-done button { margin-right: .6em; }
.dup-done form { display: inline; }
"""


def _time_text(mtime):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))


def _page_link(base_url, pagepath, label=None):
    shown = "/" + pagepath if pagepath else "/"
    return '<a href="{}/{}">{}</a>'.format(
        escape(base_url), escape(urlquote(pagepath, safe="/")), escape(label or shown))


def _edit_button(base_url, pagepath, label="編集"):
    """そのページの編集画面を開くボタン（編集はGETを受けないので、POST `cmd=edit`）。"""
    return ('<form method="post" action="{}/{}"><input type="hidden" name="cmd" value="edit">'
            '<button type="submit">{}</button></form>').format(
        escape(base_url), escape(urlquote(pagepath, safe="/")), escape(label))


def render_previews(wiki_dir, config, farm, explicit_farm, pagepath, subpath, files):
    """ファイルごとのプレビュー（HTMLの断片）と、使われたプラグインの資材のURL、ファイルごとの
    本文のプラグインのアクセス制限。`(htmls, styles, scripts, plugin_auth)`。

    `htmls`・`plugin_auth` はファイルの `key` ごと。
    `plugin_auth` は `{key: ["R", "W"] の部分集合（`#readauth`・`#writeauth` が呼ばれた種類）}`。
    描けなかったファイルは None（調べられなかった）。見つけかたは `updatepageauth` と同じ
    （描いて `context.used_plugins` を見る）。部分プレビュー（`partial=True`）なので、
    プラグインは記録を書かない。

    編集画面のプレビュー（`editor.render_preview`）と同じ手順で、そのファイルの書きかた
    （拡張子）のまま描く。**本文の `<form>` は止める**（プレビューから本物の投稿が
    できないように）。"""
    from wikilib.editor import disable_embedded_forms
    from wikilib.render import parse_source, rewrite_content_links
    from wikilib.themes import make_plugin_context

    htmls, styles, scripts, plugin_auth = {}, [], [], {}
    plugin_dir = farm_plugin_dir(wiki_dir)
    for f in files:
        context = make_plugin_context(config, farm, wiki_dir, pagepath, explicit_farm,
                                      partial=True, ext=f["ext"])
        engine = build_markdown_renderer(config, plugin_dir, context)
        env = {"wiki": context}
        try:
            tokens = parse_source(engine, f["body"], f["ext"], env)
            html = engine.renderer.render(tokens, engine.options, env)
            # 添付の置き場所はファイルごと（ファイルとフォルダの重複では別々）
            html = rewrite_content_links(html, context.base_url, f.get("subpath", subpath), wiki_dir)
            html = disable_embedded_forms(html)
            used = set(context.used_plugins)
            plugin_auth[f["key"]] = [kind for kind, name in PLUGIN_OF_KIND.items() if name in used]
        except Exception:  # 描けない本文でも、画面は出す（直すために見に来ている）
            html = "<p>プレビューを描けませんでした。</p>"
            plugin_auth[f["key"]] = None
        htmls[f["key"]] = html
        for url in plugin_style_urls(context.base_url, plugin_dir, context.used_plugins):
            if url not in styles:
                styles.append(url)
        for url in plugin_script_urls(context.base_url, plugin_dir, context.used_plugins):
            if url not in scripts:
                scripts.append(url)
    return htmls, styles, scripts, plugin_auth


def _lead_html(config, farm, base_url, pagepath, plan):
    """画面の先頭の、簡単な状況説明と詳しい説明へのリンク。"""
    names = [f["name"] for f in plan["files"]]
    first, rest = names[0], "・".join(names[1:])
    shown = (os.path.basename(plan["subpath"]) + plan["shown_ext"]) if plan["shown_ext"] else None
    if plan["shadowed"]:
        lines = ["<p>{} には、同じ名前のファイルが {} つあります（{}）。同じ名前のフォルダ "
                 "<code>{}/</code> もあるため、どれも読まれていません。まず、ファイルを1つに絞ります"
                 "（そのあとで、フォルダとの重複を整理します）。".format(
                     _page_link(base_url, pagepath), len(names), escape("・".join(names)),
                     escape(os.path.basename(plan["subpath"])))]
    else:
        lines = ["<p>{} には、同じ名前のファイルが {} つあります（{}）。読まれるのは <strong>{}</strong> "
                 "で、{} は読まれません。".format(
                     _page_link(base_url, pagepath), len(names), escape("・".join(names)),
                     escape(first), escape(rest))]
    if shown and shown != first:
        lines[0] += ("いま画面に出ているのは、取り込み済みの <strong>{}</strong> です"
                     "（取り込むと {} の内容に替わります）。").format(escape(shown), escape(first))
    lines[0] += "</p>"
    lines.append('<p>どちらを採用するか選んでください。選ばなかったほうは、名前に <code>_bak</code> を'
                 "付けたページとして残り、閲覧・編集できます。"
                 '詳しい説明は <a href="{}">同じ名前の .txt と .md があるとき</a> へ。</p>'.format(
                     escape(guide_url(config, farm, base_url, DUPLICATE_GUIDE_PAGE))))
    return '<div class="dup-lead">{}</div>'.format("".join(lines))


SCRIPT = """
(function () {
  var table = document.querySelector('.dup-att');
  if (!table) return;
  // 移動先: 一括のラジオボタンを押すと、その内容を全ファイルへコピーする。
  // ファイルごとに変えて揃わなくなったら、一括のほうは選んでいない状態に戻す
  var bulk = [].slice.call(table.querySelectorAll('input[name="dest-all"]'));
  var each = [].slice.call(table.querySelectorAll('input[type="radio"][name^="dest:"]'));
  function syncBulk() {
    var chosen = {};
    each.forEach(function (r) { if (r.checked) chosen[r.name] = r.value; });
    var values = Object.keys(chosen).map(function (k) { return chosen[k]; });
    var same = values.length > 0 && values.every(function (v) { return v === values[0]; });
    bulk.forEach(function (b) { b.checked = same && b.value === values[0]; });
  }
  bulk.forEach(function (b) {
    b.addEventListener('click', function () {
      each.forEach(function (r) { r.checked = (r.value === b.value); });
      syncBulk();
    });
  });
  each.forEach(function (r) { r.addEventListener('change', syncBulk); });
  // 画像ファイルは、ファイル名にマウスを重ねるとプレビューを出す
  var pop = document.createElement('div');
  pop.className = 'dup-pop';
  pop.hidden = true;
  var img = document.createElement('img');
  img.alt = '';
  pop.appendChild(img);
  document.body.appendChild(pop);
  var last = { clientX: 0, clientY: 0 };
  function place(e) {
    last = { clientX: e.clientX, clientY: e.clientY };
    var w = pop.offsetWidth, h = pop.offsetHeight;
    var x = e.clientX + 16, y = e.clientY + 16;
    if (x + w > window.innerWidth - 8) x = Math.max(8, e.clientX - w - 16);
    if (y + h > window.innerHeight - 8) y = Math.max(8, window.innerHeight - h - 8);
    pop.style.left = x + 'px';
    pop.style.top = y + 'px';
  }
  img.addEventListener('load', function () { place(last); });
  [].forEach.call(table.querySelectorAll('td[data-img]'), function (td) {
    td.addEventListener('mouseenter', function (e) {
      img.src = td.getAttribute('data-img');
      pop.hidden = false;
      place(e);
    });
    td.addEventListener('mousemove', place);
    td.addEventListener('mouseleave', function () {
      pop.hidden = true;
      img.removeAttribute('src');
    });
  });
})();
"""

DEST_LABELS = ((DEST_BOTH, "両方"), (DEST_TXT, ".txt 側"), (DEST_MD, ".md 側"))
KIND_LABELS = {"read": "閲覧（R）", "write": "編集（W）", "R": "閲覧（R）", "W": "編集（W）"}
# 本文のプラグインの種類の呼び名（`#readauth`＝閲覧、`#writeauth`＝編集）
PLUGIN_KIND_LABELS = {"R": "閲覧（#readauth）", "W": "編集（#writeauth）"}


def _size_text(n):
    if n >= 1024 * 1024:
        return "{:.1f} MB".format(n / (1024 * 1024))
    if n >= 1024:
        return "{:.1f} KB".format(n / 1024)
    return "{} B".format(n)


def _page_label(pagepath):
    return escape("/" + pagepath) if pagepath else "/"


def _attach_url(base_url, subpath, name):
    """添付ファイルのURL（`attach.py` の一覧と同じ形）。"""
    return "{}/{}/{}/{}".format(base_url, ATTACH_URLPATH, urlquote(subpath, safe="/"),
                                urlquote(name))


# アクセス制限の画面を、別ウィンドウで開く `onclick`（`window.open`）。`popup` と大きさを
# 指定すると、タブではなくウィンドウで開く。**`noopener` は features に入れる**——
# `<a rel="noopener">` は `window.open` には効かないため。開いた先から `window.opener`
# でこの画面を操作されない。`return false` で、リンクそのものの移動は止める
# （Ctrl+クリック・中クリックは、`href` のとおり通常のリンクとして開く）
OPEN_PRIVILEGES = ("window.open(this.href, '_blank', 'popup,noopener,width=1100,height=800'); "
                   "return false;")


def _privileges_link(base_url, label="アクセス制限"):
    """アクセス制限の画面へのリンク。**別ウィンドウで開く**（`onclick` の `window.open`）——
    この画面を残したまま設定できるように（整理の前でも後でも使う）。"""
    return '<a href="{}/{}" onclick="{}">{}</a>'.format(
        escape(base_url), PRIVILEGES_URLPATH, escape(OPEN_PRIVILEGES), escape(label))


def _dest_radios(name, checked=DEST_BOTH):
    return "".join(
        '<label class="dup-dest"><input type="radio" name="{}" value="{}"{}> {}</label>'.format(
            escape(name), value, " checked" if value == checked else "", label)
        for value, label in DEST_LABELS)


def _rule_cell(rule, show_who):
    """アクセス制限の表の1マス。指定が無ければ「指定なし」、あれば当たっている指定と許可者。
    **許可者の一覧は管理者と助手にだけ**見せる（それ以外には件数だけ）。"""
    if rule is None:
        return "指定なし"
    who = ("、".join(rule["who"]) if show_who else "{} 件".format(len(rule["who"])))
    return '<code>{}</code><br><span class="dup-who">許可者: {}</span>'.format(
        escape("、".join(rule["rules"])), escape(who))


def _attach_html(plan, state, base_url):
    """添付ファイルの欄: 一覧と、ファイルごとの移動先（両方・.txt 側・.md 側）、一括設定。"""
    files = state["attachments"]
    page, bak_page = plan["pagepath"], (
        pagepath_of_subpath(plan["bak_subpath"]) if plan["bak_subpath"] else None)
    parts = ["<h2>添付ファイル</h2>"]
    if not files:
        return parts[0] + "<p>添付ファイルはありません。</p>"
    rows = []
    for name, size in files:
        image = os.path.splitext(name)[1].lower() in IMAGE_EXTS
        rows.append(
            '<tr><td{}>{}</td><td>{}</td><td class="dup-att-dest">{}</td></tr>'.format(
                ' data-img="{}"'.format(escape(_attach_url(base_url, plan["subpath"], name)))
                if image else "", escape(name), _size_text(size),
                _dest_radios("dest:" + name)))
    here = _page_label(page)
    there = _page_label(bak_page) if bak_page else "_bak のページ"
    parts.append(
        "<p>{} 件（合計 {}）。この2つのファイルは同じ添付を使っています。"
        "移動先を、ファイルごとに選べます。</p>"
        '<p class="dup-then">「.txt 側」「.md 側」は、そのファイルのページです。'
        "採用したファイルのページが {}、採用しなかったほうが {} になります。"
        "「両方」は、{} に残したまま {} へも写します（容量が増えます）。"
        "持たせなかったほうの本文では、添付の画像などが表示されなくなります。"
        "画像ファイルは、ファイル名にマウスを重ねるとプレビューが出ます。</p>"
        '<table class="dup-att"><thead><tr><th>ファイル名</th><th>大きさ</th>'
        '<th class="dup-att-dest">移動先</th></tr></thead><tbody>'
        '<tr class="dup-att-bulk"><th colspan="2">すべて（一括）</th>'
        '<td class="dup-att-dest">{}</td></tr>{}</tbody></table>'.format(
            len(files), _size_text(sum(size for _n, size in files)), here, there, here, there,
            _dest_radios("dest-all"), "".join(rows)))
    return "".join(parts)


def _plugin_auth_html(plan, plugin_auth):
    """本文のプラグイン（`#readauth`・`#writeauth`）によるアクセス制限が、**どちらのファイルに
    何が設定されているか**。許可者は出さない（`.txt` と `.md` の本文は別なので、採用する
    ほうで、整理後の制限が変わる）。"""
    if not plugin_auth:
        return ""
    rows = []
    for f in plan["files"]:
        kinds = plugin_auth.get(f["key"])
        if kinds is None:
            cell = "調べられませんでした"
        elif kinds:
            cell = "、".join(PLUGIN_KIND_LABELS[k] for k in kinds)
        else:
            cell = "なし"
        rows.append("<tr><th>{}</th><td>{}</td></tr>".format(escape(f["name"]), cell))
    return ("<p>本文のプラグイン（#readauth・#writeauth）によるアクセス制限が、どちらのファイルに"
            "設定されているかです。</p>"
            "<table><thead><tr><th>ファイル</th><th>設定</th></tr></thead><tbody>{}</tbody></table>"
            .format("".join(rows)))


def _access_html(plan, state, show_who, base_url, plugin_auth=None):
    """アクセス制限の欄。**書き換えず、案内とリンクだけ**（冒頭の「アクセス制限は触らない」）。"""
    access = state["access"]
    page = _page_label(plan["pagepath"])
    bak = (_page_label(pagepath_of_subpath(plan["bak_subpath"]))
           if plan["bak_subpath"] else "_bak のページ")
    parts = ["<h2>アクセス制限</h2>",
             "<p>この修正では案内のみで修正を行いません。お手数をおかけしますが、本情報をもとに別途 "
             "{} の対応をお願いいたします。".format(_privileges_link(base_url)) +
             '<span class="dup-then">（別ウィンドウで開きます。この画面はそのまま残ります）</span></p>']
    rows = []
    for key in ("read", "write"):
        bak_rule = access["bak_rules"][key] if access["bak_rules"] is not None else None
        rows.append("<tr><th>{}</th><td>{}</td><td>{}</td></tr>".format(
            KIND_LABELS[key], _rule_cell(access["rules"][key], show_who),
            _rule_cell(bak_rule, show_who) if access["bak_rules"] is not None else "—"))
    parts.append(
        "<p>いま当たっているアクセス制限の指定です（右は、整理でできる {} に当たる指定）。</p>"
        "<table><thead><tr><th>種類</th><th>{}（元のページ）</th><th>{}（整理後）</th></tr></thead>"
        "<tbody>{}</tbody></table>".format(bak, page, bak, "".join(rows)))
    if access["differs"]:
        kinds = "・".join(KIND_LABELS[k] for k in access["differs"])
        parts.append(
            '<p class="dup-alert"><strong>⚠ {} には、{} と同じアクセス制限が付きません</strong>'
            "（{}）。整理した直後から、{} は {} より制限が緩い（または制限が無い）状態になります。"
            "上の {} から、整理の前でも後でも設定できます。</p>".format(
                bak, page, kinds, bak, page, _privileges_link(base_url)))
    parts.append(_plugin_auth_html(plan, plugin_auth))
    return "".join(parts)


def _info_html(plan, state, show_who, base_url, plugin_auth=None):
    """プレビューの下に出す、添付とアクセス制限の状態。"""
    return '<div class="dup-info">{}{}</div>'.format(
        _attach_html(plan, state, base_url),
        _access_html(plan, state, show_who, base_url, plugin_auth))


def _page_html(config, farm, base_url, pagepath, plan, previews, state, show_who, notice=""):
    """プレビューを左右に並べ、その下に添付とアクセス制限、いちばん下に採用のボタンを置く画面の本文。"""
    htmls, styles, scripts, plugin_auth = previews
    new_pagepath = pagepath_of_subpath(plan["bak_subpath"]) if plan["bak_subpath"] else None
    differs = bool(state["access"]["differs"])
    cols, acts = [], []
    for f in plan["files"]:
        other = next(g for g in plan["files"] if g["ext"] != f["ext"])
        badges = ""
        if f["ext"] == plan["files"][0]["ext"] and not plan["shadowed"]:
            badges += '<span class="dup-badge">読まれるほう</span>'
        if plan["shown_ext"] == f["ext"]:
            badges += '<span class="dup-badge">いま画面に出ている</span>'
        bak_file = ((os.path.basename(plan["bak_subpath"]) + other["ext"])
                    if plan["bak_subpath"] else "")
        label = markup_format_for(f["ext"])["label"]
        cols.append(
            '<section class="dup-col">'
            '<h2>{}<span class="dup-tag">{}</span></h2>'
            '<p class="dup-meta">{}{} バイト・更新 {}</p>'
            '<div class="dup-preview">{}</div>'
            "</section>".format(
                escape(f["name"]), escape(label), badges, f["size"], _time_text(f["mtime"]),
                htmls[f["key"]]))
        confirm = "{}を採用し、{}を {} として残します。".format(f["name"], other["name"], bak_file)
        if differs and new_pagepath is not None:
            confirm += "\n\n/{} には、/{} と同じアクセス制限が付きません（案内のみで、修正は行いません）。".format(
                new_pagepath, pagepath)
        confirm += "\n\nよろしいですか？"
        acts.append(
            '<div class="dup-act"><button type="submit" name="keep" value="{}" '
            'data-confirm="{}"{}>{} を採用する</button>'
            '<p class="dup-note">{}</p></div>'.format(
                escape(f["ext"]), escape(confirm), "" if new_pagepath else " disabled",
                escape(f["name"]),
                ("採用すると、{} は {} として残ります。".format(
                    escape(other["name"]), escape(bak_file)) if bak_file else "")))
    hidden = _hidden_fields(plan)
    form = ('<form method="post" action="{}/{}{}" '
            "onsubmit=\"var b=event.submitter; return !b || !b.dataset.confirm || confirm(b.dataset.confirm)\">"
            '{}<div class="dup-cols">{}{}{}</div></form>').format(
        escape(base_url), SOLVEDUP_URLPATH,
        ("/" + escape(urlquote(pagepath, safe="/"))) if pagepath else "", hidden,
        "".join(cols), _info_html(plan, state, show_who, base_url, plugin_auth), "".join(acts))
    extra = "".join('<link rel="stylesheet" href="{}">'.format(escape(u)) for u in styles)
    extra += "".join('<script src="{}" defer></script>'.format(escape(u)) for u in scripts)
    extra += "<script>{}</script>".format(SCRIPT)
    if new_pagepath is None:
        notice += ('<div class="dup-lead dup-error"><p>_bak の名前に空きが無いため、整理できません。'
                   "ファイル一覧で名前を整理してください。</p></div>")
    return '<div class="dup"><style>{}</style>{}{}{}{}</div>'.format(
        STYLE, _lead_html(config, farm, base_url, pagepath, plan), notice, form, extra)


def _hidden_fields(plan):
    """画面を開いたときの状態をフォームに持たせる。整理の段（`stage`。押すまでの間に段が
    替わっていたら断る）と、ファイルごとの本文のハッシュ（`hash<key>`）。"""
    return '<input type="hidden" name="stage" value="{}">'.format(
        escape(plan["stage"] + ":" + plan["subpath"])) + "".join(
        '<input type="hidden" name="hash{}" value="{}">'.format(escape(f["key"]), escape(f["hash"]))
        for f in plan["files"])


def _folder_lead_html(config, farm, base_url, pagepath, plan):
    """ファイルとフォルダの重複の画面の先頭。"""
    by_key = {f["key"]: f for f in plan["files"]}
    twin, entry = by_key[SIDE_FILE], by_key.get(SIDE_FOLDER)
    folder = os.path.basename(plan["twin"]) + "/"
    page = _page_link(base_url, pagepath)
    if entry is not None:
        lines = ["<p>{} には、同じ名前のファイル <code>{}</code> とフォルダ <code>{}</code> があります。"
                 "読まれるのはフォルダの入口の <strong>{}</strong> で、{} は読まれません。</p>".format(
                     page, escape(twin["name"]), escape(folder), escape(entry["name"]),
                     escape(twin["name"])),
                 "<p>どちらを採用するか選んでください。選ばなかったほうは、名前に <code>_bak</code> を"
                 "付けたページとして残り、閲覧・編集できます。添付ファイル・履歴・書きかけは、それぞれの"
                 "ファイルに付いたまま動きます。{} を採用すると、フォルダの入口（{}）へ移ります"
                 "（ページ名は変わりません）。".format(
                     escape(twin["name"]), escape(folder + INDEX_NAME + twin["ext"]))]
    else:
        lines = ["<p>{} には、同じ名前のファイル <code>{}</code> とフォルダ <code>{}</code> があります。"
                 "フォルダに入口のページ（{}）が無いので、このページは無いものとして扱われ、"
                 "{} は読まれません。</p>".format(
                     page, escape(twin["name"]), escape(folder), INDEX_NAME, escape(twin["name"])),
                 "<p>{} をフォルダの入口へ移すと、このページとして読めるようになります。"
                 "添付ファイル・履歴・書きかけも一緒に移ります。".format(escape(twin["name"]))]
    lines[-1] += '詳しい説明は <a href="{}#{}">{}</a> へ。</p>'.format(
        escape(guide_url(config, farm, base_url, DUPLICATE_GUIDE_PAGE)),
        escape(urlquote(FOLDER_GUIDE_HEADING)), FOLDER_GUIDE_HEADING)
    return '<div class="dup-lead">{}</div>'.format("".join(lines))


def _folder_page_html(config, farm, base_url, pagepath, plan, previews, state, show_who, notice=""):
    """ファイルとフォルダの重複の画面の本文。並びは `.txt` と `.md` の画面と同じ（プレビュー、
    添付とアクセス制限、採用のボタン）。添付は移動先を選ばせず、件数だけ示す。"""
    htmls, styles, scripts, plugin_auth = previews
    by_key = {f["key"]: f for f in plan["files"]}
    entry = by_key.get(SIDE_FOLDER)
    new_pagepath = pagepath_of_subpath(plan["bak_subpath"]) if plan["bak_subpath"] else None
    differs = bool(state["access"]["differs"])
    entry_name = os.path.basename(plan["twin"]) + "/" + INDEX_NAME + by_key[SIDE_FILE]["ext"]
    cols, acts, att = [], [], []
    for f in plan["files"]:
        badges = '<span class="dup-badge">読まれるほう</span>' if f["key"] == SIDE_FOLDER else ""
        count = f["attach_count"]
        att.append("{}: {} 件".format(escape(f["name"]), count))
        cols.append(
            '<section class="dup-col">'
            '<h2>{}<span class="dup-tag">{}</span></h2>'
            '<p class="dup-meta">{}{} バイト・更新 {}・添付 {} 件</p>'
            '<div class="dup-preview">{}</div>'
            "</section>".format(
                escape(f["name"]), escape(markup_format_for(f["ext"])["label"]), badges, f["size"],
                _time_text(f["mtime"]), count, htmls[f["key"]]))
        if entry is None:
            confirm = "{} を {} へ移します。よろしいですか？".format(f["name"], entry_name)
            label, note = "{} をフォルダの入口へ移す".format(f["name"]), "移すと {} になります。".format(entry_name)
        else:
            other = next(g for g in plan["files"] if g["key"] != f["key"])
            bak_file = (os.path.basename(plan["bak_subpath"]) + other["ext"]) if new_pagepath else ""
            confirm = "{}を採用し、{}を {} として残します。".format(f["name"], other["name"], bak_file)
            if f["key"] == SIDE_FILE:
                confirm += "{} は {} へ移ります。".format(f["name"], entry_name)
            if differs and new_pagepath is not None:
                confirm += "\n\n/{} には、/{} と同じアクセス制限が付きません（案内のみで、修正は行いません）。".format(
                    new_pagepath, pagepath)
            confirm += "\n\nよろしいですか？"
            label = "{} を採用する".format(f["name"])
            note = "採用すると、{} は {} として残ります。".format(other["name"], bak_file) if bak_file else ""
        acts.append(
            '<div class="dup-act"><button type="submit" name="keep" value="{}" '
            'data-confirm="{}"{}>{}</button><p class="dup-note">{}</p></div>'.format(
                escape(f["key"]), escape(confirm),
                "" if (entry is None or new_pagepath) else " disabled", escape(label), escape(note)))
    info = "<h2>添付ファイル</h2><p>{}。{}</p>".format(
        "、".join(att), "添付ファイルも一緒に移ります。" if entry is None
        else "添付ファイルは、それぞれのファイルのページに付いたまま動きます。")
    if entry is not None:
        info += _access_html(plan, state, show_who, base_url, plugin_auth)
    form = ('<form method="post" action="{}/{}{}" '
            "onsubmit=\"var b=event.submitter; return !b || !b.dataset.confirm || confirm(b.dataset.confirm)\">"
            '{}<div class="dup-cols{}">{}<div class="dup-info">{}</div>{}</div></form>').format(
        escape(base_url), SOLVEDUP_URLPATH,
        ("/" + escape(urlquote(pagepath, safe="/"))) if pagepath else "", _hidden_fields(plan),
        " dup-single" if entry is None else "", "".join(cols), info, "".join(acts))
    extra = "".join('<link rel="stylesheet" href="{}">'.format(escape(u)) for u in styles)
    extra += "".join('<script src="{}" defer></script>'.format(escape(u)) for u in scripts)
    if entry is not None and new_pagepath is None:
        notice += ('<div class="dup-lead dup-error"><p>_bak の名前に空きが無いため、整理できません。'
                   "ファイル一覧で名前を整理してください。</p></div>")
    return '<div class="dup"><style>{}</style>{}{}{}{}</div>'.format(
        STYLE, _folder_lead_html(config, farm, base_url, pagepath, plan), notice, form, extra)


def _folder_done_html(base_url, pagepath, result):
    here = _page_label(pagepath)
    if result["bak_pagepath"] is None:
        lines = ["<p><strong>{}</strong> を <strong>{}</strong> へ移しました。{} で読めます。</p>".format(
            escape(result["kept_name"]), escape(result["moved_to"]), _page_link(base_url, pagepath))]
    else:
        moved = ("（<strong>{}</strong> へ移しました）".format(escape(result["moved_to"]))
                 if result["moved_to"] else "")
        lines = ["<p><strong>{}</strong> を採用しました{}。もう一方は <strong>{}</strong>（{}）として"
                 "残しました。添付ファイル・履歴・書きかけは、それぞれのファイルに付いたまま動きました。</p>"
                 .format(escape(result["kept_name"]), moved, escape(result["bak_name"]),
                         _page_link(base_url, result["bak_pagepath"]))]
        lines.extend(_access_result(result["access"], pagepath, result["bak_pagepath"], base_url))
    if not result["synced"]:
        lines.append("<p>ページの記録の取り込みに失敗しました。1時間以内に自動で取り込まれます"
                     "（すぐ直すときは <code>./wiki.py updatepage</code>）。</p>")
    links = [_page_link(base_url, pagepath, "「{}」を見る".format(here)),
             _edit_button(base_url, pagepath, "「{}」を編集".format(here))]
    if result["bak_pagepath"] is not None:
        links += [_page_link(base_url, result["bak_pagepath"], "「/{}」を見る".format(result["bak_pagepath"])),
                  _edit_button(base_url, result["bak_pagepath"], "「/{}」を編集".format(result["bak_pagepath"]))]
    lines.append('<div class="dup-done">{}</div>'.format("".join(links)))
    return '<div class="dup"><style>{}</style><div class="dup-lead">{}</div></div>'.format(
        STYLE, "".join(lines))


def _access_result(access, pagepath, bak_pagepath, base_url):
    """結果の画面の、アクセス制限の案内（`.txt` と `.md` の整理と同じ文）。"""
    here, bak = _page_label(pagepath), _page_label(bak_pagepath)
    lines = []
    if access["differs"]:
        lines.append(
            '<p class="dup-alert"><strong>⚠ {} には、{} と同じアクセス制限が付いていません。</strong>'
            "いまは、{} より制限が緩い（または制限が無い）状態です"
            "（{}）。{} を開いて、設定してください。"
            "別ウィンドウで開くので、この画面はそのまま残ります。</p>".format(
                bak, here, here, "・".join(KIND_LABELS[k] for k in access["differs"]),
                _privileges_link(base_url)))
    else:
        lines.append("<p>アクセス制限は、修正していません。確認・設定は {} から行えます"
                     "（別ウィンドウで開きます）。</p>".format(_privileges_link(base_url)))
    if access["plugin"]:
        lines.append("<p>{} には、本文のプラグイン（#readauth・#writeauth）によるアクセス制限も"
                     "設定されています。</p>".format(here))
    return lines


def _attach_result(result, pagepath):
    """結果の画面の、添付の1行。動かしたものが無ければ空。"""
    counts = result["attach"]
    here, bak = _page_label(pagepath), _page_label(result["bak_pagepath"])
    pieces = []
    if counts[ATTACH_BOTH]:
        pieces.append("{} 件は両方（{} に残したまま {} へ写した）".format(counts[ATTACH_BOTH], here, bak))
    if counts[ATTACH_KEEP]:
        pieces.append("{} 件は {} だけに残した".format(counts[ATTACH_KEEP], here))
    if counts[ATTACH_MOVE]:
        pieces.append("{} 件は {} へ移した".format(counts[ATTACH_MOVE], bak))
    return "<p>添付ファイル: {}。</p>".format("、".join(pieces)) if pieces else ""


def _continue_html(base_url, pagepath):
    """結果の画面に添える、残りの重複の整理へのリンク（1段ずつ整理する。冒頭参照）。"""
    return ('<p class="dup-alert"><strong>まだ重複が残っています。</strong>'
            '<a href="{}/{}{}">続けて整理する</a></p>').format(
        escape(base_url), SOLVEDUP_URLPATH,
        ("/" + escape(urlquote(pagepath, safe="/"))) if pagepath else "")


def _done_html(base_url, pagepath, result):
    lines = ["<p><strong>{}</strong> を採用しました。もう一方は <strong>{}</strong>（{}）として残しました。</p>"
             .format(escape(result["kept"]), escape(result["bak_name"]),
                     _page_link(base_url, result["bak_pagepath"])),
             _attach_result(result, pagepath)]
    lines.extend(_access_result(result["access"], pagepath, result["bak_pagepath"], base_url))
    if not result["synced"]:
        lines.append("<p>ページの記録の取り込みに失敗しました。1時間以内に自動で取り込まれます"
                     "（すぐ直すときは <code>./wiki.py updatepage</code>）。</p>")
    lines.append('<div class="dup-done">{}{}{}{}</div>'.format(
        _page_link(base_url, pagepath, "「{}」を見る".format("/" + pagepath if pagepath else "/")),
        _edit_button(base_url, pagepath, "「{}」を編集".format("/" + pagepath if pagepath else "/")),
        _page_link(base_url, result["bak_pagepath"], "「/{}」を見る".format(result["bak_pagepath"])),
        _edit_button(base_url, result["bak_pagepath"],
                     "「/{}」を編集".format(result["bak_pagepath"]))))
    return '<div class="dup"><style>{}</style><div class="dup-lead">{}</div></div>'.format(
        STYLE, "".join(lines))


def _destinations(forms):
    """フォームの添付ごとの移動先 `{ファイル名: 値}`（フィールド名は `dest:<ファイル名>`）。
    `dest-all`（一括のラジオボタン）は画面のJSが各ファイルへコピーするためのもので、読まない。"""
    return {key[len("dest:"):]: forms.get(key) for key in forms.keys() if key.startswith("dest:")}


def serve_solve_dup(wiki_dir, config, farm, explicit_farm, pagepath):
    """`/.solveDupPage/<ページ名>`。GETでプレビューを見せ、POSTで整理する。

    閲覧の権限（R）が無ければ、閲覧できないページの画面と同じ（403）。**編集の権限（W）が
    無ければ、説明だけを出す**（プレビューも選ぶボタンも出さない。冒頭参照）。"""
    from wikilib import sysui
    from wikilib.themes import make_plugin_context
    from wikilib.views import render_no_page, render_no_view

    pagepath = pagepath_of_subpath((pagepath or "").strip("/"))
    if pagepath and not is_valid_pagepath(pagepath):
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)
    ref = resolve_page_ref(wiki_dir, pagepath)
    if ref is None:
        return render_no_page(wiki_dir, config, farm, pagepath, explicit_farm)
    uid = auth.current_uid(wiki_dir, farm)
    privilege = auth.page_privilege(wiki_dir, uid).check(pagepath)
    if privilege == auth.PAGE_NONE:
        return render_no_view(wiki_dir, config, farm, pagepath, explicit_farm,
                              logged_in=uid is not None)

    context = make_plugin_context(config, farm, wiki_dir, SOLVEDUP_URLPATH, explicit_farm)
    base_url = context.base_url
    title = "同じ名前のページを整理する"

    def respond(body, status=200):
        return sysui.page(wiki_dir, config, farm, explicit_farm, SOLVEDUP_URLPATH, title,
                          body, status=status)

    def inspect():
        stage = duplicate_stage(wiki_dir, ref.subpath)
        if stage is None:
            return None
        if stage[0] == STAGE_FOLDER:
            return inspect_folder(wiki_dir, ref.subpath)
        return inspect_duplicate(wiki_dir, stage[1])

    def finished(html):
        """結果の画面。重複がまだ残っていれば、続きへのリンクを先頭に添える。"""
        if duplicate_stage(wiki_dir, ref.subpath) is not None:
            html = html.replace('<div class="dup-lead">', _continue_html(base_url, pagepath)
                                + '<div class="dup-lead">', 1)
        return respond(html)

    plan = inspect()
    if plan is None:
        return respond('<div class="dup"><style>{}</style><div class="dup-lead">'
                       "<p>{} には、同じ名前のファイルの重複はありません。</p></div></div>"
                       .format(STYLE, _page_link(base_url, pagepath)))
    if privilege != auth.PAGE_WRITE:
        lead = (_folder_lead_html if plan["stage"] == STAGE_FOLDER else _lead_html)(
            config, farm, base_url, pagepath, plan)
        return respond('<div class="dup"><style>{}</style>{}<div class="dup-lead">'
                       "<p>整理するには、このページの編集の権限が必要です。"
                       "権限のある人に、この画面を開くよう伝えてください。</p></div></div>"
                       .format(STYLE, lead), status=403)

    notice = ""
    status = 200
    if request.method == "POST":
        forms = request.forms.decode()  # ファイル名（日本語など）を読めるように
        sent_stage = forms.get("stage")
        if sent_stage and sent_stage != plan["stage"] + ":" + plan["subpath"]:
            ok, message = False, "開いてから、重複の状態が変わりました。内容を確かめ直してください。"
        elif plan["stage"] == STAGE_FOLDER:
            hashes = {key: forms.get("hash" + key) for key in (SIDE_FILE, SIDE_FOLDER)}
            ok, message, result = solve_folder(wiki_dir, config, ref.subpath, forms.get("keep"),
                                               hashes, uid)
            if ok:
                _record_staff(wiki_dir, farm, ref.subpath, "/{}: {} を採用{}".format(
                    pagepath, result["kept_name"],
                    "、もう一方は /{} へ".format(result["bak_pagepath"]) if result["bak_pagepath"]
                    else "（フォルダの入口へ移した）"),
                    {"subpath": ref.subpath, "kept": result["kept_name"],
                     "bak": result["bak_pagepath"]})
                return finished(_folder_done_html(base_url, pagepath, result))
        else:
            hashes = {ext: forms.get("hash" + ext) for ext in PAGE_EXTS}
            ok, message, result = solve(wiki_dir, config, plan["subpath"], forms.get("keep"), hashes,
                                        uid, _destinations(forms))
            if ok:
                counts = result["attach"]
                _record_staff(
                    wiki_dir, farm, plan["subpath"],
                    "/{}: {} を採用、もう一方は /{} へ（添付: 両方{}・元のページだけ{}・_bak へ移した{}）".format(
                        pagepath, result["kept"], result["bak_pagepath"], counts[ATTACH_BOTH],
                        counts[ATTACH_KEEP], counts[ATTACH_MOVE]),
                    {"subpath": plan["subpath"], "kept": result["kept"],
                     "bak": result["bak_pagepath"], "attach": counts})
                return finished(_done_html(base_url, pagepath, result))
        notice = '<div class="dup-lead dup-error" role="alert"><p>{}</p></div>'.format(escape(message))
        status = 409
        plan = inspect()
        if plan is None:
            return respond('<div class="dup"><style>{}</style>{}</div>'.format(STYLE, notice),
                           status=status)
    previews = render_previews(wiki_dir, config, farm, explicit_farm, pagepath, plan["subpath"],
                               plan["files"])
    state = describe_state(wiki_dir, plan)
    show_who = auth.allows(wiki_dir, farm, auth.STAFF)
    page_html = _folder_page_html if plan["stage"] == STAGE_FOLDER else _page_html
    return respond(page_html(config, farm, base_url, pagepath, plan, previews, state,
                             show_who, notice), status)


def _record_staff(wiki_dir, farm, subpath, text, after):
    """助手の操作なら `page.dupsolve` として記録する（戻す操作は無い）。"""
    staff = stafflog.actor(wiki_dir, farm)
    if staff is not None:
        stafflog.record(wiki_dir, staff, "page.dupsolve", subpath, text, before=None, after=after)
