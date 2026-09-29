"""新しいWikiを作る（/.newwiki）。

`wikidata/<Wiki名>/` の下に、1つのWikiが必要とするフォルダ一式と説明ファイル、
それに最初のページを用意する。手で8つのフォルダを作るのと同じことを、
決まった形で漏れなく行うためのもの。

作ったWikiは `/=<Wiki名>/` で開ける。画面の「既定のWikiにする」に
チェックが入っていれば、作成に続けて `config/server.yaml` の
`farm.default` も書き換える（`set_default_farm`）。チェックの初期状態は、
既存のWikiが `_system` だけ（＝まだ自分のWikiが無い）なら入り、
他に1つでもあれば外れる。はじめて使う人が迷わず自分のWikiへ入れるように
しつつ、複数Wikiを使い分けている人の設定を勝手に変えないためのバランス。

**作るときに「利用形態」を選ぶ**（Wiki設計者の指示、2026-09-21）。選んだ形態に
応じて、そのWikiの**権限の既定値**（`config/privileges` の既定の行 `*`）と、
**ユーザ登録の受け入れかた**（`account.policy`）を最初から与える（`USAGES`）。
"""
import os
import re
from html import escape
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib.paths import (
    CONFIG_PATH, DEFAULT_FARM_FALLBACK, FARM_PREFIX, INDEX_NAME,
    NEWWIKI_DIR, NEWWIKI_URLPATH, SYSTEM_PREFIX, WIKIDATA_DIR, default_markup_ext, safe_join,
)
from wikilib import stafflog
from wikilib.web import serve_asset
from wikilib.wikiconfig import (
    default_markup, example_of, farm_config_path, load_config, save_farm_config,
    set_default_farm,
)

# Wiki名に許す文字。URLの一部になり、フォルダ名にもなるので控えめにしておく
WIKI_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# 作るときに選ぶ「利用形態」（Wiki設計者が挙げた5つの使いかた、2026-09-20）。
# **権限の既定値（既定の行）とユーザ登録の受け入れかたの組**で表す。
#
#   キー      形態の名前（画面のラジオボタンの値）
#   title     画面の選択肢の見出し（短く）
#   label     どんな場面向けか
#   read / write / signup  読める人・書ける人・アカウントの作りかたの要約。
#             画面では見出しの下に3つ並べ、違いが一目で比べられるようにする
#   rules     置く既定の行 (ページ名, 種類, 許可者)。`privilege_records.put` へそのまま渡す
#   policy    `account.policy` に書く値。None なら書かない（共通の既定に従う）
#
# 形態1（自分だけ）と形態2（LAN内で自由）は、権限の行としては同じ（何も置かない）
# なので、まとめて1つ（`free`）にしてある。**違いは「ログインの入口を出すか」だけで、
# いまはそこまで分けていない。**
USAGES = {
    "free": {
        "title": "自由に書き換える",
        "label": "自分だけ、またはLAN内の信頼できる人だけで、ログインなしに使う",
        "read": "誰でも",
        "write": "誰でも（ログイン不要）",
        "signup": "誰でも自由に",
        "rules": (),
        "policy": None,
    },
    "named": {
        "title": "ログインした人が編集",
        "label": "LAN内で複数人が書き換える。誰の文責かを残す",
        "read": "誰でも",
        "write": "ログインした人",
        "signup": "誰でも自由に",
        "rules": (("*", "R", "g:any"), ("*", "W", "g:all")),
        "policy": "open",
    },
    "public": {
        "title": "外部に公開（承認制）",
        "label": "外部に公開する。アカウントは助手の承認を経て使えるようにする",
        "read": "誰でも",
        "write": "ログインした人",
        "signup": "申請して、助手・管理者の承認が要る",
        "rules": (("*", "R", "g:any"), ("*", "W", "g:all")),
        "policy": "approval",
    },
    "members": {
        "title": "メンバー限定（承認制）",
        "label": "閲覧にもログインが要る。編集は管理者・助手だけ",
        "read": "ログインした人",
        "write": "管理者と助手だけ",
        "signup": "申請して、助手・管理者の承認が要る",
        "rules": (("*", "R", "g:all"), ("*", "W", "admin,g:staff")),
        "policy": "approval",
    },
}
# 選ばなかったときの形態。**これまでの動き**（何も置かない）のままにしてある
USAGE_DEFAULT = "free"

