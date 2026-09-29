"""本文に書かれたリンク先を、**書かれたまま**の位置で拾って書き換える。

ページの名前が変わると、そのページを指していたリンクは行き先を失う。
`links` の表（pagedb）で「どのページが指しているか」は分かるので、あとは
そのページの本文を開いて、**指し先だけ**を新しい名前に書き換えればよい。

## なぜ描画側の書き換え（render.rewrite_content_links）では足りないか

あちらはHTMLになった後の `href="…"` を直すもので、表示のたびに働く。
こちらが相手にするのは**保存されている本文そのもの**なので、記法ごとの
書きかた（`[表示](先)` と `[[表示>先]]`）を、その位置のまま直す必要がある。

## 何を書き換え、何を触らないか

拾った1つ1つを `paths.resolve_link` に通し、**ページとして解決できて、かつ
名前が変わったページを指しているものだけ**を書き換える。添付ファイル・外部URL・
ページ内アンカー・別Wikiは resolve_link が "page" 以外を返すので手を付けない。
判断を resolve_link に任せるのは、表示のときと同じ答えになるようにするため。

## 書きかたは、近さで選ぶ

絶対と相対のどちらで書くかは、**書き換えたあとの近さ**で決める。書き手が選んだ
書きかたを基本は保ちつつ、そのままでは読みにくくなる場合だけ乗り換える。

近さは「移動量」で測る。**相対の書きかたに含まれる `/` の数**で、上へ（`..`）と
下へ（`age/`）を区別しない。書き手にとっての遠さは、上下の向きではなく
**辿る段数**で決まるため。

    target        0    となりに置いてある
    ../target     1    1つ動く
    age/ten       1    1つ動く
    ../../target  2    2つ動く

| 元の書きかた | どうするか |
|---|---|
| 絶対 | 絶対のまま。ただし動いたページの本文で、相対にすると移動量1まで近づいた場合は相対にする |
| 相対 | 相対のまま。ただし動いたことで移動量が**増える**場合は絶対にする |

`../../p3/page/age/ten` のような、辿らないと行き先の見当がつかない書きかたを
残さないための決まり。同じか近くなるぶんには相対のほうが読みやすいので、
そのまま相対で書き直す。

相対を組み直したあとは resolve_link に通し直して、狙った先に解けることを
確かめる（解けなければ絶対にする）。パーセント符号化（`%E3%83%86…`）されて
いたものは、符号化したまま書き戻す。

## 動いたページ自身も見直す

指し先が変わっていなくても、**自分の位置が変わった**なら相対の書きかたは
見直さなければならない。`../target` は、動いた先から見ると別のページを
指してしまうためである。そのため `rewrite_links` には、動いた場合だけ
`old_subpath`（動く前の位置）を渡す。指していた先はそこから解く。
"""
import posixpath
import re
from urllib.parse import quote as urlquote, unquote

from wikilib import pukiwiki
from wikilib.paths import ATTACH_URLPATH, pagepath_of_subpath, resolve_link

# Markdown: `[表示](先)` `![説明](先)` の "](" のあとに続くリンク先。
# 空白の前まで（`](先 "題")` の題は含めない）と、`<…>` で囲った書きかたの両方を受ける。
MD_INLINE_RE = re.compile(r"\]\(\s*(?:<(?P<angle>[^>\n]*)>|(?P<bare>[^()\s]*))")
# Markdown: 行頭の参照定義 `[名前]: 先`
MD_REFDEF_RE = re.compile(r"(?m)^[ ]{0,3}\[[^\]\n]+\]:[ \t]*(?P<bare>\S+)")
# PukiWiki: `[[…]]` のかたまり。中身の切り分けは pukiwiki.link_tokens と同じ規則で行う
PUKI_LINK_RE = re.compile(r"\[\[(?P<inner>[^\]\n]*)\]\]")
# PukiWiki: `{[…]}` のかたまり（[[…]]の相対版。pukiwiki.INLINE_RE参照）
PUKI_RLINK_RE = re.compile(r"\{\[(?P<inner>[^\]}\n]*)\]\}")


