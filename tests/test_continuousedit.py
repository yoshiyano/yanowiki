#!/usr/bin/env python3
"""**連続編集**（編集画面のチェック）のテスト。

入っていれば、保存と内容破棄のあとに元のページへ戻らず、編集画面に留まる
（Wiki設計者の指示、2026-09-19）。見ているのは次のこと。

  保存・内容破棄   チェックが入っていれば編集画面（200）、無ければ従来どおりページへ303
  一時中断         チェックに関わらず、いつもページへ戻る
  削除の保存       本文を空にしての保存（＝ページの削除）は、チェックに関わらずページへ戻る
  画面             チェックが出ていて、既定で入っている
  タブ             開き直したとき、選んでいたタブを保つ
  押せるか         本文が保存されている内容（DB）と同じあいだは、保存・内容破棄を押せない

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_continuousedit.py     （このファイルだけ）
"""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_editprivilege import BODY, FARM, EditPrivilegeTestBase  # noqa: E402

from wikilib import draft, editor, pagedb  # noqa: E402

PAGE = "Open"
PAGE_URL = f"/=testwiki/{PAGE}"


class ContinuousBase(EditPrivilegeTestBase):

    def post(self, page=PAGE, **fields):
        """管理者としてフォームを送り、(応答, HTML) を返す。"""
        self.login_as("admin", self.post_env(**fields))
        res = editor.render_edit(self.wiki_dir, {}, FARM, page, False)
        raw = res.body if hasattr(res, "body") else res
        html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return res, html

    def saved(self, page=PAGE):
        with open(os.path.join(self.wiki_dir, page + ".md"), encoding="utf-8") as f:
            return f.read()


class TestSave(ContinuousBase):

    def test_チェック無しは従来どおりページへ戻る(self):
        res, _html = self.post(cmd="save", source="書き換えました\n", origin="")
        self.assertEqual(res.status_code, 303)
        self.assertTrue(res.headers["Location"].endswith("/" + PAGE))
        self.assertEqual(self.saved(), "書き換えました\n")

    def test_チェックがあれば編集画面に留まる(self):
        res, html = self.post(cmd="save", source="書き換えました\n", origin="",
                              continuous="1")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("Location", res.headers)
        self.assertIn("保存しました", html)
        self.assertEqual(self.saved(), "書き換えました\n")     # 保存は行われている

    def test_留まった画面には保存した内容が入っている(self):
        _res, html = self.post(cmd="save", source="書き換えました\n", origin="",
                               continuous="1")
        self.assertIn(">書き換えました\n</textarea>", html)

    def test_留まった画面のoriginは保存後の内容のもの(self):
        """次の保存が「競合」と読まれないように、基準は保存した内容に更新される。"""
        _res, html = self.post(cmd="save", source="一回目\n", origin="", continuous="1")
        origin = html.split('data-origin="', 1)[1].split('"', 1)[0]
        self.assertEqual(origin, editor.source_hash("一回目\n"))
        res, _html = self.post(cmd="save", source="二回目\n", origin=origin,
                               continuous="1")
        self.assertEqual(res.status_code, 200)                 # 競合画面へ送られない
        self.assertEqual(self.saved(), "二回目\n")

    def test_続けて何度でも保存できる(self):
        origin = ""
        for n in range(3):
            res, html = self.post(cmd="save", source=f"{n}回目\n", origin=origin,
                                  continuous="1")
            self.assertEqual(res.status_code, 200)
            origin = html.split('data-origin="', 1)[1].split('"', 1)[0]
        self.assertEqual(self.saved(), "2回目\n")

    def test_預かっていた書きかけは保存で消える(self):
        draft.save_draft(self.wiki_dir, PAGE, "書きかけ")
        self.post(cmd="save", source="書き換えました\n", origin="", continuous="1")
        self.assertIsNone(draft.load_draft(self.wiki_dir, PAGE))

    def test_新しいページを作って留まる(self):
        res, html = self.post(page="Fresh", cmd="save", source="新しい\n", origin="",
                              continuous="1")
        self.assertEqual(res.status_code, 200)
        with open(self._fresh_path(), encoding="utf-8") as f:
            self.assertEqual(f.read(), "新しい\n")
        # 作ったあとは「まだありません」ではなく、ふつうの編集画面
        self.assertNotIn("まだありません", html)

    def _fresh_path(self):
        for ext in (".txt", ".md"):
            path = os.path.join(self.wiki_dir, "Fresh" + ext)
            if os.path.isfile(path):
                return path
        self.fail("ページが作られていない")

    def test_新しいページを空のまま保存しても作らず留まる(self):
        res, html = self.post(page="Fresh", cmd="save", source="", origin="",
                              continuous="1")
        self.assertEqual(res.status_code, 200)
        self.assertIn("ページは作りませんでした", html)

    def test_本文を空にする保存は削除なのでページへ戻る(self):
        res, _html = self.post(cmd="save", source="", origin="", continuous="1")
        self.assertEqual(res.status_code, 303)
        self.assertTrue(res.headers["Location"].endswith("/" + PAGE))


