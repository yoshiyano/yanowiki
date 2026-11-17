#!/usr/bin/env python3
"""表記の変換（編集画面の表記ボタン → 管理ページ → 確定・やめる）のテスト（wikilib.markupswitch）。

見ていること:

  開く      編集画面の今の本文（書きかけを含む）を変換し、`=名前.拡張子` に書き出して画面を出す
  確定      変換後の内容で保存し直し、元の拡張子のファイルと `=` のファイル・書きかけを消す。
            履歴に1回の保存として残る
  やめる    `=` のファイルを消し、編集画面へ戻る（ページはそのまま）
  断る      開いてからページが書き換えられた・同じ名前の別の書きかたのファイルがある・
            新しいページ・編集の権限が無い
  後片付け  ページを消す・名前を変えると `=` のファイルも消える。ページの列挙には出ない
  編集画面  表記ボタンが `cmd=convert` を送る。既にあるページでは「書きかた」の選択を隠す

実行:
    _venv/bin/python3 tests/test_markupswitch.py
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_editprivilege import BODY, FARM, EditPrivilegeTestBase  # noqa: E402

from wikilib import draft, editor, markupswitch, pagedb, paths  # noqa: E402
from wikilib.backup import backup_history  # noqa: E402

PAGE = "Open"


def html_of(res):
    raw = res.body if hasattr(res, "body") else res
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


class SwitchBase(EditPrivilegeTestBase):

    def convert(self, uid="admin", **fields):
        """フォームを送って serve_convert を呼び、(応答, HTML) を返す。"""
        fields.setdefault("cmd", "convert")
        self.login_as(uid, self.post_env(**fields))
        res = markupswitch.serve_convert(self.wiki_dir, {}, FARM, False, PAGE)
        return res, html_of(res)

    def path(self, name):
        return os.path.join(self.wiki_dir, name)

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as f:
            return f.read()

    def open_page(self, source=BODY):
        """表記ボタンを押したときと同じ送りかた。管理ページの hidden を返す。"""
        res, html = self.convert(source=source, origin=editor.source_hash(BODY))
        self.assertEqual(res.status_code, 200, html[:500])
        fields = dict(re.findall(r'name="(base|conv)" value="([^"]*)"', html))
        return html, fields


class TestOpen(SwitchBase):

    def test_今の本文を変換して等号のファイルに書き出す(self):
        html, fields = self.open_page("# 題名\n\n**太字**です。\n")
        self.assertTrue(os.path.isfile(self.path("=Open.txt")))
        self.assertIn("''太字''", self.read("=Open.txt"))
        self.assertIn("表記の変換", html)
        self.assertIn('data-tab="from"', html)
        self.assertIn('data-tab="to"', html)
        self.assertEqual(set(fields), {"base", "conv"})
        # 元のファイルは触らない
        self.assertEqual(self.read("Open.md"), BODY)

    def test_書きかけを預けてあればそれを変換する(self):
        draft.save_draft(self.wiki_dir, PAGE, "書きかけの本文\n", editor.source_hash(BODY))
        self.convert(from_draft="1", origin=editor.source_hash(BODY))
        self.assertIn("書きかけの本文", self.read("=Open.txt"))

    def test_編集中にほかで更新されていれば断る(self):
        res, html = self.convert(source="自分の書き換え\n", origin="old-hash")
        self.assertFalse(os.path.exists(self.path("=Open.txt")))
        self.assertIn("ほかの場所でページが更新されています", html)

    def test_同じ名前の別の書きかたのファイルがあれば断る(self):
        with open(self.path("Open.txt"), "w", encoding="utf-8") as f:
            f.write("* txt\n")
        # .txt が読まれるので、変換先は .md（既にある）
        res, html = self.convert(source="* txt\n", origin="")
        self.assertIn("ページの重複を整理してください", html)
        self.assertEqual(self.read("Open.md"), BODY)

    def test_新しいページは変換しない(self):
        self.login_as("admin", self.post_env(cmd="convert", source="x\n"))
        res = markupswitch.serve_convert(self.wiki_dir, {}, FARM, False, "NoSuch")
        self.assertIn("新しいページは変換できません", html_of(res))
        self.assertEqual([n for n in os.listdir(self.wiki_dir) if n.startswith("=")], [])

    def test_編集の権限が無ければ断る(self):
        self.rule("Open", "W", "alice")
        res, _html = self.convert(uid="bob", source="x\n", origin="")
        self.assertEqual(res.status_code, 403)
        self.assertFalse(os.path.exists(self.path("=Open.txt")))


class TestApply(SwitchBase):

    def test_確定すると書きかたを変えて保存し直す(self):
        _html, fields = self.open_page("# 題名\n\n**太字**です。\n")
        res, html = self.convert(step="apply", **fields)
        self.assertEqual(res.status_code, 200)
        self.assertIn("PukiWiki記法に変換して保存しました", html)
        self.assertFalse(os.path.exists(self.path("Open.md")))
        self.assertFalse(os.path.exists(self.path("=Open.txt")))
        self.assertIn("''太字''", self.read("Open.txt"))
        self.assertTrue(pagedb.load_page(self.wiki_dir, PAGE)["path"].endswith(".txt"))
        # 履歴に残っている（変換前へ戻せる）
        self.assertTrue(backup_history(self.wiki_dir, PAGE, self.read("Open.txt")))

    def test_確定すると書きかけは消える(self):
        draft.save_draft(self.wiki_dir, PAGE, "書きかけ\n", editor.source_hash(BODY))
        res, html = self.convert(from_draft="1", origin=editor.source_hash(BODY))
        fields = dict(re.findall(r'name="(base|conv)" value="([^"]*)"', html))
        self.convert(step="apply", **fields)
        self.assertIsNone(draft.load_draft(self.wiki_dir, PAGE))
        self.assertIn("書きかけ", self.read("Open.txt"))

    def test_開いてからページが変わっていれば保存しない(self):
        _html, fields = self.open_page()
        with open(self.path("Open.md"), "w", encoding="utf-8") as f:
            f.write("ほかの人の更新\n")
        res, html = self.convert(step="apply", **fields)
        self.assertIn("保存はしていません", html)
        self.assertEqual(self.read("Open.md"), "ほかの人の更新\n")
        self.assertFalse(os.path.exists(self.path("Open.txt")))
        self.assertFalse(os.path.exists(self.path("=Open.txt")))

    def test_変換したものが書き換えられていれば保存しない(self):
        _html, fields = self.open_page()
        with open(self.path("=Open.txt"), "w", encoding="utf-8") as f:
            f.write("差し替え\n")
        res, html = self.convert(step="apply", **fields)
        self.assertIn("保存はしていません", html)
        self.assertEqual(self.read("Open.md"), BODY)


class TestCancel(SwitchBase):

    def test_やめると等号のファイルを消して編集画面へ戻る(self):
        self.open_page()
        res, html = self.convert(step="cancel")
        self.assertEqual(res.status_code, 200)
        self.assertIn("表記の変換をやめました", html)
        self.assertFalse(os.path.exists(self.path("=Open.txt")))
        self.assertEqual(self.read("Open.md"), BODY)


class TestTempFiles(SwitchBase):

    def test_ページの列挙に出ない(self):
        self.open_page()
        self.assertEqual([p for p, _ in paths.iter_pages(self.wiki_dir)], [PAGE])

    def test_ページを消すと一緒に消える(self):
        self.open_page()
        from wikilib.pagesave import remove_page
        os.remove(self.path("Open.md"))
        remove_page(self.wiki_dir, PAGE, known=BODY)
        self.assertFalse(os.path.exists(self.path("=Open.txt")))

    def test_名前を変えると一緒に消える(self):
        self.open_page()
        from wikilib.pagerename import rename_page
        result = rename_page(self.wiki_dir, {}, PAGE, "Renamed")
        self.assertTrue(os.path.isfile(self.path("Renamed.md")), result)
        self.assertFalse(os.path.exists(self.path("=Open.txt")))
        self.assertFalse(os.path.exists(self.path("=Renamed.txt")))

    def test_フォルダの入口のページは同じフォルダに置く(self):
        self.assertEqual(markupswitch.temp_path(self.wiki_dir, "Tech/index", ".md"),
                         os.path.realpath(self.path("Tech/=index.md")))


class TestEditorScreen(SwitchBase):

    def edit_html(self, page=PAGE):
        self.login_as("admin", self.post_env(cmd="edit"))
        return html_of(editor.render_edit(self.wiki_dir, {}, FARM, page, False))

    def test_表記ボタンはcmd_convertを送る(self):
        html = self.edit_html()
        badge = re.search(r'<button[^>]*class="edit-markup-badge"[^>]*>', html).group(0)
        self.assertIn('form="edit-actions"', badge)
        self.assertIn('value="convert"', badge)
        self.assertNotIn("disabled", badge)
        self.assertIn('id="edit-actions"', html)

    def test_既にあるページでは書きかたの選択を隠す(self):
        self.assertRegex(self.edit_html(), r'<div class="edit-markup"[^>]*hidden')

    def test_新しいページでは書きかたを選べて表記ボタンは押せない(self):
        html = self.edit_html("NoSuch")
        self.assertNotRegex(html, r'<div class="edit-markup"[^>]*hidden')
        badge = re.search(r'<button[^>]*class="edit-markup-badge"[^>]*>', html).group(0)
        self.assertIn("disabled", badge)


if __name__ == "__main__":
    unittest.main()
