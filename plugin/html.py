"""html — 中身をそのままHTMLとして表示する、ブロック・インライン両対応の
プラグイン。

    #html(){{
    <div class="custom-box">好きなHTMLをそのまま書けます</div>
    }}
    &html(){<b>強調</b>};
    #html(all){{
    <script>より強い権限が要る書きかた（後述）</script>
    }}

 1. all … 単語を書くと、タグ・属性を絞り込まずすべて通す
       (default: 書かない＝許可されたタグ・属性だけ通す)

中身にHTMLをそのまま書きます。**サイト全体の設定
（`markdown.allow_html`/`pukiwiki.allow_html`）がどのような値でも関係なく**、
このプラグインの中身は常に、少なくとも「許可されたタグ・属性だけ通す」水準
（設定でいう`true`）で表示されます。`all`を指定すると絞り込みをせずすべて
通します——**サイトの`allow_html`が`false`/`true`でも、`all`と書けば
その設定を上書きします。**

**`all`は強い権限です。** `<script>`・`<iframe>`・`onclick=`のような、
ページを開いた人に対して任意の動作をさせられる書きかたも素通りします。
書いてよいのは、その内容を自分で書いた・信頼できると確認できる場合だけに
してください。

中身は展開されません。Markdown記法・PukiWiki記法・他のプラグイン呼び出しを
書いても、リテラルな文字列としてそのまま扱われます（`&name();`のような
書きかたをしても、プラグインとしては呼ばれません）。
"""

