"""ページ本文のレンダリングと、そこから取り出す情報。

目次・タイトル・見出しの位置（セクション編集が使う）と、
本文中のリンクの書き換えをまとめている。

記法（Markdown / PukiWiki記法）ごとの読み取りかたは違っても、
出来上がるトークン列の形は同じにしてあるため、目次・見出しの位置・
リンクの書き換えはここにある同じ関数で扱える。"""
import re
import unicodedata

from wikilib import pukiwiki
from wikilib.extrarules import load_extra_rules
from wikilib.interwiki import load_interwiki
from wikilib import htmlpolicy
from wikilib.paths import (
    ATTACH_URLPATH, DELWIKI_URLPATH, FARM_PREFIX, MARKERS_PANEL_URLPATH, NEWWIKI_URLPATH,
    RESTART_URLPATH, SYSTEM_PREFIX, markup_name_for, resolve_link,
)


# ---- 段落の途中の改行（softbreak）を、日本語では詰める ----------------------
#
# 本文を読みやすく複数行に折って書くと、その行の変わり目は softbreak になり、
# HTMLでは改行文字として出る。ブラウザは連続する空白と同じく**空白1つ**として
# 描くので、英文では単語の区切りとして要るが、**日本語では書いた覚えのない
# 空白が文中に現れる**（Wiki設計者の指摘、2026-09-04）。
#
# 入れるかどうかは、改行の前後の文字で決める（Wiki設計者の指示）。
#
#   前後のどちらかが「ホワイトスペース以外の半角文字」  … 空白を入れる
#   それ以外（両側とも全角など）                        … 何も入れないで詰める
#
# 判定は east_asian_width。Na（半角）とH（半角カナ）を半角、W（全角）・
# F（全角形）・A（曖昧）を全角として扱う。**Aを全角側に入れてある**のは、
# 日本語の文中では「±」「→」「…」のような曖昧幅の文字が全角で組まれるため。
_HALFWIDTH_EAW = ("Na", "H", "N")

# 前後の文字を探すとき、飾りの開始・終了タグ（強調・リンク等）は
# 「文字を持たない目印」なので読み飛ばして、その先の文字まで見る。
# 中身が空の text も同じ（PukiWiki記法のパーサは、記法の切れ目に空の
# text トークンを挟むことがある）。
_MARKUP_ONLY = ("_open", "_close")
_SKIPPABLE_EMPTY = _MARKUP_ONLY + ("text",)


def _is_halfwidth(ch):
    """空白でない半角文字か（改行の前後がこれなら空白を残す）。"""
    if not ch or ch.isspace():
        return False
    return unicodedata.east_asian_width(ch) in _HALFWIDTH_EAW


def _edge_char(tokens, idx, step):
    """softbreakの隣にある「表示される文字」を1つ返す。分からなければNone。

    step が -1 なら手前へ（その文字列の末尾の文字）、+1 なら先へ
    （先頭の文字）。強調やリンクの開始・終了タグは文字を持たないので
    読み飛ばす。プラグインの出力や生HTMLのように**中身を見ても表示される
    文字が分からないもの**に当たったら、そこで諦めてNoneを返す
    （呼び出し側は、分からないときは空白を残す＝これまでどおりにする）。"""
    while 0 <= idx < len(tokens):
        token = tokens[idx]
        if token.content:
            return token.content[-1] if step < 0 else token.content[0]
        if not token.type.endswith(_SKIPPABLE_EMPTY):
            return None      # 中身の分からないもの（プラグイン等）
        idx += step
    return None


def render_softbreak(self, tokens, idx, options, env):
    """段落の途中の改行。日本語だけの境目では空白を残さない。

    `breaks`（改行をそのまま`<br>`にする設定）が有効なときは、
    markdown-it-py の既定と同じ振る舞いに任せる——そちらは「改行を
    見たまま出す」設定なので、詰める話とは別。"""
    if options.get("breaks"):
        return "<br />\n" if options.get("xhtmlOut") else "<br>\n"
    before = _edge_char(tokens, idx - 1, -1)
    after = _edge_char(tokens, idx + 1, 1)
    if before is None or after is None:
        return "\n"          # 判断できないときは、これまでどおり空白を残す
    return "\n" if (_is_halfwidth(before) or _is_halfwidth(after)) else ""

