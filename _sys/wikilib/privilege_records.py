"""ページごとのアクセス制限の記録（`wikidata/<Wiki名>/config/privileges`）。

**1行1件のテキスト**（Wiki設計者の指示、2026-09-13）。

    ページ名:種類:許可者,許可者,…:登録日

    ページ名  フルパス（`Tech/Secret`）か、前方一致・後方一致のワイルドカード
    種類      R（閲覧）または W（編集）。**別々に判断し、書けるのは読める人だけ**（2026-09-21）
    許可者    ログインID、または `g:グループ名` を「,」で並べる
    登録日    `yymmdd_hhmmss`（バックアップの差分と同じ形）

    Tech/Secret:R:alice,g:staff:260913_103000
    Tech/*:W:g:editors:260913_103100

**`W` は `R` を含意する**（`W` に書けば読めもする。Wiki設計者の判断、
2026-09-13）。判定は「`R` か `W` に当たれば読める」「`W` に当たれば書ける」の
2つで済む。

**ここは記録の読み書きだけ。** 利用者ごとの判定は `wikilib.auth.page_privilege`
（判定器 `privilege`）が受け持つ。モジュール名は旧 `privileges` から
`privilege_records` に改めた（Wiki設計者の指示、2026-09-14）——`R`（閲覧）の行も
持つので「編集の権限」に限った名前は合わず、判定器の `privilege` とも名前で
見分けがつくため、この名前が中身に合っている。

## なぜテキストなのか

**変えた履歴を、ページと同じ仕組みで残せる**ため（`wikilib.backup` は
テキストの差分をキーごとに積む形をしている）。sqliteだとバイナリなので
その仕組みには乗らない。詳しくは [ページごとの権限](/Tech/PagePermissions)。

書き込みは**一時ファイルへ書いてから `rename`** する。書きかけのファイルが
正本になることを防ぐためで、POSIXの `rename` は原子的に置き換わる。

## 行の読みかた（区切りが値に混ざる）

許可者には `g:staff` のように **`:` を含む値**が入る。そこで、

    左から2つ  ページ名・種類を取る（`split(":", 2)`）
    右から1つ  登録日を取る（`rsplit(":", 1)`）
    残り       許可者

という読みかたにしてある。**ページ名に `:` があると破綻する**ので、
`check_page` で弾く（`:` を含むページ名はURLでも扱いづらく、Windowsでは
ファイル名にも使えないため、実用上の損は小さい）。

読めない行は**捨てて数えるだけ**にする（`load` の戻り値には入らない）。
行が独立しているので、1行壊れても残りは効く。**壊れていたら全部拒否**に
倒すとサイトが開けなくなるので、そうはしない（守りの強度は「見せたくない
ものを隠す」。Wiki設計者の判断、2026-09-13）。

## 一意なのは (ページ名, 種類) の組

同じページ・同じ種類の行は1つだけ持つ。同じ組み合わせで登録し直すと
**上書き**になる（画面の「登録」「確定」がそのまま効く）。

**行が減るのは `delete` だけ。** `put` は足すか上書きするかしかしない
（`put` のdocstring参照）。消えかたが1か所に閉じているので、「登録した
つもりが別の行を消していた」という取り違えが起こらない。

## 画面の単位は「ページ1件」（2026-09-19）

ファイルは (ページ名, 種類) ごとに1行だが、編集画面（`privilegesui`）は
**ページ名を1件として、閲覧（R）の許可者と編集（W）の許可者を並べて**
見せる（Wiki設計者の指示、2026-09-19）。ファイルの形は変えない。画面のための
読み書きが `rows`・`add_page`・`set_page`・`delete_page`。

    rows         ファイルの行を、ページ名ごとの1件（R・Wの許可者）にまとめる
    add_page     新規の入力。**同じページ名が既にあれば古い情報とマージ**（和集合）
    set_page     既存の行の書き換え。**そのページのR・Wを入力のとおりに置き換える**
    delete_page  そのページのR・Wを両方消す

**足すときはマージ、書き換えるときは置き換え**と分けてある。マージだけでは
許可者を外せず、置き換えだけでは、うっかり同じページ名を入れ直したときに
既にいる許可者が黙って消えるため。

**片側を空にすると、その種類の行がファイルから無くなる**（空の許可者の行は
持てない）。同じページに当たるワイルドカードの指定があれば、そちらが効く。
**両方を空にすることはできない**——行ごと消える操作は `delete_page` だけにする、
という前回（2026-09-18）の切り分けをここでも守っているため。

**`version`**: 行の中身が変わると変わる印（R・Wそれぞれの登録日を並べたもの）。
`set_page`・`delete_page` に開いたときの値を渡すと、**開いたあとに別の操作で
変わっていれば断る**。画面を開いたまま放っておいた古い内容で、他の人の
書き換えを踏まないため。
"""
import os
import re
import time

