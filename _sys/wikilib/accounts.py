"""アカウントまわりの画面（一覧と編集・自分のパスワード・ハッシュ値づくり）。

    /.admin/accounts   登録されているアカウントを見る・直す  **管理者だけ**
    /.admin/accounts/api  一覧の更新・削除を1件ずつ受けるJSON API（同）
    /.passwd           自分のパスワードを変える              誰でも
    /.pwhash           パスワードからハッシュ値を作る道具    誰でも

**ここは画面を組み立てるだけ。** 記録の読み書きは`wikilib.userdb`、ログイン状態と
権限の判断は`wikilib.auth`、画面の共通部品（組み立て・知らせ・JSON・関門）は
`wikilib.sysui` が受け持つ。以前はcookieの扱い・合言葉・ログインの受け口・
権限判定もここにあったが、画面とは別の主題なので`wikilib.auth`へ移した
（Wiki設計者の指示、2026-09-13のリファクタリング方針）。

## 誰が開けるか

`/.admin/accounts` はアカウントの追加・書き換え・削除ができ、パスワードの
ハッシュ値もそのまま出す画面なので、**そこに届く相手は誰にでもなりすませる**
（他人のパスワードを書き換えてログインし直せばよい）。取り次ぐ前に
`sysui.require(..., auth.ADMIN_ONLY)` で確かめ、管理者でなければ403を返して
中身を組み立てない。

`/.passwd` を誰でも開けるままにしてあるのは、**いまのパスワードを知らないと
変えられない**（`userdb.authenticate` を通す）ためで、ログインしていない相手が
開けても他人のパスワードは変えられない。他人のぶんを書き換えるのは
`/.admin/accounts` の側、という分けかたにしてある。

## 照合はここでもauthに任せる

`/.passwd` の「いまのパスワード」の確認は`auth.try_password`を通す
（`#login`プラグイン経由のログインと**同じ数えに載せる**ため。片方だけ
数えていると、そちらから何回でも試せてしまう。Wiki設計者の了承、2026-09-06）。
ロック・無視の仕組みと記録は`wikilib.auth`と`wikilib.authlog`にある。

## 一覧の更新・削除は1ユーザーずつのAPI（Wiki設計者の指示、2026-09-12）

画面のJS（`_sys/accounts/accounts.js`）が、値を変えた行・チェックした行を
1件ずつ`/.admin/accounts/api`へ送る。まとめて1回で送らないのは、途中で1件
失敗したときに「どこまで進んだか」を追えるようにするため。誰がどのアカウントに
何をしたかは`wikilib.adminlog`に残す。

## パスワードの持ちかた

- ハッシュは利用者ごとの塩を持たずSHA-1なので、値を見られると総当たりが安い
  （詳しくは`wikilib.userdb`の冒頭）。**一覧に届く＝表全体の総当たりの入口が
  渡る**、と考えたほうがよい
- 通信をHTTPSにするかどうかはこの実装の外
"""
import re
import time
from html import escape

from bottle import request

from wikilib import adminlog, auth, sysui, userdb
from wikilib.paths import (
    ACCOUNTS_DIR, ACCOUNTS_URLPATH, PASSWD_URLPATH,
    PWHASH_URLPATH,
)
from wikilib.themes import make_plugin_context
from wikilib.web import serve_asset

# ハッシュ値の形（SHA-1の16進表記。`userdb.hash_password` の戻り値）
HASH_RE = re.compile(r"^[0-9a-f]{40}$")

# アカウントまわりの画面が共有するCSS（`/.admin/accounts.css`）。
# `/.admin` の窓口（wikilib.adminui）も同じものを読む。
ACCOUNTS_CSS = f"{ACCOUNTS_URLPATH}.css"


# ---- /.admin/accounts ------------------------------------------------------------

