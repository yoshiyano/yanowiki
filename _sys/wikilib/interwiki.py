"""PukiWiki記法の InterWiki（`[[登録名:ページ名]]` で外部サイトへリンクする記法）。

本家PukiWikiは登録名の一覧を専用のページ（InterWikiName）に書くが、
このシステムでは他の管理者向けの定義（`wikilib.extrarules` の置換ルール等）
と同じく、設定ファイル（`config/pukiwiki.interwiki.yaml`）に書く。

書式は `name`（登録名）・`url`（`$1` の位置にページ名が入る。`$1` が無ければ
末尾に付け足す）・`encode`（省略時 `std`＝URLエンコードする。`raw` にすると
そのまま差し込む）の列。
"""
from urllib.parse import quote as urlquote

from wikilib.paths import INTERWIKI_CONFIG_PATH, farm_interwiki_config_path
from wikilib.wikiconfig import example_of, read_yaml_local_or_common


class Interwiki:
    """コンパイル済みのInterWiki登録表（名前→設定の辞書）。"""

    def __init__(self, entries):
        self.entries = entries  # {name: {"url":..., "encode":...}}

    def __bool__(self):
        return bool(self.entries)

    def resolve(self, target):
        """`target`（`[[…]]` の中身、書かれたまま）が `登録名:ページ名` の
        形なら、実際のURLを返す。当てはまらなければNone。

        `#アンカー名` が付いていれば、URLの末尾にそのまま付け足す
        （InterWiki先のページ内アンカーとして解釈させるため）。"""
        name, colon, rest = target.partition(":")
        if not colon:
            return None
        entry = self.entries.get(name)
        if entry is None:
            return None
        param, sharp, anchor = rest.partition("#")
        encoded = param if entry.get("encode") == "raw" else urlquote(param)
        url = entry.get("url") or ""
        href = url.replace("$1", encoded) if "$1" in url else url + encoded
        return href + ("#" + anchor if sharp else "")


EMPTY_INTERWIKI = Interwiki({})


def load_interwiki(wiki_dir=None):
    """個別Wikiの登録表を読み、`Interwiki` を返す。

    **個別Wiki側（`wikidata/<Wiki名>/config/pukiwiki.interwiki.yaml`）が
    あれば、そちらだけを読む（共通側は読まない）。** 登録表は配列でしか
    書けず、項目単位で混ぜると「共通のどの登録名が生きているか」が
    個別Wiki側から見えなくなるため、丸ごと読み替える形にしてある。

    個別Wiki側が無ければ、雛形（`config/pukiwiki.interwiki.example.yaml`）
    を既定値として読む。`config/pukiwiki.interwiki.yaml`という実ファイルは
    用意しない（Wiki設計者の指示、2026-09-04。理由はwikilib.wikiconfig.load_config
    のdocstring参照）。"""
    data = read_yaml_local_or_common(
        farm_interwiki_config_path(wiki_dir) if wiki_dir else example_of(INTERWIKI_CONFIG_PATH),
        example_of(INTERWIKI_CONFIG_PATH),
    )

    entries = {}
    for row in data.get("interwiki") or []:
        name = (row or {}).get("name")
        url = (row or {}).get("url")
        if not name or not url:
            continue
        entries[name] = {"url": url, "encode": (row or {}).get("encode", "std")}
    return Interwiki(entries)
