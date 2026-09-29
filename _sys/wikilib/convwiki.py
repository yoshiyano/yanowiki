"""PukiWikiのデータを、このWikiのデータへ移す（`./wiki.py convwiki`）。

    ./wiki.py convwiki 1ev-c Prog1

と実行すると、`~/syncthing/pukiwiki/1ev-c/` のページと添付ファイルをもとに、
`wikidata/Prog1/` を**新しいWikiとして**作る。既にあるWikiには書き込まない
（取り違えると元のWikiを壊すため。入れ直したいときは作り直す）。

## そのまま写すもの、写さないもの

本文は**そのまま写す**。PukiWiki記法はこのシステムがそのまま読めるので
（拡張子 `.txt` が PukiWiki記法。`wikilib.pukiwiki`）、書き換える必要がない。
写さないのは次のもの。

    :config/…          PukiWikiの設定ページ。このシステムでは意味を持たない
                       （`--include-system` で写せる）
    付属のページ       FormattingRules・SandBox・RecentChanges など、PukiWikiに
                       最初から入っている15枚（`STOCK_PAGES`）と、説明書
                       `PukiWiki` 本体・配下11枚（`STOCK_FOLDERS`。前方一致）。
                       どのWikiにも同じものが入っていて、書いた人の中身ではない
                       （`--include-stock` で写せる）
    #author(…) 行      PukiWikiが保存のたびに書き足す管理行。このシステムには
                       同名のプラグインが無く、そのままだとページの先頭に
                       エラーが出る。**時刻だけは更新日時として使う**
    #freeze 行         凍結の印。このシステムには凍結が無い（権限で行う）
    backup/ diff/      PukiWikiの履歴。このシステムの履歴は形式が違うため、
    counter/ cache/    移さない。元のPukiWikiを消さずに残しておけば読める
    *.1 *.2 …          添付ファイルの旧版（PukiWikiが残した世代）
    *.sync-conflict-…  syncthingが作った競合ファイル

## 本文をさらに書き換える3つの手当て（プラグイン呼び出し）

「文面はそのまま写す」が基本だが、次の3つは書き換える（Wiki設計者の指示、
2026-09-18）。どれも**書き換えないと本文の中にエラーが出る、または
プラグインが展開されない**類のもので、直さないほうが実害が大きい。

    attachref → ref     ls2 → ls
        このシステムに実装が無い、本家PukiWikiの非標準プラグイン。
        `ref`/`ls`がそれぞれの役割を引き継いでいて、引数の並びも同じ
        なので、**名前だけ機械的に置き換える**（`rewrite_plugin_aliases`）。
        空引数（`&attachref();`）や本家固有のオプション（`#ls2(,title)`の
        `title`）は置き換えた先でも動かないが、実データでの内訳は
        「置き換えずに残す＝常にエラー」840件超に対し1割未満で、
        **置き換えたほうが圧倒的に多く直る**（Wiki設計者の指示）

    #name(...);  →  #name(...)
        ブロックプラグインの後ろに、インラインの書きかた（`&name(...);`）を
        混同した `;` が付いている本文が多い。セミコロンが残っていると
        **プラグインとして展開されず、ただの文字列として表示される**
        （`pukiwiki.PLUGIN_BLOCK_RE`は`;`を許さない）ので、これは見た目の
        整形ではなく不具合の修正（`strip_block_semicolons`）

    #navi(元のページの親フォルダと同じ書きかた)  →  #navi(..)
        `#navi(..)`が本来の使いかたなのに、その場しのぎで絶対パスの
        ページ名を書いてしまっている本文が多い。**そのページの直接の親
        フォルダと一致する場合だけ**`..`に直す（`rewrite_navi_home`）。
        すでに相対（`.`/`..`/`../`）のものや、親と違う場所を指しているもの
        （実データには無かったが、機械的な判定なので念のため）は触らない

## 名前の付け替え

PukiWikiのページ名は、このシステムのページパスにほぼそのまま対応する
（どちらも "/" で階層を表す）。手を入れるのは次の2つだけ。

    $defaultpage → index   このシステムのトップページは `index` で固定
                           （Wiki設計者の指示、2026-09-18）。どのページが
                           トップだったかは決め打ちにせず、PukiWikiの
                           `$defaultpage` から読む（実データには `TopPage` と
                           `FrontPage` の両方があった）
    子を持つページ → <名前>/index
                           `A.txt` とフォルダ `A/` は同居できない
                           （`wikilib.paths` の PAGE_EXTS 付近）。
                           子があるページは入口の形にして写す

**メニューのページ（MenuBar・RightBar）は名前を変えない。** 代わりに、この
Wikiの設定（`theme.menu1_page` / `menu2_page`）をそちらへ合わせる
（Wiki設計者の指示、2026-09-18）。本文からの `[[MenuBar]]` のような参照が
そのまま生きるので、名前を変えるより副作用が小さい。

本文は**そのまま写す**が、**トップページを指していたリンクだけは直す**
（`fix_top_page_links`）。`index` への改名はこちらの都合なので、それで壊れる
リンクは改名した側で直す。使うのはページの名前の変更と同じ道具
（`pagerename.fix_links`）。

## PukiWikiの設定を引き継ぐ

`pukiwiki.ini.php` と `default.ini.php` から、**このシステムに同じ意味の項目が
あるものだけ**を `wikidata/<Wiki名>/config/default.yaml` へ書く
（`settings_from_ini`）。

    $page_title     → theme.site_title   （配布時のまま "PukiWiki" ならWiki名）
    $menubar        → theme.menu1_page   （サイドバー上段）
    $rightbar_name  → theme.menu2_page   （右カラム、目次の下）
    $nowikiname     → pukiwiki.wikiname  （真偽が逆）
    $usefacemark    → pukiwiki.facemark
    スキン          → theme.name         （PukiWikiの既定スキンに当たるテーマ）

近いだけの項目には当てはめない。`$read_auth` や `$edit_auth` のように、
このシステムでは別の仕組み（ページごとの権限）で決めるものは、**設定として
書かずに報告へ回す**。移した先で違う効きかたをするより、あとから決め直せる
ほうがよいため。

読むのは上に挙げた変数だけにしてある。同じファイルには `$adminpass`（平文の
パスワード）も並んでいるので、丸ごと読んでから選ぶのではなく、要るものだけを読む。

## 更新日時

`#author("2026-04-10T10:11:18+09:00",…)` の時刻を、写した先のファイルの
更新日時にする。無ければ元ファイルの更新日時を使う。PukiWikiのファイルは
コピーや同期でまとめて新しくなっていることがあり（実データで確認済み）、
そのときは `#author` のほうが本当の更新日時に近いため。更新順の一覧
（`#recent`）がPukiWikiでの見えかたと揃う。

## 最後にすること

写し終えたら `pagesync.sync_wiki(force=True)` を通す。平文を置いただけでは
DB（タイトル・目次・リンク・全文検索）が空のままなので、`./wiki.py updatepage`
と同じ取り込みをここで済ませる。
"""
import binascii
import os
import re
import shutil
import time
from html.entities import html5

