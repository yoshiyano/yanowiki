#!/usr/bin/env python3
"""plugin/code.css・plugin/code.js（Prism.js本体）を作り直すための道具。

https://prismjs.com/download.html の「ダウンロードビルダー」で選べるのと
同じ構成（下のVERSION/THEME/LANGS/PLUGINS）を、npm（jsdelivr経由）から
機械的に取得・依存関係順に並べて連結する。ダウンロードビルダー自体は
ブラウザ側でしか組み立てられない（サーバー側から叩けるURLが無い）ため、
components.json（同梱の依存関係メタデータ）を自分で読んで同じことをしている。

出力先が`plugin/`なのは、Prism資材を「そのページで実際に使われた
プラグインの資材だけ読み込む」既存の仕組み（`plugin/<name>.css`・
`plugin/<name>.js`、`_sys/wikilib/plugins.py`の`plugin_asset_urls`。
`context.used_plugins`が"code"を含むページでだけ`<link>`/`<script>`が
自動で足される）に乗せているため。以前はtheme側で全ページ無条件に
読み込んでいたが、`#code`を1回も呼ばないページにまでPrism一式
（150KB超）を配る無駄があった（2026-08-29、wikiPluginセッションとの
すり合わせで移行）。`#code()`（中身無しの空呼び出し）は、素のMarkdown
コードフェンスしか使わないページでこの資材を読み込ませる合図として
plugin/code.py側に実装されている。

このビルドツール自体はtheme/に置いたまま（Prismという第三者JSの
取得・連結はwikiSystem側の管理事項のため）。plugin/code.py本体
（引数の意味・PLUGIN_INFO等）はwikiPlugin側の管轄で、ここでは触らない。

使いかた: このファイルのある場所で `./prism.build.py` を実行するだけ
（標準ライブラリのみで完結。実行にはインターネット接続が要る）。
plugin/code.css・plugin/code.js を直接上書きする。

言語・プラグインを足す/減らすときはLANGS/PLUGINSを直接編集する。
バージョンを上げるときはVERSIONを変えるだけでよい（依存関係の解決は
そのバージョンのcomponents.jsonを毎回読み直すので、追従する）。

以下はこのスクリプトが末尾に必ず追記する、wikiSystem側の追加分
（手で復元する必要はない）:
  - DARK_MODE_CSS            ダークモード対応
  - NO_COPY_CSS              nocopy（コピーボタンの個別非表示、#code参照）
  - AUTOLOADER_JS            autoloaderの取得先をjsdelivrに固定
  - LINE_NUMBERS_DEFAULT_JS  行番号を既定でON（#codeのnonumはno-line-numbers
                             クラスで個別に外す、Prism本体のisActiveの仕組み）
  - PUKIWIKI_LANG_JS         PukiWiki記法の言語定義（#code(pukiwiki)用。
                             Prismが配っている言語には無いため自前で持つ）
  - MARKDOWN_PLUGIN_JS       markdown言語定義に、このシステムのプラグイン記法
                             （#name(args) / &name(args);）の認識を足す
"""
import json
import os
import re
import time
import urllib.request

VERSION = "1.30.0"
# 配色。prismjsが配っているテーマ名をそのまま書く
# （prism / coy / dark / funky / okaidia / solarizedlight /
#  tomorrow / twilight）。既定の "prism" だけファイル名の付けかたが
# 違うので、取得のところで振り分けている
THEME = "coy"
LANGS = ["markup", "css", "clike", "javascript", "apacheconf", "arduino", "bash",
         "basic", "c", "csharp", "cpp", "cmake", "csv", "diff", "django",
         "dns-zone-file", "docker", "gcode", "git", "go", "ignore", "java",
         "json", "json5", "jsonp", "latex", "lisp", "lua", "markdown",
         "markup-templating", "matlab", "nasm", "nginx", "perl", "php",
         "python", "ruby", "rust", "scss", "sql", "typescript", "vbnet",
         "verilog", "vhdl", "vim", "wiki", "yaml"]