# 1つのWikiが持つフォルダと、その説明ファイル。
# 既存の wikidata/_system/ と同じ構成にしてある。
FOLDERS = {
    "wiki": None,  # ページ本体。説明ファイルは置かず、最初のページとメニューを入れる
    "attach": """このディレクトリには、wiki/ 配下の各ページに添付されたファイルが保存されます。
配置場所はページのパスをそのままミラーします。

（例）
  wiki/data/file.txt  に添付するファイルは  attach/data/file/  以下に配置
  wiki/index.txt      に添付するファイルは  attach/index/      以下に配置

URLは /.attach/<配置場所> で配信されます（例: /.attach/index/logo.png）。
""",
    "plugin": """この wiki 固有の拡張プラグインを配置するディレクトリです。
全 wiki 共通のプラグインはトップレベルの plugin/ に配置します。

同じ名前のプラグインが両方にある場合、こちらが優先されます。
""",
    "theme": """この wiki 固有のテーマを配置するディレクトリです。
全 wiki 共通のテーマはトップレベルの theme/ に配置します。

ここに base.html / base.css / base.js を置くと、同名の共通テーマより優先され、
このwikiだけレイアウトやデザインを差し替えられます。

共通テーマを継承する場合は "common/" を付けた名前で参照してください
（"base.html" と書くとこのファイル自身を継承することになり、無限再帰になります）。
""",
    "config": """この wiki 固有の設定ファイルを配置するディレクトリです。

default.yaml に書いた項目が、共通の設定（トップレベルの config/default.yaml）を
上書きします。書かれていない項目は共通のものがそのまま使われるため、
変えたい項目だけを残せば十分です。

このディレクトリの default.yaml は、Wikiを作ったときに共通の設定を写したものです。
何を設定できるのかが分かるよう、まるごと写してあります。

サービスの起動に関わる設定（server / farm / debug）はここに書いても効きません。
どのWikiを開くかが決まる前に要る値なので、トップレベルの config/server.yaml
だけを見ます。
""",
    "log": """このディレクトリには、正常アクセスのログが保存されます。
ログファイル自体はGit管理対象外とし、このディレクトリ構成を保持するための
説明ファイルのみを残しています。

現時点ではログ記録機能は未実装です。
""",
    "pageinfo": """このディレクトリには、ページに付随する記録が置かれます。

  backup/     ページを保存したときの差分
  draft/      編集中の書きかけ（一時保存）
  upload/     何回かに分けて送られているファイルの、継ぎ足しの途中
  wikiall.db  ページ本文と、そこから取り出した情報のデータベース

wikiall.db は wiki/ の平文ファイルと同じ内容をSQLiteにも持たせたものです。
全文検索・更新順の一覧・保存時の差分の基準に使います。平文のほうが正本なので、
壊れたり消したりしても平文から作り直せます。

いずれも「ページそのものではないが、ページ1枚ごとに紐づく記録」で、
システムが自動で書き込みます。手で編集するものではありません。

Wikiの直下に並ぶそれ以外のフォルダ（wiki/ attach/ plugin/ theme/ config/）は、
利用者が中身を書き換えるものです。性格が違うので分けています。
""",
    "pageinfo/draft": """このディレクトリには、編集中の書きかけ（一時保存）が置かれます。

編集画面のページ一覧から別のページへ移ると、書きかけがここへ預けられます。
確認を出さずに移れるようにするためのもので、更新履歴にもバックアップにも残りません。
預かっているページは、編集画面のページ一覧で赤い太字になります。

ファイル名は <ページ名>.draft です。ページ名の付けかたは backup/ と同じで、
wiki/ からのパス（拡張子抜き）の "/" を "_" に置き換えたものです。
元から "_" を含む名前は "__" に退避してから置き換えます。

同じ名前に .draft.origin を足したファイルが対になっていることがあります。
これは書きかけを預けた時点の本文のハッシュ（何を元に書き始めた書きかけか）
で、保存時の競合検出（編集を始めたあとに他の誰かが更新していないか）の
基準に使います。無くても動作します（古い書きかけとの後方互換）。

保存すると、どちらの預かりも自動で消えます。
""",
    "pageinfo/upload": """このディレクトリには、何回かに分けて送られているファイルの、継ぎ足しの途中が置かれます。

1回のPOSTで送れる大きさには上限があるため、大きな添付ファイルや長い本文の一時保存は、
編集画面が 1MB ずつに切って順に送ります。受け取った切れ端はここで継ぎ足され、
全部そろった時点で本来の置き場所（attach/ や draft/）へ移されます。

ファイル名は <送信ごとの名前>.part（継ぎ足している中身）と <送信ごとの名前>.meta
（何番目まで受け取ったか）です。送信ごとの名前は編集画面が毎回付ける英数字24文字です。

送っている最中に画面を閉じた場合などは、完成しないまま残ります。これは次の送信が
始まったときに、1時間より古いものからまとめて片づけられます。
""",
    "pageinfo/backup": """このディレクトリには、wikiページを保存したときの差分が記録されます。

ファイル名は <ページ名>.<yymmdd_hhmmss>.diff です。
ページ名は wiki/ からのパス（拡張子抜き）で、階層の "/" を "_" に置き換えたものです。
元から "_" を含む名前は "__" に退避してから置き換えます。

中身は unified diff（上書き前 -> 上書き後）です。現在のファイルに新しいものから
順に逆適用していくことで、過去の内容を復元できます。
""",
}


