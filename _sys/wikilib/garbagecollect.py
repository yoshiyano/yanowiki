"""削除したページの添付ファイルを、ページ `trashbox` へ集める（`/.garbagecollect`。
Wiki設計者の指示、2026-09-25）。

ページのファイルを消しても（エディタ・`git` などでの直接の削除、改名の残り物）、
`attach/<ページ>/` の添付は残り続け、どのページからも辿れなくなる。ここで
**持ち主のページが無い添付**を見つけ、ページ `trashbox` の添付へ移す。

    /.garbagecollect            管理者と助手。GETで確認の画面、POSTで実行
    pagesync.start_watcher      1時間ごとの取り込みのあとにも、全Wikiで行う
                                （/.updatePageAuth の後始末と同じタイミング）

## 移すもの

`attach/` の下でファイルを持つフォルダのうち、そのパスのページ（`X.txt`・`X.md`）が
無いものすべて（Wiki設計者の指示。まだ作っていないページに先に置いた添付も、
ファイルの上では区別が付かないので移す）。次のものは移さない。

    書きかけがある      そのページを書いている途中（pageinfo/draft/）
    trashbox 自身       集め先そのもの
    移動の途中          pagemove が一時的に使う `X.moving`

## 移した先の名前

`元フォルダ名__ファイル名`。元フォルダ名は attach/ からのパスで、区切りの `/` を `_` に
置き換える（`講義/第01回/a.png` → `講義_第01回__a.png`）。同じ名前が trashbox に
あれば、拡張子の前に `_2`・`_3`… を付けて上書きしない。

## trashbox は管理者と助手だけ

添付は持ち主のページの閲覧権限で配信される。閲覧を絞っていたページの添付が
誰でも読める trashbox へ移ると、制限が外れてしまう。そこで trashbox の `R`・`W` が
`config/privileges` に無ければ、`admin, g:staff` で書き足す（Wiki設計者の指示）。
すでに行があれば触らない（誰かが決めた権限を上書きしない）。**書き足せなかった
ときは移さない**（制限の無いところへ置かないため）。ページは `#attachls` だけの
PukiWiki記法のページとして作る（Wiki設計者の指示）。
"""
import os
from html import escape

from bottle import request

from wikilib import auth, privilege_records
from wikilib.attach import attach_dir_for, has_attach_files, safe_attach_name
from wikilib.diskusage import invalidate
from wikilib.draft import drafted_subpaths
from wikilib.paths import FARM_PREFIX, GARBAGECOLLECT_URLPATH, PAGE_EXTS, SYSTEM_PREFIX

TRASHBOX_PAGE = "trashbox"
TRASHBOX_EXT = ".txt"
TRASHBOX_BODY = "#attachls\n"
TRASHBOX_WHO = "admin, g:staff"
MOVING_SUFFIX = ".moving"  # pagemove.move_attach_dir が一時的に使う名前


def attach_root_of(wiki_dir):
    return os.path.join(os.path.dirname(wiki_dir), "attach")


def page_exists(wiki_dir, subpath):
    return any(os.path.isfile(os.path.join(wiki_dir, subpath + ext)) for ext in PAGE_EXTS)


def find_orphans(wiki_dir):
    """持ち主のページが無い添付。`[(実体パス, [ファイル名, …]), …]`（パス順）。"""
    root = attach_root_of(wiki_dir)
    if not os.path.isdir(root):
        return []
    drafts = set(drafted_subpaths(wiki_dir))
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith((FARM_PREFIX, SYSTEM_PREFIX))
                             and not d.endswith(MOVING_SUFFIX))
        if dirpath == root:
            continue  # attach/ 直下のファイル（README.txt など）はページの添付ではない
        sub = os.path.relpath(dirpath, root).replace(os.sep, "/")
        files = sorted(f for f in filenames if os.path.isfile(os.path.join(dirpath, f)))
        if not files or sub == TRASHBOX_PAGE:
            continue
        if page_exists(wiki_dir, sub) or sub in drafts:
            continue
        found.append((sub, files))
    return sorted(found)


