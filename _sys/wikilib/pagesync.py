"""平文ファイルの直接編集を取り込む。

編集画面を通さずに書き換えられたページを見つけて、**編集画面から保存したのと
同じ後始末**を行う。具体的には次の3つで、これによりバックアップにも残り、
リンクや目次も取り直される。

    バックアップ    公開されていた内容 → いまのファイルの内容 の差分を記録
    DBへの取り込み  本文・タイトル・目次・リンクを入れ直す
    消えたページ    「全文→空」を記録してDBから消す

システムを通さない書き換えには、次のようなものがある。

    エディタで直接ファイルを開いて書いた
    `git pull` や `git reset --hard` で入れ替わった
    別の道具（スクリプトなど）が書き出した

## いつ動くか

    起動時                  wiki.py の起動直後に1回（全Wiki）
    1時間ごと               動かしている間ずっと（バックグラウンドのスレッド）
    ページを開いたとき      平文ファイルはあるがDBに無い場合（adopt_page）
    ./wiki.py updatepage    手で動かす（対象の決めかたは下記）

見つけかたは `pagedb.stale_pages()` に任せる。**ページごとに**大きさ・更新時刻・
本文のハッシュを見るので、1ページだけ取り込んでも他のページの検出には影響しない。
「ここまで走査した」という全体の時刻を持たないため、取りこぼしが起きない。

## ファイルがあれば取り込む

平文ファイルがあるのにDBに行が無いページは、**開かれた時点でその場で取り込む**
（`adopt_page`、`pagedb.published_ref` から呼ばれる）。ファイルを置けば読める、
という素直な振る舞いを優先している。

置いた覚えのないページが勝手に出てくることはない。ファイルを置いたのは
利用者自身（エディタ・`git pull`・スクリプト）であって、システムが作るものでは
ないためである。取り込みの中身は updatepage と同じなので、バックアップにも残り、
リンクや目次も揃う。

**書き換えられた**ページ（DBに行はあるが内容が違う）はここでは扱わない。
そちらは大きさ・更新時刻・ハッシュの突き合わせが要るので、起動時・1時間ごと・
updatepage の走査に任せる。

## updatepage が見る範囲

全Wikiではなく、**1つのWikiだけ**を見る。取り込みは公開の操作なので、
いま手を入れているWikiだけが対象になるほうが事故が起きにくい。

    wikidata/<Wiki名>/ の中で実行   そのWiki（farm_of_cwd で見分ける）
    それ以外の場所で実行           既定のWiki
    =Wiki名 を付けて実行           そのWiki

`--force` を付けると、平文とDBの食い違いを**見ずに**、実在するページすべてを
取り込み直す。取り出し（目次・リンク）まで含めて入れ直したいときに使う。

## 空のフォルダを片付ける

Wiki全体を見るときは、wiki/ と attach/ の中身の無いフォルダを消す
（`prune_empty_folders`・`prune_empty_attach_folders`。Wiki設計者の指示、2026-09-25）。ページの一覧に空の階層が並ばないようにするため。
一覧（`pagetree`）は表示から外すだけで消さない。消すのは、平文との食い違いを
直す役目のここにまとめてある。
"""
import os
import time

from wikilib import pagedb
from wikilib.attach import has_attach_files
from wikilib.draft import drafted_subpaths
from wikilib.links import update_page_info
from wikilib.pagesave import remove_page, save_page
from wikilib.paths import (
    FARM_PREFIX, SYSTEM_PREFIX, WIKIDATA_DIR, entry_subpath_of, farm_plugin_dir,
    farm_wiki_dir, iter_pages, pagepath_of_subpath, resolve_page_ref,
)
from wikilib.plugins import build_markdown_renderer
from wikilib.wikiconfig import load_wiki_config

SYNC_INTERVAL = 60 * 60  # 動かしている間、この間隔で見に行く（秒）

# 取り込んだページを描き直す回数の上限（Wiki設計者の指示、2026-09-13）。
# **描くたびに本文が変わり続けるプラグイン**が現れても、そこで止まらなく
# ならないための歯止め。既定は5回。
MAX_REVIEW = 5

# 作られてからこの秒数に満たない空のフォルダは消さない。保存（save_page）は
# 「途中の階層を作る → ファイルを書く」の順なので、その間に消すと保存が失敗する。
EMPTY_FOLDER_MIN_AGE = 10 * 60


