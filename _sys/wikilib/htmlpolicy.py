"""本文に書かれた生HTMLを、どこまで通すか（`allow_html`）。

## 3つの方針

設定（`markdown.allow_html` / `pukiwiki.allow_html`）は3つの値をとる。

    false（既定）  一切通さない。書いたHTMLは文字としてそのまま出る
    true           **許可したタグ・属性だけ**通す。危ないものは文字にする
    all            すべて通す（2026-09-02より前の挙動）

**既定を false にしたのは、素通しが保存型XSSになるため**（Wiki設計者の指示、
2026-09-02）。編集できる人なら `<script>` や `onerror=` をページに置ける
状態だった。

## 何を落とすか

**XSSに関わりうるものは落とし、関わらないものは通す**（Wiki設計者の判断）。
落とす側は、一般的なサニタイザ（GitHubのMarkdown描画・DOMPurifyの既定）と
同じ顔ぶれにしてある。

    script / style / iframe / object / embed / link / meta / base
    form / input / button / textarea / select
    on… で始まる属性（onclick 等）
    href / src の javascript: data: vbscript: …（http/https/mailto/相対だけ通す）
    style 属性

`<style>` と `style` 属性を落とすのは、**スクリプトが無くても実害を出せる**
ため。位置指定で編集ボタンの上に別の要素を重ねる、偽の入力欄に見せかける、
属性セレクタと `background:url()` で入力内容を外へ送る、といったことがCSS
だけでできる。ページ全体（テーマのヘッダやメニュー）にも効いてしまう。

`form` 系を落とすのは、偽の入力欄で認証情報を集める形を防ぐため。

`class` / `id` は落とさない。単体ではXSSに関わらず、テーマのCSSを当てる
書きかたが既にあるため。

## 落としたものは「消さず、文字にする」

許可されなかったタグは取り除かず、`&lt;script&gt;` のように文字として出す。
消してしまうと、書いた本人に何が起きたのか分からない。**false のときの
見えかたとも揃う。**

## プラグインが返したHTMLは通る

この濾し器がかかるのは、**本文に書かれたHTML**（`html_block` /
`html_inline` トークン）だけである。プラグインが返した文字列は
パーサーを通らないので（`plugins.call_plugin`）、`<div class="note…">` や
`<span style="color:red">` はこの方針に関わらずそのまま出る。

プラグインが受け取る中身（body）のほうは本文と同じ扱いで、この方針が効く。
"""
import re
from html import escape

NONE = "none"   # 一切通さない（false）
SAFE = "safe"   # 許可したものだけ通す（true）
ALL = "all"     # すべて通す（all）

# 通してよいタグ。表示のための要素だけを挙げ、動きや外部の読み込みに
# 関わるものは入れない
ALLOWED_TAGS = frozenset("""
    p br hr div span
    h1 h2 h3 h4 h5 h6
    ul ol li dl dt dd
    table thead tbody tfoot tr th td caption colgroup col
    b strong i em u s strike del ins mark small big
    sub sup code pre kbd samp var tt
    blockquote q cite abbr dfn time address
    details summary figure figcaption
    a img ruby rb rt rp wbr
""".split())

# どのタグにも付けてよい属性
GLOBAL_ATTRS = frozenset(["class", "id", "title", "lang", "dir"])

# タグごとに追加で認める属性
TAG_ATTRS = {
    "a": frozenset(["href", "target", "rel", "name"]),
    "img": frozenset(["src", "alt", "width", "height", "loading"]),
    "td": frozenset(["colspan", "rowspan", "align", "valign"]),
    "th": frozenset(["colspan", "rowspan", "align", "valign", "scope"]),
    "col": frozenset(["span"]),
    "colgroup": frozenset(["span"]),
    "ol": frozenset(["start", "reversed", "type"]),
    "li": frozenset(["value"]),
    "details": frozenset(["open"]),
    "time": frozenset(["datetime"]),
    "del": frozenset(["datetime"]),
    "ins": frozenset(["datetime"]),
    "blockquote": frozenset(["cite"]),
    "q": frozenset(["cite"]),
}

# URLとして受け取る属性。ここだけスキームを見る
URL_ATTRS = frozenset(["href", "src", "cite"])
# 通してよいスキーム。相対URL（スキームを持たないもの）は常に通す
SAFE_SCHEMES = frozenset(["http", "https", "mailto", "ftp", "tel"])
_SCHEME_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9+.\-]*)\s*:")

_ATTR_RE = re.compile(
    r"""([A-Za-z_:][A-Za-z0-9:._\-]*)      # 名前
        (?:\s*=\s*
           (?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))   # 値（"…" '…' 裸）
        )?""",
    re.X)
# 1つのタグ・コメント等。markdown_it.common.html_re と同じ顔ぶれ
_TAG_RE = re.compile(
    r"""<\/?[A-Za-z][A-Za-z0-9\-]*(?:\s[^<>]*)?>   # 開始・終了タグ
      | <!--[\s\S]*?-->                            # コメント
      | <![A-Za-z][^>]*>                           # 宣言
      | <\?[\s\S]*?\?>                             # 処理命令
      | <!\[CDATA\[[\s\S]*?\]\]>                   # CDATA
    """, re.X)
_TAG_NAME_RE = re.compile(r"^<(\/)?([A-Za-z][A-Za-z0-9\-]*)")


