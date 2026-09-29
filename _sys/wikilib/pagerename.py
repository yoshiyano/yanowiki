"""ページの名前と置き場所を変える。

**名前**を変えるのと、**置き場所**（どのフォルダに置くか）を変えるのを、同じ
処理（`rename_page`）で扱う。どちらも実体パス（subpath）が変わる操作で、後始末が
まったく同じになるため。画面はファイル一覧（`wikilib.filesui`）で、名前の変更と
移動がここを呼ぶ（以前の `/.rename` の画面は 2026-09-29 に外した）。

## ページとフォルダ

対象がフォルダの入口（`Tech/Foo/index`）だった場合は、**フォルダを動かす**。
入口だけを動かしても `/Tech/Foo` で開ける先は変わらず、動かしたことにならない
ためで、そのフォルダの下にあるページは丸ごと一緒に動く。

    ふつうのページ   Tech/Foo        → Tech/Bar
    フォルダの入口   Tech/Foo/index  → Tech/Bar/index    （下のページも一緒）

ふつうのページでも、**その名前の配下にページがあれば一緒に動かす**
（`X` を動かすと `X/kid` も付いてくる）。`X` から見た `kid` の位置が変わって
しまわないようにするため。

## 移し先は、すでにある場所に限る

置き場所は、**すでにあるページの場所**に限る（`check_folder`）。どこにも
辿り着けない場所へ置いてしまうのを防ぐため。まだ無い場所へ移したいときは、
先にそこへページを作ってから移す。

まだ下位ページを持たないページを移し先にすると、そこが新しくフォルダになる
（`X` の下に `X/kid` を作るとフォルダになるのと同じ考えかた。`make_folder_entry`）。

## 一緒に動くもの

実体パス（subpath）が変わると、それに紐づくものも動かないと参照が切れる。

    ページ本体      wiki/<subpath>.<ext>
    添付ファイル    attach/<subpath>/
    バックアップ    pageinfo/backup/<ページ名>.<日時>.diff
    書きかけ        pageinfo/draft/<ページ名>
    DBの行          pageinfo/wikiall.db（本文・タイトル・目次・リンク）
    権限の記録      config/privileges・config/privileges.plugin の、そのページと配下の行

権限の記録は、**付け替えないと新しい名前のページが誰でも読める**ので、実体を
動かす前に新しい名前の行を足し、動かしたあとで古い名前の行を消す（どの瞬間にも
制限が外れない）。移し先に手で書いた行があってぶつかるときは改名を断る。
決まりの詳細は `privilege_records.renamed_rule` の前の説明。

## 指していたリンクを直す

動くと、そのページを指していたリンクは行き先を失う。どのページが指しているかは
`links` の表（pagedb）に入っているので、そこから拾って本文のリンク先を
書き換える（`pagelinks.rewrite_links`）。

直す相手は2種類あり、見かたが違う。

    動いていないページ  指し先が変わっただけ。書きかたはそのまま置き換える
    動いたページ自身    指し先が同じでも、**自分の位置が変わった**ので相対の
                        書きかたを見直す（決まりは pagelinks の冒頭）

**書き換えは、編集画面から保存したのとまったく同じ扱いにする。** 差分が
バックアップに残り、DBの本文・タイトル・目次・リンクも入れ直される。
動かしたせいで他人のページが書き換わるので、**あとから何が起きたかを
たどれる**必要があるためである。
"""
import os

from wikilib.pagelinks import rewrite_links
from wikilib import pagedb, privilege_records, stafflog
from wikilib.pagemove import convert_page_to_folder, move_page_records, page_file_of
from wikilib.pagesave import save_page
from wikilib.pagesync import sync_wiki
from wikilib.pluginlinks import rewrite_plugin_arg_links
from wikilib.paths import (
    FARM_PREFIX, INDEX_NAME, PAGE_NAME_EXT_RE, SYSTEM_PREFIX, entry_subpath_of,
    farm_plugin_dir, is_folder_entry, pagepath_of_subpath, resolve_page_ref,
)
from wikilib.plugins import build_markdown_renderer


