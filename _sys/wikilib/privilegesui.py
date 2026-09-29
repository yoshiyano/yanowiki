"""ページごとのアクセス制限を編集する画面（`/.admin/privileges`）。

    /.admin/privileges       画面。**管理者と助手だけ**（`/.admin` 配下）
    /.admin/privileges/api   追加・書き換え・削除を受けるJSON API

記録の読み書きは `wikilib.privilege_records` が持ち、ここは画面の組み立てとAPIの
受け口だけを持つ（`wikilib.accounts` と `wikilib.userdb` の分けかたと同じ）。

## テーマは使わない（Wiki設計者の指示、2026-09-23）

**編集画面（`editor.build_edit_page_html`）・バックアップ管理画面
（`backupui.build_backup_page_html`）と同じ理由・同じ形。** データの一覧と
書き換えの画面で、本文を読む場所ではないので、テーマの本文幅やレイアウトに
閉じ込める理由が無い。テーマを差し替えても・一から書いたテーマでも、この
画面はいつも同じ形で使える。**テーマのCSSも読み込まない**（バックアップ管理
画面と同じ判断。表の見た目はテーマの体裁を確かめる場所ではないため）。

権限が無いときの断り（403）は、これまでどおりテーマ側の画面
（`sysui.require`・`sysui.page`）で出す。**独自の見た目になるのは、開けた
あとの中身だけ。**

## 画面の作り（Wiki設計者の指示、2026-09-19。フルスクラッチで作り直した）

**1行が1ページ**。列は「ページ名・閲覧の許可者（R）・編集の許可者（W）」で、
ページ名が他の行と重なることはない。ファイルの形（`ページ名:種類:許可者:登録日`
の1行1件）は変えていない——ファイルの行を、画面ではページごとに並べ直して見せる
（`privilege_records.rows`）。

    一覧の行    ふだんは**読むだけ**。操作の列の「編集」アイコンを押すと、その行
                だけ入力欄になり、アイコンが「確定」に変わる。確定で書き込む。
                やめるアイコンで、書き込まずに読むだけへ戻る
    いちばん上  新規の入力。ページ名・閲覧・編集を書いて確定する。
                **同じページ名が既にあれば、古い情報とマージする**（許可者を足す）

**足すときはマージ、書き換えるときは置き換え**（`privilege_records` の冒頭参照）。
「編集」で開いた行の確定は、そのページの許可者を入力のとおりに置き換える
（許可者を外せる）。ページ名は、行の鍵なので編集中も書き換えられない。付け替え
たいときは、新しいページ名で足してから、古い行を削除する（付け替えの1手が、
古い行を黙って消す操作にならないように）。

## 行が消えるのは「削除」だけ

前回（2026-09-18）の直しの切り分けを、この作り直しでも守っている——
**登録・確定では行が消えない**。片側の許可者を空にするとその種類の指定が無くなる
が、**両方を空にする確定は断る**（行ごと消すのは削除だけ）。

## 古い画面が、他の人の書き換えを踏まない

行を開いたときの `version`（`privilege_records.rows`）を、確定・削除のときに一緒に
送る。開いたあとに変わっていれば、サーバーが断って**いまの一覧を返す**。画面は
その行の編集を閉じて、いまの内容を出し直す。

## 並べ替えと絞り込み

列の見出しを押すと、その列で並べ替える。許可者の絞り込みの欄は、**隠さずに並べ
替える**（Wiki設計者の指示、2026-09-13。「フィルタに合うものと合わないもので並び
替え」）——合うものが上、合わないものが下に来るだけで、件数は変わらない。
新規の入力の行は、いつでもいちばん上。

## アクセス権を評価する（Wiki設計者の指示、2026-09-22）

**ページ名を入れると、そのページで何が許されるかを表で確かめられる。** 記録は
書き換えない、読むだけの機能。

**「その他のユーザ」（未登録のIDを自分で打つ欄）は持たない**（2026-09-22、Wiki設計者の
指示で外した）。未登録のIDは、判定の上ではどれも未認証と同じ答えにしかならない
（`auth._user_principals` がNoneを返すため）——全員が共通の状態なので、未認証の1行が
あれば足りる。

**未認証と、実在する各アカウントのあいだに、「一般の認証済みユーザ」の行を1つ挟む**
（2026-09-23、Wiki設計者の指摘。「一般の認証済みユーザへの権限が現れない」）。
ログインはしているが、管理者でも助手でもなく、個別に名指しされた許可者にもカスタム
グループにも当たらない、という架空の立場（`auth.explain_privilege_generic`）。
`g:all` には当たるので、**未認証とは答えが違うことがある**（未認証は `g:any` にしか
当たらない）。実在のアカウントを1つも作らずに「ふつうにログインしただけの人」を
確かめられる。

**登録ユーザは、このページに直接影響する人だけを出す**（2026-09-23、Wiki設計者の
指示。「アカウント登録者全員を表示する必要はない、該当ページに直接影響する
アカウントだけ表示してほしい」）。「直接影響する」とは、**当たった行（R・W、system・
pluginの4つ）に、ログインIDとして名指しされているか、書かれたカスタムグループの
メンバーであること**（`_affected_uids`）。`g:all`・`g:any` は「一般の認証済み
ユーザ」「未認証」の2行でまかなえるので展開しない。管理者・助手というだけでは
（規則に名指しされていなければ）出ない——判定器はこの2つを特別扱いしないため
（`auth.PagePrivilege` の「特殊ルール」）。以前（〜2026-09-23）は登録ユーザ全員を
並べていたが、規則の無いページや大きなWikiでは表が意味なく長くなっていた。

判定そのものは `auth.explain_privilege`（`page_privilege` と同じ決めかたを、当たった行が
追えるようにした版）と `auth.page_privilege_rules`（ページだけで決まる「当たった行」の
部分。誰が見るかには関係ない）に任せ、ここは画面の組み立てとAPIの受け口、**絞り込んだ
アカウントぶんまとめて呼ぶこと**（`_evaluate_page`）だけを持つ。

**system（`config/privileges`）・plugin（`config/privileges.plugin`）の両方を見る**
（2026-09-23。`#readauth`・`#writeauth` の記録も判定に組み込んだのに合わせた）。
`explain_privilege`・`explain_privilege_generic` の結果は、`system`・`plugin` それぞれの
判定と、両者のうち厳しいほうの `result` を返す（`auth.PagePrivilege.check` と同じ考えかた）。
「直接影響するアカウント」も、system・plugin両方の当たった行から集める。

評価の結果は `PAGE_WRITE`/`PAGE_READ`/`PAGE_NONE` の3値だが、**画面には「閲覧・編集」
「閲覧のみ」「不許可」と出す**（Wiki設計者の指示。`R`/`W`/`-` の記号のままにしない）。

## 一覧はHTMLに埋め込んで渡す

画面を開いた時点のデータを、そのままHTMLへ埋め込む（`editor` のページ一覧と
同じ手）。あとから取りに行くと一覧が出るまでの間が空くだけで、二度手間に
なるため。追加・書き換え・削除のあとは、APIの応答に**更新後の一覧をまるごと**入れて
返し、画面はそれで描き直す（件数が少ないので、差分を組み立てるより単純）。
"""
import json
from html import escape

