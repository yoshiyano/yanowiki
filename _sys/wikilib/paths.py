"""パスとページの場所を決める土台。

このモジュールは標準ライブラリだけに依存する（依存パッケージの導入前でも読める）。
URL上のページパスと、実体のファイルの対応づけはすべてここに集約している。
"""
import hashlib
import os
import posixpath
import re

SYS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(SYS_DIR)
WIKIDATA_DIR = os.path.join(BASE_DIR, "wikidata")
PLUGIN_DIR = os.path.join(BASE_DIR, "plugin")
THEME_DIR = os.path.join(BASE_DIR, "theme")
PID_DIR = os.path.join(BASE_DIR, ".pid")  # 前回起動のPIDを覚えておく場所（Git管理対象外）
# 設定ファイルは役割で2つに分ける。
#   server.yaml  … サービスの起動に関わるもの（server / farm / debug）。
#                  Wikiごとに変えようがないので、全体で1つだけの実ファイル。
#   default.yaml … 個別Wikiの設定（page / markdown / theme）。
#                  実ファイルは無く、既定値は雛形（*.example.yaml）を直接
#                  読む。この定数は wikilib.wikiconfig.example_of() で
#                  対になる雛形のパスを作るためだけに使う（Wiki設計者の指示、
#                  2026-09-04。理由は wikilib.wikiconfig.load_config の
#                  docstring参照）。
SERVER_CONFIG_PATH = os.path.join(BASE_DIR, "config", "server.yaml")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "default.yaml")
# PukiWiki記法の「ユーザ定義ルール」「フェイスマーク定義ルール」（本家の
# default.ini.php の $line_rules / $facemark_rules に相当）。管理者が自由に
# 書ける定義なので、他の設定（server/default）と分けて別ファイルにしてある。
# default.yamlと同じく実ファイルは無く、雛形を既定値として直接読む。
EXTRARULES_CONFIG_PATH = os.path.join(BASE_DIR, "config", "pukiwiki.extrarules.yaml")
# InterWikiの登録表（本家はInterWikiNameという専用ページに書くが、こちらは
# 他の管理者向け定義と同じく設定ファイルにしてある）。これも実ファイルは無い。
INTERWIKI_CONFIG_PATH = os.path.join(BASE_DIR, "config", "pukiwiki.interwiki.yaml")
DEFAULT_FARM_FALLBACK = "_system"
FARM_PREFIX = "="  # URLでfarmを明示的に指定するためのプレフィックス（例: /=system/）
SYSTEM_PREFIX = "."  # システム資材のURLプレフィックス（例: /.theme/base.css）
THEME_URLPATH = SYSTEM_PREFIX + "theme"  # テーマ資材（CSS/JS等）のURL名前空間
SEARCH_URLPATH = SYSTEM_PREFIX + "search"  # 検索のURL（例: /.search?q=...）
# 旧URL（例: /.editwikipage/UsageGuide）。編集画面はいまこのパスを持たず、
# そのページ自身の通常URLへPOST + cmd=edit を送ることで開く
# （wiki.pyのdispatch参照）。編集の入口の存在を閲覧者に教えてしまうため。
# ここへのアクセスはメソッドを問わず、この名前を除いた通常URLへ303で
# 送り返すだけの後方互換用に残している。
#
# 名前は2026-09-06に '.edit' から '.editwikipage' へ変えた（Wiki設計者の指示）。
# **'.edit' で来ていた古いリンクは、もう送り返さない**（ただの無いページに
# なる）。編集画面そのものはこのパスを使っていないので、画面から辿る
# ぶんには影響しない。
EDIT_URLPATH = SYSTEM_PREFIX + "editwikipage"
ATTACH_URLPATH = SYSTEM_PREFIX + "attach"  # 添付ファイルのURL（例: /.attach/index/logo.png）
SECTION_URLPATH = SYSTEM_PREFIX + "section"  # セクション単位の生テキスト取得（例: /.section/UsageGuide?heading=...&scope=...）
# プレビュー（`?cmd=preview`）と差分（`?cmd=diff`）は、ページ自身の通常URLへ
# POSTする形に寄せた（Wiki設計者の指示、2026-09-17）。以前の `.preview`・`.diff`
# という専用URLは廃止。本文をそのまま本体に載せて送るのでフォームとしては読めず、
# `cmd` はクエリで受ける（`wiki.py` の dispatch 参照）
PLUGIN_URLPATH = SYSTEM_PREFIX + "plugin"  # プラグインの_action呼び出し（例: /.plugin/vote）
PAGETREE_URLPATH = SYSTEM_PREFIX + "pagetree"  # ページ一覧のツリー（JSON、ページ選択ダイアログ用）
# 編集画面の「履歴」タブが自前で持つCSS/JS（/.history.css・/.history.js）。**資材だけ**で、
# 履歴そのものはページ自身のURLへのPOST（?cmd=history）で読み書きする（wikilib.backupui）
HISTORY_URLPATH = SYSTEM_PREFIX + "history"
RESTART_URLPATH = SYSTEM_PREFIX + "restart"  # サービスの再起動（/.restart）
NEWWIKI_URLPATH = SYSTEM_PREFIX + "newwiki"  # 新しいWikiを作る（/.newwiki、資材は /.newwiki.css）
DELWIKI_URLPATH = SYSTEM_PREFIX + "delwiki"  # 既にあるWikiを消す（/.delwiki、資材は /.delwiki.css）
# ファイル一覧（/.files/。webFileDir を組み込んだ画面。wikilib.filesui）
FILES_URLPATH = SYSTEM_PREFIX + "files"
# テーマ選択の受け口（/.themeselect へPOST）。閲覧者が画面上でテーマを選び、
# 選んだ結果をcookieに覚えさせるためのもの（wikilib.themes 参照）。
THEMESELECT_URLPATH = SYSTEM_PREFIX + "themeselect"
# 選んだテーマを覚えておくcookieの土台の名前。**実際に置く名前は
# wiki_cookie_name() でWikiごとに分ける**（Pathだけでは分けきれない。
# 同関数のdocstring参照）。
THEME_COOKIE = "wikitheme"
THEME_COOKIE_MAX_AGE = 24 * 60 * 60  # 1日（Wiki設計者の指示、2026-09-04）
CONFLICT_URLPATH = SYSTEM_PREFIX + "conflict"  # 編集の競合を統合する画面（/.conflict/<ページパス>、資材は /.conflict.css など）
# 管理の道具をまとめた窓口（/.admin）。**管理者と助手が開ける**
# （Wiki設計者の指示、2026-09-08）。**これから作る管理の道具は、この下に
# サブコマンドとしてつなぐ**（同）。
#
#     /.admin              窓口（道具の一覧）
#     /.admin/accounts     アカウント一覧・編集。**管理者だけ**
#     /.admin/configwiki   Wikiの設定。管理者と助手
#
# /.accounts・/.configwiki は当初 SYSTEM_PREFIX 直下に置いていたが、この窓口の
# 下へ移した（Wiki設計者の指示、2026-09-12）。旧URLは残さない（そのまま404になる）。
# **助手グループの出し入れ（旧 /.admin/staff）は /.groups?group=staff に
# 一本化した**（Wiki設計者の指示、2026-09-12。GROUPS_URLPATH参照）。
ADMIN_URLPATH = SYSTEM_PREFIX + "admin"
# 利用者アカウント（wikilib.userdb / wikilib.accounts）。ページごとの認証を
# 入れるための土台で、いまはアカウントの登録と、その照合だけを受け持つ。
# ログイン・ログアウト・アカウント作成は #login プラグインの _action
# （/.plugin/login）が受け持つ。**ログインの入口は `/.login`**（LOGIN_URLPATH）。
# 2026-09-11にいちど「専用の画面は持たない」としたが、2026-09-21に持つ形へ戻した。
ACCOUNTS_URLPATH = ADMIN_URLPATH + "/accounts" # アカウント一覧・編集（/.admin/accounts、資材は /.admin/accounts.css）
PWHASH_URLPATH = SYSTEM_PREFIX + "pwhash"     # パスワードからハッシュ値を作る道具（/.pwhash）
PASSWD_URLPATH = SYSTEM_PREFIX + "passwd"     # 自分のパスワードを変える（/.passwd）
# `#readauth`・`#writeauth` の記録のうち、もう機能していない行を消す。**誰でも**実行できる
# （1時間に10回まで。管理者と助手は除く）。wikilib.updatepageauth
UPDATEPAGEAUTH_URLPATH = SYSTEM_PREFIX + "updatePageAuth"
# 助手の操作の記録を確かめ、元に戻す画面。**管理者だけ**。wikilib.stafflogui
STAFFLOG_URLPATH = ADMIN_URLPATH + "/stafflog"
# 削除したページ（持ち主のページが無い）の添付を、ページ trashbox へ集める。
# **管理者と助手**。GETで確認、POSTで実行。wikilib.garbagecollect
GARBAGECOLLECT_URLPATH = SYSTEM_PREFIX + "garbagecollect"
# Wikiの設定（wikidata/<Wiki名>/config/default.yaml）を書き換える画面。
# **管理者と助手**（Wiki設計者の指示、2026-09-06）。資材は /.admin/configwiki.css
CONFIGWIKI_URLPATH = ADMIN_URLPATH + "/configwiki"
# ユーザーが自分で作れる汎用グループの管理画面。**ログインしていれば誰でも
# 開ける**（Wiki設計者の指示、2026-09-12）。助手グループ（staff）の管理も
# ここに統合されている（`wikilib.groups`参照）。資材は /.groups.css・/.groups.js
# 承認待ちのアカウントを承認する・断る画面（/.admin/approvals。管理者と助手）。
# `account.policy` が `approval` のWikiで、「アカウント作成」で申請されたもの
# （`wikilib.approvalsui`）。
APPROVALS_URLPATH = ADMIN_URLPATH + "/approvals"
GROUPS_URLPATH = SYSTEM_PREFIX + "groups"