from wikilib.paths import farm_privileges_path

READ = "R"
WRITE = "W"
KINDS = (READ, WRITE)

# ワイルドカードは**前方一致か後方一致のみ**（Wiki設計者の指示、2026-09-13）。
# 途中には入れられない。`Tech/*` と `*/Secret` の2つの形だけを受ける。
WILDCARD = "*"

# 許可者として書ける形。ログインIDは半角英数字（`userdb.UID_RE`）、
# グループ名は半角小文字・数字・ハイフン・アンダースコア（`groups.GNAME_RE`）
WHO_RE = re.compile(r"^(?:[0-9A-Za-z]+|g:[a-z0-9_-]+)$")

STAMP_FMT = "%y%m%d_%H%M%S"


def path_of(wiki_dir):
    return farm_privileges_path(wiki_dir)


# `#readauth`・`#writeauth` が描画のときに書き出す記録（`plugin/_authcommon.py`）。
# パスの決めかたはここに置く——ファイルの形式（1行1件、parse_line/format_line）を
# 共有しているため。書き込み・ロックの作法はプラグイン側の役目のまま
PLUGIN_SUFFIX = ".plugin"


def plugin_path_of(wiki_dir):
    return path_of(wiki_dir) + PLUGIN_SUFFIX


def load_plugin(wiki_dir):
    """プラグインが書き出した記録を読む。`load`と同じ規約（無ければ空、読めない
    行は捨てる）。"""
    try:
        with open(plugin_path_of(wiki_dir), encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    return [e for e in (parse_line(line) for line in lines) if e is not None]


def now_stamp(now=None):
    """登録日の値。バックアップの差分と同じ `yymmdd_hhmmss`。"""
    return time.strftime(STAMP_FMT, time.localtime(now))


def parse_line(line):
    """1行を `{"page","kind","who","stamp"}` にする。読めなければ None。

    読みかたはモジュール冒頭の「行の読みかた」を参照。`who` はリスト。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(":", 2)
    if len(parts) != 3:
        return None
    page, kind, rest = parts
    if kind not in KINDS:
        return None
    who_text, sep, stamp = rest.rpartition(":")
    if not sep:
        # 登録日が無い行（手で書き足したもの）。許可者だけとして読む。
        # **見分けるのは「区切りがあったか」**——`who_text` が空かどうかで
        # 見ると、`Tech/x:R::260913_103000`（許可者が空）を取り違える
        who_text, stamp = rest, ""
    who = [w.strip() for w in who_text.split(",") if w.strip()]
    if not page or not who:
        return None
    if any(not WHO_RE.match(w) for w in who):
        # 許可者として意味を成さない値が混ざっている。**行ごと捨てる**——
        # 誰にも当たらない値を権限として持ち回るより、壊れた行として
        # 数えて知らせるほうがよい（`broken_lines`）
        return None
    return {"page": page, "kind": kind, "who": who, "stamp": stamp}


def format_line(entry):
    """1件を行にする。`parse_line` と対になる。"""
    return "{}:{}:{}:{}".format(
        entry["page"], entry["kind"], ",".join(entry["who"]), entry["stamp"])


def load(wiki_dir):
    """記録を読む。`[{"page","kind","who","stamp"}, …]`。

    ファイルが無ければ空。**読めない行は捨てる**（モジュール冒頭参照）。"""
    try:
        with open(path_of(wiki_dir), encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    return [e for e in (parse_line(line) for line in lines) if e is not None]


def broken_lines(wiki_dir):
    """読めなかった行の数。画面で「壊れている行があります」と知らせるため。"""
    try:
        with open(path_of(wiki_dir), encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return 0
    return sum(1 for line in lines
               if line.strip() and not line.strip().startswith("#")
               and parse_line(line) is None)


HEADER = (
    "# ページごとのアクセス制限。1行1件。\n"
    "#   ページ名:種類:許可者,許可者,…:登録日\n"
    "#   種類は R（閲覧）か W（編集）。R と W は別々に判断し、書けるのは読める人だけです\n"
    "#   許可者はログインIDか g:グループ名\n"
    "# この画面から書き換えられます: /.admin/privileges\n"
)


def save(wiki_dir, entries):
    """記録を丸ごと書き換える。書けたらTrue。

    **一時ファイルへ書いてから `rename`** する（モジュール冒頭参照）。
    並びは「ページ名 → 種類」の順に整えて書く——手で開いたときに読みやすく、
    差分も安定するため（画面の並べ替えはこの順とは別に画面側が行う）。"""
    path = path_of(wiki_dir)
    ordered = sorted(entries, key=lambda e: (e["page"], e["kind"]))
    text = HEADER + "".join(format_line(e) + "\n" for e in ordered)
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def check_page(page):
    """ページ名の指定として使えるか。使えれば None、駄目なら理由を返す。

    **ワイルドカードは前方一致か後方一致のみ**（`Tech/*`・`*/Secret`）。
    途中に入れることはできない。`:` を含む名前は、行の区切りと混ざるため
    受け付けない（モジュール冒頭参照）。"""
    page = (page or "").strip()
    if not page:
        return "ページ名を入力してください。"
    if ":" in page:
        return "ページ名に「:」は使えません（記録の区切りと混ざるため）。"
    if "\n" in page or "\t" in page:
        return "ページ名に改行やタブは使えません。"
    stars = page.count(WILDCARD)
    if stars > 1:
        return "「*」は1つだけ書けます。"
    if stars == 1 and not (page.startswith(WILDCARD) or page.endswith(WILDCARD)):
        return "「*」は先頭か末尾にだけ書けます（途中には入れられません）。"
    if page == WILDCARD:
        return None  # すべてのページ。書けてよい
    return None


def check_who(who_text, known=None):
    """許可者の指定として使えるか。`(リスト, 理由)` を返す（理由が None なら通る）。

    `known` に「実在するログインID・`g:` 付きグループ名」の集合を渡すと、
    **知らない相手を弾く**（Wiki設計者の指示、2026-09-13。「プラグインなどで
    未知のユーザやグループを設定した場合はエラーとする」）。渡さなければ
    形だけを見る。"""
    who = [w.strip() for w in (who_text or "").replace(" ", ",").split(",") if w.strip()]
    if not who:
        return [], "アクセスを許可する相手を入力してください。"
    for w in who:
        if not WHO_RE.match(w):
            return [], f"«{w}» は使えません（ログインIDか g:グループ名）。"
    if known is not None:
        unknown = [w for w in who if w not in known]
        if unknown:
            return [], "«{}» は登録されていません。".format("・".join(unknown))
    # 重複は落とす（同じ相手を2度書いても意味が無い）
    return list(dict.fromkeys(who)), None


def known_principals(wiki_dir):
    """いま実在するログインIDと `g:` 付きグループ名の集合。

    `check_who` に渡して、知らない相手を弾くために使う。記録がまだ無い
    Wikiでは空になる（＝何も登録できない）。"""
    from wikilib import groups, userdb

    names = {u["uid"] for u in userdb.all_users(wiki_dir)}
    try:
        with userdb.connect(wiki_dir) as con:
            names |= {"g:" + r[0] for r in
                      con.execute("SELECT DISTINCT gname FROM group_members")}
    except Exception:
        pass
    # 助手グループは、まだ誰も入っていなくても書けてよい
    names.add("g:" + groups.STAFF_GROUP)
    # 記録に持たない特別なグループ（全ユーザ・誰でも）も書ける
    names.update("g:" + g for g in groups.VIRTUAL_GROUPS)
    return names


def find(entries, page, kind):
    """(ページ名, 種類) で1件を探す。無ければ None。"""
    for e in entries:
        if e["page"] == page and e["kind"] == kind:
            return e
    return None


def put(wiki_dir, page, kind, who_text, now=None):
    """1件を登録（または上書き）する。`(成否, 文言, 一覧)` を返す。

    **(ページ名, 種類) は1件だけ**なので、同じ組み合わせが既にあればそこへ
    上書きし、無ければ足す。画面の「登録」も「確定」もこれで足りる。

    登録日は**書いた時刻**で入れ直す（Wiki設計者の指示、2026-09-13。
    「その内容で登録、上書きします」）。

    **ここは行を増やすか上書きするかしかしない。** 以前は `old_page`/
    `old_kind` で「別の行を置き換える」こともできたが、取り除いた
    （Wiki設計者の指示、2026-09-18）。画面で既存の行を「編集」で開いたまま
    入力欄を別の内容へ打ち直して登録すると、**開いただけの行が黙って
    消えていた**ためで、この作りなら仕組みの上から起こり得ない。行を
    減らすのは `delete`（画面の「削除」）だけにする、という切り分けは
    消えかたを1か所に閉じ込められるので、権限の記録にはこれが合っている。"""
    problem = check_page(page)
    if problem:
        return False, problem, load(wiki_dir)
    if kind not in KINDS:
        return False, "アクセス権の種類を選んでください。", load(wiki_dir)
    who, problem = check_who(who_text, known_principals(wiki_dir))
    if problem:
        return False, problem, load(wiki_dir)

    page = page.strip()
    entries = load(wiki_dir)
    entries = [e for e in entries if not (e["page"] == page and e["kind"] == kind)]
    entry = {"page": page, "kind": kind, "who": who, "stamp": now_stamp(now)}
    entries.append(entry)
    if not save(wiki_dir, entries):
        return False, "書き込めませんでした。", load(wiki_dir)
    return True, "«{}» の{}権限を登録しました。".format(
        page, "閲覧" if kind == READ else "編集"), entries


def delete(wiki_dir, page, kind):
    """1件を消す。`(成否, 文言, 一覧)` を返す。"""
    entries = load(wiki_dir)
    left = [e for e in entries
            if not (e["page"] == page and e["kind"] == kind)]
    if len(left) == len(entries):
        return False, "その記録はありません。", entries
    if not save(wiki_dir, left):
        return False, "書き込めませんでした。", entries
    return True, "«{}» の{}権限を消しました。".format(
        page, "閲覧" if kind == READ else "編集"), left


def rows(entries):
    """ファイルの行を、ページ名ごとの1件にまとめる。並びはページ名順。

    `{"page", "r", "w", "stamp", "version"}`。`r`・`w` は許可者のリスト
    （その種類の行が無ければ空）、`stamp` は新しいほうの登録日。
    手で同じ (ページ名, 種類) を2行書いてあっても、許可者は合わせて数える
    （判定器 `auth.PagePrivilege` も、同じ相手を合わせて見る）。"""
    by_page = {}
    for e in entries:
        row = by_page.setdefault(e["page"], {"page": e["page"], "r": [], "w": [],
                                             "r_stamp": "", "w_stamp": ""})
        key = "r" if e["kind"] == READ else "w"
        row[key] = list(dict.fromkeys(row[key] + e["who"]))
        row[key + "_stamp"] = max(row[key + "_stamp"], e["stamp"])
    out = []
    for page in sorted(by_page):
        row = by_page[page]
        row["stamp"] = max(row["r_stamp"], row["w_stamp"])
        row["version"] = row.pop("r_stamp") + "/" + row.pop("w_stamp")
        out.append(row)
    return out


def load_rows(wiki_dir):
    """画面へ渡す一覧（`rows(load(wiki_dir))`）。"""
    return rows(load(wiki_dir))


def _row_of(entries, page):
    for row in rows(entries):
        if row["page"] == page:
            return row
    return None


def _parse_lists(wiki_dir, r_text, w_text):
    """R・Wの許可者の入力を、それぞれリストにする。`(r, w, 理由)`。

    **片側だけ空でもよい**（空ならその種類の指定をしないこと）。書かれた
    許可者は、実在するログインID・グループだけを通す（`check_who`）。"""
    known = known_principals(wiki_dir)
    lists = []
    for label, text in (("閲覧", r_text), ("編集", w_text)):
        if not (text or "").replace(",", " ").strip():
            lists.append([])
            continue
        who, problem = check_who(text, known)
        if problem:
            return [], [], "{}の許可者: {}".format(label, problem)
        lists.append(who)
    return lists[0], lists[1], None


def _set_kind(entries, page, kind, who, now):
    """1つの (ページ名, 種類) を `who` にする。中身が同じなら何もしない
    （登録日を無駄に新しくしない。バックアップの差分も増えない）。

    `who` が空なら、その種類の行を無くす。"""
    old = []
    for e in entries:
        if e["page"] == page and e["kind"] == kind:
            old += e["who"]
    if set(old) == set(who):
        return entries
    left = [e for e in entries if not (e["page"] == page and e["kind"] == kind)]
    if who:
        left.append({"page": page, "kind": kind, "who": who, "stamp": now_stamp(now)})
    return left


def _label(kind):
    return "閲覧" if kind == READ else "編集"


def add_page(wiki_dir, page, r_text, w_text, now=None):
    """新規の入力。`(成否, 文言, 一覧)`。**同じページ名が既にあれば、古い情報と
    マージする**（許可者の和集合。Wiki設計者の指示、2026-09-19）。

    何を足したかは文言に出す——まとめられたことに気づけないまま、思っていた
    のと違う権限になるのを避けるため。RもWも空なら断る。"""
    problem = check_page(page)
    if problem:
        return False, problem, load_rows(wiki_dir)
    page = page.strip()
    r, w, problem = _parse_lists(wiki_dir, r_text, w_text)
    if problem:
        return False, problem, load_rows(wiki_dir)
    if not (r or w):
        return (False, "閲覧か編集の、どちらかには許可者を入力してください。",
                load_rows(wiki_dir))

    entries = load(wiki_dir)
    before = _row_of(entries, page)
    added = []
    for kind, who in ((READ, r), (WRITE, w)):
        have = before["r" if kind == READ else "w"] if before else []
        new = [x for x in who if x not in have]
        if new:
            entries = _set_kind(entries, page, kind, have + new, now)
            added.append("{}に {}".format(_label(kind), "、".join(new)))
    if not added:
        return True, "«{}» には、同じ許可者が登録済みです（変更なし）。".format(page), \
            load_rows(wiki_dir)
    if not save(wiki_dir, entries):
        return False, "書き込めませんでした。", load_rows(wiki_dir)
    if before is None:
        message = "«{}» を登録しました。".format(page)
    else:
        message = "«{}» は登録済みだったので、古い情報とまとめました（追加: {}）。".format(
            page, " ／ ".join(added))
    return True, message, rows(entries)


def set_page(wiki_dir, page, r_text, w_text, version=None, now=None):
    """既存の行の書き換え。`(成否, 文言, 一覧)`。そのページのR・Wを、入力の
    とおりに**置き換える**（許可者を外せる）。

    **無い行は作らない**（別の操作で消えた行を、古い画面から生き返らせない）。
    `version` を渡すと、開いたあとに変わっていれば断る（モジュール冒頭参照）。
    RもWも空にはできない——行ごと消すのは `delete_page`。"""
    page = (page or "").strip()
    r, w, problem = _parse_lists(wiki_dir, r_text, w_text)
    if problem:
        return False, problem, load_rows(wiki_dir)
    if not (r or w):
        return (False, "閲覧と編集の両方を空にはできません。"
                       "記録を消すときは、一覧の「削除」を使ってください。",
                load_rows(wiki_dir))

    entries = load(wiki_dir)
    row = _row_of(entries, page)
    if row is None:
        return False, "«{}» の行はありません（別の操作で消えたかもしれません）。".format(page), \
            load_rows(wiki_dir)
    if version is not None and version != row["version"]:
        return (False, "«{}» は、開いたあとに別の操作で書き換わっています。"
                       "いまの内容を読み込み直しました。".format(page), rows(entries))
    entries = _set_kind(entries, page, READ, r, now)
    entries = _set_kind(entries, page, WRITE, w, now)
    if _row_of(entries, page) == row:
        return True, "«{}» に変更はありませんでした。".format(page), rows(entries)
    if not save(wiki_dir, entries):
        return False, "書き込めませんでした。", load_rows(wiki_dir)
    return True, "«{}» を書き換えました。".format(page), rows(entries)


def delete_page(wiki_dir, page, version=None):
    """そのページのR・Wを両方消す。`(成否, 文言, 一覧)`。

    `version` は `set_page` と同じ（開いたあとに変わった行は消さない）。"""
    page = (page or "").strip()
    entries = load(wiki_dir)
    row = _row_of(entries, page)
    if row is None:
        return False, "その記録はありません。", rows(entries)
    if version is not None and version != row["version"]:
        return (False, "«{}» は、開いたあとに別の操作で書き換わっています。"
                       "いまの内容を読み込み直しました。".format(page), rows(entries))
    left = [e for e in entries if e["page"] != page]
    if not save(wiki_dir, left):
        return False, "書き込めませんでした。", rows(entries)
    return True, "«{}» の記録を消しました。".format(page), rows(left)


def matches(page_rule, pagepath):
    """そのページ名の指定が、このページに当たるか。

    **前方一致か後方一致のワイルドカード**だけを見る（`check_page` が
    それ以外を通さない）。`*` だけならすべてのページに当たる。

    **`Tech/*` は、`Tech` 自身にも当たる**（Wiki設計者の指示、2026-09-21）。フォルダの
    入口ページ（`Tech/index`）は `Tech` という単体のページとして扱われるので、
    `Tech/` から始まるページだけを見ていると、`Tech/*` で閉じたはずのフォルダの入口が
    開いたままになる。**`Tech` だけ別に決めたいときは、完全一致の行（`Tech`）を書く**——
    完全一致はワイルドカードより常に上なので、`Tech/*` を上書きできる。
    `Tech*`（`/` の無い前方一致）はこれまでどおり、`Tech` で始まる名前すべてに当たる。"""
    if page_rule == WILDCARD:
        return True
    if page_rule.endswith(WILDCARD):
        literal = page_rule[:-1]
        return pagepath.startswith(literal) or (
            literal.endswith("/") and pagepath == literal[:-1])
    if page_rule.startswith(WILDCARD):
        return pagepath.endswith(page_rule[1:])
    return pagepath == page_rule


# ---- 改名に合わせた付け替え（pagerename から呼ぶ） ------------------------------
#
# ページ（またはフォルダ）の名前が変わったら、**手で書く記録（config/privileges）も、
# `#readauth`・`#writeauth` の記録（config/privileges.plugin）も、同じく新しい名前へ
# 付け替える**（Wiki設計者の指示、2026-09-25）。付け替えないと、制限は古い名前に
# 残り、**新しい名前のページは誰でも読める**（プラグインの記録は描けば作り直されるが、
# 表示は判定が先・描画が後なので、最初に開いた人には本文が見える）。
#
# 付け替えるのは、**改名するページとその配下だけを指す行**:
#
#     Tech/Foo        （完全一致）          → New/Foo
#     Tech/Foo/Kid    （配下の完全一致）    → New/Foo/Kid
#     Tech/Foo/*      （配下の前方一致）    → New/Foo/*
#
# `Tech*`（`/` の無い前方一致）・`*/Foo`（後方一致）・`*` は、改名するページ以外にも
# 当たるので書き換えない。改名でそういう指定の範囲から出入りしたページは、移し先の
# 規則に従う（ファイルを別のフォルダへ移したときと同じ）。出た先で緩くなることは
# あるが、改名には動くページすべての W が要る（pagerename.unwritable_pages）ので、
# その人は元々本文を読んで写せる。改名で新しくできることは増えない。
#
# **どの瞬間にも、制限が外れた状態を作らない**ため、2段に分ける。
#
#     1. copy_for_rename      新しい名前の行を足す（古い名前の行も残す）
#        ――ページの実体を動かす――
#     2. finish_rename(True)  古い名前の行を消す
#        finish_rename(False) 動かせなかった。足した行を消して元に戻す
#
# 移し先に、**手で書いた同じ (ページ名, 種類) の行が既にあれば改名を断る**
# （rename_conflicts）。どちらを残しても、黙って決めると緩くなる向きがありうるため。
# プラグインの記録は描画のたびに作り直されるものなので、移し先の配下に残って
# いる行は、前にそこにあったページの残り物として消す。
#
# プラグインの記録ファイルは、プラグイン（plugin/_authcommon.py）と同じく
# `<記録>.lock` の flock で囲んで書き換える（描画と同時に走りうるため）。


def renamed_rule(page, old_root, new_root):
    """ページ名の指定 `page` を、`old_root` → `new_root` の改名に合わせて直した値。
    改名に関係しない指定なら None。"""
    if not old_root:
        return None  # トップ（空のページパス）は改名の対象にならない
    if page == old_root:
        return new_root
    if page.startswith(old_root + "/"):
        return new_root + page[len(old_root):]
    return None


def rename_conflicts(wiki_dir, old_root, new_root):
    """付け替えると、移し先に手で書いた行とぶつかる (ページ名, 種類) の一覧。"""
    entries = load(wiki_dir)
    have = {(e["page"], e["kind"]) for e in entries}
    moving = {(e["page"], e["kind"]) for e in entries
              if renamed_rule(e["page"], old_root, new_root) is not None}
    out = []
    for page, kind in sorted(moving):
        target = (renamed_rule(page, old_root, new_root), kind)
        if target in have and target not in moving:
            out.append(target)
    return out


def _copies(entries, old_root, new_root):
    return [dict(e, page=renamed_rule(e["page"], old_root, new_root)) for e in entries
            if renamed_rule(e["page"], old_root, new_root) is not None]


def _in_tree(page, root):
    return page == root or page.startswith(root + "/")


def rewrite_plugin_records(wiki_dir, change):
    """プラグインの記録を `change(entries)` の結果に書き換える。ファイルが無ければ
    何もしない。先頭の説明（`#` の行）は残す。書けなければ False。"""
    path = plugin_path_of(wiki_dir)
    if not os.path.exists(path):
        return True
    try:
        import fcntl
    except ImportError:  # Windowsなど。ロック無しで書く（プラグイン側と同じ扱い）
        fcntl = None
    try:
        with open(path + ".lock", "a") as lock:
            if fcntl is not None:
                fcntl.flock(lock, fcntl.LOCK_EX)
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            header = []
            for line in lines:
                if line.strip() and not line.startswith("#"):
                    break
                header.append(line)
            entries = [e for e in (parse_line(line) for line in lines) if e is not None]
            changed = change(entries)
            if changed == entries:
                return True
            ordered = sorted(changed, key=lambda e: (e["page"], e["kind"]))
            text = "".join(header) + "".join(format_line(e) + "\n" for e in ordered)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)
    except OSError:
        return False
    return True


def copy_for_rename(wiki_dir, old_root, new_root):
    """改名の1段目。新しい名前の行を足す（古い名前の行は残す）。書けたらTrue。"""
    entries = load(wiki_dir)
    copies = _copies(entries, old_root, new_root)
    if copies:
        taken = {(c["page"], c["kind"]) for c in copies}
        kept = [e for e in entries if (e["page"], e["kind"]) not in taken]
        if not save(wiki_dir, kept + copies):
            return False

    def change(plugin_entries):
        # 移し先の配下に残っていた行は、前にそこにあったページの残り物
        kept = [e for e in plugin_entries if not _in_tree(e["page"], new_root)]
        return kept + _copies(plugin_entries, old_root, new_root)
    return rewrite_plugin_records(wiki_dir, change)


def finish_rename(wiki_dir, old_root, new_root, moved):
    """改名の2段目。動かせたら（`moved`）古い名前の行を、動かせなかったら
    1段目で足した行を消す。書けたらTrue。"""
    def change(entries):
        if moved:
            return [e for e in entries
                    if renamed_rule(e["page"], old_root, new_root) is None]
        # 足した行は「古い名前の行を付け替えた先」にあるもの
        added = {(c["page"], c["kind"]) for c in _copies(entries, old_root, new_root)}
        return [e for e in entries if (e["page"], e["kind"]) not in added]

    entries = load(wiki_dir)
    left = change(entries)
    ok = left == entries or save(wiki_dir, left)
    return rewrite_plugin_records(wiki_dir, change) and ok
