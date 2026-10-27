#!/usr/bin/env python3
"""ページを開いている間の polling（2026-10-23、`plugin/_polling.py`）。

- `comment`・`vote` の描画範囲を `.poll-box` で包み、ページ・ID・問い合わせ先・版を持たせる
- 問い合わせ（`/.plugin/<name>?poll=1`）は、版が同じなら `unchanged`、違えば ID ごとに
  描き直した HTML を返す。無い ID は `missing`。同じ ID が重なっていれば最初のもの
- 問い合わせでは本文を書き換えない。閲覧できないページはすべて `missing`
- 送信ボタンは JS が動くまで押せない（`data-needs-js`）

実行:
    _venv/bin/python3 tests/test_polling.py
"""
import json
import os
import re
import sys
import unittest
from unittest import mock
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_callid import ID, VID, CallIdTestBase, load_plugin  # noqa: E402  （_sys を path に足す）

import bottle  # noqa: E402
from wikilib.auth import PAGE_NONE  # noqa: E402
from wikilib.plugins import PluginContext  # noqa: E402


class PollingTestBase(CallIdTestBase):
    def poll(self, page, ids, version="", name="comment", privilege=None):
        bottle.request.bind({
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": urlencode({"poll": "1", "page": page, "ids": ",".join(ids),
                                       "version": version}),
        })
        context = PluginContext(config={}, farm="t", wiki_dir=self.wiki_dir, page="",
                                base_url="")
        patch = (mock.patch.object(PluginContext, "privilege", new_callable=mock.PropertyMock,
                                   return_value=mock.Mock(check=mock.Mock(return_value=privilege)))
                 if privilege is not None else mock.MagicMock())
        try:
            with patch:
                r = load_plugin(name)._action(context)
        finally:
            bottle.request.bind({})
        self.assertEqual(r.status_code, 200)
        return json.loads(r.body)

    @staticmethod
    def boxes(html):
        return re.findall(r'<div class="poll-box" data-poll-page="([^"]*)" data-poll-id="([^"]*)" '
                          r'data-poll-action="([^"]*)" data-poll-version="([^"]*)">', html)


class TestWrap(PollingTestBase):
    def test_描画範囲を印で包む(self):
        self.write("Top", "#comment()\n\n#vote(a,b)\n")
        html = self.render("Top")
        (cid,) = re.findall(ID, self.read("Top"))
        (vid,) = re.findall(VID, self.read("Top"))
        boxes = self.boxes(html)
        self.assertEqual([b[:3] for b in boxes], [("Top", cid, "/.plugin/comment"),
                                                  ("Top", vid, "/.plugin/vote")])
        self.assertEqual(boxes[0][3], boxes[1][3])
        self.assertIn("<noscript>", html)
        self.assertIn("data-needs-js", html)

    def test_資材を読み込む印を立てる(self):
        self.write("Top", "#comment()\n")
        self.render("Top")
        _html, context = self.render_once("Top")
        self.assertIn("_polling", context.used_plugins)


class TestHandle(PollingTestBase):
    def test_版が同じなら描かない(self):
        self.write("Top", "#comment()\n")
        html = self.render("Top")
        (_page, cid, _action, version) = self.boxes(html)[0]
        self.assertEqual(self.poll("Top", [cid], version), {"unchanged": True})

    def test_新しい投稿を描いて返し_知らないIDはmissing(self):
        self.write("Top", "#comment()\n")
        html = self.render("Top")
        (_page, cid, _action, version) = self.boxes(html)[0]
        r = self.post("comment", page="Top", msg="新しい投稿", comment_id=cid, newtop="1")
        self.assertEqual(r.status_code, 204)
        data = self.poll("Top", [cid, "cmtZZZZZ"], version)
        self.assertNotEqual(data["version"], version)
        self.assertEqual(data["calls"]["cmtZZZZZ"], {"missing": True})
        fresh = data["calls"][cid]["html"]
        self.assertIn("新しい投稿", fresh)
        self.assertEqual(self.boxes(fresh)[0][:2], ("Top", cid))
        self.assertEqual(self.boxes(fresh)[0][3], data["version"])

    def test_voteの票数も返す(self):
        self.write("Top", "#vote(a,b)\n")
        html = self.render("Top")
        (_page, vid, _action, version) = self.boxes(html)[0]
        self.post("vote", page="Top", vote_id=vid, index="1")
        data = self.poll("Top", [vid], version, name="vote")
        self.assertIn("1票（100%）", data["calls"][vid]["html"])

    def test_重なっていれば最初に一致したもの(self):
        text = '#comment(見出しA, id="cmt0abcd")\n\n#comment(見出しB, id="cmt0abcd")\n'
        self.write("Top", text)
        data = self.poll("Top", ["cmt0abcd"])
        self.assertIn("見出しA", data["calls"]["cmt0abcd"]["html"])
        self.assertNotIn("見出しB", data["calls"]["cmt0abcd"]["html"])
        # 問い合わせでは振り直さない（本文を書き換えない）
        self.assertEqual(self.read("Top"), text)

    def test_IDの無い呼び出しがあっても書き換えない(self):
        self.write("Top", '#comment(id="cmt0abcd")\n\n#comment()\n')
        data = self.poll("Top", ["cmt0abcd"])
        self.assertIn("poll-box", data["calls"]["cmt0abcd"]["html"])
        self.assertEqual(self.read("Top"), '#comment(id="cmt0abcd")\n\n#comment()\n')

    def test_閲覧できない_無いページはすべてmissing(self):
        self.write("Top", '#comment(id="cmt0abcd")\n')
        data = self.poll("Top", ["cmt0abcd"], privilege=PAGE_NONE)
        self.assertEqual(data["calls"], {"cmt0abcd": {"missing": True}})
        data = self.poll("Nothing", ["cmt0abcd"])
        self.assertEqual(data["calls"], {"cmt0abcd": {"missing": True}})

    def test_差し込んだページは_そのページとして問い合わせる(self):
        self.write("Sub", '#comment(id="cmt0wxyz")\n')
        self.write("Top", '#comment(id="cmt0abcd")\n\n#include(Sub)\n')
        html = self.render("Top")
        self.assertEqual([b[:2] for b in self.boxes(html)], [("Top", "cmt0abcd"), ("Sub", "cmt0wxyz")])
        self.assertEqual(self.poll("Sub", ["cmt0abcd"])["calls"]["cmt0abcd"], {"missing": True})
        self.assertIn("poll-box", self.poll("Sub", ["cmt0wxyz"])["calls"]["cmt0wxyz"]["html"])


    def test_表のセルの中の呼び出しにも答える(self):
        self.write("Top", '#table(){{\n|~欄|h\\\\\n|#comment(id="cmt0cell")|\\\\\n}}\n')
        html = self.render("Top")
        self.assertEqual([b[:2] for b in self.boxes(html)], [("Top", "cmt0cell")])
        self.post("comment", page="Top", msg="セルの投稿", comment_id="cmt0cell", newtop="1")
        data = self.poll("Top", ["cmt0cell"], self.boxes(html)[0][3])
        self.assertIn("セルの投稿", data["calls"]["cmt0cell"]["html"])


if __name__ == "__main__":
    unittest.main()
