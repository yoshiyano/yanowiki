"""mekuri — 中身を色で塗りつぶして隠し、クリックでめくって見せる。ブロック／インライン両対応。

    #mekuri(color){{
    複数行の**中身**を隠せます。
    }}
    &mekuri(red){答え};                    文中の一部を隠す
    &mekuri(red, 3000){答え};              3秒かけてめくる
    &mekuri(color=#336, auth=g:staff){答え};   めくれる人を限る
    &mekuri(, "=w"){答え};                 このページを編集できる人だけがめくれる

 1. color … 塗りつぶしの色 (default: gray)
       color プラグインの fg/bg と同じ書きかたです。red のような色名、
       #f00 / #ff0000 / #ff0000cc（アルファつき）のような16進が書けます。
       rgb() / hsl() のような丸括弧を使う関数表記は指定できません
 2. speed … めくる時間（ミリ秒） (default: 1500＝1.5秒)
       整数だけが書けます（0なら一瞬で開きます）。単位は付けません
 3. auth  … めくることができる人 (default: 閲覧できる人は誰でも)
       ログインIDと g:グループ名 を空白で区切って並べます（引用符で囲む）。
         "alice bob"        alice と bob だけ
         g:staff            グループ staff の人だけ
         "=w"               このページの編集権限（W）がある人だけ
       =w は必ず引用符で囲みます（auth="=w" でも可）。囲まないと
       「知らない引数です」のエラーになります。
       登録されていないIDやグループを書くとエラーになります

color は1番目に書きます。speed と auth は、どちらの順でも、どちらか片方だけでも
書けます（整数なら speed、それ以外は auth として読みます）。**数字だけの文字列は、
最初の1つが speed になります。** 数字だけのログインIDを auth に指定するときは
auth=12345 のように名前を付けて書いてください（&mekuri(red, 500, 12345) のように
speed のあとに書いても通ります）。

めくれる人にだけ、隠した部分がクリック（Enter/Spaceでも可）で開きます。右から
指定の時間（既定は1.5秒）をかけて徐々に開き、いちど開いたらそのまま見えます（ページを開き直すと
また隠れます）。中身にはMarkdown記法や他のプラグインがそのまま使えます。

中身は、ページのソースを見ても直接は読めない形（暗号ではない、簡単な変換）で
HTMLに入っています。**auth を指定したときは、めくれない人には中身そのものを
送りません**（塗りつぶしだけが届く）。auth を省略したときは誰でもめくれるので、
中身の変換データは全員に届きます。変換は目隠しであって暗号ではなく、JavaScript が
読める人なら元に戻せます。強く守りたい内容は、ページの閲覧権限（#readauth）で
制限してください。
"""

