"""見本のコマンド — BackEnd で機能を作る例。標準では出さず、設定の [[mount]] の samples に書いたマウントにだけ出す。

既定のコマンド（server/builtin.py）と同じ形（宣言と処理）で作ってあり、Wiki「サーバ側実装例」が解説する。

| id | 何をするか |
|---|---|
| duplicate | 選んだファイルを、名前の先頭に _ を付けて同じフォルダに写す（複製） |
| trim | 拡張子の手前を、半角スペースで分けた最初の部分にする（トリミング） |
| touch | 更新日時を今の時刻にする（プロバイダのメソッド update_mtime） |
| numbering | 入力した開始値から、名前の先頭に「001.」のような通し番号を付ける（見出し連番） |
| timer | 状態表示のダイアログとプログレスバーの出力例（10秒タイマー） |
"""

import math
import re
import time
import uuid

from . import jobs, ops, vpath
from .commands import Command, Message, Modal
from .errors import ApiError
from .exts import stem_of

CONFLICT = {"exists": {"part": "chooseConflict"}}  # 名前の衝突は「上書き・スキップ・両方残す」を尋ねる
REPORT_AND_SELECT = ({"do": "report", "done": "@done", "fail": "@fail"}, {"do": "reload", "select": "$done.names"})


def sample_commands(capabilities, readonly: bool, samples) -> list[Command]:
    """samples（設定に書いた見本の id）のうち、このマウントで使えるものの宣言。"""
    rw = set() if readonly else set(capabilities)
    out = []
    if "duplicate" in samples and "copy" in rw:
        out.append(Command("duplicate", "複製", places=("item",), group="clipboard", order=14, job=True,
                           when={"kinds": ["file"], "select": "some", "items": {"auth": "read"},
                                 "dir": {"auth": "write"}},
                           then=REPORT_AND_SELECT, on_item_error=CONFLICT,
                           texts={"done": "複製しました", "fail": "複製でき"}))
    if "trim" in samples and "rename" in rw:
        out.append(Command("trim", "トリミング", places=("item",), group="edit", order=31, job=True,
                           when={"kinds": ["file"], "select": "some", "items": {"auth": "move", "partial": True}},
                           then=REPORT_AND_SELECT, on_item_error=CONFLICT,
                           texts={"done": "トリミングしました", "fail": "トリミングでき"}))
    if "touch" in samples and "update_mtime" in rw:
        out.append(Command("touch", "touch", places=("item",), group="edit", order=32, job=True,
                           when={"select": "some", "items": {"auth": "write", "partial": True}},
                           then=REPORT_AND_SELECT,
                           texts={"done": "更新日時を現在時刻にしました", "fail": "更新日時を変えられ"}))
    if "numbering" in samples and "rename" in rw:
        # 番号は送られてきた paths の順（FrontEnd の今の並べ替えの順）に振る
        out.append(Command(
            "numbering", "見出し連番", places=("item",), group="edit", order=33,
            when={"kinds": ["file"], "select": "some", "items": {"auth": "move", "partial": True}},
            input={"part": "prompt", "title": "@promptTitle", "label": "@promptLabel", "value": "001",
                   "detail": "@promptDetail"},
            # 開始値の誤りは BackEnd が確かめ、入力に戻す（誤りの理由はフォームの中に出る）
            on_error={"bad_input": [{"do": "retryInput"}]},
            then=REPORT_AND_SELECT,
            texts={"promptTitle": "見出し連番", "promptLabel": "開始値",
                   "promptDetail": "今の並び順に、名前の先頭へ「番号.」を付けます。桁数は開始値の桁数（01 なら 2 桁、"
                                   "001 なら 3 桁）。先頭に元からある「数字.」は付け替えます。",
                   "done": "番号を付けました", "fail": "番号を付けられ"}))
    if "timer" in samples:
        # 状態表示のダイアログ（はい・いいえ → OK）とプログレスバーの出力例
        out.append(Command("timer", "10秒タイマー", places=("background",), group="new", order=12, job=True))
    return out


# --- 処理 ---
# env は server/app.py が渡すもの（server/builtin.py の処理と同じ）

DUPLICATE_PREFIX = "_"


def _duplicate(ctx, env) -> dict:
    p = env.writable(ctx.mount, "copy").provider
    on_conflict = ctx.answers.get("onConflict", "error")
    return ops.bulk([vpath.join(x) for x in ctx.paths],
                    lambda s: ops.duplicate_one(p, s, DUPLICATE_PREFIX + vpath.split(s)[-1], on_conflict))


def trimmed_name(name: str, ext: str) -> str:
    """拡張子（項目の ext）の手前を name.split(" ")[0] にした名前（拡張子は変えない）。
    空白で始まる名前は最初の部分が空になるので、"" を返す（拡張子だけの名前は作らない）。"""
    stem = stem_of(name, ext)
    ext = name[len(stem) + 1:] if stem != name else ""
    head = stem.split(" ")[0]
    if not head:
        return ""
    return f"{head}.{ext}" if ext else head