PLUGINS = ["line-highlight", "line-numbers", "show-invisibles", "file-highlight",
           "show-language", "highlight-keywords", "autoloader", "keep-markup",
           "command-line", "toolbar", "copy-to-clipboard"]

BASE = f"https://cdn.jsdelivr.net/npm/prismjs@{VERSION}/"

# 取得したPrismのCSSで、`[class*=language-]` を2つ重ねて詳細度を上げるための
# 置換。`pre[class*=language-]` は (0,1,1) で、テーマの `.content pre`
# (0,1,2) に負ける——同点ではなく、そもそも負けている。読み込み順の規約
# （プラグイン→テーマ）以前の問題なので、選択子そのものを強くする。
#
# **なぜこうするか。** Prismのコードブロックは、diffmergeと同じ「中身の
# 見た目を自分で完結させる部品」である。テーマの `.content pre`（枠・背景・
# 余白）が効くと、外側にテーマの箱・内側にPrismの箱という二重の箱になる
# （2026-09-02、coyテーマへ変えたときに表面化。coyは背景も枠も `<pre>` では
# なく中の `<code>` に置く作りなので、ズレがはっきり出た）。テーマ側に
# 「Prismのpreには手を出さない」と覚えてもらう手もあるが、それだと第三者の
# テーマすべてに同じ約束を求めることになる。ここで閉じるほうが確実。
#
# 値を書き写さずに済むのが要点で、テーマ（THEME）を変えても追従する。
LANG_ATTR_RE = re.compile(r'\[class\*=(?P<q>["\']?)language-(?P=q)\]')


def bump_specificity(css):
    """`[class*=language-]` を2つ重ねて、選択子の詳細度を1段上げる。

    Prism自身も `.line-numbers.line-numbers` として同じ手を使っている
    （テーマの指定に勝つため）。属性選択子を重ねても、当たる要素は
    まったく変わらない。"""
    return LANG_ATTR_RE.sub(lambda m: m.group(0) * 2, css)
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.join(HERE, "..", "plugin")

THEME_RESET_CSS = """
/* ==== wikiSystem追加分: テーマの pre 装飾を打ち消す ====
   各テーマは `.content pre` に枠・背景・余白を持っている（読みものとしての
   整形済みテキスト向け）。Prismのコードブロックはそれ自身で見た目が
   完結しているので、両方が効くと**外にテーマの箱・中にPrismの箱**という
   二重の箱になる（2026-09-02、coyテーマへ変えたときに表面化）。

   背景・余白はPrism側が同じ指定を持っているので、選択子の詳細度を上げる
   （bump_specificity）だけで勝てる。**枠だけはPrism側が何も言わない**ので、
   ここで明示的に消す。box-shadowも同じ理由で消す（coyは紙めくれの影を
   ::before/::after に置くので、preそのものの影は要らない）。

   `[class*="language-"]` を2つ重ねているのは、テーマの `.content pre`
   (0,1,2) に勝つため。このブロックは prism.build.py が自動で付け直す。 */
pre[class*="language-"][class*="language-"] {
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
"""

DARK_MODE_CSS = """
/* ==== wikiSystem追加分: ダークモード対応 ====
   Prismのテーマはどれも明るい/暗いのどちらかを前提にした固定色を持つ。
   このサイトは common.css / 各テーマCSS が prefers-color-scheme: dark で
   --code-bg 等を暗色に切り替える作りなので、明るい前提のテーマ（既定の
   "prism"、いま使っている "coy" など）をそのまま置くと、暗いpre背景に
   黒文字が乗って読めなくなる。ここでは**地の色まわりだけ**を打ち消し、
   トークンごとの配色（キーワードの青・文字列の緑など）はテーマのまま
   活かす（暗い背景でも判別できる程度の彩度のため）。
   このブロックは prism.build.py が自動で付け直すので、再生成のたびに
   手で書き戻す必要はない。 */
@media (prefers-color-scheme: dark) {
  code[class*="language-"][class*="language-"],
  pre[class*="language-"][class*="language-"] {
    color: #c9d1d9;
    text-shadow: none;
  }
  :not(pre) > code[class*="language-"][class*="language-"],
  pre[class*="language-"][class*="language-"] {
    background: transparent;
  }
  .language-css .token.string, .style .token.string,
  .token.entity, .token.operator, .token.url {
    background: transparent;
  }

  /* coyテーマ用。coyは背景・枠・紙めくれの影を <pre> ではなく
     「その中の <code>」と ::before/::after に置くので、上の打ち消しが
     届かない（白い紙のまま薄い文字が乗る）。左の青い縦線はcoyの
     見どころなので残し、白地と影だけを暗い側へ寄せる。 */
  pre[class*="language-"][class*="language-"] > code {
    background-color: var(--code-bg, #161b22);
    background-image: none;
    box-shadow: -1px 0 0 0 #358ccb, 0 0 0 1px var(--border, #30363d);
  }
  pre[class*="language-"][class*="language-"]::before,
  pre[class*="language-"][class*="language-"]::after {
    box-shadow: none;
  }
  :not(pre) > code[class*="language-"][class*="language-"] {
    border-color: var(--border, #30363d);
  }
}
"""

