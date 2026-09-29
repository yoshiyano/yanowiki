"""ある時点（"YYMMDD-HHMMSS"）のWikiの姿を、保存時の差分から組み立てる。

ロードマップの「Wiki全体をある時点まで戻して見る」の下回りで、**内部処理専用**
（URLは付けていない。アクセス権も見ない。呼ぶ側が確かめる）。

    page_text_at(wiki_dir, "/foo/bar", when)     その時点の /foo/bar の本文
    folder_entries_at(wiki_dir, "foo", when)     その時点の foo/ 直下の一覧
    subpath_text_at(wiki_dir, "foo/bar", when)   実体パスで引く版

対象はページだけ。添付ファイルは履歴を残していないので扱わない。

## 組み立てかた

差分（wikilib.backup）は「上書き前 → 上書き後」なので、**いまの公開内容（DB）に、
その時点より新しい記録だけを新しい順に逆適用**すれば、その時点の内容になる。
起点が平文ではなくDBなのは backupui._current_text と同じ理由（差分はDBの内容を
基準に記録されている）。

内容が空（空白だけを含む）なら「その時点にそのページは無かった」とみなす。

- **いまは消えたページも出る。** 削除は「内容 → 空」の記録として残るので
  （pagesave.remove_page）、記録だけが残っている名前も候補に入れる
- **その時点にまだ作られていないページは出ない**（最古の記録が「空 → 内容」）
- **改名・移動したページは、その時点の名前で出る。** 差分の記録は改名のときに
  新しい名前へ付け替えられるので（backup.move_backups）、同じときに残す改名の
  記録（backup の moves 表）を新しい順にさかのぼって、当時の名前に戻す

## 分からないこと

- **10分以内の続けた保存は1本にまとめられている**（backup.backup_page）。
  その途中の時刻を指しても、まとめた記録の「前」の内容になる
- 改名の記録は 2026-09-28 から残している。それより前の改名は、いまの名前で出る
- 消したページの名前へ、あとから別のページを改名で移した場合、2つの記録が同じ
  名前の下に混ざる（move_backups）。差分がつながらなくなれば None になる
- 容量の上限で古い記録が消えている、あるいは記録が始まる前からあるページでは、
  その時点が残っている記録より前だと正確には分からない。そのときは**残っている
  うちで最も古い内容**を返す（`exact` が False になる）
- 差分が当たらなくなっていれば、在ったかどうか分からないものとして扱う
"""
import datetime
import re
import sqlite3

from wikilib import backup, pagedb
from wikilib.paths import BACKUP_STAMP, INDEX_NAME, pagepath_of_subpath

WHEN_RE = re.compile(r"^(\d{6})[-_](\d{6})$")


def stamp_of_when(when):
    """時点を、差分の記録と比べられる "yymmdd_hhmmss" にそろえる。

    "YYMMDD-HHMMSS"・"YYMMDD_HHMMSS"（記録の書式そのまま）・datetime を受け付ける。
    書式が違えば ValueError。"""
    if isinstance(when, datetime.datetime):
        return when.strftime(BACKUP_STAMP)
    m = WHEN_RE.match(when or "")
    if m is None:
        raise ValueError(f"時点の書式が違います（YYMMDD-HHMMSS）: {when!r}")
    stamp = f"{m.group(1)}_{m.group(2)}"
    datetime.datetime.strptime(stamp, BACKUP_STAMP)  # 13月などを弾く
    return stamp


# ---- 改名をさかのぼる -------------------------------------------------------

def _moves_after(wiki_dir, stamp):
    """その時点より後の改名を、新しい順に [(old, new)] で返す。"""
    with backup.connect(wiki_dir) as con:
        return [(r["old_subpath"], r["new_subpath"]) for r in con.execute(
            "SELECT old_subpath, new_subpath FROM moves WHERE stamp > ?"
            " ORDER BY stamp DESC, rowid DESC", (stamp,))]


def _name_at(key, moves):
    """いま key の下に記録があるページの、その時点の名前。

    改名を新しい順にさかのぼり、key に移ってきたものなら移る前の名前に戻す。
    途中で**その名前から出ていった**改名に当たったら None を返す。そこより前に
    その名前にいたのは別のページで、key のページはまだその名前にいなかった
    （改名先は空いていなければならないので、それより前は作られてもいない）。
    その別のページの記録は、出ていった先の名前の下にある。"""
    name = key
    for old, new in moves:
        if new == name:
            name = old
        elif old == name:
            return None
    return name