# ページごとのアクセス制限を編集する画面（/.admin/privileges）。**管理の道具**
# なので /.admin の配下（Wiki設計者の指示、2026-09-13）。記録そのものは
# farm_privileges_path（config/privileges）。
PRIVILEGES_URLPATH = ADMIN_URLPATH + "/privileges"
# ログインできた相手のID（uid）を覚えておくcookieの土台の名前
# （Wiki設計者の指示、2026-09-06）。**これ単体は本人であることの証しに
# ならない**（値は手で書き換えられる）。下の LOGIN_AUTH_COOKIE と揃って
# はじめて意味を持つ。wikilib.auth の冒頭。
# **実際に置く名前は wiki_cookie_name() でWikiごとに分ける。**
LOGIN_COOKIE = "wikiuser"
# ログイン状態が本物かを確かめるための控え（Wiki設計者の指示、2026-09-06）。
# 中身は wikilib.userdb.session_token が作る値で、**1日ごとに変わる**。
LOGIN_AUTH_COOKIE = "wikiauth"
# ブラウザに持たせる長さは**2日**。合言葉が通るのは今日ぶんと昨日ぶんなので、
# そこまでは持っていてもらう必要がある（1日で消すと、25時間ぶりに開いた人が
# 「昨日のぶんで通る」はずなのに、cookie自体を失って入れ直しになる）。
LOGIN_COOKIE_MAX_AGE = 2 * 24 * 60 * 60


# cookieの名前に使える文字（RFC 6265 の token）のうち、Wiki名として現れうる
# ものだけを見る。新しく作るWiki名は英数字と `-` `_` に限ってある
# （wikilib.newwiki.WIKI_NAME_RE）が、wikidata/ に手で置いたディレクトリも
# Wikiになるため、外れた名前も受け取れるようにしてある（下を参照）。
_COOKIE_SAFE_WIKINAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def wiki_cookie_name(base, wikiname):
    """そのWiki専用のcookieの名前（`wikiuser_1ev-c` の形）。

    **Pathで分けるだけでは足りない**（Wiki設計者からの不具合報告、2026-09-18）。
    既定のWiki（`farm.default`）はURLに `=Wiki名` が付かないため、その
    cookieのPathは `/` になり、**どのWikiのURLにも一緒に送られる**。名前が
    全Wiki共通だと、ブラウザは

        Cookie: wikiauth=<1ev-c のぶん>; wikiauth=<既定Wikiのぶん>

    のように同じ名前を2つ並べて送る（RFC 6265 はPathの長いほうを先に置くと
    定めている）。これを受ける側（bottle → http.cookies.SimpleCookie）は
    **同じ名前なら後に来たほうで上書きする**ので、いま見ているWikiのぶんが
    捨てられ、既定Wikiのぶんだけが残る。合言葉にはWiki名が混ぜてあるから
    照合は失敗し、ログインしたはずなのに来訪者として扱われていた。

    名前そのものを分ければ、いくつ並んで送られても取り違えない。Pathでの
    分離はそのまま残す（隣のWikiへ持ち出させない、という別の目的があり、
    こちらはこちらで意味がある）。

    `wikiname` にcookieの名前として使えない文字が混じるとき（`wikidata/` に
    手で置いたディレクトリなど）は、名前の代わりにその短い要約を使う。
    **名前が壊れて隣のWikiと同じになるより、読めないが衝突しないほうが安全**
    なため。"""
    if not _COOKIE_SAFE_WIKINAME_RE.match(wikiname or ""):
        digest = hashlib.sha1((wikiname or "").encode("utf-8")).hexdigest()
        wikiname = "x" + digest[:12]
    return base + "_" + wikiname
