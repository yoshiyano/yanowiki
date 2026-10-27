#!/usr/bin/env python3
"""エディタ連動の編集で配るもの（_system Wiki の添付）の試験。

配る zip・.vsix は、元のファイルから build_zip.py・build_vsix.py で組み立てたもの。元の
ファイルを直して作り直し忘れると、ダウンロードした人には古いものが届く。添付の zip・.vsix が、
いまの元のファイルから組み立てた結果と同じかを確かめる。

実行:
    _venv/bin/python3 -m unittest tests.test_editorsync_dist
"""
import importlib.util
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_DIR = os.path.join(ROOT, "wikidata", "_system", "attach", "PageEdit", "EditorSyncGuide")
EXT_DIR = os.path.join(GUIDE_DIR, "BrowserExt")
VSCODE_DIR = os.path.join(GUIDE_DIR, "VSCode")
# 配るファイル（冒頭に「更新: 日時」を書く。設計者の指示、2026-10-07）
STAMPED = ("BrowserExt/background.js", "BrowserExt/relay.js", "BrowserExt/build_zip.py", "Emacs/wikiedit.el",
           "VSCode/extension.js", "VSCode/build_vsix.py", "Neovim/wikiedit.lua")
STAMP_RE = re.compile(r"更新: (\d{4}-\d{2}-\d{2} \d{2}:\d{2} [+-]\d{2}:\d{2})")


def load_builder(path=os.path.join(EXT_DIR, "build_zip.py")):
    # 添付の置き場所に __pycache__ を作らない（Wiki 上では子ページの添付のように見えるため）
    sys.dont_write_bytecode = True
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBrowserExtZip(unittest.TestCase):

    def test_添付の_zip_は元のファイルから作った結果と同じ(self):
        builder = load_builder()
        for zip_name, manifest_name in builder.SETS.items():
            with open(os.path.join(EXT_DIR, zip_name), "rb") as f:
                self.assertEqual(f.read(), builder.build(manifest_name),
                                 zip_name + " が古い。build_zip.py を実行して作り直す")

    def test_設定の裏方の書きかたがブラウザに合っている(self):
        # Chrome は MV3 で background.scripts をエラーにし、Firefox は service_worker で動かない
        with open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8") as f:
            chrome = json.load(f)
        with open(os.path.join(EXT_DIR, "manifest.firefox.json"), encoding="utf-8") as f:
            firefox = json.load(f)
        self.assertEqual(chrome["background"], {"service_worker": "background.js"})
        self.assertEqual(firefox["background"], {"scripts": ["background.js"]})
        self.assertNotIn("browser_specific_settings", chrome)

    def test_二つの設定は裏方とFirefoxの項目のほかは同じ(self):
        with open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8") as f:
            chrome = json.load(f)
        with open(os.path.join(EXT_DIR, "manifest.firefox.json"), encoding="utf-8") as f:
            firefox = json.load(f)
        for m in (chrome, firefox):
            m.pop("background")
            m.pop("browser_specific_settings", None)
        self.assertEqual(chrome, firefox)


class TestVSCodeVsix(unittest.TestCase):

    def test_添付の_vsix_は元のファイルから作った結果と同じ(self):
        builder = load_builder(os.path.join(VSCODE_DIR, "build_vsix.py"))
        with open(os.path.join(VSCODE_DIR, builder.VSIX), "rb") as f:
            self.assertEqual(f.read(), builder.build(),
                             builder.VSIX + " が古い。build_vsix.py を実行して作り直す")

    def test_目録は_package_json_の名前と版を使う(self):
        builder = load_builder(os.path.join(VSCODE_DIR, "build_vsix.py"))
        with open(os.path.join(VSCODE_DIR, "package.json"), encoding="utf-8") as f:
            pkg = json.load(f)
        manifest = builder.manifest(pkg)
        self.assertIn('Id="%s" Version="%s" Publisher="%s"' % (pkg["name"], pkg["version"], pkg["publisher"]), manifest)
        self.assertEqual(pkg["main"], "./extension.js")


class TestUpdatedStamp(unittest.TestCase):
    """配るファイルには、冒頭に更新した日時を書く。ダウンロードした人が、手元のものが
    どの時点のものかを分かるようにするため（設計者の指示、2026-10-07）。日時が新しいかまでは
    確かめられないので、書く形だけを見る。"""

    def test_冒頭に更新の日時がある(self):
        for name in STAMPED:
            with open(os.path.join(GUIDE_DIR, name), encoding="utf-8") as f:
                head = "".join(f.readline() for _ in range(12))
            self.assertRegex(head, STAMP_RE, name + " の冒頭に「更新: YYYY-MM-DD HH:MM +09:00」が無い")

    def test_Emacs_のプラグインは名乗る日時とコメントがそろっている(self):
        with open(os.path.join(GUIDE_DIR, "Emacs/wikiedit.el"), encoding="utf-8") as f:
            text = f.read()
        comment = STAMP_RE.search(text).group(1)
        self.assertIn('(defconst wikiedit-updated "%s"' % comment, text)

    def test_VS_Code_の拡張機能は名乗る日時とコメントがそろっている(self):
        with open(os.path.join(GUIDE_DIR, "VSCode/extension.js"), encoding="utf-8") as f:
            text = f.read()
        comment = STAMP_RE.search(text).group(1)
        self.assertIn('const UPDATED = "%s";' % comment, text)

    def test_Neovim_のプラグインは名乗る日時とコメントがそろっている(self):
        with open(os.path.join(GUIDE_DIR, "Neovim/wikiedit.lua"), encoding="utf-8") as f:
            text = f.read()
        comment = STAMP_RE.search(text).group(1)
        self.assertIn('M.updated = "%s"' % comment, text)


if __name__ == "__main__":
    unittest.main()
