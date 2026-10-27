"""管理の道具をまとめた窓口（/.admin）。

    /.admin                窓口。**管理者と助手**が開ける
    /.admin/staffperms     助手に与える権限（wikilib.staffpermsui）。**管理者だけ**
    /.admin/accounts       アカウント一覧・編集。既定は管理者だけ
    /.admin/configwiki     Wikiの設定。管理者と助手
    /.admin/operations     中断した名前の変更・移動とその続き。管理者と助手
    /.admin/themes/        テーマのファイル（wikilib.themefilesui）。管理者と助手
    /.admin/update         公開版からの更新（wikilib.sysupdate）。既定Wikiの管理者と、再起動を許された助手

**助手が各画面を開けるかは、管理者が `/.admin/staffperms` で与えた権限で決まる**
（`wikilib.staffperms`。与えていなければ既定＝この仕組みを入れる前の状態）。窓口の
一覧（`TOOLS`）も、同じ権限で「開ける」「権限がありません」を出し分ける。

**これから作る管理の道具は、この下にサブコマンドとしてつなぐ**（Wiki設計者の指示、
2026-09-08）。`/.accounts` と `/.configwiki` は当初 `/.admin` の外に
置いていたが、この窓口の下へ移した（Wiki設計者の指示、2026-09-12）。

## 助手グループの管理は `/.groups` に統合した（Wiki設計者の指示、2026-09-12）

以前あった `/.admin/staff`（助手グループの出し入れ。管理者だけ）は廃止し、
`/.groups?tab=edit&group=staff` に一本化した。「助手の管理も作成した
グループと同様に扱う」というWiki設計者の指示の裏返しで、助手グループ（`staff`）は
`wikilib.groups` の仕組みそのものになった——専用の画面・専用のデータ表
（`usergroup`）を持たない。

    そのグループの編集権（g:foo, admin, g:staff）を持つ人 … /.groups?group=<名前>
    staffグループの編集権（結局 admin, g:staff の合併） … /.groups?group=staff

窓口（`TOOLS`）からは「助手グループ」としてそのURLへ直接リンクしている。
判断・データは `wikilib.groups` が持ち、ここでは並べるだけ。
"""
from html import escape

from wikilib import auth, staffperms, sysui, userdb
from wikilib.paths import (
    ACCOUNTS_URLPATH, ADMIN_URLPATH, ALLWIKI_COMMAND, APPROVALS_URLPATH,
    CONFIGWIKI_URLPATH, DELWIKI_URLPATH, GARBAGECOLLECT_URLPATH, GROUPS_URLPATH,
    NEWWIKI_URLPATH, OPERATIONS_URLPATH, PRIVILEGES_URLPATH, RESTART_URLPATH,
    STAFFLOG_URLPATH, STAFFPERMS_URLPATH, SYSTEM_PREFIX, THEMEFILES_URLPATH,
    UPDATE_URLPATH, UPDATEPAGEAUTH_URLPATH,
)
from wikilib.groups import STAFF_GROUP
from wikilib.themes import make_plugin_context
from wikilib.web import plain

# 窓口に並べる道具。**開くのに要る権限もここに書く**（画面の出し分けと、実際の
# 入口での判定が食い違わないよう、並びは1か所にまとめておく）。
#
#   (URLパス, 名前, 説明, 要る権限)
#
# 要る権限は `wikilib.staffperms` の権限の名前を並べたもの（**どれか1つ**を持てば開ける。
# 管理者は常に開ける）。管理者しか開けない道具（`/.admin/staffperms`）は
# `staffperms.ADMIN_ONLY`。入口での実際の判定は、各画面が同じ名前で行う。
# 助手の権限に関わらず誰でも開ける画面（`/.groups`・`/.updatePageAuth`）は `EVERYONE`。
# `ALLWIKI_URLPATH` の行は、実際のURL名が設定（`farm.allwiki`）で決まり、空なら出さない。
ALLWIKI_URLPATH = SYSTEM_PREFIX + ALLWIKI_COMMAND
# 「誰でも開ける」の印（助手の権限の設定に関わらない画面）
EVERYONE = "everyone"

