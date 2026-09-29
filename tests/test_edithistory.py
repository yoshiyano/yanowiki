#!/usr/bin/env python3
"""編集画面の「履歴」タブ（wikilib.backupui）のテスト。

編集画面の「添付ファイル」の右に「履歴」タブがあり、そこへ差分・復元の画面を
`<iframe>` で埋め込む（Wiki設計者の指示、2026-09-19）。読み書きはページ自身のURLへの
POST（`?cmd=history`）で行う（2026-09-28、`/.backup` をURLごとやめた）。見ているのは
次のこと。

  タブ           「添付ファイル」の右に出る。開くまで読み込まない（`data-src`）
  受け口         `?cmd=history` の表示・データ・復元。どれもそのページの編集の権限が要る
  復元のあと     303で戻さず、済んだ印（data-restored）を付けた表示をそのまま返す
  履歴が無いとき  「編集履歴はありません」（画面の描画はJSなので、文言はJS側にある）

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_edithistory.py     （このファイルだけ）
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_editprivilege import FARM, EditPrivilegeTestBase  # noqa: E402

from wikilib import backupui, editor  # noqa: E402
from wikilib.pagesave import save_page  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestTab(EditPrivilegeTestBase):

    def open_edit(self, query=""):
        env = self.post_env(cmd="edit")
        env["QUERY_STRING"] = query
        self.login_as("admin", env)
        res = editor.render_edit(self.wiki_dir, {}, FARM, "Open", False)
        raw = res.body if hasattr(res, "body") else res
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def test_添付ファイルの右に履歴のタブが出る(self):
        html = self.open_edit()
        self.assertIn('data-tab="history"', html)
        self.assertGreater(html.index('data-tab="history"'), html.index('data-tab="attach"'))
        self.assertIn(">履歴</button>", html)

    def test_開くまで読み込まない(self):
        """`src` は付けず、`data-src` に持たせる（JSが最初に開かれたときに移す）。"""
        html = self.open_edit()
        frame = html.split('class="edit-history-frame"', 1)[1].split(">", 1)[0]
        self.assertNotIn(" src=", frame)
        self.assertIn('data-src="/=testwiki/Open?cmd=history"', frame)
        self.assertIn('name="edit-history-frame"', frame)  # フォームのPOSTの宛先

    def test_履歴のタブを最初から開ける(self):
        html = self.open_edit("tab=history")
        self.assertIn('data-active-tab="history"', html)

    def test_知らないタブは編集に戻る(self):
        html = self.open_edit("tab=nope")
        self.assertIn('data-active-tab="edit"', html)


class TestHistoryHtml(unittest.TestCase):

    def test_受け口はページ自身のURL(self):
        self.assertEqual(backupui.history_url("/=w", "Tech/日本語"),
                         "/=w/Tech/%E6%97%A5%E6%9C%AC%E8%AA%9E?cmd=history")

    def test_ページは送らない(self):
        html = backupui.build_history_html("/Open?cmd=history", "Open")
        self.assertNotIn('name="page"', html)
        self.assertIn('data-page="Open"', html)

    def test_復元の直後だけ済んだ印を付ける(self):
        self.assertNotIn("data-restored", backupui.build_history_html("/a", "Open"))
        html = backupui.build_history_html("/a", "Open", message="戻しました", restored=True)
        self.assertIn('data-restored="1"', html)
        self.assertIn('data-message="戻しました"', html)

    def test_ヘッダーも左の欄も出さない(self):
        page = backupui.build_history_page_html("wikiSystem", "<div></div>",
                                                "/.history", "/.vendor")
        self.assertNotIn("bk-head", page)
        self.assertIn("bk-embed", page)
        self.assertIn('href="/.history.css"', page)
        self.assertNotIn("bk-left", backupui.build_history_html("/a", "Open"))


class TestHistoryEndpoint(EditPrivilegeTestBase):
    """`POST <ページ>?cmd=history`。どれもそのページの編集の権限（W）が要る。"""

    def setUp(self):
        super().setUp()
        # 履歴を1つ作っておく（保存すると変更の記録が残る）
        self.assertTrue(save_page(self.wiki_dir, {}, "Open", ".md", "書き換えた\n"))

    def call(self, uid, **fields):
        env = self.post_env(**fields)
        env["QUERY_STRING"] = "cmd=history"
        self.login_as(uid, env)
        return backupui.render_history(self.wiki_dir, {}, FARM, False, "Open")

    def body(self, res):
        raw = res.body if hasattr(res, "body") else res
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def test_表示(self):
        res = self.call("admin")
        self.assertEqual(res.status_code, 200)
        self.assertIn('class="bk-shell"', self.body(res))

    def test_履歴の一覧と本文(self):
        res = self.call("admin", data="history")
        data = json.loads(self.body(res))
        self.assertEqual(data["page"], "Open")
        key = data["history"][0]["key"]
        version = json.loads(self.body(self.call("admin", data="version", key=key)))
        self.assertEqual(version["current"], "書き換えた\n")

    def test_編集できる人だけ(self):
        self.tighten(True)   # 未ログインは閲覧だけ
        self.assertEqual(self.call(None).status_code, 403)
        self.assertEqual(self.call(None, data="history").status_code, 403)
        self.assertEqual(self.call("alice").status_code, 200)

    def test_閲覧だけのページの履歴は読めない(self):
        self.rule("Open", "R", "alice, bob")
        self.rule("Open", "W", "bob")
        self.assertEqual(self.call("alice", data="history").status_code, 403)
        self.assertEqual(self.call("bob", data="history").status_code, 200)

    def test_復元のあとは済んだ印を付けて返す(self):
        with mock.patch.object(backupui, "restore_backup", return_value=(True, "戻しました")) as r:
            res = self.call("admin", do="restore", key="k", base_rev="r", page="Other")
        self.assertEqual(res.status_code, 200)
        self.assertIn('data-restored="1"', self.body(res))
        # 対象のページはURLから決め、フォームの page は使わない
        self.assertEqual(r.call_args[0][2], "Open")

    def test_編集できない人は戻せない(self):
        self.tighten(True)
        with mock.patch.object(backupui, "restore_backup") as restore:
            res = self.call(None, do="restore", key="k", base_rev="r")
        self.assertEqual(res.status_code, 403)
        self.assertFalse(restore.called)

    def test_履歴の削除は受け付けない(self):
        res = self.call("admin", do="purge", pages="Open")
        self.assertEqual(res.status_code, 400)

    def test_backupのURLはもう無い(self):
        from wikilib import paths
        self.assertFalse(hasattr(paths, "BACKUP_URLPATH"))


class TestScript(unittest.TestCase):
    """JavaScript は実ブラウザでしか動かせないので、要になる文言だけを見ておく。"""

    def read(self, *parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
            return f.read()

    def test_履歴が無いときの文言(self):
        self.assertIn("変更履歴はありません", self.read("_sys", "editor", "editor.js"))
        self.assertIn("変更履歴はありません", self.read("_sys", "wikilib", "editor.py"))

    def test_履歴の一覧は親が持ち_選んだ時点を埋め込みへ知らせる(self):
        self.assertIn("wiki-backup-select", self.read("_sys", "editor", "editor.js"))
        self.assertIn("wiki-backup-select", self.read("_sys", "backupui", "backup.js"))

    def test_復元を親へ知らせて_親は受けて開き直す(self):
        self.assertIn("wiki-backup-restored", self.read("_sys", "backupui", "backup.js"))
        editor_js = self.read("_sys", "editor", "editor.js")
        self.assertIn("wiki-backup-restored", editor_js)
        # 出所を確かめてから受ける
        self.assertIn("event.origin !== window.location.origin", editor_js)


if __name__ == "__main__":
    unittest.main()
