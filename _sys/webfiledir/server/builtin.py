"""既定のコマンド — マウントの capabilities から自動で宣言するものと、そのサーバ側の処理。

一覧と振る舞いは Wiki「コマンドの宣言 > 既定のコマンド」を正とする。0.2.2 の画面の操作と同じ振る舞いにする。
処理の中身はプロバイダのメソッド（rename・trash・move など）で、ここはそれを組み合わせるだけ
（ファイル以外の構造では、何が起きるかはプロバイダが決め、見せかたは設定で変える）。
"""

import io
from dataclasses import replace
from datetime import datetime

from . import ops, vpath
from .commands import AUTH_BITS, Browse, Command, Modal, Navigate
from .config import SAMPLE_COMMANDS
from .errors import ApiError
from .samples import SAMPLE_HANDLERS, sample_commands

CONFLICT = {"exists": {"part": "chooseConflict"}}
PURGE_CONFIRM = {"title": "@confirmTitle", "message": "@confirmMessage", "detail": "@confirmDetail",
                 "okLabel": "@okLabel", "danger": True}
PURGE_TEXTS = {"confirmTitle": "完全に削除", "confirmMessage": "$items.labelを完全に削除しますか？",
               "confirmDetail": "この操作は元に戻せません。フォルダは中身ごと消えます。", "okLabel": "削除する",
               "done": "完全に削除しました", "fail": "削除でき"}
TRASH_TEXTS = {"done": "ごみ箱へ移しました", "fail": "ごみ箱へ移せ", "undo": "元に戻す"}
MAX_EDIT_SIZE = 1024 * 1024  # テキストの編集で開ける・保存できる大きさ（UTF-8 のバイト数）
# 保存に失敗したら、編集した中身を失わないよう、理由を出して編集画面に戻る
EDIT_RETRY = [{"do": "retryInput"}]


def _report(*extra) -> tuple:
    return ({"do": "report", "done": "@done", "fail": "@fail"}, {"do": "reload"}, *extra)


UNDO = {"do": "offer", "label": "@undo", "run": "restore", "items": "$done.trashIds"}