TOOLS = [
    (NEWWIKI_URLPATH, "新しいWikiを作る",
     "自分用のWikiを作る。作れるのは起点Wikiの管理者と、許された助手。", ("site.newwiki",)),
    (DELWIKI_URLPATH, "Wikiを消す",
     "いまあるWikiを1つ消す（消す前に書庫へ固める）。消せるのは起点Wikiの管理者と、許された助手。",
     ("site.delwiki",)),
    (ALLWIKI_URLPATH, "Wikiの一覧",
     "どんなWikiがあるか（名前・トップページの見出し・ページ数）。見られるのは起点Wikiの管理者と、"
     "許された助手。", ("site.allwiki",)),
    (ACCOUNTS_URLPATH, "アカウント",
     "登録されている人を見る・直す・増やす・消す。パスワードの入れ直しもここ。"
     "助手は、管理者が許した操作だけ。", ("accounts.view",)),
    (APPROVALS_URLPATH, "アカウントの承認",
     "「アカウント作成」で申請された、承認待ちのアカウントを承認する・断る。",
     ("approvals.approve", "approvals.reject")),
    (f"{GROUPS_URLPATH}?tab=edit&group={STAFF_GROUP}", "助手グループ",
     "助手（staffグループ）の出入りを直す。編集できるのは管理者と、許された助手。",
     ("groups.staff",)),
    (GROUPS_URLPATH, "グループ",
     "ふつうのグループを作る・メンバーを直す。ログインしていれば誰でも開ける"
     "（直せるのは、そのグループの編集権を持つ人）。", EVERYONE),
    (STAFFPERMS_URLPATH, "助手の権限",
     "助手ごとに、どのツールのどの操作を許すかを決める。", staffperms.ADMIN_ONLY),
    (CONFIGWIKI_URLPATH, "Wikiの設定",
     "このWikiの default.yaml を、項目の説明を読みながら書き換える。", ("config.view",)),
    (PRIVILEGES_URLPATH, "アクセス制限",
     "ページごとに、閲覧と閲覧・編集を許す相手を決める。", ("privileges.view",)),
    (UPDATEPAGEAUTH_URLPATH, "ページの権限の記録の後始末",
     "#readauth・#writeauth の記録のうち、プラグインの行が無くなったページの分を消す"
     "（開くとすぐ行う。1時間ごとにも行う）。", EVERYONE),
    (STAFFLOG_URLPATH, "助手の操作の記録",
     "助手が行った操作を見る。操作の前後を見比べ、間違った操作を元に戻す。", ("stafflog.view",)),
    (OPERATIONS_URLPATH, "中断した操作",
     "途中で止まった名前の変更・移動を確かめ、続きを行う。", ("operations.view",)),
    (THEMEFILES_URLPATH + "/", "テーマのファイル",
     "テーマのファイルを扱う。スロット型のテーマ（slottheme）は既定で助手も直せる。"
     "Jinja2 のテーマ（sitetheme）は既定では管理者だけが直せる。共通のテーマから写して直す。",
     ("themes.view",)),
    (GARBAGECOLLECT_URLPATH, "削除したページの添付",
     "持ち主のページが無い添付ファイルを、ページ trashbox へ集める（1時間ごとにも行う）。",
     ("garbagecollect.run",)),
    (RESTART_URLPATH, "サービスの再起動",
     "確認の画面を開く。再起動できるのは起点Wikiの管理者と、許された助手。", ("site.restart",)),
    (UPDATE_URLPATH, "公開版からの更新",
     "いまと最新のバージョン、その間の更新履歴を見て、公開版を取り込んで再起動する。"
     "できるのは起点Wikiの管理者と、再起動を許された助手。", ("site.restart",)),
]


def serve_admin(wiki_dir, config, farm, explicit_farm, sub):
    """`/.admin` とその下を取り次ぐ。知らないサブコマンドは404。"""
    sub = (sub or "").strip("/")
    if not sub:
        return render_admin(wiki_dir, config, farm, explicit_farm)
    perms = STAFFPERMS_URLPATH[len(ADMIN_URLPATH) + 1:]
    if sub in (perms, perms + ".css", perms + ".js"):
        from wikilib.staffpermsui import render_staffperms, serve_staffperms_asset
        if sub == perms:
            return render_staffperms(wiki_dir, config, farm, explicit_farm)
        return serve_staffperms_asset(sub[len(perms) + 1:])
    if sub == STAFFLOG_URLPATH[len(ADMIN_URLPATH) + 1:]:
        from wikilib.stafflogui import render_stafflog
        return render_stafflog(wiki_dir, config, farm, explicit_farm)
    if sub == UPDATE_URLPATH[len(ADMIN_URLPATH) + 1:]:
        from wikilib.sysupdate import render_update
        return render_update(wiki_dir, config, farm, explicit_farm)
    if sub == OPERATIONS_URLPATH[len(ADMIN_URLPATH) + 1:]:
        from wikilib.operationsui import render_operations
        return render_operations(wiki_dir, config, farm, explicit_farm)
    return plain("no page", status=404)


# ---- /.admin ---------------------------------------------------------------