NO_COPY_CSS = """
/* ==== wikiSystem追加分: nocopy（コピーボタンの個別非表示） ====
   Prismのcopy-to-clipboardには、ブロック単位で自身を止める仕組みが元から
   無い（toolbarへの登録を解除するAPIが公開されていない）。JSを改造する
   代わりに、toolbarプラグインが組み立てるDOM構造（<pre>とtoolbarのdivが
   同じ.code-toolbar内の兄弟要素になる）を利用し、一般兄弟結合子(~)で
   コピー用ボタンだけをCSSで狙って隠す。<pre data-no-copy>を付けた
   ブロックだけに効く（#codeプラグインのnocopy引数から使う、属性名は
   wikiPlugin側の提案）。 */
pre[data-no-copy] ~ .toolbar .copy-to-clipboard-button {
  display: none;
}
"""

AUTOLOADER_JS = """
/* wikiSystem追加分: autoloaderの取得先をjsdelivr（このビルドと同じ
   バージョン）に固定する。既定は「自分自身のスクリプトURLから相対的に
   components/を類推する」動きだが、1ファイルに連結したcode.jsのURL
   （/.plugin/code.js）では存在しないパスを類推してしまうため。 */
if (typeof Prism !== "undefined" && Prism.plugins && Prism.plugins.autoloader) {
  Prism.plugins.autoloader.languages_path =
    "https://cdn.jsdelivr.net/npm/prismjs@%s/components/";
}
""" % VERSION

LINE_NUMBERS_DEFAULT_JS = """
/* wikiSystem追加分: 行番号を既定でON にする（Wiki設計者の指示、2026-08-29）。
   line-numbersプラグイン自身は`Prism.util.isActive(要素, "line-numbers")`
   でON/OFFを決めている。これは要素からdocumentまで祖先を遡り、途中に
   class="line-numbers"があればON、class="no-line-numbers"があればOFF、
   どちらも無ければ既定値（第3引数、省略時false）を返す仕組み
   （Prism本体の実装済みの機能で、wikiSystem側で新たに作った仕組みでは
   ない）。<html>にline-numbersを付けて全体の既定をONにすれば、個別に
   OFFにしたい<pre>にだけclass="no-line-numbers"を付ければ、そちらが
   祖先を遡る途中で先に見つかり優先される。#codeのnonumはこの
   class="no-line-numbers"を使う想定（wikiPlugin側に伝達済み）。 */
if (typeof document !== "undefined") {
  document.documentElement.classList.add("line-numbers");
}
"""