def _trim(ctx, env) -> dict:
    p = env.writable(ctx.mount, "rename").provider
    on_conflict = ctx.answers.get("onConflict", "error")

    def one(s):
        parts = vpath.split(s)
        # 拡張子は項目の ext（プロバイダが決めたもの）に従う
        new_name = trimmed_name(parts[-1], p.stat(parts).to_json()["ext"]) if parts else ""
        if not new_name:
            raise ApiError("bad_name", "空白で始まる名前はトリミングできません", s)
        return ops.rename_one(p, s, new_name, on_conflict)

    return ops.bulk([vpath.join(x) for x in ctx.paths], one)


def _touch(ctx, env) -> dict:
    p = env.writable(ctx.mount, "update_mtime").provider
    return ops.bulk([vpath.join(x) for x in ctx.paths],
                    lambda s: {"entry": p.update_mtime(vpath.split(s)).to_json()})


NUMBER_PREFIX = re.compile(r"[0-9]+\.")


def numbered_names(names: list[str], start: str) -> list[str]:
    """names の順に、start（数字の文字列）からの番号を「番号.」で先頭に付けた名前。桁数は start の文字数
    （足りなければ 0 で埋め、超えたらそのまま桁が増える）。先頭の「数字.」は取り除いてから付ける。"""
    width, n = len(start), int(start)
    return [f"{n + i:0{width}d}." + NUMBER_PREFIX.sub("", name, count=1) for i, name in enumerate(names)]


def _numbering(ctx, env) -> dict:
    start = ctx.input or ""
    if not re.fullmatch(r"[0-9]+", start):
        raise ApiError("bad_input", "開始値は半角の数字で入力してください（例: 001）")
    p = env.writable(ctx.mount, "rename").provider
    srcs = list(ctx.paths)
    targets = numbered_names([s[-1] for s in srcs], start)
    selected = {s[-1] for s in srcs}
    results: list[dict | None] = [None] * len(srcs)

    def ok(i, entry, **extra):
        results[i] = {"src": vpath.join(srcs[i]), "ok": True, "entry": entry.to_json(), **extra}

    def fail(i, e: ApiError):
        results[i] = {"src": vpath.join(srcs[i]), "ok": False, **e.to_json()}

    # 選んだもの同士で名前が入れ替わる（並べ替えてから振り直すと 02.x と 01.x が入れ替わる）ことがあるので、
    # いったん仮の名前にしてから最終の名前にする。選んでいない項目と重なるものは、その項目だけ失敗にする
    # （1 件だけ送り直すと番号の並びが崩れるので、上書き・両方残すは尋ねない）
    moving = []
    for i, (src, target) in enumerate(zip(srcs, targets)):
        try:
            if src[-1] == target:
                ok(i, p.stat(src), unchanged=True)
            elif target not in selected and p.exists(src[:-1] + (target,)):
                raise ApiError("exists", f"「{target}」という名前の項目は既にあります", vpath.join(src[:-1] + (target,)))
            else:
                moving.append(i)
        except ApiError as e:
            fail(i, e)
    temporary = {}
    for i in moving:
        try:
            name = f".webfiledir-numbering-{uuid.uuid4().hex[:12]}"
            p.rename(srcs[i], name)
            temporary[i] = srcs[i][:-1] + (name,)
        except ApiError as e:
            fail(i, e)
    for i, tmp in temporary.items():
        try:
            ok(i, p.rename(tmp, targets[i]))
        except ApiError as e:
            try:
                p.rename(tmp, srcs[i][-1])  # 元の名前に戻す
            except ApiError:
                e = ApiError(e.code, f"{e.message}（仮の名前 {tmp[-1]} のまま残っています）", e.path)
            fail(i, e)
    return {"results": results}


TIMER_SECONDS = 10.0  # 10秒タイマーの長さ（テストでは短くする）
TIMER_STEPS = 100     # プログレスバーを進める回数（1 回 1%）


def _timer(ctx, env) -> dict:
    """はい・いいえで確かめ、はいならジョブとして TIMER_SECONDS かけて 100% まで進め、OK のダイアログで終える。"""
    answer = ctx.answers.get("timer")
    if answer is None:
        return {"effects": [Modal("10秒タイマー", "タイマーを開始して良いですか？", type="yesno", answer="timer")]}
    if answer != "yes":
        return {"effects": []}
    job = jobs.current.get()
    step = TIMER_SECONDS / TIMER_STEPS
    if job is not None:
        job.add_total(TIMER_STEPS)
    for i in range(TIMER_STEPS):
        if job is not None:
            if job.cancelled:
                return {"effects": [Message("タイマーを中止しました")]}
            job.begin(f"残り {math.ceil(TIMER_SECONDS - i * step)} 秒")
        time.sleep(step)
        if job is not None:
            job.advance()
    return {"effects": [Modal("10秒タイマー", "カウント完了しました")]}


SAMPLE_HANDLERS = {
    "duplicate": _duplicate,
    "trim": _trim,
    "touch": _touch,
    "numbering": _numbering,
    "timer": _timer,
}