def rename_root_of(subpath):
    """名前を変える対象。フォルダの入口ならそのフォルダ、ふつうのページならページ自身。

    これはページパスそのもの（`paths.pagepath_of_subpath`）である。入口を
    動かしても `/Tech` で開ける先は変わらないので、名前を変える単位も
    「URLとして見えている名前」と一致する。"""
    return pagepath_of_subpath(subpath)


def split_name(subpath):
    """(親のパス, 名前) に分ける。親が無ければ ("", 名前)。"""
    parent, _, name = rename_root_of(subpath).rpartition("/")
    return parent, name


def check_name(new_name):
    """新しい名前が使えるか。使えれば None、駄目なら理由を返す。"""
    if not new_name:
        return "新しい名前を入力してください。"
    if "/" in new_name or "\\" in new_name:
        return "名前に «/» は使えません（置き場所は下の「フォルダも変更する」で選びます）。"
    if new_name in (".", ".."):
        return "その名前は使えません。"
    if new_name.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
        return ("«{}» や «{}» で始まる名前は使えません"
                "（システムが使う目印のため）。".format(FARM_PREFIX, SYSTEM_PREFIX))
    if PAGE_NAME_EXT_RE.search(new_name):
        return ("拡張子の形で終わる名前は使えません"
                "（リンクに書いたとき添付ファイルと見分けが付かなくなるため）。")
    return None


def check_folder(wiki_dir, new_folder):
    """移す先のフォルダが使えるか。使えれば None、駄目なら理由を返す。

    選べるのは**すでにあるページの場所**だけにしてある。自由に書けると打ち間違いで
    どこにも辿り着けない場所へ置いてしまうため。まだ無い場所へ移したいときは、
    先にそこへページを作ってから移す。

    「そこにページがある」は2通りある。**そのページ自身がある**か、
    **すでに下位のページを持っている**かで、どちらも移し先として認める。
    まだ下位を持たないページを選んだ場合は、そこが新しくフォルダになる
    （`X` の下に `X/kid` を作るとフォルダになるのと同じ考えかた）。"""
    if not new_folder:
        return None  # wiki の直下。いつでも選べる
    for part in new_folder.split("/"):
        if not part or part in (".", ".."):
            return "置き場所の指定が正しくありません。"
        if part.startswith((FARM_PREFIX, SYSTEM_PREFIX)):
            return ("«{}» や «{}» で始まるフォルダには置けません"
                    "（システムが使う目印のため）。".format(FARM_PREFIX, SYSTEM_PREFIX))
    prefix = new_folder + "/"
    subpaths = pagedb.all_subpaths(wiki_dir)
    if not any(s == new_folder or s.startswith(prefix) for s in subpaths):
        return (f"«/{new_folder}» はまだありません。"
                "先にその場所へページを作ってから移してください。")
    return None


def make_folder_entry(wiki_dir, config, folder):
    """移し先に選ばれたページを、フォルダの入口（`…/index`）に作り替える。
    (駄目な理由, 作り替えたか) を返す（理由が None なら成功）。

    **`X.txt` とフォルダ `X/` は同居できない。** `resolve_page_ref` は
    フォルダがあれば必ずその中の `index` を読むので、`X.txt` を残したまま
    `X/` を作ると、中身はあるのに読めないページになってしまう
    （`pagedb.shadowed_pages`）。そこで、まだ下位を持たないページを移し先に
    選んだときは、そのページ自身に `X/index` へ引っ越してもらってから
    フォルダにする。

    **ページパス（`pagepath_of_subpath`）は `X` のまま**なので、URLも、その
    ページを指しているリンクも変わらない。移し替えるのは実体（本文の
    ファイル・添付・記録）だけである。

    引っ越しそのものは `pagemove.convert_page_to_folder` が受け持つ。
    編集画面が下位ページを作るときに通る道（`pagemove.ensure_folder_path`）
    と同じもので、ここが決めるのは**作り替えが要るかどうか**だけである。
    すでにフォルダなら何もしない（そこにページが無い場合は check_folder が
    先に弾いている）。"""
    if not folder or os.path.isdir(os.path.join(wiki_dir, folder)):
        return None, False
    if convert_page_to_folder(wiki_dir, config, folder):
        return None, True
    return f"«/{folder}» をフォルダにできませんでした。", False


