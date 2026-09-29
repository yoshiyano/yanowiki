/* groups.js — /.groups のタブ切替と、メンバーの追加・削除・並べ替え。
 *
 * タブ（作成／編集）は**同時に入力できない**（Wiki設計者の指示、2026-09-12）。
 * サーバーが最初に見せるタブをクエリ（?tab=）で決めており、ここでは
 * ボタンを押したときにもう一方を隠すだけ（入力中の値には触れない）。
 *
 * メンバーの追加・削除は、選んだ・入力した対象をまとめて1回のJSON APIへ
 * 送る（wikilib.groupsui.render_groups_api、/.groups/api）。認証は
 * cookieで送る（credentials: "same-origin"）。
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    initTabs();
    initMembers();
  });

  function initTabs() {
    var tabs = document.querySelectorAll(".grp-tab-btn");
    if (!tabs.length) return;
    tabs.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = btn.getAttribute("data-tab");
        tabs.forEach(function (b) {
          var active = b === btn;
          b.classList.toggle("grp-tab-active", active);
          b.setAttribute("aria-selected", active ? "true" : "false");
        });
        document.querySelectorAll(".grp-panel").forEach(function (panel) {
          panel.hidden = panel.getAttribute("data-panel") !== target;
        });
      });
    });
  }

  function initMembers() {
    var root = document.querySelector(".grp[data-api]");
    if (!root) return;
    var apiUrl = root.getAttribute("data-api");
    var membersBox = root.querySelector(".grp-members");
    if (!membersBox) return; // まだグループを開いていない

    var gname = membersBox.getAttribute("data-group");
    var table = membersBox.querySelector("#grp-member-table");
    var tbody = table.querySelector("tbody");
    var removeBtn = membersBox.querySelector("#grp-remove-btn");
    var removeStatus = membersBox.querySelector("#grp-remove-status");
    var addInput = membersBox.querySelector("#grp-add-input");
    var addBtn = membersBox.querySelector("#grp-add-btn");
    var addStatus = membersBox.querySelector("#grp-add-status");

    function callApi(payload) {
      return fetch(apiUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ group: gname }, payload)),
      }).then(function (res) {
        return res.json().catch(function () {
          return { ok: false, message: "サーバーの応答を読めませんでした。" };
        });
      }).catch(function () {
        return { ok: false, message: "通信できませんでした。" };
      });
    }

    function setStatus(el, text, bad) {
      el.textContent = text || "";
      el.classList.toggle("grp-bulk-status-error", !!bad);
    }

    // ---- チェックボックス→削除ボタンの有効/無効 --------------------------

    function checkboxes() {
      return Array.prototype.slice.call(tbody.querySelectorAll(".grp-check"));
    }

    function refreshRemoveButton() {
      removeBtn.disabled = !checkboxes().some(function (cb) { return cb.checked; });
    }

    tbody.addEventListener("change", function (ev) {
      if (ev.target.classList.contains("grp-check")) refreshRemoveButton();
    });

    // ---- 削除 ------------------------------------------------------------

    removeBtn.addEventListener("click", function () {
      var targets = checkboxes().filter(function (cb) { return cb.checked; });
      if (targets.length === 0) return;
      if (!window.confirm(targets.length + "人をグループから外します。よろしいですか？")) return;
      removeBtn.disabled = true;
      setStatus(removeStatus, "削除しています…");
      callApi({ cmd: "remove", uidnums: targets.map(function (cb) {
        return Number(cb.getAttribute("data-uidnum"));
      }) }).then(function (result) {
        if (result && result.ok) {
          targets.forEach(function (cb) {
            var row = cb.closest("tr");
            if (row) row.parentNode.removeChild(row);
          });
          setStatus(removeStatus, result.removed + "人を削除しました。");
        } else {
          setStatus(removeStatus, (result && result.message) || "削除できませんでした。", true);
        }
        refreshRemoveButton();
      });
    });

    // ---- 追加 ------------------------------------------------------------

    addBtn.addEventListener("click", function () {
      var uids = addInput.value.split(/[,\s]+/).map(function (s) { return s.trim(); })
        .filter(function (s) { return s; });
      if (uids.length === 0) {
        setStatus(addStatus, "追加するユーザー名を入力してください。", true);
        return;
      }
      addBtn.disabled = true;
      setStatus(addStatus, "追加しています…");
      callApi({ cmd: "add", uids: uids }).then(function (result) {
        addBtn.disabled = false;
        if (!result || !result.ok) {
          setStatus(addStatus, (result && result.message) || "追加できませんでした。", true);
          return;
        }
        (result.added || []).forEach(function (m) { addRow(m); });
        var failed = result.failed || [];
        if (failed.length === 0) {
          setStatus(addStatus, result.added.length + "人を追加しました。");
          addInput.value = "";
        } else {
          setStatus(addStatus, result.added.length + "人を追加しました。"
            + failed.length + "人は追加できませんでした："
            + failed.map(function (f) { return f[0] + "（" + f[1] + "）"; }).join("、"), true);
        }
      });
    });

    function addRow(m) {
      var tr = document.createElement("tr");
      tr.setAttribute("data-uidnum", m.uidnum);
      tr.setAttribute("data-uid", m.uid);
      tr.setAttribute("data-joined", m.joined_at);
      var esc = function (s) {
        var d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
      };
      tr.innerHTML =
        '<td><input type="checkbox" class="grp-check" data-uidnum="' + m.uidnum
        + '" aria-label="' + esc(m.uid) + 'を削除の対象に選ぶ"></td>'
        + "<td>" + esc(m.uid) + "</td>"
        + "<td>" + esc(m.name) + "</td>"
        + "<td>" + esc(m.joined_label) + "</td>";
      tbody.appendChild(tr);
    }

    // ---- ユーザー名・登録日時でのソート ------------------------------------

    var sortState = { key: null, dir: 1 };
    table.querySelectorAll("th.grp-sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        sortState.dir = sortState.key === key ? -sortState.dir : 1;
        sortState.key = key;
        table.querySelectorAll("th.grp-sortable").forEach(function (h) {
          h.classList.remove("grp-sort-asc", "grp-sort-desc");
        });
        th.classList.add(sortState.dir > 0 ? "grp-sort-asc" : "grp-sort-desc");

        var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
        rows.sort(function (a, b) {
          var av, bv;
          if (key === "joined") {
            av = Number(a.getAttribute("data-joined"));
            bv = Number(b.getAttribute("data-joined"));
          } else {
            av = a.getAttribute("data-uid") || "";
            bv = b.getAttribute("data-uid") || "";
          }
          if (av < bv) return -sortState.dir;
          if (av > bv) return sortState.dir;
          return 0;
        });
        rows.forEach(function (row) { tbody.appendChild(row); });
      });
    });
  }
})();
