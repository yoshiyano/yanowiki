#!/usr/bin/env python3
"""Wiki Farm の1つを対象に、ページ内リンクの張り先を検査する。

  ./checklinks.py <Wiki名> [<Wiki名> ...]
  ./checklinks.py --all
  ./checklinks.py --wikidata /path/to/wikidata <Wiki名>

置き場所: wikiSystem のルート（`wiki.py` のあるフォルダ）。
`wikidata/` は、次の順に探す。
  1. `--wikidata` で指定したフォルダ
  2. 環境変数 `WIKIDATA`
  3. このスクリプトと同じフォルダの `wikidata/`
  4. カレントフォルダの `wikidata/`

見出しのIDは pageinfo/wikiall.db の目次（toc）から取るので、
**先に `./wiki.py updatepage =<Wiki名>` を実行しておくこと**。
DBが古いと、直したはずのリンクが切れて見える。

コードフェンスとインラインコードの中は検査しない。
記法の説明で `](/Page)` のように書いた例が引っかかるため。

`/=別Wiki/...`（他のWikiへのリンク）と `/.xxx`（システムページ）は
このWikiの中に無くて当たり前なので対象外。

終了コード: 0 = 不良なし、1 = リンク不良あり、2 = 使いかたの誤り。
"""

import io
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WIKIDATA = None      # main() が決める


def find_wikidata(given):
    """wikidata/ のフォルダを決める。見つからなければ None。"""
    for cand in (given, os.environ.get("WIKIDATA"),
                 os.path.join(HERE, "wikidata"), os.path.join(os.getcwd(), "wikidata")):
        if cand and os.path.isdir(cand):
            return os.path.abspath(cand)
    return None


FENCE = re.compile(r"^\s*(```|~~~)")
INLINE = re.compile(r"`[^`]*`")
LINK = re.compile(r"\]\((/[^)\s#]*)(?:#([^)\s]+))?\)")


def strip_code(text):
    """コード部分を空白へ潰す。行数と桁位置は変えない。"""
    out, in_fence = [], False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            out.append("")
        else:
            out.append("" if in_fence else INLINE.sub(lambda m: " " * len(m.group(0)), line))
    return out


def page_ids(db):
    """ページ名 -> そのページの見出しID集合。"""
    ids = {}
    for sub, toc in sqlite3.connect(db).execute("select subpath, toc from pages"):
        name = "/" + sub
        if name.endswith("/index"):
            name = name[:-6]
        ids[name.rstrip("/") or "/"] = set(walk(json.loads(toc) if toc else []))
    return ids


def walk(node):
    """目次（入れ子のリスト／辞書）から id を拾い出す。"""
    if isinstance(node, dict):
        if "id" in node:
            yield node["id"]
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for x in node:
            yield from walk(x)


def check(wiki):
    root = os.path.join(WIKIDATA, wiki)
    db = os.path.join(root, "pageinfo", "wikiall.db")
    src = os.path.join(root, "wiki")
    if not os.path.isfile(db):
        return [(wiki, "", 0, "", f"{db} が無い")]
    ids = page_ids(db)

    bad = []
    for dirpath, _, files in os.walk(src):
        for f in sorted(files):
            if not f.endswith(".md"):
                continue
            path = os.path.join(dirpath, f)
            rel = os.path.relpath(path, src)
            text = io.open(path, encoding="utf-8").read()
            for no, line in enumerate(strip_code(text), 1):
                for target, anchor in LINK.findall(line):
                    if target.startswith(("/=", "/.")):
                        continue           # 他Wiki・システムページは対象外
                    page = target.rstrip("/") or "/"
                    if page not in ids:
                        bad.append((wiki, rel, no, target, "ページが無い"))
                    elif anchor and anchor not in ids[page]:
                        bad.append((wiki, rel, no, f"{page}#{anchor}", "見出しが無い"))
    return bad


def main(argv):
    global WIKIDATA
    argv = list(argv)
    given = None
    if "--wikidata" in argv:
        i = argv.index("--wikidata")
        if i + 1 >= len(argv):
            print("--wikidata にはフォルダを指定してください")
            return 2
        given = argv[i + 1]
        del argv[i:i + 2]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    WIKIDATA = find_wikidata(given)
    if WIKIDATA is None:
        print("wikidata/ が見つかりません。wikiSystem のルートに置くか、--wikidata で指定してください")
        return 2

    wikis = (sorted(d for d in os.listdir(WIKIDATA)
                    if os.path.isdir(os.path.join(WIKIDATA, d, "wiki")))
             if argv[0] == "--all" else argv)

    bad = []
    for w in wikis:
        found = check(w)
        print(f"[{w}] リンク不良 {len(found)} 件")
        bad += found
    for w, rel, no, target, why in bad:
        print(f"  {w}/{rel}:{no}  {target}   … {why}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
