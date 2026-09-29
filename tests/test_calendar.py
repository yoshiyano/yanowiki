#!/usr/bin/env python3
"""カレンダー系プラグイン（calendar・calendar_edit・calendar_read・calendar2・
calendar3・calendar_viewer）のテスト。

本家PukiWikiの書きかた（引数の順の自由・日ごとのページの名前・予定表の書式）が
そのまま通ること、閲覧できないページを「無いページ」と同じに扱うこと、年月の
移動（同じページを問い合わせ付きで開き直す）を見る。「今日」は 2026-09-25 に固定する。

実行:
    .venv/bin/python3 -m unittest discover -s tests
    .venv/bin/python3 tests/test_calendar.py     （このファイルだけ）
"""
import datetime
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_sys"))

import bottle  # noqa: E402

from wikilib import auth, paths, privilege_records, userdb  # noqa: E402
from wikilib.auth import act_as  # noqa: E402
from wikilib.pagesync import sync_wiki  # noqa: E402
from wikilib.paths import farm_plugin_dir  # noqa: E402
from wikilib.plugins import PluginContext, build_markdown_renderer  # noqa: E402
from wikilib.render import parse_source  # noqa: E402

FARM = "testwiki"
TODAY = datetime.date(2026, 9, 25)


class FixedDate(datetime.date):
    @classmethod
    def today(cls):
        return cls(TODAY.year, TODAY.month, TODAY.day)


def load_plugin(name):
    spec = importlib.util.spec_from_file_location(
        f"plugin_under_test_{name}", os.path.join(ROOT, "plugin", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CalendarTestBase(unittest.TestCase):
    PAGES = {}

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="calendar-")
        self.wiki_dir = os.path.join(self.work, "wikidata", FARM, "wiki")
        os.makedirs(self.wiki_dir)
        userdb.create_db(self.wiki_dir, "adminpw")
        userdb.add_user(self.wiki_dir, "alice",
                        userdb.hash_password(self.wiki_dir, "alice", "p"), "alice")
        self.kept = (paths.WIKIDATA_DIR, auth.SECRET_PATH)
        paths.WIKIDATA_DIR = os.path.join(self.work, "wikidata")
        auth.SECRET_PATH = os.path.join(self.work, "config", "secret.txt")
        for name, text in self.PAGES.items():
            self.put(name, text)
        sync_wiki(self.wiki_dir, {})
        self.query("")
        self.date_patch = mock.patch("datetime.date", FixedDate)
        self.date_patch.start()

    def tearDown(self):
        self.date_patch.stop()
        paths.WIKIDATA_DIR, auth.SECRET_PATH = self.kept
        bottle.request.bind({})
        shutil.rmtree(self.work, ignore_errors=True)

    def put(self, name, text, ext=".txt"):
        path = os.path.join(self.wiki_dir, name + ext)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def query(self, text):
        bottle.request.bind({"QUERY_STRING": text, "REMOTE_ADDR": "192.0.2.1"})

    def render(self, text, page="Top", uid=None, ext=".txt"):
        context = PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page=page,
                                base_url="", ext=ext)
        md = build_markdown_renderer({}, farm_plugin_dir(self.wiki_dir), context)
        env = {"wiki": context}
        with (act_as(uid) if uid else mock.MagicMock()):
            html = md.renderer.render(parse_source(md, text, ext, env), md.options, env)
        self.context = context
        return html

    def restrict(self, page, kind, who):
        ok, message, _ = privilege_records.put(self.wiki_dir, page, kind, who)
        self.assertTrue(ok, message)


def linked_days(html):
    """日付がリンクになっている日の一覧。"""
    return [int(d) for d in re.findall(r"<a [^>]*><strong>(\d+)</strong></a>", html)]