PUKIWIKI_LANG_JS = r"""
/* wikiSystem追加分: PukiWiki記法の言語定義（Wiki設計者の指示、2026-09-03）。
   `#code(pukiwiki){{ }}` や ```pukiwiki で、PukiWiki記法のコード例が
   Markdownとして誤って色付けされるのを防ぐ。Prismが配っている言語には
   PukiWikiが無いため、こちらで定義する（wikiPluginセッションによる作成）。

   各トークンは、本家PukiWikiの一般論ではなく**このシステムが実際に
   解釈する記法**（`_sys/wikilib/pukiwiki.py` の HEADING_RE・HR_RE・
   LIST_RE・QUOTE_RE・TABLE_RE・DEFLIST_RE・PLUGIN_BLOCK_RE・INLINE_RE・
   NUMREF_AMP_RE・match_amp_token）を典拠にしている。並び順にも意味が
   あり、Prismは上から順に当てるため、長いほうを先に置く必要がある
   （hr の `----` はlistの `-` より先、em の `'''` はstrong の `''` より先、
   ins の `%%%` はstrike の `%%` より先。pukiwiki.py の INLINE_RE が
   同じ順で並べているのと同じ理由）。

   色は alias でPrism標準の語彙に寄せてあるので、テーマを差し替えても
   （既定の coy に限らず）それらしく色分けされる。追加のCSSは要らない。

   複数行にまたがるプラグイン本体（`{{ … }}` の中身）は色分けの対象外
   （行ベースの正規表現の都合。呼び出し行そのものは色が付く）。 */
Prism.languages.pukiwiki = {
  'comment': {
    pattern: /^\/\/.*/m,
    greedy: true,
  },
  'plugin-block': {
    // #name(args){body} / #name(args){{ … （pukiwiki.py PLUGIN_BLOCK_RE）
    pattern: /^#[A-Za-z_][\w-]*(?:\([^)]*\))?(?:\{\{+|\{[^{}]*\})?/m,
    alias: 'function',
    inside: {
      'punctuation': /^#|[(){}]/,
    },
  },
  'heading': {
    // *見出し / **見出し / ***見出し（pukiwiki.py HEADING_RE）
    pattern: /^\*{1,3}(?!\*).*/m,
    alias: 'important',
  },
  'hr': {
    // ----（4つ以上のハイフン。pukiwiki.py HR_RE）
    pattern: /^-{4,}[ \t]*$/m,
    alias: 'punctuation',
  },
  'list': {
    // -項目 / --項目 / +項目 等（pukiwiki.py LIST_RE）
    pattern: /^[-+]{1,3}(?![-+])/m,
    alias: 'punctuation',
  },
  'quote': {
    // >引用 / >>引用（pukiwiki.py QUOTE_RE）
    pattern: /^>{1,3}/m,
    alias: 'comment',
  },
  'table-row': {
    // |セル|セル|（末尾のh/f/c任意。pukiwiki.py TABLE_RE）
    pattern: /^\|.+\|[hHfFcC]?$/m,
    inside: {
      'punctuation': /\|/,
    },
  },
  'deflist': {
    // :項目名|説明文（pukiwiki.py DEFLIST_RE）
    pattern: /^:.*?\|/m,
    alias: 'punctuation',
  },
  'plugin-inline': {
    // &name(args){body}; / &name;（pukiwiki.py match_amp_token）
    pattern: /&[A-Za-z_][\w-]*(?:\([^()]*\))?(?:\{[^{}]*\})?;/,
    alias: 'function',
    inside: {
      'punctuation': /[&(){};]/,
    },
  },
  'charref': {
    // &#10進数; / &#x16進数;（pukiwiki.py NUMREF_AMP_RE）
    pattern: /&#(?:[0-9]+|[xX][0-9A-Fa-f]+);/,
    alias: 'symbol',
  },
  'em': {
    // '''強調（斜体扱い）'''（pukiwiki.py INLINE_RE、em＝3連クォート）
    pattern: /'''.+?'''/,
    alias: 'italic',
  },
  'strong': {
    // ''強調（太字扱い）''（pukiwiki.py INLINE_RE、strong＝2連クォート）
    pattern: /''.+?''/,
    alias: 'bold',
  },
  'ins': {
    pattern: /%%%.+?%%%/,
    alias: 'inserted',
  },
  'strike': {
    pattern: /%%.+?%%/,
    alias: 'deleted',
  },
  'link': {
    // [[表示名:URL]] / [[表示名>ページ名]] 等（pukiwiki.py INLINE_RE、link）
    pattern: /\[\[[^\[\]]+\]\]/,
    alias: 'string',
    inside: {
      'punctuation': /\[\[|\]\]/,
    },
  },
  'url': {
    pattern: /(?:https?|ftp|news):\/\/[^\s<>"']+/,
    alias: 'url',
  },
  'email': {
    pattern: /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/,
    alias: 'url',
  },
  'wikiname': {
    // WikiName（大文字始まりの単語が2つ以上続く。pukiwiki.py INLINE_RE、wikiname）
    pattern: /(?:[A-Z][a-z]+){2,}(?!\w)/,
    alias: 'class-name',
  },
};
"""

