全 wiki 共通のテーマを配置するディレクトリです。
各wiki固有のテーマは wikidata/<farm名>/theme/ に配置します（同名ファイルはそちらが優先されます）。

使用するテーマは config/default.yaml の theme.name で指定します。
（共通の設定に、各wikiの config/default.yaml を重ねたものが使われます）

theme.name が tname のとき、通常は theme/tname.html（＋tname.css・tname.js）を
使いますが、theme/tname/ というフォルダがあれば、代わりにその中の
tname.html・tname.css・tname.js を使います（ファイル名の付けかたは変わりません）。
フォルダは「サブフォルダ」としてではなく、そのテーマ専用の置き場所として扱われます
（common.css 等、テーマ間で共有する資材は従来どおりフォルダの外から見つかります）。
複数ファイルを抱えるテーマを整理したいときに使う置きかたです。

## 作成・管理は wikiThemes で行います

テーマを作る・直す作業は、別のプロジェクト ../wikiThemes/ で行います。
ファイルの実体はこのディレクトリのままで、wikiThemes からはシンボリックリンクで
同じファイルを触ります。実体を動かさないのは、wikiSystem を別のPCへ持って
いったときに、それだけで動くようにしておくためです。

  wikiSystem/theme/base.html      ← 実体（Git管理）
  wikiThemes/base.html            → 上へのリンク

修正の記録は wiki の /Tech/ChangeLog/themes に残します（本体の更新履歴とは
分けています。直す人も、直す周期も違うため）。
テーマを直してコミットするときは、その記録を見てからコミット文を書きます。

## common.css / common.js — どのテーマでも読み込むもの

common.* には「テーマの作りに関わらず働くもの」だけを置いています。
目印は2通りあります。

(1) サーバーがどのテーマにも同じ形で渡すもの
  セクション編集   .content[data-editable]
  編集中の印       .content[data-draft] と、タイトル脇の {{ title_note }}
  目次の現在位置   .toc a[href^="#"]

(2) テーマがHTMLで用意する、決まったクラス名（検索）
  .search / .search-word / .search-scope / .search-submit
  .search-options（条件パネル）
  .page-search-nav / .page-search-prev / .page-search-next / .page-search-count
  .page-search-panel / .page-search-list / .page-search-more / .page-search-close

(2) は common.js が作るのではなく、テーマが置いたものに振る舞いを付ける関係です。
クラス名を合わせておけば、一から書いたテーマでも検索がそのまま使えます。
検索フォームを置かないテーマでは、何もしないだけなので問題ありません。

編集リンクと data-editable は必ず {% if editable %} で囲んでください。
editable はサーバーが決める1つの窓口で、閲覧者のそのページの編集の権限で
決まります（入口を一律に伏せる設定 theme.show_edit は 2026-09-29 に廃止）。

  <link rel="stylesheet" href="{{ theme_url }}/common.css">
  <script src="{{ theme_url }}/common.js"></script>

テーマを新しく作るときは、この2行を必ず入れてください。
入れ忘れると、そのテーマでだけ検索とセクション編集が使えなくなります（JSを忘れた場合）、
あるいは枠も色も付かない素のままで表示されます（CSSを忘れた場合）。

common.css の色は var(--名前, 既定値) の形で書いてあります。
テーマが変数を定義していればその配色になじみ、定義していなくても既定値で成立します。
common.css はテーマ自身のCSSより先に読み込むので、同名セレクタをテーマ側に書けば
後勝ちで上書きできます（プラグインCSSと同じ考えかた）。

common.css には [hidden] { display: none !important; } も入っています。
ブラウザ既定の [hidden] は作者スタイルの display 指定に負けるため、
display:flex 等を当てた要素が hidden で閉じなくなる、という落とし穴の手当てです。
テーマごとに :not([hidden]) で回避する必要はありません。

base.css のほうは base.html のページ構造（ヘッダ・2コラム・サイドバー等）の
見た目なので、base.html を継承しないテーマでは読み込みません。

## コードブロックのシンタックスハイライトは plugin/ 側にあります