""" 技術資料
本体（wikiSystem）は変えず、プラグイン単体で完結させている。

## 隠しかた
覆いは`::after`で重ね、`.is-open`が付くと`transform: scaleX(0)`
（`transform-origin: left`）へ1.5秒かけて縮める。覆いの右端が左へ動くので、
中身は右から現れる。インラインは覆いを重ねるために`inline-block`にしている
（長い文は行をまたいで折り返せなくなる）。色は`--mekuri-color`で渡し、
値は`color`プラグインと同じ`candidate`の正規表現（16進と色名だけ）で検証して
いるので、style属性へそのまま埋めても`url()`や`;`は紛れ込まない。

## 中身の変換（設計者の指示: ソースを読んでも簡単には分からないように）
中身（展開済みのHTML。改行を含む）を丸ごと1つの文字列として、
UTF-8 → 呼び出しごとのランダムな鍵（8バイト）とのXOR → Base64 にして
`data-mekuri-d`へ、鍵をBase64にして`data-mekuri-k`へ入れる（約1.33倍）。
改行も他の文字と同じバイトなので位置は分からない。Base64だけだと一目で
デコードできると分かるため、XORを挟んだ。**暗号ではない**（鍵を同じ要素に
置いているので、JSを読める人は戻せる）。
**`mekuri.js`はページの読み込み時に、めくれる人の分だけ中身を戻し**、
`.mekuri-body`で包んで`visibility:hidden`のまま入れる（`is-open`でvisibleになる）。
閉じている間も場所を取るので、覆いは本来の大きさになる（最初は、クリックで
初めて戻していたため、ダミーの大きさから開く瞬間に大きさが変わった。実機で
設計者が発見、2026-10-03）。HTMLソースには中身が無いが、DOMには読み込み後に
入る（開発者ツールでは読める。Ctrl+F・選択・印刷に出ないのは`visibility:hidden`の
効果で、ブラウザでの実測はまだ）。クリックでは覆いを縮めるだけ。
変換前の場所には、戻すまでの間の目印としてダミー（`.mekuri-dummy`）を置く。
めくれない人にはダミーしか無く、大きさは本来と一致しない（中身を送らないので
決められない）。AJAXで後から差し込まれた分は読み込み時の処理が届かないので、
クリック時に戻す（この場合だけ、開く瞬間に大きさが変わる）。
**`innerHTML`に入れた`<script>`は実行されない**。ページ読み込み時に1度だけ
走るタイプのJSには、公開されている再処理の口を呼んでいる
（`Prism.highlightAllUnder`、`KatexPlugin.renderAllUnder`。`code`・`katex`）。
ほかのプラグインのJSが読み込み時にだけ中身を処理する作りだと、隠した中では
効かない（必要なら、そのプラグインに同様の口を足す）。
入れ子（`mekuri`の中の`mekuri`）は、内側が変換済みの属性つきHTMLのまま外側の
中身として再変換される。戻したあとの内側は、それぞれ自分のクリックで開く。

## めくれない人の枠（設計者の指示: 補色の1px）
サーバーが`mekuri-locked`クラスを付け、CSSが`outline: 1px solid`で補色の枠を描く
（`border`ではなく`outline`なのは、大きさを変えないため）。補色は、CSSの相対色構文
`hsl(from var(--mekuri-color) calc(h + 180) s l)`で求める。色名も16進も同じ式で
扱え、サーバー側に色名の表を持たずに済む。相対色構文に対応していないブラウザ
（Chrome 119・Firefox 128・Safari 16.4より前）では、覆いと同じ色の枠になり、
見た目は変わらない。**無彩色（gray・black・white など）は色相を回しても同じ色**
なので、そこだけサーバー（`_edge_color`）が枠の色を決めて`--mekuri-edge`で渡す
（設計者の指示: 無彩色のときは明るさを反転した枠）。字義どおりの反転
（100%−明るさ）だと、既定の`gray`のような中間の灰色は反転しても同じ明るさで
見えないため、反転しても覆いとの明るさの差が0.4未満になる灰色だけは、黒か白の
遠いほうにしている（この部分はクロコの判断）。無彩色の判定は、CSSの色名のうち
R=G=B のもの（`GRAY_NAMES`）と、R=G=B の16進（アルファは無視）。

## めくれない人には中身を送らない（設計者の了承）
`auth`で閲覧者がめくれないときは、変換データも付けず、ダミーだけを出す。
ソースを見ても中身は無い。描画結果のキャッシュは、`wikilib`を調べた限り
見当たらず（`Cache-Control`は添付・静的資材だけ）、ページは閲覧者ごとに
その都度描かれる。ただし将来、描画結果を閲覧者をまたいで共有する仕組みが
入ると、めくれる人向けのデータが他人へ渡る／めくれる人にデータが届かない、の
どちらも起こりうる（その場合は`context`の閲覧者を見る本プラグインの前提を
見直すこと）。`auth`を省略したときは全員がめくれるので、全員にデータが届く。
成り代わり実行（`auth.act_as(SYSTEM_UID)`。`updatepageauth`が権限記録の
後始末のためにページを描く）の閲覧者`$sys`は、ユーザ記録に無いため
`g:any`にだけ当たり、データは出ない（その描画結果は使い捨て）。

## めくれる人の判定（auth）
サーバー側で閲覧者を判定し、めくれる人にだけ`data-mekuri="flip"`と
`tabindex`を付ける。JSはその属性を見るだけで、権限の判断はしない。
`context.privilege`は「ページごとのR/W/-」しか返さず、閲覧者が`g:`グループに
入っているかは分からないので、`auth.current_uid`・`userdb.find_by_uid`・
`groups.groups_of`の公開関数から`auth._user_principals`と同じ集合
（ログインID・`g:all`・所属グループ。`g:any`は誰でも）を組み立てている。
ロック・承認待ちは、未ログインと同じ扱い（`g:any`にだけ当たる）。
`=w`は`context.privilege.check(context.page)`が`W`かどうかで見る。
管理者・助手は常に編集できる決まりだが、`check`はアクセス権ルールだけに従う
ので、権限の行で締めたページでは管理者・助手でも`=w`ではめくれない。
許可者の検証は`readauth`と同じ（`privilege_records.check_who`に
`known_principals`を渡し、未知の相手は`PluginArgumentError`）。

## 引数
`color`だけ`num_order: 1`で位置を固定し、`speed`・`auth`は自由順序にしている。
自由順序は残った位置引数を**宣言順**に試し、`candidate`に合った最初の項目が
取る（`SPECIFICATIONS.md`4節）ので、`speed`（整数だけの`candidate`）を`auth`
（`candidate`無し＝何にでも合う）より先に書いている。これで「数字だけの
ログインIDと重なっても、最初の数値は`speed`」が成り立つ（設計者の指示）。
数字だけのIDを`auth`にしたいときは名前付き（`auth=12345`）で書く。
整数でない`speed`（`&mekuri(red, 1.5)`など）は`auth`として読まれ、IDとして
登録が無いので`auth`のエラーになる。
`speed`は`--mekuri-time`としてstyleへ入れる（整数だけなので、そのまま埋めても
CSSの注入にならない）。省略時はCSS側の既定（1500ms）。
`auth`はログインIDとグループ名を空白で並べるので、複数書くときは引用符で
囲む。**`=w`は引用符で囲まないと書けない**: 先頭が`=`なので`key=value`として
読まれ、「名前が空の名前付き引数」としてフレームワークが`知らない引数です`で
弾く（`_convert`/`_inline`に届く前。実測）。`"=w"`か`auth="=w"`（`auth==w`も
通るが読みにくい）で書く。設計者の「`=w`と書く」という指示は、引用符つきで
実現している。

## JS
`mekuri.js`は`document`へのクリック・キー入力のイベント委譲で、AJAXで後から
差し込まれた内容にも効く。
"""

