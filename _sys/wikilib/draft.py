"""一時保存（書きかけの退避）。

編集の途中で別のページへ移りたくなったとき、書きかけを失わずに移れるようにする。
ページ本体の保存とは別物で、更新履歴にもバックアップにも残らない。

**警告を出さずに移れる**ことを目的にしている。「保存しますか？」と訊かれるより、
黙って預かっておいて、戻ってきたら続きから書けるほうが素直だと考えたため。
預かっていることは、ページ一覧で赤い太字にして知らせる。

置き場所は wikidata/<Wiki名>/pageinfo/draft/。ファイル名の付けかたはバックアップと同じで、
階層の "/" を "_" に置き換える（元から含まれる "_" は "__" に退避）。
差分ファイルと同じ規則にしておけば、名前の読み替えを1か所で覚えれば済む。
"""
import os

from wikilib.backup import backup_name_of, subpath_of_backup_name
from wikilib.paths import farm_pageinfo_dir

DRAFT_EXT = ".draft"
# 書きかけの元になった本文のハッシュ（editor.source_hash）を覚えておく場所。
# 本文とは別のファイルにしてあるのは、.draft 自体のフォーマット（生の本文
# そのもの）を変えずに済ませるため。
DRAFT_ORIGIN_EXT = ".draft.origin"


def draft_root_of(wiki_dir):
    return farm_pageinfo_dir(wiki_dir, "draft")


def draft_path(wiki_dir, subpath):
    """一時保存ファイルの場所。subpathが名前として扱えない場合はNone。"""
    if not subpath:
        return None
    name = backup_name_of(subpath)
    if not name or name.startswith(".") or "/" in name or os.sep in name:
        return None
    return os.path.join(draft_root_of(wiki_dir), name + DRAFT_EXT)


def draft_origin_path(wiki_dir, subpath):
    """draft_path と同じ規則で、origin を覚えておくファイルの場所を返す。"""
    if not subpath:
        return None
    name = backup_name_of(subpath)
    if not name or name.startswith(".") or "/" in name or os.sep in name:
        return None
    return os.path.join(draft_root_of(wiki_dir), name + DRAFT_ORIGIN_EXT)


def move_draft(wiki_dir, old_subpath, new_subpath):
    """預かっている書きかけを、新しい実体パスのものとして付け替える。
    動かしたらTrue。無ければ何もしない。

    **`.draft` と `.draft.origin` は必ず一緒に動かす。** origin だけ古い名前に
    残ると、再開したときの「預けてから他の人が更新していないか」の判定
    （load_draft_origin）が基準を失う。名前の付けかたを知っているのはこの
    モジュールなので、付け替えもここが受け持つ（ページの実体を動かす側は
    pagemove.move_page から、まとめて呼ぶ）。"""
    moved = False
    for locate in (draft_path, draft_origin_path):
        src = locate(wiki_dir, old_subpath)
        dst = locate(wiki_dir, new_subpath)
        if src is None or dst is None or not os.path.isfile(src) or os.path.exists(dst):
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
            moved = True
        except OSError:
            pass
    return moved


def save_draft(wiki_dir, subpath, text, origin=None):
    """書きかけを預かる。保存されている内容と同じなら、預からずに消す
    （中身が同じものを「書きかけ」として赤く出しても意味がないため）。

    `origin` は、預けた時点で編集画面に表示されていた本文のハッシュ
    （＝この書きかけが何を元に書き始められたか）。渡しておくと、
    再開時（load_draft_origin）に「書きかけを預けてから、他の誰かが
    ページを更新していないか」を判定する基準として使える
    （詳しくは editor.render_edit のコメント参照）。"""
    path = draft_path(wiki_dir, subpath)
    if path is None:
        return False
    if not (text or "").strip():
        # **空の書きかけは預からない**（Wiki設計者の報告、2026-09-10）。預かっても
        # 守れるものが無いのに、**保存のときにそれが「消す指示」として読まれ
        # かねない**（editor.posted_source 参照）。すでに預かっているものが
        # あれば消しておく——空になった、という事実は残しつつ、危険な形では
        # 残さない。
        delete_draft(wiki_dir, subpath)
        return True
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        return False
    if origin:
        origin_path = draft_origin_path(wiki_dir, subpath)
        if origin_path is not None:
            try:
                with open(origin_path, "w", encoding="utf-8") as f:
                    f.write(origin)
            except OSError:
                pass  # originが残せなくても、書きかけ自体は預かれているので致命的ではない
    return True


def load_draft(wiki_dir, subpath):
    """預かっている書きかけを返す。無ければNone。"""
    path = draft_path(wiki_dir, subpath)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def load_draft_origin(wiki_dir, subpath):
    """預かっている書きかけの、元になった本文のハッシュを返す。無ければNone
    （origin を渡さずに預けた・まだ save_draft に origin 引数が無かった頃の
    書きかけ、など）。"""
    path = draft_origin_path(wiki_dir, subpath)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def has_draft(wiki_dir, subpath):
    """そのページの書きかたを預かっているか。

    中身は要らず「あるか」だけを見たい場面（ページを開くたびの表示）で使う。
    読み込まずに済ませるため、load_draft とは別に用意している。"""
    path = draft_path(wiki_dir, subpath)
    return path is not None and os.path.isfile(path)


def delete_draft(wiki_dir, subpath):
    """預かりを解く（保存できた、あるいはページを消したとき）。"""
    path = draft_path(wiki_dir, subpath)
    if path is None:
        return False
    try:
        os.remove(path)
        ok = True
    except OSError:
        ok = False
    origin_path = draft_origin_path(wiki_dir, subpath)
    if origin_path is not None:
        try:
            os.remove(origin_path)
        except OSError:
            pass  # origin を持たない書きかけだった場合はそもそも無いので気にしない
    return ok


def drafted_subpaths(wiki_dir):
    """書きかけを預かっているページの実体パスを集合で返す。

    ページ一覧を組み立てるたびに1ページずつ確かめると、ページ数だけ
    ファイルを見にいくことになる。ここで一度に読んでおく。"""
    root = draft_root_of(wiki_dir)
    try:
        entries = os.listdir(root)
    except OSError:
        return set()
    found = set()
    for fname in entries:
        if not fname.endswith(DRAFT_EXT):
            continue
        found.add(subpath_of_backup_name(fname[: -len(DRAFT_EXT)]))
    return found
