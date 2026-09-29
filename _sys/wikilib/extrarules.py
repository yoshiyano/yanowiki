r"""PukiWiki記法の「ユーザ定義ルール」「フェイスマーク定義ルール」。

本家PukiWikiの `default.ini.php` にある `$line_rules`・`$facemark_rules`
に相当する。本家では管理者が触る設定ファイルに書く決まりなので、こちらも
サーバ本体のコード（`_sys/`）ではなく、設定ファイル
（`config/pukiwiki.extrarules.yaml`）に定義を書けるようにしてある。

書式は正規表現と置換文字列の組（`pattern`/`replace`）の列。`replace` の
`\1` などは、捕捉した文字列を差し込む位置を表す。

**置換文字列の固定部分だけが、そのままHTMLとして出力される**（本家の
置換結果がHTML断片（`<span>` や `<img>`）そのものであるのと同じ扱いで、
`<` 等も自動エスケープしない。そのため定義側の責任で安全な内容にする）。
**捕捉した部分は、通常のインライン記法として解釈し直される**
（`COLOR(red):''foo''` の強調が効く）。捕捉した部分は読み手が書いた
文字列なので、生HTMLとしては出さない（`allow_html` の検閲を受ける）。
詳しくは `match_extra_rule`。

`line_rules` は常に有効。`facemark_rules` は `config/default.yaml` の
`pukiwiki.facemark`（既定true）で一括オフにできる（本家の `$usefacemark`
に相当）。文章内にたまたま似た文字列が入って誤爆する場合の逃げ道。
"""
import re

from wikilib.paths import EXTRARULES_CONFIG_PATH, farm_extrarules_config_path
from wikilib.wikiconfig import example_of, read_yaml_local_or_common


class ExtraRules:
    """コンパイル済みの置換ルール一式。

    rules は `(compiled_pattern, replace_template)` の列。line_rules・
    facemark_rules をこの時点で1つの列にまとめておく（インライン解析側は
    種類を区別する必要が無く、出てきた順に試すだけでよいため）。"""

    def __init__(self, rules):
        self.rules = rules

    def __bool__(self):
        return bool(self.rules)


EMPTY_EXTRA_RULES = ExtraRules([])


def _compile_rules(entries):
    compiled = []
    for entry in entries or []:
        pattern = (entry or {}).get("pattern")
        replace = (entry or {}).get("replace")
        if not pattern or replace is None:
            continue
        try:
            compiled.append((re.compile(pattern), replace))
        except re.error:
            continue  # 壊れた定義1つでページ全体が表示できなくなるのを防ぐ
    return compiled


def facemark_enabled(config):
    """フェイスマーク定義ルールを使うか（本家の `$usefacemark` に相当）。"""
    return bool((config.get("pukiwiki") or {}).get("facemark", True))


def load_extra_rules(config, wiki_dir=None):
    """個別Wikiのルール定義を読み、コンパイル済みの `ExtraRules` を返す。

    **個別Wiki側（`wikidata/<Wiki名>/config/pukiwiki.extrarules.yaml`）が
    あれば、そちらだけを読む（共通側は読まない）。** `default.yaml` の
    ような項目単位の重ねあわせはしない。ルールは配列でしか書けず、
    項目単位で混ぜると「共通のどの行が生きているか」が個別Wiki側から
    見えなくなるため、丸ごと読み替える形にしてある。

    個別Wiki側が無ければ、雛形（`config/pukiwiki.extrarules.example.yaml`）
    を既定値として読む。`config/pukiwiki.extrarules.yaml`という実ファイルは
    用意しない（Wiki設計者の指示、2026-09-04。理由はwikilib.wikiconfig.load_config
    のdocstring参照）。"""
    data = read_yaml_local_or_common(
        farm_extrarules_config_path(wiki_dir) if wiki_dir else example_of(EXTRARULES_CONFIG_PATH),
        example_of(EXTRARULES_CONFIG_PATH),
    )

    rules = _compile_rules(data.get("line_rules"))
    if facemark_enabled(config):
        rules += _compile_rules(data.get("facemark_rules"))
    return ExtraRules(rules)


MAX_NEST_DEPTH = 6  # SIZE(20){ COLOR(...){ ... } } のような重ね書きの深さの上限

_GROUP_REF_RE = re.compile(r"\\(\d+)")


def match_extra_rule(rules, text, pos):
    """text[pos:] の中から、最も手前で始まる定義ルールの一致を1つ探す。

    戻り値は (開始位置, 部品の列, 終了位置) か、無ければNone。
    複数のルールが手前で並んでいる場合、**先に定義されているものを優先**する
    （本家の配列の並び順で決まる仕様と同じ）。

    **部品の列は、置換文字列を `\\N`（捕捉した部分）の前後で切ったもの。**
    `("html", 文字列)` は置換文字列の固定部分で、管理者が書いたものなので
    そのままHTMLとして出す。`("inline", 文字列)` は捕捉した部分で、
    **呼び出し側が通常のインライン記法として解釈し直す**（読み手が書いた
    文字列なので、HTMLとしては出さない）。

    以前は捕捉した部分を、置換文字列へ文字列のまま埋め込んでHTMLにしていた。
    それでは `COLOR(red):''foo''` の `''foo''` が解釈されず、そのうえ
    **読み手が書いた `<script>` などが `allow_html` の検閲を通らずに出て
    しまう**（extra_rule_html は検閲の対象外のため）。部品に分けて捕捉部分だけを
    通常の解析へ戻すことで、どちらも防ぐ。入れ子（`SIZE(20){COLOR(..){..}}`）も、
    捕捉部分の中でこのルールが再び当たることで自然に展開される。"""
    best = None
    for compiled, replace in rules.rules:
        m = compiled.search(text, pos)
        # **空の一致は無いものとして扱う。** 位置が進まないので、そのまま使うと
        # 解析が同じ場所で止まらなくなる（`a*` のようなパターンで起こる）。
        # 設定画面は空に当たるパターンを保存させないが、手で書いたファイルには
        # ありうるため、ここでも防ぐ。
        if m is None or m.end() == m.start():
            continue
        if best is None or m.start() < best[0].start():
            best = (m, replace)
    if best is None:
        return None
    m, replace = best
    return m.start(), _split_replace(m, replace), m.end()


def _split_replace(m, replace):
    """置換文字列を、固定のHTMLと捕捉した部分の並びに切り分ける。"""
    parts = []
    pieces = _GROUP_REF_RE.split(replace)   # [固定, 番号, 固定, 番号, ..., 固定]
    for i, piece in enumerate(pieces):
        if i % 2 == 0:
            if piece:
                parts.append(("html", piece))
        else:
            try:
                content = m.group(int(piece))
            except IndexError:  # 定義にある番号のグループが、パターンには無い
                content = None
            if content:
                parts.append(("inline", content))
    return parts