""" 技術資料
本家PukiWikiに同名のプラグインは無いため、後方互換の制約を受けない
（`../CLAUDE.md`のPukiWiki互換方針は移植プラグインだけが対象）。

## 位置づけ: サイト設定（allow_html）から独立した、自前のHTML方針

2026-09-02、生HTML素通し（保存型XSS）対策として`markdown.allow_html`/
`pukiwiki.allow_html`の既定がfalseになり、本文に直接書いた生HTMLは
既定では一切通らなくなった（詳しくは`_sys/wikilib/htmlpolicy.py`）。

このプラグインは、**その方針とは独立に、常に自分自身の方針（既定は
`true`相当、`all`指定で`all`相当）でHTMLを通す**、意図的な抜け道として
新設した（Wiki設計者の指示）。**`allow_html`が低い権限のときに、あえてこの
プラグインで高い権限のHTMLを埋め込めるようにすることこそがこのプラグイン
の意図であり**（Wiki設計者の指示: 「allow_htmlの権限が低いときに、高い権限で
htmlを埋め込むのがhtmlプラグインの意図。本文に気軽に埋め込んだものでは
なく、意図して埋め込んだとするため」）、`#name(...)`という明示的な
プラグイン呼び出し自体が「気軽に紛れ込んだHTMLではなく、意図して埋め込んだ
HTML」の印になる。既定（`all`無し）は、それでも「不用意な事故——他所から
コピペしたHTMLに危険なタグが紛れる等——を防ぐ観点が大きい」という判断に
よる安全側フィルタ。`all`は`allow_html`の値を明示的に上書きする。サイトの
`allow_html`が`false`のWikiでも、`#html()`と書けば`true`相当のHTMLが、
`#html(all)`と書けば`allow_html`の設定を無視して無制限のHTMLが出る。

一方で、「無制限のHTMLをこのプラグイン経由でも一切入れさせたくない」
というサイト管理者のために、`all`の上限（`MAX_POLICY`）をそのWikiだけ
ローカルに絞れるようにしてある（下記参照）。

レビュー段階で、一時「`all`はそのWiki自身の`allow_html`設定が`all`の
ときだけ効く（`allow_html`が`all`を上回る）」という別案を試したが
（`allow_html`は管理者だけが変更できる設定なのに対し`all`はページ編集者
なら誰でも指定できてしまう、という懸念による）、Wiki設計者に直接確認した
結果、**「上書き」が意図どおりの設計であることが確定した。** そのWiki
だけ`all`自体を無効にしたい場合の手当ては、`allow_html`との連動ではなく
下記`MAX_POLICY`定数で行う。

## `expand_*`をいずれも宣言しない理由

中身はリテラルなHTML文字列であり、Markdown/PukiWiki記法として解釈されても
他のプラグイン呼び出しとして解釈されても困る（`katex.py`が数式の生テキストを
一切展開しないのと同じ考えかた）。`expand_block`/`expand_inline`/
`expand_plugin`をいずれも宣言しないため、`body`は`_convert`/`_inline`に
渡る前に一切加工されない（`wikilib.plugins.expand_body()`の対象外）。

## フィルタは自前実装せず`htmlpolicy.sanitize()`をそのまま使う

既定（`all`無し）の絞り込みは、本文の生HTML（`html_block`/`html_inline`
トークン）向けに`_sys/wikilib/htmlpolicy.py`が持つ`sanitize()`をそのまま
呼んで行う。許可タグ・許可属性・URLスキームの絞り込みを二重に持つと、
どちらかだけ直して他方が古いままになる事故が起きやすいため、単一の
実装を共有する。`sanitize()`は「許可されなかったタグは消さず文字にする」
という性質を持つため、このプラグインの出力もそれに揃う（書いた本人が
何が起きたか分かる）。

`sanitize()`は`html_block`/`html_inline`トークンの`content`（markdown-itが
「HTMLらしい」と認識した断片）を対象に作られており、「タグ以外の文字は
既にエスケープ済みとして扱い、二重エスケープしない」という前提がある
（詳しくは`htmlpolicy.py`のdocstring）。このプラグインの`body`はそうした
前処理を経ていない生の文字列だが、`sanitize()`内部のタグ検出
（`_TAG_RE`）はHTML5の実際のタグ開始判定（`<`の直後が英字・`/`・`!`・`?`
のいずれでもなければただの文字として扱う）と一致する作りのため、タグとして
認識されない`<`はブラウザ側でも同様にただの文字として扱われ、実害は無い
（`_clean_tag`のタグ名判定・属性の値のエスケープ・URLスキームの絞り込みは
すべてそのまま効く）。

`all`が実際に効くとき（`MAX_POLICY`がALLのとき）はフィルタを一切通さず、
`body`をそのまま返す。

## `_convert`/`_inline`が同じ実装である理由

ブロック・インラインで方針を変える理由が無い（本家に無い独自プラグインで、
挙動を分ける歴史的経緯も無い）ため、`_render()`に共通化してある。

## 中身を省略した場合

`body`が空・省略（`#html()`）なら`PluginArgumentError`にする（`katex.py`と
同じ判断。HTMLを書くためだけのプラグインで、空で呼ぶ用途が無いため）。

## `all`をそのWikiだけ無効にしたい場合（`MAX_POLICY`）

`all`は`allow_html`の値を上書きする設計のため、`allow_html`側では
`all`を止められない。**「このプラグインの`all`だけは常に無効にしたい」
というWikiがある場合**は、このファイルをそのWiki固有の`plugin/html.py`
（`wikidata/<farm名>/plugin/html.py`）へコピーし、冒頭の`MAX_POLICY`を
`ALL`から`SAFE`に書き換えればよい（「個別Wiki固有のプラグインが同名の
全Wiki共通プラグインを上書きする」という既存の仕組みをそのまま使う）。
これが、`all`という強い権限に対する**唯一の歯止め**になる。利用者
アカウント・権限の概念がこのシステムには無いため、「使ってよい人」を
プラグイン側で絞る仕組みは持たせられず、`MAX_POLICY`をALLのままにした
Wikiでは、実質的な歯止めは「そのページを編集できるかどうか」だけになる。

## 壊れたHTMLを書いた場合（`_TagBalancer`による補修）

閉じ忘れたタグをそのまま出すと、それ以降のページ表示（テーマのフッター等
も含む）まで巻き込んで崩れる。Web版の編集画面ならプレビューで気づけるが、
テキストエディタで平文ファイルを直接編集する使いかたでは、保存するまで
気づけない。**そのため「他に影響を及ぼさない程度」の簡易な補修だけは自動で
行う**（Wiki設計者の指示）。

`_TagBalancer`（`html.parser.HTMLParser`を使った軽量な実装）が、`sanitize()`
または`all`指定時の生テキストを最後にもう一度通し、次の2つだけを行う。

1. **終端まで開いたままのタグは、開いた順と逆順に閉じタグを補う。**
   `<div><span>text`のように書くと`<div><span>text</span></div>`になる
2. **対応する開始タグの無い閉じタグ（`</div>`だけを書いてしまった等）は
   黙って捨てる。** これを残すと、このプラグインの外側（周囲の本文や
   テーマの`<div>`）まで誤って閉じてしまう恐れがあるため

**HTML5の仕様が持つ「`<p>`は次のブロック要素で暗黙に閉じる」「`<li>`は
次の`<li>`で暗黙に閉じる」のような複雑な暗黙クローズ規則までは再現しない。**
あくまで「タグの対応が取れていない状態を、周囲に影響しない形に補う」だけの
簡易な処置であり、閉じかたの見た目（どこで閉じるか）まで本物のHTML5パーサー
と一致させることは目指していない。

`<script>`/`<style>`の中身は、タグとして解釈されない代わりに、閉じ忘れ補修の
際もエスケープしない（`RAW_TEXT_ELEMENTS`）。中の`<`/`>`をエスケープすると
JavaScript/CSSとして壊れるため。`html.parser.HTMLParser`自体が、この2要素の
中身をタグとして解釈しない仕組み（CDATA的な扱い）を標準で持っており、それに
乗る形で実装した。

このタグ対応の補修は、`all`の有無に関わらず両方に適用する（絞り込みの
有無とは別の関心事——「壊れたHTMLで周囲が壊れないようにする」ため）。
"""