def render_accounts(wiki_dir, config, farm, explicit_farm):
    """アカウントの一覧と編集。**管理者だけが開ける**（Wiki設計者の指示、2026-09-06）。

    確かめるのは**中身を組み立てる前、POSTを処理する前**。あとから隠すのでは
    なく、そこまで行かせない。断ったときは 403 を返す。"""
    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           ACCOUNTS_URLPATH, auth.ADMIN_ONLY)
    if denied is not None:
        return denied
    message, ok = "", True
    if request.method == "POST":
        ok, message = _apply_accounts_post(wiki_dir)
    users = userdb.all_users(wiki_dir)
    base_url = make_plugin_context(config, farm, wiki_dir, ACCOUNTS_URLPATH,
                                   explicit_farm).base_url
    body = _accounts_html(users, base_url, message, ok, userdb.exists(wiki_dir))
    if userdb.exists(wiki_dir):
        # 更新・削除はJS（accounts.js）が行う。**表示できても動かせない**
        # 中途半端さを避けるため、記録そのものが無いときは読み込ませない
        body += f'<script src="{escape(base_url)}/{ACCOUNTS_URLPATH}.js"></script>'
    out = sysui.page(wiki_dir, config, farm, explicit_farm, ACCOUNTS_URLPATH,
                     "アカウント", body, css_url=ACCOUNTS_CSS)
    # 昨日のぶんの合言葉で通った場合に備えて、今日のぶんへ置き換える
    auth.remember_login(out, config, farm, wiki_dir, explicit_farm,
                        auth.current_user(wiki_dir, farm))
    return out


def _apply_accounts_post(wiki_dir):
    """**一覧の画面から届く、いまも残っているフォーム送信**を1つ処理する。
    (成否, 文言) を返す。

    残っているのは「新しく追加する」フォームだけ（`cmd=add`）。更新・削除は
    2026-09-12に行ごとのフォーム送信から`/.admin/accounts/api`（JS経由の
    1件ずつのAPI呼び出し）へ移したので、ここに来るのはいまは `add` だけの
    はずだが、**未知の`cmd`が来たときの受け皿として残す**（URLを直接叩く等の
    想定外の送信への保険）。"""
    action = request.forms.get("cmd") or ""
    uid = (request.forms.getunicode("uid", "") or "").strip()
    name = (request.forms.getunicode("name", "") or "").strip()
    pw = (request.forms.getunicode("pw", "") or "").strip()
    raw = request.forms.getunicode("raw", "") or ""
    # 生のパスワードを入れてもらったときは、ここでハッシュに直してから渡す
    # （表に入るのはハッシュ値だけ。userdb.add_user / update_user は
    #  ハッシュ済みしか受け取らない）
    if raw:
        pw = userdb.hash_password(wiki_dir, uid, raw)

    if action == "add":
        return userdb.add_user(wiki_dir, uid, pw, name)
    return False, "知らない操作です。"