# 認証の合言葉に混ぜる、この設置に固有の文字列。**画面には出さない。**
# 無ければ最初に要るときに作る（wikilib.userdb.site_secret）。
SECRET_PATH = os.path.join(BASE_DIR, "config", "secret.txt")
SECRET_LENGTH = 10  # Wiki設計者の指示、2026-09-06
# 全Wikiの一覧を出すページ。URL名は server.yaml の farm.allwiki で決まり、
# ここにあるのはその既定値（/.allwiki）。空にすると一覧を出さない。
# **開けるのは既定Wikiの管理者と助手だけ**で、/=<Wiki名>/.allwiki は403
# （Wiki設計者の指示、2026-09-16。/.newwiki・/.restart と同じ関門を通す）
ALLWIKI_COMMAND = "allwiki"
# URL名として受け付ける形。振り分けに使う値なので、"/" などが入らないよう関門を置く
ALLWIKI_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
PLUGIN_MAX_DEPTH = 5  # プラグイン出力の再展開をこの深さで打ち切る（相互再帰の暴走を防ぐ）

# 注釈（脚注）にマウスを乗せたときに出す中身の長さ。これを超えたら途中で切る。
# 注釈はページ末尾にまとまるので、読んでいる位置から中身を確かめられるように
# するための添え物（Wiki設計者の指示、2026-09-03）。長い注釈まで全部出すと、
# ブラウザの吹き出しが画面を覆ってしまうため上限を設ける。
FOOTNOTE_TIP_MAX = 80

# プラグインが PLUGIN_INFO で宣言できる項目と、宣言しなかった場合の既定値。
# 既定はすべて「安全側」＝出力をそのまま使い、再展開もしない。
PLUGIN_DEFAULT_INFO = {
    "help": "",             # エラー時に表示する簡易ヘルプ
    "need_outer_info": False, # 引数・中身だけでは完結せず外部情報が要るか（部分プレビューでは処理しない）
    "dynamic_output": False,  # 同じ引数・中身でも出力が時間とともに変わりうるか（予約項目。まだ未使用）
    "expand_plugin": False, # 出力に含まれるプラグイン記法を展開するか
    "expand_block": False,  # 出力をブロック要素（段落・リスト等）として展開するか
    "expand_inline": False, # 出力をインライン要素（強調・リンク等）として展開するか
    "args": (),             # 引数の宣言（wikilib.plugins.bind_plugin_args）。省略＝引数を受け取らない
    # 中身（body）を展開するときに、生HTMLをどこまで通すか。
    # None＝そのページの設定（allow_html）に従う。False/True/"all" を書くと、
    # **設定に関わらず**その水準で解釈する（wikilib.htmlpolicy。
    # Wiki設計者の指示、2026-09-02）。expand_* を宣言していなければ意味を持たない
    "body_html": None,
}

_force_debug = False  # --debug 起動時に立つ。config の debug と OR で判定する

EDITOR_URLPATH = SYSTEM_PREFIX + "editor"  # 編集機能自身のCSS/JS（/.editor.css, /.editor.js）
EDITOR_DIR = os.path.join(BASE_DIR, "_sys", "editor")  # その実体の置き場所
BACKUPUI_DIR = os.path.join(BASE_DIR, "_sys", "backupui")  # バックアップ管理画面のCSS/JS
# 第三者ライブラリ（バンドラ不要のもの）をそのまま置く場所（例: /.vendor/diffmerge/…）。
# 詳しくは _sys/vendor/README.txt 参照
VENDOR_URLPATH = SYSTEM_PREFIX + "vendor"
VENDOR_DIR = os.path.join(BASE_DIR, "_sys", "vendor")
# webFileDir（ファイル一覧の部品）の置き場所。wikiSystem に同梱している（_sys/webfiledir。
# 由来と更新の手順は同じ場所の WIKISYSTEM.txt）。開発中の webFileDir で試すときは
# 環境変数 WIKI_WEBFILEDIR_DIR で差し替えられる（wikilib.filesui）
WEBFILEDIR_DIR = os.environ.get(
    "WIKI_WEBFILEDIR_DIR", os.path.join(BASE_DIR, "_sys", "webfiledir"))
SEARCH_DIR = os.path.join(BASE_DIR, "_sys", "search")  # 検索結果のCSS/JS（/.search.css, /.search.js）
CONFLICT_DIR = os.path.join(BASE_DIR, "_sys", "conflict")  # 競合を統合する画面のCSS/JS（/.conflict.css, /.conflict.js）
TREEVIEW_URLPATH = SYSTEM_PREFIX + "treeview"  # ページ一覧のTreeView（/.treeview.css/.js）
TREEVIEW_DIR = os.path.join(BASE_DIR, "_sys", "treeview")  # その実体の置き場所
ALLWIKI_DIR = os.path.join(BASE_DIR, "_sys", "allwiki")  # Wiki一覧のCSS（/.allwiki.css）
DELWIKI_DIR = os.path.join(BASE_DIR, "_sys", "delwiki")  # Wikiを消す画面のCSS（/.delwiki.css）
NEWWIKI_DIR = os.path.join(BASE_DIR, "_sys", "newwiki")  # Wikiを作る画面のCSS（/.newwiki.css）
# アカウントまわり3画面（ログイン・一覧・ハッシュ生成）で共有するCSS（/.admin/accounts.css）。
# テーマ（theme/）は別プロジェクトの持ち物なので、自前で持って触らずに済ませる
ACCOUNTS_DIR = os.path.join(BASE_DIR, "_sys", "accounts")
CONFIGUI_DIR = os.path.join(BASE_DIR, "_sys", "configui")  # 設定画面のCSS
GROUPS_DIR = os.path.join(BASE_DIR, "_sys", "groups")  # グループ管理画面のCSS/JS
PRIVILEGES_DIR = os.path.join(BASE_DIR, "_sys", "privilegesui")  # アクセス制限の画面のCSS/JS
# マーカーシステム（複数の用語を色分けして追跡する仕組み）。
# 本体（markers.js/css）は全ページに自動で差し込む（wikilib.themes.render_theme）ため
# テーマ側の変更は要らない。操作用の別ウィンドウ（panel）は独立したURL名前空間に分ける
MARKERS_URLPATH = SYSTEM_PREFIX + "markers"  # 全ページに差し込む本体（/.markers.js, /.markers.css）
MARKERS_DIR = os.path.join(BASE_DIR, "_sys", "markers")  # その実体の置き場所
MARKERS_PANEL_URLPATH = SYSTEM_PREFIX + "markers-panel"  # 操作用の別ウィンドウ（/.markers-panel）
# ページに付随する記録（backup/ と draft/）をまとめる親フォルダの名前。
# 詳しくは farm_pageinfo_dir() を参照。
PAGEINFO_DIR = "pageinfo"
LOG_DIR = "log"  # アクセスログ（access.log.db）の置き場所。詳しくは farm_log_dir() を参照
# バックアップ（差分ファイル）に使ってよい上限の大きさ。**各Wikiごと**に
# 効く（wikidata/<Wiki名>/pageinfo/backup/ 単位。全Wikiの合計ではない）。
# 超えたら、そのWikiの中でページをまたいで古い保存から順に消す
# （backup.prune_by_total_size）。
#
# **世代数ではなく大きさで区切る**（Wiki設計者の指示、2026-08-31）。以前は
# 1ページ20世代までとしていたが、世代数だと1回の変更量が大小さまざまなため、
# 「どれだけ残せるか」も「どれだけ場所を使うか」も見当がつかなかった。
# 参考: 2026-08-31時点の_systemは104ページ・493本で1.5MB
# （1差分あたり平均3.1KB）。50MBはその30倍以上あり、ふだんの利用で
# 上限に触れることはまず無い。暴走時の歯止めとして働く。
BACKUP_TOTAL_BYTES = 50 * 1024 * 1024
# 上限に達したときに、どこまで減らしにいくか（Wiki設計者の指示、2026-09-01）。
# ぎりぎりまでしか減らさないと、保存のたびに掃除が走り、そのたびに
# いちばん古い記録が1件ずつ削られていく。半分まで空けておけば、
# 掃除はたまにしか起きない。
BACKUP_PRUNE_TARGET = 0.5
# 記録がこの数に満たないページは、掃除の対象にしない（Wiki設計者の指示、2026-09-01）。
# 上限に触れる原因は、たいてい保存の多い一部のページ。履歴の浅いページまで
# 巻き添えにすると、めったに更新しないページの数少ない記録が先に消えてしまう。
# 「20未満は対象にしない」ので、20件のページから1件消すと19件になり、
# そこで対象から外れる（＝どのページにも19件は残る）。
BACKUP_MIN_KEEP = 20
BACKUP_MERGE_SECONDS = 10 * 60  # この時間内の連続した保存は、直前の差分に統合する
BACKUP_STAMP = "%y%m%d_%H%M%S"  # 差分ファイル名に使う日時の書式