import base64
import secrets

from wikilib.plugins import PluginArgumentError

COLOR_PATTERN = (
    r"#[0-9a-fA-F]{3,4}"
    r"|#[0-9a-fA-F]{6}"
    r"|#[0-9a-fA-F]{8}"
    r"|[a-zA-Z][a-zA-Z-]{0,30}"
)
COLOR = (COLOR_PATTERN, "re")
SPEED = (r"\d+", "re")  # ミリ秒の整数だけ

DEFAULT_COLOR = "gray"
WRITE_ONLY = "=w"

PLUGIN_INFO = {
    "help": "#mekuri(color,speed,auth){{中身}} / &mekuri(color,speed,auth){中身};",
    "expand_block": True,
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "color", "num_order": 1, "candidate": [COLOR], "default": None, "label": "塗りつぶしの色"},
        # color だけ位置を固定し、speed・auth は自由順序（speedが先に整数を取る）
        {"name": "speed", "candidate": [SPEED], "default": None, "label": "めくる時間(ms)"},
        {"name": "auth", "default": None, "label": "めくれる人"},
    ],
}


def _viewer_principals(context):
    """いまの閲覧者を指す許可者名の集合（ログインID・`g:all`・`g:グループ`・`g:any`）。
    1回の要求のあいだ`context`に覚える。"""
    cached = getattr(context, "_mekuri_principals", None)
    if cached is not None:
        return cached
    from wikilib import auth, groups, userdb
    from wikilib.pagesync import farm_of_wiki_dir

    names = {auth.ANY_PRINCIPAL}
    uid = auth.current_uid(context.wiki_dir, farm_of_wiki_dir(context.wiki_dir))
    user = userdb.find_by_uid(context.wiki_dir, uid) if uid else None
    if user is not None and not userdb.is_locked(user) and userdb.is_approved(user):
        names.add(user["uid"])
        names.add(auth.ALL_PRINCIPAL)
        names.update(auth.GROUP_PREFIX + g for g in groups.groups_of(context.wiki_dir, user["uidnum"]))
    context._mekuri_principals = names
    return names


