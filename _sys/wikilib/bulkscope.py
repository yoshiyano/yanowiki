"""たくさんのページをまとめて書き換える操作を速くする範囲（`with scope():`）。

名前の変更（`pagerename.rename_page`）は、動かしたページを指していたページを
1枚ずつ「編集画面から保存したのと同じ扱い」で保存し直す。1枚ごとに DB の書き込みと
本文の解析が何度も起きるので、`=webfiledir/` のフォルダ1つの名前の変更に 1.6 秒
かかり、画面が止まって見えた（2026-10-01、Wiki設計者の報告・指示「修正して
ください」）。内訳は DB の確定（commit）ごとの同期が約 0.7 秒（59 回）、本文の
解析が約 0.85 秒（57 回）だった。この範囲の中では次の2つを行う。

**DB の接続を1つにまとめ、最後に1回だけ確定する。** `pagedb.connect`・
`backup.connect` は、範囲の中ではDBのファイルごとに1つの接続を使い回す
（`adopt`）。呼び出し側の `with connect(…) as con:` は、範囲の中では抜けても
確定しない。範囲を出るときに確定する。途中で例外が起きても、そこまでの書き込みは
確定する（範囲を使わないときも1操作ずつ確定していたので、残りかたは同じ）。

**同じ本文の解析結果を使い回す**（`parse`）。保存し直す1枚の本文は、リンクを
直すとき・リンクとタイトルを記録し直すときに、同じ形で何度も解析される。
結果のトークン列は読むだけの使いかた（地の文の範囲・タイトル・目次・
プラグインの引数）にしか渡さないので、同じものを渡してよい。鍵には解析の
しかた（呼ぶ場所ごとの設定・使うエンジン）を含める。PukiWiki記法は呼ぶ場所で
生HTMLの扱いが違い、同じ本文でも結果が変わるため。

範囲の外では、どちらもこれまでどおり（1操作ずつ接続して確定し、解析も毎回行う）。

注意: 範囲の中で、`pagedb.connect`・`backup.connect` を通さずに同じ DB へ
書き込む接続を開くと、まとめている書き込みの鍵を待って止まる。DB への書き込みは
この2つの関数を通すこと。
"""
import contextlib
import contextvars

_connections = contextvars.ContextVar("bulkscope_connections", default=None)
_parses = contextvars.ContextVar("bulkscope_parses", default=None)


class _SharedConnection:
    """範囲の中で connect() が返すもの。`with` を抜けても確定せず、close() もしない。"""

    def __init__(self, con):
        self._con = con

    def __enter__(self):
        return self._con

    def __exit__(self, *exc):
        return False

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._con, name)


@contextlib.contextmanager
def scope():
    """まとめて書き換える範囲。入れ子にすると、いちばん外側の範囲にまとまる。"""
    if _connections.get() is not None:
        yield
        return
    con_token = _connections.set({})
    parse_token = _parses.set({})
    try:
        yield
    finally:
        connections = _connections.get()
        _connections.reset(con_token)
        _parses.reset(parse_token)
        for con in connections.values():
            try:
                con.commit()
            finally:
                con.close()


def adopt(path, open_connection):
    """範囲の中なら、DBのファイル path の共有の接続を返す（まだ無ければ
    open_connection() で開いて覚える）。範囲の外なら None。"""
    connections = _connections.get()
    if connections is None:
        return None
    con = connections.get(path)
    if con is None:
        con = connections[path] = open_connection()
    return _SharedConnection(con)


def parse(key, engine, text, run):
    """範囲の中なら、同じ (key, engine, text) の解析結果を使い回す。外なら run() そのもの。

    engine は鍵に使うだけでなく、範囲のあいだ参照を持っておく（解放されて同じ id の
    別のエンジンが作られ、取り違えるのを防ぐため）。"""
    cache = _parses.get()
    if cache is None:
        return run()
    k = (key, id(engine), text)
    hit = cache.get(k)
    if hit is None:
        hit = cache[k] = (engine, run())
    return hit[1]