def render_accounts_api(wiki_dir, config, farm, explicit_farm):
    """一覧（`/.admin/accounts`）の更新・削除を、**1ユーザーずつ**受ける窓口
    （`/.admin/accounts/api`。Wiki設計者の指示、2026-09-12）。

    画面（`accounts.js`）は、チェックした・値を変えたユーザーぶんだけ、
    この窓口へ**順番に**1件ずつPOSTする。まとめて1回で送らないのは、
    途中で1件失敗したときに「どこまで進んだか」をサーバー側の1件ずつの
    応答だけで画面側が追えるようにするため。

    受け取るのはJSON。

        {"cmd": "update", "uidnum": 2, "uid": "…", "name": "…", "pw": "…", "raw": "…", "lock": true}
        {"cmd": "delete", "uidnum": 2}

    `raw`（生のパスワード）が届いたら**サーバーがハッシュにして**保存する。`lock` が
    真なら `pw` を `LOCKED` にする。どちらも無ければ `pw`（ハッシュ済み）をそのまま使い、
    空なら変えない。

    返すのもJSON。`{"ok": true/false, "message": "…"}`（更新の成功時は、保存後の
    `pw` も付く）。

    **認証は本体（`/.admin/accounts`）と同じcookieで見る。** JSON専用の
    窓口なので、断るときもHTMLの403ページではなくJSONで返す——JavaScript
    から見て、HTMLを渡されても使い道が無いため。

    **誰が・どのアカウントに・何をしたかを記録する**（`wikilib.adminlog`。
    「サーバー側ではどのユーザが何を処理したかログを残す」というWiki設計者の
    指示）。成功・失敗のどちらも残す。"""
    actor = auth.current_user(wiki_dir, farm)
    if not userdb.is_admin(actor):
        # 「ログインしていない」も「管理者ではない」も同じ扱い（require_admin
        # と同じ理由。IDが実在するかを外から確かめる手がかりを与えない）
        return sysui.json_out({"ok": False, "message": "権限がありません。"}, status=403)

    try:
        body = request.json or {}
    except ValueError:
        body = {}
    cmd = body.get("cmd") or ""
    try:
        uidnum = int(body.get("uidnum"))
    except (TypeError, ValueError):
        return sysui.json_out(
            {"ok": False, "message": "対象のアカウントが分かりませんでした。"}, status=400)

    # ログに残す「対象のuid」は、消えた後も読めるよう操作前の値を控えておく
    target = userdb.get_user(wiki_dir, uidnum)
    target_uid = target["uid"] if target is not None else ""

    if cmd == "update":
        uid = (body.get("uid") or "").strip()
        name = (body.get("name") or "").strip()
        pw = (body.get("pw") or "").strip()
        # 一覧で「パスワードとして入力」にチェックが入っていたときは、生のパスワード
        # （`raw`）が届く。**ここでハッシュにしてから**渡す（`update_user` はハッシュ済みしか
        # 受け取らない）。ハッシュにはIDが混ざるので、変更後のIDで計算する
        raw = body.get("raw") or ""
        if body.get("lock"):
            # 欄を空にして送られたとき＝ロック（`pw` を `LOCKED` にする）。
            # `update_user` を通すので、IDの変更を伴っても断られない
            pw = userdb.LOCKED_PW
        elif raw:
            pw = userdb.hash_password(wiki_dir, uid, raw)
        elif pw and (target is None or pw != target["pw"]) and not HASH_RE.match(pw):
            # チェックを入れ忘れて生のパスワードを入れると、使えない値が
            # 保存されてしまうので、ハッシュ値の形でないものは断る
            ok, message = False, ("ハッシュ値は40桁の16進数で入れてください"
                                  "（パスワードを入れるときは、欄の右のチェックを入れます）。")
            pw = None
        if pw is not None:
            ok, message = userdb.update_user(wiki_dir, uidnum, uid, pw, name)
    elif cmd == "delete":
        ok, message = userdb.delete_user(wiki_dir, uidnum)
    else:
        return sysui.json_out({"ok": False, "message": "知らない操作です。"}, status=400)

    adminlog.record(wiki_dir, actor["uid"], cmd, uidnum, target_uid, ok, message)
    result = {"ok": ok, "message": message}
    if ok and cmd == "update":
        # 画面が欄の表示を更新後のハッシュ値に合わせられるよう返す
        # （この画面はもともとハッシュ値を一覧に出している）
        fresh = userdb.get_user(wiki_dir, uidnum)
        if fresh is not None:
            result["pw"] = fresh["pw"]
    out = sysui.json_out(result)
    # 昨日のぶんの合言葉で通った場合に備えて、今日のぶんへ置き換える
    # （画面を開いたまま日をまたいで操作したときの保険。render_accountsと同じ）
    auth.remember_login(out, config, farm, wiki_dir, explicit_farm, actor)
    return out


