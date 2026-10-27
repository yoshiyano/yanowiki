"""時間のかかるコマンドを裏で行う（ジョブ）。

宣言に job=True と書いたコマンドは、コマンド API（POST commands/<id>）がジョブを始めて番号を返し、
FrontEnd は GET jobs/<番号> で進み具合（何件中何件・処理中の項目）を問い合わせる。終わったら、
ふつうに行ったときと同じ応答（項目ごとの結果など）を返す。中止（POST jobs/<番号>/cancel）は、
項目と項目の間で効く（ops.bulk が確かめる）。
"""

import contextvars
import logging
import threading
import time
import uuid

from .errors import ApiError

log = logging.getLogger(__name__)

KEEP_SECONDS = 600  # 終わったジョブを覚えておく時間（FrontEnd が結果を受け取るまで）

# 処理中のジョブ（ジョブのスレッドの中だけ）。ops.bulk が進み具合を数え、中止を確かめるのに使う
current: contextvars.ContextVar = contextvars.ContextVar("webfiledir_job", default=None)


class Job:
    def __init__(self, mount: str):
        self.id = uuid.uuid4().hex
        self.mount = mount
        self.state = "running"   # "running" / "done"
        self.done = 0            # 終わった項目の数
        self.total = 0           # 項目の数（ops.bulk が数える）
        self.item = ""           # 処理中の項目（パス）
        self.cancelled = False
        self.result = None       # 終わったときの応答（ふつうに行ったときと同じ形）
        self.error = None        # ApiError で終わったとき {"error": {...}}
        self.status = 200
        self.finished = None
        self._lock = threading.Lock()

    # --- 処理の側から（ops.bulk） ---

    def add_total(self, n: int) -> None:
        with self._lock:
            self.total += n

    def begin(self, item: str) -> None:
        with self._lock:
            self.item = item

    def advance(self) -> None:
        with self._lock:
            self.done += 1

    # --- FrontEnd の側から ---

    def cancel(self) -> None:
        self.cancelled = True

    def to_json(self) -> dict:
        with self._lock:
            data = {"id": self.id, "state": self.state, "done": self.done, "total": self.total,
                    "item": self.item, "cancelled": self.cancelled}
        if self.state == "done":
            if self.error is not None:
                data.update(self.error, status=self.status)
            else:
                data["result"] = self.result
        return data


class Jobs:
    """ジョブの一覧。BackEnd のアプリに 1 つ。"""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, mount: str, work, finish=None) -> Job:
        """work() を裏のスレッドで行う。終わったら（成否に関わらず）finish() を呼ぶ。"""
        job = Job(mount)
        with self._lock:
            self._prune()
            self._jobs[job.id] = job

        def run():
            current.set(job)
            try:
                job.result = work()
            except ApiError as e:
                job.error, job.status = e.to_json(), e.status
            except Exception:
                log.exception("ジョブ %s の処理で例外", job.id)
                err = ApiError("internal", "BackEnd で予期しない誤りが起きました。記録を見てください")
                job.error, job.status = err.to_json(), err.status
            finally:
                if finish is not None:
                    try:
                        finish()
                    except Exception:
                        log.exception("ジョブ %s の後始末で例外", job.id)
                job.finished = time.time()
                job.state = "done"

        # 呼んだ時点の文脈（contextvars）を写し、その上で動かす。組み込む側が contextvars で持つ値
        # （誰の操作か・操作の記録など）を、ジョブの中でも読めるようにする。bottle.request は
        # スレッドごとの値なので引き継げない（要求の情報は contextvars で渡す）
        context = contextvars.copy_context()
        threading.Thread(target=context.run, args=(run,), name=f"webfiledir-job-{job.id[:8]}", daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            self._prune()
            return self._jobs.get(job_id)

    def _prune(self) -> None:
        now = time.time()
        for jid in [j.id for j in self._jobs.values() if j.finished and now - j.finished > KEEP_SECONDS]:
            del self._jobs[jid]


# --- プロバイダのメソッドの中から使う（ジョブの外で呼ばれたら何もしない） ---
# 1 件の操作の中の段階（名前の変更でリンクを直すページ 15 枚、など）を、FrontEnd の進み具合に出し、
# 段階の境目で中止を確かめる。数える先は ops.bulk と同じなので、項目の数と段階の数が足し合わされる。

def add_total(n: int) -> None:
    """これから行う段階の数を足す。"""
    job = current.get()
    if job is not None:
        job.add_total(n)


def begin(item: str = "") -> None:
    """これから行う段階の名前（FrontEnd の「処理中」の欄に出る。パスなら最後の名前だけが出る）。"""
    job = current.get()
    if job is not None:
        job.begin(item)


def advance() -> None:
    """段階を 1 つ終えた。"""
    job = current.get()
    if job is not None:
        job.advance()


def cancelled() -> bool:
    """中止されたか。True なら、段階の境目で止まり、ApiError("cancelled", 操作者に知らせる文) を投げる
    （一括の項目の途中ならその項目の失敗、1 件の操作なら要求全体の誤りになる）。ジョブの外では常に False。"""
    job = current.get()
    return job is not None and job.cancelled
