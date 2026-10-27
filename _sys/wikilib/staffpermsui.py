"""助手に与える権限を決める画面（`/.admin/staffperms`。**管理者だけ**）。

    GET   表（横に助手、縦に機能。チェックを入れた機能を、その助手に許す）
    POST  表の内容を保存して、同じ画面へ303で戻す

権限の定義・既定・保存は `wikilib.staffperms`。ここは画面を組み立て、送られた内容を
そのまま渡すだけ。

## 管理者だけが開ける理由

**助手が自分に権限を足せてしまうため**、この画面は権限の表に載せない
（`staffperms.ADMIN_ONLY`）。管理者の判定は `sysui.require(..., auth.ADMIN_ONLY)`。

## 表の読みかた

- 縦は機能（画面ごとにまとめた見出しの下に、操作を並べる）。横は助手（`staff` グループの
  メンバーから管理者を除いた人）。**一番左の「既定」の列は、何も設定していないときの状態**
  （この仕組みを入れる前と同じ）で、新しく助手になった人はここから始まる
- 字下げした操作は、直前の操作が前提（`Perm.needs`）。前提を外すと外れ、付けると前提も付く。
  JS（`staffperms.js`）が画面で揃え、サーバー側（`staffperms.save`）も同じ決まりで揃える
- 「既定に戻す」は、その助手の列のチェックを既定の状態へ戻す（保存するまで反映されない）

## 送り方

1つの `<form>`（POST）で、**表示した助手の分をまとめて**送る。`shown` に表示した助手の
番号、`perm.<番号>` にその助手に許す権限の名前。**`shown` に無い助手には触れない**
（画面を開いたあとに増えた助手を、古い画面が「何も許さない」で上書きしないため）。
同時に別の管理者が同じ助手を直したときは、あとに送ったほうが勝つ（行ごとの版は持たない）。

保存した結果は `wikilib.adminlog` に残す（誰が・どの助手に・何を付けた／外した）。
"""
from html import escape

from bottle import HTTPResponse, request

from wikilib import adminlog, auth, staffperms, sysui, userdb
from wikilib.paths import (
    ACCOUNTS_URLPATH, GROUPS_URLPATH, STAFFPERMS_DIR, STAFFPERMS_URLPATH,
)
from wikilib.groups import STAFF_GROUP
from wikilib.themes import make_plugin_context
from wikilib.web import serve_asset

TITLE = "助手の権限"
SAVED_KEY = "saved"
DROPPED_KEY = "dropped"


def serve_staffperms_asset(name):
    """この画面が自前で持つCSS/JS（`/.admin/staffperms.css`・`.js`）。"""
    return serve_asset(STAFFPERMS_DIR, "staffperms", name)


def render_staffperms(wiki_dir, config, farm, explicit_farm):
    """画面。**管理者だけ**が開ける。確かめるのは中身を組み立てる前・POSTを処理する前。"""
    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           STAFFPERMS_URLPATH, auth.ADMIN_ONLY)
    if denied is not None:
        return denied
    base_url = make_plugin_context(config, farm, wiki_dir, STAFFPERMS_URLPATH,
                                   explicit_farm).base_url
    here = f"{base_url}/{STAFFPERMS_URLPATH}"
    actor = auth.current_user(wiki_dir, farm)

    if request.method == "POST":
        saved, dropped = _apply_post(wiki_dir, actor)
        return HTTPResponse(status=303, headers={
            "Location": f"{here}?{SAVED_KEY}={saved}&{DROPPED_KEY}={dropped}"})

    message = _notice_for(request.query.get(SAVED_KEY), request.query.get(DROPPED_KEY))
    body = _html(wiki_dir, here, base_url, message)
    # 共通の acct- のCSSは `sysui.page` が足す。この画面だけのCSS・JSはここで足す
    body += (f'<link rel="stylesheet" href="{escape(here)}.css">'
             f'<script src="{escape(here)}.js"></script>')
    out = sysui.page(wiki_dir, config, farm, explicit_farm, STAFFPERMS_URLPATH, TITLE, body,
                     css_url=f"{ACCOUNTS_URLPATH}.css")
    auth.remember_login(out, config, farm, wiki_dir, explicit_farm, actor)
    return out


def _apply_post(wiki_dir, actor):
    """送られた表を保存する。`(変わった助手の人数, 前提が外れていて許さなかった件数)`。"""
    wanted = {}
    dropped = 0
    for raw in request.forms.getall("shown"):
        try:
            uidnum = int(raw)
        except (TypeError, ValueError):
            continue
        keys = {k for k in request.forms.getall(f"perm.{uidnum}") if k in staffperms.BY_KEY}
        effective = staffperms.resolve({k: k in keys for k in staffperms.BY_KEY})
        dropped += len(keys - effective)
        wanted[uidnum] = keys
    changes = staffperms.save(wiki_dir, wanted)
    for uidnum, added, removed in changes:
        target = userdb.get_user(wiki_dir, uidnum)
        message = "・".join(
            part for part in (
                "許した: " + "、".join(staffperms.BY_KEY[k].label for k in added) if added else "",
                "外した: " + "、".join(staffperms.BY_KEY[k].label for k in removed) if removed else "")
            if part)
        adminlog.record(wiki_dir, actor["uid"], "staffperms", uidnum,
                        target["uid"] if target else "", True, message)
    return len(changes), dropped


