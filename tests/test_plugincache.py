#!/usr/bin/env python3
"""プラグインの読み込みを1回の要求の中で使い回す（plugins.load_plugins、2026-09-27）。

差し込むページを描くたびに全プラグインを読み直していたのを、要求の environ に置いて
使い回すようにした。要求ごとに読み直す決まり（プラグインを直せば次の要求から効く）は
変えていないことも見る。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_plugincache.py     （このファイルだけ）
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
        self.write_plugin('VALUE = 1\n')
        bottle.request.bind({})
        first = load_plugins(self.plugin_dir)
        self.assertEqual(first["zzcache"]["module"].VALUE, 1)
        # 大きさを変える（同じ秒・同じ大きさだと、Python のコンパイル済みキャッシュが
        # 書き換えに気づかない。この仕組みとは関係の無い、Python の読み込みの性質）
        self.write_plugin('VALUE = 200\n')
        self.assertEqual(load_plugins(self.plugin_dir)["zzcache"]["module"].VALUE, 1)  # 同じ要求
        bottle.request.bind({})   # 次の要求
        self.assertEqual(load_plugins(self.plugin_dir)["zzcache"]["module"].VALUE, 200)

    def test_置き場所ごとに分ける(self):
        other = os.path.join(self.work, "other", "plugin")
        os.makedirs(other)
        bottle.request.bind({})
        self.assertIsNot(load_plugins(self.plugin_dir), load_plugins(other))


if __name__ == "__main__":
    unittest.main()