def _accounts_html(users, base_url, message, ok, ready=True):
    if not ready:
        # 記録そのものが無いWiki。**画面を開いたことでは作らない**ので、
        # 用意するやりかたを案内するだけにする（userdb の冒頭を参照）
        return f"""{sysui.notice(message, bad=not ok)}
<div class="acct">
  <p class="acct-lead">このWikiにはアカウントの記録がまだありません。</p>
  <p>用意するには、サーバーで次を実行してください。</p>
  <pre><code>./wiki.py initusers</code></pre>
  <p class="acct-hint">画面を開いただけでは作りません。誰でも開ける画面への
    アクセスで、既定のパスワードを持つ管理者アカウントが生えてしまうためです。</p>
</div>
"""
    rows = "\n".join(_account_row_html(u) for u in users) or (
        '<tr><td colspan="5">まだ1件もありません。</td></tr>')
    api_url = f"{escape(base_url)}/{ACCOUNTS_URLPATH}/api"
    return f"""{sysui.notice(message, bad=not ok)}
<div class="acct acct-list" data-api="{api_url}">
  <p class="acct-lead">このWikiに登録されているアカウントです
    （<code>config/users.db</code> の <code>passwd</code>）。</p>

  <div class="acct-bulk-actions">
    <button type="button" id="acct-update-btn" class="acct-go">変更を更新</button>
    <button type="button" id="acct-delete-btn" class="acct-go acct-del" disabled>
      選んだ行を削除</button>
    <span id="acct-bulk-status" class="acct-bulk-status" role="status" aria-live="polite"></span>
  </div>

  <p class="acct-hint">パスワードの欄には、保存されているハッシュ値が出ています。
    <strong>欄の右の「パスワードとして入力」にチェックを入れると</strong>、書いた文字を
    生のパスワードとしてハッシュにして登録します。<strong>チェックが無いときは、
    欄をハッシュ値として</strong>そのまま受け付けます（40桁の16進のみ）。
    <strong>欄を空にして更新すると、ロックします</strong>（解除は新しいパスワードを入れます）。</p>

  <table class="acct-table" id="acct-table">
    <thead>
      <tr><th>番号</th><th></th><th>ID</th><th>名前</th><th>パスワード</th></tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>

  <h2 class="acct-h2">新しく追加する</h2>
  <form class="acct-form acct-add" method="post">
    <input type="hidden" name="cmd" value="add">
    <div class="acct-row">
      <label for="acct-add-uid">ID</label>
      <input id="acct-add-uid" type="text" name="uid" autocomplete="off" required
             pattern="[0-9A-Za-z]+" title="半角の英数字だけが使えます">
    </div>
    <div class="acct-row">
      <label for="acct-add-name">名前</label>
      <input id="acct-add-name" type="text" name="name" autocomplete="off">
    </div>
    <div class="acct-row">
      <label for="acct-add-raw">パスワード</label>
      <input id="acct-add-raw" type="password" name="raw" autocomplete="new-password">
    </div>
    <div class="acct-row">
      <label for="acct-add-pw">ハッシュ値</label>
      <input id="acct-add-pw" type="text" name="pw" autocomplete="off"
             placeholder="上のパスワード欄を使わず、値を直接入れる場合">
    </div>
    <p class="acct-hint">どちらか一方でかまいません。<strong>両方入れた場合は
      パスワード欄が優先</strong>されます。ハッシュ値だけを作りたいときは
      <a href="{escape(base_url)}/{PWHASH_URLPATH}">ハッシュ値を作る</a> を使ってください。</p>
    <div class="acct-actions">
      <button type="submit" class="acct-go">追加</button>
    </div>
  </form>
</div>
"""


def _account_row_html(user):
    """1行ぶん。

    更新・削除は行ごとのボタンを持たず、一覧の上に集約したボタン
    （`accounts.js`）が担う（Wiki設計者の指示、2026-09-12）。この行が持つのは
    **チェックボックス**（削除の対象を選ぶ）と、**入力欄の元の値**
    （`data-orig`。JSが「値を変えたか」を見分けるために比較する側）だけ。

    **ロック中の行には印を付ける**（`pw` が `LOCKED`）。解除は
    「パスワードを付け直す」——この画面でハッシュ値か生のパスワードを
    入れて更新すれば戻る。ここは管理者しか開けないので、**解除できるのは
    管理者だけ**になる（Wiki設計者の指示、2026-09-06）。

    **管理者（`uidnum=1`）の行はチェックボックスを無効にする。**
    `userdb.delete_user` がもともと管理者を消さないので、押させておいて
    サーバーに断られるより、先に選べないようにするほうが分かりやすい。"""
    uidnum = user["uidnum"]
    locked = userdb.is_locked(user)
    is_admin_row = uidnum == userdb.ADMIN_UIDNUM
    checkbox_attrs = (' disabled data-admin="1" title="管理者は削除できません"'
                      if is_admin_row else ' data-admin="0"')
    return f"""      <tr data-uidnum="{uidnum}"{' class="acct-locked"' if locked else ''}>
        <td class="acct-num">{uidnum}{'<span class="acct-lock-mark"'
        ' title="ロック中。パスワードを付け直すと戻ります">🔒</span>' if locked else ''}{'<span'
        ' class="acct-pending-mark" title="承認待ち。承認は /.admin/approvals で行います">⏳</span>'
        if not userdb.is_approved(user) else ''}</td>
        <td class="acct-check-cell"><input type="checkbox" class="acct-check"
                   data-uidnum="{uidnum}"{checkbox_attrs}
                   aria-label="{escape(user["uid"])}を削除の対象に選ぶ"></td>
        <td><input type="text" class="acct-f-uid" data-orig="{escape(user["uid"])}"
                   value="{escape(user["uid"])}" autocomplete="off" required
                   pattern="[0-9A-Za-z]+" title="半角の英数字だけが使えます"></td>
        <td><input type="text" class="acct-f-name" data-orig="{escape(user["name"])}"
                   value="{escape(user["name"])}" autocomplete="off"></td>
        <td class="acct-pw-cell"><div class="acct-pw-wrap">
            <input type="text" class="acct-f-pw acct-hash"
                   data-orig="{escape(user["pw"])}" value="{escape(user["pw"])}"
                   autocomplete="off">
            <label class="acct-raw-label" title="入れると、欄の文字を生のパスワードとして
ハッシュにして登録します。外したままなら、欄はハッシュ値として扱います">
              <input type="checkbox" class="acct-f-raw"> パスワードとして入力</label>
          </div></td>
      </tr>"""