class TestCalendar(CalendarTestBase):
    PAGES = {"日記/20260903": "3日", "日記/20260925": "25日", "秘密/20260910": "秘密"}

    def test_年月とページ名はどちらの順でもよい(self):
        for text in ("#calendar(日記,202609)", "#calendar(202609,日記)"):
            with self.subTest(text=text):
                html = self.render(text)
                self.assertIn("2026.9 (read)", html)
                self.assertEqual(linked_days(html), [3, 25])

    def test_今月と今日(self):
        html = self.render("#calendar(日記)")
        self.assertIn('<td class="style_td_today">', html)
        self.assertNotIn("style_td_today", self.render("#calendar(日記,202608)"))

    def test_曜日のクラス(self):
        html = self.render("#calendar(日記,202609)")
        # 2026-09-06 は日曜、09-05 は土曜
        self.assertIn('<td class="style_td_sun"><strong>6</strong>', html)
        self.assertIn('<td class="style_td_sat"><strong>5</strong>', html)
        self.assertEqual(html.count("style_td_blank"), 2 + 3)   # 前に火曜まで2つ、後ろに3つ

    def test_editはある日はリンク_まだ無い日は新規編集を直接開く(self):
        html = self.render("#calendar_edit(日記,202609)")
        self.assertIn("2026.9 (edit)", html)
        self.assertEqual(linked_days(html), [3, 25])
        self.assertIn('<form class="calendar-new" method="post" action="/%E6%97%A5%E8%A8%98/20260901">'
                      '<input type="hidden" name="cmd" value="edit">'
                      '<button type="submit" title="日記/20260901"><strong>1</strong></button></form>',
                      html)
        self.assertEqual(html.count('class="calendar-new"'), 28)

    def test_editで編集の権限が無ければまだ無い日もリンク(self):
        self.restrict("日記/*", "W", "alice")
        html = self.render("#calendar_edit(日記,202609)")
        self.assertEqual(len(linked_days(html)), 30)
        self.assertNotIn("calendar-new", html)

    def test_readはcalendarと同じ(self):
        html = self.render("#calendar_read(日記,202609)")
        self.assertIn("2026.9 (read)", html)
        self.assertEqual(linked_days(html), [3, 25])

    def test_閲覧できないページは無いページと同じ(self):
        self.restrict("秘密/20260910", "R", "alice")
        self.assertEqual(linked_days(self.render("#calendar(秘密,202609)")), [])
        self.assertEqual(linked_days(self.render("#calendar(秘密,202609)", uid="alice")), [10])

    def test_年月でない引数が2つならエラー(self):
        self.assertIn("plugin-error", self.render("#calendar(foo,bar)"))

    def test_月のはみ出しは年へ繰り上げる(self):
        self.assertIn("2027.1 (read)", self.render("#calendar(日記,202613)"))

    def test_既定はこのページの下(self):
        html = self.render("#calendar_edit(202609)", page="日記")
        self.assertIn('title="日記/20260901"', html)