class TestDiscard(ContinuousBase):

    def test_チェック無しは従来どおりページへ戻る(self):
        draft.save_draft(self.wiki_dir, PAGE, "書きかけ")
        res, _html = self.post(cmd="discard")
        self.assertEqual(res.status_code, 303)
        self.assertIsNone(draft.load_draft(self.wiki_dir, PAGE))

    def test_チェックがあれば書きかけを消して編集画面に留まる(self):
        draft.save_draft(self.wiki_dir, PAGE, "書きかけ")
        res, html = self.post(cmd="discard", continuous="1")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(draft.load_draft(self.wiki_dir, PAGE))
        self.assertIn("破棄しました", html)
        # 出ているのは保存されている内容。書きかけは残っていない
        self.assertIn(BODY.strip().splitlines()[0], html)
        self.assertNotIn("書きかけ</textarea>", html)
        self.assertEqual(self.saved(), BODY)


class TestPause(ContinuousBase):

    def test_チェックがあっても一時中断はページへ戻る(self):
        res, _html = self.post(cmd="pause", source="書きかけ\n", origin="",
                               continuous="1")
        self.assertEqual(res.status_code, 303)
        self.assertTrue(res.headers["Location"].endswith("/" + PAGE))
        self.assertEqual(draft.load_draft(self.wiki_dir, PAGE), "書きかけ\n")


class TestScreen(ContinuousBase):

    def test_チェックが出ていて既定で入っている(self):
        _res, html = self.post(cmd="edit")
        self.assertIn('class="edit-continuous-check" checked', html)
        self.assertIn("連続編集", html)

    def test_ファイル一覧の右に置く(self):
        # もとは「名前を変える」の右。その入口は 2026-09-29 に外した
        _res, html = self.post(cmd="edit")
        self.assertGreater(html.index('class="edit-continuous"'),
                           html.index('class="edit-files"'))

    def test_タブを保つ(self):
        _res, html = self.post(cmd="save", source="書き換え\n", origin="",
                               continuous="1", tab="attach")
        self.assertIn('data-active-tab="attach"', html)

    def test_タブの指定が無ければ編集(self):
        _res, html = self.post(cmd="save", source="書き換え\n", origin="", continuous="1")
        self.assertIn('data-active-tab="edit"', html)


