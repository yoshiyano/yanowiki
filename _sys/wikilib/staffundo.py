"""助手の操作を元に戻す（Wiki設計者の指示、2026-09-26）。記録は `wikilib.stafflog`。

**いまの状態が、その操作の直後のままのときだけ戻す。** 後から誰かが書き換えて
いれば断り、確認の画面で前後を見比べてもらう（上書きして後の変更を消さない
ため）。戻したことは記録に書き添える（`stafflog.mark_undone`）。戻すのは管理者で、
管理者の操作は記録しないので、戻したこと自体は新しい記録にはならない。

    undo(wiki_dir, config, farm, entry_id, by_uid) -> (成否, 文言)

戻せない操作（`UNDO` に無い種類。Wikiの作成・Wiki名の変更・再起動）は、
記録を見せるだけ。
"""
import os
import shutil
import subprocess

from wikilib import groups, privilege_records, stafflog, userdb
from wikilib.attach import attach_dir_for
from wikilib.diskusage import invalidate
from wikilib.paths import PAGE_EXTS, pagepath_of_subpath, resolve_page_ref, safe_join

CHANGED = "操作のあとで書き換えられているため、戻しませんでした（前後の内容を見比べてください）。"

# 戻せない種類と、その理由（確認の画面に出す）
NOT_UNDOABLE = {
    "wiki.create": "Wikiを消すには /.delwiki を使ってください（書庫を作ってから消します）。",
    "farm.rename": "名前を戻すには、そのWikiの設定の画面（Wiki名）から変えてください。",
    "restart": "戻すものはありません。",
}


def _write_text(path, text):
    """テキストを書く（None なら消す）。一時ファイルから `rename`。"""
    if text is None:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".undo.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _remove_empty_up(directory, stop_at):
    stop = os.path.realpath(stop_at)
    current = os.path.realpath(directory)
    while current != stop and current.startswith(stop + os.sep):
        try:
            if os.listdir(current):
                return
            os.rmdir(current)
        except OSError:
            return
        current = os.path.dirname(current)


def _page_text(wiki_dir, subpath, ext):
    path = safe_join(wiki_dir, subpath + ext)
    return stafflog.read_text(path) if path else None


def _page_exists(wiki_dir, subpath):
    return any(os.path.isfile(os.path.join(wiki_dir, subpath + ext)) for ext in PAGE_EXTS)


# ---- ページ ------------------------------------------------------------------

def _undo_page_save(wiki_dir, config, farm, entry):
    from wikilib.editor import delete_page
    from wikilib.pagesave import save_page

    subpath, before, after = entry["target"], entry["before"], entry["after"]
    if _page_text(wiki_dir, subpath, after["ext"]) != after["text"]:
        return False, CHANGED
    if before["text"] is None:
        # 新しく作ったページ。消す（添付があれば delete_page が断る）
        ref = resolve_page_ref(wiki_dir, pagepath_of_subpath(subpath))
        if ref is None:
            return False, "ページを特定できませんでした。"
        return delete_page(wiki_dir, config, ref)
    if not save_page(wiki_dir, config, subpath, before["ext"], before["text"], merge=False):
        return False, "書き戻せませんでした。"
    return True, "保存する前の内容に戻しました。"


def _undo_page_delete(wiki_dir, config, farm, entry):
    from wikilib.pagesave import save_page

    subpath, before = entry["target"], entry["before"]
    if _page_exists(wiki_dir, subpath):
        return False, "同じ名前のページがすでにあります。" + CHANGED
    if before["text"] is None:
        return False, "消す前の内容が記録にありません。"
    if not save_page(wiki_dir, config, subpath, before["ext"], before["text"], merge=False):
        return False, "作り直せませんでした。"
    return True, "消す前の内容でページを作り直しました。"


def _undo_page_rename(wiki_dir, config, farm, entry):
    from wikilib.pagerename import rename_page, rename_root_of, split_name

    old_sub, new_sub = entry["before"]["subpath"], entry["after"]["subpath"]
    if not _page_exists(wiki_dir, new_sub):
        return False, "改名した先のページがありません。" + CHANGED
    old_root = rename_root_of(old_sub)
    if _page_exists(wiki_dir, old_root) or os.path.exists(os.path.join(wiki_dir, old_root)):
        return False, "元の名前がすでに使われています。" + CHANGED
    parent, name = split_name(old_root)
    ok, message, _ = rename_page(wiki_dir, config, new_sub, name, parent or "")
    return ok, (message if ok else "戻せませんでした（{}）".format(message))


