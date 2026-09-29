#!/usr/bin/env python3
"""Wikiを消す（`/.delwiki`）のテスト。

**消す前に必ず書庫（`<Wiki名>.<yymmdd_hhmmss>.7z`）へ固めてから消す**という
決まり（Wiki設計者の指示、2026-09-18）を、実際に7zを作って展開し直すところまで
確かめる。ここで見るのは次の5つ。

  - **4段の手続きを、順番どおりにしか通れない**（`TestFlow`）。名前・管理者の
    パスワード・いまの様子・最後の確認。どれか1つでも違えば先へ進まない
  - **段と段をつなぐ合札**（`TestToken`）。他人のuidでは通らず、用途違いの札も
    通らない。3段目を飛ばした最後のPOSTも通らない
  - **書庫ができるまで実体を消さない**（`TestArchive`）。作りかけは `.7z.part`
    の名前で、出来上がってから `.7z` になる
  - **やめたら書庫も消える**（`TestCancel`。Wiki設計者の指示）
  - **展開すると元に戻る**（`TestRoundTrip`）。これが成り立たないなら、
    この機能は「消すだけ」になってしまう

3段目に書いてもらう値そのもの（作りかたと書きかたの揺れの吸収）は
`wikilib.wikimark` の受け持ちで、試すのは `tests/test_wikimark.py`。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_delwiki.py     （このファイルだけ）
"""
import io as _io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlencode

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import (  # noqa: E402
    allwiki, auth, delwiki, diskusage, paths, userdb, wikimark,
)
from wikilib.paths import LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name  # noqa: E402

HOME = "home"        # 既定Wiki（この画面を開く側）
TARGET = "sandbox"   # 消される側
HOME_PW = "homepw"
TARGET_PW = "sandpw"

has7z = delwiki.sevenzip_program() is not None
need7z = unittest.skipUnless(has7z, "7z を作る道具が入っていない")


class DelwikiBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="delwiki-")
        self.wikidata = os.path.join(self.work, "wikidata")
        self.wiki_dirs = {}
        for farm, password in ((HOME, HOME_PW), (TARGET, TARGET_PW)):
            d = os.path.join(self.wikidata, farm, "wiki")
            os.makedirs(d)
            self.wiki_dirs[farm] = d
            userdb.create_db(d, password)
            with open(os.path.join(d, "index.md"), "w", encoding="utf-8") as f:
                f.write("# {}\n\nこのWikiのトップページ。\n".format(farm))
        # 消える中身が本当に消えた（＝書庫から戻った）ことを見るための目印
        os.makedirs(os.path.join(self.wikidata, TARGET, "attach", "index"))
        with open(os.path.join(self.wikidata, TARGET, "attach", "index", "note.txt"),
                  "w", encoding="utf-8") as f:
            f.write("添付も一緒に入っているか\n")

        self.kept_wikidata = paths.WIKIDATA_DIR
        self.kept_allwiki = allwiki.WIKIDATA_DIR
        paths.WIKIDATA_DIR = self.wikidata
        allwiki.WIKIDATA_DIR = self.wikidata
        self.kept_secret = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        self.config = {"farm": {"default": HOME}}
        # 使用量は10分使い回されるので、テストごとに数え直させる
        diskusage.invalidate(self.wiki_dirs[TARGET])

    def tearDown(self):
        # 書庫の出来上がりを待たないテストもあるので、裏の書庫づくりが終わってから
        # 片づける（先に片づけると、7zが一時ディレクトリを見失って失敗する）
        for thread in threading.enumerate():
            if thread.name == delwiki.ARCHIVE_THREAD_NAME:
                thread.join(timeout=30)
        paths.WIKIDATA_DIR = self.kept_wikidata
        allwiki.WIKIDATA_DIR = self.kept_allwiki
        auth.SECRET_PATH = self.kept_secret
        shutil.rmtree(self.work, ignore_errors=True)

    # ---- 画面を呼ぶ ---------------------------------------------------------

    def post(self, uid="admin", **fields):
        """`/.delwiki` へPOSTする。`uid=None` ならログインしていない状態。"""
        body = urlencode({k: v for k, v in fields.items() if v is not None}
                         ).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": _io.BytesIO(body),
            "REMOTE_ADDR": "127.0.0.1",
        }
        if uid is not None:
            user = userdb.find_by_uid(self.wiki_dirs[HOME], uid)
            token = auth.session_token(uid, HOME, user["pw"])
            environ["HTTP_COOKIE"] = (
                f"{wiki_cookie_name(LOGIN_COOKIE, HOME)}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, HOME)}={token}")
        bottle.request.environ.clear()
        bottle.request.environ.update(environ)
        return delwiki.render_delwiki(self.wiki_dirs[HOME], self.config, HOME, False)

    def get(self, uid="admin"):
        return self.post(uid=uid)  # 中身の無いPOSTも1段目に戻る（GETと同じ画面）

    def body_of(self, out):
        raw = out.body if hasattr(out, "body") else out
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def status_of(self, out):
        return getattr(out, "status_code", 200)

    # ---- 段を進める ---------------------------------------------------------

    def uid_of(self):
        return "admin"

    def to_check(self, password=TARGET_PW):
        """2段目まで通して、3段目のフォームが持っている値を返す。"""
        out = self.post(step=delwiki.STEP_PASSWORD, name=TARGET, admin_pw=password)
        body = self.body_of(out)
        return out, body, self.hidden_of(body)

    def hidden_of(self, body):
        """画面に埋まっている hidden の値を拾う（次の段へそのまま渡すため）。"""
        import re
        found = {}
        for m in re.finditer(r'<input type="hidden" name="([^"]+)" value="([^"]*)">',
                             body):
            found[m.group(1)] = m.group(2)
        return found

    def archive_of(self, hidden):
        return delwiki.done_path(TARGET, hidden["stamp"])

    def right_answers(self):
        """3段目に書けば通る値（`wikilib.wikimark` が作る）。"""
        target = self.wiki_dirs[TARGET]
        return (wikimark.usage_text(target),
                sorted(wikimark.updated_days(target))[0])


