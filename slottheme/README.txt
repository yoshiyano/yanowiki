スロットHTML のテーマ（全Wiki共通）を置くフォルダです。

スロットHTML は、式・ループ・<script> を持たないふつうの HTML のテーマです。本体が値と
部品を埋める場所に目印（data-text・data-slot・<wiki-slot> など）を付けておくと、本体が
HTML5 パーサで解析し、許可リストでサニタイズしてから埋めます。Jinja2 はこのフォルダを
読まないので、テーマからサーバのコードは動きません（wikilib.slottheme）。

  <名前>.html              テーマ（フォルダ形式の <名前>/<名前>.html も可）
  CSS・画像・フォント       /.slottheme/<テーマ名>/<ファイル名> で配る（.html・.js・.svg は配らない）

個別Wiki用は wikidata/<Wiki名>/slottheme/ に置きます（こちらより先に探します）。
同じ名前の Jinja2 のテーマ（theme/）があれば、そちらが描かれます。
書きかた・スロット・許可リストは wikiThemes の仕様案（slot/SPEC.md）に従います。