# ---- 1ページ分を組み立てる --------------------------------------------------

def _created_after(created, stamp):
    """DBの初回登録日時（"YYYY-mm-dd HH:MM:SS"）がその時点より後か。"""
    try:
        at = datetime.datetime.strptime(created, pagedb.TIME_FORMAT)
    except (TypeError, ValueError):
        return False
    return at.strftime(BACKUP_STAMP) > stamp


def _state_at(current, created, newer_diffs, has_older, stamp):
    """1ページ分を組み立てる。(本文, exact) を返す。さかのぼれなければ (None, False)。

    current      いまの公開内容（無ければ空文字列）
    created      DBの初回登録日時（DBに無ければ None）
    newer_diffs  その時点より新しい記録の差分（古い順）
    has_older    その時点以前の記録があるか"""
    text = current
    for diff in reversed(newer_diffs):
        text = backup.reverse_diff(text, diff)
        if text is None:
            return None, False
    if has_older:
        return text, True   # その時点以前の保存の「後」の内容そのもの
    if not text.strip():
        return text, True   # 最古の記録が新規作成＝その時点にはまだ無かった
    if not newer_diffs and created is not None:
        # 記録が1本も無いページ（履歴が付く前からある・直接置いたもの）は、
        # DBに入った日時がその時点より後なら、まだ無かったとみなす。
        # 前なら、入って以来一度も変わっていないので、いまの内容がそのまま当時の内容
        return ("", True) if _created_after(created, stamp) else (text, True)
    # 記録が残っているより前の時点。残っているうちで最も古い内容を返す
    return text, False


def _load(wiki_dir, stamp, subpaths=(), prefix=None):
    """組み立てに要るものを、いまの名前（key）ごとにまとめて引く。

    subpaths で名前を列挙し、prefix（"foo/" の形。"" でWiki全体）でその下を
    まとめて足す。{key: (current, created, newer_diffs, has_older)} を返す。
    いまも在るページと、記録だけが残っている（消えた）ページの両方が入る。"""
    conds, args = [], []
    subpaths = sorted(set(subpaths))
    if subpaths:
        conds.append(f"subpath IN ({','.join('?' * len(subpaths))})")
        args += subpaths
    if prefix is not None:
        # pagedb.page_entries と同じ範囲の切りかた（主キーの索引が効く）
        conds.append("(subpath >= ? AND subpath < ?)")
        args += [prefix, prefix + "￿"]
    if not conds:
        return {}
    where, args = "(" + " OR ".join(conds) + ")", tuple(args)

    pages = {}
    try:
        with pagedb.connect(wiki_dir) as con:
            for r in con.execute(
                    f"SELECT subpath, body, created FROM pages WHERE {where}", args):
                pages[r["subpath"]] = (r["body"], r["created"])
    except sqlite3.Error:
        pass

    newer, older = {}, set()
    with backup.connect(wiki_dir) as con:
        for r in con.execute(
                f"SELECT subpath, diff FROM backup WHERE {where} AND stamp > ?"
                " ORDER BY subpath, stamp", args + (stamp,)):
            newer.setdefault(r["subpath"], []).append(r["diff"])
        for r in con.execute(
                f"SELECT DISTINCT subpath FROM backup WHERE {where} AND stamp <= ?",
                args + (stamp,)):
            older.add(r["subpath"])

    out = {}
    for key in set(pages) | set(newer) | older:
        current, created = pages.get(key, ("", None))
        out[key] = (current, created, newer.get(key, []), key in older)
    return out