# ---- 消してよい相手か -------------------------------------------------------

class TestTarget(DelwikiBase):

    def test_無いWikiは消せない(self):
        self.assertIn("ありません", delwiki.target_problem("nosuch", self.config))

    def test_既定Wikiは消せない(self):
        # 名前を付けずに開いたときに出るWikiを消すと、入口そのものが無くなる
        problem = delwiki.target_problem(HOME, self.config)
        self.assertIsNotNone(problem)
        self.assertIn("既定", problem)

    def test_ほかのWikiは消せる(self):
        self.assertIsNone(delwiki.target_problem(TARGET, self.config))

    def test_名前の細工は一覧との突き合わせで落ちる(self):
        for name in ("../home", "sandbox/../home", ""):
            self.assertIsNotNone(delwiki.target_problem(name, self.config))


# ---- 合札 -------------------------------------------------------------------

class TestToken(DelwikiBase):

    def test_同じ条件なら同じ札になる(self):
        a = delwiki.token_of(delwiki.PURPOSE_ARCHIVE, TARGET, "260918_120000", "admin")
        b = delwiki.token_of(delwiki.PURPOSE_ARCHIVE, TARGET, "260918_120000", "admin")
        self.assertEqual(a, b)
        self.assertTrue(delwiki.token_ok(delwiki.PURPOSE_ARCHIVE, TARGET,
                                         "260918_120000", "admin", a))

    def test_ひとつでも違えば通らない(self):
        token = delwiki.token_of(delwiki.PURPOSE_ARCHIVE, TARGET, "260918_120000", "admin")
        # 別の人・別の用途・別のWiki・別の日時、どれも通らない
        self.assertFalse(delwiki.token_ok(delwiki.PURPOSE_ARCHIVE, TARGET,
                                          "260918_120000", "hoka", token))
        self.assertFalse(delwiki.token_ok(delwiki.PURPOSE_CHECKED, TARGET,
                                          "260918_120000", "admin", token))
        self.assertFalse(delwiki.token_ok(delwiki.PURPOSE_ARCHIVE, HOME,
                                          "260918_120000", "admin", token))
        self.assertFalse(delwiki.token_ok(delwiki.PURPOSE_ARCHIVE, TARGET,
                                          "260918_120001", "admin", token))

    def test_空の札は通らない(self):
        self.assertFalse(delwiki.token_ok(delwiki.PURPOSE_ARCHIVE, TARGET,
                                          "260918_120000", "admin", ""))