def _notice_for(saved, dropped):
    """保存のあとの知らせ。`saved` がなければ（ふつうに開いたとき）何も出さない。"""
    if saved is None:
        return ""
    try:
        n = int(saved)
    except ValueError:
        return ""
    text = f"{n}人の助手の権限を保存しました。" if n else "変更はありませんでした。"
    try:
        lost = int(dropped or 0)
    except ValueError:
        lost = 0
    if lost:
        text += f"前提の権限が外れていたため、{lost}件は許していません。"
    return sysui.notice(text)


def _html(wiki_dir, here, base_url, message):
    assistants = staffperms.assistants(wiki_dir)
    overrides = staffperms.all_overrides(wiki_dir)
    granted = {a["uidnum"]: staffperms.resolve(overrides.get(a["uidnum"], {})) for a in assistants}
    defaults = staffperms.default_set()
    columns = len(assistants) + 2

    head = "".join(_user_head_html(a) for a in assistants)
    rows = []
    current_group = None
    for perm in staffperms.PERMS:
        if perm.group != current_group:
            current_group = perm.group
            name, url = next((n, u) for k, n, u in staffperms.GROUPS if k == perm.group)
            link = (f' <a class="sp-url" href="{escape(base_url)}/{escape(url)}">/{escape(url)}</a>'
                    if url else "")
            rows.append(f'      <tr class="sp-group"><th colspan="{columns}">'
                        f"{escape(name)}{link}</th></tr>")
        rows.append(_perm_row_html(perm, assistants, granted, defaults))

    if assistants:
        table_open = f'<form method="post" action="{escape(here)}" id="sp-form">'
        table_close = """
    <div class="sp-actions">
      <button type="submit" class="acct-go" id="sp-save">保存</button>
      <span id="sp-status" class="acct-bulk-status" role="status" aria-live="polite"></span>
    </div>
  </form>"""
    else:
        table_open = table_close = ""
    empty = ""
    if not assistants:
        staff_url = f"{base_url}/{GROUPS_URLPATH}?tab=edit&group={STAFF_GROUP}"
        empty = (f'<p class="acct-notice acct-notice-error" role="status">助手はまだいません。'
                 f'<a href="{escape(staff_url)}">助手グループ</a>に加えた人が、ここに列として'
                 "並びます（下は既定の状態です）。</p>")

    return f"""{message}
<div class="acct staffperms">
  <p class="acct-lead">助手（助手グループの人）が使える操作を、助手ごとに決めます。
    <strong>チェックを入れた操作だけ</strong>、その助手が使えます。管理者はいつもすべてできます。</p>
  <ul class="acct-hint sp-notes">
    <li><strong>既定</strong>の列は、何も設定していないときの状態です。新しく助手になった人は
      既定から始まります。</li>
    <li>字下げした操作は、直前の操作が前提です。前提を外すと外れ、付けると前提も付きます。</li>
    <li><span class="sp-warn-mark">注意</span>が付いた操作は、許すと、その助手が
      自分に無い権限を間接的に得られることがあります。</li>
    <li>この画面（助手の権限）は、管理者だけが開けます。助手に許すことはできません。</li>
  </ul>
  {empty}
  {table_open}
  <div class="sp-scroll">
  <table class="acct-table sp-table" id="sp-table">
    <thead>
      <tr><th class="sp-func">機能</th><th class="sp-default">既定</th>{head}</tr>
    </thead>
    <tbody>
{chr(10).join(rows)}
    </tbody>
  </table>
  </div>{table_close}
</div>
"""


def _user_head_html(assistant):
    uidnum = assistant["uidnum"]
    return (f'<th class="sp-user" data-uidnum="{uidnum}">'
            f'<code>{escape(assistant["uid"])}</code>'
            f'<span class="sp-name">{escape(assistant["name"] or "")}</span>'
            f'<button type="button" class="sp-reset" data-uidnum="{uidnum}" '
            f'title="この助手の列を既定の状態へ戻す（保存するまで反映されません）">既定に戻す</button>'
            f'<input type="hidden" name="shown" value="{uidnum}"></th>')


def _perm_row_html(perm, assistants, granted, defaults):
    needs = " ".join(perm.needs)
    cls = "sp-perm sp-dep" if perm.needs else "sp-perm"
    warn = (f'<span class="sp-warn"><span class="sp-warn-mark">注意</span>{escape(perm.warn)}</span>'
            if perm.warn else "")
    default_mark = ('<span class="sp-on" title="既定では許す">○</span>' if perm.key in defaults
                    else '<span class="sp-off" title="既定では許さない">−</span>')
    cells = []
    for a in assistants:
        on = perm.key in granted[a["uidnum"]]
        cells.append(
            '<td class="sp-cell">'
            f'<input type="checkbox" name="perm.{a["uidnum"]}" value="{escape(perm.key)}" '
            f'data-key="{escape(perm.key)}" data-needs="{escape(needs)}" '
            f'data-default="{1 if perm.default else 0}" data-uidnum="{a["uidnum"]}"'
            f'{" checked" if on else ""} '
            f'aria-label="{escape(a["uid"])} に「{escape(perm.label)}」を許す"></td>')
    return (f'      <tr class="{cls}" data-key="{escape(perm.key)}">'
            f'<th class="sp-func" scope="row">{escape(perm.label)}{warn}</th>'
            f'<td class="sp-default">{default_mark}</td>{"".join(cells)}</tr>')