def build_toc(tokens, max_level=None):
    """見出しトークンから目次データ [{level, id, title}, ...] を組み立てる。
    HTMLに整形せずデータのまま渡すことで、目次の見せ方をテーマ側で自由に変更できる。

    max_level を与えると、h1〜hN だけを拾う（目次に出す深さ。表示の都合であって、
    見出しにidを振る範囲とは別物）。絞り込みは正規化前の生の見出しレベルで行う。

    戻り値の level は h1〜h6 の数字そのものではなく、そのページで最も浅い見出しを1とした
    相対的な深さ。「タイトル=h1・章=h2」で書いても「章=h1」で書いても、
    目次の字下げが同じ見え方になる。"""
    toc = []
    for i, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        anchor = token.attrGet("id")
        if not anchor or i + 1 >= len(tokens):
            continue
        level = int(token.tag[1:])
        if max_level is not None and level > max_level:
            continue
        toc.append({
            "level": level,
            "id": anchor,
            "title": tokens[i + 1].content,
        })
    if toc:
        shift = min(entry["level"] for entry in toc) - 1
        if shift:
            for entry in toc:
                entry["level"] -= shift
    return toc


def split_title(tokens, first_h1_as_title):
    """先頭ブロックがh1見出しなら (タイトル文字列, それを除いたトークン列, タイトルの終了行) を返す。
    first_h1_as_title が無効、または先頭がh1見出しでなければ (None, tokens, 0) をそのまま返す。
    タイトルの終了行は、本文（.content）に含まれない先頭部分を生ソースから除くために使う
    （タイトルはpage-header側で別途描画されるため）。

    これにより「1行目をタイトルにすると以降の章をh2から始めざるを得ない」という
    制約が無くなり、2つ目以降のh1を章見出しとして使えるようになる。"""
    if (first_h1_as_title and len(tokens) >= 3
            and tokens[0].type == "heading_open" and tokens[0].tag == "h1"):
        title_end = tokens[0].map[1] if tokens[0].map else 0
        return tokens[1].content, tokens[3:], title_end
    return None, tokens, 0


def render_markdown(engine, text, first_h1_as_title, context=None, toc_depth=None):
    """Markdownを (本文HTML, タイトル, 目次) にレンダリングする。
    context はプラグインへ渡す実行時情報（env経由でレンダリング規則から参照される）。
    toc_depth は目次に出す見出しの深さ（idを振る範囲とは別）。"""
    env = {"wiki": context}
    tokens = engine.parse(text, env)
    title, tokens, _ = split_title(tokens, first_h1_as_title)
    toc = build_toc(tokens, toc_depth)
    html = engine.renderer.render(tokens, engine.options, env)
    return html, title, toc


# ---- 記法ごとの入口 ---------------------------------------------------------
# 拡張子で記法を選ぶ判断は、この2つの関数に閉じ込める。呼び出し側（表示・編集・
# プレビュー・セクション編集）は、どの記法かを気にせず同じ形で扱える。

def is_pukiwiki(ext):
    return markup_name_for(ext) == "pukiwiki"


def parse_source(engine, text, ext, env=None):
    """ページの生テキストを、その拡張子の記法でトークン列にする。

    PukiWiki記法もmarkdown-itと同じ形のトークン列になるため、目次
    （build_toc）・見出しの位置（heading_positions）・レンダリングは
    どちらの記法でも同じものが使える。

    PukiWiki記法の「ユーザ定義ルール」「フェイスマーク定義ルール」
    （wikilib.extrarules）・InterWiki（wikilib.interwiki）・WikiNameの
    有効/無効は、env["wiki"]（context）にWikiの場所と設定が載っていればそこから
    読み込む。TOC抽出・差分表示など、contextを持たずに呼ぶ場面（env無し）では
    これらの機能無しで解釈する（構造の抽出には影響しないため、無くても
    困らない）。"""
    if env is None:
        env = {}
    if is_pukiwiki(ext):
        context = env.get("wiki")
        # 生HTMLは既定で認識させない（＝書かれたものは文字になる）。
        # 設定は記法ごとに分かれていて、ここは pukiwiki.allow_html を見る
        # （wikilib.htmlpolicy）
        extra_rules, interwiki, wikiname, allow_html = None, None, True, False
        if context is not None and context.wiki_dir is not None:
            extra_rules = load_extra_rules(context.config, context.wiki_dir)
            interwiki = load_interwiki(context.wiki_dir)
            wikiname = bool((context.config.get("pukiwiki") or {}).get("wikiname", True))
            allow_html = htmlpolicy.parses_html(
                htmlpolicy.html_policy(context.config, ext))
        return pukiwiki.parse(text, extra_rules=extra_rules, interwiki=interwiki,
                              wikiname=wikiname, allow_html=allow_html)
    return engine.parse(text, env)


