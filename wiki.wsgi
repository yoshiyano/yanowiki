"""WSGIサーバから使うときの入口。

    uWSGI     : uwsgi --wsgi-file /path/to/wikiSystem/wiki.wsgi
    Apache    : WSGIScriptAlias / /path/to/wikiSystem/wiki.wsgi

このファイルは「ファイルとして読み込む」サーバ向け。gunicorn はモジュール名で
指定する仕組みなので、このファイルではなく wiki.py を直に指す。

    gunicorn  : gunicorn --chdir /path/to/wikiSystem 'wiki:app'

（gunicorn に 'wiki.wsgi:application' と渡すと、wiki パッケージの wsgi モジュールを
探しにいって失敗する。）

いずれも nginx や Apache の後ろに置いて使える。

`wiki.py` を import すると、直接実行のときだけ働く _venv での再実行は行われない
（サーバごと置き換えてしまうため）。**そのため、依存パッケージの入ったPythonで
サーバを起動する必要がある。** 例:

    /path/to/wikiSystem/_venv/bin/gunicorn 'wiki:app'

/.restart は、このファイルの更新時刻を読み直しの合図に使うことがある。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wiki import app as application  # noqa: E402
