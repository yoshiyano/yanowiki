"""要求ごとにスレッドを立てる WSGI サーバ（標準ライブラリの wsgiref + ThreadingMixIn）。

自動更新（GET /api/v1/events）は接続を開いたままにするので、bottle の既定のサーバ
（1 本ずつしか処理しない wsgiref）では、その間ほかの要求が止まってしまう。
"""

from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import bottle


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True  # 開いたままの自動更新の接続が、止めるときの妨げにならないように


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class ThreadingServer(bottle.ServerAdapter):
    """bottle.run(app, server=ThreadingServer, host=..., port=...) で使う。"""

    def run(self, app):
        handler = QuietHandler if self.quiet else WSGIRequestHandler
        httpd = make_server(self.host, self.port, app, ThreadingWSGIServer, handler)
        self.port = httpd.server_port
        httpd.serve_forever()
