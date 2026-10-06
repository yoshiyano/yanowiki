"""管理の道具をまとめた窓口（/.admin）。

    /.admin                窓口。**管理者と助手**が開ける
    /.admin/accounts       アカウント一覧・編集。**管理者だけ**
    /.admin/configwiki     Wikiの設定。管理者と助手

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

from wikilib import auth, sysui, userdb
from wikilib.paths import (
    ACCOUNTS_URLPATH, ADMIN_URLPATH, APPROVALS_URLPATH, CONFIGWIKI_URLPATH,
    GARBAGECOLLECT_URLPATH, GROUPS_URLPATH, NEWWIKI_URLPATH, PRIVILEGES_URLPATH,
    STAFFLOG_URLPATH,
)
from wikilib.groups import STAFF_GROUP
from wikilib.themes import make_plugin_context
from wikilib.web import plain

# 窓口に並べる道具。**「管理者だけ」かどうかもここに書く**（画面の出し分けと、
# 実際の入口での判定が食い違わないよう、並びは1か所にまとめておく）。
#
#   (URLパス, 名前, 説明, 管理者だけか)
TOOLS = [
    (NEWWIKI_URLPATH, "新しいWikiを作る",
     "自分用のWikiを作る。作れるのは既定のWikiの管理者と助手。", False),
    (ACCOUNTS_URLPATH, "アカウント",
     "登録されている人を見る・直す・増やす・消す。パスワードの入れ直しもここ。", True),
    (APPROVALS_URLPATH, "アカウントの承認",
     "「アカウント作成」で申請された、承認待ちのアカウントを承認する・断る。", False),
    (f"{GROUPS_URLPATH}?tab=edit&group={STAFF_GROUP}", "助手グループ",
     "助手（staffグループ）の出入りを直す。編集できるのは管理者と助手。", False),
    (CONFIGWIKI_URLPATH, "Wikiの設定",
     "このWikiの default.yaml を、項目の説明を読みながら書き換える。", False),
    (PRIVILEGES_URLPATH, "アクセス制限",
     "ページごとに、閲覧と閲覧・編集を許す相手を決める。", False),
    (STAFFLOG_URLPATH, "助手の操作の記録",
     "助手が行った操作を見る。操作の前後を見比べ、間違った操作を元に戻す。", True),
    (GARBAGECOLLECT_URLPATH, "削除したページの添付",
     "持ち主のページが無い添付ファイルを、ページ trashbox へ集める（1時間ごとにも行う）。", False),
]


def serve_admin(wiki_dir, config, farm, explicit_farm, sub):
    """`/.admin` とその下を取り次ぐ。知らないサブコマンドは404。"""
    sub = (sub or "").strip("/")
    if not sub:
        return render_admin(wiki_dir, config, farm, explicit_farm)
    if sub == STAFFLOG_URLPATH[len(ADMIN_URLPATH) + 1:]:
        from wikilib.stafflogui import render_stafflog
        return render_stafflog(wiki_dir, config, farm, explicit_farm)
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
                      admin_tools_html(context.base_url, user, userdb.is_admin(user)),
                      css_url=f"{ACCOUNTS_URLPATH}.css")


def admin_tools_html(base_url, user, admin):
    """`/.admin` に並ぶ道具の一覧（**画面の外枠を除いた中身だけ**）。

    **`#login` プラグインの「管理者メニュー」タブへも、これをそのまま
    差し込む**（Wiki設計者の指示、2026-09-13）。同じ一覧を2か所で組み立てると
    かならず食い違うので、**中身を持つのはここ1つ**にしてある。道具を足す
    ときに `TOOLS` へ1行書けば、両方に出る。

    `user` はログイン中のアカウント（`auth.current_user` の戻り）、
    `admin` はその人が管理者か（`userdb.is_admin`）。**呼ぶ側が関門を通した
    あとで呼ぶこと**——ここは中身を組み立てるだけで、誰が見てよいかは見ない。

    見た目は `_sys/accounts/accounts.css`（`acct-` のクラス）に載っている。
    差し込む側は、そのCSSが届く場所であることを確かめること。"""
    rows = []
    for urlpath, label, note, admin_only in TOOLS:
        url = escape(base_url) + "/" + urlpath
        if urlpath == NEWWIKI_URLPATH:
            # 既定のWikiでしか開けない画面（Wiki名付きのURLは403）なので、
            # 開いているWikiが別のWikiでも、サイトの根のURLへ向ける
            from wikilib.render import _site_root
            root = _site_root(base_url)
            if root is not None:
                url = escape(root) + "/" + urlpath
        if admin_only and not admin:
            # **隠さずに、開けないことを見せる。** 隠すと「無い」のか
            # 「自分には開けない」のかが分からない
            name = f'{escape(label)} <span class="acct-only">管理者だけ</span>'
        else:
            name = f'<a href="{url}">{escape(label)}</a>'
        rows.append(f"      <tr><td>{name}</td><td>{note}</td>"
                    f"<td><code>/{escape(urlpath)}</code></td></tr>")
    who = "管理者" if admin else "助手"
    return f"""<div class="acct">
  <p class="acct-lead">このWikiの管理の道具です。
    いまは «{escape(user['uid'])}»（{escape(user['name'] or '')}）＝<strong>{who}</strong>
    として開いています。</p>
  <table class="acct-table acct-tools">
    <thead><tr><th>道具</th><th>できること</th><th>URL</th></tr></thead>
    <tbody>
{chr(10).join(rows)}
    </tbody>
  </table>
  <p class="acct-hint">これから作る道具も <code>/.admin/…</code> の下に足していきます。</p>
</div>
"""
