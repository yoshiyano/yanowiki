"""助手の操作の記録を確かめる画面（`/.admin/stafflog`。**管理者だけ**。Wiki設計者の
指示、2026-09-26）。記録は `wikilib.stafflog`、戻しかたは `wikilib.staffundo`。

    /.admin/stafflog              一覧（新しい順。?actor=<ID> で助手を絞る、?page=2 で次へ）
    /.admin/stafflog?id=<番号>    1件の詳細（操作の前と後）。戻せるものは「元に戻す」
    POST id=<番号>                元に戻す

管理者だけにしてあるのは、記録に**操作の前後の中身**（ページの本文・設定・
アカウントの行）が入り、戻す操作は助手自身の作業を取り消すものだから。
"""
import datetime
import difflib
import json
from html import escape
from urllib.parse import quote

from bottle import request

from wikilib import auth, stafflog, staffundo, sysui
from wikilib.paths import ACCOUNTS_URLPATH, STAFFLOG_URLPATH, pagepath_of_subpath
from wikilib.themes import make_plugin_context

PER_PAGE = 100
TITLE = "助手の操作の記録"


def render_stafflog(wiki_dir, config, farm, explicit_farm):
    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           STAFFLOG_URLPATH, auth.ADMIN_ONLY)
    if denied is not None:
        return denied
    base = make_plugin_context(config, farm, wiki_dir, STAFFLOG_URLPATH,
                               explicit_farm).base_url
    here = f"{base}/{STAFFLOG_URLPATH}"

    notice = ""
    entry_id = request.forms.get("id") if request.method == "POST" else request.query.get("id")
    if request.method == "POST" and entry_id:
        user = auth.current_user(wiki_dir, farm)
        ok, message = staffundo.undo(wiki_dir, config, farm, entry_id, user["uid"])
        cls = "acct-notice" if ok else "acct-notice acct-notice-error"
        notice = f'<div class="{cls}" role="status">{escape(message)}</div>'

    if entry_id:
        entry = stafflog.get(wiki_dir, entry_id)
        body = notice + (_detail_html(entry, here, wiki_dir) if entry is not None
                         else "<p>その記録はありません。</p>")
    else:
        body = _list_html(wiki_dir, here)
    return sysui.page(wiki_dir, config, farm, explicit_farm, STAFFLOG_URLPATH, TITLE,
                      f'<div class="acct stafflog">{body}</div>',
                      css_url=f"{ACCOUNTS_URLPATH}.css")


def _time(unixtime):
    return datetime.datetime.fromtimestamp(unixtime).strftime("%Y-%m-%d %H:%M:%S")


def _target(entry):
    """対象の見せかた。ページは実体パスではなくページパスで出す。"""
    kind, target = entry["kind"], entry["target"]
    if kind.startswith(("page.", "attach.")):
        return "/" + pagepath_of_subpath(target)
    return target


def _state(entry):
    if entry.get("undone_at") is not None:
        return f"戻した（{escape(entry['undone_by'])}、{_time(entry['undone_at'])}）"
    if staffundo.undoable(entry):
        return "戻せる"
    return "記録だけ"


