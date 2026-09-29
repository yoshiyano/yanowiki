/*
 * ac — 折りたたみの補助。<details> の開閉そのものはブラウザがするので、ここでは
 *   1. #ac(h): すぐ上の要素（見出しなど）を、押すと開閉するボタンにする
 *   2. #ac(all): 「全て開く／全て閉じる」ボタンを見せて働かせる
 * の2つだけを受け持つ。どちらも JavaScript が無ければ働かないので、無いときは
 * <summary>（「…」）で開け、ボタンは hidden のまま出ない（plugin/ac.py の技術資料）。
 */
(function () {
  "use strict";

  var ALT = "plugin-ac-alt";

  function altOf(details) {
    var next = details.nextElementSibling;
    return next && next.classList.contains(ALT) ? next : null;
  }

  /* ---- #ac(h): 押すところにした見出しの余白（Wiki設計者の指示、2026-09-27） ----
     上の余白をテーマの値の1/4に、下の余白を0にする。見出しの余白はテーマごとに
     違う（2rem・3rem・1.4em…）ので、CSSに決まった値を書かず、いま効いている値を
     測って1/4にする。値は見出しの文字の大きさに対する比（em）で入れ、サイトの
     拡大・縮小に追随させる。見出し（h1〜h6）でない要素は触らない */
  function tightenHeading(head) {
    if (!/^H[1-6]$/.test(head.tagName)) return;
    var style = window.getComputedStyle(head);
    var size = parseFloat(style.fontSize) || 16;
    var top = parseFloat(style.marginTop) || 0;
    head.style.marginTop = (top / 4 / size).toFixed(3) + "em";
    head.style.marginBottom = "0";
  }

  /* ---- #ac(h): 直前の要素を押すところにする ---- */
  function enhanceHead(details) {
    var head = details.previousElementSibling;
    if (!head || head.classList.contains("plugin-ac-header")) return;
    details.classList.add("plugin-ac-headed");
    tightenHeading(head);
    head.classList.add("plugin-ac-header");
    head.setAttribute("role", "button");
    head.setAttribute("tabindex", "0");
    head.setAttribute("aria-controls", details.id);
    var icon = document.createElement("span");
    icon.className = "plugin-ac-icon";
    icon.setAttribute("aria-hidden", "true");
    head.insertBefore(icon, head.firstChild);

    function sync() {
      head.setAttribute("aria-expanded", details.open ? "true" : "false");
      head.classList.toggle("is-open", details.open);
    }
    function toggle() { details.open = !details.open; }
    head.addEventListener("click", function (event) {
      if (event.target.closest("a, button, input, label")) return;  // 見出しの中のリンクなど
      toggle();
    });
    head.addEventListener("keydown", function (event) {
      if (event.target !== head) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      }
    });
    details.addEventListener("toggle", sync);
    sync();
  }

  /* ---- #ac(all): 後ろの同じ階層の折りたたみをまとめて開閉 ---- */
  function targetsOf(ctrl) {
    var list = [];
    for (var el = ctrl.nextElementSibling; el; el = el.nextElementSibling) {
      if (el.classList.contains("plugin-ac-ctrl")) break;
      if (el.matches("details.plugin-ac")) list.push(el);
    }
    return list;
  }

  function updateButton(ctrl) {
    var button = ctrl.querySelector(".plugin-ac-all");
    var items = targetsOf(ctrl);
    var allOpen = items.length > 0 && items.every(function (d) { return d.open; });
    button.textContent = allOpen ? "全て閉じる" : "全て開く";
    button.setAttribute("aria-pressed", allOpen ? "true" : "false");
    return allOpen;
  }

  function enhanceAll(ctrl) {
    var button = ctrl.querySelector(".plugin-ac-all");
    if (!button) return;
    ctrl.hidden = false;
    button.addEventListener("click", function () {
      var open = !updateButton(ctrl);
      targetsOf(ctrl).forEach(function (d) { d.open = open; });
      updateButton(ctrl);
    });
    targetsOf(ctrl).forEach(function (d) {
      d.addEventListener("toggle", function () { updateButton(ctrl); });
    });
    updateButton(ctrl);
  }

  /* ---- alt: 閉じているあいだだけ案内を出す（h のとき。ほかは CSS で足りる） ---- */
  function syncAlt(details) {
    var alt = altOf(details);
    if (!alt) return;
    var sync = function () { alt.hidden = details.open; };
    details.addEventListener("toggle", sync);
    sync();
  }

  function init(root) {
    root.querySelectorAll('details.plugin-ac[data-ac-head="prev"]').forEach(enhanceHead);
    root.querySelectorAll("details.plugin-ac").forEach(syncAlt);
    root.querySelectorAll("div.plugin-ac-ctrl:not(.plugin-ac-end)").forEach(enhanceAll);
  }

  init(document);
})();