def _pages_at(wiki_dir, stamp, name=None, prefix=None):
    """その時点に在ったページを {当時の名前: (本文, exact)} で返す。

    name を渡せばその1つだけ、prefix（"foo/" の形）を渡せばその下を探す。
    いまの名前が違っても、当時そこにいたページを拾う（改名の記録の新しい側を
    候補に足し、当時の名前に戻してから絞る）。"""
    moves = _moves_after(wiki_dir, stamp)
    if name is not None:
        wanted = lambda n: n == name  # noqa: E731
        keys = [name]
    else:
        wanted = lambda n: n.startswith(prefix)  # noqa: E731
        keys = []
    keys += [new for _, new in moves]

    out = {}
    for key, data in _load(wiki_dir, stamp, keys,
                           prefix if name is None else None).items():
        then = _name_at(key, moves)
        if then is None or not wanted(then):
            continue
        text, exact = _state_at(*data, stamp)
        if text is None or not text.strip():
            continue   # 無かった、またはさかのぼれない
        # 同じ名前に2つ当たったら、確かなほうを採る（ふつうは起きない）
        if then not in out or (exact and not out[then][1]):
            out[then] = (text, exact)
    return out


# ---- 公開する関数 ------------------------------------------------------------

def subpath_state_at(wiki_dir, subpath, when):
    """実体パス（拡張子抜き、index解決済み）のその時点の状態。

    {"text", "exists", "exact"} を返す。無かった・さかのぼれなければ
    text は空、exists は False。"""
    stamp = stamp_of_when(when)
    found = _pages_at(wiki_dir, stamp, name=subpath).get(subpath)
    if found is None:
        return {"text": "", "exists": False, "exact": True}
    return {"text": found[0], "exists": True, "exact": found[1]}


def subpath_text_at(wiki_dir, subpath, when):
    """実体パスで指したページの、その時点の本文。無かった・さかのぼれなければ None。"""
    state = subpath_state_at(wiki_dir, subpath, when)
    return state["text"] if state["exists"] else None


def page_text_at(wiki_dir, pagepath, when):
    """ページパス（"/foo/bar"）で指したページの、その時点の本文。
    無かった・さかのぼれなければ None。

    ページパスは実体とずれることがある（"/foo" が "foo/index" を指す）。
    その時点の入口（"foo/bar/index"）を先に見て、無ければ "foo/bar" を見る
    （いまの resolve_page_ref がフォルダ側を優先するのと同じ順）。
    ただし、その時点に入口の無いフォルダだった（＝開けなかった）かどうかまでは
    見ていない。"""
    name = (pagepath or "").strip("/")
    candidates = [f"{name}/{INDEX_NAME}" if name else INDEX_NAME]
    if name:
        candidates.append(name)
    for subpath in candidates:
        text = subpath_text_at(wiki_dir, subpath, when)
        if text is not None:
            return text
    return None


def folder_entries_at(wiki_dir, folder, when):
    """その時点の、フォルダ直下の一覧（pagedb.page_children のその時点版）。

    folder は "foo"・"/foo"・"foo/" のどれでもよい（空ならWikiの直下）。
    直下の名前ごとに1つずつ、名前順で返す。名前はどれも**その時点の**名前。

        name      直下の名前
        subpath   その名前のページの実体パス（直下の実体か、入口 "…/index"）。
                  下にページはあるが、その階層自身は開けないフォルダなら None
        pagepath  URL上の名前（先頭の "/" 無し。subpath が None ならフォルダのパス）
        has_more  その下に、subpath 以外のページがあったか
        exact     subpath の内容が正確に分かっているか（モジュール冒頭参照）

    その時点に在ったものだけを返す（いまは消えた・改名したページも含み、
    まだ作られていないものは含まない）。さかのぼれなかったページは、在ったか
    どうか分からないので入れない。"""
    stamp = stamp_of_when(when)
    folder = (folder or "").strip("/")
    prefix = folder + "/" if folder else ""
    groups = {}
    for sp, (_, exact) in sorted(_pages_at(wiki_dir, stamp, prefix=prefix).items()):
        name, sep, rest = sp[len(prefix):].partition("/")
        if not name:
            continue
        g = groups.setdefault(name, {"subpath": None, "exact": True, "more": False})
        if not sep or rest == INDEX_NAME:
            # 直下の実体と入口が両方あれば入口を採る（page_children と同じ。
            # 名前順で入口が後に来る）
            g["subpath"], g["exact"] = sp, exact
        else:
            g["more"] = True
    out = []
    for name in sorted(groups):
        g = groups[name]
        sp = g["subpath"]
        out.append({
            "name": name,
            "subpath": sp,
            "pagepath": pagepath_of_subpath(sp) if sp else prefix + name,
            "has_more": g["more"],
            "exact": g["exact"],
        })
    return out
