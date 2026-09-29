"""readauth / writeauth が共有する処理。

`_`で始まるファイルはプラグインとしては読み込まれない（`plugin/README.txt`）。
`readauth.py`・`writeauth.py`が、自分の隣にあるこのファイルを`importlib`で
読み込んで使う（プラグインは`spec_from_file_location`で個別に読み込まれるので、
兄弟モジュールを`import`では引けない）。読み込みは呼び出しのたびに行い、
`sys.modules`には置かない（置くと、このファイルを直してもサーバーを再起動する
までプラグイン本体だけ新しく、ここだけ古いままになるため）。

    common = _load_common()                       # 各プラグインの関数
    return common.run("readauth", "R", resolved, context)

2つのプラグインは、**種類（`R`＝閲覧・`W`＝閲覧と編集）と名前だけが違う**。
やることは次の2つ（Wiki設計者の指示、2026-09-21）。

1. **`config/privileges.plugin`への記録**（`register`）。表示を止めるなどの
   処理はプラグインではしない。**記録を読んで実際に止めるのは本体**で、
   手で書く`config/privileges`と同じ扱いで参照される
2. **先頭行への寄せ**（`normalize_auth_lines`）。「一番上にだけ置ける」という
   決めごと。途中に書かれていれば消して先頭へ移す

## 記録（`config/privileges.plugin`）

形式は`config/privileges`と同じ1行1件（`ページ名:種類:許可者,許可者,…:登録日`。
`wikilib.privilege_records`の`parse_line`/`format_line`をそのまま使う）。
**手で書く`privileges`とは別のファイル**に持つ。同じ（ページ名, 種類）を
プラグインが上書きして、手で登録した行を消してしまわないため。

- **ページ名は、このプラグインが置かれたページ**（`context.page`）。ワイルドカード
  は含まない（ページ名に`*`があれば断る。行の読みかたで範囲指定に化けるため）
- **許可者は、実在するログインIDか`g:グループ名`**（`check_who`に
  `known_principals`を渡す。設計者の決めごと「未知のユーザ・グループを指定した
  ときはエラー」）。実在しない名前は`PluginArgumentError`にする。存在しない
  グループ名を書いておくと、後からその名前でグループを作った相手に権限が
  渡ってしまうため
- **(ページ名, 種類)は1件だけ**。同じ内容ならファイルに触らない（登録日を
  描画のたびに書き換えない）。許可者が変わっていれば上書きし、登録日を入れ直す
- **書き込みは`.lock`ファイルの`flock`で囲み**、一時ファイルへ書いてから
  `rename`する（描画は同時に何本も走るので、読み書きの取り違えを防ぐ。
  `privilege_records.save`と同じ`rename`の方式）
- **部分プレビュー（`context.partial`）では書かない。** 保存前の、編集中の
  内容で権限が書き換わってしまうため。書き込みの検査（許可者の実在）は
  プレビューでも行い、書きかたの誤りは編集中に分かる
- **実在するページの描画でだけ書く**（`resolve_page_ref`で確かめる）。バックアップ
  管理など、ページ名が実ページでない画面の描画では書かない
- **同じ種類が同じページに複数あれば、最初の1つだけ**を記録する（あとのものは
  本文からも消える）。1回の描画で最初に処理したものだけが効くよう、
  `context._auth_seen`に処理した種類を覚える

## 記録の消しかた: 空呼びしてから、プラグインの行を消す（Wiki設計者の指示、2026-09-21）

記録を作るのは`_convert`が呼ばれたとき（描画のとき）で、**プラグインの行を
本文から消したページでは`_convert`が呼ばれない**ため、行を消すだけでは記録が
残る（制限を外したつもりで残る。厳しい側に倒れる）。そこで消しかたを2段にした。

1. **許可者を書かずに呼ぶ（空呼び。`#readauth()`）と、そのページのその種類の記録を
   削除する**（`unregister`）。エラーにはしない
2. そのあと、**プラグインの行自体を本文から消す**

1を飛ばして行だけ消すと、記録は残る。**これは本体が後始末する**
（`wikilib.updatepageauth`。1時間ごとと`/.updatePageAuth`で、ページを描いて
このプラグインが呼ばれなかった記録を消す。ページが削除された記録も同じ）。
空呼びも「同じ種類は最初の1つだけ」の対象で、プレビューでは削除しない
（保存前の内容で記録が消えないように）。**改名に伴う付け替えも本体が行う**
（`wikilib.privilege_records.copy_for_rename`・`finish_rename`。同じ`.lock`の
`flock`で囲んで書き換える。`updatepageauth`も同じ。ここのロックの作法を変える
ときは合わせること）。

## 先頭行への寄せ

### 決めごと（Wiki設計者の指示、2026-09-21）

- `#readauth(...)`・`#writeauth(...)`は**ページの一番上にだけ**置ける
- 途中に書いてあれば、その記述を**削除して先頭行へ移す**
- **Markdown（`.md`）でタイトル行（先頭の`# 見出し`）があれば、その直下へ置く**
  （Wiki設計者の指示、2026-09-21。下記「タイトル行の直下」）
- 両方あれば **readauth → writeauth** の順に並べる
- 同じ名前が複数あれば、**最初に出てきた1つだけを残す**（あとのものは消す）

### タイトル行の直下（`.md`のみ）

`wikilib.render.split_title`は**先頭のブロックが`# 見出し`のときだけ**それを
ページのタイトルとして取り出す。`.md`の1行目にプラグインを置くと、見出しが
2番目のブロックになって**取り出されず、本文に残って題名がページ名になる**
（実測。`#hr`のような出力の無いプラグインでも同じ）。プラグイン側では
`split_title`を直せないので、**タイトル行があれば、その次の行へ置く**ことで避ける。

- **タイトル行**は、本文の**最初の空でない行**が、ATXのh1（`# `＋文字列。`##`は
  含まない）か、次の行が`===`だけのsetext形式のh1のとき。空行は読み飛ばす
  （空行はブロックを作らないので、`split_title`の判定でも先頭のまま）
- タイトル行が**ない**（本文が別の書き出し・空）なら、これまでどおり先頭行
- PukiWiki記法（`.txt`）は先頭見出しの取り出しをしないので、常に先頭行
- 「タイトル行」かどうかは、**呼び出しを除いた本文**で見る（先頭に呼び出しがあって
  その次にタイトル行、という今までの置きかたのページも、直下へ直る）
- `markdown.first_h1_as_title`が無効でも同じ位置に置く（直下に置いても害は無く、
  設定を見に行かずに済むため）

### 何を「呼び出し」とみなすか

生の本文を1行ずつ見て、**行頭から書かれた** `#name(...)` だけを探す
（`plugin/vote.py`の`_find_vote_line`と同じ、字面を見る方式）。ただし次は
呼び出しとして数えない。プラグインの説明ページなどが、書きかたの例として
`#readauth(...)` を載せているだけのことがあるため。

- Markdownの囲みコード（バッククォート3つ・`~~~`）の中（`.md`のみ。PukiWiki記法に
  囲みコードは無い）
- **他のプラグインの複数行の本体（`#code{{ ... }}`）の中**。閉じは
  `wikilib.plugins.plugin_block_rule`と同じ「開いた`{`と同じ数以上の`}`だけの行」
- 行頭でない書きかた（リストや引用の中に字下げして置いたもの）

`{{ ... }}`本体つきで書かれていれば、移すときは**開きの行から閉じの行までを
1かたまりとして**動かす（本体は今は使われないが、消さずに残す）。

### 落とし穴

- **複数行の本体が閉じられていなければ、開きの1行だけを呼び出しとして扱う**
  （`plugin_block_rule`も、閉じが無いときは開きの1行だけを消費して本体の
  エラーにする）。あとの行を巻き込んで動かさない
- **除いた跡の空行が連続しないようにする**。前後がどちらも空行なら、片方を
  詰める（空行が増え続けて本文が汚れるのを防ぐ）
- 保存済みの本文を書き換えるのは**部分プレビューでないときだけ**（プレビューは
  編集中の未保存のテキストを描くので、その最中に書き換えると編集画面の元の
  内容とずれ、次の保存が競合になる）。1回の描画につき1ページ1度だけ行う
  （`context._auth_normalized`）
- 書き換えた描画自体は、書き換える前の本文から始まっている。整った本文は
  次に開いたときから。記録は位置に関係なく同じ内容になるので影響しない
"""
import os
import re

