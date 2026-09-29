"""承認待ちのアカウントを承認する・断る画面（`/.admin/approvals`）。

    /.admin/approvals    画面（GET）と、承認・断る操作（POST）。**管理者と助手**

`account.policy` が `approval` のWikiでは、ログイン画面の「アカウント作成」で
申請されたアカウントは**承認待ちで始まり、入れない**（`wikilib.auth.do_signup`。
`wikilib.userdb` の冒頭）。**助手か管理者が、ここで承認する**（Wiki設計者の指示、
2026-09-21。「ユーザ登録に staff による承認を必要とする」）。

    承認する  そのアカウントを使えるようにする（`userdb.set_approved`）。以後は
              ログインでき、`g:all` にも入る
    断る      そのアカウントを消す（`userdb.delete_user`）。申請し直せる

**承認待ちのアカウントだけを扱う。** 承認済みのアカウントをここから消せてしまうと、
助手が管理者専用の一覧（`/.admin/accounts`）の削除を通り越せる。承認の取り消しは
いまのところ画面にない（管理者が一覧で消すか、ロックする）。

## 送信のあとは転送する

POSTの結果はその場で返さず、この画面へ303で転送してから知らせを出す
（`#login` と同じ理由。再読み込みで「もう一度送りますか」が出て、同じ操作が
もう一度走るのを避ける）。**知らせに使うのはIDだけ**で、書き込みの内容は持ち回らない。
"""
from html import escape

from bottle import HTTPResponse, request

from wikilib import auth, groups, stafflog, sysui, userdb
from wikilib.paths import ACCOUNTS_URLPATH, APPROVALS_URLPATH
from wikilib.themes import make_plugin_context
from wikilib.wikiconfig import account_policy, load_wiki_config

DONE_KEY = "done"


def _act(wiki_dir, op, uidnum):
    """1件を承認する・断る。`(結果の名前, ID)` を返す。"""
    user = userdb.get_user(wiki_dir, uidnum)
    if user is None or userdb.is_approved(user):
        # 無い・すでに承認済み（別の人が先に承認した、など）。**何も書き換えない**
        return "gone", (user or {}).get("uid", "")
    staff = stafflog.actor(wiki_dir)
    if op == "approve":
        ok, _message = userdb.set_approved(wiki_dir, uidnum, True)
        if ok and staff is not None:
            stafflog.record(wiki_dir, staff, "account.approve", user["uid"], "承認した",
                            before={"user": user}, after={"uidnum": uidnum, "approved": 1})
        return ("approved" if ok else "ng"), user["uid"]
    # 断るとアカウントを消すので、戻せるよう行と所属グループを控える
    memberships = groups.groups_of(wiki_dir, uidnum) if staff is not None else []
    ok, _message = userdb.delete_user(wiki_dir, uidnum)
    if ok and staff is not None:
        stafflog.record(wiki_dir, staff, "account.reject", user["uid"],
                        "申請を断った（アカウントを消した）",
                        before={"user": user, "groups": memberships}, after=None)
    return ("rejected" if ok else "ng"), user["uid"]


def render_approvals(wiki_dir, config, farm, explicit_farm):
    """画面。**管理者と助手だけ**が開ける。確かめるのは**中身を組み立てる前・
    POSTを処理する前**（`sysui.require`）。"""
    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           APPROVALS_URLPATH, auth.STAFF)
    if denied is not None:
        return denied
    base_url = make_plugin_context(config, farm, wiki_dir, APPROVALS_URLPATH,
                                   explicit_farm).base_url
    here = f"{base_url}/{APPROVALS_URLPATH}"

    if request.method == "POST":
        op = request.forms.get("op") or ""
        try:
            uidnum = int(request.forms.get("uidnum") or "")
        except ValueError:
            uidnum = 0
        if op in ("approve", "reject") and uidnum:
            done, uid = _act(wiki_dir, op, uidnum)
        else:
            done, uid = "ng", ""
        from urllib.parse import quote
        return HTTPResponse(status=303, headers={
            "Location": f"{here}?{DONE_KEY}={done}&uid={quote(uid)}"})

    done = request.query.get(DONE_KEY) or ""
    uid = request.query.getunicode("uid", "")
    message, ok = _notice_for(done, uid)
    pending = userdb.pending_users(wiki_dir)
    body = _html(pending, here, message, ok,
                 account_policy(load_wiki_config(wiki_dir)))
    return sysui.page(wiki_dir, config, farm, explicit_farm, APPROVALS_URLPATH,
                      "アカウントの承認", body, css_url=f"{ACCOUNTS_URLPATH}.css")


def _notice_for(done, uid):
    """転送されてきた結果の知らせ。`(文言, うまくいったか)`。"""
    who = f"«{uid}» " if uid else ""
    return {
        "approved": (f"{who}を承認しました。ログインできるようになりました。", True),
        "rejected": (f"{who}の申請を断りました（アカウントを消しました）。", True),
        "gone": (f"{who}はすでに承認済みか、もうありません。", False),
        "ng": ("操作できませんでした。", False),
    }.get(done, ("", True))


def _row_html(user, here):
    uid = escape(user["uid"])
    return f"""      <tr>
        <td class="acct-num">{user["uidnum"]}</td>
        <td>{uid}</td>
        <td>{escape(user["name"] or "")}</td>
        <td>
          <form class="acct-inline" method="post" action="{escape(here)}">
            <input type="hidden" name="uidnum" value="{user["uidnum"]}">
            <button type="submit" name="op" value="approve" class="acct-go">承認する</button>
            <button type="submit" name="op" value="reject" class="acct-go acct-del"
                    onclick="return confirm('{uid} の申請を断って、アカウントを消します。よろしいですか？');">断る</button>
          </form>
        </td>
      </tr>"""


def _html(pending, here, message, ok, policy):
    rows = "\n".join(_row_html(u, here) for u in pending) or (
        '<tr><td colspan="4">承認待ちのアカウントはありません。</td></tr>')
    note = ""
    if policy != "approval":
        note = ('<p class="acct-hint">このWikiは承認制ではありません'
                '（設定 <code>account.policy</code> が <code>open</code>）。'
                '承認待ちがあるのは、承認制だったころの申請が残っている場合だけです。</p>')
    return f"""{sysui.notice(message, bad=not ok)}
<div class="acct">
  <p class="acct-lead">「アカウント作成」で申請されたアカウントです。
    <strong>承認するまで、ログインできません</strong>（権限の上では未ログインと同じ扱いです）。</p>
{note}
  <table class="acct-table">
    <thead><tr><th>番号</th><th>ID</th><th>名前</th><th></th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <p class="acct-hint">承認済みのアカウントの一覧と削除は
    <a href="{escape(here.rsplit("/", 1)[0])}/accounts">アカウント</a>（管理者だけ）にあります。</p>
</div>
"""