def _can_flip(auth_arg, context):
    """この閲覧者がめくれるか。許可者の書きかたが誤りならPluginArgumentError。"""
    if not auth_arg:
        return True
    if auth_arg.strip().lower() == WRITE_ONLY:
        return context.privilege.check(context.page) == "W"
    from wikilib import privilege_records

    who, reason = privilege_records.check_who(
        auth_arg, privilege_records.known_principals(context.wiki_dir))
    if reason:
        raise PluginArgumentError(f"auth の指定が正しくありません: {reason}")
    return not _viewer_principals(context).isdisjoint(who)


KEY_BYTES = 8

# 無彩色の色名と、その灰色の濃さ（0=黒〜255=白）。CSSの色名のうち R=G=B のもの
GRAY_NAMES = {
    "black": 0, "dimgray": 105, "dimgrey": 105, "gray": 128, "grey": 128,
    "darkgray": 169, "darkgrey": 169, "silver": 192, "lightgray": 211,
    "lightgrey": 211, "gainsboro": 220, "whitesmoke": 245, "white": 255,
}
MIN_EDGE_GAP = 0.4  # 反転した枠と覆いの明るさの差の最小値（0〜1）


def _gray_level(color):
    """無彩色なら灰色の濃さ（0.0=黒〜1.0=白）、有彩色なら None。
    色名は`GRAY_NAMES`、16進は R=G=B（アルファは無視）のものだけを無彩色とする。"""
    name = color.lower()
    if name in GRAY_NAMES:
        return GRAY_NAMES[name] / 255
    if name.startswith("#"):
        h = name[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = h[0:2], h[2:4], h[4:6]
        if r == g == b:
            return int(r, 16) / 255
    return None


def _edge_color(color):
    """めくれない人の枠の色。無彩色だけ、明るさを反転した灰色（#rrggbb）を返す。
    反転しても覆いとの差が小さい中間の灰色は、黒か白のうち遠いほうにする。
    有彩色は None（CSSが補色を求める）。"""
    g = _gray_level(color)
    if g is None:
        return None
    edge = 1 - g
    if abs(edge - g) < MIN_EDGE_GAP:
        edge = 0.0 if g >= 0.5 else 1.0
    v = round(edge * 255)
    return f"#{v:02x}{v:02x}{v:02x}"


def _scramble(html):
    """中身を「UTF-8 → XOR → Base64」に変える。`(データ, 鍵)`のBase64文字列を返す。"""
    raw = html.encode("utf-8")
    key = secrets.token_bytes(KEY_BYTES)
    xored = bytes(b ^ key[i % KEY_BYTES] for i, b in enumerate(raw))
    return base64.b64encode(xored).decode("ascii"), base64.b64encode(key).decode("ascii")


def _render(tag, resolved, body, context):
    if not body:
        raise PluginArgumentError("隠す中身を指定してください: &mekuri(color){中身}; / #mekuri(color){{中身}}")
    color = resolved["color"] or DEFAULT_COLOR
    flip = _can_flip(resolved["auth"], context)
    style = f"--mekuri-color:{color}"
    if resolved["speed"]:
        style += f"; --mekuri-time:{int(resolved['speed'])}ms"
    classes = f"mekuri mekuri-{tag}"
    if not flip:
        # めくれない人の目印。有彩色の枠（補色）はCSSが求め、無彩色だけここで決める
        classes += " mekuri-locked"
        edge = _edge_color(color)
        if edge:
            style += f"; --mekuri-edge:{edge}"
    attrs = f'class="{classes}" style="{style}"'
    if not flip:
        return attrs, '<span class="mekuri-dummy"></span>'
    data, key = _scramble(body)
    attrs += (f' data-mekuri="flip" data-mekuri-d="{data}" data-mekuri-k="{key}"'
              ' tabindex="0" role="button" aria-expanded="false"'
              ' aria-label="隠された内容。クリックでめくる"')
    return attrs, '<span class="mekuri-dummy"></span>'


def _convert(resolved, body, context):
    attrs, inner = _render("block", resolved, body, context)
    return f"<div {attrs}>{inner}</div>\n"


def _inline(resolved, body, context):
    attrs, inner = _render("inline", resolved, body, context)
    return f"<span {attrs}>{inner}</span>"