from html import escape
from html.parser import HTMLParser

from wikilib.htmlpolicy import ALL, SAFE, sanitize
from wikilib.plugins import PluginArgumentError

PLUGIN_INFO = {
    "help": "#html(all){中身} / &html(all){中身};",
    "args": [
        {"name": "all", "flag": True, "default": False, "label": "絞り込みをしない"},
    ],
}

# このプラグインが許す`all`の上限（ALL または SAFE）。既定はALL＝`all`が
# そのWikiのallow_html設定を上書きする（allow_htmlが false/true でも常に
# 無制限になる。Wiki設計者の指示による意図的な設計）。このプラグイン自体の`all`を
# そのWikiだけ常に無効にしたい場合は、このファイルをそのWiki固有の
# plugin/html.pyへコピーし、ここをSAFEに書き換える（詳しくは技術資料）。
MAX_POLICY = ALL

# 閉じタグが要らない要素（HTML5の void element一覧）。スタックに積まない。
VOID_ELEMENTS = frozenset("""
    area base br col embed hr img input link meta param source track wbr
""".split())
# 中身をタグとして解釈しない要素。閉じ忘れの自動補完でも中身をエスケープしない
# （<script>の中の "<" 等をエスケープすると中身が壊れるため）。
RAW_TEXT_ELEMENTS = frozenset(["script", "style"])


class _TagBalancer(HTMLParser):
    """開いたまま終端まで来たタグを閉じ、対応する開始タグの無い閉じタグは
    捨てる、簡易的な補修器（詳しくは技術資料）。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out = []
        self._stack = []
        self._raw_text_tag = None

    def handle_starttag(self, tag, attrs):
        self._out.append(self.get_starttag_text())
        if tag in RAW_TEXT_ELEMENTS:
            self._raw_text_tag = tag
        if tag not in VOID_ELEMENTS:
            self._stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self._out.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag not in self._stack:
            return  # 対応する開始タグが無い。周囲を誤って閉じないよう捨てる
        while self._stack[-1] != tag:
            self._out.append(f"</{self._stack.pop()}>")
        self._stack.pop()
        self._out.append(f"</{tag}>")
        if tag == self._raw_text_tag:
            self._raw_text_tag = None

    def handle_data(self, data):
        self._out.append(data if self._raw_text_tag else escape(data, quote=False))

    def handle_comment(self, data):
        self._out.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self._out.append(f"<!{decl}>")

    def handle_pi(self, data):
        self._out.append(f"<?{data}>")

    def result(self):
        while self._stack:
            self._out.append(f"</{self._stack.pop()}>")
        return "".join(self._out)


def _close_unclosed_tags(html_text):
    parser = _TagBalancer()
    parser.feed(html_text)
    parser.close()
    return parser.result()


def _wants_all(resolved):
    """`all`引数が実際に効くか。MAX_POLICYがALLのときだけ真になる
    （そのWiki自身のallow_html設定は見ない。`all`はallow_htmlより強い、
    意図的な上書きのため。技術資料参照）。"""
    return bool(resolved["all"]) and MAX_POLICY == ALL


def _render(resolved, body):
    text = body or ""
    if not text.strip():
        raise PluginArgumentError("HTMLを指定してください: #html(){中身}")
    html_text = text if _wants_all(resolved) else sanitize(text)
    return _close_unclosed_tags(html_text)


def _convert(resolved, body, context):
    return _render(resolved, body)


def _inline(resolved, body, context):
    return _render(resolved, body)
