/*
 * katex プラグインの組版処理。
 *
 * KaTeX本体（CSS/JS/フォント）は`_sys/vendor/katex/`にローカル同梱して
 * あり、`/.vendor/katex/`から配信される（`wikilib/vendor.py`）。
 * バージョンは同梱物そのもので固定されている（現在0.16.11）。上げる
 * ときは`_sys/vendor/README.txt`の手順で同梱物を丸ごと差し替える。
 *
 * .katex-source（#katex()/&katex();が出力する、生LaTeXの入れ物）が
 * 1つも無い箇所では何もしない（KaTeXの資材を無駄に読み込まない）。
 * data-katex-display属性の有無で、KaTeXのdisplayMode（独立した数式か、
 * 文中の数式か）を決める（詳しくはkatex.pyの技術資料）。
 *
 * window.KatexPlugin.renderAllUnder(root) を編集画面のライブプレビュー
 * から呼べるように公開している（Prism.highlightAllUnder(root)と同じ
 * 考えかた。詳しくはkatex.pyの技術資料）。
 */
(function () {
  "use strict";

  // サイト全体がサブパス配下にある構成（server.prefix）に追随するため、
  // 根からの絶対パス決め打ちにせず、この<script>自身のURL（/.plugin/
  // katex.jsとして配信される）から接頭辞込みの根を逆算する。
  var self = document.currentScript;
  var root = self ? self.src.replace(/\/\.plugin\/katex\.js(\?.*)?$/, "") : "";
  var BASE = root + "/.vendor/katex/";

  var loadPromise = null;

  function ensureLoaded() {
    if (loadPromise) return loadPromise;
    loadPromise = new Promise(function (resolve, reject) {
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = BASE + "katex.min.css";
      document.head.appendChild(link);

      var script = document.createElement("script");
      script.src = BASE + "katex.min.js";
      script.onload = function () {
        resolve();
      };
      script.onerror = function () {
        reject(new Error("KaTeX本体の読み込みに失敗しました"));
      };
      document.head.appendChild(script);
    });
    return loadPromise;
  }

  function renderAllUnder(scope) {
    var sources = (scope || document).querySelectorAll(".katex-source");
    if (!sources.length) return;
    ensureLoaded().then(function () {
      sources.forEach(function (el) {
        var display = el.hasAttribute("data-katex-display");
        var source = el.textContent;
        try {
          window.katex.render(source, el, {
            displayMode: display,
            throwOnError: false,
          });
        } catch (e) {
          // throwOnError: false にしていても、KaTeX自体が想定していない
          // 例外はここに来ることがある。原文を消さず、エラーだと分かる
          // 形にとどめる。
          el.textContent = source;
          el.classList.add("katex-source-error");
          el.title = e && e.message ? e.message : String(e);
        }
      });
    }).catch(function (e) {
      // KaTeX本体自体が読み込めなかった場合（_sys/vendor/katex/の資材が
      // 何らかの理由で404等）。個々の数式のLaTeX構文エラーとは別に、
      // 対象すべてを一括でエラー表示にする（原文は消さない）。
      sources.forEach(function (el) {
        el.classList.add("katex-source-error");
        el.title = e && e.message ? e.message : String(e);
      });
    });
  }

  window.KatexPlugin = { renderAllUnder: renderAllUnder };

  renderAllUnder(document);
})();