def uses_title_heading(ext, first_h1_as_title):
    """先頭の見出しをページタイトルとして抜き出す記法か。

    この扱いはMarkdown固有のもの。PukiWikiではページ名がそのままタイトルで、
    本文の先頭にタイトル行を置く習慣が無いため、設定にかかわらず抜き出さない。"""
    return first_h1_as_title and not is_pukiwiki(ext)


def render_source(engine, text, ext, first_h1_as_title, context=None, toc_depth=None):
    """ページの生テキストを、その拡張子の記法で (本文HTML, タイトル, 目次) にする。"""
    env = {"wiki": context}
    tokens = parse_source(engine, text, ext, env)
    title, tokens, _ = split_title(tokens, uses_title_heading(ext, first_h1_as_title))
    toc = build_toc(tokens, toc_depth)
    html = engine.renderer.render(tokens, engine.options, env)
    return html, title, toc


def heading_positions(tokens):
    """見出しトークンから [{level, id, start, end}, ...] を返す。

    build_toc() と違い level は生の見出しレベル（h1なら1）のまま正規化しない。
    start/end は token.map による生ソース上の行範囲（0始まり、endは含まない）。
    セクションの編集範囲（section_range）を計算するための材料で、目次の見た目には使わない。"""
    positions = []
    for i, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        anchor = token.attrGet("id")
        if not anchor or i + 1 >= len(tokens) or not token.map:
            continue
        positions.append({
            "level": int(token.tag[1:]),
            "id": anchor,
            "start": token.map[0],
            "end": token.map[1],
        })
    return positions


def section_range(positions, heading_id):
    """指定した見出し（heading_idがNoneなら「最初の見出しより前の領域」）の編集範囲を返す。

    戻り値は (header_start, header_end, body_end) の行番号（0始まり、各endは含まない）。
    body_end は「次の同レベル以上の見出し」の開始行（無ければNone＝文書末まで）。
    サブレベルの見出しはbody_endの判定に影響しない＝配下のセクションを内包する。
    heading_id に一致する見出しが無ければ None を返す。"""
    if heading_id is None:
        body_end = positions[0]["start"] if positions else None
        return None, None, body_end
    for i, h in enumerate(positions):
        if h["id"] != heading_id:
            continue
        body_end = None
        for later in positions[i + 1:]:
            if later["level"] <= h["level"]:
                body_end = later["start"]
                break
        return h["start"], h["end"], body_end
    return None


def section_bounds(text, positions, heading_id, scope, intro_start=0):
    """指定セクションが占める行範囲 (start, end) を返す（0始まり、endは含まない）。

    節だけを切り出す（extract_section_text）ときも、前後と3つに分ける
    （split_section_text）ときも、範囲の決めかたは同じなのでここに分けてある。
    見つからなければ None。"""
    found = section_range(positions, heading_id)
    if found is None:
        return None
    header_start, header_end, body_end = found

    if heading_id is None:
        start = intro_start
    elif scope == "header":
        start = header_start
    else:
        start = header_end

    end = body_end if body_end is not None else len(text.splitlines())
    return start, end


def extract_section_text(text, positions, heading_id, scope, intro_start=0):
    """text（ページの生ソース全文）から、指定セクションの範囲だけを切り出す。
    scope="header" は見出し行を含む。scope="body" は見出し行を含まない（本文のみ）。
    heading_idがNoneの場合はintro_start行目から（タイトル抽出で除かれた先頭行を
    スキップするために使う。詳細はsplit_title参照）。見つからなければ None を返す。"""
    found = section_bounds(text, positions, heading_id, scope, intro_start)
    if found is None:
        return None
    start, end = found
    return "\n".join(text.splitlines()[start:end])