Prism.js（コードブロックの色付け）は、以前はここに`prism.css`/`prism.js`
として置き、全ページ無条件に読み込んでいた。`#code`プラグインを使わない
ページにまで150KB超を配る無駄があったため、2026-08-29に
`plugin/code.css`・`plugin/code.js`（そのページで#codeが実際に使われた
ときだけ読み込まれる、既存のプラグイン資材読み込みの仕組みに乗せる形）へ
移した。詳しくは`plugin/README.txt`の「code.css / code.js」節を参照。
取得・連結する道具（`theme/prism.build.py`）はこれまでどおりここにある。

## 同梱しているテーマ

base   … 標準テーマ（青系）。サイドバー付き2コラム。
         base.html / base.css
         base.css は base.html のページ構造の見た目（検索は common.css へ移管済み）
         base.js   （common.js に加えて読み込む独自スクリプト。menu1の階層メニューを
                     details/summary に組み替えて開閉できるようにする）

fresh  … 薄緑系のすっきりしたサンプル。サイドバーは右。
         fresh.html （common/base.html を継承して差分だけ記述）
         fresh.css  （@import で base.css を土台にして色などを上書き）
         ※ JavaScript は common.js だけで足りるため fresh.js はありません

bloom  … 薄オレンジ系のゆったりしたサンプル。サイドバーはカード型。
         bloom.html （継承せず一から記述）
         bloom.css  （独立。細かい部品の見た目も自前で用意。
                     セクション編集は common.css との差分だけを書いている）
         bloom.js   （common.js に加えて読み込む独自スクリプト）

post_it_1 … PukiWiki（1.5系）の見た目を再現したテーマ。付箋風の外枠と
         クリーム色の見出し。
         post_it_1.html （継承せず一から記述）
         post_it_1.css  （独立）
         post_it_1.js   （Alt+E3連打で編集画面へ / スマホ幅のハンバーガー
                     メニュー）
         クラス名は pi- 接頭辞（.pi-all / .pi-container / .pi-base）。

pkwk   … post_it_1 を土台に、PukiWiki標準スキンの配色（#DDEEFF系）へ寄せた
         もの。ヘッダに画面上で見える編集リンク・編集ボタンは出さないが、
         画面に何も表示しない隠し操作（Alt+E3連打・Ctrl+Alt+ダブルクリック
         のセクション編集）は post_it_1 と同じく有効。検索・TopicPath・
         menu1/menu2・目次は残す。TitleとTopicPathはヘッダのロゴ右に縦積み。
         pkwk.html （post_it_1.html からヘッダの編集フォームの見た目部分を
                     外し、ロゴを追加したもの。#hidden-menu自体は残す）
         pkwk.css  （@import で post_it_1.css を土台に配色と見出しを上書き）
         pkwk.js   （post_it_1.js と同内容。Alt+E3連打とハンバーガー
                     メニューの両方を持つ）

pukiwiki_default … PukiWiki標準スキン（skin/pukiwiki.css）の見た目を base 継承で
         再現したもの。#DDEEFF系の配色、h1/h2は青背景、h3は4辺の細い
         ボーダー、h4は太い左ボーダー、monospace優先フォント。編集導線は
         base標準のまま。
         pukiwiki_default.html （common/base.html を継承。headerブロックを
                     上書きしロゴを追加、commandsはsuper()でbase標準のまま）
         pukiwiki_default.css  （@import で base.css を土台に上書き）
         ※ JavaScript は common.js だけで足りるため .js はありません

pkwk_wide … pukiwiki_default をコピーし、本文の最大幅の上限を外して画面の
         横幅全体を使うようにしたもの（左右のメニュー幅はそのまま、本文が
         伸びる）。それ以外の見た目・ヘッダ構成は pukiwiki_default と同じ。
         pkwk_wide.html （pukiwiki_default.html のコピー）
         pkwk_wide.css  （pukiwiki_default.css のコピー＋.layout の
                     max-width を none にする節）
         ※ コピーなので、pukiwiki_default への変更は自動では反映されない

## pkwk / pukiwiki_default のヘッダロゴについて

