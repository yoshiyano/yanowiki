"""日本語の中の `**強調**` が効かない件をゆるめる（Wiki設計者の指示、2026-09-06）。

## 何が起きていたか

CommonMark（markdown-it）は、`*` の並びが**開き側になれるか・閉じ側に
なれるか**を、前後の文字の種類（空白・約物・それ以外）で決める。この決めかたは
**単語のあいだに空白が入る言語**を前提にしているので、空白を使わない日本語では
本来効いてほしい書きかたが落ちる。

    文言に**「ロックまで残りn回」**を添えます     ← 効かない
    テキスト**「かぎかっこ」**つづき              ← 効かない

落ちるのは、`**` の外側が**全角の文字や約物**のとき。実際に踏んだのは次の2つ。

    文言に**「ロックまで残りn回」**を添えます     開き側の直後が「
    - **癖。**WDT のタイムアウトが…             閉じ側の直前が。で、直後が半角英字

CommonMarkは、`*` の外側が約物かどうかで開き・閉じを決める。約物の隣に置いた
`*` は「その反対側が空白か約物でなければ」開き（閉じ）になれない、という
決まりで、**空白で単語を切る言語なら妥当**だが、日本語では切れ目に空白が
無いので落ちてしまう。

## どうゆるめたか

**`*` の外側が全角の文字・約物なら、開き側（閉じ側）になれることにする。**

    直後が全角なら  → 開き側になれる
    直前が全角なら  → 閉じ側になれる

上の1つ目は直後が `「` なので開き側に、2つ目は直前が `。` なので閉じ側に
なれる。JavaScript側の `markdown-it-cjk-friendly` と同じ考えかたで、
**ゆるめる方向にしか動かさない**——もともと開き（閉じ）になれたものを
なれなくすることはしないので、英語まじりの文や既に効いていた書きかたの
結果は変わらない（`tests/test_cjkemphasis.py` でそこも固定してある）。

## 全体に効く

`markdown_it` の `StateInline.scanDelims` を差し替えるので、**この処理系で
描くものすべて**に効く（Wikiごとの設定にはしていない）。設定で切り替えられる
形にするには、Wikiごとに別の処理系を組み立てる必要があり、そこまでの
釣り合いが取れないと判断した。**ゆるめる方向にしか変わらない**——いままで
効いていた強調が効かなくなることは無い。
"""
from markdown_it.common.utils import isMdAsciiPunct, isPunctChar, isWhiteSpace
from markdown_it.rules_inline.state_inline import Scanned, StateInline

# 全角として扱う文字の範囲。**全角の空白（U+3000）は入れない**——あれは
# 空白として判定されるべきもので、約物や文字と同じ扱いにすると話が変わる。
CJK_RANGES = (
    (0x1100, 0x11FF),    # ハングル字母
    (0x2E80, 0x2EFF),    # 漢字の部首
    (0x3001, 0x303F),    # 全角の約物（、。「」『』〜 など）
    (0x3041, 0x30FF),    # ひらがな・カタカナ
    (0x3105, 0x312F),    # 注音符号
    (0x3131, 0x318E),    # ハングル互換字母
    (0x31A0, 0x31BF),    # 注音符号（拡張）
    (0x31F0, 0x31FF),    # カタカナ（拡張）
    (0x3400, 0x4DBF),    # 漢字（拡張A）
    (0x4E00, 0x9FFF),    # 漢字
    (0xA960, 0xA97F),    # ハングル字母（拡張A）
    (0xAC00, 0xD7A3),    # ハングル
    (0xF900, 0xFAFF),    # 漢字（互換）
    (0xFE10, 0xFE1F),    # 縦書き用の約物
    (0xFF01, 0xFF9F),    # 全角の英数・記号と、半角カタカナ
    (0xFFA0, 0xFFDC),    # 半角ハングル
    (0xFFE0, 0xFFE6),    # 全角の通貨記号など
    (0x20000, 0x3FFFD),  # 漢字（拡張B以降）
)


def is_cjk(char):
    """この文字は全角か（開き・閉じをゆるめる判断に使う）。

    **全角の空白は含めない**（`CJK_RANGES` の断りを参照）。"""
    if not char:
        return False
    code = ord(char)
    if code < 0x1100:      # ASCIIとラテン文字。ここが大半なので先に落とす
        return False
    for low, high in CJK_RANGES:
        if low <= code <= high:
            return True
    return False


def _scan_delims(self, start, canSplitWord):
    """`StateInline.scanDelims` の差し替え。

    もとの実装（markdown_it 4.2.0）のまま数え、**開き・閉じになれるかの
    判定を1段ゆるめて**返す。ゆるめるのは真にする側だけなので、もともと
    開き（閉じ）になれたものが、なれなくなることはない。"""
    pos = start
    maximum = self.posMax
    marker = self.src[start]

    # 行頭は空白と同じ扱い
    last_char = self.src[start - 1] if start > 0 else " "

    while pos < maximum and self.src[pos] == marker:
        pos += 1

    count = pos - start

    # 行末も空白と同じ扱い
    next_char = self.src[pos] if pos < maximum else " "

    is_last_punct = isMdAsciiPunct(ord(last_char)) or isPunctChar(last_char)
    is_next_punct = isMdAsciiPunct(ord(next_char)) or isPunctChar(next_char)

    is_last_space = isWhiteSpace(ord(last_char))
    is_next_space = isWhiteSpace(ord(next_char))

    left_flanking = not (
        is_next_space or (is_next_punct and not (is_last_space or is_last_punct))
    )
    right_flanking = not (
        is_last_space or (is_last_punct and not (is_next_space or is_next_punct))
    )

    # ここだけが元の実装との違い。**外側が全角なら、開き（閉じ）になれる**
    # ことにする（モジュール冒頭参照）。真にする側にしか動かさない
    if is_cjk(next_char):
        left_flanking = True
    if is_cjk(last_char):
        right_flanking = True

    can_open = left_flanking and (canSplitWord or (not right_flanking) or is_last_punct)
    can_close = right_flanking and (canSplitWord or (not left_flanking) or is_next_punct)

    return Scanned(can_open, can_close, count)


def install():
    """差し替えを効かせる。**何度呼んでもよい。**"""
    if getattr(StateInline.scanDelims, "_cjk_friendly", False):
        return False
    _scan_delims._cjk_friendly = True
    StateInline.scanDelims = _scan_delims
    return True