def _prune_tree(root, keep, min_age, now):
    """root の下から空のフォルダを消す（root 自身は残す）。消したものの相対パスを返す。

    下から順に見るので、空のフォルダしか入っていないフォルダもまとめて消える。
    作られたばかりかどうかは、消し始める前の更新時刻で見る（子を消すと親の
    更新時刻が新しくなり、親だけ次回へ持ち越されるのを避けるため）。
    keep(相対パス) が真のフォルダは残す。"""
    now = time.time() if now is None else now
    root = os.path.realpath(root)
    if not os.path.isdir(root):
        return []
    mtimes = {}
    for dirpath, dirnames, _files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith((FARM_PREFIX, SYSTEM_PREFIX))]
        try:
            mtimes[dirpath] = os.stat(dirpath).st_mtime
        except OSError:
            pass

    removed = []
    for dirpath in sorted(mtimes, key=len, reverse=True):  # 深いものから
        if dirpath == root:
            continue
        sub = os.path.relpath(dirpath, root).replace(os.sep, "/")
        try:
            if os.listdir(dirpath):
                continue
        except OSError:
            continue
        if now - mtimes[dirpath] < min_age or keep(sub):
            continue
        try:
            os.rmdir(dirpath)
        except OSError:
            continue
        removed.append(sub)
    return sorted(removed)


def prune_empty_folders(wiki_dir, min_age=EMPTY_FOLDER_MIN_AGE, now=None):
    """中身の無いフォルダを wiki/ から消す。消したフォルダのページパスを返す。

    消すのは、下位も含めてファイルが1つも無く、次のどれにも当たらないフォルダ。

        書きかけがある      その下のページを作りかけている（pageinfo/draft/）
        入口に添付がある    ページより先に添付だけ置いてある（attach/X/index/）
        作られたばかり      保存の途中かもしれない（EMPTY_FOLDER_MIN_AGE）"""
    drafts = drafted_subpaths(wiki_dir)

    def keep(sub):
        return (any(d.startswith(sub + "/") for d in drafts)
                or has_attach_files(wiki_dir, entry_subpath_of(sub)))

    return [pagepath_of_subpath(sub) for sub in _prune_tree(wiki_dir, keep, min_age, now)]


def prune_empty_attach_folders(wiki_dir, min_age=EMPTY_FOLDER_MIN_AGE, now=None):
    """中身の無いフォルダを attach/ から消す。消したものの attach/ からの相対パスを返す。

    添付を置く処理（attach.save_attachment・move_attachment、pagemove）は、
    どれも置く前にフォルダを作り直す（`os.makedirs(..., exist_ok=True)`）ので、
    空の置き場を消しても困らない。残すのは作られたばかりのものだけ
    （置く途中かもしれないため。理由は wiki/ 側と同じ）。"""
    attach_root = os.path.join(os.path.dirname(wiki_dir), "attach")
    return _prune_tree(attach_root, lambda sub: False, min_age, now)


def sync_page(wiki_dir, config, engine, subpath, kind, created=None):
    """1ページ分を取り込む。取り込んだらTrue。

    kind は pagedb.stale_pages() が返すもの（"updated" / "added" / "removed"）。
    created は新しく行を入れるときの初回登録日時（省略すると「いま」）。

    記録そのものは pagesave が行う（保存・復元・改名と同じ手順）。取り込みだけは
    **すでにファイルにある内容**を後から記録する操作なので、書き出しはしない。"""
    if kind == "removed":
        return remove_page(wiki_dir, subpath)

    ref = resolve_page_ref(wiki_dir, pagepath_of_subpath(subpath))
    if ref is None or not ref.exists:
        return False
    return save_page(wiki_dir, config, subpath, ref.ext, ref.body, engine=engine,
                     path=ref.path, created=created, write=False)


