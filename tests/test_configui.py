#!/usr/bin/env python3
"""Wikiの設定を画面から書き換えるところ（/.admin/configwiki）のテスト。

見ているのは、**書き換えで何を失い、何を残すか**である。

  目印        1行目のハッシュ。**このシステムが書いたままか**を見分ける
  控え        人が直したものだけ、default.yaml.YYMMDD_HHMMSS に残す（10世代）
  知らない項目 画面に無い設定も**消さない**
  印の無い項目 書かない（共通の設定がそのまま効く）

2026-09-18に**保存ボタンが無くなり**、直した項目1つだけをその場で送る形に
なった（Wiki設計者の指示）。受け取り口は `configui.apply_change` と、その
窓口 `render_configwiki_api` である。

コメントが消えることはWiki設計者の了承ずみ（2026-09-06）。消えて困るものは
控えに残る、という組み合わせで成り立っている。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_configui.py     （このファイルだけ）
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_sys"))

import bottle  # noqa: E402

from wikilib import auth, configui, userdb, wikiconfig  # noqa: E402
from wikilib.paths import (  # noqa: E402
    LOGIN_AUTH_COOKIE, LOGIN_COOKIE, wiki_cookie_name,
)


class ConfigTestBase(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="configui-")
        self.wiki_dir = os.path.join(self.work, "wikidata", "testwiki", "wiki")
        os.makedirs(self.wiki_dir)
        self.path = wikiconfig.farm_config_path(self.wiki_dir)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, text):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()


class TestMarker(ConfigTestBase):
    """1行目の目印（Wiki設計者の指示、2026-09-06）。"""

    def test_書き出したものは目印と合う(self):
        self.put(wikiconfig.dump_config({"edit": {"title_length": 30}}))
        self.assertTrue(wikiconfig.written_by_system(self.path))

    def test_1文字でも直せば合わなくなる(self):
        self.put(wikiconfig.dump_config({"edit": {"title_length": 30}}))
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("# あとから足したコメント\n")
        self.assertFalse(wikiconfig.written_by_system(self.path))

    def test_目印が無ければ人の手のものとして扱う(self):
        self.put("edit:\n  title_length: 30\n")
        self.assertFalse(wikiconfig.written_by_system(self.path))

    def test_目印だけ写しても中身が違えば合わない(self):
        # 別の内容の目印を貼っただけ、では通らない
        other = wikiconfig.dump_config({"edit": {"title_length": 99}})
        head = other.split("\n")[0]
        self.put(head + "\nedit:\n  title_length: 30\n")
        self.assertFalse(wikiconfig.written_by_system(self.path))

    def test_書き出しにコメントは入らない(self):
        # 目印の1行だけが「#」で始まる（Wiki設計者の指示）
        text = wikiconfig.dump_config({"edit": {"title_length": 30},
                                       "theme": {"site_title": "すなば"}})
        starts = [line for line in text.splitlines() if line.startswith("#")]
        self.assertEqual(len(starts), 1)
        self.assertIn("すなば", text)      # 日本語をエスケープしない


class TestBackup(ConfigTestBase):
    """控え（Wiki設計者の指示、2026-09-06）。**人が直したものだけ、10世代まで。**"""

    def test_人が直したものは控える(self):
        self.put("edit:\n  title_length: 30\n")
        self.assertTrue(wikiconfig.needs_backup(self.path))

    def test_システムが書いたままなら控えない(self):
        # 控えても同じ内容が並ぶだけで、失うものが無い
        self.put(wikiconfig.dump_config({"edit": {"title_length": 30}}))
        self.assertFalse(wikiconfig.needs_backup(self.path))

    def test_まだ無いファイルは控えない(self):
        self.assertFalse(wikiconfig.needs_backup(self.path))

    def test_名前は日時(self):
        self.put("edit: {}\n")
        saved = wikiconfig.backup_config(self.path, 1757000000)
        self.assertRegex(os.path.basename(saved), r"^default\.yaml\.\d{6}_\d{6}$")

    def test_中身がそのまま残る(self):
        self.put("# 手で書いたコメント\nedit:\n  title_length: 30\n")
        saved = wikiconfig.backup_config(self.path)
        with open(saved, encoding="utf-8") as f:
            self.assertIn("手で書いたコメント", f.read())

    def test_10世代まで(self):
        import time

        self.put("edit: {}\n")
        for i in range(14):
            wikiconfig.backup_config(self.path, 1757000000 + i * 60)
        found = wikiconfig.config_backups(self.path)
        self.assertEqual(len(found), wikiconfig.CONFIG_BACKUP_KEEP)
        # 残るのは**新しいほう**（名前が時刻そのものなので、名前の逆順）
        newest = time.strftime("%y%m%d_%H%M%S",
                               time.localtime(1757000000 + 13 * 60))
        self.assertTrue(found[0].endswith(newest), found[0])

    def test_控えの一覧は新しい順(self):
        self.put("edit: {}\n")
        for i in range(3):
            wikiconfig.backup_config(self.path, 1757000000 + i * 60)
        found = [os.path.basename(p) for p in wikiconfig.config_backups(self.path)]
        self.assertEqual(found, sorted(found, reverse=True))

    def test_設定ファイル自身は一覧に入らない(self):
        self.put("edit: {}\n")
        wikiconfig.backup_config(self.path)
        self.assertNotIn(self.path, wikiconfig.config_backups(self.path))


class TestSave(ConfigTestBase):
    """保存そのもの。"""

    def test_保存すると読み直せる(self):
        ok, _saved, _message = wikiconfig.save_farm_config(
            self.wiki_dir, {"edit": {"title_length": 30}})
        self.assertTrue(ok)
        self.assertEqual(wikiconfig.read_yaml(self.path)["edit"]["title_length"], 30)

    def test_保存したものは目印と合う(self):
        wikiconfig.save_farm_config(self.wiki_dir, {"edit": {"title_length": 30}})
        self.assertTrue(wikiconfig.written_by_system(self.path))

    def test_人が直したものは控えてから書く(self):
        self.put("# 手で書いたコメント\nedit:\n  title_length: 24\n")
        ok, saved, message = wikiconfig.save_farm_config(
            self.wiki_dir, {"edit": {"title_length": 30}})
        self.assertTrue(ok)
        self.assertIsNotNone(saved)
        self.assertIn("控えました", message)

    def test_2度目は控えない(self):
        wikiconfig.save_farm_config(self.wiki_dir, {"edit": {"title_length": 30}})
        _ok, saved, _message = wikiconfig.save_farm_config(
            self.wiki_dir, {"edit": {"title_length": 28}})
        self.assertIsNone(saved)

    def test_書きかけを残さない(self):
        wikiconfig.save_farm_config(self.wiki_dir, {"edit": {"title_length": 30}})
        self.assertFalse(os.path.exists(self.path + ".tmp"))


class TestValues(unittest.TestCase):
    """入力欄の値と、設定の値の行き来。"""

    def field(self, kind, **extra):
        got = {"path": "x.y", "label": "ためし", "type": kind, "help": ""}
        got.update(extra)
        return got

    def test_真偽(self):
        self.assertEqual(configui._from_text(self.field("bool"), "true"), (True, ""))
        self.assertEqual(configui._from_text(self.field("bool"), "false"), (False, ""))
        self.assertEqual(configui._to_text(self.field("bool"), True), "true")

    def test_生HTMLは3択(self):
        # true/false は真偽値、all だけ文字列という混ざりかた
        get = self.field("html")
        self.assertEqual(configui._from_text(get, "all"), ("all", ""))
        self.assertEqual(configui._from_text(get, "true"), (True, ""))
        self.assertEqual(configui._from_text(get, "false"), (False, ""))
        self.assertEqual(configui._to_text(get, "all"), "all")
        self.assertEqual(configui._to_text(get, True), "true")

    def test_数(self):
        self.assertEqual(configui._from_text(self.field("int"), "24"), (24, ""))
        value, problem = configui._from_text(self.field("int"), "あ")
        self.assertIsNone(value)
        self.assertIn("数を入れてください", problem)

    def test_並び(self):
        value, _problem = configui._from_text(
            self.field("lines"), "#111111\n\n  #222222  \n")
        self.assertEqual(value, ["#111111", "#222222"])
        self.assertEqual(configui._to_text(self.field("lines"), ["a", "b"]), "a\nb")

    def test_知らない選択肢は弾く(self):
        get = self.field("choice", choices=[("a", "A"), ("b", "B")])
        value, problem = configui._from_text(get, "c")
        self.assertIsNone(value)
        self.assertIn("知らない値", problem)

    def test_項目の出し入れ(self):
        data = {}
        configui._put(data, "a.b.c", 1)
        self.assertEqual(data, {"a": {"b": {"c": 1}}})
        self.assertEqual(configui._walk(data, "a.b.c"), (True, 1))
        self.assertEqual(configui._walk(data, "a.b.z"), (False, None))
        configui._drop(data, "a.b.c")
        # 空になった入れ物も片付ける（空の a: {} を書き残さない）
        self.assertEqual(data, {})


class TestApplyChange(ConfigTestBase):
    """直した項目1つの受け取り。**印の付いた項目だけ書き、知らない項目は残す。**"""

    def test_印を付けた項目を書く(self):
        ok, _message, text = configui.apply_change(
            self.wiki_dir, "edit.title_length", True, "30")
        self.assertTrue(ok)
        self.assertEqual(text, "30")
        self.assertEqual(wikiconfig.read_yaml(self.path), {"edit": {"title_length": 30}})

    def test_印を外すと消えて共通の値が返る(self):
        configui.apply_change(self.wiki_dir, "edit.title_length", True, "30")
        ok, _message, text = configui.apply_change(
            self.wiki_dir, "edit.title_length", False, "30")
        self.assertTrue(ok)
        self.assertEqual(wikiconfig.read_yaml(self.path), {})
        # 入力欄に戻すのは「いま効いている値」＝共通の設定
        common = wikiconfig.load_config()["edit"]["title_length"]
        self.assertEqual(text, str(common))

    def test_他の項目には触らない(self):
        # まとめて送らないので、直していない項目は書かれも消えもしない
        configui.apply_change(self.wiki_dir, "edit.title_length", True, "30")
        configui.apply_change(self.wiki_dir, "theme.site_title", True, "すなば")
        got = wikiconfig.read_yaml(self.path)
        self.assertEqual(got, {"edit": {"title_length": 30},
                               "theme": {"site_title": "すなば"}})

    def test_知らない項目は残す(self):
        # 手で書き足した設定を、1項目直した拍子に消してしまわない
        self.put("mystery:\n  deep: 1\n")
        configui.apply_change(self.wiki_dir, "edit.title_length", True, "30")
        got = wikiconfig.read_yaml(self.path)
        self.assertEqual(got["mystery"], {"deep": 1})
        self.assertEqual(got["edit"], {"title_length": 30})

    def test_おかしな値なら書かない(self):
        self.put("edit:\n  title_length: 24\n")
        ok, message, _text = configui.apply_change(
            self.wiki_dir, "edit.title_length", True, "あ")
        self.assertFalse(ok)
        self.assertIn("数を入れてください", message)
        # 元のファイルはそのまま
        self.assertEqual(wikiconfig.read_yaml(self.path)["edit"]["title_length"], 24)

    def test_知らない項目名は断る(self):
        ok, message, _text = configui.apply_change(
            self.wiki_dir, "mystery.deep", True, "1")
        self.assertFalse(ok)
        self.assertIn("知らない項目", message)
        self.assertFalse(os.path.exists(self.path))


class TestScreen(ConfigTestBase):
    """画面の組み立て。**タブに分かれていて、保存ボタンは無い**
    （Wiki設計者の指示、2026-09-18）。"""

    def html(self, tab=""):
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": f"tab={tab}" if tab else "",
        })
        return configui._screen_html(
            wikiconfig.load_config(), wikiconfig.read_yaml(self.path), self.path,
            "testwiki", "/=testwiki", configui._opening_tab(), self.wiki_dir)

    def test_保存ボタンもフォームも無い(self):
        html = self.html()
        self.assertNotIn("<form", html)
        self.assertNotIn('type="submit"', html)

    def test_節ごとのタブが出る(self):
        html = self.html()
        for key, _title, _fields in configui.SECTIONS:
            self.assertIn(f'data-tab="{key}"', html)
            self.assertIn(f'data-panel="{key}"', html)

    def test_Wiki名のタブが末尾にある(self):
        html = self.html()
        self.assertIn(f'data-tab="{configui.WIKINAME_TAB}"', html)
        last = [key for key, _t, _f in configui.SECTIONS][-1]
        self.assertGreater(html.index(f'data-tab="{configui.WIKINAME_TAB}"'),
                           html.index(f'data-tab="{last}"'))

    def test_定義ルールのタブは節のあと_Wiki名の前(self):
        html = self.html()
        last = [key for key, _t, _f in configui.SECTIONS][-1]
        rules = html.index(f'data-tab="{configui.EXTRARULES_TAB}"')
        self.assertGreater(rules, html.index(f'data-tab="{last}"'))
        self.assertLess(rules, html.index(f'data-tab="{configui.WIKINAME_TAB}"'))

    def test_開くのは1つだけ(self):
        html = self.html()
        self.assertIn('data-panel="edit">', html)        # hidden が付かない
        self.assertIn('data-panel="theme" hidden', html)

    def test_tabで開くタブを決められる(self):
        # 名前を変えたあとの戻り先が使う（?tab=wikiname）
        html = self.html(tab=configui.WIKINAME_TAB)
        self.assertIn(f'data-panel="{configui.WIKINAME_TAB}">', html)
        self.assertIn('data-panel="edit" hidden', html)

    def test_知らないタブは先頭に戻す(self):
        self.assertIn('data-panel="edit">', self.html(tab="mystery"))

    def test_窓口とJSの在り処を渡す(self):
        html = self.html()
        self.assertIn(f'data-api="/=testwiki/{configui.CONFIGWIKI_API}"', html)
        self.assertIn(f'src="/=testwiki/{configui.CONFIGWIKI_JS}"', html)


class TestApi(ConfigTestBase):
    """窓口（/.admin/configwiki/api）。**断りもJSONで返す**（画面のHTMLではなく）。"""

    def setUp(self):
        super().setUp()
        userdb.create_db(self.wiki_dir)
        self.kept_secret = auth.SECRET_PATH
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")

    def tearDown(self):
        auth.SECRET_PATH = self.kept_secret
        super().tearDown()

    def call(self, payload, uid="admin"):
        body = json.dumps(payload).encode("utf-8")
        bottle.request.environ.clear()
        bottle.request.environ.update({
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        })
        if uid is not None:
            user = userdb.find_by_uid(self.wiki_dir, uid)
            token = auth.session_token(uid, "testwiki", user["pw"])
            # cookieの名前はWikiごとに分かれている（wikiuser_<Wiki名>）
            bottle.request.environ["HTTP_COOKIE"] = (
                f"{wiki_cookie_name(LOGIN_COOKIE, 'testwiki')}={uid}; "
                f"{wiki_cookie_name(LOGIN_AUTH_COOKIE, 'testwiki')}={token}")
        return configui.render_configwiki_api(self.wiki_dir, {}, "testwiki", False)

    def answer(self, out):
        raw = out.body if hasattr(out, "body") else out
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    def test_未ログインは403(self):
        out = self.call({"op": "set", "path": "edit.title_length",
                         "use": True, "value": "30"}, uid=None)
        self.assertEqual(out.status_code, 403)
        self.assertFalse(self.answer(out)["ok"])
        self.assertFalse(os.path.exists(self.path))

    def test_管理者は書ける(self):
        out = self.call({"op": "set", "path": "edit.title_length",
                         "use": True, "value": "30"})
        got = self.answer(out)
        self.assertTrue(got["ok"])
        self.assertEqual(got["value"], "30")
        self.assertTrue(got["own"])
        self.assertEqual(wikiconfig.read_yaml(self.path), {"edit": {"title_length": 30}})

    def test_状態と控えの一覧も返す(self):
        # 画面の上下は書くたびに変わる。文言を1か所に保つため、組み立てて返す
        self.put("edit:\n  title_length: 24\n")       # 人が直したもの＝控えが出る
        got = self.answer(self.call({"op": "set", "path": "edit.title_length",
                                     "use": True, "value": "30"}))
        self.assertIn("この画面が書いたまま", got["state"])
        self.assertIn("控え", got["backups"])

    def test_おかしな値は400(self):
        out = self.call({"op": "set", "path": "edit.title_length",
                         "use": True, "value": "あ"})
        self.assertEqual(out.status_code, 400)
        self.assertIn("数を入れてください", self.answer(out)["message"])

    def test_知らない操作は400(self):
        out = self.call({"op": "mystery"})
        self.assertEqual(out.status_code, 400)
        self.assertIn("知らない操作", self.answer(out)["message"])


class TestShownPath(unittest.TestCase):
    """画面に出す置き場所。**wikidata/ から書く**（Wiki設計者の指示、2026-09-06）。"""

    def test_設置場所からの相対にする(self):
        from wikilib.paths import BASE_DIR

        got = configui.shown_path(
            os.path.join(BASE_DIR, "wikidata", "testwiki", "config", "default.yaml"))
        self.assertEqual(got, os.path.join("wikidata", "testwiki", "config",
                                           "default.yaml"))

    def test_外にあるものはそのまま(self):
        # 相対にすると "../.." だらけになって、かえって分かりにくい
        self.assertEqual(configui.shown_path("/tmp/somewhere/default.yaml"),
                         "/tmp/somewhere/default.yaml")


class TestSchema(unittest.TestCase):
    """画面に出す項目の並び。"""

    def fields(self):
        return [f for _key, _title, fields in configui.SECTIONS for f in fields]

    def test_項目の書きかたがそろっている(self):
        for field in self.fields():
            for key in ("path", "label", "type", "help"):
                self.assertIn(key, field, field.get("path"))
            self.assertIn(field["type"],
                          ("text", "int", "bool", "html", "lines", "choice"))
            if field["type"] == "choice":
                self.assertTrue(field.get("choices"), field["path"])

    def test_説明にMarkdownを書かない(self):
        """説明はHTMLとしてそのまま出す（エスケープしない）。

        **Markdownは通らない**ので、"**…**" と書くと星がそのまま画面に出る
        （2026-09-06にWiki設計者から指摘。実際にそうなっていた）。強調は
        <strong> で書くこと。"""
        for field in self.fields():
            self.assertNotIn("**", field["help"], field["path"])
            self.assertNotIn("`", field["help"], field["path"])

    def test_同じ項目を2度出さない(self):
        paths = [f["path"] for f in self.fields()]
        self.assertEqual(len(paths), len(set(paths)))

    # 共通の設定に値を持たない項目。**書けば効くが、既定は「指定なし」**
    # （config/default.example.yaml でも例としてコメントにしてある）
    UNSET_BY_DEFAULT = {"theme.menu1_mode", "theme.menu2_mode"}

    def test_共通の設定に無い項目を出していない(self):
        # 説明だけあって効かない項目を並べない。**書けば効く**ことの確認
        common = wikiconfig.load_config()
        for field in self.fields():
            if field["path"] in self.UNSET_BY_DEFAULT:
                continue
            found, _value = configui._walk(common, field["path"])
            self.assertTrue(found, f"{field['path']} が共通の設定に無い")


if __name__ == "__main__":
    unittest.main()