MARKDOWN_PLUGIN_JS = r"""
/* wikiSystem追加分: Prism標準のmarkdown言語定義に、このシステム独自の
   Markdown拡張（プラグイン記法 #name(args){body} / &name(args){body}; ）の
   認識を足す（Wiki設計者の指示、2026-09-03。wikiPluginセッションによる作成）。

   Prism標準のATX見出し（title規則、pattern: /(^\s*)#.+/m）は**「#」の直後に
   空白が無くてもマッチする**ため、`#code(){{ … }}` のようなプラグイン呼び出しが
   見出しとして誤って色付けされていた。`&name(args);` のほうも、markdownの
   土台であるmarkup言語から継承した汎用のentity規則（`&amp;` 等）に紛れて
   拾われる形だった。

   このシステムのMarkdown側の判定（`_sys/wikilib/plugins.py` の
   PLUGIN_BLOCK_HEAD_RE = r'^#([A-Za-z_][\w\-]*)\(' ・
   PLUGIN_INLINE_HEAD_RE = r'&([A-Za-z_][\w\-]*)\(([^()]*)\)'）は
   **丸括弧を必須にしている**ので、同じ条件の規則を`title`より前へ挿し込めば、
   本来のATX見出し（`#`の後に空白）とも、本物の文字実体参照（名前の直後が
   丸括弧になることはない）とも自然に区別できる。既存の見出し判定・
   entity判定はそのまま残る。

   PukiWiki記法側（Prism.languages.pukiwiki）は括弧を省ける別の判定なので、
   こちらとは分けてある（pukiwiki.py の PLUGIN_BLOCK_RE は括弧が任意）。 */
Prism.languages.insertBefore('markdown', 'title', {
  'plugin-block': {
    // #name(args){body} / #name(args){{ …（plugins.py PLUGIN_BLOCK_HEAD_RE）
    pattern: /^#[A-Za-z_][\w-]*\([^)]*\)(?:\{\{+|\{[^{}]*\})?/m,
    alias: 'function',
    inside: {
      'punctuation': /^#|[(){}]/,
    },
  },
  'plugin-inline': {
    // &name(args){body};（plugins.py PLUGIN_INLINE_HEAD_RE）
    pattern: /&[A-Za-z_][\w-]*\([^()]*\)(?:\{[^{}]*\})?;/,
    alias: 'function',
    inside: {
      'punctuation': /[&(){};]/,
    },
  },
});
"""




def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def topo(ids, table):
    """require→先、modify対象（一覧に有る場合のみ）→先、の順を守った並び順にする。"""
    order = []
    seen = set()
    ids_set = set(ids)

    def visit(name):
        if name in seen:
            return
        seen.add(name)
        entry = table.get(name) or {}
        for dep in as_list(entry.get("require")):
            visit(dep)
        for dep in as_list(entry.get("modify")):
            if dep in table and dep in ids_set:
                visit(dep)
        order.append(name)

    for name in ids:
        visit(name)
    return order


def scope_selectors(css_text, prefix):
    """flatな（@ルールを含まない）CSSの各ルールの、セレクタ全部の前に
    `prefix `（子孫結合子）を付けてスコープする。

    show-invisiblesのように「読み込むだけで全コードブロックに常時効いて
    しまう」プラグインCSSを、`<pre>`側のクラスが有るときだけ効くように
    後付けで狭めるための変換(SCOPED_PLUGIN_CSS参照)。"""
    def repl(m):
        selectors, decls = m.group(1), m.group(2)
        scoped = ",".join(f"{prefix} {sel.strip()}" for sel in selectors.split(","))
        return f"{scoped}{{{decls}}}"
    return re.sub(r"([^{}]+)\{([^{}]*)\}", repl, css_text)