# ---- /.passwd --------------------------------------------------------------

def render_passwd(wiki_dir, config, farm, explicit_farm):
    """自分のパスワードを変える画面。

    **いまのパスワードを知らないと変えられない。** ここだけは誰でも開ける
    ままでよい、という切り分けにしてある（`/.admin/accounts` と違い、開けることが
    そのまま書き換えられることにならないため）。

    いまのパスワードが違っていたときは、ログインと同じく**1秒おいてから**
    断る。ここも照合の入口なので、総当たりの速度を落としておく。"""
    typed = request.forms.getunicode("uid", "") or ""
    uid = typed.strip()
    message, ok, done = "", True, False

    if request.method == "POST":
        current = request.forms.getunicode("current", "") or ""
        first = request.forms.getunicode("new1", "") or ""
        second = request.forms.getunicode("new2", "") or ""
        if not userdb.exists(wiki_dir):
            ok, message = False, userdb.NO_DB_MESSAGE
        elif not first:
            ok, message = False, "新しいパスワードを入力してください。"
        elif first != second:
            ok, message = False, "新しいパスワードの2つの欄が一致しません。"
        else:
            # ここも照合の入口。**片方だけ数えると、こちらから何回でも
            # 試せてしまう**（Wiki設計者の了承、2026-09-06）。無視もロックも同じ
            user, locked, _left = auth.try_password(wiki_dir, uid, typed, current)
            if user is None:
                time.sleep(auth.RETRY_DELAY)
                ok = False
                message = ("このアカウントはロックされています。"
                           "管理者に解除を頼んでください。") if locked else \
                          "IDかいまのパスワードが違います。"
            else:
                ok, message = userdb.update_user(
                    wiki_dir, user["uidnum"], user["uid"],
                    userdb.hash_password(wiki_dir, user["uid"], first), user["name"])
                done = ok
                if ok:
                    message = f"«{user['uid']}» のパスワードを変えました。"

    if done:
        # ページの中のフォームから来ていたら、そのページへ戻す
        back = auth.back_page_url(config, farm, wiki_dir, explicit_farm)
        if back is not None:
            return auth._back_to(back, auth.LOGIN_RESULT_DONE)
    return sysui.page(wiki_dir, config, farm, explicit_farm, PASSWD_URLPATH,
                      "パスワードを変える", _passwd_html(uid, message, ok, done),
                      css_url=ACCOUNTS_CSS)


def _passwd_html(uid, message, ok, done):
    if done:
        # 変えたあとに入力欄を残すと、古いパスワードを入れたまま押し直して
        # しまう。終わったことだけを見せる
        return f"""{sysui.notice(message, bad=False)}
<div class="acct acct-done">
  <p class="acct-done-lead">次のログインから新しいパスワードを使ってください。</p>
</div>
"""
    return f"""{sysui.notice(message, bad=not ok)}
<div class="acct">
  <p class="acct-lead">自分のパスワードを変えます。
    <strong>いまのパスワードが要ります。</strong></p>
  <form class="acct-form acct-passwd" method="post">
    <div class="acct-row">
      <label for="acct-pu">ID</label>
      <input id="acct-pu" type="text" name="uid" value="{escape(uid)}"
             autocomplete="username" autofocus required
             pattern="[0-9A-Za-z]+" title="半角の英数字だけが使えます">
    </div>
    <div class="acct-row">
      <label for="acct-cur">いまのパスワード</label>
      <input id="acct-cur" type="password" name="current"
             autocomplete="current-password" required>
    </div>
    <div class="acct-row">
      <label for="acct-new1">新しいパスワード</label>
      <input id="acct-new1" type="password" name="new1"
             autocomplete="new-password" required>
    </div>
    <div class="acct-row">
      <label for="acct-new2">もう一度</label>
      <input id="acct-new2" type="password" name="new2"
             autocomplete="new-password" required>
    </div>
    <div class="acct-actions">
      <button type="submit" class="acct-go">変える</button>
    </div>
  </form>
</div>
"""