def wiki_exists(name):
    return os.path.isdir(os.path.join(WIKIDATA_DIR, name))


def validate_name(name):
    """Wiki名を確かめる。問題なければ None、あれば理由を返す。"""
    if not name:
        return "Wikiの名前を入れてください。"
    if not WIKI_NAME_RE.match(name):
        return ("名前に使えるのは半角英数字と - _ で、先頭は英数字です"
                "（URLの一部になり、フォルダ名にもなるためです）。")
    if name.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
        return f"「{FARM_PREFIX}」「{SYSTEM_PREFIX}」で始まる名前は使えません。"
    if wiki_exists(name):
        return f"「{name}」はすでにあります。"
    return None


def initial_page(name, title):
    """最初のページ（wiki/index）の中身。

    トップ画面だと分かれば十分なので、短くしておく。
    中身は作った人が書き換える前提。

    書式は既定の記法（`edit.defaultwiki`）で書く。作った直後のページを開いて
    「編集」を押したときのツールバーと、置いてあるページの書きかたを揃えるため。

    説明ページ（/Syntax など）へのリンクは置かない。ページはWikiごとに別なので、
    新しいWikiの中には無く、リンク切れになるため。"""
    return f"""* {title}

{name} のトップページです。

上の「編集」から書き換えられます。
"""


def initial_menu(name):
    """最初のメニュー（wiki/mainmenu）の中身。

    サイドバーに出るメニューもふつうのページなので、
    ここに置いておけば最初から使える状態になる。

    見出しは h2 から始める（`*` ではなく `**`）。サイドバーの中の見出しなので、
    本文と同じ h1 で始めると、テーマが本文の大見出し向けに用意した大きさで出る。"""
    return f"""** メニュー

- [[トップ>/]]

*** このWikiについて

- 名前: {name}
"""


