"""updateDB プラグイン: force=1 の制限（ログイン必須・15分に1回・1日20回、管理者と助手は制限なし）。"""
import datetime
import importlib.util
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "_sys"))


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "test_updatedb_plugin", os.path.join(ROOT, "plugin", "updateDB.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Context:
    wiki_dir = "/nonexistent/wiki"
    farm = "w"


class TestForceLimit(unittest.TestCase):

    def setUp(self):
        self.plugin = load_plugin()
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin.FORCE_LOG = os.path.join(self.tmp.name, "force.json")
        # 日付の境目に当たらないよう、今日の昼を起点にする
        self.noon = datetime.datetime.now().replace(
            hour=12, minute=0, second=0, microsecond=0).timestamp()

    def tearDown(self):
        self.tmp.cleanup()

    def count(self, key, now):
        return self.plugin._count_force(key, now)

    def test_15分たたないと断る(self):
        self.assertIsNone(self.count("w\tu", self.noon))
        refused = self.count("w\tu", self.noon + 14 * 60)
        self.assertEqual(refused.status_code, 429)
        self.assertIsNone(self.count("w\tu", self.noon + 15 * 60))

    def test_1日20回まで(self):
        for i in range(20):
            self.assertIsNone(self.count("w\tu", self.noon - 11 * 3600 + i * 15 * 60))
        refused = self.count("w\tu", self.noon + 11 * 3600)
        self.assertEqual(refused.status_code, 429)
        self.assertIn("20回", refused.body)

    def test_日付が変われば数え直す(self):
        for i in range(20):
            self.count("w\tu", self.noon - 11 * 3600 + i * 15 * 60)
        self.assertIsNone(self.count("w\tu", self.noon + 24 * 3600))

    def test_人ごとに数える(self):
        self.assertIsNone(self.count("w\ta", self.noon))
        self.assertIsNone(self.count("w\tb", self.noon))
        self.assertIsNone(self.count("x\ta", self.noon))

    def test_ログインしていなければ使えない(self):
        self.plugin.current_user = lambda wiki_dir, farm: None
        self.assertEqual(self.plugin._check_force(Context()).status_code, 403)

    def test_管理者と助手は制限なし(self):
        self.plugin.current_user = lambda wiki_dir, farm: {"uid": "admin", "uidnum": 1}
        self.plugin.is_staff = lambda wiki_dir, user: True
        for _ in range(30):
            self.assertIsNone(self.plugin._check_force(Context()))
        self.assertFalse(os.path.exists(self.plugin.FORCE_LOG))

    def test_ほかのログインユーザーは数えられる(self):
        self.plugin.current_user = lambda wiki_dir, farm: {"uid": "u", "uidnum": 5}
        self.plugin.is_staff = lambda wiki_dir, user: False
        self.assertIsNone(self.plugin._check_force(Context()))
        self.assertEqual(self.plugin._check_force(Context()).status_code, 429)


if __name__ == "__main__":
    unittest.main()
