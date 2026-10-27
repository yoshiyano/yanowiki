"""メニューページ（mainmenu・submenu）の箇条書きを、開け閉めできる形にする。

下の階層を持つ項目を `<details>` で包み、項目の記号で最初の状態を決める
（Wiki設計者の指示、2026-09-30「+ を(閉) - を(開) とした表現にしたい」）。

    - [書きかた](/Syntax)          開いた状態（<details open>）
      - [共通の書きかた](/Syntax/Common)
    + [プラグイン](/Syntax/Plugin)  閉じた状態（<details>）
      - [aname](/Syntax/Plugin/aname)

下の階層を持たない項目は、記号に関係なくこれまでどおり。項目の文字（リンク）が
`<summary>` になる。

## 分かれたリストをつなぎ直す

CommonMark では、記号が変わるとそこで別のリストになる（`-` の次に `+` が来ると
`<ul>` が2つに分かれる）。メニューでは記号を開け閉めの指定に使うので、同じ深さで
続いているリストは1つの `<ul>` につなぎ直す（設計者の確認「同一の ul に
まとめられるか」、2026-09-30）。

## 開け閉めの状態を覚える

閲覧者が開け閉めした状態は、ブラウザの localStorage に覚え、次のページを開いたときも
同じ状態で始める（`theme/common.js`）。深いページを続けて見るとき、ページを移るたびに
閉じ直されると辿りにくいため（設計者の指示「details の状態を cookie か localStorage に
保存してください」、2026-10-07）。

メニューは書き換えられるので、使えなくなった記録は捨てる（設計者の指示「menu は変更される
場合もあるので、使えなくなった情報は破棄する必要があります」、2026-10-07）。そのため
一番外の箇条書きに `data-menu-fold="<Wikiの入口>/<メニューのページ名>"` を付け、
common.js が「いまこのメニューにある項目」と覚えている記録を突き合わせて、
無くなった項目・記号の変更で最初の状態と同じになった項目の記録を消す。

## クロコの判断（設計者は未確認）

- 覚える場所は localStorage（設計者は cookie か localStorage のどちらでもよいとした）。
  開け閉めの状態はサーバーが使わないので、cookie にして全リクエストに載せる理由が無い
- 覚えるのは、最初の状態（`+`・`-`）から変えたものだけ。管理者が記号を書き換えたとき、
  閲覧者が触っていない項目は新しい最初の状態になる

- メニューのページだけに効かせる（`themes.render_menu`）。ふつうのページの `+` は、
  CommonMark どおりの箇条書きのまま（ほかの Markdown の処理系と表示を揃えるため）
- Markdown で書いたメニューだけ。PukiWiki記法の `+` は番号付きの箇条書き（`<ol>`）
  という別の意味を持つので、同じ規則を当てはめない
- `*` の項目は開け閉めしない（下の階層を常に見せる）

生のHTMLの断片ではなく `details`/`summary` のトークンを足すので、HTMLを許可
しない設定（`htmlpolicy`）でも同じように出る（タグ名を持つトークンは
markdown-it の `renderToken` がそのまま描く）。
"""
from markdown_it.token import Token

MENU_ID_ATTR = "data-menu-fold"  # 一番外の <ul> に付ける。覚えた状態をメニューごとに分ける目印
CLOSED_MARK = "+"  # 最初は閉じておく
OPEN_MARK = "-"    # 最初から開いておく
FOLD_CLASS = "menu-fold"  # 開け閉めする項目の <li> に付ける（見た目は theme/common.css）


def fold_menu_lists(tokens, menu_id=""):
    """トークン列を組み替えて返す（元の列は変えない）。

    `menu_id` があれば、一番外の箇条書きに `data-menu-fold` として付ける。開け閉めを
    覚える側（common.js）が、メニューごとに記録を分け、変わったメニューの古い記録を
    捨てるための目印で、メニューのページごとに違う値にする。"""
    out = _add_details(_merge_adjacent_lists(tokens))
    if menu_id:
        for token in out:
            if token.type == "bullet_list_open" and token.level == 0:
                token.attrSet(MENU_ID_ATTR, menu_id)
    return out


def _merge_adjacent_lists(tokens):
    """同じ深さで続く箇条書き（`</ul>` の直後の `<ul>`）を1つにつなぐ。"""
    out = []
    for token in tokens:
        if (token.type == "bullet_list_open" and out
                and out[-1].type == "bullet_list_close" and out[-1].level == token.level):
            out.pop()  # 前のリストを閉じずに、そのまま続ける
            continue
        out.append(token)
    return out


def _add_details(tokens):
    """下の階層を持つ項目を <details><summary>…</summary>…</details> で包む。"""
    out = []
    stack = []  # 開いている項目ごとに [開きのトークン, 包んだか]
    for token in tokens:
        if token.type == "list_item_open":
            out.append(token)
            stack.append([token, False])
            continue
        if stack and not stack[-1][1] and token.type in ("bullet_list_open", "ordered_list_open") \
                and token.level == stack[-1][0].level + 1:
            item = stack[-1][0]
            if item.markup in (CLOSED_MARK, OPEN_MARK):
                # 項目の文字を <summary> に入れる（開きの直後から、ここまで）
                start = len(out) - 1 - out[::-1].index(item)
                item.attrJoin("class", FOLD_CLASS)  # 点の代わりに三角を出す（common.css）
                details = Token("menu_details_open", "details", 1, block=True)
                if item.markup == OPEN_MARK:
                    details.attrSet("open", "")
                out[start + 1:start + 1] = [details,
                                            Token("menu_summary_open", "summary", 1)]
                out.append(Token("menu_summary_close", "summary", -1, block=True))
                stack[-1][1] = True
        if token.type == "list_item_close" and stack:
            _item, wrapped = stack.pop()
            if wrapped:
                out.append(Token("menu_details_close", "details", -1, block=True))
        out.append(token)
    return out
