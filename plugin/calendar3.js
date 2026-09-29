/*
 * calendar3 — 前後の月（<< >>）を押したとき、ページ全体を読み込み直さず、
 * カレンダーの表だけを取り替える（本家 calendar3.inc.php の load_calendar3 と同じ動き）。
 *
 * リンクの href は「このページを問い合わせ付きで開き直すURL」なので、この
 * スクリプトが動かない環境でも前後の月へ移れる。ここでは押されたリンクの
 * data-calendar3-file・data-calendar3-date を読み、枠（.calendar3-frame）の
 * data-calendar3-api へ問い合わせて、返ってきた表で枠の中身を置き換える。
 * 表は差し替えのたびに作り直されるので、クリックは document で受ける（委譲）。
 */
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[data-calendar3-date]");
    if (!link) return;
    var frame = link.closest(".calendar3-frame");
    if (!frame || !frame.dataset.calendar3Api) return;
    event.preventDefault();

    var url = frame.dataset.calendar3Api
      + "?file=" + encodeURIComponent(link.dataset.calendar3File || "")
      + "&date=" + encodeURIComponent(link.dataset.calendar3Date || "")
      + "&page=" + encodeURIComponent(frame.dataset.calendar3Page || "");
    frame.classList.add("is-loading");
    fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
      .then(function (html) { frame.innerHTML = html; })
      .catch(function () {
        // 取れなければ、ふつうのリンクとして開き直す
        window.location.href = link.href;
      })
      .then(function () { frame.classList.remove("is-loading"); });
  });
})();
