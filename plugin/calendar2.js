/*
 * calendar2 — 前後の月（<< >>）を押したとき、ページ全体を読み込み直さず、
 * 枠（カレンダーと今日のページの中身）だけを取り替える（calendar3.js と同じ作り）。
 *
 * リンクの href は「このページを問い合わせ付きで開き直すURL」なので、この
 * スクリプトが動かない環境でも前後の月へ移れる。ここでは押されたリンクの
 * data-calendar2-date と、枠（.calendar2-frame）の data-calendar2-file・
 * data-calendar2-off を読み、枠の data-calendar2-api へ問い合わせて、返ってきた
 * 中身で枠を置き換える。
 * 表は差し替えのたびに作り直されるので、クリックは document で受ける（委譲）。
 */
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[data-calendar2-date]");
    if (!link) return;
    var frame = link.closest(".calendar2-frame");
    if (!frame || !frame.dataset.calendar2Api) return;
    event.preventDefault();

    var url = frame.dataset.calendar2Api
      + "?file=" + encodeURIComponent(frame.dataset.calendar2File || "")
      + "&date=" + encodeURIComponent(link.dataset.calendar2Date || "")
      + "&page=" + encodeURIComponent(frame.dataset.calendar2Page || "")
      + "&off=" + encodeURIComponent(frame.dataset.calendar2Off || "0");
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
