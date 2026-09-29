"""ユーザーが自分で作れる汎用グループの画面（/.groups）。

    /.groups                窓口。**ログインしていれば誰でも開ける**
                            （Wiki設計者の指示、2026-09-12）
    /.groups?tab=create     グループ作成タブ（既定）
    /.groups?tab=edit&group=<グループ名>
                            グループ編集タブ。**そのグループを編集できる
                            人だけ**が中身（一覧・追加フォーム）を見られる
    /.groups/api            一覧の追加・削除を受けるJSON API

助手グループの管理も、ここに統合されている（Wiki設計者の指示、2026-09-12。
`wikilib.groups.STAFF_GROUP` = `"staff"`）。判断の中心は `wikilib.groups`
（編集できるか・グループの有無）で、ここは画面の組み立てとAPIの受け口だけを
持つ（`wikilib.accounts` と `wikilib.userdb` の分けかたと同じ）。

## タブは「いま見えているものだけ」

作成・編集の2つのフォームは**同時に入力できない**（Wiki設計者の指示）。
サーバー側はクエリ（`tab`）でどちらを表示するかを決めて返し、画面を開いた
直後からその状態になっている。JS（`groups.js`）はタブボタンを押したときに
もう一方を隠すだけで、フォームの中身までは触らない。

## 編集タブは「グループ名を自分で入れて開く」だけ（Wiki設計者の指示、2026-09-12）

所属グループの一覧は出さない。**そのグループの名前を知っている・編集
できる**ことが、そのグループの中身を見られる条件そのもの（`?group=`が
無ければ入力欄だけを見せる）。

## 編集できるのはメンバーだけではない（Wiki設計者の指示、2026-09-12）

`foo`グループの編集権は **`g:foo`・`admin`・`g:staff`** の誰か
（`wikilib.groups.can_edit`）。管理者と助手（`staff`グループのメンバー）は、
自分が入っていないグループも編集できる——他のグループを見渡す・
手直しできるようにするための、意図した抜け道である。

## 追加・削除はAPI（Wiki設計者の指示、2026-09-12）

チェックした複数ユーザーの削除、スペース/カンマ区切りで入れた複数ユーザーの
追加は、それぞれ**1回のJSON API呼び出しでまとめて**送る（`groups.js`）。
1件ごとに何が起きたか（追加できた／できなかった理由）はAPIの応答に含めて
返す（`wikilib.groups.add_members`）。
"""
import contextlib
import datetime
from html import escape
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib import auth, groups, stafflog, sysui, userdb
from wikilib.paths import GROUPS_DIR, GROUPS_URLPATH
from wikilib.themes import make_plugin_context
from wikilib.web import serve_asset

# この画面が自前で持つCSS（`/.groups.css`）。
GROUPS_CSS = f"{GROUPS_URLPATH}.css"


def serve_groups_asset(name):
    """`/.groups` が自前で持つCSS/JS（`/.groups.css`・`/.groups.js`）。"""
    return serve_asset(GROUPS_DIR, "groups", name)


def render_groups(wiki_dir, config, farm, explicit_farm):
    """`/.groups` の画面。GETで表示、POSTは「グループを作る」フォームだけを受ける。"""
    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           GROUPS_URLPATH, auth.ANY_USER)
    if denied is not None:
        return denied
    actor = auth.current_user(wiki_dir, farm)

    message, ok = "", True
    if request.method == "POST":
        gname = (request.forms.getunicode("gname", "") or "").strip()
        with _staff_group(wiki_dir, farm, gname, "作った"):
            ok, message = groups.create_group(wiki_dir, gname, actor["uidnum"])
        if ok:
            # 作れたら、そのまま編集タブでそのグループを開いた状態へ送る。
            # 作成者はその場でメンバーなので、続けてユーザーを追加できる
            base_url = make_plugin_context(
                config, farm, wiki_dir, GROUPS_URLPATH, explicit_farm).base_url
            return HTTPResponse(status=303, headers={
                "Location": f"{base_url}/{GROUPS_URLPATH}?tab=edit&group={urlquote(gname)}",
            })

    group_query = (request.query.getunicode("group", "") or "").strip()
    tab = request.query.get("tab") or ("edit" if group_query else "create")
    if tab not in ("create", "edit"):
        tab = "create"

    base_url = make_plugin_context(config, farm, wiki_dir, GROUPS_URLPATH, explicit_farm).base_url
    body = _groups_html(wiki_dir, actor, tab, group_query, message, ok, base_url)
    body += f'<script src="{escape(base_url)}/{GROUPS_URLPATH}.js"></script>'
    return sysui.page(wiki_dir, config, farm, explicit_farm, GROUPS_URLPATH,
                      "グループ", body, css_url=GROUPS_CSS)