def builtin_commands(capabilities, readonly: bool, samples=()) -> list[Command]:
    """capabilities（プロバイダが持つ操作）と読み取り専用かどうかから、既定のコマンドの宣言を作る。
    読み取り専用なら、変更のコマンドは宣言しない（開く・コピー元にすることは残す）。"""
    caps = set(capabilities)
    rw = set() if readonly else caps
    out = []
    if "stream" in caps:
        out += [
            Command("view", "ブラウザで表示", places=("item",), group="open", order=10, open="default",
                    when={"kinds": ["file"], "select": "one", "items": {"auth": "read"}, "reachable": True}),
            Command("download", "ダウンロード", places=("item",), group="open", order=11, open="shift",
                    when={"kinds": ["file"], "select": "one", "items": {"auth": "read"}, "reachable": True}),
        ]
    # 選んだ項目の情報を、状態表示のダイアログ（OK の型）で見せる
    out.append(Command("properties", "プロパティ", places=("item",), group="props", order=10,
                       when={"select": "one"}))
    out += [
        Command("tab", "新しいタブで開く", places=("item",), group="open", order=20, open="shift",
                when={"kinds": ["dir"], "select": "one", "items": {"auth": "exec"}, "reachable": True}),
        Command("pane", "隣の画面で開く", places=("item",), group="open", order=21,
                when={"kinds": ["dir"], "select": "one", "items": {"auth": "exec"}, "reachable": True}),
    ]
    for cap, cid, label, icon, key, order in (("mkdir", "new-folder", "新しいフォルダ", "new-folder", "Ctrl+Shift+N", 10),
                                              ("touch", "new-file", "新しいテキスト ドキュメント", "new-file", None, 11)):
        if cap in rw:
            out.append(Command(cid, label, icon=icon, places=("background", "toolbar"), group="new", order=order,
                               key=key, when={"dir": {"auth": "write"}},
                               then=({"do": "reload", "select": ["$result.name"], "edit": "$result.name"},)))
    if "stream" in caps and "replace" in rw:
        # テキストの簡易編集: 中身を読んで（GET raw）ダイアログで編集させ、全体を input で送って置き換える
        out.append(Command(
            "edit-text", "テキストを編集", places=("item",), group="open", order=12,
            when={"kinds": ["file"], "select": "one", "items": {"auth": "write"}, "reachable": True},
            input={"part": "textEdit", "title": "$item.name", "maxSize": MAX_EDIT_SIZE},
            then=({"do": "message", "text": "@done"}, {"do": "reload", "select": ["$result.name"]}),
            on_error={code: EDIT_RETRY for code in ("too_large", "forbidden", "not_found", "unsupported",
                                                     "bad_request", "bad_path", "internal", "network")},
            texts={"done": "「$item.name」を保存しました"}))
    if "stream" in rw:
        # アップロード: ブラウザの手元のファイル・フォルダを、1 ファイルずつ POST commands/<id>/upload で送る。
        # ダイアログで選ぶもの（右クリックメニュー・ツールバー）と、ほかのアプリからのドロップ（確かめずに送る）
        upload_texts = {"done": "アップロードしました", "fail": "アップロードでき"}
        out += [
            Command("upload", "アップロード", icon="upload", places=("background", "toolbar"), group="new", order=20,
                    when={"dest": {"auth": "write"}}, input={"part": "uploadDialog", "title": "アップロード"},
                    request="upload",
                    then=({"do": "report", "done": "@done", "fail": "@fail"},
                          {"do": "reload", "select": "$done.names"}),
                    on_item_error=CONFLICT, texts=upload_texts),
            Command("drop-upload", "ここにアップロード", group="drop", order=13,
                    drop=({"from": "files", "target": "folder"},), when={"dest": {"auth": "write"}},
                    request="upload", then=_report(), on_item_error=CONFLICT, texts=upload_texts),
        ]
    if "rename" in rw:
        out.append(Command(
            "rename", "名前の変更", icon="rename", places=("item", "toolbar"), group="edit", order=30, key="F2",
            when={"select": "one", "items": {"auth": "move"}},
            input={"part": "inlineEdit", "value": "$item.name", "select": "stem"},
            then=({"do": "reload", "select": ["$result.name"]},),
            on_error={"exists": [{"do": "message", "kind": "error", "text": "@exists"}, {"do": "retryInput"}],
                      "bad_name": [{"do": "message", "kind": "error", "text": "@badName"}, {"do": "retryInput"}]},
            texts={"exists": "「$input」という名前の項目は既にあります",
                   "badName": "名前に / は使えません。空・「.」・「..」も使えません"}))
    # 切り取り・コピーはサーバに尋ねない（2026-09-29 設計者決定、C6）。貼り付け・ドロップのときに送る
    if "move" in rw or ("stream" in rw and "delete" in rw):
        out.append(Command("cut", "切り取り", icon="cut", places=("item", "toolbar"), group="clipboard", order=10,
                           key="Ctrl+X", when={"select": "some", "items": {"auth": "move", "partial": True}},
                           request=None, then=({"do": "clipboard", "mode": "cut"},)))
    if "copy" in caps or "stream" in caps:
        out.append(Command("copy", "コピー", icon="copy", places=("item", "toolbar"), group="clipboard", order=11,
                           key="Ctrl+C", when={"select": "some", "items": {"auth": "read"}},
                           request=None, then=({"do": "clipboard", "mode": "copy"},)))
    if rw & {"copy", "move", "stream"}:
        paste_texts = {"done": "貼り付けました", "fail": "貼り付けられ"}
        out += [
            Command("paste", "貼り付け", icon="paste", places=("background", "toolbar"), group="clipboard",
                    order=12, key="Ctrl+V", when={"clipboard": True, "dest": {"auth": "write"}},
                    # 今いるフォルダへ貼り付けたので、貼り付けたものを選ぶ（エクスプローラーと同じ。0.x と同じ）
                    then=({"do": "report", "done": "@done", "fail": "@fail"},
                          {"do": "reload", "select": "$done.names"}),
                    on_item_error=CONFLICT, texts=paste_texts),
            Command("paste-into", "このフォルダに貼り付け", places=("item",), group="clipboard", order=13,
                    when={"kinds": ["dir"], "select": "one", "clipboard": True, "dest": {"auth": "write"},
                          "reachable": True},
                    then=_report(), on_item_error=CONFLICT, texts=paste_texts),
        ]
    if "trash" in rw:
        out.append(Command("delete", "削除", icon="delete", places=("item", "toolbar"), group="delete", order=10,
                           key="Delete", when={"select": "some", "items": {"auth": "move", "partial": True}},
                           then=_report(UNDO), texts=TRASH_TEXTS))
    elif "delete" in rw:
        # ごみ箱の無いマウントの削除は完全に削除（確認あり。0.x と同じ）
        out.append(Command("delete", "削除", icon="delete", places=("item", "toolbar"), group="delete", order=10,
                           key="Delete", when={"select": "some", "items": {"auth": "move", "partial": True}},
                           confirm=None if "before_delete" in rw else PURGE_CONFIRM, then=_report(),
                           texts=PURGE_TEXTS))
    if "delete" in rw:
        # ごみ箱の無いマウントでは「削除」と同じ動きなので、メニューには出さずキーだけ残す（0.2.3 と同じ）
        out.append(Command("purge", "完全に削除", places=("item",) if "trash" in rw else (), group="delete",
                           order=11, key="Shift+Delete",
                           when={"select": "some", "items": {"auth": "move", "partial": True}},
                           confirm=None if "before_delete" in rw else PURGE_CONFIRM, then=_report(),
                           texts=PURGE_TEXTS))
    if "move" in rw or "stream" in rw:
        out.append(Command("drop-move", "ここに移動", group="drop", order=10,
                           drop=({"target": "folder", "mounts": "same", "modifier": None},
                                 {"target": "folder", "mounts": "any", "modifier": "shift"}),
                           when={"dest": {"auth": "write"}, "items": {"auth": "move", "partial": True}},
                           then=_report(), on_item_error=CONFLICT, texts={"done": "移動しました", "fail": "移動でき"}))
    if "copy" in rw or "stream" in rw:
        out.append(Command("drop-copy", "ここにコピー", group="drop", order=11,
                           drop=({"target": "folder", "mounts": "other", "modifier": None},
                                 {"target": "folder", "mounts": "any", "modifier": "ctrl"}),
                           when={"dest": {"auth": "write"}, "items": {"auth": "read"}},
                           then=_report(), on_item_error=CONFLICT, texts={"done": "コピーしました", "fail": "コピーでき"}))
    if "trash" in rw:
        out += [
            Command("drop-trash", "ごみ箱へ移す", group="drop", order=12,
                    drop=({"target": "trash", "mounts": "same", "modifier": None},),
                    when={"items": {"auth": "move", "partial": True}}, then=_report(UNDO), texts=TRASH_TEXTS),
            Command("restore", "元に戻す", icon="restore", places=("item", "toolbar"), group="trash", order=10,
                    when={"view": "trash", "select": "some"}, then=_report(), on_item_error=CONFLICT,
                    texts={"done": "元に戻しました", "fail": "戻せ"}),
            Command("trash-purge", "完全に削除", icon="delete", places=("item", "toolbar"), group="trash",
                    order=11, key="Delete", when={"view": "trash", "select": "some"},
                    confirm=PURGE_CONFIRM, then=_report(),
                    texts={**PURGE_TEXTS, "confirmMessage": "$items.labelをごみ箱から完全に削除しますか？",
                           "confirmDetail": "この操作は元に戻せません。"}),
            Command("trash-empty", "ごみ箱を空にする", icon="trash", places=("background", "toolbar"),
                    group="trash", order=12, when={"view": "trash"},
                    confirm=PURGE_CONFIRM, then=_report(),
                    texts={**PURGE_TEXTS, "confirmTitle": "ごみ箱を空にする",
                           "confirmMessage": "ごみ箱の項目をすべて完全に削除しますか？",
                           "confirmDetail": "この操作は元に戻せません。", "okLabel": "空にする"}),
        ]
    # 項目をまとめて扱うコマンドは、BackEnd が裏で行い（ジョブ）、FrontEnd が進み具合を見せる
    out = [replace(c, job=True) if c.id in JOB_COMMANDS else c for c in out]
    # 見本のコマンド（server/samples.py）は、設定の samples に書いたマウントにだけ足す
    return out + sample_commands(capabilities, readonly, samples)