# Prismのプラグインには「ブロック単位のON/OFFが無く、読み込むだけで
# 全コードブロックに常時効く」ものがある。show-invisiblesがそれで、
# 読み物用途では主張が強すぎるとの指摘（Wiki設計者・wikiPluginセッション、
# 2026-08-29）を受け、他のプラグイン（line-numbers等）と足並みを揃えて
# `<pre>`側のクラスで個別にON/OFFできるよう、CSSだけをスコープする
# （JS側の登録・トークン付与そのものは変えていない。DOMに常に
# `<span class="token space">`等は付くが、CSSが無ければ見た目に出ない）。
SCOPED_PLUGIN_CSS = {
    "show-invisibles": "pre.show-invisibles",
}


def fetch_text(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            print(f"  retry ({e}): {url}")
            time.sleep(1)
    raise RuntimeError(f"failed to fetch {url}")


def main():
    print(f"fetching components.json (prismjs@{VERSION}) ...")
    components = json.loads(fetch_text(BASE + "components.json"))

    lang_order = topo(LANGS, components["languages"])
    plugin_order = topo(PLUGINS, components["plugins"])
    plugin_meta = components["plugins"]

    js_parts = [
        "/* Prism.js {v} ({theme}テーマ + 言語{nl}種 + プラグイン{np}種)\n"
        "   theme/prism.build.py で自動生成。手で直接編集しないこと。\n"
        "   plugin/codeプラグインの資材として、そのページで#codeが実際に\n"
        "   使われたときだけ読み込まれる（context.used_plugins参照）。 */\n".format(
            v=VERSION, theme=THEME, nl=len(LANGS), np=len(PLUGINS)),
    ]
    css_parts = [
        f"/* Prism.js {VERSION} テーマ({THEME})+プラグインCSS 自動生成（同上） */\n",
    ]

    print("fetching core ...")
    js_parts.append(fetch_text(BASE + "components/prism-core.min.js"))

    for lang in lang_order:
        print(f"fetching language: {lang}")
        js_parts.append(fetch_text(BASE + f"components/prism-{lang}.min.js"))

    # 既定テーマだけファイル名が themes/prism.min.css で、それ以外は
    # themes/prism-<名前>.min.css（配布物の命名。ここを揃えて書くと
    # 404になる）
    theme_file = "prism" if THEME == "prism" else f"prism-{THEME}"
    print(f"fetching theme: {THEME} ({theme_file}.min.css)")
    css_parts.append(bump_specificity(fetch_text(BASE + f"themes/{theme_file}.min.css")))

    for plug in plugin_order:
        print(f"fetching plugin: {plug}")
        js_parts.append(fetch_text(BASE + f"plugins/{plug}/prism-{plug}.min.js"))
        if not plugin_meta.get(plug, {}).get("noCSS"):
            css = bump_specificity(
                fetch_text(BASE + f"plugins/{plug}/prism-{plug}.min.css"))
            if plug in SCOPED_PLUGIN_CSS:
                css = scope_selectors(css, SCOPED_PLUGIN_CSS[plug])
            css_parts.append(css)

    js_parts.append(AUTOLOADER_JS)
    js_parts.append(LINE_NUMBERS_DEFAULT_JS)
    js_parts.append(PUKIWIKI_LANG_JS)
    js_parts.append(MARKDOWN_PLUGIN_JS)
    css_parts.append(THEME_RESET_CSS)
    css_parts.append(DARK_MODE_CSS)
    css_parts.append(NO_COPY_CSS)

    os.makedirs(PLUGIN_DIR, exist_ok=True)
    with open(os.path.join(PLUGIN_DIR, "code.js"), "w", encoding="utf-8") as f:
        f.write("\n".join(js_parts))
    with open(os.path.join(PLUGIN_DIR, "code.css"), "w", encoding="utf-8") as f:
        f.write("\n".join(css_parts))

    print("done: plugin/code.js, plugin/code.css")


if __name__ == "__main__":
    main()
