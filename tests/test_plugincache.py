#!/usr/bin/env python3
"""プラグインの読み込みを1回の要求の中で使い回す（plugins.load_plugins、2026-09-27）。

差し込むページを描くたびに全プラグインを読み直していたのを、要求の environ に置いて
使い回すようにした。要求ごとに読み直す決まり（プラグインを直せば次の要求から効く）は
変えていないことも見る。

実行:
    _venv/bin/python3 -m unittest discover -s tests
    _venv/bin/python3 tests/test_plugincache.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib.plugins import load_plugins  # noqa: E402


class TestPluginCache(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="plugincache-")
        self.plugin_dir = os.path.join(self.work, "plugin")
        os.makedirs(self.plugin_dir)

    def tearDown(self):
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def write_plugin(self, text):
        with open(os.path.join(self.plugin_dir, "zzcache.py"), "w", encoding="utf-8") as f:
            f.write(text)

    def test_同じ要求の中では使い回す(self):
        bottle.request.bind({})
        self.assertIs(load_plugins(self.plugin_dir), load_plugins(self.plugin_dir))

    def test_要求が変われば読み直す(self):
        self.write_plugin('PLUGIN_INFO = {}\nVALUE = 1\n')
        bottle.request.bind({})
        first = load_plugins(self.plugin_dir)
        self.assertEqual(first["zzcache"]["module"].VALUE, 1)
        # 大きさを変える（同じ秒・同じ大きさだと、Python のコンパイル済みキャッシュが
        # 書き換えに気づかない。この仕組みとは関係の無い、Python の読み込みの性質）
        self.write_plugin('PLUGIN_INFO = {}\nVALUE = 200\n')
        self.assertEqual(load_plugins(self.plugin_dir)["zzcache"]["module"].VALUE, 1)  # 同じ要求
        bottle.request.bind({})   # 次の要求
        self.assertEqual(load_plugins(self.plugin_dir)["zzcache"]["module"].VALUE, 200)

    def test_置き場所ごとに分ける(self):
        other = os.path.join(self.work, "other", "plugin")
        os.makedirs(other)
        bottle.request.bind({})
        self.assertIsNot(load_plugins(self.plugin_dir), load_plugins(other))


class TestPluginInfoRequired(unittest.TestCase):
    """`PLUGIN_INFO` を宣言していないモジュールは、プラグインとして登録しない
    （Wiki設計者の指示、2026-10-02。A案、2026-10-19）。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="plugininfo-")
        self.plugin_dir = os.path.join(self.work, "plugin")
        os.makedirs(self.plugin_dir)
        bottle.request.bind({})

    def tearDown(self):
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, name, text):
        with open(os.path.join(self.plugin_dir, name + ".py"), "w", encoding="utf-8") as f:
            f.write(text)

    def test_宣言の無いものは登録しない(self):
        self.put("zznoinfo", "def helper():\n    return 1\n")
        self.put("zznotdict", "PLUGIN_INFO = None\n")
        registry = load_plugins(self.plugin_dir)
        self.assertNotIn("zznoinfo", registry)
        self.assertNotIn("zznotdict", registry)

    def test_宣言があれば登録する(self):
        self.put("zzinfo", "PLUGIN_INFO = {}\n")
        entry = load_plugins(self.plugin_dir)["zzinfo"]
        self.assertIsNone(entry["error"])

    def test_読み込みで例外が出たものはエラー付きで登録する(self):
        self.put("zzbroken", "raise RuntimeError('boom')\n")
        entry = load_plugins(self.plugin_dir)["zzbroken"]
        self.assertIn("boom", entry["error"])


if __name__ == "__main__":
    unittest.main()