# ---- /.pwhash --------------------------------------------------------------

def render_pwhash(wiki_dir, config, farm, explicit_farm):
    """パスワードからハッシュ値を作るだけの画面。

    2回入れてもらい、**一致したときだけ**下の欄に値を出す（Wiki設計者の指示）。
    打ち間違えたまま登録してしまうのを防ぐため。作った値はどこにも記録しない
    （ここは道具であって、アカウントを触る画面ではない）。"""
    value, message, ok = "", "", True
    uid = (request.forms.getunicode("uid", "") or "").strip()
    if request.method == "POST":
        first = request.forms.getunicode("pw1", "") or ""
        second = request.forms.getunicode("pw2", "") or ""
        problem = userdb.check_uid(uid)
        if problem:
            # ハッシュ値にIDが混ざるので、IDが無いと作れない
            ok, message = False, problem
        elif not first:
            ok, message = False, "パスワードを入力してください。"
        elif first != second:
            ok, message = False, "2つの欄が一致しません。もう一度入力してください。"
        else:
            value = userdb.hash_password(wiki_dir, uid, first)
            message = "ハッシュ値を作りました。"
    return sysui.page(wiki_dir, config, farm, explicit_farm, PWHASH_URLPATH,
                      "ハッシュ値を作る", _pwhash_html(value, message, ok, uid),
                      css_url=ACCOUNTS_CSS)


def _pwhash_html(value, message, ok, uid=""):
    return f"""{sysui.notice(message, bad=not ok)}
<div class="acct">
  <p class="acct-lead">IDとパスワードからハッシュ値を作ります。
    入れた値も、作った値も、<strong>どこにも記録しません</strong>。</p>
  <p class="acct-hint">ハッシュ値は<strong>このWiki・このIDのもの</strong>です
    （Wikiの塩とIDが混ざるため）。別のWikiや別のIDには使えません。</p>
  <form class="acct-form acct-pwhash" method="post">
    <div class="acct-row">
      <label for="acct-uid">ID</label>
      <input id="acct-uid" type="text" name="uid" value="{escape(uid)}"
             autocomplete="off" required pattern="[0-9A-Za-z]+"
             title="半角の英数字だけが使えます">
    </div>
    <div class="acct-row">
      <label for="acct-pw1">パスワード</label>
      <input id="acct-pw1" type="password" name="pw1"
             autocomplete="new-password" autofocus required>
    </div>
    <div class="acct-row">
      <label for="acct-pw2">もう一度</label>
      <input id="acct-pw2" type="password" name="pw2"
             autocomplete="new-password" required>
    </div>
    <div class="acct-actions">
      <button type="submit" class="acct-go">作る</button>
    </div>
    <div class="acct-row">
      <label for="acct-hash">ハッシュ値</label>
      <input id="acct-hash" type="text" class="acct-hash" value="{escape(value)}"
             readonly aria-readonly="true" placeholder="ここに出ます">
    </div>
  </form>
</div>
"""


# ---- 資材 ------------------------------------------------------------------

def serve_accounts_asset(name):
    """アカウントまわりの画面が共有するCSS/JS（/.admin/accounts.css・.js）。

    JS（`accounts.js`）は一覧（`/.admin/accounts`）の更新・削除ボタンだけが
    使う（Wiki設計者の指示、2026-09-12）。他の画面（`/.passwd` 等）も同じCSSを
    共有するため`.js`を置いてはいるが、それらの画面には`<script>`を差して
    いないので実際には読み込まれない。"""
    return serve_asset(ACCOUNTS_DIR, "accounts", name)