# ---- 添付 --------------------------------------------------------------------

def _attach_path(wiki_dir, subpath, name):
    directory = attach_dir_for(wiki_dir, subpath)
    return None if directory is None else os.path.join(directory, name)


def _restore_blob(wiki_dir, entry, blob, dst):
    src = os.path.join(stafflog.blob_dir(wiki_dir, entry["id"]), blob)
    if not os.path.isfile(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _undo_attach_put(wiki_dir, config, farm, entry):
    before, after = entry["before"], entry["after"]
    path = _attach_path(wiki_dir, entry["target"], after["name"])
    if path is None or stafflog.file_sha(path) != after["sha"]:
        return False, CHANGED
    if before["sha"] is None:
        os.remove(path)
        _remove_empty_up(os.path.dirname(path), os.path.join(os.path.dirname(wiki_dir), "attach"))
        invalidate(wiki_dir)
        return True, f"追加された「{after['name']}」を消しました。"
    if not (before.get("blob") and _restore_blob(wiki_dir, entry, before["blob"], path)):
        return False, "上書きされる前の中身が控えにありません。"
    invalidate(wiki_dir)
    return True, f"「{after['name']}」を上書きされる前の中身に戻しました。"


def _undo_attach_delete(wiki_dir, config, farm, entry):
    before = entry["before"]
    path = _attach_path(wiki_dir, entry["target"], before["name"])
    if path is None or os.path.exists(path):
        return False, "同じ名前のファイルがすでにあります。" + CHANGED
    if not (before.get("blob") and _restore_blob(wiki_dir, entry, before["blob"], path)):
        return False, "消す前の中身が控えにありません。"
    invalidate(wiki_dir)
    return True, f"「{before['name']}」を戻しました。"


def _undo_attach_relocate(wiki_dir, config, farm, entry):
    """名前の変更・別ページへの移動を戻す（どちらも「場所Aから場所Bへ」）。"""
    before, after = entry["before"], entry["after"]
    src = _attach_path(wiki_dir, after["subpath"], after["name"])
    dst = _attach_path(wiki_dir, before["subpath"], before["name"])
    if src is None or dst is None or stafflog.file_sha(src) != after["sha"]:
        return False, CHANGED
    if os.path.exists(dst):
        return False, "元の場所に同じ名前のファイルがあります。" + CHANGED
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)
    # 置き換えられていたファイルがあれば、元の場所へ戻す
    if before.get("blob"):
        _restore_blob(wiki_dir, entry, before["blob"], src)
    else:
        _remove_empty_up(os.path.dirname(src), os.path.join(os.path.dirname(wiki_dir), "attach"))
    invalidate(wiki_dir)
    return True, f"「{before['name']}」を元の場所・名前に戻しました。"


# ---- 管理の画面 ----------------------------------------------------------------

def _undo_config_file(wiki_dir, config, farm, entry):
    path = safe_join(os.path.dirname(wiki_dir), entry["target"])
    if path is None:
        return False, "設定ファイルを特定できませんでした。"
    if stafflog.read_text(path) != entry["after"]["text"]:
        return False, CHANGED
    _write_text(path, entry["before"]["text"])
    return True, "変える前の設定に戻しました。"


def _undo_privileges(wiki_dir, config, farm, entry):
    page = entry["target"]
    entries = privilege_records.load(wiki_dir)
    if [e for e in entries if e["page"] == page] != entry["after"]:
        return False, CHANGED
    kept = [e for e in entries if e["page"] != page] + list(entry["before"] or [])
    if not privilege_records.save(wiki_dir, kept):
        return False, "アクセス制限の記録を書き換えられませんでした。"
    return True, f"«{page}» のアクセス制限を操作の前に戻しました。"


def _undo_group(wiki_dir, config, farm, entry):
    gname = entry["target"]
    if groups.member_rows(wiki_dir, gname) != entry["after"]:
        return False, CHANGED
    if not groups.set_member_rows(wiki_dir, gname, entry["before"] or []):
        return False, "グループを書き換えられませんでした。"
    return True, f"«{gname}» のメンバーを操作の前に戻しました。"