from bottle import HTTPResponse

from wikilib import auth, groups, privilege_records, stafflog, sysui, userdb
from wikilib.paths import ADMIN_URLPATH, PRIVILEGES_DIR, PRIVILEGES_URLPATH
from wikilib.themes import make_plugin_context
from wikilib.web import serve_asset

# この画面が自前で持つCSS/JS（`/.admin/privileges.css`・`.js`）
PRIVILEGES_CSS = f"{PRIVILEGES_URLPATH}.css"


def serve_privileges_asset(name):
    """`/.admin/privileges` が自前で持つCSS/JS。"""
    return serve_asset(PRIVILEGES_DIR, "privileges", name)


def _text(value):
    """APIの入力を文字列にする。文字列でなければ空（リストなどが来ても
    例外にせず、「入力が無い」として、いつもの検査で断る）。"""
    return value if isinstance(value, str) else ""


def _rows_json(wiki_dir):
    """画面へ渡す一覧。`<` を逃がしておく（HTMLへ直に埋め込むため）。"""
    return json.dumps(privilege_records.load_rows(wiki_dir),
                      ensure_ascii=False).replace("<", "\\u003c")


# 表の2行目（「一般の認証済みユーザ」）を指す予約語。ログインIDは半角英数字だけ
# （`userdb.UID_RE`）なので、`$` を含むこの値が実在のアカウントと重なることは無い
# （`auth.SYSTEM_UID` と同じ考えかた）。
GENERIC_USER_UID = "$any"


def _user_label(user):
    """評価フォームに出す、そのアカウントの表示名。名前が無ければIDだけ。"""
    return user["uid"] if not user["name"] else f'{user["uid"]}（{user["name"]}）'


