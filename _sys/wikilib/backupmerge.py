"""バックアップ履歴からの部分復元（diffmergeによる取り込みマージ）。

wikilib.backupui.restore_backup は「選んだ時点にまるごと戻す」操作。
こちらは、2文書マージ（_sys/vendor/diffmerge、render(...,{merge:true})）で
相違点ごとに選んで取り込んだ結果を保存する（ブラウザ側で完成済みのテキストを
受け取るだけで、マージ処理そのものはサーバー側では行わない）。

Wiki設計者の指示（2026-08-29）: 「これまでは戻すことしかできませんでしたが、
今回のmergeを活用することで、一部分のみを戻すことができるようになります。」

## 楽観ロック（base_rev）

マージ画面は「開いたときの現在」を土台に取り込み結果を組み立てる。保存を
押すまでの間に他の変更が入っていると、その組み立て直後の土台と保存直前の
実際の現在とがずれ、せっかくの取り込み結果が古い内容を巻き戻すことになり
かねない。そこで、画面を開いたときの現在の内容のハッシュ（backup.content_rev）
を base_rev として一緒に送ってもらい、保存直前に取り直したハッシュと突き合わせる。
食い違えば保存せずに断る（Wiki設計者の指示、2026-08-31）。
"""
from wikilib.backup import backed_up_subpaths, content_rev
from wikilib.pagedb import published_body
from wikilib.pagesave import save_page
from wikilib.paths import page_ext_of_subpath, page_file_path


def apply_partial_merge(wiki_dir, config, subpath, merged_text, base_rev):
    """diffmergeで取り込んだ結果を保存する。(成否, 知らせる文言) を返す。

    restore_backup と同じ形の戻り値・同じ制約（空にする取り込みは断る）に
    そろえてある。「変更前」の基準（known）は、restore_backup と同じく
    保存時点のDBの内容（＝いまの公開内容）にする。"""
    if not subpath or subpath not in backed_up_subpaths(wiki_dir):
        return False, "対象のページを選んでください。"

    current = published_body(wiki_dir, subpath, "")
    if content_rev(current) != base_rev:
        return False, ("保存の間に他の変更が入ったため、取り込めませんでした。"
                       "画面を読み込み直してください。")
    if merged_text == current:
        return False, "取り込んだ内容が、いまのページと同じです。"
    if not merged_text.strip():
        # restore_backup と同じ理由（空にする＝削除の手順を勝手に肩代わりしない）
        return False, ("取り込んだ結果、ページが空になります。"
                       "削除したい場合は編集画面で本文を空にして保存してください。")

    ext = page_ext_of_subpath(wiki_dir, subpath)
    path = page_file_path(wiki_dir, subpath, ext)
    if path is None:
        return False, "書き戻す先を決められませんでした。"

    # 取り込みも1つの保存として記録する（統合すると直前の差分と相殺されて
    # 「一部を取り込んだ」という事実が残らないことがあるため、まとめずに1本残す）
    if not save_page(wiki_dir, config, subpath, ext, merged_text,
                     path=path, known=current, merge=False):
        return False, "保存できませんでした。"
    return True, "選んだ内容を取り込んで保存しました。"