def _puki_target_span(inner, offset):
    """`[[…]]`・`{[…]}` の中身から、リンク先が書かれている範囲を (開始, 終了) で返す。

    受ける形は pukiwiki.link_tokens と同じ（`[[表示>先]]` `[[表示:URL]]` `[[名前]]`、
    `{[…]}`も同じ切り分け）。表示名は触らず、**先の部分だけ**を書き換えたいので、
    位置で返す。"""
    arrow = inner.find(">")
    if arrow >= 0:
        start = arrow + 1
    else:
        head, colon, rest = inner.partition(":")
        if colon and re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://", rest.strip()):
            return None  # `[[表示:URL]]`。外部URLなので触らない
        start = 0
    # 前後の空白は書きかたの一部なので残し、中身の範囲だけを返す
    end = len(inner)
    while start < end and inner[start].isspace():
        start += 1
    while end > start and inner[end - 1].isspace():
        end -= 1
    if start >= end:
        return None
    return offset + start, offset + end


_fallback_engine = None


def default_engine():
    """engine を渡されなかった呼び出し向けの、使い回すだけの軽いMarkdownIt。
    プラグイン等の記法は要らない（地の文かどうかの判定にしか使わないため）。"""
    global _fallback_engine
    if _fallback_engine is None:
        from markdown_it import MarkdownIt
        _fallback_engine = MarkdownIt("gfm-like")
    return _fallback_engine


def excluded_ranges(text, tokens):
    """正規表現では判別できない「地の文」の範囲（コードブロック・インライン
    コード・HTMLブロック）を、パーサのトークン列から集める。

    Markdown・PukiWikiのどちらも同じ形のToken列を返す（pukiwiki.parse も
    markdown_it.Token をそのまま使っている）ため、この関数は記法を問わず
    共通で使える。fence/code_block/html_block はブロック単位で `token.map`
    （行範囲）を持つので、行の開始オフセットを前計算して文字位置に直す。
    インラインの code_inline だけは1行の中の話なので、その行の範囲内で
    バッククォート込みの文字列を探して位置を特定する（コード片そのものの
    中身は markdown-it が既に確定させているので、探す範囲を行内に絞れば
    誤って別の場所を拾う心配はない）。"""
    lines = text.split("\n")
    line_start = [0]
    for line in lines:
        line_start.append(line_start[-1] + len(line) + 1)

    ranges = []
    for token in tokens:
        if token.type in ("fence", "code_block", "html_block") and token.map:
            start, end = token.map
            ranges.append((line_start[start], line_start[min(end, len(lines))]))
        elif token.type == "inline" and token.map and token.children:
            start, end = token.map
            seg_start = line_start[start]
            seg = text[seg_start:line_start[min(end, len(lines))]]
            for child in token.children:
                if child.type != "code_inline":
                    continue
                needle = "`" + child.content + "`"
                pos = seg.find(needle)
                if pos != -1:
                    ranges.append((seg_start + pos, seg_start + pos + len(needle)))
    return ranges


def is_excluded(start, end, ranges):
    return any(r_start <= start and end <= r_end for r_start, r_end in ranges)