# ---- マークアップ書式の定義 -------------------------------------------------
# 編集画面のツールバーは、この定義だけを見て組み立てられる（JavaScript側に個々の
# 記法を書かない）。記法を足すときは、ここに同じ形の定義を足せば、同じツールバーが
# そのまま新しい記法用として働く。
#
# 各アクションの指定方法（いずれか1つ）:
#   wrap      … 選択範囲の前後を囲む [開始, 終了]
#   prefix    … 選択した各行の先頭に付ける（line=True で行単位）
#   block     … 選択範囲を独立した行として前後で囲む [開始, 終了]
#   template  … 定型文を挿入する（${text} が選択文字列に置き換わる）
#   palette   … 文字色・背景色のポップオーバーを開く。1つのポップオーバーで
#               fg/bgを両方選べ、「適用」で1回だけ &color(fg,bg){選択}; を
#               挿入する（位置引数。片方だけ選んだ場合は片方だけ渡す）。
#               色の一覧は render_edit が config の edit.custom_colors を
#               BASE_COLOR_NAMES に足して "base_colors"/"custom_colors" として
#               差し込む（このファイルには書かない）
#   size_percents … サイズのポップオーバーを開き、選んだ増減％（例: +10）から
#               100を足した割合で &size(割合%){選択}; を挿入する
#               （プリセットの増減％の並び。&size() 自体が割合(%)指定を
#               受け付ける。任意入力は無く、プリセットのみ）

# palette アクションの「基本の色」16色（CSS標準の色名）。wikiごとに変わらない
# 固定値なので、editor.py 側の custom_colors（config由来）とは別に持つ
BASE_COLOR_NAMES = [
    "black", "gray", "silver", "white",
    "maroon", "red", "olive", "yellow",
    "green", "lime", "teal", "aqua",
    "navy", "blue", "purple", "fuchsia",
]

# config の edit.custom_colors を書き忘れた・壊れている場合のフォールバック
# （config/default.example.yaml に書いた既定値と揃えてある）
DEFAULT_CUSTOM_COLORS = [
    "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71",
    "#1abc9c", "#3498db", "#9b59b6", "#34495e",
    "#c0392b", "#d35400", "#f39c12", "#27ae60",
    "#16a085", "#2980b9", "#8e44ad", "#7f8c8d",
]

MARKUP_FORMATS = {
    "pukiwiki": {
        "label": "PukiWiki記法",
        "ext": ".txt",
        "actions": [
            {"name": "heading", "label": "見出し", "icon": "H", "prefix": "* ", "line": True},
            {"name": "bold", "label": "強調", "icon": "B", "wrap": ["''", "''"], "sample": "強調"},
            {"name": "italic", "label": "斜体", "icon": "I", "wrap": ["'''", "'''"], "sample": "斜体"},
            {"name": "strike", "label": "取消線", "icon": "S", "wrap": ["%%", "%%"], "sample": "取消線"},
            {"name": "link", "label": "リンク", "icon": "🔗", "template": "[[${text}>/ページ名]]", "sample": "リンク"},
            {"name": "list", "label": "箇条書き", "icon": "•", "prefix": "- ", "line": True},
            {"name": "numlist", "label": "番号つき", "icon": "1.", "prefix": "+ ", "line": True},
            {"name": "quote", "label": "引用", "icon": "❝", "prefix": "> ", "line": True},
            {"name": "pre", "label": "整形済み", "icon": "⌗", "prefix": " ", "line": True},
            {"name": "table", "label": "表", "icon": "▦",
             "template": "|~見出し1|~見出し2|h\n|${text}||"},
            {"name": "deflist", "label": "定義リスト", "icon": "：",
             "template": ":${text}|説明\n"},
            {"name": "annotation", "label": "注釈", "icon": "†",
             "wrap": ["((", "))"], "sample": "注釈"},
            {"name": "color", "label": "文字色・背景色", "icon": "A", "palette": True, "sample": "文字"},
            {"name": "fontsize", "label": "文字サイズ", "icon": "⇕",
             "size_percents": [-10, -5, 5, 10, 15], "sample": "サイズ"},
            {"name": "br", "label": "改行", "icon": "↵", "template": "~\n"},
            {"name": "hr", "label": "区切り線", "icon": "―", "template": "\n----\n"},
        ],
    },
    "markdown": {
        "label": "Markdown",
        "ext": ".md",
        "actions": [
            {"name": "heading", "label": "見出し", "icon": "H", "prefix": "## ", "line": True},
            {"name": "bold", "label": "太字", "icon": "B", "wrap": ["**", "**"], "sample": "太字"},
            {"name": "italic", "label": "斜体", "icon": "I", "wrap": ["*", "*"], "sample": "斜体"},
            {"name": "strike", "label": "打ち消し", "icon": "S", "wrap": ["~~", "~~"], "sample": "打ち消し"},
            {"name": "code", "label": "コード", "icon": "‹›", "wrap": ["`", "`"], "sample": "コード"},
            {"name": "link", "label": "リンク", "icon": "🔗", "template": "[${text}](/ページ名)", "sample": "リンク"},
            {"name": "image", "label": "画像", "icon": "🖼", "template": "![${text}](ファイル名.png)", "sample": "説明"},
            {"name": "list", "label": "箇条書き", "icon": "•", "prefix": "- ", "line": True},
            {"name": "numlist", "label": "番号つき", "icon": "1.", "prefix": "1. ", "line": True},
            {"name": "quote", "label": "引用", "icon": "❝", "prefix": "> ", "line": True},
            {"name": "codeblock", "label": "コードブロック", "icon": "⌗", "block": ["```", "```"]},
            {"name": "table", "label": "表", "icon": "▦",
             "template": "| 見出し1 | 見出し2 |\n|---|---|\n| ${text} | |"},
            {"name": "hr", "label": "区切り線", "icon": "―", "template": "\n---\n"},
        ],
    },
    # 記法を持たない素のテキスト。拡張子を持たないので、どのページの書式にもならない
    # （未知の拡張子だったときの受け皿として使う）。
    "plain": {
        "label": "プレーンテキスト",
        "ext": None,
        "actions": [],
    },
}


