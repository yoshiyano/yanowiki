#!/home/yoshi/ClaudeWS/wikiSystem/_venv/bin/python
"""`plugin/popular.py` のテスト（除外の指定 exclude・消えたページ）。

`#recent` と同じ書きかたで、除いてから上位を切る。消えたページは並べない。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_popular.py     （このファイルだけ）
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import accesslog, auth, paths, userdb  # noqa: E402
from wikilib.pagesync import sync_wiki  # noqa: E402
from wikilib.paths import farm_plugin_dir  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import parse_source  # noqa: E402

FARM = "other"


class TestPopularExclude(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="popular-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(os.path.join(self.wiki_dir, "Tech", "ChangeLog"))
        userdb.create_db(self.wiki_dir, "adminpw")
        self.kept = (paths.WIKIDATA_DIR, auth.SECRET_PATH)
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        for name in ("Top", "Open", "Tech/ChangeLog/2026-09-29"):
            with open(os.path.join(self.wiki_dir, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(f"{name}の本文\n")
        sync_wiki(self.wiki_dir, {})
        bottle.request.bind({})
        # 更新履歴がいちばん多く、次が Open
        for page, times in (("Tech/ChangeLog/2026-09-29", 3), ("Open", 2), ("Top", 1)):
            for n in range(times):
                accesslog.record_access(self.wiki_dir, f"/={FARM}/{page}", f"10.0.0.{n}", "test")

    def tearDown(self):
        paths.WIKIDATA_DIR, auth.SECRET_PATH = self.kept
        shutil.rmtree(self.work, ignore_errors=True)

    def render(self, text):
        context = PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page="Top",
                                base_url=f"/={FARM}", ext=".txt")
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        env = {"wiki": context}
        return md.renderer.render(parse_source(md, text, ".txt", env), md.options, env)

    def test_除かなければ更新履歴も並ぶ(self):
        html = self.render("#popular(10d,10)")
        self.assertIn("Tech/ChangeLog/2026-09-29", html)

    def test_除いたページは並ばず上位も詰まる(self):
        html = self.render("#popular(10d,1,Tech/ChangeLog)")
        self.assertNotIn("ChangeLog", html)
        self.assertIn(">Open<", html)   # 除いてから切るので、1位は Open になる

    def test_名前付きでも書ける(self):
        html = self.render("#popular(day=10, num=10, exclude=Tech/ChangeLog;Top)")
        self.assertNotIn("ChangeLog", html)
        self.assertNotIn(">Top<", html)
        self.assertIn(">Open<", html)

    def test_消えたページは並べない(self):
        # アクセスの記録は残るが、ページは消えた（DBに無い）
        from wikilib.pagesave import remove_page
        os.remove(os.path.join(self.wiki_dir, "Tech", "ChangeLog", "2026-09-29.txt"))
        remove_page(self.wiki_dir, "Tech/ChangeLog/2026-09-29")
        html = self.render("#popular(10d,1)")
        self.assertNotIn("ChangeLog", html)
        self.assertIn(">Open<", html)   # 消えたぶん順位が詰まる

    def test_空の区切りは知らせる(self):
        # 書き間違いは黙って読み飛ばさず、プラグインのエラーとして出す（詳しい文言は
        # デバッグの設定のときだけ出る）
        html = self.render("#popular(10d,10,Tech/ChangeLog;)")
        self.assertIn("plugin-error", html)


if __name__ == "__main__":
    unittest.main()