def link_spans(text, ext, engine=None, interwiki=None):
    """本文の中のリンク先を (開始, 終了, リンク先, relative) で返す（前から順）。

    relativeは`{[…]}`（pukiwiki.link_tokensの相対版）由来ならTrue。
    `rewrite_links`が、書き換えた結果の先頭の"./"を省いてよいかどうかの
    判定に使う（`{[…]}`は裸のまま書けば"./"を補った場合と同じ意味になる
    ため。`{[./X]}`と`{[X]}`は常に等価）。

    コードブロック・インラインコード・HTMLコメントに書かれた、リンクに
    似た記法（説明・記法のサンプル・コメントアウトしたリンクなど）を
    誤って拾わないよう、実際のパーサが「地の文」として扱った範囲
    （`excluded_ranges`）に含まれる候補は取り除く。

    engine は使い回したい MarkdownIt インスタンスがあれば渡す（省略時は
    軽いものをこの中だけで使い回す）。呼び出し側が既に持っていれば、
    パーサを新たに作り直すコストを省ける。

    interwiki は `{[…]}`（相対）を`pukiwiki.relativize_target`へ通す前に、
    InterWiki登録名（`名前:ページ名`）ではないことを確かめるために使う
    （pukiwiki.link_tokensと同じ順序——InterWikiの判定を先に行う。
    渡さなくても動くが、InterWikiが登録されたWikiでは`{[名前:ページ名]}`
    が誤って相対化されうる）。"""
    spans = []
    if ext == ".txt":
        for pattern, relative in ((PUKI_LINK_RE, False), (PUKI_RLINK_RE, True)):
            for m in pattern.finditer(text):
                found = _puki_target_span(m.group("inner"), m.start("inner"))
                if found is None:
                    continue
                raw = text[found[0]:found[1]]
                href = raw
                if relative and not (
                        interwiki is not None
                        and interwiki.resolve(raw.split("#", 1)[0]) is not None):
                    # {[…]}（relative）は、書かれたまま（rawが位置の書き換え
                    # 対象）ではなく、pukiwiki.relativize_targetを通した
                    # 「実際に指す先」をhrefとして返す。[[…]]と{[…]}のbare
                    # な書きかたが別の意味（絶対/相対）を持つため、
                    # resolve_link に渡す値はここでそろえておく必要がある。
                    href = pukiwiki.relativize_target(raw)
                # relativeは呼び出し側（rewrite_links）が、書き換えた結果の
                # 先頭の"./"を取り除いてよいかどうかの判定に使う
                # （{[…]}由来の場合だけ、"./"は書かなくても同じ意味になる）。
                spans.append((found[0], found[1], href, relative))
        spans.sort()
    else:
        for pattern in (MD_INLINE_RE, MD_REFDEF_RE):
            for m in pattern.finditer(text):
                group = "angle" if m.groupdict().get("angle") is not None else "bare"
                if m.group(group) is None:
                    continue
                # Markdownには{[…]}に相当する記法が無いので常にFalse
                spans.append((m.start(group), m.end(group), m.group(group), False))
        spans.sort()

    if not spans:
        return spans

    tokens = pukiwiki.parse(text) if ext == ".txt" else (engine or default_engine()).parse(text)
    ranges = excluded_ranges(text, tokens)
    if not ranges:
        return spans
    return [s for s in spans if not is_excluded(s[0], s[1], ranges)]


def canonical_target(subpath, href, wiki_dir=None):
    """そのリンクが指す先を **(持ち主, ファイル名)** で返す。どちらでもなければ
    (None, None)。

    ページなら 持ち主 が指す先そのもの（`/ページパス` の形）で、ファイル名は
    None。添付ファイルなら 持ち主 がそのファイルを持つページ、ファイル名が
    そのファイル。

    **添付ファイルも「絶対の指し先」として、ページと同じ土台で扱うための形。**
    持ち主のページパスが変わったか（＝持ち主自身の改名）と、参照元からの
    相対の書きかたが保てているか（＝参照元が動いた）は別の話で、後者は
    ページでも添付でも同じ計算で決まる（`rewritten_href` を参照。持ち主を
    「そのページ自身」とみなせば、ページの指しかたはファイル名が無い添付の
    指しかたと同じ形になる）。

    `page_links`（links.py）と同じ整えかたを通す。**同じ指しかたが2通りに
    分かれると突き合わせで取りこぼす**ため、揃える関数は1つにしておく。"""
    kind, target = resolve_link(subpath, href, wiki_dir)
    if kind == "page":
        return "/" + pagepath_of_subpath(unquote(target.split("#", 1)[0])), None
    if kind == "attach":
        owner_subpath, sep, filename = unquote(target.split("#", 1)[0]).rpartition("/")
        if not sep:
            return None, None
        return "/" + pagepath_of_subpath(owner_subpath), filename
    return None, None


