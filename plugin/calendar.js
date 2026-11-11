/*
 * calendar 系の共通 — 日ごとのページを年・月のフォルダへ組み替えている間の枠
 * （.calendar-migrate。calendar_.py「日ごとのページは `年/月/` のフォルダに置く」）。
 *
 *   - data-calendar-migrate-start="1" なら、_action へ組み替えの開始を頼む
 *     （POST、X-Requested-With: fetch。編集の権限がある人が開いたときだけ 1 になる）
 *   - 1 秒ごとに進み具合を問い合わせ、プログレスバー・件数・作業中の YYYY/MM を更新する
 *   - 終わったらページを読み込み直す。うまく移せなかったページがあれば、一覧を出して止まる
 *   - 同じ基準の枠が 1 ページに 2 つあっても、問い合わせは 1 つにまとめる
 */
(function () {
  "use strict";

  function show(boxes, data) {
    boxes.forEach(function (box) {
      var bar = box.querySelector(".calendar-migrate-bar");
      if (bar) { bar.max = Math.max(data.total || 0, 1); bar.value = data.done || 0; }
      var count = box.querySelector(".calendar-migrate-count");
      if (count) count.textContent = (data.done || 0) + " / " + (data.total || 0);
      var cur = box.querySelector(".calendar-migrate-current");
      if (cur) cur.textContent = data.current || "";
    });
  }

  function message(boxes, lines, reload) {
    boxes.forEach(function (box) {
      var area = box.querySelector(".calendar-migrate-message");
      if (!area) return;
      area.textContent = "";
      lines.forEach(function (line) {
        var p = document.createElement("p");
        p.textContent = line;
        area.appendChild(p);
      });
      if (reload) {
        var button = document.createElement("button");
        button.type = "button";
        button.textContent = "ページを読み込み直す";
        button.addEventListener("click", function () { window.location.reload(); });
        area.appendChild(button);
      }
    });
  }

  function query(box, what) {
    return "migrate=" + what
      + "&base=" + encodeURIComponent(box.dataset.calendarMigrateBase || "")
      + "&sep=" + encodeURIComponent(box.dataset.calendarMigrateSep || "");
  }

  function watch(boxes) {
    var box = boxes[0];
    var api = box.dataset.calendarMigrateApi;

    function poll() {
      fetch(api + "?" + query(box, "status"), {
        credentials: "same-origin", headers: { "X-Requested-With": "fetch" }
      }).then(function (res) {
        return res.json();
      }).then(function (data) {
        if (data.error) { message(boxes, [data.error], true); return; }
        show(boxes, data);
        if (data.state === "running") { setTimeout(poll, 1000); return; }
        if (data.errors && data.errors.length) {
          message(boxes, ["移せなかったページがあります。"].concat(data.errors), true);
          return;
        }
        window.location.reload();
      }).catch(function () {
        setTimeout(poll, 3000);   // 通信の失敗は、しばらくして問い合わせ直す
      });
    }

    if (box.dataset.calendarMigrateStart !== "1") { poll(); return; }
    fetch(api, {
      method: "POST", credentials: "same-origin",
      headers: { "X-Requested-With": "fetch",
                 "Content-Type": "application/x-www-form-urlencoded" },
      body: query(box, "start")
    }).then(function (res) {
      return res.json();
    }).then(function (data) {
      if (data.error) { message(boxes, [data.error], true); return; }
      show(boxes, data);
      poll();
    }).catch(function () {
      message(boxes, ["ファイル構成の更新を始められませんでした。"], true);
    });
  }

  function init() {
    var groups = {};
    document.querySelectorAll(".calendar-migrate").forEach(function (box) {
      var key = box.dataset.calendarMigrateBase + "\n" + box.dataset.calendarMigrateSep;
      (groups[key] = groups[key] || []).push(box);
    });
    Object.keys(groups).forEach(function (key) {
      var boxes = groups[key];
      // 始める枠を先頭にする（1 つでも start があれば頼む）
      boxes.sort(function (a, b) {
        return (b.dataset.calendarMigrateStart === "1") - (a.dataset.calendarMigrateStart === "1");
      });
      watch(boxes);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