def moved_pages(wiki_dir, old_root, new_root, is_folder, subpaths=None):
    """動くページを [(旧subpath, 新subpath), …] で返す。

    フォルダなら、その下にあるページを全部拾う（DBに入っているものが対象）。
    ふつうのページでも、**その名前の配下にページがあれば一緒に動かす**
    （`X` を動かすと `X/kid` も付いてくる。`X` から見た `kid` の位置が
    変わらないようにするため）。

    subpaths は DB のページの一覧（`pagedb.all_subpaths`）。何度も呼ぶ側
    （ファイル一覧の行ごとの判定）が1回読んだものを渡す。省けばここで読む。"""
    prefix = old_root + "/"
    if subpaths is None:
        subpaths = pagedb.all_subpaths(wiki_dir)
    under = [(s, new_root + "/" + s[len(prefix):])
             for s in subpaths if s.startswith(prefix)]
    if is_folder:
        return under
    return [(old_root, new_root)] + under


def unwritable_pages(wiki_dir, subpath, privilege, subpaths=None):
    """名前を変えると動くページのうち、編集の権限（W）が無いもののページパス。

    空なら変えてよい。ファイル一覧（filesui）の名前の変更・移動と、項目の権限（動かす）が使う。
    subpath はフォルダの入口（`X/index`）でもよく、その場合は下のページも数える。

    **動くページすべてに編集の権限（`W`）が要る**（Wiki設計者の指示、2026-09-17）。
    名前や置き場所を変えることは、そのページを編集することだからである。フォルダの
    入口を動かすと中のページも一緒に動くので、**1枚でも編集できないページが混じって
    いれば断る**。混じったまま通すと、編集できないはずのページのURLを変えられる。

    **リンクの書き換え（`fix_links`）は数えない。** こちらは動いたページを指して
    いた**他のページ**を直すもので、書き換えなければリンクが切れる。これは
    利用者の編集ではなくシステムの後始末なので、指しているページの権限は見ない。
    subpaths は `moved_pages` と同じ（省けばここで読む）。"""
    from wikilib import auth
    moving = [pagepath_of_subpath(old) for old, _ in
              moved_pages(wiki_dir, rename_root_of(subpath), "x", is_folder_entry(subpath),
                          subpaths)]
    # ふつうのページでは moving にも自分自身が入るので、重なりを除く
    pagepaths = list(dict.fromkeys([pagepath_of_subpath(subpath)] + moving))
    return [p for p in pagepaths if privilege.check(p) != auth.PAGE_WRITE]


def _attach_root(wiki_dir):
    return os.path.join(os.path.dirname(wiki_dir), "attach")


def _move_tree(src, dst):
    """フォルダごと動かす。移動元が無ければ何もしない。動かせたらTrue。"""
    if not os.path.isdir(src) or os.path.exists(dst):
        return False
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(src, dst)
    except OSError:
        return False
    return True