def render_groups_api(wiki_dir, config, farm, explicit_farm):
    """一覧の追加・削除を受けるJSON API（`/.groups/api`）。

    受け取るのはJSON。

        {"cmd": "add", "group": "…", "uids": ["a", "b"]}
        {"cmd": "remove", "group": "…", "uidnums": [2, 5]}

    **編集権が無ければ断る。** グループ編集は「g:<グループ名>・admin・
    g:staff の誰か」ができる（Wiki設計者の指示、2026-09-12。`wikilib.groups.
    can_edit`）。それ以外の相手には、どちらの操作も許さない。"""
    actor = auth.current_user(wiki_dir, farm)
    if actor is None:
        return sysui.json_out({"ok": False, "message": "ログインしてください。"}, status=403)

    body = sysui.json_body()
    cmd = body.get("cmd") or ""
    gname = (body.get("group") or "").strip()

    problem = groups.check_gname(gname)
    if problem:
        return sysui.json_out({"ok": False, "message": problem}, status=400)
    if not auth.can_edit_group(wiki_dir, gname, actor["uidnum"]):
        return sysui.json_out({"ok": False, "message": "このグループを編集する権限がありません。"}, status=403)

    if cmd == "add":
        raw = body.get("uids")
        if not isinstance(raw, list):
            return sysui.json_out({"ok": False, "message": "追加するIDを指定してください。"}, status=400)
        uids = [str(u).strip() for u in raw if str(u).strip()]
        if not uids:
            return sysui.json_out({"ok": False, "message": "追加するIDを指定してください。"}, status=400)
        with _staff_group(wiki_dir, farm, gname, "メンバーを加えた"):
            added, failed = groups.add_members(wiki_dir, gname, uids)
        return sysui.json_out({
            "ok": True,
            "added": [_member_json(m) for m in added],
            "failed": failed,
        })
    if cmd == "remove":
        raw = body.get("uidnums")
        if not isinstance(raw, list):
            return sysui.json_out({"ok": False, "message": "削除する対象を指定してください。"}, status=400)
        try:
            uidnums = [int(n) for n in raw]
        except (TypeError, ValueError):
            return sysui.json_out({"ok": False, "message": "削除する対象が正しくありません。"}, status=400)
        with _staff_group(wiki_dir, farm, gname, "メンバーを外した"):
            removed = groups.remove_members(wiki_dir, gname, uidnums)
        return sysui.json_out({"ok": True, "removed": removed})
    return sysui.json_out({"ok": False, "message": "知らない操作です。"}, status=400)


@contextlib.contextmanager
def _staff_group(wiki_dir, farm, gname, what):
    """助手の操作なら、グループのメンバーを前後で控えて記録する（wikilib.stafflog）。"""
    staff = stafflog.actor(wiki_dir, farm)
    before = groups.member_rows(wiki_dir, gname) if staff is not None else None
    yield
    if staff is None:
        return
    after = groups.member_rows(wiki_dir, gname)
    if after != before:
        stafflog.record(wiki_dir, staff, "group.members", gname, what,
                        before=before, after=after)


def _member_json(m):
    return {"uid": m["uid"], "name": m["name"], "uidnum": m["uidnum"],
           "joined_at": m["joined_at"], "joined_label": _format_time(m["joined_at"])}


def _format_time(unixtime):
    return datetime.datetime.fromtimestamp(unixtime).strftime("%Y-%m-%d %H:%M")