def render_admin(wiki_dir, config, farm, explicit_farm):
    """管理の道具の窓口。**管理者と助手**が開ける（Wiki設計者の指示、2026-09-08）。

    並べるのは `TOOLS`。助手には「管理者だけ」の道具もそうと分かる形で
    見せる（隠すと、開けないことと存在しないことの区別が付かない）。"""
    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           ADMIN_URLPATH, auth.STAFF)
    if denied is not None:
        return denied
    user = auth.current_user(wiki_dir, farm)
    context = make_plugin_context(config, farm, wiki_dir, ADMIN_URLPATH,
                                  explicit_farm)
    return sysui.page(wiki_dir, config, farm, explicit_farm, ADMIN_URLPATH, "管理",
                      admin_tools_html(context.base_url, user, userdb.is_admin(user),
                                       wiki_dir))


def _may_open(access, admin, held):
    """`TOOLS` の「要る権限」に対して、この人は開けるか。"""
    if access == EVERYONE:
        return True
    if access == staffperms.ADMIN_ONLY:
        return admin
    return admin or any(key in held for key in access)


def admin_tools_html(base_url, user, admin, wiki_dir=None):
    """`/.admin` に並ぶ道具の一覧（**画面の外枠を除いた中身だけ**）。

    **`#login` プラグインの「管理者メニュー」タブへも、これをそのまま
    差し込む**（Wiki設計者の指示、2026-09-13）。同じ一覧を2か所で組み立てると
    かならず食い違うので、**中身を持つのはここ1つ**にしてある。道具を足す
    ときに `TOOLS` へ1行書けば、両方に出る。

    `user` はログイン中のアカウント（`auth.current_user` の戻り）、
    `admin` はその人が管理者か（`userdb.is_admin`）。**呼ぶ側が関門を通した
    あとで呼ぶこと**——ここは中身を組み立てるだけで、誰が見てよいかは見ない。

    `wiki_dir` を渡すと、その人に与えられた権限（`staffperms.granted_set`）で
    「開ける」「権限がありません」を出し分ける。**差し込む側は、どちらも渡す**
    （`/.admin` の画面も、`#login` の「管理者メニュー」も）。渡さないと**既定の
    権限**（`staffperms.default_set`）で出し分けるので、管理者が既定と変えた
    助手には、実際と違う出し分けになる（開けない道具のリンクを押しても、断りの
    画面になるだけ）。出し分けが2か所で食い違わないよう、渡さない呼び出しは
    作らないこと。

    **見た目を持つのは `_sys/accounts/accounts.css` ただ1つ**で、この関数が
    `<link>` ごと連れてくる。差し込む側（`/.admin` の画面も、`#login` の
    「管理者メニュー」のタブも）は、CSSを持たない・足さない。**一覧の見た目を
    差し込む側でもう一度書くと、二重管理になる**（Wiki設計者の指示、2026-10-12。
    「ページの二重管理にならないようにしてください。二重管理にならないなら
    .admin/ ページは消す必要ありません」）。"""
    from wikilib.render import _site_root, _site_wide_commands
    from wikilib.wikiconfig import allwiki_command, load_config
    rows = []
    site_wide = _site_wide_commands()
    held = (staffperms.granted_set(wiki_dir, user) if wiki_dir is not None
            else staffperms.default_set())
    for urlpath, label, note, access in TOOLS:
        if urlpath == ALLWIKI_URLPATH:
            command = allwiki_command(load_config())
            if not command:
                continue  # 一覧を出さない設定のサイト
            urlpath = SYSTEM_PREFIX + command
        url = escape(base_url) + "/" + urlpath
        if urlpath in site_wide:
            # 既定のWikiでしか開けない画面（Wiki名付きのURLは403）なので、
            # 開いているWikiが別のWikiでも、サイトの根のURLへ向ける
            root = _site_root(base_url)
            if root is not None:
                url = escape(root) + "/" + urlpath
        if not _may_open(access, admin, held):
            # **隠さずに、開けないことを見せる。** 隠すと「無い」のか
            # 「自分には開けない」のかが分からない
            mark = "管理者だけ" if access == staffperms.ADMIN_ONLY else "権限がありません"
            name = f'{escape(label)} <span class="acct-only">{mark}</span>'
        else:
            name = f'<a href="{url}">{escape(label)}</a>'
        rows.append(f"      <tr><td>{name}</td><td>{note}</td>"
                    f"<td><code>/{escape(urlpath)}</code></td></tr>")
    who = "管理者" if admin else "助手"
    css = escape(base_url) + "/" + ACCOUNTS_URLPATH + ".css"
    return f"""<div class="acct acct-list acct-admin">
  <link rel="stylesheet" href="{css}">
  <p class="acct-lead">このWikiの管理ツールです。
    いまは «{escape(user['uid'])}»（{escape(user['name'] or '')}）＝<strong>{who}</strong>
    として開いています。</p>
  <table class="acct-table acct-tools">
    <thead><tr><th>ツール</th><th>できること</th><th>URL</th></tr></thead>
    <tbody>
{chr(10).join(rows)}
    </tbody>
  </table>
  <p class="acct-hint">これから作るツールも <code>/.admin/…</code> の下に足していきます。</p>
</div>
"""
