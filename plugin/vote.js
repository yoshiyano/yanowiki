/*
 * vote プラグイン: 投票を fetch で送る（ページ遷移も履歴の追加も起きない）。
 *
 * JS が無い環境では投票を受け付けない（Wiki設計者の指示、2026-10-20。投票の
 * ボタンは _polling.js が押せるようにする）。成功したら "wiki:poll-refresh" を
 * 投げ、_polling.js に投票の欄だけを差し替えてもらう。断られたら、理由を
 * 欄のそばに出す（comment.js と同じ作り）。
 *
 * 投票の欄は polling で差し替わるので、送信はページ全体（document）で受ける。
 */
(function () {
  "use strict";

  function message(box, text) {
    var p = box.querySelector(".poll-message");
    if (!p) {
      p = document.createElement("p");
      p.className = "poll-message";
      box.appendChild(p);
    }
    p.textContent = text;
    p.hidden = !text;
  }

  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    var area = form.closest && form.closest(".vote-box");
    if (!area) return;
    ev.preventDefault();
    var button = ev.submitter;
    if (!window.fetch || !button || !button.name) {
      message(area, "この環境では投票ができません（JavaScript の fetch が必要です）。");
      return;
    }
    var data = new URLSearchParams(new FormData(form));
    data.set(button.name, button.value);  // 押したボタン（選択肢の番号）
    var box = form.closest(".poll-box");
    var buttons = form.querySelectorAll('button[type="submit"]');
    buttons.forEach(function (b) { b.disabled = true; });  // 二重投票を防ぐ
    if (box) box.dataset.pollBusy = "1";
    message(area, "");
    fetch(form.action, {
      method: "POST",
      body: data,
      headers: { "X-Requested-With": "fetch" },
      credentials: "same-origin"
    }).then(function (res) {
      if (res.status === 204) return null;
      return res.text().then(function (text) { return text || "投票できませんでした。"; });
    }, function () {
      return "通信に失敗しました。";
    }).then(function (error) {
      if (box) delete box.dataset.pollBusy;
      buttons.forEach(function (b) { b.disabled = false; });
      if (error) {
        message(area, error);
        return;
      }
      form.dispatchEvent(new CustomEvent("wiki:poll-refresh", { bubbles: true }));
    });
  });
})();