class TestCalendar2(CalendarTestBase):
    PAGES = {"日記/2026-09-03": "3日の本文", "日記/2026-09-25": "今日の本文",
             "日記/2026-08-01": "8月1日の本文", "2026-09-10": "頭なし"}

    def test_ページがある日はリンク_無い日は作るためのリンク(self):
        html = self.render("#calendar2(日記,202609,off)")
        self.assertEqual(linked_days(html), [3, 25])
        self.assertIn('<form class="calendar-new small" method="post"'
                      ' action="/%E6%97%A5%E8%A8%98/2026-09-01"><input type="hidden" name="cmd"'
                      ' value="edit"><button type="submit" title="日記/2026-09-01">1</button></form>',
                      html)

    def test_編集の権限が無ければ無い日は数字だけ(self):
        self.restrict("日記/*", "W", "alice")
        html = self.render("#calendar2(日記,202609,off)")
        self.assertNotIn("calendar-new", html)
        self.assertIn('<span class="small">1</span>', html)

    def test_今日のページの中身を並べる(self):
        html = self.render("#calendar2(日記)")
        self.assertIn('<div class="calendar2-today">', html)
        self.assertIn("今日の本文", html)
        self.assertIn("[この日記を編集]", html)
        self.assertNotIn("今日の本文", self.render("#calendar2(日記,off)"))

    def test_別の月ではその月の1日のページ(self):
        html = self.render("#calendar2(日記,202608)")
        self.assertIn("8月1日の本文", html)

    def test_今日のページが無ければ空と出す_名前は新規編集を直接開く(self):
        html = self.render("#calendar2(日記,202607)")
        self.assertIn('<div class="calendar2-empty"><form class="calendar-new calendar2-new" method="post"'
                      ' action="/%E6%97%A5%E8%A8%98/2026-07-01">'
                      '<input type="hidden" name="cmd" value="edit">'
                      '<button type="submit" title="日記/2026-07-01">日記/2026-07-01</button></form>'
                      'は空です。</div>', html)

    def test_編集の権限が無ければ空の案内は文字だけ(self):
        self.restrict("日記/*", "W", "alice")
        html = self.render("#calendar2(日記,202607)")
        self.assertIn('<div class="calendar2-empty">日記/2026-07-01は空です。</div>', html)

    def test_星は頭に何も付けない(self):
        html = self.render("#calendar2(*,202609,off)")
        self.assertEqual(linked_days(html), [10])

    def test_前後の月へは同じページを問い合わせ付きで開く(self):
        html = self.render("#calendar2(日記,off)", page="Top")
        self.assertIn('href="/Top?plugin=calendar2&amp;file=%E6%97%A5%E8%A8%98&amp;date=202608"',
                      html)
        self.query("plugin=calendar2&file=%E6%97%A5%E8%A8%98&date=202608")
        self.assertIn("<strong>2026.8</strong>", self.render("#calendar2(日記,off)"))
        # 別の基準のカレンダーは動かない
        self.assertIn("<strong>2026.9</strong>", self.render("#calendar2(別,off)"))

    def test_前後の月は枠の中身だけを取りに行ける(self):
        html = self.render("#calendar2(日記)", page="Top")
        self.assertIn('<div class="calendar2-frame" data-calendar2-api="/.plugin/calendar2"'
                      ' data-calendar2-page="Top" data-calendar2-file="日記" data-calendar2-off="0">',
                      html)
        self.assertIn('data-calendar2-date="202608"', html)
        c2 = load_plugin("calendar2")
        self.query("file=%E6%97%A5%E8%A8%98&date=202608&page=Top&off=0")
        context = PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page="",
                                base_url="")
        inner = c2._action(context)
        self.assertTrue(inner.startswith('<div class="calendar2">'))
        self.assertIn("<strong>2026.8</strong>", inner)
        self.assertIn("8月1日の本文", inner)         # 別の月ではその月の1日
        self.assertIn('href="/Top?plugin=calendar2', inner)
        self.query("file=*&date=202609&page=Top&off=1")
        inner = c2._action(context)
        self.assertTrue(inner.startswith('<table class="calendar style_calendar">'))
        self.assertEqual(linked_days(inner), [10])

    def test_今日のページが閲覧できなければ空と同じ(self):
        self.restrict("日記/2026-09-25", "R", "alice")
        html = self.render("#calendar2(日記)")
        self.assertNotIn("今日の本文", html)
        self.assertIn("は空です。", html)


SCHEDULE = """予定
- 5/22 締め切り
- 6/6  懇談会::（八草）\\n3年次担当
- 7/11-12	&color(brown){オープンキャンパス};
- 14/25 翌年の予定
- 1/30-33 月をまたぐ
- 4
-- 13	prog1-1
-- 20-21 合宿
- 6
-- 1	prog1-7
"""