def _account_status_row(wiki_dir, user):
    """評価フォーム向けの、そのアカウントの状態。`userdb.all_users` が返す行から直接作る
    （`_account_status` のように改めて `find_by_uid` で引き直さない）。

    ロック中・未承認は判定の上では未認証と同じに扱われる（`auth._user_principals`）ので、
    その旨が画面で分かるようにここへ含める。"""
    return {
        "uid": user["uid"],
        "name": user["name"] or "",
        "locked": userdb.is_locked(user),
        "approved": userdb.is_approved(user),
        "admin": userdb.is_admin(user),
        "staff": auth.is_staff(wiki_dir, user),
    }


def _affected_uids(wiki_dir, *rule_sets):
    """当たった行（`page_privilege_rules` の戻り値をいくつでも）の `who` から、
    **直接影響するアカウントのuid集合**を作る（Wiki設計者の指示、2026-09-23。
    モジュール冒頭「アクセス権を評価する」参照）。

    ログインIDとして名指しされていれば、そのまま。`g:カスタムグループ名` なら
    そのメンバー全員。`g:all`・`g:any` は「一般の認証済みユーザ」「未認証」の
    2行でまかなえるので展開しない（記録に持たない特別なグループで、メンバーの
    集合という形を持たないため）。"""
    who = set()
    for rules in rule_sets:
        for side in ("read", "write"):
            rule = rules.get(side)
            if rule:
                who.update(rule["who"])
    uids = set()
    for w in who:
        if w in (auth.ALL_PRINCIPAL, auth.ANY_PRINCIPAL):
            continue
        if w.startswith(auth.GROUP_PREFIX):
            uids.update(m["uid"] for m in groups.members(wiki_dir, w[len(auth.GROUP_PREFIX):]))
        else:
            uids.add(w)
    return uids


def _evaluate_page(wiki_dir, page):
    """このページについて、**直接影響するアカウント＋未認証・一般の認証済み
    ユーザ**、それぞれの判定をまとめて返す（評価フォームの中身。Wiki設計者の
    指示、2026-09-22・2026-09-23）。記録は読むだけで書き換えない。

    下ごしらえ（`privilege_records.load`・`load_plugin`）は1回だけ行い、人数ぶん
    読み直さない（`auth.explain_privilege`・`page_privilege_rules` の `rows`／
    `plugin_rows` 引数）。"""
    page = (page or "").strip("/")
    rows = privilege_records.load(wiki_dir)
    plugin_rows = privilege_records.load_plugin(wiki_dir)
    system_rules = auth.page_privilege_rules(wiki_dir, page, rows=rows)
    plugin_rules = auth.page_privilege_rules(wiki_dir, page, rows=plugin_rows)
    affected = _affected_uids(wiki_dir, system_rules, plugin_rules)
    users = [
        {
            "uid": "", "label": "未認証", "account": None,
            "result": auth.explain_privilege(
                wiki_dir, None, page, rows=rows, plugin_rows=plugin_rows)["result"],
        },
        {
            "uid": GENERIC_USER_UID, "label": "一般の認証済みユーザ", "account": None,
            "result": auth.explain_privilege_generic(
                wiki_dir, page, rows=rows, plugin_rows=plugin_rows)["result"],
        },
    ]
    for user in userdb.all_users(wiki_dir):
        if user["uid"] not in affected:
            continue
        users.append({
            "uid": user["uid"], "label": _user_label(user),
            "account": _account_status_row(wiki_dir, user),
            "result": auth.explain_privilege(
                wiki_dir, user["uid"], page, rows=rows, plugin_rows=plugin_rows)["result"],
        })
    return {"page": page,
            "system": {"read": system_rules["read"], "write": system_rules["write"]},
            "plugin": {"read": plugin_rules["read"], "write": plugin_rules["write"]},
            "users": users}


def render_privileges(wiki_dir, config, farm, explicit_farm):
    """画面。**管理者と助手だけ**が開ける。

    確かめるのは**中身を組み立てる前**（`sysui.require`）。開けた場合は、テーマを
    使わない独自のページ（`build_privileges_page_html`）で返す——**断りの画面
    （403）はこれまでどおりテーマ側**（モジュール冒頭「テーマは使わない」参照）。"""
    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           PRIVILEGES_URLPATH, auth.STAFF)
    if denied is not None:
        return denied
    base_url = make_plugin_context(config, farm, wiki_dir,
                                   PRIVILEGES_URLPATH, explicit_farm).base_url
    broken = privilege_records.broken_lines(wiki_dir)
    body = _html(_rows_json(wiki_dir), broken, base_url)
    theme_conf = config.get("theme") or {}
    page = build_privileges_page_html(
        site_title=theme_conf.get("site_title", "wikiSystem"),
        home_url=base_url + "/",
        admin_url=base_url + "/" + ADMIN_URLPATH,
        body=body,
        asset_url=base_url + "/" + PRIVILEGES_URLPATH,
    )
    return HTTPResponse(body=page, status=200, content_type="text/html; charset=utf-8")


