/*
 * bloom — 薄オレンジ系テーマの独自スクリプト（サンプル）
 *
 * ● このJSの書き方の特徴: 「共通の common.js はそのまま読み込み、足りない機能だけ足す」
 *   bloom.html は common.js → bloom.js の順に読み込みます。検索・セクション編集・
 *   目次は common.js が担当したままで、このファイルはこのテーマ固有の動きだけを持ちます。
 *
 * ● このテーマはヘッダそのものを持ちません（サイト名・コマンド・検索は
 *   すべてsubbar内、目次の直後の.subbar-commandsに置いてあります）。
 *   代わりに「上に戻る」ボタンを用意しています。
 *
 * ● 検索モーダル（.search-modal）の開閉・ドラッグ移動・ページ内検索結果
 *   （.page-search-panel）のドラッグ移動は、bloom固有ではなく全テーマ
 *   共通の機能としてcommon.js側へ移した（.search-modal-*という決まった
 *   クラス名を使うテーマなら、どのテーマでも同じ動きになる）。このファイル
 *   には「上に戻る」ボタン以外、検索まわりのロジックは残っていない。
 */
(function () {
  "use strict";

  var SHOW_AFTER = 400;  // これ以上スクロールしたらボタンを出す（px）

  var button = document.createElement("button");
  button.type = "button";
  button.className = "to-top";
  button.setAttribute("aria-label", "ページの先頭へ戻る");
  button.textContent = "↑";
  document.body.appendChild(button);

  button.addEventListener("click", function () {
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
  });

  function update() {
    button.classList.toggle("visible", window.scrollY > SHOW_AFTER);
  }

  // スクロールのたびに処理せず、描画のタイミングにまとめる
  var ticking = false;
  window.addEventListener("scroll", function () {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      update();
      ticking = false;
    });
  }, { passive: true });

  update();
})();