def adopt_page(wiki_dir, subpath, config=None):
    """平文ファイルはあるがDBに無いページを、その場で取り込む。取り込んだらTrue。

    ページを開いたときに `pagedb.published_ref` から呼ばれる。**ファイルを置けば
    読める**ようにするためのもので、`git clone` や `git pull` で入ってきたページ、
    エディタで直に書いたページが、updatepage を待たずに読める。

    中身は updatepage の "added" と同じ（`sync_page` をそのまま通す）ので、
    バックアップにも残り、タイトル・目次・リンクも揃う。取り込む処理を分けて持つと
    どちらかだけ直す事故が起きるため、経路は1つにしてある。

    すでにDBに行があれば何もしない。**書き換えの取り込みではない。** そちらは
    平文との突き合わせが要るので、走査（起動時・1時間ごと・updatepage）に任せる。

    初回登録日時は、そのページにバックアップが残っていればいちばん古い日時を使う
    （`pagedb.rebuild` と同じ考えかた）。行を失っただけのページを入れ直すときに
    「今日作られた」ことにしないためで、**取り込む前に**調べる（取り込むと、この
    取り込み自身の差分が1本増えるため）。本当に新しいページなら差分はまだ無いので、
    そのまま「いま」になる。

    差分の一覧を引くので、まとめて取り込む走査のほうでは行わない（ページ数の分だけ
    引くことになる。作り直しのときは `pagedb.rebuild` が同じ手当てをしている）。"""
    if pagedb.load_page(wiki_dir, subpath) is not None:
        return False
    if config is None:
        config = load_wiki_config(wiki_dir)
    created = pagedb.first_backup_stamp(wiki_dir, subpath)
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir))
    return sync_page(wiki_dir, config, engine, subpath, "added", created=created)


def forced_pages(wiki_dir, subpath=None):
    """`--force` のときに見る一覧。stale_pages() と同じ形で返す。

    **平文とDBの食い違いを見ない。** 実在するページはすべて取り込み直す対象に
    する（大きさも更新時刻も同じでも読み直す）。DBに行があれば "updated"、
    無ければ "added" とするのは数えかたを揃えるためで、どちらも同じ処理になる。

    ページを1つに絞った場合は、そのページだけを見る。絞らない場合は、消えた
    ページの後始末（"removed"）もここで拾う。"""
    known = set(pagedb.all_subpaths(wiki_dir))
    found = []
    seen = set()
    for pagepath, _ in iter_pages(wiki_dir):
        ref = resolve_page_ref(wiki_dir, pagepath)
        if ref is None or not ref.exists:
            continue
        seen.add(ref.subpath)
        if subpath is not None and ref.subpath != subpath:
            continue
        found.append({"subpath": ref.subpath,
                      "kind": "updated" if ref.subpath in known else "added"})
    for sub in sorted(known - seen):
        if subpath is None or sub == subpath:
            found.append({"subpath": sub, "kind": "removed"})
    return found


def farm_of_wiki_dir(wiki_dir):
    """`wikidata/<Wiki名>/wiki` からWiki名を取り出す。

    描くときに要る（`make_plugin_context` がWiki名で base_url を組み立てる）。
    取り込みの入口は `wiki_dir` しか持ち回らない場所があるので、そこから
    導けるようにしてある。"""
    return os.path.basename(os.path.dirname(wiki_dir))