def fix_links(wiki_dir, config, renames, moved=(), engine=None):
    """名前や置き場所が変わったページを指しているリンクを書き換える。
    直したページの実体パスを返す。

    renames は {旧ページパス: 新ページパス}、moved は **(旧実体パス, 新実体パス)**
    の並び。ページパスと実体パスは `/Tech` と `Tech/index` のようにずれるので、
    混ぜないよう引数を分けて受け取る。

    直す相手は2種類あり、見かたが違う。

        動いていないページ  指し先が変わっただけ。書きかたはそのまま置き換える
        動いたページ自身    指し先が同じでも、**自分の位置が変わった**ので
                            相対の書きかたを見直す（pagelinks の決まり）

    本文の記法上のリンク（`rewrite_links`）に加えて、プラグインの引数に
    書かれたページ名（`"link": True` と宣言された引数。`rewrite_plugin_arg_links`）
    も同じ規則で書き換える。

    **編集画面から保存したのと同じ扱い**にする（差分をバックアップに残し、
    DBの本文・タイトル・目次・リンクも入れ直す）。名前を変えたせいで他人の
    ページが書き換わるので、あとから何が起きたかをたどれるようにするため。"""
    if engine is None:
        engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir))
    registry = getattr(engine, "plugin_registry", None)

    moved_map = dict(moved)  # 新実体パス → 旧実体パス
    new_to_old = {new: old for old, new in moved_map.items()}

    # 動いたページを指していたページを集める。動いたページ自身も対象に入れる
    wanted = set(new_to_old)
    for old_page in renames:
        for source in pagedb.backlinks_of(wiki_dir, "/" + old_page):
            # 逆リンクの source は動いたあとの実体パスで記録されている
            wanted.add(source)

    fixed = []
    for subpath in sorted(wanted):
        ref = resolve_page_ref(wiki_dir, pagepath_of_subpath(subpath))
        if ref is None or not ref.exists:
            continue
        cache = pagedb.link_rows_of(wiki_dir, subpath)
        old_subpath = new_to_old.get(subpath)
        updated, count = rewrite_links(ref.body, subpath, ref.ext, renames,
                                       old_subpath=old_subpath,
                                       cache=cache, wiki_dir=wiki_dir, engine=engine)
        updated, plugin_count = rewrite_plugin_arg_links(
            updated, ref.ext, subpath, renames, registry, old_subpath=old_subpath,
            wiki_dir=wiki_dir, engine=engine)
        count += plugin_count
        if not count:
            continue
        # 編集画面から保存したのと同じ扱い（pagesave）。名前を変えたせいで他人の
        # ページが書き換わるので、差分を1本残して何が起きたかを追えるようにする
        if save_page(wiki_dir, config, subpath, ref.ext, updated, engine=engine,
                     path=ref.path, merge=False):
            fixed.append(subpath)
    return fixed


def rename_page(wiki_dir, config, subpath, new_name, new_folder=None):
    """ページ（またはフォルダ）の名前と置き場所を変える。
    (成否, 知らせる文言, 新しいページパス) を返す。

    new_folder に None を渡すと置き場所は変えない。空文字列は wiki の直下を指す。

    助手の操作なら1件として記録する（wikilib.stafflog）。リンクを直すための
    他のページの保存は、この1件にまとめる（`quiet()`）。"""
    staff = stafflog.actor(wiki_dir)
    with stafflog.quiet():
        ok, message, new_pagepath = _rename_page(wiki_dir, config, subpath,
                                                 new_name, new_folder)
    if ok and staff is not None:
        new_subpath = (new_pagepath + "/" + INDEX_NAME if is_folder_entry(subpath)
                       else new_pagepath)
        stafflog.record(wiki_dir, staff, "page.rename", subpath,
                        "/{} → /{}".format(pagepath_of_subpath(subpath), new_pagepath),
                        before={"subpath": subpath}, after={"subpath": new_subpath})
    return ok, message, new_pagepath