def resolve_href(subpath, href, wiki_dir=None, interwiki=None):
    """書かれたリンク先の文字列を解決する。(種別, 持ち主, ファイル名) を返す。
    このWiki内の場所を指さなければNone。

    種別は `"page"` か `"attach"`。ページならファイル名はNone。InterWiki
    （登録名が一致するもの。wikilib.interwiki）は、このWiki内の場所ではない
    のでNoneになる。抽出（links.page_links）とリライト（rewrite_links）の
    両方から、同じ判断として使う。"""
    if interwiki is not None and interwiki.resolve(href.split("#", 1)[0]) is not None:
        return None
    owner, filename = canonical_target(subpath, href, wiki_dir)
    if owner is None:
        return None
    return ("attach" if filename else "page"), owner, filename


def move_amount(rel):
    """相対の書きかたが持つ「移動量」。**`/` の数**で数える。

        ./target        0   となりに置いてある
        ../target       1   1つ動く
        ./age/ten       1   1つ動く
        ../../target    2   2つ動く

    上へ（`..`）と下へ（`age/`）を区別せず、書かれたままの区切りの数で数える。
    書き手にとっての「どれだけ遠いか」は、上下の向きではなく**辿る段数**で
    決まるため。アンカー（`#…`）は位置を表さないので、渡す前に落としておく。

    先頭の `./` は数えない。**「ここから下」を表すのに必ず要る書きかた**
    （付けないとルートからの絶対になる）であって、距離ではないため。"""
    if rel.startswith("./"):
        rel = rel[2:]
    return rel.count("/")


def relative_href(base, target):
    """base のページから target のページを指す相対の書きかた。同じ場所なら空。

    上へ辿らない（`..` で始まらない）ぶんには **`./` を必ず前に付ける**。
    付けないと「ルートからの絶対」の意味になってしまうため
    （paths.full_pagepath）。"""
    rel = posixpath.relpath(target or ".", base or ".")
    if rel == ".":
        return ""
    return rel if rel.startswith("..") else "./" + rel