def review_page(wiki_dir, config, farm, subpath, max_review=MAX_REVIEW):
    """取り込んだページを**1回描く**。本文が落ち着くまで描き直す。
    `(描いた回数, 落ち着いたか)` を返す（Wiki設計者の指示、2026-09-13）。

    ## なぜ取り込みで描くのか

    **描いたときにしか作られない記録がある。** プラグインが描画の中で書き出す
    もの（ページごとのアクセス制限など。[ページごとの権限](/Tech/PagePermissions)）が
    それで、**ファイルを直接置いて取り込んだページは、誰かが開くまで一度も
    描かれない**ため、その間ずっと記録が欠けたままになる。`git pull` で
    ページがまとめて入る運用では、これがそのまま穴になる。

    ここで1回描いておけば、**取り込んだ時点で「開かれたのと同じ状態」**に
    なる。**プラグインの側に特別な取り決めは要らない**——いつもの描画を
    1回呼ぶだけなので、本体がどのプラグインの何を知る必要もない。

    ## なぜ描き直すのか

    **描くと本文が書き換わるプラグインが出てくる**（Wiki設計者の指示、
    2026-09-13。いまはまだ無い）。書き換わったということは、**次に描かれる
    のは別の本文**ということなので、そのままでは記録が1つ前の本文のものに
    なる。**描く前と描いたあとが一致するまで**繰り返して、落ち着いた本文で
    記録が作られるようにする。

    繰り返しは `max_review` 回まで（既定は `MAX_REVIEW` = 5）。**描くたびに
    違う値を書くプラグイン**（時刻を書き込むなど）があると永遠に一致しないので、
    そこで打ち切って「落ち着かなかった」と返す。打ち切っても取り込み自体は
    止めない——記録が1回ぶん古いだけで、ページは読める。

    描画で例外が出たページも、そこで止めずに「落ち着いた」として返す。
    **描けないページがあることと、取り込みが失敗することは別**で、
    そのページの不具合は開いたときに画面で見える。"""
    from wikilib.render import render_source
    from wikilib.themes import make_plugin_context

    pagepath = pagepath_of_subpath(subpath)
    first_h1 = (config.get("markdown") or {}).get("first_h1_as_title", True)
    for done in range(1, max_review + 1):
        ref = resolve_page_ref(wiki_dir, pagepath)
        if ref is None or not ref.exists:
            # 取り込んだ直後に消えた。描くものが無いので、そこで終わり
            return done - 1, True
        before = ref.body
        context = make_plugin_context(config, farm, wiki_dir, pagepath, ext=ref.ext)
        engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir), context)
        try:
            render_source(engine, before, ref.ext, first_h1, context)
        except Exception:
            return done, True
        after = resolve_page_ref(wiki_dir, pagepath)
        if after is None or not after.exists or after.body == before:
            return done, True
    return max_review, False


def sync_wiki(wiki_dir, config=None, subpath=None, force=False, farm=None):
    """1つのWikiを取り込む。{"updated":…, "added":…, "removed":…, "seconds":…} を返す。

    subpath を与えるとそのページだけを見る。**他のページの検出には影響しない**
    （どこまで見たかを覚えず、ページごとに突き合わせるため）。

    force=True なら食い違いを見ずに、対象のページをすべて読み直して入れ直す。
    初回登録日時（created）は record_page が引き継ぐので、入れ直しても変わらない。

    **取り込んだページは、最後にまとめて1回描く**（`review_page`。Wiki設計者の
    指示、2026-09-13）。描いたときにしか作られない記録を、取り込んだ時点で
    揃えるため。描いた拍子に本文が変わったら落ち着くまで描き直し、それでも
    落ち着かなかったページは結果の "unsettled" に入る（数えは "reviewed"）。

    subpath を絞らない（Wiki全体を見る）ときだけ、`X.拡張子` とフォルダ `X/` の
    衝突で読めなくなっているページも調べ、結果の "shadowed" に入れる
    （`pagedb.shadowed_pages` 参照）。Wiki全体の性質を見るものなので、
    1ページだけの取り込みでは調べない。

    **記録がまだ無いとき（取ってきた直後の1回目）は、全ページを新しく登録した
    ものとして数える。** 結果の "first" が真になり、`format_result` がそのことを
    書き添える（Wiki設計者の指示、2026-09-08）。それまでは「目次・リンクの取り出し」
    としか出ておらず、**初めて動かした人には何が起きたのか読み取れなかった。**"""
    started = time.perf_counter()
    if config is None:
        config = load_wiki_config(wiki_dir)
    if farm is None:
        farm = farm_of_wiki_dir(wiki_dir)
    result = {"updated": 0, "added": 0, "removed": 0, "filled": 0,
              "seconds": 0.0, "pages": [], "shadowed": [], "first": False,
              "reviewed": 0, "unsettled": [], "pruned": [], "pruned_attach": []}
    # 取り込んだページ。**この一覧を作ってから、最後にまとめて描く**
    # （`review_page`。描いた拍子に本文が書き換わることがあるので、
    # 取り込みの数えが済んでから手を付ける）
    reviewing = []

    # 記録が無ければ、ここで平文から作り直される（pagedb.rebuild）。そのときは
    # 本文だけが入った状態なので、下の「埋める」で全ページぶんを取り出す
    result["first"] = pagedb.ensure_db(wiki_dir)
    if force:
        found = forced_pages(wiki_dir, subpath)
    else:
        found = pagedb.stale_pages(wiki_dir)
        if subpath is not None:
            found = [f for f in found if f["subpath"] == subpath]
    engine = None
    if found:
        engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir))
        for item in found:
            if sync_page(wiki_dir, config, engine, item["subpath"], item["kind"]):
                result[item["kind"]] += 1
                result["pages"].append((item["kind"], item["subpath"]))
                if item["kind"] != "removed":
                    reviewing.append(item["subpath"])

    # 取り出し済みでないページ（タイトル・目次・リンクが未取得）を埋める。
    # DBを作り直した直後は本文しか入っていない。表示のたびに1ページずつ
    # 埋まってはいくが、**逆リンクは全ページ分が揃わないと数えられない**ので、
    # ここでまとめて済ませておく
    for row in pagedb.all_pages(wiki_dir):
        if subpath is not None and row["subpath"] != subpath:
            continue
        if row["toc"] is not None:
            continue
        if engine is None:
            engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir))
        ext = os.path.splitext(row["path"])[1]
        update_page_info(wiki_dir, row["subpath"], engine, row["body"], ext, config)
        # 1回目は**そのページ自体が新しく登録されたもの**なので「追加」で数える。
        # 2回目からは、途中で足りなくなったぶんを埋めただけなので「取り出し」
        if result["first"]:
            result["added"] += 1
            result["pages"].append(("added", row["subpath"]))
        else:
            result["filled"] += 1
        reviewing.append(row["subpath"])

    # 取り込んだページを描く。**同じページを2度描かない**（取り込みと
    # 「埋める」の両方に載ることがあるため）。描いた拍子に本文が変われば
    # 落ち着くまで描き直す（`review_page`）
    for target in dict.fromkeys(reviewing):
        _, settled = review_page(wiki_dir, config, farm, target)
        result["reviewed"] += 1
        if not settled:
            result["unsettled"].append(target)

    if subpath is None:
        result["shadowed"] = pagedb.shadowed_pages(wiki_dir)
        # 中身の無いフォルダを片付ける。1ページだけの取り込みでは行わない
        # （Wiki全体の性質を見るもの。shadowed と同じ）
        result["pruned"] = prune_empty_folders(wiki_dir)
        result["pruned_attach"] = prune_empty_attach_folders(wiki_dir)

    result["seconds"] = time.perf_counter() - started
    return result


