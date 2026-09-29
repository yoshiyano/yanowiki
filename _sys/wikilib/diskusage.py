"""そのWikiがどれだけ場所を使っているか（ページと添付ファイル）。

テーマがフッタに出すためのもの（Wiki設計者の指示、2026-08-31）。
表示の形はテーマが決められるよう、数えた値と整形済みの文字列の両方を渡す。

## 何を数えるか

    ページ    wiki/ 以下のページファイルすべて
    添付      attach/ 以下のファイルすべて

**バックアップ（pageinfo/backup/）は含めない**（Wiki設計者の指示）。利用者から見て
「自分が置いたもの」はページと添付で、バックアップはシステムが勝手に貯める
控えなので、同じ数字に混ぜると「何を消せば減るのか」が分からなくなる。
下書き（pageinfo/draft/）とアクセスログ（log/）も同じ理由で含めない。

## 数えるのは訊かれたときだけ

フッタは全ページに出るので、毎回ディレクトリを歩くと表示のたびに費用がかかる。
そこで **DiskUsage は渡されただけでは何もせず、テーマが実際に値を使った
ときに初めて数える**（Jinjaが `{{ disk_usage }}` を文字列にする時点）。
使わないテーマは費用ゼロで済む。

## 数え直す間隔（Wiki設計者の指示、2026-08-31）

数えた結果は CACHE_SECONDS（10分）の間だけ使い回す。そのうえで、
**システムを通した変更があったときは、その場でキャッシュを捨てる**
（`invalidate()`）。添付の追加・削除やページの保存は、利用者が
「いま自分がやったこと」なので、フッタの数字がすぐ変わってほしい。

一方、**システムを通さずに置かれたファイル**（サーバー上で直接コピーした、
など）は、こちらから知りようがないので10分の追従で十分としている。
"""
import os
import time

# 数え直す間隔。システムを通した変更は invalidate() で即座に反映されるので、
# ここが受け持つのは「システムを通さずに置かれたファイル」への追従だけ
CACHE_SECONDS = 10 * 60
_cache = {}  # wiki_dir -> (数えた時刻, ページのバイト数, 添付のバイト数)


def invalidate(wiki_dir):
    """そのWikiの数え直しを次の表示で行わせる。

    添付の追加・削除・付け替えや、ページの保存・削除から呼ぶ。
    **数え直しはここではしない**（保存の処理を重くしないため）。
    捨てておくだけで、次にフッタが値を使うときに数え直される。"""
    _cache.pop(wiki_dir, None)


def format_size(size):
    """バイト数を読みやすい文字列にする（"465B" "43KB" "1.2MB" "123MB"）。

    10未満のときだけ小数第1位まで出す。"1MB" と "1.9MB" が同じ表示に
    なってしまうのを避けつつ、桁が大きいところでは細かい数字を出さない。"""
    if size < 1024:
        return "{}B".format(size)
    for unit in ("KB", "MB", "GB"):
        size /= 1024.0
        if size < 1024 or unit == "GB":
            if size < 10:
                return "{:.1f}{}".format(size, unit)
            return "{:.0f}{}".format(size, unit)
    return "{:.0f}GB".format(size)  # ここには来ない（GBで打ち切るため）


def _dir_size(path):
    """そのフォルダ以下のファイルの合計バイト数。読めないものは飛ばす。

    シンボリックリンクの先は数えない（リンク元とリンク先で二重に数えるのを
    避けるため。attach/ に別の場所を指すリンクを置く運用も考えられる）。"""
    total = 0
    stack = [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def measure(wiki_dir):
    """(ページのバイト数, 添付のバイト数) を返す。CACHE_SECONDS の間は使い回す。"""
    now = time.time()
    hit = _cache.get(wiki_dir)
    if hit is not None and now - hit[0] < CACHE_SECONDS:
        return hit[1], hit[2]
    pages = _dir_size(wiki_dir)
    # 添付の置き場所は wiki/ の隣（attach.attach_dir_for と同じ組み立て）
    attached = _dir_size(os.path.join(os.path.dirname(wiki_dir), "attach"))
    _cache[wiki_dir] = (now, pages, attached)
    return pages, attached


class DiskUsage:
    """テーマへ渡す値。**使われるまで数えない。**

    テーマからの使いかた（どれも同じ数字を別の形で出すだけ）。

        {{ disk_usage.text }}     DiskUsage: Page/Attached 1.2MB/349KB
        {{ disk_usage }}          1.2MB/349KB
        {{ disk_usage.page }}     1.2MB
        {{ disk_usage.attached }} 349KB

    バイト数そのものが要るときは page_bytes / attached_bytes。
    自分で単位を付けたい場合や、大きさで色を変えたい場合に使える。"""

    def __init__(self, wiki_dir):
        self._wiki_dir = wiki_dir
        self._sizes = None

    def _measured(self):
        if self._sizes is None:  # 1回のページ表示の中では数え直さない
            self._sizes = measure(self._wiki_dir)
        return self._sizes

    @property
    def page_bytes(self):
        return self._measured()[0]

    @property
    def attached_bytes(self):
        return self._measured()[1]

    @property
    def page(self):
        return format_size(self.page_bytes)

    @property
    def attached(self):
        return format_size(self.attached_bytes)

    @property
    def text(self):
        """Wiki設計者が指定した形（2026-08-31）。テーマはこれを置くだけでよい。"""
        return "DiskUsage: Page/Attached {}/{}".format(self.page, self.attached)

    def __str__(self):
        return "{}/{}".format(self.page, self.attached)