DEFAULT_MARKUP = "pukiwiki"  # 新規ページを作るときの書式（編集画面で選び直せる）
# Wikiごとに設定で変えられる（`edit.defaultwiki`。wikiconfig.default_markup）。
# 設定を読むのは wikiconfig の役目で、こちら（paths）はconfigを知らない
# ——wikiconfig が paths を読み込んでいるので、逆向きには参照できないため。
# そのため「どの記法か」は**呼び出し側が決めて渡す**形にしてある。
# ページとして扱う拡張子。閲覧時はこの順に探す（.txt が優先）
PAGE_EXTS = (".txt", ".md")
# フォルダの入口になるページの名前。`/Tech` が実体 `Tech/index` を指す約束。
# **`X.txt` と フォルダ `X/` は同居できない**（resolve_page_ref はフォルダが
# あれば必ずその中の index を読むので、残した `X.txt` は読めなくなる。
# pagedb.shadowed_pages が拾うのがその状態）。そのため入口かどうかの判定と、
# ページパスと実体パスの行き来は、下の3つ（is_folder_entry /
# pagepath_of_subpath / entry_subpath_of）に集めてある。
# 実体そのものを `X` と `X/index` の間で移す操作は wikilib.pagemove の担当。
INDEX_NAME = "index"
# ログインの入口（`/.login`。ナビの「ログイン」リンクが指す先）。**システムのURLなので、
# ページ名と衝突せず、ページごとの権限（`config/privileges`）の対象にもならない**
# （Wiki設計者の指示、2026-09-21）。閲覧にもログインを求めるWikiでも、ここは開く。
# 中身は `#login()` と同じフォーム（`wikilib.views.render_login`）。
# 以前は `Login` という名前のページを入口にしていた（2026-09-18〜2026-09-21）が、
# その名前でページを作ると権限で読めなくなる・実在のページが入口の役を奪う、という
# 問題があったので、システムのURLへ移した。`Login` は、いまはふつうのページ名。
LOGIN_URLPATH = SYSTEM_PREFIX + "login"
# 拡張子に見える末尾（"." のあとに英数字1〜6文字）。**ページ名には付けられない**
# 決まりにしてあり、これが付いていればリンク先は添付ファイルとみなす
# （resolve_link）。ページか添付かを名前の形だけで見分けるための線引きで、
# ファイルがあるかどうかは見ない。
PAGE_NAME_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,6}$")
# 画像として扱う拡張子（小文字で比較する）。添付一覧のサムネイル判定
# （wikilib.attach.ATTACH_IMAGE_EXTS）と、PukiWiki記法のリンクが画像を
# 指しているときの自動プレビュー（wikilib.pukiwiki.link_tokens）の両方が
# ここを参照する。標準ライブラリだけに依存するこのモジュールに置き、
# どちらからも依存の向きが崩れないようにしている。
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp", ".ico")


def markup_name_for(ext):
    """拡張子から書式の名前を返す。未知の拡張子は素のテキスト扱い。"""
    for name, fmt in MARKUP_FORMATS.items():
        if fmt["ext"] == ext:
            return name
    return "plain"


def markup_format_for(ext):
    """拡張子から書式定義を選ぶ。未知の拡張子は素のテキスト扱い。"""
    return MARKUP_FORMATS[markup_name_for(ext)]


def selectable_markups():
    """編集画面で選べる書式を [(名前, 定義), ...] で返す。

    拡張子を持つものだけが対象（"plain" は受け皿であって、選んで書くものではない）。
    並びはこの定義の順がそのまま画面の並びになる。"""
    return [(name, fmt) for name, fmt in MARKUP_FORMATS.items() if fmt["ext"]]


def markup_ext_or(name, default_ext):
    """書式の名前からその拡張子を返す。選べない名前だったときは default_ext。

    画面から送られてくる書式名を受けるための関門。ここを通さずに拡張子を
    決めると、知らない名前でファイルを作ってしまう。"""
    fmt = MARKUP_FORMATS.get(name or "")
    if fmt and fmt["ext"]:
        return fmt["ext"]
    return default_ext
DEFAULT_THEMEFILE = "base"  # 既定のテーマ名（theme/base.html を参照する）
THEME_COMMON_PREFIX = "common"  # 個別Wiki固有テーマから全Wiki共通テーマを継承するための名前空間
SEARCH_TEMPLATE = "search.html"  # 検索結果ページのテンプレート
SEARCH_SNIPPET_LEN = 140  # 検索結果に表示する抜粋の長さ

# ---- 境界の外に出さないパス結合 ---------------------------------------------
#
# 設定ファイルの値・URLの断片・アップロードされた名前など、外部由来の文字列を
# ディレクトリ結合に使う箇所は、素の os.path.join を直接使わずここを通す。
# 同じ考えかたの「realpathを取り、prefixで比較する」チェックが
# attach.py・vendor.py・（このファイルの）farm_wiki_dir に、微妙に書きかたを
# 変えつつ重複していた。1箇所にまとめ、書き漏れ・書き間違いの余地を減らす
# （Wiki設計者の指示、2026-09-04。theme.name（当時の名前はtheme.default）を
# パス結合に素通ししていた穴が見つかったのを機に、chrootのように最上位
# パスの外へ出さない共通の関数を用意することになった）。