def trash_name(subpath, name):
    """移した先のファイル名（`元フォルダ名__ファイル名`、区切りの `/` は `_`）。"""
    return safe_attach_name(subpath.replace("/", "_") + "__" + name)


def _free_name(directory, name):
    """directory に無い名前を返す。あれば拡張子の前に `_2`・`_3`… を付ける。"""
    stem, ext = os.path.splitext(name)
    candidate, n = name, 2
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{stem}_{n}{ext}"
        n += 1
    return candidate


def _remove_empty_up(directory, stop_at):
    """移し終えて空になったフォルダを、attach/ の手前まで上へたどって消す。"""
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


def ensure_trashbox(wiki_dir, config):
    """trashbox の権限の行とページを用意する。用意できたら True。

    権限を先に書く。ページや添付を置いたあとで権限が書けないと、その間だけ
    誰でも読めるため。"""
    entries = privilege_records.load(wiki_dir)
    for kind in (privilege_records.READ, privilege_records.WRITE):
        if privilege_records.find(entries, TRASHBOX_PAGE, kind) is not None:
            continue
        ok, _message, entries = privilege_records.put(wiki_dir, TRASHBOX_PAGE, kind,
                                                      TRASHBOX_WHO)
        if not ok:
            return False
    if not page_exists(wiki_dir, TRASHBOX_PAGE):
        from wikilib.pagesave import save_page  # 循環を避けるため呼び出し時に読み込む
        if not save_page(wiki_dir, config, TRASHBOX_PAGE, TRASHBOX_EXT, TRASHBOX_BODY):
            return False
    return True


def collect(wiki_dir, config):
    """持ち主のページが無い添付を trashbox へ移す。

    `{"moved": [(元の実体パス, 元の名前, 移した名前), …], "ready": 用意できたか}`。"""
    orphans = find_orphans(wiki_dir)
    # trashbox のページだけが消されていたときも、添付の持ち主を作り直す
    if not orphans and (page_exists(wiki_dir, TRASHBOX_PAGE)
                        or not has_attach_files(wiki_dir, TRASHBOX_PAGE)):
        return {"moved": [], "ready": True}
    if not ensure_trashbox(wiki_dir, config):
        return {"moved": [], "ready": False}

    dst_dir = attach_dir_for(wiki_dir, TRASHBOX_PAGE)
    root = attach_root_of(wiki_dir)
    moved = []
    for sub, files in orphans:
        src_dir = attach_dir_for(wiki_dir, sub)
        if src_dir is None:
            continue
        for name in files:
            new_name = trash_name(sub, name)
            if new_name is None:
                continue
            os.makedirs(dst_dir, exist_ok=True)
            new_name = _free_name(dst_dir, new_name)
            try:
                os.replace(os.path.join(src_dir, name), os.path.join(dst_dir, new_name))
            except OSError:
                continue
            moved.append((sub, name, new_name))
        _remove_empty_up(src_dir, root)
    if moved:
        invalidate(wiki_dir)
    return {"moved": moved, "ready": True}


def collect_all(log=None):
    """全Wikiで `collect` を行う（1時間ごとの取り込みのあと。pagesync.start_watcher）。"""
    from wikilib.pagesync import wiki_names
    from wikilib.paths import farm_wiki_dir
    from wikilib.wikiconfig import load_wiki_config

    for name in wiki_names():
        wiki_dir = farm_wiki_dir(name)
        if wiki_dir is None:
            continue
        try:
            result = collect(wiki_dir, load_wiki_config(wiki_dir))
        except Exception:  # 1つのWikiの失敗で、ほかのWikiを止めない
            continue
        if log is None:
            continue
        if result["moved"]:
            log("削除したページの添付: [{}] {}件を /{} へ移しました".format(
                name, len(result["moved"]), TRASHBOX_PAGE))
        elif not result["ready"]:
            log("削除したページの添付: [{}] /{} の権限かページを用意できず、移していません".format(
                name, TRASHBOX_PAGE))


