/*
 * glossarytip プラグインの実処理。
 *
 * このファイルは、ページで #glossarytip() が実際に呼ばれたときだけ
 * /.plugin/glossarytip.js として読み込まれる（CSSと同じ仕組み。
 * plugin/glossarytip.py の技術資料参照）。
 *
 * 1. 本文（main.content）の中にある <dl>（定義リスト。mdit_py_plugins の
 *    deflist / PukiWiki記法の ":用語|説明" が両方ともこの形で出力される）
 *    から、<dt> と <dd> のペアを集めて「用語 → 説明」の対応表を作る。
 *    1つの <dt> に複数の <code>用語</code> が並ぶ書きかた
 *    （例: <dt><code>subpath</code> / <code>subpaths</code></dt>）にも
 *    対応し、それぞれを別の用語として扱う。
 * 2. その <dl> 自身を除いた本文中のテキスト（<code> の中も含む）を走査し、
 *    対応表の用語と単語境界つきで完全一致する箇所を
 *    <abbr title="説明">用語</abbr> で包む。
 *
 * 大文字小文字は区別する（識別子的な語を想定しているため）。
 * 二重に包まないよう、既に <abbr> の中にあるテキストは対象外にする。
 */
(function () {
  "use strict";

  var root = document.querySelector("main.content") || document.querySelector(".content");
  if (!root) return;

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  // ---- 1. <dl> から 用語 → 説明 の対応表を作る ----
  var terms = {};
  [].slice.call(root.querySelectorAll("dl")).forEach(function (dl) {
    var pendingWords = [];
    [].slice.call(dl.children).forEach(function (el) {
      if (el.tagName === "DT") {
        var codes = [].slice.call(el.querySelectorAll("code"));
        var words = codes.length ? codes.map(function (c) { return c.textContent.trim(); })
                                  : [el.textContent.trim()];
        words.forEach(function (w) { if (w) pendingWords.push(w); });
      } else if (el.tagName === "DD") {
        var definition = el.textContent.trim();
        if (definition) {
          pendingWords.forEach(function (w) {
            // 同じ用語が複数回定義されていても、最初に見つかったものを使う
            if (!Object.prototype.hasOwnProperty.call(terms, w)) terms[w] = definition;
          });
        }
        pendingWords = [];
      }
    });
  });

  var words = Object.keys(terms);
  if (!words.length) return;

  // 長い語を先に試す（"subpaths" が "subpath" の一致に食われないように）
  words.sort(function (a, b) { return b.length - a.length; });
  var alternation = words.map(escapeRegExp).join("|");
  // \b（JavaScript正規表現の標準の単語境界）は [A-Za-z0-9_] の内外の
  // 切り替わりでしか成立しないため、両側とも日本語（\wに含まれない文字）
  // だと境界を検出できず、日本語のみの用語が一致しなかった
  // （Tech/GlossarytipBoundaryBug.md参照）。ASCII語の文字を明示的に除く
  // lookaround方式に置き換えることで、ASCII語との誤結合を防ぎつつ
  // 日本語のみの用語にも対応する。
  var testPattern = new RegExp("(?<![A-Za-z0-9_])(?:" + alternation + ")(?![A-Za-z0-9_])");
  var splitPattern = new RegExp("((?<![A-Za-z0-9_])(?:" + alternation + ")(?![A-Za-z0-9_]))");

  // ---- 2. <dl>・<abbr>・<script>・<style> の外にあるテキストノードを集める ----
  var targets = [];
  var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: function (node) {
      var el = node.parentElement;
      while (el && el !== root) {
        var tag = el.tagName;
        if (tag === "DL" || tag === "ABBR" || tag === "SCRIPT" || tag === "STYLE") {
          return NodeFilter.FILTER_REJECT;
        }
        el = el.parentElement;
      }
      return testPattern.test(node.data) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
    },
  });
  var node;
  while ((node = walker.nextNode())) targets.push(node);

  // ---- 3. マッチ箇所を <abbr title="説明"> で包む ----
  targets.forEach(function (textNode) {
    var parts = textNode.data.split(splitPattern);
    if (parts.length <= 1) return;

    var frag = document.createDocumentFragment();
    parts.forEach(function (part, i) {
      // split の奇数番目が splitPattern の捕捉グループ（＝一致した用語）
      if (i % 2 === 1 && Object.prototype.hasOwnProperty.call(terms, part)) {
        var abbr = document.createElement("abbr");
        abbr.className = "glossarytip-term";
        abbr.title = terms[part];
        abbr.textContent = part;
        frag.appendChild(abbr);
      } else if (part) {
        frag.appendChild(document.createTextNode(part));
      }
    });
    textNode.parentNode.replaceChild(frag, textNode);
  });
})();