def safe_join(base_dir, *parts):
    """base_dirを最上位（chrootの最上位に相当）として、partsを結合した
    絶対パスを返す。結合結果がbase_dirの外に出る場合はNoneを返す。

    シンボリックリンクの先までは追いかけない（os.path.realpathではなく
    os.path.normpathで正規化するだけ）。base_dir自身や結合の途中に
    シンボリックリンクがあり、その実体が境界の外にあるようなケースは
    この関数の対象外——**シンボリックリンクは運用者がファイルシステムに
    自分で置くものであり、外部からの入力では作れない**ため、この関数が
    防ぐ対象（外部由来の文字列によるパス逸脱）とは性質が異なる
    （Wiki設計者の指示により、その先までは追わない設計にした）。"""
    base = os.path.normpath(os.path.abspath(base_dir))
    target = os.path.normpath(os.path.abspath(os.path.join(base_dir, *parts)))
    if target == base or target.startswith(base + os.sep):
        return target
    return None


# ---- ページの場所を決める -------------------------------------------------

def farm_wiki_dir(farm):
    """Wiki名からwikidata/<Wiki名>/wiki/の絶対パスを返す。
    不正なWiki名、または該当するWikiが存在しない場合はNone。"""
    if not farm or farm in (".", "..") or "/" in farm or "\\" in farm:
        return None
    d = safe_join(WIKIDATA_DIR, farm, "wiki")
    if d is None or not os.path.isdir(d):
        return None
    return d


def farm_plugin_dir(wiki_dir):
    return os.path.join(os.path.dirname(wiki_dir), "plugin")


def farm_config_path(wiki_dir):
    """個別Wikiの設定ファイル（wikidata/<Wiki名>/config/default.yaml）の場所。"""
    return os.path.join(os.path.dirname(wiki_dir), "config", "default.yaml")


def farm_extrarules_config_path(wiki_dir):
    """個別Wikiの置換ルール定義（wikidata/<Wiki名>/config/pukiwiki.extrarules.yaml）の場所。"""
    return os.path.join(os.path.dirname(wiki_dir), "config", "pukiwiki.extrarules.yaml")


def farm_interwiki_config_path(wiki_dir):
    """個別WikiのInterWiki登録表（wikidata/<Wiki名>/config/pukiwiki.interwiki.yaml）の場所。"""
    return os.path.join(os.path.dirname(wiki_dir), "config", "pukiwiki.interwiki.yaml")


def farm_privileges_path(wiki_dir):
    """ページごとのアクセス制限（wikidata/<Wiki名>/config/privileges）の場所。

    アカウント（`users.db`）と同じ `config/` に置く。**Wikiごとに別**で、
    中身は `wikilib.privilege_records` が見る。手で書いた分と、プラグインが描画の
    中で書き出す分（`privileges.plugin`）を分けて持つ
    （[ページごとの権限](/Tech/PagePermissions)）。"""
    return os.path.join(os.path.dirname(wiki_dir), "config", "privileges")


def farm_users_db_path(wiki_dir):
    """個別Wikiの利用者アカウント（wikidata/<Wiki名>/config/users.db）の場所。

    設定と同じ `config/` に置く（Wiki設計者の指示、2026-09-05）。**Wikiごとに別**で、
    全Wiki共通のアカウントは持たない——farmは「別のWiki」なので、誰が書けるかも
    Wikiごとに決められるほうが素直なため。中身は `wikilib.userdb` が見る。"""
    return os.path.join(os.path.dirname(wiki_dir), "config", "users.db")


def farm_pageinfo_dir(wiki_dir, *names):
    """ページに付随する記録の置き場所（wikidata/<Wiki名>/pageinfo/…）。

    backup（保存時の差分）と draft（編集中の書きかけ）が入る。どちらも
    「ページそのものではないが、ページ1枚ごとに紐づく記録」で、置き場所も
    Git管理の扱い（実ファイルは対象外）も同じなので、1つの親にまとめている。
    Wikiの直下に並ぶフォルダは、利用者が中身を書き換えるもの（wiki/ attach/
    plugin/ theme/ config/）だけになる。"""
    return os.path.join(os.path.dirname(wiki_dir), PAGEINFO_DIR, *names)


def farm_auth_log_path(wiki_dir):
    """認証の履歴の置き場所（wikidata/<Wiki名>/log/auth.log.db）。

    アカウントの記録（config/users.db）とは別のDBにしてある。あちらは
    **いまの状態**、こちらは**起きたことの積み上げ**で、消してよい条件も
    増えかたも違うため。log/ に置く理由は farm_log_dir() を参照。"""
    return farm_log_dir(wiki_dir, "auth.log.db")


def farm_admin_log_path(wiki_dir):
    """管理操作の履歴の置き場所（wikidata/<Wiki名>/log/admin.log.db）。

    誰が（管理者・助手のuid）・どのアカウントに対して・何を（update/delete）
    行ったかを積み上げる記録（Wiki設計者の指示、2026-09-12。
    `/.admin/accounts` の一覧操作をAPI化した際に追加）。**照合の成否を
    残す認証の履歴（auth.log.db）とは別物**なので、ファイルも分ける。"""
    return farm_log_dir(wiki_dir, "admin.log.db")


def farm_log_dir(wiki_dir, *names):
    """アクセスログの置き場所（wikidata/<Wiki名>/log/…）。

    pageinfo/ と分けているのは、Git管理の扱いが違うため。pageinfo/ は
    「システムを通さない書き換え」を検出するための実行時の記録で、消えても
    平文ファイルから作り直せる。log/ は個人情報・運用情報そのもの（アクセス元・
    端末種別）を含み、作り直せる元が無い。誤って同じ場所に置いて一括で
    掃除される事故を避けるため、最初から別フォルダにしてある。"""
    return os.path.join(os.path.dirname(wiki_dir), LOG_DIR, *names)


def resolve_page(target):
    """target: 拡張子なしのページパス（絶対パス）。
    見つかれば (実ファイルパス, 拡張子, 内容) を返し、なければ None を返す。"""
    for ext in PAGE_EXTS:
        candidate = target + ext
        if os.path.isfile(candidate):
            with open(candidate, encoding="utf-8") as f:
                return candidate, ext, f.read()
    return None