# ---- /.garbagecollect -------------------------------------------------------

def serve_garbage_collect(wiki_dir, config, farm, explicit_farm):
    """`/.garbagecollect`。**管理者と助手**（Wiki設計者の指示）。GETで確認、POSTで実行。

    リンクを踏んだだけで動かないよう、実行はPOSTだけにしてある（`/.restart` と同じ）。"""
    from wikilib import sysui  # 循環を避けるため呼び出し時に読み込む
    from wikilib.paths import ACCOUNTS_URLPATH
    from wikilib.themes import make_plugin_context

    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           GARBAGECOLLECT_URLPATH, auth.STAFF)
    if denied is not None:
        return denied
    context = make_plugin_context(config, farm, wiki_dir, GARBAGECOLLECT_URLPATH, explicit_farm)
    base = escape(context.base_url)
    trash_link = f'<a href="{base}/{TRASHBOX_PAGE}">/{TRASHBOX_PAGE}</a>'

    if request.method == "POST":
        from wikilib import stafflog

        staff = stafflog.actor(wiki_dir, farm)
        with stafflog.quiet():  # trashbox のページ・権限の用意は、この1件にまとめる
            result = collect(wiki_dir, config)
        if staff is not None and result["moved"]:
            stafflog.record(
                wiki_dir, staff, "garbagecollect", TRASHBOX_PAGE,
                f"{len(result['moved'])}件を /{TRASHBOX_PAGE} へ移した", before=None,
                after={"moved": [[sub, name, new, stafflog.file_sha(
                    os.path.join(attach_dir_for(wiki_dir, TRASHBOX_PAGE), new))]
                    for sub, name, new in result["moved"]]})
        if not result["ready"]:
            body = (f"<p>/{TRASHBOX_PAGE} の権限かページを用意できなかったため、"
                    "何も移していません。</p>")
        elif result["moved"]:
            rows = "".join(
                f"<tr><td><code>{escape(sub)}/{escape(name)}</code></td>"
                f"<td><code>{escape(new)}</code></td></tr>"
                for sub, name, new in result["moved"])
            body = (f"<p>{len(result['moved'])}件を {trash_link} へ移しました。</p>"
                    '<table class="acct-table"><thead><tr><th>元の場所</th>'
                    f"<th>移した名前</th></tr></thead><tbody>{rows}</tbody></table>")
        else:
            body = "<p>移す添付はありませんでした。</p>"
    else:
        orphans = find_orphans(wiki_dir)
        count = sum(len(files) for _sub, files in orphans)
        if orphans:
            rows = "".join(
                f"<tr><td><code>{escape(sub)}</code></td><td>{len(files)}</td></tr>"
                for sub, files in orphans)
            listing = ('<table class="acct-table"><thead><tr><th>元の場所（attach/ から）</th>'
                       f"<th>ファイル数</th></tr></thead><tbody>{rows}</tbody></table>")
        else:
            listing = "<p>いまは移す添付はありません。</p>"
        body = (f"<p>削除したページ（持ち主のページが無い）の添付ファイルを {trash_link} へ"
                f"移します。いま{count}件あります。</p>"
                f"<p>移した先の名前は <code>元フォルダ名__ファイル名</code> です。"
                f"/{TRASHBOX_PAGE} は管理者と助手だけが開けます。"
                "1時間ごとにも自動で行います。</p>"
                f"{listing}"
                f'<form method="post" action="{base}/{GARBAGECOLLECT_URLPATH}" style="margin-top: 1em">'
                '<button type="submit">移す</button></form>')
    return sysui.page(wiki_dir, config, farm, explicit_farm, GARBAGECOLLECT_URLPATH,
                      "削除したページの添付を集める", f'<div class="acct">{body}</div>',
                      css_url=f"{ACCOUNTS_URLPATH}.css")
