"""calendar_read — [calendar](/Syntax/Plugin/calendar) を「read」のモードで表示する。

    #calendar_read                   今月。日ごとのページはこのページの下
    #calendar_read(日記, 202609)      書きかたは calendar と同じ

 1. date … 表示する年月（6桁の `yyyymm`） (default: 今月)
 2. page … 日ごとのページを置く場所のページ名 (default: このページ)

その日のページがあるときだけ、日付がリンクになります（[calendar](/Syntax/Plugin/calendar)
と同じ）。表題には `(read)` と出ます。
"""

""" 技術資料
本家 `calendar_read.inc.php` の移植。本家は `global $command = 'read'` にしてから
`plugin_calendar_convert` を呼んだ。ここでは兄弟の `calendar.py` を読み込んで
`render(resolved, context, "read")` を呼ぶ（`calendar` の既定と同じ動き）。
"""
import importlib.util
import os

PLUGIN_INFO = {
    "help": "#calendar_read(date,page)",
    "args": [
        {"name": "date", "candidate": [(r"\d{6}", "re")], "default": "", "label": "年月（6桁の yyyymm）"},
        {"name": "page", "num_order": -1, "link": True},
    ],
}


def _load_calendar():
    """兄弟の calendar.py（本家の require_once PLUGIN_DIR . 'calendar.inc.php'）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendar.py")
    spec = importlib.util.spec_from_file_location("wikiplugin_calendar_for_read", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _convert(resolved, body, context):
    return _load_calendar().render(resolved, context, "read")