def build_privileges_page_html(site_title, home_url, admin_url, body, asset_url):
    """アクセス制限の画面のページ全体を組み立てる。**テーマは使わない**
    （モジュール冒頭「テーマは使わない」参照。`editor.build_edit_page_html`・
    `backupui.build_backup_page_html` と同じ形）。

    編集画面と違い、ページ一覧（treeview）は無い——アクセス制限は特定の1ページを
    起点に開く画面ではないため。バックアップ管理画面と同じく、**テーマのCSSも
    読み込まない**。"""
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>アクセス制限 - {escape(site_title)}</title>
<link rel="stylesheet" href="{escape(asset_url)}.css">
</head>
<body class="prv-body">
<header class="prv-head">
  <a class="prv-home" href="{escape(home_url)}">{escape(site_title)}</a>
  <span class="prv-head-title">アクセス制限</span>
  <a class="prv-back" href="{escape(admin_url)}">管理の画面へ戻る</a>
</header>
<main class="prv-main">
{body}</main>
<script src="{escape(asset_url)}.js" defer></script>
</body>
</html>
"""


def render_privileges_api(wiki_dir, config, farm, explicit_farm):
    """追加・書き換え・削除を受けるJSON API。

    受け取るのは `{"op": "add"|"set"|"delete", "page", …}`。**どの操作でも、
    更新後の一覧をまるごと返す**（画面はそれで描き直す）。

        add     `page`・`r`・`w`（許可者をカンマか空白で並べた文字列）。
                同じページ名があれば、古い情報とマージする
        set     `add` と同じ入力に `version`。そのページのR・Wを置き換える
        delete  `page` と `version`。そのページのR・Wを両方消す

    `version` は行を開いたときの値。開いたあとに変わっていれば断られる
    （モジュール冒頭「古い画面が、他の人の書き換えを踏まない」参照）。"""
    denied = sysui.require(wiki_dir, config, farm, explicit_farm,
                           PRIVILEGES_URLPATH, auth.STAFF)
    if denied is not None:
        # 画面ではなくJSONで断る（APIを叩いているのは画面のJSなので）
        return sysui.json_out({"ok": False, "message": "権限がありません。"},
                              status=403)
    data = sysui.json_body()
    op = _text(data.get("op"))
    page = _text(data.get("page"))
    version = data.get("version")
    version = version if isinstance(version, str) else None
    # 助手の書き換えは、そのページの行を前後で控えて記録する（wikilib.stafflog）
    staff = stafflog.actor(wiki_dir, farm) if op in ("add", "set", "delete") else None
    before = _page_rules(wiki_dir, page) if staff is not None else None
    if op == "add":
        ok, message, rows = privilege_records.add_page(
            wiki_dir, page, _text(data.get("r")), _text(data.get("w")))
    elif op == "set":
        ok, message, rows = privilege_records.set_page(
            wiki_dir, page, _text(data.get("r")), _text(data.get("w")),
            version=version)
    elif op == "delete":
        ok, message, rows = privilege_records.delete_page(
            wiki_dir, page, version=version)
    elif op == "evaluate":
        # 記録は書き換えない。読むだけ（モジュール冒頭「アクセス権を評価する」参照）
        return sysui.json_out({"ok": True, **_evaluate_page(wiki_dir, page)})
    else:
        return sysui.json_out({"ok": False, "message": "知らない操作です。"},
                              status=400)
    if ok and staff is not None:
        after = _page_rules(wiki_dir, page)
        if after != before:
            stafflog.record(wiki_dir, staff, "privileges.page", page,
                            {"add": "登録した", "set": "書き換えた", "delete": "消した"}[op],
                            before=before, after=after)
    return sysui.json_out({"ok": ok, "message": message, "rows": rows})


def _page_rules(wiki_dir, page):
    """そのページの行（`config/privileges`）。助手の操作の記録に使う。"""
    return [e for e in privilege_records.load(wiki_dir) if e["page"] == page]


def _html(rows_json, broken, base_url):
    """画面の中身。表の行（新規の入力の行を含む）と、評価フォームの結果は `privileges.js` が描く。"""
    warn = ""
    if broken:
        warn = sysui.notice(
            "読めない行が{}件あります（config/privileges を直してください）。"
            "その行は無いものとして扱っています。".format(broken),
            bad=True, prefix="prv")
    return f"""<div class="prv" data-api="{escape(base_url)}/{PRIVILEGES_URLPATH}/api">
{warn}
  <p class="prv-lead">ページごとに、閲覧と編集を許す相手を決めます。
    行はふだん読むだけで、鉛筆（編集）で書き換え、確定で登録します。</p>

  <details class="prv-help">
    <summary>書きかたと決まりごと</summary>
    <p>ページ名は <code>Tech/Secret</code> のようなフルパスか、
      <code>Tech/*</code>・<code>*/Secret</code> のような前後どちらかの一致で書きます。
      <code>Tech/*</code> は入口のページ <code>Tech</code> にも当たります（<code>Tech</code> だけ
      別に決めるなら、<code>Tech</code> と書いた行を足します）。
      許可者は、ログインIDか <code>g:グループ名</code>（<code>g:all</code> は登録ユーザ全員、
      <code>g:any</code> は未ログインを含む誰でも）を、カンマか空白で並べます。</p>
    <ul>
      <li><strong>ワイルドカード使用のルールが複数個一致する場合は、一致したルール文字列が
        長いものが優先されます。</strong>
        完全一致（ワイルドカードを使わない指定）は、どのワイルドカードよりも常に優先されます。
        同じ長さで複数当たった場合は、それらの許可者をまとめて使います。</li>
      <li><strong>閲覧と編集は別々に決まります。</strong>
        編集できるのは、<strong>閲覧できる人のうち、編集の欄にも載っている人だけ</strong>です
        （閲覧の欄に載っていない人は、編集の欄に載っていても何もできません）。</li>
      <li><strong>指定の無い欄は、誰にでも許します。</strong>
        閲覧だけを書いたページは、載っている人が読めて、その人たちは編集もできます。
        読むだけにしたい人がいるなら、編集の欄も書いてください。
        編集だけを書いたページは、載っていない人も読むことだけはできます。</li>
      <li>いちばん上の行は新規の入力です。<strong>同じページ名が既にあれば、
        許可者を足してまとめます</strong>（既にいる人は消えません）。</li>
      <li>行の「編集」は、その行を書き換える入力欄にします。
        <strong>確定すると、その行の許可者は入力のとおりに置き換わります。</strong>
        片側を空にすると、その種類の指定が無くなります
        （同じページに当たるワイルドカードの指定があれば、そちらが効きます）。</li>
      <li>記録が消えるのは、「削除」を押したときだけです。</li>
    </ul>
    <p class="prv-hint">記録は <code>config/privileges</code> にテキストで置いてあります
      （1行1件: <code>ページ名:種類:許可者,…:登録日</code>）。
      書けなくなったときは、そのファイルを直接直せます。</p>
  </details>

  <div class="prv-notice" id="prv-notice" role="status" hidden></div>

  <div class="prv-toolbar">
    <label for="prv-filter">許可者で絞り込み</label>
    <input type="search" class="prv-filter" id="prv-filter"
           placeholder="合う行が上に来ます" autocomplete="off">
  </div>

  <div class="prv-tablewrap">
    <table class="prv-table" id="prv-table">
      <thead>
        <tr>
          <th><button type="button" class="prv-sort" data-sort="page">ページ名</button></th>
          <th><button type="button" class="prv-sort" data-sort="r">閲覧の許可者</button></th>
          <th><button type="button" class="prv-sort" data-sort="w">編集の許可者</button></th>
          <th><button type="button" class="prv-sort" data-sort="stamp">更新日</button></th>
          <th class="prv-ops">操作</th>
        </tr>
      </thead>
      <tbody id="prv-rows"></tbody>
    </table>
  </div>

  <details class="prv-eval" id="prv-eval">
    <summary class="prv-eval-summary">アクセス権を評価する</summary>
    <p class="prv-eval-lead">ページ名を入れると、そのページで何が許されるかを表で
      確かめられます。未認証・一般の認証済みユーザと、<strong>このページに直接
      影響するアカウント</strong>（規則に名指しされている人・カスタムグループの
      メンバー）だけを並べます。<strong>記録は書き換えません。</strong></p>
    <div class="prv-eval-form">
      <div class="prv-eval-row">
        <label for="prv-eval-page">ページ名</label>
        <input type="text" id="prv-eval-page" placeholder="Tech/Secret" autocomplete="off">
      </div>
    </div>
    <div class="prv-eval-result" id="prv-eval-result" aria-live="polite"></div>
  </details>
</div>
<script id="prv-data" type="application/json">{rows_json}</script>
<script src="{escape(base_url)}/{PRIVILEGES_URLPATH}.js" defer></script>
"""