# ---- 手続きの流れ -----------------------------------------------------------

@need7z
class TestFlow(DelwikiBase):
    """**順番どおりにしか通れない。**"""

    def test_名前を入れると管理者のパスワードを訊かれる(self):
        out = self.post(step=delwiki.STEP_NAME, name=TARGET)
        body = self.body_of(out)
        self.assertIn("管理者", body)
        self.assertIn('name="admin_pw"', body)

    def test_既定Wikiの名前では先へ進めない(self):
        body = self.body_of(self.post(step=delwiki.STEP_NAME, name=HOME))
        self.assertIn("既定", body)
        self.assertNotIn('name="admin_pw"', body)

    def test_パスワードが違えば書庫も作らない(self):
        out = self.post(step=delwiki.STEP_PASSWORD, name=TARGET, admin_pw="ちがう")
        self.assertEqual(self.status_of(out), 403)
        self.assertIn('name="admin_pw"', self.body_of(out))
        self.assertEqual([e for e in os.listdir(self.wikidata) if ".7z" in e], [])

    def test_既定Wikiの管理者のパスワードでは通らない(self):
        # **確かめるのは消される側の管理者。** この画面を開ける人＝既定Wikiの
        # 管理者・助手であることは、関門で済んでいる
        out = self.post(step=delwiki.STEP_PASSWORD, name=TARGET, admin_pw=HOME_PW)
        self.assertEqual(self.status_of(out), 403)

    def test_パスワードが通ると書庫づくりが始まる(self):
        out, body, hidden = self.to_check()
        self.assertIn("ディスク使用量", body)
        self.assertEqual(hidden["name"], TARGET)
        self.assertTrue(hidden["stamp"])
        self.assertTrue(hidden["token"])
        state, _ = delwiki.wait_for_archive(TARGET, hidden["stamp"])
        self.assertEqual(state, "done")

    def test_様子が違えば先へ進めない(self):
        _out, _body, hidden = self.to_check()
        out = self.post(step=delwiki.STEP_CHECK, name=TARGET, stamp=hidden["stamp"],
                        token=hidden["token"], usage="999MB/999MB",
                        updated="2000-01-01")
        self.assertEqual(self.status_of(out), 403)
        self.assertIn("ディスク使用量", self.body_of(out))  # 3段目に留まる

    def test_様子が合えば最後の確認へ進む(self):
        _out, _body, hidden = self.to_check()
        usage, day = self.right_answers()
        out = self.post(step=delwiki.STEP_CHECK, name=TARGET, stamp=hidden["stamp"],
                        token=hidden["token"], usage=usage, updated=day)
        body = self.body_of(out)
        self.assertIn("最後の確認", body)
        self.assertIn(self.hidden_of(body)["checked"], body)

    def test_3段目を飛ばした最後のPOSTは通らない(self):
        _out, _body, hidden = self.to_check()
        delwiki.wait_for_archive(TARGET, hidden["stamp"])
        out = self.post(step=delwiki.STEP_FINAL, name=TARGET, stamp=hidden["stamp"],
                        token=hidden["token"], checked="でたらめ")
        self.assertEqual(self.status_of(out), 403)
        self.assertTrue(os.path.isdir(os.path.join(self.wikidata, TARGET)))

    def test_最後まで通すと消える(self):
        hidden = self.walk_to_final()
        out = self.post(step=delwiki.STEP_FINAL, **hidden)
        self.assertEqual(self.status_of(out), 200)
        self.assertIn("消しました", self.body_of(out))
        self.assertFalse(os.path.exists(os.path.join(self.wikidata, TARGET)))
        self.assertTrue(os.path.isfile(self.archive_of(hidden)))

    def walk_to_final(self):
        """4段目のフォームが持っている hidden まで進める。"""
        _out, _body, hidden = self.to_check()
        usage, day = self.right_answers()
        out = self.post(step=delwiki.STEP_CHECK, name=TARGET, stamp=hidden["stamp"],
                        token=hidden["token"], usage=usage, updated=day)
        final = self.hidden_of(self.body_of(out))
        delwiki.wait_for_archive(TARGET, final["stamp"])
        return {k: final[k] for k in ("name", "stamp", "token", "checked")}


