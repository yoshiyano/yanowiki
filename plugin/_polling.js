/*
 * polling（plugin/_polling.py）のブラウザ側。comment・vote などの描画範囲
 * （.poll-box）を、保存されている本文に合わせて差し替える。
 *
 *   - ページごとに 1 回まとめて問い合わせる（data-poll-page ごと。#include で
 *     差し込んだページは別の組になる）。問い合わせ先はその組の最初の
 *     data-poll-action（どのプラグインの受け口も _polling.py に任せている）
 *   - 間隔は 5 分。タブが隠れている間は問い合わせない。戻ったときに 5 分以上
 *     経っていれば、すぐに問い合わせる（Wiki設計者の指示、2026-10-22）
 *   - 版（data-poll-version）が同じなら、サーバは描かずに unchanged を返し、
 *     ここでは何もしない
 *   - 返ってきた ID のうち、知らないものは無視する。missing なら「該当フォームが
 *     なくなりました」と出して送信ボタンを止める（入力欄の中身は消さない）
 *   - 差し替えるときは、書きかけの入力（name の付いた入力欄の値）とカーソルの
 *     位置を引き継ぐ。送信している最中の範囲（data-poll-busy）は差し替えない
 *   - 投稿が成功したら、comment.js・vote.js が "wiki:poll-refresh" イベントを
 *     投げるので、そのページだけをすぐ問い合わせる（ページの再読み込みはしない）
 *   - JS が動く環境でだけ送信できるように、data-needs-js の付いたボタンの
 *     disabled を外す（JS が無ければ <noscript> の案内が出る）
 */
(function () {
  "use strict";
  var INTERVAL = 5 * 60 * 1000;
  var TICK = 60 * 1000;
  var lastPoll = Date.now();
  var running = {};
  var again = {};

  function enable(root) {
    root.querySelectorAll("[data-needs-js]").forEach(function (el) {
      el.disabled = false;
      el.removeAttribute("data-needs-js");
    });
  }

  function boxesOf(page) {
    return [].filter.call(document.querySelectorAll(".poll-box"), function (box) {
      return box.dataset.pollPage === page && !box.classList.contains("poll-gone");
    });
  }

  function pages() {
    var seen = [];
    document.querySelectorAll(".poll-box").forEach(function (box) {
      if (!box.classList.contains("poll-gone") && seen.indexOf(box.dataset.pollPage) < 0) {
        seen.push(box.dataset.pollPage);
      }
    });
    return seen;
  }

  // 書きかけの入力を、新しい描画範囲の同じ name・同じ順番の入力欄へ写す
  function carry(from, to) {
    var focused = document.activeElement;
    from.querySelectorAll("input[name], textarea[name]").forEach(function (el) {
      if (el.type === "hidden" || el.type === "submit" || el.type === "button") return;
      var same = [].filter.call(from.querySelectorAll('[name="' + el.name + '"]'), function (x) {
        return x.type === el.type;
      });
      var k = same.indexOf(el);
      var target = [].filter.call(to.querySelectorAll('[name="' + el.name + '"]'), function (x) {
        return x.type === el.type;
      })[k];
      if (!target) return;
      if (el.type === "checkbox" || el.type === "radio") target.checked = el.checked;
      else target.value = el.value;
      if (el === focused) {
        to._pollFocus = { el: target, start: el.selectionStart, end: el.selectionEnd };
      }
    });
  }

  function replace(box, html) {
    var holder = document.createElement("div");
    holder.innerHTML = html;
    var fresh = holder.querySelector(".poll-box");
    if (!fresh) return;
    carry(box, fresh);
    enable(fresh);
    box.replaceWith(fresh);
    var f = fresh._pollFocus;
    if (f) {
      f.el.focus();
      try { f.el.setSelectionRange(f.start, f.end); } catch (e) { /* 範囲を持たない入力欄 */ }
    }
  }

  function gone(box) {
    box.classList.add("poll-gone");
    box.querySelectorAll('button, input[type="submit"]').forEach(function (b) { b.disabled = true; });
    var p = document.createElement("p");
    p.className = "poll-message";
    p.textContent = "該当フォームがなくなりました。入力した内容は残っています。";
    box.appendChild(p);
  }

  function poll(page) {
    var boxes = boxesOf(page);
    if (!boxes.length) return;
    if (running[page]) {
      again[page] = true;  // 問い合わせの途中に頼まれたら、終わってからもう 1 回
      return;
    }
    running[page] = true;
    var ids = [];
    boxes.forEach(function (box) {
      if (ids.indexOf(box.dataset.pollId) < 0) ids.push(box.dataset.pollId);
    });
    var query = new URLSearchParams({
      poll: "1", page: page, ids: ids.join(","), version: boxes[0].dataset.pollVersion || ""
    });
    fetch(boxes[0].dataset.pollAction + "?" + query.toString(), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" }
    }).then(function (res) {
      return res.ok ? res.json() : null;
    }).then(function (data) {
      if (!data || data.unchanged) return;
      boxesOf(page).forEach(function (box) {
        if (box.dataset.pollBusy) return;
        var r = (data.calls || {})[box.dataset.pollId];
        if (!r) return;  // 知らない ID は無視する
        if (r.missing) gone(box);
        else if (typeof r.html === "string") replace(box, r.html);
      });
      boxesOf(page).forEach(function (box) {
        if (!box.dataset.pollBusy && data.version) box.dataset.pollVersion = data.version;
      });
    }).catch(function () {
      // 通信の失敗は次の回に任せる
    }).then(function () {
      running[page] = false;
      if (again[page]) {
        again[page] = false;
        poll(page);
      }
    });
  }

  function pollAll() {
    lastPoll = Date.now();
    pages().forEach(poll);
  }

  enable(document);
  setInterval(function () {
    if (!document.hidden && Date.now() - lastPoll >= INTERVAL) pollAll();
  }, TICK);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && Date.now() - lastPoll >= INTERVAL) pollAll();
  });
  document.addEventListener("wiki:poll-refresh", function (ev) {
    var box = ev.target.closest && ev.target.closest(".poll-box");
    if (box) poll(box.dataset.pollPage);
  });
})();
