"""ページの実体を移すときの後始末をまとめたモジュール。

`Tech/ChangeLog.md` の下に `Tech/ChangeLog/2026-08-11` を作りたくなったとき、
`Tech/ChangeLog.md` を `Tech/ChangeLog/index.md` へ移してフォルダにする——
といった「ページの置き場所そのものが変わる」操作を扱う。

ページの実体パス（subpath）が変わると、それに紐づくものも一緒に動かないと
参照が切れる。動かすのは次の4つ。

    ページ本体      wiki/<subpath>.<ext>
    添付ファイル    attach/<subpath>/
    バックアップ    pageinfo/backup.db（その記録が指すページ名）
    書きかけ        pageinfo/draft/（.draft と .draft.origin）
    DBの行          pageinfo/wikiall.db（本文・タイトル・目次・リンク）

置き場所の決まりは [ページとフォルダ・削除](/Tech/EditGuide/PageFolder) を参照。
"""
import os

from wikilib.attach import attach_dir_for
from wikilib.backup import move_backups
from wikilib.draft import move_draft
from wikilib.pagedb import rename_page
from wikilib.paths import INDEX_NAME, PAGE_EXTS, entry_subpath_of, page_file_path

# INDEX_NAME（フォルダの入口になるページの名前）の定義は wikilib.paths にある。
# ここから読み込んでいる呼び出し元があるので、名前はそのまま通す。


def page_file_of(wiki_dir, subpath):
    """その実体パスに対応する既存のページファイルを返す。無ければ (None, None)。
    閲覧時と同じく .txt を優先する。"""
    for ext in PAGE_EXTS:
        path = page_file_path(wiki_dir, subpath, ext)
        if path is not None and os.path.isfile(path):
            return path, ext
    return None, None


def move_attach_dir(wiki_dir, old_subpath, new_subpath):
    """添付ファイルの置き場所を移す。無ければ何もしない。

    ページ→フォルダ（X → X/index）とフォルダ→ページ（X/index → X）では
    移動元と移動先が親子になるため、そのまま os.replace すると
    「自分の中へ自分を移す」ことになって失敗する。向きに応じて、
    いったん逃がす／中身を1つずつ持ち上げる、と分けて扱う。"""
    src = attach_dir_for(wiki_dir, old_subpath)
    dst = attach_dir_for(wiki_dir, new_subpath)
    if src is None or dst is None or not os.path.isdir(src):
        return

    try:
        if dst.startswith(src + os.sep):
            # ページ→フォルダ: attach/X → attach/X/index。
            # いったん隣へ逃がしてから入れ直す
            if os.path.exists(dst):
                return
            spare = src.rstrip(os.sep) + ".moving"
            if os.path.exists(spare):
                return  # 前回の移動が途中で終わっている。触らない
            os.replace(src, spare)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(spare, dst)
        elif src.startswith(dst + os.sep):
            # フォルダ→ページ: attach/X/index → attach/X。移動先は src の親なので必ず在る。
            # 中身を1つずつ親へ持ち上げ、空になった src を消す
            for entry in os.listdir(src):
                target = os.path.join(dst, entry)
                if os.path.exists(target):
                    continue  # 同じ名前が親にあれば残す（消さない）
                os.replace(os.path.join(src, entry), target)
            os.rmdir(src)
        else:
            if os.path.exists(dst):
                return
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
    except OSError:
        pass  # 添付が移せなくても、ページの移動そのものは成立させる


def move_page(wiki_dir, config, old_subpath, new_subpath):
    """ページの実体と、それに紐づくものをまとめて移す。移せたらTrue。

    内容は変えないので、バックアップに新しい差分は作らない
    （中身は同じで置き場所だけが変わったため）。"""
    src, ext = page_file_of(wiki_dir, old_subpath)
    if src is None:
        return False
    dst = page_file_path(wiki_dir, new_subpath, ext)
    if dst is None or os.path.exists(dst):
        return False

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.replace(src, dst)
    except OSError:
        return False

    move_page_records(wiki_dir, old_subpath, new_subpath, ext)
    return True


def move_page_records(wiki_dir, old_subpath, new_subpath, ext):
    """ページの実体**以外**（添付・バックアップ・書きかけ・DBの行）を付け替える。

    実体を自分で動かした呼び出し（フォルダごと `os.replace` する
    pagerename.rename_page）からも、同じ後始末を1か所で使えるように
    分けてある。添付は既に動かされていれば何もしない（移動元が無い）ので、
    まとめて動かした側から呼んでも二重にはならない。"""
    move_attach_dir(wiki_dir, old_subpath, new_subpath)
    move_backups(wiki_dir, old_subpath, new_subpath)
    move_draft(wiki_dir, old_subpath, new_subpath)
    rename_page(wiki_dir, old_subpath, new_subpath, ext)


def convert_page_to_folder(wiki_dir, config, subpath):
    """その名前のページをフォルダに変える（`X.md` → `X/index.md`）。

    下位ページを作ろうとしたとき、同じ名前のページが既にあると
    フォルダを作れない。そのページをフォルダの入口へ移して道を空ける。"""
    src, _ = page_file_of(wiki_dir, subpath)
    if src is None:
        return False  # ページが無ければフォルダを作るのに邪魔はしない
    return move_page(wiki_dir, config, subpath, entry_subpath_of(subpath))


def ensure_folder_path(wiki_dir, config, subpath):
    """`subpath` のページを作れるよう、途中の階層をフォルダにしておく。

    `Tech/ChangeLog/2026-08-11` を作るとき、`Tech/ChangeLog` がページだったら
    `Tech/ChangeLog/index` へ移す。移したものの実体パスを一覧で返す。"""
    parts = subpath.split("/")
    moved = []
    for i in range(1, len(parts)):
        ancestor = "/".join(parts[:i])
        if os.path.isdir(os.path.join(wiki_dir, ancestor)):
            continue  # すでにフォルダ
        if convert_page_to_folder(wiki_dir, config, ancestor):
            moved.append(ancestor)
    return moved


def folder_has_only_index(wiki_dir, folder_subpath):
    """そのフォルダの中身が入口ページ（index）だけかどうか。"""
    directory = os.path.join(wiki_dir, folder_subpath)
    if not os.path.isdir(directory):
        return False
    try:
        entries = os.listdir(directory)
    except OSError:
        return False
    if not entries:
        return False
    for entry in entries:
        if os.path.isdir(os.path.join(directory, entry)):
            return False
        stem, ext = os.path.splitext(entry)
        if ext not in PAGE_EXTS or stem != INDEX_NAME:
            return False  # index 以外のものが残っている
    return True


def convert_folder_to_page(wiki_dir, config, folder_subpath):
    """入口ページしか残っていないフォルダを、ふつうのページに戻す
    （`X/index.md` → `X.md` にしてフォルダを消す）。戻せたらTrue。

    下位ページを消したあとに、中身が入口だけになったフォルダを畳むために使う。
    convert_page_to_folder の逆向きで、この2つが揃うことで下位フォルダの
    作成と削除が行き来できるようになる。"""
    if not folder_subpath or not folder_has_only_index(wiki_dir, folder_subpath):
        return False
    # 移動先に同じ名前のページがあってはいけない（あれば畳まない）
    existing, _ = page_file_of(wiki_dir, folder_subpath)
    if existing is not None:
        return False
    if not move_page(wiki_dir, config, entry_subpath_of(folder_subpath), folder_subpath):
        return False
    try:
        os.rmdir(os.path.join(wiki_dir, folder_subpath))
    except OSError:
        pass  # 添付など別のものが残っていれば、フォルダはそのままにしておく
    return True