from wikilib.attach import safe_attach_name
from wikilib.newwiki import create_wiki, validate_name
from wikilib.paths import FARM_PREFIX, INDEX_NAME, SYSTEM_PREFIX, WIKIDATA_DIR, safe_join

# 変換元の既定の置き場所。`~/pukiwiki` は `~/syncthing/pukiwiki` への
# シンボリックリンクなので、どちらで書いても同じ場所を指す
DEFAULT_SOURCE_ROOT = os.path.expanduser("~/syncthing/pukiwiki")

HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")
# PukiWikiが本文の先頭に書く管理行。`#author("時刻","ID","名前")` と `#freeze`
AUTHOR_RE = re.compile(r'^#author\("([^"]*)"')
FREEZE_RE = re.compile(r"^#freeze\s*$")
# PukiWikiの設定ファイル。読む順（あとのものが優先。PukiWikiの読み込み順と同じで、
# default.ini.php は「見る人ごとの既定」として pukiwiki.ini.php のあとに重なる）
INI_FILES = ("pukiwiki.ini.php", "default.ini.php")
# 設定ファイルから拾う変数。**ここに挙げたものだけを読む。**
# 同じファイルには `$adminpass`（平文のパスワード）のような、こちらへ持ち込んで
# よくないものも並んでいる。丸ごと読んでから選ぶのではなく、要るものだけを読む
INI_WANTED = (
    "page_title", "defaultpage", "menubar", "rightbar_name",
    "nowikiname", "usefacemark", "read_auth", "edit_auth", "line_break",
)
# PukiWikiが `$defaultpage` を書いていなかったときの、本家の既定値
DEFAULT_TOP_PAGE = "FrontPage"
# PukiWikiに最初から入っている付属のページ（記法の説明・練習場・自動で書かれる一覧）。
# **どのWikiにも同じものが入っていて、書いた人の中身ではない**ので写さない
# （Wiki設計者の指示、2026-09-18。実データ4つのどれにも、この15枚が揃っていた）。
# `--include-stock` で写せる
STOCK_PAGES = frozenset({
    "AutoTicketLinkName", "BracketName", "FormattingRules", "Help", "InterWiki",
    "InterWikiName", "InterWikiSandBox", "PHP", "RecentChanges", "RecentDeleted",
    "SandBox", "WikiEngines", "WikiName", "WikiWikiWeb", "YukiWiki",
})
# PukiWiki本体の説明書（マニュアル）。`PukiWiki` 自身とその配下すべて
# （`PukiWiki/1.4/Manual/Plugin/A-D` など）が対象で、STOCK_PAGES と違って
# **前方一致**で判定する（フォルダ丸ごとが配布物のため）。実データ4つのどれにも、
# 同じ11枚が揃っていた（Wiki設計者の指示、2026-09-18。「Pukiwikiフォルダも
# 転送不要」）。`--include-stock` で写せる（STOCK_PAGESと同じ扱い）
STOCK_FOLDERS = ("PukiWiki",)


def is_stock_page(name):
    """PukiWiki付属のページ（`STOCK_PAGES` または `STOCK_FOLDERS` 配下）か。"""
    if name in STOCK_PAGES:
        return True
    return any(name == folder or name.startswith(folder + "/")
              for folder in STOCK_FOLDERS)
# PukiWikiの既定スキンに当たるテーマ。移したあとの見た目を、元のWikiに近づける
DEFAULT_THEME = "pukiwiki_default"
# `$page_title` がこの値なら、PukiWiki側で名前を付けていない（配布時のまま）
STOCK_PAGE_TITLE = "PukiWiki"
PHP_ASSIGN_RE = re.compile(r"^\s*\$([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*;")
# YAMLに引用符なしで書ける値かどうか
PLAIN_YAML_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
# 添付ファイルの旧版（`…_ファイル名.1`）と、syncthingの競合ファイル
ATTACH_OLD_RE = re.compile(r"\.\d+$")
CONFLICT_MARK = ".sync-conflict-"
# 本文で使われているプラグインを拾う（報告用。実行はしない）
PLUGIN_BLOCK_RE = re.compile(r"^#([A-Za-z_][A-Za-z0-9_-]*)", re.M)
PLUGIN_INLINE_RE = re.compile(r"&([A-Za-z_][A-Za-z0-9_-]*)\s*[({;]")

