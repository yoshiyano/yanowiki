"""ページ1枚を「保存した」ことにする後始末。

本文が変わったときにやることは、どこから変えても同じ3つになる。

    バックアップ    公開されていた内容 → 新しい内容 の差分を記録する
    平文ファイル    新しい内容を書き出す
    DB              本文を入れ直し、続けてタイトル・目次・リンクを取り出す

この3つは**揃っていないと意味がない**。差分だけ残ってDBが古いと次の差分が
狂い、DBだけ新しいとバックアップに履歴が残らない。順番も決まっていて、
差分は**書き換える前に**取らなければならない（変更前の内容が要るため）。

同じ手順が保存・復元・取り込み・改名の4か所に散っていたので、ここ1つに
まとめてある。呼ぶ側が違っても、記録のされかたが揃うようにするため。

## 「変更前」はDBの内容

差分の基準は**システムが最後に知っている内容**（DB）で、現存する平文ファイル
ではない。平文のほうを使うと、システムを通さない書き換えがあった場合に
その書き換え後を「変更前」と見なしてしまい、直接編集した分が記録から抜け落ちる
（詳しくは pagedb の冒頭）。

## ファイルを書くかどうか

取り込み（pagesync）だけは、**すでにファイルにある内容**を後から記録する操作
なので書き出さない。それ以外（保存・復元・改名によるリンクの直し）は書き出す。

## 途中の階層は、書く前にフォルダにしておく

`A` というページがあるところへ `A/B` を書くと、OSから見れば `A.txt` と
フォルダ `A/` が並ぶだけで、エラーにもならない。だがwikiでは `A` が
**読めなくなる**（`resolve_page_ref` はフォルダがあれば必ず `A/index` を
読むため。`pagedb.shadowed_pages` が拾うのがこの状態）。

そこで書き出す前に `pagemove.ensure_folder_path` を通し、途中の階層に
ページがあれば入口（`A/index`）へ移してから書く。**呼ぶ側が自分で
`open` する必要も、この決まりを覚える必要もない**ようにするため
（Wiki設計者の指示、2026-09-05）。
"""
import os

from wikilib import pagedb, stafflog
from wikilib.backup import backup_page
from wikilib.diskusage import invalidate
from wikilib.links import update_page_info
from wikilib.pagemove import ensure_folder_path
from wikilib.paths import farm_plugin_dir
from wikilib.plugins import build_markdown_renderer


def save_page(wiki_dir, config, subpath, ext, text, engine=None, path=None,
              known=None, merge=True, write=True, created=None):
    """ページ1枚分を保存したことにする。記録できたらTrue。

    subpath  ページの実体パス（拡張子抜き）
    ext      拡張子。記法がこれで決まるので、書き出す先とDBの両方に効く
    text     新しい内容
    engine   レンダラ。省略するとその場で作る（何枚も続けて保存するときは
             作ったものを渡し回すと速い）
    path     書き出す先。省略すると subpath + ext から決める
    known    差分の「変更前」。省略するとDBの内容（＝公開されていた内容）
    merge    直前の差分と統合してよいか。削除や復元のように「そうした事実を
             必ず残したい」場面では False にする
    write    平文ファイルを書き出すか。すでに書かれている内容を後から記録する
             場合（取り込み）だけ False にする
    created  新しくDBに入れるときの初回登録日時（既存の行があれば引き継がれる）
    """
    file_path = path or os.path.join(wiki_dir, subpath + ext)
    if known is None:
        known = pagedb.published_body(wiki_dir, subpath, "")
    # 助手の操作なら、書き換える前の平文を控えて記録する（wikilib.stafflog）
    staff = stafflog.actor(wiki_dir) if write else None
    old_text = stafflog.read_text(file_path) if staff is not None else None

    # 差分は書き換える前に取る（「変更前」が要るため）
    backup_page(wiki_dir, subpath, known, text, merge=merge)

    if write:
        # 途中の階層にページがあれば、先に入口へ移してフォルダを空ける。
        # そうしないと A.txt を残したまま A/ ができ、A が読めなくなる
        # （モジュール冒頭「途中の階層は、書く前にフォルダにしておく」）
        ensure_folder_path(wiki_dir, config, subpath)
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            return False

    if engine is None:
        engine = build_markdown_renderer(config, farm_plugin_dir(wiki_dir))
    pagedb.record_page(wiki_dir, subpath, ext, text, path=file_path, created=created)
    update_page_info(wiki_dir, subpath, engine, text, ext, config)
    # フッタに出る使用量を次の表示で数え直させる（Wiki設計者の指示、2026-08-31。
    # システムを通した変更はすぐ反映し、直接置かれたファイルは10分で追従する）
    invalidate(wiki_dir)
    if staff is not None and old_text != text:
        stafflog.record(wiki_dir, staff, "page.save", subpath,
                        "新しく作った" if old_text is None else "書き換えた",
                        before={"ext": ext, "text": old_text},
                        after={"ext": ext, "text": text})
    return True


def remove_page(wiki_dir, subpath, known=None):
    """ページが消えたことを記録する。消える前の内容を残してからDBの行を消す。

    差分は直前のものと統合しない。作ってすぐ消した場合、統合すると「空→空」で
    差し引きゼロになり、**消える直前の内容がどこにも残らなくなる**ため。"""
    if known is None:
        known = pagedb.published_body(wiki_dir, subpath, "")
    backup_page(wiki_dir, subpath, known, "", merge=False)
    invalidate(wiki_dir)
    return pagedb.remove_page(wiki_dir, subpath)