from wikilib import privilege_records
from wikilib.pagedb import resolve_page_ref
from wikilib.pagesave import save_page
from wikilib.plugins import (PLUGIN_BLOCK_FENCE_RE, PluginArgumentError,
                             match_plugin_block)
from wikilib.render import is_pukiwiki

try:
    import fcntl
except ImportError:  # Windowsなど。ロック無しで動く（書き込みの取り違えは起こりうる）
    fcntl = None

# 先頭に並べる順（read → write）。この名前の呼び出しだけを整理の対象にする
AUTH_PLUGINS = ("readauth", "writeauth")

RECORD_HEADER = (
    "# ページの中の #readauth・#writeauth が、描画のときに書き出す記録。1行1件。\n"
    "#   ページ名:種類:許可者,許可者,…:登録日\n"
    "#   種類は R（閲覧）か W（閲覧・編集）。ページ名は、そのプラグインが書かれたページ\n"
    "# 手で書く記録は config/privileges にあります（/.admin/privileges）。\n"
    "# ここは書き換えても、そのページが次に描画されたときにプラグインが書き直します\n"
)

_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# タイトル行（h1）。ATXは「#」のあとが空白か行末（`#readauth(`や`##`は含まない）。
# setextは、次の行が「=」だけ
_ATX_H1_RE = re.compile(r"^ {0,3}#(?:[ \t].*)?$")
_SETEXT_H1_UNDERLINE_RE = re.compile(r"^ {0,3}=+[ \t]*$")