class TestCalendar3(CalendarTestBase):
    PAGES = {"schedule2026": SCHEDULE}

    def items(self, html):
        return {int(m.group(1)): m.group(2) for m in re.finditer(
            r"<strong>(\d+)</strong><div class=\"calendar3-items\">(.*?)</div>", html, re.S)
            if m.group(2)}

    def test_予定の読みかた(self):
        c3 = load_plugin("calendar3")
        got = c3.parse_schedule(SCHEDULE, 2026)
        self.assertIn((2026, 5, 22, 22, "締め切り"), got)
        self.assertIn((2026, 7, 11, 12, "&color(brown){オープンキャンパス};"), got)
        self.assertIn((2027, 2, 25, 25, "翌年の予定"), got)
        self.assertIn((2026, 4, 13, 13, "prog1-1"), got)
        self.assertIn((2026, 4, 20, 21, "合宿"), got)
        self.assertIn((2026, 6, 1, 1, "prog1-7"), got)

    def test_月の升目に並ぶ(self):
        html = self.render("#calendar3(schedule2026,202607)")
        items = self.items(html)
        self.assertEqual(sorted(items), [11, 12])
        self.assertIn('<span style="color:brown">オープンキャンパス</span>', items[11])

    def test_ツールチップ(self):
        items = self.items(self.render("#calendar3(schedule2026,202606)"))
        self.assertEqual(items[6], '・<span title="（八草）\n3年次担当">懇談会</span><br>')

    def test_年はページ名の末尾4桁_13月以降は翌年(self):
        self.assertEqual(sorted(self.items(self.render("#calendar3(schedule2026,202702)"))), [25])
        self.assertIn("翌年の予定", self.render("#calendar3(schedule2026,202702)"))

    def test_月末を越える期間(self):
        self.assertEqual(sorted(self.items(self.render("#calendar3(schedule2026,202601)"))),
                         [30, 31])
        self.assertEqual(sorted(self.items(self.render("#calendar3(schedule2026,202602)"))),
                         [1, 2])

    def test_ツリー形式の期間(self):
        self.assertEqual(sorted(self.items(self.render("#calendar3(schedule2026,202604)"))),
                         [13, 20, 21])

    def test_予定表を閲覧できなければ予定を出さない(self):
        self.restrict("schedule2026", "R", "alice")
        html = self.render("#calendar3(schedule2026,202607)")
        self.assertEqual(self.items(html), {})
        self.assertIn("予定表を閲覧する権限がありません", html)
        self.assertEqual(sorted(self.items(self.render("#calendar3(schedule2026,202607)",
                                                        uid="alice"))), [11, 12])

    def test_前後の月は表だけを取りに行ける(self):
        html = self.render("#calendar3(schedule2026,202607)", page="Top")
        self.assertIn('data-calendar3-api="/.plugin/calendar3"', html)
        self.assertIn('data-calendar3-date="202606"', html)
        self.assertIn('href="/Top?plugin=calendar3&amp;file=schedule2026&amp;date=202608"', html)
        c3 = load_plugin("calendar3")
        self.query("file=schedule2026&date=202606&page=Top")
        context = PluginContext(config={}, farm=FARM, wiki_dir=self.wiki_dir, page="",
                                base_url="")
        table = c3._action(context)
        self.assertTrue(table.startswith('<table class="calendar calendar3'))
        self.assertIn("懇談会", table)
        self.assertIn('href="/Top?plugin=calendar3', table)

    def test_offなら既定の予定表(self):
        self.assertIn("[<a href=\"/%E4%BA%88%E5%AE%9A%E8%A1%A8\">予定表</a>]",
                      self.render("#calendar3(off,202607)"))


