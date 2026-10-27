"""テーマのファイル（`/.admin/themes/`）。webFileDir を組み込み、テーマのファイルを
エクスプローラーの形で扱う。**そのWikiの管理者と助手**が開ける（下の「開ける人と記録」）。

Wiki設計者の指示（2026-10-03）: 「ファイル一覧の機能でテーマファイルも編集できるように」
「本体の theme ファイルは readonly として、個別の theme は read/write として２つのフォルダを
一括して見れるように、/shared/ と /sitetheme/ でそれぞれを閲覧でき、shared からコピーが
しやすい状態に」。shared は、設計者の「shared ではなく common のほうが良いか？」を受けて
common にした（テンプレートで共通のテーマを指す名前 `common/`（`THEME_COMMON_PREFIX`）と揃う）。

    /common/      全Wiki共通のテーマ（`theme/`。wikiThemes の持ち物）。読み取り専用
    /sitetheme/   そのWiki固有のテーマ（`wikidata/<Wiki>/theme/`）。読み書きできる
    /slotcommon/  全Wiki共通のスロット型のテーマ（`slottheme/`）。読み取り専用
    /slottheme/   そのWiki固有のスロット型のテーマ（`wikidata/<Wiki>/slottheme/`）。読み書きできる

スロット型の2つは、Wiki設計者の「ツリーには４つ並べる」（2026-10-04）で足した（スロット型の
テーマは `wikilib.slottheme`）。マウントの id・並び順はクロコの実装例。

1つの webFileDir のアプリに4つのマウントとして持つ。マウントの id が、そのまま画面の
ツリーの最上位とアドレス（`#/common/…`）になる。common から sitetheme へは、webFileDir の
既定のコピー（Ctrl+C → 貼り付け、ドラッグ）もマウントをまたいで使える。

## sitetheme へコピー

設計者の「shared から sitetheme へのコピー機能が欲しい」（2026-10-03）。common の項目の右クリックと
ツールバーに、独自のコマンド「sitetheme へコピー」（`COPY_COMMAND`）を出す。

以下はクロコの実装例（設計者は未確認）:

- 写し先は sitetheme の**同じ場所**（`common/foo/x.css` → `sitetheme/foo/x.css`）。テーマは
  個別Wiki固有の同じ名前が優先されるので、写せばそのまま差し替わる。途中のフォルダは作る
- フォルダは、sitetheme に同じフォルダがあれば中身を混ぜる（webFileDir の上書きはファイル同士だけ）
- 同じ名前のファイルがあれば、はい・いいえで「上書きしますか」と尋ねる。はいなら上書きし、
  置き換えられたほうは sitetheme のごみ箱へ（webFileDir の上書きと同じ）。いいえなら、それを
  飛ばして残りを写す
- 写したら、sitetheme のその場所を開いて見せる

sitetheme にはアップロード（ツールバー・右クリックの「アップロード」、ほかのアプリからのドロップ）と、
テキストの簡易編集（右クリックの「テキストを編集」。UTF-8・1 MiB まで）が出る。どちらも webFileDir が、
書き込めて `stream`（編集は加えて `replace`）を持つマウントに自動で宣言する（1.1.0 に向けて dev に
入ったもの）。common は読み取り専用なので出ない。

## slottheme で書けるもの

スロット型のテーマ（`.html`）と CSS・画像・フォント（`SLOT_EXTS`）だけ。テキストの編集は `.html`・
`.css`。`.html`・`.css` は、どの経路（アップロード・貼り付け・「slottheme へコピー」・編集・名前の
変更）で入るときも、`slottheme.check`・`slottheme.check_css` で取り除かれるものがあれば、理由を付けて
断る（Wiki設計者が「断る」を選んだ、2026-10-05）。描くとき・配るときにも取り除くので、安全はそちらで
守られる。保存時に断るのは、フォルダの中を「書いたとおりに描かれる」状態に保つため。

以下はクロコの実装例（設計者は未確認）:

- ほかの拡張子のファイルは置けない（名前の変更・新規作成でも）。新しいファイル（webFileDir の既定の
  名前「新しいテキスト ドキュメント.txt」）は、拡張子を `.css` にして作る
- ごみ箱は `pageinfo/slottheme-trash`

## sitetheme で書けるもの

Jinja2 が読む場所（sitetheme）に、画面からコードを入れさせない（Wiki設計者の指示、2026-10-03）:
「css と画像ファイルに制限して upload やファイルを編集する権限をもたせます」「html については
コピー権限までは与えても編集権限は与えません。リネームにより html から他のファイルにすることは
認めても、他のファイルから html など jinja2 がコード解釈する拡張子に変更することは不許可」。

    アップロード      CSS と画像だけ（`UPLOAD_EXTS`）
    テキストの編集    CSS だけ（`EDIT_EXTS`）。ほかのファイルは項目の「書く」を落として、
                      メニューにも出さない（ファイルの「書く」を見るのは edit-text だけ）
    名前の変更・新規作成   ほかの拡張子から `CODE_EXTS` へは変えられない。同じ拡張子どうし
                      （html → html）と、`CODE_EXTS` からほかへは変えられる
    コピー           どれも写せる（common から・sitetheme の中で。中身は元のファイルのまま）

決まりは管理者にも効かせる（クロコの案を設計者が承認、2026-10-04）。

今のコードで Jinja2 がテーマの置き場所から読むのは `.html` で終わる名前だけ（`themefile + ".html"`・
継承先。検索結果の `search.html` は `_sys/search/` にあり、テーマの置き場所からは読まない）。以下はクロコの実装例（設計者は未確認）:

- `CODE_EXTS` には、閲覧者のブラウザでスクリプトとして動く `.js`・`.svg` も入れる。`/.theme/` は
  sitetheme のファイルを共通のものより先に配るので、書いた CSS を `base.js` へ変えられると、
  全閲覧者のブラウザで動く。`.htm`・`.j2` などのテンプレートの拡張子も、先回りして入れる
- アップロードの画像に `.svg` は入れない（直接開くとスクリプトが動く）
- アップロードは、要求の中で「アップロード中」の印を立て（`_uploading`）、`write_file` がそれを
  見て断る。`write_file` は common からの貼り付けでも呼ばれるので、印の無い書き込み（コピー）は
  通す。置けるかを先に確かめる要求（`check=1`。`write_file` を呼ばない）は、受け取った時点で断る

## 開ける人と記録

Wiki設計者の「権限は各wikiの 助手まで。記録は残します」（2026-10-04）。

    管理者   4つすべて
    助手     common（読み取り専用。「sitetheme へコピー」は出さない）・slotcommon・slottheme。
             Jinja2 の sitetheme は見せない（`mount_access`）

**ここまでは助手に与える権限の既定**。管理者は `/.admin/staffperms` で、助手ごとに
slottheme の編集（`themes.slot`）を外す、sitetheme を見せる（`themes.site.view`）・
編集させる（`themes.site.edit`）ことができる（`wikilib.staffperms`。前提は
`themes.view`）。

助手の slottheme での操作は「助手の操作の記録」（`wikilib.stafflog`。kind は `theme.*`）に残す
（管理者の操作は記録しない。stafflog の決まり）。

以下はクロコの実装例（設計者は未確認）:

- 助手に sitetheme を見せないのは、Jinja2 が読む場所だから（sitetheme の決まりで画面からはコードを
  入れられないが、管理者の領分として分ける）。common は参考と CSS の写し元として見せる
- 記録だけを残し、「元に戻す」は付けない。消したものはごみ箱から戻せ、編集は前の中身を控えとして残す
- 誰が操作しているかは、要求の中で決めて文脈に持つ（`_viewer`）。webFileDir はジョブへ文脈を写すので、
  裏で行う削除・貼り付けでも同じ人として記録できる

以下もクロコの実装例（設計者は未確認）:

- ごみ箱は、テーマのフォルダの外（`pageinfo/theme-trash`）に置く。`/.theme/` は「.」で始まる
  名前も配信するので、既定の置き場所（根の直下の `.fdweb-trash`）だと消したファイルが届いてしまう
- 自動更新（開いたままの接続）は使わない（ファイル一覧と同じ）
- アップロードの1ファイルの上限は、添付と同じ `attach.max_size`（`attach.attach_max_bytes`）。
  アプリを作るときに読むので、設定を変えたら再起動まで前の値のまま
"""
import contextvars
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import parse_qs