# ---- 先頭行への寄せ ---------------------------------------------------------

def _fence_close_re(fence):
    return re.compile(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")


def find_auth_blocks(lines, ext):
    """`AUTH_PLUGINS`の呼び出しを [(名前, 開始行, 終了行)] で返す（終了行は含まない）。

    出てきた順。囲みコードと、他のプラグインの複数行の本体の中は見ない。"""
    blocks = []
    md = not is_pukiwiki(ext)
    fence_close = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if md:
            if fence_close is not None:
                if fence_close.match(line):
                    fence_close = None
                i += 1
                continue
            m = _FENCE_OPEN_RE.match(line)
            if m:
                fence_close = _fence_close_re(m.group(1))
                i += 1
                continue

        parsed = match_plugin_block(line)
        if not parsed:
            i += 1
            continue

        end = i + 1
        fence_m = PLUGIN_BLOCK_FENCE_RE.fullmatch(parsed[2].rstrip())
        if fence_m:
            close_re = re.compile(r"^\}{" + str(len(fence_m.group(1))) + r",}\s*$")
            j = i + 1
            while j < len(lines) and not close_re.match(lines[j]):
                j += 1
            if j < len(lines):
                end = j + 1  # 閉じが見つからなければ開きの1行だけ（落とし穴参照）
        if parsed[0] in AUTH_PLUGINS:
            blocks.append((parsed[0], i, end))
        i = end
    return blocks


def _title_end(lines):
    """`.md`のタイトル行の次の行の位置。タイトル行が無ければ0（先頭）。

    最初の空でない行がh1なら、その行（setextなら下線の行）の次を返す。"""
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines):
        return 0
    if _ATX_H1_RE.match(lines[i]):
        return i + 1
    if i + 1 < len(lines) and lines[i].strip() and _SETEXT_H1_UNDERLINE_RE.match(lines[i + 1]):
        return i + 2
    return 0


def normalize_auth_lines(text, ext):
    """`AUTH_PLUGINS`の呼び出しを先頭（`.md`でタイトル行があればその直下）へ
    寄せた本文を返す。すでに整っていれば`text`そのもの（`is`で比べられる）を返す。"""
    lines = text.split("\n")
    blocks = find_auth_blocks(lines, ext)
    if not blocks:
        return text

    first = {}
    for name, start, end in blocks:
        first.setdefault(name, (start, end))
    head = []
    for name in AUTH_PLUGINS:
        if name in first:
            start, end = first[name]
            head.extend(lines[start:end])

    dropped = set()
    for _name, start, end in blocks:
        dropped.update(range(start, end))
    rest = []
    k = 0
    while k < len(lines):
        if k not in dropped:
            rest.append(lines[k])
            k += 1
            continue
        while k in dropped:
            k += 1
        # 除いた跡の前後がどちらも空行なら片方を詰める
        if rest and rest[-1].strip() == "" and k < len(lines) and lines[k].strip() == "":
            k += 1

    # `.md`でタイトル行があれば、その直下へ（`split_title`がタイトルを取り出せるように）
    at = 0 if is_pukiwiki(ext) else _title_end(rest)
    new_text = "\n".join(rest[:at] + head + rest[at:])
    return text if new_text == text else new_text