def _rename_page(wiki_dir, config, subpath, new_name, new_folder=None):
    """`rename_page` の本体（記録は外側で行う）。"""
    new_name = (new_name or "").strip()
    problem = check_name(new_name)
    if problem:
        return False, problem, None

    is_folder = is_folder_entry(subpath)
    parent, old_name = split_name(subpath)
    if new_folder is None:
        new_folder = parent
    new_folder = (new_folder or "").strip().strip("/")
    problem = check_folder(wiki_dir, new_folder)
    if problem:
        return False, problem, None

    old_root = rename_root_of(subpath)
    new_root = (new_folder + "/" + new_name) if new_folder else new_name
    if new_root == old_root:
        return False, "名前も置き場所も変わっていません。", None
    # 自分の中へ自分を移すことはできない（フォルダごと動かすと行き場が消える）
    if new_root.startswith(old_root + "/"):
        return False, "自分の中へは移せません。", None
    if os.path.exists(os.path.join(wiki_dir, new_root)) or \
            page_file_of(wiki_dir, new_root)[0] is not None:
        return False, f"«/{new_root}» はすでに使われています。", None
    clash = privilege_records.rename_conflicts(wiki_dir, old_root, new_root)
    if clash:
        return False, ("移し先の «/{}» には、アクセス制限の記録がすでにあります"
                       "（/.admin/privileges）。先にどちらかを整理してください。"
                       .format(clash[0][0])), None

    # 移し先がまだ下位を持たないページなら、先にフォルダの入口へ作り替える
    # （そうしないと、そのページが読めなくなる。make_folder_entry 参照）
    problem, became_folder = make_folder_entry(wiki_dir, config, new_folder)
    if problem:
        return False, problem, None

    pairs = moved_pages(wiki_dir, old_root, new_root, is_folder)
    if not pairs:
        return False, "動かす対象が見つかりません。", None

    # それぞれの拡張子は動かす前に控える（動かしたあとでは辿れない）
    exts = {old: page_file_of(wiki_dir, old)[1] for old, _ in pairs}

    # 権限の記録は、実体を動かす前に新しい名前の行を足しておく（冒頭の説明）
    if not privilege_records.copy_for_rename(wiki_dir, old_root, new_root):
        privilege_records.finish_rename(wiki_dir, old_root, new_root, moved=False)
        return False, "アクセス制限の記録を書き換えられませんでした。", None

    def undo(message):
        privilege_records.finish_rename(wiki_dir, old_root, new_root, moved=False)
        return False, message, None

    if is_folder:
        # フォルダごと動かす。中のページ・下位フォルダが一度に付いてくる
        if not _move_tree(os.path.join(wiki_dir, old_root),
                          os.path.join(wiki_dir, new_root)):
            return undo("フォルダを動かせませんでした。")
    else:
        src, ext = page_file_of(wiki_dir, old_root)
        if src is None:
            return undo("元のページが見つかりません。")
        dst = os.path.join(wiki_dir, new_root + ext)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
        except OSError:
            return undo("ページを動かせませんでした。")
        # 同じ名前のフォルダ（配下ページの置き場所）も一緒に動かす。
        # `X` を動かしたのに `X/kid` が元の場所に残ると、`X` から見た `kid` の
        # 位置が変わってしまう
        _move_tree(os.path.join(wiki_dir, old_root),
                   os.path.join(wiki_dir, new_root))
    # 添付は実体パスをそのままミラーしているので、同じ付け替えでよい
    _move_tree(os.path.join(_attach_root(wiki_dir), old_root),
               os.path.join(_attach_root(wiki_dir), new_root))
    # 動かしたあとに空になったフォルダは片付ける（中身の無い階層を残さない）
    from wikilib.editor import remove_empty_dirs
    remove_empty_dirs(os.path.join(wiki_dir, os.path.dirname(old_root)), wiki_dir)

    # ページ1枚ごとに、紐づく記録を付け替える
    for old, new in pairs:
        # 実体は上でフォルダごと動かしてあるので、紐づくもの（添付・記録・
        # 書きかけ・DBの行）だけを付け替える。添付は既に動いていれば
        # 移動元が無く、何もしない（pagemove.move_page_records）
        move_page_records(wiki_dir, old, new, exts.get(old) or ".md")
    privilege_records.finish_rename(wiki_dir, old_root, new_root, moved=True)

    # 直す相手は links の表（逆リンク）から引くので、平文を置いただけで
    # まだ取り込んでいないページがあると取りこぼす。リネームは他人のページを
    # 書き換える操作なので、ここで先に取り込んで正しさを優先する
    sync_wiki(wiki_dir, config)

    renames = {pagepath_of_subpath(old): pagepath_of_subpath(new) for old, new in pairs}
    fixed = fix_links(wiki_dir, config, renames, moved=pairs)

    what = "フォルダ" if is_folder else "ページ"
    moved_folder = new_folder != parent
    if moved_folder and new_name != old_name:
        did = f"«/{new_root}» に移して名前も変えました"
    elif moved_folder:
        did = f"«/{new_folder or ''}» へ移しました" if new_folder else "いちばん上へ移しました"
    else:
        did = f"名前を «{new_name}» に変えました"
    detail = f"（{len(pairs)}ページ）" if len(pairs) > 1 else ""
    note = f" {len(fixed)}ページのリンクを直しました。" if fixed else ""
    if became_folder:
        # URLは変わらないが、実体が動いたことは知らせる（添付や記録も一緒に
        # 動いているため、あとから「なぜ index になったのか」を追えるように）
        note += f" «/{new_folder}» はフォルダになりました（入口は «{INDEX_NAME}»）。"
    head = pairs[0][1] if not is_folder else entry_subpath_of(new_root)
    return True, f"{what}の{did}{detail}。{note}", pagepath_of_subpath(head)