from bottle import HTTPResponse, request

from wikilib import auth, slottheme, staffperms, stafflog, sysui
from wikilib.attach import attach_max_bytes
from wikilib.filesui import _is_supported, _webfiledir, call_app, screen_html
from wikilib.paths import (
    SLOTTHEME_DIR, THEME_DIR, THEMEFILES_URLPATH, farm_pageinfo_dir, farm_slottheme_dir,
)
from wikilib.themes import theme_dirs

COMMON_MOUNT = "common"        # 全Wiki共通のテーマ（読み取り専用）
SITE_MOUNT = "sitetheme"       # そのWiki固有のテーマ（読み書き）
TRASH_DIRNAME = "theme-trash"  # sitetheme のごみ箱（pageinfo/ の下）
SLOT_COMMON_MOUNT = "slotcommon"   # 全Wiki共通のスロット型のテーマ（読み取り専用）
SLOT_SITE_MOUNT = "slottheme"       # そのWiki固有のスロット型のテーマ（読み書き）
SLOT_TRASH_DIRNAME = "slottheme-trash"
COPY_COMMAND = "copy-to-site"  # common の項目を sitetheme の同じ場所へ写す（モジュール冒頭）
SLOT_COPY_COMMAND = "copy-to-slottheme"   # slotcommon の項目を slottheme の同じ場所へ写す
OVERWRITE_ANSWER = "overwrite"  # 上書きを尋ねるダイアログの答えの名前