def split_section_text(text, positions, heading_id, scope, intro_start=0):
    """text を (その節より前, その節, その節より後) の3つに分ける。
    見つからなければ None。

    **3つを繋ぐと元のtextに戻る**（1バイトも変わらない）。`splitlines()` で
    切って `"\n".join()` で繋ぎ直す extract_section_text と違い、行末を
    そのまま持ったまま切るためである。

    セクション編集の保存は、前後をそのまま画面に持たせておいて、編集した節と
    一緒に**ページ全体**として送り返してもらう（Wiki設計者の指示、2026-09-01）。
    そうすると保存は編集画面からの保存とまったく同じ扱いになり、見出しidが
    後から変わっても、書き戻す先を探し直す必要がない。**そのためには、
    切ったものを繋ぐと元に戻ることが前提**になる。"""
    found = section_bounds(text, positions, heading_id, scope, intro_start)
    if found is None:
        return None
    start, end = found
    lines = text.splitlines(keepends=True)
    return ("".join(lines[:start]), "".join(lines[start:end]), "".join(lines[end:]))


# テーマのテンプレート環境はテーマディレクトリの組み合わせごとにキャッシュする

BARE_LINK_RE = re.compile(r'(href|src)="([^"]*)"')

# 既定のWikiでしか開けない画面（Wiki名付きのURLは403）と、どのWikiにも属さない
# 資材。本文に `/.newwiki` と書いたら、入口を付けずに書かれたまま出す
# （`rewrite_content_links` の「システムのURL」参照）。`/.allwiki` は名前を設定で
# 変えられるので、ここには入れず `_site_wide_commands` で足す
SITE_WIDE_URLPATHS = (RESTART_URLPATH, NEWWIKI_URLPATH, DELWIKI_URLPATH, MARKERS_PANEL_URLPATH)


def _site_wide_commands():
    from wikilib.wikiconfig import allwiki_command, load_config
    names = list(SITE_WIDE_URLPATHS)
    allwiki = allwiki_command(load_config())
    if allwiki:
        names.append(SYSTEM_PREFIX + allwiki)
    return names


def _site_root(base_url):
    """サイトの根（`server.prefix` の分。接頭辞なしなら空文字列）。分からなければ None。

    入口（`base_url`）から `/=Wiki名` を除いたもの。プロキシが入口を伝えている
    （`X-Forwarded-Prefix`）ときは、入口が `/sandbox` のようにWiki名を含まない形に
    なり、そこからサイトの根は割り出せないので None。"""
    from wikilib.wikiconfig import forwarded_prefix
    if forwarded_prefix() is not None:
        return None
    return base_url.rsplit("/" + FARM_PREFIX, 1)[0]


def _is_site_wide(value, commands):
    """`/.newwiki`・`/.newwiki.css`・`/.newwiki?x=1` のように、既定のWikiでしか
    開けない画面（とその資材）を指しているか。"""
    head = re.split(r"[/?#]", value[1:], maxsplit=1)[0]
    return any(head == name or head.startswith(name + ".") for name in commands)