def copy_common_config(root):
    """既定値の雛形（config/default.example.yaml）を、そのWikiの config/ に
    default.yamlとして写す。

    ここに書いた項目が既定値を上書きする。書き換えの出発点として、
    何が設定できるのかがその場で見られるよう、まるごと写しておく。

    **これは新規作成という明示的な操作のときだけ行う。** 既にあるWikiを
    開いたときに同じことを自動でやると、そのあと既定値（雛形）を直しても
    複製済みのWiki側には反映されなくなる（wikilib.wikiconfig.load_config
    のdocstring参照）。ここは「作った瞬間の値で編集の出発点を作る」という
    利用者の能動的な操作の結果なので、その事故には当たらない。"""
    example_path = example_of(CONFIG_PATH)
    if not os.path.isfile(example_path):
        return False
    try:
        with open(example_path, encoding="utf-8") as f:
            text = f.read()
        with open(os.path.join(root, "config", "default.yaml"), "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except OSError:
        return False


def write_policy(new_wiki_dir, policy, copied):
    """そのWikiの `account.policy` を書く。`copied` は default.yaml が雛形の写しか。

    写しなら、**コメントを残したまま**その1行だけを置き換える（設定画面から
    書くとコメントが消え、写しが「人の手が入ったもの」として控えられてしまう）。
    写しでなければ、設定画面と同じ書き出し（`save_farm_config`）で
    `account.policy` だけを持つ default.yaml を作る。"""
    path = farm_config_path(new_wiki_dir)
    if not copied:
        ok, _saved, message = save_farm_config(new_wiki_dir, {"account": {"policy": policy}})
        return ok, message
    with open(path, encoding="utf-8") as f:
        text = f.read()
    pattern = re.compile(r"(^account:\n(?:[ \t].*\n|\n)*?[ \t]+policy:[ \t]*)\S+", re.MULTILINE)
    new_text, count = pattern.subn(lambda m: m.group(1) + policy, text, count=1)
    if not count:
        new_text = text.rstrip("\n") + f"\n\naccount:\n  policy: {policy}\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return True, ""


def create_wiki(name, title, independent_config=False, admin_password="",
                usage=USAGE_DEFAULT):
    """Wikiの入れものを作る。(成否, 知らせる文言) を返す。

    usage … 利用形態（`USAGES` のキー）。そのWikiの権限の既定値とユーザ登録の
        受け入れかたを、最初から与える。省略すると `free`（何も置かない。
        これまでの動き）。知らない値なら**何も作らずに断る**。

    admin_password … このWikiの `admin` の最初のパスワード。**画面からは
        必ず入れてもらう**（Wiki設計者の指示、2026-09-08）。省略できるのは、
        呼び出し側のテストなど画面を通らない場合だけで、そのときは
        既定の `adminpw` になる（`wikilib.userdb.create_db` 参照）。

    independent_config … Trueなら、既定値の雛形（config/default.example.yaml）
        を最初からこのWikiのconfig/default.yamlとして複製する
        （copy_common_config参照）。falseが既定——複製しなければ、この
        Wikiは自分のconfig/に何も持たず、既定値をそのまま使い続ける
        （wikilib.wikiconfig.load_configのdocstring参照。複製すると
        「複製した瞬間の値で固定される」ため、既定値の変更に追従したい
        場合は複製しないほうがよい。あとから設定を個別に変えたく
        なったときに複製する、という選びかたを想定している）。
        この関数の既定値は False のままだが、**作成画面（`/.newwiki`）のチェックは
        既定で入れてある**（Wiki設計者の指示、2026-09-15。`render_newwiki` 参照）。"""
    problem = validate_name(name)
    if problem:
        return False, problem
    if usage not in USAGES:
        return False, "利用形態が正しくありません。"

    # wikidata/ の外に出る指定になっていないか確かめる（validate_nameの
    # WIKI_NAME_REで既に弾いているはずだが、念のため二重に）
    root = safe_join(WIKIDATA_DIR, name)
    if root is None:
        return False, "その名前では作れません。"

    try:
        for folder, readme in FOLDERS.items():
            # キーは "pageinfo/draft" のように階層を持つことがある
            path = os.path.join(root, *folder.split("/"))
            os.makedirs(path, exist_ok=True)
            if readme:
                with open(os.path.join(path, "README.txt"), "w", encoding="utf-8") as f:
                    f.write(readme)
        # 最初のページは既定の記法で置く（拡張子もその記法のもの）。
        # 記法は既定値（config/default.example.yaml の edit.defaultwiki）に
        # 従う。independent_configの有無に関わらず、load_config()自体が
        # この既定値を直接読むので、作った直後の中身と設定は食い違わない。
        ext = default_markup_ext(default_markup(load_config()))
        pages = {
            INDEX_NAME + ext: initial_page(name, title or name),
            "mainmenu" + ext: initial_menu(name),
        }
        for filename, text in pages.items():
            with open(os.path.join(root, "wiki", filename), "w", encoding="utf-8") as f:
                f.write(text)
        if independent_config:
            copy_common_config(root)
    except OSError as e:
        return False, f"作れませんでした（{e}）。"

    # 置いたページをDBにも入れておく（以後の保存で差分の基準になる）
    from wikilib.pagedb import rebuild
    rebuild(os.path.join(root, "wiki"))

    # アカウントの記録（config/users.db）もここで用意する。**画面を開いた
    # ときには作らない**ので、作る場所はここと `./wiki.py initusers` だけ
    # （Wiki設計者の指示、2026-09-05。理由は wikilib.userdb の冒頭）
    new_wiki_dir = os.path.join(root, "wiki")
    from wikilib.userdb import create_db
    create_db(new_wiki_dir, admin_password)

    # 助手グループ（staff）にadminを先に入れておく（Wiki設計者の指示、2026-09-12。
    # 「予め作る」）。以降は普通のグループと同じ扱いになる
    from wikilib.groups import ensure_staff_group
    ensure_staff_group(new_wiki_dir)

    # 利用形態に応じた権限の既定値とユーザ登録の受け入れかた。**アカウントの記録が
    # 無いと許可者（admin・g:staff）を確かめられない**ので、上のあとに置く
    from wikilib import privilege_records
    chosen = USAGES[usage]
    for page, kind, who in chosen["rules"]:
        ok, message, _ = privilege_records.put(new_wiki_dir, page, kind, who)
        if not ok:
            return False, f"権限の既定値を置けませんでした（{message}）。"
    if chosen["policy"] is not None:
        try:
            ok, message = write_policy(new_wiki_dir, chosen["policy"], independent_config)
        except OSError as e:
            ok, message = False, str(e)
        if not ok:
            return False, f"ユーザ登録の受け入れかたを書けませんでした（{message}）。"

    return True, f"Wiki「{name}」を作りました。"


def render_newwiki(wiki_dir, config, farm, explicit_farm):
    """/.newwiki の画面。GETで入力、POSTで作成する。

    **既定Wikiの管理者と助手だけが開ける**（Wiki設計者の指示、2026-09-13）。
    Wikiを増やすのはサービス全体に効く操作なので、判定は開いているWikiでは
    なく既定Wikiのアカウントで行う（`sysui.require_on_default_farm`）。
    確かめるのは**中身を組み立てる前、POSTを処理する前**。"""
    from wikilib import sysui  # 循環を避けるため呼び出し時に読み込む
    from wikilib.allwiki import wiki_names
    from wikilib import sysui
    from wikilib.themes import make_plugin_context

    denied = sysui.require_on_default_farm(config, farm, wiki_dir, explicit_farm,
                                           NEWWIKI_URLPATH)
    if denied is not None:
        return denied

    context = make_plugin_context(config, farm, wiki_dir, NEWWIKI_URLPATH, explicit_farm)
    action = context.base_url + "/" + NEWWIKI_URLPATH

    name = (request.forms.getunicode("name", "") or "").strip()
    title = (request.forms.getunicode("title", "") or "").strip()
    message, ok = "", True

    if request.method == "POST":
        set_default = request.forms.get("set_default") is not None
        independent_config = request.forms.get("independent_config") is not None
        usage = request.forms.get("usage") or USAGE_DEFAULT
        # 管理者のパスワードは**必ず入れてもらう**（Wiki設計者の指示、2026-09-08）。
        # 既定値のまま作ると、そのWikiは「誰でも知っている値で管理者に
        # 入れる」状態から始まってしまう
        admin_pw = request.forms.getunicode("admin_pw", "") or ""
        admin_pw2 = request.forms.getunicode("admin_pw2", "") or ""
        if not admin_pw:
            ok, message = False, "管理者のパスワードを入力してください。"
        elif admin_pw != admin_pw2:
            ok, message = False, "管理者のパスワードの2つの欄が一致しません。"
        else:
            ok, message = create_wiki(name, title, independent_config, admin_pw, usage)
        if ok:
            staff = stafflog.actor(wiki_dir, farm)
            if staff is not None:
                stafflog.record(wiki_dir, staff, "wiki.create", name, "作った",
                                before=None, after={"name": name, "title": title})
            if set_default:
                set_default_farm(name)
            # 作れたら、その新しいWikiのトップへ送る
            return HTTPResponse(status=303, headers={
                "Location": "{}/{}{}/".format(
                    context.base_url.rsplit("/" + FARM_PREFIX, 1)[0],
                    FARM_PREFIX, urlquote(name)),
            })
    else:
        # まだ _system しか無い（＝自分のWikiがまだ無い）なら、既定で
        # チェックを入れておく。他に1つでもあれば、勝手に切り替えない
        others = [w for w in wiki_names() if w != DEFAULT_FARM_FALLBACK]
        set_default = not others
        # 「Wiki設定を独立させる」は既定でチェックを入れる（Wiki設計者の指示、
        # 2026-09-15）。何を設定できるかが、そのWikiの config/default.yaml に
        # 最初から揃う。引き換えに、写した項目はその時点の値で固定され、あとで
        # 既定値（config/default.example.yaml）を直しても届かなくなる
        # （wikilib.wikiconfig.load_configのdocstring参照）。以前はこちらを
        # 避けて外していた。追従させたいWikiは、作るときにチェックを外せばよい。
        independent_config = True
        usage = USAGE_DEFAULT

    usage_rows = "".join(f"""
      <label class="newwiki-usage" for="nw-usage-{key}">
        <input id="nw-usage-{key}" type="radio" name="usage" value="{key}"{" checked" if key == usage else ""}>
        <span class="newwiki-usage-body">
          <strong class="newwiki-usage-title">{escape(item["title"])}</strong>
          <span class="newwiki-usage-label">{escape(item["label"])}</span>
          <span class="newwiki-usage-facts">
            <span><em>閲覧</em>{escape(item["read"])}</span>
            <span><em>編集</em>{escape(item["write"])}</span>
            <span><em>アカウント</em>{escape(item["signup"])}</span>
          </span>
        </span>
      </label>""" for key, item in USAGES.items())

    notice = ""
    if message:
        cls = "newwiki-notice" if ok else "newwiki-notice newwiki-notice-error"
        notice = f'<div class="{cls}" role="status">{escape(message)}</div>'

    body = f"""{notice}
<div class="newwiki">
  <p class="newwiki-lead"><code>wikidata/&lt;名前&gt;/</code> にフォルダ一式と、
    トップページ・メニューを用意します。</p>
  <form class="newwiki-form" method="post" action="{escape(action)}">
    <fieldset class="newwiki-set">
      <legend>名前</legend>
      <div class="newwiki-row">
        <label for="nw-name">Wikiの名前</label>
        <input id="nw-name" type="text" name="name" value="{escape(name)}"
               placeholder="例: sandbox" autocomplete="off" required>
      </div>
      <p class="newwiki-hint">半角英数字と <code>-</code> <code>_</code>（先頭は英数字）。
        <code>/=名前/</code> で開けます。</p>
      <div class="newwiki-row">
        <label for="nw-title">トップページの見出し</label>
        <input id="nw-title" type="text" name="title" value="{escape(title)}"
               placeholder="省略すると名前" autocomplete="off">
      </div>
    </fieldset>

    <fieldset class="newwiki-set">
      <legend>管理者（admin）のパスワード</legend>
      <div class="newwiki-row">
        <label for="nw-adminpw">パスワード</label>
        <input id="nw-adminpw" type="password" name="admin_pw"
               autocomplete="new-password" required>
      </div>
      <div class="newwiki-row">
        <label for="nw-adminpw2">もう一度</label>
        <input id="nw-adminpw2" type="password" name="admin_pw2"
               autocomplete="new-password" required>
      </div>
      <p class="newwiki-hint"><strong>空にはできません</strong>（誰でも管理者に入れる状態を避けるため）。
        忘れたら <code>./wiki.py resetpw</code> で入れ直せます。</p>
    </fieldset>

    <fieldset class="newwiki-set">
      <legend>使いかた</legend>
      <p class="newwiki-hint">誰が読めて誰が書けるかが決まります。あとから
        アクセス制限（<code>/.admin/privileges</code>）と設定画面の「アカウント」タブで変えられます。</p>
      <div class="newwiki-usages">{usage_rows}
      </div>
    </fieldset>

    <fieldset class="newwiki-set">
      <legend>設定</legend>
      <label class="newwiki-check" for="nw-independent">
        <input id="nw-independent" type="checkbox" name="independent_config"{" checked" if independent_config else ""}>
        <span>Wiki設定を独立させる
          <span class="newwiki-hint">共通の設定を写した <code>config/default.yaml</code> を用意します。
            写した値は作った時点のままで、あとで共通の既定値を直しても届きません。</span></span>
      </label>
      <label class="newwiki-check" for="nw-default">
        <input id="nw-default" type="checkbox" name="set_default"{" checked" if set_default else ""}>
        <span>既定のWikiにする
          <span class="newwiki-hint"><code>/</code> を開いたときに出るWikiにします。</span></span>
      </label>
    </fieldset>

    <div class="newwiki-actions">
      <button type="submit" class="newwiki-go">作る</button>
      <a class="newwiki-cancel" href="{escape(context.base_url)}/">やめる</a>
    </div>
  </form>
</div>"""
    return sysui.page(wiki_dir, config, farm, explicit_farm, NEWWIKI_URLPATH,
                      "新しいWikiを作る", body, css_url=f"{NEWWIKI_URLPATH}.css")


def serve_newwiki_asset(name):
    """この画面が自前で持つCSS（/.newwiki.css）。"""
    return serve_asset(NEWWIKI_DIR, "newwiki", name, kinds=("css",))