# sitetheme で書けるもの（モジュール冒頭「sitetheme で書けるもの」）
UPLOAD_EXTS = frozenset({".css", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico"})
EDIT_EXTS = frozenset({".css"})
CODE_EXTS = frozenset({".html", ".htm", ".xhtml", ".j2", ".jinja", ".jinja2",
                       ".js", ".mjs", ".svg", ".svgz", ".xml"})
# slottheme で書けるもの（モジュール冒頭「slottheme で書けるもの」）
SLOT_EXTS = frozenset({".html"}) | slottheme.ASSET_EXTS
SLOT_EDIT_EXTS = frozenset({".html", ".css"})
SLOT_NEW_FILE_EXT = ".css"
UPLOAD_PATH_RE = re.compile(r"^/api/v1/commands/[^/]+/upload$")
_uploading = contextvars.ContextVar("themefiles_uploading", default=False)
# いまの要求の人: (持っている権限の集合, 記録する助手のアカウント または None)。
# モジュール冒頭「開ける人と記録」。権限は `wikilib.staffperms`（管理者は全部）
_viewer = contextvars.ContextVar("themefiles_viewer", default=(frozenset(), None))


def file_ext(name):
    """拡張子（小文字）。末尾の空白・「.」は落として見る（`x.html.` も `.html` として扱う）。"""
    return os.path.splitext((name or "").rstrip(" ."))[1].lower()


def _upload_ext_text(exts=UPLOAD_EXTS):
    return "・".join(sorted(e[1:] for e in exts))


def content_problems(name, data):
    """slottheme の `.html`・`.css` の中身で、描くときに取り除かれるもの（それ以外は空）。"""
    ext = file_ext(name)
    if ext not in SLOT_EDIT_EXTS:
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ["UTF-8 として読めません"]
    return slottheme.check(text) if ext == ".html" else slottheme.check_css(text)


def problems_text(problems):
    shown = "／".join(problems[:3])
    more = f" ほか {len(problems) - 3} 件" if len(problems) > 3 else ""
    return f"描くときに取り除かれるものがあるので保存しません: {shown}{more}"

_lock = threading.Lock()
_apps = {}   # wiki_dir → webFileDir のアプリ


def site_theme_dir(wiki_dir):
    """そのWiki固有のテーマの置き場所（テーマの探索で最初に見る場所）。"""
    return theme_dirs(wiki_dir)[0]


def _make_site_provider_class(wfd):
    providers = wfd["providers"]
    ApiError = wfd["errors"].ApiError

    def check_code_name(old, new, path):
        to = file_ext(new)
        if to in CODE_EXTS and to != file_ext(old):
            raise ApiError("forbidden", f"ほかの種類のファイルを {to} には変えられません", path)

    class SiteThemeProvider(providers.LocalProvider):
        """そのWiki固有のテーマ。書けるものを拡張子で絞る（モジュール冒頭「sitetheme で書けるもの」）。"""

        @staticmethod
        def _auth(real, is_dir, place):
            auth = providers.LocalProvider._auth(real, is_dir, place)
            if not is_dir and file_ext(real) not in EDIT_EXTS:
                auth &= ~2   # 「書く」を落とす（テキストの編集を出さない）
            return auth

        def rename(self, path, new_name):
            check_code_name(path[-1] if path else "", new_name, "/" + "/".join(path))
            return super().rename(path, new_name)

        def create_file(self, parent, name):
            check_code_name("", name, "/" + "/".join(tuple(parent) + (name,)))
            return super().create_file(parent, name)

        def copy(self, src, dest_dir, new_name=None):
            if new_name is not None:
                check_code_name(src[-1], new_name, "/" + "/".join(src))
            return super().copy(src, dest_dir, new_name)

        def move(self, src, dest_dir, new_name=None):
            if new_name is not None:
                check_code_name(src[-1], new_name, "/" + "/".join(src))
            return super().move(src, dest_dir, new_name)

        def replace_file(self, path, stream):
            if file_ext(path[-1] if path else "") not in EDIT_EXTS:
                raise ApiError("forbidden", "中身を編集できるのは CSS だけです", "/" + "/".join(path))
            return super().replace_file(path, stream)

        def write_file(self, parent, name, stream, mtime=None):
            if _uploading.get() and file_ext(name) not in UPLOAD_EXTS:
                raise ApiError("forbidden",
                               f"アップロードできるのは CSS と画像（{_upload_ext_text()}）だけです",
                               "/" + "/".join(tuple(parent) + (name,)))
            return super().write_file(parent, name, stream, mtime)

    return SiteThemeProvider


def _make_slot_provider_class(wfd, wiki_dir):
    import io
    import tempfile
    providers = wfd["providers"]
    ops = wfd["ops"]
    ApiError = wfd["errors"].ApiError

    def shown(parts):
        return "/" + "/".join(parts)

    def log(kind, target, summary, before=None):
        """助手の操作なら記録する（before は控える中身のバイト列）。"""
        user = _viewer.get()[1]
        if user is None:
            return
        blob = None
        try:
            if before is not None:
                fd, blob = tempfile.mkstemp(prefix="theme-", dir=None)
                with os.fdopen(fd, "wb") as f:
                    f.write(before)
            stafflog.record(wiki_dir, user, kind, "slottheme" + target, summary,
                            blobs={"before": blob} if blob else None)
        finally:
            stafflog.drop(blob)

    def check_ext(name, path):
        if file_ext(name) not in SLOT_EXTS:
            raise ApiError("forbidden", "slottheme に置けるのは HTML・CSS・画像・フォント"
                           f"（{_upload_ext_text(SLOT_EXTS)}）だけです", path)

    def check_data(name, data, path):
        problems = content_problems(name, data)
        if problems:
            raise ApiError("bad_request", problems_text(problems), path)

    class SlotThemeProvider(providers.LocalProvider):
        """そのWiki固有のスロット型のテーマ（モジュール冒頭「slottheme で書けるもの」）。"""

        @staticmethod
        def _auth(real, is_dir, place):
            auth = providers.LocalProvider._auth(real, is_dir, place)
            if not is_dir and file_ext(real) not in SLOT_EDIT_EXTS:
                auth &= ~2   # 「書く」を落とす（テキストの編集を出さない）
            return auth

        def _read(self, path):
            with self.open_read(path) as f:
                return f.read()

        def rename(self, path, new_name):
            if path and self.stat(path).kind == "file":
                check_ext(new_name, shown(path))
                if file_ext(new_name) != file_ext(path[-1]):
                    check_data(new_name, self._read(path), shown(path))
            entry = super().rename(path, new_name)
            log("theme.rename", shown(path), f"名前の変更: {path[-1]} → {new_name}")
            return entry

        def create_file(self, parent, name):
            if file_ext(name) not in SLOT_EXTS:
                stem = os.path.splitext(name)[0] or "新しいファイル"
                name = ops.free_name(self, tuple(parent), stem + SLOT_NEW_FILE_EXT, False)
            entry = super().create_file(parent, name)
            log("theme.put", shown(tuple(parent) + (entry.name,)), "新しいファイル")
            return entry

        def mkdir(self, parent, name):
            entry = super().mkdir(parent, name)
            log("theme.put", shown(tuple(parent) + (entry.name,)), "新しいフォルダ")
            return entry

        def copy(self, src, dest_dir, new_name=None):
            if new_name is not None and self.stat(src).kind == "file":
                check_ext(new_name, shown(src))
            entry = super().copy(src, dest_dir, new_name)
            log("theme.put", shown(tuple(dest_dir) + (entry.name,)), f"コピー: {shown(src)} から")
            return entry

        def move(self, src, dest_dir, new_name=None):
            if new_name is not None and self.stat(src).kind == "file":
                check_ext(new_name, shown(src))
            entry = super().move(src, dest_dir, new_name)
            log("theme.rename", shown(src), f"移動: {shown(tuple(dest_dir) + (entry.name,))} へ")
            return entry

        def replace_file(self, path, stream):
            if file_ext(path[-1] if path else "") not in SLOT_EDIT_EXTS:
                raise ApiError("forbidden", "中身を編集できるのは HTML と CSS だけです", shown(path))
            data = stream.read()
            check_data(path[-1], data, shown(path))
            before = self._read(path) if _viewer.get()[1] is not None else None
            entry = super().replace_file(path, io.BytesIO(data))
            log("theme.edit", shown(path), "テキストの編集（前の中身を控えた）", before)
            return entry

        def write_file(self, parent, name, stream, mtime=None):
            # アップロードも、ほかのマウントからの貼り付けも、ここを通る
            where = shown(tuple(parent) + (name,))
            check_ext(name, where)
            if file_ext(name) in SLOT_EDIT_EXTS:
                data = stream.read()
                check_data(name, data, where)
                stream = io.BytesIO(data)
            entry = super().write_file(parent, name, stream, mtime)
            log("theme.put", shown(tuple(parent) + (entry.name,)),
                "アップロード" if _uploading.get() else "ほかのフォルダからコピー")
            return entry

        def delete(self, path):
            result = super().delete(path)
            log("theme.delete", shown(path), "完全に削除")
            return result

        def trash(self, path):
            item = super().trash(path)
            log("theme.delete", shown(path), "ごみ箱へ移した")
            return item

        def restore(self, trash_id, new_name=None):
            entry = super().restore(trash_id, new_name)
            log("theme.restore", "/" + entry.name, "ごみ箱から戻した")
            return entry

        def purge(self, trash_id):
            result = super().purge(trash_id)
            log("theme.delete", "", f"ごみ箱から完全に削除（{trash_id}）")
            return result

    return SlotThemeProvider


def _make_copy_source_class(wfd, command_id, target_mount):
    """読み取り専用の共通のテーマ。項目を target_mount の同じ場所へ写すコマンドを持つ。"""
    providers = wfd["providers"]
    ops = wfd["ops"]
    ApiError = wfd["errors"].ApiError

    class CommonThemeProvider(providers.LocalProvider):
        """全Wiki共通のテーマ。読み取り専用のマウントで見せ、項目を写し先へ写すコマンドを持つ。"""

        commands = (
            providers.Command(command_id, f"{target_mount} へコピー", icon="paste",
                              places=("item", "toolbar"), group="clipboard", order=15,
                              when={"select": "some", "items": {"auth": "read"}}),
        )

        def __init__(self, root, site):
            super().__init__(root)
            self.site = site   # 写し先（写し先のマウントと同じフォルダ・同じごみ箱のプロバイダ）

        def run_command(self, cid, ctx):
            if cid != command_id:
                return super().run_command(cid, ctx)
            if not ctx.paths:
                raise ApiError("bad_request", "コピーするものを選んでください")
            files, dirs = [], []   # (common のパス, 写し先のフォルダ)・写すフォルダ（空のものも作る）
            for path in ctx.paths:
                self._collect(tuple(path), files, dirs)
            conflicts = [src for src, dest in files if self.site.exists(dest + (src[-1],))]
            answer = ctx.answers.get(OVERWRITE_ANSWER)
            if conflicts and answer is None:
                names = "、".join("/".join(src) for src in conflicts[:5])
                more = f" ほか {len(conflicts) - 5} 件" if len(conflicts) > 5 else ""
                return [providers.Modal(
                    f"{target_mount} へコピー",
                    f"{target_mount} に同じ名前のファイルがあります（{names}{more}）。上書きしますか？"
                    f"（上書きされたファイルは {target_mount} のごみ箱へ移ります。いいえなら、それを"
                    "飛ばして残りをコピーします）",
                    type="yesno", answer=OVERWRITE_ANSWER, default="no")]
            on_conflict = "overwrite" if answer == "yes" else "skip"
            copied = skipped = 0
            for path in dirs:
                self._make_dirs(path)
            for src, dest in files:
                self._make_dirs(dest)
                res = ops.transfer_across(self, self.site, "copy", "/" + "/".join(src), dest,
                                          on_conflict)
                if res.get("skipped"):
                    skipped += 1
                else:
                    copied += 1
            parent = tuple(ctx.paths[0])[:-1]
            text = f"{target_mount} へ {copied} 件コピーしました" + (
                f"（{skipped} 件は飛ばしました）" if skipped else "")
            return [providers.Browse(target_mount, "/" + "/".join(parent)),
                    providers.Message(text, "info")]

        def _collect(self, path, files, dirs):
            if self.stat(path).kind == "dir":
                dirs.append(path)
                for entry in self.listdir(path):
                    self._collect(path + (entry.name,), files, dirs)
            else:
                files.append((path, path[:-1]))

        def _make_dirs(self, path):
            for i in range(1, len(path) + 1):
                if not self.site.exists(path[:i]):
                    self.site.mkdir(path[:i - 1], path[i - 1])
                elif self.site.stat(path[:i]).kind != "dir":
                    raise ApiError("exists", f"{target_mount} に同じ名前のファイルがあり、フォルダを作れません",
                                   "/" + "/".join(path[:i]))

    return CommonThemeProvider


def _app_for(wiki_dir, config, farm):
    with _lock:
        app = _apps.get(wiki_dir)
        if app is not None:
            return app
        wfd = _webfiledir()
        if wfd is None or not _is_supported(wfd):
            return None
        site_dir = site_theme_dir(wiki_dir)
        slot_dir = farm_slottheme_dir(wiki_dir)
        for d in (site_dir, slot_dir, SLOTTHEME_DIR, farm_pageinfo_dir(wiki_dir)):
            os.makedirs(d, exist_ok=True)
        cfg = wfd["config"]
        trash = Path(farm_pageinfo_dir(wiki_dir, TRASH_DIRNAME))
        slot_trash = Path(farm_pageinfo_dir(wiki_dir, SLOT_TRASH_DIRNAME))
        wfd_config = cfg.Config(
            server=cfg.ServerConfig(max_upload_size=attach_max_bytes(config)),
            mounts=(
                cfg.MountConfig(id=COMMON_MOUNT, type="commontheme", root=Path(THEME_DIR),
                                readonly=True, label="common（全Wiki共通・読み取り専用）"),
                cfg.MountConfig(id=SITE_MOUNT, type="sitetheme", root=Path(site_dir), trash=trash,
                                label=f"sitetheme（{farm} 固有）"),
                cfg.MountConfig(id=SLOT_COMMON_MOUNT, type="slotcommon", root=Path(SLOTTHEME_DIR),
                                readonly=True, label="slotcommon（スロット型・全Wiki共通・読み取り専用）"),
                cfg.MountConfig(id=SLOT_SITE_MOUNT, type="slottheme", root=Path(slot_dir),
                                trash=slot_trash, label=f"slottheme（スロット型・{farm} 固有）"),
            ))
        common_class = _make_copy_source_class(wfd, COPY_COMMAND, SITE_MOUNT)
        slot_common_class = _make_copy_source_class(wfd, SLOT_COPY_COMMAND, SLOT_SITE_MOUNT)
        site_class = _make_site_provider_class(wfd)
        slot_class = _make_slot_provider_class(wfd, wiki_dir)
        site = site_class(site_dir, trash)
        slot = slot_class(slot_dir, slot_trash)
        app = wfd["app"].create_app(
            wfd_config,
            mount_access=_mount_access,
            live_updates=False,
            providers={"commontheme": lambda m: common_class(m.root, site),
                       "sitetheme": lambda m: site_class(m.root, m.trash),
                       "slotcommon": lambda m: slot_common_class(m.root, slot),
                       "slottheme": lambda m: slot_class(m.root, m.trash)})
        _apps[wiki_dir] = app
        return app


def _mount_access(req, mid):
    """マウントごとの許し（モジュール冒頭「開ける人と記録」）。人は要求の中で決めた `_viewer`。

    sitetheme は `themes.site.view`（見る）・`themes.site.edit`（編集）、slottheme の編集は
    `themes.slot`。common から sitetheme へ写す操作は sitetheme の編集と同じ扱い、
    slotcommon から slottheme へ写す操作は slottheme の編集と同じ扱い。"""
    held = _viewer.get()[0]
    if mid == COMMON_MOUNT:
        return "ro" if "themes.site.edit" in held else {"access": "ro", "disable": [COPY_COMMAND]}
    if mid == SLOT_COMMON_MOUNT:
        return "ro" if "themes.slot" in held else {"access": "ro",
                                                    "disable": [SLOT_COPY_COMMAND]}
    if mid == SITE_MOUNT:
        if "themes.site.edit" in held:
            return "rw"
        return "ro" if "themes.site.view" in held else None
    return "rw" if "themes.slot" in held else "ro"


def serve_themefiles(wiki_dir, config, farm, explicit_farm, base_url):
    """`/.admin/themes…` の要求を webFileDir へ渡す。base_url は `…/.admin/themes`（末尾の / 無し）。
    画面も API も、要求のたびに管理者か助手か（と、助手に与えた権限）を確かめる。"""
    denied = sysui.require_perm(wiki_dir, config, farm, explicit_farm,
                                THEMEFILES_URLPATH, "themes.view")
    if denied is not None:
        return denied
    token = _viewer.set((staffperms.granted_set(wiki_dir, auth.current_user(wiki_dir, farm)),
                         stafflog.actor(wiki_dir, farm)))
    try:
        return _serve(wiki_dir, config, farm, base_url)
    finally:
        _viewer.reset(token)


def _serve(wiki_dir, config, farm, base_url):

    env = request.environ
    path_info = env.get("PATH_INFO", "")
    marker = "/" + THEMEFILES_URLPATH
    at = path_info.find(marker)
    rest = path_info[at + len(marker):] if at >= 0 else ""
    if not rest:
        # 画面の相対URLが末尾の / を前提にしている（ファイル一覧と同じ）
        return HTTPResponse(status=303, headers={"Location": base_url + "/"})

    app = _app_for(wiki_dir, config, farm)
    if app is None:
        return HTTPResponse(
            status=503, body="ファイル一覧の部品（webFileDir 1.0 以降）が見つかりません。",
            headers={"Content-Type": "text/plain; charset=utf-8"})

    if rest == "/" and env.get("REQUEST_METHOD") in ("GET", "HEAD"):
        return HTTPResponse(screen_html(f"テーマのファイル - {farm}"), headers={
            "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache"})
    if UPLOAD_PATH_RE.match(rest) and env.get("REQUEST_METHOD") == "POST":
        denied = _check_upload(env)
        if denied is not None:
            return denied
        token = _uploading.set(True)
        try:
            return call_app(app, at + len(marker))
        finally:
            _uploading.reset(token)
    return call_app(app, at + len(marker))


def _check_upload(env):
    """アップロードの要求（置けるかを確かめるだけの check=1 も）を、名前の拡張子で先に断る。
    断るときは webFileDir のエラーと同じ形（{"error": {code, message, path}}）で返す。"""
    query = parse_qs(env.get("QUERY_STRING", ""))
    first = lambda k: (query.get(k) or [""])[0]   # noqa: E731
    allowed = {SITE_MOUNT: (UPLOAD_EXTS, "CSS と画像"),
               SLOT_SITE_MOUNT: (SLOT_EXTS, "HTML・CSS・画像・フォント")}.get(first("mount"))
    if allowed is None or first("kind") != "file":
        return None
    name = first("path").split("/")[-1]
    if file_ext(name) in allowed[0]:
        return None
    _drain(env)
    body = {"error": {"code": "forbidden",
                      "message": f"アップロードできるのは {allowed[1]}（{_upload_ext_text(allowed[0])}）だけです",
                      "path": first("dest").rstrip("/") + "/" + first("path")}}
    return HTTPResponse(json.dumps(body, ensure_ascii=False), status=403, headers={
        "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"})


def _drain(env):
    """読まなかった本文を読み捨てる（送り手が送り終えられるように）。"""
    try:
        left = int(env.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return
    stream = env.get("wsgi.input")
    while left > 0 and stream is not None:
        data = stream.read(min(left, 1024 * 1024))
        if not data:
            break
        left -= len(data)
