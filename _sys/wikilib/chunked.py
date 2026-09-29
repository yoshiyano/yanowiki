"""大きなものを何回かに分けて受け取る。

1回のPOSTで送れる大きさには上限がある（bottle は受け取ったものを一度メモリに
置くため、そこに制限を設けている）。**上限を上げて済ませるのではなく、送る側で
切って何回かに分ける。** 上限を上げると、1回のPOSTで確保されるメモリがそのまま
増え、同時に複数のファイルを送ったときの合計にも効いてしまうため。

送る側は `chunk_id`（そのひとまとまりを表す名前）と `chunk_index`（何番目か）、
`chunk_total`（全部で何個か）を添えて、`part` に中身の切れ端を入れて送る。
こちらは切れ端を順に継ぎ足し、全部そろった時点で1つのファイルにして返す。

継ぎ足しの途中は wikidata/<Wiki名>/pageinfo/upload/ に置く。
"""
import json
import os
import re
import time

from bottle import request

from wikilib.paths import farm_pageinfo_dir

# 分けて送るときの1回ぶんの大きさ。送る側もこの値を使う（画面へ配っている）。
# 1回のPOSTがこの程度なら、同時にいくつか進んでいても受け取り側の負担は小さい
CHUNK_BYTES = 1024 * 1024

# 継ぎ足しの途中を、いつまで置いておくか。送っている最中に閉じられた場合など、
# 完成しないまま残るものがあるため
CHUNK_KEEP_SECONDS = 3600

# 送る側が付ける名前。パスを組み立てるのに使うので、英数字だけに限る
CHUNK_ID_RE = re.compile(r"^[A-Za-z0-9]{8,64}$")


def chunk_root_of(wiki_dir):
    return farm_pageinfo_dir(wiki_dir, "upload")


def _paths_of(wiki_dir, chunk_id):
    root = chunk_root_of(wiki_dir)
    return (os.path.join(root, chunk_id + ".part"),
            os.path.join(root, chunk_id + ".meta"))


def is_chunked():
    """分けて送られてきたPOSTかどうか。"""
    return bool(request.forms.getunicode("chunk_id"))


def sweep_old(wiki_dir, now=None):
    """完成しないまま置かれている継ぎ足しの跡を片づける。消した数を返す。"""
    root = chunk_root_of(wiki_dir)
    now = now or time.time()
    removed = 0
    try:
        entries = os.listdir(root)
    except OSError:
        return 0
    for name in entries:
        if not name.endswith((".part", ".meta")):
            continue
        path = os.path.join(root, name)
        try:
            if now - os.path.getmtime(path) < CHUNK_KEEP_SECONDS:
                continue
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed


def take_chunk(wiki_dir, field="part", max_bytes=None):
    """切れ端を1つ受け取る。(状態, 出来上がったパス, 断り文句) を返す。

    状態は次の3つ。

    "more"
        受け取ったが、まだ続きがある。呼び出し側は204で返して次を待つ。
    "done"
        全部そろった。2つめの戻り値が、継ぎ足し終えたファイルのパス。
        **中身を読んだら呼び出し側が消す**（finish_chunk を使う）。
    "error"
        受け取れなかった。3つめの戻り値が理由。

    番号が飛んだ場合は受け取らない。順に継ぎ足すだけの作りなので、抜けたまま
    進むと**壊れたものを完成として渡してしまう**ため。"""
    chunk_id = request.forms.getunicode("chunk_id", "")
    if not CHUNK_ID_RE.match(chunk_id or ""):
        return "error", None, "送信の名前が正しくありません。"
    try:
        index = int(request.forms.getunicode("chunk_index", ""))
        total = int(request.forms.getunicode("chunk_total", ""))
    except ValueError:
        return "error", None, "送信の番号が正しくありません。"
    if total < 1 or not 0 <= index < total:
        return "error", None, "送信の番号が範囲の外です。"

    upload = request.files.get(field)
    if upload is None:
        return "error", None, "送るものが入っていませんでした。"

    root = chunk_root_of(wiki_dir)
    part_path, meta_path = _paths_of(wiki_dir, chunk_id)
    try:
        os.makedirs(root, exist_ok=True)
    except OSError:
        return "error", None, "受け取る場所を用意できませんでした。"

    if index == 0:
        sweep_old(wiki_dir)  # 新しく始めるついでに、古い跡を片づける
        meta = {"next": 0, "total": total,
                "name": request.forms.getunicode("chunk_name", "")}
    else:
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            # ここまで継ぎ足したものは、もう続きを繋げられない。置いておいても
            # 使い道が無いので、この場で片づける（送る側は名前を取り直して初めから）
            _remove(part_path, meta_path)
            return "error", None, "送信の途中が失われました。もう一度お試しください。"
        if meta.get("next") != index or meta.get("total") != total:
            _remove(part_path, meta_path)
            return "error", None, "送信の順番が入れ替わりました。もう一度お試しください。"

    try:
        with open(part_path, "wb" if index == 0 else "ab") as f:
            upload.file.seek(0)
            while True:
                block = upload.file.read(CHUNK_BYTES)
                if not block:
                    break
                f.write(block)
        size = os.path.getsize(part_path)
    except OSError:
        _remove(part_path, meta_path)
        return "error", None, "受け取りに失敗しました。"

    if max_bytes is not None and size > max_bytes:
        # 途中で超えた時点でやめる。最後まで受け取ってから断ると、その間ずっと
        # 置き場所を使い続けることになる
        _remove(part_path, meta_path)
        return "error", None, "大きすぎます。"

    meta["next"] = index + 1
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
    except OSError:
        _remove(part_path, meta_path)
        return "error", None, "受け取りに失敗しました。"

    if meta["next"] < total:
        return "more", None, ""
    return "done", part_path, ""


def chunk_name(wiki_dir, chunk_id):
    """そのひとまとまりに添えられていた名前（添付ならファイル名）を返す。"""
    _part, meta_path = _paths_of(wiki_dir, chunk_id)
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f).get("name", "")
    except (OSError, ValueError):
        return ""


def finish_chunk(wiki_dir, chunk_id):
    """継ぎ足し終えたものを片づける。中身を読んだあとに呼ぶ。"""
    _remove(*_paths_of(wiki_dir, chunk_id))


def _remove(*paths):
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass
