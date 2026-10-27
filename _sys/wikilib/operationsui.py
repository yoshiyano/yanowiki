"""中断した操作の画面（/.admin/operations）。**管理者と助手**が開ける。

助手は、管理者が与えた権限（`wikilib.staffperms`）で、見る（`operations.view`）・
続きを行う（`operations.resume`）。既定はどちらも与えてある。

名前の変更・移動は、作業の手順のファイルに沿って行い、［中止］か時間の上限で止まると
続きを残す（`wikilib.operations`）。ここではそれを一覧にし、続きを行う。続きはファイル一覧の
「中断した操作を続ける」からも行える（Wiki設計者が了承した決まり、2026-10-01）。

    GET   一覧（どこからどこへ・始めた人・時刻・状態・直したページの数・止めたときの知らせ）
    POST  id の操作の続きを行う（1回で続ける時間の上限は operations.TIME_LIMIT）

以下はクロコの実装例: ファイル一覧では「動くページすべてを編集できる人」だけが続けられるが、
ここは管理の道具なので、開ける人（管理者と助手）なら続けられる。止めたときの記録を消す
（続きをやめる）操作は置かない。途中の状態のまま残すことになるため。
"""
import datetime
from html import escape

from bottle import request

from wikilib import auth, operations, sysui
from wikilib.paths import ACCOUNTS_URLPATH, OPERATIONS_URLPATH
from wikilib.themes import make_plugin_context
from wikilib.wikiconfig import load_wiki_config

TITLE = "中断した操作"


def render_operations(wiki_dir, config, farm, explicit_farm):
    denied = sysui.require_perm(wiki_dir, config, farm, explicit_farm,
                                OPERATIONS_URLPATH, "operations.view")
    if denied is not None:
        return denied
    base = make_plugin_context(config, farm, wiki_dir, OPERATIONS_URLPATH,
                               explicit_farm).base_url
    here = f"{base}/{OPERATIONS_URLPATH}"

    notice = ""
    if request.method == "POST":
        from wikilib.pagerename import resume_operation
        if auth.can(wiki_dir, farm, "operations.resume"):
            progress = operations.Progress()
            ok, message, _ = resume_operation(wiki_dir, load_wiki_config(wiki_dir),
                                              request.forms.get("id") or "",
                                              progress=progress)
        else:
            ok, message = False, "続きを行う権限がありません。"
        cls = "acct-notice" if ok else "acct-notice acct-notice-error"
        notice = f'<div class="{cls}" role="status">{escape(message)}</div>'

    body = notice + _list_html(wiki_dir, here, auth.can(wiki_dir, farm, "operations.resume"))
    return sysui.page(wiki_dir, config, farm, explicit_farm, OPERATIONS_URLPATH, TITLE,
                      f'<div class="acct operations">{body}</div>',
                      css_url=f"{ACCOUNTS_URLPATH}.css")


def _time(unixtime):
    return datetime.datetime.fromtimestamp(unixtime).strftime("%Y-%m-%d %H:%M:%S")


def _state(op):
    if operations.is_active(op):
        return "行っています"
    if op.get("state") == "paused":
        return "中断"
    return "途中で止まりました（サーバーの停止など）"


def _list_html(wiki_dir, here, can_resume=True):
    ops = operations.unfinished(wiki_dir)
    lead = ('<p class="acct-lead">途中で止まった名前の変更・移動です。［続ける］で続きを行います。'
            "続けているあいだに時間の上限（{:.0f} 秒）を超えたら、そこでまた止まります。"
            "止まっているあいだ、範囲が重なる名前の変更・移動・削除はできません。</p>"
            .format(operations.TIME_LIMIT))
    if not ops:
        return lead + "<p>中断している操作はありません。</p>"
    rows = []
    for op in ops:
        steps = f"{len(op.get('done', []))} / 8"
        button = ("" if operations.is_active(op) or not can_resume else
                  f'<form method="post" action="{escape(here)}">'
                  f'<input type="hidden" name="id" value="{escape(op["id"])}">'
                  '<button type="submit">続ける</button></form>')
        rows.append(
            "      <tr>"
            f"<td>{escape(operations.describe(op))}</td>"
            f"<td>{escape(op.get('actor') or '（未ログイン）')}</td>"
            f"<td>{escape(_time(op.get('created', 0)))}<br>{escape(_time(op.get('updated', 0)))}</td>"
            f"<td>{escape(_state(op))}<br>手順 {steps}・リンクを直したページ {op.get('fixed_count', 0)} 枚</td>"
            f"<td>{escape(op.get('message') or '')}</td>"
            f"<td>{button}</td></tr>")
    return lead + f"""<table class="acct-table">
    <thead><tr><th>操作</th><th>始めた人</th><th>始めた時刻<br>最後に進んだ時刻</th>
      <th>状態</th><th>止めたときの知らせ</th><th></th></tr></thead>
    <tbody>
{chr(10).join(rows)}
    </tbody>
  </table>
"""
