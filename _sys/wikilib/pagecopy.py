"""ページ（フォルダなら中のページごと）を写す（2026-10-02）。

ファイル一覧（`wikilib.filesui`）のコピー（Ctrl+C → 貼り付け、Ctrl を押しながらのドラッグ）が
呼ぶ。Wiki設計者の指示「複製はやめて、コピー機能にしてください」（webFileDir の見本の
「複製」の代わりに、webFileDir の既定のコピーを使う形）。

ファイルを写すのと違い、次のことも一緒に行う（クロコの実装例）:

    アクセス制限    手で書いた記録（config/privileges）と、本文の #readauth・#writeauth の
                    記録（config/privileges.plugin）を、写しの名前にも足す。**写しのページを
                    作る前に**足す（制限の無い写しが一瞬でもできないように）。#readauth は
                    ページを開いたときに記録を書くので、本文を写すだけでは、誰かが開くまで
                    写しが誰でも読めてしまう
    添付            ページの添付（置き場所の直下のファイル）を写しの置き場所へ写す
    リンク          写したページの本文の中だけを直す。写したページどうしを指すリンクは
                    写しを指すように、相対の書きかたは写し先から同じページを指すように
                    （pagerename の書き換えと同じ `rewrite_links`。元のページ・ほかの
                    ページは書き換えない）
    保存            新しいページとして保存する（`pagesave.save_page`。差分が残る）

断るもの: 読めないページを含む（見えないページを写すことになる）、写し先に手で書いた
アクセス制限の記録がある、中断している名前の変更と範囲が重なる。どれも写す前に確かめる。

[中止]（webFileDir のジョブ）はページとページの間で効き、それまでに写したページは残す
（元のページには触れないので、残ったものを消せば元に戻る）。
"""
import os
import shutil

from wikilib import bulkscope, operations, pagedb, pagelist, privilege_records
from wikilib.attach import attach_dir_for
from wikilib.auth import PAGE_READ, PAGE_WRITE
from wikilib.pagelinks import rewrite_links
from wikilib.pagerename import moved_pages
from wikilib.pagesave import save_page
from wikilib.pluginlinks import rewrite_plugin_arg_links
from wikilib.paths import farm_plugin_dir, pagepath_of_subpath, resolve_page_ref
from wikilib.plugins import build_markdown_renderer


class CopyError(Exception):
    """写せない。`code` は webFileDir の誤りのコード（forbidden・bad_request・cancelled）。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def copy_pages(wiki_dir, config, old_root, new_root, is_folder, progress=None):
    """old_root（ページ、またはフォルダ）を new_root へ写す。写したページの実体パスの一覧を返す。

    呼ぶ側は、new_root が空いていること・名前が使えることを確かめておく（filesui）。"""
    progress = progress or operations.Progress()
    pairs = moved_pages(wiki_dir, old_root, new_root, is_folder)
    if not pairs:
        raise CopyError("bad_request", "写すページが見つかりません。")

    judge = pagelist.judge_for(wiki_dir)
    if any(judge.check(pagepath_of_subpath(old)) not in (PAGE_READ, PAGE_WRITE)
           for old, _ in pairs):
        # どのページかは言わない（見えないページの名前を出さない）
        raise CopyError("forbidden", "読む権限が無いページが含まれるため、写せません。")
    if any(judge.check(pagepath_of_subpath(new)) != PAGE_WRITE for _, new in pairs):
        raise CopyError("forbidden", "写し先にページを作る権限がありません。")
    busy = operations.overlapping(wiki_dir, (old_root, new_root))
    if busy is not None:
        raise CopyError("bad_request", operations.busy_message(busy))
    clash = privilege_records.rename_conflicts(wiki_dir, old_root, new_root)
    if clash:
        raise CopyError("bad_request", "写し先の «/{}» には、アクセス制限の記録がすでにあります"
                        "（/.admin/privileges）。先に整理してください。".format(clash[0][0]))

    # 写しを作る前にアクセス制限の記録を足す（冒頭の説明）。古い名前の行は残す
    # （名前の変更の1段目と同じ働き）
    if not privilege_records.copy_for_rename(wiki_dir, old_root, new_root):
        raise CopyError("bad_request", "アクセス制限の記録を書き換えられませんでした。")

    renames = {pagepath_of_subpath(old): pagepath_of_subpath(new) for old, new in pairs}
    engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir))
    registry = getattr(engine, "plugin_registry", None)
    copied = []
    progress.add_total(len(pairs))
    with bulkscope.scope():
        for old, new in pairs:
            if progress.cancelled():
                raise CopyError("cancelled", "途中で中止しました（{} ページのうち {} ページを"
                                "写しました）。".format(len(pairs), len(copied)))
            progress.begin(pagepath_of_subpath(old))
            ref = resolve_page_ref(wiki_dir, pagepath_of_subpath(old))
            if ref is None or not ref.exists:
                progress.advance()
                continue
            body, _ = rewrite_links(ref.body, new, ref.ext, renames, old_subpath=old,
                                    cache=pagedb.link_rows_of(wiki_dir, old),
                                    wiki_dir=wiki_dir, engine=engine)
            body, _ = rewrite_plugin_arg_links(body, ref.ext, new, renames, registry,
                                               old_subpath=old, wiki_dir=wiki_dir,
                                               engine=engine)
            _copy_attachments(wiki_dir, old, new)
            if not save_page(wiki_dir, config, new, ref.ext, body, engine=engine,
                             known="", merge=False):
                raise CopyError("bad_request", "«/{}» を書き出せませんでした。"
                                .format(pagepath_of_subpath(new)))
            copied.append(new)
            progress.advance()
    return copied


def _copy_attachments(wiki_dir, old, new):
    """ページの添付（置き場所の直下のファイル。下のフォルダは下位ページのもの）を写す。"""
    src = attach_dir_for(wiki_dir, old)
    dst = attach_dir_for(wiki_dir, new)
    if src is None or dst is None or not os.path.isdir(src):
        return
    files = [e for e in os.scandir(src) if e.is_file()]
    if not files:
        return
    os.makedirs(dst, exist_ok=True)
    for entry in files:
        shutil.copy2(entry.path, os.path.join(dst, entry.name))
