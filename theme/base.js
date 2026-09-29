/*
 * base — 標準テーマの独自スクリプト
 *
 * ● このJSの書き方の特徴: 「共通の common.js はそのまま読み込み、足りない機能だけ足す」
 *   base.html は common.js → base.js の順に読み込みます。検索・セクション編集・
 *   目次は common.js が担当したままで、このファイルはこのテーマ固有の動きだけを持ちます。
 *
 * ● menu1（左カラム、既定: mainmenuページ）は入れ子リストで階層メニューになる。
 *   階層が深いと縦に伸びすぎるため、枝（子リストを持つ項目）ごとに開閉できるようにする。
 *   ネイティブの <details>/<summary> に組み替えることで、開閉の状態管理・キーボード操作
 *   （Enter/Space）・三角マーカーの描画をブラウザ標準機能に任せている。
 *
 * ● .mainbar .menu1 という組み合わせは base 独自のマークアップ（fresh/bloom/post_it_1
 *   はmenu1を別の入れ物に置く）にしか出てこないため、他テーマがこのスクリプトを
 *   共有しても（fresh は継承の都合上そうなる）何も起きない。
 */
(function () {
  "use strict";

  var root = document.querySelector(".mainbar .menu1");
  if (!root) return;

  // 先に全 li を集めてから組み替える（組み替え中にツリー構造が変わっても、
  // 保持している li 参照そのものは動かないので影響しない）。
  var items = root.querySelectorAll("li");

  items.forEach(function (li) {
    var childList = li.querySelector(":scope > ul, :scope > ol");
    if (!childList) return;

    var details = document.createElement("details");
    details.className = "menu1-node";
    details.open = false;

    var summary = document.createElement("summary");
    // childList より手前の中身（リンクや文章。markdownの改行有無で
    // <p>で包まれる場合とそのままの場合がある）を丸ごとsummaryへ移す。
    while (li.firstChild && li.firstChild !== childList) {
      summary.appendChild(li.firstChild);
    }

    details.appendChild(summary);
    details.appendChild(childList);
    li.appendChild(details);
  });
})();
