"""添付ファイルの置き場所・配信・管理。

置き場所はページのパスをそのままミラーする（attach/<ページの実体パス>/）。
ファイル名の正規化を自前で行っているのは、bottleの FileUpload.filename が
ASCII以外を落としてしまい、日本語のファイル名が壊れるため。
"""
import datetime
import os
import posixpath
import re
import shutil
from urllib.parse import quote as urlquote

from bottle import HTTPResponse, request

from wikilib.web import static_file

from wikilib import auth, stafflog
from wikilib.accesslog import record_access
from wikilib.dbbackup import maybe_backup
from wikilib.imagesize import image_dimensions
from wikilib.diskusage import invalidate
from wikilib.paths import (
    ATTACH_URLPATH, IMAGE_EXTS, is_valid_pagepath, pagepath_of_subpath, resolve_page_ref,
    safe_join,
)

ATTACH_MAX_BYTES = 20 * 1024 * 1024  # 1ファイルあたりの上限（設定が無い場合）
# 設定に書ける大きさの単位。"20MB" のように書けるようにするためのもの。
# 1024刻みにしているのは、ファイルの大きさの見せかた（format_bytes）と揃えるため。
SIZE_UNITS = {"": 1, "B": 1, "K": 1024, "KB": 1024,
              "M": 1024 ** 2, "MB": 1024 ** 2,
              "G": 1024 ** 3, "GB": 1024 ** 3}
SIZE_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]*)\s*$")


def parse_size(value, default):
    """設定に書かれた大きさを byte 数にする。読めない書きかたなら default を返す。

    "20MB" のような書きかたと、単位なしの数（byte）の両方を受ける。
    設定を書き損じただけでサービスが止まるのは割に合わないので、
    分からない値は既定に落として動かし続ける。"""
    if value is None:
        return default
    if isinstance(value, bool):  # YAMLの true/false が数として通るのを防ぐ
        return default
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else default
    m = SIZE_RE.match(str(value))
    if not m:
        return default
    number, unit = m.group(1), m.group(2).upper()
    if unit not in SIZE_UNITS:
        return default
    size = int(float(number) * SIZE_UNITS[unit])
    return size if size > 0 else default


def attach_max_bytes(config):
    """1ファイルあたりの上限。config の attach.max_size で変えられる。

    bottle 側に上限があるわけではない（bottle の MEMFILE_MAX は、
    受け取ったデータをメモリに置くか一時ファイルに落とすかの分かれ目で、
    受け付ける大きさの上限ではない）。ここで決めているのは、
    置き場所を使い切らないための、このWiki自身の取り決めである。"""
    return parse_size((config or {}).get("attach", {}).get("max_size"),
                      ATTACH_MAX_BYTES)
# ファイル名に使えない文字。パス区切りと制御文字に加え、Windowsで予約されている記号も外す
ATTACH_BAD_CHARS_RE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')


def attach_dir_for(wiki_dir, subpath):
    """そのページの添付ファイル置き場の絶対パスを返す。置き場所の外を指す場合はNone。"""
    attach_root = os.path.join(os.path.dirname(wiki_dir), "attach")
    return safe_join(attach_root, subpath)


def has_attach_files(wiki_dir, subpath):
    """そのページに添付ファイルが1つでもあるか。

    ページの削除（editor.delete_page）と、空のフォルダを残すかどうかの判定
    （pagetree・pagesync）が使う。後者は「ページの無いフォルダに、先に添付だけ
    置いておく」使いかたを守るため、フォルダの入口（`X/index`）について聞く。"""
    directory = attach_dir_for(wiki_dir, subpath)
    if directory is None or not os.path.isdir(directory):
        return False
    return any(os.path.isfile(os.path.join(directory, n)) for n in os.listdir(directory))


CLIP_NAME_RE = re.compile(r"^clip(\d+)\.", re.IGNORECASE)