class PageRef:
    """URLのページパスが指す「対象ページ」。

    ページが実在するかどうかに関わらず、次が決まっている:
      pagepath … URL上のページパス（"" ならそのWikiのトップ）
      subpath  … 実体のwiki_dir相対パス（拡張子抜き、index解決済み）
      ext      … 拡張子。実在すればそのファイルのもの、無ければ既定の書式
      path     … 実ファイルの絶対パス（実在しない場合は「保存するならここ」）
      body     … 内容（実在しなければ空文字列）
      exists   … 実在するか
      privilege … いまの閲覧者のアクセス権（`auth.PAGE_WRITE`/`PAGE_READ`/
                  `PAGE_NONE` ＝ "W"/"R"/"-"）。判定していなければ None

    **`exists` が何を指すかは、誰が作ったPageRefかで変わる。**
    resolve_page_ref（このモジュール）が作ったものは「平文ファイルがあるか」、
    pagedb.published_ref が作ったものは「公開されているか」を指す。
    どちらを受け取っていても `not ref.exists` で「無い」の判定になり、
    その場面で正しい「無い」（編集なら平文、表示なら公開）が返る。

    **`privilege` を埋めるのは pagedb.published_ref だけ**（Wiki設計者の指示、
    2026-09-15）。resolve_page_ref は誰が見ているかを知らない層なので None のまま。
    **`-` でも `body` は入っている**（今後の拡張で本文が要る場面のため）。
    出すかどうかは受け取った側が `privilege` を見て決めること。

    subpath は添付ファイル・バックアップの置き場所にもそのまま使う。
    URL（pagepath）と実体（subpath）は "/Tech" → "Tech/index" のようにずれるため、
    この2つを取り違えると index のページを取りこぼす。両方をここで一度に決めて
    持ち回ることで、呼び出し側が個別に index を解決しなくて済むようにしている。"""

    __slots__ = ("pagepath", "subpath", "ext", "path", "body", "exists", "privilege")

    def __init__(self, pagepath, subpath, ext, path, body, exists, privilege=None):
        self.pagepath = pagepath
        self.subpath = subpath
        self.ext = ext
        self.path = path
        self.body = body
        self.exists = exists
        self.privilege = privilege


def default_markup_ext(markup=None):
    """新しく作るページの拡張子。`markup` は記法の名前（`MARKUP_FORMATS`のキー）。

    渡さない・知らない名前のときはシステムの既定（`DEFAULT_MARKUP`）にする。
    Wikiごとの設定（`edit.defaultwiki`）を読むのは `wikiconfig.default_markup`
    の役目で、その戻り値をここへ渡してもらう（`DEFAULT_MARKUP`の注記参照）。"""
    return MARKUP_FORMATS[markup if markup in MARKUP_FORMATS else DEFAULT_MARKUP]["ext"]


def resolve_page_ref(wiki_dir, pagepath, default_markup=None):
    """URLのページパスから対象ページを特定する。wiki_dirの外を指す場合はNone。

    実在しないページでもNoneではなくPageRefを返す（exists=False）。新規作成や
    プレビューでも同じ判断（どのファイルを指すか）を使い回せるようにするため。

    `default_markup` は**まだ無いページ**に付ける拡張子を決める記法
    （`wikiconfig.default_markup(config)`の戻り値）。実在するページの拡張子は
    ファイル側で決まっているので、この指定は関係しない。渡さなければ
    システムの既定になる（既存ページしか扱わない呼び出しは渡さなくてよい）。"""
    real_wiki_dir = os.path.realpath(wiki_dir)
    real_target = os.path.realpath(os.path.normpath(os.path.join(wiki_dir, pagepath)))
    if real_target != real_wiki_dir and not real_target.startswith(real_wiki_dir + os.sep):
        return None

    # フォルダを指していれば、その中の index が対象。ページパスが空（そのWikiのトップ）や
    # 末尾スラッシュの場合も、実体としては index を指す。
    if os.path.isdir(real_target) or not pagepath or pagepath.endswith("/"):
        real_target = os.path.join(real_target, INDEX_NAME)

    subpath = os.path.relpath(real_target, real_wiki_dir).replace(os.sep, "/")
    found = resolve_page(real_target)
    if found is not None:
        path, ext, body = found
        return PageRef(pagepath, subpath, ext, path, body, True)

    # まだ無いページ。保存するなら既定の書式で、この場所になる
    ext = default_markup_ext(default_markup)
    return PageRef(pagepath, subpath, ext, real_target + ext, "", False)


def full_pagepath(base_pagepath, name):
    """書かれたリンク先 name を、いま開いているページ base_pagepath から見て
    解決し、ページパスにする（本家PukiWikiの get_fullname と同じ決まり）。

        （/p1/p2/page を開いているとき）
        abc         → abc            ルートからの絶対
        abc/def     → abc/def
        ./abc       → p1/p2/page/abc
        ../abc      → p1/p2/abc
        ../bbb/abc  → p1/p2/bbb/abc

    **`./` を付けない裸の名前は、となりではなくルートからの絶対**という点が
    要になる。PukiWikiで書かれた資産をそのまま読めるようにするための決まりで、
    `[[FrontPage]]` のような書きかたが、どのページから書かれていても同じ
    ページを指すようになる。

    `..` がルートを越える場合はルートで止める（本家はトップページへ落とすが、
    このWikiのトップはページパスが空なので同じ結果になる）。"""
    if name in ("", ".", "./"):
        return base_pagepath
    if name.startswith("./"):
        parts = [p for p in name.split("/") if p]  # "./abc" → [".", "abc"]
        parts[0] = base_pagepath
        return "/".join(p for p in parts if p)
    if name == ".." or name.startswith("../"):
        up = [p for p in name.split("/") if p]
        here = [p for p in base_pagepath.split("/") if p]
        while up and up[0] == "..":
            up.pop(0)
            if here:
                here.pop()
        return "/".join(here + up)
    return name.strip("/")


def _attach_owner_subpath(wiki_dir, owner_pagepath, base_pagepath, page_subpath):
    """添付ファイルの持ち主ページを、置き場所に使う実体パス（subpath）にする。

    フォルダを兼ねるページは実体が `<名前>/index` なので、ページパスから
    そのまま組み立てることはできない（`resolve_page_ref` にファイルを見て
    もらう必要がある）。いま開いているページが持ち主なら、その subpath を
    すでに持っているので調べ直さない。"""
    if owner_pagepath == base_pagepath:
        return page_subpath
    if wiki_dir is None:
        # 場所が分からない場面（差分表示など）。書かれたまま（トップページだけは実体が index）
        return owner_pagepath or INDEX_NAME
    ref = resolve_page_ref(wiki_dir, owner_pagepath)
    return ref.subpath if ref is not None else owner_pagepath