def _undo_approve(wiki_dir, config, farm, entry):
    row = entry["before"]["user"]
    user = userdb.get_user(wiki_dir, row["uidnum"])
    if user is None or user["uid"] != row["uid"] or not userdb.is_approved(user):
        return False, CHANGED
    ok, message = userdb.set_approved(wiki_dir, row["uidnum"], False)
    return ok, ("«{}» を承認待ちに戻しました。".format(row["uid"]) if ok else message)


def _undo_reject(wiki_dir, config, farm, entry):
    row = entry["before"]["user"]
    ok, message = userdb.restore_user(wiki_dir, row)
    if not ok:
        return False, message
    for gname in entry["before"].get("groups") or []:
        groups.add_members(wiki_dir, gname, [row["uid"]])
    return True, "«{}» を承認待ちのアカウントとして入れ直しました。".format(row["uid"])


def _undo_garbagecollect(wiki_dir, config, farm, entry):
    from wikilib.garbagecollect import TRASHBOX_PAGE

    moved = entry["after"]["moved"]
    plan = []
    for sub, name, new, sha in moved:
        src = _attach_path(wiki_dir, TRASHBOX_PAGE, new)
        dst = _attach_path(wiki_dir, sub, name)
        if src is None or dst is None or stafflog.file_sha(src) != sha:
            return False, f"trashbox の「{new}」が無いか変わっています。" + CHANGED
        if os.path.exists(dst):
            return False, f"元の場所に「{sub}/{name}」があります。" + CHANGED
        plan.append((src, dst))
    for src, dst in plan:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(src, dst)
    invalidate(wiki_dir)
    return True, f"{len(plan)}件を元の場所へ戻しました。"


def _undo_wiki_delete(wiki_dir, config, farm, entry):
    from wikilib import delwiki

    name, archive = entry["before"]["name"], entry["before"]["archive"]
    root = delwiki.wikidata_dir()
    if os.path.exists(os.path.join(root, name)):
        return False, f"「{name}」がすでにあります。" + CHANGED
    path = os.path.join(root, archive)
    if not os.path.isfile(path):
        return False, f"書庫（{archive}）が見つかりません。"
    program = delwiki.sevenzip_program()
    if program is None:
        return False, "7z を展開する道具が見つかりません。"
    try:
        done = subprocess.run([program, "x", "-y", "-bd", "-o" + root, "--", path],
                              capture_output=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"展開できませんでした（{e}）。"
    if done.returncode != 0 or not os.path.isdir(os.path.join(root, name)):
        return False, "展開できませんでした（7z が {} で終わりました）。".format(done.returncode)
    return True, f"「{name}」を書庫から戻しました。"


UNDO = {
    "page.save": _undo_page_save,
    "page.delete": _undo_page_delete,
    "page.rename": _undo_page_rename,
    "attach.put": _undo_attach_put,
    "attach.delete": _undo_attach_delete,
    "attach.rename": _undo_attach_relocate,
    "attach.move": _undo_attach_relocate,
    "config.file": _undo_config_file,
    "privileges.page": _undo_privileges,
    "group.members": _undo_group,
    "account.approve": _undo_approve,
    "account.reject": _undo_reject,
    "garbagecollect": _undo_garbagecollect,
    "wiki.delete": _undo_wiki_delete,
}


def undoable(entry):
    return entry["kind"] in UNDO and entry.get("undone_at") is None


def undo(wiki_dir, config, farm, entry_id, by_uid):
    """記録1件を元に戻す。`(成否, 文言)`。"""
    entry = stafflog.get(wiki_dir, entry_id)
    if entry is None:
        return False, "その記録はありません。"
    if entry.get("undone_at") is not None:
        return False, "この操作はすでに戻してあります。"
    handler = UNDO.get(entry["kind"])
    if handler is None:
        return False, NOT_UNDOABLE.get(entry["kind"], "この操作は戻せません。")
    try:
        with stafflog.quiet():
            ok, message = handler(wiki_dir, config, farm, entry)
    except (OSError, KeyError, TypeError, ValueError) as e:
        return False, f"戻せませんでした（{e}）。"
    if ok:
        stafflog.mark_undone(wiki_dir, entry_id, by_uid, message)
    return ok, message
