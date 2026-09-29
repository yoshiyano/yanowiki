# プラグイン

用意されているプラグインの一覧です。
呼びかた（`#name()` / `&name();` と引数の決まり）は [共通の書きかた](/Syntax/Common#プラグインの呼びかた)、
自分でつくるときは [プラグインの開発方法](/Tech/dev_plugin) をご覧ください。

## 用意されているプラグイン

### ブロックとして書くもの（`#name()`）

段落や見出しと同じく、1つのかたまりとして場所を取ります。行の始まりに `#` を置いて書きます。

| プラグイン | できること |
|---|---|
| [`#ac`](/Syntax/Plugin/ac) | 押すと開いたり閉じたりする、折りたたみの枠を作る |
| [`#aname`](/Syntax/Plugin/aname) | ページ内アンカー（リンクの飛び先）を設置する |
| [`#attachls`](/Syntax/Plugin/attachls) | ページに添付されたファイルの一覧を出す |
| [`#blockdiv`](/Syntax/Plugin/blockdiv) | 枠つきの箱を作り、段組みや回り込みに使う |
| [`#br`](/Syntax/Plugin/br) | 強制的に1行分の空白（改行）を入れる |
| [`#calendar`](/Syntax/Plugin/calendar) | 1か月のカレンダーを表示し、日ごとのページへ案内する |
| [`#calendar_edit`](/Syntax/Plugin/calendar_edit) | 全部の日付をリンクにしたカレンダーで、日ごとのページを作りながら使う |
| [`#calendar_read`](/Syntax/Plugin/calendar_read) | ページがある日だけリンクにしたカレンダーを表示する |
| [`#calendar_viewer`](/Syntax/Plugin/calendar_viewer) | 日ごとのページの中身を、まとめて表示する |
| [`#calendar2`](/Syntax/Plugin/calendar2) | 前後の月へ移れるカレンダーと、今日のページの中身を並べて表示する |
| [`#calendar3`](/Syntax/Plugin/calendar3) | 予定表のページに書いた予定を、月のカレンダーに並べて表示する |
| [`#clear`](/Syntax/Plugin/clear) | 画像などの回り込みを止める |
| [`#code`](/Syntax/Plugin/code) | Markdownのコードフェンスと同じHTMLで表示する |
| [`#comment`](/Syntax/Plugin/comment) | コメント投稿フォーム |
| [`#contents`](/Syntax/Plugin/contents) | そのページの見出し一覧（目次）を差し込む |
| [`#glossarytip`](/Syntax/Plugin/glossarytip) | ページ内の用語をtooltipで参照できるようにする |
| [`#hr`](/Syntax/Plugin/hr) | 水平線（区切り線）を引く |
| [`#html`](/Syntax/Plugin/html) | 中身をそのままHTMLとして表示する |
| [`#img`](/Syntax/Plugin/img) | 画像を差し込む |
| [`#include`](/Syntax/Plugin/include) | 別のページの本文をこのページに差し込む |
| [`#katex`](/Syntax/Plugin/katex) | LaTeX数式をKaTeXで表示する |
| [`#login`](/Syntax/Plugin/login) | ログイン・ログアウト・アカウント作成のフォームを置く |
| [`#ls`](/Syntax/Plugin/ls) | ページの一覧（リンク付き）を差し込む |
| [`#navi`](/Syntax/Plugin/navi) | 目次ページと子ページを行き来する送りを出す |
| [`#newpage`](/Syntax/Plugin/newpage) | ページ名を入れて新しいページを作る入力欄を置く |
| [`#note`](/Syntax/Plugin/note) | 中身を囲んで目立たせる |
| [`#pagediv`](/Syntax/Plugin/pagediv) | いくつかのページの本文を、枠に入れて縦横に並べて差し込む |
| [`#plugin_debug`](/Syntax/Plugin/plugin_debug) | ページの中だけ一時的にプラグインの詳細表示を切り替える |
| [`#popular`](/Syntax/Plugin/popular) | 人気ページの順位を差し込む |
| [`#pre`](/Syntax/Plugin/pre) | 整形済みテキスト（コード表示など）をそのまま表示する |
| [`#readauth`](/Syntax/Plugin/readauth) | そのページを閲覧できるユーザを限る |
| [`#recent`](/Syntax/Plugin/recent) | 最近更新されたページの一覧を差し込む |
| [`#ref`](/Syntax/Plugin/ref) | 添付ファイルを参照する |
| [`#viewable_period`](/Syntax/Plugin/viewable_period) | 指定した期間の外では、ページの本文を表示しない |
| [`#vote`](/Syntax/Plugin/vote) | 簡易投票（アンケート）フォームを置く |
| [`#writeauth`](/Syntax/Plugin/writeauth) | そのページを編集できるユーザを限る |

### インラインとして書くもの（`&name();`）

文の途中へ挟めます。末尾のセミコロン（`;`）を忘れないでください。
両方の書きかたがあるものは、どちらの表にも載せています（引数や中身の書きかたは同じです）。

| プラグイン | できること |
|---|---|
| [`&ac`](/Syntax/Plugin/ac) | 押すと開いたり閉じたりする、折りたたみの枠を作る |
| [`&aname`](/Syntax/Plugin/aname) | ページ内アンカー（リンクの飛び先）を設置する |
| [`&br`](/Syntax/Plugin/br) | 強制的に1行分の空白（改行）を入れる |
| [`&color`](/Syntax/Plugin/color) | 文字色・背景色を指定する |
| [`&html`](/Syntax/Plugin/html) | 中身をそのままHTMLとして表示する |
| [`&img`](/Syntax/Plugin/img) | 画像を差し込む |
| [`&katex`](/Syntax/Plugin/katex) | LaTeX数式をKaTeXで表示する |
| [`&login`](/Syntax/Plugin/login) | いま入っている人の表示名・IDを差し込む |
| [`&new`](/Syntax/Plugin/new) | 日付やページの更新が新しければ「New!」の印を付ける |
| [`&note`](/Syntax/Plugin/note) | 中身を囲んで目立たせる |
| [`&ref`](/Syntax/Plugin/ref) | 添付ファイルを参照する |
| [`&ruby`](/Syntax/Plugin/ruby) | 文字にふりがな（ルビ）を振る |
| [`&size`](/Syntax/Plugin/size) | 文字の大きさを指定する |

### 記法として働くもの

呼び出すのではなく、そのページで書きかたそのものを有効にします。

| プラグイン | できること |
|---|---|
| [`tasklist`](/Syntax/Plugin/tasklist) | チェックリストの記法を有効にする |

### ページには書かないもの

| プラグイン | できること |
|---|---|
| [`updateDB`](/Tech/UpdateDB) | 平文ファイルを直接書き換えたあと、その内容を表示・検索に取り込む（URL `/.plugin/updateDB` を開いて使う） |

一覧は手で並べています。プラグインを作ったら、ここにも1行足してください。

## エラーが出たときは

書きかたが違うときや、そのプラグインが無いときは、その場所だけが赤い枠のエラー表示になり、ページのほかの部分はふつうに表示されます。

#nosuchplugin()

枠の中の説明を確認してください。設定で `plugin.debug` が有効なら、詳しい情報も折りたたんで出ます。
よくある間違いは [共通の書きかた](/Syntax/Common#うまく動かないとき) にまとめてあります。