def _normalize_saved_page(context):
    """保存済みの本文で、`#readauth`/`#writeauth`を先頭へ寄せる。

    1回の描画につき1ページ1度だけ。部分プレビューでは何もしない。"""
    if context.partial or not context.wiki_dir or not context.page:
        return
    done = getattr(context, "_auth_normalized", None)
    if done is None:
        done = context._auth_normalized = set()
    if context.page in done:
        return
    done.add(context.page)

    ref = resolve_page_ref(context.wiki_dir, context.page)
    if ref is None or not ref.exists:
        return
    source = ref.body or ""
    new_source = normalize_auth_lines(source, ref.ext)
    if new_source != source:
        save_page(context.wiki_dir, context.config, ref.subpath, ref.ext, new_source)


# ---- 記録（config/privileges.plugin）-----------------------------------------

def records_path(wiki_dir):
    return privilege_records.plugin_path_of(wiki_dir)


def load_records(path):
    """記録を読む。`[{"page","kind","who","stamp"}, …]`。読めない行は捨てる。"""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    return [e for e in (privilege_records.parse_line(line) for line in lines) if e]


def _write_records(path, entries):
    ordered = sorted(entries, key=lambda e: (e["page"], e["kind"]))
    text = RECORD_HEADER + "".join(privilege_records.format_line(e) + "\n" for e in ordered)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def register(wiki_dir, page, kind, who, now=None):
    """(ページ名, 種類)の記録を、`who`の内容にする。書き換えたらTrue、
    すでに同じ内容ならファイルに触らずFalse。書けなければ`OSError`。

    許可者の並びだけが違うときは同じ内容として扱う（権限は変わらないので）。"""
    path = records_path(wiki_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "a") as lock:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        entries = load_records(path)
        current = privilege_records.find(entries, page, kind)
        if current is not None and set(current["who"]) == set(who):
            return False
        entries = [e for e in entries if e is not current]
        entries.append({"page": page, "kind": kind, "who": list(who),
                        "stamp": privilege_records.now_stamp(now)})
        _write_records(path, entries)
    return True


def unregister(wiki_dir, page, kind):
    """(ページ名, 種類)の記録を消す。消したらTrue、もともと無ければファイルに
    触らずFalse。書けなければ`OSError`。"""
    path = records_path(wiki_dir)
    if not os.path.exists(path):
        return False
    with open(path + ".lock", "a") as lock:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        entries = load_records(path)
        current = privilege_records.find(entries, page, kind)
        if current is None:
            return False
        _write_records(path, [e for e in entries if e is not current])
    return True


def _parse_users(name, raw, wiki_dir):
    """`users`を許可者のリストにする。空（空呼び）ならNone（記録を消す合図）。
    使えなければ`PluginArgumentError`。"""
    users = [u.strip() for u in (raw or "").split(",") if u.strip()]
    if not users:
        return None
    who, problem = privilege_records.check_who(
        ",".join(users), privilege_records.known_principals(wiki_dir))
    if problem:
        raise PluginArgumentError(f"{name}: {problem}")
    return who


def run(name, kind, resolved, context):
    """`readauth`/`writeauth`の`_convert`の中身。出力は無い（空文字列を返す）。

    許可者が空（空呼び）なら、そのページのその種類の記録を消す。"""
    _normalize_saved_page(context)
    who = _parse_users(name, resolved["users"], context.wiki_dir)

    # この描画で、同じ種類の最初の1つだけが効く（本文からも、あとのものは消える）
    seen = getattr(context, "_auth_seen", None)
    if seen is None:
        seen = context._auth_seen = set()
    if kind in seen:
        return ""
    seen.add(kind)

    if context.partial or not context.wiki_dir or not context.page:
        return ""
    page = context.page.strip("/")
    ref = resolve_page_ref(context.wiki_dir, page)
    if ref is None or not ref.exists:
        return ""  # 実在するページの描画でだけ書く
    if privilege_records.WILDCARD in page:
        raise PluginArgumentError(
            f"{name}: 「*」を含むページ名には権限を記録できません"
            "（記録の中でワイルドカードと区別が付かないため）。")
    problem = privilege_records.check_page(page)
    if problem:
        raise PluginArgumentError(f"{name}: {problem}")
    try:
        if who is None:
            unregister(context.wiki_dir, page, kind)  # 空呼び: 記録を消す
        else:
            register(context.wiki_dir, page, kind, who)
    except OSError:
        raise PluginArgumentError(
            f"{name}: アクセス権の記録（config/privileges.plugin）を書き込めませんでした。"
            "このままでは制限が効きません。")
    return ""
