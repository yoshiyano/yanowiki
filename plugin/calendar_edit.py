"""calendar_edit — [calendar](/Syntax/Plugin/calendar) を「edit」のモードで表示する。

    #calendar_edit                   今月。日ごとのページはこのページの下
    #calendar_edit(日記, 202609)      書きかたは calendar と同じ

 1. date … 表示する年月（6桁の `yyyymm`） (default: 今月)
 2. page … 日ごとのページを置く場所のページ名 (default: このページ)

**すべての日付を押せます。** まだ無い日を押すと、その日のページの新規編集の画面が
開きます（編集の権限がある人だけ。無い人には、ページへのリンクです）。表題には
`(edit)` と出ます。
"""

""" 技術資料
本家 `calendar_edit.inc.php` の移植。本家は `global $command = 'edit'` にしてから
`plugin_calendar_convert` を呼んだ。ここでは兄弟の `calendar.py` を読み込んで
`render(resolved, context, "edit")` を呼ぶ。本家が `?cmd=edit` へ直接リンクした
ところをページのURLへのリンクにした理由は `calendar.py` の技術資料「日付のリンク」。
"""
import importlib.util
import os

PLUGIN_INFO = {
    "help": "#calendar_edit(date,page)",
    "args": [
        {"name": "date", "candidate": [(r"\d{6}", "re")], "default": "", "label": "年月（6桁の yyyymm）"},
        {"name": "page", "num_order": -1, "link": True},
    ],
}


def _load_calendar():
    """兄弟の calendar.py（本家の require_once PLUGIN_DIR . 'calendar.inc.php'）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendar.py")
    spec = importlib.util.spec_from_file_location("wikiplugin_calendar_for_edit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _convert(resolved, body, context):
    return _load_calendar().render(resolved, context, "edit")
