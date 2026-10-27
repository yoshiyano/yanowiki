/* mekuri プラグイン: 読み込み時に中身を戻して見えない状態で置き、クリック
   （Enter/Space）で覆いを開く。
   めくれる人かどうかはサーバーが決めており（めくれない人には data-mekuri も
   中身のデータも送られない）、ここでは見るだけ。
   中身は サーバー側で UTF-8 → XOR → Base64 に変えてある（暗号ではない目隠し）。
   document でのイベント委譲なので、AJAXで後から差し込まれた内容にも効く。 */
(function () {
  "use strict";

  function unscramble(el) {
    var d = el.getAttribute("data-mekuri-d");
    var k = el.getAttribute("data-mekuri-k");
    if (d === null || k === null) return null;
    var raw = atob(d), key = atob(k);
    var bytes = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) {
      bytes[i] = raw.charCodeAt(i) ^ key.charCodeAt(i % key.length);
    }
    return new TextDecoder("utf-8").decode(bytes);
  }

  // innerHTML に入れた<script>は動かず、読み込み時に1度だけ走る処理も届かないので、
  // 公開されている再処理の口があるプラグインには、中身へ向けて呼ぶ
  function reprocess(root) {
    try {
      if (window.Prism && Prism.highlightAllUnder) Prism.highlightAllUnder(root);
    } catch (e) { /* 色付けに失敗しても、めくること自体は続ける */ }
    try {
      if (window.KatexPlugin && KatexPlugin.renderAllUnder) KatexPlugin.renderAllUnder(root);
    } catch (e) { /* 同上 */ }
  }

  // 中身を戻して、見えない状態（visibility:hidden）のまま置く。こうしておくと、
  // 閉じている間の覆いも本来の大きさになる（ダミーのままだと、開く瞬間に大きさが変わる）。
  // 戻す前のHTMLソースには中身が無く、ここでDOMに入れる。失敗したら null
  function ready(el) {
    if (el.hasAttribute("data-mekuri-ready")) return true;
    var html;
    try {
      html = unscramble(el);
    } catch (e) {
      return false; // データが壊れていれば、何もしない（覆いは残る）
    }
    if (html === null) return false;
    var tag = el.classList.contains("mekuri-block") ? "div" : "span";
    el.innerHTML = "<" + tag + ' class="mekuri-body">' + html + "</" + tag + ">";
    el.removeAttribute("data-mekuri-d");
    el.removeAttribute("data-mekuri-k");
    el.setAttribute("data-mekuri-ready", "");
    reprocess(el);
    return true;
  }

  function prepare(root) {
    var list = (root || document).querySelectorAll(
      '.mekuri[data-mekuri="flip"]:not([data-mekuri-ready])');
    for (var i = 0; i < list.length; i++) ready(list[i]);
  }

  function flip(el) {
    if (!el || el.classList.contains("is-open")) return;
    // AJAXで後から差し込まれた分など、まだ戻していなければここで戻す
    // （この場合は開く瞬間に大きさが変わる）
    if (!ready(el)) return;
    // 開いたあとは「めくる対象」ではなくす（中身のリンクのクリックを止めないため）
    el.removeAttribute("data-mekuri");
    el.removeAttribute("aria-label");
    el.removeAttribute("tabindex");
    el.setAttribute("aria-expanded", "true");
    void el.offsetWidth; // 覆いが scaleX(1) で描かれてから開く
    requestAnimationFrame(function () { el.classList.add("is-open"); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { prepare(document); });
  } else {
    prepare(document);
  }

  document.addEventListener("click", function (ev) {
    var el = ev.target.closest && ev.target.closest('.mekuri[data-mekuri="flip"]');
    if (!el) return;
    // 開く前のクリックは、中身のリンクなどを動かさずにめくるだけにする
    ev.preventDefault();
    flip(el);
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    var el = ev.target.closest && ev.target.closest('.mekuri[data-mekuri="flip"]');
    if (!el || el !== ev.target) return;
    ev.preventDefault();
    flip(el);
  });
})();