# ジョブとして行う既定のコマンド（項目の数・大きさによって時間がかかりうるもの）
JOB_COMMANDS = frozenset({"paste", "paste-into", "drop-move", "drop-copy", "drop-trash", "delete", "purge",
                          "restore", "trash-purge", "trash-empty"})


BUILTIN_IDS = frozenset(c.id for c in builtin_commands(
    {"mkdir", "touch", "rename", "delete", "copy", "move", "stream", "trash", "update_mtime", "replace"}, False,
    SAMPLE_COMMANDS)
    + builtin_commands({"delete"}, False))


# --- サーバ側の処理 ---
# env は server/app.py が渡すもの: mount(mid) … 使える（読める）マウント、writable(mid, capability) … 変えてよい
# マウント、touched(mid) … 変えたマウントを覚える（自動更新の知らせ）、raw_url(mid, path, mode) … 中身の URL

def _one(ctx):
    return ctx.paths[0]


def _source_mode(ctx) -> str:
    return "move" if ctx.source["mode"] == "cut" else "copy"


def _transfer(ctx, env, mode: str) -> dict:
    """貼り付け・ドロップ: source の項目を dest へ写す・移す。マウントをまたげば元を読んで先に書く。"""
    src = ctx.source
    texts = [vpath.join(p) for p in src["paths"]]
    if mode == "move":
        # 移すときは、項目それぞれの「動かす」を確かめ、無い項目だけ失敗にする（貼り付けの宣言の when は
        # コピーと共通なので「動かす」を書けない。ドロップの移動は when で確かめ済み）
        source_provider = env.mount(src["mount"]).provider
        denied, kept = [], []
        for t in texts:
            try:
                ok = source_provider.stat(vpath.split(t)).auth & AUTH_BITS["move"]
            except ApiError:
                ok = True  # 無いなどは、写すときにその項目の失敗になる
            if ok:
                kept.append(t)
            else:
                denied.append({"src": t, "ok": False,
                               **ApiError("forbidden", "動かす権限がありません", t).to_json()})
        res = _transfer_texts(ctx, env, mode, kept) if kept else {"results": []}
        res["results"] = res["results"] + denied
        return res
    return _transfer_texts(ctx, env, mode, texts)


