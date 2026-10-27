#!/usr/bin/env python3
"""公開版からの更新（`wikilib.sysupdate`）と、info の更新の知らせ（`pagenotice.update_notice`）のテスト。

GitHub への問い合わせと、git・uv の実行は差し替える。作業ツリーの確かめ（`checkout_state`）は、
一時的な git の作業ツリーを作って確かめる。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_sysupdate.py     （このファイルだけ）
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

from wikilib import pagenotice, sysupdate  # noqa: E402

CHANGELOG = """# 更新履歴

## 1.2.0（2026-11-01）

- 新しい機能

## 1.1.1（2026-10-06）

- 直したこと

## 1.1（2026-09-30）

- もっと前
"""


class TestVersion(unittest.TestCase):

    def test_wiki_pyから読む(self):
        self.assertEqual(sysupdate.parse_version('X = 1\nVERSION = "1.2.0"\nREVISION = "3"\n'), "1.2.0")
        self.assertIsNone(sysupdate.parse_version("nothing"))

    def test_新しいかどうか(self):
        self.assertTrue(sysupdate.is_newer("1.2", "1.1.1"))
        self.assertTrue(sysupdate.is_newer("1.10", "1.9"))
        self.assertFalse(sysupdate.is_newer("1.1.1", "1.1.1"))
        self.assertFalse(sysupdate.is_newer("1.1.0", "1.1"))
        self.assertFalse(sysupdate.is_newer("1.1", "1.1.1"))
        self.assertFalse(sysupdate.is_newer(None, "1.1"))

    def test_今より新しい節だけ(self):
        sections = sysupdate.changelog_sections(CHANGELOG, "1.1")
        self.assertEqual([s["version"] for s in sections], ["1.2.0", "1.1.1"])
        self.assertTrue(sections[0]["text"].startswith("## 1.2.0"))
        self.assertIn("新しい機能", sections[0]["text"])
        self.assertNotIn("直したこと", sections[0]["text"])

    def test_最新なら節は無い(self):
        self.assertEqual(sysupdate.changelog_sections(CHANGELOG, "1.2.0"), [])


SHA = "0123456789abcdef0123456789abcdef01234567"


def fake_opener(files, sha=SHA, seen=None):
    """GitHub の代わり。API にはコミット `sha` を返し、raw はそのコミットを指したときだけ `files` を返す。"""
    def opener(req, timeout=None):
        url = getattr(req, "full_url", req)
        if seen is not None:
            seen.append(url)
        if url.startswith(sysupdate.COMMIT_API):
            return io.BytesIO(sha.encode("ascii"))
        name = url[len(sysupdate.raw_base(sha)):]
        if not url.startswith(sysupdate.raw_base(sha)) or name not in files:
            raise OSError("404 " + url)
        return io.BytesIO(files[name].encode("utf-8"))
    return opener


class TestBranch(unittest.TestCase):
    """見に行くブランチ（server.yaml の update.branch）。"""

    def test_既定はmain(self):
        self.assertEqual(sysupdate.source_branch({}), "main")

    def test_試験ブランチを見られる(self):
        self.assertEqual(sysupdate.source_branch({"update": {"branch": "update-test"}}), "update-test")
        self.assertTrue(sysupdate.raw_base("update-test").endswith("/yanowiki/update-test/"))

    def test_ブランチ名に使えない値は既定に戻す(self):
        for bad in ("-x", "a b", "../x", "a;rm", ""):
            self.assertEqual(sysupdate.source_branch({"update": {"branch": bad}}), "main", bad)


class TestCheck(unittest.TestCase):

    def setUp(self):
        self.saved = dict(sysupdate._latest)

    def tearDown(self):
        sysupdate._latest.clear()
        sysupdate._latest.update(self.saved)

    def test_最新版と更新履歴を覚える(self):
        info = sysupdate.check_now(fake_opener({
            "wiki.py": 'VERSION = "1.2.0"\n', sysupdate.CHANGELOG_PATH: CHANGELOG}), branch="main")
        self.assertEqual(info["version"], "1.2.0")
        self.assertIn("## 1.2.0", info["changelog"])
        self.assertIsNone(info["error"])
        self.assertEqual(info["commit"], SHA)
        self.assertEqual(sysupdate.available("1.1.1"), "1.2.0")
        self.assertIsNone(sysupdate.available("1.2.0"))

    def test_更新履歴が無くてもバージョンは知らせる(self):
        info = sysupdate.check_now(fake_opener({"wiki.py": 'VERSION = "1.2.0"\n'}), branch="main")
        self.assertEqual(info["version"], "1.2.0")
        self.assertEqual(info["changelog"], "")
        self.assertIsNone(info["error"])

    def test_コミットを指して読む(self):
        seen = []
        sysupdate.check_now(fake_opener({"wiki.py": 'VERSION = "1.2.0"\n'}, seen=seen), branch="update-test")
        self.assertEqual(seen[0], sysupdate.COMMIT_API + "update-test")
        self.assertTrue(all(u.startswith(sysupdate.raw_base(SHA)) for u in seen[1:]), seen)

    def test_コミットを読めなければ知らせない(self):
        info = sysupdate.check_now(fake_opener({"wiki.py": 'VERSION = "1.2.0"\n'}, sha="<html>"), branch="main")
        self.assertIsNone(info["version"])
        self.assertTrue(info["error"])

    def test_つながらなければ知らせない(self):
        info = sysupdate.check_now(fake_opener({}), branch="main")
        self.assertIsNone(info["version"])
        self.assertTrue(info["error"])
        self.assertIsNone(sysupdate.available("1.1"))

    def test_調べ直すのは間をおいてから(self):
        with mock.patch.object(sysupdate.threading, "Thread") as thread:
            sysupdate._latest.update(checked_at=time.time(), checking=False)
            sysupdate.check_in_background()
            thread.assert_not_called()
            sysupdate._latest.update(checked_at=time.time() - sysupdate.CHECK_INTERVAL - 1)
            sysupdate.check_in_background()
            thread.assert_called_once()
            sysupdate.check_in_background()   # 調べている途中なら重ねない
            thread.assert_called_once()


@unittest.skipUnless(shutil.which("git"), "git が無い")
class TestCheckoutState(unittest.TestCase):
    """更新できる作業ツリーか（公開版のまま・main・_system の外に手元の変更が無い）。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sysupdate-")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("remote", "add", "origin", "https://github.com/yoshiyano/yanowiki.git")
        self.write("wiki.py", 'VERSION = "1.1.1"\n')
        self.write("wikidata/_system/wiki/index.md", "# top\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        uv = mock.patch.object(sysupdate, "find_uv", return_value="/usr/bin/uv")
        uv.start()
        self.addCleanup(uv.stop)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write(self, path, text):
        full = os.path.join(self.root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)

    def test_公開版のままなら更新できる(self):
        state = sysupdate.checkout_state(self.root)
        self.assertEqual(state, {"problems": [], "system_changes": []})
        self.assertEqual(sysupdate.current_version(self.root), "1.1.1")

    def test_systemのWikiの手直しは知らせるだけ(self):
        self.write("wikidata/_system/wiki/index.md", "# 直した\n")
        state = sysupdate.checkout_state(self.root)
        self.assertEqual(state["problems"], [])
        self.assertEqual(state["system_changes"], ["wikidata/_system/wiki/index.md"])

    def test_ほかの手元の変更があれば更新できない(self):
        self.write("wiki.py", 'VERSION = "9"\n')
        self.assertTrue(any("wiki.py" in p for p in sysupdate.checkout_state(self.root)["problems"]))

    def test_mainでなければ更新できない(self):
        self.git("checkout", "-q", "-b", "dev")
        self.assertTrue(any("main" in p for p in sysupdate.checkout_state(self.root)["problems"]))

    def test_公開版から取ってきたものでなければ更新できない(self):
        self.git("remote", "set-url", "origin", "git@github.com:yoshiyano/wikiSystem.git")
        self.assertTrue(any("origin" in p for p in sysupdate.checkout_state(self.root)["problems"]))

    def test_gitの作業ツリーでなければ更新できない(self):
        plain = tempfile.mkdtemp(prefix="sysupdate-plain-")
        self.addCleanup(shutil.rmtree, plain, True)
        self.assertTrue(sysupdate.checkout_state(plain)["problems"])


class FakeRun:
    """subprocess.run の代わり。呼ばれた順に記録し、`fail` に含む最初の語で失敗させる。"""

    def __init__(self, fail=()):
        self.calls = []
        self.fail = fail

    def __call__(self, args, **kw):
        self.calls.append(list(args))
        key = " ".join(args[1:3])
        code = 1 if key in self.fail and not self.failed_once(key) else 0
        out = "abc123\n" if args[1:3] == ["rev-parse", "HEAD"] else ""
        return subprocess.CompletedProcess(args, code, stdout=out, stderr="失敗の理由" if code else "")

    def failed_once(self, key):
        # 戻すときの同じ操作は通す（失敗させるのは最初の1回だけ）
        hits = [c for c in self.calls if " ".join(c[1:3]) == key]
        return len(hits) > 1


class TestRunUpdate(unittest.TestCase):

    def setUp(self):
        uv = mock.patch.object(sysupdate, "find_uv", return_value="uv")
        uv.start()
        self.addCleanup(uv.stop)

    def test_取ってきて合わせて部品を入れ直す(self):
        run = FakeRun()
        result = sysupdate.run_update(SHA, "/x", run=run)
        self.assertTrue(result["ok"])
        self.assertEqual([c[:3] for c in run.calls], [
            ["git", "rev-parse", "HEAD"], ["git", "fetch", "--depth"],
            ["git", "reset", "--hard"], ["uv", "sync", "--inexact"], ["git", "rev-parse", "HEAD"]])
        self.assertEqual(run.calls[1][-2:], ["origin", SHA])
        self.assertEqual(run.calls[2][-1], "FETCH_HEAD")

    def test_コミットが分からなければ何もしない(self):
        run = FakeRun()
        self.assertFalse(sysupdate.run_update("main", "/x", run=run)["ok"])
        self.assertEqual(run.calls, [])

    def test_取ってこられなければ何も変えない(self):
        run = FakeRun(fail=("fetch --depth",))
        result = sysupdate.run_update(SHA, "/x", run=run)
        self.assertFalse(result["ok"])
        self.assertFalse(any(c[1] == "reset" for c in run.calls))

    def test_部品を入れ直せなければ前へ戻す(self):
        run = FakeRun(fail=("sync --inexact",))
        result = sysupdate.run_update(SHA, "/x", run=run)
        self.assertFalse(result["ok"])
        self.assertIn(["git", "reset", "--hard", "abc123"], run.calls)
        self.assertIn("戻しました", result["message"])


class TestUpdateNotice(unittest.TestCase):
    """info の更新の知らせ。Wiki名を含まないURLの既定のWikiで、再起動を許された人にだけ出す。"""

    def notice(self, farm="main", explicit=False, can=True, newer="1.2.0"):
        config = {}
        with mock.patch("wikilib.wikiconfig.load_default_farm", return_value="main"), \
                mock.patch("wikilib.auth.can", return_value=can), \
                mock.patch.object(sysupdate, "check_in_background"), \
                mock.patch.object(sysupdate, "available", return_value=newer), \
                mock.patch.object(sysupdate, "current_version", return_value="1.1.1"):
            return pagenotice.update_notice(config, farm, "", "/wiki", explicit)

    def test_新しい版があれば更新の画面へつなぐ(self):
        html = str(self.notice())
        self.assertIn('href="/.admin/update"', html)
        self.assertIn("1.2.0", html)
        self.assertIn("1.1.1", html)

    def test_新しい版が無ければ出さない(self):
        self.assertIsNone(self.notice(newer=None))

    def test_権限が無ければ出さない(self):
        self.assertIsNone(self.notice(can=False))

    def test_既定でないWikiには出さない(self):
        self.assertIsNone(self.notice(farm="other"))

    def test_Wiki名を含むURLには出さない(self):
        self.assertIsNone(self.notice(explicit=True))


if __name__ == "__main__":
    unittest.main()