def _groups_html(wiki_dir, actor, tab, group_query, message, ok, base_url):
    if not userdb.exists(wiki_dir):
        return f"""{sysui.notice(message, bad=not ok, prefix="grp")}
<div class="grp">
  <p class="grp-lead">このWikiにはアカウントの記録がまだありません。
    グループはアカウントに紐づくため、先にアカウントを用意してください。</p>
  <pre><code>./wiki.py initusers</code></pre>
</div>
"""
    create_notice = sysui.notice(message, bad=not ok, prefix="grp") if tab == "create" else ""
    api_url = f"{escape(base_url)}/{GROUPS_URLPATH}/api"
    return f"""<div class="grp" data-api="{api_url}">
  <div class="grp-tabs" role="tablist">
    <button type="button" class="grp-tab-btn{' grp-tab-active' if tab == 'create' else ''}"
            data-tab="create" role="tab" aria-selected="{'true' if tab == 'create' else 'false'}">
      グループ作成</button>
    <button type="button" class="grp-tab-btn{' grp-tab-active' if tab == 'edit' else ''}"
            data-tab="edit" role="tab" aria-selected="{'true' if tab == 'edit' else 'false'}">
      グループ編集</button>
  </div>

  <div class="grp-panel" data-panel="create"{'' if tab == 'create' else ' hidden'}>
    {create_notice}
    <form class="grp-form" method="post">
      <div class="grp-row">
        <label for="grp-create-name">グループ名</label>
        <input id="grp-create-name" type="text" name="gname" autocomplete="off" required
               pattern="[a-z0-9_-]+"
               title="半角の小文字・数字・ハイフン(-)・アンダースコア(_)が使えます">
      </div>
      <p class="grp-hint">半角の小文字・数字・ハイフン(-)・アンダースコア(_)で
        名前を決めてください。すでにあるグループ名は使えません。作成した人は、
        そのままメンバーに加わります。</p>
      <div class="grp-actions">
        <button type="submit" class="grp-go">作成</button>
      </div>
    </form>
  </div>

  <div class="grp-panel" data-panel="edit"{'' if tab == 'edit' else ' hidden'}>
    <form class="grp-open-form" method="get">
      <input type="hidden" name="tab" value="edit">
      <div class="grp-row">
        <label for="grp-open-name">グループ名</label>
        <input id="grp-open-name" type="text" name="group" autocomplete="off" required
               pattern="[a-z0-9_-]+" value="{escape(group_query)}">
      </div>
      <div class="grp-actions">
        <button type="submit" class="grp-go">開く</button>
      </div>
    </form>
{_group_detail_html(wiki_dir, actor, group_query, message, ok) if tab == 'edit' else ''}
  </div>
</div>
"""


def _group_detail_html(wiki_dir, actor, gname, message, ok):
    if not gname:
        return ""
    problem = groups.check_gname(gname)
    if problem:
        return sysui.notice(problem, bad=True, prefix="grp")
    if not groups.exists(wiki_dir, gname):
        return sysui.notice(f"«{escape(gname)}» というグループはありません。"
                            "「グループ作成」タブから作れます。",
                            bad=True, prefix="grp")
    if not auth.can_edit_group(wiki_dir, gname, actor["uidnum"]):
        return sysui.notice(f"«{escape(gname)}» を編集する権限がありません。", bad=True, prefix="grp")

    rows = "\n".join(_member_row_html(m) for m in groups.members(wiki_dir, gname))
    api_notice = sysui.notice(message, bad=not ok, prefix="grp")
    return f"""
{api_notice}
<div class="grp-members" data-group="{escape(gname)}">
  <h2 class="grp-h2">«{escape(gname)}» のメンバー</h2>

  <div class="grp-bulk-actions">
    <button type="button" id="grp-remove-btn" class="grp-go grp-del" disabled>
      選んだユーザを削除</button>
    <span id="grp-remove-status" class="grp-bulk-status" role="status" aria-live="polite"></span>
  </div>

  <table class="grp-table" id="grp-member-table">
    <thead>
      <tr>
        <th></th>
        <th class="grp-sortable" data-sort="uid">ユーザー名</th>
        <th>表示名</th>
        <th class="grp-sortable" data-sort="joined">登録日時</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>

  <h2 class="grp-h2">ユーザを追加する</h2>
  <div class="grp-add">
    <textarea id="grp-add-input" class="grp-add-textarea" rows="2"
              placeholder="ユーザー名をスペースまたはカンマ区切りで入力"></textarea>
    <div class="grp-actions">
      <button type="button" id="grp-add-btn" class="grp-go">追加</button>
      <span id="grp-add-status" class="grp-bulk-status" role="status" aria-live="polite"></span>
    </div>
  </div>
</div>
"""


def _member_row_html(m):
    return f"""      <tr data-uidnum="{m['uidnum']}" data-uid="{escape(m['uid'])}"
          data-joined="{m['joined_at']}">
        <td><input type="checkbox" class="grp-check" data-uidnum="{m['uidnum']}"
                   aria-label="{escape(m['uid'])}を削除の対象に選ぶ"></td>
        <td>{escape(m['uid'])}</td>
        <td>{escape(m['name'])}</td>
        <td>{_format_time(m['joined_at'])}</td>
      </tr>"""