def rewritten_href(href, subpath, new_owner, filename=None,
                    old_owner=None, old_subpath=None):
    """指し先を差し替える。絶対と相対のどちらで書くかは下の決まりで選ぶ。

    **ページも添付ファイルも同じ計算**で決める。ページは filename が None、
    添付ファイルは持ち主（new_owner）にファイル名（filename）が付く形なだけで、
    「持ち主までの距離」で近さを測るのは共通している。

    new_owner は書き換えたあとに指すべき持ち主（先頭の `/` なし。ページ自身が
    対象ならページパスそのもの）。old_owner は動く前に指していた持ち主
    （先頭の `/` あり。`canonical_target` の返り値そのまま）。**動いていない
    参照元でも常に渡す**（前より遠くなっていないかの比較に使うため）。
    old_subpath を渡すと「参照元のページ自身が動いた」場合として、動く前の
    位置から見た書きかたと比べる（渡さなければ、参照元は動いていないとして、
    いまの位置をそのまま「動く前の位置」として使う）。

    ## どちらで書くか

    **絶対で書かれていたものは絶対のまま。** ただし動いたページ自身の本文では、
    相対にすると隣り合う（移動量1）ところまで近づいた場合だけ相対に直す。
    近くにあるものを絶対で指し続けると、フォルダごと動かしたときに毎回
    書き換えが要るためで、近さが分かる書きかたにしておくほうが後で楽になる。

    **相対で書かれていたものは相対のまま。** ただし動いたことで前より遠くなる
    （移動量が増える）場合は絶対にする。`../../p3/page/age/ten` のような、
    辿らないと行き先の見当がつかない書きかたを残さないため。同じか近くなる
    ぶんには相対のほうが読みやすいので、そのまま相対で書き直す。

    **添付ファイルは、遠くなっても絶対にしない。** 添付ファイルには
    farmをまたいでも安全な絶対の書きかたが無い（`absolute_form` 参照。
    唯一の絶対の書きかた `/.attach/…` は system の生URLとして素通りする
    ためfarmの接頭辞が付かず、既定のfarmが変わると別のfarmを指してしまう）。
    そのため読みやすさより安全（確実に元のfarmへ解ける）を優先し、
    遠くなっても相対のまま書き直す。"""
    bare, sep, anchor = href.partition("#")
    encoded = unquote(bare) != bare  # 元が符号化されていたか

    def dress(path):
        return (urlquote(path) if encoded else path) + sep + anchor

    def with_filename(owner_path):
        return owner_path + "/" + filename if filename else owner_path

    # 書き手が「ルートからの絶対」のつもりで書いたか。**`/` 始まりだけでは
    # ない**——`[[Glossary]]` のような裸の名前もルートからの絶対である
    # （paths.full_pagepath）。`/` 始まりだけを絶対とみなしていたころは、
    # 裸の名前が相対として扱われ、リネームのたびに `[[../../../../Words]]`
    # のような `..` の連なりへ書き換えられていた（2026-09-05に修正）。
    #
    # 添付ファイルはこの判定から外す。区切りの有無で意味が変わる
    # （`logo.png` は「いま開いているページ」の添付、`bbb/img.jpg` は
    # `/bbb` の添付。resolve_link 参照）うえ、そもそも絶対へ寄せる先が
    # 無い（absolute_form 参照）ので、これまでどおり相対で書き直す。
    written_absolute = not filename and not bare.startswith(("./", "../"))
    # 裸で書かれていたら裸のまま戻す。裸も `/` 付きも意味は同じなので、
    # 書き手の書きかたを勝手に変えない（1枚の改名で、指している全ページの
    # 見た目が変わってしまわないようにするため）
    bare_written = written_absolute and not bare.startswith("/")

    def absolute_form():
        # 添付ファイルには「farmをまたいでも安全な絶対の書きかた」が無い。
        # `/持ち主/ファイル名` は resolve_link に「ページ」として解決されて
        # しまう（`/` で始まる書きかたは常にページ扱い）。唯一の絶対の書きかた
        # `/.attach/持ち主/ファイル名`（Syntax/Common）は system の生URL
        # （"keep"）として素通りする＝farmの接頭辞が付かないため、farmを
        # 明示するURLで開いている場合や、既定のfarmが変わった場合に別の
        # farmを指してしまう。そのため本体の書き換えでは使わない
        # （`usable` が偽になる、辿れない場合の最後の手段としてのみ使う）。
        if filename:
            return "/" + ATTACH_URLPATH + "/" + new_owner + "/" + filename
        # new_owner が空になるのはWikiのトップだけ。裸で書くと空文字列に
        # なってリンクが消えるので、そのときは `/` 付きにする
        return new_owner if (bare_written and new_owner) else "/" + new_owner

    moved = old_subpath is not None
    base = pagepath_of_subpath(subpath)
    old_base = pagepath_of_subpath(old_subpath) if moved else base
    rel_owner = relative_href(base, new_owner)
    rel = with_filename(rel_owner) if rel_owner else ""
    # 組み直した相対が本当に狙った先へ解けるか（`..` でWikiの外に出ないか）
    usable = bool(rel_owner) and canonical_target(subpath, rel) == ("/" + new_owner, filename)
    before_rel_owner = relative_href(old_base, (old_owner or "")[1:])

    if written_absolute:
        # 絶対で書かれていた。動いたページ自身の本文で、隣り合うところまで
        # 近づいたときだけ相対にする
        if usable and move_amount(rel_owner) <= 1 and moved:
            return dress(rel)
        return dress(absolute_form())

    if not usable:
        return dress(absolute_form())  # 相対では書けない（最後の手段）
    if filename:
        # 添付ファイルは、farmをまたいでも安全な絶対の書きかたが無いので
        # （absolute_form 参照）、遠くなっても相対のまま書き直す
        return dress(rel)
    # 相対で書かれていた。動いたのが参照元自身でも、指し先だけが動いた場合でも、
    # 前より遠くなる（移動量が増える）なら絶対にする
    return dress(rel if move_amount(rel_owner) <= move_amount(before_rel_owner)
                else absolute_form())