# PukiWikiの非標準プラグインのうち、このシステムの標準プラグインが同じ役割を
# 持っているもの。`attachref`は`ref`の、`ls2`は`ls`の、本家における別名・
# 上位互換にあたる（引数の並びも同じ）ので、名前だけ書き換えれば動く
# （Wiki設計者の指示、2026-09-18）。
#
# **機械的に置き換える。** 空引数（`&attachref();`）や本家固有のオプション
# （`#ls2(,title)`のtitleなど）は書き換えた先でも動かないが、実データでの
# 内訳は「このシステムに無いプラグインとして常にエラーになる」840件超に対し
# 動かないまま残るのは1割未満で、**置き換えないより置き換えたほうが圧倒的に
# 多くのページが直る**（Wiki設計者の指示、2026-09-18「置き換えずにエラーに
# なるより、置き換えてエラーになる件数のほうが圧倒的なので、機械的に
# 置き換えてください」）。動かないまま残った呼び出しは`unknown_plugins`とは
# 別に拾って報告する（`rewrite_plugin_aliases`）。
PLUGIN_ALIASES = {"attachref": "ref", "ls2": "ls"}
# ブロック（`#name(...)`）・インライン（`&name(...)`/`&name;`）どちらの形でも
# 使われているため、両方を見る。名前の直後が `(` か `;` か（ブロックは行末も）
# であることを確かめてから置き換える——`#ls2を` のように、たまたま名前で
# 始まる地の文（プラグインのマニュアルページに実例が多い）を巻き込まないため
PLUGIN_ALIAS_BLOCK_RE = re.compile(
    r"^#(" + "|".join(PLUGIN_ALIASES) + r")(?=[(;]|\s*$)", re.M)
PLUGIN_ALIAS_INLINE_RE = re.compile(
    r"&(" + "|".join(PLUGIN_ALIASES) + r")(?=[(;])")

# ブロックプラグイン呼び出し `#name(args)` の直後についた、誤りの `;`。
# PukiWikiのブロックプラグインはセミコロンを書かない記法（つけるのは
# インライン `&name(args);` のほう）だが、間違えて書かれている本文が多い
# （Wiki設計者の指摘、2026-09-18）。セミコロンが残っていると
# `pukiwiki.PLUGIN_BLOCK_RE`（末尾は `\s*$` で、`;` を許さない）に
# マッチせず、**プラグインとして展開されずただの文字列として表示される**
# ——地味に見えるが実際には壊れているので、これは単なる整形以上の意味を持つ。
#
# 実データに例があったのは `#name(args);` の単純形だけ（本体つき
# `#name(args){body};` やbody複数行の `#name{{ … }};` の例は無い）ので、
# その形だけを対象にする。貪欲マッチ（`.*`）は`pukiwiki.PLUGIN_BLOCK_RE`の
# 引数の取りかたに合わせてある
BLOCK_SEMICOLON_RE = re.compile(
    r"^(#[A-Za-z_][\w-]*(?:\(.*\))?)[ \t]*;[ \t]*$", re.M)

# navi の第一引数（home）を取り出す。本体つき呼び出しの例が無いので
# `#name(args)` の単純形だけを見る（BLOCK_SEMICOLON_REと同じ理由）
NAVI_CALL_RE = re.compile(r"#navi\(([^)]*)\)")


def source_dir(name, root=None):
    """変換元のディレクトリを決める。見つからなければNone。

    名前だけ（`1ev-c`）なら既定の置き場所の下、"/" を含むならパスとして扱う。
    置き場所を丸ごと別の場所へ移していても使えるようにするため。"""
    if not name:
        return None
    if "/" in name or os.path.isabs(name):
        path = os.path.abspath(os.path.expanduser(name))
    else:
        path = os.path.join(root or DEFAULT_SOURCE_ROOT, name)
    return path if os.path.isdir(os.path.join(path, "wiki")) else None


def php_value(raw):
    """PHPの右辺を、Pythonの値にする。読めない書きかたならNone。

    読むのは文字列（`'MenuBar'`）と整数（`0`）だけ。配列や式は、移せる設定の
    中に無いので相手にしない。"""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        quote = raw[0]
        out, escaped = [], False
        for ch in raw[1:]:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                return "".join(out)
            else:
                out.append(ch)
        return None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return None


def read_ini(src):
    """PukiWikiの設定ファイルから、移せる値だけを読む。{変数名: 値} を返す。

    見るのは `INI_FILES` の2つ。PHPを実行するわけではないので、`if` の中の
    代入や式で組み立てている値は読めない——読めたものだけを使い、読めなければ
    その設定は移さない（書き損じた値を引き継ぐより、共通の既定値のままの
    ほうが安全なため）。"""
    found = {}
    for filename in INI_FILES:
        path = os.path.join(src, filename)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lstrip().startswith(("//", "#", "*")):
                    continue
                match = PHP_ASSIGN_RE.match(line)
                if match is None or match.group(1) not in INI_WANTED:
                    continue
                value = php_value(match.group(2))
                if value is not None:
                    found[match.group(1)] = value
    return found


def top_page_name(ini, override=""):
    """どのページをトップページ（`index`）にするかを決める。

    このシステムのトップページは `index` で固定なので（Wiki設計者の指示、
    2026-09-18）、PukiWikiが `$defaultpage` に書いていたページを `index` として
    写す。`$defaultpage` は書き換えられていることがあり（実データでは `TopPage` と
    `FrontPage` の両方があった）、**決め打ちにはできない**。"""
    return (override or ini.get("defaultpage") or DEFAULT_TOP_PAGE).strip("/")