def wiki_names():
    """いま在るWikiの名前（wiki/ を持つフォルダだけを数える）。"""
    try:
        entries = sorted(os.listdir(WIKIDATA_DIR))
    except OSError:
        return []
    return [e for e in entries
            if os.path.isdir(os.path.join(WIKIDATA_DIR, e, "wiki"))]


def farm_of_cwd():
    """いまいる場所から対象のWikiを見分ける。wikidata/<Wiki名>/ の中（何階層下でも）
    にいればその名前、外にいればNone。

    `updatepage` を引数なしで実行したときに、手を入れているWikiがそのまま
    対象になるようにするためのもの。"""
    try:
        cwd = os.path.realpath(os.getcwd())
    except OSError:
        return None
    root = os.path.realpath(WIKIDATA_DIR)
    if not cwd.startswith(root + os.sep):
        return None
    name = os.path.relpath(cwd, root).split(os.sep)[0]
    return name if farm_wiki_dir(name) is not None else None


def sync_all(farm=None, subpath=None, force=False):
    """すべてのWikiを取り込む。{Wiki名: 結果} を返す。

    farm を与えるとそのWikiだけを見る。"""
    results = {}
    for name in wiki_names():
        if farm is not None and name != farm:
            continue
        wiki_dir = farm_wiki_dir(name)
        if wiki_dir is None:
            continue
        results[name] = sync_wiki(wiki_dir, subpath=subpath, force=force, farm=name)
    return results