def resolve_link(page_subpath, href, wiki_dir=None):
    """本文に書かれたリンク先を解釈する。(種類, 値) を返す。

    **記法によらず、リンクの意味を決めるのはここだけ。** Markdownでも
    [PukiWiki記法](/Syntax/PukiWiki)でも、リンクは同じ形のトークンになったあと
    この関数を通る。書き手から見た決まりが記法で変わらないようにするためで、
    表示（render.rewrite_content_links）と記録（links.py）も同じ判断を使う。

    ## ページの指しかた（full_pagepath）

        /foo     このWiki内の絶対パス
        foo      **ルートからの絶対**（となりではない）
        ./foo    いま開いているページの下
        ../foo   1つ上から

    ## 添付ファイルの指しかた

    ディレクトリの部分だけを上と同じ決まりで読み、そこにあるページの添付と
    して扱う。**書いていなければ「いま開いているページ」**になる。

        （/p1/p2/page を開いているとき）
        img.jpg          → /p1/p2/page の添付
        ./img.jpg        → /p1/p2/page の添付
        ../img.jpg       → /p1/p2      の添付
        ../bbb/img.jpg   → /p1/p2/bbb  の添付
        bbb/img.jpg      → /bbb        の添付
        /bbb/img.jpg     → /bbb        の添付
        /img.jpg         → トップページの添付

    ページか添付ファイルかは**名前の形だけ**で決める。末尾が拡張子に見える形
    （PAGE_NAME_EXT_RE、`.` のあとに英数字1〜6文字）なら添付ファイル、
    そうでなければページとする。

        logo.png  bar.jpg  memo.txt   → 添付ファイル
        UsageGuide  Tech/Reference    → ページ

    実在するかは見ない。**まだ無いページへのリンクもページとして扱う**ため。
    リンクをたどって「このページはまだありません → このページを作る」へ
    進めるのは、このWikiの中心にある流れなので、書いた時点でリンク先が
    無くても構わないようにしている。

    wiki_dir は、添付の持ち主がフォルダを兼ねるページ（実体が `…/index`）
    だった場合にそれを見分けるために使う。渡さなくても、いま開いている
    ページの添付（いちばん多い書きかた）は正しく解ける。

    返す種類は3つ。
        ("page",   ページパス)      このWikiのページ
        ("attach", 実体パス/ファイル名) 持ち主のページと、その添付ファイル
        ("keep",   None)            触らないもの（外部URL・ページ内アンカー・
                                    mailto:・tel:・別Wiki・システムのURL）
    """
    if not href or href.startswith(("#", "mailto:", "tel:")) or "://" in href:
        return "keep", None

    bare, sep, anchor = href.partition("#")
    if href.startswith("/"):
        rest = bare[1:]
        if rest.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
            return "keep", None  # 別Wiki（/=名前/…）とシステムのURL（/.attach/…）
        if not PAGE_NAME_EXT_RE.search(bare):
            return "page", rest.rstrip("/") + sep + anchor
        # 添付ファイル。下の分岐で、ディレクトリの部分（/ページ/）をページと同じく
        # ルートからの絶対として読む（`/図.png` はトップページの添付）

    base = pagepath_of_subpath(page_subpath)

    if PAGE_NAME_EXT_RE.search(bare):
        head, slash, filename = bare.rpartition("/")
        if not slash:
            owner_subpath = page_subpath  # 書いていない＝いま開いているページ
        else:
            owner_subpath = _attach_owner_subpath(
                wiki_dir, full_pagepath(base, head + "/"), base, page_subpath)
        return "attach", owner_subpath + "/" + filename + sep + anchor

    return "page", full_pagepath(base, bare).rstrip("/") + sep + anchor


def page_ext_of_subpath(wiki_dir, subpath, default_markup=None):
    """実体のパス（拡張子抜き）から、そのページの拡張子を決める。
    まだ無いページは既定の書式のものを返す（`default_markup`。resolve_page_ref参照）。

    ページの実体（subpath）だけを持ち回っている処理が、その記法を取り違えずに
    書き戻せるようにするためのもの（.txt のページを .md として書き出してしまうと、
    同じ名前のページが2つできてしまう）。"""
    found = resolve_page(os.path.join(wiki_dir, subpath))
    if found is not None:
        return found[1]
    return default_markup_ext(default_markup)


def is_folder_entry(subpath):
    """その実体パスがフォルダの入口（`…/index`）かどうか。

    木に並ぶ1段ぶんの名前が `index` かどうか（pagetree.sort_key など）とは
    別の話で、ここが見るのは**実体パス全体**である。"""
    return subpath == INDEX_NAME or subpath.endswith("/" + INDEX_NAME)


def pagepath_of_subpath(subpath):
    """resolve_page_ref の逆。実体のパス（拡張子抜き）からURLのページパスを求める。
    ページ一覧を作るときなど、ファイル側から辿る場合に使う。"""
    if not is_folder_entry(subpath):
        return subpath
    return subpath[: -len(INDEX_NAME)].rstrip("/")


def entry_subpath_of(folder):
    """pagepath_of_subpath の逆向き。そのフォルダの入口ページの実体パス。

    **フォルダだと分かっている場合にだけ使う。** ふつうのページのページパスは
    実体パスと同じなので、URLから実体を求めるのは resolve_page_ref の役目
    （そちらはフォルダが実在するかをファイルシステムに聞く）。"""
    folder = (folder or "").strip("/")
    return folder + "/" + INDEX_NAME if folder else INDEX_NAME

def page_file_path(wiki_dir, pagepath, ext):
    """ページの保存先を決める。wiki_dirの外へ出るパスはNoneを返す。"""
    real_wiki_dir = os.path.realpath(wiki_dir)
    target = os.path.realpath(os.path.normpath(os.path.join(wiki_dir, pagepath + ext)))
    if not target.startswith(real_wiki_dir + os.sep):
        return None
    return target


def iter_pages(wiki_dir):
    """wiki配下の全ページを (ページパス, 本文) で列挙する。
    ページ名のルールどおり、"=" や "." で始まる名前は対象外とする。"""
    seen = set()
    for dirpath, dirnames, filenames in os.walk(wiki_dir):
        dirnames[:] = [
            d for d in sorted(dirnames)
            if not d.startswith((FARM_PREFIX, SYSTEM_PREFIX))
        ]
        for fname in sorted(filenames):
            stem, ext = os.path.splitext(fname)
            if ext not in PAGE_EXTS or stem.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
                continue
            target = os.path.join(dirpath, stem)
            if target in seen:
                continue
            seen.add(target)
            found = resolve_page(target)  # .txt優先。閲覧時と同じ内容を検索対象にする
            if found is None:
                continue
            subpath = os.path.relpath(target, wiki_dir).replace(os.sep, "/")
            yield pagepath_of_subpath(subpath), found[2]


def is_valid_pagepath(pagepath):
    """"=" はWiki指定、"." はシステム資材用の予約プレフィックスのため、ページ名には使用できない。"""
    return not any(
        seg.startswith((FARM_PREFIX, SYSTEM_PREFIX)) for seg in pagepath.split("/")
    )
