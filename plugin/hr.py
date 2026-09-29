"""hr — 水平線（区切り線）を1本挿入する、ブロック専用のプラグイン。

    #hr()

引数はありません。段落の間に横線を1本引いて区切りたいときに使います。
"""

""" 技術資料
本家PukiWikiの`hr.inc.php`を移植した。**本家のソースがこの環境に無く、
記憶（学習データ）を頼りに移植した箇所である**（`../README.md`の
「本家PukiWikiのソースはローカルに無い」参照。確認できていないことを
明記する）。

記憶している本家`hr.inc.php`は`plugin_hr_convert()`が`<hr>`を返すだけの
非常に単純な実装で、引数は一切取らない。`plugin_hr_inline()`は無く
（`clear.inc.php`と同じ、水平線という性質上ブロック専用と判断した）、
このシステムでも`_inline`は定義していない（`&hr();`と書くと「このプラグイン
はインライン記法に対応していません」になる。`clear.py`と同じ扱い）。

**`class="short_line"`を付ける（Wiki設計者の指示）。** 本家は、ページ本文に
直接`----`（`-`4つ）と書く記法でも水平線が引けるが、こちらは無印の
`<hr>`を返す。`#hr()`プラグインはそれとは別の書きかたとして区別され、
`<hr class="short_line">`を返す（このシステムでも、Markdown記法の
`---`・PukiWiki記法の`----`はどちらも無印`<hr />`のままで、`#hr()`だけが
`short_line`クラス付きになる）。

見た目は、本家PukiWiki既定スキンの`pukiwiki.css`にある`.short_line`の
CSS（Wiki設計者の提供）を`plugin/hr.css`へそのまま移植した。

```css
hr.short_line {
  text-align: center;
  width: 80%;
  border-style: solid;
  border-color: #333333;
  border-width: 1px 0;
}
```

`border-width: 1px 0`（上下だけ1px、左右0）で細い二重線のような見た目に
なる。`width: 80%`で幅を狭めても中央に寄る（実機で確認済み。`text-align:
center`自体はブロック要素の`<hr>`には効かないが、`<hr>`はブラウザの既定
UAスタイルシートに`margin-inline: auto`相当が元々含まれているため、幅を
100%未満にするだけで自動的に中央寄せになる。`text-align: center`は
実質的に無くても同じ見た目になる冗長な指定だが、本家のCSSをそのまま
移植する方針のため削らずに残した）。

もし本家`hr.inc.php`が実際には何らかの引数（太さ・幅等、古いHTML4の
`<hr size width noshade>`相当）を取っていた場合は、後方互換の観点から
追加の対応が必要になる。本家ソースを確認できる機会があれば見直すこと。
"""

PLUGIN_INFO = {
    "help": "#hr()",
}


def _convert(resolved, body, context):
    return '<hr class="short_line">'