def format_result(results):
    """起動ログに出す1行。取り込むものが無かった場合も、かかった時間は出す。

    取ってきた直後の1回目（記録がまだ無い）だったことと、`X.拡張子` と
    フォルダ `X/` の衝突で読めないページがあることは、続く行で知らせる。"""
    total = {"updated": 0, "added": 0, "removed": 0, "filled": 0}
    seconds = 0.0
    shadowed = []
    unsettled = []
    pruned = []
    pruned_attach = []
    first = []
    for name, r in results.items():
        for key in total:
            total[key] += r.get(key, 0)
        seconds += r["seconds"]
        for pagepath in r.get("shadowed") or ():
            shadowed.append((name, pagepath))
        for sub in r.get("unsettled") or ():
            unsettled.append((name, pagepath_of_subpath(sub)))
        for pagepath in r.get("pruned") or ():
            pruned.append((name, pagepath))
        for sub in r.get("pruned_attach") or ():
            pruned_attach.append((name, sub))
        if r.get("first"):
            first.append(name)
    parts = []
    if total["updated"]:
        parts.append("更新{}".format(total["updated"]))
    if total["added"]:
        parts.append("追加{}".format(total["added"]))
    if total["removed"]:
        parts.append("削除{}".format(total["removed"]))
    if total["filled"]:
        parts.append("目次・リンクの取り出し{}".format(total["filled"]))
    what = " ".join(parts) if parts else "変更なし"
    lines = ["ページの取り込み: {} ({} Wiki, {:.2f}秒)".format(what, len(results), seconds)]
    if first:
        # **取ってきた直後の1回目**（記録がまだ無い）。何が起きたのかを書き添える
        lines.append(
            "  ※ 記録がまだ無かったので、置いてあるページを全部登録しました"
            "（{}）。次からは変わったぶんだけです。".format("・".join(first)))
    if shadowed:
        lines.append(
            "  ※ 同名のフォルダに隠れて読めないページが{}件あります"
            "（同じ場所にファイルとフォルダが両方あります）:".format(len(shadowed)))
        for name, pagepath in shadowed:
            lines.append("    [{}] /{}".format(name, pagepath))
    if pruned:
        lines.append("  ※ 中身の無いフォルダを{}件片付けました:".format(len(pruned)))
        for name, pagepath in pruned:
            lines.append("    [{}] /{}/".format(name, pagepath))
    if pruned_attach:
        lines.append("  ※ 添付の置き場で、中身の無いフォルダを{}件片付けました:".format(
            len(pruned_attach)))
        for name, sub in pruned_attach:
            lines.append("    [{}] attach/{}/".format(name, sub))
    if unsettled:
        # **描くたびに本文が変わり続けている。** プラグインが時刻のような
        # 「毎回違う値」を書いている可能性が高い（`review_page` 参照）
        lines.append(
            "  ※ {}回描き直しても本文が落ち着かなかったページが{}件あります"
            "（描くたびに本文を書き換えるプラグインがあるかもしれません）:".format(
                MAX_REVIEW, len(unsettled)))
        for name, pagepath in unsettled:
            lines.append("    [{}] /{}".format(name, pagepath))
    return "\n".join(lines)


# ---- 動かしている間、定期的に見に行く ---------------------------------------

def start_watcher(interval=SYNC_INTERVAL, log=None):
    """一定の間隔で取り込みを行うスレッドを立てる。

    daemon にしてあるので、サービスを止めるときに待たされない。
    gunicorn のようにワーカーが複数ある場合、それぞれがこのスレッドを持つが、
    取り込みは何度行っても同じ結果になる（変わっていなければ何もしない）ので
    害はない。1回目は間隔を空けてから動かす（起動直後は main が済ませている）。

    取り込みのあとで、機能していないページの権限の記録を消す
    （`updatepageauth.sweep_all`。Wiki設計者の指示、2026-09-25。1時間ごと）。
    続けて、削除したページの添付を trashbox へ集める（`garbagecollect.collect_all`。
    Wiki設計者の指示、2026-09-25。同じタイミング）。"""
    import threading

    def loop():
        while True:
            time.sleep(interval)
            try:
                results = sync_all()
            except Exception:  # 取り込みの失敗でサービスを止めない
                continue
            if log is not None and any(
                    r["updated"] or r["added"] or r["removed"] or r["filled"]
                    for r in results.values()):
                log(format_result(results))
            try:
                from wikilib.updatepageauth import sweep_all
                sweep_all(log)
            except Exception:  # 後始末の失敗でサービスを止めない
                pass
            try:
                from wikilib.garbagecollect import collect_all
                collect_all(log)
            except Exception:  # 後始末の失敗でサービスを止めない
                continue

    thread = threading.Thread(target=loop, name="pagesync", daemon=True)
    thread.start()
    return thread