def rewrite_content_links(html, base_url, attach_subpath, wiki_dir=None):
    """本文・メニュー中のリンクと画像参照（href="..." / src="..."）を書き換える。

    リンク先をどう読むかは記法によらず paths.resolve_link が決める。ここでは
    その答えを実際のURLに直すだけで、書きかたの決まりはこのモジュールには持たない。

    - ページ（"page"）: base_url を前置する。ページ本文はWikiをまたいでも安定する
      ようルート相対パスで書くことを推奨している（UsageGuide参照）が、URLで
      "=_system/" のようにfarmを明示していたりserver.prefixでサブパスに
      設置していたりすると、
      そのままではリンクをたどった先でその明示や接頭辞が失われてしまうため。
    - 添付ファイル（"attach"）: resolve_link が持ち主のページごと決めてくれる
      （書いていなければこのページ自身）ので、"/.attach/" を前に付けるだけ。
    - 触らないもの（"keep"）: 外部URL・"#anchor"・"mailto:"・"tel:"、それに
      既に "=Wiki名" を指している（Wikiが確定済みの）リンク。

    **入口（base_url）で始まるリンクも触らない。** 書き換え済みのリンクを
    もう一度通すと、入口が二重に付くため。二度通ることは実際にある
    （`#include` などのプラグインが取り込んだ本文を自分で書き換え、
    そのあと外側のページ全体がもう一度書き換える）。`/=Wiki名` の入口は上の
    「=Wiki名」の規則で素通りするが、`server.prefix` や、プロキシが伝える
    入口（`X-Forwarded-Prefix`。`/sandbox` のように `=` を含まない形）では
    この規則に当たらず `/sandbox/sandbox/…` になっていた。
    代償として、入口と同じ名前で始まるページ（`/sandbox/foo` と書いた
    `sandbox/foo` ページへのリンク）は、そのページを指せなくなる。

    ## システムのURL（`/.〜`）にも入口を付ける（2026-09-25）

    本文に書いた `/.attach/…`・`/.admin/configwiki`・`/.search` などは、
    `resolve_link` では「触らないもの」だが、**表示のURLには入口を付ける**。
    付けないと、既定以外のWikiで押したとき**既定のWikiの**添付・設定画面・
    検索が開いていた（Wiki設計者の指示で修正。`pagediv` の見出しに続く、
    既定のWikiへ飛ぶ不具合の2件目の調査で見つかった）。

    ただし、既定のWikiでしか開けない画面（`/.newwiki`・`/.delwiki`・`/.restart`・
    `/.allwiki`。Wiki名付きのURLは403）と、どのWikiにも属さない資材
    （`/.markers-panel`）は、**これまでどおり書かれたまま**出す（`SITE_WIDE_URLPATHS`）。
    リンクの記録（`links.py`）は `resolve_link` の答えのままで、ここでは表示の
    URLだけを変える。

    ## サイトの根（`server.prefix`）を付けるもの（2026-09-26）

    `server.prefix`（例 `/pre`）でサブパスに置いたとき、次の2つには**サイトの根**
    （`/pre`。入口から `/=Wiki名` を除いたもの。`_site_root`）だけを付ける。
    どちらもWikiは決まっているので、入口（`/pre/=_system`）ではなく根を付ける。

    - 別のWikiを指すリンク（`/=other/X` → `/pre/=other/X`）
    - 上の既定のWikiでしか開けない画面（`/.newwiki` → `/pre/.newwiki`）

    プロキシが入口を伝えている（`X-Forwarded-Prefix`）ときは、入口が `/sandbox` の
    ようにWiki名を含まない形で根を割り出せないので、どちらも書かれたまま出す
    （割り出し損なうと `/sandbox/.newwiki`、つまり403のURLになる）。

    **サイトの根で始まるリンクも触らない**（入口で始まるリンクと同じく、書き換え
    済みのため）。付けた `/pre/=other/X` がもう一度ここを通ると、`pre/=other/X`
    というページへのリンクに読まれてしまう。代償も入口のときと同じで、根と同じ
    名前で始まるページ（`/pre/foo` と書いた `pre/foo`）は指せなくなる。"""
    entrance = base_url + "/" if base_url else None
    root = _site_root(base_url) if base_url else ""
    root_entrance = root + "/" if root else None
    site_wide = []   # 既定のWikiでしか開けない画面の名前。要るときだけ読む

    def system_url(value):
        if not site_wide:
            site_wide.extend(_site_wide_commands())
        if _is_site_wide(value, site_wide):
            return (root or "") + value
        return base_url + value

    def repl(match):
        attr, value = match.group(1), match.group(2)
        if entrance and value.startswith(entrance):
            return match.group(0)
        if root_entrance and value.startswith(root_entrance):
            return match.group(0)   # サイトの根を付け済み（docstring「サイトの根」）
        kind, target = resolve_link(attach_subpath, value, wiki_dir)
        if kind == "keep":
            if base_url and value.startswith("/" + SYSTEM_PREFIX):
                return f'{attr}="{system_url(value)}"'
            if root and value.startswith("/" + FARM_PREFIX):
                return f'{attr}="{root}{value}"'
            return match.group(0)
        if kind == "page":
            return f'{attr}="{base_url}/{target}"'
        return f'{attr}="{base_url}/{ATTACH_URLPATH}/{target}"'

    return BARE_LINK_RE.sub(repl, html)