def _transfer_texts(ctx, env, mode: str, texts: list[str]) -> dict:
    src, dest = ctx.source, ctx.dest
    on_conflict = ctx.answers.get("onConflict", "error")
    if src["mount"] == dest["mount"]:
        p = env.writable(dest["mount"], mode).provider
        return ops.bulk(texts, lambda s: ops.transfer_one(p, mode, s, dest["path"], on_conflict))
    # マウントをまたぐ: 元は読めること（移動なら消せること）、先は書けること。どちらも中身を読み書きできること
    source = env.writable(src["mount"], "delete") if mode == "move" else env.mount(src["mount"])
    if "stream" not in source.provider.capabilities:
        raise ApiError("unsupported", "このマウントからは、ほかのマウントへ写せません")
    target = env.writable(dest["mount"], "stream")
    return ops.bulk(texts, lambda s: ops.transfer_across(source.provider, target.provider, mode, s, dest["path"],
                                                         on_conflict))


def _delete(ctx, env, permanent: bool) -> dict:
    m = env.writable(ctx.mount, "delete" if permanent else "trash")
    p = m.provider
    texts = [vpath.join(x) for x in ctx.paths]
    if permanent:
        return ops.bulk(texts, lambda s: p.delete(vpath.split(s)))
    return ops.bulk(texts, lambda s: {"trashId": p.trash(vpath.split(s)).id})


def _open_stream(ctx, env, mode: str) -> dict:
    m = env.mount(ctx.mount)
    path = _one(ctx)
    # 中身を読めるかをここで確かめる（権限が無いなど）。確かめずに URL を返すと、画面は新しいタブを
    # 開き、そのタブに誤りの JSON が出る（2026-09-29、mode 000 のファイルで起きた）
    with m.provider.open_read(path):
        pass
    if mode == "view":
        return {"effects": [Navigate(env.raw_url(ctx.mount, path), "_blank")]}
    # 保存として返すので、この画面から移ってもページは変わらない
    return {"effects": [Navigate(env.raw_url(ctx.mount, path, "download"), "_self")]}


def _create(ctx, env, kind: str) -> dict:
    m = env.writable(ctx.mount, "mkdir" if kind == "dir" else "touch")
    return {"result": ops.create(m.provider, ctx.dir, ctx.input, kind).to_json()}


def _rename(ctx, env) -> dict:
    m = env.writable(ctx.mount, "rename")
    path = _one(ctx)
    if not path:
        raise ApiError("bad_path", "マウントの根は名前を変えられません", "/")
    return {"result": m.provider.rename(path, vpath.check_name(ctx.input)).to_json()}


AUTH_NAMES = (("move", "動かす"), ("read", "読む"), ("write", "書く"), ("exec", "実行"))


def size_text(n: int) -> str:
    """「1.2 MB（1,234,567 バイト）」。"""
    if n < 1024:
        return f"{n:,} バイト"
    value, unit = float(n), "B"
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024
        if value < 1024:
            break
    return f"{value:.1f} {unit}（{n:,} バイト）"