class TestCalendarViewer(CalendarTestBase):
    PAGES = {f"日記/{d}": f"{d}の本文" for d in (
        "2026-08-16", "2026-09-22", "2026-09-24", "2026-09-25", "2026-09-27", "2026-10-25")}
    PAGES.update({"日記/メモ": "日付でない", "旧日記/20260925": "区切り無しの本文"})

    def shown(self, html):
        return re.findall(r"(\d{4}-\d{2}-\d{2})の本文", html)

    def test_今月の過去を新しい順(self):
        html = self.render("#calendar_viewer(日記,this)")
        self.assertEqual(self.shown(html), ["2026-09-25", "2026-09-24", "2026-09-22"])
        self.assertIn("2026/9/25 (金)", html)
        self.assertIn("&lt;&lt;2026-10", html)
        self.assertIn("2026-08&gt;&gt;", html)

    def test_future_と_view(self):
        self.assertEqual(self.shown(self.render("#calendar_viewer(日記,this,future)")),
                         ["2026-09-25", "2026-09-27"])
        self.assertEqual(self.shown(self.render("#calendar_viewer(日記,2026-09,view)")),
                         ["2026-09-22", "2026-09-24", "2026-09-25", "2026-09-27"])

    def test_件数と飛ばし(self):
        html = self.render("#calendar_viewer(日記,2)")
        self.assertEqual(self.shown(html), ["2026-09-25", "2026-09-24"])
        self.assertIn("次の2件&gt;&gt;", html)
        html = self.render("#calendar_viewer(日記,2*2)")
        self.assertEqual(self.shown(html), ["2026-09-22", "2026-08-16"])
        self.assertIn("&lt;&lt;前の2件", html)
        self.assertNotIn("次の2件", html)

    def test_本文は省略のための枠で包む(self):
        html = self.render("#calendar_viewer(日記,1)")
        self.assertIn('<div class="calendar_viewer-body">\n', html)
        self.assertIn("calendar_viewer", self.context.used_plugins)

    def test_区切り無し(self):
        html = self.render("#calendar_viewer(旧日記,this,past,none)")
        self.assertIn("区切り無しの本文", html)

    def test_閲覧できないページは並ばない(self):
        self.restrict("日記/2026-09-24", "R", "alice")
        self.assertEqual(self.shown(self.render("#calendar_viewer(日記,this)")),
                         ["2026-09-25", "2026-09-22"])

    def test_同じページを2つの一覧に出せる(self):
        html = self.render("#calendar_viewer(日記,1)\n#calendar_viewer(日記,this)")
        self.assertEqual(self.shown(html).count("2026-09-25"), 2)

    def test_置いたページ自身は差し込まない(self):
        html = self.render("#calendar_viewer(日記,this)", page="日記/2026-09-25")
        self.assertIn("このページ自身は差し込めません", html)

    def test_同じ基準は4つまで(self):
        html = self.render("\n".join(["#calendar_viewer(日記,1)"] * 5))
        self.assertEqual(self.shown(html).count("2026-09-25"), 4)
        self.assertIn("plugin-error", html)

    def test_互いに差し込み合っても止まる(self):
        self.put("日記/2026-09-24", "#calendar_viewer(日記,this)")
        self.put("日記/2026-09-25", "#calendar_viewer(日記,this)")
        sync_wiki(self.wiki_dir, {})
        html = self.render("#calendar_viewer(日記,this)")
        self.assertIn("plugin-error", html)

    def test_前後のリンクで開き直す(self):
        self.query("plugin=calendar_viewer&file=%E6%97%A5%E8%A8%98&date=2026-10&mode=past&date_sep=-")
        self.assertEqual(self.shown(self.render("#calendar_viewer(日記,this)")), [])
        self.query("plugin=calendar_viewer&file=%E6%97%A5%E8%A8%98&date=2026-08&mode=past&date_sep=-")
        self.assertEqual(self.shown(self.render("#calendar_viewer(日記,this)")), ["2026-08-16"])

    def test_2つ目の引数が読めなければエラー(self):
        self.assertIn("plugin-error", self.render("#calendar_viewer(日記,きのう)"))


if __name__ == "__main__":
    unittest.main()