def settings_from_ini(ini, wiki_name, theme=DEFAULT_THEME):
    """PukiWikiの設定を、このWikiの `config/default.yaml` の中身にする。

    [(節, 項目, 値, 由来の説明)] と、移せなかったものの説明を返す。

    **移すのは、このシステムに同じ意味の項目があるものだけ。** 近いだけの
    項目へ当てはめると、移した先で違う効きかたをする。当てはめずに報告へ
    回すほうが、あとから決め直せる。"""
    items, notes = [], []

    title = ini.get("page_title")
    if title and title != STOCK_PAGE_TITLE:
        items.append(("theme", "site_title", title, f"$page_title = '{title}'"))
    else:
        # 配布時のまま（"PukiWiki"）なら、そのWikiの名前を入れる。ヘッダに
        # 「PukiWiki」と出ても、どのWikiなのかが読み手に伝わらないため
        items.append(("theme", "site_title", wiki_name,
                      "$page_title は配布時のままだったので、Wikiの名前を入れています"))

    menubar = (ini.get("menubar") or "").strip("/")
    if menubar:
        items.append(("theme", "menu1_page", menubar,
                      f"$menubar = '{menubar}'（サイドバー上段。ページ名は変えずに"
                      "、こちらを合わせています）"))
    rightbar = (ini.get("rightbar_name") or "").strip("/")
    if rightbar:
        items.append(("theme", "menu2_page", rightbar,
                      f"$rightbar_name = '{rightbar}'（このシステムのmenu2。"
                      "右のカラムで、目次の下に出ます）"))
    if theme:
        items.append(("theme", "name", theme,
                      "PukiWikiの既定スキンに当たるテーマ"))

    if ini.get("nowikiname"):
        items.append(("pukiwiki", "wikiname", False,
                      "$nowikiname = 1（WikiNameの自動リンクを切っていた）"))
    if "usefacemark" in ini and not ini["usefacemark"]:
        items.append(("pukiwiki", "facemark", False, "$usefacemark = 0"))

    # 写したページはすべてPukiWiki記法（.txt）。新しく作るページの初期値も
    # それに合わせておく（共通の既定値と同じ値だが、**このWikiの性格として**
    # 書いておく。共通の既定値が変わっても、このWikiは変わらない）
    items.append(("edit", "defaultwiki", "pukiwiki",
                  "写したページはすべてPukiWiki記法（.txt）です"))

    if ini.get("read_auth"):
        notes.append("$read_auth = 1 … 閲覧に認証を要求していました。"
                     "このシステムには全体で切り替える設定が無いので、"
                     "ページごとの権限（config/privileges）で設定してください")
    if ini.get("edit_auth"):
        notes.append("$edit_auth = 1 … 編集に認証を要求していました。"
                     "全体で断るなら config/privileges に「*:W:g:all」（あわせて「*:R:g:any」）を、"
                     "ページごとなら config/privileges にそのページを書いてください")
    if ini.get("line_break"):
        notes.append("$line_break = 1 … 行末で改行する設定でしたが、"
                     "このシステムには同じ設定がありません")
    return items, notes


def config_text(items, notes, src_name):
    """`config/default.yaml` に書く文面を組み立てる。

    共通の既定値（`config/default.example.yaml`）を丸ごと写すのではなく、
    **PukiWikiから引き継いだ項目だけ**を書く。書かれていない項目は共通の
    既定値がそのまま効くので、こちらを直せば移したWikiにも届く
    （`wikilib.wikiconfig.load_config` の冒頭）。"""
    lines = [
        f"# PukiWiki（{src_name}）の設定から引き継いだ項目です"
        "（`./wiki.py convwiki` が書きました）。",
        "# 由来をコメントに添えてあります。書かれていない項目は、共通の既定値",
        "# （config/default.example.yaml）がそのまま効きます。",
        "",
    ]
    for section in dict.fromkeys(section for section, _, _, _ in items):
        lines.append(f"{section}:")
        for one, key, value, why in items:
            if one != section:
                continue
            lines.append(f"  # {why}")
            lines.append(f"  {key}: {yaml_value(value)}")
        lines.append("")
    if notes:
        lines.append("# 引き継げなかった設定:")
        lines.extend("#   " + note for note in notes)
        lines.append("")
    return "\n".join(lines)