def _list_html(wiki_dir, here):
    actor = (request.query.getunicode("actor", "") or "").strip() or None
    try:
        page = max(1, int(request.query.get("page") or 1))
    except ValueError:
        page = 1
    total = stafflog.count(wiki_dir, actor)
    rows = stafflog.entries(wiki_dir, PER_PAGE, (page - 1) * PER_PAGE, actor)
    lead = ("助手が行った操作の記録です（管理者の操作は記録しません）。"
            "行を開くと操作の前後を見比べられ、戻せるものは「元に戻す」で戻せます。"
            "戻すのは、いまの状態が操作の直後のままのときだけです。")
    if actor:
        lead += f' いまは «{escape(actor)}» だけを出しています（<a href="{escape(here)}">すべて</a>）。'
    if not rows:
        return f'<p class="acct-lead">{lead}</p><p>記録はまだありません。</p>'
    trs = []
    for e in rows:
        link = f"{escape(here)}?id={e['id']}"
        who = f'<a href="{escape(here)}?actor={quote(e["actor_uid"])}">{escape(e["actor_uid"])}</a>'
        trs.append(
            f"<tr><td>{_time(e['unixtime'])}</td><td>{who}</td>"
            f"<td>{escape(stafflog.KINDS.get(e['kind'], e['kind']))}</td>"
            f"<td><code>{escape(_target(e))}</code></td>"
            f"<td>{escape(e['summary'])}</td><td>{_state(e)}</td>"
            f'<td><a href="{link}">開く</a></td></tr>')
    pager = []
    if page > 1:
        pager.append(f'<a href="{escape(here)}?page={page - 1}'
                     f'{"&actor=" + quote(actor) if actor else ""}">新しいほうへ</a>')
    if page * PER_PAGE < total:
        pager.append(f'<a href="{escape(here)}?page={page + 1}'
                     f'{"&actor=" + quote(actor) if actor else ""}">古いほうへ</a>')
    return (f'<p class="acct-lead">{lead}</p>'
            f'<p class="acct-hint">全{total}件</p>'
            '<table class="acct-table stafflog-table"><thead><tr>'
            "<th>日時</th><th>助手</th><th>操作</th><th>対象</th><th>内容</th>"
            "<th>状態</th><th></th></tr></thead><tbody>"
            + "".join(trs) + "</tbody></table>"
            + (f'<p class="acct-hint">{" ・ ".join(pager)}</p>' if pager else ""))


def _text_of(value):
    """前後の見比べに出す文字列。本文・設定はそのまま、ほかはJSONで。"""
    if value is None:
        return None
    if isinstance(value, dict) and set(value) <= {"ext", "text"}:
        return value.get("text")
    if isinstance(value, dict) and "user" in value:
        value = dict(value, user={k: v for k, v in value["user"].items() if k != "pw"})
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _diff_html(before, after):
    a, b = _text_of(before), _text_of(after)
    if a is None and b is None:
        return "<p>（前後の内容はありません）</p>"
    lines = list(difflib.unified_diff(
        (a or "").splitlines(), (b or "").splitlines(),
        "操作の前" + ("（無し）" if a is None else ""),
        "操作の後" + ("（無し）" if b is None else ""), lineterm=""))
    if not lines:
        return "<p>（前後で違いはありません）</p>"
    return '<pre class="stafflog-diff">' + escape("\n".join(lines)) + "</pre>"


def _detail_html(entry, here, wiki_dir):
    rows = [
        ("日時", _time(entry["unixtime"])),
        ("助手", escape(entry["actor_uid"])),
        ("操作", escape(stafflog.KINDS.get(entry["kind"], entry["kind"]))),
        ("対象", f"<code>{escape(_target(entry))}</code>"),
        ("内容", escape(entry["summary"])),
        ("状態", _state(entry)),
    ]
    if entry.get("undo_note"):
        rows.append(("戻したときの結果", escape(entry["undo_note"])))
    table = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    action = ""
    if staffundo.undoable(entry):
        action = (f'<form method="post" action="{escape(here)}" style="margin: 1em 0">'
                  f'<input type="hidden" name="id" value="{entry["id"]}">'
                  '<button type="submit" class="acct-go">元に戻す</button> '
                  '<span class="acct-hint">いまの状態が操作の直後のままのときだけ戻します。</span>'
                  "</form>")
    elif entry.get("undone_at") is None and entry["kind"] in staffundo.NOT_UNDOABLE:
        action = f'<p class="acct-hint">{escape(staffundo.NOT_UNDOABLE[entry["kind"]])}</p>'
    return (f'<p><a href="{escape(here)}">一覧へ戻る</a></p>'
            f'<table class="acct-table">{table}</table>{action}'
            "<h2>操作の前と後</h2>" + _diff_html(entry["before"], entry["after"]))