def next_clip_name(wiki_dir, subpath, ext):
    """クリップボードから貼り付けた画像に付ける名前を決める。

    そのページの添付の中から `clipNNN.拡張子` という名前を拾い、
    いちばん大きい番号の次（3桁ゼロ詰め）を返す。**欠番があっても詰めない**
    （途中の番号を消しても、次に貼り付けたものはそこを埋めずに続きから
    振る。Wiki設計者の指定）。1件も無ければ `clip001`。"""
    directory = attach_dir_for(wiki_dir, subpath)
    max_n = 0
    if directory and os.path.isdir(directory):
        for name in os.listdir(directory):
            m = CLIP_NAME_RE.match(name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return f"clip{max_n + 1:03d}{ext}"


def safe_attach_name(raw):
    """アップロードされたファイル名を、そのまま保存してよい形に整える。読めなければNone。

    bottleの FileUpload.filename はASCII以外を落としてしまうため自前で行う
    （日本語のファイル名をそのまま扱いたいため）。ディレクトリを含む名前は
    最後の要素だけを採り、パスを遡る余地を残さない。"""
    name = os.path.basename((raw or "").replace("\\", "/")).strip()
    name = ATTACH_BAD_CHARS_RE.sub("", name)
    name = name.strip(" .")  # 先頭の "." による隠しファイル化と、末尾の "." を防ぐ
    if not name or name in (".", ".."):
        return None
    return name[:255]


# 添付ファイルの種別。拡張子から判定し、一覧のアイコンと説明に使う。
# 先に並べたものが優先されるわけではなく、拡張子は重複しない前提。
ATTACH_KINDS = (
    ("image", "画像", IMAGE_EXTS),
    ("video", "動画", (".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".ogv")),
    ("audio", "音声", (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".opus")),
    ("pdf", "PDF", (".pdf",)),
    ("doc", "文書", (".doc", ".docx", ".odt", ".rtf")),
    ("sheet", "表計算", (".xls", ".xlsx", ".ods", ".csv", ".tsv")),
    ("slide", "スライド", (".ppt", ".pptx", ".odp")),
    ("archive", "圧縮", (".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar")),
    ("code", "コード", (".py", ".ipynb",
                        ".js", ".css", ".html", ".htm",
                        ".json", ".yaml", ".yml", ".xml",
                        ".sh", ".c", ".h", ".cpp",
                        ".rb", ".go", ".rs", ".sql", "pl")),
    ("text", "テキスト", (".txt", ".md", ".log", ".ini", ".conf")),
)
# 画像として扱う拡張子（サムネイル表示の対象）
ATTACH_IMAGE_EXTS = ATTACH_KINDS[0][2]


def attach_kind(name):
    """ファイル名から (種別id, 表示名) を返す。当てはまらなければ その他。"""
    ext = os.path.splitext(name)[1].lower()
    for kind, label, exts in ATTACH_KINDS:
        if ext in exts:
            return kind, label
    return "file", "ファイル"


def list_attachments(wiki_dir, subpath, base_url):
    """そのページの添付ファイル一覧を [{name, size, mtime, url, kind, ...}, ...] で返す（名前順）。

    `url` には内容バージョン `?v=<int(st_mtime * 10)>`（100ミリ秒刻み）を
    付ける。これは編集画面の添付タブ専用の対策で（この関数の呼び出し元は
    build_attach_panel_html だけ）、本文の記法や描画済みページの `<img>` には
    影響しない。

    狙いは「同じ名前で貼り直したとき、マウスオーバーのサムネイルが古いまま
    になる」不具合。clip001.png を消してクリップボードから貼り直すと
    next_clip_name がまた 001 を振るため URL が前回と一致する。配信側は
    `Cache-Control: no-cache`（wikilib.web.static_file）＋ETagで再検証できる
    ようにしてあるが、編集画面は1ページを開いたまま添付一覧をAJAXで
    差し替える作りで、同一URLの画像はブラウザのメモリ内キャッシュから
    返され、この再検証が働かない。URLにmtimeを織り込めば、貼り直したときは
    URLも変わり、確実に取り直させられる。中身（＝mtime）が同じなら `?v=` も
    不変なので通常のキャッシュはそのまま効く。

    刻みが100ミリ秒でも、貼り直しは「削除リクエスト→貼り付け→アップロード
    リクエスト」の往復と人の操作を挟むため、同名ファイルがこの間隔に
    収まって二度書かれることはない。トークンは内容ハッシュではないので、
    厳密には「mtimeが一致する別の中身」で衝突しうるが、アップロードは常に
    新しいmtimeになるためこの経路では踏まない。"""
    directory = attach_dir_for(wiki_dir, subpath)
    if directory is None or not os.path.isdir(directory):
        return []
    items = []
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        stat = os.stat(path)
        kind, kind_label = attach_kind(name)
        is_image = kind == "image"
        # 解像度はデコードせずヘッダだけ読んで求める（imagesize）ので、
        # 一覧を出すたびに毎回読んでもよい重さ。ico・avifなど対応していない
        # 形式やヘッダを読み取れなかった場合はNone（一覧側は "(未知)" を添える）
        url = "{}/{}/{}/{}".format(base_url, ATTACH_URLPATH, subpath, urlquote(name))
        url += "?v={}".format(int(stat.st_mtime * 10))
        items.append({
            "name": name,
            "size": stat.st_size,
            "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "url": url,
            "kind": kind,
            "kind_label": kind_label,
            "is_image": is_image,
            "dimensions": image_dimensions(path) if is_image else None,
        })
    return items


def format_bytes(size):
    """ファイルサイズを読みやすい単位にする。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def format_attach_size(size, dimensions, is_image):
    """添付ファイル一覧のサイズ欄の表示。画像なら、サイズの後ろに解像度を
    "(幅×高さ)" の形で添える（list_attachments の dimensions、
    image_dimensions参照）。画像なのに解像度を読み取れなかった場合
    （ico・avif、大きさの書かれていないSVGなど）は "(未知)" を添え、
    画像でなければサイズだけにする。"""
    text = format_bytes(size)
    if dimensions:
        w, h = dimensions
        text += f" ({w}×{h})"
    elif is_image:
        text += " (未知)"
    return text


def plan_attachment(wiki_dir, subpath, raw_name, size, overwrite=False, max_bytes=None):
    """置き先を決めて、置いてよいかを確かめる。(置き先, 名前, 断り文句) を返す。

    受け取りかたが2つ（1回で送られたもの・何回かに分けて送られたもの）あり、
    名前の確かめかたも置き場所も上限も同じなので、ここにまとめてある。"""
    name = safe_attach_name(raw_name or "")
    if name is None:
        return None, "", "ファイル名を読み取れませんでした。名前を変えてお試しください。"

    directory = attach_dir_for(wiki_dir, subpath)
    if directory is None:
        return None, name, "保存先を決められませんでした。"
    path = os.path.join(directory, name)
    if os.path.exists(path) and not overwrite:
        return None, name, f"「{name}」は既にあります。置き換えるには「同名を置き換える」を選んでください。"

    if size == 0:
        return None, name, "中身が空のファイルは添付できません。"
    limit = ATTACH_MAX_BYTES if max_bytes is None else max_bytes
    if size > limit:
        return None, name, f"ファイルが大きすぎます（上限 {format_bytes(limit)}）。"
    return path, name, ""


def _staff_prepare(wiki_dir, path):
    """助手の操作なら、操作の前の状態を控える。`(助手, 元のハッシュ, 控え)`。
    助手でなければ `(None, None, None)`（wikilib.stafflog）。"""
    staff = stafflog.actor(wiki_dir)
    if staff is None:
        return None, None, None
    sha = stafflog.file_sha(path)
    return staff, sha, (stafflog.stash(wiki_dir, path) if sha else None)


def _staff_put(wiki_dir, staff, subpath, name, path, old_sha, stash):
    """添付を置いた（追加・上書き）ことを記録する。"""
    if staff is None:
        return
    stafflog.record(wiki_dir, staff, "attach.put", subpath,
                    f"「{name}」を{'上書きした' if old_sha else '追加した'}",
                    before={"name": name, "sha": old_sha,
                            "blob": "before" if stash else None},
                    after={"name": name, "sha": stafflog.file_sha(path)},
                    blobs={"before": stash} if stash else None)
    stafflog.drop(stash)


def save_attachment(wiki_dir, subpath, upload, overwrite=False, max_bytes=None):
    """アップロードされたファイルを保存する。(成否, 知らせる文言) を返す。"""
    # 上限の判定は、書き出す前にシークして実際の長さを見る（Content-Lengthは信用しない）
    upload.file.seek(0, os.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(0)
    path, name, refused = plan_attachment(
        wiki_dir, subpath, getattr(upload, "raw_filename", "") or "",
        size, overwrite, max_bytes)
    if refused:
        return False, refused

    staff, old_sha, stash = _staff_prepare(wiki_dir, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    upload.save(path, overwrite=True)
    invalidate(wiki_dir)
    _staff_put(wiki_dir, staff, subpath, name, path, old_sha, stash)
    return True, f"「{name}」を添付しました。"


def adopt_attachment(wiki_dir, subpath, src_path, raw_name,
                     overwrite=False, max_bytes=None):
    """何回かに分けて受け取り終えたファイルを、添付として置く。

    中身はもう出来上がっているので、読み直さずに移す。"""
    try:
        size = os.path.getsize(src_path)
    except OSError:
        return False, "受け取ったものが見つかりませんでした。"
    path, name, refused = plan_attachment(
        wiki_dir, subpath, raw_name, size, overwrite, max_bytes)
    if refused:
        return False, refused

    staff, old_sha, stash = _staff_prepare(wiki_dir, path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.move(src_path, path)
    except OSError:
        stafflog.drop(stash)
        return False, f"「{name}」を置けませんでした。"
    invalidate(wiki_dir)
    _staff_put(wiki_dir, staff, subpath, name, path, old_sha, stash)
    return True, f"「{name}」を添付しました。"


def delete_attachment(wiki_dir, subpath, raw_name):
    """添付ファイルを1つ削除する。(成否, 知らせる文言) を返す。"""
    name = safe_attach_name(raw_name)
    if name is None:
        return False, "削除するファイルを指定してください。"
    directory = attach_dir_for(wiki_dir, subpath)
    if directory is None:
        return False, "削除するファイルを指定してください。"
    path = os.path.join(directory, name)
    # 実体がそのページの添付置き場の直下にあることを確かめてから消す
    if os.path.realpath(os.path.dirname(path)) != os.path.realpath(directory):
        return False, "削除するファイルを指定してください。"
    if not os.path.isfile(path):
        return False, f"「{name}」は見つかりませんでした。"
    staff, old_sha, stash = _staff_prepare(wiki_dir, path)
    try:
        os.remove(path)
    except OSError:
        stafflog.drop(stash)
        return False, f"「{name}」を削除できませんでした。"
    invalidate(wiki_dir)
    if staff is not None:
        stafflog.record(wiki_dir, staff, "attach.delete", subpath, f"「{name}」を削除した",
                        before={"name": name, "sha": old_sha,
                                "blob": "before" if stash else None},
                        after=None, blobs={"before": stash} if stash else None)
        stafflog.drop(stash)
    return True, f"「{name}」を削除しました。"


def rename_attachment(wiki_dir, subpath, raw_name, new_raw_name, overwrite=False):
    """添付ファイルの名前を変える（置き場所は同じページのまま）。
    (成否, 知らせる文言) を返す。

    「添付ページの変更」（move_attachment）が置き場所（どのページの
    添付か）を変えるのに対して、こちらは同じ場所のまま名前だけを変える。"""
    name = safe_attach_name(raw_name)
    if name is None:
        return False, "名前を変えるファイルを指定してください。"
    new_name = safe_attach_name(new_raw_name)
    if new_name is None:
        return False, "新しい名前を入力してください。"
    if new_name == name:
        return False, "名前が変わっていません。"

    directory = attach_dir_for(wiki_dir, subpath)
    if directory is None:
        return False, "名前を変えるファイルを指定してください。"

    src = os.path.join(directory, name)
    if not os.path.isfile(src):
        return False, f"「{name}」は見つかりませんでした。"
    dst = os.path.join(directory, new_name)
    if os.path.exists(dst) and not overwrite:
        return False, (f"「{new_name}」は既にあります。"
                       "置き換えるには「同名を置き換える」を選んでください。")

    staff, dst_sha, stash = _staff_prepare(wiki_dir, dst)
    try:
        os.replace(src, dst)
    except OSError:
        stafflog.drop(stash)
        return False, f"「{name}」の名前を変えられませんでした。"
    invalidate(wiki_dir)
    if staff is not None:
        # 同じ名前を置き換えたときは、置き換えられたほうも控える
        stafflog.record(wiki_dir, staff, "attach.rename", subpath,
                        f"「{name}」を「{new_name}」に変えた",
                        before={"subpath": subpath, "name": name, "dst_sha": dst_sha,
                                "blob": "replaced" if stash else None},
                        after={"subpath": subpath, "name": new_name,
                               "sha": stafflog.file_sha(dst)},
                        blobs={"replaced": stash} if stash else None)
        stafflog.drop(stash)
    return True, f"「{name}」を「{new_name}」に変えました。"


def move_attachment(wiki_dir, subpath, raw_name, dest_pagepath, overwrite=False):
    """添付ファイルを別のページへ移す（＝所属先ページの変更）。
    (成否, 知らせる文言) を返す。名前だけを変えたい場合は rename_attachment。

    移動先は「ページパス」で受け取り、実体の置き場所は resolve_page_ref に決めさせる。
    "/Tech" のようなフォルダ相当のページでも attach/Tech/index/ に正しく移すため。"""
    name = safe_attach_name(raw_name)
    if name is None:
        return False, "移動するファイルを指定してください。"
    if dest_pagepath is None or not is_valid_pagepath(dest_pagepath):
        return False, "移動先のページを選んでください。"

    ref = resolve_page_ref(wiki_dir, dest_pagepath)
    if ref is None:
        return False, "移動先のページを選んでください。"
    if ref.subpath == subpath:
        return False, "移動先が今のページと同じです。"

    src_dir = attach_dir_for(wiki_dir, subpath)
    dst_dir = attach_dir_for(wiki_dir, ref.subpath)
    if src_dir is None or dst_dir is None:
        return False, "移動先を決められませんでした。"

    src = os.path.join(src_dir, name)
    if not os.path.isfile(src):
        return False, f"「{name}」は見つかりませんでした。"
    dst = os.path.join(dst_dir, name)
    if os.path.exists(dst) and not overwrite:
        return False, (f"移動先に「{name}」が既にあります。"
                       "置き換えるには「同名を置き換える」を選んでください。")

    staff, dst_sha, stash = _staff_prepare(wiki_dir, dst)
    os.makedirs(dst_dir, exist_ok=True)
    try:
        os.replace(src, dst)  # 同じディスク内なので中身の複製は起きない
    except OSError:
        stafflog.drop(stash)
        return False, f"「{name}」を移動できませんでした。"
    if staff is not None:
        stafflog.record(wiki_dir, staff, "attach.move", subpath,
                        f"「{name}」を /{ref.pagepath} へ移した",
                        before={"subpath": subpath, "name": name, "dst_sha": dst_sha,
                                "blob": "replaced" if stash else None},
                        after={"subpath": ref.subpath, "name": name,
                               "sha": stafflog.file_sha(dst)},
                        blobs={"replaced": stash} if stash else None)
        stafflog.drop(stash)

    where = "/" + ref.pagepath if ref.pagepath else "/"
    note = "" if ref.exists else "（移動先のページはまだありません）"
    invalidate(wiki_dir)
    return True, f"「{name}」を {where} へ移動しました。{note}"

def attach_viewable(wiki_dir, farm, relpath):
    """その添付ファイルを、いまの閲覧者が読んでよいか。

    **添付の持ち主のページの閲覧権限に従う**（Wiki設計者の指示、2026-09-14）。
    置き場所はページのパスをそのままミラーしているので、`relpath` の
    ディレクトリ部分が持ち主のページになる（`Tech/index/logo.png` はフォルダの
    入口なので `Tech`。`paths.pagepath_of_subpath`）。

    `a/../b` のような書きかたで別のページの添付を指されても取り違えないよう、
    **先にパスを正規化してから**ページ名を取り出す。ファイルシステムには触らない。"""
    normalized = posixpath.normpath("/" + (relpath or "")).lstrip("/")
    owner = pagepath_of_subpath(posixpath.dirname(normalized))
    privilege = auth.page_privilege(wiki_dir, auth.current_uid(wiki_dir, farm))
    return privilege.check(owner) != auth.PAGE_NONE


def attach_not_found():
    """添付ファイルを返せないときの応答。**ファイルが無いときも、閲覧の権限が
    無いときも、これ1つ**（Wiki設計者の指示、2026-09-14。「ファイル無しと閲覧権限が
    かかった場合とは同じ表示が望ましい」）。

    以前はファイルが無いときだけテーマ付きの画面（旧 `views.render_no_attach`）を
    出し、持ち主のページや添付タブへ案内していた。しかし権限で止めた側と見た目が
    違うと、**見比べるだけでそのページに制限がかかっていると分かってしまう**。
    案内を残したまま揃えることはできない（案内の有無で見分けがつく）ので、
    どちらもテキストの404に揃えた。この判断に賛成で、ページに貼った画像が欠けて
    いるたびにテーマを描かずに済むという利点もある。"""
    return HTTPResponse(body="File not found", status=404,
                        content_type="text/plain; charset=utf-8")


def serve_attach(wiki_dir, config, farm, relpath, explicit_farm):
    """添付ファイルを配信する。置き場所はページのパスをそのままミラーする
    （例: ページ "data/file" の添付は attach/data/file/img.zip、"index.md" 自体の
    添付は attach/index/logo.png）。全Wiki共通の置き場所は無い（添付はページに属するため）。

    **返せないときは、理由を問わず `attach_not_found`**（404 `File not found`）。
    閲覧の権限が無ければ、ファイルを探しにも行かない。"""
    if not attach_viewable(wiki_dir, farm, relpath):
        return attach_not_found()

    attach_dir = os.path.join(os.path.dirname(wiki_dir), "attach")
    real_target = safe_join(attach_dir, relpath)
    if real_target is None or not os.path.isfile(real_target):
        return attach_not_found()
    directory, filename = os.path.split(real_target)
    response = static_file(filename, root=directory)
    # 304（ブラウザ側キャッシュの再検証。実際には転送していない）はログの
    # 対象外にする。これを含めると、同じ画像を貼ったページを開き直すたびに
    # 「新規アクセス」が積み重なってしまうため（本文はrender_page側にキャッシュの
    # 仕組みが無いため常に200だが、添付ファイルはETag/Last-Modifiedで304を返せる）。
    if response.status_code == 200:
        record_access(wiki_dir, request.path, request.remote_addr,
                      request.headers.get("User-Agent"))
        # DBの控えが前日以前なら取り直す（views.render_page と同じ）
        maybe_backup(wiki_dir)
    return response
