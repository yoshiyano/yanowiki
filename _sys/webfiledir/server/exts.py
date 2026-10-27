"""拡張子の既定の規則。拡張子を決めるのはサーバだけで、項目の JSON の ext に載せる（画面は切り出さない）。

プロバイダは Entry.ext に値を入れれば、項目ごとに拡張子を決められる（入れなければこの規則）。
"""

# 最後の "." だけでは表せない拡張子。まとめて 1 つの拡張子にする（2026-09-30 設計者の指示）
COMPOUND_EXTS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst")


def split_ext(name: str) -> tuple[str, str]:
    """拡張子の手前と拡張子（"." を含まない）。
    - COMPOUND_EXTS で終わる名前は、それをまとめて拡張子にする（大文字・小文字は区別せず当て、綴りは元のまま）
    - それ以外は最後の "." で分ける。先頭の "."（いくつ続いても）は区切りと見なさず、末尾の "." のあとが空なら拡張子なし
    - 手前が空か "." だけになる名前（".tar.gz" そのもの）には、複合拡張子を当てない"""
    lower = name.lower()
    for suffix in COMPOUND_EXTS:
        if lower.endswith(suffix) and name[:-len(suffix)].lstrip("."):
            return name[:-len(suffix)], name[-len(suffix) + 1:]
    lead = len(name) - len(name.lstrip("."))
    i = name.rfind(".")
    if i < lead or i == len(name) - 1:
        return name, ""
    return name[:i], name[i + 1:]


def default_ext(name: str, kind: str) -> str:
    """項目の既定の拡張子。フォルダは拡張子を持たない。"""
    return "" if kind == "dir" else split_ext(name)[1]


def stem_of(name: str, ext: str) -> str:
    """ext（項目の拡張子）の手前。ext が空か、名前が ".ext" で終わらなければ名前そのもの。"""
    if ext and name.lower().endswith("." + ext.lower()) and len(name) > len(ext) + 1:
        return name[:-(len(ext) + 1)]
    return name