class TestButtonsEnabled(ContinuousBase):
    """**変更が無いときは、保存と内容破棄を押せない**（Wiki設計者の指示、2026-09-19）。

    比べる相手は「更新状況」タブの差分と同じ、システムが知っている本文（DB）。
    差分が空なら未変更、という1つの規則。入力に合わせた付け外しは editor.js が
    するので、ここで見るのは**開いた直後の状態**と、比べる本文の渡しかた。"""

    def buttons(self, html):
        """(保存が押せない, 内容破棄が押せない)。"""
        def off(name):
            tag = html.split(f'class="{name}"', 1)[1].split(">", 1)[0]
            return "disabled" in tag
        return off("edit-save"), off("edit-discard")

    def test_開いた直後は_どちらも押せない(self):
        _res, html = self.post(cmd="edit")
        self.assertEqual(self.buttons(html), (True, True))

    def test_書きかけを復元して開けば_どちらも押せる(self):
        draft.save_draft(self.wiki_dir, PAGE, "書きかけです\n")
        _res, html = self.post(cmd="edit")
        self.assertEqual(self.buttons(html), (False, False))

    def test_まだ無いページも_空のあいだは押せない(self):
        _res, html = self.post(page="Fresh", cmd="edit")
        self.assertEqual(self.buttons(html), (True, True))

    def test_連続編集で保存した直後は_押せない(self):
        _res, html = self.post(cmd="save", source="書き換えました\n", origin="",
                               continuous="1")
        self.assertEqual(self.buttons(html), (True, True))

    def test_連続編集で内容破棄した直後も_押せない(self):
        draft.save_draft(self.wiki_dir, PAGE, "書きかけ")
        _res, html = self.post(cmd="discard", continuous="1")
        self.assertEqual(self.buttons(html), (True, True))

    def test_比べる本文がJSONで渡る(self):
        _res, html = self.post(cmd="edit")
        block = html.split('class="edit-saved">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(block), BODY)

    def test_比べる相手はDBの本文(self):
        """平文ファイルと食い違っていれば、DBのほうを渡す（更新状況タブと同じ）。
        画面に出ているのは平文ファイルの本文なので、押せる（差分がある）。"""
        pagedb.record_page(self.wiki_dir, PAGE, ".md", "DBにある本文\n")
        _res, html = self.post(cmd="edit")
        block = html.split('class="edit-saved">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(block), "DBにある本文\n")
        self.assertEqual(self.buttons(html), (False, False))

    def test_JSONに閉じタグが混ざっても脱出されない(self):
        """本文に `</script>` があっても、JSONの入れ物を閉じられない。"""
        body = "前\n</script><b>x</b>\n後\n"
        with open(os.path.join(self.wiki_dir, PAGE + ".md"), "w", encoding="utf-8") as f:
            f.write(body)
        pagedb.record_page(self.wiki_dir, PAGE, ".md", body)
        _res, html = self.post(cmd="edit")
        block = html.split('class="edit-saved">', 1)[1].split("</script>", 1)[0]
        self.assertNotIn("<", block)
        self.assertEqual(json.loads(block), body)


class TestScriptGuard(unittest.TestCase):
    """editor.js の名前の衝突を防ぐ見張り。

    保存側の変数（ボタンだけの `<form>`）を `actions` と書いたため、同じ関数にある
    ツールバー操作の対応表 `var actions = {}` と**同じ変数**になっていた
    （2026-09-10の修正から）。開いた直後はツールバーのボタンが効かず、記法を
    選び直すと今度は保存が黙って失敗した。JavaScript は実ブラウザでしか動かせないので、
    せめて宣言が1つだけであることを見ておく。"""

    def test_actionsの宣言は1つだけ(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "_sys", "editor", "editor.js")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        # 行頭の宣言だけを数える（説明のコメントに書いた文字には当たらない）
        self.assertEqual(len(re.findall(r"^\s*var actions\b", text, re.M)), 1)
        # 保存側は別の名前で持っている
        self.assertIn('var actionForm = document.querySelector(".edit-actions")', text)

    def test_ボタン行の中身は文書全体から探す(self):
        """画面が低い（高さ500px未満）と、`.edit-buttons` が `.page-editor` の外へ移る。
        `form.querySelector` で探すと見失い、Ctrl+S・ESC が効かなくなり、一時保存の
        表示も出なくなる（2026-09-20に直した）。"""
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "_sys", "editor", "editor.js")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for cls in ("edit-save", "edit-pause", "edit-discard", "edit-draft-state",
                    "edit-rename", "edit-continuous"):
            self.assertNotIn(f'form.querySelector(".{cls}', text, cls)


if __name__ == "__main__":
    unittest.main()
