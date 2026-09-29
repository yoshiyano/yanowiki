/*
  pkwk のスクリプト。内容は post_it_1.js と同じ（このテーマは post_it_1 の
  動きをそのまま引き継ぐ）。2つのことを担当する。
  （編集のホットキー Alt+E は他テーマと同じく common.js が受け持つ。以前ここにあった
  3連打の独自実装は、操作メニューを共通化したため廃止した。2026-09-24）
    1. 700px幅を下回ったときのハンバーガーメニュー（#menu-toggle）による
       #rightbar のスライドイン/アウト開閉。
    2. 620px幅（post_it_1.cssの @media (max-width: 620px)）を下回ったときに検索フォーム
       （#site-search-form）を .header-row-title から #rightbar の先頭へ
       移動し、上回ったら元に戻す（Wiki設計者の指示、2026-09-05）。CSSだけでは
       別々の親を持つ要素間の移動はできないため、DOM操作で行う。
       ノードを直接 insertBefore で動かすだけなので、common.js が
       この要素に付けたイベントリスナーは移動後も保持される。
       ハンバーガーボタンは動かさない（ヘッダ2行目 .header-row-path に
       残り、620px以下ではCSSでposition: fixedにして画面右上へ固定する）。
  検索フォームは標準の <form method="get"> だけで完結するため、それ以外の
  ロジックは持たない（ページ内検索・目次ハイライト等は common.js 側）。
*/
(function () {
  "use strict";

  var menuToggle = document.getElementById("menu-toggle");
  var rightbar = document.getElementById("rightbar");
  var backdrop = document.getElementById("menu-backdrop");
  if (!menuToggle || !rightbar || !backdrop) return;

  function isMenuOpen() {
    return rightbar.classList.contains("is-open");
  }

  function closeMenu() {
    rightbar.classList.remove("is-open");
    backdrop.hidden = true;
    menuToggle.setAttribute("aria-expanded", "false");
  }

  function openMenu() {
    rightbar.classList.add("is-open");
    backdrop.hidden = false;
    menuToggle.setAttribute("aria-expanded", "true");
  }

  menuToggle.addEventListener("click", function () {
    if (isMenuOpen()) closeMenu(); else openMenu();
  });
  backdrop.addEventListener("click", closeMenu);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && isMenuOpen()) closeMenu();
  });

  // 画面幅がブレークポイント（post_it_1.cssの700px）を超えたら、
  // off-canvas表示自体が解除されるため、開閉状態も合わせてリセットしておく。
  var mql = window.matchMedia("(max-width: 700px)");
  var onBreakpointChange = function (event) {
    if (!event.matches) closeMenu();
  };
  if (mql.addEventListener) {
    mql.addEventListener("change", onBreakpointChange);
  } else if (mql.addListener) {
    mql.addListener(onBreakpointChange);
  }

  // 620px幅（post_it_1.cssの @media (max-width: 620px)）を下回ったら検索フォームを
  // #rightbar（ハンバーガーメニューの中）の先頭へ移動し、上回ったら
  // .header-row-title（検索窓の元の場所。ヘッダ1行目の末尾）へ戻す
  // （Wiki設計者の指示、2026-09-05）。
  // .search-options（検索の詳細条件パネル）はposition: fixedで自分の
  // 位置を計算し直す作りのため、動かす必要はない。
  var searchForm = document.getElementById("site-search-form");
  var titleRow = document.querySelector(".header-row-title");
  if (searchForm && titleRow) {
    var mqlSearch = window.matchMedia("(max-width: 620px)");
    var placeSearch = function (narrow) {
      if (narrow) {
        // メニューの中では先頭（menu1などより上）に置く
        if (searchForm.parentNode !== rightbar) {
          rightbar.insertBefore(searchForm, rightbar.firstChild);
        }
      } else {
        // ヘッダ1行目では末尾（サイト名・タイトルの後ろ）に戻す
        if (searchForm.parentNode !== titleRow) {
          titleRow.appendChild(searchForm);
        }
      }
    };
    placeSearch(mqlSearch.matches);
    var onSearchBreakpointChange = function (event) {
      placeSearch(event.matches);
    };
    if (mqlSearch.addEventListener) {
      mqlSearch.addEventListener("change", onSearchBreakpointChange);
    } else if (mqlSearch.addListener) {
      mqlSearch.addListener(onSearchBreakpointChange);
    }
  }
})();