def rewrite_links(text, subpath, ext, renames, old_subpath=None, cache=None,
                  wiki_dir=None, interwiki=None, engine=None):
    """本文のリンク先を書き換える。(新しい本文, 書き換えた数) を返す。

    engine は link_spans に渡すだけ（使い回したい MarkdownIt があれば）。

    renames は {旧ページパス: 新ページパス}（どちらも先頭の `/` は付けない）。
    ページの実体パス subpath は、**書き換えたあとの位置**を渡すこと
    （相対パスの起点になるため）。

    old_subpath を渡すと、**そのページ自身が動いた**場合として扱う。動いた側は
    指し先が変わらなくても書きかたを見直す必要がある（同じ `../target` でも、
    動いた先からは別のページを指してしまうため）。動いていないページでは
    渡さないこと。

    ## cache: 本文を読み直さなくても、何を指しているかは分かっている

    cache は `{書かれた文字列: (種別, 持ち主, ファイル名)}`（`links` テーブルに
    記録済みの解決結果。`pagedb.link_rows_of` の戻り値をそのまま渡せる）。
    本文はどのみち保存のたびに全文を取り出し直しているので、**位置ではなく
    文字列をキーにした解決結果のキャッシュ**さえあれば、ここで改めて
    `resolve_link` を呼ぶ必要がない。実際に本文のどこにその文字列があるかは
    `link_spans` でそのときの本文に毎回かければ見つかる（本文はここでは
    変わっていないので、位置がずれる心配もない）。

    cache に無い文字列（まだ取り出していない本文など）は、wiki_dir を渡して
    いればその場で解決する（保険）。渡していなければ触らずに読み飛ばす。"""
    lookup = {"/" + old: new for old, new in (renames or {}).items()}
    moved = old_subpath is not None and old_subpath != subpath
    if not lookup and not moved:
        return text, 0
    cache = cache or {}
    resolve_base = old_subpath if moved else subpath
    new_base = pagepath_of_subpath(subpath)

    out, last, changed = [], 0, 0
    for start, end, href, relative in link_spans(text, ext, engine=engine, interwiki=interwiki):
        resolved = cache.get(href)
        if resolved is None:
            if wiki_dir is None and interwiki is None:
                continue
            resolved = resolve_href(resolve_base, href, wiki_dir, interwiki)
        if resolved is None:
            continue
        kind, owner, filename = resolved

        if not moved and owner not in lookup:
            continue  # 動いていないページで、指し先の名前も変わっていない
        new_owner = lookup.get(owner, owner[1:])

        if filename and moved and new_owner == new_base:
            # 添付ファイルの持ち主が、動いた自分自身になった。添付フォルダは
            # ページと一緒に動くので、相対の書きかたを見直す必要が無い
            # （`./logo.png` はどこへ動いても「いま開いているページ」を指す）
            continue

        new_href = rewritten_href(href, subpath, new_owner, filename,
                                   old_owner=owner,
                                   old_subpath=old_subpath if moved else None)
        if new_href == href:
            continue  # hrefは常に"./"付きの相対形（relativize_target）なので、
                      # 「変化なし」の判定はここ（下の"./"剥がしより前）で行う
        if relative and new_href.startswith("./") and len(new_href) > 2:
            # {[…]}由来のリンクは、"./"を書かなくても同じ意味になる
            # （relativize_targetが裸の書きかたを"./"付きへそろえているのと
            # ちょうど逆の変換）。rewritten_hrefは[[…]]・{[…]}を区別せず
            # 常に明示の"./"/"../"付きで相対を書くため、{[…]}に書き戻す
            # ときだけ冗長な"./"を取り除く。"../"・絶対（"/"始まり）は
            # {[…]}では意味が変わるのでそのまま残す
            # （Wiki設計者の指示、2026-09-04。"/a/./b"を"/a/b"に整えるのと同じ、
            # パスの意味を考える必要が無い機械的な変換）。
            new_href = new_href[2:]
        out.append(text[last:start])
        out.append(new_href)
        last = end
        changed += 1
    if not changed:
        return text, 0
    out.append(text[last:])
    return "".join(out), changed