どちらもヘッダにロゴ画像を出す作り（pkwk は {{ theme_url }}/pkwk-logo.png、
pukiwiki_default / pkwk_wide は {{ theme_url }}/logo.png。pukiwiki_default だけ
テーマ名を付けない名前にしてある、Wiki設計者の指示 2026-09-19）だが、**画像そのものは theme/ に同梱していない。** 参考にした
サイトが使っていたロゴ（Python公式ロゴ／PukiWiki公式ロゴ）をそのまま
再配布すると商標・著作権の許容範囲を超えうるため（2026-09-03、
wikiSystem側からの指摘）で、これらの画像ファイルは
`wikidata/<farm名>/theme/` （gitignore対象、サイト固有の素材置き場）
に配置する運用にしている。

- テンプレート側の `<img>` は無条件参照（存在チェックはしていない）。
  テーマ資材はファーム固有の `wikidata/<farm名>/theme/` → この theme/ の
  順に探されるので、ファーム側に置いたロゴが優先される。
  （現状 `wikidata/sandbox/theme/` に本家ロゴのサンプルを置いてある）
- logo.png だけは、wikiSystem 自身のロゴをこの theme/ に置いてある。いまは
  本の木の図案（logo_booktree.png と同じ中身。2026-09-29 に Wiki設計者が差し替えた）。
  ファーム側に logo.png を用意していなければ、pukiwiki_default / pkwk_wide の
  ヘッダにはこれが出る。
  pkwk-logo.png は同梱していないので、pkwk を使うファームでは引き続き
  ファーム側に用意すること（無いと404で壊れた画像アイコンになる）。
- 自分の環境で本家の見た目を再現したい場合、ライセンス上問題ないと自分で
  判断できるロゴを同じファイル名で `wikidata/<farm名>/theme/` に置く。

### wikiSystem ロゴのバリエーション（logo*.png）

logo.png のほかは、どのテーマからも参照していない素材で、差し替えたいときに
ファーム側の theme/ へ logo.png の名前でコピーして使う想定。logo1〜5 は
_system トップの画像から切り出して背景を透過にしたもの。

  logo.png          256×256  既定のロゴ。logo_booktree.png と同じ中身
  logo_booktree.png 256×256  本の木（枝に開いた本が実る木）、透過背景。ヘッダの72×72表示用
  logo1.png         256×256  エンブレム（本と葉）、透過背景。2026-09-29 まで logo.png だったもの
  logo2.png         256×256  生成りの角丸バッジに入れたもの（暗いヘッダでも沈まない）
  logo3.png         256×256  深緑の縁取りの円形バッジに入れたもの
  logo4.png         256×256  深緑一色のデュオトーン（落ち着いた配色のテーマ向け）
  logo5.png         404×160  横長の元デザイン（「Wiki」の文字入り）、透過背景。
                            文字が深緑なので明るい背景向け。正方形の枠には入れないこと
                            （72×72 に押し込むと潰れる）

tDiary（http://www.tdiary.org/）用CSSテーマ（342種、GPL2）をwikiSystemの
テーマへ変換する仕組み（PukiWiki本家の skin/tdiary.skin.php 相当）も
2026-09-04に作ったが、**theme/（Git管理・GitHub公開）には何も置いていない。**
変換プログラム（tdiary.build.py）・共有資材（tdiary.css等）・変換済みの
テーマ一式は、いずれも wikidata/freshtest/theme/ に置く運用にした（Wiki設計者の
指示。個別テーマCSSと同じ理由に加え、342種ぶんの生成物でリポジトリを
太らせないため）。詳細は wikidata/freshtest/theme/tdiary.build.py
自身のdocstringと、Tech/ChangeLog/themes/2026-09-04 を参照。

search.html は「設定中のテーマ」を継承するため、どのテーマを選んでも
検索結果ページはそのデザインに追従します。

CSS/JSは /.theme/base.css のようなURLで配信されます（別farmでは /=system/.theme/base.css）。

詳しい説明は wiki ページ /ThemeGuide（一般向け）と /Tech/ThemeGuide（開発者向け）を参照してください。