# ---- 書庫 -------------------------------------------------------------------

@need7z
class TestArchive(DelwikiBase):

    def test_出来上がるまでは別の名前(self):
        stamp = delwiki.new_stamp()
        ok, _ = delwiki.start_archive(TARGET, stamp)
        self.assertTrue(ok)
        state, _detail = delwiki.wait_for_archive(TARGET, stamp)
        self.assertEqual(state, "done")
        # 作りかけの名前は残らない
        self.assertFalse(os.path.exists(delwiki.part_path(TARGET, stamp)))
        self.assertTrue(os.path.isfile(delwiki.done_path(TARGET, stamp)))

    def test_名前は指定どおり(self):
        stamp = delwiki.new_stamp()
        delwiki.start_archive(TARGET, stamp)
        delwiki.wait_for_archive(TARGET, stamp)
        self.assertIn("{}.{}.7z".format(TARGET, stamp), os.listdir(self.wikidata))

    def test_書庫が無ければ消さない(self):
        # 4段目まで通っていても、書庫が出来ていなければ実体は消えない
        out = self.post(step=delwiki.STEP_FINAL, name=TARGET, stamp="260918_000000",
                        token=delwiki.token_of(delwiki.PURPOSE_ARCHIVE, TARGET,
                                               "260918_000000", "admin"),
                        checked=delwiki.token_of(delwiki.PURPOSE_CHECKED, TARGET,
                                                 "260918_000000", "admin"))
        self.assertEqual(self.status_of(out), 409)
        self.assertTrue(os.path.isdir(os.path.join(self.wikidata, TARGET)))


# ---- やめたとき -------------------------------------------------------------

@need7z
class TestCancel(DelwikiBase):
    """**やめたら書庫も消す**（Wiki設計者の指示、2026-09-18）。"""

    def test_やめると書庫が残らない(self):
        _out, _body, hidden = self.to_check()
        delwiki.wait_for_archive(TARGET, hidden["stamp"])
        self.assertTrue(os.path.isfile(self.archive_of(hidden)))
        out = self.post(cancel="1", name=TARGET, stamp=hidden["stamp"],
                        token=hidden["token"])
        self.assertIn("片づけました", self.body_of(out))
        self.assertFalse(os.path.exists(self.archive_of(hidden)))
        # 実体は無事
        self.assertTrue(os.path.isdir(os.path.join(self.wikidata, TARGET)))

    def test_札が通らないPOSTでは書庫を消さない(self):
        _out, _body, hidden = self.to_check()
        delwiki.wait_for_archive(TARGET, hidden["stamp"])
        self.post(cancel="1", name=TARGET, stamp=hidden["stamp"], token="でたらめ")
        self.assertTrue(os.path.isfile(self.archive_of(hidden)))


# ---- 戻せるか ---------------------------------------------------------------

@need7z
class TestRoundTrip(DelwikiBase):
    """**展開すれば元に戻る。** ここが成り立たないなら「消すだけ」になる。"""

    def test_展開すると中身がそろって戻る(self):
        hidden = TestFlow.walk_to_final(self)
        # **書庫が出来上がったあとで数える。** 手続きの途中で増えるファイル
        # （認証の記録 log/auth.log.db）まで含めて、書庫の中身と突き合わせる
        before = self.snapshot(os.path.join(self.wikidata, TARGET))
        self.post(step=delwiki.STEP_FINAL, **hidden)
        self.assertFalse(os.path.exists(os.path.join(self.wikidata, TARGET)))

        subprocess.run([delwiki.sevenzip_program(), "x", "-y",
                        self.archive_of(hidden)],
                       cwd=self.wikidata, stdout=subprocess.DEVNULL,
                       stderr=subprocess.STDOUT, check=True)
        after = self.snapshot(os.path.join(self.wikidata, TARGET))
        self.assertEqual(before, after)
        # アカウントの記録も添付も戻っている
        self.assertIn("config/users.db", before)
        self.assertIn("attach/index/note.txt", before)

    def snapshot(self, root):
        """そのフォルダ以下の {相対パス: 中身のバイト数}。"""
        found = {}
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                found[rel] = os.path.getsize(full)
        return found


if __name__ == "__main__":
    unittest.main(verbosity=2)