def yaml_value(value):
    """YAMLの値として書く。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if PLAIN_YAML_RE.match(text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def decode_hex(stem):
    """PukiWikiのファイル名（ページ名をhexで書いたもの）を戻す。読めなければNone。"""
    if not HEX_RE.match(stem) or len(stem) % 2:
        return None
    try:
        return binascii.unhexlify(stem).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None


def strip_pukiwiki_header(text):
    """先頭の管理行（`#author` / `#freeze`）を落とす。(本文, 時刻文字列orNone) を返す。

    どちらもPukiWikiが自分の都合で書き足す行で、読み手に見せる文面ではない。
    残すと、このシステムには同名のプラグインが無いためページの先頭に
    エラーが出る。**先頭にある分だけ**を落とす（本文の途中に同じ書きかたが
    あれば、それは書いた人が置いたものなので触らない）。"""
    stamp = None
    lines = text.split("\n")
    cut = 0
    for line in lines:
        found = AUTHOR_RE.match(line)
        if found:
            stamp = stamp or found.group(1)
            cut += 1
            continue
        if FREEZE_RE.match(line):
            cut += 1
            continue
        break
    return "\n".join(lines[cut:]), stamp


def parse_stamp(text):
    """`#author` の時刻（ISO 8601）を time.time() と同じ形の数にする。読めなければNone。"""
    if not text:
        return None
    try:
        import datetime
        return datetime.datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def safe_segment(segment, strict=True):
    """ページ名の1階層ぶんを、このシステムで使える形に整える。

    "=" と "." で始まる名前は使えない（`paths.is_valid_pagepath`。前者はWiki指定、
    後者はシステム資材のURLに使う）。前後の空白も、見た目で区別できないので落とす。
    ここまでは strict でなくても必ず行う。

    strict ではさらに末尾の "." も落とす。ファイル名として扱いにくいためだが、
    **落とすと別のページと同じ名前になってしまうことがある**（実データに
    「演習」と「演習.」が並んでいた）。そのときは呼び出し側が strict=False で
    取り直し、元の名前のまま写す。整える都合でページを1枚失うほうが困るため。"""
    cleaned = segment.strip()
    if strict:
        cleaned = cleaned.rstrip(" .")
    if cleaned.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
        cleaned = "_" + cleaned
    return cleaned or "_"


def collect_pages(src, include_system=False, include_stock=False):
    """変換元のページを集める。{ページ名: ファイルのパス} と、写さないものを返す。"""
    pages, skipped = {}, []
    wiki = os.path.join(src, "wiki")
    for filename in sorted(os.listdir(wiki)):
        if not filename.endswith(".txt"):
            continue  # .bk（PukiWikiの旧版）など
        stem = filename[: -len(".txt")]
        if CONFLICT_MARK in stem:
            skipped.append((filename, "syncthingの競合ファイル"))
            continue
        name = decode_hex(stem)
        if name is None:
            skipped.append((filename, "ファイル名を読めない"))
            continue
        if name.startswith(":") and not include_system:
            skipped.append((name, "PukiWikiの設定ページ"))
            continue
        if is_stock_page(name) and not include_stock:
            skipped.append((name, "PukiWiki付属のページ"))
            continue
        pages[name] = os.path.join(wiki, filename)
    return pages, skipped


def plan_subpaths(names, top_page=DEFAULT_TOP_PAGE):
    """ページ名から、写した先の実体パス（拡張子抜き）を決める。

    {ページ名: 実体パス} と、付け替えの記録・衝突の記録を返す。付け替えは
    モジュール冒頭の「名前の付け替え」のとおり。

    top_page は `index` にするページ（PukiWikiの `$defaultpage`）。空文字を
    渡すと、そのページも他と同じように元の名前で写す。"""
    def tidy(name, strict=True):
        parts = [safe_segment(seg, strict) for seg in name.split("/") if seg.strip()]
        return "/".join(parts)

    cleaned = {}
    renamed, conflicts = [], []
    for name in sorted(names):
        subpath = tidy(name)
        if not subpath:
            conflicts.append((name, "名前が空になる"))
            continue
        cleaned[name] = subpath
    # 整えた結果が他のページとぶつかったものは、整えずに写し直す（safe_segment参照）
    crowded = {sub for sub in cleaned.values()
               if sum(1 for one in cleaned.values() if one == sub) > 1}
    for name, subpath in list(cleaned.items()):
        if subpath in crowded and tidy(name, strict=False) != subpath:
            cleaned[name] = tidy(name, strict=False)
    for name, subpath in cleaned.items():
        if subpath != name:
            renamed.append((name, subpath, "使えない文字を直した"))

    # トップページだけは `index` にする。このシステムのトップページは
    # `index` で固定のため（Wiki設計者の指示、2026-09-18）。メニューのページは
    # **名前を変えず**、設定（theme.menu1_page / menu2_page）のほうを合わせる
    taken = set(cleaned.values())
    if top_page and top_page in cleaned:
        if INDEX_NAME in taken:
            # 写した先に index という名前のページが既にあるなら、付け替えない
            renamed.append((top_page, cleaned[top_page],
                            f"{INDEX_NAME} が既にあるので元の名前のまま"))
        else:
            taken.discard(cleaned[top_page])
            cleaned[top_page] = INDEX_NAME
            taken.add(INDEX_NAME)
            renamed.append((top_page, INDEX_NAME, "トップページ"))

    # 子を持つページは入口（<名前>/index）にする。`A.txt` とフォルダ `A/` は
    # 同居できないため（モジュール冒頭「名前の付け替え」）
    folders = set()
    for subpath in cleaned.values():
        parts = subpath.split("/")
        for i in range(1, len(parts)):
            folders.add("/".join(parts[:i]))

    # 入口の形に変えないページを先に決め、変えるページを後から入れる。
    # `A` と `A/index` が両方あるという珍しい場合に、**元から入口の形をして
    # いるほう**（`A/index`）を残すため。逆にすると、そのWikiの入口として
    # 書かれていたページが消えてしまう
    result, used = {}, {}
    for entering in (False, True):
        for name in sorted(cleaned, key=lambda n: cleaned[n]):
            subpath = cleaned[name]
            if (subpath in folders) is not entering:
                continue
            if entering:
                subpath = subpath + "/" + INDEX_NAME
                renamed.append((name, subpath, "子を持つページの入口"))
            if subpath in used:
                conflicts.append((name, f"{used[subpath]} と同じ場所（{subpath}）になる"))
                continue
            used[subpath] = name
            result[name] = subpath
    return result, renamed, conflicts


def collect_attachments(src, subpaths):
    """添付ファイルを集める。[(元のパス, 写す先の相対パス, 元のファイル名)] と、
    写せないものを返す。

    PukiWikiの添付は `attach/<ページ名のhex>_<ファイル名のhex>` という1枚の
    ファイルで、末尾に数字が付いたものは旧版、`.log` はダウンロード数の記録。
    このシステムの置き場所はページのパスをそのままミラーしたフォルダなので
    （`wikilib.attach`）、持ち主のページから写す先が決まる。"""
    plans, skipped = [], []
    attach = os.path.join(src, "attach")
    if not os.path.isdir(attach):
        return plans, skipped
    for filename in sorted(os.listdir(attach)):
        if filename.startswith(".") or filename in ("index.html",):
            continue
        if filename.endswith(".log"):
            continue  # ダウンロード数の記録。中身はページでも添付でもない
        if CONFLICT_MARK in filename:
            skipped.append((filename, "syncthingの競合ファイル"))
            continue
        page_hex, sep, file_hex = filename.partition("_")
        if not sep:
            skipped.append((filename, "添付ファイルの形になっていない"))
            continue
        if ATTACH_OLD_RE.search(file_hex):
            continue  # PukiWikiが残した旧版（…_ファイル名.1）
        page = decode_hex(page_hex)
        name = decode_hex(file_hex)
        if page is None or name is None:
            skipped.append((filename, "ファイル名を読めない"))
            continue
        if page not in subpaths:
            skipped.append((f"{page}/{name}", "持ち主のページを写していない"))
            continue
        safe = safe_attach_name(name)
        if safe is None:
            skipped.append((f"{page}/{name}", "使えないファイル名"))
            continue
        plans.append((os.path.join(attach, filename),
                      os.path.join(subpaths[page], safe), name))
    return plans, skipped


def unknown_plugins(texts, wiki_dir):
    """写した本文が呼んでいるプラグインのうち、このシステムに無いものを数える。

    移したあとに「ページの真ん中にエラーが出る」のを、動かす前に知らせるための
    もの。ここで止めはしない——文面はそのまま写すのが目的で、足りないプラグインを
    どうするか（作る・書き換える・放っておく）は移したあとの判断になる。"""
    from wikilib.paths import farm_plugin_dir
    from wikilib.plugins import load_plugins

    known = set(load_plugins(farm_plugin_dir(wiki_dir)))
    counts = {}
    for text in texts:
        for found in PLUGIN_BLOCK_RE.findall(text):
            if found not in known:
                counts[found] = counts.get(found, 0) + 1
        for found in PLUGIN_INLINE_RE.findall(text):
            if found in known or found + ";" in html5:
                continue  # `&amp;` のようなHTML実体参照はプラグインではない
            counts["&" + found] = counts.get("&" + found, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


def references_to_renamed(texts, renamed):
    """付け替えたページ名が本文で何回参照されているかを数える。

    文面は書き換えないので（モジュール冒頭「名前の付け替え」）、直す必要が
    あるかどうかを移したあとに判断できるよう、件数だけを報告に載せる。"""
    counts = {}
    for name, subpath, reason in renamed:
        if reason != "トップページ":
            continue
        hits = sum(text.count(name) for text in texts)
        if hits:
            counts[name] = (subpath, hits)
    return counts


def strip_block_semicolons(text):
    """ブロックプラグイン呼び出しの末尾についた誤りの `;` を消す。
    (新しい本文, 消した数) を返す（`BLOCK_SEMICOLON_RE`参照）。"""
    text, count = BLOCK_SEMICOLON_RE.subn(r"\1", text)
    return text, count


def rewrite_plugin_aliases(text):
    """`attachref`→`ref`、`ls2`→`ls` に、名前だけを機械的に置き換える。
    (新しい本文, {元の名前: 件数}) を返す（`PLUGIN_ALIASES`参照。**動かない
    呼び出しがあっても置き換える**——モジュール冒頭のコメントとWiki設計者の
    指示、2026-09-18）。

    呼ぶ前に`strip_block_semicolons`を通しておくこと。`#ls2(...);`のように
    セミコロンが残っていると、`;`が引数の外にあるためここでは一緒に検出できる
    （このRE自体は`;`の有無を問わない）が、置き換えたあとの`#ls(...);`は
    セミコロン付きのままなので、結局プラグインとして展開されない。"""
    counts = {}

    def block_repl(m):
        name = m.group(1)
        counts[name] = counts.get(name, 0) + 1
        return "#" + PLUGIN_ALIASES[name]

    def inline_repl(m):
        name = m.group(1)
        counts[name] = counts.get(name, 0) + 1
        return "&" + PLUGIN_ALIASES[name]

    text = PLUGIN_ALIAS_BLOCK_RE.sub(block_repl, text)
    text = PLUGIN_ALIAS_INLINE_RE.sub(inline_repl, text)
    return text, counts


def rewrite_navi_home(text, subpath):
    """`#navi(引数)`の第一引数（home）が、そのページの**直接の親フォルダ**と
    同じ書きかたなら `..` に置き換える。(新しい本文, 直した数) を返す。

    `home`は本文のリンクと同じ決まりで相対パスを書ける
    （`navi.py`のdocstring）。`#navi(..)`の形が本来の使いかたで、実データは
    「その場しのぎで絶対パスを書いてしまった」ケースがほとんどだった
    （Wiki設計者の指摘、2026-09-18）。**すでに相対で書かれているもの
    （`.`/`..`/`../`）や、親と一致しないものは触らない**——本当に別の場所を
    指している`#navi(講義)`のような呼びかたまで壊さないため（実データでは
    起きなかったが、機械的な判定なので念のため一致するものだけに絞る）。

    subpath は**実体パス**（`plan_subpaths`が決めた書く先）。子を持つ
    ページは`<名前>/index`になっているので（モジュール冒頭「名前の付け替え」）、
    その1つ上（`<名前>`）は**同じページの入口フォルダ**であって親ページでは
    ない。`pagepath_of_subpath`で`/index`を剥がしてから親を数える
    （`演習/第01回/index`→ページパス`演習/第01回`→親`演習`）。"""
    from wikilib.paths import pagepath_of_subpath
    from wikilib.plugins import parse_plugin_args

    pagepath = pagepath_of_subpath(subpath)
    parent = pagepath.rsplit("/", 1)[0] if "/" in pagepath else ""
    if not parent:
        return text, 0  # 最上位のページ（親が無い）は対象にならない
    count = 0

    def repl(m):
        nonlocal count
        argstr = m.group(1)
        args, _ = parse_plugin_args(argstr)
        if not args or args[0] is None:
            return m.group(0)
        home = str(args[0]).strip()
        if not home or home in (".", "..") or home.startswith(("./", "../")):
            return m.group(0)  # 空、またはすでに相対
        if home.strip("/") != parent:
            return m.group(0)  # 親フォルダとは違う場所を指している
        count += 1
        rest = argstr.split(",", 1)
        new_argstr = ".." + ("," + rest[1] if len(rest) > 1 else "")
        return f"#navi({new_argstr})"

    text = NAVI_CALL_RE.sub(repl, text)
    return text, count


def point_to_top_page(text, top_page):
    """`[[TopPage]]` のように**名前がそのまま見えている**リンクを、
    `[[TopPage>/]]` に変える。(新しい本文, 直した数) を返す。

    トップページは `index` になるので、名前だけのリンクをそのまま
    `fix_top_page_links` に任せると `[[/]]`——つまり画面に「/」とだけ出る
    リンクになる。**見えている文字は元のまま、指し先だけを移したい**ので、
    先に「表示＞指し先」の形にしておく。

    どこがリンクなのかの判定は、このシステム自身の走査（`pagelinks.link_spans`）
    に任せる。整形済みやコードの中の `[[…]]` を書き換えてしまわないため。
    `[[表示>TopPage]]` のように既に分かれている書きかたは触らない
    （そちらは `fix_top_page_links` が指し先だけを直す）。"""
    if not top_page:
        return text, 0
    from wikilib.pagelinks import link_spans

    out, last, count = [], 0, 0
    for start, end, href, _ in link_spans(text, ".txt"):
        if href != top_page:
            continue
        if text[max(0, start - 2):start] != "[[" or text[end:end + 2] != "]]":
            continue  # 名前だけの書きかたではない
        out.append(text[last:start])
        out.append(top_page + ">/")
        last = end
        count += 1
    if not count:
        return text, 0
    out.append(text[last:])
    return "".join(out), count


def fix_top_page_links(wiki_dir, top_page):
    """トップページにした元の名前（`[[TopPage]]` など）を指すリンクを直す。
    直したページ数を返す。

    **文面をそのまま写す方針の中で、ここだけは直す。** トップページを `index` に
    するのはこちらの都合の改名で、**その改名のせいで壊れるリンクは、改名した側が
    直すのが筋**だから。ページの名前の変更（ファイル一覧）が指し元を直すのと同じ
    ことを、同じ道具（`pagerename.fix_links`）で行う。

    取り込み（`sync_wiki`）のあとに呼ぶこと。どのページが指しているかは、
    取り込みで作られる逆リンクの記録から引く。"""
    if not top_page:
        return 0
    from wikilib.pagerename import fix_links
    from wikilib.wikiconfig import load_wiki_config

    # 新しいページパスは "" （トップページ）。`[[TopPage]]` は `[[TopPage>/]]` の
    # ように、見える文字はそのままで指し先だけが変わる
    return len(fix_links(wiki_dir, load_wiki_config(wiki_dir), {top_page: ""}))


def convert(src_name, wiki_name, title="", admin_password="", source_root=None,
            include_system=False, include_stock=False, top_page="",
            theme=DEFAULT_THEME, dry_run=False, log=print):
    """PukiWikiのデータを写して、新しいWikiを作る。(成否, 結果) を返す。

    dry_run=True なら**何も書かずに**、何をどこへ写すかだけを報告する。
    数百ページを一度に動かす操作なので、先に見られるようにしてある。

    top_page は `index` にするページ。省略すると PukiWiki の `$defaultpage`。
    theme は写したWikiで使うテーマ（空文字なら設定に書かず、共通の既定に任せる）。"""
    src = source_dir(src_name, source_root)
    if src is None:
        log(f"変換元「{src_name}」が見つかりません"
            f"（{source_root or DEFAULT_SOURCE_ROOT} の下、または wiki/ を持つディレクトリ）。")
        return False, {}

    problem = validate_name(wiki_name)
    if problem:
        log(problem)
        return False, {}

    pages, skipped_pages = collect_pages(src, include_system, include_stock)
    if not pages:
        log(f"{src} にページがありません。")
        return False, {}
    ini = read_ini(src)
    top = top_page_name(ini, top_page)
    settings, notes = settings_from_ini(ini, title or wiki_name, theme)
    subpaths, renamed, conflicts = plan_subpaths(pages, top)
    attachments, skipped_attach = collect_attachments(src, subpaths)

    # 本文は**書き込む前に**すべて読んでおく。試算でも「このシステムに無い
    # プラグイン」まで見せたいので、読む作業と書く作業を分けてある
    bodies, pointed, semicolons, navi_fixed = {}, 0, 0, 0
    aliases = {}
    for name in sorted(subpaths):
        with open(pages[name], encoding="utf-8", errors="replace") as f:
            text = f.read()
        text, stamp = strip_pukiwiki_header(text)
        # トップページを名前で指していたリンクは、見える文字を残したまま
        # 指し先だけを移す（point_to_top_page）
        text, count = point_to_top_page(text, top if top in subpaths else "")
        pointed += count
        # セミコロンは、名前の置き換え・navi書き換えより先に消す（それぞれの
        # 正規表現が `#name(...)` の直後で終わることを前提にしているため）
        text, count = strip_block_semicolons(text)
        semicolons += count
        text, found = rewrite_plugin_aliases(text)
        for alias_name, alias_count in found.items():
            aliases[alias_name] = aliases.get(alias_name, 0) + alias_count
        text, count = rewrite_navi_home(text, subpaths[name])
        navi_fixed += count
        bodies[name] = (text, parse_stamp(stamp) or os.path.getmtime(pages[name]))

    root = safe_join(WIKIDATA_DIR, wiki_name)
    wiki_dir = os.path.join(root, "wiki")
    texts = [text for text, _ in bodies.values()]
    report = {
        "src": src, "wiki": wiki_name,
        "pages": len(subpaths), "attachments": len(attachments),
        "renamed": renamed, "conflicts": conflicts,
        "skipped_pages": skipped_pages, "skipped_attach": skipped_attach,
        "unknown_plugins": unknown_plugins(texts, wiki_dir),
        "referenced": references_to_renamed(texts, renamed), "seconds": 0.0,
        "top_page": top if top in subpaths else "",
        "settings": settings, "notes": notes, "fixed_links": 0, "pointed": pointed,
        "aliases": aliases, "semicolons": semicolons, "navi_fixed": navi_fixed,
    }
    started = time.perf_counter()

    if dry_run:
        log(f"（試算）{src} → wikidata/{wiki_name}/")
        _log_report(report, log, detail=True)
        return True, report

    ok, message = create_wiki(wiki_name, title or wiki_name,
                              admin_password=admin_password)
    log(message)
    if not ok:
        return False, report

    # 設定は**ページを置く前に**書く。取り込み（sync_wiki）が全ページを1回描くので、
    # そのときにはもう、このWikiの設定（記法・WikiName・メニューのページ名）で
    # 描かれるようにしておく
    with open(os.path.join(root, "config", "default.yaml"), "w", encoding="utf-8") as f:
        f.write(config_text(settings, notes, os.path.basename(src)))

    for name, (text, when) in bodies.items():
        dest = os.path.join(wiki_dir, subpaths[name] + ".txt")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text)
        os.utime(dest, (when, when))

    # 作った直後のWikiに置かれる `mainmenu` は、このシステムの既定のメニュー名。
    # PukiWiki側のメニュー（MenuBar など）を使うことにしたなら、どこからも
    # 参照されない置き土産になるので片づける（写したページに同じ名前があれば残す）
    menu1 = dict((key, value) for _, key, value, _ in settings).get("menu1_page")
    if menu1 and menu1 != "mainmenu" and "mainmenu" not in subpaths.values():
        stub = os.path.join(wiki_dir, "mainmenu.txt")
        if os.path.isfile(stub):
            os.remove(stub)

    attach_root = os.path.join(root, "attach")
    for source, relative, original in attachments:
        dest = os.path.join(attach_root, relative)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(source, dest)

    # 平文を置いただけではDBが空なので、`./wiki.py updatepage` と同じ取り込みを
    # ここで済ませる（モジュール冒頭「最後にすること」）
    from wikilib.pagesync import sync_wiki
    synced = sync_wiki(wiki_dir, force=True, farm=wiki_name)
    report["synced"] = synced
    report["fixed_links"] = fix_top_page_links(wiki_dir, report["top_page"])
    report["seconds"] = time.perf_counter() - started

    log(f"{src} → wikidata/{wiki_name}/")
    _log_report(report, log)
    log(f"  取り込み: 追加 {synced['added']} / 更新 {synced['updated']} "
        f"（{synced['seconds']:.1f}秒）")
    if synced.get("shadowed"):
        log("  読めないページ（同じ名前のフォルダに隠れている）: "
            + ", ".join(synced["shadowed"]))
    log(f"  /={wiki_name}/ で開けます（管理者は admin）。")
    return True, report


def _log_report(report, log, detail=False):
    """報告を人が読む形で出す。件数が0のものは出さない（読む量を増やさないため）。

    detail（試算のとき）では、除外したものを1つずつ並べる。本番の実行では
    件数だけにする——写した結果はWikiを開けば見られるので、行数を増やして
    肝心の「作りました」を埋もれさせないため。"""
    log(f"  ページ {report['pages']} 枚 / 添付 {report['attachments']} 個")
    for name, subpath, reason in report["renamed"]:
        log(f"  名前: {name} → {subpath}（{reason}）")
    for name, reason in report["conflicts"]:
        log(f"  **写しません**: {name}（{reason}）")
    kinds = {}
    for _, reason in report["skipped_pages"] + report["skipped_attach"]:
        kinds[reason] = kinds.get(reason, 0) + 1
    for reason, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
        log(f"  除外: {reason} {count} 件")
    if detail:
        for name, reason in report["skipped_pages"] + report["skipped_attach"]:
            log(f"    除外: {name}（{reason}）")
    for section, key, value, why in report.get("settings", ()):
        log(f"  設定: {section}.{key} = {yaml_value(value)}（{why}）")
    for note in report.get("notes", ()):
        log(f"  引き継げない設定: {note}")
    for name, (subpath, hits) in report["referenced"].items():
        log(f"  本文中の「{name}」{hits} 箇所はトップページ（{subpath}）になりました"
            f"（指していたリンク {report.get('pointed', 0)} 箇所"
            f"＋{report.get('fixed_links', 0)} ページ分を直しました）")
    for name, count in sorted(report.get("aliases", {}).items()):
        log(f"  {name} → {PLUGIN_ALIASES[name]} に書き換え: {count} 箇所")
    if report.get("semicolons"):
        log(f"  ブロックプラグインの誤ったセミコロンを消しました: {report['semicolons']} 箇所")
    if report.get("navi_fixed"):
        log(f"  #navi(ページ名) を #navi(..) に直しました: {report['navi_fixed']} 箇所")
    if report["unknown_plugins"]:
        listed = ", ".join(f"{name}×{count}" for name, count in report["unknown_plugins"][:12])
        log(f"  このシステムに無いプラグイン: {listed}")