def html_policy(config, ext):
    """その記法での方針（none / safe / all）を返す。

    記法ごとに別の設定を見る。`.txt` は `pukiwiki.allow_html`、それ以外は
    `markdown.allow_html`。**書かれていなければ none**（安全側）。

    YAMLの `false` は真偽値、`all` は文字列で入ってくる。`true` は
    「許可したものだけ」の意味になる（2026-09-02に意味が変わった。
    それ以前の `true` ＝すべて通す は `all` に当たる）。"""
    from wikilib.render import is_pukiwiki
    section = "pukiwiki" if is_pukiwiki(ext) else "markdown"
    conf = (config or {}).get(section) or {}
    return normalize_policy(conf.get("allow_html", False))


def normalize_policy(value):
    """設定に書かれた値を none / safe / all のどれかに直す。

    読めない値は none にする（安全側に倒す。設定の書き損じで、意図せず
    素通しになるのを避けるため）。"""
    if value is True:
        return SAFE
    if value is False or value is None:
        return NONE
    text = str(value).strip().lower()
    if text == "all":
        return ALL
    if text in ("true", "safe", "yes", "on"):
        return SAFE
    return NONE


def resolve_policy(value, config, ext):
    """プラグインが指定した方針を、実際に使う方針に直す。

    `None`（指定なし）なら、そのページの設定（`allow_html`）に従う。
    値が書かれていれば、**そのページの設定に関わらず**その方針になる
    （Wiki設計者の指示、2026-09-02。プラグインは自分が渡すテキストを、どの水準で
    解釈させたいかを自分で決められる）。

    `wikilib.plugins` が中身（body）を展開するとき、プラグインが
    `PLUGIN_INFO["body_html"]` で宣言した値をここへ通す。自分で
    `build_expand_renderer` などを呼ぶプラグインは、その引数へ直に渡す。"""
    if value is None:
        return html_policy(config, ext)
    return normalize_policy(value)


def parses_html(policy):
    """パーサーに生HTMLを認識させるか（none なら認識させず、文字にする）。"""
    return policy in (SAFE, ALL)


def sanitize(fragment):
    """許可したタグ・属性だけを残した断片を返す。

    落としたタグは**消さずに文字**（`&lt;script&gt;`）へ変える。タグ以外の
    文字はそのまま通す（すでにエスケープ済みの本文がここへ来るため、
    二重エスケープしない）。"""
    out = []
    pos = 0
    for m in _TAG_RE.finditer(fragment):
        out.append(fragment[pos:m.start()])
        out.append(_clean_tag(m.group(0)))
        pos = m.end()
    out.append(fragment[pos:])
    return "".join(out)


def _clean_tag(tag):
    """タグ1つを、通すなら整えた形で、通さないなら文字にして返す。"""
    m = _TAG_NAME_RE.match(tag)
    if m is None:
        # コメント・宣言・CDATA など。中身を隠せるので通さない
        return escape(tag)
    closing, name = m.group(1), m.group(2).lower()
    if name not in ALLOWED_TAGS:
        return escape(tag)
    if closing:
        return "</%s>" % name

    allowed = GLOBAL_ATTRS | TAG_ATTRS.get(name, frozenset())
    kept = []
    body = tag[m.end():].rstrip(">").rstrip("/")
    for a in _ATTR_RE.finditer(body):
        attr = a.group(1).lower()
        if attr not in allowed:
            continue
        value = a.group(2)
        if value is None:
            value = a.group(3)
        if value is None:
            value = a.group(4)
        if value is None:
            kept.append(attr)          # 値なしの属性（open 等）
            continue
        if attr in URL_ATTRS and not _safe_url(value):
            continue
        kept.append('%s="%s"' % (attr, escape(value, quote=True)))
    selfclose = " /" if tag.rstrip().endswith("/>") else ""
    return "<%s%s%s>" % (name, (" " + " ".join(kept)) if kept else "", selfclose)


def _safe_url(value):
    """URLとして通してよいか。スキームを持たない（相対・アンカー）ものは通す。"""
    m = _SCHEME_RE.match(value.replace("\t", "").replace("\n", ""))
    if m is None:
        return True
    return m.group(1).lower() in SAFE_SCHEMES


def install(engine, policy=None):
    """描画時の濾し器を engine に取り付ける。

    生HTMLは `html_block`（かたまり）と `html_inline`（タグ1つ）の2種類の
    トークンになる。**PukiWiki側のパーサーも同じトークン型を出す**ので、
    この2つを差し替えれば両方の記法に効く。

    `policy` を渡すと**そのエンジンでは常にその方針**になる（プラグインが
    自分の渡すテキストの水準を決めた場合。plugins.build_expand_renderer）。
    渡さなければ、描画のたびにそのページの記法から決める——レンダラーは
    Markdown・PukiWikiの両方で使い回されるので（render.render_source）、
    取り付けるときに1つへ固定できないため。"""

    def render_html(self, tokens, idx, options, env):
        content = tokens[idx].content
        if policy is not None:
            return _apply(policy, content)
        context = (env or {}).get("wiki")
        if context is None:
            return escape(content)      # 素性が分からないときは通さない
        return _apply(html_policy(context.config, getattr(context, "ext", ".md")),
                      content)

    engine.add_render_rule("html_block", render_html)
    engine.add_render_rule("html_inline", render_html)
    return engine


def _apply(policy, content):
    """方針どおりに1つの断片を通す・絞る・文字にする。"""
    if policy == ALL:
        return content
    if policy == SAFE:
        return sanitize(content)
    # none。パーサーが認識していないはずなので、ふつうはここへ来ない
    return escape(content)