def _edit_text(ctx, env) -> dict:
    m = env.writable(ctx.mount, "replace")
    path = _one(ctx)
    if ctx.input is None:
        raise ApiError("bad_request", "保存する中身（input）がありません")
    data = ctx.input.encode("utf-8")
    if len(data) > MAX_EDIT_SIZE:
        raise ApiError("too_large", f"大きすぎて保存できません（上限は {size_text(MAX_EDIT_SIZE)}）", vpath.join(path))
    if m.provider.stat(path).kind != "file":
        raise ApiError("bad_path", "フォルダは編集できません", vpath.join(path))
    return {"result": m.provider.replace_file(path, io.BytesIO(data)).to_json()}


def _properties(ctx, env) -> dict:
    m = env.mount(ctx.mount)
    path = _one(ctx)
    e = m.provider.stat(path)
    j = e.to_json()
    rows = [("場所", f"{m.config.label}: {vpath.join(path[:-1]) if path else '/'}"),
            ("種類", "フォルダ" if e.kind == "dir" else (f"ファイル（{j['ext']}）" if j["ext"] else "ファイル"))]
    if e.size is not None:
        rows.append(("サイズ", size_text(e.size)))
    if e.mtime is not None:
        rows.append(("更新日時", datetime.fromtimestamp(e.mtime).strftime("%Y-%m-%d %H:%M:%S")))
    rows.append(("権限", "・".join(name for key, name in AUTH_NAMES if e.auth & AUTH_BITS[key]) or "なし"))
    return {"effects": [Modal(e.name or "/", rows=rows)]}


def _paste(ctx, env) -> dict:
    res = _transfer(ctx, env, _source_mode(ctx))
    if ctx.source["mode"] == "cut":
        # 切り取ったものは、貼り付けたらクリップボードから外す（0.x と同じ）
        res["effects"] = [{"do": "clipboardClear"}]
    return res


def _restore(ctx, env) -> dict:
    p = env.writable(ctx.mount, "trash").provider
    on_conflict = ctx.answers.get("onConflict", "error")
    return ops.bulk(ctx.ids, lambda i: ops.restore_one(p, i, on_conflict), key="id")


def _trash_purge(ctx, env) -> dict:
    p = env.writable(ctx.mount, "trash").provider
    return ops.bulk(ctx.ids, p.purge, key="id")


def _trash_empty(ctx, env) -> dict:
    p = env.writable(ctx.mount, "trash").provider
    return ops.bulk([i.id for i in p.list_trash()], p.purge, key="id")


def _browse(target: str):
    def handler(ctx, env):
        return {"effects": [Browse(ctx.mount, vpath.join(_one(ctx)), target)]}
    return handler


def _drop_trash(ctx, env) -> dict:
    """ツリーのごみ箱へのドロップ。運んできた項目（source）を、同じマウントのごみ箱へ移す。"""
    if ctx.source["mount"] != ctx.mount:
        raise ApiError("unsupported", "ほかのマウントのごみ箱へは移せません")
    ctx.paths = list(ctx.source["paths"])
    return _delete(ctx, env, False)


def _delete_default(ctx, env) -> dict:
    # ごみ箱の無いマウントの「削除」は完全に削除（宣言も確認付きにしてある）
    return _delete(ctx, env, "trash" not in env.mount(ctx.mount).provider.capabilities)


HANDLERS = {
    "view": lambda ctx, env: _open_stream(ctx, env, "view"),
    "download": lambda ctx, env: _open_stream(ctx, env, "download"),
    "tab": _browse("_blank"),
    "pane": _browse("other"),
    "new-folder": lambda ctx, env: _create(ctx, env, "dir"),
    "new-file": lambda ctx, env: _create(ctx, env, "file"),
    "properties": _properties,
    "edit-text": _edit_text,
    "rename": _rename,
    "paste": _paste,
    "paste-into": _paste,
    "delete": _delete_default,
    "purge": lambda ctx, env: _delete(ctx, env, True),
    "drop-move": lambda ctx, env: _transfer(ctx, env, "move"),
    "drop-copy": lambda ctx, env: _transfer(ctx, env, "copy"),
    "drop-trash": _drop_trash,
    "restore": _restore,
    "trash-purge": _trash_purge,
    "trash-empty": _trash_empty,
    **SAMPLE_HANDLERS,
}
# 貼り付け・ドロップは source（クリップボードかドラッグの元）と dest（移す先）が要る
USES_SOURCE = frozenset({"paste", "paste-into", "drop-move", "drop-copy", "drop-trash"})
