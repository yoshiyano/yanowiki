/* staffperms.js — /.admin/staffperms の表の操作。
 *
 *   前提の揃え  … 前提のある操作は、前提を外すと外れ、付けると前提も付く
 *                 （data-needs。サーバー側の wikilib.staffperms.resolve と同じ決まり）
 *   既定に戻す  … その助手の列を、既定（data-default）の状態へ戻す。保存するまで反映されない
 *   変更の印    … 開いたときの状態（data-saved）と違うセルに印を付け、数を出す
 *
 * 保存は普通のフォームの送信（POST）。JSが動かなくても保存はできる（その場合、
 * 前提の揃えはサーバーが行う）。
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var table = document.getElementById("sp-table");
    if (!table) return;
    var statusEl = document.getElementById("sp-status");
    var saveBtn = document.getElementById("sp-save");

    var boxes = Array.prototype.slice.call(table.querySelectorAll('input[type="checkbox"]'));
    if (boxes.length === 0) return;

    // 助手ごとに { 権限の名前: チェックボックス } を作る
    var columns = {};
    boxes.forEach(function (box) {
      var uidnum = box.getAttribute("data-uidnum");
      (columns[uidnum] = columns[uidnum] || {})[box.getAttribute("data-key")] = box;
      box.setAttribute("data-saved", box.checked ? "1" : "0");
    });

    function needsOf(box) {
      var text = box.getAttribute("data-needs") || "";
      return text ? text.split(" ") : [];
    }

    // 付けた操作の前提を、順にたどって付ける
    function ensureNeeds(box) {
      var column = columns[box.getAttribute("data-uidnum")];
      needsOf(box).forEach(function (key) {
        var need = column[key];
        if (need && !need.checked) {
          need.checked = true;
          ensureNeeds(need);
        }
      });
    }

    // 外した操作を前提にしている操作を、順にたどって外す
    function dropDependents(box) {
      var column = columns[box.getAttribute("data-uidnum")];
      var key = box.getAttribute("data-key");
      Object.keys(column).forEach(function (other) {
        var dep = column[other];
        if (dep.checked && needsOf(dep).indexOf(key) >= 0) {
          dep.checked = false;
          dropDependents(dep);
        }
      });
    }

    function refresh() {
      var changed = 0;
      boxes.forEach(function (box) {
        var diff = (box.checked ? "1" : "0") !== box.getAttribute("data-saved");
        box.parentNode.classList.toggle("sp-changed", diff);
        if (diff) changed++;
      });
      if (statusEl) {
        statusEl.textContent = changed ? "保存していない変更が " + changed + " 件あります。" : "";
      }
    }

    table.addEventListener("change", function (ev) {
      var box = ev.target;
      if (!box.matches || !box.matches('input[type="checkbox"]')) return;
      if (box.checked) ensureNeeds(box); else dropDependents(box);
      refresh();
    });

    Array.prototype.forEach.call(table.querySelectorAll(".sp-reset"), function (button) {
      button.addEventListener("click", function () {
        var column = columns[button.getAttribute("data-uidnum")] || {};
        Object.keys(column).forEach(function (key) {
          column[key].checked = column[key].getAttribute("data-default") === "1";
        });
        refresh();
      });
    });

    // 保存せずに離れようとしたら確かめる（送信のときは確かめない）
    var submitting = false;
    var form = document.getElementById("sp-form");
    if (form) {
      form.addEventListener("submit", function () { submitting = true; });
    }
    window.addEventListener("beforeunload", function (ev) {
      if (submitting) return;
      if (table.querySelector(".sp-changed")) {
        ev.preventDefault();
        ev.returnValue = "";
      }
    });

    if (saveBtn) refresh();
  });
})();
